"""Live spectator views for in-progress matches."""

from __future__ import annotations

from typing import Any, Callable

from battle.replay import replay_frame

CatalogFn = Callable[[str], dict[str, Any]]


def room_mode(room: Any) -> str:
    if getattr(room, "ranked", False):
        return "ranked"
    if room.hotseat:
        return "hotseat"
    if room.vs_ai:
        return "ai"
    return "pvp"


def spectator_view(room: Any, catalog: CatalogFn) -> dict[str, Any]:
    """Read-only board state for spectators."""
    state = room.match
    if not state:
        raise ValueError("No active match.")
    frame = replay_frame(state, catalog, log_delta=None)
    frame["log"] = list(state.log[-24:])
    if not room.spectator_show_hands:
        for p in frame.get("players") or []:
            if isinstance(p, dict):
                p["hand"] = []
    frame["viewer_seat"] = 0
    frame["acting_seat"] = int(state.turn_seat)
    frame["viewer_role"] = "spectator"
    frame["spectator_mode"] = room_mode(room)
    frame["spectator_show_hands"] = bool(room.spectator_show_hands)
    frame["vs_ai"] = bool(room.vs_ai)
    frame["hotseat"] = bool(room.hotseat)
    frame["legal_actions"] = []
    frame["replay_mode"] = bool(room.spectator_show_hands)
    return frame


def live_room_summary(room: Any) -> dict[str, Any]:
    match = room.match
    players: list[dict[str, Any] | None] = []
    for slot in room.seats:
        if not slot:
            players.append(None)
            continue
        players.append(
            {
                "username": slot.username,
                "is_ai": bool(slot.is_ai),
                "leader_card_id": slot.leader_card_id,
            }
        )
    return {
        "room_code": room.code,
        "mode": room_mode(room),
        "status": "playing",
        "turn_number": int(match.turn_number) if match else 0,
        "players": players,
        "spectator_count": len(room.spectators),
        "show_hands": bool(room.spectator_show_hands),
    }
