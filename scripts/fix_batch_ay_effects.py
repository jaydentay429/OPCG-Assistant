#!/usr/bin/env python3
"""Batch AY: Bonney/Egghead Then-if, Pacifista leader name, Stage-like soft fixes."""

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

EGGHEAD = "Egghead|蛋頭|蛋头"
STRAW = "Straw Hat Crew|草帽一行人"
BONNEY = "Jewelry Bonney|珠寶・波妮|珠宝・波妮"
LUFFY = "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫|モンキー・D・ルフィ"
BRILLIANT = (
    "He Possesses the World's Most Brilliant Mind|"
    "全世界頭腦最聰明的男人|"
    "全世界头脑最聪明的男人"
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

    # EB04-001 — −1000 ungated; Life→hand only if Life≥2.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-001",
        [
            {
                "timing": "opponent_turn",
                "summary": "If Life≤1: this Leader +2000",
                "ops": [{"op": "buff_self", "amount": 2000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 1,
            },
            {
                "timing": "activate_main",
                "summary": "Once: up to 1 opp Character −1000; Then if Life≥2 may Life→hand",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -1000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                    },
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "owner": "self",
                        "require_life_gte": 2,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
        ],
    )

    # EB04-056 — both turns; Bonney includes Leader.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-056",
        [
            {
                "timing": "your_turn",
                "summary": "If own Bonney on field and Life=0: this gains Blocker",
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
                "require_life_lte": 0,
                "require_own_name_on_field": BONNEY,
            },
            {
                "timing": "opponent_turn",
                "summary": "If own Bonney on field and Life=0: this gains Blocker",
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
                "require_life_lte": 0,
                "require_own_name_on_field": BONNEY,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-106",
        [
            {
                "timing": "on_play",
                "summary": "You may Life→hand (top/bottom): KO up to 1 opp Character cost≤5",
                "ops": [
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top_or_bottom",
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 5,
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
        "EB04-053",
        [
            {
                "timing": "on_block",
                "summary": "If Life≤2: draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 2,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-053",
        [
            {
                "timing": "on_play",
                "summary": "Attach up to 1 rested DON!! to Leader; Then if opp Life≥3, opp Life→owner hand",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "leader",
                        "optional": True,
                    },
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "owner": "opponent",
                        "hand_owner": "life_owner",
                        "require_opp_life_gte": 3,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_ko",
                "summary": "You may flip Life top face-up: play up to 1 Character power≤6000 from hand",
                "ops": [
                    {
                        "op": "flip_life",
                        "face": "up",
                        "position": "top",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "power_lte": 6000,
                        "from_zone": "hand",
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
        "EB04-058",
        [
            {
                "timing": "on_play",
                "summary": "If Life≤2: add up to 1 top deck to Life",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 2,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-054",
        [
            {
                "timing": "on_play",
                "summary": "If Life≤2: add up to 1 top deck to Life",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 2,
            },
            {
                "timing": "on_ko",
                "summary": "Add up to 1 opp Life top to owner's hand",
                "ops": [
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "owner": "opponent",
                        "hand_owner": "life_owner",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP13-108 — Rush gated by Egghead; Then opp Life→hand ungated.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-108",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Egghead: this gains Rush this turn; Then opp adds Life top to hand",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "turn",
                        "require_leader_trait": EGGHEAD,
                    },
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top",
                        "optional": False,
                        "owner": "opponent",
                        "hand_owner": "life_owner",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "If Life≤1: rest up to 1 opp Character cost≤7",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 7,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 1,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-061",
        [
            {
                "timing": "hand_cost",
                "summary": "If Life≤1: this card in hand −1 cost",
                "ops": [{"op": "hand_cost_reduce", "amount": -1}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 1,
            },
            {
                "timing": "on_play",
                "summary": "You may trash 1: Leader +2000 until opp end; Then this gains Blocker until opp end",
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
                        "amount": 2000,
                        "target_kind": "leader",
                        "optional": False,
                        "duration": "until_opp_turn_end",
                    },
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
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
        "EB04-002",
        [
            {
                "timing": "on_play",
                "summary": "Look top 4; add up to 1 Egghead or Straw Hat other than Bonney; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "trait_any": [EGGHEAD, STRAW],
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": BONNEY,
                        "destination": "hand",
                        "reveal_adds": True,
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
        "OP13-007",
        [
            {
                "timing": "activate_main",
                "summary": "You may attach 1 active DON!! + trash this: up to 1 opp Character −3000",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_cost": True,
                        "from_active": True,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                    },
                    {
                        "op": "trash",
                        "target_kind": "self",
                        "optional": False,
                        "as_cost": True,
                    },
                    {
                        "op": "buff",
                        "amount": -3000,
                        "target_kind": "opponent_character",
                        "optional": True,
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
        "ST21-003",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 own Straw Hat power≥6000 gains blockerless this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blockerless",
                        "target_kind": "own_character",
                        "trait_contains": STRAW,
                        "power_gte": 6000,
                        "duration": "turn",
                        "optional": True,
                        "count": 1,
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
                "summary": "Once: if opp has Character power≥8000, this gains Rush: Character",
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-114",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5; add up to 1 Egghead other than this; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": EGGHEAD,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": BRILLIANT,
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
        "ST29-016",
        [
            {
                "timing": "on_play",
                "summary": "Your Monkey.D.Luffy Leader gains Unblockable this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blockerless",
                        "target_kind": "leader",
                        "name_contains": LUFFY,
                        "duration": "turn",
                        "optional": False,
                    }
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
        "EB04-008",
        [
            {
                "timing": "on_play",
                "summary": "If Life≤2: up to 1 opp Character −3000 this turn",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -3000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 2,
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

    # Soft-fix: 「若X，A。之後，B」— move ability-level require_* onto first op(s) before 之後.
    then_if_re = re.compile(r"【登場時】若.{2,80}時，.{2,120}。之後，")
    for cid, entry in list(ov_cards.items()):
        info = catalog.get(cid) or {}
        zh = str(info.get("effect") or "")
        if not then_if_re.search(zh):
            continue
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            if ab.get("timing") != "on_play":
                abs_out.append(ab)
                continue
            req_keys = [k for k in list(ab.keys()) if str(k).startswith("require_")]
            ops = list(ab.get("ops") or [])
            if not req_keys or len(ops) < 2:
                abs_out.append(ab)
                continue
            # Gate only the first op; leave Then ops ungated.
            first = dict(ops[0])
            for k in req_keys:
                first[k] = ab.pop(k)
                changed = True
            ab["ops"] = [first] + [dict(o) for o in ops[1:]]
            abs_out.append(ab)
        if changed:
            entry2 = normalize_card_entry(
                cid, {"version": int(entry.get("version") or 1), "abilities": abs_out}
            )
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    # Soft-fix: activate_main Then-if Life after first effect (like EB04-001).
    act_then_life = re.compile(
        r"【啟動主要】.{0,80}。之後，若自己的生命值卡在(\d+)張以上時"
    )
    for cid, entry in list(ov_cards.items()):
        info = catalog.get(cid) or {}
        zh = str(info.get("effect") or "")
        m = act_then_life.search(zh)
        if not m:
            continue
        need = int(m.group(1))
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            if ab.get("timing") != "activate_main":
                abs_out.append(ab)
                continue
            if ab.get("require_life_gte") is not None:
                need2 = ab.pop("require_life_gte")
                ops = []
                for i, o in enumerate(ab.get("ops") or []):
                    o = dict(o)
                    if i > 0 and o.get("op") in {"life_to_hand", "draw", "trash_life"}:
                        o["require_life_gte"] = need2
                        changed = True
                    ops.append(o)
                ab["ops"] = ops
                changed = True
            else:
                ops = list(ab.get("ops") or [])
                if len(ops) >= 2 and ops[-1].get("op") == "life_to_hand":
                    last = dict(ops[-1])
                    if last.get("require_life_gte") is None:
                        last["require_life_gte"] = need
                        ab["ops"] = [dict(o) for o in ops[:-1]] + [last]
                        changed = True
            abs_out.append(ab)
        if changed:
            entry2 = normalize_card_entry(
                cid, {"version": int(entry.get("version") or 1), "abilities": abs_out}
            )
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    # Soft-fix: duplicate choose_target + buff on same ability.
    for cid, entry in list(ov_cards.items()):
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            ops = list(ab.get("ops") or [])
            if (
                len(ops) == 2
                and ops[0].get("op") == "choose_target"
                and ops[1].get("op") == "buff"
                and ops[0].get("target_kind") == ops[1].get("target_kind")
            ):
                ab["ops"] = [dict(ops[1])]
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
    print(f"batch_ay updated {n} card entries")


if __name__ == "__main__":
    main()
