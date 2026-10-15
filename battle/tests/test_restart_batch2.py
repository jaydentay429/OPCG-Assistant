"""Battle restart batch 2: EB05/OP18 overrides that were still lacking runnable effects."""

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
    get_card_entry,
    reload_effect_library,
    resolve_ability,
)
from battle.effects import effect_blob, has_blocker, has_meaningful_effect_text  # noqa: E402
from battle.engine import (  # noqa: E402
    _run_pending_effect,
    apply_action,
    apply_battle_character_ko,
    effective_character_cost,
    inst_power,
    legal_actions,
)
from battle.state import CardInst, MatchState, PendingAttack, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))

BATCH2 = [
    "EB05-004",
    "EB05-019",
    "EB05-030",
    "EB05-040",
    "EB05-049",
    "OP18-011",
    "OP18-034",
    "OP18-061",
    "OP18-063",
    "OP18-076",
    "OP18-084",
    "OP18-091",
]


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "BOTH": {
            "card_id": "BOTH",
            "card_type": "Character",
            "cost": 2,
            "power": 3000,
            "name": "Both",
            "traits": ["動物", "阿拉巴斯坦王國"],
            "traits_en": ["Animal", "Alabasta"],
        },
        "ANI": {
            "card_id": "ANI",
            "card_type": "Character",
            "cost": 2,
            "power": 3000,
            "name": "Ani",
            "traits": ["動物"],
            "traits_en": ["Animal"],
        },
        "FF5": {
            "card_id": "FF5",
            "card_type": "Character",
            "cost": 5,
            "power": 5000,
            "name": "FF5",
            "traits": ["佛朗基一家"],
            "traits_en": ["Franky Family"],
        },
        "FF6": {
            "card_id": "FF6",
            "card_type": "Character",
            "cost": 6,
            "power": 6000,
            "name": "FF6",
            "traits": ["佛朗基一家"],
            "traits_en": ["Franky Family"],
        },
        "SH4": {
            "card_id": "SH4",
            "card_type": "Character",
            "cost": 4,
            "power": 4000,
            "name": "SH4",
            "traits": ["草帽一行人"],
            "traits_en": ["Straw Hat Crew"],
        },
        "STG5": {
            "card_id": "STG5",
            "card_type": "Stage",
            "cost": 5,
            "name": "Stage5",
            "traits": ["草帽一行人"],
            "traits_en": ["Straw Hat Crew"],
        },
        "STG4": {
            "card_id": "STG4",
            "card_type": "Stage",
            "cost": 4,
            "name": "Stage4",
            "traits": ["草帽一行人"],
            "traits_en": ["Straw Hat Crew"],
        },
        "ST6": {"card_id": "ST6", "card_type": "Stage", "cost": 6, "name": "Stage6"},
        "W7C": {
            "card_id": "W7C",
            "card_type": "Character",
            "cost": 2,
            "power": 2000,
            "name": "W7",
            "traits": ["W7"],
            "traits_en": ["Water Seven"],
        },
        "NAVY": {
            "card_id": "NAVY",
            "card_type": "Character",
            "cost": 3,
            "power": 3000,
            "name": "Navy",
            "traits": ["海軍"],
            "traits_en": ["Navy"],
        },
        "STAGE": {"card_id": "STAGE", "card_type": "Stage", "cost": 1, "name": "Stage"},
        "HK6": {
            "card_id": "HK6",
            "card_type": "Character",
            "cost": 6,
            "power": 6000,
            "name": "HK6",
            "traits": ["神之騎士團"],
            "traits_en": ["Holy Knights"],
        },
        "HK7": {
            "card_id": "HK7",
            "card_type": "Character",
            "cost": 7,
            "power": 7000,
            "name": "HK7",
            "traits": ["神之騎士團"],
            "traits_en": ["Holy Knights"],
        },
        "TBP": {
            "card_id": "TBP",
            "card_type": "Character",
            "cost": 2,
            "power": 2000,
            "name": "TBP",
            "traits": ["恐怖三桅帆船海賊團"],
            "traits_en": ["Thriller Bark Pirates"],
        },
        "PLAIN": {"card_id": "PLAIN", "card_type": "Character", "cost": 2, "power": 2000, "name": "Plain"},
        "WANO6": {
            "card_id": "WANO6",
            "card_type": "Character",
            "cost": 3,
            "power": 6000,
            "name": "Wano6",
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
        },
        "WANO7": {
            "card_id": "WANO7",
            "card_type": "Character",
            "cost": 4,
            "power": 7000,
            "name": "Wano7",
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
        },
        "EV1": {"card_id": "EV1", "card_type": "Event", "cost": 1, "name": "Event1"},
        "EV2": {"card_id": "EV2", "card_type": "Event", "cost": 1, "name": "Event2"},
        "P6": {"card_id": "P6", "card_type": "Character", "cost": 1, "power": 6000, "name": "P6"},
        "P7": {"card_id": "P7", "card_type": "Character", "cost": 1, "power": 7000, "name": "P7"},
        "C2": {"card_id": "C2", "card_type": "Character", "cost": 2, "power": 2000, "name": "C2"},
        "C3": {"card_id": "C3", "card_type": "Character", "cost": 3, "power": 3000, "name": "C3"},
        "C5": {"card_id": "C5", "card_type": "Character", "cost": 5, "power": 4000, "name": "C5"},
        "C6": {"card_id": "C6", "card_type": "Character", "cost": 6, "power": 5000, "name": "C6"},
        "C7": {"card_id": "C7", "card_type": "Character", "cost": 7, "power": 7000, "name": "C7"},
        "HAND": {"card_id": "HAND", "card_type": "Character", "cost": 1, "power": 1000, "name": "Hand"},
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "Character", "cost": 1, "power": 1000, "name": cid}


