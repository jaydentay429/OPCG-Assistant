"""Screenshot cards are one row per id, and official sync replaces that row."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from manual_cards import apply_manual_cards, load_manual_cards, row_is_official  # noqa: E402
from sync_limited_variants import is_manual_catalog_row  # noqa: E402
from sync_official_cards import ParsedCard, merge_index  # noqa: E402


def test_seed_matches_index_and_ids_are_unique():
    cards = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    seed = load_manual_cards()
    assert set(seed) == {
        "EB05-046",
        "EB05-016",
        "EB05-016-P1",
        "OP18-112",
        "OP18-016",
        "OP18-025",
        "OP18-044",
        "OP18-069",
        "OP18-091",
        "OP18-111",
        "EB05-059",
        "EB05-008",
        "EB05-040",
        "P-160",
        "OP18-089",
        "OP18-076",
        "OP18-106",
        "EB05-049",
        "OP18-017",
        "OP18-024",
        "OP18-055",
        "OP18-011",
        "OP18-034",
        "OP18-046",
        "OP18-048",
        "OP18-084",
        "OP18-061",
        "OP18-100",
        "OP18-113",
        "EB05-030",
        "EB05-019",
        "EB05-004",
        "EB05-018",
        "EB05-043",
        "EB05-061",
        "EB05-031",
        "EB05-004-P1",
        "EB05-018-P1",
        "EB05-028-P1",
        "EB05-037-P1",
        "EB05-043-P1",
        "EB05-057-P1",
        "EB05-001-P1",
        "EB05-014-P2",
        "EB05-006-P1",
        "EB05-021-P1",
        "EB05-034-P1",
        "EB05-052-P1",
        "EB05-046-P1",
        "EB05-055-P1",
        "EB05-016-P2",
        "EB05-061-P1",
        "EB05-010-P2",
        "EB05-006-P2",
        "EB05-031-P1",
        "OP14-033-P3",
        "ST17-004-P3",
        "OP17-081-P1",
        "OP17-109-P1",
    }
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
    assert cards["OP18-044"]["name"] == "Mr.賓茲&Miss凱瑟蓮娜"
    assert cards["OP18-044"]["name_en"] == "Mr. Beans & Miss. Katherina"
    assert cards["OP18-044"]["manual_source"] == "screenshot"
    assert "suppress_pack_image" not in cards["OP18-044"]
    assert cards["OP18-044"]["img_url"] == ""
    assert cards["OP18-044"]["img_full_url"] == ""
    assert cards["OP18-044"]["preview"] is True
    assert cards["OP18-044"]["colors"] == ["藍"]
    assert cards["OP18-044"]["colors_en"] == ["Blue"]
    assert cards["OP18-044"]["cost"] == 3
    assert cards["OP18-044"]["power"] == 4000
    assert cards["OP18-044"]["counter"] == 1000
    assert cards["OP18-044"]["rarity"] == "C"
    assert cards["OP18-044"]["attributes"] == ["知"]
    assert cards["OP18-044"]["attributes_en"] == ["Wisdom"]
    assert cards["OP18-044"]["traits"] == ["B・W"]
    assert cards["OP18-044"]["traits_en"] == ["Baroque Works"]
    assert cards["OP18-044"]["card_type"] == "Character"
    assert cards["OP18-044"]["effect"].startswith("【咚‼×1】")
    assert "trash 1 card from your hand" in cards["OP18-044"]["effect_en"]
    assert cards["OP18-044"]["card_sets"] == ["補充包 OP-18【OP-18】"]
    assert cards["OP18-044"]["pack_id"] == "OP-18"
    assert cards["OP18-069"]["name"] == "索德姆&哥摩拉"
    assert cards["OP18-069"]["name_en"] == "Sodom & Gomorrah"
    assert cards["OP18-069"]["manual_source"] == "screenshot"
    assert "suppress_pack_image" not in cards["OP18-069"]
    assert cards["OP18-069"]["img_url"] == ""
    assert cards["OP18-069"]["img_full_url"] == ""
    assert cards["OP18-069"]["preview"] is True
    assert cards["OP18-069"]["colors"] == ["紫"]
    assert cards["OP18-069"]["colors_en"] == ["Purple"]
    assert cards["OP18-069"]["cost"] == 1
    assert cards["OP18-069"]["power"] == 2000
    assert cards["OP18-069"]["life"] is None
    assert cards["OP18-069"]["counter"] == 2000
    assert cards["OP18-069"]["rarity"] == "C"
    assert cards["OP18-069"]["attributes"] == ["打"]
    assert cards["OP18-069"]["attributes_en"] == ["Strike"]
    assert cards["OP18-069"]["traits"] == ["動物", "W7", "佛朗基一家"]
    assert cards["OP18-069"]["traits_en"] == ["Animal", "Water Seven", "Franky Family"]
    assert cards["OP18-069"]["card_type"] == "Character"
    assert cards["OP18-069"]["effect"] == (
        "若自己擁有《佛朗基一家》特徵的角色卡即將遭到KO時，可以替換成咚‼−1，並將這張角色卡置為休息狀態。"
    )
    assert cards["OP18-069"]["effect_en"] == (
        "If your {Franky Family} type Character would be K.O.'d, you may DON!! −1 and rest this Character instead."
    )
    assert cards["OP18-069"]["card_sets"] == ["補充包 OP-18【OP-18】"]
    assert cards["OP18-069"]["pack_id"] == "OP-18"
    assert cards["OP18-091"] == seed["OP18-091"]
    assert cards["OP18-091"]["name"] == "布洛基"
    assert cards["OP18-091"]["name_en"] == "Brogy"
    assert cards["OP18-091"]["colors"] == ["黑"]
    assert cards["OP18-091"]["cost"] == 4
    assert cards["OP18-091"]["power"] == 5000
    assert cards["OP18-091"]["counter"] == 2000
    assert cards["OP18-091"]["life"] is None
    assert cards["OP18-091"]["attributes"] == ["斬"]
    assert cards["OP18-091"]["traits"] == ["巨人族", "艾爾帕布", "巨兵海賊團"]
    assert cards["OP18-091"]["effect"].startswith("這張角色卡的費用+12。")
    assert "cost of 2 or less from your trash" in cards["OP18-091"]["effect_en"]
    assert cards["OP18-111"] == seed["OP18-111"]
    assert cards["OP18-111"]["name"] == "飛鼠"
    assert cards["OP18-111"]["name_en"] == "Momonga"
    assert cards["OP18-111"]["colors"] == ["黃"]
    assert cards["OP18-111"]["cost"] == 7
    assert cards["OP18-111"]["power"] == 7000
    assert cards["OP18-111"]["counter"] == 2000
    assert cards["OP18-111"]["traits"] == ["中將", "海軍"]
    assert cards["OP18-111"]["effect"].startswith("【速攻】")
    assert cards["OP18-111"]["effect_en"].startswith("[Rush]")
    assert cards["EB05-059"] == seed["EB05-059"]
    assert cards["EB05-059"]["name"] == "夏洛特・普琳!!"
    assert cards["EB05-059"]["name_en"] == "Charlotte Pudding!!"
    assert cards["EB05-059"]["card_type"] == "Event"
    assert cards["EB05-059"]["colors"] == ["黃"]
    assert cards["EB05-059"]["cost"] == 1
    assert cards["EB05-059"]["power"] is None
    assert cards["EB05-059"]["counter"] is None
    assert cards["EB05-059"]["rarity"] == "R"
    assert cards["EB05-059"]["traits"] == ["BIG MOM海賊團"]
    assert cards["EB05-059"]["effect"].startswith("【主要】抽1張卡片")
    assert "{Big Mom Pirates}" in cards["EB05-059"]["effect_en"]
    assert cards["EB05-008"] == seed["EB05-008"]
    assert cards["EB05-008"]["name"] == "魯夫，就是現在"
    assert cards["EB05-008"]["name_en"] == "Luffy, Now's Your Chance"
    assert cards["EB05-008"]["card_type"] == "Event"
    assert cards["EB05-008"]["colors"] == ["紅"]
    assert cards["EB05-008"]["cost"] == 1
    assert cards["EB05-008"]["rarity"] == "C"
    assert cards["EB05-008"]["traits"] == ["王下七武海", "九蛇海賊團"]
    assert "力量值-7000" in cards["EB05-008"]["effect"]
    assert "−7000 power" in cards["EB05-008"]["effect_en"]
    assert cards["EB05-040"] == seed["EB05-040"]
    assert cards["EB05-040"]["name"] == "你需要我吧？！！♡"
    assert cards["EB05-040"]["name_en"] == "You Need Me, Don't You?!!♡"
    assert cards["EB05-040"]["card_type"] == "Event"
    assert cards["EB05-040"]["colors"] == ["紫"]
    assert cards["EB05-040"]["cost"] == 0
    assert cards["EB05-040"]["rarity"] == "R"
    assert cards["EB05-040"]["traits"] == ["唐吉訶德海賊團"]
    assert cards["EB05-040"]["effect"].startswith("【主要】可以將1張自己活動狀態的咚‼卡放回咚‼卡組")
    assert "draw 3 cards" in cards["EB05-040"]["effect_en"]
    for cid in ("OP18-091", "OP18-111", "EB05-059", "EB05-008", "EB05-040"):
        assert cards[cid]["manual_source"] == "screenshot"
        assert cards[cid]["preview"] is True
        assert cards[cid]["img_url"] == ""
        assert cards[cid]["img_full_url"] == ""
        assert "suppress_pack_image" not in cards[cid]
        assert cards[cid]["life"] is None
    assert cards["P-160"]["name"] == "納菲魯塔利・薇薇"
    assert cards["P-160"]["name_en"] == "Nefeltari Vivi"
    assert cards["P-160"]["manual_source"] == "screenshot"
    assert "suppress_pack_image" not in cards["P-160"]
    assert cards["P-160"]["img_url"] == ""
    assert cards["P-160"]["img_full_url"] == ""
    assert cards["P-160"]["preview"] is True
    assert cards["P-160"]["colors"] == ["黃"]
    assert cards["P-160"]["colors_en"] == ["Yellow"]
    assert cards["P-160"]["cost"] == 3
    assert cards["P-160"]["power"] == 4000
    assert cards["P-160"]["counter"] == 1000
    assert cards["P-160"]["rarity"] == "P"
    assert cards["P-160"]["attributes"] == ["知"]
    assert cards["P-160"]["attributes_en"] == ["Wisdom"]
    assert cards["P-160"]["traits"] == ["阿拉巴斯坦王國"]
    assert cards["P-160"]["traits_en"] == ["Alabasta"]
    assert cards["P-160"]["card_type"] == "Character"
    assert "持有屬性（知）" in cards["P-160"]["effect"]
    assert cards["P-160"]["trigger"].startswith("【觸發器】")
    assert "2 or less Life cards" in cards["P-160"]["effect_en"]
    assert cards["P-160"]["card_sets"] == ["推廣卡【P】"]
    assert cards["P-160"]["pack_id"] == "P"
    assert cards["OP18-089"]["name"] == "多利"
    assert cards["OP18-089"]["name_en"] == "Dorry"
    assert cards["OP18-089"]["manual_source"] == "screenshot"
    assert "suppress_pack_image" not in cards["OP18-089"]
    assert cards["OP18-089"]["preview"] is True
    assert cards["OP18-089"]["colors"] == ["黑"]
    assert cards["OP18-089"]["colors_en"] == ["Black"]
    assert cards["OP18-089"]["cost"] == 4
    assert cards["OP18-089"]["power"] == 5000
    assert cards["OP18-089"]["counter"] == 2000
    assert cards["OP18-089"]["rarity"] == "C"
    assert cards["OP18-089"]["attributes"] == ["斬"]
    assert cards["OP18-089"]["attributes_en"] == ["Slash"]
    assert cards["OP18-089"]["traits"] == ["巨人族", "艾爾帕布", "巨兵海賊團"]
    assert cards["OP18-089"]["traits_en"] == ["Giant", "Elbaph", "Giant Pirates"]
    assert cards["OP18-089"]["effect"].startswith("這張角色卡的費用+12。")
    assert "trashes 1 card from their hand" in cards["OP18-089"]["effect_en"]
    assert cards["OP18-089"]["card_sets"] == ["補充包 OP-18【OP-18】"]
    assert cards["OP18-089"]["pack_id"] == "OP-18"
    assert cards["OP18-076"]["name"] == "鯊魚潛水3號"
    assert cards["OP18-076"]["name_en"] == "Shark Submerge No.3"
    assert cards["OP18-076"]["manual_source"] == "screenshot"
    assert "suppress_pack_image" not in cards["OP18-076"]
    assert cards["OP18-076"]["preview"] is True
    assert cards["OP18-076"]["card_type"] == "Stage"
    assert cards["OP18-076"]["colors"] == ["紫"]
    assert cards["OP18-076"]["colors_en"] == ["Purple"]
    assert cards["OP18-076"]["cost"] == 5
    assert cards["OP18-076"]["power"] is None
    assert cards["OP18-076"]["counter"] is None
    assert cards["OP18-076"]["rarity"] == "UC"
    assert cards["OP18-076"]["attributes"] == ["-"]
    assert cards["OP18-076"]["traits"] == ["草帽一行人"]
    assert cards["OP18-076"]["traits_en"] == ["Straw Hat Crew"]
    assert "咚‼" in cards["OP18-076"]["effect"]
    assert "during this turn" in cards["OP18-076"]["effect_en"]
    assert cards["OP18-076"]["card_sets"] == ["補充包 OP-18【OP-18】"]
    assert cards["OP18-076"]["pack_id"] == "OP-18"
    assert cards["OP18-106"]["name"] == "鬥犬"
    assert cards["OP18-106"]["name_en"] == "Doberman"
    assert cards["OP18-106"]["manual_source"] == "screenshot"
    assert "suppress_pack_image" not in cards["OP18-106"]
    assert cards["OP18-106"]["preview"] is True
    assert cards["OP18-106"]["colors"] == ["黃"]
    assert cards["OP18-106"]["colors_en"] == ["Yellow"]
    assert cards["OP18-106"]["cost"] == 7
    assert cards["OP18-106"]["power"] == 7000
    assert cards["OP18-106"]["counter"] == 2000
    assert cards["OP18-106"]["rarity"] == "C"
    assert cards["OP18-106"]["attributes"] == ["斬"]
    assert cards["OP18-106"]["attributes_en"] == ["Slash"]
    assert cards["OP18-106"]["traits"] == ["中將", "海軍"]
    assert cards["OP18-106"]["traits_en"] == ["Vice Admiral", "Navy"]
    assert cards["OP18-106"]["effect"].startswith("【雙重攻擊】")
    assert "This card deals 2 damage." in cards["OP18-106"]["effect_en"]
    assert cards["OP18-106"]["card_sets"] == ["補充包 OP-18【OP-18】"]
    assert cards["OP18-106"]["pack_id"] == "OP-18"
    assert cards["EB05-049"]["name"] == "特別鬼魂"
    assert cards["EB05-049"]["name_en"] == "Special Hollow"
    assert cards["EB05-049"]["manual_source"] == "screenshot"
    assert "suppress_pack_image" not in cards["EB05-049"]
    assert cards["EB05-049"]["preview"] is True
    assert cards["EB05-049"]["card_type"] == "Event"
    assert cards["EB05-049"]["colors"] == ["黑"]
    assert cards["EB05-049"]["colors_en"] == ["Black"]
    assert cards["EB05-049"]["cost"] == 1
    assert cards["EB05-049"]["power"] is None
    assert cards["EB05-049"]["counter"] is None
    assert cards["EB05-049"]["rarity"] == "C"
    assert cards["EB05-049"]["traits"] == ["恐怖三桅帆船海賊團"]
    assert cards["EB05-049"]["traits_en"] == ["Thriller Bark Pirates"]
    assert "費用-3" in cards["EB05-049"]["effect"]
    assert "{Thriller Bark Pirates}" in cards["EB05-049"]["effect_en"]
    assert cards["EB05-049"]["card_sets"] == ["Heroines Edition vol.2【EB-05】"]
    assert cards["EB05-049"]["pack_id"] == "EB-05"
    assert cards["OP18-046"]["name"] == "Mr.0&Miss All星期天"
    assert cards["OP18-046"]["name_en"] == "Mr.0 & Miss All Sunday"
    assert cards["OP18-046"]["counter"] is None
    assert cards["OP18-046"]["attributes"] == ["特", "知"]
    assert cards["OP18-046"]["life"] is None
    assert cards["OP18-046"]["img_url"] == ""
    assert cards["EB05-061"]["name"] == "娜美"
    assert cards["EB05-061"]["rarity"] == "SEC"
    assert cards["EB05-061"]["img_url"] == ""
    assert cards["EB05-061"]["life"] is None
    assert cards["EB05-031"]["traits"] == ["賓什莫克家", "杰爾馬66"]
    assert cards["EB05-031"]["traits_en"] == ["The Vinsmoke Family", "GERMA 66"]
    assert cards["EB05-004"]["img_url"] == ""
    assert "EB05-004-P1" not in cards["EB05-004"]["img_url"]
    p_nami = cards["EB05-061-P1"]
    assert p_nami["rarity"] == "SEC"
    assert p_nami["name"] == cards["EB05-061"]["name"]
    assert p_nami["effect"] == cards["EB05-061"]["effect"]
    assert p_nami["card_sets"] == cards["EB05-061"]["card_sets"]
    assert p_nami["img_url"] == ""
    pudding = cards["OP17-109-P1"]
    assert pudding["name"] == "夏洛特・普琳"
    assert pudding["name_en"] == "Charlotte Pudding"
    assert pudding["rarity"] == "SP"
    assert pudding["effect"] == cards["OP17-109"]["effect"]
    assert pudding["card_sets"] == cards["OP17-109"]["card_sets"]
    assert pudding["manual_source"] == "screenshot"
    assert cards["EB05-006-P2"]["rarity"] == "SP"
    assert cards["EB05-006-P2"]["effect"] == cards["EB05-006"]["effect"]
    assert cards["EB05-016-P2"]["rarity"] == "SR"
    assert cards["EB05-016-P2"]["effect"] == cards["EB05-016"]["effect"]
    assert cards["EB05-010-P2"]["rarity"] == "L"
    assert cards["EB05-014-P1"]["rarity"] == "SP"
    assert cards["OP14-033-P1"]["rarity"] == "SR"
    assert cards["OP14-033-P2"]["img_url"] == "images/cardlist/card/OP14-033_p2.png"
    assert "manual_source" not in cards["OP14-033-P1"]
    assert cards["OP18-065"]["counter"] is None
    assert cards["OP18-065"]["attributes"] == ["？"]
    assert cards["OP18-065"]["attributes_en"] == ["Unknown"]
    assert cards["OP18-065"]["img_url"] == "https://api.optcgassistant.com/packs/OP18-065.png"
    assert cards["OP18-031"]["img_url"] == "https://api.optcgassistant.com/packs/OP18-031.png"
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
    assert list(cards).count("OP18-044") == 1
    assert list(cards).count("OP18-069") == 1
    assert list(cards).count("OP18-091") == 1
    assert list(cards).count("OP18-111") == 1
    assert list(cards).count("EB05-059") == 1
    assert list(cards).count("EB05-008") == 1
    assert list(cards).count("EB05-040") == 1
    assert list(cards).count("P-160") == 1
    assert list(cards).count("OP18-089") == 1
    assert list(cards).count("OP18-076") == 1
    assert list(cards).count("OP18-106") == 1
    assert list(cards).count("EB05-049") == 1
    overrides = json.loads((ROOT / "index" / "card_effect_overrides.json").read_text(encoding="utf-8"))
    # New cards are catalog-only. Hedgehog keeps the rekeyed encoding, nothing new.
    assert "EB05-046" not in overrides["cards"]
    assert "OP18-112" not in overrides["cards"]
    assert "OP18-016" not in overrides["cards"]
    assert "OP18-025" not in overrides["cards"]
    assert "OP18-044" not in overrides["cards"]
    assert "OP18-069" not in overrides["cards"]
    assert "OP18-091" not in overrides["cards"]
    assert "OP18-111" not in overrides["cards"]
    assert "EB05-059" not in overrides["cards"]
    assert "EB05-008" not in overrides["cards"]
    assert "EB05-040" not in overrides["cards"]
    assert "P-160" not in overrides["cards"]
    assert "OP18-089" not in overrides["cards"]
    assert "OP18-076" not in overrides["cards"]
    assert "OP18-106" not in overrides["cards"]
    assert "EB05-049" not in overrides["cards"]
    assert "EB05-016-P1" not in overrides["cards"]
    assert overrides["cards"]["EB05-016"]["card_id"] == "EB05-016"
    assert overrides["cards"]["EB05-048"]["card_id"] == "EB05-048"
    hog_timings = {a["timing"] for a in overrides["cards"]["EB05-048"]["abilities"]}
    assert hog_timings == {"on_play", "counter_event"}


def test_official_sync_overwrites_screenshot_row_without_duplicates():
    index: dict = {}
    assert apply_manual_cards(index) == 59
    assert apply_manual_cards(index) == 59
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
    assert merged["OP18-044"]["name"] == "Mr.賓茲&Miss凱瑟蓮娜"
    assert merged["OP18-044"]["manual_source"] == "screenshot"
    assert list(merged).count("OP18-044") == 1
    assert merged["OP18-069"]["name"] == "索德姆&哥摩拉"
    assert merged["OP18-069"]["manual_source"] == "screenshot"
    assert list(merged).count("OP18-069") == 1
    assert merged["OP18-091"]["name"] == "布洛基"
    assert merged["OP18-111"]["name"] == "飛鼠"
    assert merged["EB05-059"]["name"] == "夏洛特・普琳!!"
    assert merged["EB05-008"]["name"] == "魯夫，就是現在"
    assert merged["EB05-040"]["name"] == "你需要我吧？！！♡"
    for cid in ("OP18-091", "OP18-111", "EB05-059", "EB05-008", "EB05-040"):
        assert merged[cid]["manual_source"] == "screenshot"
        assert list(merged).count(cid) == 1
    assert merged["P-160"]["name"] == "納菲魯塔利・薇薇"
    assert merged["P-160"]["manual_source"] == "screenshot"
    assert list(merged).count("P-160") == 1
    assert merged["OP18-089"]["name"] == "多利"
    assert merged["OP18-089"]["manual_source"] == "screenshot"
    assert list(merged).count("OP18-089") == 1
    assert merged["OP18-076"]["name"] == "鯊魚潛水3號"
    assert merged["OP18-076"]["manual_source"] == "screenshot"
    assert list(merged).count("OP18-076") == 1
    assert merged["OP18-106"]["name"] == "鬥犬"
    assert merged["OP18-106"]["manual_source"] == "screenshot"
    assert list(merged).count("OP18-106") == 1
    assert merged["EB05-049"]["name"] == "特別鬼魂"
    assert merged["EB05-049"]["manual_source"] == "screenshot"
    assert list(merged).count("EB05-049") == 1
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


def test_limited_sync_keeps_manual_rows():
    assert is_manual_catalog_row({"manual_source": "screenshot", "name": "娜美"}) is True
    assert is_manual_catalog_row({"name": "官方", "effect": "效果"}) is False
    assert is_manual_catalog_row(None) is False


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
