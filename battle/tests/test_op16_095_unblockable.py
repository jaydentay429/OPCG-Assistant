"""OP16-095: grant Unblockable to chosen Wano Character — not a false innate on the played card."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_abilities, reload_effect_library  # noqa: E402
from battle.effects import apply_ops, detect_keywords, has_blockerless, live_keywords  # noqa: E402
from battle.engine import apply_action  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _catalog(cid: str) -> dict:
    table = {
        "OP16-095": {
            "card_id": "OP16-095",
            "card_type": "CHARACTER",
            "name": "Monkey.D.Luffy",
            "colors": ["黑"],
            "traits": ["和之國", "草帽一行人"],
            "traits_en": ["Land of Wano", "Straw Hat Crew"],
            "cost": 2,
            "power": 2000,
            "effect": "【登場時】最多1張自己黑色擁有《和之國》特徵的角色卡，在這個回合，獲得【防禦不可】。 (這張卡片不會遭到防禦)",
            "effect_en": "[On Play] Up to 1 of your black {Land of Wano} type Characters gains [Unblockable] during this turn. (This card cannot be blocked.)",
        },
        "WANO": {
            "card_id": "WANO",
            "card_type": "CHARACTER",
            "name": "Other Wano",
            "colors": ["黑"],
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
            "cost": 3,
            "power": 4000,
            "effect": "",
        },
        "L0": {"card_type": "LEADER", "name": "L", "power": 5000},
    }
    return dict(table.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000})


def test_op16_095_not_innate_blockerless():
    info = _catalog("OP16-095")
    assert "blockerless" not in detect_keywords(info)
    inst = CardInst(iid="luffy", card_id="OP16-095")
    assert "blockerless" not in live_keywords(info, inst)
    assert not has_blockerless(info, inst)


def test_op16_095_encoding_allows_self_target():
    reload_effect_library(force=True)
    ab = get_abilities("OP16-095", "on_play")[0]
    op = ab["ops"][0]
    assert op.get("op") == "grant_keyword"
    assert op.get("keyword") == "blockerless"
    assert not op.get("exclude_self")


def test_op16_095_grant_other_does_not_buff_self():
    reload_effect_library(force=True)
    p0 = PlayerState(seat=0, user_id="u0", username="p0", is_ai=False, leader_card_id="L0", hand=[], deck=["D"] * 10)
    p1 = PlayerState(seat=1, user_id="u1", username="p1", is_ai=False, leader_card_id="L0", hand=[], deck=["D"] * 10)
    st = MatchState(room_code="t", status="playing", phase="main", turn_seat=0, players=[p0, p1])
    luffy = CardInst(iid="luffy", card_id="OP16-095")
    other = CardInst(iid="other", card_id="WANO")
    p0.characters = [luffy, other]
    ops = list(get_abilities("OP16-095", "on_play")[0]["ops"])
    for o in ops:
        o["source_iid"] = "luffy"
        o["card_id"] = "OP16-095"
    apply_ops(st, 0, ops, _catalog)
    assert st.pending_choice is not None
    assert "luffy" in st.pending_choice.options  # self is legal
    assert "other" in st.pending_choice.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "other"}, _catalog)["ok"]
    assert "blockerless" in (other.turn_keywords or [])
    assert "blockerless" not in (luffy.turn_keywords or [])
    assert has_blockerless(_catalog("WANO"), other)
    assert not has_blockerless(_catalog("OP16-095"), luffy)


def test_op16_095_can_grant_self():
    reload_effect_library(force=True)
    p0 = PlayerState(seat=0, user_id="u0", username="p0", is_ai=False, leader_card_id="L0", hand=[], deck=["D"] * 10)
    p1 = PlayerState(seat=1, user_id="u1", username="p1", is_ai=False, leader_card_id="L0", hand=[], deck=["D"] * 10)
    st = MatchState(room_code="t", status="playing", phase="main", turn_seat=0, players=[p0, p1])
    luffy = CardInst(iid="luffy", card_id="OP16-095")
    other = CardInst(iid="other", card_id="WANO")
    p0.characters = [luffy, other]
    ops = list(get_abilities("OP16-095", "on_play")[0]["ops"])
    for o in ops:
        o["source_iid"] = "luffy"
        o["card_id"] = "OP16-095"
    apply_ops(st, 0, ops, _catalog)
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "luffy"}, _catalog)["ok"]
    assert "blockerless" in (luffy.turn_keywords or [])
    assert "blockerless" not in (other.turn_keywords or [])
    assert has_blockerless(_catalog("OP16-095"), luffy)


def test_op16_095_expires_after_end_turn():
    """Granted Unblockable must clear at end of turn — never stamp permanent keywords."""
    from battle.engine import _clear_turn_duration_effects

    reload_effect_library(force=True)
    p0 = PlayerState(seat=0, user_id="u0", username="p0", is_ai=False, leader_card_id="L0", hand=[], deck=["D"] * 10)
    p1 = PlayerState(seat=1, user_id="u1", username="p1", is_ai=False, leader_card_id="L0", hand=[], deck=["D"] * 10)
    st = MatchState(room_code="t", status="playing", phase="main", turn_seat=0, players=[p0, p1])
    luffy = CardInst(iid="luffy", card_id="OP16-095")
    other = CardInst(iid="other", card_id="WANO")
    p0.characters = [luffy, other]
    ops = list(get_abilities("OP16-095", "on_play")[0]["ops"])
    for o in ops:
        o["source_iid"] = "luffy"
        o["card_id"] = "OP16-095"
    apply_ops(st, 0, ops, _catalog)
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "other"}, _catalog)["ok"]
    assert "blockerless" in (other.turn_keywords or [])
    assert "blockerless" not in (other.keywords or [])
    _clear_turn_duration_effects(st)
    assert "blockerless" not in (other.turn_keywords or [])
    assert "blockerless" not in (other.keywords or [])
    assert not has_blockerless(_catalog("WANO"), other)


def test_op16_095_permanent_duration_coerced_to_turn():
    """If duration is wrongly permanent on a targeted grant, still use turn_keywords."""
    from battle.engine import _clear_turn_duration_effects

    p0 = PlayerState(seat=0, user_id="u0", username="p0", is_ai=False, leader_card_id="L0", hand=[], deck=["D"] * 10)
    p1 = PlayerState(seat=1, user_id="u1", username="p1", is_ai=False, leader_card_id="L0", hand=[], deck=["D"] * 10)
    st = MatchState(room_code="t", status="playing", phase="main", turn_seat=0, players=[p0, p1])
    other = CardInst(iid="other", card_id="WANO")
    p0.characters = [other]
    apply_ops(
        st,
        0,
        [
            {
                "op": "grant_keyword",
                "keyword": "blockerless",
                "target_kind": "own_character",
                "trait_contains": "Land of Wano",
                "duration": "permanent",  # wrong — must not stick
                "optional": True,
                "count": 1,
                "color": "black",
                "target_iid": "other",
            }
        ],
        _catalog,
    )
    assert "blockerless" in (other.turn_keywords or [])
    assert "blockerless" not in (other.keywords or [])
    _clear_turn_duration_effects(st)
    assert not has_blockerless(_catalog("WANO"), other)
