"""Normalize topdecks facet values for country / host / tournament / placement."""

from __future__ import annotations

import re
from typing import Any

_PAREN_RE = re.compile(r"\([^)]*\)")
_SPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def strip_parens(text: str) -> str:
    s = _PAREN_RE.sub(" ", str(text or ""))
    return _SPACE_RE.sub(" ", s).strip()


def _compact(text: str) -> str:
    return _NON_ALNUM_RE.sub("", strip_parens(text).lower())


# --- country -----------------------------------------------------------------

# raw (lower/stripped) -> canonical key
_COUNTRY_ALIASES: dict[str, str] = {
    "jp": "japan",
    "japan": "japan",
    "us": "usa",
    "usa": "usa",
    "unitedstate": "usa",
    "unitedstates": "usa",
    "na": "north_america",
    "northamerica": "north_america",
    "northameria": "north_america",
    "eu": "europe",
    "europe": "europe",
    "oce": "oceania",
    "oceania": "oceania",
    "aus": "australia",
    "australia": "australia",
    "nz": "new_zealand",
    "newzealand": "new_zealand",
    "uk": "uk",
    "gb": "uk",
    "greatbritain": "uk",
    "britain": "uk",
    "unitedkingdom": "uk",
    "england": "uk",
    "englanduk": "uk",
    "sg": "singapore",
    "singapore": "singapore",
    "sinagpore": "singapore",
    "ph": "philippines",
    "philippines": "philippines",
    "philipines": "philippines",
    "mys": "malaysia",
    "malaysia": "malaysia",
    "hk": "hong_kong",
    "hongkong": "hong_kong",
    "hong kong": "hong_kong",
    "latam": "latam",
    "latinamerica": "latam",
    "latin america": "latam",
    "kr": "korea",
    "korea": "korea",
    "southkorea": "korea",
    "vn": "vietnam",
    "vietnam": "vietnam",
    "italia": "italy",
    "itali": "italy",
    "italy": "italy",
    "brasil": "brazil",
    "brazil": "brazil",
    "gemany": "germany",
    "germany": "germany",
    "neitherlands": "netherlands",
    "netherlands": "netherlands",
    "switzeland": "switzerland",
    "switzerland": "switzerland",
    "turkiye": "turkey",
    "turkey": "turkey",
    "taiwan": "taiwan",
    "china": "china",
    "thailand": "thailand",
    "indonesia": "indonesia",
    "mexico": "mexico",
    "argentina": "argentina",
    "chile": "chile",
    "canada": "canada",
    "belgium": "belgium",
    "france": "france",
    "spain": "spain",
    "portugal": "portugal",
    "panama": "panama",
    "brunei": "brunei",
    "puertorico": "puerto_rico",
    "poland": "poland",
    "costarica": "costa_rica",
    "peru": "peru",
    "kuwait": "kuwait",
    "greece": "greece",
    "ecuador": "ecuador",
    "dominicanrepublic": "dominican_republic",
    "hungary": "hungary",
    "croatia": "croatia",
    "asia": "asia",
    "southeastasia": "southeast_asia",
    "bulgaria": "bulgaria",
    "austria": "austria",
    "israel": "israel",
    "slovakia": "slovakia",
    "lithuania": "lithuania",
    "sweden": "sweden",
    "southafrica": "south_africa",
    "ukraine": "ukraine",
    "luxembourg": "luxembourg",
    "denmark": "denmark",
    "venezuela": "venezuela",
    "slovenia": "slovenia",
    "colombia": "colombia",
    "uruguay": "uruguay",
    "norway": "norway",
    "nicaragua": "nicaragua",
    "guatemala": "guatemala",
    "finland": "finland",
    "saudiarabia": "saudi_arabia",
    "czechrepublic": "czech_republic",
}

