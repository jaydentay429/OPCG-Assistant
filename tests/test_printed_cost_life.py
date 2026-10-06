"""Printed cost and life stay on the card type that actually prints them.

The official cardlist has one number box. Characters, events, and stages print
cost. Leaders print life. Sync must not copy that number into the other field.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sync_official_cards import (  # noqa: E402
    ParsedCard,
    is_leader_card_type,
    is_play_cost_card_type,
    merge_index,
)
from sync_preview_cards import merge_preview_card, parse_limitless_card_html  # noqa: E402

INDEX_PATH = ROOT / "index" / "cards_by_id.json"


def test_merge_index_character_stores_cost_and_clears_life():
    index = {
        "OP01-002": {
            "card_id": "OP01-002",
            "card_type": "Character",
            "category": "Character",
            "cost": 1,
            "life": 1,
            "name": "旧",
        }
    }
    official = ParsedCard(
        card_id="OP01-002",
        name="娜美",
        rarity="C",
        card_type="Character",
        fields={"life": "3", "effect": "效果", "power": "2000"},
    )
    row = merge_index(index, {"OP01-002": official}, "https://example.invalid/cardlist/")["OP01-002"]
    assert row["cost"] == 3
    assert row["life"] is None


def test_merge_index_leader_stores_life_and_clears_cost():
    index = {
        "OP01-001": {
            "card_id": "OP01-001",
            "card_type": "Leader",
            "category": "Leader",
            "cost": 5,
            "life": 5,
            "name": "旧",
        }
    }
    official = ParsedCard(
        card_id="OP01-001",
        name="索隆",
        rarity="L",
        card_type="Leader",
        fields={"life": "5", "effect": "效果", "power": "5000"},
    )
    row = merge_index(index, {"OP01-001": official}, "https://example.invalid/cardlist/")["OP01-001"]
    assert row["life"] == 5
    assert row["cost"] is None


def test_merge_index_event_zero_cost_clears_life():
    index = {
        "OP01-030": {
            "card_id": "OP01-030",
            "card_type": "Event",
            "cost": 2,
            "life": 2,
            "name": "旧",
        }
    }
    official = ParsedCard(
        card_id="OP01-030",
        name="事件",
        rarity="C",
        card_type="Event",
        fields={"life": "-", "effect": "效果"},
    )
    row = merge_index(index, {"OP01-030": official}, "https://example.invalid/cardlist/")["OP01-030"]
    assert row["cost"] == 0
    assert row["life"] is None


def test_preview_parse_keeps_only_the_printed_stat():
    character = parse_limitless_card_html(
        """
        <div class="card-text-name">Nami</div>
        <div class="card-text-type">Character Red 2 Cost 5 Life</div>
        <div class="card-text-section">4000 Power</div>
        """,
        "EB05-061",
    )
    assert character is not None
    assert character["cost"] == 2
    assert "life" not in character

    leader = parse_limitless_card_html(
        """
        <div class="card-text-name">Robin</div>
        <div class="card-text-type">Leader Green 4 Life 4 Cost</div>
        <div class="card-text-section">5000 Power</div>
        """,
        "EB05-010",
    )
    assert leader is not None
    assert leader["life"] == 4
    assert "cost" not in leader


def test_preview_merge_drops_stale_opposite_stat():
    character = merge_preview_card(
        {
            "card_id": "EB05-028",
            "card_type": "Character",
            "cost": 4,
            "life": 5,
            "preview": True,
        },
        {"card_id": "EB05-028", "name_en": "Boa Hancock"},
        "Heroines Edition vol.2【EB-05】",
    )
    assert character["cost"] == 4
    assert character["life"] is None

    leader = merge_preview_card(
        {
            "card_id": "EB05-010",
            "card_type": "Leader",
            "cost": 4,
            "life": 4,
            "preview": True,
        },
        {"card_id": "EB05-010", "name_en": "Nico Robin"},
        "Heroines Edition vol.2【EB-05】",
    )
    assert leader["life"] == 4
    assert leader["cost"] is None


def test_catalog_index_has_no_play_cost_life_or_leader_cost():
    cards = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    play_cost_with_life: list[str] = []
    leaders_with_cost: list[str] = []
    for cid, row in cards.items():
        if not isinstance(row, dict):
            continue
        parts = (row.get("card_type"), row.get("category"))
        if is_play_cost_card_type(*parts) and row.get("life") is not None:
            play_cost_with_life.append(cid)
        if is_leader_card_type(*parts) and row.get("cost") is not None:
            leaders_with_cost.append(cid)
    assert play_cost_with_life == []
    assert leaders_with_cost == []
    # Life that disagreed with cost was cleared; the stored cost stays.
    assert cards["EB05-028"]["life"] is None
    assert cards["EB05-028"]["cost"] == 4
    assert cards["EB05-028-P1"]["cost"] == 4
    assert cards["EB05-020"]["life"] is None
    assert cards["EB05-020"]["cost"] == 1
    assert cards["EB05-010"]["cost"] is None
    assert cards["EB05-010"]["life"] == 4
    assert cards["EB05-010-P2"]["cost"] is None
    assert cards["EB05-010-P2"]["life"] == 4
    assert cards["ST01-001"]["life"] == 5
    assert cards["ST01-001"]["cost"] is None


def test_card_api_hides_character_life_and_leader_cost():
    import app

    app.load_cards_index()
    character = app.build_card_response("EB05-028", app.cards_by_id["EB05-028"])
    assert character.life is None
    assert character.cost == 4
    leader = app.build_card_response("EB05-010", app.cards_by_id["EB05-010"])
    assert leader.life == 4
    assert leader.cost is None
    known = app.build_card_response("ST01-001", app.cards_by_id["ST01-001"])
    assert known.life == 5
    assert known.cost is None
