"""Batch-Z effect encoding fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.engine import _resolve_search_dest  # noqa: E402
from battle.state import MatchState, PendingSearch, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def setup_module() -> None:
    reload_effect_library()


def test_op11_040_top_or_bottom_search() -> None:
    ab = get_card_entry("OP11-040")["abilities"][0]
    assert ab.get("optional") is True
    assert ab.get("require_don_field_gte") == 8
    op = ab["ops"][0]
    assert op.get("to_top_or_bottom") is True
    assert "Straw Hat" in str(op.get("trait_contains") or "") or "草帽" in str(op.get("trait_contains") or "")


def test_op01_119_buff_then_life_gated_don() -> None:
    abs_ = get_card_entry("OP01-119")["abilities"]
    counters = [a for a in abs_ if a["timing"] == "counter_event"]
    assert len(counters) == 2
    assert counters[0].get("require_life_lte") is None
    assert counters[0]["ops"][0]["op"] == "buff"
    assert counters[1].get("require_life_lte") == 2
    assert counters[1]["ops"][0].get("as_rested") is True
    trig = next(a for a in abs_ if a["timing"] == "trigger")
    assert trig["ops"][0].get("as_rested") is not True


def test_op04_075_trigger_active_don() -> None:
    trig = next(a for a in get_card_entry("OP04-075")["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0].get("as_rested") is not True


def test_op06_119_reveal_play_exclude_sanji() -> None:
    op = get_card_entry("OP06-119")["abilities"][0]["ops"][0]
    assert op.get("top_n") == 1
    assert op.get("destination") == "play"
    assert op.get("cost_lte") == 9
    assert "Sanji" in str(op.get("exclude_name") or "") or "香吉士" in str(op.get("exclude_name") or "")


def test_op09_078_draw_gated() -> None:
    ops = get_card_entry("OP09-078")["abilities"][0]["ops"]
    draw = next(o for o in ops if o["op"] == "draw")
    assert "Straw Hat" in str(draw.get("require_leader_trait") or "") or "草帽" in str(
        draw.get("require_leader_trait") or ""
    )


def test_op13_043_trash_mandatory() -> None:
    trash = get_card_entry("OP13-043")["abilities"][0]["ops"][1]
    assert trash.get("optional") is False


def test_op08_076_current_power_gate() -> None:
    ops = get_card_entry("OP08-076")["abilities"][0]["ops"]
    assert ops[1].get("require_opp_char_power_gte") == 6000


def test_search_dest_choose_runtime() -> None:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP11-040",
        deck=["A", "B", "C"],
        hand=[],
        life=["L"] * 5,
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
    )
    st = MatchState(
        room_code="Z",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )
    st.pending_search = PendingSearch(
        seat=0,
        card_id="OP11-040",
        source_iid="leader",
        revealed=["X1", "X2"],
        eligible=[0, 1],
        max_add=0,
        phase="choose_dest",
        order_bottom=True,
        to_top_or_bottom=True,
        order_dest="",
        remaining_ops=[],
    )
    r = _resolve_search_dest(st, 0, "deck:top", lambda cid: _CARDS.get(cid) or {})
    assert r.get("ok")
    assert st.pending_search is not None
    assert st.pending_search.phase == "order"
    assert st.pending_search.order_dest == "top"


if __name__ == "__main__":
    setup_module()
    from scripts.fix_batch_z_effects import main as fix_main

    fix_main()
    reload_effect_library()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
