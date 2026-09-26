from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from battle.state import CardInst, MatchState, PendingChoice, PendingEffect, PendingSearch, PlayerState, new_iid
from battle.effect_schema import ALLOWED_OPS, sanitize_op
from battle.choice_purpose import grant_keyword_choice_summary, purpose_from_op

CatalogFn = Callable[[str], dict[str, Any]]


COLOR_MAP = {
    "red": "red",
    "blue": "blue",
    "green": "green",
    "purple": "purple",
    "black": "black",
    "yellow": "yellow",
    "紅": "red",
    "红": "red",
    "藍": "blue",
    "蓝": "blue",
    "綠": "green",
    "绿": "green",
    "紫": "purple",
    "黑": "black",
    "黃": "yellow",
    "黄": "yellow",
}


def normalize_colors(raw: list[Any] | None) -> set[str]:
    out: set[str] = set()
    for item in raw or []:
        key = str(item or "").strip().lower()
        mapped = COLOR_MAP.get(key) or COLOR_MAP.get(str(item or "").strip())
        if mapped:
            out.add(mapped)
        elif key in COLOR_MAP.values():
            out.add(key)
    return out


def card_type_of(info: dict[str, Any]) -> str:
    text = str(info.get("card_type_en") or info.get("card_type") or info.get("category") or "").lower()
    if "leader" in text or "領袖" in text or "领袖" in text or "领航" in text:
        return "leader"
    if "event" in text or "事件" in text:
        return "event"
    if "stage" in text or "舞台" in text:
        return "stage"
    return "character"


def _printed_cost(info: dict[str, Any]) -> int:
    try:
        return max(0, int(str(info.get("cost") or "0").split()[0].replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _printed_power(info: dict[str, Any]) -> int:
    try:
        return max(0, int(str(info.get("power") or "0").split()[0].replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _treated_as_names(info: dict[str, Any]) -> list[str]:
    """Names this card is also treated as (也可視為 / also treat this card's name as)."""
    text = " ".join(
        str(info.get(k) or "")
        for k in ("effect", "effect_text", "text", "effect_en", "trigger", "trigger_en")
    )
    if not text:
        return []
    out: list[str] = []
    for m in re.finditer(r"也可視為「([^」]+)」(?:和「([^」]+)」)?|也可视为「([^」]+)」(?:和「([^」]+)」)?", text):
        for g in m.groups():
            if g and g.strip():
                out.append(g.strip())
    for m in re.finditer(
        r"also treat this card'?s? name as\s*\[([^\]]+)\](?:\s*and\s*\[([^\]]+)\])?",
        text,
        re.I,
    ):
        for g in m.groups():
            if g and g.strip():
                out.append(g.strip())
    # Dedupe preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for n in out:
        key = n.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(n)
    return uniq


def _card_name_blob(info: dict[str, Any]) -> str:
    parts = [str(info.get("name") or ""), str(info.get("name_en") or "")]
    parts.extend(_treated_as_names(info))
    # Spoken / regional aliases (希留 ↔ 矢龍, 赤犬 ↔ Sakazuki, …).
    try:
        from battle.name_aliases import alias_texts_for_en

        parts.extend(alias_texts_for_en(str(info.get("name_en") or "")))
    except Exception:
        pass
    return " ".join(p for p in parts if p).lower()


def _name_alias_parts(needle: str) -> list[str]:
    """Split EN|ZH|/ aliases used in encodings into individual needles."""
    raw = str(needle or "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.replace("/", "|").split("|") if p.strip()]


def _card_matches_name_contains(info: dict[str, Any], needle: str) -> bool:
    """True if card matches any pipe-separated name alias (substring or exact)."""
    parts = _name_alias_parts(needle)
    if not parts:
        return False
    blob = _card_name_blob(info)
    return any((p.lower() in blob) or _card_has_name(info, p) for p in parts)


def _card_excluded_by_name(info: dict[str, Any], needle: str) -> bool:
    """True if card should be excluded by a pipe-separated exclude_name filter."""
    parts = _name_alias_parts(needle)
    if not parts:
        return False
    blob = _card_name_blob(info)
    return any(_card_has_name(info, p) or (p.lower() in blob) for p in parts)


def _norm_card_name(value: str) -> str:
    s = (value or "").strip().lower()
    for a, b in (
        ("・", "."),
        ("·", "."),
        ("．", "."),
        (" ", ""),
        ("\u3000", ""),
        ("'", ""),
        ("’", ""),
    ):
        s = s.replace(a, b)
    return s


def _card_has_name(info: dict[str, Any], needle: str) -> bool:
    """True if printed ZH/EN name (or treated-as name) equals needle."""
    target = _norm_card_name(needle)
    if not target:
        return False
    names = [info.get("name"), info.get("name_en"), *_treated_as_names(info)]
    for raw in names:
        if _norm_card_name(str(raw or "")) == target:
            return True
    return False


def _grant_keyword_char_ok(
    op: dict[str, Any],
    info: dict[str, Any],
    *,
    live_power: int | None = None,
    cost: int | None = None,
) -> bool:
    """Match grant_keyword filters.

    ``name_or_trait`` is identity OR (name **or** trait). Power/cost gates still
    apply to both branches (OP16-001: 8000+ Whitebeard **or** 8000+ Luffy).
    """
    name_needle = str(op.get("name_contains") or "").strip()
    excl_needle = str(op.get("exclude_name") or "").strip()
    trait_needle = str(op.get("trait_contains") or op.get("trait_includes") or "").strip()
    color_needle = str(op.get("color") or "").strip().lower()
    if excl_needle and _card_excluded_by_name(info, excl_needle):
        return False
    name_ok = (not name_needle) or _card_matches_name_contains(info, name_needle)
    trait_ok = True
    if trait_needle or (isinstance(op.get("trait_any"), list) and op.get("trait_any")) or (
        isinstance(op.get("trait_all"), list) and op.get("trait_all")
    ):
        from battle.engine import _op_traits_ok

        trait_ok = _op_traits_ok(info, op)

    def _text_flags_ok() -> bool:
        if op.get("require_no_on_play") or op.get("require_no_when_attacking"):
            import re as _re

            text = str(info.get("effect") or info.get("effect_text") or info.get("text") or "")
            if op.get("require_no_on_play") and _re.search(r"【登場時】|【登场时】|\[on play\]", text, _re.I):
                return False
            if op.get("require_no_when_attacking") and _re.search(
                r"【攻擊時】|【攻击时】|\[when attacking\]", text, _re.I
            ):
                return False
        if op.get("require_no_effect") and has_meaningful_effect_text(info):
            return False
        if color_needle:
            blob = _card_color_blob(info)
            if not any(a.lower() in blob for a in _color_aliases(color_needle)):
                return False
        return True

    def _numeric_ok() -> bool:
        if op.get("cost_lte") is not None or op.get("cost_gte") is not None or op.get("cost_eq") is not None:
            cost_v = cost if cost is not None else _printed_cost(info)
            if op.get("cost_lte") is not None and cost_v > int(op["cost_lte"]):
                return False
            if op.get("cost_gte") is not None and cost_v < int(op["cost_gte"]):
                return False
            if op.get("cost_eq") is not None and cost_v != int(op["cost_eq"]):
                return False
        if op.get("power_gte") is not None or op.get("power_lte") is not None:
            pow_v = live_power if live_power is not None else _printed_power(info)
            if op.get("power_gte") is not None and pow_v < int(op["power_gte"]):
                return False
            if op.get("power_lte") is not None and pow_v > int(op["power_lte"]):
                return False
        return True

    if not _text_flags_ok():
        return False
    if op.get("name_or_trait") and (name_needle or trait_needle):
        identity_ok = bool((name_needle and name_ok) or (trait_needle and trait_ok))
        return identity_ok and _numeric_ok()
    if name_needle and not name_ok:
        return False
    if (trait_needle or (isinstance(op.get("trait_any"), list) and op.get("trait_any")) or (isinstance(op.get("trait_all"), list) and op.get("trait_all"))) and not trait_ok:
        return False
    return _numeric_ok()


def _parse_exclude_name(chunk: str) -> str:
    m = re.search(
        r"other than\s*\[([^\]]+)\]|除了「([^」]+)」以外|除了『([^』]+)』以外",
        chunk,
        re.I,
    )
    if not m:
        return ""
    return next((g for g in m.groups() if g), "").strip()


def _search_exclude_needles(op: dict[str, Any], catalog: CatalogFn | None) -> list[str]:
    """Names that must not be added from a search (usually the searching card's own name)."""
    needles: list[str] = []
    raw = str(op.get("exclude_name") or "").strip()
    if raw:
        needles.extend(_name_alias_parts(raw) or [raw])
    cid = str(op.get("card_id") or "").strip()
    if catalog and cid:
        src = catalog(cid)
        zh = str(src.get("name") or "").strip()
        en = str(src.get("name_en") or "").strip()
        blob = f"{src.get('effect') or ''}\n{src.get('effect_en') or ''}"
        self_excluded = bool(
            (zh and f"除了「{zh}」以外" in blob)
            or (en and re.search(rf"other than\s*\[\s*{re.escape(en)}\s*\]", blob, re.I))
            or (raw and any(_norm_card_name(p) in {_norm_card_name(zh), _norm_card_name(en)} for p in _name_alias_parts(raw)))
        )
        if self_excluded:
            needles.extend(n for n in (zh, en) if n)
    # Preserve order, drop empties/dupes
    seen: set[str] = set()
    out: list[str] = []
    for n in needles:
        key = _norm_card_name(n)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def _enrich_search_op_from_card(op: dict[str, Any], catalog: CatalogFn | None) -> dict[str, Any]:
    """Fill missing search filters from live card text (stale library entries)."""
    out = dict(op)
    cid = str(out.get("card_id") or "").strip()
    if not catalog or not cid:
        return out
    parsed = _parse_look_top_search(effect_blob(catalog(cid)))
    if not parsed:
        # Still try exclude-only from text
        excl = _parse_exclude_name(effect_blob(catalog(cid)))
        if excl and not str(out.get("exclude_name") or "").strip():
            out["exclude_name"] = excl
        return out
    for key in ("trait_contains", "name_contains", "exclude_name", "summary"):
        if not str(out.get(key) or "").strip() and parsed.get(key):
            out[key] = parsed[key]
    for key in ("cost_eq", "cost_lte", "cost_gte", "power_lte", "power_eq", "power_gte"):
        if out.get(key) is None and parsed.get(key) is not None:
            out[key] = parsed[key]
    # Paper 「角色卡」must survive stale library entries that only stored the trait.
    if not str(out.get("card_type") or "").strip() and parsed.get("card_type"):
        out["card_type"] = parsed["card_type"]
    # Prefer paper look destination when encoded entry wrongly says play-but-adds-to-hand.
    if parsed.get("destination") == "hand" and out.get("destination") == "play":
        out["destination"] = "hand"
        out.pop("as_rested", None)
    # Paper「其餘…廢棄區」must win over stale library order_bottom=True.
    if parsed.get("trash_rest"):
        out["trash_rest"] = True
        out["order_bottom"] = False
    elif "order_bottom" not in out and "order_bottom" in parsed:
        out["order_bottom"] = parsed["order_bottom"]
    return out


def _card_trait_blob(info: dict[str, Any]) -> str:
    raw: list[Any] = []
    for key in ("traits", "traits_en", "trait", "trait_en"):
        v = info.get(key)
        if isinstance(v, list):
            raw.extend(v)
        elif v:
            raw.append(v)
    return " ".join(str(x or "") for x in raw).lower()


def _count_own_trait_field(
    player: PlayerState,
    catalog: CatalogFn,
    trait: str,
    *,
    include_leader: bool = False,
    include_stage: bool = False,
) -> int:
    """Count own field cards matching trait (Leader / Characters / Stages)."""
    from battle.engine import _info_has_trait

    n = 0
    if include_leader:
        info = catalog(player.leader_card_id) if catalog else {}
        if not trait or _info_has_trait(info or {}, trait):
            n += 1
    for c in player.characters:
        info = catalog(c.card_id) if catalog else {}
        if not trait or _info_has_trait(info or {}, trait):
            n += 1
    if include_stage:
        for s in getattr(player, "stages", None) or []:
            info = catalog(s.card_id) if catalog else {}
            if not trait or _info_has_trait(info or {}, trait):
                n += 1
    return n


def _card_color_blob(info: dict[str, Any]) -> str:
    return " ".join(
        str(x or "") for x in (info.get("colors") or []) + (info.get("colors_en") or [])
    ).lower()


def card_attr_blob(info: dict[str, Any], inst: Any | None = None) -> str:
    """Printed + granted attributes (EN/ZH) for matching."""
    parts = [
        *(info.get("attributes_en") or []),
        *(info.get("attributes") or []),
        info.get("attribute"),
        info.get("attribute_en"),
        info.get("attr"),
    ]
    if inst is not None:
        parts.extend(getattr(inst, "turn_attributes", None) or [])
        parts.extend(getattr(inst, "granted_attributes", None) or [])
    return " ".join(str(x or "") for x in parts)


def attr_alias_keys(needle: str) -> tuple[str, ...]:
    key = (needle or "").strip().lower()
    aliases = {
        "slash": ("slash", "斬", "斩"),
        "斬": ("slash", "斬", "斩"),
        "斩": ("slash", "斬", "斩"),
        "strike": ("strike", "打"),
        "打": ("strike", "打"),
        "special": ("special", "特"),
        "特": ("special", "特"),
        "ranged": ("ranged", "射"),
        "射": ("ranged", "射"),
        "wisdom": ("wisdom", "知"),
        "知": ("wisdom", "知"),
    }
    return aliases.get(key, (key,))


def _color_aliases(needle: str) -> tuple[str, ...]:
    key = (needle or "").strip().lower()
    aliases = {
        "green": ("green", "綠", "绿"),
        "綠": ("green", "綠", "绿"),
        "绿": ("green", "綠", "绿"),
        "red": ("red", "紅", "红"),
        "紅": ("red", "紅", "红"),
        "红": ("red", "紅", "红"),
        "blue": ("blue", "藍", "蓝"),
        "藍": ("blue", "藍", "蓝"),
        "蓝": ("blue", "藍", "蓝"),
        "purple": ("purple", "紫"),
        "紫": ("purple", "紫"),
        "black": ("black", "黑"),
        "黑": ("black", "黑"),
        "yellow": ("yellow", "黃", "黄"),
        "黃": ("yellow", "黃", "黄"),
        "黄": ("yellow", "黃", "黄"),
    }
    return aliases.get(key, (needle,))


def effect_blob(info: dict[str, Any]) -> str:
    parts = [
        str(info.get("effect_en") or ""),
        str(info.get("effect") or ""),
        str(info.get("trigger_en") or ""),
        str(info.get("trigger") or ""),
    ]
    return "\n".join(p for p in parts if p.strip())


def has_meaningful_effect_text(info_or_blob: dict[str, Any] | str) -> bool:
    """True when text has more than blank/dash or keyword-only reminder text.

    Used by compilers and audits so Blocker/Rush-only and "-" cards are not
    treated as empty-with-text gaps.
    """
    blob = effect_blob(info_or_blob) if isinstance(info_or_blob, dict) else str(info_or_blob or "")
    blob = blob.strip()
    if not blob or re.fullmatch(r"[-—－\s/]*", blob):
        return False
    # Deck-construction rules only (not resolvable in battle).
    if re.search(
        r"you may have any number of this card in your deck|"
        r"可不限張數放入卡組|可不限张数放入卡组",
        blob,
        re.I,
    ) and not re.search(
        r"\[(?:on play|when attacking|activate|trigger|counter|main)\]|"
        r"【(?:登場時|登场时|攻擊時|攻击时|啟動主要|启动主要|觸發器|触发器|反擊|反击|主要)】",
        blob,
        re.I,
    ):
        return False
    compact = re.sub(
        r"\[(?:Blocker|Rush|Double Attack|Banish|Blockerless)\][^\[【]*|"
        r"【(?:防禦|防御|速攻|雙重攻擊|双重攻击|除去|無防禦|无防御)】[^\[【]*",
        "",
        blob,
        flags=re.I,
    )
    # Strip parenthetical reminder text left after keyword labels.
    compact = re.sub(r"\([^)]*\)|（[^）]*）", "", compact)
    compact = re.sub(r"[-—－\s/]+", " ", compact).strip()
    return bool(compact)


def detect_keywords(info: dict[str, Any]) -> list[str]:
    text = effect_blob(info)
    # Strip "gains [Keyword]" grant clauses so cards that *give* Blocker/Rush
    # to another unit are not treated as having that keyword themselves (OP16-048).
    stripped = re.sub(
        r"(?:最多\s*\d+\s*張)?(?:自己的?)?「[^」]+」[^。\n]{0,48}(?:獲得|获得)\s*【(?:防禦不可|防御不可|防禦|防御|速攻|雙重攻擊|双重攻击|不可阻擋|不可阻挡|流放|消滅|消灭)】|"
        r"(?:up to\s+\d+\s+of\s+)?your\s+\[[^\]]+\][^\.\n]{0,60}gains?\s+\["
        r"(?:Blocker|Rush|Double Attack|Banish|Blockerless|Unblockable)\]|"
        r"(?:獲得|获得)\s*【(?:防禦不可|防御不可|防禦|防御|速攻|雙重攻擊|双重攻击|不可阻擋|不可阻挡)】|"
        r"gains?\s+\[(?:Blocker|Rush|Double Attack|Banish|Blockerless|Unblockable)\]|"
        # Keyword reminder text attached to grants (OP16-095 etc.)
        r"[（(]\s*(?:這張卡片不會遭到防禦|这张卡片不会遭到防御|This card cannot be blocked\.?)\s*[）)]",
        " ",
        text,
        flags=re.I,
    )
    # Strip references to Blocker as a *condition/restriction* on someone else
    # (OP09-118 Roger, ST01-012 deny-blocker, etc.) — not innate 【防禦】 on this card.
    stripped = re.sub(
        r"(?:無法|无法|cannot|can'?t)\s*(?:發動|发动|activate)\s*(?:a\s+)?(?:【(?:防禦|防御)】|\[Blocker\])|"
        r"(?:對手|对方|opponent).{0,80}(?:發動|发动|activates?)\s*(?:a\s+)?(?:【(?:防禦|防御)】|\[Blocker\])|"
        r"when (?:your )?opponent activates?\s*\[Blocker\]|"
        r"(?:啟動|启动|activate).{0,12}【(?:防禦|防御)】時|"
        r"(?:啟動|启动|activate).{0,12}\[Blocker\]",
        " ",
        stripped,
        flags=re.I,
    )
    low = stripped.lower()
    found: list[str] = []
    # Rush: character must be checked before plain Rush (text contains 速攻).
    if re.search(r"【速攻：角色】|\[rush:\s*character\]|rush:\s*character", stripped, re.I):
        found.append("rush_character")
    elif any(n in low or n in stripped for n in ("[rush]", "【rush】", "【速攻】", "rush")):
        # Avoid matching "rush" inside longer unrelated English words when only "rush" token exists.
        if "【速攻】" in stripped or "[rush]" in low or re.search(r"(^|[^a-z])rush([^a-z]|$)", low):
            found.append("rush")
    checks = [
        ("blocker", ("[blocker]", "【blocker】", "【阻擋者】", "【阻挡者】", "【防禦】", "【防御】")),
        ("double_attack", ("[double attack]", "【double attack】", "【雙重攻擊】", "【双重攻击】")),
        ("banish", ("[banish]", "【banish】", "【流放】", "【消滅】", "【消灭】", "【消失】")),
        ("blockerless", ("[blockerless]", "【blockerless】", "【不可阻擋】", "【不可阻挡】", "【防禦不可】", "【防御不可】")),
    ]
    for key, needles in checks:
        if any(n in low or n in stripped for n in needles):
            found.append(key)
    if re.search(r"【觸發器】|【触发】|\[trigger\]", stripped, re.I):
        found.append("trigger")
    return found


def parse_when_attacking_base_power_copy(info: dict[str, Any]) -> dict[str, Any] | None:
    """
    When Attacking base-power rewrite templates:
      - becomes opponent Leader's power (OP16-055 / OP16-036 / EB04-052)
      - choose a Character; base becomes that Character's power (EB01-061 / OP16-104)
    """
    text = effect_blob(info)
    if not re.search(r"\[when attacking\]|【攻擊時】|【攻击时】", text, re.I):
        return None

    # Extract When Attacking body (prefer Chinese clause when present).
    # Combined timings like 【攻擊時】/【防禦時】 leave almost no body in a
    # [^【]-limited capture — fall back to a wider window / full text.
    chunk = ""
    for blob in (str(info.get("effect") or ""), str(info.get("effect_en") or ""), text):
        m = re.search(
            r"(?:【攻擊時】|【攻击时】|\[when attacking\])([^【\[]{0,320})",
            blob,
            re.I,
        )
        if m and len((m.group(1) or "").strip()) >= 8:
            chunk = m.group(0)
            break
        m2 = re.search(
            r"(?:【攻擊時】|【攻击时】|\[when attacking\]).{0,40}"
            r"(?:【防禦時】|【防御时】|【阻擋時】|【阻挡时】|\[on block\])?"
            r"(?:【每回合1次】|\[once per turn\])?"
            r"(.{0,280})",
            blob,
            re.I,
        )
        if m2:
            chunk = m2.group(0)
            break
    if not chunk:
        chunk = text

    don_n = 0
    m_don = re.search(
        r"(?:\[DON!!\s*x\s*(\d+)\]|【咚‼?\s*[×xX]\s*(\d+)】).{0,40}?(?:\[When Attacking\]|【攻擊時】|【攻击时】)|"
        r"(?:\[When Attacking\]|【攻擊時】|【攻击时】).{0,40}?(?:\[DON!!\s*x\s*(\d+)\]|【咚‼?\s*[×xX]\s*(\d+)】)",
        text,
        re.I,
    )
    if m_don:
        don_n = int(next(g for g in m_don.groups() if g) or 1)

    # Choose a Character → copy its power into this card's base.
    if re.search(
        r"(?:choose|select).{0,40}[Cc]haracter.{0,80}base power becomes the same|"
        r"(?:選擇|选择)最多1張.{0,20}角色卡.{0,80}原本.{0,20}力量.{0,40}(?:選擇|选择)的角色卡|"
        r"變成和選擇的角色卡的力量|变成和选择的角色卡的力量",
        chunk,
        re.I,
    ):
        out: dict[str, Any] = {
            "timing": "when_attacking",
            "summary": "When Attacking: choose a Character; base power becomes that Character's power",
            "ops": [
                {
                    "op": "set_base_power_from_character",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "require_don_attached_gte": don_n,
                    "summary": "Choose a Character to copy power from",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
        if don_n:
            out["require_don_attached_gte"] = don_n
        return out

    # Copy opponent Leader's power into this card's base.
    if re.search(
        r"(?:base power becomes the same as your opponent'?s Leader'?s power)|"
        r"(?:power becomes the same as your opponent'?s Leader'?s power)|"
        r"(?:這張角色卡的原本力量值.{0,40}對手的領航卡.{0,16}相同)|"
        r"(?:这张角色卡的原本力量值.{0,40}对手的领航卡.{0,16}相同)|"
        r"(?:原本力量[值]?.{0,40}變成和對手的領航卡.{0,16}相同)|"
        r"(?:原本力量[值]?.{0,40}变成和对手的领航卡.{0,16}相同)",
        chunk,
        re.I,
    ):
        out = {
            "timing": "when_attacking",
            "summary": "When Attacking: base power becomes opponent Leader's power this turn",
            "ops": [
                {
                    "op": "set_base_power_from_opponent_leader",
                    "require_don_attached_gte": don_n,
                    "summary": "Set base power to opponent Leader's power",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
        if don_n:
            out["require_don_attached_gte"] = don_n
        return out

    # This Character's base power becomes N this turn (rare self fixed-set on attack).
    m_fix = re.search(
        r"(?:這張角色卡|这张角色卡|this [Cc]haracter).{0,40}(?:原本的?力量[值]?|base power).{0,24}"
        r"(?:變更成|变更成|becomes?)\s*(\d{3,5})",
        chunk,
        re.I,
    )
    if m_fix:
        out = {
            "timing": "when_attacking",
            "summary": f"When Attacking: base power becomes {m_fix.group(1)}",
            "ops": [
                {
                    "op": "set_base_power",
                    "amount": int(m_fix.group(1)),
                    "target_kind": "self",
                    "require_don_attached_gte": don_n,
                    "summary": f"Set base power to {m_fix.group(1)}",
                }
            ],
            "status": "compiled",
            "confidence": 0.75,
        }
        if don_n:
            out["require_don_attached_gte"] = don_n
        return out

    # This Character's power becomes equal to opponent Leader (total power, OP06-009).
    # Match on full text too — body often sits after 【防禦時】/【每回合1次】.
    if re.search(
        r"(?:這張角色卡.{0,60}力量值變成和對手的領航卡|这张角色卡.{0,60}力量值变成和对手的领航卡|"
        r"this [Cc]haracter.{0,80}becomes? the same power as your opponent'?s Leader|"
        r"this [Cc]haracter.{0,40}power becomes? the same as your opponent'?s Leader)",
        text,
        re.I,
    ) and not re.search(r"原本力量|base power", text, re.I):
        out = {
            "timing": "when_attacking",
            "summary": "When Attacking: power becomes equal to opponent Leader",
            "ops": [
                {
                    "op": "set_power_equal_opponent_leader",
                    "require_don_attached_gte": don_n,
                    "summary": "Set power equal to opponent Leader",
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
            "once": bool(re.search(r"每回合1次|once per turn", text, re.I)),
        }
        if don_n:
            out["require_don_attached_gte"] = don_n
        return out

    return None


def parse_continuous_base_power_copy(info: dict[str, Any]) -> dict[str, Any] | None:
    """
    Continuous base-power rewrite (not When Attacking).
    Example OP14-053: [Opponent's Turn] if hand ≤7, base power = your Leader's base power.
    """
    text = effect_blob(info)
    # Prefer opponent's turn aura copying own Leader base.
    m = re.search(
        r"(?:【對方回合中】|【对方回合中】|\[Opponent'?s Turn\]).{0,200}?"
        r"(?:這張角色卡的原本力量值|这张角色卡的原本力量值|this [Cc]haracter'?s base power).{0,40}"
        r"(?:變成和自己的領航卡的原本力量|变成和自己的领航卡的原本力量|becomes the same as your Leader'?s base power)",
        text,
        re.I | re.S,
    )
    if not m:
        return None
    chunk = m.group(0)
    out: dict[str, Any] = {
        "timing": "opponent_turn",
        "summary": chunk.strip()[:240],
        "ops": [{"op": "continuous_base_from_own_leader_printed"}],
        "status": "compiled",
        "confidence": 0.85,
    }
    m_hand = re.search(r"(?:手牌.{0,6}(\d+)\s*[張张]以下|(\d+)\s*or less cards? in your hand)", chunk, re.I)
    if m_hand:
        out["require_hand_lte"] = int(next(g for g in m_hand.groups() if g))
    return out


def parse_on_opponent_attack_base_power_copy(info: dict[str, Any]) -> dict[str, Any] | None:
    """
    [On Your Opponent's Attack] base becomes the attacking Leader/Character's power (OP04-069).
    """
    text = effect_blob(info)
    if not re.search(
        r"【對方攻擊時】|【对方攻击时】|【對方的攻擊時】|【对方的攻击时】|\[on your opponent'?s attack\]",
        text,
        re.I,
    ):
        return None
    if not re.search(
        r"(?:變成和對手進行攻擊的領航卡或角色卡|变成和对手进行攻击的领航卡或角色卡|"
        r"becomes the same as your opponent'?s attacking (?:Leader or )?Character|"
        r"becomes the same as the attacking)",
        text,
        re.I,
    ):
        return None
    ops: list[dict[str, Any]] = []
    m_ret = re.search(r"don!!\s*[−\-~－]\s*(\d+)|咚‼?\s*[−\-~－]\s*(\d+)", text, re.I)
    if m_ret:
        ops.append({"op": "return_don", "count": int(m_ret.group(1) or m_ret.group(2) or 1)})
    ops.append(
        {
            "op": "set_base_power_from_attacker",
            "summary": "Set base power to the attacking unit's power",
        }
    )
    return {
        "timing": "on_opponent_attack",
        "summary": "On Opponent's Attack: base power becomes the attacking unit's power",
        "ops": ops,
        "status": "compiled",
        "confidence": 0.85,
    }


def has_main_timing(info: dict[str, Any]) -> bool:
    text = effect_blob(info)
    return bool(re.search(r"【主要】|\[main\]", text, re.I))


def _main_effect_chunk(text: str) -> str:
    """Body of 【主要】 / [Main] up to the next timing tag.

    Events often print `[Main]/[Counter]` sharing one body — do not stop at that
    combined Counter marker. A separate `[Counter]` section on its own still ends Main.
    Mid-sentence `with a [Trigger]` must not truncate the Main body.
    """
    m = re.search(r"(?:【主要】|\[main\])", text, re.I)
    if not m:
        return ""
    rest = text[m.end() :]
    # Skip combined Counter marker right after Main ([Main]/[Counter] shared body).
    m_ctr = re.match(r"\s*/\s*(?:\[counter\]|【反擊】|【反击】)", rest, re.I)
    skip = 0
    if m_ctr:
        skip = m_ctr.end()
        rest = rest[skip:]
    stop = re.search(
        r"(?:"
        r"(?:^|[\n\r/])\s*【(?!主要)[^】]{0,16}】|"
        r"(?:^|[\n\r/])\s*\[(?!main\])(?:on\s+play|when\s+attacking|activate|trigger|counter|blocker|don!!|opponent|end of)\b|"
        # Separate Counter section after sentence end / whitespace (not the /Counter combo).
        r"(?<=[.。])\s*(?:\[counter\]|【反擊】|【反击】)|"
        r"\s+(?:\[counter\]|【反擊】|【反击】)"
        r")",
        rest,
        re.I | re.M,
    )
    # If we already skipped /Counter, don't stop at a Counter that is only the shared body.
    consumed = m.end() + skip
    end = consumed + (stop.start() if stop else min(len(rest), 500))
    return text[m.start() : end]


def _parse_leader_or_char_buff(chunk: str) -> dict[str, Any] | None:
    # Opponent Leader or Character −N / ?N (OCR) / -N
    m_opp = re.search(
        r"(?:give|gains?)(?:\s+up to\s*1\s+of)?\s+your opponent'?s\s+"
        r"(?:Leader or (?:1 of their )?Characters?|Leader or Character cards?|Characters?)"
        r".{0,40}([+\-−－?＋])\s*(\d{3,5})\s*power|"
        r"最多\s*1\s*[張张]對手的(?:領航卡或角色卡|领航卡或角色卡|角色卡).{0,24}力量(?:值)?\s*([+\-−－＋])\s*(\d{3,5})",
        chunk,
        re.I,
    )
    if m_opp:
        sign, num = (m_opp.group(1), m_opp.group(2)) if m_opp.lastindex >= 2 else (None, None)
        # Chinese form uses groups 3,4
        if m_opp.lastindex and m_opp.lastindex >= 4 and m_opp.group(3):
            sign, num = m_opp.group(3), m_opp.group(4)
        amt = int(num or 0)
        if sign and sign in "-−－?":
            amt = -abs(amt)
        elif sign and sign in "+＋":
            amt = abs(amt)
        else:
            amt = -abs(amt) if "opponent" in chunk.lower() or "對手" in chunk or "对手" in chunk else abs(amt)
        tk = (
            "opponent_leader_or_character"
            if re.search(r"Leader or|領航卡或|领航卡或", m_opp.group(0), re.I)
            else "opponent_character"
        )
        op = {
            "op": "buff",
            "amount": amt,
            "target_kind": tk,
            "optional": True,
            "summary": f"Opponent {'Leader/' if 'leader' in tk else ''}Character {amt:+d}",
        }
        if re.search(
            r"until the end of (?:your )?opponent'?s next end phase|"
            r"下一個對手結束階段結束前|下一个对手结束阶段结束前",
            chunk,
            re.I,
        ):
            op["duration"] = "until_opp_turn_end"
        return op
    m_buff = re.search(
        r"(?:your Leader or Character|自己的領航卡或角色卡|自己的领袖卡或角色卡|自己的領袖卡或角色卡).{0,48}"
        r"(?:gains?\s*\+?|力量(?:值)?\+)\s*(\d{3,5})",
        chunk,
        re.I,
    )
    if not m_buff:
        m_buff = re.search(
            r"(?:Leader or Character|領航卡或角色卡|领袖卡或角色卡|領袖卡或角色卡).{0,40}\+(\d{3,5})",
            chunk,
            re.I,
        )
    if not m_buff:
        # "Your Leader gains +1000 power during this turn"
        m_buff = re.search(
            r"(?:your Leader|自己的領航卡|自己的领航卡).{0,40}(?:gains?\s*\+?|力量(?:值)?\+)\s*(\d{3,5})",
            chunk,
            re.I,
        )
        if m_buff:
            op = {
                "op": "buff",
                "amount": int(m_buff.group(1)),
                "target_kind": "leader",
                "optional": False,
                "summary": "Leader gains power this turn",
            }
            if re.search(
                r"until the end of (?:your )?opponent'?s next end phase|"
                r"下一個對手結束階段結束前|下一个对手结束阶段结束前",
                chunk,
                re.I,
            ):
                op["duration"] = "until_opp_turn_end"
                op["summary"] = "Leader gains power until opponent End Phase"
            return op
    if not m_buff:
        return None
    return {
        "op": "buff",
        "amount": int(m_buff.group(1)),
        "target_kind": "own_character_or_leader",
        "optional": True,
        "summary": "Choose Leader or Character to buff",
    }


def _parse_place_on_bottom_ops(chunk: str) -> list[dict[str, Any]]:
    """
    Field Character → owner's deck bottom.
    Covers cost/power/base-cost filters, opponent-only, and multi-target ("up to 2" / dual clauses).
    Skips search leftovers and hand/trash reorder bottoms.
    """
    if not chunk:
        return []
    if not re.search(
        r"bottom of (?:its |the |your )?owner'?s deck|"
        r"bottom of your deck|"
        r"(?:持有者的)?卡[組组]下面|"
        r"牌[組组]下面",
        chunk,
        re.I,
    ):
        return []

    # Drop search-leftover / reveal-reorder sentences that also mention bottom.
    scrubbed = re.sub(
        r"(?:其餘|其余|the rest of the cards|remaining cards).{0,80}?(?:卡[組组]下面|bottom of)",
        " ",
        chunk,
        flags=re.I,
    )
    scrubbed = re.sub(
        r"(?:公開的卡片|revealed card).{0,40}?(?:卡[組组]下面|bottom)",
        " ",
        scrubbed,
        flags=re.I,
    )
    # Hand → bottom (not field Character).
    if not re.search(r"角色卡|Character", scrubbed, re.I):
        return []

    out: list[dict[str, Any]] = []

    def _emit(count: int, *, opponent: bool, filters: dict[str, Any], summary: str) -> None:
        n = max(1, min(3, int(count or 1)))
        base: dict[str, Any] = {
            "op": "return_to_bottom",
            "count": 1,
            "target_kind": "opponent_character" if opponent else "any_character",
            "optional": True,
            "summary": summary,
        }
        base.update(filters)
        for _ in range(n):
            out.append(dict(base))

    # English: "up to N [of your opponent's] Character(s) with ..."
    en_pat = re.compile(
        r"up to\s+(\d+)\s+(?:of your opponent'?s\s+)?Characters?"
        r"(?:\s+other than\s+\[[^\]]+\])?"
        r"(?:\s+with\s+(?:"
        r"(?:a\s+)?base\s+cost of\s+(\d+)(\s+or less)?|"
        r"(?:a\s+)?cost of\s+(\d+)(\s+or less)?|"
        r"(?:a\s+)?(?:base\s+)?power of\s+(\d+)\s+or less|"
        r"(\d+)\s+(?:base\s+)?power or less"
        r"))?"
        r"(?=[^.]{0,160}?bottom of (?:its |the )?owner'?s deck)",
        re.I,
    )
    for m in en_pat.finditer(scrubbed):
        window = scrubbed[max(0, m.start() - 24) : m.end() + 40]
        if re.search(r"from your (?:hand|trash|deck)|自己(?:手牌|廢棄|卡組)", window, re.I):
            continue
        opponent = bool(re.search(r"opponent'?s", m.group(0), re.I)) or bool(
            re.search(r"opponent'?s", scrubbed[max(0, m.start() - 30) : m.start() + 20], re.I)
        )
        filters: dict[str, Any] = {}
        if m.group(2):  # base cost
            n = int(m.group(2))
            if m.group(3):
                filters["cost_lte"] = n
            else:
                filters["cost_eq"] = n
        elif m.group(4):  # cost
            n = int(m.group(4))
            if m.group(5):
                filters["cost_lte"] = n
            else:
                filters["cost_eq"] = n
        elif m.group(6):
            filters["power_lte"] = int(m.group(6))
        elif m.group(7):
            filters["power_lte"] = int(m.group(7))
            if re.search(r"base power", m.group(0), re.I):
                filters["base_power_lte"] = filters.pop("power_lte")
        bits = []
        if opponent:
            bits.append("opponent")
        if "cost_lte" in filters:
            bits.append(f"cost ≤{filters['cost_lte']}")
        elif "cost_eq" in filters:
            bits.append(f"cost {filters['cost_eq']}")
        if "power_lte" in filters:
            bits.append(f"power ≤{filters['power_lte']}")
        if "base_power_lte" in filters:
            bits.append(f"base power ≤{filters['base_power_lte']}")
        summary = "Place Character on owner's deck bottom"
        if bits:
            summary = f"Place {' '.join(bits)} Character on owner's deck bottom"
        _emit(int(m.group(1)), opponent=opponent, filters=filters, summary=summary)

    if out:
        return out

    # Chinese: 「將最多N張…角色卡…卡組下面」 / 「將對手最多N張…」
    zh_pat = re.compile(
        r"(?:(?:將|将)(?:對手|对手)?|和)最多\s*(\d+)\s*[張张]"
        r"(?:對手|对手)?"
        r"(?:除了「[^」]+」以外)?"
        r"(?:"
        r"原本費用\s*(\d+)\s*以下|原本费用\s*(\d+)\s*以下|"
        r"原本費用\s*(\d+)(?!以下)|原本费用\s*(\d+)(?!以下)|"
        r"費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下|"
        r"費用\s*(\d+)(?!以下)|费用\s*(\d+)(?!以下)|"
        r"原本力量(?:值)?\s*(\d+)\s*以下|"
        r"力量(?:值)?\s*(\d+)\s*以下"
        r")?"
        r"(?:的)?(?:對手|对手)?角色卡",
        re.I,
    )
    # Require a bottom marker somewhere after the first match in the scrubbed main clause.
    if not re.search(r"角色卡.{0,40}(?:持有者的)?卡[組组]下面", scrubbed, re.I):
        # English already handled; Chinese without 角色卡…下面 — bail
        if not re.search(r"Character.{0,80}bottom of", scrubbed, re.I):
            return out

    for m in zh_pat.finditer(scrubbed):
        after = scrubbed[m.end() : m.end() + 50]
        # Dual clause: "...角色卡和最多1張..." shares one trailing bottom — accept if bottom still ahead.
        ahead = scrubbed[m.start() : m.start() + 200]
        if not re.search(r"卡[組组]下面|bottom of", ahead, re.I):
            continue
        if re.search(r"其餘|其余", ahead[:80]):
            continue
        if re.search(r"手牌|廢棄區|废弃区|卡組上面|卡组上面", m.group(0)):
            continue
        opponent = bool(re.search(r"對手|对手", scrubbed[max(0, m.start() - 4) : m.end()]))
        filters = {}
        if m.group(2) or m.group(3):
            filters["cost_lte"] = int(m.group(2) or m.group(3))
        elif m.group(4) or m.group(5):
            filters["cost_eq"] = int(m.group(4) or m.group(5))
        elif m.group(6) or m.group(7):
            filters["cost_lte"] = int(m.group(6) or m.group(7))
        elif m.group(8) or m.group(9):
            filters["cost_eq"] = int(m.group(8) or m.group(9))
        elif m.group(10):
            filters["base_power_lte"] = int(m.group(10))
        elif m.group(11):
            filters["power_lte"] = int(m.group(11))
        bits = []
        if opponent:
            bits.append("對手")
        if "cost_lte" in filters:
            bits.append(f"費用≤{filters['cost_lte']}")
        elif "cost_eq" in filters:
            bits.append(f"費用{filters['cost_eq']}")
        if "power_lte" in filters:
            bits.append(f"力量≤{filters['power_lte']}")
        if "base_power_lte" in filters:
            bits.append(f"原本力量≤{filters['base_power_lte']}")
        summary = "將角色卡放到持有者的卡組下面"
        if bits:
            summary = f"將{' '.join(bits)}的角色卡放到持有者的卡組下面"
        _emit(int(m.group(1)), opponent=opponent, filters=filters, summary=summary)

    # No-filter: 「將最多1張角色卡放置在持有者的卡組下面」 / Place up to 1 Character at the bottom
    if not out:
        m_any = re.search(
            r"(?:place up to\s+(\d+)\s+(?:of your opponent'?s\s+)?Characters?\s+at the bottom of (?:the owner'?s|your) deck)|"
            r"(?:將|将)(?:對手|对手)?最多\s*(\d+)\s*[張张](?:對手|对手)?角色卡.{0,20}(?:持有者的)?卡[組组]下面",
            scrubbed,
            re.I,
        )
        if m_any:
            count = int(m_any.group(1) or m_any.group(2) or 1)
            opponent = bool(re.search(r"opponent|對手|对手", m_any.group(0), re.I))
            _emit(
                count,
                opponent=opponent,
                filters={},
                summary="Place Character on owner's deck bottom",
            )

    # Own Character with power/cost filter → your deck bottom (EB01-011 style).
    if not out:
        m_own = re.search(
            r"place\s+(\d+)\s+of your Characters?(?: with\s+(\d+)\s+base power)?\s+at the bottom of your deck|"
            r"(?:將|将)\s*(\d+)\s*[張张]自己(?:原本力量值\s*(\d+))?的角色卡.{0,20}卡[組组]下面",
            scrubbed,
            re.I,
        )
        if m_own:
            count = int(next(g for g in (m_own.group(1), m_own.group(3)) if g))
            filters: dict[str, Any] = {}
            pow_n = m_own.group(2) or m_own.group(4)
            if pow_n:
                n_pow = int(pow_n)
                filters["base_power_lte"] = n_pow
                filters["base_power_gte"] = n_pow
            _emit(count, opponent=False, filters=filters, summary="Place own Character on deck bottom")

    # Self + hand → bottom (hand_to_deck style cost).
    if re.search(
        r"place this (?:card|Character).{0,40}(?:and \d+ card from your hand)?.{0,40}bottom of your deck|"
        r"(?:將|将)這[張张].{0,20}和\s*\d+\s*[張张]手牌.{0,20}卡[組组]下面|"
        r"(?:將|将)这[张張].{0,20}和\s*\d+\s*[张張]手牌.{0,20}卡[組组]下面",
        scrubbed,
        re.I,
    ):
        m_n = re.search(r"and\s+(\d+)\s+card|和\s*(\d+)\s*[張张]手牌", scrubbed, re.I)
        n_hand = int(next((g for g in (m_n.groups() if m_n else ()) if g), "1"))
        out.append(
            {
                "op": "hand_to_deck",
                "count": max(1, min(5, n_hand + 1)),
                "position": "bottom",
                "include_self": True,
                "optional": True,
                "as_cost": True,
                "summary": "Place this card and hand card(s) at deck bottom",
            }
        )

    return out


def _parse_return_char_to_hand_ops(chunk: str) -> list[dict[str, Any]]:
    """Return up to 1 Character (optionally cost-filtered) to owner's hand."""
    if not chunk:
        return []
    if not re.search(
        r"return up to\s*\d+.{0,80}Character.{0,60}hand|"
        r"(?:將|将)最多\s*\d+\s*[張张].{0,50}角色卡.{0,30}(?:放回|返回)持有者的手牌",
        chunk,
        re.I,
    ):
        return []
    # Avoid pure colon-cost lines without "up to".
    if re.search(r"^(?:可[將将]|You may return).{0,80}手牌\s*[:：]", chunk.strip(), re.I):
        return []
    opponent = bool(re.search(r"opponent'?s|對手的|对手的", chunk, re.I))
    op: dict[str, Any] = {
        "op": "return_to_hand",
        "target_kind": "opponent_character" if opponent else "any_character",
        "optional": True,
        "summary": "Return a Character to its owner's hand",
    }
    m_cost = re.search(
        r"(?:cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下)",
        chunk,
        re.I,
    )
    if m_cost:
        op["cost_lte"] = int(next(g for g in m_cost.groups() if g))
    return [op]


def parse_main_event(info: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Parse common 【主要】 event templates used when playing an Event in Main.
    Example OP05-057: buff your Leader/Character +3000, then bottom a cost≤2 Character.
    """
    if not has_main_timing(info):
        return []
    text = effect_blob(info)
    chunk = _main_effect_chunk(text) or text
    ops: list[dict[str, Any]] = []

    # Optional DON rest cost before colon (OP13-058).
    if re.search(
        r"(?:you may rest\s*\d+\s*of your don|可將\s*\d+\s*[張张]?自己的咚.{0,12}置為休息|可将\s*\d+\s*[张张]?自己的咚.{0,12}置为休息)",
        chunk,
        re.I,
    ):
        m_n = re.search(r"(?:rest\s*(\d+)|可[將将]\s*(\d+))", chunk, re.I)
        ops.append({"op": "rest_don", "count": max(1, int((m_n.group(1) or m_n.group(2)) if m_n else 1))})

    buff = _parse_leader_or_char_buff(chunk)
    if buff:
        ops.append(buff)

    if re.search(r"draw 2|抽2張|抽2张|抽2", chunk, re.I):
        ops.append({"op": "draw", "count": 2})
    elif re.search(r"draw 1|抽1張|抽1张|抽1(?!\d)", chunk, re.I):
        ops.append({"op": "draw", "count": 1})

    ops.extend(_parse_place_on_bottom_ops(chunk))
    ops.extend(_parse_return_char_to_hand_ops(chunk))
    ops.extend(_parse_cost_reduce_family_ops(chunk))
    ops.extend(_parse_deny_blocker_ops(chunk))
    ops.extend(_parse_allow_attack_active_ops(chunk))
    ops.extend(_parse_grant_keyword_ops(chunk))
    ops.extend(_parse_replace_battle_ko_ops(chunk))
    ops.extend(_parse_cannot_take_life_ops(chunk))
    ops.extend(_parse_skip_untap_ops(chunk))
    ops.extend(_parse_ko_own_any_buff_leader_ops(chunk))
    ops.extend(_parse_negate_effects_ops(chunk))
    ops.extend(_parse_trash_to_bottom_ops(chunk))
    ops.extend(_parse_set_active_ops(chunk))
    ops.extend(_parse_restriction_ops(chunk))
    ops.extend(_parse_hand_to_deck_ops(chunk))
    ops.extend(_parse_reveal_opp_hand_ops(chunk))
    ops.extend(_parse_grant_cost_ops(chunk))
    ops.extend(_parse_redirect_attack_ops(chunk))
    ops.extend(_parse_trash_hand_down_to_ops(chunk))
    ops.extend(_parse_skip_untap_ops(chunk))
    ops.extend(_parse_cannot_take_life_ops(chunk))
    ops.extend(_parse_deny_attack_ops(chunk))
    ops.extend(_parse_deny_rest_ops(chunk))
    ops.extend(_parse_set_cost_ops(chunk))
    ops.extend(_parse_trash_opponent_char_ops(chunk))
    # Rest with cost filter (e.g. 對手費用0的角色卡置為休息)
    if re.search(
        r"rest up to 1 of your opponent|將最多1[張张]對手.{0,40}置為休息|将最多1[张張]对手.{0,40}置为休息",
        chunk,
        re.I,
    ):
        existing = next((o for o in ops if o.get("op") == "rest_opponent_character"), None)
        if existing is None:
            rest_op = {"op": "rest_opponent_character", "count": 1}
            ops.append(rest_op)
            existing = rest_op
        m_ceq = re.search(r"(?:費用|费用)\s*(\d+)\s*的角色|cost of\s*(\d+)(?!\s*or less)", chunk, re.I)
        if m_ceq and existing.get("cost_eq") is None:
            existing["cost_eq"] = int(m_ceq.group(1) or m_ceq.group(2))
        m_clte = re.search(r"(?:費用|费用)\s*(\d+)\s*以下|cost of\s*(\d+)\s*or less", chunk, re.I)
        if m_clte and existing.get("cost_lte") is None:
            existing["cost_lte"] = int(m_clte.group(1) or m_clte.group(2))
    life_ops = _parse_life_zone_ops(chunk)
    if life_ops:
        cost_life = [o for o in life_ops if o.get("as_cost")]
        rest_life = [o for o in life_ops if not o.get("as_cost")]
        if cost_life and not any(o.get("as_cost") for o in ops):
            ops = cost_life + ops
        for o in rest_life:
            if not any(x.get("op") == o.get("op") and x.get("owner") == o.get("owner") for x in ops):
                ops.append(o)
    # Dual KO by base cost (OP10-098 Liberation).
    if re.search(r"k\.?o\.?|KO", chunk, re.I):
        seen_costs: set[int] = set()
        for m_ko in re.finditer(
            r"up to\s*1 of your opponent'?s Characters with a base cost of\s*(\d+)\s*or less|"
            r"最多1張原本費用\s*(\d+)\s*以下|最多1张原本费用\s*(\d+)\s*以下",
            chunk,
            re.I,
        ):
            cost_lte = int(next(g for g in m_ko.groups() if g))
            if cost_lte in seen_costs:
                continue
            seen_costs.add(cost_lte)
            ops.append(
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": cost_lte,
                    "summary": f"K.O. up to 1 opponent Character with base cost ≤{cost_lte}",
                }
            )
    # Add card with [Trigger] from trash to hand (OP16-115).
    if re.search(
        r"add up to 1 card with a \[trigger\].{0,80}from your trash to your hand|"
        r"將最多1張自己廢棄區中.{0,40}【觸發器】.{0,40}加入手牌|"
        r"将最多1张自己废弃区中.{0,40}【触发器】.{0,40}加入手牌",
        chunk,
        re.I,
    ):
        ops.append(
            {
                "op": "add_from_trash",
                "count": 1,
                "optional": True,
                "require_trigger": True,
                "name_exclude": "Black Vortex",
                "summary": "Add up to 1 [Trigger] card from trash to hand",
            }
        )
    play_zone = _parse_play_from_zone(chunk)
    if play_zone and not any(o.get("op") == "play_from_hand" for o in ops):
        ops.append(play_zone)

    return ops


def has_counter_timing(info: dict[str, Any]) -> bool:
    text = effect_blob(info)
    if re.search(r"【反撃】|【反击】|【反擊】|\[counter\]", text, re.I):
        return True
    return False


def event_playable_in_main(info: dict[str, Any]) -> bool:
    """Events with only Counter timing cannot be played in the Main phase (10-2-3 / 10-2-4)."""
    if has_main_timing(info):
        return True
    if has_counter_timing(info):
        return False
    # Ambiguous text: allow if no explicit Counter keyword.
    return True


def max_deck_copies(info: dict[str, Any]) -> int:
    text = effect_blob(info)
    if re.search(r"any number of this card|可不限張數放入卡組|可不限张数放入卡组", text, re.I):
        return 50
    return 4



def _opp_end_expire_seat(controller_seat: int) -> int:
    """Paper 「下一個對手結束階段結束前」expires at the controller's opponent End Phase."""
    return 1 - int(controller_seat)


def _duration_is_until_opp_end(duration: str | None) -> bool:
    d = str(duration or "").strip().lower()
    return d in {"until_opp_turn_end", "until_opp_end", "next_opp_end"}


def _set_leader_base_power(player, *, amount: int, printed: int, duration: str, controller_seat: int) -> None:
    """Rewrite Leader printed power. until_opp_turn_end must not use leader_power_mod
    (that bucket is wiped at every End Phase, including the controller's own)."""
    delta = int(amount) - int(printed)
    if _duration_is_until_opp_end(duration):
        kept = [e for e in (player.leader_power_until_end or []) if not e.get("set_base")]
        kept.append(
            {
                "amount": delta,
                "expire_seat": _opp_end_expire_seat(controller_seat),
                "set_base": True,
            }
        )
        player.leader_power_until_end = kept
        return
    player.leader_power_mod = delta


def _place_cid_on_life(player, cid: str, *, top: bool = True, face_up: bool = False) -> None:
    """Put a card id onto Life; keep life_face aligned when faces are tracked."""
    if top:
        player.life.insert(0, cid)
    else:
        player.life.append(cid)
    if player.life_face or face_up:
        while len(player.life_face) < len(player.life) - 1:
            player.life_face.append(False)
        if top:
            player.life_face.insert(0, bool(face_up))
        else:
            player.life_face.append(bool(face_up))
        while len(player.life_face) < len(player.life):
            player.life_face.append(False)


def _deliver_trash_card(player, cid: str, op: dict[str, Any]) -> str:
    dest = str(op.get("destination") or "hand").strip().lower()
    if dest == "life":
        face_up = str(op.get("face") or "down").strip().lower() == "up"
        top = str(op.get("position") or "top").strip().lower() != "bottom"
        _place_cid_on_life(player, cid, top=top, face_up=face_up)
        return "life"
    player.hand.append(cid)
    return "hand"


def _apply_negate_to_target(foe, target: str, duration: str | None, controller_seat: int) -> bool:
    """Negate Leader or Character effects for this turn or until opp End Phase."""
    until = _duration_is_until_opp_end(duration)
    expire = _opp_end_expire_seat(controller_seat)
    is_lead = target == "leader" or target == f"leader-{foe.seat}"
    if is_lead:
        if until:
            foe.leader_effects_negated_until_end.append({"expire_seat": expire})
        else:
            foe.leader_effects_negated = True
        return True
    inst = next((c for c in foe.characters if c.iid == target), None)
    if not inst:
        return False
    if until:
        inst.effects_negated_until_end.append({"expire_seat": expire})
    else:
        inst.effects_negated = True
    return True


def _victim_on_ko_ops(state, owner_seat: int, ko_cid: str, ko_iid: str, catalog) -> list[dict[str, Any]]:
    """Ops for the KO'd card's [On K.O.] (gates already applied by resolve_ability)."""
    try:
        from battle.effect_library import resolve_ability

        info = catalog(ko_cid) if catalog else {}
        pending = resolve_ability(
            state, owner_seat, ko_cid, ko_iid, "on_ko", info, None, allow_llm=False, catalog=catalog
        )
    except Exception:
        return []
    if not pending or not pending.ops:
        return []
    out: list[dict[str, Any]] = []
    for o in pending.ops:
        if not isinstance(o, dict) or str(o.get("op") or "") == "unsupported":
            continue
        oo = dict(o)
        oo.setdefault("source_iid", ko_iid)
        oo.setdefault("card_id", ko_cid)
        # Victim [On K.O.] must resolve as the KO'd card's owner, not the KO controller.
        oo["_as_seat"] = owner_seat
        out.append(oo)
    return out


def _apply_timed_power_mod(
    owner,
    *,
    amount: int,
    duration: str | None,
    controller_seat: int,
    on_leader: bool,
    inst=None,
) -> None:
    """Route power into this-turn mod, this-battle bucket, or until-opp-end bucket."""
    if _duration_is_until_opp_end(duration):
        entry = {"amount": int(amount), "expire_seat": _opp_end_expire_seat(controller_seat)}
        if on_leader:
            owner.leader_power_until_end.append(entry)
        elif inst is not None:
            inst.power_until_end.append(entry)
        return
    if str(duration or "").strip().lower() == "battle":
        entry = {"amount": int(amount), "expire_kind": "battle"}
        if on_leader:
            owner.leader_power_until_end.append(entry)
        elif inst is not None:
            inst.power_until_end.append(entry)
        return
    if on_leader:
        owner.leader_power_mod += int(amount)
    elif inst is not None:
        inst.power_mod += int(amount)


def _infer_buff_target_kind(op: dict[str, Any]) -> str:
    """Default target pool when encoding omitted target_kind (common on −power debuffs)."""
    tk = str(op.get("target_kind") or "").strip().lower()
    if tk:
        return tk
    amount = int(op.get("amount") or 0)
    if amount < 0:
        return "opponent_character"
    return "own_leader_or_character"


def _annotate_buff_duration_from_text(op: dict, blob: str) -> dict:
    """If paper says until next opponent End Phase, stamp duration on buff ops."""
    out = dict(op)
    if out.get("duration"):
        return out
    if re.search(
        r"until the end of (?:your )?opponent'?s next end phase|"
        r"下一個對手的?結束階段結束(?:時)?前|下一个对手的?结束阶段结束(?:时)?前|"
        r"次の相手のエンドフェイズ終了時まで|"
        r"until the end of your opponent'?s turn",
        blob,
        re.I,
    ):
        # Prefer opp-end when that phrase appears near the power change for this op.
        out["duration"] = "until_opp_turn_end"
    return out

def live_keywords(
    info: dict[str, Any],
    inst: CardInst | None = None,
    *,
    state: Any | None = None,
    owner_seat: int | None = None,
    catalog: Any | None = None,
) -> list[str]:
    """Innate + this-turn grants + permanent grants (ignores stale false summon keywords)."""
    innate = detect_keywords(info)
    turn = list((inst.turn_keywords if inst else None) or [])
    until = [
        str(e.get("keyword") or "")
        for e in ((inst.keywords_until_end if inst else None) or [])
        if e.get("keyword")
    ]
    blob = effect_blob(info)
    # Cards that only *grant* Blocker to another unit must not keep a self Blocker
    # leftover from older detect_keywords / bad compile (OP16-048).
    # Self DON!!xN / "this Character gains Blocker" is NOT grant-only.
    self_blocker_grant = bool(
        re.search(
            r"這張角色卡獲得【防禦】|这张角色卡获得【防御】|"
            r"this character gains? \[blocker\]|"
            r"(?:【咚‼?\s*[×xX]\s*\d+】|\[don!!\s*x\s*\d+\]).{0,60}"
            r"(?:獲得【防禦】|获得【防御】|gains? \[blocker\])",
            blob,
            re.I,
        )
    )
    grant_only_blocker = (
        "blocker" not in innate
        and not self_blocker_grant
        and bool(re.search(r"獲得【防禦】|获得【防御】|gains? \[Blocker\]|gain \[Blocker\]", blob, re.I))
    )
    grant_only_rush = "rush" not in innate and "rush_character" not in innate and bool(
        re.search(
            r"獲得【速攻】|获得【速攻】|獲得【速攻：角色】|获得【速攻：角色】|gains? \[Rush\]|gain \[Rush\]",
            blob,
            re.I,
        )
    )
    self_blockerless_grant = bool(
        re.search(
            r"這張角色卡獲得【防禦不可】|这张角色卡获得【防御不可】|"
            r"this character gains? \[unblockable\]|"
            r"this character gains? \[blockerless\]",
            blob,
            re.I,
        )
    )
    grant_only_blockerless = not self_blockerless_grant and bool(
        re.search(
            r"獲得【防禦不可】|获得【防御不可】|獲得【不可阻擋】|获得【不可阻挡】|"
            r"gains? \[Unblockable\]|gain \[Unblockable\]|gains? \[Blockerless\]",
            blob,
            re.I,
        )
    )
    if grant_only_blockerless:
        innate = [k for k in innate if k != "blockerless"]
    perm: list[str] = []
    for k in (inst.keywords if inst else None) or []:
        if k == "blocker" and grant_only_blocker:
            continue
        if k in {"rush", "rush_character"} and grant_only_rush:
            continue
        if k == "blockerless" and grant_only_blockerless:
            continue
        if k not in innate and k not in turn and k not in until:
            perm.append(k)
    keys = list(dict.fromkeys([*innate, *turn, *until, *perm]))
    # Continuous DON!!xN self grants (OP15-053 etc.) — must show in UI / public keywords.
    if inst is not None:
        keys = _merge_continuous_self_keyword_grants(
            keys, inst, state=state, owner_seat=owner_seat, catalog=catalog
        )
    return keys


def _merge_continuous_self_keyword_grants(
    keys: list[str],
    inst: CardInst,
    *,
    state: Any | None = None,
    owner_seat: int | None = None,
    catalog: Any | None = None,
) -> list[str]:
    """Append live self grant_keyword from your_turn/opponent_turn continuous gates."""
    out = list(keys)
    try:
        from battle.effect_library import ability_is_runnable, get_abilities

        want = {"blocker", "rush", "rush_character", "double_attack", "banish"}
        missing = [k for k in want if k not in out]
        if not missing:
            return out
        don = int(inst.don_attached or 0)

        def _kw_from_op(o: dict, *, src_iid: str) -> str | None:
            if str(o.get("op") or "") != "grant_keyword":
                return None
            kw = str(o.get("keyword") or "").strip().lower()
            if kw not in missing:
                return None
            tk = str(o.get("target_kind") or "self").strip().lower()
            trait = str(o.get("trait_contains") or o.get("trait_includes") or "").strip()
            board_wide = bool(o.get("all") or trait or o.get("name_contains") or o.get("trait_all") or o.get("trait_any"))
            if tk in {"", "self"}:
                if src_iid != inst.iid:
                    return None
            elif tk in {"own_character", "own_characters", "all_own"}:
                if not board_wide and src_iid != inst.iid:
                    return None
            else:
                return None
            if trait or o.get("trait_all") or o.get("trait_any"):
                from battle.engine import _op_traits_ok

                victim = catalog(inst.card_id) if catalog else info
                if not _op_traits_ok(victim or {}, o):
                    return None
            return kw

        def _ability_ok(ab: dict, *, src_iid: str, src_don: int) -> bool:
            if not ability_is_runnable(ab):
                return False
            need = int(ab.get("require_don_attached_gte") or 0)
            if need > 0 and src_don < need:
                return False
            other_gates = [
                k
                for k in ab
                if str(k).startswith("require_") and k != "require_don_attached_gte"
            ]
            if other_gates:
                if state is None or owner_seat is None or catalog is None:
                    return False
                from battle.engine import _ability_board_conditions_ok

                return _ability_board_conditions_ok(
                    state,
                    owner_seat,
                    ab,
                    catalog,
                    don_attached=src_don,
                    source_iid=src_iid,
                )
            return True

        my_turn_self = None
        if state is not None and owner_seat is not None:
            my_turn_self = state.turn_seat == owner_seat

        for timing in ("your_turn", "opponent_turn", "don_attached"):
            if my_turn_self is not None:
                if timing == "your_turn" and not my_turn_self:
                    continue
                if timing == "opponent_turn" and my_turn_self:
                    continue
            for ab in get_abilities(inst.card_id, timing):
                if not _ability_ok(ab, src_iid=inst.iid, src_don=don):
                    continue
                for o in ab.get("ops") or []:
                    kw = _kw_from_op(o, src_iid=inst.iid)
                    if not kw:
                        continue
                    out.append(kw)
                    missing = [k for k in missing if k != kw]
                    if not missing:
                        return list(dict.fromkeys(out))

        if state is not None and owner_seat is not None and catalog is not None and missing:
            player = state.player(owner_seat)
            my_turn = state.turn_seat == owner_seat
            sources: list[tuple[str, str, int]] = [
                ("leader", player.leader_card_id, int(player.leader_don or 0)),
                *[(c.iid, c.card_id, int(c.don_attached or 0)) for c in player.characters],
                *[(s.iid, s.card_id, 0) for s in player.stages],
            ]
            for src_iid, cid, src_don in sources:
                if src_iid == inst.iid:
                    continue
                for timing in ("your_turn", "opponent_turn"):
                    if timing == "your_turn" and not my_turn:
                        continue
                    if timing == "opponent_turn" and my_turn:
                        continue
                    for ab in get_abilities(cid, timing):
                        if not _ability_ok(ab, src_iid=src_iid, src_don=src_don):
                            continue
                        for o in ab.get("ops") or []:
                            kw = _kw_from_op(o, src_iid=src_iid)
                            if not kw:
                                continue
                            out.append(kw)
                            missing = [k for k in missing if k != kw]
                            if not missing:
                                return list(dict.fromkeys(out))
    except Exception:
        return out
    return list(dict.fromkeys(out))


def has_blocker(
    info: dict[str, Any],
    inst: CardInst | None = None,
    *,
    state: Any | None = None,
    owner_seat: int | None = None,
    catalog: Any | None = None,
) -> bool:
    return "blocker" in live_keywords(
        info, inst, state=state, owner_seat=owner_seat, catalog=catalog
    )


def has_rush(
    info: dict[str, Any],
    inst: CardInst | None = None,
    *,
    state: Any | None = None,
    owner_seat: int | None = None,
    catalog: Any | None = None,
) -> bool:
    return "rush" in live_keywords(
        info, inst, state=state, owner_seat=owner_seat, catalog=catalog
    )


def has_rush_character(
    info: dict[str, Any],
    inst: CardInst | None = None,
    *,
    state: Any | None = None,
    owner_seat: int | None = None,
    catalog: Any | None = None,
) -> bool:
    return "rush_character" in live_keywords(
        info, inst, state=state, owner_seat=owner_seat, catalog=catalog
    )


def has_banish(info: dict[str, Any], inst: CardInst | None = None) -> bool:
    return "banish" in live_keywords(info, inst)


def has_double_attack(info: dict[str, Any], inst: CardInst | None = None) -> bool:
    return "double_attack" in live_keywords(info, inst)


def has_blockerless(info: dict[str, Any], inst: CardInst | None = None) -> bool:
    return "blockerless" in live_keywords(info, inst)


def _on_play_chunk(text: str) -> str:
    """Extract On Play body without stopping at English [Name] / keyword brackets."""
    m = re.search(r"(?:\[on play\]|【登場時】|【登场时】)", text, re.I)
    if not m:
        return text
    rest = text[m.end() :]
    # Shared timing: [On Play]/[When Attacking] EFFECT — body belongs to both.
    shared = re.match(
        r"\s*/\s*(?:\[when attacking\]|【攻擊時】|【攻击时】)\s*",
        rest,
        re.I,
    )
    if shared:
        rest = rest[shared.end() :]
        stop = re.search(
            r"(?=【(?:啟動主要|启动主要|KO時|KO时|觸發器|触发器|反擊|反击|阻擋時|阻挡时|"
            r"對方的?攻擊時|对方的?攻击时|我方回合中|對方回合中|对方回合中)】|"
            r"\[(?:activate(?:\s*:\s*main)?|on\s*k\.?o\.?|trigger|counter|on\s+block|"
            r"on\s+your\s+opponent'?s\s+attack|your\s+turn|opponent'?s\s+turn)\])",
            rest,
            re.I,
        )
        end = m.end() + shared.end() + (stop.start() if stop else min(len(rest), 600))
        return text[m.start() : end]
    # Stop at a new timing tag, not at keyword brackets like [Trigger]/[Blocker] mid-sentence.
    stop = re.search(
        r"(?=【(?:攻擊時|攻击时|啟動主要|启动主要|KO時|KO时|反擊|反击|阻擋時|阻挡时|"
        r"對方的?攻擊時|对方的?攻击时|我方回合中|對方回合中|对方回合中|我方的?回合結束時|我方的?回合结束时)】|"
        r"(?:\n|\r|/)\s*【(?:觸發器|触发器)】|"
        r"\[(?:when\s+attacking|activate(?:\s*:\s*main)?|on\s*k\.?o\.?|counter|"
        r"on\s+block|on\s+your\s+opponent'?s\s+attack|your\s+turn|opponent'?s\s+turn|"
        r"end\s+of\s+your\s+turn)\]|"
        r"(?:\n|\r|/)\s*\[trigger\])",
        rest,
        re.I,
    )
    end = m.end() + (stop.start() if stop else min(len(rest), 600))
    return text[m.start() : end]


def _parse_attach_don_ops(chunk: str) -> list[dict[str, Any]]:
    """Give/attach DON!! from DON!! deck onto Leader/Character (not cost-area gain_don)."""
    ops: list[dict[str, Any]] = []
    # Must be an explicit attach/give onto a unit — not "add DON!! … set it as active" (cost area).
    if re.search(
        r"從(?:自己的)?咚‼?卡組追加.{0,40}咚.{0,20}(?:並)?(?:置為|设为|set).{0,12}(?:活動|活动|active)|"
        r"add.{0,40}DON!!.{0,40}(?:from your DON!! deck).{0,40}set it as active",
        chunk,
        re.I,
    ) and not re.search(r"附加|attach|give.{0,20}(?:this|Leader|Character)", chunk, re.I):
        return ops
    m = re.search(
        r"(?:附加|給予|给予|give|attach).{0,40}?(?:最多)?\s*(\d+)\s*張?.{0,12}?(?:休息|活動|rested|active)?.{0,12}?咚|"
        r"(?:give|attach).{0,24}?(?:up to )?(\d+).{0,24}?DON!!",
        chunk,
        re.I,
    )
    if not m and re.search(
        r"從(?:自己的)?咚‼?卡組追加(?:最多)?\s*\d+\s*張?(?:休息|活動)狀態的咚.{0,40}(?:附加|給|给)|"
        r"(?:give|attach).{0,40}DON!!.{0,40}(?:Leader|Character|領航|领航|角色)",
        chunk,
        re.I,
    ):
        m_n = re.search(r"(?:最多)?\s*(\d+)\s*張|up to\s*(\d+)|(\d+)\s*DON", chunk, re.I)
        n = int(next((g for g in (m_n.groups() if m_n else ()) if g), "1"))
        as_rested = bool(re.search(r"休息|rested", chunk, re.I))
        tk = "leader" if re.search(r"領航|领航|Leader", chunk, re.I) else "self"
        if re.search(r"自己的角色|your Character|選擇.{0,10}角色|选择.{0,10}角色", chunk, re.I):
            tk = "own_character"
        op_ad: dict[str, Any] = {"op": "attach_don", "count": n, "as_rested": as_rested, "target_kind": tk}
        # 「休息狀態的咚」= take from cost-area rested DON!! (not DON!! deck).
        if as_rested:
            op_ad["from_rested"] = True
        ops.append(op_ad)
        return ops
    if m:
        n = int(next((g for g in m.groups() if g), "1"))
        as_rested = bool(re.search(r"休息|rested", chunk, re.I))
        tk = "leader" if re.search(r"領航|领航|Leader", chunk, re.I) else "self"
        if re.search(r"自己的角色|your Character|選擇.{0,10}角色|选择.{0,10}角色", chunk, re.I):
            tk = "own_character"
        if re.search(r"領航卡或角色卡|Leader or Character|leader or character", chunk, re.I):
            tk = "own_leader_or_character"
        op_ad = {"op": "attach_don", "count": max(1, n), "as_rested": as_rested, "target_kind": tk}
        if as_rested:
            op_ad["from_rested"] = True
        m_trait = re.search(
            r"擁有《([^》]+)》特徵|拥有《([^》]+)》特征|\{([^}]+)\}\s*type",
            chunk,
            re.I,
        )
        if m_trait:
            trait = next((g for g in m_trait.groups() if g), "").strip()
            if trait:
                op_ad["trait_contains"] = trait
        ops.append(op_ad)
    return ops


def _parse_trash_hand_cost(chunk: str) -> list[dict[str, Any]]:
    """Optional 'you may trash N cards from your hand:' cost → trash_hand as_cost."""
    # Specific: trash 1 card with a [Trigger] from your hand
    if re.search(
        r"(?:you may )?trash\s*1\s*card with a \[Trigger\] from your hand\s*:|"
        r"(?:可以)?廢棄\s*1\s*張(?:自己手牌中)?持有【觸發器】的卡片\s*[：:]|"
        r"(?:可以)?废弃\s*1\s*张(?:自己手牌中)?持有【触发器】的卡片\s*[：:]|"
        r"(?:可以)?廢棄\s*1\s*張擁有【觸發器】的手牌\s*[：:]|"
        r"(?:可以)?废弃\s*1\s*张拥有【触发器】的手牌\s*[：:]",
        chunk,
        re.I,
    ):
        return [{"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "require_trigger": True}]
    m_trait = re.search(
        r"(?:you may )?trash\s*1\s*\{([^}]+)\}\s*type card from your hand\s*:|"
        r"(?:可以)?廢棄\s*1\s*張擁有《([^》]+)》特徵的手牌\s*[：:]|"
        r"(?:可以)?废弃\s*1\s*张拥有《([^》]+)》特征的手牌\s*[：:]",
        chunk,
        re.I,
    )
    if m_trait:
        trait = next((g for g in m_trait.groups() if g), "").strip()
        return [
            {
                "op": "trash_hand",
                "count": 1,
                "optional": True,
                "as_cost": True,
                "trait_contains": trait,
            }
        ]
    m = re.search(
        r"(?:可以)?廢棄\s*(\d+)\s*張自己的手牌\s*[：:]|"
        r"(?:可以)?废弃\s*(\d+)\s*张自己的手牌\s*[：:]|"
        r"you may trash\s*(\d+)\s*card.{0,24}from your hand\s*:",
        chunk,
        re.I,
    )
    if not m:
        return []
    n = int(next(g for g in m.groups() if g))
    return [{"op": "trash_hand", "count": n, "optional": True, "as_cost": True}]


def _parse_play_from_zone(chunk: str) -> dict[str, Any] | None:
    """Play from hand / trash / hand_or_trash."""
    # Play this Character from trash (On K.O. revival etc.)
    if re.search(
        r"play this Character(?: card)? from your trash|"
        r"使這張角色卡從廢棄區中登場|"
        r"使这张角色卡从废弃区中登场",
        chunk,
        re.I,
    ):
        return {
            "op": "play_from_hand",
            "count": 1,
            "card_type": "character",
            "optional": False,
            "from_zone": "trash",
            "self_card": True,
            "summary": "Play this Character from trash",
        }
    # trash-only or hand-or-trash
    m_trash = re.search(
        r"play up to\s*(\d+).{0,160}?from your trash(?:\s*(?:as )?rested)?|"
        r"使最多\s*(\d+)[張张].{0,100}?從廢棄區.{0,40}登場|"
        r"使最多\s*(\d+)[張张].{0,100}?从废弃区.{0,40}登场|"
        r"play up to\s*(\d+).{0,160}?from your hand or trash|"
        r"使最多\s*(\d+)[張张].{0,80}?(?:手牌或廢棄區|手牌或废弃区).{0,40}登場",
        chunk,
        re.I,
    )
    if m_trash:
        n = int(next(g for g in m_trash.groups() if g) or 1)
        text = m_trash.group(0)
        out: dict[str, Any] = {
            "op": "play_from_hand",
            "count": max(1, min(3, n)),
            "card_type": "character",
            "optional": True,
            "from_zone": "hand_or_trash" if re.search(r"hand or trash|手牌或", text, re.I) else "trash",
        }
        if re.search(r"(?:as )?rested|以休息狀態|以休息状态", text, re.I):
            out["as_rested"] = True
        m_name = re.search(r"「([^」]+)」|\[([^\]]+)\]", text)
        if m_name and not re.search(r"\[Trigger\]|【觸發|【触发", text, re.I):
            name = (m_name.group(1) or m_name.group(2) or "").strip()
            if name and name.lower() not in {"trigger", "blocker", "rush", "on play", "on k.o."}:
                out["name_contains"] = name
        m_trait = re.search(r"\{([^}]+)\}\s*type|擁有《([^》]+)》|拥有《([^》]+)》", text, re.I)
        if m_trait:
            out["trait_contains"] = next((g for g in m_trait.groups() if g), "").strip()
        m_cost = re.search(r"(?:with (?:a )?cost of|費用|费用)\s*(\d+)(\s*or less|以下)?", text, re.I)
        if m_cost:
            ncost = int(m_cost.group(1))
            if m_cost.group(2):
                out["cost_lte"] = ncost
            else:
                out["cost_eq"] = ncost
        return out
    # from deck
    m_deck = re.search(
        r"play up to\s*(\d+).{0,160}?from your deck|"
        r"使最多\s*(\d+)[張张].{0,100}?從(?:自己的)?卡組.{0,40}登場|"
        r"使最多\s*(\d+)[張张].{0,100}?从(?:自己的)?卡组.{0,40}登场",
        chunk,
        re.I,
    )
    if m_deck:
        n = int(next(g for g in m_deck.groups() if g) or 1)
        text = m_deck.group(0)
        out = {
            "op": "play_from_hand",
            "count": max(1, min(3, n)),
            "card_type": "character",
            "optional": True,
            "from_zone": "deck",
        }
        m_trait = re.search(r"\{([^}]+)\}\s*type|擁有《([^》]+)》|拥有《([^》]+)》", text, re.I)
        if m_trait:
            out["trait_contains"] = next((g for g in m_trait.groups() if g), "").strip()
        m_cost = re.search(r"(?:with (?:a )?cost of|費用|费用)\s*(\d+)(\s*or less|以下)?", text, re.I)
        if m_cost:
            ncost = int(m_cost.group(1))
            if m_cost.group(2):
                out["cost_lte"] = ncost
            else:
                out["cost_eq"] = ncost
        m_col = re.search(r"\b(green|red|blue|purple|black|yellow)\b|(綠|绿|紅|红|藍|蓝|紫|黑|黃|黄)色?", text, re.I)
        if m_col:
            rawc = next((g for g in m_col.groups() if g), "")
            cmap = {"綠": "green", "绿": "green", "紅": "red", "红": "red", "藍": "blue", "蓝": "blue", "紫": "purple", "黑": "black", "黃": "yellow", "黄": "yellow"}
            out["color"] = cmap.get(rawc, rawc.lower())
        return out
    return _parse_play_from_hand(chunk)


def _parse_replace_battle_ko_ops(chunk: str) -> list[dict[str, Any]]:
    if re.search(
        r"would be k\.?o\.?'?d.{0,80}trash 1 card from your hand instead|"
        r"遭到KO時.{0,40}廢棄1張.{0,12}手牌|"
        r"遭到KO时.{0,40}废弃1张.{0,12}手牌|"
        r"instead of being k\.?o\.?'?d.{0,40}trash 1 card from your hand",
        chunk,
        re.I,
    ):
        return [{"op": "replace_battle_ko"}]
    return []


def _parse_replace_leave_ops(chunk: str) -> list[dict[str, Any]]:
    """
    Continuous replacement shields paid from Life / hand / this Character:
    - ST09-010: if this Character would be K.O.'d, trash 1 Life instead (once/turn)
    - OP15-098: if filtered own Character would leave by opponent, Life→hand instead
    - OP05-100: if this Character would leave, trash 1 Life instead
    - OP13-047 / OP13-060: trash this Character instead of allied KO
    - OP12-027: rest this Character instead of allied KO
    - EB04-031: return 1 DON!! instead of KO
    """
    # If you would take damage, you may trash this Character instead (EB05-052)
    if re.search(
        r"if you would take damage.{0,80}trash this Character instead|"
        r"即將受到傷害時.{0,60}可以替換成將這張角色卡|"
        r"即将受到伤害时.{0,60}可以替换成将这张角色卡",
        chunk,
        re.I,
    ):
        return [
            {
                "op": "replace_life_damage",
                "optional": True,
                "cost": "trash_self",
                "summary": "You may trash this Character instead of taking damage",
            }
        ]
    # Self KO → return DON!! to DON deck
    if re.search(
        r"if this Character would be k\.?o\.?'?d.{0,100}"
        r"return\s*1\s*DON!! card from your field to your DON!! deck|"
        r"若這張角色卡即將遭到KO時.{0,60}場上.{0,20}咚‼?卡放回咚|"
        r"若这张角色卡即将遭到KO时.{0,60}场上.{0,20}咚‼?卡放回咚",
        chunk,
        re.I,
    ):
        return [
            {
                "op": "replace_leave",
                "trigger": "ko",
                "target": "self",
                "cost": "return_don",
                "optional": True,
                "summary": "Return 1 DON!! instead of being K.O.'d",
            }
        ]
    # Self leave → trash 1 hand
    if re.search(
        r"if this Character would be removed from the field.{0,120}trash 1 card from your hand instead|"
        r"這張角色卡即將離開場上時.{0,60}可以替換成廢棄1[張张]自己的手牌|"
        r"这张角色卡即将离开场上时.{0,60}可以替换成废弃1[张張]自己的手牌",
        chunk,
        re.I,
    ):
        op_th: dict[str, Any] = {
            "op": "replace_leave",
            "trigger": "opp_remove",
            "target": "self",
            "cost": "trash_hand",
            "once": True,
            "optional": True,
            "summary": "Trash 1 hand instead of leaving",
        }
        m_lt = re.search(r"Leader'?s? type includes\s*[\"']([^\"']+)[\"']|領航卡擁有包含[『「]([^』」]+)[』」]", chunk, re.I)
        # leader gate stays on ability
        return [op_th]
    # Filtered own KO by opponent → place N trash to bottom
    if re.search(
        r"would be k\.?o\.?'?d by your opponent'?s? effect.{0,120}"
        r"place\s*(\d+)\s*cards? from your trash at the bottom|"
        r"因對手的效果即將遭到KO時.{0,80}將\s*(\d+)\s*[張张]自己廢棄區|"
        r"因对手的效果即将遭到KO时.{0,80}将\s*(\d+)\s*[张張]自己废弃区",
        chunk,
        re.I,
    ):
        m_n = re.search(r"place\s*(\d+)\s*cards? from your trash|將\s*(\d+)\s*[張张]自己廢棄|将\s*(\d+)\s*[张張]自己废弃", chunk, re.I)
        n = int(next(g for g in m_n.groups() if g)) if m_n else 3
        op_tb: dict[str, Any] = {
            "op": "replace_leave",
            "trigger": "opp_remove",
            "target": "own_filtered",
            "cost": "trash_to_bottom",
            "trash_count": n,
            "once": True,
            "optional": True,
            "exclude_self": False,
            "summary": f"Place {n} trash at bottom instead of K.O.",
        }
        m_cost = re.search(r"base cost of\s*(\d+)\s*or less|原本費用\s*(\d+)\s*以下|原本费用\s*(\d+)\s*以下", chunk, re.I)
        if m_cost:
            op_tb["base_cost_lte"] = int(next(g for g in m_cost.groups() if g))
        if re.search(r"\bblack\b|黑色", chunk, re.I):
            op_tb["color"] = "black"
        return [op_tb]
    # Self KO / leave → trash Life
    if re.search(
        r"if this Character would be (?:k\.?o\.?'?d|leave the field).{0,120}"
        r"trash\s*1\s*card from the (?:top or bottom|top|bottom) of your Life|"
        r"若這張角色卡(?:即將遭到KO|即將離開場上)時.{0,80}生命值區(?:上面或下面|上面|下面).{0,20}廢棄|"
        r"若这张角色卡(?:即将遭到KO|即将离开场上)时.{0,80}生命值区(?:上面或下面|上面|下面).{0,20}废弃|"
        r"若這張角色卡即將離開場上時.{0,40}生命值區上面的卡片放置在廢棄區|"
        r"若这张角色卡即将离开场上时.{0,40}生命值区上面的卡片放置在废弃区",
        chunk,
        re.I,
    ):
        pos = "top_or_bottom" if re.search(r"top or bottom|上面或下面", chunk, re.I) else "top"
        return [
            {
                "op": "replace_leave",
                "trigger": "opp_remove" if re.search(r"leave the field|離開場上|离开场上", chunk, re.I) else "ko",
                "target": "self",
                "cost": "trash_life",
                "life_position": pos,
                "once": True,
                "optional": True,
                "summary": "Trash 1 Life instead of this Character leaving / being K.O.'d",
            }
        ]
    # Trash THIS Character instead of another own Character being K.O.'d
    if re.search(
        r"you may trash this Character instead|"
        r"可以替換成將這張角色卡放置在廢棄區|可以替换成将这张角色卡放置在废弃区|"
        r"可以替換成將這張角色卡放置到廢棄區",
        chunk,
        re.I,
    ) and re.search(
        r"would be k\.?o\.?'?d|即將遭到KO|即将遭到KO|遭到KO時|遭到KO时",
        chunk,
        re.I,
    ):
        op_ts: dict[str, Any] = {
            "op": "replace_leave",
            "trigger": "opp_remove" if re.search(r"opponent'?s? effect|對手的效果|对手的效果", chunk, re.I) else "ko",
            "target": "own_filtered",
            "cost": "trash_self",
            "exclude_self": True,
            "optional": True,
            "summary": "Trash this Character instead of allied K.O.",
        }
        m_trait = re.search(
            r"type including\s*[\"']([^\"']+)[\"']|包含[『「]([^』」]+)[』」]特徵|包含[『「]([^』」]+)[』」]特征|"
            r"\{([^}]+)\} type|《([^》]+)》特徵|《([^》]+)》特征",
            chunk,
            re.I,
        )
        if m_trait:
            op_ts["trait_contains"] = next(g for g in m_trait.groups() if g).strip()
        return [op_ts]
    # Rest THIS Character instead of allied KO (OP12-027) or leave (OP10-032)
    if re.search(
        r"you may rest this Character instead|"
        r"可以替換成將這張角色卡置為休息狀態|可以替换成将这张角色卡置为休息状态",
        chunk,
        re.I,
    ) and re.search(
        r"would be (?:k\.?o\.?'?d|removed from the field)|遭到KO|即将遭到KO|即將遭到KO|"
        r"即將離開場上|即将离开场上|leave the field",
        chunk,
        re.I,
    ):
        op_rs: dict[str, Any] = {
            "op": "replace_leave",
            "trigger": "opp_remove"
            if re.search(r"opponent'?s? effect|對手的效果|对手的效果", chunk, re.I)
            else "ko",
            "target": "own_filtered",
            "cost": "rest_self",
            "exclude_self": True,
            "optional": True,
            "summary": "Rest this Character instead of allied leave / K.O.",
        }
        m_cost = re.search(r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下", chunk, re.I)
        if m_cost:
            op_rs["base_cost_lte"] = int(next(g for g in m_cost.groups() if g))
        if re.search(r"<Slash>|（斬）|\(斬\)|擁有\(斬\)|拥有\(斩\)", chunk, re.I):
            op_rs["attr_contains"] = "Slash"
        m_color = re.search(
            r"\b(green|red|blue|yellow|black|purple)\b Character|"
            r"(綠|红|紅|蓝|藍|黄|黃|黑|紫)色的角色",
            chunk,
            re.I,
        )
        if m_color:
            color = (m_color.group(1) or m_color.group(2) or "").strip().lower()
            color_map = {
                "綠": "green",
                "红": "red",
                "紅": "red",
                "蓝": "blue",
                "藍": "blue",
                "黄": "yellow",
                "黃": "yellow",
                "黑": "black",
                "紫": "purple",
            }
            op_rs["color"] = color_map.get(color, color)
        excl = _parse_exclude_name(chunk)
        if excl:
            op_rs["exclude_name"] = excl
        return [op_rs]
    # Filtered own Character removed by opponent → Life to hand
    if re.search(
        r"would be removed from the field by your opponent|"
        r"因為對手而即將離開場上|因为对手而即将离开场上|"
        r"因對手的效果即將離開|因对手的效果即将离开|"
        r"因對手的效果離開場上|因对手的效果离开场上",
        chunk,
        re.I,
    ) and re.search(
        r"add\s*1\s*card from the top of your Life.{0,40}hand|"
        r"將1張自己生命值區上面的卡片加入手牌|将1张自己生命值区上面的卡片加入手牌",
        chunk,
        re.I,
    ):
        op: dict[str, Any] = {
            "op": "replace_leave",
            "trigger": "opp_remove",
            "target": "own_filtered",
            "cost": "life_to_hand",
            "life_position": "top",
            "optional": True,
            "summary": "Life to hand instead of Character leaving",
        }
        m_pow_gte = re.search(
            r"(\d+)\s*base power or more|原本力量值\s*(\d+)\s*以上|原本力量\s*(\d+)\s*以上",
            chunk,
            re.I,
        )
        m_pow_lte = re.search(
            r"(\d+)\s*base power or less|原本力量值\s*(\d+)\s*以下|原本力量\s*(\d+)\s*以下",
            chunk,
            re.I,
        )
        if m_pow_gte:
            op["base_power_gte"] = int(next(g for g in m_pow_gte.groups() if g))
        if m_pow_lte:
            op["base_power_lte"] = int(next(g for g in m_pow_lte.groups() if g))
        m_cost_lte = re.search(
            r"base cost of\s*(\d+)\s*or less|原本費用\s*(\d+)\s*以下|原本费用\s*(\d+)\s*以下",
            chunk,
            re.I,
        )
        if m_cost_lte:
            op["base_cost_lte"] = int(next(g for g in m_cost_lte.groups() if g))
        m_trait = re.search(r"\{([^}]+)\} type|《([^》]+)》特徵|《([^》]+)》特征", chunk)
        if m_trait:
            op["trait_contains"] = next(g for g in m_trait.groups() if g).strip()
        return [op]
    # Battle KO → Life to hand (OP10-034)
    if re.search(
        r"would be k\.?o\.?'?d in battle.{0,100}add\s*1\s*card from the top of your Life cards to your hand|"
        r"在對戰中遭到KO時.{0,60}可以替換成將1張自己生命值區上面的卡片加入手牌|"
        r"在对战中遭到KO时.{0,60}可以替换成将1张自己生命值区上面的卡片加入手牌",
        chunk,
        re.I,
    ):
        return [
            {
                "op": "replace_leave",
                "trigger": "ko",
                "target": "self",
                "cost": "life_to_hand",
                "life_position": "top",
                "once": True,
                "optional": True,
                "summary": "Life to hand instead of being K.O.'d in battle",
            }
        ]
    # Flip Life instead of leave / KO (common Neptune / Shirahoshi)
    if re.search(
        r"would be (?:removed from the field|k\.?o\.?'?d).{0,100}turn\s*1\s*card from the top of your Life|"
        r"即將(?:離開場上|遭到KO).{0,80}生命值區上面的卡片翻成",
        chunk,
        re.I,
    ):
        op2: dict[str, Any] = {
            "op": "replace_leave",
            "trigger": "opp_remove" if re.search(r"opponent|對手|对手", chunk, re.I) else "ko",
            "target": "self" if re.search(r"this Character|這張角色|这张角色", chunk, re.I) else "own_filtered",
            "cost": "flip_life",
            "life_position": "top",
            "optional": True,
            "summary": "Flip 1 Life face-up instead of leaving",
        }
        m_cost_lte = re.search(
            r"base cost of\s*(\d+)\s*or less|原本費用\s*(\d+)\s*以下|原本费用\s*(\d+)\s*以下",
            chunk,
            re.I,
        )
        if m_cost_lte:
            op2["base_cost_lte"] = int(next(g for g in m_cost_lte.groups() if g))
        m_pow_lte = re.search(
            r"(\d+)\s*base power or less|原本力量值\s*(\d+)\s*以下",
            chunk,
            re.I,
        )
        if m_pow_lte:
            op2["base_power_lte"] = int(next(g for g in m_pow_lte.groups() if g))
        return [op2]
    # Rest 1 of your cards instead of this Character leaving (OP14-029)
    if re.search(
        r"if this Character would be removed from the field by your opponent'?s? effect.{0,100}"
        r"you may rest 1 of your cards instead|"
        r"若這張角色卡因對手的效果即將離開場上時.{0,60}可以替換成將1張自己的卡片置為休息狀態|"
        r"若这张角色卡因对手的效果即将离开场上时.{0,60}可以替换成将1张自己的卡片置为休息状态",
        chunk,
        re.I,
    ):
        return [
            {
                "op": "replace_leave",
                "trigger": "opp_remove",
                "target": "self",
                "cost": "rest_own",
                "optional": True,
                "summary": "Rest 1 of your cards instead of this Character leaving",
            }
        ]
    # Rest another Character instead of this Character being rested (PRB02-006)
    if re.search(
        r"if this Character would be rested by your opponent'?s? Character'?s? effect.{0,100}"
        r"you may rest 1 of your other Characters instead|"
        r"若這張角色卡因對手角色卡的效果將置為休息狀態時.{0,60}可以替換成將1張自己其他的角色卡置為休息狀態|"
        r"若这张角色卡因对手角色卡的效果将置为休息状态时.{0,60}可以替换成将1张自己其他的角色卡置为休息状态",
        chunk,
        re.I,
    ):
        return [
            {
                "op": "replace_rest",
                "target": "self",
                "cost": "rest_other_character",
                "optional": True,
                "summary": "Rest 1 other Character instead of this Character being rested",
            }
        ]
    return []


def _parse_cannot_take_life_ops(chunk: str) -> list[dict[str, Any]]:
    if re.search(
        r"cannot add Life cards to your hand|"
        r"不能將生命值卡加入手牌|不能将生命值卡加入手牌|"
        r"無法將生命值卡加入手牌|无法将生命值卡加入手牌|"
        r"無法以自己的效果將生命值卡加入手牌|无法以自己的效果将生命值卡加入手牌",
        chunk,
        re.I,
    ):
        return [{"op": "cannot_take_life"}]
    return []


def _parse_skip_untap_ops(chunk: str) -> list[dict[str, Any]]:
    if not re.search(
        r"will not become active|不會置為活動|不会置为活动|不会变为活动|不會變為活動|"
        r"無法為活動|无法为活动|無法變為活動|无法变为活动|"
        r"下一重整階段無法|下一重整阶段无法|不[會会]在下一個重整",
        chunk,
        re.I,
    ):
        return []
    op: dict[str, Any] = {
        "op": "skip_untap",
        "count": 1,
        "target_kind": "opponent_character_rested",
        "optional": True,
    }
    if re.search(r"all of your opponent's rested|對手的休息狀態角色卡全數|对手的休息状态角色卡全数", chunk, re.I):
        op["all"] = True
        op["optional"] = False
    m_n = re.search(r"up to\s*(\d+)|最多\s*(\d+)", chunk, re.I)
    if m_n:
        op["count"] = max(1, min(5, int(next(g for g in m_n.groups() if g))))
    m_cost = re.search(r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下", chunk, re.I)
    if m_cost:
        op["cost_lte"] = int(next(g for g in m_cost.groups() if g))
    m_pow = re.search(
        r"(?:with\s*)?(?:a )?(?:base )?power of\s*(\d+)\s*or less|力量值\s*(\d+)\s*以下",
        chunk,
        re.I,
    )
    if m_pow:
        op["power_lte"] = int(next(g for g in m_pow.groups() if g))
    return [op]


def _parse_reorder_life_ops(chunk: str) -> list[dict[str, Any]]:
    if re.search(
        r"look at all of your opponent'?s? Life cards and place them back|"
        r"查看對手全數的生命值卡.{0,40}任意順序|"
        r"查看对手全数的生命值卡.{0,40}任意顺序",
        chunk,
        re.I,
    ):
        return [{"op": "reorder_life", "owner": "opponent"}]
    if re.search(
        r"look at all of your Life cards and place them back|"
        r"查看自己全數的生命值卡.{0,40}任意順序|"
        r"查看自己全数的生命值卡.{0,40}任意顺序",
        chunk,
        re.I,
    ):
        return [{"op": "reorder_life", "owner": "self"}]
    return []


def _parse_look_deck_ops(chunk: str) -> list[dict[str, Any]]:
    """Look at top N and put back top/bottom in any order — no add to hand/play."""
    if re.search(r"add (?:it|them) to your hand|加入手牌|play up to|使最多\s*\d+.{0,40}登場", chunk, re.I):
        return []
    m = re.search(
        r"look at\s*(\d+)\s*cards?\s*from the top of your deck.{0,80}"
        r"place them (?:at the )?(?:top or bottom|top|bottom)|"
        r"(?:從自己的卡組上面)?查看\s*(\d+)\s*[張张].{0,60}"
        r"(?:依任意順序)?(?:放回|放置).{0,20}(?:卡組)?(?:上面或下面|上面|下面)",
        chunk,
        re.I,
    )
    if not m:
        return []
    n = int(next(g for g in m.groups() if g))
    pos = "top_or_bottom"
    if re.search(r"top or bottom|上面或下面", m.group(0), re.I):
        pos = "top_or_bottom"
    elif re.search(r"\bbottom\b|下面", m.group(0), re.I) and not re.search(r"top|上面", m.group(0), re.I):
        pos = "bottom"
    elif re.search(r"\btop\b|上面", m.group(0), re.I) and not re.search(r"bottom|下面", m.group(0), re.I):
        pos = "top"
    return [{"op": "look_deck", "count": max(1, min(8, n)), "position": pos, "optional": False}]


def _parse_play_cost_aura(info: dict[str, Any]) -> dict[str, Any] | None:
    """Your Turn: cost of playing {Trait} Characters from hand −N."""
    text = effect_blob(info)
    m = re.search(
        r"The cost of playing \{([^}]+)\} type Character cards with a cost of (\d+) or more from your hand will be reduced by (\d+)",
        text,
        re.I,
    )
    if m:
        trait, cost_gte, amt = m.group(1), int(m.group(2)), int(m.group(3))
        return {
            "timing": "your_turn",
            "summary": m.group(0)[:240],
            "ops": [{"op": "hand_cost_reduce", "amount": -abs(amt)}],
            "status": "compiled",
            "confidence": 0.85,
            "hand_trait": trait,
            "hand_cost_gte": cost_gte,
        }
    m_zh = re.search(
        r"使自己手牌中費用\s*(\d+)\s*以上擁有《([^》]+)》特徵的角色卡登場的支付費用減少\s*(\d+)|"
        r"使自己手牌中费用\s*(\d+)\s*以上拥有《([^》]+)》特征的角色卡登场的支付费用减少\s*(\d+)",
        text,
        re.I,
    )
    if not m_zh:
        return None
    gs = [g for g in m_zh.groups() if g is not None]
    cost_gte, trait, amt = int(gs[0]), gs[1], int(gs[2])
    return {
        "timing": "your_turn",
        "summary": m_zh.group(0)[:240],
        "ops": [{"op": "hand_cost_reduce", "amount": -abs(amt)}],
        "status": "compiled",
        "confidence": 0.85,
        "hand_trait": trait,
        "hand_cost_gte": cost_gte,
    }


def _parse_grant_keyword_ops(chunk: str) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []

    def _named_target(text: str) -> str:
        # "If you have [Name] on your field, this Character gains …" — Name is a gate, not target.
        if re.search(
            r"(?:if you have|若自己場上有|若自己场上有).{0,60}(?:on your field|時|时).{0,40}"
            r"(?:this Character gains|這張角色卡獲得|这张角色卡获得)",
            text,
            re.I,
        ):
            return ""
        m = re.search(
            r"(?:最多\s*\d+\s*張)?(?:自己的?)?「([^」]+)」|"
            r"(?:up to\s+\d+\s+of\s+)?your\s+\[([^\]]+)\]",
            text,
            re.I,
        )
        return next((g for g in (m.groups() if m else ()) if g), "").strip() if m else ""

    duration = "turn" if re.search(r"during this turn|在這個回合|在这个回合", chunk, re.I) else "permanent"
    if re.search(r"獲得【防禦】|获得【防御】|gains? \[Blocker\]|gain \[Blocker\]", chunk, re.I):
        name = _named_target(chunk)
        op: dict[str, Any] = {"op": "grant_keyword", "keyword": "blocker", "duration": duration}
        if name:
            op["target_kind"] = "own_character"
            op["name_contains"] = name
            op["optional"] = True
            op["count"] = 1
        else:
            op["target_kind"] = "self"
        ops.append(op)
    if re.search(r"獲得【速攻】|获得【速攻】|gains? \[Rush\]|gain \[Rush\]", chunk, re.I):
        name = _named_target(chunk)
        op = {"op": "grant_keyword", "keyword": "rush", "duration": duration}
        if name:
            op["target_kind"] = "own_character"
            op["name_contains"] = name
            op["optional"] = True
            op["count"] = 1
        else:
            op["target_kind"] = "self"
        ops.append(op)
    if re.search(
        r"gains? \[Unblockable\]|gain \[Unblockable\]|"
        r"獲得【防禦不可】|获得【防御不可】|獲得【不可阻擋】|获得【不可阻挡】|"
        r"gains? \[Blockerless\]|獲得【無防禦】|获得【无防御】",
        chunk,
        re.I,
    ):
        # "Up to 1 of your … Characters gains [Unblockable]" — not a self innate grant.
        m_up = re.search(
            r"(?:最多\s*\d+\s*張|up to\s+\d+).{0,80}?(?:角色卡|Characters?).{0,40}?(?:獲得|获得|gains?)",
            chunk,
            re.I,
        )
        op_bl: dict[str, Any] = {
            "op": "grant_keyword",
            "keyword": "blockerless",
            "duration": duration,
            "optional": True,
            "count": 1,
        }
        if m_up or re.search(r"最多\s*\d+\s*張自己|up to\s+\d+\s+of\s+your", chunk, re.I):
            op_bl["target_kind"] = "own_character"
            # Trait / color cues when present (OP16-095).
            m_tr = re.search(
                r"\{([^}]+)\}|《([^》]+)》|拥有《([^》]+)》|擁有《([^》]+)》",
                chunk,
            )
            if m_tr:
                trait = next((g for g in m_tr.groups() if g), "")
                if trait:
                    op_bl["trait_contains"] = trait
            if re.search(r"黑色|black", chunk, re.I):
                op_bl["color"] = "black"
        else:
            name = _named_target(chunk)
            if name:
                op_bl["target_kind"] = "own_character"
                op_bl["name_contains"] = name
            else:
                op_bl["target_kind"] = "self"
                op_bl.pop("optional", None)
                op_bl.pop("count", None)
        ops.append(op_bl)
    if re.search(
        r"gains? \[Double Attack\]|gain \[Double Attack\]|獲得【雙重攻擊】|获得【双重攻击】|持有【Double Attack】",
        chunk,
        re.I,
    ):
        name = _named_target(chunk)
        op = {"op": "grant_keyword", "keyword": "double_attack", "duration": duration}
        if name:
            op["target_kind"] = "own_character"
            op["name_contains"] = name
            op["optional"] = True
            op["count"] = 1
        elif re.search(r"Leader or Character|領航卡或角色|领航卡或角色", chunk, re.I):
            op["target_kind"] = "own_leader_or_character"
            op["optional"] = True
        else:
            op["target_kind"] = "self"
        ops.append(op)
    if re.search(
        r"gains? \[Banish\]|gain \[Banish\]|獲得【驅逐】|获得【驱逐】|持有【Banish】",
        chunk,
        re.I,
    ):
        name = _named_target(chunk)
        op = {"op": "grant_keyword", "keyword": "banish", "duration": duration}
        if name:
            op["target_kind"] = "own_character"
            op["name_contains"] = name
            op["optional"] = True
            op["count"] = 1
        else:
            op["target_kind"] = "self"
        ops.append(op)
    return ops


def _parse_deny_blocker_ops(chunk: str) -> list[dict[str, Any]]:
    """Your opponent cannot activate [Blocker] (optionally power-gated)."""
    if not re.search(
        r"cannot activate .{0,40}\[Blocker\]|cannot activate \[Blocker\]|"
        r"不能啟動【防禦】|无法启动【防御】|不能發動【防禦】|无法发动【防御】|"
        r"不能啟動.{0,12}【防禦】|无法启动.{0,12}【防御】",
        chunk,
        re.I,
    ):
        return []
    duration = "turn" if re.search(r"during this turn|在這個回合|在这个回合", chunk, re.I) else "battle"
    op: dict[str, Any] = {"op": "deny_blocker", "duration": duration}
    if re.search(
        r"whenever your Leader attacks|when your Leader attacks|"
        r"自己的領航卡攻擊時|自己的领航卡攻击时|領航卡攻擊時|领航卡攻击时",
        chunk,
        re.I,
    ):
        op["when_leader_attacks"] = True
    m_lte = re.search(
        r"(?:blocker|防禦|防御).{0,48}?(?:that has |with )?\s*(\d+)\s*(?:power or less|or less power|以下)|"
        r"力量值\s*(\d+)\s*以下.{0,24}(?:blocker|防禦|防御)|"
        r"(\d+)\s*(?:power or less|or less power|以下).{0,24}(?:blocker|防禦|防御)",
        chunk,
        re.I,
    )
    m_gte = re.search(
        r"(?:blocker|防禦|防御).{0,48}?(?:that has |with )?\s*(\d+)\s*(?:power or more|or more power|以上)|"
        r"力量值\s*(\d+)\s*以上.{0,24}(?:blocker|防禦|防御)|"
        r"(\d+)\s*(?:power or more|or more power|以上).{0,24}(?:blocker|防禦|防御)",
        chunk,
        re.I,
    )
    if m_lte:
        op["power_lte"] = int(next(g for g in m_lte.groups() if g))
    if m_gte:
        op["power_gte"] = int(next(g for g in m_gte.groups() if g))
    return [op]


def _parse_allow_attack_active_ops(chunk: str) -> list[dict[str, Any]]:
    """Up to 1 of your … can also attack active Characters during this turn.
    Also: this Character can attack Characters on the turn it is played (optionally if opp has N+ chars).
    """
    if re.search(
        r"also attack active|也可攻擊活動|也可攻击活动|也可以攻擊活動|也可以攻击活动",
        chunk,
        re.I,
    ):
        op: dict[str, Any] = {
            "op": "allow_attack_active",
            "count": 1,
            "target_kind": "own_character",
            "optional": True,
        }
        m_trait = re.search(
            r"(?:your|自己的?)\s*\{([^}]+)\}|"
            r"擁有《([^》]+)》|拥有《([^》]+)》",
            chunk,
            re.I,
        )
        if m_trait:
            trait = next((g for g in m_trait.groups() if g), "").strip()
            if trait:
                op["trait_contains"] = trait
                op["target_kind"] = "own_leader_or_character"
        if re.search(r"leader or character|領航卡或角色|领航卡或角色", chunk, re.I):
            op["target_kind"] = "own_leader_or_character"
        return [op]
    # Rush-like: can attack Characters on play turn (often gated by opp char count)
    # Skip keyword reminder text under [Rush] / 【速攻】
    if re.search(r"\[Rush|【速攻", chunk, re.I) and not re.search(
        r"opponent has\s*\d+\s*or more|場上有\s*\d+\s*[張张]以上對手|场上有\s*\d+\s*[张張]以上对手",
        chunk,
        re.I,
    ):
        return []
    if re.search(
        r"can attack Characters? on the turn in which (?:it is|they are) played|"
        r"登場的回合即可攻擊角色|登场的回合即可攻击角色|"
        r"登場的回合可以攻擊角色|登场的回合可以攻击角色",
        chunk,
        re.I,
    ):
        op = {
            "op": "allow_attack_active",
            "count": 1,
            "target_kind": "self",
            "optional": False,
            "summary": "Can attack Characters the turn played",
        }
        m_opp = re.search(
            r"opponent has\s*(\d+)\s*or more Characters|"
            r"場上有\s*(\d+)\s*[張张]以上對手的角色|"
            r"场上有\s*(\d+)\s*[张張]以上对手的角色",
            chunk,
            re.I,
        )
        if m_opp:
            op["require_opp_chars_count_gte"] = int(next(g for g in m_opp.groups() if g))
        return [op]
    return []


def _parse_negate_effects_ops(chunk: str) -> list[dict[str, Any]]:
    """Negate effects of opponent Leader / Character(s) this turn."""
    if not re.search(
        r"negate (?:the )?effects?|效果無效|效果无效",
        chunk,
        re.I,
    ):
        return []
    # On Play negation is a different op.
    if re.search(r"\[on play\]|【登場時】|【登场时】", chunk, re.I) and re.search(
        r"on play.?effects? are negated|【登場時】效果無效|【登场时】效果无效",
        chunk,
        re.I,
    ):
        return []
    all_board = bool(
        re.search(
            r"leader and all of (?:their|your opponent'?s) characters|"
            r"領航卡和角色卡全數|领航卡和角色卡全数",
            chunk,
            re.I,
        )
    )
    each_one = bool(
        re.search(
            r"up to 1 of each of your opponent'?s leader and character|"
            r"最多各1張對手的領航卡和角色|最多各1张对手的领航卡和角色",
            chunk,
            re.I,
        )
    )
    if all_board:
        return [
            {
                "op": "negate_effects",
                "all": True,
                "include_leader": True,
                "include_characters": True,
                "target_kind": "opponent_all",
                "optional": False,
                "count": 20,
                "summary": "Negate all opponent Leader/Character effects this turn",
            }
        ]
    if each_one:
        return [
            {
                "op": "negate_effects",
                "count": 1,
                "include_leader": True,
                "optional": True,
                "target_kind": "leader",
                "summary": "Negate opponent Leader effects this turn",
            },
            {
                "op": "negate_effects",
                "count": 1,
                "include_characters": True,
                "optional": True,
                "target_kind": "opponent_character",
                "summary": "Negate up to 1 opponent Character effects this turn",
            },
        ]
    return [
        {
            "op": "negate_effects",
            "count": 1,
            "optional": True,
            "target_kind": "opponent_leader_or_character",
            "include_leader": True,
            "include_characters": True,
            "summary": "Negate up to 1 opponent Leader or Character effects this turn",
        }
    ]


def _parse_negate_on_play_ops(chunk: str) -> list[dict[str, Any]]:
    if not re.search(
        r"\[on play\].{0,40}negated|on play.?effects? are negated|"
        r"【登場時】效果無效|【登场时】效果无效|登場時.?效果無效|登场时.?效果无效",
        chunk,
        re.I,
    ):
        return []
    out: list[dict[str, Any]] = []
    if re.search(
        r"your \[on play\] effects? are negated|自己的【登場時】效果無效|自己的【登场时】效果无效|自己的\[on play\]",
        chunk,
        re.I,
    ):
        out.append({"op": "negate_on_play", "side": "self", "duration": "permanent"})
    if re.search(
        r"your opponent'?s \[on play\]|對手的【登場時】|对手的【登场时】|對手的\[on play\]",
        chunk,
        re.I,
    ):
        out.append({"op": "negate_on_play", "side": "opponent", "duration": "until_opp_turn_end"})
    if not out:
        out.append({"op": "negate_on_play", "side": "opponent", "duration": "until_opp_turn_end"})
    return out


def _extract_require_opp_hand_gte_from_text(chunk: str) -> int | None:
    m = re.search(
        r"(?:opponent(?:'s)?|對手|对手).{0,12}手牌有\s*(\d+)\s*[張张]以上|"
        r"(?:opponent(?:'s)?|對手|对手).{0,24}(?:has\s+)?(\d+)\s+or more (?:cards? )?in (?:their |the )?hand|"
        r"if (?:your )?opponent has (\d+) or more cards? in (?:their )?hand",
        chunk,
        re.I,
    )
    if not m:
        return None
    return int(next(g for g in m.groups() if g))


def _parse_opponent_hand_to_bottom_ops(chunk: str) -> list[dict[str, Any]]:
    m = re.search(
        r"(?:your )?opponent (?:must )?places?\s*(\d+)\s*cards? from (?:their|the) hand(?:\s+in any order)? at the bottom|"
        r"對手將\s*(\d+)\s*[張张]自身的手牌(?:依任意順序)?放置到?卡組下面|对手将\s*(\d+)\s*[张張]自身的手牌(?:依任意顺序)?放置到?卡组下面|"
        r"對手將\s*(\d+)\s*[張张]自身的手牌(?:依任意順序)?放置在卡組下面|对手将\s*(\d+)\s*[张張]自身的手牌(?:依任意顺序)?放置在卡组下面|"
        r"(?:your )?opponent (?:must )?places? 1 card from (?:their|the) hand(?:\s+in any order)? at the bottom|"
        r"對手將1張自身的手牌(?:依任意順序)?放置到?卡組下面|对手将1张自身的手牌(?:依任意顺序)?放置到?卡组下面|"
        r"對手將1張自身的手牌(?:依任意順序)?放置在卡組下面|对手将1张自身的手牌(?:依任意顺序)?放置在卡组下面",
        chunk,
        re.I,
    )
    if not m:
        return []
    nums = [int(g) for g in m.groups() if g]
    n = nums[0] if nums else 1
    op: dict[str, Any] = {"op": "opponent_hand_to_bottom", "count": max(1, min(5, n)), "optional": False}
    hand_gte = _extract_require_opp_hand_gte_from_text(chunk)
    if hand_gte is not None:
        op["require_opp_hand_gte"] = hand_gte
    return [op]


def _parse_trash_to_bottom_ops(chunk: str) -> list[dict[str, Any]]:
    # Opponent places N Events from trash on bottom.
    m = re.search(
        r"(?:your )?opponent places?\s*(\d+)\s*events? from (?:their|the) trash at the bottom|"
        r"對手將\s*(\d+)\s*[張张]自身廢棄區中的事件卡.{0,24}卡組下面|"
        r"对手将\s*(\d+)\s*[张张]自身废弃区中的事件卡.{0,24}卡组下面",
        chunk,
        re.I,
    )
    if m:
        n = int(next(g for g in m.groups() if g))
        return [
            {
                "op": "trash_to_bottom",
                "count": n,
                "owner": "opponent",
                "card_type": "event",
                "order_any": True,
                "optional": False,
                "summary": f"Opponent places {n} Events from trash on deck bottom",
            }
        ]
    # Opponent places N cards from trash on bottom (any type).
    m_opp = re.search(
        r"(?:your )?opponent places?\s*(\d+)\s*cards? from (?:their|the) trash at the bottom|"
        r"對手將\s*(\d+)\s*[張张]自身廢棄區中的卡片.{0,30}卡組下面|"
        r"对手将\s*(\d+)\s*[张张]自身废弃区中的卡片.{0,30}卡组下面",
        chunk,
        re.I,
    )
    if m_opp:
        n = int(next(g for g in m_opp.groups() if g))
        return [
            {
                "op": "trash_to_bottom",
                "count": n,
                "owner": "opponent",
                "card_type": "any",
                "order_any": True,
                "optional": False,
                "summary": f"Opponent places {n} cards from trash on deck bottom",
            }
        ]
    # Own trash → bottom (often as cost / colon).
    m_self = re.search(
        r"(?:you may )?(?:place|return)\s*(\d+)\s*cards?.{0,80}from your trash (?:at|to) the bottom|"
        r"可?[將将]\s*(\d+)\s*[張张].{0,80}廢棄區.{0,40}(?:卡組|卡组)下面|"
        r"可?[将將]\s*(\d+)\s*[张張].{0,80}废弃区.{0,40}卡组下面",
        chunk,
        re.I,
    )
    if m_self:
        n = int(next(g for g in m_self.groups() if g))
        trait = ""
        m_tr = re.search(
            r"type including\s*[\"']([^\"']+)[\"']|包含[『「]([^』」]+)[』」]",
            m_self.group(0) + chunk[m_self.start() : m_self.end() + 20],
            re.I,
        )
        if m_tr:
            trait = next(g for g in m_tr.groups() if g)
        op: dict[str, Any] = {
            "op": "trash_to_bottom",
            "count": max(1, min(10, n)),
            "owner": "self",
            "card_type": "any",
            "order_any": True,
            "optional": bool(re.search(r"you may|可[將将]", m_self.group(0), re.I)),
        }
        if re.search(r":|：", chunk) and op["optional"]:
            op["as_cost"] = True
        if trait:
            if len(trait) <= 4 or trait.upper() == "CP":
                op["trait_includes"] = trait
            else:
                op["trait_contains"] = trait
        return [op]
    return []


def _parse_activate_timing_ops(chunk: str) -> list[dict[str, Any]]:
    if re.search(
        r"activate this card'?s \[on k\.?o\.?\] effect|"
        r"發動這張卡片的【KO時】效果|发动这张卡片的【KO时】效果",
        chunk,
        re.I,
    ):
        return [{"op": "activate_timing", "timing": "on_ko", "summary": "Activate this card's On K.O. effect"}]
    if re.search(
        r"activate this card'?s \[main\] effect|"
        r"發動這張卡片的【主要】效果|发动这张卡片的【主要】效果",
        chunk,
        re.I,
    ):
        # Event [Main] effects are resolved as on_play when the Event is played / Triggered.
        return [{"op": "activate_timing", "timing": "on_play", "summary": "Activate this card's Main effect"}]
    if re.search(
        r"activate this card'?s \[on play\] effect|"
        r"發動這張卡片的【登場時】效果|发动这张卡片的【登场时】效果",
        chunk,
        re.I,
    ):
        return [{"op": "activate_timing", "timing": "on_play", "summary": "Activate this card's On Play effect"}]
    return []


def _parse_restriction_ops(chunk: str) -> list[dict[str, Any]]:
    """Common 'Then you cannot…' / restriction clauses (excludes cannot_take_life)."""
    ops: list[dict[str, Any]] = []
    if re.search(
        r"cannot play cards from your hand|"
        r"無法使用手牌中的卡片|无法使用手牌中的卡片",
        chunk,
        re.I,
    ):
        ops.append({"op": "cannot_play_from_hand", "card_type": "any"})
    m_char = re.search(
        r"cannot play Character cards with a base cost of\s*(\d+)\s*or more|"
        r"無法使原本費用\s*(\d+)\s*以上的角色卡登場|无法使原本费用\s*(\d+)\s*以上的角色卡登场",
        chunk,
        re.I,
    )
    if m_char:
        ops.append(
            {
                "op": "cannot_play_from_hand",
                "card_type": "character",
                "base_cost_gte": int(next(g for g in m_char.groups() if g)),
            }
        )
    return ops


def _parse_active_don_ops(chunk: str) -> list[dict[str, Any]]:
    _don = r"(?:‼|!!)"
    if re.search(
        rf"add up to\s*\d+\s*don{_don}\s*cards?\s*from your don{_don}\s*deck|"
        rf"add\s*\d+\s*don{_don}\s*cards?\s*from your don{_don}\s*deck|"
        rf"從(?:自己的)?咚{_don}?卡組追加|从(?:自己的)?咚{_don}?卡组追加",
        chunk,
        re.I,
    ):
        return []
    if re.search(
        rf"set all of your don{_don}\s*cards as active|"
        rf"咚{_don}?卡全數置為活動|咚{_don}?卡全数置为活动",
        chunk,
        re.I,
    ):
        return [{"op": "active_don", "count": 10}]
    m = re.search(
        rf"set up to\s*(\d+)\s*of your don{_don}\s*cards as active|"
        r"(?:將最多|将最多)\s*(\d+)\s*張?自己的咚|"
        r"(?:將最多|将最多)\s*(\d+)\s*[張张].{0,12}咚.{0,24}置為活動|"
        r"(?:將最多|将最多)\s*(\d+)\s*[張张].{0,12}咚.{0,24}置为活动",
        chunk,
        re.I,
    )
    if m:
        n = int(next(g for g in m.groups() if g))
        return [{"op": "active_don", "count": max(1, min(10, n))}]
    return []


def _parse_gain_don_ops(chunk: str) -> list[dict[str, Any]]:
    """Add N DON!! from DON!! deck (optionally rested)."""
    _don = r"(?:‼|!!)"
    m = re.search(
        rf"(?:add(?:\s+up to)?\s*(\d+)\s*don{_don}\s*cards?\s*from your don{_don}\s*deck|"
        rf"add(?:\s+up to)?\s*(\d+)\s*don{_don}\s*card|"
        rf"從(?:自己的)?咚{_don}?卡組追加(?:最多)?\s*(\d+)\s*[張张]?|"
        rf"从(?:自己的)?咚{_don}?卡组追加(?:最多)?\s*(\d+)\s*[张張]?)",
        chunk,
        re.I,
    )
    if not m:
        # "Add 1 DON!! card from your DON!! deck and set it as active"
        if re.search(
            rf"add\s*(?:up to\s*)?(\d+)?\s*don{_don}\s*card.{0,40}from your don{_don}\s*deck|"
            rf"從咚{_don}?卡組追加|从咚{_don}?卡组追加",
            chunk,
            re.I,
        ):
            m_n = re.search(r"(?:up to|最多)?\s*(\d+)|追加(?:最多)?\s*(\d+)", chunk, re.I)
            n = int(next((g for g in (m_n.groups() if m_n else ()) if g), "1"))
            op: dict[str, Any] = {"op": "gain_don", "count": max(1, min(5, n))}
            if re.search(r"rest it|休息狀態|休息状态|as rested", chunk, re.I):
                op["as_rested"] = True
            return [op]
        return []
    n = int(next(g for g in m.groups() if g))
    op = {"op": "gain_don", "count": max(1, min(5, n))}
    if re.search(r"rest it|休息狀態|休息状态|as rested", chunk, re.I):
        op["as_rested"] = True
    return [op]


def _parse_opp_return_don_ops(chunk: str) -> list[dict[str, Any]]:
    """Opponent returns N DON!! from their field to DON!! deck."""
    _don = r"(?:‼|!!)"
    m = re.search(
        rf"(?:your )?opponent returns?\s*(\d+)\s*don{_don}|"
        rf"對手將\s*(\d+)\s*[張张]?自身場上的咚|"
        rf"对手将\s*(\d+)\s*[张張]?自身场上的咚|"
        rf"對手放回\s*(\d+)\s*[張张]?咚|对手放回\s*(\d+)\s*[张張]?咚",
        chunk,
        re.I,
    )
    if not m:
        return []
    n = int(next(g for g in m.groups() if g))
    op: dict[str, Any] = {
        "op": "return_don",
        "count": max(1, min(10, n)),
        "owner": "opponent",
        "summary": f"Opponent returns {n} DON!!",
    }
    m_gate = re.search(
        rf"if your opponent has\s*(\d+)\s*or more don{_don}|對手場上有\s*(\d+)\s*[張张]?以上的?咚|对手场上有\s*(\d+)\s*[张張]?以上的?咚",
        chunk,
        re.I,
    )
    if m_gate:
        op["summary"] = f"If opponent DON field ≥{next(g for g in m_gate.groups() if g)}, return {n}"
    return [op]


def _chunk_has_leader_multicolor(chunk: str) -> bool:
    return bool(
        re.search(
            r"Leader is multicolored|領航卡有多種顏色|领航卡有多种颜色|領袖.?有多種顏色|领袖.?有多种颜色|"
            r"Leader has multiple colors|多色領航|多色领航",
            chunk,
            re.I,
        )
    )


def _parse_hand_to_deck_ops(chunk: str) -> list[dict[str, Any]]:
    if re.search(
        r"(?:you may )?place 1 card from your hand at the top or bottom of your deck\s*:?|"
        r"可?[將将]1張自己的手牌放置在卡組上面或下面\s*[：:]?|"
        r"可?[将將]1张自己的手牌放置在卡组上面或下面\s*[：:]?",
        chunk,
        re.I,
    ):
        op = {"op": "hand_to_deck", "count": 1, "position": "top_or_bottom", "optional": False}
        if re.search(r"you may place|可[將将]", chunk, re.I) and re.search(r":|：", chunk):
            op["optional"] = True
            op["as_cost"] = True
        return [op]
    if re.search(
        r"(?:you may )?place 1 card from your hand at the top of your deck\s*:?|"
        r"可?[將将]1張自己的手牌放置在卡組上面\s*[：:]?|"
        r"可?[将將]1张自己的手牌放置在卡组上面\s*[：:]?",
        chunk,
        re.I,
    ):
        op = {"op": "hand_to_deck", "count": 1, "position": "top", "optional": False}
        if re.search(r"you may place|可[將将]", chunk, re.I) and re.search(r":|：", chunk):
            op["optional"] = True
            op["as_cost"] = True
        return [op]
    m_n = re.search(
        r"(?:you may )?place\s*(\d+)\s*cards? from your hand at the bottom of your deck|"
        r"可?[將将]\s*(\d+)\s*[張张]自己的手牌放置在卡組下面|"
        r"可?[将將]\s*(\d+)\s*[张張]自己的手牌放置在卡组下面|"
        r"(?:you may )?place 1 card from your hand at the bottom of your deck\s*:?|"
        r"可?[將将]1張自己的手牌放置在卡組下面\s*[：:]?|"
        r"可?[将將]1张自己的手牌放置在卡组下面\s*[：:]?",
        chunk,
        re.I,
    )
    if m_n:
        nums = [int(g) for g in m_n.groups() if g]
        n = nums[0] if nums else 1
        op = {"op": "hand_to_deck", "count": max(1, min(5, n)), "position": "bottom", "optional": False}
        if re.search(r"you may place|可[將将]", m_n.group(0), re.I) and re.search(r":|：", chunk):
            op["optional"] = True
            op["as_cost"] = True
        return [op]
    if re.search(
        r"place this (?:Character|card) and 1 card from your hand at the bottom|"
        r"[將将]這張(?:角色卡|卡片)和1張自己的手牌(?:依任意順序)?放置在卡組下面|"
        r"[将將]这张(?:角色卡|卡片)和1张自己的手牌(?:依任意顺序)?放置在卡组下面",
        chunk,
        re.I,
    ):
        return [
            {
                "op": "hand_to_deck",
                "count": 1,
                "position": "bottom",
                "optional": True,
                "as_cost": True,
                "include_self": True,
            }
        ]
    # Return all hand to deck, shuffle, optionally draw equal / opponent draws N
    if re.search(
        r"Return all cards in your hand to your deck and shuffle|"
        r"將自己的手牌全部放回卡組.{0,20}洗牌|将自己的手牌全部放回卡组.{0,20}洗牌",
        chunk,
        re.I,
    ):
        op: dict[str, Any] = {
            "op": "hand_to_deck",
            "all": True,
            "shuffle": True,
            "owner": "self",
            "optional": False,
            "summary": "Return all hand to deck and shuffle",
        }
        if re.search(r"draw cards equal|依放回卡組的卡片張數抽|依放回卡组的卡片张数抽", chunk, re.I):
            op["then_draw_equal"] = True
        return [op]
    if re.search(
        r"(?:your )?opponent returns? all cards in (?:their|the) hand to (?:their|the) deck|"
        r"對手將自身的手牌全部放回卡組|对手将自身的手牌全部放回卡组",
        chunk,
        re.I,
    ):
        op = {
            "op": "hand_to_deck",
            "all": True,
            "shuffle": True,
            "owner": "opponent",
            "optional": False,
            "summary": "Opponent returns all hand to deck and shuffles",
        }
        m_d = re.search(r"(?:opponent )?draws?\s*(\d+)|對手抽\s*(\d+)|对手抽\s*(\d+)", chunk, re.I)
        if m_d:
            op["then_draw"] = int(next(g for g in m_d.groups() if g))
        return [op]
    return []


def _parse_reveal_opp_hand_ops(chunk: str) -> list[dict[str, Any]]:
    m = re.search(
        r"choose\s*(\d+)\s*cards? from (?:your )?opponent'?s hand|"
        r"選擇對手的\s*(\d+)\s*[張张]手牌|选择对手的\s*(\d+)\s*[张张]手牌",
        chunk,
        re.I,
    )
    if m and re.search(r"reveal|公開|公开", chunk, re.I):
        n = int(next(g for g in m.groups() if g))
        return [{"op": "reveal_opp_hand", "count": n, "optional": False}]
    if re.search(
        r"reveals? their hand|公開(?:自身的)?手牌|公开(?:自身的)?手牌|並公開手牌|并公开手牌",
        chunk,
        re.I,
    ):
        return [{"op": "reveal_opp_hand", "count": 1, "optional": False, "summary": "Reveal opponent hand"}]
    return []


def _parse_grant_cost_ops(chunk: str) -> list[dict[str, Any]]:
    m = re.search(
        r"gains?\s*\+?(\d+)\s*cost|gain\s*\+?(\d+)\s*cost|費用\+(\d+)|费用\+(\d+)",
        chunk,
        re.I,
    )
    if not m:
        return []
    amt = int(next(g for g in m.groups() if g))
    op: dict[str, Any] = {
        "op": "grant_cost",
        "amount": amt,
        "target_kind": "own_character",
        "optional": True,
        "summary": f"Character gains +{amt} cost",
    }
    if re.search(r"all of your|全數|全数|Characters with", chunk, re.I):
        op["all"] = True
        op["target_kind"] = "all_own"
        op["optional"] = False
        op["summary"] = f"Own Characters gain +{amt} cost"
    m_trait = re.search(
        r"\{([^}]+)\}\s*type|擁有《([^》]+)》|拥有《([^》]+)》|"
        r"type including [\"']?([^\"'\n]+)[\"']?|包含『([^』]+)』|包含《([^》]+)》",
        chunk,
        re.I,
    )
    if m_trait:
        trait = next((g for g in m_trait.groups() if g), "").strip()
        if trait:
            op["trait_contains"] = trait
    m_name = re.search(r"「([^」]+)」|\[([^\]]+)\]", chunk)
    if m_name and re.search(r"最多\s*1|up to\s*1|自己的「|your \[", chunk, re.I):
        name = (m_name.group(1) or m_name.group(2) or "").strip()
        if name and name.lower() not in {"trigger", "blocker", "rush", "don!!"}:
            op["name_contains"] = name
            op["target_kind"] = "own_character"
            op["optional"] = True
    if re.search(r"this Character|這張角色|这张角色", chunk, re.I) and not re.search(
        r"up to 1 of your|最多1張自己|最多1张自己|最多1張自己的「|最多1张自己的「", chunk, re.I
    ):
        op["target_kind"] = "self"
        op["optional"] = False
        op.pop("all", None)
        op.pop("name_contains", None)
    return [op]


def parse_static_self_cost(info: dict[str, Any]) -> list[dict[str, Any]]:
    """Continuous 'this Character +N cost' while on the field (both turns)."""
    text = effect_blob(info)
    # Prefer the untimed / always-on clause, not On Play one-shots.
    # Match leading "這張角色卡的費用+N" before the first timing tag when present.
    head = text
    stop = re.search(
        r"【(?:登場時|登场时|攻擊時|攻击时|啟動主要|启动主要|KO時|KO时|觸發器|触发器|反擊|反击|"
        r"我方回合中|對方回合中|对方回合中)】|"
        r"\[(?:on play|when attacking|activate|on k\.?o\.?|trigger|counter|your turn|opponent)",
        text,
        re.I,
    )
    if stop:
        head = text[: stop.start()]
    m = re.search(
        r"(?:這張角色卡|这张角色卡|this Character)(?:的)?(?:費用|费用)\+(\d+)|"
        r"this Character gains?\s*\+?(\d+)\s*cost",
        head,
        re.I,
    )
    if not m:
        # Also allow gated forms that are continuous (leader trait / trash / hand).
        m = re.search(
            r"(?:這張角色卡|这张角色卡|this Character)(?:的)?(?:費用|费用)\+(\d+)|"
            r"this Character gains?\s*\+?(\d+)\s*cost",
            text,
            re.I,
        )
        if not m:
            return []
        # Skip if the only match sits inside an On Play / Activate body as a grant to another card.
        if re.search(r"最多\s*1\s*[張张]自己|up to\s*1\s*of your", text, re.I) and re.search(
            r"「[^」]+」.{0,20}(?:費用|费用)\+|\[.+?\].{0,20}gains?\s*\+",
            text,
            re.I,
        ):
            # Named other-character grant — not static self cost.
            if not re.search(
                r"(?:這張角色卡|这张角色卡|this Character)(?:的)?(?:費用|费用)\+",
                head,
                re.I,
            ):
                return []
    amt = int(next(g for g in m.groups() if g))
    out: list[dict[str, Any]] = []
    base: dict[str, Any] = {
        "summary": f"This Character +{amt} cost (static)",
        "ops": [{"op": "grant_cost", "amount": amt, "target_kind": "self"}],
        "status": "compiled",
        "confidence": 0.9,
    }
    # Optional continuous gates on the same sentence / nearby clause.
    m_leader = re.search(
        r"若自己的領航卡擁有《([^》]+)》|若自己的领航卡拥有《([^》]+)》|"
        r"if your Leader has the \{([^}]+)\}",
        text,
        re.I,
    )
    # Only apply leader gate when it clearly conditions the cost line.
    if m_leader and re.search(
        r"領航卡擁有.《[^》]+》.特徵時，這張角色卡的費用|领航卡拥有.《[^》]+》.特征时，这张角色卡的费用|"
        r"Leader has the \{[^}]+\}.type.{0,40}this Character gains",
        text,
        re.I,
    ):
        base["require_leader_trait"] = next(g for g in m_leader.groups() if g)
    for timing in ("your_turn", "opponent_turn"):
        out.append({**base, "timing": timing})
    return out


def _parse_redirect_attack_ops(chunk: str) -> list[dict[str, Any]]:
    if not re.search(
        r"change the attack target|攻擊的對象變更|攻击的对象变更|redirect",
        chunk,
        re.I,
    ):
        return []
    op: dict[str, Any] = {
        "op": "redirect_attack",
        "target_kind": "own_leader_or_character",
        "optional": False,
        "summary": "Change the attack target",
    }
    m_trait = re.search(r"\{([^}]+)\}|《([^》]+)》", chunk)
    if m_trait:
        op["trait_contains"] = next(g for g in m_trait.groups() if g)
    # 「這位領航員或《…》」— Leader is always a legal redirect target.
    if re.search(r"Leader|領航員|领航员", chunk, re.I):
        op["include_leader"] = True
    return [op]


def _parse_deny_attack_ops(chunk: str) -> list[dict[str, Any]]:
    if not re.search(
        r"cannot attack|無法進行攻擊|无法进行攻击|不能攻擊|不能攻击",
        chunk,
        re.I,
    ):
        return []
    # Self cannot-attack is handled by cannot_attack static.
    if re.search(r"this Character cannot attack|這張角色卡無法進行攻擊|这张角色卡无法进行攻击", chunk, re.I):
        return []
    op: dict[str, Any] = {
        "op": "deny_attack",
        "count": 1,
        "target_kind": "opponent_character",
        "optional": True,
        "duration": "until_opp_turn_end",
        "summary": "Opponent Character cannot attack",
    }
    if re.search(r"active Characters|活動狀態的角色|活动状态的角色", chunk, re.I):
        op["active_only"] = True
    if re.search(r"Leader or Character|領航卡或角色|领航卡或角色", chunk, re.I):
        op["include_leader"] = True
    excl = _parse_exclude_name(chunk)
    if excl:
        op["exclude_name"] = excl
    m = re.search(r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下", chunk, re.I)
    if m:
        op["cost_lte"] = int(next(g for g in m.groups() if g))
    m_base = re.search(r"base cost of\s*(\d+)\s*or less|原本費用\s*(\d+)\s*以下|原本费用\s*(\d+)\s*以下", chunk, re.I)
    if m_base:
        op["base_cost_lte"] = int(next(g for g in m_base.groups() if g))
    m2 = re.search(r"up to\s*(\d+)|最多\s*(\d+)", chunk, re.I)
    if m2:
        op["count"] = int(next(g for g in m2.groups() if g))
    if re.search(r"during this turn|在這個回合|在这个回合", chunk, re.I):
        op["duration"] = "turn"
    return [op]


def _parse_deny_rest_ops(chunk: str) -> list[dict[str, Any]]:
    if not re.search(
        r"cannot be rested|無法置為休息|无法置为休息|不能被休息|cannot be rest|"
        r"無法為休息|无法为休息|不能置為休息|不能置为休息",
        chunk,
        re.I,
    ):
        return []
    # Self immunity ("cannot be rested by opponent's effects") is not deny_rest.
    if re.search(
        r"this Character cannot be rested by|這張角色卡.{0,40}(?:不會|无法|無法).{0,40}休息|"
        r"这张角色卡.{0,40}(?:不会|无法).{0,40}休息",
        chunk,
        re.I,
    ) and not re.search(
        r"(?:up to\s*\d+\s+of\s+)?(?:your )?opponent'?s Characters?.{0,40}cannot be rested|"
        r"最多\s*\d+\s*張?對手.{0,30}無法置為休息",
        chunk,
        re.I,
    ):
        return []
    op: dict[str, Any] = {
        "op": "deny_rest",
        "count": 1,
        "target_kind": "opponent_character",
        "optional": True,
        "duration": "until_opp_turn_end",
        "summary": "Opponent Character cannot be rested",
    }
    if re.search(r"none of the selected|全數|全数|all of your opponent", chunk, re.I):
        op["count"] = 5
        op["optional"] = False
        op["all"] = True
    m_n = re.search(r"up to\s*(\d+)|最多\s*(\d+)\s*張|最多\s*(\d+)\s*张", chunk, re.I)
    if m_n:
        op["count"] = max(1, min(5, int(next(g for g in m_n.groups() if g))))
    m = re.search(r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下", chunk, re.I)
    if m:
        op["cost_lte"] = int(next(g for g in m.groups() if g))
    return [op]


def _parse_set_cost_ops(chunk: str) -> list[dict[str, Any]]:
    # Must be "set cost TO 0", not a filter like "0-cost Character" / 「費用0的角色卡」.
    if not re.search(
        r"set the cost of.{0,80}to\s*0|"
        r"(?:費用|费用)(?:值)?\s*(?:變更|变更|變成|变成|改)\s*(?:成|為|为)\s*0|"
        r"(?:將|将).{0,48}(?:費用|费用)(?:值)?.{0,24}(?:變更|变更|變成|变成|改)\s*(?:成|為|为)\s*0",
        chunk,
        re.I,
    ):
        return []
    op: dict[str, Any] = {
        "op": "set_cost",
        "amount": 0,
        "count": 1,
        "target_kind": "opponent_character",
        "optional": True,
        "summary": "Set Character cost to 0",
    }
    if re.search(r"no base effect|沒有原本效果|没有原本效果", chunk, re.I):
        op["require_no_effect"] = True
    return [op]


def _parse_trash_self_power_debuff(chunk: str) -> list[dict[str, Any]]:
    """
    Colon-cost: trash this Character → common follow-ups (−/+ power, KO, rest, reduce cost).
    """
    if not re.search(
        r"(?:you may )?trash this Character\s*:|"
        r"可[將将]這[張张]角色卡放置[在到]廢棄區\s*[：:]|"
        r"可[將将]这[张張]角色卡放置[在到]废弃区\s*[：:]",
        chunk,
        re.I,
    ):
        return []
    ops: list[dict[str, Any]] = [
        {
            "op": "trash",
            "target_kind": "self",
            "as_cost": True,
            "optional": False,
            "summary": "Trash this Character",
        }
    ]
    # Opponent −power
    if re.search(
        r"(?:力量(?:值)?\s*[−\-－]\s*\d{3,5}|[−\-－]\s*\d{3,5}\s*power|power\s*[−\-－]\s*\d{3,5})",
        chunk,
        re.I,
    ) and re.search(r"對手|对手|opponent", chunk, re.I):
        m_amt = re.search(
            r"(?:力量(?:值)?\s*[−\-－]\s*(\d{3,5})|[−\-－]\s*(\d{3,5})\s*power|power\s*[−\-－]\s*(\d{3,5}))",
            chunk,
            re.I,
        )
        amount = -abs(int(next(g for g in m_amt.groups() if g)))
        m_count = re.search(r"(?:最多|up to)\s*(\d+)", chunk, re.I)
        count = max(1, min(5, int(m_count.group(1)))) if m_count else 1
        m_ceq = re.search(
            r"(?:費用|费用)\s*(\d+)\s*的角色|(\d+)\s*cost Characters?|Characters? with a cost of\s*(\d+)(?!\s*or less)",
            chunk,
            re.I,
        )
        cost_eq = int(next(g for g in m_ceq.groups() if g)) if m_ceq else None
        # Emit one buff op per target so each opens its own choice (engine has no buff.count).
        for i in range(count):
            buff: dict[str, Any] = {
                "op": "buff",
                "amount": amount,
                "optional": True,
                "target_kind": "opponent_character",
                "summary": f"Give up to 1 opponent's Character {amount}",
            }
            if cost_eq is not None:
                buff["cost_eq"] = cost_eq
                buff["summary"] = f"Give up to 1 opponent's cost-{cost_eq} Character {amount}"
            if count > 1:
                buff["summary"] = f"{buff['summary']} ({i + 1}/{count})"
            ops.append(buff)
        return ops

    m_own = re.search(
        r"(?:自己.{0,48}(?:領航|领航|角色)|your (?:Leader or )?Character).{0,40}"
        r"(?:力量(?:值)?\s*\+\s*(\d{3,5})|\+\s*(\d{3,5})\s*power|gains?\s*\+?\s*(\d{3,5})\s*power)",
        chunk,
        re.I,
    )
    if m_own:
        amount = abs(int(next(g for g in m_own.groups() if g)))
        ops.append(
            {
                "op": "buff",
                "amount": amount,
                "optional": True,
                "target_kind": "own_character_or_leader",
                "summary": f"Give your Leader or Character +{amount}",
            }
        )
        return ops

    ko = _parse_ko_op(chunk)
    if ko:
        ops.append(ko)
        return ops

    trash_opp = _parse_trash_opponent_char_ops(chunk)
    if trash_opp:
        ops.extend(trash_opp)
        return ops

    if re.search(
        r"rest up to 1 of your opponent|將最多1[張张]對手.{0,24}置為休息|将最多1[张張]对手.{0,24}置为休息",
        chunk,
        re.I,
    ):
        rest: dict[str, Any] = {"op": "rest_opponent_character", "count": 1, "optional": True}
        m_ceq = re.search(r"(?:費用|费用)\s*(\d+)\s*的角色|cost of\s*(\d+)(?!\s*or less)", chunk, re.I)
        if m_ceq:
            rest["cost_eq"] = int(m_ceq.group(1) or m_ceq.group(2))
        m_clte = re.search(r"(?:費用|费用)\s*(\d+)\s*以下|cost of\s*(\d+)\s*or less", chunk, re.I)
        if m_clte:
            rest["cost_lte"] = int(m_clte.group(1) or m_clte.group(2))
        ops.append(rest)
        return ops

    m_red = re.search(
        r"(?:費用|费用)\s*[−\-－]\s*(\d+)|[−\-－]\s*(\d+)\s*cost",
        chunk,
        re.I,
    )
    if m_red and re.search(r"對手|对手|opponent", chunk, re.I):
        amt = abs(int(next(g for g in m_red.groups() if g)))
        ops.append(
            {
                "op": "reduce_cost",
                "amount": -amt,
                "count": 1,
                "target_kind": "opponent_character",
                "optional": True,
                "summary": f"Give up to 1 opponent Character −{amt} cost",
            }
        )
        return ops

    # Colon-cost matched but follow-up not templated — leave empty so callers
    # can still prepend trash-self onto independently parsed ops.
    return []


def _trash_self_as_cost_op() -> dict[str, Any]:
    return {
        "op": "trash",
        "target_kind": "self",
        "as_cost": True,
        "optional": False,
        "summary": "Trash this Character",
    }


def _has_trash_self_colon_cost(chunk: str) -> bool:
    return bool(
        re.search(
            r"(?:you may )?trash this Character\s*:|"
            r"可[將将]這[張张]角色卡放置[在到]廢棄區\s*[：:]|"
            r"可[將将]这[张張]角色卡放置[在到]废弃区\s*[：:]",
            chunk,
            re.I,
        )
    )


def _extract_require_opp_char_cost_0_or_gte(chunk: str) -> int | None:
    """
    'if your opponent has a Character with a cost of 0 or with a cost of N or more'
    「若場上有對手費用0或N以上的角色卡時」
    """
    m = re.search(
        r"(?:opponent|對手|对手).{0,40}(?:cost of\s*0|費用\s*0|费用\s*0).{0,24}"
        r"(?:or (?:with a )?cost of\s*(\d+)\s*or more|或\s*(\d+)\s*以上)",
        chunk,
        re.I,
    )
    if m:
        return int(next(g for g in m.groups() if g))
    m2 = re.search(
        r"若場上有對手(?:費用|费用)\s*0\s*或\s*(\d+)\s*以上|"
        r"若场上有对手(?:费用|費用)\s*0\s*或\s*(\d+)\s*以上",
        chunk,
        re.I,
    )
    if m2:
        return int(next(g for g in m2.groups() if g))
    return None


def _extract_require_field_char_cost_0_or_gte(chunk: str) -> int | None:
    """
    'If there is a Character with a cost of 0 or with a cost of N or more'
    「若場上有費用0或N以上的角色卡時」(any side)
    """
    if not chunk:
        return None
    # Prefer opponent-specific extractor when text names opponent.
    if re.search(r"opponent|對手|对手", chunk, re.I) and _extract_require_opp_char_cost_0_or_gte(chunk) is not None:
        return None
    m = re.search(
        r"(?:if there is a Character with a cost of\s*0\s*or with a cost of\s*(\d+)\s*or more)|"
        r"若場上有(?:費用|费用)\s*0\s*或\s*(\d+)\s*以上|"
        r"若场上有(?:费用|費用)\s*0\s*或\s*(\d+)\s*以上",
        chunk,
        re.I,
    )
    if m:
        return int(next(g for g in m.groups() if g))
    return None


def _text_requires_don_field_lte_opponent(chunk: str) -> bool:
    """Own field DON!! count ≤ opponent's (engine: require_don_field_deficit_gte=0)."""
    if not chunk:
        return False
    return bool(
        re.search(
            r"number of DON!! cards on your field is equal to or less than|"
            r"自己場上的咚‼?卡(?:的)?數量(?:少於等於|≤|不多於)對手|"
            r"自己场上的咚‼?卡(?:的)?数量(?:少于等于|≤|不多于)对手|"
            r"場上的咚‼?卡數量少於等於對手|场上的咚‼?卡数量少于等于对手|"
            r"咚‼?卡的數量少於等於對手場上|咚‼?卡的数量少于等于对手场上",
            chunk,
            re.I,
        )
    )


def _extract_require_hand_lte_from_text(chunk: str) -> int | None:
    if not chunk:
        return None
    m = re.search(
        r"(?:if you have|you may draw.{0,24}if you have)\s*(\d+)\s*or less cards? in your hand|"
        r"若自己的手牌在\s*(\d+)\s*[張张]以下|"
        r"手牌在\s*(\d+)\s*[張张]以下時|"
        r"手牌有\s*(\d+)\s*[張张]以下",
        chunk,
        re.I,
    )
    if not m:
        return None
    return int(next(g for g in m.groups() if g))


def _extract_require_life_lte_from_text(chunk: str) -> int | None:
    """Own Life ≤ N only. Opponent Life uses require_opp_life_lte."""
    if not chunk:
        return None
    # Strip opponent-life clauses so 「對手的生命值卡在N張以下」never sets own gate.
    cleaned = re.sub(
        r"(?:對手的|对手的|your opponent(?:'s)?|opponent(?:'s)?)\s*"
        r"(?:生命值卡在\s*\d+\s*[張张]以下|生命值\s*≤\s*\d+|\d+\s*or less [Ll]ife)",
        " ",
        chunk,
        flags=re.I,
    )
    m = re.search(
        r"(?:if you have\s*)?(\d+)\s*or less [Ll]ife|"
        r"自己的生命值卡在\s*(\d+)\s*[張张]以下|"
        r"若自己的生命值卡在\s*(\d+)|"
        r"(?<![對手对])生命值卡在\s*(\d+)\s*[張张]以下|"
        r"若生命值\s*≤\s*(\d+)",
        cleaned,
        re.I,
    )
    if not m:
        return None
    return int(next(g for g in m.groups() if g))


def _extract_require_opp_life_lte_from_text(chunk: str) -> int | None:
    if not chunk:
        return None
    m = re.search(
        r"(?:對手的|对手的|your opponent(?:'s)?|opponent(?:'s)?)\s*"
        r"(?:生命值卡在\s*(\d+)\s*[張张]以下|生命值\s*≤\s*(\d+))|"
        r"(?:if your opponent has\s*)?(\d+)\s*or less [Ll]ife",
        chunk,
        re.I,
    )
    if not m:
        return None
    return int(next(g for g in m.groups() if g))


def _enrich_ops_with_target_filters(ops: list[dict[str, Any]], chunk: str) -> list[dict[str, Any]]:
    """Fill cost/power filters on bare KO / return / rest ops from paper text."""
    if not ops or not chunk:
        return ops
    parsed_ko = _parse_ko_op(chunk)
    out: list[dict[str, Any]] = []
    for raw in ops:
        o = dict(raw)
        kind = str(o.get("op") or "")
        if kind in {"ko", "ko_lowest_opponent"} and parsed_ko:
            has = any(o.get(k) is not None for k in ("cost_lte", "cost_eq", "power_lte", "base_power_lte"))
            if not has and any(
                parsed_ko.get(k) is not None for k in ("cost_lte", "cost_eq", "power_lte", "base_power_lte")
            ):
                if kind == "ko_lowest_opponent":
                    o = dict(parsed_ko)
                else:
                    for k in ("cost_lte", "cost_eq", "power_lte", "base_power_lte", "target_kind"):
                        if parsed_ko.get(k) is not None and o.get(k) is None:
                            o[k] = parsed_ko[k]
            # Always prefer rested target when paper text requires it.
            if parsed_ko.get("target_kind") == "opponent_character_rested":
                o["target_kind"] = "opponent_character_rested"
            if parsed_ko.get("base_power_lte") is not None and o.get("power_lte") is not None and o.get("base_power_lte") is None:
                o["base_power_lte"] = o.pop("power_lte")
        if kind == "return_to_hand" and o.get("cost_lte") is None:
            for p in _parse_return_char_to_hand_ops(chunk):
                if p.get("cost_lte") is not None:
                    o["cost_lte"] = p["cost_lte"]
                    break
        if kind in {"rest_opponent_character", "rest_character"} and o.get("cost_lte") is None and o.get("cost_eq") is None:
            m_clte = re.search(r"(?:費用|费用)\s*(\d+)\s*以下|cost of\s*(\d+)\s*or less", chunk, re.I)
            if m_clte:
                o["cost_lte"] = int(m_clte.group(1) or m_clte.group(2))
            else:
                m_ceq = re.search(r"(?:費用|费用)\s*(\d+)\s*的角色|cost of\s*(\d+)(?!\s*or less)", chunk, re.I)
                if m_ceq:
                    o["cost_eq"] = int(m_ceq.group(1) or m_ceq.group(2))
        # 「自己的卡片」/ "your cards" with no type → Leader / Character / Stage / DON!!.
        if kind == "rest_character" and "opponent" not in str(o.get("target_kind") or ""):
            if re.search(
                r"自己的卡片置為休息|自己的卡片置为休息|of your cards|"
                r"rest\s+\d+\s+of your cards|rest 1 of your cards",
                chunk,
                re.I,
            ) and not re.search(
                r"自己的角色卡置為休息|自己的角色卡置为休息|rest\s+\d+\s+of your Characters|"
                r"自己的咚‼?卡置為休息|rest\s+\d+\s+of your DON",
                chunk,
                re.I,
            ):
                o["include_leader"] = True
                o["include_don"] = True
                o["include_stage"] = True
                m_n = re.search(
                    r"(?:可)?將\s*(\d+)\s*張自己的卡片|(?:可)?将\s*(\d+)\s*张自己的卡片|"
                    r"rest\s+(\d+)\s+of your cards",
                    chunk,
                    re.I,
                )
                if m_n and o.get("count") is None:
                    o["count"] = max(1, min(5, int(next(g for g in m_n.groups() if g))))
        if kind == "draw" and o.get("require_opp_char_cost_0_or_gte") is None:
            gte = _extract_require_opp_char_cost_0_or_gte(chunk)
            if gte is not None:
                o["require_opp_char_cost_0_or_gte"] = gte
        out.append(o)
    return out


def _apply_common_text_gates(ability: dict[str, Any], chunk: str) -> dict[str, Any]:
    """Attach frequent ability-level gates inferred from a timing chunk."""
    if not ability or not chunk:
        return ability
    out = dict(ability)
    if _text_requires_don_field_lte_opponent(chunk) and out.get("require_don_field_deficit_gte") is None:
        out["require_don_field_deficit_gte"] = 0
    hand_n = _extract_require_hand_lte_from_text(chunk)
    if hand_n is not None and out.get("require_hand_lte") is None:
        out["require_hand_lte"] = hand_n
    life_n = _extract_require_life_lte_from_text(chunk)
    if life_n is not None and out.get("require_life_lte") is None:
        out["require_life_lte"] = life_n
    opp_life_n = _extract_require_opp_life_lte_from_text(chunk)
    if opp_life_n is not None and out.get("require_opp_life_lte") is None:
        out["require_opp_life_lte"] = opp_life_n
    return out


def _finalize_trailing_conditional_draw(ops: list[dict[str, Any]], chunk: str) -> list[dict[str, Any]]:
    """Move trailing Then-if draw after other ops and attach opp cost gate when present."""
    if not ops or not any(o.get("op") == "draw" for o in ops):
        return ops
    trailing = bool(
        re.search(
            r"(?:之後|之后|Then,?).{0,12}(?:若|if).{0,120}(?:draw\s*1|抽1)",
            chunk,
            re.I,
        )
    )
    gte = _extract_require_opp_char_cost_0_or_gte(chunk)
    if not trailing and gte is None:
        return ops
    draws = [dict(o) for o in ops if o.get("op") == "draw"]
    rest = [o for o in ops if o.get("op") != "draw"]
    if gte is not None:
        for d in draws:
            d["require_opp_char_cost_0_or_gte"] = gte
    if trailing:
        return rest + draws
    # Condition without clear "afterwards" — still gate draws that appear with the phrase.
    for d in draws:
        if "require_opp_char_cost_0_or_gte" in d:
            return rest + draws
    return ops


def _extract_require_field_char_cost_eq(chunk: str) -> int | None:
    """
    'If there is a Character with a cost of N on the field' / 「若場上有費用N的角色卡時」.
    """
    m = re.search(
        r"(?:if there is|if .{0,24}have).{0,40}(?:a )?(?:Character|Characters).{0,24}cost of\s*(\d+)|"
        r"若場上有(?:費用|费用)\s*(\d+)\s*的角色|"
        r"若场上有(?:费用|費用)\s*(\d+)\s*的角色",
        chunk,
        re.I,
    )
    if not m:
        return None
    return int(next(g for g in m.groups() if g))


def _parse_trash_opponent_char_ops(chunk: str) -> list[dict[str, Any]]:
    """Trash / place in Trash up to 1 opponent Character (often cost-filtered)."""
    if not re.search(
        r"trash up to\s*\d+\s*of your opponent'?s Characters?|"
        r"將最多\s*\d+\s*[張张]對手.{0,48}放置[在到]廢棄區|"
        r"将最多\s*\d+\s*[张張]对手.{0,48}放置[在到]废弃区",
        chunk,
        re.I,
    ):
        return []
    op: dict[str, Any] = {
        "op": "trash",
        "target_kind": "opponent_character",
        "optional": True,
        "count": 1,
        "summary": "Trash up to 1 opponent's Character",
    }
    m_lte = re.search(r"(?:費用|费用)\s*(\d+)\s*以下|cost of\s*(\d+)\s*or less", chunk, re.I)
    m_eq = re.search(
        r"(?:費用|费用)\s*(\d+)\s*的角色|Characters? with a cost of\s*(\d+)(?!\s*or less)|(\d+)\s*cost Characters?",
        chunk,
        re.I,
    )
    if m_lte:
        op["cost_lte"] = int(m_lte.group(1) or m_lte.group(2))
        op["summary"] = f"Trash up to 1 opponent's Character with cost ≤{op['cost_lte']}"
    elif m_eq:
        op["cost_eq"] = int(next(g for g in m_eq.groups() if g))
        op["summary"] = f"Trash up to 1 opponent's cost-{op['cost_eq']} Character"
    if re.search(r"rested Character|休息狀態|休息状态|休息中", chunk, re.I):
        op["target_kind"] = "opponent_character_rested"
    return [op]


def _parse_trash_hand_down_to_ops(chunk: str) -> list[dict[str, Any]]:
    m = re.search(
        r"trash cards from your hands until you each have\s*(\d+)|"
        r"廢棄自身的手牌使手牌只有\s*(\d+)|废弃自身的手牌使手牌只有\s*(\d+)",
        chunk,
        re.I,
    )
    if not m:
        return []
    return [
        {
            "op": "trash_hand_down_to",
            "hand_size": int(next(g for g in m.groups() if g)),
            "side": "both",
            "summary": "Both players trash down to N cards in hand",
        }
    ]


def _parse_ko_own_any_buff_leader_ops(chunk: str) -> list[dict[str, Any]]:
    """OP06-095 style: may KO any number of own trait cost≤N; Leader +1000 per KO."""
    if not re.search(
        r"(?:you may )?k\.?o\.?\s*any number of your|"
        r"可以KO自己費用|可以KO自己费用",
        chunk,
        re.I,
    ):
        return []
    m_cost = re.search(r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下", chunk, re.I)
    m_trait = re.search(r"\{([^}]+)\}|《([^》]+)》", chunk)
    cost_lte = int(next(g for g in m_cost.groups() if g)) if m_cost else 2
    trait = next((g for g in m_trait.groups() if g), "").strip() if m_trait else ""
    ops: list[dict[str, Any]] = [
        {
            "op": "ko",
            "target_kind": "own_character",
            "optional": True,
            "cost_lte": cost_lte,
            "count": 5,
            "summary": "K.O. any number of own Characters (cost filter)",
        }
    ]
    if trait:
        ops[0]["trait_contains"] = trait
    # Per-KO leader buff is approximated as a second leader buff; engine won't multiply yet.
    if re.search(r"additional \+1000|每KO1張|每KO1张", chunk, re.I):
        ops.append(
            {
                "op": "buff",
                "amount": 1000,
                "target_kind": "leader",
                "optional": False,
                "summary": "Leader +1000 per Character K.O.'d (best-effort once)",
            }
        )
    return ops


def _parse_set_active_ops(chunk: str) -> list[dict[str, Any]]:
    # Do not treat "set DON!! as active" as Character set-active.
    scrubbed = re.sub(
        r"(?:DON!!|咚‼?|咚!!).{0,40}(?:as active|置為活動|置为活动)|"
        r"(?:as active|置為活動|置为活动).{0,20}(?:DON!!|咚‼?)",
        " ",
        chunk,
        flags=re.I,
    )
    if re.search(
        r"置為活動狀態|置为活动状态|set.{0,80}as active|become active",
        scrubbed,
        re.I,
    ) and re.search(r"角色|Character|Leader|領航|领航", scrubbed, re.I):
        if re.search(
            r"leader and all of your characters|領航卡和角色卡全數|领航卡和角色卡全数|"
            r"自己的領航卡和角色卡全數|自己的领航卡和角色卡全数",
            scrubbed,
            re.I,
        ):
            return [
                {"op": "set_character_active", "count": 5, "target_kind": "own_character", "optional": False},
            ]
        tk = "self" if re.search(r"這張角色卡|这张角色卡|this Character", scrubbed, re.I) else "own_character"
        return [{"op": "set_character_active", "count": 1, "target_kind": tk, "optional": True}]
    return []


def _parse_cannot_be_ko_ops(chunk: str) -> list[dict[str, Any]]:
    if re.search(
        r"不會因對手的效果而遭到KO|不会因对手的效果而遭到KO|"
        r"cannot be K\.?O\.?.{0,40}by (?:your )?opponent'?s effects|"
        r"cannot be K\.?O\.?.{0,20}by effects|"
        r"不會因效果而遭到KO|不会因效果而遭到KO|"
        r"does not leave.{0,40}by (?:your )?opponent'?s effects",
        chunk,
        re.I,
    ):
        return [{"op": "cannot_be_ko", "target_kind": "self", "optional": False, "summary": "Cannot be K.O.'d by effects"}]
    # Trait-filtered board shield: "{Trait} Characters other than [Name] cannot be K.O.'d in battle"
    m_tr = re.search(
        r"\{([^}]+)\}\s*type Characters?(?: other than your \[([^\]]+)\])? cannot be K\.?O|"
        r"除了自己的「([^」]+)」以外[，,]?擁有《([^》]+)》特徵的角色卡.{0,20}不會遭到KO|"
        r"除了自己的「([^」]+)」以外[，,]?拥有《([^》]+)》特征的角色卡.{0,20}不会遭到KO",
        chunk,
        re.I,
    )
    if m_tr:
        gs = [g for g in m_tr.groups() if g]
        # EN: trait, exclude_name?; ZH: exclude, trait
        if re.search(r"\{", m_tr.group(0)):
            trait = gs[0]
            excl = gs[1] if len(gs) > 1 else ""
        else:
            excl = gs[0] if len(gs) > 1 else ""
            trait = gs[-1]
        op: dict[str, Any] = {
            "op": "cannot_be_ko",
            "target_kind": "own_character",
            "all": True,
            "trait_contains": trait,
            "optional": False,
            "summary": f"{{{trait}}} Characters cannot be K.O.'d",
        }
        if excl:
            op["exclude_name"] = excl
        return [op]
    m_attr = re.search(
        r"cannot be K\.?O\.?'?d in battle by\s*<([^>]+)>\s*attribute|"
        r"在和擁有\s*[<(（]\s*([^>)）]+)\s*[>)）]\s*屬性.{0,30}不會遭到KO|"
        r"在和拥有\s*[<(（]\s*([^>)）]+)\s*[>)）]\s*属性.{0,30}不会遭到KO|"
        r"不會被.{0,12}屬性.{0,20}KO|不会被.{0,12}属性.{0,20}KO",
        chunk,
        re.I,
    )
    if m_attr:
        attr = next((g for g in m_attr.groups() if g), "").strip()
        op = {
            "op": "cannot_be_ko",
            "target_kind": "self",
            "optional": False,
            "summary": f"Cannot be K.O.'d in battle by <{attr}> attribute" if attr else "Cannot be K.O.'d in battle",
        }
        if attr:
            op["attribute"] = attr[:40]
        return [op]
    if re.search(
        r"cannot be K\.?O\.?'?d in battle|對戰中不會遭到KO|对战中不会遭到KO|"
        r"本回合不會遭到KO|本回合不会遭到KO",
        chunk,
        re.I,
    ):
        return [{"op": "cannot_be_ko", "target_kind": "self", "optional": False}]
    return []


def _parse_rest_opponent_ops(chunk: str) -> list[dict[str, Any]]:
    """Rest up to N opponent Characters (optionally cost-filtered)."""
    if re.search(r"rest up to\s*\d+\s*of your opponent'?s DON|將最多\s*\d+\s*[張张]對手的咚|将最多\s*\d+\s*[张張]对手的咚", chunk, re.I):
        # Opponent DON rest not modeled yet.
        return []
    m = re.search(
        r"rest up to\s*(\d+)\s*of your opponent'?s (?:Leader or )?Characters?(?: with a cost of\s*(\d+)\s*or less)?|"
        r"將最多\s*(\d+)\s*[張张]對手(?:費用|费用)\s*(\d+)\s*以下.{0,12}置[為为]休息|"
        r"将最多\s*(\d+)\s*[张張]对手(?:费用|費用)\s*(\d+)\s*以下.{0,12}置为休息|"
        r"將最多\s*(\d+)\s*[張张]對手的(?:領航卡或)?角色卡置[為为]休息|"
        r"将最多\s*(\d+)\s*[张張]对手的(?:领航卡或)?角色卡置为休息",
        chunk,
        re.I,
    )
    if not m:
        return []
    nums = [int(g) for g in m.groups() if g]
    n = nums[0] if nums else 1
    cost_lte = nums[1] if len(nums) > 1 else None
    op: dict[str, Any] = {
        "op": "rest_opponent_character",
        "count": max(1, min(5, n)),
        "optional": True,
    }
    if cost_lte is not None:
        op["cost_lte"] = cost_lte
    if re.search(r"Leader or Character|領航卡或角色|领航卡或角色", m.group(0), re.I):
        op["include_leader"] = True
    return [op]


def _parse_power_buff_amount(chunk: str) -> list[dict[str, Any]]:
    """Self or leader/character +/- power for when_attacking style chunks."""
    ops: list[dict[str, Any]] = []
    if re.search(r"becomes?|變成|变成|相同|變更成|变更成", chunk, re.I):
        return ops
    m = re.search(
        r"(?:這張角色卡|这张角色卡|this Character).{0,20}(?:力量[值]?\s*([+\-−－]\s*\d{3,5})|gains?\s*([+\-−－]?\s*\d{3,5})\s*power)|"
        r"(?:力量[值]?\s*([+\-−－]\s*\d{3,5})|gains?\s*([+\-−－]?\s*\d{3,5})\s*power)",
        chunk,
        re.I,
    )
    if m:
        raw = next((g for g in m.groups() if g), None)
        if raw:
            amount = int(re.sub(r"[^\d\-]", "", raw.replace("−", "-").replace("－", "-")) or 0)
            if amount:
                ops.append({"op": "buff_self", "amount": amount})
    m2 = re.search(
        r"(?:對手的?(?:領航卡或)?角色卡|your opponent'?s (?:Leader or )?Character).{0,40}"
        r"(?:力量[值]?\s*([+\-−－]\s*\d{3,5})|gains?\s*([+\-−－]?\s*\d{3,5})\s*power|power\s*([+\-−－]\s*\d{3,5}))",
        chunk,
        re.I,
    )
    if m2:
        raw = next((g for g in m2.groups() if g), None)
        if raw:
            amount = int(re.sub(r"[^\d\-]", "", raw.replace("−", "-").replace("－", "-")) or 0)
            if amount:
                ops.append(
                    {
                        "op": "buff",
                        "amount": amount,
                        "target_kind": "opponent_character",
                        "optional": True,
                    }
                )
    return ops


def _parse_return_own_as_cost(pre: str) -> dict[str, Any] | None:
    """Parse optional 'return your Character to hand' cost before a colon."""
    if not re.search(r"放回持有者的手牌|return .{0,80}(?:to the )?owner'?s hand|return .{0,80}to (?:your|the owner's) hand", pre, re.I):
        return None
    # Must target your own character (not opponent bounce as the cost itself).
    if not re.search(
        r"自己(?:費用|费用|\d|的角色|角色卡)|your Characters?|of your Character|"
        r"Character to your hand|1 Character to the owner'?s hand|"
        r"除了這張角色卡以外自己|除了这张角色卡以外自己",
        pre,
        re.I,
    ):
        return None
    # Reject opponent-targeting costs mistaken as own.
    if re.search(r"opponent|對手|对方|對手的|对方的", pre, re.I) and not re.search(
        r"自己|your Character|to your hand", pre, re.I
    ):
        return None
    op: dict[str, Any] = {
        "op": "return_to_hand",
        "target_kind": "own_character",
        "optional": True,
        "as_cost": True,
    }
    m_gte = re.search(r"(?:費用|费用)\s*(\d+)\s*以上|cost of\s*(\d+)\s*or more", pre, re.I)
    if m_gte:
        op["cost_gte"] = int(m_gte.group(1) or m_gte.group(2))
    if re.search(r"除了這張角色卡以外|除了这张角色卡以外|other than this Character", pre, re.I):
        op["exclude_self"] = True
    return op


def _parse_colon_gated_on_play(chunk: str) -> list[dict[str, Any]] | None:
    """
    OPTCG 'You may COST: EFFECT' — dark text before the colon is a required cost.
    Skipping / failing the cost cancels everything after the colon.
    """
    m = re.search(
        r"(可將[^：:\n]{6,140}放回持有者的手牌|可将[^：:\n]{6,140}放回持有者的手牌|"
        r"You may return [^:\n]{6,140}hand)\s*[：:]\s*(.+)",
        chunk,
        re.I | re.S,
    )
    if not m:
        return None
    cost = _parse_return_own_as_cost(m.group(1))
    if not cost:
        return None
    effect_text = m.group(2).strip()
    ops: list[dict[str, Any]] = [cost]
    play_hand = _parse_play_from_hand(effect_text) or _parse_play_from_zone(effect_text)
    if play_hand:
        ops.append(play_hand)
    if re.search(r"draw 2|抽2張|抽2张|抽2", effect_text, re.I):
        ops.append({"op": "draw", "count": 2})
    elif re.search(r"draw 1|抽1張|抽1张|抽1", effect_text, re.I):
        ops.append({"op": "draw", "count": 1})
    if re.search(
        r"將最多1張(?:費用|费用)\d+以下的角色卡放回持有者的手牌|"
        r"将最多1张(?:费用|費用)\d+以下的角色卡放回持有者的手牌|"
        r"return up to 1 Character with a cost of \d+ or less to the (?:owner'?s )?hand",
        effect_text,
        re.I,
    ):
        bounce: dict[str, Any] = {
            "op": "return_to_hand",
            "target_kind": "opponent_character",
            "optional": True,
        }
        m_cost = re.search(r"(?:費用|费用)\s*(\d+)\s*以下|cost of\s*(\d+)\s*or less", effect_text, re.I)
        if m_cost:
            bounce["cost_lte"] = int(m_cost.group(1) or m_cost.group(2))
        ops.append(bounce)
    if len(ops) <= 1:
        return None
    return ops


def _parse_life_to_hand_cost(chunk: str) -> list[dict[str, Any]]:
    """Life → hand (cost or effect), including opponent's Life to owner's hand."""
    ops: list[dict[str, Any]] = []
    # Opponent Life → owner's hand (common Warlords / Teach template)
    if re.search(
        r"add\s*(?:up to\s*)?1\s*card from the top of your opponent'?s Life cards to the owner'?s hand|"
        r"將最多\s*1\s*張對手生命值區上面的卡片[，,]?\s*加入持有者的手牌|"
        r"将最多\s*1\s*张对手生命值区上面的卡片[，,]?\s*加入持有者的手牌|"
        r"將最多\s*1\s*張對手生命值區上面的卡片加入持有者的手牌|"
        r"将最多\s*1\s*张对手生命值区上面的卡片加入持有者的手牌",
        chunk,
        re.I,
    ):
        ops.append(
            {
                "op": "life_to_hand",
                "count": 1,
                "position": "top",
                "optional": True,
                "owner": "opponent",
                "hand_owner": "life_owner",
            }
        )
    # Colon-cost: add 1 from own Life to hand:
    if re.search(
        r"(?:you may )?add\s*1\s*card from .{0,40}(?:your )?Life.{0,30}hand\s*:|"
        r"可[將将]\s*1\s*[張张]自己生命值區.{0,20}加入手牌\s*[：:]",
        chunk,
        re.I,
    ):
        pos = "top_or_bottom" if re.search(r"top or bottom|上面或下面", chunk, re.I) else "top"
        if re.search(r"\bbottom of your Life|生命值區下面|生命值区下面", chunk, re.I) and pos != "top_or_bottom":
            pos = "bottom"
        ops.append(
            {
                "op": "life_to_hand",
                "count": 1,
                "position": pos,
                "optional": True,
                "as_cost": True,
                "owner": "self",
            }
        )
        return ops
    # Own Life → hand (non-cost / Then)
    if re.search(
        r"(?:you may )?add\s*(?:up to\s*)?1\s*card from (?:the )?(?:top or bottom|top|bottom) of your Life|"
        r"(?:you may )?add\s*1\s*card from your Life|"
        r"將最多1張.{0,20}自己生命值區.{0,24}加入手牌|将最多1张.{0,20}自己生命值区.{0,24}加入手牌|"
        r"可[將将]\s*1\s*[張张]自己生命值區.{0,20}加入手牌",
        chunk,
        re.I,
    ) and not re.search(r"opponent'?s Life|對手生命|对手生命", chunk, re.I):
        pos = "top"
        if re.search(r"top or bottom|上面或下面", chunk, re.I):
            pos = "top_or_bottom"
        elif re.search(r"\bbottom of your Life|生命值區下面|生命值区下面", chunk, re.I):
            pos = "bottom"
        ops.append(
            {
                "op": "life_to_hand",
                "count": 1,
                "position": pos,
                "optional": True,
                "owner": "self",
            }
        )
    return ops


def _parse_flip_life_cost(chunk: str) -> list[dict[str, Any]]:
    """Flip Life face-up/down — cost, all, or single face-up Life."""
    # All Life face-down / face-up
    if re.search(
        r"turn all of your Life cards face-?(down|up)|"
        r"將自己的生命值卡全數翻成(?:背面朝上|正面朝上)|将自己的生命值卡全数翻成(?:背面朝上|正面朝上)",
        chunk,
        re.I,
    ):
        face = "down" if re.search(r"face-?down|背面", chunk, re.I) else "up"
        return [{"op": "flip_life", "face": face, "all": True, "optional": False}]
    # Turn 1 face-up Life face-down (cost or effect)
    m_fu = re.search(
        r"(?:you may )?turn\s*1\s*of your face-up Life cards face-?down\s*:?|"
        r"可[將将]\s*1\s*[張张]自己正面朝上的生命值卡置為背面朝上\s*[：:]?",
        chunk,
        re.I,
    )
    if m_fu:
        as_cost = bool(re.search(r"[：:]", m_fu.group(0))) or bool(
            re.search(r"face-?down\s*:|背面朝上\s*[：:]", chunk, re.I)
        )
        return [
            {
                "op": "flip_life",
                "face": "down",
                "require_face": "up",
                "as_cost": as_cost,
                "optional": True,
            }
        ]
    m = re.search(
        r"(?:you may )?turn\s*(\d+)\s*cards? from the top of your Life cards face-?(up|down)\s*:|"
        r"可將\s*(\d+)\s*張自己生命值區上面的卡片翻成(?:正面朝上|背面朝上)\s*[：:]|"
        r"可将\s*(\d+)\s*张自己生命值区上面的卡片翻成(?:正面朝上|背面朝上)\s*[：:]",
        chunk,
        re.I,
    )
    if not m:
        # Replacement / instead: turn 1 from top face-up
        m2 = re.search(
            r"(?:you may )?turn\s*1\s*card from the top of your Life cards face-?(up|down)|"
            r"將\s*1\s*張自己生命值區上面的卡片翻成(?:正面朝上|背面朝上)|"
            r"将\s*1\s*张自己生命值区上面的卡片翻成(?:正面朝上|背面朝上)",
            chunk,
            re.I,
        )
        if not m2:
            m3 = re.search(
                r"(?:you may )?turn\s*1\s*card from the top or bottom of your Life cards face-?(up|down)\s*:|"
                r"可將\s*1\s*張自己生命值區上面或下面的卡片翻成(?:正面朝上|背面朝上)\s*[：:]",
                chunk,
                re.I,
            )
            if not m3:
                return []
            face = "up" if re.search(r"face-?up|正面", m3.group(0), re.I) else "down"
            return [
                {
                    "op": "flip_life",
                    "face": face,
                    "position": "top_or_bottom",
                    "as_cost": True,
                    "optional": True,
                }
            ]
        face = "up" if re.search(r"face-?up|正面", m2.group(0), re.I) else "down"
        as_cost = bool(re.search(r"face-?(?:up|down)\s*:|翻成(?:正面朝上|背面朝上)\s*[：:]", chunk, re.I))
        return [
            {
                "op": "flip_life",
                "face": face,
                "position": "top",
                "as_cost": as_cost,
                "optional": True,
            }
        ]
    n = int(next(g for g in m.groups()[:1] + m.groups()[2:] if g and str(g).isdigit()))
    face_raw = next((g for g in m.groups() if g in {"up", "down"}), None)
    if face_raw is None:
        face = "up" if re.search(r"face-?up|正面", m.group(0), re.I) else "down"
    else:
        face = face_raw
    return [
        {
            "op": "flip_life",
            "face": face,
            "position": "top",
            "as_cost": True,
            "optional": True,
        }
        for _ in range(max(1, min(3, n)))
    ]


def _parse_trash_life_ops(chunk: str) -> list[dict[str, Any]]:
    """Trash from Life (self / opponent / both), including colon costs."""
    ops: list[dict[str, Any]] = []
    # Both players trash 1 from top of Life
    if re.search(
        r"trash\s*1\s*card from the top of each of your and your opponent'?s Life|"
        r"雙方各自將\s*1\s*張生命值區上面的卡片放置在廢棄區|"
        r"双方各自将\s*1\s*张生命值区上面的卡片放置在废弃区",
        chunk,
        re.I,
    ):
        return [
            {"op": "trash_life", "count": 1, "position": "top", "owner": "self", "optional": False},
            {"op": "trash_life", "count": 1, "position": "top", "owner": "opponent", "optional": False},
        ]
    # Colon-cost: trash 1 from top or bottom of your Life:
    if re.search(
        r"(?:you may )?trash\s*1\s*card from the top or bottom of your Life cards\s*:|"
        r"可[將将]\s*1\s*[張张]自己生命值區上面或下面的卡片放置[到在]廢棄區\s*[：:]",
        chunk,
        re.I,
    ):
        ops.append(
            {
                "op": "trash_life",
                "count": 1,
                "position": "top_or_bottom",
                "owner": "self",
                "optional": True,
                "as_cost": True,
            }
        )
    # Colon-cost: trash 1 from top of your Life:
    elif re.search(
        r"(?:you may )?trash\s*1\s*card from the top of your Life cards\s*:|"
        r"可[將将]\s*1\s*[張张]自己生命值區上面的卡片放置[到在]廢棄區\s*[：:]",
        chunk,
        re.I,
    ):
        ops.append(
            {
                "op": "trash_life",
                "count": 1,
                "position": "top",
                "owner": "self",
                "optional": True,
                "as_cost": True,
            }
        )
    # Opponent Life trash
    m_opp = re.search(
        r"trash\s*(?:up to\s*)?(\d+)\s*cards? from the top of your opponent'?s Life|"
        r"將最多\s*(\d+)\s*張對手生命值區上面的卡片放置在廢棄區|"
        r"将最多\s*(\d+)\s*张对手生命值区上面的卡片放置在废弃区|"
        r"將\s*(\d+)\s*張對手生命值區上面|"
        r"将\s*(\d+)\s*张对手生命值区上面",
        chunk,
        re.I,
    )
    if m_opp:
        n = int(next(g for g in m_opp.groups() if g))
        ops.append(
            {
                "op": "trash_life",
                "count": max(1, min(5, n)),
                "position": "top",
                "owner": "opponent",
                "optional": True,
            }
        )
    # Self Life trash (non-cost)
    m_self = re.search(
        r"trash\s*(?:up to\s*)?(\d+)\s*cards? from the top of your Life|"
        r"將最多\s*(\d+)\s*張自己生命值區上面的卡片放置在廢棄區|"
        r"将最多\s*(\d+)\s*张自己生命值区上面的卡片放置在废弃区",
        chunk,
        re.I,
    )
    if m_self and not re.search(r"opponent'?s Life|對手生命|对手生命|each of your and|top or bottom", chunk, re.I):
        n = int(next(g for g in m_self.groups() if g))
        ops.append(
            {
                "op": "trash_life",
                "count": max(1, min(5, n)),
                "position": "top",
                "owner": "self",
                "optional": True,
            }
        )
    return ops


def _parse_hand_to_life_ops(chunk: str) -> list[dict[str, Any]]:
    if not re.search(
        r"add\s*(?:up to\s*)?\d*.{0,40}from your hand.{0,40}(?:to the )?(?:top of your )?Life|"
        r"手牌加入生命值|將最多\s*\d*\s*[張张]?自己的?手牌加入生命|将最多\s*\d*\s*[张张]?自己的?手牌加入生命",
        chunk,
        re.I,
    ):
        return []
    return [{"op": "hand_to_life", "count": 1, "optional": True, "position": "top"}]


def _parse_life_zone_ops(chunk: str) -> list[dict[str, Any]]:
    """Life↔hand / flip Life costs / trash Life — shared across timings."""
    ops: list[dict[str, Any]] = []
    ops.extend(_parse_life_to_hand_cost(chunk))
    if not any(o.get("op") == "flip_life" for o in ops):
        ops.extend(_parse_flip_life_cost(chunk))
    ops.extend(_parse_trash_life_ops(chunk))
    ops.extend(_parse_hand_to_life_ops(chunk))
    return ops


def _parse_colon_life_or_flip_costs(chunk: str) -> list[dict[str, Any]]:
    """Colon costs paid from Life (to hand / flip)."""
    ops: list[dict[str, Any]] = []
    life = _parse_life_to_hand_cost(chunk)
    cost_life = [o for o in life if o.get("as_cost")]
    if cost_life:
        return cost_life
    flip = _parse_flip_life_cost(chunk)
    if flip:
        return flip
    return []


def _ensure_colon_cost_ops(ops: list[dict[str, Any]], info: dict[str, Any]) -> list[dict[str, Any]]:
    """If card text has a colon-cost but library ops skipped it, rebuild from text."""
    if any(o.get("as_cost") for o in ops):
        return ops
    blob = effect_blob(info)
    chunk = _on_play_chunk(blob) if re.search(r"\[on play\]|【登場時】|【登场时】", blob, re.I) else blob
    gated = _parse_colon_gated_on_play(chunk)
    if gated:
        kinds = {str(o.get("op") or "") for o in ops}
        if kinds & {"play_from_hand", "draw", "return_to_hand"}:
            return gated
    # Life→hand / flip Life colon costs: prepend onto existing post-cost ops.
    life_costs = _parse_colon_life_or_flip_costs(blob)
    cost_only = [o for o in life_costs if o.get("as_cost")]
    if cost_only and ops:
        return [*cost_only, *ops]
    if life_costs and not ops:
        return life_costs
    return ops


def parse_simple_on_play(info: dict[str, Any]) -> list[dict[str, Any]]:
    text = effect_blob(info)
    # Only parse real On Play chunks — never the whole text (avoids On K.O. / Activate leaks).
    if not re.search(r"\[on play\]|【登場時】|【登场时】", text, re.I):
        return []
    chunk = _on_play_chunk(text)
    gated = _parse_colon_gated_on_play(chunk)
    if gated:
        return gated
    ops: list[dict[str, Any]] = []
    if re.search(r"draw 2|抽2張|抽2张|抽2", chunk, re.I):
        ops.append({"op": "draw", "count": 2})
    elif re.search(r"draw 1|抽1張|抽1张|抽1", chunk, re.I):
        ops.append({"op": "draw", "count": 1})
    if re.search(r"(add|gain).{0,24}1 don|咚‼?\s*\+?\s*1|追加.{0,6}1张?咚", chunk, re.I):
        ops.append({"op": "gain_don", "count": 1})
    if re.search(r"rest (up to )?1|休息最多1|将最多1张.{0,12}休息|將最多1張.{0,12}休息", chunk, re.I):
        ops.append({"op": "rest_opponent_character", "count": 1})
    # Prefer structured KO when cost/power/stage filters are present.
    ko_op = _parse_ko_op(chunk)
    if ko_op:
        ops.append(ko_op)
    elif re.search(r"k\.?o\.?\s*(up to )?1|KO最多1|将对方最多1张.{0,20}KO|將對方最多1張.{0,20}KO", chunk, re.I):
        ops.append({"op": "ko_lowest_opponent", "count": 1})
    # Deck search templates (best effort):
    # - "Look at 3 cards from the top ... reveal up to 1 {Impel Down} type ... add to hand"
    # - "從自己的卡組上面查看3張 ... 公開最多1張擁有《推進城》特徵 ... 加入手牌"
    search_op = _parse_look_top_search(chunk)
    if search_op:
        ops.append(search_op)
    play_hand = _parse_play_from_zone(chunk) or _parse_play_from_zone(text)
    if play_hand:
        ops.append(play_hand)
    ops.extend(_parse_place_on_bottom_ops(chunk))
    ops.extend(_parse_return_char_to_hand_ops(chunk))
    ops.extend(_parse_attach_don_ops(chunk))
    ops.extend(_parse_grant_keyword_ops(chunk))
    ops.extend(_parse_set_active_ops(chunk))
    ops.extend(_parse_cannot_be_ko_ops(chunk))
    ops.extend(_parse_deny_blocker_ops(chunk))
    ops.extend(_parse_allow_attack_active_ops(chunk))
    ops.extend(_parse_replace_battle_ko_ops(chunk))
    ops.extend(_parse_cannot_take_life_ops(chunk))
    ops.extend(_parse_skip_untap_ops(chunk))
    ops.extend(_parse_reorder_life_ops(chunk))
    ops.extend(_parse_look_deck_ops(chunk))
    ops.extend(_parse_negate_effects_ops(chunk))
    ops.extend(_parse_trash_to_bottom_ops(chunk))
    ops.extend(_parse_opponent_hand_to_bottom_ops(chunk))
    ops.extend(_parse_restriction_ops(chunk))
    ops.extend(_parse_hand_to_deck_ops(chunk))
    ops.extend(_parse_reveal_opp_hand_ops(chunk))
    ops.extend(_parse_grant_cost_ops(chunk))
    ops.extend(_parse_redirect_attack_ops(chunk))
    ops.extend(_parse_trash_hand_down_to_ops(chunk))
    ops.extend(_parse_active_don_ops(chunk))
    ops.extend(_parse_deny_attack_ops(chunk))
    ops.extend(_parse_deny_rest_ops(chunk))
    ops.extend(_parse_set_cost_ops(chunk))
    ops.extend(_parse_trash_opponent_char_ops(chunk))
    if re.search(
        r"rest up to 1 of your opponent|將最多1[張张]對手.{0,40}置為休息|将最多1[张張]对手.{0,40}置为休息",
        chunk,
        re.I,
    ):
        existing = next((o for o in ops if o.get("op") == "rest_opponent_character"), None)
        if existing is None:
            existing = {"op": "rest_opponent_character", "count": 1}
            ops.append(existing)
        m_ceq = re.search(r"(?:費用|费用)\s*(\d+)\s*的角色|cost of\s*(\d+)(?!\s*or less)", chunk, re.I)
        if m_ceq and existing.get("cost_eq") is None:
            existing["cost_eq"] = int(m_ceq.group(1) or m_ceq.group(2))
        m_clte = re.search(r"(?:費用|费用)\s*(\d+)\s*以下|cost of\s*(\d+)\s*or less", chunk, re.I)
        if m_clte and existing.get("cost_lte") is None:
            existing["cost_lte"] = int(m_clte.group(1) or m_clte.group(2))
    # Leader gains +N until next turn
    m_lead = re.search(
        r"up to 1 of your Leader gains?\s*\+?(\d+)\s*power|"
        r"最多1張自己的領航卡力量值\+(\d+)|最多1张自己的领航卡力量值\+(\d+)",
        chunk,
        re.I,
    )
    if m_lead:
        ops.append(
            {
                "op": "buff",
                "amount": int(next(g for g in m_lead.groups() if g)),
                "target_kind": "leader",
                "optional": True,
                "summary": "Up to 1 Leader gains power",
            }
        )
    # Life zone ops (life↔hand / flip / trash)
    life_ops = _parse_life_zone_ops(chunk)
    if life_ops:
        cost_life = [o for o in life_ops if o.get("as_cost")]
        rest_life = [o for o in life_ops if not o.get("as_cost")]
        if cost_life and not any(o.get("as_cost") for o in ops):
            ops = cost_life + ops
        for o in rest_life:
            if not any(
                x.get("op") == o.get("op") and x.get("owner") == o.get("owner") for x in ops
            ):
                ops.append(o)
    # Deduplicate identical ops
    seen: set[tuple] = set()
    uniq: list[dict[str, Any]] = []
    for o in ops:
        key = (o.get("op"), o.get("amount"), o.get("count"), o.get("card_type"), o.get("base_cost_gte"), o.get("owner"), o.get("as_cost"))
        if key in seen and o.get("op") in {"cannot_take_life", "cannot_play_from_hand"}:
            continue
        seen.add(key)
        uniq.append(o)
    ops = uniq
    # add_life from deck top
    if re.search(
        r"add up to 1 card from the top of your deck to the top of your Life|"
        r"將最多1張自己卡組上面的卡片加到生命值區上面|"
        r"将最多1张自己卡组上面的卡片加到生命值区上面",
        chunk,
        re.I,
    ):
        ops.append({"op": "add_life", "count": 1})
    family = _parse_cost_reduce_family_ops(chunk)
    cost_ops = [o for o in family if o.get("as_cost")]
    rest_family = [o for o in family if not o.get("as_cost")]
    # Colon-cost KO own must run before the effect after the colon (e.g. P-144 draw).
    if cost_ops:
        ops = [
            o
            for o in ops
            if not (o.get("op") == "ko" and o.get("target_kind") == "own_character")
        ]
        ops = cost_ops + ops
    for op in rest_family:
        if op.get("op") == "ko" and any(o.get("op") == "ko" for o in ops):
            if op.get("target_kind") == "own_character":
                ops = [
                    o
                    for o in ops
                    if not (o.get("op") == "ko" and str(o.get("target_kind", "")).startswith("opponent"))
                ]
                ops.append(op)
                continue
        if op.get("op") == "reduce_cost" and any(o.get("op") == "reduce_cost" for o in ops):
            continue
        if op.get("op") in {"trash_deck_top", "buff_all_own"} and any(o.get("op") == op.get("op") for o in ops):
            continue
        ops.append(op)
    trash_cost = _parse_trash_hand_cost(chunk)
    if trash_cost and not any(o.get("op") == "trash_hand" for o in ops):
        ops = trash_cost + ops
    ops = _enrich_ops_with_target_filters(ops, chunk)
    return _finalize_trailing_conditional_draw(ops, chunk)


def _on_ko_chunk(text: str) -> str:
    m = re.search(r"(?:\[on\s*k\.?o\.?\]|【KO時】|【KO时】)", text, re.I)
    if not m:
        return ""
    rest = text[m.end() :]
    stop = re.search(
        r"(?=【(?!KO時|KO时)[^】]{0,12}】|"
        r"\[(?!on\s*k\.?o\.?\])(?:on\s+play|when\s+attacking|activate|trigger|counter|blocker|don!!|opponent|your\s+turn)\b)",
        rest,
        re.I,
    )
    end = m.end() + (stop.start() if stop else min(len(rest), 600))
    return text[m.start() : end]


def _parse_reduce_cost_ops(chunk: str) -> list[dict[str, Any]]:
    """Give up to N opponent Characters −X cost during this turn."""
    if not chunk:
        return []
    # Avoid matching power debuffs (−4000 power).
    if not re.search(r"cost|費用|费用", chunk, re.I):
        return []
    ops: list[dict[str, Any]] = []
    patterns = (
        r"(?:give\s+)?up to\s*(\d+)\s+of your opponent'?s?\s+characters?\s*[−\-－–]\s*(\d+)\s*cost",
        r"最多\s*(\d+)\s*[張张]對手的角色卡.{0,48}費用\s*[−\-－–]\s*(\d+)",
        r"最多\s*(\d+)\s*[张张]对手的角色卡.{0,48}费用\s*[−\-－–]\s*(\d+)",
        r"最多1[張张]對手的角色卡.{0,48}費用\s*[−\-－–]\s*(\d+)",
        r"最多1[张张]对手的角色卡.{0,48}费用\s*[−\-－–]\s*(\d+)",
        r"give up to 1 of your opponent'?s?\s+characters?\s*[−\-－–]\s*(\d+)\s*cost",
    )
    seen: set[tuple[int, int]] = set()
    for pat in patterns:
        for m in re.finditer(pat, chunk, re.I):
            groups = [g for g in m.groups() if g]
            if len(groups) >= 2:
                count, amt = int(groups[0]), int(groups[1])
            elif len(groups) == 1:
                count, amt = 1, int(groups[0])
            else:
                continue
            key = (count, amt)
            if key in seen:
                continue
            seen.add(key)
            ops.append(
                {
                    "op": "reduce_cost",
                    "amount": -abs(amt),
                    "count": max(1, min(5, count)),
                    "target_kind": "opponent_character",
                    "optional": True,
                    "summary": f"Give up to {count} opponent Character(s) −{amt} cost this turn",
                }
            )
    return ops


def _parse_trash_deck_top_ops(chunk: str) -> list[dict[str, Any]]:
    if not chunk:
        return []
    m = re.search(
        r"(?:you may\s+)?(?:trash|place)\s*(\d+)\s*cards? from the top of your deck|"
        r"(?:and\s+)?trash\s*(\d+)\s*cards? from the top of your deck|"
        r"(?:並|并)?[將将]\s*(\d+)\s*[張张]自己卡組上面的卡片放置[在到]廢棄區|"
        r"(?:並|并)?[將将]\s*(\d+)\s*[张张]自己卡组上面的卡片放置[在到]废弃区|"
        r"可[將将]\s*(\d+)\s*[張张]自己卡組上面|可[將将](\d+)[張张]自己卡組上面|"
        r"可[將将]\s*(\d+)\s*[张张]自己卡组上面|"
        r"廢棄\s*(\d+)\s*[張张]自己卡組上面|废弃\s*(\d+)\s*[张张]自己卡组上面",
        chunk,
        re.I,
    )
    if not m:
        return []
    n = int(next((g for g in m.groups() if g), "1"))
    optional = bool(re.search(r"you may|可以|可將|可将", m.group(0), re.I))
    return [{"op": "trash_deck_top", "count": max(1, min(10, n)), "optional": optional}]


def _parse_buff_all_own_ops(chunk: str) -> list[dict[str, Any]]:
    """Leader and/or all your Characters gain +N power this turn."""
    if not chunk:
        return []
    # Trait-filtered: all of your {Trait} Characters gain +N
    # Also: Characters with a type including "Whitebeard Pirates"
    m_tr = re.search(
        r"all of your \{([^}]+)\} type Characters?(?: other than this Character)? gains?\s*[+＋]\s*(\d{3,5})\s*power|"
        r"All of your Characters with a type including\s*[\"']([^\"']+)[\"']\s*gains?\s*[+＋]\s*(\d{3,5})\s*power|"
        r"(?:除了這張角色卡以外)?自己擁有《([^》]+)》特徵的角色卡全數力量值\s*[+＋]\s*(\d{3,5})|"
        r"(?:除了这张角色卡以外)?自己拥有《([^》]+)》特征的角色卡全数力量值\s*[+＋]\s*(\d{3,5})|"
        r"自己擁有包含[『「]([^』」]+)[』」]特徵的角色卡全數力量值\s*[+＋]\s*(\d{3,5})|"
        r"自己拥有包含[『「]([^』」]+)[』」]特征的角色卡全数力量值\s*[+＋]\s*(\d{3,5})",
        chunk,
        re.I,
    )
    if m_tr:
        gs = [g for g in m_tr.groups() if g]
        trait, amt = gs[0], int(gs[1])
        op: dict[str, Any] = {
            "op": "buff_all_own",
            "amount": amt,
            "include_leader": False,
            "trait_contains": trait,
            "summary": f"All your {{{trait}}} Characters gain +{amt}",
        }
        if re.search(r"other than this Character|除了這張角色卡以外|除了这张角色卡以外", m_tr.group(0), re.I):
            op["exclude_self"] = True
        return [op]
    # Require explicit '+' so ".{0,40}" cannot swallow "+1" and leave "000".
    m = re.search(
        r"(?:your leader and all of your characters|leader and all of your characters)"
        r".{0,40}\+\s*(\d{3,5})\s*power|"
        r"(?:自己的領航卡和角色卡全數|自己的领航卡和角色卡全数|自己的領航卡與角色卡全數)"
        r".{0,40}力量(?:值)?\+\s*(\d{3,5})|"
        r"(?:all of your characters(?:\s+and your leader)?).{0,40}\+\s*(\d{3,5})\s*power",
        chunk,
        re.I,
    )
    if not m:
        return []
    amt = int(next((g for g in m.groups() if g), "1000"))
    include_leader = bool(re.search(r"leader|領航|领航", m.group(0), re.I))
    return [
        {
            "op": "buff_all_own",
            "amount": amt,
            "include_leader": include_leader,
            "summary": f"Your {'Leader and ' if include_leader else ''}Characters gain +{amt} power",
        }
    ]


def _parse_ko_own_ops(chunk: str) -> list[dict[str, Any]]:
    """
    KO 1 of your Characters — as colon-cost or as a Then effect.
    Detects trait / exclude-self when present.
    """
    if not chunk:
        return []
    # Colon-cost form: "You may K.O. 1 of your {Trait} ... :"
    m_cost = re.search(
        r"(?:you may\s+)?k\.?o\.?\s*1 of your (?:characters?|character cards)"
        r"(?:\s+other than this character)?"
        r"(?:\s+with a type including\s*[\"'「『]([^\"'」』]+)"
        r"|\s+with the \{([^}]+)\}\s*type"
        r"|\s+\{([^}]+)\}\s*type)?"
        r"[^:：]{0,60}[:：]|"
        r"(?:可以)?KO(?:除了這張角色卡以外|除了这张角色卡以外)?\s*1[張张]自己"
        r"(?:擁有包含[『「《]([^』」》]+)[』」》]|拥有包含[『「《]([^』」》]+)[』」》]"
        r"|擁有《([^》]+)》|拥有《([^》]+)》)?[特徵特征]的角色卡[^:：]{0,40}[:：]",
        chunk,
        re.I,
    )
    m_then = re.search(
        r"(?:then[,，]?\s*)k\.?o\.?\s*1 of your (?:characters?|character cards)"
        r"(?:\s+with the \{([^}]+)\}\s*type|\s+\{([^}]+)\}\s*type)?"
        r"|"
        r"(?:之後|之后)[，,]?KO\s*1[張张]自己(?:擁有《([^》]+)》|拥有《([^》]+)》)?",
        chunk,
        re.I,
    )
    m_plain = None
    if not m_cost and not m_then:
        m_plain = re.search(
            r"(?:you may\s+)?k\.?o\.?\s*1 of your (?:characters?|character cards)"
            r"(?:\s+other than this character)?"
            r"(?:\s+with a type including\s*[\"'「『]([^\"'」』]+)"
            r"|\s+with the \{([^}]+)\}\s*type"
            r"|\s+\{([^}]+)\}\s*type)?"
            r"|"
            r"(?:可以)?KO(?:除了這張角色卡以外|除了这张角色卡以外)?\s*1[張张]自己"
            r"(?:擁有包含[『「《]([^』」》]+)[』」》]|拥有包含[『「《]([^』」》]+)[』」》]"
            r"|擁有《([^》]+)》|拥有《([^》]+)》)?",
            chunk,
            re.I,
        )
        if not m_plain:
            return []
    m = m_cost or m_then or m_plain
    assert m is not None
    as_cost = m_cost is not None or (
        m_plain is not None
        and bool(re.search(r"[:：]", chunk[m.start() : min(len(chunk), m.end() + 8)]))
    )
    trait = next((g for g in m.groups() if g), "") or ""
    trait = trait.strip()
    exclude_self = bool(
        re.search(r"other than this character|除了這張角色卡以外|除了这张角色卡以外", m.group(0), re.I)
    )
    op: dict[str, Any] = {
        "op": "ko",
        "target_kind": "own_character",
        "optional": False if as_cost else True,
        "summary": f"KO 1 of your{f' {{{trait}}}' if trait else ''} Characters",
    }
    if trait:
        op["trait_contains"] = trait
    if as_cost:
        op["as_cost"] = True
    if exclude_self:
        op["exclude_self"] = True
    return [op]


def _parse_cost_reduce_family_ops(chunk: str) -> list[dict[str, Any]]:
    """
    Ordered ops for KO-own / cost-reduce / mill / board-buff family.
    Colon-cost KO own comes first; Then-KO own comes after reduce/mill/buff.
    """
    if not chunk:
        return []
    ko_ops = _parse_ko_own_ops(chunk)
    ko_cost = [o for o in ko_ops if o.get("as_cost")]
    ko_then = [o for o in ko_ops if not o.get("as_cost")]
    out: list[dict[str, Any]] = []
    out.extend(ko_cost)
    out.extend(_parse_reduce_cost_ops(chunk))
    out.extend(_parse_buff_all_own_ops(chunk))
    out.extend(_parse_trash_deck_top_ops(chunk))
    out.extend(ko_then)
    # De-dupe identical ops
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for o in out:
        key = json.dumps(o, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(o)
    return deduped


def parse_static_opp_cost_reduce(info: dict[str, Any]) -> dict[str, Any] | None:
    """
    Continuous [Your Turn] (optional [DON!! xN]): give all opponent Characters −N cost.
    """
    text = effect_blob(info)
    if not re.search(
        r"give all of your opponent'?s? characters?\s*[−\-－–]\s*\d+\s*cost|"
        r"對手的角色卡全數費用\s*[−\-－–]\s*\d+|对手的角色卡全数费用\s*[−\-－–]\s*\d+",
        text,
        re.I,
    ):
        return None
    don_n = 0
    if re.search(
        r"\[DON!!\s*x\s*(\d+)\]\s*\[Your Turn\].{0,120}give all of your opponent|"
        r"\[Your Turn\]\s*\[DON!!\s*x\s*(\d+)\].{0,120}give all of your opponent|"
        r"【咚‼?\s*[×xX]\s*(\d+)】\s*【我方回合中】.{0,120}(?:對手的角色卡全數費用|对手的角色卡全数费用)",
        text,
        re.I,
    ):
        m_don = re.search(
            r"\[DON!!\s*x\s*(\d+)\]\s*\[Your Turn\]|\[Your Turn\]\s*\[DON!!\s*x\s*(\d+)\]|"
            r"【咚‼?\s*[×xX]\s*(\d+)】\s*【我方回合中】",
            text,
            re.I,
        )
        if m_don:
            don_n = int(next(g for g in m_don.groups() if g))
    m_amt = re.search(
        r"give all of your opponent'?s? characters?\s*[−\-－–]\s*(\d+)\s*cost|"
        r"對手的角色卡全數費用\s*[−\-－–]\s*(\d+)|对手的角色卡全数费用\s*[−\-－–]\s*(\d+)",
        text,
        re.I,
    )
    if not m_amt:
        return None
    amt = int(next(g for g in m_amt.groups() if g))
    out: dict[str, Any] = {
        "timing": "your_turn",
        "summary": m_amt.group(0).strip()[:240],
        "ops": [{"op": "static_reduce_opp_cost", "amount": -abs(amt)}],
        "status": "compiled",
        "confidence": 0.9,
    }
    if don_n:
        out["require_don_attached_gte"] = don_n
    m_all = re.search(
        r"only (?:Characters|Character cards) on your field are \{([^}]+)\}|"
        r"場上的角色卡只有擁有《([^》]+)》|场上的角色卡只有拥有《([^》]+)》",
        text,
        re.I,
    )
    if m_all:
        out["require_all_chars_trait"] = next(g for g in m_all.groups() if g).strip()
    m_n_trait = re.search(
        r"if you have\s*(\d+)\s*or more \{([^}]+)\} type Characters|"
        r"擁有《([^》]+)》特徵的角色卡有\s*(\d+)\s*張以上|拥有《([^》]+)》特征的角色卡有\s*(\d+)\s*张以上",
        text,
        re.I,
    )
    if m_n_trait:
        gs = [g for g in m_n_trait.groups() if g]
        if gs[0].isdigit():
            out["require_chars_trait_gte"] = int(gs[0])
            out["require_chars_trait"] = gs[1]
        else:
            out["require_chars_trait"] = gs[0]
            out["require_chars_trait_gte"] = int(gs[1])
    return out


def parse_untimed_static(info: dict[str, Any]) -> dict[str, Any] | None:
    """Continuous effects with no [Your Turn]/[On Play] markers."""
    text = effect_blob(info)
    if not text.strip():
        return None
    if re.search(
        r"\[(?:on play|when attacking|activate|trigger|counter|your turn|opponent)\]|"
        r"【(?:登場時|登场时|攻擊時|攻击时|啟動主要|启动主要|觸發器|触发器|反擊|反击|我方回合中)】",
        text,
        re.I,
    ):
        # Still allow static clauses that coexist with timed abilities elsewhere.
        # Handled below only when the whole text is untimed; otherwise return None.
        has_timed = True
    else:
        has_timed = False

    m_don = re.search(r"\[DON!!\s*x\s*(\d+)\]|【咚‼?\s*[×xX]\s*(\d+)】", text, re.I)
    if not has_timed and m_don and re.search(r"also attack .{0,20}active|可以攻擊.?對手活動|可以攻击.?对手活动", text, re.I):
        n = int(next(g for g in m_don.groups() if g))
        return {
            "timing": "don_attached",
            "summary": text.strip()[:240],
            "ops": [{"op": "allow_attack_active", "count": 1, "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.8,
            "require_don_attached_gte": n,
        }

    if not has_timed and re.search(
        r"can attack Characters on the turn in which (?:they are|it is) played|"
        r"登場的回合可以攻擊角色|登场的回合可以攻击角色",
        text,
        re.I,
    ):
        return {
            "timing": "your_turn",
            "summary": text.strip()[:240],
            "ops": [{"op": "grant_keyword", "keyword": "rush_character", "target_kind": "self"}],
            "status": "needs_review",
            "confidence": 0.65,
        }

    if not has_timed and re.search(
        r"cannot be k\.?o\.?'?d in battle|"
        r"不會在對戰中被KO|不会在对战中被KO",
        text,
        re.I,
    ):
        return {
            "timing": "your_turn",
            "summary": text.strip()[:240],
            "ops": [{"op": "cannot_be_ko", "target_kind": "self"}],
            "status": "needs_review",
            "confidence": 0.6,
        }

    if not has_timed and re.search(
        r"would be removed from the field by your opponent|"
        r"因為對手而即將離開場上|因为对手而即将离开场上|"
        r"因對手的效果離開場上|因对手的效果离开场上|"
        r"if this Character would be (?:k\.?o\.?'?d|leave the field).{0,80}trash\s*1\s*card from .{0,40}Life|"
        r"若這張角色卡即將遭到KO時.{0,60}生命值|"
        r"若这张角色卡即将遭到KO时.{0,60}生命值|"
        r"若這張角色卡即將離開場上時.{0,60}生命值|"
        r"若这张角色卡即将离开场上时.{0,60}生命值|"
        r"you may trash this Character instead|可以替換成將這張角色卡放置在廢棄區|可以替换成将这张角色卡放置在废弃区|"
        r"you may rest this Character instead|可以替換成將這張角色卡置為休息狀態|可以替换成将这张角色卡置为休息状态",
        text,
        re.I,
    ):
        ops = _parse_replace_leave_ops(text)
        if ops:
            return {
                "timing": "your_turn",
                "summary": text.strip()[:240],
                "ops": ops,
                "status": "compiled",
                "confidence": 0.85,
                "once": bool(re.search(r"once per turn|每回合1次", text, re.I)),
            }
        return {
            "timing": "your_turn",
            "summary": text.strip()[:240],
            "ops": [{"op": "replace_battle_ko"}],
            "status": "needs_review",
            "confidence": 0.55,
        }

    # Attack lock: cannot attack unless opponent has N Characters with base power ≥ X.
    m_lock = re.search(
        r"cannot attack unless your opponent has\s*(\d+)\s*or more Characters with a base power of\s*(\d+)|"
        r"若場上沒有\s*(\d+)\s*[張张]對手原本力量值\s*(\d+)\s*以上|"
        r"若场上没有\s*(\d+)\s*[张张]对手原本力量值\s*(\d+)\s*以上",
        text,
        re.I,
    )
    if m_lock and re.search(r"cannot attack|無法進行攻擊|无法进行攻击", text, re.I):
        gs = [g for g in m_lock.groups() if g]
        out = {
            "timing": "your_turn",
            "summary": text.strip()[:240],
            "ops": [{"op": "cannot_attack", "target_kind": "self"}],
            "status": "compiled",
            "confidence": 0.85,
            "require_opp_chars_count_gte": int(gs[0]),
            "require_opp_chars_base_power_gte": int(gs[1]),
        }
        return out

    # Plain cannot attack (optionally with hand-trash negate this turn).
    if re.search(r"this Character cannot attack\.|這張角色卡無法進行攻擊|这张角色卡无法进行攻击", text, re.I):
        out = {
            "timing": "your_turn",
            "summary": text.strip()[:240],
            "ops": [{"op": "cannot_attack", "target_kind": "self"}],
            "status": "compiled",
            "confidence": 0.85,
        }
        if re.search(r"trashed from your hand|廢棄自己手牌|废弃自己手牌", text, re.I):
            out["negated_when_hand_trashed"] = True
        return out

    # Taunt while rested.
    if re.search(
        r"if this Character is rested.{0,80}cannot attack any card other|"
        r"若這張角色卡在休息狀態時.{0,80}只能攻擊|"
        r"若这张角色卡在休息状态时.{0,80}只能攻击",
        text,
        re.I,
    ):
        name = ""
        m_name = re.search(r"Character \[([^\]]+)\]|角色卡「([^」]+)」", text)
        if m_name:
            name = next(g for g in m_name.groups() if g)
        return {
            "timing": "opponent_turn",
            "summary": text.strip()[:240],
            "ops": [{"op": "taunt", "target_kind": "self", "while_rested": True, "name_contains": name}],
            "status": "compiled",
            "confidence": 0.85,
            "while_rested": True,
        }

    # Permanent self On Play negation (Blackbeard-style) — untimed only.
    neg = _parse_negate_on_play_ops(text)
    if neg and any(o.get("side") == "self" for o in neg) and not has_timed:
        return {
            "timing": "your_turn",
            "summary": text.strip()[:240],
            "ops": neg,
            "status": "compiled",
            "confidence": 0.8,
        }

    return None


def parse_negate_on_play_aura(info: dict[str, Any]) -> dict[str, Any] | None:
    """Continuous 'Your [On Play] effects are negated' (may coexist with Activate: Main)."""
    text = effect_blob(info)
    if not re.search(
        r"your \[on play\] effects? are negated|自己的【登場時】效果無效|自己的【登场时】效果无效",
        text,
        re.I,
    ):
        return None
    return {
        "timing": "your_turn",
        "summary": "Your [On Play] effects are negated.",
        "ops": [{"op": "negate_on_play", "side": "self", "duration": "permanent"}],
        "status": "compiled",
        "confidence": 0.85,
    }


def parse_hand_cost_reduce(info: dict[str, Any]) -> dict[str, Any] | None:
    """'Give this card in your hand −N cost' with common board/life conditions."""
    text = effect_blob(info)
    m = re.search(
        r"give this card in your hand\s*[−\-－–]\s*(\d+)\s*cost|"
        r"手牌中這張卡片的費用\s*[−\-－–]\s*(\d+)|手牌中这张卡片的费用\s*[−\-－–]\s*(\d+)",
        text,
        re.I,
    )
    if not m:
        return None
    amt = int(next(g for g in m.groups() if g))
    # Clause before the reduce (best-effort: up to ~200 chars before match)
    pre = text[max(0, m.start() - 220) : m.start()]
    out: dict[str, Any] = {
        "timing": "hand_cost",
        "summary": (pre + m.group(0)).strip()[:240],
        "ops": [{"op": "hand_cost_reduce", "amount": -abs(amt)}],
        "status": "compiled",
        "confidence": 0.85,
    }
    m_pow = re.search(r"Character with\s*(\d+)\s*power or more|力量值\s*(\d+)\s*以上", pre, re.I)
    if m_pow and re.search(r"if you have a Character|若場上有自己|若场上有自己", pre, re.I):
        out["require_own_char_power_gte"] = int(next(g for g in m_pow.groups() if g))
    if m_pow and re.search(
        r"if your opponent has a Character|opponent has a Character|"
        r"若對手場上有|若对手场上有|若對手有力量|若对手有力量",
        pre,
        re.I,
    ) and not re.search(r"base power|基礎力量|基础力量", pre, re.I):
        out["require_opp_char_power_gte"] = int(next(g for g in m_pow.groups() if g))
    m_base = re.search(
        r"Character with\s*(\d+)\s*base power or more|基礎力量值\s*(\d+)\s*以上|基础力量值\s*(\d+)\s*以上",
        pre,
        re.I,
    )
    if m_base and re.search(r"opponent|對手|对手", pre, re.I):
        out["require_opp_char_base_power_gte"] = int(next(g for g in m_base.groups() if g))
    m_life = re.search(r"(\d+)\s*or less Life|生命值卡在\s*(\d+)\s*張以下|生命值卡在\s*(\d+)\s*张以下|1 or less Life", pre, re.I)
    if m_life:
        out["require_life_lte"] = int(next((g for g in m_life.groups() if g), "1"))
    if re.search(r"at least 2 less than|少2張以上|少2张以上", pre, re.I):
        out["require_don_field_deficit_gte"] = 2
    m_trash = re.search(r"(\d+)\s*or more cards in your trash|廢棄區有\s*(\d+)\s*張以上|废弃区有\s*(\d+)\s*张以上", pre, re.I)
    if m_trash:
        out["require_trash_gte"] = int(next(g for g in m_trash.groups() if g))
    m_ev = re.search(r"(\d+)\s*or more Events in your trash|廢棄區有\s*(\d+)\s*張以上事件|废弃区有\s*(\d+)\s*张以上事件", pre, re.I)
    if m_ev:
        out["require_trash_events_gte"] = int(next(g for g in m_ev.groups() if g))
    if re.search(r"Leader has 0 power or less|領航卡力量值在0以下|领航卡力量值在0以下", pre, re.I):
        out["require_leader_power_lte"] = 0
    m_trait_pow = re.search(
        r"\{([^}]+)\}\s*type Character with\s*(\d+)\s*power or more|"
        r"擁有《([^》]+)》特徵.{0,20}力量值\s*(\d+)\s*以上|拥有《([^》]+)》特征.{0,20}力量值\s*(\d+)\s*以上",
        pre,
        re.I,
    )
    if m_trait_pow:
        gs = [g for g in m_trait_pow.groups() if g]
        out["require_chars_trait"] = gs[0]
        out["require_own_char_power_gte"] = int(gs[1])
    m_name = re.search(
        r"\[([^\]]+)\]\s*or\s*\[([^\]]+)\] Character with\s*(\d+)\s*base power|"
        r"「([^」]+)」或「([^」]+)」.{0,20}基礎力量值\s*(\d+)",
        pre,
        re.I,
    )
    if m_name:
        gs = [g for g in m_name.groups() if g]
        out["require_own_name_contains"] = "|".join(gs[:-1])
        out["require_own_char_power_gte"] = int(gs[-1])
    m_lead = re.search(r"Leader has the \{([^}]+)\}|領航卡擁有《([^》]+)》|领航卡拥有《([^》]+)》", pre, re.I)
    if m_lead:
        out["require_leader_trait"] = next(g for g in m_lead.groups() if g).strip()
    m_rest = re.search(r"(\d+)\s*or more rested cards|休息狀態的卡片有\s*(\d+)\s*張以上|休息状态的卡片有\s*(\d+)\s*张以上", pre, re.I)
    if m_rest:
        out["require_opp_rested_chars_gte"] = int(next(g for g in m_rest.groups() if g))
    if re.search(
        r"during the turn in which a card (?:in your hand )?is trashed by an effect|"
        r"在因效果而廢棄自己手牌的回合中|在因效果而废弃自己手牌的回合中",
        pre,
        re.I,
    ):
        out["require_hand_trashed_by_effect_this_turn"] = True
    return out


def parse_board_hand_cost_aura(info: dict[str, Any]) -> dict[str, Any] | None:
    """e.g. [DON!! x1] Give blue Events in your hand −1 cost."""
    text = effect_blob(info)
    m = re.search(
        r"(?:\[DON!!\s*x\s*(\d+)\]\s*)?Give\s+(blue|red|green|purple|black|yellow)\s+(Events?|Characters?|Stages?)\s+in your hand\s*[−\-－–]\s*(\d+)\s*cost|"
        r"(?:【咚‼?\s*[×xX]\s*(\d+)】\s*)?自己手牌中的(藍|蓝|紅|红|綠|绿|紫|黑|黃|黄)色(事件卡|角色卡|舞台卡)，費用\s*[−\-－–]\s*(\d+)",
        text,
        re.I,
    )
    if not m:
        return None
    gs = list(m.groups())
    # Normalize groups from EN or ZH
    don_n = 0
    color = ""
    ctype = "event"
    amt = 1
    if gs[0] and str(gs[0]).isdigit() and gs[3]:
        don_n = int(gs[0])
        color = str(gs[1]).lower()
        ctype = str(gs[2]).lower().rstrip("s")
        amt = int(gs[3])
    elif gs[4] is not None or gs[7]:
        if gs[4] and str(gs[4]).isdigit():
            don_n = int(gs[4])
        color_map = {"藍": "blue", "蓝": "blue", "紅": "red", "红": "red", "綠": "green", "绿": "green", "紫": "purple", "黑": "black", "黃": "yellow", "黄": "yellow"}
        color = color_map.get(str(gs[5] or ""), str(gs[5] or "").lower())
        t = str(gs[6] or "")
        ctype = "event" if "事件" in t else ("character" if "角色" in t else "stage")
        amt = int(gs[7] or 1)
    else:
        return None
    out: dict[str, Any] = {
        "timing": "hand_cost",
        "summary": m.group(0).strip()[:240],
        "ops": [{"op": "hand_cost_reduce", "amount": -abs(amt)}],
        "status": "compiled",
        "confidence": 0.85,
        "hand_color": color,
        "hand_card_type": ctype,
    }
    if don_n:
        out["require_don_attached_gte"] = don_n
    return out


def parse_any_don_attach_cost_trigger(info: dict[str, Any]) -> dict[str, Any] | None:
    """
    Garp-style: when Leader or Character is given DON!!, reduce opp Character cost.
    """
    text = effect_blob(info)
    m = re.search(
        r"(?:\[Your Turn\])?\s*When this Leader or 1 of your Characters is given a DON!! card[,:]?\s*"
        r"give up to 1 of your opponent'?s? Characters with a cost of\s*(\d+)\s*or less\s*[−\-－–]\s*(\d+)\s*cost|"
        r"【我方回合中】這張領航卡或自己的角色卡附加咚!!?卡時，最多1張對手費用\s*(\d+)\s*以下的角色卡，在這個回合，費用\s*[−\-－–]\s*(\d+)|"
        r"【我方回合中】这张领航卡或自己的角色卡附加咚!!?卡时，最多1张对手费用\s*(\d+)\s*以下的角色卡，在这个回合，费用\s*[−\-－–]\s*(\d+)",
        text,
        re.I,
    )
    if not m:
        return None
    gs = [g for g in m.groups() if g]
    cost_lte = int(gs[0])
    amt = int(gs[1])
    return {
        "timing": "on_don_attached",
        "summary": m.group(0).strip()[:240],
        "ops": [
            {
                "op": "reduce_cost",
                "amount": -abs(amt),
                "count": 1,
                "target_kind": "opponent_character",
                "cost_lte": cost_lte,
                "optional": True,
                "summary": f"Give up to 1 opponent Character with cost ≤{cost_lte} −{amt} cost",
            }
        ],
        "status": "compiled",
        "confidence": 0.9,
        "on_any_own_don_attach": True,
        "require_your_turn": True,
    }


def _parse_ko_op(chunk: str) -> dict[str, Any] | None:
    """Parse 'K.O. up to 1 ...' with optional stage/cost/power/rested filters."""
    # Never treat "K.O. 1 of your Characters" as opponent KO.
    if re.search(
        r"k\.?o\.?\s*1 of your (?:characters?|character cards)|"
        r"KO(?:除了這張角色卡以外|除了这张角色卡以外)?\s*1[張张]自己",
        chunk,
        re.I,
    ):
        own = _parse_ko_own_ops(chunk)
        return own[0] if own else None
    if not re.search(
        r"k\.?o\.?\s*(?:up to\s*)?(\d+)|KO最多\s*(\d+)|將最多\s*(\d+).{0,40}KO|将最多\s*(\d+).{0,40}KO",
        chunk,
        re.I,
    ):
        return None
    m_n = re.search(
        r"k\.?o\.?\s*(?:up to\s*)?(\d+)|KO最多\s*(\d+)|將最多\s*(\d+).{0,40}KO|将最多\s*(\d+).{0,40}KO",
        chunk,
        re.I,
    )
    count = 1
    if m_n:
        count = max(1, min(3, int(next(g for g in m_n.groups() if g))))
    op: dict[str, Any] = {"op": "ko", "optional": True}
    if count > 1:
        op["count"] = count
    if re.search(r"stage|舞台卡", chunk, re.I):
        op["target_kind"] = "opponent_stage"
    elif re.search(
        r"rested character|休息中的角色|休止中的角色|"
        r"對手休息狀態|对手休息状态|休息狀態(?:的)?(?:對手)?角色|休息状态(?:的)?(?:对手)?角色|"
        r"opponent'?s rested",
        chunk,
        re.I,
    ):
        op["target_kind"] = "opponent_character_rested"
    else:
        op["target_kind"] = "opponent_character"

    m_cost = re.search(
        r"(?:cost of|費用|费用)\s*(\d+)\s*or less|(\d+)\s*or less(?:\s*\w+)?\s*cost|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下",
        chunk,
        re.I,
    )
    if m_cost:
        n = next((int(g) for g in m_cost.groups() if g), None)
        if n is not None:
            if re.search(r"base cost|原本費用|原本费用|基礎費用|基础费用", chunk, re.I):
                op["base_cost_lte"] = n
            else:
                op["cost_lte"] = n
    m_cost_eq = re.search(
        r"(?:cost of|費用|费用)\s*(\d+)(?!\s*or less|以下)|費用\s*(\d+)的|费用\s*(\d+)的",
        chunk,
        re.I,
    )
    # Prefer exact "cost of 1" / 費用1 when not "or less"
    if "cost_lte" not in op and re.search(r"cost of 1(?!\s*or less)|費用1(?!以下)|费用1(?!以下)", chunk, re.I):
        op["cost_eq"] = 1
    elif m_cost_eq and "cost_lte" not in op:
        # only if clearly "Stages with a cost of 1" style without "or less"
        if re.search(r"with a cost of \d+(?!\s*or less)|費用\d+(?!以下)|费用\d+(?!以下)", chunk, re.I):
            n = next((int(g) for g in m_cost_eq.groups() if g), None)
            if n is not None:
                op["cost_eq"] = n

    m_pow = re.search(
        r"(?:(\d+)\s*(?:base\s+)?power or less)|(?:力量[值]?\s*(\d+)\s*以下)|(?:power of\s*(\d+)\s*or less)",
        chunk,
        re.I,
    )
    if m_pow:
        n = next((int(g) for g in m_pow.groups() if g), None)
        if n is not None:
            if re.search(r"base power|基礎力量|基础力量|原本力量", chunk, re.I):
                op["base_power_lte"] = n
            else:
                op["power_lte"] = n
    return op


def parse_on_ko(info: dict[str, Any]) -> dict[str, Any] | None:
    """Parse [On K.O.] continuous-resolution effects into an ability."""
    text = effect_blob(info)
    chunk = _on_ko_chunk(text)
    if not chunk:
        return None
    body = chunk
    ops: list[dict[str, Any]] = []
    if re.search(r"draw 2|抽2", body, re.I):
        ops.append({"op": "draw", "count": 2})
    elif re.search(r"draw 1|抽1", body, re.I):
        ops.append({"op": "draw", "count": 1})
    if re.search(r"(add|gain).{0,24}1 don|咚‼?\s*\+?\s*1|追加.{0,6}1", body, re.I) and not re.search(
        r"don!!\s*−|don!!\s*-|咚‼?\s*−|咚‼?\s*-", body, re.I
    ):
        as_rested = bool(re.search(r"rest it|置為休息|置为休息|休息狀態|休息状态", body, re.I))
        ops.append({"op": "gain_don", "count": 1, **({"as_rested": True} if as_rested else {})})
    if re.search(r"don!!\s*−\s*1|don!!\s*-\s*1|咚‼?\s*−\s*1|咚‼?\s*-\s*1", body, re.I):
        ops.append({"op": "return_don", "count": 1})
    ko_op = _parse_ko_op(body)
    if ko_op:
        ops.append(ko_op)
    play_hand = _parse_play_from_zone(body)
    if play_hand:
        ops.append(play_hand)
    ops.extend(_parse_place_on_bottom_ops(body))
    ops.extend(_parse_return_char_to_hand_ops(body))
    ops.extend(_parse_skip_untap_ops(body))
    life_ops = _parse_life_zone_ops(body)
    if life_ops:
        cost_life = [o for o in life_ops if o.get("as_cost")]
        rest_life = [o for o in life_ops if not o.get("as_cost")]
        if cost_life and not any(o.get("as_cost") for o in ops):
            ops = cost_life + ops
        for o in rest_life:
            if not any(x.get("op") == o.get("op") and x.get("owner") == o.get("owner") for x in ops):
                ops.append(o)
    trash_cost = _parse_trash_hand_cost(body)
    if trash_cost and not any(o.get("op") == "trash_hand" for o in ops):
        ops = trash_cost + ops
    if re.search(
        r"add up to 1 card from the top of your deck to the top of your Life|"
        r"將最多1張自己卡組上面的卡片加到生命值區上面|"
        r"将最多1张自己卡组上面的卡片加到生命值区上面",
        body,
        re.I,
    ):
        ops.append({"op": "add_life", "count": 1})
    if not ops:
        return None
    out: dict[str, Any] = {
        "timing": "on_ko",
        "summary": chunk.strip()[:240],
        "ops": ops,
        "status": "compiled",
        "confidence": 0.8,
    }
    m_life = re.search(r"(\d+)\s*or less Life|生命值卡在\s*(\d+)\s*張以下|生命值卡在\s*(\d+)\s*张以下", body, re.I)
    if m_life:
        out["require_life_lte"] = int(next(g for g in m_life.groups() if g))
    # Leader type/trait gate
    m_trait = re.search(
        r"(?:Leader(?:'s)? type includes|Leader has the)\s*[\"'{《]?([^\"'}》\n]{2,40})[\"'}》]?|"
        r"領航卡擁有包含[『「]?([^』」]{1,40})[』」]?|"
        r"领航卡拥有包含[『「]?([^』」]{1,40})[』」]?|"
        r"領袖擁有《([^》]+)》|领袖拥有《([^》]+)》",
        body,
        re.I,
    )
    if m_trait:
        trait = next((g.strip() for g in m_trait.groups() if g), "")
        trait = trait.strip(" \"'《》『』")
        # Normalize common short forms
        if trait in {"B・W", "B.W", "B·W", "BW"}:
            trait = "Baroque Works"
        if trait:
            out["require_leader_trait"] = trait[:40]
    return out


def _parse_play_from_hand(chunk: str) -> dict[str, Any] | None:
    """Play up to N Character from hand with optional cost/power/name/trait filters."""
    if not re.search(
        r"from your hand|自己手牌中|Play this card|使這張卡片登場|使这张卡片登场",
        chunk,
        re.I,
    ):
        return None
    # Trigger "Play this card" (optionally gated).
    if re.search(r"Play this card|使這張卡片登場|使这张卡片登场", chunk, re.I) and not re.search(
        r"play up to|使最多|Play\s+\d+\s+\{",
        chunk,
        re.I,
    ):
        out_self: dict[str, Any] = {
            "op": "play_from_hand",
            "count": 1,
            "card_type": "character",
            "optional": False,
            "self_card": True,
            "summary": "Play this card",
        }
        return out_self
    if not re.search(r"play up to|使最多|Play\s+\d+\s+\{|使\s*\d+\s*[張张].{0,40}登場|使\s*\d+\s*[张張].{0,40}登场", chunk, re.I):
        return None
    # Prefer the play-from-hand clause (ignore unrelated "play" words)
    m_clause = re.search(
        r"(?:then[,，]?\s*)?play up to\s*\d+.{0,140}?from your hand(?:\s*(?:as )?rested)?|"
        r"Play\s+\d+\s+\{[^}]+\}.{0,80}?from your hand|"
        r"(?:之後|之后)?[，,]?使最多\d+[張张]自己手牌中.{0,100}登場|"
        r"(?:之後|之后)?[，,]?使最多\d+[張张]自己手牌中.{0,100}登场|"
        r"使最多\s*\d+\s*[張张].{0,80}手牌.{0,40}登場|"
        r"使最多\s*\d+\s*[张張].{0,80}手牌.{0,40}登场",
        chunk,
        re.I,
    )
    if not m_clause:
        return None
    text = m_clause.group(0)
    out: dict[str, Any] = {
        "op": "play_from_hand",
        "count": 1,
        "card_type": "character",
        "optional": True,
    }
    # Stage play-from-hand
    if re.search(r"stage|舞台卡", text, re.I):
        out["card_type"] = "stage"
    m_n = re.search(r"(?:play up to|Play|使最多|使)\s*(\d+)", text, re.I)
    if m_n:
        out["count"] = max(1, min(3, int(m_n.group(1))))
    if re.search(r"(?:as )?rested|以休息狀態|以休息状态", text, re.I):
        out["as_rested"] = True

    m_name = re.search(r"「([^」]+)」|\[([^\]]+)\]", text)
    if m_name and re.search(r"手牌中的「|play up to\s*\d+\s*\[", text, re.I):
        out["name_contains"] = (m_name.group(1) or m_name.group(2) or "").strip()
    m_trait = re.search(
        r"\{([^}]+)\}\s*type|擁有《([^》]+)》特徵|拥有《([^》]+)》特征",
        text,
        re.I,
    )
    if m_trait:
        out["trait_contains"] = next((g for g in m_trait.groups() if g), "").strip()

    m_cost = re.search(
        r"(?:with (?:a )?cost of|費用|费用)\s*(\d+)(\s*or less|以下)?",
        text,
        re.I,
    )
    if m_cost:
        n = int(m_cost.group(1))
        if m_cost.group(2):
            out["cost_lte"] = n
        else:
            out["cost_eq"] = n

    m_pow = re.search(r"(?:with\s*)?(\d+)\s*power or less|力量值\s*(\d+)\s*以下", text, re.I)
    if m_pow:
        out["power_lte"] = int(m_pow.group(1) or m_pow.group(2) or 0)

    m_col = re.search(
        r"(?:費用|费用)\s*\d+(?:以下)?(綠|绿|紅|红|藍|蓝|紫|黑|黃|黄)(?:色)?|"
        r"(green|red|blue|purple|black|yellow)\s+(?:character|stage|card)",
        text,
        re.I,
    )
    if m_col:
        out["color"] = next((g for g in m_col.groups() if g), "").strip()

    # Character / stage / named / typed card
    if not out.get("name_contains") and not re.search(r"character|stage|角色卡|舞台卡|type card|特徵的卡片|特征的卡片", text, re.I):
        return None
    return out


def _hand_card_matches_play_op(info: dict[str, Any], op: dict[str, Any]) -> bool:
    want_type = str(op.get("card_type") or "character").lower()
    if card_type_of(info) != want_type:
        return False
    if op.get("cost_eq") is not None:
        if _printed_cost(info) != int(op.get("cost_eq") or 0):
            return False
    elif op.get("cost_lte") is not None:
        if _printed_cost(info) > int(op.get("cost_lte") or 0):
            return False
    if op.get("total_cost_lte") is not None:
        if _printed_cost(info) > int(op.get("total_cost_lte") or 0):
            return False
    if op.get("power_lte") is not None:
        if _printed_power(info) > int(op.get("power_lte") or 0):
            return False
    needle_name = str(op.get("name_contains") or "").strip()
    needle_attr = str(op.get("attribute") or op.get("attr_contains") or "").strip().lower()
    name_hit = bool(needle_name) and _card_matches_name_contains(info, needle_name)
    attr_hit = False
    attr_opts = [x.strip() for x in needle_attr.split("|") if x.strip()] if needle_attr else []
    if attr_opts:
        attrs = card_attr_blob(info).lower()
        aliases = {
            "slash": ("slash", "斬", "斩"),
            "斬": ("slash", "斬", "斩"),
            "斩": ("slash", "斬", "斩"),
            "strike": ("strike", "打"),
            "打": ("strike", "打"),
            "ranged": ("ranged", "射"),
            "射": ("ranged", "射"),
            "special": ("special", "特"),
            "特": ("special", "特"),
            "wisdom": ("wisdom", "知"),
            "知": ("wisdom", "知"),
        }
        for opt in attr_opts:
            keys = aliases.get(opt, (opt,))
            if any(k.lower() in attrs for k in keys):
                attr_hit = True
                break
    if op.get("name_or_attribute") and (needle_name or attr_opts):
        if not (name_hit or attr_hit):
            return False
    elif not op.get("trait_or_attribute"):
        if needle_name and not name_hit:
            return False
        if attr_opts and not attr_hit:
            return False
    excl = str(op.get("exclude_name") or "").strip()
    if excl and _card_excluded_by_name(info, excl):
        return False
    needle_trait = str(op.get("trait_contains") or "").strip().lower()
    trait_any = [str(x).strip().lower() for x in (op.get("trait_any") or []) if str(x).strip()]
    if trait_any:
        needle_trait = "|".join([needle_trait] + trait_any) if needle_trait else "|".join(trait_any)
    if needle_trait:
        traits = _card_trait_blob(info)
        aliases = {
            "impel down": ("impel down", "推進城", "推进城", "インペルダウン"),
            "推進城": ("impel down", "推進城", "推进城", "インペルダウン"),
            "推进城": ("impel down", "推進城", "推进城", "インペルダウン"),
            "インペルダウン": ("impel down", "推進城", "推进城", "インペルダウン"),
            "jailer beast": ("jailer beast", "獄卒獸", "狱卒兽"),
            "獄卒獸": ("jailer beast", "獄卒獸", "狱卒兽"),
            "狱卒兽": ("jailer beast", "獄卒獸", "狱卒兽"),
            "foxy pirates": ("foxy pirates", "弗克西海賊團", "弗克西海贼团"),
            "弗克西海賊團": ("foxy pirates", "弗克西海賊團", "弗克西海贼团"),
            "弗克西海贼团": ("foxy pirates", "弗克西海賊團", "弗克西海贼团"),
            "straw hat crew": ("straw hat crew", "草帽一行人"),
            "草帽一行人": ("straw hat crew", "草帽一行人"),
            "dressrosa": ("dressrosa", "多雷斯羅薩", "多雷斯罗萨"),
            "多雷斯羅薩": ("dressrosa", "多雷斯羅薩", "多雷斯罗萨"),
            "多雷斯罗萨": ("dressrosa", "多雷斯羅薩", "多雷斯罗萨"),
            "kuja pirates": ("kuja pirates", "九蛇海賊團", "九蛇海贼团"),
            "九蛇海賊團": ("kuja pirates", "九蛇海賊團", "九蛇海贼团"),
            "amazon lily": ("amazon lily", "亞馬遜百合", "亚马逊百合"),
            "亞馬遜百合": ("amazon lily", "亞馬遜百合", "亚马逊百合"),
            "亚马逊百合": ("amazon lily", "亞馬遜百合", "亚马逊百合"),
        }
        trait_opts = [x.strip() for x in needle_trait.split("|") if x.strip()]

        def _trait_hit(opt: str) -> bool:
            keys = aliases.get(opt, (opt,))
            return any(k.lower() in traits for k in keys)

        trait_hit = any(_trait_hit(opt) for opt in trait_opts)
        if op.get("trait_or_attribute") and (needle_trait or attr_opts):
            if not (trait_hit or attr_hit):
                return False
        elif op.get("name_or_trait"):
            if not (trait_hit or name_hit):
                return False
        elif not trait_hit:
            return False
    elif op.get("trait_or_attribute") and attr_opts:
        if not attr_hit:
            return False
    color = str(op.get("color") or "").strip()
    if color:
        blob = _card_color_blob(info)
        if not any(a.lower() in blob for a in _color_aliases(color)):
            return False
    if op.get("require_trigger") and not card_has_trigger(info):
        return False
    return True


def _parse_look_top_search(chunk: str) -> dict[str, Any] | None:
    """Parse look-at-top-N → reveal/play up to M matching → hand or play."""
    look_n = 0
    m_top = re.search(r"look at\s*(\d+)\s*cards?\s*from the top", chunk, re.I)
    if m_top:
        look_n = int(m_top.group(1))
    else:
        m_top = re.search(r"(?:從自己的卡組上面)?(?:查看|檢視|检视)\s*(\d+)\s*[張张]", chunk, re.I)
        if m_top:
            look_n = int(m_top.group(1))
    if look_n <= 0:
        return None
    # Secondary clauses (之後 / Then … play from hand) must not pollute search filters.
    m_then = re.search(
        r"(?:[。．!]|\.\s+)\s*(?:之後|之后|然後|然后|Then\b)",
        chunk,
        re.I,
    )
    look_body = chunk[: m_then.start()] if m_then else chunk
    # Filters apply to the revealed/looked cards — ignore leader/field gates before 查看.
    m_look_start = re.search(
        r"(?:從自己的卡組上面)?(?:查看|檢視|检视)\s*\d+|look at\s*\d+\s*cards?\s*from the top",
        look_body,
        re.I,
    )
    reveal_span = look_body[m_look_start.start() :] if m_look_start else look_body
    dest_hand = bool(re.search(r"add (it|them|to your hand)|加入手牌", reveal_span, re.I))
    # Play from among looked cards — not a later "play from hand" after 之後.
    dest_play = (not dest_hand) and bool(
        re.search(
            r"(?:and |; )?play up to\s*\d+|使最多\s*\d+\s*[張张].{0,80}(?:登場|登场)",
            reveal_span,
            re.I,
        )
    )
    if not dest_play and not dest_hand:
        return None
    trait = ""
    name = ""
    m_trait = re.search(r"\{([^}]+)\}\s*type", reveal_span, re.I)
    if m_trait:
        trait = m_trait.group(1).strip()
    if not trait:
        m_inc = re.search(
            r'type including\s*"([^"]+)"|type including\s*\[([^\]]+)\]|'
            r"擁有包含[『「]([^』」]+)[』」]特徵|拥有包含[『「]([^』」]+)[』」]特征",
            reveal_span,
            re.I,
        )
        if m_inc:
            trait = next((g for g in m_inc.groups() if g), "").strip()
    if not trait:
        m_trait = re.search(r"擁有《([^》]+)》特徵|拥有《([^》]+)》特征", reveal_span, re.I)
        if m_trait:
            trait = (m_trait.group(1) or m_trait.group(2) or "").strip()
    # Named search: reveal up to 1 [Zou] / 公開最多1張「佐烏」
    m_name = re.search(
        r"(?:reveal up to\s*\d+\s*\[([^\]]+)\]|公開最多\d+[張张]「([^」]+)」|公开最多\d+[张張]「([^」]+)」)",
        reveal_span,
        re.I,
    )
    if m_name:
        name = next((g for g in m_name.groups() if g), "").strip()
    # Name OR Event: [Sanji] or Event / 「香吉士」或事件
    or_event = bool(
        re.search(
            r"\[([^\]]+)\] or Event|「([^」]+)」或事件卡?|or Event card",
            reveal_span,
            re.I,
        )
    )
    if or_event and not name:
        m_ne = re.search(r"\[([^\]]+)\] or Event|「([^」]+)」或事件", reveal_span, re.I)
        if m_ne:
            name = next((g for g in m_ne.groups() if g), "").strip()
    # Cost filters scoped to look/reveal clause only (not a later 之後 play-from-hand).
    cost_eq = None
    cost_lte = None
    cost_gte = None
    m_range = re.search(
        r"(?:with a )?cost of\s*(\d+)\s*(?:to|-|–)\s*(\d+)|費用\s*(\d+)\s*至\s*(\d+)|费用\s*(\d+)\s*至\s*(\d+)",
        reveal_span,
        re.I,
    )
    if m_range:
        nums = [int(g) for g in m_range.groups() if g]
        if len(nums) >= 2:
            cost_gte, cost_lte = min(nums[0], nums[1]), max(nums[0], nums[1])
    m_cost_gte = re.search(
        r"(?:with a )?cost of\s*(\d+)\s*or more|費用\s*(\d+)\s*以上|费用\s*(\d+)\s*以上",
        reveal_span,
        re.I,
    )
    if m_cost_gte and cost_gte is None:
        cost_gte = int(next(g for g in m_cost_gte.groups() if g))
    m_cost_lte = re.search(
        r"(?:with a )?cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下",
        reveal_span,
        re.I,
    )
    if m_cost_lte and cost_lte is None:
        cost_lte = int(next(g for g in m_cost_lte.groups() if g))
    m_cost = re.search(
        r"(?:reveal up to\s*\d+\s*.{0,24}cost of\s*(\d+)|公開最多\d+[張张]費用(\d+)的|公开最多\d+[张張]费用(\d+)的)",
        reveal_span,
        re.I,
    )
    if m_cost and not trait and not name and cost_lte is None and cost_gte is None:
        cost_eq = int(next(g for g in m_cost.groups() if g))
    # Power filters in reveal clause
    power_lte = None
    power_eq = None
    power_gte = None
    m_plte = re.search(r"(?:power of\s*)?(\d+)\s*or less|力量值\s*(\d+)\s*以下", reveal_span, re.I)
    if m_plte:
        power_lte = int(next(g for g in m_plte.groups() if g))
    m_pgte = re.search(r"(?:power of\s*)?(\d+)\s*or more|力量值\s*(\d+)\s*以上", reveal_span, re.I)
    if m_pgte:
        power_gte = int(next(g for g in m_pgte.groups() if g))
    m_peq = re.search(r"power of\s*(\d+)|力量值\s*(\d+)", reveal_span, re.I)
    if m_peq and power_lte is None and power_gte is None:
        power_eq = int(next(g for g in m_peq.groups() if g))
    max_add = 1
    m_max = re.search(r"(?:reveal up to|公開最多|公开最多|play up to|使最多|up to|最多)\s*(\d+)", reveal_span, re.I)
    if m_max:
        max_add = max(1, min(2, int(m_max.group(1))))
    exclude_name = _parse_exclude_name(reveal_span)
    op: dict[str, Any] = {"op": "search_deck", "top_n": max(1, min(look_n, 8)), "max_add": max_add}
    if trait:
        op["trait_contains"] = trait
    if name:
        op["name_contains"] = name
    if or_event:
        op["or_event"] = True
    if cost_eq is not None:
        op["cost_eq"] = cost_eq
    if cost_lte is not None:
        op["cost_lte"] = cost_lte
    if cost_gte is not None:
        op["cost_gte"] = cost_gte
    if power_lte is not None:
        op["power_lte"] = power_lte
    if power_eq is not None:
        op["power_eq"] = power_eq
    if power_gte is not None:
        op["power_gte"] = power_gte
    if exclude_name:
        op["exclude_name"] = exclude_name
    if dest_hand:
        op["destination"] = "hand"
    elif dest_play:
        op["destination"] = "play"
        op["card_type"] = "character"
        if re.search(r"play.{0,40}rested|休息狀態登場|休息状态登场|as rested", reveal_span, re.I):
            op["as_rested"] = True
    # 「擁有《…》特徵的角色卡」/ "{X} type Character" — Events with the trait are ineligible.
    if not op.get("card_type") and not or_event and re.search(
        r"(?:Character cards?|Characters?\s+(?:with|that)|角色卡)",
        reveal_span,
        re.I,
    ):
        op["card_type"] = "character"
    # Official look-top searches place the rest at the bottom in any order.
    # Trash-the-rest is usually after 之後 / Then — check the full chunk, not only the look clause.
    rest_blob = chunk
    if re.search(
        r"trash the rest|place the rest.{0,40}trash|"
        r"(?:其餘|其余|剩下的?)卡片.{0,12}(?:放到|放置在|送入|放入)?(?:廢棄區|废弃区)",
        rest_blob,
        re.I,
    ) and not re.search(
        r"(?:其餘|其余|剩下的?)卡片.{0,20}(?:依任意順序)?(?:放到|放置在)(?:持有者的)?卡[組组]下面|"
        r"(?:the )?rest.{0,40}bottom of (?:your |the )?deck",
        rest_blob,
        re.I,
    ):
        op["order_bottom"] = False
        op["trash_rest"] = True
    else:
        op["order_bottom"] = True
    return op


def _parse_add_from_trash(chunk: str) -> dict[str, Any] | None:
    """Add up to N cards from trash to hand (not play)."""
    if re.search(r"from your trash(?:\s+as)?\s+rested|從廢棄區.{0,20}登場|从废弃区.{0,20}登场", chunk, re.I):
        # Play-from-trash is handled elsewhere.
        if not re.search(r"to your hand|加入手牌", chunk, re.I):
            return None
    m = re.search(
        r"add up to\s*(\d+).{0,160}?from your trash to your hand|"
        r"將最多\s*(\d+)\s*[張张].{0,120}?廢棄區.{0,80}?加入手牌|"
        r"将最多\s*(\d+)\s*[张張].{0,120}?废弃区.{0,80}?加入手牌|"
        r"add up to\s*(\d+).{0,80}?from your trash|"
        r"將最多\s*(\d+)\s*[張张].{0,40}?自己廢棄區|"
        r"将最多\s*(\d+)\s*[张張].{0,40}?自己废弃区",
        chunk,
        re.I,
    )
    if not m:
        return None
    if not re.search(r"to your hand|加入手牌", m.group(0) + chunk[m.end() : m.end() + 40], re.I):
        # Require hand destination nearby when English "add ... from trash" is ambiguous.
        if not re.search(r"to your hand|加入手牌", chunk, re.I):
            return None
    n = int(next(g for g in m.groups() if g) or 1)
    text = m.group(0)
    op: dict[str, Any] = {
        "op": "add_from_trash",
        "count": max(1, min(5, n)),
        "optional": True,
    }
    if re.search(r"\[trigger\]|【觸發器】|【触发器】|【触发】", text, re.I):
        op["require_trigger"] = True
    if re.search(r"\bevent\b|事件卡", text, re.I):
        op["card_type"] = "event"
    elif re.search(r"\bstage\b|舞台卡", text, re.I):
        op["card_type"] = "stage"
    elif re.search(r"character|角色卡", text, re.I):
        op["card_type"] = "character"
    m_trait = re.search(r"\{([^}]+)\}\s*type|擁有《([^》]+)》|拥有《([^》]+)》|type including\s*[\"']([^\"']+)", text, re.I)
    if m_trait:
        op["trait_contains"] = next((g for g in m_trait.groups() if g), "").strip()
    m_name = re.search(r"\[([^\]]+)\]|「([^」]+)」", text)
    if m_name and not re.search(r"\[Trigger\]|【觸發|【触发", text, re.I):
        name = (m_name.group(1) or m_name.group(2) or "").strip()
        if name and name.lower() not in {"trigger", "blocker", "rush", "on play", "on k.o.", "don!!"}:
            # "other than [Name]" is exclude; plain [Name] is include.
            if re.search(rf"other than\s*\[{re.escape(name)}\]|除了「{re.escape(name)}」", chunk, re.I):
                op["name_exclude"] = name
            else:
                op["name_contains"] = name
    excl = _parse_exclude_name(chunk)
    if excl:
        op["name_exclude"] = excl
    m_cost = re.search(r"(?:with (?:a )?cost of|費用|费用)\s*(\d+)(\s*or less|以下)?", text, re.I)
    if m_cost:
        ncost = int(m_cost.group(1))
        if m_cost.group(2):
            op["cost_lte"] = ncost
        else:
            op["cost_eq"] = ncost
    m_color = re.search(r"\b(red|blue|green|purple|black|yellow)\b|(紅|红|藍|蓝|綠|绿|紫|黑|黃|黄)色", text, re.I)
    if m_color:
        raw = next((g for g in m_color.groups() if g), "")
        color_map = {
            "紅": "red",
            "红": "red",
            "藍": "blue",
            "蓝": "blue",
            "綠": "green",
            "绿": "green",
            "紫": "purple",
            "黑": "black",
            "黃": "yellow",
            "黄": "yellow",
        }
        op["color"] = color_map.get(raw, raw.lower())
    return op


def parse_trigger_ops(info: dict[str, Any]) -> list[dict[str, Any]]:
    text = effect_blob(info)
    ops: list[dict[str, Any]] = []
    if not re.search(r"【觸發器】|【触发】|\[trigger\]", text, re.I):
        return ops
    # Prefer Chinese trigger body when present (some EN prints diverge, e.g. ST22-017).
    # Only match Trigger sections that start a line / slash block — not mid-sentence
    # "card with a [Trigger]" references.
    zh = str(info.get("effect") or "")
    en = str(info.get("effect_en") or "")
    chunk = ""
    for blob in (zh, en, text):
        m = re.search(
            r"(?:^|[\n\r/])\s*(?:【觸發器】|【触发器】|【触发】|\[trigger\])\s*([^\n]*)",
            blob,
            re.I | re.M,
        )
        if m and m.group(1).strip():
            chunk = m.group(1).strip()
            break
    if not chunk:
        return ops
    if re.search(r"draw 2|抽2", chunk, re.I):
        ops.append({"op": "draw", "count": 2})
    elif re.search(r"draw 1|抽1張|抽1张|抽1", chunk, re.I):
        ops.append({"op": "draw", "count": 1})
    if re.search(r"don!!\s*\+1|咚‼?\s*\+?\s*1|add 1 don|追加.{0,6}1张?咚", chunk, re.I):
        ops.append({"op": "gain_don", "count": 1})
    if re.search(r"rest.?1|rest up to 1|休息最多1|將最多1張.{0,8}休息|将最多1张.{0,8}休息", chunk, re.I):
        ops.append({"op": "rest_opponent_character", "count": 1})
    if re.search(r"power\s*\+1000|\+1000|力量\+1000", chunk, re.I):
        ops.append({"op": "buff", "amount": 1000, "target_iid": "leader"})
    ops.extend(_parse_place_on_bottom_ops(chunk))
    ops.extend(_parse_return_char_to_hand_ops(chunk))
    ops.extend(_parse_negate_effects_ops(chunk))
    ops.extend(_parse_activate_timing_ops(chunk))
    ops.extend(_parse_gain_don_ops(chunk))
    ops.extend(_parse_opp_return_don_ops(chunk))
    buff = _parse_leader_or_char_buff(chunk)
    if buff and not any(o.get("op") == "buff" for o in ops):
        ops.append(buff)
    play = _parse_play_from_hand(chunk) or _parse_play_from_zone(chunk)
    if play and not any(o.get("op") == "play_from_hand" for o in ops):
        ops.append(play)
    # Opponent trashes from hand
    m_ot = re.search(
        r"(?:your )?opponent trashes?\s*(\d+)|對手廢棄\s*(\d+)|对手废弃\s*(\d+)",
        chunk,
        re.I,
    )
    if m_ot and not any(o.get("op") == "trash_hand" and o.get("owner") == "opponent" for o in ops):
        ops.append(
            {
                "op": "trash_hand",
                "count": int(next(g for g in m_ot.groups() if g)),
                "optional": False,
                "owner": "opponent",
            }
        )
    if re.search(r"trash 1 card from your hand|廢棄1張自己的手牌|废弃1张自己的手牌", chunk, re.I):
        if not any(o.get("op") == "trash_hand" and o.get("owner") != "opponent" for o in ops):
            ops.append({"op": "trash_hand", "count": 1, "optional": False})
    return ops


def has_activate_main(info: dict[str, Any]) -> bool:
    text = effect_blob(info)
    return bool(re.search(r"【啟動主要】|【启动主要】|\[activate:\s*main\]|\[activate main\]", text, re.I))


def parse_activate_main(info: dict[str, Any]) -> dict[str, Any] | None:
    """
    Best-effort 【启动主要】 parser for common templates.
    Returns {cost_don, rest_self, once, ops, summary, conditions...} or None.
    """
    text = effect_blob(info)
    # Prefer Chinese body when present (cleaner); else English.
    # Allow nested 【登場時】 etc. inside the body (negate On Play effects).
    m = re.search(
        r"(?:【啟動主要】|【启动主要】)"
        r"(?:\s*(?:【每回合1次】|【每回合一次】))?"
        r"((?:(?!【(?:登場時|登场时|攻擊時|攻击时|觸發器|触发器|反擊|反击|我方回合中|對方回合中)】|"
        r"\[(?:on\s+play|when\s+attacking|trigger|counter|your\s+turn)\])[\s\S]){0,420})",
        text,
    )
    if not m:
        m = re.search(
            r"(?:\[activate:\s*main\]|\[activate main\])"
            r"(?:\s*\[once per turn\])?"
            r"((?:(?!\[(?:on\s+play|when\s+attacking|trigger|counter|your\s+turn|opponent)\]|"
            r"【(?:登場時|登场时|攻擊時|攻击时)】)[\s\S]){0,420})",
            text,
            re.I,
        )
    if not m:
        return None
    chunk = m.group(0)
    body = m.group(1) or ""
    # If body was cut before 【登場時】negate clause, append trailing negate sentence from full text.
    if re.search(r"對手的$|对手的$|opponent'?s$", body.strip(), re.I) or (
        re.search(r"trash 1 card from your hand|廢棄1張自己的手牌|废弃1张自己的手牌", chunk, re.I)
        and not _parse_negate_on_play_ops(chunk)
    ):
        neg_tail = re.search(
            r"(?:在下一個對手回合結束前|在下一个对手回合结束前|until the end of your opponent'?s next turn)"
            r".{0,80}?(?:對手的【登場時】效果無效|对手的【登场时】效果无效|opponent'?s \[on play\] effects are negated)",
            text,
            re.I,
        )
        if neg_tail:
            body = body + " " + neg_tail.group(0)
            chunk = chunk + " " + neg_tail.group(0)
    once = bool(re.search(r"【每回合1次】|【每回合一次】|once per turn", chunk, re.I))

    # Cost: circled numbers / DON!! −N (return) / rest N DON
    cost_don = 0  # rest active DON as cost (①)
    return_don_cost = 0  # DON!! −N return to DON deck
    circled = {
        "①": 1,
        "②": 2,
        "③": 3,
        "④": 4,
        "⑤": 5,
        "⑥": 6,
        "⑦": 7,
        "⑧": 8,
        "⑨": 9,
        "⑩": 10,
        "➀": 1,
        "➁": 2,
        "➂": 3,
        "➃": 4,
        "➄": 5,
        "➅": 6,
        "➆": 7,
        "➇": 8,
        "➈": 9,
        "➉": 10,
    }
    for sym, n in circled.items():
        if sym in chunk:
            cost_don = max(cost_don, n)
    m_rest_don = re.search(
        r"(?:you may )?rest\s*(\d+)\s*of your don(?:‼|!!)?\s*cards?\s*:|"
        r"可[將将]\s*(\d+)\s*[張张]?自己的咚.{0,16}置[為为]休息\s*[：:]|"
        r"[將将]\s*(\d+)\s*[張张]?自己的咚.{0,16}置[為为]休息\s*[：:]",
        chunk,
        re.I,
    )
    if m_rest_don:
        cost_don = max(cost_don, int(next(g for g in m_rest_don.groups() if g)))
    m_ret = re.search(r"don!!\s*[−\-~－]\s*(\d+)|咚‼?\s*[−\-~－]\s*(\d+)", chunk, re.I)
    if m_ret:
        return_don_cost = int(m_ret.group(1) or m_ret.group(2) or "0")

    rest_self = bool(
        re.search(
            r"rest this (character|stage|leader)|将此(?:角色|舞台|领袖|領航)卡?转为休息|將此(?:角色|舞台|領袖|領航)卡?轉為休息|"
            r"可以将此|可以將此|rest this stage|"
            r"可將這張(?:角色|舞台|領航)卡置為休息|可将这张(?:角色|舞台|领航)卡置为休息|"
            r"這張(?:角色|舞台|領航)卡置為休息|这张(?:角色|舞台|领航)卡置为休息",
            chunk,
            re.I,
        )
    )

    ops: list[dict[str, Any]] = []
    if return_don_cost:
        ops.append({"op": "return_don", "count": return_don_cost})

    # Lucy-style: Activate Main checks Events already activated this turn (EN FAQ),
    # OR arms a this-turn watcher for future Events (rarer CN 「時」arm wording).
    # Prefer past-check when EN/CN says "if you have activated" / 「若已發動」.
    m_past_event = re.search(
        r"(?:if you have activated|若自己(?:在這個回合|在这个回合)?已?發動|若自己(?:在這個回合|在这个回合)?已?发动).{0,48}"
        r"(?:原本費用|原本费用|a cost of|cost of|base cost of)\s*(\d+)\s*(?:以上|or more).{0,32}"
        r"(?:事件|Event).{0,32}(?:抽\s*(\d+)|draw\s*(\d+))",
        body,
        re.I,
    )
    m_arm_event = None if m_past_event else re.search(
        r"(?:在這個回合|在这个回合|during this turn).{0,40}"
        r"(?:若自己發動|若自己发动|if you activate).{0,40}"
        r"(?:原本費用|原本费用|a cost of|cost of)\s*(\d+)\s*(?:以上|or more).{0,24}"
        r"(?:事件|Event).{0,24}"
        r"(?:抽\s*(\d+)|draw\s*(\d+))",
        body,
        re.I,
    )
    # EN official Lucy: "If you have activated an Event with a base cost of 3 or more during this turn, draw 1"
    if not m_past_event:
        m_past_event = re.search(
            r"(?:if you have activated an event).{0,80}"
            r"(?:base cost of|a cost of|cost of)\s*(\d+)\s*(?:or more).{0,40}"
            r"draw\s*(\d+)",
            body,
            re.I,
        )
    if m_past_event:
        cost_gte = int(m_past_event.group(1) or 3)
        draw_n = int(m_past_event.group(2) or m_past_event.group(3) or 1)
        ops.append(
            {
                "op": "draw",
                "count": max(1, min(5, draw_n)),
                "require_event_activated_cost_gte": cost_gte,
            }
        )
    elif m_arm_event:
        # Activate: Main + this-turn Event wording → check already-activated (EN FAQ), not arm.
        cost_gte = int(m_arm_event.group(1) or 3)
        draw_n = int(m_arm_event.group(2) or m_arm_event.group(3) or 1)
        ops.append(
            {
                "op": "draw",
                "count": max(1, min(5, draw_n)),
                "require_event_activated_cost_gte": cost_gte,
            }
        )
    # Draw (avoid matching "draw" inside unrelated words / Event gates)
    elif re.search(r"draw 2|抽2張|抽2张|抽2", body, re.I):
        ops.append({"op": "draw", "count": 2})
    elif re.search(r"draw 1|抽1張|抽1张|抽1(?!0)", body, re.I):
        ops.append({"op": "draw", "count": 1})

    # Power buff on self (leader/character) — only if clearly this card gains power
    # (deferred until after cost-reduce / KO family so "afterwards if…" clauses stay last)
    pending_buff_self: dict[str, Any] | None = None
    if re.search(
        r"this (leader|character) gains?\s*\+?(1000|2000|3000)|"
        r"這[張张].{0,12}(?:領航|领航|角色).{0,40}力量(?:值)?\+(1000|2000|3000)|"
        r"力量(?:值)?\+(1000|2000|3000).{0,24}(?:直到|直至|下一個|下一个)",
        body,
        re.I,
    ):
        amt = 1000
        m_amt = re.search(r"\+(1000|2000|3000)", body)
        if m_amt:
            amt = int(m_amt.group(1))
        pending_buff_self = {"op": "buff_self", "amount": amt}
        # "Afterwards, if there is a 0-cost Character on the field, this Leader gains +1000"
        if re.search(
            r"(?:之後|之后|afterwards?).{0,12}(?:若|if).{0,40}(?:費用|费用)\s*\d+\s*的角色|"
            r"(?:之後|之后|afterwards?).{0,12}(?:若|if).{0,40}cost of\s*\d+",
            body,
            re.I,
        ):
            field_ceq = _extract_require_field_char_cost_eq(body)
            if field_ceq is not None:
                pending_buff_self["require_field_char_cost_eq"] = field_ceq

    # Rest opponent — do NOT match resting your own DON!! / your cards as cost
    if re.search(
        r"rest up to 1 of your opponent|rest up to 1 of your opponent's|"
        r"將對方最多1|将对方最多1|休息最多1張對手|休息最多1张对手",
        body,
        re.I,
    ):
        ops.append({"op": "rest_opponent_character", "count": 1})

    # DON!! bang variants in TC/EN printings: U+203C ‼ or ASCII !!
    _don = r"(?:‼|!!)"

    # Refresh rested DON on field (OP16-022 style) — NOT "add from DON!! deck"
    add_from_deck = bool(
        re.search(
            rf"add up to\s*\d+\s*don{_don}\s*cards?\s*from your don{_don}\s*deck|"
            rf"從(?:自己的)?咚{_don}?卡組追加|从(?:自己的)?咚{_don}?卡组追加|"
            rf"追加(?:最多)?\d+張(?:活動|休息)狀態的咚|追加(?:最多)?\d+张(?:活动|休息)状态的咚",
            body,
            re.I,
        )
    )
    m_refresh = re.search(
        rf"set up to\s*(\d+)\s*of your don{_don}\s*cards as active|"
        r"(?:將最多|将最多)\s*(\d+)\s*張?自己的咚|"
        r"(?:將最多|将最多)\s*(\d+)\s*張?.{0,8}咚.{0,16}置為活動|"
        r"(?:將最多|将最多)\s*(\d+)\s*張?.{0,8}咚.{0,16}置为活动",
        body,
        re.I,
    )
    if m_refresh and not add_from_deck:
        n = int(next(g for g in m_refresh.groups() if g) or "1")
        ops.append({"op": "active_don", "count": max(1, min(5, n))})
    elif (
        not add_from_deck
        and re.search(
            rf"set up to\s*\d+\s*of your don{_don}\s*cards as active|"
            rf"咚{_don}?卡置為活動狀態|咚{_don}?卡置为活动状态",
            body,
            re.I,
        )
    ):
        m_n = re.search(r"(?:up to|最多)\s*(\d+)", body, re.I)
        ops.append({"op": "active_don", "count": max(1, min(5, int(m_n.group(1) if m_n else 1)))})

    # Add DON from DON deck (active by default; rested when text says so)
    if add_from_deck:
        m_add = re.search(
            rf"(?:up to|最多)\s*(\d+)|追加(?:最多)?\s*(\d+)\s*張|add\s+(\d+)\s+don{_don}",
            body,
            re.I,
        )
        n = int(next((g for g in (m_add.groups() if m_add else ()) if g), "1"))
        gain_op: dict[str, Any] = {"op": "gain_don", "count": max(1, min(5, n))}
        if re.search(
            rf"休息狀態的咚|休息状态的咚|rested (?:state )?don|don{_don}\s*card.{0,24}rest it|and rest it",
            body,
            re.I,
        ):
            gain_op["as_rested"] = True
        ops.append(gain_op)
    search_op = _parse_look_top_search(chunk)
    if search_op:
        ops.append(search_op)

    ops.extend(_parse_place_on_bottom_ops(body))
    ops.extend(_parse_return_char_to_hand_ops(body))

    # KO-own / cost-reduce / mill / board-buff family (Crocodile, Moria, etc.)
    family = _parse_cost_reduce_family_ops(body) or _parse_cost_reduce_family_ops(chunk)
    for op in family:
        if op.get("op") == "ko" and any(o.get("op") == "ko" for o in ops):
            continue
        if op.get("op") == "reduce_cost" and any(o.get("op") == "reduce_cost" for o in ops):
            continue
        if op.get("op") == "trash_deck_top" and any(o.get("op") == "trash_deck_top" for o in ops):
            continue
        if op.get("op") == "buff_all_own" and any(o.get("op") == "buff_all_own" for o in ops):
            continue
        ops.append(op)

    trash_cost = _parse_trash_hand_cost(chunk)
    if trash_cost and not any(o.get("op") == "trash_hand" for o in ops):
        ops = trash_cost + ops

    ops.extend(_parse_negate_on_play_ops(body) or _parse_negate_on_play_ops(chunk))
    ops.extend(_parse_negate_effects_ops(body))
    ops.extend(_parse_restriction_ops(body) or _parse_restriction_ops(chunk))
    ops.extend(_parse_skip_untap_ops(body) or _parse_skip_untap_ops(chunk))
    ops.extend(_parse_redirect_attack_ops(body) or _parse_redirect_attack_ops(chunk))
    ops.extend(_parse_hand_to_deck_ops(body))
    ops.extend(_parse_deny_attack_ops(body) or _parse_deny_attack_ops(chunk))
    ops.extend(_parse_deny_rest_ops(body) or _parse_deny_rest_ops(chunk))
    trash_debuff = _parse_trash_self_power_debuff(body) or _parse_trash_self_power_debuff(chunk)
    if trash_debuff:
        follow_kinds = {
            str(o.get("op") or "")
            for o in trash_debuff
            if not (o.get("op") == "trash" and o.get("target_kind") == "self")
        }
        ops = [o for o in ops if str(o.get("op") or "") not in follow_kinds]
        ops = [o for o in ops if not (o.get("op") == "trash" and o.get("target_kind") == "self")]
        costish = [
            o
            for o in ops
            if o.get("as_cost") or o.get("op") in {"return_don", "rest_don", "trash_hand", "flip_life"}
        ]
        rest = [o for o in ops if o not in costish]
        ops = [*costish, *trash_debuff, *rest]
    else:
        ops.extend(_parse_set_cost_ops(body) or _parse_set_cost_ops(chunk))
        ko = _parse_ko_op(body) or _parse_ko_op(chunk)
        if ko and not any(o.get("op") == "ko" for o in ops):
            ops.append(ko)
        trash_opp = _parse_trash_opponent_char_ops(body) or _parse_trash_opponent_char_ops(chunk)
        for top in trash_opp:
            if not any(o.get("op") == "trash" and o.get("target_kind") == top.get("target_kind") for o in ops):
                ops.append(top)
    # Trash-this-Character colon cost: prepend when follow-up was parsed separately.
    if _has_trash_self_colon_cost(body) or _has_trash_self_colon_cost(chunk):
        if ops and not any(o.get("op") == "trash" and o.get("target_kind") == "self" for o in ops):
            ops = [_trash_self_as_cost_op(), *ops]
    if pending_buff_self is not None and not any(o.get("op") == "buff_self" for o in ops):
        ops.append(pending_buff_self)
    # Rest opponent — attach cost filters when present
    if re.search(
        r"rest up to 1 of your opponent|將最多1[張张]對手.{0,40}置為休息|将最多1[张張]对手.{0,40}置为休息|"
        r"將對方最多1|将对方最多1|休息最多1[張张]對手|休息最多1[张張]对手",
        body,
        re.I,
    ):
        existing = next((o for o in ops if o.get("op") == "rest_opponent_character"), None)
        if existing is None:
            existing = {"op": "rest_opponent_character", "count": 1}
            ops.append(existing)
        m_ceq = re.search(r"(?:費用|费用)\s*(\d+)\s*的角色|cost of\s*(\d+)(?!\s*or less)", body, re.I)
        if m_ceq and existing.get("cost_eq") is None:
            existing["cost_eq"] = int(m_ceq.group(1) or m_ceq.group(2))
        m_clte = re.search(r"(?:費用|费用)\s*(\d+)\s*以下|cost of\s*(\d+)\s*or less", body, re.I)
        if m_clte and existing.get("cost_lte") is None:
            existing["cost_lte"] = int(m_clte.group(1) or m_clte.group(2))
    life_ops = _parse_life_zone_ops(body) or _parse_life_zone_ops(chunk)
    if life_ops:
        cost_life = [o for o in life_ops if o.get("as_cost")]
        rest_life = [o for o in life_ops if not o.get("as_cost")]
        if cost_life and not any(o.get("as_cost") for o in ops):
            ops = cost_life + ops
        for o in rest_life:
            if not any(x.get("op") == o.get("op") and x.get("owner") == o.get("owner") for x in ops):
                ops.append(o)

    # Grant rush_character: can attack Characters on the turn played.
    if re.search(
        r"can attack Characters on the turn in which (?:they are|it is) played|"
        r"在登場的回合即可攻擊角色|在登场的回合即可攻击角色|"
        r"登場的回合即可攻擊角色|登场的回合即可攻击角色",
        body,
        re.I,
    ):
        op_kw: dict[str, Any] = {
            "op": "grant_keyword",
            "keyword": "rush_character",
            "target_kind": "own_character",
            "optional": True,
            "summary": "Choose a Character that can attack Characters the turn it is played",
        }
        m_tr = re.search(r"\{([^}]+)\}|《([^》]+)》", body)
        # Prefer Fish-Man / Merfolk dual trait — store first trait; engine trait check is contains.
        if m_tr:
            op_kw["trait_contains"] = next(g for g in m_tr.groups() if g)
        ops.append(op_kw)

    # Conditions
    require_all_chars_trait = ""
    m_trait = re.search(
        r"only (?:characters|character cards).{0,48}\{([^}]+)\}|"
        r"(?:場上的)?角色卡只有擁有《([^》]+)》|角色卡只有拥有《([^》]+)》|"
        r"只有擁有《([^》]+)》特徵的角色|只有拥有《([^》]+)》特征的角色",
        body,
        re.I,
    )
    if m_trait:
        require_all_chars_trait = next((g for g in m_trait.groups() if g), "").strip()

    require_leader_trait = ""
    m_lead = re.search(
        r"if your leader has the \{([^}]+)\}|"
        r"領航卡擁有《([^》]+)》|领航卡拥有《([^》]+)》",
        body,
        re.I,
    )
    if m_lead:
        require_leader_trait = next((g for g in m_lead.groups() if g), "").strip()

    require_char_power_gte = 0
    m_pow = re.search(
        r"character with\s*(\d+)\s*power or more|力量值\s*(\d+)\s*以上",
        body,
        re.I,
    )
    if m_pow:
        require_char_power_gte = int(m_pow.group(1) or m_pow.group(2) or "0")

    if not ops:
        return None
    out: dict[str, Any] = {
        "cost_don": cost_don,
        "rest_self": rest_self,
        "once": once,
        "ops": ops,
        "summary": chunk.strip()[:180],
    }
    if require_all_chars_trait:
        out["require_all_chars_trait"] = require_all_chars_trait
    if require_leader_trait:
        out["require_leader_trait"] = require_leader_trait
    if require_char_power_gte:
        out["require_char_power_gte"] = require_char_power_gte
    # Whole-ability field cost gate (rare on Activate; common on On Play via templates).
    field_ceq = _extract_require_field_char_cost_eq(body) or _extract_require_field_char_cost_eq(chunk)
    if field_ceq is not None and not any(o.get("require_field_char_cost_eq") is not None for o in ops):
        # Only gate the whole activate when the condition is not a trailing "afterwards" clause.
        if not re.search(r"(?:之後|之后|afterwards?).{0,12}(?:若|if)", body, re.I):
            out["require_field_char_cost_eq"] = field_ceq
    scope = body if len((body or "").strip()) > 10 else chunk
    out["ops"] = _enrich_ops_with_target_filters(ops, scope)
    return _apply_common_text_gates(out, scope)


def card_has_trigger(info: dict[str, Any]) -> bool:
    """True if the card has a printed [Trigger] ability.

    Mentions like 「持有【觸發器】」 / "with a [Trigger]" in another effect do not count.
    """
    for key in ("trigger", "trigger_en"):
        blob = str(info.get(key) or "").strip()
        if blob and re.search(r"【觸發器】|【触发】|\[trigger\]", blob, re.I):
            return True
    text = effect_blob(info)
    return bool(re.search(r"(?:^|[。．!\n])\s*(?:【觸發器】|【触发】|\[Trigger\])", text, re.I))


def _don_room(player: PlayerState) -> int:
    cap = int(getattr(player, "don_deck_size", 0) or 10)
    if cap <= 0:
        cap = 10
    return max(0, cap - int(player.don_given or 0))


def apply_ops(state: MatchState, seat: int, ops: list[dict[str, Any]], catalog: Callable[[str], dict[str, Any]]) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    player = state.player(seat)
    foe = state.player(state.other(seat))
    queue = list(ops)

    def _halt_for_replace(leave_kind: str, extra: list[dict[str, Any]] | None = None) -> bool:
        from battle.leave_replace import stash_replace_resume

        return stash_replace_resume(
            state,
            leave_kind=leave_kind,
            apply_seat=seat,
            extra_ops=extra,
            queue=queue,
        )

    def _pause_if_nested_prompt() -> bool:
        """If a nested self-rested (etc.) opened a prompt, keep outer remaining ops."""
        if state.pending_choice:
            if queue:
                state.pending_choice.remaining_ops = list(state.pending_choice.remaining_ops or []) + list(queue)
            return True
        if state.pending_search or getattr(state, "pending_effect", None):
            return True
        return False

    while queue:
        op = queue.pop(0)
        as_seat = op.get("_as_seat")
        if as_seat is not None and int(as_seat) != int(seat):
            nested = dict(op)
            nested.pop("_as_seat", None)
            logs.extend(apply_ops(state, int(as_seat), [nested], catalog))
            if _pause_if_nested_prompt():
                return logs
            continue
        kind = str(op.get("op") or "")
        if kind == "unsupported":
            logs.append({"key": "play.log.effect_unsupported", "id": str(op.get("reason") or "")})
            continue
        # Defer until End Phase (this player's turn end).
        if op.get("at_end_of_turn"):
            deferred = dict(op)
            deferred.pop("at_end_of_turn", None)
            if deferred.get("effect_played_only"):
                iids = list(getattr(player, "_last_effect_played_iids", None) or [])
                if not iids:
                    continue
                deferred.pop("effect_played_only", None)
                deferred["target_iid"] = iids[-1]
            player.pending_end_of_turn_ops.append(deferred)
            logs.append({"key": "play.log.effect_applied", "summary": f"queue_end_of_turn:{kind}"})
            continue
        if op.get("if_trashed") and int(getattr(player, "_last_trash_hand_count", 0) or 0) <= 0:
            continue
        if op.get("if_returned") and int(getattr(player, "_last_return_to_hand_count", 0) or 0) <= 0:
            continue
        if op.get("if_played") and int(getattr(player, "_last_play_from_hand_count", 0) or 0) <= 0:
            continue
        if op.get("require_own_name_all") or op.get("require_chars_base_power_eq") is not None:
            from battle.engine import _ability_board_conditions_ok

            if not _ability_board_conditions_ok(state, seat, op, catalog):
                continue
        if op.get("if_declared_cost_match") and not getattr(player, "_declare_cost_match", False):
            continue
        if op.get("require_opp_hand_gte") is not None and len(foe.hand) < int(op["require_opp_hand_gte"]):
            continue
        if op.get("require_opp_hand_lte") is not None and len(foe.hand) > int(op["require_opp_hand_lte"]):
            continue
        if op.get("require_hand_gte") is not None and len(player.hand) < int(op["require_hand_gte"]):
            continue
        if op.get("require_hand_lte") is not None and len(player.hand) > int(op["require_hand_lte"]):
            continue
        if op.get("require_event_activated_cost_gte") is not None:
            need = int(op["require_event_activated_cost_gte"])
            costs = list(getattr(player, "event_activated_costs", None) or [])
            if not any(int(c) >= need for c in costs):
                continue
        if op.get("require_life_lte") is not None and len(player.life) > int(op["require_life_lte"]):
            continue
        if op.get("require_life_gte") is not None and len(player.life) < int(op["require_life_gte"]):
            continue
        if op.get("require_trash_gte") is not None and len(player.trash) < int(op["require_trash_gte"]):
            continue
        if op.get("require_opp_life_lte") is not None and len(foe.life) > int(op["require_opp_life_lte"]):
            continue
        if op.get("require_opp_life_gte") is not None and len(foe.life) < int(op["require_opp_life_gte"]):
            continue
        if op.get("require_leader_active") and bool(getattr(player, "leader_rested", False)):
            if op.get("as_cost"):
                return logs
            continue
        if op.get("require_life_less_than_opponent") and not (len(player.life) < len(foe.life)):
            continue
        if op.get("require_leader_multicolor"):
            lead = catalog(player.leader_card_id)
            colors = normalize_colors(lead.get("colors_en") or lead.get("colors"))
            if len(colors) < 2:
                continue
        if op.get("require_chars_deficit_gte") is not None:
            from battle.engine import _ability_board_conditions_ok

            if not _ability_board_conditions_ok(state, seat, op, catalog):
                continue
        if op.get("require_chars_trait_gte") is not None or (
            op.get("require_chars_trait") and op.get("require_chars_trait_gte") is not None
        ):
            from battle.engine import _ability_board_conditions_ok

            if not _ability_board_conditions_ok(state, seat, op, catalog):
                continue
        if op.get("require_own_char_cost_gte") is not None:
            from battle.engine import _ability_board_conditions_ok

            if not _ability_board_conditions_ok(state, seat, op, catalog):
                continue
        if op.get("require_given_don_gte") is not None:
            from battle.engine import _ability_board_conditions_ok

            if not _ability_board_conditions_ok(state, seat, op, catalog):
                continue
        if op.get("require_opp_rested_chars_gte") is not None:
            from battle.engine import _ability_board_conditions_ok

            if not _ability_board_conditions_ok(state, seat, op, catalog):
                continue
        if (
            op.get("require_opp_don_field_gte") is not None
            or op.get("require_don_field_gte") is not None
            or op.get("require_don_field_lte") is not None
        ):
            from battle.engine import _ability_board_conditions_ok

            if not _ability_board_conditions_ok(state, seat, op, catalog):
                continue
        if op.get("require_don_field_deficit_gte") is not None:
            from battle.engine import _ability_board_conditions_ok

            if not _ability_board_conditions_ok(state, seat, op, catalog):
                continue
        if op.get("require_opp_char_power_gte") is not None:
            from battle.engine import _ability_board_conditions_ok

            if not _ability_board_conditions_ok(state, seat, op, catalog):
                continue
        if op.get("require_own_char_power_gte") is not None:
            from battle.engine import inst_power

            need = int(op["require_own_char_power_gte"])
            if not any(inst_power(state, seat, c.iid, catalog) >= need for c in player.characters):
                continue
        if op.get("require_rested_own_chars_gte") is not None:
            need = int(op["require_rested_own_chars_gte"])
            rested = sum(1 for c in player.characters if c.rested)
            if rested < need:
                continue
        if op.get("require_rested_cards_gte") is not None:
            need = int(op["require_rested_cards_gte"])
            rested = int(player.don_rested or 0) + sum(1 for c in player.characters if c.rested)
            if player.leader_rested:
                rested += 1
            rested += sum(1 for s in (getattr(player, "stages", None) or []) if getattr(s, "rested", False))
            if rested < need:
                continue
        if op.get("require_leader_trait"):
            from battle.engine import _info_has_trait

            lead = catalog(player.leader_card_id)
            if not _info_has_trait(lead, str(op["require_leader_trait"])):
                continue
        if op.get("require_played_this_turn"):
            src_iid = str(op.get("source_iid") or "")
            src = None
            if src_iid and src_iid != "leader":
                src = next((c for c in player.characters if c.iid == src_iid), None)
            if src is None or not getattr(src, "summoning_sick", False):
                continue
        if op.get("require_leader_name"):
            lead = catalog(player.leader_card_id)
            needles = [x.strip() for x in str(op["require_leader_name"]).split("|") if x.strip()]
            blob = " ".join(
                str(x or "")
                for x in (lead.get("name"), lead.get("name_en"), lead.get("name_cn"), player.leader_card_id)
            )
            if needles and not any(n in blob for n in needles):
                continue
        if op.get("require_leader_attribute"):
            lead = catalog(player.leader_card_id)
            want = str(op["require_leader_attribute"]).strip().lower()
            blob = card_attr_blob(lead).lower()
            opts = [a.strip().lower() for a in want.split("|") if a.strip()] or [want]
            if not any(any(k in blob for k in attr_alias_keys(o)) for o in opts):
                continue
        if op.get("require_field_char_cost_eq") is not None:
            need = int(op["require_field_char_cost_eq"])
            try:
                from battle.engine import effective_character_cost

                has = False
                for s in (seat, state.other(seat)):
                    for c in state.player(s).characters:
                        if effective_character_cost(state, s, c, catalog) == need:
                            has = True
                            break
                    if has:
                        break
                if not has:
                    continue
            except Exception:
                continue
        if op.get("require_field_char_cost_gte") is not None:
            gte = int(op["require_field_char_cost_gte"])
            try:
                from battle.engine import effective_character_cost

                has = False
                for s in (seat, state.other(seat)):
                    for c in state.player(s).characters:
                        if effective_character_cost(state, s, c, catalog) >= gte:
                            has = True
                            break
                    if has:
                        break
                if not has:
                    continue
            except Exception:
                continue
        if op.get("require_opp_char_cost_0_or_gte") is not None:
            gte = int(op["require_opp_char_cost_0_or_gte"])
            try:
                from battle.engine import effective_character_cost

                has = False
                for c in foe.characters:
                    cost = effective_character_cost(state, state.other(seat), c, catalog)
                    if cost == 0 or cost >= gte:
                        has = True
                        break
                if not has:
                    continue
            except Exception:
                continue
        if kind == "draw":
            if op.get("equal_trashed"):
                n = max(0, int(getattr(player, "_last_trash_hand_count", 0) or 0))
                if n <= 0:
                    continue
            elif op.get("until_hand_size") is not None:
                target = max(0, int(op["until_hand_size"]))
                n = max(0, target - len(player.hand))
            else:
                n = max(1, int(op.get("count") or 1))
            drawn = 0
            for _ in range(n):
                if not player.deck:
                    break
                player.hand.append(player.deck.pop(0))
                drawn += 1
            if drawn:
                logs.append({"key": "play.log.draws", "name": player.username, "n": drawn})
        elif kind == "gain_don":
            if op.get("require_opp_char_base_power_gte") is not None:
                need = int(op["require_opp_char_base_power_gte"])
                if not any(int(getattr(c, "power", 0) or 0) >= need or int((catalog(c.card_id) or {}).get("power") or 0) >= need for c in foe.characters):
                    continue
            n = max(1, int(op.get("count") or 1))
            room = _don_room(player)
            n = min(n, room)
            player.don_given += n
            if op.get("as_rested"):
                player.don_rested += n
            else:
                player.don_active += n
            if n:
                logs.append({"key": "play.log.gains_don", "name": player.username, "n": n})
        elif kind == "rest_don":
            any_number = bool(op.get("any_number"))
            optional = bool(op.get("optional", False))
            as_cost = bool(op.get("as_cost"))
            token = str(op.get("target_iid") or "").strip().lower()
            don_owner = foe if str(op.get("owner") or "self") == "opponent" else player
            if any_number:
                cap = max(1, min(10, int(op.get("count") or 10)))
                n = 1
            else:
                n = max(1, int(op.get("count") or 1))
                cap = n
            if not op.get("_continue_rest_don") and token not in {"don", "yes"}:
                setattr(player, "_last_rest_don_count", 0)
            already = int(getattr(player, "_last_rest_don_count", 0) or 0)
            if any_number and already >= cap:
                continue
            available = int(don_owner.don_active or 0)
            if available < n:
                if as_cost and (not any_number or already <= 0):
                    return logs
                continue
            # Optional 「可將…咚‼置為休息」must ask; any_number always asks each tick.
            need_prompt = (bool(any_number) or optional) and token not in {"don", "yes"}
            if need_prompt and not state.pending_choice:
                rem = dict(op)
                rem.pop("target_iid", None)
                state.pending_choice = PendingChoice(
                    seat=seat,
                    card_id=str(op.get("card_id") or ""),
                    source_iid=str(op.get("source_iid") or ""),
                    target_kind="don",
                    options=["don"],
                    remaining_ops=[rem, *queue],
                    optional=True,
                    summary=str(op.get("summary") or ("Rest DON!!" if any_number else "Rest 1 DON!!")),
                    purpose=purpose_from_op(op),
                )
                logs.append({"key": "play.log.choice_offer", "name": player.username})
                return logs
            take = min(1 if any_number else n, available)
            don_owner.don_active -= take
            don_owner.don_rested += take
            if take:
                logs.append({"key": "play.log.rest_don", "name": don_owner.username, "n": take})
                setattr(player, "_last_rest_don_count", already + take)
            elif as_cost:
                return logs
            if any_number:
                left_cap = cap - int(getattr(player, "_last_rest_don_count", 0) or 0)
                if left_cap > 0 and int(don_owner.don_active or 0) > 0:
                    cont = dict(op)
                    cont["count"] = left_cap
                    cont["optional"] = True
                    cont["_continue_rest_don"] = True
                    cont.pop("target_iid", None)
                    queue.insert(0, cont)
        elif kind == "return_attached_don":
            # Return up to N attached DON!! to the cost area as rested (合計已附加 → 費用區).
            n = max(1, int(op.get("count") or 1))
            optional = bool(op.get("optional", False))
            total_attached = int(player.leader_don or 0) + sum(int(c.don_attached or 0) for c in player.characters)
            if total_attached < n:
                if op.get("as_cost") or not optional:
                    return logs
                continue
            remaining = n
            # Prefer source character / leader first, then others (deterministic).
            source = str(op.get("source_iid") or "")
            order: list[tuple[str, Any]] = []
            if source == "leader" and int(player.leader_don or 0) > 0:
                order.append(("leader", None))
            elif source:
                src_ch = next((c for c in player.characters if c.iid == source), None)
                if src_ch and int(src_ch.don_attached or 0) > 0:
                    order.append(("char", src_ch))
            if int(player.leader_don or 0) > 0 and ("leader", None) not in order:
                order.append(("leader", None))
            for ch in player.characters:
                if int(ch.don_attached or 0) > 0 and all(ch is not x for _, x in order if x is not None):
                    order.append(("char", ch))
            taken = 0
            for kind_src, inst in order:
                if remaining <= 0:
                    break
                if kind_src == "leader":
                    take = min(remaining, int(player.leader_don or 0))
                    player.leader_don -= take
                else:
                    take = min(remaining, int(inst.don_attached or 0))
                    inst.don_attached -= take
                remaining -= take
                taken += take
            if taken:
                player.don_rested += taken
                player.don_given = max(0, int(player.don_given or 0) - taken)
                logs.append({"key": "play.log.return_attached_don", "name": player.username, "n": taken})
            elif op.get("as_cost"):
                return logs
        elif kind == "active_don":
            if op.get("all"):
                n = max(1, int(player.don_rested or 0))
            else:
                n = max(1, int(op.get("count") or 1))
            take = min(n, player.don_rested)
            player.don_rested -= take
            player.don_active += take
            if take:
                logs.append({"key": "play.log.active_don", "name": player.username, "n": take})
        elif kind == "return_don":
            # DON!! −N (8-3-1-6): return N DON from cost area and/or attached to DON deck.
            # Player chooses which pile / card each DON comes from when multiple sources exist.
            # 「1張以上」→ any_number: return 1 then optionally keep returning.
            any_number = bool(op.get("any_number"))
            don_owner = foe if str(op.get("owner") or "self") == "opponent" else player
            owner_seat = state.other(seat) if don_owner is foe else seat
            optional = bool(op.get("optional", False))
            as_cost = bool(op.get("as_cost"))
            if any_number:
                cap = max(1, min(10, int(op.get("count") or 10)))
                n = 1
            else:
                n = max(1, int(op.get("count") or 1))
                cap = n

            def _field_total() -> int:
                if op.get("active_only"):
                    return int(don_owner.don_active or 0)
                return (
                    int(don_owner.don_active or 0)
                    + int(don_owner.don_rested or 0)
                    + int(don_owner.leader_don or 0)
                    + sum(int(c.don_attached or 0) for c in don_owner.characters)
                )

            def _options() -> tuple[list[str], dict[str, str]]:
                opts: list[str] = []
                labels: dict[str, str] = {}
                if int(don_owner.don_active or 0) > 0:
                    opts.append("don:active")
                    labels["don:active"] = f"don_active:{int(don_owner.don_active)}"
                if not op.get("active_only"):
                    if int(don_owner.don_rested or 0) > 0:
                        opts.append("don:rested")
                        labels["don:rested"] = f"don_rested:{int(don_owner.don_rested)}"
                    if int(don_owner.leader_don or 0) > 0:
                        opts.append("don:leader")
                        labels["don:leader"] = f"don_leader:{int(don_owner.leader_don)}"
                    for ch in don_owner.characters:
                        attached = int(ch.don_attached or 0)
                        if attached <= 0:
                            continue
                        tok = f"don:char:{ch.iid}"
                        opts.append(tok)
                        labels[tok] = f"don_char:{attached}:{ch.card_id}"
                return opts, labels

            def _take_one(token: str) -> bool:
                tok = str(token or "").strip().lower()
                if tok == "don:active" and int(don_owner.don_active or 0) > 0:
                    don_owner.don_active -= 1
                elif tok == "don:rested" and int(don_owner.don_rested or 0) > 0:
                    don_owner.don_rested -= 1
                elif tok == "don:leader" and int(don_owner.leader_don or 0) > 0:
                    don_owner.leader_don -= 1
                elif tok.startswith("don:char:"):
                    iid = tok.split(":", 2)[-1]
                    ch = next((c for c in don_owner.characters if c.iid == iid), None)
                    if not ch or int(ch.don_attached or 0) <= 0:
                        return False
                    ch.don_attached -= 1
                else:
                    return False
                if int(don_owner.don_given or 0) > 0:
                    don_owner.don_given -= 1
                return True

            if not op.get("_continue_return_don"):
                setattr(player, "_last_return_don_count", 0)
            already = int(getattr(player, "_last_return_don_count", 0) or 0)
            if any_number and already >= cap:
                continue

            available = _field_total()
            need = 1 if any_number else n
            if available < need:
                if as_cost and (not any_number or already <= 0):
                    return logs
                continue

            chosen = str(op.get("target_iid") or "").strip()
            opts, labels = _options()
            # Optional 「可將…放回」 / any_number: prompt so player can pay or stop.
            # Fixed multi-return after first payment continues without re-asking skip.
            force_prompt = (
                bool(any_number) or (optional and not op.get("_continue_return_don"))
            ) and not chosen
            if not chosen:
                if force_prompt and opts and not state.pending_choice:
                    rem = dict(op)
                    rem.pop("target_iid", None)
                    state.pending_choice = PendingChoice(
                        seat=owner_seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind="return_don",
                        options=opts,
                        option_labels=labels,
                        remaining_ops=[rem, *queue],
                        optional=True,
                        summary=str(
                            op.get("summary")
                            or (
                                "Return DON!! to DON deck (1 or more)"
                                if any_number
                                else f"Return {n} DON!! to DON deck"
                            )
                        ),
                        purpose="return_don",
                        controller_seat=seat,
                        mark_once=bool(op.get("mark_once")),
                        mark_once_source_iid=str(op.get("mark_once_source_iid") or op.get("source_iid") or ""),
                    )
                    logs.append({"key": "play.log.choice_offer", "name": don_owner.username})
                    return logs
                # Unique source: auto-drain from that pile (no choice needed).
                if len(opts) == 1 and not optional and not any_number:
                    chosen = opts[0]
                elif len(opts) > 1 and not state.pending_choice:
                    rem = dict(op)
                    rem.pop("target_iid", None)
                    state.pending_choice = PendingChoice(
                        seat=owner_seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind="return_don",
                        options=opts,
                        option_labels=labels,
                        remaining_ops=[rem, *queue],
                        optional=bool(optional),
                        summary=str(op.get("summary") or f"Return {n} DON!! to DON deck"),
                        purpose="return_don",
                        controller_seat=seat,
                        mark_once=bool(op.get("mark_once")),
                        mark_once_source_iid=str(op.get("mark_once_source_iid") or op.get("source_iid") or ""),
                    )
                    logs.append({"key": "play.log.choice_offer", "name": don_owner.username})
                    return logs
                elif not opts:
                    if as_cost and already <= 0:
                        return logs
                    continue
                else:
                    chosen = opts[0]

            if not _take_one(chosen):
                if as_cost and already <= 0:
                    return logs
                continue
            logs.append({"key": "play.log.return_don", "name": don_owner.username, "n": 1})
            setattr(player, "_last_return_don_count", already + 1)
            try:
                from battle.engine import _fire_don_returned

                _fire_don_returned(state, owner_seat, 1, catalog)
            except Exception:
                pass
            if any_number:
                left_cap = cap - int(getattr(player, "_last_return_don_count", 0) or 0)
                if left_cap > 0 and _field_total() > 0:
                    cont = dict(op)
                    cont["count"] = left_cap
                    cont["optional"] = True
                    cont["_continue_return_don"] = True
                    cont.pop("target_iid", None)
                    queue.insert(0, cont)
            else:
                left = n - 1
                if left > 0:
                    cont = dict(op)
                    cont["count"] = left
                    cont["optional"] = False
                    cont["_continue_return_don"] = True
                    cont.pop("target_iid", None)
                    queue.insert(0, cont)
        elif kind == "win_game":
            from battle.rules.checkpoints import set_loser

            # Controller wins ⇒ opponent loses.
            set_loser(state, state.other(seat), "play.log.effect_applied", summary="win_game")
            logs.append({"key": "play.log.effect_applied", "summary": "win_game"})
            return logs
        elif kind == "arm_untap_on_char_battle":
            player.untap_on_char_battle = True
            logs.append({"key": "play.log.effect_applied", "summary": "arm_untap_on_char_battle"})
        elif kind == "arm_draw_on_event":
            rule = {
                "cost_gte": max(0, min(10, int(op.get("cost_gte") or 0))),
                "count": max(1, min(5, int(op.get("count") or 1))),
                "source_iid": str(op.get("source_iid") or ""),
            }
            player.draw_on_event_rules.append(rule)
            logs.append(
                {
                    "key": "play.log.effect_applied",
                    "summary": f"arm_draw_on_event:cost>={rule['cost_gte']}",
                }
            )
        elif kind == "cannot_attack_char_base_cost_lte":
            n = max(0, min(10, int(op.get("count") or 0)))
            player.cannot_attack_char_base_cost_lte = n
            logs.append({"key": "play.log.effect_applied", "summary": f"cannot_attack_char_base_cost_lte:{n}"})
        elif kind == "rest_opponent_char_or_don":
            # Rest up to N total among opponent Characters (active) and/or DON!! (active).
            remaining = max(1, min(5, int(op.get("count") or 1)))
            token = str(op.get("target_iid") or "")
            optional = bool(op.get("optional", True))

            def _options() -> list[str]:
                opts = [
                    c.iid
                    for c in foe.characters
                    if not c.rested
                    and c.iid not in foe.deny_rest_iids
                    and c.iid not in foe.deny_rest_until_opp_end_iids
                ]
                if int(foe.don_active or 0) > 0:
                    opts.append("don")
                return opts

            if not token:
                options = _options()
                if not options:
                    continue
                if len(options) > 1 or (optional and remaining >= 1):
                    if not state.pending_choice:
                        state.pending_choice = PendingChoice(
                            seat=seat,
                            card_id=str(op.get("card_id") or ""),
                            source_iid=str(op.get("source_iid") or ""),
                            target_kind="opponent_character_or_don",
                            options=options,
                            remaining_ops=[dict(op), *queue],
                            optional=optional,
                            summary=str(op.get("summary") or "Rest opponent Character or DON!!"),
                purpose=purpose_from_op(op),
            )
                        logs.append({"key": "play.log.choice_offer", "name": player.username})
                        return logs
                    continue
                token = options[0]
            applied = False
            if token == "don":
                if foe.don_active > 0:
                    foe.don_active -= 1
                    foe.don_rested += 1
                    applied = True
                    logs.append({"key": "play.log.rest_don", "name": foe.username, "n": 1})
            else:
                inst = next((c for c in foe.characters if c.iid == token), None)
                if inst and not inst.rested:
                    inst.rested = True
                    applied = True
                    logs.append({"key": "play.log.rests", "name": foe.username, "id": inst.card_id})
            if applied:
                remaining -= 1
            if remaining > 0 and _options():
                cont = dict(op)
                cont["count"] = remaining
                cont.pop("target_iid", None)
                queue.insert(0, cont)
        elif kind == "rest_opponent_character":
            # Prefer interactive choice when multiple actives exist; include Leader when requested.
            include_leader = bool(op.get("include_leader"))
            include_don = bool(op.get("include_don"))
            include_stage = bool(op.get("include_stage"))
            leader_only = bool(op.get("leader_only")) or str(op.get("target_kind") or "").strip().lower() in {
                "opponent_leader",
                "leader",
            }
            if leader_only:
                if not foe.leader_rested:
                    foe.leader_rested = True
                    logs.append({"key": "play.log.rests_opponent", "name": player.username})
                continue
            if op.get("all"):
                for pick in list(foe.characters):
                    if pick.rested:
                        continue
                    if pick.iid in foe.deny_rest_iids or pick.iid in foe.deny_rest_until_opp_end_iids:
                        continue
                    pick.rested = True
                    logs.append({"key": "play.log.rests_opponent", "name": player.username, "id": pick.card_id})
                    try:
                        from battle.engine import _fire_self_rested

                        _fire_self_rested(state, state.other(seat), pick.iid, catalog)
                    except Exception:
                        pass
                continue
            # 「對手的卡片」= Leader / Character / Stage / DON!! — use rest_character path.
            if include_don or include_stage or include_leader:
                cont = {
                    "op": "rest_character",
                    "target_kind": "opponent_character",
                    "optional": bool(op.get("optional", True)),
                    "count": max(1, int(op.get("count") or 1)),
                    "include_leader": True if (include_leader or include_don or include_stage) else False,
                    "include_don": include_don,
                    "include_stage": include_stage,
                    "card_id": str(op.get("card_id") or ""),
                    "source_iid": str(op.get("source_iid") or ""),
                }
                if op.get("also_skip_untap"):
                    cont["also_skip_untap"] = True
                if op.get("require_blocker"):
                    cont["require_blocker"] = True
                for key in ("cost_lte", "cost_eq", "power_lte", "base_power_lte", "trait_contains", "name_contains"):
                    if op.get(key) is not None:
                        cont[key] = op[key]
                queue.insert(0, cont)
                continue
            filters = {}
            for key in (
                "cost_lte",
                "cost_eq",
                "base_cost_lte",
                "power_lte",
                "base_power_lte",
                "trait_contains",
                "name_contains",
            ):
                if op.get(key) is not None:
                    filters[key] = op[key]
            active = [
                c
                for c in foe.characters
                if not c.rested and c.iid not in foe.deny_rest_iids and c.iid not in foe.deny_rest_until_opp_end_iids
            ]
            if op.get("require_blocker"):
                active = [
                    c
                    for c in active
                    if has_blocker(
                        catalog(c.card_id) or {},
                        c,
                        state=state,
                        owner_seat=state.other(seat),
                        catalog=catalog,
                    )
                ]
            if op.get("don_attached_gte") is not None:
                need = int(op.get("don_attached_gte") or 0)
                active = [c for c in active if int(c.don_attached or 0) >= need]
            if op.get("cost_lte_opp_life"):
                life_n = len(foe.life)
                active = [
                    c
                    for c in active
                    if _printed_cost(catalog(c.card_id) or {})
                    <= life_n
                ]
            if op.get("cost_lte_total_life"):
                from battle.engine import effective_character_cost

                life_n = len(player.life) + len(foe.life)
                filtered = []
                for c in active:
                    try:
                        cost = effective_character_cost(state, state.other(seat), c, catalog)
                    except Exception:
                        cost = _printed_cost(catalog(c.card_id) or {})
                    if cost <= life_n:
                        filtered.append(c)
                active = filtered
            if filters:
                allowed = set(_choice_options(state, seat, "opponent_character_active", catalog, filters))
                active = [c for c in active if c.iid in allowed]
            options = ([f"leader"] if include_leader and not foe.leader_rested else []) + [c.iid for c in active]
            if len(options) > 1 and not state.pending_choice:
                cont = {"op": "rest_character", "target_kind": "opponent_character_active", "include_leader": include_leader}
                for key in (
                    "cost_lte",
                    "cost_eq",
                    "base_cost_lte",
                    "power_lte",
                    "base_power_lte",
                    "trait_contains",
                    "name_contains",
                ):
                    if op.get(key) is not None:
                        cont[key] = op[key]
                if op.get("cost_lte_opp_life"):
                    cont["cost_lte_opp_life"] = True
                if op.get("cost_lte_total_life"):
                    cont["cost_lte_total_life"] = True
                if op.get("require_blocker"):
                    cont["require_blocker"] = True
                if op.get("also_skip_untap"):
                    cont["also_skip_untap"] = True
                state.pending_choice = PendingChoice(
                    seat=seat,
                    card_id=str(op.get("card_id") or ""),
                    source_iid=str(op.get("source_iid") or ""),
                    target_kind="opponent_character_active",
                    options=options,
                    remaining_ops=[cont, *queue],
                    optional=bool(op.get("optional", True)),
                    summary=str(op.get("summary") or "Choose a character to rest"),
                purpose=purpose_from_op(op),
            )
                logs.append({"key": "play.log.choice_offer", "name": player.username})
                return logs
            if options:
                tgt = options[0]
                if tgt == "leader":
                    foe.leader_rested = True
                    logs.append({"key": "play.log.rests_opponent", "name": player.username})
                else:
                    pick = next((c for c in foe.characters if c.iid == tgt), None)
                    if pick:
                        src_iid = str(op.get("source_iid") or "")
                        by_opp_char = bool(
                            src_iid
                            and src_iid != "leader"
                            and any(c.iid == src_iid for c in player.characters)
                        )
                        if by_opp_char:
                            try:
                                from battle.leave_replace import try_replace_rest

                                if try_replace_rest(
                                    state,
                                    state.other(seat),
                                    pick,
                                    by_opponent_character_effect=True,
                                    catalog=catalog,
                                ):
                                    if _halt_for_replace("rest"):
                                        return logs
                                    logs.append(
                                        {
                                            "key": "play.log.effect_applied",
                                            "summary": "replace_rest",
                                            "id": pick.card_id,
                                        }
                                    )
                                    continue
                            except Exception:
                                pass
                        pick.rested = True
                        logs.append({"key": "play.log.rests_opponent", "name": player.username})
                        try:
                            from battle.engine import _fire_self_rested

                            _fire_self_rested(state, state.other(seat), pick.iid, catalog)
                        except Exception:
                            pass
                        if op.get("also_skip_untap"):
                            if pick.iid not in foe.skip_untap_iids:
                                foe.skip_untap_iids.append(pick.iid)
                                logs.append(
                                    {"key": "play.log.effect_applied", "summary": "skip_untap"}
                                )
                        if _pause_if_nested_prompt():
                            return logs
        elif kind == "rest_character":
            target = str(op.get("target_iid") or "")
            tk = str(op.get("target_kind") or "").strip().lower()
            source = str(op.get("source_iid") or "")
            if op.get("all") and not target and "opponent" in tk:
                for pick in list(foe.characters):
                    if pick.rested:
                        continue
                    if pick.iid in foe.deny_rest_iids or pick.iid in foe.deny_rest_until_opp_end_iids:
                        continue
                    pick.rested = True
                    logs.append({"key": "play.log.rests_opponent", "name": player.username, "id": pick.card_id})
                    try:
                        from battle.engine import _fire_self_rested

                        _fire_self_rested(state, state.other(seat), pick.iid, catalog)
                    except Exception:
                        pass
                continue
            # Rest this Character/Stage (cost for Stage 【对方攻击时】 etc.)
            if not target and tk in {"self", "source", "own_stage"}:
                hit = next((c for c in player.characters if c.iid == source), None) if source else None
                if hit:
                    if hit.rested and op.get("as_cost"):
                        return logs
                    was_active = not hit.rested
                    hit.rested = True
                    logs.append({"key": "play.log.rests_self", "name": player.username, "id": hit.card_id})
                    if was_active:
                        try:
                            from battle.engine import _fire_self_rested

                            _fire_self_rested(state, seat, hit.iid, catalog)
                        except Exception:
                            pass
                        if _pause_if_nested_prompt():
                            return logs
                    continue
                stage = next((s for s in player.stages if s.iid == source), None) if source else None
                if stage is None and tk == "own_stage" and len(player.stages) == 1:
                    stage = player.stages[0]
                if stage:
                    if stage.rested and op.get("as_cost"):
                        return logs
                    stage.rested = True
                    logs.append({"key": "play.log.rests_self", "name": player.username, "id": stage.card_id})
                    continue
                # Never fall through to opponent targeting for self/stage costs.
                if op.get("as_cost") or op.get("optional"):
                    return logs
                continue
            if not target:
                # Guard: unknown/self kinds must not default to opponent board.
                if tk in {"self", "source", "own_stage", ""}:
                    if op.get("as_cost") or op.get("optional"):
                        return logs
                    continue
                filters: dict[str, Any] = {}
                for key in (
                    "name_contains",
                    "exclude_name",
                    "trait_contains",
                    "cost_lte",
                    "cost_eq",
                    "cost_gte",
                    "power_lte",
                    "base_power_lte",
                    "include_leader",
                    "include_don",
                    "include_stage",
                    "active_only",
                ):
                    if op.get(key) is not None:
                        filters[key] = op[key]
                # Colon-cost rests must target an active card.
                if op.get("as_cost") and "active_only" not in filters:
                    filters["active_only"] = True
                # 「自己的卡片」with no type = Leader / Character / Stage / DON!!.
                if op.get("include_leader"):
                    filters["include_leader"] = True
                if op.get("include_don"):
                    filters["include_don"] = True
                if op.get("include_stage"):
                    filters["include_stage"] = True
                if op.get("require_blocker"):
                    filters["require_blocker"] = True
                options = _choice_options(
                    state,
                    seat,
                    str(op.get("target_kind") or "opponent_character_active"),
                    catalog,
                    filters or None,
                )
                options = [
                    iid
                    for iid in options
                    if iid not in foe.deny_rest_iids
                    and iid not in foe.deny_rest_until_opp_end_iids
                    and iid not in player.deny_rest_iids
                    and iid not in player.deny_rest_until_opp_end_iids
                ]
                # Drop already-rested own Leader when required active.
                if filters.get("active_only") and "leader" in options and player.leader_rested:
                    options = [o for o in options if o != "leader"]
                if not options:
                    if op.get("as_cost"):
                        return logs
                    continue
                # Always ask for 「自己的卡片」rest costs (Leader/Stage/DON!! eligible) —
                # even when only one legal target, so the player sees the payment.
                force_pick = bool(
                    op.get("as_cost")
                    and (
                        op.get("include_leader")
                        or op.get("include_don")
                        or op.get("include_stage")
                    )
                )
                if len(options) == 1 and not force_pick:
                    target = options[0]
                elif not state.pending_choice:
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind=str(op.get("target_kind") or "opponent_character_active"),
                        options=options,
                        remaining_ops=[dict(op), *queue],
                        optional=bool(op.get("optional", True)),
                        summary=str(op.get("summary") or "Choose a character to rest"),
                purpose=purpose_from_op(op),
            )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                else:
                    continue
            if (
                target in foe.deny_rest_iids
                or target in foe.deny_rest_until_opp_end_iids
                or target in player.deny_rest_iids
                or target in player.deny_rest_until_opp_end_iids
            ):
                continue
            def _queue_remaining_own_card_rests() -> None:
                """「可將N張自己的卡片置為休息」— after one rest, keep paying count−1."""
                try:
                    need = max(1, int(op.get("count") or 1))
                except (TypeError, ValueError):
                    need = 1
                if need <= 1:
                    return
                cont = {k: v for k, v in op.items() if k != "target_iid"}
                cont["count"] = need - 1
                # Once the optional package starts, remaining rests are required.
                if op.get("as_cost"):
                    cont["optional"] = False
                queue.insert(0, cont)

            if target == "don":
                opp_side = "opponent" in str(op.get("target_kind") or "")
                don_owner = foe if opp_side else player
                if int(don_owner.don_active or 0) <= 0:
                    if op.get("as_cost"):
                        return logs
                    continue
                don_owner.don_active -= 1
                don_owner.don_rested += 1
                logs.append({"key": "play.log.rest_don", "name": don_owner.username, "n": 1})
                _queue_remaining_own_card_rests()
                continue
            if target == "leader" or target.startswith("leader"):
                # Rest opponent or own leader depending on target_kind.
                own_side = "own" in str(op.get("target_kind") or "") or "self" in str(op.get("target_kind") or "")
                opp_side = "opponent" in str(op.get("target_kind") or "")
                if opp_side and not own_side:
                    if foe.leader_rested and op.get("as_cost"):
                        return logs
                    foe.leader_rested = True
                    logs.append({"key": "play.log.rests_opponent", "name": player.username})
                else:
                    if player.leader_rested and op.get("as_cost"):
                        return logs
                    player.leader_rested = True
                    logs.append({"key": "play.log.rests_self", "name": player.username, "id": player.leader_card_id})
                _queue_remaining_own_card_rests()
                continue
            else:
                # Own stage by iid (from target_iid)
                own_stage = next((s for s in player.stages if s.iid == target), None)
                if own_stage:
                    if own_stage.rested and op.get("as_cost"):
                        return logs
                    own_stage.rested = True
                    logs.append({"key": "play.log.rests_self", "name": player.username, "id": own_stage.card_id})
                    _queue_remaining_own_card_rests()
                    continue
                # Opponent stage by iid
                foe_stage = next((s for s in foe.stages if s.iid == target), None)
                if foe_stage:
                    if foe_stage.rested and op.get("as_cost"):
                        return logs
                    foe_stage.rested = True
                    logs.append({"key": "play.log.rests_opponent", "name": player.username, "id": foe_stage.card_id})
                    _queue_remaining_own_card_rests()
                    continue
                for owner_seat, owner in ((state.other(seat), foe), (seat, player)):
                    hit = next((c for c in owner.characters if c.iid == target), None)
                    if hit:
                        # Self immunity: cannot be rested by opponent's effects.
                        try:
                            from battle.engine import has_continuous_protection

                            if owner_seat != seat and has_continuous_protection(
                                state, owner_seat, hit.iid, "cannot_be_rested", catalog
                            ):
                                logs.append(
                                    {
                                        "key": "play.log.effect_unsupported",
                                        "id": hit.card_id,
                                        "summary": "cannot_be_rested",
                                    }
                                )
                                break
                        except Exception:
                            if getattr(hit, "cannot_be_rested", False) and owner_seat != seat:
                                logs.append(
                                    {
                                        "key": "play.log.effect_unsupported",
                                        "id": hit.card_id,
                                        "summary": "cannot_be_rested",
                                    }
                                )
                                break
                        if hit.rested and op.get("as_cost"):
                            return logs
                        was_active = not hit.rested
                        if was_active and owner_seat != seat:
                            src_iid = str(op.get("source_iid") or "")
                            by_opp_char = bool(
                                src_iid
                                and src_iid != "leader"
                                and any(c.iid == src_iid for c in player.characters)
                            )
                            if by_opp_char:
                                try:
                                    from battle.leave_replace import try_replace_rest

                                    if try_replace_rest(
                                        state,
                                        owner_seat,
                                        hit,
                                        by_opponent_character_effect=True,
                                        catalog=catalog,
                                    ):
                                        if _halt_for_replace("rest"):
                                            return logs
                                        logs.append(
                                            {
                                                "key": "play.log.effect_applied",
                                                "summary": "replace_rest",
                                                "id": hit.card_id,
                                            }
                                        )
                                        break
                                except Exception:
                                    pass
                        hit.rested = True
                        logs.append({"key": "play.log.rests_opponent", "name": player.username})
                        if was_active:
                            try:
                                from battle.engine import _fire_self_rested

                                _fire_self_rested(state, owner_seat, hit.iid, catalog)
                            except Exception:
                                pass
                            if _pause_if_nested_prompt():
                                return logs
                        if op.get("also_skip_untap") and owner_seat != seat:
                            if hit.iid not in owner.skip_untap_iids:
                                owner.skip_untap_iids.append(hit.iid)
                                logs.append(
                                    {"key": "play.log.effect_applied", "summary": "skip_untap"}
                                )
                        _queue_remaining_own_card_rests()
                        break
        elif kind == "ko":
            # 「若有執行此動作時」after optional trash_hand — only KO if hand trash paid.
            if op.get("if_trash_hand") or op.get("require_trash_hand_gte") is not None:
                need = int(op.get("require_trash_hand_gte") or (1 if op.get("if_trash_hand") else 0))
                if int(getattr(player, "_last_trash_hand_count", 0) or 0) < need:
                    continue
            target = str(op.get("target_iid") or "")
            if op.get("same_target_as_prior") and not target:
                prior = str(getattr(player, "_last_negate_target_iid", "") or "")
                if prior and prior != "leader" and not str(prior).startswith("leader-"):
                    target = prior
            filters = {
                k: op[k]
                for k in ("cost_lte", "cost_eq", "base_cost_lte", "power_lte", "base_power_lte", "trait_contains")
                if op.get(k) is not None
            }
            tk = str(op.get("target_kind") or "opponent_character")
            # Mass KO: all Characters (optionally both sides) other than self.
            if op.get("all") and not target:
                tk_l = tk.strip().lower()
                # Explicit opponent / own pools first — never treat "opponent_*" as own.
                if tk_l.startswith("opponent"):
                    pool = list(foe.characters)
                elif tk_l.startswith("own"):
                    pool = list(player.characters)
                elif tk_l in {"any_character", "all", "all_characters"}:
                    pool = list(player.characters) + list(foe.characters)
                elif op.get("exclude_self"):
                    # 「除了這張以外」mass KO without an ownership word → both fields.
                    pool = list(player.characters) + list(foe.characters)
                else:
                    # Default KO side is opponent (paper 對手).
                    pool = list(foe.characters)
                src = str(op.get("source_iid") or "")
                victims = [c for c in pool if not (op.get("exclude_self") and src and c.iid == src)]
                if "rested" in tk_l or op.get("rested_only"):
                    victims = [c for c in victims if c.rested]
                if op.get("cost_lte") is not None or op.get("cost_eq") is not None or op.get("base_cost_lte") is not None:
                    from battle.engine import effective_character_cost

                    filtered = []
                    for c in victims:
                        owner_seat = seat if any(x.iid == c.iid for x in player.characters) else state.other(seat)
                        info = catalog(c.card_id)
                        try:
                            cost = effective_character_cost(state, owner_seat, c, catalog)
                        except Exception:
                            cost = _printed_cost(info)
                        printed = _printed_cost(info)
                        if op.get("cost_lte") is not None and cost > int(op["cost_lte"]):
                            continue
                        if op.get("cost_eq") is not None and cost != int(op["cost_eq"]):
                            continue
                        if op.get("base_cost_lte") is not None and printed > int(op["base_cost_lte"]):
                            continue
                        filtered.append(c)
                    victims = filtered
                if (
                    op.get("power_lte") is not None
                    or op.get("power_gte") is not None
                    or op.get("base_power_lte") is not None
                ):
                    from battle.engine import inst_power

                    filtered = []
                    for c in victims:
                        owner_seat = seat if any(x.iid == c.iid for x in player.characters) else state.other(seat)
                        info = catalog(c.card_id)
                        if op.get("base_power_lte") is not None:
                            try:
                                raw = info.get("power") if info else 0
                                base = int(str(raw).split()[0].replace(",", "") or 0)
                            except Exception:
                                base = 0
                            if c.base_power_override is not None:
                                base = int(c.base_power_override)
                            if base > int(op["base_power_lte"]):
                                continue
                        if op.get("power_lte") is not None or op.get("power_gte") is not None:
                            try:
                                pow_v = int(inst_power(state, owner_seat, c.iid, catalog))
                            except Exception:
                                pow_v = 0
                            if op.get("power_lte") is not None and pow_v > int(op["power_lte"]):
                                continue
                            if op.get("power_gte") is not None and pow_v < int(op["power_gte"]):
                                continue
                        filtered.append(c)
                    victims = filtered
                on_ko_ops: list[dict[str, Any]] = []
                for hit in list(victims):
                    owner = player if any(c.iid == hit.iid for c in player.characters) else foe
                    owner_seat = owner.seat
                    by_opp = owner_seat != seat
                    try:
                        from battle.engine import has_continuous_protection

                        if has_continuous_protection(state, owner_seat, hit.iid, "cannot_be_ko", catalog) and by_opp:
                            continue
                        if has_continuous_protection(state, owner_seat, hit.iid, "cannot_be_removed", catalog) and by_opp:
                            continue
                    except Exception:
                        if getattr(hit, "cannot_be_ko", False) and by_opp:
                            continue
                        if getattr(hit, "cannot_be_removed", False) and by_opp:
                            continue
                    from battle.leave_replace import try_replace_leave

                    if try_replace_leave(
                        state, owner_seat, hit, by_opponent=by_opp, catalog=catalog
                    ):
                        extra = [
                            {"op": "ko", "target_iid": rest.iid, "optional": False}
                            for rest in victims
                            if rest.iid != hit.iid
                        ]
                        if _halt_for_replace("ko", extra):
                            return logs
                        logs.append({"key": "play.log.effect_applied", "summary": "replace_leave"})
                        continue
                    if hit.don_attached:
                        owner.don_rested += hit.don_attached
                        hit.don_attached = 0
                    owner.characters = [c for c in owner.characters if c.iid != hit.iid]
                    owner.trash.append(hit.card_id)
                    logs.append({"key": "play.log.ko", "id": hit.card_id})
                    try:
                        from battle.engine import fire_own_trait_leave_or_ko

                        fire_own_trait_leave_or_ko(
                            state,
                            owner_seat,
                            hit.card_id,
                            catalog,
                            by_opponent_effect=by_opp,
                            by_ko=True,
                        )
                    except Exception:
                        pass
                    try:
                        from battle.engine import fire_on_opp_ko

                        fire_on_opp_ko(state, owner_seat, catalog)
                    except Exception:
                        pass
                    on_ko_ops.extend(_victim_on_ko_ops(state, owner_seat, hit.card_id, hit.iid, catalog))
                if on_ko_ops:
                    queue[0:0] = on_ko_ops
                continue
            if not target:
                options = _choice_options(state, seat, tk, catalog, filters)
                if op.get("exclude_self"):
                    src = str(op.get("source_iid") or "")
                    if src:
                        options = [x for x in options if x != src]
                # Total-power KO (OP09-018 / OP05-007): each pick must fit remaining budget.
                total_budget = op.get("total_power_lte")
                total_cost_budget = op.get("total_cost_lte")
                if total_budget is not None:
                    from battle.engine import inst_power

                    budget = int(total_budget)
                    filtered_opts: list[str] = []
                    for iid in options:
                        owner_seat = state.other(seat) if any(
                            c.iid == iid for c in foe.characters
                        ) else seat
                        if "opponent" in tk:
                            owner_seat = state.other(seat)
                        try:
                            pow_v = int(inst_power(state, owner_seat, iid, catalog))
                        except Exception:
                            continue
                        if pow_v <= budget:
                            filtered_opts.append(iid)
                    options = filtered_opts
                elif total_cost_budget is not None:
                    from battle.engine import effective_character_cost

                    budget = int(total_cost_budget)
                    filtered_opts = []
                    for iid in options:
                        owner_seat = state.other(seat) if "opponent" in tk else seat
                        hit = next((c for c in state.player(owner_seat).characters if c.iid == iid), None)
                        if not hit:
                            continue
                        try:
                            cost_v = int(effective_character_cost(state, owner_seat, hit, catalog))
                        except Exception:
                            cost_v = _printed_cost(catalog(hit.card_id))
                        if cost_v <= budget:
                            filtered_opts.append(iid)
                    options = filtered_opts
                if not options:
                    if op.get("as_cost"):
                        return logs
                    continue
                # 「最多1張」optional KO: always ask, even if only one legal target.
                if len(options) == 1 and not op.get("optional") and not op.get("always_choose"):
                    target = options[0]
                elif not state.pending_choice:
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind=tk,
                        options=options,
                        remaining_ops=[dict(op), *queue],
                        optional=bool(op.get("optional", True)),
                        summary=str(op.get("summary") or "Choose a card to KO"),
                        purpose="ko",
                    )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                else:
                    continue
            # Stage KO (own / opponent / either)
            if tk in {"opponent_stage", "own_stage", "any_stage"} or (
                target
                and (
                    any(s.iid == target for s in foe.stages)
                    or any(s.iid == target for s in player.stages)
                )
            ):
                pools: list[tuple[Any, list]] = []
                if tk == "own_stage":
                    pools = [(player, player.stages)]
                elif tk == "opponent_stage":
                    pools = [(foe, foe.stages)]
                else:
                    pools = [(player, player.stages), (foe, foe.stages)]
                hit = None
                hit_owner = None
                for owner, stages in pools:
                    hit = next((s for s in stages if s.iid == target), None)
                    if hit:
                        hit_owner = owner
                        break
                if hit and hit_owner:
                    hit_owner.stages = [s for s in hit_owner.stages if s.iid != hit.iid]
                    hit_owner.trash.append(hit.card_id)
                    logs.append({"key": "play.log.ko", "id": hit.card_id})
                elif op.get("as_cost"):
                    return logs
                continue
            for owner in (foe, player):
                hit = next((c for c in owner.characters if c.iid == target), None)
                if not hit:
                    continue
                # 「之後，若該張…費用N以下時，即KO」— re-check filters on locked prior target.
                if filters:
                    from battle.engine import effective_character_cost, printed_cost, printed_power, inst_power

                    try:
                        pc = int(effective_character_cost(state, owner.seat, hit, catalog))
                    except Exception:
                        pc = int(printed_cost(catalog(hit.card_id)))
                    if filters.get("cost_lte") is not None and pc > int(filters["cost_lte"]):
                        break
                    if filters.get("cost_eq") is not None and pc != int(filters["cost_eq"]):
                        break
                    if filters.get("base_cost_lte") is not None:
                        base_c = int(printed_cost(catalog(hit.card_id)))
                        if base_c > int(filters["base_cost_lte"]):
                            break
                    if filters.get("power_lte") is not None:
                        try:
                            pow_v = int(inst_power(state, owner.seat, hit.iid, catalog))
                        except Exception:
                            pow_v = 0
                        if pow_v > int(filters["power_lte"]):
                            break
                    if filters.get("base_power_lte") is not None:
                        if int(printed_power(catalog(hit.card_id))) > int(filters["base_power_lte"]):
                            break
                owner_seat = owner.seat
                by_opp = owner_seat != seat
                try:
                    from battle.engine import has_continuous_protection

                    protected = by_opp and (
                        has_continuous_protection(state, owner_seat, hit.iid, "cannot_be_ko", catalog)
                        or has_continuous_protection(state, owner_seat, hit.iid, "cannot_be_removed", catalog)
                    )
                except Exception:
                    protected = by_opp and (
                        bool(getattr(hit, "cannot_be_ko", False)) or bool(getattr(hit, "cannot_be_removed", False))
                    )
                if protected:
                    logs.append({"key": "play.log.effect_unsupported", "id": "cannot_be_ko"})
                    if op.get("as_cost"):
                        return logs
                    break
                from battle.leave_replace import try_replace_leave

                if try_replace_leave(
                    state, owner_seat, hit, by_opponent=by_opp, catalog=catalog
                ):
                    extra = []
                    rem_count = max(0, int(op.get("count") or 1) - 1)
                    if rem_count > 0 and op.get("total_power_lte") is not None:
                        rem_budget = int(op["total_power_lte"])
                        cont = dict(op)
                        cont["count"] = rem_count
                        cont["total_power_lte"] = rem_budget
                        cont.pop("target_iid", None)
                        extra.append(cont)
                    elif rem_count > 0 and op.get("total_cost_lte") is not None:
                        rem_budget = int(op["total_cost_lte"])
                        cont = dict(op)
                        cont["count"] = rem_count
                        cont["total_cost_lte"] = rem_budget
                        cont.pop("target_iid", None)
                        extra.append(cont)
                    elif rem_count > 0:
                        cont = dict(op)
                        cont["count"] = rem_count
                        cont.pop("target_iid", None)
                        extra.append(cont)
                    if _halt_for_replace("ko", extra):
                        return logs
                    logs.append({"key": "play.log.effect_applied", "summary": "replace_leave"})
                    break
                hit_power = 0
                hit_cost = 0
                if op.get("total_power_lte") is not None:
                    try:
                        from battle.engine import inst_power

                        hit_power = int(inst_power(state, owner_seat, hit.iid, catalog))
                    except Exception:
                        hit_power = 0
                if op.get("total_cost_lte") is not None:
                    try:
                        from battle.engine import effective_character_cost

                        hit_cost = int(effective_character_cost(state, owner_seat, hit, catalog))
                    except Exception:
                        hit_cost = _printed_cost(catalog(hit.card_id))
                if hit.don_attached:
                    owner.don_rested += hit.don_attached
                    hit.don_attached = 0
                owner.characters = [c for c in owner.characters if c.iid != hit.iid]
                owner.trash.append(hit.card_id)
                logs.append({"key": "play.log.ko", "id": hit.card_id})
                try:
                    from battle.engine import fire_own_trait_leave_or_ko

                    fire_own_trait_leave_or_ko(
                        state,
                        owner_seat,
                        hit.card_id,
                        catalog,
                        by_opponent_effect=by_opp,
                        by_ko=True,
                    )
                except Exception:
                    pass
                try:
                    from battle.engine import fire_on_opp_ko

                    fire_on_opp_ko(state, owner_seat, catalog)
                except Exception:
                    pass
                victim_ops = _victim_on_ko_ops(state, owner_seat, hit.card_id, hit.iid, catalog)
                # Queue another pick while count/budget remain (total-power multi KO).
                rem_count = max(0, int(op.get("count") or 1) - 1)
                if rem_count > 0 and op.get("total_power_lte") is not None:
                    rem_budget = int(op["total_power_lte"]) - hit_power
                    if rem_budget > 0:
                        cont = dict(op)
                        cont["count"] = rem_count
                        cont["total_power_lte"] = rem_budget
                        cont.pop("target_iid", None)
                        cont["optional"] = True
                        queue.insert(0, cont)
                elif rem_count > 0 and op.get("total_cost_lte") is not None:
                    rem_budget = int(op["total_cost_lte"]) - hit_cost
                    if rem_budget > 0:
                        cont = dict(op)
                        cont["count"] = rem_count
                        cont["total_cost_lte"] = rem_budget
                        cont.pop("target_iid", None)
                        cont["optional"] = True
                        queue.insert(0, cont)
                elif rem_count > 0 and op.get("count") is not None and op.get("total_power_lte") is None and op.get("total_cost_lte") is None:
                    cont = dict(op)
                    cont["count"] = rem_count
                    cont.pop("target_iid", None)
                    cont["optional"] = True
                    queue.insert(0, cont)
                if victim_ops:
                    queue[0:0] = victim_ops
                break
            else:
                if op.get("as_cost"):
                    return logs
        elif kind == "reduce_cost":
            amount = int(op.get("amount") or 0)
            remaining = max(1, min(5, int(op.get("count") or 1)))
            target = str(op.get("target_iid") or "")
            tk = str(op.get("target_kind") or "opponent_character")
            filters = {
                k: op[k]
                for k in ("cost_lte", "cost_eq", "cost_gte")
                if op.get(k) is not None
            }
            while remaining > 0:
                pick = target if remaining == int(op.get("count") or 1) and target else ""
                if not pick:
                    options = _choice_options(state, seat, tk, catalog, filters or None)
                    # Already reduced targets still eligible (stacking cost mods is fine)
                    if not options:
                        break
                    # 「最多1張」optional: always ask, even with a single legal target.
                    if len(options) == 1 and not op.get("optional") and not op.get("always_choose"):
                        pick = options[0]
                    elif not state.pending_choice:
                        cont = dict(op)
                        cont["count"] = remaining
                        cont.pop("target_iid", None)
                        state.pending_choice = PendingChoice(
                            seat=seat,
                            card_id=str(op.get("card_id") or ""),
                            source_iid=str(op.get("source_iid") or ""),
                            target_kind=tk,
                            options=options,
                            remaining_ops=[cont, *queue],
                            optional=bool(op.get("optional", True)),
                            summary=str(op.get("summary") or f"Cost {amount} this turn / 費用{amount}"),
                            purpose="reduce_cost",
                        )
                        logs.append({"key": "play.log.choice_offer", "name": player.username})
                        return logs
                    else:
                        break
                applied = False
                for owner in (foe, player):
                    hit = next((c for c in owner.characters if c.iid == pick), None)
                    if hit:
                        hit.cost_mod += amount
                        logs.append(
                            {
                                "key": "play.log.effect_applied",
                                "id": hit.card_id,
                                "summary": f"cost{amount:+d}",
                            }
                        )
                        applied = True
                        break
                if not applied:
                    break
                remaining -= 1
                target = ""
                if remaining > 0 and bool(op.get("optional", True)):
                    # Re-queue remainder so player can skip further targets.
                    cont = dict(op)
                    cont["count"] = remaining
                    cont.pop("target_iid", None)
                    queue.insert(0, cont)
                    break
        elif kind == "buff_all_own":
            amount = int(op.get("amount") or 0)
            trait = str(op.get("trait_contains") or "").strip()
            exclude_self = bool(op.get("exclude_self"))
            source_iid = str(op.get("source_iid") or "")
            if op.get("include_leader", True) and not trait:
                player.leader_power_mod += amount
                logs.append(
                    {
                        "key": "play.log.gains_power",
                        "id": player.leader_card_id,
                        "amount": f"{amount:+d}",
                    }
                )
            for ch in player.characters:
                if exclude_self and source_iid and ch.iid == source_iid:
                    continue
                if trait:
                    from battle.engine import _info_has_trait

                    if not _info_has_trait(catalog(ch.card_id), trait):
                        continue
                ch.power_mod += amount
                logs.append({"key": "play.log.gains_power", "id": ch.card_id, "amount": f"{amount:+d}"})
        elif kind == "trash_deck_top":
            n = max(1, min(10, int(op.get("count") or 1)))
            optional = bool(op.get("optional", False))
            moved = 0
            for _ in range(n):
                if not player.deck:
                    break
                cid = player.deck.pop(0)
                player.trash.append(cid)
                moved += 1
            if moved:
                logs.append({"key": "play.log.trashes", "name": player.username, "n": moved})
            elif optional:
                continue
        elif kind == "ko_lowest_opponent":
            if foe.characters:
                def _pow(c: CardInst) -> int:
                    try:
                        raw = catalog(c.card_id).get("power")
                        return int(str(raw).split()[0].replace(",", "") or 0) + c.power_mod
                    except Exception:
                        return c.power_mod

                candidates = [c for c in foe.characters if not getattr(c, "cannot_be_ko", False)]
                if not candidates:
                    continue
                hit = min(candidates, key=_pow)
                if hit.don_attached:
                    foe.don_rested += hit.don_attached
                    hit.don_attached = 0
                foe.characters = [c for c in foe.characters if c.iid != hit.iid]
                foe.trash.append(hit.card_id)
                logs.append({"key": "play.log.ko", "id": hit.card_id})
        elif kind == "buff_self":
            # Continuous scalers (per distinct names / per trash / …) are live-evaluated in
            # inst_power/_static_power_bonus — never bake them into power_mod.
            if any(
                op.get(k)
                for k in (
                    "per_distinct_own_char_names",
                    "per_rested_don",
                    "per_trash_cards",
                    "per_trash_events",
                    "per_own_chars",
                    "per_returned_chars",
                )
            ):
                continue
            amount = int(op.get("amount") or 0)
            source = str(op.get("source_iid") or "")
            duration = str(op.get("duration") or "").strip().lower()
            inst = next((c for c in player.characters if c.iid == source), None)
            if inst:
                _apply_timed_power_mod(
                    player, amount=amount, duration=duration, controller_seat=seat, on_leader=False, inst=inst
                )
                logs.append({"key": "play.log.gains_power", "id": inst.card_id, "amount": f"{amount:+d}"})
            else:
                _apply_timed_power_mod(
                    player, amount=amount, duration=duration, controller_seat=seat, on_leader=True
                )
        elif kind == "set_base_power_from_opponent_leader":
            source = str(op.get("source_iid") or "")
            need = int(op.get("require_don_attached_gte") or 0)
            inst = next((c for c in player.characters if c.iid == source), None)
            if not inst:
                continue
            if need and int(inst.don_attached or 0) < need:
                continue
            foe_seat = state.other(seat)
            foe_p = state.player(foe_seat)
            try:
                raw = catalog(foe_p.leader_card_id).get("power")
                opp_base = int(str(raw).split()[0].replace(",", "") or 0)
            except Exception:
                opp_base = 0
            # Leader DON only boosts on that player's turn (6-5-5-2).
            opp_don = foe_p.leader_don * 1000 if state.turn_seat == foe_seat else 0
            inst.base_power_override = max(0, opp_base + int(foe_p.leader_power_mod or 0) + opp_don)
            logs.append(
                {
                    "key": "play.log.base_power_set",
                    "id": inst.card_id,
                    "amount": inst.base_power_override,
                }
            )
        elif kind == "set_base_power":
            source = str(op.get("source_iid") or "")
            need = int(op.get("require_don_attached_gte") or 0)
            amount = max(0, int(op.get("amount") or 0))
            tk = str(op.get("target_kind") or "self")
            trait = str(op.get("trait_contains") or "").strip()
            from battle.engine import _info_has_trait

            if tk in {"own_leader_or_character", "own_character_or_leader"}:
                target = str(op.get("target_iid") or "")
                optional = bool(op.get("optional", True))
                if not target:
                    options: list[str] = ["leader"] + [c.iid for c in player.characters]
                    if not options:
                        continue
                    if (optional or len(options) > 1) and not state.pending_choice:
                        state.pending_choice = PendingChoice(
                            seat=seat,
                            card_id=str(op.get("card_id") or ""),
                            source_iid=source,
                            target_kind="own_leader_or_character",
                            options=options,
                            remaining_ops=[dict(op), *queue],
                            optional=optional,
                            summary=str(op.get("summary") or f"Set base power to {amount}"),
                            purpose=purpose_from_op(op),
                        )
                        logs.append({"key": "play.log.choice_offer", "name": player.username})
                        return logs
                    target = options[0]
                if target == "leader" or target == f"leader-{seat}":
                    try:
                        raw = catalog(player.leader_card_id).get("power")
                        printed = int(str(raw).split()[0].replace(",", "") or 0)
                    except Exception:
                        printed = 0
                    _set_leader_base_power(
                        player,
                        amount=amount,
                        printed=printed,
                        duration=str(op.get("duration") or ""),
                        controller_seat=seat,
                    )
                    logs.append({"key": "play.log.base_power_set", "id": player.leader_card_id, "amount": amount})
                else:
                    inst = next((c for c in player.characters if c.iid == target), None)
                    if inst:
                        inst.base_power_override = amount
                        logs.append({"key": "play.log.base_power_set", "id": inst.card_id, "amount": amount})
            elif tk == "leader" or source == "leader":
                if trait and not _info_has_trait(catalog(player.leader_card_id), trait):
                    continue
                try:
                    raw = catalog(player.leader_card_id).get("power")
                    printed = int(str(raw).split()[0].replace(",", "") or 0)
                except Exception:
                    printed = 0
                _set_leader_base_power(
                    player,
                    amount=amount,
                    printed=printed,
                    duration=str(op.get("duration") or ""),
                    controller_seat=seat,
                )
                logs.append({"key": "play.log.base_power_set", "id": player.leader_card_id, "amount": amount})
            elif op.get("all") or tk in {"own_character", "own_characters"}:
                for ch in player.characters:
                    info = catalog(ch.card_id)
                    if trait and not _info_has_trait(info, trait):
                        continue
                    ch.base_power_override = amount
                    logs.append({"key": "play.log.base_power_set", "id": ch.card_id, "amount": amount})
            else:
                inst = next((c for c in player.characters if c.iid == source), None)
                if not inst:
                    continue
                if need and int(inst.don_attached or 0) < need:
                    continue
                if trait and not _info_has_trait(catalog(inst.card_id), trait):
                    continue
                inst.base_power_override = amount
                logs.append({"key": "play.log.base_power_set", "id": inst.card_id, "amount": amount})
        elif kind == "set_base_power_from_character":
            source = str(op.get("source_iid") or "")
            need = int(op.get("require_don_attached_gte") or 0)
            inst = next((c for c in player.characters if c.iid == source), None)
            if not inst:
                continue
            if need and int(inst.don_attached or 0) < need:
                continue
            target = str(op.get("target_iid") or "")
            if not target:
                tk = str(op.get("target_kind") or "opponent_character")
                options = _choice_options(state, seat, tk, catalog, None)
                if not options:
                    continue
                if len(options) == 1 and not op.get("optional"):
                    target = options[0]
                elif not state.pending_choice:
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=source,
                        target_kind=tk,
                        options=options,
                        remaining_ops=[dict(op), *queue],
                        optional=bool(op.get("optional", True)),
                        summary=str(op.get("summary") or "Choose a Character to copy power from"),
                purpose=purpose_from_op(op),
            )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                else:
                    continue
            # Snapshot chosen unit's current power (printed + mod + DON if that owner's turn).
            snap = 0
            for owner in (player, foe):
                if target == "leader" or target == f"leader-{owner.seat}":
                    try:
                        raw = catalog(owner.leader_card_id).get("power")
                        snap = int(str(raw).split()[0].replace(",", "") or 0)
                    except Exception:
                        snap = 0
                    snap += int(owner.leader_power_mod or 0)
                    if state.turn_seat == owner.seat:
                        snap += int(owner.leader_don or 0) * 1000
                    break
                hit = next((c for c in owner.characters if c.iid == target), None)
                if not hit:
                    continue
                try:
                    raw = catalog(hit.card_id).get("power")
                    # Prefer the chosen card's current power; if it has its own base override, use that.
                    printed = int(str(raw).split()[0].replace(",", "") or 0)
                except Exception:
                    printed = 0
                base = printed if hit.base_power_override is None else int(hit.base_power_override)
                snap = base + int(hit.power_mod or 0)
                if state.turn_seat == owner.seat:
                    snap += int(hit.don_attached or 0) * 1000
                break
            inst.base_power_override = max(0, snap)
            logs.append({"key": "play.log.base_power_set", "id": inst.card_id, "amount": inst.base_power_override})
        elif kind == "set_base_power_from_attacker":
            source = str(op.get("source_iid") or "")
            inst = next((c for c in player.characters if c.iid == source), None)
            if not inst or not state.attack:
                continue
            atk_seat = state.attack.attacker_seat
            atk_iid = state.attack.attacker_iid
            atk_p = state.player(atk_seat)
            snap = 0
            if atk_iid == "leader":
                try:
                    raw = catalog(atk_p.leader_card_id).get("power")
                    snap = int(str(raw).split()[0].replace(",", "") or 0)
                except Exception:
                    snap = 0
                snap += int(atk_p.leader_power_mod or 0)
                if state.turn_seat == atk_seat:
                    snap += int(atk_p.leader_don or 0) * 1000
            else:
                hit = next((c for c in atk_p.characters if c.iid == atk_iid), None)
                if hit:
                    try:
                        raw = catalog(hit.card_id).get("power")
                        printed = int(str(raw).split()[0].replace(",", "") or 0)
                    except Exception:
                        printed = 0
                    base = printed if hit.base_power_override is None else int(hit.base_power_override)
                    snap = base + int(hit.power_mod or 0)
                    if state.turn_seat == atk_seat:
                        snap += int(hit.don_attached or 0) * 1000
            inst.base_power_override = max(0, snap)
            logs.append({"key": "play.log.base_power_set", "id": inst.card_id, "amount": inst.base_power_override})
        elif kind == "set_power_equal_opponent_leader":
            source = str(op.get("source_iid") or "")
            need = int(op.get("require_don_attached_gte") or 0)
            inst = next((c for c in player.characters if c.iid == source), None)
            if not inst:
                continue
            if need and int(inst.don_attached or 0) < need:
                continue
            foe_seat = state.other(seat)
            foe_p = state.player(foe_seat)
            try:
                raw = catalog(foe_p.leader_card_id).get("power")
                opp_base = int(str(raw).split()[0].replace(",", "") or 0)
            except Exception:
                opp_base = 0
            opp_don = foe_p.leader_don * 1000 if state.turn_seat == foe_seat else 0
            inst.power_override = max(0, opp_base + int(foe_p.leader_power_mod or 0) + opp_don)
            logs.append({"key": "play.log.base_power_set", "id": inst.card_id, "amount": inst.power_override})
        elif kind == "continuous_base_from_own_leader_printed":
            # Continuous marker — evaluated in inst_power, not here.
            continue
        elif kind == "set_don":
            n = max(0, min(10, int(op.get("count") or 0)))
            room = _don_room(player)
            extra = min(max(0, n - player.don_active), room)
            if extra:
                player.don_given += extra
                player.don_active += extra
                logs.append({"key": "play.log.gains_don", "name": player.username, "n": extra})
        elif kind == "equalize_don_to_opponent":
            from battle.engine import _don_on_field

            own = int(_don_on_field(player))
            opp = int(_don_on_field(foe))
            if own > opp:
                diff = own - opp
                # Prefer returning active DON!!, then rested.
                take_active = min(diff, int(player.don_active or 0))
                player.don_active = int(player.don_active or 0) - take_active
                player.don_given = max(0, int(player.don_given or 0) - take_active)
                rem = diff - take_active
                if rem > 0:
                    take_rest = min(rem, int(player.don_rested or 0))
                    player.don_rested = int(player.don_rested or 0) - take_rest
                    player.don_given = max(0, int(player.don_given or 0) - take_rest)
                logs.append({"key": "play.log.return_don", "name": player.username, "n": diff})
            logs.append({"key": "play.log.effect_applied", "summary": "equalize_don_to_opponent"})
        elif kind == "extra_turn":
            # Semantic + soft engine marker: grant an additional own turn after this one.
            setattr(state, "pending_extra_turn_seat", seat)
            logs.append({"key": "play.log.effect_applied", "summary": "extra_turn"})
        elif kind == "buff":
            amount = int(op.get("amount") or 0)
            target = str(op.get("target_iid") or "")
            optional = bool(op.get("optional", False))
            per_choose = bool(op.get("per_choose"))
            # 「活動狀態的領航卡」as cost — cannot pay if Leader is rested.
            if (
                op.get("as_cost")
                and (
                    op.get("require_leader_active")
                    or str(op.get("target_kind") or "").strip().lower() in {"leader", "own_leader"}
                )
                and bool(getattr(player, "leader_rested", False))
            ):
                return logs
            if op.get("if_life_to_hand") and int(getattr(player, "_last_life_to_hand_count", 0) or 0) <= 0:
                continue
            if op.get("same_target_as_prior") or str(op.get("target_kind") or "").strip().lower() in {
                "prior",
                "prior_buff",
                "same_as_prior",
            }:
                prior = str(getattr(player, "_last_buff_target_iid", "") or "")
                if not prior:
                    continue
                target = prior
            own_field_scale = op.get("per_own_chars") is not None or bool(op.get("per_own_trait"))
            if op.get("per_rested_don") is not None:
                step = max(1, int(op.get("per_rested_don") or 1))
                rested_n = int(getattr(player, "_last_rest_don_count", 0) or 0)
                stacks = rested_n // step
                if stacks <= 0:
                    continue
                amount = amount * stacks
            elif op.get("per_don_attached") is not None:
                step = max(1, int(op.get("per_don_attached") or 1))
                src_inst = next((c for c in player.characters if c.iid == source), None)
                attached = int(src_inst.don_attached or 0) if src_inst else 0
                if source in {"", "leader"} or source == "leader":
                    attached = int(player.leader_don or 0)
                stacks = attached // step
                if stacks <= 0:
                    continue
                amount = amount * stacks
            elif own_field_scale:
                step = max(1, int(op.get("per_own_chars") or 1))
                trait = str(op.get("per_own_trait") or "").strip()
                field_n = _count_own_trait_field(
                    player,
                    catalog,
                    trait,
                    include_leader=bool(op.get("include_leader")),
                    include_stage=bool(op.get("include_stage")),
                )
                stacks = max(0, field_n // step)
                if stacks <= 0:
                    continue
                if per_choose:
                    if op.get("_buff_repeats_left") is None:
                        op = dict(op)
                        op["_buff_repeats_left"] = stacks
                else:
                    amount = amount * stacks
            elif op.get("per_trash_cards") is not None or per_choose:
                step = max(1, int(op.get("per_trash_cards") or 1))
                trashed_n = int(getattr(player, "_last_trash_hand_count", 0) or 0)
                already = int(getattr(player, "_trash_buff_applied", 0) or 0)
                stacks = max(0, trashed_n // step) if trashed_n else int(op.get("_buff_repeats_left") or 0)
                if op.get("_buff_repeats_left") is not None:
                    stacks = max(0, int(op.get("_buff_repeats_left") or 0))
                elif trashed_n <= 0:
                    setattr(player, "_trash_buff_applied", 0)
                    continue
                else:
                    stacks = max(0, (trashed_n // step) - already)
                if stacks <= 0:
                    setattr(player, "_trash_buff_applied", 0)
                    continue
                if per_choose:
                    if op.get("_buff_repeats_left") is None:
                        op = dict(op)
                        op["_buff_repeats_left"] = stacks
                else:
                    amount = amount * stacks
                    # Final batch (or remainder) — clear incremental tracker.
                    setattr(player, "_trash_buff_applied", 0)
            if op.get("all") and not target:
                buff_tk = _infer_buff_target_kind(op)
                filters: dict[str, Any] = {}
                for key in (
                    "cost_lte",
                    "cost_eq",
                    "cost_gte",
                    "power_lte",
                    "power_gte",
                    "base_power_lte",
                    "trait_contains",
                    "name_contains",
                    "exclude_name",
                    "include_leader",
                    "include_stage",
                    "include_leader_if_name",
                    "require_trigger",
                    "exclude_iids",
                ):
                    if op.get(key) is None:
                        continue
                    if own_field_scale and key in {"include_leader", "include_stage"}:
                        continue
                    filters[key] = op[key]
                options = _choice_options(state, seat, buff_tk, catalog, filters or None)
                duration = str(op.get("duration") or "").strip().lower()
                is_opp = buff_tk.startswith("opponent") or "opponent" in buff_tk
                for tid in options:
                    if tid == "leader" or str(tid).startswith("leader-"):
                        owner = foe if is_opp else player
                        _apply_timed_power_mod(
                            owner, amount=amount, duration=duration, controller_seat=seat, on_leader=True
                        )
                        logs.append({"key": "play.log.gains_power", "id": owner.leader_card_id, "amount": f"{amount:+d}"})
                    else:
                        for owner in ((foe, player) if is_opp else (player, foe)):
                            inst = next((c for c in owner.characters if c.iid == tid), None)
                            if not inst:
                                continue
                            _apply_timed_power_mod(
                                owner, amount=amount, duration=duration, controller_seat=seat, on_leader=False, inst=inst
                            )
                            logs.append({"key": "play.log.gains_power", "id": inst.card_id, "amount": f"{amount:+d}"})
                            break
                continue
            if not target:
                filters: dict[str, Any] = {}
                for key in (
                    "cost_lte",
                    "cost_eq",
                    "cost_gte",
                    "power_lte",
                    "power_gte",
                    "base_power_lte",
                    "trait_contains",
                    "name_contains",
                    "exclude_name",
                    "include_leader",
                    "include_stage",
                    "include_leader_if_name",
                    "require_trigger",
                    "exclude_iids",
                ):
                    if op.get(key) is None:
                        continue
                    # per_own_* include_leader/stage are field-count flags, not opp targets.
                    if own_field_scale and key in {"include_leader", "include_stage"}:
                        continue
                    filters[key] = op[key]
                buff_tk = _infer_buff_target_kind(op)
                options = _choice_options(
                    state,
                    seat,
                    buff_tk,
                    catalog,
                    filters or None,
                )
                if not options:
                    continue
                # 「最多1張」optional buff: always ask, even if only one legal target.
                if (optional or op.get("always_choose") or len(options) > 1) and not state.pending_choice:
                    rem = dict(op)
                    rem.pop("target_iid", None)
                    rem.setdefault("target_kind", buff_tk)
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind=buff_tk,
                        options=options,
                        remaining_ops=[rem, *queue],
                        optional=optional,
                        summary=str(op.get("summary") or "Choose a buff target"),
                        purpose="buff",
                    )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                target = options[0]
            duration = str(op.get("duration") or "").strip().lower()
            buff_tk = _infer_buff_target_kind(op)
            is_opp = buff_tk.startswith("opponent") or "opponent" in buff_tk
            if (target == f"leader-{foe.seat}" or (target == "leader" and is_opp)) and target != f"leader-{seat}":
                _apply_timed_power_mod(
                    foe, amount=amount, duration=duration, controller_seat=seat, on_leader=True
                )
                logs.append({"key": "play.log.gains_power", "id": foe.leader_card_id, "amount": f"{amount:+d}"})
                setattr(player, "_last_buff_target_iid", target if target.startswith("leader") else f"leader-{foe.seat}")
            elif target == "leader" or target == f"leader-{seat}":
                _apply_timed_power_mod(
                    player, amount=amount, duration=duration, controller_seat=seat, on_leader=True
                )
                logs.append({"key": "play.log.gains_power", "id": player.leader_card_id, "amount": f"{amount:+d}"})
                setattr(player, "_last_buff_target_iid", "leader")
            else:
                applied = False
                for owner in ((foe, player) if is_opp else (player, foe)):
                    inst = next((c for c in owner.characters if c.iid == target), None)
                    if not inst:
                        continue
                    _apply_timed_power_mod(
                        owner, amount=amount, duration=duration, controller_seat=seat, on_leader=False, inst=inst
                    )
                    logs.append({"key": "play.log.gains_power", "id": inst.card_id, "amount": f"{amount:+d}"})
                    applied = True
                    setattr(player, "_last_buff_target_iid", target)
                    break
                if not applied:
                    continue
            if target:
                for later in queue:
                    if later.get("op") != "buff":
                        continue
                    if str(later.get("target_kind") or "") != str(op.get("target_kind") or ""):
                        continue
                    excl = list(later.get("exclude_iids") or [])
                    if target not in excl:
                        excl.append(target)
                    later["exclude_iids"] = excl
            if op.get("also_deny_blocker_when_attacks"):
                atk_iid = "leader" if str(getattr(player, "_last_buff_target_iid", "") or "").startswith("leader") else str(
                    getattr(player, "_last_buff_target_iid", "") or ""
                )
                if atk_iid:
                    player.deny_blocker.append(
                        {
                            "duration": duration if duration in {"battle", "turn"} else "turn",
                            "when_attacker_iid": atk_iid,
                        }
                    )
            if per_choose:
                left = int(op.get("_buff_repeats_left") or 1) - 1
                if left > 0:
                    cont = dict(op)
                    cont["_buff_repeats_left"] = left
                    cont.pop("target_iid", None)
                    queue.insert(0, cont)
        elif kind == "return_to_hand":
            target = str(op.get("target_iid") or "")
            ctype = str(op.get("card_type") or "").strip().lower()
            tk = str(op.get("target_kind") or "opponent_character")
            if not op.get("target_iid"):
                setattr(player, "_last_return_to_hand_count", 0)
            # Stage return: paper 「舞台卡」must target stages, not Characters.
            if ctype == "stage" and tk not in {"own_stage", "opponent_stage", "any_stage"}:
                tk = "any_stage"
            stage_pool = tk in {"own_stage", "opponent_stage", "any_stage"} or ctype == "stage"
            if not target:
                filters: dict[str, Any] = {}
                if op.get("cost_gte") is not None:
                    filters["cost_gte"] = op["cost_gte"]
                if op.get("cost_lte") is not None:
                    filters["cost_lte"] = op["cost_lte"]
                if op.get("cost_eq") is not None:
                    filters["cost_eq"] = op["cost_eq"]
                if op.get("name_contains"):
                    filters["name_contains"] = op["name_contains"]
                if op.get("exclude_name"):
                    filters["exclude_name"] = op["exclude_name"]
                if op.get("trait_contains"):
                    filters["trait_contains"] = op["trait_contains"]
                options = _choice_options(state, seat, tk, catalog, filters or None)
                if op.get("exclude_self"):
                    src = str(op.get("source_iid") or "")
                    if src:
                        options = [x for x in options if x != src]
                if not options:
                    # Optional colon-cost with no legal payment → effect after colon does not fire.
                    if op.get("as_cost"):
                        return logs
                    continue
                if len(options) == 1 and not op.get("optional"):
                    target = options[0]
                elif not state.pending_choice:
                    choose_seat = (
                        state.other(seat)
                        if str(op.get("chooser") or "").strip().lower() == "opponent"
                        else seat
                    )
                    default_summary = (
                        "Choose a Stage to return"
                        if stage_pool
                        else (
                            "Choose a character to return (cost)"
                            if op.get("as_cost")
                            else "Choose a character to return"
                        )
                    )
                    state.pending_choice = PendingChoice(
                        seat=choose_seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind=tk,
                        options=options,
                        remaining_ops=[dict(op), *queue],
                        optional=bool(op.get("optional", True)),
                        summary=str(op.get("summary") or default_summary),
                        purpose=purpose_from_op(op),
                        controller_seat=seat,
                    )
                    logs.append({"key": "play.log.choice_offer", "name": state.player(choose_seat).username})
                    return logs
                else:
                    continue
            if stage_pool:
                for owner in (foe, player):
                    hit = next((s for s in owner.stages if s.iid == target), None)
                    if not hit:
                        continue
                    owner.stages = [s for s in owner.stages if s.iid != hit.iid]
                    owner.hand.append(hit.card_id)
                    prev = int(getattr(player, "_last_return_to_hand_count", 0) or 0)
                    setattr(player, "_last_return_to_hand_count", prev + 1)
                    logs.append({"key": "play.log.return_hand", "id": hit.card_id})
                    break
            else:
                for owner in (foe, player):
                    hit = next((c for c in owner.characters if c.iid == target), None)
                    if not hit:
                        continue
                    owner_seat = owner.seat
                    if getattr(hit, "cannot_be_removed", False) and owner_seat != seat:
                        logs.append({"key": "play.log.effect_unsupported", "id": "cannot_be_removed"})
                        break
                    if op.get("negate_this_turn") or op.get("negate_effects"):
                        _apply_negate_to_target(
                            owner, hit.iid, str(op.get("duration") or "turn"), seat
                        )
                    from battle.leave_replace import try_replace_leave

                    if try_replace_leave(
                        state, owner_seat, hit, by_opponent=owner_seat != seat, catalog=catalog, by_ko=False
                    ):
                        if _halt_for_replace("return_hand"):
                            return logs
                        logs.append({"key": "play.log.effect_applied", "summary": "replace_leave"})
                        break
                    if hit.don_attached:
                        owner.don_rested += hit.don_attached
                        hit.don_attached = 0
                    owner.characters = [c for c in owner.characters if c.iid != hit.iid]
                    owner.hand.append(hit.card_id)
                    prev = int(getattr(player, "_last_return_to_hand_count", 0) or 0)
                    setattr(player, "_last_return_to_hand_count", prev + 1)
                    logs.append({"key": "play.log.return_hand", "id": hit.card_id})
                    try:
                        from battle.engine import fire_own_trait_leave_or_ko

                        fire_own_trait_leave_or_ko(
                            state,
                            owner_seat,
                            hit.card_id,
                            catalog,
                            by_opponent_effect=owner_seat != seat,
                            by_ko=False,
                        )
                    except Exception:
                        pass
                    break
        elif kind == "trash":
            target = str(op.get("target_iid") or "")
            tk = str(op.get("target_kind") or "").strip().lower()
            as_cost = bool(op.get("as_cost"))
            optional = bool(op.get("optional", True))
            if not target and tk in {"self", "source"}:
                src = str(op.get("source_iid") or "")
                if src and as_cost and optional and not state.pending_choice:
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=src,
                        target_kind="own_character",
                        options=[src],
                        remaining_ops=[dict(op), *queue],
                        optional=True,
                        summary=str(op.get("summary") or "Trash this Character"),
                        purpose=purpose_from_op(op),
                    )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                target = src
            if not target and tk and tk != "self":
                filters: dict[str, Any] = {}
                for key in ("cost_lte", "cost_eq", "cost_gte", "power_lte", "base_power_lte"):
                    if op.get(key) is not None:
                        filters[key] = op[key]
                if op.get("trait_contains"):
                    filters["trait_contains"] = op["trait_contains"]
                if op.get("name_contains"):
                    filters["name_contains"] = op["name_contains"]
                if op.get("exclude_name"):
                    filters["exclude_name"] = op["exclude_name"]
                options = _choice_options(state, seat, tk, catalog, filters or None)
                if op.get("exclude_self"):
                    src = str(op.get("source_iid") or "")
                    options = [i for i in options if i != src]
                if not options:
                    if as_cost:
                        return logs
                    continue
                if len(options) == 1 and not op.get("optional"):
                    target = options[0]
                elif not state.pending_choice:
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind=tk,
                        options=options,
                        remaining_ops=[dict(op), *queue],
                        optional=bool(op.get("optional", True)),
                        summary=str(op.get("summary") or "Choose a Character to trash"),
                purpose=purpose_from_op(op),
            )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                else:
                    continue
            if target == "leader":
                if as_cost:
                    return logs
                continue
            if not target:
                if as_cost:
                    return logs
                continue
            trashed = False
            for owner in (player, foe):
                hit = next((c for c in owner.characters if c.iid == target), None)
                if hit:
                    owner_seat = owner.seat
                    if getattr(hit, "cannot_be_removed", False) and owner_seat != seat:
                        logs.append({"key": "play.log.effect_unsupported", "id": "cannot_be_removed"})
                        if as_cost:
                            return logs
                        break
                    if hit.don_attached:
                        owner.don_rested += hit.don_attached
                        hit.don_attached = 0
                    owner.characters = [c for c in owner.characters if c.iid != hit.iid]
                    owner.trash.append(hit.card_id)
                    logs.append({"key": "play.log.ko", "id": hit.card_id})
                    try:
                        from battle.engine import fire_own_trait_leave_or_ko

                        fire_own_trait_leave_or_ko(
                            state,
                            owner_seat,
                            hit.card_id,
                            catalog,
                            by_opponent_effect=owner_seat != seat,
                            by_ko=True,
                        )
                    except Exception:
                        pass
                    trashed = True
                    break
            if not trashed:
                for owner in (player, foe):
                    hit = next((s for s in owner.stages if s.iid == target), None)
                    if not hit:
                        continue
                    owner.stages = [s for s in owner.stages if s.iid != hit.iid]
                    owner.trash.append(hit.card_id)
                    logs.append({"key": "play.log.ko", "id": hit.card_id})
                    trashed = True
                    break
            if not trashed and as_cost:
                return logs
        elif kind == "trash_hand":
            optional = bool(op.get("optional", True))
            as_cost = bool(op.get("as_cost"))
            require_trigger = bool(op.get("require_trigger"))
            trait = str(op.get("trait_contains") or "").strip()
            hand_owner = foe if str(op.get("owner") or "self") == "opponent" else player
            any_number = bool(op.get("any_number"))
            if any_number:
                n = max(1, min(20, int(op.get("count") or 20)))
            else:
                n = max(1, min(5, int(op.get("count") or 1)))
            if op.get("require_opp_chars_count_lte") is not None and len(foe.characters) > int(
                op["require_opp_chars_count_lte"]
            ):
                continue

            def _hand_ok(cid: str) -> bool:
                info = catalog(cid)
                if require_trigger and not card_has_trigger(info):
                    return False
                if trait:
                    from battle.engine import _info_has_trait

                    if not _info_has_trait(info, trait):
                        return False
                want_type = str(op.get("card_type") or "").strip().lower()
                if want_type:
                    ctype = card_type_of(info)
                    if want_type == "event_or_stage":
                        if ctype not in {"event", "stage"}:
                            return False
                    elif ctype != want_type:
                        return False
                name_raw = str(op.get("name_contains") or "").strip().lower()
                if name_raw:
                    blob = _card_name_blob(info)
                    parts = [p.strip() for p in name_raw.replace("|", "/").split("/") if p.strip()]
                    if parts and not any(p in blob for p in parts):
                        return False
                for key, getter in (
                    ("cost_lte", _printed_cost),
                    ("cost_gte", _printed_cost),
                    ("cost_eq", _printed_cost),
                    ("power_lte", _printed_power),
                    ("power_gte", _printed_power),
                    ("power_eq", _printed_power),
                ):
                    if op.get(key) is None:
                        continue
                    val = getter(info)
                    need = int(op[key])
                    if key.endswith("_lte") and val > need:
                        return False
                    if key.endswith("_gte") and val < need:
                        return False
                    if key.endswith("_eq") and val != need:
                        return False
                return True

            if not str(op.get("target_iid") or "").startswith("hand:") and not op.get("_continue_trash"):
                setattr(player, "_last_trash_hand_count", 0)
                setattr(player, "_trash_buff_applied", 0)

            eligible_idxs = [i for i, cid in enumerate(hand_owner.hand) if _hand_ok(cid)]
            if not any_number and len(eligible_idxs) < n:
                if as_cost:
                    return logs
                continue
            if any_number:
                n = min(n, len(eligible_idxs)) if eligible_idxs else 0
                if n == 0 and as_cost and not optional:
                    return logs
                if n == 0:
                    # Optional any-number cost with nothing to trash: skip follow-ups that need trash.
                    setattr(player, "_last_trash_hand_count", 0)
                    continue
            choose_seat = state.other(seat) if hand_owner is foe else seat
            opp_chooses = hand_owner is foe or str(op.get("chooser") or "").lower() == "opponent"
            token = str(op.get("target_iid") or "")
            # Hand owner (or explicit chooser) picks which cards — never auto-pick when
            # there is discretion (optional cost, multi-pick, or more eligible than needed).
            if not token.startswith("hand:"):
                options = [f"hand:{i}:{hand_owner.hand[i]}" for i in eligible_idxs]
                need_choice = bool(options) and (
                    optional or len(options) > n or n > 1 or any_number
                )
                # Sole eligible card: auto only when the trash is mandatory.
                # Optional / as_cost「可以」must still ask (pay vs skip), even if n==1.
                if len(options) == n == 1 and not any_number and not optional:
                    need_choice = False
                elif len(options) == 1 and n >= 1 and not optional and not any_number:
                    need_choice = False
                if need_choice and not state.pending_choice:
                    state.pending_choice = PendingChoice(
                        seat=choose_seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind="hand_card",
                        options=options,
                        remaining_ops=[dict(op), *queue],
                        optional=bool(optional),
                        summary=str(op.get("summary") or "Trash card(s) from hand"),
                        purpose="trash",
                        controller_seat=seat,
                        multi_select=bool(any_number),
                    )
                    logs.append(
                        {
                            "key": "play.log.choice_offer",
                            "name": state.player(choose_seat).username,
                        }
                    )
                    return logs
                if need_choice:
                    continue
            trashed = 0
            if token.startswith("hand:"):
                parts = token.split(":")
                try:
                    idx = int(parts[1])
                except Exception:
                    idx = -1
                if 0 <= idx < len(hand_owner.hand) and _hand_ok(hand_owner.hand[idx]):
                    cid = hand_owner.hand.pop(idx)
                    hand_owner.trash.append(cid)
                    trashed = 1
                    logs.append({"key": "play.log.trashes", "name": hand_owner.username, "id": cid})
                if trashed:
                    prev = int(getattr(player, "_last_trash_hand_count", 0) or 0)
                    setattr(player, "_last_trash_hand_count", prev + trashed)
                    # Immediate +power per trash so the board updates before「完成」.
                    for nxt in queue:
                        if not isinstance(nxt, dict) or nxt.get("op") != "buff":
                            continue
                        if nxt.get("per_trash_cards") is None:
                            continue
                        step = max(1, int(nxt.get("per_trash_cards") or 1))
                        if trashed < step:
                            break
                        amt = int(nxt.get("amount") or 0) * (trashed // step)
                        tk = str(nxt.get("target_kind") or "leader")
                        tid = str(nxt.get("target_iid") or "")
                        if tid in {"", "leader"} or tk in {"leader", "own_leader"}:
                            player.leader_power_mod += amt
                            logs.append(
                                {
                                    "key": "play.log.gains_power",
                                    "id": player.leader_card_id,
                                    "amount": f"{amt:+d}",
                                }
                            )
                        else:
                            inst = next((c for c in player.characters if c.iid == tid), None)
                            if inst:
                                inst.power_mod += amt
                                logs.append(
                                    {
                                        "key": "play.log.gains_power",
                                        "id": inst.card_id,
                                        "amount": f"{amt:+d}",
                                    }
                                )
                        applied = int(getattr(player, "_trash_buff_applied", 0) or 0)
                        setattr(player, "_trash_buff_applied", applied + (trashed // step))
                        break
                left = n - trashed
                if left > 0:
                    cont = dict(op)
                    cont["count"] = left
                    # Any-number: keep optional so the player can stop and still resolve the buff.
                    cont["optional"] = True if any_number else False
                    cont["_continue_trash"] = True
                    cont.pop("target_iid", None)
                    cont.pop("require_opp_hand_gte", None)
                    cont.pop("require_opp_hand_lte", None)
                    cont.pop("require_hand_gte", None)
                    cont.pop("require_hand_lte", None)
                    queue.insert(0, cont)
            else:
                for idx in sorted(eligible_idxs, reverse=True):
                    if trashed >= n:
                        break
                    if 0 <= idx < len(hand_owner.hand) and _hand_ok(hand_owner.hand[idx]):
                        cid = hand_owner.hand.pop(idx)
                        hand_owner.trash.append(cid)
                        trashed += 1
                        logs.append({"key": "play.log.trashes", "name": hand_owner.username, "id": cid})
                setattr(player, "_last_trash_hand_count", trashed)
            if as_cost and not any_number and token.startswith("hand:") and trashed < 1:
                return logs
            if as_cost and not any_number and not token.startswith("hand:") and trashed < n:
                return logs
            if as_cost and any_number and trashed <= 0 and not optional:
                return logs
            if as_cost and any_number and token.startswith("hand:") and trashed < 1 and int(getattr(player, "_last_trash_hand_count", 0) or 0) <= 0:
                return logs
            # Fire hand-trash watchers once the trash_hand op is complete (no multi-pick continuation).
            total_trashed = int(getattr(hand_owner, "_last_trash_hand_count", 0) or 0) or int(
                getattr(player, "_last_trash_hand_count", 0) or 0
            )
            # Prefer the hand owner's counter when self-trash; keep controller's for equal_trashed draws.
            if hand_owner is player:
                total_trashed = int(getattr(player, "_last_trash_hand_count", 0) or 0)
            cont0 = queue[0] if queue else None
            continuing = (
                isinstance(cont0, dict)
                and cont0.get("op") == "trash_hand"
                and cont0.get("_continue_trash")
            )
            if total_trashed > 0 and not continuing:
                hand_owner.hand_trashed_by_effect_this_turn = True
                try:
                    from battle.engine import fire_hand_trash_by_effect

                    fire_hand_trash_by_effect(
                        state,
                        hand_owner.seat,
                        catalog,
                        effect_card_id=str(op.get("card_id") or ""),
                        by_own_effect=hand_owner.seat == seat,
                        trashed_count=total_trashed,
                    )
                except Exception:
                    pass
        elif kind == "replace_battle_ko":
            player.replace_battle_ko = True
            logs.append({"key": "play.log.effect_applied", "summary": "replace_battle_ko"})
        elif kind == "play_characters_rested":
            logs.append({"key": "play.log.effect_applied", "summary": "play_characters_rested"})
        elif kind == "cannot_attack_leader":
            player.cannot_attack_opp_leader = True
            logs.append({"key": "play.log.effect_applied", "summary": "cannot_attack_leader"})
        elif kind == "replace_leave":
            # Continuous shield — enforced at KO/leave time via try_replace_leave.
            logs.append({"key": "play.log.effect_applied", "summary": "replace_leave"})
        elif kind == "replace_life_damage":
            logs.append({"key": "play.log.effect_applied", "summary": "replace_life_damage"})
        elif kind == "replace_rest":
            # Continuous shield — enforced when rested via try_replace_rest.
            logs.append({"key": "play.log.effect_applied", "summary": "replace_rest"})
        elif kind == "hand_cost_reduce":
            # Activate / event: stash temporary hand-play cost reduction on the player.
            mod = {
                "amount": int(op.get("amount") or 0),
                "next_only": bool(op.get("next_only")),
            }
            if op.get("name_contains"):
                mod["name_contains"] = str(op.get("name_contains"))
            if op.get("cost_gte") is not None:
                try:
                    mod["cost_gte"] = int(op["cost_gte"])
                except (TypeError, ValueError):
                    pass
            if op.get("trait_contains"):
                mod["trait_contains"] = str(op.get("trait_contains"))
            player.temp_hand_cost_mods.append(mod)
            logs.append({"key": "play.log.effect_applied", "summary": "hand_cost_reduce"})
        elif kind == "cannot_take_life":
            player.cannot_take_life = True
            logs.append({"key": "play.log.effect_applied", "summary": "cannot_take_life"})
        elif kind == "skip_untap":
            from battle.engine import effective_character_cost

            count = max(1, int(op.get("count") or 1))
            tk = str(op.get("target_kind") or "opponent_character_rested").strip().lower()
            if tk in {"self", "own_character", "source"}:
                src = str(op.get("source_iid") or op.get("target_iid") or "")
                if src and src not in player.skip_untap_iids:
                    player.skip_untap_iids.append(src)
                    logs.append({"key": "play.log.effect_applied", "summary": "skip_untap"})
                continue
            own_leader = tk in {"own_leader", "self_leader"} or (
                tk in {"leader"} and str(op.get("owner") or "").strip().lower() in {"self", "own"}
            )
            if own_leader or tk in {"leader"} or (op.get("include_leader") and not op.get("count") and tk == "leader"):
                marked = player if own_leader else foe
                if op.get("require_rested") and not marked.leader_rested:
                    continue
                marked.leader_skip_untap = True
                logs.append(
                    {
                        "key": "play.log.effect_applied",
                        "summary": "skip_untap:own_leader" if own_leader else "skip_untap:leader",
                    }
                )
                continue
            cost_lte = op.get("cost_lte")
            cost_eq = op.get("cost_eq")
            power_lte = op.get("power_lte") or op.get("base_power_lte")
            # Continuous aura: mark all matching Characters on one/both sides.
            if op.get("all") and tk in {"any_character", "all", "all_characters", "opponent_character", "own_character"}:
                owners = []
                if tk.startswith("own"):
                    owners = [(seat, player)]
                elif tk.startswith("opponent"):
                    owners = [(state.other(seat), foe)]
                else:
                    owners = [(seat, player), (state.other(seat), foe)]
                marked = 0
                for own_seat, owner in owners:
                    for c in owner.characters:
                        if cost_lte is not None:
                            try:
                                cost = effective_character_cost(state, own_seat, c, catalog)
                            except Exception:
                                cost = _printed_cost(catalog(c.card_id))
                            if cost > int(cost_lte):
                                continue
                        if cost_eq is not None:
                            try:
                                cost = effective_character_cost(state, own_seat, c, catalog)
                            except Exception:
                                cost = _printed_cost(catalog(c.card_id))
                            if cost != int(cost_eq):
                                continue
                        if power_lte is not None:
                            from battle.engine import inst_power

                            if inst_power(state, own_seat, c.iid, catalog) > int(power_lte):
                                continue
                        if c.iid not in owner.skip_untap_iids:
                            owner.skip_untap_iids.append(c.iid)
                            marked += 1
                if marked:
                    logs.append({"key": "play.log.effect_applied", "summary": "skip_untap:all"})
                continue
            need_rested = tk.endswith("_rested") or "rested" in tk
            include_leader = bool(op.get("include_leader"))
            include_don = bool(op.get("include_don"))
            include_stage = bool(op.get("include_stage"))
            # 「對手休息狀態的卡片」(no type word) → Leader / Character / Stage / DON!!.
            # Do NOT force all zones when only include_leader (e.g. OP04-031 領航卡和角色卡).
            if tk in {"opponent_card", "opponent_cards", "opponent_card_rested"}:
                include_leader = True
                include_don = True
                include_stage = True
            # 「角色卡或咚‼」
            if "character_or_don" in tk or tk.endswith("_or_don") or "_or_don_" in tk:
                include_don = True
            cands = [c for c in foe.characters if (c.rested if need_rested else True)]
            if cost_lte is not None:
                cands = [
                    c
                    for c in cands
                    if effective_character_cost(state, state.other(seat), c, catalog) <= int(cost_lte)
                ]
            if cost_eq is not None:
                cands = [
                    c
                    for c in cands
                    if effective_character_cost(state, state.other(seat), c, catalog) == int(cost_eq)
                ]
            if power_lte is not None:
                from battle.engine import inst_power

                foe_seat = state.other(seat)
                cands = [c for c in cands if inst_power(state, foe_seat, c.iid, catalog) <= int(power_lte)]
            options: list[str] = [c.iid for c in cands]
            excluded = {str(x) for x in (op.get("exclude_iids") or [])}
            options = [x for x in options if x not in excluded and x not in foe.skip_untap_iids]
            if include_leader and (not need_rested or foe.leader_rested):
                if "leader" not in options and "leader" not in excluded:
                    options.append("leader")
            if include_stage:
                for stg in foe.stages:
                    if need_rested and not stg.rested:
                        continue
                    if stg.iid not in options and stg.iid not in excluded and stg.iid not in foe.skip_untap_iids:
                        options.append(stg.iid)
            if include_don and int(foe.don_rested or 0) > int(getattr(foe, "skip_untap_don", 0) or 0):
                if "don" not in excluded:
                    options.append("don")
            if op.get("all"):
                for iid in options:
                    if iid == "leader":
                        foe.leader_skip_untap = True
                    elif iid == "don":
                        foe.skip_untap_don = int(getattr(foe, "skip_untap_don", 0) or 0) + int(foe.don_rested or 0)
                    elif iid and iid not in foe.skip_untap_iids:
                        foe.skip_untap_iids.append(iid)
                if options:
                    logs.append({"key": "play.log.effect_applied", "summary": "skip_untap"})
                continue
            target = str(op.get("target_iid") or "")
            need_choice = bool(
                not target
                and options
                and not state.pending_choice
                and (
                    op.get("always_choose")
                    or op.get("optional", True)
                    or len(options) > count
                )
            )
            if need_choice:
                choice_tk = "opponent_character_rested" if need_rested else "opponent_character"
                state.pending_choice = PendingChoice(
                    seat=seat,
                    card_id=str(op.get("card_id") or ""),
                    source_iid=str(op.get("source_iid") or ""),
                    target_kind=choice_tk,
                    options=list(options),
                    remaining_ops=[dict(op), *queue],
                    optional=bool(op.get("optional", True)),
                    summary=str(
                        op.get("summary")
                        or "Choose card(s) that will not become active next Refresh"
                    ),
                    purpose=purpose_from_op(op),
                )
                logs.append({"key": "play.log.choice_offer", "name": player.username})
                return logs
            picks = [target] if target else list(options[:count])
            # Multi-pick: after one selection, re-queue remaining count.
            applied = 0
            for iid in picks:
                if applied >= count:
                    break
                if iid == "leader":
                    foe.leader_skip_untap = True
                    applied += 1
                    logs.append({"key": "play.log.effect_applied", "summary": "skip_untap:leader"})
                elif iid == "don":
                    if int(foe.don_rested or 0) <= int(getattr(foe, "skip_untap_don", 0) or 0):
                        continue
                    foe.skip_untap_don = int(getattr(foe, "skip_untap_don", 0) or 0) + 1
                    applied += 1
                    logs.append({"key": "play.log.effect_applied", "summary": "skip_untap:don"})
                elif iid and iid not in foe.skip_untap_iids:
                    foe.skip_untap_iids.append(iid)
                    applied += 1
            left = count - applied
            if left > 0 and target and len(options) > 1:
                cont = {k: v for k, v in op.items() if k != "target_iid"}
                cont["count"] = left
                excl = list(cont.get("exclude_iids") or [])
                if target and target not in excl and target != "don":
                    excl.append(target)
                cont["exclude_iids"] = excl
                # Filter already-picked from future options via exclude on chars
                queue.insert(0, cont)
            if applied:
                logs.append({"key": "play.log.effect_applied", "summary": "skip_untap"})
        elif kind == "reorder_life":
            owner = str(op.get("owner") or "self").strip().lower()
            to_deck_top = bool(op.get("to_deck_top"))
            # Infer mode from encoding: self_or_opponent / look_top → peek top 1;
            # to_deck_top → move 1 Life to deck top then reorder rest; else reorder all.
            if to_deck_top:
                mode = "to_deck_top"
            elif owner == "self_or_opponent" or op.get("look_top") or int(op.get("count") or 0) == 1:
                mode = "top_or_bottom"
            else:
                mode = "reorder_all"
            optional = bool(op.get("optional", mode == "top_or_bottom"))

            if mode == "top_or_bottom":
                # Step 1: choose whose Life (自己或對手).
                if owner == "self_or_opponent":
                    chosen_owner = str(op.get("life_owner") or op.get("target_iid") or "")
                    if chosen_owner in {"life_owner:self", "self"}:
                        owner = "self"
                    elif chosen_owner in {"life_owner:opponent", "opponent"}:
                        owner = "opponent"
                    else:
                        opts: list[str] = []
                        if player.life:
                            opts.append("life_owner:self")
                        if foe.life:
                            opts.append("life_owner:opponent")
                        if not opts:
                            continue
                        if len(opts) == 1 and not optional:
                            owner = "opponent" if opts[0].endswith("opponent") else "self"
                        elif not state.pending_choice:
                            state.pending_choice = PendingChoice(
                                seat=seat,
                                card_id=str(op.get("card_id") or ""),
                                source_iid=str(op.get("source_iid") or ""),
                                target_kind="life_owner",
                                options=opts,
                                remaining_ops=[dict(op), *queue],
                                optional=optional,
                                summary=str(
                                    op.get("summary")
                                    or "Look up to 1 top Life; place top or bottom / 查看最多1張生命值區上面"
                                ),
                                option_labels={
                                    "life_owner:self": "Your Life / 自己的生命值",
                                    "life_owner:opponent": "Opponent's Life / 對手的生命值",
                                },
                                purpose="life",
                            )
                            logs.append({"key": "play.log.choice_offer", "name": player.username})
                            return logs
                        else:
                            continue

                life_owner = foe if owner == "opponent" else player
                if not life_owner.life:
                    continue
                peeked = life_owner.life[0]
                pos_token = str(op.get("target_iid") or "")
                if pos_token not in {"life:top", "life:bottom"}:
                    if not state.pending_choice:
                        state.pending_choice = PendingChoice(
                            seat=seat,
                            card_id=str(op.get("card_id") or ""),
                            source_iid=str(op.get("source_iid") or ""),
                            target_kind="life_position",
                            options=["life:top", "life:bottom"],
                            remaining_ops=[
                                {
                                    **dict(op),
                                    "owner": owner,
                                    "life_owner": owner,
                                    "looked_cid": peeked,
                                },
                                *queue,
                            ],
                            optional=optional,
                            summary=str(
                                op.get("summary")
                                or f"Looked {peeked}: place on Life top or bottom / 放置在生命值區上面或下面"
                            ),
                            option_labels={"life:top": "Life top", "life:bottom": "Life bottom"},
                            purpose="life",
                        )
                        logs.append({"key": "play.log.choice_offer", "name": player.username})
                        return logs
                    continue
                # Place: top = no-op; bottom = move top card to bottom.
                if pos_token == "life:bottom":
                    cid = life_owner.life.pop(0)
                    face = False
                    if life_owner.life_face:
                        face = bool(life_owner.life_face.pop(0))
                    life_owner.life.append(cid)
                    if life_owner.life_face or face:
                        while len(life_owner.life_face) < len(life_owner.life) - 1:
                            life_owner.life_face.append(False)
                        life_owner.life_face.append(face)
                logs.append(
                    {
                        "key": "play.log.effect_applied",
                        "summary": "reorder_life",
                        "n": 1,
                        "owner": owner,
                        "dest": "bottom" if pos_token == "life:bottom" else "top",
                        "id": peeked,
                    }
                )
            elif mode == "reorder_all":
                life_owner = foe if owner == "opponent" else player
                if not life_owner.life:
                    continue
                if len(life_owner.life) == 1:
                    logs.append(
                        {
                            "key": "play.log.effect_applied",
                            "summary": "reorder_life",
                            "n": 1,
                            "owner": owner,
                        }
                    )
                    continue
                revealed = list(life_owner.life)
                life_owner.life.clear()
                life_owner.life_face.clear()
                state.pending_search = PendingSearch(
                    seat=seat,
                    card_id=str(op.get("card_id") or ""),
                    source_iid=str(op.get("source_iid") or ""),
                    revealed=revealed,
                    eligible=list(range(len(revealed))),
                    max_add=0,
                    summary=str(op.get("summary") or "Reorder Life cards / 依任意順序放置生命值卡"),
                    remaining_ops=list(queue),
                    phase="order",
                    bottom_order=[],
                    order_bottom=True,
                    destination="life_reorder",
                    life_seat=life_owner.seat,
                    order_dest="top",
                )
                logs.append({"key": "play.log.search_order", "name": player.username, "n": len(revealed)})
                return logs
            else:
                # to_deck_top: look all Life; put 1 on deck top; reorder rest on Life.
                life_owner = foe if owner == "opponent" else player
                if not life_owner.life:
                    continue
                revealed = list(life_owner.life)
                life_owner.life.clear()
                life_owner.life_face.clear()
                state.pending_search = PendingSearch(
                    seat=seat,
                    card_id=str(op.get("card_id") or ""),
                    source_iid=str(op.get("source_iid") or ""),
                    revealed=revealed,
                    eligible=list(range(len(revealed))),
                    max_add=1,
                    summary=str(
                        op.get("summary")
                        or "Choose 1 Life card to put on deck top; reorder the rest / 將1張放到卡組上面"
                    ),
                    remaining_ops=list(queue),
                    phase="pick",
                    bottom_order=[],
                    order_bottom=True,
                    destination="deck_top_life_rest",
                    life_seat=life_owner.seat,
                    order_dest="top",
                )
                logs.append({"key": "play.log.search_offer", "name": player.username, "n": len(revealed)})
                return logs
        elif kind == "look_deck":
            n = max(1, min(8, int(op.get("count") or 1)))
            take = min(n, len(player.deck))
            if take <= 0:
                continue
            pos = str(op.get("position") or "top_or_bottom").strip().lower()
            token = str(op.get("target_iid") or "").strip().lower()
            if pos == "top_or_bottom" and token not in {"deck:top", "deck:bottom"}:
                if not state.pending_choice:
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind="deck_position",
                        options=["deck:top", "deck:bottom"],
                        remaining_ops=[dict(op), *queue],
                        optional=False,
                        summary=str(op.get("summary") or "Place cards on top or bottom / 放到卡組上面或下面"),
                        purpose="deck_order",
                    )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                continue
            if token == "deck:top" or pos == "top":
                dest = "top"
            elif token == "deck:bottom" or pos == "bottom":
                dest = "bottom"
            else:
                dest = "bottom"
            peeked = [player.deck.pop(0) for _ in range(take)]
            if take == 1:
                if dest == "top":
                    player.deck.insert(0, peeked[0])
                else:
                    player.deck.append(peeked[0])
                logs.append({"key": "play.log.effect_applied", "summary": "look_deck", "n": take, "dest": dest})
                continue
            state.pending_search = PendingSearch(
                seat=seat,
                card_id=str(op.get("card_id") or ""),
                source_iid=str(op.get("source_iid") or ""),
                revealed=list(peeked),
                eligible=list(range(len(peeked))),
                max_add=0,
                summary=str(op.get("summary") or "Reorder looked cards"),
                remaining_ops=list(queue),
                phase="order",
                bottom_order=[],
                order_bottom=True,
                order_dest=dest,
            )
            logs.append({"key": "play.log.search_order", "name": player.username, "n": take})
            return logs
        elif kind == "look_opp_deck":
            n = max(1, min(5, int(op.get("count") or 1)))
            take = min(n, len(foe.deck))
            peeked: list[str] = []
            costs: list[int] = []
            if take:
                peeked = [foe.deck.pop(0) for _ in range(take)]
                for cid in peeked:
                    info = catalog(cid) if callable(catalog) else {}
                    try:
                        costs.append(int((info or {}).get("cost") or 0))
                    except (TypeError, ValueError):
                        costs.append(0)
                # Put back face-up reveal (top order preserved).
                for cid in reversed(peeked):
                    foe.deck.insert(0, cid)
            # Declare-cost match: without a UI prompt, mark pending for later ops.
            # Downstream ops with if_declared_cost_match skip until a match is confirmed.
            setattr(player, "_opp_deck_reveal_costs", costs)
            setattr(player, "_declare_cost_match", bool(op.get("declare_cost") and costs))
            logs.append(
                {
                    "key": "play.log.effect_applied",
                    "summary": "look_opp_deck" + (":declare_cost" if op.get("declare_cost") else ""),
                    "n": take,
                    "costs": costs,
                    "ids": peeked,
                }
            )
        elif kind == "negate_effects":
            tk = str(op.get("target_kind") or "opponent_leader_or_character")
            target = str(op.get("target_iid") or "")
            duration = str(op.get("duration") or "turn")
            optional = bool(op.get("optional", True))
            if tk in {"self", "source"}:
                src = str(op.get("source_iid") or target)
                inst = next((c for c in player.characters if c.iid == src), None)
                if inst:
                    _apply_negate_to_target(player, inst.iid, duration, seat)
                    logs.append({"key": "play.log.effect_applied", "id": inst.card_id, "summary": "negate_effects:self"})
                continue
            if op.get("all") or tk == "opponent_all":
                _apply_negate_to_target(foe, "leader", duration, seat)
                for ch in foe.characters:
                    _apply_negate_to_target(foe, ch.iid, duration, seat)
                logs.append({"key": "play.log.effect_applied", "summary": "negate_effects_all"})
                continue
            if not target:
                options: list[str] = []
                leader_only = tk == "leader" or (
                    op.get("include_leader") and not op.get("include_characters") and tk not in {
                        "opponent_character",
                        "opponent_leader_or_character",
                    }
                )
                if leader_only or op.get("include_leader") or tk in {"opponent_leader_or_character", "leader"}:
                    if tk != "opponent_character" or op.get("include_leader"):
                        options.append("leader")
                if (not leader_only) and (
                    op.get("include_characters")
                    or tk in {"opponent_character", "opponent_leader_or_character"}
                ):
                    for c in foe.characters:
                        if op.get("cost_lte") is not None or op.get("cost_gte") is not None or op.get("cost_eq") is not None:
                            try:
                                from battle.engine import printed_cost

                                pc = int(printed_cost(catalog(c.card_id)))
                            except Exception:
                                pc = 99
                            if op.get("cost_lte") is not None and pc > int(op["cost_lte"]):
                                continue
                            if op.get("cost_gte") is not None and pc < int(op["cost_gte"]):
                                continue
                            if op.get("cost_eq") is not None and pc != int(op["cost_eq"]):
                                continue
                        options.append(c.iid)
                if leader_only:
                    options = ["leader"]
                if not options:
                    continue
                if (optional or len(options) > 1) and not state.pending_choice:
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind="opponent_character" if "leader" not in options else "opponent_leader_or_character",
                        options=options,
                        remaining_ops=[dict(op), *queue],
                        optional=optional,
                        summary=str(op.get("summary") or "Choose a card to negate effects"),
                        purpose=purpose_from_op(op),
                    )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                target = options[0]
            if _apply_negate_to_target(foe, target, duration, seat):
                setattr(player, "_last_negate_target_iid", target)
                logs.append({"key": "play.log.effect_applied", "summary": "negate_effects"})
        elif kind == "negate_on_play":
            side = str(op.get("side") or "opponent")
            if side in {"self", "both"}:
                player.negate_on_play = True
            if side in {"opponent", "both"}:
                foe.negate_on_play = True
            logs.append({"key": "play.log.effect_applied", "summary": f"negate_on_play:{side}"})
        elif kind == "opponent_hand_to_bottom":
            # Opponent chooses which of their hand cards go to deck bottom (and in which order).
            n = max(1, min(5, int(op.get("count") or 1)))
            if not foe.hand:
                continue
            token = str(op.get("target_iid") or "")
            if not token.startswith("hand:"):
                options = [f"hand:{i}:{cid}" for i, cid in enumerate(foe.hand)]
                # Auto only when exactly one card exists (no discretion).
                if len(foe.hand) > 1 or n > 1:
                    if not state.pending_choice:
                        state.pending_choice = PendingChoice(
                            seat=state.other(seat),
                            card_id=str(op.get("card_id") or ""),
                            source_iid=str(op.get("source_iid") or ""),
                            target_kind="hand_card",
                            options=options,
                            remaining_ops=[dict(op), *queue],
                            optional=False,
                            summary=str(
                                op.get("summary")
                                or f"Opponent: place {n} hand card(s) on deck bottom"
                            ),
                            controller_seat=seat,
                purpose=purpose_from_op(op),
            )
                        logs.append(
                            {
                                "key": "play.log.choice_offer",
                                "name": foe.username,
                                "summary": "opponent_hand_to_bottom",
                            }
                        )
                        return logs
                    continue
            moved = 0
            if token.startswith("hand:"):
                parts = token.split(":")
                try:
                    idx = int(parts[1])
                except Exception:
                    idx = -1
                if 0 <= idx < len(foe.hand):
                    cid = foe.hand.pop(idx)
                    foe.deck.append(cid)
                    moved = 1
                    logs.append(
                        {"key": "play.log.return_bottom", "name": foe.username, "n": 1, "id": cid}
                    )
                left = n - moved
                if left > 0 and foe.hand:
                    cont = dict(op)
                    cont["count"] = left
                    cont.pop("target_iid", None)
                    # Hand-size gates apply once at effect start, not mid multi-pick.
                    cont.pop("require_opp_hand_gte", None)
                    cont.pop("require_opp_hand_lte", None)
                    queue.insert(0, cont)
                continue
            # Single-card auto path.
            cid = foe.hand.pop()
            foe.deck.append(cid)
            logs.append({"key": "play.log.return_bottom", "name": foe.username, "n": 1, "id": cid})
            left = n - 1
            if left > 0 and foe.hand:
                cont = dict(op)
                cont["count"] = left
                cont.pop("target_iid", None)
                cont.pop("require_opp_hand_gte", None)
                cont.pop("require_opp_hand_lte", None)
                queue.insert(0, cont)
        elif kind == "trash_to_bottom":
            n = max(1, min(20, int(op.get("count") or 1)))
            owner = foe if str(op.get("owner") or "self") == "opponent" else player
            want = str(op.get("card_type") or "any").lower()
            trait = str(op.get("trait_contains") or op.get("trait_includes") or "").lower()
            name_n = str(op.get("name_contains") or "").strip()
            cost_gte = op.get("cost_gte")
            cost_lte = op.get("cost_lte")
            cost_eq = op.get("cost_eq")
            picked: list[str] = []
            remain: list[str] = []
            for cid in list(owner.trash):
                info = catalog(cid)
                cat = str(info.get("category") or info.get("card_type") or "").lower()
                is_event = "event" in cat or cat in {"event", "events"}
                is_char = "character" in cat
                ok = want == "any" or (want == "event" and is_event) or (want == "character" and is_char)
                if ok and trait:
                    traits = " ".join(
                        str(x or "") for x in (info.get("traits") or []) + (info.get("traits_en") or [])
                    ).lower()
                    # trait_includes: substring match (e.g. "CP")
                    if trait not in traits:
                        ok = False
                if ok and name_n and not _card_matches_name_contains(info, name_n):
                    ok = False
                if ok and (cost_gte is not None or cost_lte is not None or cost_eq is not None):
                    try:
                        from battle.engine import printed_cost

                        pc = int(printed_cost(info))
                    except Exception:
                        pc = 0
                    if cost_eq is not None and pc != int(cost_eq):
                        ok = False
                    if cost_gte is not None and pc < int(cost_gte):
                        ok = False
                    if cost_lte is not None and pc > int(cost_lte):
                        ok = False
                if ok and len(picked) < n:
                    picked.append(cid)
                else:
                    remain.append(cid)
            owner.trash = remain
            for cid in picked:
                owner.deck.append(cid)
            if picked:
                logs.append({"key": "play.log.return_bottom", "name": owner.username, "n": len(picked)})
            per_n = op.get("buff_self_per_n")
            per_amt = op.get("buff_self_amount")
            if per_n and per_amt and picked:
                stacks = len(picked) // max(1, int(per_n))
                if stacks > 0:
                    src = str(op.get("source_iid") or "")
                    inst = next((c for c in player.characters if c.iid == src), None) if src else None
                    if inst is None and player.characters:
                        inst = player.characters[0]
                    if inst is not None:
                        gain = stacks * int(per_amt)
                        inst.power_mod = int(getattr(inst, "power_mod", 0) or 0) + gain
                        logs.append({"key": "play.log.buff", "id": inst.card_id, "amount": gain})
        elif kind == "cannot_attack":
            source = str(op.get("source_iid") or "")
            tk = str(op.get("target_kind") or "self").strip().lower()
            target = str(op.get("target_iid") or source)
            if tk in {"leader", "own_leader"} or target in {"leader", f"leader-{seat}"}:
                player.deny_attack_leader = True
                logs.append({"key": "play.log.effect_applied", "summary": "cannot_attack:leader"})
            else:
                inst = next((c for c in player.characters if c.iid == target), None)
                if inst:
                    inst.cannot_attack = True
                    logs.append({"key": "play.log.effect_applied", "id": inst.card_id, "summary": "cannot_attack"})
        elif kind == "cannot_active_don_by_character":
            # Soft lock: Character effects cannot set DON!! active this turn.
            setattr(player, "cannot_active_don_by_character", True)
            logs.append({"key": "play.log.effect_applied", "summary": "cannot_active_don_by_character"})
        elif kind == "cannot_draw_by_effect":
            setattr(player, "cannot_draw_by_effect", True)
            logs.append({"key": "play.log.effect_applied", "summary": "cannot_draw_by_effect"})
        elif kind == "taunt":
            source = str(op.get("source_iid") or "")
            target = str(op.get("target_iid") or source)
            inst = next((c for c in player.characters if c.iid == target), None)
            if inst:
                inst.taunt = True
                logs.append({"key": "play.log.effect_applied", "id": inst.card_id, "summary": "taunt"})
        elif kind == "activate_timing":
            from battle.effect_library import get_card_entry

            timing = str(op.get("timing") or "on_ko")
            cid = str(op.get("card_id") or "")
            entry = get_card_entry(cid) if cid else {}
            linked = [
                a
                for a in (entry.get("abilities") or [])
                if a.get("timing") == timing and a.get("status") != "unsupported"
            ]
            if linked:
                ab = linked[0]
                try:
                    from battle.engine import _ability_board_conditions_ok

                    if catalog and not _ability_board_conditions_ok(
                        state,
                        seat,
                        ab,
                        catalog,
                        source_iid=str(op.get("source_iid") or ""),
                    ):
                        continue
                except Exception:
                    pass
                linked_ops = [dict(x) for x in (ab.get("ops") or []) if x.get("op") != "unsupported"]
                src = str(op.get("source_iid") or "")
                for oo in linked_ops:
                    if src:
                        oo.setdefault("source_iid", src)
                    if cid:
                        oo.setdefault("card_id", cid)
                if linked_ops:
                    queue = linked_ops + queue
                    logs.append({"key": "play.log.effect_applied", "summary": f"activate_timing:{timing}"})
        elif kind == "add_from_trash":
            if op.get("require_trash_gte") is not None and len(player.trash) < int(op["require_trash_gte"]):
                continue
            n = max(1, min(5, int(op.get("count") or 1)))
            if op.get("self_card"):
                cid = str(op.get("card_id") or "")
                moved = 0
                if cid and cid in player.trash:
                    player.trash.remove(cid)
                    dest = _deliver_trash_card(player, cid, op)
                    moved = 1
                if moved:
                    key = "play.log.add_life" if dest == "life" else "play.log.draws"
                    logs.append({"key": key, "name": player.username, "n": moved})
                continue
            excl = str(op.get("name_exclude") or op.get("exclude_name") or "").strip()
            needle = str(op.get("name_contains") or "").strip()
            trait = str(op.get("trait_contains") or "").strip()
            color = str(op.get("color") or "").lower()
            want_type = str(op.get("card_type") or "").lower()
            require_trig = bool(op.get("require_trigger"))
            cost_eq = op.get("cost_eq")
            cost_lte = op.get("cost_lte")
            cost_gte = op.get("cost_gte")
            # Indexed tokens so the player can choose when optional / multi-pick.
            cand_tokens: list[str] = []
            for idx, cid in enumerate(list(player.trash)):
                info = catalog(cid)
                if excl and _card_excluded_by_name(info, excl):
                    continue
                if needle and not _card_matches_name_contains(info, needle):
                    continue
                if want_type and want_type != "any":
                    if card_type_of(info) != want_type:
                        continue
                if trait:
                    from battle.engine import _info_has_trait

                    if not _info_has_trait(info, trait):
                        continue
                if color:
                    blob = _card_color_blob(info)
                    if not any(a.lower() in blob for a in _color_aliases(color)):
                        continue
                if require_trig:
                    blob = str(info.get("effect_en") or "") + str(info.get("effect") or "")
                    if not re.search(r"\[trigger\]|【觸發器】|【触发器】|【触发】", blob, re.I):
                        continue
                printed = _printed_cost(info)
                if cost_eq is not None and printed != int(cost_eq):
                    continue
                if cost_lte is not None and printed > int(cost_lte):
                    continue
                if cost_gte is not None and printed < int(cost_gte):
                    continue
                cand_tokens.append(f"trash:{idx}:{cid}")
            if not cand_tokens:
                continue
            optional = bool(op.get("optional", True))
            # Always let the player choose for optional "up to N" adds, or when more candidates than needed.
            if (optional or len(cand_tokens) > n) and not state.pending_choice:
                then = {
                    "op": "add_from_trash",
                    "count": 1,
                    "optional": False,
                    "self_token": True,
                }
                for k in (
                    "card_type",
                    "trait_contains",
                    "name_contains",
                    "name_exclude",
                    "exclude_name",
                    "color",
                    "cost_lte",
                    "cost_eq",
                    "cost_gte",
                    "require_trigger",
                    "destination",
                    "face",
                    "position",
                ):
                    if op.get(k) is not None:
                        then[k] = op[k]
                dest = str(op.get("destination") or "hand").lower()
                state.pending_choice = PendingChoice(
                    seat=seat,
                    card_id=str(op.get("card_id") or ""),
                    source_iid=str(op.get("source_iid") or ""),
                    target_kind="hand_card",
                    options=cand_tokens,
                    remaining_ops=list(queue),
                    optional=optional,
                    summary=str(op.get("summary") or ("Add a card from trash to Life" if dest == "life" else "Add a card from trash to hand")),
                    purpose=str(op.get("purpose") or ("life" if dest == "life" else "add_hand")),
                    then_op=then,
                )
                logs.append({"key": "play.log.choice_offer", "name": player.username})
                return logs
            # Auto path: forced and unique / exact count.
            moved = 0
            dest = str(op.get("destination") or "hand").lower()
            for token in cand_tokens[:n]:
                mtok = re.match(r"^trash:(\d+):(.+)$", token)
                if not mtok:
                    continue
                idx = int(mtok.group(1))
                cid = mtok.group(2)
                if idx < 0 or idx >= len(player.trash) or player.trash[idx] != cid:
                    try:
                        idx = player.trash.index(cid)
                    except ValueError:
                        continue
                player.trash.pop(idx)
                dest = _deliver_trash_card(player, cid, op)
                moved += 1
            if moved:
                key = "play.log.add_life" if dest == "life" else "play.log.draws"
                logs.append({"key": key, "name": player.username, "n": moved})
        elif kind == "cannot_play_from_hand":
            entry: dict[str, Any] = {"card_type": str(op.get("card_type") or "any")}
            if op.get("base_cost_gte") is not None:
                entry["base_cost_gte"] = int(op["base_cost_gte"])
            if op.get("base_cost_lte") is not None:
                entry["base_cost_lte"] = int(op["base_cost_lte"])
            player.cannot_play_rules.append(entry)
            logs.append({"key": "play.log.effect_applied", "summary": "cannot_play_from_hand"})
        elif kind == "hand_to_deck":
            don_owner = foe if str(op.get("owner") or "self") == "opponent" else player
            pos = str(op.get("position") or "bottom")
            moved = 0
            if op.get("include_self"):
                # Leave field: trash/move this character into deck as part of cost.
                src = str(op.get("source_iid") or "")
                hit = next((c for c in player.characters if c.iid == src), None) if src else None
                if hit:
                    if hit.don_attached:
                        player.don_rested += hit.don_attached
                        hit.don_attached = 0
                    player.characters = [c for c in player.characters if c.iid != hit.iid]
                    if pos == "top":
                        player.deck.insert(0, hit.card_id)
                    else:
                        player.deck.append(hit.card_id)
                    moved += 1
            if op.get("all"):
                n = len(don_owner.hand)
            else:
                n = max(1, min(20 if op.get("all") else 5, int(op.get("count") or 1)))
            for _ in range(n):
                if not don_owner.hand:
                    break
                card = don_owner.hand.pop()
                if pos == "top":
                    don_owner.deck.insert(0, card)
                else:
                    don_owner.deck.append(card)
                moved += 1
            if op.get("shuffle") and don_owner.deck:
                import random

                random.shuffle(don_owner.deck)
            if moved:
                logs.append({"key": "play.log.return_bottom", "name": don_owner.username, "n": moved})
            if op.get("then_draw_equal") and moved:
                drawn = 0
                for _ in range(moved):
                    if not don_owner.deck:
                        break
                    don_owner.hand.append(don_owner.deck.pop(0))
                    drawn += 1
                if drawn:
                    logs.append({"key": "play.log.draws", "name": don_owner.username, "n": drawn})
            elif op.get("then_draw"):
                drawn = 0
                for _ in range(int(op["then_draw"])):
                    if not don_owner.deck:
                        break
                    don_owner.hand.append(don_owner.deck.pop(0))
                    drawn += 1
                if drawn:
                    logs.append({"key": "play.log.draws", "name": don_owner.username, "n": drawn})
        elif kind == "reveal_opp_hand":
            n = max(1, min(5, int(op.get("count") or 1)))
            # Best-effort: log first N hand card ids (no hidden-info UI yet).
            shown = list(foe.hand[:n])
            if shown:
                logs.append(
                    {
                        "key": "play.log.effect_applied",
                        "summary": "reveal_opp_hand",
                        "n": len(shown),
                        "ids": shown,
                    }
                )
        elif kind == "reveal_hand":
            n = max(1, min(10, int(op.get("count") or 1)))
            optional = bool(op.get("optional", True))
            as_cost = bool(op.get("as_cost"))
            hand_owner = foe if str(op.get("owner") or "self") == "opponent" else player
            trait = str(op.get("trait_contains") or op.get("trait_includes") or "").strip()

            def _reveal_ok(cid: str) -> bool:
                info = catalog(cid) if callable(catalog) else {}
                want_type = str(op.get("card_type") or "").strip().lower()
                type_ok = True
                if want_type:
                    ctype = card_type_of(info or {})
                    type_ok = ctype == want_type
                trait_ok = True
                if trait:
                    from battle.engine import _info_has_trait

                    trait_ok = _info_has_trait(info or {}, trait)
                if op.get("type_or_trait") and (want_type or trait):
                    if not ((want_type and type_ok) or (trait and trait_ok)):
                        return False
                else:
                    if want_type and not type_ok:
                        return False
                    if trait and not trait_ok:
                        return False
                for key, getter in (
                    ("cost_lte", _printed_cost),
                    ("cost_gte", _printed_cost),
                    ("cost_eq", _printed_cost),
                    ("power_lte", _printed_power),
                    ("power_gte", _printed_power),
                    ("power_eq", _printed_power),
                ):
                    if op.get(key) is None:
                        continue
                    val = getter(info or {})
                    need = int(op[key])
                    if key.endswith("_lte") and val > need:
                        return False
                    if key.endswith("_gte") and val < need:
                        return False
                    if key.endswith("_eq") and val != need:
                        return False
                if op.get("require_trigger") and not card_has_trigger(info):
                    return False
                return True

            if not str(op.get("target_iid") or "").startswith("hand:"):
                setattr(player, "_last_reveal_hand_count", 0)

            eligible_idxs = [i for i, cid in enumerate(hand_owner.hand) if _reveal_ok(cid)]
            if len(eligible_idxs) < n:
                if as_cost:
                    return logs
                continue
            token = str(op.get("target_iid") or "")
            if not token.startswith("hand:"):
                options = [f"hand:{i}:{hand_owner.hand[i]}" for i in eligible_idxs]
                need_choice = bool(options) and (optional or len(options) > n or n > 1)
                if len(options) == n == 1 and not optional:
                    need_choice = False
                elif len(options) == 1 and n >= 1 and not optional:
                    need_choice = False
                if need_choice and not state.pending_choice:
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind="hand_card",
                        options=options,
                        remaining_ops=[dict(op), *queue],
                        optional=bool(optional),
                        summary=str(op.get("summary") or "Reveal card(s) from hand"),
                        purpose="general",
                    )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                if need_choice:
                    continue
            shown: list[str] = []
            if token.startswith("hand:"):
                parts = token.split(":")
                try:
                    idx = int(parts[1])
                except Exception:
                    idx = -1
                if 0 <= idx < len(hand_owner.hand) and _reveal_ok(hand_owner.hand[idx]):
                    cid = hand_owner.hand[idx]
                    shown.append(cid)
                    prev = int(getattr(player, "_last_reveal_hand_count", 0) or 0)
                    setattr(player, "_last_reveal_hand_count", prev + 1)
                    logs.append(
                        {
                            "key": "play.log.effect_applied",
                            "summary": "reveal_hand",
                            "n": 1,
                            "ids": [cid],
                            "as_cost": as_cost,
                        }
                    )
                    left = n - 1
                    if left > 0:
                        cont = dict(op)
                        cont["count"] = left
                        cont["optional"] = False
                        cont.pop("target_iid", None)
                        queue.insert(0, cont)
                elif as_cost:
                    return logs
            else:
                for idx in eligible_idxs:
                    if len(shown) >= n:
                        break
                    shown.append(hand_owner.hand[idx])
                setattr(player, "_last_reveal_hand_count", len(shown))
                logs.append(
                    {
                        "key": "play.log.effect_applied",
                        "summary": "reveal_hand",
                        "n": len(shown),
                        "ids": shown,
                        "as_cost": as_cost,
                    }
                )
                if as_cost and len(shown) < n:
                    return logs
        elif kind == "grant_cost":
            from battle.engine import _info_has_trait

            amt = int(op.get("amount") or 0)
            trait = str(op.get("trait_contains") or op.get("trait_includes") or "").strip()
            name_needle = str(op.get("name_contains") or "").strip()
            tk = str(op.get("target_kind") or "own_character")
            if op.get("all") or tk == "all_own":
                pool = foe.characters if "opponent" in tk else player.characters
                for ch in pool:
                    info = catalog(ch.card_id)
                    if op.get("trait_includes"):
                        blob = " ".join(str(x or "") for x in (info.get("traits") or []) + (info.get("traits_en") or [])).lower()
                        needles = [x.strip().lower() for x in str(op.get("trait_includes")).split("|") if x.strip()]
                        if needles and not any(n in blob for n in needles):
                            continue
                    elif trait and not _info_has_trait(info, trait):
                        continue
                    if name_needle and not _card_matches_name_contains(info, name_needle):
                        continue
                    ch.cost_mod += amt
                logs.append({"key": "play.log.effect_applied", "summary": f"grant_cost:{amt}"})
            else:
                target = str(op.get("target_iid") or "")
                source = str(op.get("source_iid") or "")
                if not target and tk == "self" and source:
                    target = source
                if not target and tk in {"own_character", "own_characters", "own_leader_or_character"}:
                    options: list[str] = []
                    if tk == "own_leader_or_character":
                        lead_info = catalog(player.leader_card_id)
                        ok_lead = True
                        if trait and not _info_has_trait(lead_info, trait):
                            ok_lead = False
                        if name_needle and not _card_matches_name_contains(lead_info, name_needle):
                            ok_lead = False
                        if ok_lead:
                            options.append("leader")
                    for ch in player.characters:
                        info = catalog(ch.card_id)
                        if trait and not _info_has_trait(info, trait):
                            continue
                        if name_needle and not _card_matches_name_contains(info, name_needle):
                            continue
                        options.append(ch.iid)
                    if not options:
                        continue
                    optional = bool(op.get("optional", True))
                    if (optional or len(options) > 1) and not state.pending_choice:
                        state.pending_choice = PendingChoice(
                            seat=seat,
                            card_id=str(op.get("card_id") or ""),
                            source_iid=source,
                            target_kind="own_character" if "leader" not in options else "own_leader_or_character",
                            options=options,
                            remaining_ops=[dict(op), *queue],
                            optional=optional,
                            summary=str(op.get("summary") or f"+{amt} cost this turn / 費用+{amt}"),
                            purpose="grant_cost",
                        )
                        logs.append({"key": "play.log.choice_offer", "name": player.username})
                        return logs
                    target = options[0]
                if target == "leader" or target == f"leader-{seat}":
                    # Leaders don't use cost_mod; skip silently.
                    continue
                inst = next((c for c in player.characters if c.iid == target), None) if target else None
                if inst:
                    inst.cost_mod += amt
                    logs.append({"key": "play.log.effect_applied", "id": inst.card_id, "summary": f"grant_cost:{amt}"})
        elif kind == "redirect_attack":
            if state.attack and state.attack.attacker_seat == state.other(seat):
                target = str(op.get("target_iid") or "")
                if not target:
                    from battle.engine import _info_has_trait

                    options: list[str] = []
                    name_n = str(op.get("name_contains") or "").strip()
                    trait = str(op.get("trait_contains") or "").strip()
                    base_gte = op.get("base_power_gte")
                    for c in player.characters:
                        info = catalog(c.card_id)
                        if trait and not _info_has_trait(info, trait):
                            continue
                        if name_n and not _card_matches_name_contains(info, name_n):
                            continue
                        if base_gte is not None and _printed_power(info) < int(base_gte):
                            continue
                        options.append(c.iid)
                    # Leader: include_leader (e.g. OP16-080 「這位領航員或…」) or trait match.
                    # Skip when name/power filters imply Character-only.
                    include_leader = bool(op.get("include_leader"))
                    if not name_n and base_gte is None:
                        if include_leader or not trait or _info_has_trait(
                            catalog(player.leader_card_id), trait
                        ):
                            options = ["leader", *options]
                    if not options:
                        continue
                    if len(options) > 1 and not state.pending_choice:
                        state.pending_choice = PendingChoice(
                            seat=seat,
                            card_id=str(op.get("card_id") or ""),
                            source_iid=str(op.get("source_iid") or ""),
                            target_kind="own_character",
                            options=options,
                            remaining_ops=[dict(op), *queue],
                            optional=bool(op.get("optional", False)),
                            summary=str(op.get("summary") or "Choose new attack target"),
                purpose=purpose_from_op(op),
            )
                        logs.append({"key": "play.log.choice_offer", "name": player.username})
                        return logs
                    target = options[0]
                state.attack.target_iid = target
                logs.append({"key": "play.log.effect_applied", "summary": "redirect_attack"})
        elif kind == "trash_hand_down_to":
            size = int(op.get("hand_size") or 5)
            sides = []
            side = str(op.get("side") or "both")
            if side in {"self", "both"}:
                sides.append(player)
            if side in {"opponent", "both"}:
                sides.append(foe)
            for pl in sides:
                while len(pl.hand) > size:
                    pl.trash.append(pl.hand.pop())
                    logs.append({"key": "play.log.trash_hand", "name": pl.username})
        elif kind == "life_to_hand":
            n = max(1, min(5, int(op.get("count") or 1)))
            pos = str(op.get("position") or "top")
            owner_side = str(op.get("owner") or "self")
            life_owner = foe if owner_side == "opponent" else player
            hand_owner_mode = str(op.get("hand_owner") or ("controller" if owner_side == "opponent" else "life_owner"))
            if hand_owner_mode == "life_owner":
                hand_owner = life_owner
            else:
                hand_owner = player
            as_cost = bool(op.get("as_cost"))
            if len(life_owner.life) < n:
                if as_cost:
                    return logs
                continue
            # top_or_bottom: prefer top unless pending chose bottom
            if pos == "top_or_bottom" and str(op.get("target_iid") or "") not in {"life:top", "life:bottom"}:
                if not state.pending_choice:
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind="life_position",
                        options=["life:top", "life:bottom"],
                        remaining_ops=[dict(op), *queue],
                        optional=bool(op.get("optional", True)) and not as_cost,
                        summary=str(op.get("summary") or "Choose Life card (top or bottom)"),
                        option_labels={"life:top": "Life top", "life:bottom": "Life bottom"},
                purpose=purpose_from_op(op),
            )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
            if str(op.get("target_iid") or "") == "life:bottom" or pos == "bottom":
                pos = "bottom"
            else:
                pos = "top"
            moved = 0
            for _ in range(n):
                if not life_owner.life:
                    break
                if pos == "bottom":
                    card = life_owner.life.pop()
                    if life_owner.life_face and len(life_owner.life_face) >= len(life_owner.life) + 1:
                        life_owner.life_face.pop()
                else:
                    card = life_owner.life.pop(0)
                    if life_owner.life_face:
                        life_owner.life_face.pop(0)
                hand_owner.hand.append(card)
                moved += 1
            setattr(player, "_last_life_to_hand_count", moved)
            if moved:
                logs.append({"key": "play.log.draws", "name": hand_owner.username, "n": moved})
                try:
                    from battle.engine import fire_life_leave

                    fire_life_leave(state, life_owner.seat, catalog)
                except Exception:
                    pass
            elif as_cost:
                return logs
        elif kind == "trash_life":
            pos = str(op.get("position") or "top")
            as_cost = bool(op.get("as_cost"))
            life_owner = foe if str(op.get("owner") or "self") == "opponent" else player
            until = op.get("until_life_eq")
            if until is not None:
                target_life = max(0, min(10, int(until)))
                n = max(0, len(life_owner.life) - target_life)
            else:
                n = max(1, min(10, int(op.get("count") or 1)))
            if n <= 0:
                continue
            if len(life_owner.life) < n and until is None:
                if as_cost:
                    return logs
                continue
            moved = 0
            for _ in range(n):
                if not life_owner.life:
                    break
                if until is not None and len(life_owner.life) <= int(until):
                    break
                if pos == "bottom":
                    card = life_owner.life.pop()
                    if life_owner.life_face:
                        life_owner.life_face.pop()
                else:
                    card = life_owner.life.pop(0)
                    if life_owner.life_face:
                        life_owner.life_face.pop(0)
                life_owner.trash.append(card)
                moved += 1
            if moved:
                logs.append({"key": "play.log.life_trashed", "name": life_owner.username, "n": moved})
                try:
                    from battle.engine import fire_life_leave

                    fire_life_leave(state, life_owner.seat, catalog)
                except Exception:
                    pass
            elif as_cost:
                return logs
        elif kind == "hand_to_life":
            n = max(1, min(5, int(op.get("count") or 1)))
            if not player.hand:
                continue

            def _hand_to_life_ok(cid: str) -> bool:
                info = catalog(cid)
                want_type = str(op.get("card_type") or "").strip().lower()
                if want_type and card_type_of(info) != want_type:
                    return False
                fake = dict(op)
                fake["card_type"] = want_type or card_type_of(info)
                return _hand_card_matches_play_op(info, fake)

            eligible = [f"hand:{i}:{cid}" for i, cid in enumerate(player.hand) if _hand_to_life_ok(cid)]
            if not eligible:
                continue
            if not str(op.get("target_iid") or "").startswith("hand:") and not state.pending_choice:
                optional = bool(op.get("optional", True))
                need_choice = optional or len(eligible) > n or n > 1
                if len(eligible) == n == 1 and not optional:
                    need_choice = False
                if need_choice:
                    then = {"op": "hand_to_life", "count": 1, "optional": False}
                    for k in (
                        "card_type",
                        "require_trigger",
                        "name_contains",
                        "trait_contains",
                        "face",
                        "position",
                        "cost_eq",
                        "cost_lte",
                        "cost_gte",
                    ):
                        if op.get(k) is not None:
                            then[k] = op[k]
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind="hand_card",
                        options=eligible,
                        remaining_ops=list(queue),
                        optional=optional,
                        summary=str(op.get("summary") or "Add 1 card from hand to Life"),
                        then_op=then,
                        purpose=purpose_from_op(op),
                    )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                op = dict(op)
                op["target_iid"] = eligible[0]
            token = str(op.get("target_iid") or "")
            idx = 0
            if token.startswith("hand:"):
                try:
                    idx = int(token.split(":")[1])
                except (IndexError, ValueError):
                    idx = 0
            if idx < 0 or idx >= len(player.hand):
                idx = 0
            if not player.hand:
                continue
            card = player.hand.pop(idx)
            player.life.insert(0, card)
            face = str(op.get("face") or "").strip().lower()
            face_up = face != "down"
            if player.life_face or face in {"up", "down"}:
                if not player.life_face:
                    player.life_face = [True] * (len(player.life) - 1)
                player.life_face.insert(0, face_up)
            logs.append({"key": "play.log.add_life", "name": player.username, "n": 1})
        elif kind == "place_on_life":
            # Place Character onto Life (usually opponent's Character → opponent's Life).
            # life_position resolve overwrites target_iid with life:top/bottom, so keep
            # the Character iid in char_iid across the second choice.
            life_owner = foe if str(op.get("owner") or "opponent") == "opponent" else player
            tk = str(op.get("target_kind") or "opponent_character")
            raw_target = str(op.get("target_iid") or "")
            char_iid = str(op.get("char_iid") or "")
            pos = str(op.get("position") or "top_or_bottom")
            face_up = str(op.get("face") or "up") != "down"
            if raw_target.startswith("life:"):
                chosen_pos = raw_target
            elif pos in {"top", "bottom"}:
                chosen_pos = f"life:{pos}"
            else:
                chosen_pos = ""
            if not char_iid and raw_target and not raw_target.startswith("life:"):
                char_iid = raw_target
            if not char_iid:
                filters: dict[str, Any] = {}
                for key in (
                    "cost_lte",
                    "cost_eq",
                    "cost_gte",
                    "power_lte",
                    "power_gte",
                    "base_power_lte",
                    "base_power_gte",
                    "trait_contains",
                    "exclude_name",
                    "name_contains",
                ):
                    if op.get(key) is not None:
                        filters[key] = op[key]
                options = _choice_options(state, seat, tk, catalog, filters or None)
                if not options:
                    if op.get("as_cost"):
                        return logs
                    continue
                if len(options) == 1 and not op.get("optional"):
                    char_iid = options[0]
                elif not state.pending_choice:
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind=tk,
                        options=options,
                        remaining_ops=[dict(op), *queue],
                        optional=bool(op.get("optional", True)),
                        summary=str(op.get("summary") or "Choose a Character to place on Life"),
                        purpose=purpose_from_op(op),
                    )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                else:
                    continue
            if not chosen_pos and pos == "top_or_bottom" and not state.pending_choice:
                cont = dict(op)
                cont["char_iid"] = char_iid
                cont.pop("target_iid", None)
                state.pending_choice = PendingChoice(
                    seat=seat,
                    card_id=str(op.get("card_id") or ""),
                    source_iid=str(op.get("source_iid") or ""),
                    target_kind="life_position",
                    options=["life:top", "life:bottom"],
                    remaining_ops=[cont, *queue],
                    optional=False,
                    summary=str(op.get("summary") or "Place on Life top or bottom"),
                    option_labels={"life:top": "Life top", "life:bottom": "Life bottom"},
                purpose=purpose_from_op(op),
            )
                logs.append({"key": "play.log.choice_offer", "name": player.username})
                return logs
            if not chosen_pos:
                chosen_pos = "life:top"
            hit = next((c for c in life_owner.characters if c.iid == char_iid), None)
            owner_field = life_owner if hit else None
            if not hit:
                hit = next((c for c in player.characters if c.iid == char_iid), None)
                owner_field = player if hit else None
            if not hit:
                hit = next((c for c in foe.characters if c.iid == char_iid), None)
                owner_field = foe if hit else None
            if not hit or owner_field is None:
                continue
            if hit.don_attached:
                owner_field.don_rested += hit.don_attached
                hit.don_attached = 0
            owner_field.characters = [c for c in owner_field.characters if c.iid != hit.iid]
            while len(life_owner.life_face) < len(life_owner.life):
                life_owner.life_face.append(True)
            if chosen_pos == "life:bottom" or pos == "bottom":
                life_owner.life.append(hit.card_id)
                life_owner.life_face.append(face_up)
            else:
                life_owner.life.insert(0, hit.card_id)
                life_owner.life_face.insert(0, face_up)
            logs.append({"key": "play.log.effect_applied", "summary": f"place_on_life:{hit.card_id}"})
        elif kind == "flip_life":
            face = str(op.get("face") or "down")
            pos = str(op.get("position") or "top_or_bottom")
            as_cost = bool(op.get("as_cost"))
            optional = bool(op.get("optional", True))
            if not player.life:
                if as_cost:
                    return logs
                continue
            # Ensure life_face length
            while len(player.life_face) < len(player.life):
                player.life_face.append(True)
            if len(player.life_face) > len(player.life):
                player.life_face = player.life_face[: len(player.life)]
            chosen = str(op.get("target_iid") or "")
            # 「可將…翻成…：效果」— ask pay vs skip even when position is fixed (top/bottom).
            if (
                as_cost
                and optional
                and chosen not in {"life:top", "life:bottom"}
                and not state.pending_choice
            ):
                if pos == "bottom":
                    opts = ["life:bottom"]
                elif pos == "top":
                    opts = ["life:top"]
                else:
                    opts = ["life:top", "life:bottom"]
                state.pending_choice = PendingChoice(
                    seat=seat,
                    card_id=str(op.get("card_id") or ""),
                    source_iid=str(op.get("source_iid") or ""),
                    target_kind="life_position",
                    options=opts,
                    remaining_ops=[dict(op), *queue],
                    optional=True,
                    summary=str(op.get("summary") or f"You may flip Life face-{face}"),
                    option_labels={"life:top": "Life top", "life:bottom": "Life bottom"},
                    purpose=purpose_from_op(op),
                )
                logs.append({"key": "play.log.choice_offer", "name": player.username})
                return logs
            if pos == "top_or_bottom" and chosen not in {"life:top", "life:bottom"} and not state.pending_choice:
                state.pending_choice = PendingChoice(
                    seat=seat,
                    card_id=str(op.get("card_id") or ""),
                    source_iid=str(op.get("source_iid") or ""),
                    target_kind="life_position",
                    options=["life:top", "life:bottom"],
                    remaining_ops=[dict(op), *queue],
                    optional=optional and not as_cost,
                    summary=str(op.get("summary") or f"Flip Life card face-{face}"),
                    option_labels={"life:top": "Life top", "life:bottom": "Life bottom"},
                    purpose=purpose_from_op(op),
                )
                logs.append({"key": "play.log.choice_offer", "name": player.username})
                return logs
            if chosen == "life:bottom" or pos == "bottom":
                idx = len(player.life) - 1
            else:
                idx = 0
            player.life_face[idx] = face == "up"
            logs.append({"key": "play.log.effect_applied", "summary": f"flip_life:{face}"})
        elif kind == "choose_one":
            options = list(op.get("options") or [])
            if len(options) < 2:
                continue
            chooser = str(op.get("chooser") or "self")
            choose_seat = state.other(seat) if chooser == "opponent" else seat

            def _option_gates_ok(opt: dict[str, Any]) -> bool:
                if opt.get("require_opp_hand_gte") is not None and len(foe.hand) < int(opt["require_opp_hand_gte"]):
                    return False
                if opt.get("require_opp_hand_lte") is not None and len(foe.hand) > int(opt["require_opp_hand_lte"]):
                    return False
                if opt.get("require_hand_gte") is not None and len(player.hand) < int(opt["require_hand_gte"]):
                    return False
                if opt.get("require_hand_lte") is not None and len(player.hand) > int(opt["require_hand_lte"]):
                    return False
                if opt.get("require_don_active_gte") is not None and int(player.don_active or 0) < int(
                    opt["require_don_active_gte"]
                ):
                    return False
                if opt.get("require_leader_active") and player.leader_rested:
                    return False
                if opt.get("require_leader_attribute"):
                    want = str(opt["require_leader_attribute"]).strip().lower()
                    blob = card_attr_blob(catalog(player.leader_card_id)).lower()
                    opts = [a.strip().lower() for a in want.split("|") if a.strip()] or [want]
                    if opts and not any(any(k in blob for k in attr_alias_keys(o)) for o in opts):
                        return False
                return True

            gated = [(i, opt) for i, opt in enumerate(options) if isinstance(opt, dict) and _option_gates_ok(opt)]
            if not gated:
                if op.get("as_cost"):
                    return logs
                continue
            optional_choice = bool(op.get("optional", False))
            if len(gated) == 1 and len(options) >= 2 and not optional_choice:
                only_ops = [dict(x) for x in (gated[0][1].get("ops") or []) if isinstance(x, dict)]
                for gkey in ("require_opp_hand_gte", "require_opp_hand_lte", "require_hand_gte", "require_hand_lte"):
                    if gated[0][1].get(gkey) is not None:
                        for oo in only_ops:
                            oo.setdefault(gkey, gated[0][1][gkey])
                if bool(op.get("as_cost")):
                    only_ops.extend(dict(x) for x in queue if isinstance(x, dict))
                    queue.clear()
                if only_ops:
                    queue[0:0] = only_ops
                continue
            tokens = [f"opt:{i}" for i, _ in gated]
            branches: dict[str, list[dict[str, Any]]] = {}
            option_labels: dict[str, str] = {}
            as_cost = bool(op.get("as_cost"))
            for i, opt in gated:
                branch = [dict(x) for x in (opt.get("ops") or []) if isinstance(x, dict)]
                for gkey in ("require_opp_hand_gte", "require_opp_hand_lte", "require_hand_gte", "require_hand_lte"):
                    if opt.get(gkey) is not None:
                        for oo in branch:
                            oo.setdefault(gkey, opt[gkey])
                # Colon-cost: follow-ups only run after a branch is chosen.
                if as_cost:
                    branch.extend(dict(x) for x in queue if isinstance(x, dict))
                branches[f"opt:{i}"] = branch
                option_labels[f"opt:{i}"] = str(opt.get("label") or f"Option {i + 1}")
            labels = "; ".join(f"{tok}:{option_labels[tok]}" for tok in tokens)
            state.pending_choice = PendingChoice(
                seat=choose_seat,
                card_id=str(op.get("card_id") or ""),
                source_iid=str(op.get("source_iid") or ""),
                target_kind="effect_option",
                options=tokens,
                remaining_ops=[] if as_cost else list(queue),
                optional=optional_choice,
                summary=str(op.get("summary") or labels)[:160],
                purpose="choose_effect",
                option_branches=branches,
                option_labels=option_labels,
                controller_seat=seat,
            )
            logs.append({"key": "play.log.choice_offer", "name": state.player(choose_seat).username})
            return logs
            # When as_cost, swallow the shared queue (already copied into each branch).
            if as_cost:
                queue.clear()
        elif kind == "attack_tax":
            entry = {
                "all": bool(op.get("all", True)),
                "trash_hand": max(1, int(op.get("trash_hand") or 2)),
                "duration": str(op.get("duration") or "until_opp_turn_end"),
            }
            foe.attack_tax_rules.append(entry)
            logs.append({"key": "play.log.effect_applied", "summary": f"attack_tax:{entry['trash_hand']}"})
        elif kind in {"deny_attack", "deny_rest"}:
            target = str(op.get("target_iid") or "")
            tk = str(op.get("target_kind") or "opponent_character")
            count = max(1, int(op.get("count") or 1))
            duration = str(op.get("duration") or "until_opp_turn_end").strip().lower()
            if op.get("same_target_as_prior") and not target:
                prior = str(getattr(player, "_last_negate_target_iid", "") or getattr(player, "_last_buff_target_iid", "") or "")
                if not prior or prior == "leader" or str(prior).startswith("leader-"):
                    continue
                target = prior
            filters: dict[str, Any] = {}
            for key in (
                "cost_lte",
                "power_lte",
                "base_power_lte",
                "base_cost_lte",
                "exclude_name",
                "require_no_effect",
                "name_contains",
                "trait_contains",
                "exclude_iids",
            ):
                if op.get(key) is not None:
                    filters[key] = op[key]
            if kind == "deny_attack":
                if duration == "until_opp_turn_end":
                    bucket = foe.deny_attack_until_opp_end_iids
                else:
                    bucket = foe.deny_attack_iids
            else:
                if duration == "until_opp_turn_end":
                    bucket = foe.deny_rest_until_opp_end_iids
                else:
                    bucket = foe.deny_rest_iids

            def _mark_leader_denied() -> None:
                if kind != "deny_attack":
                    return
                if duration == "until_opp_turn_end":
                    foe.deny_attack_leader_until_opp_end = True
                else:
                    foe.deny_attack_leader = True

            if not target:
                options = _choice_options(state, seat, tk, catalog, filters or None)
                if op.get("active_only"):
                    options = [iid for iid in options if any(c.iid == iid and not c.rested for c in foe.characters)]
                options = [iid for iid in options if iid == "leader" or iid not in bucket]
                if op.get("include_leader") and kind == "deny_attack":
                    if op.get("rested_only") and not foe.leader_rested:
                        pass
                    elif "leader" not in options:
                        options = ["leader", *options]
                if op.get("rested_only") and kind == "deny_attack" and tk in {"leader"}:
                    if not foe.leader_rested:
                        continue
                    target = "leader"
                if not options:
                    continue
                if op.get("all"):
                    for iid in options:
                        if iid == "leader":
                            _mark_leader_denied()
                        elif iid not in bucket:
                            bucket.append(iid)
                    logs.append({"key": "play.log.effect_applied", "summary": f"{kind}:all"})
                    continue
                # Up-to-N (e.g. OP14-033 count=2): ask whenever more than one eligible
                # remains, not only when len(options) > count. With exactly 2 eligible
                # and count=2 the old check auto-took options[0] and never re-queued.
                if len(options) > 1 and not state.pending_choice:
                    rem = {k: v for k, v in op.items() if k != "target_iid"}
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind=tk,
                        options=options,
                        remaining_ops=[rem, *queue],
                        optional=bool(op.get("optional", True)),
                        summary=str(op.get("summary") or f"Choose target for {kind}"),
                        purpose=purpose_from_op(op),
                    )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                target = options[0]
            if target == "leader" and kind == "deny_attack":
                _mark_leader_denied()
                logs.append({"key": "play.log.effect_applied", "summary": "deny_attack:leader"})
            elif target and target not in bucket:
                bucket.append(target)
                logs.append({"key": "play.log.effect_applied", "summary": kind})
            left = count - 1
            if left > 0 and target:
                cont = {k: v for k, v in op.items() if k != "target_iid"}
                cont["count"] = left
                excl = list(cont.get("exclude_iids") or [])
                if target not in excl:
                    excl.append(target)
                cont["exclude_iids"] = excl
                queue.insert(0, cont)
        elif kind == "set_cost":
            target = str(op.get("target_iid") or "")
            amt = int(op.get("amount") or 0)
            filters: dict[str, Any] = {}
            if op.get("require_no_effect"):
                filters["require_no_effect"] = True
            if not target:
                options = _choice_options(
                    state, seat, str(op.get("target_kind") or "opponent_character"), catalog, filters or None
                )
                if not options:
                    continue
                if len(options) > 1 and not state.pending_choice and op.get("optional", True):
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind=str(op.get("target_kind") or "opponent_character"),
                        options=options,
                        remaining_ops=[dict(op), *queue],
                        optional=True,
                        summary=str(op.get("summary") or "Choose Character to set cost"),
                purpose=purpose_from_op(op),
            )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                target = options[0]
            for owner in (player, foe):
                inst = next((c for c in owner.characters if c.iid == target), None)
                if inst:
                    printed = _printed_cost(catalog(inst.card_id))
                    inst.cost_mod = amt - printed
                    logs.append({"key": "play.log.effect_applied", "id": inst.card_id, "summary": f"set_cost:{amt}"})
                    break
        elif kind == "attach_don":
            from battle.engine import _info_has_trait

            want = max(1, min(5, int(op.get("count") or 1)))
            # as_rested (paper: 休息狀態的咚) means take from cost-area rested DON!!,
            # not draw fresh DON!! from the DON!! deck into the cost area.
            # from_active (OP13-003): give 1 DON!! already placed in cost area this DON!! Phase.
            take_from_rested_pool = bool(op.get("from_rested") or op.get("as_rested"))
            take_from_active = bool(op.get("from_active")) and not take_from_rested_pool
            take_from_cost_area = (
                bool(op.get("from_cost_area")) and not take_from_rested_pool and not take_from_active
            )
            from_owner_side = str(op.get("from_owner") or op.get("owner") or "self").strip().lower()
            don_src = foe if from_owner_side == "opponent" else player
            tk = str(op.get("target_kind") or "self")
            to_opponent = tk.startswith("opponent")
            board = foe if to_opponent else player
            if take_from_rested_pool:
                n = min(want, int(don_src.don_rested or 0))
            elif take_from_active:
                n = min(want, int(don_src.don_active or 0))
            elif take_from_cost_area:
                n = min(
                    want,
                    int(don_src.don_active or 0) + int(don_src.don_rested or 0),
                )
            else:
                room = _don_room(don_src)
                n = min(want, room)
            if n <= 0:
                if op.get("as_cost"):
                    return logs
                continue
            target = str(op.get("target_iid") or "")
            source = str(op.get("source_iid") or "")
            trait = str(op.get("trait_contains") or "").strip()
            name_needle = str(op.get("name_contains") or "").strip()

            def _attach_char_ok(info: dict[str, Any], inst: CardInst | None = None) -> bool:
                if trait and not _info_has_trait(info, trait):
                    return False
                needle_attr = str(op.get("attr_contains") or op.get("attribute") or "").strip()
                if needle_attr:
                    attrs = card_attr_blob(info, inst).lower()
                    opts = [x.strip() for x in needle_attr.split("|") if x.strip()]
                    if not any(any(k.lower() in attrs for k in attr_alias_keys(opt)) for opt in opts):
                        return False
                if name_needle:
                    opts = [x.strip() for x in name_needle.split("|") if x.strip()] or [name_needle]
                    if not any(_card_has_name(info, x) for x in opts):
                        return False
                if op.get("base_power_eq") is not None:
                    try:
                        base = int(str(info.get("power") or "0").split()[0].replace(",", "") or 0)
                    except (TypeError, ValueError):
                        base = 0
                    if base != int(op["base_power_eq"]):
                        return False
                return True

            def _attach_eligible() -> list[str]:
                out: list[str] = []
                excluded = {str(x) for x in (op.get("exclude_iids") or [])}
                lead_kinds = {
                    "own_leader_or_character",
                    "leader",
                    "all_own",
                    "opponent_leader_or_character",
                    "opponent_leader",
                }
                if tk in lead_kinds and _attach_char_ok(catalog(board.leader_card_id)):
                    if tk not in {"own_character", "opponent_character"} and "leader" not in excluded:
                        out.append("leader")
                if tk not in {"leader", "opponent_leader"}:
                    for c in board.characters:
                        if c.iid in excluded:
                            continue
                        if _attach_char_ok(catalog(c.card_id), c):
                            out.append(c.iid)
                return out

            # 「附加最多各1張…在自己的領航卡和自己全數的角色卡」
            if op.get("all") and not target and tk in {
                "own_leader_or_character",
                "own_characters",
                "all_own",
                "own_character",
            }:
                for tid in _attach_eligible():
                    if take_from_rested_pool:
                        if int(don_src.don_rested or 0) <= 0:
                            break
                        don_src.don_rested -= 1
                    elif take_from_active:
                        if int(don_src.don_active or 0) <= 0:
                            break
                        don_src.don_active -= 1
                    elif take_from_cost_area:
                        if int(don_src.don_active or 0) + int(don_src.don_rested or 0) <= 0:
                            break
                        if int(don_src.don_active or 0) > 0:
                            don_src.don_active -= 1
                        else:
                            don_src.don_rested -= 1
                    else:
                        if _don_room(don_src) <= 0:
                            break
                        don_src.don_given += 1
                    if tid == "leader":
                        board.leader_don += 1
                    else:
                        inst = next((c for c in board.characters if c.iid == tid), None)
                        if inst:
                            inst.don_attached += 1
                        else:
                            if take_from_rested_pool:
                                don_src.don_rested += 1
                            else:
                                don_src.don_given = max(0, int(don_src.don_given or 0) - 1)
                                don_src.don_rested += 1
                            continue
                    logs.append({"key": "play.log.attach_don", "name": player.username})
                continue

            if not target:
                if tk in {"self", ""} and source and source != "leader" and not to_opponent:
                    target = source
                elif tk in {"leader", "opponent_leader"}:
                    options = _attach_eligible()
                    if "leader" not in options:
                        if op.get("as_cost"):
                            return logs
                        continue
                    # Name-gated Leader (e.g. attach to Zoro Leader only).
                    if name_needle and not _attach_char_ok(catalog(board.leader_card_id)):
                        if op.get("as_cost"):
                            return logs
                        continue
                    target = "leader"
                elif tk in {
                    "own_character",
                    "own_leader_or_character",
                    "opponent_character",
                    "opponent_leader_or_character",
                }:
                    options = _attach_eligible()
                    if not options:
                        if op.get("as_cost"):
                            return logs
                        if not take_from_rested_pool and not to_opponent:
                            # Legacy: unused DON from deck lands rested in cost area.
                            don_src.don_given += n
                            don_src.don_rested += n
                            logs.append({"key": "play.log.gains_don", "name": player.username, "n": n})
                        continue
                    if (len(options) > 1 or op.get("optional", True)) and not state.pending_choice:
                        if to_opponent:
                            choice_tk = (
                                "opponent_leader_or_character"
                                if "leader" in options
                                else "opponent_character"
                            )
                        else:
                            choice_tk = (
                                "own_leader_or_character" if "leader" in options else "own_character"
                            )
                        state.pending_choice = PendingChoice(
                            seat=seat,
                            card_id=str(op.get("card_id") or ""),
                            source_iid=source,
                            target_kind=choice_tk,
                            options=options,
                            remaining_ops=[dict(op), *queue],
                            optional=bool(op.get("optional", True)),
                            summary=str(op.get("summary") or "Choose a Character to attach DON!!"),
                            purpose=purpose_from_op(op),
                        )
                        logs.append({"key": "play.log.choice_offer", "name": player.username})
                        return logs
                    target = options[0]
                else:
                    target = source or "leader"
            if take_from_rested_pool:
                don_src.don_rested -= n
            elif take_from_active:
                don_src.don_active -= n
            elif take_from_cost_area:
                take_a = min(n, int(don_src.don_active or 0))
                don_src.don_active -= take_a
                don_src.don_rested -= n - take_a
            else:
                don_src.don_given += n
            if target == "leader" or target.startswith("leader"):
                board.leader_don += n
            else:
                inst = next((c for c in board.characters if c.iid == target), None)
                if inst:
                    inst.don_attached += n
                else:
                    don_src.don_rested += n
            logs.append({"key": "play.log.attach_don", "name": player.username})
            # 「最多各2張…在最多2張」— re-queue remaining targets after one attach.
            try:
                targets_left = max(1, int(op.get("target_count") or 1))
            except (TypeError, ValueError):
                targets_left = 1
            if targets_left > 1:
                cont = {k: v for k, v in op.items() if k != "target_iid"}
                cont["target_count"] = targets_left - 1
                excl = list(cont.get("exclude_iids") or [])
                if target and target not in excl:
                    excl.append(target)
                cont["exclude_iids"] = excl
                queue.insert(0, cont)
        elif kind == "set_character_active":
            target = str(op.get("target_iid") or "")
            source = str(op.get("source_iid") or "")
            tk = str(op.get("target_kind") or "own_character")
            count = max(1, int(op.get("count") or 1))
            if op.get("all"):
                count = 20
            if not target:
                if tk == "self" and source:
                    target = source
                elif tk == "leader":
                    name_needle = str(op.get("name_contains") or "").strip()
                    if name_needle:
                        opts = [x.strip() for x in name_needle.split("|") if x.strip()] or [name_needle]
                        lead_info = catalog(player.leader_card_id)
                        if not any(_card_has_name(lead_info, n) for n in opts):
                            continue
                    if not player.leader_rested and not op.get("optional", True):
                        # Already active — still "set active" is a no-op success for mandatory.
                        pass
                    target = "leader"
                else:
                    from battle.engine import _info_has_trait, effective_character_cost

                    options = []
                    for c in player.characters:
                        if not c.rested:
                            continue
                        info = catalog(c.card_id)
                        trait = str(op.get("trait_contains") or "").strip()
                        if trait and not _info_has_trait(info, trait):
                            continue
                        name_needle = str(op.get("name_contains") or "").strip()
                        if name_needle:
                            name_opts = [x.strip() for x in name_needle.split("|") if x.strip()] or [name_needle]
                            blob = _card_name_blob(info)
                            if not any((n.lower() in blob) or _card_has_name(info, n) for n in name_opts):
                                continue
                        if op.get("cost_lte") is not None:
                            try:
                                cost = effective_character_cost(state, seat, c, catalog)
                            except Exception:
                                cost = _printed_cost(info)
                            if cost > int(op["cost_lte"]):
                                continue
                        if op.get("cost_gte") is not None:
                            try:
                                cost = effective_character_cost(state, seat, c, catalog)
                            except Exception:
                                cost = _printed_cost(info)
                            if cost < int(op["cost_gte"]):
                                continue
                        if op.get("cost_eq") is not None:
                            try:
                                cost = effective_character_cost(state, seat, c, catalog)
                            except Exception:
                                cost = _printed_cost(info)
                            if cost != int(op["cost_eq"]):
                                continue
                        if op.get("base_cost_lte") is not None:
                            printed = _printed_cost(info)
                            if printed > int(op["base_cost_lte"]):
                                continue
                        if op.get("base_cost_gte") is not None:
                            printed = _printed_cost(info)
                            if printed < int(op["base_cost_gte"]):
                                continue
                        if op.get("power_lte") is not None:
                            from battle.engine import inst_power

                            if inst_power(state, seat, c.iid, catalog) > int(op["power_lte"]):
                                continue
                        if op.get("power_gte") is not None:
                            from battle.engine import inst_power

                            if inst_power(state, seat, c.iid, catalog) < int(op["power_gte"]):
                                continue
                        attr_needle = str(op.get("attribute") or "").strip()
                        if attr_needle:
                            blob = card_attr_blob(info, c).lower()
                            opts = [a.strip().lower() for a in attr_needle.split("|") if a.strip()] or [
                                attr_needle.lower()
                            ]
                            if not any(any(k in blob for k in attr_alias_keys(o)) for o in opts):
                                continue
                        options.append(c.iid)
                    if op.get("include_leader") and player.leader_rested:
                        lead_info = catalog(player.leader_card_id)
                        trait = str(op.get("trait_contains") or "").strip()
                        ok_lead = True
                        if trait and not _info_has_trait(lead_info, trait):
                            ok_lead = False
                        if ok_lead and "leader" not in options:
                            options.append("leader")
                    if op.get("include_stage"):
                        for stg in player.stages:
                            if not stg.rested:
                                continue
                            st_info = catalog(stg.card_id)
                            trait = str(op.get("trait_contains") or "").strip()
                            if trait and not _info_has_trait(st_info, trait):
                                continue
                            if stg.iid not in options:
                                options.append(stg.iid)
                    if op.get("include_don") and int(player.don_rested or 0) > 0:
                        if "don" not in options:
                            options.append("don")
                    if not options:
                        continue
                    if op.get("all"):
                        activated = 0
                        if op.get("include_leader") and player.leader_rested:
                            player.leader_rested = False
                            activated += 1
                            logs.append({"key": "play.log.sets_active", "id": player.leader_card_id})
                        for iid in [x for x in options if x not in {"leader", "don"}]:
                            inst = next((c for c in player.characters if c.iid == iid), None)
                            if inst and inst.rested:
                                inst.rested = False
                                activated += 1
                                logs.append({"key": "play.log.sets_active", "id": inst.card_id})
                                continue
                            stg = next((s for s in player.stages if s.iid == iid), None)
                            if stg and stg.rested:
                                stg.rested = False
                                activated += 1
                                logs.append({"key": "play.log.sets_active", "id": stg.card_id})
                        if "don" in options and int(player.don_rested or 0) > 0:
                            n = int(player.don_rested or 0)
                            player.don_active = int(player.don_active or 0) + n
                            player.don_rested = 0
                            activated += n
                            logs.append({"key": "play.log.sets_active", "summary": f"don:{n}"})
                        continue
                    if len(options) > count and not state.pending_choice:
                        choice_tk = "own_character"
                        if any(x == "leader" for x in options) or any(
                            next((s for s in player.stages if s.iid == x), None) for x in options
                        ):
                            choice_tk = "own_leader_or_character"
                        state.pending_choice = PendingChoice(
                            seat=seat,
                            card_id=str(op.get("card_id") or ""),
                            source_iid=source,
                            target_kind=choice_tk,
                            options=options,
                            remaining_ops=[dict(op), *queue],
                            optional=bool(op.get("optional", True)),
                            summary="Choose a card to set active",
                            purpose=purpose_from_op(op),
                        )
                        logs.append({"key": "play.log.choice_offer", "name": player.username})
                        return logs
                    target = options[0]
            if target == "leader" or target == f"leader-{seat}":
                player.leader_rested = False
                setattr(player, "_last_set_active_iid", "leader")
                logs.append({"key": "play.log.sets_active", "id": player.leader_card_id})
            elif target == "don":
                n = min(1, int(player.don_rested or 0))
                if n:
                    player.don_rested -= n
                    player.don_active = int(player.don_active or 0) + n
                    setattr(player, "_last_set_active_iid", "don")
                    logs.append({"key": "play.log.sets_active", "summary": "don:1"})
            else:
                inst = next((c for c in player.characters if c.iid == target), None)
                if inst:
                    inst.rested = False
                    setattr(player, "_last_set_active_iid", target)
                    logs.append({"key": "play.log.sets_active", "id": inst.card_id})
                else:
                    stg = next((s for s in player.stages if s.iid == target), None)
                    if stg:
                        stg.rested = False
                        setattr(player, "_last_set_active_iid", target)
                        logs.append({"key": "play.log.sets_active", "id": stg.card_id})
        elif kind == "grant_keyword":
            kw = str(op.get("keyword") or "").strip().lower()
            if not kw:
                continue
            source = str(op.get("source_iid") or "")
            target = str(op.get("target_iid") or "")
            if op.get("same_target_as_prior") and not target:
                prior = str(
                    getattr(player, "_last_set_active_iid", "")
                    or getattr(player, "_last_buff_target_iid", "")
                    or ""
                )
                if not prior:
                    continue
                target = prior
            tk = str(op.get("target_kind") or "self")
            duration = str(op.get("duration") or "turn").strip().lower()
            # Schema used to default missing duration to "permanent", which made
            # On Play "gains Unblockable this turn" stick forever on the target.
            # Keep explicit permanent only for continuous auras (all / self-only).
            if (
                kw == "blockerless"
                and duration == "permanent"
                and not op.get("all")
                and tk in {"own_character", "own_characters"}
            ):
                duration = "turn"
            count = max(1, min(20, int(op.get("count") or 1)))
            if op.get("all"):
                count = 20
            name_needle = str(op.get("name_contains") or "").strip()
            excl_needle = str(op.get("exclude_name") or "").strip()
            trait_needle = str(op.get("trait_contains") or op.get("trait_includes") or "").strip()
            color_needle = str(op.get("color") or "").strip().lower()
            candidates: list[str] = []
            if target:
                candidates = [target]
            elif tk == "self" and source:
                candidates = [source]
            else:
                from battle.engine import effective_character_cost, inst_power

                filtered = bool(
                    name_needle
                    or trait_needle
                    or excl_needle
                    or color_needle
                    or tk in {"own_character", "own_characters"}
                    or op.get("cost_lte") is not None
                    or op.get("cost_gte") is not None
                    or op.get("cost_eq") is not None
                    or op.get("power_gte") is not None
                    or op.get("power_lte") is not None
                    or op.get("require_no_on_play")
                    or op.get("require_no_when_attacking")
                    or op.get("require_no_effect")
                    or op.get("exclude_self")
                    or op.get("all")
                    or op.get("name_or_trait")
                    or op.get("trait_any")
                    or op.get("trait_all")
                )
                if filtered:
                    for ch in player.characters:
                        if op.get("exclude_self") and source and ch.iid == source:
                            continue
                        info = catalog(ch.card_id)
                        cost = None
                        live = None
                        if op.get("cost_lte") is not None or op.get("cost_gte") is not None or op.get("cost_eq") is not None:
                            try:
                                cost = effective_character_cost(state, seat, ch, catalog)
                            except Exception:
                                cost = _printed_cost(info)
                        if op.get("power_gte") is not None or op.get("power_lte") is not None:
                            try:
                                live = inst_power(state, seat, ch.iid, catalog)
                            except Exception:
                                live = _printed_power(info)
                        if _grant_keyword_char_ok(op, info, live_power=live, cost=cost):
                            candidates.append(ch.iid)
            if (
                op.get("optional", bool(name_needle or trait_needle or excl_needle or color_needle or op.get("require_no_on_play") or op.get("require_no_when_attacking") or op.get("cost_lte") is not None))
                and not target
                and not op.get("all")
                and candidates
                and (len(candidates) > count or bool(op.get("optional")))
                and not state.pending_choice
            ):
                state.pending_choice = PendingChoice(
                    seat=seat,
                    card_id=str(op.get("card_id") or ""),
                    source_iid=source,
                    target_kind="own_character",
                    options=list(candidates),
                    remaining_ops=[dict(op), *queue],
                    optional=True,
                    summary=grant_keyword_choice_summary(op),
                    purpose="grant_keyword",
                )
                logs.append({"key": "play.log.choice_offer", "name": player.username})
                return logs
            if (
                op.get("optional", bool(name_needle or trait_needle or excl_needle or color_needle))
                and not target
                and not candidates
                and tk not in {"leader", "own_leader"}
            ):
                continue
            # Leader grants (e.g. Event Main → Leader gains blockerless this turn).
            if tk in {"leader", "own_leader"} or target in {"leader", f"leader-{seat}"}:
                lead_info = catalog(player.leader_card_id)
                if name_needle:
                    name_opts = [x.strip() for x in name_needle.split("|") if x.strip()] or [name_needle]
                    blob = _card_name_blob(lead_info)
                    if not any((n.lower() in blob) or _card_has_name(lead_info, n) for n in name_opts):
                        continue
                if _duration_is_until_opp_end(duration):
                    existing = {str(e.get("keyword") or "") for e in player.leader_keywords_until_end}
                    if kw not in existing:
                        player.leader_keywords_until_end.append(
                            {"keyword": kw, "expire_seat": _opp_end_expire_seat(seat)}
                        )
                        logs.append(
                            {
                                "key": "play.log.effect_applied",
                                "id": player.leader_card_id,
                                "summary": f"+{kw}",
                            }
                        )
                else:
                    if kw not in player.leader_turn_keywords:
                        player.leader_turn_keywords.append(kw)
                        logs.append(
                            {
                                "key": "play.log.effect_applied",
                                "id": player.leader_card_id,
                                "summary": f"+{kw}",
                            }
                        )
                continue
            # Single candidate with optional name grant: still apply (may activate).
            for iid in (candidates[:count] if candidates else ([source] if source and tk == "self" else [])):
                if iid == "leader" or iid == f"leader-{seat}":
                    bucket = player.leader_turn_keywords
                    if kw not in bucket:
                        bucket.append(kw)
                        logs.append(
                            {
                                "key": "play.log.effect_applied",
                                "id": player.leader_card_id,
                                "summary": f"+{kw}",
                            }
                        )
                    continue
                inst = next((c for c in player.characters if c.iid == iid), None)
                if not inst:
                    continue
                if _duration_is_until_opp_end(duration):
                    existing = {str(e.get("keyword") or "") for e in inst.keywords_until_end}
                    if kw not in existing:
                        inst.keywords_until_end.append(
                            {"keyword": kw, "expire_seat": _opp_end_expire_seat(seat)}
                        )
                        logs.append({"key": "play.log.effect_applied", "id": inst.card_id, "summary": f"+{kw}"})
                else:
                    bucket = inst.turn_keywords if duration in {"turn", "next_turn", "battle"} else inst.keywords
                    if duration == "next_turn":
                        bucket = inst.turn_keywords
                    if kw not in bucket:
                        bucket.append(kw)
                        if kw in {"rush", "rush_character"} and duration in {"turn", "next_turn", "battle"}:
                            inst.summoning_sick = False
                        logs.append({"key": "play.log.effect_applied", "id": inst.card_id, "summary": f"+{kw}"})
        elif kind == "grant_attribute":
            from battle.engine import _info_has_trait

            attr = str(op.get("attribute") or "").strip()
            if not attr:
                continue
            # Canonicalize to English primary token when possible.
            canon = attr_alias_keys(attr)[0]
            source = str(op.get("source_iid") or "")
            target = str(op.get("target_iid") or "")
            tk = str(op.get("target_kind") or "self")
            duration = str(op.get("duration") or "turn").strip().lower()
            count = max(1, min(5, int(op.get("count") or 1)))
            name_needle = str(op.get("name_contains") or "").strip()
            trait_needle = str(op.get("trait_contains") or "").strip()
            candidates: list[str] = []
            if target:
                candidates = [target]
            elif tk == "self" and source:
                candidates = [source]
            else:
                for ch in player.characters:
                    info = catalog(ch.card_id)
                    if name_needle:
                        name_opts = [x.strip() for x in name_needle.split("|") if x.strip()] or [name_needle]
                        if not any(_card_has_name(info, n) for n in name_opts):
                            continue
                    if trait_needle and not _info_has_trait(info, trait_needle):
                        continue
                    candidates.append(ch.iid)
            if (
                op.get("optional", bool(name_needle or trait_needle))
                and not target
                and len(candidates) > count
                and not state.pending_choice
            ):
                state.pending_choice = PendingChoice(
                    seat=seat,
                    card_id=str(op.get("card_id") or ""),
                    source_iid=source,
                    target_kind="own_character",
                    options=list(candidates),
                    remaining_ops=[dict(op), *queue],
                    optional=True,
                    summary=str(op.get("summary") or f"Grant {attr}"),
                purpose=purpose_from_op(op),
            )
                logs.append({"key": "play.log.choice_offer", "name": player.username})
                return logs
            if not candidates and tk == "self" and source:
                candidates = [source]
            for iid in candidates[:count]:
                inst = next((c for c in player.characters if c.iid == iid), None)
                if not inst:
                    continue
                bucket = (
                    inst.turn_attributes
                    if duration in {"turn", "until_opp_turn_end", "next_turn", "battle"}
                    else inst.granted_attributes
                )
                if canon not in [a.lower() for a in bucket]:
                    bucket.append(canon)
                    logs.append(
                        {
                            "key": "play.log.effect_applied",
                            "id": inst.card_id,
                            "summary": f"+attr:{canon}",
                        }
                    )
        elif kind in {"cannot_be_ko", "cannot_be_removed", "cannot_be_rested"}:
            source = str(op.get("source_iid") or "")
            target = str(op.get("target_iid") or source)
            traits = [str(t) for t in (op.get("trait_any") or []) if str(t).strip()]
            if not traits and op.get("trait_contains"):
                traits = [str(op.get("trait_contains"))]
            excl = str(op.get("exclude_name") or "").strip()
            any_leave = kind == "cannot_be_removed" or bool(op.get("any_leave"))
            tk = str(op.get("target_kind") or "self")
            from battle.engine import _info_has_trait

            def _mark(inst: CardInst) -> None:
                info = catalog(inst.card_id)
                if traits and not any(_info_has_trait(info, t) for t in traits):
                    return
                color = str(op.get("color") or "").strip().lower()
                if color:
                    blob = _card_color_blob(info)
                    if not any(a.lower() in blob for a in _color_aliases(color)):
                        return
                if excl and _card_excluded_by_name(info, excl):
                    return
                if op.get("cost_lte") is not None and _printed_cost(info) > int(op["cost_lte"]):
                    return
                if op.get("cost_gte") is not None and _printed_cost(info) < int(op["cost_gte"]):
                    return
                if op.get("cost_eq") is not None and _printed_cost(info) != int(op["cost_eq"]):
                    return
                if kind == "cannot_be_rested":
                    inst.cannot_be_rested = True
                    logs.append({"key": "play.log.effect_applied", "id": inst.card_id, "summary": "cannot_be_rested"})
                    return
                if any_leave:
                    inst.cannot_be_removed = True
                    logs.append(
                        {
                            "key": "play.log.effect_applied",
                            "id": inst.card_id,
                            "summary": "cannot_be_removed",
                        }
                    )
                    return
                inst.cannot_be_ko = True
                logs.append(
                    {
                        "key": "play.log.effect_applied",
                        "id": inst.card_id,
                        "summary": "cannot_be_ko",
                    }
                )

            if tk in {"opponent_character", "opponent_characters"} or (
                op.get("all") and "opponent" in tk
            ):
                for ch in foe.characters:
                    _mark(ch)
            elif op.get("all") or (tk in {"own_character", "own_characters"} and not str(op.get("target_iid") or "")):
                for ch in player.characters:
                    _mark(ch)
            else:
                inst = next((c for c in player.characters if c.iid == target), None)
                if inst:
                    _mark(inst)
        elif kind == "deny_blocker":
            target = str(op.get("target_iid") or "")
            tk = str(op.get("target_kind") or "").strip().lower()
            # 「最多1張」targeted deny: pick one Character (optionally power-gated).
            if tk and not target:
                filters: dict[str, Any] = {}
                for key in ("power_lte", "power_gte", "cost_lte", "cost_eq", "cost_gte"):
                    if op.get(key) is not None:
                        filters[key] = op[key]
                options = _choice_options(state, seat, tk, catalog, filters or None)
                if not options:
                    continue
                if len(options) == 1 and not op.get("optional", True):
                    target = options[0]
                elif not state.pending_choice:
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind=tk,
                        options=options,
                        remaining_ops=[dict(op), *queue],
                        optional=bool(op.get("optional", True)),
                        summary=str(op.get("summary") or "Choose a Character that cannot Block"),
                        purpose=purpose_from_op(op),
                    )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                else:
                    continue
            entry: dict[str, Any] = {
                "duration": str(op.get("duration") or "battle"),
            }
            if target:
                entry["target_iid"] = target
            if op.get("when_leader_attacks"):
                entry["when_leader_attacks"] = True
            if op.get("base_cost_lte") is not None:
                entry["base_cost_lte"] = int(op["base_cost_lte"])
            if op.get("base_cost_gte") is not None:
                entry["base_cost_gte"] = int(op["base_cost_gte"])
            # Global power/cost gates only when not locking a specific target.
            if not target:
                if op.get("power_lte") is not None:
                    entry["power_lte"] = int(op["power_lte"])
                if op.get("power_gte") is not None:
                    entry["power_gte"] = int(op["power_gte"])
                for key in ("cost_lte", "cost_eq", "cost_gte"):
                    if op.get(key) is not None:
                        entry[key] = int(op[key])
            player.deny_blocker.append(entry)
            logs.append({"key": "play.log.effect_applied", "summary": "deny_blocker"})
        elif kind == "allow_attack_active":
            from battle.engine import _info_has_trait

            target = str(op.get("target_iid") or "")
            trait = str(op.get("trait_contains") or "").strip()
            tk = str(op.get("target_kind") or "own_character")
            source = str(op.get("source_iid") or "")
            count = max(1, int(op.get("count") or 1))
            candidates: list[str] = []
            if target:
                candidates = [target]
            elif tk == "self" and source:
                candidates = [source]
            elif tk in {"leader", "own_leader"}:
                candidates = ["leader"]
            else:
                for ch in player.characters:
                    if trait and not _info_has_trait(catalog(ch.card_id), trait):
                        continue
                    candidates.append(ch.iid)
                if tk in {"own_leader_or_character", "leader_or_character"}:
                    if not trait or _info_has_trait(catalog(player.leader_card_id), trait):
                        candidates.append("leader")
            if (
                op.get("optional", True)
                and not target
                and candidates
                and not state.pending_choice
            ):
                state.pending_choice = PendingChoice(
                    seat=seat,
                    card_id=str(op.get("card_id") or ""),
                    source_iid=source,
                    target_kind="own_character",
                    options=list(candidates),
                    remaining_ops=[dict(op), *queue],
                    optional=True,
                    summary=str(op.get("summary") or "Choose character that can attack active"),
                purpose=purpose_from_op(op),
            )
                logs.append({"key": "play.log.choice_offer", "name": player.username})
                return logs
            for iid in candidates[:count]:
                if iid not in player.attack_active_iids:
                    player.attack_active_iids.append(iid)
            if candidates:
                logs.append({"key": "play.log.effect_applied", "summary": "allow_attack_active"})
        elif kind == "return_to_bottom":
            # Two modes:
            # 1) Field Character/Stage → owner's deck bottom
            # 2) Legacy: cards from hand → your deck bottom
            target = str(op.get("target_iid") or "")
            field_mode = bool(
                op.get("target_kind")
                or op.get("cost_lte") is not None
                or op.get("cost_eq") is not None
                or op.get("power_lte") is not None
                or op.get("base_power_lte") is not None
                or op.get("base_cost_lte") is not None
                or op.get("all")
            )
            if field_mode or target:
                tk = str(op.get("target_kind") or "any_character")
                if op.get("all") and not target:
                    from battle.engine import effective_character_cost

                    def _ok_char(owner_seat: int, c: CardInst) -> bool:
                        info = catalog(c.card_id)
                        try:
                            cost = effective_character_cost(state, owner_seat, c, catalog)
                        except Exception:
                            cost = _printed_cost(info)
                        printed = _printed_cost(info)
                        if op.get("cost_lte") is not None and cost > int(op["cost_lte"]):
                            return False
                        if op.get("cost_eq") is not None and cost != int(op["cost_eq"]):
                            return False
                        if op.get("cost_gte") is not None and cost < int(op["cost_gte"]):
                            return False
                        if op.get("base_cost_lte") is not None and printed > int(op["base_cost_lte"]):
                            return False
                        if op.get("base_cost_eq") is not None and printed != int(op["base_cost_eq"]):
                            return False
                        if op.get("exclude_self") and str(op.get("source_iid") or "") == c.iid:
                            return False
                        return True

                    victims: list[tuple[Any, CardInst]] = []
                    if tk in {"any_character", "all", "all_characters"} or not tk:
                        for own_seat, owner in ((seat, player), (state.other(seat), foe)):
                            for c in list(owner.characters):
                                if _ok_char(own_seat, c):
                                    victims.append((owner, c))
                    elif tk.startswith("own"):
                        for c in list(player.characters):
                            if _ok_char(seat, c):
                                victims.append((player, c))
                    elif tk.startswith("opponent"):
                        for c in list(foe.characters):
                            if _ok_char(state.other(seat), c):
                                victims.append((foe, c))
                    for owner, hit in victims:
                        if getattr(hit, "cannot_be_removed", False) and owner.seat != seat:
                            continue
                        from battle.leave_replace import try_replace_leave

                        if try_replace_leave(
                            state,
                            owner.seat,
                            hit,
                            by_opponent=owner.seat != seat,
                            catalog=catalog,
                            by_ko=False,
                        ):
                            if _halt_for_replace("bottom"):
                                return logs
                            logs.append({"key": "play.log.effect_applied", "summary": "replace_leave"})
                            continue
                        if hit.don_attached:
                            owner.don_rested += hit.don_attached
                            hit.don_attached = 0
                        owner.characters = [c for c in owner.characters if c.iid != hit.iid]
                        owner.deck.append(hit.card_id)
                        logs.append({"key": "play.log.return_bottom_char", "id": hit.card_id, "name": owner.username})
                        try:
                            from battle.engine import fire_own_trait_leave_or_ko

                            fire_own_trait_leave_or_ko(
                                state,
                                owner.seat,
                                hit.card_id,
                                catalog,
                                by_opponent_effect=owner.seat != seat,
                                by_ko=False,
                            )
                        except Exception:
                            pass
                    continue
                if tk == "own_stage" and not target:
                    filters: dict[str, Any] = {}
                    if op.get("cost_lte") is not None:
                        filters["cost_lte"] = op["cost_lte"]
                    if op.get("cost_eq") is not None:
                        filters["cost_eq"] = op["cost_eq"]
                    options = _choice_options(state, seat, "own_stage", catalog, filters or None)
                    if not options:
                        if op.get("as_cost"):
                            return logs
                        continue
                    if len(options) == 1 and not op.get("optional"):
                        target = options[0]
                    elif not state.pending_choice:
                        state.pending_choice = PendingChoice(
                            seat=seat,
                            card_id=str(op.get("card_id") or ""),
                            source_iid=str(op.get("source_iid") or ""),
                            target_kind="own_stage",
                            options=options,
                            remaining_ops=[dict(op), *queue],
                            optional=bool(op.get("optional", True)),
                            summary=str(op.get("summary") or "Choose a Stage to put on bottom"),
                purpose=purpose_from_op(op),
            )
                        logs.append({"key": "play.log.choice_offer", "name": player.username})
                        return logs
                    else:
                        continue
                if not target:
                    filters = {}
                    if op.get("cost_lte") is not None:
                        filters["cost_lte"] = op["cost_lte"]
                    if op.get("cost_eq") is not None:
                        filters["cost_eq"] = op["cost_eq"]
                    if op.get("cost_gte") is not None:
                        filters["cost_gte"] = op["cost_gte"]
                    if op.get("base_cost_lte") is not None:
                        filters["base_cost_lte"] = op["base_cost_lte"]
                    if op.get("power_lte") is not None:
                        filters["power_lte"] = op["power_lte"]
                    if op.get("base_power_lte") is not None:
                        filters["base_power_lte"] = op["base_power_lte"]
                    if op.get("trait_contains"):
                        filters["trait_contains"] = op["trait_contains"]
                    if op.get("name_contains"):
                        filters["name_contains"] = op["name_contains"]
                    options = _choice_options(state, seat, tk, catalog, filters or None)
                    if op.get("exclude_self"):
                        src = str(op.get("source_iid") or "")
                        options = [i for i in options if i != src]
                    if not options:
                        if op.get("as_cost"):
                            return logs
                        continue
                    if len(options) == 1 and not op.get("optional"):
                        target = options[0]
                    elif not state.pending_choice:
                        state.pending_choice = PendingChoice(
                            seat=seat,
                            card_id=str(op.get("card_id") or ""),
                            source_iid=str(op.get("source_iid") or ""),
                            target_kind=tk,
                            options=options,
                            remaining_ops=[dict(op), *queue],
                            optional=bool(op.get("optional", True)),
                            summary=str(op.get("summary") or "Choose a Character to put on the bottom of the deck"),
                purpose=purpose_from_op(op),
            )
                        logs.append({"key": "play.log.choice_offer", "name": player.username})
                        return logs
                    else:
                        continue
                placed = False
                # Stages first
                for owner in (player, foe):
                    hit_s = next((s for s in owner.stages if s.iid == target), None)
                    if hit_s:
                        owner.stages = [s for s in owner.stages if s.iid != hit_s.iid]
                        owner.deck.append(hit_s.card_id)
                        logs.append({"key": "play.log.return_bottom_char", "id": hit_s.card_id, "name": owner.username})
                        placed = True
                        break
                if not placed:
                    for owner in (player, foe):
                        hit = next((c for c in owner.characters if c.iid == target), None)
                        if not hit:
                            continue
                        if getattr(hit, "cannot_be_removed", False) and owner.seat != seat:
                            logs.append({"key": "play.log.effect_unsupported", "id": "cannot_be_removed"})
                            placed = True
                            break
                        from battle.leave_replace import try_replace_leave

                        if try_replace_leave(
                            state,
                            owner.seat,
                            hit,
                            by_opponent=owner.seat != seat,
                            catalog=catalog,
                            by_ko=False,
                        ):
                            if _halt_for_replace("bottom"):
                                return logs
                            logs.append({"key": "play.log.effect_applied", "summary": "replace_leave"})
                            placed = True
                            break
                        if hit.don_attached:
                            owner.don_rested += hit.don_attached
                            hit.don_attached = 0
                        owner.characters = [c for c in owner.characters if c.iid != hit.iid]
                        owner.deck.append(hit.card_id)
                        logs.append({"key": "play.log.return_bottom_char", "id": hit.card_id, "name": owner.username})
                        try:
                            from battle.engine import fire_own_trait_leave_or_ko

                            fire_own_trait_leave_or_ko(
                                state,
                                owner.seat,
                                hit.card_id,
                                catalog,
                                by_opponent_effect=owner.seat != seat,
                                by_ko=False,
                            )
                        except Exception:
                            pass
                        placed = True
                        break
                if not placed:
                    if op.get("as_cost"):
                        return logs
                    continue
            else:
                n = max(1, min(5, int(op.get("count") or 1)))
                moved = 0
                for _ in range(n):
                    if not player.hand:
                        break
                    player.deck.append(player.hand.pop())
                    moved += 1
                if moved:
                    logs.append({"key": "play.log.return_bottom", "name": player.username, "n": moved})
        elif kind == "add_life":
            n = max(1, int(op.get("count") or 1))
            pos = str(op.get("position") or "bottom").strip().lower()
            # 「卡組上面」is fixed — never ask which card. Optionality belongs on as_cost trash /
            # may_activate, not a second deck-top confirm (OP15-113).
            face_up = str(op.get("face") or "down").strip().lower() == "up"
            top = pos == "top"
            added = 0
            for _ in range(n):
                if not player.deck:
                    break
                cid = player.deck.pop(0)
                _place_cid_on_life(player, cid, top=top, face_up=face_up)
                added += 1
            if added:
                logs.append({"key": "play.log.add_life", "name": player.username, "n": added})
        elif kind == "deal_life_damage":
            # Simplified: move top life to hand (no trigger pause mid-op batch).
            n = max(1, int(op.get("count") or 1))
            victim = player if str(op.get("owner") or "opponent") == "self" else foe
            if op.get("optional") and not str(op.get("target_iid") or ""):
                if not victim.life:
                    continue
                if not state.pending_choice:
                    nxt = dict(op)
                    nxt["optional"] = False
                    nxt["target_iid"] = "life:damage"
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind="life",
                        options=["life:damage"],
                        remaining_ops=[nxt, *queue],
                        optional=True,
                        summary=str(op.get("summary") or "Deal 1 damage to opponent"),
                        purpose="life",
                    )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
            dealt = 0
            for _ in range(n):
                if not victim.life:
                    break
                cid = victim.life.pop(0)
                if victim.life_face:
                    victim.life_face.pop(0)
                victim.hand.append(cid)
                dealt += 1
            while len(victim.life_face) > len(victim.life):
                victim.life_face.pop()
            while len(victim.life_face) < len(victim.life):
                victim.life_face.append(False)
            if dealt:
                logs.append({"key": "play.log.life_taken", "name": victim.username, "left": len(victim.life)})
        elif kind == "choose_target":
            if state.pending_choice:
                continue
            options = _choice_options(state, seat, str(op.get("target_kind") or "opponent_character"))
            if not options:
                continue
            then_op = op.get("then_op") if isinstance(op.get("then_op"), dict) else None
            state.pending_choice = PendingChoice(
                seat=seat,
                card_id=str(op.get("card_id") or ""),
                source_iid=str(op.get("source_iid") or ""),
                target_kind=str(op.get("target_kind") or "opponent_character"),
                options=options,
                remaining_ops=list(queue),
                optional=bool(op.get("optional", True)),
                summary=str(op.get("summary") or "Choose a target"),
                then_op=then_op,
                purpose=purpose_from_op(op),
            )
            logs.append({"key": "play.log.choice_offer", "name": player.username})
            return logs
        elif kind == "search_deck":
            # Interactive: reveal top N and let the player choose eligible cards.
            if state.pending_search:
                continue
            op = _enrich_search_op_from_card(op, catalog)
            # New search supersedes prior add disclosure.
            state.public_search_adds = None
            needle_name = str(op.get("name_contains") or "").strip().lower()
            needle_trait = str(op.get("trait_contains") or "").strip().lower()
            trait_any = [str(x).strip().lower() for x in (op.get("trait_any") or []) if str(x).strip()]
            if trait_any:
                needle_trait = "|".join([needle_trait] + trait_any) if needle_trait else "|".join(trait_any)
            cost_eq = op.get("cost_eq")
            cost_lte = op.get("cost_lte")
            cost_gte = op.get("cost_gte")
            power_lte = op.get("power_lte")
            power_gte = op.get("power_gte")
            power_eq = op.get("power_eq")
            require_trigger = bool(op.get("require_trigger"))
            needle_attr = str(op.get("attr_contains") or op.get("attribute") or "").strip().lower()
            needle_color = str(op.get("color") or "").strip().lower()
            exclude_needles = _search_exclude_needles(op, catalog)
            top_n = max(1, int(op.get("top_n") or 5))
            max_add = max(1, int(op.get("max_add") or 1))
            destination = str(op.get("destination") or "hand").lower()
            trash_rest = bool(op.get("trash_rest"))
            take = min(top_n, len(player.deck))
            revealed = [player.deck.pop(0) for _ in range(take)]

            def _matches(card_id: str) -> bool:
                info = catalog(card_id)
                attrs = card_attr_blob(info).lower()
                if exclude_needles and any(_card_has_name(info, n) for n in exclude_needles):
                    return False
                if require_trigger and not card_has_trigger(info):
                    return False
                name_ok = (not needle_name) or _card_matches_name_contains(info, needle_name)
                is_event = card_type_of(info) == "event"
                event_ok = bool(op.get("or_event")) and is_event
                if event_ok and needle_color:
                    blob = _card_color_blob(info)
                    event_ok = any(a.lower() in blob for a in _color_aliases(needle_color))
                trait_ok = True
                if needle_trait:
                    from battle.engine import _info_has_trait

                    trait_ok = _info_has_trait(info, needle_trait)
                attr_opts = [x.strip().lower() for x in needle_attr.split("|") if x.strip()] if needle_attr else []
                attr_ok = (not attr_opts) or any(
                    any(k in attrs for k in attr_alias_keys(a)) for a in attr_opts
                )
                color_ok = True
                if needle_color and not (op.get("or_event") and (needle_attr or needle_name)):
                    # Color gate applies to all cards unless used as the Event branch of an OR search.
                    blob = _card_color_blob(info)
                    color_ok = any(a.lower() in blob for a in _color_aliases(needle_color))
                if op.get("name_or_trait") and (needle_name or needle_trait):
                    if not (name_ok or trait_ok):
                        return False
                else:
                    if op.get("or_event") and needle_attr:
                        if not (attr_ok or event_ok):
                            return False
                    elif needle_name and op.get("or_event"):
                        if not (name_ok or event_ok):
                            return False
                    elif needle_name and not name_ok:
                        return False
                    if needle_trait and not trait_ok:
                        return False
                    if needle_attr and not op.get("or_event") and not attr_ok:
                        return False
                if not color_ok:
                    return False
                if cost_eq is not None and _printed_cost(info) != int(cost_eq):
                    return False
                if cost_lte is not None and _printed_cost(info) > int(cost_lte):
                    return False
                if cost_gte is not None and _printed_cost(info) < int(cost_gte):
                    return False
                # Power gates apply to non-Event cards (Events usually have no power).
                if not is_event:
                    try:
                        pow_v = int(str(info.get("power") or 0).split()[0].replace(",", "") or 0)
                    except (TypeError, ValueError):
                        pow_v = 0
                    if power_lte is not None and pow_v > int(power_lte):
                        return False
                    if power_gte is not None and pow_v < int(power_gte):
                        return False
                    if power_eq is not None and pow_v != int(power_eq):
                        return False
                want_type = str(op.get("card_type") or "").lower()
                if want_type and want_type not in {"any", "*"}:
                    if op.get("or_event") and want_type == "character":
                        if not ((card_type_of(info) == "character") or event_ok):
                            return False
                    elif card_type_of(info) != want_type:
                        return False
                elif destination == "play":
                    if card_type_of(info) != "character":
                        return False
                return True

            if (
                needle_name
                or needle_trait
                or cost_eq is not None
                or cost_lte is not None
                or cost_gte is not None
                or power_lte is not None
                or power_gte is not None
                or power_eq is not None
                or exclude_needles
                or require_trigger
                or destination == "play"
                or op.get("card_type")
                or op.get("color")
                or needle_attr
                or op.get("or_event")
                or op.get("name_or_trait")
            ):
                eligible = [i for i, cid in enumerate(revealed) if _matches(cid)]
                reveal_adds = True
            else:
                eligible = list(range(len(revealed)))
                # Explicit override; default False for unrestricted look.
                reveal_adds = bool(op.get("reveal_adds", False))
            if op.get("reveal_adds") is False:
                reveal_adds = False
            if op.get("reveal_adds") is True:
                reveal_adds = True
            state.pending_search = PendingSearch(
                seat=seat,
                card_id=str(op.get("card_id") or ""),
                source_iid=str(op.get("source_iid") or ""),
                revealed=revealed,
                eligible=eligible,
                max_add=max_add,
                trait_contains=str(op.get("trait_contains") or ""),
                name_contains=str(op.get("name_contains") or ""),
                card_type=str(op.get("card_type") or ""),
                summary=str(op.get("summary") or ""),
                remaining_ops=list(queue),
                phase="pick",
                # trash_rest overrides bottom ordering (paper: 其餘放到廢棄區).
                order_bottom=False if trash_rest else bool(op.get("order_bottom", True)),
                exclude_name=str(op.get("exclude_name") or (exclude_needles[0] if exclude_needles else "")),
                destination=destination if destination in {"hand", "play", "life"} else "hand",
                face=str(op.get("face") or "down"),
                trash_rest=trash_rest,
                reveal_adds=reveal_adds,
                to_top_or_bottom=bool(op.get("to_top_or_bottom")),
                order_dest="bottom" if not op.get("to_top_or_bottom") else "",
            )
            logs.append({"key": "play.log.search_offer", "name": player.username, "n": len(revealed)})
            # Pause; remaining ops resume after search resolves.
            return logs
        elif kind == "play_from_hand":
            if state.pending_choice:
                continue
            setattr(player, "_last_play_from_hand_count", 0)
            want_type = str(op.get("card_type") or "character").lower()
            zone = str(op.get("from_zone") or "hand").lower()
            hand_owner = foe if str(op.get("owner") or "self") == "opponent" else player
            play_seat = hand_owner.seat
            # Resolve dynamic cost cap from opponent field DON!! count.
            if op.get("cost_lte_opp_don_field"):
                from battle.engine import _don_on_field

                op = dict(op)
                op["cost_lte"] = int(_don_on_field(foe))
            if op.get("cost_lte_own_don_field"):
                from battle.engine import _don_on_field

                op = dict(op)
                op["cost_lte"] = int(_don_on_field(player))
            # Play this exact source card (On K.O. revival, Trigger 「使這張卡片登場」).
            if op.get("self_card"):
                cid = str(op.get("card_id") or "")
                token = ""
                if cid and zone in {"hand", "hand_or_trash"} and cid in player.hand:
                    idx = player.hand.index(cid)
                    token = f"hand:{idx}:{cid}"
                elif cid and cid in player.trash:
                    idx = len(player.trash) - 1 - player.trash[::-1].index(cid)
                    token = f"trash:{idx}:{cid}"
                elif cid and cid in player.hand:
                    idx = player.hand.index(cid)
                    token = f"hand:{idx}:{cid}"
                if not token:
                    continue
                if want_type == "character" and len(player.characters) >= 5:
                    options = [c.iid for c in player.characters]
                    if not options:
                        continue
                    state.pending_choice = PendingChoice(
                        seat=seat,
                        card_id=str(op.get("card_id") or ""),
                        source_iid=str(op.get("source_iid") or ""),
                        target_kind="own_character",
                        options=options,
                        remaining_ops=list(queue),
                        optional=bool(op.get("optional", True)),
                        summary="Choose a Character to trash for space",
                        purpose="replace",
                        then_op={
                            "op": "play_token_after_replace",
                            "token": token,
                            "as_rested": bool(op.get("as_rested")),
                        },
                    )
                    logs.append({"key": "play.log.choice_offer", "name": player.username})
                    return logs
                try:
                    from battle.engine import _effect_play_from_hand_token

                    src = str(op.get("source_iid") or "")
                    by_char = bool(src and src != "leader" and any(c.iid == src for c in player.characters))
                    played = _effect_play_from_hand_token(
                        state,
                        seat,
                        token,
                        catalog,
                        as_rested=bool(op.get("as_rested")),
                        by_character_effect=by_char,
                    )
                except Exception:
                    continue
                if played.get("ok"):
                    logs.extend(played.get("logs") or [])
                continue
            options: list[str] = []
            board_full = want_type == "character" and len(hand_owner.characters) >= 5
            if zone in {"hand", "hand_or_trash"}:
                for i, cid in enumerate(hand_owner.hand):
                    info = catalog(cid)
                    if not _hand_card_matches_play_op(info, op):
                        continue
                    options.append(f"hand:{i}:{cid}")
            if zone in {"trash", "hand_or_trash"}:
                for i, cid in enumerate(hand_owner.trash):
                    info = catalog(cid)
                    if not _hand_card_matches_play_op(info, op):
                        continue
                    options.append(f"trash:{i}:{cid}")
            if not options:
                continue
            summary = str(op.get("summary") or ("Play a Character (choose replace)" if board_full else "Play a Character"))
            rem_count = max(0, int(op.get("count") or 1) - 1)
            cont_ops: list[dict[str, Any]] = []
            if rem_count > 0:
                cont = dict(op)
                cont["count"] = rem_count
                cont["optional"] = True
                cont_ops.append(cont)
            then = {
                "op": "play_from_hand",
                "card_type": want_type,
                "count": 1,
                "optional": True,
                "from_zone": zone,
            }
            for k in (
                "cost_lte",
                "cost_eq",
                "power_lte",
                "name_contains",
                "exclude_name",
                "trait_contains",
                "color",
                "as_rested",
                "require_trigger",
                "cost_lte_opp_don_field",
                "cost_lte_own_don_field",
                "name_or_trait",
                "trait_any",
                "different_names",
                "total_cost_lte",
                "owner",
                "if_returned",
            ):
                if op.get(k) is not None:
                    then[k] = op[k]
            src = str(op.get("source_iid") or "")
            if src and src != "leader" and any(c.iid == src for c in player.characters):
                then["by_character_effect"] = True
                then["source_iid"] = src
            state.pending_choice = PendingChoice(
                seat=play_seat,
                card_id=str(op.get("card_id") or ""),
                source_iid=str(op.get("source_iid") or ""),
                target_kind="hand_card",
                options=options,
                remaining_ops=[*cont_ops, *queue],
                optional=bool(op.get("optional", True)),
                summary=summary,
                purpose=str(op.get("purpose") or "play"),
                then_op=then,
                controller_seat=play_seat,
            )
            logs.append({"key": "play.log.choice_offer", "name": hand_owner.username})
            return logs
    return logs


def _choice_options(state: MatchState, seat: int, target_kind: str, catalog: CatalogFn | None = None, filters: dict[str, Any] | None = None) -> list[str]:
    player = state.player(seat)
    foe = state.player(state.other(seat))
    kind = (target_kind or "").strip().lower()
    filters = filters or {}
    include_leader = bool(filters.get("include_leader"))
    if kind == "opponent_character_active":
        cands = [c for c in foe.characters if not c.rested]
    elif kind == "opponent_character_rested":
        cands = [c for c in foe.characters if c.rested]
    elif kind == "opponent_character":
        cands = list(foe.characters)
    elif kind == "opponent_stage":
        cands = list(foe.stages)
    elif kind == "own_stage":
        cands = list(player.stages)
    elif kind == "any_stage":
        cands = list(player.stages) + list(foe.stages)
    elif kind == "own_character":
        cands = list(player.characters)
    elif kind == "own_character_or_leader":
        cands = list(player.characters)
        include_leader = True
    elif kind == "own_leader_or_character":
        cands = list(player.characters)
        include_leader = True
    elif kind == "any_character":
        cands = list(player.characters) + list(foe.characters)
    elif kind == "leader":
        return ["leader"]
    elif kind == "opponent_leader":
        return ["leader"]
    elif kind in {"self", "source"}:
        # Self rest costs are resolved via source_iid — never opponent board.
        return []
    else:
        cands = list(foe.characters)

    if filters.get("active_only"):
        cands = [c for c in cands if not c.rested]

    if catalog is None and not filters:
        out = [c.iid for c in cands]
        if include_leader and not (filters.get("active_only") and player.leader_rested):
            out = ["leader", *out]
        if filters.get("include_don") and int(player.don_active or 0) > 0:
            out.append("don")
        return out

    from battle.engine import _info_has_trait, effective_character_cost

    out: list[str] = []
    owner_seat_for = {}
    for c in state.player(seat).characters:
        owner_seat_for[c.iid] = seat
    for c in state.player(state.other(seat)).characters:
        owner_seat_for[c.iid] = state.other(seat)

    for c in cands:
        info = catalog(c.card_id) if catalog else {}
        owner = owner_seat_for.get(c.iid, state.other(seat) if "opponent" in kind else seat)
        if catalog:
            try:
                cost = effective_character_cost(state, owner, c, catalog)
            except Exception:
                cost = max(0, _printed_cost(info) + int(getattr(c, "cost_mod", 0) or 0))
        else:
            cost = 0
        printed = _printed_cost(info) if info else 0
        if filters.get("cost_lte") is not None and cost > int(filters["cost_lte"]):
            continue
        if filters.get("cost_eq") is not None and cost != int(filters["cost_eq"]):
            continue
        if filters.get("cost_gte") is not None and cost < int(filters["cost_gte"]):
            continue
        if filters.get("base_cost_lte") is not None and printed > int(filters["base_cost_lte"]):
            continue
        needle_trait = str(filters.get("trait_contains") or "").strip()
        if needle_trait and catalog and not _info_has_trait(info, needle_trait):
            continue
        needle_name = str(filters.get("name_contains") or "").strip()
        if needle_name and not _card_matches_name_contains(info, needle_name):
            continue
        excl = str(filters.get("exclude_name") or "").strip()
        if excl and _card_excluded_by_name(info, excl):
            continue
        if filters.get("require_no_effect") and has_meaningful_effect_text(info):
            continue
        if filters.get("require_trigger") and not card_has_trigger(info):
            continue
        excluded = {str(x) for x in (filters.get("exclude_iids") or [])}
        if excluded and c.iid in excluded:
            continue
        try:
            raw = info.get("power") if info else 0
            base = int(str(raw).split()[0].replace(",", "") or 0)
        except Exception:
            base = 0
        if filters.get("base_power_lte") is not None and base > int(filters["base_power_lte"]):
            continue
        if filters.get("base_power_eq") is not None and base != int(filters["base_power_eq"]):
            continue
        if filters.get("require_blocker"):
            if not has_blocker(
                info,
                c,
                state=state,
                owner_seat=owner,
                catalog=catalog,
            ):
                continue
        live = base + int(getattr(c, "power_mod", 0) or 0) + int(getattr(c, "don_attached", 0) or 0) * 1000
        if filters.get("power_lte") is not None and live > int(filters["power_lte"]):
            continue
        if filters.get("power_gte") is not None and live < int(filters["power_gte"]):
            continue
        out.append(c.iid)
    if filters.get("include_leader_if_name") and catalog:
        lead_info = catalog(player.leader_card_id) if kind.startswith("own") else catalog(foe.leader_card_id)
        if _card_matches_name_contains(lead_info or {}, str(filters.get("include_leader_if_name") or "")):
            include_leader = True
    if include_leader or kind in {"opponent_leader_or_character"}:
        if not (filters.get("active_only") and (
            (kind.startswith("own") and player.leader_rested)
            or (kind.startswith("opponent") and foe.leader_rested)
        )):
            lead_ok = True
            needle_trait = str(filters.get("trait_contains") or "").strip()
            if needle_trait and catalog:
                if kind.startswith("opponent"):
                    lead_info = catalog(foe.leader_card_id)
                else:
                    lead_info = catalog(player.leader_card_id)
                lead_ok = _info_has_trait(lead_info or {}, needle_trait)
            if lead_ok:
                lead_seat = state.other(seat) if kind.startswith("opponent") else seat
                try:
                    from battle.engine import inst_power

                    live_lead = inst_power(state, lead_seat, "leader", catalog) if catalog else 0
                except Exception:
                    live_lead = 0
                if filters.get("power_lte") is not None and live_lead > int(filters["power_lte"]):
                    lead_ok = False
                if filters.get("power_gte") is not None and live_lead < int(filters["power_gte"]):
                    lead_ok = False
            if lead_ok:
                out = ["leader", *out]
    if filters.get("include_stage"):
        if kind.startswith("own"):
            stages = list(player.stages)
        elif kind.startswith("opponent"):
            stages = list(foe.stages)
        else:
            stages = []
        if filters.get("active_only"):
            stages = [s for s in stages if not s.rested]
        for s in stages:
            if s.iid not in out:
                out.append(s.iid)
    if filters.get("include_don"):
        if kind.startswith("own") and int(player.don_active or 0) > 0:
            out.append("don")
        elif kind.startswith("opponent") and int(foe.don_active or 0) > 0:
            out.append("don")
    return out


_ALLOWED_OPS = ALLOWED_OPS
_COMPLEX_HINT = re.compile(
    r"look at|reveal|trash|k\.?o\.?|banish|return|choose|select|your opponent|up to|"
    r"公開|查看|廢棄|废弃|返回|選擇|选择|對手|对手|最多",
    re.I,
)


def sanitize_ops(ops: list[dict[str, Any]], state: MatchState) -> list[dict[str, Any]]:
    # Keep signature for callers; board-live KO filter still applied.
    live_iids = {c.iid for p in state.players for c in p.characters}
    live_iids.update({"leader", "leader-0", "leader-1"})
    out: list[dict[str, Any]] = []
    for raw in ops:
        op = sanitize_op(raw)
        if not op:
            continue
        if op["op"] == "ko" and op.get("target_iid"):
            if op["target_iid"] not in live_iids or str(op["target_iid"]).startswith("leader"):
                # Keep as choose-target style without concrete iid
                op.pop("target_iid", None)
                op.setdefault("target_kind", "opponent_character")
        out.append(op)
    return out[:8]


def _board_snapshot(state: MatchState, seat: int) -> dict[str, Any]:
    def brief(p: Any) -> dict[str, Any]:
        return {
            "seat": p.seat,
            "username": p.username,
            "life": p.life_count,
            "don_active": p.don_active,
            "characters": [{"iid": c.iid, "card_id": c.card_id, "rested": c.rested} for c in p.characters],
            "hand_count": len(p.hand),
            "hand": list(p.hand) if p.seat == seat else [],
        }

    return {
        "phase": state.phase,
        "turn_seat": state.turn_seat,
        "players": [brief(p) for p in state.players],
    }


def _is_search_ops(ops: list[dict[str, Any]]) -> bool:
    return any(o.get("op") == "search_deck" for o in ops)


def _force_search_from_blob(blob: str) -> list[dict[str, Any]] | None:
    """If text is clearly a look-at-top search, never let LLM collapse it into draw."""
    op = _parse_look_top_search(blob)
    return [op] if op else None


def propose_complex_effect(
    state: MatchState,
    seat: int,
    card_id: str,
    source_iid: str,
    info: dict[str, Any],
    ask_llm: Callable[[str], str] | None,
) -> PendingEffect | None:
    simple = parse_simple_on_play(info)
    blob = effect_blob(info)
    if not blob.strip():
        return None
    # Search effects are always interactive (player picks from revealed cards).
    if simple and _is_search_ops(simple):
        return PendingEffect(
            effect_id=new_iid("fx"),
            seat=seat,
            card_id=card_id,
            source_iid=source_iid,
            summary="On Play: search",
            ops=simple,
            uncertain=False,
        )
    forced_search = _force_search_from_blob(blob)
    if forced_search:
        return PendingEffect(
            effect_id=new_iid("fx"),
            seat=seat,
            card_id=card_id,
            source_iid=source_iid,
            summary="On Play: search",
            ops=forced_search,
            uncertain=False,
        )
    if simple and not _COMPLEX_HINT.search(blob):
        return PendingEffect(
            effect_id=new_iid("fx"),
            seat=seat,
            card_id=card_id,
            source_iid=source_iid,
            summary=f"On Play: {simple}",
            ops=simple,
            uncertain=False,
        )
    if detect_keywords(info) and len(blob) < 70 and not simple:
        return None
    ops = list(simple)
    summary = "Unresolved effect — review before applying."
    if ask_llm is not None:
        prompt = (
            "You are an OPTCG rules resolver. Return ONLY JSON: "
            '{"summary":"...","ops":[{"op":"draw|gain_don|set_don|rest_opponent_character|buff|ko|search_deck",'
            '"count":1,"amount":1000,"target_iid":"","top_n":3,"max_add":1,"trait_contains":"","name_contains":""}]}\n'
            "Use empty ops if the effect cannot be applied safely this turn. "
            "Look-at-top / reveal-from-deck / add-to-hand effects MUST use op=search_deck (never draw). "
            "Only KO a character iid that exists on the snapshot. Do not invent hidden info.\n"
            f"Card: {card_id} {info.get('name_en') or info.get('name')}\n"
            f"Effect:\n{blob}\n"
            f"Acting seat: {seat}\n"
            f"Board snapshot:\n{json.dumps(_board_snapshot(state, seat), ensure_ascii=False)}\n"
        )
        try:
            raw = ask_llm(prompt)
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S)
            data = json.loads(cleaned)
            if isinstance(data, dict):
                summary = str(data.get("summary") or summary)
                maybe_ops = data.get("ops")
                if isinstance(maybe_ops, list):
                    ops = sanitize_ops([x for x in maybe_ops if isinstance(x, dict)], state)
                    if simple and not ops:
                        ops = list(simple)
                    # Never let LLM turn a look-at search into a silent draw.
                    if any(o.get("op") == "draw" for o in ops) and _parse_look_top_search(blob):
                        ops = _force_search_from_blob(blob) or [o for o in ops if o.get("op") != "draw"]
        except Exception:
            pass
    if not ops:
        return None
    # Interactive search must apply immediately (opens picker), not via confirm dialog.
    if _is_search_ops(ops):
        return PendingEffect(
            effect_id=new_iid("fx"),
            seat=seat,
            card_id=card_id,
            source_iid=source_iid,
            summary=(summary or "On Play: search")[:240],
            ops=ops,
            uncertain=False,
        )
    return PendingEffect(
        effect_id=new_iid("fx"),
        seat=seat,
        card_id=card_id,
        source_iid=source_iid,
        summary=summary[:240],
        ops=ops,
        uncertain=True,
    )


def get_deepseek_asker() -> Callable[[str], str] | None:
    api_key = str(os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None

    def ask(prompt: str) -> str:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            messages=[
                {"role": "system", "content": "Return only compact JSON. No markdown."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "1600")),
            timeout=float(os.getenv("DEEPSEEK_TIMEOUT", "60")),
        )
        return str(resp.choices[0].message.content or "").strip()

    return ask
