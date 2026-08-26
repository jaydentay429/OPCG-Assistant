"""OP17-031..045 encoding / runtime (Red-Hair + Rocks package)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import ability_is_runnable, get_card_entry, reload_effect_library  # noqa: E402
from battle.engine import _ability_board_conditions_ok, _fire_board_timing  # noqa: E402
from battle.leave_replace import confirm_replace_if_pending, try_replace_leave  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

IDS = [f"OP17-{i:03d}" for i in range(31, 46)]


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP17-039"),
        deck=list(kwargs.get("deck0", ["A"] * 20)),
        hand=list(kwargs.get("hand0", [])),
        life=["L"] * int(kwargs.get("life0", 5)),
        trash=list(kwargs.get("trash0", [])),
        don_active=int(kwargs.get("don_active0", 5) or 0),
        don_rested=int(kwargs.get("don_rested0", 0) or 0),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id=kwargs.get("leader1", "OP01-001"),
        deck=["B"] * 20,
        hand=[],
        life=["R"] * 5,
        trash=[],
        don_active=int(kwargs.get("don_active1", 0) or 0),
    )
    return MatchState(
        room_code="OP17C",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 0),
        first_seat=0,
        turn_number=3,
        players=[p0, p1],
    )


def _cat(extra: dict | None = None):
    base = {
        "OP17-039": {
            "name": "Rocks.D.Xebec",
            "card_type": "LEADER",
            "power": "5000",
            "traits_en": ["Rocks Pirates"],
        },
        "OP17-020": {
            "name": "Shanks",
            "card_type": "LEADER",
            "power": "5000",
            "traits_en": ["Red-Haired Pirates"],
        },
        "OP01-001": {"name": "Luffy", "card_type": "LEADER", "power": "5000", "traits_en": []},
        "BIG": {"name": "Big", "card_type": "LEADER", "power": "7000", "traits_en": []},
        "OP17-043": {
            "name": "Ganzui",
            "card_type": "CHARACTER",
            "power": "7000",
            "cost": "5",
            "traits_en": ["Rocks Pirates"],
        },
        "OP17-045": {
            "name": "Kyo",
            "card_type": "CHARACTER",
            "power": "4000",
            "cost": "2",
            "traits_en": ["Rocks Pirates"],
        },
        "SMALL": {"name": "Small", "card_type": "CHARACTER", "power": "1000", "cost": "1"},
        "A": {"name": "A", "card_type": "CHARACTER", "power": "1000", "cost": "1"},
        "B": {"name": "B", "card_type": "EVENT", "cost": "1"},
        "H1": {"name": "H1", "card_type": "CHARACTER", "cost": "2"},
        "H2": {"name": "H2", "card_type": "CHARACTER", "cost": "3"},
        "L": {"name": "Life", "card_type": "CHARACTER", "cost": "1"},
        "R": {"name": "R", "card_type": "CHARACTER", "cost": "1"},
    }
    if extra:
        base.update(extra)
    return lambda cid: base.get(cid) or {"name": cid, "card_type": "CHARACTER", "power": "1000", "cost": "1"}


def test_op17_031_to_045_runnable():
    reload_effect_library(force=True)
    for cid in IDS:
        if cid == "OP17-035":
            continue
        abilities = get_card_entry(cid)["abilities"]
        bad = [a for a in abilities if a.get("ops") and not ability_is_runnable(a)]
        assert not bad, f"{cid} still has unrunnable abilities: {bad}"

    yasopp = get_card_entry("OP17-031")
    eoy = next(a for a in yasopp["abilities"] if a["timing"] == "end_of_your_turn")
    assert "Red-Haired Pirates" in str(eoy["ops"][0].get("trait_contains") or "")

    roux = next(a for a in get_card_entry("OP17-033")["abilities"] if a["timing"] == "on_opponent_attack")
    assert roux["ops"][0].get("op") == "trash"
    assert roux["ops"][1].get("target_kind") == "opponent_leader_or_character"

    rockstar = next(a for a in get_card_entry("OP17-034")["abilities"] if a["timing"] == "activate_main")
    assert int(rockstar.get("require_opp_leader_power_gte") or 0) == 6000
    assert rockstar["ops"][1].get("op") == "set_base_power"

    ev36 = get_card_entry("OP17-036")
    main36 = next(a for a in ev36["abilities"] if a["timing"] == "on_play")
    assert main36["ops"][0].get("count") == 6
    ctr36 = next(a for a in ev36["abilities"] if a["timing"] == "counter_event")
    assert ctr36["ops"][0].get("duration") == "battle"

    ev37 = get_card_entry("OP17-037")
    assert next(a for a in ev37["abilities"] if a["timing"] == "on_play")["ops"][0]["top_n"] == 5
    ctr37 = next(a for a in ev37["abilities"] if a["timing"] == "counter_event")
    assert ctr37["ops"][0].get("include_leader") is True

    rocks_atk = next(a for a in get_card_entry("OP17-039")["abilities"] if a["timing"] == "when_attacking")
    assert rocks_atk["ops"][1].get("op") == "look_deck"
    assert rocks_atk["ops"][2].get("count") == 2

    newgate = get_card_entry("OP17-040")
    battle = next(a for a in newgate["abilities"] if a["timing"] == "on_own_leader_battle")
    assert battle.get("once") is True
    assert battle["ops"][1].get("duration") == "battle"

    wang = next(a for a in get_card_entry("OP17-041")["abilities"] if a["timing"] == "on_play")
    assert wang["ops"][1].get("all") is True
    assert wang["ops"][1].get("base_cost_eq") == 1

    kaido = next(a for a in get_card_entry("OP17-042")["abilities"] if a["timing"] == "on_play")
    assert kaido["ops"][0].get("op") == "reveal_hand"
    assert kaido["ops"][0].get("count") == 3

    john = get_card_entry("OP17-044")
    assert any(a.get("while_rested") for a in john["abilities"] if a["timing"] == "your_turn")


def test_op17_034_gate_opp_leader_power():
    reload_effect_library(force=True)
    st = _state(leader0="OP17-020", leader1="BIG")
    ab = next(a for a in get_card_entry("OP17-034")["abilities"] if a["timing"] == "activate_main")
    cat = _cat()
    assert _ability_board_conditions_ok(st, 0, ab, cat) is True
    st.players[1].leader_card_id = "OP01-001"
    assert _ability_board_conditions_ok(st, 0, ab, cat) is False


def test_op17_043_replace_trash_two_hand():
    reload_effect_library(force=True)
    st = _state(hand0=["H1", "H2", "B"])
    ganzui = CardInst(iid="g1", card_id="OP17-043")
    st.players[0].characters = [ganzui]
    cat = _cat()
    assert try_replace_leave(st, 0, ganzui, by_opponent=True, catalog=cat, by_ko=False) is True
    confirm_replace_if_pending(st, cat, accept=True)
    assert len(st.players[0].hand) == 1
    assert len(st.players[0].trash) == 2
    assert any(c.iid == "g1" for c in st.players[0].characters)


def test_op17_045_replace_any_character():
    reload_effect_library(force=True)
    st = _state(hand0=["H1", "H2", "B"])
    kyo = CardInst(iid="k0", card_id="OP17-045")
    victim = CardInst(iid="v1", card_id="SMALL")
    st.players[0].characters = [kyo, victim]
    cat = _cat()
    assert try_replace_leave(st, 0, victim, by_opponent=True, catalog=cat, by_ko=False) is True
    confirm_replace_if_pending(st, cat, accept=True)
    assert len(st.players[0].trash) == 2
    assert any(c.iid == "v1" for c in st.players[0].characters)
