"""EB05-046 Stinger Hedgehog: rest DON + KO own B・W → deny Blocker on opp cost 0 this turn; Counter Leader +3000."""

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
from battle.effects import has_counter_timing  # noqa: E402
from battle.engine import _blocker_denied, apply_action, inst_power  # noqa: E402
from battle.state import CardInst, MatchState, PendingAttack, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "BW": {
            "card_id": "BW",
            "card_type": "CHARACTER",
            "cost": 2,
            "power": 3000,
            "name": "Monday",
            "traits": ["B・W"],
            "keywords": ["blocker"],
        },
        "NOBW": {
            "card_id": "NOBW",
            "card_type": "CHARACTER",
            "cost": 2,
            "power": 3000,
            "name": "Other",
            "traits": ["草帽一行人"],
        },
        "C0": {
            "card_id": "C0",
            "card_type": "CHARACTER",
            "cost": 0,
            "power": 1000,
            "name": "Zero",
            "keywords": ["blocker"],
        },
        "C1": {
            "card_id": "C1",
            "card_type": "CHARACTER",
            "cost": 1,
            "power": 2000,
            "name": "One",
            "keywords": ["blocker"],
        },
        "OP02-093": {"card_id": "OP02-093", "card_type": "LEADER", "power": 5000, "name": "Crocodile", "colors": ["黑"]},
        "OP01-001": {"card_id": "OP01-001", "card_type": "LEADER", "power": 5000, "name": "Luffy"},
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _main_state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP02-093",
        deck=["X"] * 20,
        hand=["EB05-046"],
        life=["L"] * 5,
        don_active=3,
        don_given=3,
        turns_completed=1,
        characters=[
            CardInst(iid="bw", card_id="BW", rested=False, summoning_sick=False),
            CardInst(iid="nobw", card_id="NOBW", rested=False, summoning_sick=False),
        ],
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["Y"] * 20,
        hand=[],
        life=["M"] * 5,
        characters=[
            CardInst(iid="c0", card_id="C0", rested=False, summoning_sick=False, keywords=["blocker"]),
            CardInst(iid="c1", card_id="C1", rested=False, summoning_sick=False, keywords=["blocker"]),
        ],
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


def _confirm_if_needed(st: MatchState) -> None:
    if st.pending_effect is not None:
        assert apply_action(st, 0, {"type": "confirm_effect", "accept": True}, catalog)["ok"]


def test_eb05_046_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-046")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-046 abilities dropped on normalize"
    main = next(a for a in get_abilities("EB05-046", "on_play"))
    assert main["ops"][0].get("op") == "rest_don"
    assert main["ops"][0].get("as_cost") is True
    assert main["ops"][1].get("op") == "ko"
    assert main["ops"][1].get("target_kind") == "own_character"
    assert main["ops"][1].get("as_cost") is True
    assert "B・W" in str(main["ops"][1].get("trait_contains") or "")
    deny = main["ops"][2]
    assert deny.get("op") == "deny_blocker"
    assert deny.get("duration") == "turn"
    assert deny.get("cost_eq") == 0
    ctr = next(a for a in get_abilities("EB05-046", "counter_event"))
    assert ctr["ops"][0].get("op") == "buff"
    assert ctr["ops"][0].get("amount") == 3000
    info = catalog("EB05-046")
    assert has_counter_timing(info) is True


def test_eb05_046_main_denies_cost0_blocker():
    reload_effect_library(force=True)
    st = _main_state()
    don_before = st.players[0].don_active
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _confirm_if_needed(st)
    # rest DON (may auto-pay)
    while st.pending_choice is not None and any(
        str(o).startswith("don:") or str(o) == "don" for o in (st.pending_choice.options or [])
    ):
        tid = st.pending_choice.options[0]
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": tid}, catalog)["ok"]
    assert st.pending_choice is not None
    opts = st.pending_choice.options or []
    assert "bw" in opts
    assert "nobw" not in opts
    assert "c0" not in opts
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "bw"}, catalog)["ok"]
    assert st.pending_choice is None
    assert "BW" in st.players[0].trash
    assert not any(c.iid == "bw" for c in st.players[0].characters)
    assert st.players[0].don_active == don_before - 1 - 1  # play 1 + rest 1
    assert st.players[0].deny_blocker
    c0 = next(c for c in st.players[1].characters if c.iid == "c0")
    c1 = next(c for c in st.players[1].characters if c.iid == "c1")
    assert _blocker_denied(st, 0, c0, catalog) is True
    assert _blocker_denied(st, 0, c1, catalog) is False


def test_eb05_046_skip_cost_does_not_deny():
    reload_effect_library(force=True)
    st = _main_state()
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _confirm_if_needed(st)
    while st.pending_choice is not None:
        assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
        _confirm_if_needed(st)
        if st.pending_choice is None:
            break
    assert any(c.iid == "bw" for c in st.players[0].characters)
    assert not st.players[0].deny_blocker


def test_eb05_046_counter_leader_plus_3000():
    reload_effect_library(force=True)
    st = _main_state()
    st.phase = "counter"
    st.turn_seat = 1
    st.attack = PendingAttack(
        attacker_seat=1,
        attacker_iid="leader",
        target_iid="leader",
        declared_power=5000,
        combat_entered=True,
    )
    before = inst_power(st, 0, "leader", catalog)
    assert apply_action(st, 0, {"type": "counter", "hand_index": 0}, catalog)["ok"]
    assert inst_power(st, 0, "leader", catalog) == before + 3000
    assert apply_action(st, 0, {"type": "pass_counter"}, catalog)["ok"]
    assert inst_power(st, 0, "leader", catalog) == before
