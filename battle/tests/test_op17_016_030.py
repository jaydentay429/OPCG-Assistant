"""OP17-016..030 encoding / runtime (Whitebeard events + Red-Hair package)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import ability_is_runnable, get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops, detect_keywords  # noqa: E402
from battle.engine import _ability_board_conditions_ok, _confirm_effect, _resolve_choice  # noqa: E402
from battle.leave_replace import try_replace_leave  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

IDS = [f"OP17-{i:03d}" for i in range(16, 31)]


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP17-020"),
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
        room_code="OP17B",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 0),
        first_seat=0,
        turn_number=3,
        players=[p0, p1],
    )


def _cat(extra: dict | None = None):
    base = {
        "OP17-020": {
            "name": "香克斯",
            "name_en": "Shanks",
            "card_type": "LEADER",
            "power": "5000",
            "colors_en": ["Red"],
            "traits_en": ["The Four Emperors", "Red-Haired Pirates"],
        },
        "LUFFY": {
            "name": "Monkey.D.Luffy",
            "name_en": "Monkey.D.Luffy",
            "card_type": "LEADER",
            "power": "5000",
            "colors_en": ["Red"],
            "traits_en": ["Straw Hat Crew"],
        },
        "OP01-001": {"name": "Luffy", "card_type": "LEADER", "power": "5000", "colors_en": ["Red"]},
        "HI": {
            "name": "Hi",
            "card_type": "CHARACTER",
            "power": "9000",
            "cost": "8",
        },
        "MID": {
            "name": "Mid",
            "card_type": "CHARACTER",
            "power": "5000",
            "cost": "4",
        },
        "LOW": {"name": "Low", "card_type": "CHARACTER", "power": "2000", "cost": "2"},
        "A": {"name": "A", "card_type": "CHARACTER", "power": "1000", "cost": "1"},
        "B": {"name": "B", "card_type": "EVENT", "cost": "1"},
        "L": {"name": "Life", "card_type": "CHARACTER", "cost": "1"},
        "R": {"name": "R", "card_type": "CHARACTER", "cost": "1"},
    }
    if extra:
        base.update(extra)
    return lambda cid: base.get(cid) or {"name": cid, "card_type": "CHARACTER", "power": "1000", "cost": "1"}


def test_op17_016_to_030_runnable():
    reload_effect_library(force=True)
    for cid in IDS:
        abilities = get_card_entry(cid)["abilities"]
        bad = [a for a in abilities if a.get("ops") and not ability_is_runnable(a)]
        assert not bad, f"{cid} still has unrunnable abilities: {bad}"

    ev = next(a for a in get_card_entry("OP17-017")["abilities"] if a["timing"] == "counter_event")
    assert ev["ops"][0].get("amount") == 2000
    assert ev["ops"][0].get("duration") == "battle"
    assert ev["ops"][0].get("trait_contains") == "Whitebeard Pirates"
    assert ev["ops"][1].get("amount") == -2000
    assert ev["ops"][1].get("duration") == "turn"

    world = next(a for a in get_card_entry("OP17-018")["abilities"] if a["timing"] == "on_play")
    assert world["ops"][0].get("op") == "rest_don"
    assert world["ops"][0].get("count") == 2
    assert world["ops"][1].get("target_kind") == "opponent_stage"
    ctr = next(a for a in get_card_entry("OP17-018")["abilities"] if a["timing"] == "counter_event")
    assert int(ctr.get("require_chars_base_power_gte") or 0) == 8000
    assert int(ctr.get("require_chars_base_power_count_gte") or 0) == 2

    search = next(a for a in get_card_entry("OP17-019")["abilities"] if a["timing"] == "on_play")
    assert search["ops"][0].get("op") == "search_deck"
    trig = next(a for a in get_card_entry("OP17-019")["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0].get("target_kind") == "leader"

    oli = next(a for a in get_card_entry("OP17-021")["abilities"] if a["timing"] == "your_turn")
    assert oli["ops"][0].get("cost") == "rest_own"
    assert oli["ops"][0].get("trigger") == "opp_remove"

    shanks = next(a for a in get_card_entry("OP17-022")["abilities"] if a["timing"] == "on_play")
    assert shanks["ops"][1].get("all") is True

    nami = next(a for a in get_card_entry("OP17-023")["abilities"] if a["timing"] == "your_turn")
    assert "East Blue" in str(nami["ops"][0].get("trait_contains") or "")

    snake = next(a for a in get_card_entry("OP17-025")["abilities"] if a["timing"] == "activate_main")
    assert snake["ops"][0].get("op") == "attach_don"
    assert snake["ops"][0].get("from_rested") is True

    fugar = next(a for a in get_card_entry("OP17-026")["abilities"] if a["timing"] == "when_attacking")
    assert fugar.get("require_leader_trait") == "Red-Haired Pirates"
    assert fugar["ops"][0].get("cost_lte") == 2

    beck = next(a for a in get_card_entry("OP17-027")["abilities"] if a["timing"] == "on_play")
    assert beck["ops"][0].get("op") == "draw"
    assert beck["ops"][1].get("count") == 2

    hongo = next(a for a in get_card_entry("OP17-029")["abilities"] if a["timing"] == "on_play")
    assert hongo["ops"][0].get("op") == "active_don"
    assert hongo["ops"][1].get("cost_lte") == 2

    luffy = next(a for a in get_card_entry("OP17-030")["abilities"] if a["timing"] == "on_play")
    assert luffy["ops"][0].get("op") == "rest_don"
    assert luffy["ops"][1].get("keyword") == "rush"
    act = next(a for a in get_card_entry("OP17-030")["abilities"] if a["timing"] == "activate_main")
    assert int(act.get("require_hand_lte") or 0) == 5

    gab = {"effect": "[Banish] [On Play] Rest up to 1 of your opponent's Characters."}
    assert "banish" in detect_keywords(gab)
    assert "blocker" in detect_keywords({"effect": "[Blocker] [On Play] K.O. up to 1 rested Character."})
    assert "rush_character" in detect_keywords(
        {"effect": "[Rush: Character] [On Play] If your Leader has the {Red-Haired Pirates} type, draw 1 card."}
    )


def test_018_counter_needs_two_8000_chars():
    reload_effect_library(force=True)
    ab = next(a for a in get_card_entry("OP17-018")["abilities"] if a["timing"] == "counter_event")
    cat = _cat()
    st = _state()
    st.players[0].characters = [CardInst(iid="h1", card_id="HI")]
    assert _ability_board_conditions_ok(st, 0, ab, cat) is False
    st.players[0].characters.append(CardInst(iid="h2", card_id="HI"))
    assert _ability_board_conditions_ok(st, 0, ab, cat) is True
    st.players[0].characters = [CardInst(iid="m1", card_id="MID"), CardInst(iid="m2", card_id="MID")]
    assert _ability_board_conditions_ok(st, 0, ab, cat) is False


def test_022_rests_all_opp_characters():
    cat = _cat()
    st = _state()
    st.players[1].characters = [
        CardInst(iid="a", card_id="HI"),
        CardInst(iid="b", card_id="MID"),
        CardInst(iid="c", card_id="LOW", rested=True),
    ]
    apply_ops(st, 0, [{"op": "rest_opponent_character", "all": True}], cat)
    assert all(c.rested for c in st.players[1].characters)


def test_030_rests_own_don_not_opp_character():
    reload_effect_library(force=True)
    ab = next(a for a in get_card_entry("OP17-030")["abilities"] if a["timing"] == "on_play")
    assert ab["ops"][0].get("op") == "rest_don"
    assert not any(o.get("op") == "rest_opponent_character" for o in ab["ops"])
    cat = _cat()
    st = _state(don_active0=3)
    st.players[1].characters = [CardInst(iid="opp", card_id="HI")]
    apply_ops(st, 0, [{"op": "rest_don", "count": 1, "owner": "self", "as_cost": True, "target_iid": "don"}], cat)
    assert st.players[0].don_active == 2
    assert st.players[0].don_rested == 1
    assert st.players[1].characters[0].rested is False


def test_025_activate_is_attach_not_ko():
    reload_effect_library(force=True)
    ab = next(a for a in get_card_entry("OP17-025")["abilities"] if a["timing"] == "activate_main")
    assert ab["ops"][0].get("op") == "attach_don"
    cat = _cat()
    st = _state(leader0="OP17-020", don_rested0=2, don_active0=3)
    apply_ops(
        st,
        0,
        [
            {
                "op": "attach_don",
                "count": 1,
                "from_rested": True,
                "as_rested": True,
                "target_kind": "leader",
                "name_contains": "Shanks",
            }
        ],
        cat,
    )
    assert st.players[0].leader_don == 1
    assert st.players[0].don_rested == 1


def test_026_leader_trait_gate():
    reload_effect_library(force=True)
    ab = next(a for a in get_card_entry("OP17-026")["abilities"] if a["timing"] == "when_attacking")
    cat = _cat()
    st = _state(leader0="OP17-020")
    assert _ability_board_conditions_ok(st, 0, ab, cat) is True
    st.players[0].leader_card_id = "LUFFY"
    assert _ability_board_conditions_ok(st, 0, ab, cat) is False


def test_030_activate_needs_hand_lte_5():
    reload_effect_library(force=True)
    ab = next(a for a in get_card_entry("OP17-030")["abilities"] if a["timing"] == "activate_main")
    cat = _cat()
    st = _state(hand0=["A"] * 5)
    assert _ability_board_conditions_ok(st, 0, ab, cat) is True
    st.players[0].hand = ["A"] * 6
    assert _ability_board_conditions_ok(st, 0, ab, cat) is False


def test_021_rest_own_asks_and_skip_allows_leave():
    reload_effect_library(force=True)
    cat = _cat(
        {
            "OP17-021": {
                "name": "Crone Oli",
                "card_type": "CHARACTER",
                "power": "4000",
                "cost": "3",
                "traits_en": ["Red-Haired Pirates Allies"],
            },
            "RH": {
                "name": "Ally",
                "card_type": "CHARACTER",
                "power": "5000",
                "cost": "4",
                "traits_en": ["Red-Haired Pirates"],
            },
        }
    )
    st = _state(don_active0=2, leader0="OP17-020")
    oli = CardInst(iid="oli", card_id="OP17-021")
    ally = CardInst(iid="ally", card_id="RH")
    st.players[0].characters = [oli, ally]
    apply_ops(st, 1, [{"op": "ko", "target_iid": "ally", "target_kind": "opponent_character"}], cat)
    assert any(c.iid == "ally" for c in st.players[0].characters)
    assert st.pending_choice is not None
    assert st.pending_choice.purpose == "replace_leave"
    assert "don" in st.pending_choice.options
    assert "leader" in st.pending_choice.options
    _resolve_choice(st, 0, None, cat)
    assert not any(c.iid == "ally" for c in st.players[0].characters)
    assert st.players[0].don_active == 2


def test_021_rest_own_don_saves_character():
    reload_effect_library(force=True)
    cat = _cat(
        {
            "OP17-021": {
                "name": "Crone Oli",
                "card_type": "CHARACTER",
                "power": "4000",
                "cost": "3",
                "traits_en": ["Red-Haired Pirates Allies"],
            },
            "RH": {
                "name": "Ally",
                "card_type": "CHARACTER",
                "power": "5000",
                "cost": "4",
                "traits_en": ["Red-Haired Pirates"],
            },
        }
    )
    st = _state(don_active0=2, leader0="OP17-020")
    oli = CardInst(iid="oli", card_id="OP17-021")
    ally = CardInst(iid="ally", card_id="RH")
    st.players[0].characters = [oli, ally]
    apply_ops(st, 1, [{"op": "ko", "target_iid": "ally", "target_kind": "opponent_character"}], cat)
    _resolve_choice(st, 0, "don", cat)
    assert any(c.iid == "ally" for c in st.players[0].characters)
    assert st.players[0].don_active == 1
    assert st.players[0].don_rested == 1
    assert not st.players[0].leader_rested


def test_015_marco_confirm_required():
    reload_effect_library(force=True)
    cat = _cat(
        {
            "OP17-015": {
                "name": "Marco",
                "card_type": "CHARACTER",
                "power": "6000",
                "cost": "5",
                "traits_en": ["Whitebeard Pirates"],
            },
            "ALLY": {
                "name": "Atmos",
                "card_type": "CHARACTER",
                "power": "6000",
                "cost": "4",
                "traits_en": ["Whitebeard Pirates"],
            },
        }
    )
    st = _state(leader0="OP17-001")
    ally = CardInst(iid="ally", card_id="ALLY")
    marco = CardInst(iid="marco", card_id="OP17-015")
    st.players[0].characters = [ally, marco]
    ok = try_replace_leave(st, 0, ally, by_opponent=True, catalog=cat, by_ko=False)
    assert ok is True
    assert any(c.iid == "marco" for c in st.players[0].characters)
    assert st.pending_effect is not None
    _confirm_effect(st, 0, False, cat)
    assert not any(c.iid == "ally" for c in st.players[0].characters)
    assert any(c.iid == "marco" for c in st.players[0].characters)
