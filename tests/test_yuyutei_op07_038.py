"""OP07-038-P2 EB-02 foil must take yuyu 99800, not a stale 248000."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sync_yuyutei_prices import (  # noqa: E402
    _needles_unique_in_family,
    _resolve_from_card_products,
)


class Dummy:
    pass


def _products() -> list[dict]:
    return [
        {
            "card_id": "OP07-038",
            "base_id": "OP07-038",
            "name": "ボア・ハンコック(パラレル)",
            "price": 12800,
            "kind": "parallel",
            "rarity": "P-L",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op07",
        },
        {
            "card_id": "OP07-038",
            "base_id": "OP07-038",
            "name": "ボア・ハンコック(パラレル/箔押し)",
            "price": 99800,
            "kind": "special",
            "rarity": "P-L",
            "in_stock": True,
            "image_url": "",
            "set_slug": "eb02",
        },
        {
            "card_id": "OP07-038",
            "base_id": "OP07-038",
            "name": "ボア・ハンコック",
            "price": 50,
            "kind": "base",
            "rarity": "L",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op07",
        },
    ]


def test_p2_eb02_foil_is_99800():
    assert any(n.upper().replace("-", "") == "EB02" for n in _needles_unique_in_family("OP07-038-P2"))
    products = _products()
    p2, p2_st = _resolve_from_card_products(Dummy(), products, "OP07-038-P2", allow_image_hash=False)
    p1, p1_st = _resolve_from_card_products(Dummy(), products, "OP07-038-P1", allow_image_hash=False)
    base, _ = _resolve_from_card_products(Dummy(), products, "OP07-038", allow_image_hash=False)
    assert base == 50
    assert p1 == 12800 and p1_st.startswith("ok")
    assert p2 == 99800 and p2_st.startswith("ok")


if __name__ == "__main__":
    test_p2_eb02_foil_is_99800()
    print("OK")
