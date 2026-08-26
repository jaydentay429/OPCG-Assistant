#!/usr/bin/env python3
"""Leader gates + refill empty abilities + hand_to_deck all/shuffle.

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
    _parse_buff_all_own_ops,
    _parse_grant_keyword_ops,
    _parse_hand_to_deck_ops,
    _parse_leader_or_char_buff,
    _parse_place_on_bottom_ops,
    _parse_play_from_zone,
    _parse_rest_opponent_ops,
    _parse_return_char_to_hand_ops,
    effect_blob,
    parse_activate_main,
    parse_trigger_ops,
)
from fix_semantic_gates_v2 import (  # noqa: E402
    LEADER_NAME_RE,
    LEADER_TRAIT_RE,
    _timing_chunk,
    _trim_cross_timing,
)

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "leader_fill_v24_fixed_ids.txt"

LEADER_POWER_COST_RE = re.compile(
    r"(?:you may )?(?:give )?(?:your )?(?:active )?Leader\s*[−\-－]\s*(\d{3,5}).{0,40}:|"
    r"可以?[將将]1張自己活動狀態的領航卡力量值\s*[−\-－]\s*(\d{3,5})\s*[：:]|"
    r"可以?[將将]1张自己活动状态的领航卡力量值\s*[−\-－]\s*(\d{3,5})\s*[：:]",
    re.I,
)
OPP_BUFF_RE = re.compile(
    r"(?:give|gains?)(?:\s+up to\s*(\d+)\s+of)?\s+(?:your )?opponent'?s Characters?"
    r".{0,40}([+\-−－])\s*(\d{3,5})\s*power|"
    r"最多\s*(\d+)\s*[張张]對手的角色卡.{0,24}力量(?:值)?\s*([+\-−－])\s*(\d{3,5})",
    re.I,
)
NAMED_BUFF_RE = re.compile(
    r"(?:up to\s*(\d+)\s+of )?your \[([^\]]+)\](?: cards?)? gains?\s*[+＋]\s*(\d{3,5})\s*power|"
    r"最多\s*(\d+)\s*[張张]?自己的「([^」]+)」.{0,24}力量(?:值)?\s*[+＋]\s*(\d{3,5})",
    re.I,
)
TRASH_SELF_RE = re.compile(
    r"(?:you may )?trash this Character\s*:|"
    r"可?[將将]這張角色卡放置在廢棄區\s*[：:]|"
    r"可?[将將]这张角色卡放置在废弃区\s*[：:]",
    re.I,
)
OPP_CHOOSE_TRASH_HAND_RE = re.compile(
    r"(?:your )?opponent chooses?\s*1 card from your hand.{0,40}trash|"
    r"對手選擇1張自己的手牌.{0,20}廢棄|对手选择1张自己的手牌.{0,20}废弃",
    re.I,
)


def _leader_trait_from_chunk(chunk: str) -> str | None:
    chunk_en = re.split(r"[\n]|若自己的|【", chunk or "")[0]
    m = LEADER_TRAIT_RE.search(chunk_en) or LEADER_TRAIT_RE.search(chunk or "")
    if not m:
        return None
    brace = re.findall(r"\{([^}]+)\}", m.group(0))
    if brace:
        return "|".join(t.strip() for t in brace if t.strip())[:80]
    traits = [g.strip() for g in m.groups() if g and g.strip()]
    return "|".join(traits)[:80] if traits else None


def _fill_ops(timing: str, chunk: str, info: dict[str, Any]) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    if timing == "activate_main":
        parsed = parse_activate_main(info)
        if parsed and parsed.get("ops"):
            ops.extend(list(parsed["ops"]))
    if timing == "trigger":
        ops.extend(parse_trigger_ops(info))

    # Leader power cost → buff leader negative (as cost style)
    m = LEADER_POWER_COST_RE.search(chunk)
    if m and not any(o.get("op") == "buff" and o.get("target_kind") == "leader" for o in ops):
        amt = -abs(int(next(g for g in m.groups() if g)))
        ops.insert(0, {"op": "buff", "amount": amt, "target_kind": "leader", "optional": True, "as_cost": True})

    if TRASH_SELF_RE.search(chunk) and not any(o.get("op") == "trash" and o.get("target_kind") == "self" for o in ops):
        ops.insert(0, {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True})

    buff = _parse_leader_or_char_buff(chunk)
    if buff and not any(o.get("op") == "buff" for o in ops):
        ops.append(buff)

    m_ob = OPP_BUFF_RE.search(chunk)
    if m_ob and not any(o.get("op") == "buff" and "opponent" in str(o.get("target_kind") or "") for o in ops):
        gs = [g for g in m_ob.groups() if g]
        # count?, sign, amount
        if len(gs) >= 2:
            if gs[0] in "+-−－＋" or (len(gs) >= 3 and gs[-2] in "+-−－＋"):
                sign = gs[-2] if gs[-2] in "+-−－＋" else gs[0]
                amt = int(gs[-1])
                if sign in "-−－":
                    amt = -abs(amt)
            else:
                amt = -abs(int(gs[-1]))
            ops.append({"op": "buff", "amount": amt, "target_kind": "opponent_character", "optional": True})

    m_nb = NAMED_BUFF_RE.search(chunk)
    if m_nb and not any(o.get("op") == "buff" and o.get("name_contains") for o in ops):
        gs = [g for g in m_nb.groups() if g]
        if len(gs) >= 2:
            name = gs[-2] if not gs[-2].isdigit() else gs[0]
            amt = int(gs[-1])
            # fix: groups are count?, name, amount
            if len(gs) == 3:
                name, amt = gs[1], int(gs[2])
            elif len(gs) == 2:
                name, amt = gs[0], int(gs[1])
            ops.append(
                {
                    "op": "buff",
                    "amount": amt,
                    "target_kind": "own_character",
                    "name_contains": name,
                    "optional": True,
                }
            )

    for o in _parse_rest_opponent_ops(chunk):
        if not any(x.get("op") == o.get("op") for x in ops):
            ops.append(o)
    for o in _parse_return_char_to_hand_ops(chunk):
        if not any(x.get("op") == "return_to_hand" for x in ops):
            ops.append(o)
    for o in _parse_hand_to_deck_ops(chunk):
        if not any(x.get("op") == "hand_to_deck" for x in ops):
            ops.append(o)
    for o in _parse_grant_keyword_ops(chunk):
        if not any(x.get("op") == "grant_keyword" and x.get("keyword") == o.get("keyword") for x in ops):
            ops.append(o)
    for o in _parse_buff_all_own_ops(chunk):
        if not any(x.get("op") == "buff_all_own" for x in ops):
            ops.append(o)
    play = _parse_play_from_zone(chunk)
    if play and not any(o.get("op") == "play_from_hand" for o in ops):
        ops.append(play)
    for o in _parse_place_on_bottom_ops(chunk):
        if not any(x.get("op") == o.get("op") for x in ops):
            ops.append(o)

    if OPP_CHOOSE_TRASH_HAND_RE.search(chunk) and not any(o.get("op") == "trash_hand" for o in ops):
        ops.append({"op": "trash_hand", "count": 1, "optional": False, "owner": "self", "summary": "Opponent chooses 1 from your hand to trash"})

    # Draw
    m_d = re.search(r"[Dd]raw\s*(\d+)|抽\s*(\d+)", chunk)
    if m_d and not any(o.get("op") == "draw" for o in ops):
        ops.append({"op": "draw", "count": int(next(g for g in m_d.groups() if g))})

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for o in ops:
        so = sanitize_op(o)
        if not so:
            continue
        key = json.dumps(so, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        out.append(so)
    return out


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
        "leader_trait": 0,
        "leader_name": 0,
        "empty_fill": 0,
        "hand_all": 0,
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
        new_abs: list[dict[str, Any]] = []
        multi = len(abilities) > 1

        for a in abilities:
            a = dict(a)
            timing = str(a.get("timing") or "")
            chunk = _trim_cross_timing(_timing_chunk(blob, timing), timing) or ""
            if multi and (not chunk or chunk == blob):
                chunk = _trim_cross_timing(str(a.get("summary") or ""), timing) or chunk
            ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

            # Leader trait / name gates (EN clause only to avoid bleed)
            trait = _leader_trait_from_chunk(chunk)
            if trait and not a.get("require_leader_trait"):
                a["require_leader_trait"] = trait
                changed = True
                stats["leader_trait"] += 1
            chunk_en = re.split(r"[\n]|若自己的|【", chunk)[0]
            m_name = LEADER_NAME_RE.search(chunk_en) or LEADER_NAME_RE.search(chunk)
            if m_name and not a.get("require_leader_name"):
                a["require_leader_name"] = m_name.group(1).strip()[:60]
                changed = True
                stats["leader_name"] += 1

            # Refill empty abilities
            if not ops:
                filled = _fill_ops(timing, chunk, info)
                if filled:
                    ops = filled
                    # carry rest_self / once from parse_activate_main
                    if timing == "activate_main":
                        parsed = parse_activate_main(info)
                        if parsed:
                            if parsed.get("rest_self"):
                                a["rest_self"] = True
                            if parsed.get("once"):
                                a["once"] = True
                            if parsed.get("cost_don"):
                                a["cost_don"] = parsed["cost_don"]
                            if parsed.get("require_leader_trait") and not a.get("require_leader_trait"):
                                a["require_leader_trait"] = parsed["require_leader_trait"]
                    changed = True
                    stats["empty_fill"] += 1

            # Inject hand_to_deck all when missing
            htd = _parse_hand_to_deck_ops(chunk)
            if htd and any(o.get("all") for o in htd):
                if not any(o.get("op") == "hand_to_deck" and o.get("all") for o in ops):
                    # Replace wrong return_to_hand stand-ins
                    ops = [o for o in ops if not (o.get("op") == "return_to_hand" and not o.get("cost_lte"))]
                    ops = htd + ops
                    changed = True
                    stats["hand_all"] += 1

            # Fix named buff when parse had buff_self for named character
            m_nb = NAMED_BUFF_RE.search(chunk)
            if m_nb:
                gs = [g for g in m_nb.groups() if g]
                name = gs[1] if len(gs) >= 3 else gs[0]
                amt = int(gs[-1])
                if any(o.get("op") == "buff_self" for o in ops) and re.search(r"「|\[", chunk):
                    ops = [o for o in ops if o.get("op") != "buff_self"]
                    ops.append(
                        {
                            "op": "buff",
                            "amount": amt,
                            "target_kind": "own_character",
                            "name_contains": name,
                            "optional": True,
                        }
                    )
                    changed = True
                    stats["empty_fill"] += 1

            a["ops"] = [sanitize_op(o) for o in ops if sanitize_op(o)]
            na = normalize_ability(a)
            if na and (na.get("ops") or na.get("status") == "verified"):
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
