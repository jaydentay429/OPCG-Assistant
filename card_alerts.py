"""Email alerts for logged-in users: new cards and watched-card price changes.

Opt-in only. Every email carries a one-click unsubscribe link. Nothing is sent
unless the server sets CARD_ALERTS_ENABLED=1 (see deploy/optcgassistant/README.txt);
the API reports the flag so the site hides the settings while it is off.

Tables live in the auth database (meta/auth.db):
  card_alert_prefs  user_id, new_cards, price_watch, lang, unsubscribe_token, timestamps
  card_alert_watch  user_id, card_id, last_notified_price
"""

from __future__ import annotations

import html
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

FEATURE_ENV = "CARD_ALERTS_ENABLED"
PRICE_PCT_ENV = "CARD_ALERTS_PRICE_PCT"
WATCH_MAX = 80
LANGS = {"zh-Hant", "zh-Hans", "en"}


def feature_enabled() -> bool:
    return str(os.getenv(FEATURE_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def price_threshold_pct() -> float:
    try:
        value = float(os.getenv(PRICE_PCT_ENV) or "10")
    except ValueError:
        value = 10.0
    return max(1.0, min(value, 90.0))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS card_alert_prefs (
            user_id INTEGER PRIMARY KEY,
            new_cards INTEGER NOT NULL DEFAULT 0,
            price_watch INTEGER NOT NULL DEFAULT 0,
            lang TEXT NOT NULL DEFAULT 'zh-Hant',
            unsubscribe_token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS card_alert_watch (
            user_id INTEGER NOT NULL,
            card_id TEXT NOT NULL,
            last_notified_price INTEGER,
            added_at TEXT NOT NULL,
            PRIMARY KEY (user_id, card_id)
        )
        """
    )


def _prefs_row(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM card_alert_prefs WHERE user_id = ?", (int(user_id),)).fetchone()


def get_settings(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    ensure_tables(conn)
    row = _prefs_row(conn, user_id)
    watch_count = conn.execute(
        "SELECT COUNT(*) FROM card_alert_watch WHERE user_id = ?", (int(user_id),)
    ).fetchone()[0]
    return {
        "new_cards": bool(row["new_cards"]) if row else False,
        "price_watch": bool(row["price_watch"]) if row else False,
        "lang": (row["lang"] if row else "zh-Hant"),
        "watch_count": int(watch_count or 0),
        "threshold_pct": price_threshold_pct(),
    }


def set_settings(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    new_cards: bool,
    price_watch: bool,
    lang: str | None = None,
) -> dict[str, Any]:
    ensure_tables(conn)
    now = _now()
    use_lang = lang if lang in LANGS else None
    row = _prefs_row(conn, user_id)
    if row is None:
        conn.execute(
            """
            INSERT INTO card_alert_prefs
                (user_id, new_cards, price_watch, lang, unsubscribe_token, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(user_id),
                int(bool(new_cards)),
                int(bool(price_watch)),
                use_lang or "zh-Hant",
                secrets.token_urlsafe(24),
                now,
                now,
            ),
        )
    else:
        conn.execute(
            """
            UPDATE card_alert_prefs
            SET new_cards = ?, price_watch = ?, lang = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (int(bool(new_cards)), int(bool(price_watch)), use_lang or row["lang"], now, int(user_id)),
        )
    conn.commit()
    return get_settings(conn, user_id)


def set_watchlist(conn: sqlite3.Connection, user_id: int, card_ids: Iterable[str]) -> int:
    """Replace the user's watched ids (max WATCH_MAX). Kept ids keep their baseline price."""
    ensure_tables(conn)
    wanted: list[str] = []
    for raw in card_ids:
        cid = str(raw or "").strip().upper()
        if cid and cid not in wanted:
            wanted.append(cid)
        if len(wanted) >= WATCH_MAX:
            break
    existing = {
        r["card_id"]
        for r in conn.execute("SELECT card_id FROM card_alert_watch WHERE user_id = ?", (int(user_id),))
    }
    remove = existing - set(wanted)
    now = _now()
    for cid in remove:
        conn.execute("DELETE FROM card_alert_watch WHERE user_id = ? AND card_id = ?", (int(user_id), cid))
    for cid in wanted:
        if cid not in existing:
            conn.execute(
                "INSERT INTO card_alert_watch (user_id, card_id, last_notified_price, added_at) VALUES (?, ?, NULL, ?)",
                (int(user_id), cid, now),
            )
    conn.commit()
    return len(wanted)


def unsubscribe(conn: sqlite3.Connection, token: str, kind: str = "all") -> dict[str, Any] | None:
    """One-click unsubscribe. `kind`: all | new_cards | price_watch. None for an unknown token."""
    ensure_tables(conn)
    tok = str(token or "").strip()
    if not tok:
        return None
    row = conn.execute("SELECT * FROM card_alert_prefs WHERE unsubscribe_token = ?", (tok,)).fetchone()
    if row is None:
        return None
    new_cards = bool(row["new_cards"])
    price_watch = bool(row["price_watch"])
    if kind in {"all", "new_cards"}:
        new_cards = False
    if kind in {"all", "price_watch"}:
        price_watch = False
    conn.execute(
        "UPDATE card_alert_prefs SET new_cards = ?, price_watch = ?, updated_at = ? WHERE user_id = ?",
        (int(new_cards), int(price_watch), _now(), int(row["user_id"])),
    )
    conn.commit()
    return {"new_cards": new_cards, "price_watch": price_watch}


# --- digest ---------------------------------------------------------------------------


def detect_new_cards(current_ids: Iterable[str], state_path: Path) -> tuple[list[str], bool]:
    """(ids not seen before, first_run). The first run only records the catalog."""
    ids = sorted({str(x) for x in current_ids if x})
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        known = set(state.get("known_ids") or [])
        first = not known
    except (OSError, json.JSONDecodeError):
        known, first = set(), True
    new_ids = [] if first else [cid for cid in ids if cid not in known]
    return new_ids, first


def save_known_cards(current_ids: Iterable[str], state_path: Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"known_ids": sorted({str(x) for x in current_ids if x}), "updated_at": _now()}),
        encoding="utf-8",
    )


def price_moves(
    watch_rows: Iterable[dict[str, Any]],
    prices: dict[str, Any],
    threshold_pct: float,
) -> tuple[list[dict[str, Any]], list[tuple[str, int]]]:
    """(changes to email, baselines to store silently).

    A row without a baseline gets the current price stored and no email. A change
    of at least `threshold_pct` from the last emailed price is reported.
    """
    changes: list[dict[str, Any]] = []
    baselines: list[tuple[str, int]] = []
    for row in watch_rows:
        cid = str(row.get("card_id") or "")
        info = prices.get(cid) if isinstance(prices.get(cid), dict) else None
        try:
            current = int((info or {}).get("current_price") or 0)
        except (TypeError, ValueError):
            current = 0
        if current <= 0:
            continue
        last = row.get("last_notified_price")
        if last in (None, "", 0):
            baselines.append((cid, current))
            continue
        last_i = int(last)
        if last_i <= 0:
            baselines.append((cid, current))
            continue
        pct = (current - last_i) * 100.0 / last_i
        if abs(pct) >= threshold_pct:
            changes.append({"card_id": cid, "old": last_i, "new": current, "pct": round(pct, 1)})
    return changes, baselines


_COPY = {
    "zh-Hant": {
        "subject_new": "OPCG 卡牌助手：{n} 張新卡",
        "subject_price": "OPCG 卡牌助手：{n} 張關注卡價格變動",
        "subject_both": "OPCG 卡牌助手：{a} 張新卡、{b} 張關注卡價格變動",
        "hi": "Hi {user}，",
        "new_head": "新收錄的卡：",
        "price_head": "關注清單價格變動（Yuyu-tei 參考價）：",
        "unsub": "不想再收到？一鍵取消訂閱：",
        "why": "你在 optcgassistant.com 開啟了郵件提醒，所以收到這封信。",
    },
    "zh-Hans": {
        "subject_new": "OPCG 卡牌助手：{n} 张新卡",
        "subject_price": "OPCG 卡牌助手：{n} 张关注卡价格变动",
        "subject_both": "OPCG 卡牌助手：{a} 张新卡、{b} 张关注卡价格变动",
        "hi": "Hi {user}，",
        "new_head": "新收录的卡：",
        "price_head": "关注清单价格变动（Yuyu-tei 参考价）：",
        "unsub": "不想再收到？一键取消订阅：",
        "why": "你在 optcgassistant.com 开启了邮件提醒，所以收到这封信。",
    },
    "en": {
        "subject_new": "OPCG Card Assistant: {n} new cards",
        "subject_price": "OPCG Card Assistant: price changes on {n} watched cards",
        "subject_both": "OPCG Card Assistant: {a} new cards, {b} price changes",
        "hi": "Hi {user},",
        "new_head": "New cards:",
        "price_head": "Watchlist price changes (Yuyu-tei reference):",
        "unsub": "Don't want these? Unsubscribe in one click:",
        "why": "You get this email because you turned on alerts at optcgassistant.com.",
    },
}

_LANG_PREFIX = {"zh-Hant": "", "zh-Hans": "/zh-hans", "en": "/en"}


def build_email(
    *,
    lang: str,
    username: str,
    site_url: str,
    token: str,
    new_cards: list[tuple[str, str]],
    changes: list[dict[str, Any]],
    new_total: int | None = None,
) -> tuple[str, str, str]:
    """(subject, text, html). `new_cards` is [(card_id, display name)], already capped."""
    use = lang if lang in _COPY else "zh-Hant"
    c = _COPY[use]
    base = site_url.rstrip("/")
    prefix = _LANG_PREFIX[use]
    total_new = new_total if new_total is not None else len(new_cards)
    if total_new and changes:
        subject = c["subject_both"].format(a=total_new, b=len(changes))
    elif total_new:
        subject = c["subject_new"].format(n=total_new)
    else:
        subject = c["subject_price"].format(n=len(changes))
    unsub_url = f"{base}/alerts/unsubscribe?token={token}"
    lines = [c["hi"].format(user=username), ""]
    parts_html = [f"<p>{html.escape(c['hi'].format(user=username))}</p>"]
    if new_cards:
        lines.append(c["new_head"])
        items = []
        for cid, name in new_cards:
            url = f"{base}{prefix}/cards/{cid}"
            lines.append(f"- {cid} {name} {url}")
            items.append(f'<li><a href="{html.escape(url)}">{html.escape(cid)} {html.escape(name)}</a></li>')
        if total_new > len(new_cards):
            more = f"(+{total_new - len(new_cards)}) {base}{prefix}/sets"
            lines.append(f"- … {more}")
            items.append(f"<li>… {html.escape(more)}</li>")
        lines.append("")
        parts_html.append(f"<p>{html.escape(c['new_head'])}</p><ul>{''.join(items)}</ul>")
    if changes:
        lines.append(c["price_head"])
        items = []
        for ch in changes:
            url = f"{base}{prefix}/cards/{ch['card_id']}"
            sign = "+" if ch["pct"] > 0 else ""
            text = f"{ch['card_id']}: ¥{ch['old']:,} → ¥{ch['new']:,} ({sign}{ch['pct']}%)"
            lines.append(f"- {text} {url}")
            items.append(f'<li><a href="{html.escape(url)}">{html.escape(text)}</a></li>')
        lines.append("")
        parts_html.append(f"<p>{html.escape(c['price_head'])}</p><ul>{''.join(items)}</ul>")
    lines += [c["why"], f"{c['unsub']} {unsub_url}"]
    parts_html.append(
        f'<p style="color:#64748b;font-size:12px">{html.escape(c["why"])}<br>'
        f'{html.escape(c["unsub"])} <a href="{html.escape(unsub_url)}">{html.escape(unsub_url)}</a></p>'
    )
    return subject, "\n".join(lines), "".join(parts_html)
