from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from analytics.db import fetch_pageviews, first_seen_before, load_user_emails
from analytics.exclude import (
    REASON_LABELS,
    exclusion_reasons,
    signals_from_row,
)

HKT = ZoneInfo("Asia/Hong_Kong")

# Paths with fewer than this many views are rolled into「其他页面」.
HOT_PATH_MIN_VIEWS = 5
HOT_PATH_TOP_N = 5
# In diagnostics, surface clean-traffic visitors at/above this hit count.
SUSPECT_MIN_VIEWS = 8
SUSPECT_TOP_N = 8


def report_day_bounds_hkt(day: date | None = None) -> tuple[str, str, str]:
    """
    Return (label_yyyy_mm_dd, start_utc_iso, end_utc_iso) for one HKT calendar day.
    Default: yesterday in Hong Kong.
    """
    now_hkt = datetime.now(HKT)
    target = day or (now_hkt.date() - timedelta(days=1))
    start_hkt = datetime(target.year, target.month, target.day, tzinfo=HKT)
    end_hkt = start_hkt + timedelta(days=1)
    start_utc = start_hkt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = end_hkt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return target.isoformat(), start_utc, end_utc


def normalize_path(path: str | None) -> str:
    """Strip query/hash and collapse deep dynamic routes for readable tops."""
    raw = str(path or "/").strip() or "/"
    raw = raw.split("?", 1)[0].split("#", 1)[0].strip() or "/"
    if not raw.startswith("/"):
        raw = "/" + raw
    # Drop trailing slash except root.
    if len(raw) > 1 and raw.endswith("/"):
        raw = raw.rstrip("/")

    if raw.startswith("/cards/") and len(raw) > len("/cards/"):
        return "/cards/*"
    if raw.startswith("/community/") and raw[len("/community/") :].isdigit():
        return "/community/*"
    if raw.startswith("/binder/s/"):
        return "/binder/s/*"
    if raw.startswith("/play/history/") and len(raw) > len("/play/history/"):
        return "/play/history/*"
    return raw or "/"


def classify_referrer(referrer: str | None) -> str:
    """Return one of: direct | search | referral."""
    ref = str(referrer or "").strip()
    if not ref:
        return "direct"
    try:
        host = (urlparse(ref).netloc or "").lower()
    except Exception:
        host = ""
    if not host:
        return "direct"
    # Strip credentials/port noise
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    host = host.split(":")[0]

    search_needles = (
        "google.",
        "google.com",
        "bing.",
        "bing.com",
        "yahoo.",
        "baidu.",
        "duckduckgo.",
        "ecosia.",
        "search.brave.",
    )
    if any(n in host for n in search_needles):
        return "search"

    # Site itself + common local/dev hosts → internal / related.
    if (
        "optcgassistant.com" in host
        or host in {"localhost", "127.0.0.1"}
        or host.endswith(".local")
    ):
        return "referral"
    return "referral"


def row_matches_exclude_config(row: Any, email_by_user_id: dict[int, str] | None = None) -> bool:
    """Current exclusion rules, not the insert-time is_excluded flag alone."""
    return bool(exclusion_reasons(signals_from_row(row, email_by_user_id)))


def exclusion_reason_counts(rows: list[Any], email_by_user_id: dict[int, str] | None = None) -> Counter[str]:
    """Pageview counts by primary reason. A hit is counted once."""
    counts: Counter[str] = Counter()
    for row in rows:
        reasons = exclusion_reasons(signals_from_row(row, email_by_user_id))
        if reasons:
            counts[reasons[0]] += 1
    return counts


def _pct(part: int, whole: int) -> str:
    if whole <= 0:
        return "0%"
    raw = f"{(100.0 * part / whole):.1f}".rstrip("0").rstrip(".")
    return f"{raw}%"


def _hot_paths(path_counter: Counter[str]) -> tuple[list[tuple[str, int]], int]:
    """
    Return (top paths for display, other_views).
    Paths under HOT_PATH_MIN_VIEWS roll into other; among the rest keep Top N.
    """
    high = [(p, n) for p, n in path_counter.items() if n >= HOT_PATH_MIN_VIEWS]
    low_views = sum(n for p, n in path_counter.items() if n < HOT_PATH_MIN_VIEWS)
    high.sort(key=lambda x: (-x[1], x[0]))
    top = high[:HOT_PATH_TOP_N]
    rest_high = sum(n for _, n in high[HOT_PATH_TOP_N:])
    other = low_views + rest_high
    return top, other


