#!/usr/bin/env python3
"""Batch Y: Zoro/Slash package, Kaido attach-opp-DON, Kin'emon cost, etc."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

ZORO = "Roronoa Zoro|羅羅亞・索隆|罗罗亚・索隆"
SLASH = "Slash|斬|斩"
SUPERNOVAS = "Supernovas|超新星"
CAVENDISH = "Cavendish|卡文迪許|卡文迪许"
FILM_SH = "FILM|Straw Hat Crew|草帽一行人"
PERONA = "Perona|培羅娜|培罗娜"


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


def _opp_don_activate() -> dict[str, Any]:
    """OP15-003/017/023: give opp rested DON to opp Character, then attach from owner's cost."""
    return {
        "timing": "activate_main",
        "summary": "[Once] Give 1 opp rested DON!! to opp Character: then attach 1 from owner's cost to their Leader/Character",
        "ops": [
            {
                "op": "attach_don",
                "count": 1,
                "as_cost": True,
                "from_rested": True,
                "as_rested": True,
                "target_kind": "opponent_character",
                "optional": True,
                "from_owner": "opponent",
            },
            {
                "op": "attach_don",
                "count": 1,
                "from_rested": True,
                "as_rested": True,
                "target_kind": "opponent_leader_or_character",
                "optional": True,
                "from_owner": "opponent",
            },
        ],
        "status": "compiled",
        "confidence": 0.95,
        "once": True,
        "cost_don": 0,
        "rest_self": False,
    }


