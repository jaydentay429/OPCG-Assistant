"""Official ban list: data file, variant inheritance, and server rejection."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as appmod  # noqa: E402
from app import _validate_deck_contents  # noqa: E402
from battle.engine import ranked_deck_ban_error  # noqa: E402
from official_restriction import (  # noqa: E402
    LIST_PATH,
    load_restriction_entries,
    official_restriction_error,
    restriction_base_id,
    restriction_violations,
)

BANNED = ["OP03-040", "OP06-047", "OP06-086", "OP06-116", "OP14-020", "ST10-001"]
PAIRS = [
    ("OP07-115", "EB04-058"),
    ("OP11-040", "OP11-067"),
    ("OP11-040", "OP08-069"),
]
NOT_ON_LIST = [
    "OP07-045",
    "EB01-059",
    "ST06-015",
    "OP02-024",
    "OP03-098",
    "OP02-117",
    "OP05-041",
    "OP02-052",
    "P-163",
]
TODAY = date(2026, 10, 13)


def test_restriction_file_matches_the_current_official_list():
    payload = json.loads(LIST_PATH.read_text(encoding="utf-8"))
    entries = load_restriction_entries()
    assert [row["card_id"] for row in entries if row["type"] == "banned"] == [
        "OP06-047",
        "OP03-040",
        "OP06-086",
        "ST10-001",
        "OP06-116",
        "OP14-020",
    ]
    banned = sorted(row["card_id"] for row in entries if row["type"] == "banned")
    assert banned == BANNED
    assert [row for row in entries if row["type"] == "restricted"] == []
    assert [tuple(row["card_ids"]) for row in entries if row["type"] == "pair"] == list(PAIRS)
    listed = {row.get("card_id") for row in entries}
    listed.update(card_id for row in entries for card_id in row.get("card_ids") or [])
    assert listed.isdisjoint(NOT_ON_LIST)
    mihawk = next(row for row in entries if row.get("card_id") == "OP14-020")
    assert mihawk["effective_date"] == "2026-10-12"
    assert mihawk["type"] == "banned"
    assert mihawk["source_url"] == "https://en.onepiece-cardgame.com/news/restriction-261001.html"
    assert "https://en.onepiece-cardgame.com/news/restriction.html" in payload["current_list_urls"]
    assert "https://asia-en.onepiece-cardgame.com/news/restriction.html" in payload["current_list_urls"]
    law = next(row for row in entries if row.get("card_id") == "ST10-001")
    reject = next(row for row in entries if row.get("card_id") == "OP06-116")
    borsalino = next(row for row in entries if row.get("type") == "pair" and "EB04-058" in row["card_ids"])
    assert law["asia_effective_date"] == "2024-09-01"
    assert reject["asia_effective_date"] == "2024-04-01"
    assert borsalino["effective_date"] == "2026-04-10"
    assert borsalino["asia_effective_date"] == "2026-05-01"


def test_variants_inherit_the_base_card_and_pairs_need_both_cards():
    assert restriction_base_id("OP14-020-P1") == "OP14-020"
    assert restriction_base_id("op14-020-p1") == "OP14-020"
    mihawk = official_restriction_error("OP14-020-P1", {}, lang="en", on_date=TODAY)
    assert mihawk and "OP14-020-P1" in mihawk and "2026-10-12" in mihawk
    assert official_restriction_error("OP14-020", {}, lang="en", on_date=date(2026, 10, 11)) is None
    assert official_restriction_error("OP11-040", {"OP01-016": 4}, lang="en", on_date=TODAY) is None
    pair = official_restriction_error("OP11-040-P1", {"OP11-067-P1": 1}, lang="zh", on_date=TODAY)
    assert pair and "禁用组合" in pair and "OP11-040-P1" in pair and "OP11-067-P1" in pair
    assert official_restriction_error("ST01-001", {"OP11-067": 4}, on_date=TODAY) is None
    pudding = official_restriction_error("ST01-001", {"OP06-047": 4}, lang="zh", on_date=TODAY)
    assert pudding and "OP06-047" in pudding and "2026-04-01 起禁用" in pudding


def test_restricted_cap_counts_variants_together():
    entries = [
        {
            "card_id": "OP01-016",
            "type": "restricted",
            "effective_date": "2026-01-01",
            "source_url": "https://en.onepiece-cardgame.com/news/restriction.html",
        }
    ]
    assert restriction_violations("ST01-001", {"OP01-016": 1}, on_date=TODAY, entries=entries) == []
    hits = restriction_violations(
        "ST01-001",
        {"OP01-016": 1, "OP01-016-P1": 1},
        on_date=TODAY,
        entries=entries,
    )
    assert len(hits) == 1 and hits[0].kind == "restricted"


def test_ranked_and_deck_save_reject_banned_decks():
    appmod.load_cards_index()
    err = ranked_deck_ban_error("OP14-020", {"OP01-016": 4})
    assert err and "Banned card OP14-020" in err and "2026-10-12" in err
    assert ranked_deck_ban_error("OP18-060", {"OP18-119": 4}, on_date=date(2026, 10, 13)) is None
    assert ranked_deck_ban_error("OP17-001", {"OP01-016": 4}) is None

    with pytest.raises(HTTPException) as banned_leader:
        _validate_deck_contents("OP14-020-P1", {"OP01-016": 4})
    assert banned_leader.value.status_code == 400
    assert "OP14-020-P1" in str(banned_leader.value.detail)
    assert "2026-10-12 起禁用" in str(banned_leader.value.detail)

    with pytest.raises(HTTPException) as banned_pair:
        _validate_deck_contents("OP11-040", {"OP08-069": 1, "OP01-016": 4})
    assert "禁用组合" in str(banned_pair.value.detail)
    assert "OP11-040" in str(banned_pair.value.detail)
    assert "OP08-069" in str(banned_pair.value.detail)

    leader, cards = _validate_deck_contents("ST01-001", {"OP01-016": 4})
    assert leader == "ST01-001"
    assert cards["OP01-016"] == 4
