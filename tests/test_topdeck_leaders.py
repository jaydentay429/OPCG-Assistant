"""Leader pages: deck counts, wins, champion lists and common cards per base leader."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from fastapi import HTTPException, Response  # noqa: E402

import app  # noqa: E402


def _deck(did, leader, date, placement, cards, fmt="jp"):
    return {
        "id": did,
        "leader": leader,
        "date": date,
        "placement": placement,
        "format": fmt,
        "cards": cards,
    }


DECKS = [
    _deck("d1", "OP01-001", "11/20/2026", "1st Place", {"OP01-001": 1, "OP01-016": 4, "OP01-013": 2}),
    _deck("d2", "OP01-001-P1", "11/18/2026", "Top 8", {"OP01-016": 4, "OP01-016-P1": 0, "OP02-004": 3}),
    _deck("d3", "OP01-001", "10/01/2026", "2nd Place", {"OP01-016": 2}, fmt="en"),
    _deck("d4", "ST01-001", "11/19/2026", "1st", {"ST01-012": 4}),
]


def test_stats_group_parallel_leaders_and_count_wins():
    stats = app.compute_topdeck_leader_stats(DECKS)
    luffy = stats["OP01-001"]
    assert luffy["decks"] == 3
    assert luffy["wins"] == 1
    assert luffy["top_finishes"] == 3
    assert luffy["champion_ids"] == ["d1"]
    assert luffy["recent_ids"] == ["d1", "d2", "d3"]
    assert luffy["formats"] == {"jp": 2, "en": 1}
    assert luffy["first_date"] == "2026-10-01"
    assert luffy["last_date"] == "2026-11-20"
    # The leader itself is not a "common card"; zero-qty rows are ignored.
    assert "OP01-001" not in luffy["card_decks"]
    assert luffy["card_decks"]["OP01-016"] == 3
    assert luffy["card_qty"]["OP01-016"] == 10
    assert luffy["sample"] == 3


def test_leader_endpoints(monkeypatch):
    monkeypatch.setattr(app, "ensure_topdecks_data_fresh", lambda: None)
    monkeypatch.setattr(app, "topdecks_decks_sorted", DECKS)
    monkeypatch.setattr(app, "topdecks_by_id", {d["id"]: d for d in DECKS})
    monkeypatch.setattr(app, "topdecks_mtime", 12345.0)
    monkeypatch.setattr(app, "_topdeck_leader_cache", {"mtime": None, "stats": {}})

    listing = app.topdecks_leaders(Response(), min_decks=1)
    assert [r["leader"] for r in listing["items"]] == ["OP01-001", "ST01-001"]
    assert listing["items"][0]["decks"] == 3

    only_big = app.topdecks_leaders(Response(), min_decks=2)
    assert [r["leader"] for r in only_big["items"]] == ["OP01-001"]

    detail = app.topdecks_leader_detail(Response(), "op01-001-p1")
    assert detail["leader"] == "OP01-001"
    assert [d["id"] for d in detail["champion_decks"]] == ["d1"]
    top = detail["common_cards"][0]
    assert top["id"] == "OP01-016"
    assert top["decks"] == 3
    assert top["rate"] == 1.0
    assert top["avg_qty"] == pytest.approx(3.33, abs=0.01)

    with pytest.raises(HTTPException) as exc:
        app.topdecks_leader_detail(Response(), "OP09-001")
    assert exc.value.status_code == 404
