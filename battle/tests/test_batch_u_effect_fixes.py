"""Batch-U effect encoding + runtime fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops, max_deck_copies  # noqa: E402
from battle.engine import _blocker_denied, fire_own_trait_leave_or_ko  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def setup_module() -> None:
    reload_effect_library()


def catalog(cid: str):
    base = dict(_CARDS.get(cid) or {"cost": 1, "name": cid, "card_type": "CHARACTER"})
    return base


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.pop("leader0", "OP16-041"),
        deck=["X"] * 30,
        hand=kwargs.pop("hand0", []),
        life=["L"] * kwargs.pop("life_n", 5),
        don_active=kwargs.pop("don_active", 10),
        leader_don=kwargs.pop("leader_don", 1),
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
        characters=kwargs.pop("chars1", []),
    )
    return MatchState(
        room_code="U",
        status="playing",
        phase=kwargs.pop("phase", "main"),
        turn_seat=kwargs.pop("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def test_op16_041_leave_any_no_chars_trait_gate() -> None:
    for a in get_card_entry("OP16-041")["abilities"]:
        assert a.get("on_any_leave") is True
        assert a.get("require_chars_trait") is None
        assert "推進城" in str(a.get("on_own_trait_leave_or_ko") or "")
        assert "推進城的囚犯" in str(a["ops"][0].get("name_contains") or "")


def test_op16_041_leader_fires_on_leave() -> None:
    """Leader watcher must see Impel Down leave even when no Impel chars remain."""
    st = _state(
        leader0="OP16-041",
        leader_don=1,
        hand0=["OP16-042"],
        chars0=[],
    )
    # Victim already left; fire with Impel Down prisoner id
    fire_own_trait_leave_or_ko(st, 0, "OP16-042", catalog, by_opponent_effect=False, by_ko=False)
    # on_any_leave + optional → pending confirm
    assert st.pending_effect is not None
    assert st.pending_effect.card_id.startswith("OP16-041")
    assert st.pending_effect.source_iid == "leader"


def test_op13_057_life_on_deny_op_not_ability() -> None:
    play = next(a for a in get_card_entry("OP13-057")["abilities"] if a["timing"] == "on_play")
    assert play.get("require_life_lte") is None
    deny = next(o for o in play["ops"] if o["op"] == "deny_blocker")
    assert deny.get("require_life_lte") == 1
    assert deny.get("when_leader_attacks") is True
    ctr = next(a for a in get_card_entry("OP13-057")["abilities"] if a["timing"] == "counter_event")
    assert ctr["ops"][0].get("duration") == "battle"


def test_op13_057_when_leader_attacks_runtime() -> None:
    st = _state(life_n=1, leader0="OP13-001")
    apply_ops(
        st,
        0,
        [{"op": "deny_blocker", "duration": "turn", "when_leader_attacks": True}],
        catalog,
    )
    assert st.players[0].deny_blocker
    assert st.players[0].deny_blocker[0].get("when_leader_attacks") is True
    blocker = CardInst(iid="b1", card_id="OP16-045")
    st.players[1].characters = [blocker]
    # No attack yet / character attacking → not denied
    st.attack = None
    assert _blocker_denied(st, 0, blocker, catalog) is False
    from battle.state import PendingAttack

    st.attack = PendingAttack(attacker_seat=0, attacker_iid="c1", target_iid="leader", declared_power=5000)
    assert _blocker_denied(st, 0, blocker, catalog) is False
    st.attack = PendingAttack(attacker_seat=0, attacker_iid="leader", target_iid="leader", declared_power=5000)
    assert _blocker_denied(st, 0, blocker, catalog) is True


def test_op06_058_bilateral_bottom() -> None:
    play = next(a for a in get_card_entry("OP06-058")["abilities"] if a["timing"] == "on_play")
    assert play["ops"][0].get("target_kind") == "any_character"
    assert play["ops"][0].get("cost_lte") == 6


def test_op07_056_counter_battle_buff() -> None:
    ctr = next(a for a in get_card_entry("OP07-056")["abilities"] if a["timing"] == "counter_event")
    assert ctr["ops"][0].get("as_cost") is True
    assert ctr["ops"][1].get("duration") == "battle"
    assert ctr["ops"][1].get("amount") == 4000


def test_op16_042_unlimited_deck() -> None:
    assert max_deck_copies(catalog("OP16-042")) >= 50


def test_op16_045_impel_trait() -> None:
    op = get_card_entry("OP16-045")["abilities"][0]["ops"][1]
    assert "推進城" in str(op.get("trait_contains") or "")


def test_op16_048_048_prisoner_and_blocker() -> None:
    entry = get_card_entry("OP16-048")
    play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert "推進城" in str(play.get("require_leader_trait") or "")
    atk = next(a for a in entry["abilities"] if a["timing"] == "on_opponent_attack")
    assert atk["ops"][0].get("keyword") == "blocker"


def test_op16_055_power_copy() -> None:
    atk = next(a for a in get_card_entry("OP16-055")["abilities"] if a["timing"] == "when_attacking")
    assert atk.get("require_don_attached_gte") == 1
    assert atk["ops"][0].get("op") == "set_base_power_from_opponent_leader"


def test_op16_056_trash_draw_deny() -> None:
    ab = get_card_entry("OP16-056")["abilities"][0]
    assert [o["op"] for o in ab["ops"]] == ["trash", "draw", "deny_attack"]
    assert ab["ops"][2].get("cost_lte") == 9


if __name__ == "__main__":
    setup_module()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
