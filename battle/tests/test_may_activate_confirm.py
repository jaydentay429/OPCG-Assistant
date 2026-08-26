"""「可以發動」reactive abilities must pause for controller confirm."""

from __future__ import annotations

import json
from pathlib import Path

from battle.effect_library import ability_needs_confirm, get_card_entry, reload_effect_library, resolve_ability
from battle.engine import _confirm_effect, _run_pending_effect, fire_own_trait_leave_or_ko
from battle.state import CardInst, MatchState, PlayerState

_ROOT = Path(__file__).resolve().parents[2]
_CARDS = json.loads((_ROOT / "index" / "cards_by_id.json").read_text())


def catalog(cid: str):
    return _CARDS.get(cid) or {"cost": 1, "name": cid, "card_type": "CHARACTER"}


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.pop("leader0", "OP01-001"),
        deck=["X"] * 30,
        hand=kwargs.pop("hand0", []),
        life=["L"] * 5,
        don_active=kwargs.pop("don_active", 10),
        characters=kwargs.pop("chars0", []),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["Y"] * 30,
        hand=[],
        life=["M"] * 5,
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase=kwargs.pop("phase", "main"),
        turn_seat=kwargs.pop("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
        **kwargs,
    )


def test_library_optional_flags_on_may_activate_set():
    reload_effect_library(force=True)
    cases = [
        ("OP07-038", "your_turn"),
        ("OP10-042", "opponent_turn"),
        ("OP11-040", "turn_start"),
        ("OP11-041", "on_opponent_attack"),
        ("OP11-043", "on_opponent_attack"),
        ("OP11-088", "on_opponent_attack"),
        ("OP12-081", "on_opponent_play"),
        ("OP13-100", "your_turn"),
        ("OP16-041", "your_turn"),
        ("PRB02-009", "opponent_turn"),
    ]
    for cid, timing in cases:
        abs_ = [a for a in get_card_entry(cid).get("abilities") or [] if a.get("timing") == timing]
        if cid == "OP10-042":
            abs_ = [a for a in abs_ if a.get("once")]
        assert abs_, f"{cid} missing {timing}"
        ab = abs_[0]
        assert ab.get("optional") is True, cid
        assert ability_needs_confirm(ab, catalog(cid)) is True, cid


def test_op12_081_when_attacking_not_optional():
    reload_effect_library(force=True)
    ab = next(a for a in get_card_entry("OP12-081")["abilities"] if a["timing"] == "when_attacking")
    assert not ab.get("optional")
    assert ability_needs_confirm(ab, catalog("OP12-081")) is False


def test_op11_040_turn_start_pauses_for_confirm():
    reload_effect_library(force=True)
    st = _state(leader0="OP11-040", don_active=0)
    # Field DON gate: put 8 active DON conceptually via don_active+rested as field count.
    st.players[0].don_active = 8
    pending = resolve_ability(
        st, 0, "OP11-040", "leader", "turn_start", catalog("OP11-040"), None, allow_llm=False, catalog=catalog
    )
    assert pending is not None and pending.uncertain is True
    _run_pending_effect(st, pending, catalog)
    assert st.pending_effect is not None
    _confirm_effect(st, 0, False, catalog)
    assert st.pending_effect is None


def test_op10_042_leave_watcher_confirm_does_not_burn_once_on_decline():
    reload_effect_library(force=True)
    watcher = CardInst(iid="law", card_id="OP10-042")
    st = _state(chars0=[watcher], turn_seat=1, phase="main")
    fire_own_trait_leave_or_ko(st, 0, "OP04-039", catalog, by_opponent_effect=True, by_ko=True)
    assert st.pending_effect is not None
    assert st.pending_effect.uncertain is True
    assert not watcher.once_used
    _confirm_effect(st, 0, False, catalog)
    assert st.pending_effect is None
    assert not watcher.once_used


def test_op13_100_play_watcher_requires_confirm():
    reload_effect_library(force=True)
    from battle.engine import _fire_character_play_watchers

    st = _state(chars0=[CardInst(iid="bonney", card_id="OP13-100")])
    paused = _fire_character_play_watchers(st, 0, "trig", "OP14-082", catalog, from_zone="hand")
    assert paused is True
    assert st.pending_effect is not None and st.pending_effect.uncertain is True
    _confirm_effect(st, 0, False, catalog)
    assert not st.players[0].characters[0].once_used
