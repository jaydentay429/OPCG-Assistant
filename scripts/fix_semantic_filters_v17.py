#!/usr/bin/env python3
"""Inject missing filters, fix rest-own costs, RTH own targets, play-from-trash.

Writes library + overrides.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from battle.effect_library import get_card_entry, library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability, normalize_card_entry  # noqa: E402
from battle.effects import effect_blob  # noqa: E402
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "filters_v17_fixed_ids.txt"

COST_LTE_RE = re.compile(
    r"(?:with a |a )?cost of\s*(\d+)\s*or less|"
    r"(?:費用|费用)\s*(\d+)\s*以下",
    re.I,
)
COST_GTE_RE = re.compile(
    r"(?:with a |a )?cost of\s*(\d+)\s*or more|"
    r"(?:費用|费用)\s*(\d+)\s*以上",
    re.I,
)
POWER_LTE_RE = re.compile(
    r"(?:with (?:a )?(?:base )?power of|power of)\s*(\d+)\s*or less|"
    r"(?:原本)?力量值\s*(\d+)\s*以下",
    re.I,
)
BASE_POWER_LTE_RE = re.compile(
    r"(?:with (?:a )?base power of|base power of)\s*(\d+)\s*or less|"
    r"原本力量值\s*(\d+)\s*以下",
    re.I,
)
TRAIT_RE = re.compile(
    r"\{([^}]+)\}\s*type|"
    r"擁有《([^》]+)》特徵|拥有《([^》]+)》特征|"
    r"《([^》]+)》特徵|《([^》]+)》特征",
    re.I,
)
NAME_RE = re.compile(
    r"\[([^\]]{2,40})\]|"
    r"「([^」]{2,40})」|"
    r"角色卡「([^」]{2,40})」",
    re.I,
)
TRIGGER_RE = re.compile(r"\[Trigger\]|持有【觸發器】|持有【触发器】|持有【觸發】|持有【触发】", re.I)
PLAY_FROM_TRASH_RE = re.compile(
    r"from your (?:hand or )?trash|from your trash|"
    r"從(?:手牌或)?廢棄區|从(?:手牌或)?废弃区",
    re.I,
)
REST_OWN_COST_RE = re.compile(
    r"(?:you may )?rest\s*(?:this card and\s*)?(?:1 of )?your|"
    r"可?[將将](?:這張卡片和)?(?:1[張张])?自己|"
    r"可?[將将]這張(?:角色卡|卡片)置[為为]休息",
    re.I,
)
RTH_OWN_RE = re.compile(
    r"return 1 of your Characters to (?:your|the owner'?s?) hand|"
    r"[將将]1[張张]自己的角色卡放回|"
    r"return .{0,40}your Characters?.{0,20}hand",
    re.I,
)
CHARS_GTE_RE = re.compile(
    r"if you have\s*(\d+)\s*Characters|"
    r"若自己的角色卡有\s*(\d+)\s*[張张]|"
    r"若場上有\s*(\d+)\s*[張张]自己的角色",
    re.I,
)
LEADER_GATE_RE = re.compile(
    r"if your Leader (?:has|is)|若自己的領航卡|若自己的领航卡",
    re.I,
)
GRANT_OTHER_RE = re.compile(
    r"(?:gains?|gets?|give).{0,40}\[(?:Blocker|Rush|Double Attack|Banish)\]|"
    r"獲得【(?:防禦|速攻|双重攻击|雙重攻擊|消失)】|获得【(?:防御|速攻|双重攻击|消失)】",
    re.I,
)


def _num(m: re.Match[str] | None) -> int | None:
    if not m:
        return None
    return int(next(g for g in m.groups() if g))


def _split_cost_body(chunk: str) -> tuple[str, str]:
    """Split optional colon-cost preface from effect body."""
    m = re.search(r"[:：]", chunk)
    if not m:
        return "", chunk
    pre, body = chunk[: m.start()], chunk[m.end() :]
    if REST_OWN_COST_RE.search(pre) or re.search(
        r"you may (?:trash|return|rest)|可[將将]|DON!!\s*[−\-－]|咚‼?\s*[−\-－]",
        pre,
        re.I,
    ):
        return pre, body
    return "", chunk


def _extract_filters(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    n = _num(COST_LTE_RE.search(text))
    if n is not None:
        out["cost_lte"] = n
    n = _num(COST_GTE_RE.search(text))
    if n is not None:
        out["cost_gte"] = n
    n = _num(BASE_POWER_LTE_RE.search(text))
    if n is not None:
        out["base_power_lte"] = n
    else:
        n = _num(POWER_LTE_RE.search(text))
        if n is not None:
            out["power_lte"] = n
    if TRIGGER_RE.search(text):
        out["require_trigger"] = True
    m_tr = TRAIT_RE.search(text)
    if m_tr:
        out["trait_contains"] = next(g for g in m_tr.groups() if g).strip()
    # Prefer bracket names near play/KO verbs; skip Trigger/DON/Activate labels.
    for m in NAME_RE.finditer(text):
        name = next(g for g in m.groups() if g).strip()
        if name.lower() in {
            "trigger",
            "blocker",
            "rush",
            "banish",
            "double attack",
            "once per turn",
            "main",
            "counter",
            "on play",
            "activate: main",
            "don!! x1",
            "don!! x2",
        }:
            continue
        if re.search(r"^(?:DON|费用|費用|\d)", name, re.I):
            continue
        out["name_contains"] = name
        break
    return out


def _apply_filters(op: dict[str, Any], filt: dict[str, Any], keys: list[str]) -> bool:
    changed = False
    for k in keys:
        if k not in filt:
            continue
        if op.get(k) in (None, "", False):
            op[k] = filt[k]
            changed = True
        elif k.endswith("_lte") or k.endswith("_gte") or k.endswith("_eq"):
            if int(op.get(k) or 0) != int(filt[k]):
                # Only overwrite when missing-like zero or clearly wrong empty; keep existing if set.
                pass
    return changed


def _parse_rest_own_cost(pre: str) -> dict[str, Any] | None:
    if not REST_OWN_COST_RE.search(pre):
        return None
    if re.search(r"opponent|對手|对手", pre, re.I) and not re.search(r"your |自己", pre, re.I):
        return None
    op: dict[str, Any] = {
        "op": "rest_character",
        "target_kind": "own_character",
        "optional": True,
        "as_cost": True,
        "count": 1,
    }
    if re.search(r"this (?:Character|card)|這張(?:角色卡|卡片)|这张(?:角色卡|卡片)", pre, re.I) and not re.search(
        r"this card and|這張卡片和|这张卡片和", pre, re.I
    ):
        op["target_kind"] = "self"
    if re.search(r"Leader or Stage|領航卡或舞台|领航卡或舞台", pre, re.I):
        op["target_kind"] = "own_leader_or_character"
        op["summary"] = "Rest own Leader or Stage"
    elif re.search(r"Leader or Character|領航卡或角色|领航卡或角色", pre, re.I):
        op["target_kind"] = "own_leader_or_character"
    elif re.search(r"your cards?:|自己的卡片", pre, re.I):
        op["target_kind"] = "own_character"
        op["summary"] = "Rest 1 of your cards"
    filt = _extract_filters(pre)
    for k in ("cost_lte", "cost_gte", "cost_eq", "trait_contains", "name_contains"):
        if k in filt:
            op[k] = filt[k]
    # "this card and 1 of your [Name]"
    m_and = re.search(
        r"this card and 1 of your \[([^\]]+)\]|"
        r"這張卡片和1[張张]自己的「([^」]+)」|"
        r"这张卡片和1[张張]自己的「([^」]+)」",
        pre,
        re.I,
    )
    if m_and:
        # Represent as rest self + rest named own character (two ops handled by caller)
        return {
            "_pair": [
                {"op": "rest_character", "target_kind": "self", "optional": True, "as_cost": True},
                {
                    "op": "rest_character",
                    "target_kind": "own_character",
                    "optional": True,
                    "as_cost": True,
                    "name_contains": next(g for g in m_and.groups() if g).strip(),
                },
            ]
        }
    return op


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
        "filters": 0,
        "rest_own_cost": 0,
        "rth_own": 0,
        "play_trash": 0,
        "chars_gate": 0,
        "drop_leader_gate": 0,
        "grant_kw": 0,
        "drop_extra_rest_opp": 0,
        "cards_touched": 0,
    }
    touched: list[str] = []
    reload_effect_library(force=True)

    targets = [cid for cid, rev in (semantic.get("cards") or {}).items() if rev.get("verdict") == "issue"]
    qpath = ROOT / "meta" / "effect_problem_queue.json"
    if qpath.is_file():
        for it in json.loads(qpath.read_text(encoding="utf-8")).get("items") or []:
            if it.get("status") == "open":
                targets.append(it["id"])
    targets = sorted(set(targets))

    own_card_kinds = {
        "own_character",
        "own_leader_or_character",
        "own_character_or_leader",
        "self",
        "leader",
    }

    for cid in targets:
        info = catalog.get(cid) or {}
        blob = effect_blob(info)
        merged = get_card_entry(cid)
        abilities = [dict(a) for a in (merged.get("abilities") or []) if isinstance(a, dict)]
        if not abilities:
            continue
        changed = False
        new_abs: list[dict] = []
        multi = len(abilities) > 1

        for a in abilities:
            a = dict(a)
            timing = str(a.get("timing") or "")
            chunk = _trim_cross_timing(_timing_chunk(blob, timing), timing) or ""
            if multi and (not chunk or chunk == blob):
                chunk = _trim_cross_timing(str(a.get("summary") or ""), timing) or chunk
            ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]
            pre, body = _split_cost_body(chunk)

            # 1) Inject / fix rest-own as cost
            rest_spec = _parse_rest_own_cost(pre) if pre else None
            if rest_spec:
                pair = rest_spec.get("_pair")
                want_ops = pair if isinstance(pair, list) else [rest_spec]
                has_own_rest = any(
                    o.get("op") in {"rest_character", "rest_opponent_character"}
                    and (
                        str(o.get("target_kind") or "") in own_card_kinds
                        or o.get("as_cost")
                    )
                    for o in ops
                )
                # Fix wrong opponent rest used as the only rest when paper is own rest cost
                wrong = [
                    o
                    for o in ops
                    if o.get("op") in {"rest_character", "rest_opponent_character"}
                    and "opponent" in str(o.get("target_kind") or "")
                    and o.get("as_cost")
                ]
                if wrong and not has_own_rest:
                    for o in wrong:
                        o["op"] = "rest_character"
                        o["target_kind"] = want_ops[0].get("target_kind") or "own_character"
                        for k, v in want_ops[0].items():
                            if k != "op" and v is not None:
                                o[k] = v
                        stats["rest_own_cost"] += 1
                        changed = True
                    has_own_rest = True
                if not has_own_rest and not any(
                    o.get("op") == "rest_character" and str(o.get("target_kind") or "") in own_card_kinds for o in ops
                ):
                    # Drop spurious opponent rest if paper cost is own-rest and body has no rest-opp
                    if not re.search(r"rest up to .{0,20}opponent|將最多.{0,20}對手|将最多.{0,20}对手", body, re.I):
                        before = len(ops)
                        ops = [
                            o
                            for o in ops
                            if not (
                                o.get("op") in {"rest_character", "rest_opponent_character"}
                                and "opponent" in str(o.get("target_kind") or "")
                            )
                        ]
                        if len(ops) < before:
                            stats["drop_extra_rest_opp"] += 1
                            changed = True
                    ops = list(want_ops) + ops
                    stats["rest_own_cost"] += 1
                    changed = True
                elif has_own_rest:
                    for o in ops:
                        if o.get("op") == "rest_character" and str(o.get("target_kind") or "") in own_card_kinds:
                            if not o.get("as_cost"):
                                o["as_cost"] = True
                                changed = True
                                stats["rest_own_cost"] += 1
                            for k, v in want_ops[0].items():
                                if k in {"cost_lte", "cost_gte", "trait_contains", "name_contains", "target_kind"} and v:
                                    if o.get(k) in (None, ""):
                                        o[k] = v
                                        changed = True

            # 2) RTH own
            if RTH_OWN_RE.search(chunk) or RTH_OWN_RE.search(body):
                for o in ops:
                    if o.get("op") == "return_to_hand" and "opponent" in str(o.get("target_kind") or ""):
                        o["target_kind"] = "own_character"
                        stats["rth_own"] += 1
                        changed = True

            # 3) chars gate
            m_chars = CHARS_GTE_RE.search(chunk)
            if m_chars:
                n = int(next(g for g in m_chars.groups() if g))
                if int(a.get("require_chars_gte") or 0) != n:
                    a["require_chars_gte"] = n
                    stats["chars_gate"] += 1
                    changed = True

            # 4) Drop leader gates when timing chunk has no leader condition
            if not LEADER_GATE_RE.search(chunk):
                for key in ("require_leader_name", "require_leader_trait", "require_leader_color"):
                    if a.get(key):
                        a.pop(key, None)
                        stats["drop_leader_gate"] += 1
                        changed = True

            # 5) play_from_hand filters + from_zone
            play_window = body if body else chunk
            # Prefer the play-clause window
            m_play = re.search(
                r"(?:play up to|Play up to|使最多|從手牌|从手牌|from your hand|from your trash).{0,160}",
                play_window,
                re.I,
            )
            play_text = m_play.group(0) if m_play else play_window
            play_filt = _extract_filters(play_text)
            for o in ops:
                if o.get("op") != "play_from_hand":
                    continue
                if PLAY_FROM_TRASH_RE.search(play_text) or PLAY_FROM_TRASH_RE.search(chunk):
                    want_zone = "hand_or_trash" if re.search(r"hand or trash|手牌或廢棄|手牌或废弃", chunk, re.I) else "trash"
                    if re.search(r"from your hand or trash|手牌或", chunk, re.I):
                        want_zone = "hand_or_trash"
                    elif re.search(r"from your trash|從廢棄區|从废弃区", chunk, re.I) and not re.search(
                        r"from your hand(?! or trash)", chunk, re.I
                    ):
                        want_zone = "trash"
                    else:
                        want_zone = str(o.get("from_zone") or "hand")
                    if want_zone in {"trash", "hand_or_trash"} and o.get("from_zone") != want_zone:
                        # Only upgrade when paper mentions trash
                        if PLAY_FROM_TRASH_RE.search(chunk):
                            if re.search(r"hand or trash|手牌或", chunk, re.I):
                                o["from_zone"] = "hand_or_trash"
                            elif re.search(r"from your trash|從廢棄區|从废弃区", chunk, re.I):
                                o["from_zone"] = "trash"
                            stats["play_trash"] += 1
                            changed = True
                if _apply_filters(
                    o,
                    play_filt,
                    ["cost_lte", "power_lte", "base_power_lte", "trait_contains", "name_contains", "require_trigger"],
                ):
                    stats["filters"] += 1
                    changed = True

            # 6) KO / trash / RTH / rest_opponent filters from body
            for verb, opnames in (
                (r"K\.?O\.?|击破|擊破|KO", {"ko"}),
                (r"return .{0,40}hand|放回持有者的手牌|放回手牌", {"return_to_hand"}),
                (r"trash|廢棄|废弃|放置到廢棄|放置到废弃", {"trash"}),
                (r"rest up to .{0,30}opponent|將最多.{0,30}對手.{0,20}休息|将最多.{0,30}对手.{0,20}休息", {"rest_opponent_character", "rest_character"}),
                (r"negate|無效|无效", {"negate_effects"}),
                (r"cannot attack|無法攻擊|无法攻击", {"deny_attack", "cannot_attack"}),
            ):
                m_v = re.search(verb + r".{0,140}", body or chunk, re.I)
                if not m_v:
                    continue
                filt = _extract_filters(m_v.group(0))
                for o in ops:
                    if o.get("op") not in opnames:
                        continue
                    # Don't overwrite own-rest cost filters with opponent effect filters
                    if o.get("as_cost") and o.get("op") == "rest_character":
                        continue
                    keys = ["cost_lte", "cost_eq", "power_lte", "base_power_lte", "trait_contains", "require_trigger"]
                    if _apply_filters(o, filt, keys):
                        stats["filters"] += 1
                        changed = True

            # 7) grant_keyword target: paper grants to another card, not self
            if GRANT_OTHER_RE.search(chunk) and re.search(
                r"up to 1 of your|最多1[張张]自己|Leader or Character|領航卡或角色|领航卡或角色|"
                r"your \[[^\]]+\] Characters?|自己的「",
                chunk,
                re.I,
            ):
                for o in ops:
                    if o.get("op") == "grant_keyword" and o.get("target_kind") in {None, "", "self"}:
                        if re.search(r"Leader or Character|領航卡或角色|领航卡或角色", chunk, re.I):
                            o["target_kind"] = "own_leader_or_character"
                        else:
                            o["target_kind"] = "own_character"
                        o["optional"] = True
                        # name filter if present near grant
                        nf = _extract_filters(chunk)
                        if nf.get("name_contains") and not o.get("name_contains"):
                            o["name_contains"] = nf["name_contains"]
                        stats["grant_kw"] += 1
                        changed = True

            # 8) Drop extra rest_opponent when paper has no rest-opponent clause
            if any(o.get("op") in {"rest_opponent_character", "rest_character"} and "opponent" in str(o.get("target_kind") or "") for o in ops):
                if not re.search(
                    r"rest (?:up to \d+ of )?your opponent|將最多.{0,40}對手.{0,30}置[為为]休息|"
                    r"将最多.{0,40}对手.{0,30}置为休息|rest 1 of your opponent",
                    chunk,
                    re.I,
                ):
                    before = len(ops)
                    ops = [
                        o
                        for o in ops
                        if not (
                            o.get("op") in {"rest_opponent_character", "rest_character"}
                            and "opponent" in str(o.get("target_kind") or "")
                            and not o.get("as_cost")
                        )
                    ]
                    if len(ops) < before:
                        stats["drop_extra_rest_opp"] += 1
                        changed = True

            a["ops"] = ops
            na = normalize_ability(a)
            if na:
                new_abs.append(na)

        if not changed:
            continue
        fixed = normalize_card_entry(cid, {"version": 1, "abilities": new_abs})
        cards[cid] = fixed
        overrides[cid] = fixed
        stats["cards_touched"] += 1
        touched.append(cid)

    print(json.dumps({"stats": stats, "touched": len(touched)}, ensure_ascii=False))
    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    OUT_IDS.write_text("\n".join(touched) + ("\n" if touched else ""), encoding="utf-8")
    if args.dry_run:
        return 0
    raw["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if "cards" in raw:
        raw["cards"] = cards
    lib_path.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ovr_raw["cards"] = overrides
    ovr_raw["generated_at"] = raw["generated_at"]
    ovr_path.write_text(json.dumps(ovr_raw, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    reload_effect_library(force=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
