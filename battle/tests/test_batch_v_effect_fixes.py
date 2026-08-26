"""Batch-V effect encoding + hand-trash runtime."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import effective_play_cost, fire_hand_trash_by_effect  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def setup_module() -> None:
    reload_effect_library()


def catalog(cid: str):
    return dict(_CARDS.get(cid) or {"cost": 1, "name": cid, "card_type": "CHARACTER", "traits": []})


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.pop("leader0", "OP12-040"),
        deck=["X"] * 30,
        hand=kwargs.pop("hand0", []),
        life=["L"] * 5,
        don_active=kwargs.pop("don_active", 10),
        characters=kwargs.pop("chars0", []),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["Y"] * 30,
        hand=kwargs.pop("hand1", []),
        life=["M"] * 5,
        characters=kwargs.pop("chars1", []),
    )
    return MatchState(
        room_code="V",
        status="playing",
        phase="main",
        turn_seat=kwargs.pop("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def test_op12_040_navy_source_both_turns() -> None:
    abs_ = get_card_entry("OP12-040")["abilities"]
    assert {a["timing"] for a in abs_} >= {"your_turn", "opponent_turn"}
    for a in abs_:
        assert a.get("on_hand_trash_by_own_effect") is True
        assert "Navy" in str(a.get("require_effect_source_trait") or "")
        assert a.get("require_chars_trait") is None
        assert a["ops"][0].get("equal_trashed") is True


def test_op12_040_draw_equal_runtime() -> None:
    st = _state(leader0="OP12-040", hand0=["A", "B"], deck=["D1", "D2", "D3"] + ["X"] * 27)
    # Simulate Navy card trashing 2
    apply_ops(
        st,
        0,
        [{"op": "trash_hand", "count": 2, "optional": False, "owner": "self", "card_id": "OP12-056"}],
        catalog,
    )
    # After interactive picks may be pending; force count path
    st.players[0].hand = ["A", "B"]
    st.pending_choice = None
    apply_ops(
        st,
        0,
        [
            {
                "op": "trash_hand",
                "count": 2,
                "optional": False,
                "owner": "self",
                "card_id": "OP12-056",
                "target_iid": "hand:0:A",
            }
        ],
        catalog,
    )
    # Manual fire with known count
    st.players[0].hand = []
    st.players[0].deck = ["D1", "D2", "D3"] + ["X"] * 27
    fire_hand_trash_by_effect(
        st, 0, catalog, effect_card_id="OP12-056", by_own_effect=True, trashed_count=2
    )
    assert len(st.players[0].hand) == 2


def test_op06_043_bottom_cost_not_opp_buff() -> None:
    ab = get_card_entry("OP06-043")["abilities"][0]
    ops = ab["ops"]
    assert [o["op"] for o in ops] == ["trash_hand", "return_to_bottom", "buff_self"]
    assert ops[0].get("as_cost") is True
    assert ops[1].get("as_cost") is True
    assert ops[1].get("target_kind") == "any_character"
    assert ops[1].get("cost_lte") == 2
    assert ops[2].get("amount") == 3000


def test_op06_051_opp_returns_character() -> None:
    ops = get_card_entry("OP06-051")["abilities"][0]["ops"]
    assert ops[0].get("as_cost") is True and ops[0].get("count") == 2
    assert ops[1].get("op") == "return_to_hand"
    assert ops[1].get("target_kind") == "opponent_character"
    assert ops[1].get("chooser") == "opponent"


def test_eb04_028_navy_on_deny_not_ability() -> None:
    play = next(a for a in get_card_entry("EB04-028")["abilities"] if a["timing"] == "on_play")
    assert play.get("require_leader_trait") is None
    deny = next(o for o in play["ops"] if o["op"] == "deny_attack")
    assert "Navy" in str(deny.get("require_leader_trait") or "")


def test_op12_051_targeted_base_cost_deny() -> None:
    deny = get_card_entry("OP12-051")["abilities"][0]["ops"][2]
    assert deny.get("op") == "deny_blocker"
    assert deny.get("target_kind") == "opponent_character"
    assert deny.get("base_cost_lte") == 4


def test_op12_056_and_st33_005_blue() -> None:
    for cid in ("OP12-056", "ST33-005"):
        play = next(
            o
            for a in get_card_entry(cid)["abilities"]
            for o in a["ops"]
            if o.get("op") == "play_from_hand"
        )
        assert play.get("color") == "blue"
        assert "Navy" in str(play.get("trait_contains") or "")


def test_st33_004_hand_cost_gate() -> None:
    ab = get_card_entry("ST33-004")["abilities"][0]
    assert ab.get("timing") == "hand_cost"
    assert ab.get("require_hand_trashed_by_effect_this_turn") is True
    st = _state(hand0=["ST33-004"])
    # Without flag: full cost
    assert effective_play_cost(st, 0, "ST33-004", catalog) == 6
    st.players[0].hand_trashed_by_effect_this_turn = True
    assert effective_play_cost(st, 0, "ST33-004", catalog) == 3


def test_op14_049_hand_trash_rush() -> None:
    abs_ = get_card_entry("OP14-049")["abilities"]
    assert any(a.get("on_hand_trashed_by_effect") for a in abs_)
    st = _state(
        chars0=[CardInst(iid="j1", card_id="OP14-049")],
        hand0=["Z"],
    )
    fire_hand_trash_by_effect(st, 0, catalog, effect_card_id="ST33-001", by_own_effect=True, trashed_count=1)
    ch = st.players[0].characters[0]
    assert "rush" in (ch.turn_keywords or []) or any(
        "rush" in str(e.get("keyword") or e) for e in (ch.keywords_until_end or [])
    ) or "rush" in getattr(ch, "turn_keywords", set())


if __name__ == "__main__":
    setup_module()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
