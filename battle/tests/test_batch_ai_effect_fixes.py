"""Batch-AI effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_op15_083_split() -> None:
    abs_ = get_card_entry("OP15-083")["abilities"]
    on_play = next(a for a in abs_ if a["timing"] == "on_play")
    assert on_play.get("require_trash_gte") is None
    assert on_play["ops"][0]["op"] == "trash_deck_top"
    act = next(a for a in abs_ if a["timing"] == "activate_main")
    assert act["ops"][1].get("require_trash_gte") == 15
    assert act["ops"][1].get("from_rested") is True


def test_op15_096_trait_on_trash_only() -> None:
    ab = get_card_entry("OP15-096")["abilities"][0]
    assert ab.get("require_leader_trait") is None
    assert ab["ops"][0]["op"] == "rest_don"
    assert "草帽" in str(ab["ops"][1].get("require_leader_trait") or "")


def test_op15_095_trash_on_buff_only() -> None:
    ab = get_card_entry("OP15-095")["abilities"][0]
    assert ab.get("require_trash_gte") is None
    assert ab["ops"][1].get("require_trash_gte") == 15


def test_op16_039_then_if_impel() -> None:
    abs_ = get_card_entry("OP16-039")["abilities"]
    on_play = next(a for a in abs_ if a["timing"] == "on_play")
    assert on_play.get("require_leader_trait") is None
    assert on_play["ops"][0]["op"] == "grant_keyword"
    assert "推進城" in str(on_play["ops"][1].get("require_leader_trait") or "") or "Impel" in str(
        on_play["ops"][1].get("require_leader_trait") or ""
    )
    trig = next(a for a in abs_ if a["timing"] == "trigger")
    assert trig["ops"][0].get("leader_only") is True


def test_prb02_006_no_grant_blocker() -> None:
    abs_ = get_card_entry("PRB02-006")["abilities"]
    assert all(
        not any(o.get("op") == "grant_keyword" and o.get("keyword") == "blocker" for o in a.get("ops") or [])
        for a in abs_
    )


def test_op14_031_no_grant_blocker() -> None:
    abs_ = get_card_entry("OP14-031")["abilities"]
    assert all(
        not any(o.get("op") == "grant_keyword" and o.get("keyword") == "blocker" for o in a.get("ops") or [])
        for a in abs_
    )


def test_similar_then_if() -> None:
    op = get_card_entry("OP07-096")["abilities"][0]["ops"]
    assert op[0]["op"] == "draw" and op[1].get("require_trash_gte") == 10
    op = get_card_entry("OP16-101")["abilities"][0]["ops"]
    assert op[0]["op"] == "buff" and op[1]["op"] == "ko" and op[1].get("require_trash_gte") == 10
    op = get_card_entry("OP02-013")["abilities"][0]["ops"]
    assert op[0]["op"] == "buff" and op[1]["op"] == "grant_keyword"


if __name__ == "__main__":
    setup_module()
    test_op15_083_split()
    test_op15_096_trait_on_trash_only()
    test_op15_095_trash_on_buff_only()
    test_op16_039_then_if_impel()
    test_prb02_006_no_grant_blocker()
    test_op14_031_no_grant_blocker()
    test_similar_then_if()
    print("ok")
