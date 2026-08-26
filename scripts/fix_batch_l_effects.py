#!/usr/bin/env python3
"""Batch L: SWORD auras, on_opp_ko, any-leave, Navy gates, exclude names."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

NAVY = "Navy|海軍"
SWORD = "SWORD"
HELMEPPO = "Helmeppo|貝魯梅柏|贝鲁梅柏"
KUJYAKU = "Kujyaku|孔雀"
RIPPER = "Ripper|梨帕"
NAVY_EVENT = "I'm Gonna Be a Navy Officer!!!|我可是…要成為海軍將軍的男人!!!!|ぼくは!!!海軍将校になる男です!!!!"

ALL_TRAIT_COST_BUFF = re.compile(
    r"【(?:對方|对方)回合中】自己費用\s*(\d+)\s*以下擁有《([^》]+)》特徵的角色卡全數力量值\s*([+\-−]?\d+)",
)
LEADER_BASE_POWER = re.compile(
    r"【(?:對方|对方)回合中】自己擁有《([^》]+)》特徵的領航卡，原本的力量值變更成\s*(\d+)",
)
OPP_KO_DRAW = re.compile(r"對手的角色卡遭到KO時[，,]\s*抽\s*(\d+)")
REST_TO_TRASH = re.compile(r"將其餘卡片放到廢棄區")
BELLEMERE = re.compile(r"exclude_name.:\s*.*Bellemere")
AFTERWARDS_IF = re.compile(r"之後[，,].{0,8}若")
BLOCKER_OTHER = re.compile(
    r"若場上有除了「([^」]+)」以外自己([^角]{0,12})擁有《([^》]+)》特徵的角色卡時[，,].{0,20}獲得【防禦】"
)


def _paper(catalog: dict[str, Any], cid: str) -> str:
    info = catalog.get(cid) or {}
    return str(info.get("effect") or info.get("effect_text") or info.get("text") or "")


def _variants(catalog: dict[str, Any], base: str) -> list[str]:
    out = [base]
    out.extend(sorted(k for k in catalog if k.startswith(base + "-")))
    return [c for c in out if c in catalog or c == base]


def _write(ov_cards: dict, lib_cards: dict, catalog: dict, cid: str, abilities: list[dict[str, Any]]) -> int:
    n = 0
    for vid in _variants(catalog, cid):
        entry = normalize_card_entry(vid, {"version": 1, "abilities": abilities})
        ov_cards[vid] = entry
        lib_cards[vid] = {**entry, "card_id": vid}
        n += 1
    return n


def _named(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-041",
        [
            {
                "timing": "opponent_turn",
                "summary": "Opp turn: all own SWORD Characters cost≤6 +2000 (including this)",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_character",
                        "all": True,
                        "trait_contains": SWORD,
                        "cost_lte": 6,
                        "optional": False,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_play",
                "summary": "May trash 1 Navy card from hand: draw 2",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "trait_contains": NAVY,
                    },
                    {"op": "draw", "count": 2},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-003",
        [
            {
                "timing": "opponent_turn",
                "summary": "Opp turn: own Navy Leader printed power becomes 7000",
                "ops": [
                    {
                        "op": "set_base_power",
                        "amount": 7000,
                        "target_kind": "leader",
                        "optional": False,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": NAVY,
            }
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-044",
        [
            {
                "timing": "your_turn",
                "summary": "Once: if Leader Navy and this would leave, may trash 1 hand instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "ko",
                        "target": "self",
                        "cost": "trash_hand",
                        "life_position": "top",
                        "any_leave": True,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_leader_trait": NAVY,
            },
            {
                "timing": "opponent_turn",
                "summary": "Once: if Leader Navy and this would leave, may trash 1 hand instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "ko",
                        "target": "self",
                        "cost": "trash_hand",
                        "life_position": "top",
                        "any_leave": True,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_leader_trait": NAVY,
            },
            {
                "timing": "your_turn",
                "summary": "Once: when opp Character is KO'd, draw 1",
                "ops": [{"op": "draw", "count": 1, "on_opp_ko": True}],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "on_opp_ko": True,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-008",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 own SWORD Leader or Character may attack active Characters this turn",
                "ops": [
                    {
                        "op": "allow_attack_active",
                        "count": 1,
                        "target_kind": "own_leader_or_character",
                        "trait_contains": SWORD,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "Up to 1 own SWORD Leader or Character may attack active Characters this turn",
                "ops": [
                    {
                        "op": "allow_attack_active",
                        "count": 1,
                        "target_kind": "own_leader_or_character",
                        "trait_contains": SWORD,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: up to 1 opp Character −1000 this turn",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -1000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-008",
        [
            {
                "timing": "on_play",
                "summary": "May trash 1 hand: if Navy Leader, up to 1 opp Character −6000 this turn",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "buff",
                        "amount": -6000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                        "require_leader_trait": NAVY,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-082",
        [
            {
                "timing": "activate_main",
                "summary": "Trash this: if Navy Leader, up to 1 Navy Character may attack active; then trash top 2",
                "ops": [
                    {
                        "op": "trash",
                        "target_kind": "self",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "allow_attack_active",
                        "count": 1,
                        "target_kind": "own_character",
                        "trait_contains": NAVY,
                        "optional": True,
                        "require_leader_trait": NAVY,
                    },
                    {
                        "op": "trash_deck_top",
                        "count": 2,
                        "optional": False,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": False,
                "once": False,
            }
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-092",
        [
            {
                "timing": "on_play",
                "summary": "May trash 1 hand: draw 1 and play up to 1 SWORD cost≤8 other than Helmeppo from trash; EOT that Character to bottom",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {"op": "draw", "count": 1},
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 8,
                        "exclude_name": HELMEPPO,
                        "trait_contains": SWORD,
                        "from_zone": "trash",
                    },
                    {
                        "op": "return_to_bottom",
                        "count": 1,
                        "optional": False,
                        "at_end_of_turn": True,
                        "effect_played_only": True,
                        "target_kind": "own_character",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )
    blocker = {
        "timing": "your_turn",
        "summary": "If you have another black Navy Character other than Ripper, this gains Blocker",
        "ops": [
            {
                "op": "grant_keyword",
                "keyword": "blocker",
                "target_kind": "self",
                "duration": "permanent",
            }
        ],
        "status": "compiled",
        "confidence": 0.95,
        "require_other_chars_trait": NAVY,
        "require_chars_color": "black",
        "require_other_exclude_name": RIPPER,
    }
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-096",
        [
            blocker,
            {**blocker, "timing": "opponent_turn"},
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-099",
        [
            {
                "timing": "on_play",
                "summary": "Look 3: add up to 1 Navy other than this Event; rest to trash",
                "ops": [
                    {
                        "op": "search_deck",
                        "trait_contains": NAVY,
                        "top_n": 3,
                        "max_add": 1,
                        "trash_rest": True,
                        "order_bottom": False,
                        "exclude_name": NAVY_EVENT,
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Activate this card's Main effect",
                "ops": [
                    {
                        "op": "activate_timing",
                        "timing": "on_play",
                        "summary": "Activate this card's Main effect",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-004",
        [
            {
                "timing": "on_play",
                "summary": "Look 5: add up to 1 Navy excluding Kujyaku; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "trait_contains": NAVY,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": KUJYAKU,
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "May trash self: up to 1 own Character +1000 this turn",
                "ops": [
                    {
                        "op": "trash",
                        "target_kind": "self",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "buff",
                        "amount": 1000,
                        "target_kind": "own_character",
                        "optional": True,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": False,
                "once": False,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-096",
        [
            {
                "timing": "on_play",
                "summary": "May rest 2 DON!!: up to 1 opp Character cost≤5 effects negated this turn",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 2,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "negate_effects",
                        "count": 1,
                        "optional": True,
                        "duration": "turn",
                        "target_kind": "opponent_character",
                        "cost_lte": 5,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "If trash≥10: up to 1 own Leader or Character +4000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 4000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_trash_gte": 10,
            },
        ],
    )
    return n


def _abilities_of(ov_cards: dict, lib_cards: dict, cid: str) -> list[dict[str, Any]]:
    entry = ov_cards.get(cid) or lib_cards.get(cid) or {}
    return list(entry.get("abilities") or [])


def _store(ov_cards: dict, lib_cards: dict, cid: str, abilities: list[dict[str, Any]]) -> None:
    entry = normalize_card_entry(cid, {"version": 1, "abilities": abilities})
    ov_cards[cid] = entry
    lib_cards[cid] = {**entry, "card_id": cid}


def _trait_enc(zh: str) -> str:
    aliases = {
        "海軍": NAVY,
        "SWORD": SWORD,
        "和之國": "Land of Wano|和之國",
        "白鬍子海賊團": "Whitebeard Pirates|白鬍子海賊團",
    }
    return aliases.get(zh, zh)


def _patch_similar(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0
    skip = {
        "EB03-041",
        "EB04-003",
        "EB04-044",
        "EB03-008",
        "OP11-008",
        "OP11-082",
        "OP11-092",
        "OP11-096",
        "OP11-099",
        "OP11-004",
        "OP14-096",
        "OP13-007",
        "OP11-001",
        "EB04-047",
        "PRB02-001",
    }

    def _skipped(cid: str) -> bool:
        return any(cid == s or cid.startswith(s + "-") for s in skip)

    for cid, info in catalog.items():
        if not isinstance(info, dict):
            continue
        if _skipped(cid):
            continue
        paper = _paper(catalog, cid)
        if not paper:
            continue
        abilities = _abilities_of(ov_cards, lib_cards, cid)
        changed = False

        m_all = ALL_TRAIT_COST_BUFF.search(paper)
        if m_all:
            cost_n = int(m_all.group(1))
            trait = _trait_enc(m_all.group(2))
            amt = int(str(m_all.group(3)).replace("−", "-").replace("—", "-"))
            need = [
                {
                    "timing": "opponent_turn",
                    "summary": f"Opp turn: all own {trait} Characters cost≤{cost_n} {amt:+d}",
                    "ops": [
                        {
                            "op": "buff",
                            "amount": amt,
                            "target_kind": "own_character",
                            "all": True,
                            "trait_contains": trait,
                            "cost_lte": cost_n,
                            "optional": False,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                }
            ]
            # Keep other timings (on_play etc.)
            others = [a for a in abilities if a.get("timing") != "opponent_turn"]
            merged = others + need
            if abilities != merged:
                abilities = merged
                changed = True

        m_lead = LEADER_BASE_POWER.search(paper)
        if m_lead:
            trait = _trait_enc(m_lead.group(1))
            amt = int(m_lead.group(2))
            patched = False
            new_abs: list[dict[str, Any]] = []
            for ab in abilities:
                if ab.get("timing") != "opponent_turn":
                    new_abs.append(ab)
                    continue
                ops = list(ab.get("ops") or [])
                if any(o.get("op") in {"set_base_power", "continuous_set_base_power"} for o in ops):
                    ops = [
                        {
                            "op": "set_base_power",
                            "amount": amt,
                            "target_kind": "leader",
                            "optional": False,
                        }
                    ]
                    ab = dict(ab)
                    ab["ops"] = ops
                    ab["require_leader_trait"] = trait
                    patched = True
                new_abs.append(ab)
            if not patched:
                new_abs.append(
                    {
                        "timing": "opponent_turn",
                        "summary": f"Opp turn: own {trait} Leader printed power becomes {amt}",
                        "ops": [
                            {
                                "op": "set_base_power",
                                "amount": amt,
                                "target_kind": "leader",
                                "optional": False,
                            }
                        ],
                        "status": "compiled",
                        "confidence": 0.95,
                        "require_leader_trait": trait,
                    }
                )
                patched = True
            if patched:
                abilities = new_abs
                changed = True

        m_ko = OPP_KO_DRAW.search(paper)
        if m_ko and "【我方回合中】" in paper:
            has_flag = any(
                a.get("on_opp_ko") or any(o.get("on_opp_ko") for o in (a.get("ops") or []) if isinstance(o, dict))
                for a in abilities
            )
            if not has_flag:
                abilities = list(abilities) + [
                    {
                        "timing": "your_turn",
                        "summary": f"Once: when opp Character is KO'd, draw {m_ko.group(1)}",
                        "ops": [{"op": "draw", "count": int(m_ko.group(1)), "on_opp_ko": True}],
                        "status": "compiled",
                        "confidence": 0.95,
                        "once": True,
                        "on_opp_ko": True,
                    }
                ]
                changed = True

        if REST_TO_TRASH.search(paper):
            for ab in abilities:
                ops = list(ab.get("ops") or [])
                for op in ops:
                    if op.get("op") != "search_deck":
                        continue
                    if op.get("trash_rest"):
                        continue
                    if op.get("order_bottom"):
                        op["trash_rest"] = True
                        op["order_bottom"] = False
                        changed = True
                ab["ops"] = ops

        for ab in abilities:
            ops = list(ab.get("ops") or [])
            for op in ops:
                excl = str(op.get("exclude_name") or "")
                if excl == "Bellemere" and ("貝魯梅柏" in paper or "Helmeppo" in paper):
                    op["exclude_name"] = HELMEPPO
                    changed = True
                if excl == "Kujyaku" and "孔雀" in paper:
                    op["exclude_name"] = KUJYAKU
                    changed = True
            ab["ops"] = ops

        # Activate: 若 Leader … 之後 still runs — move ability-level Navy gate onto pre-之後 ops.
        if (
            any(a.get("timing") == "activate_main" and a.get("require_leader_trait") for a in abilities)
            and re.search(r"若自己的領航卡擁有《[^》]+》特徵時[，,].{0,80}之後", paper)
        ):
            new_abs = []
            for ab in abilities:
                if ab.get("timing") != "activate_main" or not ab.get("require_leader_trait"):
                    new_abs.append(ab)
                    continue
                trait = ab.get("require_leader_trait")
                ops = list(ab.get("ops") or [])
                gated = False
                for op in ops:
                    if op.get("op") in {"allow_attack_active", "buff", "grant_keyword"} and not gated:
                        op["require_leader_trait"] = trait
                        gated = True
                        break
                ab = dict(ab)
                ab.pop("require_leader_trait", None)
                ab["ops"] = ops
                new_abs.append(ab)
                changed = True
            abilities = new_abs

        m_blk = BLOCKER_OTHER.search(paper)
        if m_blk:
            excl_name = m_blk.group(1)
            color_zh = m_blk.group(2)
            trait = _trait_enc(m_blk.group(3))
            color = "black" if "黑" in color_zh else ("red" if "紅" in color_zh or "红" in color_zh else "")
            excl = RIPPER if "梨帕" in excl_name or "Ripper" in excl_name else excl_name
            need = {
                "timing": "your_turn",
                "summary": f"If another {color} {trait} Character other than {excl_name}, this gains Blocker",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_other_chars_trait": trait,
            }
            if color:
                need["require_chars_color"] = color
            need["require_other_exclude_name"] = excl
            others = [
                a
                for a in abilities
                if not (
                    a.get("timing") in {"your_turn", "opponent_turn"}
                    and any(o.get("op") == "grant_keyword" and o.get("keyword") == "blocker" for o in (a.get("ops") or []))
                )
            ]
            merged = others + [need, {**need, "timing": "opponent_turn"}]
            if abilities != merged:
                abilities = merged
                changed = True

        # Paper −N vs encoded amount mismatch on On Play trash-then-debuff.
        m_amt = re.search(r"力量值\s*([+\-−]\d+)", paper)
        if m_amt and "【登場時】" in paper:
            want = int(str(m_amt.group(1)).replace("−", "-"))
            for ab in abilities:
                if ab.get("timing") != "on_play":
                    continue
                for op in ab.get("ops") or []:
                    if op.get("op") == "buff" and int(op.get("amount") or 0) < 0 and int(op.get("amount") or 0) != want:
                        op["amount"] = want
                        changed = True

        if changed:
            _store(ov_cards, lib_cards, cid, abilities)
            n += 1
    return n


def main() -> int:
    ov_path = ROOT / "index" / "card_effect_overrides.json"
    lib_path, _ = library_paths()
    ov = json.loads(ov_path.read_text(encoding="utf-8"))
    lib = json.loads(lib_path.read_text(encoding="utf-8"))
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))

    named = _named(catalog, ov_cards, lib_cards)
    similar = _patch_similar(catalog, ov_cards, lib_cards)

    ov["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lib["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = lib_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(lib, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(lib_path)
    reload_effect_library(force=True)
    print(f"wrote named={named} similar={similar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
