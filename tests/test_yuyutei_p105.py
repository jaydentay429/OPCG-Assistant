"""P-105-P2 OP-15 SP must take yuyu 5980, not stay unpriced."""

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
            "card_id": "P-105",
            "base_id": "P-105",
            "name": "サボ(パラレル)",
            "price": 5980,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": False,
            "image_url": "",
            "set_slug": "op15",
        },
        {
            "card_id": "P-105",
            "base_id": "P-105",
            "name": "サボ(プロモーションカードセット2025ゲットキャンペーン)",
            "price": 220,
            "kind": "base",
            "rarity": "P",
            "in_stock": True,
            "image_url": "",
            "set_slug": "promo-200",
        },
        {
            "card_id": "P-105",
            "base_id": "P-105",
            "name": "サボ(パラレル)",
            "price": 120,
            "kind": "parallel",
            "rarity": "P",
            "in_stock": True,
            "image_url": "",
            "set_slug": "promo-200",
        },
    ]


def test_p2_op15_sp():
    assert _expected_yuyu_section("P-105-P2") == "SP"
    assert any(n.upper().replace("-", "") == "OP15" for n in _needles_unique_in_family("P-105-P2"))
    p2, p2_st = _resolve_from_card_products(Dummy(), _products(), "P-105-P2", allow_image_hash=False)
    assert p2 == 5980 and p2_st.startswith("ok")


if __name__ == "__main__":
    test_p2_op15_sp()
    print("OK")
