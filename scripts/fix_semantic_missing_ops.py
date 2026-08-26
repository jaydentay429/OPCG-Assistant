#!/usr/bin/env python3
"""Inject / repair high-yield missing ops on semantic-issue cards.

Fixes:
  - DON!!−N cost → return_don (as_cost); rest_don mis-tagged as return when paper returns DON
  - missing buff / debuff from ±N power text
  - buff amount 0
  - missing KO / play_from_hand / add_life / grant blocker
  - draw 2 + trash 1

Usage:
  .venv/bin/python scripts/fix_semantic_missing_ops.py --dry-run
  .venv/bin/python scripts/fix_semantic_missing_ops.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability, normalize_card_entry  # noqa: E402
from battle.effects import (  # noqa: E402
    _enrich_ops_with_target_filters,
    _parse_ko_op,
    _parse_play_from_zone,
    effect_blob,
)

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "missing_ops_fixed_ids.txt"

DON_RETURN_RE = re.compile(
    r"DON!!\s*[−\-－]\s*(\d+)|咚‼?\s*[−\-－]\s*(\d+)|"
    r"return the specified number of DON!! cards from your field to your DON!! deck",
    re.I,
)
DON_REST_RE = re.compile(
    r"(?:you may )?rest\s*(\d+)\s*of your DON!!|可[將将]\s*(\d+)\s*[張张]?自己的咚.{0,12}置為休息|"
    r"可[將将]\s*(\d+)\s*[张張]?自己的咚.{0,12}置为休息",
    re.I,
)
BUFF_POS_RE = re.compile(
    r"(?:gains?|gain)\s*\+(\d{3,5})\s*power|力量值\+(\d{3,5})|(?:\+|＋)(\d{3,5})\s*(?:power|力量)",
    re.I,
)
BUFF_NEG_RE = re.compile(
    r"(?:give|gains?|gain).{0,40}[−\-－]\s*(\d{3,5})\s*power|"
    r"力量值\s*[−\-－]\s*(\d{3,5})|[−\-－]\s*(\d{3,5})\s*(?:power|力量)",
    re.I,
)
DRAW_TRASH_RE = re.compile(
    r"(?:draw\s*2.{0,80}trash\s*1|抽2.{0,60}(?:廢棄|废弃)\s*1)",
    re.I,
)
ADD_LIFE_RE = re.compile(
    r"add up to 1 card from the top of your deck to the top of your Life|"
    r"將最多1[張张]自己卡組上面的卡片加到生命值區上面|"
    r"将最多1[张張]自己卡组上面的卡片加到生命值区上面",
    re.I,
)
GRANT_BLOCKER_RE = re.compile(
    r"(?:gains?|gain|gets?|獲得|获得|擁有|拥有)\s*(?:\[Blocker\]|【阻擋者】|【阻挡者】)|"
    r"(?:\[Blocker\]|【阻擋者】|【阻挡者】).{0,12}(?:during this turn|在這個回合|在这个回合)",
    re.I,
)


def _timing_chunk(blob: str, timing: str) -> str:
    t = (timing or "").lower()
    patterns = {
        "on_play": r"(?:\[on play\]|【登場時】|【登场时】)",
        "when_attacking": r"(?:\[when attacking\]|【攻擊時】|【攻击时】)",
        "activate_main": r"(?:\[activate(?:\s*:\s*main)?\]|【啟動主要】|【启动主要】)",
        "trigger": r"(?:\[trigger\]|【觸發器】|【触发器】)",
        "on_ko": r"(?:\[on\s*k\.?o\.?\]|【KO時】|【KO时】)",
        "main_start": r"(?:\[main\]|【主要】)",
        "counter_event": r"(?:\[counter\]|【反擊】|【反击】)",
        "on_opponent_attack": r"(?:\[on your opponent'?s attack\]|【對方的?攻擊時】|【对方的?攻击时】)",
        "end_of_your_turn": r"(?:\[end of your turn\]|【我方的?回合結束時】|【我方的?回合结束时】)",
        "your_turn": r"(?:\[your turn\]|【我方回合中】)",
    }
    pat = patterns.get(t)
    if not pat:
        return blob
    m = re.search(pat, blob, re.I)
    if not m:
        return blob
    rest = blob[m.end() :]
    stop = re.search(
        r"(?=\[(?:on play|when attacking|activate|on\s*k\.?o\.?|trigger|counter|main|don!!|your turn|end of)|【)",
        rest,
        re.I,
    )
    end = m.end() + (stop.start() if stop else min(len(rest), 520))
    return blob[m.start() : end]


def _scope(ability: dict, blob: str, multi: bool) -> str:
    summary = str(ability.get("summary") or "").strip()
    chunk = _timing_chunk(blob, str(ability.get("timing") or ""))
    if len(summary) >= 24:
        return summary
    if multi:
        return chunk or blob
    return chunk if len(chunk) > 40 else blob


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
    overrides = ovr_raw.get("cards") if isinstance(ovr_raw.get("cards"), dict) else ovr_raw
    if not isinstance(overrides, dict):
        overrides = {}

    stats = {
        "return_don": 0,
        "rest_to_return": 0,
        "buff_inject": 0,
        "debuff_inject": 0,
        "buff_amt": 0,
        "ko_inject": 0,
        "play_inject": 0,
        "add_life": 0,
        "grant_blocker": 0,
        "trash_hand": 0,
        "cards_touched": 0,
    }
    touched: list[str] = []

    for cid, rev in (semantic.get("cards") or {}).items():
        if rev.get("verdict") != "issue":
            continue
        entry = cards.get(cid)
        if not isinstance(entry, dict):
            continue
        abilities = [dict(a) for a in (entry.get("abilities") or []) if isinstance(a, dict)]
        if not abilities:
            continue
        blob = effect_blob(catalog.get(cid) or {})
        multi = len(abilities) > 1
        changed = False
        new_abs: list[dict] = []

        for ability in abilities:
            scope = _scope(ability, blob, multi)
            ops = [dict(o) for o in (ability.get("ops") or [])]

            # rest_don → return_don when paper returns DON!!−N
            if DON_RETURN_RE.search(scope) and not DON_REST_RE.search(scope):
                for o in ops:
                    if o.get("op") == "rest_don":
                        o["op"] = "return_don"
                        o["as_cost"] = True
                        o["optional"] = True
                        stats["rest_to_return"] += 1
                        changed = True

            # inject return_don cost
            m_don = DON_RETURN_RE.search(scope)
            if m_don and not DON_REST_RE.search(scope):
                n = 1
                for g in m_don.groups():
                    if g and str(g).isdigit():
                        n = int(g)
                        break
                if not any(o.get("op") == "return_don" for o in ops):
                    # activate_main may use cost_don instead
                    if ability.get("timing") == "activate_main" and int(ability.get("cost_don") or 0) >= n:
                        pass
                    else:
                        ops = [
                            {
                                "op": "return_don",
                                "count": n,
                                "as_cost": True,
                                "optional": True,
                            },
                            *ops,
                        ]
                        stats["return_don"] += 1
                        changed = True
                if ability.get("timing") == "activate_main" and not ability.get("cost_don"):
                    # keep cost_don in sync for activate legality helpers
                    ability["cost_don"] = n

            # buff amount 0
            m_pos = BUFF_POS_RE.search(scope) or (None if multi else BUFF_POS_RE.search(blob))
            m_neg = BUFF_NEG_RE.search(scope)
            # avoid treating DON!!−N as debuff
            if m_neg and re.search(r"DON!!|咚‼", m_neg.group(0)):
                m_neg = None
            for o in ops:
                if o.get("op") not in {"buff", "buff_self", "buff_all_own"}:
                    continue
                if int(o.get("amount") or 0) != 0:
                    continue
                if m_neg and (
                    str(o.get("target_kind") or "").startswith("opponent")
                    or re.search(r"opponent|對手|对手", scope, re.I)
                ):
                    amt = -int(next(g for g in m_neg.groups() if g))
                    o["amount"] = amt
                    stats["buff_amt"] += 1
                    changed = True
                elif m_pos:
                    o["amount"] = int(next(g for g in m_pos.groups() if g))
                    stats["buff_amt"] += 1
                    changed = True

            # inject missing positive buff
            if m_pos and not any(o.get("op") in {"buff", "buff_self", "buff_all_own"} for o in ops):
                # Require the +N to appear in this ability's timing chunk (avoid cross-timing leaks).
                chunk = _timing_chunk(blob, str(ability.get("timing") or ""))
                if multi and chunk and not BUFF_POS_RE.search(chunk) and not BUFF_POS_RE.search(str(ability.get("summary") or "")):
                    pass
                else:
                    amt = int(next(g for g in m_pos.groups() if g))
                    if re.search(r"all of your|自己的角色卡全数|自己的角色卡全部|所有自己", scope, re.I):
                        ops.append({"op": "buff_all_own", "amount": amt})
                    elif re.search(r"this (?:Leader|Character)|這張|这张|自身", scope, re.I) and not re.search(
                        r"up to 1 of your|最多1[張张]自己", scope, re.I
                    ):
                        ops.append({"op": "buff_self", "amount": amt})
                    else:
                        tk = "own_leader_or_character"
                        if re.search(r"Leader or Character|領航卡或角色|领航卡或角色", scope, re.I):
                            tk = "own_leader_or_character"
                        elif re.search(r"opponent|對手|对手", scope, re.I) and re.search(r"gains?\s*\+", scope, re.I):
                            tk = "opponent_character"
                        ops.append({"op": "buff", "amount": amt, "target_kind": tk, "optional": True})
                    stats["buff_inject"] += 1
                    changed = True

            # inject missing debuff (opponent −N)
            if (
                m_neg
                and re.search(r"opponent|對手|对手", scope, re.I)
                and not any(o.get("op") in {"buff", "buff_self"} and int(o.get("amount") or 0) < 0 for o in ops)
            ):
                # skip leader self-pay costs like "give your active Leader −5000"
                if re.search(r"your active Leader|自己的活動狀態領航|自己的活动状态领航|自己的領航卡力量值\s*[−\-－]", scope, re.I):
                    pass
                else:
                    amt = -int(next(g for g in m_neg.groups() if g))
                    ops.append(
                        {
                            "op": "buff",
                            "amount": amt,
                            "target_kind": "opponent_character",
                            "optional": True,
                        }
                    )
                    stats["debuff_inject"] += 1
                    changed = True

            # missing KO
            if re.search(r"K\.?O\.?\s*(up to )?1|KO最多1|KO\s*最多\s*1", scope, re.I):
                if not any(o.get("op") in {"ko", "ko_lowest_opponent"} for o in ops):
                    ko = _parse_ko_op(scope) or _parse_ko_op(blob)
                    if ko:
                        ops.append(ko)
                        stats["ko_inject"] += 1
                        changed = True

            # missing play_from_hand
            if re.search(
                r"play up to 1|從(?:自己的)?(?:手牌|廢棄區|废弃区).{0,48}登場|从(?:自己的)?(?:手牌|废弃区|廢棄區).{0,48}登场",
                scope,
                re.I,
            ):
                if not any(o.get("op") == "play_from_hand" for o in ops):
                    play = _parse_play_from_zone(scope) or _parse_play_from_zone(blob)
                    if play:
                        ops.append(play)
                        stats["play_inject"] += 1
                        changed = True
                    elif re.search(r"from your trash|廢棄區|废弃区", scope, re.I):
                        ops.append({"op": "play_from_hand", "count": 1, "from_zone": "trash", "optional": True})
                        stats["play_inject"] += 1
                        changed = True

            # trash zone on existing play
            for o in ops:
                if o.get("op") != "play_from_hand":
                    continue
                if str(o.get("from_zone") or "hand") == "trash":
                    continue
                if re.search(r"from your trash|從自己的廢棄區|从自己的废弃区", scope, re.I):
                    if re.search(r"hand or trash|手牌或廢棄|手牌或废弃", scope, re.I):
                        o["from_zone"] = "hand_or_trash"
                    else:
                        o["from_zone"] = "trash"
                    changed = True

            # add_life
            if ADD_LIFE_RE.search(scope) and not any(o.get("op") == "add_life" for o in ops):
                ops.append({"op": "add_life", "count": 1})
                stats["add_life"] += 1
                changed = True

            # grant blocker
            if GRANT_BLOCKER_RE.search(scope) and not any(
                o.get("op") == "grant_keyword" and "blocker" in str(o.get("keyword") or "").lower() for o in ops
            ):
                ops.append(
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "optional": False,
                    }
                )
                stats["grant_blocker"] += 1
                changed = True

            # draw2 trash1
            if DRAW_TRASH_RE.search(scope):
                if any(o.get("op") == "draw" for o in ops) and not any(o.get("op") == "trash_hand" for o in ops):
                    rebuilt = []
                    done = False
                    for o in ops:
                        rebuilt.append(o)
                        if not done and o.get("op") == "draw" and int(o.get("count") or 1) >= 2:
                            rebuilt.append({"op": "trash_hand", "count": 1, "optional": True})
                            done = True
                    if done:
                        ops = rebuilt
                        stats["trash_hand"] += 1
                        changed = True

            ops = _enrich_ops_with_target_filters(ops, scope)
            # Dedupe identical play_from_hand rows
            seen_play: set[tuple] = set()
            deduped: list[dict] = []
            for o in ops:
                if o.get("op") == "play_from_hand":
                    key = (
                        o.get("from_zone"),
                        o.get("cost_eq"),
                        o.get("cost_lte"),
                        o.get("trait_contains"),
                        o.get("name_contains"),
                        o.get("count"),
                    )
                    if key in seen_play:
                        continue
                    seen_play.add(key)
                deduped.append(o)
            ops = deduped
            ability["ops"] = ops
            na = normalize_ability(ability)
            if na:
                new_abs.append(na)

        if not changed:
            continue
        fixed = normalize_card_entry(cid, {"version": 1, "abilities": new_abs})
        cards[cid] = fixed
        # Override layer wins per timing when runnable — keep it in sync or our fix is masked.
        overrides[cid] = fixed
        stats["cards_touched"] += 1
        touched.append(cid)

    print(json.dumps(stats, ensure_ascii=False), flush=True)
    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    OUT_IDS.write_text("\n".join(touched) + ("\n" if touched else ""), encoding="utf-8")
    print(f"Wrote ids {OUT_IDS} ({len(touched)})", flush=True)
    if args.dry_run:
        return 0
    payload = {
        "version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cards": cards,
    }
    tmp = lib_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(lib_path)
    ovr_payload = {
        "version": int(ovr_raw.get("version") or 1),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cards": overrides,
    }
    # Preserve top-level keys if present
    for k, v in ovr_raw.items():
        if k not in {"cards", "generated_at"}:
            ovr_payload[k] = v
    ovr_payload["cards"] = overrides
    tmp_o = ovr_path.with_suffix(".json.tmp")
    tmp_o.write_text(json.dumps(ovr_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp_o.replace(ovr_path)
    reload_effect_library(force=True)
    print(f"Wrote {lib_path}", flush=True)
    print(f"Wrote {ovr_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
