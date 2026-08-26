from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi import WebSocket

from battle.ai import _acting_seat, ai_must_act, step_ai_once
from battle.engine import apply_action, public_view, start_match
from battle.replay import (
    attach_replay_id_to_view,
    init_recording,
    persist_replay,
    record_frame,
)
from battle.spectator import live_room_summary, room_mode, spectator_view
from battle.state import MatchState

CatalogFn = Callable[[str], dict[str, Any]]
LlmFn = Callable[[str], str] | None


def _room_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


@dataclass
class SpectatorSlot:
    user_id: str
    username: str
    ws: WebSocket | None = None


@dataclass
class SeatSlot:
    user_id: str
    username: str
    is_ai: bool
    leader_card_id: str | None = None
    cards: dict[str, int] | None = None
    deck_id: str | None = None
    deck_name: str | None = None
    ready: bool = False
    ws: WebSocket | None = None

    @property
    def has_deck(self) -> bool:
        return bool(self.leader_card_id and self.cards)


@dataclass
class Room:
    code: str
    host_user_id: str
    vs_ai: bool
    hotseat: bool = False
    seats: list[SeatSlot | None] = field(default_factory=lambda: [None, None])
    match: MatchState | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)
    replay_id: str | None = None
    replay_frames: list[dict[str, Any]] = field(default_factory=list)
    replay_log_len: int = 0
    replay_persisted: bool = False
    allow_spectators: bool = True
    spectator_show_hands: bool = True
    ranked: bool = False
    spectators: list[SpectatorSlot] = field(default_factory=list)
    chat: list[dict[str, Any]] = field(default_factory=list)


