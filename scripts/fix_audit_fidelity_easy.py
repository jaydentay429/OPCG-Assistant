#!/usr/bin/env python3
"""Auto-fix remaining audit/fidelity easy wins from latest reports."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability, normalize_card_entry  # noqa: E402


def main() -> int:
    lib_path, _ = library_paths()
    raw = json.loads(lib_path.read_text(encoding="utf-8"))
    cards = raw.setdefault("cards", {})
    audit = json.loads((ROOT / "meta" / "effect_audit_report.json").read_text(encoding="utf-8"))
    fid = json.loads((ROOT / "meta" / "effect_fidelity_full_report.json").read_text(encoding="utf-8"))

    stats = {
        "once_flags": 0,
        "gates": 0,
        "leader_traits": 0,
        "leader_names": 0,
        "timing_aliases": 0,
        "cards_touched": 0,
    }

    touched: set[str] = set()

    def entry(cid: str) -> dict:
        e = cards.get(cid) or {"version": 1, "abilities": []}
        return e

    def _cid(f: dict) -> str:
        return str(f.get("card_id") or f.get("id") or f.get("base_id") or "")

    # 1) once flags from audit
    for f in audit.get("findings") or []:
        if f.get("category") != "once_flag_missing":
            continue
        cid = _cid(f)
        if not cid or cid not in cards:
            continue
        e = entry(cid)
        abs_ = [dict(a) for a in (e.get("abilities") or [])]
        want_timing = str(f.get("timing") or "")
        changed = False
        for a in abs_:
            if a.get("once"):
                continue
            timing = str(a.get("timing") or "")
            if want_timing and timing != want_timing:
                continue
            if timing in {
                "activate_main",
                "when_attacking",
                "on_play",
                "trigger",
                "on_ko",
                "on_don_returned",
                "your_turn",
                "opponent_turn",
                "counter_event",
                "on_opponent_attack",
                "on_block",
                "end_of_your_turn",
            }:
                a["once"] = True
                changed = True
                stats["once_flags"] += 1
        if changed:
            normed = [na for a in abs_ if (na := normalize_ability(a))]
            cards[cid] = normalize_card_entry(cid, {"version": 1, "abilities": normed})
            touched.add(cid)

    # 2) fidelity gates / leader requirements
    for f in fid.get("findings") or []:
        cat = str(f.get("category") or "")
        cid = _cid(f)
        if not cid or cid not in cards:
            continue
        e = entry(cid)
        abs_ = [dict(a) for a in (e.get("abilities") or [])]
        if not abs_:
            continue
        changed = False
        detail = str(f.get("detail") or "")

        if cat == "missing_gate":
            m = re.search(r"(require_[a-z_]+)=(\d+)", detail)
            if m:
                key, val = m.group(1), int(m.group(2))
                for a in abs_:
                    if a.get(key) is None:
                        a[key] = val
                        changed = True
                        stats["gates"] += 1
        elif cat == "missing_leader_trait":
            m = re.search(r"leader trait '([^']+)'", detail)
            if m:
                trait = m.group(1)
                for a in abs_:
                    if not a.get("require_leader_trait"):
                        a["require_leader_trait"] = trait
                        changed = True
                        stats["leader_traits"] += 1
        elif cat == "missing_leader_name":
            m = re.search(r"leader name '([^']+)'", detail)
            if m:
                name = m.group(1)
                for a in abs_:
                    if not a.get("require_leader_name"):
                        a["require_leader_name"] = name
                        changed = True
                        stats["leader_names"] += 1
        elif cat == "missing_timing":
            # Mirror on_don_returned abilities onto the text-marked timing.
            want = str(f.get("timing") or "")
            if want and not any(a.get("timing") == want for a in abs_):
                donors = [a for a in abs_ if a.get("timing") == "on_don_returned"]
                if donors:
                    clone = dict(donors[0])
                    clone["timing"] = want
                    abs_.append(clone)
                    changed = True
                    stats["timing_aliases"] += 1

        if changed:
            normed = [na for a in abs_ if (na := normalize_ability(a))]
            cards[cid] = normalize_card_entry(cid, {"version": 1, "abilities": normed})
            touched.add(cid)

    stats["cards_touched"] = len(touched)
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
