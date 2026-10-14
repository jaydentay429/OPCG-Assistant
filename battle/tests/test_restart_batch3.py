"""Battle restart batch 3: EB05/OP18/P overrides that were still lacking runnable effects."""

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
)
from battle.effects import apply_ops, effect_blob, has_blocker, has_meaningful_effect_text  # noqa: E402
from battle.engine import (  # noqa: E402
    _clear_turn_duration_effects,
    _run_pending_effect,
    apply_action,
    apply_battle_character_ko,
    inst_power,
    legal_actions,
)
from battle.leave_replace import try_replace_leave  # noqa: E402
from battle.state import CardInst, MatchState, PendingAttack, PlayerState  # noqa: E402
from battle.effect_library import resolve_ability  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))

BATCH3 = [
    "EB05-008",
    "EB05-031",
    "EB05-046",
    "EB05-059",
    "EB05-061",
    "OP18-017",
    "OP18-046",
    "OP18-069",
    "OP18-100",
    "OP18-113",
    "P-160",
]


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "EVR": {"card_id": "EVR", "card_type": "Event", "cost": 1, "name": "Red Event", "colors": ["紅"]},
        "EVR2": {"card_id": "EVR2", "card_type": "Event", "cost": 1, "name": "Red Event 2", "colors": ["紅"]},
        "EVB": {"card_id": "EVB", "card_type": "Event", "cost": 1, "name": "Blue Event", "colors": ["藍"]},
        "RED2": {"card_id": "RED2", "card_type": "Character", "cost": 2, "power": 2000, "name": "Red2", "colors": ["紅"]},
        "RED3": {"card_id": "RED3", "card_type": "Character", "cost": 3, "power": 3000, "name": "Red3", "colors": ["紅"]},
        "BLU2": {"card_id": "BLU2", "card_type": "Character", "cost": 2, "power": 2000, "name": "Blu2", "colors": ["藍"]},
        "C5": {"card_id": "C5", "card_type": "Character", "cost": 5, "power": 5000, "name": "C5"},
        "P8": {"card_id": "P8", "card_type": "Character", "cost": 8, "power": 8000, "name": "P8"},
        "P7": {"card_id": "P7", "card_type": "Character", "cost": 7, "power": 7000, "name": "P7"},
        "P6": {"card_id": "P6", "card_type": "Character", "cost": 4, "power": 6000, "name": "P6"},
        "P4": {"card_id": "P4", "card_type": "Character", "cost": 2, "power": 4000, "name": "P4"},
        "BMP": {
            "card_id": "BMP",
            "card_type": "Character",
            "cost": 3,
            "power": 4000,
            "name": "BMP",
            "traits": ["BIG MOM海賊團"],
            "traits_en": ["Big Mom Pirates"],
        },
        "BMP5": {
            "card_id": "BMP5",
            "card_type": "Character",
            "cost": 4,
            "power": 5000,
            "name": "BMP5",
            "traits": ["BIG MOM海賊團"],
            "traits_en": ["Big Mom Pirates"],
        },
        "ALA": {
            "card_id": "ALA",
            "card_type": "Character",
            "cost": 3,
            "power": 4000,
            "name": "Ala",
            "traits": ["阿拉巴斯坦王國"],
            "traits_en": ["Alabasta"],
        },
        "FF": {
            "card_id": "FF",
            "card_type": "Character",
            "cost": 3,
            "power": 4000,
            "name": "FF",
            "traits": ["佛朗基一家"],
            "traits_en": ["Franky Family"],
        },
        "CP9": {
            "card_id": "CP9",
            "card_type": "Character",
            "cost": 4,
            "power": 4000,
            "name": "CP9",
            "traits": ["CP9"],
            "traits_en": ["CP9"],
        },
        "C8": {"card_id": "C8", "card_type": "Character", "cost": 8, "power": 8000, "name": "C8"},
        "C9": {"card_id": "C9", "card_type": "Character", "cost": 9, "power": 9000, "name": "C9"},
        "WIS": {
            "card_id": "WIS",
            "card_type": "Character",
            "cost": 2,
            "power": 2000,
            "name": "Wis",
            "attributes": ["知"],
            "attributes_en": ["Wisdom"],
        },
        "STR": {
            "card_id": "STR",
            "card_type": "Character",
            "cost": 2,
            "power": 2000,
            "name": "Str",
            "attributes": ["打"],
            "attributes_en": ["Strike"],
        },
        "TRIG4": {
            "card_id": "TRIG4",
            "card_type": "Character",
            "cost": 2,
            "power": 4000,
            "name": "Trig4",
            "trigger": "[Trigger] Draw 1 card.",
        },
        "TRIG5": {
            "card_id": "TRIG5",
            "card_type": "Character",
            "cost": 3,
            "power": 5000,
            "name": "Trig5",
            "trigger": "[Trigger] Draw 1 card.",
        },
        "VINS": {
            "card_id": "VINS",
            "card_type": "Leader",
            "cost": 0,
            "power": 5000,
            "life": 5,
            "name": "Vins",
            "colors": ["紫"],
            "traits": ["賓什莫克家"],
            "traits_en": ["The Vinsmoke Family"],
        },
        "PLEAD": {
            "card_id": "PLEAD",
            "card_type": "Leader",
            "cost": 0,
            "power": 5000,
            "life": 5,
            "name": "Purple",
            "colors": ["紫"],
        },
        "YLEAD": {
            "card_id": "YLEAD",
            "card_type": "Leader",
            "cost": 0,
            "power": 5000,
            "life": 5,
            "name": "Yellow",
            "colors": ["黃"],
        },
        "BLEAD": {
            "card_id": "BLEAD",
            "card_type": "Leader",
            "cost": 0,
            "power": 5000,
            "life": 5,
            "name": "Blue",
            "colors": ["藍"],
        },
        "BWLEAD": {
            "card_id": "BWLEAD",
            "card_type": "Leader",
            "cost": 0,
            "power": 5000,
            "life": 5,
            "name": "BW",
            "colors": ["藍"],
            "traits": ["B・W"],
            "traits_en": ["Baroque Works"],
        },
        "CPLEAD": {
            "card_id": "CPLEAD",
            "card_type": "Leader",
            "cost": 0,
            "power": 5000,
            "life": 5,
            "name": "CP",
            "colors": ["黃"],
            "traits": ["CP9"],
            "traits_en": ["CP9"],
        },
        "JUNK": {"card_id": "JUNK", "card_type": "Character", "cost": 1, "power": 1000, "name": "Junk"},
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "Character", "cost": 1, "power": 1000, "name": cid}


