"""Battle replay recording and persistence."""

from __future__ import annotations

import gzip
import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable

from battle.engine import public_view
from battle.state import MatchState

CatalogFn = Callable[[str], dict[str, Any]]

REPLAYS_DIR = Path(__file__).resolve().parent.parent / "meta" / "replays"
INDEX_FILE = REPLAYS_DIR / "index.sqlite"
MAX_REPLAYS_PER_USER = 30

_replay_lock = threading.Lock()


def _is_registered_user_id(user_id: str) -> bool:
    uid = str(user_id or "")
    return uid.startswith("user_") and not uid.startswith("guest_")


def _registered_participants(room: Any) -> list[str]:
    """User ids that should receive a saved replay."""
    ids: list[str] = []
    if room.hotseat:
        host = str(room.host_user_id or "")
        if _is_registered_user_id(host):
            ids.append(host)
        return ids
    for slot in room.seats:
        if not slot or slot.is_ai:
            continue
        uid = str(slot.user_id or "")
        if ":p2" in uid:
            continue
        if _is_registered_user_id(uid) and uid not in ids:
            ids.append(uid)
    return ids


def _replay_mode(room: Any) -> str:
    if getattr(room, "ranked", False):
        return "ranked"
    if room.hotseat:
        return "hotseat"
    if room.vs_ai:
        return "ai"
    return "pvp"


