"""EB05-007 Monet: On Play may reveal 3 Event|{Punk Hazard} then draw 1; EoT +5000 until opp End."""

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
from battle.engine import apply_action, inst_power  # noqa: E402
from battle.state import MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "EV1": {"card_id": "EV1", "card_type": "Event", "cost": 1, "name": "EV1"},
        "EV2": {"card_id": "EV2", "card_type": "Event", "cost": 1, "name": "EV2"},
        "EV3": {"card_id": "EV3", "card_type": "Event", "cost": 1, "name": "EV3"},
        "PH1": {
            "card_id": "PH1",
            "card_type": "Character",
            "cost": 1,
            "power": 2000,
            "name": "PH1",
            "traits": ["龐克哈薩特"],
            "traits_en": ["Punk Hazard"],
        },
        "JUNK": {
            "card_id": "JUNK",
            "card_type": "Character",
            "cost": 1,
            "power": 1000,
            "name": "JUNK",
            "traits": ["海軍"],
            "traits_en": ["Navy"],
        },
        "D0": {"card_id": "D0", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "D0"},
        "D1": {"card_id": "D1", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "D1"},
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, hand: list[str]) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP14-060",
        deck=["D0", "D1"] + ["X"] * 18,
        hand=list(hand),
        life=["L"] * 5,
        don_active=2,
        don_given=2,
        turns_completed=1,
        leader_rested=False,
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


def _finish_reveals(st: MatchState, n: int = 3) -> None:
    for _ in range(n):
        assert st.pending_choice is not None
        tid = (st.pending_choice.options or [None])[0]
        assert tid
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": tid}, catalog)["ok"]


def test_eb05_007_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-007")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-007 abilities dropped on normalize"
    timings = {a.get("timing") for a in abs_}
    assert "on_play" in timings
    assert "end_of_your_turn" in timings
    play = next(a for a in get_abilities("EB05-007", "on_play"))
    reveal, draw = play["ops"]
    assert reveal.get("op") == "reveal_hand"
    assert reveal.get("count") == 3
    assert reveal.get("as_cost") is True
    assert reveal.get("optional") is True
    assert reveal.get("card_type") == "event"
    assert reveal.get("type_or_trait") is True
    trait = str(reveal.get("trait_contains") or "")
    assert "Punk Hazard" in trait or "龐克哈薩特" in trait or "パンクハザード" in trait
    assert draw.get("op") == "draw" and draw.get("count") == 1
    eot = next(a for a in get_abilities("EB05-007", "end_of_your_turn"))
    buff = eot["ops"][0]
    assert buff.get("op") == "buff_self"
    assert buff.get("amount") == 5000
    assert buff.get("duration") == "until_opp_turn_end"


def test_eb05_007_reveal_three_events_draws():
    reload_effect_library(force=True)
    st = _state(hand=["EB05-007", "EV1", "EV2", "EV3"])
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-007" for c in p0.characters)
    _finish_reveals(st, 3)
    assert st.pending_choice is None
    assert "D0" in p0.hand
    assert len(p0.deck) == 19


def test_eb05_007_reveal_event_and_trait_mix_draws():
    reload_effect_library(force=True)
    st = _state(hand=["EB05-007", "EV1", "PH1", "EV2"])
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _finish_reveals(st, 3)
    assert st.pending_choice is None
    assert "D0" in p0.hand


def test_eb05_007_skip_reveal_does_not_draw():
    reload_effect_library(force=True)
    st = _state(hand=["EB05-007", "EV1", "EV2", "EV3"])
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert st.pending_choice is None
    assert "D0" not in p0.hand
    assert len(p0.deck) == 20


def test_eb05_007_too_few_eligible_does_not_draw():
    reload_effect_library(force=True)
    st = _state(hand=["EB05-007", "EV1", "EV2", "JUNK"])
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert st.pending_choice is None
    assert "D0" not in p0.hand
    assert len(p0.deck) == 20


def test_eb05_007_end_turn_plus_5000_until_opp_end():
    reload_effect_library(force=True)
    st = _state(hand=["EB05-007"])
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    mon = next(c for c in p0.characters if c.card_id == "EB05-007")
    assert inst_power(st, 0, mon.iid, catalog) == 1000
    assert apply_action(st, 0, {"type": "end_turn"}, catalog)["ok"]
    assert st.turn_seat == 1
    assert inst_power(st, 0, mon.iid, catalog) == 6000
    assert apply_action(st, 1, {"type": "end_turn"}, catalog)["ok"]
    assert inst_power(st, 0, mon.iid, catalog) == 1000
