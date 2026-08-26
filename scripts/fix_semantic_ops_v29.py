#!/usr/bin/env python3
"""Deterministic semantic fixes v29: choose_one, gates, deck zone, continuous auras.

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
from battle.effect_schema import normalize_ability, normalize_card_entry  # noqa: E402
from battle.effects import effect_blob  # noqa: E402
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

OUT_IDS = ROOT / "meta" / "logs" / "ops_v29_fixed_ids.txt"

DRAW_UNTIL_HAND_RE = re.compile(
    r"Draw card\(s\) so that you have\s*(\d+)\s*cards? in your hand|"
    r"抽取卡片使自己的手牌有\s*(\d+)\s*[張张]|"
    r"抽取卡片使自己的手牌有(\d+)[張张]",
    re.I,
)
OWN_NAME_BUFF_RE = re.compile(
    r"If you have \[([^\]]+)\].{0,40}gains?\s*[+＋]\s*(\d{3,5})\s*power|"
    r"若場上有自己的「([^」]+)」時.{0,40}力量值\s*[+＋]\s*(\d{3,5})|"
    r"若场上有自己的「([^」]+)」时.{0,40}力量值\s*[+＋]\s*(\d{3,5})",
    re.I,
)
OPP_DON_GTE_RE = re.compile(
    r"If your opponent has\s*(\d+)\s*or more DON!! cards on their field|"
    r"若對手場上的咚‼?卡有\s*(\d+)\s*[張张]以上|"
    r"若对手场上的咚‼?卡有\s*(\d+)\s*[张張]以上",
    re.I,
)
CHOOSE_TRASH_OR_COST_RE = re.compile(
    r"choose one:.{0,20}opponent trashes?\s*1.{0,80}Give up to 1.{0,40}−\s*(\d+)\s*cost|"
    r"選擇下列其中一項。.{0,20}對手廢棄1[張张].{0,80}費用\s*[-−]\s*(\d+)|"
    r"选择下列其中一项。.{0,20}对手废弃1[张張].{0,80}费用\s*[-−]\s*(\d+)",
    re.I | re.S,
)
CHOOSE_DRAW_OR_LIFE_RE = re.compile(
    r"draw 1 card\..{0,40}Character with a cost of\s*(\d+)\s*or more.{0,80}Life cards instead|"
    r"抽1[張张]卡片。.{0,40}費用\s*(\d+)\s*以上.{0,80}生命值|"
    r"抽1[张張]卡片。.{0,40}费用\s*(\d+)\s*以上.{0,80}生命值",
    re.I | re.S,
)
NEXT_HAND_COST_RE = re.compile(
    r"the next time you play a \{([^}]+)\} type Character card with a cost of\s*(\d+)\s*or more"
    r".{0,80}cost will be reduced by\s*(\d+)|"
    r"接下來使自己手牌中費用(\d+)以上擁有《([^》]+)》特徵的角色卡登場的支付費用減少(\d+)|"
    r"接下来使自己手牌中费用(\d+)以上拥有《([^》]+)》特征的角色卡登场的支付费用减少(\d+)",
    re.I,
)
GRANT_NAMED_BLOCKER_RE = re.compile(
    r"Your \[([^\]]+)\] gains \[Blocker\]|"
    r"自己的「([^」]+)」獲得【防禦】|自己的「([^」]+)」获得【防御】",
    re.I,
)
SELF_BLOCKER_IF_NAME_RE = re.compile(
    r"If you have \[([^\]]+)\] on your field, this Character gains \[Blocker\]|"
    r"若自己場上有「([^」]+)」時，這張角色卡獲得【防禦】|"
    r"若自己场上有「([^」]+)」时，这张角色卡获得【防御】",
    re.I,
)
ATTACH_GIVEN_DON_RE = re.compile(
    r"Give up to\s*(\d+)\s*total of your currently given DON!! cards to 1 of your Characters|"
    r"附加合計最多(\d+)[張张]自己被附加的咚|"
    r"附加合计最多(\d+)[张張]自己被附加的咚",
    re.I,
)
PLAY_NAMED_FROM_DECK_RE = re.compile(
    r"Play up to 1 \[([^\]]+)\] with a cost of\s*(\d+)\s*or less from your deck|"
    r"使最多1[張张]自己卡組中費用(\d+)以下的「([^」]+)」登場|"
    r"使最多1[张張]自己卡组中费用(\d+)以下的「([^」]+)」登场",
    re.I,
)
LAND_WANO_FROM_DECK_RE = re.compile(
    r"Play up to 1 green \{Land of Wano\} type Character card with a cost of\s*(\d+)\s*from your deck|"
    r"使最多1[張张]自己卡組中費用(\d+)綠色擁有《和之國》|"
    r"使最多1[张張]自己卡组中费用(\d+)绿色拥有《和之国》",
    re.I,
)
NAVY_REPLACE_RE = re.compile(
    r"If your \{Navy\} type Character with\s*(\d+)\s*base power or less would be removed|"
    r"自己原本力量值(\d+)以下擁有《海軍》特徵的角色卡即將離開|"
    r"自己原本力量值(\d+)以下拥有《海军》特征的角色卡即将离开",
    re.I,
)
SWORD_RUSH_RE = re.compile(
    r"Your \{SWORD\} type Characters can attack Characters on the turn|"
    r"自己擁有《SWORD》特徵的角色卡在登場的回合即可攻擊角色|"
    r"自己拥有《SWORD》特征的角色卡在登场的回合即可攻击角色",
    re.I,
)
OPP_KO_DRAW_RE = re.compile(
    r"When your opponent's Character is K\.O\.?'?d,\s*draw\s*1|"
    r"對手的角色卡遭到KO時，抽1[張张]|对手的角色卡遭到KO时，抽1[张張]",
    re.I,
)
REVEAL_PLAY_RESTED_RE = re.compile(
    r"Reveal 1 card from the top of your deck and play up to 1 Character card with a cost of\s*(\d+)\s*rested|"
    r"公開1[張张]自己卡組上面的卡片.{0,40}使最多1[張张]費用(\d+).{0,20}休息|"
    r"公开1[张張]自己卡组上面的卡片.{0,40}使最多1[张張]费用(\d+).{0,20}休息",
    re.I,
)
TOTAL_LIFE_HAND_LTE_RE = re.compile(
    r"total of\s*(\d+)\s*or less cards in your Life area and hand|"
    r"生命值區和手牌的卡片合計在(\d+)[張张]以下|"
    r"生命值区和手牌的卡片合计在(\d+)[张張]以下",
    re.I,
)


def _clone_continuous_to_opp_turn(abilities: list[dict[str, Any]]) -> bool:
    """If a permanent grant sits only on your_turn, mirror onto opponent_turn."""
    changed = False
    your = [a for a in abilities if a.get("timing") == "your_turn"]
    opp_timings = {id(a) for a in abilities if a.get("timing") == "opponent_turn"}
    for a in your:
        ops = a.get("ops") or []
        if not any(
            o.get("op") == "grant_keyword" and o.get("keyword") in {"blocker", "rush_character"}
            for o in ops
        ):
            continue
        if a.get("on_opp_ko"):
            continue
        # already mirrored?
        sig = json.dumps({"ops": ops, "gates": {k: a.get(k) for k in a if str(k).startswith("require_")}}, sort_keys=True)
        has = False
        for b in abilities:
            if b.get("timing") != "opponent_turn":
                continue
            sig2 = json.dumps(
                {"ops": b.get("ops") or [], "gates": {k: b.get(k) for k in b if str(k).startswith("require_")}},
                sort_keys=True,
            )
            if sig == sig2:
                has = True
                break
        if has:
            continue
        twin = dict(a)
        twin["timing"] = "opponent_turn"
        abilities.append(twin)
        changed = True
    return changed


def fix_card(cid: str, info: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any] | None:
    blob = effect_blob(info)
    new_abs: list[dict[str, Any]] = [dict(a) for a in (entry.get("abilities") or []) if isinstance(a, dict)]
    changed = False

    for a in new_abs:
        t = str(a.get("timing") or "")
        chunk = _trim_cross_timing(_timing_chunk(blob, t), t) or ""
        ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

        # OP02-111 style name gate
        m = OWN_NAME_BUFF_RE.search(chunk or blob)
        if t == "when_attacking" and m:
            gs = [g for g in m.groups() if g]
            # name then power OR interleaved
            name = gs[0] if not gs[0].isdigit() else gs[1]
            if name and a.get("require_own_name_on_field") != name:
                # Prefer EN name when Chinese is Jax-like for Jango cards
                if name in {"傑克斯", "杰克斯"} and re.search(r"\[Jango\]", blob):
                    name = "Jango"
                a["require_own_name_on_field"] = name
                changed = True

        # OP02-051 draw until hand size
        m = DRAW_UNTIL_HAND_RE.search(chunk or blob)
        if t == "on_play" and m:
            n = int(next(g for g in m.groups() if g))
            if not any(o.get("until_hand_size") == n for o in ops if o.get("op") == "draw"):
                ops = [{"op": "draw", "until_hand_size": n, "count": 1}] + [
                    o for o in ops if not (o.get("op") == "draw" and not o.get("until_hand_size"))
                ]
                changed = True

        # OP02-090 trigger opp DON gate
        m = OPP_DON_GTE_RE.search(chunk or blob)
        if t == "trigger" and m:
            n = int(next(g for g in m.groups() if g))
            if a.get("require_opp_don_field_gte") != n:
                a["require_opp_don_field_gte"] = n
                # clear mistaken own don gate if present
                if a.get("require_don_field_gte") == n:
                    a.pop("require_don_field_gte", None)
                changed = True

        # OP06-093 choose_one
        m = CHOOSE_TRASH_OR_COST_RE.search(chunk or blob)
        if t == "on_play" and m and not any(o.get("op") == "choose_one" for o in ops):
            red = int(next(g for g in m.groups() if g))
            ops = [
                {
                    "op": "choose_one",
                    "chooser": "self",
                    "options": [
                        {
                            "id": "trash_hand",
                            "label": "Opponent trashes 1",
                            "ops": [{"op": "trash_hand", "count": 1, "owner": "opponent", "optional": False}],
                        },
                        {
                            "id": "reduce_cost",
                            "label": f"Give −{red} cost",
                            "ops": [
                                {
                                    "op": "reduce_cost",
                                    "amount": -red,
                                    "count": 1,
                                    "target_kind": "opponent_character",
                                    "optional": True,
                                }
                            ],
                        },
                    ],
                }
            ]
            if re.search(r"5 or more cards in their hand|手牌有5[張张]以上", blob, re.I):
                a["require_opp_hand_gte"] = 5
            a["status"] = "compiled"
            a["confidence"] = 0.9
            changed = True

        # OP04-040 choose draw or life
        m = CHOOSE_DRAW_OR_LIFE_RE.search(chunk or blob)
        if t == "when_attacking" and m and not any(o.get("op") == "choose_one" for o in ops):
            cost_n = int(next(g for g in m.groups() if g))
            m_tot = TOTAL_LIFE_HAND_LTE_RE.search(chunk or blob)
            if m_tot:
                a["require_life_plus_hand_lte"] = int(next(g for g in m_tot.groups() if g))
            a["require_don_attached_gte"] = max(int(a.get("require_don_attached_gte") or 0), 1)
            ops = [
                {
                    "op": "choose_one",
                    "chooser": "self",
                    "options": [
                        {"id": "draw", "label": "Draw 1", "ops": [{"op": "draw", "count": 1}]},
                        {
                            "id": "add_life",
                            "label": "Add life instead if cost 8+",
                            "ops": [{"op": "add_life", "count": 1}],
                            "require_own_char_cost_gte": cost_n,
                        },
                    ],
                }
            ]
            a["status"] = "compiled"
            a["confidence"] = 0.9
            changed = True

        # OP02-025 activate: next hand cost reduce
        m = NEXT_HAND_COST_RE.search(chunk or blob)
        if t == "activate_main" and m:
            gs = [g for g in m.groups() if g]
            # EN: trait, cost_gte, amt | ZH: cost_gte, trait, amt
            if gs[0].isdigit():
                cost_gte, trait, amt = int(gs[0]), gs[1], int(gs[2])
            else:
                trait, cost_gte, amt = gs[0], int(gs[1]), int(gs[2])
            ops = [
                {
                    "op": "hand_cost_reduce",
                    "amount": -amt,
                    "trait_contains": trait,
                    "cost_gte": cost_gte,
                    "next_only": True,
                    "once": True,
                }
            ]
            a["once"] = True
            a["require_chars_lte"] = min(int(a.get("require_chars_lte") or 1), 1)
            if re.search(r"1 or less Characters|角色卡在1[張张]以下", blob, re.I):
                a["require_chars_lte"] = 1
            a["status"] = "compiled"
            a["confidence"] = 0.9
            changed = True
            # drop duplicate your_turn bleed
        if t == "your_turn" and NEXT_HAND_COST_RE.search(blob) and any(
            o.get("op") == "hand_cost_reduce" for o in ops
        ):
            # keep only if activate_main missing; else drop bleed
            if any(x.get("timing") == "activate_main" for x in new_abs):
                ops = []
                changed = True

        # OP07-001 attach up to 2 given DON
        m = ATTACH_GIVEN_DON_RE.search(chunk or blob)
        if t == "activate_main" and m:
            n = int(next(g for g in m.groups() if g))
            for o in ops:
                if o.get("op") == "attach_don":
                    if int(o.get("count") or 0) != n or o.get("target_kind") != "own_character":
                        o["count"] = n
                        o["target_kind"] = "own_character"
                        o["optional"] = True
                        changed = True
            if not any(o.get("op") == "attach_don" for o in ops):
                ops = [{"op": "attach_don", "count": n, "target_kind": "own_character", "optional": True}]
                changed = True
            a["once"] = True

        # Named play from deck
        m = PLAY_NAMED_FROM_DECK_RE.search(chunk or blob)
        if t in {"on_ko", "activate_main"} and m:
            gs = [g for g in m.groups() if g]
            if gs[0].isdigit():
                cost_n, name = int(gs[0]), gs[1]
            else:
                name, cost_n = gs[0], int(gs[1])
            for o in ops:
                if o.get("op") == "play_from_hand":
                    if o.get("from_zone") != "deck" or o.get("name_contains") != name:
                        o["from_zone"] = "deck"
                        o["name_contains"] = name
                        o["cost_lte"] = cost_n
                        o["optional"] = True
                        changed = True
            if re.search(r"Opponent's Turn|對方回合|对方回合", blob, re.I):
                if not a.get("require_opponent_turn"):
                    a["require_opponent_turn"] = True
                    changed = True

        m = LAND_WANO_FROM_DECK_RE.search(chunk or blob)
        if t == "on_ko" and m:
            cost_n = int(next(g for g in m.groups() if g))
            for o in ops:
                if o.get("op") == "play_from_hand":
                    o["from_zone"] = "deck"
                    o["cost_eq"] = cost_n
                    o["trait_contains"] = "Land of Wano"
                    o["color"] = "green"
                    o["optional"] = True
                    changed = True

        # OP02-030 activate: rest self active with cost_don 3
        if t == "activate_main" and re.search(r"Set this Character as active|將這張角色卡置為活動|将这张角色卡置为活动", chunk or blob, re.I):
            for o in ops:
                if o.get("op") == "set_character_active":
                    if o.get("target_kind") != "self":
                        o["target_kind"] = "self"
                        changed = True
            if not any(o.get("op") == "rest_don" and o.get("as_cost") for o in ops) and int(a.get("cost_don") or 0) >= 1:
                ops = [{"op": "rest_don", "count": int(a.get("cost_don") or 3), "as_cost": True}] + ops
                changed = True

        # grant named blocker continuous
        m = GRANT_NAMED_BLOCKER_RE.search(chunk or blob)
        if t in {"your_turn", "opponent_turn"} and m:
            name = next(g for g in m.groups() if g)
            for o in ops:
                if o.get("op") == "grant_keyword" and o.get("keyword") == "blocker":
                    if o.get("name_contains") != name:
                        o["name_contains"] = name
                        o["target_kind"] = "own_character"
                        o["duration"] = "permanent"
                        changed = True

        m = SELF_BLOCKER_IF_NAME_RE.search(chunk or blob)
        if t in {"your_turn", "opponent_turn"} and m:
            name = next(g for g in m.groups() if g)
            if a.get("require_own_name_on_field") != name:
                a["require_own_name_on_field"] = name
                changed = True

        # OP11-001 navy replace_leave
        m = NAVY_REPLACE_RE.search(chunk or blob)
        if t == "your_turn" and m and not any(o.get("op") == "replace_leave" for o in ops):
            pow_n = int(next(g for g in m.groups() if g))
            # if this ability is the rush one, skip — inject separate below
            if any(o.get("op") in {"allow_attack_active", "grant_keyword"} for o in ops) and not any(
                o.get("op") == "trash_to_bottom" for o in ops
            ):
                pass
            elif any(o.get("op") == "trash_to_bottom" for o in ops) or "removed from the field" in (a.get("summary") or ""):
                ops = [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "trash_to_bottom",
                        "trash_count": 3,
                        "trait_contains": "Navy",
                        "base_power_lte": pow_n,
                        "once": True,
                        "optional": True,
                    }
                ]
                a["once"] = True
                changed = True

        # ST12-013 reveal play rested from deck
        m = REVEAL_PLAY_RESTED_RE.search(chunk or blob)
        if t == "when_attacking" and m:
            cost_n = int(next(g for g in m.groups() if g))
            ops = [
                {
                    "op": "search_deck",
                    "top_n": 1,
                    "max_add": 1,
                    "destination": "play",
                    "card_type": "character",
                    "cost_lte": cost_n,
                    "as_rested": True,
                    "order_bottom": False,
                }
            ]
            changed = True

        # EB04-044 P variants: ensure on_opp_ko draw
        if t == "your_turn" and any(o.get("op") == "draw" for o in ops) and OPP_KO_DRAW_RE.search(blob):
            if not a.get("on_opp_ko"):
                a["on_opp_ko"] = True
                for o in ops:
                    if o.get("op") == "draw":
                        o["on_opp_ko"] = True
                a["once"] = True
                changed = True

        a["ops"] = [dict(o) for o in ops if isinstance(o, dict) and o.get("op")]

    # Drop empty abilities
    before = len(new_abs)
    new_abs = [a for a in new_abs if a.get("ops")]
    if len(new_abs) != before:
        changed = True

    # Inject opp-KO draw for P variants missing it
    if OPP_KO_DRAW_RE.search(blob) and not any(
        a.get("on_opp_ko") or any(o.get("on_opp_ko") for o in (a.get("ops") or [])) for a in new_abs
    ):
        new_abs.append(
            normalize_ability(
                {
                    "timing": "your_turn",
                    "summary": "When opponent's Character is K.O.'d, draw 1",
                    "ops": [{"op": "draw", "count": 1, "on_opp_ko": True}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "once": True,
                    "on_opp_ko": True,
                }
            )
        )
        changed = True
    else:
        # collapse duplicate on_opp_ko draws
        seen_draw = False
        kept = []
        for a in new_abs:
            is_opp_draw = a.get("on_opp_ko") and any(o.get("op") == "draw" for o in (a.get("ops") or []))
            if is_opp_draw:
                if seen_draw:
                    changed = True
                    continue
                seen_draw = True
            kept.append(a)
        new_abs = kept

    # Inject OP11-001 replace if missing entirely
    m = NAVY_REPLACE_RE.search(blob)
    if m and not any(any(o.get("op") == "replace_leave" for o in (a.get("ops") or [])) for a in new_abs):
        pow_n = int(next(g for g in m.groups() if g))
        new_abs.append(
            normalize_ability(
                {
                    "timing": "your_turn",
                    "summary": "Once: place 3 trash bottom instead of Navy char leaving",
                    "ops": [
                        {
                            "op": "replace_leave",
                            "trigger": "opp_remove",
                            "target": "own_filtered",
                            "cost": "trash_to_bottom",
                            "trash_count": 3,
                            "trait_contains": "Navy",
                            "base_power_lte": pow_n,
                            "once": True,
                            "optional": True,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                    "once": True,
                }
            )
        )
        changed = True

    # SWORD rush: fix allow_attack to trait
    if SWORD_RUSH_RE.search(blob):
        for a in new_abs:
            for o in a.get("ops") or []:
                if o.get("op") == "allow_attack_active" and o.get("target_kind") == "self":
                    o["target_kind"] = "own_character"
                    o["trait_contains"] = "SWORD"
                    changed = True
                if o.get("op") == "grant_keyword" and o.get("keyword") == "rush_character":
                    o["target_kind"] = "own_character"
                    o["trait_contains"] = "SWORD"
                    changed = True

    if _clone_continuous_to_opp_turn(new_abs):
        changed = True

    # Copy base → P variant when P is thinner
    m = re.match(r"(.+)-P\d+$", cid)
    if m:
        base = get_card_entry(m.group(1))
        if base and len(base.get("abilities") or []) > len(new_abs):
            # same effect text start
            new_abs = [dict(a) for a in base["abilities"]]
            changed = True

    if not changed:
        return None
    cleaned = [a for a in (normalize_ability(x) for x in new_abs) if a]
    if not cleaned:
        return None
    return normalize_card_entry(cid, {"version": 1, "abilities": cleaned})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    q = json.loads((ROOT / "meta" / "effect_problem_queue.json").read_text())
    open_ids = [it["id"] for it in q["items"] if it.get("status") == "open"]
    seeds = [
        "EB04-044-P1",
        "EB04-044-P2",
        "OP02-025",
        "OP02-030",
        "OP02-051",
        "OP02-074",
        "OP02-090",
        "OP02-111",
        "OP04-040",
        "OP06-093",
        "OP07-001",
        "OP08-071",
        "OP08-073",
        "OP11-001",
        "EB02-033",
        "ST12-013",
        "OP05-109",
    ]
    for cid in seeds:
        if cid not in open_ids:
            open_ids.append(cid)
    for cid, info in catalog.items():
        blob = effect_blob(info)
        if any(
            r.search(blob)
            for r in (
                DRAW_UNTIL_HAND_RE,
                CHOOSE_TRASH_OR_COST_RE,
                CHOOSE_DRAW_OR_LIFE_RE,
                NEXT_HAND_COST_RE,
                OPP_DON_GTE_RE,
                GRANT_NAMED_BLOCKER_RE,
                SELF_BLOCKER_IF_NAME_RE,
                ATTACH_GIVEN_DON_RE,
                NAVY_REPLACE_RE,
            )
        ):
            if cid not in open_ids:
                open_ids.append(cid)
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
        entry = cards.get(cid) or get_card_entry(cid) or {"card_id": cid, "version": 1, "abilities": []}
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
    for cid in seeds:
        if cid in fixed:
            e = get_card_entry(cid)
            print(cid, json.dumps([(a.get("timing"), [o.get("op") for o in a.get("ops") or []], {k: a.get(k) for k in a if k.startswith("require_") or k in {"once", "on_opp_ko"}}) for a in (e or {}).get("abilities") or []], ensure_ascii=False)[:240])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
