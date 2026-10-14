"""Leaving a room must clear a waiting guest and block reattach during a match."""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if "battle" not in sys.modules:
    pkg = types.ModuleType("battle")
    pkg.__path__ = [str(ROOT / "battle")]
    sys.modules["battle"] = pkg

from battle.rooms import RoomManager  # noqa: E402


def test_waiting_guest_leave_clears_seat_and_host_closes_room():
    mgr = RoomManager(lambda _cid: {})
    room = mgr.create_room({"user_id": "host", "username": "Host"}, False)
    mgr.join_room(room.code, {"user_id": "guest", "username": "Guest"})
    assert mgr.depart_user(room, "guest") == "left"
    assert room.seats[1] is None
    assert mgr.depart_user(room, "host") == "closed"
    assert mgr.get(room.code) is None


def test_in_match_depart_rejects_reattach():
    mgr = RoomManager(lambda _cid: {})
    room = mgr.create_room({"user_id": "host", "username": "Host"}, False)
    mgr.join_room(room.code, {"user_id": "guest", "username": "Guest"})
    room.match = types.SimpleNamespace(status="playing")  # type: ignore[assignment]
    assert mgr.depart_user(room, "guest") == "departed"
    slot = room.seats[1]
    assert slot is not None and slot.departed is True
    assert mgr.seat_for_user(room, "guest") == 1
