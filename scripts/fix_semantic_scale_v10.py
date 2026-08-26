#!/usr/bin/env python3
"""Scaling buff_self, hand_to_deck, keyword/dedupe/rest_don fixes.

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
    _enrich_ops_with_target_filters,
    _parse_grant_keyword_ops,
    _parse_hand_to_deck_ops,
    effect_blob,
)
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "scale_v10_fixed_ids.txt"

SCALE_RE = re.compile(
    r"(?:gains?\s*\+?(\d{3,5})\s*power for every\s*(\d+)\s*(?:of your )?rested DON|"
    r"每有\s*(\d+)\s*[張张]休息狀態的咚.{0,40}力量值\+(\d{3,5})|"
    r"每有\s*(\d+)\s*[张张]休息状态的咚.{0,40}力量值\+(\d{3,5})|"
    r"gains?\s*\+?(\d{3,5})\s*power for every\s*(\d+)\s*Events? in your trash|"
    r"廢棄區中每有\s*(\d+)\s*[張张]事件.{0,40}力量值\+(\d{3,5})|"
    r"废弃区中每有\s*(\d+)\s*[张张]事件.{0,40}力量值\+(\d{3,5})|"
    r"gains?\s*\+?(\d{3,5})\s*power(?: and \+(\d+)\s*cost)? for every\s*(\d+)\s*cards? in your trash|"
    r"廢棄區中每有\s*(\d+)\s*[張张]卡片.{0,40}力量值\+(\d{3,5})|"
    r"废弃区中每有\s*(\d+)\s*[张张]卡片.{0,40}力量值\+(\d{3,5}))",
    re.I,
)
LEADER_NAME_RE = re.compile(
    r"If your Leader is \[([^\]]+)\]|若自己的領航卡是「([^」]+)」|若自己的领航卡是「([^」]+)」",
    re.I,
)
LEADER_TRAIT_RE = re.compile(
    r"If your Leader(?:'s type)? (?:has|includes?)\s*(?:the )?\{([^}]+)\}|"
    r"Leader'?s? type includes?\s*[\"']([^\"']+)[\"']|"
    r"若自己的領航卡擁有(?:包含)?[『「《]([^』」》]+)[』」》]|"
    r"若自己的领航卡拥有(?:包含)?[『「《]([^』」》]+)[』」》]",
    re.I,
)
REST_DON_RE = re.compile(
    r"(?:you may )?rest\s*(\d+)\s*of your don(?:‼|!!)?\s*cards?\s*:|"
    r"可[將将]\s*(\d+)\s*[張张]?自己的咚.{0,16}置[為为]休息\s*[：:]",
    re.I,
)


def _parse_scale(text: str) -> dict | None:
    # rested DON
    m = re.search(
        r"\+?\s*(\d{3,5})\s*power for every\s*(\d+)\s*(?:of your )?rested DON|"
        r"每有\s*(\d+)\s*[張张]休息狀態的咚.{0,60}力量值\+(\d{3,5})|"
        r"每有\s*(\d+)\s*[张张]休息状态的咚.{0,60}力量值\+(\d{3,5})",
        text,
        re.I,
    )
    if m:
        gs = [g for g in m.groups() if g]
        if m.group(1) and m.group(2):
            return {"amount": int(m.group(1)), "per_rested_don": int(m.group(2))}
        return {"amount": int(gs[1]), "per_rested_don": int(gs[0])}
    # trash events
    m = re.search(
        r"\+?\s*(\d{3,5})\s*power for every\s*(\d+)\s*Events? in your trash|"
        r"廢棄區中每有\s*(\d+)\s*[張张]事件.{0,60}力量值\+(\d{3,5})|"
        r"废弃区中每有\s*(\d+)\s*[张张]事件.{0,60}力量值\+(\d{3,5})",
        text,
        re.I,
    )
    if m:
        gs = [g for g in m.groups() if g]
        if m.group(1) and m.group(2):
            return {"amount": int(m.group(1)), "per_trash_events": int(m.group(2))}
        return {"amount": int(gs[1]), "per_trash_events": int(gs[0])}
    # trash cards (+ optional cost)
    m = re.search(
        r"\+?\s*(\d{3,5})\s*power(?: and \+(\d+)\s*cost)? for every\s*(\d+)\s*cards? in your trash|"
        r"廢棄區中每有\s*(\d+)\s*[張张]卡片.{0,80}力量值\+(\d{3,5})(?:.{0,40}費用\+(\d+))?|"
        r"废弃区中每有\s*(\d+)\s*[张张]卡片.{0,80}力量值\+(\d{3,5})(?:.{0,40}费用\+(\d+))?",
        text,
        re.I,
    )
    if m:
        if m.group(1) and m.group(3):
            out = {"amount": int(m.group(1)), "per_trash_cards": int(m.group(3))}
            if m.group(2):
                out["cost_amount"] = int(m.group(2))
            return out
        # ZH: step, power, optional cost
        step = m.group(4) or m.group(7)
        power = m.group(5) or m.group(8)
        cost = m.group(6) or m.group(9)
        if step and power:
            out = {"amount": int(power), "per_trash_cards": int(step)}
            if cost:
                out["cost_amount"] = int(cost)
            return out
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
        "scale": 0,
        "hand_to_deck": 0,
        "keyword": 0,
        "dedupe_buff": 0,
        "rest_don": 0,
        "leader_name": 0,
        "leader_trait": 0,
        "turn_static": 0,
        "cards_touched": 0,
    }
    touched: list[str] = []
    reload_effect_library(force=True)

    for cid, rev in (semantic.get("cards") or {}).items():
        if rev.get("verdict") != "issue":
            continue
        merged = get_card_entry(cid)
        abilities = [dict(a) for a in (merged.get("abilities") or []) if isinstance(a, dict)]
        blob = effect_blob(catalog.get(cid) or {})
        multi = len(abilities) > 1
        changed = False
        new_abs: list[dict] = []
        timings = {str(a.get("timing") or "") for a in abilities}

        # Inject missing your_turn scaling static if text has it and no your_turn ability
        scale_blob = _parse_scale(blob)
        if scale_blob and "your_turn" not in timings and re.search(
            r"\[Your Turn\]|【我方回合中】|for every|每有", blob, re.I
        ):
            ab: dict = {
                "timing": "your_turn",
                "summary": blob.split("\n")[0][:240],
                "ops": [{"op": "buff_self", "amount": scale_blob["amount"], **{k: v for k, v in scale_blob.items() if k.startswith("per_")}}],
                "status": "compiled",
                "confidence": 0.85,
            }
            if scale_blob.get("cost_amount"):
                ab["ops"].append(
                    {
                        "op": "grant_cost",
                        "amount": scale_blob["cost_amount"],
                        "target_kind": "self",
                        "per_trash_cards": scale_blob.get("per_trash_cards"),
                    }
                )
            m_don = re.search(r"\[DON!!\s*[xX×]\s*(\d+)\]|【咚‼?\s*[×xX]\s*(\d+)】", blob, re.I)
            if m_don:
                ab["require_don_attached_gte"] = int(next(g for g in m_don.groups() if g))
            m_lt = LEADER_TRAIT_RE.search(blob)
            if m_lt:
                ab["require_leader_trait"] = next(g for g in m_lt.groups() if g)
            abilities.insert(0, ab)
            timings.add("your_turn")
            stats["turn_static"] += 1
            changed = True

        for ability in abilities:
            timing = str(ability.get("timing") or "")
            chunk = _trim_cross_timing(_timing_chunk(blob, timing), timing)
            summary = _trim_cross_timing(str(ability.get("summary") or "").strip(), timing)
            if multi:
                scope = summary if len(summary) >= 12 else (chunk if chunk != blob else summary)
            else:
                scope = summary if len(summary) >= 18 else (chunk or blob)
            text = f"{scope}\n{chunk}" if chunk and chunk != blob else (scope or blob)
            ops = [dict(o) for o in (ability.get("ops") or [])]

            # scaling on existing buff_self / inject
            sc = _parse_scale(text) if timing in {"your_turn", "opponent_turn", "don_attached"} else None
            if sc:
                found = False
                for i, o in enumerate(ops):
                    if o.get("op") != "buff_self":
                        continue
                    o = dict(o)
                    o["amount"] = sc["amount"]
                    for k, v in sc.items():
                        if k.startswith("per_"):
                            o[k] = v
                    ops[i] = o
                    found = True
                    stats["scale"] += 1
                    changed = True
                    break
                if not found and timing in {"your_turn", "opponent_turn", "don_attached"}:
                    ops.append({"op": "buff_self", "amount": sc["amount"], **{k: v for k, v in sc.items() if k.startswith("per_")}})
                    stats["scale"] += 1
                    changed = True
                if sc.get("cost_amount") and not any(o.get("op") == "grant_cost" for o in ops):
                    ops.append(
                        {
                            "op": "grant_cost",
                            "amount": sc["cost_amount"],
                            "target_kind": "self",
                            "per_trash_cards": sc.get("per_trash_cards"),
                        }
                    )
                    changed = True

            # hand_to_deck
            for hop in _parse_hand_to_deck_ops(text):
                if any(o.get("op") == "hand_to_deck" for o in ops):
                    break
                ops.append(hop)
                stats["hand_to_deck"] += 1
                changed = True
                break

            # keywords
            for gop in _parse_grant_keyword_ops(text):
                kw = str(gop.get("keyword") or "")
                if any(o.get("op") == "grant_keyword" and str(o.get("keyword") or "") == kw for o in ops):
                    continue
                ops.append(gop)
                stats["keyword"] += 1
                changed = True

            # rest_don sync
            m_rd = REST_DON_RE.search(text)
            if m_rd:
                n = int(next(g for g in m_rd.groups() if g))
                if timing in {"activate_main", "main_start"} and int(ability.get("cost_don") or 0) != n:
                    ability["cost_don"] = n
                    changed = True
                rds = [i for i, o in enumerate(ops) if o.get("op") == "rest_don"]
                if not rds:
                    ops.insert(0, {"op": "rest_don", "count": n, "as_cost": True})
                    stats["rest_don"] += 1
                    changed = True
                else:
                    for i in rds:
                        if int(ops[i].get("count") or 0) != n:
                            o = dict(ops[i])
                            o["count"] = n
                            o["as_cost"] = True
                            ops[i] = o
                            stats["rest_don"] += 1
                            changed = True
                    # dedupe
                    keep = True
                    cleaned = []
                    for o in ops:
                        if o.get("op") == "rest_don":
                            if not keep:
                                changed = True
                                continue
                            keep = False
                        cleaned.append(o)
                    ops = cleaned

            # leader name / trait gates
            if not ability.get("require_leader_name"):
                m = LEADER_NAME_RE.search(text)
                if m:
                    ability["require_leader_name"] = next(g for g in m.groups() if g)[:60]
                    stats["leader_name"] += 1
                    changed = True
            if not ability.get("require_leader_trait"):
                m = LEADER_TRAIT_RE.search(text)
                if m:
                    ability["require_leader_trait"] = next(g for g in m.groups() if g)[:80]
                    stats["leader_trait"] += 1
                    changed = True

            # dedupe identical buff
            seen = set()
            deduped = []
            for o in ops:
                if o.get("op") == "buff":
                    key = (o.get("amount"), o.get("target_kind"), o.get("optional"))
                    if key in seen:
                        stats["dedupe_buff"] += 1
                        changed = True
                        continue
                    seen.add(key)
                deduped.append(o)
            ops = deduped

            ops = _enrich_ops_with_target_filters(ops, text)
            ability["ops"] = ops
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
