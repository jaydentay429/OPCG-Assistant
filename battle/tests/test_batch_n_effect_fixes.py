"""Batch-N effect encoding / runtime (owner hand, play-this Trigger, hand_to_life filters)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops, detect_keywords  # noqa: E402
from battle.engine import _ability_board_conditions_ok, _resolve_trigger  # noqa: E402
from battle.state import CardInst, MatchState, PendingTrigger, PlayerState  # noqa: E402


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "ST29-001"),
        deck=list(kwargs.get("deck0", ["A"] * 20)),
        hand=list(kwargs.get("hand0", [])),
        life=["L"] * int(kwargs.get("life0", 4)),
        trash=list(kwargs.get("trash0", [])),
        don_active=int(kwargs.get("don_active0", 0) or 0),
        don_rested=int(kwargs.get("don_rested0", 2) or 0),
        don_given=int(kwargs.get("don_given0", 2) or 0),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["B"] * 20,
        hand=[],
        life=["R1", "R2", "R3", "R4", "R5"][: int(kwargs.get("life1", 5))],
        trash=[],
    )
    return MatchState(
        room_code="N",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def _cat(extra: dict | None = None):
    base = {
        "ST29-001": {
            "name": "蒙其・D・魯夫",
            "name_en": "Monkey.D.Luffy",
            "card_type": "LEADER",
            "power": "5000",
            "traits": ["蛋頭", "草帽一行人"],
            "traits_en": ["Egghead", "Straw Hat Crew"],
        },
        "ZH_LUFFY": {
            "name": "蒙其・D・魯夫",
            "card_type": "LEADER",
            "power": "5000",
        },
        "OP01-001": {"name": "F", "card_type": "LEADER", "power": "5000"},
        "ST29-005": {
            "name": "吉貝爾",
            "name_en": "Jinbe",
            "card_type": "CHARACTER",
            "power": "5000",
            "cost": "6",
            "effect": "【觸發器】若自己的領航卡是「蒙其・D・魯夫」時，使這張卡片登場。",
            "effect_en": "[Trigger] If your Leader is [Monkey.D.Luffy], play this card.",
        },
        "ST29-009": {
            "name": "妮可・羅賓",
            "name_en": "Nico Robin",
            "card_type": "CHARACTER",
            "power": "2000",
            "cost": "4",
            "effect": "【防禦】(對手攻擊後，將這張卡片置為休息狀態即可使攻擊的對象換成這張卡片)\n【觸發器】若自己的領航卡是「蒙其・D・魯夫」時，使這張卡片登場。",
        },
        "TRIG": {
            "name": "Trigger Char",
            "card_type": "CHARACTER",
            "power": "4000",
            "cost": "3",
            "effect": "【觸發器】抽1張卡片。",
            "effect_en": "[Trigger] Draw 1 card.",
        },
        "PLAIN": {"name": "Plain", "card_type": "CHARACTER", "power": "3000", "cost": "2"},
        "EVT": {"name": "Event", "card_type": "EVENT", "cost": "1"},
        "A": {"name": "A", "card_type": "CHARACTER", "power": "1000", "cost": "1"},
        "B": {"name": "B", "card_type": "EVENT", "cost": "1"},
        "L": {"name": "Life", "card_type": "CHARACTER", "cost": "1"},
        "R1": {"name": "R1", "card_type": "CHARACTER", "cost": "1"},
        "R2": {"name": "R2", "card_type": "CHARACTER", "cost": "1"},
        "R3": {"name": "R3", "card_type": "CHARACTER", "cost": "1"},
        "R4": {"name": "R4", "card_type": "CHARACTER", "cost": "1"},
        "R5": {"name": "R5", "card_type": "CHARACTER", "cost": "1"},
        "LOW": {"name": "Low", "card_type": "CHARACTER", "power": "2000", "cost": "4"},
        "HIGH": {"name": "High", "card_type": "CHARACTER", "power": "5000", "cost": "7"},
    }
    if extra:
        base.update(extra)
    return lambda cid: base.get(cid) or {"name": cid, "card_type": "CHARACTER", "power": "1000", "cost": "1"}


def test_encodings():
    reload_effect_library(force=True)
    nami = get_card_entry("EB03-053")["abilities"]
    life = next(o for a in nami if a["timing"] == "on_play" for o in a["ops"] if o.get("op") == "life_to_hand")
    assert life.get("hand_owner") == "life_owner"
    assert life.get("owner") == "opponent"

    robin = next(a for a in get_card_entry("EB03-055")["abilities"] if a["timing"] == "on_play")
    assert "require_leader_trait" not in robin
    add = next(o for o in robin["ops"] if o.get("op") == "add_life")
    assert add.get("position") == "top"
    assert int(add.get("count") or 0) == 2
    assert "草帽" in str(add.get("require_leader_trait") or "") or "Straw Hat" in str(add.get("require_leader_trait") or "")

    snake = next(a for a in get_card_entry("EB03-059")["abilities"] if a["timing"] == "on_play")
    htl = snake["ops"][0]
    assert htl.get("require_trigger") is True
    assert htl.get("card_type") == "character"
    assert htl.get("face") == "up"
    deny = next(a for a in get_card_entry("EB03-059")["abilities"] if a["timing"] == "trigger")["ops"][0]
    assert "蒙其" in str(deny.get("exclude_name") or "")

    twister = next(a for a in get_card_entry("EB04-059")["abilities"] if a["timing"] == "on_play")
    assert twister.get("require_chars_deficit_gte") == 1
    kos = [o for o in twister["ops"] if o.get("op") == "ko"]
    assert len(kos) == 2
    assert all(o.get("require_chars_deficit_gte") is None for o in kos)

    bonney_play = next(a for a in get_card_entry("OP13-108")["abilities"] if a["timing"] == "on_play")
    assert not any(o.get("op") == "rest_opponent_character" for o in bonney_play["ops"])
    assert any(o.get("op") == "grant_keyword" and o.get("keyword") == "rush" for o in bonney_play["ops"])
    lth = next(o for o in bonney_play["ops"] if o.get("op") == "life_to_hand")
    assert lth.get("hand_owner") == "life_owner"
    assert lth.get("optional") is False
    assert bonney_play.get("require_life_lte") is None
    trig = next(a for a in get_card_entry("OP13-108")["abilities"] if a["timing"] == "trigger")
    assert trig.get("require_life_lte") == 1
    assert trig["ops"][0].get("optional") is True

    jinbe = next(a for a in get_card_entry("ST29-005")["abilities"] if a["timing"] == "trigger")
    assert jinbe["ops"][0].get("self_card") is True
    assert "蒙其" in str(jinbe.get("require_leader_name") or "")

    robin_st = get_card_entry("ST29-009")
    assert not any(a.get("timing") == "on_opponent_attack" for a in robin_st["abilities"])
    play = next(a for a in robin_st["abilities"] if a["timing"] == "trigger")["ops"][0]
    assert play.get("self_card") is True
    assert play.get("name_contains") in (None, "")


def test_st29_009_innate_blocker():
    info = {
        "effect": "【防禦】(對手攻擊後，將這張卡片置為休息狀態即可使攻擊的對象換成這張卡片)\n【觸發器】若自己的領航卡是「蒙其・D・魯夫」時，使這張卡片登場。"
    }
    assert "blocker" in detect_keywords(info)


def test_life_to_hand_owner_not_controller():
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


def test_add_life_count_two_to_top():
    st = _state(deck0=["A", "B", "C"] + ["X"] * 10)
    before = list(st.players[0].life)
    apply_ops(st, 0, [{"op": "add_life", "count": 2, "optional": False, "position": "top"}], _cat())
    assert st.players[0].life[:2] == ["B", "A"]
    assert st.players[0].life[2:] == before


def test_hand_to_life_filters_trigger_characters():
    st = _state(hand0=["EVT", "PLAIN", "TRIG"])
    apply_ops(
        st,
        0,
        [
            {
                "op": "hand_to_life",
                "count": 1,
                "optional": True,
                "face": "up",
                "card_type": "character",
                "require_trigger": True,
            }
        ],
        _cat(),
    )
    pending = st.pending_choice
    assert pending is not None
    ids = [tok.split(":")[-1] for tok in pending.options]
    assert ids == ["TRIG"]
    assert pending.then_op.get("require_trigger") is True
    assert pending.then_op.get("face") == "up"


def test_deal_life_damage_optional_offers_skip():
    st = _state()
    apply_ops(st, 0, [{"op": "deal_life_damage", "count": 1, "optional": True}], _cat())
    assert st.pending_choice is not None
    assert st.pending_choice.optional is True
    assert st.players[1].life[0] == "R1"


def test_trigger_play_this_card_not_other_hand_character():
    st = _state(hand0=["PLAIN"], leader0="ST29-001")
    st.pending_trigger = PendingTrigger(
        seat=0,
        card_id="ST29-005",
        ops=[{"op": "play_from_hand", "card_type": "character", "from_zone": "hand", "self_card": True, "optional": False}],
        remaining_hits=0,
        summary="play this",
    )
    st.phase = "trigger"
    out = _resolve_trigger(st, 0, True, _cat())
    assert out.get("ok") is True
    ids = [c.card_id for c in st.players[0].characters]
    assert "ST29-005" in ids
    assert "PLAIN" in st.players[0].hand
    assert "ST29-005" not in st.players[0].trash


def test_zh_only_leader_name_gate():
    reload_effect_library(force=True)
    ab = next(a for a in get_card_entry("ST29-005")["abilities"] if a["timing"] == "trigger")
    st = _state(leader0="ZH_LUFFY")
    assert _ability_board_conditions_ok(st, 0, ab, _cat()) is True
    st.players[0].leader_card_id = "OP01-001"
    assert _ability_board_conditions_ok(st, 0, ab, _cat()) is False


def test_deficit_gates_ko_not_flip():
    st = _state()
    st.players[0].life_face = [False] * len(st.players[0].life)
    apply_ops(
        st,
        0,
        [
            {"op": "flip_life", "face": "up", "position": "top", "optional": False, "as_cost": True},
            {
                "op": "ko",
                "target_kind": "opponent_character",
                "optional": True,
                "cost_lte": 6,
                "require_chars_deficit_gte": 1,
            },
        ],
        _cat(),
    )
    assert st.players[0].life_face[0] is True
    st.players[1].characters = [CardInst(iid="low", card_id="LOW")]
    apply_ops(
        st,
        0,
        [
            {
                "op": "ko",
                "target_kind": "opponent_character",
                "optional": False,
                "cost_lte": 6,
                "require_chars_deficit_gte": 1,
            }
        ],
        _cat(),
    )
    assert st.players[1].characters == []
