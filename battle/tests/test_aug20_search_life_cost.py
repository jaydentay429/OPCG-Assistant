"""Multi-add search, brothers filters, face-up life public view, opp-turn +cost."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_abilities, reload_effect_library  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import (  # noqa: E402
    apply_action,
    effective_character_cost,
    legal_actions,
    public_view,
)
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

CATALOG = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    return CATALOG.get(cid) or {"cost": 1, "power": 1000, "name": cid, "name_en": cid}


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP01-001"),
        deck=list(kwargs.get("deck0", ["D"] * 20)),
        hand=list(kwargs.get("hand0", ["H1", "H2", "H3"])),
        life=list(kwargs.get("life0", ["L"] * 5)),
        life_face=list(kwargs.get("life_face0", [])),
        characters=list(kwargs.get("chars0", [])),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id=kwargs.get("leader1", "OP01-001"),
        deck=["B"] * 20,
        hand=["O1", "O2"],
        life=["M"] * 5,
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def test_st13_013_search_accepts_brothers_cost_lte_5():
    reload_effect_library(force=True)
    ab = get_abilities("ST13-013", "on_play")[0]
    op = ab["ops"][0]
    assert op["op"] == "search_deck"
    assert "Portgas.D.Ace" in op["name_contains"]
    assert "Monkey.D.Luffy" in op["name_contains"]
    assert op.get("cost_lte") == 5

    st = _state(deck0=["ACE5", "ACE6", "LUFFY", "OTHER", "ACE5"])

    def cat(cid: str):
        if cid == "ACE5":
            return {"name": "波特卡斯・D・艾斯", "name_en": "Portgas.D.Ace", "cost": 5, "type": "CHARACTER"}
        if cid == "ACE6":
            return {"name": "波特卡斯・D・艾斯", "name_en": "Portgas.D.Ace", "cost": 6, "type": "CHARACTER"}
        if cid == "LUFFY":
            return {"name": "蒙其・D・魯夫", "name_en": "Monkey.D.Luffy", "cost": 4, "type": "CHARACTER"}
        if cid == "OTHER":
            return {"name": "娜美", "name_en": "Nami", "cost": 3, "type": "CHARACTER"}
        return catalog(cid)

    apply_ops(st, 0, [op], cat)
    assert st.pending_search is not None
    # indices: 0 ACE5 ok, 1 ACE6 no, 2 LUFFY ok, 3 OTHER no, 4 ACE5 ok
    assert set(st.pending_search.eligible) == {0, 2, 4}


def test_op16_077_multi_add_requires_confirm():
    reload_effect_library(force=True)
    ab = get_abilities("OP16-077", "on_play")[0]
    assert ab["ops"][0].get("max_add") == 2
    assert ab["ops"][1].get("op") == "trash_hand"

    def cat(cid: str):
        if cid.startswith("NAVY"):
            return {
                "name": "海軍測試",
                "name_en": "Navy Test",
                "cost": 3,
                "type": "CHARACTER",
                "traits": ["海軍"],
                "traits_en": ["Navy"],
            }
        return {"name": "Other", "name_en": "Other", "cost": 2, "type": "CHARACTER", "traits": [], "traits_en": []}

    st = _state(deck0=["NAVY1", "NAVY2", "X", "NAVY3", "Y"] + ["PAD"] * 10, hand0=["H1", "H2"])
    apply_ops(st, 0, [ab["ops"][0]], cat)
    assert st.pending_search is not None
    assert st.pending_search.max_add == 2
    assert set(st.pending_search.eligible) == {0, 1, 3}

    r1 = apply_action(st, 0, {"type": "select_search", "index": 0}, cat)
    assert r1["ok"]
    assert st.pending_search is not None
    assert st.pending_search.selected == [0]
    assert any(a.get("type") == "confirm_search" for a in legal_actions(st, 0, cat))

    r2 = apply_action(st, 0, {"type": "select_search", "index": 1}, cat)
    assert r2["ok"]
    assert st.pending_search.selected == [0, 1]

    r3 = apply_action(st, 0, {"type": "confirm_search"}, cat)
    assert r3["ok"]
    # After resolve, either ordering leftovers or trash_hand remaining
    hand = st.players[0].hand
    assert "NAVY1" in hand and "NAVY2" in hand


def test_face_up_life_visible_in_public_view():
    st = _state(life0=["OP16-108", "L2", "L3"], life_face0=[True, False, False])
    view = public_view(st, viewer_seat=1, catalog=catalog)
    faces = view["players"][0]["life_faces"]
    assert faces[0]["face_up"] is True
    assert faces[0]["card_id"] == "OP16-108"
    assert faces[1]["face_up"] is False
    assert faces[1]["card_id"] is None


def test_life_damage_pops_matching_life_face():
    """Face-up Life flag must leave with the damaged card, not stick on the next."""
    from battle.engine import _deal_one_life_damage

    st = _state(life0=["FACEUP", "L2", "L3"], life_face0=[True, False, False], deck0=["D"] * 20)
    paused = _deal_one_life_damage(st, 0, catalog, banish=False, remaining_hits=0)
    assert paused is False
    assert st.players[0].life == ["L2", "L3"]
    assert st.players[0].life_face == [False, False]
    assert "FACEUP" in st.players[0].hand
    faces = public_view(st, viewer_seat=1, catalog=catalog)["players"][0]["life_faces"]
    assert faces[0]["face_up"] is False
    assert faces[0]["card_id"] is None
    assert faces[1]["face_up"] is False


def test_op16_080_opp_turn_raises_character_cost():
    reload_effect_library(force=True)
    ch = CardInst(iid="c1", card_id="OP01-016", rested=False)
    st = _state(leader0="OP16-080", chars0=[ch], turn_seat=1)  # opponent's turn for seat 0
    cost = effective_character_cost(st, 0, ch, catalog)
    printed = int(str(catalog("OP01-016").get("cost") or 0).split()[0] or 0)
    assert cost == printed + 1
    view = public_view(st, viewer_seat=0, catalog=catalog)
    assert view["players"][0]["characters"][0]["cost"] == printed + 1


def test_op14_086_trash_gate_bw_cost_aura():
    reload_effect_library(force=True)
    bw = CardInst(iid="bw", card_id="OP14-083", rested=False)
    self_c = CardInst(iid="self", card_id="OP14-086", rested=False)
    other = CardInst(iid="ot", card_id="OP16-110", rested=False)
    st = _state(chars0=[self_c, bw, other], turn_seat=0)
    st.players[0].trash = [f"T{i}" for i in range(7)]
    assert effective_character_cost(st, 0, self_c, catalog) == int(catalog("OP14-086")["cost"]) + 2
    assert effective_character_cost(st, 0, bw, catalog) == int(catalog("OP14-083")["cost"]) + 2
    assert effective_character_cost(st, 0, other, catalog) == int(catalog("OP16-110")["cost"])


def test_op16_110_on_ko_after_redirect_battle():
    reload_effect_library(force=True)
    from battle.engine import _resolve_attack
    from battle.state import PendingAttack

    vic = CardInst(iid="vic", card_id="OP16-110", rested=False)
    st = _state(leader0="OP16-080", chars0=[vic], turn_seat=1, deck0=["D"] * 20)
    st.players[0].deck = ["D"] * 20
    st.players[1].leader_power_mod = 10000
    st.players[1].characters = [
        CardInst(iid="o1", card_id="OP14-083"),
        CardInst(iid="o2", card_id="OP14-079"),  # cost usually ≤6
    ]
    st.phase = "attack"
    st.attack = PendingAttack(attacker_seat=1, attacker_iid="leader", target_iid="leader", declared_power=5000)
    apply_ops(st, 0, [{"op": "redirect_attack", "target_iid": "vic"}], catalog)
    assert st.attack and st.attack.target_iid == "vic"
    hand_before = list(st.players[0].hand)
    _resolve_attack(st, catalog)
    assert "OP16-110" in st.players[0].trash
    assert len(st.players[0].hand) == len(hand_before) + 1
    # Rest up to 1 cost≤6 — either choice prompt or auto-rest when only one eligible.
    rested = [c for c in st.players[1].characters if c.rested]
    assert st.pending_choice is not None or rested


def test_op16_108_add_trash_to_life_face_up():
    reload_effect_library(force=True)
    st = _state(leader0="OP16-080", hand0=["OP16-108", "H1"], life0=["L"] * 4, life_face0=[])
    st.players[0].trash = ["OP16-110"]
    st.players[0].don_active = 10
    r = apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)
    assert r["ok"]
    # Trash hand cost
    assert st.pending_choice is not None
    apply_action(st, 0, {"type": "select_choice", "target_iid": st.pending_choice.options[0]}, catalog)
    # Pick trash card → Life face-up
    assert st.pending_choice is not None
    assert st.pending_choice.then_op and st.pending_choice.then_op.get("face") == "up"
    apply_action(st, 0, {"type": "select_choice", "target_iid": st.pending_choice.options[0]}, catalog)
    assert st.players[0].life[0] == "OP16-110"
    assert st.players[0].life_face[0] is True
    faces = public_view(st, viewer_seat=1, catalog=catalog)["players"][0]["life_faces"]
    assert faces[0]["face_up"] is True and faces[0]["card_id"] == "OP16-110"


def test_op15_113_trash_then_auto_deck_top_life():
    reload_effect_library(force=True)
    from battle.effects import apply_ops

    st = _state(hand0=["H1", "H2"], life0=["L"] * 4, life_face0=[False] * 4, deck0=["TOP", "D2"] + ["D"] * 20)
    ops = get_abilities("OP15-113", "on_play")[0]["ops"]
    apply_ops(st, 0, list(ops), catalog)
    assert st.pending_choice is not None  # trash hand cost
    apply_action(st, 0, {"type": "select_choice", "target_iid": st.pending_choice.options[0]}, catalog)
    # After trash, deck top goes to Life with no second choice
    assert st.pending_choice is None
    assert st.players[0].life[0] == "TOP"
    assert st.players[0].life_face[0] is False


def test_op12_006_or_red_event():
    reload_effect_library(force=True)
    ab = get_abilities("OP12-006", "on_play")[0]
    op = ab["ops"][0]
    assert op.get("or_event") is True
    assert str(op.get("color") or "").lower() == "red"


def test_prb02_018_brothers_names():
    reload_effect_library(force=True)
    ab = get_abilities("PRB02-018", "on_play")[0]
    nc = ab["ops"][0]["name_contains"]
    assert "Sabo" in nc and "Portgas.D.Ace" in nc and "Monkey.D.Luffy" in nc
