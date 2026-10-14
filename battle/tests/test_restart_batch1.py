"""Battle restart batch 1: EB05/OP18 overrides that were still lacking runnable effects."""

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

from battle.effect_library import (  # noqa: E402
    ability_is_runnable,
    card_has_timing_gaps,
    get_abilities,
    get_card_entry,
    reload_effect_library,
)
from battle.effect_schema import ability_is_runnable as schema_runnable  # noqa: E402
from battle.engine import (  # noqa: E402
    apply_action,
    apply_battle_character_ko,
    effective_character_cost,
    inst_power,
)
from battle.effects import effect_blob, has_meaningful_effect_text  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))

BATCH1 = [
    "EB05-018",
    "EB05-043",
    "OP18-010",
    "OP18-016",
    "OP18-024",
    "OP18-025",
    "OP18-032",
    "OP18-044",
    "OP18-048",
    "OP18-052",
    "OP18-055",
    "OP18-089",
]


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "LOW": {
            "card_id": "LOW",
            "card_type": "CHARACTER",
            "cost": 2,
            "power": 3000,
            "name": "Low",
            "traits": ["阿拉巴斯坦王國"],
            "traits_en": ["Alabasta"],
        },
        "HIGH": {
            "card_id": "HIGH",
            "card_type": "CHARACTER",
            "cost": 7,
            "power": 9000,
            "name": "High",
            "traits": ["海軍"],
            "traits_en": ["Navy"],
        },
        "ALA": {
            "card_id": "ALA",
            "card_type": "CHARACTER",
            "cost": 4,
            "power": 6000,
            "name": "Ala",
            "traits": ["阿拉巴斯坦王國"],
            "traits_en": ["Alabasta"],
        },
        "BIG": {
            "card_id": "BIG",
            "card_type": "CHARACTER",
            "cost": 4,
            "power": 7000,
            "name": "Big",
            "traits": ["阿拉巴斯坦王國"],
            "traits_en": ["Alabasta"],
        },
        "BW3": {
            "card_id": "BW3",
            "card_type": "CHARACTER",
            "cost": 3,
            "power": 4000,
            "name": "BW3",
            "traits": ["B・W"],
            "traits_en": ["Baroque Works"],
        },
        "BW6": {
            "card_id": "BW6",
            "card_type": "CHARACTER",
            "cost": 6,
            "power": 5000,
            "name": "BW6",
            "traits": ["B・W"],
            "traits_en": ["Baroque Works"],
        },
        "C2": {"card_id": "C2", "card_type": "CHARACTER", "cost": 2, "power": 2000, "name": "C2"},
        "C3": {"card_id": "C3", "card_type": "CHARACTER", "cost": 3, "power": 3000, "name": "C3"},
        "C6": {"card_id": "C6", "card_type": "CHARACTER", "cost": 6, "power": 5000, "name": "C6"},
        "C7": {"card_id": "C7", "card_type": "CHARACTER", "cost": 7, "power": 6000, "name": "C7"},
        "P3": {"card_id": "P3", "card_type": "CHARACTER", "cost": 1, "power": 3000, "name": "P3"},
        "P5": {"card_id": "P5", "card_type": "CHARACTER", "cost": 1, "power": 5000, "name": "P5"},
        "HAND": {"card_id": "HAND", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "Hand"},
        "OH": {"card_id": "OH", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "OppHand"},
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": cid}


def _players(
    *,
    hand: list[str] | None = None,
    chars: list[CardInst] | None = None,
    opp_chars: list[CardInst] | None = None,
    opp_hand: list[str] | None = None,
    trash: list[str] | None = None,
    leader_rested: bool = False,
    deck: list[str] | None = None,
    leader: str = "OP01-001",
) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=leader,
        leader_rested=leader_rested,
        deck=list(deck or ["X"] * 20),
        hand=list(hand or []),
        trash=list(trash or []),
        life=["L"] * 5,
        don_active=10,
        don_given=10,
        turns_completed=1,
        characters=list(chars or []),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["Y"] * 20,
        hand=list(opp_hand or []),
        life=["M"] * 5,
        characters=list(opp_chars or []),
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


def _settle(st: MatchState, seat: int = 0) -> None:
    if st.pending_effect is not None:
        assert apply_action(st, st.pending_effect.seat, {"type": "confirm_effect", "accept": True}, catalog)["ok"]


def test_batch1_overrides_are_runnable_and_close_timing_gaps():
    reload_effect_library(force=True)
    for cid in BATCH1:
        entry = get_card_entry(cid)
        abs_ = [a for a in (entry.get("abilities") or []) if ability_is_runnable(a)]
        assert abs_, cid
        info = catalog(cid)
        assert has_meaningful_effect_text(effect_blob(info))
        assert not card_has_timing_gaps(info, entry.get("abilities") or []), cid
        assert schema_runnable(abs_[0])


