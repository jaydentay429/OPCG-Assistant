#!/usr/bin/env python3
"""Deterministic cluster repairs for semantic-issue cards.

Targets high-yield patterns from the semantic-review cluster:
  - bare KO / return / rest missing cost/power filters
  - DON!! field count ≤ opponent → require_don_field_deficit_gte=0
  - hand/life ≤ N gates
  - draw 2 + trash 1 missing trash_hand
  - play_from_hand missing from_zone=trash
  - buff amount 0
  - opp cost 0-or-N gate on draw

Usage:
  .venv/bin/python scripts/fix_semantic_clusters.py --dry-run
  .venv/bin/python scripts/fix_semantic_clusters.py
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

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability, normalize_card_entry  # noqa: E402
from battle.effects import (  # noqa: E402
    _apply_common_text_gates,
    _enrich_ops_with_target_filters,
    _extract_require_hand_lte_from_text,
    _extract_require_life_lte_from_text,
    _text_requires_don_field_lte_opponent,
    effect_blob,
)

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "cluster_fixed_ids.txt"
DRAW_TRASH = re.compile(
    r"(?:draw\s*2.{0,80}trash\s*1\s*card|抽2.{0,60}(?:將|将)?.{0,20}(?:廢棄|废弃)\s*1)",
    re.I,
)
AMT_RE = re.compile(
    r"(?:力量(?:值)?\s*([+\-−－]\s*\d{3,5})|([+\-−－]\s*\d{3,5})\s*(?:power|力量)|power\s*([+\-−－]\s*\d{3,5}))",
    re.I,
)


def _parse_amt(raw: str) -> int | None:
    s = (raw or "").replace("−", "-").replace("－", "-").strip()
    if s and s[0] not in "+-":
        s = "+" + s
    s = re.sub(r"[^\d\-]", "", s)
    if not s or s == "-":
        return None
    try:
        n = int(s)
    except ValueError:
        return None
    return n if n else None


def _diag_blob(rev: dict) -> str:
    parts = []
    for iss in rev.get("issues") or []:
        if not isinstance(iss, dict):
            continue
        parts.append(" ".join(str(iss.get(k) or "") for k in ("problem", "expected", "actual", "timing")))
    return "\n".join(parts)


def _ability_scope(ability: dict, blob: str, multi: bool) -> str:
    summary = str(ability.get("summary") or "").strip()
    if len(summary) >= 24:
        return summary
    if not multi:
        return blob
    return summary + "\n" + blob if summary else blob


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all-issue", action="store_true", help="Also scan non-issue cards (default: issue only)")
    args = ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    semantic = json.loads(SEM.read_text(encoding="utf-8")) if SEM.exists() else {"cards": {}}
    lib_path, _ = library_paths()
    raw = json.loads(lib_path.read_text(encoding="utf-8"))
    cards = raw.get("cards") or raw

    stats = {
        "ops_enriched": 0,
        "don_lte_gate": 0,
        "hand_lte_gate": 0,
        "life_lte_gate": 0,
        "trash_zone": 0,
        "trash_hand": 0,
        "buff_fixed": 0,
        "cards_touched": 0,
    }
    touched: list[str] = []

    for cid, rev in (semantic.get("cards") or {}).items():
        if not args.all_issue and rev.get("verdict") != "issue":
            continue
        entry = cards.get(cid)
        if not isinstance(entry, dict):
            continue
        abilities = [dict(a) for a in (entry.get("abilities") or []) if isinstance(a, dict)]
        if not abilities:
            continue
        blob = effect_blob(catalog.get(cid) or {})
        diag = _diag_blob(rev)
        multi = len(abilities) > 1
        changed = False

        new_abs: list[dict] = []
        for ability in abilities:
            scope = _ability_scope(ability, blob, multi)
            before_ops = json.dumps(ability.get("ops") or [], sort_keys=True, ensure_ascii=False)
            ops = _enrich_ops_with_target_filters(list(ability.get("ops") or []), scope)
            if multi and before_ops == json.dumps(ops, sort_keys=True, ensure_ascii=False):
                # Summary too thin — try full blob once for filter fill.
                ops = _enrich_ops_with_target_filters(ops, blob)
            if json.dumps(ops, sort_keys=True, ensure_ascii=False) != before_ops:
                stats["ops_enriched"] += 1
                changed = True

            # trash play
            for op in ops:
                if op.get("op") != "play_from_hand":
                    continue
                if str(op.get("from_zone") or "hand") == "trash":
                    continue
                if re.search(r"from your trash|從自己的廢棄區|从自己的废弃区", scope, re.I) or (
                    re.search(r"废弃区|廢棄區|from trash", diag, re.I)
                    and re.search(r"play_from_hand|登場|登场|play", diag, re.I)
                ):
                    op["from_zone"] = "trash"
                    stats["trash_zone"] += 1
                    changed = True

            # buff amount 0
            amts = [_parse_amt(next(g for g in m.groups() if g)) for m in AMT_RE.finditer(scope + "\n" + blob)]
            amts = [a for a in amts if a]
            for op in ops:
                if op.get("op") not in {"buff", "buff_self", "buff_all_own"}:
                    continue
                if int(op.get("amount") or 0) != 0:
                    continue
                amt = amts[0] if len(amts) == 1 else None
                if amt is None:
                    m = AMT_RE.search(diag)
                    if m:
                        amt = _parse_amt(next(g for g in m.groups() if g))
                if amt is None:
                    continue
                op["amount"] = max(-5000, min(5000, int(amt)))
                stats["buff_fixed"] += 1
                changed = True

            # draw 2 / trash 1
            if DRAW_TRASH.search(scope) or (not multi and DRAW_TRASH.search(blob)) or re.search(
                r"抽2.{0,20}廢棄1|draw 2.{0,20}trash 1|缺少.*trash_hand|漏.*弃1|漏.*棄1", diag, re.I
            ):
                if any(o.get("op") == "draw" for o in ops) and not any(o.get("op") == "trash_hand" for o in ops):
                    rebuilt: list[dict] = []
                    inserted = False
                    for o in ops:
                        rebuilt.append(o)
                        if not inserted and o.get("op") == "draw" and int(o.get("count") or 1) >= 2:
                            rebuilt.append({"op": "trash_hand", "count": 1, "optional": True})
                            inserted = True
                    if inserted:
                        ops = rebuilt
                        stats["trash_hand"] += 1
                        changed = True

            ability["ops"] = ops
            # Gates: prefer scope match; diagnosis can unlock blob-wide attach on single-ability cards.
            gate_chunk = scope
            if multi:
                if _text_requires_don_field_lte_opponent(scope) or _extract_require_hand_lte_from_text(scope) is not None or _extract_require_life_lte_from_text(scope) is not None:
                    gate_chunk = scope
                elif not str(ability.get("summary") or "").strip() and not multi:
                    gate_chunk = blob
                else:
                    gate_chunk = scope
            else:
                gate_chunk = blob if len(scope) < 24 else scope

            before_gates = {
                k: ability.get(k)
                for k in ("require_don_field_deficit_gte", "require_hand_lte", "require_life_lte")
            }
            gated = _apply_common_text_gates(ability, gate_chunk)
            # Diagnosis-backed gates when text attach missed on single-ability cards.
            if not multi:
                if re.search(r"咚.{0,12}≤|自己≤對手|equal to or less than the number", diag, re.I):
                    if gated.get("require_don_field_deficit_gte") is None and _text_requires_don_field_lte_opponent(blob):
                        gated["require_don_field_deficit_gte"] = 0
                if re.search(r"手牌\s*≤|手牌数≤|手牌在\d+|or less cards in your hand", diag, re.I):
                    n = _extract_require_hand_lte_from_text(blob)
                    if n is not None and gated.get("require_hand_lte") is None:
                        gated["require_hand_lte"] = n
                if re.search(r"生命\s*≤|生命值≤|or less Life", diag, re.I):
                    n = _extract_require_life_lte_from_text(blob)
                    if n is not None and gated.get("require_life_lte") is None:
                        gated["require_life_lte"] = n

            after_gates = {
                k: gated.get(k)
                for k in ("require_don_field_deficit_gte", "require_hand_lte", "require_life_lte")
            }
            if after_gates != before_gates:
                if before_gates.get("require_don_field_deficit_gte") != after_gates.get("require_don_field_deficit_gte"):
                    if after_gates.get("require_don_field_deficit_gte") is not None:
                        stats["don_lte_gate"] += 1
                if before_gates.get("require_hand_lte") != after_gates.get("require_hand_lte"):
                    if after_gates.get("require_hand_lte") is not None:
                        stats["hand_lte_gate"] += 1
                if before_gates.get("require_life_lte") != after_gates.get("require_life_lte"):
                    if after_gates.get("require_life_lte") is not None:
                        stats["life_lte_gate"] += 1
                changed = True
            ability = gated
            na = normalize_ability(ability)
            if na:
                new_abs.append(na)

        if not changed:
            continue
        cards[cid] = normalize_card_entry(cid, {"version": 1, "abilities": new_abs})
        stats["cards_touched"] += 1
        touched.append(cid)

    print(json.dumps(stats, ensure_ascii=False), flush=True)
    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    OUT_IDS.write_text("\n".join(touched) + ("\n" if touched else ""), encoding="utf-8")
    print(f"Wrote ids {OUT_IDS} ({len(touched)})", flush=True)
    if args.dry_run:
        return 0
    payload = {
        "version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cards": cards,
    }
    tmp = lib_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(lib_path)
    reload_effect_library(force=True)
    print(f"Wrote {lib_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
