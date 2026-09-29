"""Daily-report exclusion: cookie, account, user agent, datacenter IP, header."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.db import fetch_pageviews, init_analytics_db, insert_pageview  # noqa: E402
from analytics.exclude import (  # noqa: E402
    REASON_ACCOUNT,
    REASON_COOKIE,
    REASON_HEADER,
    REASON_IP,
    REASON_UA,
    TrafficSignals,
    datacenter_networks,
    exclusion_reasons,
    ip_is_datacenter,
    legacy_excluded,
)
from analytics.recount import format_report, parse_access_log, recount_rows, window_dates  # noqa: E402
from analytics.report import build_daily_report  # noqa: E402

CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
CUBOT = (
    "Mozilla/5.0 (Linux; Android 10; CUBOT_X30) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/83.0.4103.106 Mobile Safari/537.36"
)
HOME_IP = "198.51.100.10"


def _signals(**overrides) -> TrafficSignals:
    base = dict(
        visitor_id="visitor-normal",
        username="fan",
        email="fan@example.com",
        user_id=42,
        ip_hash="abc123",
        ip=HOME_IP,
        user_agent=CHROME,
        exclude_cookie=False,
        internal_header=False,
    )
    base.update(overrides)
    return TrafficSignals(**base)


def test_normal_visitor_is_counted():
    assert exclusion_reasons(_signals()) == ()
    assert ip_is_datacenter(HOME_IP) is False
    assert ip_is_datacenter("127.0.0.1") is False


def test_cookie_excludes_without_using_ip():
    reasons = exclusion_reasons(_signals(exclude_cookie=True, ip=HOME_IP))
    assert reasons[0] == REASON_COOKIE


def test_account_user_id_and_email(monkeypatch):
    monkeypatch.setenv("ANALYTICS_EXCLUDE_USER_IDS", "7, 42")
    monkeypatch.setenv("ANALYTICS_EXCLUDE_EMAILS", "owner@example.com")
    assert exclusion_reasons(_signals(user_id=7, email="other@example.com"))[0] == REASON_ACCOUNT
    assert exclusion_reasons(_signals(user_id=99, email="Owner@Example.com"))[0] == REASON_ACCOUNT
    assert exclusion_reasons(_signals(user_id=99, email="fan@example.com")) == ()


@pytest.mark.parametrize(
    "ua",
    [
        "Mozilla/5.0 HeadlessChrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36 Playwright",
        "Mozilla/5.0 puppeteer Chrome/120.0.0.0",
        "python-requests/2.32.3",
        "curl/8.5.0",
        "wget/1.21.4",
        "Go-http-client/1.1",
        "node-fetch/3.3.2",
        "axios/1.7.2",
        "undici",
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
        "Bytespider",
        "facebookexternalhit/1.1",
        "Slackbot-LinkExpanding 1.0 (preview)",
        "OPCG-Internal",
    ],
)
def test_machine_user_agents_are_excluded(ua: str):
    reasons = exclusion_reasons(_signals(user_agent=ua))
    assert REASON_UA in reasons


def test_cubot_phone_is_counted():
    assert exclusion_reasons(_signals(user_agent=CUBOT)) == ()


def test_datacenter_ip_and_extra_cidr(monkeypatch):
    nets = datacenter_networks()
    sample = next(net for net in nets if net.version == 4 and net.prefixlen < 32)
    inside = str(next(sample.hosts()))
    assert ip_is_datacenter(inside) is True
    assert exclusion_reasons(_signals(ip=inside))[0] == REASON_IP

    monkeypatch.setenv("ANALYTICS_DATACENTER_CIDRS_ONLY", "1")
    monkeypatch.setenv("ANALYTICS_DATACENTER_CIDRS", "203.0.113.0/24")
    assert ip_is_datacenter(inside) is False
    assert exclusion_reasons(_signals(ip="203.0.113.9"))[0] == REASON_IP
    assert exclusion_reasons(_signals(ip=HOME_IP)) == ()


def test_internal_header_excludes():
    reasons = exclusion_reasons(_signals(internal_header=True))
    assert reasons == (REASON_HEADER,)


def test_cookie_outranks_user_agent():
    reasons = exclusion_reasons(
        _signals(exclude_cookie=True, user_agent="python-requests/2.32.3")
    )
    assert reasons[0] == REASON_COOKIE


def test_legacy_rules_ignore_user_agent(monkeypatch):
    monkeypatch.setenv("ANALYTICS_EXCLUDE_VISITOR_IDS", "visitor-bot")
    signals = _signals(visitor_id="visitor-human", user_agent="curl/8.0.0")
    assert legacy_excluded(signals) is False
    assert REASON_UA in exclusion_reasons(signals)
    assert legacy_excluded(_signals(visitor_id="visitor-bot")) is True


def test_insert_and_report_honor_new_signals(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ANALYTICS_DB_FILE", str(tmp_path / "analytics.db"))
    monkeypatch.setenv("ANALYTICS_EXCLUDE_USER_IDS", "7")
    monkeypatch.delenv("ANALYTICS_EXCLUDE_EMAILS", raising=False)
    monkeypatch.delenv("ANALYTICS_EXCLUDE_VISITOR_IDS", raising=False)
    monkeypatch.delenv("ANALYTICS_EXCLUDE_USERNAMES", raising=False)
    monkeypatch.delenv("ANALYTICS_EXCLUDE_IP_HASHES", raising=False)
    init_analytics_db()
    when = datetime.now(timezone.utc) - timedelta(days=1)
    insert_pageview(
        path="/",
        visitor_id="human",
        session_id="s-human",
        user_agent=CHROME,
        ip=HOME_IP,
        ts=when,
    )
    insert_pageview(
        path="/",
        visitor_id="owner-cookie",
        session_id="s-cookie",
        user_agent=CHROME,
        ip=HOME_IP,
        exclude_cookie=True,
        ts=when,
    )
    insert_pageview(
        path="/",
        visitor_id="owner-account",
        session_id="s-account",
        user_id=7,
        username="owner",
        email="owner@example.com",
        user_agent=CHROME,
        ip=HOME_IP,
        ts=when,
    )
    insert_pageview(
        path="/",
        visitor_id="bot",
        session_id="s-bot",
        user_agent="curl/8.5.0",
        ip=HOME_IP,
        ts=when,
    )
    stored = fetch_pageviews("1970-01-01T00:00:00Z", "2999-01-01T00:00:00Z")
    flags = {row["visitor_id"]: int(row["is_excluded"]) for row in stored}
    assert flags["human"] == 0
    assert flags["owner-cookie"] == 1
    assert flags["owner-account"] == 1
    assert flags["bot"] == 1
    from zoneinfo import ZoneInfo

    hkt_day = when.astimezone(ZoneInfo("Asia/Hong_Kong")).date()
    _subject, body = build_daily_report(hkt_day)
    assert "独立访客 (UV)：1" in body
    assert "不计入我" in body
    assert "机器 User-Agent" in body
    assert "账号" in body


def test_recount_splits_old_and_new(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("ANALYTICS_EXCLUDE_VISITOR_IDS", raising=False)
    monkeypatch.delenv("ANALYTICS_EXCLUDE_USERNAMES", raising=False)
    monkeypatch.delenv("ANALYTICS_EXCLUDE_IP_HASHES", raising=False)
    monkeypatch.delenv("ANALYTICS_EXCLUDE_USER_IDS", raising=False)
    monkeypatch.delenv("ANALYTICS_EXCLUDE_EMAILS", raising=False)
    day = datetime(2026, 9, 28, 2, 0, tzinfo=timezone.utc)
    rows = [
        {
            "ts": day.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "visitor_id": "human",
            "username": None,
            "user_id": None,
            "email": None,
            "ip_hash": "h",
            "client_ip": HOME_IP,
            "user_agent": CHROME,
            "has_exclude_cookie": 0,
            "has_internal_header": 0,
        },
        {
            "ts": day.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "visitor_id": "bot",
            "username": None,
            "user_id": None,
            "email": None,
            "ip_hash": "b",
            "client_ip": HOME_IP,
            "user_agent": "curl/8.5.0",
            "has_exclude_cookie": 0,
            "has_internal_header": 0,
        },
    ]
    from datetime import date

    result = recount_rows(rows, days=[date(2026, 9, 28)], today=None)
    assert result.days[0].old_visitors == 2
    assert result.days[0].new_visitors == 1
    assert result.days[0].by_reason[REASON_UA] == 1
    text = format_report(result, source="fixture")
    assert "旧口径访客" in text
    assert "2026-09-28\t2\t1\t1" in text


def test_access_log_recount_uses_ip_and_ua():
    text = "\n".join(
        [
            '198.51.100.10 - - [28/Sep/2026:10:00:00 +0800] "GET / HTTP/1.1" 200 1 "-" "' + CHROME + '"',
            '198.51.100.11 - - [28/Sep/2026:10:05:00 +0800] "GET / HTTP/1.1" 200 1 "-" "curl/8.5.0"',
            "not a log line",
        ]
    )
    events, skipped = parse_access_log(text)
    assert skipped == 1
    from datetime import date

    result = recount_rows(events, days=[date(2026, 9, 28)])
    assert result.days[0].old_visitors == 2
    assert result.days[0].new_visitors == 1
    assert result.days[0].by_reason[REASON_UA] == 1


def test_old_schema_rows_cannot_invent_ua_hits():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE pageviews (
            ts TEXT, visitor_id TEXT, username TEXT, ip_hash TEXT, user_id INTEGER
        )
        """
    )
    conn.execute(
        "INSERT INTO pageviews (ts, visitor_id, username, ip_hash, user_id) VALUES (?, ?, ?, ?, ?)",
        ("2026-09-28T02:00:00Z", "human", None, "h", None),
    )
    row = conn.execute("SELECT * FROM pageviews").fetchone()
    assert exclusion_reasons(signals_from_row_of(row)) == ()


def signals_from_row_of(row):
    from analytics.exclude import signals_from_row

    return signals_from_row(row)


def test_window_dates_includes_today():
    now = datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc)
    days = window_dates(now, 7)
    assert len(days) == 7
    assert days[-1] == now.date()
    assert days[0] == now.date() - timedelta(days=6)
