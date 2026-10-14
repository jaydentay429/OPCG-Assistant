"""OP18-085 Cerberus: bounce self, then grant one keyword to Saint Shamrock."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.ai import pick_ai_action  # noqa: E402
from battle.effect_library import get_abilities, reload_effect_library  # noqa: E402
from battle.effects import detect_keywords, has_banish, has_blockerless, has_rush  # noqa: E402
from battle.engine import _clear_turn_duration_effects, apply_action  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402
from manual_cards import load_manual_cards  # noqa: E402

ROW = load_manual_cards()["OP18-085"]


def _catalog(cid: str) -> dict:
    table = {
        "OP18-085": dict(ROW),
        "OP18-119": {
            "card_id": "OP18-119",
            "card_type": "Character",
            "name": "夏姆洛克聖",
            "name_en": "Saint Shamrock",
            "cost": 8,
            "power": 9000,
            "effect": "",
        },
        "OTHER": {
            "card_id": "OTHER",
            "card_type": "Character",
            "name": "其他",
            "name_en": "Someone Else",
            "cost": 3,
            "power": 4000,
            "effect": "",
        },
        "BLK": {
            "card_id": "BLK",
            "card_type": "Character",
            "name": "阻擋者",
            "name_en": "Guard",
            "cost": 1,
            "power": 1000,
            "effect": "【防禦】(對手攻擊後，將這張卡片置為休息狀態即可使攻擊的對象換成這張卡片)",
        },
        "L0": {"card_type": "LEADER", "name": "L", "name_en": "L", "power": 5000, "life": 5},
    }
    return dict(table.get(cid) or {"card_id": cid, "card_type": "Character", "cost": 1, "power": 1000})


def _state(*own: CardInst, opp: list[CardInst] | None = None) -> MatchState:
    p0 = PlayerState(
        seat=0, user_id="u0", username="p0", is_ai=False, leader_card_id="L0", hand=[], deck=["D"] * 10
    )
    p1 = PlayerState(
        seat=1, user_id="u1", username="p1", is_ai=False, leader_card_id="L0", hand=[], deck=["D"] * 10
    )
    p0.characters = list(own)
    p1.characters = list(opp or [])
    return MatchState(room_code="t", status="playing", phase="main", turn_seat=0, players=[p0, p1])


def _cerb(**kw) -> CardInst:
    base = dict(iid="cerb", card_id="OP18-085", summoning_sick=False)
    base.update(kw)
    return CardInst(**base)


def _sham(iid: str = "sham", **kw) -> CardInst:
    base = dict(iid=iid, card_id="OP18-119", summoning_sick=True)
    base.update(kw)
    return CardInst(**base)


def _option_token(pending, keyword: str) -> str:
    for tok, ops in (pending.option_branches or {}).items():
        if ops and ops[0].get("keyword") == keyword:
            return tok
    raise AssertionError(keyword)


def _pay(st: MatchState) -> None:
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "cerb"}, _catalog)["ok"]
    pending = st.pending_choice
    assert pending is not None
    assert pending.options == ["cerb"]
    assert pending.optional is True
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "cerb"}, _catalog)["ok"]
    assert all(c.iid != "cerb" for c in st.players[0].characters)
    assert st.players[0].hand[-1] == "OP18-085"
    assert "OP18-085" not in st.players[1].hand


def setup_module() -> None:
    reload_effect_library(force=True)


def test_op18_085_encoding_and_not_innate_keywords():
    assert detect_keywords(ROW) == [] or set(detect_keywords(ROW)) <= {"trigger"}
    found = set(detect_keywords(ROW))
    assert "rush" not in found
    assert "banish" not in found
    assert "blockerless" not in found
    abilities = get_abilities("OP18-085", "activate_main")
    assert len(abilities) == 1
    ops = abilities[0]["ops"]
    assert ops[0]["op"] == "return_to_hand"
    assert ops[0]["target_kind"] == "self"
    assert ops[0]["as_cost"] is True
    assert ops[0]["optional"] is True
    assert ops[1]["op"] == "choose_one"
    keywords = [opt["ops"][0]["keyword"] for opt in ops[1]["options"]]
    assert keywords == ["rush", "banish", "blockerless"]
    for opt in ops[1]["options"]:
        grant = opt["ops"][0]
        assert grant["duration"] == "turn"
        assert grant["optional"] is True
        assert "夏姆洛克聖" in grant["name_contains"]
        assert "Saint Shamrock" in grant["name_contains"]


def test_pay_cost_returns_cerberus_to_owners_hand_then_grants_one_keyword():
    sham = _sham(summoning_sick=False)
    other = CardInst(iid="other", card_id="OTHER", summoning_sick=False)
    opp = _sham(iid="opp-sham", summoning_sick=False)
    st = _state(_cerb(), sham, other, opp=[opp])
    _pay(st)
    pending = st.pending_choice
    assert pending is not None
    assert pending.target_kind == "effect_option"
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": _option_token(pending, "banish")}, _catalog)["ok"]
    grant = st.pending_choice
    assert grant is not None
    assert grant.options == ["sham"]
    assert "other" not in grant.options
    assert "opp-sham" not in grant.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "sham"}, _catalog)["ok"]
    assert has_banish(_catalog("OP18-119"), sham)
    assert "banish" in sham.turn_keywords
    assert "banish" not in (sham.keywords or [])
    assert not has_rush(_catalog("OP18-119"), sham)
    assert not has_blockerless(_catalog("OP18-119"), sham)
    assert not has_banish(_catalog("OTHER"), other)
    assert not has_banish(_catalog("OP18-119"), opp)


def test_skip_cost_leaves_cerberus_and_grants_nothing():
    sham = _sham()
    st = _state(_cerb(), sham)
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "cerb"}, _catalog)["ok"]
    assert apply_action(st, 0, {"type": "skip_choice"}, _catalog)["ok"]
    assert st.pending_choice is None
    assert any(c.iid == "cerb" for c in st.players[0].characters)
    assert st.players[0].hand == []
    assert not has_rush(_catalog("OP18-119"), sham)


def test_rush_clears_summoning_sickness_and_expires():
    sham = _sham(summoning_sick=True)
    st = _state(_cerb(), sham)
    _pay(st)
    pending = st.pending_choice
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": _option_token(pending, "rush")}, _catalog)["ok"]
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "sham"}, _catalog)["ok"]
    assert has_rush(_catalog("OP18-119"), sham)
    assert sham.summoning_sick is False
    _clear_turn_duration_effects(st)
    assert not has_rush(_catalog("OP18-119"), sham)
    assert "rush" not in (sham.turn_keywords or [])


def test_up_to_one_only_the_chosen_shamrock():
    sick = _sham(iid="sick")
    ready = _sham(iid="ready", summoning_sick=False)
    st = _state(_cerb(), sick, ready)
    _pay(st)
    pending = st.pending_choice
    assert apply_action(
        st, 0, {"type": "select_choice", "target_iid": _option_token(pending, "blockerless")}, _catalog
    )["ok"]
    assert set(st.pending_choice.options) == {"sick", "ready"}
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "ready"}, _catalog)["ok"]
    assert has_blockerless(_catalog("OP18-119"), ready)
    assert not has_blockerless(_catalog("OP18-119"), sick)


def test_ai_skips_when_no_shamrock():
    st = _state(_cerb(), CardInst(iid="other", card_id="OTHER"))
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "cerb"}, _catalog)["ok"]
    choice = pick_ai_action(st, 0, _catalog)
    assert choice is not None
    assert choice["type"] == "skip_choice"


def test_ai_rush_on_summoning_sick_shamrock():
    sham = _sham(summoning_sick=True)
    ready = _sham(iid="ready", summoning_sick=False)
    st = _state(_cerb(), sham, ready)
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "cerb"}, _catalog)["ok"]
    pay = pick_ai_action(st, 0, _catalog)
    assert pay == {"type": "select_choice", "target_iid": "cerb"}
    assert apply_action(st, 0, pay, _catalog)["ok"]
    keyword = pick_ai_action(st, 0, _catalog)
    assert keyword is not None and keyword["type"] == "select_choice"
    assert st.pending_choice.option_branches[keyword["target_iid"]][0]["keyword"] == "rush"
    assert apply_action(st, 0, keyword, _catalog)["ok"]
    target = pick_ai_action(st, 0, _catalog)
    assert target == {"type": "select_choice", "target_iid": "sham"}
    assert apply_action(st, 0, target, _catalog)["ok"]
    assert has_rush(_catalog("OP18-119"), sham)
    assert not has_rush(_catalog("OP18-119"), ready)


def test_ai_unblockable_when_a_blocker_can_stop_the_swing():
    sham = _sham(summoning_sick=False)
    blocker = CardInst(iid="blk", card_id="BLK", rested=False, keywords=["blocker"])
    st = _state(_cerb(), sham, opp=[blocker])
    _pay(st)
    keyword = pick_ai_action(st, 0, _catalog)
    assert keyword is not None
    assert st.pending_choice.option_branches[keyword["target_iid"]][0]["keyword"] == "blockerless"


def test_ai_banish_when_shamrock_can_attack_and_nothing_blocks():
    sham = _sham(summoning_sick=False)
    st = _state(_cerb(), sham)
    _pay(st)
    keyword = pick_ai_action(st, 0, _catalog)
    assert keyword is not None
    assert st.pending_choice.option_branches[keyword["target_iid"]][0]["keyword"] == "banish"
