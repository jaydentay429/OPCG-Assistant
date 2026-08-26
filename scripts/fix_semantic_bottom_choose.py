#!/usr/bin/env python3
"""Fix deck-bottom / choose_target / kw / life / gain_don / once clusters.

Writes library + overrides.

Usage:
  .venv/bin/python scripts/fix_semantic_bottom_choose.py --dry-run
  .venv/bin/python scripts/fix_semantic_bottom_choose.py
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
    _parse_life_zone_ops,
    _parse_place_on_bottom_ops,
    effect_blob,
)

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "bottom_choose_fixed_ids.txt"

ONCE_RE = re.compile(r"\[Once Per Turn\]|【每回合1次】|【每回合一次】", re.I)
GAIN_DON_RE = re.compile(
    r"(?:add|gain)\s+up to\s+(\d+)\s+DON!!|"
    r"從(?:自己的)?咚‼?卡組追加(?:最多)?\s*(\d+)|"
    r"从(?:自己的)?咚‼?卡组追加(?:最多)?\s*(\d+)",
    re.I,
)
LIFE_GTE_RE = re.compile(r"(\d+)\s+or more Life|生命值卡在\s*(\d+)\s*[張张]以上", re.I)


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
        "end_of_your_turn": r"(?:\[end of your turn\]|【我方的?回合結束時】|【我方的?回合结束时】)",
        "your_turn": r"(?:\[your turn\]|【我方回合中】)",
    }
    pat = patterns.get(t)
    if not pat:
        return blob
    m = re.search(pat, blob, re.I)
    if not m:
        return blob
    rest = blob[m.end() :]
    stop = re.search(
        r"(?=\[(?:on play|when attacking|activate|on\s*k\.?o\.?|trigger|counter|main|don!!|"
        r"your turn|end of|on your opponent'?s attack|opponent'?s turn)\]|【)",
        rest,
        re.I,
    )
    end = m.end() + (stop.start() if stop else min(len(rest), 520))
    return blob[m.start() : end]


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
        "bottom": 0,
        "choose_ko": 0,
        "kw": 0,
        "life": 0,
        "gain_don": 0,
        "once": 0,
        "life_gate": 0,
        "play_on_ko": 0,
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
            chunk = _timing_chunk(blob, timing)
            summary = str(ability.get("summary") or "").strip()
            scope = summary if len(summary) >= 24 else (chunk if multi else blob)
            if len(scope) < 20:
                scope = chunk or blob
            ops = [dict(o) for o in (ability.get("ops") or [])]

            # once
            if ONCE_RE.search(scope) or ONCE_RE.search(chunk):
                if not ability.get("once"):
                    ability["once"] = True
                    stats["once"] += 1
                    changed = True

            # fix life_gte/lte conflict: "N or more" should only set gte
            m_lge = LIFE_GTE_RE.search(scope) or LIFE_GTE_RE.search(chunk)
            if m_lge:
                n = int(next(g for g in m_lge.groups() if g))
                if ability.get("require_life_lte") == n and ability.get("require_life_gte") == n:
                    del ability["require_life_lte"]
                    ability["require_life_gte"] = n
                    stats["life_gate"] += 1
                    changed = True
                elif ability.get("require_life_gte") is None and re.search(r"以上|or more", scope + chunk, re.I):
                    ability["require_life_gte"] = n
                    if ability.get("require_life_lte") == n:
                        del ability["require_life_lte"]
                    stats["life_gate"] += 1
                    changed = True

            # place on bottom
            if not any(o.get("op") in {"return_to_bottom", "hand_to_deck"} for o in ops):
                bottoms = _parse_place_on_bottom_ops(scope) or _parse_place_on_bottom_ops(chunk)
                if bottoms:
                    ops.extend(bottoms)
                    stats["bottom"] += 1
                    changed = True

            # choose_target → ko
            rebuilt = []
            for o in ops:
                if o.get("op") == "choose_target" and not o.get("then_op"):
                    ko = _parse_ko_op(scope) or _parse_ko_op(chunk)
                    if ko and re.search(r"K\.?O|KO", scope, re.I):
                        rebuilt.append(ko)
                        stats["choose_ko"] += 1
                        changed = True
                        continue
                rebuilt.append(o)
            ops = rebuilt

            # grant keywords
            have_kw = {str(o.get("keyword") or "").lower() for o in ops if o.get("op") == "grant_keyword"}
            for g in _parse_grant_keyword_ops(scope) or _parse_grant_keyword_ops(chunk):
                kw = str(g.get("keyword") or "").lower()
                if kw and kw not in have_kw:
                    ops.append(g)
                    have_kw.add(kw)
                    stats["kw"] += 1
                    changed = True

            # life zone ops (only when this timing chunk mentions Life)
            if re.search(r"\bLife\b|生命值", scope + "\n" + chunk, re.I):
                if not any(o.get("op") in {"life_to_hand", "flip_life", "trash_life", "add_life"} for o in ops):
                    life_ops = _parse_life_zone_ops(scope) or _parse_life_zone_ops(chunk)
                    if life_ops:
                        costish = [o for o in life_ops if o.get("as_cost")]
                        rest = [o for o in life_ops if not o.get("as_cost")]
                        ops = [*costish, *ops, *rest] if costish else [*ops, *rest]
                        stats["life"] += 1
                        changed = True

            # gain_don (cost area), not attach
            if not any(o.get("op") == "gain_don" for o in ops) and not re.search(r"附加|attach", scope, re.I):
                m_g = GAIN_DON_RE.search(scope) or GAIN_DON_RE.search(chunk)
                if m_g and re.search(r"set it as active|置為活動|置为活动|追加", scope + chunk, re.I):
                    n = int(next(g for g in m_g.groups() if g))
                    ops.append({"op": "gain_don", "count": max(1, min(5, n))})
                    stats["gain_don"] += 1
                    changed = True

            # OP14-120 style: on_ko trash hand + play self from trash
            if timing == "on_ko" and re.search(
                r"play this Character card from your trash|從廢棄區中登場|从废弃区中登场|使這張角色卡從廢棄區|使这张角色卡从废弃区",
                scope + chunk,
                re.I,
            ):
                if not any(o.get("op") == "play_from_hand" for o in ops):
                    if not any(o.get("op") == "trash_hand" for o in ops):
                        ops.append({"op": "trash_hand", "count": 1, "optional": True, "as_cost": True})
                    ops.append(
                        {
                            "op": "play_from_hand",
                            "count": 1,
                            "from_zone": "trash",
                            "self_card": True,
                            "optional": False,
                            "summary": "Play this Character from trash",
                        }
                    )
                    stats["play_on_ko"] += 1
                    changed = True

            # Remove misplaced self-from-trash play on non-on_ko if on_ko exists
            if timing != "on_ko" and multi and any(a.get("timing") == "on_ko" for a in abilities):
                before = len(ops)
                ops = [
                    o
                    for o in ops
                    if not (
                        o.get("op") == "play_from_hand"
                        and o.get("self_card")
                        and str(o.get("from_zone") or "") == "trash"
                    )
                ]
                if len(ops) < before:
                    changed = True

            ops = _enrich_ops_with_target_filters(ops, scope)
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
