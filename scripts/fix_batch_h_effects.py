#!/usr/bin/env python3
"""Batch H: given-DON gates, dual-trait searches, targeted unblockable, stage rest."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

TRAIT_EN = {
    "蛋頭": "Egghead",
    "草帽一行人": "Straw Hat Crew",
    "超新星": "Supernovas",
    "基德海賊團": "Kid Pirates",
    "哈特海賊團": "Heart Pirates",
    "亞馬遜百合": "Amazon Lily",
    "九蛇海賊團": "Kuja Pirates",
    "百獸海賊團": "Animal Kingdom Pirates",
    "BIG MOM海賊團": "Big Mom Pirates",
    "阿拉巴斯坦王國": "Alabasta",
    "魚人族": "Fish-Man",
    "人魚族": "Merfolk",
    "海王類": "Neptunian",
    "魚人島": "Fish-Man Island",
    "火戰車海賊團": "Firetank Pirates",
    "革命軍": "Revolutionary Army",
    "黑鬍子海賊團": "Blackbeard Pirates",
}

OR_TRAIT = re.compile(r"擁有《([^》]+)》或《([^》]+)》")
STAGE_REST = re.compile(r"這張舞台卡置為休息|rest this Stage", re.I)
GIVEN_DON = re.compile(r"已附加的咚.{0,8}合計\s*(\d+)")


def _variants(catalog: dict[str, Any], base: str) -> list[str]:
    out = [base]
    out.extend(sorted(k for k in catalog if k.startswith(base + "-")))
    return [c for c in out if c in catalog or c == base]


def _write(ov_cards: dict, lib_cards: dict, catalog: dict, cid: str, abilities: list[dict[str, Any]]) -> int:
    entry = normalize_card_entry(cid, {"version": 1, "abilities": abilities})
    n = 0
    for vid in _variants(catalog, cid):
        ov_cards[vid] = entry
        lib_cards[vid] = entry
        n += 1
    return n


def _named(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-002",
        [
            {
                "timing": "on_play",
                "summary": "Look 4: add up to 1 Egghead or Straw Hat Crew other than Jewelry Bonney",
                "ops": [
                    {
                        "op": "search_deck",
                        "trait_contains": "Egghead|Straw Hat Crew",
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": "Jewelry Bonney|珠寶・波妮",
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-019",
        [
            {
                "timing": "on_play",
                "summary": "Look 4: add up to 1 Supernovas or Straw Hat Crew Character",
                "ops": [
                    {
                        "op": "search_deck",
                        "trait_contains": "Supernovas|Straw Hat Crew",
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "card_type": "character",
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
        "OP12-015",
        [
            {
                "timing": "your_turn",
                "summary": "If total given DON!! ≥2: this +2000",
                "ops": [{"op": "buff_self", "amount": 2000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_given_don_gte": 2,
            },
            {
                "timing": "opponent_turn",
                "summary": "If total given DON!! ≥2: this +2000",
                "ops": [{"op": "buff_self", "amount": 2000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_given_don_gte": 2,
            },
            {
                "timing": "on_play",
                "summary": "May reveal 2 Event from hand: play up to 1 red Character power≤3000; attach 1 rested DON!!",
                "ops": [
                    {
                        "op": "reveal_hand",
                        "count": 2,
                        "optional": True,
                        "as_cost": True,
                        "card_type": "event",
                        "owner": "self",
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "power_lte": 3000,
                        "color": "red",
                        "from_zone": "hand",
                    },
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
                "confidence": 0.9,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-018",
        [
            {
                "timing": "counter_event",
                "summary": "Own Character or Silvers Rayleigh +2000; may rest 1 DON!!: all opp −1000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_character",
                        "optional": True,
                        "duration": "battle",
                        "include_leader_if_name": "Silvers Rayleigh|席爾巴斯・雷利",
                        "summary": "Own Character or Silvers Rayleigh +2000",
                    },
                    {
                        "op": "rest_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "buff",
                        "amount": -1000,
                        "target_kind": "opponent_leader_or_character",
                        "optional": False,
                        "all": True,
                        "duration": "turn",
                        "summary": "If DON!! rested: all opp Leader and Characters −1000",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
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
                "summary": "Up to 1 own Straw Hat power≥6000 gains Unblockable this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blockerless",
                        "target_kind": "own_character",
                        "trait_contains": "Straw Hat Crew",
                        "power_gte": 6000,
                        "optional": True,
                        "duration": "turn",
                        "count": 1,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST21-017",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 opp Character −5000; then if own Character power≥6000, KO opp power≤2000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -5000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "power_lte": 2000,
                        "require_own_char_power_gte": 6000,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Activate this card's Main effect",
                "ops": [
                    {
                        "op": "activate_timing",
                        "timing": "on_play",
                        "summary": "Activate this card's Main effect",
                    }
                ],
                "status": "compiled",
                "confidence": 0.9,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST31-004",
        [
            {
                "timing": "your_turn",
                "summary": "If total given DON!! ≥3: gain Rush",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "permanent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_given_don_gte": 3,
            },
            {
                "timing": "on_play",
                "summary": "For every own Straw Hat card: up to 1 opp Character −1000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -1000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                        "per_choose": True,
                        "per_own_chars": 1,
                        "per_own_trait": "Straw Hat Crew",
                        "include_leader": True,
                        "include_stage": True,
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
        "ST31-005",
        [
            {
                "timing": "on_play",
                "summary": "Look 5: add up to 1 Straw Hat Crew card",
                "ops": [
                    {
                        "op": "search_deck",
                        "trait_contains": "Straw Hat Crew",
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Rest this Stage: attach up to 1 rested DON!! to own Monkey.D.Luffy",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "name_contains": "Monkey.D.Luffy|蒙其・D・魯夫",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": True,
                "once": False,
            },
        ],
    )
    return n


def _patch_similar(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0

    def _store(cid: str, abilities: list[dict[str, Any]]) -> None:
        nonlocal n
        entry = normalize_card_entry(cid, {"version": 1, "abilities": abilities})
        ov_cards[cid] = entry
        lib_cards[cid] = entry
        n += 1

    for cid, info in catalog.items():
        text = str(info.get("effect") or "")
        entry = ov_cards.get(cid) or lib_cards.get(cid) or {}
        abilities = [dict(a) for a in (entry.get("abilities") or [])]
        if not abilities:
            continue
        changed = False

        m_or = OR_TRAIT.search(text)
        if m_or:
            zh_a, zh_b = m_or.group(1), m_or.group(2)
            for ab in abilities:
                ops = list(ab.get("ops") or [])
                for op in ops:
                    if op.get("op") != "search_deck":
                        continue
                    tc = str(op.get("trait_contains") or "")
                    en_a, en_b = TRAIT_EN.get(zh_a, zh_a), TRAIT_EN.get(zh_b, zh_b)
                    has_a = en_a in tc or zh_a in tc
                    has_b = en_b in tc or zh_b in tc
                    if not (has_a and has_b):
                        op["trait_contains"] = f"{en_a}|{en_b}"
                        changed = True
                ab["ops"] = ops

        m_don = GIVEN_DON.search(text)
        if m_don:
            need = int(m_don.group(1))
            for ab in abilities:
                if ab.get("require_don_attached_gte") == need and ab.get("require_given_don_gte") is None:
                    ab.pop("require_don_attached_gte", None)
                    ab["require_given_don_gte"] = need
                    changed = True
                # Static self-power with given-DON should also apply on opponent's turn.
                if (
                    ab.get("timing") == "your_turn"
                    and ab.get("require_given_don_gte") == need
                    and any(o.get("op") == "buff_self" for o in ab.get("ops") or [])
                ):
                    if not any(
                        x.get("timing") == "opponent_turn" and x.get("require_given_don_gte") == need
                        for x in abilities
                    ):
                        abilities.append(
                            {
                                **{k: v for k, v in ab.items() if k != "ops"},
                                "timing": "opponent_turn",
                                "ops": [dict(o) for o in ab.get("ops") or []],
                            }
                        )
                        changed = True

        if STAGE_REST.search(text) and str(info.get("card_type") or info.get("type") or "").lower() == "stage":
            for ab in abilities:
                if ab.get("timing") == "activate_main" and not ab.get("rest_self"):
                    ab["rest_self"] = True
                    changed = True
                if ab.get("timing") == "activate_main":
                    ops = list(ab.get("ops") or [])
                    for op in ops:
                        if op.get("op") != "attach_don":
                            continue
                        if "休息狀態的咚" in text or "rested DON" in str(info.get("effect_en") or ""):
                            if not op.get("from_rested") and not op.get("as_rested"):
                                op["as_rested"] = True
                                op["from_rested"] = True
                                changed = True
                    ab["ops"] = ops

        if changed:
            _store(cid, abilities)
    return n


def main() -> int:
    ov_path = ROOT / "index" / "card_effect_overrides.json"
    lib_path, _ = library_paths()
    ov = json.loads(ov_path.read_text(encoding="utf-8"))
    lib = json.loads(lib_path.read_text(encoding="utf-8"))
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))

    named = _named(catalog, ov_cards, lib_cards)
    similar = _patch_similar(catalog, ov_cards, lib_cards)

    ov["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lib["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = lib_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(lib, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(lib_path)
    reload_effect_library(force=True)
    print(f"wrote named={named} similar={similar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
