"""Batch-F effect encoding / runtime fixes (Aug 2026)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, hand_cost_abilities, reload_effect_library  # noqa: E402
from battle.engine import (  # noqa: E402
    _continuous_base_power,
    effective_play_cost,
    inst_power,
    validate_battle_deck,
)
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def test_op13_096_search_main():
    reload_effect_library(force=True)
    entry = get_card_entry("OP13-096")
    main = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert main["ops"][0]["op"] == "search_deck"
    assert main["ops"][0].get("trash_rest") is True
    trig = next(a for a in entry["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0]["op"] == "activate_timing"
    assert trig["ops"][0].get("timing") == "on_play"


def test_op11_097_trash_gate_only_on_add():
    reload_effect_library(force=True)
    ab = get_card_entry("OP11-097")["abilities"][0]
    assert ab.get("require_trash_gte") is None
    assert ab["ops"][0]["op"] == "buff"
    assert ab["ops"][1].get("require_trash_gte") == 10


def test_op05_097_stage_hand_cost_aura():
    reload_effect_library(force=True)
    abs_ = hand_cost_abilities("OP05-097")
    assert abs_ and abs_[0]["timing"] == "hand_cost"
    op = abs_[0]["ops"][0]
    assert op.get("cost_gte") == 2
    assert "Celestial" in (op.get("trait_contains") or "") or "天龍" in (op.get("trait_contains") or "")

    def cat(cid: str) -> dict:
        table = {
            "OP05-097": {"name": "MG", "card_type": "STAGE", "cost": 1},
            "OP13-079": {"name": "Imu", "card_type": "LEADER", "power": 5000, "colors_en": ["Black"]},
            "CD": {
                "name": "Noble",
                "card_type": "CHARACTER",
                "cost": 3,
                "power": 4000,
                "colors_en": ["Black"],
                "traits_en": ["Celestial Dragons"],
            },
            "OTH": {
                "name": "Other",
                "card_type": "CHARACTER",
                "cost": 3,
                "power": 4000,
                "colors_en": ["Black"],
                "traits_en": ["Navy"],
            },
        }
        return dict(table.get(cid) or {"name": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000})

    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP13-079",
        deck=["A"] * 20,
        hand=["CD"],
        life=["L"] * 4,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP13-079",
        deck=["B"] * 20,
        hand=[],
        life=["R"] * 5,
    )
    st = MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )
    st.players[0].stages.append(CardInst(iid="mg", card_id="OP05-097"))
    assert effective_play_cost(st, 0, "CD", cat) == 2
    assert effective_play_cost(st, 0, "OTH", cat) == 3


def test_op13_084_board_base_power_aura():
    reload_effect_library(force=True)

    def cat(cid: str) -> dict:
        table = {
            "OP13-084": {
                "name": "Peter",
                "power": "6000",
                "card_type": "CHARACTER",
                "traits_en": ["Five Elders"],
            },
            "ELDER": {
                "name": "Elder",
                "power": "5000",
                "card_type": "CHARACTER",
                "traits_en": ["Five Elders"],
            },
            "NAVY": {"name": "Navy", "power": "5000", "card_type": "CHARACTER", "traits_en": ["Navy"]},
            "L": {"name": "L", "card_type": "LEADER", "power": 5000},
        }
        return dict(table.get(cid) or {"name": cid, "power": "1000", "card_type": "CHARACTER"})

    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="L",
        deck=["A"] * 20,
        hand=[],
        life=["L"] * 4,
        trash=["T"] * 10,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="L",
        deck=["B"] * 20,
        hand=[],
        life=["R"] * 5,
    )
    st = MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )
    st.players[0].characters.append(CardInst(iid="peter", card_id="OP13-084"))
    elder = CardInst(iid="e1", card_id="ELDER")
    navy = CardInst(iid="n1", card_id="NAVY")
    st.players[0].characters.extend([elder, navy])
    assert _continuous_base_power(st, 0, elder, cat) == 7000
    assert inst_power(st, 0, "e1", cat) == 7000
    assert _continuous_base_power(st, 0, navy, cat) is None


def test_op13_086_trash_hand_after_search():
    reload_effect_library(force=True)
    ops = get_card_entry("OP13-086")["abilities"][0]["ops"]
    assert ops[0]["op"] == "search_deck"
    assert "夏露莉雅" in (ops[0].get("exclude_name") or "")
    assert ops[1]["op"] == "trash_hand"


def test_op13_079_deck_bans_events_cost_gte_2():
    reload_effect_library(force=True)
    entry = get_card_entry("OP13-079")
    assert int(entry.get("deck_ban_event_cost_gte") or 0) == 2

    def cat(cid: str) -> dict:
        if cid == "OP13-079":
            return {"name": "Imu", "card_type": "LEADER", "colors_en": ["Black"], "life": 4, "power": 5000}
        if cid.startswith("E"):
            cost = 3 if cid == "E3" else 1
            return {"name": cid, "card_type": "EVENT", "cost": cost, "colors_en": ["Black"]}
        return {"name": cid, "card_type": "CHARACTER", "cost": 1, "colors_en": ["Black"], "power": 1000}

    deck = {f"X{i}": 1 for i in range(49)}
    deck["E3"] = 1
    assert "forbids Events" in (validate_battle_deck("OP13-079", deck, cat) or "")
    deck2 = {f"X{i}": 1 for i in range(49)}
    deck2["E1"] = 1
    assert validate_battle_deck("OP13-079", deck2, cat) is None
