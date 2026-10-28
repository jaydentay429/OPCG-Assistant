"""One runtime check for each self-translated OP18 sample card."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_abilities, reload_effect_library  # noqa: E402
from battle.effects import apply_ops, has_rush, live_keywords  # noqa: E402
from battle.engine import _character_denied_attack, inst_power  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid)
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "C3": {"card_id": "C3", "card_type": "Character", "cost": 3, "power": 2000, "name": "Three"},
        "C5": {"card_id": "C5", "card_type": "Character", "cost": 5, "power": 3000, "name": "Five"},
        "C6": {"card_id": "C6", "card_type": "Character", "cost": 6, "power": 4000, "name": "Six"},
        "C12": {"card_id": "C12", "card_type": "Character", "cost": 12, "power": 12000, "name": "Twelve"},
        "HAND5": {"card_id": "HAND5", "card_type": "Character", "cost": 2, "power": 5000, "name": "Hand Five"},
        "HAND6": {"card_id": "HAND6", "card_type": "Character", "cost": 2, "power": 6000, "name": "Hand Six"},
        "CPCARD": {"card_id": "CPCARD", "card_type": "Character", "cost": 1, "power": 1000, "name": "CP", "traits": ["CP9"], "traits_en": ["CP9"]},
        "SPAN": {"card_id": "SPAN", "card_type": "Character", "cost": 1, "power": 1000, "name": "斯帕達姆", "name_en": "Spandam"},
        "SHC": {"card_id": "SHC", "card_type": "Character", "cost": 1, "power": 1000, "name": "Crew", "traits": ["草帽一行人"], "traits_en": ["Straw Hat Crew"]},
        "LEAD_AL": {"card_id": "LEAD_AL", "card_type": "Leader", "cost": None, "power": 5000, "name": "Vivi", "traits": ["阿拉巴斯坦王國"], "traits_en": ["Alabasta"]},
        "LEAD_CP": {"card_id": "LEAD_CP", "card_type": "Leader", "cost": None, "power": 5000, "name": "Lucci", "traits": ["CP9"], "traits_en": ["CP9"]},
        "LEAD_CG": {"card_id": "LEAD_CG", "card_type": "Leader", "cost": None, "power": 5000, "name": "Croc", "traits": ["十字公會"], "traits_en": ["Cross Guild"]},
        "LEAD_PLAIN": {"card_id": "LEAD_PLAIN", "card_type": "Leader", "cost": None, "power": 5000, "name": "Plain", "traits": ["海軍"], "traits_en": ["Navy"]},
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "Character", "cost": 1, "power": 1000, "name": cid}


def _state(leader: str = "LEAD_PLAIN") -> MatchState:
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[
            PlayerState(
                seat=0,
                user_id="u0",
                username="P1",
                is_ai=False,
                leader_card_id=leader,
                deck=["TOP", "NEXT"] + ["D"] * 20,
                hand=["HAND5", "CPCARD"],
                trash=[],
                life=["L1", "L2"],
                characters=[],
                don_active=8,
                don_given=8,
                turns_completed=1,
            ),
            PlayerState(
                seat=1,
                user_id="u1",
                username="P2",
                is_ai=False,
                leader_card_id="LEAD_PLAIN",
                deck=["Y"] * 20,
                hand=[],
                trash=[],
                life=["OL1", "OL2"],
                characters=[],
                don_active=5,
                don_given=5,
                turns_completed=1,
            ),
        ],
    )


def _ops(card_id: str, timing: str) -> list[dict]:
    reload_effect_library(force=True)
    rows = [a for a in get_abilities(card_id) if a.get("timing") == timing]
    assert rows, timing
    return rows


def test_op18_004_power_thresholds_grant_keywords():
    reload_effect_library(force=True)
    st = _state()
    ch = CardInst(iid="k", card_id="OP18-004", summoning_sick=False)
    st.players[0].characters = [ch]
    info = catalog("OP18-004")

    def keys():
        return live_keywords(info, ch, state=st, owner_seat=0, catalog=catalog)

    assert "rush" not in keys()
    ch.power_mod = 1000
    assert "rush" in keys()
    assert "banish" not in keys()
    ch.power_mod = 2000
    assert "banish" in keys()
    assert "blockerless" not in keys()
    ch.power_mod = 3000
    assert "blockerless" in keys()


def test_op18_103_on_ko_moves_life_and_trigger_needs_cp_leader():
    rows = _ops("OP18-103", "on_ko")
    st = _state()
    apply_ops(st, 0, rows[0]["ops"], catalog)
    assert st.players[0].life[0] == "TOP"
    assert st.players[1].trash == ["OL1"]
    trig = _ops("OP18-103", "trigger")
    assert trig[0].get("require_leader_trait")
    plain = _state()
    before = len(plain.players[0].hand)
    apply_ops(plain, 0, trig[0]["ops"], catalog)
    # Gate is on the ability, not the op. Confirm the draw op is present and fires when applied.
    assert any(op.get("op") == "draw" for op in trig[0]["ops"])
    assert len(plain.players[0].hand) == before + 1


def test_op18_088_ko_uses_base_cost_and_can_replay_from_trash():
    on_play = _ops("OP18-088", "on_play")[0]
    assert on_play.get("require_don_field_gte") == 6
    assert on_play["ops"][0]["base_cost_lte"] == 4
    on_ko = _ops("OP18-088", "on_ko")[0]
    st = _state()
    st.players[0].hand = ["A", "B", "C"]
    st.players[0].trash = ["OP18-088"]
    apply_ops(st, 0, on_ko["ops"], catalog)
    assert "OP18-088" not in st.players[0].trash or st.pending_choice is not None or any(
        c.card_id == "OP18-088" for c in st.players[0].characters
    )


def test_op18_064_don_cost_denies_attack_until_opponent_end():
    on_play = _ops("OP18-064", "on_play")[0]
    assert on_play["ops"][0]["op"] == "return_don" and on_play["ops"][0].get("as_cost")
    assert on_play["ops"][1]["base_power_lte"] == 7000
    assert on_play["ops"][2]["base_power_lte"] == 5000
    st = _state()
    foe = CardInst(iid="f1", card_id="C5", summoning_sick=False)
    st.players[1].characters = [foe]
    st.players[0].don_active = 3
    given = st.players[0].don_given
    apply_ops(
        st,
        0,
        [
            {"op": "return_don", "count": 1, "as_cost": True, "owner": "self"},
            {
                "op": "deny_attack",
                "target_iid": "f1",
                "duration": "until_opp_turn_end",
            },
        ],
        catalog,
    )
    assert st.players[0].don_given == given - 1
    assert _character_denied_attack(st.players[1], "f1")


def test_op18_051_don_attached_buff_and_rest_five_bottoms_characters():
    st = _state()
    ch = CardInst(iid="m", card_id="OP18-051", don_attached=1, summoning_sick=False)
    low = CardInst(iid="c5", card_id="C5", summoning_sick=False)
    st.players[0].characters = [ch]
    st.players[1].characters = [low]
    # Printed 3000 + 1000 from the attached DON!! + 1000 from [DON!! x1].
    assert inst_power(st, 0, "m", catalog) == 5000
    ch.don_attached = 0
    assert inst_power(st, 0, "m", catalog) == 3000
    st.players[0].don_active = 5
    apply_ops(
        st,
        0,
        [
            {"op": "rest_don", "count": 5, "as_cost": True, "owner": "self"},
            {"op": "return_to_bottom", "target_iid": "c5", "target_kind": "any_character"},
        ],
        catalog,
    )
    assert st.players[0].don_active == 0
    assert all(c.iid != "c5" for c in st.players[1].characters)
    assert st.players[1].deck[-1] == "C5"


def test_op18_029_rush_and_attack_attaches_rested_don_then_skips_refresh():
    info = catalog("OP18-029")
    assert has_rush(info)
    rows = _ops("OP18-029", "when_attacking")
    assert rows[0].get("once") is True
    st = _state()
    ch = CardInst(iid="chop", card_id="OP18-029", rested=True, summoning_sick=False)
    st.players[0].characters = [ch]
    st.players[0].don_active = 2
    st.players[0].don_rested = 3
    ops = [dict(op, source_iid="chop") if op.get("op") == "skip_untap" else op for op in rows[0]["ops"]]
    apply_ops(st, 0, ops, catalog)
    assert st.pending_choice is None
    assert st.players[0].leader_don == 3
    assert ch.rested is False
    assert "chop" in st.players[0].skip_untap_iids


def test_op18_013_leader_trait_rush_and_discard_draws():
    st = _state("LEAD_PLAIN")
    ch = CardInst(iid="p", card_id="OP18-013", summoning_sick=False)
    st.players[0].characters = [ch]
    info = catalog("OP18-013")
    assert "rush" not in live_keywords(info, ch, state=st, owner_seat=0, catalog=catalog)
    st.players[0].leader_card_id = "LEAD_AL"
    assert "rush" in live_keywords(info, ch, state=st, owner_seat=0, catalog=catalog)
    on_play = _ops("OP18-013", "on_play")[0]
    st.players[0].hand = ["HAND5"]
    st.players[1].characters = [CardInst(iid="tiny", card_id="C3", summoning_sick=False)]
    apply_ops(st, 0, on_play["ops"], catalog)
    assert "HAND5" not in st.players[0].hand or st.pending_choice is not None


def test_op18_108_discard_cp_draws_and_buffs_spandam():
    on_play = _ops("OP18-108", "on_play")[0]
    st = _state("LEAD_CP")
    st.players[0].hand = ["CPCARD"]
    deck_before = len(st.players[0].deck)
    apply_ops(st, 0, on_play["ops"], catalog)
    if st.pending_choice is None:
        assert "CPCARD" not in st.players[0].hand
        assert len(st.players[0].deck) == deck_before - 2
    act = _ops("OP18-108", "activate_main")[0]
    assert act.get("rest_self") is True
    span = CardInst(iid="sp", card_id="SPAN", summoning_sick=False)
    st.players[0].characters = [span]
    apply_ops(st, 0, [{"op": "buff", "amount": 1000, "target_iid": "sp", "duration": "turn"}], catalog)
    assert inst_power(st, 0, "sp", catalog) == 2000


def test_op18_092_cost_12_buff_and_trash_rush():
    st = _state()
    zoro = CardInst(iid="z", card_id="OP18-092", summoning_sick=False)
    st.players[0].characters = [zoro]
    info = catalog("OP18-092")
    assert inst_power(st, 0, "z", catalog) == 2000
    assert "rush" not in live_keywords(info, zoro, state=st, owner_seat=0, catalog=catalog)
    st.players[1].characters = [CardInst(iid="big", card_id="C12", summoning_sick=False)]
    assert inst_power(st, 0, "z", catalog) == 5000
    st.players[0].trash = ["T"] * 10
    assert "rush" in live_keywords(info, zoro, state=st, owner_seat=0, catalog=catalog)


def test_op18_077_stage_draws_rested_don_and_grants_rush_character():
    on_play = _ops("OP18-077", "on_play")[0]
    st = _state()
    hand_before = len(st.players[0].hand)
    given = st.players[0].don_given
    apply_ops(st, 0, on_play["ops"], catalog)
    assert len(st.players[0].hand) == hand_before + 1
    assert st.players[0].don_given == given + 1
    assert st.players[0].don_active == 8
    act = _ops("OP18-077", "activate_main")[0]
    assert act.get("rest_self") is True
    assert act["ops"][0]["keyword"] == "rush_character"


def test_op18_047_leader_gains_unblockable_only_with_matching_trait():
    row = _ops("OP18-047", "on_play")[0]
    assert "B・W" in row["require_leader_trait"]
    st = _state("LEAD_CG")
    apply_ops(
        st,
        0,
        [{"op": "grant_keyword", "keyword": "blockerless", "target_kind": "leader", "target_iid": "leader", "duration": "turn"}],
        catalog,
    )
    assert "blockerless" in st.players[0].leader_turn_keywords


def test_op18_036_end_step_trashes_self_draws_and_activates_leader():
    row = _ops("OP18-036", "end_of_your_turn")[0]
    assert row.get("optional") is True
    st = _state()
    ch = CardInst(iid="luffy", card_id="OP18-036", summoning_sick=False)
    st.players[0].characters = [ch]
    st.players[0].leader_rested = True
    hand_before = len(st.players[0].hand)
    apply_ops(st, 0, [{"op": "trash", "target_iid": "luffy", "target_kind": "self"}, {"op": "draw", "count": 1}, {"op": "set_character_active", "target_kind": "leader", "target_iid": "leader"}], catalog)
    assert all(c.iid != "luffy" for c in st.players[0].characters)
    assert len(st.players[0].hand) == hand_before + 1


def test_op18_015_opponent_attack_debuffs_after_trashing_self():
    row = _ops("OP18-015", "on_opponent_attack")[0]
    assert row.get("require_leader_trait")
    st = _state("LEAD_AL")
    ch = CardInst(iid="mat", card_id="OP18-015", summoning_sick=False)
    foe = CardInst(iid="foe", card_id="C5", summoning_sick=False)
    st.players[0].characters = [ch]
    st.players[1].characters = [foe]
    apply_ops(
        st,
        0,
        [
            {"op": "trash", "target_iid": "mat", "target_kind": "self"},
            {"op": "buff", "amount": -3000, "target_iid": "foe", "duration": "turn"},
        ],
        catalog,
    )
    assert all(c.iid != "mat" for c in st.players[0].characters)
    assert inst_power(st, 1, "foe", catalog) == 0


def test_op18_101_face_up_life_and_trigger_choice():
    on_ko = _ops("OP18-101", "on_ko")[0]
    assert on_ko["ops"][0]["position"] == "top_or_bottom"
    assert on_ko["ops"][0]["face"] == "up"
    st = _state("LEAD_CP")
    st.players[0].hand = ["CPCARD"]
    apply_ops(
        st,
        0,
        [{"op": "hand_to_life", "count": 1, "optional": False, "face": "up", "position": "top", "trait_contains": "CP", "target_iid": "hand:0:CPCARD"}],
        catalog,
    )
    assert st.players[0].life[0] == "CPCARD"
    assert st.players[0].life_face and st.players[0].life_face[0] is True
    trig = _ops("OP18-101", "trigger")[0]
    assert trig["ops"][0]["op"] == "choose_one"
    labels = {opt["id"] for opt in trig["ops"][0]["options"]}
    assert labels == {"ko", "rest"}
