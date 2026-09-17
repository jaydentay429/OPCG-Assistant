"""OP09-051 manga vs OP-14 silver SP must not share a stale 128000."""

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
            "card_id": "OP09-051",
            "base_id": "OP09-051",
            "name": "バギー(パラレル)",
            "price": 980,
            "kind": "parallel",
            "rarity": "P-R",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op09",
        },
        {
            "card_id": "OP09-051",
            "base_id": "OP09-051",
            "name": "バギー(パラレル)(スーパーパラレル)",
            "price": 99800,
            "kind": "special",
            "rarity": "P-R",
            "in_stock": False,
            "image_url": "",
            "set_slug": "op09",
        },
        {
            "card_id": "OP09-051",
            "base_id": "OP09-051",
            "name": "バギー",
            "price": 120,
            "kind": "base",
            "rarity": "R",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op09",
        },
        {
            "card_id": "OP09-051",
            "base_id": "OP09-051",
            "name": "バギー(パラレル)(金パラレル)",
            "price": 198000,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": False,
            "image_url": "",
            "set_slug": "op14",
        },
        {
            "card_id": "OP09-051",
            "base_id": "OP09-051",
            "name": "バギー(パラレル)(銀パラレル)",
            "price": 79800,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": False,
            "image_url": "",
            "set_slug": "op14",
        },
        {
            "card_id": "OP09-051",
            "base_id": "OP09-051",
            "name": "バギー(パラレル)",
            "price": 7980,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": False,
            "image_url": "",
            "set_slug": "op09",
        },
    ]


def test_manga_without_alt_name_and_silver_sp():
    assert _is_likely_manga_variant("OP09-051-P2")
    assert not _is_likely_manga_variant("OP09-051-P1")
    assert not _is_likely_manga_variant("OP09-051-P5")
    assert not _is_likely_manga_variant("OP09-051-P6")
    products = _products()
    session = Dummy()
    p2, p2_st = _resolve_from_card_products(session, products, "OP09-051-P2", allow_image_hash=False)
    p6, p6_st = _resolve_from_card_products(session, products, "OP09-051-P6", allow_image_hash=False)
    p1, _ = _resolve_from_card_products(session, products, "OP09-051-P1", allow_image_hash=False)
    p3, _ = _resolve_from_card_products(session, products, "OP09-051-P3", allow_image_hash=False)
    p5, _ = _resolve_from_card_products(session, products, "OP09-051-P5", allow_image_hash=False)
    assert p2 == 99800 and "manga" in p2_st
    assert p6 == 79800 and "gold_silver" in p6_st
    assert p1 == 980
    assert p3 == 7980
    assert p5 == 198000


if __name__ == "__main__":
    test_manga_without_alt_name_and_silver_sp()
    print("OK")
