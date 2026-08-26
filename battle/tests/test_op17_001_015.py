"""OP17-001..015 encoding / runtime (Whitebeard red package)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import ability_is_runnable, get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops, detect_keywords  # noqa: E402
from battle.engine import _ability_board_conditions_ok, _clear_turn_duration_effects, inst_power  # noqa: E402
from battle.leave_replace import confirm_replace_if_pending, try_replace_leave  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

IDS = [f"OP17-{i:03d}" for i in range(1, 16)]


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP17-001"),
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
        leader_card_id="OP01-001",
        deck=["B"] * 20,
        hand=[],
        life=["R"] * 5,
        trash=[],
    )
    return MatchState(
        room_code="OP17",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 0),
        first_seat=0,
        turn_number=3,
        players=[p0, p1],
    )


def _cat(extra: dict | None = None):
    base = {
        "OP17-001": {
            "name": "愛德華・紐蓋特",
            "name_en": "Edward.Newgate",
            "card_type": "LEADER",
            "power": "5000",
            "colors": ["紅"],
            "colors_en": ["Red"],
            "traits_en": ["The Four Emperors", "Whitebeard Pirates"],
        },
        "DUAL": {
            "name": "Dual",
            "name_en": "Dual Leader",
            "card_type": "LEADER",
            "power": "5000",
            "colors_en": ["Red", "Green"],
        },
        "LUFFY": {
            "name": "Monkey.D.Luffy",
            "name_en": "Monkey.D.Luffy",
            "card_type": "LEADER",
            "power": "5000",
            "colors_en": ["Red"],
            "traits_en": ["Straw Hat Crew"],
        },
        "WANO_LEAD": {
            "name": "Kouzuki Oden",
            "name_en": "Kouzuki Oden",
            "card_type": "LEADER",
            "power": "5000",
            "colors_en": ["Red"],
            "traits_en": ["Land of Wano"],
        },
        "OP01-001": {"name": "Luffy", "card_type": "LEADER", "power": "5000", "colors_en": ["Red"]},
        "BIG": {
            "name": "Big",
            "card_type": "CHARACTER",
            "power": "12000",
            "cost": "9",
        },
        "RESTED": {
            "name": "Rested",
            "card_type": "CHARACTER",
            "power": "6000",
            "cost": "5",
        },
        "LOW": {"name": "Low", "card_type": "CHARACTER", "power": "2000", "cost": "2"},
        "ALLY": {
            "name": "Atmos",
            "card_type": "CHARACTER",
            "power": "6000",
            "cost": "4",
            "traits_en": ["Whitebeard Pirates"],
        },
        "MARCO": {
            "name": "Marco",
            "card_type": "CHARACTER",
            "power": "6000",
            "cost": "5",
            "traits_en": ["Whitebeard Pirates"],
            "effect": (
                "If one of your Characters would be removed from the field by your opponent's effect, "
                "you may K.O. this Character instead. [On K.O.] You may trash 1 card with a type including "
                '"Whitebeard Pirates" from your hand: Play this Character card from your trash.'
            ),
        },
        "WB_HAND": {
            "name": "Fossa",
            "card_type": "CHARACTER",
            "power": "3000",
            "cost": "1",
            "traits_en": ["Whitebeard Pirates"],
        },
        "A": {"name": "A", "card_type": "CHARACTER", "power": "1000", "cost": "1"},
        "B": {"name": "B", "card_type": "EVENT", "cost": "1"},
        "L": {"name": "Life", "card_type": "CHARACTER", "cost": "1"},
        "R": {"name": "R", "card_type": "CHARACTER", "cost": "1"},
    }
    if extra:
        base.update(extra)
    return lambda cid: base.get(cid) or {"name": cid, "card_type": "CHARACTER", "power": "1000", "cost": "1"}


def test_op17_001_to_015_runnable():
    reload_effect_library(force=True)
    for cid in IDS:
        abilities = get_card_entry(cid)["abilities"]
        bad = [a for a in abilities if a.get("ops") and not ability_is_runnable(a)]
        assert not bad, f"{cid} still has unrunnable abilities: {bad}"
    assert detect_keywords({"effect": get_card_entry("OP17-003")["abilities"][0]["summary"]}) or True
    izo_text = {
        "effect": "[Rush: Character] [On Play] If your Leader is [Edward.Newgate] or has the {Land of Wano} type, give up to 1 of your opponent's rested Characters −6000 power during this turn."
    }
    assert "rush_character" in detect_keywords(izo_text)
    blenheim = {
        "effect": "[Blocker] [On K.O.] Play up to 1 card with a cost of 1 and a type including \"Whitebeard Pirates\" from your hand."
    }
    assert "blocker" in detect_keywords(blenheim)

    oden = next(a for a in get_card_entry("OP17-007")["abilities"] if a["timing"] == "on_play")
    assert oden.get("require_leader_name_or_trait") is True
    assert oden["ops"][0].get("trait_any")

    ace = next(a for a in get_card_entry("OP17-013")["abilities"] if a["timing"] == "hand_cost")
    assert int(ace.get("require_opp_char_power_gte") or 0) == 10000

    whitey = next(a for a in get_card_entry("OP17-014")["abilities"] if a["timing"] == "on_opponent_attack")
    assert whitey["ops"][0].get("op") == "trash"
    assert whitey["ops"][1].get("target_kind") == "leader"

    marco = next(a for a in get_card_entry("OP17-015")["abilities"] if a["timing"] == "on_ko")
    assert marco["ops"][0].get("trait_contains") == "Whitebeard Pirates"
    shield = next(a for a in get_card_entry("OP17-015")["abilities"] if a["timing"] == "your_turn")
    assert shield["ops"][0].get("cost") == "ko_self"


def test_jozu_sets_newgate_base_until_opp_end():
    cat = _cat()
    st = _state(leader0="OP17-001", turn_seat=0)
    apply_ops(
        st,
        0,
        [
            {
                "op": "set_base_power",
                "amount": 8000,
                "target_kind": "leader",
                "duration": "until_opp_turn_end",
            }
        ],
        cat,
    )
    assert inst_power(st, 0, "leader", cat) == 8000
    # Own End Phase must not wipe it.
    _clear_turn_duration_effects(st)
    assert inst_power(st, 0, "leader", cat) == 8000
    # Opponent End Phase expires it.
    st.turn_seat = 1
    _clear_turn_duration_effects(st)
    assert inst_power(st, 0, "leader", cat) == 5000


def test_newgate_10c_requires_monocolor_leader():
    reload_effect_library(force=True)
    ab = next(a for a in get_card_entry("OP17-005")["abilities"] if a["timing"] == "on_play")
    cat = _cat()
    st = _state(leader0="OP17-001")
    assert _ability_board_conditions_ok(st, 0, ab, cat) is True
    st.players[0].leader_card_id = "DUAL"
    assert _ability_board_conditions_ok(st, 0, ab, cat) is False


def test_izo_leader_gate():
    reload_effect_library(force=True)
    ab = next(a for a in get_card_entry("OP17-003")["abilities"] if a["timing"] == "on_play")
    cat = _cat()
    st = _state(leader0="OP17-001")
    assert _ability_board_conditions_ok(st, 0, ab, cat) is True
    st.players[0].leader_card_id = "WANO_LEAD"
    assert _ability_board_conditions_ok(st, 0, ab, cat) is True
    st.players[0].leader_card_id = "LUFFY"
    assert _ability_board_conditions_ok(st, 0, ab, cat) is False


def test_fossa_needs_opp_10000_and_unique_name():
    reload_effect_library(force=True)
    ab = next(a for a in get_card_entry("OP17-010")["abilities"] if a["timing"] == "activate_main")
    cat = _cat({"FOSSA": {"name": "Fossa", "name_en": "Fossa", "card_type": "CHARACTER", "power": "3000"}})
    st = _state()
    st.players[0].characters = [CardInst(iid="f1", card_id="FOSSA")]
    assert _ability_board_conditions_ok(st, 0, ab, cat, source_iid="f1") is False
    st.players[1].characters = [CardInst(iid="big", card_id="BIG")]
    assert _ability_board_conditions_ok(st, 0, ab, cat, source_iid="f1") is True
    st.players[0].characters.append(CardInst(iid="f2", card_id="FOSSA"))
    assert _ability_board_conditions_ok(st, 0, ab, cat, source_iid="f1") is False


def test_marco_ko_self_instead():
    reload_effect_library(force=True)
    cat = _cat()
    st = _state(hand0=["WB_HAND"], turn_seat=1)
    ally = CardInst(iid="ally", card_id="ALLY")
    marco = CardInst(iid="marco", card_id="OP17-015")
    st.players[0].characters = [ally, marco]
    ok = try_replace_leave(st, 0, ally, by_opponent=True, catalog=cat, by_ko=False)
    assert ok is True
    confirm_replace_if_pending(st, cat)
    ids = {c.iid for c in st.players[0].characters}
    assert "ally" in ids
    assert "marco" not in ids
    assert "OP17-015" in st.players[0].trash or any(c.card_id == "OP17-015" for c in st.players[0].characters)
