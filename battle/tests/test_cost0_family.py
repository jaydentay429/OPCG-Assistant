"""Regression: cost-0 filters must not compile as set_cost; related gates/ops stay correct."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_abilities, reload_effect_library  # noqa: E402
from battle.effects import (  # noqa: E402
    _parse_set_cost_ops,
    effect_blob,
    parse_activate_main,
    parse_simple_on_play,
)

CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def setup_module():
    reload_effect_library(force=True)


def test_no_false_set_cost_from_cost0_filter_text():
    bad = []
    for cid, info in CARDS.items():
        if not isinstance(info, dict):
            continue
        blob = effect_blob(info)
        if "費用0的角色" not in blob and "费用0的角色" not in blob and "0 cost Character" not in blob:
            continue
        if _parse_set_cost_ops(blob):
            continue
        for a in get_abilities(cid):
            if any(o.get("op") == "set_cost" for o in a.get("ops") or []):
                bad.append(cid)
    assert bad == []


def test_op14_090_rest_cost_eq():
    ops = parse_simple_on_play(CARDS["OP14-090"])
    assert ops and ops[0]["op"] == "rest_opponent_character"
    assert ops[0].get("cost_eq") == 0


def test_st19_003_trash_cost_eq():
    spec = parse_activate_main(CARDS["ST19-003"])
    assert spec
    trash = next(o for o in spec["ops"] if o.get("op") == "trash")
    assert trash.get("cost_eq") == 0
    assert trash.get("target_kind") == "opponent_character"


def test_op07_003_two_buffs():
    spec = parse_activate_main(CARDS["OP07-003"])
    assert spec
    buffs = [o for o in spec["ops"] if o.get("op") == "buff"]
    assert len(buffs) == 2
    assert all(b.get("amount") == -2000 for b in buffs)


def test_st08_009_field_cost_gate():
    from battle.effect_library import _from_templates

    ab = _from_templates("ST08-009", "on_play", CARDS["ST08-009"])
    assert ab
    assert ab.get("require_field_char_cost_eq") == 0


def test_op02_093_conditional_buff_self():
    spec = parse_activate_main(CARDS["OP02-093"])
    assert spec
    buff = next(o for o in spec["ops"] if o.get("op") == "buff_self")
    assert buff.get("require_field_char_cost_eq") == 0


def test_zero_cost_events_are_numeric_zero():
    """Official cardlist prints Event 0 as '-'; curve/filter must store 0, not null."""
    samples = ("OP12-016", "OP02-068", "OP15-074", "EB04-009", "OP16-020")
    for cid in samples:
        assert CARDS[cid].get("cost") == 0, cid
    leftover = [
        cid
        for cid, info in CARDS.items()
        if isinstance(info, dict)
        and str(info.get("category") or "") == "Event"
        and info.get("cost") is None
    ]
    assert leftover == []
