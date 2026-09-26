"""OP18 leaders: Karoo, Luffy, Ms. All Sunday, Spandam."""

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

from battle.effect_library import get_abilities, get_card_entry, reload_effect_library, resolve_ability  # noqa: E402
from battle.effects import apply_ops, has_rush  # noqa: E402
from battle.engine import _begin_turn, apply_action, fire_own_trait_leave_or_ko, inst_power  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))

EXTRAS = {
    "BOTH": {
        "card_id": "BOTH",
        "card_type": "CHARACTER",
        "cost": 3,
        "power": 4000,
        "name": "BOTH",
        "traits": ["動物", "阿拉巴斯坦王國"],
        "traits_en": ["Animal", "Alabasta"],
    },
    "ANIMAL": {
        "card_id": "ANIMAL",
        "card_type": "CHARACTER",
        "cost": 2,
        "power": 3000,
        "name": "ANIMAL",
        "traits": ["動物"],
        "traits_en": ["Animal"],
    },
    "BW3": {
        "card_id": "BW3",
        "card_type": "CHARACTER",
        "cost": 3,
        "power": 3000,
        "name": "BW3",
        "traits": ["B・W"],
        "traits_en": ["Baroque Works"],
    },
    "BW2": {
        "card_id": "BW2",
        "card_type": "CHARACTER",
        "cost": 2,
        "power": 2000,
        "name": "BW2",
        "traits": ["B・W"],
        "traits_en": ["Baroque Works"],
    },
    "CP1": {
        "card_id": "CP1",
        "card_type": "CHARACTER",
        "cost": 1,
        "power": 1000,
        "name": "CP1",
        "traits": ["CP9"],
        "traits_en": ["CP9"],
    },
    "JUNK": {"card_id": "JUNK", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "JUNK"},
    "D0": {"card_id": "D0", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "D0"},
}


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    return EXTRAS.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, leader: str, **kw) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=leader,
        deck=list(kw.get("deck", ["D0"] * 20)),
        hand=list(kw.get("hand", [])),
        life=list(kw.get("life", ["L"] * 5)),
        don_active=int(kw.get("don_active", 5)),
        don_given=int(kw.get("don_given", 5)),
        don_rested=int(kw.get("don_rested", 0)),
        leader_don=int(kw.get("leader_don", 0)),
        leader_rested=bool(kw.get("leader_rested", False)),
        turns_completed=1,
        characters=list(kw.get("chars0", [])),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["Y"] * 20,
        hand=list(kw.get("hand1", [])),
        life=["M"] * 5,
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=int(kw.get("turn_seat", 0)),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def test_op18_leader_override_shapes():
    reload_effect_library(force=True)
    for cid in ("OP18-001", "OP18-022", "OP18-041", "OP18-079"):
        abs_ = [a for a in get_card_entry(cid)["abilities"] if a.get("ops")]
        assert abs_, f"{cid} dropped on normalize"

    atk = next(a for a in get_abilities("OP18-022", "when_attacking"))
    assert atk.get("require_don_attached_gte") == 3
    assert atk.get("once") is True
    assert atk["ops"][0]["op"] == "set_character_active"
    assert atk["ops"][1]["op"] == "skip_untap"
    assert atk["ops"][1].get("target_kind") == "own_leader"

    span = next(a for a in get_abilities("OP18-079", "activate_main"))
    ops = span["ops"]
    assert ops[0]["op"] == "trash_hand" and ops[0].get("as_cost")
    assert "CP" in str(ops[0].get("trait_contains") or "")
    assert ops[1]["op"] == "rest_don" and ops[1].get("count") == 2 and ops[1].get("as_cost")
    assert ops[2]["op"] == "rest_character" and ops[2].get("as_cost")
    assert ops[3]["op"] == "add_life" and ops[3].get("position") == "top"

    aura = next(a for a in get_abilities("OP18-001", "your_turn") if not a.get("on_own_char_ko"))
    rush = next(o for o in aura["ops"] if o.get("op") == "grant_keyword")
    buff = next(o for o in aura["ops"] if o.get("op") == "buff")
    assert rush.get("keyword") == "rush" and rush.get("all") is True
    assert len(rush.get("trait_all") or []) == 2
    assert buff.get("amount") == 1000

    ko = next(a for a in get_abilities("OP18-041", "your_turn") if a.get("on_own_char_ko"))
    assert ko.get("require_victim_base_power_gte") == 3000
    assert ko["ops"][0]["op"] == "draw"
    assert ko["ops"][1]["op"] == "trash_hand" and ko["ops"][1].get("owner") == "opponent"


