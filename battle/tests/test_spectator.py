"""Spectator mode tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.rooms import RoomManager
from battle.spectator import live_room_summary, room_mode, spectator_view


def _catalog(cid: str) -> dict:
    base = {
        "card_id": cid,
        "name": cid,
        "name_en": cid,
        "colors_en": ["Red"],
        "colors": ["Red"],
    }
    if cid == "LDR":
        return {
            **base,
            "card_type_en": "LEADER",
            "card_type": "LEADER",
            "life": 5,
            "power": 5000,
            "cost": 0,
        }
    return {
        **base,
        "card_type_en": "CHARACTER",
        "card_type": "CHARACTER",
        "cost": 1,
        "power": 1000,
    }


def _deck_cards() -> dict[str, int]:
    cards: dict[str, int] = {}
    for i in range(1, 13):
        cards[f"C{i:02d}"] = 4
    cards["C13"] = 2
    return cards


def _start_ai_room(manager: RoomManager, *, allow: bool = True, show_hands: bool = True):
    host = {
        "user_id": "user_1",
        "username": "host",
        "leader_card_id": "LDR",
        "cards": _deck_cards(),
        "deck_name": "Deck",
    }
    room = manager.create_room(
        host,
        vs_ai=True,
        ai_deck={
            "name": "AI Deck",
            "leader_card_id": "LDR",
            "cards": _deck_cards(),
        },
        allow_spectators=allow,
        spectator_show_hands=show_hands,
    )
    return room


def test_room_mode_ai() -> None:
    manager = RoomManager(_catalog)
    room = _start_ai_room(manager)
    assert room_mode(room) == "ai"
    assert room.match is not None


def test_list_spectatable_only_playing() -> None:
    manager = RoomManager(_catalog)
    room = _start_ai_room(manager, allow=True)
    listed = manager.list_spectatable_rooms("all")
    assert any(r["room_code"] == room.code for r in listed)
    room.allow_spectators = False
    listed2 = manager.list_spectatable_rooms("all")
    assert not any(r["room_code"] == room.code for r in listed2)


def test_spectator_view_hides_hands_when_disabled() -> None:
    manager = RoomManager(_catalog)
    room = _start_ai_room(manager, show_hands=False)
    view = spectator_view(room, _catalog)
    assert view["viewer_role"] == "spectator"
    for p in view["players"]:
        assert p["hand"] == []


def test_spectator_view_shows_hands_when_enabled() -> None:
    manager = RoomManager(_catalog)
    room = _start_ai_room(manager, show_hands=True)
    view = spectator_view(room, _catalog)
    assert any(len(p.get("hand") or []) > 0 for p in view["players"])


def test_live_room_summary() -> None:
    manager = RoomManager(_catalog)
    room = _start_ai_room(manager)
    summary = live_room_summary(room)
    assert summary["mode"] == "ai"
    assert summary["status"] == "playing"
    assert len(summary["players"]) == 2


def test_add_chat_keeps_messages() -> None:
    manager = RoomManager(_catalog)
    room = _start_ai_room(manager)
    payload = manager.add_chat(room, "user_1", "host", "  hello  ")
    assert payload["type"] == "chat"
    assert payload["messages"][-1]["text"] == "hello"
    assert len(room.chat) == 1