_COUNTRY_LABELS: dict[str, dict[str, str]] = {
    "japan": {"en": "Japan", "zh-Hans": "日本", "zh-Hant": "日本"},
    "usa": {"en": "United States", "zh-Hans": "美国", "zh-Hant": "美國"},
    "north_america": {"en": "North America", "zh-Hans": "北美", "zh-Hant": "北美"},
    "europe": {"en": "Europe", "zh-Hans": "欧洲", "zh-Hant": "歐洲"},
    "oceania": {"en": "Oceania", "zh-Hans": "大洋洲", "zh-Hant": "大洋洲"},
    "australia": {"en": "Australia", "zh-Hans": "澳大利亚", "zh-Hant": "澳洲"},
    "new_zealand": {"en": "New Zealand", "zh-Hans": "新西兰", "zh-Hant": "紐西蘭"},
    "uk": {"en": "United Kingdom", "zh-Hans": "英国", "zh-Hant": "英國"},
    "singapore": {"en": "Singapore", "zh-Hans": "新加坡", "zh-Hant": "新加坡"},
    "philippines": {"en": "Philippines", "zh-Hans": "菲律宾", "zh-Hant": "菲律賓"},
    "malaysia": {"en": "Malaysia", "zh-Hans": "马来西亚", "zh-Hant": "馬來西亞"},
    "hong_kong": {"en": "Hong Kong", "zh-Hans": "香港", "zh-Hant": "香港"},
    "latam": {"en": "Latin America", "zh-Hans": "拉丁美洲", "zh-Hant": "拉丁美洲"},
    "korea": {"en": "Korea", "zh-Hans": "韩国", "zh-Hant": "韓國"},
    "vietnam": {"en": "Vietnam", "zh-Hans": "越南", "zh-Hant": "越南"},
    "italy": {"en": "Italy", "zh-Hans": "意大利", "zh-Hant": "意大利"},
    "brazil": {"en": "Brazil", "zh-Hans": "巴西", "zh-Hant": "巴西"},
    "germany": {"en": "Germany", "zh-Hans": "德国", "zh-Hant": "德國"},
    "netherlands": {"en": "Netherlands", "zh-Hans": "荷兰", "zh-Hant": "荷蘭"},
    "switzerland": {"en": "Switzerland", "zh-Hans": "瑞士", "zh-Hant": "瑞士"},
    "turkey": {"en": "Turkey", "zh-Hans": "土耳其", "zh-Hant": "土耳其"},
    "taiwan": {"en": "Taiwan", "zh-Hans": "台湾", "zh-Hant": "台灣"},
    "china": {"en": "China", "zh-Hans": "中国", "zh-Hant": "中國"},
    "thailand": {"en": "Thailand", "zh-Hans": "泰国", "zh-Hant": "泰國"},
    "indonesia": {"en": "Indonesia", "zh-Hans": "印尼", "zh-Hant": "印尼"},
    "mexico": {"en": "Mexico", "zh-Hans": "墨西哥", "zh-Hant": "墨西哥"},
    "argentina": {"en": "Argentina", "zh-Hans": "阿根廷", "zh-Hant": "阿根廷"},
    "chile": {"en": "Chile", "zh-Hans": "智利", "zh-Hant": "智利"},
    "canada": {"en": "Canada", "zh-Hans": "加拿大", "zh-Hant": "加拿大"},
    "belgium": {"en": "Belgium", "zh-Hans": "比利时", "zh-Hant": "比利時"},
    "france": {"en": "France", "zh-Hans": "法国", "zh-Hant": "法國"},
    "spain": {"en": "Spain", "zh-Hans": "西班牙", "zh-Hant": "西班牙"},
    "portugal": {"en": "Portugal", "zh-Hans": "葡萄牙", "zh-Hant": "葡萄牙"},
    "panama": {"en": "Panama", "zh-Hans": "巴拿马", "zh-Hant": "巴拿馬"},
    "brunei": {"en": "Brunei", "zh-Hans": "文莱", "zh-Hant": "汶萊"},
    "puerto_rico": {"en": "Puerto Rico", "zh-Hans": "波多黎各", "zh-Hant": "波多黎各"},
    "poland": {"en": "Poland", "zh-Hans": "波兰", "zh-Hant": "波蘭"},
    "costa_rica": {"en": "Costa Rica", "zh-Hans": "哥斯达黎加", "zh-Hant": "哥斯大黎加"},
    "peru": {"en": "Peru", "zh-Hans": "秘鲁", "zh-Hant": "秘魯"},
    "kuwait": {"en": "Kuwait", "zh-Hans": "科威特", "zh-Hant": "科威特"},
    "greece": {"en": "Greece", "zh-Hans": "希腊", "zh-Hant": "希臘"},
    "ecuador": {"en": "Ecuador", "zh-Hans": "厄瓜多尔", "zh-Hant": "厄瓜多"},
    "dominican_republic": {"en": "Dominican Republic", "zh-Hans": "多米尼加", "zh-Hant": "多明尼加"},
    "hungary": {"en": "Hungary", "zh-Hans": "匈牙利", "zh-Hant": "匈牙利"},
    "croatia": {"en": "Croatia", "zh-Hans": "克罗地亚", "zh-Hant": "克羅地亞"},
    "asia": {"en": "Asia", "zh-Hans": "亚洲", "zh-Hant": "亞洲"},
    "southeast_asia": {"en": "Southeast Asia", "zh-Hans": "东南亚", "zh-Hant": "東南亞"},
    "bulgaria": {"en": "Bulgaria", "zh-Hans": "保加利亚", "zh-Hant": "保加利亞"},
    "austria": {"en": "Austria", "zh-Hans": "奥地利", "zh-Hant": "奧地利"},
    "israel": {"en": "Israel", "zh-Hans": "以色列", "zh-Hant": "以色列"},
    "slovakia": {"en": "Slovakia", "zh-Hans": "斯洛伐克", "zh-Hant": "斯洛伐克"},
    "lithuania": {"en": "Lithuania", "zh-Hans": "立陶宛", "zh-Hant": "立陶宛"},
    "sweden": {"en": "Sweden", "zh-Hans": "瑞典", "zh-Hant": "瑞典"},
    "south_africa": {"en": "South Africa", "zh-Hans": "南非", "zh-Hant": "南非"},
    "ukraine": {"en": "Ukraine", "zh-Hans": "乌克兰", "zh-Hant": "烏克蘭"},
    "luxembourg": {"en": "Luxembourg", "zh-Hans": "卢森堡", "zh-Hant": "盧森堡"},
    "denmark": {"en": "Denmark", "zh-Hans": "丹麦", "zh-Hant": "丹麥"},
    "venezuela": {"en": "Venezuela", "zh-Hans": "委内瑞拉", "zh-Hant": "委內瑞拉"},
    "slovenia": {"en": "Slovenia", "zh-Hans": "斯洛文尼亚", "zh-Hant": "斯洛維尼亞"},
    "colombia": {"en": "Colombia", "zh-Hans": "哥伦比亚", "zh-Hant": "哥倫比亞"},
    "uruguay": {"en": "Uruguay", "zh-Hans": "乌拉圭", "zh-Hant": "烏拉圭"},
    "norway": {"en": "Norway", "zh-Hans": "挪威", "zh-Hant": "挪威"},
    "nicaragua": {"en": "Nicaragua", "zh-Hans": "尼加拉瓜", "zh-Hant": "尼加拉瓜"},
    "guatemala": {"en": "Guatemala", "zh-Hans": "危地马拉", "zh-Hant": "瓜地馬拉"},
    "finland": {"en": "Finland", "zh-Hans": "芬兰", "zh-Hant": "芬蘭"},
    "saudi_arabia": {"en": "Saudi Arabia", "zh-Hans": "沙特阿拉伯", "zh-Hant": "沙特阿拉伯"},
    "czech_republic": {"en": "Czech Republic", "zh-Hans": "捷克", "zh-Hant": "捷克"},
}


