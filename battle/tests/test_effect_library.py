"""Regression tests for curated / compiled effect library."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import (  # noqa: E402
    compile_card_from_templates,
    lookup_runnable_ability,
    reload_effect_library,
    resolve_ability,
)
from battle.effect_schema import ability_is_runnable, normalize_ability  # noqa: E402
from battle.state import MatchState, PlayerState  # noqa: E402


def _load_catalog() -> dict:
    with (ROOT / "index" / "cards_by_id.json").open(encoding="utf-8") as f:
        return json.load(f)


def _minimal_state() -> MatchState:
    p0 = PlayerState(seat=0, user_id="u0", username="P1", is_ai=False, leader_card_id="L", deck=["A", "B", "C"], hand=[], life=["X"] * 5)
    p1 = PlayerState(seat=1, user_id="u1", username="AI", is_ai=True, leader_card_id="L", deck=["A"] * 10, hand=[], life=["X"] * 5)
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=1,
        players=[p0, p1],
        rng_seed=1,
    )


def test_op16_034_search_from_library_or_template():
    reload_effect_library(force=True)
    catalog = _load_catalog()
    info = catalog["OP16-034"]
    ability = lookup_runnable_ability("OP16-034", "on_play")
    assert ability is not None, "OP16-034 should have runnable on_play"
    assert any(o.get("op") == "search_deck" for o in ability["ops"])
    state = _minimal_state()
    pending = resolve_ability(state, 0, "OP16-034", "ch1", "on_play", info, None, allow_llm=False)
    assert pending is not None
    assert pending.uncertain is False
    assert any(o.get("op") == "search_deck" for o in pending.ops)


def test_golden_overrides():
    reload_effect_library(force=True)
    golden_path = Path(__file__).with_name("golden_effects.json")
    goldens = json.loads(golden_path.read_text(encoding="utf-8"))
    for cid, expected in goldens.items():
        if not isinstance(expected, dict) or "abilities" not in expected:
            continue
        for exp in expected["abilities"]:
            got = lookup_runnable_ability(cid, exp["timing"])
            assert got is not None, f"missing {cid} {exp['timing']}"
            assert [o.get("op") for o in got["ops"]] == [o.get("op") for o in exp["ops"]]


def test_compile_templates_never_draw_for_look_at():
    catalog = _load_catalog()
    info = catalog["OP16-034"]
    entry = compile_card_from_templates("OP16-034", info)
    on_play = next((a for a in entry["abilities"] if a["timing"] == "on_play"), None)
    assert on_play and ability_is_runnable(on_play)
    assert all(o.get("op") != "draw" for o in on_play["ops"])
    assert any(o.get("op") == "search_deck" for o in on_play["ops"])


def test_normalize_rejects_bad_timing():
    assert normalize_ability({"timing": "nope", "ops": [{"op": "draw"}]}) is None


if __name__ == "__main__":
    test_normalize_rejects_bad_timing()
    test_compile_templates_never_draw_for_look_at()
    test_op16_034_search_from_library_or_template()
    test_golden_overrides()
    print("ok")
