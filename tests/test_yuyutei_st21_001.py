"""ST21-001 family: don't mix reprint 980 onto the base kicking art."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sync_yuyutei_prices import (  # noqa: E402
    _needles_unique_in_family,
    _resolve_by_unique_set_name,
    _resolve_from_card_products,
    classify_listing_name,
)


def test_p2_matches_base_shop_listing():
    needles = _needles_unique_in_family("ST21-001-P2")
    assert any("BASE SHOP" in n.upper() for n in needles)
    products = [
        {
            "card_id": "ST21-001",
            "base_id": "ST21-001",
            "name": "モンキー・D・ルフィ",
            "price": 980,
            "kind": "base",
            "in_stock": True,
            "image_url": "",
        },
        {
            "card_id": "ST21-001",
            "base_id": "ST21-001",
            "name": "モンキー・D・ルフィ",
            "price": 1980,
            "kind": "base",
            "in_stock": True,
            "image_url": "",
        },
        {
            "card_id": "ST21-001",
            "base_id": "ST21-001",
            "name": "モンキー・D・ルフィ(パラレル)(BASE SHOPリミテッドカードコレクションvol.1)",
            "price": 2480,
            "kind": classify_listing_name(
                "モンキー・D・ルフィ(パラレル)(BASE SHOPリミテッドカードコレクションvol.1)"
            ),
            "in_stock": True,
            "image_url": "",
        },
    ]
    assert products[2]["kind"] == "parallel"
    assert _resolve_by_unique_set_name(products, "ST21-001-P2") == 2480
    class Dummy:
        pass

    price, status = _resolve_from_card_products(Dummy(), products, "ST21-001-P2", allow_image_hash=False)
    assert price == 2480
    assert "set_name" in status


def test_base_does_not_take_min_when_reprint_family_without_hash():
    products = [
        {
            "card_id": "ST21-001",
            "base_id": "ST21-001",
            "name": "モンキー・D・ルフィ",
            "price": 980,
            "kind": "base",
            "in_stock": True,
            "image_url": "",
        },
        {
            "card_id": "ST21-001",
            "base_id": "ST21-001",
            "name": "モンキー・D・ルフィ",
            "price": 1980,
            "kind": "base",
            "in_stock": True,
            "image_url": "",
        },
    ]
    class Dummy:
        pass

    price, status = _resolve_from_card_products(Dummy(), products, "ST21-001", allow_image_hash=False)
    # Without images we must not guess the cheaper reprint price onto the base.
    assert price is None
    assert status == "price_not_found"


if __name__ == "__main__":
    test_p2_matches_base_shop_listing()
    test_base_does_not_take_min_when_reprint_family_without_hash()
    print("OK")
