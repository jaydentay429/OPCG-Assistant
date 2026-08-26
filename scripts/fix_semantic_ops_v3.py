#!/usr/bin/env python3
"""Inject missing rest_don/cost_don, KO, keywords, play/draw/gain/rth ops.

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
    _parse_grant_keyword_ops,
    _parse_ko_op,
    _parse_return_char_to_hand_ops,
    effect_blob,
)

# Reuse timing helpers from gates_v2 when available.
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # type: ignore
except Exception:
    def _timing_chunk(blob: str, timing: str) -> str:
        return blob

    def _trim_cross_timing(text: str, timing: str) -> str:
        return text

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "ops_v3_fixed_ids.txt"

REST_DON_RE = re.compile(
    r"(?:you may )?rest\s*(\d+)\s*of your don(?:‼|!!)?\s*cards?\s*:|"
    r"可[將将]\s*(\d+)\s*[張张]?自己的咚.{0,16}置[為为]休息\s*[：:]|"
    r"[將将]\s*(\d+)\s*[張张]?自己的咚.{0,16}置[為为]休息\s*[：:]",
    re.I,
)
DRAW_RE = re.compile(r"draw\s*(?:up to\s*)?(\d+)\b|抽\s*(\d+)\s*[張张]", re.I)
GAIN_DON_RE = re.compile(
    r"add up to\s*(\d+)\s*DON(?:‼|!!)\s*cards? from your DON|"
    r"從咚‼?卡組追加最多\s*(\d+)|从咚‼?卡组追加最多\s*(\d+)|"
    r"追加最多\s*(\d+)\s*[張张]?活動狀態的咚|追加最多\s*(\d+)\s*[张张]?活动状态的咚",
    re.I,
)
ADD_LIFE_RE = re.compile(
    r"add (?:up to\s*)?(\d+).{0,40}from the top of your deck.{0,30}Life|"
    r"[將将]最多\s*(\d+)\s*[張张]自己卡組上面的卡片加入生命|"
    r"從自己的卡組上面加入\s*(\d+)\s*[張张].{0,12}生命",
    re.I,
)
PLAY_HAND_RE = re.compile(
    r"play up to\s*(\d+).{0,80}from (?:your )?hand|"
    r"使最多\s*(\d+)\s*[張张].{0,40}手牌.{0,30}登場|"
    r"使最多\s*(\d+)\s*[张张].{0,40}手牌.{0,30}登场",
    re.I,
)
TRASH_COST_RE = re.compile(
    r"you may trash\s*(\d+).{0,40}hand\s*:|"
    r"可以廢棄\s*(\d+)\s*[張张]自己的手牌\s*[：:]|"
    r"可以废弃\s*(\d+)\s*[张张]自己的手牌\s*[：:]",
    re.I,
)
REDUCE_COST_RE = re.compile(
    r"(?:give|gets?).{0,60}[−\-－]\s*(\d+)\s*cost|"
    r"費用\s*[−\-－]\s*(\d+)|费用\s*[−\-－]\s*(\d+)",
    re.I,
)


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
        "cost_don": 0,
        "rest_don": 0,
        "ko": 0,
        "keyword": 0,
        "draw": 0,
        "gain_don": 0,
        "add_life": 0,
        "play_hand": 0,
        "trash_cost": 0,
        "rth": 0,
        "rth_fix": 0,
        "reduce_cost": 0,
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
            if multi:
                scope = summary if len(summary) >= 12 else (chunk if chunk != blob else summary)
            else:
                scope = summary if len(summary) >= 18 else (chunk or blob)
            gate_scope = chunk if (chunk and chunk != blob) else scope
            if multi and (not gate_scope or gate_scope == blob):
                gate_scope = scope
            gate_scope = _trim_cross_timing(gate_scope, timing)
            scope = _trim_cross_timing(scope, timing)
            text = f"{gate_scope}\n{scope}"

            ops = [dict(o) for o in (ability.get("ops") or [])]

            # rest N DON as cost → cost_don (preferred) or rest_don op
            m_rd = REST_DON_RE.search(text)
            if m_rd:
                n = int(next(g for g in m_rd.groups() if g))
                if timing in {"activate_main", "main_start", "on_play", "when_attacking", "on_opponent_attack", "end_of_your_turn"}:
                    if int(ability.get("cost_don") or 0) < n:
                        ability["cost_don"] = n
                        stats["cost_don"] += 1
                        changed = True
                if not any(o.get("op") == "rest_don" and int(o.get("count") or 0) == n for o in ops):
                    # Keep a visible rest_don cost op for non-activate or when cost_don alone is easy to miss
                    if timing not in {"activate_main"} or int(ability.get("cost_don") or 0) != n:
                        ops.insert(0, {"op": "rest_don", "count": n, "as_cost": True})
                        stats["rest_don"] += 1
                        changed = True
                    elif timing == "activate_main" and not any(o.get("op") == "rest_don" for o in ops):
                        # still add for semantic clarity matching paper
                        ops.insert(0, {"op": "rest_don", "count": n, "as_cost": True})
                        stats["rest_don"] += 1
                        changed = True
                else:
                    for i, o in enumerate(ops):
                        if o.get("op") == "rest_don" and int(o.get("count") or 0) != n:
                            o = dict(o)
                            o["count"] = n
                            o["as_cost"] = True
                            ops[i] = o
                            stats["rest_don"] += 1
                            changed = True

            # KO
            if not any(o.get("op") in {"ko", "ko_lowest_opponent"} for o in ops):
                ko = _parse_ko_op(text)
                if ko and re.search(r"K\.?O|KO", text, re.I):
                    # Emit one op per count for engine compatibility if needed
                    cnt = int(ko.get("count") or 1)
                    base = dict(ko)
                    base.pop("count", None)
                    for _ in range(cnt):
                        ops.append(dict(base))
                    stats["ko"] += 1
                    changed = True

            # Keywords
            for gop in _parse_grant_keyword_ops(text):
                kw = str(gop.get("keyword") or "")
                if any(
                    o.get("op") == "grant_keyword" and str(o.get("keyword") or "") == kw
                    for o in ops
                ):
                    continue
                ops.append(gop)
                stats["keyword"] += 1
                changed = True

            # Draw count
            m_d = DRAW_RE.search(text)
            if m_d and re.search(r"draw|抽", text, re.I):
                n = int(next(g for g in m_d.groups() if g))
                if 1 <= n <= 5:
                    draws = [o for o in ops if o.get("op") == "draw"]
                    if not draws:
                        ops.append({"op": "draw", "count": n})
                        stats["draw"] += 1
                        changed = True
                    elif all(int(o.get("count") or 0) != n for o in draws):
                        # fix first draw
                        for i, o in enumerate(ops):
                            if o.get("op") == "draw":
                                o = dict(o)
                                o["count"] = n
                                ops[i] = o
                                stats["draw"] += 1
                                changed = True
                                break

            # gain_don
            m_g = GAIN_DON_RE.search(text)
            if m_g and not any(o.get("op") in {"gain_don", "set_don"} for o in ops):
                n = int(next(g for g in m_g.groups() if g))
                op = {"op": "gain_don", "count": max(1, min(5, n))}
                if re.search(r"rested DON|休息狀態的咚|休息状态的咚", text, re.I):
                    op["as_rested"] = True
                ops.append(op)
                stats["gain_don"] += 1
                changed = True

            # add_life from deck
            m_al = ADD_LIFE_RE.search(text)
            if m_al and not any(o.get("op") == "add_life" for o in ops):
                n = int(next(g for g in m_al.groups() if g))
                ops.append({"op": "add_life", "count": max(1, min(5, n)), "optional": True})
                stats["add_life"] += 1
                changed = True

            # play from hand
            m_ph = PLAY_HAND_RE.search(text)
            if m_ph and not any(o.get("op") == "play_from_hand" for o in ops):
                n = int(next(g for g in m_ph.groups() if g))
                op: dict = {
                    "op": "play_from_hand",
                    "count": max(1, min(3, n)),
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                }
                m_c = re.search(
                    r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下",
                    text,
                    re.I,
                )
                if m_c:
                    op["cost_lte"] = int(next(g for g in m_c.groups() if g))
                m_tr = re.search(r"\{([^}]+)\}\s*type|擁有《([^》]+)》特徵|拥有《([^》]+)》特征", text, re.I)
                if m_tr:
                    op["trait_contains"] = next(g for g in m_tr.groups() if g)
                ops.append(op)
                stats["play_hand"] += 1
                changed = True

            # trash hand as cost
            m_th = TRASH_COST_RE.search(text)
            if m_th:
                n = int(next(g for g in m_th.groups() if g))
                ths = [i for i, o in enumerate(ops) if o.get("op") == "trash_hand"]
                if not ths:
                    ops.insert(0, {"op": "trash_hand", "count": n, "optional": True, "as_cost": True})
                    stats["trash_cost"] += 1
                    changed = True
                else:
                    i = ths[0]
                    o = dict(ops[i])
                    if not o.get("as_cost") or int(o.get("count") or 0) != n:
                        o["count"] = n
                        o["as_cost"] = True
                        o["optional"] = True
                        ops[i] = o
                        stats["trash_cost"] += 1
                        changed = True

            # return to hand
            if not any(o.get("op") == "return_to_hand" for o in ops):
                for rop in _parse_return_char_to_hand_ops(text):
                    ops.append(rop)
                    stats["rth"] += 1
                    changed = True
                    break

            # fix wrong rth target: opponent chooses own active character
            if re.search(
                r"your opponent returns?.{0,40}active Character|"
                r"對手將.{0,20}自身活動狀態的角色|对手将.{0,20}自身活动状态的角色",
                text,
                re.I,
            ):
                for i, o in enumerate(ops):
                    if o.get("op") == "return_to_hand" and "opponent_character_active" not in str(
                        o.get("target_kind") or ""
                    ):
                        o = dict(o)
                        o["target_kind"] = "opponent_character_active"
                        ops[i] = o
                        stats["rth_fix"] += 1
                        changed = True

            # reduce_cost
            m_rc = REDUCE_COST_RE.search(text)
            if m_rc and not any(o.get("op") in {"reduce_cost", "set_cost", "hand_cost_reduce"} for o in ops):
                if re.search(r"opponent|對手|对手", text, re.I) or re.search(
                    r"Character|角色", text, re.I
                ):
                    amt = -abs(int(next(g for g in m_rc.groups() if g)))
                    ops.append(
                        {
                            "op": "reduce_cost",
                            "amount": amt,
                            "count": 1,
                            "target_kind": "opponent_character",
                            "optional": True,
                        }
                    )
                    stats["reduce_cost"] += 1
                    changed = True

            ops = _enrich_ops_with_target_filters(ops, text)
            ability["ops"] = ops
            # preserve trimmed summary when it removes cross-timing noise
            if summary and len(summary) >= 12:
                ability["summary"] = summary[:240]
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
