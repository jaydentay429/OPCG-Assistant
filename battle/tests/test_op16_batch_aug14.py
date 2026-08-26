"""Regression: OP16-094/082/097/079/095/087/099 + OP15-092 + replace slot + OP14-079."""

from __future__ import annotations

from battle.effects import apply_ops, has_blockerless, has_rush, live_keywords, parse_static_self_cost
from battle.engine import (
    _clear_turn_duration_effects,
    _effect_play_from_hand_token,
    apply_action,
    effective_character_cost,
    inst_power,
    legal_actions,
)
from battle.effect_library import get_abilities, reload_effect_library
from battle.state import CardInst, MatchState, PlayerState


def _cat(cid: str) -> dict:
    table = {
        "L_WANO": {
            "card_id": "L_WANO",
            "card_type": "LEADER",
            "name": "大和",
            "power": 5000,
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
            "colors": ["黑"],
        },
        "OP16-094": {
            "card_id": "OP16-094",
            "card_type": "CHARACTER",
            "cost": 5,
            "power": 6000,
            "name": "艾斯",
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
            "colors": ["黑"],
            "effect": "【啟動主要】【每回合1次】附加最多1張休息狀態的咚‼卡在1張自己擁有《和之國》特徵的領航卡或角色卡。",
        },
        "OP16-082": {
            "card_id": "OP16-082",
            "card_type": "CHARACTER",
            "cost": 2,
            "power": 3000,
            "name": "錦右衛門",
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
            "colors": ["黑"],
            "effect": "這張角色卡的費用+3。 【登場時】若自己的領航卡擁有《和之國》特徵時，從自己的卡組上面查看5張卡片，公開最多1張擁有《和之國》特徵的卡片，並加入手牌。之後，將其餘卡片放到廢棄區。",
        },
        "WANO6": {
            "card_id": "WANO6",
            "card_type": "CHARACTER",
            "cost": 6,
            "power": 6000,
            "name": "大和",
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
            "colors": ["黑"],
        },
        "C2": {
            "card_id": "C2",
            "card_type": "CHARACTER",
            "cost": 2,
            "power": 2000,
            "name": "雜魚",
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
            "colors": ["黑"],
        },
        "MOMO": {
            "card_id": "MOMO",
            "card_type": "CHARACTER",
            "cost": 5,
            "power": 5000,
            "name": "光月桃之助",
            "name_en": "Kozuki Momonosuke",
            "traits": ["和之國", "光月家"],
            "traits_en": ["Land of Wano", "Kouzuki Clan"],
            "colors": ["黑"],
        },
        "OP16-083": {
            "card_id": "OP16-083",
            "card_type": "CHARACTER",
            "cost": 9,
            "power": 9000,
            "name": "光月桃之助",
            "name_en": "Kozuki Momonosuke",
            "traits": ["和之國", "光月家"],
            "traits_en": ["Land of Wano", "Kouzuki Clan"],
            "colors": ["黑"],
        },
        "OP16-084": {
            "card_id": "OP16-084",
            "card_type": "CHARACTER",
            "cost": 5,
            "power": 5000,
            "name": "光月桃之助",
            "name_en": "Kozuki Momonosuke",
            "traits": ["和之國", "光月家"],
            "traits_en": ["Land of Wano", "Kouzuki Clan"],
            "colors": ["黑"],
            "effect": "【啟動主要】可將費用20以上的這張角色卡放置在廢棄區：若自己的場上有9張以上咚‼卡時，使最多1張自己廢棄區中費用9的「光月桃之助」登場。",
        },
        "OP16-086": {
            "card_id": "OP16-086",
            "card_type": "CHARACTER",
            "cost": 6,
            "power": 6000,
            "name": "大和",
            "name_en": "Yamato",
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
            "colors": ["黑"],
        },
        "OP16-087": {
            "card_id": "OP16-087",
            "card_type": "CHARACTER",
            "cost": 2,
            "power": 1000,
            "name": "忍",
            "name_en": "Shinobu",
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
            "colors": ["黑"],
            "effect": "【登場時】可將這張角色卡放置在廢棄區：若自己的領航卡擁有《和之國》特徵時，抽1張卡片，最多1張自己的「光月桃之助」，在這個回合，費用+20。",
        },
        "BLK_WANO": {
            "card_id": "BLK_WANO",
            "card_type": "CHARACTER",
            "cost": 4,
            "power": 5000,
            "name": "黑和",
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
            "colors": ["黑"],
            "colors_en": ["Black"],
        },
        "OP16-079": {
            "card_id": "OP16-079",
            "card_type": "LEADER",
            "name": "大和",
            "power": 5000,
            "traits": ["和之國"],
            "traits_en": ["Land of Wano"],
            "colors": ["黑"],
            "effect": "自己廢棄區中擁有《和之國》特徵的角色卡登場時，該張角色卡，在這個回合，獲得【速攻】。",
        },
        "OP15-092": {
            "card_id": "OP15-092",
            "card_type": "CHARACTER",
            "cost": 8,
            "power": 8000,
            "name": "魯夫",
            "traits": ["草帽一行人"],
            "traits_en": ["Straw Hat Crew"],
            "colors": ["紫"],
            "effect": "依照自己廢棄區中的卡片張數，適用下列效果。 ・若有10張以上時，這張角色卡原本的力量值變更成9000、費用+10。 ・若有20張以上時，在對方的回合，自己的領航卡原本的力量值變更成7000。 ・若有30張以上時，這張角色卡的力量值+1000。",
        },
        "BW": {
            "card_id": "BW",
            "card_type": "CHARACTER",
            "cost": 3,
            "power": 4000,
            "name": "Mr.5",
            "traits": ["B・W"],
            "traits_en": ["Baroque Works"],
            "colors": ["紫"],
        },
        "OPP": {
            "card_id": "OPP",
            "card_type": "CHARACTER",
            "cost": 5,
            "power": 6000,
            "name": "對手",
            "traits": ["海军"],
            "traits_en": ["Navy"],
            "colors": ["红"],
        },
        "OP14-079": {
            "card_id": "OP14-079",
            "card_type": "CHARACTER",
            "cost": 8,
            "power": 8000,
            "name": "克洛克達爾",
            "traits": ["B・W"],
            "traits_en": ["Baroque Works"],
            "colors": ["紫"],
        },
    }
    return dict(table.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000, "colors": ["黑"]})


