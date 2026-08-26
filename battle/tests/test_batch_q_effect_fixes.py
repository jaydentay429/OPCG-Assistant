"""Batch-Q effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_op11_041_life_leave_no_don_gate() -> None:
    entry = get_card_entry("OP11-041")
    life = next(a for a in entry["abilities"] if a.get("on_life_leave"))
    assert life["timing"] == "your_turn"
    assert life.get("require_don_attached_gte") is None
    assert life.get("require_hand_lte") == 7
    assert life.get("once") is True
    assert life.get("on_life_leave_from") == "either"
    atk = next(a for a in entry["abilities"] if a["timing"] == "on_opponent_attack")
    assert atk.get("require_don_attached_gte") == 1
    assert atk["ops"][0].get("as_cost") is True
    assert atk["ops"][1].get("op") == "buff"
    assert atk["ops"][1].get("duration") == "turn"


def test_op08_105_opp_life_leave() -> None:
    ab = next(a for a in get_card_entry("OP08-105")["abilities"] if a.get("on_life_leave"))
    assert ab.get("on_life_leave_from") == "opponent"
    assert ab.get("require_don_attached_gte") == 1


def test_thriller_bark_triggers() -> None:
    for cid in ("OP14-102", "OP14-089", "OP14-100", "OP14-109", "OP14-117", "OP14-110", "OP14-111"):
        trig = next(a for a in get_card_entry(cid)["abilities"] if a["timing"] == "trigger")
        op = trig["ops"][0]
        assert op.get("cost_lte") == 4
        assert op.get("as_rested") is True
        assert "Thriller" in str(op.get("trait_contains") or "")
        assert op.get("from_zone") == "trash"


def test_op14_104_add_from_trash_life() -> None:
    play = next(a for a in get_card_entry("OP14-104")["abilities"] if a["timing"] == "on_play")
    choose = play["ops"][0]
    assert choose["op"] == "choose_one"
    life_ops = choose["options"][0]["ops"]
    assert life_ops[0]["op"] == "add_from_trash"
    assert life_ops[0].get("destination") == "life"
    assert life_ops[0].get("face") == "up"


def test_op13_119_bounce_then_opp_play() -> None:
    play = next(a for a in get_card_entry("OP13-119")["abilities"] if a["timing"] == "on_play")
    ops = play["ops"]
    assert ops[1]["op"] == "return_to_hand"
    bounce = ops[2]
    assert bounce.get("owner") == "opponent"
    assert bounce.get("if_returned") is True
    assert bounce.get("cost_lte") == 4
    p5 = next(a for a in get_card_entry("OP13-119-P5")["abilities"] if a["timing"] == "on_play")
    assert p5["ops"][2].get("cost_lte") == 8


def test_op14_110_hogback_exclude() -> None:
    on_ko = next(a for a in get_card_entry("OP14-110")["abilities"] if a["timing"] == "on_ko")
    excl = str(on_ko["ops"][0].get("exclude_name") or "")
    assert "Hogback" in excl
    assert "赫古巴庫" in excl


def test_schema_play_from_hand_owner_if_returned() -> None:
    ab = normalize_ability(
        {
            "timing": "on_play",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "owner": "opponent",
                    "if_returned": True,
                    "cost_lte": 4,
                    "from_zone": "hand",
                }
            ],
        }
    )
    op = ab["ops"][0]
    assert op.get("owner") == "opponent"
    assert op.get("if_returned") is True


def test_schema_on_life_leave_ability() -> None:
    ab = normalize_ability(
        {
            "timing": "your_turn",
            "on_life_leave": True,
            "on_life_leave_from": "opponent",
            "ops": [{"op": "draw", "count": 1}],
        }
    )
    assert ab.get("on_life_leave") is True
    assert ab.get("on_life_leave_from") == "opponent"


if __name__ == "__main__":
    setup_module()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all ok")
