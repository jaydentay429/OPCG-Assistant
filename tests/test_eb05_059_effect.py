"""EB05-059 keeps the trigger on its own fields.

The manual row already stores the main text in effect / effect_en and the
trigger line in trigger / trigger_en. /cards/EB05-059 must not append that
line back onto the effect fields.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402


def test_eb05_059_api_effect_omits_trigger_line():
    app.load_cards_index()
    basic = app.cards_by_id["EB05-059"]
    card = app.build_card_response("EB05-059", basic)

    assert card.trigger.startswith("【觸發器】")
    assert "持有【觸發器】" in card.trigger
    assert card.trigger_en.startswith("[Trigger]")
    assert "[Trigger]" in card.trigger_en

    effect = card.effect or ""
    effect_en = card.effect_en or ""
    assert effect == basic["effect"]
    assert effect_en == basic["effect_en"]
    assert effect.startswith("【主要】抽1張卡片")
    assert "【觸發器】" not in effect
    assert not effect.endswith(card.trigger)
    assert "{Big Mom Pirates}" in effect_en
    assert "[Trigger]" not in effect_en
    assert not effect_en.endswith(card.trigger_en)


def test_st22_016_api_effect_omits_split_trigger_line():
    """Official rows may repeat the trigger inside effect_en. The API still splits it."""
    app.load_cards_index()
    basic = app.cards_by_id["ST22-016"]
    assert "[Trigger]" in basic["effect_en"]
    assert basic["trigger_en"].startswith("[Trigger]")
    card = app.build_card_response("ST22-016", basic)

    assert card.trigger.startswith("【觸發器】")
    assert card.trigger_en == "[Trigger] Draw 1 card."
    effect = card.effect or ""
    effect_en = card.effect_en or ""
    assert effect.startswith("【反擊】")
    assert "【觸發器】" not in effect
    assert effect_en.startswith("[Counter]")
    assert "[Trigger]" not in effect_en
    assert "Draw 1 card." not in effect_en
    assert not effect.endswith(card.trigger)
    assert not effect_en.endswith(card.trigger_en)


def test_strip_split_trigger_keeps_midline_trigger_property():
    body = "【主要】使持有【觸發器】的角色卡登場。"
    assert app._strip_split_trigger(body, "【觸發器】抽1張卡片。") == body
    english = '[Main] Play up to 1 card with a [Trigger] from your hand.'
    assert app._strip_split_trigger(english, "[Trigger] Draw 1 card.") == english
    combined = "[Counter] Draw 1.\n[Trigger] Draw 1 card."
    assert app._strip_split_trigger(combined, "[Trigger] Draw 1 card.") == "[Counter] Draw 1."