def test_op18_022_luffy_untaps_then_skips_own_refresh():
    reload_effect_library(force=True)
    st = _state(leader="OP18-022", leader_rested=True, leader_don=3)
    p0 = st.players[0]
    pending = resolve_ability(
        st, 0, "OP18-022", "leader", "when_attacking", catalog("OP18-022"), None, allow_llm=False, catalog=catalog
    )
    assert pending is not None
    apply_ops(st, 0, pending.ops, catalog)
    assert p0.leader_rested is False
    assert p0.leader_skip_untap is True
    p0.leader_rested = True
    _begin_turn(st, 0, catalog)
    assert p0.leader_rested is True
    assert p0.leader_skip_untap is False


def test_op18_001_karoo_rush_and_plus_1000_requires_both_traits():
    reload_effect_library(force=True)
    both = CardInst(iid="both", card_id="BOTH")
    animal = CardInst(iid="an", card_id="ANIMAL")
    st = _state(leader="OP18-001", chars0=[both, animal])
    assert inst_power(st, 0, "both", catalog) == 5000
    assert has_rush(catalog("BOTH"), both, state=st, owner_seat=0, catalog=catalog)
    assert inst_power(st, 0, "an", catalog) == 3000
    assert not has_rush(catalog("ANIMAL"), animal, state=st, owner_seat=0, catalog=catalog)


def test_op18_001_karoo_draw_on_alabasta_ko_once():
    reload_effect_library(force=True)
    st = _state(leader="OP18-001", chars0=[CardInst(iid="both", card_id="BOTH")])
    p0 = st.players[0]
    hand0 = len(p0.hand)
    fire_own_trait_leave_or_ko(st, 0, "BOTH", catalog, by_ko=True)
    assert len(p0.hand) == hand0 + 1
    fire_own_trait_leave_or_ko(st, 0, "BOTH", catalog, by_ko=True)
    assert len(p0.hand) == hand0 + 1


def test_op18_041_sunday_ko_draw_and_opp_trash():
    reload_effect_library(force=True)
    st = _state(leader="OP18-041", chars0=[CardInst(iid="bw", card_id="BW3")], hand1=["JUNK", "D0"])
    p0, p1 = st.players
    fire_own_trait_leave_or_ko(st, 0, "BW3", catalog, by_ko=True)
    assert len(p0.hand) == 1
    assert st.pending_choice is not None
    assert st.pending_choice.seat == 1
    tid = (st.pending_choice.options or [None])[0]
    assert apply_action(st, 1, {"type": "select_choice", "target_iid": tid}, catalog)["ok"]
    assert len(p1.hand) == 1
    assert "JUNK" in p1.trash or "D0" in p1.trash


def test_op18_041_sunday_ignores_low_base_power():
    reload_effect_library(force=True)
    st = _state(leader="OP18-041", chars0=[CardInst(iid="bw", card_id="BW2")], hand1=["JUNK"])
    fire_own_trait_leave_or_ko(st, 0, "BW2", catalog, by_ko=True)
    assert st.players[0].hand == []
    assert st.pending_choice is None
    assert st.players[1].hand == ["JUNK"]


def test_op18_079_spandam_pays_cost_and_adds_life():
    reload_effect_library(force=True)
    st = _state(leader="OP18-079", hand=["CP1", "JUNK"], don_active=3, deck=["LIFE1"] + ["D0"] * 19)
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "leader"}, catalog)["ok"]
    while st.pending_choice is not None:
        opts = st.pending_choice.options or []
        pick = next((o for o in opts if "CP1" in str(o)), opts[0])
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert "CP1" in p0.trash
    assert p0.don_active == 1
    assert p0.don_rested >= 2
    assert p0.leader_rested is True
    assert p0.life[0] == "LIFE1"
