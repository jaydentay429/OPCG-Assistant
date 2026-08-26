#!/usr/bin/env python3
"""Batch BA: ODYSSEY / rested-chars Then-if / Lim search gate fixes."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

ODYSSEY = "ODYSSEY"
LIM = "Lim|莉姆|リム"


def _variants(catalog: dict[str, Any], base: str) -> list[str]:
    out = [base]
    out.extend(sorted(k for k in catalog if k.startswith(base + "-")))
    return [c for c in out if c in catalog or c == base]


def _write(ov_cards: dict, lib_cards: dict, catalog: dict, cid: str, abilities: list[dict[str, Any]]) -> int:
    n = 0
    for vid in _variants(catalog, cid):
        entry = normalize_card_entry(vid, {"version": 1, "abilities": abilities})
        ov_cards[vid] = entry
        lib_cards[vid] = {**entry, "card_id": vid}
        n += 1
    return n


def main() -> None:
    ov_path, lib_path = library_paths()
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    ov = json.loads(ov_path.read_text())
    lib = json.loads(lib_path.read_text())
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    n = 0

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-022",
        [
            {
                "timing": "your_turn",
                "summary": "Your Characters are played rested",
                "ops": [{"op": "play_characters_rested"}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "Your Characters are played rested",
                "ops": [{"op": "play_characters_rested"}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: rest 3 DON!!: gain 1 rested DON!! + play up to 1 ODYSSEY cost≤5 from hand",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 3,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {"op": "gain_don", "count": 1, "as_rested": True, "optional": True},
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "trait_contains": ODYSSEY,
                        "from_zone": "hand",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-037",
        [
            {
                "timing": "your_turn",
                "summary": "Once: instead of leaving by opp effect, rest 1 ODYSSEY Character",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "self",
                        "cost": "rest_other_character",
                        "rest_count": 1,
                        "rest_trait_contains": ODYSSEY,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
            {
                "timing": "opponent_turn",
                "summary": "Once: instead of leaving by opp effect, rest 1 ODYSSEY Character",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "self",
                        "cost": "rest_other_character",
                        "rest_count": 1,
                        "rest_trait_contains": ODYSSEY,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
            {
                "timing": "end_of_your_turn",
                "summary": "Set up to 1 own ODYSSEY Character as active",
                "ops": [
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "own_character",
                        "optional": True,
                        "trait_contains": ODYSSEY,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-023",
        [
            {
                "timing": "end_of_your_turn",
                "summary": "Set this Character as active",
                "ops": [
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "self",
                        "optional": False,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP09-037 — search ungated; end-of-turn active if 3+ rested.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-037",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5; add up to 1 ODYSSEY other than Lim; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": ODYSSEY,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": LIM,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "end_of_your_turn",
                "summary": "If 3+ rested own Characters: set this as active",
                "ops": [
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "self",
                        "optional": False,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_rested_own_chars_gte": 3,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "P-078",
        [
            {
                "timing": "your_turn",
                "summary": "If 2+ rested ODYSSEY Characters: this +1000",
                "ops": [{"op": "buff_self", "amount": 1000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_rested_own_chars_gte": 2,
                "require_rested_own_chars_trait": ODYSSEY,
            },
            {
                "timing": "opponent_turn",
                "summary": "If 2+ rested ODYSSEY Characters: this +1000",
                "ops": [{"op": "buff_self", "amount": 1000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_rested_own_chars_gte": 2,
                "require_rested_own_chars_trait": ODYSSEY,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-027",
        [
            {
                "timing": "when_attacking",
                "summary": "Once: if 3+ rested own Characters, draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_rested_own_chars_gte": 3,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-031",
        [
            {
                "timing": "end_of_your_turn",
                "summary": "If 2+ rested own Characters: set this as active",
                "ops": [
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "self",
                        "optional": False,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_rested_own_chars_gte": 2,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-035",
        [
            {
                "timing": "on_play",
                "summary": "If 2+ rested own Characters: rest up to 1 opp Character cost≤5",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 5,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_rested_own_chars_gte": 2,
            },
        ],
    )

    # OP10-024 — rest gated; Then KO rested cost≤3 ungated.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-024",
        [
            {
                "timing": "on_play",
                "summary": "If 2+ rested: rest up to 1 opp cost≤5; Then KO up to 1 opp rested cost≤3",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 5,
                        "optional": True,
                        "require_rested_own_chars_gte": 2,
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character_rested",
                        "optional": True,
                        "cost_lte": 3,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-025",
        [
            {
                "timing": "on_play",
                "summary": "If 2+ rested own Characters: draw 3 trash 2",
                "ops": [
                    {"op": "draw", "count": 3},
                    {
                        "op": "trash_hand",
                        "count": 2,
                        "optional": False,
                        "owner": "self",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_rested_own_chars_gte": 2,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-029",
        [
            {
                "timing": "on_play",
                "summary": "If 2+ rested: set up to 1 own rested ODYSSEY cost≤5 as active",
                "ops": [
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "own_character",
                        "optional": True,
                        "trait_contains": ODYSSEY,
                        "cost_lte": 5,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_rested_own_chars_gte": 2,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-028",
        [
            {
                "timing": "on_play",
                "summary": "Set all DON!! active; Then cannot play from hand this turn",
                "ops": [
                    {"op": "active_don", "count": 10, "all": True},
                    {
                        "op": "cannot_play_from_hand",
                        "duration": "turn",
                        "card_type": "any",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-037",
        [
            {
                "timing": "on_play",
                "summary": "If DON!! field≥7: all own ODYSSEY Leader+Characters +1000 until opp end",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 1000,
                        "target_kind": "own_leader_or_character",
                        "optional": False,
                        "all": True,
                        "include_leader": True,
                        "trait_contains": ODYSSEY,
                        "duration": "until_opp_turn_end",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_gte": 7,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-041",
        [
            {
                "timing": "counter_event",
                "summary": "Up to 1 own Leader/Character +2000 this battle; Then if ODYSSEY Leader + 2+ rested, active up to 2",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    },
                    {
                        "op": "set_character_active",
                        "count": 2,
                        "target_kind": "own_character",
                        "optional": True,
                        "require_rested_own_chars_gte": 2,
                        "require_leader_trait": ODYSSEY,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Rest up to 1 opp Character cost≤4",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 4,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-037",
        [
            {
                "timing": "on_play",
                "summary": "Rest 3 DON!!: rest up to 2 opp Characters or DON!!",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 3,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "rest_opponent_char_or_don",
                        "count": 2,
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "Leader +3000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "leader",
                        "optional": False,
                        "duration": "battle",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP08-036",
        [
            {
                "timing": "on_play",
                "summary": "All opp rested Characters cost≤7 skip untap next Refresh",
                "ops": [
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "opponent_character_rested",
                        "cost_lte": 7,
                        "optional": False,
                        "all": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Rest up to 1 opp Character",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Soft-fix: 「若…休息…時，A。之後，B」on_play — gate only first op.
    then_rested = re.compile(
        r"【登場時】若場上有(\d+)張以上自己休息狀態的角色卡時，.{2,80}。之後，"
    )
    for cid, entry in list(ov_cards.items()):
        info = catalog.get(cid) or {}
        zh = str(info.get("effect") or "")
        m = then_rested.search(zh)
        if not m:
            continue
        need = int(m.group(1))
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            if ab.get("timing") != "on_play":
                abs_out.append(ab)
                continue
            ops = [dict(o) for o in (ab.get("ops") or [])]
            if len(ops) < 2:
                abs_out.append(ab)
                continue
            if ab.get("require_rested_own_chars_gte") is not None:
                ab.pop("require_rested_own_chars_gte", None)
                changed = True
            if not ops[0].get("require_rested_own_chars_gte"):
                ops[0]["require_rested_own_chars_gte"] = need
                changed = True
            ab["ops"] = ops
            abs_out.append(ab)
        if changed:
            entry2 = normalize_card_entry(
                cid, {"version": int(entry.get("version") or 1), "abilities": abs_out}
            )
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    # Soft-fix: end_of_your_turn missing rested gate when paper has it; on_play wrongly has it.
    eoy_rested = re.compile(
        r"【我方回合結束時】若場上有(\d+)張以上自己休息狀態的角色卡時"
    )
    for cid, entry in list(ov_cards.items()):
        info = catalog.get(cid) or {}
        zh = str(info.get("effect") or "")
        m = eoy_rested.search(zh)
        if not m:
            continue
        need = int(m.group(1))
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            if ab.get("timing") == "on_play" and ab.get("require_rested_own_chars_gte") is not None:
                # Only strip if on_play body doesn't require rested
                body = ""
                mm = re.search(r"【登場時】([^【]+)", zh)
                if mm:
                    body = mm.group(1)
                if "休息" not in body:
                    ab.pop("require_rested_own_chars_gte", None)
                    changed = True
            if ab.get("timing") == "end_of_your_turn":
                if ab.get("require_rested_own_chars_gte") is None:
                    ab["require_rested_own_chars_gte"] = need
                    changed = True
            abs_out.append(ab)
        if changed:
            entry2 = normalize_card_entry(
                cid, {"version": int(entry.get("version") or 1), "abilities": abs_out}
            )
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_ba updated {n} card entries")


if __name__ == "__main__":
    main()
