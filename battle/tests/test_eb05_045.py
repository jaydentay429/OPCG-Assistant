"""EB05-045 Ms. Monday: On Play KO own B・W; On K.O. look 3 reveal B・W, trash rest."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Avoid battle/__init__.py FastAPI import when running as a script.
if "battle" not in sys.modules:
    pkg = types.ModuleType("battle")
    pkg.__path__ = [str(ROOT / "battle")]
    sys.modules["battle"] = pkg

from battle.effect_library import get_abilities, get_card_entry, reload_effect_library, resolve_ability  # noqa: E402
from battle.engine import _run_pending_effect, apply_action  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000, "traits": []}


def _state(*, hand: list[str], field: list[str] | None = None, deck: list[str] | None = None) -> MatchState:
    chars = [
        CardInst(iid=f"c{i}", card_id=cid, rested=False, summoning_sick=False)
        for i, cid in enumerate(field or [])
    ]
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP02-093",
        deck=list(deck or ["D"] * 20),
        hand=list(hand),
        life=["L"] * 5,
        don_active=5,
        don_given=5,
        turns_completed=1,
        characters=chars,
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
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def test_eb05_045_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-045")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert len(abs_) >= 2, "EB05-045 abilities dropped on normalize"
    on_play = next(a for a in get_abilities("EB05-045", "on_play"))
    ko_op = on_play["ops"][0]
    assert ko_op.get("op") == "ko"
    assert ko_op.get("target_kind") == "own_character"
    assert ko_op.get("optional") is True
    assert "B・W" in str(ko_op.get("trait_contains") or "") or "Baroque" in str(
        ko_op.get("trait_contains") or ""
    )
    on_ko = next(a for a in get_abilities("EB05-045", "on_ko"))
    search = on_ko["ops"][0]
    assert search.get("op") == "search_deck"
    assert search.get("top_n") == 3
    assert search.get("max_add") == 1
    assert search.get("trash_rest") is True
    assert search.get("destination") == "hand"


def test_eb05_045_on_play_kos_own_baroque():
    reload_effect_library(force=True)
    # EB01-035 is B・W; OP01-016 is Straw Hat (not eligible).
    st = _state(hand=["EB05-045"], field=["EB01-035", "OP01-016"])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-045" for c in st.players[0].characters)
    assert st.pending_choice is not None
    opts = st.pending_choice.options or []
    by_id = {c.iid: c.card_id for c in st.players[0].characters}
    eligible = {by_id[o] for o in opts if o in by_id}
    assert "EB01-035" in eligible
    assert "EB05-045" in eligible  # self is also B・W
    assert "OP01-016" not in eligible
    tok = next(o for o in opts if by_id.get(o) == "EB01-035")
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": tok}, catalog)["ok"]
    field_ids = {c.card_id for c in st.players[0].characters}
    assert "EB01-035" not in field_ids
    assert "OP01-016" in field_ids
    assert "EB05-045" in field_ids


def test_eb05_045_on_ko_look3_trash_rest():
    reload_effect_library(force=True)
    monday = CardInst(iid="mon", card_id="EB05-045")
    st = _state(
        hand=[],
        field=[],
        deck=["EB01-035", "OP01-016", "OP02-098", "X", "Y"],
    )
    st.players[0].characters = [monday]
    pending = resolve_ability(
        st,
        0,
        "EB05-045",
        "mon",
        "on_ko",
        catalog("EB05-045"),
        None,
        allow_llm=False,
        catalog=catalog,
    )
    assert pending is not None and pending.ops
    _run_pending_effect(st, pending, catalog)
    assert st.pending_search is not None
    assert st.pending_search.trash_rest is True
    assert st.pending_search.eligible == [0]
    assert apply_action(st, 0, {"type": "select_search", "index": 0}, catalog)["ok"]
    if st.pending_search is not None:
        assert apply_action(st, 0, {"type": "confirm_search"}, catalog)["ok"]
    assert st.players[0].hand == ["EB01-035"]
    assert set(st.players[0].trash) == {"OP01-016", "OP02-098"}
    assert st.players[0].deck[:2] == ["X", "Y"]


if __name__ == "__main__":
    test_eb05_045_override_shape()
    test_eb05_045_on_play_kos_own_baroque()
    test_eb05_045_on_ko_look3_trash_rest()
    print("OK")
