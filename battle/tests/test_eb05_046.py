"""EB05-046 Yamato: Blocker and +3000 only vs an opponent Character with base power 8000+.

On the opponent's attack, you may trash 1 card from hand. The trash-10 check is
after that cost (engine convention for 「：若…」): the discarded card counts.
Empty hand cannot pay, so the effect does not resolve.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if "battle" not in sys.modules:
    pkg = types.ModuleType("battle")
    pkg.__path__ = [str(ROOT / "battle")]
    sys.modules["battle"] = pkg

from battle.effect_library import get_abilities, get_card_entry, reload_effect_library, resolve_ability  # noqa: E402
from battle.effects import has_blocker  # noqa: E402
from battle.engine import _confirm_effect, _run_pending_effect, apply_action, inst_power  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "BIG": {"card_id": "BIG", "card_type": "CHARACTER", "cost": 8, "power": 9000, "name": "Big"},
        "SMALL": {"card_id": "SMALL", "card_type": "CHARACTER", "cost": 4, "power": 4000, "name": "Small"},
        "OP01-001": {"card_id": "OP01-001", "card_type": "LEADER", "power": 5000, "name": "Luffy"},
        "OP02-001": {"card_id": "OP02-001", "card_type": "LEADER", "power": 5000, "name": "Law"},
        "HAND": {"card_id": "HAND", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "Hand"},
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, opp_cards: list[CardInst] | None, hand: list[str] | None = None, trash: int = 0) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["D"] * 20,
        hand=list(hand or []),
        life=["L"] * 5,
        trash=["T"] * trash,
        don_active=0,
        don_given=0,
        turns_completed=1,
        characters=[CardInst(iid="yamato", card_id="EB05-046", rested=False, summoning_sick=False)],
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP02-001",
        deck=["B"] * 20,
        hand=[],
        life=["M"] * 5,
        characters=list(opp_cards or []),
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


def test_eb05_046_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-046")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-046 abilities dropped on normalize"
    for timing in ("your_turn", "opponent_turn"):
        aura = next(a for a in get_abilities("EB05-046", timing))
        assert aura.get("require_opp_field_char_base_power_gte") == 8000
        assert any(o.get("op") == "grant_keyword" and o.get("keyword") == "blocker" for o in aura["ops"])
        assert any(o.get("op") == "buff_self" and o.get("amount") == 3000 for o in aura["ops"])
    atk = next(a for a in get_abilities("EB05-046", "on_opponent_attack"))
    assert atk.get("require_trash_gte") is None
    assert atk["ops"][0].get("op") == "trash_hand"
    assert atk["ops"][0].get("as_cost") is True
    assert atk["ops"][0].get("optional") is True
    assert atk["ops"][1].get("op") == "set_base_power"
    assert atk["ops"][1].get("amount") == 7000
    assert atk["ops"][1].get("target_kind") == "leader"
    assert atk["ops"][1].get("duration") == "turn"
    assert atk["ops"][1].get("require_trash_gte") == 10


def test_eb05_046_blocker_and_power_only_for_printed_8000():
    reload_effect_library(force=True)
    big = _state(opp_cards=[CardInst(iid="big", card_id="BIG", rested=False, summoning_sick=False)])
    info = catalog("EB05-046")
    yamato = big.players[0].characters[0]
    assert has_blocker(info, yamato, state=big, owner_seat=0, catalog=catalog) is True
    assert inst_power(big, 0, "yamato", catalog) == 8000
    big.turn_seat = 1
    assert has_blocker(info, yamato, state=big, owner_seat=0, catalog=catalog) is True
    assert inst_power(big, 0, "yamato", catalog) == 8000

    none = _state(opp_cards=[])
    yamato = none.players[0].characters[0]
    assert has_blocker(info, yamato, state=none, owner_seat=0, catalog=catalog) is False
    assert inst_power(none, 0, "yamato", catalog) == 5000

    buffed = _state(
        opp_cards=[CardInst(iid="small", card_id="SMALL", rested=False, summoning_sick=False, power_mod=5000)]
    )
    assert inst_power(buffed, 1, "small", catalog) == 9000
    yamato = buffed.players[0].characters[0]
    assert has_blocker(info, yamato, state=buffed, owner_seat=0, catalog=catalog) is False
    assert inst_power(buffed, 0, "yamato", catalog) == 5000


def _resolve_attack_trash(st: MatchState) -> None:
    pending = resolve_ability(
        st,
        0,
        "EB05-046",
        "yamato",
        "on_opponent_attack",
        catalog("EB05-046"),
        None,
        allow_llm=False,
        catalog=catalog,
    )
    assert pending is not None and pending.ops
    _run_pending_effect(st, pending, catalog)
    if st.pending_effect is not None:
        _confirm_effect(st, 0, True, catalog)


def test_eb05_046_trash_checked_after_discard_cost():
    reload_effect_library(force=True)
    # 9 in trash + the discarded card = 10, so the effect applies.
    st = _state(opp_cards=[], hand=["HAND"], trash=9)
    before = inst_power(st, 0, "leader", catalog)
    _resolve_attack_trash(st)
    assert st.pending_choice is not None
    token = st.pending_choice.options[0]
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": token}, catalog)["ok"]
    assert st.players[0].hand == []
    assert len(st.players[0].trash) == 10
    assert inst_power(st, 0, "leader", catalog) == 7000
    assert before == 5000

    # 8 in trash + discard = 9, still under 10: cost is paid, effect does not apply.
    st = _state(opp_cards=[], hand=["HAND"], trash=8)
    _resolve_attack_trash(st)
    token = st.pending_choice.options[0]
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": token}, catalog)["ok"]
    assert len(st.players[0].trash) == 9
    assert inst_power(st, 0, "leader", catalog) == 5000

    # Already 10 before paying: still applies.
    st = _state(opp_cards=[], hand=["HAND"], trash=10)
    _resolve_attack_trash(st)
    token = st.pending_choice.options[0]
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": token}, catalog)["ok"]
    assert inst_power(st, 0, "leader", catalog) == 7000


def test_eb05_046_empty_hand_cannot_activate():
    reload_effect_library(force=True)
    st = _state(opp_cards=[], hand=[], trash=12)
    before = inst_power(st, 0, "leader", catalog)
    _resolve_attack_trash(st)
    assert st.pending_choice is None
    assert st.players[0].hand == []
    assert len(st.players[0].trash) == 12
    assert inst_power(st, 0, "leader", catalog) == before


def test_eb05_046_declining_discard_does_not_set_power():
    reload_effect_library(force=True)
    st = _state(opp_cards=[], hand=["HAND"], trash=12)
    _resolve_attack_trash(st)
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert st.players[0].hand == ["HAND"]
    assert len(st.players[0].trash) == 12
    assert inst_power(st, 0, "leader", catalog) == 5000
