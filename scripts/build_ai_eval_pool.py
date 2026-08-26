#!/usr/bin/env python3
"""Build a fixed AI eval pool: top N tournament decks, one per leader."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOPDECKS_PATH = ROOT / "meta" / "topdecks_decks.json"
OUT_PATH = ROOT / "meta" / "ai_eval_pool.json"

# Lower is better.
_PLACE_RANK: dict[str, int] = {
    "1st Place": 0,
    "1st (6-0)": 0,
    "1st (5-0)": 0,
    "1st (4-0)": 0,
    "1st (3-0)": 0,
    "2nd Place": 2,
    "3rd Place": 3,
    "4th Place": 4,
    "Top-4": 5,
    "T4": 5,
    "Top-8": 8,
    "T8": 8,
    "Top-16": 16,
    "T16": 16,
    "Top-32": 32,
    "T32": 32,
}


def _parse_date(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _place_rank(placement: Any) -> int:
    key = str(placement or "").strip()
    if key in _PLACE_RANK:
        return _PLACE_RANK[key]
    m = re.search(r"(\d+)", key)
    if m:
        return int(m.group(1))
    return 999


def _deck_fingerprint(cards: dict[str, int], leader: str) -> str:
    parts = [f"{leader}:L"]
    for cid in sorted(cards):
        parts.append(f"{cid}:{cards[cid]}")
    return "|".join(parts)


def _normalize_cards(raw: Any, leader: str) -> dict[str, int]:
    out: dict[str, int] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        cid = str(k or "").strip()
        if not cid or cid == leader:
            continue
        try:
            n = int(v or 0)
        except (TypeError, ValueError):
            continue
        if n > 0:
            out[cid] = n
    return out


def _meta_priority(slug: str) -> int:
    s = (slug or "").lower()
    if "op17" in s:
        return 0
    if "op16" in s:
        return 1
    return 5


def build_pool(*, top: int, recent_days: int, prefer_meta: str | None) -> dict[str, Any]:
    data = json.loads(TOPDECKS_PATH.read_text(encoding="utf-8"))
    decks = data.get("decks") if isinstance(data, dict) else data
    if not isinstance(decks, list):
        raise SystemExit("topdecks_decks.json: missing decks list")

    dated: list[tuple[datetime, dict[str, Any]]] = []
    for row in decks:
        if not isinstance(row, dict):
            continue
        dt = _parse_date(row.get("date"))
        if dt:
            dated.append((dt, row))
    if not dated:
        raise SystemExit("no dated decks found")
    dated.sort(key=lambda x: x[0], reverse=True)
    newest = dated[0][0]
    cutoff = newest.toordinal() - max(0, recent_days)

    candidates: list[dict[str, Any]] = []
    for dt, row in dated:
        if dt.toordinal() < cutoff:
            continue
        slug = str(row.get("meta_slug") or "")
        if prefer_meta and prefer_meta.lower() not in slug.lower():
            continue
        leader = str(row.get("leader") or "").strip()
        cards = _normalize_cards(row.get("cards"), leader)
        n = sum(cards.values())
        if not leader or n < 45 or n > 55:
            continue
        candidates.append(
            {
                "id": str(row.get("id") or ""),
                "name": str(row.get("name") or leader),
                "leader_card_id": leader,
                "cards": cards,
                "non_leader_count": n,
                "placement": str(row.get("placement") or ""),
                "date": str(row.get("date") or ""),
                "meta_slug": slug,
                "format": str(row.get("format") or ""),
                "source_url": str(row.get("source_url") or row.get("meta_url") or ""),
                "_dt": dt,
                "_place": _place_rank(row.get("placement")),
                "_meta_pri": _meta_priority(slug),
                "_fp": _deck_fingerprint(cards, leader),
            }
        )

    candidates.sort(
        key=lambda d: (d["_meta_pri"], d["_place"], -d["_dt"].toordinal(), d["leader_card_id"])
    )

    picked: list[dict[str, Any]] = []
    seen_leaders: set[str] = set()
    seen_fp: set[str] = set()
    for row in candidates:
        leader = row["leader_card_id"]
        fp = row["_fp"]
        if leader in seen_leaders or fp in seen_fp:
            continue
        seen_leaders.add(leader)
        seen_fp.add(fp)
        clean = {k: v for k, v in row.items() if not k.startswith("_")}
        picked.append(clean)
        if len(picked) >= top:
            break

    return {
        "source": "meta/topdecks_decks.json",
        "rule": f"top {top} by OP17>OP16 meta, placement, date; dedupe leader + deck fingerprint",
        "newest_deck_date": newest.strftime("%Y-%m-%d"),
        "recent_days": recent_days,
        "prefer_meta": prefer_meta,
        "count": len(picked),
        "decks": picked,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--recent-days", type=int, default=60)
    ap.add_argument(
        "--prefer-meta",
        default="",
        help="Optional substring filter on meta_slug (e.g. op17)",
    )
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()
    prefer = args.prefer_meta.strip() or None
    pool = build_pool(top=args.top, recent_days=args.recent_days, prefer_meta=prefer)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(pool, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({pool['count']} decks)")
    for i, d in enumerate(pool["decks"], 1):
        print(
            f"  {i:2d}. {d['leader_card_id']:12s}  {d['placement']:12s}  "
            f"{d['date']:10s}  {d['name'][:40]}"
        )


if __name__ == "__main__":
    main()
