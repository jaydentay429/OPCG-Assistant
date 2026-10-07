"""Tournament decks sort by date, placement, then record — not raw placement text."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import Response  # noqa: E402

import app  # noqa: E402
from topdecks_normalize import (  # noqa: E402
    norm_placement,
    parse_topdeck_record,
    placement_sort_rank,
)

CARD = "OP01-002"


def test_norm_placement_covers_live_spellings():
    cases = {
        "1st Place": "1st",
        "1st (16-1)": "1st",
        "1st PLace": "1st",
        "1st place": "1st",
        "1st Palce": "1st",
        "1s Place": "1st",
        "1ts Place": "1st",
        "1th Place": "1st",
        "1st(3)(15-0)": "1st",
        "1st Swiss(10-0)": "1st",
        "2nd Place": "2nd",
        "2rd Place": "2nd",
        "2d Place": "2nd",
        "3rd Place": "3rd",
        "3th Place": "3rd",
        "4th Place": "4th",
        "4rd Place": "4th",
        "5th Place": "5th",
        "5h Place": "5th",
        "22nd Place": "place_22",
        "21st Place": "place_21",
        "23rd Place": "place_23",
        "23th Place": "place_23",
        "10th (9-1)": "place_10",
        "Top-8": "top_8",
        "Top 8": "top_8",
        "top 8": "top_8",
        "TOP-16": "top_16",
        "Top8": "top_8",
        "Top4": "top_4",
        "T8 (13-2)": "top_8",
        "T16(10-3)": "top_16",
        "T4": "top_4",
        "T32 Swiss": "top_32",
        "T32 (8-2) Swiss": "top_32",
        "T8 (8-1)Swiss": "top_8",
        "T4(8-1)Swiss": "top_4",
        "T64(8-2)Swiss": "top_64",
        "T16 (8-2)Swiss": "top_16",
        "T4 n T16": "top_4",
        "NA": "na",
        "NA(9-2)": "na",
        "NA (8-2)Swiss": "na",
        "冠军": "1st",
        "冠軍": "1st",
        "亚军": "2nd",
        "亞軍": "2nd",
        "季军": "3rd",
        "季軍": "3rd",
        "第1名": "1st",
        "第4名": "4th",
        "第10名": "place_10",
        "第一名": "1st",
        "前8": "top_8",
        "前 16": "top_16",
    }
    for raw, key in cases.items():
        assert norm_placement(raw) == key, raw


def test_unparsed_placements_stay_out_of_the_ranked_bands():
    for raw in ("", "Top-x", "Top-X", "45934", "8-0"):
        assert placement_sort_rank(raw)[0] == 3, raw


def test_parse_record_reads_win_loss_and_skips_other_parens():
    assert parse_topdeck_record("1st (16-1)") == (17, 16, 1)
    assert parse_topdeck_record("NA(9-2)") == (11, 9, 2)
    assert parse_topdeck_record("T16(10-3)") == (13, 10, 3)
    assert parse_topdeck_record("1st(3)(15-0)") == (15, 15, 0)
    assert parse_topdeck_record("T2 (9-1-0)") == (10, 9, 1)
    assert parse_topdeck_record("6th Swiss(9-1)") == (10, 9, 1)
    assert parse_topdeck_record("1st (4-0) ") == (4, 4, 0)
    assert parse_topdeck_record("T2 (7-x)") is None
    assert parse_topdeck_record("1st Place (9 wins)") is None
    assert parse_topdeck_record("1st Place 7 wins") is None
    assert parse_topdeck_record("8-0") is None
    assert parse_topdeck_record("1st Place") is None


def _row(deck_id: str, placement: str, date: str = "10/4/2026") -> dict:
    return {
        "id": deck_id,
        "date": date,
        "placement": placement,
        "name": deck_id,
        "leader": "OP01-001",
        "cards": {CARD: 4},
    }


def _ids(rows: list[dict]) -> list[str]:
    return [row["id"] for row in sorted(rows, key=app.topdeck_sort_key)]


def test_same_day_orders_placement_then_record_then_id():
    rows = [
        _row("na-huge", "NA (20-0)"),
        _row("t16", "T16 (10-3)"),
        _row("t8", "T8 (13-2)"),
        _row("tenth", "10th (9-1)"),
        _row("first-small", "1st (5-0)"),
        _row("first-big", "1st (16-1)"),
        _row("first-plain-b", "1st Place"),
        _row("first-plain-a", "1st Place"),
        _row("second", "2nd Place"),
        _row("t64", "T64 (9-3)"),
        _row("unknown", "45934"),
        _row("same-wins-b", "T16 (9-3)"),
        _row("same-wins-a", "T16 (10-2)"),
    ]
    assert _ids(rows) == [
        "first-big",  # 1st (16-1): more games than 1st (5-0)
        "first-small",
        "first-plain-a",  # no record sorts after a parsed record; id breaks the tie
        "first-plain-b",
        "second",
        "t8",
        "t16",  # T16 (10-3): more games than the other T16s
        "same-wins-a",  # T16 (10-2) before T16 (9-3): same games, more wins, fewer losses
        "same-wins-b",
        "t64",
        "tenth",  # other Nth after every top cut
        "na-huge",  # NA last even with a long record
        "unknown",
    ]


def test_more_games_beats_a_cleaner_shorter_record():
    rows = [
        _row("short", "1st (5-0)"),
        _row("long", "1st (5-2)"),
    ]
    assert _ids(rows) == ["long", "short"]


def test_record_key_counts_games_wins_then_losses():
    key = app.topdeck_sort_key(_row("a", "T8 (10-2)"))
    assert key[2] == (0, -12, -10, 2)
    missing = app.topdeck_sort_key(_row("b", "T8"))
    assert missing[2][0] == 1
    assert key < missing


def test_newer_date_beats_a_better_placement():
    rows = [
        _row("old-win", "1st (16-1)", date="10/4/2026"),
        _row("new-cut", "T64 (1-1)", date="10/5/2026"),
    ]
    assert _ids(rows) == ["new-cut", "old-win"]


def test_podium_before_top_cuts_and_fourth_ties_t4():
    assert placement_sort_rank("3rd Place") < placement_sort_rank("T2")
    assert placement_sort_rank("T2") < placement_sort_rank("T4")
    assert placement_sort_rank("4th Place") == placement_sort_rank("T4")
    assert placement_sort_rank("T4") < placement_sort_rank("T8")
    assert placement_sort_rank("T8") < placement_sort_rank("5th Place")
    assert placement_sort_rank("第1名") < placement_sort_rank("前8")


def test_card_tournaments_endpoint_uses_the_same_order(tmp_path, monkeypatch):
    decks = [
        _row("new-cut", "T64 (1-1)", date="10/5/2026"),
        _row("first-big", "1st (16-1)"),
        _row("first-small", "1st (5-0)"),
        _row("t16", "T16"),
        _row("t8", "T8 (3-1)"),
        _row("na", "NA (9-2)"),
        _row("tenth", "10th Place"),
    ]
    path = tmp_path / "topdecks_decks.json"
    path.write_text(json.dumps({"decks": decks}), encoding="utf-8")
    monkeypatch.setattr(app, "TOPDECKS_FILE", path)
    saved = {
        "payload": app.topdecks_payload,
        "mtime": app.topdecks_mtime,
        "by_id": app.topdecks_by_id,
        "by_card": app.topdecks_by_card_base,
        "appearances": app.topdecks_appearances_by_card,
        "sorted": app.topdecks_decks_sorted,
        "facets": app.topdecks_facets_cache,
        "blobs": app.topdecks_meta_blob_by_id,
    }
    try:
        app.topdecks_mtime = 0
        app.load_topdecks_data()
        listed = [row["id"] for row in app.topdecks_decks_sorted]
        body = app.card_recent_tournaments(Response(), CARD, limit=30)
        appeared = [item["id"] for item in body["items"]]
        assert listed == appeared == [
            "new-cut",
            "first-big",
            "first-small",
            "t8",
            "t16",
            "tenth",
            "na",
        ]
        assert body["total_matched"] == 7
    finally:
        app.topdecks_payload = saved["payload"]
        app.topdecks_mtime = saved["mtime"]
        app.topdecks_by_id = saved["by_id"]
        app.topdecks_by_card_base = saved["by_card"]
        app.topdecks_appearances_by_card = saved["appearances"]
        app.topdecks_decks_sorted = saved["sorted"]
        app.topdecks_facets_cache = saved["facets"]
        app.topdecks_meta_blob_by_id = saved["blobs"]
