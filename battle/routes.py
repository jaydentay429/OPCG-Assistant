from __future__ import annotations

import asyncio
import json
import secrets
import time
from typing import Any, Callable

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from battle.ai_decks import get_ai_deck, load_ai_decks
from battle.effect_library import ensure_loaded, library_stats
from battle.engine import public_view, ranked_deck_ban_error, validate_battle_deck
from battle.replay import list_replays_for_user, load_replay
from battle.matchmaking import Matchmaker, RankedMatchmaker
from battle.rank import (
    build_appeal_admin_email,
    elite_roster,
    get_appeal_by_id,
    get_appeal_status,
    get_user_profile,
    leaderboard,
    match_history,
    review_ranked_appeal,
    submit_ranked_appeal,
    verify_appeal_review_token,
)
from battle.rooms import RoomManager


CatalogFn = Callable[[str], dict[str, Any]]
AuthFn = Callable[[str], dict[str, Any] | None]
DeckFn = Callable[[str, str], dict[str, Any] | None]
LlmFn = Callable[[str], str] | None
EmailFn = Callable[..., None]

AI_STEP_DELAY_SEC = 2.0
GUEST_TOKEN_TTL_SEC = 24 * 3600

# Ephemeral guests for unauthenticated battle rooms.
_guest_sessions: dict[str, dict[str, Any]] = {}
_ai_pace_locks: dict[str, asyncio.Lock] = {}


class InlineDeck(BaseModel):
    leader_card_id: str
    cards: dict[str, int] = Field(default_factory=dict)
    name: str | None = None


class CreateRoomRequest(BaseModel):
    deck_id: str | None = None
    deck: InlineDeck | None = None
    vs_ai: bool = False
    ai_deck_id: str | None = None
    hotseat: bool = False
    opp_deck_id: str | None = None
    opp_deck: InlineDeck | None = None
    allow_spectators: bool = True
    spectator_show_hands: bool = True


class SpectatorSettingsRequest(BaseModel):
    allow_spectators: bool | None = None
    spectator_show_hands: bool | None = None


class MatchJoinRequest(BaseModel):
    deck_id: str | None = None
    deck: InlineDeck | None = None
    allow_spectators: bool = True
    spectator_show_hands: bool = True


class JoinRoomRequest(BaseModel):
    deck_id: str | None = None
    deck: InlineDeck | None = None


class SetDeckRequest(BaseModel):
    deck_id: str | None = None
    deck: InlineDeck | None = None


class SetReadyRequest(BaseModel):
    ready: bool = True


class BugReportRequest(BaseModel):
    message: str
    room_code: str | None = None
    phase: str | None = None
    turn_number: int | None = None
    page_url: str | None = None


class RankAppealRequest(BaseModel):
    room_code: str
    message: str
    replay_id: str | None = None


class RankAppealReviewRequest(BaseModel):
    appeal_id: int
    action: str
    note: str | None = None


def _purge_guest_sessions() -> None:
    now = time.time()
    dead = [tok for tok, meta in _guest_sessions.items() if float(meta.get("expires_at") or 0) <= now]
    for tok in dead:
        _guest_sessions.pop(tok, None)


def _mint_guest_user(username: str = "Guest") -> tuple[str, dict[str, Any]]:
    _purge_guest_sessions()
    token = secrets.token_urlsafe(24)
    suffix = secrets.token_hex(3)
    base = str(username or "Guest")[:32] or "Guest"
    user = {
        "user_id": f"guest_{secrets.token_hex(8)}",
        "username": f"{base}-{suffix}",
        "is_guest": True,
    }
    _guest_sessions[token] = {
        **user,
        "expires_at": time.time() + GUEST_TOKEN_TTL_SEC,
    }
    return token, user


def _guest_user_from_token(token: str) -> dict[str, Any] | None:
    _purge_guest_sessions()
    meta = _guest_sessions.get(str(token or "").strip())
    if not meta:
        return None
    return {
        "user_id": str(meta["user_id"]),
        "username": str(meta.get("username") or "Guest"),
        "is_guest": True,
    }


def _ai_pace_lock(room_code: str) -> asyncio.Lock:
    code = str(room_code or "")
    lock = _ai_pace_locks.get(code)
    if lock is None:
        lock = asyncio.Lock()
        _ai_pace_locks[code] = lock
    return lock


