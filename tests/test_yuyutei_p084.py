"""P-084-P1 OP-17 SP must take yuyu 19800, not stay unpriced."""

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
            "card_id": "P-084",
            "base_id": "P-084",
            "name": "バギー(パラレル)",
            "price": 19800,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op17",
        },
        {
            "card_id": "P-084",
            "base_id": "P-084",
            "name": "バギー(ホロなし)",
            "price": 50,
            "kind": "base",
            "rarity": "P",
            "in_stock": True,
            "image_url": "",
            "set_slug": "st25",
        },
        {
            "card_id": "P-084",
            "base_id": "P-084",
            "name": "バギー(週刊少年ジャンプ付録)",
            "price": 120,
            "kind": "base",
            "rarity": "P",
            "in_stock": True,
            "image_url": "",
            "set_slug": "promo-100",
        },
    ]


def test_p1_op17_sp():
    assert _expected_yuyu_section("P-084-P1") == "SP"
    assert any(n.upper().replace("-", "") == "OP17" for n in _needles_unique_in_family("P-084-P1"))
    p1, p1_st = _resolve_from_card_products(Dummy(), _products(), "P-084-P1", allow_image_hash=False)
    assert p1 == 19800 and p1_st.startswith("ok")


if __name__ == "__main__":
    test_p1_op17_sp()
    print("OK")
