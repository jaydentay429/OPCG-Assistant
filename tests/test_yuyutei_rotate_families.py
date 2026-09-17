"""Daily yuyu rotate: family expand, ghost prices, checkpoint skip, hard-miss clear."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sync_yuyutei_prices import (  # noqa: E402
    expand_family_members,
    is_hard_miss_status,
    merge_price_record,
    select_sync_card_ids,
)


def test_expand_family_writes_all_known_members(monkeypatch):
    monkeypatch.setattr(
        "sync_yuyutei_prices._known_family_ids",
        lambda base: {"OP07-038", "OP07-038-P1", "OP07-038-P2"},
    )
    families = {"OP07-038": ["OP07-038-P2"]}
    out = expand_family_members(families, enabled=True)
    assert out["OP07-038"][0] == "OP07-038-P2"
    assert set(out["OP07-038"]) == {"OP07-038", "OP07-038-P1", "OP07-038-P2"}
    skipped = expand_family_members(families, enabled=False)
    assert skipped["OP07-038"] == ["OP07-038-P2"]


def test_rotate_puts_ghost_and_miss_before_priced():
    cards = {
        "OP01-001": {
            "current_price": 50,
            "status": "ok_exact",
            "last_checked": "2026-09-14T00:00:00+00:00",
        },
        "OP07-038-P2": {
            "current_price": 248000,
            "status": "variant_not_found_strict",
            "last_checked": "2026-09-01T00:00:00+00:00",
        },
        "OP01-006-R1": {
            "current_price": None,
            "status": "variant_not_found_strict",
            "last_checked": "2026-08-04T00:00:00+00:00",
        },
    }
    ordered, _ = select_sync_card_ids(
        ["OP01-001", "OP07-038-P2", "OP01-006-R1"],
        cards,
        rotate_families=True,
    )
    assert ordered[0] == "OP07-038-P2"  # leftover yen + hard miss
    assert ordered[1] == "OP01-006-R1"  # unique-set miss, no price
    assert ordered[-1] == "OP01-001"


def test_rotate_skips_done_bases():
    cards = {
        "OP01-001": {"current_price": 50, "status": "ok_exact", "last_checked": "2026-09-14T00:00:00+00:00"},
        "OP01-002": {"current_price": 80, "status": "ok_exact", "last_checked": "2026-09-14T00:00:00+00:00"},
    }
    ordered, _ = select_sync_card_ids(
        ["OP01-001", "OP01-002"],
        cards,
        rotate_families=True,
        done_bases={"OP01-001"},
    )
    assert ordered == ["OP01-002"]


def test_merge_clears_hard_miss_but_keeps_429():
    old = {
        "current_price": 248000,
        "history": [{"ts": "2026-01-01T00:00:00+00:00", "price": 248000}],
    }
    cleared = merge_price_record(old, None, "2026-09-15T00:00:00+00:00", "https://yuyu-tei.jp/", clear_price=True)
    assert cleared["current_price"] is None
    assert cleared["history"][-1]["price"] == 248000

    kept = merge_price_record(old, None, "2026-09-15T00:00:00+00:00", "https://yuyu-tei.jp/", clear_price=False)
    assert kept["current_price"] == 248000


def test_hard_miss_includes_detail_status():
    assert is_hard_miss_status("variant_not_found_strict")
    assert is_hard_miss_status("detail_variant_not_found")
    assert is_hard_miss_status("price_not_found")
    assert not is_hard_miss_status("http_429")
    assert not is_hard_miss_status("ok_exact")


if __name__ == "__main__":
    class _Dummy:
        def setattr(self, *args, **kwargs):
            raise RuntimeError("run via pytest")

    print("run with pytest")
