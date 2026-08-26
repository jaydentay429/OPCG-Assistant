#!/usr/bin/env python3
"""Static fidelity checklist for A/B/C focus cards → meta/effect_fidelity_report.md"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))

from battle.effect_library import get_abilities, reload_effect_library
from battle.effects import effect_blob
from scripts.fix_abc_fidelity import FOCUS, base_id

EXPECT = {
    "OP08-043": {"on_play": {"ops": {"attack_tax"}, "gates": {"require_life_lte", "require_leader_trait"}}},
    "OP14-119": {
        "your_turn": {"ops": {"deny_rest"}, "extra": {"trigger_on": "self_rested"}},
        "on_opponent_attack": {"ops": {"trash_hand", "buff"}},
    },
    "OP05-072": {"on_play": {"ops": {"buff"}, "gates": {"require_don_field_gte"}}},
    "OP09-033": {"on_play": {"ops": {"cannot_be_ko"}, "gates": {"require_rested_own_chars_gte"}}},
    "ST07-015": {"on_play": {"ops": {"choose_one"}}},
    "ST11-003": {"on_play": {"ops": {"choose_one"}, "gates": {"require_leader_name"}}},
    "OP06-039": {"on_play": {"ops": {"choose_one"}}},
    "OP08-117": {"on_play": {"ops": {"trash_life", "ko"}}, "trigger": {"ops": {"life_to_hand", "hand_to_life"}}},
    "EB04-054": {"on_ko": {"ops": {"life_to_hand"}}},
    "OP15-097": {"on_play": {"ops": {"deny_attack"}, "gates": {"require_trash_gte"}}},
    "OP08-112": {"on_play": {"ops": {"deny_attack"}}},
    "OP14-118": {"counter_event": {"ops": {"deny_attack"}, "gates": {"require_life_lte"}}},
    "P-057": {"on_play": {"ops": {"skip_untap"}, "gates": {"require_leader_name"}}},
    "OP03-091": {"on_play": {"ops": {"set_cost"}}},
    "OP04-100": {"trigger": {"ops": {"deny_attack"}}},
    "OP14-111": {"trigger": {"ops": {"play_from_hand"}}},
}


def main() -> None:
    reload_effect_library(force=True)
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    rows = []
    fails = 0
    for base, rules in EXPECT.items():
        cid = base if base in catalog else next((k for k in catalog if base_id(k) == base), base)
        abs_ = {a["timing"]: a for a in get_abilities(cid)}
        ok_all = True
        notes = []
        for timing, rule in rules.items():
            a = abs_.get(timing)
            if not a:
                ok_all = False
                notes.append(f"missing timing {timing}")
                continue
            ops = {o.get("op") for o in (a.get("ops") or [])}
            need = set(rule.get("ops") or [])
            if not need.issubset(ops):
                ok_all = False
                notes.append(f"{timing} ops {ops} missing {need - ops}")
            for g in rule.get("gates") or []:
                if a.get(g) is None:
                    ok_all = False
                    notes.append(f"{timing} missing gate {g}")
            for k, v in (rule.get("extra") or {}).items():
                if a.get(k) != v:
                    ok_all = False
                    notes.append(f"{timing} {k}={a.get(k)!r} want {v!r}")
            if timing == "on_play" and base == "OP08-112":
                if not (a.get("ops") or [{}])[0].get("exclude_name"):
                    ok_all = False
                    notes.append("missing exclude_name")
            if timing == "on_ko" and base == "EB04-054":
                if (a.get("ops") or [{}])[0].get("hand_owner") != "life_owner":
                    ok_all = False
                    notes.append("hand_owner != life_owner")
        if not ok_all:
            fails += 1
        rows.append((base, "PASS" if ok_all else "FAIL", "; ".join(notes)))

    md = [
        "# Effect fidelity report (A/B/C focus)",
        "",
        f"Generated: `{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}`",
        "",
        f"- Checked: **{len(rows)}** bases",
        f"- Failures: **{fails}**",
        "",
        "| Base | Result | Notes |",
        "|------|--------|-------|",
    ]
    for b, r, n in rows:
        md.append(f"| {b} | {r} | {n.replace('|', '/')} |")
    out = ROOT / "meta" / "effect_fidelity_report.md"
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"checked": len(rows), "failures": fails, "path": str(out)}))
    if fails:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
