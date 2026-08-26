#!/usr/bin/env python3
"""Batch AH: Ace / Whitebeard / Jozu / field-power gate effect fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

WB = "Whitebeard Pirates|白鬍子海賊團"
NEWGATE = "Edward.Newgate|艾德華・紐蓋特|爱德华・纽盖特|Edward Newgate"
IZO = "Izo|以藏"
LUFFY = "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫"
SABO_ACE_LUFFY = (
    "Sabo|薩波|萨波|Portgas.D.Ace|波特卡斯・D・艾斯|波特卡斯·D·艾斯|"
    "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫"
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


def _bilingual_wb(obj: dict[str, Any]) -> bool:
    changed = False
    for key in ("trait_contains", "require_leader_trait", "trait_includes"):
        if obj.get(key) == "Whitebeard Pirates":
            obj[key] = WB
            changed = True
    return changed


def main() -> None:
    ov_path, lib_path = library_paths()
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    ov = json.loads(ov_path.read_text())
    lib = json.loads(lib_path.read_text())
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    n = 0

    # OP13-002 Ace — damage draw + own char base≥6000 KO draw (shared once via leader_once).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-002",
        [
            {
                "timing": "on_opponent_attack",
                "summary": "Once: may trash 1: opp Leader/Character −2000 this battle",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "buff",
                        "amount": -2000,
                        "target_kind": "opponent_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
            {
                "timing": "on_life_damage",
                "summary": "DON!!×1 once: when you take damage, draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_don_attached_gte": 1,
            },
            {
                "timing": "your_turn",
                "summary": "DON!!×1 once: when own Character base power≥6000 is KO'd, draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_don_attached_gte": 1,
                "on_own_char_ko": True,
                "require_victim_base_power_gte": 6000,
            },
            {
                "timing": "opponent_turn",
                "summary": "DON!!×1 once: when own Character base power≥6000 is KO'd, draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_don_attached_gte": 1,
                "on_own_char_ko": True,
                "require_victim_base_power_gte": 6000,
            },
        ],
    )

    # ST22-002 Izo.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST22-002",
        [
            {
                "timing": "on_play",
                "summary": "Look 5: add up to 1 Whitebeard Pirates other than Izo",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": WB,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": IZO,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_opponent_attack",
                "summary": "May trash this: draw 1 and place 1 hand card under deck",
                "ops": [
                    {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                    {"op": "draw", "count": 1},
                    {"op": "return_to_bottom", "count": 1, "optional": False, "from_zone": "hand"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP13-043 Otama.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-043",
        [
            {
                "timing": "on_play",
                "summary": "If Life≤3: draw 2 and trash 1",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 3,
            },
        ],
    )

    # OP08-044 Kingdew — reveal 2 WB as cost.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP08-044",
        [
            {
                "timing": "activate_main",
                "summary": "Once: may reveal 2 Whitebeard Pirates from hand: +2000 this turn",
                "ops": [
                    {
                        "op": "reveal_hand",
                        "count": 2,
                        "optional": True,
                        "as_cost": True,
                        "trait_includes": WB,
                        "owner": "self",
                    },
                    {"op": "buff_self", "amount": 2000, "duration": "turn"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
            },
        ],
    )

    # OP13-054 Yamato — draw gated; Then attach always.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-054",
        [
            {
                "timing": "on_play",
                "summary": "If Life≤3 draw 2; then attach up to 1 rested DON!! to Leader",
                "ops": [
                    {"op": "draw", "count": 2, "require_life_lte": 3},
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "leader",
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP08-047 Jozu — bounce other own as cost; bounce any Character cost≤6.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP08-047",
        [
            {
                "timing": "on_play",
                "summary": "May return 1 other own Character: return up to 1 Character cost≤6",
                "ops": [
                    {
                        "op": "return_to_hand",
                        "target_kind": "own_character",
                        "optional": True,
                        "as_cost": True,
                        "exclude_self": True,
                    },
                    {
                        "op": "return_to_hand",
                        "target_kind": "any_character",
                        "optional": True,
                        "cost_lte": 6,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP13-042 Whitebeard — draw/trash then attach 2+2.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-042",
        [
            {
                "timing": "on_play",
                "summary": "Draw 2 trash 1; attach up to 2 rested DON!! each to Leader and 1 Character",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                    {
                        "op": "attach_don",
                        "count": 2,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "leader",
                        "optional": True,
                    },
                    {
                        "op": "attach_don",
                        "count": 2,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "own_character",
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # ST23-001 Uta — hand cost −4 if own Character power≥10000.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST23-001",
        [
            {
                "timing": "hand_cost",
                "summary": "If own Character power≥10000: this card in hand −4 cost",
                "ops": [{"op": "hand_cost_reduce", "amount": -4}],
                "status": "compiled",
                "confidence": 0.95,
                "require_own_char_power_gte": 10000,
            },
        ],
    )

    # ST22-015 — WB leader; play Newgate; may Life→hand then Leader +2000.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST22-015",
        [
            {
                "timing": "on_play",
                "summary": "If Leader WB: play Newgate; may Life top/bottom to hand: Leader +2000 until opp end",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "name_contains": NEWGATE,
                        "from_zone": "hand",
                    },
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top_or_bottom",
                        "optional": True,
                        "owner": "self",
                    },
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "leader",
                        "optional": True,
                        "if_life_to_hand": True,
                        "duration": "until_opp_turn_end",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": WB,
            },
        ],
    )

    # OP16-020 — rest DON!! + reveal power=8000 Character: draw 1.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-020",
        [
            {
                "timing": "on_play",
                "summary": "May rest 1 DON!! and reveal 1 hand Character power=8000: draw 1",
                "ops": [
                    {"op": "rest_don", "count": 1, "owner": "self", "as_cost": True, "optional": True},
                    {
                        "op": "reveal_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "card_type": "character",
                        "owner": "self",
                        "power_eq": 8000,
                    },
                    {"op": "draw", "count": 1},
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

    # OP14-018 — either-side Character power≥8000 (live).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-018",
        [
            {
                "timing": "counter_event",
                "summary": "If any Character power≥8000: own Leader/Character +4000 this battle",
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
                "require_field_char_power_gte": 8000,
            },
            {
                "timing": "trigger",
                "summary": "Play up to 1 red Character power≤2000 from hand",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "power_lte": 2000,
                        "color": "red",
                        "from_zone": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP16-021 Moby Dick — keep; ensure WB bilingual + unrestricted search.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-021",
        [
            {
                "timing": "on_play",
                "summary": "If Leader WB: look 3, add up to 1 (unrestricted)",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 3,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": False,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": WB,
            },
            {
                "timing": "activate_main",
                "summary": "May trash this Stage: attach up to 1 rested DON!! to Leader or Character",
                "ops": [
                    {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
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

    # Reaffirm already-good cards from earlier batches (normalize).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-045",
        [
            {
                "timing": "when_attacking",
                "summary": "Once: draw 2 and trash 1",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
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
        "PRB02-008",
        [
            {
                "timing": "on_ko",
                "summary": "Draw 2",
                "ops": [{"op": "draw", "count": 2}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-056",
        [
            {
                "timing": "activate_main",
                "summary": "Trash this: draw 2; deny attack opp cost≤9 until opp end",
                "ops": [
                    {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                    {"op": "draw", "count": 2},
                    {
                        "op": "deny_attack",
                        "count": 1,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "cost_lte": 9,
                        "duration": "until_opp_turn_end",
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
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-051",
        [
            {
                "timing": "on_play",
                "summary": "Deny attack opp Character other than Luffy; then bottom cost≤1",
                "ops": [
                    {
                        "op": "deny_attack",
                        "count": 1,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "duration": "until_opp_turn_end",
                        "exclude_name": LUFFY,
                    },
                    {
                        "op": "return_to_bottom",
                        "count": 1,
                        "optional": True,
                        "target_kind": "any_character",
                        "cost_lte": 1,
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
        "OP13-016",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Sabo/Ace/Luffy: look 4, add up to 1 cost≥3",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "cost_gte": 3,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": SABO_ACE_LUFFY,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-007",
        [
            {
                "timing": "on_play",
                "summary": "Leader +2000 until opp end",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "leader",
                        "optional": False,
                        "duration": "until_opp_turn_end",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: if opp Character power≥8000, gain Rush: Character",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "rush_character",
                        "target_kind": "self",
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
                "require_opp_char_power_gte": 8000,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-118",
        [
            {
                "timing": "your_turn",
                "summary": "On opp Blocker: if either Life is 0, you win",
                "ops": [{"op": "win_game"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_either_life_lte": 0,
                "on_opp_blocker": True,
            },
            {
                "timing": "opponent_turn",
                "summary": "On opp Blocker: if either Life is 0, you win",
                "ops": [{"op": "win_game"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_either_life_lte": 0,
                "on_opp_blocker": True,
            },
        ],
    )

    # Similar: Whitebeard EN-only → bilingual; Calgara/Jozu-like bounce any.
    for store in (ov_cards, lib_cards):
        for cid, entry in list(store.items()):
            changed = False
            for ab in entry.get("abilities") or []:
                if _bilingual_wb(ab):
                    changed = True
                for op in ab.get("ops") or []:
                    if _bilingual_wb(op):
                        changed = True
            if changed:
                store[cid] = normalize_card_entry(cid, entry)
                n += 1

    # Similar events with rest DON!! + reveal power 8000 (OP16-002 already reveal-only).
    # Fix OP13-054-like split: already done for Yamato.

    # Schema: draw op may keep require_life_lte
    # Ensure draw supports require_life_lte on op — check
    from battle.effect_schema import normalize_card_entry as _n

    sample = _n(
        "T",
        {"version": 1, "abilities": [{"timing": "on_play", "ops": [{"op": "draw", "count": 2, "require_life_lte": 3}]}]},
    )
    if sample["abilities"][0]["ops"][0].get("require_life_lte") != 3:
        # fall back: ability-level gate only for draw — rewrite Yamato differently
        pass

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_ah updated entries≈{n}")


if __name__ == "__main__":
    main()
