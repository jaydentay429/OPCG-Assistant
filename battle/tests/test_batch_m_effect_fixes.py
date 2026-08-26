"""Batch-M effect encoding / runtime (Life dest, On K.O. opp-turn, set_base_power choice)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import (  # noqa: E402
    _ability_board_conditions_ok,
    _clear_turn_duration_effects,
    inst_effects_negated,
    inst_power,
)
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP16-080"),
        deck=list(kwargs.get("deck0", ["A"] * 20)),
        hand=list(kwargs.get("hand0", [])),
        life=["L"] * 4,
        trash=list(kwargs.get("trash0", [])),
        don_active=int(kwargs.get("don_active0", 0) or 0),
        don_rested=int(kwargs.get("don_rested0", 0) or 0),
        don_given=int(kwargs.get("don_given0", 0) or 0),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["B"] * 20,
        hand=[],
        life=["R1", "R2", "R3", "R4", "R5"],
        trash=[],
    )
    return MatchState(
        room_code="M",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def _cat(extra: dict | None = None):
    base = {
        "OP16-080": {
            "name": "馬歇爾・D・汀奇",
            "name_en": "Marshall.D.Teach",
            "card_type": "LEADER",
            "power": "5000",
            "traits_en": ["Blackbeard Pirates"],
            "traits": ["黑鬍子海賊團"],
        },
        "OP01-001": {"name": "F", "card_type": "LEADER", "power": "5000"},
        "LOW": {"name": "Low", "card_type": "CHARACTER", "power": "2000", "cost": "2"},
        "HIGH": {"name": "High", "card_type": "CHARACTER", "power": "5000", "cost": "4"},
        "BB6": {
            "name": "Shiryu",
            "name_en": "Shiryu",
            "card_type": "CHARACTER",
            "power": "7000",
            "cost": "6",
            "traits": ["黑鬍子海賊團"],
            "traits_en": ["Blackbeard Pirates"],
        },
        "OP16-103": {
            "name": "范・歐葛",
            "card_type": "CHARACTER",
            "power": "2000",
            "cost": "1",
            "traits": ["黑鬍子海賊團"],
            "traits_en": ["Blackbeard Pirates"],
        },
        "KEEP": {"name": "Keep", "card_type": "CHARACTER", "power": "4000", "cost": "3"},
        "A": {"name": "A", "card_type": "CHARACTER", "power": "1000", "cost": "1"},
        "B": {"name": "B", "card_type": "EVENT", "cost": "1"},
        "L": {"name": "Life", "card_type": "CHARACTER", "cost": "1"},
        "R1": {"name": "R1", "card_type": "CHARACTER", "cost": "1"},
        "R2": {"name": "R2", "card_type": "CHARACTER", "cost": "1"},
        "R3": {"name": "R3", "card_type": "CHARACTER", "cost": "1"},
        "R4": {"name": "R4", "card_type": "CHARACTER", "cost": "1"},
        "R5": {"name": "R5", "card_type": "CHARACTER", "cost": "1"},
    }
    if extra:
        base.update(extra)
    return lambda cid: base.get(cid) or {"name": cid, "card_type": "CHARACTER", "power": "1000", "cost": "1"}


def test_encodings():
    reload_effect_library(force=True)
    st = next(a for a in get_card_entry("OP09-099")["abilities"] if a["timing"] == "activate_main")
    assert st.get("rest_self") is True
    assert any(o.get("op") == "trash_hand" and o.get("as_cost") for o in st["ops"])
    search = next(o for o in st["ops"] if o.get("op") == "search_deck")
    assert int(search.get("top_n") or 0) == 3

    play = next(a for a in get_card_entry("OP16-108")["abilities"] if a["timing"] == "on_play")
    add = next(o for o in play["ops"] if o.get("op") == "add_from_trash")
    assert add.get("destination") == "life"
    assert add.get("face") == "up"
    assert int(add.get("cost_lte") or 0) == 6

    look = next(a for a in get_card_entry("OP16-119")["abilities"] if a["timing"] == "on_play")
    sd = look["ops"][0]
    assert sd.get("op") == "search_deck"
    assert int(sd.get("top_n") or 0) == 3
    assert sd.get("destination") == "life"
    trig = next(a for a in get_card_entry("OP16-119")["abilities"] if a["timing"] == "trigger")
    neg = next(o for o in trig["ops"] if o.get("op") == "negate_effects")
    assert neg.get("target_kind") == "opponent_character"

    ko = next(a for a in get_card_entry("OP16-103")["abilities"] if a["timing"] == "on_ko")
    assert ko.get("require_opponent_turn") is True

    wolf = next(a for a in get_card_entry("OP16-106")["abilities"] if a["timing"] == "on_ko")
    sbp = next(o for o in wolf["ops"] if o.get("op") == "set_base_power")
    assert sbp.get("target_kind") == "own_leader_or_character"
    assert int(sbp.get("amount") or 0) == 7000

    teach = next(a for a in get_card_entry("OP09-093")["abilities"] if a["timing"] == "activate_main")
    ops = teach["ops"]
    assert ops[0].get("target_kind") == "leader"
    assert ops[1].get("duration") == "until_opp_turn_end"
    assert ops[2].get("same_target_as_prior") is True

    ev = next(a for a in get_card_entry("OP16-116")["abilities"] if a["timing"] == "on_play")
    life = next(o for o in ev["ops"] if o.get("op") == "life_to_hand")
    assert life.get("hand_owner") == "life_owner"

    bors = next(a for a in get_card_entry("EB04-058")["abilities"] if a["timing"] == "on_play")
    assert bors["ops"][0].get("position") == "top"
    zoro = next(a for a in get_card_entry("OP15-113")["abilities"] if a["timing"] == "on_play")
    assert any(o.get("op") == "add_life" and o.get("position") == "top" for o in zoro["ops"])


def test_ko_all_honors_power_lte():
    st = _state(turn_seat=0)
    st.players[1].characters = [
        CardInst(iid="low", card_id="LOW", power_mod=-2000),
        CardInst(iid="high", card_id="HIGH", power_mod=-2000),
    ]
    apply_ops(
        st,
        0,
        [{"op": "ko", "all": True, "target_kind": "opponent_character", "power_lte": 0, "optional": False}],
        _cat(),
    )
    ids = {c.card_id for c in st.players[1].characters}
    assert "HIGH" in ids
    assert "LOW" not in ids


def test_set_base_power_offers_leader_or_character():
    st = _state()
    st.players[0].characters = [CardInst(iid="keep", card_id="KEEP")]
    apply_ops(
        st,
        0,
        [{"op": "set_base_power", "amount": 7000, "target_kind": "own_leader_or_character", "optional": True}],
        _cat(),
    )
    pending = st.pending_choice
    assert pending is not None
    assert "leader" in pending.options
    assert "keep" in pending.options


def test_add_from_trash_to_life_face_up():
    st = _state(trash0=["BB6"])
    apply_ops(
        st,
        0,
        [
            {
                "op": "add_from_trash",
                "count": 1,
                "optional": False,
                "trait_contains": "Blackbeard Pirates",
                "cost_lte": 6,
                "destination": "life",
                "face": "up",
                "position": "top",
            }
        ],
        _cat(),
    )
    assert st.players[0].life[0] == "BB6"
    assert "BB6" not in st.players[0].trash
    assert st.players[0].life_face[0] is True


def test_search_deck_destination_life():
    st = _state(deck0=["A", "B", "KEEP", "L"] + ["X"] * 10)
    apply_ops(
        st,
        0,
        [{"op": "search_deck", "top_n": 3, "max_add": 1, "destination": "life", "order_bottom": True}],
        _cat(),
    )
    pending = st.pending_search
    assert pending is not None
    assert pending.destination == "life"
    assert pending.revealed == ["A", "B", "KEEP"]


def test_life_to_hand_goes_to_life_owner():
    st = _state()
    apply_ops(
        st,
        0,
        [
            {
                "op": "life_to_hand",
                "count": 1,
                "position": "top",
                "optional": False,
                "owner": "opponent",
                "hand_owner": "life_owner",
            }
        ],
        _cat(),
    )
    assert "R1" in st.players[1].hand
    assert "R1" not in st.players[0].hand
    assert st.players[1].life[0] == "R2"


def test_negate_until_opp_end_survives_controller_end():
    st = _state(turn_seat=0)
    st.players[1].characters = [CardInst(iid="high", card_id="HIGH")]
    apply_ops(
        st,
        0,
        [
            {
                "op": "negate_effects",
                "target_kind": "opponent_character",
                "target_iid": "high",
                "optional": False,
                "duration": "until_opp_turn_end",
            }
        ],
        _cat(),
    )
    assert inst_effects_negated(st.players[1], "high") is True
    _clear_turn_duration_effects(st)
    assert inst_effects_negated(st.players[1], "high") is True
    st.turn_seat = 1
    _clear_turn_duration_effects(st)
    assert inst_effects_negated(st.players[1], "high") is False


def test_on_ko_require_opponent_turn():
    reload_effect_library(force=True)
    st = _state(turn_seat=0, leader0="OP16-080")
    cat = _cat()
    ab = next(a for a in get_card_entry("OP16-103")["abilities"] if a["timing"] == "on_ko")
    assert _ability_board_conditions_ok(st, 0, ab, cat, source_iid="gone") is False
    st.turn_seat = 1
    assert _ability_board_conditions_ok(st, 0, ab, cat, source_iid="gone") is True


def test_activate_timing_skips_when_own_turn():
    reload_effect_library(force=True)
    st = _state(turn_seat=0)
    apply_ops(
        st,
        0,
        [{"op": "activate_timing", "timing": "on_ko", "card_id": "OP16-103", "source_iid": "x"}],
        _cat(),
    )
    assert st.pending_choice is None
    assert len(st.players[0].hand) == 0


def test_add_life_position_top():
    st = _state(deck0=["A", "B"] + ["X"] * 10)
    before = list(st.players[0].life)
    apply_ops(st, 0, [{"op": "add_life", "count": 1, "optional": False, "position": "top"}], _cat())
    assert st.players[0].life[0] == "A"
    assert st.players[0].life[1:] == before


def test_wyper_mass_ko_after_minus():
    st = _state(turn_seat=0)
    st.players[1].characters = [
        CardInst(iid="low", card_id="LOW"),
        CardInst(iid="high", card_id="HIGH"),
    ]
    apply_ops(
        st,
        0,
        [
            {
                "op": "buff",
                "amount": -2000,
                "target_kind": "opponent_character",
                "all": True,
                "optional": False,
                "duration": "turn",
            },
            {"op": "ko", "target_kind": "opponent_character", "all": True, "optional": False, "power_lte": 0},
        ],
        _cat(),
    )
    assert inst_power(st, 1, "high", _cat()) == 3000
    ids = {c.card_id for c in st.players[1].characters}
    assert ids == {"HIGH"}


def test_op15_114_ko_opponent_zero_not_own():
    """Wyper: −2000 then KO power≤0 must not KO the controller's own Characters."""
    reload_effect_library(force=True)
    st = _state(turn_seat=0)
    st.players[0].life = ["L"] * 5
    st.players[0].life_face = [False] * 5
    st.players[0].characters = [CardInst(iid="own0", card_id="ZERO")]
    st.players[1].characters = [
        CardInst(iid="opp0", card_id="LOW"),
        CardInst(iid="opp1", card_id="HIGH"),
    ]
    cat = _cat({"ZERO": {"name": "Zero", "card_type": "CHARACTER", "power": "0", "cost": "1"}})
    ab = next(a for a in get_card_entry("OP15-114")["abilities"] if a.get("timing") == "on_play")
    ops = [dict(o) for o in ab["ops"] if o.get("op") != "flip_life"]
    apply_ops(st, 0, ops, cat)
    assert any(c.iid == "own0" for c in st.players[0].characters)
    assert "ZERO" not in st.players[0].trash
    assert {c.card_id for c in st.players[1].characters} == {"HIGH"}
    assert "LOW" in st.players[1].trash
