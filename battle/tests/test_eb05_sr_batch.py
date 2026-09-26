"""EB05 SR batch: Bonney, Stussy, Shirahoshi, Alvida, Sugar, Yamato, Gloriosa, Nami."""

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

from battle.effect_library import get_abilities, get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import live_keywords  # noqa: E402
from battle.engine import _deal_one_life_damage, apply_action, inst_power, legal_actions  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))

EXTRAS = {
    "P2": {"card_id": "P2", "card_type": "CHARACTER", "cost": 1, "power": 2000, "name": "P2"},
    "P3": {"card_id": "P3", "card_type": "CHARACTER", "cost": 1, "power": 2000, "name": "P3"},
    "CG8": {
        "card_id": "CG8",
        "card_type": "CHARACTER",
        "cost": 8,
        "power": 8000,
        "name": "CG8",
        "traits": ["十字公會"],
        "traits_en": ["Cross Guild"],
    },
    "MEG": {"card_id": "MEG", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "梅加羅", "name_en": "Megalo"},
    "NEP": {
        "card_id": "NEP",
        "card_type": "CHARACTER",
        "cost": 3,
        "power": 5000,
        "name": "NEP",
        "traits": ["海王類"],
        "traits_en": ["Neptunian"],
    },
    "JUNK": {"card_id": "JUNK", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "JUNK"},
    "BP8": {"card_id": "BP8", "card_type": "CHARACTER", "cost": 5, "power": 8000, "name": "BP8"},
    "H1": {"card_id": "H1", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "H1"},
    "D0": {"card_id": "D0", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "D0"},
}


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    return EXTRAS.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, leader: str, hand: list[str], don: int = 10, **extra) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=leader,
        deck=list(extra.get("deck", ["D0"] * 20)),
        hand=list(hand),
        life=list(extra.get("life", ["L"] * 5)),
        trash=list(extra.get("trash", [])),
        don_active=don,
        don_given=don,
        turns_completed=1,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["Y"] * 20,
        hand=[],
        life=["M"] * 5,
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
    return st


def test_eb05_sr_override_shapes():
    reload_effect_library(force=True)
    for cid in (
        "EB05-001",
        "EB05-006",
        "EB05-014",
        "EB05-014-P1",
        "EB05-021",
        "EB05-034",
        "EB05-052",
        "EB05-055",
    ):
        abs_ = [a for a in get_card_entry(cid)["abilities"] if a.get("ops")]
        assert abs_, f"{cid} dropped on normalize"

    bonney = next(a for a in get_abilities("EB05-001", "on_play"))
    assert "超新星" in str(bonney.get("require_leader_trait") or "") or "Supernovas" in str(
        bonney.get("require_leader_trait") or ""
    )
    assert bonney["ops"][0]["op"] == "draw" and bonney["ops"][0]["count"] == 2
    play = bonney["ops"][1]
    assert play["op"] == "play_from_hand" and play.get("count") == 2 and play.get("power_lte") == 2000

    stussy = next(a for a in get_abilities("EB05-006", "activate_main"))
    assert stussy.get("once") is True
    assert stussy["ops"][0]["op"] == "life_to_hand" and stussy["ops"][0].get("as_cost")
    assert stussy["ops"][1]["op"] == "choose_one"

    shira = next(a for a in get_abilities("EB05-014", "on_play"))
    search = shira["ops"][0]
    assert search["op"] == "search_deck" and search.get("name_or_trait") is True
    assert search.get("top_n") == 5 and search.get("max_add") == 2 and search.get("trash_rest") is True
    shira_p = next(a for a in get_abilities("EB05-014-P1", "on_play"))
    assert shira_p["ops"][0].get("name_or_trait") is True
    assert shira_p["ops"][0].get("max_add") == 2

    alvida = next(a for a in get_abilities("EB05-021", "on_play"))
    assert alvida["ops"][0]["op"] == "draw"
    assert alvida["ops"][2]["op"] == "cannot_play_from_hand"

    sugar = next(a for a in get_abilities("EB05-034", "on_play"))
    assert sugar["ops"][0]["op"] == "return_don" and sugar["ops"][0].get("count") == 2
    assert sugar["ops"][1].get("require_don_field_gte") == 7

    glo = next(a for a in get_abilities("EB05-052", "your_turn"))
    assert glo["ops"][0]["op"] == "replace_life_damage"

    nami = next(a for a in get_abilities("EB05-055", "on_play"))
    assert nami.get("require_your_turn") is True
    assert "Wisdom" in str(nami.get("require_leader_attribute") or "") or "知" in str(
        nami.get("require_leader_attribute") or ""
    )


