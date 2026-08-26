"""Unit tests for deterministic effect audit checkers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_audit import (  # noqa: E402
    audit_card,
    check_empty_with_text,
    check_ko_own_as_opp,
    check_look_at_as_draw,
)
from battle.effects import has_meaningful_effect_text  # noqa: E402


def test_ko_own_as_opp_detects_wrong_target():
    info = {
        "name": "Test",
        "effect_en": 'You may K.O. 1 of your Characters with a type including "Baroque Works": Draw 1 card.',
        "effect": "可以KO1張自己擁有包含『B・W』特徵的角色卡：抽1張卡片。",
    }
    blob = info["effect_en"] + "\n" + info["effect"]
    abilities = [
        {
            "timing": "on_play",
            "summary": info["effect_en"],
            "ops": [{"op": "ko", "target_kind": "opponent_character", "optional": True}],
            "status": "compiled",
            "confidence": 0.7,
        }
    ]
    findings = check_ko_own_as_opp("P-144", info, abilities, blob)
    assert any(f["category"] == "ko_own_as_opp" for f in findings)


def test_ko_own_ok_when_own_target():
    info = {
        "name": "Test",
        "effect_en": "You may K.O. 1 of your Characters: Draw 1 card.",
        "effect": "",
    }
    blob = info["effect_en"]
    abilities = [
        {
            "timing": "on_play",
            "summary": info["effect_en"],
            "ops": [
                {"op": "ko", "target_kind": "own_character", "as_cost": True},
                {"op": "draw", "count": 1},
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ]
    findings = check_ko_own_as_opp("X-001", info, abilities, blob)
    assert findings == []


def test_look_at_as_draw():
    info = {
        "name": "Searchy",
        "effect_en": "Look at 3 cards from the top of your deck; reveal up to 1 {Impel Down} type and add it to your hand.",
        "effect": "",
    }
    blob = info["effect_en"]
    abilities = [
        {
            "timing": "on_play",
            "summary": info["effect_en"],
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.6,
        }
    ]
    findings = check_look_at_as_draw("OP16-034", info, abilities, blob)
    assert any(f["category"] == "look_at_as_draw" for f in findings)


def test_audit_card_aggregates():
    info = {
        "name": "Bad",
        "effect_en": "You may K.O. 1 of your Characters: Draw 1.",
        "effect": "",
    }
    abilities = [
        {
            "timing": "on_play",
            "ops": [{"op": "ko", "target_kind": "opponent_character"}],
            "status": "compiled",
            "confidence": 0.5,
            "summary": "You may K.O. 1 of your Characters: Draw 1.",
        }
    ]
    findings = audit_card("T-1", info, abilities)
    cats = {f["category"] for f in findings}
    assert "ko_own_as_opp" in cats


def test_empty_with_text_skips_dash_and_keyword_only():
    assert check_empty_with_text("X", {"name": "A", "effect": "-", "effect_en": "-"}, [], "- / -") == []
    blocker = {
        "name": "B",
        "effect_en": "[Blocker] (After your opponent declares an attack, you may rest this card.)",
        "effect": "【防禦】(對手攻擊後，將這張卡片置為休息狀態。)",
    }
    blob = blocker["effect_en"] + "\n" + blocker["effect"]
    assert not has_meaningful_effect_text(blocker)
    assert check_empty_with_text("Y", blocker, [], blob) == []


def test_empty_with_text_flags_real_text():
    info = {
        "name": "Ace",
        "effect_en": "When this Leader attacks, draw 1 card.",
        "effect": "",
    }
    findings = check_empty_with_text("Z", info, [], info["effect_en"])
    assert any(f["category"] == "empty_with_text" for f in findings)


if __name__ == "__main__":
    test_ko_own_as_opp_detects_wrong_target()
    test_ko_own_ok_when_own_target()
    test_look_at_as_draw()
    test_audit_card_aggregates()
    test_empty_with_text_skips_dash_and_keyword_only()
    test_empty_with_text_flags_real_text()
    print("ok")