def _state(leader0="L_WANO", leader1="L_WANO") -> MatchState:
    st = MatchState(
        room_code="t",
        players=[
            PlayerState(
                seat=0,
                user_id="a",
                username="A",
                is_ai=False,
                leader_card_id=leader0,
                life=["L"] * 5,
                deck=["D"] * 30,
            ),
            PlayerState(
                seat=1,
                user_id="b",
                username="B",
                is_ai=False,
                leader_card_id=leader1,
                life=["M"] * 5,
                deck=["D"] * 30,
            ),
        ],
    )
    st.status = "playing"
    st.phase = "main"
    st.turn_seat = 0
    return st


def test_attach_rested_don_from_cost_area_not_deck():
    st = _state()
    p = st.players[0]
    p.don_rested = 3
    p.don_given = 5
    p.don_active = 2
    ch = CardInst(iid="c1", card_id="OP16-094")
    p.characters.append(ch)
    before_given = p.don_given
    apply_ops(
        st,
        0,
        [
            {
                "op": "attach_don",
                "count": 1,
                "as_rested": True,
                "from_rested": True,
                "target_kind": "own_leader_or_character",
                "trait_contains": "Land of Wano",
                "target_iid": "c1",
                "optional": True,
            }
        ],
        _cat,
    )
    assert p.don_rested == 2
    assert p.don_given == before_given
    assert ch.don_attached == 1


def test_static_self_cost_op16_082():
    reload_effect_library(force=True)
    parsed = parse_static_self_cost(_cat("OP16-082"))
    assert any(a.get("timing") == "your_turn" for a in parsed)
    assert any(a.get("timing") == "opponent_turn" for a in parsed)
    st = _state()
    ch = CardInst(iid="k1", card_id="OP16-082")
    st.players[0].characters.append(ch)
    # Override + template should yield printed 2 + 3 = 5
    assert effective_character_cost(st, 0, ch, _cat) == 5
    st.turn_seat = 1
    assert effective_character_cost(st, 0, ch, _cat) == 5


