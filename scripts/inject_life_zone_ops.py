#!/usr/bin/env python3
"""Inject parsed life-zone ops into library abilities that are missing them.

Also upgrades battle-KO / leave replacements that should be replace_leave.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_fidelity import extract_expected_signals  # noqa: E402
from battle.effect_library import compile_card_from_templates, library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import ability_is_runnable, normalize_ability, normalize_card_entry  # noqa: E402
from battle.effects import (  # noqa: E402
    _parse_life_zone_ops,
    _parse_replace_leave_ops,
    effect_blob,
    has_meaningful_effect_text,
)


def _merge_ops(existing: list[dict], extra: list[dict]) -> list[dict]:
    out = list(existing)
    for op in extra:
        kind = op.get("op")
        if kind == "replace_leave":
            # Prefer replace_leave over bare replace_battle_ko / incomplete stubs.
            out = [o for o in out if o.get("op") not in {"replace_battle_ko", "choose_target"}]
            if not any(o.get("op") == "replace_leave" for o in out):
                out.insert(0, op)
            continue
        if any(
            o.get("op") == kind
            and o.get("owner") == op.get("owner")
            and o.get("as_cost") == op.get("as_cost")
            for o in out
        ):
            continue
        # Put costs first
        if op.get("as_cost"):
            out.insert(0, op)
        else:
            out.append(op)
    return out


def _pick_timing(blob: str, abilities: list[dict], op: dict) -> str | None:
    # Prefer timing already present that matches text tags / op role.
    by_t = {a.get("timing"): a for a in abilities if a.get("timing")}
    order = []
    if re.search(r"\[trigger\]|【觸發器】|【触发】", blob, re.I):
        order.append("trigger")
    if re.search(r"\[counter\]|【反擊】|【反击】", blob, re.I):
        order.append("counter_event")
    if re.search(r"\[activate: main\]|【啟動主要】|【启动主要】", blob, re.I):
        order.append("activate_main")
    if re.search(r"\[end of your turn\]|【我方回合結束時】|【我方回合结束时】", blob, re.I):
        order.append("end_of_your_turn")
    if re.search(r"\[on play\]|【登場時】|【登场时】|\[main\]|【主要】", blob, re.I):
        order.append("on_play")
    if re.search(r"\[on block\]|【防禦時】|【防御时】", blob, re.I):
        order.append("on_block")
    if re.search(r"would be k\.?o\.?'?d|遭到KO", blob, re.I):
        order.append("on_ko")
    if re.search(r"\[your turn\]|【我方回合中】", blob, re.I):
        order.append("your_turn")
    order.extend(["on_play", "activate_main", "trigger", "counter_event", "your_turn", "end_of_your_turn"])
    for t in order:
        if t in by_t:
            return t
    # Create timing from template if possible
    return order[0] if order else None


def main() -> int:
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    lib_path, _ = library_paths()
    raw = json.loads(lib_path.read_text(encoding="utf-8"))
    cards = raw.setdefault("cards", {})

    stats = {"cards_touched": 0, "ops_injected": 0, "replace_upgraded": 0}

    for cid, info in catalog.items():
        if not has_meaningful_effect_text(info):
            continue
        blob = effect_blob(info)
        expected = extract_expected_signals(info)
        hints = set(expected.get("op_hints") or [])
        life_ops = _parse_life_zone_ops(blob)
        replace_ops = _parse_replace_leave_ops(blob)
        # Also pull replace from battle-KO Life-to-hand parser path
        if not replace_ops:
            # compile templates may now emit replace_leave for OP10-034
            templ = compile_card_from_templates(cid, info)
            for a in templ.get("abilities") or []:
                for o in a.get("ops") or []:
                    if o.get("op") == "replace_leave":
                        replace_ops.append(o)

        needed = []
        for o in life_ops:
            if o.get("op") in hints:
                needed.append(o)
        for o in replace_ops:
            needed.append(o)

        if not needed and not (hints & {"life_to_hand", "trash_life", "hand_to_life", "flip_life", "replace_leave"}):
            continue

        entry = cards.get(cid) or {"version": 1, "abilities": []}
        abilities = [dict(a) for a in (entry.get("abilities") or [])]
        by_t = {a.get("timing"): a for a in abilities if a.get("timing")}
        changed = False

        # Upgrade replace_battle_ko → replace_leave when parser knows the shield.
        if replace_ops:
            for t, a in list(by_t.items()):
                ops = list(a.get("ops") or [])
                if any(o.get("op") == "replace_battle_ko" for o in ops) or not any(
                    o.get("op") == "replace_leave" for o in ops
                ):
                    if t in {"on_ko", "your_turn", "opponent_turn"} or "replace_leave" in hints:
                        new_ops = _merge_ops(ops, replace_ops)
                        if new_ops != ops:
                            a["ops"] = new_ops
                            a["status"] = "compiled" if a.get("status") == "unsupported" else a.get("status") or "compiled"
                            by_t[t] = a
                            changed = True
                            stats["replace_upgraded"] += 1

        for op in needed:
            kind = op.get("op")
            # Skip bare life ops that are only replacement costs.
            if kind in {"trash_life", "life_to_hand", "flip_life"} and replace_ops:
                if any(r.get("cost") == kind for r in replace_ops):
                    # Still ensure replace_leave is present
                    if kind == "replace_leave":
                        pass
                    elif any(r.get("op") == "replace_leave" for r in replace_ops):
                        if not any(
                            o.get("op") == "replace_leave"
                            for a in by_t.values()
                            for o in (a.get("ops") or [])
                        ):
                            timing = _pick_timing(blob, list(by_t.values()), op) or "your_turn"
                            cur = by_t.get(timing) or {
                                "timing": timing,
                                "summary": blob.strip()[:200],
                                "ops": [],
                                "status": "compiled",
                                "confidence": 0.75,
                            }
                            cur["ops"] = _merge_ops(list(cur.get("ops") or []), replace_ops)
                            by_t[timing] = cur
                            changed = True
                            stats["ops_injected"] += 1
                        continue

            if kind == "replace_leave":
                timing = _pick_timing(blob, list(by_t.values()), op) or "your_turn"
                if re.search(r"in battle|對戰中|对战中", blob, re.I):
                    timing = "on_ko" if "on_ko" in by_t or True else timing
                    timing = "on_ko"
                cur = by_t.get(timing) or {
                    "timing": timing,
                    "summary": blob.strip()[:200],
                    "ops": [],
                    "status": "compiled",
                    "confidence": 0.8,
                    "once": True,
                }
                before = list(cur.get("ops") or [])
                cur["ops"] = _merge_ops(before, [op])
                if cur["ops"] != before:
                    by_t[timing] = cur
                    changed = True
                    stats["ops_injected"] += 1
                continue

            timing = _pick_timing(blob, list(by_t.values()), op)
            if not timing:
                continue
            cur = by_t.get(timing)
            if cur is None:
                cur = {
                    "timing": timing,
                    "summary": blob.strip()[:200],
                    "ops": [],
                    "status": "compiled",
                    "confidence": 0.75,
                }
            # Don't inject into pure unsupported-only stubs without clearing unsupported
            ops = [o for o in (cur.get("ops") or []) if o.get("op") != "unsupported"]
            before = list(ops)
            ops = _merge_ops(ops, [op])
            # Fix common miscompile: trash_hand used where trash_life is meant for Life costs
            if op.get("op") == "trash_life" and op.get("as_cost"):
                ops = [o for o in ops if not (o.get("op") == "trash_hand" and o.get("as_cost"))]
            if op.get("op") == "life_to_hand":
                # remove mistaken return_to_hand for Life→hand
                ops = [
                    o
                    for o in ops
                    if not (o.get("op") == "return_to_hand" and "Life" in blob)
                ]
            if ops != before or cur.get("status") == "unsupported":
                cur["ops"] = ops
                if cur.get("status") == "unsupported" and any(
                    ability_is_runnable({"ops": ops, "status": "compiled", "timing": timing})
                    for _ in [0]
                ):
                    cur["status"] = "compiled"
                elif ops:
                    cur["status"] = cur.get("status") if cur.get("status") != "unsupported" else "compiled"
                by_t[timing] = cur
                changed = True
                stats["ops_injected"] += 1

        if not changed:
            continue

        normed = []
        for a in by_t.values():
            na = normalize_ability(a)
            if na:
                normed.append(na)
        if not normed:
            continue
        cards[cid] = normalize_card_entry(cid, {"version": 1, "abilities": normed})
        stats["cards_touched"] += 1

    print(json.dumps(stats, ensure_ascii=False), flush=True)
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