def mount_battle(
    app: FastAPI,
    *,
    catalog: CatalogFn,
    auth_from_token: AuthFn,
    auth_from_request: Callable[[Request], dict[str, Any]],
    load_deck: DeckFn,
    ask_llm: LlmFn = None,
    send_email: EmailFn = None,
) -> RoomManager:
    ensure_loaded()
    manager = RoomManager(catalog, ask_llm=ask_llm)
    matchmaker = Matchmaker(manager)
    ranked_matchmaker = RankedMatchmaker(manager)
    router = APIRouter(tags=["battle"])

    def _resolve_token_user(token: str) -> dict[str, Any] | None:
        user = auth_from_token(token)
        if user:
            return user
        return _guest_user_from_token(token)

    def _try_auth_user(request: Request) -> dict[str, Any] | None:
        auth_header = str(request.headers.get("Authorization") or "")
        token = ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
        if not token:
            token = str(request.cookies.get("opcg_token") or request.cookies.get("token") or "").strip()
        if token:
            guest = _guest_user_from_token(token)
            if guest:
                return guest
        try:
            return auth_from_request(request)
        except HTTPException as exc:
            if exc.status_code == 401:
                return None
            raise

    def _require_user(request: Request, *, allow_guest: bool = True) -> tuple[dict[str, Any], str | None]:
        """Returns (user, guest_token_if_minted)."""
        user = _try_auth_user(request)
        if user:
            if not allow_guest and user.get("is_guest"):
                raise HTTPException(status_code=401, detail="请先登录。")
            return user, None
        if not allow_guest:
            raise HTTPException(status_code=401, detail="请先登录。")
        token, guest = _mint_guest_user()
        return guest, token

    def _require_registered_user(request: Request) -> dict[str, Any]:
        user = _try_auth_user(request)
        if not user or user.get("is_guest"):
            raise HTTPException(status_code=401, detail="请先登录。")
        return user

    @router.get("/battle/effect-library/stats")
    def effect_library_stats() -> dict[str, Any]:
        ensure_loaded()
        return library_stats()

    class EffectOverrideBody(BaseModel):
        card_id: str
        abilities: list[dict[str, Any]]
        version: int = 1

    @router.post("/battle/effect-library/override")
    def put_effect_override(payload: EffectOverrideBody) -> dict[str, Any]:
        """Write a human override into card_effect_overrides.json and reload."""
        from battle.effect_library import library_paths, reload_effect_library
        from battle.effect_schema import normalize_card_entry

        _lib_path, ovr_path = library_paths()
        cards: dict[str, Any] = {}
        if ovr_path.exists():
            try:
                raw = json.loads(ovr_path.read_text(encoding="utf-8"))
                cards = dict((raw or {}).get("cards") or {})
            except Exception:
                cards = {}
        entry = normalize_card_entry(
            payload.card_id,
            {"version": payload.version, "abilities": payload.abilities},
        )
        cards[payload.card_id] = entry
        ovr_path.parent.mkdir(parents=True, exist_ok=True)
        ovr_path.write_text(
            json.dumps({"version": 1, "cards": cards}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        reload_effect_library(force=True)
        return {"ok": True, "card_id": payload.card_id, "abilities": entry.get("abilities") or []}

    def _inline_deck_payload(user: dict[str, Any], deck: InlineDeck) -> dict[str, Any]:
        leader = str(deck.leader_card_id or "").strip()
        cards = {str(k): int(v) for k, v in (deck.cards or {}).items() if int(v or 0) > 0}
        err = validate_battle_deck(leader, cards, catalog)
        if err:
            raise HTTPException(status_code=400, detail=err)
        name = str(deck.name or "Imported").strip()[:80] or "Imported"
        return {
            "user_id": str(user["user_id"]),
            "username": str(user.get("username") or "Player"),
            "leader_card_id": leader,
            "cards": cards,
            "deck_id": None,
            "deck_name": name,
        }

    def _deck_payload(user: dict[str, Any], deck_id: str) -> dict[str, Any]:
        if user.get("is_guest"):
            raise HTTPException(status_code=400, detail="Guests must import a deck (inline).")
        deck = load_deck(str(user["user_id"]), deck_id)
        if not deck:
            raise HTTPException(status_code=404, detail="Deck not found.")
        leader = str(deck.get("leader_card_id") or "")
        cards = {str(k): int(v) for k, v in (deck.get("cards") or {}).items() if int(v or 0) > 0}
        err = validate_battle_deck(leader, cards, catalog)
        if err:
            raise HTTPException(status_code=400, detail=err)
        return {
            "user_id": str(user["user_id"]),
            "username": str(user.get("username") or "Player"),
            "leader_card_id": leader,
            "cards": cards,
            "deck_id": str(deck_id),
            "deck_name": str(deck.get("name") or deck_id),
        }

    def _resolve_player_deck(
        user: dict[str, Any],
        *,
        deck_id: str | None,
        inline: InlineDeck | None,
    ) -> dict[str, Any]:
        if inline is not None:
            return _inline_deck_payload(user, inline)
        if deck_id:
            return _deck_payload(user, deck_id)
        raise HTTPException(status_code=400, detail="Select or import a deck.")

    def _user_only(user: dict[str, Any]) -> dict[str, Any]:
        return {
            "user_id": str(user["user_id"]),
            "username": str(user.get("username") or "Player"),
        }

    def _ai_deck_payload(ai_deck_id: str | None) -> dict[str, Any] | None:
        if not ai_deck_id:
            return None
        deck = get_ai_deck(ai_deck_id)
        if not deck:
            raise HTTPException(status_code=404, detail="AI deck not found.")
        err = validate_battle_deck(str(deck["leader_card_id"]), dict(deck["cards"]), catalog)
        if err:
            raise HTTPException(status_code=400, detail=f"AI deck invalid: {err}")
        return {
            "name": deck["name"],
            "leader_card_id": deck["leader_card_id"],
            "cards": dict(deck["cards"]),
        }

    def _room_info(
        room: Any,
        *,
        guest_token: str | None = None,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = manager.waiting_payload(room)
        if guest_token:
            payload["guest_token"] = guest_token
        if user and user.get("is_guest"):
            payload["guest_user_id"] = str(user.get("user_id") or "")
            payload["guest_username"] = str(user.get("username") or "")
        return payload

    async def _paced_advance_ai(room_obj: Any, push_state: Callable[[], Any]) -> None:
        if not room_obj.vs_ai:
            return
        async with _ai_pace_lock(room_obj.code):
            steps = 0
            while steps < 40 and manager.ai_should_act(room_obj):
                await asyncio.sleep(AI_STEP_DELAY_SEC)
                advanced = await asyncio.to_thread(manager.advance_ai_one_step, room_obj)
                if not advanced:
                    break
                await push_state()
                await manager.broadcast(room_obj)
                steps += 1

    def _spawn_ai(room_obj: Any, push_state: Callable[[], Any]) -> None:
        """Keep the WS receive loop free so chat/ping still work during AI turns."""
        if not room_obj.vs_ai or not manager.ai_should_act(room_obj):
            return
        asyncio.create_task(_paced_advance_ai(room_obj, push_state))

    @router.get("/battle/ai-decks")
    def list_ai_decks() -> dict[str, Any]:
        decks = load_ai_decks()
        return {
            "decks": [
                {
                    "id": d["id"],
                    "name": d["name"],
                    "leader_card_id": d["leader_card_id"],
                    "non_leader_count": d["non_leader_count"],
                }
                for d in decks
            ]
        }

    @router.post("/battle/guest-token")
    def mint_guest_token() -> dict[str, Any]:
        token, guest = _mint_guest_user()
        return {
            "guest_token": token,
            "guest_user_id": guest["user_id"],
            "guest_username": guest["username"],
        }

    @router.post("/battle/rooms")
    def create_room(request: Request, payload: CreateRoomRequest) -> dict[str, Any]:
        user, guest_token = _require_user(request, allow_guest=True)
        try:
            if payload.hotseat:
                if payload.vs_ai:
                    raise HTTPException(status_code=400, detail="Cannot combine hotseat with AI.")
                if not ((payload.deck_id or payload.deck) and (payload.opp_deck_id or payload.opp_deck)):
                    raise HTTPException(status_code=400, detail="Select or import both decks for self battle.")
                spec = _resolve_player_deck(user, deck_id=payload.deck_id, inline=payload.deck)
                if payload.opp_deck is not None:
                    opp = _inline_deck_payload(user, payload.opp_deck)
                else:
                    opp = _deck_payload(user, str(payload.opp_deck_id))
                room = manager.create_room(
                    spec,
                    vs_ai=False,
                    hotseat=True,
                    opp_deck=opp,
                    allow_spectators=payload.allow_spectators,
                    spectator_show_hands=payload.spectator_show_hands,
                )
            elif payload.vs_ai:
                if not (payload.deck_id or payload.deck):
                    raise HTTPException(status_code=400, detail="Select or import your deck for AI battle.")
                spec = _resolve_player_deck(user, deck_id=payload.deck_id, inline=payload.deck)
                ai_spec = _ai_deck_payload(payload.ai_deck_id)
                if ai_spec is None:
                    pool = load_ai_decks()
                    if pool:
                        ai_spec = _ai_deck_payload(str(pool[0]["id"]))
                room = manager.create_room(
                    spec,
                    vs_ai=True,
                    ai_deck=ai_spec,
                    allow_spectators=payload.allow_spectators,
                    spectator_show_hands=payload.spectator_show_hands,
                )
            else:
                room = manager.create_room(
                    _user_only(user),
                    vs_ai=False,
                    allow_spectators=payload.allow_spectators,
                    spectator_show_hands=payload.spectator_show_hands,
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _room_info(room, guest_token=guest_token, user=user)

    def _match_payload(
        result: dict[str, Any],
        *,
        guest_token: str | None = None,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(result)
        if guest_token:
            payload["guest_token"] = guest_token
        if user and user.get("is_guest"):
            payload["guest_user_id"] = str(user.get("user_id") or "")
            payload["guest_username"] = str(user.get("username") or "")
        return payload

    @router.post("/battle/matchmaking/join")
    def join_matchmaking(request: Request, payload: MatchJoinRequest) -> dict[str, Any]:
        user, guest_token = _require_user(request, allow_guest=True)
        spec = _resolve_player_deck(user, deck_id=payload.deck_id, inline=payload.deck)
        try:
            result = matchmaker.join(
                spec,
                allow_spectators=payload.allow_spectators,
                spectator_show_hands=payload.spectator_show_hands,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _match_payload(result, guest_token=guest_token, user=user)

    @router.post("/battle/matchmaking/leave")
    def leave_matchmaking(request: Request) -> dict[str, Any]:
        user, guest_token = _require_user(request, allow_guest=True)
        matchmaker.leave(str(user["user_id"]))
        return _match_payload(
            {"status": "idle", "room_code": None, "queued": 0},
            guest_token=guest_token,
            user=user,
        )

    @router.get("/battle/matchmaking/status")
    def matchmaking_status(request: Request) -> dict[str, Any]:
        user, guest_token = _require_user(request, allow_guest=True)
        result = matchmaker.status(str(user["user_id"]))
        return _match_payload(result, guest_token=guest_token, user=user)

    @router.post("/battle/ranked/join")
    def join_ranked(request: Request, payload: MatchJoinRequest) -> dict[str, Any]:
        user = _require_registered_user(request)
        spec = _resolve_player_deck(user, deck_id=payload.deck_id, inline=payload.deck)
        ban_err = ranked_deck_ban_error(str(spec["leader_card_id"]), dict(spec["cards"]))
        if ban_err:
            raise HTTPException(status_code=400, detail=ban_err)
        try:
            result = ranked_matchmaker.join(
                spec,
                allow_spectators=payload.allow_spectators,
                spectator_show_hands=payload.spectator_show_hands,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result

    @router.post("/battle/ranked/leave")
    def leave_ranked(request: Request) -> dict[str, Any]:
        user = _require_registered_user(request)
        ranked_matchmaker.leave(str(user["user_id"]))
        return {"status": "idle", "room_code": None, "queued": 0}

    @router.get("/battle/ranked/status")
    def ranked_status(request: Request) -> dict[str, Any]:
        user = _require_registered_user(request)
        return ranked_matchmaker.status(str(user["user_id"]))

    @router.get("/battle/rank/me")
    def rank_me(request: Request) -> dict[str, Any]:
        user = _require_registered_user(request)
        return get_user_profile(str(user["user_id"]))

    @router.get("/battle/rank/leaderboard")
    def rank_leaderboard(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
        return {"entries": leaderboard(limit=limit)}

    @router.get("/battle/rank/elite")
    def rank_elite() -> dict[str, Any]:
        return elite_roster()

    @router.get("/battle/rank/history")
    def rank_history(request: Request, limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
        user = _require_registered_user(request)
        return {"matches": match_history(str(user["user_id"]), limit=limit)}

    @router.get("/battle/rank/appeal/status")
    def rank_appeal_status(request: Request, room_code: str = Query(..., min_length=4)) -> dict[str, Any]:
        user = _require_registered_user(request)
        return get_appeal_status(str(user["user_id"]), room_code)

    def _appeal_review_html(title: str, message: str, *, ok: bool = True) -> str:
        accent = "#16a34a" if ok else "#dc2626"
        return f"""<!DOCTYPE html>
<html lang="zh-Hans"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · OPCG</title></head>
<body style="font-family:Segoe UI,PingFang SC,sans-serif;background:#0f172a;color:#f1f5f9;padding:24px;line-height:1.55">
<div style="max-width:520px;margin:40px auto;background:#1e293b;border:1px solid #334155;border-radius:12px;padding:24px">
<h1 style="margin:0 0 12px;font-size:1.35rem;color:{accent}">{title}</h1>
<p style="margin:0 0 16px">{message}</p>
<p style="margin:0;color:#94a3b8;font-size:0.9rem">OPCG 卡牌助手 · 排位平反</p>
</div></body></html>"""

    @router.get("/battle/rank/appeal/review")
    def rank_appeal_review_click(
        appeal_id: int = Query(..., ge=1),
        action: str = Query(...),
        token: str = Query(...),
    ) -> HTMLResponse:
        act = str(action or "").strip().lower()
        if act not in {"approve", "reject"}:
            return HTMLResponse(
                _appeal_review_html("无效操作", "链接参数不正确。", ok=False),
                status_code=400,
            )
        if not verify_appeal_review_token(appeal_id, act, token):
            return HTMLResponse(
                _appeal_review_html("链接无效或已过期", "请从最新邮件重新打开，或使用管理员工具。", ok=False),
                status_code=403,
            )

        appeal = get_appeal_by_id(appeal_id)
        if not appeal:
            return HTMLResponse(
                _appeal_review_html("申请不存在", f"找不到编号 #{appeal_id} 的申请。", ok=False),
                status_code=404,
            )

        room_code = str(appeal.get("room_code") or "")
        status = str(appeal.get("status") or "")
        if status != "pending":
            if act == "approve" and status == "approved":
                msg = f"房间 {room_code} 的排位分数此前已退回，双方胜负记录已撤销。"
                return HTMLResponse(_appeal_review_html("已处理", msg, ok=True))
            if act == "reject" and status == "rejected":
                return HTMLResponse(_appeal_review_html("已驳回", "该申请此前已驳回。", ok=True))
            return HTMLResponse(
                _appeal_review_html("已处理", f"申请 #{appeal_id} 当前状态：{status}。", ok=True),
            )

        try:
            result = review_ranked_appeal(appeal_id, act, note="email-link")
        except ValueError as exc:
            return HTMLResponse(
                _appeal_review_html("处理失败", str(exc), ok=False),
                status_code=400,
            )

        if act == "approve":
            msg = (
                f"已确认房间 {result.get('room_code') or room_code} 存在 Bug。"
                f"双方分数已恢复（P0 → {result.get('p0_rating_restored')}，"
                f"P1 → {result.get('p1_rating_restored')}），该局胜负不计入战绩。"
            )
            return HTMLResponse(_appeal_review_html("已确认 Bug · 分数已退回", msg, ok=True))
        return HTMLResponse(_appeal_review_html("已驳回", "申请未通过，分数与胜负保持不变。", ok=True))

    @router.post("/battle/rank/appeal")
    def submit_rank_appeal(request: Request, payload: RankAppealRequest) -> dict[str, Any]:
        user = _require_registered_user(request)
        try:
            result = submit_ranked_appeal(
                str(user["user_id"]),
                str(user.get("username") or "Player"),
                room_code=payload.room_code,
                description=payload.message,
                replay_id=payload.replay_id,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        import os

        to_email = str(
            os.getenv("RANK_APPEAL_EMAIL") or os.getenv("BUG_REPORT_EMAIL") or os.getenv("SMTP_FROM") or ""
        ).strip()
        api_base = str(os.getenv("API_BASE_URL") or "http://127.0.0.1:8000").strip().rstrip("/")
        subject, body, html = build_appeal_admin_email(
            appeal_id=int(result["appeal_id"]),
            room_code=payload.room_code,
            replay_id=payload.replay_id,
            reporter_username=str(user.get("username") or "Player"),
            reporter_user_id=str(user["user_id"]),
            message=payload.message.strip(),
            api_base=api_base,
        )
        if to_email and send_email:
            try:
                send_email(to_email, subject, body, html=html)
            except TypeError:
                send_email(to_email, subject, body)
            except Exception as exc:
                print(f"[rank-appeal] send failed: {exc}\n{body}")
        else:
            print(f"[rank-appeal] appeal_id={result['appeal_id']} room={payload.room_code}\n{body}")
            if html:
                print(f"[rank-appeal html]\n{html[:600]}")

        return result

    @router.post("/battle/rank/appeal/review")
    def review_rank_appeal_route(request: Request, payload: RankAppealReviewRequest) -> dict[str, Any]:
        import os

        token = str(request.headers.get("X-Rank-Appeal-Admin-Token") or "").strip()
        expected = str(os.getenv("RANK_APPEAL_ADMIN_TOKEN") or os.getenv("ANALYTICS_ADMIN_TOKEN") or "").strip()
        if not expected or token != expected:
            raise HTTPException(status_code=403, detail="Admin token required.")
        try:
            return review_ranked_appeal(payload.appeal_id, payload.action, note=str(payload.note or ""))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/battle/rooms/live")
    def list_live_spectatable_rooms(mode: str = Query("all")) -> dict[str, Any]:
        rooms = manager.list_spectatable_rooms(mode)
        return {"rooms": rooms}

    @router.post("/battle/rooms/{code}/spectator-settings")
    async def set_spectator_settings(
        code: str,
        request: Request,
        payload: SpectatorSettingsRequest,
    ) -> dict[str, Any]:
        user, guest_token = _require_user(request, allow_guest=True)
        room = manager.get(code)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found.")
        try:
            _, kick = manager.set_spectator_settings(
                room,
                str(user["user_id"]),
                allow_spectators=payload.allow_spectators,
                spectator_show_hands=payload.spectator_show_hands,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        for spec_ws in kick:
            try:
                await spec_ws.close()
            except Exception:
                pass
        await manager.broadcast(room)
        return _room_info(room, guest_token=guest_token, user=user)

    @router.get("/battle/rooms/{code}")
    def get_room(code: str) -> dict[str, Any]:
        room = manager.get(code)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found.")
        return _room_info(room)

    @router.post("/battle/rooms/{code}/join")
    async def join_room(code: str, request: Request, payload: JoinRoomRequest = JoinRoomRequest()) -> dict[str, Any]:
        user, guest_token = _require_user(request, allow_guest=True)
        try:
            if payload.deck or payload.deck_id:
                spec = _resolve_player_deck(user, deck_id=payload.deck_id, inline=payload.deck)
            else:
                spec = _user_only(user)
            room = manager.join_room(code, spec)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await manager.broadcast(room)
        return _room_info(room, guest_token=guest_token, user=user)

    @router.post("/battle/rooms/{code}/deck")
    async def set_deck(code: str, request: Request, payload: SetDeckRequest) -> dict[str, Any]:
        user, guest_token = _require_user(request, allow_guest=True)
        room = manager.get(code)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found.")
        if not (payload.deck or payload.deck_id):
            raise HTTPException(status_code=400, detail="Select or import a deck.")
        try:
            deck = _resolve_player_deck(user, deck_id=payload.deck_id, inline=payload.deck)
            manager.set_deck(room, str(user["user_id"]), deck)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await manager.broadcast(room)
        return _room_info(room, guest_token=guest_token, user=user)

    @router.post("/battle/rooms/{code}/ready")
    async def set_ready(code: str, request: Request, payload: SetReadyRequest) -> dict[str, Any]:
        user, guest_token = _require_user(request, allow_guest=True)
        room = manager.get(code)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found.")
        try:
            manager.set_ready(room, str(user["user_id"]), bool(payload.ready))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await manager.broadcast(room)
        return _room_info(room, guest_token=guest_token, user=user)

    def _require_registered_user(request: Request) -> dict[str, Any]:
        user = _try_auth_user(request)
        if not user or user.get("is_guest"):
            raise HTTPException(status_code=401, detail="请先登录。")
        return user

    @router.get("/battle/replays")
    def list_replays(request: Request) -> dict[str, Any]:
        user = _require_registered_user(request)
        matches = list_replays_for_user(str(user["user_id"]))
        return {"matches": matches}

    @router.get("/battle/replays/{replay_id}")
    def get_replay(replay_id: str, request: Request) -> dict[str, Any]:
        user = _require_registered_user(request)
        data = load_replay(replay_id, str(user["user_id"]))
        if not data:
            raise HTTPException(status_code=404, detail="Replay not found.")
        return data

    @router.post("/battle/bug-report")
    def submit_bug_report(request: Request, payload: BugReportRequest) -> dict[str, Any]:
        user = _try_auth_user(request)
        if not user or user.get("is_guest"):
            raise HTTPException(status_code=401, detail="请先登录。")
        message = str(payload.message or "").strip()
        if len(message) < 4:
            raise HTTPException(status_code=400, detail="Please describe the bug (at least a few characters).")
        if len(message) > 4000:
            raise HTTPException(status_code=400, detail="Bug report is too long.")
        import os

        to_email = str(os.getenv("BUG_REPORT_EMAIL") or os.getenv("SMTP_FROM") or "jaydentay429@gmail.com").strip()
        username = str(user.get("username") or "player")
        user_id = str(user.get("user_id") or "")
        subject = f"[OPCG Battle Bug] {username} · {payload.room_code or 'no-room'}"
        if not payload.room_code and payload.page_url:
            subject = f"[OPCG Bug] {username}"
        body = (
            f"From: {username} ({user_id})\n"
            f"Room: {payload.room_code or '-'}\n"
            f"Phase: {payload.phase or '-'}\n"
            f"Turn: {payload.turn_number if payload.turn_number is not None else '-'}\n"
            f"Page: {payload.page_url or '-'}\n"
            f"\n---\n{message}\n"
        )
        if send_email is None:
            print(f"[battle-bug] to={to_email}\n{subject}\n{body}")
        else:
            try:
                send_email(to_email, subject, body)
            except Exception as exc:
                print(f"[battle-bug] send failed: {exc}\n{body}")
                raise HTTPException(status_code=502, detail="Failed to send bug report email.") from exc
        return {"ok": True}

    @router.websocket("/battle/ws")
    async def battle_ws(ws: WebSocket, token: str = "", room: str = "", role: str = "") -> None:
        await ws.accept()
        user = _resolve_token_user(token)
        if not user:
            await ws.send_json({"type": "error", "error": "Auth required."})
            await ws.close()
            return
        room_obj = manager.get(room)
        if not room_obj:
            await ws.send_json({"type": "error", "error": "Room not found."})
            await ws.close()
            return

        is_spectator = str(role or "").strip().lower() == "spectator"
        if is_spectator:
            if not manager.can_spectate(room_obj):
                await ws.send_json({"type": "error", "error": "Spectating is not allowed for this match."})
                await ws.close()
                return
            spec = manager.add_spectator(
                room_obj,
                str(user["user_id"]),
                str(user.get("username") or "Spectator"),
                ws,
            )

            async def push_spectator() -> None:
                if not room_obj.match:
                    return
                view = manager._spectator_view_for_room(room_obj)
                try:
                    await ws.send_json({"type": "state", "state": view})
                except Exception:
                    spec.ws = None

            await push_spectator()
            await manager.broadcast_chat(room_obj)
            try:
                while True:
                    data = await ws.receive_json()
                    if not isinstance(data, dict):
                        continue
                    if data.get("type") == "ping":
                        await ws.send_json({"type": "pong"})
                        continue
                    if data.get("type") == "sync":
                        await push_spectator()
                        await manager.broadcast(room_obj)
                        await manager.broadcast_chat(room_obj)
                    elif data.get("type") == "chat":
                        await ws.send_json({"type": "error", "error": "Spectators cannot chat."})
                    elif data.get("type") == "action":
                        await ws.send_json({"type": "error", "error": "Spectators cannot act."})
            except WebSocketDisconnect:
                manager.remove_spectator_ws(room_obj, ws)
            except Exception:
                manager.remove_spectator_ws(room_obj, ws)
                try:
                    await ws.close()
                except Exception:
                    pass
            return

        seat = manager.seat_for_user(room_obj, str(user["user_id"]))
        if seat is None:
            await ws.send_json({"type": "error", "error": "Join the room first."})
            await ws.close()
            return
        slot = room_obj.seats[seat]
        if slot:
            old_ws = slot.ws
            slot.ws = ws
            # Only one live socket per seat — otherwise actions on a stale socket
            # never see broadcast replies (UI stuck on “处理中…”).
            if old_ws is not None and old_ws is not ws:
                try:
                    await old_ws.close()
                except Exception:
                    pass

        async def push_state_to(target: WebSocket) -> None:
            if not room_obj.match:
                try:
                    await target.send_json(manager.waiting_payload(room_obj))
                except Exception:
                    pass
                return
            view_seat = seat
            if room_obj.hotseat:
                # Always follow acting seat in self-battle (do not require host-id match).
                view_seat = manager.hotseat_viewer_seat(room_obj)
            view = manager._public_view_for_room(room_obj, view_seat)
            try:
                await target.send_json({"type": "state", "state": view})
            except Exception:
                pass

        async def push_here() -> None:
            await push_state_to(ws)

        await manager.broadcast(room_obj)
        await manager.broadcast_chat(room_obj)
        # Pace opening AI moves once a human is watching (do not block chat).
        _spawn_ai(room_obj, push_here)

        try:
            while True:
                data = await ws.receive_json()
                if not isinstance(data, dict):
                    continue
                if data.get("type") == "ping":
                    await ws.send_json({"type": "pong"})
                    continue
                if data.get("type") == "action":
                    action = data.get("action") or {}
                    # Combat reactions must never wait on LLM / block the event loop.
                    kind = str((action or {}).get("type") or "")
                    no_llm = kind in {
                        "attack",
                        "block",
                        "counter",
                        "pass_counter",
                        "end_turn",
                        "concede",
                        "attach_don",
                        "remove_don",
                        "confirm_effect",
                    }
                    action_snapshot = dict(action) if isinstance(action, dict) else {}
                    result = await asyncio.to_thread(
                        manager.handle_action,
                        room_obj,
                        str(user["user_id"]),
                        action_snapshot,
                        use_llm=not no_llm,
                    )
                    if not result.get("ok"):
                        try:
                            await ws.send_json(
                                {"type": "error", "error": result.get("error") or "Action failed."}
                            )
                        except Exception:
                            pass
                    # Always reply on THIS socket first (stale-slot safe), then others.
                    await push_state_to(ws)
                    await manager.broadcast(room_obj)
                    if result.get("ok"):
                        _spawn_ai(room_obj, push_here)
                elif data.get("type") == "sync":
                    await push_state_to(ws)
                    await manager.broadcast(room_obj)
                    await manager.broadcast_chat(room_obj)
                    _spawn_ai(room_obj, push_here)
                elif data.get("type") == "chat":
                    try:
                        payload = manager.add_chat(
                            room_obj,
                            str(user["user_id"]),
                            str(user.get("username") or "Player"),
                            str(data.get("text") or ""),
                        )
                    except ValueError as exc:
                        await ws.send_json({"type": "error", "error": str(exc)})
                        continue
                    await manager.broadcast_chat(room_obj, payload)
        except WebSocketDisconnect:
            if slot and slot.ws is ws:
                slot.ws = None
        except Exception:
            if slot and slot.ws is ws:
                slot.ws = None
            try:
                await ws.close()
            except Exception:
                pass

    app.include_router(router)
    return manager
