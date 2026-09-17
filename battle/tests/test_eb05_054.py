"""EB05-054 Charlotte Brulee: [Trigger] play up to 2 Big Mom Pirates Characters with power 4000 from hand."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_abilities, get_card_entry, reload_effect_library  # noqa: E402
from battle.engine import _resolve_trigger, apply_action  # noqa: E402
from battle.state import MatchState, PendingTrigger, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, hand: list[str]) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP03-099",
        deck=["D"] * 20,
        hand=list(hand),
        life=["L"] * 5,
        don_active=2,
        don_given=2,
        turns_completed=1,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["B"] * 20,
        hand=[],
        life=["M"] * 5,
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase="trigger",
        turn_seat=1,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def test_eb05_054_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-054")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-054 abilities dropped on normalize"
    ab = next(a for a in get_abilities("EB05-054", "trigger"))
    op = ab["ops"][0]
    assert op.get("op") == "play_from_hand"
    assert op.get("count") == 2
    assert op.get("power_eq") == 4000
    assert op.get("optional") is True
    assert "Big Mom" in str(op.get("trait_contains") or "") or "BIG MOM" in str(op.get("trait_contains") or "")
    assert op.get("from_zone") == "hand"
    assert op.get("card_type") == "character"


def test_eb05_054_trigger_plays_two_4000_big_mom():
    reload_effect_library(force=True)
    ab = next(a for a in get_abilities("EB05-054", "trigger"))
    # OP03-103 Killer Beater 4000 Big Mom; ST07-006 Flampe 4000 Big Mom; OP01-016 non-matching 5000
    st = _state(hand=["EB05-054", "OP03-103", "ST07-006", "OP01-016"])
    st.pending_trigger = PendingTrigger(
        seat=0,
        card_id="EB05-054",
        ops=list(ab["ops"]),
        remaining_hits=0,
        summary=str(ab.get("summary") or "trigger"),
    )
    assert _resolve_trigger(st, 0, True, catalog)["ok"]
    assert st.pending_choice is not None
    opts = st.pending_choice.options or []
    assert any("OP03-103" in o for o in opts)
    assert any("ST07-006" in o for o in opts)
    assert not any("OP01-016" in o for o in opts)
    # May include Brulee herself (also 4000 Big Mom).
    tok1 = next(o for o in opts if "OP03-103" in o)
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": tok1}, catalog)["ok"]
    if st.pending_choice is not None:
        opts2 = st.pending_choice.options or []
        tok2 = next(o for o in opts2 if "ST07-006" in o)
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": tok2}, catalog)["ok"]
    field = {c.card_id for c in st.players[0].characters}
    assert "OP03-103" in field
    assert "ST07-006" in field
    assert "OP01-016" in st.players[0].hand
