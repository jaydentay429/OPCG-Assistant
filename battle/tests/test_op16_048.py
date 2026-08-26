"""OP16-048 Buggy / OP16-042 Prisoner of Impel Down effect fidelity."""

from __future__ import annotations

import json
from pathlib import Path

from battle.effect_library import get_card_entry, reload_effect_library
from battle.effects import detect_keywords, live_keywords
from battle.state import CardInst

_ROOT = Path(__file__).resolve().parents[2]
_CARDS = json.loads((_ROOT / "index" / "cards_by_id.json").read_text())


def test_op16_048_not_innate_blocker():
    info = _CARDS["OP16-048"]
    assert "blocker" not in detect_keywords(info)
    stale = CardInst(iid="c1", card_id="OP16-048", keywords=["blocker"])
    assert "blocker" not in live_keywords(info, stale)


def test_op16_048_abilities_split():
    reload_effect_library(force=True)
    entry = get_card_entry("OP16-048")
    by_t = {a["timing"]: a for a in entry.get("abilities") or []}
    assert "on_play" in by_t
    assert "on_opponent_attack" in by_t
    on_play_ops = [o["op"] for o in by_t["on_play"].get("ops") or []]
    assert on_play_ops == ["draw", "play_from_hand"]
    assert by_t["on_play"].get("require_leader_trait")
    grant = by_t["on_opponent_attack"]["ops"][0]
    assert grant["op"] == "grant_keyword"
    assert grant["keyword"] == "blocker"
    assert grant["duration"] == "turn"
    assert "Prisoner" in grant.get("name_contains", "")
    assert by_t["on_opponent_attack"].get("once") is True
    assert by_t["on_opponent_attack"].get("optional") is True


def test_op16_048_opponent_attack_requires_confirm():
    """「可以發動」must pause for accept/decline; decline does not burn once."""
    from battle.effect_library import resolve_ability
    from battle.engine import _confirm_effect, _run_pending_effect
    from battle.state import MatchState, PlayerState

    reload_effect_library(force=True)

    def catalog(cid):
        return _CARDS.get(cid) or {"cost": 1, "name": cid, "card_type": "CHARACTER"}

    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP02-062",
        deck=["X"] * 20,
        hand=[],
        life=["L"] * 5,
        characters=[
            CardInst(iid="buggy", card_id="OP16-048"),
            CardInst(iid="pris", card_id="OP16-042"),
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
    st = MatchState(
        room_code="T",
        status="playing",
        phase="block",
        turn_seat=1,
        first_seat=1,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )
    pending = resolve_ability(
        st,
        0,
        "OP16-048",
        "buggy",
        "on_opponent_attack",
        catalog("OP16-048"),
        None,
        allow_llm=False,
        catalog=catalog,
    )
    assert pending is not None and pending.uncertain is True
    _run_pending_effect(st, pending, catalog)
    assert st.pending_effect is not None
    assert "blocker" not in (p0.characters[1].turn_keywords or [])
    _confirm_effect(st, 0, False, catalog)
    assert st.pending_effect is None
    assert not p0.characters[0].once_used
    assert "blocker" not in (p0.characters[1].turn_keywords or [])


def test_op16_042_is_vanilla_unlimited():
    info = _CARDS["OP16-042"]
    assert detect_keywords(info) == []
    from battle.effects import max_deck_copies

    assert max_deck_copies(info) >= 50
    reload_effect_library(force=True)
    assert get_card_entry("OP16-042").get("abilities") == []
