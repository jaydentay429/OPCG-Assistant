"""Batch-AJ effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.engine import _played_card_gates_ok  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_op12_081_vs_leader_and_play_gates() -> None:
    abs_ = get_card_entry("OP12-081")["abilities"]
    atk = next(a for a in abs_ if a["timing"] == "when_attacking")
    assert atk.get("vs_leader_only") is True
    play = next(a for a in abs_ if a["timing"] == "on_opponent_play")
    assert play.get("require_played_base_cost_gte") == 8
    assert play.get("or_played_by_character_effect") is True
    assert _played_card_gates_ok(play, {"cost": 8}, by_character_effect=False)
    assert not _played_card_gates_ok(play, {"cost": 4}, by_character_effect=False)
    assert _played_card_gates_ok(play, {"cost": 4}, by_character_effect=True)


def test_op12_086_name_or_trait_robin() -> None:
    op = get_card_entry("OP12-086")["abilities"][0]["ops"][0]
    assert op.get("name_or_trait") is True
    assert "Robin" in str(op.get("name_contains") or "") or "羅賓" in str(op.get("name_contains") or "")
    assert "可亞拉" in str(op.get("exclude_name") or "") or "Koala" in str(op.get("exclude_name") or "")


def test_op12_094_trash_bottom_cost() -> None:
    ops = get_card_entry("OP12-094")["abilities"][0]["ops"]
    assert ops[0]["op"] == "trash_to_bottom" and ops[0].get("as_cost")
    assert ops[0].get("count") == 3
    assert ops[1]["op"] == "play_from_hand" and ops[1].get("require_leader_trait")
    assert get_card_entry("OP12-094")["abilities"][0].get("require_leader_trait") is None


def test_op12_119_cost_duration() -> None:
    ops = get_card_entry("OP12-119")["abilities"][0]["ops"]
    assert ops[2]["op"] == "grant_cost"
    assert ops[2].get("duration") == "until_opp_turn_end"


def test_op12_098_same_target_gate() -> None:
    ops = get_card_entry("OP12-098")["abilities"][0]["ops"]
    assert ops[1].get("same_target_as_prior") is True
    assert ops[1].get("require_own_char_cost_gte") == 8
    assert "革命" in str(ops[1].get("require_chars_trait") or "") or "Revolutionary" in str(
        ops[1].get("require_chars_trait") or ""
    )


def test_op12_087_koala_bilingual() -> None:
    ab = get_card_entry("OP12-087")["abilities"][0]
    assert "可亞拉" in str(ab.get("require_leader_name") or "") or "Koala" in str(
        ab.get("require_leader_name") or ""
    )


if __name__ == "__main__":
    setup_module()
    test_op12_081_vs_leader_and_play_gates()
    test_op12_086_name_or_trait_robin()
    test_op12_094_trash_bottom_cost()
    test_op12_119_cost_duration()
    test_op12_098_same_target_gate()
    test_op12_087_koala_bilingual()
    print("ok")