def main() -> None:
    ov_path, lib_path = library_paths()
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    ov = json.loads(ov_path.read_text())
    lib = json.loads(lib_path.read_text())
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    n = 0

    # OP12-020 Zoro Leader — keep arm + cannot attack
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-020",
        [
            {
                "timing": "activate_main",
                "summary": "[DON!!×3][Once] Untap if battles Character; cannot attack base-cost≤7 Characters",
                "ops": [
                    {"op": "arm_untap_on_char_battle"},
                    {"op": "cannot_attack_char_base_cost_lte", "count": 7, "duration": "turn"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
                "require_don_attached_gte": 3,
            },
        ],
    )

    # EB01-012 Cavendish
    cav = {
        "require_leader_trait": SUPERNOVAS,
        "require_no_other_name": CAVENDISH,
        "ops": [{"op": "active_don", "count": 2, "optional": True}],
        "status": "compiled",
        "confidence": 0.95,
        "summary": "If Leader Supernovas and no other Cavendish: active up to 2 DON!!",
    }
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB01-012",
        [
            {"timing": "on_play", **cav},
            {"timing": "when_attacking", **cav},
        ],
    )

    # OP12-028 Hiyori
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-028",
        [
            {
                "timing": "activate_main",
                "summary": "Rest 1 DON!! + this: if Leader Zoro, search top 5 Slash or green Event",
                "ops": [
                    {"op": "rest_don", "count": 1, "owner": "self", "as_cost": True, "optional": True},
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
                        "attr_contains": SLASH,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": True,
                "once": False,
                "require_leader_name": ZORO,
            },
        ],
    )

    # OP12-031 Tashigi — rest base cost≤6, attach rested DON to Zoro Leader
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-031",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Rest up to 1 opp base-cost≤6; attach up to 3 rested DON!! to Zoro Leader",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "base_cost_lte": 6,
                        "optional": True,
                    },
                    {
                        "op": "attach_don",
                        "count": 3,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "leader",
                        "optional": True,
                        "name_contains": ZORO,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP12-026 Kuina — same attach-to-Zoro-Leader pattern (already leader; ensure base_cost)
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-026",
        [
            {
                "timing": "activate_main",
                "summary": "Rest this: rest opp base-cost≤4; attach up to 3 rested DON!! to Zoro Leader",
                "ops": [
                    {"op": "rest_character", "target_kind": "self", "optional": True, "as_cost": True},
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "base_cost_lte": 4,
                        "optional": True,
                    },
                    {
                        "op": "attach_don",
                        "count": 3,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "leader",
                        "optional": True,
                        "name_contains": ZORO,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": False,
            },
        ],
    )

    # OP12-034 Perona
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-034",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If Leader Slash: search top 5 Slash or green Event",
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
                        "attr_contains": SLASH,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_attribute": SLASH,
            },
        ],
    )

    # OP12-037
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-037",
        [
            {
                "timing": "on_play",
                "summary": "[Main] May rest 3 DON!!: rest up to 2 total opp Characters or DON!!",
                "ops": [
                    {"op": "rest_don", "count": 3, "owner": "self", "as_cost": True, "optional": True},
                    {"op": "rest_opponent_char_or_don", "count": 2, "optional": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "[Counter] Leader +3000 this battle",
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

    # OP12-039
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-039",
        [
            {
                "timing": "on_play",
                "summary": "[Main] Set your Zoro Leader active",
                "ops": [
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "leader",
                        "optional": False,
                        "name_contains": ZORO,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "[Trigger] Up to 1 own Leader/Character +1000 this turn",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 1000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP13-031 Law — already good; reaffirm
    blocker = {
        "require_life_lte": 1,
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
        "summary": "If Life≤1: gains Blocker",
    }
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-031",
        [
            {"timing": "your_turn", **blocker},
            {"timing": "opponent_turn", **blocker},
            {
                "timing": "on_play",
                "summary": "[On Play] May return 1 own Character: play cost≤5 from hand rested",
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

    # OP13-037 Zoro
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-037",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If Leader FILM/Straw Hat: active up to 2 DON!!",
                "ops": [{"op": "active_don", "count": 2, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": FILM_SH,
            },
            {
                "timing": "end_of_your_turn",
                "summary": "[End of Your Turn] Set this Character active",
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

    # OP13-040
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-040",
        [
            {
                "timing": "on_play",
                "summary": "[Main] May rest 2 DON!!: up to 2 opp rested cost≤7 skip next Refresh",
                "ops": [
                    {"op": "rest_don", "count": 2, "owner": "self", "as_cost": True, "optional": True},
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
                "summary": "[Counter] Leader +3000 this battle",
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

    # OP14-023
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-023",
        [
            {
                "timing": "end_of_your_turn",
                "summary": "[End of Your Turn] Set this Character active",
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

    # OP15-023 Kaido
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-023",
        [
            {
                "timing": "on_ko",
                "summary": "[On K.O.] Up to 2 opp rested cards skip next Refresh",
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
            _opp_don_activate(),
        ],
    )

    # Similar OP15-003 / OP15-017 activate
    for cid, extras in (
        (
            "OP15-003",
            [
                {
                    "timing": "your_turn",
                    "summary": "If would be KO'd: may trash hand Character power≤6000 instead",
                    "ops": [
                        {
                            "op": "replace_leave",
                            "trigger": "ko",
                            "target": "self",
                            "cost": "trash_hand",
                            "life_position": "top",
                            "power_lte": 6000,
                            "card_type": "character",
                            "optional": True,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
                {
                    "timing": "opponent_turn",
                    "summary": "If would be KO'd: may trash hand Character power≤6000 instead",
                    "ops": [
                        {
                            "op": "replace_leave",
                            "trigger": "ko",
                            "target": "self",
                            "cost": "trash_hand",
                            "life_position": "top",
                            "power_lte": 6000,
                            "card_type": "character",
                            "optional": True,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
            ],
        ),
        (
            "OP15-017",
            [],  # Blocker is keyword on card; activate only
        ),
    ):
        abs_ = list(extras) + [_opp_don_activate()]
        n += _write(ov_cards, lib_cards, catalog, cid, abs_)

    # OP15-035 Laboon — 「自己的卡片」rest 2
    replace = {
        "op": "replace_leave",
        "trigger": "opp_remove",
        "target": "own_filtered",
        "cost": "rest_own",
        "rest_count": 2,
        "life_position": "top",
        "base_power_lte": 7000,
        "optional": True,
    }
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-035",
        [
            {
                "timing": "your_turn",
                "summary": "If own base≤7000 would leave by opp effect: may rest 2 cards instead",
                "ops": [replace],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "If own base≤7000 would leave by opp effect: may rest 2 cards instead",
                "ops": [replace],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # ST32-001 Kin'emon — rest Slash Leader OR 1 DON!!
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST32-001",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] May rest Slash Leader or 1 DON!!: draw 2, trash 1",
                "ops": [
                    {
                        "op": "choose_one",
                        "chooser": "self",
                        "optional": True,
                        "as_cost": True,
                        "summary": "休息斬屬性領航卡或1張咚‼",
                        "options": [
                            {
                                "id": "leader",
                                "label": "休息斬屬性領航卡",
                                "require_leader_attribute": SLASH,
                                "require_leader_active": True,
                                "ops": [
                                    {
                                        "op": "rest_character",
                                        "target_kind": "leader",
                                        "optional": False,
                                        "as_cost": True,
                                    }
                                ],
                            },
                            {
                                "id": "don",
                                "label": "休息1張咚‼",
                                "require_don_active_gte": 1,
                                "ops": [
                                    {
                                        "op": "rest_don",
                                        "count": 1,
                                        "owner": "self",
                                        "as_cost": True,
                                        "optional": False,
                                    }
                                ],
                            },
                        ],
                    },
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # ST32-002 Oden — base cost≤6 deny rest
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST32-002",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Draw 1; up to 1 opp base-cost≤6 cannot be rested until opp End",
                "ops": [
                    {"op": "draw", "count": 1},
                    {
                        "op": "deny_rest",
                        "count": 1,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "base_cost_lte": 6,
                        "duration": "until_opp_turn_end",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # ST32-003 Mihawk
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST32-003",
        [
            {
                "timing": "your_turn",
                "summary": "[Your Turn] When this becomes rested: draw 1, trash 1",
                "ops": [
                    {"op": "draw", "count": 1},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "trigger_on": "self_rested",
            },
            {
                "timing": "on_play",
                "summary": "[On Play] If Leader Slash: play cost≤5 Slash or Perona from hand",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "name_contains": PERONA,
                        "attribute": SLASH,
                        "name_or_attribute": True,
                        "from_zone": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_attribute": SLASH,
            },
        ],
    )

    # ST32-005 Zoro
    rush = {
        "ops": [
            {
                "op": "grant_keyword",
                "keyword": "rush_character",
                "target_kind": "self",
                "duration": "permanent",
                "summary": "Rush: Character",
            }
        ],
        "status": "compiled",
        "confidence": 0.95,
        "summary": "Rush: Character",
    }
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST32-005",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If Leader Slash: rest up to 1 opp cost≤2",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 2,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_attribute": SLASH,
            },
            {"timing": "your_turn", **rush},
            {"timing": "opponent_turn", **rush},
        ],
    )

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_y wrote {n} card entries")


if __name__ == "__main__":
    main()
