#!/usr/bin/env python3
"""Send opt-in card alert emails (new cards, watched-card price changes).

Does nothing unless CARD_ALERTS_ENABLED=1. Run once a day after the official and
price syncs (deploy/optcgassistant/run_daily_card_alerts.sh).

  python3 scripts/send_card_alerts.py            # send
  python3 scripts/send_card_alerts.py --dry-run  # print what would go out, change nothing

The first run only records the current card list (meta/card_alerts_state.json),
so nobody gets a 5,000-card "new cards" email. A watched card's first seen price
is stored as its baseline without an email.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

import card_alerts  # noqa: E402

CARDS_PATH = ROOT / "index" / "cards_by_id.json"
PRICES_PATH = ROOT / "meta" / "market_prices.json"
AUTH_DB = ROOT / "meta" / "auth.db"
STATE_PATH = ROOT / "meta" / "card_alerts_state.json"
NEW_CARDS_LIST_MAX = 30


def _site_url() -> str:
    return str(os.getenv("OPCG_SITE_URL") or "https://optcgassistant.com").strip().rstrip("/")


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def run(*, dry_run: bool, auth_db: Path = AUTH_DB, state_path: Path = STATE_PATH) -> dict[str, int]:
    stats = {"recipients": 0, "sent": 0, "failed": 0, "new_cards": 0, "baselines": 0}
    cards = _load_json(CARDS_PATH)
    prices = (_load_json(PRICES_PATH).get("cards") or {})
    prices = {str(k).upper(): v for k, v in prices.items() if isinstance(v, dict)}
    if not cards:
        print("[card-alerts] cards_by_id.json missing or empty; stop")
        return stats
    new_ids, first_run = card_alerts.detect_new_cards(cards.keys(), state_path)
    stats["new_cards"] = len(new_ids)
    if first_run:
        print(f"[card-alerts] first run: recorded {len(cards)} cards, no new-card emails")
    new_list = [(cid, str((cards.get(cid) or {}).get("name") or "")) for cid in new_ids[:NEW_CARDS_LIST_MAX]]
    threshold = card_alerts.price_threshold_pct()
    site = _site_url()

    from email_util import EmailSendError, send_email  # noqa: WPS433

    conn = sqlite3.connect(auth_db)
    conn.row_factory = sqlite3.Row
    try:
        card_alerts.ensure_tables(conn)
        users = conn.execute(
            """
            SELECT p.user_id, p.new_cards, p.price_watch, p.lang, p.unsubscribe_token,
                   u.email, u.username, u.email_verified
            FROM card_alert_prefs p JOIN users u ON u.id = p.user_id
            WHERE (p.new_cards = 1 OR p.price_watch = 1) AND u.email_verified = 1
            """
        ).fetchall()
        for user in users:
            uid = int(user["user_id"])
            changes: list[dict] = []
            baselines: list[tuple[str, int]] = []
            if user["price_watch"]:
                rows = [dict(r) for r in conn.execute(
                    "SELECT card_id, last_notified_price FROM card_alert_watch WHERE user_id = ?", (uid,)
                )]
                changes, baselines = card_alerts.price_moves(rows, prices, threshold)
            wants_new = bool(user["new_cards"]) and bool(new_ids)
            if not dry_run:
                for cid, price in baselines:
                    conn.execute(
                        "UPDATE card_alert_watch SET last_notified_price = ? WHERE user_id = ? AND card_id = ?",
                        (price, uid, cid),
                    )
                conn.commit()
            stats["baselines"] += len(baselines)
            if not wants_new and not changes:
                continue
            stats["recipients"] += 1
            subject, text, html = card_alerts.build_email(
                lang=str(user["lang"] or "zh-Hant"),
                username=str(user["username"] or ""),
                site_url=site,
                token=str(user["unsubscribe_token"]),
                new_cards=new_list if wants_new else [],
                new_total=len(new_ids) if wants_new else 0,
                changes=changes,
            )
            if dry_run:
                print(f"[card-alerts] dry-run user={uid}: {subject}")
                continue
            try:
                send_email(str(user["email"]), subject, text, html=html, log_prefix="card-alerts")
            except EmailSendError as exc:
                stats["failed"] += 1
                print(f"[card-alerts] send failed user={uid}: {exc}")
                continue
            stats["sent"] += 1
            for ch in changes:
                conn.execute(
                    "UPDATE card_alert_watch SET last_notified_price = ? WHERE user_id = ? AND card_id = ?",
                    (ch["new"], uid, ch["card_id"]),
                )
            conn.commit()
    finally:
        conn.close()
    if not dry_run:
        card_alerts.save_known_cards(cards.keys(), state_path)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not card_alerts.feature_enabled():
        print(f"[card-alerts] {card_alerts.FEATURE_ENV} is off; nothing sent")
        return 0
    stats = run(dry_run=args.dry_run)
    print("[card-alerts] " + " ".join(f"{k}={v}" for k, v in stats.items()))
    return 1 if stats["failed"] and not stats["sent"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
