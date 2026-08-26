"""ABC fidelity: engine primitives + focus card paper correctness."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_abilities, reload_effect_library, resolve_ability  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import _ability_board_conditions_ok, _attack_tax_needed, legal_actions  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _catalog():
    return json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP01-001"),
        deck=["A"] * 20,
        hand=list(kwargs.get("hand0", ["H1", "H2", "H3"])),
        life=list(kwargs.get("life0", ["L"] * 5)),
        trash=list(kwargs.get("trash0", [])),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id=kwargs.get("leader1", "OP01-001"),
        deck=["B"] * 20,
        hand=list(kwargs.get("hand1", ["H4", "H5"])),
        life=list(kwargs.get("life1", ["M"] * 5)),
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
    p0.turns_completed = 1
    p1.turns_completed = 1
    return st


def test_choose_one_self_and_opponent():
    st = _state()
    cat = _catalog()

    def catalog(cid):
        return cat.get(cid) or {"cost": 1, "power": 1000, "name": cid}

    logs = apply_ops(
        st,
        0,
        [
            {
                "op": "choose_one",
                "chooser": "self",
                "options": [
                    {"id": "a", "label": "draw", "ops": [{"op": "draw", "count": 1}]},
                    {"id": "b", "label": "don", "ops": [{"op": "gain_don", "count": 1}]},
                ],
            }
        ],
        catalog,
    )
    assert st.pending_choice is not None
    assert st.pending_choice.target_kind == "effect_option"
    assert st.pending_choice.seat == 0
    assert st.pending_choice.controller_seat == 0

    st2 = _state()
    apply_ops(
        st2,
        0,
        [
            {
                "op": "choose_one",
                "chooser": "opponent",
                "options": [
                    {"id": "a", "label": "x", "ops": [{"op": "draw", "count": 1}]},
                    {"id": "b", "label": "y", "ops": [{"op": "add_life", "count": 1}]},
                ],
            }
        ],
        catalog,
    )
    assert st2.pending_choice is not None
    assert st2.pending_choice.seat == 1
    assert st2.pending_choice.controller_seat == 0


def test_attack_tax_blocks_and_pays():
    st = _state(hand1=["A", "B"])
    st.players[1].attack_tax_rules.append({"all": True, "trash_hand": 2})
    st.players[1].characters.append(CardInst(iid="c1", card_id="OP01-016", rested=False, summoning_sick=False))
    st.turn_seat = 1
    cat = _catalog()

    def catalog(cid):
        return cat.get(cid) or {"cost": 1, "power": 5000, "name": cid, "card_type": "CHARACTER"}

    assert _attack_tax_needed(st.players[1], "c1") == 2
    actions = legal_actions(st, 1, catalog)
    attacks = [a for a in actions if a.get("type") == "attack"]
    assert attacks  # hand has 2
    st.players[1].hand = ["A"]
    actions = legal_actions(st, 1, catalog)
    assert not any(a.get("type") == "attack" for a in actions)


def test_life_to_hand_life_owner():
    st = _state(life1=["LIFE1", "LIFE2"])
    cat = _catalog()

    def catalog(cid):
        return cat.get(cid) or {}

    apply_ops(
        st,
        0,
        [{"op": "life_to_hand", "count": 1, "owner": "opponent", "hand_owner": "life_owner"}],
        catalog,
    )
    assert "LIFE1" in st.players[1].hand
    assert "LIFE1" not in st.players[0].hand
    assert st.players[1].life[0] == "LIFE2"


def test_cannot_be_ko_trait_any():
    st = _state()
    st.players[0].characters = [
        CardInst(iid="a", card_id="TRAIT_SH"),
        CardInst(iid="b", card_id="TRAIT_NAVY"),
    ]

    def catalog(cid):
        if cid == "TRAIT_SH":
            return {"traits_en": ["Straw Hat Crew"], "traits": ["草帽一行人"], "name": "SH"}
        if cid == "TRAIT_NAVY":
            return {"traits_en": ["Navy"], "traits": ["海軍"], "name": "Navy"}
        return {}

    apply_ops(
        st,
        0,
        [{"op": "cannot_be_ko", "all": True, "trait_any": ["Straw Hat Crew"], "target_kind": "own_character"}],
        catalog,
    )
    assert st.players[0].characters[0].cannot_be_ko is True
    assert st.players[0].characters[1].cannot_be_ko is False


def test_resolve_ability_gates_life_and_don_field():
    reload_effect_library(force=True)
    cat = _catalog()
    info = cat["OP05-072"]
    st = _state(life0=["L"] * 5)
    st.players[0].don_active = 2  # field DON low

    def catalog(cid):
        return cat.get(cid) or {}

    pending = resolve_ability(st, 0, "OP05-072", "x", "on_play", info, None, allow_llm=False, catalog=catalog)
    assert pending is None  # require_don_field_gte 8

    st.players[0].don_active = 8
    pending = resolve_ability(st, 0, "OP05-072", "x", "on_play", info, None, allow_llm=False, catalog=catalog)
    assert pending is not None
    assert any(o.get("op") == "buff" and o.get("amount") == -2000 for o in pending.ops)


def test_focus_cards_ops_shape():
    reload_effect_library(force=True)
    checks = {
        "OP08-043": ("on_play", ["attack_tax"]),
        "OP14-119": ("your_turn", ["deny_rest"]),
        "ST07-015": ("on_play", ["choose_one"]),
        "ST11-003": ("on_play", ["choose_one"]),
        "OP08-117": ("on_play", ["trash_life", "ko"]),
        "EB04-054": ("on_ko", ["life_to_hand"]),
        "OP15-097": ("on_play", ["deny_attack"]),
        "OP08-112": ("on_play", ["deny_attack"]),
    }
    for cid, (timing, ops) in checks.items():
        ab = next((a for a in get_abilities(cid) if a.get("timing") == timing), None)
        assert ab is not None, cid
        got = [o.get("op") for o in ab.get("ops") or []]
        assert got[: len(ops)] == ops, f"{cid}: {got}"
        if cid == "OP08-112":
            assert ab["ops"][0].get("exclude_name")
        if cid == "OP15-097":
            assert ab.get("require_trash_gte") == 10
            assert ab["ops"][0].get("base_cost_lte") == 5
        if cid == "EB04-054":
            assert ab["ops"][0].get("hand_owner") == "life_owner"
        if cid == "OP14-119":
            assert ab.get("trigger_on") == "self_rested"


def test_board_conditions_leader_name():
    st = _state(leader0="ST11-001")  # Uta if exists else whatever
    cat = _catalog()
    # Force leader name
    st.players[0].leader_card_id = "ST11-001"

    def catalog(cid):
        info = dict(cat.get(cid) or {})
        if cid == "ST11-001":
            info["name_en"] = "Uta"
            info["name"] = "美音"
        return info

    ok = _ability_board_conditions_ok(
        st, 0, {"require_leader_name": "Uta"}, catalog
    )
    assert ok is True
    bad = _ability_board_conditions_ok(
        st, 0, {"require_leader_name": "Luffy"}, catalog
    )
    assert bad is False
