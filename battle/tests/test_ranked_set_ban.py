from datetime import date

from battle.engine import ranked_deck_ban_error, deck_has_ranked_banned_cards

BEFORE = date(2026, 10, 13)


def test_ranked_bans_op18_eb05_before_release():
    assert deck_has_ranked_banned_cards("OP18-021", {"OP07-015": 4}, on_date=BEFORE) == ["OP18-021"]
    assert "EB05-016" in deck_has_ranked_banned_cards("OP17-001", {"EB05-016": 4}, on_date=BEFORE)
    assert ranked_deck_ban_error("OP17-001", {"OP01-016": 4}, on_date=BEFORE) is None
    assert ranked_deck_ban_error("OP11-022-P2", {"OP01-016-P9": 4}, on_date=BEFORE) is None
    err = ranked_deck_ban_error("OP18-060", {"OP18-119": 4}, on_date=BEFORE)
    assert err and "OP18" in err and "2026-11-20" in err
