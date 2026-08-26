#!/usr/bin/env python3
"""Batch AZ: Blackbeard / Teach / Avalo / Then-if negate fixes."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

BB = "Blackbeard Pirates|黑鬍子海賊團|黑胡子海贼团"
KUZAN = "Kuzan|庫山|库山"
MY_ERA = "My Era...Begins!!|是我的時代啦!!!!|是我的时代啦!!!!"


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


def main() -> None:
    ov_path, lib_path = library_paths()
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    ov = json.loads(ov_path.read_text())
    lib = json.loads(lib_path.read_text())
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    n = 0

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-081",
        [
            {
                "timing": "your_turn",
                "summary": "Your [On Play] effects are negated",
                "ops": [{"op": "negate_on_play", "side": "self", "duration": "permanent"}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "Your [On Play] effects are negated",
                "ops": [{"op": "negate_on_play", "side": "self", "duration": "permanent"}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "You may trash 1: opp [On Play] negated until opp turn end",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "negate_on_play",
                        "side": "opponent",
                        "duration": "until_opp_turn_end",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP09-089 — trash hand + trash self; draw gated; Then −2 cost ungated.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-089",
        [
            {
                "timing": "activate_main",
                "summary": "Trash 1 + trash this: if BB Leader draw 1; Then up to 1 opp Character −2 cost",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "trash",
                        "target_kind": "self",
                        "optional": False,
                        "as_cost": True,
                    },
                    {
                        "op": "draw",
                        "count": 1,
                        "require_leader_trait": BB,
                    },
                    {
                        "op": "reduce_cost",
                        "amount": -2,
                        "count": 1,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                    },
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
        "OP09-095",
        [
            {
                "timing": "activate_main",
                "summary": "Rest 1 DON!! + this: look top 5; add up to 1 BB; rest bottom",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": BB,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "rest_self": True,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-083",
        [
            {
                "timing": "on_play",
                "summary": "Trash 2 from hand",
                "ops": [{"op": "trash_hand", "count": 2, "optional": False, "owner": "self"}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-090",
        [
            {
                "timing": "activate_main",
                "summary": "Rest this: if BB Leader, KO up to 1 opp Character cost≤1",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 1,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "rest_self": True,
                "require_leader_trait": BB,
            },
            {
                "timing": "on_ko",
                "summary": "Draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-086",
        [
            {
                "timing": "your_turn",
                "summary": "Cannot be KO'd by opponent effects",
                "ops": [{"op": "cannot_be_ko", "target_kind": "self", "optional": False}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "Cannot be KO'd by opponent effects",
                "ops": [{"op": "cannot_be_ko", "target_kind": "self", "optional": False}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "your_turn",
                "summary": "If BB Leader: +1000 per 4 cards in trash",
                "ops": [{"op": "buff_self", "amount": 1000, "per_trash_cards": 4}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": BB,
            },
            {
                "timing": "opponent_turn",
                "summary": "If BB Leader: +1000 per 4 cards in trash",
                "ops": [{"op": "buff_self", "amount": 1000, "per_trash_cards": 4}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": BB,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-086",
        [
            {
                "timing": "opponent_turn",
                "summary": "This +2000",
                "ops": [{"op": "buff_self", "amount": 2000}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: if BB Leader and played this turn, KO up to 1 opp base cost≤3",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "base_cost_lte": 3,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_leader_trait": BB,
                "require_played_this_turn": True,
            },
        ],
    )

    # PRB02-015 — Blocker + cost+4 continuous; KO on KO.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "PRB02-015",
        [
            {
                "timing": "your_turn",
                "summary": "If BB Leader: this gains Blocker and +4 cost",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    },
                    {"op": "grant_cost", "amount": 4, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": BB,
            },
            {
                "timing": "opponent_turn",
                "summary": "If BB Leader: this gains Blocker and +4 cost",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    },
                    {"op": "grant_cost", "amount": 4, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": BB,
            },
            {
                "timing": "on_ko",
                "summary": "If BB Leader: KO up to 1 opp Character base cost≤4",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "base_cost_lte": 4,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": BB,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-083",
        [
            {
                "timing": "activate_main",
                "summary": "Rest this: if BB Leader, up to 1 opp Character −3 cost",
                "ops": [
                    {
                        "op": "reduce_cost",
                        "amount": -3,
                        "count": 1,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "rest_self": True,
                "require_leader_trait": BB,
            },
            {
                "timing": "on_ko",
                "summary": "Draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-084",
        [
            {
                "timing": "activate_main",
                "summary": "Once: if BB Leader, choose Double Attack / Banish / Blocker until opp end",
                "ops": [
                    {
                        "op": "choose_one",
                        "chooser": "self",
                        "options": [
                            {
                                "id": "da",
                                "label": "雙重攻擊",
                                "ops": [
                                    {
                                        "op": "grant_keyword",
                                        "keyword": "double_attack",
                                        "target_kind": "self",
                                        "duration": "until_opp_turn_end",
                                    }
                                ],
                            },
                            {
                                "id": "banish",
                                "label": "消失",
                                "ops": [
                                    {
                                        "op": "grant_keyword",
                                        "keyword": "banish",
                                        "target_kind": "self",
                                        "duration": "until_opp_turn_end",
                                    }
                                ],
                            },
                            {
                                "id": "blocker",
                                "label": "防禦",
                                "ops": [
                                    {
                                        "op": "grant_keyword",
                                        "keyword": "blocker",
                                        "target_kind": "self",
                                        "duration": "until_opp_turn_end",
                                    }
                                ],
                            },
                        ],
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_leader_trait": BB,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-082",
        [
            {
                "timing": "your_turn",
                "summary": "Cannot leave field by opponent effects",
                "ops": [
                    {
                        "op": "cannot_be_removed",
                        "target_kind": "self",
                        "any_leave": True,
                        "optional": False,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "Cannot leave field by opponent effects",
                "ops": [
                    {
                        "op": "cannot_be_removed",
                        "target_kind": "self",
                        "any_leave": True,
                        "optional": False,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Trash this: draw 1; Then play up to 1 BB cost≤5 other than Kuzan from trash",
                "ops": [
                    {
                        "op": "trash",
                        "target_kind": "self",
                        "optional": True,
                        "as_cost": True,
                    },
                    {"op": "draw", "count": 1},
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "exclude_name": KUZAN,
                        "trait_contains": BB,
                        "from_zone": "trash",
                    },
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
        "ST27-003",
        [
            {
                "timing": "on_ko",
                "summary": "Play up to 1 BB Character cost≤5 from trash rested",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "trait_contains": BB,
                        "as_rested": True,
                        "from_zone": "trash",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP09-093 — Leader negate gated; Then char negate + deny ungated.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-093",
        [
            {
                "timing": "activate_main",
                "summary": "Once: if BB+played this turn, negate opp Leader; Then negate+deny 1 opp Character until opp end",
                "ops": [
                    {
                        "op": "negate_effects",
                        "count": 1,
                        "optional": True,
                        "duration": "turn",
                        "target_kind": "leader",
                        "include_leader": True,
                        "require_leader_trait": BB,
                        "require_played_this_turn": True,
                    },
                    {
                        "op": "negate_effects",
                        "count": 1,
                        "optional": True,
                        "duration": "until_opp_turn_end",
                        "target_kind": "opponent_character",
                        "include_characters": True,
                    },
                    {
                        "op": "deny_attack",
                        "count": 1,
                        "optional": False,
                        "target_kind": "opponent_character",
                        "duration": "until_opp_turn_end",
                        "same_target_as_prior": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-096",
        [
            {
                "timing": "on_play",
                "summary": "Look top 3; add up to 1 BB other than this; trash rest",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": BB,
                        "top_n": 3,
                        "max_add": 1,
                        "trash_rest": True,
                        "order_bottom": False,
                        "exclude_name": MY_ERA,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Activate this card's Main effect",
                "ops": [{"op": "activate_timing", "timing": "on_play"}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-099",
        [
            {
                "timing": "activate_main",
                "summary": "Trash 1 + rest this Stage: look top 3; add up to 1 BB; rest bottom",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": BB,
                        "top_n": 3,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "rest_self": True,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-098",
        [
            {
                "timing": "on_play",
                "summary": "If BB Leader: negate up to 1 opp Character; Then if that cost≤4, KO it",
                "ops": [
                    {
                        "op": "negate_effects",
                        "count": 1,
                        "optional": True,
                        "duration": "turn",
                        "target_kind": "opponent_character",
                        "include_characters": True,
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 1,
                        "cost_lte": 4,
                        "same_target_as_prior": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": BB,
            },
            {
                "timing": "trigger",
                "summary": "Negate up to 1 opp Leader or Character this turn",
                "ops": [
                    {
                        "op": "negate_effects",
                        "count": 1,
                        "optional": True,
                        "duration": "turn",
                        "target_kind": "opponent_leader_or_character",
                        "include_leader": True,
                        "include_characters": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Soft-fix ST27-004: BB leader → Blocker + cost+1 per 4 trash; on_play trash 1.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST27-004",
        [
            {
                "timing": "on_play",
                "summary": "Trash 1 from hand",
                "ops": [{"op": "trash_hand", "count": 1, "optional": False, "owner": "self"}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "your_turn",
                "summary": "If BB Leader: Blocker; +1 cost per 4 trash cards",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    },
                    {
                        "op": "grant_cost",
                        "amount": 1,
                        "target_kind": "self",
                        "per_trash_cards": 4,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": BB,
            },
            {
                "timing": "opponent_turn",
                "summary": "If BB Leader: Blocker; +1 cost per 4 trash cards",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    },
                    {
                        "op": "grant_cost",
                        "amount": 1,
                        "target_kind": "self",
                        "per_trash_cards": 4,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": BB,
            },
        ],
    )

    # Soft-fix: activate_main missing require_played_this_turn when paper says 登場的回合.
    played_re = re.compile(r"【啟動主要】[^【]{0,160}(?:而且是|若是)?這張角色卡登場的回合")
    for cid, entry in list(ov_cards.items()):
        info = catalog.get(cid) or {}
        zh = str(info.get("effect") or "")
        if not played_re.search(zh):
            continue
        if "而且是這張角色卡登場的回合" not in zh and "若是這張角色卡登場的回合" not in zh:
            continue
        then_if = bool(re.search(r"登場的回合時，.{2,100}。之後，", zh))
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            if ab.get("timing") != "activate_main":
                abs_out.append(ab)
                continue
            ops = [dict(o) for o in (ab.get("ops") or [])]
            if any(o.get("require_played_this_turn") for o in ops) or ab.get("require_played_this_turn"):
                abs_out.append(ab)
                continue
            if then_if:
                for o in ops:
                    if o.get("as_cost"):
                        continue
                    o["require_played_this_turn"] = True
                    if ab.get("require_leader_trait") and not o.get("require_leader_trait"):
                        o["require_leader_trait"] = ab.pop("require_leader_trait")
                    changed = True
                    break
                ab["ops"] = ops
            else:
                ab["require_played_this_turn"] = True
                changed = True
            abs_out.append(ab)
        if changed:
            entry2 = normalize_card_entry(
                cid, {"version": int(entry.get("version") or 1), "abilities": abs_out}
            )
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    # Soft-fix: permanent self negate_on_play only on your_turn → add opponent_turn.
    for cid, entry in list(ov_cards.items()):
        abs_list = list(entry.get("abilities") or [])
        has_yt = False
        has_ot = False
        sample = None
        for ab in abs_list:
            ops = ab.get("ops") or []
            if len(ops) == 1 and ops[0].get("op") == "negate_on_play" and ops[0].get("side") == "self":
                if ab.get("timing") == "your_turn":
                    has_yt = True
                    sample = ab
                if ab.get("timing") == "opponent_turn":
                    has_ot = True
        if has_yt and not has_ot and sample is not None:
            abs_list.append(
                {
                    **{k: sample.get(k) for k in sample if k != "timing"},
                    "timing": "opponent_turn",
                }
            )
            entry2 = normalize_card_entry(
                cid, {"version": int(entry.get("version") or 1), "abilities": abs_list}
            )
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_az updated {n} card entries")


if __name__ == "__main__":
    main()
