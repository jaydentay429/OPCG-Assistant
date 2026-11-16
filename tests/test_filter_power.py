"""Character power 0 must be searchable; power options come from the catalog."""

from __future__ import annotations

import sys
from pathlib import Path

from starlette.responses import Response

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402


def _run_filter(**kwargs):
    response = Response()
    params = dict(
        color=None,
        colors=None,
        cost=None,
        costs=None,
        counter=None,
        counters=None,
        power=None,
        powers=None,
        card_type=None,
        card_types=None,
        attribute=None,
        attributes=None,
        series=None,
        serieses=None,
        rarity=None,
        rarities=None,
        block=None,
        blocks=None,
        keyword=None,
        keywords=None,
        q=None,
        price_min=None,
        price_max=None,
        sort=None,
        priced_only=False,
        offset=0,
        limit=300,
    )
    params.update(kwargs)
    rows = app.filter_cards(response, **params)
    return response, rows


def test_snapshot_keeps_integer_zero_power():
    saved = dict(app.official_snapshot_map)
    cid = "OP99-900"
    try:
        app.official_snapshot_map[cid] = {
            "card_id": cid,
            "card_type": "Character",
            "fields": {"power": 0, "cost": "1"},
        }
        fields = app._snapshot_to_card_fields(cid)
        assert fields["power"] == 0
        assert fields["cost"] == 1
    finally:
        app.official_snapshot_map = saved


def test_filter_character_dash_or_blank_power_is_zero():
    """Official '-' / missing power on a Character is 0 in /filters/cards."""
    app.load_cards_index()
    saved_cards = app.cards_by_id
    saved_snap = dict(app.official_snapshot_map)
    cid_dash = "OP99-901"
    cid_blank = "OP99-902"
    try:
        cards = dict(app.cards_by_id)
        for cid, name in ((cid_dash, "破折号战力"), (cid_blank, "空白战力")):
            cards[cid] = {
                "name": name,
                "name_en": name,
                "category": "Character",
                "cost": 1,
                "rarity": "C",
                "colors": ["綠"],
            }
        app.cards_by_id = cards
        app.official_snapshot_map[cid_dash] = {
            "card_id": cid_dash,
            "card_type": "Character",
            "fields": {"power": "-", "cost": "1"},
        }
        app.official_snapshot_map[cid_blank] = {
            "card_id": cid_blank,
            "card_type": "Character",
            "fields": {"cost": "1"},
        }
        app.rebuild_filter_index()

        for cid in (cid_dash, cid_blank):
            resp = app.build_filter_card_response(cid, cards[cid])
            assert resp.power == 0
            assert resp.card_type
            assert "character" in resp.card_type.lower() or "角色" in resp.card_type

        response, matched = _run_filter(powers="0")
        ids = {row.id for row in matched}
        assert cid_dash in ids
        assert cid_blank in ids
        assert int(response.headers["X-Total-Count"]) >= 2
    finally:
        app.cards_by_id = saved_cards
        app.official_snapshot_map = saved_snap
        app.rebuild_filter_index()


def test_filter_event_blank_power_is_not_zero():
    """Events have no printed power; they must not appear under 战力 0."""
    app.load_cards_index()
    saved_cards = app.cards_by_id
    saved_snap = dict(app.official_snapshot_map)
    cid = "OP99-903"
    try:
        cards = dict(app.cards_by_id)
        cards[cid] = {
            "name": "测试事件",
            "name_en": "Test Event",
            "category": "Event",
            "cost": 1,
            "rarity": "C",
            "colors": ["綠"],
        }
        app.cards_by_id = cards
        app.official_snapshot_map[cid] = {
            "card_id": cid,
            "card_type": "Event",
            "fields": {"power": "-", "cost": "1"},
        }
        app.rebuild_filter_index()

        resp = app.build_filter_card_response(cid, cards[cid])
        assert resp.power is None

        _, matched = _run_filter(powers="0")
        assert cid not in {row.id for row in matched}
    finally:
        app.cards_by_id = saved_cards
        app.official_snapshot_map = saved_snap
        app.rebuild_filter_index()


def test_filter_cards_powers_zero_includes_otama():
    """Live catalog: OP07-022 玉兒 is a 0-power Character and must match."""
    app.load_cards_index()
    app.load_official_snapshot_data()
    app.rebuild_filter_index()
    assert "OP07-022" in app.cards_by_id

    resp = app.build_filter_card_response("OP07-022", app.cards_by_id["OP07-022"])
    assert resp.power == 0

    # More than one page of 0-power cards after the fix; raise the cap.
    response = Response()
    rows = app.filter_cards(
        response,
        color=None,
        colors=None,
        cost=None,
        costs=None,
        counter=None,
        counters=None,
        power=None,
        powers="0",
        card_type=None,
        card_types=None,
        attribute=None,
        attributes=None,
        series=None,
        serieses=None,
        rarity=None,
        rarities=None,
        block=None,
        blocks=None,
        keyword=None,
        keywords=None,
        q=None,
        price_min=None,
        price_max=None,
        sort=None,
        priced_only=False,
        offset=0,
        limit=300,
    )
    ids = {row.id for row in rows}
    assert "OP07-022" in ids
    assert int(response.headers["X-Total-Count"]) >= 100


def test_filter_options_include_zero_and_high_powers():
    app.load_cards_index()
    app.load_official_snapshot_data()
    app.rebuild_filter_index()
    opts = app.get_filter_options()
    powers = opts["powers"]
    assert powers == sorted(powers)
    for value in (0, 10000, 11000, 12000, 13000):
        assert value in powers, f"missing power option {value}"
