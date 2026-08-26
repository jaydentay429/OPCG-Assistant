#!/usr/bin/env python3
"""High-yield target_kind / place_on_life / junk choose_target cleanup.

Writes library + overrides.

Usage:
  .venv/bin/python scripts/fix_semantic_targets_v2.py --dry-run
  .venv/bin/python scripts/fix_semantic_targets_v2.py
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
    _parse_ko_op,
    effect_blob,
)

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "targets_v2_fixed_ids.txt"

AMT_RE = re.compile(
    r"(?:gains?|give|gets?|力量值)\s*([+\-−－＋]\s*\d{3,5})|"
    r"([+\-−－＋]\s*\d{3,5})\s*(?:power|力量)",
    re.I,
)
LIFE_PLACE_RE = re.compile(
    r"(?:place|add) up to\s*(\d+)\s+(?:of )?your opponent'?s Characters?.{0,120}"
    r"(?:top or bottom|top|bottom) of (your opponent'?s|your) Life|"
    r"(?:將|将)最多\s*(\d+)\s*[張张].{0,12}(?:對手|对手).{0,30}角色卡.{0,80}"
    r"(?:以正面朝上)?(?:放置在|加入)(?:持有者的|對手的|对手的|自己的)?生命值",
    re.I,
)
LEADER_OR_CHAR_RE = re.compile(
    r"Leader or Character|領航卡或角色卡|领航卡或角色卡|領袖卡或角色卡|领袖卡或角色卡",
    re.I,
)


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
        "on_block": r"(?:\[on block\]|【阻擋時】|【阻挡时】)",
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
        r"your turn|end of|on your opponent'?s attack|on block|opponent'?s turn)\]|【)",
        rest,
        re.I,
    )
    end = m.end() + (stop.start() if stop else min(len(rest), 520))
    return blob[m.start() : end]


def _parse_amt(raw: str) -> int | None:
    s = (raw or "").replace("−", "-").replace("－", "-").replace("＋", "+").strip()
    s = re.sub(r"[^\d+\-]", "", s)
    if not s or s in {"+", "-"}:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _loc_target_kind(scope: str, amount: int | None = None) -> str | None:
    if not LEADER_OR_CHAR_RE.search(scope):
        return None
    opp = bool(re.search(r"opponent'?s|對手|对手", scope, re.I))
    own = bool(re.search(r"\byour\b|自己的|我方", scope, re.I))
    if amount is not None:
        if amount < 0:
            return "opponent_leader_or_character"
        if amount > 0:
            return "own_leader_or_character"
    if opp and not own:
        return "opponent_leader_or_character"
    if own and not opp:
        return "own_leader_or_character"
    # both or neither — prefer side implied by give/gains
    if re.search(r"give .{0,40}opponent|對手的|对手的", scope, re.I):
        return "opponent_leader_or_character"
    return "own_leader_or_character"


def _life_place_op(scope: str) -> dict | None:
    m = LIFE_PLACE_RE.search(scope)
    if not m:
        return None
    n = next((g for g in m.groups() if g and g.isdigit()), None)
    count = max(1, min(3, int(n))) if n else 1
    owner = "opponent"
    # "of your Life" without opponent's → own life pile
    frag = m.group(0)
    if re.search(r"of your Life|自己的?生命值", frag, re.I) and not re.search(
        r"opponent'?s Life|對手的?生命|对手的?生命|持有者的生命", frag, re.I
    ):
        owner = "self"
    op = {
        "op": "place_on_life",
        "count": count,
        "owner": owner,
        "position": "top_or_bottom",
        "face": "up",
        "optional": True,
        "target_kind": "opponent_character",
    }
    m_c = re.search(r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下", scope, re.I)
    if m_c:
        op["cost_lte"] = int(next(g for g in m_c.groups() if g))
    return op


def _infer_buff(scope: str) -> dict | None:
    m = AMT_RE.search(scope)
    if not m:
        return None
    if re.search(r"give\s+\d+\s+active DON|附加.{0,12}咚", scope, re.I):
        return None
    amt = _parse_amt(next(g for g in m.groups() if g))
    if amt is None:
        return None
    tk = _loc_target_kind(scope, amt)
    if not tk:
        if amt < 0:
            tk = "opponent_character" if re.search(r"Character|角色", scope, re.I) else "opponent_leader_or_character"
        else:
            tk = "own_character" if re.search(r"Character|角色", scope, re.I) else "leader"
    return {"op": "buff", "amount": amt, "target_kind": tk, "optional": True}


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
        "loc_tk": 0,
        "buff_side": 0,
        "place_on_life": 0,
        "choose_replaced": 0,
        "choose_dropped": 0,
        "activate_timing": 0,
        "dedupe_buff": 0,
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
            scope = summary if len(summary) >= 18 else (chunk if multi else blob)
            if len(scope) < 12:
                scope = chunk or blob
            ops = [dict(o) for o in (ability.get("ops") or [])]

            # activate this card's [X] effect
            m_act = re.search(
                r"activate this card'?s\s*\[([^\]]+)\]\s*effect|"
                r"發動這張卡片的【([^】]+)】效果|发动这张卡片的【([^】]+)】效果",
                scope,
                re.I,
            )
            if m_act and not any(o.get("op") == "activate_timing" for o in ops):
                label = next(g for g in m_act.groups() if g)
                label_l = label.strip().lower()
                timing_map = {
                    "counter": "counter_event",
                    "main": "main_start",
                    "activate: main": "activate_main",
                    "on play": "on_play",
                }
                linked = timing_map.get(label_l, label_l.replace(" ", "_"))
                ops = [{"op": "activate_timing", "timing": linked, "optional": False}]
                stats["activate_timing"] += 1
                changed = True

            rebuilt: list[dict] = []
            for o in ops:
                kind = o.get("op")

                # Drop junk empty choose_target when activate_timing already set
                if kind == "choose_target" and any(x.get("op") == "activate_timing" for x in ops):
                    stats["choose_dropped"] += 1
                    changed = True
                    continue

                # place_on_life replacement for empty choose / wrong add_life pair
                if kind == "choose_target" and not o.get("then_op"):
                    life_op = _life_place_op(scope)
                    if life_op:
                        rebuilt.append(life_op)
                        stats["place_on_life"] += 1
                        stats["choose_replaced"] += 1
                        changed = True
                        continue
                    buff = _infer_buff(scope)
                    if buff:
                        rebuilt.append(buff)
                        stats["choose_replaced"] += 1
                        changed = True
                        continue
                    ko = _parse_ko_op(scope)
                    if ko and re.search(r"K\.?O|KO", scope, re.I):
                        rebuilt.append(ko)
                        stats["choose_replaced"] += 1
                        changed = True
                        continue
                    # Drop empty choose when other concrete ops already exist and summary
                    # is not a pure targeting effect.
                    concrete = [x for x in ops if x.get("op") not in {"choose_target", "unsupported"}]
                    if concrete and not re.search(
                        r"give|gains?|K\.?O|rest|return|place|add up to|力量|置為|置为",
                        scope,
                        re.I,
                    ):
                        stats["choose_dropped"] += 1
                        changed = True
                        continue

                # Fix Leader-or-Character target kinds
                if kind in {
                    "buff",
                    "choose_target",
                    "ko",
                    "return_to_hand",
                    "rest_character",
                    "rest_opponent_character",
                    "trash",
                    "set_character_active",
                    "attach_don",
                    "grant_keyword",
                    "place_on_life",
                }:
                    amt = o.get("amount") if kind == "buff" else None
                    if kind == "buff" and isinstance(o.get("then_op"), dict):
                        pass
                    loc = _loc_target_kind(scope, int(amt) if amt is not None else None)
                    if loc and o.get("target_kind") != loc:
                        # don't widen rest_opponent_character to leader via wrong op
                        if kind == "rest_opponent_character" and "leader" in loc:
                            pass
                        else:
                            o = dict(o)
                            o["target_kind"] = loc
                            if kind == "choose_target" and isinstance(o.get("then_op"), dict):
                                then = dict(o["then_op"])
                                if then.get("op") in {"buff", "ko", "return_to_hand", "trash"}:
                                    then["target_kind"] = loc
                                    o["then_op"] = then
                            stats["loc_tk"] += 1
                            changed = True

                # buff side correction: +power on opponent tk with "your" text
                if kind == "buff":
                    try:
                        amt = int(o.get("amount") or 0)
                    except (TypeError, ValueError):
                        amt = 0
                    tk = str(o.get("target_kind") or "")
                    if amt > 0 and "opponent" in tk and re.search(r"\byour\b|自己的|我方", scope, re.I):
                        o = dict(o)
                        o["target_kind"] = (
                            "own_leader_or_character"
                            if LEADER_OR_CHAR_RE.search(scope)
                            else "own_character"
                            if re.search(r"Character|角色", scope, re.I)
                            else "leader"
                        )
                        stats["buff_side"] += 1
                        changed = True
                    if amt < 0 and tk.startswith("own") and re.search(r"opponent|對手|对手", scope, re.I):
                        o = dict(o)
                        o["target_kind"] = (
                            "opponent_leader_or_character"
                            if LEADER_OR_CHAR_RE.search(scope)
                            else "opponent_character"
                        )
                        stats["buff_side"] += 1
                        changed = True

                # choose_target with then_op buff: sync target_kind
                if kind == "choose_target" and isinstance(o.get("then_op"), dict):
                    then = o["then_op"]
                    if then.get("op") == "buff":
                        loc = _loc_target_kind(scope, then.get("amount"))
                        if loc and o.get("target_kind") != loc:
                            o = dict(o)
                            o["target_kind"] = loc
                            then = dict(then)
                            then["target_kind"] = loc
                            o["then_op"] = then
                            stats["loc_tk"] += 1
                            changed = True

                rebuilt.append(o)

            ops = rebuilt

            # Inject place_on_life if text has it but ops don't
            if _life_place_op(scope) and not any(o.get("op") == "place_on_life" for o in ops):
                # Replace stray add_life that wrongly stands in for char→life
                cleaned = []
                replaced = False
                for o in ops:
                    if o.get("op") == "choose_target" and not o.get("then_op") and not replaced:
                        cleaned.append(_life_place_op(scope))
                        replaced = True
                        stats["place_on_life"] += 1
                        changed = True
                        continue
                    if o.get("op") == "add_life" and LIFE_PLACE_RE.search(scope) and not replaced:
                        # drop mis-parsed add_life once when place_on_life covers it
                        continue
                    cleaned.append(o)
                if not replaced:
                    cleaned.append(_life_place_op(scope))
                    stats["place_on_life"] += 1
                    changed = True
                ops = cleaned

            # Dedupe identical buff ops
            seen_buff = set()
            deduped = []
            for o in ops:
                if o.get("op") == "buff":
                    key = (o.get("amount"), o.get("target_kind"), o.get("optional"), o.get("cost_lte"))
                    if key in seen_buff:
                        stats["dedupe_buff"] += 1
                        changed = True
                        continue
                    seen_buff.add(key)
                # choose_target+buff duplicate of bare buff
                if (
                    o.get("op") == "choose_target"
                    and isinstance(o.get("then_op"), dict)
                    and o["then_op"].get("op") == "buff"
                ):
                    bkey = (
                        o["then_op"].get("amount"),
                        o.get("target_kind"),
                        True,
                        o.get("cost_lte"),
                    )
                    if any(
                        x.get("op") == "buff"
                        and x.get("amount") == o["then_op"].get("amount")
                        and x.get("target_kind") == o.get("target_kind")
                        for x in ops
                    ):
                        # keep bare buff, drop choose wrapper
                        stats["dedupe_buff"] += 1
                        changed = True
                        continue
                deduped.append(o)
            ops = deduped

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
