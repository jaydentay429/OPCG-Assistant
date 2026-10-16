"""The green hawk AI deck must not ship the banned Mihawk leader."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from battle.ai_decks import load_ai_decks
from battle.engine import validate_battle_deck
from battle.set_legality import casual_deck_legality_error
from official_restriction import official_restriction_error

ROOT = Path(__file__).resolve().parents[2]
_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
_OPEN = date(2026, 12, 1)


def catalog(cid: str) -> dict:
    return _CARDS.get(cid) or {}


def test_green_hawk_uses_a_legal_green_leader():
    decks = load_ai_decks(force=True)
    hawk = next(deck for deck in decks if deck["name"] == "绿鹰眼")
    leader = hawk["leader_card_id"]
    assert leader == "OP12-020"
    assert leader != "OP14-020"
    info = catalog(leader)
    assert info.get("card_type") == "Leader"
    assert "綠" in (info.get("colors") or [])
    cards = hawk["cards"]
    assert sum(cards.values()) == 50
    assert official_restriction_error(leader, cards, on_date=_OPEN) is None
    assert validate_battle_deck(leader, cards, catalog) is None
    assert casual_deck_legality_error(leader, cards, on_date=_OPEN) is None
    for deck in decks:
        assert official_restriction_error(deck["leader_card_id"], deck["cards"], on_date=_OPEN) is None
        assert validate_battle_deck(deck["leader_card_id"], deck["cards"], catalog) is None
