#!/usr/bin/env python3
"""Retag Event [Main] as on_play; drop duplicate cost_don+rest_don; fix Queen/Kaido."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402

AKP = "Animal Kingdom Pirates|百獸海賊團|百兽海贼团"


def _is_event(info: dict) -> bool:
    blob = " ".join(str(info.get(k) or "") for k in ("card_type", "type", "category")).lower()
    return "event" in blob or "事件" in blob


def main() -> int:
    ov_path = ROOT / "index" / "card_effect_overrides.json"
    ov = json.loads(ov_path.read_text(encoding="utf-8"))
    ov_cards = ov.setdefault("cards", {})
    lib_path, _ = library_paths()
    lib = json.loads(lib_path.read_text(encoding="utf-8"))
    cards = lib.setdefault("cards", {})
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))

    n_main = n_cost = 0
    touched: set[str] = set()
    for cid, entry in ov_cards.items():
        info = catalog.get(cid) or {}
        changed = False
        for a in entry.get("abilities") or []:
            if a.get("timing") == "main_start" and _is_event(info):
                a["timing"] = "on_play"
                n_main += 1
                changed = True
            ops = a.get("ops") or []
            if int(a.get("cost_don") or 0) > 0 and any(
                isinstance(o, dict) and o.get("op") == "rest_don" and o.get("as_cost") for o in ops
            ):
                a["cost_don"] = 0
                n_cost += 1
                changed = True
        if cid == "EB04-032" or cid.startswith("EB04-032-"):
            for a in entry.get("abilities") or []:
                if a.get("timing") == "activate_main":
                    a["cost_don"] = 0
                    a["require_leader_trait"] = AKP
                    for o in a.get("ops") or []:
                        if o.get("op") == "rest_don" and o.get("as_cost"):
                            o["optional"] = True
                        if o.get("op") == "gain_don":
                            o["optional"] = True
                            o["as_rested"] = True
                if a.get("timing") == "on_play":
                    for o in a.get("ops") or []:
                        if o.get("op") == "trash_hand":
                            o["trait_contains"] = AKP
            changed = True
        if cid == "OP17-058" or cid.startswith("OP17-058-"):
            for a in entry.get("abilities") or []:
                if a.get("timing") in {"when_attacking", "on_opponent_attack"}:
                    a["optional"] = True
                    a["may_activate"] = True
            changed = True
        if changed:
            touched.add(cid)
            packed = dict(entry)
            packed["card_id"] = cid
            ov_cards[cid] = packed
            cards[cid] = packed

    ov["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lib["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = lib_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(lib, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(lib_path)
    reload_effect_library(force=True)
    print(f"event main_start→on_play: {n_main}, dropped duplicate cost_don: {n_cost}, cards: {len(touched)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
