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
    assert set(seed) == {"EB05-046", "EB05-016", "EB05-016-P1", "OP18-112", "OP18-016", "OP18-025"}
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
    assert cards["OP18-016"]["name"] == "蒙其・D・魯夫"
    assert cards["OP18-016"]["name_en"] == "Monkey.D.Luffy"
    assert cards["OP18-016"]["manual_source"] == "screenshot"
    assert "suppress_pack_image" not in cards["OP18-016"]
    assert cards["OP18-016"]["img_url"] == ""
    assert cards["OP18-016"]["img_full_url"] == ""
    assert cards["OP18-016"]["preview"] is True
    assert cards["OP18-016"]["colors"] == ["紅"]
    assert cards["OP18-016"]["colors_en"] == ["Red"]
    assert cards["OP18-016"]["cost"] == 6
    assert cards["OP18-016"]["power"] == 7000
    assert cards["OP18-016"]["counter"] == 1000
    assert cards["OP18-016"]["rarity"] == "C"
    assert cards["OP18-016"]["attributes"] == ["打"]
    assert cards["OP18-016"]["attributes_en"] == ["Strike"]
    assert cards["OP18-016"]["traits"] == ["阿拉巴斯坦王國", "草帽一行人"]
    assert cards["OP18-016"]["traits_en"] == ["Alabasta", "Straw Hat Crew"]
    assert cards["OP18-016"]["card_sets"] == ["補充包 OP-18【OP-18】"]
    assert cards["OP18-016"]["pack_id"] == "OP-18"
    assert cards["OP18-025"]["name"] == "貢貝"
    assert cards["OP18-025"]["name_en"] == "Gonbe"
    assert cards["OP18-025"]["manual_source"] == "screenshot"
    assert "suppress_pack_image" not in cards["OP18-025"]
    assert cards["OP18-025"]["img_url"] == ""
    assert cards["OP18-025"]["img_full_url"] == ""
    assert cards["OP18-025"]["preview"] is True
    assert cards["OP18-025"]["colors"] == ["綠"]
    assert cards["OP18-025"]["colors_en"] == ["Green"]
    assert cards["OP18-025"]["cost"] == 1
    assert cards["OP18-025"]["power"] == 0
    assert cards["OP18-025"]["counter"] == 1000
    assert cards["OP18-025"]["rarity"] == "C"
    assert cards["OP18-025"]["attributes"] == ["知"]
    assert cards["OP18-025"]["attributes_en"] == ["Wisdom"]
    assert cards["OP18-025"]["traits"] == ["動物", "W7"]
    assert cards["OP18-025"]["traits_en"] == ["Animal", "Water Seven"]
    assert cards["OP18-025"]["card_type"] == "Character"
    assert cards["OP18-025"]["effect"].startswith("【我方回合結束時】")
    assert "rested" in cards["OP18-025"]["effect_en"]
    assert cards["OP18-025"]["card_sets"] == ["補充包 OP-18【OP-18】"]
    assert cards["OP18-025"]["pack_id"] == "OP-18"
    # Base id stays EB05-016. The stored SP row was the heroine parallel art;
    # the normal printing is SR, and EB05-016-P1 keeps the SP mark used by other -P1 rows.
    assert cards["EB05-016"]["card_id"] == "EB05-016"
    assert cards["EB05-016"]["name"] == "妮可・羅賓"
    assert cards["EB05-016"]["name_en"] == "Nico Robin"
    assert cards["EB05-016"]["rarity"] == "SR"
    assert cards["EB05-016"]["attributes"] == ["知"]
    assert cards["EB05-016"]["manual_source"] == "screenshot"
    assert "suppress_pack_image" not in cards["EB05-016"]
    assert cards["EB05-016"]["img_url"] == ""
    assert cards["EB05-016"]["card_sets"] == ["Heroines Edition vol.2【EB-05】"]
    p1 = cards["EB05-016-P1"]
    assert p1["card_id"] == "EB05-016-P1"
    assert p1["name"] == cards["EB05-016"]["name"]
    assert p1["name_en"] == cards["EB05-016"]["name_en"]
    assert p1["effect"] == cards["EB05-016"]["effect"]
    assert p1["effect_en"] == cards["EB05-016"]["effect_en"]
    assert p1["cost"] == 6 and p1["power"] == 6000 and p1["counter"] == 1000
    assert p1["rarity"] == "SP"
    assert p1["manual_source"] == "screenshot"
    assert "suppress_pack_image" not in p1
    assert "(異圖卡)" not in p1["name"]
    assert list(cards).count("EB05-016") == 1
    assert list(cards).count("EB05-016-P1") == 1
    assert list(cards).count("EB05-046") == 1
    assert list(cards).count("EB05-048") == 1
    assert list(cards).count("OP18-112") == 1
    assert list(cards).count("OP18-016") == 1
    assert list(cards).count("OP18-025") == 1
    overrides = json.loads((ROOT / "index" / "card_effect_overrides.json").read_text(encoding="utf-8"))
    # New cards are catalog-only. Hedgehog keeps the rekeyed encoding, nothing new.
    assert "EB05-046" not in overrides["cards"]
    assert "OP18-112" not in overrides["cards"]
    assert "OP18-016" not in overrides["cards"]
    assert "OP18-025" not in overrides["cards"]
    assert "EB05-016-P1" not in overrides["cards"]
    assert overrides["cards"]["EB05-016"]["card_id"] == "EB05-016"
    assert overrides["cards"]["EB05-048"]["card_id"] == "EB05-048"
    hog_timings = {a["timing"] for a in overrides["cards"]["EB05-048"]["abilities"]}
    assert hog_timings == {"on_play", "counter_event"}


