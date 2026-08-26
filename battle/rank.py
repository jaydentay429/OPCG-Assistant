"""Ranked PvP ratings (ELO), tiers, and elite title assignment."""

from __future__ import annotations

import hashlib
import hmac
import base64
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

RANK_DB_FILE = Path(__file__).resolve().parent.parent / "meta" / "rank.db"
AUTH_DB_FILE = Path(__file__).resolve().parent.parent / "meta" / "auth.db"

DEFAULT_RATING = 1000
K_FACTOR = 32
K_FACTOR_PLACEMENT = 40
PLACEMENT_GAMES = 10

INITIAL_WINDOW = 300
WINDOW_EXPAND_EVERY_SEC = 10
WINDOW_EXPAND_STEP = 200
WINDOW_MAX = 2000

ELITE_MIN = {
    "warlord": 2000,
    "emperor": 2200,
    "pirate_king": 2400,
}
ELITE_SLOTS = {
    "pirate_king": 1,
    "emperor": 4,
    "warlord": 7,
}

TIER_BOUNDS: list[tuple[int, str]] = [
    (999, "trainee"),
    (1199, "crew"),
    (1399, "captain_rank"),
    (1599, "captain"),
    (1799, "bounty"),
    (1999, "supernova"),
]

TIER_LABELS: dict[str, dict[str, str]] = {
    "trainee": {"zh-Hant": "見習船員", "zh-Hans": "见习船员", "en": "Trainee"},
    "crew": {"zh-Hant": "普通船員", "zh-Hans": "普通船员", "en": "Crew"},
    "captain_rank": {"zh-Hant": "隊長", "zh-Hans": "队长", "en": "Commander"},
    "captain": {"zh-Hant": "船長", "zh-Hans": "船长", "en": "Captain"},
    "bounty": {"zh-Hant": "過億賞金犯", "zh-Hans": "过亿赏金犯", "en": "Super-Bounty"},
    "supernova": {"zh-Hant": "超新星", "zh-Hans": "超新星", "en": "Supernova"},
}

ELITE_LABELS: dict[str, dict[str, str]] = {
    "warlord": {"zh-Hant": "七武海", "zh-Hans": "七武海", "en": "Warlord"},
    "emperor": {"zh-Hant": "四皇", "zh-Hans": "四皇", "en": "Emperor"},
    "pirate_king": {"zh-Hant": "海賊王", "zh-Hans": "海贼王", "en": "Pirate King"},
}

_rank_lock = threading.Lock()

APPEAL_LINK_TTL_SEC = 7 * 86400


def _appeal_signing_secret() -> str:
    for key in ("RANK_APPEAL_ADMIN_TOKEN", "ANALYTICS_ADMIN_TOKEN", "AUTH_SESSION_SECRET"):
        val = str(os.getenv(key) or "").strip()
        if val:
            return val
    return "opcg-rank-appeal-dev"


