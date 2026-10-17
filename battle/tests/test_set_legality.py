"""Scheduled sets still need effect data. Release dates do not block battle."""

from datetime import date

from battle.set_legality import (
    battle_today,
    card_has_battle_effect_data,
    card_legality_block,
    casual_deck_legality_error,
    ranked_set_legality_error,
)
from battle.engine import ranked_deck_ban_error

BEFORE = date(2026, 10, 13)
EB05_RELEASE = date(2026, 10, 30)
OP18_RELEASE = date(2026, 11, 20)
OP18_LEGAL = date(2026, 11, 27)
AFTER = date(2026, 12, 1)


def test_release_dates_do_not_block_casual_ai_or_ranked():
    assert card_legality_block("EB05-001", mode="casual", on_date=BEFORE) is None
    assert card_legality_block("OP18-001", mode="ranked", on_date=BEFORE) is None
    assert card_legality_block("EB05-001", mode="ranked", on_date=EB05_RELEASE) is None
    assert card_legality_block("OP18-001", mode="casual", on_date=OP18_RELEASE) is None
    assert card_legality_block("OP18-001", mode="ranked", on_date=OP18_RELEASE) is None
    assert card_legality_block("OP18-085", mode="casual", on_date=BEFORE) is None
    assert card_legality_block("OP18-085", mode="ranked", on_date=OP18_RELEASE) is None
    assert card_legality_block("OP18-085", mode="ranked", on_date=OP18_LEGAL) is None
    assert casual_deck_legality_error("OP17-001", {"EB05-001": 4}, on_date=BEFORE) is None
    assert ranked_set_legality_error("OP18-001", {"OP01-016": 4}, on_date=BEFORE) is None
    assert ranked_set_legality_error("EB05-016", {"OP01-016": 4}, on_date=EB05_RELEASE) is None
    assert ranked_set_legality_error("OP18-060", {"OP18-119": 4}, on_date=OP18_RELEASE) is None
    assert ranked_deck_ban_error("OP18-060", {"OP18-119": 4}, on_date=BEFORE) is None


def test_missing_effect_data_still_blocks_before_and_after_release():
    assert card_has_battle_effect_data("EB05-001")
    assert card_has_battle_effect_data("EB05-004")
    assert card_has_battle_effect_data("EB05-008")
    assert card_has_battle_effect_data("OP18-011")
    assert card_has_battle_effect_data("OP18-017")
    assert card_has_battle_effect_data("OP18-085")
    assert not card_has_battle_effect_data("OP18-003")
    assert not card_has_battle_effect_data("OP18-106")
    assert card_legality_block("EB05-001", mode="casual", on_date=BEFORE) is None
    assert card_legality_block("EB05-004", mode="ranked", on_date=BEFORE) is None
    assert card_legality_block("OP18-003", mode="casual", on_date=BEFORE) == "no_effect"
    assert card_legality_block("OP18-003", mode="ranked", on_date=AFTER) == "no_effect"
    assert card_legality_block("OP18-106", mode="casual", on_date=OP18_LEGAL) == "no_effect"
    missing = casual_deck_legality_error("OP17-001", {"OP18-003": 4}, on_date=BEFORE)
    assert missing and "OP18-003" in missing and "battle effect data is missing" in missing
    assert "release date" not in missing
    assert casual_deck_legality_error("OP17-001", {"EB05-004": 4}, on_date=BEFORE) is None
    assert casual_deck_legality_error("EB05-001", {"OP01-016": 4}, on_date=BEFORE) is None
    ranked_missing = ranked_deck_ban_error("OP18-106", {"OP01-016": 4}, on_date=BEFORE)
    assert ranked_missing and "OP18-106" in ranked_missing and "battle effect data is missing" in ranked_missing


def test_parallel_art_uses_base_effect_data_and_old_sets_stay_open():
    assert card_has_battle_effect_data("OP18-001-P1")
    assert card_legality_block("OP18-001-P1", mode="casual", on_date=BEFORE) is None
    assert card_legality_block("OP01-001", mode="ranked", on_date=BEFORE) is None
    assert ranked_deck_ban_error("OP17-001", {"OP01-016": 4}, on_date=BEFORE) is None
    assert casual_deck_legality_error("ST01-001", {"OP01-016": 4}, on_date=BEFORE) is None


def test_opcg_battle_today_is_ignored(monkeypatch):
    monkeypatch.delenv("OPCG_BATTLE_TODAY", raising=False)
    real = battle_today()
    monkeypatch.setenv("OPCG_BATTLE_TODAY", "1999-01-01")
    assert battle_today() == real
    assert battle_today(BEFORE) == BEFORE
    assert card_legality_block("EB05-001", mode="casual") is None
    assert card_legality_block("OP18-001", mode="ranked") is None
    monkeypatch.delenv("OPCG_BATTLE_TODAY", raising=False)
    assert battle_today() == real
