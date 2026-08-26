from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_AI_DECKS_PATH = Path(__file__).resolve().parent.parent / "meta" / "ai_decks.json"
_CACHE: list[dict[str, Any]] | None = None


def _normalize_cards(raw: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        try:
            n = int(v or 0)
        except (TypeError, ValueError):
            continue
        cid = str(k or "").strip()
        if cid and n > 0:
            out[cid] = n
    return out


def load_ai_decks(*, force: bool = False) -> list[dict[str, Any]]:
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    out: list[dict[str, Any]] = []
    try:
        data = json.loads(_AI_DECKS_PATH.read_text(encoding="utf-8"))
    except Exception:
        _CACHE = []
        return _CACHE
    rows = data.get("decks") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        _CACHE = []
        return _CACHE
    for row in rows:
        if not isinstance(row, dict):
            continue
        did = str(row.get("id") or "").strip()
        leader = str(row.get("leader_card_id") or "").strip()
        cards = _normalize_cards(row.get("cards"))
        if not did or not leader or not cards:
            continue
        out.append(
            {
                "id": did,
                "name": str(row.get("name") or did),
                "leader_card_id": leader,
                "cards": cards,
                "non_leader_count": sum(cards.values()),
            }
        )
    _CACHE = out
    return out


def get_ai_deck(deck_id: str) -> dict[str, Any] | None:
    needle = str(deck_id or "").strip()
    if not needle:
        return None
    for deck in load_ai_decks():
        if deck["id"] == needle:
            return deck
    return None
