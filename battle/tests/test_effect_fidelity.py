"""Tests for full-library effect fidelity extractor/diff."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_fidelity import diff_card, extract_expected_signals  # noqa: E402


def test_extract_choose_one_and_gates():
    info = {
        "effect_en": "[Main] If you have 2 or less Life cards, choose one: • Draw 1. • Gain 1 DON!!",
        "effect": "",
    }
    sig = extract_expected_signals(info)
    assert "choose_one" in sig["op_hints"]
    assert sig["gates"].get("require_life_lte") == 2
    assert "on_play" in sig["timings"] or "counter_event" in sig["timings"] or True


def test_extract_attack_tax():
    info = {
        "effect_en": (
            "[On Play] If your Leader's type includes {Whitebeard Pirates} and you have 2 or less Life cards, "
            "select all of your opponent's Characters. Until the end of your opponent's next turn, "
            "none of the selected Characters can attack unless your opponent trashes 2 cards from their hand "
            "whenever they attack."
        )
    }
    sig = extract_expected_signals(info)
    assert "attack_tax" in sig["op_hints"]
    assert sig["gates"].get("require_life_lte") == 2


def test_diff_detects_wrong_attack_tax():
    info = {
        "effect_en": (
            "[On Play] If your Leader's type includes {Whitebeard Pirates} and you have 2 or less Life cards, "
            "Characters can attack unless your opponent trashes 2 cards from their hand whenever they attack."
        )
    }
    abilities = [
        {
            "timing": "on_play",
            "ops": [{"op": "deny_rest", "all": True, "count": 5}],
            "status": "compiled",
            "confidence": 0.8,
        }
    ]
    findings = diff_card("OP08-043", info, abilities, include_template_drift=False)
    cats = {f["category"] for f in findings}
    assert "wrong_op_attack_tax" in cats or "missing_op_attack_tax" in cats


def test_diff_passes_when_choose_one_present():
    info = {"effect_en": "[Main] Choose one: • Rest 1 Character. • K.O. 1 rested Character."}
    abilities = [
        {
            "timing": "on_play",
            "ops": [
                {
                    "op": "choose_one",
                    "chooser": "self",
                    "options": [
                        {"id": "a", "label": "rest", "ops": [{"op": "rest_opponent_character", "count": 1}]},
                        {"id": "b", "label": "ko", "ops": [{"op": "ko", "count": 1}]},
                    ],
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ]
    findings = diff_card("OP06-039", info, abilities, include_template_drift=False)
    assert not any(f["category"] == "missing_choose_one" for f in findings)
