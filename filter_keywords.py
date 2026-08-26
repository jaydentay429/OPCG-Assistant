"""Lightweight keyword tags for card search filters (Blocker / Rush / DON×N / …)."""

from __future__ import annotations

import re
from typing import Any

# Values accepted by /filters/cards?keywords=…
FILTER_KEYWORD_IDS: tuple[str, ...] = (
    "blocker",
    "rush",
    "double_attack",
    "banish",
    "blockerless",
    "trigger",
    "don_x1",
    "don_x2",
    "don_x3",
)

_DON_TAG_RE = re.compile(
    r"\[DON!!\s*x\s*(\d+)\]|【咚‼?\s*[×xX]\s*(\d+)】",
    re.I,
)

# Strip "gains [Keyword]" grant clauses so cards that *give* keywords
# are not treated as having that keyword themselves.
_GRANT_STRIP_RE = re.compile(
    r"(?:最多\s*\d+\s*張)?(?:自己的?)?「[^」]+」[^。\n]{0,48}(?:獲得|获得)\s*【(?:防禦|防御|速攻|雙重攻擊|双重攻击|不可阻擋|不可阻挡|流放|消滅|消灭)】|"
    r"(?:up to\s+\d+\s+of\s+)?your\s+\[[^\]]+\][^\.\n]{0,60}gains?\s+\["
    r"(?:Blocker|Rush|Double Attack|Banish|Blockerless|Unblockable)\]|"
    r"(?:獲得|获得)\s*【(?:防禦|防御|速攻|雙重攻擊|双重攻击|不可阻擋|不可阻挡)】|"
    r"gains?\s+\[(?:Blocker|Rush|Double Attack|Banish|Blockerless|Unblockable)\]",
    re.I,
)

_cache: dict[str, frozenset[str]] = {}


def clear_filter_keyword_cache() -> None:
    _cache.clear()


def _effect_blob(info: dict[str, Any]) -> str:
    parts = [
        str(info.get("effect") or ""),
        str(info.get("effect_en") or ""),
        str(info.get("trigger") or ""),
        str(info.get("trigger_en") or ""),
    ]
    return "\n".join(p for p in parts if p.strip())


def detect_filter_keywords(info: dict[str, Any]) -> frozenset[str]:
    """Return filter keyword ids present on a card (own keywords, not grants)."""
    text = _effect_blob(info)
    if not text.strip():
        return frozenset()

    stripped = _GRANT_STRIP_RE.sub(" ", text)
    low = stripped.lower()
    found: set[str] = set()

    if re.search(r"【速攻：角色】|\[rush:\s*character\]|rush:\s*character", stripped, re.I):
        found.add("rush")
    elif any(n in low or n in stripped for n in ("[rush]", "【rush】", "【速攻】", "rush")):
        if "【速攻】" in stripped or "[rush]" in low or re.search(r"(^|[^a-z])rush([^a-z]|$)", low):
            found.add("rush")

    checks = [
        ("blocker", ("[blocker]", "【blocker】", "【阻擋者】", "【阻挡者】", "【防禦】", "【防御】")),
        ("double_attack", ("[double attack]", "【double attack】", "【雙重攻擊】", "【双重攻击】")),
        ("banish", ("[banish]", "【banish】", "【流放】", "【消滅】", "【消灭】", "【消失】")),
        ("blockerless", ("[blockerless]", "【blockerless】", "【不可阻擋】", "【不可阻挡】", "【防禦不可】", "【防御不可】")),
    ]
    for key, needles in checks:
        if any(n in low or n in stripped for n in needles):
            found.add(key)

    if re.search(r"【觸發器】|【触发】|\[trigger\]", stripped, re.I):
        found.add("trigger")

    for m in _DON_TAG_RE.finditer(text):
        n = int(next(g for g in m.groups() if g) or 0)
        if n == 1:
            found.add("don_x1")
        elif n == 2:
            found.add("don_x2")
        elif n >= 3:
            # x3+ collapse into don_x3 for the filter chip
            found.add("don_x3")

    return frozenset(found)


def card_filter_keywords(card_id: str, basic: dict[str, Any] | None) -> frozenset[str]:
    cid = str(card_id or "").strip()
    if not cid:
        return frozenset()
    cached = _cache.get(cid)
    if cached is not None:
        return cached
    tags = detect_filter_keywords(basic or {})
    _cache[cid] = tags
    return tags
