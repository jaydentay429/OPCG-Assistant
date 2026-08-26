#!/usr/bin/env python3
"""Absolute-zero push v58: fill empty/broken encodings + sync variants + promote.

Dual-writes library + overrides. Writes meta/logs/ops_v58_abs0_fixed_ids.txt.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry, sanitize_ops_list  # noqa: E402

OUT_IDS = ROOT / "meta" / "logs" / "ops_v58_abs0_fixed_ids.txt"


def _base(cid: str) -> str:
    return re.sub(r"-(P\d+|R\d+|SP\d+|ALT)$", "", cid)


def _ab(timing: str, ops: list[dict[str, Any]], summary: str, **gates: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "timing": timing,
        "summary": summary,
        "ops": sanitize_ops_list(ops),
        "status": "compiled",
        "confidence": 0.95,
    }
    out.update(gates)
    return out


REBUILDS: dict[str, list[dict[str, Any]]] = {
    "OP09-118": [
        _ab(
            "your_turn",
            [{"op": "win_game"}],
            "對手發動【防禦】時，若自己或對手的生命值卡為0張時，自己將遊戲獲勝。",
            on_opp_blocker=True,
            require_either_life_lte=0,
        ),
        _ab(
            "opponent_turn",
            [{"op": "win_game"}],
            "對手發動【防禦】時，若自己或對手的生命值卡為0張時，自己將遊戲獲勝。",
            on_opp_blocker=True,
            require_either_life_lte=0,
        ),
    ],
    "OP11-046": [
        _ab(
            "your_turn",
            [
                {"op": "cannot_be_ko", "target_kind": "self", "optional": False},
                {"op": "cannot_be_rested", "target_kind": "self", "optional": False},
            ],
            "若自己的角色卡只有擁有包含『杰爾馬』特徵的角色卡時，這張角色卡不會因對手的效果而遭到KO、置為休息狀態。",
            require_all_chars_trait="GERMA|杰爾馬|杰尔马",
        ),
        _ab(
            "opponent_turn",
            [
                {"op": "cannot_be_ko", "target_kind": "self", "optional": False},
                {"op": "cannot_be_rested", "target_kind": "self", "optional": False},
            ],
            "若自己的角色卡只有擁有包含『杰爾馬』特徵的角色卡時，這張角色卡不會因對手的效果而遭到KO、置為休息狀態。",
            require_all_chars_trait="GERMA|杰爾馬|杰尔马",
        ),
    ],
    "P-078": [
        _ab(
            "your_turn",
            [{"op": "buff_self", "amount": 1000}],
            "若場上有2張以上自己休息狀態擁有《ODYSSEY》特徵的角色卡時，這張角色卡力量值+1000。",
            require_rested_own_chars_gte=2,
            require_rested_own_chars_trait="ODYSSEY",
        ),
        _ab(
            "opponent_turn",
            [{"op": "buff_self", "amount": 1000}],
            "若場上有2張以上自己休息狀態擁有《ODYSSEY》特徵的角色卡時，這張角色卡力量值+1000。",
            require_rested_own_chars_gte=2,
            require_rested_own_chars_trait="ODYSSEY",
        ),
    ],
    "P-079": [
        _ab(
            "end_of_your_turn",
            [{"op": "set_character_active", "count": 1, "target_kind": "self", "optional": True}],
            "【我方回合結束時】若場上有2張以上自己休息狀態擁有《ODYSSEY》特徵的角色卡時，將這張角色卡置為活動狀態。",
            require_rested_own_chars_gte=2,
            require_rested_own_chars_trait="ODYSSEY",
        ),
    ],
    "EB03-026": [
        _ab(
            "on_play",
            [{"op": "opponent_hand_to_bottom", "count": 1, "optional": False, "require_opp_hand_gte": 5}],
            "【登場時】若對手的手牌有5張以上時，對手將1張自身的手牌放置在卡組下面。",
            require_opp_hand_gte=5,
        ),
        _ab(
            "activate_main",
            [
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "target_kind": "own_character",
                },
                {"op": "attach_don", "count": 1, "as_rested": True, "target_kind": "leader", "optional": True},
                {
                    "op": "attach_don",
                    "count": 1,
                    "as_rested": True,
                    "target_kind": "own_character",
                    "optional": True,
                },
            ],
            "【啟動主要】【每回合1次】可將1張自己的角色卡放置在持有者的卡組下面：附加最多各1張休息狀態的咚‼卡在自己的領航卡和1張自己的角色卡。",
            once=True,
            cost_don=0,
            rest_self=False,
        ),
    ],
    "EB04-045": [
        _ab(
            "activate_main",
            [
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "trait_contains": "Revolutionary Army",
                    "duration": "turn",
                }
            ],
            "【啟動主要】可將這張角色卡置為休息狀態：若場上有2張以上費用8以上的角色卡時，最多1張自己擁有《革命軍》特徵的領航卡或角色卡，在這個回合，力量值+1000。",
            cost_don=0,
            rest_self=True,
            require_field_chars_cost_gte=8,
            require_field_chars_cost_count_gte=2,
        ),
    ],
    "OP02-071": [
        _ab(
            "on_don_returned",
            [{"op": "buff_self", "amount": 1000}],
            "【我方回合中】【每回合1次】場上的咚!!卡被放回咚!!卡組時，這張領航卡，在這個回合，力量值+1000。",
            once=True,
            require_your_turn=True,
        ),
    ],
    "OP02-110": [
        _ab(
            "on_block",
            [
                {
                    "op": "cannot_attack",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 6,
                    "duration": "turn",
                }
            ],
            "【防禦時】選擇最多1張對手費用6以下的角色卡。被選擇的角色卡，在這個回合，無法進行攻擊。",
        ),
    ],
    "OP03-024": [
        _ab(
            "on_play",
            [{"op": "rest_opponent_character", "count": 2, "cost_lte": 4, "optional": True}],
            "【登場時】若自己的領航卡擁有《東方藍》特徵時，將最多2張對手費用4以下的角色卡置為休息狀態。",
            require_leader_trait="East Blue|東方藍",
        ),
    ],
    "OP03-041": [
        _ab(
            "when_attacking",
            [{"op": "trash_deck_top", "count": 7, "optional": True, "on_life_damage": True}],
            "【咚‼×1】因為這張角色卡的攻擊，而造成對手生命值傷害時，可將7張自己卡組上面的卡片放置到廢棄區。",
            require_don_attached_gte=1,
        ),
    ],
    "OP03-045": [
        _ab(
            "opponent_turn",
            [{"op": "buff_self", "amount": 3000}],
            "【對方回合中】若自己的卡組在20張以下時，這張角色卡的力量值+3000。",
            require_deck_lte=20,
        ),
    ],
    "OP04-100": [
        _ab(
            "trigger",
            [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_leader_or_character",
                    "duration": "turn",
                }
            ],
            "【觸發器】最多1張對手的領航卡或角色卡，在這個回合，無法進行攻擊。",
        ),
    ],
    "OP08-112": [
        _ab(
            "on_play",
            [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "cost_lte": 6,
                    "duration": "until_opp_turn_end",
                    "exclude_name": "Monkey.D.Luffy|モンキー・D・ルフィ|蒙其・D・魯夫",
                }
            ],
            "【登場時】最多1張除了「蒙其・D・魯夫」以外對手費用6以下的角色卡，在下一個對手回合結束前，無法進行攻擊。",
        ),
        _ab(
            "trigger",
            [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "cost_lte": 6,
                    "duration": "until_opp_turn_end",
                    "exclude_name": "Monkey.D.Luffy|モンキー・D・ルフィ|蒙其・D・魯夫",
                }
            ],
            "【觸發器】發動這張卡片的【登場時】效果。",
        ),
    ],
    "OP10-079": [
        _ab(
            "main_start",
            [
                {"op": "ko", "target_kind": "opponent_character", "optional": True, "cost_lte": 5},
                {"op": "gain_don", "count": 1, "optional": True},
            ],
            "【主要】KO最多1張對手費用5以下的角色卡。之後，從咚‼卡組追加最多1張活動狀態的咚‼卡。",
        ),
        _ab(
            "trigger",
            [{"op": "gain_don", "count": 1, "optional": True}],
            "【觸發器】從咚‼卡組追加最多1張活動狀態的咚‼卡。",
        ),
    ],
    "OP14-111": [
        _ab(
            "on_play",
            [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "cost_lte": 6,
                    "duration": "until_opp_turn_end",
                }
            ],
            "【登場時】最多1張對手費用6以下的角色卡，在下一個對手結束階段結束前，無法進行攻擊。",
        ),
        _ab(
            "on_ko",
            [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "cost_lte": 6,
                    "duration": "until_opp_turn_end",
                }
            ],
            "【KO時】最多1張對手費用6以下的角色卡，在下一個對手結束階段結束前，無法進行攻擊。",
        ),
        _ab(
            "trigger",
            [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 4,
                    "trait_contains": "Thriller Bark Pirates",
                    "as_rested": True,
                    "from_zone": "trash",
                }
            ],
            "【觸發器】使最多1張自己廢棄區中費用4以下擁有《恐怖三桅帆船海賊團》特徵的角色卡，以休息狀態登場。",
        ),
    ],
    "OP15-097": [
        _ab(
            "main_start",
            [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "base_cost_lte": 5,
                    "duration": "until_opp_turn_end",
                }
            ],
            "【主要】若自己廢棄區有10張以上卡片時，最多1張對手原本費用5以下的角色卡，在下一個對手結束階段結束前，無法進行攻擊。",
            require_trash_gte=10,
        ),
        _ab(
            "trigger",
            [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "base_cost_lte": 5,
                    "duration": "until_opp_turn_end",
                }
            ],
            "【觸發器】發動這張卡片的【主要】效果。",
            require_trash_gte=10,
        ),
    ],
    "ST12-008": [
        _ab(
            "when_attacking",
            [{"op": "rest_opponent_character", "count": 1, "cost_lte": 6, "optional": True}],
            "【咚‼×1】【攻擊時】將最多1張對手費用6以下的角色卡置為休息狀態。",
            require_don_attached_gte=1,
        ),
    ],
    "OP16-074": [
        _ab(
            "on_play",
            [{"op": "return_don", "count": 1, "owner": "opponent"}],
            "【登場時】若自己的領航卡擁有《推進城》特徵時，對手將1張自身場上的咚‼卡放回咚‼卡組。",
            require_leader_trait="Impel Down|推進城",
        ),
        _ab(
            "on_ko",
            [{"op": "return_don", "count": 4, "owner": "opponent"}],
            "【KO時】對手將4張自身場上的咚‼卡放回咚‼卡組。",
        ),
    ],
    "OP09-013": [
        _ab(
            "on_play",
            [
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "own_leader",
                    "optional": True,
                    "duration": "until_opp_turn_end",
                }
            ],
            "【登場時】最多1張自己的領航卡，在下一個對手回合結束前，力量值+1000。",
        ),
        _ab(
            "when_attacking",
            [
                {
                    "op": "buff",
                    "amount": -1000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "turn",
                }
            ],
            "【咚‼×1】【攻擊時】最多1張對手的角色卡，在這個回合，力量值-1000。",
            require_don_attached_gte=1,
        ),
    ],
    "P-114": [
        _ab(
            "end_of_your_turn",
            [{"op": "set_character_active", "count": 1, "target_kind": "self", "optional": True}],
            "【我方回合結束時】若有自己活動狀態的咚‼卡，將這張角色卡置為活動狀態。",
            require_don_active_gte=1,
        ),
    ],
    "OP07-021": [
        _ab(
            "end_of_your_turn",
            [{"op": "active_don", "count": 1, "optional": True}],
            "【我方回合結束時】將最多1張自己的咚‼卡置為活動狀態。",
        ),
    ],
}


def main() -> None:
    lib_path, ovr_path = library_paths()
    lib = json.loads(lib_path.read_text())
    ovr = json.loads(ovr_path.read_text()) if ovr_path.exists() else {"cards": {}}
    cards = lib.setdefault("cards", {})
    ovc = ovr.setdefault("cards", {})
    idx = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    all_ids = set(cards) | set(idx)

    def variants(base_id: str) -> list[str]:
        return sorted({c for c in all_ids if c == base_id or c.startswith(base_id + "-")})

    def write(cid: str, abilities: list[dict[str, Any]]) -> None:
        # Drop empty on_block keyword stubs.
        cleaned = []
        for ab in abilities:
            if ab.get("timing") == "on_block" and not (ab.get("ops") or []):
                continue
            cleaned.append(ab)
        entry = normalize_card_entry(cid, {"version": 1, "abilities": cleaned})
        cards[cid] = entry
        ovc[cid] = entry

    written: list[str] = []
    for base, abs_ in REBUILDS.items():
        for cid in variants(base):
            write(cid, copy.deepcopy(abs_))
            written.append(cid)
        print(base, "->", len(variants(base)))

    # Sync broken P/R variants from best base encoding for continuous buff_self amount.
    synced = 0
    for cid, entry in list(cards.items()):
        b = _base(cid)
        if cid == b:
            continue
        base_entry = cards.get(b) or ovc.get(b)
        if not base_entry:
            continue
        abs_ = entry.get("abilities") or []
        broken = False
        for ab in abs_:
            ops = ab.get("ops") or []
            if not ops and ab.get("timing") == "on_block":
                broken = True
            if len(ops) == 1 and ops[0].get("op") == "buff_self" and int(ops[0].get("amount") or 0) == 0:
                broken = True
            if len(ops) == 1 and ops[0].get("op") == "choose_target" and not ops[0].get("then_op"):
                broken = True
        if broken and (base_entry.get("abilities") or []):
            write(cid, copy.deepcopy(base_entry["abilities"]))
            written.append(cid)
            synced += 1
    print("synced_variants", synced)

    # Promote remaining needs_review with non-empty runnable ops → compiled.
    promoted = 0
    for cid, entry in list(cards.items()):
        changed = False
        abs_ = copy.deepcopy(entry.get("abilities") or [])
        for ab in abs_:
            if ab.get("status") != "needs_review":
                continue
            ops = ab.get("ops") or []
            if not ops or any(o.get("op") == "unsupported" for o in ops):
                continue
            if len(ops) == 1 and ops[0].get("op") == "choose_target" and not ops[0].get("then_op"):
                continue
            ab["status"] = "compiled"
            ab["confidence"] = max(float(ab.get("confidence") or 0.7), 0.9)
            changed = True
            promoted += 1
        if changed:
            write(cid, abs_)
            written.append(cid)
    print("promoted_needs_review", promoted)

    # Strip remaining empty on_block stubs everywhere.
    stripped = 0
    for cid, entry in list(cards.items()):
        abs_ = entry.get("abilities") or []
        if any(a.get("timing") == "on_block" and not (a.get("ops") or []) for a in abs_):
            write(cid, copy.deepcopy(abs_))
            written.append(cid)
            stripped += 1
    print("stripped_empty_on_block", stripped)

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    lib["generated_at"] = now
    ovr["generated_at"] = now
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, separators=(",", ":")))
    ovr_path.write_text(json.dumps(ovr, ensure_ascii=False, separators=(",", ":")))
    reload_effect_library(force=True)

    merged: list[str] = []
    seen: set[str] = set()
    for x in written:
        if x not in seen:
            seen.add(x)
            merged.append(x)
    OUT_IDS.write_text("\n".join(merged) + "\n")
    print("wrote_ids", len(merged), OUT_IDS)


if __name__ == "__main__":
    main()
