#!/usr/bin/env python3
"""Batch J: any-number rest DON, if_trashed, this-turn-end, trigger cost leak."""

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

ANY_REST_DON = re.compile(r"任意張數的咚|any number of your DON", re.I)
THIS_TURN_END = re.compile(r"這回合結束時|這個回合結束時|at the end of this turn", re.I)
END_OF_YOUR = re.compile(r"【我方回合結束時】")
IF_YOU_DO = re.compile(r"若有執行此動作|If you do[,:]", re.I)
MAY_REST_DON = re.compile(
    r"可將\s*\d+\s*張自己的咚|You may rest \d+ of your DON",
    re.I,
)
KEEP_OPTIONAL_REST_DON = ("OP13-040", "OP12-018")
NAMI_EXCLUDE = re.compile(r"除了「娜美」|other than\s*\[Nami\]", re.I)
ON_PLAY_CHUNK = re.compile(
    r"【登場時】(.+?)(?=【(?:我方回合結束時|攻擊時|啟動主要|對方攻擊時|觸發器|反擊|防禦時)】|$)",
    re.S,
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


def _named(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-001",
        [
            {
                "timing": "on_opponent_attack",
                "summary": "DON!!×1: if active DON!!≤5, may rest any DON!!; +2000 per rested this way to Leader or 1 Straw Hat",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 10,
                        "owner": "self",
                        "any_number": True,
                        "optional": True,
                    },
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "count": 1,
                        "trait_contains": "Straw Hat Crew|草帽一行人",
                        "duration": "battle",
                        "per_rested_don": 1,
                        "summary": "+2000 per DON!! rested this way to Leader or Straw Hat Character",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 1,
                "require_don_active_lte": 5,
            }
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP05-038",
        [
            {
                "timing": "counter_event",
                "summary": "+4000 this battle; then may trash 1; if you do, active up to 3 DON!!",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 4000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    },
                    {"op": "trash_hand", "count": 1, "optional": True, "owner": "self"},
                    {"op": "active_don", "count": 3, "optional": True, "if_trashed": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Rest up to 1 opp Leader or Character cost≤3",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "include_leader": True,
                        "cost_lte": 3,
                        "optional": True,
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
                "summary": "All opp rested Characters cost≤7 skip next Refresh",
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
                "ops": [
                    {"op": "rest_opponent_character", "count": 1, "optional": True},
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
        "OP13-027",
        [
            {
                "timing": "on_play",
                "summary": "Set up to 2 own DON!! as active",
                "ops": [{"op": "active_don", "count": 2, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "end_of_your_turn",
                "summary": "If Leader FILM or Straw Hat: set up to 1 DON!! active",
                "ops": [{"op": "active_don", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": "FILM|Straw Hat Crew|草帽一行人",
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-031",
        [
            {
                "timing": "your_turn",
                "summary": "Blocker",
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
            },
            {
                "timing": "on_play",
                "summary": "Rest up to 2 opp cost≤8; at end of this turn active up to 5 DON!!",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 2,
                        "cost_lte": 8,
                        "optional": True,
                    },
                    {"op": "active_don", "count": 5, "optional": True, "at_end_of_turn": True},
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
                        "include_leader": True,
                        "include_stage": True,
                        "duration": "turn",
                        "per_own_chars": 1,
                        "per_own_trait": "Straw Hat Crew",
                        "per_choose": True,
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
                "summary": "May rest 2 DON!!: up to 2 opp rested cost≤7 skip untap until opp refresh",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 2,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "skip_untap",
                        "count": 2,
                        "target_kind": "opponent_character_rested",
                        "cost_lte": 7,
                        "optional": True,
                        "summary": "Up to 2 opp rested Characters cost≤7 skip next untap",
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
        "EB02-017",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5; add up to 1 Straw Hat other than Nami; rest to bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "trait_contains": "Straw Hat Crew",
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": "Nami|娜美",
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
        "OP01-016",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5; add up to 1 Straw Hat other than Nami; rest to bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "trait_contains": "Straw Hat Crew",
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": "Nami|娜美",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )
    return n


def _entry_of(ov_cards: dict, lib_cards: dict, cid: str) -> dict[str, Any]:
    return ov_cards.get(cid) or lib_cards.get(cid) or {}


def _patch_similar(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0
    ids = sorted(set(catalog) | set(ov_cards) | set(lib_cards))

    def store(cid: str, abilities: list[dict[str, Any]]) -> None:
        nonlocal n
        entry = normalize_card_entry(cid, {"version": 1, "abilities": abilities})
        ov_cards[cid] = entry
        lib_cards[cid] = {**entry, "card_id": cid}
        n += 1

    for cid in ids:
        info = catalog.get(cid) or {}
        paper = str(info.get("effect") or "")
        paper_en = str(info.get("effect_en") or "")
        blob = f"{paper}\n{paper_en}"
        raw = _entry_of(ov_cards, lib_cards, cid)
        abilities = [dict(a) for a in (raw.get("abilities") or [])]
        if not abilities:
            continue
        changed = False

        if ANY_REST_DON.search(blob):
            for ab in abilities:
                ops = list(ab.get("ops") or [])
                for op in ops:
                    if op.get("op") != "rest_don":
                        continue
                    if not op.get("any_number"):
                        op["any_number"] = True
                        op["optional"] = True
                        op.pop("as_cost", None)
                        op["count"] = max(int(op.get("count") or 10), 10)
                        changed = True
                ab["ops"] = ops

        if IF_YOU_DO.search(blob):
            for ab in abilities:
                ops = list(ab.get("ops") or [])
                for i, op in enumerate(ops):
                    if op.get("op") != "trash_hand":
                        continue
                    if op.get("as_cost") and not op.get("optional", True):
                        continue
                    for later in ops[i + 1 :]:
                        if later.get("op") in {"trash_hand", "rest_don"}:
                            continue
                        if later.get("if_trashed"):
                            continue
                        later["if_trashed"] = True
                        changed = True
                ab["ops"] = ops

        if THIS_TURN_END.search(blob) and not END_OF_YOUR.search(paper):
            eot = [a for a in abilities if a.get("timing") == "end_of_your_turn"]
            hosts = [
                a
                for a in abilities
                if a.get("timing") in {"on_play", "when_attacking", "activate_main", "counter_event"}
            ]
            if eot and hosts:
                host = hosts[0]
                host_ops = list(host.get("ops") or [])
                for ab in eot:
                    for op in list(ab.get("ops") or []):
                        moved = dict(op)
                        moved["at_end_of_turn"] = True
                        host_ops.append(moved)
                        changed = True
                host["ops"] = host_ops
                abilities = [a for a in abilities if a.get("timing") != "end_of_your_turn"]

        m_play = ON_PLAY_CHUNK.search(paper)
        if m_play:
            chunk = (m_play.group(1) or "").strip()
            if chunk and chunk not in {"/", "／"} and "領航" not in chunk and "Leader" not in chunk:
                for ab in abilities:
                    if ab.get("timing") != "on_play":
                        continue
                    if ab.get("require_leader_trait"):
                        ab.pop("require_leader_trait", None)
                        changed = True

        if "【觸發器】" in paper:
            trig = paper.split("【觸發器】", 1)[-1]
            if not re.search(r"費用|费用|cost", trig, re.I):
                for ab in abilities:
                    if ab.get("timing") != "trigger":
                        continue
                    ops = list(ab.get("ops") or [])
                    for op in ops:
                        if op.get("op") != "rest_opponent_character":
                            continue
                        for key in ("cost_lte", "cost_eq", "cost_gte"):
                            if key in op:
                                op.pop(key, None)
                                changed = True
                    ab["ops"] = ops

        if NAMI_EXCLUDE.search(blob):
            for ab in abilities:
                ops = list(ab.get("ops") or [])
                for op in ops:
                    if op.get("op") != "search_deck":
                        continue
                    excl = str(op.get("exclude_name") or "")
                    if "娜美" not in excl:
                        op["exclude_name"] = "Nami|娜美" if not excl or excl.lower() == "nami" else f"{excl}|娜美"
                        changed = True
                ab["ops"] = ops

        # Revert mass optional-on-rest_don from the first J pass (keep named OP13-040).
        if MAY_REST_DON.search(blob) and not cid.startswith(KEEP_OPTIONAL_REST_DON):
            for ab in abilities:
                ops = list(ab.get("ops") or [])
                for op in ops:
                    if op.get("op") != "rest_don":
                        continue
                    if op.get("as_cost") and op.get("optional") and not op.get("any_number"):
                        op.pop("optional", None)
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
