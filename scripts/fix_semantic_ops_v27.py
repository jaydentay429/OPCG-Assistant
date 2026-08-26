#!/usr/bin/env python3
"""Deterministic semantic fixes v27: trash-play, costs, buff_all_own, events, replace.

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
    _parse_buff_all_own_ops,
    _parse_replace_leave_ops,
    effect_blob,
)
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

OUT_IDS = ROOT / "meta" / "logs" / "ops_v27_fixed_ids.txt"

TRASH_COST_TRAIT_RE = re.compile(
    r"(?:you may )?trash\s*1\s*\{([^}]+)\} type card from your hand\s*:|"
    r"可以廢棄1[張张]自己手牌中擁有《([^》]+)》特徵的卡片\s*[：:]|"
    r"可以废弃1[张張]自己手牌中拥有《([^》]+)》特征的卡片\s*[：:]",
    re.I,
)
TRASH_COST_PLAIN_RE = re.compile(
    r"(?:you may )?trash\s*1 card from your hand\s*:|"
    r"可以廢棄1[張张]自己的手牌\s*[：:]|"
    r"可以废弃1[张張]自己的手牌\s*[：:]",
    re.I,
)
TRASH_OWN_CHAR_COST_RE = re.compile(
    r"(?:you may )?trash 1 of your Characters\s*:|"
    r"可[將将]1[張张]自己的角色卡放置在廢棄區\s*[：:]|"
    r"可[将將]1[张張]自己的角色卡放置在废弃区\s*[：:]",
    re.I,
)
PLAY_FROM_TRASH_RE = re.compile(
    r"play up to\s*1.{0,80}from your trash|"
    r"使最多1[張张]自己廢棄區|"
    r"使最多1[张張]自己废弃区",
    re.I,
)
REVEAL_TOP1_PLAY_RE = re.compile(
    r"Reveal 1 card from the top of your deck.{0,120}play|"
    r"公開1[張张]自己卡組上面的卡片.{0,80}登場|"
    r"公开1[张張]自己卡组上面的卡片.{0,80}登场",
    re.I,
)
GAIN_DON_BOTH_RE = re.compile(
    r"add up to 1 DON!! card from your DON!! deck and set it as active.{0,80}"
    r"add up to 1 additional DON!! card and rest it|"
    r"追加最多1[張张].{0,20}活動狀態.{0,80}追加最多1[張张].{0,20}休息|"
    r"追加最多1[张張].{0,20}活动状态.{0,80}追加最多1[张張].{0,20}休息",
    re.I,
)
BUFF_PER_HAND_RE = re.compile(
    r"gains?\s*[+＋]\s*(\d{3,5})\s*power for every card in your hand|"
    r"自己每有1[張张]手牌.{0,20}力量(?:值)?\s*[+＋]\s*(\d{3,5})",
    re.I,
)
CANNOT_ATK_UNLESS_RE = re.compile(
    r"cannot attack unless there is a Character with\s*(\d+)\s*base power or more|"
    r"若場上沒有原本力量值\s*(\d+)\s*以上的角色卡時.{0,20}無法進行攻擊|"
    r"若场上没有原本力量值\s*(\d+)\s*以上的角色卡时.{0,20}无法进行攻击",
    re.I,
)
ON_OPP_EVENT_RE = re.compile(
    r"Draw 1 card when your opponent activates an Event|"
    r"對手發動事件卡時，抽1[張张]|对手发动事件卡时，抽1[张張]",
    re.I,
)
ON_EVENT_RE = re.compile(
    r"When you activate an Event.{0,80}draw|"
    r"自己發動事件卡時.{0,40}抽",
    re.I,
)


def _on_play_only(blob: str) -> str:
    m = re.search(
        r"\[On Play\](.*?)(?=\[(?:On K\.?O\.?|When Attacking|Activate|Trigger|Counter|Your Turn|Opponent|Main|DON!!|Once)|"
        r"【(?:登場時|KO時|攻擊時|啟動|觸發|反擊|我方|對方|主要|咚|每回合)|$)",
        blob,
        re.I | re.S,
    )
    if m:
        return m.group(1)
    m = re.search(r"【登場時】(.*?)(?=【(?:KO時|攻擊時|啟動|觸發|反擊|我方|對方|主要|咚|每回合)|$)", blob, re.I | re.S)
    return m.group(1) if m else ""


def fix_card(cid: str, info: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any] | None:
    blob = effect_blob(info)
    abs_in = [dict(a) for a in (entry.get("abilities") or []) if isinstance(a, dict)]
    changed = False
    new_abs: list[dict[str, Any]] = []
    leave_ops = _parse_replace_leave_ops(blob)

    for a in abs_in:
        t = str(a.get("timing") or "")
        chunk = _trim_cross_timing(_timing_chunk(blob, t), t) or ""
        ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

        # Bleed continuous buff/grant onto on_play
        if t == "on_play":
            on_only = _on_play_only(blob)
            if on_only and not re.search(r"Leader|領航|领航|gains \+|力量值\+|費用\+|费用\+", on_only, re.I):
                if any(x.get("timing") == "your_turn" for x in abs_in):
                    before = len(ops)
                    ops = [o for o in ops if o.get("op") not in {"buff_self", "grant_cost", "buff_all_own"}]
                    if len(ops) != before:
                        changed = True
                    if a.get("require_leader_trait") and not re.search(r"Leader|領航|领航", on_only, re.I):
                        # keep gate only if on_play itself needs it
                        if not re.search(r"If your Leader|若自己的領航|若自己的领航", on_only, re.I):
                            a.pop("require_leader_trait", None)
                            changed = True

        # Trash trait cost
        m = TRASH_COST_TRAIT_RE.search(chunk) or (TRASH_COST_TRAIT_RE.search(blob) if t == "on_play" else None)
        if m and t in {"on_play", "activate_main", "main_start"}:
            trait = next(g for g in m.groups() if g)
            if not any(o.get("op") == "trash_hand" for o in ops):
                ops.insert(
                    0,
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                        "trait_contains": trait,
                    },
                )
                changed = True
            else:
                for o in ops:
                    if o.get("op") == "trash_hand":
                        o["as_cost"] = True
                        o["optional"] = True
                        o["trait_contains"] = trait
                        changed = True

        # Plain trash hand cost
        if TRASH_COST_PLAIN_RE.search(chunk) and t in {"on_play", "activate_main", "main_start"}:
            if not any(o.get("op") == "trash_hand" for o in ops):
                ops.insert(0, {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"})
                changed = True
            else:
                for o in ops:
                    if o.get("op") == "trash_hand" and not o.get("as_cost"):
                        o["as_cost"] = True
                        o["optional"] = True
                        changed = True

        # Trash own character cost
        if TRASH_OWN_CHAR_COST_RE.search(chunk) and t == "on_play":
            if not any(o.get("op") == "trash" and o.get("target_kind") in {None, "own_character", "self"} for o in ops):
                # draw may already exist; add trash cost
                if not any(o.get("op") == "trash" for o in ops):
                    ops.insert(0, {"op": "trash", "target_kind": "own_character", "optional": True, "as_cost": True})
                    changed = True

        # Play from trash
        if PLAY_FROM_TRASH_RE.search(chunk) or (t in {"on_play", "activate_main"} and PLAY_FROM_TRASH_RE.search(blob)):
            for o in ops:
                if o.get("op") == "play_from_hand":
                    if o.get("from_zone") != "trash" and not (
                        "hand_or_trash" == o.get("from_zone") and re.search(r"hand or trash|手牌或廢棄", chunk, re.I)
                    ):
                        if re.search(r"from your trash|廢棄區|废弃区", chunk or blob, re.I):
                            o["from_zone"] = "trash"
                            changed = True
                    # CP trait including vs name
                    m_inc = re.search(
                        r'type including\s*[\"\']([^\"\']+)[\"\']|包含[『「]([^』」]+)[』」]特徵|包含[『「]([^』」]+)[』」]特征',
                        chunk or blob,
                        re.I,
                    )
                    if m_inc:
                        trait = next(g for g in m_inc.groups() if g)
                        if o.get("name_contains") and not o.get("trait_contains"):
                            o.pop("name_contains", None)
                        o["trait_contains"] = trait
                        changed = True
                    m_ex = re.search(r"other than \[([^\]]+)\]|除了「([^」]+)」以外", chunk or blob, re.I)
                    if m_ex:
                        o["exclude_name"] = next(g for g in m_ex.groups() if g)
                        if o.get("name_contains") == o.get("exclude_name"):
                            o.pop("name_contains", None)
                        changed = True
                    m_pwr = re.search(r"(\d+)\s*power or less|力量(?:值)?\s*(\d+)\s*以下", chunk or blob, re.I)
                    if m_pwr:
                        o["power_lte"] = int(next(g for g in m_pwr.groups() if g))
                        changed = True
                    if re.search(r"no base effect|原本沒有效果|原本没有效果", chunk or blob, re.I):
                        o["no_base_effect"] = True
                        changed = True
                    m_cost = re.search(r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下", chunk or blob, re.I)
                    if m_cost and o.get("cost_lte") is None:
                        o["cost_lte"] = int(next(g for g in m_cost.groups() if g))
                        changed = True

        # Reveal top 1 → play if match (not search 5 to hand)
        if t == "when_attacking" and REVEAL_TOP1_PLAY_RE.search(chunk or blob):
            ops = [o for o in ops if o.get("op") != "search_deck"]
            op = {
                "op": "search_deck",
                "top_n": 1,
                "max_add": 1,
                "destination": "play",
                "card_type": "character",
                "order_bottom": False,
                "optional": True,
            }
            m_tr = re.search(r"\{([^}]+)\} type|《([^》]+)》特徵|《([^》]+)》特征", chunk or blob)
            if m_tr:
                op["trait_contains"] = next(g for g in m_tr.groups() if g)
            m_c = re.search(r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下", chunk or blob, re.I)
            if m_c:
                op["cost_lte"] = int(next(g for g in m_c.groups() if g))
            if re.search(r"play that card rested|休息狀態登場|休息状态登场|as rested", chunk or blob, re.I):
                op["as_rested"] = True
            ops.append(op)
            # ensure rest_don cost 1 if ➀
            if re.search(r"➀|①|\(You may rest|可將費用區的咚", chunk or blob, re.I):
                if not any(o.get("op") == "rest_don" for o in ops):
                    ops.insert(0, {"op": "rest_don", "count": 1, "as_cost": True, "optional": True})
            changed = True

        # gain_don active + rested
        if GAIN_DON_BOTH_RE.search(chunk or blob) and t == "activate_main":
            ops = [o for o in ops if o.get("op") != "gain_don"]
            ops.append({"op": "gain_don", "count": 1, "optional": True})
            ops.append({"op": "gain_don", "count": 1, "as_rested": True, "optional": True})
            changed = True

        # buff_all_own
        bao = _parse_buff_all_own_ops(chunk) or _parse_buff_all_own_ops(blob if t == "your_turn" else "")
        if bao and t == "your_turn":
            if any(o.get("op") == "buff_self" for o in ops) and not any(o.get("op") == "buff_all_own" for o in ops):
                ops = [o for o in ops if o.get("op") != "buff_self"]
                ops.extend(bao)
                changed = True
            elif not any(o.get("op") == "buff_all_own" for o in ops):
                ops.extend(bao)
                changed = True

        # buff per hand
        m = BUFF_PER_HAND_RE.search(chunk)
        if m and t == "your_turn":
            amt = int(next(g for g in m.groups() if g))
            for o in ops:
                if o.get("op") == "buff_self":
                    o["amount"] = amt
                    o["per_hand_cards"] = 1
                    changed = True

        # cannot attack unless
        m = CANNOT_ATK_UNLESS_RE.search(chunk or blob)
        if m and t == "your_turn":
            pwr = int(next(g for g in m.groups() if g))
            for o in ops:
                if o.get("op") == "cannot_attack":
                    o["unless_field_char_base_power_gte"] = pwr
                    changed = True
            a["require_field_char_base_power_gte"] = pwr  # inverse semantics in gate name is awkward; keep on op

        # life 0 for blocker grant
        if t == "your_turn" and re.search(r"0 Life cards|生命值卡為0|生命值卡为0", chunk or blob, re.I):
            if any(o.get("op") == "grant_keyword" for o in ops):
                a["require_life_lte"] = 0
                changed = True

        # trash_life as_cost
        if t == "on_play" and re.search(r"trash 1 card from the top of your Life cards\s*:|生命值區上面的卡片放置在廢棄區\s*[：:]", chunk, re.I):
            for o in ops:
                if o.get("op") == "trash_life":
                    o["as_cost"] = True
                    o["optional"] = True
                    changed = True

        # Active don after trash wano cost
        if t == "activate_main" and re.search(r"Set up to\s*2 of your DON!! cards as active|最多2[張张]自己的咚", chunk, re.I):
            if not any(o.get("op") == "active_don" for o in ops):
                ops.append({"op": "active_don", "count": 2, "optional": True})
                changed = True

        # Opp all -3000 on trigger
        if t == "trigger" and re.search(r"all of your opponent'?s? Characters?\s*[−\-－]\s*(\d{3,5})|對手的角色卡全數.{0,20}[−\-－]\s*(\d{3,5})", chunk or blob, re.I):
            m = re.search(r"[−\-－]\s*(\d{3,5})", chunk or blob)
            amt = -abs(int(m.group(1))) if m else -3000
            if not any(o.get("op") == "buff" and o.get("all") for o in ops):
                ops = [o for o in ops if not (o.get("op") == "buff" and int(o.get("amount") or 0) < 0)]
                ops.insert(0, {"op": "buff", "amount": amt, "target_kind": "opponent_character", "all": True, "duration": "turn"})
                changed = True
            if re.search(r"0 Life|生命值卡為0|生命值卡为0", chunk or blob, re.I) and re.search(
                r"play this card|使這張卡片登場|使这张卡片登场", chunk or blob, re.I
            ):
                if not any(o.get("op") == "play_from_hand" and o.get("self_card") for o in ops):
                    ops.append(
                        {
                            "op": "play_from_hand",
                            "count": 1,
                            "self_card": True,
                            "from_zone": "hand",
                            "card_type": "character",
                            "optional": False,
                        }
                    )
                    a["require_life_lte"] = 0
                    changed = True

        a["ops"] = [sanitize_op(o) for o in ops if sanitize_op(o)]
        na = normalize_ability(a)
        if na:
            new_abs.append(na)

    # Inject replace_leave continuous
    if leave_ops and not any(o.get("op") == "replace_leave" for a in new_abs for o in (a.get("ops") or [])):
        ab: dict[str, Any] = {
            "timing": "your_turn",
            "summary": leave_ops[0].get("summary") or "replace_leave",
            "ops": leave_ops,
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        }
        if re.search(r"Navy|海軍|海军", blob, re.I) and leave_ops[0].get("cost") == "trash_hand":
            ab["require_leader_trait"] = "Navy"
        new_abs.append(normalize_ability(ab))
        changed = True

    # on_opp_event / on_event abilities
    if ON_OPP_EVENT_RE.search(blob) and not any(a.get("timing") == "on_opp_event" for a in new_abs):
        # migrate your_turn draw-only
        kept = []
        for a in new_abs:
            if a.get("timing") == "your_turn" and [o.get("op") for o in (a.get("ops") or [])] == ["draw"]:
                gates = {k: a[k] for k in a if k.startswith("require_")}
                ab = {
                    "timing": "on_opp_event",
                    "summary": "When opponent activates Event: draw 1",
                    "ops": [{"op": "draw", "count": 1}],
                    "status": "compiled",
                    "confidence": 0.9,
                    "once": True,
                    **gates,
                }
                kept.append(normalize_ability(ab))
                changed = True
            else:
                kept.append(a)
        new_abs = kept
        if not any(a.get("timing") == "on_opp_event" for a in new_abs):
            new_abs.append(
                normalize_ability(
                    {
                        "timing": "on_opp_event",
                        "summary": "When opponent activates Event: draw 1",
                        "ops": [{"op": "draw", "count": 1}],
                        "status": "compiled",
                        "confidence": 0.9,
                        "once": True,
                        "require_don_attached_gte": 1,
                    }
                )
            )
            changed = True

    if ON_EVENT_RE.search(blob) and not any(a.get("timing") == "on_event" for a in new_abs) and not abs_in:
        # empty leader like OP01-062
        ab = {
            "timing": "on_event",
            "summary": "When you activate Event: maybe draw 1",
            "ops": [{"op": "draw", "count": 1, "optional": True}],
            "status": "compiled",
            "confidence": 0.85,
            "require_don_attached_gte": 1,
            "require_hand_lte": 4,
            "once": True,
        }
        new_abs.append(normalize_ability(ab))
        changed = True
    elif ON_EVENT_RE.search(blob) and not any(a.get("timing") == "on_event" for a in new_abs):
        new_abs.append(
            normalize_ability(
                {
                    "timing": "on_event",
                    "summary": "When you activate Event: maybe draw 1",
                    "ops": [{"op": "draw", "count": 1, "optional": True}],
                    "status": "compiled",
                    "confidence": 0.85,
                    "require_don_attached_gte": 1,
                    "require_hand_lte": 4,
                    "once": True,
                }
            )
        )
        changed = True

    # OP01-091 style: ensure require_don_field_gte stays + buff all opp
    for a in new_abs:
        if a.get("timing") == "your_turn" and a.get("require_don_field_gte"):
            for o in a.get("ops") or []:
                if o.get("op") == "buff" and not o.get("all"):
                    o["all"] = True
                    o["target_kind"] = "opponent_character"
                    changed = True

    if not changed or not new_abs:
        return None
    return normalize_card_entry(cid, {"version": 1, "abilities": [a for a in new_abs if a]})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    q = json.loads((ROOT / "meta" / "effect_problem_queue.json").read_text())
    open_ids = [it["id"] for it in q["items"] if it.get("status") == "open"]
    # always include empty leaders with on_event text
    for cid, info in catalog.items():
        blob = effect_blob(info)
        if ON_EVENT_RE.search(blob) or ON_OPP_EVENT_RE.search(blob):
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
    for cid in [
        "EB02-047",
        "EB03-039",
        "EB04-031",
        "EB04-032",
        "EB04-043",
        "EB04-044",
        "EB04-048",
        "EB04-051",
        "EB04-056",
        "OP01-004",
        "OP01-031",
        "OP01-060",
        "OP01-062",
        "OP01-072",
        "OP01-091",
        "OP02-019",
    ]:
        e = get_card_entry(cid) or {}
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
