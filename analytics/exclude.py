"""Decide whether one pageview counts in the daily traffic report.

Page behavior is unchanged. This module only marks hits the digest should skip.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any, Iterable, Mapping

# Cookie set by the unlisted exclude-me page. Value is fixed; the token never
# travels on later requests.
EXCLUDE_COOKIE_NAME = "opcg_exclude_me"
EXCLUDE_COOKIE_VALUE = "1"

# QA / agents send either this header or a User-Agent containing the marker.
INTERNAL_HEADER_NAME = "x-opcg-internal"
INTERNAL_HEADER_VALUE = "1"
INTERNAL_UA_MARKER = "opcg-internal"

REASON_HEADER = "header"
REASON_COOKIE = "cookie"
REASON_ACCOUNT = "account"
REASON_UA = "ua"
REASON_IP = "ip"
REASON_VISITOR_ID = "visitor_id"
REASON_IP_HASH = "ip_hash"

# Stable order. The first match is the primary reason in the digest.
_REASON_ORDER = (
    REASON_HEADER,
    REASON_COOKIE,
    REASON_ACCOUNT,
    REASON_UA,
    REASON_IP,
    REASON_VISITOR_ID,
    REASON_IP_HASH,
)

REASON_LABELS = {
    REASON_HEADER: "内部请求头",
    REASON_COOKIE: "不计入我",
    REASON_ACCOUNT: "账号",
    REASON_UA: "机器 User-Agent",
    REASON_IP: "数据中心 IP",
    REASON_VISITOR_ID: "visitor_id 名单",
    REASON_IP_HASH: "ip_hash 名单",
}

_DEFAULT_CIDR_FILE = Path(__file__).resolve().parent / "datacenter_cidrs.txt"

# Named clients that do not always contain bot/crawler/spider/preview.
_UA_SUBSTRINGS = (
    "headlesschrome",
    "playwright",
    "puppeteer",
    "python-requests",
    "go-http-client",
    "node-fetch",
    "axios",
    "undici",
    INTERNAL_UA_MARKER,
    "facebookexternalhit",
    "whatsapp",
    "embedly",
    "iframely",
    "libcurl",
)
# curl/wget as their own token. "libcurl" is listed above.
_CURL_WGET = re.compile(r"(?:^|[^a-z])(?:curl|wget)(?:[^a-z]|$)", re.I)
# Suffix/word so "Googlebot" matches and "CUBOT_X30" does not (`_` is a word char).
_BOT_WORD = re.compile(r"\w*(?:bot|crawler|spider)\b", re.I)
_PREVIEW = re.compile(r"preview", re.I)

_network_cache_key: tuple[str, str, str] | None = None
_network_cache: tuple[Any, ...] | None = None


@dataclass(frozen=True)
class TrafficSignals:
    visitor_id: str = ""
    username: str | None = None
    email: str | None = None
    user_id: int | str | None = None
    ip_hash: str | None = None
    # In-memory only, at insert time. Stored rows do not carry a raw IP.
    ip: str | None = None
    # Frozen at insert. Recount uses this and does not match CIDRs again.
    ip_is_datacenter: bool = False
    user_agent: str | None = None
    exclude_cookie: bool = False
    internal_header: bool = False


def _csv_set(env_key: str) -> set[str]:
    raw = str(os.getenv(env_key) or "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def _row_keys(row: Any) -> set[str] | None:
    keys = getattr(row, "keys", None)
    if callable(keys):
        try:
            return set(keys())
        except Exception:
            return None
    if isinstance(row, Mapping):
        return set(row.keys())
    return None


def _row_get(row: Any, name: str, default: Any = None) -> Any:
    keys = _row_keys(row)
    if keys is not None and name not in keys:
        return default
    try:
        value = row[name]
    except Exception:
        return default
    return default if value is None else value


def _flag(value: Any) -> bool:
    try:
        return int(value or 0) == 1
    except (TypeError, ValueError):
        return str(value).strip() == "1"


def signals_from_row(
    row: Any,
    email_by_user_id: Mapping[int, str] | None = None,
) -> TrafficSignals:
    """Build signals from a pageviews row.

    Email comes only from the auth.db lookup keyed by user_id. A leftover
    email or client_ip column on an older database is ignored.
    """
    user_id = _row_get(row, "user_id")
    email = None
    if email_by_user_id and user_id is not None and str(user_id).strip() != "":
        try:
            email = str(email_by_user_id.get(int(user_id)) or "").strip() or None
        except (TypeError, ValueError):
            email = None
    return TrafficSignals(
        visitor_id=str(_row_get(row, "visitor_id") or ""),
        username=(str(_row_get(row, "username")).strip() if _row_get(row, "username") else None),
        email=email,
        user_id=user_id,
        ip_hash=(str(_row_get(row, "ip_hash")).strip() if _row_get(row, "ip_hash") else None),
        ip=None,
        ip_is_datacenter=_flag(_row_get(row, "ip_is_datacenter", 0)),
        user_agent=(str(_row_get(row, "user_agent")).strip() if _row_get(row, "user_agent") else None),
        exclude_cookie=_flag(_row_get(row, "has_exclude_cookie", 0)),
        internal_header=_flag(_row_get(row, "has_internal_header", 0)),
    )


def ua_is_machine(user_agent: str | None) -> bool:
    """True for automated clients. Search engines match too; they may still crawl."""
    ua = str(user_agent or "").strip()
    if not ua:
        return False
    lowered = ua.lower()
    if any(needle in lowered for needle in _UA_SUBSTRINGS):
        return True
    if _CURL_WGET.search(ua) or _BOT_WORD.search(ua) or _PREVIEW.search(ua):
        return True
    return False


def _parse_networks(items: Iterable[str]) -> list[Any]:
    nets: list[Any] = []
    for raw in items:
        text = str(raw or "").strip()
        if not text or text.startswith("#"):
            continue
        # Allow "a,b" leftovers and host/mask with a trailing comment.
        text = text.split("#", 1)[0].strip().split()[0].strip().rstrip(",")
        if not text:
            continue
        try:
            nets.append(ip_network(text, strict=False))
        except ValueError:
            continue
    return nets


def _cidr_file_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def datacenter_networks() -> tuple[Any, ...]:
    """Built-in snapshot plus optional env/file extras. Cached on the env values."""
    global _network_cache_key, _network_cache
    only = str(os.getenv("ANALYTICS_DATACENTER_CIDRS_ONLY") or "").strip()
    extra = str(os.getenv("ANALYTICS_DATACENTER_CIDRS") or "")
    file_override = str(os.getenv("ANALYTICS_DATACENTER_CIDRS_FILE") or "").strip()
    key = (only, extra, file_override)
    if _network_cache_key == key and _network_cache is not None:
        return _network_cache
    lines: list[str] = []
    if only not in {"1", "true", "yes", "on"}:
        lines.extend(_cidr_file_lines(_DEFAULT_CIDR_FILE))
    if file_override:
        lines.extend(_cidr_file_lines(Path(file_override)))
    if extra.strip():
        lines.extend(part.strip() for part in extra.split(","))
    nets = tuple(_parse_networks(lines))
    _network_cache_key = key
    _network_cache = nets
    return nets


def ip_is_datacenter(ip: str | None) -> bool:
    text = str(ip or "").strip()
    if not text:
        return False
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    # Drop a trailing port on IPv4 only. IPv6 with a port is rare here.
    if text.count(":") == 1 and "." in text:
        text = text.split(":", 1)[0]
    try:
        addr = ip_address(text)
    except ValueError:
        return False
    for net in datacenter_networks():
        if addr.version == net.version and addr in net:
            return True
    return False


def _account_excluded(signals: TrafficSignals) -> bool:
    user_ids = _csv_set("ANALYTICS_EXCLUDE_USER_IDS")
    uid = str(signals.user_id).strip() if signals.user_id is not None else ""
    if uid and uid in user_ids:
        return True
    emails = {item.lower() for item in _csv_set("ANALYTICS_EXCLUDE_EMAILS")}
    email = str(signals.email or "").strip().lower()
    if email and email in emails:
        return True
    names = _csv_set("ANALYTICS_EXCLUDE_USERNAMES")
    username = str(signals.username or "").strip()
    if username and (username in names or username.lower() in {item.lower() for item in names}):
        return True
    return False


def legacy_excluded(signals: TrafficSignals) -> bool:
    """Previous digest rules: visitor id, username, and ip hash lists only."""
    visitor_id = str(signals.visitor_id or "").strip()
    if visitor_id and visitor_id in _csv_set("ANALYTICS_EXCLUDE_VISITOR_IDS"):
        return True
    names = _csv_set("ANALYTICS_EXCLUDE_USERNAMES")
    username = str(signals.username or "").strip()
    if username and (username in names or username.lower() in {item.lower() for item in names}):
        return True
    ip_hash = str(signals.ip_hash or "").strip()
    if ip_hash and ip_hash in _csv_set("ANALYTICS_EXCLUDE_IP_HASHES"):
        return True
    return False


def exclusion_reasons(signals: TrafficSignals) -> tuple[str, ...]:
    """Reason codes, highest priority first. Empty means the hit counts."""
    found: list[str] = []
    if signals.internal_header:
        found.append(REASON_HEADER)
    if signals.exclude_cookie:
        found.append(REASON_COOKIE)
    if _account_excluded(signals):
        found.append(REASON_ACCOUNT)
    if ua_is_machine(signals.user_agent):
        found.append(REASON_UA)
    # Prefer the flag stored at insert. A raw IP is only present in memory
    # while the hit is being recorded, never read back from pageviews.
    if signals.ip_is_datacenter or ip_is_datacenter(signals.ip):
        found.append(REASON_IP)
    visitor_id = str(signals.visitor_id or "").strip()
    if visitor_id and visitor_id in _csv_set("ANALYTICS_EXCLUDE_VISITOR_IDS"):
        found.append(REASON_VISITOR_ID)
    ip_hash = str(signals.ip_hash or "").strip()
    if ip_hash and ip_hash in _csv_set("ANALYTICS_EXCLUDE_IP_HASHES"):
        found.append(REASON_IP_HASH)
    order = {name: index for index, name in enumerate(_REASON_ORDER)}
    found.sort(key=lambda name: order.get(name, 99))
    # Dedupe while keeping order.
    seen: set[str] = set()
    unique: list[str] = []
    for name in found:
        if name in seen:
            continue
        seen.add(name)
        unique.append(name)
    return tuple(unique)


def is_excluded_event(
    *,
    visitor_id: str = "",
    username: str | None = None,
    ip_hash: str | None = None,
    email: str | None = None,
    user_id: int | str | None = None,
    ip: str | None = None,
    ip_is_datacenter: bool = False,
    user_agent: str | None = None,
    exclude_cookie: bool = False,
    internal_header: bool = False,
) -> bool:
    """True when the daily report should ignore this hit."""
    return bool(
        exclusion_reasons(
            TrafficSignals(
                visitor_id=visitor_id,
                username=username,
                email=email,
                user_id=user_id,
                ip_hash=ip_hash,
                ip=ip,
                ip_is_datacenter=ip_is_datacenter,
                user_agent=user_agent,
                exclude_cookie=exclude_cookie,
                internal_header=internal_header,
            )
        )
    )
