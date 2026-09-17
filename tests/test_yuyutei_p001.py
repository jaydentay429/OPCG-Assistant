"""Promo P-rarity: base P-001 vs named parallels must not share one miss."""

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
            "card_id": "P-001",
            "base_id": "P-001",
            "name": "モンキー・D・ルフィ",
            "price": 980,
            "kind": "base",
            "rarity": "P",
            "in_stock": True,
            "image_url": "",
            "set_slug": "promo-100",
        },
        {
            "card_id": "P-001",
            "base_id": "P-001",
            "name": "モンキー・D・ルフィ(パラレル)(25周年エディション)",
            "price": 5980,
            "kind": "parallel",
            "rarity": "P",
            "in_stock": True,
            "image_url": "",
            "set_slug": "promo-100",
        },
        {
            "card_id": "P-001",
            "base_id": "P-001",
            "name": "モンキー・D・ルフィ(パラレル)(チャンピオンシップ)",
            "price": 12800,
            "kind": "parallel",
            "rarity": "P",
            "in_stock": True,
            "image_url": "",
            "set_slug": "promo-100",
        },
        {
            "card_id": "P-001",
            "base_id": "P-001",
            "name": "モンキー・D・ルフィ(パラレル)(セブンイレブン)",
            "price": 1780,
            "kind": "parallel",
            "rarity": "P",
            "in_stock": True,
            "image_url": "",
            "set_slug": "promo-100",
        },
        {
            "card_id": "P-001",
            "base_id": "P-001",
            "name": "モンキー・D・ルフィ(パラレル)(BANDAI CARD GAMES Fest 23-24 Edition)",
            "price": 3980,
            "kind": "parallel",
            "rarity": "P",
            "in_stock": True,
            "image_url": "",
            "set_slug": "promo-100",
        },
    ]


def test_promo_section_is_p_not_pp():
    assert _expected_yuyu_section("P-001") == "P"
    assert _expected_yuyu_section("P-001-P1") == "P"
    assert _expected_yuyu_section("P-001-P4") == "P"


def test_promo_needles():
    assert any("25周年" in n for n in _needles_unique_in_family("P-001-P1"))
    assert any("セブンイレブン" in n for n in _needles_unique_in_family("P-001-P4"))
    assert any("チャンピオンシップ" in n for n in _needles_unique_in_family("P-001-P2"))


def test_p001_family_resolves_without_hash():
    products = _products()
    session = Dummy()
    base, base_st = _resolve_from_card_products(session, products, "P-001", allow_image_hash=False)
    p1, p1_st = _resolve_from_card_products(session, products, "P-001-P1", allow_image_hash=False)
    p2, p2_st = _resolve_from_card_products(session, products, "P-001-P2", allow_image_hash=False)
    p4, p4_st = _resolve_from_card_products(session, products, "P-001-P4", allow_image_hash=False)
    assert base == 980 and base_st.startswith("ok")
    assert p1 == 5980 and p1_st.startswith("ok")
    assert p2 == 12800 and p2_st.startswith("ok")
    assert p4 == 1780 and p4_st.startswith("ok")


if __name__ == "__main__":
    test_promo_section_is_p_not_pp()
    test_promo_needles()
    test_p001_family_resolves_without_hash()
    print("OK")
