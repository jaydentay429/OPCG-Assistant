"""Batch-W effect encoding + treated-as names."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import _card_matches_name_contains, _treated_as_names  # noqa: E402
from battle.engine import _activate_don_cost_to_spend  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def setup_module() -> None:
    reload_effect_library()


def catalog(cid: str):
    return dict(_CARDS.get(cid) or {"cost": 1, "name": cid})


def test_eb04_038_treated_as_law() -> None:
    info = catalog("EB04-038")
    names = _treated_as_names(info)
    assert any("托拉法爾加" in n or "Trafalgar" in n for n in names)
    assert any("羅希南特" in n or "Rosinante" in n for n in names)
    assert _card_matches_name_contains(info, "Trafalgar Law|托拉法爾加・羅") is True


def test_eb04_059_deficit_on_ko_not_ability() -> None:
    play = next(a for a in get_card_entry("EB04-059")["abilities"] if a["timing"] == "on_play")
    assert play.get("require_chars_deficit_gte") is None
    kos = [o for o in play["ops"] if o["op"] == "ko"]
    assert len(kos) == 2
    assert all(o.get("require_chars_deficit_gte") == 1 for o in kos)


def test_op16_065_navy_on_gain_don() -> None:
    act = next(a for a in get_card_entry("OP16-065")["abilities"] if a["timing"] == "activate_main")
    assert act.get("require_leader_trait") is None
    gain = next(o for o in act["ops"] if o["op"] == "gain_don")
    assert "Navy" in str(gain.get("require_leader_trait") or "")


def test_op16_067_trash_after_search() -> None:
    ops = get_card_entry("OP16-067")["abilities"][0]["ops"]
    assert [o["op"] for o in ops] == ["search_deck", "trash_hand"]


def test_op16_078_no_double_don_cost() -> None:
    act = next(a for a in get_card_entry("OP16-078")["abilities"] if a["timing"] == "activate_main")
    assert act.get("rest_self") is True
    assert act.get("cost_don") in (0, None)
    assert any(o.get("op") == "return_don" and o.get("as_cost") for o in act["ops"])
    assert _activate_don_cost_to_spend(act) == 0


def test_st10_010_hand_gate_on_trash() -> None:
    play = get_card_entry("ST10-010")["abilities"]
    assert len(play) == 1
    assert play[0].get("require_opp_hand_gte") is None
    trash = play[0]["ops"][1]
    assert trash.get("require_opp_hand_gte") == 7
    assert trash.get("owner") == "opponent"


def test_op12_108_law_bilingual() -> None:
    op = get_card_entry("OP12-108")["abilities"][0]["ops"][0]
    assert "托拉法爾加" in str(op.get("name_contains") or "")


def test_op13_086_p1_has_trash_hand() -> None:
    ops = get_card_entry("OP13-086-P1")["abilities"][0]["ops"]
    assert any(o.get("op") == "trash_hand" for o in ops)


if __name__ == "__main__":
    setup_module()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
