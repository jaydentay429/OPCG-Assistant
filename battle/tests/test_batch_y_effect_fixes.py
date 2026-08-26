"""Batch-Y effect encoding fixes (Zoro/Slash, Kaido opp-DON, Kin'emon)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import _begin_turn  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def setup_module() -> None:
    reload_effect_library()


def catalog(cid: str):
    return dict(_CARDS.get(cid) or {"cost": 1, "name": cid, "power": 5000})


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.pop("leader0", "OP12-020"),
        deck=["X"] * 30,
        hand=kwargs.pop("hand0", []),
        life=kwargs.pop("life0", ["L"] * 5),
        characters=kwargs.pop("chars0", []),
        don_rested=kwargs.pop("don_rested", 0),
        don_active=kwargs.pop("don_active", 0),
        leader_don=kwargs.pop("leader_don", 0),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id=kwargs.pop("leader1", "OP01-001"),
        deck=["Y"] * 30,
        hand=kwargs.pop("hand1", []),
        life=kwargs.pop("life1", ["M"] * 5),
        characters=kwargs.pop("chars1", []),
        don_rested=kwargs.pop("don_rested1", 0),
        don_active=kwargs.pop("don_active1", 0),
        leader_rested=kwargs.pop("leader_rested1", False),
    )
    return MatchState(
        room_code="Y",
        status="playing",
        phase="main",
        turn_seat=kwargs.pop("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def test_op12_031_attach_zoro_leader_base_cost() -> None:
    ops = get_card_entry("OP12-031")["abilities"][0]["ops"]
    assert ops[0].get("base_cost_lte") == 6
    assert ops[1]["op"] == "attach_don"
    assert ops[1].get("target_kind") == "leader"
    assert "Zoro" in str(ops[1].get("name_contains") or "") or "索隆" in str(ops[1].get("name_contains") or "")


def test_op15_023_ko_and_activate() -> None:
    abs_ = get_card_entry("OP15-023")["abilities"]
    ko = next(a for a in abs_ if a["timing"] == "on_ko")
    assert ko.get("once") is not True
    skip = ko["ops"][0]
    assert skip.get("include_don") and skip.get("include_leader") and skip.get("include_stage")
    act = next(a for a in abs_ if a["timing"] == "activate_main")
    assert act["ops"][0].get("from_owner") == "opponent"
    assert act["ops"][0].get("target_kind") == "opponent_character"
    assert act["ops"][1].get("target_kind") == "opponent_leader_or_character"


def test_op15_003_017_same_activate() -> None:
    for cid in ("OP15-003", "OP15-017"):
        act = next(a for a in get_card_entry(cid)["abilities"] if a["timing"] == "activate_main")
        assert act["ops"][0].get("from_owner") == "opponent"
        assert act["ops"][1].get("target_kind") == "opponent_leader_or_character"


def test_st32_001_choose_leader_or_don() -> None:
    ops = get_card_entry("ST32-001")["abilities"][0]["ops"]
    assert ops[0]["op"] == "choose_one"
    assert ops[0].get("as_cost") and ops[0].get("optional")
    ids = {o["id"] for o in ops[0]["options"]}
    assert ids == {"leader", "don"}


def test_st32_002_base_cost_deny_rest() -> None:
    op = get_card_entry("ST32-002")["abilities"][0]["ops"][1]
    assert op["op"] == "deny_rest"
    assert op.get("base_cost_lte") == 6


def test_eb01_012_cavendish_bilingual() -> None:
    a = get_card_entry("EB01-012")["abilities"][0]
    assert "Cavendish" in str(a.get("require_no_other_name") or "")
    assert "超新星" in str(a.get("require_leader_trait") or "") or "Supernovas" in str(
        a.get("require_leader_trait") or ""
    )


def test_attach_don_from_opponent_runtime() -> None:
    st = _state(
        chars1=[CardInst(iid="oc1", card_id="OP01-016", rested=False)],
        don_rested1=3,
    )
    p0, p1 = st.player(0), st.player(1)
    apply_ops(
        st,
        0,
        [
            {
                "op": "attach_don",
                "count": 1,
                "from_rested": True,
                "as_rested": True,
                "from_owner": "opponent",
                "target_kind": "opponent_character",
                "target_iid": "oc1",
            }
        ],
        catalog,
    )
    assert p1.don_rested == 2
    assert p1.characters[0].don_attached == 1
    assert p0.don_rested == 0


def test_skip_untap_don_survives_refresh() -> None:
    st = _state(don_rested1=4, leader_rested1=True)
    p1 = st.player(1)
    apply_ops(
        st,
        0,
        [
            {
                "op": "skip_untap",
                "count": 1,
                "target_kind": "opponent_character_rested",
                "include_leader": True,
                "include_don": True,
                "include_stage": True,
                "target_iid": "don",
            },
            {
                "op": "skip_untap",
                "count": 1,
                "target_kind": "opponent_character_rested",
                "include_leader": True,
                "include_don": True,
                "target_iid": "leader",
            },
        ],
        catalog,
    )
    assert p1.skip_untap_don >= 1
    assert p1.leader_skip_untap is True
    _begin_turn(st, 1, catalog)
    assert p1.leader_rested is True
    assert p1.don_rested >= 1


def test_op12_028_requires_zoro_leader() -> None:
    act = get_card_entry("OP12-028")["abilities"][0]
    assert "Zoro" in str(act.get("require_leader_name") or "") or "索隆" in str(
        act.get("require_leader_name") or ""
    )


if __name__ == "__main__":
    setup_module()
    # re-apply encodings so base_cost_lte is present
    from scripts.fix_batch_y_effects import main as fix_main

    fix_main()
    reload_effect_library()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
