"""OP05-119-P3 PRB reprint must take yuyu (PRB) 7980, not a stale 12800."""

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
            "card_id": "OP05-119",
            "base_id": "OP05-119",
            "name": "モンキー・D・ルフィ(パラレル)(PRB)",
            "price": 7980,
            "kind": "parallel",
            "rarity": "P-SEC",
            "in_stock": True,
            "image_url": "",
            "set_slug": "prb01",
        },
        {
            "card_id": "OP05-119",
            "base_id": "OP05-119",
            "name": "モンキー・D・ルフィ(パラレル)",
            "price": 29800,
            "kind": "parallel",
            "rarity": "P-SEC",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op05",
        },
        {
            "card_id": "OP05-119",
            "base_id": "OP05-119",
            "name": "モンキー・D・ルフィ(パラレル)(スーパーパラレル)",
            "price": 798000,
            "kind": "special",
            "rarity": "P-SEC",
            "in_stock": False,
            "image_url": "",
            "set_slug": "op05",
        },
        {
            "card_id": "OP05-119",
            "base_id": "OP05-119",
            "name": "モンキー・D・ルフィ",
            "price": 780,
            "kind": "base",
            "rarity": "SEC",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op05",
        },
        {
            "card_id": "OP05-119",
            "base_id": "OP05-119",
            "name": "モンキー・D・ルフィ(パラレル)(English 2nd Anniversary set日本語版)",
            "price": 19800,
            "kind": "parallel",
            "rarity": "SEC",
            "in_stock": True,
            "image_url": "",
            "set_slug": "promo-op10",
        },
        {
            "card_id": "OP05-119",
            "base_id": "OP05-119",
            "name": "モンキー・D・ルフィ(パラレル)",
            "price": 59800,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op09",
        },
        {
            "card_id": "OP05-119",
            "base_id": "OP05-119",
            "name": "モンキー・D・ルフィ(パラレル)(金パラレル)",
            "price": 1280000,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": False,
            "image_url": "",
            "set_slug": "op11",
        },
        {
            "card_id": "OP05-119",
            "base_id": "OP05-119",
            "name": "モンキー・D・ルフィ(パラレル)(銀パラレル)",
            "price": 498000,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": False,
            "image_url": "",
            "set_slug": "op11",
        },
    ]


def test_p3_prb_section_and_needle():
    assert _expected_yuyu_section("OP05-119") == "SEC"
    assert _expected_yuyu_section("OP05-119-P3") == "P-SEC"
    assert _expected_yuyu_section("OP05-119-R1") == "SEC"
    assert any(n.upper().replace("-", "") == "PRB01" for n in _needles_unique_in_family("OP05-119-P3"))


def test_family_prices_without_hash():
    products = _products()
    session = Dummy()
    base, _ = _resolve_from_card_products(session, products, "OP05-119", allow_image_hash=False)
    p1, _ = _resolve_from_card_products(session, products, "OP05-119-P1", allow_image_hash=False)
    p2, _ = _resolve_from_card_products(session, products, "OP05-119-P2", allow_image_hash=False)
    p3, p3_st = _resolve_from_card_products(session, products, "OP05-119-P3", allow_image_hash=False)
    p5, _ = _resolve_from_card_products(session, products, "OP05-119-P5", allow_image_hash=False)
    p6, p6_st = _resolve_from_card_products(session, products, "OP05-119-P6", allow_image_hash=False)
    p7, p7_st = _resolve_from_card_products(session, products, "OP05-119-P7", allow_image_hash=False)
    p8, _ = _resolve_from_card_products(session, products, "OP05-119-P8", allow_image_hash=False)
    assert base == 780
    assert p1 == 29800
    assert p2 == 798000
    assert p3 == 7980 and p3_st.startswith("ok")
    assert p5 == 59800
    assert p6 == 498000 and "gold_silver" in p6_st
    assert p7 == 1280000 and "gold_silver" in p7_st
    assert p8 == 19800


if __name__ == "__main__":
    test_p3_prb_section_and_needle()
    test_family_prices_without_hash()
    print("OK")
