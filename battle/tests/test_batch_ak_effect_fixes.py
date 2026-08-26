"""Batch-AK effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_op14_005_attach_leader_or_char() -> None:
    op = get_card_entry("OP14-005")["abilities"][0]["ops"][0]
    assert op["op"] == "attach_don"
    assert op.get("target_kind") == "own_leader_or_character"
    assert op.get("from_rested") is True


def test_op14_010_power_lte_play() -> None:
    op = get_card_entry("OP14-010")["abilities"][0]["ops"][0]
    assert op.get("destination") == "play"
    assert op.get("power_lte") == 2000
    assert "超新星" in str(op.get("trait_contains") or "") or "Supernovas" in str(
        op.get("trait_contains") or ""
    )


def test_op14_011_blocker_both_turns() -> None:
    abs_ = get_card_entry("OP14-011")["abilities"]
    assert {a["timing"] for a in abs_} == {"your_turn", "opponent_turn"}
    assert all(a.get("require_don_attached_gte") == 2 for a in abs_)


def test_op14_002_source_power_gate() -> None:
    ab = get_card_entry("OP14-002")["abilities"][0]
    assert ab.get("require_source_power_gte") == 5000


def test_op14_009_no_grant_rush() -> None:
    abs_ = get_card_entry("OP14-009")["abilities"]
    assert all(
        not any(o.get("op") == "grant_keyword" and o.get("keyword") == "rush" for o in a.get("ops") or [])
        for a in abs_
    )
    assert abs_[0]["timing"] == "on_opponent_attack"


def test_op14_019_trait_any() -> None:
    op = get_card_entry("OP14-019")["abilities"][0]["ops"][0]
    assert isinstance(op.get("trait_any"), list) and len(op["trait_any"]) >= 2


def test_similar_source_power() -> None:
    assert get_card_entry("OP14-006")["abilities"][0].get("require_source_power_gte") == 5000
    assert get_card_entry("OP14-012")["abilities"][0].get("require_source_power_gte") == 5000


if __name__ == "__main__":
    setup_module()
    test_op14_005_attach_leader_or_char()
    test_op14_010_power_lte_play()
    test_op14_011_blocker_both_turns()
    test_op14_002_source_power_gate()
    test_op14_009_no_grant_rush()
    test_op14_019_trait_any()
    test_similar_source_power()
    print("ok")