def test_add_from_trash_offers_choice_then_play_from_hand():
    st = _state()
    p = st.players[0]
    p.trash = ["WANO6", "C2"]
    p.hand = ["C2"]
    apply_ops(
        st,
        0,
        [
            {
                "op": "add_from_trash",
                "count": 1,
                "optional": True,
                "card_type": "character",
                "trait_contains": "Land of Wano",
                "cost_lte": 6,
            },
            {"op": "play_from_hand", "count": 1, "card_type": "character", "optional": True, "cost_lte": 2, "from_zone": "hand"},
        ],
        _cat,
    )
    assert st.pending_choice is not None
    assert st.pending_choice.purpose in {"add_hand", "play"} or "trash:" in (st.pending_choice.options[0] if st.pending_choice.options else "")
    assert all(str(o).startswith("trash:") for o in st.pending_choice.options)
    # Pick WANO6
    tok = next(o for o in st.pending_choice.options if o.endswith(":WANO6"))
    r = apply_action(st, 0, {"type": "select_choice", "target_iid": tok}, _cat, None)
    assert r.get("ok")
    assert "WANO6" in p.hand
    assert st.pending_choice is not None  # play_from_hand next
    assert any(str(o).startswith("hand:") for o in st.pending_choice.options)


def test_play_from_trash_grants_rush_via_leader_watcher():
    reload_effect_library(force=True)
    st = _state(leader0="OP16-079")
    p = st.players[0]
    p.trash = ["WANO6"]
    played = _effect_play_from_hand_token(st, 0, "trash:0:WANO6", _cat)
    assert played.get("ok")
    inst = p.characters[-1]
    info = _cat(inst.card_id)
    assert "rush" in live_keywords(info, inst) or has_rush(info, inst)
    assert "rush" in (inst.turn_keywords or [])


def test_blockerless_is_turn_not_permanent():
    st = _state()
    p = st.players[0]
    ch = CardInst(iid="b1", card_id="BLK_WANO")
    p.characters.append(ch)
    apply_ops(
        st,
        0,
        [
            {
                "op": "grant_keyword",
                "keyword": "blockerless",
                "target_kind": "own_character",
                "trait_contains": "Land of Wano",
                "duration": "turn",
                "optional": True,
                "count": 1,
                "color": "black",
                "target_iid": "b1",
            }
        ],
        _cat,
    )
    assert "blockerless" in (ch.turn_keywords or [])
    assert "blockerless" not in (ch.keywords or [])
    assert has_blockerless(_cat("BLK_WANO"), ch)
    _clear_turn_duration_effects(st)
    assert "blockerless" not in (ch.turn_keywords or [])
    assert not has_blockerless(_cat("BLK_WANO"), ch)


def test_grant_cost_momonosuke_offers_choice():
    st = _state()
    p = st.players[0]
    momo = CardInst(iid="m1", card_id="MOMO")
    other = CardInst(iid="c1", card_id="C2")
    p.characters.extend([momo, other])
    apply_ops(
        st,
        0,
        [
            {
                "op": "grant_cost",
                "amount": 20,
                "target_kind": "own_character",
                "name_contains": "光月桃之助|桃之助|Momonosuke",
                "optional": True,
            }
        ],
        _cat,
    )
    assert st.pending_choice is not None
    assert "m1" in st.pending_choice.options
    assert "c1" not in st.pending_choice.options
    apply_action(st, 0, {"type": "select_choice", "target_iid": "m1"}, _cat, None)
    assert momo.cost_mod == 20


def test_replace_keeps_slot_index():
    st = _state()
    p = st.players[0]
    for i in range(5):
        p.characters.append(CardInst(iid=f"x{i}", card_id="C2"))
    p.hand = ["WANO6"]
    p.don_active = 10
    target = p.characters[2].iid
    before_ids = [c.card_id for c in p.characters]
    r = apply_action(
        st,
        0,
        {"type": "play_card", "hand_index": 0, "replace_iid": target},
        _cat,
        None,
    )
    assert r.get("ok")
    assert len(p.characters) == 5
    assert p.characters[2].card_id == "WANO6"
    assert before_ids[2] == "C2"


def test_op15_092_continuous_trash_gates():
    reload_effect_library(force=True)
    st = _state()
    p = st.players[0]
    ch = CardInst(iid="luffy", card_id="OP15-092")
    p.characters.append(ch)
    p.trash = [f"T{i}" for i in range(10)]
    assert effective_character_cost(st, 0, ch, _cat) == 18  # 8+10
    assert inst_power(st, 0, "luffy", _cat) == 9000
    p.trash = [f"T{i}" for i in range(20)]
    st.turn_seat = 1  # opponent turn
    assert inst_power(st, 0, "leader", _cat) == 7000
    p.trash = [f"T{i}" for i in range(30)]
    assert inst_power(st, 0, "luffy", _cat) == 10000  # 9000+1000


