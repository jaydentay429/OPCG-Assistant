"""Full-library effect fidelity: extract paper signals from text and diff vs library."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Callable

from battle.effect_library import compile_card_from_templates, detect_timings_in_text
from battle.effect_schema import ability_is_runnable
from battle.effects import (
    _parse_exclude_name,
    _parse_replace_leave_ops,
    effect_blob,
    has_meaningful_effect_text,
)

GATE_PATTERNS: list[tuple[str, re.Pattern[str], Callable[[re.Match[str]], int]]] = [
    (
        "require_life_lte",
        re.compile(
            r"(?:have|with)\s*(\d+)\s*or less Life|Life cards?,?\s*(\d+)\s*or less|"
            r"生命值卡在\s*(\d+)\s*張以下|生命值卡在\s*(\d+)\s*张以下",
            re.I,
        ),
        lambda m: int(next(g for g in m.groups() if g)),
    ),
    (
        "require_life_gte",
        re.compile(
            r"(?:have|with)\s*(\d+)\s*or more Life|Life cards?,?\s*(\d+)\s*or more|"
            r"生命值卡在\s*(\d+)\s*張以上|生命值卡在\s*(\d+)\s*张以上",
            re.I,
        ),
        lambda m: int(next(g for g in m.groups() if g)),
    ),
    (
        "require_trash_gte",
        re.compile(
            r"(\d+)\s*or more cards? in your trash|trash.{0,12}(\d+)\s*or more|"
            r"廢棄區有\s*(\d+)\s*張以上|废弃区有\s*(\d+)\s*张以上",
            re.I,
        ),
        lambda m: int(next(g for g in m.groups() if g)),
    ),
    (
        "require_don_field_gte",
        re.compile(
            r"(\d+)\s*or more DON!! cards? on your field|"
            r"場上有\s*(\d+)\s*張以上咚|场上有\s*(\d+)\s*张以上咚",
            re.I,
        ),
        lambda m: int(next(g for g in m.groups() if g)),
    ),
    (
        "require_don_attached_gte",
        re.compile(
            r"\[DON!!\s*x\s*(\d+)\]|【咚‼?\s*[×xX]\s*(\d+)】",
            re.I,
        ),
        lambda m: int(next(g for g in m.groups() if g)),
    ),
    (
        "require_rested_own_chars_gte",
        re.compile(
            r"(\d+)\s*or more rested Characters|"
            r"(\d+)\s*張以上.{0,8}休息狀態的角色|(\d+)\s*张以上.{0,8}休息状态的角色|"
            r"場上有\s*(\d+)\s*張以上自己休息|场上有\s*(\d+)\s*张以上自己休息",
            re.I,
        ),
        lambda m: int(next(g for g in m.groups() if g)),
    ),
    (
        "require_opp_life_lte",
        re.compile(
            r"opponent has\s*(\d+)\s*or less Life|對手的生命值卡在\s*(\d+)\s*張以下|对手的生命值卡在\s*(\d+)\s*张以下",
            re.I,
        ),
        lambda m: int(next(g for g in m.groups() if g)),
    ),
    (
        "require_total_life_lte",
        re.compile(
            r"you and your opponent have a total of\s*(\d+)\s*or less Life|"
            r"雙方的生命值卡合計張數在\s*(\d+)\s*張以下|双方的生命值卡合计张数在\s*(\d+)\s*张以下",
            re.I,
        ),
        lambda m: int(next(g for g in m.groups() if g)),
    ),
    (
        "require_either_don_field_gte",
        re.compile(
            r"(?:you or your opponent|either player).{0,40}(\d+)\s*DON|"
            r"自己或對手的場上有\s*(\d+)\s*張(?:以上)?咚|"
            r"自己或对手的场上有\s*(\d+)\s*张(?:以上)?咚",
            re.I,
        ),
        lambda m: int(next(g for g in m.groups() if g)),
    ),
]

OP_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("choose_one", re.compile(r"choose one|選擇下列|选择下列|Your opponent chooses|對手選擇|对手选择", re.I)),
    (
        "attack_tax",
        re.compile(
            r"cannot attack unless.{0,60}trash|can attack unless.{0,60}trash|"
            r"must trash\s*\d+.{0,40}hand.{0,60}attack|"
            r"trashes?\s*\d+\s*cards? from (?:their |your opponent'?s )?hand.{0,40}attack|"
            r"要進行攻擊時.{0,20}必須廢棄|要进行攻击时.{0,20}必须废弃|"
            r"廢棄\d+張.{0,16}手牌才可以進行攻擊|废弃\d+张.{0,16}手牌才可以进行攻击",
            re.I,
        ),
    ),
    ("deny_attack", re.compile(r"cannot attack|無法進行攻擊|无法进行攻击|不能攻擊|不能攻击", re.I)),
    ("deny_rest", re.compile(r"cannot be rested|無法置為休息|无法置为休息|無法為休息|无法为休息", re.I)),
    (
        "trash_life",
        re.compile(
            r"trash\s*(?:up to\s*)?\d+\s*cards? from the (?:top or bottom|top|bottom) of (?:your |your opponent'?s |each of your and your opponent'?s )?Life|"
            r"you may trash\s*\d+\s*cards? from the (?:top or bottom|top|bottom) of your Life|"
            r"(?:可[將将])?\s*\d+\s*[張张]自己生命值區(?:上面或下面|上面|下面)的卡片放置[在到]廢棄區|"
            r"(?:將|将)(?:最多)?\s*\d+\s*[張张](?:對手|对手|自己)?生命值區上面的卡片放置在廢棄區|"
            r"雙方各自將\s*\d+\s*[張张]生命值區上面|双方各自将\s*\d+\s*[张张]生命值区上面",
            re.I,
        ),
    ),
    (
        "hand_to_life",
        re.compile(
            r"add\s*(?:up to\s*)?\d*.{0,40}from your hand.{0,40}Life|"
            r"手牌加入生命值|將最多\s*\d*\s*張?自己的?手牌加入生命|将最多\s*\d*\s*张?自己的?手牌加入生命",
            re.I,
        ),
    ),
    (
        "place_on_life",
        re.compile(
            r"place up to\s*\d+\s+of your opponent'?s Characters?.{0,80}"
            r"(?:top or bottom|top|bottom) of your opponent'?s Life|"
            r"(?:將|将)最多\s*\d+\s*[張张]對手.{0,40}角色卡.{0,40}生命值區的(?:上面或下面|上面|下面)|"
            r"(?:將|将)最多\s*\d+\s*[张張]对手.{0,40}角色卡.{0,40}生命值区的(?:上面或下面|上面|下面)",
            re.I,
        ),
    ),
    ("life_to_hand", re.compile(
        r"(?:add|place) up to\s*\d*.{0,24}(?:card )?from .{0,20}Life.{0,30}hand|"
        r"you may add\s*\d*.{0,24}from .{0,20}Life.{0,20}hand|"
        r"將最多.{0,20}生命值區.{0,24}加入(?:持有者的)?手牌|将最多.{0,20}生命值区.{0,24}加入(?:持有者的)?手牌|"
        r"可將\d*.{0,12}生命值區.{0,16}加入手牌|可将\d*.{0,12}生命值区.{0,16}加入手牌",
        re.I,
    )),
    ("set_cost", re.compile(r"set the cost of.{0,60}to\s*0|費用.{0,12}(?:成|為|为)\s*0|费用.{0,12}(?:成|为)\s*0", re.I)),
    ("skip_untap", re.compile(r"will not become active|無法為活動|无法为活动|跳過重整|跳过重整", re.I)),
    ("flip_life", re.compile(r"turn\s*\d*.{0,30}Life.{0,20}face[- ]?(?:up|down)|生命值區.{0,16}翻成", re.I)),
    ("redirect_attack", re.compile(r"change the (?:target|attack target)|將攻擊的對象換成|将攻击的对象换成", re.I)),
    ("activate_timing", re.compile(r"activate this card'?s|發動這張卡片的|发动这张卡片的", re.I)),
]


def base_card_id(card_id: str) -> str:
    return re.sub(r"-(?:P|R)\d+$", "", card_id)


def extract_expected_signals(info: dict[str, Any]) -> dict[str, Any]:
    """Derive paper-rule signals from card text (independent of library)."""
    blob = effect_blob(info)
    timings = sorted(detect_timings_in_text(blob))
    gates: dict[str, int] = {}
    for key, pat, cast in GATE_PATTERNS:
        m = pat.search(blob)
        if m:
            try:
                gates[key] = cast(m)
            except Exception:
                pass

    m_lead_trait = re.search(
        r"Leader(?:'s type)? (?:has|includes|is).{0,6}\{\s*([^}]+)\s*\}|"
        r"領航卡擁有《([^》]+)》|领航卡拥有《([^》]+)》|"
        r"Leader is \[([^\]]+)\]|領航卡是「([^」]+)」|领航卡是「([^」]+)」",
        blob,
        re.I,
    )
    leader_trait = ""
    leader_name = ""
    if m_lead_trait:
        g = next((x for x in m_lead_trait.groups() if x), "")
        # Name form uses [Name] / 「名」; trait uses {Trait} / 《》
        span = m_lead_trait.group(0)
        if re.search(r"\{|《", span):
            leader_trait = g.strip()
        else:
            leader_name = g.strip()

    op_hints = [name for name, pat in OP_HINTS if pat.search(blob)]
    # deny_attack = force opponent units not to attack. Drop self/taunt/self-target limits.
    if "deny_attack" in op_hints:
        real_deny_attack = bool(
            re.search(
                r"(?:up to\s*\d+\s+of\s+)?(?:your )?opponent'?s (?:Characters?|Leaders?).{0,60}cannot attack|"
                r"your opponent cannot attack (?!any card other than)|"
                r"最多\s*\d*\s*張?對手.{0,40}無法進行攻擊|最多\s*\d*\s*张?对手.{0,40}无法进行攻击|"
                r"對手的(?:角色|領航).{0,40}無法進行攻擊|对手的(?:角色|领航).{0,40}无法进行攻击",
                blob,
                re.I,
            )
        )
        if not real_deny_attack:
            op_hints = [h for h in op_hints if h != "deny_attack"]
    # deny_rest = opponent Characters cannot be rested (not self immunity to rest).
    if "deny_rest" in op_hints:
        real_deny_rest = bool(
            re.search(
                r"(?:up to\s*\d+\s+of\s+)?(?:your )?opponent'?s Characters?.{0,80}cannot be rested|"
                r"最多\s*\d*\s*張?對手.{0,40}無法置為休息|最多\s*\d*\s*张?对手.{0,40}无法置为休息",
                blob,
                re.I,
            )
        )
        if not real_deny_rest:
            op_hints = [h for h in op_hints if h != "deny_rest"]
    # "trash Life instead of leave/K.O." is a replacement shield, not trash_life effect.
    if "trash_life" in op_hints and re.search(
        r"would be (?:k\.?o\.?'?d|leave the field|removed from the field).{0,120}"
        r"trash .{0,40}Life.{0,40}instead|"
        r"(?:即將遭到KO|即將離開場上|即将遭到KO|即将离开场上).{0,60}替換.{0,40}生命值|"
        r"(?:即將遭到KO|即將離開場上|即将遭到KO|即将离开场上).{0,60}替换.{0,40}生命值",
        blob,
        re.I,
    ):
        op_hints = [h for h in op_hints if h != "trash_life"]
    # Life→hand paid as leave/KO-replacement is replace_leave, not life_to_hand effect.
    if "life_to_hand" in op_hints and re.search(
        r"would be (?:removed from the field|k\.?o\.?'?d).{0,120}"
        r"add .{0,40}Life.{0,40}hand|"
        r"(?:即將離開場上|即將遭到KO|即将离开场上|即将遭到KO).{0,60}生命值區.{0,24}加入手牌|"
        r"(?:即將離開場上|即將遭到KO|即将离开场上|即将遭到KO).{0,60}生命值区.{0,24}加入手牌",
        blob,
        re.I,
    ):
        op_hints = [h for h in op_hints if h != "life_to_hand"]
    # Flip Life paid as leave-replacement is replace_leave, not flip_life effect.
    if "flip_life" in op_hints and re.search(
        r"would be (?:removed from the field|k\.?o\.?'?d|leave the field).{0,120}"
        r"turn .{0,40}Life.{0,30}face|"
        r"(?:即將離開場上|即將遭到KO|即将离开场上|即将遭到KO).{0,60}生命值區.{0,24}翻成|"
        r"(?:即將離開場上|即將遭到KO|即将离开场上|即将遭到KO).{0,60}生命值区.{0,24}翻成",
        blob,
        re.I,
    ):
        op_hints = [h for h in op_hints if h != "flip_life"]
    # Only hint replace_leave when the dedicated parser recognizes the shield.
    if _parse_replace_leave_ops(blob) and "replace_leave" not in op_hints:
        op_hints.append("replace_leave")
    # Also treat battle-KO → Life-to-hand as replace_leave.
    if re.search(
        r"would be k\.?o\.?'?d in battle.{0,100}add .{0,40}Life.{0,40}hand|"
        r"在對戰中遭到KO時.{0,60}生命值區.{0,24}加入手牌|"
        r"在对战中遭到KO时.{0,60}生命值区.{0,24}加入手牌",
        blob,
        re.I,
    ):
        op_hints = [h for h in op_hints if h != "life_to_hand"]
        if "replace_leave" not in op_hints:
            op_hints.append("replace_leave")
    exclude_name = _parse_exclude_name(blob) or ""
    chooser_opponent = bool(re.search(r"Your opponent chooses|對手選擇|对手选择", blob, re.I))

    return {
        "timings": timings,
        "gates": gates,
        "leader_trait": leader_trait,
        "leader_name": leader_name,
        "op_hints": op_hints,
        "exclude_name": exclude_name,
        "chooser_opponent": chooser_opponent,
        "meaningful": has_meaningful_effect_text(info),
    }


def _ability_ops(ability: dict[str, Any]) -> list[str]:
    return [str(o.get("op") or "") for o in (ability.get("ops") or [])]


def _ability_op_set(ability: dict[str, Any]) -> set[str]:
    return set(_ability_ops(ability))


def _flatten_ops(abilities: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for a in abilities:
        for o in a.get("ops") or []:
            kind = str(o.get("op") or "")
            if not kind:
                continue
            out.add(kind)
            if kind == "choose_one":
                for opt in o.get("options") or []:
                    for nested in opt.get("ops") or []:
                        if nested.get("op"):
                            out.add(str(nested["op"]))
    return out


def diff_card(
    card_id: str,
    info: dict[str, Any],
    abilities: list[dict[str, Any]],
    *,
    include_template_drift: bool = True,
) -> list[dict[str, Any]]:
    """Return fidelity findings for one card (empty = PASS)."""
    findings: list[dict[str, Any]] = []
    expected = extract_expected_signals(info)
    if not expected["meaningful"]:
        return findings

    by_t = {str(a.get("timing") or ""): a for a in abilities if a.get("timing")}
    runnable_timings = {t for t, a in by_t.items() if ability_is_runnable(a)}
    all_ops = _flatten_ops(abilities)

    # Missing detected timings
    for t in expected["timings"]:
        if t not in runnable_timings:
            # activate_timing on trigger may cover Main/On Play body
            if t in {"on_play", "counter_event"} and any(
                "activate_timing" in _ability_op_set(a) for a in abilities if a.get("timing") == "trigger"
            ):
                continue
            # Specialized watchers already encode 「我方回合中」 context.
            if t == "your_turn" and runnable_timings & {
                "on_don_returned",
                "on_opp_event",
                "on_opp_trigger",
                "on_trigger",
                "end_of_your_turn",
            }:
                continue
            if t == "opponent_turn" and runnable_timings & {"on_trigger", "on_opp_trigger"}:
                if any(
                    a.get("require_opponent_turn")
                    for a in abilities
                    if a.get("timing") in {"on_trigger", "on_opp_trigger"}
                ):
                    continue
            # Filter text 「未持有【攻擊時】/【登場時】」 is not a real timing.
            blob = effect_blob(info)
            if t == "when_attacking" and "未持有【攻擊時】" in blob:
                continue
            if t == "on_play" and "未持有【登場時】" in blob:
                continue
            findings.append(
                {
                    "card_id": card_id,
                    "base_id": base_card_id(card_id),
                    "category": "missing_timing",
                    "severity": "high",
                    "timing": t,
                    "detail": f"text marks {t} but no runnable ability",
                }
            )

    hints = set(expected["op_hints"])

    # Attack tax wrongly compiled as deny_rest-all
    if "attack_tax" in hints:
        if "attack_tax" not in all_ops:
            if any(o.get("op") == "deny_rest" and o.get("all") for a in abilities for o in (a.get("ops") or [])):
                findings.append(
                    {
                        "card_id": card_id,
                        "base_id": base_card_id(card_id),
                        "category": "wrong_op_attack_tax",
                        "severity": "critical",
                        "detail": "text requires attack_tax but library uses deny_rest all",
                    }
                )
            elif any(a.get("status") == "compiled" for a in abilities):
                findings.append(
                    {
                        "card_id": card_id,
                        "base_id": base_card_id(card_id),
                        "category": "missing_op_attack_tax",
                        "severity": "high",
                        "detail": "text requires attack_tax; not present in abilities",
                    }
                )

    # Choose-one
    if "choose_one" in hints:
        if "choose_one" not in all_ops:
            # Only flag if some main/on_play/trigger ability is compiled without choose_one
            for a in abilities:
                if a.get("timing") in {"on_play", "trigger", "counter_event", "activate_main"} and a.get("status") == "compiled":
                    if "choose_one" not in _ability_op_set(a) and "activate_timing" not in _ability_op_set(a):
                        findings.append(
                            {
                                "card_id": card_id,
                                "base_id": base_card_id(card_id),
                                "category": "missing_choose_one",
                                "severity": "high",
                                "timing": a.get("timing"),
                                "detail": "text has choose-one but ability has no choose_one op",
                            }
                        )
                        break
        elif expected["chooser_opponent"]:
            for a in abilities:
                for o in a.get("ops") or []:
                    if o.get("op") == "choose_one" and o.get("chooser") != "opponent":
                        findings.append(
                            {
                                "card_id": card_id,
                                "base_id": base_card_id(card_id),
                                "category": "wrong_chooser",
                                "severity": "high",
                                "timing": a.get("timing"),
                                "detail": "opponent should choose but chooser!=opponent",
                            }
                        )

    # Exclude name on deny_attack
    excl = expected["exclude_name"]
    if excl and "deny_attack" in hints:
        deny_ops = [o for a in abilities for o in (a.get("ops") or []) if o.get("op") == "deny_attack"]
        if deny_ops and not any(o.get("exclude_name") for o in deny_ops):
            findings.append(
                {
                    "card_id": card_id,
                    "base_id": base_card_id(card_id),
                    "category": "missing_exclude_name",
                    "severity": "high",
                    "detail": f"deny_attack missing exclude_name={excl!r}",
                }
            )

    # Op hints that should appear somewhere when timing exists
    soft_required = {
        "trash_life",
        "hand_to_life",
        "place_on_life",
        "set_cost",
        "skip_untap",
        "flip_life",
        "redirect_attack",
        "deny_attack",
        "deny_rest",
        "life_to_hand",
        "replace_leave",
    }
    # replace_leave cost fields already encode Life payments.
    replace_costs = {
        str(o.get("cost") or "")
        for a in abilities
        for o in (a.get("ops") or [])
        if o.get("op") == "replace_leave"
    }
    for hint in hints & soft_required:
        if hint == "deny_attack" and "attack_tax" in hints:
            continue
        if hint == "redirect_attack" and ("redirect_attack" in all_ops or "choose_target" in all_ops):
            continue
        if hint in {"trash_life", "life_to_hand", "flip_life"} and hint in replace_costs:
            continue
        if hint not in all_ops:
            # Aliases / equivalent encodings.
            if hint == "hand_to_life" and "add_life" in all_ops:
                continue
            if hint == "deny_attack" and "cannot_attack_leader" in all_ops:
                continue
            # Already demoted / queued — keep as low so reports focus on wrong compiled.
            if any(a.get("status") == "needs_review" for a in abilities):
                sev = "low"
            elif any(a.get("status") == "compiled" for a in abilities):
                sev = "high"
            else:
                sev = "medium"
            findings.append(
                {
                    "card_id": card_id,
                    "base_id": base_card_id(card_id),
                    "category": "missing_op_hint",
                    "severity": sev,
                    "detail": f"text suggests op={hint} but library lacks it",
                }
            )

    # Gates: if text has gate and a compiled ability exists for primary timing, require gate on some ability
    primary = None
    for t in ("on_play", "counter_event", "when_attacking", "on_ko", "trigger", "activate_main"):
        if t in by_t and ability_is_runnable(by_t[t]):
            primary = by_t[t]
            break
    if primary and primary.get("status") in {"compiled", "verified"}:
        def _gate_present(gate: str) -> bool:
            aliases = {
                "require_life_gte": ("require_life_gte", "require_opp_life_gte", "require_either_life_gte", "require_total_life_gte"),
                "require_life_lte": ("require_life_lte", "require_opp_life_lte", "require_either_life_lte", "require_total_life_lte", "if_life_lte"),
                "require_opp_life_lte": ("require_opp_life_lte", "require_either_life_lte"),
                "require_don_field_gte": (
                    "require_don_field_gte",
                    "require_opp_don_field_gte",
                    "require_don_field_0_or_gte",
                    "require_either_don_field_gte",
                    "on_return_don_from_field_gte",
                    "require_don_field_deficit_gte",
                ),
                "require_trash_gte": ("require_trash_gte", "if_trash_gte", "require_trash_events_gte"),
                "require_rested_own_chars_gte": (
                    "require_rested_own_chars_gte",
                    "require_opp_rested_chars_gte",
                    "require_rested_cards_gte",
                ),
                "require_don_attached_gte": ("require_don_attached_gte",),
            }.get(gate, (gate,))
            for a in abilities:
                for key in aliases:
                    if a.get(key) is not None:
                        return True
                for o in a.get("ops") or []:
                    for key in aliases:
                        if o.get(key) is not None:
                            return True
                    if o.get("op") == "choose_one":
                        for opt in o.get("options") or []:
                            if any(opt.get(k) is not None for k in aliases):
                                return True
                            for nested in opt.get("ops") or []:
                                if any(nested.get(k) is not None for k in aliases):
                                    return True
            return False

        for g, val in expected["gates"].items():
            if not _gate_present(g):
                findings.append(
                    {
                        "card_id": card_id,
                        "base_id": base_card_id(card_id),
                        "category": "missing_gate",
                        "severity": "medium",
                        "detail": f"text implies {g}={val} but no ability has it",
                    }
                )
        if expected["leader_trait"]:
            if not any(
                a.get("require_leader_trait")
                or any(
                    o.get("require_leader_trait")
                    or (
                        o.get("op") == "choose_one"
                        and any(opt.get("require_leader_trait") for opt in (o.get("options") or []))
                    )
                    for o in (a.get("ops") or [])
                )
                for a in abilities
            ):
                findings.append(
                    {
                        "card_id": card_id,
                        "base_id": base_card_id(card_id),
                        "category": "missing_leader_trait",
                        "severity": "medium",
                        "detail": f"text implies leader trait {expected['leader_trait']!r}",
                    }
                )
        if expected["leader_name"]:
            if not any(a.get("require_leader_name") for a in abilities):
                findings.append(
                    {
                        "card_id": card_id,
                        "base_id": base_card_id(card_id),
                        "category": "missing_leader_name",
                        "severity": "medium",
                        "detail": f"text implies leader name {expected['leader_name']!r}",
                    }
                )

    # Dangling choose_target
    for a in abilities:
        ops = a.get("ops") or []
        if ops and all(o.get("op") == "choose_target" and not o.get("then_op") for o in ops):
            if a.get("status") == "compiled":
                findings.append(
                    {
                        "card_id": card_id,
                        "base_id": base_card_id(card_id),
                        "category": "dangling_choose_target",
                        "severity": "high",
                        "timing": a.get("timing"),
                        "detail": "compiled ability is choose_target stub only",
                    }
                )

    # Template drift: template has stronger primary op set than library
    if include_template_drift:
        try:
            fresh = compile_card_from_templates(card_id, info)
        except Exception:
            fresh = {"abilities": []}
        for a in fresh.get("abilities") or []:
            t = str(a.get("timing") or "")
            if not t or not ability_is_runnable(a):
                continue
            lib = by_t.get(t)
            if not lib or not ability_is_runnable(lib):
                continue
            if lib.get("status") == "needs_review":
                continue
            fresh_ops = _ability_op_set(a)
            # Flatten choose_one nests so nested trash_life/flip_life count as present.
            lib_ops = set()
            for o in lib.get("ops") or []:
                kind = str(o.get("op") or "")
                if not kind:
                    continue
                lib_ops.add(kind)
                if kind == "choose_one":
                    for opt in o.get("options") or []:
                        for nested in opt.get("ops") or []:
                            if nested.get("op"):
                                lib_ops.add(str(nested["op"]))
                if kind == "choose_target" and isinstance(o.get("then_op"), dict) and o["then_op"].get("op"):
                    lib_ops.add(str(o["then_op"]["op"]))
            # Aliases
            if "cannot_attack_leader" in lib_ops:
                lib_ops.add("deny_attack")
            if "add_life" in lib_ops:
                lib_ops.add("hand_to_life")
            # Template offers real ops while library is only choose_target / unsupported
            bare = lib_ops - {"unsupported", "choose_target", "buff"}
            if fresh_ops - {"unsupported", "choose_target"} and not bare and lib_ops <= {"choose_target", "unsupported"}:
                findings.append(
                    {
                        "card_id": card_id,
                        "base_id": base_card_id(card_id),
                        "category": "template_stronger",
                        "severity": "medium",
                        "timing": t,
                        "detail": f"template ops={sorted(fresh_ops)} library ops={sorted(lib_ops)}",
                    }
                )
            # High-value ops in template missing from library
            valuable = fresh_ops & {
                "choose_one",
                "attack_tax",
                "trash_life",
                "hand_to_life",
                "place_on_life",
                "deny_attack",
                "set_cost",
                "flip_life",
            }
            missing = valuable - lib_ops
            if missing and lib.get("status") == "compiled":
                findings.append(
                    {
                        "card_id": card_id,
                        "base_id": base_card_id(card_id),
                        "category": "template_ops_missing",
                        "severity": "medium",
                        "timing": t,
                        "detail": f"template has {sorted(missing)} not in library",
                    }
                )

    return findings


def run_fidelity_audit(
    catalog: dict[str, Any],
    *,
    get_abilities,
    base_only: bool = True,
    limit: int | None = None,
    severity_min: str = "medium",
) -> dict[str, Any]:
    sev_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    min_rank = sev_rank.get(severity_min, 1)

    seen_bases: set[str] = set()
    findings: list[dict[str, Any]] = []
    scanned = 0
    pass_bases = 0
    fail_bases = 0

    for cid, info in catalog.items():
        if not isinstance(info, dict):
            continue
        b = base_card_id(cid)
        if base_only:
            if b in seen_bases:
                continue
            seen_bases.add(b)
        if not has_meaningful_effect_text(info):
            continue
        scanned += 1
        if limit is not None and scanned > limit:
            break
        abs_ = get_abilities(cid) or []
        card_findings = diff_card(cid, info, abs_)
        card_findings = [f for f in card_findings if sev_rank.get(str(f.get("severity")), 0) >= min_rank]
        if card_findings:
            fail_bases += 1
            findings.extend(card_findings)
        else:
            pass_bases += 1

    by_cat: Counter[str] = Counter(str(f.get("category") or "") for f in findings)
    by_sev: Counter[str] = Counter(str(f.get("severity") or "") for f in findings)
    unique_fail_bases = sorted({f["base_id"] for f in findings})

    return {
        "totals": {
            "cards_scanned": scanned,
            "pass_bases": pass_bases,
            "fail_bases": fail_bases,
            "findings": len(findings),
            "unique_fail_bases": len(unique_fail_bases),
        },
        "by_category": dict(by_cat),
        "by_severity": dict(by_sev),
        "findings": findings,
        "unique_fail_bases": unique_fail_bases,
    }


def report_to_markdown(report: dict[str, Any], *, max_rows: int = 80) -> str:
    totals = report.get("totals") or {}
    lines = [
        "# Full-library effect fidelity report",
        "",
        f"- Cards scanned (meaningful text): **{totals.get('cards_scanned', 0)}**",
        f"- PASS bases: **{totals.get('pass_bases', 0)}**",
        f"- FAIL bases: **{totals.get('fail_bases', 0)}**",
        f"- Findings: **{totals.get('findings', 0)}**",
        "",
        "## By category",
        "",
        "| Category | Count |",
        "|----------|------:|",
    ]
    for cat, n in sorted((report.get("by_category") or {}).items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"| `{cat}` | {n} |")
    lines += [
        "",
        "## By severity",
        "",
        "| Severity | Count |",
        "|----------|------:|",
    ]
    for sev, n in sorted((report.get("by_severity") or {}).items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"| {sev} | {n} |")

    # Group sample findings by category
    by: dict[str, list] = defaultdict(list)
    for f in report.get("findings") or []:
        by[str(f.get("category"))].append(f)

    lines += ["", "## Sample findings", ""]
    shown = 0
    for cat, items in sorted(by.items(), key=lambda x: -len(x[1])):
        lines.append(f"### `{cat}` ({len(items)})")
        lines.append("")
        for f in items[:12]:
            lines.append(
                f"- **{f.get('base_id')}** [{f.get('severity')}]"
                f"{f' `{f.get('timing')}`' if f.get('timing') else ''}: {f.get('detail')}"
            )
            shown += 1
            if shown >= max_rows:
                break
        lines.append("")
        if shown >= max_rows:
            lines.append("_… truncated …_")
            break

    return "\n".join(lines).rstrip() + "\n"
