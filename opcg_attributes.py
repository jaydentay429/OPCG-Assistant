"""卡牌属性（斩/打/射/特/知/？）与英文 canonical 名互转。"""
from __future__ import annotations

ATTRIBUTE_ORDER = ("Slash", "Strike", "Ranged", "Special", "Wisdom", "Unknown")

ATTRIBUTE_LABELS: dict[str, tuple[str, str]] = {
    "Slash": ("斩", "Slash"),
    "Strike": ("打", "Strike"),
    "Ranged": ("射", "Ranged"),
    "Special": ("特", "Special"),
    "Wisdom": ("知", "Wisdom"),
    "Unknown": ("？", "Unknown"),
}

_ATTRIBUTE_ALIASES: dict[str, str | None] = {
    "slash": "Slash",
    "strike": "Strike",
    "ranged": "Ranged",
    "special": "Special",
    "wisdom": "Wisdom",
    "unknown": "Unknown",
    "斩": "Slash",
    "斩击": "Slash",
    "打": "Strike",
    "打击": "Strike",
    "射": "Ranged",
    "远程": "Ranged",
    "特": "Special",
    "特殊": "Special",
    "知": "Wisdom",
    "智慧": "Wisdom",
    "?": "Unknown",
    "？": "Unknown",
    "-": None,
    "—": None,
    "－": None,
}


def _alias_key(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if text in ATTRIBUTE_LABELS:
        return text
    mapped = _ATTRIBUTE_ALIASES.get(text)
    if mapped is None and text in _ATTRIBUTE_ALIASES:
        return ""
    if mapped:
        return mapped
    mapped = _ATTRIBUTE_ALIASES.get(text.lower())
    if mapped is None and text.lower() in _ATTRIBUTE_ALIASES:
        return ""
    return mapped or text


def normalize_attributes(values: list[str] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        parts = [p.strip() for p in values.replace("/", ",").split(",") if p.strip()]
    else:
        parts = [str(v).strip() for v in values if str(v).strip()]
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        canonical = _alias_key(part)
        if not canonical or canonical not in ATTRIBUTE_LABELS or canonical in seen:
            continue
        seen.add(canonical)
        out.append(canonical)
    order = {name: idx for idx, name in enumerate(ATTRIBUTE_ORDER)}
    out.sort(key=lambda name: order.get(name, len(ATTRIBUTE_ORDER)))
    return out


def resolve_card_attributes(card: dict) -> list[str]:
    for key in ("attributes_en", "attributes"):
        attrs = normalize_attributes(card.get(key))
        if attrs:
            return attrs
    return []


def attribute_label(canonical: str, *, lang_en: bool) -> str:
    labels = ATTRIBUTE_LABELS.get(canonical)
    if not labels:
        return canonical
    return labels[1] if lang_en else labels[0]


def format_attributes(values: list[str] | str | None, *, lang_en: bool) -> str:
    attrs = normalize_attributes(values)
    if not attrs:
        return "-"
    return ", ".join(attribute_label(name, lang_en=lang_en) for name in attrs)


def format_card_attributes(card: dict, *, lang_en: bool) -> str:
    return format_attributes(resolve_card_attributes(card), lang_en=lang_en)


def filter_zh_options() -> list[str]:
    return [ATTRIBUTE_LABELS[name][0] for name in ATTRIBUTE_ORDER if name != "Unknown"]


def filter_zh_to_en(selected_zh: list[str]) -> list[str]:
    zh_to_en = {zh: en for en, (zh, _en) in ATTRIBUTE_LABELS.items()}
    out: list[str] = []
    for value in selected_zh:
        canonical = _alias_key(str(value).strip())
        if canonical in ATTRIBUTE_LABELS and canonical not in out:
            out.append(canonical)
            continue
        mapped = zh_to_en.get(str(value).strip())
        if mapped and mapped not in out:
            out.append(mapped)
    return out
