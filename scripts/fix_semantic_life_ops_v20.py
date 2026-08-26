#!/usr/bin/env python3
"""Fix draw+trash counts/optional, life trash→add_life, trigger play-this, hand_to_deck.

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
from battle.effects import _parse_hand_to_deck_ops, effect_blob  # noqa: E402
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "life_ops_v20_fixed_ids.txt"

DRAW_TRASH_RE = re.compile(
    r"[Dd]raw\s*(\d+)\s*cards?(?: and|,)?\s*trash\s*(\d+)\s*cards?\s*from your hand|"
    r"抽\s*(\d+)\s*[張张](?:卡片)?[，,]?\s*(?:並|并)?廢棄\s*(\d+)\s*[張张]|"
    r"抽\s*(\d+)\s*[张張](?:卡片)?[，,]?\s*(?:並|并)?废弃\s*(\d+)\s*[张張]",
    re.I,
)
TRASH_LIFE_COST_RE = re.compile(
    r"(?:you may )?trash\s*1\s*card from the top of your Life cards\s*:|"
    r"可?[將将]\s*1\s*[張张]自己生命值區上面的卡片放置[到在]廢棄區\s*[：:]|"
    r"可?[将將]\s*1\s*[张張]自己生命值区上面的卡片放置[到在]废弃区\s*[：:]",
    re.I,
)
ADD_LIFE_RE = re.compile(
    r"add up to\s*(\d+)\s*cards? from the top of your deck to the top of your Life|"
    r"將最多\s*(\d+)\s*[張张]自己卡組上面的卡片加到生命值區上面|"
    r"将最多\s*(\d+)\s*[张張]自己卡组上面的卡片加到生命值区上面|"
    r"add\s*(\d+)\s*cards? from the top of your deck to the top of your Life|"
    r"將\s*(\d+)\s*[張张]自己卡組上面的卡片加到生命值區上面|"
    r"将\s*(\d+)\s*[张張]自己卡组上面的卡片加到生命值区上面",
    re.I,
)
PLAY_THIS_RE = re.compile(
    r"(?:\[Trigger\]|【觸發器】|【触发器】).{0,20}Play this card|"
    r"【觸發器】使這張卡片登場|【触发器】使这张卡片登场",
    re.I,
)
ACTIVE_DON_RE = re.compile(
    r"set up to\s*(\d+)\s*of your DON!! cards? as active|"
    r"將最多\s*(\d+)\s*[張张]自己的咚‼?卡置[為为]活動|"
    r"将最多\s*(\d+)\s*[张張]自己的咚‼?卡置为活动",
    re.I,
)
GAIN_DON_UPTO_RE = re.compile(
    r"add up to\s*(\d+)\s*DON!!|"
    r"獲得最多\s*(\d+)\s*[張张]咚|获得最多\s*(\d+)\s*[张張]咚",
    re.I,
)


def _nums(m: re.Match[str]) -> list[int]:
    return [int(g) for g in m.groups() if g]


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
        "draw_trash": 0,
        "life_add": 0,
        "life_dedupe": 0,
        "play_this": 0,
        "hand_to_deck": 0,
        "drop_rest_don": 0,
        "active_don": 0,
        "gain_don_opt": 0,
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

            # 1) Draw N + trash M (mandatory trash)
            m_dt = DRAW_TRASH_RE.search(chunk) or (
                DRAW_TRASH_RE.search(blob) if timing in {"on_play", "on_ko", "trigger", "when_attacking"} and not multi else None
            )
            # Prefer chunk; for trigger-only "Play this card" skip draw_trash from full blob
            if timing == "trigger" and PLAY_THIS_RE.search(chunk or blob):
                m_dt = DRAW_TRASH_RE.search(chunk) if chunk and not PLAY_THIS_RE.search(chunk) else None
            if m_dt:
                d, t = _nums(m_dt)[0], _nums(m_dt)[1]
                # Only apply when this timing chunk actually contains the draw+trash (or single timing card)
                if DRAW_TRASH_RE.search(chunk) or (not multi and DRAW_TRASH_RE.search(blob)):
                    has_draw = any(o.get("op") == "draw" for o in ops)
                    has_trash = any(o.get("op") == "trash_hand" for o in ops)
                    if not has_draw:
                        ops = [{"op": "draw", "count": d}] + ops
                        changed = True
                        stats["draw_trash"] += 1
                    if not has_trash:
                        ops.append({"op": "trash_hand", "count": t, "optional": False})
                        changed = True
                        stats["draw_trash"] += 1
                    for o in ops:
                        if o.get("op") == "draw" and int(o.get("count") or 0) != d:
                            o["count"] = d
                            stats["draw_trash"] += 1
                            changed = True
                        if o.get("op") == "trash_hand":
                            if int(o.get("count") or 0) != t or o.get("optional") is not False:
                                o["count"] = t
                                o["optional"] = False
                                stats["draw_trash"] += 1
                                changed = True

            # 2) trash_life cost → add_life
            if TRASH_LIFE_COST_RE.search(chunk):
                # Dedupe trash_life to one as_cost
                tl = [o for o in ops if o.get("op") == "trash_life"]
                if len(tl) > 1:
                    keep = dict(tl[0])
                    keep["as_cost"] = True
                    keep["optional"] = True
                    keep["owner"] = "self"
                    keep["position"] = keep.get("position") or "top"
                    ops = [o for o in ops if o.get("op") != "trash_life"]
                    ops = [keep] + ops
                    stats["life_dedupe"] += 1
                    changed = True
                elif len(tl) == 1:
                    if not tl[0].get("as_cost"):
                        tl[0]["as_cost"] = True
                        tl[0]["optional"] = True
                        stats["life_dedupe"] += 1
                        changed = True
                else:
                    ops = [
                        {
                            "op": "trash_life",
                            "count": 1,
                            "position": "top",
                            "owner": "self",
                            "optional": True,
                            "as_cost": True,
                        }
                    ] + ops
                    stats["life_dedupe"] += 1
                    changed = True

                m_add = ADD_LIFE_RE.search(chunk)
                if m_add and not any(o.get("op") == "add_life" for o in ops):
                    n = _nums(m_add)[0]
                    ops.append({"op": "add_life", "count": max(1, min(5, n)), "optional": True})
                    stats["life_add"] += 1
                    changed = True
                elif m_add:
                    n = _nums(m_add)[0]
                    for o in ops:
                        if o.get("op") == "add_life" and int(o.get("count") or 0) != n:
                            o["count"] = n
                            o["optional"] = True
                            stats["life_add"] += 1
                            changed = True

            # 3) Trigger Play this card
            if timing == "trigger" and PLAY_THIS_RE.search(chunk or blob):
                # Replace with clean self play
                want = {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": False,
                    "self_card": True,
                    "summary": "Play this card",
                }
                # Drop junk ops that belong to other timings (draw/trash/buff) when trigger is only play this
                trig_only = bool(
                    re.search(
                        r"^(?:\[Trigger\]|【觸發器】|【触发器】).{0,8}(?:Play this card|使這張卡片登場|使这张卡片登场)\.?$",
                        (chunk or "").strip(),
                        re.I,
                    )
                ) or (
                    PLAY_THIS_RE.search(chunk or "")
                    and not re.search(r"draw|trash|KO|力量|power|DON!!|rest |抽|廢棄|废弃", chunk or "", re.I)
                )
                if trig_only:
                    if ops != [want] and not (
                        len(ops) == 1
                        and ops[0].get("op") == "play_from_hand"
                        and ops[0].get("self_card")
                    ):
                        ops = [want]
                        stats["play_this"] += 1
                        changed = True
                else:
                    # Ensure self_card play exists; strip require_trigger name filters on play this
                    found = False
                    for o in ops:
                        if o.get("op") == "play_from_hand":
                            if not o.get("self_card"):
                                o["self_card"] = True
                                o.pop("require_trigger", None)
                                o.pop("name_contains", None)
                                o.pop("trait_contains", None)
                                o["optional"] = False
                                stats["play_this"] += 1
                                changed = True
                            found = True
                    if not found and PLAY_THIS_RE.search(chunk or ""):
                        ops.append(want)
                        stats["play_this"] += 1
                        changed = True

            # 4) hand_to_deck cost
            hd = _parse_hand_to_deck_ops(chunk)
            if hd and not any(o.get("op") == "hand_to_deck" for o in ops):
                if hd[0].get("as_cost") or re.search(
                    r"place this card and 1 card from your hand|這張卡片和1張自己的手牌|这张卡片和1张自己的手牌",
                    chunk,
                    re.I,
                ):
                    ops = hd + ops
                    stats["hand_to_deck"] += 1
                    changed = True

            # 5) active_don free — drop spurious rest_don cost
            m_ad = ACTIVE_DON_RE.search(chunk)
            if m_ad:
                n = _nums(m_ad)[0]
                if not re.search(r"rest\s*\d+\s*of your DON!! cards?\s*:|可[將将].{0,12}咚‼?卡置[為为]休息狀態\s*[：:]", chunk, re.I):
                    before = len(ops)
                    ops = [o for o in ops if o.get("op") != "rest_don"]
                    if len(ops) < before:
                        stats["drop_rest_don"] += 1
                        changed = True
                if not any(o.get("op") in {"active_don", "set_don"} for o in ops):
                    ops.append({"op": "active_don", "count": n, "optional": True})
                    stats["active_don"] += 1
                    changed = True
                else:
                    for o in ops:
                        if o.get("op") in {"active_don", "set_don"} and int(o.get("count") or 0) != n:
                            o["count"] = n
                            o["optional"] = True
                            stats["active_don"] += 1
                            changed = True

            # 6) gain_don optional for "up to"
            m_g = GAIN_DON_UPTO_RE.search(chunk)
            if m_g:
                n = _nums(m_g)[0]
                for o in ops:
                    if o.get("op") == "gain_don":
                        if o.get("optional") is not True or int(o.get("count") or 0) != n:
                            o["optional"] = True
                            o["count"] = n
                            stats["gain_don_opt"] += 1
                            changed = True

            a["ops"] = ops
            na = normalize_ability(a)
            if na:
                new_abs.append(na)

        # Dual timing [On Play]/[On K.O.] — mirror ops onto empty twin
        if re.search(r"\[On Play\]\s*/\s*\[On K\.?O\.?\]|【登場時】\s*/\s*【KO時】|【登场时】\s*/\s*【KO时】", blob, re.I):
            by_t = {str(a.get("timing")): a for a in new_abs}
            src = None
            for t in ("on_ko", "on_play"):
                a = by_t.get(t)
                if a and (a.get("ops") or []):
                    src = a
                    break
            if src:
                for t in ("on_play", "on_ko"):
                    a = by_t.get(t)
                    if a is not None and not (a.get("ops") or []):
                        a["ops"] = [dict(o) for o in (src.get("ops") or [])]
                        for k, v in src.items():
                            if str(k).startswith("require_") and a.get(k) is None:
                                a[k] = v
                        if src.get("require_leader_trait") and not a.get("require_leader_trait"):
                            a["require_leader_trait"] = src["require_leader_trait"]
                        changed = True
                        stats["draw_trash"] += 1
                # re-normalize
                new_abs = [normalize_ability(a) for a in new_abs]
                new_abs = [a for a in new_abs if a]

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
