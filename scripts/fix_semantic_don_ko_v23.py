#!/usr/bin/env python3
"""DON!!x gate placement, empty on_ko/end_turn fill, cannot_be_ko, grant gates.

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
    _parse_cannot_be_ko_ops,
    _parse_grant_keyword_ops,
    _parse_place_on_bottom_ops,
    _parse_play_from_zone,
    _parse_return_char_to_hand_ops,
    effect_blob,
)
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "don_ko_v23_fixed_ids.txt"

DON_X_RE = re.compile(r"\[DON!!\s*[xX×]\s*(\d+)\]|【咚‼?\s*[×xX]\s*(\d+)】", re.I)
DON_FIELD_RE = re.compile(
    r"(?:if you have|若自己的?場上有|若自己的?场上有)\s*(\d+)\s*(?:or more )?DON!!|"
    r"場上有\s*(\d+)\s*[張张](?:以上)?咚|场上有\s*(\d+)\s*[张張](?:以上)?咚|"
    r"(\d+)\s*DON!! cards? on your field",
    re.I,
)
DON_ACTIVE_RE = re.compile(
    r"(?:if you have\s*)?(\d+)\s*or more active DON|"
    r"活動狀態的咚‼?卡有\s*(\d+)\s*[張张]以上|"
    r"活动状态的咚‼?卡有\s*(\d+)\s*[张張]以上",
    re.I,
)
ADD_LIFE_RE = re.compile(
    r"add up to\s*(\d+)\s*cards? from the top of your deck to the top of your Life|"
    r"將最多\s*(\d+)\s*[張张]自己卡組上面的卡片加[入到]生命|"
    r"将最多\s*(\d+)\s*[张張]自己卡组上面的卡片加[入到]生命",
    re.I,
)
SET_ACTIVE_RE = re.compile(
    r"set (?:up to\s*(\d+)\s*of )?your Characters?(?: with a cost of\s*(\d+)\s*or less)? as active|"
    r"set this Character as active|"
    r"將最多\s*(\d+)\s*[張张]自己(?:費用|费用)\s*(\d+)\s*以下.{0,12}置[為为]活動|"
    r"將這張角色卡置[為为]活動|将这张角色卡置为活动|"
    r"将最多\s*(\d+)\s*[张張]自己(?:费用|費用)\s*(\d+)\s*以下.{0,12}置为活动",
    re.I,
)
CIRCLED_COST = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5, "➀": 1, "➁": 2, "➂": 3}
PRINTED_BLOCKER_ONLY = re.compile(
    r"^\[Blocker\]\s*\([^)]*\)\s*$|^【防禦】\s*[（(][^)）]*[)）]\s*$|^【防御】\s*[（(][^)）]*[)）]\s*$",
    re.I,
)
FIELD_NAME_GATE = re.compile(
    r"(?:if you have|若自己場上有|若自己场上有)\s*[「\[]([^」\]]+)[」\]]",
    re.I,
)
OPP_COST0_RE = re.compile(
    r"opponent has a Character with a cost of\s*0|對手費用0|对手费用0|對手有費用0|对手有费用0",
    re.I,
)
OWN_RETURN_RE = re.compile(
    r"return 1 of your Characters? to the owner'?s hand|"
    r"將1張自己的角色卡放回持有者的手牌|将1张自己的角色卡放回持有者的手牌",
    re.I,
)


def _leading_don(chunk: str) -> int | None:
    if not chunk:
        return None
    m = re.match(r"\s*(?:\[DON!!\s*[xX×]\s*(\d+)\]|【咚‼?\s*[×xX]\s*(\d+)】)", chunk, re.I)
    if m:
        return int(next(g for g in m.groups() if g))
    # Also accept DON immediately before timing header already included
    m2 = DON_X_RE.search(chunk[:60])
    if m2 and chunk.find(m2.group(0)) < 40:
        return int(next(g for g in m2.groups() if g))
    return None


def _fill_on_ko(chunk: str) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    m_ret = re.search(r"DON!!\s*[−\-－]\s*(\d+)|咚‼?\s*[−\-－]\s*(\d+)", chunk, re.I)
    if m_ret:
        ops.append({"op": "return_don", "count": int(next(g for g in m_ret.groups() if g)), "owner": "self"})
    m_life = ADD_LIFE_RE.search(chunk)
    if m_life:
        ops.append({"op": "add_life", "count": int(next(g for g in m_life.groups() if g)), "optional": True})
    play = _parse_play_from_zone(chunk)
    if play:
        ops.append(play)
    return [o for o in (sanitize_op(x) for x in ops) if o]


def _fill_end_turn(chunk: str) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    # circled cost → rest_don as cost
    for ch, n in CIRCLED_COST.items():
        if ch in chunk:
            ops.append({"op": "rest_don", "count": n, "as_cost": True})
            break
    m = SET_ACTIVE_RE.search(chunk)
    if m or re.search(r"置[為为]活動|置为活动|as active", chunk, re.I):
        op: dict[str, Any] = {
            "op": "set_character_active",
            "optional": True,
            "target_kind": "self" if re.search(r"this Character|這張角色|这张角色", chunk, re.I) else "own_character",
            "count": 1,
        }
        nums = [int(g) for g in (m.groups() if m else ()) if g]
        if len(nums) >= 2:
            op["count"] = nums[0]
            op["cost_lte"] = nums[1]
        elif len(nums) == 1 and re.search(r"cost of|費用|费用", chunk, re.I):
            op["cost_lte"] = nums[0]
        ops.append(op)
    return [o for o in (sanitize_op(x) for x in ops) if o]


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
        "don_x_set": 0,
        "don_x_drop": 0,
        "don_field": 0,
        "don_active": 0,
        "on_ko_fill": 0,
        "end_fill": 0,
        "cannot_be_ko": 0,
        "grant_fix": 0,
        "drop_printed_blocker": 0,
        "rth": 0,
        "bottom": 0,
        "name_gate": 0,
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
            # Try inject continuous / on_ko from empty library
            if not (
                re.search(r"\[On K\.?O\.?\]|【KO時】|【KO时】", blob, re.I)
                or re.search(r"cannot be K\.?O|不會因效果|不会因效果|對戰中不會|对战中不会", blob, re.I)
                or DON_X_RE.search(blob)
            ):
                continue
            abilities = []

        changed = False
        by_timing: dict[str, dict[str, Any]] = {}
        for a in abilities:
            t = str(a.get("timing") or "")
            if t:
                by_timing[t] = dict(a)

        # Ensure on_ko / end_of_your_turn stubs exist when paper has them
        for t, pat in (
            ("on_ko", r"\[On K\.?O\.?\]|【KO時】|【KO时】|When this Character is K\.?O"),
            ("end_of_your_turn", r"\[End of Your Turn\]|【我方的?回合結束時】|【我方的?回合结束时】"),
        ):
            if t not in by_timing and re.search(pat, blob, re.I):
                by_timing[t] = {
                    "timing": t,
                    "ops": [],
                    "status": "compiled",
                    "confidence": 0.85,
                    "summary": "",
                }
                changed = True
        # Continuous cannot_be_ko / grant without timed header → your_turn
        if "your_turn" not in by_timing and re.search(
            r"cannot be K\.?O|不會因效果|不会因效果|對戰中不會遭到KO|对战中不会遭到KO",
            blob,
            re.I,
        ):
            if not re.search(r"\[On Play\].{0,80}gains? \[|【登場時】.{0,40}獲得【", blob, re.I):
                by_timing["your_turn"] = {
                    "timing": "your_turn",
                    "ops": [],
                    "status": "compiled",
                    "confidence": 0.85,
                    "summary": "",
                }
                changed = True
        if "your_turn" not in by_timing and re.search(
            r"(?:If you have|若自己場上有|若自己场上有).{0,80}gains? \[|這張角色卡獲得【|这张角色卡获得【",
            blob,
            re.I,
        ):
            if not re.search(r"\[On Play\]|【登場時】|【登场时】", blob, re.I):
                by_timing["your_turn"] = {
                    "timing": "your_turn",
                    "ops": [],
                    "status": "compiled",
                    "confidence": 0.85,
                    "summary": "",
                }
                changed = True

        multi = len(by_timing) > 1
        for timing, a in list(by_timing.items()):
            a = dict(a)
            chunk = _trim_cross_timing(_timing_chunk(blob, timing), timing) or ""
            if multi and (not chunk or chunk == blob):
                chunk = _trim_cross_timing(str(a.get("summary") or ""), timing) or chunk
            ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

            # 1) DON!! xN gate placement
            want_don = _leading_don(chunk)
            have_don = a.get("require_don_attached_gte")
            if want_don is not None:
                if int(have_don or 0) != want_don:
                    a["require_don_attached_gte"] = want_don
                    changed = True
                    stats["don_x_set"] += 1
            elif have_don is not None and timing in {
                "on_play",
                "on_block",
                "trigger",
                "counter_event",
                "main_start",
            }:
                # Bleed onto timings that don't lead with DON!! xN
                if not DON_X_RE.search(chunk[:80] if chunk else ""):
                    a.pop("require_don_attached_gte", None)
                    changed = True
                    stats["don_x_drop"] += 1

            # 2) Field DON count gate
            m_df = DON_FIELD_RE.search(chunk)
            if m_df and a.get("require_don_field_gte") is None:
                a["require_don_field_gte"] = int(next(g for g in m_df.groups() if g))
                changed = True
                stats["don_field"] += 1

            # 3) Active DON gate
            m_da = DON_ACTIVE_RE.search(chunk)
            if m_da and a.get("require_don_active_gte") is None:
                a["require_don_active_gte"] = int(next(g for g in m_da.groups() if g))
                changed = True
                stats["don_active"] += 1

            # 4) Fill empty on_ko
            if timing == "on_ko" and not ops:
                filled = _fill_on_ko(chunk)
                if filled:
                    ops = filled
                    changed = True
                    stats["on_ko_fill"] += 1
            elif timing == "on_ko":
                # Ensure add_life present when text has it
                if ADD_LIFE_RE.search(chunk) and not any(o.get("op") == "add_life" for o in ops):
                    m = ADD_LIFE_RE.search(chunk)
                    ops.append({"op": "add_life", "count": int(next(g for g in m.groups() if g)), "optional": True})
                    changed = True
                    stats["on_ko_fill"] += 1
                if re.search(r"from your deck|從卡組|从卡组", chunk, re.I) and not any(
                    o.get("op") == "play_from_hand" for o in ops
                ):
                    play = _parse_play_from_zone(chunk)
                    if play:
                        ops.append(play)
                        changed = True
                        stats["on_ko_fill"] += 1
                # Fix wrong from_zone=hand when paper is from deck
                if re.search(r"from your deck|從卡組|从卡组", chunk, re.I):
                    for o in ops:
                        if o.get("op") == "play_from_hand" and o.get("from_zone") != "deck":
                            o["from_zone"] = "deck"
                            changed = True
                            stats["on_ko_fill"] += 1

            # 5) Fill empty end_of_your_turn
            if timing == "end_of_your_turn" and not ops:
                filled = _fill_end_turn(chunk)
                if filled:
                    ops = filled
                    # circled cost also as cost_don on ability
                    for ch, n in CIRCLED_COST.items():
                        if ch in chunk:
                            a["cost_don"] = n
                            break
                    changed = True
                    stats["end_fill"] += 1

            # 6) cannot_be_ko
            coko = _parse_cannot_be_ko_ops(chunk)
            if coko and timing in {"your_turn", "opponent_turn", "on_play"}:
                # Prefer your_turn / opponent_turn for continuous shields
                if timing == "on_play" and not re.search(r"\[On Play\]|【登場時】|【登场时】", chunk, re.I):
                    coko = []
            if coko:
                if not any(o.get("op") == "cannot_be_ko" for o in ops):
                    ops.extend(coko)
                    changed = True
                    stats["cannot_be_ko"] += 1
                else:
                    # Replace incomplete cannot_be_ko with parser result
                    ops = [o for o in ops if o.get("op") != "cannot_be_ko"] + coko
                    changed = True
                    stats["cannot_be_ko"] += 1
            # Drop cannot_be_ko bleed onto wrong timings
            if timing in {"on_play", "on_ko", "when_attacking", "end_of_your_turn", "activate_main"} and any(
                o.get("op") == "cannot_be_ko" for o in ops
            ):
                if not re.search(r"\[On Play\]|【登場時】|【登场时】", chunk[:30], re.I) and timing == "on_play":
                    ops = [o for o in ops if o.get("op") != "cannot_be_ko"]
                    changed = True
                elif timing != "on_play" and not re.search(
                    r"cannot be K\.?O|不會因效果|不会因效果|對戰中不會|对战中不会", chunk[:80], re.I
                ):
                    ops = [o for o in ops if o.get("op") != "cannot_be_ko"]
                    changed = True
                    stats["cannot_be_ko"] += 1

            # 7) grant_keyword fix + gates — only on timings whose chunk actually grants
            if re.search(r"gains? \[|獲得【|获得【", chunk, re.I) and not (
                timing != "on_play"
                and re.search(r"\[On Play\]|【登場時】|【登场时】", chunk, re.I)
                and timing in {"your_turn", "on_ko", "when_attacking", "end_of_your_turn"}
            ):
                grants = _parse_grant_keyword_ops(chunk)
                if grants and not any(o.get("op") == "grant_keyword" for o in ops):
                    ops.extend(grants)
                    changed = True
                    stats["grant_fix"] += 1
                # Fix wrong name target → self + field name gate
                for o in ops:
                    if o.get("op") != "grant_keyword":
                        continue
                    if o.get("name_contains") and re.search(
                        r"this Character gains|這張角色卡獲得|这张角色卡获得", chunk, re.I
                    ):
                        o["target_kind"] = "self"
                        o.pop("name_contains", None)
                        o.pop("optional", None)
                        o.pop("count", None)
                        changed = True
                        stats["grant_fix"] += 1
                m_name = FIELD_NAME_GATE.search(chunk)
                if m_name and a.get("require_own_name_on_field") is None:
                    a["require_own_name_on_field"] = m_name.group(1).strip()
                    changed = True
                    stats["name_gate"] += 1
                if OPP_COST0_RE.search(chunk) and a.get("require_field_char_cost_eq") is None:
                    a["require_field_char_cost_eq"] = 0
                    changed = True
                    stats["grant_fix"] += 1
                # Drop spurious buff_self when only granting keyword
                if any(o.get("op") == "grant_keyword" for o in ops) and any(
                    o.get("op") == "buff_self" for o in ops
                ):
                    if not re.search(r"gains?\s*[+＋]\s*\d{3,5}\s*power|力量值\s*[+＋]\s*\d{3,5}", chunk, re.I):
                        ops = [o for o in ops if o.get("op") != "buff_self"]
                        changed = True
                        stats["grant_fix"] += 1
            elif timing == "your_turn" and any(o.get("op") == "grant_keyword" for o in ops):
                # Drop grant bleed onto your_turn when paper grant is On Play only
                if re.search(r"\[On Play\].{0,120}gains? \[|【登場時】.{0,80}獲得【", blob, re.I) and not re.search(
                    r"\[Your Turn\].{0,80}gains? \[|【我方回合中】.{0,40}獲得【", blob, re.I
                ):
                    ops = [o for o in ops if o.get("op") != "grant_keyword"]
                    for k in list(a.keys()):
                        if k.startswith("require_field_char") or k == "require_own_name_on_field":
                            a.pop(k, None)
                    changed = True
                    stats["grant_fix"] += 1

            # 8) Drop printed-Blocker-only on_block grant
            if timing == "on_block":
                slim = re.sub(r"\s+", " ", chunk).strip()
                if PRINTED_BLOCKER_ONLY.search(slim) or (
                    re.search(r"^\[Blocker\]|^【防禦】|^【防御】", slim, re.I)
                    and not re.search(r"gains? \[Blocker\]|獲得【防禦】|获得【防御】", slim, re.I)
                ):
                    if any(o.get("op") == "grant_keyword" for o in ops):
                        ops = [o for o in ops if o.get("op") != "grant_keyword"]
                        changed = True
                        stats["drop_printed_blocker"] += 1
                    if a.get("require_don_attached_gte") is not None and not _leading_don(chunk):
                        a.pop("require_don_attached_gte", None)
                        changed = True
                        stats["don_x_drop"] += 1

            # 9) Own return-to-hand missing
            if OWN_RETURN_RE.search(chunk) and not any(
                o.get("op") == "return_to_hand"
                and str(o.get("target_kind") or "") in {"own_character", "self", "any_character"}
                for o in ops
            ):
                ops = [
                    {"op": "return_to_hand", "target_kind": "own_character", "optional": False, "count": 1},
                    *ops,
                ]
                changed = True
                stats["rth"] += 1

            # 10) Place opponent to bottom on when_attacking
            if timing == "when_attacking":
                bottoms = _parse_place_on_bottom_ops(chunk)
                if bottoms and not any(o.get("op") in {"return_to_bottom", "place_on_bottom"} for o in ops):
                    # also accept return_to_bottom naming
                    for b in bottoms:
                        ops.append(b)
                    changed = True
                    stats["bottom"] += 1

            a["ops"] = [sanitize_op(o) for o in ops if sanitize_op(o)]
            # Drop empty non-runnable stubs except continuous your_turn with gates only + cannot_be_ko
            na = normalize_ability(a)
            if na:
                by_timing[timing] = na

        # Drop empty your_turn that only had wrong don gate and no ops
        for t in list(by_timing.keys()):
            a = by_timing[t]
            if t in {"your_turn", "on_block"} and not (a.get("ops") or []):
                # keep if has meaningful continuous gate+op elsewhere; drop pure empty
                if not any(str(k).startswith("require_") and k not in {"require_don_attached_gte"} for k in a):
                    if a.get("require_don_attached_gte") and t == "your_turn":
                        # might be continuous rush with only don — keep if blob grants on your_turn
                        chunk = _trim_cross_timing(_timing_chunk(blob, t), t) or ""
                        if not re.search(r"gains?|獲得|获得|cannot|不會|不会", chunk, re.I):
                            del by_timing[t]
                            changed = True
                            continue

        new_abs = []
        for a in by_timing.values():
            na = normalize_ability(a)
            if na and (na.get("ops") or any(str(k).startswith("require_") for k in na)):
                # skip empty gate-only without ops unless your_turn continuous with cannot/grant already handled
                if not na.get("ops"):
                    continue
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
