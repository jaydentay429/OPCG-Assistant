"""Batch-AB effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_return_don_any_number_schema() -> None:
    e = normalize_card_entry(
        "X",
        {
            "version": 1,
            "abilities": [
                {
                    "timing": "on_play",
                    "ops": [
                        {
                            "op": "return_don",
                            "count": 10,
                            "owner": "self",
                            "as_cost": True,
                            "optional": True,
                            "any_number": True,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                }
            ],
        },
    )
    op = e["abilities"][0]["ops"][0]
    assert op.get("any_number") is True
    assert op.get("optional") is True
    assert op.get("as_cost") is True


def test_op09_119_return_1_plus() -> None:
    ops = get_card_entry("OP09-119")["abilities"][0]["ops"]
    assert ops[0]["op"] == "return_don"
    assert ops[0].get("any_number") is True
    assert ops[0].get("optional") is True
    assert ops[0].get("as_cost") is True
    assert ops[1]["op"] == "draw"
    assert ops[2].get("keyword") == "rush"


def test_op09_065_has_return_cost() -> None:
    ops = get_card_entry("OP09-065")["abilities"][0]["ops"]
    assert ops[0]["op"] == "return_don" and ops[0].get("any_number")
    assert ops[1].get("keyword") == "rush"
    assert ops[2]["op"] == "rest_opponent_character" and ops[2].get("cost_lte") == 6


def test_op09_068_070_073_any_number() -> None:
    for cid in ("OP09-068", "OP09-070", "OP09-073"):
        op0 = get_card_entry(cid)["abilities"][0]["ops"][0]
        assert op0["op"] == "return_don"
        assert op0.get("any_number") is True
        assert op0.get("optional") is True


def test_op09_078_trash_as_cost() -> None:
    ops = get_card_entry("OP09-078")["abilities"][0]["ops"]
    trash = next(o for o in ops if o["op"] == "trash_hand")
    assert trash.get("as_cost") is True and trash.get("optional") is True
    draw = next(o for o in ops if o["op"] == "draw")
    assert "Straw Hat" in str(draw.get("require_leader_trait") or "") or "草帽" in str(
        draw.get("require_leader_trait") or ""
    )


def test_op05_119_gain_don_optional() -> None:
    act = next(a for a in get_card_entry("OP05-119")["abilities"] if a["timing"] == "activate_main")
    assert act.get("once") and act.get("cost_don") == 1
    assert act["ops"][0].get("optional") is True


def test_st10_002_don_0_or_8() -> None:
    ab = get_card_entry("ST10-002")["abilities"][0]
    assert ab.get("require_don_field_0_or_gte") == 8
    assert ab.get("once") is True


def test_op08_076_current_power_gate() -> None:
    ops = get_card_entry("OP08-076")["abilities"][0]["ops"]
    assert ops[1].get("require_opp_char_power_gte") == 6000


def test_st31_004_per_straw_hat() -> None:
    on_play = next(a for a in get_card_entry("ST31-004")["abilities"] if a["timing"] == "on_play")
    op = on_play["ops"][0]
    assert op.get("per_choose") is True
    assert op.get("include_leader") is True and op.get("include_stage") is True
    assert "Straw Hat" in str(op.get("per_own_trait") or "") or "草帽" in str(op.get("per_own_trait") or "")


def test_st21_003_blockerless() -> None:
    op = get_card_entry("ST21-003")["abilities"][0]["ops"][0]
    assert op.get("keyword") == "blockerless"
    assert op.get("power_gte") == 6000


def test_op08_119_ko_all_except_self() -> None:
    ops = get_card_entry("OP08-119")["abilities"][0]["ops"]
    ko = ops[1]
    assert ko.get("all") and ko.get("exclude_self")
    assert ko.get("target_kind") == "any_character"


if __name__ == "__main__":
    setup_module()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all batch_ab tests passed")
