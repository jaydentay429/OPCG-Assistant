#!/usr/bin/env python3
"""Batch AP: Alabasta / opp-life gates / rest_self / base cost / similar fixes."""

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

ALABASTA = "Alabasta|阿拉巴斯坦王國"
STRAW = "Straw Hat Crew|草帽一行人"
EGG = "Egghead|蛋頭"
BONNEY = "Jewelry Bonney|珠寶・波妮|珠宝・波妮"


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


def _strip_erroneous_own_life_gate(ability: dict[str, Any], zh: str) -> dict[str, Any]:
    """Drop require_life_lte when paper only gates on opponent Life for this ability text."""
    ab = dict(ability)
    if ab.get("require_life_lte") is None:
        return ab
    timing = str(ab.get("timing") or "")
    # Attack body often wrongly inherited Trigger's opp-life clause.
    if timing == "when_attacking" and "【攻擊時】" in zh:
        atk = zh.split("【觸發器】")[0] if "【觸發器】" in zh else zh
        if "對手的生命值" not in atk and "对手的生命值" not in atk and "opponent" not in atk.lower():
            ab.pop("require_life_lte", None)
            ab.pop("require_opp_life_lte", None)
            return ab
    # Dual own+opp with same N and paper only says 對手的生命值 → keep opp only.
    if ab.get("require_opp_life_lte") is not None:
        if re.search(r"對手的生命值|对手的生命值|opponent(?:'s)? (?:has )?\d+ or less [Ll]ife", zh, re.I):
            if not re.search(r"自己的生命值", zh):
                ab.pop("require_life_lte", None)
    # Trigger play that only checks opp life.
    if timing == "trigger" and ab.get("require_life_lte") is not None:
        if re.search(r"【觸發器】[^【]*對手的生命值|【触发器】[^【]*对手的生命值", zh):
            if not re.search(r"【觸發器】[^【]*自己的生命值", zh):
                n = int(ab["require_life_lte"])
                ab.pop("require_life_lte", None)
                ab.setdefault("require_opp_life_lte", n)
    return ab


