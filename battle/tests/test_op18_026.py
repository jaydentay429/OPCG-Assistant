"""OP18-026 Chimney: Activate Main rest own Gonbe + this Character → set Leader Monkey.D.Luffy active."""

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
from battle.engine import apply_action, legal_actions  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "GONBE": {
            "card_id": "GONBE",
            "card_type": "CHARACTER",
            "cost": 1,
            "power": 1000,
            "name": "貢貝",
            "name_en": "Gonbe",
        },
        "OTHER": {
            "card_id": "OTHER",
            "card_type": "CHARACTER",
            "cost": 1,
            "power": 1000,
            "name": "Nami",
        },
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, leader: str = "OP18-022") -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=leader,
        leader_rested=True,
        deck=["X"] * 20,
        hand=[],
        life=["L"] * 5,
        don_active=2,
        don_given=2,
        turns_completed=1,
        characters=[
            CardInst(iid="chim", card_id="OP18-026", rested=False, summoning_sick=False),
            CardInst(iid="gon", card_id="GONBE", rested=False, summoning_sick=False),
            CardInst(iid="oth", card_id="OTHER", rested=False, summoning_sick=False),
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


def test_op18_026_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("OP18-026")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "OP18-026 abilities dropped on normalize"
    act = next(a for a in get_abilities("OP18-026", "activate_main"))
    rest_g = act["ops"][0]
    assert rest_g.get("op") == "rest_character"
    assert rest_g.get("as_cost") is True
    assert "貢貝" in str(rest_g.get("name_contains") or "")
    rest_self = act["ops"][1]
    assert rest_self.get("target_kind") == "self"
    assert rest_self.get("as_cost") is True
    active = act["ops"][2]
    assert active.get("op") == "set_character_active"
    assert active.get("target_kind") == "leader"
    assert "蒙其" in str(active.get("name_contains") or "") or "Luffy" in str(active.get("name_contains") or "")


def test_op18_026_activate_rests_gonbe_and_stands_luffy():
    reload_effect_library(force=True)
    st = _state()
    acts = legal_actions(st, 0, catalog)
    assert any(a.get("type") == "activate_main" and a.get("source_iid") == "chim" for a in acts)
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "chim"}, catalog)["ok"]
    if st.pending_effect is not None:
        assert apply_action(st, 0, {"type": "confirm_effect", "accept": True}, catalog)["ok"]
    if st.pending_choice is not None:
        opts = st.pending_choice.options or []
        assert "gon" in opts
        assert "oth" not in opts
        assert "chim" not in opts
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": "gon"}, catalog)["ok"]
    gon = next(c for c in st.players[0].characters if c.iid == "gon")
    chim = next(c for c in st.players[0].characters if c.iid == "chim")
    assert gon.rested is True
    assert chim.rested is True
    assert st.players[0].leader_rested is False


def test_op18_026_skip_keeps_leader_rested():
    reload_effect_library(force=True)
    st = _state()
    st.players[0].characters.append(
        CardInst(iid="gon2", card_id="GONBE", rested=False, summoning_sick=False)
    )
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "chim"}, catalog)["ok"]
    if st.pending_effect is not None:
        assert apply_action(st, 0, {"type": "confirm_effect", "accept": True}, catalog)["ok"]
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    chim = next(c for c in st.players[0].characters if c.iid == "chim")
    gon = next(c for c in st.players[0].characters if c.iid == "gon")
    assert chim.rested is False
    assert gon.rested is False
    assert st.players[0].leader_rested is True
