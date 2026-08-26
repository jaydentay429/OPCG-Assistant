"""trash_hand must honor card_type filters (Event/Stage), and any-number costs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effects import apply_ops  # noqa: E402
from battle.engine import apply_action, legal_actions  # noqa: E402
from battle.state import MatchState, PendingEffect, PlayerState  # noqa: E402


def _catalog(cid: str) -> dict:
    table = {
        "E1": {"card_type": "EVENT", "name": "Event One", "cost": 1},
        "E2": {"card_type": "EVENT", "name": "Event Two", "cost": 2},
        "S1": {"card_type": "STAGE", "name": "Stage One", "cost": 1},
        "C1": {"card_type": "CHARACTER", "name": "Char One", "cost": 3, "power": 4000},
        "C2": {"card_type": "CHARACTER", "name": "Char Two", "cost": 4, "power": 5000},
        "LUCY": {"card_type": "LEADER", "name": "Lucy", "power": 5000, "life": 4},
        "FOE": {"card_type": "LEADER", "name": "Foe", "power": 5000, "life": 5},
    }
    return dict(table.get(cid) or {"card_type": "CHARACTER", "name": cid, "cost": 1, "power": 1000})


def _state(*, hand: list[str]) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="me",
        is_ai=False,
        leader_card_id="LUCY",
        deck=["D"] * 20,
        hand=list(hand),
        life=["L"] * 4,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="foe",
        is_ai=False,
        leader_card_id="FOE",
        deck=["B"] * 20,
        hand=[],
        life=["M"] * 5,
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def test_event_or_stage_excludes_characters():
    st = _state(hand=["E1", "C1", "S1", "C2"])
    apply_ops(
        st,
        0,
        [
            {
                "op": "trash_hand",
                "count": 20,
                "any_number": True,
                "optional": True,
                "as_cost": True,
                "card_type": "event_or_stage",
                "summary": "trash event/stage",
            },
            {"op": "buff", "amount": 1000, "target_kind": "leader", "duration": "battle", "per_trash_cards": 1},
        ],
        _catalog,
    )
    assert st.pending_choice is not None
    opts = st.pending_choice.options
    assert any(o.endswith(":E1") for o in opts)
    assert any(o.endswith(":S1") for o in opts)
    assert not any(":C1" in o for o in opts)
    assert not any(":C2" in o for o in opts)


def test_event_only_filter():
    st = _state(hand=["E1", "E2", "S1", "C1"])
    apply_ops(
        st,
        0,
        [{"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "card_type": "event"}],
        _catalog,
    )
    assert st.pending_choice is not None
    opts = st.pending_choice.options
    assert sorted(o.split(":")[-1] for o in opts) == ["E1", "E2"]
    assert not any(o.endswith(":S1") for o in opts)
    assert not any(o.endswith(":C1") for o in opts)


def test_any_number_partial_then_skip_keeps_buff():
    st = _state(hand=["E1", "E2", "C1"])
    apply_ops(
        st,
        0,
        [
            {
                "op": "trash_hand",
                "count": 20,
                "any_number": True,
                "optional": True,
                "as_cost": True,
                "card_type": "event_or_stage",
            },
            {"op": "buff", "amount": 1000, "target_kind": "leader", "duration": "battle", "per_trash_cards": 1},
        ],
        _catalog,
    )
    assert st.pending_choice is not None
    assert st.pending_choice.multi_select is True
    pick = next(o for o in st.pending_choice.options if o.endswith(":E1"))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, _catalog)["ok"]
    assert "E1" in st.players[0].trash
    assert int(getattr(st.players[0], "_last_trash_hand_count", 0) or 0) == 1
    # Power rises immediately on each trash, not only after Done.
    assert st.players[0].leader_power_mod == 1000
    if st.pending_choice:
        assert apply_action(st, 0, {"type": "skip_choice"}, _catalog)["ok"]
    assert st.pending_choice is None
    assert st.players[0].leader_power_mod == 1000


def test_any_number_two_trashes_stack_immediately():
    st = _state(hand=["E1", "E2", "S1"])
    apply_ops(
        st,
        0,
        [
            {
                "op": "trash_hand",
                "count": 20,
                "any_number": True,
                "optional": True,
                "as_cost": True,
                "card_type": "event_or_stage",
            },
            {"op": "buff", "amount": 1000, "target_kind": "leader", "duration": "battle", "per_trash_cards": 1},
        ],
        _catalog,
    )
    pick1 = next(o for o in (st.pending_choice.options if st.pending_choice else []) if o.endswith(":E1"))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick1}, _catalog)["ok"]
    assert st.players[0].leader_power_mod == 1000
    pick2 = next(o for o in (st.pending_choice.options if st.pending_choice else []) if o.endswith(":E2"))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick2}, _catalog)["ok"]
    assert st.players[0].leader_power_mod == 2000
    assert apply_action(st, 0, {"type": "skip_choice"}, _catalog)["ok"]
    assert st.players[0].leader_power_mod == 2000


def test_lucy_style_optional_trash_still_needs_confirm():
    from battle.effect_library import ability_needs_confirm, get_abilities
    from pathlib import Path
    import json

    cards = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    info = cards.get("OP15-002") or {}
    abs_ = get_abilities("OP15-002", "on_opponent_attack")
    assert abs_
    assert ability_needs_confirm(abs_[0], info) is True


def test_legal_actions_expose_confirm_on_source():
    st = _state(hand=["E1"])
    st.pending_effect = PendingEffect(
        effect_id="t1",
        seat=0,
        card_id="LUCY",
        source_iid="leader",
        ops=[{"op": "draw", "count": 1}],
        summary="may trash",
        uncertain=True,
    )
    acts = legal_actions(st, 0, _catalog)
    kinds = {(a.get("type"), a.get("accept"), a.get("source_iid")) for a in acts}
    assert ("confirm_effect", True, "leader") in kinds
    assert ("confirm_effect", False, "leader") in kinds


if __name__ == "__main__":
    test_event_or_stage_excludes_characters()
    test_event_only_filter()
    test_any_number_partial_then_skip_keeps_buff()
    test_any_number_two_trashes_stack_immediately()
    test_lucy_style_optional_trash_still_needs_confirm()
    test_legal_actions_expose_confirm_on_source()
    print("ok")
