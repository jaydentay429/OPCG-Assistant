"""In-memory PvP matchmaking queue."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from battle.rank import get_rating, is_registered_user_id, match_window
from battle.rooms import RoomManager

WAITING_TTL_SEC = 90.0
MATCHED_TTL_SEC = 300.0


@dataclass
class QueueTicket:
    user_id: str
    username: str
    leader_card_id: str
    cards: dict[str, int]
    deck_id: str | None
    deck_name: str
    allow_spectators: bool
    spectator_show_hands: bool
    joined_at: float = field(default_factory=time.time)
    heartbeat_at: float = field(default_factory=time.time)
    room_code: str | None = None


class Matchmaker:
    def __init__(self, rooms: RoomManager):
        self.rooms = rooms
        self.lock = threading.Lock()
        self.waiting: list[QueueTicket] = []
        self.by_user: dict[str, QueueTicket] = {}

    def join(
        self,
        spec: dict[str, Any],
        *,
        allow_spectators: bool = True,
        spectator_show_hands: bool = True,
    ) -> dict[str, Any]:
        uid = str(spec["user_id"])
        with self.lock:
            self._purge()
            existing = self.by_user.get(uid)
            if existing and existing.room_code:
                room = self.rooms.get(existing.room_code)
                live = bool(room and room.match and str(getattr(room.match, "status", "")) == "playing")
                if live:
                    existing.heartbeat_at = time.time()
                    return self._payload(existing)
                self.by_user.pop(uid, None)

            ticket = QueueTicket(
                user_id=uid,
                username=str(spec.get("username") or "Player"),
                leader_card_id=str(spec.get("leader_card_id") or ""),
                cards=dict(spec.get("cards") or {}),
                deck_id=spec.get("deck_id"),
                deck_name=str(spec.get("deck_name") or ""),
                allow_spectators=bool(allow_spectators),
                spectator_show_hands=bool(spectator_show_hands),
            )
            if not ticket.leader_card_id or not ticket.cards:
                raise ValueError("Select or import a deck.")

            self.waiting = [t for t in self.waiting if t.user_id != uid]
            partner = next((t for t in self.waiting if t.user_id != uid and not t.room_code), None)
            self.by_user[uid] = ticket
            if not partner:
                self.waiting.append(ticket)
                return self._payload(ticket)

            self.waiting = [t for t in self.waiting if t.user_id not in {uid, partner.user_id}]
            allow = ticket.allow_spectators and partner.allow_spectators
            hands = allow and ticket.spectator_show_hands and partner.spectator_show_hands
            room = self.rooms.create_matched_room(
                self._spec(partner),
                self._spec(ticket),
                allow_spectators=allow,
                spectator_show_hands=hands,
            )
            now = time.time()
            partner.room_code = room.code
            ticket.room_code = room.code
            partner.heartbeat_at = now
            ticket.heartbeat_at = now
            self.by_user[partner.user_id] = partner
            self.by_user[uid] = ticket
            return self._payload(ticket)

    def leave(self, user_id: str) -> None:
        uid = str(user_id)
        with self.lock:
            self.by_user.pop(uid, None)
            self.waiting = [t for t in self.waiting if t.user_id != uid]

    def status(self, user_id: str) -> dict[str, Any]:
        uid = str(user_id)
        with self.lock:
            self._purge()
            ticket = self.by_user.get(uid)
            if not ticket:
                return {"status": "idle", "room_code": None, "queued": len(self.waiting)}
            ticket.heartbeat_at = time.time()
            if ticket.room_code:
                room = self.rooms.get(ticket.room_code)
                if not room or not room.match:
                    self.by_user.pop(uid, None)
                    return {"status": "idle", "room_code": None, "queued": len(self.waiting)}
            return self._payload(ticket)

    def _purge(self) -> None:
        now = time.time()
        keep: list[QueueTicket] = []
        for ticket in self.waiting:
            if now - ticket.heartbeat_at > WAITING_TTL_SEC:
                if self.by_user.get(ticket.user_id) is ticket:
                    self.by_user.pop(ticket.user_id, None)
                continue
            keep.append(ticket)
        self.waiting = keep
        dead: list[str] = []
        for uid, ticket in self.by_user.items():
            if ticket.room_code:
                room = self.rooms.get(ticket.room_code)
                stale = now - ticket.heartbeat_at > MATCHED_TTL_SEC
                if stale or not room:
                    dead.append(uid)
            elif ticket not in self.waiting:
                dead.append(uid)
        for uid in dead:
            self.by_user.pop(uid, None)

    def _spec(self, ticket: QueueTicket) -> dict[str, Any]:
        return {
            "user_id": ticket.user_id,
            "username": ticket.username,
            "leader_card_id": ticket.leader_card_id,
            "cards": ticket.cards,
            "deck_id": ticket.deck_id,
            "deck_name": ticket.deck_name,
        }

    def _payload(self, ticket: QueueTicket) -> dict[str, Any]:
        if ticket.room_code:
            return {
                "status": "matched",
                "room_code": ticket.room_code,
                "queued": len(self.waiting),
            }
        return {
            "status": "queued",
            "room_code": None,
            "queued": len(self.waiting),
            "waited_sec": int(max(0, time.time() - ticket.joined_at)),
        }


@dataclass
class RankedQueueTicket(QueueTicket):
    rating: int = 1000


class RankedMatchmaker(Matchmaker):
    """Rating-aware queue separate from casual matchmaking."""

    def join(
        self,
        spec: dict[str, Any],
        *,
        allow_spectators: bool = True,
        spectator_show_hands: bool = True,
    ) -> dict[str, Any]:
        uid = str(spec["user_id"])
        if not is_registered_user_id(uid):
            raise PermissionError("Ranked matchmaking requires a registered account.")
        rating = int(spec.get("rating") or get_rating(uid))
        spec = {**spec, "rating": rating}
        with self.lock:
            self._purge()
            existing = self.by_user.get(uid)
            if existing and existing.room_code:
                room = self.rooms.get(existing.room_code)
                live = bool(room and room.match and str(getattr(room.match, "status", "")) == "playing")
                if live:
                    existing.heartbeat_at = time.time()
                    return self._payload(existing)
                self.by_user.pop(uid, None)

            ticket = RankedQueueTicket(
                user_id=uid,
                username=str(spec.get("username") or "Player"),
                leader_card_id=str(spec.get("leader_card_id") or ""),
                cards=dict(spec.get("cards") or {}),
                deck_id=spec.get("deck_id"),
                deck_name=str(spec.get("deck_name") or ""),
                allow_spectators=bool(allow_spectators),
                spectator_show_hands=bool(spectator_show_hands),
                rating=rating,
            )
            if not ticket.leader_card_id or not ticket.cards:
                raise ValueError("Select or import a deck.")

            self.waiting = [t for t in self.waiting if t.user_id != uid]
            partner = self._find_partner(ticket)
            self.by_user[uid] = ticket
            if not partner:
                self.waiting.append(ticket)
                return self._payload(ticket)

            self.waiting = [t for t in self.waiting if t.user_id not in {uid, partner.user_id}]
            allow = ticket.allow_spectators and partner.allow_spectators
            hands = allow and ticket.spectator_show_hands and partner.spectator_show_hands
            room = self.rooms.create_matched_room(
                self._spec(partner),
                self._spec(ticket),
                allow_spectators=allow,
                spectator_show_hands=hands,
                ranked=True,
            )
            now = time.time()
            partner.room_code = room.code
            ticket.room_code = room.code
            partner.heartbeat_at = now
            ticket.heartbeat_at = now
            self.by_user[partner.user_id] = partner
            self.by_user[uid] = ticket
            return self._payload(ticket)

    def _find_partner(self, ticket: RankedQueueTicket) -> RankedQueueTicket | None:
        now = time.time()
        my_wait = now - ticket.joined_at
        my_window = match_window(my_wait)
        candidates: list[tuple[int, float, RankedQueueTicket]] = []
        for other in self.waiting:
            if other.user_id == ticket.user_id or other.room_code:
                continue
            if not isinstance(other, RankedQueueTicket):
                continue
            other_wait = now - other.joined_at
            window = match_window(max(my_wait, other_wait))
            diff = abs(ticket.rating - other.rating)
            if diff <= window:
                candidates.append((diff, other.joined_at, other))
        if not candidates:
            return None
        candidates.sort(key=lambda c: (c[0], c[1]))
        return candidates[0][2]

    def _payload(self, ticket: QueueTicket) -> dict[str, Any]:
        base = super()._payload(ticket)
        if isinstance(ticket, RankedQueueTicket):
            base["rating"] = ticket.rating
            if base.get("status") == "queued":
                waited = int(base.get("waited_sec") or 0)
                base["match_window"] = match_window(waited)
        return base