def replay_frame(state: MatchState, catalog: CatalogFn, *, log_delta: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Omniscient board snapshot for replay playback."""
    base = public_view(state, viewer_seat=0, catalog=catalog)
    p0_view = public_view(state, viewer_seat=0, catalog=catalog)["players"]
    p1_view = public_view(state, viewer_seat=1, catalog=catalog)["players"]
    players = [p0_view[0], p1_view[1]]
    frame: dict[str, Any] = {
        "room_code": state.room_code,
        "status": state.status,
        "phase": state.phase,
        "turn_seat": state.turn_seat,
        "first_seat": state.first_seat,
        "turn_number": state.turn_number,
        "mulligan_seat": state.mulligan_seat,
        "winner_seat": state.winner_seat,
        "players": players,
        "attack": base.get("attack"),
        "pending_effect": base.get("pending_effect"),
        "pending_trigger": base.get("pending_trigger"),
        "pending_search": _full_pending_search(state, catalog),
        "public_search_adds": base.get("public_search_adds"),
        "pending_choice": _full_pending_choice(state),
        "log_delta": list(log_delta or []),
        "legal_actions": [],
        "replay_mode": True,
    }
    return frame


def _full_pending_search(state: MatchState, catalog: CatalogFn) -> dict[str, Any] | None:
    ps = state.pending_search
    if not ps:
        return None
    view = public_view(state, viewer_seat=ps.seat, catalog=catalog)
    return view.get("pending_search")


def _full_pending_choice(state: MatchState) -> dict[str, Any] | None:
    pc = state.pending_choice
    if not pc:
        return None
    return {
        "seat": pc.seat,
        "card_id": pc.card_id,
        "source_iid": pc.source_iid,
        "target_kind": pc.target_kind,
        "options": list(pc.options),
        "option_labels": dict(pc.option_labels),
        "optional": pc.optional,
        "multi_select": bool(pc.multi_select),
        "summary": pc.summary,
        "purpose": getattr(pc, "purpose", None),
    }


def should_record(room: Any) -> bool:
    return bool(_registered_participants(room))


def init_recording(room: Any) -> None:
    if not should_record(room):
        room.replay_id = None
        room.replay_frames = []
        room.replay_log_len = 0
        return
    room.replay_id = secrets.token_urlsafe(16)
    room.replay_frames = []
    room.replay_log_len = 0


def record_frame(room: Any, catalog: CatalogFn) -> None:
    if not room.match or not room.replay_id:
        return
    state = room.match
    log_len = len(state.log)
    delta = list(state.log[room.replay_log_len : log_len])
    room.replay_log_len = log_len
    room.replay_frames.append(replay_frame(state, catalog, log_delta=delta))


def _ensure_index() -> None:
    REPLAYS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(INDEX_FILE)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS replays (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                room_code TEXT,
                created_at REAL NOT NULL,
                winner_seat INTEGER,
                p0_username TEXT,
                p1_username TEXT,
                p0_leader TEXT,
                p1_leader TEXT,
                turn_number INTEGER,
                frame_count INTEGER,
                participant_ids TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_replays_user ON replays(user_id, created_at DESC)")
        conn.commit()
    finally:
        conn.close()


def _delete_replay_file(replay_id: str) -> None:
    path = REPLAYS_DIR / f"{replay_id}.json.gz"
    if path.exists():
        path.unlink()


def _trim_user_replays(user_id: str) -> None:
    conn = sqlite3.connect(INDEX_FILE)
    try:
        rows = conn.execute(
            "SELECT id FROM replays WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        ).fetchall()
        excess = len(rows) - MAX_REPLAYS_PER_USER
        if excess <= 0:
            return
        for (rid,) in rows[:excess]:
            conn.execute("DELETE FROM replays WHERE id = ?", (rid,))
            _delete_replay_file(str(rid))
        conn.commit()
    finally:
        conn.close()


def persist_replay(room: Any, catalog: CatalogFn) -> str | None:
    """Write finished match to disk. Returns replay_id or None."""
    if not room.match or not room.replay_id or not room.replay_frames:
        return None
    participants = _registered_participants(room)
    if not participants:
        return None
    state = room.match
    if state.status != "finished":
        return None

    replay_id = str(room.replay_id)
    p0 = state.players[0]
    p1 = state.players[1]
    header = {
        "id": replay_id,
        "mode": _replay_mode(room),
        "room_code": room.code,
        "created_at": state.created_at,
        "finished_at": state.updated_at,
        "winner_seat": state.winner_seat,
        "participant_ids": participants,
        "p0": {
            "user_id": p0.user_id,
            "username": p0.username,
            "leader_card_id": p0.leader_card_id,
            "is_ai": p0.is_ai,
        },
        "p1": {
            "user_id": p1.user_id,
            "username": p1.username,
            "leader_card_id": p1.leader_card_id,
            "is_ai": p1.is_ai,
        },
        "turn_number": state.turn_number,
        "log": list(state.log),
        "frame_count": len(room.replay_frames),
    }
    payload = {"header": header, "frames": list(room.replay_frames)}
    REPLAYS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPLAYS_DIR / f"{replay_id}.json.gz"
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with gzip.open(path, "wb") as f:
        f.write(raw)

    participant_json = json.dumps(participants, ensure_ascii=False)
    with _replay_lock:
        _ensure_index()
        conn = sqlite3.connect(INDEX_FILE)
        try:
            for uid in participants:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO replays (
                        id, user_id, mode, room_code, created_at, winner_seat,
                        p0_username, p1_username, p0_leader, p1_leader,
                        turn_number, frame_count, participant_ids
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        replay_id,
                        uid,
                        header["mode"],
                        room.code,
                        float(state.created_at),
                        state.winner_seat,
                        p0.username,
                        p1.username,
                        p0.leader_card_id,
                        p1.leader_card_id,
                        int(state.turn_number),
                        len(room.replay_frames),
                        participant_json,
                    ),
                )
            conn.commit()
            for uid in participants:
                _trim_user_replays(uid)
        finally:
            conn.close()
    return replay_id


def list_replays_for_user(user_id: str) -> list[dict[str, Any]]:
    uid = str(user_id or "")
    if not _is_registered_user_id(uid):
        return []
    with _replay_lock:
        _ensure_index()
        if not INDEX_FILE.exists():
            return []
        conn = sqlite3.connect(INDEX_FILE)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT id, mode, room_code, created_at, winner_seat,
                       p0_username, p1_username, p0_leader, p1_leader,
                       turn_number, frame_count
                FROM replays
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (uid, MAX_REPLAYS_PER_USER),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def load_replay(replay_id: str, user_id: str) -> dict[str, Any] | None:
    uid = str(user_id or "")
    if not _is_registered_user_id(uid):
        return None
    rid = str(replay_id or "").strip()
    if not rid:
        return None
    with _replay_lock:
        _ensure_index()
        conn = sqlite3.connect(INDEX_FILE)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT participant_ids FROM replays WHERE id = ? AND user_id = ?",
                (rid, uid),
            ).fetchone()
            if not row:
                return None
            participants = json.loads(str(row["participant_ids"] or "[]"))
            if uid not in participants:
                return None
        finally:
            conn.close()
    path = REPLAYS_DIR / f"{rid}.json.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rb") as f:
        data = json.loads(f.read().decode("utf-8"))
    header = data.get("header") or {}
    if uid not in (header.get("participant_ids") or participants):
        return None
    return data


def attach_replay_id_to_view(view: dict[str, Any], room: Any) -> None:
    if room.replay_id and room.match and room.match.status == "finished":
        view["replay_id"] = str(room.replay_id)