def _players(
    *,
    hand: list[str] | None = None,
    chars: list[CardInst] | None = None,
    opp_chars: list[CardInst] | None = None,
    opp_hand: list[str] | None = None,
    trash: list[str] | None = None,
    deck: list[str] | None = None,
    leader: str = "OP01-001",
    opp_leader: str = "OP01-001",
    life: list[str] | None = None,
    opp_life: list[str] | None = None,
    turn_seat: int = 0,
    don_active: int = 10,
    don_rested: int = 0,
    don_given: int = 10,
) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=leader,
        deck=list(deck or ["X"] * 20),
        hand=list(hand or []),
        trash=list(trash or []),
        life=list(life or ["L"] * 5),
        don_active=don_active,
        don_rested=don_rested,
        don_given=don_given,
        turns_completed=1,
        characters=list(chars or []),
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
        don_active=10,
        don_given=10,
        turns_completed=1,
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=turn_seat,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def _accept(st: MatchState, seat: int = 0) -> None:
    if st.pending_effect is not None and st.pending_effect.seat == seat:
        assert apply_action(st, seat, {"type": "confirm_effect", "accept": True}, catalog)["ok"]


def _pick(st: MatchState, suffix: str, seat: int = 0) -> None:
    ch = st.pending_choice
    assert ch is not None, suffix
    tok = next(t for t in ch.options if str(t).endswith(suffix) or t == suffix)
    assert apply_action(st, seat, {"type": "select_choice", "target_iid": tok}, catalog)["ok"]


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


