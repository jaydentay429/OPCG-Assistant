"""Batch-K effect encoding / runtime fixes (Rush OR, reveal-hand cost, hand Counter)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import apply_action, effective_counter, inst_power, live_leader_keywords  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP16-001"),
        deck=list(kwargs.get("deck0", ["A"] * 20)),
        hand=list(kwargs.get("hand0", [])),
        life=["L"] * 4,
        trash=[],
        don_active=int(kwargs.get("don_active0", 0) or 0),
        don_rested=int(kwargs.get("don_rested0", 0) or 0),
        don_given=int(kwargs.get("don_given0", 0) or 0),
        leader_don=int(kwargs.get("leader_don0", 0) or 0),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["B"] * 20,
        hand=[],
        life=["R"] * 5,
        trash=[],
    )
    return MatchState(
        room_code="K",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def _cat(extra: dict | None = None):
    base = {
        "OP16-001": {
            "name": "波特卡斯・D・艾斯",
            "name_en": "Portgas.D.Ace",
            "card_type": "LEADER",
            "power": "5000",
            "traits_en": ["Whitebeard Pirates"],
            "traits": ["白鬍子海賊團"],
        },
        "OP01-001": {"name": "F", "card_type": "LEADER", "power": "5000"},
        "WB8": {
            "name": "Vista",
            "name_en": "Vista",
            "card_type": "CHARACTER",
            "power": "8000",
            "cost": "6",
            "traits_en": ["Whitebeard Pirates"],
            "traits": ["白鬍子海賊團"],
        },
        "WB5": {
            "name": "Curiel",
            "card_type": "CHARACTER",
            "power": "5000",
            "cost": "4",
            "traits_en": ["Whitebeard Pirates"],
            "traits": ["白鬍子海賊團"],
        },
        "LF6": {
            "name": "蒙其・D・魯夫",
            "name_en": "Monkey.D.Luffy",
            "card_type": "CHARACTER",
            "power": "6000",
            "cost": "4",
            "traits_en": ["Straw Hat Crew"],
            "traits": ["草帽一行人"],
        },
        "LF8": {
            "name": "蒙其・D・魯夫",
            "name_en": "Monkey.D.Luffy",
            "card_type": "CHARACTER",
            "power": "8000",
            "cost": "7",
            "traits_en": ["Straw Hat Crew"],
            "traits": ["草帽一行人"],
        },
        "H8": {
            "name": "Thatch",
            "card_type": "CHARACTER",
            "power": "8000",
            "cost": "8",
            "counter": "1000",
            "traits_en": ["Whitebeard Pirates"],
        },
        "ACE6": {
            "name": "波特卡斯・D・艾斯",
            "name_en": "Portgas.D.Ace",
            "card_type": "CHARACTER",
            "power": "6000",
            "cost": "5",
            "counter": "1000",
            "traits_en": ["Whitebeard Pirates"],
            "traits": ["白鬍子海賊團"],
        },
        "OARS": {
            "name": "小歐斯Jr.",
            "name_en": "LittleOars Jr.",
            "card_type": "CHARACTER",
            "power": "8000",
            "cost": "4",
            "traits_en": ["Whitebeard Pirates Allies"],
            "traits": ["白鬍子海賊團旗下"],
        },
        "NG": {
            "name": "艾德華・紐蓋特",
            "name_en": "Edward.Newgate",
            "card_type": "CHARACTER",
            "power": "10000",
            "cost": "8",
            "traits_en": ["Whitebeard Pirates"],
            "traits": ["白鬍子海賊團"],
        },
        "EV": {"name": "Event", "card_type": "EVENT", "cost": "1", "counter": "0"},
        "STG": {"name": "白鯨號", "card_type": "STAGE", "cost": "1", "traits_en": ["Whitebeard Pirates"]},
    }
    if extra:
        base.update(extra)
    return base.get


def test_op16_001_rush_or_whitebeard_or_luffy():
    reload_effect_library(force=True)
    spec = get_card_entry("OP16-001")["abilities"][0]
    op = spec["ops"][0]
    assert op.get("name_or_trait") is True
    assert "魯夫" in str(op.get("name_contains") or "")
    assert op.get("power_gte") == 8000

    st = _state()
    st.players[0].characters.extend(
        [
            CardInst(iid="wb8", card_id="WB8"),
            CardInst(iid="wb5", card_id="WB5"),
            CardInst(iid="lf6", card_id="LF6"),
            CardInst(iid="lf8", card_id="LF8"),
        ]
    )
    apply_ops(st, 0, [dict(op)], _cat())
    assert st.pending_choice is not None
    opts = set(st.pending_choice.options)
    assert "wb8" in opts
    assert "lf8" in opts
    assert "lf6" not in opts
    assert "wb5" not in opts


def test_op13_007_skip_attach_cancels_debuff():
    reload_effect_library(force=True)
    ops = get_card_entry("OP13-007")["abilities"][0]["ops"]
    assert ops[0].get("as_cost") is True
    assert ops[1].get("as_cost") is True

    st = _state(don_active0=2, don_given0=2)
    st.players[0].characters.append(CardInst(iid="src", card_id="OP13-007"))
    st.players[1].characters.append(CardInst(iid="opp", card_id="WB8"))
    cat = _cat({"OP13-007": {"name": "Ace", "card_type": "CHARACTER", "power": "1000", "cost": "1"}})
    apply_ops(st, 0, [{**dict(o), "source_iid": "src"} for o in ops], cat)
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, cat)["ok"]
    assert inst_power(st, 1, "opp", cat) == 8000
    assert any(c.iid == "src" for c in st.players[0].characters)


def test_reveal_hand_skip_cancels_followup():
    reload_effect_library(force=True)
    ops = next(a["ops"] for a in get_card_entry("OP16-003")["abilities"] if a["timing"] == "on_play")
    assert ops[0].get("op") == "reveal_hand"
    assert ops[0].get("power_eq") == 8000

    st = _state(hand0=["H8", "H8b"])
    st.players[1].characters.append(CardInst(iid="opp", card_id="WB8"))
    cat = _cat({"H8b": {"name": "B", "card_type": "CHARACTER", "power": "8000"}})
    apply_ops(st, 0, [dict(o) for o in ops], cat)
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, cat)["ok"]
    assert inst_power(st, 1, "opp", cat) == 8000


def test_reveal_hand_too_few_aborts_cost():
    reload_effect_library(force=True)
    ops = next(a["ops"] for a in get_card_entry("OP16-003")["abilities"] if a["timing"] == "on_play")
    st = _state(hand0=["H8", "LF6"])
    st.players[1].characters.append(CardInst(iid="opp", card_id="WB8"))
    apply_ops(st, 0, [dict(o) for o in ops], _cat())
    assert st.pending_choice is None
    assert inst_power(st, 1, "opp", _cat()) == 8000


def test_op16_011_on_play_has_reveal_cost():
    reload_effect_library(force=True)
    play = next(a for a in get_card_entry("OP16-011")["abilities"] if a["timing"] == "on_play")
    assert play["ops"][0].get("op") == "reveal_hand"
    assert play["ops"][0].get("power_eq") == 8000
    assert play["ops"][1].get("op") == "draw"


def test_op16_014_trash_hand_filters():
    reload_effect_library(force=True)
    ko = next(a for a in get_card_entry("OP16-014")["abilities"] if a["timing"] == "on_ko")
    trash = ko["ops"][0]
    assert trash.get("power_eq") == 8000
    assert trash.get("card_type") == "character"


def test_op16_017_penalty_gated_on_own_cost8_whitebeard():
    reload_effect_library(force=True)
    abs_ = get_card_entry("OP16-017")["abilities"]
    assert {a.get("timing") for a in abs_} == {"your_turn", "opponent_turn"}
    assert all(a.get("require_no_own_char_cost_gte") == 8 for a in abs_)

    st = _state()
    oars_info = {
        "name": "小歐斯Jr.",
        "name_en": "LittleOars Jr.",
        "card_type": "CHARACTER",
        "power": "8000",
        "cost": "4",
        "traits_en": ["Whitebeard Pirates Allies"],
        "traits": ["白鬍子海賊團旗下"],
    }
    cat = _cat({"OP16-017": oars_info})
    st.players[0].characters.append(CardInst(iid="oars", card_id="OP16-017"))
    assert inst_power(st, 0, "oars", cat) == 4000

    st.players[0].characters.append(CardInst(iid="ng", card_id="NG"))
    assert inst_power(st, 0, "oars", cat) == 8000


def test_op16_021_unrestricted_search_and_trash_stage():
    reload_effect_library(force=True)
    play = next(a for a in get_card_entry("OP16-021")["abilities"] if a["timing"] == "on_play")
    search = play["ops"][0]
    assert not search.get("trait_contains")
    assert not search.get("name_contains")
    act = next(a for a in get_card_entry("OP16-021")["abilities"] if a["timing"] == "activate_main")
    assert act["ops"][0].get("op") == "trash"
    assert act["ops"][1].get("from_rested") is True

    st = _state(don_rested0=2, don_given0=2)
    from battle.state import CardInst as _C

    # Stage lives on stages list.
    st.players[0].stages.append(_C(iid="stg", card_id="STG"))
    cat = _cat()
    apply_ops(st, 0, [{**dict(o), "source_iid": "stg"} for o in act["ops"]], cat)
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "stg"}, cat)["ok"]
    assert not st.players[0].stages
    assert "STG" in st.players[0].trash
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "leader"}, cat)["ok"]
    assert st.players[0].leader_don == 1
    assert st.players[0].don_rested == 1


def test_op16_118_hand_counter_sets_8000_chars():
    reload_effect_library(force=True)
    hc = next(a for a in get_card_entry("OP16-118")["abilities"] if a["timing"] == "hand_cost")
    assert hc["ops"][0].get("op") == "hand_counter"
    search = next(a for a in get_card_entry("OP16-118")["abilities"] if a["timing"] == "on_play")
    assert "魯夫" in str(search["ops"][0].get("name_contains") or "")

    st = _state(hand0=["H8"])
    st.players[0].characters.append(CardInst(iid="ace", card_id="OP16-118"))
    cat = _cat({"OP16-118": _cat()("ACE6")})
    assert effective_counter(st, 0, "H8", cat) == 2000
    assert effective_counter(st, 0, "LF6", cat) == 0


def test_op16_003_leader_double_attack_aura():
    reload_effect_library(force=True)
    st = _state()
    st.players[0].characters.append(CardInst(iid="ng", card_id="OP16-003"))
    cat = _cat(
        {
            "OP16-003": {
                "name": "Edward.Newgate",
                "card_type": "CHARACTER",
                "power": "10000",
                "cost": "8",
                "traits_en": ["Whitebeard Pirates"],
            }
        }
    )
    keys = live_leader_keywords(st, 0, cat)
    assert "double_attack" in keys
    assert inst_power(st, 0, "leader", cat) == 7000
    st.turn_seat = 1
    keys = live_leader_keywords(st, 0, cat)
    assert "double_attack" not in keys


def test_st30_016_draw_gated_buff_always():
    reload_effect_library(force=True)
    ab = get_card_entry("ST30-016")["abilities"][0]
    assert ab.get("require_trash_names_all") is None
    draw = ab["ops"][1]
    assert draw.get("require_chars_base_power_eq") == 6000
    assert len(draw.get("require_own_name_all") or []) == 2

    st = _state(deck0=["A"] * 20)
    cat = _cat({"ST30-016": {"name": "Event", "card_type": "EVENT", "cost": "1"}})
    apply_ops(st, 0, [dict(o) for o in ab["ops"]], cat)
    # Buff offers a target; draw must not have happened yet without Ace+Luffy.
    if st.pending_choice:
        apply_action(st, 0, {"type": "select_choice", "target_iid": "leader"}, cat)
    assert len(st.players[0].hand) == 0

    st2 = _state(deck0=["Z"] * 20)
    st2.players[0].characters.extend(
        [CardInst(iid="ace", card_id="ACE6"), CardInst(iid="lf", card_id="LF6")]
    )
    apply_ops(st2, 0, [dict(o) for o in ab["ops"]], cat)
    if st2.pending_choice:
        apply_action(st2, 0, {"type": "select_choice", "target_iid": "leader"}, cat)
    assert "Z" in st2.players[0].hand


def test_st30_004_reveal_cost_before_draw():
    reload_effect_library(force=True)
    ops = get_card_entry("ST30-004")["abilities"][0]["ops"]
    assert ops[0].get("op") == "reveal_hand"
    assert ops[0].get("power_eq") == 6000
    assert ops[1].get("op") == "draw"