def test_eb05_018_on_play_skip_untap_cost6():
    reload_effect_library(force=True)
    st = _players(
        leader="OP01-031",
        hand=["EB05-018"],
        opp_chars=[
            CardInst(iid="c6", card_id="C6", rested=True, summoning_sick=False),
            CardInst(iid="c7", card_id="C7", rested=True, summoning_sick=False),
            CardInst(iid="up", card_id="C6", rested=False, summoning_sick=False),
        ],
    )
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _settle(st)
    ch = st.pending_choice
    assert ch is not None
    assert "c6" in ch.options
    assert "c7" not in ch.options
    assert "up" not in ch.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "c6"}, catalog)["ok"]
    assert "c6" in st.players[1].skip_untap_iids


def test_eb05_043_on_ko_choose_ko_or_rest():
    reload_effect_library(force=True)
    st = _players(
        chars=[CardInst(iid="src", card_id="EB05-043", summoning_sick=False)],
        opp_chars=[
            CardInst(iid="c6", card_id="C6", rested=False, summoning_sick=False),
            CardInst(iid="c7", card_id="C7", rested=False, summoning_sick=False),
        ],
    )
    apply_battle_character_ko(st, 0, st.players[0].characters[0], catalog)
    ch = st.pending_choice
    assert ch is not None
    assert "opt:0" in ch.options and "opt:1" in ch.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "opt:0"}, catalog)["ok"]
    ko = st.pending_choice
    assert ko is not None
    assert "c6" in ko.options and "c7" not in ko.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "c6"}, catalog)["ok"]
    assert "C6" in st.players[1].trash

    st2 = _players(
        chars=[CardInst(iid="src", card_id="EB05-043", summoning_sick=False)],
        opp_chars=[CardInst(iid="c6", card_id="C6", rested=False, summoning_sick=False)],
    )
    apply_battle_character_ko(st2, 0, st2.players[0].characters[0], catalog)
    assert apply_action(st2, 0, {"type": "select_choice", "target_iid": "opt:1"}, catalog)["ok"]
    if st2.pending_choice is not None:
        assert apply_action(st2, 0, {"type": "select_choice", "target_iid": "c6"}, catalog)["ok"]
    assert st2.players[1].characters[0].rested is True


def test_op18_010_on_ko_adds_power_lte_4000_from_trash():
    reload_effect_library(force=True)
    op = next(a for a in get_abilities("OP18-010", "on_ko"))["ops"][0]
    assert op["op"] == "add_from_trash" and op["power_lte"] == 4000
    st = _players(
        chars=[CardInst(iid="src", card_id="OP18-010", summoning_sick=False)],
        trash=["P3", "P5"],
    )
    apply_battle_character_ko(st, 0, st.players[0].characters[0], catalog)
    ch = st.pending_choice
    assert ch is not None
    assert any(tok.endswith(":P3") for tok in ch.options)
    assert not any(tok.endswith(":P5") for tok in ch.options)
    pick = next(tok for tok in ch.options if tok.endswith(":P3"))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert "P3" in st.players[0].hand
    assert "P3" not in st.players[0].trash


def test_op18_016_on_ko_plays_alabasta_power_lte_6000():
    reload_effect_library(force=True)
    st = _players(
        hand=["ALA", "BIG", "HIGH"],
        chars=[CardInst(iid="src", card_id="OP18-016", summoning_sick=False)],
    )
    apply_battle_character_ko(st, 0, st.players[0].characters[0], catalog)
    ch = st.pending_choice
    assert ch is not None
    assert any(tok.endswith(":ALA") for tok in ch.options)
    assert not any(tok.endswith(":BIG") for tok in ch.options)
    assert not any(tok.endswith(":HIGH") for tok in ch.options)
    pick = next(tok for tok in ch.options if tok.endswith(":ALA"))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert any(c.card_id == "ALA" for c in st.players[0].characters)
    assert "ALA" not in st.players[0].hand


def test_op18_024_end_turn_may_trash_to_active_leader():
    reload_effect_library(force=True)
    src = CardInst(iid="koko", card_id="OP18-024", rested=True, summoning_sick=False)
    st = _players(chars=[src], leader_rested=True)
    assert apply_action(st, 0, {"type": "end_turn"}, catalog)["ok"]
    if st.pending_effect is not None:
        assert apply_action(st, 0, {"type": "confirm_effect", "accept": True}, catalog)["ok"]
    ch = st.pending_choice
    assert ch is not None
    assert "koko" in ch.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "koko"}, catalog)["ok"]
    assert st.players[0].leader_rested is False
    assert "OP18-024" in st.players[0].trash


def test_op18_025_end_turn_actives_leader_only_while_rested():
    reload_effect_library(force=True)
    rested = _players(
        chars=[CardInst(iid="gon", card_id="OP18-025", rested=True, summoning_sick=False)],
        leader_rested=True,
    )
    assert apply_action(rested, 0, {"type": "end_turn"}, catalog)["ok"]
    assert rested.players[0].leader_rested is False
    assert any(c.card_id == "OP18-025" for c in rested.players[0].characters)

    active = _players(
        chars=[CardInst(iid="gon", card_id="OP18-025", rested=False, summoning_sick=False)],
        leader_rested=True,
    )
    assert apply_action(active, 0, {"type": "end_turn"}, catalog)["ok"]
    assert active.players[0].leader_rested is True


