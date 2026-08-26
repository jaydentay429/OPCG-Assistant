"""Hotseat: after attack, viewer must switch to the defending seat."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.ai import _acting_seat  # noqa: E402
from battle.engine import apply_action, legal_actions, public_view  # noqa: E402
from battle.state import CardInst, MatchState, PendingAttack, PendingEffect, PlayerState  # noqa: E402


def _catalog(cid: str) -> dict:
    table = {
        "L0": {"card_type": "LEADER", "name": "P1", "power": 5000, "life": 5},
        "L1": {"card_type": "LEADER", "name": "P2", "power": 5000, "life": 5},
        "ATK": {"card_type": "CHARACTER", "name": "Atk", "power": 6000, "cost": 4},
        "DEF": {
            "card_type": "CHARACTER",
            "name": "Defender",
            "power": 5000,
            "cost": 3,
            "effect": "【對方攻擊時】【每回合1次】可以廢棄1張自己的手牌：這張角色卡力量值+2000。",
            "effect_en": "[On Your Opponent's Attack] [Once Per Turn] You may trash 1 card from your hand: this Character gains +2000 power.",
        },
        "PLAIN": {"card_type": "CHARACTER", "name": "Plain", "power": 4000, "cost": 2, "effect": ""},
    }
    return dict(table.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000})


def _hotseat_state() -> MatchState:
    p0 = PlayerState(
        seat=0, user_id="u", username="host", is_ai=False, leader_card_id="L0", hand=[], deck=["D"] * 20, life=["X"] * 5
    )
    p1 = PlayerState(
        seat=1, user_id="u:p2", username="host · P2", is_ai=False, leader_card_id="L1", hand=["ATK"], deck=["D"] * 20, life=["X"] * 5
    )
    p0.turns_completed = 1
    p0.characters = [CardInst(iid="atk", card_id="ATK", rested=False, summoning_sick=False)]
    p1.characters = [CardInst(iid="def", card_id="DEF", rested=False, summoning_sick=False)]
    return MatchState(room_code="hs", status="playing", phase="main", turn_seat=0, players=[p0, p1])


def test_acting_seat_pending_effect_is_controller_not_first_human():
    st = _hotseat_state()
    st.phase = "block"
    st.attack = PendingAttack(attacker_seat=0, attacker_iid="atk", target_iid="leader", declared_power=6000)
    st.pending_effect = PendingEffect(
        effect_id="fx",
        seat=1,
        card_id="DEF",
        source_iid="def",
        summary="may trash",
        ops=[{"op": "trash_hand", "count": 1}],
        uncertain=True,
        confirmations={},
    )
    assert _acting_seat(st) == 1
    view = public_view(st, _acting_seat(st), _catalog)
    assert view["viewer_seat"] == 1
    kinds = [a["type"] for a in view["legal_actions"]]
    assert "confirm_effect" in kinds


def test_attack_character_switches_acting_to_defender():
    st = _hotseat_state()
    st.players[1].characters = [
        CardInst(iid="plain", card_id="PLAIN", rested=True, summoning_sick=False),
    ]
    r = apply_action(st, 0, {"type": "attack", "attacker_iid": "atk", "target_iid": "plain"}, _catalog)
    assert r.get("ok"), r
    assert st.phase == "block"
    assert st.attack and st.attack.target_iid == "plain"
    assert _acting_seat(st) == 1
    view = public_view(st, 1, _catalog)
    assert view["viewer_seat"] == 1
    kinds = [a["type"] for a in view["legal_actions"]]
    assert "block" in kinds
    assert legal_actions(st, 0, _catalog) == [{"type": "concede"}]


def test_attack_character_with_on_attack_confirm_still_switches():
    st = _hotseat_state()
    st.players[1].characters = [
        CardInst(iid="def", card_id="DEF", rested=True, summoning_sick=False),
    ]
    r = apply_action(st, 0, {"type": "attack", "attacker_iid": "atk", "target_iid": "def"}, _catalog)
    assert r.get("ok"), r
    # 【对方攻击时】 optional confirm pauses before Block — viewer must already be defender.
    assert st.pending_effect is not None or st.phase == "block"
    assert _acting_seat(st) == 1
    view = public_view(st, 1, _catalog)
    assert view["viewer_seat"] == 1
    kinds = [a["type"] for a in view["legal_actions"]]
    assert "confirm_effect" in kinds or "block" in kinds
    if st.pending_effect:
        assert apply_action(st, 1, {"type": "confirm_effect", "accept": False}, _catalog)["ok"]
        assert st.phase == "block"
        assert _acting_seat(st) == 1


def test_blockerless_attack_leader_switches_to_defender_counter():
    """OP16-095 Unblockable → skip Block → Counter must flip hotseat viewer."""
    st = _hotseat_state()
    st.players[0].characters = [
        CardInst(iid="atk", card_id="ATK", rested=False, summoning_sick=False, turn_keywords=["blockerless"])
    ]
    st.players[1].characters = []
    st.players[1].hand = ["ATK"]
    r = apply_action(st, 0, {"type": "attack", "attacker_iid": "atk", "target_iid": "leader"}, _catalog)
    assert r.get("ok"), r
    assert st.phase == "counter"
    assert st.attack and st.attack.combat_entered
    assert _acting_seat(st) == 1
    view = public_view(st, _acting_seat(st), _catalog)
    assert view["viewer_seat"] == 1
    kinds = [a["type"] for a in view["legal_actions"]]
    assert "pass_counter" in kinds
    assert legal_actions(st, 0, _catalog) == [{"type": "concede"}]