class RoomManager:
    def __init__(self, catalog: CatalogFn, ask_llm: LlmFn = None):
        self.catalog = catalog
        self.ask_llm = ask_llm
        self.rooms: dict[str, Room] = {}
        self.lock = threading.Lock()

    def cleanup(self, max_age_sec: float = 3 * 3600) -> None:
        now = time.time()
        with self.lock:
            dead = [code for code, room in self.rooms.items() if now - room.updated_at > max_age_sec]
            for code in dead:
                self.rooms.pop(code, None)

    def create_room(
        self,
        host: dict[str, Any],
        vs_ai: bool,
        ai_deck: dict[str, Any] | None = None,
        *,
        hotseat: bool = False,
        opp_deck: dict[str, Any] | None = None,
        allow_spectators: bool = True,
        spectator_show_hands: bool = True,
    ) -> Room:
        """
        PvP: create empty waiting room (deck/ready set later).
        AI: host + AI decks provided → match starts immediately.
        Hotseat: host controls both seats; both decks from the same user → start immediately.
        """
        if hotseat and vs_ai:
            raise ValueError("Hotseat and AI modes are mutually exclusive.")
        self.cleanup()
        with self.lock:
            for _ in range(20):
                code = _room_code()
                if code not in self.rooms:
                    break
            room = Room(
                code=code,
                host_user_id=str(host["user_id"]),
                vs_ai=vs_ai,
                hotseat=bool(hotseat),
                allow_spectators=bool(allow_spectators),
                spectator_show_hands=bool(spectator_show_hands),
            )
            host_slot = SeatSlot(
                user_id=str(host["user_id"]),
                username=str(host.get("username") or "Host"),
                is_ai=False,
                leader_card_id=host.get("leader_card_id"),
                cards=host.get("cards"),
                deck_id=host.get("deck_id"),
                deck_name=host.get("deck_name"),
                ready=False,
            )
            room.seats[0] = host_slot
            if hotseat:
                if not host_slot.has_deck:
                    raise ValueError("Self battle requires your first deck.")
                if not opp_deck or not opp_deck.get("leader_card_id") or not opp_deck.get("cards"):
                    raise ValueError("Self battle requires a second deck.")
                uid = str(host["user_id"])
                base_name = str(host.get("username") or "Player")
                p2_name = str(opp_deck.get("deck_name") or opp_deck.get("name") or "P2")
                room.seats[1] = SeatSlot(
                    user_id=f"{uid}:p2",
                    username=f"{base_name} · {p2_name}",
                    is_ai=False,
                    leader_card_id=opp_deck.get("leader_card_id"),
                    cards=opp_deck.get("cards"),
                    deck_id=opp_deck.get("deck_id"),
                    deck_name=str(opp_deck.get("deck_name") or opp_deck.get("name") or ""),
                    ready=True,
                )
                host_slot.ready = True
                self._start_match(room)
            elif vs_ai:
                if not host_slot.has_deck:
                    raise ValueError("AI battle requires your deck.")
                ai_leader = (ai_deck or {}).get("leader_card_id") or host.get("leader_card_id")
                ai_cards = (ai_deck or {}).get("cards") or host.get("cards")
                ai_name = str((ai_deck or {}).get("name") or "AI")
                room.seats[1] = SeatSlot(
                    user_id="ai",
                    username=f"AI · {ai_name}" if ai_deck else "AI",
                    is_ai=True,
                    leader_card_id=ai_leader,
                    cards=ai_cards,
                    deck_name=ai_name,
                    ready=True,
                )
                self._start_match(room)
            self.rooms[code] = room
            return room

    def create_matched_room(
        self,
        p0: dict[str, Any],
        p1: dict[str, Any],
        *,
        allow_spectators: bool = True,
        spectator_show_hands: bool = True,
        ranked: bool = False,
    ) -> Room:
        """Instant PvP room from matchmaking — both decks ready, match starts now."""
        self.cleanup()
        with self.lock:
            for _ in range(20):
                code = _room_code()
                if code not in self.rooms:
                    break
            room = Room(
                code=code,
                host_user_id=str(p0["user_id"]),
                vs_ai=False,
                hotseat=False,
                allow_spectators=bool(allow_spectators),
                spectator_show_hands=bool(spectator_show_hands),
                ranked=bool(ranked),
            )

            def _slot(player: dict[str, Any]) -> SeatSlot:
                return SeatSlot(
                    user_id=str(player["user_id"]),
                    username=str(player.get("username") or "Player"),
                    is_ai=False,
                    leader_card_id=player.get("leader_card_id"),
                    cards=player.get("cards"),
                    deck_id=player.get("deck_id"),
                    deck_name=player.get("deck_name"),
                    ready=True,
                )

            room.seats[0] = _slot(p0)
            room.seats[1] = _slot(p1)
            if not room.seats[0].has_deck or not room.seats[1].has_deck:
                raise ValueError("Both players need decks.")
            self._start_match(room)
            self.rooms[code] = room
            return room

    def get(self, code: str) -> Room | None:
        return self.rooms.get(str(code or "").strip().upper())

    def join_room(self, code: str, guest: dict[str, Any]) -> Room:
        room = self.get(code)
        if not room:
            raise ValueError("Room not found.")
        with room.lock:
            if room.vs_ai:
                raise ValueError("This room is vs AI.")
            if room.hotseat:
                raise ValueError("This room is self-battle (hotseat).")
            if room.match:
                raise ValueError("Match already started.")
            if room.seats[0] and room.seats[0].user_id == guest["user_id"]:
                return room
            if room.seats[1] and room.seats[1].user_id not in {None, guest["user_id"]}:
                raise ValueError("Room is full.")
            room.seats[1] = SeatSlot(
                user_id=str(guest["user_id"]),
                username=str(guest.get("username") or "Guest"),
                is_ai=False,
                leader_card_id=guest.get("leader_card_id"),
                cards=guest.get("cards"),
                deck_id=guest.get("deck_id"),
                deck_name=guest.get("deck_name"),
                ready=False,
            )
            room.updated_at = time.time()
            return room

    def set_deck(self, room: Room, user_id: str, deck: dict[str, Any]) -> Room:
        with room.lock:
            if room.match:
                raise ValueError("Match already started.")
            seat = self.seat_for_user(room, user_id)
            if seat is None:
                raise ValueError("You are not in this room.")
            slot = room.seats[seat]
            if not slot or slot.is_ai:
                raise ValueError("Invalid seat.")
            slot.leader_card_id = deck.get("leader_card_id")
            slot.cards = deck.get("cards")
            slot.deck_id = deck.get("deck_id")
            slot.deck_name = deck.get("deck_name")
            slot.ready = False  # changing deck clears ready
            room.updated_at = time.time()
            return room

    def set_ready(self, room: Room, user_id: str, ready: bool) -> Room:
        with room.lock:
            if room.match:
                raise ValueError("Match already started.")
            seat = self.seat_for_user(room, user_id)
            if seat is None:
                raise ValueError("You are not in this room.")
            slot = room.seats[seat]
            if not slot or slot.is_ai:
                raise ValueError("Invalid seat.")
            if ready and not slot.has_deck:
                raise ValueError("Select a deck before ready.")
            slot.ready = bool(ready)
            room.updated_at = time.time()
            if self._both_ready(room):
                self._start_match(room)
            return room

    def _both_ready(self, room: Room) -> bool:
        if room.vs_ai:
            return False
        a, b = room.seats[0], room.seats[1]
        if not a or not b:
            return False
        return bool(a.has_deck and b.has_deck and a.ready and b.ready)

    def _start_match(self, room: Room) -> None:
        a, b = room.seats[0], room.seats[1]
        if not a or not b or not a.has_deck or not b.has_deck:
            raise ValueError("Both players need decks.")
        room.match = start_match(
            room.code,
            {
                "user_id": a.user_id,
                "username": a.username,
                "is_ai": a.is_ai,
                "leader_card_id": a.leader_card_id,
                "cards": a.cards,
            },
            {
                "user_id": b.user_id,
                "username": b.username,
                "is_ai": b.is_ai,
                "leader_card_id": b.leader_card_id,
                "cards": b.cards,
            },
            self.catalog,
        )
        init_recording(room)
        record_frame(room, self.catalog)
        # AI autoplay is paced on the WebSocket (broadcast between steps).
        room.updated_at = time.time()

    def _maybe_finish_replay(self, room: Room) -> None:
        if not room.match or room.replay_persisted:
            return
        if room.match.status != "finished":
            return
        if persist_replay(room, self.catalog):
            room.replay_persisted = True
        if room.ranked:
            try:
                from battle.rank import apply_match_result

                apply_match_result(room)
            except Exception:
                pass

    def _attach_elite_badges(self, view: dict[str, Any], room: Room) -> None:
        if not room.match:
            return
        try:
            from battle.rank import elite_badges_for_user_ids, is_registered_user_id

            uids = [
                str(p.user_id)
                for p in room.match.players
                if not getattr(p, "is_ai", False) and is_registered_user_id(str(p.user_id))
            ]
            if not uids:
                return
            badges = elite_badges_for_user_ids(uids)
            for pview in view.get("players") or []:
                if not isinstance(pview, dict):
                    continue
                uid = str(pview.get("user_id") or "")
                badge = badges.get(uid)
                if badge:
                    pview["elite_title"] = badge.get("elite_title")
                    pview["elite_title_zh"] = badge.get("elite_title_zh")
        except Exception:
            pass

    def _public_view_for_room(self, room: Room, seat: int) -> dict[str, Any]:
        view = public_view(room.match, seat, self.catalog)  # type: ignore[arg-type]
        if room.hotseat:
            view["hotseat"] = True
            view["acting_seat"] = self.hotseat_viewer_seat(room)
        if room.ranked:
            view["ranked"] = True
        attach_replay_id_to_view(view, room)
        self._attach_elite_badges(view, room)
        return view

    def can_spectate(self, room: Room) -> bool:
        if not room.match:
            return False
        if room.match.status == "finished":
            return False
        return bool(room.allow_spectators)

    def list_spectatable_rooms(self, mode: str = "all") -> list[dict[str, Any]]:
        self.cleanup()
        want = str(mode or "all").strip().lower()
        out: list[dict[str, Any]] = []
        with self.lock:
            rooms = list(self.rooms.values())
        for room in rooms:
            if not self.can_spectate(room):
                continue
            m = room_mode(room)
            if want not in {"", "all"} and m != want:
                continue
            out.append(live_room_summary(room))
        out.sort(key=lambda r: str(r.get("room_code") or ""))
        return out

    def _spectator_view_for_room(self, room: Room) -> dict[str, Any]:
        view = spectator_view(room, self.catalog)
        self._attach_elite_badges(view, room)
        return view

    def add_spectator(self, room: Room, user_id: str, username: str, ws: WebSocket) -> SpectatorSlot:
        uid = str(user_id)
        for spec in room.spectators:
            if spec.user_id == uid:
                old_ws = spec.ws
                spec.ws = ws
                spec.username = str(username or spec.username)
                if old_ws is not None and old_ws is not ws:
                    # replaced by newer connection
                    pass
                return spec
        slot = SpectatorSlot(user_id=uid, username=str(username or "Spectator"), ws=ws)
        room.spectators.append(slot)
        return slot

    def remove_spectator_ws(self, room: Room, ws: WebSocket) -> None:
        for spec in room.spectators:
            if spec.ws is ws:
                spec.ws = None
        room.spectators = [s for s in room.spectators if s.ws is not None]

    def set_spectator_settings(
        self,
        room: Room,
        user_id: str,
        *,
        allow_spectators: bool | None = None,
        spectator_show_hands: bool | None = None,
    ) -> tuple[Room, list[WebSocket]]:
        if str(user_id) != str(room.host_user_id):
            raise ValueError("Only the room host can change spectator settings.")
        kick: list[WebSocket] = []
        with room.lock:
            if allow_spectators is not None:
                room.allow_spectators = bool(allow_spectators)
                if not room.allow_spectators:
                    kick = [s.ws for s in room.spectators if s.ws]
                    room.spectators = []
            if spectator_show_hands is not None:
                room.spectator_show_hands = bool(spectator_show_hands)
            room.updated_at = time.time()
            return room, kick

    def seat_for_user(self, room: Room, user_id: str) -> int | None:
        for i, slot in enumerate(room.seats):
            if slot and slot.user_id == user_id:
                return i
        return None

    def is_hotseat_host(self, room: Room, user_id: str) -> bool:
        return bool(room.hotseat and str(user_id) == str(room.host_user_id))

    def hotseat_viewer_seat(self, room: Room) -> int:
        """Which seat the hotseat host should see / act as right now."""
        if not room.match:
            return 0
        acting = _acting_seat(room.match)
        if acting is not None:
            return int(acting)
        return int(getattr(room.match, "turn_seat", 0) or 0)

    def waiting_payload(self, room: Room) -> dict[str, Any]:
        def seat_view(s: SeatSlot | None) -> dict[str, Any] | None:
            if not s:
                return None
            return {
                "user_id": s.user_id,
                "username": s.username,
                "is_ai": s.is_ai,
                "ready": bool(s.ready),
                "has_deck": s.has_deck,
                "deck_id": s.deck_id,
                "deck_name": s.deck_name,
                "leader_card_id": s.leader_card_id,
            }

        return {
            "type": "room",
            "room_code": room.code,
            "status": "playing" if room.match else "waiting",
            "vs_ai": room.vs_ai,
            "hotseat": bool(room.hotseat),
            "ranked": bool(room.ranked),
            "allow_spectators": bool(room.allow_spectators),
            "spectator_show_hands": bool(room.spectator_show_hands),
            "can_spectate": self.can_spectate(room),
            "players": [seat_view(s) for s in room.seats],
        }

    def chat_payload(self, room: Room) -> dict[str, Any]:
        return {"type": "chat", "messages": list(room.chat)}

    def add_chat(self, room: Room, user_id: str, username: str, text: str) -> dict[str, Any]:
        body = " ".join(str(text or "").split())
        if not body:
            raise ValueError("Empty chat.")
        if len(body) > 200:
            body = body[:200]
        msg = {
            "id": secrets.token_hex(6),
            "user_id": str(user_id),
            "username": str(username or "Player")[:32],
            "text": body,
            "ts": time.time(),
            "seat": self.seat_for_user(room, user_id),
        }
        with room.lock:
            room.chat.append(msg)
            if len(room.chat) > 80:
                room.chat = room.chat[-80:]
            room.updated_at = time.time()
        return self.chat_payload(room)

    async def broadcast_chat(self, room: Room, payload: dict[str, Any] | None = None) -> None:
        data = payload or self.chat_payload(room)
        sockets: list[WebSocket] = []
        for slot in room.seats:
            if slot and slot.ws and not slot.is_ai:
                sockets.append(slot.ws)
        for spec in room.spectators:
            if spec.ws:
                sockets.append(spec.ws)
        for ws in sockets:
            try:
                await ws.send_json(data)
            except Exception:
                pass

    async def broadcast(self, room: Room) -> None:
        if not room.match:
            payload_waiting = self.waiting_payload(room)
            for slot in room.seats:
                if slot and slot.ws:
                    try:
                        await slot.ws.send_json(payload_waiting)
                    except Exception:
                        slot.ws = None
            return
        if room.hotseat:
            host = room.seats[0]
            if not host or not host.ws:
                return
            seat = self.hotseat_viewer_seat(room)
            view = self._public_view_for_room(room, seat)
            try:
                await host.ws.send_json({"type": "state", "state": view})
            except Exception:
                host.ws = None
            return
        for slot in room.seats:
            if not slot or not slot.ws or slot.is_ai:
                continue
            seat = self.seat_for_user(room, slot.user_id)
            view = self._public_view_for_room(room, seat)  # type: ignore[arg-type]
            try:
                await slot.ws.send_json({"type": "state", "state": view})
            except Exception:
                slot.ws = None
        if room.match:
            spec_view = self._spectator_view_for_room(room)
            dead: list[SpectatorSlot] = []
            for spec in room.spectators:
                if not spec.ws:
                    dead.append(spec)
                    continue
                try:
                    await spec.ws.send_json({"type": "state", "state": spec_view})
                except Exception:
                    spec.ws = None
                    dead.append(spec)
            if dead:
                room.spectators = [s for s in room.spectators if s.ws is not None]

    def ai_should_act(self, room: Room) -> bool:
        if not room.match:
            return False
        with room.lock:
            return ai_must_act(room.match)

    def advance_ai_one_step(self, room: Room) -> bool:
        """Apply one heuristic AI action. Returns True if a step was taken."""
        if not room.match:
            return False
        with room.lock:
            try:
                # Skip LLM during AI autoplay: DeepSeek calls hang with no state push.
                advanced = step_ai_once(room.match, self.catalog, ask_llm=None)
            except Exception:
                # Never leave the WS thread dead mid-prompt; human can still sync/concede.
                room.match.add_log("play.log.effect_unsupported", id="ai")
                advanced = False
            room.updated_at = time.time()
            if advanced:
                record_frame(room, self.catalog)
                self._maybe_finish_replay(room)
            return advanced

    def advance_ai(self, room: Room) -> None:
        """Apply AI until a human must act (no pacing; prefer advance_ai_one_step + sleep)."""
        if not room.match:
            return
        steps = 0
        while steps < 40 and self.ai_should_act(room):
            if not self.advance_ai_one_step(room):
                break
            steps += 1

    def handle_action(
        self,
        room: Room,
        user_id: str,
        action: dict[str, Any],
        *,
        use_llm: bool = True,
    ) -> dict[str, Any]:
        if not room.match:
            return {"ok": False, "error": "Match has not started."}
        # Hotseat: the single browser always acts as whoever must act now.
        # Do not gate on is_hotseat_host alone — a mismatched host_user_id would
        # freeze combat on seat 0 (attack works, block/counter never switches).
        if room.hotseat:
            host_uid = str(room.host_user_id or "")
            slot0 = room.seats[0].user_id if room.seats[0] else None
            if str(user_id) not in {host_uid, str(slot0 or "")}:
                return {"ok": False, "error": "You are not in this room."}
            seat = self.hotseat_viewer_seat(room)
            raw_as = action.get("as_seat") if isinstance(action, dict) else None
            if raw_as is not None:
                try:
                    want = int(raw_as)
                except (TypeError, ValueError):
                    want = -1
                if want in (0, 1):
                    seat = want
            action = {k: v for k, v in dict(action or {}).items() if k != "as_seat"}
        else:
            seat = self.seat_for_user(room, user_id)
        if seat is None:
            return {"ok": False, "error": "You are not in this room."}
        with room.lock:
            try:
                # Apply human action only — AI is advanced separately so the WS
                # handler can broadcast immediately (end turn felt frozen before).
                result = apply_action(
                    room.match,
                    seat,
                    action,
                    self.catalog,
                    # Battle resolution is library/templates only — never live LLM.
                    ask_llm=None,
                )
            except Exception as exc:
                return {"ok": False, "error": f"Action failed: {exc}"}
            room.updated_at = time.time()
            if result.get("ok"):
                record_frame(room, self.catalog)
                self._maybe_finish_replay(room)
            return result
