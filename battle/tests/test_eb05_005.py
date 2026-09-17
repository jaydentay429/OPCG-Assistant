"""EB05-005 Belo Betty: On Play +2000 to RA+Trigger; Activate trash self, opp −2000."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if "battle" not in sys.modules:
    pkg = types.ModuleType("battle")
    pkg.__path__ = [str(ROOT / "battle")]
    sys.modules["battle"] = pkg

from battle.effect_library import get_abilities, get_card_entry, reload_effect_library  # noqa: E402
from battle.engine import apply_action  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000, "traits": []}


def _state(*, hand: list[str] | None = None, field: list[tuple[str, str]] | None = None) -> MatchState:
    chars = [
        CardInst(iid=iid, card_id=cid, rested=False, summoning_sick=False)
        for iid, cid in (field or [])
    ]
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP05-002",
        deck=["D"] * 20,
        hand=list(hand or []),
        life=["L"] * 5,
        don_active=5,
        don_given=5,
        turns_completed=1,
        characters=chars,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["B"] * 20,
        hand=[],
        life=["M"] * 5,
        characters=[CardInst(iid="opp", card_id="OP01-016", rested=False, summoning_sick=False)],
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def test_eb05_005_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-005")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert len(abs_) >= 2, "EB05-005 abilities dropped on normalize"
    on_play = next(a for a in get_abilities("EB05-005", "on_play"))
    buffs = [o for o in on_play["ops"] if o.get("op") == "buff"]
    assert len(buffs) == 3
    for op in buffs:
        assert op.get("amount") == 2000
        assert op.get("optional") is True
        assert op.get("require_trigger") is True
        assert "革命軍" in str(op.get("trait_contains") or "") or "Revolutionary" in str(
            op.get("trait_contains") or ""
        )
        assert op.get("target_kind") == "own_character"
        assert op.get("duration") == "turn"
    act = next(a for a in get_abilities("EB05-005", "activate_main"))
    assert act["ops"][0].get("op") == "trash"
    assert act["ops"][0].get("target_kind") == "self"
    assert act["ops"][0].get("as_cost") is True
    assert act["ops"][1].get("op") == "buff"
    assert act["ops"][1].get("amount") == -2000
    assert act["ops"][1].get("target_kind") == "opponent_character"


def test_eb05_005_on_play_buffs_only_ra_with_trigger():
    reload_effect_library(force=True)
    # OP05-011 / EB05-051: RA + Trigger; OP05-006: RA no Trigger; EB05-054: Trigger, not RA.
    st = _state(
        hand=["EB05-005"],
        field=[
            ("ra_t1", "OP05-011"),
            ("ra_t2", "EB05-051"),
            ("ra_no", "OP05-006"),
            ("trig", "EB05-054"),
        ],
    )
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-005" for c in st.players[0].characters)
    assert st.pending_choice is not None
    opts = set(st.pending_choice.options or [])
    assert "ra_t1" in opts
    assert "ra_t2" in opts
    assert "ra_no" not in opts
    assert "trig" not in opts
    betty = next(c for c in st.players[0].characters if c.card_id == "EB05-005")
    assert betty.iid not in opts
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "ra_t1"}, catalog)["ok"]
    if st.pending_choice is not None:
        opts2 = set(st.pending_choice.options or [])
        assert "ra_t1" not in opts2
        assert "ra_t2" in opts2
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": "ra_t2"}, catalog)["ok"]
    if st.pending_choice is not None:
        assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    by_iid = {c.iid: c for c in st.players[0].characters}
    assert by_iid["ra_t1"].power_mod == 2000
    assert by_iid["ra_t2"].power_mod == 2000
    assert by_iid["ra_no"].power_mod == 0
    assert by_iid["trig"].power_mod == 0


def test_eb05_005_activate_trashes_self_and_debuffs_opp():
    reload_effect_library(force=True)
    st = _state(field=[("betty", "EB05-005")])
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "betty"}, catalog)["ok"]
    # Optional trash-self cost: confirm this Character, then pick the −2000 target.
    assert st.pending_choice is not None
    assert "betty" in (st.pending_choice.options or [])
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "betty"}, catalog)["ok"]
    assert "EB05-005" in st.players[0].trash
    assert not any(c.iid == "betty" for c in st.players[0].characters)
    assert st.pending_choice is not None
    assert "opp" in (st.pending_choice.options or [])
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "opp"}, catalog)["ok"]
    opp = next(c for c in st.players[1].characters if c.iid == "opp")
    assert opp.power_mod == -2000


if __name__ == "__main__":
    test_eb05_005_override_shape()
    test_eb05_005_on_play_buffs_only_ra_with_trigger()
    test_eb05_005_activate_trashes_self_and_debuffs_opp()
    print("OK")