def test_op18_032_on_play_and_on_ko_skip_untap_power_8000():
    reload_effect_library(force=True)
    low = CardInst(iid="low", card_id="LOW", rested=True, summoning_sick=False)
    high = CardInst(iid="high", card_id="HIGH", rested=True, summoning_sick=False)
    st = _players(leader="OP01-031", hand=["OP18-032"], opp_chars=[low, high])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _settle(st)
    ch = st.pending_choice
    assert ch is not None
    assert "low" in ch.options and "high" not in ch.options
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert st.players[1].skip_untap_iids == []

    played = next(c for c in st.players[0].characters if c.card_id == "OP18-032")
    apply_battle_character_ko(st, 0, played, catalog)
    ch2 = st.pending_choice
    assert ch2 is not None and "low" in ch2.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "low"}, catalog)["ok"]
    assert "low" in st.players[1].skip_untap_iids


def test_op18_044_don_buff_and_on_play_draw_trash():
    reload_effect_library(force=True)
    st = _players(leader="OP01-060", hand=["OP18-044", "HAND"], deck=["D0"] + ["X"] * 19)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _settle(st)
    inst = next(c for c in st.players[0].characters if c.card_id == "OP18-044")
    assert inst_power(st, 0, inst.iid, catalog) == 4000
    assert "D0" in st.players[0].hand or "D0" in st.players[0].trash
    if st.pending_choice is not None:
        pick = st.pending_choice.options[0]
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert len(st.players[0].hand) == 1
    assert apply_action(st, 0, {"type": "attach_don", "target_iid": inst.iid}, catalog)["ok"]
    # 4000 printed + 1000 DON!! + 1000 [DON!! x1]
    assert inst_power(st, 0, inst.iid, catalog) == 6000


def test_op18_048_on_play_plays_bw_cost_lte_5():
    reload_effect_library(force=True)
    st = _players(leader="OP01-060", hand=["OP18-048", "BW3", "BW6"])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _settle(st)
    ch = st.pending_choice
    assert ch is not None
    assert any(tok.endswith(":BW3") for tok in ch.options)
    assert not any(tok.endswith(":BW6") for tok in ch.options)
    pick = next(tok for tok in ch.options if tok.endswith(":BW3"))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert any(c.card_id == "BW3" for c in st.players[0].characters)


def test_op18_052_don_buff_and_play_bw_cost_lte_3():
    reload_effect_library(force=True)
    st = _players(leader="OP01-060", hand=["OP18-052", "BW3", "BW6"])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _settle(st)
    inst = next(c for c in st.players[0].characters if c.card_id == "OP18-052")
    ch = st.pending_choice
    assert ch is not None
    assert any(tok.endswith(":BW3") for tok in ch.options)
    assert not any(tok.endswith(":BW6") for tok in ch.options)
    pick = next(tok for tok in ch.options if tok.endswith(":BW3"))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert apply_action(st, 0, {"type": "attach_don", "target_iid": inst.iid}, catalog)["ok"]
    # 4000 printed + 1000 DON!! + 1000 [DON!! x1]
    assert inst_power(st, 0, inst.iid, catalog) == 6000


def test_op18_055_returns_cost_lte_2():
    reload_effect_library(force=True)
    st = _players(
        leader="OP01-060",
        hand=["OP18-055"],
        opp_chars=[
            CardInst(iid="c2", card_id="C2", summoning_sick=False),
            CardInst(iid="c3", card_id="C3", summoning_sick=False),
        ],
    )
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _settle(st)
    ch = st.pending_choice
    assert ch is not None
    assert "c2" in ch.options and "c3" not in ch.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "c2"}, catalog)["ok"]
    assert "C2" in st.players[1].hand
    assert all(c.iid != "c2" for c in st.players[1].characters)


def test_op18_089_plus_12_cost_and_optional_hand_trash():
    reload_effect_library(force=True)
    st = _players(leader="OP09-061", hand=["OP18-089", "HAND"], opp_hand=["OH", "OH"])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _settle(st)
    inst = next(c for c in st.players[0].characters if c.card_id == "OP18-089")
    assert effective_character_cost(st, 0, inst, catalog) == 16
    st.turn_seat = 1
    assert effective_character_cost(st, 0, inst, catalog) == 16
    st.turn_seat = 0
    ch = st.pending_choice
    assert ch is not None and ch.seat == 0
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert st.players[1].hand == ["OH", "OH"]

    st2 = _players(leader="OP09-061", hand=["OP18-089", "HAND"], opp_hand=["OH"])
    assert apply_action(st2, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _settle(st2)
    mine = next(tok for tok in (st2.pending_choice.options or []) if tok.endswith(":HAND"))
    assert apply_action(st2, 0, {"type": "select_choice", "target_iid": mine}, catalog)["ok"]
    assert "HAND" in st2.players[0].trash
    opp = st2.pending_choice
    if opp is not None:
        assert opp.seat == 1
        assert apply_action(st2, 1, {"type": "select_choice", "target_iid": opp.options[0]}, catalog)["ok"]
    assert "OH" in st2.players[1].trash
