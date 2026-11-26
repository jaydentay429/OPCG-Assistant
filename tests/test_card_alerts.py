import json
import sqlite3

import card_alerts


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_opt_in_watchlist_and_unsubscribe():
    conn = _conn()
    assert card_alerts.get_settings(conn, 7)["new_cards"] is False
    s = card_alerts.set_settings(conn, 7, new_cards=True, price_watch=True, lang="en")
    assert s["new_cards"] and s["price_watch"] and s["lang"] == "en"
    assert card_alerts.set_watchlist(conn, 7, ["op01-001", "OP01-001", "ST01-001"]) == 2
    conn.execute("UPDATE card_alert_watch SET last_notified_price = 500 WHERE card_id = 'OP01-001'")
    assert card_alerts.set_watchlist(conn, 7, ["OP01-001"]) == 1
    row = conn.execute("SELECT last_notified_price FROM card_alert_watch WHERE card_id='OP01-001'").fetchone()
    assert row[0] == 500  # kept ids keep their baseline
    token = conn.execute("SELECT unsubscribe_token FROM card_alert_prefs").fetchone()[0]
    assert card_alerts.unsubscribe(conn, "nope") is None
    assert card_alerts.unsubscribe(conn, token, "price_watch") == {"new_cards": True, "price_watch": False}
    assert card_alerts.unsubscribe(conn, token) == {"new_cards": False, "price_watch": False}


def test_price_moves_baseline_and_threshold():
    rows = [
        {"card_id": "A", "last_notified_price": None},
        {"card_id": "B", "last_notified_price": 1000},
        {"card_id": "C", "last_notified_price": 1000},
        {"card_id": "D", "last_notified_price": 1000},
    ]
    prices = {"A": {"current_price": 300}, "B": {"current_price": 1050}, "C": {"current_price": 850}}
    changes, baselines = card_alerts.price_moves(rows, prices, 10)
    assert baselines == [("A", 300)]
    assert changes == [{"card_id": "C", "old": 1000, "new": 850, "pct": -15.0}]


def test_new_cards_first_run_records_only(tmp_path):
    state = tmp_path / "s.json"
    assert card_alerts.detect_new_cards(["A", "B"], state) == ([], True)
    card_alerts.save_known_cards(["A", "B"], state)
    assert card_alerts.detect_new_cards(["A", "B", "C"], state) == (["C"], False)
    assert json.loads(state.read_text())["known_ids"] == ["A", "B"]


def test_email_has_unsubscribe_and_language_links():
    subject, text, html = card_alerts.build_email(
        lang="en", username="sam", site_url="https://x.test/", token="tok",
        new_cards=[("OP15-001", "Luffy")], new_total=3,
        changes=[{"card_id": "OP01-001", "old": 1000, "new": 1200, "pct": 20.0}],
    )
    assert subject == "OPCG Card Assistant: 3 new cards, 1 price changes"
    assert "https://x.test/en/cards/OP15-001" in text
    assert "https://x.test/alerts/unsubscribe?token=tok" in text and "tok" in html
    assert "+20.0%" in text


def test_feature_flag(monkeypatch):
    monkeypatch.delenv(card_alerts.FEATURE_ENV, raising=False)
    assert card_alerts.feature_enabled() is False
    monkeypatch.setenv(card_alerts.FEATURE_ENV, "1")
    assert card_alerts.feature_enabled() is True


def test_api_endpoints_respect_flag(monkeypatch, tmp_path):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import pytest
    from fastapi import HTTPException

    import app

    db = tmp_path / "auth.db"
    monkeypatch.setattr(app, "AUTH_DB_FILE", db)
    user = {"id": 3, "username": "u", "email": "u@x", "email_verified": 1, "is_admin": 0}
    monkeypatch.setattr(app, "_require_auth_user", lambda request: user)
    monkeypatch.delenv(card_alerts.FEATURE_ENV, raising=False)

    got = app.card_alert_settings(None)
    assert got["feature_enabled"] is False and got["email_verified"] is True
    with pytest.raises(HTTPException) as err:
        app.update_card_alert_settings(None, app.CardAlertSettingsRequest(new_cards=True))
    assert err.value.status_code == 503

    monkeypatch.setenv(card_alerts.FEATURE_ENV, "1")
    got = app.update_card_alert_settings(None, app.CardAlertSettingsRequest(new_cards=True, lang="zh-Hans"))
    assert got["new_cards"] is True and got["lang"] == "zh-Hans"
    assert app.update_card_alert_watchlist(None, app.CardAlertWatchlistRequest(card_ids=["op01-001"]))["watch_count"] == 1
    with pytest.raises(HTTPException):
        app.card_alert_unsubscribe(app.CardAlertUnsubscribeRequest(token="bad"))
    conn = sqlite3.connect(db)
    token = conn.execute("SELECT unsubscribe_token FROM card_alert_prefs").fetchone()[0]
    conn.close()
    assert app.card_alert_unsubscribe(app.CardAlertUnsubscribeRequest(token=token))["new_cards"] is False
