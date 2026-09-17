"""OP09-001 Shanks: on opp attack, −1000 to opponent Leader or Character (incl. parallels)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.engine import apply_action, inst_power, legal_actions, printed_power  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    if cid == "ATK":
        return {"card_id": cid, "card_type": "CHARACTER", "cost": 4, "power": 6000, "name": "Atk"}
    row = _CARDS.get(cid)
    if row:
        return dict(row)
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(leader_id: str) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=leader_id,
        deck=["X"] * 30,
        hand=[],
        life=["L"] * 5,
        turns_completed=1,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["Y"] * 30,
        hand=[],
        life=["M"] * 5,
        characters=[CardInst(iid="atk", card_id="ATK", rested=False, summoning_sick=False)],
        turns_completed=1,
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=1,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def _buff_op(cid: str) -> dict:
    entry = get_card_entry(cid)
    ab = next(a for a in entry["abilities"] if a.get("timing") == "on_opponent_attack")
    assert ab.get("once") is True
    assert ab.get("optional") is True
    buff = next(o for o in (ab.get("ops") or []) if o.get("op") == "buff")
    assert buff.get("amount") == -1000
    assert buff.get("target_kind") == "opponent_leader_or_character"
    assert buff.get("duration") == "turn"
    assert buff.get("optional") is True
    return buff


def test_op09_001_and_parallels_target_opp_leader_or_character():
    reload_effect_library(force=True)
    for cid in ("OP09-001", "OP09-001-P1", "OP09-001-P2", "OP09-001-P3"):
        _buff_op(cid)


def _confirm_and_offer_targets(st: MatchState, leader_id: str) -> None:
    r = apply_action(st, 1, {"type": "attack", "attacker_iid": "atk", "target_iid": "leader"}, catalog)
    assert r.get("ok"), r
    pe = st.pending_effect
    assert pe is not None
    assert pe.seat == 0
    assert pe.card_id == leader_id
    assert pe.source_iid == "leader"
    kinds = [a["type"] for a in legal_actions(st, 0, catalog)]
    assert "confirm_effect" in kinds
    assert apply_action(st, 0, {"type": "confirm_effect", "accept": True}, catalog)["ok"]
    ch = st.pending_choice
    assert ch is not None
    assert "leader" in (ch.options or [])
    assert "atk" in (ch.options or [])


def test_op09_001_p1_can_debuff_opponent_leader():
    """Live bug: Red-Hair parallel could not target the opponent Leader for −1000."""
    reload_effect_library(force=True)
    st = _state("OP09-001-P1")
    own_before = inst_power(st, 0, "leader", catalog)
    opp_before = inst_power(st, 1, "leader", catalog)
    assert opp_before == printed_power(catalog("OP01-001"))
    _confirm_and_offer_targets(st, "OP09-001-P1")
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "leader"}, catalog)["ok"]
    assert inst_power(st, 1, "leader", catalog) == opp_before - 1000
    assert inst_power(st, 0, "leader", catalog) == own_before
    assert st.players[1].leader_power_mod == -1000
    assert st.players[0].leader_power_mod == 0
    assert st.players[0].leader_once_used is True


def test_op09_001_p1_can_debuff_opponent_character():
    reload_effect_library(force=True)
    st = _state("OP09-001-P1")
    _confirm_and_offer_targets(st, "OP09-001-P1")
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "atk"}, catalog)["ok"]
    assert inst_power(st, 1, "atk", catalog) == 5000
    assert st.players[1].leader_power_mod == 0
    assert st.players[0].leader_once_used is True


if __name__ == "__main__":
    test_op09_001_and_parallels_target_opp_leader_or_character()
    test_op09_001_p1_can_debuff_opponent_leader()
    test_op09_001_p1_can_debuff_opponent_character()
    print("OK")
