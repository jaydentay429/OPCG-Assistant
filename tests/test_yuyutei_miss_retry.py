"""Avoidable yuyu misses: unique PRB reprints, Chinese promo needles, daily order."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sync_yuyutei_prices import (  # noqa: E402
    _distinctive_set_needles,
    _expected_yuyu_section,
    _needles_unique_in_family,
    _promo_listing_needles,
    _resolve_from_card_products,
    select_sync_card_ids,
)


class Dummy:
    pass


def test_chinese_promo_needles():
    packs = _promo_listing_needles("推廣卡包 Vol.6")
    assert any("プロモーションパックVol.6" in n for n in packs)
    sets = _promo_listing_needles("推廣卡套組2026")
    assert "プロモーションカードセット" in sets
    assert any("ファミリーデッキ" in n for n in _promo_listing_needles("家庭牌組套裝"))
    assert any("交流会" in n for n in _promo_listing_needles("2024年9月交流會紀念品"))
    assert any("始めようキャンペーン" in n for n in _promo_listing_needles("啟航活動推廣卡包"))
    assert any("スタンダードバトルパックVol.14" in n for n in _promo_listing_needles("常規賽卡包Vol.14"))


def test_prb_reprint_unique_needle():
    assert _expected_yuyu_section("OP01-006-R1") == "UC"
    assert any(n.upper().replace("-", "") == "PRB01" for n in _needles_unique_in_family("OP01-006-R1"))


def test_prb_reprint_resolves_without_hash():
    products = [
        {
            "card_id": "OP01-006",
            "base_id": "OP01-006",
            "name": "お玉(パラレル)",
            "price": 580,
            "kind": "parallel",
            "rarity": "P-UC",
            "in_stock": True,
            "image_url": "",
            "set_slug": "prb01",
        },
        {
            "card_id": "OP01-006",
            "base_id": "OP01-006",
            "name": "お玉(パラレル)(PRB)",
            "price": 1780,
            "kind": "parallel",
            "rarity": "P-UC",
            "in_stock": True,
            "image_url": "",
            "set_slug": "prb01",
        },
        {
            "card_id": "OP01-006",
            "base_id": "OP01-006",
            "name": "お玉(海賊旗フォイル)",
            "price": 220,
            "kind": "base",
            "rarity": "UC",
            "in_stock": True,
            "image_url": "",
            "set_slug": "prb01",
        },
        {
            "card_id": "OP01-006",
            "base_id": "OP01-006",
            "name": "お玉",
            "price": 120,
            "kind": "base",
            "rarity": "UC",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op01",
        },
    ]
    base, base_st = _resolve_from_card_products(Dummy(), products, "OP01-006", allow_image_hash=False)
    r1, r1_st = _resolve_from_card_products(Dummy(), products, "OP01-006-R1", allow_image_hash=False)
    assert base == 120 and base_st.startswith("ok")
    assert r1 == 220 and r1_st.startswith("ok")


def test_daily_puts_unique_miss_before_priced():
    cards = {
        "OP01-006": {
            "current_price": 120,
            "status": "ok_exact",
            "last_checked": "2026-09-14T00:00:00+00:00",
        },
        "OP01-006-R1": {
            "current_price": None,
            "status": "variant_not_found_strict",
            "last_checked": "2026-08-04T00:00:00+00:00",
        },
        "OP01-006-P1": {
            "current_price": None,
            "status": "variant_not_found_strict",
            "last_checked": "2026-08-04T00:00:00+00:00",
        },
    }
    ordered, _ = select_sync_card_ids(
        ["OP01-006", "OP01-006-P1", "OP01-006-R1"],
        cards,
        priced_or_new=True,
        miss_limit=0,
        priced_limit=10,
    )
    assert ordered[0] == "OP01-006-R1"
    assert "OP01-006" in ordered
    # Shared-PRB alts still need hash; do not spend the daily miss budget on them
    # when miss_limit is 0.
    assert "OP01-006-P1" not in ordered


def test_promo_pack_needles_on_index_row():
    needles = _distinctive_set_needles("OP01-015-P1")
    assert any("プロモーションパックVol.6" in n for n in needles)


if __name__ == "__main__":
    test_chinese_promo_needles()
    test_prb_reprint_unique_needle()
    test_prb_reprint_resolves_without_hash()
    test_daily_puts_unique_miss_before_priced()
    test_promo_pack_needles_on_index_row()
    print("OK")
