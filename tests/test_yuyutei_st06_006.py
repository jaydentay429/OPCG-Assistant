"""ST06-006-P2 OP-08 SP must take yuyu 5980, not stay unpriced."""

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
            "card_id": "ST06-006",
            "base_id": "ST06-006",
            "name": "たしぎ",
            "price": 120,
            "kind": "base",
            "rarity": "C",
            "in_stock": True,
            "image_url": "",
            "set_slug": "st06",
        },
        {
            "card_id": "ST06-006",
            "base_id": "ST06-006",
            "name": "たしぎ(パラレル)(スタンダードバトルパック2022 Vol.2)",
            "price": 320,
            "kind": "parallel",
            "rarity": "C",
            "in_stock": True,
            "image_url": "",
            "set_slug": "promo-st10",
        },
        {
            "card_id": "ST06-006",
            "base_id": "ST06-006",
            "name": "たしぎ(パラレル)",
            "price": 5980,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": False,
            "image_url": "",
            "set_slug": "op08",
        },
    ]


def test_p2_op08_sp():
    assert _expected_yuyu_section("ST06-006-P2") == "SP"
    assert any(n.upper().replace("-", "") == "OP08" for n in _needles_unique_in_family("ST06-006-P2"))
    products = _products()
    p2, p2_st = _resolve_from_card_products(Dummy(), products, "ST06-006-P2", allow_image_hash=False)
    p1, _ = _resolve_from_card_products(Dummy(), products, "ST06-006-P1", allow_image_hash=False)
    base, _ = _resolve_from_card_products(Dummy(), products, "ST06-006", allow_image_hash=False)
    assert base == 120
    assert p1 == 320
    assert p2 == 5980 and p2_st.startswith("ok")


if __name__ == "__main__":
    test_p2_op08_sp()
    print("OK")
