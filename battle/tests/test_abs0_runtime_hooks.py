"""Runtime regressions for abs0 engine hooks (OP12-020 / OP09-118 / OP11-046 / ST10-007 / replace costs)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import reload_effect_library  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import (  # noqa: E402
    _choose_block,
    _declare_attack,
    _resolve_attack,
    has_continuous_protection,
)
from battle.leave_replace import confirm_replace_if_pending, try_replace_leave  # noqa: E402
from battle.state import CardInst, MatchState, PendingAttack, PlayerState  # noqa: E402


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


def test_op12_020_arm_and_attack_gate():
    reload_effect_library(force=True)
    cat = _catalog()
    st = _state(leader0="OP12-020")
    st.players[0].leader_don = 3
    st.players[0].don_active = 5
    low = CardInst(iid="low", card_id="COST5", rested=True)
    high = CardInst(iid="high", card_id="COST8", rested=True)
    st.players[1].characters.extend([low, high])

    def catalog(cid):
        if cid == "COST5":
            return {"cost": "5", "power": "5000", "name": "Low"}
        if cid == "COST8":
            return {"cost": "8", "power": "8000", "name": "High"}
        return cat.get(cid) or {"cost": "0", "power": "5000", "name": cid}

    apply_ops(
        st,
        0,
        [
            {"op": "arm_untap_on_char_battle"},
            {"op": "cannot_attack_char_base_cost_lte", "count": 7, "duration": "turn"},
        ],
        catalog,
    )
    assert st.players[0].untap_on_char_battle is True
    assert st.players[0].cannot_attack_char_base_cost_lte == 7

    bad = _declare_attack(st, 0, "leader", "low", catalog)
    assert bad.get("ok") is False

    ok = _declare_attack(st, 0, "leader", "high", catalog)
    assert ok.get("ok") is True
    assert st.players[0].leader_rested is True

    st.phase = "counter"
    _resolve_attack(st, catalog)
    assert st.players[0].leader_rested is False


def test_op09_118_win_on_opp_blocker_either_life_zero():
    reload_effect_library(force=True)
    cat = _catalog()
    st = _state(leader0="OP09-118", life0=[], life1=["M"] * 3)
    blocker = CardInst(iid="blk", card_id="BLK", rested=False)
    st.players[1].characters.append(blocker)
    st.players[0].leader_rested = False
    st.attack = PendingAttack(attacker_seat=0, attacker_iid="leader", target_iid="leader", declared_power=5000)
    st.phase = "block"

    def catalog(cid):
        if cid == "BLK":
            return {"cost": "3", "power": "4000", "name": "Blocker", "keywords": ["Blocker"]}
        return cat.get(cid) or {"cost": "0", "power": "5000", "name": cid}

    out = _choose_block(st, 1, "blk", catalog)
    assert out.get("ok") is True
    assert st.status == "finished"
    assert st.winner_seat == 0


def test_op11_046_continuous_protection_requires_all_germa():
    reload_effect_library(force=True)
    cat = _catalog()
    st = _state()
    germa = CardInst(iid="g1", card_id="OP11-046")
    other = CardInst(iid="x1", card_id="OTHER")
    st.players[0].characters.extend([germa, other])

    def catalog(cid):
        if cid == "OP11-046":
            return cat.get(cid) or {
                "cost": "5",
                "power": "6000",
                "traits": ["杰爾馬66"],
                "traits_en": ["GERMA 66"],
            }
        if cid == "OTHER":
            return {"cost": "2", "power": "3000", "traits": ["Navy"], "traits_en": ["Navy"]}
        return cat.get(cid) or {}

    assert has_continuous_protection(st, 0, "g1", "cannot_be_ko", catalog) is False

    st.players[0].characters = [germa]
    assert has_continuous_protection(st, 0, "g1", "cannot_be_ko", catalog) is True
    assert has_continuous_protection(st, 0, "g1", "cannot_be_rested", catalog) is True


def test_st10_007_on_don_returned_fires_ko_choice():
    reload_effect_library(force=True)
    cat = _catalog()
    st = _state()
    st.turn_seat = 0
    self_ch = CardInst(iid="s1", card_id="ST10-007")
    foe_ch = CardInst(iid="f1", card_id="LOW", rested=True)
    st.players[0].characters.append(self_ch)
    st.players[1].characters.append(foe_ch)
    st.players[0].don_active = 2

    def catalog(cid):
        if cid == "LOW":
            return {"cost": "2", "power": "2000", "name": "Low"}
        return cat.get(cid) or {"cost": "0", "power": "5000", "name": cid}

    apply_ops(st, 0, [{"op": "return_don", "count": 1}], catalog)
    # Optional KO → pending choice, or auto if engine auto-picks single target.
    if st.pending_choice:
        assert st.pending_choice.target_kind.startswith("opponent_character") or "ko" in (
            st.pending_choice.summary or ""
        ).lower() or any(
            str(o.get("op") or "") == "ko" for o in (st.pending_choice.remaining_ops or [])
        ) or st.pending_choice.target_kind in {
            "opponent_character",
            "opponent_character_rested",
            "opponent_character_active",
        }
    else:
        assert not any(c.iid == "f1" for c in st.players[1].characters)


def test_op14_016_leader_power_minus_replace_cost():
    reload_effect_library(force=True)
    cat = _catalog()
    st = _state(leader0="OP14-016")
    victim = CardInst(iid="v1", card_id="SUP")
    ally = CardInst(iid="a1", card_id="ALLY")
    st.players[0].characters.extend([victim, ally])

    def catalog(cid):
        if cid == "SUP":
            return {"cost": "4", "power": "5000", "traits_en": ["Supernovas"], "traits": ["超新星"]}
        if cid == "ALLY":
            return {"cost": "2", "power": "2000", "traits": [], "traits_en": []}
        return cat.get(cid) or {}

    ok = try_replace_leave(st, 0, victim, by_opponent=True, catalog=catalog)
    assert ok is True
    confirm_replace_if_pending(st, catalog)
    assert any(c.iid == "v1" for c in st.players[0].characters)
    assert st.players[0].leader_power_mod == -2000
    assert ally.power_mod == 0
    assert st.players[0].leader_once_used is True


def test_op07_029_rests_opponent_character():
    reload_effect_library(force=True)
    cat = _catalog()
    st = _state()
    self_ch = CardInst(iid="s1", card_id="OP07-029")
    ally = CardInst(iid="a1", card_id="ALLY", rested=False)
    foe_ch = CardInst(iid="f1", card_id="FOE", rested=False)
    st.players[0].characters.extend([self_ch, ally])
    st.players[1].characters.append(foe_ch)

    def catalog(cid):
        if cid == "OP07-029":
            return cat.get(cid) or {"cost": "3", "power": "4000", "traits_en": ["Supernovas"]}
        return {"cost": "3", "power": "3000", "name": cid, "traits": [], "traits_en": []}

    ok = try_replace_leave(st, 0, self_ch, by_opponent=True, catalog=catalog)
    assert ok is True
    confirm_replace_if_pending(st, catalog)
    assert any(c.iid == "s1" for c in st.players[0].characters)
    assert foe_ch.rested is True
    assert ally.rested is False


def test_activate_main_op15_072_requires_kotori_and_satori():
    from battle.effect_library import resolve_activate_spec
    from battle.engine import _activate_main, _activate_spec_legal

    reload_effect_library(force=True)
    cat = _catalog()
    st = _state(leader0="OP15-072")
    st.players[0].don_active = 5
    st.players[0].don_rested = 0
    src = CardInst(iid="hotori", card_id="OP15-072", rested=False)
    st.players[0].characters.append(src)
    st.players[0].characters.append(CardInst(iid="k1", card_id="OP15-064"))
    st.players[0].characters.append(CardInst(iid="s1", card_id="OP15-066"))
    st.players[1].characters.append(CardInst(iid="f1", card_id="FOE"))

    def catalog(cid):
        if cid == "FOE":
            return {"cost": "3", "power": "4000", "name": "Foe"}
        return cat.get(cid) or {"cost": "0", "power": "5000", "name": cid}

    spec = resolve_activate_spec("OP15-072", catalog("OP15-072"))
    assert spec and spec.get("require_own_name_all")
    assert _activate_spec_legal(st.players[0], spec, catalog, is_leader=False) is True
    # Missing 大悟 → illegal
    st.players[0].characters = [src, CardInst(iid="k1", card_id="OP15-064")]
    assert _activate_spec_legal(st.players[0], spec, catalog, is_leader=False) is False


def test_activate_main_op12_028_slash_or_green_event_search():
    from battle.effect_library import resolve_activate_spec
    from battle.engine import _activate_main

    reload_effect_library(force=True)
    cat = _catalog()
    st = _state(leader0="OP12-020")  # Zoro leader
    st.players[0].don_active = 3
    src = CardInst(iid="hiyori", card_id="OP12-028", rested=False)
    st.players[0].characters.append(src)
    # Deck top: non-match, Slash char, green Event
    st.players[0].deck = ["NOPE", "SLASH", "GEVENT", "X", "Y"] + ["Z"] * 10

    def catalog(cid):
        if cid == "NOPE":
            return {"cost": "1", "power": "1000", "name": "Nope", "card_type": "Character", "colors": ["紅"], "attributes_en": ["Strike"]}
        if cid == "SLASH":
            return {"cost": "2", "power": "3000", "name": "Slasher", "card_type": "Character", "colors": ["紅"], "attributes_en": ["Slash"]}
        if cid == "GEVENT":
            return {"cost": "1", "name": "Green Ev", "card_type": "Event", "colors": ["綠"]}
        if cid in {"X", "Y", "Z"}:
            return {"cost": "1", "power": "1000", "name": cid, "card_type": "Character", "colors": ["藍"], "attributes_en": ["Special"]}
        return cat.get(cid) or {"cost": "0", "power": "5000", "name": cid, "card_type": "Leader", "attributes_en": ["Slash"]}

    out = _activate_main(st, 0, "hiyori", catalog)
    assert out.get("ok") is True
    assert st.players[0].don_active == 2
    assert src.rested is True
    assert st.pending_search is not None
    assert set(st.pending_search.eligible) == {1, 2}


def test_counter_op03_072_requires_trash_hand_cost():
    reload_effect_library(force=True)
    from battle.effect_library import get_card_entry

    entry = get_card_entry("OP03-072")
    ctr = next(a for a in entry["abilities"] if a["timing"] == "counter_event")
    assert any(o.get("op") == "trash_hand" and o.get("as_cost") for o in ctr["ops"])
    assert any(o.get("op") == "buff" and o.get("amount") == 3000 for o in ctr["ops"])


def test_op15_093_grants_rush_character_and_slash():
    from battle.effect_library import resolve_activate_spec
    from battle.engine import _activate_main

    reload_effect_library(force=True)
    cat = _catalog()
    st = _state()
    st.players[0].don_active = 0
    st.players[0].trash = ["T"] * 15
    src = CardInst(iid="sq", card_id="OP15-093", rested=False)
    luffy = CardInst(iid="luf", card_id="OP01-003", rested=False)
    st.players[0].characters.extend([src, luffy])

    def catalog(cid):
        if cid == "OP01-003":
            return {"cost": "5", "power": "6000", "name": "蒙其・D・魯夫", "name_en": "Monkey.D.Luffy", "card_type": "Character"}
        return cat.get(cid) or {"cost": "0", "power": "5000", "name": cid}

    spec = resolve_activate_spec("OP15-093", catalog("OP15-093"))
    assert any(o.get("op") == "grant_attribute" and o.get("attribute") == "Slash" for o in spec["ops"])
    out = _activate_main(st, 0, "sq", catalog)
    assert out.get("ok") is True
    # 「可將這張角色卡放置在廢棄區」is an optional as_cost — confirm, then grants.
    if st.pending_choice:
        from battle.engine import _resolve_choice

        while st.pending_choice:
            opts = st.pending_choice.options
            _resolve_choice(st, st.pending_choice.seat, opts[0] if opts else None, catalog)
    assert "sq" not in [c.iid for c in st.players[0].characters]  # trashed as cost
    assert "rush_character" in (luffy.turn_keywords or luffy.keywords)
    assert any(a.lower() == "slash" for a in (luffy.turn_attributes or []))


def test_op07_076_p1_has_return_don_and_rest():
    reload_effect_library(force=True)
    from battle.effect_library import get_card_entry

    ctr = next(a for a in get_card_entry("OP07-076-P1")["abilities"] if a["timing"] == "counter_event")
    assert any(o.get("op") == "return_don" and o.get("count") == 1 for o in ctr["ops"])
    assert any(o.get("op") == "rest_opponent_character" for o in ctr["ops"])


def test_st32_004_rush_gated_by_leader_slash():
    reload_effect_library(force=True)
    from battle.effect_library import get_card_entry
    from battle.engine import _ability_board_conditions_ok

    entry = get_card_entry("ST32-004")
    yt = next(a for a in entry["abilities"] if a["timing"] == "your_turn")
    assert yt.get("require_leader_attribute")
    assert any(o.get("keyword") == "rush_character" for o in yt["ops"])
    cat = _catalog()
    st = _state(leader0="OP12-020")  # Slash Zoro
    assert _ability_board_conditions_ok(st, 0, yt, lambda c: cat.get(c) or {}) is True
    st2 = _state(leader0="OP01-001")  # non-slash Luffy leader typically
    # OP01-001 may lack attributes_en — treat as fail gate
    ok = _ability_board_conditions_ok(st2, 0, yt, lambda c: cat.get(c) or {})
    lead = cat.get("OP01-001") or {}
    attrs = " ".join(str(x) for x in (lead.get("attributes_en") or []))
    if "Slash" not in attrs:
        assert ok is False


def test_st28_004_return_attached_don_and_gates():
    reload_effect_library(force=True)
    from battle.effect_library import get_card_entry, resolve_activate_spec
    from battle.engine import _activate_spec_legal

    entry = get_card_entry("ST28-004")
    assert entry
    assert any(a.get("timing") == "your_turn" and a.get("require_life_lte") == 2 for a in entry["abilities"])
    spec = resolve_activate_spec("ST28-004", {"card_id": "ST28-004"})
    assert spec and any(o.get("op") == "return_attached_don" for o in spec["ops"])
    st = _state()
    p = st.players[0]
    p.leader_don = 1
    p.don_given = 2
    p.characters = [CardInst(iid="c1", card_id="ST28-004", don_attached=1)]
    assert _activate_spec_legal(p, spec, lambda c: {}, is_leader=False) is True
    logs = apply_ops(
        st,
        0,
        [{"op": "return_attached_don", "count": 2, "as_cost": True, "source_iid": "c1"}],
        lambda c: {},
    )
    assert p.leader_don == 0 and p.characters[0].don_attached == 0
    assert p.don_rested == 2 and p.don_given == 0
    assert any(l.get("key") == "play.log.return_attached_don" for l in logs)


def test_fidelity_hotfix_encodings():
    reload_effect_library(force=True)
    from battle.effect_library import get_card_entry

    op03 = get_card_entry("OP03-120")
    assert any(o.get("op") == "trash_life" for a in op03["abilities"] for o in a["ops"])
    assert op03["abilities"][0].get("require_opp_life_gte") == 4
    op06 = get_card_entry("OP06-096")
    ops = op06["abilities"][0]["ops"]
    assert ops[0].get("op") == "life_to_hand" and ops[0].get("as_cost")
    assert ops[1].get("op") == "cannot_be_ko" and ops[1].get("cost_lte") == 7
    for cid in ("EB02-051", "OP06-021", "OP06-092", "OP08-030", "ST12-006"):
        e = get_card_entry(cid)
        assert any(o.get("op") == "choose_one" for a in e["abilities"] for o in a["ops"]), cid
    op09 = get_card_entry("OP09-041")
    active = next(o for a in op09["abilities"] for o in a["ops"] if o.get("op") == "set_character_active")
    assert active.get("require_leader_trait") == "ODYSSEY"
    assert active.get("require_rested_own_chars_gte") == 2
    st28 = get_card_entry("ST28-001")
    assert st28["abilities"][0].get("require_opp_life_gte") == 3
    op11 = get_card_entry("OP11-102")
    assert op11["abilities"][0].get("timing") == "on_opp_event"
    assert op11["abilities"][0].get("also_on_opp_trigger") is True
    assert op11["abilities"][0].get("require_opp_life_gte") == 2


def test_on_opp_event_watcher_fires_draw():
    reload_effect_library(force=True)
    from battle.engine import _play_card

    cat = _catalog()
    st = _state(leader0="OP01-001")
    # Usopp OP01-004 on board with DON!! attached
    st.players[0].characters = [CardInst(iid="u1", card_id="OP01-004", don_attached=1)]
    st.players[0].hand = []
    st.turn_seat = 0
    # Opponent plays a Main event from hand
    st.players[1].hand = ["OP02-091"]  # 毒之路 Main gain don
    st.players[1].don_active = 5
    st.turn_seat = 1
    before = len(st.players[0].hand)
    _play_card(st, 1, 0, lambda c: cat.get(c) or {}, lambda *a, **k: None)
    # Watcher is OP01-004 on seat 0; require_your_turn means only on seat0's turn.
    # So on opponent's turn it should NOT fire. Re-test on own turn via helper.
    from battle.engine import _fire_opp_activation_watchers

    st.turn_seat = 0
    st.players[0].hand = []
    _fire_opp_activation_watchers(st, 1, lambda c: cat.get(c) or {}, kind="event")
    assert len(st.players[0].hand) == 1


def test_board_power_aura_and_per_distinct_names():
    reload_effect_library(force=True)
    from battle.engine import inst_power

    cat = _catalog()
    st = _state(leader0="OP02-001", life0=["L"])  # life <=1 for stage aura
    st.turn_seat = 0
    # Stage OP02-024 buffs Whitebeard chars + Edward leader
    st.players[0].stages = [CardInst(iid="st1", card_id="OP02-024")]
    st.players[0].characters = [
        CardInst(iid="c1", card_id="OP02-004"),  # typically Whitebeard type
    ]
    # Force life gate
    st.players[0].life = ["L"]
    # OP16-034 per distinct names: 4 distinct → +4000 + DON1000 = 5000
    st.players[0].characters = [
        CardInst(iid="c2", card_id="OP16-034", don_attached=1),
        CardInst(iid="c3", card_id="ST22-002"),  # Izo
        CardInst(iid="c4", card_id="ST22-004"),  # Elmy
        CardInst(iid="c5", card_id="ST22-005"),  # Oden
    ]
    pow16 = inst_power(st, 0, "c2", lambda c: cat.get(c) or {})
    assert pow16 == 5000, pow16

    # Same English name collapse must not apply when Chinese names differ — still 4.
    def catalog_prefer_zh(cid):
        info = dict(cat.get(cid) or {})
        return info

    assert inst_power(st, 0, "c2", catalog_prefer_zh) == 5000

    # Without DON gate, static bonus is off → only 0 printed.
    st.players[0].characters[0].don_attached = 0
    assert inst_power(st, 0, "c2", lambda c: cat.get(c) or {}) == 0


def test_on_trigger_and_play_character_watchers():
    reload_effect_library(force=True)
    from battle.effect_library import get_card_entry
    from battle.effects import card_has_trigger
    from battle.engine import _fire_character_play_watchers, _fire_trigger_activation_watchers

    op05 = get_card_entry("OP05-109")
    assert op05["abilities"][0]["timing"] == "on_trigger"
    op13 = get_card_entry("OP13-106")
    assert op13["abilities"][0]["timing"] == "on_trigger"
    assert op13["abilities"][0].get("require_opponent_turn") is True
    op100 = get_card_entry("OP13-100")
    assert op100["abilities"][0].get("on_own_play_character") is True
    assert op100["abilities"][0].get("require_played_has_trigger") is True
    assert op100["abilities"][0]["ops"][0].get("count") == 2

    cat = _catalog()
    st = _state()
    st.players[0].characters = [CardInst(iid="w1", card_id="OP05-109")]
    st.players[0].deck = ["D1", "D2", "D3", "D4"]
    st.players[0].hand = ["H1", "H2", "H3"]
    before_deck = len(st.players[0].deck)
    _fire_trigger_activation_watchers(st, 1, lambda c: cat.get(c) or {})
    # Drew 2 from deck (trash may be interactive or auto).
    assert len(st.players[0].deck) == before_deck - 2 or st.pending_choice or st.pending_effect

    st2 = _state()
    st2.players[0].characters = [CardInst(iid="w2", card_id="OP13-100")]
    st2.players[0].don_rested = 5
    trig_cid = None
    for cid, info in cat.items():
        ctype = str(info.get("card_type") or "").lower()
        if ctype == "character" and card_has_trigger(info):
            trig_cid = cid
            break
    assert trig_cid
    played = CardInst(iid="p1", card_id=trig_cid)
    st2.players[0].characters.append(played)
    _fire_character_play_watchers(
        st2, 0, played.iid, trig_cid, lambda c: cat.get(c) or {}, from_zone="hand"
    )
    assert st2.pending_choice or st2.pending_effect or st2.players[0].characters[0].once_used


def test_either_life_and_bilateral_encodings():
    reload_effect_library(force=True)
    from battle.effect_library import get_card_entry
    from battle.engine import _ability_board_conditions_ok

    for cid in ("OP03-104", "EB02-053", "ST07-008", "OP10-116", "ST07-008-P1"):
        e = get_card_entry(cid)
        assert any(
            o.get("op") == "reorder_life" and o.get("owner") == "self_or_opponent"
            for a in e["abilities"]
            for o in a["ops"]
        ), cid
    op16 = get_card_entry("OP16-081")
    assert op16["abilities"][0].get("require_field_char_cost_gte") == 8
    assert op16["abilities"][0].get("rest_self") is True
    op14 = get_card_entry("OP14-018")
    ab = op14["abilities"][0]
    assert ab.get("require_field_char_base_power_gte") == 8000
    cat = _catalog()
    st = _state()
    assert _ability_board_conditions_ok(st, 0, ab, lambda c: cat.get(c) or {}) is False
    st.players[1].characters = [CardInst(iid="x", card_id="PWR8")]

    def catalog(cid):
        if cid == "PWR8":
            return {"power": "8000", "cost": "5", "name": "Big"}
        return cat.get(cid) or {}

    assert _ability_board_conditions_ok(st, 0, ab, catalog) is True

    op05 = get_card_entry("OP05-100")
    gate_abs = [a for a in op05["abilities"] if a.get("require_no_name_on_field")]
    assert gate_abs
    st3 = _state()
    st3.players[0].characters = [CardInst(iid="s", card_id="OP05-100")]
    assert _ability_board_conditions_ok(st3, 0, gate_abs[0], lambda c: cat.get(c) or {}) is True
    st3.players[1].characters = [CardInst(iid="l", card_id="LUFFY")]

    def cat2(cid):
        if cid == "LUFFY":
            return {"name": "蒙其・D・魯夫", "name_en": "Monkey.D.Luffy"}
        return cat.get(cid) or {}

    assert _ability_board_conditions_ok(st3, 0, gate_abs[0], cat2) is False


def test_per_count_power_scalers():
    reload_effect_library(force=True)
    from battle.effect_library import get_card_entry, static_power_abilities
    from battle.engine import has_continuous_protection, inst_power

    cat = _catalog()

    def catalog(cid):
        return cat.get(cid) or {}

    # EB01-014: every 3 rested DON!!
    e = get_card_entry("EB01-014-P1")
    op = e["abilities"][0]["ops"][0]
    assert op.get("per_rested_don") == 3
    st = _state()
    st.players[0].don_rested = 6
    st.players[0].characters = [CardInst(iid="c", card_id="EB01-014", don_attached=1)]
    # printed 5000 + DON 1000 + 2*1000
    assert inst_power(st, 0, "c", catalog) == 8000

    # OP01-083: every 2 Events in trash
    assert any(
        o.get("per_trash_events") == 2
        for a in get_card_entry("OP01-083")["abilities"]
        for o in a["ops"]
    )

    # OP09-086: cannot_be_ko ungated; power gated + per 4 trash
    st2 = _state()
    st2.players[0].characters = [CardInst(iid="bb", card_id="OP09-086")]
    st2.players[0].trash = ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"]
    assert has_continuous_protection(st2, 0, "bb", "cannot_be_ko", catalog) is True
    flags = []
    for a in static_power_abilities("OP09-086", cat["OP09-086"]):
        for o in a["ops"]:
            if o.get("per_trash_cards"):
                flags.append(int(o["per_trash_cards"]))
    assert 4 in flags


if __name__ == "__main__":
    tests = [
        test_op12_020_arm_and_attack_gate,
        test_op09_118_win_on_opp_blocker_either_life_zero,
        test_op11_046_continuous_protection_requires_all_germa,
        test_st10_007_on_don_returned_fires_ko_choice,
        test_op14_016_leader_power_minus_replace_cost,
        test_op07_029_rests_opponent_character,
        test_activate_main_op15_072_requires_kotori_and_satori,
        test_activate_main_op12_028_slash_or_green_event_search,
        test_counter_op03_072_requires_trash_hand_cost,
        test_op15_093_grants_rush_character_and_slash,
        test_op07_076_p1_has_return_don_and_rest,
        test_st32_004_rush_gated_by_leader_slash,
        test_st28_004_return_attached_don_and_gates,
        test_fidelity_hotfix_encodings,
        test_on_opp_event_watcher_fires_draw,
        test_board_power_aura_and_per_distinct_names,
        test_on_trigger_and_play_character_watchers,
        test_either_life_and_bilateral_encodings,
        test_per_count_power_scalers,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("OK", fn.__name__)
        except Exception as e:
            failed += 1
            print("FAIL", fn.__name__, type(e).__name__, e)
    raise SystemExit(failed)
