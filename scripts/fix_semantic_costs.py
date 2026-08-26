#!/usr/bin/env python3
"""Fix rest_self / rested-KO / choose_target→ko / trash as_cost clusters.

Usage:
  .venv/bin/python scripts/fix_semantic_costs.py --dry-run
  .venv/bin/python scripts/fix_semantic_costs.py
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
    _enrich_ops_with_target_filters,
    _parse_ko_op,
    effect_blob,
)

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "cost_fixed_ids.txt"

REST_SELF_RE = re.compile(
    r"(?:you may )?rest this (?:Character|Stage|Leader)\s*:|"
    r"可[將将]這[張张](?:角色|舞台|領航|领航)卡置為休息\s*[：:]|"
    r"可[將将]这[张張](?:角色|舞台|领航|領航)卡置为休息\s*[：:]",
    re.I,
)
TRASH_HAND_COST_RE = re.compile(
    r"(?:you may )?trash\s*(\d+)\s*cards? from your hand\s*:|"
    r"可[將将]\s*(\d+)\s*[張张]手牌放置[在到]廢棄區\s*[：:]|"
    r"可[將将]\s*(\d+)\s*[张張]手牌放置[在到]废弃区\s*[：:]|"
    r"可[將将]1[張张]手牌放置[在到]廢棄區\s*[：:]|"
    r"可[將将]1[张張]手牌放置[在到]废弃区\s*[：:]",
    re.I,
)
TRASH_DECK_COST_RE = re.compile(
    r"(?:you may )?trash\s*(\d+)\s*cards? from the top of your deck\s*:|"
    r"可[將将]自己卡組上面\s*(\d+)\s*[張张]卡片放置[在到]廢棄區\s*[：:]|"
    r"可[將将]自己卡组上面\s*(\d+)\s*[张張]卡片放置[在到]废弃区\s*[：:]",
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
    }
    pat = patterns.get(t)
    if not pat:
        return blob
    m = re.search(pat, blob, re.I)
    if not m:
        return str(blob)
    rest = blob[m.end() :]
    stop = re.search(
        r"(?=\[(?:on play|when attacking|activate|on\s*k\.?o\.?|trigger|counter|main|don!!)|【)",
        rest,
        re.I,
    )
    end = m.end() + (stop.start() if stop else min(len(rest), 500))
    return blob[m.start() : end]


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
        "rested_target": 0,
        "rest_self": 0,
        "choose_to_ko": 0,
        "trash_hand_cost": 0,
        "trash_deck_cost": 0,
        "ops_enriched": 0,
        "cards_touched": 0,
    }
    touched: list[str] = []

    for cid, rev in (semantic.get("cards") or {}).items():
        if rev.get("verdict") != "issue":
            continue
        entry = cards.get(cid)
        if not isinstance(entry, dict):
            continue
        abilities = [dict(a) for a in (entry.get("abilities") or []) if isinstance(a, dict)]
        if not abilities:
            continue
        blob = effect_blob(catalog.get(cid) or {})
        changed = False
        new_abs: list[dict] = []

        for ability in abilities:
            timing = str(ability.get("timing") or "")
            chunk = _timing_chunk(blob, timing)
            scope = str(ability.get("summary") or "").strip() or chunk or blob
            if len(scope) < 20:
                scope = chunk or blob

            ops = list(ability.get("ops") or [])
            before = json.dumps(ops, sort_keys=True, ensure_ascii=False)

            # Flatten choose_target → ko when then_op is ko / summary says KO.
            rebuilt: list[dict] = []
            for op in ops:
                if op.get("op") == "choose_target":
                    then = op.get("then_op") if isinstance(op.get("then_op"), dict) else None
                    wants_ko = (then and then.get("op") == "ko") or bool(
                        re.search(r"K\.?O|KO", scope, re.I)
                    )
                    if wants_ko:
                        parsed = _parse_ko_op(scope) or _parse_ko_op(chunk) or _parse_ko_op(blob)
                        if then and then.get("op") == "ko":
                            ko = dict(then)
                            if parsed:
                                for k in ("cost_lte", "cost_eq", "power_lte", "base_power_lte", "target_kind"):
                                    if parsed.get(k) is not None and ko.get(k) is None:
                                        ko[k] = parsed[k]
                        elif parsed:
                            ko = dict(parsed)
                        else:
                            ko = {
                                "op": "ko",
                                "target_kind": str(op.get("target_kind") or "opponent_character"),
                                "optional": True,
                            }
                        # pull power from then summary if needed
                        if ko.get("power_lte") is None and ko.get("base_power_lte") is None and then:
                            m = re.search(r"(\d{3,5})\s*(?:or less|以下)", str(then.get("summary") or ""), re.I)
                            if m:
                                ko["power_lte"] = int(m.group(1))
                        rebuilt.append(ko)
                        stats["choose_to_ko"] += 1
                        changed = True
                        continue
                rebuilt.append(dict(op))
            ops = rebuilt

            ops = _enrich_ops_with_target_filters(ops, scope)
            ops = _enrich_ops_with_target_filters(ops, chunk)
            if json.dumps(ops, sort_keys=True, ensure_ascii=False) != before:
                stats["ops_enriched"] += 1
                changed = True

            # Force rested KO target from paper.
            for op in ops:
                if op.get("op") != "ko":
                    continue
                if re.search(
                    r"rested Character|對手休息狀態|对手休息状态|休息狀態.{0,12}角色|休息状态.{0,12}角色",
                    scope + "\n" + chunk,
                    re.I,
                ):
                    if str(op.get("target_kind") or "") != "opponent_character_rested":
                        op["target_kind"] = "opponent_character_rested"
                        stats["rested_target"] += 1
                        changed = True

            # rest_self colon cost
            if REST_SELF_RE.search(chunk) or REST_SELF_RE.search(scope):
                if timing in {"activate_main", "on_play", "when_attacking"} and not ability.get("rest_self"):
                    ability["rest_self"] = True
                    stats["rest_self"] += 1
                    changed = True

            # trash_hand as_cost
            m_th = TRASH_HAND_COST_RE.search(chunk) or TRASH_HAND_COST_RE.search(scope)
            if m_th:
                n = 1
                for g in m_th.groups():
                    if g and str(g).isdigit():
                        n = int(g)
                        break
                th = [o for o in ops if o.get("op") == "trash_hand"]
                if not th:
                    ops = [{"op": "trash_hand", "count": n, "optional": True, "as_cost": True}, *ops]
                    stats["trash_hand_cost"] += 1
                    changed = True
                else:
                    for o in th:
                        if not o.get("as_cost"):
                            o["as_cost"] = True
                            o["optional"] = True
                            stats["trash_hand_cost"] += 1
                            changed = True

            # trash_deck_top as_cost
            m_td = TRASH_DECK_COST_RE.search(chunk) or TRASH_DECK_COST_RE.search(scope)
            if m_td:
                n = 1
                for g in m_td.groups():
                    if g and str(g).isdigit():
                        n = int(g)
                        break
                td = [o for o in ops if o.get("op") == "trash_deck_top"]
                if not td:
                    ops = [{"op": "trash_deck_top", "count": n, "as_cost": True, "optional": True}, *ops]
                    stats["trash_deck_cost"] += 1
                    changed = True
                else:
                    for o in td:
                        if not o.get("as_cost"):
                            o["as_cost"] = True
                            o["optional"] = True
                            if not o.get("count"):
                                o["count"] = n
                            stats["trash_deck_cost"] += 1
                            changed = True

            ability["ops"] = ops
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
