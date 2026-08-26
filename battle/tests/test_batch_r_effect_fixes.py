"""Batch-R effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import apply_action, inst_power  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState, new_iid  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def _state(*, don_active0: int = 0, leader0: str = "OP12-001") -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="A",
        is_ai=False,
        leader_card_id=leader0,
        deck=["A"] * 20,
        hand=[],
        life=["L"] * 4,
        trash=[],
        don_active=don_active0,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="B",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["B"] * 20,
        hand=[],
        life=["R"] * 5,
        trash=[],
    )
    return MatchState(
        room_code="R",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=1,
        players=[p0, p1],
    )


def test_st30_001_own_base_power_and_names() -> None:
    entry = get_card_entry("ST30-001")
    for a in entry["abilities"]:
        if a["ops"] and a["ops"][0].get("op") == "buff_self":
            assert a.get("require_own_char_base_power_gte") == 7000
            assert a.get("require_field_char_base_power_gte") is None
    aura = next(a for a in entry["abilities"] if a["timing"] == "opponent_turn" and len(a["ops"]) == 2)
    names = " ".join(str(o.get("name_contains") or "") for o in aura["ops"])
    assert "Monkey.D.Luffy" in names
    assert "|Monkey" not in names.replace("Monkey.D.Luffy", "")
    assert "Portgas.D.Ace" in names
    assert "|Portgas" not in names.replace("Portgas.D.Ace", "")


def test_optional_rest_don_prompts() -> None:
    ops = get_card_entry("OP12-018")["abilities"][0]["ops"]
    assert ops[1].get("optional") is True and ops[1].get("as_cost") is True
    st = _state(don_active0=1)
    st.players[1].characters.append(CardInst(iid="o1", card_id="O1"))
    catalog = {
        "OP12-001": {"name": "L", "power": "5000", "card_type": "LEADER"},
        "OP01-001": {"name": "F", "power": "5000", "card_type": "LEADER"},
        "O1": {"name": "Opp", "power": "5000", "cost": 3, "card_type": "CHARACTER"},
    }.get
    apply_ops(st, 0, [dict(ops[1]), dict(ops[2])], catalog)
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert st.players[0].don_active == 1
    assert inst_power(st, 1, "o1", catalog) == 5000


def test_op12_037_rest_don_optional() -> None:
    play = next(a for a in get_card_entry("OP12-037")["abilities"] if a["timing"] == "on_play")
    assert play["ops"][0].get("optional") is True


def test_st30_012_rest_don_optional() -> None:
    play = next(a for a in get_card_entry("ST30-012")["abilities"] if a["timing"] == "on_play")
    assert play["ops"][0].get("optional") is True
    assert play["ops"][1].get("keyword") == "rush"


def test_op13_031_blocker_both_turns() -> None:
    timings = {
        a["timing"]
        for a in get_card_entry("OP13-031")["abilities"]
        if a.get("require_life_lte") == 1
    }
    assert "your_turn" in timings and "opponent_turn" in timings


def test_st31_001_rush_both_turns_and_sanji_exclude() -> None:
    entry = get_card_entry("ST31-001")
    rush = [a for a in entry["abilities"] if a.get("require_don_attached_gte") == 2]
    assert {a["timing"] for a in rush} >= {"your_turn", "opponent_turn"}
    play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    excl = str(play["ops"][1].get("exclude_name") or "")
    assert "Sanji" in excl and "香吉士" in excl


def test_schema_own_base_power_gate() -> None:
    ab = normalize_ability(
        {
            "timing": "your_turn",
            "require_own_char_base_power_gte": 7000,
            "ops": [{"op": "buff_self", "amount": -2000}],
        }
    )
    assert ab.get("require_own_char_base_power_gte") == 7000


if __name__ == "__main__":
    setup_module()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all ok")
