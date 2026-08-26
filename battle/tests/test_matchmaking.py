"""PvP matchmaking tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.matchmaking import Matchmaker
from battle.rooms import RoomManager


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


def _player(uid: str, name: str) -> dict:
    return {
        "user_id": uid,
        "username": name,
        "leader_card_id": "LDR",
        "cards": _deck_cards(),
        "deck_id": f"d-{uid}",
        "deck_name": f"{name} deck",
    }


def test_two_players_match_immediately() -> None:
    rooms = RoomManager(_catalog)
    mm = Matchmaker(rooms)
    first = mm.join(_player("u1", "A"), allow_spectators=True, spectator_show_hands=True)
    assert first["status"] == "queued"
    second = mm.join(_player("u2", "B"), allow_spectators=True, spectator_show_hands=True)
    assert second["status"] == "matched"
    code = second["room_code"]
    assert code
    room = rooms.get(code)
    assert room is not None and room.match is not None
    again = mm.status("u1")
    assert again["status"] == "matched"
    assert again["room_code"] == code


def test_same_user_does_not_match_self() -> None:
    rooms = RoomManager(_catalog)
    mm = Matchmaker(rooms)
    mm.join(_player("u1", "A"))
    again = mm.join(_player("u1", "A"))
    assert again["status"] == "queued"
    assert len(mm.waiting) == 1


def test_spectator_prefs_use_intersection() -> None:
    rooms = RoomManager(_catalog)
    mm = Matchmaker(rooms)
    mm.join(_player("u1", "A"), allow_spectators=True, spectator_show_hands=True)
    mm.join(_player("u2", "B"), allow_spectators=False, spectator_show_hands=True)
    room = next(iter(rooms.rooms.values()))
    assert room.allow_spectators is False
    assert room.spectator_show_hands is False


def test_leave_returns_to_idle() -> None:
    rooms = RoomManager(_catalog)
    mm = Matchmaker(rooms)
    mm.join(_player("u1", "A"))
    mm.leave("u1")
    assert mm.status("u1")["status"] == "idle"
    second = mm.join(_player("u2", "B"))
    assert second["status"] == "queued"