def main() -> None:
    ov_path, lib_path = library_paths()
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    ov = json.loads(ov_path.read_text())
    lib = json.loads(lib_path.read_text())
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    n = 0

    # OP04-001 Vivi Leader.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP04-001",
        [
            {
                "timing": "your_turn",
                "summary": "This Leader cannot attack",
                "ops": [{"op": "cannot_attack", "target_kind": "leader"}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "This Leader cannot attack",
                "ops": [{"op": "cannot_attack", "target_kind": "leader"}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: rest 2 DON!!: draw 1; up to 1 own Character gains Rush this turn",
                "ops": [
                    {"op": "rest_don", "count": 2, "owner": "self", "as_cost": True},
                    {"op": "draw", "count": 1},
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "own_character",
                        "duration": "turn",
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
        ],
    )

    # EB04-002 Bonney.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-002",
        [
            {
                "timing": "on_play",
                "summary": "Look top 4; add up to 1 Egghead/Straw Hat other than Bonney",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": f"{EGG}|{STRAW}",
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

    # OP04-002 Igaram — rest this + active Leader −5000 as cost.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP04-002",
        [
            {
                "timing": "activate_main",
                "summary": "Rest this + active Leader −5000: search top 5 for up to 1 Alabasta",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -5000,
                        "target_kind": "leader",
                        "optional": True,
                        "as_cost": True,
                        "duration": "turn",
                        "require_leader_active": True,
                    },
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": ALABASTA,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "rest_self": True,
                "once": False,
            },
        ],
    )

    # OP10-011 Chopper — Blocker innate; opp-turn +2000.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-011",
        [
            {
                "timing": "opponent_turn",
                "summary": "This Character +2000 power",
                "ops": [{"op": "buff_self", "amount": 2000}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-013 Scissors.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-013",
        [
            {
                "timing": "hand_cost",
                "summary": "If Leader power ≤0: this card in hand −2 cost",
                "ops": [{"op": "hand_cost_reduce", "amount": -2}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_power_lte": 0,
            },
        ],
    )

    # EB03-006 Nami.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-006",
        [
            {
                "timing": "on_play",
                "summary": "You may give active Leader −5000: draw 1",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -5000,
                        "target_kind": "leader",
                        "optional": True,
                        "as_cost": True,
                        "duration": "turn",
                        "require_leader_active": True,
                    },
                    {"op": "draw", "count": 1},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: if Leader Alabasta, up to 1 opp Character −1000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -1000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_leader_trait": ALABASTA,
            },
        ],
    )

    # OP06-007 Jack.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-007",
        [
            {
                "timing": "on_play",
                "summary": "KO up to 1 opp Character with power ≤10000",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "power_lte": 10000,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # EB04-024 Tilestone.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-024",
        [
            {
                "timing": "activate_main",
                "summary": "Rest this + trash 1: up to 1 own Alabasta gains Unblockable",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "grant_keyword",
                        "keyword": "blockerless",
                        "target_kind": "own_character",
                        "trait_contains": ALABASTA,
                        "duration": "turn",
                        "optional": True,
                        "count": 1,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "rest_self": True,
                "once": False,
            },
        ],
    )

    # OP11-056 Brook — base cost 1 either side.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-056",
        [
            {
                "timing": "on_play",
                "summary": "Place up to 1 Character with base cost 1 on owner's deck bottom",
                "ops": [
                    {
                        "op": "return_to_bottom",
                        "count": 1,
                        "optional": True,
                        "target_kind": "any_character",
                        "base_cost_eq": 1,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-047 Sanji.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-047",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 own Character gains Unblockable this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blockerless",
                        "target_kind": "own_character",
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

    # OP10-045 Cavendish.
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

    # OP11-054 Nami.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-054",
        [
            {
                "timing": "on_play",
                "summary": "If Leader multicolor: draw 3; place 2 hand cards top or bottom",
                "ops": [
                    {"op": "draw", "count": 3},
                    {
                        "op": "hand_to_deck",
                        "count": 2,
                        "position": "top_or_bottom",
                        "optional": False,
                        "owner": "self",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_multicolor": True,
            },
        ],
    )

    # EB03-024 Vivi.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-024",
        [
            {
                "timing": "on_play",
                "summary": "Play up to 1 Alabasta/Straw Hat cost≤5 from hand; then cannot play Characters",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "trait_any": [ALABASTA, STRAW],
                        "from_zone": "hand",
                    },
                    {
                        "op": "cannot_play_from_hand",
                        "duration": "turn",
                        "card_type": "character",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # EB04-023 — Double Attack innate.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-023",
        [
            {
                "timing": "on_play",
                "summary": "You may give active Leader −5000: draw 2",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -5000,
                        "target_kind": "leader",
                        "optional": True,
                        "as_cost": True,
                        "duration": "turn",
                        "require_leader_active": True,
                    },
                    {"op": "draw", "count": 2},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP05-118 Kaido — opponent Life only.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP05-118",
        [
            {
                "timing": "on_play",
                "summary": "If opponent Life ≤3: draw 4",
                "ops": [{"op": "draw", "count": 4}],
                "status": "compiled",
                "confidence": 0.95,
                "require_opp_life_lte": 3,
            },
        ],
    )

    # Similar leader −5000 as cost + active.
    for cid in ("OP04-006", "OP07-006"):
        e = ov_cards.get(cid) or lib_cards.get(cid)
        if not isinstance(e, dict):
            continue
        abs_out = []
        changed = False
        for ab in e.get("abilities") or []:
            ab = dict(ab)
            ops = []
            for o in ab.get("ops") or []:
                o = dict(o)
                if (
                    o.get("op") == "buff"
                    and o.get("as_cost")
                    and o.get("target_kind") == "leader"
                    and int(o.get("amount") or 0) < 0
                ):
                    if not o.get("require_leader_active"):
                        o["require_leader_active"] = True
                        changed = True
                ops.append(o)
            ab["ops"] = ops
            abs_out.append(ab)
        if changed:
            n += _write(ov_cards, lib_cards, catalog, cid, abs_out)

    # OP05-114 Counter Then-if opp life (similar).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP05-114",
        [
            {
                "timing": "counter_event",
                "summary": "+2000 to own Leader/Character; Then if opp Life≤2 that card +2000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_character_or_leader",
                        "optional": True,
                        "duration": "battle",
                    },
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "prior",
                        "same_target_as_prior": True,
                        "optional": False,
                        "duration": "battle",
                        "require_opp_life_lte": 2,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "KO up to 1 opp Character with cost ≤ opponent Life",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte_opp_life": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # P-155 — attack ungated by life; Trigger opp life.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "P-155",
        [
            {
                "timing": "when_attacking",
                "summary": "You may trash 1 Trigger from hand: up to 1 opp Character −2000",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "require_trigger": True,
                        "owner": "self",
                    },
                    {
                        "op": "buff",
                        "amount": -2000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "If opponent Life ≤3: play this",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": False,
                        "from_zone": "hand",
                        "self_card": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_opp_life_lte": 3,
            },
        ],
    )

    # OP06-100 — attack not gated by life; KO cost ≤ opp life; Trigger opp life.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-100",
        [
            {
                "timing": "when_attacking",
                "summary": "DON!!×2: you may trash 1: KO up to 1 Character cost ≤ opp Life",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte_opp_life": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 2,
            },
            {
                "timing": "trigger",
                "summary": "If opponent Life ≤3: play this",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": False,
                        "from_zone": "hand",
                        "self_card": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_opp_life_lte": 3,
            },
        ],
    )

    # Similar: EB01-003, EB01-054 — drop erroneous own life gate.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB01-003",
        [
            {
                "timing": "when_attacking",
                "summary": "If opponent Life ≤2: this Character +2000",
                "ops": [{"op": "buff_self", "amount": 2000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_opp_life_lte": 2,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB01-054",
        [
            {
                "timing": "on_play",
                "summary": "If opponent Life ≤1: KO up to 1 opp Character cost≤3",
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
                "require_opp_life_lte": 1,
            },
        ],
    )

    # Bulk soft-fix remaining dual own+opp life gates from paper.
    for store in (ov_cards, lib_cards):
        for cid, entry in list(store.items()):
            if not isinstance(entry, dict):
                continue
            zh = str((catalog.get(cid) or {}).get("effect") or "")
            abs_in = entry.get("abilities") or []
            abs_out = [_strip_erroneous_own_life_gate(dict(a), zh) for a in abs_in]
            if abs_out != abs_in:
                entry2 = normalize_card_entry(
                    cid, {"version": int(entry.get("version") or 1), "abilities": abs_out}
                )
                ov_cards[cid] = entry2
                lib_cards[cid] = {**entry2, "card_id": cid}
                n += 1

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_ap updated {n} card entries")


if __name__ == "__main__":
    main()
