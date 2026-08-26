"""Batch-O effect encoding fixes (OP14-108, OP07-107, OP16-102, ST34-004, OP15-119, …)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_op14_108_on_play_ko_not_activate_on_ko() -> None:
    entry = get_card_entry("OP14-108")
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert on_play.get("require_leader_multicolor") is True
    assert on_play.get("require_opp_life_lte") == 3
    assert on_play.get("require_life_lte") is None
    ops = on_play["ops"]
    assert ops[0]["op"] == "ko"
    assert ops[0].get("base_power_lte") == 7000
    trig = next(a for a in entry["abilities"] if a["timing"] == "trigger")
    assert trig["ops"] == [{"op": "activate_timing", "timing": "on_play"}] or trig["ops"][0]["op"] == "activate_timing"


def test_op07_107_life_gates_play_only() -> None:
    entry = get_card_entry("OP07-107")
    ab = next(a for a in entry["abilities"] if a["timing"] == "trigger")
    assert ab.get("require_life_lte") is None
    assert ab["ops"][0]["op"] == "draw"
    assert ab["ops"][1]["op"] == "play_from_hand"
    assert ab["ops"][1].get("require_life_lte") == 1
    assert ab["ops"][1].get("self_card") is True


def test_op16_102_trigger_only_activates_on_ko() -> None:
    entry = get_card_entry("OP16-102")
    trig = next(a for a in entry["abilities"] if a["timing"] == "trigger")
    assert len(trig["ops"]) == 1
    assert trig["ops"][0]["op"] == "activate_timing"
    assert trig["ops"][0]["timing"] == "on_ko"
    on_ko = next(a for a in entry["abilities"] if a["timing"] == "on_ko")
    assert "蜂巢" in str(on_ko["ops"][1].get("name_contains") or "") or "Fullalead" in str(
        on_ko["ops"][1].get("name_contains") or ""
    )


def test_st34_004_set_base_power_zero() -> None:
    entry = get_card_entry("ST34-004")
    ab = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    ops = ab["ops"]
    assert ops[0]["op"] == "return_don" and ops[0].get("count") == 4
    assert ops[1]["op"] == "trash_hand"
    assert any(o.get("op") == "set_base_power" and o.get("amount") == 0 for o in ops)


def test_op09_062_gain_don_rested() -> None:
    entry = get_card_entry("OP09-062")
    ab = next(a for a in entry["abilities"] if a["timing"] == "when_attacking")
    gain = next(o for o in ab["ops"] if o["op"] == "gain_don")
    assert gain.get("as_rested") is True


def test_op09_078_trait_on_buff_only() -> None:
    entry = get_card_entry("OP09-078")
    ab = next(a for a in entry["abilities"] if a["timing"] == "counter_event")
    assert ab.get("require_leader_trait") is None
    buff = next(o for o in ab["ops"] if o["op"] == "buff")
    assert "Straw Hat" in str(buff.get("require_leader_trait") or "") or "草帽" in str(
        buff.get("require_leader_trait") or ""
    )
    assert ab["ops"][-1]["op"] == "draw" and ab["ops"][-1]["count"] == 2


def test_op15_119_blocker_via_flag_not_on_block() -> None:
    entry = get_card_entry("OP15-119")
    timings = {a["timing"] for a in entry["abilities"]}
    assert "on_block" not in timings
    assert "on_opp_event" in timings
    blocker = [a for a in entry["abilities"] if a.get("on_opp_blocker")]
    assert len(blocker) >= 1
    assert any(a["timing"] == "your_turn" for a in blocker)


def test_op15_113_add_life_optional() -> None:
    entry = get_card_entry("OP15-113")
    ab = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    add = next(o for o in ab["ops"] if o["op"] == "add_life")
    assert add.get("optional") is True
