"""Curated effect library loader + unified resolve_ability entrypoint."""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable

from battle.effect_schema import (
    TIMINGS,
    ability_is_runnable,
    normalize_ability,
    normalize_card_entry,
    sanitize_ops_list,
)
from battle.effects import (
    _COMPLEX_HINT,
    _ensure_colon_cost_ops,
    _force_search_from_blob,
    _is_search_ops,
    detect_keywords,
    effect_blob,
    has_main_timing,
    parse_activate_main,
    parse_main_event,
    parse_on_ko,
    parse_simple_on_play,
    parse_trigger_ops,
)
from battle.state import MatchState, PendingEffect, new_iid

CatalogFn = Callable[[str], dict[str, Any]]
LlmFn = Callable[[str], str] | None

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LIBRARY = _ROOT / "index" / "card_effects.json"
_DEFAULT_OVERRIDES = _ROOT / "index" / "card_effect_overrides.json"

_lock = threading.RLock()
_library: dict[str, dict[str, Any]] = {}
_overrides: dict[str, dict[str, Any]] = {}
_loaded = False
_library_mtime: float | None = None
_overrides_mtime: float | None = None


def library_paths() -> tuple[Path, Path]:
    lib = Path(os.getenv("OPCG_CARD_EFFECTS", str(_DEFAULT_LIBRARY)))
    ovr = Path(os.getenv("OPCG_CARD_EFFECT_OVERRIDES", str(_DEFAULT_OVERRIDES)))
    return lib, ovr


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def reload_effect_library(*, force: bool = False) -> None:
    global _library, _overrides, _loaded, _library_mtime, _overrides_mtime
    lib_path, ovr_path = library_paths()
    with _lock:
        lm = _mtime(lib_path)
        om = _mtime(ovr_path)
        if (
            not force
            and _loaded
            and lm == _library_mtime
            and om == _overrides_mtime
        ):
            return
        raw_lib = _load_json(lib_path)
        raw_ovr = _load_json(ovr_path)
        # Support either { "cards": { id: ... } } or flat { id: ... }
        if "cards" in raw_lib and isinstance(raw_lib["cards"], dict):
            raw_lib = raw_lib["cards"]
        if "cards" in raw_ovr and isinstance(raw_ovr["cards"], dict):
            raw_ovr = raw_ovr["cards"]
        _library = {cid: normalize_card_entry(cid, v if isinstance(v, dict) else {}) for cid, v in raw_lib.items()}
        _overrides = {cid: normalize_card_entry(cid, v if isinstance(v, dict) else {}) for cid, v in raw_ovr.items()}
        _library_mtime = lm
        _overrides_mtime = om
        _loaded = True


def ensure_loaded() -> None:
    reload_effect_library(force=False)


def get_card_entry(card_id: str) -> dict[str, Any]:
    """Return merged card entry: per-timing override group wins, library fills the rest.

    Older overrides sometimes only curated one timing and wiped LLM/template fills
    for other timings. Merging keeps override fixes without masking progress.

    Multiple abilities that share a timing (e.g. two ``your_turn`` clauses) are kept
    as a group — last-write-wins on a single timing key was collapsing them.
    """
    ensure_loaded()
    with _lock:
        lib = _library.get(card_id)
        ovr = _overrides.get(card_id)
        if not ovr or not ovr.get("abilities"):
            return lib or normalize_card_entry(card_id, {})
        if not lib or not lib.get("abilities"):
            return ovr

        def _group(abilities: list[dict[str, Any]]) -> tuple[list[str], dict[str, list[dict[str, Any]]]]:
            order: list[str] = []
            groups: dict[str, list[dict[str, Any]]] = {}
            for a in abilities or []:
                t = str(a.get("timing") or "")
                if not t:
                    continue
                if t not in groups:
                    groups[t] = []
                    order.append(t)
                groups[t].append(a)
            return order, groups

        lib_order, lib_groups = _group(list(lib.get("abilities") or []))
        ovr_order, ovr_groups = _group(list(ovr.get("abilities") or []))
        order = list(lib_order)
        for t in ovr_order:
            if t not in order:
                order.append(t)

        merged: list[dict[str, Any]] = []
        for t in order:
            ovr_list = ovr_groups.get(t) or []
            lib_list = lib_groups.get(t) or []
            if ovr_list and any(ability_is_runnable(a) for a in ovr_list):
                merged.extend(ovr_list)
            elif lib_list:
                merged.extend(lib_list)
            else:
                merged.extend(ovr_list)

        return normalize_card_entry(
            card_id,
            {
                "version": max(int(lib.get("version") or 1), int(ovr.get("version") or 1),),
                "abilities": merged,
                **(
                    {"deck_ban_event_cost_gte": ovr["deck_ban_event_cost_gte"]}
                    if ovr.get("deck_ban_event_cost_gte") is not None
                    else (
                        {"deck_ban_event_cost_gte": lib["deck_ban_event_cost_gte"]}
                        if lib.get("deck_ban_event_cost_gte") is not None
                        else {}
                    )
                ),
            },
        )


def get_abilities(card_id: str, timing: str | None = None) -> list[dict[str, Any]]:
    entry = get_card_entry(card_id)
    abilities = list(entry.get("abilities") or [])
    if timing:
        t = timing.strip().lower()
        abilities = [a for a in abilities if a.get("timing") == t]
    return abilities


def lookup_runnable_ability(card_id: str, timing: str) -> dict[str, Any] | None:
    for ability in get_abilities(card_id, timing):
        if ability_is_runnable(ability):
            return ability
    return None


def library_stats() -> dict[str, Any]:
    ensure_loaded()
    with _lock:
        by_timing: dict[str, int] = {t: 0 for t in sorted(TIMINGS)}
        by_status: dict[str, int] = {"compiled": 0, "verified": 0, "needs_review": 0, "unsupported": 0}
        runnable = 0
        unsupported = 0
        empty_entries = 0
        for entry in {**_library, **_overrides}.values():
            abs_ = entry.get("abilities") or []
            if not abs_:
                empty_entries += 1
            for a in abs_:
                t = a.get("timing")
                if t in by_timing:
                    by_timing[t] += 1
                st = str(a.get("status") or "compiled")
                if st in by_status:
                    by_status[st] += 1
                if ability_is_runnable(a):
                    runnable += 1
                if a.get("status") == "unsupported":
                    unsupported += 1
        return {
            "library_cards": len(_library),
            "override_cards": len(_overrides),
            "abilities_by_timing": by_timing,
            "abilities_by_status": by_status,
            "runnable_abilities": runnable,
            "unsupported_abilities": unsupported,
            "empty_entries": empty_entries,
        }


def detect_timings_in_text(blob: str) -> set[str]:
    """Return engine timings that appear as keyword markers in card text."""
    import re as _re

    from battle.rules.timings import TIMING_DETECT_PATTERNS

    found: set[str] = set()
    text = blob or ""
    if not text.strip():
        return found
    for timing, pat in TIMING_DETECT_PATTERNS.items():
        if _re.search(pat, text, _re.I):
            found.add(timing)
    return _refine_gated_turn_timings(text, found)


def _refine_gated_turn_timings(blob: str, found: set[str]) -> set[str]:
    """Drop your_turn/opponent_turn when they only gate another keyword timing.

    Example: `[Your Turn] [On Play] Draw 1` needs on_play, not a separate your_turn ability.
    Standalone `[Your Turn] This Character gains +1000` still requires your_turn.

    Also drop `trigger` when the only matches are mid-sentence 'card with a [Trigger]'
    keyword references, not a Trigger ability section.
    """
    import re as _re

    out = set(found)
    gate_next = (
        r"\[(?:on\s+play|when\s+attacking|activate(?:\s*:\s*main)?|on\s*k\.?o\.?|trigger|on\s+block|"
        r"on\s+your\s+opponent'?s\s+attack)\]|"
        r"【(?:登場時|登场时|攻擊時|攻击时|啟動主要|启动主要|KO時|KO时|觸發器|触发器|阻擋時|阻挡时|"
        r"對方的?攻擊時|对方的?攻击时)】|"
        r"發動【觸發器】時|发动【触发器】时|發動【触发器】時"
    )

    def _only_gates(marker: str) -> bool:
        matches = list(_re.finditer(marker, blob, _re.I))
        if not matches:
            return True
        for m in matches:
            after = blob[m.end() : m.end() + 48]
            # Allow whitespace / once-per-turn between turn tag and the real timing.
            after = _re.sub(r"^\s*(?:\[once per turn\]|【每回合1次】)?\s*", "", after, flags=_re.I)
            if not _re.match(gate_next, after, _re.I):
                return False
        return True

    if "your_turn" in out and _only_gates(r"\[your turn\]|【我方回合中】"):
        out.discard("your_turn")
    if "opponent_turn" in out and _only_gates(r"\[opponent'?s turn\]|【對方回合中】|【对方回合中】"):
        out.discard("opponent_turn")

    if "trigger" in out:
        # Real Trigger sections usually start a line / slash-separated block.
        section = list(
            _re.finditer(
                r"(?:^|[\n\r/])\s*(?:\[trigger\]|【觸發器】|【触发器】|【触发】)",
                blob,
                _re.I | _re.M,
            )
        )
        if not section:
            out.discard("trigger")

    if "on_play" in out:
        # Drop [On Play] that only appear inside "effects are negated" clauses.
        real_sections = list(
            _re.finditer(
                r"(?:^|[\n\r/])\s*(?:\[on play\]|【登場時】|【登场时】|\[main\]|【主要】)",
                blob,
                _re.I | _re.M,
            )
        )
        negate_only = list(
            _re.finditer(
                r"(?:your|opponent'?s|自己的|對手的|对手的)\s*(?:\[on play\]|【登場時】|【登场时】)"
                r".{0,24}(?:effects? are )?negated|效果無效|效果无效",
                blob,
                _re.I,
            )
        )
        # Also mid-sentence references like "Activate this card's [On Play] effect" are not on_play sections.
        if not real_sections and negate_only:
            out.discard("on_play")
        elif not real_sections:
            # Only mid-sentence [On Play] mentions (no section start).
            all_marks = list(_re.finditer(r"\[on play\]|【登場時】|【登场时】|\[main\]|【主要】", blob, _re.I))
            if all_marks and all(
                _re.search(
                    r"negated|無效|无效|activate this card'?s|發動這張|发动这张",
                    blob[max(0, m.start() - 40) : m.end() + 40],
                    _re.I,
                )
                for m in all_marks
                if not _re.match(r"\[main\]|【主要】", m.group(0), _re.I)
            ):
                # Keep on_play if any [Main]/【主要】 remains.
                if not any(_re.match(r"\[main\]|【主要】", m.group(0), _re.I) for m in all_marks):
                    out.discard("on_play")

    return out


