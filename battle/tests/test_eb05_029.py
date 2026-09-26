"""EB05-029 Haori Ori: Main may trash 1: blank+bounce opp cost≤6; Trigger draw 2 trash 1."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if "battle" not in sys.modules:
    pkg = types.ModuleType("battle")
    pkg.__path__ = [str(ROOT / "battle")]
    sys.modules["battle"] = pkg

from battle.effect_library import get_abilities, get_card_entry, reload_effect_library  # noqa: E402
from battle.engine import _resolve_trigger, apply_action  # noqa: E402
from battle.state import CardInst, MatchState, PendingTrigger, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "H1": {"card_id": "H1", "card_type": "CHARACTER", "cost": 1, "power": 2000, "name": "H1"},
        "C6": {"card_id": "C6", "card_type": "CHARACTER", "cost": 6, "power": 7000, "name": "C6"},
        "C7": {"card_id": "C7", "card_type": "CHARACTER", "cost": 7, "power": 8000, "name": "C7"},
        "D0": {"card_id": "D0", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "D0"},
        "D1": {"card_id": "D1", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "D1"},
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, hand: list[str]) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="ST22-001",
        deck=["D0", "D1"] + ["X"] * 18,
        hand=list(hand),
        life=["L"] * 5,
        don_active=8,
        don_given=8,
        turns_completed=1,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["Y"] * 20,
        hand=[],
        life=["M"] * 5,
        characters=[
            CardInst(iid="cheap", card_id="C6", rested=False),
            CardInst(iid="dear", card_id="C7", rested=False),
        ],
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


def _drain(st: MatchState, seat: int) -> None:
    for _ in range(8):
        if st.pending_effect and st.pending_effect.seat == seat:
            assert apply_action(st, seat, {"type": "confirm_effect", "accept": True}, catalog)["ok"]
            continue
        break


def test_eb05_029_override_shape() -> None:
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-029")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-029 abilities dropped on normalize"
    main = next(a for a in get_abilities("EB05-029", "on_play"))
    trash, bounce = main["ops"]
    assert trash.get("op") == "trash_hand" and trash.get("as_cost") is True
    assert bounce.get("op") == "return_to_hand"
    assert bounce.get("cost_lte") == 6
    assert bounce.get("negate_this_turn") is True
    trig = next(a for a in get_abilities("EB05-029", "trigger"))
    assert trig["ops"][0].get("op") == "draw" and trig["ops"][0].get("count") == 2
    assert trig["ops"][1].get("op") == "trash_hand" and trig["ops"][1].get("count") == 1


def test_eb05_029_skip_cost_does_not_bounce() -> None:
    reload_effect_library(force=True)
    st = _state(hand=["EB05-029", "H1"])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _drain(st, 0)
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert [c.iid for c in st.player(1).characters] == ["cheap", "dear"]
    assert "H1" in st.player(0).hand
    assert "EB05-029" in st.player(0).trash


def test_eb05_029_bounce_cost_6_not_7() -> None:
    reload_effect_library(force=True)
    st = _state(hand=["EB05-029", "H1"])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _drain(st, 0)
    assert st.pending_choice is not None
    opts = st.pending_choice.options or []
    pay = next(o for o in opts if str(o).endswith(":H1") or o == "H1")
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pay}, catalog)["ok"]
    _drain(st, 0)
    ch = st.pending_choice
    assert ch is not None
    assert "cheap" in (ch.options or [])
    assert "dear" not in (ch.options or [])
    cheap = next(c for c in st.player(1).characters if c.iid == "cheap")
    assert cheap.effects_negated is False
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "cheap"}, catalog)["ok"]
    assert "cheap" not in [c.iid for c in st.player(1).characters]
    assert "C6" in st.player(1).hand
    assert "dear" in [c.iid for c in st.player(1).characters]
    assert "H1" in st.player(0).trash


def test_eb05_029_trigger_draw_2_trash_1() -> None:
    reload_effect_library(force=True)
    st = _state(hand=["KEEP"])
    st.phase = "trigger"
    st.pending_trigger = PendingTrigger(
        seat=0,
        card_id="EB05-029",
        summary="trig",
        ops=list(next(a for a in get_abilities("EB05-029", "trigger"))["ops"]),
    )
    assert _resolve_trigger(st, 0, True, catalog)["ok"]
    if st.pending_choice is not None:
        opts = st.pending_choice.options or []
        pick = next(o for o in opts if "KEEP" in str(o) or "D0" in str(o) or "D1" in str(o))
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert st.pending_choice is None
    assert len(st.player(0).hand) == 2
    assert "EB05-029" in st.player(0).trash
    assert len(st.player(0).trash) >= 2
