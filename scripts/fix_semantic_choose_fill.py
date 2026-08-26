#!/usr/bin/env python3
"""Fill empty choose_target then_ops + inject active_don / life-place markers.

Writes library + overrides.

Usage:
  .venv/bin/python scripts/fix_semantic_choose_fill.py --dry-run
  .venv/bin/python scripts/fix_semantic_choose_fill.py
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
    _parse_active_don_ops,
    _parse_ko_op,
    effect_blob,
)

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "choose_fill_fixed_ids.txt"

AMT_RE = re.compile(
    r"(?:gains?|give|gets?|力量值)\s*([+\-−－＋]\s*\d{3,5})|"
    r"([+\-−－＋]\s*\d{3,5})\s*(?:power|力量)",
    re.I,
)
LIFE_PLACE_RE = re.compile(
    r"place up to\s*(\d+)\s+of your opponent'?s Characters?.{0,80}"
    r"(?:top or bottom|top|bottom) of your opponent'?s Life|"
    r"(?:將|将)最多\s*(\d+)\s*[張张]對手.{0,40}角色卡.{0,40}"
    r"生命值區的(?:上面或下面|上面|下面)|"
    r"(?:將|将)最多\s*(\d+)\s*[张張]对手.{0,40}角色卡.{0,40}"
    r"生命值区的(?:上面或下面|上面|下面)",
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


def _infer_then_from_scope(scope: str, target_kind: str) -> dict | None:
    ko = _parse_ko_op(scope)
    if ko and re.search(r"K\.?O|KO", scope, re.I):
        return ko

    if re.search(
        r"set .{0,40}as active|置為活動|置为活动",
        scope,
        re.I,
    ) and re.search(r"Character|角色", scope, re.I):
        return {"op": "set_character_active", "count": 1, "target_kind": "own_character", "optional": True}

    if re.search(r"rest up to|置為休息|置为休息", scope, re.I) and re.search(
        r"opponent|對手|对手", scope, re.I
    ):
        op = {"op": "rest_opponent_character", "count": 1, "optional": True}
        m = re.search(r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下", scope, re.I)
        if m:
            op["cost_lte"] = int(next(g for g in m.groups() if g))
        return op

    if re.search(r"return .{0,60}hand|放回持有者的手牌|返回持有者的手牌", scope, re.I):
        tk = target_kind or "opponent_character"
        if re.search(r"active|活動狀態|活动状态", scope, re.I):
            tk = "opponent_character_active"
        op = {"op": "return_to_hand", "target_kind": tk, "optional": True}
        m = re.search(r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下", scope, re.I)
        if m:
            op["cost_lte"] = int(next(g for g in m.groups() if g))
        return op

    m_life = LIFE_PLACE_RE.search(scope)
    if m_life:
        n = int(next(g for g in m_life.groups() if g))
        op = {
            "op": "place_on_life",
            "count": max(1, min(3, n)),
            "owner": "opponent",
            "position": "top_or_bottom",
            "face": "up",
            "optional": True,
            "target_kind": "opponent_character",
        }
        m_c = re.search(r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下", scope, re.I)
        if m_c:
            op["cost_lte"] = int(next(g for g in m_c.groups() if g))
        return op

    m = AMT_RE.search(scope)
    if m:
        amt = _parse_amt(next(g for g in m.groups() if g))
        if amt is None:
            return None
        # DON attach "give 1 active DON" is not a power buff
        if re.search(r"give\s+\d+\s+active DON|附加.{0,12}咚", scope, re.I) and abs(amt) < 100:
            return None
        tk = target_kind or (
            "opponent_leader_or_character"
            if amt < 0 and re.search(r"Leader or Character|領航卡或角色|领航卡或角色", scope, re.I)
            else "opponent_character"
            if amt < 0
            else "own_leader_or_character"
            if re.search(r"Leader or Character|領航卡或角色|领航卡或角色", scope, re.I)
            else "own_character"
            if re.search(r"Character|角色", scope, re.I)
            else "leader"
        )
        return {"op": "buff", "amount": amt, "target_kind": tk, "optional": True}
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

    stats = {"choose_filled": 0, "choose_replaced": 0, "active_don": 0, "rth_active": 0, "cards_touched": 0}
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
            scope = summary if len(summary) >= 20 else (chunk if multi else blob)
            if len(scope) < 16:
                scope = chunk or blob
            ops = [dict(o) for o in (ability.get("ops") or [])]

            rebuilt: list[dict] = []
            for o in ops:
                if o.get("op") == "choose_target" and not o.get("then_op"):
                    then = _infer_then_from_scope(scope, str(o.get("target_kind") or ""))
                    if then:
                        # Prefer flattening to the concrete op when it's the only action.
                        if len(ops) == 1 or then.get("op") in {"buff", "ko", "rest_opponent_character", "return_to_hand", "place_on_life", "set_character_active"}:
                            # Keep cost filter on outer choose if present
                            for k in ("cost_lte", "cost_eq", "power_lte", "base_power_lte"):
                                if o.get(k) is not None and then.get(k) is None:
                                    then[k] = o.get(k)
                            if then.get("op") == "buff" and not then.get("target_kind"):
                                then["target_kind"] = o.get("target_kind") or then.get("target_kind")
                            rebuilt.append(then)
                            stats["choose_replaced"] += 1
                            changed = True
                            continue
                        o = dict(o)
                        o["then_op"] = then
                        stats["choose_filled"] += 1
                        changed = True
                if o.get("op") == "return_to_hand":
                    if re.search(r"active Character|活動狀態的角色|活动状态的角色", scope, re.I):
                        if "active" not in str(o.get("target_kind") or ""):
                            o["target_kind"] = "opponent_character_active"
                            stats["rth_active"] += 1
                            changed = True
                rebuilt.append(o)
            ops = rebuilt

            # active_don
            if not any(o.get("op") == "active_don" for o in ops):
                for op in _parse_active_don_ops(scope) or _parse_active_don_ops(chunk):
                    ops.append(op)
                    stats["active_don"] += 1
                    changed = True

            # life-place when only choose_target missing and parser path didn't catch
            if LIFE_PLACE_RE.search(scope) and not any(
                o.get("op") == "place_on_life"
                or (o.get("op") == "choose_target" and isinstance(o.get("then_op"), dict) and o["then_op"].get("op") == "place_on_life")
                for o in ops
            ):
                then = _infer_then_from_scope(scope, "opponent_character")
                if then and then.get("op") == "place_on_life":
                    ops.append(then)
                    stats["choose_replaced"] += 1
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
