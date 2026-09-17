"""ST31-004-P1 OP-17 SP must take yuyu 99800, not stay unpriced."""

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
            "card_id": "ST31-004",
            "base_id": "ST31-004",
            "name": "モンキー・D・ルフィ",
            "price": 220,
            "kind": "base",
            "rarity": "SR",
            "in_stock": True,
            "image_url": "",
            "set_slug": "st31",
        },
        {
            "card_id": "ST31-004",
            "base_id": "ST31-004",
            "name": "モンキー・D・ルフィ(パラレル)",
            "price": 99800,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op17",
        },
    ]


def test_p1_op17_sp():
    assert _expected_yuyu_section("ST31-004") == "SR"
    assert _expected_yuyu_section("ST31-004-P1") == "SP"
    assert any(n.upper().replace("-", "") == "OP17" for n in _needles_unique_in_family("ST31-004-P1"))
    products = _products()
    base, _ = _resolve_from_card_products(Dummy(), products, "ST31-004", allow_image_hash=False)
    p1, p1_st = _resolve_from_card_products(Dummy(), products, "ST31-004-P1", allow_image_hash=False)
    assert base == 220
    assert p1 == 99800 and p1_st.startswith("ok")


if __name__ == "__main__":
    test_p1_op17_sp()
    print("OK")
