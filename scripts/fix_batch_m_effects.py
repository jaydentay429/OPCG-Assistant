#!/usr/bin/env python3
"""Batch M: Life destinations, On K.O. opponent-turn, set_base_power choice, trash costs."""

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

BB = "Blackbeard Pirates|黑鬍子海賊團|黑胡子海贼团"
TEACH = "Marshall.D.Teach|馬歇爾・D・汀奇|马歇尔・D・汀奇"
VORTEX = "Black Vortex|闇水"
SKY = "Sky Island|空島|空岛"

LOOK_LIFE = re.compile(
    r"從自己的卡組上面查看(\d+)張卡片[，,].{0,40}將最多(\d+)張卡片加入生命值區上面"
)
ADD_LIFE_TOP = re.compile(
    r"將最多\s*1\s*張自己卡組上面的卡片加入生命值區上面|add up to 1 card from the top of your deck to the top of your Life"
)
OPP_TURN_KO = re.compile(r"【(?:對方|对方)回合中】【KO時】|【(?:對方|对方)回合中】【KO时】")
STAGE_TRASH_REST = re.compile(
    r"可以廢棄1張自己的手牌[、，,]將這張(?:舞台卡|角色卡)置為休息"
)
TRASH_SELF_NOT_REST = re.compile(
    r"可以廢棄1張自己的手牌[、，,]將這張(?:舞台卡|角色卡)放置在廢棄區"
)
OWNER_HAND = re.compile(r"對手生命值區上面的卡片[，,]加入持有者的手牌")
TRASH_TO_LIFE = re.compile(
    r"廢棄區中(?:費用(\d+)以下)?(?:擁有《([^》]+)》特徵的)?卡片[，,]以正面朝上加入生命值區上面"
)
TRIG_NEGATE_CHAR_ONLY = re.compile(
    r"【觸發器】最多1張對手的角色卡[，,].{0,12}效果無效"
)
SET_BASE_OWN = re.compile(
    r"最多1張自己的領航卡或角色卡[，,].{0,12}原本的力量值變更成\s*(\d+)"
)


def _paper(catalog: dict[str, Any], cid: str) -> str:
    info = catalog.get(cid) or {}
    blob = " ".join(
        str(info.get(k) or "")
        for k in ("effect", "effect_text", "text", "trigger", "effect_en", "trigger_en")
    )
    return blob


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


def _store(ov_cards: dict, lib_cards: dict, cid: str, abilities: list[dict[str, Any]]) -> None:
    entry = normalize_card_entry(cid, {"version": 1, "abilities": abilities})
    ov_cards[cid] = entry
    lib_cards[cid] = {**entry, "card_id": cid}


