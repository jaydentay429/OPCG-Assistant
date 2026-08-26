"""OP15-046 Sabo activate Event from hand; OP09-118 Roger keyword fidelity."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import reload_effect_library, get_abilities  # noqa: E402
from battle.effects import detect_keywords, has_blocker, has_rush, apply_ops  # noqa: E402
from battle.engine import apply_action  # noqa: E402
from battle.state import MatchState, PlayerState, CardInst  # noqa: E402


def test_roger_has_rush_not_blocker():
    reload_effect_library(force=True)
    import json

    info = json.loads((ROOT / "index" / "cards_by_id.json").read_text())["OP09-118"]
    kws = detect_keywords(info)
    assert "rush" in kws
    assert "blocker" not in kws
    assert has_rush(info) is True
    assert has_blocker(info) is False


def test_sabo_on_play_is_dressrosa_event():
    reload_effect_library(force=True)
    abs_ = get_abilities("OP15-046", "on_play")
    assert abs_
    op = abs_[0]["ops"][0]
    assert op.get("op") == "play_from_hand"
    assert op.get("card_type") == "event"
    assert "Dressrosa" in str(op.get("trait_contains") or "")
    assert abs_[0].get("require_leader_trait") == "Dressrosa"


def test_sabo_activates_event_from_hand():
    reload_effect_library(force=True)
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="me",
        is_ai=False,
        leader_card_id="OP15-002",  # Dressrosa Lucy
        deck=["D"] * 20,
        hand=["EV1"],
        life=["L"] * 4,
        don_active=5,
        don_given=5,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="foe",
        is_ai=False,
        leader_card_id="FOE",
        deck=["B"] * 20,
        hand=[],
        life=["M"] * 5,
    )
    st = MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )

    def catalog(cid: str):
        table = {
            "OP15-002": {
                "card_type": "LEADER",
                "name": "Lucy",
                "traits": ["多雷斯羅薩"],
                "traits_en": ["Dressrosa"],
                "power": 5000,
                "life": 4,
            },
            "FOE": {"card_type": "LEADER", "name": "Foe", "power": 5000, "life": 5},
            "OP15-046": {
                "card_type": "CHARACTER",
                "name": "Sabo",
                "cost": 7,
                "power": 9000,
                "effect": "【防禦】 【登場時】若自己的領航卡擁有《多雷斯羅薩》特徵時，發動最多1張自己手牌中擁有《多雷斯羅薩》特徵的事件卡。",
                "traits": ["多雷斯羅薩"],
                "traits_en": ["Dressrosa"],
            },
            "EV1": {
                "card_type": "EVENT",
                "name": "Dressrosa Event",
                "cost": 2,
                "traits": ["多雷斯羅薩"],
                "traits_en": ["Dressrosa"],
                "effect": "【主要】抽1張卡片。",
            },
            "C1": {"card_type": "CHARACTER", "name": "Char", "cost": 2, "power": 3000},
        }
        return dict(table.get(cid) or {"card_type": "CHARACTER", "name": cid, "cost": 1, "power": 1000})

    # Put Sabo on field via on_play ops directly after simulating play cost paid.
    st.players[0].characters.append(CardInst(iid="sabo", card_id="OP15-046", summoning_sick=True))
    apply_ops(
        st,
        0,
        [
            {
                "op": "play_from_hand",
                "count": 1,
                "card_type": "event",
                "optional": True,
                "trait_contains": "Dressrosa|多雷斯羅薩",
                "from_zone": "hand",
            }
        ],
        catalog,
    )
    assert st.pending_choice is not None
    assert any(o.endswith(":EV1") for o in st.pending_choice.options)
    pick = st.pending_choice.options[0]
    hand_before = len(st.players[0].hand)
    deck_before = len(st.players[0].deck)
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert "EV1" in st.players[0].trash
    # Event Main draw 1 should have resolved.
    assert len(st.players[0].hand) == hand_before  # -1 event +1 draw, or -1 if draw failed
    # Prefer: draw happened
    assert len(st.players[0].deck) == deck_before - 1


if __name__ == "__main__":
    test_roger_has_rush_not_blocker()
    test_sabo_on_play_is_dressrosa_event()
    test_sabo_activates_event_from_hand()
    print("ok")