def test_eb05_001_bonney_supernovas_draws_and_plays():
    reload_effect_library(force=True)
    st = _state(leader="OP14-001", hand=["EB05-001", "P2", "P3"], don=5)
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert "D0" in p0.hand and p0.hand.count("D0") + sum(1 for c in p0.hand if c.startswith("D")) >= 2
    # Two play-from-hand picks
    for _ in range(2):
        if st.pending_choice is None:
            break
        tid = (st.pending_choice.options or [None])[0]
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": tid}, catalog)["ok"]
    names = [c.card_id for c in p0.characters]
    assert "EB05-001" in names
    assert "P2" in names or "P3" in names


def test_eb05_001_bonney_without_supernovas_no_draw():
    reload_effect_library(force=True)
    st = _state(leader="OP04-001", hand=["EB05-001"], don=5)
    p0 = st.players[0]
    deck_n = len(p0.deck)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert len(p0.deck) == deck_n
    assert p0.hand == []


def test_eb05_014_shirahoshi_search_or_filter():
    reload_effect_library(force=True)
    st = _state(
        leader="OP14-020",
        hand=["EB05-014"],
        don=1,
        deck=["MEG", "JUNK", "NEP", "JUNK", "JUNK"] + ["X"] * 15,
    )
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert st.pending_search is not None
    revealed = list(st.pending_search.revealed or [])
    assert "MEG" in revealed and "NEP" in revealed
    i_meg = revealed.index("MEG")
    i_nep = revealed.index("NEP")
    assert apply_action(st, 0, {"type": "select_search", "index": i_meg}, catalog)["ok"]
    assert apply_action(st, 0, {"type": "select_search", "index": i_nep}, catalog)["ok"]
    if st.pending_search is not None:
        assert apply_action(st, 0, {"type": "confirm_search"}, catalog)["ok"]
    assert "MEG" in p0.hand and "NEP" in p0.hand
    assert "JUNK" in p0.trash


def test_eb05_021_alvida_locks_character_plays():
    reload_effect_library(force=True)
    st = _state(leader="ST22-001", hand=["EB05-021", "CG8"], don=9)
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    if st.pending_choice is not None:
        tid = (st.pending_choice.options or [None])[0]
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": tid}, catalog)["ok"]
    plays = [a for a in legal_actions(st, 0, catalog) if a.get("type") == "play_card"]
    assert not plays


def test_eb05_034_sugar_debuff_after_don_cost():
    reload_effect_library(force=True)
    st = _state(leader="OP14-060", hand=["EB05-034"], don=10)
    st.players[1].characters.append(CardInst(iid="opp", card_id="BP8"))
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    if st.pending_effect is not None:
        assert apply_action(st, 0, {"type": "confirm_effect", "accept": True}, catalog)["ok"]
    # Return 2 DON (may be interactive)
    while st.pending_choice is not None and "don:" in str((st.pending_choice.options or [""])[0]):
        tid = st.pending_choice.options[0]
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": tid}, catalog)["ok"]
    if st.pending_choice is not None:
        tid = (st.pending_choice.options or [None])[0]
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": tid}, catalog)["ok"]
    assert inst_power(st, 1, "opp", catalog) == 4000


def test_eb05_052_gloriosa_trashes_instead_of_life():
    reload_effect_library(force=True)
    st = _state(leader="OP08-058", hand=[], don=0)
    glo = CardInst(iid="glo", card_id="EB05-052")
    st.players[0].characters.append(glo)
    life_n = len(st.players[0].life)
    paused = _deal_one_life_damage(st, 0, catalog)
    assert paused is True
    assert st.pending_choice is not None
    assert "glo" in (st.pending_choice.options or [])
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "glo"}, catalog)["ok"]
    assert len(st.players[0].life) == life_n
    assert "EB05-052" in st.players[0].trash
    assert not any(c.iid == "glo" for c in st.players[0].characters)


def test_eb05_055_nami_wisdom_adds_life():
    reload_effect_library(force=True)
    st = _state(leader="OP08-058", hand=["EB05-055"], don=5)
    p0 = st.players[0]
    life_n = len(p0.life)
    deck_n = len(p0.deck)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert len(p0.life) == life_n + 1
    assert len(p0.deck) == deck_n - 1