def _players(
    *,
    hand: list[str] | None = None,
    chars: list[CardInst] | None = None,
    opp_chars: list[CardInst] | None = None,
    opp_hand: list[str] | None = None,
    trash: list[str] | None = None,
    stages: list[CardInst] | None = None,
    opp_stages: list[CardInst] | None = None,
    leader_rested: bool = False,
    deck: list[str] | None = None,
    leader: str = "OP01-001",
    opp_leader: str = "OP01-001",
    life: list[str] | None = None,
    opp_life: list[str] | None = None,
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
        life=list(life or ["L"] * 5),
        don_active=10,
        don_given=10,
        turns_completed=1,
        characters=list(chars or []),
        stages=list(stages or []),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id=opp_leader,
        deck=["Y"] * 20,
        hand=list(opp_hand or []),
        life=list(opp_life or ["M"] * 5),
        characters=list(opp_chars or []),
        stages=list(opp_stages or []),
        turns_completed=1,
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


def _accept(st: MatchState, seat: int = 0) -> None:
    if st.pending_effect is not None and st.pending_effect.seat == seat:
        assert apply_action(st, seat, {"type": "confirm_effect", "accept": True}, catalog)["ok"]


def _finish_search(st: MatchState, picks: list[int], seat: int = 0) -> None:
    assert st.pending_search is not None
    for index in picks:
        assert apply_action(st, seat, {"type": "select_search", "index": index}, catalog)["ok"]
    if st.pending_search is not None and st.pending_search.phase == "pick":
        assert apply_action(st, seat, {"type": "confirm_search"}, catalog)["ok"]
    while st.pending_search is not None and st.pending_search.phase == "order":
        acts = [a for a in legal_actions(st, seat, catalog) if a.get("type") == "order_search_bottom"]
        assert acts
        assert apply_action(st, seat, acts[0], catalog)["ok"]


def _counter_state(st: MatchState) -> MatchState:
    st.phase = "counter"
    st.turn_seat = 1
    st.attack = PendingAttack(
        attacker_seat=1,
        attacker_iid="leader",
        target_iid="leader",
        declared_power=5000,
        combat_entered=True,
    )
    return st


def test_batch2_overrides_are_runnable_and_close_timing_gaps():
    reload_effect_library(force=True)
    for cid in BATCH2:
        entry = get_card_entry(cid)
        runnable = [a for a in (entry.get("abilities") or []) if ability_is_runnable(a)]
        assert runnable, cid
        info = catalog(cid)
        assert has_meaningful_effect_text(effect_blob(info))
        assert not card_has_timing_gaps(info, entry.get("abilities") or []), cid


def test_eb05_004_reveal_events_then_draw_and_ko_plays_rested():
    reload_effect_library(force=True)
    st = _players(hand=["EB05-004", "EV1", "EV2", "PLAIN"], deck=["D1", "D2", "D3"])
    before = len(st.players[0].hand)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    ch = st.pending_choice
    assert ch is not None
    assert any(tok.endswith(":EV1") for tok in ch.options)
    assert not any(tok.endswith(":PLAIN") for tok in ch.options)
    pick = next(tok for tok in ch.options if tok.endswith(":EV1"))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    if st.pending_choice is not None:
        pick2 = next(tok for tok in st.pending_choice.options if tok.endswith(":EV2"))
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick2}, catalog)["ok"]
    assert len(st.players[0].hand) == before - 1 + 2
    assert "D1" in st.players[0].hand and "D2" in st.players[0].hand

    skipped = _players(hand=["EB05-004", "EV1", "EV2"], deck=["D1", "D2"])
    assert apply_action(skipped, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(skipped)
    assert apply_action(skipped, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert skipped.players[0].deck == ["D1", "D2"]

    ko = _players(hand=["P6", "P7"], chars=[CardInst(iid="baby", card_id="EB05-004", summoning_sick=False)])
    apply_battle_character_ko(ko, 0, ko.players[0].characters[0], catalog)
    ch = ko.pending_choice
    assert ch is not None
    assert any(tok.endswith(":P6") for tok in ch.options)
    assert not any(tok.endswith(":P7") for tok in ch.options)
    pick = next(tok for tok in ch.options if tok.endswith(":P6"))
    assert apply_action(ko, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    played = next(c for c in ko.players[0].characters if c.card_id == "P6")
    assert played.rested is True


def test_eb05_019_counter_rests_then_buffs_wano_and_trigger_plays():
    reload_effect_library(force=True)
    st = _players(
        leader="OP01-031",
        hand=["EB05-019"],
        chars=[
            CardInst(iid="wano", card_id="WANO6", summoning_sick=False),
            CardInst(iid="plain", card_id="PLAIN", summoning_sick=False),
        ],
    )
    _counter_state(st)
    before = inst_power(st, 0, "wano", catalog)
    assert apply_action(st, 0, {"type": "counter", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    assert st.pending_choice is not None
    assert "leader" in st.pending_choice.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "leader"}, catalog)["ok"]
    assert st.players[0].leader_rested is True
    assert st.pending_choice is not None
    assert "wano" in st.pending_choice.options
    assert "plain" not in st.pending_choice.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "wano"}, catalog)["ok"]
    assert inst_power(st, 0, "wano", catalog) == before + 4000

    trig = _players(leader="OP01-031", hand=["WANO6", "WANO7", "PLAIN"], opp_life=["M"] * 3)
    pending = resolve_ability(
        trig, 0, "EB05-019", "life", "trigger", catalog("EB05-019"), None, allow_llm=False, catalog=catalog
    )
    assert pending is not None
    _run_pending_effect(trig, pending, catalog)
    _accept(trig)
    assert trig.pending_choice is not None
    assert any(tok.endswith(":WANO6") for tok in trig.pending_choice.options)
    assert not any(tok.endswith(":WANO7") for tok in trig.pending_choice.options)
    pick = next(tok for tok in trig.pending_choice.options if tok.endswith(":WANO6"))
    assert apply_action(trig, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert any(c.card_id == "WANO6" for c in trig.players[0].characters)

    gated = _players(leader="OP01-031", hand=["WANO6"], opp_life=["M"] * 4)
    assert (
        resolve_ability(
            gated, 0, "EB05-019", "life", "trigger", catalog("EB05-019"), None, allow_llm=False, catalog=catalog
        )
        is None
    )


def test_eb05_030_nami_returns_cost5_and_counter_draws():
    reload_effect_library(force=True)
    st = _players(
        leader="OP03-040",
        hand=["EB05-030"],
        chars=[CardInst(iid="c5", card_id="C5", summoning_sick=False)],
        opp_chars=[
            CardInst(iid="c6", card_id="C6", summoning_sick=False),
            CardInst(iid="opp5", card_id="C5", rested=True, summoning_sick=False),
        ],
    )
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    assert st.pending_choice is not None
    assert "c5" in st.pending_choice.options
    assert "opp5" in st.pending_choice.options
    assert "c6" not in st.pending_choice.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "opp5"}, catalog)["ok"]
    assert "C5" in st.players[1].hand
    assert not any(c.iid == "opp5" for c in st.players[1].characters)

    other = _players(leader="OP01-060", hand=["EB05-030"], chars=[CardInst(iid="c5", card_id="C5")])
    assert apply_action(other, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert other.pending_choice is None
    assert any(c.iid == "c5" for c in other.players[0].characters)

    ctr = _players(leader="OP03-040", hand=["EB05-030"], deck=["D1", "D2"])
    _counter_state(ctr)
    before = inst_power(ctr, 0, "leader", catalog)
    hand_n = len(ctr.players[0].hand)
    assert apply_action(ctr, 0, {"type": "counter", "hand_index": 0}, catalog)["ok"]
    _accept(ctr)
    assert "D1" in ctr.players[0].hand
    assert ctr.pending_choice is not None
    assert "leader" in ctr.pending_choice.options
    assert apply_action(ctr, 0, {"type": "select_choice", "target_iid": "leader"}, catalog)["ok"]
    assert inst_power(ctr, 0, "leader", catalog) == before + 1000
    assert apply_action(ctr, 0, {"type": "pass_counter"}, catalog)["ok"]
    assert inst_power(ctr, 0, "leader", catalog) == before + 1000
    assert len(ctr.players[0].hand) == hand_n


def test_eb05_040_donquixote_returns_don_then_draws_and_counter_buffs():
    reload_effect_library(force=True)
    st = _players(leader="OP14-060", hand=["EB05-040"], deck=["D1", "D2", "D3", "D4"])
    active = st.players[0].don_active
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    assert st.pending_choice is not None
    assert "don:active" in st.pending_choice.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "don:active"}, catalog)["ok"]
    assert st.players[0].don_active == active - 1
    if st.pending_choice is not None:
        pick = st.pending_choice.options[0]
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert sum(1 for cid in ("D1", "D2", "D3") if cid in st.players[0].hand or cid in st.players[0].trash) == 3
    assert len(st.players[0].trash) >= 2

    wrong = _players(leader="OP09-061", hand=["EB05-040"], deck=["D1", "D2", "D3"])
    deck_n = len(wrong.players[0].deck)
    assert apply_action(wrong, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert wrong.pending_choice is None
    assert len(wrong.players[0].deck) == deck_n

    ctr = _players(leader="OP14-060", hand=["EB05-040"])
    _counter_state(ctr)
    before = inst_power(ctr, 0, "leader", catalog)
    assert apply_action(ctr, 0, {"type": "counter", "hand_index": 0}, catalog)["ok"]
    _accept(ctr)
    assert inst_power(ctr, 0, "leader", catalog) == before + 2000


def test_eb05_049_ko_thriller_bark_reduces_cost_and_counter_buffs():
    reload_effect_library(force=True)
    st = _players(
        leader="OP09-061",
        hand=["EB05-049"],
        chars=[
            CardInst(iid="tbp", card_id="TBP", summoning_sick=False),
            CardInst(iid="plain", card_id="PLAIN", summoning_sick=False),
        ],
        opp_chars=[CardInst(iid="vic", card_id="C5", summoning_sick=False)],
    )
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    assert st.pending_choice is not None
    assert "tbp" in st.pending_choice.options
    assert "plain" not in st.pending_choice.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "tbp"}, catalog)["ok"]
    if st.pending_choice is not None:
        assert "vic" in st.pending_choice.options
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": "vic"}, catalog)["ok"]
    assert "TBP" in st.players[0].trash
    vic = next(c for c in st.players[1].characters if c.iid == "vic")
    assert effective_character_cost(st, 1, vic, catalog) == 2

    skipped = _players(
        leader="OP09-061",
        hand=["EB05-049"],
        chars=[CardInst(iid="tbp", card_id="TBP", summoning_sick=False)],
        opp_chars=[CardInst(iid="vic", card_id="C5", summoning_sick=False)],
    )
    assert apply_action(skipped, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(skipped)
    assert apply_action(skipped, 0, {"type": "skip_choice"}, catalog)["ok"]
    vic2 = next(c for c in skipped.players[1].characters if c.iid == "vic")
    assert effective_character_cost(skipped, 1, vic2, catalog) == 5

    ctr = _players(
        leader="OP09-061",
        hand=["EB05-049"],
        chars=[CardInst(iid="tbp", card_id="TBP", summoning_sick=False)],
    )
    _counter_state(ctr)
    before = inst_power(ctr, 0, "leader", catalog)
    assert apply_action(ctr, 0, {"type": "counter", "hand_index": 0}, catalog)["ok"]
    _accept(ctr)
    assert apply_action(ctr, 0, {"type": "select_choice", "target_iid": "tbp"}, catalog)["ok"]
    if ctr.pending_choice is not None:
        assert apply_action(ctr, 0, {"type": "select_choice", "target_iid": "leader"}, catalog)["ok"]
    assert inst_power(ctr, 0, "leader", catalog) == before + 4000


def test_op18_011_animal_alabasta_aura_and_opponent_turn_blocker():
    reload_effect_library(force=True)
    vivi = CardInst(iid="vivi", card_id="OP18-011", summoning_sick=False)
    both = CardInst(iid="both", card_id="BOTH", summoning_sick=False)
    ani = CardInst(iid="ani", card_id="ANI", summoning_sick=False)
    st = _players(chars=[vivi, both, ani])
    assert inst_power(st, 0, "both", catalog) == 4000
    assert inst_power(st, 0, "ani", catalog) == 3000
    assert inst_power(st, 0, "vivi", catalog) == 0
    assert not has_blocker(catalog("OP18-011"), vivi, state=st, owner_seat=0, catalog=catalog)

    st.turn_seat = 1
    assert inst_power(st, 0, "both", catalog) == 4000
    assert inst_power(st, 0, "vivi", catalog) == 6000
    assert has_blocker(catalog("OP18-011"), vivi, state=st, owner_seat=0, catalog=catalog)


def test_op18_034_plays_trait_card_then_rests_if_stage_cost5():
    reload_effect_library(force=True)
    bare = _players(
        leader="OP01-031",
        hand=["OP18-034", "FF5", "FF6", "SH4", "STG4"],
        opp_chars=[CardInst(iid="c4", card_id="C5", rested=False, summoning_sick=False)],
    )
    assert apply_action(bare, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(bare)
    opts = bare.pending_choice.options
    assert any(tok.endswith(":FF5") for tok in opts)
    assert any(tok.endswith(":SH4") for tok in opts)
    assert any(tok.endswith(":STG4") for tok in opts)
    assert not any(tok.endswith(":FF6") for tok in opts)
    pick = next(tok for tok in opts if tok.endswith(":FF5"))
    assert apply_action(bare, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert any(c.card_id == "FF5" for c in bare.players[0].characters)
    assert bare.players[1].characters[0].rested is False

    staged = _players(
        leader="OP01-031",
        hand=["OP18-034", "SH4"],
        stages=[CardInst(iid="stg", card_id="STG5")],
        opp_chars=[
            CardInst(iid="low", card_id="C5", summoning_sick=False),
            CardInst(iid="mid", card_id="C6", summoning_sick=False),
            CardInst(iid="high", card_id="C7", summoning_sick=False),
        ],
    )
    assert apply_action(staged, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(staged)
    pick = next(tok for tok in staged.pending_choice.options if tok.endswith(":SH4"))
    assert apply_action(staged, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    low = next(c for c in staged.players[1].characters if c.iid == "low")
    mid = next(c for c in staged.players[1].characters if c.iid == "mid")
    high = next(c for c in staged.players[1].characters if c.iid == "high")
    if staged.pending_choice is not None:
        assert "low" in staged.pending_choice.options
        assert "mid" in staged.pending_choice.options
        assert "high" not in staged.pending_choice.options
        assert apply_action(staged, 0, {"type": "select_choice", "target_iid": "low"}, catalog)["ok"]
    assert low.rested is True
    assert mid.rested is False
    assert high.rested is False


def test_op18_061_looks_five_adds_stage_or_water_seven():
    reload_effect_library(force=True)
    deck = ["W7C", "STAGE", "NAVY", "W7C", "NAVY", "KEEP"]
    st = _players(leader="OP09-061", hand=["OP18-061"], deck=deck)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    revealed = list(st.pending_search.revealed or [])
    assert revealed[:5] == ["W7C", "STAGE", "NAVY", "W7C", "NAVY"]
    assert set(st.pending_search.eligible) == {0, 1, 3}
    _finish_search(st, [0, 1])
    assert st.players[0].hand.count("W7C") == 1
    assert "STAGE" in st.players[0].hand
    assert st.players[0].deck[-1] == "KEEP" or "KEEP" in st.players[0].deck
    assert st.players[0].deck[:1] == ["KEEP"] or st.players[0].deck[0] == "KEEP"


def test_op18_063_kos_cost5_stage_for_rested_don():
    reload_effect_library(force=True)
    st = _players(
        leader="OP09-061",
        hand=["OP18-063"],
        stages=[
            CardInst(iid="st5", card_id="STG5"),
            CardInst(iid="st6", card_id="ST6"),
        ],
    )
    st.players[0].don_given = 4
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    paid = st.players[0].don_rested
    assert st.pending_choice is not None
    assert "st5" in st.pending_choice.options
    assert "st6" not in st.pending_choice.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "st5"}, catalog)["ok"]
    assert not any(s.iid == "st5" for s in st.players[0].stages)
    assert "STG5" in st.players[0].trash
    assert st.players[0].don_rested == paid + 1

    skip = _players(leader="OP09-061", hand=["OP18-063"], stages=[CardInst(iid="st5", card_id="STG5")])
    skip.players[0].don_given = 4
    assert apply_action(skip, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(skip)
    paid_skip = skip.players[0].don_rested
    assert apply_action(skip, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert any(s.iid == "st5" for s in skip.players[0].stages)
    assert skip.players[0].don_rested == paid_skip


def test_op18_076_on_play_draws_and_attack_buffs_after_rest():
    reload_effect_library(force=True)
    st = _players(leader="OP09-061", hand=["OP18-076"], deck=["D1", "D2"])
    st.players[0].don_given = 4
    before = st.players[0].don_rested
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    assert "D1" in st.players[0].hand
    play_cost = int(catalog("OP18-076").get("cost") or 0)
    assert st.players[0].don_rested == before + play_cost + 1

    atk = _players(
        chars=[CardInst(iid="atk", card_id="PLAIN", summoning_sick=False)],
        opp_leader="OP09-061",
        opp_stages=[CardInst(iid="shark", card_id="OP18-076", rested=False)],
        opp_chars=[
            CardInst(iid="a", card_id="PLAIN", summoning_sick=False),
            CardInst(iid="b", card_id="C2", summoning_sick=False),
        ],
    )
    before_a = inst_power(atk, 1, "a", catalog)
    before_lead = inst_power(atk, 1, "leader", catalog)
    assert apply_action(atk, 0, {"type": "attack", "attacker_iid": "atk", "target_iid": "leader"}, catalog)["ok"]
    _accept(atk, 1)
    shark = next(s for s in atk.players[1].stages if s.iid == "shark")
    assert shark.rested is True
    assert atk.pending_choice is not None
    assert apply_action(atk, 1, {"type": "select_choice", "target_iid": "a"}, catalog)["ok"]
    if atk.pending_choice is not None and "b" in (atk.pending_choice.options or []):
        assert apply_action(atk, 1, {"type": "select_choice", "target_iid": "b"}, catalog)["ok"]
    assert inst_power(atk, 1, "a", catalog) == before_a + 1000
    assert inst_power(atk, 1, "leader", catalog) == before_lead + 1000

    tall = _players(
        chars=[CardInst(iid="atk", card_id="PLAIN", summoning_sick=False)],
        opp_stages=[CardInst(iid="shark", card_id="OP18-076", rested=False)],
        opp_chars=[CardInst(iid="a", card_id="PLAIN", summoning_sick=False)],
    )
    tall.players[1].leader_power_mod = 2000
    before_lead = inst_power(tall, 1, "leader", catalog)
    assert before_lead > 5000
    assert apply_action(tall, 0, {"type": "attack", "attacker_iid": "atk", "target_iid": "leader"}, catalog)["ok"]
    _accept(tall, 1)
    if tall.pending_choice is not None:
        assert "leader" not in tall.pending_choice.options
        assert apply_action(tall, 1, {"type": "select_choice", "target_iid": "a"}, catalog)["ok"]
    assert inst_power(tall, 1, "leader", catalog) == before_lead


def test_op18_084_looks_four_and_activate_plays_from_trash():
    reload_effect_library(force=True)
    deck = ["HK6", "NAVY", "PLAIN", "HK7", "KEEP"]
    st = _players(leader="OP09-061", hand=["OP18-084"], deck=deck)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    revealed = list(st.pending_search.revealed or [])
    assert revealed == ["HK6", "NAVY", "PLAIN", "HK7"]
    assert set(st.pending_search.eligible) == {0, 3}
    _finish_search(st, [0])
    assert "HK6" in st.players[0].hand
    assert "NAVY" in st.players[0].trash and "PLAIN" in st.players[0].trash and "HK7" in st.players[0].trash
    assert st.players[0].deck[0] == "KEEP"

    gunko = next(c for c in st.players[0].characters if c.card_id == "OP18-084")
    st.players[0].trash = ["HK7", "HK6"]
    st.players[0].don_active = 6
    st.phase = "main"
    st.turn_seat = 0
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": gunko.iid}, catalog)["ok"]
    _accept(st)
    assert st.pending_choice is not None
    assert "don" in st.pending_choice.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "don"}, catalog)["ok"]
    assert st.players[0].don_active == 2
    assert st.pending_choice is not None
    assert any(tok.endswith(":HK6") for tok in st.pending_choice.options)
    assert not any(tok.endswith(":HK7") for tok in st.pending_choice.options)
    pick = next(tok for tok in st.pending_choice.options if tok.endswith(":HK6"))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert any(c.card_id == "HK6" for c in st.players[0].characters)
    assert "HK6" not in st.players[0].trash


def test_op18_091_cost_plus_12_and_attack_adds_cost2_from_trash():
    reload_effect_library(force=True)
    brogy = CardInst(iid="brogy", card_id="OP18-091", summoning_sick=False)
    st = _players(leader="OP09-061", chars=[brogy], hand=["HAND"], trash=["C2", "C3"])
    assert effective_character_cost(st, 0, brogy, catalog) == 16
    st.turn_seat = 1
    assert effective_character_cost(st, 0, brogy, catalog) == 16
    st.turn_seat = 0
    assert apply_action(st, 0, {"type": "attack", "attacker_iid": "brogy", "target_iid": "leader"}, catalog)["ok"]
    _accept(st)
    assert st.pending_choice is not None
    pick = next(tok for tok in st.pending_choice.options if tok.endswith(":HAND"))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    if st.pending_choice is not None:
        assert any(tok.endswith(":C2") for tok in st.pending_choice.options)
        assert not any(tok.endswith(":C3") for tok in st.pending_choice.options)
        add = next(tok for tok in st.pending_choice.options if tok.endswith(":C2"))
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": add}, catalog)["ok"]
    assert "C2" in st.players[0].hand
    assert "HAND" in st.players[0].trash
    assert "C3" in st.players[0].trash