def _summarize_business(rows: list[Any], *, start_utc: str) -> dict[str, Any]:
    pageviews = len(rows)
    visitors = {str(r["visitor_id"]) for r in rows}
    sessions = {str(r["session_id"]) for r in rows}
    logged_in_rows = [r for r in rows if r["user_id"] is not None]
    logged_in_users = sorted(
        {str(r["username"] or r["user_id"]) for r in logged_in_rows if (r["username"] or r["user_id"])}
    )

    returning = first_seen_before(visitors, start_utc)
    new_visitors = visitors - returning

    paths: Counter[str] = Counter()
    referrer_bucket: Counter[str] = Counter()
    visitor_hits: Counter[str] = Counter()
    visitor_ips: dict[str, Counter[str]] = defaultdict(Counter)
    hourly: Counter[str] = Counter()

    for r in rows:
        paths[normalize_path(r["path"])] += 1
        referrer_bucket[classify_referrer(r["referrer"])] += 1
        vid = str(r["visitor_id"] or "")
        visitor_hits[vid] += 1
        iph = str(r["ip_hash"] or "").strip()
        if iph:
            visitor_ips[vid][iph] += 1

        ts = str(r["ts"] or "")
        try:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            hour = dt.astimezone(HKT).strftime("%H")
        except ValueError:
            hour = "??"
        hourly[hour] += 1

    top_paths, other_path_views = _hot_paths(paths)

    suspects: list[tuple[str, int, str]] = []
    for vid, hits in visitor_hits.most_common(SUSPECT_TOP_N * 2):
        if hits < SUSPECT_MIN_VIEWS:
            break
        ip_counter = visitor_ips.get(vid) or Counter()
        top_ip = ip_counter.most_common(1)[0][0] if ip_counter else "?"
        suspects.append((vid, hits, top_ip))
        if len(suspects) >= SUSPECT_TOP_N:
            break

    return {
        "pageviews": pageviews,
        "unique_visitors": len(visitors),
        "unique_sessions": len(sessions),
        "new_visitors": len(new_visitors),
        "returning_visitors": len(returning),
        "logged_in_pageviews": len(logged_in_rows),
        "logged_in_users": logged_in_users,
        "top_paths": top_paths,
        "other_path_views": other_path_views,
        "referrer_bucket": referrer_bucket,
        "hourly": sorted(hourly.items()),
        "suspects": suspects,
    }


