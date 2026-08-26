"""OP16-082 trash_rest + play-from-trash choice tokens."""

from __future__ import annotations

from battle.effects import apply_ops
from battle.engine import apply_action
from battle.state import CardInst, MatchState, PlayerState


def _catalog(cid: str) -> dict:
    table = {
        "WANO1": {
            "card_id": "WANO1",
            "card_type": "CHARACTER",
            "cost": 3,
            "name": "Kin",
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
            "colors": ["黑"],
        },
        "OTHER": {
            "card_id": "OTHER",
            "card_type": "CHARACTER",
            "cost": 2,
            "name": "Other",
            "traits": ["海军"],
            "traits_en": ["Navy"],
            "colors": ["红"],
        },
        "Y8": {
            "card_id": "Y8",
            "card_type": "CHARACTER",
            "cost": 8,
            "name": "大和",
            "name_en": "Yamato",
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
            "colors": ["黑"],
        },
        "Y6": {
            "card_id": "Y6",
            "card_type": "CHARACTER",
            "cost": 6,
            "name": "大和",
            "name_en": "Yamato",
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
            "colors": ["黑"],
        },
        "L_WANO": {
            "card_id": "L_WANO",
            "card_type": "LEADER",
            "name": "Lucy",
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
            "colors": ["黑"],
        },
    }
    return dict(table.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "colors": ["黑"]})


def _state(*, deck=None, trash=None, characters=None, leader="L_WANO") -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="me",
        is_ai=False,
        leader_card_id=leader,
        deck=list(deck or []),
        hand=[],
        trash=list(trash or []),
        characters=list(characters or []),
        life=["L"] * 5,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="foe",
        is_ai=False,
        leader_card_id="FOE",
        deck=["D"] * 20,
        hand=[],
        life=["M"] * 5,
    )
    return MatchState(room_code="T", status="playing", phase="main", turn_seat=0, players=[p0, p1])


def test_trash_rest_puts_leftovers_in_trash():
    st = _state(deck=["WANO1", "OTHER", "OTHER", "OTHER", "OTHER", "D", "D"])
    apply_ops(
        st,
        0,
        [
            {
                "op": "search_deck",
                "trait_contains": "Land of Wano",
                "top_n": 5,
                "max_add": 1,
                "order_bottom": False,
                "destination": "hand",
                "trash_rest": True,
            }
        ],
        _catalog,
    )
    assert st.pending_search is not None
    assert st.pending_search.trash_rest is True
    assert st.pending_search.order_bottom is False
    # Pick the only eligible Wano card (index 0).
    assert apply_action(st, 0, {"type": "select_search", "index": 0}, _catalog)["ok"]
    assert st.pending_search is None
    assert "WANO1" in st.players[0].hand
    assert st.players[0].trash.count("OTHER") == 4
    assert "OTHER" not in st.players[0].deck[:5]


def test_trash_rest_skip_trashes_all_revealed():
    st = _state(deck=["OTHER", "OTHER", "OTHER", "D"])
    apply_ops(
        st,
        0,
        [{"op": "search_deck", "top_n": 3, "max_add": 1, "trash_rest": True, "order_bottom": False}],
        _catalog,
    )
    assert apply_action(st, 0, {"type": "skip_search"}, _catalog)["ok"]
    assert st.players[0].trash.count("OTHER") == 3


def test_play_from_trash_offers_trash_tokens():
    st = _state(trash=["Y8", "OTHER"], characters=[CardInst(iid="c1", card_id="Y6")])
    apply_ops(
        st,
        0,
        [
            {
                "op": "play_from_hand",
                "count": 1,
                "card_type": "character",
                "optional": True,
                "cost_eq": 8,
                "name_contains": "Yamato|大和",
                "color": "black",
                "from_zone": "trash",
            }
        ],
        _catalog,
    )
    assert st.pending_choice is not None
    assert st.pending_choice.options
    assert all(o.startswith("trash:") for o in st.pending_choice.options)
    assert any(o.endswith(":Y8") for o in st.pending_choice.options)
    assert not any(o.endswith(":OTHER") for o in st.pending_choice.options)
