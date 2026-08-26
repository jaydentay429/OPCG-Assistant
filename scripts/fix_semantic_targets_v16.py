#!/usr/bin/env python3
"""Fix wrong targets, drop extra set_active, inject hand gates / trait_any / hand_to_deck costs.

Writes library + overrides.
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
sys.path.insert(0, str(ROOT / "scripts"))

from battle.effect_library import get_card_entry, library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability, normalize_card_entry  # noqa: E402
from battle.effects import _parse_hand_to_deck_ops, effect_blob  # noqa: E402
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "targets_v16_fixed_ids.txt"

TRASH_SELF_RE = re.compile(
    r"(?:you may )?trash this (?:Character|card|Stage)\s*:|"
    r"可?[將将]這張(?:角色卡|卡片|舞台卡)放置到廢棄區\s*[：:]|"
    r"可?[将將]这张(?:角色卡|卡片|舞台卡)放置到废弃区\s*[：:]|"
    r"trash this Character",
    re.I,
)
RTH_SELF_RE = re.compile(
    r"(?:you may )?return this (?:Character|card) to (?:the )?owner'?s? hand|"
    r"可?[將将]這張(?:角色卡|卡片)放回持有者的手牌|"
    r"可?[将將]这张(?:角色卡|卡片)放回持有者的手牌|"
    r"add this card to your hand|將這張卡片加入手牌|将这张卡片加入手牌",
    re.I,
)
RTH_OWN_RE = re.compile(
    r"return 1 of your Characters to (?:the )?owner'?s? hand|"
    r"[將将]1[張张]自己的角色卡放回持有者的手牌|"
    r"[將将]最多1[張张]自己的角色卡放回",
    re.I,
)
KO_OPP_RE = re.compile(
    r"K\.?O\.?\s*up to\s*\d+\s*of your opponent'?s|"
    r"KO最多\s*\d+\s*[張张]對手|KO最多\s*\d+\s*[张張]对手",
    re.I,
)
ATTACH_OWN_RE = re.compile(
    r"[Gg]ive up to\s*\d+\s*(?:rested )?DON!!.{0,40}(?:Leader or|your Leader)|"
    r"附加最多\s*\d+\s*[張张].{0,20}咚.{0,30}(?:領航卡或|领航卡或|自己的領航|自己的领航)",
    re.I,
)
OPP_HAND_GATE_RE = re.compile(
    r"if your opponent has\s*(\d+)\s*or more cards? in (?:their|the) hand|"
    r"若對手的手牌有\s*(\d+)\s*[張张]以上|若对手的手牌有\s*(\d+)\s*[张張]以上",
    re.I,
)
TRAIT_OR_RE = re.compile(
    r"\{([^}]+)\}\s*or\s*\{([^}]+)\}\s*type|"
    r"擁有《([^》]+)》或《([^》]+)》特徵|拥有《([^》]+)》或《([^》]+)》特征",
    re.I,
)
SET_ACTIVE_OWN_RE = re.compile(
    r"set (?:up to\s*\d+\s*of )?your.{0,40}as active|set this Character as active|"
    r"置[為为]活動狀態",
    re.I,
)
SKIP_UNTAP_RE = re.compile(
    r"will not become active|無法[為为]活動|无法为活动|skip.?untap|重整階段無法",
    re.I,
)


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
        "trash_self": 0,
        "rth_self": 0,
        "ko_opp": 0,
        "drop_set_active": 0,
        "attach_own": 0,
        "opp_hand_gate": 0,
        "trait_or": 0,
        "hand_to_deck": 0,
        "drop_leader_gate": 0,
        "drop_extra_rth": 0,
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

            # 1) trash this Character → self
            if TRASH_SELF_RE.search(chunk):
                for o in ops:
                    if o.get("op") == "trash" and o.get("target_kind") != "self":
                        o["target_kind"] = "self"
                        if re.search(r":|：", chunk):
                            o["as_cost"] = True
                            o["optional"] = True
                        stats["trash_self"] += 1
                        changed = True

            # 2) return_to_hand self / own
            if RTH_SELF_RE.search(chunk):
                for o in ops:
                    if o.get("op") == "return_to_hand" and "opponent" in str(o.get("target_kind") or ""):
                        o["target_kind"] = "self"
                        stats["rth_self"] += 1
                        changed = True
            elif RTH_OWN_RE.search(chunk):
                for o in ops:
                    if o.get("op") == "return_to_hand" and "opponent" in str(o.get("target_kind") or ""):
                        o["target_kind"] = "own_character"
                        stats["rth_self"] += 1
                        changed = True
            # Drop extra RTH when text is only add_from_trash
            if (
                any(o.get("op") == "return_to_hand" for o in ops)
                and re.search(r"from your trash to your hand|廢棄區.{0,20}加入手牌|废弃区.{0,20}加入手牌", chunk, re.I)
                and not re.search(r"return .{0,30}hand|放回手牌", chunk, re.I)
            ):
                before = len(ops)
                ops = [o for o in ops if o.get("op") != "return_to_hand"]
                if len(ops) < before:
                    stats["drop_extra_rth"] += 1
                    changed = True

            # 3) KO opponent
            if KO_OPP_RE.search(chunk):
                for o in ops:
                    if o.get("op") == "ko" and "own" in str(o.get("target_kind") or ""):
                        o["target_kind"] = "opponent_character"
                        stats["ko_opp"] += 1
                        changed = True

            # 4) Drop set_character_active when effect is only skip_untap
            if any(o.get("op") == "skip_untap" for o in ops) and any(o.get("op") == "set_character_active" for o in ops):
                if SKIP_UNTAP_RE.search(chunk) and not (
                    SET_ACTIVE_OWN_RE.search(chunk)
                    and re.search(r"your |自己|這張角色|这张角色|this Character", chunk, re.I)
                    and not SKIP_UNTAP_RE.search(chunk)
                ):
                    # If chunk is skip-untap only (no own set active), drop set_character_active
                    if not re.search(
                        r"set (?:up to \d+ of )?your (?:DON|Character)|將最多.{0,20}自己.{0,20}置[為为]活動",
                        chunk,
                        re.I,
                    ):
                        before = len(ops)
                        ops = [o for o in ops if o.get("op") != "set_character_active"]
                        if len(ops) < before:
                            stats["drop_set_active"] += 1
                            changed = True

            # 5) attach_don own leader/character
            if ATTACH_OWN_RE.search(chunk):
                for o in ops:
                    if o.get("op") == "attach_don":
                        tk = str(o.get("target_kind") or "")
                        if tk in {"self", "opponent_character", ""} or "opponent" in tk:
                            o["target_kind"] = "own_leader_or_character"
                            stats["attach_own"] += 1
                            changed = True

            # 6) opp hand gate
            m_hand = OPP_HAND_GATE_RE.search(chunk)
            if m_hand:
                n = int(next(g for g in m_hand.groups() if g))
                if int(a.get("require_opp_hand_gte") or 0) != n:
                    a["require_opp_hand_gte"] = n
                    stats["opp_hand_gate"] += 1
                    changed = True

            # 7) trait OR on play_from_hand / search
            m_tr = TRAIT_OR_RE.search(chunk)
            if m_tr:
                traits = [g.strip() for g in m_tr.groups() if g]
                if len(traits) >= 2:
                    for o in ops:
                        if o.get("op") in {"play_from_hand", "search_deck", "add_from_trash"}:
                            cur = o.get("trait_any")
                            if not cur:
                                # replace single trait_contains
                                o["trait_any"] = traits[:4]
                                o.pop("trait_contains", None)
                                stats["trait_or"] += 1
                                changed = True
                            elif isinstance(cur, list) and set(traits) - set(cur):
                                o["trait_any"] = list(dict.fromkeys(list(cur) + traits))[:4]
                                stats["trait_or"] += 1
                                changed = True

            # 8) hand_to_deck cost (this card + 1 hand)
            hd = _parse_hand_to_deck_ops(chunk)
            if hd and not any(o.get("op") == "hand_to_deck" for o in ops):
                if hd[0].get("as_cost") or re.search(r"place this card and 1 card from your hand|這張卡片和1張自己的手牌|这张卡片和1张自己的手牌", chunk, re.I):
                    ops = hd + ops
                    stats["hand_to_deck"] += 1
                    changed = True

            # 9) Drop leader name gate from timings that don't mention Leader condition
            if a.get("require_leader_name") and not re.search(
                r"if your Leader is|若自己的領航卡是|若自己的领航卡是", chunk, re.I
            ):
                # Keep on your_turn continuous if blob has the condition for that effect
                if timing == "on_play" or (
                    timing == "your_turn"
                    and not re.search(r"if your Leader is|若自己的領航卡是", chunk, re.I)
                ):
                    a.pop("require_leader_name", None)
                    stats["drop_leader_gate"] += 1
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