def build_daily_report(day: date | None = None) -> tuple[str, str]:
    """
    Build (subject, body) for the daily analytics email.

    Exclusion is applied from the current rules (cookie, account, user agent,
    datacenter IP, internal header, and ANALYTICS_EXCLUDE_* lists) before any
    business metrics are computed. The insert-time is_excluded flag is not
    enough on its own, because the lists can change later.
    """
    label, start_utc, end_utc = report_day_bounds_hkt(day)
    all_rows = fetch_pageviews(start_utc, end_utc, include_excluded=True)
    email_by_user_id = load_user_emails()

    clean = [r for r in all_rows if not row_matches_exclude_config(r, email_by_user_id)]
    excluded = [r for r in all_rows if row_matches_exclude_config(r, email_by_user_id)]
    reason_counts = exclusion_reason_counts(excluded, email_by_user_id)

    biz = _summarize_business(clean, start_utc=start_utc)
    excl_visitors = {str(r["visitor_id"]) for r in excluded}
    pv = biz["pageviews"]
    ref = biz["referrer_bucket"]
    direct_n = int(ref.get("direct", 0))
    search_n = int(ref.get("search", 0))
    referral_n = int(ref.get("referral", 0))

    start_hkt = (
        datetime.strptime(start_utc, "%Y-%m-%dT%H:%M:%SZ")
        .replace(tzinfo=timezone.utc)
        .astimezone(HKT)
        .strftime("%Y-%m-%d %H:%M:%S")
    )
    end_hkt = (
        datetime.strptime(end_utc, "%Y-%m-%dT%H:%M:%SZ")
        .replace(tzinfo=timezone.utc)
        .astimezone(HKT)
        .strftime("%Y-%m-%d %H:%M:%S")
    )

    users = biz["logged_in_users"]
    users_txt = f"[{', '.join(users)}]" if users else "[]"

    subject = (
        f"[OPCG] {label} 流量日报 · "
        f"{biz['unique_visitors']} UV / {biz['pageviews']} PV"
    )

    lines: list[str] = [
        f"**📊 OPCG 流量日报 (HKT {label})**",
        f"统计区间：{start_utc.replace('T', ' ').replace('Z', '')} ~ "
        f"{end_utc.replace('T', ' ').replace('Z', '')} (UTC)",
        f"（对应 HKT：{start_hkt} ~ {end_hkt}）",
        "",
        "**核心指标**",
        f"* 页面浏览量 (PV)：{biz['pageviews']}",
        f"* 独立访客 (UV)：{biz['unique_visitors']}"
        f"（新访客：{biz['new_visitors']} | 回访访客：{biz['returning_visitors']}）",
        f"* 总会话数 (Sessions)：{biz['unique_sessions']}",
        f"* 登录用户数：{len(users)}"
        f"（浏览量：{biz['logged_in_pageviews']}，包含用户：{users_txt})",
        "",
        f"**高频访问页面 Top {HOT_PATH_TOP_N}**",
    ]

    if biz["top_paths"]:
        for path, n in biz["top_paths"]:
            lines.append(f"* {path} ({n} 次)")
    else:
        lines.append("* （无达到阈值门槛的页面）")
    if biz["other_path_views"] > 0 or not biz["top_paths"]:
        lines.append(f"* 其他页面: {biz['other_path_views']} 次")

    lines.extend(
        [
            "",
            "**流量来源分布**",
            f"* 直接访问 (Direct)：{direct_n} 次 ({_pct(direct_n, pv)})",
            f"* 搜索引擎 (Bing/Google)：{search_n} 次 ({_pct(search_n, pv)})",
            f"* 站内/关联域名跳转：{referral_n} 次 ({_pct(referral_n, pv)})",
            "",
            "**按小时分布 (HKT)**",
        ]
    )

    if biz["hourly"]:
        for hour, n in biz["hourly"]:
            if hour == "??":
                lines.append(f"*??:00 - ??:00 (共 {n} 次浏览)")
                continue
            try:
                h0 = int(hour)
                h1 = (h0 + 1) % 24
                lines.append(f"*{h0:02d}:00 - {h1:02d}:00 (共 {n} 次浏览)")
            except ValueError:
                lines.append(f"*{hour}:00 (共 {n} 次浏览)")
    else:
        lines.append("*（无）")

    lines.extend(
        [
            "",
            "---",
            "**🛠️ 诊断与排除区（仅供开发者参考）**",
            f"* 已排除：{len(excluded)} 次浏览 / {len(excl_visitors)} 个访客",
            "  （cookie、账号、User-Agent、数据中心 IP、X-OPCG-Internal，以及 ANALYTICS_EXCLUDE_* 名单）",
        ]
    )
    if reason_counts:
        for code, _label in REASON_LABELS.items():
            n = int(reason_counts.get(code, 0))
            if n:
                lines.append(f"  * {_label}：{n} 次浏览")

    if biz["suspects"]:
        lines.append("* 疑似未排除的高频 ID（请核对是否添加到环境变量）：")
        for vid, hits, ip_hash in biz["suspects"]:
            lines.append(f"  * [{vid}] ({hits} 次) -> IP Hash: [{ip_hash}]")
    else:
        lines.append("* 疑似未排除的高频 ID：无（业务流量中无明显高频 visitor）")

    lines.extend(
        [
            "",
            "配置提示:",
            "  ANALYTICS_EXCLUDE_VISITOR_IDS=visitor_id1,visitor_id2",
            "  ANALYTICS_EXCLUDE_USERNAMES=your_username",
            "  ANALYTICS_EXCLUDE_USER_IDS=1,2",
            "  ANALYTICS_EXCLUDE_EMAILS=you@example.com",
            "  ANALYTICS_EXCLUDE_IP_HASHES=iphash1,iphash2",
            "  ANALYTICS_EXCLUDE_ME_TOKEN=（不公开页面的 token，不要提交真实值）",
            "  请求头 X-OPCG-Internal: 1 或 User-Agent 含 OPCG-Internal 的访问不计入",
            "",
            "— OPCG Analytics",
        ]
    )

    return subject, "\n".join(lines)
