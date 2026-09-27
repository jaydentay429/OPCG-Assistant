"""Screenshot / hand-entered cards that are not on the official card list yet.

Rows live in ``index/manual_cards.json`` and are copied into ``index/cards_by_id.json``
under the same card id. ``sync_official_cards.py`` overwrites that id when the
official list publishes it, then this module refuses to put the screenshot row back.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
MANUAL_CARDS_PATH = BASE_DIR / "index" / "manual_cards.json"


def load_manual_cards(path: Path | None = None) -> dict[str, dict[str, Any]]:
    file_path = path or MANUAL_CARDS_PATH
    if not file_path.exists():
        return {}
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    rows = payload.get("cards") if isinstance(payload, dict) else None
    if not isinstance(rows, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for raw_id, row in rows.items():
        if isinstance(row, dict):
            out[str(raw_id)] = row
    return out


def row_is_official(card: Any) -> bool:
    """Official catalog row: real text, and not still marked preview or manual."""
    if not isinstance(card, dict):
        return False
    if card.get("preview") or card.get("manual_source"):
        return False
    return bool(str(card.get("name") or "").strip() or str(card.get("effect") or "").strip())


def apply_manual_cards(
    index: dict[str, Any],
    cards: dict[str, dict[str, Any]] | None = None,
) -> int:
    """Insert or refresh screenshot rows. One key per id. Official rows are left as-is."""
    incoming = cards if cards is not None else load_manual_cards()
    applied = 0
    for raw_id, row in incoming.items():
        card_id = str(raw_id).strip()
        if not card_id or not isinstance(row, dict):
            continue
        existing = index.get(card_id)
        if row_is_official(existing):
            continue
        merged = dict(row)
        merged["card_id"] = card_id
        merged["preview"] = True
        merged["manual_source"] = str(merged.get("manual_source") or "screenshot")
        index[card_id] = merged
        applied += 1
    return applied
