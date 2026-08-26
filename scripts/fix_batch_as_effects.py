#!/usr/bin/env python3
"""Batch AS: Roger DON!! phase / given-DON / Then-if / Jack exclude fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

ROGER = "Roger Pirates|羅傑海賊團|罗杰海盗团"
JACK = "Jack|傑克|杰克"
GOL_ROGER = "Gol.D.Roger|哥爾・D・羅傑|哥尔・D・罗杰|ゴール・D・ロジャー"


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

    # OP13-003 Roger Leader — DON!! Phase attach, not on_don_attached.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-003",
        [
            {
                "timing": "on_don_phase",
                "summary": "If field has DON!!: attach 1 DON!! placed this DON!! Phase to Leader",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "target_kind": "leader",
                        "optional": False,
                        "from_active": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_gte": 1,
            },
            {
                "timing": "your_turn",
                "summary": "If DON!! on field ≤9: this Leader −2000",
                "ops": [{"op": "buff_self", "amount": -2000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_lte": 9,
            },
            {
                "timing": "opponent_turn",
                "summary": "If DON!! on field ≤9: this Leader −2000",
                "ops": [{"op": "buff_self", "amount": -2000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_lte": 9,
            },
        ],
    )

    # OP13-065 — ZH excludes Jack (not Shanks).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-065",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5; add up to 1 Roger Pirates other than Jack",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": ROGER,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": JACK,
                        "destination": "hand",
                        "reveal_adds": True,
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
        "OP13-072",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Roger Pirates and given DON!!≥1: add up to 1 rested DON!!",
                "ops": [
                    {
                        "op": "gain_don",
                        "count": 1,
                        "as_rested": True,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": ROGER,
                "require_given_don_gte": 1,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST18-001",
        [
            {
                "timing": "on_play",
                "summary": "If DON!! on field ≥8: rest up to 1 opp Character cost≤5",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 5,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_gte": 8,
            },
        ],
    )

    # OP13-061 — given DON gates gain only; Then KO ungated. No attach_don.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-061",
        [
            {
                "timing": "on_play",
                "summary": "If given DON!!≥1: add up to 1 rested DON!!; Then KO up to 1 cost≤1",
                "ops": [
                    {
                        "op": "gain_don",
                        "count": 1,
                        "as_rested": True,
                        "optional": True,
                        "require_given_don_gte": 1,
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 1,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Similar given-DON gain_don without bogus attach_don.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-062",
        [
            {
                "timing": "on_play",
                "summary": "If given DON!!≥1: add up to 1 active DON!!",
                "ops": [
                    {
                        "op": "gain_don",
                        "count": 1,
                        "optional": True,
                        "require_given_don_gte": 1,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "Return up to 1 opp Character with base power ≤3000 to hand",
                "ops": [
                    {
                        "op": "return_to_hand",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "base_power_lte": 3000,
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
        "OP13-063",
        [
            {
                "timing": "on_play",
                "summary": "If given DON!!≥1: add up to 1 rested DON!!",
                "ops": [
                    {
                        "op": "gain_don",
                        "count": 1,
                        "as_rested": True,
                        "optional": True,
                        "require_given_don_gte": 1,
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
        "OP13-068",
        [
            {
                "timing": "your_turn",
                "summary": "If DON!! on field ≥8: this +2000",
                "ops": [{"op": "buff_self", "amount": 2000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_gte": 8,
            },
            {
                "timing": "opponent_turn",
                "summary": "If DON!! on field ≥8: this +2000",
                "ops": [{"op": "buff_self", "amount": 2000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_gte": 8,
            },
            {
                "timing": "on_play",
                "summary": "If Leader Roger Pirates: add up to 1 rested DON!!",
                "ops": [
                    {
                        "op": "gain_don",
                        "count": 1,
                        "as_rested": True,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": ROGER,
            },
        ],
    )

    # OP13-067 — Roger gates draw/trash; Then gain_don ungated.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-067",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Roger Pirates: draw 2 trash 1; Then add up to 1 rested DON!!",
                "ops": [
                    {
                        "op": "draw",
                        "count": 2,
                        "require_leader_trait": ROGER,
                    },
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": False,
                        "owner": "self",
                        "require_leader_trait": ROGER,
                    },
                    {
                        "op": "gain_don",
                        "count": 1,
                        "as_rested": True,
                        "optional": True,
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
        "P-107",
        [
            {
                "timing": "on_play",
                "summary": "If either side has ≥10 DON!! on field: Leader +2000 until opp end",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "leader",
                        "optional": False,
                        "duration": "until_opp_turn_end",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_either_don_field_gte": 10,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST23-001",
        [
            {
                "timing": "hand_cost",
                "summary": "If own Character power≥10000: this card in hand −4 cost",
                "ops": [{"op": "hand_cost_reduce", "amount": -4}],
                "status": "compiled",
                "confidence": 0.95,
                "require_own_char_power_gte": 10000,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-007",
        [
            {
                "timing": "on_play",
                "summary": "Leader +2000 until opp end",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "leader",
                        "optional": False,
                        "duration": "until_opp_turn_end",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: if opp Character power≥8000, gain Rush: Character this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "rush_character",
                        "target_kind": "self",
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_opp_char_power_gte": 8000,
            },
        ],
    )

    # OP09-004 — Rush innate; continuous −1000.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-004",
        [
            {
                "timing": "your_turn",
                "summary": "All opponent Characters −1000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -1000,
                        "target_kind": "opponent_character",
                        "optional": False,
                        "all": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "All opponent Characters −1000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -1000,
                        "target_kind": "opponent_character",
                        "optional": False,
                        "all": True,
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
        "OP09-118",
        [
            {
                "timing": "your_turn",
                "summary": "On opp Blocker: if either Life is 0, you win",
                "ops": [{"op": "win_game"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_either_life_lte": 0,
                "on_opp_blocker": True,
            },
            {
                "timing": "opponent_turn",
                "summary": "On opp Blocker: if either Life is 0, you win",
                "ops": [{"op": "win_game"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_either_life_lte": 0,
                "on_opp_blocker": True,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-076",
        [
            {
                "timing": "on_play",
                "summary": "You may rest 5 DON!!: if given DON!!≥1, up to 1 opp Character −8000",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 5,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "buff",
                        "amount": -8000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 1,
                        "require_given_don_gte": 1,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "You may trash 1: up to 1 own Leader/Character +3000 this battle",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
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
        "OP13-075",
        [
            {
                "timing": "on_play",
                "summary": "You may rest 1 DON!!: if Leader Gol.D.Roger and given DON!!, add up to 1 rested DON!!",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "gain_don",
                        "count": 1,
                        "as_rested": True,
                        "optional": True,
                        "require_leader_name": GOL_ROGER,
                        "require_given_don_gte": 1,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "Leader +3000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "leader",
                        "optional": False,
                        "duration": "battle",
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
        "OP14-077",
        [
            {
                "timing": "counter_event",
                "summary": "Up to 1 own Leader/Character +4000; Then if opp Character power≥6000, add rested DON!!",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 4000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    },
                    {
                        "op": "gain_don",
                        "count": 1,
                        "as_rested": True,
                        "optional": True,
                        "require_opp_char_power_gte": 6000,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Soft-fix similar Roger Then-if (draw/trash gated, gain_don ungated).
    for cid, entry in list(ov_cards.items()):
        info = catalog.get(cid) or {}
        zh = str(info.get("effect") or "")
        if "羅傑海賊團" not in zh and "Roger Pirates" not in str(info.get("effect_en") or ""):
            continue
        if "之後" not in zh or "追加最多1張休息狀態的咚" not in zh:
            continue
        if "抽" not in zh:
            continue
        if not isinstance(entry, dict):
            continue
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            if ab.get("timing") != "on_play" or not ab.get("require_leader_trait"):
                abs_out.append(ab)
                continue
            if not any(o.get("op") == "gain_don" for o in (ab.get("ops") or [])):
                abs_out.append(ab)
                continue
            trait = ab.pop("require_leader_trait")
            ops = []
            for o in ab.get("ops") or []:
                o = dict(o)
                if o.get("op") in {"draw", "trash_hand"}:
                    o["require_leader_trait"] = trait
                    changed = True
                ops.append(o)
            ab["ops"] = ops
            abs_out.append(ab)
            changed = True
        if changed:
            entry2 = normalize_card_entry(cid, {"version": int(entry.get("version") or 1), "abilities": abs_out})
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_as updated {n} card entries")


if __name__ == "__main__":
    main()
