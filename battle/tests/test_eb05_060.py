"""EB05-060 I'm Counting on Lilith!!!: Main trash cost≥5 Egghead → deck top to Life; Counter flip Life → +4000 battle."""

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
from battle.engine import _confirm_effect, apply_action, inst_power  # noqa: E402
from battle.state import CardInst, MatchState, PendingAttack, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "EGG5": {
            "card_id": "EGG5",
            "card_type": "CHARACTER",
            "cost": 5,
            "power": 6000,
            "name": "Egg5",
            "traits": ["蛋頭", "科學家"],
        },
        "EGG2": {
            "card_id": "EGG2",
            "card_type": "CHARACTER",
            "cost": 2,
            "power": 2000,
            "name": "Egg2",
            "traits": ["蛋頭"],
        },
        "NOEGG": {
            "card_id": "NOEGG",
            "card_type": "CHARACTER",
            "cost": 5,
            "power": 6000,
            "name": "NoEgg",
            "traits": ["草帽一行人"],
        },
        "OP01-001": {"card_id": "OP01-001", "card_type": "LEADER", "power": 5000, "name": "Luffy"},
        "D0": {"card_id": "D0", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "D0"},
        "LIFE": {"card_id": "LIFE", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "Life"},
        "Y": {"card_id": "Y", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "Y"},
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _main_state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="ST07-001",
        deck=["D0"] + ["X"] * 19,
        hand=["EB05-060"],
        life=["LIFE"] * 5,
        life_face=[False] * 5,
        don_active=2,
        don_given=2,
        turns_completed=1,
        characters=[
            CardInst(iid="egg5", card_id="EGG5", rested=False, summoning_sick=False),
            CardInst(iid="egg2", card_id="EGG2", rested=False, summoning_sick=False),
            CardInst(iid="noegg", card_id="NOEGG", rested=False, summoning_sick=False),
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
        life=["Y"] * 5,
        characters=[CardInst(iid="opp", card_id="EGG5", rested=False, summoning_sick=False)],
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


def test_eb05_060_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-060")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-060 abilities dropped on normalize"
    main = next(a for a in get_abilities("EB05-060", "on_play"))
    trash = main["ops"][0]
    assert trash.get("op") == "trash"
    assert trash.get("as_cost") is True
    assert trash.get("target_kind") == "own_character"
    assert trash.get("cost_gte") == 5
    assert "蛋頭" in str(trash.get("trait_contains") or "")
    add = main["ops"][1]
    assert add.get("op") == "add_life"
    assert add.get("position") == "top"
    ctr = next(a for a in get_abilities("EB05-060", "counter_event"))
    flip = ctr["ops"][0]
    assert flip.get("op") == "flip_life"
    assert flip.get("face") == "up"
    assert flip.get("as_cost") is True
    buff = ctr["ops"][1]
    assert buff.get("op") == "buff"
    assert buff.get("amount") == 4000
    assert buff.get("duration") == "battle"
    assert buff.get("target_kind") == "own_leader_or_character"
    info = catalog("EB05-060")
    assert has_counter_timing(info) is True


def test_eb05_060_main_trashes_cost5_egghead_and_adds_deck_to_life():
    reload_effect_library(force=True)
    st = _main_state()
    life_n = len(st.players[0].life)
    deck0 = st.players[0].deck[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert "EB05-060" in st.players[0].trash
    if st.pending_effect is not None:
        _confirm_effect(st, 0, True, catalog)
    assert st.pending_choice is not None
    opts = st.pending_choice.options or []
    assert "egg5" in opts
    assert "egg2" not in opts
    assert "noegg" not in opts
    assert "opp" not in opts
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "egg5"}, catalog)["ok"]
    assert st.pending_choice is None
    assert "EGG5" in st.players[0].trash
    assert not any(c.iid == "egg5" for c in st.players[0].characters)
    assert any(c.iid == "egg2" for c in st.players[0].characters)
    assert len(st.players[0].life) == life_n + 1
    assert st.players[0].life[0] == deck0


def test_eb05_060_skip_trash_does_not_add_life():
    reload_effect_library(force=True)
    st = _main_state()
    life_n = len(st.players[0].life)
    deck_n = len(st.players[0].deck)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    if st.pending_effect is not None:
        _confirm_effect(st, 0, True, catalog)
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert st.pending_choice is None
    assert len(st.players[0].life) == life_n
    assert len(st.players[0].deck) == deck_n
    assert any(c.iid == "egg5" for c in st.players[0].characters)


def test_eb05_060_counter_flip_life_then_buff_this_battle():
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
    before_leader = inst_power(st, 0, "leader", catalog)
    before_egg = inst_power(st, 0, "egg5", catalog)
    assert apply_action(st, 0, {"type": "counter", "hand_index": 0}, catalog)["ok"]
    assert st.pending_choice is not None
    assert "life:top" in (st.pending_choice.options or [])
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "life:top"}, catalog)["ok"]
    assert st.players[0].life_face[0] is True
    assert st.pending_choice is not None
    opts = st.pending_choice.options or []
    assert "leader" in opts
    assert "egg5" in opts
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "leader"}, catalog)["ok"]
    assert inst_power(st, 0, "leader", catalog) == before_leader + 4000
    assert inst_power(st, 0, "egg5", catalog) == before_egg
    assert apply_action(st, 0, {"type": "pass_counter"}, catalog)["ok"]
    assert inst_power(st, 0, "leader", catalog) == before_leader
