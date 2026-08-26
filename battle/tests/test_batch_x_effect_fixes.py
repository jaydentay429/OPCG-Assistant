"""Batch-X effect encoding fixes (Hancock/Kuja, Perfume Feet, look+attach)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import fire_own_trait_leave_or_ko  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def setup_module() -> None:
    reload_effect_library()


def catalog(cid: str):
    return dict(_CARDS.get(cid) or {"cost": 1, "name": cid, "power": 5000})


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.pop("leader0", "OP14-041"),
        deck=["X"] * 30,
        hand=kwargs.pop("hand0", []),
        life=kwargs.pop("life0", ["L"] * 5),
        characters=kwargs.pop("chars0", []),
        don_rested=kwargs.pop("don_rested", 0),
        leader_don=kwargs.pop("leader_don", 0),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["Y"] * 30,
        hand=kwargs.pop("hand1", []),
        life=kwargs.pop("life1", ["M"] * 5),
        characters=kwargs.pop("chars1", []),
    )
    return MatchState(
        room_code="X",
        status="playing",
        phase="main",
        turn_seat=kwargs.pop("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def test_op14_041_ko_watcher_base_power() -> None:
    abs_ = get_card_entry("OP14-041")["abilities"]
    ko = [a for a in abs_ if a.get("on_own_trait_ko")]
    assert len(ko) == 2
    for a in ko:
        assert a.get("require_victim_base_power_gte") == 5000
        assert a.get("require_own_char_power_gte") is None
        assert a.get("require_don_attached_gte") == 1
        assert a.get("once") is True


def test_op14_105_reveal_and_attach_all() -> None:
    act = next(a for a in get_card_entry("OP14-105")["abilities"] if a["timing"] == "activate_main")
    ops = act["ops"]
    assert ops[0]["op"] == "reveal_hand"
    assert ops[0].get("count") == 3
    assert ops[0].get("as_cost") is True
    assert "Amazon Lily" in str(ops[0].get("trait_contains") or "") or "亞馬遜" in str(
        ops[0].get("trait_contains") or ""
    )
    assert ops[1]["op"] == "attach_don"
    assert ops[1].get("all") is True
    assert ops[1].get("from_rested") or ops[1].get("as_rested")


def test_op14_107_opp_life_only() -> None:
    play = next(a for a in get_card_entry("OP14-107")["abilities"] if a["timing"] == "on_play")
    assert play.get("require_opp_life_lte") == 3
    assert play.get("require_life_lte") is None


def test_op14_114_kuja_rested_don() -> None:
    act = next(a for a in get_card_entry("OP14-114")["abilities"] if a["timing"] == "activate_main")
    op = act["ops"][0]
    assert op["op"] == "attach_don"
    assert op.get("from_rested") or op.get("as_rested")
    assert "Kuja" in str(op.get("trait_contains") or "") or "九蛇" in str(op.get("trait_contains") or "")


def test_op07_057_deny_when_attacks() -> None:
    op = get_card_entry("OP07-057")["abilities"][0]["ops"][0]
    assert op["op"] == "buff"
    assert op.get("also_deny_blocker_when_attacks") is True
    assert op.get("duration") == "turn"
    assert "Warlords" in str(op.get("trait_contains") or "") or "七武海" in str(op.get("trait_contains") or "")


def test_op12_077_deny_when_attacks() -> None:
    op = get_card_entry("OP12-077")["abilities"][0]["ops"][0]
    assert op.get("also_deny_blocker_when_attacks") is True
    assert "Law" in str(op.get("name_contains") or "") or "羅" in str(op.get("name_contains") or "")


def test_st17_004_look_then_attach() -> None:
    ops = get_card_entry("ST17-004")["abilities"][0]["ops"]
    assert ops[0]["op"] == "look_deck"
    assert ops[0].get("count") == 3
    assert ops[1]["op"] == "attach_don"
    assert "Warlords" in str(ops[1].get("trait_contains") or "") or "七武海" in str(
        ops[1].get("trait_contains") or ""
    )


def test_op16_113_blocker_both_turns() -> None:
    abs_ = get_card_entry("OP16-113")["abilities"]
    blockers = [a for a in abs_ if a.get("require_life_lte") == 2]
    timings = {a["timing"] for a in blockers}
    assert timings == {"your_turn", "opponent_turn"}


def test_p109_look_then_attach() -> None:
    ops = get_card_entry("P-109")["abilities"][0]["ops"]
    assert ops[0]["op"] == "look_deck"
    assert ops[1]["op"] == "attach_don"


def test_attach_don_all_runtime() -> None:
    st = _state(
        leader0="OP14-041",
        don_rested=5,
        chars0=[
            CardInst(iid="c1", card_id="OP14-114", rested=False),
            CardInst(iid="c2", card_id="OP14-107", rested=False),
        ],
    )
    p0 = st.player(0)
    logs = apply_ops(
        st,
        0,
        [
            {
                "op": "attach_don",
                "count": 1,
                "as_rested": True,
                "from_rested": True,
                "target_kind": "own_leader_or_character",
                "all": True,
            }
        ],
        catalog,
    )
    assert p0.leader_don == 1
    assert p0.characters[0].don_attached == 1
    assert p0.characters[1].don_attached == 1
    assert p0.don_rested == 2
    assert any(l.get("key") == "play.log.attach_don" for l in logs)


def test_buff_also_deny_blocker_runtime() -> None:
    st = _state(chars0=[CardInst(iid="w1", card_id="OP14-112", rested=False)])
    p0 = st.player(0)
    apply_ops(
        st,
        0,
        [
            {
                "op": "buff",
                "amount": 2000,
                "target_kind": "own_character",
                "target_iid": "w1",
                "duration": "turn",
                "also_deny_blocker_when_attacks": True,
            }
        ],
        catalog,
    )
    assert any(r.get("when_attacker_iid") == "w1" for r in p0.deny_blocker)


def test_fire_on_own_trait_ko_victim_power() -> None:
    st = _state(leader0="OP14-041", leader_don=1, life1=["x", "y"])
    victim = {
        "name": "test",
        "power": 5000,
        "traits_en": ["Kuja Pirates"],
        "traits": ["九蛇海賊團"],
    }
    cats = {"OP14-041": catalog("OP14-041"), "V1": victim}

    def cat(cid: str):
        return dict(cats.get(cid) or catalog(cid))

    fire_own_trait_leave_or_ko(st, 0, "V1", cat, by_ko=True)
    p0, p1 = st.player(0), st.player(1)
    assert st.pending_choice is not None or len(p1.life) < 2 or len(p0.hand) > 0


if __name__ == "__main__":
    setup_module()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
