#!/usr/bin/env python3
"""Batch I: Enel DON-deck cap, look-deck reorder, name-or-event, DON costs."""

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

ENEL = "Enel|艾涅爾|艾尼尔"
SANJI = "Sanji|香吉士"

OR_EVENT = re.compile(r"「([^」]+)」或事件卡?")
LOOK_REORDER = re.compile(
    r"查看\s*(\d+)\s*[張张].{0,80}(?:卡組)?上面或下面|"
    r"look at\s*(\d+)\s*cards?.{0,80}top or bottom",
    re.I,
)
DON_FIELD_LTE6 = re.compile(r"自己場上的咚.{0,12}在\s*6\s*張以下|you have 6 or less DON", re.I)
SKIP_UNTAP = re.compile(r"無法為活動|无法为活动|will not become active", re.I)
POWER_LTE = re.compile(r"力量值\s*(\d+)\s*以下|(\d+)\s*power or less", re.I)
DON_COLON = re.compile(r"咚‼?\s*[-−]\s*(\d+).{0,40}[：:]")
DON_TRASH = re.compile(r"咚‼?\s*[-−]\s*(\d+)\s*,\s*可以廢棄")
COUNTER_NAMED = re.compile(r"【反擊】最多1張自己的「([^」]+)」")
ADD_HAND = re.compile(r"加入手牌|使最多.{0,20}登場|add (?:it|them|up to).{0,40}hand|play up to", re.I)


def _variants(catalog: dict[str, Any], base: str) -> list[str]:
    out = [base]
    out.extend(sorted(k for k in catalog if k.startswith(base + "-")))
    return [c for c in out if c in catalog or c == base]


