"""EB05-009 Let's Die Together!!!: Main buffs own printed-power≤4000 chars until opp End; Counter Leader +3000 battle."""

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
from battle.engine import apply_action, inst_power  # noqa: E402
from battle.state import CardInst, MatchState, PendingAttack, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "LOW": {"card_id": "LOW", "card_type": "CHARACTER", "cost": 1, "power": 2000, "name": "Low"},
        "MID": {"card_id": "MID", "card_type": "CHARACTER", "cost": 3, "power": 4000, "name": "Mid"},
        "HIGH": {"card_id": "HIGH", "card_type": "CHARACTER", "cost": 5, "power": 5000, "name": "High"},
        "OP01-001": {"card_id": "OP01-001", "card_type": "LEADER", "power": 5000, "name": "Luffy"},
        "D0": {"card_id": "D0", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "D0"},
        "X": {"card_id": "X", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "X"},
        "Y": {"card_id": "Y", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "Y"},
        "L": {"card_id": "L", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "L"},
        "M": {"card_id": "M", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "M"},
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _main_state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["D0"] + ["X"] * 19,
        hand=["EB05-009"],
        life=["L"] * 5,
        don_active=2,
        don_given=2,
        turns_completed=1,
        characters=[
            CardInst(iid="low", card_id="LOW", rested=False, summoning_sick=False),
            CardInst(iid="mid", card_id="MID", rested=False, summoning_sick=False),
            CardInst(iid="high", card_id="HIGH", rested=False, summoning_sick=False),
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
        characters=[CardInst(iid="opp", card_id="LOW", rested=False, summoning_sick=False)],
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


def test_eb05_009_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-009")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-009 abilities dropped on normalize"
    main = next(a for a in get_abilities("EB05-009", "on_play"))
    assert main["ops"][0].get("op") == "buff"
    assert main["ops"][0].get("amount") == 1000
    assert main["ops"][0].get("all") is True
    assert main["ops"][0].get("target_kind") == "own_character"
    assert main["ops"][0].get("base_power_lte") == 4000
    assert main["ops"][0].get("duration") == "until_opp_turn_end"
    ctr = next(a for a in get_abilities("EB05-009", "counter_event"))
    assert ctr["ops"][0].get("op") == "buff"
    assert ctr["ops"][0].get("amount") == 3000
    assert ctr["ops"][0].get("target_kind") == "leader"
    assert ctr["ops"][0].get("duration") == "battle"
    info = catalog("EB05-009")
    assert has_counter_timing(info) is True


def test_eb05_009_main_buffs_printed_power_lte_4000_until_opp_end():
    reload_effect_library(force=True)
    st = _main_state()
    high = next(c for c in st.players[0].characters if c.iid == "high")
    high.power_mod = -1000  # current 4000, printed 5000 — must not gain
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert "EB05-009" in st.players[0].trash
    assert inst_power(st, 0, "low", catalog) == 3000
    assert inst_power(st, 0, "mid", catalog) == 5000
    assert inst_power(st, 0, "high", catalog) == 4000
    assert inst_power(st, 1, "opp", catalog) == 2000
    assert inst_power(st, 0, "leader", catalog) == 5000
    assert apply_action(st, 0, {"type": "end_turn"}, catalog)["ok"]
    assert st.turn_seat == 1
    assert inst_power(st, 0, "low", catalog) == 3000
    assert inst_power(st, 0, "mid", catalog) == 5000
    assert apply_action(st, 1, {"type": "end_turn"}, catalog)["ok"]
    assert inst_power(st, 0, "low", catalog) == 2000
    assert inst_power(st, 0, "mid", catalog) == 4000


def test_eb05_009_counter_buffs_own_leader_this_battle():
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
