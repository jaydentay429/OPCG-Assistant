#!/usr/bin/env python3
"""Batch AU: Smoker aura / Koby replace_leave / Then active_don / innate Blocker fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402
from battle.effects import detect_keywords  # noqa: E402

NAVY_PH = "Navy|Punk Hazard|海軍|龐克哈薩特|庞克哈萨特"
NAVY = "Navy|海軍"


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
        "OP10-001",
        [
            {
                "timing": "opponent_turn",
                "summary": "All own Navy or Punk Hazard Characters +1000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 1000,
                        "target_kind": "own_character",
                        "optional": False,
                        "all": True,
                        "trait_contains": NAVY_PH,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: if own Character power≥7000, set up to 2 DON!! active",
                "ops": [{"op": "active_don", "count": 2, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_char_power_gte": 7000,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-004",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5; add up to 1 Navy other than Kujyaku",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": NAVY,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": "Kujyaku|孔雀",
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "You may trash this: up to 1 own Character +1000 this turn",
                "ops": [
                    {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                    {
                        "op": "buff",
                        "amount": 1000,
                        "target_kind": "own_character",
                        "optional": True,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-009 — shield any own base≤7000 Char; cost Leader −2000; not once; not trash_life.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-009",
        [
            {
                "timing": "your_turn",
                "summary": "If own Character base≤7000 would leave by opp effect: Leader −2000 instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "self_power_minus",
                        "amount": -2000,
                        "apply_to": "leader",
                        "base_power_lte": 7000,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "If own Character base≤7000 would leave by opp effect: Leader −2000 instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "self_power_minus",
                        "amount": -2000,
                        "apply_to": "leader",
                        "base_power_lte": 7000,
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
        "OP10-011",
        [
            {
                "timing": "opponent_turn",
                "summary": "This Character +2000",
                "ops": [{"op": "buff_self", "amount": 2000}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-008",
        [
            {
                "timing": "on_play",
                "summary": "You may trash 1: if Leader Navy, up to 1 opp Character −6000",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "buff",
                        "amount": -6000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "require_leader_trait": NAVY,
                        "duration": "turn",
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
        "PRB02-001",
        [
            {
                "timing": "opponent_turn",
                "summary": "If Leader Navy: this +1000",
                "ops": [{"op": "buff_self", "amount": 1000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": NAVY,
            },
            {
                "timing": "when_attacking",
                "summary": "KO up to 1 opp base≤3000; Then if hand≤6 draw 1",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "base_power_lte": 3000,
                    },
                    {"op": "draw", "count": 1, "require_hand_lte": 6},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Vanilla — no effect text.
    for vanilla in ("OP11-017", "OP13-036"):
        n += _write(ov_cards, lib_cards, catalog, vanilla, [])

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-034",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Slash: look top 5; add up to 1 Slash or green Event",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "or_event": True,
                        "color": "green",
                        "attr_contains": "Slash|斬|斩",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_attribute": "Slash|斬|斩",
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-026",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 opp rested Character or DON!! skips next Refresh",
                "ops": [
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "opponent_character_or_don_rested",
                        "optional": True,
                        "include_don": True,
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
        "OP10-030",
        [
            {
                "timing": "activate_main",
                "summary": "Set up to 1 DON!! active; Then cannot active DON!! by Character effects this turn",
                "ops": [
                    {"op": "active_don", "count": 1, "optional": True},
                    {"op": "cannot_active_don_by_character", "duration": "turn"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP12-118 — Then active_don ungated.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-118",
        [
            {
                "timing": "on_play",
                "summary": "If rested cards≥8: draw 2 trash 1; Then set up to 1 DON!! active",
                "ops": [
                    {"op": "draw", "count": 2, "require_rested_cards_gte": 8},
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": False,
                        "owner": "self",
                        "require_rested_cards_gte": 8,
                    },
                    {"op": "active_don", "count": 1, "optional": True},
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
        "OP13-031",
        [
            {
                "timing": "your_turn",
                "summary": "If Life≤1: gain Blocker",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 1,
            },
            {
                "timing": "opponent_turn",
                "summary": "If Life≤1: gain Blocker",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 1,
            },
            {
                "timing": "on_play",
                "summary": "You may return 1 own Character: play up to 1 cost≤5 from hand rested",
                "ops": [
                    {
                        "op": "return_to_hand",
                        "target_kind": "own_character",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "as_rested": True,
                        "from_zone": "hand",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP12-030 — Blocker innate; do not grant_keyword.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-030",
        [
            {
                "timing": "on_play",
                "summary": "Set up to 4 DON!! active; Then cannot play base cost≥7 Characters this turn",
                "ops": [
                    {"op": "active_don", "count": 4, "optional": True},
                    {
                        "op": "cannot_play_from_hand",
                        "duration": "turn",
                        "card_type": "character",
                        "base_cost_gte": 7,
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
        "ST24-004",
        [
            {
                "timing": "on_play",
                "summary": "Rest up to 1 opp Character + skip untap; Then if opp rested≥2, Leader +2000 until opp end",
                "ops": [
                    {
                        "op": "rest_character",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 1,
                        "also_skip_untap": True,
                    },
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "leader",
                        "optional": False,
                        "require_opp_rested_chars_gte": 2,
                        "duration": "until_opp_turn_end",
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
        "OP12-037",
        [
            {
                "timing": "on_play",
                "summary": "You may rest 3 DON!!: rest up to 2 total opp Characters or DON!!",
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
        "OP13-040",
        [
            {
                "timing": "on_play",
                "summary": "You may rest 2 DON!!: up to 2 opp rested cost≤7 Characters skip next Refresh",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 2,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "skip_untap",
                        "count": 2,
                        "target_kind": "opponent_character_rested",
                        "cost_lte": 7,
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

    # Similar Then-if (ST11-004): Uta-gated search; Then active_don ungated.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST11-004",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Uta: look top 3 add FILM; Then set up to 1 DON!! active",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "FILM",
                        "top_n": 3,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": "New Genesis|新時代|新时代",
                        "destination": "hand",
                        "reveal_adds": True,
                        "require_leader_name": "Uta|美音",
                    },
                    {"op": "active_don", "count": 1, "optional": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Soft-fix: strip bogus permanent grant_keyword blocker when innate.
    for cid, entry in list(ov_cards.items()):
        info = catalog.get(cid) or {}
        zh = str(info.get("effect") or "")
        en = str(info.get("effect_en") or "")
        if "獲得【防禦】" in zh or "gains [Blocker]" in en or "gains【Blocker】" in en:
            continue
        if "blocker" not in detect_keywords(info):
            continue
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ops = ab.get("ops") or []
            if (
                len(ops) == 1
                and ops[0].get("op") == "grant_keyword"
                and ops[0].get("keyword") == "blocker"
                and ops[0].get("duration") == "permanent"
                and ab.get("timing") in {"your_turn", "opponent_turn"}
                and not any(str(k).startswith("require_") for k in ab)
            ):
                changed = True
                continue
            abs_out.append(ab)
        if changed:
            entry2 = normalize_card_entry(
                cid, {"version": int(entry.get("version") or 1), "abilities": abs_out}
            )
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    # Soft-fix: Then active_don wrongly ability-gated — only move op-safe gates.
    _OP_SAFE_GATES = {
        "require_rested_cards_gte",
        "require_don_field_gte",
        "require_don_field_lte",
        "require_leader_name",
        "require_leader_trait",
        "require_hand_lte",
        "require_hand_gte",
    }
    for cid, entry in list(ov_cards.items()):
        info = catalog.get(cid) or {}
        zh = str(info.get("effect") or "")
        if "之後" not in zh or "置為活動狀態" not in zh or "若" not in zh:
            continue
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            if ab.get("timing") != "on_play":
                abs_out.append(ab)
                continue
            gates = {
                k: ab[k]
                for k in list(ab)
                if str(k).startswith("require_") and k in _OP_SAFE_GATES
            }
            if not gates:
                abs_out.append(ab)
                continue
            ops = ab.get("ops") or []
            if not any(o.get("op") == "active_don" for o in ops):
                abs_out.append(ab)
                continue
            new_ops = []
            for o in ops:
                o = dict(o)
                if o.get("op") != "active_don":
                    for gk, gv in gates.items():
                        o.setdefault(gk, gv)
                    changed = True
                new_ops.append(o)
            for gk in gates:
                ab.pop(gk, None)
            ab["ops"] = new_ops
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
    print(f"batch_au updated {n} card entries")


if __name__ == "__main__":
    main()
