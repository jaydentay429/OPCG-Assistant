"""OP17-058 optional DON−1, OP17-078 Event Main on play, EB04-032 rest DON then gain rested DON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import (  # noqa: E402
    ability_needs_confirm,
    get_card_entry,
    reload_effect_library,
    resolve_ability,
)
from battle.engine import _confirm_effect, _run_pending_effect, apply_action, legal_actions  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str):
    return _CARDS.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.pop("leader0", "OP17-058"),
        deck=["X"] * 30,
        hand=kwargs.pop("hand0", []),
        life=["L"] * 5,
        don_active=kwargs.pop("don_active", 10),
        don_rested=kwargs.pop("don_rested", 0),
        don_given=kwargs.pop("don_given", 10),
        characters=kwargs.pop("chars0", []),
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
        characters=kwargs.pop("chars1", []),
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase=kwargs.pop("phase", "main"),
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
        **kwargs,
    )


def test_op17_058_attack_effect_is_optional():
    reload_effect_library(force=True)
    for timing in ("when_attacking", "on_opponent_attack"):
        ab = next(a for a in get_card_entry("OP17-058")["abilities"] if a["timing"] == timing)
        assert ab.get("optional") is True
        assert ability_needs_confirm(ab, catalog("OP17-058")) is True
    st = _state(don_active=4)
    pending = resolve_ability(
        st, 0, "OP17-058", "leader", "when_attacking", catalog("OP17-058"), None, allow_llm=False, catalog=catalog
    )
    assert pending is not None and pending.uncertain is True
    _run_pending_effect(st, pending, catalog)
    assert st.pending_effect is not None
    _confirm_effect(st, 0, False, catalog)
    assert st.pending_effect is None
    assert st.players[0].don_active == 4


def test_op17_078_event_main_is_on_play():
    reload_effect_library(force=True)
    ab = next(a for a in get_card_entry("OP17-078")["abilities"] if a["timing"] == "on_play")
    assert ab["ops"][0].get("op") == "rest_don"
    assert ab["ops"][0].get("count") == 2
    assert not ab["ops"][0].get("optional")


def test_op17_078_playable_even_if_rest_cost_short():
    """Card cost can be paid; effect rest-DON is separate and fails closed."""
    reload_effect_library(force=True)
    st = _state(leader0="OP17-058", hand0=["OP17-078", "H1", "H2", "H3"], don_active=3, don_given=5)
    acts = legal_actions(st, 0, catalog)
    assert any(a.get("card_id") == "OP17-078" for a in acts)
    r = apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)
    assert r.get("ok"), r
    p = st.players[0]
    assert "OP17-078" in p.trash
    assert "OP17-078" not in p.hand
    # Play cost 2 rested; remaining 1 active cannot rest 2, so no trash/gain.
    assert p.don_active == 1
    assert p.don_given == 5
    assert st.pending_choice is None
    assert st.pending_effect is None


def test_op17_078_auto_rests_don_when_enough_after_play():
    reload_effect_library(force=True)
    st = _state(leader0="OP17-058", hand0=["OP17-078", "H1", "H2", "H3"], don_active=6, don_given=5)
    r = apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)
    assert r.get("ok"), r
    p = st.players[0]
    # Play cost 2 + auto rest 2, no DON picker.
    assert p.don_active == 2
    assert p.don_rested >= 4
    assert st.pending_choice is None or st.pending_choice.target_kind != "don"


def test_op17_066_no_own_cost10_skips_on_play():
    reload_effect_library(force=True)
    st = _state(leader0="OP17-058", hand0=["OP17-066"], don_active=5, don_given=5)
    r = apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)
    assert r.get("ok"), r
    p = st.players[0]
    assert p.don_given == 5
    assert st.pending_effect is None
    assert len(p.hand) == 0


def test_op17_066_with_cost10_asks_before_don_minus():
    reload_effect_library(force=True)
    big = CardInst(iid="big", card_id="COST10")

    def cat(cid: str):
        if cid == "COST10":
            return {"card_id": cid, "card_type": "CHARACTER", "cost": 10, "power": 10000}
        return catalog(cid)

    st = _state(leader0="OP17-058", hand0=["OP17-066"], chars0=[big], don_active=5, don_given=5)
    r = apply_action(st, 0, {"type": "play_card", "hand_index": 0}, cat)
    assert r.get("ok"), r
    assert st.pending_effect is not None
    _confirm_effect(st, 0, False, cat)
    assert st.players[0].don_given == 5


def test_eb04_032_activate_gains_rested_don():
    reload_effect_library(force=True)
    act = next(a for a in get_card_entry("EB04-032")["abilities"] if a["timing"] == "activate_main")
    assert int(act.get("cost_don") or 0) == 0
    queen = CardInst(iid="q", card_id="EB04-032")
    st = _state(leader0="OP17-058", chars0=[queen], don_active=2, don_rested=0, don_given=5)
    r = apply_action(st, 0, {"type": "activate_main", "source_iid": "q"}, catalog)
    assert r.get("ok"), r
    # Optional rest-DON cost: confirm by selecting DON.
    if st.pending_choice is not None:
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": "don"}, catalog)["ok"]
        if st.pending_choice is not None:
            assert apply_action(st, 0, {"type": "select_choice", "target_iid": "don"}, catalog)["ok"]
    p = st.players[0]
    assert p.don_active == 0
    assert p.don_rested == 3  # rest 2 field DON + gain 1 rested
    assert p.don_given == 6