def test_op14_079_ko_then_reduce_cost_choice():
    st = _state(leader0="L_WANO", leader1="L_WANO")
    p = st.players[0]
    foe = st.players[1]
    croco = CardInst(iid="cr", card_id="OP14-079")
    bw = CardInst(iid="bw", card_id="BW")
    p.characters.extend([croco, bw])
    opp = CardInst(iid="o1", card_id="OPP")
    foe.characters.append(opp)
    apply_ops(
        st,
        0,
        [
            {"op": "ko", "target_kind": "own_character", "optional": True, "as_cost": True, "trait_contains": "B・W"},
            {"op": "reduce_cost", "amount": -10, "count": 1, "target_kind": "opponent_character", "optional": True},
        ],
        _cat,
    )
    assert st.pending_choice is not None
    # Prefer BW over Croco if both match — both have B・W; pick bw
    assert "bw" in st.pending_choice.options
    apply_action(st, 0, {"type": "select_choice", "target_iid": "bw"}, _cat, None)
    assert all(c.iid != "bw" for c in p.characters)
    assert st.pending_choice is not None  # reduce cost
    assert "o1" in st.pending_choice.options
    apply_action(st, 0, {"type": "select_choice", "target_iid": "o1"}, _cat, None)
    assert opp.cost_mod == -10


def test_op16_087_grant_cost_keeps_name_filter():
    reload_effect_library(force=True)
    ab = get_abilities("OP16-087", "on_play")[0]
    trash = ab["ops"][0]
    assert trash.get("optional") is True
    grant = next(o for o in ab["ops"] if o.get("op") == "grant_cost")
    assert "Momonosuke" in str(grant.get("name_contains") or "")
    assert grant.get("trait_contains") in (None, "")


def test_op16_087_optional_trash_self_offers_choice():
    reload_effect_library(force=True)
    st = _state(leader0="L_WANO")
    p = st.players[0]
    shinobu = CardInst(iid="s87", card_id="OP16-087")
    p.characters.append(shinobu)
    pending = __import__("battle.effect_library", fromlist=["resolve_ability"]).resolve_ability(
        st, 0, "OP16-087", "s87", "on_play", _cat("OP16-087"), None, allow_llm=False, catalog=_cat
    )
    assert pending and pending.ops
    from battle.engine import _run_pending_effect

    _run_pending_effect(st, pending, _cat)
    assert st.pending_choice is not None
    assert st.pending_choice.optional is True
    assert st.pending_choice.options == ["s87"]
    assert "OP16-087" in p.characters[0].card_id or any(c.iid == "s87" for c in p.characters)


def test_op16_084_activate_requires_effective_cost_20_and_don_9():
    reload_effect_library(force=True)
    st = _state(leader0="L_WANO")
    p = st.players[0]
    momo = CardInst(iid="m084", card_id="OP16-084")
    p.characters.append(momo)
    p.don_active = 10
    p.don_given = 10
    assert not any(
        a.get("type") == "activate_main" and a.get("source_iid") == "m084" for a in legal_actions(st, 0, _cat)
    )
    momo.cost_mod = 15
    assert effective_character_cost(st, 0, momo, _cat) == 20
    assert any(
        a.get("type") == "activate_main" and a.get("source_iid") == "m084" for a in legal_actions(st, 0, _cat)
    )
    p.don_active = 8
    p.don_given = 8
    assert not any(
        a.get("type") == "activate_main" and a.get("source_iid") == "m084" for a in legal_actions(st, 0, _cat)
    )


def test_op16_084_play_from_trash_only_cost9_momonosuke():
    reload_effect_library(force=True)
    st = _state()
    p = st.players[0]
    p.trash = ["OP16-083", "OP16-086", "MOMO"]
    ab = get_abilities("OP16-084", "activate_main")[0]
    play = next(o for o in ab["ops"] if o.get("op") == "play_from_hand")
    apply_ops(st, 0, [play], _cat)
    assert st.pending_choice is not None
    opts = st.pending_choice.options
    assert len(opts) == 1
    assert opts[0].endswith(":OP16-083")
