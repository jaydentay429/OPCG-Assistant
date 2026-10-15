"""Release and tournament-legal dates for sets that need effect data."""

from datetime import date

from battle.set_legality import (
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


def test_schedule_blocks_unreleased_sets_in_casual_and_ranked():
    assert card_legality_block("EB05-001", mode="casual", on_date=BEFORE) == "unreleased"
    assert card_legality_block("OP18-001", mode="ranked", on_date=BEFORE) == "unreleased"
    casual = casual_deck_legality_error("OP17-001", {"EB05-001": 4}, on_date=BEFORE)
    ranked = ranked_set_legality_error("OP18-001", {"OP01-016": 4}, on_date=BEFORE)
    assert casual and "EB05-001" in casual and "2026-10-30" in casual
    assert ranked and "OP18-001" in ranked and "2026-11-20" in ranked


def test_casual_opens_on_release_only_with_effect_data():
    assert card_has_battle_effect_data("EB05-001")
    assert card_has_battle_effect_data("EB05-004")
    assert not card_has_battle_effect_data("EB05-008")
    assert card_legality_block("EB05-001", mode="casual", on_date=EB05_RELEASE) is None
    assert card_legality_block("EB05-004", mode="casual", on_date=EB05_RELEASE) is None
    assert card_legality_block("EB05-008", mode="casual", on_date=EB05_RELEASE) == "no_effect"
    missing = casual_deck_legality_error("OP17-001", {"EB05-008": 4}, on_date=AFTER)
    assert missing and "EB05-008" in missing and "battle effect data is missing" in missing
    assert casual_deck_legality_error("OP17-001", {"EB05-004": 4}, on_date=AFTER) is None
    assert casual_deck_legality_error("EB05-001", {"OP01-016": 4}, on_date=EB05_RELEASE) is None


def test_ranked_waits_for_tournament_legal_date():
    assert card_legality_block("EB05-001", mode="ranked", on_date=EB05_RELEASE) == "not_ranked_legal"
    assert card_legality_block("EB05-001", mode="ranked", on_date=date(2026, 11, 6)) is None
    early = ranked_set_legality_error("EB05-016", {"OP01-016": 4}, on_date=EB05_RELEASE)
    assert early and "tournament-legal date" in early and "2026-11-06" in early
    assert ranked_set_legality_error("EB05-016", {"OP01-016": 4}, on_date=date(2026, 11, 6)) is None


def test_op18_ranked_date_is_marked_assumed():
    assert card_legality_block("OP18-001", mode="casual", on_date=OP18_RELEASE) is None
    assert card_legality_block("OP18-001", mode="ranked", on_date=OP18_RELEASE) == "not_ranked_legal"
    assert card_has_battle_effect_data("OP18-011")
    assert card_legality_block("OP18-011", mode="casual", on_date=OP18_LEGAL) is None
    assert not card_has_battle_effect_data("OP18-017")
    assert card_legality_block("OP18-017", mode="casual", on_date=OP18_LEGAL) == "no_effect"
    assumed = ranked_set_legality_error("OP18-060", {"OP18-119": 4}, on_date=OP18_RELEASE)
    assert assumed and "2026-11-27" in assumed and "7-day rule" in assumed
    assert ranked_set_legality_error("OP18-001", {"OP01-016": 4}, on_date=OP18_LEGAL) is None
    missing = ranked_deck_ban_error("OP18-017", {"OP01-016": 4}, on_date=AFTER)
    assert missing and "OP18-017" in missing and "battle effect data is missing" in missing


def test_op18_085_uses_op18_release_and_tournament_dates():
    assert card_legality_block("OP18-085", mode="casual", on_date=BEFORE) == "unreleased"
    assert card_legality_block("OP18-085", mode="ranked", on_date=BEFORE) == "unreleased"
    assert card_has_battle_effect_data("OP18-085")
    assert card_legality_block("OP18-085", mode="casual", on_date=OP18_RELEASE) is None
    assert card_legality_block("OP18-085", mode="ranked", on_date=OP18_RELEASE) == "not_ranked_legal"
    assert card_legality_block("OP18-085", mode="casual", on_date=OP18_LEGAL) is None
    assert card_legality_block("OP18-085", mode="ranked", on_date=OP18_LEGAL) is None


def test_parallel_art_uses_base_effect_data_and_old_sets_stay_open():
    assert card_has_battle_effect_data("OP18-001-P1")
    assert card_legality_block("OP18-001-P1", mode="casual", on_date=OP18_RELEASE) is None
    assert card_legality_block("OP01-001", mode="ranked", on_date=BEFORE) is None
    assert ranked_deck_ban_error("OP17-001", {"OP01-016": 4}, on_date=BEFORE) is None
    assert casual_deck_legality_error("ST01-001", {"OP01-016": 4}, on_date=BEFORE) is None
