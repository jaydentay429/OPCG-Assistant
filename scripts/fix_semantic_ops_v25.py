#!/usr/bin/env python3
"""Deterministic semantic fixes v25: look_deck, or_event, replace_leave, inject ops.

Dual-writes library + overrides.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from battle.effect_library import get_card_entry, library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability, normalize_card_entry, sanitize_op  # noqa: E402
from battle.effects import (  # noqa: E402
    _parse_hand_to_deck_ops,
    _parse_look_deck_ops,
    _parse_look_top_search,
    _parse_reorder_life_ops,
    _parse_replace_leave_ops,
    _parse_reveal_opp_hand_ops,
    effect_blob,
    parse_activate_main,
    parse_trigger_ops,
)
from fix_semantic_gates_v2 import LEADER_NAME_RE, LEADER_TRAIT_RE, _timing_chunk, _trim_cross_timing  # noqa: E402

OUT_IDS = ROOT / "meta" / "logs" / "ops_v25_fixed_ids.txt"

DIFF_COLOR_RE = re.compile(r"different color|不同顏色|不同颜色", re.I)
DRAW_RE = re.compile(r"draw\s*(\d+)\s*cards?|抽\s*(\d+)\s*[張张]", re.I)
TRASH_HAND_RE = re.compile(
    r"(?:your )?opponent trashes?\s*(\d+)\s*cards? from (?:their|the) hand|"
    r"對手廢棄\s*(\d+)\s*[張张].{0,12}手牌|对手废弃\s*(\d+)\s*[张張].{0,12}手牌|"
    r"(?:you may )?trash\s*(\d+)\s*cards? from your hand|"
    r"(?:可以)?廢棄\s*(\d+)\s*[張张]自己的手牌|废弃\s*(\d+)\s*[张張]自己的手牌",
    re.I,
)
BUFF_RE = re.compile(
    r"(?:gains?|give).{0,40}[+＋]\s*(\d{3,5})\s*power|"
    r"力量(?:值)?\s*[+＋]\s*(\d{3,5})",
    re.I,
)
FLIP_ALL_LIFE_RE = re.compile(
    r"turn all of your Life cards face-down|將自己全數的生命值卡翻成背面|将自己全数的生命值卡翻成背面",
    re.I,
)


def _ops_kinds(ops: list[dict[str, Any]]) -> set[str]:
    return {str(o.get("op") or "") for o in ops}


def _merge_op(ops: list[dict[str, Any]], new: dict[str, Any]) -> bool:
    kind = new.get("op")
    if not kind:
        return False
    # Prefer enriching existing same-op when unique
    same = [o for o in ops if o.get("op") == kind]
    if kind == "search_deck" and same:
        o = same[0]
        changed = False
        for k, v in new.items():
            if k == "op":
                continue
            if v in (None, "", False) and k not in {"order_bottom"}:
                continue
            if o.get(k) in (None, "", False) and v not in (None, "", False):
                o[k] = v
                changed = True
            elif k in {"or_event", "trash_rest", "as_rested", "different_color"} and v and not o.get(k):
                o[k] = v
                changed = True
            elif k in {"name_contains", "trait_contains"} and v and not o.get(k):
                o[k] = v
                changed = True
            elif k == "top_n" and int(o.get("top_n") or 0) != int(v or 0) and int(v or 0) > 0:
                # Prefer paper-parsed top_n when library defaulted to 5 wrongly
                if int(o.get("top_n") or 0) == 5 and int(v) != 5:
                    o[k] = v
                    changed = True
        return changed
    if kind in {"draw", "trash_hand", "buff", "buff_self", "look_deck", "reorder_life", "reveal_opp_hand", "hand_to_deck", "replace_leave"}:
        if kind == "draw" and any(o.get("op") == "draw" for o in ops):
            return False
        if kind == "look_deck" and any(o.get("op") == "look_deck" for o in ops):
            return False
        if kind == "replace_leave" and any(o.get("op") == "replace_leave" for o in ops):
            # Upgrade from replace_battle_ko by removing it later
            return False
        if kind == "hand_to_deck":
            for o in ops:
                if o.get("op") == "hand_to_deck":
                    ch = False
                    for k, v in new.items():
                        if k == "op":
                            continue
                        if v and not o.get(k):
                            o[k] = v
                            ch = True
                    return ch
        ops.append(new)
        return True
    if kind not in _ops_kinds(ops):
        ops.append(new)
        return True
    return False


def _choose_one_life(chunk: str) -> dict[str, Any] | None:
    if not re.search(r"Choose one:|選擇以下其中一項|选择以下其中一项", chunk, re.I):
        return None
    opts: list[dict[str, Any]] = []
    reorders = _parse_reorder_life_ops(chunk)
    if reorders:
        opts.append({"id": "reorder", "label": "Reorder Life", "ops": reorders})
    if FLIP_ALL_LIFE_RE.search(chunk):
        opts.append(
            {
                "id": "flip",
                "label": "Flip all Life face-down",
                "ops": [{"op": "flip_life", "face": "down", "all": True, "optional": False}],
            }
        )
    if len(opts) >= 2:
        return {"op": "choose_one", "chooser": "self", "options": opts, "summary": "Choose one Life option"}
    return None


def _choose_one_ko_bounce(chunk: str) -> dict[str, Any] | None:
    if not re.search(r"Choose one:|選擇以下其中一項|选择以下其中一项", chunk, re.I):
        return None
    if not re.search(r"K\.?O\.?|回手|return up to|place up to", chunk, re.I):
        return None
    # OP05-096 style cost≤1 three-way
    m = re.search(r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下", chunk, re.I)
    if not m:
        return None
    n = int(next(g for g in m.groups() if g))
    opts = [
        {
            "id": "ko",
            "label": "K.O.",
            "ops": [{"op": "ko", "count": 1, "cost_lte": n, "optional": True, "target_kind": "opponent_character"}],
        },
        {
            "id": "hand",
            "label": "Return to hand",
            "ops": [
                {
                    "op": "return_to_hand",
                    "count": 1,
                    "cost_lte": n,
                    "optional": True,
                    "target_kind": "opponent_character",
                }
            ],
        },
    ]
    if re.search(r"top or bottom of (?:the |your )?owner'?s? Life|生命值區上面或下面|生命值区上面或下面", chunk, re.I):
        opts.append(
            {
                "id": "life",
                "label": "Place on Life",
                "ops": [
                    {
                        "op": "place_on_life",
                        "count": 1,
                        "cost_lte": n,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "position": "top_or_bottom",
                        "owner": "opponent",
                    }
                ],
            }
        )
    if len(opts) >= 2:
        return {"op": "choose_one", "chooser": "self", "options": opts}
    return None


def fix_card(cid: str, info: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any] | None:
    blob = effect_blob(info)
    abs_in = [dict(a) for a in (entry.get("abilities") or []) if isinstance(a, dict)]
    if not abs_in:
        return None
    changed = False
    new_abs: list[dict[str, Any]] = []

    for a in abs_in:
        t = str(a.get("timing") or "")
        chunk = _trim_cross_timing(_timing_chunk(blob, t), t) or ""
        ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

        # Drop spurious replace_battle_ko when paper is leave-replace
        leave = _parse_replace_leave_ops(chunk) or _parse_replace_leave_ops(blob)
        if leave:
            before = len(ops)
            ops = [o for o in ops if o.get("op") not in {"replace_battle_ko"}]
            if len(ops) != before:
                changed = True
            for op in leave:
                if _merge_op(ops, op):
                    changed = True

        # Look-only → look_deck (replace bogus search_deck)
        look = _parse_look_deck_ops(chunk)
        if look:
            if any(o.get("op") == "search_deck" for o in ops) and not re.search(
                r"add (?:it|them) to your hand|加入手牌|play up to|登場", chunk, re.I
            ):
                ops = [o for o in ops if o.get("op") != "search_deck"]
                changed = True
            if _merge_op(ops, look[0]):
                changed = True

        # search enrich
        search = _parse_look_top_search(chunk)
        if search:
            if _merge_op(ops, search):
                changed = True

        # hand_to_deck include_self etc
        for op in _parse_hand_to_deck_ops(chunk):
            if _merge_op(ops, op):
                changed = True

        for op in _parse_reorder_life_ops(chunk):
            if _merge_op(ops, op):
                changed = True

        for op in _parse_reveal_opp_hand_ops(chunk):
            if _merge_op(ops, op):
                changed = True

        # choose_one expansions
        for builder in (_choose_one_life, _choose_one_ko_bounce):
            co = builder(chunk)
            if co:
                # replace empty/placeholder choose_one
                if any(o.get("op") == "choose_one" and not (o.get("options") or []) for o in ops):
                    ops = [o for o in ops if o.get("op") != "choose_one"]
                    ops.append(co)
                    changed = True
                elif not any(o.get("op") == "choose_one" for o in ops):
                    # if only flip_life present but paper is choose_one
                    if builder is _choose_one_life and any(o.get("op") == "flip_life" for o in ops):
                        ops = [o for o in ops if o.get("op") != "flip_life"]
                        ops.append(co)
                        changed = True
                    elif builder is _choose_one_ko_bounce:
                        ops.append(co)
                        changed = True

        # different_color play_from_hand: strip wrong trait
        if DIFF_COLOR_RE.search(chunk):
            for o in ops:
                if o.get("op") == "play_from_hand":
                    if o.get("trait_contains"):
                        o.pop("trait_contains", None)
                        changed = True
                    if not o.get("different_color"):
                        o["different_color"] = True
                        changed = True

        # inject draw
        m = DRAW_RE.search(chunk)
        if m and "draw" not in _ops_kinds(ops):
            # avoid injecting when look_deck-only
            if not look:
                n = int(next(g for g in m.groups() if g))
                ops.append({"op": "draw", "count": n})
                changed = True

        # inject trash_hand
        m = TRASH_HAND_RE.search(chunk)
        if m and "trash_hand" not in _ops_kinds(ops):
            n = int(next(g for g in m.groups() if g) or 1)
            owner = "opponent" if re.search(r"opponent trashes|對手廢棄|对手废弃", m.group(0), re.I) else "self"
            as_cost = bool(re.search(r":|：", chunk) and re.search(r"you may trash|可以廢棄|可以废弃", chunk, re.I))
            op = {"op": "trash_hand", "count": n, "owner": owner, "optional": as_cost or owner == "self"}
            if as_cost:
                op["as_cost"] = True
            ops.append(op)
            changed = True

        # inject simple buff if completely missing and paper has +power
        m = BUFF_RE.search(chunk)
        if m and not any(o.get("op") in {"buff", "buff_self", "buff_all_own"} for o in ops):
            amt = int(next(g for g in m.groups() if g))
            # skip if choose_one / complex
            if not re.search(r"Choose one|選擇以下|选择以下", chunk, re.I):
                tk = "leader_or_character"
                if re.search(r"this (?:Leader|Character)|這張|这张", chunk, re.I):
                    ops.append({"op": "buff_self", "amount": amt})
                else:
                    ops.append({"op": "buff", "amount": amt, "target_kind": "own_character", "optional": True})
                changed = True

        # activate refill if empty
        if t == "activate_main" and not ops:
            parsed = parse_activate_main(info)
            if parsed and parsed.get("ops"):
                ops = list(parsed["ops"])
                for k, v in parsed.items():
                    if str(k).startswith("require_") and v and not a.get(k):
                        a[k] = v
                        changed = True
                changed = True
        if t == "trigger" and not ops:
            tops = parse_trigger_ops(info)
            if tops:
                ops = list(tops)
                changed = True

        # Spurious leader gate: ability chunk has no Leader mention
        if (a.get("require_leader_trait") or a.get("require_leader_name")) and chunk:
            if not re.search(r"Leader|領航|领航", chunk, re.I):
                # Keep if cost_don payment-then-if pattern (gate is soft) — still drop for on_play/main when clearly wrong
                if t in {"on_play", "when_attacking", "counter_event"} or (
                    t == "main_start" and not re.search(r"若自己的領航|若自己的领航|If your Leader", blob, re.I)
                ):
                    a.pop("require_leader_trait", None)
                    a.pop("require_leader_name", None)
                    changed = True

        # Drop empty your_turn junk when opponent_turn has the real effect
        if t == "your_turn" and any(o.get("op") in {"replace_battle_ko"} for o in ops):
            if re.search(r"\[Opponent'?s? Turn\]|【對方回合中】|【对方回合中】", blob, re.I) and not re.search(
                r"\[Your Turn\]|【我方回合中】", chunk, re.I
            ):
                changed = True
                continue  # drop ability

        a["ops"] = [sanitize_op(o) for o in ops if sanitize_op(o)]
        na = normalize_ability(a)
        if na:
            new_abs.append(na)

    # Ensure continuous replace_leave abilities exist when paper has untimed leave text
    if leave := _parse_replace_leave_ops(blob):
        if not any(
            o.get("op") == "replace_leave" for a in new_abs for o in (a.get("ops") or [])
        ):
            new_abs.append(
                normalize_ability(
                    {
                        "timing": "your_turn" if leave[0].get("trigger") != "opp_remove" else "opponent_turn",
                        "summary": leave[0].get("summary") or "replace_leave",
                        "ops": leave,
                        "status": "compiled",
                        "confidence": 0.85,
                    }
                )
            )
            changed = True

    if not changed or not new_abs:
        return None
    return normalize_card_entry(cid, {"version": 1, "abilities": new_abs})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    q = json.loads((ROOT / "meta" / "effect_problem_queue.json").read_text())
    open_ids = [it["id"] for it in q["items"] if it.get("status") == "open"]
    if args.limit:
        open_ids = open_ids[: args.limit]

    lib_path, ovr_path = library_paths()
    raw = json.loads(lib_path.read_text())
    cards = raw["cards"]
    ovr = json.loads(ovr_path.read_text())
    overrides = ovr.get("cards") or {}

    fixed: list[str] = []
    for cid in open_ids:
        info = catalog.get(cid) or {}
        entry = cards.get(cid) or get_card_entry(cid)
        if not entry:
            continue
        out = fix_card(cid, info, entry)
        if not out:
            continue
        cards[cid] = out
        overrides[cid] = out
        fixed.append(cid)

    raw["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    lib_path.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")))
    ovr["cards"] = overrides
    ovr["generated_at"] = raw["generated_at"]
    ovr_path.write_text(json.dumps(ovr, ensure_ascii=False, separators=(",", ":")))
    reload_effect_library(force=True)

    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    OUT_IDS.write_text("\n".join(fixed) + ("\n" if fixed else ""))
    print(json.dumps({"fixed": len(fixed), "ids_file": str(OUT_IDS)}, ensure_ascii=False))
    for cid in ["EB01-020", "EB01-030", "EB01-052", "EB04-029", "OP05-096", "OP07-090", "OP10-032", "P-074", "ST12-014"]:
        if cid in fixed or True:
            e = get_card_entry(cid)
            print(
                cid,
                [
                    (
                        a.get("timing"),
                        [o.get("op") for o in (a.get("ops") or [])],
                        {k: a[k] for k in a if k.startswith("require_")},
                    )
                    for a in (e.get("abilities") or [])
                ],
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
