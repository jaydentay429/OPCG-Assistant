"""Deterministic audit of compiled card effects vs card text.

Records mismatches by category for batch fixing later. Does not mutate the library.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from battle.effect_library import (
    compile_card_from_templates,
    detect_timings_in_text,
    get_abilities,
)
from battle.effect_schema import ability_is_runnable
from battle.effects import effect_blob, has_meaningful_effect_text

Catalog = dict[str, dict[str, Any]]
Finding = dict[str, Any]

_RE_KO_OWN = re.compile(
    r"k\.?o\.?\s*1 of your (?:characters?|character cards)|"
    r"(?:可以)?KO(?:除了這張角色卡以外|除了这张角色卡以外)?\s*1[張张]自己",
    re.I,
)
_RE_KO_OPP = re.compile(
    r"k\.?o\.?\s*(?:up to\s*)?\d+\s+of your opponent|"
    r"KO最多\s*\d*[張张]對手|KO最多\s*\d*[张张]对手",
    re.I,
)
_RE_COST_REDUCE = re.compile(
    r"(?:give (?:up to \d+ of )?your opponent'?s? characters?|"
    r"give all of your opponent'?s? characters?|"
    r"give this card in your hand|"
    r"give .{0,40} in your hand)\s*[−\-－–]\s*\d+\s*cost|"
    r"對手的角色卡(?:全數)?費用\s*[−\-－–]\s*\d+|"
    r"对手的角色卡(?:全数)?费用\s*[−\-－–]\s*\d+|"
    r"手牌中這張卡片的費用\s*[−\-－–]\s*\d+|"
    r"手牌中这张卡片的费用\s*[−\-－–]\s*\d+|"
    r"手牌中的.{0,24}費用\s*[−\-－–]\s*\d+|"
    r"最多\d*[張张]對手的角色卡.{0,40}費用\s*[−\-－–]\s*\d+",
    re.I,
)
_RE_COST_OPS = frozenset({"reduce_cost", "static_reduce_opp_cost", "hand_cost_reduce"})
_RE_COUNTER = re.compile(r"【反擊】|【反击】|\[counter\]", re.I)
_RE_ACTIVATEISH = re.compile(
    r"\[activate:\s*main\]|【啟動主要】|【启动主要】|\[main\]|【主要】",
    re.I,
)
_RE_LOOK_AT = re.compile(
    r"look at (?:the )?(?:top )?\d+|reveal up to|"
    r"從(?:自己的)?卡組上面查看|从(?:自己的)?卡组上面查看|"
    r"查看\d+[張张]",
    re.I,
)
_RE_ONCE = re.compile(r"【每回合1次】|【每回合一次】|\[once per turn\]", re.I)
_TEMPLATE_FAMILY_OPS = frozenset(
    {
        "reduce_cost",
        "static_reduce_opp_cost",
        "hand_cost_reduce",
        "search_deck",
        "trash_deck_top",
        "buff_all_own",
        "ko",
    }
)

SEVERITY_BY_CATEGORY = {
    "ko_own_as_opp": "error",
    "cost_reduce_gap": "error",
    "bogus_counter_event": "error",
    "look_at_as_draw": "error",
    "once_flag_missing": "warn",
    "template_lib_diverge": "warn",
    "timing_unsupported": "warn",
    "empty_with_text": "warn",
}


def base_card_id(cid: str) -> str:
    return re.sub(r"-(?:P|R)\d+$", "", cid)


def _finding(
    *,
    cid: str,
    name: str,
    category: str,
    timing: str = "",
    detail: str = "",
    evidence: str = "",
) -> Finding:
    return {
        "id": cid,
        "base_id": base_card_id(cid),
        "name": name,
        "category": category,
        "severity": SEVERITY_BY_CATEGORY.get(category, "warn"),
        "timing": timing,
        "detail": detail[:240],
        "evidence": evidence[:200],
    }


def _ops_sig(ops: list[dict[str, Any]] | None) -> list[tuple[Any, ...]]:
    out: list[tuple[Any, ...]] = []
    for o in ops or []:
        out.append(
            (
                o.get("op"),
                o.get("target_kind"),
                o.get("amount"),
                o.get("as_cost"),
                o.get("count"),
                o.get("trait_contains"),
            )
        )
    return out


def _lib_has_cost_op(abilities: list[dict[str, Any]]) -> bool:
    for ab in abilities:
        for o in ab.get("ops") or []:
            if o.get("op") in _RE_COST_OPS:
                return True
    return False


def check_ko_own_as_opp(
    cid: str,
    info: dict[str, Any],
    abilities: list[dict[str, Any]],
    blob: str,
) -> list[Finding]:
    if not _RE_KO_OWN.search(blob):
        return []
    # Pure opponent-KO lines elsewhere are fine if own-KO is also correctly compiled.
    findings: list[Finding] = []
    name = str(info.get("name") or info.get("name_en") or cid)
    has_own_ko = False
    wrong: list[tuple[str, str]] = []
    for ab in abilities:
        if not ability_is_runnable(ab):
            continue
        timing = str(ab.get("timing") or "")
        for o in ab.get("ops") or []:
            op = o.get("op")
            tk = str(o.get("target_kind") or "")
            if op == "ko" and tk == "own_character":
                has_own_ko = True
            if op == "ko_lowest_opponent" or (op == "ko" and tk.startswith("opponent")):
                # Only flag if this ability's summary/chunk looks like own-KO, or card has own-KO and no correct own op yet
                summary = str(ab.get("summary") or "")
                if _RE_KO_OWN.search(summary) or _RE_KO_OWN.search(blob):
                    if not _RE_KO_OPP.search(summary):
                        wrong.append((timing, f"{op}/{tk or '-'}"))
    if wrong and not has_own_ko:
        findings.append(
            _finding(
                cid=cid,
                name=name,
                category="ko_own_as_opp",
                timing=wrong[0][0],
                detail=f"Own-KO text but ops target opponent: {', '.join(f'{t}:{o}' for t, o in wrong[:3])}",
                evidence=blob[:160],
            )
        )
    elif wrong and has_own_ko:
        # Mixed: still flag abilities whose summary is own-KO but ops are opp
        for timing, op_s in wrong:
            # already have own elsewhere — only report if summary clearly own-only
            pass
    return findings


def check_cost_reduce_gap(
    cid: str,
    info: dict[str, Any],
    abilities: list[dict[str, Any]],
    blob: str,
) -> list[Finding]:
    if not _RE_COST_REDUCE.search(blob):
        return []
    if _lib_has_cost_op(abilities):
        return []
    # Ignore pure power debuffs that our regex might partially catch — require "cost"/"費用"
    if not re.search(r"cost|費用|费用", blob, re.I):
        return []
    name = str(info.get("name") or info.get("name_en") or cid)
    return [
        _finding(
            cid=cid,
            name=name,
            category="cost_reduce_gap",
            timing="",
            detail="Cost −N text present but no reduce_cost / static_reduce_opp_cost / hand_cost_reduce ops",
            evidence=blob[:160],
        )
    ]


def check_bogus_counter_event(
    cid: str,
    info: dict[str, Any],
    abilities: list[dict[str, Any]],
    blob: str,
) -> list[Finding]:
    if _RE_COUNTER.search(blob):
        return []
    name = str(info.get("name") or info.get("name_en") or cid)
    findings: list[Finding] = []
    for ab in abilities:
        if str(ab.get("timing") or "") != "counter_event":
            continue
        if not ability_is_runnable(ab):
            continue
        summary = str(ab.get("summary") or "")
        if _RE_ACTIVATEISH.search(summary) or _RE_ACTIVATEISH.search(blob):
            findings.append(
                _finding(
                    cid=cid,
                    name=name,
                    category="bogus_counter_event",
                    timing="counter_event",
                    detail="Runnable counter_event without [Counter] marker; summary/text looks like Activate/Main",
                    evidence=(summary or blob)[:160],
                )
            )
            break
        # Also flag ko_lowest_opponent counter with no counter text
        ops = ab.get("ops") or []
        if any(o.get("op") in {"ko_lowest_opponent", "ko"} for o in ops):
            findings.append(
                _finding(
                    cid=cid,
                    name=name,
                    category="bogus_counter_event",
                    timing="counter_event",
                    detail="Runnable counter_event KO ops without [Counter] in card text",
                    evidence=(summary or blob)[:160],
                )
            )
            break
    return findings


def check_look_at_as_draw(
    cid: str,
    info: dict[str, Any],
    abilities: list[dict[str, Any]],
    blob: str,
) -> list[Finding]:
    name = str(info.get("name") or info.get("name_en") or cid)
    findings: list[Finding] = []
    for ab in abilities:
        if not ability_is_runnable(ab):
            continue
        ops = ab.get("ops") or []
        has_draw = any(o.get("op") == "draw" for o in ops)
        has_search = any(o.get("op") == "search_deck" for o in ops)
        if not (has_draw and not has_search):
            continue
        # Only flag when THIS ability's summary is look-at/search, not unrelated deck text elsewhere.
        summary = str(ab.get("summary") or "")
        if not _RE_LOOK_AT.search(summary):
            continue
        # Ignore multi-timing dumps: look-at belongs to another timing in the same summary.
        timing = str(ab.get("timing") or "")
        if timing == "on_play":
            # Strip after when-attacking / activate markers — look-at there is not this ability.
            cut = re.split(r"【攻擊時】|【攻击时】|\[when attacking\]|【啟動主要】|\[activate", summary, maxsplit=1, flags=re.I)
            summary_scope = cut[0] if cut else summary
            if not _RE_LOOK_AT.search(summary_scope):
                continue
        if re.search(r"^Trigger:\s*\[\{'op': 'draw'", summary):
            continue
        findings.append(
            _finding(
                cid=cid,
                name=name,
                category="look_at_as_draw",
                timing=timing,
                detail="Look-at / reveal-top text compiled as draw without search_deck",
                evidence=summary[:160],
            )
        )
        break
    return findings


def check_once_flag_missing(
    cid: str,
    info: dict[str, Any],
    abilities: list[dict[str, Any]],
    blob: str,
) -> list[Finding]:
    if not _RE_ONCE.search(blob):
        return []
    name = str(info.get("name") or info.get("name_en") or cid)
    findings: list[Finding] = []
    # Focus on activate_main / when_attacking where once is meaningful
    for ab in abilities:
        timing = str(ab.get("timing") or "")
        if timing not in {"activate_main", "when_attacking", "on_don_attached", "your_turn"}:
            continue
        if not ability_is_runnable(ab):
            continue
        summary = str(ab.get("summary") or "")
        # Prefer abilities whose summary mentions once, or activate_main with once in full blob
        if timing == "activate_main" or _RE_ONCE.search(summary):
            if not ab.get("once"):
                findings.append(
                    _finding(
                        cid=cid,
                        name=name,
                        category="once_flag_missing",
                        timing=timing,
                        detail="Once-per-turn text but ability.once is not set",
                        evidence=(summary or blob)[:160],
                    )
                )
                break
    return findings


def check_timing_unsupported(
    cid: str,
    info: dict[str, Any],
    abilities: list[dict[str, Any]],
    blob: str,
) -> list[Finding]:
    name = str(info.get("name") or info.get("name_en") or cid)
    findings: list[Finding] = []
    detected = detect_timings_in_text(blob)
    by_t = {str(a.get("timing")): a for a in abilities}

    def _covers(timing: str) -> dict[str, Any] | None:
        ab = by_t.get(timing)
        if ab is not None and ability_is_runnable(ab):
            return ab
        # Events historically stored [Main] as activate_main; engine plays Events via on_play.
        if timing == "on_play":
            am = by_t.get("activate_main")
            if am is not None and ability_is_runnable(am):
                cat = str(info.get("category") or info.get("card_type") or "")
                if cat.lower() == "event" and re.search(r"\[main\]|【主要】", blob, re.I):
                    return am
        return None

    for timing in sorted(detected):
        ab = _covers(timing)
        if ab is not None:
            continue
        existing = by_t.get(timing)
        if existing is None:
            findings.append(
                _finding(
                    cid=cid,
                    name=name,
                    category="timing_unsupported",
                    timing=timing,
                    detail=f"Text marks {timing} but no ability present",
                    evidence=blob[:160],
                )
            )
            continue
        if not ability_is_runnable(existing):
            reason = "unsupported"
            for o in existing.get("ops") or []:
                if o.get("op") == "unsupported":
                    reason = str(o.get("reason") or "unsupported")
                    break
            findings.append(
                _finding(
                    cid=cid,
                    name=name,
                    category="timing_unsupported",
                    timing=timing,
                    detail=f"Non-runnable ability ({reason})",
                    evidence=str(existing.get("summary") or blob)[:160],
                )
            )
    return findings


def check_empty_with_text(
    cid: str,
    info: dict[str, Any],
    abilities: list[dict[str, Any]],
    blob: str,
) -> list[Finding]:
    # Dash-only / keyword-only reminder text is not a compile gap.
    if not has_meaningful_effect_text(info if info else blob):
        return []
    if abilities:
        return []
    name = str(info.get("name") or info.get("name_en") or cid)
    return [
        _finding(
            cid=cid,
            name=name,
            category="empty_with_text",
            detail="Card has effect text but library abilities list is empty",
            evidence=blob[:160],
        )
    ]


def check_template_lib_diverge(
    cid: str,
    info: dict[str, Any],
    abilities: list[dict[str, Any]],
    blob: str,
) -> list[Finding]:
    """Template has family ops that library is missing or contradicts."""
    try:
        fresh = compile_card_from_templates(cid, info)
    except Exception as exc:  # noqa: BLE001 — audit must not die on one card
        name = str(info.get("name") or info.get("name_en") or cid)
        return [
            _finding(
                cid=cid,
                name=name,
                category="template_lib_diverge",
                detail=f"compile_card_from_templates failed: {exc}",
                evidence=blob[:120],
            )
        ]
    name = str(info.get("name") or info.get("name_en") or cid)
    lib_by_t: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ab in abilities:
        if ability_is_runnable(ab):
            lib_by_t[str(ab.get("timing") or "")].append(ab)
    findings: list[Finding] = []
    for ab in fresh.get("abilities") or []:
        if not ability_is_runnable(ab):
            continue
        timing = str(ab.get("timing") or "")
        tops = ab.get("ops") or []
        family = [o for o in tops if o.get("op") in _TEMPLATE_FAMILY_OPS]
        if not family:
            continue
        # Own-KO family specially interesting
        interesting = False
        for o in family:
            if o.get("op") in {"reduce_cost", "static_reduce_opp_cost", "hand_cost_reduce", "search_deck", "trash_deck_top", "buff_all_own"}:
                interesting = True
            if o.get("op") == "ko" and o.get("target_kind") == "own_character":
                interesting = True
        if not interesting:
            continue
        lib_abs = lib_by_t.get(timing) or []
        if not lib_abs:
            findings.append(
                _finding(
                    cid=cid,
                    name=name,
                    category="template_lib_diverge",
                    timing=timing,
                    detail=f"Template has family ops {_ops_sig(family)[:4]} but library has no runnable {timing}",
                    evidence=str(ab.get("summary") or "")[:160],
                )
            )
            continue
        # Compare: template family ops should appear (by op+target_kind) in some lib ability
        lib_ops_flat = [o for lab in lib_abs for o in (lab.get("ops") or [])]
        for fo in family:
            op = fo.get("op")
            tk = fo.get("target_kind")
            matched = False
            for lo in lib_ops_flat:
                if lo.get("op") != op:
                    continue
                if op == "ko" and tk == "own_character":
                    if lo.get("target_kind") == "own_character":
                        matched = True
                        break
                    continue
                if tk and lo.get("target_kind") and lo.get("target_kind") != tk:
                    continue
                matched = True
                break
            if matched:
                continue
            # Contradiction: template wants own KO, library has opponent KO for same timing
            if op == "ko" and tk == "own_character":
                if any(
                    (lo.get("op") == "ko" and str(lo.get("target_kind", "")).startswith("opponent"))
                    or lo.get("op") == "ko_lowest_opponent"
                    for lo in lib_ops_flat
                ):
                    findings.append(
                        _finding(
                            cid=cid,
                            name=name,
                            category="template_lib_diverge",
                            timing=timing,
                            detail="Template KO own_character but library KO targets opponent",
                            evidence=str(ab.get("summary") or "")[:160],
                        )
                    )
                    continue
            findings.append(
                _finding(
                    cid=cid,
                    name=name,
                    category="template_lib_diverge",
                    timing=timing,
                    detail=f"Template op {op}/{tk or '-'} missing from library {timing}",
                    evidence=str(ab.get("summary") or "")[:160],
                )
            )
    return findings


CHECKERS: list[Callable[[str, dict[str, Any], list[dict[str, Any]], str], list[Finding]]] = [
    check_empty_with_text,
    check_timing_unsupported,
    check_ko_own_as_opp,
    check_cost_reduce_gap,
    check_bogus_counter_event,
    check_look_at_as_draw,
    check_once_flag_missing,
    check_template_lib_diverge,
]


def audit_card(cid: str, info: dict[str, Any], abilities: list[dict[str, Any]] | None = None) -> list[Finding]:
    blob = effect_blob(info).strip()
    abs_ = abilities if abilities is not None else get_abilities(cid)
    findings: list[Finding] = []
    for checker in CHECKERS:
        findings.extend(checker(cid, info, abs_, blob))
    return findings


def iter_catalog_ids(catalog: Catalog, *, base_only: bool = False) -> Iterable[str]:
    if not base_only:
        yield from sorted(catalog.keys())
        return
    seen: set[str] = set()
    # Prefer bare base id when present; else first variant
    for cid in sorted(catalog.keys()):
        base = base_card_id(cid)
        if base in seen:
            continue
        if base in catalog:
            seen.add(base)
            yield base
        else:
            seen.add(base)
            yield cid


def run_audit(
    catalog: Catalog,
    *,
    base_only: bool = False,
    category: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    findings: list[Finding] = []
    scanned = 0
    for cid in iter_catalog_ids(catalog, base_only=base_only):
        info = catalog.get(cid)
        if not isinstance(info, dict):
            continue
        scanned += 1
        card_findings = audit_card(cid, info)
        if category:
            card_findings = [f for f in card_findings if f.get("category") == category]
        findings.extend(card_findings)
        if limit is not None and scanned >= limit:
            break

    by_category: Counter[str] = Counter(str(f.get("category")) for f in findings)
    by_severity: Counter[str] = Counter(str(f.get("severity")) for f in findings)
    samples: dict[str, list[Finding]] = {}
    for cat, _ in by_category.most_common():
        samples[cat] = [f for f in findings if f.get("category") == cat][:20]

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "totals": {
            "cards_scanned": scanned,
            "findings": len(findings),
            "unique_bases": len({str(f.get("base_id")) for f in findings}),
        },
        "by_category": dict(by_category.most_common()),
        "by_severity": dict(by_severity.most_common()),
        "findings": findings,
        "samples_by_category": samples,
    }


def report_to_markdown(report: dict[str, Any]) -> str:
    totals = report.get("totals") or {}
    lines = [
        "# Effect audit report\n\n",
        f"Generated: `{report.get('generated_at')}`\n\n",
        f"- Cards scanned: **{totals.get('cards_scanned', 0)}**\n",
        f"- Findings: **{totals.get('findings', 0)}** "
        f"({totals.get('unique_bases', 0)} unique bases)\n\n",
        "## By category\n\n",
        "| Category | Count | Severity |\n|----------|------:|----------|\n",
    ]
    by_cat = report.get("by_category") or {}
    for cat, count in by_cat.items():
        sev = SEVERITY_BY_CATEGORY.get(cat, "warn")
        lines.append(f"| `{cat}` | {count} | {sev} |\n")
    lines.append("\n## By severity\n\n")
    for sev, count in (report.get("by_severity") or {}).items():
        lines.append(f"- `{sev}`: {count}\n")
    samples = report.get("samples_by_category") or {}
    for cat in by_cat:
        rows = samples.get(cat) or []
        lines.append(f"\n## Samples: `{cat}`\n\n")
        lines.append("| ID | Name | Timing | Detail |\n|----|------|--------|--------|\n")
        for f in rows[:15]:
            detail = str(f.get("detail") or "").replace("|", "/")
            lines.append(
                f"| {f.get('id')} | {f.get('name')} | {f.get('timing') or '-'} | {detail[:100]} |\n"
            )
    return "".join(lines)