def test_batch3_overrides_are_runnable_and_close_timing_gaps():
    reload_effect_library(force=True)
    for cid in BATCH3:
        entry = get_card_entry(cid)
        runnable = [a for a in (entry.get("abilities") or []) if ability_is_runnable(a)]
        assert runnable, cid
        info = catalog(cid)
        assert has_meaningful_effect_text(effect_blob(info))
        assert not card_has_timing_gaps(info, entry.get("abilities") or []), cid


def test_eb05_008_main_debuffs_rested_and_counter_needs_no_cost5():
    reload_effect_library(force=True)
    st = _players(
        hand=["EB05-008", "EVR", "EVR2", "EVB"],
        opp_chars=[
            CardInst(iid="rested", card_id="P4", rested=True, summoning_sick=False),
            CardInst(iid="active", card_id="P6", rested=False, summoning_sick=False),
        ],
    )
    before = inst_power(st, 1, "rested", catalog)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    assert st.players[0].leader_don == 1
    ch = st.pending_choice
    assert ch is not None
    assert any(tok.endswith(":EVR") for tok in ch.options)
    assert not any(tok.endswith(":EVB") for tok in ch.options)
    _pick(st, ":EVR")
    _pick(st, ":EVR2")
    assert "rested" in st.pending_choice.options
    assert "active" not in st.pending_choice.options
    _pick(st, "rested")
    assert inst_power(st, 1, "rested", catalog) == before - 7000

    blocked = _players(hand=["EB05-008"], chars=[CardInst(iid="big", card_id="C5", summoning_sick=False)])
    _counter_state(blocked)
    lead_before = inst_power(blocked, 0, "leader", catalog)
    assert apply_action(blocked, 0, {"type": "counter", "hand_index": 0}, catalog)["ok"]
    _accept(blocked)
    assert blocked.pending_choice is None
    assert inst_power(blocked, 0, "leader", catalog) == lead_before

    ok = _players(hand=["EB05-008"], chars=[CardInst(iid="small", card_id="P4", summoning_sick=False)])
    _counter_state(ok)
    before_lead = inst_power(ok, 0, "leader", catalog)
    assert apply_action(ok, 0, {"type": "counter", "hand_index": 0}, catalog)["ok"]
    _accept(ok)
    assert "leader" in ok.pending_choice.options
    _pick(ok, "leader")
    assert inst_power(ok, 0, "leader", catalog) == before_lead + 4000


