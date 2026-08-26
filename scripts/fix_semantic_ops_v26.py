#!/usr/bin/env python3
"""Deterministic semantic fixes v26: gates bleed, allow_attack, filters, KO-return-DON.

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
    _parse_allow_attack_active_ops,
    _parse_replace_leave_ops,
    effect_blob,
    parse_trigger_ops,
)
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

OUT_IDS = ROOT / "meta" / "logs" / "ops_v26_fixed_ids.txt"

OPP_RTH_ACTIVE_RE = re.compile(
    r"(?:your )?opponent returns?\s*1 of their active Characters? to the owner'?s? hand|"
    r"對手將1[張张]自身活動狀態的角色卡放回持有者的手牌|"
    r"对手将1[张張]自身活动状态的角色卡放回持有者的手牌",
    re.I,
)
NEG_BUFF_RE = re.compile(
    r"(?:give|gains?).{0,60}opponent'?s? Characters?.{0,40}[−\-－]\s*(\d{3,5})\s*power|"
    r"最多\s*(\d+)\s*[張张]對手的角色卡.{0,24}力量(?:值)?\s*[−\-－]\s*(\d{3,5})|"
    r"對手的角色卡.{0,24}力量(?:值)?\s*[−\-－]\s*(\d{3,5})",
    re.I,
)
POWER_LTE_RE = re.compile(
    r"(?:with )?(?:a )?power of\s*(\d+)\s*or less|力量(?:值)?\s*(\d+)\s*以下",
    re.I,
)
DRAW_PER_TRAIT_RE = re.compile(
    r"Draw a card for each of your \{([^}]+)\} type Characters|"
    r"每有1[張张]自己擁有《([^》]+)》特徵的角色卡，抽1[張张]|"
    r"每有1[张張]自己拥有《([^》]+)》特征的角色卡，抽1[张張]",
    re.I,
)
ACTIVE_LEADER_RE = re.compile(
    r"set your \{([^}]+)\} type Leader as active|"
    r"將自己擁有《([^》]+)》特徵的領航卡置為活動|"
    r"将自己拥有《([^》]+)》特征的领航卡置为活动",
    re.I,
)
ACTIVE_CHARS_LEADER_RE = re.compile(
    r"set up to\s*(\d+)\s+of your \{([^}]+)\} type Characters and your Leader as active|"
    r"最多\s*(\d+)\s*[張张]自己擁有《([^》]+)》特徵的角色卡和領航卡置為活動|"
    r"最多\s*(\d+)\s*[张張]自己拥有《([^》]+)》特征的角色卡和领航卡置为活动",
    re.I,
)
PLAY_SELF_TRASH_HAND_RE = re.compile(
    r"(?:you may )?trash 1 card from your hand\s*:\s*Play this card|"
    r"可以廢棄1[張张]自己的手牌\s*[：:]\s*使這張卡片登場|"
    r"可以废弃1[张張]自己的手牌\s*[：:]\s*使这张卡片登场",
    re.I,
)
REST_OPP_DON_OR_CHAR_RE = re.compile(
    r"rest up to\s*1 of your opponent'?s? DON!! cards or Characters|"
    r"將最多1[張张]對手.{0,20}咚‼?卡或角色卡置為休息|"
    r"将最多1[张張]对手.{0,20}咚‼?卡或角色卡置为休息",
    re.I,
)


def _on_play_chunk(blob: str) -> str:
    m = re.search(
        r"\[On Play\](.*?)(?=\[(?:On K\.?O\.?|When Attacking|Activate|Trigger|Counter|Your Turn|Opponent|Main|DON!!)|"
        r"【(?:登場時|KO時|攻擊時|啟動|觸發|反擊|我方|對方|主要|咚)|$)",
        blob,
        re.I | re.S,
    )
    if m:
        return m.group(1)
    m = re.search(
        r"【登場時】(.*?)(?=【(?:KO時|攻擊時|啟動|觸發|反擊|我方|對方|主要|咚)|$)",
        blob,
        re.I | re.S,
    )
    return m.group(1) if m else ""


def fix_card(cid: str, info: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any] | None:
    blob = effect_blob(info)
    abs_in = [dict(a) for a in (entry.get("abilities") or []) if isinstance(a, dict)]
    if not abs_in:
        return None
    changed = False
    new_abs: list[dict[str, Any]] = []

    # Precompute continuous allow_attack / replace_leave from full blob
    allow_ops = _parse_allow_attack_active_ops(blob)
    leave_ops = _parse_replace_leave_ops(blob)

    for a in abs_in:
        t = str(a.get("timing") or "")
        chunk = _trim_cross_timing(_timing_chunk(blob, t), t) or ""
        ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

        # 1) Bleed: on_play got continuous leader gate / buff_self from your_turn aura
        if t == "on_play":
            on_chunk = _on_play_chunk(blob)
            if on_chunk and not re.search(r"Leader|領航|领航", on_chunk, re.I):
                if a.get("require_leader_trait") or a.get("require_leader_name"):
                    # Keep if ONLY on_play mentions it elsewhere — strip when your_turn holds the aura
                    if any(
                        x.get("timing") == "your_turn"
                        and (x.get("require_leader_trait") or x.get("require_leader_name"))
                        for x in abs_in
                    ):
                        a.pop("require_leader_trait", None)
                        a.pop("require_leader_name", None)
                        changed = True
                    elif re.search(r"\[On Play\].{0,120}Draw|【登場時】.{0,40}抽", blob, re.I) and re.search(
                        r"this Character gains \+|這張角色卡.{0,20}力量|这张角色卡.{0,20}力量", blob, re.I
                    ):
                        # Continuous power is not on_play
                        a.pop("require_leader_trait", None)
                        a.pop("require_leader_name", None)
                        changed = True
                # Strip buff_self that belongs to continuous clause
                if any(o.get("op") == "buff_self" for o in ops) and re.search(
                    r"gains \+\d+ power for every|每有\d+[張张].{0,20}力量", blob, re.I
                ):
                    if not re.search(r"\[On Play\].{0,80}gains|【登場時】.{0,40}力量", blob, re.I):
                        ops = [o for o in ops if o.get("op") != "buff_self"]
                        changed = True

        # 2) Soft leader gate after cost (Perona): counter should not have leader name
        if t == "counter_event" and a.get("require_leader_name"):
            if not re.search(r"Leader is|領航卡是|领航卡是", chunk, re.I):
                a.pop("require_leader_name", None)
                changed = True

        # 3) Opponent return active character to hand
        if OPP_RTH_ACTIVE_RE.search(chunk) or (t == "counter_event" and OPP_RTH_ACTIVE_RE.search(blob)):
            if not any(o.get("op") == "return_to_hand" for o in ops):
                ops.append(
                    {
                        "op": "return_to_hand",
                        "count": 1,
                        "target_kind": "opponent_character_active",
                        "optional": False,
                        "summary": "Opponent returns 1 active Character to hand",
                    }
                )
                changed = True

        # 4) Fix play_from_hand from_zone when paper says hand
        for o in ops:
            if o.get("op") == "play_from_hand" and o.get("from_zone") == "trash":
                if re.search(r"from your hand|自己手牌中|從手牌", chunk, re.I) and not re.search(
                    r"hand or trash|手牌或廢棄|手牌或废弃", chunk, re.I
                ):
                    o["from_zone"] = "hand"
                    changed = True

        # 5) Negative buff
        m = NEG_BUFF_RE.search(chunk)
        if m and not any(o.get("op") == "buff" and int(o.get("amount") or 0) < 0 for o in ops):
            nums = [int(g) for g in m.groups() if g and str(g).isdigit()]
            amt = -abs(nums[-1]) if nums else -2000
            cnt = nums[0] if len(nums) >= 2 and nums[0] <= 5 else 1
            ops.append(
                {
                    "op": "buff",
                    "amount": amt,
                    "count": cnt,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "turn",
                }
            )
            changed = True

        # 6) power_lte on targeted ops
        m = POWER_LTE_RE.search(chunk)
        if m:
            pwr = int(next(g for g in m.groups() if g))
            for o in ops:
                if o.get("op") in {
                    "deny_attack",
                    "ko",
                    "return_to_hand",
                    "rest_opponent_character",
                    "play_from_hand",
                    "trash",
                }:
                    if o.get("power_lte") is None:
                        o["power_lte"] = pwr
                        changed = True
            # trigger play with power + require_trigger
            if t == "trigger" and any(o.get("op") == "play_from_hand" for o in ops):
                for o in ops:
                    if o.get("op") == "play_from_hand":
                        if o.get("power_lte") is None:
                            o["power_lte"] = pwr
                            changed = True
                        if re.search(r"\[Trigger\]|持有【觸發器】|持有【触发器】", chunk + blob, re.I):
                            if not o.get("require_trigger"):
                                o["require_trigger"] = True
                                changed = True

        # 7) Draw per trait + trash equal
        m = DRAW_PER_TRAIT_RE.search(chunk) or DRAW_PER_TRAIT_RE.search(blob)
        if m and t == "on_play":
            trait = next(g for g in m.groups() if g)
            # replace flat draw
            ops = [o for o in ops if o.get("op") not in {"draw", "trash_hand"}]
            ops.append(
                {
                    "op": "draw",
                    "count": 1,
                    "per_own_trait": trait,
                    "then_trash_equal": True,
                    "summary": f"Draw 1 per {{{trait}}}, then trash equal",
                }
            )
            changed = True

        # 8) set leader active
        m = ACTIVE_LEADER_RE.search(chunk)
        if m:
            trait = next(g for g in m.groups() if g)
            for o in ops:
                if o.get("op") == "set_character_active":
                    o["target_kind"] = "leader"
                    o["trait_contains"] = trait
                    changed = True
            if not any(o.get("op") == "set_character_active" for o in ops):
                ops.append(
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "leader",
                        "trait_contains": trait,
                        "optional": False,
                    }
                )
                changed = True

        # 9) chars + leader active
        m = ACTIVE_CHARS_LEADER_RE.search(chunk)
        if m:
            gs = [g for g in m.groups() if g]
            n = int(gs[0])
            trait = gs[1]
            ops = [o for o in ops if o.get("op") != "set_character_active"]
            ops.append(
                {
                    "op": "set_character_active",
                    "count": n,
                    "target_kind": "own_character",
                    "trait_contains": trait,
                    "include_leader": True,
                    "optional": True,
                }
            )
            changed = True

        # 10) Trigger play this after trash hand cost
        if t == "trigger" and PLAY_SELF_TRASH_HAND_RE.search(chunk or blob):
            if not any(o.get("op") == "play_from_hand" and o.get("self_card") for o in ops):
                if not any(o.get("op") == "trash_hand" for o in ops):
                    ops.insert(
                        0,
                        {
                            "op": "trash_hand",
                            "count": 1,
                            "optional": True,
                            "as_cost": True,
                            "owner": "self",
                        },
                    )
                ops.append(
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "from_zone": "hand",
                        "self_card": True,
                        "optional": False,
                        "summary": "Play this card",
                    }
                )
                changed = True

        # 11) Drop spurious set_character_active from activate when paper is active_don + rest opp
        if t == "activate_main" and REST_OPP_DON_OR_CHAR_RE.search(chunk):
            if any(o.get("op") == "set_character_active" for o in ops) and not re.search(
                r"set .{0,40}as active|置為活動|置为活动", chunk, re.I
            ):
                ops = [o for o in ops if o.get("op") != "set_character_active"]
                changed = True
            # Prefer rest_don target optionally — keep rest_opponent_character; add note via rest_don on opp if missing
            # Engine may not rest opp DON via rest_opponent_character — leave as-is for now.

        # 12) End of turn FILM trait on set_character_active
        if t == "end_of_your_turn":
            m_film = re.search(r"\{([^}]+)\} type Characters? as active|擁有《([^》]+)》特徵的角色卡置為活動", chunk, re.I)
            if m_film:
                trait = next(g for g in m_film.groups() if g)
                for o in ops:
                    if o.get("op") == "set_character_active" and not o.get("trait_contains"):
                        o["trait_contains"] = trait
                        changed = True

        # 13) Opponent's Turn On K.O. — mark require via timing note on ability
        if t == "on_ko" and re.search(r"\[Opponent'?s? Turn\].{0,40}\[On K\.?O\.?\]|【對方回合中】【KO時】|【对方回合中】【KO时】", blob, re.I):
            if not a.get("require_opponent_turn"):
                a["require_opponent_turn"] = True
                changed = True
            # fix exclude self name / hand_or_trash already often present
            for o in ops:
                if o.get("op") == "play_from_hand" and o.get("name_contains") and re.search(
                    r"other than \[([^\]]+)\]|除了「([^」]+)」以外", chunk or blob, re.I
                ):
                    m_ex = re.search(r"other than \[([^\]]+)\]|除了「([^」]+)」以外", chunk or blob, re.I)
                    if m_ex:
                        excl = next(g for g in m_ex.groups() if g)
                        # name_contains should not be the excluded name
                        if o.get("name_contains") == excl:
                            o.pop("name_contains", None)
                            o["exclude_name"] = excl
                            changed = True
                if o.get("op") == "grant_cost" and t == "on_ko":
                    # grant_cost is continuous — drop from on_ko
                    ops = [x for x in ops if x.get("op") != "grant_cost"]
                    changed = True
                    break

        # 14) Inject allow_attack on your_turn / on_play carrier
        if allow_ops and t in {"on_play", "your_turn"}:
            if t == "your_turn" or (
                t == "on_play"
                and re.search(r"can attack Characters on the turn|登場的回合即可攻擊|登场的回合即可攻击", blob, re.I)
            ):
                if not any(o.get("op") == "allow_attack_active" for o in ops):
                    # Prefer separate your_turn ability — if only on_play exists, attach there for digest
                    if t == "on_play" and not any(x.get("timing") == "your_turn" for x in abs_in):
                        ops = list(allow_ops) + ops
                        # opp count gate on ability
                        gte = allow_ops[0].get("require_opp_chars_count_gte")
                        if gte:
                            a["require_opp_chars_count_gte"] = gte
                        changed = True

        a["ops"] = [sanitize_op(o) for o in ops if sanitize_op(o)]
        na = normalize_ability(a)
        if na:
            new_abs.append(na)

    # Ensure your_turn allow_attack ability exists
    if allow_ops and not any(
        o.get("op") == "allow_attack_active" for a in new_abs for o in (a.get("ops") or [])
    ):
        ab: dict[str, Any] = {
            "timing": "your_turn",
            "summary": allow_ops[0].get("summary") or "Can attack Characters when played",
            "ops": allow_ops,
            "status": "compiled",
            "confidence": 0.85,
        }
        if allow_ops[0].get("require_opp_chars_count_gte"):
            ab["require_opp_chars_count_gte"] = allow_ops[0]["require_opp_chars_count_gte"]
        new_abs.insert(0, normalize_ability(ab))
        changed = True

    # Ensure replace_leave for KO-return-DON
    if leave_ops and not any(o.get("op") == "replace_leave" for a in new_abs for o in (a.get("ops") or [])):
        new_abs.append(
            normalize_ability(
                {
                    "timing": "your_turn",
                    "summary": leave_ops[0].get("summary") or "replace_leave",
                    "ops": leave_ops,
                    "status": "compiled",
                    "confidence": 0.9,
                }
            )
        )
        changed = True

    # Continuous grant_cost for +cost if leader trait (EB03-042 style)
    if re.search(
        r"this Character gains?\s*\+\s*\d+\s*cost|這張角色卡的費用\s*\+|这张角色卡的费用\s*\+",
        blob,
        re.I,
    ) and not any(o.get("op") == "grant_cost" for a in new_abs for o in (a.get("ops") or [])):
        m = re.search(r"gains?\s*\+\s*(\d+)\s*cost|費用\s*\+\s*(\d+)|费用\s*\+\s*(\d+)", blob, re.I)
        amt = int(next(g for g in m.groups() if g)) if m else 4
        trait_m = re.search(r"Leader has the \{([^}]+)\}|領航卡擁有《([^》]+)》", blob, re.I)
        ab = {
            "timing": "your_turn",
            "summary": "Gains +cost if Leader has trait",
            "ops": [{"op": "grant_cost", "amount": amt, "target_kind": "self"}],
            "status": "compiled",
            "confidence": 0.85,
        }
        if trait_m:
            ab["require_leader_trait"] = next(g for g in trait_m.groups() if g)
        new_abs.append(normalize_ability(ab))
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
    for cid in [
        "EB01-027",
        "EB01-028",
        "EB02-019",
        "EB02-048",
        "EB03-042",
        "EB03-049",
        "EB03-054",
        "EB03-061",
        "EB04-009",
        "EB04-011",
        "EB04-012",
        "EB04-013",
        "EB04-027",
        "EB04-028",
        "EB04-031",
    ]:
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