def norm_country(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    compact = _compact(text)
    if compact in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[compact]
    # spaced form for "Hong Kong" etc. already handled via compact
    spaced = strip_parens(text).lower()
    if spaced in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[spaced]
    return compact or spaced


def country_labels(key: str) -> dict[str, str]:
    if key in _COUNTRY_LABELS:
        return dict(_COUNTRY_LABELS[key])
    # fallback: title-case the key/raw
    nice = key.replace("_", " ").strip()
    nice = nice.title() if nice else key
    return {"en": nice, "zh-Hans": nice, "zh-Hant": nice}


# --- host --------------------------------------------------------------------

def norm_host(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    return strip_parens(text) or text


# --- tournament --------------------------------------------------------------

_TOURNAMENT_ALIASES: dict[str, str] = {
    "sb": "standard_battle",
    "standardbattle": "standard_battle",
    "fs": "flagship",
    "flagship": "flagship",
    "tc": "treasure_cup",
    "treasurecup": "treasure_cup",
    "storetc": "treasure_cup",
    "regional": "regional",
    "regionals": "regional",
    "storeregional": "store_regional",
    "shopevent": "shop_event",
    "shopcs": "shop_cs",
    "storecs": "store_cs",
    "storechampionship": "store_championship",
    "storeprelims": "store_prelims",
    "3on3": "3v3",
    "3v3": "3v3",
    "3v3cs": "3v3",
    "cs3v3": "3v3",
    "cs3on3": "3v3",
    "5v5": "5v5",
    "5on5": "5v5",
    "2on2": "2v2",
    "2v2": "2v2",
    "tb": "treasure_box",
    "nationals": "nationals",
    "online": "online",
    "optcgsim": "optcgsim",
    "exgrand": "ex_grand",
    "piratebattle": "pirate_battle",
    "opbattle": "op_battle",
    "areaqualifier": "area_qualifier",
    "areaqualifiers": "area_qualifier",
    "ocefinal": "oce_final",
    "heroinescup": "heroines_cup",
}

_TOURNAMENT_LABELS: dict[str, dict[str, str]] = {
    "standard_battle": {"en": "Standard Battle", "zh-Hans": "标准赛", "zh-Hant": "標準賽"},
    "flagship": {"en": "Flagship", "zh-Hans": "旗舰赛", "zh-Hant": "旗艦賽"},
    "treasure_cup": {"en": "Treasure Cup", "zh-Hans": "宝藏杯", "zh-Hant": "寶藏杯"},
    "regional": {"en": "Regional", "zh-Hans": "地区赛", "zh-Hant": "地區賽"},
    "store_regional": {"en": "Store Regional", "zh-Hans": "店内地区赛", "zh-Hant": "店內地區賽"},
    "shop_event": {"en": "Shop Event", "zh-Hans": "店内活动", "zh-Hant": "店內活動"},
    "shop_cs": {"en": "Shop CS", "zh-Hans": "店内CS", "zh-Hant": "店內CS"},
    "store_cs": {"en": "Store CS", "zh-Hans": "店内CS", "zh-Hant": "店內CS"},
    "store_championship": {"en": "Store Championship", "zh-Hans": "店内锦标赛", "zh-Hant": "店內錦標賽"},
    "store_prelims": {"en": "Store Prelims", "zh-Hans": "店内预选", "zh-Hant": "店內預選"},
    "3v3": {"en": "3v3", "zh-Hans": "3v3", "zh-Hant": "3v3"},
    "5v5": {"en": "5v5", "zh-Hans": "5v5", "zh-Hant": "5v5"},
    "2v2": {"en": "2v2", "zh-Hans": "2v2", "zh-Hant": "2v2"},
    "treasure_box": {"en": "Treasure Box", "zh-Hans": "宝箱赛", "zh-Hant": "寶箱賽"},
    "nationals": {"en": "Nationals", "zh-Hans": "全国赛", "zh-Hant": "全國賽"},
    "online": {"en": "Online", "zh-Hans": "线上赛", "zh-Hant": "線上賽"},
    "optcgsim": {"en": "OPTCG Sim", "zh-Hans": "模拟器赛", "zh-Hant": "模擬器賽"},
    "ex_grand": {"en": "EX Grand", "zh-Hans": "EX大奖赛", "zh-Hant": "EX大獎賽"},
    "pirate_battle": {"en": "Pirate Battle", "zh-Hans": "海贼对战", "zh-Hant": "海賊對戰"},
    "op_battle": {"en": "OP Battle", "zh-Hans": "OP对战", "zh-Hant": "OP對戰"},
    "area_qualifier": {"en": "Area Qualifier", "zh-Hans": "赛区资格赛", "zh-Hant": "賽區資格賽"},
    "oce_final": {"en": "OCE Final", "zh-Hans": "大洋洲决赛", "zh-Hant": "大洋洲決賽"},
    "heroines_cup": {"en": "Heroines Cup", "zh-Hans": "女主角杯", "zh-Hant": "女主角杯"},
}


def norm_tournament(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    compact = _compact(text)
    if not compact:
        return ""

    # Team formats often appear inside longer names (e.g. "GAO 3v3", "CS 3on3")
    if "3on3" in compact or "3v3" in compact:
        return "3v3"
    if "5on5" in compact or "5v5" in compact:
        return "5v5"
    if "2on2" in compact or "2v2" in compact:
        return "2v2"

    if compact in _TOURNAMENT_ALIASES:
        return _TOURNAMENT_ALIASES[compact]

    # Prefix aliases: "RegionalFinal" etc. — only exact keys above; fallback to stripped text
    base = strip_parens(text)
    return base or text


def tournament_labels(key: str) -> dict[str, str]:
    if key in _TOURNAMENT_LABELS:
        return dict(_TOURNAMENT_LABELS[key])
    nice = key.replace("_", " ").strip()
    if re.fullmatch(r"[a-z0-9]+(?: [a-z0-9]+)*", nice.lower()):
        nice = nice.title()
    return {"en": nice, "zh-Hans": nice, "zh-Hant": nice}


# --- placement ---------------------------------------------------------------

_PLACE_ORDINAL = {
    "1st": "1st",
    "2nd": "2nd",
    "3rd": "3rd",
    "4th": "4th",
    "5th": "5th",
    "6th": "6th",
    "7th": "7th",
    "8th": "8th",
}


def norm_placement(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    base = strip_parens(text)
    low = _SPACE_RE.sub(" ", base.lower()).strip()
    if not low or low in {"na", "n/a", "-"}:
        return "na"

    # Top-8 / Top 8 / T8 / top-4
    m = re.match(r"^(?:top[-\s]?|t)(\d+)\b", low.replace(" ", ""))
    if not m:
        m = re.match(r"^top[-\s]?(\d+)\b", low)
    if m:
        return f"top_{int(m.group(1))}"

    m = re.match(r"^(1st|2nd|3rd|[4-9]th|\d+th)\b", low)
    if m:
        token = m.group(1)
        if token in _PLACE_ORDINAL:
            return _PLACE_ORDINAL[token]
        # 10th, 11th...
        num = re.match(r"^(\d+)", token)
        if num:
            return f"place_{int(num.group(1))}"

    compact = _compact(low)
    if compact.startswith("t") and compact[1:].isdigit():
        return f"top_{int(compact[1:])}"

    return base or text


_PLACEMENT_LABELS: dict[str, dict[str, str]] = {
    "1st": {"en": "1st Place", "zh-Hans": "冠军", "zh-Hant": "冠軍"},
    "2nd": {"en": "2nd Place", "zh-Hans": "亚军", "zh-Hant": "亞軍"},
    "3rd": {"en": "3rd Place", "zh-Hans": "季军", "zh-Hant": "季軍"},
    "4th": {"en": "4th Place", "zh-Hans": "第4名", "zh-Hant": "第4名"},
    "5th": {"en": "5th Place", "zh-Hans": "第5名", "zh-Hant": "第5名"},
    "6th": {"en": "6th Place", "zh-Hans": "第6名", "zh-Hant": "第6名"},
    "7th": {"en": "7th Place", "zh-Hans": "第7名", "zh-Hant": "第7名"},
    "8th": {"en": "8th Place", "zh-Hans": "第8名", "zh-Hant": "第8名"},
    "top_2": {"en": "Top 2", "zh-Hans": "前2", "zh-Hant": "前2"},
    "top_4": {"en": "Top 4", "zh-Hans": "前4", "zh-Hant": "前4"},
    "top_8": {"en": "Top 8", "zh-Hans": "前8", "zh-Hant": "前8"},
    "top_16": {"en": "Top 16", "zh-Hans": "前16", "zh-Hant": "前16"},
    "top_32": {"en": "Top 32", "zh-Hans": "前32", "zh-Hant": "前32"},
    "top_64": {"en": "Top 64", "zh-Hans": "前64", "zh-Hant": "前64"},
    "na": {"en": "N/A", "zh-Hans": "未知", "zh-Hant": "未知"},
}


def placement_labels(key: str) -> dict[str, str]:
    if key in _PLACEMENT_LABELS:
        return dict(_PLACEMENT_LABELS[key])
    if key.startswith("top_"):
        n = key.split("_", 1)[1]
        return {"en": f"Top {n}", "zh-Hans": f"前{n}", "zh-Hant": f"前{n}"}
    if key.startswith("place_"):
        n = key.split("_", 1)[1]
        return {"en": f"{n}th Place", "zh-Hans": f"第{n}名", "zh-Hant": f"第{n}名"}
    nice = key.replace("_", " ")
    return {"en": nice, "zh-Hans": nice, "zh-Hant": nice}


def facet_row(value: str, count: int, labels: dict[str, str]) -> dict[str, Any]:
    return {
        "value": value,
        "count": count,
        "label_en": labels.get("en") or value,
        "label_zh_Hans": labels.get("zh-Hans") or value,
        "label_zh_Hant": labels.get("zh-Hant") or value,
    }
