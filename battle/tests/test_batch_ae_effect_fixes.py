"""Batch-AE effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import detect_keywords, has_blocker  # noqa: E402
from battle.leave_replace import _pay_replace_cost, _replace_cost_payable  # noqa: E402
from battle.state import CardInst, PlayerState  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_op15_039_cannot_attack_not_deny() -> None:
    abs_ = get_card_entry("OP15-039")["abilities"]
    cont = [a for a in abs_ if a["timing"] in ("your_turn", "opponent_turn")]
    assert len(cont) == 2
    for a in cont:
        assert a["ops"][0]["op"] == "cannot_attack"
        assert a["ops"][0].get("target_kind") == "leader"
    act = next(a for a in abs_ if a["timing"] == "activate_main")
    assert act.get("rest_self") is True
    assert "多雷斯羅薩" in str(act["ops"][0].get("trait_contains") or "")
    assert act["ops"][1].get("cost_eq") == 3


def test_op15_040_053_dressrosa_search() -> None:
    for cid in ("OP15-040", "OP15-053"):
        op = next(a for a in get_card_entry(cid)["abilities"] if a["timing"] == "on_play")["ops"][0]
        assert "Dressrosa" in str(op.get("trait_contains") or "")
        assert "多雷斯羅薩" in str(op.get("trait_contains") or "")
        assert op.get("destination") == "hand"
        assert op.get("reveal_adds") is True


def test_op15_052_return_own_to_bottom() -> None:
    op = get_card_entry("OP15-052")["abilities"][0]["ops"][0]
    assert op["op"] == "replace_leave"
    assert op.get("cost") == "return_own_to_bottom"
    assert op.get("base_power_lte") == 7000

    owner = PlayerState(seat=0, user_id="t", username="t", is_ai=False, leader_card_id="OP15-039")
    leo = CardInst(iid="leo1", card_id="OP15-052")
    owner.characters = [leo]
    pay = {"op": "replace_leave", "cost": "return_own_to_bottom"}
    assert _replace_cost_payable(owner, pay, leo, catalog=lambda _c: {}) is True
    assert _pay_replace_cost(owner, pay, leo, catalog=lambda _c: {}, target_iid="leo1") is True
    assert owner.characters == []
    assert owner.deck[-1] == "OP15-052"


def test_op15_042_rebecca_bilingual() -> None:
    ab = next(a for a in get_card_entry("OP15-042")["abilities"] if a["timing"] == "on_play")
    assert "Rebecca" in str(ab.get("require_leader_name") or "")
    assert "蕾貝卡" in str(ab.get("require_leader_name") or "")
    assert ab["ops"][0].get("as_cost") is True


def test_op15_047_no_bogus_on_block() -> None:
    abs_ = get_card_entry("OP15-047")["abilities"]
    assert not any(a.get("timing") == "on_block" for a in abs_)
    assert abs_[0]["ops"][0].get("keyword") == "blockerless"
    # Innate Blocker still detected from paper text.
    import json

    cards = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    assert "blocker" in detect_keywords(cards["OP15-047"])
    assert has_blocker(cards["OP15-047"]) is True


def test_op15_051_dressrosa_leader_gate() -> None:
    ab = get_card_entry("OP15-051")["abilities"][0]
    assert ab["timing"] == "opponent_turn"
    assert "多雷斯羅薩" in str(ab.get("require_leader_trait") or "")
    assert ab["ops"][0].get("amount") == 3000


def test_op07_051_exclude_luffy() -> None:
    ops = get_card_entry("OP07-051")["abilities"][0]["ops"]
    assert "Luffy" in str(ops[0].get("exclude_name") or "") or "魯夫" in str(ops[0].get("exclude_name") or "")
    assert ops[1]["op"] == "return_to_bottom" and ops[1].get("cost_lte") == 1


def test_similar_bogus_on_block_stripped() -> None:
    for cid in ("ST15-003", "OP05-066", "OP16-083", "OP12-021", "OP14-070"):
        entry = get_card_entry(cid)
        if not entry:
            continue
        for a in entry.get("abilities") or []:
            if a.get("timing") != "on_block":
                continue
            ops = a.get("ops") or []
            assert not (
                len(ops) == 1
                and ops[0].get("op") == "grant_keyword"
                and ops[0].get("keyword") == "blocker"
                and ops[0].get("target_kind") == "self"
            ), cid


if __name__ == "__main__":
    setup_module()
    test_op15_039_cannot_attack_not_deny()
    test_op15_040_053_dressrosa_search()
    test_op15_052_return_own_to_bottom()
    test_op15_042_rebecca_bilingual()
    test_op15_047_no_bogus_on_block()
    test_op15_051_dressrosa_leader_gate()
    test_op07_051_exclude_luffy()
    test_similar_bogus_on_block_stripped()
    print("ok")
