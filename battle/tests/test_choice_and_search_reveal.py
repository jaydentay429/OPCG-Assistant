"""Opponent hand choice + restricted search reveal."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effects import (  # noqa: E402
    _parse_opponent_hand_to_bottom_ops,
    apply_ops,
)
from battle.engine import _resolve_choice, _resolve_search, public_view  # noqa: E402
from battle.state import MatchState, PlayerState  # noqa: E402


def _catalog():
    return json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=list(kwargs.get("deck0", ["D"] * 20)),
        hand=list(kwargs.get("hand0", ["H1", "H2", "H3"])),
        life=["L"] * 5,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["B"] * 20,
        hand=list(kwargs.get("hand1", ["O1", "O2", "O3", "O4", "O5", "O6"])),
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


def test_eb04_022_parser_attaches_hand_gate():
    text = (
        "【登場時】可以廢棄2張自己的手牌：若對手的手牌有6張以上時，"
        "對手將2張自身的手牌依任意順序放置在卡組下面。"
    )
    ops = _parse_opponent_hand_to_bottom_ops(text)
    assert ops and ops[0]["op"] == "opponent_hand_to_bottom"
    assert ops[0]["count"] == 2
    assert ops[0].get("require_opp_hand_gte") == 6


def test_opponent_hand_to_bottom_lets_opponent_choose():
    st = _state()
    cat = _catalog()

    def catalog(cid):
        return cat.get(cid) or {"cost": 1, "power": 1000, "name": cid}

    apply_ops(
        st,
        0,
        [{"op": "opponent_hand_to_bottom", "count": 2, "require_opp_hand_gte": 6}],
        catalog,
    )
    assert st.pending_choice is not None
    assert st.pending_choice.seat == 1  # opponent chooses
    assert st.pending_choice.controller_seat == 0
    assert all(o.startswith("hand:") for o in st.pending_choice.options)

    pick = st.pending_choice.options[0]
    cid = pick.split(":")[-1]
    before = list(st.players[1].hand)
    _resolve_choice(st, 1, pick, catalog)
    assert cid not in st.players[1].hand
    assert st.players[1].deck[-1] == cid or st.pending_choice is not None
    # Second pick still pending (n=2)
    assert st.pending_choice is not None
    assert st.pending_choice.seat == 1
    assert len(st.players[1].hand) == len(before) - 1


def test_opponent_hand_gate_skips_when_below():
    st = _state(hand1=["A", "B", "C"])  # 3 < 6
    cat = _catalog()

    def catalog(cid):
        return cat.get(cid) or {"cost": 1, "name": cid}

    apply_ops(
        st,
        0,
        [{"op": "opponent_hand_to_bottom", "count": 2, "require_opp_hand_gte": 6}],
        catalog,
    )
    assert st.pending_choice is None
    assert len(st.players[1].hand) == 3


def test_opp_trash_hand_opponent_chooses():
    st = _state(hand1=["A", "B", "C", "D", "E"])
    cat = _catalog()

    def catalog(cid):
        return cat.get(cid) or {"cost": 1, "name": cid}

    apply_ops(st, 0, [{"op": "trash_hand", "count": 1, "optional": False, "owner": "opponent"}], catalog)
    assert st.pending_choice is not None
    assert st.pending_choice.seat == 1
    assert st.pending_choice.controller_seat == 0


def test_restricted_search_reveals_ids_to_opponent():
    st = _state(deck0=["KEEP", "SKIP", "OTHER", "X", "Y"])

    def catalog(cid):
        traits = ["Pirate"] if cid == "KEEP" else ["Navy"]
        return {"cost": 1, "name": cid, "card_type": "CHARACTER", "traits": traits}

    apply_ops(
        st,
        0,
        [
            {
                "op": "search_deck",
                "top_n": 3,
                "max_add": 1,
                "trait_contains": "Pirate",
                "order_bottom": False,
            }
        ],
        catalog,
    )
    assert st.pending_search is not None
    assert st.pending_search.reveal_adds is True
    assert 0 in st.pending_search.eligible
    _resolve_search(st, 0, [0], catalog)
    assert st.public_search_adds == {"seat": 0, "n": 1, "ids": ["KEEP"]}
    view = public_view(st, 1, catalog)
    assert view["public_search_adds"]["ids"] == ["KEEP"]
    assert any(e.get("key") == "play.log.searches_reveal" for e in st.log)


def test_unrestricted_search_count_only():
    st = _state(deck0=["A1", "A2", "A3", "A4", "A5"])
    cat = _catalog()

    def catalog(cid):
        return cat.get(cid) or {"cost": 1, "name": cid, "card_type": "CHARACTER"}

    apply_ops(
        st,
        0,
        [{"op": "search_deck", "top_n": 3, "max_add": 1, "order_bottom": False}],
        catalog,
    )
    assert st.pending_search is not None
    assert st.pending_search.reveal_adds is False
    _resolve_search(st, 0, [0], catalog)
    assert st.public_search_adds == {"seat": 0, "n": 1, "ids": []}
    assert any(e.get("key") == "play.log.searches" and e.get("n") == 1 for e in st.log)
    view = public_view(st, 1, catalog)
    assert view["public_search_adds"]["ids"] == []
    assert view["public_search_adds"]["n"] == 1


def test_op16_026_search_ignores_followup_cost_lte():
    """Paper: look top 3 → add Impel Down; cost≤2 is only the later play_from_hand."""
    from battle.effect_library import get_card_entry, reload_effect_library

    reload_effect_library(force=True)
    entry = get_card_entry("OP16-026")
    assert entry
    ops = entry["abilities"][0]["ops"]
    assert ops[0]["op"] == "search_deck"
    assert ops[0].get("cost_lte") is None
    assert ops[1]["op"] == "play_from_hand"
    assert ops[1].get("cost_lte") == 2

    st = _state(deck0=["OP02-062", "ST12-003", "OP02-063", "X", "Y"])
    cat = _catalog()

    def catalog(cid):
        return cat.get(cid) or {"cost": 1, "name": cid, "card_type": "CHARACTER"}

    apply_ops(st, 0, [dict(ops[0], card_id="OP16-026")], catalog)
    assert st.pending_search is not None
    # OP02-062 / OP02-063 have 推進城; ST12-003 does not
    assert st.pending_search.eligible == [0, 2]


def test_similar_search_then_play_and_cost_gates():
    """EB02-013/028 dest=hand + follow-up play; cost≥4 / cost 2–8 searches."""
    from battle.effect_library import get_card_entry, reload_effect_library
    from battle.effects import _parse_look_top_search

    reload_effect_library(force=True)
    cat = _catalog()

    def catalog(cid):
        return cat.get(cid) or {"cost": 1, "name": cid, "card_type": "CHARACTER"}

    e013 = get_card_entry("EB02-013")
    ops = e013["abilities"][0]["ops"]
    assert ops[0]["destination"] == "hand"
    assert ops[1]["op"] == "play_from_hand"

    e028 = get_card_entry("EB02-028")
    ops = e028["abilities"][0]["ops"]
    assert ops[0]["destination"] == "hand"
    assert ops[0].get("cost_eq") == 2
    assert not ops[0].get("trait_contains")
    assert ops[1].get("as_rested") is True

    e008 = get_card_entry("EB02-008")
    assert e008["abilities"][0]["ops"][0].get("cost_gte") == 4
    assert e008["abilities"][0]["ops"][0].get("cost_eq") is None

    e060 = get_card_entry("EB03-060")
    s = e060["abilities"][0]["ops"][0]
    assert s.get("cost_gte") == 2 and s.get("cost_lte") == 8

    # cost≥4: cost4 and cost5 eligible, cost3 not
    st = _state(deck0=["C3", "C4", "C5", "X"])
    apply_ops(
        st,
        0,
        [{"op": "search_deck", "top_n": 3, "max_add": 1, "cost_gte": 4, "card_id": "EB02-008"}],
        lambda cid: {"cost": int(cid[1]) if cid.startswith("C") else 1, "name": cid, "card_type": "CHARACTER"},
    )
    assert st.pending_search.eligible == [1, 2]

    p = _parse_look_top_search(cat["EB02-028"]["effect"])
    assert p.get("cost_eq") == 2
    assert p.get("destination") == "hand"
    assert not p.get("trait_contains")
    p8 = _parse_look_top_search(cat["EB02-008"]["effect"])
    assert p8.get("cost_gte") == 4 and p8.get("cost_eq") is None


def test_piped_name_aliases_match_helpers_and_ops():
    """EN|ZH name_contains / exclude_name must match either printed name across ops."""
    from battle.effects import (
        _card_matches_name_contains,
        _card_excluded_by_name,
        _hand_card_matches_play_op,
        _choice_options,
        apply_ops,
    )
    from battle.effect_library import get_card_entry, reload_effect_library
    from battle.state import CardInst

    reload_effect_library(force=True)
    cat = _catalog()

    zou = cat["OP08-039"]
    assert _card_matches_name_contains(zou, "Zou|佐烏")
    assert _card_matches_name_contains(zou, "佐烏")
    assert not _card_matches_name_contains(zou, "Vegapunk|貝卡帕庫")

    luffy = next(c for c in cat.values() if (c.get("name_en") or "") == "Monkey.D.Luffy")
    assert _card_excluded_by_name(luffy, "Monkey.D.Luffy|蒙其・D・魯夫|蒙其・D・路飞")

    # play_from_hand: OP06-060 Vinsmoke Ichiji piped name
    ichiji = next(
        (c for cid, c in cat.items() if cid.startswith("OP06-") and "伊吉士" in str(c.get("name") or "")),
        None,
    )
    assert ichiji
    op = {"op": "play_from_hand", "card_type": "character", "name_contains": "賓什莫克・伊吉士|Vinsmoke Ichiji", "optional": True}
    assert _hand_card_matches_play_op(ichiji, op)

    # choice_options name filter for buff-style targets
    st = _state()
    st.players[0].characters = [
        CardInst(iid="a", card_id="OP08-039"),
        CardInst(iid="b", card_id="OP02-062"),
    ]

    def catalog(cid):
        return cat.get(cid) or {"cost": 1, "name": cid, "card_type": "CHARACTER"}

    opts = _choice_options(st, 0, "own_character", catalog, {"name_contains": "Zou|佐烏"})
    assert opts == ["a"]

    # OP16-048 still offers prisoner
    st2 = _state(deck0=["DRAW"] + ["X"] * 10, hand0=["OP16-042", "OTHER"])
    apply_ops(st2, 0, list(get_card_entry("OP16-048")["abilities"][0]["ops"]), catalog)
    assert st2.pending_choice is not None
    assert any(o.endswith(":OP16-042") for o in st2.pending_choice.options)
