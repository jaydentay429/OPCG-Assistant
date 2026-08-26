"""Batch-AC effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_return_don_active_only_schema() -> None:
    e = normalize_card_entry(
        "X",
        {
            "version": 1,
            "abilities": [
                {
                    "timing": "activate_main",
                    "ops": [
                        {
                            "op": "return_don",
                            "count": 8,
                            "owner": "self",
                            "as_cost": True,
                            "optional": True,
                            "active_only": True,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                }
            ],
        },
    )
    assert e["abilities"][0]["ops"][0].get("active_only") is True


def test_op16_060_active_eight() -> None:
    ops = get_card_entry("OP16-060")["abilities"][0]["ops"]
    assert ops[0]["count"] == 8 and ops[0].get("active_only") and ops[0].get("optional")
    assert ops[1].get("count") == 3 and ops[1].get("different_names")


def test_op16_066_order_gain_then_draw_trash() -> None:
    ops = get_card_entry("OP16-066")["abilities"][0]["ops"]
    assert ops[0]["op"] == "gain_don" and ops[0].get("as_rested")
    assert ops[1]["op"] == "draw" and ops[1]["count"] == 2
    assert ops[2]["op"] == "trash_hand" and ops[2]["count"] == 2
    trait = str(get_card_entry("OP16-066")["abilities"][0].get("require_leader_trait") or "")
    assert "Navy" in trait or "海軍" in trait


def test_op16_073_active_and_rested_no_bogus_your_turn() -> None:
    abs_ = get_card_entry("OP16-073")["abilities"]
    assert {a["timing"] for a in abs_} == {"on_play", "end_of_your_turn"}
    ops = next(a for a in abs_ if a["timing"] == "on_play")["ops"]
    assert ops[0]["op"] == "gain_don" and not ops[0].get("as_rested")
    assert ops[1]["op"] == "gain_don" and ops[1].get("as_rested")
    eot = next(a for a in abs_ if a["timing"] == "end_of_your_turn")
    assert eot["ops"][1].get("target_kind") == "self"


def test_op16_075_active_and_rested() -> None:
    ops = get_card_entry("OP16-075")["abilities"][0]["ops"]
    assert len(ops) == 2
    assert not ops[0].get("as_rested") and ops[1].get("as_rested")


def test_similar_op09_061_eb04_031() -> None:
    for cid in ("OP09-061", "EB04-031"):
        abs_ = get_card_entry(cid)["abilities"]
        don_abs = [a for a in abs_ if any(o.get("op") == "gain_don" for o in a["ops"])]
        assert don_abs
        ops = don_abs[0]["ops"]
        gains = [o for o in ops if o.get("op") == "gain_don"]
        assert len(gains) == 2
        assert not gains[0].get("as_rested") and gains[1].get("as_rested")


def test_op16_076_admiral_bilingual_and_battle() -> None:
    abs_ = get_card_entry("OP16-076")["abilities"]
    main = abs_[0]["ops"][1]
    assert "Admiral" in str(main.get("trait_contains") or "") or "上將" in str(main.get("trait_contains") or "")
    counter = abs_[1]
    assert counter["ops"][0].get("duration") == "battle"
    trait = str(counter.get("require_chars_trait") or "")
    assert "Admiral" in trait or "上將" in trait


def test_op16_077_reveal_adds() -> None:
    op = get_card_entry("OP16-077")["abilities"][0]["ops"][0]
    assert op.get("max_add") == 2 and op.get("reveal_adds") is True


def test_op07_076_trigger_optional() -> None:
    trig = next(a for a in get_card_entry("OP07-076")["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0].get("optional") is True


if __name__ == "__main__":
    setup_module()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all batch_ac tests passed")