def test_official_sync_overwrites_screenshot_row_without_duplicates():
    index: dict = {}
    assert apply_manual_cards(index) == 6
    assert apply_manual_cards(index) == 6
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
    assert merged["OP18-016"]["name"] == "蒙其・D・魯夫"
    assert merged["OP18-016"]["manual_source"] == "screenshot"
    assert "suppress_pack_image" not in merged["OP18-016"]
    assert list(merged).count("OP18-016") == 1
    assert merged["OP18-025"]["name"] == "貢貝"
    assert merged["OP18-025"]["manual_source"] == "screenshot"
    assert list(merged).count("OP18-025") == 1
    assert merged["EB05-016"]["rarity"] == "SR"
    assert merged["EB05-016-P1"]["rarity"] == "SP"

    official_robin = {
        "EB05-016": ParsedCard(
            card_id="EB05-016",
            name="官方羅賓",
            rarity="SR",
            card_type="Character",
            fields={"effect": "官方效果", "power": "6000", "color": "綠", "attribute": "知", "type": "草帽一行人"},
            card_sets=["Heroines Edition vol.2【EB-05】"],
        ),
        "EB05-016-P1": ParsedCard(
            card_id="EB05-016-P1",
            name="官方羅賓異畫",
            rarity="SP",
            card_type="Character",
            fields={"effect": "官方異畫效果", "power": "6000", "color": "綠", "attribute": "知", "type": "草帽一行人"},
            card_sets=["Heroines Edition vol.2【EB-05】"],
        ),
    }
    merged = merge_index(merged, official_robin, "https://example.invalid/cardlist/")
    assert merged["EB05-016"]["name"] == "官方羅賓"
    assert merged["EB05-016"]["card_id"] == "EB05-016"
    assert "preview" not in merged["EB05-016"]
    assert "manual_source" not in merged["EB05-016"]
    assert merged["EB05-016-P1"]["name"] == "官方羅賓異畫"
    assert "manual_source" not in merged["EB05-016-P1"]
    apply_manual_cards(merged)
    assert merged["EB05-016"]["name"] == "官方羅賓"
    assert merged["EB05-016-P1"]["name"] == "官方羅賓異畫"
    assert merged["OP18-016"]["manual_source"] == "screenshot"
    assert list(merged).count("EB05-016") == 1
    assert list(merged).count("EB05-016-P1") == 1


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
