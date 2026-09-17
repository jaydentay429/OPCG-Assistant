"""OP08-001-P2 EB-02 foil must take yuyu 59800, not a stale 148000."""

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
            "card_id": "OP08-001",
            "base_id": "OP08-001",
            "name": "トニートニー・チョッパー(パラレル)",
            "price": 3980,
            "kind": "parallel",
            "rarity": "P-L",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op08",
        },
        {
            "card_id": "OP08-001",
            "base_id": "OP08-001",
            "name": "トニートニー・チョッパー(パラレル/箔押し)",
            "price": 59800,
            "kind": "special",
            "rarity": "P-L",
            "in_stock": True,
            "image_url": "",
            "set_slug": "eb02",
        },
        {
            "card_id": "OP08-001",
            "base_id": "OP08-001",
            "name": "トニートニー・チョッパー",
            "price": 50,
            "kind": "base",
            "rarity": "L",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op08",
        },
        {
            "card_id": "OP08-001",
            "base_id": "OP08-001",
            "name": "トニートニー・チョッパー(パラレル)(BASE SHOPリミテッドカードコレクションvol.1)",
            "price": 1280,
            "kind": "parallel",
            "rarity": "L",
            "in_stock": True,
            "image_url": "",
            "set_slug": "promo-op10",
        },
    ]


def test_p2_eb02_foil_is_59800():
    assert any(n.upper().replace("-", "") == "EB02" for n in _needles_unique_in_family("OP08-001-P2"))
    products = _products()
    p2, p2_st = _resolve_from_card_products(Dummy(), products, "OP08-001-P2", allow_image_hash=False)
    p1, _ = _resolve_from_card_products(Dummy(), products, "OP08-001-P1", allow_image_hash=False)
    p3, _ = _resolve_from_card_products(Dummy(), products, "OP08-001-P3", allow_image_hash=False)
    base, _ = _resolve_from_card_products(Dummy(), products, "OP08-001", allow_image_hash=False)
    assert base == 50
    assert p1 == 3980
    assert p2 == 59800 and p2_st.startswith("ok")
    assert p3 == 1280


if __name__ == "__main__":
    test_p2_eb02_foil_is_59800()
    print("OK")
