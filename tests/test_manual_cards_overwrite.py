"""Screenshot cards are one row per id, and official sync replaces that row."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from manual_cards import apply_manual_cards, load_manual_cards, row_is_official  # noqa: E402
from sync_official_cards import ParsedCard, merge_index  # noqa: E402


def test_seed_matches_index_and_ids_are_unique():
    cards = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    seed = load_manual_cards()
    assert set(seed) == {"EB05-046", "OP18-112"}
    assert cards["EB05-046"]["name"] == "大和"
    assert cards["EB05-046"]["name_en"] == "Yamato"
    assert cards["EB05-046"]["manual_source"] == "screenshot"
    assert "suppress_pack_image" not in cards["EB05-046"]
    assert cards["EB05-046"]["img_url"] == ""
    assert cards["EB05-046"]["img_full_url"] == ""
    assert "EB05-046.png" not in json.dumps(cards["EB05-046"])
    assert cards["EB05-046"]["preview"] is True
    assert cards["EB05-048"]["name"] == "刺針刺蝟"
    assert cards["EB05-048"]["name_en"] == "Stinger Hedgehog"
    assert cards["EB05-048"]["card_id"] == "EB05-048"
    assert cards["EB05-048"]["card_type"] == "Event"
    assert cards["EB05-048"]["rarity"] == "R"
    assert cards["EB05-048"]["img_url"].endswith("/EB05-048.png")
    assert cards["EB05-048"]["img_full_url"].endswith("/EB05-048.png")
    assert "EB05-046" not in cards["EB05-048"]["img_url"]
    assert cards["EB05-007"]["colors"] == ["紅"]
    assert cards["EB05-007"]["colors_en"] == ["Red"]
    assert cards["EB05-047"]["colors"] == ["黑"]
    assert cards["EB05-047"]["colors_en"] == ["Black"]
    assert cards["EB05-009"]["rarity"] == "R"
    assert cards["EB05-029"]["rarity"] == "C"
    assert cards["OP18-112"]["name"] == "火燒山"
    assert cards["OP18-112"]["manual_source"] == "screenshot"
    assert list(cards).count("EB05-046") == 1
    assert list(cards).count("EB05-048") == 1
    assert list(cards).count("OP18-112") == 1
    overrides = json.loads((ROOT / "index" / "card_effect_overrides.json").read_text(encoding="utf-8"))
    # New cards are catalog-only. Hedgehog keeps the rekeyed encoding, nothing new.
    assert "EB05-046" not in overrides["cards"]
    assert "OP18-112" not in overrides["cards"]
    assert overrides["cards"]["EB05-048"]["card_id"] == "EB05-048"
    hog_timings = {a["timing"] for a in overrides["cards"]["EB05-048"]["abilities"]}
    assert hog_timings == {"on_play", "counter_event"}


def test_official_sync_overwrites_screenshot_row_without_duplicates():
    index: dict = {}
    assert apply_manual_cards(index) == 2
    assert apply_manual_cards(index) == 2
    assert list(index).count("EB05-046") == 1
    assert index["EB05-046"]["name"] == "大和"

    official = ParsedCard(
        card_id="EB05-046",
        name="官方大和",
        rarity="SR",
        card_type="Character",
        fields={
            "effect": "官方效果",
            "power": "5000",
            "color": "黑",
            "attribute": "打",
            "type": "和之國",
        },
        card_sets=["Heroines Edition vol.2【EB-05】"],
    )
    merged = merge_index(index, {"EB05-046": official}, "https://example.invalid/cardlist/")
    row = merged["EB05-046"]
    assert row["name"] == "官方大和"
    assert row["effect"] == "官方效果"
    assert "preview" not in row
    assert "manual_source" not in row
    assert not row.get("suppress_pack_image")
    assert list(merged).count("EB05-046") == 1
    assert row_is_official(row) is True

    apply_manual_cards(merged)
    assert merged["EB05-046"]["name"] == "官方大和"
    assert merged["EB05-046"].get("manual_source") is None
    assert list(merged).count("EB05-046") == 1
    # The other screenshot card was not on the official list, so it remains.
    assert merged["OP18-112"]["name"] == "火燒山"
    assert merged["OP18-112"]["manual_source"] == "screenshot"
    assert list(merged).count("OP18-112") == 1


def test_apply_does_not_replace_an_existing_official_card():
    index = {
        "OP18-112": {
            "card_id": "OP18-112",
            "name": "官方火燒山",
            "effect": "官方",
            "card_type": "Character",
        }
    }
    assert apply_manual_cards(index, {"OP18-112": {"name": "火燒山", "manual_source": "screenshot"}}) == 0
    assert index["OP18-112"]["name"] == "官方火燒山"
    assert "manual_source" not in index["OP18-112"]
