#!/usr/bin/env python3
"""Promote complete needs_review abilities and strip leftover unsupported stubs.

Usage:
  .venv/bin/python scripts/promote_effect_quality.py
  .venv/bin/python scripts/promote_effect_quality.py --dry-run
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

from battle.effect_library import (  # noqa: E402
    compile_card_from_templates,
    library_paths,
    reload_effect_library,
)
from battle.effect_schema import ability_is_runnable, normalize_ability, normalize_card_entry, sanitize_ops_list  # noqa: E402
from battle.effects import (  # noqa: E402
    effect_blob,
    has_meaningful_effect_text,
    _parse_grant_cost_ops,
    _parse_hand_to_deck_ops,
    _parse_redirect_attack_ops,
    _parse_restriction_ops,
    _parse_reveal_opp_hand_ops,
    _parse_skip_untap_ops,
    _parse_trash_hand_down_to_ops,
    _parse_cannot_take_life_ops,
)


def _base(cid: str) -> str:
    return re.sub(r"-(?:P|R)\d+$", "", cid)


def _load_library() -> dict[str, dict]:
    path, _ = library_paths()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("cards"), dict):
        return raw["cards"]
    return raw if isinstance(raw, dict) else {}


def _dangling_choose(ops: list[dict]) -> bool:
    """True if choose_target is the only meaningful op and has no then_op."""
    real = [o for o in ops if o.get("op") and o.get("op") != "unsupported"]
    if not real:
        return True
    if len(real) == 1 and real[0].get("op") == "choose_target" and not real[0].get("then_op"):
        return True
    return False


def _fill_missing_from_text(ops: list[dict], blob: str) -> list[dict]:
    """Append restriction-family ops parsed from full blob if missing."""
    kinds = {o.get("op") for o in ops}
    extras: list[dict] = []
    for parser in (
        _parse_restriction_ops,
        _parse_hand_to_deck_ops,
        _parse_reveal_opp_hand_ops,
        _parse_grant_cost_ops,
        _parse_redirect_attack_ops,
        _parse_trash_hand_down_to_ops,
        _parse_skip_untap_ops,
        _parse_cannot_take_life_ops,
    ):
        for op in parser(blob):
            if op.get("op") not in kinds:
                extras.append(op)
                kinds.add(op.get("op"))
    # Late-bound imports for deny_* / set_cost
    from battle.effects import _parse_deny_attack_ops, _parse_deny_rest_ops, _parse_set_cost_ops

    for parser in (_parse_deny_attack_ops, _parse_deny_rest_ops, _parse_set_cost_ops):
        for op in parser(blob):
            if op.get("op") not in kinds:
                extras.append(op)
                kinds.add(op.get("op"))
    if not extras:
        return ops
    # Drop unsupported placeholders once we filled something, or always strip unsupported
    # when other real ops remain after fill.
    cleaned = [o for o in ops if o.get("op") != "unsupported"] + extras
    return sanitize_ops_list(cleaned)


def _should_promote(ability: dict) -> bool:
    if ability.get("status") != "needs_review":
        return False
    ops = ability.get("ops") or []
    if not ops:
        return False
    if any(o.get("op") == "unsupported" for o in ops):
        return False
    if _dangling_choose(ops):
        return False
    return ability_is_runnable(ability)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    cards = _load_library()

    promoted = 0
    stripped = 0
    filled = 0
    templated = 0

    for cid, info in catalog.items():
        if not has_meaningful_effect_text(info):
            continue
        entry = cards.get(cid) or {"abilities": []}
        abs_in = list(entry.get("abilities") or [])
        if not abs_in:
            continue
        blob = effect_blob(info)
        changed = False
        fresh = compile_card_from_templates(cid, info)
        fresh_by = {a["timing"]: a for a in (fresh.get("abilities") or []) if ability_is_runnable(a)}

        new_abs: list[dict] = []
        for a in abs_in:
            a = dict(a)
            timing = str(a.get("timing") or "")
            ops = list(a.get("ops") or [])
            has_unsup = any(o.get("op") == "unsupported" for o in ops)

            # Prefer fresh template when it has no unsupported and covers this timing.
            fr = fresh_by.get(timing)
            if fr and not any(o.get("op") == "unsupported" for o in (fr.get("ops") or [])):
                if has_unsup or a.get("status") == "needs_review":
                    # Keep once / require_* fields from either side when present.
                    merged = dict(fr)
                    for key in (
                        "once",
                        "require_leader_trait",
                        "require_don_attached_gte",
                        "require_trash_gte",
                        "require_rested_own_chars_gte",
                        "require_rested_own_chars_trait",
                        "on_opponent_event",
                        "on_char_leave_by_own_effect",
                        "require_opp_hand_gte",
                        "while_rested",
                        "negated_when_hand_trashed",
                        "require_opp_chars_count_gte",
                        "require_opp_chars_base_power_gte",
                    ):
                        if a.get(key) is not None and merged.get(key) is None:
                            merged[key] = a[key]
                    a = merged
                    changed = True
                    templated += 1
                    ops = list(a.get("ops") or [])
                    has_unsup = False

            if has_unsup:
                before = len(ops)
                ops2 = _fill_missing_from_text(ops, blob)
                # Always drop unsupported once any real ops exist after fill attempt.
                real = [o for o in ops2 if o.get("op") != "unsupported"]
                if real:
                    if len(real) < before or any(o.get("op") == "unsupported" for o in ops):
                        stripped += 1
                    if len(ops2) > len([o for o in ops if o.get("op") != "unsupported"]):
                        filled += 1
                    a["ops"] = sanitize_ops_list(real)
                    a["status"] = "needs_review" if _dangling_choose(real) else "compiled"
                    if a["status"] == "compiled":
                        a["confidence"] = max(float(a.get("confidence") or 0.6), 0.75)
                    changed = True
                    ops = a["ops"]

            na = normalize_ability(a)
            if not na:
                continue
            if _should_promote(na):
                na["status"] = "compiled"
                na["confidence"] = max(float(na.get("confidence") or 0.6), 0.8)
                promoted += 1
                changed = True
            new_abs.append(na)

        # Add any fresh template timings we fully compile that library lacked.
        have = {a.get("timing") for a in new_abs}
        for timing, fr in fresh_by.items():
            if timing not in have:
                new_abs.append(fr)
                changed = True
                templated += 1

        if changed:
            cards[cid] = normalize_card_entry(cid, {"version": 1, "abilities": new_abs})

    print(
        json.dumps(
            {
                "promoted_to_compiled": promoted,
                "stripped_unsupported": stripped,
                "filled_restriction_ops": filled,
                "template_upgrades": templated,
            },
            ensure_ascii=False,
        )
    )

    if args.dry_run:
        return 0

    lib_path, _ = library_paths()
    payload = {
        "version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cards": cards,
    }
    lib_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    reload_effect_library(force=True)
    print(f"Wrote {lib_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
