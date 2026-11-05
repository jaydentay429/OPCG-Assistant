#!/usr/bin/env python3
"""Fill index/card_names_ja.json from the official Japanese cardlist.

The daily pipeline syncs Traditional Chinese and English names only.
Japanese names live in this sidecar so search can use them without rewriting
index/cards_by_id.json. DON!! cards already store name_jp; those are merged
in when the official list has no row.

    python sync_card_names_ja.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from atomic_io import atomic_write_text

BASE_DIR = Path(__file__).resolve().parent
INDEX_PATH = BASE_DIR / "index" / "cards_by_id.json"
OUT_PATH = BASE_DIR / "index" / "card_names_ja.json"
OFFICIAL_JA_URL = "https://www.onepiece-cardgame.com/cardlist/"


def _load_index_names() -> dict[str, str]:
    """name_ja / name_jp already on a card. Does not replace an official name."""
    if not INDEX_PATH.is_file():
        return {}
    try:
        payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[ja] skip index merge: {exc}", file=sys.stderr)
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, str] = {}
    for raw_id, row in payload.items():
        if not isinstance(row, dict):
            continue
        text = str(row.get("name_ja") or row.get("name_jp") or "").strip()
        cid = str(row.get("card_id") or raw_id or "").strip()
        if cid and text:
            out[cid] = text
    return out


def main() -> int:
    from sync_official_cards import fetch_cards_from_official_url

    parsed = fetch_cards_from_official_url(OFFICIAL_JA_URL)
    names: dict[str, str] = {}
    for cid, card in parsed.items():
        text = str(card.name or "").strip()
        if cid and text:
            names[cid] = text
    official = len(names)
    for cid, text in _load_index_names().items():
        names.setdefault(cid, text)
    ordered = {cid: names[cid] for cid in sorted(names)}
    atomic_write_text(OUT_PATH, json.dumps(ordered, ensure_ascii=False, indent=2) + "\n")
    print(
        f"[ja] official={official} with_index_fallback={len(ordered)} -> {OUT_PATH}",
        flush=True,
    )
    return 0 if ordered else 1


if __name__ == "__main__":
    raise SystemExit(main())
