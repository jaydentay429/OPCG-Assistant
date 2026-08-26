#!/usr/bin/env python3
"""Fix buff target_kind + inject attach/active/rest/rth/mill + leader OR traits.

Writes both card_effects.json and card_effect_overrides.json.

Usage:
  .venv/bin/python scripts/fix_semantic_targets_ops.py --dry-run
  .venv/bin/python scripts/fix_semantic_targets_ops.py
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
    _parse_attach_don_ops,
    _parse_return_char_to_hand_ops,
    _parse_set_active_ops,
    effect_blob,
)

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "targets_ops_fixed_ids.txt"

LEADER_OR_RE = re.compile(
    r"(?:Leader has the \{([^}]+)\} or \{([^}]+)\}|"
    r"領航卡擁有《([^》]+)》或《([^》]+)》|"
    r"领航卡拥有《([^》]+)》或《([^》]+)》)",
    re.I,
)
MILL_RE = re.compile(
    r"(?:trash\s*(\d+)\s*cards? from the top of your deck|"
    r"(?:將|将)(?:最多)?\s*(\d+)\s*[張张]自己卡組上面的卡片放置[在到]廢棄區|"
    r"(?:將|将)(?:最多)?\s*(\d+)\s*[张張]自己卡组上面的卡片放置[在到]废弃区)",
    re.I,
)
REST_OPP_RE = re.compile(
    r"(?:rest up to 1 of your opponent'?s Characters?|"
    r"(?:將|将)最多1[張张]對手.{0,40}置為休息|"
    r"(?:將|将)最多1[张張]对手.{0,40}置为休息)",
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


def _infer_buff_target(scope: str, amount: int) -> str | None:
    if re.search(r"opponent'?s Leader or Character|對手的領航卡或角色|对手的领航卡或角色", scope, re.I):
        return "opponent_leader_or_character"
    if re.search(r"opponent'?s Characters?|對手的角色|对手的角色", scope, re.I):
        return "opponent_character"
    if amount < 0 and re.search(r"opponent|對手|对手", scope, re.I):
        return "opponent_character"
    if re.search(r"your Leader or Character|自己的領航卡或角色|自己的领航卡或角色", scope, re.I):
        return "own_leader_or_character"
    if re.search(r"your Characters? or \[|自己的角色卡或「", scope, re.I):
        return "own_character"
    if re.search(r"your Leader|自己的領航|自己的领航|Your Leader", scope, re.I) and not re.search(
        r"Character|角色", scope, re.I
    ):
        return "leader"
    if re.search(r"this Character|這張角色|这张角色|自身", scope, re.I):
        return "self"
    if re.search(r"your Characters?|自己的角色", scope, re.I):
        return "own_character"
    if amount > 0 and re.search(r"Leader|領航|领航", scope, re.I):
        return "leader"
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
        "buff_tk": 0,
        "attach": 0,
        "active": 0,
        "rest_opp": 0,
        "rth": 0,
        "mill": 0,
        "leader_or": 0,
        "cards_touched": 0,
    }
    touched: list[str] = []

    reload_effect_library(force=True)

    for cid, rev in (semantic.get("cards") or {}).items():
        if rev.get("verdict") != "issue":
            continue
        # Start from merged view so we don't fight stale overrides.
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

            # buff target_kind
            for o in ops:
                if o.get("op") != "buff" or o.get("target_kind"):
                    continue
                tk = _infer_buff_target(scope, int(o.get("amount") or 0))
                if tk:
                    o["target_kind"] = tk
                    stats["buff_tk"] += 1
                    changed = True

            # attach_don
            if not any(o.get("op") == "attach_don" for o in ops):
                for op in _parse_attach_don_ops(scope) or _parse_attach_don_ops(chunk):
                    ops.append(op)
                    stats["attach"] += 1
                    changed = True

            # set active
            if not any(o.get("op") == "set_character_active" for o in ops):
                for op in _parse_set_active_ops(scope) or _parse_set_active_ops(chunk):
                    ops.append(op)
                    stats["active"] += 1
                    changed = True

            # return to hand
            if not any(o.get("op") == "return_to_hand" for o in ops):
                for op in _parse_return_char_to_hand_ops(scope) or _parse_return_char_to_hand_ops(chunk):
                    ops.append(op)
                    stats["rth"] += 1
                    changed = True

            # rest opponent
            if REST_OPP_RE.search(scope) or REST_OPP_RE.search(chunk):
                if not any(o.get("op") in {"rest_opponent_character", "rest_character"} for o in ops):
                    rest_op: dict = {"op": "rest_opponent_character", "count": 1, "optional": True}
                    m_clte = re.search(r"(?:費用|费用)\s*(\d+)\s*以下|cost of\s*(\d+)\s*or less", scope + chunk, re.I)
                    if m_clte:
                        rest_op["cost_lte"] = int(m_clte.group(1) or m_clte.group(2))
                    ops.append(rest_op)
                    stats["rest_opp"] += 1
                    changed = True

            # mill deck top
            m_mill = MILL_RE.search(scope) or MILL_RE.search(chunk)
            if m_mill and not any(o.get("op") == "trash_deck_top" for o in ops):
                n = int(next(g for g in m_mill.groups() if g))
                as_cost = bool(re.search(r":|：", m_mill.group(0)) or re.search(r"trash.{0,40}:", scope, re.I))
                op_m = {"op": "trash_deck_top", "count": n, "optional": True}
                if as_cost:
                    op_m["as_cost"] = True
                ops = [op_m, *ops] if as_cost else [*ops, op_m]
                stats["mill"] += 1
                changed = True

            # leader OR trait
            m_or = LEADER_OR_RE.search(scope) or LEADER_OR_RE.search(chunk) or (
                None if multi else LEADER_OR_RE.search(blob)
            )
            if m_or:
                traits = [g.strip() for g in m_or.groups() if g and str(g).strip()]
                if len(traits) >= 2:
                    joined = "|".join(traits[:2])
                    cur = str(ability.get("require_leader_trait") or "")
                    if "|" not in cur:
                        ability["require_leader_trait"] = joined
                        stats["leader_or"] += 1
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
