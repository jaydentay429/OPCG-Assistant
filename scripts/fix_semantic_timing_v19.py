#!/usr/bin/env python3
"""Split cross-timing bleed, dedupe ops, fix leader buffs, inject play-from-trash / field gates.

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
from battle.effect_schema import normalize_ability, normalize_card_entry  # noqa: E402
from battle.effects import (  # noqa: E402
    _extract_require_field_char_cost_0_or_gte,
    _parse_play_from_zone,
    effect_blob,
)
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "timing_v19_fixed_ids.txt"

# Op → text markers that justify keeping it in a timing chunk.
OP_MARKERS: dict[str, str] = {
    "attach_don": r"attach|附加|rested DON|DON!! card each|give.{0,80}DON|給予.{0,40}咚|给予.{0,40}咚",
    "gain_don": r"add up to\s*\d+\s*DON|獲得最多.{0,12}咚|获得最多.{0,12}咚|Add up to\s*\d+\s*DON",
    "draw": r"\bdraw\b|抽\s*\d+|抽牌",
    "buff": r"gains?\s*[+＋−\-－]?\s*\d{3,5}\s*power|力量值\s*[+＋−\-－]\s*\d{3,5}|give.{0,80}power|Give up to.{0,80}[−\-－+＋]\s*\d{3,5}\s*power",
    "buff_self": r"this Character gains|這張角色卡.{0,12}力量|这张角色卡.{0,12}力量",
    "trash_deck_top": r"trash\s*\d+\s*cards? from the top|卡組上面.{0,20}廢棄|卡组上面.{0,20}废弃",
    "trash_hand": r"trash\s*\d+\s*cards? from your hand|廢棄\s*\d+\s*[張张].{0,8}手牌|废弃\s*\d+\s*[张張].{0,8}手牌",
    "opponent_hand_to_bottom": r"places?\s*\d+\s*cards? from (?:their|the) hand at the bottom|手牌.{0,12}卡組底|手牌.{0,12}卡组底",
    "reduce_cost": r"[−\-－]\s*\d+\s*cost|費用\s*[−\-－]\s*\d+|费用\s*[−\-－]\s*\d+",
    "return_to_bottom": r"(?:place|return).{0,50}(?:your Character|自己的角色).{0,40}bottom|bottom of the owner'?s? deck|卡組下面|卡组下面",
    "return_to_hand": r"return.{0,40}hand|放回.{0,12}手牌",
    "ko": r"K\.?O\.?|击破|擊破",
    "trash": r"trash (?:up to )?\d+\s*of |trash this|放置到廢棄區|放置到废弃区|废弃1[張张]对手|廢棄1[張张]對手",
    "search_deck": r"look at|search|查看|檢視|检视|检索|檢索",
    "play_from_hand": r"play up to|使最多.{0,40}登場|使最多.{0,40}登场|Play this card|使這張卡片登場|使这张卡片登场",
    "grant_keyword": r"\[Blocker\]|\[Rush\]|\[Banish\]|\[Double Attack\]|【防禦】|【防御】|【速攻】|【消失】|【双重|【雙重",
    "cannot_take_life": r"cannot add Life|無法.{0,20}生命|无法.{0,20}生命",
    "negate_effects": r"negate|無效|无效",
    "rest_don": r"rest\s*\d+\s*of your DON|咚‼?卡置[為为]休息",
    "rest_character": r"rest .{0,40}Character|角色卡置[為为]休息",
    "rest_opponent_character": r"rest .{0,30}opponent|對手.{0,20}置[為为]休息|对手.{0,20}置为休息",
    "set_character_active": r"set .{0,40}as active|置[為为]活動",
    "active_don": r"DON!! cards? as active|咚‼?卡置[為为]活動",
    "trash_life": r"trash .{0,30}[Ll]ife|廢棄.{0,20}生命|废弃.{0,20}生命",
    "life_to_hand": r"[Ll]ife.{0,20}hand|生命.{0,20}手牌",
    "hand_to_life": r"hand.{0,30}[Ll]ife|手牌.{0,20}生命",
    "add_life": r"add .{0,40}[Ll]ife|加到生命",
    "hand_to_deck": r"hand.{0,30}deck|手牌.{0,20}卡組|手牌.{0,20}卡组",
}


def _chunk_justifies(op_name: str, chunk: str) -> bool | None:
    """True/False if we have a marker; None if unknown op (keep)."""
    pat = OP_MARKERS.get(op_name)
    if not pat:
        return None
    return bool(re.search(pat, chunk, re.I))


def _dedupe_ops(ops: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    dropped = 0
    for o in ops:
        key = (
            o.get("op"),
            o.get("target_kind"),
            o.get("count"),
            o.get("amount"),
            o.get("cost_lte"),
            o.get("cost_eq"),
            o.get("power_lte"),
            o.get("keyword"),
            o.get("from_zone"),
            o.get("as_cost"),
            o.get("name_contains"),
            o.get("trait_contains"),
        )
        if key in seen and o.get("op") in {
            "return_to_hand",
            "trash_life",
            "hand_to_life",
            "draw",
            "buff",
            "buff_self",
            "trash_deck_top",
            "cannot_take_life",
            "gain_don",
            "attach_don",
            "ko",
            "trash",
            "reduce_cost",
        }:
            dropped += 1
            continue
        seen.add(key)
        out.append(o)
    return out, dropped


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
        "timing_scrub": 0,
        "dedupe": 0,
        "leader_buff": 0,
        "duration_turn": 0,
        "play_trash": 0,
        "field_0_or_gte": 0,
        "force_optional_false": 0,
        "drop_onplay_gate": 0,
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
        multi = len(abilities) > 1

        # Precompute chunks per ability index
        chunks: list[str] = []
        for a in abilities:
            timing = str(a.get("timing") or "")
            chunk = _trim_cross_timing(_timing_chunk(blob, timing), timing) or ""
            if multi and (not chunk or chunk == blob):
                chunk = _trim_cross_timing(str(a.get("summary") or ""), timing) or chunk
            chunks.append(chunk)

        # Work lists: (ability_dict, ops_list, chunk)
        work: list[tuple[dict, list[dict], str]] = []
        orphan_ops: list[dict] = []

        for idx, a0 in enumerate(abilities):
            a = dict(a0)
            timing = str(a.get("timing") or "")
            chunk = chunks[idx]
            ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

            # 1) Cross-timing scrub: known ops must be justified by this timing's chunk
            if multi and chunk:
                kept: list[dict] = []
                for o in ops:
                    name = str(o.get("op") or "")
                    here = _chunk_justifies(name, chunk)
                    if here is True or here is None:
                        kept.append(o)
                        continue
                    orphan_ops.append(o)
                    stats["timing_scrub"] += 1
                    changed = True
                ops = kept

            work.append((a, ops, chunk))

        # Rehome orphans into timings that justify them
        if orphan_ops:
            for o in orphan_ops:
                name = str(o.get("op") or "")
                placed = False
                for a, ops, chunk in work:
                    if not chunk:
                        continue
                    if _chunk_justifies(name, chunk) is True and not any(
                        x.get("op") == name
                        and x.get("target_kind") == o.get("target_kind")
                        and x.get("amount") == o.get("amount")
                        for x in ops
                    ):
                        ops.append(dict(o))
                        placed = True
                        changed = True
                        break

        new_abs: list[dict] = []
        for a, ops, chunk in work:
            timing = str(a.get("timing") or "")

            # 2) Dedupe
            ops, dropped = _dedupe_ops(ops)
            if dropped:
                stats["dedupe"] += dropped
                changed = True

            # 3) Leader buff: paper says Leader gains, not this Character / own_character only
            if re.search(
                r"(?:your |自己的)?Leader gains|領航卡.{0,12}力量值\s*[+＋]|领航卡.{0,12}力量值\s*[+＋]|"
                r"Up to 1 of your Leader(?! or Character)|最多1[張张]自己的領航卡(?!或角色)|最多1[张張]自己的领航卡(?!或角色)",
                chunk,
                re.I,
            ) and not re.search(r"Leader or Character|領航卡或角色|领航卡或角色", chunk, re.I):
                for o in ops:
                    if o.get("op") == "buff_self":
                        o["op"] = "buff"
                        o["target_kind"] = "leader"
                        o["optional"] = True
                        stats["leader_buff"] += 1
                        changed = True
                    elif o.get("op") == "buff" and o.get("target_kind") in {
                        "own_character",
                        "self",
                        "own_character_or_leader",
                    }:
                        o["target_kind"] = "leader"
                        stats["leader_buff"] += 1
                        changed = True

            # Leader or Character → fix buff_self
            if re.search(r"Leader or Character|領航卡或角色|领航卡或角色", chunk, re.I):
                for o in ops:
                    if o.get("op") == "buff_self":
                        o["op"] = "buff"
                        o["target_kind"] = "own_leader_or_character"
                        o["optional"] = True
                        stats["leader_buff"] += 1
                        changed = True

            # 4) duration turn for grant_keyword / buff when during this turn
            if re.search(r"during this turn|在這個回合|在这个回合|during this battle|在這場對戰|在这场对战", chunk, re.I):
                for o in ops:
                    if o.get("op") == "grant_keyword" and o.get("duration") == "permanent":
                        if re.search(r"during this battle|在這場對戰|在这场对战", chunk, re.I):
                            o["duration"] = "battle"
                        else:
                            o["duration"] = "turn"
                        stats["duration_turn"] += 1
                        changed = True

            # 5) play from trash missing
            play = _parse_play_from_zone(chunk) if chunk else None
            if isinstance(play, dict) and play.get("from_zone") in {"trash", "hand_or_trash"}:
                if not any(o.get("op") == "play_from_hand" for o in ops):
                    ops.append(play)
                    stats["play_trash"] += 1
                    changed = True
                else:
                    for o in ops:
                        if o.get("op") == "play_from_hand" and o.get("from_zone") not in {"trash", "hand_or_trash"}:
                            o["from_zone"] = play["from_zone"]
                            for k in ("cost_lte", "cost_eq", "trait_contains", "name_contains", "as_rested"):
                                if play.get(k) is not None and o.get(k) in (None, ""):
                                    o[k] = play[k]
                            stats["play_trash"] += 1
                            changed = True

            # 6) field cost 0 or N+
            gte = _extract_require_field_char_cost_0_or_gte(chunk)
            if gte is not None:
                if a.get("require_field_char_cost_eq") == 0:
                    a.pop("require_field_char_cost_eq", None)
                    changed = True
                if int(a.get("require_field_char_cost_0_or_gte") or -1) != gte:
                    a["require_field_char_cost_0_or_gte"] = gte
                    stats["field_0_or_gte"] += 1
                    changed = True
                for o in ops:
                    if o.get("op") == "draw" and o.get("require_field_char_cost_0_or_gte") is None:
                        o["require_field_char_cost_0_or_gte"] = gte
                        changed = True

            # 7) Force optional=False for mandatory KO / trash_deck_top without you may/up to
            for o in ops:
                if o.get("op") in {"ko", "trash_deck_top", "draw"} and o.get("optional") is True:
                    if o.get("op") == "trash_deck_top" and re.search(
                        r"trash\s*\d+\s*cards? from the top|將\s*\d+\s*[張张].{0,20}卡組上面|将\s*\d+\s*[张張].{0,20}卡组上面",
                        chunk,
                        re.I,
                    ):
                        if not re.search(r"you may|可[將将]|up to|最多", chunk, re.I):
                            o["optional"] = False
                            stats["force_optional_false"] += 1
                            changed = True
                    if o.get("op") == "ko" and re.search(r"K\.?O\.?", chunk, re.I):
                        if not re.search(r"you may|可[將将]|up to|最多", chunk, re.I):
                            o["optional"] = False
                            stats["force_optional_false"] += 1
                            changed = True

            # 8) Drop spurious leader gates on on_play when chunk has no leader condition
            if timing == "on_play" and chunk and not re.search(
                r"if your Leader|若自己的領航|若自己的领航", chunk, re.I
            ):
                for key in ("require_leader_name", "require_leader_trait", "require_leader_color"):
                    if a.get(key):
                        a.pop(key, None)
                        stats["drop_onplay_gate"] += 1
                        changed = True

            a["ops"] = ops
            na = normalize_ability(a)
            if na:
                new_abs.append(na)

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