def make_appeal_review_token(appeal_id: int, action: str) -> str:
    act = str(action or "").strip().lower()
    if act not in {"approve", "reject"}:
        raise ValueError("invalid action")
    exp = int(time.time()) + APPEAL_LINK_TTL_SEC
    payload = f"{int(appeal_id)}:{act}:{exp}"
    sig = hmac.new(_appeal_signing_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    raw = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def verify_appeal_review_token(appeal_id: int, action: str, token: str) -> bool:
    act = str(action or "").strip().lower()
    try:
        pad = "=" * (-len(str(token or "")) % 4)
        raw = base64.urlsafe_b64decode(str(token or "") + pad).decode("utf-8")
        parts = raw.split(":")
        if len(parts) != 4:
            return False
        aid_s, act_t, exp_s, sig = parts
        if int(aid_s) != int(appeal_id) or act_t != act:
            return False
        if int(exp_s) < int(time.time()):
            return False
        payload = f"{aid_s}:{act_t}:{exp_s}"
        expect = hmac.new(_appeal_signing_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expect, sig)
    except Exception:
        return False


def appeal_review_urls(appeal_id: int, *, api_base: str) -> dict[str, str]:
    base = str(api_base or "").rstrip("/")
    approve_token = make_appeal_review_token(appeal_id, "approve")
    reject_token = make_appeal_review_token(appeal_id, "reject")
    q = f"appeal_id={int(appeal_id)}"
    return {
        "approve": f"{base}/battle/rank/appeal/review?{q}&action=approve&token={approve_token}",
        "reject": f"{base}/battle/rank/appeal/review?{q}&action=reject&token={reject_token}",
    }


def build_appeal_admin_email(
    *,
    appeal_id: int,
    room_code: str,
    replay_id: str | None,
    reporter_username: str,
    reporter_user_id: str,
    message: str,
    api_base: str,
) -> tuple[str, str, str]:
    links = appeal_review_urls(appeal_id, api_base=api_base)
    subject = f"[OPCG 排位平反 #{appeal_id}] 房间 {room_code}"
    text = (
        f"申请编号: {appeal_id}\n"
        f"房间: {room_code}\n"
        f"回放: {replay_id or '-'}\n"
        f"申请人: {reporter_username} ({reporter_user_id})\n\n"
        f"--- Bug 描述 ---\n{message.strip()}\n\n"
        f"确认有 Bug（退回双方分数与胜负）:\n{links['approve']}\n\n"
        f"驳回申请:\n{links['reject']}\n"
    )
    html = f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;line-height:1.5;color:#111">
<h2>排位平反申请 #{appeal_id}</h2>
<p><strong>房间</strong> {room_code}<br>
<strong>回放</strong> {replay_id or "-"}<br>
<strong>申请人</strong> {reporter_username} ({reporter_user_id})</p>
<h3>Bug 描述</h3>
<pre style="white-space:pre-wrap;background:#f4f4f5;padding:12px;border-radius:8px">{message.strip()}</pre>
<p style="margin-top:24px">
<a href="{links['approve']}" style="display:inline-block;padding:12px 20px;background:#16a34a;color:#fff;text-decoration:none;border-radius:8px;font-weight:700;margin-right:12px">确认有 Bug（退回分数）</a>
<a href="{links['reject']}" style="display:inline-block;padding:12px 20px;background:#64748b;color:#fff;text-decoration:none;border-radius:8px;font-weight:700">驳回申请</a>
</p>
<p style="color:#666;font-size:13px">点击「确认有 Bug」后，该局排位胜负与分数将对<strong>双方玩家</strong>一并撤销。</p>
</body></html>"""
    return subject, text, html


def get_appeal_by_id(appeal_id: int) -> dict[str, Any] | None:
    _init_db()
    with _rank_lock:
        conn = _db()
        try:
            row = conn.execute("SELECT * FROM ranked_appeals WHERE id = ?", (int(appeal_id),)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def is_registered_user_id(user_id: str) -> bool:
    uid = str(user_id or "")
    return uid.startswith("user_") and not uid.startswith("guest_")


def match_window(wait_sec: float) -> int:
    waited = max(0.0, float(wait_sec))
    expansions = int(waited // WINDOW_EXPAND_EVERY_SEC)
    return min(INITIAL_WINDOW + expansions * WINDOW_EXPAND_STEP, WINDOW_MAX)


def _db() -> sqlite3.Connection:
    RANK_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(RANK_DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _auth_db() -> sqlite3.Connection:
    conn = sqlite3.connect(AUTH_DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _rank_lock:
        conn = _db()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS user_ratings (
                    user_id TEXT PRIMARY KEY,
                    rating INTEGER NOT NULL DEFAULT 1000,
                    games INTEGER NOT NULL DEFAULT 0,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    draws INTEGER NOT NULL DEFAULT 0,
                    peak_rating INTEGER NOT NULL DEFAULT 1000,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ranked_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_code TEXT NOT NULL,
                    replay_id TEXT,
                    p0_user_id TEXT NOT NULL,
                    p1_user_id TEXT NOT NULL,
                    p0_username TEXT NOT NULL DEFAULT '',
                    p1_username TEXT NOT NULL DEFAULT '',
                    winner_seat INTEGER,
                    p0_rating_before INTEGER NOT NULL,
                    p1_rating_before INTEGER NOT NULL,
                    p0_rating_after INTEGER NOT NULL,
                    p1_rating_after INTEGER NOT NULL,
                    p0_delta INTEGER NOT NULL,
                    p1_delta INTEGER NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ranked_results_room ON ranked_results(room_code);
                CREATE TABLE IF NOT EXISTS settled_rooms (
                    room_code TEXT PRIMARY KEY,
                    settled_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ranked_appeals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_code TEXT NOT NULL UNIQUE,
                    replay_id TEXT,
                    reporter_user_id TEXT NOT NULL,
                    reporter_username TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at REAL NOT NULL,
                    reviewed_at REAL,
                    review_note TEXT
                );
                """
            )
            try:
                conn.execute(
                    "ALTER TABLE ranked_results ADD COLUMN reverted INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass
            conn.commit()
        finally:
            conn.close()


def _user_db_id(user_id: str) -> int | None:
    uid = str(user_id or "")
    if not uid.startswith("user_"):
        return None
    try:
        return int(uid.split("_", 1)[1])
    except (IndexError, ValueError):
        return None


def lookup_usernames(user_ids: list[str]) -> dict[str, str]:
    ids: list[int] = []
    for uid in user_ids:
        n = _user_db_id(uid)
        if n is not None:
            ids.append(n)
    if not ids or not AUTH_DB_FILE.exists():
        return {}
    placeholders = ",".join("?" for _ in ids)
    conn = _auth_db()
    try:
        rows = conn.execute(
            f"SELECT id, username FROM users WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        return {f"user_{int(r['id'])}": str(r["username"]) for r in rows}
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


def _ensure_user(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM user_ratings WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        return row
    now = time.time()
    conn.execute(
        """
        INSERT INTO user_ratings (user_id, rating, peak_rating, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, DEFAULT_RATING, DEFAULT_RATING, now),
    )
    row = conn.execute("SELECT * FROM user_ratings WHERE user_id = ?", (user_id,)).fetchone()
    assert row is not None
    return row


def base_tier(rating: int) -> str:
    r = int(rating)
    for bound, tier in TIER_BOUNDS:
        if r <= bound:
            return tier
    return "supernova"


def _expected_score(rating_a: int, rating_b: int) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def _k_factor(games: int) -> int:
    return K_FACTOR_PLACEMENT if games < PLACEMENT_GAMES else K_FACTOR


def compute_elite_titles(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Assign at most one elite title per user. Returns user_id -> elite key."""
    rated = sorted(
        [r for r in rows if int(r.get("rating") or 0) >= ELITE_MIN["warlord"]],
        key=lambda r: (-int(r["rating"]), str(r["user_id"])),
    )
    assigned: dict[str, str] = {}
    taken: set[str] = set()

    for r in rated:
        uid = str(r["user_id"])
        rating = int(r["rating"])
        if (
            rating >= ELITE_MIN["pirate_king"]
            and len([t for t in assigned.values() if t == "pirate_king"]) < ELITE_SLOTS["pirate_king"]
        ):
            assigned[uid] = "pirate_king"
            taken.add(uid)

    emperor_count = 0
    for r in rated:
        uid = str(r["user_id"])
        if uid in taken:
            continue
        rating = int(r["rating"])
        if rating >= ELITE_MIN["emperor"] and emperor_count < ELITE_SLOTS["emperor"]:
            assigned[uid] = "emperor"
            taken.add(uid)
            emperor_count += 1

    warlord_count = 0
    for r in rated:
        uid = str(r["user_id"])
        if uid in taken:
            continue
        rating = int(r["rating"])
        if rating >= ELITE_MIN["warlord"] and warlord_count < ELITE_SLOTS["warlord"]:
            assigned[uid] = "warlord"
            taken.add(uid)
            warlord_count += 1

    return assigned


def elite_badges_for_user_ids(user_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Return elite_title / elite_title_zh for registered users."""
    _init_db()
    ids = [str(uid) for uid in user_ids if is_registered_user_id(str(uid))]
    if not ids:
        return {}
    with _rank_lock:
        conn = _db()
        try:
            elite_rows = conn.execute(
                "SELECT user_id, rating FROM user_ratings WHERE rating >= ?",
                (ELITE_MIN["warlord"],),
            ).fetchall()
            elite_map = compute_elite_titles([dict(r) for r in elite_rows])
        finally:
            conn.close()
    out: dict[str, dict[str, Any]] = {}
    for uid in ids:
        elite = elite_map.get(uid)
        out[uid] = {
            "elite_title": elite,
            "elite_title_zh": ELITE_LABELS.get(elite or "", {}).get("zh-Hant") if elite else None,
        }
    return out


def _profile_row(row: sqlite3.Row, elite_map: dict[str, str] | None = None) -> dict[str, Any]:
    uid = str(row["user_id"])
    rating = int(row["rating"])
    games = int(row["games"])
    wins = int(row["wins"])
    losses = int(row["losses"])
    elite = (elite_map or {}).get(uid)
    tier = base_tier(rating)
    tier_label_zh = TIER_LABELS.get(tier, {}).get("zh-Hant", tier)
    elite_title_zh = ELITE_LABELS.get(elite or "", {}).get("zh-Hant") if elite else None
    display_tier_zh = elite_title_zh or tier_label_zh
    win_rate = round(wins / games, 4) if games else 0.0
    return {
        "user_id": uid,
        "rating": rating,
        "tier": tier,
        "tier_label_zh": display_tier_zh,
        "elite_title": elite,
        "elite_title_zh": elite_title_zh,
        "games": games,
        "wins": wins,
        "losses": losses,
        "draws": int(row["draws"]),
        "win_rate": win_rate,
        "peak_rating": int(row["peak_rating"]),
        "elite_pending": bool(rating >= ELITE_MIN["warlord"] and not elite),
    }


def get_user_profile(user_id: str) -> dict[str, Any]:
    _init_db()
    with _rank_lock:
        conn = _db()
        try:
            row = _ensure_user(conn, user_id)
            conn.commit()
            all_rows = conn.execute(
                "SELECT user_id, rating FROM user_ratings WHERE rating >= ? ORDER BY rating DESC",
                (ELITE_MIN["warlord"],),
            ).fetchall()
            elite_map = compute_elite_titles([dict(r) for r in all_rows])
            profile = _profile_row(row, elite_map)
        finally:
            conn.close()
    names = lookup_usernames([user_id])
    profile["username"] = names.get(user_id, "")
    return profile


def get_rating(user_id: str) -> int:
    return int(get_user_profile(user_id)["rating"])


def leaderboard(limit: int = 50) -> list[dict[str, Any]]:
    _init_db()
    limit = max(1, min(int(limit), 200))
    with _rank_lock:
        conn = _db()
        try:
            rows = conn.execute(
                """
                SELECT * FROM user_ratings
                WHERE games > 0 OR rating != ?
                ORDER BY rating DESC, updated_at ASC
                LIMIT ?
                """,
                (DEFAULT_RATING, limit),
            ).fetchall()
            elite_rows = conn.execute(
                "SELECT user_id, rating FROM user_ratings WHERE rating >= ?",
                (ELITE_MIN["warlord"],),
            ).fetchall()
            elite_map = compute_elite_titles([dict(r) for r in elite_rows])
            profiles = [_profile_row(r, elite_map) for r in rows]
        finally:
            conn.close()
    names = lookup_usernames([p["user_id"] for p in profiles])
    for i, p in enumerate(profiles):
        p["username"] = names.get(p["user_id"], p["user_id"])
        p["rank"] = i + 1
    return profiles


def elite_roster() -> dict[str, list[dict[str, Any]]]:
    board = leaderboard(limit=500)
    out: dict[str, list[dict[str, Any]]] = {
        "pirate_king": [],
        "emperor": [],
        "warlord": [],
    }
    for p in board:
        et = p.get("elite_title")
        if et in out:
            out[str(et)].append(p)
    for key in out:
        cap = ELITE_SLOTS[key]
        out[key] = out[key][:cap]
    return out


def match_history(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    _init_db()
    limit = max(1, min(int(limit), 100))
    uid = str(user_id)
    with _rank_lock:
        conn = _db()
        try:
            rows = conn.execute(
                """
                SELECT * FROM ranked_results
                WHERE p0_user_id = ? OR p1_user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (uid, uid, limit),
            ).fetchall()
            results = [dict(r) for r in rows]
        finally:
            conn.close()
    for r in results:
        seat = 0 if r["p0_user_id"] == uid else 1
        opp_seat = 1 - seat
        r["opponent_user_id"] = r["p1_user_id"] if seat == 0 else r["p0_user_id"]
        r["opponent_username"] = r["p1_username"] if seat == 0 else r["p0_username"]
        r["rating_before"] = r["p0_rating_before"] if seat == 0 else r["p1_rating_before"]
        r["rating_after"] = r["p0_rating_after"] if seat == 0 else r["p1_rating_after"]
        r["delta"] = r["p0_delta"] if seat == 0 else r["p1_delta"]
        ws = r.get("winner_seat")
        if ws is None:
            r["result"] = "draw"
        elif int(ws) == seat:
            r["result"] = "win"
        else:
            r["result"] = "loss"
        r["my_seat"] = seat
        r["opponent_seat"] = opp_seat
    return results


def apply_match_result(room: Any) -> dict[str, Any] | None:
    """Apply ELO update for a finished ranked room. Idempotent."""
    if not getattr(room, "ranked", False):
        return None
    if not room.match or room.match.status != "finished":
        return None
    seats = room.seats or [None, None]
    if len(seats) < 2 or not seats[0] or not seats[1]:
        return None
    if seats[0].is_ai or seats[1].is_ai:
        return None
    p0_uid = str(seats[0].user_id or "")
    p1_uid = str(seats[1].user_id or "")
    if not is_registered_user_id(p0_uid) or not is_registered_user_id(p1_uid):
        return None

    code = str(room.code)
    winner_seat = room.match.winner_seat
    replay_id = getattr(room, "replay_id", None)

    _init_db()
    with _rank_lock:
        conn = _db()
        try:
            settled = conn.execute(
                "SELECT room_code FROM settled_rooms WHERE room_code = ?",
                (code,),
            ).fetchone()
            if settled:
                return None

            p0_row = _ensure_user(conn, p0_uid)
            p1_row = _ensure_user(conn, p1_uid)
            r0 = int(p0_row["rating"])
            r1 = int(p1_row["rating"])
            g0 = int(p0_row["games"])
            g1 = int(p1_row["games"])

            e0 = _expected_score(r0, r1)
            e1 = _expected_score(r1, r0)
            if winner_seat is None:
                s0 = s1 = 0.5
            elif int(winner_seat) == 0:
                s0, s1 = 1.0, 0.0
            elif int(winner_seat) == 1:
                s0, s1 = 0.0, 1.0
            else:
                return None

            d0 = round(_k_factor(g0) * (s0 - e0))
            d1 = round(_k_factor(g1) * (s1 - e1))
            nr0 = r0 + d0
            nr1 = r1 + d1
            now = time.time()

            def _bump(uid: str, nr: int, win: int, loss: int, draw: int) -> None:
                conn.execute(
                    """
                    UPDATE user_ratings SET
                        rating = ?,
                        games = games + 1,
                        wins = wins + ?,
                        losses = losses + ?,
                        draws = draws + ?,
                        peak_rating = MAX(peak_rating, ?),
                        updated_at = ?
                    WHERE user_id = ?
                    """,
                    (nr, win, loss, draw, nr, now, uid),
                )

            if winner_seat is None:
                _bump(p0_uid, nr0, 0, 0, 1)
                _bump(p1_uid, nr1, 0, 0, 1)
            elif int(winner_seat) == 0:
                _bump(p0_uid, nr0, 1, 0, 0)
                _bump(p1_uid, nr1, 0, 1, 0)
            else:
                _bump(p0_uid, nr0, 0, 1, 0)
                _bump(p1_uid, nr1, 1, 0, 0)

            conn.execute(
                """
                INSERT INTO ranked_results (
                    room_code, replay_id,
                    p0_user_id, p1_user_id, p0_username, p1_username,
                    winner_seat,
                    p0_rating_before, p1_rating_before,
                    p0_rating_after, p1_rating_after,
                    p0_delta, p1_delta, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    replay_id,
                    p0_uid,
                    p1_uid,
                    str(seats[0].username or ""),
                    str(seats[1].username or ""),
                    winner_seat,
                    r0,
                    r1,
                    nr0,
                    nr1,
                    d0,
                    d1,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO settled_rooms (room_code, settled_at) VALUES (?, ?)",
                (code, now),
            )
            conn.commit()
            return {
                "room_code": code,
                "p0": {"user_id": p0_uid, "delta": d0, "rating_after": nr0},
                "p1": {"user_id": p1_uid, "delta": d1, "rating_after": nr1},
            }
        finally:
            conn.close()


def _get_ranked_result_row(conn: sqlite3.Connection, room_code: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM ranked_results WHERE room_code = ?",
        (str(room_code),),
    ).fetchone()


def get_appeal_status(user_id: str, room_code: str) -> dict[str, Any]:
    """Appeal status for a ranked room (participant only)."""
    _init_db()
    uid = str(user_id)
    code = str(room_code or "").strip().upper()
    with _rank_lock:
        conn = _db()
        try:
            result = _get_ranked_result_row(conn, code)
            if not result:
                return {"ok": False, "error": "not_ranked", "status": "none"}
            if uid not in {str(result["p0_user_id"]), str(result["p1_user_id"])}:
                return {"ok": False, "error": "not_participant", "status": "none"}
            reverted = int(result["reverted"] if "reverted" in result.keys() else 0)
            if reverted:
                return {
                    "ok": True,
                    "status": "reverted",
                    "can_appeal": False,
                    "room_code": code,
                }
            row = conn.execute(
                "SELECT * FROM ranked_appeals WHERE room_code = ?",
                (code,),
            ).fetchone()
            if not row:
                return {
                    "ok": True,
                    "status": "none",
                    "can_appeal": True,
                    "room_code": code,
                }
            return {
                "ok": True,
                "status": str(row["status"]),
                "can_appeal": False,
                "appeal_id": int(row["id"]),
                "reporter_user_id": str(row["reporter_user_id"]),
                "created_at": float(row["created_at"]),
                "room_code": code,
            }
        finally:
            conn.close()


def submit_ranked_appeal(
    user_id: str,
    username: str,
    *,
    room_code: str,
    description: str,
    replay_id: str | None = None,
) -> dict[str, Any]:
    _init_db()
    uid = str(user_id)
    code = str(room_code or "").strip().upper()
    text = str(description or "").strip()
    if len(text) < 8:
        raise ValueError("请具体描述 Bug 情况（至少 8 个字）。")
    if len(text) > 4000:
        raise ValueError("描述过长。")

    with _rank_lock:
        conn = _db()
        try:
            result = _get_ranked_result_row(conn, code)
            if not result:
                raise ValueError("这不是排位对局，或分数尚未结算。")
            if int(result["reverted"] if "reverted" in result.keys() else 0):
                raise ValueError("该对局分数已退回。")
            if uid not in {str(result["p0_user_id"]), str(result["p1_user_id"])}:
                raise PermissionError("仅对局玩家可提交平反申请。")

            existing = conn.execute(
                "SELECT * FROM ranked_appeals WHERE room_code = ?",
                (code,),
            ).fetchone()
            if existing:
                st = str(existing["status"])
                if st == "pending":
                    raise ValueError("该对局已有待审核的平反申请。")
                if st == "approved":
                    raise ValueError("该对局分数已退回。")
                raise ValueError("该对局平反申请已被驳回。")

            now = time.time()
            cur = conn.execute(
                """
                INSERT INTO ranked_appeals (
                    room_code, replay_id, reporter_user_id, reporter_username,
                    description, status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (code, replay_id, uid, str(username or ""), text, now),
            )
            conn.commit()
            return {
                "ok": True,
                "appeal_id": int(cur.lastrowid),
                "status": "pending",
                "room_code": code,
            }
        finally:
            conn.close()


def revert_ranked_match(room_code: str, *, review_note: str = "") -> dict[str, Any]:
    """Rollback ELO and W/L for both players. Idempotent if already reverted."""
    _init_db()
    code = str(room_code or "").strip().upper()
    with _rank_lock:
        conn = _db()
        try:
            result = _get_ranked_result_row(conn, code)
            if not result:
                raise ValueError("Ranked result not found.")
            if int(result["reverted"] if "reverted" in result.keys() else 0):
                return {"ok": True, "already_reverted": True, "room_code": code}

            p0_uid = str(result["p0_user_id"])
            p1_uid = str(result["p1_user_id"])
            winner_seat = result["winner_seat"]
            now = time.time()

            conn.execute(
                "UPDATE user_ratings SET rating = ?, updated_at = ? WHERE user_id = ?",
                (int(result["p0_rating_before"]), now, p0_uid),
            )
            conn.execute(
                "UPDATE user_ratings SET rating = ?, updated_at = ? WHERE user_id = ?",
                (int(result["p1_rating_before"]), now, p1_uid),
            )

            def _undo_record(uid: str, seat: int) -> None:
                if winner_seat is None:
                    conn.execute(
                        """
                        UPDATE user_ratings SET
                            games = MAX(0, games - 1),
                            draws = MAX(0, draws - 1)
                        WHERE user_id = ?
                        """,
                        (uid,),
                    )
                elif int(winner_seat) == seat:
                    conn.execute(
                        """
                        UPDATE user_ratings SET
                            games = MAX(0, games - 1),
                            wins = MAX(0, wins - 1)
                        WHERE user_id = ?
                        """,
                        (uid,),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE user_ratings SET
                            games = MAX(0, games - 1),
                            losses = MAX(0, losses - 1)
                        WHERE user_id = ?
                        """,
                        (uid,),
                    )

            _undo_record(p0_uid, 0)
            _undo_record(p1_uid, 1)

            conn.execute(
                "UPDATE ranked_results SET reverted = 1 WHERE room_code = ?",
                (code,),
            )
            conn.execute(
                """
                UPDATE ranked_appeals SET
                    status = 'approved',
                    reviewed_at = ?,
                    review_note = ?
                WHERE room_code = ? AND status = 'pending'
                """,
                (now, str(review_note or ""), code),
            )
            conn.commit()
            return {
                "ok": True,
                "room_code": code,
                "p0_rating_restored": int(result["p0_rating_before"]),
                "p1_rating_restored": int(result["p1_rating_before"]),
            }
        finally:
            conn.close()


def review_ranked_appeal(appeal_id: int, action: str, *, note: str = "") -> dict[str, Any]:
    _init_db()
    act = str(action or "").strip().lower()
    if act not in {"approve", "reject"}:
        raise ValueError("action must be approve or reject")

    with _rank_lock:
        conn = _db()
        try:
            row = conn.execute(
                "SELECT * FROM ranked_appeals WHERE id = ?",
                (int(appeal_id),),
            ).fetchone()
            if not row:
                raise ValueError("Appeal not found.")
            if str(row["status"]) != "pending":
                raise ValueError("Appeal already reviewed.")

            code = str(row["room_code"])
            now = time.time()
            if act == "reject":
                conn.execute(
                    """
                    UPDATE ranked_appeals SET
                        status = 'rejected',
                        reviewed_at = ?,
                        review_note = ?
                    WHERE id = ?
                    """,
                    (now, str(note or ""), int(appeal_id)),
                )
                conn.commit()
                return {"ok": True, "status": "rejected", "appeal_id": int(appeal_id)}
            conn.commit()
        finally:
            conn.close()

    if act == "approve":
        out = revert_ranked_match(code, review_note=note or "approved")
        out["appeal_id"] = int(appeal_id)
        out["status"] = "approved"
        return out
    return {"ok": False}
