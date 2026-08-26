"""Battle replay recording and persistence tests."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle import replay as replay_mod  # noqa: E402
from battle.engine import apply_action  # noqa: E402
from battle.rooms import RoomManager  # noqa: E402


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


@pytest.fixture
def replays_tmp(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        monkeypatch.setattr(replay_mod, "REPLAYS_DIR", root)
        monkeypatch.setattr(replay_mod, "INDEX_FILE", root / "index.sqlite")
        yield root


def _finish_mulligan(room_manager: RoomManager, room) -> None:
    assert room.match
    actor = str(room.host_user_id)
    while room.match.phase == "mulligan":
        room_manager.handle_action(room, actor, {"type": "mulligan", "redraw": False})


def test_registered_match_records_frames_and_persists(replays_tmp: Path) -> None:
    mgr = RoomManager(_catalog)
    spec = {
        "user_id": "user_1",
        "username": "Alice",
        "leader_card_id": "LDR",
        "cards": _deck_cards(),
    }
    opp = {
        "user_id": "user_2",
        "username": "Bob",
        "leader_card_id": "LDR",
        "cards": _deck_cards(),
    }
    room = mgr.create_room(spec, vs_ai=False, hotseat=True, opp_deck=opp)
    assert room.replay_id
    assert len(room.replay_frames) >= 1

    _finish_mulligan(mgr, room)
    assert len(room.replay_frames) >= 2

    seat = mgr.seat_for_user(room, "user_1")
    assert seat is not None
    mgr.handle_action(room, "user_1", {"type": "concede"})
    assert room.match and room.match.status == "finished"
    assert room.replay_persisted

    rid = str(room.replay_id)
    assert (replays_tmp / f"{rid}.json.gz").exists()

    rows = replay_mod.list_replays_for_user("user_1")
    assert len(rows) == 1
    assert rows[0]["id"] == rid
    assert rows[0]["frame_count"] >= 2

    data = replay_mod.load_replay(rid, "user_1")
    assert data is not None
    assert len(data["frames"]) >= 2
    assert data["header"]["winner_seat"] == 1


def test_non_participant_cannot_load_replay(replays_tmp: Path) -> None:
    mgr = RoomManager(_catalog)
    spec = {
        "user_id": "user_10",
        "username": "P1",
        "leader_card_id": "LDR",
        "cards": _deck_cards(),
    }
    opp = {
        "user_id": "user_11",
        "username": "P2",
        "leader_card_id": "LDR",
        "cards": _deck_cards(),
    }
    room = mgr.create_room(spec, vs_ai=False, hotseat=True, opp_deck=opp)
    _finish_mulligan(mgr, room)
    mgr.handle_action(room, "user_10", {"type": "concede"})
    rid = str(room.replay_id)
    assert replay_mod.load_replay(rid, "user_99") is None


def test_guest_match_does_not_persist(replays_tmp: Path) -> None:
    mgr = RoomManager(_catalog)
    spec = {
        "user_id": "guest_abc",
        "username": "Guest",
        "leader_card_id": "LDR",
        "cards": _deck_cards(),
    }
    opp = {
        "user_id": "guest_def",
        "username": "Guest2",
        "leader_card_id": "LDR",
        "cards": _deck_cards(),
    }
    room = mgr.create_room(spec, vs_ai=False, hotseat=True, opp_deck=opp)
    assert room.replay_id is None
    assert room.replay_frames == []
    _finish_mulligan(mgr, room)
    mgr.handle_action(room, "guest_abc", {"type": "concede"})
    assert not room.replay_persisted
    assert list(replays_tmp.glob("*.json.gz")) == []


def test_replay_frame_is_omniscient() -> None:
    from battle.engine import start_match

    state = start_match(
        "X",
        {"user_id": "user_1", "username": "A", "leader_card_id": "LDR", "cards": _deck_cards()},
        {"user_id": "user_2", "username": "B", "leader_card_id": "LDR", "cards": _deck_cards()},
        _catalog,
    )
    frame = replay_mod.replay_frame(state, _catalog, log_delta=[])
    p0_hand = frame["players"][0]["hand"]
    p1_hand = frame["players"][1]["hand"]
    assert isinstance(p0_hand, list) and len(p0_hand) > 0
    assert isinstance(p1_hand, list) and len(p1_hand) > 0
    assert frame.get("legal_actions") == []
