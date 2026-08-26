"""OP17-046..060 encoding / runtime (Rocks + Purple package)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import ability_is_runnable, get_card_entry, reload_effect_library  # noqa: E402

IDS = [f"OP17-{i:03d}" for i in range(46, 61)]


def test_op17_046_to_060_runnable():
    reload_effect_library(force=True)
    for cid in IDS:
        if cid in {"OP17-051"}:
            continue
        abilities = get_card_entry(cid)["abilities"]
        bad = [a for a in abilities if a.get("ops") and not ability_is_runnable(a)]
        assert not bad, f"{cid} still has unrunnable abilities: {bad}"

    gloriosa = get_card_entry("OP17-046")
    assert any(a.get("timing") == "your_turn" for a in gloriosa["abilities"])
    on_play = next(a for a in gloriosa["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][0].get("target_kind") == "any_character"

    shiki_eoy = next(a for a in get_card_entry("OP17-047")["abilities"] if a["timing"] == "end_of_your_turn")
    assert shiki_eoy["ops"][0].get("op") == "opponent_hand_to_bottom"
    assert int(shiki_eoy.get("require_hand_lte") or 0) == 2

    shiki048 = get_card_entry("OP17-048")
    assert any(
        a.get("timing") == "your_turn"
        and any(o.get("keyword") == "rush_character" for o in a.get("ops") or [])
        for a in shiki048["abilities"]
    )
    atk = next(a for a in shiki048["abilities"] if a["timing"] == "when_attacking")
    assert atk["ops"][0].get("trait_contains") or atk["ops"][0].get("op") == "trash_hand"

    linlin = next(a for a in get_card_entry("OP17-049")["abilities"] if a["timing"] == "on_play")
    assert linlin["ops"][0].get("op") == "choose_one"
    ctr = next(a for a in get_card_entry("OP17-049")["abilities"] if a["timing"] == "on_opponent_attack")
    assert ctr["ops"][1].get("duration") == "battle"

    marlon = next(a for a in get_card_entry("OP17-052")["abilities"] if a["timing"] == "on_play")
    assert marlon["ops"][0].get("op") == "add_from_trash"
    assert marlon["ops"][0].get("cost_eq") == 0

    barbell_ko = next(a for a in get_card_entry("OP17-053")["abilities"] if a["timing"] == "on_ko")
    assert barbell_ko["ops"][0].get("count") == 2

    stussy = next(a for a in get_card_entry("OP17-054")["abilities"] if a["timing"] == "on_play")
    assert stussy["ops"][0].get("base_cost_lte") == 6
    act = next(a for a in get_card_entry("OP17-054")["abilities"] if a["timing"] == "activate_main")
    assert act["ops"][0].get("count") == 3

    ev55 = get_card_entry("OP17-055")
    main55 = next(a for a in ev55["abilities"] if a["timing"] == "on_play")
    assert main55["ops"][1].get("keyword") == "blockerless"

    ev56 = get_card_entry("OP17-056")
    assert next(a for a in ev56["abilities"] if a["timing"] == "on_play")["ops"][0]["count"] == 5

    stage = next(a for a in get_card_entry("OP17-057")["abilities"] if a["timing"] == "on_opponent_attack")
    assert stage["ops"][0].get("as_cost") is True
    assert stage["ops"][2].get("trait_contains")

    aramaki = get_card_entry("OP17-059")
    assert any(a.get("timing") == "your_turn" for a in aramaki["abilities"])
    play59 = next(a for a in aramaki["abilities"] if a["timing"] == "on_play")
    assert play59["ops"][1].get("op") == "draw"
    assert play59["ops"][2].get("count") == 2

    ulti = next(a for a in get_card_entry("OP17-060")["abilities"] if a["timing"] == "on_play")
    assert "Animal Kingdom" in str(ulti.get("require_leader_trait") or "")
    assert ulti["ops"][1].get("power_lte") == 3000
