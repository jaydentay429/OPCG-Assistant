"""OP13-042 family: SP reprint vs P-SR alt vs base SR must not share stale prices."""

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
            "card_id": "OP13-042",
            "base_id": "OP13-042",
            "name": "エドワード・ニューゲート(パラレル)",
            "price": 1280,
            "kind": "parallel",
            "rarity": "P-SR",
            "in_stock": True,
            "image_url": "https://card.yuyu-tei.jp/opc/100_140/op13/10052.jpg",
            "href": "https://yuyu-tei.jp/sell/opc/card/op13/10052",
            "set_slug": "op13",
        },
        {
            "card_id": "OP13-042",
            "base_id": "OP13-042",
            "name": "エドワード・ニューゲート",
            "price": 220,
            "kind": "base",
            "rarity": "SR",
            "in_stock": True,
            "image_url": "https://card.yuyu-tei.jp/opc/100_140/op13/10051.jpg",
            "href": "https://yuyu-tei.jp/sell/opc/card/op13/10051",
            "set_slug": "op13",
        },
        {
            "card_id": "OP13-042",
            "base_id": "OP13-042",
            "name": "エドワード・ニューゲート(パラレル)",
            "price": 9980,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": False,
            "image_url": "https://card.yuyu-tei.jp/opc/100_140/op15/10151.jpg",
            "href": "https://yuyu-tei.jp/sell/opc/card/op15/10151",
            "set_slug": "op15",
        },
    ]


def test_expected_sections():
    assert _expected_yuyu_section("OP13-042") == "SR"
    assert _expected_yuyu_section("OP13-042-P1") == "P-SR"
    assert _expected_yuyu_section("OP13-042-P2") == "SP"


def test_p2_unique_op15_needle():
    needles = _needles_unique_in_family("OP13-042-P2")
    assert any("OP-15" in n.upper() or n.upper().replace("-", "") == "OP15" for n in needles)


def test_sp_prb_not_blocked_by_same_set_reprint():
    needles = _needles_unique_in_family("OP05-091-P4")
    assert any("PRB-02" in n.upper() for n in needles)
    products = [
        {
            "card_id": "OP05-091",
            "base_id": "OP05-091",
            "name": "レベッカ(パラレル)(PRB2)",
            "price": 7980,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": False,
            "image_url": "",
            "set_slug": "prb02",
        },
        {
            "card_id": "OP05-091",
            "base_id": "OP05-091",
            "name": "レベッカ(パラレル)",
            "price": 9980,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": False,
            "image_url": "",
            "set_slug": "op06",
        },
    ]
    p2, p2_st = _resolve_from_card_products(Dummy(), products, "OP05-091-P2", allow_image_hash=False)
    p4, p4_st = _resolve_from_card_products(Dummy(), products, "OP05-091-P4", allow_image_hash=False)
    assert p2 == 9980 and p2_st.startswith("ok")
    assert p4 == 7980 and p4_st.startswith("ok")


def test_original_sp_unique_among_gold_silver_family():
    needles = _needles_unique_in_family("OP09-004-P3")
    assert any(n.upper().replace("-", "") == "OP09" for n in needles)
    products = [
        {
            "card_id": "OP09-004",
            "base_id": "OP09-004",
            "name": "シャンクス(パラレル)",
            "price": 12800,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op09",
        },
        {
            "card_id": "OP09-004",
            "base_id": "OP09-004",
            "name": "シャンクス(パラレル)(金パラレル)",
            "price": 128000,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op13",
        },
        {
            "card_id": "OP09-004",
            "base_id": "OP09-004",
            "name": "シャンクス(パラレル)(銀パラレル)",
            "price": 59800,
            "kind": "parallel",
            "rarity": "SP",
            "in_stock": True,
            "image_url": "",
            "set_slug": "op13",
        },
    ]
    p3, p3_st = _resolve_from_card_products(Dummy(), products, "OP09-004-P3", allow_image_hash=False)
    assert p3 == 12800 and p3_st.startswith("ok")
    p5, p5_st = _resolve_from_card_products(Dummy(), products, "OP09-004-P5", allow_image_hash=False)
    p6, p6_st = _resolve_from_card_products(Dummy(), products, "OP09-004-P6", allow_image_hash=False)
    assert p5 == 128000 and "gold_silver" in p5_st
    assert p6 == 59800 and "gold_silver" in p6_st


def test_live_shape_resolves_without_hash():
    products = _products()
    session = Dummy()
    base, base_st = _resolve_from_card_products(session, products, "OP13-042", allow_image_hash=False)
    p1, p1_st = _resolve_from_card_products(session, products, "OP13-042-P1", allow_image_hash=False)
    p2, p2_st = _resolve_from_card_products(session, products, "OP13-042-P2", allow_image_hash=False)
    assert (base, base_st.startswith("ok")) == (220, True)
    assert p1 == 1280
    assert "section_rarity" in p1_st or "set_name" in p1_st or "booster_parallel" in p1_st
    assert p2 == 9980
    assert p2_st.startswith("ok")


if __name__ == "__main__":
    test_expected_sections()
    test_p2_unique_op15_needle()
    test_live_shape_resolves_without_hash()
    test_sp_prb_not_blocked_by_same_set_reprint()
    test_original_sp_unique_among_gold_silver_family()
    print("OK")
