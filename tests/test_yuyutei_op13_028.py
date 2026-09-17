"""OP13-028-P2 OP-17 SP must take yuyu 34800, not stay unpriced."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sync_yuyutei_prices import (  # noqa: E402
    _expected_yuyu_section,
    _needles_unique_in_family,
    _resolve_from_card_products,
)


class Dummy:
    pass


def _products() -> list[dict]:
    return [
        {
            "card_id": "OP13-028",
            "base_id": "OP13-028",
            "name": "シャンクス(パラレル)",
            "price": 1280,
            "kind": "parallel",
            "rarity": "P-SR",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op13",
        },
        {
            "card_id": "OP13-028",
            "base_id": "OP13-028",
            "name": "シャンクス",
            "price": 320,
            "kind": "base",
            "rarity": "SR",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op13",
        },
        {
            "card_id": "OP13-028",
            "base_id": "OP13-028",
            "name": "シャンクス(パラレル)",
            "price": 34800,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op17",
        },
    ]


def test_p2_op17_sp():
    assert _expected_yuyu_section("OP13-028-P2") == "SP"
    assert any(n.upper().replace("-", "") == "OP17" for n in _needles_unique_in_family("OP13-028-P2"))
    products = _products()
    p2, p2_st = _resolve_from_card_products(Dummy(), products, "OP13-028-P2", allow_image_hash=False)
    p1, _ = _resolve_from_card_products(Dummy(), products, "OP13-028-P1", allow_image_hash=False)
    base, _ = _resolve_from_card_products(Dummy(), products, "OP13-028", allow_image_hash=False)
    assert base == 320
    assert p1 == 1280
    assert p2 == 34800 and p2_st.startswith("ok")


if __name__ == "__main__":
    test_p2_op17_sp()
    print("OK")