def card_has_timing_gaps(info: dict[str, Any], abilities: list[dict[str, Any]]) -> bool:
    """True if text marks a timing that has no runnable ability yet."""
    detected = detect_timings_in_text(effect_blob(info))
    if not detected and effect_blob(info).strip() and not abilities:
        return True
    by_t = {str(a.get("timing")): a for a in abilities}
    for t in detected:
        a = by_t.get(t)
        if a is None or not ability_is_runnable(a):
            return True
    return False


def _unsupported_stub(timing: str, reason: str) -> dict[str, Any]:
    return {
        "timing": timing,
        "summary": f"Needs review / unsupported ({reason})",
        "ops": [{"op": "unsupported", "reason": reason}],
        "status": "unsupported",
        "confidence": 0.1,
    }


def parse_don_static_power(info: dict[str, Any]) -> dict[str, Any] | None:
    """
    Parse continuous self-power effects gated by [DON!! xN].

    Supports:
      [DON!! xN] [Your Turn] ... +P
      [DON!! xN] [Opponent's Turn] ... +P
      [DON!! xN] This Character/Leader/card gains +P
      reversed [Your Turn]/[Opponent's Turn] then [DON!! xN]
    Skips When Attacking / Activate: Main / until-end temporary auras / team-wide buffs.
    """
    import re as _re

    en = str(info.get("effect_en") or "")
    zh = str(info.get("effect") or info.get("effect_cn") or "")
    if not (en or zh):
        return None

    # Prefer English structure; fall back to Chinese.
    patterns_en = [
        # [DON!! xN] [Your Turn] ...
        (
            "your_turn",
            r"\[DON!!\s*x\s*(\d+)\]\s*\[Your Turn\](.{0,280}?)(?=\[On Play\]|\[Activate:|\[When Attacking\]|\[Trigger\]|\[DON!!|$)",
        ),
        # [Your Turn] [DON!! xN] ...
        (
            "your_turn",
            r"\[Your Turn\]\s*\[DON!!\s*x\s*(\d+)\](.{0,280}?)(?=\[On Play\]|\[Activate:|\[When Attacking\]|\[Trigger\]|\[DON!!|$)",
        ),
        # [DON!! xN] [Opponent's Turn] ...
        (
            "opponent_turn",
            r"\[DON!!\s*x\s*(\d+)\]\s*\[Opponent's Turn\](.{0,280}?)(?=\[On Play\]|\[Activate:|\[When Attacking\]|\[Trigger\]|\[DON!!|$)",
        ),
        # [Opponent's Turn] [DON!! xN] ...
        (
            "opponent_turn",
            r"\[Opponent's Turn\]\s*\[DON!!\s*x\s*(\d+)\](.{0,280}?)(?=\[On Play\]|\[Activate:|\[When Attacking\]|\[Trigger\]|\[DON!!|$)",
        ),
        # [DON!! xN] plain continuous (no turn tag immediately after)
        (
            "don_attached",
            r"\[DON!!\s*x\s*(\d+)\](?!\s*\[(?:When Attacking|Activate:|On Play|Trigger|On Your Opponent's Attack)\])(.{0,280}?)(?=\[On Play\]|\[Activate:|\[When Attacking\]|\[Trigger\]|\[DON!!|$)",
        ),
    ]
    patterns_zh = [
        (
            "your_turn",
            r"【咚‼?\s*[×xX]\s*(\d+)】\s*【我方回合中】(.{0,280}?)(?=【登場時】|【启动主要】|【啟動主要】|【攻击时】|【攻擊時】|【咚‼?|$)",
        ),
        (
            "opponent_turn",
            r"【咚‼?\s*[×xX]\s*(\d+)】\s*【對手回合中】(.{0,280}?)(?=【登場時】|【启动主要】|【啟動主要】|【攻击时】|【攻擊時】|【咚‼?|$)",
        ),
        (
            "don_attached",
            r"【咚‼?\s*[×xX]\s*(\d+)】(?!\s*【(?:攻擊時|攻击时|啟動主要|启动主要|登場時)】)(.{0,280}?)(?=【登場時】|【启动主要】|【啟動主要】|【攻击时】|【攻擊時】|【咚‼?|$)",
        ),
    ]

    timing = None
    don_n = 1
    body = ""
    chunk = ""
    for tname, pat in patterns_en:
        m = _re.search(pat, en, _re.I | _re.S)
        if not m:
            continue
        timing = tname
        don_n = max(1, min(10, int(m.group(1) or 1)))
        body = m.group(2) or ""
        chunk = m.group(0)
        break
    if timing is None:
        for tname, pat in patterns_zh:
            m = _re.search(pat, zh, _re.I | _re.S)
            if not m:
                continue
            timing = tname
            don_n = max(1, min(10, int(m.group(1) or 1)))
            body = m.group(2) or ""
            chunk = m.group(0)
            break
    if timing is None:
        return None

    # Continuous scalers that keep this as a live static buff (not rejected).
    per_distinct_names = bool(
        _re.search(
            r"(?:for every|for each).{0,40}different card name|"
            r"カード名の異なる|"
            r"卡片名稱不同|卡片名称不同|名稱不同的角色|名称不同的角色",
            body,
            _re.I,
        )
    )
    per_rested_don_m = _re.search(
        r"(?:for every|every)\s*(\d+)\s*(?:of your )?rested DON|"
        r"每有\s*(\d+)\s*張休息狀態的咚|自己每有\s*(\d+)\s*張休息狀態的咚|"
        r"レストしたドン.*?(\d+)\s*枚につき|ドン.*?(\d+)\s*枚につき",
        body,
        _re.I,
    )
    per_trash_events_m = _re.search(
        r"(?:for every|every)\s*(\d+)\s*Events? in your trash|"
        r"廢棄區中每有\s*(\d+)\s*張事件|废弃区中每有\s*(\d+)\s*张事件|"
        r"トラッシュ.*?(?:の)?イベント.*?(\d+)\s*枚につき",
        body,
        _re.I,
    )
    per_trash_cards_m = _re.search(
        r"(?:for every|every)\s*(\d+)\s*cards? in your trash|"
        r"廢棄區中每有\s*(\d+)\s*張卡片|废弃区中每有\s*(\d+)\s*张卡片|"
        r"自分のトラッシュ.*?(\d+)\s*枚につき",
        body,
        _re.I,
    )
    # Event-trash takes priority over generic trash-cards when both could match.
    if per_trash_events_m and ("事件" in body or "Event" in body or "イベント" in body):
        per_trash_cards_m = None

    has_scaler = bool(
        per_distinct_names or per_rested_don_m or per_trash_events_m or per_trash_cards_m
    )

    # Reject non-continuous / non-self-simple effects.
    # Scaler 「每有/for each」 forms above are kept.
    if not has_scaler and _re.search(r"for each|per each|每有|每張|每张", body, _re.I):
        return None
    reject = _re.search(
        r"when attacking|activate:\s*main|until the start of your next turn|"
        r"all of your (?:\{[^}]+\} type )?characters gain|"
        r"your leader and (?:all )?characters|"
        r"on your opponent's attack|"
        r"根據|根据|"
        r"攻擊時|攻击时|啟動主要|启动主要|直到自己的下一個回合|"
        r"自己的角色卡全部|領袖卡和角色卡|"
        # Base/power copy effects are never plain +N continuous buffs.
        r"becomes? the same|base power becomes|power becomes|"
        r"變成和|变成和|變更成|变更成|變成.?相同|变成.?相同",
        body,
        _re.I,
    )
    if reject:
        return None
    # Must be a self power buff (Character / Leader / this card), not only keywords.
    if not _re.search(
        r"(?:this (?:character|leader|card)|this leader|該角色|这张角色|這張角色|此領袖|此领袖|這張領袖|这张领袖).{0,40}(?:gain|power|力量)|"
        r"(?:gains?|gain)\s*\+?\d{3,5}\s*power|"
        r"力量[值]?\s*\+\d{3,5}",
        body,
        _re.I,
    ):
        return None

    amt_m = _re.search(r"(?:gains?\s*\+?|power\s*\+|力量[值]?\s*\+)(\d{3,5})", body, _re.I)
    if not amt_m:
        amt_m = _re.search(r"\+(\d{3,5})\s*power", body, _re.I)
    if not amt_m:
        return None
    amount = max(0, min(5000, int(amt_m.group(1))))
    if amount <= 0:
        return None

    buff_op: dict[str, Any] = {"op": "buff_self", "amount": amount}
    if per_distinct_names:
        buff_op["per_distinct_own_char_names"] = True
    elif per_rested_don_m:
        n = int(next(g for g in per_rested_don_m.groups() if g))
        buff_op["per_rested_don"] = max(1, min(10, n))
    elif per_trash_events_m:
        n = int(next(g for g in per_trash_events_m.groups() if g))
        buff_op["per_trash_events"] = max(1, min(20, n))
    elif per_trash_cards_m:
        n = int(next(g for g in per_trash_cards_m.groups() if g))
        buff_op["per_trash_cards"] = max(1, min(20, n))

    out: dict[str, Any] = {
        "timing": timing,
        "summary": chunk.strip()[:240],
        "ops": sanitize_ops_list([buff_op]),
        "status": "compiled",
        "confidence": 0.8,
        "require_don_attached_gte": don_n,
    }

    hand_ge = _re.search(
        r"(?:(\d+)\s*or more cards in your hand|hand.*?(\d+)\s*or more|手牌[有]?(\d+)\s*[張张]以上)",
        body,
        _re.I,
    )
    if hand_ge:
        n = next((int(g) for g in hand_ge.groups() if g), None)
        if n is not None:
            out["require_hand_gte"] = max(0, min(20, n))
    hand_le = _re.search(
        r"(?:(\d+)\s*or less cards in your hand|hand.*?(\d+)\s*or less|手牌[有]?(\d+)\s*[張张]以下)",
        body,
        _re.I,
    )
    if hand_le:
        n = next((int(g) for g in hand_le.groups() if g), None)
        if n is not None:
            out["require_hand_lte"] = max(0, min(20, n))

    chars_ge = _re.search(
        r"(?:(\d+)\s*or more [Cc]haracters|角色卡[有]?(\d+)\s*張以上|角色[有]?(\d+)\s*张以上)",
        body,
        _re.I,
    )
    if chars_ge:
        n = next((int(g) for g in chars_ge.groups() if g), None)
        if n is not None:
            out["require_chars_gte"] = max(0, min(5, n))

    life_le = _re.search(
        r"(?:(\d+)\s*or less [Ll]ife|生命[有]?(\d+)\s*[張张]以下|0\s*[Ll]ife cards|生命[為为]?\s*0)",
        body,
        _re.I,
    )
    if life_le:
        if _re.search(r"0\s*[Ll]ife|生命[為为]?\s*0", body, _re.I):
            out["require_life_lte"] = 0
        else:
            n = next((int(g) for g in life_le.groups() if g), None)
            if n is not None:
                out["require_life_lte"] = max(0, min(10, n))

    if _re.search(r"less [Ll]ife cards than your opponent|生命[數数]?少於對手|生命[数數]?少于对手", body, _re.I):
        out["require_life_less_than_opponent"] = True

    # Leader trait gate: If your Leader has {X} / 若自己的領航卡擁有《X》
    trait_m = _re.search(
        r"(?:if your [Ll]eader has (?:the )?\{([^}]+)\}|"
        r"若自己的領航卡擁有《([^》]+)》|"
        r"若自己的领航卡拥有《([^》]+)》|"
        r"自分のリーダーが《([^》]+)》)",
        body,
    )
    if trait_m:
        trait = next((g for g in trait_m.groups() if g), "").strip()
        if trait:
            out["require_leader_trait"] = trait[:40]

    deck_le = _re.search(
        r"(?:(\d+)\s*or less cards in your deck|卡組[有]?(\d+)\s*[張张]以下|卡组[有]?(\d+)\s*张以下)",
        body,
        _re.I,
    )
    if deck_le:
        n = next((int(g) for g in deck_le.groups() if g), None)
        if n is not None:
            out["require_deck_lte"] = max(0, min(60, n))

    opp_rest = _re.search(
        r"opponent has (\d+)\s*or more rested [Cc]haracters|對手有(\d+)\s*張以上休止|对手有(\d+)\s*张以上休息",
        body,
        _re.I,
    )
    if opp_rest:
        n = next((int(g) for g in opp_rest.groups() if g), None)
        if n is not None:
            out["require_opp_rested_chars_gte"] = max(0, min(5, n))

    return out


