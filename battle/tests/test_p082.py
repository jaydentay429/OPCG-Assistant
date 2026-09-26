"""P-082 Crocodile: Your Turn On Play, Cross Guild or Baroque Works Leader, bottom opp power≤2000."""

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
from battle.engine import apply_action  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "WEAK": {"card_id": "WEAK", "card_type": "CHARACTER", "cost": 1, "power": 2000, "name": "WEAK"},
        "STRONG": {"card_id": "STRONG", "card_type": "CHARACTER", "cost": 4, "power": 5000, "name": "STRONG"},
        "D0": {"card_id": "D0", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "D0"},
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, leader: str) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=leader,
        deck=["D0"] * 20,
        hand=["P-082"],
        life=["L"] * 5,
        don_active=5,
        don_given=5,
        turns_completed=1,
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
        characters=[CardInst(iid="w", card_id="WEAK"), CardInst(iid="s", card_id="STRONG")],
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


def test_p082_override_shape():
    reload_effect_library(force=True)
    for cid in ("P-082", "P-082-P1", "P-082-P2", "P-082-R1"):
        abs_ = [a for a in get_card_entry(cid)["abilities"] if a.get("ops")]
        assert abs_, f"{cid} dropped"
        play = next(a for a in get_abilities(cid, "on_play"))
        assert play.get("require_your_turn") is True
        trait = str(play.get("require_leader_trait") or "")
        assert "Cross Guild" in trait or "十字公會" in trait
        assert "Baroque" in trait or "B・W" in trait or "B.W" in trait
        op = play["ops"][0]
        assert op["op"] == "return_to_bottom"
        assert op.get("target_kind") == "opponent_character"
        assert op.get("power_lte") == 2000


def test_p082_bottoms_opp_2000_with_cross_guild_leader():
    reload_effect_library(force=True)
    st = _state(leader="OP09-042")
    p1 = st.players[1]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert st.pending_choice is not None
    assert "w" in (st.pending_choice.options or [])
    assert "s" not in (st.pending_choice.options or [])
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "w"}, catalog)["ok"]
    assert all(c.iid != "w" for c in p1.characters)
    assert p1.deck[-1] == "WEAK"


def test_p082_no_bounce_without_leader_trait():
    reload_effect_library(force=True)
    st = _state(leader="ST22-001")
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert st.pending_choice is None
    assert any(c.iid == "w" for c in st.players[1].characters)
