"""Battle routes stay mounted but refuse play while BATTLE_ENABLED is off.

The old room page (frontend/src/components/play/PlayPageClient.tsx) polls
GET /battle/rooms/{code} every 2 seconds. Only status 404 clears the saved
room, stops that interval, and disconnects the socket. 410 is ignored and
the tab keeps polling, so paused routes use 404.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from starlette.websockets import WebSocket, WebSocketDisconnect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.routes import (  # noqa: E402
    PAUSED_DETAIL,
    _mint_guest_user,
    battle_enabled,
    mount_battle,
)


def _deny(_request: Request) -> dict:
    raise HTTPException(status_code=401, detail="请先登录。")


def _user_auth(request: Request) -> dict:
    header = str(request.headers.get("authorization") or "")
    if header == "Bearer good":
        return {"user_id": "user_7", "username": "jay"}
    raise HTTPException(status_code=401, detail="请先登录。")


def _client(monkeypatch, *, enabled: bool = False, send_email=None, auth=None) -> tuple[TestClient, object]:
    if enabled:
        monkeypatch.setenv("BATTLE_ENABLED", "1")
    else:
        monkeypatch.delenv("BATTLE_ENABLED", raising=False)
    app = FastAPI()
    manager = mount_battle(
        app,
        catalog=lambda _card_id: {},
        auth_from_token=lambda _token: None,
        auth_from_request=auth or _deny,
        load_deck=lambda _user_id, _deck_id: None,
        send_email=send_email,
    )
    return TestClient(app), manager


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, False),
        ("", False),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
        ("1", True),
        ("true", True),
        ("YES", True),
        ("on", True),
        (" 1 ", True),
    ],
)
def test_battle_enabled_flag(monkeypatch, raw, expected) -> None:
    if raw is None:
        monkeypatch.delenv("BATTLE_ENABLED", raising=False)
    else:
        monkeypatch.setenv("BATTLE_ENABLED", raw)
    assert battle_enabled() is expected


def test_paused_does_not_construct_rooms_or_matchmakers(monkeypatch) -> None:
    monkeypatch.delenv("BATTLE_ENABLED", raising=False)

    def _boom(*_args, **_kwargs):
        raise AssertionError("paused battle must not construct runtime objects")

    monkeypatch.setattr("battle.routes.ensure_loaded", _boom)
    monkeypatch.setattr("battle.routes.RoomManager", _boom)
    monkeypatch.setattr("battle.routes.Matchmaker", _boom)
    monkeypatch.setattr("battle.routes.RankedMatchmaker", _boom)
    _client_obj, manager = _client(monkeypatch, enabled=False)
    assert manager is None
    _client_obj.close()


PAUSED_CALLS = [
    ("GET", "/battle/rooms/OLDROOM"),
    ("GET", "/battle/rooms/no-such-room"),
    ("POST", "/battle/rooms"),
    ("POST", "/battle/rooms/OLDROOM/join"),
    ("POST", "/battle/rooms/OLDROOM/deck"),
    ("POST", "/battle/rooms/OLDROOM/ready"),
    ("POST", "/battle/rooms/OLDROOM/spectator-settings"),
    ("GET", "/battle/rooms/live"),
    ("POST", "/battle/matchmaking/join"),
    ("POST", "/battle/matchmaking/leave"),
    ("GET", "/battle/matchmaking/status"),
    ("POST", "/battle/ranked/join"),
    ("POST", "/battle/ranked/leave"),
    ("GET", "/battle/ranked/status"),
    ("GET", "/battle/rank/me"),
    ("GET", "/battle/rank/leaderboard"),
    ("GET", "/battle/rank/elite"),
    ("GET", "/battle/rank/history"),
    ("GET", "/battle/rank/appeal/status?room_code=OLDROOM"),
    ("GET", "/battle/rank/appeal/review"),
    ("POST", "/battle/rank/appeal"),
    ("POST", "/battle/rank/appeal/review"),
    ("GET", "/battle/replays"),
    ("GET", "/battle/replays/abc"),
    ("GET", "/battle/ai-decks"),
    ("POST", "/battle/guest-token"),
    ("GET", "/battle/effect-library/stats"),
    ("POST", "/battle/effect-library/override"),
]


def test_paused_play_routes_are_404(monkeypatch) -> None:
    client, _manager = _client(monkeypatch, enabled=False)
    for method, path in PAUSED_CALLS:
        response = client.request(method, path, json={})
        assert response.status_code == 404, path
        assert response.json()["detail"] == PAUSED_DETAIL
    client.close()


def test_paused_websocket_is_rejected(monkeypatch) -> None:
    client, _manager = _client(monkeypatch, enabled=False)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/battle/ws?token=guest&room=OLDROOM&role=player"):
            pass
    assert exc.value.code == 1008
    # Handshake closed before a room could exist.
    follow = client.get("/battle/rooms/OLDROOM")
    assert follow.status_code == 404
    client.close()


def test_bug_report_unchanged_while_paused(monkeypatch, capsys) -> None:
    monkeypatch.delenv("BUG_REPORT_EMAIL", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    sent: list[tuple[str, str, str]] = []

    def send_email(to_email: str, subject: str, body: str) -> None:
        sent.append((to_email, subject, body))

    client, _manager = _client(monkeypatch, enabled=False, send_email=send_email, auth=_user_auth)

    missing = client.post("/battle/bug-report", json={"message": "cards stuck on the board"})
    assert missing.status_code == 401
    assert missing.json()["detail"] == "请先登录。"

    guest_token, _guest = _mint_guest_user("Guest")
    guest = client.post(
        "/battle/bug-report",
        json={"message": "cards stuck on the board"},
        headers={"Authorization": f"Bearer {guest_token}"},
    )
    assert guest.status_code == 401

    short = client.post(
        "/battle/bug-report",
        json={"message": "no"},
        headers={"Authorization": "Bearer good"},
    )
    assert short.status_code == 400
    assert "at least" in short.json()["detail"]

    long = client.post(
        "/battle/bug-report",
        json={"message": "x" * 4001},
        headers={"Authorization": "Bearer good"},
    )
    assert long.status_code == 400
    assert long.json()["detail"] == "Bug report is too long."

    ok = client.post(
        "/battle/bug-report",
        json={
            "message": "cards stuck on the board",
            "room_code": "OLDROOM",
            "phase": "main",
            "turn_number": 3,
            "page_url": "https://optcgassistant.com/play",
        },
        headers={"Authorization": "Bearer good"},
    )
    assert ok.status_code == 200
    assert ok.json() == {"ok": True}
    assert len(sent) == 1
    to_email, subject, body = sent[0]
    assert to_email == "jaydentay429@gmail.com"
    assert subject == "[OPCG Battle Bug] jay · OLDROOM"
    assert "From: jay (user_7)" in body
    assert "Room: OLDROOM" in body
    assert "Phase: main" in body
    assert "Turn: 3" in body
    assert "cards stuck on the board" in body

    topbar = client.post(
        "/battle/bug-report",
        json={"message": "top bar report", "page_url": "https://optcgassistant.com/"},
        headers={"Authorization": "Bearer good"},
    )
    assert topbar.status_code == 200
    assert sent[1][1] == "[OPCG Bug] jay"

    def explode(_to: str, _subject: str, _body: str) -> None:
        raise RuntimeError("smtp down")

    failing, _manager = _client(monkeypatch, enabled=False, send_email=explode, auth=_user_auth)
    broken = failing.post(
        "/battle/bug-report",
        json={"message": "cards stuck on the board"},
        headers={"Authorization": "Bearer good"},
    )
    assert broken.status_code == 502
    assert broken.json()["detail"] == "Failed to send bug report email."
    failing.close()

    silent, _manager = _client(monkeypatch, enabled=False, send_email=None, auth=_user_auth)
    printed = silent.post(
        "/battle/bug-report",
        json={"message": "cards stuck on the board", "page_url": "https://optcgassistant.com/"},
        headers={"Authorization": "Bearer good"},
    )
    assert printed.status_code == 200
    assert printed.json() == {"ok": True}
    captured = capsys.readouterr().out
    assert "[battle-bug]" in captured
    assert "top bar" not in captured or "cards stuck on the board" in captured
    silent.close()

    wrong_method = client.get("/battle/bug-report")
    assert wrong_method.status_code == 405
    assert wrong_method.json()["detail"] == "Method Not Allowed"
    assert "POST" in (wrong_method.headers.get("allow") or "")

    invalid = client.post(
        "/battle/bug-report",
        content=b"not-json",
        headers={"content-type": "application/json", "Authorization": "Bearer good"},
    )
    assert invalid.status_code == 422
    client.close()


def test_enabled_flag_restores_room_lookup_and_bug_report(monkeypatch) -> None:
    sent: list[str] = []

    def send_email(_to: str, subject: str, _body: str) -> None:
        sent.append(subject)

    client, manager = _client(monkeypatch, enabled=True, send_email=send_email, auth=_user_auth)
    assert manager is not None
    missing = client.get("/battle/rooms/NOPE")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Room not found."
    ok = client.post(
        "/battle/bug-report",
        json={"message": "still works", "page_url": "https://optcgassistant.com/"},
        headers={"Authorization": "Bearer good"},
    )
    assert ok.status_code == 200
    assert ok.json() == {"ok": True}
    assert sent == ["[OPCG Bug] jay"]
    client.close()


class LegacyRoomTab:
    """Transcription of the old room tab in PlayPageClient.tsx.

    On ready, a saved room opens one websocket (lines 282-300). A 2s interval
    then GETs the room (lines 307-350). Status 404 disconnects, deletes
    sessionStorage room key, and sets roomCode to null, which clears the
    interval. Reconnect only happens when a live state exists or a successful
    poll says the match is playing (lines 302-305 and 318-322). connectBattleWs
    itself does not reconnect.
    """

    def __init__(self, client: TestClient, room: str, token: str) -> None:
        self.client = client
        self.session_room: str | None = room
        self.token = token
        self.room_code: str | None = None
        self.state = None
        self.socket_open = False
        self.ws_connects = 0
        self.room_gets = 0

    def disconnect(self) -> None:
        self.socket_open = False

    def connect(self, code: str, auth_token: str | None = None) -> None:
        token = auth_token or self.token
        if not token:
            return
        self.disconnect()
        self.room_code = code
        self.session_room = code
        self.ws_connects += 1
        try:
            with self.client.websocket_connect(f"/battle/ws?token={token}&room={code}") as ws:
                self.socket_open = True
                ws.receive_text()
        except WebSocketDisconnect:
            self.socket_open = False

    def on_ready(self) -> None:
        saved = self.session_room
        if saved and self.token:
            self.connect(saved, self.token)

    def poll_once(self) -> None:
        if not self.room_code:
            return
        self.room_gets += 1
        response = self.client.get(f"/battle/rooms/{self.room_code}")
        if response.status_code == 404:
            self.disconnect()
            self.session_room = None
            self.room_code = None
            self.state = None
            return
        if response.status_code != 200:
            return
        info = response.json()
        if info.get("status") == "playing" and self.token and not self.socket_open:
            self.connect(self.room_code)

    def maybe_reconnect(self) -> None:
        if self.room_code and self.token and self.state and not self.socket_open:
            self.connect(self.room_code)

    def run_seconds(self, seconds: int = 30, interval: int = 2) -> None:
        self.on_ready()
        elapsed = interval
        while elapsed <= seconds:
            if not self.room_code:
                break
            self.poll_once()
            self.maybe_reconnect()
            elapsed += interval


def test_legacy_room_tab_stops_after_404(monkeypatch) -> None:
    client, _manager = _client(monkeypatch, enabled=False)
    tab = LegacyRoomTab(client, "OLDROOM", "guest-token")
    tab.run_seconds(30)
    assert tab.room_gets == 1
    assert tab.ws_connects == 1
    assert tab.session_room is None
    assert tab.room_code is None
    assert tab.socket_open is False
    client.close()


def test_legacy_room_tab_would_keep_polling_on_410() -> None:
    app = FastAPI()

    @app.get("/battle/rooms/{code}")
    def gone(code: str) -> None:
        raise HTTPException(status_code=410, detail=f"gone {code}")

    @app.websocket("/battle/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.close(code=1008)

    client = TestClient(app)
    tab = LegacyRoomTab(client, "OLDROOM", "guest-token")
    tab.run_seconds(30)
    assert tab.room_gets == 15
    assert tab.ws_connects == 1
    assert tab.room_code == "OLDROOM"
    assert tab.session_room == "OLDROOM"
    client.close()