def test_eb05_031_trashes_deck_for_vinsmoke_and_gains_don():
    reload_effect_library(force=True)
    deck = [f"D{i}" for i in range(12)]
    st = _players(hand=["EB05-031"], deck=deck, leader="VINS", don_active=10, don_given=10)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    assert st.pending_choice is not None
    _pick(st, "don:active")
    assert len(st.players[0].deck) == 2
    assert len(st.players[0].trash) == 10

    whiff = _players(hand=["EB05-031"], deck=list(deck), leader="PLEAD")
    assert apply_action(whiff, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(whiff)
    _pick(whiff, "don:active")
    assert len(whiff.players[0].deck) == 12

    act = _players(
        chars=[CardInst(iid="reiju", card_id="EB05-031", summoning_sick=False)],
        opp_chars=[CardInst(iid="big", card_id="P8", summoning_sick=False)],
        don_active=2,
        don_given=2,
    )
    assert apply_action(act, 0, {"type": "activate_main", "source_iid": "reiju"}, catalog)["ok"]
    _pick(act, "reiju")
    assert all(c.card_id != "EB05-031" for c in act.players[0].characters)
    assert act.players[0].don_active == 6
    assert act.players[0].don_given == 6

    no_big = _players(
        chars=[CardInst(iid="reiju", card_id="EB05-031", summoning_sick=False)],
        opp_chars=[CardInst(iid="small", card_id="P4", summoning_sick=False)],
        don_active=2,
        don_given=2,
    )
    assert apply_action(no_big, 0, {"type": "activate_main", "source_iid": "reiju"}, catalog)["ok"]
    _pick(no_big, "reiju")
    assert no_big.players[0].don_active == 2
    assert no_big.players[0].don_given == 2


def test_eb05_046_aura_and_trash_sets_leader_base():
    reload_effect_library(force=True)
    bare = _players(chars=[CardInst(iid="yama", card_id="EB05-046", summoning_sick=False)])
    info = catalog("EB05-046")
    assert not has_blocker(info, bare.players[0].characters[0], state=bare, owner_seat=0, catalog=catalog)
    assert inst_power(bare, 0, "yama", catalog) == 5000

    aura = _players(
        chars=[CardInst(iid="yama", card_id="EB05-046", summoning_sick=False)],
        opp_chars=[CardInst(iid="big", card_id="P8", summoning_sick=False)],
    )
    yama = aura.players[0].characters[0]
    assert has_blocker(info, yama, state=aura, owner_seat=0, catalog=catalog)
    assert inst_power(aura, 0, "yama", catalog) == 8000

    st = _players(
        chars=[CardInst(iid="yama", card_id="EB05-046", summoning_sick=False)],
        hand=["JUNK"],
        trash=["T"] * 9,
        turn_seat=1,
    )
    st.phase = "main"
    assert apply_action(st, 1, {"type": "attack", "attacker_iid": "leader", "target_iid": "leader"}, catalog)["ok"]
    _accept(st, 0)
    _pick(st, ":JUNK", 0)
    assert inst_power(st, 0, "leader", catalog) == 7000

    short = _players(
        chars=[CardInst(iid="yama", card_id="EB05-046", summoning_sick=False)],
        hand=["JUNK"],
        trash=["T"] * 8,
        turn_seat=1,
    )
    before = inst_power(short, 0, "leader", catalog)
    assert apply_action(short, 1, {"type": "attack", "attacker_iid": "leader", "target_iid": "leader"}, catalog)["ok"]
    _accept(short, 0)
    _pick(short, ":JUNK", 0)
    assert inst_power(short, 0, "leader", catalog) == before


def test_eb05_059_battle_shield_and_trigger_play():
    reload_effect_library(force=True)
    st = _players(
        leader="YLEAD",
        hand=["EB05-059"],
        deck=["D1", "D2"],
        chars=[
            CardInst(iid="bmp", card_id="BMP", summoning_sick=False),
            CardInst(iid="big", card_id="BMP5", summoning_sick=False),
            CardInst(iid="plain", card_id="P4", summoning_sick=False),
        ],
    )
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    assert "D1" in st.players[0].hand
    bmp = next(c for c in st.players[0].characters if c.iid == "bmp")
    other = next(c for c in st.players[0].characters if c.iid == "big")
    assert bmp.battle_ko_shields
    assert not other.battle_ko_shields
    assert not next(c for c in st.players[0].characters if c.iid == "plain").battle_ko_shields
    apply_battle_character_ko(st, 0, bmp, catalog)
    assert any(c.iid == "bmp" for c in st.players[0].characters)
    apply_ops(st, 1, [{"op": "ko", "target_iid": "bmp", "target_kind": "opponent_character", "optional": False}], catalog)
    assert all(c.iid != "bmp" for c in st.players[0].characters)

    shield = _players(chars=[CardInst(iid="bmp", card_id="BMP", summoning_sick=False)])
    pending = resolve_ability(
        shield, 0, "EB05-059", "life", "on_play", catalog("EB05-059"), None, allow_llm=False, catalog=catalog
    )
    assert pending is not None
    _run_pending_effect(shield, pending, catalog)
    _accept(shield)
    bmp = shield.players[0].characters[0]
    assert bmp.battle_ko_shields
    shield.turn_seat = 0
    _clear_turn_duration_effects(shield)
    assert bmp.battle_ko_shields
    shield.turn_seat = 1
    _clear_turn_duration_effects(shield)
    assert not bmp.battle_ko_shields

    trig = _players(leader="YLEAD", hand=["TRIG4", "TRIG5", "P4"], deck=["N1"])
    pending = resolve_ability(
        trig, 0, "EB05-059", "life", "trigger", catalog("EB05-059"), None, allow_llm=False, catalog=catalog
    )
    assert pending is not None
    _run_pending_effect(trig, pending, catalog)
    _accept(trig)
    assert "N1" in trig.players[0].hand
    assert any(tok.endswith(":TRIG4") for tok in trig.pending_choice.options)
    assert not any(tok.endswith(":TRIG5") for tok in trig.pending_choice.options)
    assert not any(tok.endswith(":P4") for tok in trig.pending_choice.options)
    _pick(trig, ":TRIG4")
    assert any(c.card_id == "TRIG4" for c in trig.players[0].characters)


def test_eb05_061_replaces_leave_and_plays_red():
    reload_effect_library(force=True)
    st = _players(
        chars=[
            CardInst(iid="nami", card_id="EB05-061", summoning_sick=False),
            CardInst(iid="small", card_id="P6", summoning_sick=False),
            CardInst(iid="big", card_id="P7", summoning_sick=False),
        ],
        life=["TOP", "BOT"],
    )
    victim = next(c for c in st.players[0].characters if c.iid == "small")
    assert try_replace_leave(st, 0, victim, by_opponent=True, catalog=catalog) is True
    _accept(st)
    assert any(c.iid == "small" for c in st.players[0].characters)
    assert st.players[0].life == ["BOT"]
    assert "TOP" in st.players[0].hand
    big = next(c for c in st.players[0].characters if c.iid == "big")
    assert try_replace_leave(st, 0, big, by_opponent=True, catalog=catalog) is False
    again = next(c for c in st.players[0].characters if c.iid == "small")
    assert try_replace_leave(st, 0, again, by_opponent=True, catalog=catalog) is False

    play = _players(hand=["EB05-061", "RED2", "RED3", "BLU2"])
    assert apply_action(play, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(play)
    assert any(tok.endswith(":RED2") for tok in play.pending_choice.options)
    assert not any(tok.endswith(":RED3") for tok in play.pending_choice.options)
    assert not any(tok.endswith(":BLU2") for tok in play.pending_choice.options)
    _pick(play, ":RED2")
    assert any(c.card_id == "RED2" for c in play.players[0].characters)


def test_op18_017_effect_replace_and_rush():
    reload_effect_library(force=True)
    st = _players(
        chars=[
            CardInst(iid="zoro", card_id="OP18-017", summoning_sick=False),
            CardInst(iid="ala", card_id="ALA", summoning_sick=False),
            CardInst(iid="plain", card_id="P4", summoning_sick=False),
        ]
    )
    ala = next(c for c in st.players[0].characters if c.iid == "ala")
    before = inst_power(st, 0, "leader", catalog)
    assert try_replace_leave(st, 0, ala, by_opponent=True, catalog=catalog, by_ko=True, by_effect=False) is False
    assert try_replace_leave(st, 0, ala, by_opponent=True, catalog=catalog, by_ko=False, by_effect=True) is True
    _accept(st)
    assert any(c.iid == "ala" for c in st.players[0].characters)
    assert inst_power(st, 0, "leader", catalog) == before - 2000
    plain = next(c for c in st.players[0].characters if c.iid == "plain")
    assert try_replace_leave(st, 0, plain, by_opponent=True, catalog=catalog, by_effect=True) is False

    rush = _players(
        chars=[
            CardInst(iid="zoro", card_id="OP18-017", summoning_sick=False),
            CardInst(iid="ala", card_id="ALA", summoning_sick=True),
            CardInst(iid="plain", card_id="P4", summoning_sick=True),
        ]
    )
    assert apply_action(rush, 0, {"type": "attack", "attacker_iid": "zoro", "target_iid": "leader"}, catalog)["ok"]
    _accept(rush)
    assert "ala" in rush.pending_choice.options
    assert "plain" not in rush.pending_choice.options
    _pick(rush, "ala")
    granted = next(c for c in rush.players[0].characters if c.iid == "ala")
    assert "rush" in granted.turn_keywords
    assert granted.summoning_sick is False


def test_op18_046_attaches_rested_don_and_sets_baroque_leader():
    reload_effect_library(force=True)
    st = _players(
        leader="BLEAD",
        hand=["OP18-046"],
        deck=["D1", "D2", "D3"],
        chars=[CardInst(iid="ally", card_id="P4", summoning_sick=False)],
        don_active=10,
        don_rested=0,
        don_given=10,
    )
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    assert "D1" in st.players[0].hand and "D2" in st.players[0].hand
    played = next(c for c in st.players[0].characters if c.card_id == "OP18-046")
    ally = next(c for c in st.players[0].characters if c.iid == "ally")
    assert st.players[0].leader_don == 2
    assert played.don_attached == 2
    assert ally.don_attached == 2

    bw = _players(
        leader="BWLEAD",
        chars=[CardInst(iid="mr0", card_id="OP18-046", summoning_sick=False)],
        hand=["JUNK"],
        turn_seat=1,
    )
    assert apply_action(bw, 1, {"type": "attack", "attacker_iid": "leader", "target_iid": "leader"}, catalog)["ok"]
    _accept(bw, 0)
    _pick(bw, ":JUNK", 0)
    assert inst_power(bw, 0, "leader", catalog) == 7000

    other = _players(
        leader="BLEAD",
        chars=[CardInst(iid="mr0", card_id="OP18-046", summoning_sick=False)],
        hand=["JUNK"],
        turn_seat=1,
    )
    before = inst_power(other, 0, "leader", catalog)
    assert apply_action(other, 1, {"type": "attack", "attacker_iid": "leader", "target_iid": "leader"}, catalog)["ok"]
    _accept(other, 0)
    _pick(other, ":JUNK", 0)
    assert inst_power(other, 0, "leader", catalog) == before


def test_op18_069_returns_don_and_rests_instead_of_ko():
    reload_effect_library(force=True)
    st = _players(
        chars=[
            CardInst(iid="sodom", card_id="OP18-069", summoning_sick=False),
            CardInst(iid="ff", card_id="FF", summoning_sick=False),
        ],
        don_active=0,
        don_rested=2,
        don_given=2,
    )
    victim = next(c for c in st.players[0].characters if c.iid == "ff")
    assert try_replace_leave(st, 0, victim, by_opponent=True, catalog=catalog) is True
    _accept(st)
    assert any(c.iid == "ff" for c in st.players[0].characters)
    sodom = next(c for c in st.players[0].characters if c.iid == "sodom")
    assert sodom.rested is True
    assert st.players[0].don_rested == 1

    rested = _players(
        chars=[
            CardInst(iid="sodom", card_id="OP18-069", rested=True, summoning_sick=False),
            CardInst(iid="ff", card_id="FF", summoning_sick=False),
        ],
        don_rested=2,
        don_given=2,
        don_active=0,
    )
    victim = next(c for c in rested.players[0].characters if c.iid == "ff")
    assert try_replace_leave(rested, 0, victim, by_opponent=True, catalog=catalog) is False


def test_op18_100_adds_cp_life_and_trigger_rests():
    reload_effect_library(force=True)
    st = _players(leader="YLEAD", hand=["OP18-100", "CP9", "JUNK"], deck=["D1", *["X"] * 10], life=["L1"])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    assert "D1" in st.players[0].hand
    assert any(tok.endswith(":CP9") for tok in st.pending_choice.options)
    assert not any(tok.endswith(":JUNK") for tok in st.pending_choice.options)
    _pick(st, ":CP9")
    assert "life:bottom" in st.pending_choice.options
    _pick(st, "life:bottom")
    assert st.players[0].life[-1] == "CP9"
    assert st.players[0].life_face[-1] is True

    trig = _players(
        leader="CPLEAD",
        hand=["OP18-100"],
        deck=["N1", *["X"] * 10],
        opp_chars=[CardInst(iid="opp", card_id="P4", rested=False, summoning_sick=False)],
    )
    pending = resolve_ability(
        trig, 0, "OP18-100", "life", "trigger", catalog("OP18-100"), None, allow_llm=False, catalog=catalog
    )
    assert pending is not None
    _run_pending_effect(trig, pending, catalog)
    _accept(trig)
    assert "N1" in trig.players[0].hand
    assert "leader" in trig.pending_choice.options
    assert "opp" in trig.pending_choice.options
    _pick(trig, "opp")
    assert next(c for c in trig.players[1].characters if c.iid == "opp").rested is True

    gated = _players(leader="YLEAD", hand=["OP18-100"], deck=["N1"], life=["L"] * 5)
    before = len(gated.players[0].hand)
    pending = resolve_ability(
        gated, 0, "OP18-100", "life", "trigger", catalog("OP18-100"), None, allow_llm=False, catalog=catalog
    )
    assert pending is None
    assert gated.players[0].deck == ["N1"]
    assert len(gated.players[0].hand) == before


def test_op18_113_trashes_life_and_trigger_bottoms_cost():
    reload_effect_library(force=True)
    st = _players(leader="YLEAD", hand=["OP18-113"], opp_life=["TOP", "MID"])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    assert st.players[1].life == ["MID"]
    assert st.players[1].trash == ["TOP"]

    ko = _players(
        chars=[CardInst(iid="lucci", card_id="OP18-113", summoning_sick=False)],
        opp_life=["A", "B"],
    )
    apply_battle_character_ko(ko, 0, ko.players[0].characters[0], catalog)
    _accept(ko)
    assert ko.players[1].life == ["B"]
    assert "A" in ko.players[1].trash

    trig = _players(
        leader="CPLEAD",
        hand=["OP18-113"],
        deck=["N1", *["X"] * 10],
        chars=[CardInst(iid="c8", card_id="C8", summoning_sick=False)],
        opp_chars=[CardInst(iid="c9", card_id="C9", summoning_sick=False)],
    )
    pending = resolve_ability(
        trig, 0, "OP18-113", "life", "trigger", catalog("OP18-113"), None, allow_llm=False, catalog=catalog
    )
    assert pending is not None
    _run_pending_effect(trig, pending, catalog)
    _accept(trig)
    assert "N1" in trig.players[0].hand
    assert "c8" in trig.pending_choice.options
    assert "c9" not in trig.pending_choice.options
    _pick(trig, "c8")
    assert trig.players[0].deck[-1] == "C8"
    assert all(c.iid != "c8" for c in trig.players[0].characters)


def test_p160_searches_wisdom_and_trigger_plays_at_low_life():
    reload_effect_library(force=True)
    deck = ["WIS", "STR", "JUNK", "P4", "P6", "TAIL"]
    st = _players(leader="YLEAD", hand=["P-160", "JUNK"], deck=deck)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _accept(st)
    assert st.pending_search is not None
    assert st.pending_search.eligible == [0]
    _finish_search(st, [0])
    assert "WIS" in st.players[0].hand
    assert st.players[0].deck[-4:] == ["STR", "JUNK", "P4", "P6"] or set(st.players[0].deck[-4:]) == {
        "STR",
        "JUNK",
        "P4",
        "P6",
    }
    assert st.pending_choice is not None
    _pick(st, ":JUNK")
    assert "JUNK" in st.players[0].trash
    assert "WIS" in st.players[0].hand

    low = _players(leader="YLEAD", hand=["P-160"], life=["L1", "L2"])
    pending = resolve_ability(
        low, 0, "P-160", "life", "trigger", catalog("P-160"), None, allow_llm=False, catalog=catalog
    )
    assert pending is not None
    _run_pending_effect(low, pending, catalog)
    _accept(low)
    assert any(c.card_id == "P-160" for c in low.players[0].characters)

    high = _players(leader="YLEAD", hand=["P-160"], life=["L1", "L2", "L3"])
    pending = resolve_ability(
        high, 0, "P-160", "life", "trigger", catalog("P-160"), None, allow_llm=False, catalog=catalog
    )
    assert pending is None
    assert all(c.card_id != "P-160" for c in high.players[0].characters)