def _write(ov_cards: dict, lib_cards: dict, catalog: dict, cid: str, abilities: list[dict[str, Any]]) -> int:
    entry = normalize_card_entry(cid, {"version": 1, "abilities": abilities})
    n = 0
    for vid in _variants(catalog, cid):
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
        "OP15-058",
        [
            {
                "timing": "your_turn",
                "summary": "Rule: DON!! deck size is 6",
                "ops": [{"op": "rule_don_deck_size", "count": 6}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once after your 2nd turn: +1 active DON!!, +up to 4 rested; attach up to 4 rested to 1 own Character",
                "ops": [
                    {"op": "gain_don", "count": 1, "optional": True},
                    {"op": "gain_don", "count": 4, "as_rested": True, "optional": True},
                    {
                        "op": "attach_don",
                        "count": 4,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "own_character",
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_turn_gte": 2,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-072",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −2, you may trash 1 hand: draw 2",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {"op": "return_don", "count": 2, "as_cost": True, "owner": "self"},
                    {"op": "draw", "count": 2},
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
        "OP10-067",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −1: add purple Event cost≤5 from trash; then set 1 DON!! active",
                "ops": [
                    {"op": "return_don", "count": 1, "as_cost": True, "owner": "self"},
                    {
                        "op": "add_from_trash",
                        "count": 1,
                        "optional": True,
                        "card_type": "event",
                        "color": "purple",
                        "cost_lte": 5,
                    },
                    {"op": "active_don", "count": 1, "optional": True},
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
        "OP12-063",
        [
            {
                "timing": "your_turn",
                "summary": "If trash Events≥4: this +2000 power and +5 cost",
                "ops": [
                    {"op": "buff_self", "amount": 2000},
                    {"op": "grant_cost", "amount": 5, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_trash_events_gte": 4,
            },
            {
                "timing": "opponent_turn",
                "summary": "If trash Events≥4: this +2000 power and +5 cost",
                "ops": [
                    {"op": "buff_self", "amount": 2000},
                    {"op": "grant_cost", "amount": 5, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_trash_events_gte": 4,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-071",
        [
            {
                "timing": "on_play",
                "summary": "Look 4: add up to 1 Sanji or Event; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": SANJI,
                        "or_event": True,
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
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
        "OP15-061",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −1: draw 1",
                "ops": [
                    {"op": "return_don", "count": 1, "as_cost": True},
                    {"op": "draw", "count": 1},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "If DON!! field ≤6: up to 1 opp Character −1000",
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
                "require_don_field_lte": 6,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-066",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −1: draw 1",
                "ops": [
                    {"op": "return_don", "count": 1, "as_cost": True},
                    {"op": "draw", "count": 1},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "If DON!! field ≤6: look 2, place top or bottom",
                "ops": [{"op": "look_deck", "count": 2, "position": "top_or_bottom"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_lte": 6,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-074",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −1: if Leader Enel, draw 1; up to 1 own Character +2 cost until opp end",
                "ops": [
                    {"op": "return_don", "count": 1, "as_cost": True, "owner": "self"},
                    {"op": "draw", "count": 1},
                    {
                        "op": "grant_cost",
                        "amount": 2,
                        "target_kind": "own_character",
                        "optional": True,
                        "count": 1,
                        "duration": "until_opp_turn_end",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": ENEL,
            },
            {
                "timing": "counter_event",
                "summary": "Up to 1 own Enel +2000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "count": 1,
                        "name_contains": ENEL,
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
        "OP15-075",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −1: if Leader Enel, +1000 to 1 own Leader/Character; KO opp ≤3000",
                "ops": [
                    {"op": "return_don", "count": 1, "as_cost": True},
                    {
                        "op": "buff",
                        "amount": 1000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "turn",
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "power_lte": 3000,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": ENEL,
            },
            {
                "timing": "counter_event",
                "summary": "Up to 1 own Enel +2000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "count": 1,
                        "name_contains": ENEL,
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
        "OP15-076",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −1: if Leader Enel, draw 1; opp Character −1000",
                "ops": [
                    {"op": "return_don", "count": 1, "as_cost": True, "owner": "self"},
                    {"op": "draw", "count": 1},
                    {
                        "op": "buff",
                        "amount": -1000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 1,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": ENEL,
            },
            {
                "timing": "counter_event",
                "summary": "Up to 1 own Enel +2000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "count": 1,
                        "name_contains": ENEL,
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
        "OP15-077",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −1: draw 1; skip untap 1 rested opp Character power≤6000",
                "ops": [
                    {"op": "return_don", "count": 1, "as_cost": True, "owner": "self"},
                    {"op": "draw", "count": 1},
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "opponent_character_rested",
                        "optional": True,
                        "power_lte": 6000,
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
        "OP15-078",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −2: draw 1; rest up to 1 opp Character power≤5000",
                "ops": [
                    {"op": "return_don", "count": 2, "as_cost": True, "owner": "self"},
                    {"op": "draw", "count": 1},
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "power_lte": 5000,
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "Up to 1 own Leader/Character +1000 this battle; then if DON!! field≤6 draw 1",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 1000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    },
                    {"op": "draw", "count": 1, "require_don_field_lte": 6},
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
        "OP15-118",
        [
            {
                "timing": "your_turn",
                "summary": "DON!! field ≤6: cannot leave by opponent effects +2000",
                "ops": [
                    {"op": "cannot_be_removed", "target_kind": "self", "any_leave": True, "optional": False},
                    {"op": "buff_self", "amount": 2000},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_lte": 6,
            },
            {
                "timing": "opponent_turn",
                "summary": "DON!! field ≤6: cannot leave by opponent effects +2000",
                "ops": [
                    {"op": "cannot_be_removed", "target_kind": "self", "any_leave": True, "optional": False},
                    {"op": "buff_self", "amount": 2000},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_lte": 6,
            },
            {
                "timing": "on_play",
                "summary": "DON!! −1: look top 5 add 1; rest bottom; trash 1 hand",
                "ops": [
                    {"op": "return_don", "count": 1, "as_cost": True, "owner": "self"},
                    {
                        "op": "search_deck",
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": False,
                    },
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )
    return n


def _name_en(zh: str) -> str:
    table = {
        "香吉士": "Sanji",
        "艾涅爾": "Enel",
        "艾尼尔": "Enel",
        "蒙其・D・魯夫": "Monkey.D.Luffy",
    }
    return table.get(zh, zh)


def _patch_similar(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0

    def store(cid: str, abilities: list[dict[str, Any]]) -> None:
        nonlocal n
        entry = normalize_card_entry(cid, {"version": 1, "abilities": abilities})
        ov_cards[cid] = entry
        lib_cards[cid] = entry
        n += 1

    for cid, info in catalog.items():
        text = f"{info.get('effect') or ''} {info.get('effect_en') or ''}"
        entry = ov_cards.get(cid) or lib_cards.get(cid) or {}
        abilities = [dict(a) for a in (entry.get("abilities") or [])]
        if not abilities:
            continue
        changed = False

        m_or = OR_EVENT.search(info.get("effect") or "")
        if m_or:
            zh = m_or.group(1)
            needle = f"{_name_en(zh)}|{zh}"
            for ab in abilities:
                ops = list(ab.get("ops") or [])
                for op in ops:
                    if op.get("op") != "search_deck":
                        continue
                    if op.get("or_event"):
                        continue
                    op["or_event"] = True
                    op["name_contains"] = needle
                    changed = True
                ab["ops"] = ops

        if LOOK_REORDER.search(text) and not ADD_HAND.search(text):
            m = LOOK_REORDER.search(text)
            look_n = int(next(g for g in m.groups() if g))
            for ab in abilities:
                ops = list(ab.get("ops") or [])
                new_ops: list[dict[str, Any]] = []
                for op in ops:
                    if op.get("op") == "search_deck" and not op.get("name_contains") and not op.get("trait_contains"):
                        new_ops.append({"op": "look_deck", "count": look_n, "position": "top_or_bottom"})
                        changed = True
                    elif op.get("op") == "look_deck":
                        op["count"] = look_n
                        op["position"] = "top_or_bottom"
                        new_ops.append(op)
                    else:
                        new_ops.append(op)
                ab["ops"] = new_ops

        if DON_FIELD_LTE6.search(text):
            for ab in abilities:
                if ab.get("timing") != "when_attacking":
                    continue
                if ab.get("require_don_field_lte") is None:
                    ab["require_don_field_lte"] = 6
                    changed = True

        if SKIP_UNTAP.search(text):
            m_pow = POWER_LTE.search(text)
            if m_pow:
                plte = int(next(g for g in m_pow.groups() if g))
                for ab in abilities:
                    ops = list(ab.get("ops") or [])
                    for op in ops:
                        if op.get("op") == "skip_untap" and op.get("power_lte") is None:
                            op["power_lte"] = plte
                            changed = True
                    ab["ops"] = ops

        m_dt = DON_TRASH.search(info.get("effect") or "")
        if m_dt:
            don_n = int(m_dt.group(1))
            for ab in abilities:
                if ab.get("timing") != "on_play":
                    continue
                ops = list(ab.get("ops") or [])
                for op in ops:
                    if op.get("op") == "return_don" and not op.get("as_cost"):
                        op["as_cost"] = True
                        op["count"] = don_n
                        changed = True
                    if op.get("op") == "trash_hand" and not op.get("as_cost"):
                        op["as_cost"] = True
                        op["optional"] = True
                        changed = True
                kinds = [o.get("op") for o in ops]
                if "trash_hand" in kinds and "return_don" in kinds:
                    ti = kinds.index("trash_hand")
                    ri = kinds.index("return_don")
                    if ri < ti:
                        ops[ri], ops[ti] = ops[ti], ops[ri]
                        changed = True
                ab["ops"] = ops

        m_colon = DON_COLON.search(info.get("effect") or "")
        if m_colon and not m_dt:
            don_n = int(m_colon.group(1))
            for ab in abilities:
                if ab.get("timing") not in {"on_play", "when_attacking", "activate_main"}:
                    continue
                ops = list(ab.get("ops") or [])
                for op in ops:
                    if op.get("op") == "return_don" and int(op.get("count") or 0) == don_n and not op.get("as_cost"):
                        op["as_cost"] = True
                        changed = True
                kinds = [o.get("op") for o in ops]
                if "return_don" in kinds and "draw" in kinds:
                    ri = kinds.index("return_don")
                    di = kinds.index("draw")
                    if di < ri:
                        ops[di], ops[ri] = ops[ri], ops[di]
                        changed = True
                ab["ops"] = ops

        m_ctr = COUNTER_NAMED.search(info.get("effect") or "")
        if m_ctr:
            zh = m_ctr.group(1)
            needle = f"{_name_en(zh)}|{zh}"
            for ab in abilities:
                if ab.get("timing") not in {"counter_event", "counter"}:
                    continue
                ops = list(ab.get("ops") or [])
                for op in ops:
                    if op.get("op") != "buff":
                        continue
                    tk = str(op.get("target_kind") or "")
                    if tk in {"own_character", "own_character_or_leader"}:
                        op["target_kind"] = "own_leader_or_character"
                        op["name_contains"] = needle
                        op.setdefault("duration", "battle")
                        changed = True
                    elif tk == "own_leader_or_character" and not op.get("name_contains"):
                        op["name_contains"] = needle
                        op.setdefault("duration", "battle")
                        changed = True
                    if op.get("duration") != "battle" and "這場對戰" in (info.get("effect") or ""):
                        op["duration"] = "battle"
                        changed = True
                ab["ops"] = ops

        if changed:
            store(cid, abilities)
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
