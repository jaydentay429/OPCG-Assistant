#!/usr/bin/env python3
"""Search/play split, skip_untap fixes, attach name targets, simple choose_one.

Writes library + overrides.
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
    _parse_look_top_search,
    _parse_play_from_hand,
    _parse_play_from_zone,
    _parse_skip_untap_ops,
    effect_blob,
)
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "search_choose_v21_fixed_ids.txt"

LOOK_RE = re.compile(r"look at|查看|檢視|检视", re.I)
HAND_THEN_PLAY_RE = re.compile(
    r"add (?:it|them) to your hand.{0,80}play up to|加入手牌.{0,80}(?:然後|然后|再).{0,40}(?:登場|登场)|"
    r"add it to your hand and place the rest.{0,80}(?:Then,? )?[Pp]lay",
    re.I,
)
ATTACH_NAME_RE = re.compile(
    r"(?:give|attach).{0,60}(?:DON!!|咚).{0,40}(?:to 1 of your )?\[([^\]]+)\]|"
    r"give 1 active DON!! card to 1 of your \[([^\]]+)\]|"
    r"附加.{0,40}「([^」]+)」|"
    r"給予.{0,40}「([^」]+)」|给予.{0,40}「([^」]+)」",
    re.I,
)
SET_ACTIVE_COUNT_RE = re.compile(
    r"set up to\s*(\d+)\s*of your.{0,40}as active|"
    r"將最多\s*(\d+)\s*[張张].{0,40}置[為为]活動|"
    r"将最多\s*(\d+)\s*[张張].{0,40}置为活动",
    re.I,
)
CHOOSE_ONE_RE = re.compile(r"Choose one\s*:|選擇一項\s*[：:]|选择一项\s*[：:]", re.I)


def _branch_ops(text: str) -> list[dict[str, Any]]:
    """Best-effort parse a single choose-one branch into ops."""
    ops: list[dict[str, Any]] = []
    t = text.strip()
    if not t:
        return ops
    # Draw (plain)
    m = re.search(r"^[Dd]raw\s*(\d+)|^抽\s*(\d+)", t)
    if m:
        ops.append({"op": "draw", "count": int(next(g for g in m.groups() if g))})
    # Opponent trash hand with hand gate
    m = re.search(
        r"[Ii]f (?:your opponent has|對手的手牌有|对手的手牌有)\s*(\d+)\s*(?:or more|以上).{0,100}"
        r"(?:(?:your )?opponent trashes?\s*(\d+)|(?:trash|廢棄|废弃)\s*(\d+).{0,40}(?:opponent'?s? hand|對手的手牌|对手的手牌|their hand))|"
        r"trash\s*(\d+)\s*cards? from your opponent'?s hand|"
        r"對手廢棄\s*(\d+)\s*[張张]手牌|对手废弃\s*(\d+)\s*[张張]手牌|"
        r"廢棄\s*(\d+)\s*[張张]對手的手牌|废弃\s*(\d+)\s*[张張]对手的手牌",
        t,
        re.I,
    )
    if m:
        nums = [int(g) for g in m.groups() if g]
        gate = None
        count = 1
        if len(nums) >= 2 and re.search(r"or more|以上", t, re.I):
            gate, count = nums[0], nums[1]
        elif nums:
            count = nums[-1]
        op: dict[str, Any] = {
            "op": "trash_hand",
            "count": count,
            "optional": False,
            "owner": "opponent",
        }
        if gate is not None:
            op["summary"] = f"If opponent hand ≥{gate}, trash {count}"
        ops.append(op)
    # set active own
    m = re.search(
        r"[Ss]et up to\s*(\d+)\s*of your.{0,120}as active|"
        r"將最多\s*(\d+)\s*[張张].{0,80}置[為为]活動|"
        r"将最多\s*(\d+)\s*[张張].{0,80}置为活动",
        t,
        re.I,
    )
    if m:
        n = int(next(g for g in m.groups() if g))
        op = {
            "op": "set_character_active",
            "count": n,
            "target_kind": "own_leader_or_character"
            if re.search(r"Leader or Character|領航卡或角色|领航卡或角色", t, re.I)
            else "own_character",
            "optional": True,
        }
        m_c = re.search(r"cost of\s*(\d+)\s*or less|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下", t, re.I)
        if m_c:
            op["cost_lte"] = int(next(g for g in m_c.groups() if g))
        m_tr = re.search(r"\{([^}]+)\}\s*type|《([^》]+)》", t)
        if m_tr:
            op["trait_contains"] = next(g for g in m_tr.groups() if g)
        ops.append(op)
    # rest this + opponent
    if re.search(
        r"[Rr]est this Character and up to\s*\d+\s*of your opponent|"
        r"將這張角色卡置[為为]休息.{0,40}對手|将这张角色卡置为休息.{0,40}对手",
        t,
        re.I,
    ):
        ops.append({"op": "rest_character", "target_kind": "self", "optional": False})
        m_n = re.search(r"up to\s*(\d+)|最多\s*(\d+)", t, re.I)
        n = int(next(g for g in m_n.groups() if g)) if m_n else 1
        ops.append({"op": "rest_opponent_character", "count": n, "optional": True})
    # return to hand
    m = re.search(
        r"[Rr]eturn up to\s*(\d+)\s*of your opponent'?s Characters?(?: with a cost of\s*(\d+)\s*or less)?|"
        r"將最多\s*(\d+)\s*[張张]對手(?:費用|费用)\s*(\d+)\s*以下",
        t,
        re.I,
    )
    if m and re.search(r"return|放回手牌", t, re.I):
        nums = [int(g) for g in m.groups() if g]
        op = {
            "op": "return_to_hand",
            "target_kind": "opponent_character",
            "optional": True,
            "count": nums[0] if nums else 1,
        }
        if len(nums) > 1:
            op["cost_lte"] = nums[1]
        ops.append(op)
    # KO
    m = re.search(
        r"K\.?O\.?\s*up to\s*(\d+)\s*of your opponent'?s Characters?(?: with a cost of\s*(\d+)\s*or less)?|"
        r"KO最多\s*(\d+)\s*[張张]對手(?:費用|费用)\s*(\d+)\s*以下",
        t,
        re.I,
    )
    if m:
        nums = [int(g) for g in m.groups() if g]
        op = {"op": "ko", "target_kind": "opponent_character", "optional": True, "count": nums[0] if nums else 1}
        if len(nums) > 1:
            op["cost_lte"] = nums[1]
        ops.append(op)
    # hand-gated draw
    m = re.search(
        r"[Ii]f you have\s*(\d+)\s*or less cards? in your hand,?\s*[Dd]raw\s*(\d+)|"
        r"手牌在\s*(\d+)\s*[張张]以下.{0,12}抽\s*(\d+)",
        t,
        re.I,
    )
    if m:
        nums = [int(g) for g in m.groups() if g]
        ops.append({"op": "draw", "count": nums[1], "optional": False})
    # add_life
    if re.search(r"add .{0,40}[Ll]ife|加到生命", t, re.I):
        m = re.search(r"up to\s*(\d+)|最多\s*(\d+)", t, re.I)
        n = int(next(g for g in m.groups() if g)) if m else 1
        ops.append({"op": "add_life", "count": n, "optional": True})
    out = []
    for o in ops:
        so = sanitize_op(o)
        if so:
            out.append(so)
    return out


def _parse_choose_one_op(chunk: str) -> dict[str, Any] | None:
    if not CHOOSE_ONE_RE.search(chunk):
        return None
    parts = CHOOSE_ONE_RE.split(chunk, maxsplit=1)
    if len(parts) < 2:
        return None
    body = parts[1]
    # Cut at next major timing tag
    body = re.split(
        r"\[(?:Trigger|Counter|On Play|Activate|DON!!|Main|When Attacking)",
        body,
        maxsplit=1,
        flags=re.I,
    )[0]
    # Prefer bullet separators when present
    if "•" in body or "・" in body:
        options_raw = re.split(r"\s*[•・]\s*", body)
    else:
        options_raw = re.split(r"(?:^|\n)\s*[•\-]\s+|(?:^|\n)\s*(?=[A-Z•])", body)
        if len([o for o in options_raw if o and len(o.strip(" \n\r\t-•・")) > 3]) < 2:
            options_raw = re.split(r"\s+-\s+", body)
    options_raw = [o.strip(" \n\r\t-•・") for o in options_raw if o and len(o.strip(" \n\r\t-•・")) > 3]
    cleaned: list[str] = []
    for o in options_raw:
        if re.search(
            r"^(?:Draw|If |Set |Rest |Return |K\.?O|Play |Give |Add |抽|若|將|将|KO|休息|返回)",
            o,
            re.I,
        ):
            cleaned.append(o)
    if len(cleaned) < 2:
        cleaned = [o for o in options_raw if len(o) > 5][:4]
    if len(cleaned) < 2:
        return None
    options = []
    for i, text in enumerate(cleaned[:4]):
        bops = _branch_ops(text)
        if not bops:
            continue
        options.append({"id": f"opt{i}", "label": text[:80], "ops": bops})
    if len(options) < 2:
        return None
    return {"op": "choose_one", "chooser": "self", "options": options, "summary": "Choose one"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    semantic = json.loads(SEM.read_text(encoding="utf-8")) if SEM.exists() else {"cards": {}}
    lib_path, ovr_path = library_paths()
    raw = json.loads(lib_path.read_text(encoding="utf-8"))
    cards = raw.get("cards") or raw
    ovr_raw = json.loads(ovr_path.read_text(encoding="utf-8")) if ovr_path.is_file() else {"cards": {}}
    overrides = ovr_raw.get("cards") if isinstance(ovr_raw.get("cards"), dict) else {}

    stats = {
        "search_hand": 0,
        "search_inject": 0,
        "drop_search": 0,
        "play_after": 0,
        "skip_untap": 0,
        "attach_name": 0,
        "set_active_count": 0,
        "choose_one": 0,
        "cards_touched": 0,
    }
    touched: list[str] = []
    reload_effect_library(force=True)

    targets = [cid for cid, rev in (semantic.get("cards") or {}).items() if rev.get("verdict") == "issue"]
    qpath = ROOT / "meta" / "effect_problem_queue.json"
    if qpath.is_file():
        for it in json.loads(qpath.read_text(encoding="utf-8")).get("items") or []:
            if it.get("status") == "open":
                targets.append(it["id"])
    targets = sorted(set(targets))

    for cid in targets:
        info = catalog.get(cid) or {}
        blob = effect_blob(info)
        merged = get_card_entry(cid)
        abilities = [dict(a) for a in (merged.get("abilities") or []) if isinstance(a, dict)]
        if not abilities:
            continue
        changed = False
        new_abs: list[dict] = []
        multi = len(abilities) > 1

        for a in abilities:
            a = dict(a)
            timing = str(a.get("timing") or "")
            chunk = _trim_cross_timing(_timing_chunk(blob, timing), timing) or ""
            if multi and (not chunk or chunk == blob):
                chunk = _trim_cross_timing(str(a.get("summary") or ""), timing) or chunk
            ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

            # 1) Search destination hand when paper adds to hand (not play-from-look)
            if LOOK_RE.search(chunk) and re.search(r"add (?:it|them) to your hand|加入手牌", chunk, re.I):
                for o in ops:
                    if o.get("op") == "search_deck" and o.get("destination") == "play":
                        o.pop("destination", None)
                        o.pop("card_type", None)
                        stats["search_hand"] += 1
                        changed = True
                # Inject separate play_from_hand after search when paper has then-play from hand
                if re.search(r"(?:Then,? )?[Pp]lay up to|然後使最多|然后使最多", chunk, re.I):
                    play = _parse_play_from_hand(chunk) or _parse_play_from_zone(chunk)
                    if isinstance(play, dict) and not any(o.get("op") == "play_from_hand" for o in ops):
                        # play from hand (not look destination)
                        play = dict(play)
                        play["from_zone"] = "hand"
                        ops.append(play)
                        stats["play_after"] += 1
                        changed = True

            # 2) Inject missing search
            if LOOK_RE.search(chunk) and re.search(r"add (?:it|them) to your hand|加入手牌|play up to", chunk, re.I):
                if not any(o.get("op") == "search_deck" for o in ops):
                    parsed = _parse_look_top_search(chunk)
                    if parsed:
                        if parsed.get("destination") == "play" and re.search(
                            r"add (?:it|them) to your hand|加入手牌", chunk, re.I
                        ):
                            parsed.pop("destination", None)
                            parsed.pop("card_type", None)
                        ops.append(parsed)
                        stats["search_inject"] += 1
                        changed = True
                        if re.search(r"(?:Then,? )?[Pp]lay up to|然後使最多|然后使最多", chunk, re.I):
                            play = _parse_play_from_hand(chunk)
                            if isinstance(play, dict) and not any(o.get("op") == "play_from_hand" for o in ops):
                                play = dict(play)
                                play["from_zone"] = "hand"
                                ops.append(play)
                                stats["play_after"] += 1

            # 3) Drop spurious search
            if any(o.get("op") == "search_deck" for o in ops) and not LOOK_RE.search(chunk):
                if not LOOK_RE.search(blob) or (
                    multi and chunk and not LOOK_RE.search(chunk)
                ):
                    # Only drop if this timing chunk has no look, and play-from-hand is the real effect
                    if re.search(r"play up to|使最多.{0,40}登場|使最多.{0,40}登场|from your hand", chunk, re.I):
                        before = len(ops)
                        ops = [o for o in ops if o.get("op") != "search_deck"]
                        if len(ops) < before:
                            stats["drop_search"] += 1
                            changed = True

            # 4) skip_untap replace wrong set_character_active
            skip = _parse_skip_untap_ops(chunk)
            if skip:
                before = len(ops)
                ops = [o for o in ops if o.get("op") != "set_character_active" or not re.search(
                    r"will not become active|不會置為活動|无法为活动|無法為活動", chunk, re.I
                )]
                if not any(o.get("op") == "skip_untap" for o in ops):
                    ops.extend(skip)
                    stats["skip_untap"] += 1
                    changed = True
                else:
                    for o in ops:
                        if o.get("op") == "skip_untap":
                            for k, v in skip[0].items():
                                if k != "op" and o.get(k) in (None, "") and v is not None:
                                    o[k] = v
                                    changed = True
                                    stats["skip_untap"] += 1
                if len(ops) < before:
                    stats["skip_untap"] += 1
                    changed = True

            # 5) attach_don named character
            m_at = ATTACH_NAME_RE.search(chunk)
            if m_at:
                name = next(g for g in m_at.groups() if g).strip()
                for o in ops:
                    if o.get("op") == "attach_don":
                        if o.get("target_kind") in {"self", "", None} or not o.get("name_contains"):
                            o["target_kind"] = "own_character"
                            o["name_contains"] = name
                            stats["attach_name"] += 1
                            changed = True

            # 6) set_character_active count
            m_sa = SET_ACTIVE_COUNT_RE.search(chunk)
            if m_sa and not re.search(r"will not become active|不會置為活動", chunk, re.I):
                n = int(next(g for g in m_sa.groups() if g))
                for o in ops:
                    if o.get("op") == "set_character_active" and int(o.get("count") or 1) != n:
                        o["count"] = n
                        o["optional"] = True
                        stats["set_active_count"] += 1
                        changed = True

            # 7) choose_one inject
            if CHOOSE_ONE_RE.search(chunk) and not any(o.get("op") == "choose_one" for o in ops):
                co = _parse_choose_one_op(chunk)
                if co:
                    cost_ops = [
                        o
                        for o in ops
                        if o.get("as_cost")
                        or (
                            o.get("op") in {"trash_to_bottom", "return_don", "rest_don", "trash_hand", "trash_life"}
                            and re.search(r":|：", chunk)
                            and o.get("op") != "choose_one"
                        )
                    ]
                    # Prefer cost ops that appear before "Choose one"
                    pre = CHOOSE_ONE_RE.split(chunk, maxsplit=1)[0]
                    cost_ops = [
                        o
                        for o in ops
                        if o.get("as_cost")
                        or (
                            o.get("op") in {"trash_to_bottom", "return_don", "rest_don"}
                            and re.search(r"trash|place|bottom|DON!!\s*[−\-]|休息", pre, re.I)
                        )
                    ]
                    ops = cost_ops + [co]
                    seen: set[tuple] = set()
                    uniq: list[dict] = []
                    for o in ops:
                        key = (
                            o.get("op"),
                            o.get("count"),
                            o.get("owner"),
                            str(o.get("options"))[:60] if o.get("op") == "choose_one" else o.get("target_kind"),
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        uniq.append(o)
                    ops = uniq
                    # Opp hand gate from choose branch text
                    m_gate = re.search(
                        r"opponent has\s*(\d+)\s*or more|對手的手牌有\s*(\d+)\s*以上|对手的手牌有\s*(\d+)\s*以上",
                        chunk,
                        re.I,
                    )
                    if m_gate and a.get("require_opp_hand_gte") is None:
                        # Don't force on ability — gate is branch-local; stamp on trash_hand summary only
                        pass
                    stats["choose_one"] += 1
                    changed = True

            a["ops"] = ops
            na = normalize_ability(a)
            if na:
                new_abs.append(na)

        # Inject missing [Main] look/search ability when only counter exists
        if re.search(r"\[Main\]|【主要】", blob) and LOOK_RE.search(blob):
            has_main = any(str(a.get("timing")) in {"main_start", "activate_main"} for a in new_abs)
            if not has_main:
                main_chunk = _trim_cross_timing(_timing_chunk(blob, "main_start"), "main_start") or ""
                parsed = _parse_look_top_search(main_chunk) if main_chunk else None
                if parsed:
                    ab: dict[str, Any] = {"timing": "main_start", "ops": [parsed], "status": "compiled"}
                    if re.search(r"if your Leader is \[([^\]]+)\]|若自己的領航卡是「([^」]+)」", main_chunk, re.I):
                        m = re.search(
                            r"if your Leader is \[([^\]]+)\]|若自己的領航卡是「([^」]+)」|若自己的领航卡是「([^」]+)」",
                            main_chunk,
                            re.I,
                        )
                        if m:
                            ab["require_leader_name"] = next(g for g in m.groups() if g)
                    na = normalize_ability(ab)
                    if na:
                        new_abs.append(na)
                        stats["search_inject"] += 1
                        changed = True

        if not changed:
            continue
        fixed = normalize_card_entry(cid, {"version": 1, "abilities": new_abs})
        cards[cid] = fixed
        overrides[cid] = fixed
        stats["cards_touched"] += 1
        touched.append(cid)

    print(json.dumps({"stats": stats, "touched": len(touched)}, ensure_ascii=False))
    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    OUT_IDS.write_text("\n".join(touched) + ("\n" if touched else ""), encoding="utf-8")
    if args.dry_run:
        return 0
    raw["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if "cards" in raw:
        raw["cards"] = cards
    lib_path.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ovr_raw["cards"] = overrides
    ovr_raw["generated_at"] = raw["generated_at"]
    ovr_path.write_text(json.dumps(ovr_raw, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    reload_effect_library(force=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
