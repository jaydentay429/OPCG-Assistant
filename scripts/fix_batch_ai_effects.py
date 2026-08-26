#!/usr/bin/env python3
"""Batch AI: Straw Hat mill / Then-if gate / innate Blocker effect fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

SH = "Straw Hat Crew|草帽一行人"
CHOPPER = "Tony Tony.Chopper|多尼多尼・喬巴|托尼托尼・乔巴"
LUFFY = "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫"
IMPEL = "Impel Down|推進城|推进城"
NAMI = "Nami|娜美"
WB = "Whitebeard Pirates|白鬍子海賊團"


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

    # OP15-022 Brook Leader — keep structure.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-022",
        [
            {
                "timing": "your_turn",
                "summary": "Do not lose on deck-out; lose at end of turn when deck is 0",
                "ops": [{"op": "rule_deckout_end_of_turn"}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: trash 4; if deck 0, set up to 1 Character active",
                "ops": [
                    {"op": "trash_deck_top", "count": 4, "optional": False},
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "own_character",
                        "optional": True,
                        "require_deck_lte": 0,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
            },
        ],
    )

    # OP15-081 Sanji.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-081",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Straw Hat Crew: trash 5 from deck",
                "ops": [{"op": "trash_deck_top", "count": 5, "optional": False}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": SH,
            },
        ],
    )

    # OP15-083 Spoiler — on_play always trash 3; activate trash self if trash≥15 attach.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-083",
        [
            {
                "timing": "on_play",
                "summary": "Trash 3 from deck",
                "ops": [{"op": "trash_deck_top", "count": 3, "optional": False}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "May trash this: if trash≥15, attach up to 1 rested DON!!",
                "ops": [
                    {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "require_trash_gte": 15,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": False,
                "once": False,
            },
        ],
    )

    # OP15-085 Chopper.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-085",
        [
            {
                "timing": "on_play",
                "summary": "Trash 3 from deck",
                "ops": [{"op": "trash_deck_top", "count": 3, "optional": False}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "May trash this: if Leader SH, add up to 1 SH Character other than Chopper from trash",
                "ops": [
                    {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                    {
                        "op": "add_from_trash",
                        "count": 1,
                        "optional": True,
                        "name_exclude": CHOPPER,
                        "trait_contains": SH,
                        "card_type": "character",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": False,
                "once": False,
                "require_leader_trait": SH,
            },
        ],
    )

    # OP15-088 Pirate Union — +6 cost continuous; trash 3 as cost play SH cost≤2 from trash.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-088",
        [
            {
                "timing": "your_turn",
                "summary": "This Character gains +6 cost",
                "ops": [{"op": "grant_cost", "amount": 6, "target_kind": "self"}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "This Character gains +6 cost",
                "ops": [{"op": "grant_cost", "amount": 6, "target_kind": "self"}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_play",
                "summary": "May trash 3: play up to 1 SH Character cost≤2 from trash",
                "ops": [
                    {"op": "trash_deck_top", "count": 3, "optional": True, "as_cost": True},
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 2,
                        "trait_contains": SH,
                        "from_zone": "trash",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-092 Luffy trash thresholds.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-092",
        [
            {
                "timing": "your_turn",
                "summary": "If trash≥10: base power 9000 and +10 cost",
                "ops": [
                    {"op": "set_base_power", "target_kind": "self", "optional": False, "amount": 9000},
                    {"op": "grant_cost", "amount": 10, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_trash_gte": 10,
            },
            {
                "timing": "opponent_turn",
                "summary": "If trash≥10: base power 9000 and +10 cost",
                "ops": [
                    {"op": "set_base_power", "target_kind": "self", "optional": False, "amount": 9000},
                    {"op": "grant_cost", "amount": 10, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_trash_gte": 10,
            },
            {
                "timing": "opponent_turn",
                "summary": "If trash≥20: Leader base power becomes 7000",
                "ops": [{"op": "set_base_power", "target_kind": "leader", "optional": False, "amount": 7000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_trash_gte": 20,
            },
            {
                "timing": "your_turn",
                "summary": "If trash≥30: +1000 power",
                "ops": [{"op": "buff_self", "amount": 1000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_trash_gte": 30,
            },
            {
                "timing": "opponent_turn",
                "summary": "If trash≥30: +1000 power",
                "ops": [{"op": "buff_self", "amount": 1000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_trash_gte": 30,
            },
        ],
    )

    # OP15-086 Nami.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-086",
        [
            {
                "timing": "on_play",
                "summary": "If Leader SH: play up to 1 SH Character cost≤7 from trash with Rush this turn",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 7,
                        "trait_contains": SH,
                        "from_zone": "trash",
                    },
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "own_character",
                        "duration": "turn",
                        "effect_played_only": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": SH,
            },
        ],
    )

    # EB02-017 Nami search.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB02-017",
        [
            {
                "timing": "on_play",
                "summary": "Look 5: add up to 1 SH other than Nami",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": SH,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": NAMI,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # PRB02-006 Zoro — replace_rest only; innate Blocker via keywords.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "PRB02-006",
        [
            {
                "timing": "opponent_turn",
                "summary": "If would be rested by opp Character effect, may rest 1 other Character instead",
                "ops": [
                    {
                        "op": "replace_rest",
                        "target": "self",
                        "cost": "rest_other_character",
                        "optional": True,
                        "summary": "Rest 1 other Character instead of this Character being rested",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP14-031 Nami — innate Blocker; on_play rest + end-turn active DON.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-031",
        [
            {
                "timing": "on_play",
                "summary": "Rest up to 2 opp cost≤8; at end of turn active up to 5 DON!!",
                "ops": [
                    {"op": "rest_opponent_character", "count": 2, "cost_lte": 8, "optional": True},
                    {"op": "active_don", "count": 5, "optional": True, "at_end_of_turn": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-024 Usopp.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-024",
        [
            {
                "timing": "opponent_turn",
                "summary": "Cannot be rested by opp Leader/Character effects; gains Blocker",
                "ops": [
                    {"op": "cannot_be_rested", "target_kind": "self", "optional": False},
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_ko",
                "summary": "Rest up to 1 opp Leader or Character cost≤7",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "include_leader": True,
                        "cost_lte": 7,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-032 Brook.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-032",
        [
            {
                "timing": "on_play",
                "summary": "Rest up to 1 opponent card (Leader/Character/Stage/DON!!)",
                "ops": [
                    {
                        "op": "rest_character",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 1,
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
                "summary": "May trash this: if Leader SH, set up to 1 own base cost≤8 Character active",
                "ops": [
                    {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "own_character",
                        "optional": True,
                        "base_cost_lte": 8,
                        "require_leader_trait": SH,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": False,
                "once": False,
            },
        ],
    )

    # OP15-096 — rest DON ungated; trash if SH.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-096",
        [
            {
                "timing": "on_play",
                "summary": "May rest 1 DON!!: if Leader SH, trash 5 from deck",
                "ops": [
                    {"op": "rest_don", "count": 1, "owner": "self", "as_cost": True, "optional": True},
                    {
                        "op": "trash_deck_top",
                        "count": 5,
                        "optional": False,
                        "require_leader_trait": SH,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "May trash 1: own Leader/Character +3000 this battle",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-095 — rest DON ungated; buff if trash≥15.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-095",
        [
            {
                "timing": "on_play",
                "summary": "May rest 1 DON!!: if trash≥15, own SH Leader/Character +3000 this turn",
                "ops": [
                    {"op": "rest_don", "count": 1, "owner": "self", "as_cost": True, "optional": True},
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "trait_contains": SH,
                        "duration": "turn",
                        "require_trash_gte": 15,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "If trash≥15: own Leader/Character +4000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 4000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_trash_gte": 15,
            },
        ],
    )

    # OP12-037 / OP13-040 / OP08-036 — reaffirm.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-037",
        [
            {
                "timing": "on_play",
                "summary": "May rest 3 DON!!: rest up to 2 opp Characters or DON!!",
                "ops": [
                    {"op": "rest_don", "count": 3, "owner": "self", "as_cost": True, "optional": True},
                    {"op": "rest_opponent_char_or_don", "count": 2, "optional": True},
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
                "summary": "May rest 2 DON!!: up to 2 opp rested cost≤7 skip untap next refresh",
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
                "summary": "All opp rested cost≤7 Characters skip untap next refresh",
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
                "ops": [{"op": "rest_opponent_character", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP16-039 — Double Attack always; rest if Impel Down; trigger Leader only.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-039",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 own Luffy Double Attack; then if Leader Impel Down rest up to 2 opp cost≤3",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "double_attack",
                        "target_kind": "own_character",
                        "name_contains": LUFFY,
                        "duration": "turn",
                        "optional": True,
                        "count": 1,
                    },
                    {
                        "op": "rest_opponent_character",
                        "count": 2,
                        "cost_lte": 3,
                        "optional": True,
                        "require_leader_trait": IMPEL,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Rest opponent's Leader",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "leader_only": True,
                        "optional": False,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Similar Then-if misgates.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-096",
        [
            {
                "timing": "on_play",
                "summary": "Draw 1; then if trash≥10, opp Character −3 cost this turn",
                "ops": [
                    {"op": "draw", "count": 1},
                    {
                        "op": "reduce_cost",
                        "amount": -3,
                        "count": 1,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                        "require_trash_gte": 10,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "KO up to 1 opp Character cost≤3",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 3,
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
        "OP16-101",
        [
            {
                "timing": "on_play",
                "summary": "Own Leader/Character +3000; then if trash≥10 KO up to 1 opp cost≤2",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "turn",
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 2,
                        "require_trash_gte": 10,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Add up to 1 Yamato from trash to hand",
                "ops": [
                    {
                        "op": "add_from_trash",
                        "count": 1,
                        "optional": True,
                        "name_contains": "Yamato|大和",
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
        "OP02-013",
        [
            {
                "timing": "on_play",
                "summary": "Up to 2 opp Characters −3000; then if Leader WB, this gains Rush",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -3000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 2,
                        "duration": "turn",
                    },
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "turn",
                        "require_leader_trait": WB,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Similar rest_don + if trait/trash events.
    for cid, trait, rest_n, second in [
        (
            "OP14-076",
            "Donquixote Pirates|唐吉訶德海賊團",
            2,
            {"op": "gain_don", "count": 1, "as_rested": True, "optional": True},
        ),
        (
            "OP12-117",
            "Supernovas|超新星",
            5,
            {
                "op": "place_on_life",
                "count": 1,
                "owner": "self",
                "position": "top_or_bottom",
                "face": "down",
                "target_kind": "any_character",
                "optional": True,
                "cost_lte": 9,
            },
        ),
        (
            "OP16-070",
            "Navy|海軍",
            2,
            {"op": "gain_don", "count": 1, "as_rested": True, "optional": True},
        ),
    ]:
        second = dict(second)
        second["require_leader_trait"] = trait
        abs_ = [
            {
                "timing": "on_play",
                "summary": f"May rest {rest_n} DON!!: if Leader has trait, resolve effect",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": rest_n,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    second,
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ]
        # Keep counter / blocker extras from existing when present.
        old = ov_cards.get(cid) or lib_cards.get(cid) or {}
        for a in old.get("abilities") or []:
            if a.get("timing") in {"counter_event", "your_turn", "opponent_turn"} and a.get("timing") != "on_play":
                # Preserve non-main extras (e.g. counter, innate-ish).
                if a.get("timing") == "counter_event":
                    abs_.append(a)
        # OP16-070 / OP14-076 may have Blocker keyword only — leave empty extras.
        if cid == "OP14-076":
            abs_.append(
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
                }
            )
        if cid == "OP12-117":
            abs_.append(
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
                }
            )
        n += _write(ov_cards, lib_cards, catalog, cid, abs_)

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_ai updated entries≈{n}")


if __name__ == "__main__":
    main()
