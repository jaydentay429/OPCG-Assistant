"""OP09-093-P2 manga must take yuyu 148000, not a stale 178000."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sync_yuyutei_prices import (  # noqa: E402
    _is_likely_manga_variant,
    _resolve_from_card_products,
)


class Dummy:
    pass


def _products() -> list[dict]:
    return [
        {
            "card_id": "OP09-093",
            "base_id": "OP09-093",
            "name": "マーシャル・D・ティーチ(パラレル)",
            "price": 980,
            "kind": "parallel",
            "rarity": "P-SR",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op09",
        },
        {
            "card_id": "OP09-093",
            "base_id": "OP09-093",
            "name": "マーシャル・D・ティーチ(パラレル)(スーパーパラレル)",
            "price": 148000,
            "kind": "special",
            "rarity": "P-SR",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op09",
        },
        {
            "card_id": "OP09-093",
            "base_id": "OP09-093",
            "name": "マーシャル・D・ティーチ",
            "price": 120,
            "kind": "base",
            "rarity": "SR",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op09",
        },
        {
            "card_id": "OP09-093",
            "base_id": "OP09-093",
            "name": "マーシャル・D・ティーチ(パラレル)(金パラレル)",
            "price": 148000,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": False,
            "image_url": "",
            "set_slug": "op12",
        },
        {
            "card_id": "OP09-093",
            "base_id": "OP09-093",
            "name": "マーシャル・D・ティーチ(パラレル)(銀パラレル)",
            "price": 79800,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": False,
            "image_url": "",
            "set_slug": "op12",
        },
        {
            "card_id": "OP09-093",
            "base_id": "OP09-093",
            "name": "マーシャル・D・ティーチ(パラレル)",
            "price": 12800,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op09",
        },
    ]


def test_manga_is_148000_not_stale_gold():
    assert _is_likely_manga_variant("OP09-093-P2")
    assert not _is_likely_manga_variant("OP09-093-P1")
    products = _products()
    p2, p2_st = _resolve_from_card_products(Dummy(), products, "OP09-093-P2", allow_image_hash=False)
    p1, _ = _resolve_from_card_products(Dummy(), products, "OP09-093-P1", allow_image_hash=False)
    p3, _ = _resolve_from_card_products(Dummy(), products, "OP09-093-P3", allow_image_hash=False)
    assert p2 == 148000 and "manga" in p2_st
    assert p1 == 980
    assert p3 == 12800


if __name__ == "__main__":
    test_manga_is_148000_not_stale_gold()
    print("OK")
