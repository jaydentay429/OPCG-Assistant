#!/usr/bin/env python3
"""Batch AW: Krieg / East Blue / cost-area DON!! / Kuro end-turn fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

EAST = "East Blue|東方藍|东方蓝"
KRIEG = "Krieg|克利克"
OUTCOME = (
    "The Outcome Will Tell Us Who's Strong and Who's Weak|"
    "是強是弱讓結果來決定|"
    "是强是弱让结果来决定"
)


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
        "OP15-001",
        [
            {
                "timing": "opponent_turn",
                "summary": "DON!!×1: if all own Characters are East Blue, all opp Characters −2000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -2000,
                        "target_kind": "opponent_character",
                        "optional": False,
                        "all": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 1,
                "require_all_chars_trait": EAST,
            },
            {
                "timing": "activate_main",
                "summary": "Once: rest up to 1 opp Character with ≥2 DON!! attached",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "don_attached_gte": 2,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
        ],
    )

    # OP15-009 — already correct from AU; rewrite to keep variants synced.
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
        "OP15-011",
        [
            {
                "timing": "opponent_turn",
                "summary": "If Leader East Blue: gain Blocker and +2000",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    },
                    {"op": "buff_self", "amount": 2000},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": EAST,
            },
            {
                "timing": "on_ko",
                "summary": "If Leader East Blue: KO up to 1 opp base≤6000",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "base_power_lte": 6000,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": EAST,
            },
        ],
    )

    alvida_morgan_activate = {
        "timing": "activate_main",
        "summary": "Once: attach 1 opp rested DON!! to opp Character: attach up to 1 rested DON!! to owner's Leader/Character",
        "ops": [
            {
                "op": "attach_don",
                "count": 1,
                "as_rested": True,
                "as_cost": True,
                "from_rested": True,
                "target_kind": "opponent_character",
                "optional": True,
                "from_owner": "opponent",
            },
            {
                "op": "attach_don",
                "count": 1,
                "as_rested": True,
                "from_rested": True,
                "target_kind": "opponent_leader_or_character",
                "optional": True,
                "from_owner": "opponent",
            },
        ],
        "status": "compiled",
        "confidence": 0.95,
        "once": True,
    }

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-003",
        [
            {
                "timing": "your_turn",
                "summary": "If this would be KO'd: trash 1 hand Character power≤6000 instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "ko",
                        "target": "self",
                        "cost": "trash_hand",
                        "count": 1,
                        "power_lte": 6000,
                        "card_type": "character",
                        "hand_card_type": "character",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "If this would be KO'd: trash 1 hand Character power≤6000 instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "ko",
                        "target": "self",
                        "cost": "trash_hand",
                        "count": 1,
                        "power_lte": 6000,
                        "card_type": "character",
                        "hand_card_type": "character",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            dict(alvida_morgan_activate),
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-017",
        [dict(alvida_morgan_activate)],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-007",
        [
            {
                "timing": "on_play",
                "summary": "If Leader East Blue: play up to 1 Character cost≤5 from hand",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "from_zone": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": EAST,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-008",
        [
            {
                "timing": "on_play",
                "summary": "Attach up to 3 opp rested DON!! to 1 opp Character; Then gain Rush this turn",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 3,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "from_owner": "opponent",
                    },
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once if played this turn: all opp Characters −1000 per DON!! on this",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -1000,
                        "target_kind": "opponent_character",
                        "optional": False,
                        "all": True,
                        "duration": "turn",
                        "per_don_attached": 1,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_played_this_turn": True,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-026",
        [
            {
                "timing": "on_play",
                "summary": "Look top 3; add up to 1 East Blue",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": EAST,
                        "top_n": 3,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "You may trash this: attach up to 1 opp rested DON!! to 1 opp Character",
                "ops": [
                    {
                        "op": "trash",
                        "target_kind": "self",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "from_owner": "opponent",
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
        "OP15-028",
        [
            {
                "timing": "on_play",
                "summary": "If Leader East Blue: attach up to 1 opp cost-area DON!! to 1 opp Character",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "from_cost_area": True,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "from_owner": "opponent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": EAST,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-023",
        [
            {
                "timing": "on_ko",
                "summary": "Up to 2 opp rested cards skip next Refresh",
                "ops": [
                    {
                        "op": "skip_untap",
                        "count": 2,
                        "target_kind": "opponent_character_rested",
                        "optional": True,
                        "include_leader": True,
                        "include_don": True,
                        "include_stage": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: attach 1 opp rested DON!! to opp Character: attach up to 1 cost-area DON!! to owner's Leader/Character",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "as_cost": True,
                        "from_rested": True,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "from_owner": "opponent",
                    },
                    {
                        "op": "attach_don",
                        "count": 1,
                        "from_cost_area": True,
                        "target_kind": "opponent_leader_or_character",
                        "optional": True,
                        "from_owner": "opponent",
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
        "OP15-027",
        [
            {
                "timing": "on_play",
                "summary": "Rest up to 1 opp Character with DON!! attached",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "don_attached_gte": 1,
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
        "OP15-025",
        [
            {
                "timing": "on_play",
                "summary": "Attach up to 2 opp cost-area DON!! to 1 opp Character; Then at turn end skip-untap 1 rested with ≥3 DON!!",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 2,
                        "from_cost_area": True,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "from_owner": "opponent",
                    },
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "opponent_character_rested",
                        "don_attached_gte": 3,
                        "optional": True,
                        "at_end_of_turn": True,
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-037",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5; add up to 1 East Blue other than this event",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": EAST,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": OUTCOME,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-038",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 opp rested cost≤8 with ≥2 DON!! skips next Refresh",
                "ops": [
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "opponent_character_rested",
                        "cost_lte": 8,
                        "don_attached_gte": 2,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "Up to 1 own Krieg +4000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 4000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "count": 1,
                        "name_contains": KRIEG,
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
                "summary": "All opp rested Characters cost≤7 skip next Refresh",
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

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_aw updated {n} card entries")


if __name__ == "__main__":
    main()
