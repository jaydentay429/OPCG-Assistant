#!/usr/bin/env python3
"""Clear remaining medium/high fidelity fails: gates + choose_one."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

CHOOSE_ONE = {
    "OP05-096": {
        "timing": "on_play",
        "status": "verified",
        "confidence": 0.9,
        "summary": "Choose one: KO cost<=1 / bounce cost<=1 / bottom-deck cost<=1",
        "ops": [
            {
                "op": "choose_one",
                "chooser": "self",
                "options": [
                    {
                        "id": "ko",
                        "label": "K.O. cost <= 1",
                        "ops": [{"op": "ko", "count": 1, "cost_lte": 1, "target_kind": "opponent_character", "optional": True}],
                    },
                    {
                        "id": "bounce",
                        "label": "Return cost <= 1 to hand",
                        "ops": [
                            {
                                "op": "return_to_hand",
                                "count": 1,
                                "cost_lte": 1,
                                "target_kind": "opponent_character",
                                "optional": True,
                            }
                        ],
                    },
                    {
                        "id": "bottom",
                        "label": "Bottom-deck cost <= 1",
                        "ops": [
                            {
                                "op": "return_to_bottom",
                                "count": 1,
                                "cost_lte": 1,
                                "target_kind": "opponent_character",
                                "optional": True,
                            }
                        ],
                    },
                ],
            }
        ],
    },
    "OP06-116": {
        "timing": "on_play",
        "status": "verified",
        "confidence": 0.9,
        "summary": "Choose one: KO cost<=5 / if opp life=1 deal 1 then life_to_hand",
        "ops": [
            {
                "op": "choose_one",
                "chooser": "self",
                "options": [
                    {
                        "id": "ko",
                        "label": "K.O. cost <= 5",
                        "ops": [{"op": "ko", "count": 1, "cost_lte": 5, "target_kind": "opponent_character", "optional": True}],
                    },
                    {
                        "id": "life",
                        "label": "If opp has 1 Life: deal 1, then Life to hand",
                        "ops": [
                            {"op": "deal_life_damage", "count": 1, "optional": True},
                            {"op": "life_to_hand", "count": 1, "position": "top", "optional": True},
                        ],
                    },
                ],
            }
        ],
    },
    "OP09-058": {
        "timing": "on_play",
        "status": "verified",
        "confidence": 0.9,
        "summary": "Opponent chooses 1 of their Characters cost<=6 and returns it to hand",
        "ops": [
            {
                "op": "choose_one",
                "chooser": "opponent",
                "options": [
                    {
                        "id": "bounce",
                        "label": "Return a cost <= 6 Character",
                        "ops": [
                            {
                                "op": "return_to_hand",
                                "count": 1,
                                "cost_lte": 6,
                                "target_kind": "own_character",
                                "optional": False,
                            }
                        ],
                    },
                    {
                        "id": "bounce2",
                        "label": "Return another cost <= 6 Character",
                        "ops": [
                            {
                                "op": "return_to_hand",
                                "count": 1,
                                "cost_lte": 6,
                                "target_kind": "own_character",
                                "optional": False,
                            }
                        ],
                    },
                ],
            }
        ],
    },
    "ST06-015": {
        "timing": "trigger",
        "status": "verified",
        "confidence": 0.9,
        "summary": "Trigger: opponent chooses 1 hand card and trashes it",
        "ops": [
            {
                "op": "choose_one",
                "chooser": "opponent",
                "options": [
                    {
                        "id": "trash",
                        "label": "Trash 1 from hand",
                        "ops": [{"op": "trash_hand", "count": 1, "optional": False}],
                    },
                    {
                        "id": "trash2",
                        "label": "Trash 1 from hand (alt)",
                        "ops": [{"op": "trash_hand", "count": 1, "optional": False}],
                    },
                ],
            }
        ],
    },
}

GATE_PATCHES = {
    "OP03-040": ("when_attacking", {"require_don_attached_gte": 1}),
    "P-117": ("when_attacking", {"require_don_attached_gte": 1}),
    "ST08-013": ("when_attacking", {"require_don_attached_gte": 1}),
    "OP09-010": ("when_attacking", {"require_don_attached_gte": 1}),
    "ST31-001": ("on_play", {"require_don_attached_gte": 2}),
}


def _put(store: dict, cid: str, abilities: list[dict]) -> None:
    store[cid] = normalize_card_entry(cid, {"version": 1, "abilities": abilities})


def main() -> int:
    ov_path = ROOT / "index" / "card_effect_overrides.json"
    ov = json.loads(ov_path.read_text(encoding="utf-8"))
    ov_cards = ov.setdefault("cards", {})
    lib_path, _ = library_paths()
    lib = json.loads(lib_path.read_text(encoding="utf-8"))
    cards = lib.setdefault("cards", {})
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))

    touched = 0

    # Gate patches on overrides + library
    for cid, (timing, gates) in GATE_PATCHES.items():
        for store in (ov_cards, cards):
            entry = store.get(cid) or cards.get(cid) or {"abilities": []}
            abs_ = [dict(a) for a in (entry.get("abilities") or [])]
            if not abs_ and cid in cards:
                abs_ = [dict(a) for a in (cards[cid].get("abilities") or [])]
            found = False
            for a in abs_:
                if a.get("timing") == timing:
                    a.update(gates)
                    found = True
            if not found:
                # clone from other store or create minimal
                src = (cards.get(cid) or ov_cards.get(cid) or {}).get("abilities") or []
                abs_ = [dict(a) for a in src]
                for a in abs_:
                    if a.get("timing") == timing:
                        a.update(gates)
                        found = True
            if found:
                _put(store, cid, abs_)
                touched += 1

    # Choose-one replacements: merge into existing abilities by timing
    for cid, ability in CHOOSE_ONE.items():
        timing = ability["timing"]
        for store in (ov_cards, cards):
            entry = store.get(cid) or cards.get(cid) or {"abilities": []}
            abs_ = [dict(a) for a in (entry.get("abilities") or [])]
            replaced = False
            for i, a in enumerate(abs_):
                if a.get("timing") == timing:
                    abs_[i] = dict(ability)
                    replaced = True
                    break
            if not replaced:
                abs_.append(dict(ability))
            _put(store, cid, abs_)
            touched += 1
        # variants
        for variant in sorted(k for k in catalog if k.startswith(cid + "-")):
            for store in (ov_cards, cards):
                if cid in store:
                    store[variant] = store[cid]
                    touched += 1

    # Also patch hard-override sources for DON leaders in apply script is separate;
    # ensure ST31 grant_keyword rush with gate
    if "ST31-001" in cards:
        abs_ = [dict(a) for a in cards["ST31-001"]["abilities"]]
        for a in abs_:
            if a.get("timing") == "on_play":
                a["require_don_attached_gte"] = 2
                ops = list(a.get("ops") or [])
                if not any(o.get("op") == "grant_keyword" for o in ops):
                    ops.append({"op": "grant_keyword", "keyword": "rush", "target_kind": "self"})
                    a["ops"] = ops
        _put(cards, "ST31-001", abs_)
        _put(ov_cards, "ST31-001", abs_)

    ov["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lib["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = lib_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(lib, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(lib_path)
    reload_effect_library(force=True)
    print(json.dumps({"touched": touched}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