# Back-compat alias
def parse_your_turn_static_power(info: dict[str, Any]) -> dict[str, Any] | None:
    parsed = parse_don_static_power(info)
    if not parsed:
        return None
    if parsed.get("timing") != "your_turn":
        return None
    return parsed


def static_power_abilities(card_id: str, info: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Runnable continuous DON!! self-power abilities (library/override/template)."""
    ensure_loaded()
    out: list[dict[str, Any]] = []
    seen = set()
    for timing in ("your_turn", "opponent_turn", "don_attached"):
        for ability in get_abilities(card_id, timing):
            if not ability_is_runnable(ability):
                continue
            # Only self power buffs
            if not any(o.get("op") == "buff_self" for o in (ability.get("ops") or [])):
                continue
            key = (
                ability.get("timing"),
                ability.get("require_don_attached_gte"),
                ability.get("require_hand_gte"),
                ability.get("require_hand_lte"),
                tuple(sorted((k, ability.get(k)) for k in ability if str(k).startswith("require_"))),
                tuple(
                    (
                        o.get("op"),
                        o.get("amount"),
                        bool(o.get("per_distinct_own_char_names")),
                        o.get("per_rested_don"),
                        o.get("per_trash_cards"),
                        o.get("per_trash_events"),
                        o.get("per_own_chars"),
                    )
                    for o in (ability.get("ops") or [])
                ),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(ability)
    if out:
        return out
    if info is None:
        return []
    templated = parse_don_static_power(info)
    if templated and ability_is_runnable(templated):
        return [templated]
    return []


def continuous_base_power_abilities(card_id: str, info: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Continuous base-power rewrite abilities (library / template)."""
    ensure_loaded()
    out: list[dict[str, Any]] = []
    for timing in ("your_turn", "opponent_turn"):
        for ability in get_abilities(card_id, timing):
            if not ability_is_runnable(ability):
                continue
            if not any(
                o.get("op")
                in {
                    "continuous_base_from_own_leader_printed",
                    "set_base_power",
                    "continuous_set_base_power",
                }
                for o in (ability.get("ops") or [])
            ):
                continue
            out.append(ability)
    if out:
        return out
    if info is None:
        return []
    from battle.effects import parse_continuous_base_power_copy

    templated = parse_continuous_base_power_copy(info)
    if templated and ability_is_runnable(templated):
        return [templated]
    return []


def static_cost_abilities(card_id: str, info: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Continuous Your Turn auras that reduce all opponent Character costs."""
    ensure_loaded()
    out: list[dict[str, Any]] = []
    for ability in get_abilities(card_id, "your_turn"):
        if not ability_is_runnable(ability):
            continue
        if not any(o.get("op") == "static_reduce_opp_cost" for o in (ability.get("ops") or [])):
            continue
        out.append(ability)
    if out:
        return out
    if info is None:
        return []
    from battle.effects import parse_static_opp_cost_reduce

    templated = parse_static_opp_cost_reduce(info)
    if templated and ability_is_runnable(templated):
        return [templated]
    return []


def hand_cost_abilities(card_id: str, info: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Hand-play cost reduction abilities (self or board aura)."""
    ensure_loaded()
    out: list[dict[str, Any]] = []
    for ability in get_abilities(card_id, "hand_cost"):
        if not ability_is_runnable(ability):
            continue
        if not any(o.get("op") == "hand_cost_reduce" for o in (ability.get("ops") or [])):
            continue
        out.append(ability)
    if out:
        return out
    if info is None:
        return []
    from battle.effects import parse_board_hand_cost_aura, parse_hand_cost_reduce

    for parser in (parse_hand_cost_reduce, parse_board_hand_cost_aura):
        templated = parser(info)
        if templated and ability_is_runnable(templated):
            out.append(templated)
    return out


def your_turn_power_abilities(card_id: str, info: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Deprecated alias — returns all static DON power abilities."""
    return static_power_abilities(card_id, info)


def _annotate_ops(ops: list[dict[str, Any]], card_id: str, source_iid: str, summary: str = "") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in ops:
        op = dict(raw)
        # Always stamp source for self-targeting / cost ops (Stage rest-self, etc.).
        op.setdefault("card_id", card_id)
        op.setdefault("source_iid", source_iid)
        if summary and not op.get("summary"):
            # Keep per-op summary when present; otherwise inherit ability summary for search/choice UI.
            if op.get("op") in {"search_deck", "play_from_hand", "buff", "rest_character", "trash_hand"}:
                op["summary"] = summary
        out.append(op)
    return out


def _from_templates(card_id: str, timing: str, info: dict[str, Any]) -> dict[str, Any] | None:
    """Deterministic parsers → ability-shaped dict."""
    if timing == "on_play":
        blob = effect_blob(info)
        # Never invent On Play from Activate: Main / Trigger / When Attacking-only text
        # (e.g. ST02-007 Jewelry Bonney search must stay Activate: Main + DON!! cost).
        has_on_play_tag = bool(re.search(r"\[on play\]|【登場時】|【登场时】", blob, re.I))
        ctype = str(info.get("card_type") or info.get("type") or info.get("category") or "").lower()
        is_event = "event" in ctype or "事件" in ctype
        if not has_on_play_tag:
            # Event [Main] resolves when the Event is played, not at Main Phase start.
            if not (is_event and has_main_timing(info)):
                return None
            ops = parse_main_event(info)
            if not ops:
                return None
        else:
            ops = parse_simple_on_play(info)
            if not ops:
                ops = parse_main_event(info)
            if not ops:
                forced = _force_search_from_blob(blob)
                if forced:
                    ops = forced
            if not ops:
                return None
        status = "compiled"
        known = {
            "draw",
            "gain_don",
            "rest_opponent_character",
            "ko_lowest_opponent",
            "ko",
            "search_deck",
            "play_from_hand",
            "buff",
            "buff_self",
            "buff_all_own",
            "return_to_bottom",
            "return_to_hand",
            "reduce_cost",
            "trash_deck_top",
            "trash_hand",
            "active_don",
            "rest_don",
            "set_character_active",
            "cannot_take_life",
            "cannot_play_from_hand",
            "skip_untap",
            "hand_to_deck",
            "reveal_opp_hand",
            "reveal_hand",
            "look_deck",
            "look_opp_deck",
            "grant_cost",
            "redirect_attack",
            "trash_hand_down_to",
            "add_from_trash",
            "negate_effects",
            "negate_on_play",
            "grant_keyword",
            "grant_attribute",
            "attach_don",
            "add_life",
            "choose_target",
            "trash_to_bottom",
            "opponent_hand_to_bottom",
            "deny_blocker",
            "allow_attack_active",
            "replace_battle_ko",
            "deny_attack",
            "deny_rest",
            "set_cost",
            "life_to_hand",
            "flip_life",
            "trash_life",
            "hand_to_life",
            "place_on_life",
            "replace_leave",
            "replace_rest",
            "replace_battle_ko",
            "redirect_attack",
        }
        if _COMPLEX_HINT.search(blob) and not all(o.get("op") in known for o in ops):
            # Partial parse of a complex card — still usable but flagged.
            status = "needs_review"
        summary = str(info.get("effect") or info.get("effect_en") or f"On Play: {ops}")[:240]
        if parse_main_event(info) and not parse_simple_on_play(info):
            summary = (info.get("effect") or info.get("effect_en") or summary)[:240]
        out = {
            "timing": "on_play",
            "summary": summary,
            "ops": sanitize_ops_list(ops),
            "status": status,
            "confidence": 0.85 if status == "compiled" else 0.55,
        }
        # Whole-ability gate: 「若場上有費用N的角色卡時，…」
        from battle.effects import _extract_require_field_char_cost_eq, _on_play_chunk

        field_ceq = _extract_require_field_char_cost_eq(_on_play_chunk(blob) or blob)
        if field_ceq is not None:
            out["require_field_char_cost_eq"] = field_ceq
        return out
    # Also mirror condition fields from parse_activate_main into template compile
    if timing == "activate_main":
        spec = parse_activate_main(info)
        if not spec or not spec.get("ops"):
            return None
        out = {
            "timing": "activate_main",
            "summary": str(spec.get("summary") or "Activate: Main")[:240],
            "ops": sanitize_ops_list(list(spec.get("ops") or [])),
            "status": "compiled",
            "confidence": 0.85,
            "cost_don": int(spec.get("cost_don") or 0),
            "rest_self": bool(spec.get("rest_self")),
            "once": bool(spec.get("once")),
        }
        if spec.get("require_all_chars_trait"):
            out["require_all_chars_trait"] = spec["require_all_chars_trait"]
        if spec.get("require_leader_trait"):
            out["require_leader_trait"] = spec["require_leader_trait"]
        if spec.get("require_char_power_gte"):
            out["require_char_power_gte"] = spec["require_char_power_gte"]
        if spec.get("require_field_char_cost_eq") is not None:
            out["require_field_char_cost_eq"] = int(spec["require_field_char_cost_eq"])
        return out
    if timing == "trigger":
        ops = parse_trigger_ops(info)
        if not ops:
            return None
        return {
            "timing": "trigger",
            "summary": f"Trigger: {ops}"[:240],
            "ops": sanitize_ops_list(ops),
            "status": "compiled",
            "confidence": 0.8,
        }
    if timing == "when_attacking":
        # Best-effort: when attacking + draw/don/buff/bottom/base-copy templates.
        import re as _re

        from battle.effects import (
            _parse_attach_don_ops,
            _parse_cannot_be_ko_ops,
            _parse_grant_keyword_ops,
            _parse_ko_op,
            _parse_place_on_bottom_ops,
            _parse_power_buff_amount,
            _parse_return_char_to_hand_ops,
            _parse_set_active_ops,
            _parse_trash_hand_cost,
            parse_when_attacking_base_power_copy,
        )

        blob = effect_blob(info)
        parsed_copy = parse_when_attacking_base_power_copy(info)
        m = _re.search(
            r"(?:\[when attacking\]|【攻擊時】|【攻击时】)"
            r"((?:(?!\[(?:on\s+play|when\s+attacking|activate(?:\s*:\s*main)?|counter|"
            r"on\s*k\.?o\.?|on\s+block|your\s+turn|opponent'?s\s+turn|end\s+of)|"
            r"【(?:登場時|登场时|啟動主要|启动主要|反擊|反击|KO時|KO时|我方回合中|對方回合中|对方回合中)】|"
            r"(?:\n|\r|/)\s*【(?:觸發器|触发器)】|"
            r"(?:\n|\r|/)\s*\[trigger\]).){0,400})",
            blob,
            _re.I | _re.S,
        )
        if not m and not parsed_copy:
            return None
        chunk = m.group(0) if m else str((parsed_copy or {}).get("summary") or "")
        ops: list[dict[str, Any]] = []
        if parsed_copy and parsed_copy.get("ops"):
            ops.extend(list(parsed_copy["ops"]))
        if _re.search(r"draw 1|抽1", chunk, _re.I):
            ops.append({"op": "draw", "count": 1})
        if _re.search(r"don!!\s*\+1|咚‼?\s*\+?\s*1", chunk, _re.I) and not _re.search(
            r"don!!\s*[×xX]|咚‼?\s*[×xX]", chunk, _re.I
        ):
            ops.append({"op": "gain_don", "count": 1})
        # Only plain self buff — never match "Leader's power" / copy effects.
        ops.extend(_parse_power_buff_amount(chunk))
        if not any(o.get("op") == "buff_self" for o in ops):
            if _re.search(r"(?:gains?\s*\+1000|power\s*\+1000|力量[值]?\s*\+1000)", chunk, _re.I) and not _re.search(
                r"becomes?|變成|变成|相同", chunk, _re.I
            ):
                ops.append({"op": "buff_self", "amount": 1000})
        ko_op = _parse_ko_op(chunk)
        if ko_op and not (
            ko_op.get("target_kind") == "own_character"
            and _re.search(r"cost|費用|费用|\+\s*\d{3,5}\s*power|力量", chunk, _re.I)
        ):
            # Own-KO + reduce/buff family handled below to avoid duplicate KO ops.
            ops.append(ko_op)
        elif ko_op and ko_op.get("target_kind") != "own_character":
            ops.append(ko_op)
        ops.extend(_parse_place_on_bottom_ops(chunk))
        ops.extend(_parse_return_char_to_hand_ops(chunk))
        ops.extend(_parse_attach_don_ops(chunk))
        ops.extend(_parse_grant_keyword_ops(chunk))
        ops.extend(_parse_set_active_ops(chunk))
        ops.extend(_parse_cannot_be_ko_ops(chunk))
        from battle.effects import (
            _parse_allow_attack_active_ops,
            _parse_cannot_take_life_ops,
            _parse_cost_reduce_family_ops as _family,
            _parse_deny_blocker_ops,
            _parse_replace_battle_ko_ops,
            _parse_skip_untap_ops,
        )

        ops.extend(_parse_deny_blocker_ops(chunk))
        ops.extend(_parse_allow_attack_active_ops(chunk))
        from battle.effects import (
            _parse_negate_effects_ops,
            _parse_opponent_hand_to_bottom_ops,
            _parse_trash_to_bottom_ops,
        )

        ops.extend(_parse_negate_effects_ops(chunk))
        for op in _family(chunk):
            if op.get("op") == "ko" and any(
                o.get("op") == "ko" and o.get("target_kind") == op.get("target_kind") for o in ops
            ):
                continue
            if op.get("op") == "ko" and op.get("target_kind") == "own_character":
                ops = [
                    o
                    for o in ops
                    if not (o.get("op") == "ko" and str(o.get("target_kind", "")).startswith("opponent"))
                ]
            if any(o.get("op") == op.get("op") for o in ops) and op.get("op") in {
                "reduce_cost",
                "trash_deck_top",
                "buff_all_own",
                "ko",
            }:
                continue
            ops.append(op)
        trash_cost = _parse_trash_hand_cost(chunk)
        if trash_cost and not any(o.get("op") == "trash_hand" for o in ops):
            ops = trash_cost + ops
        from battle.effects import _parse_life_zone_ops

        life_ops = _parse_life_zone_ops(chunk) or _parse_life_zone_ops(blob)
        if life_ops:
            cost_life = [o for o in life_ops if o.get("as_cost")]
            rest_life = [o for o in life_ops if not o.get("as_cost")]
            if cost_life and not any(o.get("as_cost") for o in ops):
                ops = cost_life + ops
            for o in rest_life:
                if not any(x.get("op") == o.get("op") and x.get("owner") == o.get("owner") for x in ops):
                    ops.append(o)
        # Keyword brackets like [Blocker] truncate the local chunk; re-scan full blob.
        for extra in (
            _parse_deny_blocker_ops(blob)
            + _parse_allow_attack_active_ops(blob)
            + _parse_cannot_take_life_ops(blob)
            + _parse_replace_battle_ko_ops(blob)
            + _parse_skip_untap_ops(blob)
            + _parse_negate_effects_ops(blob)
        ):
            if any(o.get("op") == extra.get("op") for o in ops):
                continue
            ops.append(extra)
        if not ops:
            return None
        out: dict[str, Any] = {
            "timing": "when_attacking",
            "summary": (parsed_copy or {}).get("summary") or chunk.strip()[:240],
            "ops": sanitize_ops_list(ops),
            "status": "compiled",
            "confidence": 0.8 if parsed_copy else 0.7,
        }
        if parsed_copy and parsed_copy.get("require_don_attached_gte") is not None:
            out["require_don_attached_gte"] = int(parsed_copy["require_don_attached_gte"])
        if parsed_copy and parsed_copy.get("once"):
            out["once"] = True
        return out
    if timing == "opponent_turn":
        from battle.effects import parse_continuous_base_power_copy

        cont = parse_continuous_base_power_copy(info)
        if cont:
            return {
                **cont,
                "ops": sanitize_ops_list(list(cont.get("ops") or [])),
            }
        parsed = parse_don_static_power(info)
        return parsed if parsed and parsed.get("timing") == "opponent_turn" else None
    if timing in {"on_block", "on_opponent_attack", "end_of_your_turn", "end_of_opponent_turn", "turn_start", "main_start"}:
        import re as _re

        from battle.effects import (
            _parse_place_on_bottom_ops,
            _parse_return_char_to_hand_ops,
            parse_on_opponent_attack_base_power_copy,
        )

        if timing == "on_opponent_attack":
            copied = parse_on_opponent_attack_base_power_copy(info)
            if copied:
                return {
                    **copied,
                    "ops": sanitize_ops_list(list(copied.get("ops") or [])),
                }

        if timing == "on_block":
            from battle.effects import parse_when_attacking_base_power_copy

            # OP06-009 shares When Attacking / On Block wording.
            block_copy = parse_when_attacking_base_power_copy(info)
            if block_copy and any(
                o.get("op") == "set_power_equal_opponent_leader" for o in (block_copy.get("ops") or [])
            ):
                out = {
                    **block_copy,
                    "timing": "on_block",
                    "summary": "On Block: power becomes equal to opponent Leader",
                    "ops": sanitize_ops_list(list(block_copy.get("ops") or [])),
                }
                return out

        patterns = {
            "on_opponent_attack": (
                r"(?:\[on your opponent'?s attack\]|【對方的?攻擊時】|【对方的?攻击时】|"
                r"【對方攻擊時】|【对方攻击时】)"
                r"((?:(?!\[(?:on\s+play|when\s+attacking|activate|trigger|counter|your\s+turn)|"
                r"【(?:登場時|登场时|攻擊時|攻击时|啟動主要|触發器|触发器|我方回合中)】).){0,360})"
            ),
            "on_block": (
                r"(?:\[on block\]|【阻擋時】|【阻挡时】|【防禦時】|【防御时】)"
                r"((?:(?!\[(?:on\s+play|when\s+attacking|activate|trigger|counter)|"
                r"【(?:登場時|登场时|攻擊時|攻击时|啟動主要)】).){0,280})"
            ),
            "end_of_your_turn": (
                r"(?:\[end of your turn\]|【我方的?回合結束時】|【我方的?回合结束时】)"
                r"((?:(?!\[(?:on\s+play|when\s+attacking|activate|trigger|counter)|"
                r"【(?:登場時|登场时|攻擊時|攻击时|啟動主要|触發器|触发器)】).){0,300})"
            ),
            "end_of_opponent_turn": (
                r"(?:\[end of your opponent'?s turn\]|【對方的?回合結束時】|【对方的?回合结束时】)"
                r"((?:(?!\[(?:on\s+play|when\s+attacking|activate|trigger|counter)|"
                r"【(?:登場時|登场时|攻擊時|攻击时|啟動主要)】).){0,300})"
            ),
            "turn_start": r"(?:\[start of your turn\]|【我方的?回合開始時】|【我方的?回合开始时】)([^【\[]{0,220})",
            "main_start": r"(?:\[main\]|【主要】)([^【\[]{0,120})",
        }
        blob = effect_blob(info)
        m = _re.search(patterns[timing], blob, _re.I | _re.S)
        if not m:
            return None
        chunk = m.group(0)
        ops: list[dict[str, Any]] = []
        if _re.search(r"draw 2|抽2", chunk, _re.I):
            ops.append({"op": "draw", "count": 2})
        elif _re.search(r"draw 1|抽1", chunk, _re.I):
            ops.append({"op": "draw", "count": 1})
        if _re.search(r"don!!\s*\+1|咚‼?\s*\+?\s*1", chunk, _re.I) and not _re.search(
            r"don!!\s*[×xX]|咚‼?\s*[×xX]|don!!\s*[−\-]", chunk, _re.I
        ):
            ops.append({"op": "gain_don", "count": 1})
        if _re.search(r"(?:gains?\s*\+1000|power\s*\+1000|力量[值]?\s*\+1000)", chunk, _re.I) and not _re.search(
            r"becomes?|變成|变成|相同", chunk, _re.I
        ):
            ops.append({"op": "buff_self", "amount": 1000})
        if _re.search(r"rest (up to )?1|休息最多1|將對方最多1|将对方最多1", chunk, _re.I):
            ops.append({"op": "rest_opponent_character", "count": 1})
        ops.extend(_parse_place_on_bottom_ops(chunk))
        ops.extend(_parse_return_char_to_hand_ops(chunk))
        from battle.effects import (
            _parse_redirect_attack_ops,
            _parse_set_active_ops,
            _parse_skip_untap_ops,
            _parse_trash_hand_cost,
        )

        ops.extend(_parse_set_active_ops(chunk))
        ops.extend(_parse_redirect_attack_ops(chunk))
        ops.extend(_parse_skip_untap_ops(chunk))
        if _re.search(r"don!!\s*[−\-~－]\s*1|咚‼?\s*[−\-~－]\s*1", chunk, _re.I):
            if not any(o.get("op") == "rest_don" for o in ops):
                ops.append({"op": "rest_don", "count": 1})
        trash_cost = _parse_trash_hand_cost(chunk)
        if trash_cost and not any(o.get("op") == "trash_hand" for o in ops):
            ops = trash_cost + ops
        if not ops:
            return None
        out_ab: dict[str, Any] = {
            "timing": timing,
            "summary": chunk.strip()[:240],
            "ops": sanitize_ops_list(ops),
            "status": "compiled",
            "confidence": 0.65,
        }
        if _re.search(r"once per turn|每回合1次", chunk, _re.I):
            out_ab["once"] = True
        m_rested_trait = _re.search(
            r"(\d+)\s+or more rested \{([^}]+)\}|"
            r"(\d+)\s*[張张]以上自己休息狀態擁有《([^》]+)》|"
            r"(\d+)\s*[张张]以上自己休息状态拥有《([^》]+)》",
            chunk,
            _re.I,
        )
        if m_rested_trait:
            gs = [g for g in m_rested_trait.groups() if g]
            out_ab["require_rested_own_chars_gte"] = int(gs[0])
            out_ab["require_rested_own_chars_trait"] = gs[1]
        return out_ab
    if timing == "your_turn":
        import re as _re

        from battle.effects import (
            _parse_opponent_hand_to_bottom_ops,
            _parse_replace_leave_ops,
            parse_negate_on_play_aura,
            parse_static_opp_cost_reduce,
            parse_untimed_static,
        )

        # Continuous leave/KO shields (ST09-010, OP15-098, etc.)
        leave_ops = _parse_replace_leave_ops(effect_blob(info))
        if leave_ops:
            blob_leave = effect_blob(info)
            return {
                "timing": "your_turn",
                "summary": blob_leave.strip()[:240],
                "ops": sanitize_ops_list(leave_ops),
                "status": "compiled",
                "confidence": 0.85,
                "once": bool(_re.search(r"once per turn|每回合1次", blob_leave, _re.I)),
            }
        untimed = parse_untimed_static(info)
        if untimed and any(o.get("op") == "replace_leave" for o in (untimed.get("ops") or [])):
            return {
                **untimed,
                "ops": sanitize_ops_list(list(untimed.get("ops") or [])),
            }

        cost_aura = parse_static_opp_cost_reduce(info)
        if cost_aura:
            return {
                **cost_aura,
                "ops": sanitize_ops_list(list(cost_aura.get("ops") or [])),
            }
        # Reaction: when opponent activates Event / when Character leaves by your effect.
        blob = effect_blob(info)
        if _re.search(r"\[your turn\]|【我方回合中】", blob, _re.I):
            ops: list[dict[str, Any]] = []
            ops.extend(_parse_opponent_hand_to_bottom_ops(blob))
            if ops:
                out_yt: dict[str, Any] = {
                    "timing": "your_turn",
                    "summary": blob.strip()[:240],
                    "ops": sanitize_ops_list(ops),
                    "status": "compiled",
                    "confidence": 0.75,
                    "once": bool(_re.search(r"once per turn|每回合1次", blob, _re.I)),
                }
                if _re.search(r"activates? an Event|發動事件|发动事件", blob, _re.I):
                    out_yt["on_opponent_event"] = True
                if _re.search(
                    r"removed from the field by your effect|因為自己的效果離開|因为自己的效果离开",
                    blob,
                    _re.I,
                ):
                    out_yt["on_char_leave_by_own_effect"] = True
                m_hand = _re.search(
                    r"(\d+)\s+or more cards in their hand|手牌有\s*(\d+)\s*[張张]以上",
                    blob,
                    _re.I,
                )
                if m_hand:
                    out_yt["require_opp_hand_gte"] = int(next(g for g in m_hand.groups() if g))
                if _re.search(
                    r"rest this Character|將這張角色卡置為休息|将这张角色卡置为休息",
                    blob,
                    _re.I,
                ):
                    ops2 = list(out_yt["ops"])
                    ops2.append({"op": "rest_character", "target_kind": "self", "optional": False})
                    out_yt["ops"] = sanitize_ops_list(ops2)
                return out_yt
        # Reaction / your-turn event clauses beyond hand-to-bottom.
        if _re.search(r"\[your turn\]|【我方回合中】", blob, _re.I):
            from battle.effects import (
                _parse_hand_to_deck_ops,
                _parse_skip_untap_ops,
            )

            ops_evt: list[dict[str, Any]] = []
            if _re.search(r"draw 1|抽1", blob, _re.I):
                ops_evt.append({"op": "draw", "count": 1})
            ops_evt.extend(_parse_hand_to_deck_ops(blob))
            ops_evt.extend(_parse_skip_untap_ops(blob))
            from battle.effects import _parse_life_zone_ops

            life_ops = _parse_life_zone_ops(blob)
            for o in life_ops:
                if not any(x.get("op") == o.get("op") and x.get("owner") == o.get("owner") for x in ops_evt):
                    ops_evt.append(o)
            # Life → hand (treat as add_life reverse: deal from life to hand via add_life from life zone — approximate as draw from life)
            if _re.search(
                r"add 1 card from the top of your Life cards to your hand|"
                r"將1張自己生命值區上面的卡片加入手牌|将1张自己生命值区上面的卡片加入手牌",
                blob,
                _re.I,
            ) and not any(o.get("op") == "life_to_hand" for o in ops_evt):
                ops_evt.append({"op": "life_to_hand", "count": 1, "position": "top", "optional": True})
            if ops_evt and not ops:
                out_evt: dict[str, Any] = {
                    "timing": "your_turn",
                    "summary": blob.strip()[:240],
                    "ops": sanitize_ops_list(ops_evt),
                    "status": "compiled",
                    "confidence": 0.7,
                    "once": bool(_re.search(r"once per turn|每回合1次", blob, _re.I)),
                }
                return out_evt
            if ops:  # hand-to-bottom reaction already built
                pass

        aura = parse_negate_on_play_aura(info)
        if aura:
            return {**aura, "ops": sanitize_ops_list(list(aura.get("ops") or []))}
        # Static trash-gated self buff + cost grant (OP14-086).
        if _re.search(r"\[your turn\]|【我方回合中】", blob, _re.I) or _re.search(
            r"if you have\s*\d+\s*or more cards in your trash|"
            r"廢棄區有\s*\d+\s*[張张]以上|废弃区有\s*\d+\s*[张张]以上",
            blob,
            _re.I,
        ):
            from battle.effects import _parse_grant_cost_ops

            ops_yt: list[dict[str, Any]] = []
            m_buff = _re.search(
                r"this Character gains?\s*\+?(\d+)\s*power|這張角色卡的力量值\+(\d+)|这张角色卡的力量值\+(\d+)",
                blob,
                _re.I,
            )
            if m_buff:
                ops_yt.append({"op": "buff_self", "amount": int(next(g for g in m_buff.groups() if g))})
            ops_yt.extend(_parse_grant_cost_ops(blob))
            if ops_yt:
                out_static: dict[str, Any] = {
                    "timing": "your_turn",
                    "summary": blob.strip()[:240],
                    "ops": sanitize_ops_list(ops_yt),
                    "status": "compiled",
                    "confidence": 0.8,
                }
                m_tr = _re.search(
                    r"(\d+)\s+or more cards in your trash|廢棄區有\s*(\d+)\s*[張张]以上|废弃区有\s*(\d+)\s*[张张]以上",
                    blob,
                    _re.I,
                )
                if m_tr:
                    out_static["require_trash_gte"] = int(next(g for g in m_tr.groups() if g))
                return out_static
        parsed = parse_don_static_power(info)
        return parsed if parsed and parsed.get("timing") == "your_turn" else None
    if timing == "hand_cost":
        from battle.effects import parse_board_hand_cost_aura, parse_hand_cost_reduce

        for parser in (parse_hand_cost_reduce, parse_board_hand_cost_aura):
            parsed = parser(info)
            if parsed:
                return {
                    **parsed,
                    "ops": sanitize_ops_list(list(parsed.get("ops") or [])),
                }
        return None
    if timing == "don_attached":
        parsed = parse_don_static_power(info)
        return parsed if parsed and parsed.get("timing") == "don_attached" else None
    if timing == "on_don_attached":
        import re as _re

        from battle.effects import (
            _parse_cost_reduce_family_ops,
            _parse_place_on_bottom_ops,
            _parse_return_char_to_hand_ops,
            parse_any_don_attach_cost_trigger,
        )

        any_don = parse_any_don_attach_cost_trigger(info)
        if any_don:
            return {
                **any_don,
                "ops": sanitize_ops_list(list(any_don.get("ops") or [])),
            }

        blob = effect_blob(info)
        m = _re.search(
            r"(?:\[when (?:this card is )?don!! attached\]|【咚‼?附加時】|【咚附加时】)([^【\[]{0,220})",
            blob,
            _re.I,
        )
        if not m:
            return None
        chunk = m.group(0)
        ops: list[dict[str, Any]] = []
        if _re.search(r"draw 2|抽2", chunk, _re.I):
            ops.append({"op": "draw", "count": 2})
        elif _re.search(r"draw 1|抽1", chunk, _re.I):
            ops.append({"op": "draw", "count": 1})
        if _re.search(r"(?:gains?\s*\+1000|power\s*\+1000|力量[值]?\s*\+1000)", chunk, _re.I):
            ops.append({"op": "buff_self", "amount": 1000})
        ops.extend(_parse_place_on_bottom_ops(chunk))
        ops.extend(_parse_return_char_to_hand_ops(chunk))
        ops.extend(_parse_cost_reduce_family_ops(chunk))
        if not ops:
            return None
        return {
            "timing": "on_don_attached",
            "summary": chunk.strip()[:240],
            "ops": sanitize_ops_list(ops),
            "status": "compiled",
            "confidence": 0.7,
        }
    if timing == "on_ko":
        parsed = parse_on_ko(info)
        if not parsed:
            return None
        return {
            **parsed,
            "ops": sanitize_ops_list(list(parsed.get("ops") or [])),
        }
    if timing == "counter_event":
        import re as _re

        from battle.effects import (
            _parse_deny_attack_ops,
            _parse_deny_rest_ops,
            _parse_ko_op,
            _parse_ko_own_any_buff_leader_ops,
            _parse_leader_or_char_buff,
            _parse_place_on_bottom_ops,
            _parse_replace_battle_ko_ops,
            _parse_return_char_to_hand_ops,
            _parse_skip_untap_ops,
            parse_main_event as _parse_main_event_for_counter,
        )

        blob = effect_blob(info)
        if not _re.search(r"\[counter\]|【反撃】|【反击】", blob, _re.I):
            return None
        m = _re.search(
            r"(?:\[counter\]|【反撃】|【反击】)"
            r"((?:(?!(?:^|[\n\r/])\s*\[(?:on\s+play|when\s+attacking|activate|trigger|main)|"
            r"(?:^|[\n\r/])\s*【(?:登場時|登场时|攻擊時|攻击时|啟動主要|启动主要|觸發器|触发器|主要)】).){0,400})",
            blob,
            _re.I | _re.S | _re.M,
        )
        if not m:
            return None
        chunk = m.group(0)
        # Shared [Main]/[Counter] body — Counter marker has little/no unique body.
        if len(chunk.strip()) < 24 or _re.fullmatch(
            r"(?:\[counter\]|【反撃】|【反击】)\s*", chunk.strip(), _re.I
        ):
            main_ops = _parse_main_event_for_counter(info)
            if main_ops:
                return {
                    "timing": "counter_event",
                    "summary": (info.get("effect_en") or info.get("effect") or "")[:240],
                    "ops": sanitize_ops_list(main_ops),
                    "status": "compiled",
                    "confidence": 0.75,
                }
            return None
        ops: list[dict[str, Any]] = []
        buff = _parse_leader_or_char_buff(chunk)
        if buff:
            ops.append(buff)
        if _re.search(r"draw 2|抽2", chunk, _re.I):
            ops.append({"op": "draw", "count": 2})
        elif _re.search(r"draw 1|抽1", chunk, _re.I):
            ops.append({"op": "draw", "count": 1})
        ops.extend(_parse_place_on_bottom_ops(chunk))
        ops.extend(_parse_return_char_to_hand_ops(chunk))
        ops.extend(_parse_replace_battle_ko_ops(blob))
        ops.extend(_parse_skip_untap_ops(blob))
        ops.extend(_parse_ko_own_any_buff_leader_ops(chunk))
        ops.extend(_parse_deny_attack_ops(chunk))
        ops.extend(_parse_deny_rest_ops(chunk))
        ko = _parse_ko_op(chunk)
        if ko:
            ops.append(ko)
        if not ops:
            # Marker present but body lives under [Main]/ — reuse main parse.
            main_ops = _parse_main_event_for_counter(info)
            if main_ops:
                ops = main_ops
        if not ops:
            return None
        return {
            "timing": "counter_event",
            "summary": chunk.strip()[:240],
            "ops": sanitize_ops_list(ops),
            "status": "compiled",
            "confidence": 0.75,
        }
    return None


def ability_needs_confirm(ability: dict[str, Any] | None, info: dict[str, Any] | None = None) -> bool:
    """True if ability is 「可以發動」and must pause for controller accept/decline."""
    if not ability:
        return False
    if ability.get("optional") or ability.get("may_activate") or ability.get("uncertain"):
        return True
    timing_early = str(ability.get("timing") or "").strip().lower()
    if timing_early in {"when_attacking", "on_opponent_attack", "on_play"}:
        # Paper "DON!! −N:" is a chosen cost, not a forced trigger.
        for o in ability.get("ops") or []:
            if isinstance(o, dict) and o.get("op") == "return_don" and o.get("as_cost"):
                return True
    summary = str(ability.get("summary") or "")
    if re.search(
        r"可以發動|可以发动|this effect can be activated|you may activate|you may trash|may trash self",
        summary,
        re.I,
    ):
        return True
    blob = ""
    if info is not None:
        try:
            blob = effect_blob(info) or str(info.get("effect") or "")
        except Exception:
            blob = str(info.get("effect") or "")
    if not blob:
        return False

    actionable = {
        "draw",
        "play_from_hand",
        "attach_don",
        "trash",
        "grant_keyword",
        "buff",
        "buff_self",
        "search_deck",
        "trash_hand",
        "life_to_hand",
        "trash_life",
        "trash_deck_top",
        "return_to_hand",
        "ko",
        "rest_character",
        "active_character",
    }
    ops = [str(o.get("op") or "") for o in (ability.get("ops") or []) if isinstance(o, dict)]
    has_action = any(o in actionable for o in ops)
    # Continuous auras (grant_cost / permanent blocker) must not pause.
    if not has_action:
        return False

    timing = str(ability.get("timing") or "").strip().lower()
    timing_cues = {
        "on_opponent_attack": r"【對方攻擊時】|【对手攻击时】|對手攻擊時|对手攻击时|\[On Your Opponent's Attack\]|when your opponent attacks|對手的角色卡攻擊時|对手的角色卡攻击时",
        "on_block": r"【防禦】時|【防御】时|when (?:this Character )?blocks|\[On Block\]|對手的角色卡攻擊時|对手的角色卡攻击时",
        "when_attacking": r"【攻擊時】|【攻击时】|\[When Attacking\]",
        "on_ko": r"【KO時】|【KO时】|\[On K\.O\.\]",
        "on_life_damage": r"生命值受到傷害時|生命值受到伤害时",
        "on_opp_event": r"對手發動事件卡|对手发动事件卡",
        "on_opp_trigger": r"對手發動.{0,8}觸發|对手发动.{0,8}触发",
        "on_event": r"自己發動事件|发动事件卡时",
        "on_trigger": r"自己發動【觸發|发动【触发",
        "end_of_your_turn": r"自己的回合結束時|自己的回合结束时|\[End of Your Turn\]",
        "end_of_opponent_turn": r"對手的回合結束時|对手的回合结束时",
        "turn_start": r"我方回合開始時|我方回合开始时|回合開始時|\[Start of Your Turn\]",
        "main_start": r"主要階段開始時|主要阶段开始时",
        "on_opponent_play": r"對手使.{0,30}登場時|对手使.{0,30}登场时",
        "on_don_returned": r"咚‼?卡放回|DON!!.*returned",
        "on_don_attached": r"咚‼?卡被附加時",
    }
    cue = timing_cues.get(timing)
    if cue:
        for m in re.finditer(cue, blob, re.I):
            window = blob[m.start() : m.start() + 120]
            if re.search(r"可以發動|可以发动|you may activate|可以廢棄|可以废弃|可將|可将|you may rest|you may trash", window, re.I):
                return True

    # once-per-turn reactive abilities: if paper has 可以發動 anywhere, require confirm
    if ability.get("once") and re.search(r"可以發動|可以发动|this effect can be activated", blob, re.I):
        return True

    # Watcher abilities encoded as your_turn/opponent_turn with once / on_* flags.
    if timing in {"your_turn", "opponent_turn"} and (
        ability.get("once")
        or ability.get("trigger_on")
        or ability.get("on_own_play_character")
        or ability.get("on_opp_play_character")
        or ability.get("on_hand_trash_by_own_effect")
        or ability.get("on_hand_trashed_by_effect")
        or ability.get("on_life_leave")
        or ability.get("on_opp_blocker")
        or ability.get("on_opp_blocker_or_event")
        or ability.get("on_own_trait_leave_or_ko")
        or ability.get("on_char_leave_by_own_effect")
        or any(isinstance(o, dict) and o.get("on_life_leave") for o in (ability.get("ops") or []))
    ):
        if re.search(
            r"(?:離開場上時|离开场上时|登場時|登场时|生命值卡離開時|置為休息狀態時|置为休息状态时|遭到KO時|遭到KO时|"
            r"對手的角色卡攻擊時|对手的角色卡攻击时).{0,40}可以發動|"
            r"可以發動.{0,40}(?:離開|离开|登場|登场|休息|KO)|"
            r"【每回合1次】.{0,60}可以發動|"
            r"置為休息狀態時，可以發動|置为休息状态时，可以发动",
            blob,
            re.I,
        ):
            return True
    return False


def resolve_ability(
    state: MatchState,
    seat: int,
    card_id: str,
    source_iid: str,
    timing: str,
    info: dict[str, Any],
    ask_llm: LlmFn = None,
    *,
    allow_llm: bool = True,
    catalog: CatalogFn | None = None,
    trigger_on: str | None = None,
) -> PendingEffect | None:
    """
    Resolve order: overrides/library → deterministic templates → None.
    Live LLM is not used in-match.
    """
    timing = timing.strip().lower()
    if timing not in TIMINGS:
        return None

    player = state.player(seat)
    # Negation gates
    if timing == "on_play" and player.negate_on_play:
        return None
    try:
        from battle.engine import inst_effects_negated

        if inst_effects_negated(player, source_iid):
            return None
    except Exception:
        if source_iid == "leader" and player.leader_effects_negated:
            return None
        if source_iid != "leader":
            inst_neg = next((c for c in player.characters if c.iid == source_iid), None)
            if inst_neg and inst_neg.effects_negated:
                return None

    def _leader_trait_ok(ability: dict[str, Any]) -> bool:
        trait = str(ability.get("require_leader_trait") or "").strip()
        if not trait or catalog is None:
            return True
        try:
            from battle.engine import _info_has_trait

            return _info_has_trait(catalog(state.player(seat).leader_card_id), trait)
        except Exception:
            return True

    def _board_gates_ok(ability: dict[str, Any]) -> bool:
        if catalog is None:
            # Fall back to leader trait + don only when no catalog.
            return _leader_trait_ok(ability) and _don_gate_ok(ability)
        try:
            from battle.engine import _ability_board_conditions_ok

            don = 0
            if source_iid == "leader":
                don = int(state.player(seat).leader_don or 0)
            else:
                inst = next((c for c in state.player(seat).characters if c.iid == source_iid), None)
                don = int(inst.don_attached or 0) if inst else 0
            return _ability_board_conditions_ok(
                state, seat, ability, catalog, don_attached=don, source_iid=source_iid
            )
        except Exception:
            return _leader_trait_ok(ability) and _don_gate_ok(ability)

    def _don_gate_ok(ability: dict[str, Any]) -> bool:
        need = int(ability.get("require_don_attached_gte") or 0)
        if need <= 0:
            return True
        player = state.player(seat)
        if source_iid == "leader":
            return player.leader_don >= need
        inst = next((c for c in player.characters if c.iid == source_iid), None)
        return bool(inst and inst.don_attached >= need)

    def _once_ok(ability: dict[str, Any]) -> bool:
        if not ability.get("once"):
            return True
        player = state.player(seat)
        if source_iid == "leader":
            return not player.leader_once_used
        inst = next((c for c in player.characters if c.iid == source_iid), None)
        if inst is not None:
            return not inst.once_used
        stage = next((s for s in player.stages if s.iid == source_iid), None)
        return bool(stage is None or not stage.once_used)

    def _trigger_on_ok(ability: dict[str, Any]) -> bool:
        # self_rested abilities only fire when trigger_on="self_rested" is passed.
        want = str(ability.get("trigger_on") or "").strip().lower()
        if trigger_on == "self_rested":
            return want == "self_rested"
        if trigger_on == "opp_blocker":
            return bool(ability.get("on_opp_blocker") or ability.get("on_opp_blocker_or_event"))
        if trigger_on == "opp_blocker_or_event":
            return bool(ability.get("on_opp_blocker_or_event") or ability.get("on_opp_blocker"))
        if trigger_on == "own_play_character":
            return bool(ability.get("on_own_play_character"))
        if trigger_on == "opp_play_character":
            return bool(ability.get("on_opp_play_character"))
        if trigger_on == "life_leave":
            if ability.get("on_life_leave"):
                return True
            return any(isinstance(o, dict) and o.get("on_life_leave") for o in (ability.get("ops") or []))
        # Passive "your_turn"/"opponent_turn" continuous must not auto-run event watchers.
        if ability.get("on_opp_blocker") or ability.get("on_opp_blocker_or_event"):
            return False
        if ability.get("on_own_play_character") or ability.get("on_opp_play_character"):
            return False
        if ability.get("on_hand_trash_by_own_effect"):
            return False
        if ability.get("on_hand_trashed_by_effect"):
            return False
        if ability.get("on_life_leave") or any(
            isinstance(o, dict) and o.get("on_life_leave") for o in (ability.get("ops") or [])
        ):
            return False
        if ability.get("on_own_trait_leave_or_ko") or ability.get("on_char_leave_by_own_effect"):
            return False
        if ability.get("on_opp_ko") or any(
            isinstance(o, dict) and o.get("on_opp_ko") for o in (ability.get("ops") or [])
        ):
            return False
        return want != "self_rested"

    # 1) Curated library / overrides — scan ALL abilities for this timing.
    # lookup_runnable_ability only returns the first; cards like OP15-119 pair a
    # continuous Rush aura with a separate on_opp_blocker watcher on your_turn.
    lib_abilities = [a for a in get_abilities(card_id, timing) if ability_is_runnable(a)]
    for ability in lib_abilities:
        if not _board_gates_ok(ability) or not _once_ok(ability) or not _trigger_on_ok(ability):
            continue
        ops = _annotate_ops(list(ability.get("ops") or []), card_id, source_iid, str(ability.get("summary") or ""))
        ops = _annotate_ops(_ensure_colon_cost_ops(ops, info), card_id, source_iid, str(ability.get("summary") or ""))
        if ops:
            return PendingEffect(
                effect_id=new_iid("fx"),
                seat=seat,
                card_id=card_id,
                source_iid=source_iid,
                summary=str(ability.get("summary") or f"{timing}")[:240],
                ops=ops,
                uncertain=ability_needs_confirm(ability, info),
                once=bool(ability.get("once")),
            )
    if lib_abilities:
        # Curated entry exists for this timing; do not fall through to templates.
        return None

    # 2) Deterministic templates
    templated = _from_templates(card_id, timing, info)
    if (
        templated
        and ability_is_runnable(templated)
        and _board_gates_ok(templated)
        and _once_ok(templated)
        and _trigger_on_ok(templated)
    ):
        ops = _annotate_ops(list(templated.get("ops") or []), card_id, source_iid, str(templated.get("summary") or ""))
        ops = _annotate_ops(_ensure_colon_cost_ops(ops, info), card_id, source_iid, str(templated.get("summary") or ""))
        return PendingEffect(
            effect_id=new_iid("fx"),
            seat=seat,
            card_id=card_id,
            source_iid=source_iid,
            summary=str(templated.get("summary") or timing)[:240],
            ops=ops,
            uncertain=ability_needs_confirm(templated, info),
            once=bool(templated.get("once")),
        )

    # Live LLM is intentionally not used in-match. Resolution is:
    # curated library / overrides → deterministic templates only.
    # (Offline compile tools may still call propose_complex_effect directly.)

    # 3) Keyword-only cards: no structured effect
    blob = effect_blob(info)
    if detect_keywords(info) and len(blob) < 80:
        return None

    # Unsupported / missing — log via empty return; caller may add log
    return None


def resolve_activate_spec(card_id: str, info: dict[str, Any]) -> dict[str, Any] | None:
    """Activate: Main metadata + ops from library or parser."""
    from battle.effect_schema import _copy_ability_gates

    ability = lookup_runnable_ability(card_id, "activate_main")
    parsed = parse_activate_main(info)
    if ability:
        out = {
            "cost_don": int(ability.get("cost_don") or (parsed or {}).get("cost_don") or 0),
            "rest_self": bool(ability.get("rest_self") if "rest_self" in ability else (parsed or {}).get("rest_self")),
            "once": bool(ability.get("once") if "once" in ability else (parsed or {}).get("once")),
            "ops": list(ability.get("ops") or []),
            "summary": str(ability.get("summary") or (parsed or {}).get("summary") or "Activate: Main"),
        }
        _copy_ability_gates(ability, out)
        if parsed:
            gate_only = {}
            _copy_ability_gates(parsed, gate_only)
            for key, val in gate_only.items():
                if key not in out and val is not None:
                    out[key] = val
        if ability.get("require_char_power_gte") is not None:
            out["require_char_power_gte"] = ability["require_char_power_gte"]
        elif parsed and parsed.get("require_char_power_gte") is not None:
            out["require_char_power_gte"] = parsed["require_char_power_gte"]
        return out
    if parsed:
        return parsed
    return None


def resolve_trigger_ops(card_id: str, info: dict[str, Any]) -> list[dict[str, Any]]:
    ability = lookup_runnable_ability(card_id, "trigger")
    if ability:
        return list(ability.get("ops") or [])
    templated = _from_templates(card_id, "trigger", info)
    if templated:
        return list(templated.get("ops") or [])
    return parse_trigger_ops(info)


def compile_card_from_templates(card_id: str, info: dict[str, Any]) -> dict[str, Any]:
    """Offline helper: build a card_effects entry from deterministic parsers only."""
    from battle.effects import (
        parse_any_don_attach_cost_trigger,
        parse_board_hand_cost_aura,
        parse_hand_cost_reduce,
        parse_negate_on_play_aura,
        parse_static_opp_cost_reduce,
        parse_untimed_static,
        _parse_play_cost_aura,
    )

    abilities: list[dict[str, Any]] = []
    for timing in (
        "on_play",
        "activate_main",
        "trigger",
        "when_attacking",
        "on_block",
        "on_opponent_attack",
        "on_ko",
        "end_of_your_turn",
        "end_of_opponent_turn",
        "turn_start",
        "main_start",
        "counter_event",
        "your_turn",
        "opponent_turn",
        "don_attached",
        "on_don_attached",
        "on_don_phase",
        "hand_cost",
    ):
        a = _from_templates(card_id, timing, info)
        if a:
            na = normalize_ability(a)
            if na:
                abilities.append(na)
    # Extra continuous / hand-cost parses that can coexist with other same-timing abilities.
    extras: list[dict[str, Any] | None] = [
        parse_static_opp_cost_reduce(info),
        parse_don_static_power(info),
        parse_hand_cost_reduce(info),
        parse_board_hand_cost_aura(info),
        parse_any_don_attach_cost_trigger(info),
        _parse_play_cost_aura(info),
        parse_untimed_static(info),
        parse_negate_on_play_aura(info),
    ]
    seen_keys: set[tuple[Any, ...]] = set()
    for a in abilities:
        key = (
            a.get("timing"),
            tuple((o.get("op"), o.get("amount")) for o in (a.get("ops") or [])),
            a.get("require_don_attached_gte"),
            a.get("hand_color"),
        )
        seen_keys.add(key)
    for raw in extras:
        if not raw:
            continue
        na = normalize_ability(raw)
        if not na or not ability_is_runnable(na):
            continue
        key = (
            na.get("timing"),
            tuple((o.get("op"), o.get("amount")) for o in (na.get("ops") or [])),
            na.get("require_don_attached_gte"),
            na.get("hand_color"),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        abilities.append(na)
    # Stub any timing markers present in text that still lack a runnable ability.
    blob = effect_blob(info)
    present = {str(a.get("timing")) for a in abilities}
    for timing in sorted(detect_timings_in_text(blob)):
        existing = next((a for a in abilities if a.get("timing") == timing), None)
        if existing and ability_is_runnable(existing):
            continue
        if existing and existing.get("status") == "unsupported":
            continue
        stub = normalize_ability(_unsupported_stub(timing, f"complex_{timing}"))
        if not stub:
            continue
        if existing:
            abilities = [stub if a.get("timing") == timing else a for a in abilities]
        else:
            abilities.append(stub)
            present.add(timing)
    return normalize_card_entry(card_id, {"version": 1, "abilities": abilities})
