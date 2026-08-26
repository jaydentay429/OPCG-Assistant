"""Batch-G effect encoding / runtime fixes (Aug 2026)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import has_rush_character, live_keywords  # noqa: E402
from battle.engine import effective_character_cost, inst_power  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _mk_state(*, trash=0, turn_seat=0):
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP14-079",
        deck=["A"] * 20,
        hand=[],
        life=["L"] * 4,
        trash=["T"] * trash,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="L2",
        deck=["B"] * 20,
        hand=[],
        life=["R"] * 5,
    )
    return MatchState(
        room_code="G",
        status="playing",
        phase="main",
        turn_seat=turn_seat,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def test_op14_099_main_is_search_only():
    reload_effect_library(force=True)
    ops = get_card_entry("OP14-099")["abilities"]
    main = next(a for a in ops if a["timing"] == "on_play")
    assert [o["op"] for o in main["ops"]] == ["search_deck"]
    assert main["ops"][0].get("trash_rest") is True
    assert "不服氣" in (main["ops"][0].get("exclude_name") or "")
    trig = next(a for a in ops if a["timing"] == "trigger")
    assert trig["ops"][0]["op"] == "activate_timing"


def test_op14_091_requires_bw_and_cost():
    reload_effect_library(force=True)
    op = get_card_entry("OP14-091")["abilities"][0]["ops"][0]
    assert op["op"] == "play_from_hand"
    assert op.get("cost_lte") == 5
    assert "B・W" in (op.get("trait_contains") or "") or "Baroque" in (op.get("trait_contains") or "")
    assert op.get("from_zone") == "hand_or_trash"


def test_op14_093_cost_lte_8():
    reload_effect_library(force=True)
    op = get_card_entry("OP14-093")["abilities"][0]["ops"][0]
    assert op.get("cost_lte") == 8
    assert op.get("card_type") == "character"


def test_op05_094_single_skip_untap_cost_eq():
    reload_effect_library(force=True)
    ops = get_card_entry("OP05-094")["abilities"][0]["ops"]
    assert [o["op"] for o in ops] == ["reduce_cost", "skip_untap"]
    assert ops[1].get("cost_eq") == 0
    assert ops[1].get("target_kind") == "opponent_character"
    assert ops[0].get("duration") == "turn"


def test_op14_090_split_rush_and_rest():
    reload_effect_library(force=True)
    entry = get_card_entry("OP14-090")
    yt = next(a for a in entry["abilities"] if a["timing"] == "your_turn")
    assert yt.get("require_field_char_cost_0_or_gte") == 8
    assert yt["ops"][0].get("keyword") == "rush_character"
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert on_play.get("require_field_char_cost_0_or_gte") is None
    assert on_play["ops"][0]["op"] == "rest_opponent_character"

    def cat(cid: str) -> dict:
        table = {
            "OP14-090": {
                "name": "Mr.1",
                "card_type": "CHARACTER",
                "cost": 5,
                "power": 6000,
                "traits_en": ["Baroque Works"],
                "effect": "若場上有費用0或8以上的角色卡時，這張角色卡在登場的回合即可攻擊角色卡。",
            },
            "OP14-079": {
                "name": "Crocodile",
                "card_type": "LEADER",
                "power": 5000,
                "traits_en": ["Baroque Works"],
            },
            "ZERO": {"name": "Z", "card_type": "CHARACTER", "cost": 0, "power": 1000},
            "L2": {"name": "L2", "card_type": "LEADER", "power": 5000},
        }
        return dict(table.get(cid) or {"name": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000})

    st = _mk_state()
    mr1 = CardInst(iid="m1", card_id="OP14-090", summoning_sick=True)
    st.players[0].characters.append(mr1)
    assert has_rush_character(cat("OP14-090"), mr1, state=st, owner_seat=0, catalog=cat) is False
    st.players[0].characters.append(CardInst(iid="z", card_id="ZERO"))
    assert has_rush_character(cat("OP14-090"), mr1, state=st, owner_seat=0, catalog=cat) is True
    keys = live_keywords(cat("OP14-090"), mr1, state=st, owner_seat=0, catalog=cat)
    assert "rush_character" in keys


def test_op14_086_board_cost_aura():
    reload_effect_library(force=True)

    def cat(cid: str) -> dict:
        table = {
            "OP14-086": {
                "name": "Sara",
                "card_type": "CHARACTER",
                "cost": 5,
                "power": 6000,
                "traits_en": ["Baroque Works"],
            },
            "BW": {
                "name": "Agent",
                "card_type": "CHARACTER",
                "cost": 3,
                "power": 4000,
                "traits_en": ["Baroque Works"],
            },
            "NAVY": {
                "name": "Navy",
                "card_type": "CHARACTER",
                "cost": 3,
                "power": 4000,
                "traits_en": ["Navy"],
            },
            "OP14-079": {
                "name": "Crocodile",
                "card_type": "LEADER",
                "power": 5000,
                "traits_en": ["Baroque Works"],
            },
            "L2": {"name": "L2", "card_type": "LEADER", "power": 5000},
        }
        return dict(table.get(cid) or {"name": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000})

    st = _mk_state(trash=7)
    sara = CardInst(iid="s", card_id="OP14-086")
    bw = CardInst(iid="b", card_id="BW")
    navy = CardInst(iid="n", card_id="NAVY")
    st.players[0].characters.extend([sara, bw, navy])
    assert effective_character_cost(st, 0, sara, cat) == 7
    assert effective_character_cost(st, 0, bw, cat) == 5
    assert effective_character_cost(st, 0, navy, cat) == 3
    assert inst_power(st, 0, "s", cat) == 7000


def test_op14_120_p1_aligned():
    reload_effect_library(force=True)
    e = get_card_entry("OP14-120-P1")
    on_play = next(a for a in e["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][0]["op"] == "deny_attack"
    assert on_play["ops"][1].get("require_opp_char_cost_0_or_gte") == 8
    on_ko = next(a for a in e["abilities"] if a["timing"] == "on_ko")
    assert on_ko["ops"][1].get("self_card") is True


def test_p057_single_skip_untap():
    reload_effect_library(force=True)
    ops = get_card_entry("P-057")["abilities"][0]["ops"]
    assert [o["op"] for o in ops] == ["skip_untap"]
    assert ops[0].get("count") == 2
    assert ops[0].get("cost_lte") == 4


def test_eb04_047_hand_or_trash_filters():
    reload_effect_library(force=True)
    op = get_card_entry("EB04-047")["abilities"][0]["ops"][1]
    assert op.get("from_zone") == "hand_or_trash"
    assert op.get("cost_lte") == 3
    assert "SWORD" in (op.get("trait_contains") or "")


def test_op07_032_and_op11_001_rush_character():
    reload_effect_library(force=True)
    yt = next(a for a in get_card_entry("OP07-032")["abilities"] if a["timing"] == "your_turn")
    assert yt["ops"][0].get("keyword") == "rush_character"
    on_play = next(a for a in get_card_entry("OP07-032")["abilities"] if a["timing"] == "on_play")
    assert on_play.get("require_leader_trait")
    assert on_play["ops"][0]["op"] == "rest_opponent_character"

    lead = next(
        a
        for a in get_card_entry("OP11-001")["abilities"]
        if a["timing"] == "your_turn" and a["ops"][0].get("op") == "grant_keyword"
    )
    assert lead["ops"][0].get("keyword") == "rush_character"
    assert lead["ops"][0].get("all") is True

    def cat(cid: str) -> dict:
        table = {
            "OP11-001": {
                "name": "Koby",
                "card_type": "LEADER",
                "power": 5000,
                "traits_en": ["Navy", "SWORD"],
            },
            "SW": {
                "name": "Sword",
                "card_type": "CHARACTER",
                "cost": 3,
                "power": 4000,
                "traits_en": ["SWORD"],
            },
            "NAVY": {
                "name": "Navy",
                "card_type": "CHARACTER",
                "cost": 3,
                "power": 4000,
                "traits_en": ["Navy"],
            },
            "L2": {"name": "L2", "card_type": "LEADER", "power": 5000},
        }
        return dict(table.get(cid) or {"name": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000})

    st = _mk_state()
    st.players[0].leader_card_id = "OP11-001"
    sw = CardInst(iid="sw", card_id="SW", summoning_sick=True)
    navy = CardInst(iid="nv", card_id="NAVY", summoning_sick=True)
    st.players[0].characters.extend([sw, navy])
    assert has_rush_character(cat("SW"), sw, state=st, owner_seat=0, catalog=cat) is True
    assert has_rush_character(cat("NAVY"), navy, state=st, owner_seat=0, catalog=cat) is False


def test_eb02_019_rush_not_gated_by_leader():
    reload_effect_library(force=True)
    yt = next(a for a in get_card_entry("EB02-019")["abilities"] if a["timing"] == "your_turn")
    assert yt.get("require_opp_chars_count_gte") == 2
    assert yt.get("require_leader_trait") is None
    on_play = next(a for a in get_card_entry("EB02-019")["abilities"] if a["timing"] == "on_play")
    assert on_play.get("require_leader_trait")
    assert on_play["ops"][0]["op"] == "rest_opponent_character"
