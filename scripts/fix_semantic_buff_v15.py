#!/usr/bin/env python3
"""Fix buff amount caps, inject missing buffs/rest/cannot_be_ko, opponent hand bottom.

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
sys.path.insert(0, str(ROOT / "scripts"))

from battle.effect_library import get_card_entry, library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability, normalize_card_entry  # noqa: E402
from battle.effects import (  # noqa: E402
    _parse_cannot_be_ko_ops,
    _parse_opponent_hand_to_bottom_ops,
    _parse_power_buff_amount,
    _parse_rest_opponent_ops,
    effect_blob,
)
from fix_semantic_gates_v2 import DON_X_RE, _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "buff_v15_fixed_ids.txt"

BUFF_RE = re.compile(
    r"(?:gains?|gets?)\s*([+＋−\-－])\s*(\d{3,5})\s*power|"
    r"力量值\s*([+＋−\-－])\s*(\d{3,5})|"
    r"力量\s*([+＋−\-－])\s*(\d{3,5})",
    re.I,
)
ALL_OPP_BUFF_RE = re.compile(
    r"(?:give )?all of your opponent'?s Characters\s*([+＋−\-－])\s*(\d{3,5})\s*power|"
    r"對手的角色卡全數力量值\s*([+＋−\-－])\s*(\d{3,5})|"
    r"对手的角色卡全数力量值\s*([+＋−\-－])\s*(\d{3,5})",
    re.I,
)


def _signed_amount(sign: str, raw: str) -> int:
    n = int(raw)
    if sign in {"−", "－", "-"}:
        return -n
    return n


def _parse_counter_or_event_buffs(chunk: str) -> list[dict]:
    ops: list[dict] = []
    m_all = ALL_OPP_BUFF_RE.search(chunk)
    if m_all:
        sign = next(g for g in m_all.groups()[::2] if g)
        amt = _signed_amount(sign, next(g for g in m_all.groups()[1::2] if g))
        return [{"op": "buff", "amount": amt, "target_kind": "opponent_character", "optional": False, "all": True}]
    # Leader or Character gains +N
    m = re.search(
        r"Up to 1 of your Leader or Character cards gains\s*([+＋−\-－])\s*(\d{3,5})\s*power|"
        r"最多1張自己的領航卡或角色卡.{0,12}力量值\s*([+＋−\-－])\s*(\d{3,5})|"
        r"最多1张自己的领航卡或角色卡.{0,12}力量值\s*([+＋−\-－])\s*(\d{3,5})",
        chunk,
        re.I,
    )
    if m:
        sign = next(g for g in m.groups()[::2] if g)
        amt = _signed_amount(sign, next(g for g in m.groups()[1::2] if g))
        ops.append(
            {
                "op": "buff",
                "amount": amt,
                "target_kind": "own_leader_or_character",
                "optional": True,
            }
        )
    # Opponent character give -N
    m2 = re.search(
        r"(?:Give|give) up to\s*(\d+)\s*of your opponent'?s.{0,40}Characters?\s*([+＋−\-－])\s*(\d{3,5})\s*power|"
        r"最多\s*(\d+)\s*[張张]對手.{0,40}角色卡.{0,12}力量值\s*([+＋−\-－])\s*(\d{3,5})|"
        r"最多\s*(\d+)\s*[张張]对手.{0,40}角色卡.{0,12}力量值\s*([+＋−\-－])\s*(\d{3,5})",
        chunk,
        re.I,
    )
    if m2:
        groups = [g for g in m2.groups() if g]
        # count, sign, amount loosely
        if len(groups) >= 3:
            sign = groups[-2]
            amt = _signed_amount(sign, groups[-1])
            ops.append(
                {
                    "op": "buff",
                    "amount": amt,
                    "target_kind": "opponent_character",
                    "optional": True,
                }
            )
    if not ops:
        ops.extend(_parse_power_buff_amount(chunk))
    return ops


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
        "buff_fix": 0,
        "buff_add": 0,
        "cannot_ko": 0,
        "rest_opp": 0,
        "opp_hand_bottom": 0,
        "synth_ability": 0,
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

    for cid in targets:
        info = catalog.get(cid) or {}
        blob = effect_blob(info)
        merged = get_card_entry(cid)
        abilities = [dict(a) for a in (merged.get("abilities") or []) if isinstance(a, dict)]
        changed = False
        new_abs: list[dict] = []

        # Continuous cannot_be_ko / all-opp buff with no ability yet
        if not abilities:
            synth: list[dict] = []
            # on_play-less static text
            cko = _parse_cannot_be_ko_ops(blob)
            if cko:
                m = DON_X_RE.search(blob)
                ab: dict = {
                    "timing": "your_turn",
                    "summary": cko[0].get("summary") or "Cannot be K.O.'d",
                    "ops": cko,
                    "status": "compiled",
                    "confidence": 0.85,
                }
                if m:
                    ab["require_don_attached_gte"] = int(next(g for g in m.groups() if g))
                synth.append(ab)
            allb = ALL_OPP_BUFF_RE.search(blob)
            if allb:
                sign = next(g for g in allb.groups()[::2] if g)
                amt = _signed_amount(sign, next(g for g in allb.groups()[1::2] if g))
                synth.append(
                    {
                        "timing": "on_play",
                        "summary": f"Give all opponent Characters {amt:+d} power.",
                        "ops": [{"op": "buff", "amount": amt, "target_kind": "opponent_character", "optional": False, "all": True}],
                        "status": "compiled",
                        "confidence": 0.85,
                    }
                )
            if synth:
                for s in synth:
                    na = normalize_ability(s)
                    if na:
                        new_abs.append(na)
                changed = True
                stats["synth_ability"] += len(synth)
                abilities = []  # skip empty loop
            else:
                continue

        for a in abilities:
            a = dict(a)
            timing = str(a.get("timing") or "")
            chunk = _trim_cross_timing(_timing_chunk(blob, timing), timing) or ""
            ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

            # Fix existing buff amounts from chunk
            parsed_buffs = _parse_counter_or_event_buffs(chunk)
            if parsed_buffs:
                # Update matching polarity amounts
                for pb in parsed_buffs:
                    want = int(pb.get("amount") or 0)
                    updated = False
                    for o in ops:
                        if o.get("op") not in {"buff", "buff_self", "buff_all_own"}:
                            continue
                        cur = int(o.get("amount") or 0)
                        same_side = (cur >= 0 and want >= 0) or (cur < 0 and want < 0)
                        same_target = (
                            not pb.get("target_kind")
                            or o.get("target_kind") == pb.get("target_kind")
                            or (o.get("op") == "buff_self" and pb.get("op") == "buff_self")
                        )
                        if same_side and same_target and cur != want:
                            o["amount"] = want
                            if pb.get("target_kind") and o.get("op") == "buff":
                                o["target_kind"] = pb["target_kind"]
                            stats["buff_fix"] += 1
                            changed = True
                            updated = True
                            break
                    if not updated and not any(
                        o.get("op") in {"buff", "buff_self", "buff_all_own"} and int(o.get("amount") or 0) == want for o in ops
                    ):
                        # Empty ops or missing buff
                        if not any(o.get("op") in {"buff", "buff_self", "buff_all_own"} for o in ops) or timing in {
                            "when_attacking",
                            "counter_event",
                            "on_play",
                            "main_start",
                        }:
                            if not any(o.get("op") in {"buff", "buff_self"} and int(o.get("amount") or 0) == want for o in ops):
                                ops.append(pb)
                                stats["buff_add"] += 1
                                changed = True

            # cannot_be_ko on this timing / continuous clause in chunk
            for cko in _parse_cannot_be_ko_ops(chunk) or _parse_cannot_be_ko_ops(blob if timing in {"your_turn", "don_attached"} else ""):
                if not any(o.get("op") == "cannot_be_ko" for o in ops):
                    # Prefer synthesizing your_turn for continuous protection text
                    if timing in {"activate_main", "on_ko", "trigger"} and re.search(
                        r"This Character cannot be K\.?O|這張角色卡不會|这张角色卡不会", blob, re.I
                    ):
                        continue
                    ops.append(cko)
                    stats["cannot_ko"] += 1
                    changed = True

            # rest opponent
            for ro in _parse_rest_opponent_ops(chunk):
                if not any(o.get("op") == "rest_opponent_character" for o in ops):
                    ops.insert(0 if not any(o.get("as_cost") for o in ops[:1]) else 1, ro)
                    stats["rest_opp"] += 1
                    changed = True
                else:
                    for o in ops:
                        if o.get("op") != "rest_opponent_character":
                            continue
                        if int(o.get("count") or 1) != int(ro.get("count") or 1):
                            o["count"] = ro["count"]
                            stats["rest_opp"] += 1
                            changed = True
                        if ro.get("cost_lte") is not None and o.get("cost_lte") != ro.get("cost_lte"):
                            o["cost_lte"] = ro["cost_lte"]
                            stats["rest_opp"] += 1
                            changed = True

            # opponent hand to bottom
            for oh in _parse_opponent_hand_to_bottom_ops(chunk):
                if not any(o.get("op") == "opponent_hand_to_bottom" for o in ops):
                    ops.append(oh)
                    stats["opp_hand_bottom"] += 1
                    changed = True
                else:
                    for o in ops:
                        if o.get("op") == "opponent_hand_to_bottom" and int(o.get("count") or 1) != int(oh.get("count") or 1):
                            o["count"] = oh["count"]
                            stats["opp_hand_bottom"] += 1
                            changed = True

            a["ops"] = ops
            na = normalize_ability(a)
            if na:
                new_abs.append(na)

        # Synthesize your_turn cannot_be_ko if missing entirely
        if re.search(r"This Character cannot be K\.?O|這張角色卡不會|这张角色卡不会", blob, re.I):
            if not any(o.get("op") == "cannot_be_ko" for a in new_abs for o in (a.get("ops") or [])):
                cko = _parse_cannot_be_ko_ops(blob)
                if cko:
                    ab = {
                        "timing": "your_turn",
                        "summary": cko[0].get("summary") or "Cannot be K.O.'d",
                        "ops": cko,
                        "status": "compiled",
                        "confidence": 0.85,
                    }
                    m = DON_X_RE.search(blob)
                    # Only attach DON gate if DON!! xN immediately scopes the cannot-ko clause
                    if m and re.search(
                        r"\[DON!!\s*[xX×]\s*\d+\].{0,40}cannot be K\.?O|"
                        r"【咚‼?\s*[×xX]\s*\d+】.{0,40}不會遭到KO|【咚‼?\s*[×xX]\s*\d+】.{0,40}不会遭到KO",
                        blob,
                        re.I,
                    ):
                        ab["require_don_attached_gte"] = int(next(g for g in m.groups() if g))
                    na = normalize_ability(ab)
                    if na:
                        new_abs.insert(0, na)
                        stats["cannot_ko"] += 1
                        changed = True

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
