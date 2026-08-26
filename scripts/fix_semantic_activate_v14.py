#!/usr/bin/env python3
"""Fix rest_don counts, rest_self, attach/gain_don counts, DON-gate bleed, keywords.

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
    _parse_active_don_ops,
    _parse_grant_keyword_ops,
    _parse_set_active_ops,
    effect_blob,
)
from fix_semantic_gates_v2 import DON_X_RE, REST_SELF_RE, _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "activate_v14_fixed_ids.txt"

CIRCLED = {
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
REST_DON_RE = re.compile(
    r"(?:you may )?rest\s*(\d+)\s*of your don(?:‼|!!)?\s*cards?\s*:|"
    r"可[將将]\s*(\d+)\s*[張张]?自己的咚.{0,16}置[為为]休息\s*[：:]|"
    r"[將将]\s*(\d+)\s*[張张]?自己的咚.{0,16}置[為为]休息\s*[：:]",
    re.I,
)
ATTACH_DON_RE = re.compile(
    r"(?:give|attach).{0,60}up to\s*(\d+)\s*(?:rested )?DON|"
    r"附加最多\s*(\d+)\s*[張张].{0,20}咚|"
    r"Give this Character up to\s*(\d+)\s*rested DON",
    re.I,
)
GAIN_DON_RE = re.compile(
    r"add up to\s*(\d+)\s*DON(?:‼|!!)\s*cards? from your DON|"
    r"追加最多\s*(\d+)\s*[張张].{0,12}咚|"
    r"從咚‼?卡組追加最多\s*(\d+)|从咚‼?卡组追加最多\s*(\d+)",
    re.I,
)
KO_TEXT_RE = re.compile(r"\bK\.?O\.?\b|淘汰|KO全數|KO全数", re.I)


def _circled_cost(text: str) -> int | None:
    for sym, n in CIRCLED.items():
        if sym in text:
            return n
    m = REST_DON_RE.search(text)
    if m:
        return int(next(g for g in m.groups() if g))
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
        "rest_don": 0,
        "rest_self": 0,
        "attach_don": 0,
        "gain_don": 0,
        "don_gate_fix": 0,
        "set_active": 0,
        "active_don": 0,
        "keyword": 0,
        "drop_extra_ko": 0,
        "synth_rush": 0,
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

            # 1) rest_don / cost_don from circled number in this timing
            n_cost = _circled_cost(chunk)
            if n_cost:
                a["cost_don"] = n_cost
                found = False
                for o in ops:
                    if o.get("op") == "rest_don":
                        if int(o.get("count") or 0) != n_cost or not o.get("as_cost"):
                            o["count"] = n_cost
                            o["as_cost"] = True
                            stats["rest_don"] += 1
                            changed = True
                        found = True
                        break
                if not found:
                    ops.insert(0, {"op": "rest_don", "count": n_cost, "as_cost": True})
                    stats["rest_don"] += 1
                    changed = True

            # 2) rest_self
            if REST_SELF_RE.search(chunk) and not a.get("rest_self"):
                a["rest_self"] = True
                stats["rest_self"] += 1
                changed = True
            if a.get("rest_self") or REST_SELF_RE.search(chunk):
                # Fix rest_character wrongly targeting opponent when "rest this Character"
                for o in ops:
                    if o.get("op") == "rest_character" and "opponent" in str(o.get("target_kind") or ""):
                        o["target_kind"] = "self"
                        stats["rest_self"] += 1
                        changed = True

            # 3) attach_don count
            m_att = ATTACH_DON_RE.search(chunk)
            if m_att:
                n = int(next(g for g in m_att.groups() if g))
                if any(o.get("op") == "attach_don" for o in ops):
                    for o in ops:
                        if o.get("op") == "attach_don" and int(o.get("count") or 0) != n:
                            o["count"] = n
                            o["optional"] = True
                            stats["attach_don"] += 1
                            changed = True
                else:
                    ops.append({"op": "attach_don", "count": n, "target_kind": "self", "optional": True})
                    stats["attach_don"] += 1
                    changed = True

            # 4) gain_don count
            m_gain = GAIN_DON_RE.search(chunk)
            if m_gain:
                n = int(next(g for g in m_gain.groups() if g))
                for o in ops:
                    if o.get("op") == "gain_don" and int(o.get("count") or 0) != n:
                        o["count"] = n
                        stats["gain_don"] += 1
                        changed = True

            # 5) DON!! xN gate: only keep if present in this timing's gate_scope
            m_don = DON_X_RE.search(chunk)
            if m_don:
                n = int(next(g for g in m_don.groups() if g))
                if int(a.get("require_don_attached_gte") or 0) != n:
                    a["require_don_attached_gte"] = n
                    stats["don_gate_fix"] += 1
                    changed = True
            elif a.get("require_don_attached_gte") is not None:
                # Strip bled gates (DON belongs to another timing / continuous clause)
                a.pop("require_don_attached_gte", None)
                stats["don_gate_fix"] += 1
                changed = True

            # 6) set_character_active / active_don
            for sa in _parse_set_active_ops(chunk):
                if not any(o.get("op") == "set_character_active" for o in ops):
                    ops.append(sa)
                    stats["set_active"] += 1
                    changed = True
            try:
                ad = _parse_active_don_ops(chunk)
            except Exception:
                ad = []
            if ad and not any(o.get("op") == "active_don" for o in ops):
                ops.extend(ad)
                stats["active_don"] += 1
                changed = True
            elif ad:
                for o in ops:
                    if o.get("op") == "active_don":
                        want = int(ad[0].get("count") or 1)
                        if int(o.get("count") or 0) != want:
                            o["count"] = want
                            stats["active_don"] += 1
                            changed = True

            # 7) grant_keyword from chunk
            kws = _parse_grant_keyword_ops(chunk)
            for kw in kws:
                if not any(o.get("op") == "grant_keyword" and o.get("keyword") == kw.get("keyword") for o in ops):
                    # Avoid putting continuous rush onto event timings unless chunk itself grants it
                    if timing in {"on_ko", "on_play", "trigger"} and kw.get("keyword") == "rush":
                        if not re.search(r"gains? \[Rush\]|獲得【速攻】|获得【速攻】", chunk, re.I):
                            continue
                    ops.append(kw)
                    stats["keyword"] += 1
                    changed = True

            # 8) Drop KO ops when this timing text has no KO
            if any(o.get("op") == "ko" for o in ops) and not KO_TEXT_RE.search(chunk):
                ops = [o for o in ops if o.get("op") != "ko"]
                stats["drop_extra_ko"] += 1
                changed = True

            a["ops"] = ops
            na = normalize_ability(a)
            if na:
                new_abs.append(na)

        # 9) Synthesize continuous rush under DON!! xN when missing
        if re.search(
            r"\[DON!!\s*[xX×]\s*\d+\]\s*This Character gains \[Rush\]|"
            r"【咚‼?\s*[×xX]\s*\d+】這張角色卡獲得【速攻】|"
            r"【咚‼?\s*[×xX]\s*\d+】这张角色卡获得【速攻】",
            blob,
            re.I,
        ):
            has_rush = any(
                o.get("op") == "grant_keyword" and o.get("keyword") == "rush"
                for a in new_abs
                for o in (a.get("ops") or [])
            )
            if not has_rush:
                m = DON_X_RE.search(blob)
                n = int(next(g for g in m.groups() if g)) if m else 1
                syn = normalize_ability(
                    {
                        "timing": "your_turn",
                        "summary": f"[DON!! x{n}] This Character gains [Rush].",
                        "ops": [{"op": "grant_keyword", "keyword": "rush", "target_kind": "self", "duration": "permanent"}],
                        "require_don_attached_gte": n,
                        "status": "compiled",
                        "confidence": 0.9,
                    }
                )
                if syn:
                    new_abs.insert(0, syn)
                    stats["synth_rush"] += 1
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
