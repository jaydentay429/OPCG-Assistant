#!/usr/bin/env python3
"""Batch N: owner's hand, Life top, Trigger play-this-card, Bonney mash, hand_to_life filters."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

LUFFY = "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫"
EGGHEAD = "Egghead|蛋頭|蛋头"
STRAW = "Straw Hat Crew|草帽一行人"
OWNER_HAND = re.compile(r"持有者的手牌|to the owner'?s hand")
ADD_LIFE_TOP = re.compile(
    r"將最多\s*(\d+)\s*張自己卡組上面的卡片加入生命值區上面|"
    r"add up to\s*(\d+)\s*cards? from the top of your deck to the top of your Life"
)
PLAY_THIS = re.compile(r"使這張卡片登場|Play this card")
DEFICIT_AFTER_FLIP = re.compile(
    r"翻成正面朝上[：:].{0,20}若自己的角色卡比對手的角色卡少"
)
INNATE_BLOCKER = re.compile(r"【防禦】\s*[（(]|\[Blocker\]\s*\(")
LEADER_THEN_ADD_LIFE = re.compile(
    r"放置在廢棄區[：:].{0,8}若自己的領航卡|"
    r"trash 1 card from the top of your Life cards:\s*If your Leader"
)


def _paper(catalog: dict[str, Any], cid: str) -> str:
    info = catalog.get(cid) or {}
    return " ".join(
        str(info.get(k) or "")
        for k in ("effect", "effect_text", "text", "trigger", "effect_en", "trigger_en")
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


def _play_this_ops(*, as_cost_trash: bool = False) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    if as_cost_trash:
        ops.append(
            {
                "op": "trash_hand",
                "count": 1,
                "optional": True,
                "as_cost": True,
                "owner": "self",
            }
        )
    ops.append(
        {
            "op": "play_from_hand",
            "count": 1,
            "card_type": "character",
            "optional": False,
            "from_zone": "hand",
            "self_card": True,
            "summary": "Play this card",
        }
    )
    return ops


def _named(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-053",
        [
            {
                "timing": "on_play",
                "summary": "Give up to 1 rested DON!! to your Leader",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "leader",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_play",
                "summary": "If opp Life ≥3: add up to 1 opp Life top to owner's hand",
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
                "require_opp_life_gte": 3,
            },
            {
                "timing": "on_ko",
                "summary": "May flip Life top face-up: play up to 1 own Character power≤6000 from hand",
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
        "EB03-055",
        [
            {
                "timing": "on_play",
                "summary": "May trash Life top: if Straw Hat Leader, add up to 2 deck top to Life top",
                "ops": [
                    {
                        "op": "trash_life",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "add_life",
                        "count": 2,
                        "optional": True,
                        "position": "top",
                        "require_leader_trait": STRAW,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_ko",
                "summary": "Opp turn: you may deal 1 damage to opponent",
                "ops": [{"op": "deal_life_damage", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "require_opponent_turn": True,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-059",
        [
            {
                "timing": "on_play",
                "summary": "If Egghead Leader and ≥2 Life: add up to 1 Trigger Character from hand to Life top face-up",
                "ops": [
                    {
                        "op": "hand_to_life",
                        "count": 1,
                        "optional": True,
                        "face": "up",
                        "position": "top",
                        "card_type": "character",
                        "require_trigger": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_gte": 2,
                "require_leader_trait": EGGHEAD,
            },
            {
                "timing": "trigger",
                "summary": "Up to 1 opp Character cost≤6 other than Luffy cannot attack this turn",
                "ops": [
                    {
                        "op": "deny_attack",
                        "count": 1,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "cost_lte": 6,
                        "duration": "turn",
                        "exclude_name": LUFFY,
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
        "EB04-059",
        [
            {
                "timing": "on_play",
                "summary": "May flip Life top face-up: if fewer Characters than opponent, KO up to 1 cost≤6 and up to 1 cost≤5",
                "ops": [
                    {
                        "op": "flip_life",
                        "face": "up",
                        "position": "top",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 6,
                        "require_chars_deficit_gte": 1,
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 5,
                        "require_chars_deficit_gte": 1,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Draw 2 and trash 1 hand",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
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
        "OP05-105",
        [
            {
                "timing": "trigger",
                "summary": "May trash 1 hand: play this card",
                "ops": _play_this_ops(as_cost_trash=True),
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-104",
        [
            {
                "timing": "on_ko",
                "summary": "If opp Life≤3: add up to 1 deck top to Life top",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_opp_life_lte": 3,
            },
            {
                "timing": "trigger",
                "summary": "If opp Life≤3: play this card",
                "ops": _play_this_ops(),
                "status": "compiled",
                "confidence": 0.95,
                "require_opp_life_lte": 3,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-108",
        [
            {
                "timing": "on_play",
                "summary": "If Egghead Leader: this gains Rush this turn; then opponent adds 1 Life top to their hand",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "turn",
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
                "require_leader_trait": EGGHEAD,
            },
            {
                "timing": "trigger",
                "summary": "If own Life≤1: rest up to 1 opp Character cost≤7",
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
        "OP16-107",
        [
            {
                "timing": "on_ko",
                "summary": "Add up to 1 card from top of opp Life to owner's hand",
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
            {
                "timing": "trigger",
                "summary": "May trash 1 hand: play this card",
                "ops": _play_this_ops(as_cost_trash=True),
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST29-004",
        [
            {
                "timing": "on_play",
                "summary": "Look 4; reveal up to 1 Straw Hat Crew; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": STRAW,
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "May trash 1 hand: play this card",
                "ops": _play_this_ops(as_cost_trash=True),
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST29-005",
        [
            {
                "timing": "trigger",
                "summary": "If Leader is Monkey.D.Luffy, play this card",
                "ops": _play_this_ops(),
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": LUFFY,
            }
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST29-009",
        [
            {
                "timing": "trigger",
                "summary": "If Leader is Monkey.D.Luffy, play this card",
                "ops": _play_this_ops(),
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": LUFFY,
            }
        ],
    )
    return n


def _ensure_luffy_alias(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if "Monkey.D.Luffy" not in raw and "蒙其" not in raw:
        return None
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    for extra in LUFFY.split("|"):
        if extra not in parts:
            parts.append(extra)
    joined = "|".join(parts)
    return joined if joined != raw else None


def _patch_similar(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0
    skip = {
        "EB03-053",
        "EB03-055",
        "EB03-059",
        "EB04-059",
        "OP05-105",
        "OP06-104",
        "OP13-108",
        "OP16-107",
        "ST29-004",
        "ST29-005",
        "ST29-009",
    }
    reload_effect_library(force=True)
    for cid, info in catalog.items():
        if not isinstance(cid, str) or cid in skip:
            continue
        paper = _paper(catalog, cid)
        if not paper.strip():
            continue
        entry = get_card_entry(cid)
        abilities = [dict(a) for a in (entry.get("abilities") or [])]
        if not abilities:
            continue
        changed = False

        if OWNER_HAND.search(paper):
            for ab in abilities:
                for op in ab.get("ops") or []:
                    if op.get("op") == "life_to_hand" and str(op.get("owner") or "") == "opponent":
                        if op.get("hand_owner") != "life_owner":
                            op["hand_owner"] = "life_owner"
                            changed = True

        m_add = ADD_LIFE_TOP.search(paper)
        if m_add:
            count = int(m_add.group(1) or m_add.group(2) or 1)
            for ab in abilities:
                for op in ab.get("ops") or []:
                    if op.get("op") != "add_life":
                        continue
                    if op.get("position") != "top":
                        op["position"] = "top"
                        changed = True
                    if int(op.get("count") or 1) != count and count > 1:
                        op["count"] = count
                        changed = True
                    if not op.get("optional"):
                        op["optional"] = True
                        changed = True

        if LEADER_THEN_ADD_LIFE.search(paper):
            for ab in abilities:
                if ab.get("timing") not in {"on_play", "activate_main"}:
                    continue
                trait = str(ab.get("require_leader_trait") or "").strip()
                if not trait:
                    continue
                ops = list(ab.get("ops") or [])
                if not any(o.get("op") == "trash_life" and o.get("as_cost") for o in ops):
                    continue
                if not any(o.get("op") == "add_life" for o in ops):
                    continue
                ab.pop("require_leader_trait", None)
                for op in ops:
                    if op.get("op") == "add_life" and not op.get("require_leader_trait"):
                        op["require_leader_trait"] = trait
                        changed = True

        if PLAY_THIS.search(paper):
            for ab in abilities:
                if ab.get("timing") != "trigger":
                    continue
                for op in ab.get("ops") or []:
                    if op.get("op") != "play_from_hand":
                        continue
                    if not op.get("self_card"):
                        op["self_card"] = True
                        changed = True
                    if op.get("from_zone") not in {None, "hand", "trash", "hand_or_trash"}:
                        op["from_zone"] = "hand"
                        changed = True
                    elif not op.get("from_zone"):
                        op["from_zone"] = "hand"
                        changed = True
                    if op.get("optional") is True and "最多" not in (ab.get("summary") or "") and "up to" not in str(ab.get("summary") or "").lower():
                        op["optional"] = False
                        changed = True
                    if op.get("name_contains") and "這張" in paper:
                        op.pop("name_contains", None)
                        changed = True
                    if op.get("require_trigger") and "這張" in paper:
                        op.pop("require_trigger", None)
                        changed = True

        if DEFICIT_AFTER_FLIP.search(paper):
            for ab in abilities:
                if ab.get("require_chars_deficit_gte") is None:
                    continue
                need = int(ab["require_chars_deficit_gte"])
                ab.pop("require_chars_deficit_gte", None)
                for op in ab.get("ops") or []:
                    if op.get("op") == "ko" and op.get("require_chars_deficit_gte") is None:
                        op["require_chars_deficit_gte"] = need
                changed = True

        if INNATE_BLOCKER.search(paper):
            kept = []
            for ab in abilities:
                ops = list(ab.get("ops") or [])
                if (
                    ab.get("timing") == "on_opponent_attack"
                    and len(ops) == 1
                    and ops[0].get("op") == "grant_keyword"
                    and str(ops[0].get("keyword") or "").lower() == "blocker"
                    and str(ops[0].get("target_kind") or "self") == "self"
                ):
                    changed = True
                    continue
                kept.append(ab)
            if len(kept) != len(abilities):
                abilities = kept
                changed = True

        for ab in abilities:
            new_name = _ensure_luffy_alias(str(ab.get("require_leader_name") or ""))
            if new_name:
                ab["require_leader_name"] = new_name
                changed = True
            for op in ab.get("ops") or []:
                new_ex = _ensure_luffy_alias(str(op.get("exclude_name") or ""))
                if new_ex:
                    op["exclude_name"] = new_ex
                    changed = True

        if changed:
            n += _write(ov_cards, lib_cards, catalog, cid, abilities)
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
    ov["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lib["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = lib_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(lib, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(lib_path)
    reload_effect_library(force=True)

    similar = _patch_similar(catalog, ov_cards, lib_cards)
    if similar:
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