def _named(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-058",
        [
            {
                "timing": "on_play",
                "summary": "If Life ≤2: add up to 1 deck top to Life top",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 2,
            }
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-093",
        [
            {
                "timing": "activate_main",
                "summary": "If BB Leader and played this turn: negate opp Leader this turn; then negate+deny one opp Character until opp turn end",
                "ops": [
                    {
                        "op": "negate_effects",
                        "count": 1,
                        "optional": True,
                        "duration": "turn",
                        "target_kind": "leader",
                        "include_leader": True,
                        "summary": "Negate up to 1 opponent Leader this turn",
                    },
                    {
                        "op": "negate_effects",
                        "count": 1,
                        "optional": True,
                        "duration": "until_opp_turn_end",
                        "target_kind": "opponent_character",
                        "include_characters": True,
                        "summary": "Negate up to 1 opp Character until opp turn end",
                    },
                    {
                        "op": "deny_attack",
                        "count": 1,
                        "optional": False,
                        "target_kind": "opponent_character",
                        "duration": "until_opp_turn_end",
                        "same_target_as_prior": True,
                        "summary": "That Character cannot attack until opp turn end",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
                "require_leader_trait": BB,
                "require_played_this_turn": True,
            }
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-099",
        [
            {
                "timing": "activate_main",
                "summary": "Trash 1 hand and rest this Stage: look 3, add up to 1 Blackbeard Pirates, rest bottom",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": BB,
                        "top_n": 3,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": True,
                "once": False,
            }
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-113",
        [
            {
                "timing": "on_play",
                "summary": "May trash 1 hand: add up to 1 deck top to Life top",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
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
        "OP16-103",
        [
            {
                "timing": "on_ko",
                "summary": "Opponent's turn: if BB Leader, draw 1 and give up to 1 opp Leader/Character −3000 this turn",
                "ops": [
                    {"op": "draw", "count": 1},
                    {
                        "op": "buff",
                        "amount": -3000,
                        "target_kind": "opponent_leader_or_character",
                        "optional": True,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": BB,
                "require_opponent_turn": True,
            },
            {
                "timing": "trigger",
                "summary": "Activate this card's On K.O. effect",
                "ops": [{"op": "activate_timing", "timing": "on_ko", "summary": "Activate On K.O. effect"}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-106",
        [
            {
                "timing": "on_ko",
                "summary": "If BB Leader: draw 1; set up to 1 own Leader/Character base power to 7000 this turn",
                "ops": [
                    {"op": "draw", "count": 1},
                    {
                        "op": "set_base_power",
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "amount": 7000,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": BB,
            },
            {
                "timing": "trigger",
                "summary": "Activate this card's On K.O. effect",
                "ops": [{"op": "activate_timing", "timing": "on_ko", "summary": "Activate On K.O. effect"}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-108",
        [
            {
                "timing": "on_play",
                "summary": "May trash 1 hand: add up to 1 BB cost≤6 from trash to Life top face-up",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "add_from_trash",
                        "count": 1,
                        "optional": True,
                        "trait_contains": BB,
                        "cost_lte": 6,
                        "destination": "life",
                        "face": "up",
                        "position": "top",
                        "summary": "Add up to 1 BB cost≤6 from trash to Life face-up",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
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
        "OP16-115",
        [
            {
                "timing": "on_play",
                "summary": "If BB Leader: add up to 1 Trigger from trash other than Black Vortex",
                "ops": [
                    {
                        "op": "add_from_trash",
                        "count": 1,
                        "optional": True,
                        "require_trigger": True,
                        "name_exclude": VORTEX,
                        "summary": "Add up to 1 [Trigger] card from trash to hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": BB,
            },
            {
                "timing": "trigger",
                "summary": "Negate up to 1 opponent Leader or Character this turn",
                "ops": [
                    {
                        "op": "negate_effects",
                        "count": 1,
                        "optional": True,
                        "duration": "turn",
                        "target_kind": "opponent_leader_or_character",
                        "include_leader": True,
                        "include_characters": True,
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
        "OP16-116",
        [
            {
                "timing": "on_play",
                "summary": "If DON!!≥10: play up to 1 Teach; then opp Life top to owner's hand",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "name_contains": TEACH,
                        "from_zone": "hand",
                    },
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "owner": "opponent",
                        "hand_owner": "life_owner",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_gte": 10,
            },
            {
                "timing": "trigger",
                "summary": "Draw 2; trash 1 hand",
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
        "OP16-119",
        [
            {
                "timing": "on_play",
                "summary": "Look 3; add up to 1 to Life top; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 3,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "life",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Negate up to 1 opp Character this turn; then KO up to 1 cost≤5",
                "ops": [
                    {
                        "op": "negate_effects",
                        "count": 1,
                        "optional": True,
                        "duration": "turn",
                        "target_kind": "opponent_character",
                        "include_characters": True,
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
        "OP16-109",
        [
            {
                "timing": "on_ko",
                "summary": "If BB Leader: draw 1 and KO up to 2 opp cost≤1 Characters",
                "ops": [
                    {"op": "draw", "count": 1},
                    {"op": "ko", "target_kind": "opponent_character", "optional": True, "cost_lte": 1},
                    {"op": "ko", "target_kind": "opponent_character", "optional": True, "cost_lte": 1},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": BB,
            },
            {
                "timing": "trigger",
                "summary": "Activate this card's On K.O. effect",
                "ops": [{"op": "activate_timing", "timing": "on_ko", "summary": "Activate On K.O. effect"}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )
    # Similar over-tag: 放置在廢棄區 is leave-to-trash, not rest_self.
    for cid in _variants(catalog, "OP09-089"):
        entry = ov_cards.get(cid) or lib_cards.get(cid) or {}
        abilities = [dict(a) for a in (entry.get("abilities") or [])]
        if not abilities:
            continue
        for ab in abilities:
            if ab.get("timing") == "activate_main" and ab.get("rest_self"):
                ab["rest_self"] = False
        n += _write(ov_cards, lib_cards, catalog, cid, abilities)
    return n


def _patch_similar(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0
    skip = {
        "EB04-058",
        "OP09-093",
        "OP09-099",
        "OP15-113",
        "OP16-103",
        "OP16-106",
        "OP16-108",
        "OP16-109",
        "OP16-115",
        "OP16-116",
        "OP16-119",
        "OP09-089",
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

        if ADD_LIFE_TOP.search(paper):
            for ab in abilities:
                for op in ab.get("ops") or []:
                    if op.get("op") == "add_life":
                        if op.get("position") != "top":
                            op["position"] = "top"
                            changed = True
                        if not op.get("optional"):
                            op["optional"] = True
                            changed = True

        m_look = LOOK_LIFE.search(paper)
        if m_look:
            top_n = int(m_look.group(1))
            max_add = int(m_look.group(2))
            for ab in abilities:
                for op in ab.get("ops") or []:
                    if op.get("op") != "search_deck":
                        continue
                    if op.get("destination") != "life":
                        op["destination"] = "life"
                        changed = True
                    if int(op.get("top_n") or 0) != top_n:
                        op["top_n"] = top_n
                        changed = True
                    if int(op.get("max_add") or 0) != max_add:
                        op["max_add"] = max_add
                        changed = True

        if OPP_TURN_KO.search(paper):
            for ab in abilities:
                if ab.get("timing") == "on_ko" and not ab.get("require_opponent_turn"):
                    ab["require_opponent_turn"] = True
                    changed = True

        if TRASH_SELF_NOT_REST.search(paper):
            for ab in abilities:
                if ab.get("timing") != "activate_main":
                    continue
                if ab.get("rest_self"):
                    ab["rest_self"] = False
                    changed = True

        if STAGE_TRASH_REST.search(paper):
            for ab in abilities:
                if ab.get("timing") != "activate_main":
                    continue
                ops = list(ab.get("ops") or [])
                if not any(o.get("op") == "trash_hand" and o.get("as_cost") for o in ops):
                    ops.insert(
                        0,
                        {
                            "op": "trash_hand",
                            "count": 1,
                            "optional": True,
                            "as_cost": True,
                            "owner": "self",
                        },
                    )
                    ab["ops"] = ops
                    changed = True
                if not ab.get("rest_self"):
                    ab["rest_self"] = True
                    changed = True

        # Split mashed On Play that also compiled the [On K.O.] life-to-hand clause.
        on_ko_has_life = any(
            a.get("timing") == "on_ko"
            and any(o.get("op") == "life_to_hand" for o in (a.get("ops") or []))
            for a in abilities
        )
        if on_ko_has_life:
            for ab in abilities:
                if ab.get("timing") != "on_play":
                    continue
                ops = [o for o in (ab.get("ops") or []) if o.get("op") != "life_to_hand"]
                if ops != list(ab.get("ops") or []):
                    ab["ops"] = ops
                    changed = True

        if OWNER_HAND.search(paper):
            for ab in abilities:
                for op in ab.get("ops") or []:
                    if op.get("op") == "life_to_hand" and str(op.get("owner") or "") == "opponent":
                        if op.get("hand_owner") != "life_owner":
                            op["hand_owner"] = "life_owner"
                            changed = True

        m_trash_life = TRASH_TO_LIFE.search(paper)
        if m_trash_life:
            cost_lte = int(m_trash_life.group(1)) if m_trash_life.group(1) else None
            trait_zh = m_trash_life.group(2) or ""
            trait = BB if "黑鬍子" in trait_zh or "黑胡子" in trait_zh else trait_zh
            for ab in abilities:
                if ab.get("timing") not in {"on_play", "activate_main", "when_attacking"}:
                    continue
                ops = list(ab.get("ops") or [])
                has_life = any(o.get("op") == "add_from_trash" and o.get("destination") == "life" for o in ops)
                if has_life:
                    continue
                add_op: dict[str, Any] = {
                    "op": "add_from_trash",
                    "count": 1,
                    "optional": True,
                    "destination": "life",
                    "face": "up",
                    "position": "top",
                }
                if cost_lte is not None:
                    add_op["cost_lte"] = cost_lte
                if trait:
                    add_op["trait_contains"] = trait
                ops.append(add_op)
                ab["ops"] = ops
                changed = True

        if TRIG_NEGATE_CHAR_ONLY.search(paper):
            for ab in abilities:
                if ab.get("timing") != "trigger":
                    continue
                for op in ab.get("ops") or []:
                    if op.get("op") != "negate_effects":
                        continue
                    if op.get("target_kind") in {"opponent_leader_or_character", "leader"}:
                        op["target_kind"] = "opponent_character"
                        op["include_characters"] = True
                        op.pop("include_leader", None)
                        changed = True

        m_base = SET_BASE_OWN.search(paper)
        if m_base:
            amt = int(m_base.group(1))
            for ab in abilities:
                for op in ab.get("ops") or []:
                    if op.get("op") == "set_base_power":
                        if op.get("target_kind") != "own_leader_or_character":
                            op["target_kind"] = "own_leader_or_character"
                            changed = True
                        if int(op.get("amount") or 0) != amt:
                            op["amount"] = amt
                            changed = True
                        if not op.get("optional"):
                            op["optional"] = True
                            changed = True

        for ab in abilities:
            if ab.get("timing") != "on_ko":
                continue
            chunk = paper
            m_chunk = re.search(r"【KO時】[^【]+", paper)
            if m_chunk:
                chunk = m_chunk.group(0)
            if re.search(r"將最多1張自己卡組上面的卡片加入生命值區上面", chunk):
                if not any(o.get("op") == "add_life" for o in (ab.get("ops") or [])):
                    ops = list(ab.get("ops") or [])
                    ops.append({"op": "add_life", "count": 1, "optional": True, "position": "top"})
                    ab["ops"] = ops
                    changed = True
            elif re.search(r"手牌加入生命值區上面|加入對手的生命值區", chunk):
                ops = [o for o in (ab.get("ops") or []) if o.get("op") != "add_life"]
                if ops != list(ab.get("ops") or []):
                    ab["ops"] = ops
                    changed = True
            _store(ov_cards, lib_cards, cid, abilities)
            n += 1
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
