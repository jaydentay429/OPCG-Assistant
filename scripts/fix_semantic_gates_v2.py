#!/usr/bin/env python3
"""Inject missing gates / costs / search fields on semantic-issue cards.

Writes library + overrides.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability, normalize_card_entry  # noqa: E402
from battle.effects import (  # noqa: E402
    _enrich_ops_with_target_filters,
    _parse_look_top_search,
    effect_blob,
)

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "gates_v2_fixed_ids.txt"

LEADER_TRAIT_RE = re.compile(
    r"(?:if your Leader (?:has|is)(?: the)?\s*\{([^}]+)\}(?:\s*or\s*\{([^}]+)\})?|"
    r"Leader'?s? type includes?\s*[\"']([^\"']+)[\"']|"
    r"若自己的?領航卡擁有(?:包含)?[『「《]([^』」》]+)[』」》](?:或[『「《]([^』」》]+)[』」》])?|"
    r"若自己的?领航卡拥有(?:包含)?[『「《]([^』」》]+)[』」》](?:或[『「《]([^』」》]+)[』」》])?|"
    r"若自己的?領袖(?:卡)?擁有(?:包含)?[『「《]([^』」》]+)[』」》]|"
    r"若自己的?领袖(?:卡)?拥有(?:包含)?[『「《]([^』」》]+)[』」》])",
    re.I,
)
LEADER_NAME_RE = re.compile(
    r"(?:if your Leader is|若自己的?領航卡是|若自己的?领航卡是)\s*[「\[]([^」\]]+)[」\]]",
    re.I,
)
DON_X_RE = re.compile(
    r"\[DON!!\s*[xX×]\s*(\d+)\]|【咚‼?\s*[×xX]\s*(\d+)】|DON!!\s*[xX×]\s*(\d+)",
    re.I,
)
CHARS_GTE_RE = re.compile(
    r"if you have\s*(\d+)\s*or more Characters|"
    r"場上有自己的角色卡\s*(\d+)\s*張以上|场上有自己的角色卡\s*(\d+)\s*张以上",
    re.I,
)
CHARS_LTE_RE = re.compile(
    r"if you have\s*(\d+)\s*or less Characters|"
    r"場上的自己的?角色卡[為为]\s*(\d+)\s*張以下|"
    r"场上的自己的?角色卡[为為]\s*(\d+)\s*张以下|"
    r"自己的角色卡\s*(\d+)\s*張以下|自己的角色卡\s*(\d+)\s*张以下",
    re.I,
)
NO_OTHER_NAME_RE = re.compile(
    r"(?:if you (?:do not|don't) have another|場上沒有自己其他的(?:角色卡)?|场上没有自己其他的(?:角色卡)?)"
    r"[「\"]([^」\"]+)[」\"]|"
    r"場上沒有自己其他的角色卡「([^」]+)」|场上没有自己其他的角色卡「([^」]+)」|"
    r"場上沒有自己其他的「([^」]+)」|场上没有自己其他的「([^」]+)」",
    re.I,
)
REST_SELF_RE = re.compile(
    r"(?:you may )?rest this (?:Character|card)\s*:|"
    r"可[將将]這張角色卡置為休息狀態[：:]|"
    r"可[將将]这张角色卡置为休息状态[：:]|"
    r"[將将]這張角色卡置為休息狀態[：:]|"
    r"[將将]这张角色卡置为休息状态[：:]",
    re.I,
)
LEADER_POWER_COST_RE = re.compile(
    r"(?:you may )?(?:give )?(?:your )?(?:active )?Leader\s*[−\-－]\s*(\d{3,5}).{0,24}:|"
    r"可以?[將将]1張自己活動狀態的領航卡力量值\s*[−\-－]\s*(\d{3,5})\s*[：:]|"
    r"可以?[將将]1张自己活动状态的领航卡力量值\s*[−\-－]\s*(\d{3,5})\s*[：:]|"
    r"1張自己活動狀態的領航卡.{0,12}力量值\s*[−\-－]\s*(\d{3,5})\s*[：:]|"
    r"1张自己活动状态的领航卡.{0,12}力量值\s*[−\-－]\s*(\d{3,5})\s*[：:]",
    re.I,
)
RETURN_DON_RE = re.compile(
    r"DON!!\s*[−\-－]?\s*(\d+)|咚‼?\s*[−\-－]?\s*(\d+)|"
    r"return\s*(\d+)\s*DON|將\s*(\d+)\s*張?.{0,8}咚.{0,16}放回咚",
    re.I,
)
AMT_RE = re.compile(
    r"(?:gains?|give|gets?|力量值)\s*([+\-−－＋]\s*\d{3,5})|"
    r"([+\-−－＋]\s*\d{3,5})\s*(?:power|力量)",
    re.I,
)


def _trim_cross_timing(text: str, timing: str) -> str:
    """Drop trailing other-timing sections from a polluted summary/chunk."""
    if not text:
        return text
    # Markers that start a *different* ability section.
    stops = [
        r"\[(?:on play|when attacking|activate(?:\s*:\s*main)?|on\s*k\.?o\.?|trigger|counter|main|"
        r"your turn|opponent'?s turn|end of your turn|on your opponent'?s attack|on block|don!!\s*[xX×])\]",
        r"【(?:登場時|登场时|攻擊時|攻击时|啟動主要|启动主要|KO時|KO时|觸發器|触发器|反擊|反击|主要|"
        r"我方回合中|對方回合中|对方回合中|我方的?回合結束時|對方的?攻擊時|阻挡时|阻擋時|咚‼?\s*[×xX])】",
    ]
    # Keep the first timing header that matches this ability, cut at the next header.
    t = (timing or "").lower()
    own = {
        "on_play": r"\[on play\]|【登場時】|【登场时】",
        "when_attacking": r"\[when attacking\]|【攻擊時】|【攻击时】",
        "activate_main": r"\[activate(?:\s*:\s*main)?\]|【啟動主要】|【启动主要】",
        "trigger": r"\[trigger\]|【觸發器】|【触发器】",
        "main_start": r"\[main\]|【主要】",
        "counter_event": r"\[counter\]|【反擊】|【反击】",
        "opponent_turn": r"\[opponent'?s turn\]|【對方回合中】|【对方回合中】",
        "your_turn": r"\[your turn\]|【我方回合中】",
        "on_opponent_attack": r"\[on your opponent'?s attack\]|【對方的?攻擊時】|【对方的?攻击时】",
        "end_of_your_turn": r"\[end of your turn\]|【我方的?回合結束時】|【我方的?回合结束时】",
    }.get(t)
    start = 0
    if own:
        m = re.search(own, text, re.I)
        if m:
            start = m.start()
            # Keep a leading [DON!! xN] / 【咚!!×N】 immediately before this timing.
            pre = text[:start]
            m_don = re.search(
                r"(?:\[DON!!\s*[xX×]\s*\d+\]|【咚‼?\s*[×xX]\s*\d+】)\s*$",
                pre,
                re.I,
            )
            if m_don:
                start = m_don.start()
    body = text[start:]
    # Find next foreign timing marker after this ability's own header.
    stop_re = re.compile(
        r"(?=\[(?:on play|when attacking|activate(?:\s*:\s*main)?|on\s*k\.?o\.?|trigger|counter|main|"
        r"your turn|opponent'?s turn|end of your turn|on your opponent'?s attack|on block)\]|"
        r"【(?:登場時|登场时|攻擊時|攻击时|啟動主要|启动主要|KO時|KO时|觸發器|触发器|反擊|反击|主要|"
        r"我方回合中|對方回合中|对方回合中|我方的?回合結束時|對方的?攻擊時)】|"
        # DON!! xN that prefixes a *different* timing (not a leading gate for this one).
        r"\[DON!!\s*[xX×]\s*\d+\]\s*\[|"
        r"【咚‼?\s*[×xX]\s*\d+】\s*【)",
        re.I,
    )
    # Skip past this ability's own timing header so we don't cut at ourselves.
    search_from = 0
    if own:
        m_own_body = re.search(own, body, re.I)
        if m_own_body:
            search_from = m_own_body.end()
    if search_from < 8:
        search_from = min(8, len(body))
    for m2 in stop_re.finditer(body[search_from:]):
        abs_pos = search_from + m2.start()
        pre = body[max(0, abs_pos - 48) : abs_pos]
        # Nested refs inside "Activate this card's [Main] effect" are not section boundaries.
        if re.search(r"activate this card'?s\s*$|發動這張卡片的\s*$|发动这张卡片的\s*$", pre, re.I):
            continue
        body = body[:abs_pos]
        break
    # Drop a trailing bare [DON!! xN] leftover that belongs to the next ability.
    body = re.sub(
        r"(?:\s*\[DON!!\s*[xX×]\s*\d+\]|\s*【咚‼?\s*[×xX]\s*\d+】)+\s*$",
        "",
        body,
        flags=re.I,
    )
    return body.strip()


def _timing_chunk(blob: str, timing: str) -> str:
    t = (timing or "").lower()
    patterns = {
        "on_play": r"(?:\[on play\]|【登場時】|【登场时】)",
        "when_attacking": r"(?:\[when attacking\]|【攻擊時】|【攻击时】)",
        "activate_main": r"(?:\[activate(?:\s*:\s*main)?\]|【啟動主要】|【启动主要】)",
        "trigger": r"(?:\[trigger\]|【觸發器】|【触发器】)",
        "on_ko": r"(?:\[on\s*k\.?o\.?\]|【KO時】|【KO时】)",
        "main_start": r"(?:\[main\]|【主要】)",
        "counter_event": r"(?:\[counter\]|【反擊】|【反击】)",
        "on_opponent_attack": r"(?:\[on your opponent'?s attack\]|【對方的?攻擊時】|【对方的?攻击时】)",
        "opponent_turn": r"(?:\[opponent'?s turn\]|【對方回合中】|【对方回合中】)",
        "your_turn": r"(?:\[your turn\]|【我方回合中】)",
        "end_of_your_turn": r"(?:\[end of your turn\]|【我方的?回合結束時】|【我方的?回合结束时】)",
        "don_attached": r"(?:\[don!!\s*[xX×]\s*\d+\]|【咚‼?\s*[×xX]\s*\d+】)",
    }
    pat = patterns.get(t)
    if not pat:
        return blob
    m = re.search(pat, blob, re.I)
    if not m:
        return blob
    start = m.start()
    # Keep a leading [DON!! xN] / 【咚!!×N】 immediately before this timing.
    pre = blob[:start]
    m_don = re.search(
        r"(?:\[DON!!\s*[xX×]\s*\d+\]|【咚‼?\s*[×xX]\s*\d+】)\s*$",
        pre,
        re.I,
    )
    if m_don:
        start = m_don.start()
    rest = blob[m.end() :]
    stop_re = re.compile(
        r"(?=\[(?:on play|when attacking|activate|on\s*k\.?o\.?|trigger|counter|main|don!!|"
        r"your turn|end of|on your opponent'?s attack|on block|opponent'?s turn)\]|【)",
        re.I,
    )
    cut = None
    for sm in stop_re.finditer(rest):
        pre2 = rest[max(0, sm.start() - 48) : sm.start()]
        if re.search(r"activate this card'?s\s*$|發動這張卡片的\s*$|发动这张卡片的\s*$", pre2, re.I):
            continue
        cut = sm.start()
        break
    end = m.end() + (cut if cut is not None else min(len(rest), 560))
    return blob[start:end]


def _parse_amt(raw: str) -> int | None:
    s = (raw or "").replace("−", "-").replace("－", "-").replace("＋", "+").strip()
    s = re.sub(r"[^\d+\-]", "", s)
    if not s or s in {"+", "-"}:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    semantic = json.loads(SEM.read_text(encoding="utf-8")) if SEM.exists() else {"cards": {}}
    lib_path, ovr_path = library_paths()
    raw = json.loads(lib_path.read_text(encoding="utf-8"))
    cards = raw.get("cards") or raw
    ovr_raw = json.loads(ovr_path.read_text(encoding="utf-8")) if ovr_path.is_file() else {"cards": {}}
    overrides = ovr_raw.get("cards") if isinstance(ovr_raw.get("cards"), dict) else {}

    stats = {
        "leader_trait": 0,
        "don_x": 0,
        "chars_gte": 0,
        "chars_lte": 0,
        "no_other_name": 0,
        "rest_self": 0,
        "leader_power_cost": 0,
        "search_enrich": 0,
        "search_add": 0,
        "return_don": 0,
        "buff0": 0,
        "once": 0,
        "cards_touched": 0,
    }
    touched: list[str] = []
    reload_effect_library(force=True)

    for cid, rev in (semantic.get("cards") or {}).items():
        if rev.get("verdict") != "issue":
            continue
        merged = get_card_entry(cid)
        abilities = [dict(a) for a in (merged.get("abilities") or []) if isinstance(a, dict)]
        if not abilities:
            continue
        blob = effect_blob(catalog.get(cid) or {})
        multi = len(abilities) > 1
        changed = False
        new_abs: list[dict] = []

        for ability in abilities:
            timing = str(ability.get("timing") or "")
            chunk = _trim_cross_timing(_timing_chunk(blob, timing), timing)
            summary = _trim_cross_timing(str(ability.get("summary") or "").strip(), timing)
            # Never fall back to full card blob on multi-ability cards — that
            # bleeds gates/costs across timings (e.g. rest_self from Activate Main).
            if multi:
                scope = summary if len(summary) >= 12 else (chunk if chunk != blob else summary)
            else:
                scope = summary if len(summary) >= 18 else (chunk or blob)
            if len(scope) < 12:
                scope = summary or chunk
            gate_scope = chunk if (chunk and chunk != blob) else scope
            if multi and (not gate_scope or gate_scope == blob):
                gate_scope = scope
            gate_scope = _trim_cross_timing(gate_scope, timing)
            scope = _trim_cross_timing(scope, timing)

            # leader trait (scope-local only — never whole-card blob)
            if not ability.get("require_leader_trait"):
                m = LEADER_TRAIT_RE.search(gate_scope) or LEADER_TRAIT_RE.search(scope)
                if m:
                    traits = [g.strip() for g in m.groups() if g and g.strip()]
                    # Prefer {...} English traits when present in the match.
                    brace = re.findall(r"\{([^}]+)\}", m.group(0))
                    if brace:
                        traits = [t.strip() for t in brace if t.strip()]
                    if traits:
                        ability["require_leader_trait"] = "|".join(traits)[:80]
                        stats["leader_trait"] += 1
                        changed = True
            if not ability.get("require_leader_name"):
                m = LEADER_NAME_RE.search(gate_scope) or LEADER_NAME_RE.search(scope)
                if m:
                    ability["require_leader_name"] = m.group(1).strip()[:60]
                    stats["leader_trait"] += 1
                    changed = True

            # DON!! xN
            if ability.get("require_don_attached_gte") is None:
                m = DON_X_RE.search(gate_scope) or DON_X_RE.search(scope)
                if m:
                    n = int(next(g for g in m.groups() if g))
                    ability["require_don_attached_gte"] = max(1, min(10, n))
                    stats["don_x"] += 1
                    changed = True

            # chars gte/lte
            if ability.get("require_chars_gte") is None:
                m = CHARS_GTE_RE.search(gate_scope) or CHARS_GTE_RE.search(scope)
                if m:
                    ability["require_chars_gte"] = int(next(g for g in m.groups() if g))
                    stats["chars_gte"] += 1
                    changed = True
            if ability.get("require_chars_lte") is None:
                m = CHARS_LTE_RE.search(gate_scope) or CHARS_LTE_RE.search(scope)
                if m:
                    ability["require_chars_lte"] = int(next(g for g in m.groups() if g))
                    stats["chars_lte"] += 1
                    changed = True

            # unique name
            if not ability.get("require_no_other_name"):
                m = NO_OTHER_NAME_RE.search(gate_scope) or NO_OTHER_NAME_RE.search(scope)
                if m:
                    ability["require_no_other_name"] = next(g for g in m.groups() if g).strip()[:60]
                    stats["no_other_name"] += 1
                    changed = True

            # rest_self cost
            if not ability.get("rest_self") and REST_SELF_RE.search(gate_scope):
                ability["rest_self"] = True
                stats["rest_self"] += 1
                changed = True

            # once
            if not ability.get("once") and re.search(r"once per turn|每回合1次|每回合一次", gate_scope, re.I):
                ability["once"] = True
                stats["once"] += 1
                changed = True

            ops = [dict(o) for o in (ability.get("ops") or [])]

            # leader power cost → buff/buff_self as_cost
            m_cost = LEADER_POWER_COST_RE.search(gate_scope)
            if m_cost:
                amt = -abs(int(next(g for g in m_cost.groups() if g)))
                has = False
                for i, o in enumerate(ops):
                    if o.get("op") in {"buff_self", "buff"} and int(o.get("amount") or 0) < 0:
                        o = dict(o)
                        o["amount"] = amt
                        o["optional"] = True
                        o["as_cost"] = True
                        if o.get("op") == "buff":
                            o["target_kind"] = "leader"
                        ops[i] = o
                        has = True
                        stats["leader_power_cost"] += 1
                        changed = True
                        break
                if not has:
                    ops.insert(
                        0,
                        {
                            "op": "buff",
                            "amount": amt,
                            "target_kind": "leader",
                            "optional": True,
                            "as_cost": True,
                        },
                    )
                    stats["leader_power_cost"] += 1
                    changed = True

            # enrich / add search_deck
            parsed_search = _parse_look_top_search(gate_scope) or _parse_look_top_search(chunk)
            if parsed_search:
                # also pick cost_lte for play-from-search style if present in text
                m_cl = re.search(
                    r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下",
                    gate_scope,
                    re.I,
                )
                if m_cl and parsed_search.get("cost_eq") is None and parsed_search.get("cost_lte") is None:
                    # only if reveal mentions cost filter for character
                    if re.search(r"Character|角色", gate_scope, re.I):
                        parsed_search["cost_lte"] = int(next(g for g in m_cl.groups() if g))
                found = False
                for i, o in enumerate(ops):
                    if o.get("op") != "search_deck":
                        continue
                    o = dict(o)
                    for k in ("top_n", "max_add", "trait_contains", "name_contains", "cost_eq", "cost_lte", "exclude_name", "order_bottom"):
                        if parsed_search.get(k) is not None and (o.get(k) in (None, "", 0) or k == "order_bottom"):
                            if k == "order_bottom" or o.get(k) in (None, ""):
                                o[k] = parsed_search[k]
                    ops[i] = o
                    found = True
                    stats["search_enrich"] += 1
                    changed = True
                    break
                if not found and re.search(r"look at|查看|檢視|检视", gate_scope, re.I):
                    ops.append(parsed_search)
                    stats["search_add"] += 1
                    changed = True

            # return_don
            if not any(o.get("op") == "return_don" for o in ops) and not ability.get("cost_don"):
                m = re.search(
                    r"\[DON!!\s*[−\-－]\s*(\d+)\]|【咚‼?\s*[−\-－]\s*(\d+)】|"
                    r"DON!!\s*[−\-－]\s*(\d+)\s*:|咚‼?\s*[−\-－]\s*(\d+)\s*[：:]",
                    gate_scope,
                    re.I,
                )
                if m:
                    n = int(next(g for g in m.groups() if g))
                    ops.insert(0, {"op": "return_don", "count": max(1, min(5, n))})
                    stats["return_don"] += 1
                    changed = True

            # buff0 / tiny amount
            for i, o in enumerate(ops):
                if o.get("op") != "buff":
                    continue
                try:
                    amt = int(o.get("amount") or 0)
                except (TypeError, ValueError):
                    amt = 0
                if abs(amt) >= 100:
                    continue
                m = AMT_RE.search(gate_scope) or AMT_RE.search(scope)
                if not m:
                    continue
                parsed = _parse_amt(next(g for g in m.groups() if g))
                if parsed is None or abs(parsed) < 100:
                    continue
                o = dict(o)
                o["amount"] = parsed
                ops[i] = o
                stats["buff0"] += 1
                changed = True

            # Drop redundant rest_character self when rest_self flag covers cost
            if ability.get("rest_self"):
                cleaned = []
                for o in ops:
                    if (
                        o.get("op") in {"rest_character", "rest_opponent_character"}
                        and str(o.get("target_kind") or "") in {"self", "own_character", ""}
                        and len(ops) > 1
                        and REST_SELF_RE.search(gate_scope)
                    ):
                        # keep if it's the effect (rest opponent), drop self-rest cost dup
                        if "opponent" not in str(o.get("target_kind") or "") and not re.search(
                            r"rest up to|置為休息狀態的對手|置为休息状态的对手",
                            gate_scope,
                            re.I,
                        ):
                            # only drop obvious self cost ops without filters
                            if o.get("op") == "rest_character" and o.get("cost_lte") is None:
                                changed = True
                                continue
                    cleaned.append(o)
                ops = cleaned

            ops = _enrich_ops_with_target_filters(ops, gate_scope)
            ability["ops"] = ops
            na = normalize_ability(ability)
            if na:
                new_abs.append(na)

        if not changed:
            continue
        fixed = normalize_card_entry(cid, {"version": 1, "abilities": new_abs})
        cards[cid] = fixed
        overrides[cid] = fixed
        stats["cards_touched"] += 1
        touched.append(cid)

    print(json.dumps(stats, ensure_ascii=False), flush=True)
    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    OUT_IDS.write_text("\n".join(touched) + ("\n" if touched else ""), encoding="utf-8")
    print(f"Wrote ids {OUT_IDS} ({len(touched)})", flush=True)
    if args.dry_run:
        return 0

    payload = {"version": 1, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cards": cards}
    tmp = lib_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(lib_path)

    ovr_payload = dict(ovr_raw) if isinstance(ovr_raw, dict) else {}
    ovr_payload["cards"] = overrides
    ovr_payload["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp_o = ovr_path.with_suffix(".json.tmp")
    tmp_o.write_text(json.dumps(ovr_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp_o.replace(ovr_path)
    reload_effect_library(force=True)
    print(f"Wrote {lib_path}", flush=True)
    print(f"Wrote {ovr_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
