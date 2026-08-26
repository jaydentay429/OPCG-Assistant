#!/usr/bin/env python3
"""Keywords/trigger/gates v22: multicolor, buff_all, empty triggers, KO-all, opp DON.

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
from battle.effect_schema import normalize_ability, normalize_card_entry, sanitize_op  # noqa: E402
from battle.effects import (  # noqa: E402
    _chunk_has_leader_multicolor,
    _parse_activate_timing_ops,
    _parse_buff_all_own_ops,
    _parse_gain_don_ops,
    _parse_grant_keyword_ops,
    _parse_leader_or_char_buff,
    _parse_opp_return_don_ops,
    _parse_play_from_hand,
    _parse_play_from_zone,
    _parse_return_char_to_hand_ops,
    effect_blob,
    parse_trigger_ops,
)
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "keywords_trigger_v22_fixed_ids.txt"

KO_ALL_EXCEPT_SELF = re.compile(
    r"K\.?O\.?\s*all Characters other than this Character|"
    r"除了這張角色卡以外[，,]?KO全數|除了这张角色卡以外[，,]?KO全数|"
    r"KO全數的角色卡|KO全数的角色卡",
    re.I,
)
PRINTED_BLOCKER = re.compile(
    r"^\[Blocker\]|【防禦】|【防御】",
    re.I,
)
GAIN_BLOCKER = re.compile(
    r"gains? \[Blocker\]|獲得【防禦】|获得【防御】",
    re.I,
)


def _fill_trigger_ops(chunk: str, info: dict[str, Any]) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    for o in _parse_activate_timing_ops(chunk):
        ops.append(o)
    for o in _parse_gain_don_ops(chunk):
        ops.append(o)
    for o in _parse_opp_return_don_ops(chunk):
        ops.append(o)
    for o in _parse_return_char_to_hand_ops(chunk):
        ops.append(o)
    buff = _parse_leader_or_char_buff(chunk)
    if buff:
        ops.append(buff)
    play = _parse_play_from_hand(chunk) or _parse_play_from_zone(chunk)
    if play:
        ops.append(play)
    m_ot = re.search(
        r"(?:your )?opponent trashes?\s*(\d+)|對手廢棄\s*(\d+)|对手废弃\s*(\d+)",
        chunk,
        re.I,
    )
    if m_ot:
        ops.append(
            {
                "op": "trash_hand",
                "count": int(next(g for g in m_ot.groups() if g)),
                "optional": False,
                "owner": "opponent",
            }
        )
    # Fallback to card-level trigger parser when chunk alone is thin.
    if not ops:
        for o in parse_trigger_ops(info):
            ops.append(o)
    # Dedup by op+key fields
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for o in ops:
        so = sanitize_op(o)
        if not so:
            continue
        key = json.dumps(so, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        out.append(so)
    return out


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
        "multicolor": 0,
        "grant_blocker_move": 0,
        "buff_all": 0,
        "empty_trigger": 0,
        "activate_timing": 0,
        "ko_all": 0,
        "opp_return_don": 0,
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
        if not abilities and not (
            _chunk_has_leader_multicolor(blob) and GAIN_BLOCKER.search(blob)
        ):
            continue
        changed = False
        new_abs: list[dict[str, Any]] = []
        multi = len(abilities) > 1
        by_timing = {str(a.get("timing") or ""): dict(a) for a in abilities if a.get("timing")}

        # Continuous multicolor Blocker: move off on_play onto your_turn
        if _chunk_has_leader_multicolor(blob) and GAIN_BLOCKER.search(blob):
            # Strip grant_keyword blocker from on_play if paper grants continuously
            for t in list(by_timing.keys()):
                a = by_timing[t]
                ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]
                chunk = _trim_cross_timing(_timing_chunk(blob, t), t) or ""
                if t == "on_play" and any(o.get("op") == "grant_keyword" and o.get("keyword") == "blocker" for o in ops):
                    if not GAIN_BLOCKER.search(chunk):
                        ops = [
                            o
                            for o in ops
                            if not (o.get("op") == "grant_keyword" and o.get("keyword") == "blocker")
                        ]
                        a["ops"] = ops
                        by_timing[t] = a
                        changed = True
                        stats["grant_blocker_move"] += 1
            yt = dict(
                by_timing.get("your_turn")
                or {
                    "timing": "your_turn",
                    "ops": [],
                    "status": "compiled",
                    "confidence": 0.9,
                    "summary": "If Leader is multicolored, gains [Blocker]",
                }
            )
            yops = [dict(o) for o in (yt.get("ops") or []) if isinstance(o, dict)]
            if not any(o.get("op") == "grant_keyword" and o.get("keyword") == "blocker" for o in yops):
                yops.append(
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    }
                )
                changed = True
                stats["grant_blocker_move"] += 1
            if not yt.get("require_leader_multicolor"):
                yt["require_leader_multicolor"] = True
                changed = True
                stats["multicolor"] += 1
            yt["ops"] = yops
            by_timing["your_turn"] = yt

        for timing, a in list(by_timing.items()):
            a = dict(a)
            chunk = _trim_cross_timing(_timing_chunk(blob, timing), timing) or ""
            if multi and (not chunk or chunk == blob):
                chunk = _trim_cross_timing(str(a.get("summary") or ""), timing) or chunk
            ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

            # Multicolor gate on this ability when chunk mentions it (EN/primary clause only;
            # avoid Chinese continuous bleed after English On Play body).
            chunk_gate = re.split(r"[\n]|若自己的|【", chunk)[0]
            if _chunk_has_leader_multicolor(chunk_gate) and not a.get("require_leader_multicolor"):
                a["require_leader_multicolor"] = True
                changed = True
                stats["multicolor"] += 1
            elif (
                timing == "trigger"
                and _chunk_has_leader_multicolor(chunk)
                and not a.get("require_leader_multicolor")
            ):
                a["require_leader_multicolor"] = True
                changed = True
                stats["multicolor"] += 1

            # Fill empty / wrong activate_timing on trigger
            if timing == "trigger":
                need_fill = not ops or (
                    len(ops) == 1
                    and ops[0].get("op") == "activate_timing"
                    and ops[0].get("timing") == "on_ko"
                    and re.search(r"\[Main\]|【主要】", chunk, re.I)
                )
                if need_fill:
                    filled = _fill_trigger_ops(chunk, info)
                    if filled:
                        # Prefer activate_timing from filled if present
                        ops = filled
                        changed = True
                        stats["empty_trigger"] += 1
                # Fix wrong activate_timing target
                for o in ops:
                    if o.get("op") == "activate_timing":
                        want = _parse_activate_timing_ops(chunk)
                        if want and want[0].get("timing") != o.get("timing"):
                            o["timing"] = want[0]["timing"]
                            o["summary"] = want[0].get("summary") or o.get("summary")
                            changed = True
                            stats["activate_timing"] += 1

            # buff_all_own replace wrong buff_self
            ba = _parse_buff_all_own_ops(chunk)
            if ba:
                if any(o.get("op") == "buff_self" for o in ops) and not any(
                    o.get("op") == "buff_all_own" for o in ops
                ):
                    ops = [o for o in ops if o.get("op") != "buff_self"] + ba
                    changed = True
                    stats["buff_all"] += 1
                elif not any(o.get("op") == "buff_all_own" for o in ops) and re.search(
                    r"all of your|角色卡全數|角色卡全数", chunk, re.I
                ):
                    ops.extend(ba)
                    changed = True
                    stats["buff_all"] += 1
                else:
                    for o in ops:
                        if o.get("op") != "buff_all_own":
                            continue
                        want = ba[0]
                        for k in ("amount", "trait_contains", "exclude_self", "include_leader"):
                            if want.get(k) is not None and o.get(k) != want.get(k):
                                o[k] = want[k]
                                changed = True
                                stats["buff_all"] += 1

            # KO all except self
            if KO_ALL_EXCEPT_SELF.search(chunk):
                hit = False
                for o in ops:
                    if o.get("op") == "ko":
                        o["all"] = True
                        o["exclude_self"] = True
                        o["optional"] = False
                        o["target_kind"] = "any_character"
                        hit = True
                        changed = True
                        stats["ko_all"] += 1
                if not hit:
                    ops.append(
                        {
                            "op": "ko",
                            "all": True,
                            "exclude_self": True,
                            "optional": False,
                            "target_kind": "any_character",
                        }
                    )
                    changed = True
                    stats["ko_all"] += 1

            # Opponent return DON
            opp_don = _parse_opp_return_don_ops(chunk)
            if opp_don:
                for want in opp_don:
                    if not any(
                        o.get("op") == "return_don"
                        and o.get("owner") == "opponent"
                        and int(o.get("count") or 0) == int(want.get("count") or 0)
                        for o in ops
                    ):
                        # Don't confuse with own cost return_don
                        ops.append(want)
                        changed = True
                        stats["opp_return_don"] += 1
                # Also inject don field gate when text has it
                m_gate = re.search(
                    r"opponent has\s*(\d+)\s*or more DON|對手場上有\s*(\d+)\s*[張张]?以上|对手场上有\s*(\d+)\s*[张張]?以上",
                    chunk,
                    re.I,
                )
                if m_gate and a.get("require_don_field_gte") is None:
                    # Gate is on opponent field — store as require note via summary only if no schema;
                    # prefer require_don_field_gte on ability when engine supports opponent check.
                    pass

            a["ops"] = [sanitize_op(o) for o in ops if sanitize_op(o)]
            na = normalize_ability(a)
            if na:
                by_timing[timing] = na

        # Rebuild ability list
        for timing, a in by_timing.items():
            na = normalize_ability(a)
            if na and (na.get("ops") or na.get("status") == "verified"):
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
