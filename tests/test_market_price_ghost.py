"""API must hide leftover yen prices after a hard yuyu miss; 429 keeps the old price."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import get_market_price_info, visible_market_current_price  # noqa: E402
import app as appmod  # noqa: E402


def test_visible_price_hides_hard_miss_keeps_429():
    miss = {"current_price": 198000, "status": "variant_not_found_strict"}
    assert visible_market_current_price(miss) is None
    busy = {"current_price": 59800, "status": "http_429"}
    assert visible_market_current_price(busy) == 59800
    ok = {"current_price": 50, "status": "ok_exact"}
    assert visible_market_current_price(ok) == 50


def test_get_market_price_info_nulls_ghost(monkeypatch):
    monkeypatch.setattr(appmod, "ensure_market_price_data_fresh", lambda: None)
    appmod.market_price_map = {
        "EB01-006-R1": {
            "current_price": 198000,
            "status": "variant_not_found_strict",
            "history": [{"ts": "2026-01-01T00:00:00+00:00", "price": 198000}],
            "source": "yuyu-tei",
            "currency": "JPY",
            "last_seen": "2026-01-01T00:00:00+00:00",
            "last_checked": "2026-09-15T00:00:00+00:00",
        }
    }
    info = get_market_price_info("EB01-006-R1", exact=True)
    assert info is not None
    assert info["current_price"] is None
