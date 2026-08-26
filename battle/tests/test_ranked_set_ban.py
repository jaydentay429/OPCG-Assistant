from battle.engine import ranked_deck_ban_error, deck_has_ranked_banned_cards


def test_ranked_bans_op18_eb05():
    assert deck_has_ranked_banned_cards("OP18-021", {"OP07-015": 4}) == ["OP18-021"]
    assert "EB05-016" in deck_has_ranked_banned_cards("OP17-001", {"EB05-016": 4})
    assert ranked_deck_ban_error("OP17-001", {"OP01-016": 4}) is None
    assert ranked_deck_ban_error("OP11-022-P2", {"OP01-016-P9": 4}) is None
    err = ranked_deck_ban_error("OP18-060", {"OP18-119": 4})
    assert err and "OP18" in err
