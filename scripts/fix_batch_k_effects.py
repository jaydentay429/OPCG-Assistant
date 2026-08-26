#!/usr/bin/env python3
"""Batch K: Rush OR, reveal-hand cost, Stage trash, hand Counter, field gates."""

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

LUFFY = "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫"
ACE = "Portgas.D.Ace|波特卡斯・D・艾斯"
WB = "Whitebeard Pirates|白鬍子海賊團"

REVEAL_DRAW = re.compile(
    r"可以公開\s*(\d+)\s*張自己手牌中力量值\s*(\d+)\s*的角色卡\s*[：:]\s*抽\s*(\d+)",
)
TRASH_PWR = re.compile(
    r"可以廢棄\s*(\d+)\s*張自己手牌中力量值\s*(\d+)\s*的角色卡",
)
UNRESTRICTED_ADD = re.compile(
    r"查看\s*(\d+)\s*張卡片.{0,80}將最多\s*1\s*張卡片加入手牌",
)
STAGE_TRASH = re.compile(r"可[將将]這[張张]舞台卡放置[在到]廢棄區\s*[：:]")
REST_DON = re.compile(r"休息狀態的咚")
NO_OWN_COST = re.compile(
    r"若場上沒有自己費用\s*(\d+)\s*以上擁有包含『([^』]+)』特徵的角色卡時[，,]"
    r"這張角色卡的力量值([+\-−]?\d+)",
)
PLAY_RESTED = re.compile(r"以休息狀態登場")
LUFFY_EN = re.compile(r"^Monkey\.D\.Luffy(?:\|Monkey\.D\.Luffy)?$")


def _paper(catalog: dict[str, Any], cid: str) -> str:
    info = catalog.get(cid) or {}
    return str(info.get("effect") or info.get("effect_text") or info.get("text") or "")


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


