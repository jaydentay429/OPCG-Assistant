#!/usr/bin/env python3
"""Batch AT: Donquixote / DON!!−1 redirect / replace_leave / counter search fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

DONQ = "Donquixote Pirates|唐吉訶德海賊團|唐吉诃德海贼团"
EXCLUDE_078 = (
    "I Do Not Forgive Those Who Laugh at My Family!!!|"
    "我絕對不會放過嘲笑我家人的傢伙…!!!|"
    "我绝对不会放过嘲笑我家人的家伙…!!!"
)


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

    # OP14-060 Leader — DON!!−1 (return), then redirect to Leader or Donquixote Character.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-060",
        [
            {
                "timing": "on_opponent_attack",
                "summary": "Once: DON!!−1: redirect attack to Leader or Donquixote Character",
                "ops": [
                    {
                        "op": "return_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                    },
                    {
                        "op": "redirect_attack",
                        "target_kind": "own_leader_or_character",
                        "trait_contains": DONQ,
                        "include_leader": True,
                        "optional": False,
                        "summary": "Change the attack target",
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
        "OP10-065",
        [
            {
                "timing": "activate_main",
                "summary": "Rest 1 DON!! + this: look top 5, add up to 1 Donquixote",
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
                        "trait_contains": DONQ,
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
        "OP14-067",
        [
            {
                "timing": "on_ko",
                "summary": "Add up to 1 rested DON!!; look top 5, add up to 1 Donquixote",
                "ops": [
                    {
                        "op": "gain_don",
                        "count": 1,
                        "as_rested": True,
                        "optional": True,
                    },
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": DONQ,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-063",
        [
            {
                "timing": "on_play",
                "summary": "Add up to 1 active DON!!",
                "ops": [{"op": "gain_don", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_ko",
                "summary": "If opp DON!!≥6: play up to 1 Donquixote Character cost≤5 from hand",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "trait_contains": DONQ,
                        "from_zone": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_opp_don_field_gte": 6,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-072",
        [
            {
                "timing": "on_play",
                "summary": "Add up to 1 active DON!!",
                "ops": [{"op": "gain_don", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_ko",
                "summary": "DON!!−1: add up to 1 top deck card to Life top",
                "ops": [
                    {
                        "op": "return_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                    },
                    {
                        "op": "add_life",
                        "count": 1,
                        "optional": True,
                        "position": "top",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP14-061 Vergo — missing replace_leave; when_attacking wrongly had once + buff_self.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-061",
        [
            {
                "timing": "your_turn",
                "summary": "Once: Donquixote Character leave by opp effect → return 1 DON!! instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "return_don",
                        "don_count": 1,
                        "trait_contains": DONQ,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
            {
                "timing": "opponent_turn",
                "summary": "Once: Donquixote Character leave by opp effect → return 1 DON!! instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "return_don",
                        "don_count": 1,
                        "trait_contains": DONQ,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
            {
                "timing": "when_attacking",
                "summary": "DON!!−1: up to 1 opp Character −2000 this turn",
                "ops": [
                    {
                        "op": "return_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                    },
                    {
                        "op": "buff",
                        "amount": -2000,
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

    # OP14-068 — only on_don_returned during opponent's turn (drop bogus opponent_turn gain).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-068",
        [
            {
                "timing": "on_don_returned",
                "summary": "Opp turn once: when DON!! returned, if Leader Donquixote, add up to 1 rested DON!!",
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
                "once": True,
                "require_leader_trait": DONQ,
                "require_opponent_turn": True,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-071",
        [
            {
                "timing": "end_of_your_turn",
                "summary": "If Leader Donquixote: add up to 1 active DON!!",
                "ops": [{"op": "gain_don", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": DONQ,
            },
        ],
    )

    # OP14-074 — on play is ACTIVE DON!! (not rested).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-074",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Donquixote: add up to 1 active DON!!",
                "ops": [{"op": "gain_don", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": DONQ,
            },
            {
                "timing": "on_ko",
                "summary": "Draw 2, trash 1; Then add up to 2 rested DON!!",
                "ops": [
                    {"op": "draw", "count": 2},
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": False,
                        "owner": "self",
                    },
                    {
                        "op": "gain_don",
                        "count": 2,
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
        "OP10-071",
        [
            {
                "timing": "on_play",
                "summary": "DON!!−1: play up to 1 Donquixote Character cost≤5 from hand",
                "ops": [
                    {
                        "op": "return_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "trait_contains": DONQ,
                        "from_zone": "hand",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_opponent_attack",
                "summary": "Once: you may rest 1 DON!!: add up to 1 active DON!!",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {"op": "gain_don", "count": 1, "optional": True},
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
        "OP14-069",
        [
            {
                "timing": "on_play",
                "summary": "DON!!−3: choose one (KO cost≤8 if Leader Donquixote / deny_rest ×3 cost≤7)",
                "ops": [
                    {
                        "op": "return_don",
                        "count": 3,
                        "owner": "self",
                        "as_cost": True,
                    },
                    {
                        "op": "choose_one",
                        "chooser": "self",
                        "options": [
                            {
                                "id": "opt0",
                                "label": "If Leader Donquixote: KO up to 1 opp Character cost≤8",
                                "ops": [
                                    {
                                        "op": "ko",
                                        "target_kind": "opponent_character",
                                        "optional": True,
                                        "count": 1,
                                        "cost_lte": 8,
                                    }
                                ],
                                "require_leader_trait": DONQ,
                            },
                            {
                                "id": "opt1",
                                "label": "Up to 3 opp Characters cost≤7 cannot be rested until opp end",
                                "ops": [
                                    {
                                        "op": "deny_rest",
                                        "count": 3,
                                        "optional": True,
                                        "target_kind": "opponent_character",
                                        "cost_lte": 7,
                                        "duration": "until_opp_turn_end",
                                    }
                                ],
                            },
                        ],
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

    search_078 = {
        "op": "search_deck",
        "name_contains": "",
        "trait_contains": DONQ,
        "top_n": 3,
        "max_add": 1,
        "order_bottom": True,
        "destination": "hand",
        "exclude_name": EXCLUDE_078,
        "reveal_adds": True,
    }
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-078",
        [
            {
                "timing": "on_play",
                "summary": "Look top 3; add up to 1 Donquixote other than this event",
                "ops": [dict(search_078)],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "Look top 3; add up to 1 Donquixote other than this event",
                "ops": [dict(search_078)],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-076",
        [
            {
                "timing": "counter_event",
                "summary": "DON!!−1: up to 1 own Leader/Character +2000; Then rest up to 1 opp Character",
                "ops": [
                    {
                        "op": "return_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                    },
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    },
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Add up to 1 active DON!!",
                "ops": [{"op": "gain_don", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Soft-fix: on_play 「活動狀態的咚」 wrongly encoded as_rested.
    for cid, entry in list(ov_cards.items()):
        info = catalog.get(cid) or {}
        zh = str(info.get("effect") or "")
        if "登場時" not in zh or "活動狀態的咚" not in zh:
            continue
        if "登場時" in zh and "休息狀態的咚" in zh:
            # Mixed card (e.g. Monet): only strip as_rested on on_play.
            pass
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            if ab.get("timing") != "on_play":
                abs_out.append(ab)
                continue
            ops = []
            for o in ab.get("ops") or []:
                o = dict(o)
                if o.get("op") == "gain_don" and o.get("as_rested"):
                    # Only if paper on-play clause is 活動 (not 休息).
                    # Heuristic: first 登場時 chunk before next 【.
                    chunk = zh.split("【登場時】", 1)[-1].split("【", 1)[0]
                    if "活動狀態的咚" in chunk and "休息狀態的咚" not in chunk:
                        o.pop("as_rested", None)
                        changed = True
                ops.append(o)
            ab["ops"] = ops
            abs_out.append(ab)
        if changed:
            entry2 = normalize_card_entry(
                cid, {"version": int(entry.get("version") or 1), "abilities": abs_out}
            )
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_at updated {n} card entries")


if __name__ == "__main__":
    main()
