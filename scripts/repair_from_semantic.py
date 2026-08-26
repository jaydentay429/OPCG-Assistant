#!/usr/bin/env python3
"""Deterministic repairs driven by semantic-review diagnoses + text.

Fixes:
  1) buff/buff_self/buff_all_own amount==0 using diagnosis (+N) or text heuristics
  2) play_from_hand missing from_zone=trash when diagnosis says trash/废弃区
  3) drop obviously-extra set_character_active when diagnosis says paper has none

Usage:
  .venv/bin/python scripts/repair_from_semantic.py --dry-run
  .venv/bin/python scripts/repair_from_semantic.py
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
from battle.effects import effect_blob  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
AMT_RE = re.compile(r"([+\-−－])\s*(\d{3,5})")
AMT_BARE = re.compile(r"(?:应为|纸面为|未体现|expected|amount)\D{0,12}([+\-−－]?\s*\d{3,5})")


def _parse_amt(raw: str) -> int | None:
    s = (raw or "").replace("−", "-").replace("－", "-").replace("+", "").strip()
    s = re.sub(r"[^\d\-]", "", s)
    if not s or s == "-":
        return None
    try:
        n = int(s)
    except ValueError:
        return None
    # Diagnoses usually omit sign for "+2000" after stripping; keep negatives.
    if n == 0:
        return None
    # If original had no minus, treat as positive power delta.
    if "-" not in (raw or "") and n > 0:
        return n
    if "-" in (raw or ""):
        return -abs(n)
    return n


def _amounts_from_text(text: str) -> list[int]:
    out: list[int] = []
    for m in re.finditer(
        r"(?:力量(?:值)?\s*([+\-−－]\s*\d{3,5})|([+\-−－]\s*\d{3,5})\s*(?:power|力量)|power\s*([+\-−－]\s*\d{3,5}))",
        text or "",
        re.I,
    ):
        raw = next(g for g in m.groups() if g)
        n = _parse_amt(raw if raw.strip()[0] in "+-−－" else f"+{raw}")
        if n:
            out.append(n)
    return out


def _diag_amount(issue: dict) -> int | None:
    blob = " ".join(str(issue.get(k) or "") for k in ("problem", "expected", "actual"))
    # Prefer explicit +/- in Chinese diagnoses.
    for m in AMT_RE.finditer(blob):
        n = _parse_amt(m.group(0))
        if n:
            return n
    m2 = AMT_BARE.search(blob)
    if m2:
        n = _parse_amt(m2.group(1) if m2.group(1).strip()[0:1] in "+-−－" else f"+{m2.group(1)}")
        if n:
            return n
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    semantic = json.loads(SEM.read_text(encoding="utf-8")) if SEM.exists() else {"cards": {}}
    lib_path, _ = library_paths()
    raw = json.loads(lib_path.read_text(encoding="utf-8"))
    cards = raw.get("cards") or raw

    stats = {
        "buff_fixed": 0,
        "trash_zone_fixed": 0,
        "extra_active_dropped": 0,
        "cards_touched": 0,
    }

    for cid, rev in (semantic.get("cards") or {}).items():
        if rev.get("verdict") != "issue":
            continue
        entry = cards.get(cid)
        if not isinstance(entry, dict):
            continue
        abilities = list(entry.get("abilities") or [])
        if not abilities:
            continue
        blob = effect_blob(catalog.get(cid) or {})
        text_amts = _amounts_from_text(blob)
        by_t = {a.get("timing"): dict(a) for a in abilities if a.get("timing")}
        changed = False
        issues = [i for i in (rev.get("issues") or []) if isinstance(i, dict)]

        for iss in issues:
            timing = iss.get("timing")
            problem = str(iss.get("problem") or "")
            expected = str(iss.get("expected") or "")
            text = problem + " " + expected

            # 1) buff amount 0
            if re.search(r"amount\s*为\s*0|增益数值|未体现\s*\+|力量值加成|buff_self|buff ", text, re.I):
                amt = _diag_amount(iss)
                if amt is None and len(text_amts) == 1:
                    amt = text_amts[0]
                if amt is not None:
                    targets = []
                    if timing and timing in by_t:
                        targets = [by_t[timing]]
                    else:
                        targets = list(by_t.values())
                    for a in targets:
                        for op in a.get("ops") or []:
                            if op.get("op") not in {"buff", "buff_self", "buff_all_own"}:
                                continue
                            if int(op.get("amount") or 0) != 0:
                                continue
                            # Prefer sign: opponent debuffs often negative in diagnosis.
                            if "−" in text or "－" in text or "-" in text and "对手" in text:
                                if amt > 0 and re.search(r"对手|opponent|\-", text):
                                    # keep diagnosis sign if present
                                    if re.search(r"[−－\-]\s*\d{3,5}", text):
                                        amt = -abs(amt)
                            op["amount"] = max(-5000, min(5000, int(amt)))
                            changed = True
                            stats["buff_fixed"] += 1

            # 2) play from trash
            if re.search(r"废弃区|廢棄區|from trash|play_from_hand.{0,20}手牌", text, re.I):
                if re.search(r"废弃|廢棄|trash", text, re.I):
                    targets = [by_t[timing]] if timing in by_t else list(by_t.values())
                    for a in targets:
                        for op in a.get("ops") or []:
                            if op.get("op") != "play_from_hand":
                                continue
                            if str(op.get("from_zone") or "hand") == "trash":
                                continue
                            op["from_zone"] = "trash"
                            changed = True
                            stats["trash_zone_fixed"] += 1

            # 3) extra set_character_active
            if re.search(r"多出\s*set_character_active|纸面无此.*set_character_active|无 set_character_active", text, re.I):
                targets = [by_t[timing]] if timing in by_t else list(by_t.values())
                for a in targets:
                    before = list(a.get("ops") or [])
                    after = [o for o in before if o.get("op") != "set_character_active"]
                    if len(after) < len(before):
                        a["ops"] = after
                        changed = True
                        stats["extra_active_dropped"] += len(before) - len(after)

        # Heuristic: any remaining zero buffs with a single text amount
        if len(text_amts) == 1:
            for a in by_t.values():
                for op in a.get("ops") or []:
                    if op.get("op") in {"buff", "buff_self", "buff_all_own"} and int(op.get("amount") or 0) == 0:
                        op["amount"] = text_amts[0]
                        changed = True
                        stats["buff_fixed"] += 1

        if not changed:
            continue
        new_abs = []
        for a in by_t.values():
            na = normalize_ability(a)
            if na:
                new_abs.append(na)
        cards[cid] = normalize_card_entry(cid, {"version": 1, "abilities": new_abs})
        stats["cards_touched"] += 1

    print(json.dumps(stats, ensure_ascii=False), flush=True)
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