def _named(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-001",
        [
            {
                "timing": "activate_main",
                "summary": "Once: up to 1 own 8000+ Whitebeard Pirates Character or Luffy gains Rush",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "own_character",
                        "name_contains": LUFFY,
                        "trait_includes": WB,
                        "name_or_trait": True,
                        "power_gte": 8000,
                        "duration": "turn",
                        "optional": True,
                        "count": 1,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
            }
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
                "summary": "Attach 1 active DON!! to Leader/Character and trash this: opp Character −3000",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "as_cost": True,
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
                "cost_don": 0,
                "rest_self": False,
                "once": False,
            }
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-011",
        [
            {
                "timing": "on_play",
                "summary": "May reveal 1 hand Character power 8000: draw 1",
                "ops": [
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
                "timing": "when_attacking",
                "summary": "DON!!×1: KO up to 2 opp base power≤2000",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 2,
                        "base_power_lte": 2000,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 1,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-014",
        [
            {
                "timing": "your_turn",
                "summary": "If own Character would leave by opp effect, may KO this instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "trash_self",
                        "life_position": "top",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.85,
            },
            {
                "timing": "opponent_turn",
                "summary": "If own Character would leave by opp effect, may KO this instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "trash_self",
                        "life_position": "top",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.85,
            },
            {
                "timing": "on_ko",
                "summary": "Trash hand Character power 8000: play this from trash",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "card_type": "character",
                        "power_eq": 8000,
                        "owner": "self",
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": False,
                        "from_zone": "trash",
                        "self_card": True,
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
        "OP16-017",
        [
            {
                "timing": "your_turn",
                "summary": "If no own cost≥8 Character whose type includes Whitebeard Pirates: this −4000",
                "ops": [{"op": "buff_self", "amount": -4000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_no_own_char_cost_gte": 8,
                "require_chars_trait": WB,
            },
            {
                "timing": "opponent_turn",
                "summary": "If no own cost≥8 Character whose type includes Whitebeard Pirates: this −4000",
                "ops": [{"op": "buff_self", "amount": -4000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_no_own_char_cost_gte": 8,
                "require_chars_trait": WB,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-021",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Whitebeard Pirates: look 3, add up to 1 card; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 3,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": WB,
            },
            {
                "timing": "activate_main",
                "summary": "Trash this Stage: attach up to 1 rested DON!! to Leader or Character",
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
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "from_rested": True,
                        "as_rested": True,
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
        "OP16-118",
        [
            {
                "timing": "hand_cost",
                "summary": "Characters with power 8000 in hand become Counter +2000",
                "ops": [
                    {
                        "op": "hand_counter",
                        "amount": 2000,
                        "power_eq": 8000,
                        "card_type": "character",
                        "all": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_play",
                "summary": "Look 5: add up to 1 Luffy or type including Whitebeard Pirates; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": LUFFY,
                        "trait_contains": WB,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "name_or_trait": True,
                    }
                ],
                "status": "verified",
                "confidence": 0.95,
            },
            {
                "timing": "on_ko",
                "summary": "Look 5: add up to 1 Luffy or type including Whitebeard Pirates; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": LUFFY,
                        "trait_contains": WB,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "name_or_trait": True,
                    }
                ],
                "status": "verified",
                "confidence": 0.95,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST30-016",
        [
            {
                "timing": "counter_event",
                "summary": "+3000 this battle; then if own Ace and Luffy Characters base 6000, draw 1",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    },
                    {
                        "op": "draw",
                        "count": 1,
                        "require_own_name_all": [ACE, LUFFY],
                        "require_chars_base_power_eq": 6000,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )
    return n


def _store(ov_cards: dict, lib_cards: dict, cid: str, abilities: list[dict[str, Any]]) -> None:
    entry = normalize_card_entry(cid, {"version": 1, "abilities": abilities})
    ov_cards[cid] = entry
    lib_cards[cid] = {**entry, "card_id": cid}


def _patch_similar(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0
    ids = sorted({*catalog.keys(), *ov_cards.keys(), *lib_cards.keys()})
    for cid in ids:
        paper = _paper(catalog, cid)
        raw = ov_cards.get(cid) or lib_cards.get(cid)
        if not raw:
            continue
        abilities = [dict(a) for a in (raw.get("abilities") or [])]
        changed = False

        m_rev = REVEAL_DRAW.search(paper)
        if m_rev:
            count, power, draws = int(m_rev.group(1)), int(m_rev.group(2)), int(m_rev.group(3))
            for ab in abilities:
                if ab.get("timing") != "on_play":
                    continue
                ops = list(ab.get("ops") or [])
                if any(o.get("op") == "reveal_hand" for o in ops):
                    continue
                if not any(o.get("op") == "draw" for o in ops):
                    continue
                reveal = {
                    "op": "reveal_hand",
                    "count": count,
                    "optional": True,
                    "as_cost": True,
                    "card_type": "character",
                    "owner": "self",
                    "power_eq": power,
                }
                ab["ops"] = [reveal, *ops]
                changed = True

        m_tr = TRASH_PWR.search(paper)
        if m_tr:
            tcount, tpow = int(m_tr.group(1)), int(m_tr.group(2))
            for ab in abilities:
                ops = list(ab.get("ops") or [])
                for op in ops:
                    if op.get("op") != "trash_hand" or not op.get("as_cost"):
                        continue
                    if op.get("power_eq") is not None:
                        continue
                    op["power_eq"] = tpow
                    op["card_type"] = "character"
                    op["count"] = tcount
                    changed = True
                ab["ops"] = ops
                if PLAY_RESTED.search(paper) and ab.get("timing") == "on_ko":
                    for op in ops:
                        if op.get("op") == "play_from_hand" and op.get("self_card") and not op.get("as_rested"):
                            op["as_rested"] = True
                            changed = True

        m_un = UNRESTRICTED_ADD.search(paper)
        if m_un:
            chunk = paper[m_un.start() : m_un.end()]
            if "「" not in chunk and "特徵" not in chunk:
                for ab in abilities:
                    if ab.get("timing") != "on_play":
                        continue
                    ops = list(ab.get("ops") or [])
                    for op in ops:
                        if op.get("op") != "search_deck":
                            continue
                        if op.get("name_or_trait"):
                            continue
                        if op.get("trait_contains") or op.get("name_contains") or op.get("trait_any"):
                            op["trait_contains"] = ""
                            op["name_contains"] = ""
                            op.pop("trait_any", None)
                            changed = True
                    ab["ops"] = ops

        if STAGE_TRASH.search(paper) and REST_DON.search(paper):
            for ab in abilities:
                if ab.get("timing") != "activate_main":
                    continue
                ops = list(ab.get("ops") or [])
                if any(o.get("op") == "trash" for o in ops):
                    continue
                if not any(o.get("op") == "attach_don" for o in ops):
                    continue
                trash = {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True}
                new_ops = [trash]
                for op in ops:
                    if op.get("op") == "attach_don":
                        op = dict(op)
                        op["from_rested"] = True
                        op["as_rested"] = True
                    new_ops.append(op)
                ab["ops"] = new_ops
                changed = True

        m_no = NO_OWN_COST.search(paper)
        if m_no:
            cost_n = int(m_no.group(1))
            trait = m_no.group(2)
            amt = int(str(m_no.group(3)).replace("−", "-").replace("—", "-"))
            trait_enc = f"{trait}|Whitebeard Pirates" if "白鬍子" in trait else trait
            need = [
                {
                    "timing": "your_turn",
                    "summary": f"If no own cost≥{cost_n} Character whose type includes {trait}: this {amt}",
                    "ops": [{"op": "buff_self", "amount": amt}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_no_own_char_cost_gte": cost_n,
                    "require_chars_trait": trait_enc,
                },
                {
                    "timing": "opponent_turn",
                    "summary": f"If no own cost≥{cost_n} Character whose type includes {trait}: this {amt}",
                    "ops": [{"op": "buff_self", "amount": amt}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_no_own_char_cost_gte": cost_n,
                    "require_chars_trait": trait_enc,
                },
            ]
            if abilities != need:
                abilities = need
                changed = True

        for ab in abilities:
            ops = list(ab.get("ops") or [])
            for op in ops:
                nc = str(op.get("name_contains") or "")
                if LUFFY_EN.match(nc.strip()):
                    op["name_contains"] = LUFFY
                    changed = True
            ab["ops"] = ops

        if changed:
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
