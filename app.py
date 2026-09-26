from __future__ import annotations

import base64
import json
import os
import re
import hashlib
import hmac
import secrets
import smtplib
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from dataclasses import dataclass

import requests
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import dotenv_values, load_dotenv
from opcg_attributes import normalize_attributes, resolve_card_attributes
from filter_keywords import FILTER_KEYWORD_IDS, card_filter_keywords
from topdecks_normalize import (
    country_labels,
    facet_row,
    norm_country,
    norm_host,
    norm_placement,
    norm_tournament,
    placement_labels,
    tournament_labels,
)
import topdecks_likes
import card_comments
from pydantic import BaseModel

# OpenAI SDK import can block for a long time on some networks; load lazily.
OpenAI = None  # type: ignore[misc, assignment]
_openai_import_attempted = False


def _ensure_openai() -> bool:
    global OpenAI
    if OpenAI is not None:
        return True
    try:
        from openai import OpenAI as _OpenAI

        OpenAI = _OpenAI
        return True
    except Exception:
        return False


try:
    import imagehash
    from PIL import Image
except Exception:
    imagehash = None
    Image = None

cv2 = None  # type: ignore
np = None  # type: ignore
_cv_import_attempted = False


def _ensure_cv_deps() -> bool:
    """Lazy-load OpenCV / numpy (import can take tens of seconds)."""
    global cv2, np, _cv_import_attempted
    if cv2 is not None and np is not None:
        return True
    if _cv_import_attempted:
        return bool(cv2 is not None or np is not None)
    _cv_import_attempted = True
    try:
        import numpy as _np  # type: ignore

        np = _np
    except Exception:
        np = None
    try:
        import cv2 as _cv2  # type: ignore

        cv2 = _cv2
    except Exception:
        cv2 = None
    return bool(cv2 is not None or np is not None)

# torch / transformers are huge and can hang on first import (network/model
# download). Keep them lazy so API startup and price endpoints stay responsive.
torch = None
CLIPModel = None
CLIPProcessor = None
_clip_import_attempted = False


def _ensure_clip_deps() -> bool:
    global torch, CLIPModel, CLIPProcessor, _clip_import_attempted
    if torch is not None and CLIPModel is not None and CLIPProcessor is not None:
        return True
    if _clip_import_attempted:
        return False
    _clip_import_attempted = True
    try:
        import torch as _torch  # type: ignore
        from transformers import CLIPModel as _CLIPModel  # type: ignore
        from transformers import CLIPProcessor as _CLIPProcessor  # type: ignore

        torch = _torch
        CLIPModel = _CLIPModel
        CLIPProcessor = _CLIPProcessor
        return True
    except Exception:
        torch = None
        CLIPModel = None
        CLIPProcessor = None
        return False


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)
INDEX_PATH = BASE_DIR / "index" / "cards_by_id.json"
CARDS_DIR = BASE_DIR / "cards"
PACKS_DIR = BASE_DIR / "packs"
OFFICIAL_RULES_PATH = BASE_DIR / "official_rules"
LIMITLESS_META_FILE = BASE_DIR / "meta" / "limitless_meta.json"
LIMITLESS_COOCCURRENCE_FILE = BASE_DIR / "meta" / "card_cooccurrence.json"
MARKET_PRICE_FILE = BASE_DIR / "meta" / "market_prices.json"
TOPDECKS_FILE = BASE_DIR / "meta" / "topdecks_decks.json"
OFFICIAL_SYNC_SNAPSHOT_FILE = BASE_DIR / "cards" / "official_sync" / "latest_cards.json"
PHOTO_HASH_INDEX_FILE = BASE_DIR / "meta" / "photo_hash_index.json"
PHOTO_CLIP_INDEX_FILE = BASE_DIR / "meta" / "photo_clip_index.npz"
ATTRIBUTE_CACHE_FILE = BASE_DIR / "meta" / "card_attributes_map.json"
AI_ADVICE_CACHE_FILE = BASE_DIR / "meta" / "ai_advice_cache.json"
DECKS_STORE_FILE = BASE_DIR / "meta" / "user_decks.json"
MAX_USER_DECKS = 40
COLLECTION_STORE_FILE = BASE_DIR / "meta" / "user_collections.json"
BINDER_STORE_FILE = BASE_DIR / "meta" / "user_binders.json"
BINDER_SHARES_FILE = BASE_DIR / "meta" / "binder_shares.json"
AUTH_DB_FILE = BASE_DIR / "meta" / "auth.db"
MAX_AI_CACHE_ITEMS = int(os.getenv("MAX_AI_CACHE_ITEMS", "3000"))
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
# R2/CDN（bucket 根目录为卡图文件名时启用；不配则继续使用本机 `/packs` 静态路由）
OPCG_PACKS_PUBLIC_URL = os.getenv("OPCG_PACKS_PUBLIC_URL", "").strip().rstrip("/")
API_KEY_ENV_NAME = "DEEPSEEK_API_KEY"
API_KEY_FALLBACK_ENV_NAME = "OPCG_API_KEY"
DEEPSEEK_MODEL = "deepseek-chat"
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.15"))
IMAGE_FETCH_TIMEOUT_SEC = float(os.getenv("IMAGE_FETCH_TIMEOUT_SEC", "4"))
IMAGE_FETCH_MAX_CANDIDATES = int(os.getenv("IMAGE_FETCH_MAX_CANDIDATES", "1"))
OFFICIAL_IMAGE_HOSTS = [
    "https://www.onepiece-cardgame.com/",
]
AI_PROMPT_VERSION = "v3_rule_safe"
AI_SYSTEM_PROMPT = (
    "你是一个专业的 One Piece TCG 冠军选手。"
    "请根据这张卡的效果，给出当前环境下可行的配合 Combo 与实战建议。"
    "必须严格遵守 Context 中的官方规则，不得编造规则。"
    "禁止把卡牌基础资料重复粘贴到实战建议。"
    "若规则依据不足，请明确说明不确定，不要写成确定规则判定。"
    "请严格返回 JSON，格式为："
    '{"combos":["可为空或多条"],"play_tip":"tip","combo_refs":[["规则1"]],'
    '"play_tip_refs":["规则3"],"rules_refs":["兼容旧字段"],'
    '"confidence":"high|medium|low","insufficient_rules":false}'
)
AUTH_SESSION_DAYS = int(os.getenv("AUTH_SESSION_DAYS", "30"))
AUTH_VERIFY_TOKEN_HOURS = int(os.getenv("AUTH_VERIFY_TOKEN_HOURS", "48"))
AUTH_RESET_TOKEN_HOURS = int(os.getenv("AUTH_RESET_TOKEN_HOURS", "2"))


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _auth_bypass_from_dotenv_file() -> bool | None:
    """优先读项目根 `.env` 里的 OPCG_AUTH_BYPASS，避免仅依赖进程环境变量。"""
    try:
        vals = dotenv_values(BASE_DIR / ".env")
        raw = str((vals or {}).get("OPCG_AUTH_BYPASS") or "").strip().lower()
    except Exception:
        raw = ""
    if raw == "":
        return None
    return raw in {"1", "true", "yes", "on"}


def _cors_allow_origins() -> list[str]:
    """浏览器 Origin 列表。生产环境请设置 OPCG_CORS_ORIGINS（逗号分隔，含协议与域名，无路径）。"""
    raw = os.getenv("OPCG_CORS_ORIGINS", "").strip()
    defaults = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # next dev 会在 3000 被占用时自动退到 3001/3002
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://localhost",
        "http://127.0.0.1",
    ]
    if not raw:
        return defaults
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        o = part.strip().rstrip("/")
        if not o or o in seen:
            continue
        seen.add(o)
        out.append(o)
    return out if out else defaults


def _cors_allow_origin_regex() -> str | None:
    """未显式配置 OPCG_CORS_ORIGINS 时放行任意本机/局域网来源，避免 dev 端口漂移导致预检 400。"""
    if os.getenv("OPCG_CORS_ORIGINS", "").strip():
        return None
    return r"^http://(localhost|127\.0\.0\.1|\[::1\]|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?$"


app = FastAPI(title="OPCG Card API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_origin_regex=_cors_allow_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

# 仅本地调试启用：在 .env 中设置 OPCG_AUTH_BYPASS=1。生产环境切勿开启。
_bypass_opt = _auth_bypass_from_dotenv_file()
AUTH_BYPASS_FOR_TESTING = bool(_bypass_opt) if _bypass_opt is not None else _env_flag("OPCG_AUTH_BYPASS", False)
PACKS_DIR.mkdir(parents=True, exist_ok=True)
# /packs/{file} is served by buffered route below (StaticFiles truncates under concurrent wall loads).


class CardResponse(BaseModel):
    id: str
    name: str | None = None
    name_en: str | None = None
    rarity: str | None = None
    colors: list[str] = []
    colors_en: list[str] = []
    pack_id: str | None = None
    img_local_url: str | None = None
    img_url: str | None = None
    img_full_url: str | None = None
    alt_image_urls: list[str] = []
    cost: int | None = None
    effect: str | None = None
    effect_en: str | None = None
    trigger: str | None = None
    trigger_en: str | None = None
    power: int | str | None = None
    traits: list[str] = []
    traits_en: list[str] = []
    card_type: str | None = None
    card_type_en: str | None = None
    counter: int | str | None = None
    block_number: int | None = None
    attributes: list[str] = []
    attributes_en: list[str] = []
    card_sets: list[str] = []
    # Sibling illustration id → official getInfo (detail page switches source with thumbs).
    variant_card_sets: dict[str, list[str]] = {}
    market_price: dict[str, Any] | None = None
    life: int | None = None


class AIAdvice(BaseModel):
    combos: list[str] = []
    play_tip: str = ""
    combo_refs: list[list[str]] = []
    play_tip_refs: list[str] = []
    rules_refs: list[str] = []
    confidence: str = "medium"
    insufficient_rules: bool = False
    insufficient_reasons: list[str] = []
    leader_deck_plans: list[dict[str, Any]] = []


class CardWithAIResponse(BaseModel):
    card: CardResponse
    ai_advice: AIAdvice | None = None
    ai_error: str | None = None
    meta_evidence: dict[str, Any] | None = None


class FilterCardResponse(BaseModel):
    id: str
    name: str | None = None
    name_en: str | None = None
    rarity: str | None = None
    colors: list[str] = []
    cost: int | None = None
    power: int | None = None
    counter: int | None = None
    card_type: str | None = None
    block_number: int | None = None
    attributes: list[str] = []
    img_url: str | None = None
    img_full_url: str | None = None
    img_local_url: str | None = None


@dataclass(frozen=True, slots=True)
class FilterIndexEntry:
    """Precomputed row for /filters/cards — avoids rebuilding responses per request."""

    id: str
    sort_key: str
    colors: frozenset[str]
    card_type: str
    attrs: frozenset[str]
    series: str
    rarity: str
    block: int | None
    cost: int | None
    counter: int | None
    power: int | None
    keywords: frozenset[str]
    name: str
    name_en: str
    response: FilterCardResponse


class ErrorResponse(BaseModel):
    error: str
    path: str
    detail: Any


class PhotoRecognizeRequest(BaseModel):
    image_base64: str


class PhotoRecognizeResponse(BaseModel):
    card_id: str | None = None
    base_card_id: str | None = None
    distance: int | None = None
    confidence: str = "low"
    message: str = ""
    candidates: list[dict[str, Any]] = []
    score_gap: int | None = None
    stage: str = ""
    debug: dict[str, Any] = {}


class CardThumbnailBatchRequest(BaseModel):
    ids: list[str] = []


class TopdeckLikeRequest(BaseModel):
    deck_id: str
    liked: bool = True


class CardCommentCreateRequest(BaseModel):
    body: str
    anonymous: bool = False


class CardCommentLikeRequest(BaseModel):
    liked: bool = True


class CardCommentReportRequest(BaseModel):
    reason: str


class DeckCardChangeRequest(BaseModel):
    user_id: str | None = None
    card_id: str
    count: int = 1


class DeckCreateRequest(BaseModel):
    user_id: str | None = None
    name: str
    leader_card_id: str | None = None
    cards: dict[str, int] | None = None


class DeckRenameRequest(BaseModel):
    user_id: str | None = None
    name: str


class DeckSaveRequest(BaseModel):
    user_id: str | None = None
    name: str | None = None
    leader_card_id: str | None = None
    cards: dict[str, int] | None = None


class DeckResponse(BaseModel):
    id: str
    name: str
    leader_card_id: str | None = None
    cards: dict[str, int] = {}
    non_leader_count: int = 0
    total_count: int = 0
    is_valid_ready: bool = False
    created_at: str
    updated_at: str


class DeckListResponse(BaseModel):
    user_id: str
    decks: list[DeckResponse] = []


class CollectionCardChangeRequest(BaseModel):
    card_id: str
    count: int = 1


class CollectionResponse(BaseModel):
    owner: str
    cards: dict[str, int] = {}
    total_unique: int = 0
    total_copies: int = 0


class BinderSlotUpdateRequest(BaseModel):
    page: int
    slot: int
    card_id: str | None = None


class BinderSwapRequest(BaseModel):
    page: int
    from_slot: int
    to_slot: int


class BinderPageTitleRequest(BaseModel):
    page: int
    title: str


class BinderResponse(BaseModel):
    owner: str
    pages: list[list[str | None]] = []
    page_titles: list[str] = []


class BinderShareCreateResponse(BaseModel):
    token: str
    url_path: str
    owner_name: str = ""


class BinderSharedResponse(BaseModel):
    token: str
    owner_name: str = ""
    pages: list[list[str | None]] = []
    page_titles: list[str] = []


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str


class LoginRequest(BaseModel):
    login: str  # email or username
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    email: str
    email_verified: bool


class MeResponse(BaseModel):
    username: str
    email: str
    email_verified: bool
    is_admin: bool = False


class AnalyticsEventIn(BaseModel):
    path: str
    referrer: str | None = None
    visitor_id: str
    session_id: str
    language: str | None = None
    screen: str | None = None


class AnalyticsAiCrawlIn(BaseModel):
    bot: str
    path: str


_AI_CRAWL_BOTS = {
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "PerplexityBot",
    "ClaudeBot",
    "Google-Extended",
}


cards_by_id: dict[str, dict[str, Any]] = {}
leader_name_index: list[tuple[str, str]] = []
card_search_norm_by_id: dict[str, str] = {}
name_hans_by_en: dict[str, str] = {}
name_aliases_by_en: dict[str, dict[str, Any]] = {}
NAME_HANS_BY_EN_PATH = BASE_DIR / "meta" / "name_hans_by_en.json"
NAME_ALIASES_PATH = BASE_DIR / "meta" / "name_aliases.json"

try:
    from opencc import OpenCC as _OpenCC

    _opencc_t2s = _OpenCC("t2s")
    _opencc_s2t = _OpenCC("s2t")
except Exception as _opencc_exc:
    _opencc_t2s = None
    _opencc_s2t = None
    print(
        f"[warn] OpenCC unavailable ({_opencc_exc}); "
        "simplified/traditional trait search will miss many cards. "
        "Install: pip install opencc-python-reimplemented",
        flush=True,
    )
pack_cache: dict[str, Any] = {}
official_rules_context = ""
official_rules_files: list[str] = []
tournament_meta_context = ""
cooccurrence_map: dict[str, list[dict[str, Any]]] = {}
card_count_stats: dict[str, dict[str, Any]] = {}
limitless_top_decks: list[dict[str, Any]] = []
limitless_recent_tournaments: list[dict[str, Any]] = []
ai_advice_cache: dict[str, AIAdvice] = {}
card_type_cache: dict[str, str] = {}
card_analysis_cache: dict[str, dict[str, Any]] = {}
market_price_map: dict[str, dict[str, Any]] = {}
market_price_mtime: float = 0.0
market_price_updated_at: str = ""
topdecks_payload: dict[str, Any] = {}
topdecks_mtime: float = 0.0
topdecks_by_id: dict[str, dict[str, Any]] = {}
# Newest-first deck list (same rows as payload["decks"], pre-sorted for list API).
topdecks_decks_sorted: list[dict[str, Any]] = []
# Facets computed once per file load (avoid rescanning ~12k decks on every /meta).
topdecks_facets_cache: dict[str, list[dict[str, Any]]] = {}
# deck id → lowercased searchable meta blob (author/name/tournament/…).
topdecks_meta_blob_by_id: dict[str, str] = {}
# base card id → deck ids that include it as leader or main deck (alt arts share base)
topdecks_by_card_base: dict[str, set[str]] = {}
# base card id → newest-first appearances: (date_tuple, deck_id, qty, is_leader)
topdecks_appearances_by_card: dict[str, list[tuple[tuple[int, int, int], str, int, bool]]] = {}
official_snapshot_map: dict[str, dict[str, Any]] = {}
variant_id_map: dict[str, list[str]] = {}
local_image_url_map: dict[str, str] = {}
local_image_path_map: dict[str, Path] = {}
filter_index: list[FilterIndexEntry] = []
cached_attribute_map: dict[str, list[str]] = {}
attribute_ocr_cache: dict[str, list[str]] = {}
_rapidocr_engine: Any | None = None
photo_hash_index: dict[str, dict[str, Any]] = {}
photo_hash_ready: bool = False
clip_index_ready: bool = False
clip_embeddings: dict[str, Any] = {}
clip_model: Any | None = None
clip_processor: Any | None = None
deck_store_lock = threading.Lock()
collection_store_lock = threading.Lock()
binder_store_lock = threading.Lock()
auth_db_lock = threading.Lock()
CLIP_MODEL_NAME = os.getenv("OPCG_CLIP_MODEL", "openai/clip-vit-base-patch32")
CLIP_PREWARM_ON_STARTUP = os.getenv("CLIP_PREWARM_ON_STARTUP", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
RECOGNIZE_USE_CLIP = os.getenv("RECOGNIZE_USE_CLIP", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
RECOGNIZE_INCLUDE_DEBUG = os.getenv("RECOGNIZE_INCLUDE_DEBUG", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
# CLIP distance = int((1 - cosine_sim) * 1000). Lower is better.
CLIP_HIGH_DIST = int(os.getenv("CLIP_HIGH_DIST", "80"))
CLIP_HIGH_GAP = int(os.getenv("CLIP_HIGH_GAP", "35"))
CLIP_MED_DIST = int(os.getenv("CLIP_MED_DIST", "150"))
CLIP_MED_GAP = int(os.getenv("CLIP_MED_GAP", "20"))
DEEPSEEK_RECOGNIZE_MODEL = os.getenv("DEEPSEEK_RECOGNIZE_MODEL", "deepseek-chat")
RECOGNIZE_USE_DEEPSEEK = os.getenv("RECOGNIZE_USE_DEEPSEEK", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
RECOGNIZE_DEEPSEEK_FREE_MODE = os.getenv("RECOGNIZE_DEEPSEEK_FREE_MODE", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
RECOGNIZE_DEEPSEEK_VISION = os.getenv("RECOGNIZE_DEEPSEEK_VISION", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_user_id(user_id: str) -> str:
    raw = str(user_id or "").strip().lower()
    if not raw:
        return "guest"
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-")
    return cleaned[:48] or "guest"


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _mask_email(email: str) -> str:
    text = _normalize_email(email)
    if "@" not in text:
        return "***"
    local, _, domain = text.partition("@")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _normalize_username(username: str) -> str:
    raw = str(username or "").strip().lower()
    cleaned = re.sub(r"[^a-z0-9_]+", "", raw)
    return cleaned[:32]


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt.encode("utf-8"), 120_000)
    return base64.b64encode(digest).decode("ascii")


def _make_password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    return f"{salt}${_hash_password(password, salt)}"


def _verify_password(password: str, stored: str) -> bool:
    if "$" not in str(stored):
        return False
    salt, old_hash = str(stored).split("$", 1)
    new_hash = _hash_password(password, salt)
    return hmac.compare_digest(new_hash, old_hash)


def _parse_iso_dt(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _auth_db() -> sqlite3.Connection:
    AUTH_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(AUTH_DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _init_auth_db() -> None:
    with auth_db_lock:
        conn = _auth_db()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    email_verified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS email_verify_tokens (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(users)").fetchall()}
            if "is_admin" not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        finally:
            conn.close()


def _deck_owner_id_from_user_row(user_row: sqlite3.Row) -> str:
    return f"user_{int(user_row['id'])}"


def _frontend_site_url() -> str:
    raw = str(os.getenv("OPCG_SITE_URL") or "").strip().rstrip("/")
    if raw:
        return raw
    origins = _cors_allow_origins()
    for o in origins:
        if "localhost" in o or "127.0.0.1" in o:
            return o.rstrip("/")
    return origins[0].rstrip("/") if origins else "http://127.0.0.1:3000"


def _send_email(to_email: str, subject: str, body: str, *, html: str | None = None) -> None:
    from email_util import send_email

    send_email(to_email, subject, body, html=html, log_prefix="auth")


def _send_verify_email(email: str, username: str, verify_url: str) -> None:
    _send_email(
        email,
        "请验证你的邮箱",
        (
            f"Hi {username},\n\n请点击以下链接验证邮箱：\n{verify_url}\n\n"
            f"链接 {AUTH_VERIFY_TOKEN_HOURS} 小时内有效。"
        ),
    )


def _send_reset_password_email(email: str, username: str, reset_url: str) -> None:
    _send_email(
        email,
        "重置你的 OPCG 账号密码",
        (
            f"Hi {username},\n\n收到重置密码请求。请点击以下链接设置新密码：\n{reset_url}\n\n"
            f"链接 {AUTH_RESET_TOKEN_HOURS} 小时内有效。若非本人操作，请忽略本邮件。"
        ),
    )


def _read_auth_user_from_request(request: Request) -> sqlite3.Row | None:
    auth = str(request.headers.get("Authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return None
    with auth_db_lock:
        conn = _auth_db()
        try:
            row = conn.execute(
                """
                SELECT s.token, s.expires_at, s.revoked_at, u.*
                FROM auth_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = ?
                """,
                (token,),
            ).fetchone()
        finally:
            conn.close()
    if row is None or row["revoked_at"] is not None:
        return None
    exp = _parse_iso_dt(row["expires_at"])
    now = datetime.now(timezone.utc)
    if exp is None or exp <= now:
        return None
    return row


def _require_auth_user(request: Request) -> sqlite3.Row:
    if AUTH_BYPASS_FOR_TESTING:
        return {
            "id": 0,
            "username": "test_user",
            "email": "test@local",
            "email_verified": 1,
            "is_admin": 1,
        }  # type: ignore[return-value]
    row = _read_auth_user_from_request(request)
    if row is None:
        raise HTTPException(status_code=401, detail="请先登录。")
    return row


def _username_for_owner_id(owner_id: str) -> str | None:
    """Map forum author id `user_{n}` to auth username."""
    raw = str(owner_id or "").strip()
    if not raw.startswith("user_"):
        return None
    try:
        uid = int(raw.split("_", 1)[1])
    except ValueError:
        return None
    with auth_db_lock:
        conn = _auth_db()
        try:
            row = conn.execute("SELECT username FROM users WHERE id = ?", (uid,)).fetchone()
        finally:
            conn.close()
    if row is None:
        return None
    return str(row["username"])


def _is_admin_for_owner_id(owner_id: str) -> bool:
    raw = str(owner_id or "").strip()
    if not raw.startswith("user_"):
        return False
    try:
        uid = int(raw.split("_", 1)[1])
    except ValueError:
        return False
    with auth_db_lock:
        conn = _auth_db()
        try:
            row = conn.execute("SELECT is_admin FROM users WHERE id = ?", (uid,)).fetchone()
        finally:
            conn.close()
    if row is None:
        return False
    try:
        return bool(int(row["is_admin"] or 0))
    except (TypeError, ValueError, KeyError):
        return False


def _email_for_owner_id(owner_id: str) -> str | None:
    raw = str(owner_id or "").strip()
    if not raw.startswith("user_"):
        return None
    try:
        uid = int(raw.split("_", 1)[1])
    except ValueError:
        return None
    with auth_db_lock:
        conn = _auth_db()
        try:
            row = conn.execute("SELECT email FROM users WHERE id = ?", (uid,)).fetchone()
        finally:
            conn.close()
    if row is None:
        return None
    return str(row["email"])


def _new_deck_id(user_id: str, name: str) -> str:
    seed = f"{user_id}:{name}:{datetime.now(timezone.utc).timestamp()}".encode("utf-8")
    return hashlib.sha1(seed).hexdigest()[:12]


_user_store_locks: dict[str, threading.Lock] = {
    "decks": threading.Lock(),
    "collection": threading.Lock(),
    "binder": threading.Lock(),
}


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON via temp file + os.replace to avoid truncated stores."""
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _load_decks_store() -> dict[str, Any]:
    if not DECKS_STORE_FILE.exists():
        return {}
    try:
        data = json.loads(DECKS_STORE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_decks_store(store: dict[str, Any]) -> None:
    with _user_store_locks["decks"]:
        _atomic_write_json(DECKS_STORE_FILE, store)


def _load_collection_store() -> dict[str, Any]:
    if not COLLECTION_STORE_FILE.exists():
        return {}
    try:
        data = json.loads(COLLECTION_STORE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_collection_store(store: dict[str, Any]) -> None:
    with _user_store_locks["collection"]:
        _atomic_write_json(COLLECTION_STORE_FILE, store)


def _normalize_collection_cards(cards: dict[str, Any] | None) -> dict[str, int]:
    out: dict[str, int] = {}
    for raw_id, raw_cnt in (cards or {}).items():
        cid = normalize_card_id(str(raw_id))
        iv = _to_int(raw_cnt)
        if not cid or iv is None or iv <= 0:
            continue
        out[cid] = iv
    return out


def _serialize_collection(owner: str, cards: dict[str, Any] | None) -> CollectionResponse:
    normalized = _normalize_collection_cards(cards)
    return CollectionResponse(
        owner=owner,
        cards=normalized,
        total_unique=len(normalized),
        total_copies=sum(normalized.values()),
    )


def _default_binder_pages() -> list[list[str | None]]:
    return [[None for _ in range(18)] for _ in range(10)]


def _default_binder_titles() -> list[str]:
    return ["" for _ in range(10)]


def _normalize_binder_pages(raw: Any) -> list[list[str | None]]:
    pages = _default_binder_pages()
    if not isinstance(raw, list):
        return pages
    for pidx in range(min(10, len(raw))):
        row = raw[pidx]
        if not isinstance(row, list):
            continue
        for sidx in range(min(18, len(row))):
            cid = normalize_card_id(str(row[sidx] or ""))
            pages[pidx][sidx] = cid if cid else None
    return pages


def _normalize_binder_payload(raw: Any) -> tuple[list[list[str | None]], list[str]]:
    if isinstance(raw, dict):
        pages = _normalize_binder_pages(raw.get("pages"))
        titles_raw = raw.get("page_titles")
        titles = _default_binder_titles()
        if isinstance(titles_raw, list):
            for i in range(min(10, len(titles_raw))):
                titles[i] = str(titles_raw[i] or "").strip()[:40]
        return pages, titles
    return _normalize_binder_pages(raw), _default_binder_titles()


def _load_binder_store() -> dict[str, Any]:
    if not BINDER_STORE_FILE.exists():
        return {}
    try:
        data = json.loads(BINDER_STORE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_binder_store(store: dict[str, Any]) -> None:
    with _user_store_locks["binder"]:
        _atomic_write_json(BINDER_STORE_FILE, store)


def _load_binder_shares() -> dict[str, Any]:
    if not BINDER_SHARES_FILE.exists():
        return {}
    try:
        data = json.loads(BINDER_SHARES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_binder_shares(store: dict[str, Any]) -> None:
    with _user_store_locks["binder"]:
        _atomic_write_json(BINDER_SHARES_FILE, store)


def _upsert_binder_share(
    owner: str,
    owner_name: str,
    pages: list[list[str | None]],
    titles: list[str],
) -> str:
    """Create or refresh a stable share token for this owner."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with binder_store_lock:
        store = _load_binder_shares()
        token = ""
        for tok, entry in store.items():
            if isinstance(entry, dict) and str(entry.get("owner") or "") == owner:
                token = str(tok)
                break
        if not token:
            token = secrets.token_urlsafe(12)
        store[token] = {
            "owner": owner,
            "owner_name": str(owner_name or "")[:40],
            "created_at": str((store.get(token) or {}).get("created_at") or now) if token in store else now,
            "updated_at": now,
            "pages": pages,
            "page_titles": titles,
        }
        _save_binder_shares(store)
    return token


def _is_leader_card(card_id: str) -> bool:
    basic = cards_by_id.get(normalize_card_id(card_id)) or {}
    return str(basic.get("card_type") or "").strip().lower() == "leader"


def _deck_non_leader_count(cards: dict[str, Any]) -> int:
    total = 0
    for _cid, cnt in (cards or {}).items():
        iv = _to_int(cnt)
        if iv is None or iv <= 0:
            continue
        total += iv
    return total


def _resolve_deck_card_id(card_id: str) -> str:
    """Resolve deck card id; keep 异画 suffix when present in catalog."""
    norm = normalize_card_id(str(card_id or "").strip())
    if not norm:
        return ""
    if norm in cards_by_id:
        return norm
    base = _base_card_id(norm)
    if base in cards_by_id:
        return base
    return norm


def _normalize_deck_cards(cards: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for card_id, cnt in (cards or {}).items():
        norm = _resolve_deck_card_id(str(card_id))
        iv = _to_int(cnt)
        if not norm or iv is None or iv <= 0:
            continue
        out[norm] = int(out.get(norm, 0) or 0) + iv
    return out


def _max_deck_copies(card_id: str) -> int:
    """Most cards are capped at 4; some print 'any number in your deck'."""
    basic = cards_by_id.get(normalize_card_id(card_id)) or {}
    blob = f"{basic.get('effect') or ''}\n{basic.get('effect_en') or ''}"
    if re.search(
        r"any number of this card|可不限張數放入卡組|可不限张数放入卡组",
        blob,
        re.I,
    ):
        return 50
    return 4


def _validate_deck_contents(
    leader_card_id: str | None,
    cards_raw: dict[str, Any] | None,
) -> tuple[str | None, dict[str, int]]:
    """
    Returns normalized leader id (or None) and non-leader card counts.
    Leader cannot appear in the main deck dict.
    """
    cards = _normalize_deck_cards(cards_raw)
    leader = normalize_card_id(str(leader_card_id or "")) or None
    if leader:
        leader = _resolve_deck_card_id(leader)
        if leader not in cards_by_id:
            raise HTTPException(status_code=404, detail=f"未找到卡号 {leader}。")
        if not _is_leader_card(leader):
            raise HTTPException(status_code=400, detail="只能将 Leader 类型卡设置为队长。")
        cards.pop(leader, None)
    for cid in list(cards.keys()):
        if cid not in cards_by_id:
            raise HTTPException(status_code=404, detail=f"未找到卡号 {cid}。")
        if _is_leader_card(cid):
            raise HTTPException(status_code=400, detail="主卡组不能包含 Leader 类型卡。")
        if int(cards.get(cid) or 0) > _max_deck_copies(cid):
            raise HTTPException(
                status_code=400,
                detail=f"{cid} 最多只能放 {_max_deck_copies(cid)} 张。",
            )
    if _deck_non_leader_count(cards) > 50:
        raise HTTPException(status_code=400, detail="非 Leader 卡总数最多 50 张。")
    return leader, cards


def _serialize_deck(deck: dict[str, Any]) -> DeckResponse:
    cards = _normalize_deck_cards(deck.get("cards") if isinstance(deck, dict) else {})
    leader_raw = normalize_card_id(str((deck or {}).get("leader_card_id") or "")) or None
    leader = _resolve_deck_card_id(leader_raw) if leader_raw else None
    non_leader_count = _deck_non_leader_count(cards)
    total_count = non_leader_count + (1 if leader else 0)
    return DeckResponse(
        id=str(deck.get("id") or ""),
        name=str(deck.get("name") or "未命名卡组"),
        leader_card_id=leader,
        cards=cards,
        non_leader_count=non_leader_count,
        total_count=total_count,
        is_valid_ready=bool(leader and non_leader_count == 50),
        created_at=str(deck.get("created_at") or now_iso()),
        updated_at=str(deck.get("updated_at") or now_iso()),
    )

def _safe_mtime(path: Path) -> int:
    try:
        return int(path.stat().st_mtime)
    except OSError:
        return 0


def build_ai_context_fingerprint() -> str:
    """
    Build a lightweight version stamp for AI cache invalidation.
    Any update to rules/meta/index/cooccurrence should rotate this fingerprint.
    """
    parts: list[str] = [
        f"rules_dir={_safe_mtime(OFFICIAL_RULES_PATH)}",
        f"meta={_safe_mtime(LIMITLESS_META_FILE)}",
        f"cooccur={_safe_mtime(LIMITLESS_COOCCURRENCE_FILE)}",
        f"index={_safe_mtime(INDEX_PATH)}",
        f"prompt={AI_PROMPT_VERSION}",
    ]
    if OFFICIAL_RULES_PATH.is_dir():
        for p in sorted(OFFICIAL_RULES_PATH.rglob("*")):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".txt", ".md", ".json"}:
                continue
            parts.append(f"{p.name}:{_safe_mtime(p)}")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _advice_to_dict(advice: AIAdvice) -> dict[str, Any]:
    if hasattr(advice, "model_dump"):
        return advice.model_dump()  # pydantic v2
    return advice.dict()  # pydantic v1


def load_ai_advice_cache_from_disk() -> None:
    global ai_advice_cache
    if not AI_ADVICE_CACHE_FILE.exists():
        return
    try:
        payload = json.loads(AI_ADVICE_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    rows = payload.get("items") if isinstance(payload, dict) else {}
    if not isinstance(rows, dict):
        return
    loaded: dict[str, AIAdvice] = {}
    for key, value in rows.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        try:
            loaded[key] = AIAdvice(**value)
        except Exception:
            continue
    if loaded:
        ai_advice_cache.update(loaded)


def persist_ai_advice_cache_to_disk() -> None:
    if len(ai_advice_cache) > MAX_AI_CACHE_ITEMS:
        overflow = len(ai_advice_cache) - MAX_AI_CACHE_ITEMS
        for _ in range(overflow):
            try:
                ai_advice_cache.pop(next(iter(ai_advice_cache)))
            except StopIteration:
                break
    payload = {
        "updated_at": now_iso(),
        "items": {k: _advice_to_dict(v) for k, v in ai_advice_cache.items()},
    }
    try:
        AI_ADVICE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        AI_ADVICE_CACHE_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        # Cache persistence must never break card API response.
        pass


IMAGE_LAZY_FETCH_ENABLED = _env_flag("IMAGE_LAZY_FETCH_ENABLED", False)
ATTRIBUTE_OCR_ENABLED = _env_flag("ATTRIBUTE_OCR_ENABLED", False)


def normalize_card_id(raw_card_id: str) -> str:
    cleaned = raw_card_id.strip().upper()
    cleaned = cleaned.replace("_", "-").replace(" ", "")
    cleaned = cleaned.replace("－", "-")
    # Keep only letters/numbers/hyphen to tolerate accidental extra characters.
    cleaned = re.sub(r"[^A-Z0-9-]", "", cleaned)
    # Illustrated DON cards: DON17-10163, DONEB03-10182, DON00-10001
    m_don = re.match(r"^(DON[A-Z0-9]*)-(\d{3,5}(?:-[A-Z0-9]+)?)$", cleaned)
    if m_don:
        return f"{m_don.group(1)}-{m_don.group(2)}"
    # Canonicalize ids like ST-30-001 -> ST30-001
    m = re.match(r"^([A-Z]{2,4})-?(\d{2})-(\d{3}(?:-[A-Z0-9]+)?)$", cleaned)
    if m:
        cleaned = f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    return cleaned


def normalize_name_query(keyword: str) -> str:
    return keyword.strip().lower()


def normalize_en_card_name(text: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\s*\(Parallel\)\s*$", "", str(text or "").strip(), flags=re.IGNORECASE)).strip()


def normalize_name_for_match(text: str) -> str:
    raw = str(text or "").strip().lower()
    raw = re.sub(r"\s+", "", raw)
    raw = re.sub(r"[^0-9a-z\u4e00-\u9fffぁ-んァ-ヶー]", "", raw)
    return raw


def _opencc_convert(text: str, converter: Any) -> str:
    if not text or converter is None:
        return str(text or "")
    try:
        return str(converter.convert(text))
    except Exception:
        return str(text or "")


def expand_name_search_texts(*parts: str | None) -> list[str]:
    """Collect TW / simplified / English name variants for matching."""
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        raw = str(part or "").strip()
        if not raw:
            continue
        variants = [
            raw,
            _opencc_convert(raw, _opencc_t2s),
            _opencc_convert(raw, _opencc_s2t),
        ]
        for v in variants:
            key = v.strip()
            if key and key not in seen:
                seen.add(key)
                out.append(key)
    return out


def build_card_search_blob(card_basic: dict[str, Any] | None) -> str:
    basic = card_basic if isinstance(card_basic, dict) else {}
    name = str(basic.get("name") or "").strip()
    name_en = normalize_en_card_name(basic.get("name_en"))
    hans = name_hans_by_en.get(name_en, "") if name_en else ""
    alias_parts = _alias_texts_for_en(name_en)
    trait_parts: list[str] = []
    for key in ("traits", "traits_en"):
        raw = basic.get(key)
        if isinstance(raw, list):
            trait_parts.extend(str(x).strip() for x in raw if str(x).strip())
        elif isinstance(raw, str) and raw.strip():
            trait_parts.extend(p.strip() for p in re.split(r"[,/|]", raw) if p.strip())
    texts = expand_name_search_texts(name, name_en, hans, *alias_parts, *trait_parts)
    return normalize_name_for_match(" ".join(texts))


def expand_query_match_norms(query: str) -> list[str]:
    raw = str(query or "").strip()
    if not raw:
        return []
    variants = expand_name_search_texts(raw)
    # Popular Mainland ↔ Taiwan lexical pairs (query-side), beyond pure OpenCC.
    synonym_pairs = [
        ("路飞", "魯夫"),
        ("路飞", "鲁夫"),
        ("山治", "香吉士"),
        ("乌索普", "騙人布"),
        ("乌索普", "骗人布"),
        ("弗兰奇", "佛朗基"),
        ("甚平", "吉貝爾"),
        ("甚平", "吉贝尔"),
        ("凯多", "海道"),
        ("巴基", "巴其"),
        ("罗罗诺亚", "羅羅亞"),
        ("罗罗诺亚", "罗罗亚"),
        ("托尼托尼", "多尼多尼"),
        ("特拉法尔加", "托拉法爾加"),
        ("特拉法尔加", "托拉法尔加"),
        ("蒙奇", "蒙其"),
        ("草帽海贼团", "草帽一行人"),
        ("草帽海賊團", "草帽一行人"),
        ("红发海贼团", "紅髮海賊團"),
        ("紅发海賊團", "紅髮海賊團"),
        ("希留", "矢龍"),
        ("希留", "矢龙"),
        ("雨之希留", "矢龍"),
        ("雨之希留", "矢龙"),
        ("雨之希留", "希留"),
        ("矢龙", "矢龍"),
    ]
    expanded = list(variants)
    for text in list(variants):
        for a, b in synonym_pairs:
            if a and a in text:
                expanded.append(text.replace(a, b))
            if b and b in text:
                expanded.append(text.replace(b, a))
    norms: list[str] = []
    seen: set[str] = set()
    for text in expanded:
        norm = normalize_name_for_match(text)
        if norm and norm not in seen:
            seen.add(norm)
            norms.append(norm)
    return norms


def card_matches_text_query(
    card_id: str,
    card_name: str,
    query: str,
    name_en: str | None = None,
    *,
    query_norms: list[str] | None = None,
) -> bool:
    q = str(query or "").strip()
    if not q:
        return True
    q_lower = q.lower()
    cid_raw = str(card_id or "")
    cid_lower = cid_raw.lower().replace("_", "-")
    cid_norm = normalize_card_id(cid_raw)
    q_id = normalize_card_id(q) if re.search(r"[A-Za-z0-9]", q) else ""
    if q_id:
        cid_compact = cid_norm.replace("-", "")
        q_compact = q_id.replace("-", "")
        if cid_norm.startswith(q_id) or q_compact in cid_compact or q_id in cid_norm:
            return True
    q_compact_lo = q_lower.replace("-", "").replace("_", "").replace(" ", "")
    cid_compact_lo = cid_lower.replace("-", "").replace("_", "").replace(" ", "")
    if q_compact_lo and q_compact_lo in cid_compact_lo:
        return True

    norms = query_norms if query_norms is not None else expand_query_match_norms(q)
    blob = card_search_norm_by_id.get(cid_norm) or ""
    if not blob:
        blob = build_card_search_blob(
            {
                "name": card_name,
                "name_en": name_en,
            }
        )
    for qn in norms:
        if qn and qn in blob:
            return True

    # Blob already includes TW/Hans/EN/alias norms — skip per-card OpenCC when present.
    if blob:
        return False

    # Fallback: raw / normalized direct checks on TW + EN names.
    for text in expand_name_search_texts(card_name, name_en):
        if q_lower in text.lower():
            return True
        q_name = normalize_name_for_match(q)
        if q_name and q_name in normalize_name_for_match(text):
            return True
    return False


def load_name_hans_by_en() -> None:
    global name_hans_by_en
    if not NAME_HANS_BY_EN_PATH.exists():
        name_hans_by_en = {}
        return
    try:
        payload = json.loads(NAME_HANS_BY_EN_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            name_hans_by_en = {str(k): str(v) for k, v in payload.items() if str(k).strip() and str(v).strip()}
        else:
            name_hans_by_en = {}
    except Exception:
        name_hans_by_en = {}


def load_name_aliases() -> None:
    global name_aliases_by_en
    if not NAME_ALIASES_PATH.exists():
        name_aliases_by_en = {}
        return
    try:
        payload = json.loads(NAME_ALIASES_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            name_aliases_by_en = {
                str(k).strip(): v
                for k, v in payload.items()
                if str(k).strip() and isinstance(v, dict)
            }
        else:
            name_aliases_by_en = {}
    except Exception:
        name_aliases_by_en = {}


def card_display_name_zh(basic: dict[str, Any] | None, *, hans: bool) -> str:
    """Paper TW name, or Mainland map when hans=True (Shanks→香克斯, Kaido→凯多)."""
    row = basic if isinstance(basic, dict) else {}
    name_tw = str(row.get("name") or "").strip()
    name_en = normalize_en_card_name(row.get("name_en"))
    alias = name_aliases_by_en.get(name_en) or {} if name_en else {}
    if hans:
        display = str(alias.get("display_hans") or "").strip()
        if not display and name_en:
            display = str(name_hans_by_en.get(name_en) or "").strip()
        return display or name_tw or name_en
    display = str(alias.get("display_hant") or "").strip()
    return display or name_tw or name_en


def _alias_texts_for_en(name_en: str | None) -> list[str]:
    key = normalize_en_card_name(name_en)
    row = name_aliases_by_en.get(key) or {}
    out: list[str] = []
    for item in row.get("aliases") or []:
        text = str(item or "").strip()
        if text:
            out.append(text)
    for field in ("display_hans", "display_hant"):
        text = str(row.get(field) or "").strip()
        if text:
            out.append(text)
    return out


def rebuild_card_search_index() -> None:
    global card_search_norm_by_id
    blob_map: dict[str, str] = {}
    for cid, basic in cards_by_id.items():
        blob_map[str(cid)] = build_card_search_blob(basic if isinstance(basic, dict) else {})
    card_search_norm_by_id = blob_map


def rebuild_leader_name_index() -> None:
    global leader_name_index
    rows: list[tuple[str, str]] = []
    for cid, basic in cards_by_id.items():
        category = str((basic or {}).get("category") or "").strip().lower()
        if category != "leader":
            continue
        name = str((basic or {}).get("name") or "").strip()
        if not name:
            continue
        key = normalize_name_for_match(name)
        if key:
            rows.append((key, cid))
    # longer name first to avoid short-token false matches.
    rows.sort(key=lambda x: len(x[0]), reverse=True)
    leader_name_index = rows


def infer_leader_card_from_archetype(archetype: str) -> str:
    text = str(archetype or "").strip()
    if not text:
        return ""
    # Remove "by xxx" suffix noise for better matching.
    text = re.sub(r"\s+by\s+.+$", "", text, flags=re.IGNORECASE).strip()
    normalized = normalize_name_for_match(text)
    if not normalized:
        return ""
    for name_key, cid in leader_name_index:
        if name_key and name_key in normalized:
            return cid
    return ""


def get_card_type(card_id: str) -> str:
    normalized = normalize_card_id(card_id)
    cached = card_type_cache.get(normalized)
    if cached is not None:
        return cached
    basic = cards_by_id.get(normalized, {})
    card_type = str(basic.get("category") or "").strip()
    if not card_type and basic:
        detail = build_card_response(normalized, basic)
        card_type = str(detail.card_type or "").strip()
    card_type_cache[normalized] = card_type
    return card_type


def is_leader_card(card_id: str) -> bool:
    card_type = get_card_type(card_id).lower()
    return card_type in {"leader", "领袖"}


def get_api_key() -> str:
    api_key = os.getenv(API_KEY_ENV_NAME, "").strip()
    if not api_key:
        api_key = os.getenv(API_KEY_FALLBACK_ENV_NAME, "").strip()
    if not api_key:
        raise RuntimeError(
            "缺少 API Key。请在 .env 中设置 "
            f"{API_KEY_ENV_NAME}=你的密钥"
        )
    return api_key


def load_official_rules_context() -> None:
    global official_rules_context, official_rules_files

    candidates: list[Path] = []
    if OFFICIAL_RULES_PATH.is_file():
        candidates.append(OFFICIAL_RULES_PATH)
    if OFFICIAL_RULES_PATH.is_dir():
        for ext in ("*.txt", "*.md", "*.json"):
            candidates.extend(sorted(OFFICIAL_RULES_PATH.glob(ext)))

    # Also allow project-root files like official_rules.txt,
    # even when official_rules/ directory exists.
    for ext in (".txt", ".md", ".json"):
        candidate = BASE_DIR / f"official_rules{ext}"
        if candidate.exists():
            candidates.append(candidate)
    if not candidates:
        raise RuntimeError(
            "未找到本地 official_rules。请创建 `official_rules/` 目录（txt/md/json）"
            "或 `official_rules.txt` 文件。"
        )

    chunks: list[str] = []
    used_files: list[str] = []
    for file_path in candidates:
        try:
            text = file_path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            chunks.append(f"[{file_path.name}]\n{text}")
            used_files.append(file_path.name)

    if not chunks:
        raise RuntimeError("official_rules 文件为空，无法作为 AI 分析依据。")

    official_rules_context = "\n\n".join(chunks)
    official_rules_files = used_files


def load_tournament_meta_context() -> None:
    global tournament_meta_context, limitless_top_decks, limitless_recent_tournaments
    if not LIMITLESS_META_FILE.exists():
        tournament_meta_context = ""
        limitless_top_decks = []
        limitless_recent_tournaments = []
        return
    try:
        data = json.loads(LIMITLESS_META_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        tournament_meta_context = ""
        limitless_top_decks = []
        limitless_recent_tournaments = []
        return
    tournament_meta_context = str(data.get("context_for_ai") or "").strip()
    top_decks = data.get("top_decks") or []
    recent_tournaments = data.get("recent_tournaments") or []
    limitless_top_decks = top_decks if isinstance(top_decks, list) else []
    limitless_recent_tournaments = (
        recent_tournaments if isinstance(recent_tournaments, list) else []
    )


def load_card_cooccurrence() -> None:
    global cooccurrence_map, card_count_stats
    if not LIMITLESS_COOCCURRENCE_FILE.exists():
        cooccurrence_map = {}
        card_count_stats = {}
        return
    try:
        data = json.loads(LIMITLESS_COOCCURRENCE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cooccurrence_map = {}
        card_count_stats = {}
        return
    raw = data.get("related_cards") or {}
    if isinstance(raw, dict):
        cooccurrence_map = {str(k).upper(): v for k, v in raw.items() if isinstance(v, list)}
    else:
        cooccurrence_map = {}
    raw_count_stats = data.get("card_count_stats") or {}
    if isinstance(raw_count_stats, dict):
        card_count_stats = {
            str(k).upper(): v for k, v in raw_count_stats.items() if isinstance(v, dict)
        }
    else:
        card_count_stats = {}


def load_market_price_data() -> None:
    global market_price_map, market_price_mtime, market_price_updated_at
    if not MARKET_PRICE_FILE.exists():
        market_price_map = {}
        market_price_mtime = 0.0
        market_price_updated_at = ""
        return
    try:
        payload = json.loads(MARKET_PRICE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        market_price_map = {}
        market_price_mtime = 0.0
        market_price_updated_at = ""
        return
    cards = payload.get("cards") if isinstance(payload, dict) else {}
    market_price_updated_at = (
        str(payload.get("updated_at") or "").strip() if isinstance(payload, dict) else ""
    )
    if isinstance(cards, dict):
        market_price_map = {
            normalize_card_id(str(k)): v
            for k, v in cards.items()
            if isinstance(v, dict)
        }
        try:
            market_price_mtime = MARKET_PRICE_FILE.stat().st_mtime
        except OSError:
            market_price_mtime = 0.0
    else:
        market_price_map = {}
        market_price_mtime = 0.0


def _parse_topdeck_date(raw: Any) -> tuple[int, int, int]:
    """Parse M/D/YYYY from topdecks; unknown → (0,0,0) so they sink when sorting newest-first."""
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", str(raw or "").strip())
    if not m:
        return (0, 0, 0)
    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= month <= 12 and 1 <= day <= 31 and year >= 2000):
        return (0, 0, 0)
    return (year, month, day)


def load_topdecks_data() -> None:
    """Load cached tournament decks from sync_topdecks.py output."""
    global topdecks_payload, topdecks_mtime, topdecks_by_id, topdecks_by_card_base
    global topdecks_appearances_by_card, topdecks_decks_sorted, topdecks_facets_cache
    global topdecks_meta_blob_by_id
    if not TOPDECKS_FILE.exists():
        topdecks_payload = {}
        topdecks_mtime = 0.0
        topdecks_by_id = {}
        topdecks_by_card_base = {}
        topdecks_appearances_by_card = {}
        topdecks_decks_sorted = []
        topdecks_facets_cache = {}
        topdecks_meta_blob_by_id = {}
        return
    try:
        mtime = TOPDECKS_FILE.stat().st_mtime
    except OSError:
        mtime = 0.0
    if topdecks_payload and mtime and mtime <= topdecks_mtime:
        return
    try:
        payload = json.loads(TOPDECKS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        topdecks_payload = {}
        topdecks_mtime = 0.0
        topdecks_by_id = {}
        topdecks_by_card_base = {}
        topdecks_appearances_by_card = {}
        topdecks_decks_sorted = []
        topdecks_facets_cache = {}
        topdecks_meta_blob_by_id = {}
        return
    if not isinstance(payload, dict):
        topdecks_payload = {}
        topdecks_mtime = 0.0
        topdecks_by_id = {}
        topdecks_by_card_base = {}
        topdecks_appearances_by_card = {}
        topdecks_decks_sorted = []
        topdecks_facets_cache = {}
        topdecks_meta_blob_by_id = {}
        return
    decks = payload.get("decks") if isinstance(payload.get("decks"), list) else []
    by_id: dict[str, dict[str, Any]] = {}
    by_card: dict[str, set[str]] = {}
    appearances: dict[str, list[tuple[tuple[int, int, int], str, int, bool]]] = {}
    sorted_rows: list[dict[str, Any]] = []
    for row in decks:
        if not isinstance(row, dict):
            continue
        did = str(row.get("id") or "").strip()
        if not did:
            continue
        by_id[did] = row
        sorted_rows.append(row)
        date_key = _parse_topdeck_date(row.get("date"))
        leader = normalize_card_id(str(row.get("leader") or ""))
        leader_base = _base_card_id(leader) if leader else ""
        qty_by_base: dict[str, int] = {}
        cards = row.get("cards") if isinstance(row.get("cards"), dict) else {}
        for raw_id, raw_qty in cards.items():
            cid = normalize_card_id(str(raw_id))
            if not cid:
                continue
            base = _base_card_id(cid)
            try:
                n = max(0, int(raw_qty or 0))
            except (TypeError, ValueError):
                n = 0
            if n <= 0:
                continue
            qty_by_base[base] = int(qty_by_base.get(base) or 0) + n
        if leader_base and int(qty_by_base.get(leader_base) or 0) <= 0:
            qty_by_base[leader_base] = 1
        for base, qty in qty_by_base.items():
            by_card.setdefault(base, set()).add(did)
            appearances.setdefault(base, []).append(
                (date_key, did, int(qty), bool(leader_base and base == leader_base))
            )
    for rows in appearances.values():
        rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
    sorted_rows.sort(
        key=lambda row: (
            _parse_topdeck_date(row.get("date")),
            str(row.get("placement") or ""),
            str(row.get("name") or ""),
            str(row.get("id") or ""),
        ),
        reverse=True,
    )
    payload["decks"] = sorted_rows
    topdecks_payload = payload
    topdecks_by_id = by_id
    topdecks_by_card_base = by_card
    topdecks_appearances_by_card = appearances
    topdecks_decks_sorted = sorted_rows
    topdecks_mtime = mtime
    # Facets / search blobs are built lazily on first request (functions defined later).
    topdecks_facets_cache = {}
    topdecks_meta_blob_by_id = {}


def _topdeck_query_matching_card_bases(query: str) -> set[str]:
    """Resolve free-text query to base card ids (name / id; parallels share base)."""
    q = str(query or "").strip()
    if not q:
        return set()
    bases: set[str] = set()
    if re.search(r"[A-Za-z]", q) and "-" in q:
        q_id = normalize_card_id(q)
        if q_id:
            bases.add(_base_card_id(q_id))
    q_norms = expand_query_match_norms(q)
    for cid, basic in cards_by_id.items():
        if not isinstance(basic, dict):
            continue
        cid_s = str(cid)
        if cid_s.upper().startswith("DON"):
            continue
        name = str(basic.get("name") or "")
        name_en = str(basic.get("name_en") or "") or None
        if card_matches_text_query(cid_s, name, q, name_en=name_en, query_norms=q_norms):
            bases.add(_base_card_id(cid_s))
    return bases


def _topdeck_row_meta_blob(row: dict[str, Any]) -> str:
    leader = normalize_card_id(str(row.get("leader") or ""))
    leader_basic = cards_by_id.get(leader) or cards_by_id.get(_base_card_id(leader)) or {}
    name_en = normalize_en_card_name(leader_basic.get("name_en"))
    parts = [
        row.get("name"),
        row.get("author"),
        row.get("tournament"),
        row.get("placement"),
        row.get("country"),
        row.get("host"),
        row.get("leader"),
        row.get("meta_title"),
        leader_basic.get("name"),
        leader_basic.get("name_en"),
        name_hans_by_en.get(name_en, "") if name_en else "",
    ]
    return " ".join(str(p or "") for p in parts).lower()


def ensure_topdecks_data_fresh() -> None:
    if not TOPDECKS_FILE.exists():
        return
    try:
        mtime = TOPDECKS_FILE.stat().st_mtime
    except OSError:
        return
    if mtime > topdecks_mtime:
        load_topdecks_data()


def ensure_market_price_data_fresh() -> None:
    global market_price_mtime
    try:
        current_mtime = MARKET_PRICE_FILE.stat().st_mtime
    except OSError:
        current_mtime = 0.0
    if current_mtime > market_price_mtime:
        load_market_price_data()


def _is_hard_miss_price_status(status: str) -> bool:
    s = str(status or "").strip().lower()
    return "variant_not_found" in s or "price_not_found" in s


def visible_market_current_price(info: dict[str, Any] | None) -> Any:
    """Hard matcher misses must not keep showing a leftover yen price. 429 keeps it."""
    if not isinstance(info, dict):
        return None
    if _is_hard_miss_price_status(str(info.get("status") or "")):
        return None
    return info.get("current_price")


def _count_visible_priced_entries() -> int:
    priced = 0
    for info in market_price_map.values():
        if not isinstance(info, dict):
            continue
        raw = visible_market_current_price(info)
        try:
            n = int(raw) if raw is not None else None
        except (TypeError, ValueError):
            n = None
        if n is not None and n > 0:
            priced += 1
    return priced


def get_market_price_info(card_id: str, exact: bool = False) -> dict[str, Any] | None:
    ensure_market_price_data_fresh()
    card_key = normalize_card_id(card_id)
    candidates = [card_key]
    if not exact:
        base_id = _base_card_id(card_key)
        if base_id not in candidates:
            candidates.append(base_id)
        compact = card_key.replace("-", "")
        if compact not in candidates:
            candidates.append(compact)
    info = None
    for key in candidates:
        maybe = market_price_map.get(key)
        if isinstance(maybe, dict):
            info = maybe
            break
    if not isinstance(info, dict):
        return None
    history = info.get("history")
    if not isinstance(history, list):
        history = []
    cleaned_history: list[dict[str, Any]] = []
    for row in history:
        if not isinstance(row, dict):
            continue
        ts = str(row.get("ts") or "").strip()
        price = row.get("price")
        if not ts:
            continue
        try:
            price_val = int(price) if price is not None else None
        except (TypeError, ValueError):
            price_val = None
        cleaned_history.append({"ts": ts, "price": price_val})
    return {
        "source": str(info.get("source") or "yuyu-tei"),
        "currency": str(info.get("currency") or "JPY"),
        "current_price": visible_market_current_price(info),
        "last_seen": str(info.get("last_seen") or ""),
        "last_checked": str(info.get("last_checked") or ""),
        "history": cleaned_history,
    }


def load_official_snapshot_data() -> None:
    global official_snapshot_map
    if not OFFICIAL_SYNC_SNAPSHOT_FILE.exists():
        official_snapshot_map = {}
        return
    try:
        payload = json.loads(OFFICIAL_SYNC_SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        official_snapshot_map = {}
        return
    rows = payload.get("cards") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        official_snapshot_map = {}
        return
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = normalize_card_id(str(row.get("id") or ""))
        if not cid:
            continue
        mapped[cid] = row
    official_snapshot_map = mapped


def load_cached_attribute_map() -> None:
    global cached_attribute_map
    if not ATTRIBUTE_CACHE_FILE.exists():
        cached_attribute_map = {}
        return
    try:
        payload = json.loads(ATTRIBUTE_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cached_attribute_map = {}
        return
    raw = payload.get("cards") if isinstance(payload, dict) else {}
    if not isinstance(raw, dict):
        cached_attribute_map = {}
        return
    out: dict[str, list[str]] = {}
    for k, v in raw.items():
        cid = normalize_card_id(str(k))
        if not cid:
            continue
        if isinstance(v, list):
            attrs = [str(x).strip() for x in v if str(x).strip()]
            if attrs:
                out[cid] = attrs
    cached_attribute_map = out


def rebuild_variant_id_map() -> None:
    global variant_id_map
    grouped: dict[str, list[str]] = {}
    for cid in cards_by_id.keys():
        normalized = normalize_card_id(cid)
        base = _base_card_id(normalized)
        if normalized == base:
            grouped.setdefault(base, [])
            continue
        grouped.setdefault(base, []).append(normalized)
    variant_id_map = {k: sorted(list(dict.fromkeys(v))) for k, v in grouped.items()}


def pack_image_public_url(filename: str) -> str:
    """对外返回的卡图 URL：CDN 根路径文件名，或未配置时 API 的 /packs 。"""
    fname = Path(str(filename)).name
    if not fname:
        return f"{API_BASE_URL}/packs/"
    if OPCG_PACKS_PUBLIC_URL:
        return f"{OPCG_PACKS_PUBLIC_URL}/{fname}"
    return f"{API_BASE_URL}/packs/{fname}"


def card_image_proxy_url(card_id: str) -> str | None:
    """浏览器无法直接加载官方图床（CORP same-site）；改走本机 API 代理。"""
    card_key = normalize_card_id(card_id)
    if not card_key or card_key not in cards_by_id:
        return None
    existing = local_image_url_map.get(card_key)
    if existing:
        return existing
    return f"{API_BASE_URL}/images/card/{card_key}"


def _guess_image_media_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    if ext == ".gif":
        return "image/gif"
    return "image/png"


_PACK_MANIFEST_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _packs_manifest_files() -> list[Path]:
    """R2 同步后可在本机生成清单，VPS 删空 packs/ 时仍能提供 img_local_url。"""
    raw = os.getenv("OPCG_PACKS_MANIFEST", "").strip()
    if raw:
        p = Path(raw)
        path = p if p.is_absolute() else BASE_DIR / p
        return [path] if path.is_file() else []
    default = BASE_DIR / "meta" / "pack_files_r2.txt"
    return [default] if default.is_file() else []


def _parse_pack_manifest_filename(line: str) -> str | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split()
    if len(parts) >= 2 and parts[0].isdigit():
        name = " ".join(parts[1:]).strip()
    else:
        name = line.strip()
    name = Path(name).name
    if not name or name == "." or name == "..":
        return None
    return name


def rebuild_local_image_url_map() -> None:
    global local_image_url_map, local_image_path_map
    mapped: dict[str, str] = {}
    path_map: dict[str, Path] = {}
    for mf in _packs_manifest_files():
        try:
            body = mf.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in body.splitlines():
            fname = _parse_pack_manifest_filename(line)
            if not fname:
                continue
            if Path(fname).suffix.lower() not in _PACK_MANIFEST_IMAGE_EXTS:
                continue
            cid = normalize_card_id(Path(fname).stem)
            if not cid or cid in mapped:
                continue
            mapped[cid] = pack_image_public_url(fname)
    for file_path in sorted(PACKS_DIR.glob("*.*")):
        if not file_path.is_file():
            continue
        cid = normalize_card_id(file_path.stem)
        if not cid:
            continue
        mapped[cid] = pack_image_public_url(file_path.name)
        path_map[cid] = file_path
    local_image_url_map = mapped
    local_image_path_map = path_map


def rebuild_filter_index() -> None:
    """Warm filter rows once at startup so each search skips response rebuild."""
    global filter_index
    rows: list[FilterIndexEntry] = []
    for cid, basic in cards_by_id.items():
        basic_dict = basic if isinstance(basic, dict) else {}
        resp = build_filter_card_response(cid, basic_dict)
        attrs = frozenset(
            str(a).strip().lower() for a in (resp.attributes or []) if str(a).strip()
        )
        rows.append(
            FilterIndexEntry(
                id=str(resp.id),
                sort_key=card_id_sort_key(resp.id),
                colors=frozenset(expand_color_tokens(resp.colors or [])),
                card_type=str(resp.card_type or "").strip().lower(),
                attrs=attrs,
                series=infer_series_from_card_id(str(resp.id)),
                rarity=rarity_match_key(resp.rarity),
                block=_to_int(resp.block_number),
                cost=_to_int(resp.cost),
                counter=_to_int(resp.counter),
                power=_to_int(resp.power),
                keywords=card_filter_keywords(cid, basic_dict),
                name=str(resp.name or ""),
                name_en=str(resp.name_en or ""),
                response=resp,
            )
        )
    rows.sort(key=lambda r: r.sort_key)
    filter_index = rows


def _snapshot_to_card_fields(card_id: str) -> dict[str, Any]:
    row = official_snapshot_map.get(normalize_card_id(card_id), {})
    if not isinstance(row, dict):
        return {}
    fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}

    def _split_slash(raw: Any) -> list[str]:
        return [str(x).strip() for x in str(raw or "").split("/") if str(x).strip()]

    out: dict[str, Any] = {}
    if row.get("name"):
        out["name"] = row.get("name")
    if row.get("rarity"):
        out["rarity"] = row.get("rarity")
    if row.get("card_type"):
        out["category"] = row.get("card_type")
    if fields.get("color"):
        out["colors"] = _split_slash(fields.get("color"))
    if fields.get("attribute"):
        out["attributes"] = _split_slash(fields.get("attribute"))
    if fields.get("type"):
        out["types"] = _split_slash(fields.get("type"))
    card_sets = [str(x).strip() for x in (row.get("card_sets") or []) if str(x).strip()]
    if card_sets:
        out["card_sets"] = card_sets
    if fields.get("effect"):
        out["effect"] = fields.get("effect")
    # Prefer official cost; only fallback to life for leader-like records that may not expose cost.
    # Non-leaders print 0 as "-" in the official cost/life node.
    is_leader = bool(re.search(r"leader|領袖|领袖", str(row.get("card_type") or ""), flags=re.I))
    if fields.get("cost") is not None:
        cv = str(fields.get("cost")).strip()
        if cv.isdigit():
            out["cost"] = int(cv)
        elif not is_leader and cv in {"-", "—", "－"}:
            out["cost"] = 0
    if fields.get("life") is not None:
        lv = str(fields.get("life")).strip()
        if lv.isdigit():
            out["life"] = int(lv)
        if "cost" not in out:
            if lv.isdigit():
                out["cost"] = int(lv)
            elif not is_leader and lv in {"-", "—", "－", ""}:
                out["cost"] = 0
    if fields.get("power"):
        pv = str(fields.get("power")).replace(",", "").strip()
        out["power"] = int(pv) if pv.isdigit() else fields.get("power")
    if fields.get("counter"):
        cv = str(fields.get("counter")).replace(",", "").strip()
        out["counter"] = int(cv) if cv.isdigit() else fields.get("counter")
    if fields.get("block_icon"):
        bv = str(fields.get("block_icon")).strip()
        out["block_number"] = int(bv) if bv.isdigit() else None
    images = row.get("image_candidates")
    if isinstance(images, list) and images:
        first = str(images[0] or "").strip()
        if first:
            out["img_url"] = first
            out["img_full_url"] = first
    return out


def _get_local_card_image_path(card_id: str, img_local_url: Any) -> Path | None:
    card_key = normalize_card_id(card_id)
    if img_local_url:
        text = str(img_local_url).strip()
        if "/packs/" in text:
            name = Path(text.rsplit("/packs/", 1)[-1].split("?", 1)[0]).name
            path = PACKS_DIR / name
            if path.exists():
                return path
        pub = OPCG_PACKS_PUBLIC_URL
        if pub and text.startswith(f"{pub}/"):
            name = Path(text.split("?", 1)[0][len(pub) + 1 :]).name
            if name:
                path = PACKS_DIR / name
                if path.exists():
                    return path
        if text.startswith("http://") or text.startswith("https://"):
            name = Path(text.rsplit("/", 1)[-1].split("?", 1)[0]).name
            if name:
                path = PACKS_DIR / name
                if path.exists():
                    return path
    candidates = list(PACKS_DIR.glob(f"{card_key}.*"))
    if candidates:
        return candidates[0]
    return None


def _infer_attributes_from_local_image(card_id: str, img_local_url: Any, img_full_url: Any) -> list[str]:
    if not ATTRIBUTE_OCR_ENABLED:
        return []
    cached = attribute_ocr_cache.get(card_id)
    if cached is not None:
        return cached
    image_path = _get_local_card_image_path(card_id, img_local_url)

    try:
        from rapidocr_onnxruntime import RapidOCR  # noqa: F401
    except Exception:
        attribute_ocr_cache[card_id] = []
        return []

    engine = _get_rapidocr_engine()
    if engine is None:
        attribute_ocr_cache[card_id] = []
        return []

    result = None
    if image_path and image_path.exists():
        try:
            result, _ = engine(str(image_path))
        except Exception:
            result = None
    elif img_full_url:
        try:
            resp = requests.get(
                str(img_full_url).strip(),
                timeout=6,
                headers={
                    "User-Agent": "Mozilla/5.0 OPCG-API/1.0",
                    "Referer": OFFICIAL_IMAGE_HOSTS[0],
                },
            )
            if resp.status_code == 200 and resp.content:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
                    tmp.write(resp.content)
                    tmp.flush()
                    result, _ = engine(tmp.name)
        except Exception:
            result = None
    if result is None:
        attribute_ocr_cache[card_id] = []
        return []

    text_blob = " ".join(str(item[1]) for item in (result or []) if isinstance(item, (list, tuple)) and len(item) >= 2).upper()
    mapping = [
        ("STRIKE", "打擊"),
        ("SLASH", "斬擊"),
        ("SPECIAL", "特殊"),
        ("RANGED", "遠程"),
        ("WISDOM", "智慧"),
        ("打", "打擊"),
        ("斬", "斬擊"),
        ("特", "特殊"),
        ("射", "遠程"),
        ("知", "智慧"),
    ]
    out: list[str] = []
    for token, zh in mapping:
        if token in text_blob and zh not in out:
            out.append(zh)
    attribute_ocr_cache[card_id] = out
    return out


def get_cooccurrence_hint(card_id: str) -> str:
    normalized = normalize_card_id(card_id)
    related = cooccurrence_map.get(normalized, [])
    if not related:
        return ""
    top = related[:8]
    parts = [f"{item.get('card_id')}({item.get('cooccur')})" for item in top]
    return "；".join(parts)


def get_cooccurrence_items(card_id: str, min_cooccur: int = 2) -> list[dict[str, Any]]:
    normalized = normalize_card_id(card_id)
    related = cooccurrence_map.get(normalized, [])
    filtered = [
        x
        for x in related
        if isinstance(x, dict)
        and str(x.get("card_id") or "").strip()
        and int(x.get("cooccur") or 0) >= min_cooccur
    ]
    return filtered[:20]


def get_core_priority_cards(card_id: str, max_cards: int = 3) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for item in get_cooccurrence_items(card_id, min_cooccur=2):
        cid = normalize_card_id(str(item.get("card_id") or ""))
        if not cid or is_leader_card(cid):
            continue
        basic = cards_by_id.get(cid)
        if not basic:
            continue
        stat = card_count_stats.get(cid, {})
        score = int(item.get("cooccur") or 0) * 10 + int(stat.get("most_common_count") or 0)
        ranked.append(
            {
                "card_id": cid,
                "name": str(basic.get("name") or "").strip(),
                "cooccur": int(item.get("cooccur") or 0),
                "most_common_count": int(stat.get("most_common_count") or 0),
                "score": score,
            }
        )
    ranked.sort(key=lambda x: (x["score"], x["cooccur"]), reverse=True)
    return ranked[:max_cards]


def infer_card_role(card_id: str) -> str:
    normalized_id = normalize_card_id(card_id)
    basic = cards_by_id.get(normalized_id)
    if not basic:
        return "联动件"

    cached = card_analysis_cache.get(normalized_id)
    if cached is None:
        full_card: dict[str, Any] = {}
        pack_id = basic.get("pack_id")
        if pack_id:
            pack_data = load_pack_data(str(pack_id))
            if pack_data is not None:
                full_card = extract_card_from_pack(pack_data, normalized_id) or {}
        raw_effect = full_card.get("effect") or basic.get("effect")
        cached = {
            "card_type": str(full_card.get("category") or basic.get("category") or "").lower(),
            "effect": str(normalize_effect_text(raw_effect) or "").lower(),
            "power": full_card.get("power") if full_card.get("power") is not None else basic.get("power"),
            "counter": full_card.get("counter") if full_card.get("counter") is not None else basic.get("counter"),
            "cost": full_card.get("cost") if full_card.get("cost") is not None else basic.get("cost"),
        }
        card_analysis_cache[normalized_id] = cached

    ctype = str(cached.get("card_type") or "").lower()
    effect = str(cached.get("effect") or "").lower()
    power = int(cached.get("power") or 0) if str(cached.get("power") or "").isdigit() else 0
    counter = int(cached.get("counter") or 0) if str(cached.get("counter") or "").isdigit() else 0
    cost = int(cached.get("cost") or 0) if str(cached.get("cost") or "").isdigit() else 0

    if ctype == "event":
        return "解场件"
    if "ko" in effect or "移除" in effect or "除去" in effect:
        return "解场件"
    if "draw" in effect or "抽" in effect or "检索" in effect or "search" in effect:
        return "过牌件"
    if counter >= 2000 or "blocker" in effect or "防御" in effect or "阻挡" in effect:
        return "防守件"
    if power >= 7000 or cost >= 7:
        return "终结点"
    return "联动件"


def get_role_priority_cards(card_id: str, max_cards: int = 6) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in get_cooccurrence_items(card_id, min_cooccur=2)[:20]:
        cid = normalize_card_id(str(item.get("card_id") or ""))
        if not cid or is_leader_card(cid):
            continue
        basic = cards_by_id.get(cid)
        if not basic:
            continue
        result.append(
            {
                "card_id": cid,
                "name": str(basic.get("name") or "").strip(),
                "role": infer_card_role(cid),
                "cooccur": int(item.get("cooccur") or 0),
            }
        )
        if len(result) >= max_cards:
            break
    return result


def _archetype_color_tokens(archetype: str) -> set[str]:
    text = str(archetype or "").strip().lower()
    out: set[str] = set()
    for c in ("red", "blue", "green", "purple", "black", "yellow"):
        if c in text:
            out.add(c)
    return out


def get_relevant_top_decks(
    card_id: str,
    colors: list[str],
    max_items: int = 12,
    enforce_leader_match: bool = False,
) -> list[dict[str, Any]]:
    prefix = get_series_prefix(card_id)
    target_id = normalize_card_id(card_id)
    target_colors = {str(c).strip().lower() for c in colors if str(c).strip()}
    scored: list[tuple[float, dict[str, Any]]] = []
    for deck in limitless_top_decks:
        if not isinstance(deck, dict):
            continue
        arche = str(deck.get("archetype") or "").strip()
        if not arche:
            continue
        leader_card = str(deck.get("leader_card") or "").upper()
        inferred_leader = infer_leader_card_from_archetype(arche)
        effective_leader = leader_card or inferred_leader
        if enforce_leader_match and effective_leader != target_id:
            continue
        share = float(deck.get("share_percent") or 0.0)
        sample_count = int(deck.get("sample_count") or 0)
        from_tournaments = int(deck.get("from_tournaments") or 0)
        arche_colors = _archetype_color_tokens(arche)

        score = 0.0
        if effective_leader.startswith(prefix):
            score += 4.0
        if target_colors and arche_colors:
            score += float(len(target_colors.intersection(arche_colors))) * 3.0
        score += min(share, 60.0) / 10.0
        score += min(sample_count, 30) / 6.0
        score += min(from_tournaments, 20) / 10.0
        if score <= 0:
            continue
        enriched = dict(deck)
        if inferred_leader and not leader_card:
            enriched["leader_card"] = inferred_leader
        scored.append((score, enriched))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored[:max_items]]


def build_50_card_plan(
    seed_ids: list[str],
    fallback_colors: list[str] | None = None,
    max_copies_per_card: int = 4,
    require_tournament_evidence: bool = False,
    allowed_ids: set[str] | None = None,
    require_count_stats: bool = False,
) -> list[tuple[str, int]]:
    pool: list[str] = []
    seen: set[str] = set()
    for cid in seed_ids:
        normalized = normalize_card_id(cid)
        if not normalized or normalized in seen or is_leader_card(normalized):
            continue
        if normalized not in cards_by_id:
            continue
        if allowed_ids is not None and normalized not in allowed_ids:
            continue
        if require_count_stats and normalized not in card_count_stats:
            continue
        # seed_ids already come from cooccurrence/ranking pipeline, treat as tournament-evidenced.
        seen.add(normalized)
        pool.append(normalized)

    # If pool is too small, backfill with tournament-observed same-color non-leader cards.
    if len(pool) < 13:
        color_set = {str(c).strip().lower() for c in (fallback_colors or []) if str(c).strip()}
        observed_ids = sorted(
            card_count_stats.keys(),
            key=lambda x: int((card_count_stats.get(x) or {}).get("mentions") or 0),
            reverse=True,
        )
        for cid in observed_ids:
            basic = cards_by_id.get(cid) or {}
            normalized = normalize_card_id(cid)
            if normalized in seen or is_leader_card(normalized):
                continue
            if allowed_ids is not None and normalized not in allowed_ids:
                continue
            if require_count_stats and normalized not in card_count_stats:
                continue
            if color_set:
                card_colors = {str(c).strip().lower() for c in (basic.get("colors") or []) if str(c).strip()}
                if not card_colors.intersection(color_set):
                    continue
            seen.add(normalized)
            pool.append(normalized)
            if len(pool) >= 20:
                break

    # Last-resort backfill (still color-filtered), but avoid cards with no basic data.
    if len(pool) < 13 and not require_tournament_evidence:
        color_set = {str(c).strip().lower() for c in (fallback_colors or []) if str(c).strip()}
        for cid, basic in cards_by_id.items():
            normalized = normalize_card_id(cid)
            if normalized in seen or is_leader_card(normalized):
                continue
            if allowed_ids is not None and normalized not in allowed_ids:
                continue
            if require_count_stats and normalized not in card_count_stats:
                continue
            if color_set:
                card_colors = {str(c).strip().lower() for c in (basic.get("colors") or []) if str(c).strip()}
                if not card_colors.intersection(color_set):
                    continue
            seen.add(normalized)
            pool.append(normalized)
            if len(pool) >= 20:
                break

    # Rank pool by tournament evidence (mentions/cooccur/count mode).
    def score(cid: str) -> int:
        stat = card_count_stats.get(cid, {})
        mentions = int(stat.get("mentions") or 0)
        weighted_mentions = float(stat.get("mentions_weighted") or 0.0)
        common = int(stat.get("most_common_count") or 0)
        ratio = float(stat.get("most_common_ratio") or 0.0)
        # Weighted mentions reflect tournament scale quality (large events weigh more).
        return int(weighted_mentions * 12) + mentions * 4 + common * 5 + int(ratio * 100)

    pool = sorted(pool, key=score, reverse=True)
    if require_tournament_evidence and not pool:
        return []

    # Allocate counts to exactly 50 cards, preferring tournament common counts.
    counts: dict[str, int] = {cid: 0 for cid in pool}
    remaining = 50
    for cid in pool:
        stat = card_count_stats.get(cid, {})
        suggested = int(stat.get("most_common_count") or 0)
        if suggested <= 0:
            continue
        add = min(max(1, suggested), max_copies_per_card, remaining)
        counts[cid] = add
        remaining -= add
        if remaining <= 0:
            break

    idx = 0
    order = pool[:]
    while remaining > 0 and order:
        cid = order[idx % len(order)]
        if counts[cid] < max_copies_per_card:
            counts[cid] += 1
            remaining -= 1
        idx += 1
        if idx > len(order) * 2 and all(v >= max_copies_per_card for v in counts.values()):
            break

    if remaining > 0:
        return []

    result = [(cid, cnt) for cid, cnt in counts.items() if cnt > 0]
    # Higher counts first, then stable ID order.
    result.sort(key=lambda x: (-x[1], x[0]))
    return result


def build_leader_deck_advice(card_id: str, card_name: str, colors: list[str] | None = None) -> AIAdvice:
    strict_matched_decks = get_relevant_top_decks(
        card_id,
        colors or [],
        max_items=5,
        enforce_leader_match=True,
    )
    fallback_matched_decks: list[dict[str, Any]] = []
    # If strict leader match has no samples, fallback to same-color/same-meta decks.
    if not strict_matched_decks:
        fallback_matched_decks = get_relevant_top_decks(
            card_id,
            colors or [],
            max_items=5,
            enforce_leader_match=False,
        )
    matched_decks = strict_matched_decks if strict_matched_decks else fallback_matched_decks

    # Keep only credible references for user-facing leader plans.
    # 0.00% micro-sample rows are too noisy for direct recommendation.
    credible_decks: list[dict[str, Any]] = []
    for d in matched_decks:
        share = float(d.get("share_percent") or 0.0)
        sample = int(d.get("sample_count") or 0)
        tours = int(d.get("from_tournaments") or 0)
        if share >= 0.2 or sample >= 8 or tours >= 20:
            credible_decks.append(d)
    matched_decks = credible_decks
    role_cards = get_role_priority_cards(card_id, max_cards=8)
    cooccur_by_card: dict[str, int] = {}
    role_groups: dict[str, list[str]] = {
        "终结点": [],
        "解场件": [],
        "防守件": [],
        "过牌件": [],
        "联动件": [],
    }
    for item in role_cards:
        role = str(item.get("role") or "联动件")
        cid = str(item.get("card_id") or "").strip()
        if role in role_groups and cid:
            role_groups[role].append(cid)
            cooccur_by_card[cid] = int(item.get("cooccur") or 0)

    # Leader-specific strict candidate pool:
    # only cards with tournament evidence and linked by cooccurrence/statistics.
    allowed_pool: set[str] = set()
    for item in get_cooccurrence_items(card_id, min_cooccur=1):
        cid = normalize_card_id(str(item.get("card_id") or ""))
        if not cid or is_leader_card(cid):
            continue
        if cid in card_count_stats:
            allowed_pool.add(cid)
    for cid in role_groups["终结点"] + role_groups["解场件"] + role_groups["防守件"] + role_groups["过牌件"] + role_groups["联动件"]:
        n = normalize_card_id(cid)
        if n and n in card_count_stats and not is_leader_card(n):
            allowed_pool.add(n)

    top_meta_lines = [
        f"#{d.get('rank')} {d.get('archetype')} ({d.get('share_percent')}%)"
        for d in matched_decks[:3]
    ]
    config_parts: list[str] = []
    if role_groups["终结点"]:
        config_parts.append(f"终结点建议 6-10 张（例：{', '.join(role_groups['终结点'][:3])}）")
    if role_groups["解场件"]:
        config_parts.append(f"解场件建议 8-12 张（例：{', '.join(role_groups['解场件'][:3])}）")
    if role_groups["防守件"]:
        config_parts.append(f"防守件建议 6-10 张（例：{', '.join(role_groups['防守件'][:3])}）")
    if role_groups["过牌件"]:
        config_parts.append(f"过牌/检索建议 8-12 张（例：{', '.join(role_groups['过牌件'][:3])}）")

    if not config_parts:
        config_parts.append("当前赛事样本较少，建议先按主流榜单构建 50 张主卡并进行 10 局小样本测试。")

    meta_summary = "；".join(top_meta_lines) if top_meta_lines else "暂无足够高可信 Top Deck 样本"
    play_tip = (
        f"Leader 专项建议（{card_id} {card_name}）："
        f"参考近期环境 {meta_summary}。"
        f"牌组配置建议：{'；'.join(config_parts)}。"
        "玩法建议：前期优先稳定资源与过牌，中期围绕解场+防守控制交换，"
        "后期保留终结点与关键事件完成收束。"
    )
    seed_profiles: list[tuple[str, list[str], str]] = [
        (
            "均衡",
            role_groups["终结点"] + role_groups["解场件"] + role_groups["防守件"] + role_groups["过牌件"] + role_groups["联动件"],
            "平衡解场、防守与终结能力，适合大多数对局节奏。",
        ),
        (
            "控制",
            role_groups["解场件"] + role_groups["防守件"] + role_groups["过牌件"] + role_groups["终结点"] + role_groups["联动件"],
            "优先资源交换与解场，拖入中后期通过终结点收束。",
        ),
        (
            "节奏",
            role_groups["过牌件"] + role_groups["联动件"] + role_groups["终结点"] + role_groups["解场件"] + role_groups["防守件"],
            "前中期通过过牌和联动抢节奏，维持场面压制。",
        ),
    ]
    def format_plan_lines(alloc: list[tuple[str, int]]) -> list[str]:
        sample_base = 0
        weighted_sample_base = 0.0
        cooccur_base = 0
        for cid, _ in alloc:
            stat = card_count_stats.get(cid, {})
            sample_base = max(sample_base, int(stat.get("mentions") or 0))
            weighted_sample_base = max(weighted_sample_base, float(stat.get("mentions_weighted") or 0.0))
            cooccur_base = max(cooccur_base, int(cooccur_by_card.get(cid) or 0))
        if sample_base <= 0:
            sample_base = 1
        if weighted_sample_base <= 0:
            weighted_sample_base = 1.0
        if cooccur_base <= 0:
            cooccur_base = 1

        def count_prob_text(cid: str) -> str:
            stat = card_count_stats.get(cid, {})
            dist = stat.get("distribution") or {}
            total = sum(int(v or 0) for v in dist.values())
            if total <= 0:
                return "1-4张概率: 暂无统计"
            probs: list[str] = []
            for n in (1, 2, 3, 4):
                p = (int(dist.get(str(n), 0) or 0) / total) * 100
                probs.append(f"{n}张 {p:.0f}%")
            return " / ".join(probs)

        lines: list[str] = []
        for cid, cnt in alloc:
            stat = card_count_stats.get(cid, {})
            mentions = int(stat.get("mentions") or 0)
            weighted_mentions = float(stat.get("mentions_weighted") or 0.0)
            if weighted_mentions > 0:
                weighted_ratio = (weighted_mentions / weighted_sample_base) * 100
                usage_text = f"加权样本 {weighted_mentions:.1f}（相对强度 {weighted_ratio:.1f}%）"
            elif mentions > 0:
                raw_ratio = (mentions / sample_base) * 100
                usage_text = f"赛事样本 {mentions}（相对强度 {raw_ratio:.1f}%）"
            else:
                usage_text = "赛事样本较少"
            lines.append(
                f"{cid} x{cnt}（{usage_text}｜{count_prob_text(cid)}）"
            )
        return lines

    leader_deck_plans: list[dict[str, Any]] = []
    strict_mode = bool(strict_matched_decks)
    for idx, deck in enumerate(matched_decks[:3]):
        profile_name, seed_ids, profile_tip = seed_profiles[idx % len(seed_profiles)]
        alloc = build_50_card_plan(
            seed_ids,
            fallback_colors=colors,
            require_tournament_evidence=False,
            allowed_ids=allowed_pool if allowed_pool else None,
            require_count_stats=True,
        )
        if not alloc:
            continue
        cards_lines = format_plan_lines(alloc)
        if not cards_lines:
            continue
        arche = str(deck.get("archetype") or "主流构筑").strip()
        rank = int(deck.get("rank") or 0)
        share = float(deck.get("share_percent") or 0.0)
        sample = int(deck.get("sample_count") or 0)
        tours = int(deck.get("from_tournaments") or 0)
        display_no = idx + 1
        title = f"同环境参考#{display_no}"
        if strict_mode:
            ref_note = f"（来源样本：{arche}）"
        else:
            ref_note = f"（来源样本：{arche}；非该Leader直连样本，仅作环境补充参考）"
        leader_deck_plans.append(
            {
                "name": title,
                "cards": cards_lines,
                "playstyle": (
                    f"占比约 {share:.2f}%"
                    f"{f'（样本 {sample}）' if sample > 0 else ''}"
                    f"{f'，来源赛事 {tours} 场' if tours > 0 else ''}。"
                    f"{ref_note}"
                    f"AI 解析：{profile_tip}（主卡组共50张，不含Leader）。"
                ),
            }
        )

    # Fallback to role-profile plans if no matched deck references are available.
    if not leader_deck_plans:
        for profile_name, seed_ids, profile_tip in seed_profiles:
            alloc = build_50_card_plan(
                seed_ids,
                fallback_colors=colors,
                require_tournament_evidence=False,
                allowed_ids=allowed_pool if allowed_pool else None,
                require_count_stats=True,
            )
            if not alloc:
                continue
            cards_lines = format_plan_lines(alloc)
            if not cards_lines:
                continue
            leader_deck_plans.append(
                {
                    "name": f"{profile_name}构筑",
                    "cards": cards_lines,
                    "playstyle": f"AI 解析：{profile_tip}（主卡组共50张，不含Leader）。",
                }
            )

    has_any_plan = bool(leader_deck_plans)
    # Keep panel available when we at least have same-meta references.
    insufficient = not has_any_plan and not bool(matched_decks)
    reasons = [] if not insufficient else ["该 Leader 相关比赛样本不足，已停止自动构筑以避免瞎掰。"]
    return AIAdvice(
        combos=[],
        play_tip=play_tip,
        combo_refs=[],
        play_tip_refs=["Leader专项配置模型", "近期赛事Top Deck", "赛事共现统计"],
        confidence="medium" if not insufficient else "low",
        insufficient_rules=insufficient,
        insufficient_reasons=reasons,
        leader_deck_plans=leader_deck_plans,
    )


def build_candidate_cards_context(card_id: str, max_cards: int = 10) -> tuple[list[str], str]:
    allowed_ids: list[str] = [normalize_card_id(card_id)]
    candidate_lines: list[str] = []
    preferred_lines: list[str] = []
    fallback_lines: list[str] = []
    base = cards_by_id.get(normalize_card_id(card_id), {})
    base_colors = {str(x).strip().lower() for x in (base.get("colors") or []) if str(x).strip()}
    base_prefix = get_series_prefix(card_id)

    for item in get_cooccurrence_items(card_id):
        cid = normalize_card_id(str(item.get("card_id") or ""))
        if not cid or cid in allowed_ids:
            continue
        if is_leader_card(cid):
            continue
        card_basic = cards_by_id.get(cid)
        if not card_basic:
            continue
        detail = build_card_response(cid, card_basic)
        short_effect = (detail.effect or "无").replace("\n", " ")[:120]
        role = infer_card_role(cid)
        line = (
            f"- {cid} | {detail.name or '-'} | 角色={role} | 共现{item.get('cooccur')} | "
            f"效果摘要: {short_effect}"
        )
        cid_prefix = get_series_prefix(cid)
        cid_colors = {str(x).strip().lower() for x in (detail.colors or []) if str(x).strip()}
        if (base_colors and base_colors.intersection(cid_colors)) or cid_prefix == base_prefix:
            preferred_lines.append(line)
        else:
            fallback_lines.append(line)

    merged_lines = preferred_lines + fallback_lines
    selected_lines = merged_lines[:max_cards]
    for line in selected_lines:
        m = re.search(r"^- ([A-Z0-9_-]+) \|", line)
        if m:
            cid = normalize_card_id(m.group(1))
            if cid not in allowed_ids:
                allowed_ids.append(cid)
    candidate_lines = selected_lines

    return allowed_ids, "\n".join(candidate_lines)


def get_series_meta_hint(card_id: str, colors: list[str]) -> str:
    hints: list[str] = []
    series_related = get_relevant_top_decks(card_id, colors, max_items=8)
    for item in series_related:
        arche = str(item.get("archetype") or "").strip()
        rank = item.get("rank")
        share = item.get("share_percent")
        sample_count = int(item.get("sample_count") or 0)
        if arche:
            sample_text = f" | sample={sample_count}" if sample_count > 0 else ""
            hints.append(f"#{rank} {arche} ({share}%){sample_text}")

    tournaments = limitless_recent_tournaments[:8]
    tournament_lines = []
    for t in tournaments:
        name = str(t.get("name") or "").strip()
        fmt = str(t.get("region_format") or "").strip()
        players = t.get("players")
        if name:
            tournament_lines.append(f"{name} | {fmt} | {players} players")

    parts: list[str] = []
    if hints:
        parts.append("同环境相关 Top Decks: " + "；".join(hints))
    if tournament_lines:
        parts.append("近期赛事样本: " + "；".join(tournament_lines))
    return "\n".join(parts)


def build_topk_deck_evidence(card_id: str, colors: list[str], max_items: int = 6) -> str:
    rows = get_relevant_top_decks(card_id, colors, max_items=max_items)
    if not rows:
        return ""
    out: list[str] = []
    for idx, d in enumerate(rows, start=1):
        arche = str(d.get("archetype") or "").strip()
        if not arche:
            continue
        out.append(
            f"{idx}. archetype={arche} | leader={str(d.get('leader_card') or '').strip()} | "
            f"rank={d.get('rank')} | share={d.get('share_percent')} | "
            f"sample={int(d.get('sample_count') or 0)} | tournaments={int(d.get('from_tournaments') or 0)}"
        )
    return "\n".join(out)


def build_meta_evidence(card_id: str, colors: list[str]) -> dict[str, Any]:
    prefix = get_series_prefix(card_id)
    series_related = get_relevant_top_decks(card_id, colors, max_items=12)

    cooccur_items = cooccurrence_map.get(normalize_card_id(card_id), [])[:12]
    count_stat = card_count_stats.get(normalize_card_id(card_id), {})
    tournaments = limitless_recent_tournaments[:12]
    core_priority_cards = get_core_priority_cards(card_id, max_cards=3)
    role_priority_cards = get_role_priority_cards(card_id, max_cards=6)
    protect_targets = [
        x for x in core_priority_cards if str(x.get("card_id") or "").strip()
    ][:2]
    evidence_score = 0
    evidence_reasons: list[str] = []
    if official_rules_context.strip():
        evidence_score += 40
    else:
        evidence_reasons.append("缺少官方规则文本")
    if cooccur_items:
        evidence_score += 30
    else:
        evidence_reasons.append("缺少该卡的共现数据")
    if count_stat:
        evidence_score += 20
    else:
        evidence_reasons.append("缺少该卡投入张数统计")
    if core_priority_cards:
        evidence_score += 10
    else:
        evidence_reasons.append("缺少核心保护目标")

    return {
        "series_prefix": prefix,
        "top_decks_considered": series_related[:12],
        "cooccurrence_cards": cooccur_items,
        "count_stat": count_stat,
        "recent_tournaments": tournaments,
        "core_priority_cards": core_priority_cards,
        "role_priority_cards": role_priority_cards,
        "protect_targets": protect_targets,
        "evidence_score": evidence_score,
        "evidence_reasons": evidence_reasons,
    }


def _extract_json_text(raw_content: str) -> str:
    content = raw_content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
        content = re.sub(r"\s*```$", "", content)
    return content.strip()


def build_ai_cache_key(
    card_id: str,
    card_name: str,
    card_effect: str | None,
    series_prefix: str,
    cooccur_hint: str,
    series_meta_hint: str,
) -> str:
    payload = {
        "prompt_version": AI_PROMPT_VERSION,
        "context_fingerprint": build_ai_context_fingerprint(),
        "card_id": card_id,
        "card_name": card_name,
        "card_effect": card_effect or "",
        "series_prefix": series_prefix,
        "cooccur_hint": cooccur_hint,
        "series_meta_hint": series_meta_hint,
        "rules_len": len(official_rules_context),
        "meta_len": len(tournament_meta_context),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_ai_advice_content(raw_content: str) -> AIAdvice:
    content = _extract_json_text(raw_content)

    # Path 1: strict JSON
    try:
        parsed = json.loads(content)
        combos_raw = parsed.get("combos", [])
        play_tip_raw = parsed.get("play_tip", "")
        combo_refs_raw = parsed.get("combo_refs", [])
        play_tip_refs_raw = parsed.get("play_tip_refs", [])
        refs_raw = parsed.get("rules_refs", [])
        confidence_raw = str(parsed.get("confidence", "medium")).lower()
        insufficient_rules_raw = bool(parsed.get("insufficient_rules", False))
        insufficient_reasons_raw = parsed.get("insufficient_reasons", [])
        leader_deck_plans_raw = parsed.get("leader_deck_plans", [])
        combos = [str(x).strip() for x in combos_raw if str(x).strip()]
        play_tip = str(play_tip_raw).strip()
        rules_refs = [str(x).strip() for x in refs_raw if str(x).strip()]
        combo_refs: list[list[str]] = []
        for item in combo_refs_raw:
            if isinstance(item, list):
                refs = [str(x).strip() for x in item if str(x).strip()]
                combo_refs.append(refs)
            else:
                combo_refs.append([])
        play_tip_refs = [str(x).strip() for x in play_tip_refs_raw if str(x).strip()]
        insufficient_reasons = [
            str(x).strip() for x in insufficient_reasons_raw if str(x).strip()
        ]
        leader_deck_plans = (
            leader_deck_plans_raw if isinstance(leader_deck_plans_raw, list) else []
        )

        # Backward compatibility: if new fields missing, fallback to shared refs.
        if not combo_refs and rules_refs:
            combo_refs = [rules_refs[:], rules_refs[:]]
        if not play_tip_refs and rules_refs:
            play_tip_refs = rules_refs[:]

        while len(combo_refs) < len(combos):
            combo_refs.append([])
        combo_refs = combo_refs[: len(combos)]
        confidence = (
            confidence_raw if confidence_raw in {"high", "medium", "low"} else "medium"
        )
        if combos or play_tip:
            return AIAdvice(
                combos=combos,
                play_tip=play_tip,
                combo_refs=combo_refs,
                play_tip_refs=play_tip_refs,
                rules_refs=rules_refs,
                confidence=confidence,
                insufficient_rules=insufficient_rules_raw,
                insufficient_reasons=insufficient_reasons,
                leader_deck_plans=leader_deck_plans,
            )
    except json.JSONDecodeError:
        pass

    # Path 2: loose text fallback (line-based extraction)
    lines = [ln.strip(" -•\t") for ln in content.splitlines() if ln.strip()]
    combos: list[str] = []
    play_tip = ""
    for ln in lines:
        low = ln.lower()
        if ("combo" in low or "配合" in ln) and len(combos) < 2:
            combos.append(ln)
            continue
        if ("建议" in ln or "打法" in ln or "tip" in low) and not play_tip:
            play_tip = ln

    if len(combos) < 2:
        for ln in lines:
            if ln not in combos:
                combos.append(ln)
            if len(combos) >= 2:
                break

    if not play_tip and len(lines) >= 3:
        play_tip = lines[-1]

    combos = [x for x in combos if x]
    if not combos and not play_tip:
        raise RuntimeError("AI 返回格式无法解析出 Combo 或建议。")

    return AIAdvice(
        combos=combos,
        play_tip=play_tip,
        combo_refs=[[] for _ in combos],
        play_tip_refs=[],
        insufficient_reasons=[],
    )


def ask_ai_for_combo(
    card_id: str,
    card_name: str,
    card_effect: str | None,
    colors: list[str] | None = None,
    card_type: str | None = None,
    cost: Any = None,
    power: Any = None,
    strict_mode: bool = True,
) -> AIAdvice:
    if not official_rules_context.strip():
        raise RuntimeError("official_rules 尚未加载，请检查规则文件。")
    if is_leader_card(card_id):
        return build_leader_deck_advice(card_id, card_name, colors)

    api_key = get_api_key()
    effect_text = (card_effect or "该卡未提供效果文本").strip()
    series_prefix = get_series_prefix(card_id)
    tournament_context_block = (
        f"\n\n以下是近期赛事与主流卡组环境数据（Meta Context）：\n{tournament_meta_context}\n"
        if tournament_meta_context
        else ""
    )
    cooccur_hint = get_cooccurrence_hint(card_id)
    cooccur_context_block = (
        f"\n\n以下是该卡在近期赛事页面中的高频共现卡（卡号(共现次数)）：\n{cooccur_hint}\n"
        if cooccur_hint
        else ""
    )
    series_meta_hint = get_series_meta_hint(card_id, colors or [])
    series_meta_context_block = (
        f"\n\n以下是按当前卡动态筛选的环境证据：\n{series_meta_hint}\n"
        if series_meta_hint
        else ""
    )
    topk_deck_evidence = build_topk_deck_evidence(card_id, colors or [], max_items=6)
    topk_deck_block = (
        f"\n\n以下是为当前卡检索到的 Top-K 相关比赛卡组证据（优先参考）：\n{topk_deck_evidence}\n"
        if topk_deck_evidence
        else ""
    )

    cache_key = build_ai_cache_key(
        card_id,
        card_name,
        card_effect,
        series_prefix,
        cooccur_hint,
        series_meta_hint,
    )
    cached = ai_advice_cache.get(cache_key)
    if cached is not None:
        return cached

    allowed_card_ids, candidate_cards_context = build_candidate_cards_context(card_id)
    core_priority_cards = get_core_priority_cards(card_id, max_cards=3)
    role_priority_cards = get_role_priority_cards(card_id, max_cards=6)
    evidence_reasons: list[str] = []
    if not cooccur_hint:
        evidence_reasons.append("缺少该卡高频共现证据")
    if not card_count_stats.get(normalize_card_id(card_id), {}):
        evidence_reasons.append("缺少该卡投入张数统计")
    if not core_priority_cards:
        evidence_reasons.append("缺少稳定核心保护目标")
    core_priority_text = "；".join(
        [
            f"{x['card_id']}({x['name'] or '-'}|共现{x['cooccur']}|常见{x['most_common_count']}张)"
            for x in core_priority_cards
        ]
    )
    candidate_cards_block = (
        f"\n\n以下是允许优先使用的候选卡清单（来自近期赛事高频共现，名称与效果已校验）：\n{candidate_cards_context}\n"
        if candidate_cards_context
        else ""
    )
    core_priority_block = (
        f"\n\n以下是当前卡组环境中的核心优先位（高优先保护/保留）：\n{core_priority_text}\n"
        if core_priority_text
        else ""
    )
    role_priority_text = "；".join(
        [
            f"{x['card_id']}({x['name'] or '-'}|{x['role']}|共现{x['cooccur']})"
            for x in role_priority_cards
        ]
    )
    role_priority_block = (
        f"\n\n以下是候选卡分工标签（用于资源分配优先级）：\n{role_priority_text}\n"
        if role_priority_text
        else ""
    )
    count_stat = card_count_stats.get(normalize_card_id(card_id), {})
    count_stat_block = (
        f"\n\n以下是该卡在赛事页面中抓到的投入张数统计：\n{json.dumps(count_stat, ensure_ascii=False)}\n"
        if count_stat
        else ""
    )
    # If meta evidence is empty, avoid letting model improvise factual strategic claims.
    if len(allowed_card_ids) <= 1 and not cooccur_hint and not count_stat:
        fallback = build_fallback_advice(
            card_id,
            card_name,
            "",
            colors=colors,
            card_type=card_type,
            cost=cost,
            power=power,
        )
        fallback.play_tip = (
            "当前赛事样本中未抓到该卡的有效共现/张数数据，已切换为保守建议。"
            "建议先完成一次 `sync_limitless.py` 数据同步后再查看 AI 组合。"
        )
        fallback.play_tip_refs = ["数据不足保护策略"]
        fallback.confidence = "low"
        fallback.insufficient_rules = True
        fallback.insufficient_reasons = ["缺少该卡共现与张数证据"]
        ai_advice_cache[cache_key] = fallback
        persist_ai_advice_cache_to_disk()
        return fallback

    evidence = build_meta_evidence(card_id, colors or [])
    if int(evidence.get("evidence_score") or 0) < 45:
        fallback = build_fallback_advice(
            card_id,
            card_name,
            "当前赛事证据不足，建议先按高频共现卡做实测，等待更多近期比赛样本后再刷新建议。",
            colors=colors,
            card_type=card_type,
            cost=cost,
            power=power,
        )
        fallback.confidence = "low"
        fallback.insufficient_rules = True
        fallback.insufficient_reasons = list(evidence.get("evidence_reasons") or [])
        ai_advice_cache[cache_key] = fallback
        persist_ai_advice_cache_to_disk()
        return fallback

    card_fact_block = (
        "以下卡牌事实为本地数据库权威信息，不得篡改：\n"
        f"- card_id: {card_id}\n"
        f"- name: {card_name}\n"
        f"- colors: {colors or []}\n"
        f"- type: {card_type or '-'}\n"
        f"- cost: {cost if cost is not None else '-'}\n"
        f"- power: {power if power is not None else '-'}\n"
    )

    user_prompt = (
        "以下是官方规则背景知识（Context），你必须严格遵循，不得违反或忽略：\n"
        f"{official_rules_context}\n\n"
        f"{card_fact_block}\n"
        f"{tournament_context_block}"
        f"{cooccur_context_block}"
        f"{series_meta_context_block}"
        f"{topk_deck_block}"
        f"{candidate_cards_block}"
        f"{core_priority_block}"
        f"{role_priority_block}"
        f"{count_stat_block}"
        f"卡牌编号：{card_id}\n"
        f"卡牌名称：{card_name}\n"
        f"卡牌效果：{effect_text}\n"
        "请在上述官方规则范围内给出尽可能有价值的 Combo（可以为 0 条、1 条、2 条或更多）和实战建议。"
        f"当前卡系列为 {series_prefix}。除非完全无法给出建议，否则禁止使用其他 OP 系列卡号。"
        "优先使用上面“动态筛选的环境证据”与“高频共现卡”中的信息来做推荐。"
        f"除当前卡外，优先只使用这份候选卡清单中的卡号：{', '.join(allowed_card_ids)}。"
        "如果候选卡不足以组成 combo，可返回更少的 combo，不要编造冷门卡。"
        "仅可基于本次提供的官方规则与赛事证据输出建议，不允许凭空假设环境结论。"
        f"严格模式={strict_mode}。若为 true，每条 combo 必须包含至少一个明确卡号。"
        "硬规则：Leader/领袖卡不属于主卡组投入，不得建议“2-4张/满编领袖”，也不要把领袖当普通角色联动位。"
        "若给出防守与资源分配建议，应优先保护上面“核心优先位”中的卡，而不是次要过牌件。"
        "资源分配需遵循角色优先级：终结点 > 解场件 > 防守件 > 过牌件 > 联动件。"
        "若张数统计显示 most_common_count=4 且比例较高，请优先建议满编或接近满编。"
        "每条 combo 尽量包含涉及的卡号，便于验证。"
        "禁止编造规则；如果信息不足，请设置 insufficient_rules=true 并说明限制。"
        "实战建议只写“操作思路与对局取舍”，不要重复卡号/颜色/费用/战力等基础资料。"
        "请分别给出每条 Combo 的引用，写入 combo_refs；实战建议引用写入 play_tip_refs。"
    )

    if not _ensure_openai() or OpenAI is None:
        raise RuntimeError("OpenAI SDK unavailable")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    completion = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": AI_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=AI_TEMPERATURE,
    )

    content = completion.choices[0].message.content if completion.choices else ""
    if not content:
        raise RuntimeError("AI 未返回有效内容。")
    raw_advice = _parse_ai_advice_content(content)
    invalid_notes = collect_combo_violations(raw_advice, allowed_card_ids, strict_mode)
    if invalid_notes:
        repair_prompt = (
            "你上一版输出包含不合规 combo，请只返回修正后的 JSON。\n"
            f"不合规原因：{'；'.join(invalid_notes)}\n"
            f"可用卡号白名单：{', '.join(allowed_card_ids)}\n"
            "要求：每条 combo 必须包含白名单中的明确卡号；如果做不到，可减少条数但不要编造。\n"
            "另外，play_tip 不要重复基础卡牌资料，只保留实战操作建议。"
        )
        repair = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": AI_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": content},
                {"role": "user", "content": repair_prompt},
            ],
            temperature=0.0,
        )
        repaired_content = (
            repair.choices[0].message.content if repair.choices else ""
        )
        if repaired_content:
            repaired = _parse_ai_advice_content(repaired_content)
            second_invalid_notes = collect_combo_violations(
                repaired, allowed_card_ids, strict_mode
            )
            if not second_invalid_notes and (repaired.combos or repaired.play_tip):
                raw_advice = repaired

    advice = enforce_allowed_cards(
        raw_advice,
        allowed_card_ids,
        strict_require_card_id=strict_mode,
    )

    advice = apply_count_stat_guardrail(advice, card_id)
    advice = enforce_rule_safe_tip(
        advice,
        card_id,
        card_name,
        allowed_card_ids,
        core_priority_cards,
        role_priority_cards,
    )
    if not advice.combos:
        advice = build_fallback_advice(
            card_id,
            card_name,
            advice.play_tip,
            colors=colors,
            card_type=card_type,
            cost=cost,
            power=power,
        )
        advice = enforce_rule_safe_tip(
            advice,
            card_id,
            card_name,
            allowed_card_ids,
            core_priority_cards,
            role_priority_cards,
        )
    if advice.insufficient_rules:
        advice.insufficient_reasons = evidence_reasons[:] or ["证据覆盖不足"]
        advice.play_tip_refs = list(dict.fromkeys((advice.play_tip_refs or []) + ["证据评分模型"]))
    ai_advice_cache[cache_key] = advice
    persist_ai_advice_cache_to_disk()
    return advice


def collect_combo_violations(
    advice: AIAdvice, allowed_ids: list[str], strict_mode: bool
) -> list[str]:
    violations: list[str] = []
    allowed_upper = {normalize_card_id(x) for x in allowed_ids if x}
    id_pattern = re.compile(r"\b([A-Z]{2,3}\d{2}-\d{3}(?:_[A-Z0-9]+)?)\b", re.IGNORECASE)
    for combo in advice.combos:
        ids = [normalize_card_id(x) for x in id_pattern.findall(combo)]
        if strict_mode and not ids:
            violations.append("存在未包含卡号的 combo")
            continue
        outside = [cid for cid in ids if cid not in allowed_upper]
        if outside:
            violations.append(f"存在白名单外卡号: {', '.join(outside)}")
    return violations


def get_series_prefix(card_id: str) -> str:
    normalized = normalize_card_id(card_id)
    if "-" in normalized:
        return normalized.split("-", 1)[0]
    return normalized


def enforce_same_series(advice: AIAdvice, card_id: str) -> AIAdvice:
    prefix = get_series_prefix(card_id)
    if not prefix.startswith("OP"):
        return advice

    kept_combos: list[str] = []
    kept_refs: list[list[str]] = []
    for idx, combo in enumerate(advice.combos):
        series_mentions = re.findall(r"\b([A-Z]{2}\d{2})-\d{3}\b", combo.upper())
        has_other_op_series = any(s.startswith("OP") and s != prefix for s in series_mentions)
        if has_other_op_series:
            continue
        kept_combos.append(combo)
        kept_refs.append(advice.combo_refs[idx] if idx < len(advice.combo_refs) else [])

    advice.combos = kept_combos
    advice.combo_refs = kept_refs
    if not advice.combos:
        advice.insufficient_rules = True
    return advice


def enforce_allowed_cards(
    advice: AIAdvice, allowed_ids: list[str], strict_require_card_id: bool = False
) -> AIAdvice:
    allowed_upper = {normalize_card_id(x) for x in allowed_ids if x}
    if not allowed_upper:
        return advice

    kept_combos: list[str] = []
    kept_refs: list[list[str]] = []
    id_pattern = re.compile(r"\b([A-Z]{2,3}\d{2}-\d{3}(?:_[A-Z0-9]+)?)\b", re.IGNORECASE)
    for idx, combo in enumerate(advice.combos):
        ids = [normalize_card_id(x) for x in id_pattern.findall(combo)]
        if strict_require_card_id and not ids:
            continue
        # Leader cards should not be suggested as normal deck slots.
        if any(is_leader_card(cid) for cid in ids):
            continue
        # Non-strict mode: allow combos without explicit IDs.
        if ids and any(cid not in allowed_upper for cid in ids):
            continue
        kept_combos.append(combo)
        kept_refs.append(advice.combo_refs[idx] if idx < len(advice.combo_refs) else [])

    advice.combos = kept_combos
    advice.combo_refs = kept_refs
    if not advice.combos and not advice.play_tip:
        advice.insufficient_rules = True
    return advice


def apply_count_stat_guardrail(advice: AIAdvice, card_id: str) -> AIAdvice:
    if is_leader_card(card_id):
        return advice
    stat = card_count_stats.get(normalize_card_id(card_id), {})
    if not stat:
        return advice
    dominant = int(stat.get("most_common_count") or 0)
    ratio = float(stat.get("most_common_ratio") or 0.0)
    if dominant >= 4 and ratio >= 0.45:
        tip = advice.play_tip or ""
        if "1-2张" in tip or "1～2张" in tip or "1~2张" in tip:
            tip = tip.replace("1-2张", "3-4张").replace("1～2张", "3-4张").replace("1~2张", "3-4张")
        if "4张" not in tip:
            append = f"（基于赛事抓取样本，常见投入为{dominant}张，建议优先考虑接近满编。）"
            tip = (tip + append).strip() if tip else append
        advice.play_tip = tip
    return advice


def cleanup_play_tip_text(play_tip: str) -> str:
    tip = (play_tip or "").strip()
    if not tip:
        return tip
    # Remove verbose "卡牌事实：" prefix block if model echoes it.
    tip = re.sub(r"^卡牌事实：[^。]*。\s*", "", tip)
    # Remove common key-value dump patterns.
    tip = re.sub(r"(?:颜色|类型|费用|战力)\s*[=:]\s*[^；。,\n]+[；。]?\s*", "", tip)
    # Remove statements that suggest adding multiple Leader copies into deck.
    tip = re.sub(r"(领袖|Leader)[^。]*?(满编|[2-4]\s*张|3-4张|4张)[^。]*。?", "", tip, flags=re.IGNORECASE)
    return tip.strip()


def build_safe_play_tip(
    card_id: str,
    card_name: str,
    allowed_ids: list[str],
    core_priority_cards: list[dict[str, Any]] | None = None,
    role_priority_cards: list[dict[str, Any]] | None = None,
) -> str:
    related = [x for x in allowed_ids if normalize_card_id(x) != normalize_card_id(card_id)][:2]
    related_text = "、".join(related) if related else "高频共现卡"
    core_text = ""
    if core_priority_cards:
        top = core_priority_cards[0]
        core_text = f"优先保护 {top.get('card_id')}（{top.get('name') or '-'}）这类核心终结点。"
    role_text = ""
    if role_priority_cards:
        role_map: dict[str, str] = {}
        for item in role_priority_cards:
            role = str(item.get("role") or "")
            cid = str(item.get("card_id") or "")
            if role and cid and role not in role_map:
                role_map[role] = cid
        if role_map:
            chunks = [f"{k}:{v}" for k, v in role_map.items()]
            role_text = "分工优先级（终结点>解场件>防守件>过牌件>联动件）： " + "，".join(chunks) + "。"
    return (
        f"开局：优先用 {card_id}（{card_name}）做检索/过牌，先稳定资源与手牌质量。"
        f"中期：围绕 {related_text} 组织两卡联动，先保证出牌曲线与防守节奏。"
        f"后期：以已建立的场面优势换牌差，避免高风险 all-in；{core_text or '若对局信息不足，优先选择稳健交换。'}"
        f"{role_text}"
    )


def enforce_rule_safe_tip(
    advice: AIAdvice,
    card_id: str,
    card_name: str,
    allowed_ids: list[str],
    core_priority_cards: list[dict[str, Any]] | None = None,
    role_priority_cards: list[dict[str, Any]] | None = None,
) -> AIAdvice:
    tip = cleanup_play_tip_text(advice.play_tip)
    low_conf = (advice.confidence or "").lower() == "low"
    if advice.insufficient_rules or low_conf or not tip:
        advice.play_tip = build_safe_play_tip(
            card_id, card_name, allowed_ids, core_priority_cards, role_priority_cards
        )
        advice.play_tip_refs = ["规则安全模板", "赛事共现统计"]
        if advice.confidence not in {"high", "medium"}:
            advice.confidence = "medium"
    else:
        if core_priority_cards:
            top = core_priority_cards[0]
            top_id = str(top.get("card_id") or "").strip()
            top_name = str(top.get("name") or "").strip()
            if top_id and top_id not in tip:
                tip = (
                    f"{tip} 中后期资源交换时，优先保留并保护 {top_id}"
                    f"{f'（{top_name}）' if top_name else ''} 这类核心输出位。"
                ).strip()
        advice.play_tip = tip
    return advice


def build_fallback_advice(
    card_id: str,
    card_name: str,
    current_tip: str,
    colors: list[str] | None = None,
    card_type: str | None = None,
    cost: Any = None,
    power: Any = None,
) -> AIAdvice:
    related = get_cooccurrence_items(card_id, min_cooccur=1)[:3]
    combos: list[str] = []
    refs: list[list[str]] = []
    for item in related:
        cid = normalize_card_id(str(item.get("card_id") or ""))
        if not cid:
            continue
        if is_leader_card(cid):
            continue
        basic = cards_by_id.get(cid)
        if not basic:
            continue
        detail = build_card_response(cid, basic)
        pair_stat = card_count_stats.get(cid, {})
        copies = pair_stat.get("most_common_count")
        copies_hint = f"，常见投入约 {copies} 张" if copies else ""
        combos.append(
            f"可优先测试 {normalize_card_id(card_id)} + {cid}（{detail.name or '-'}）的联动，"
            f"该搭配在赛事页面中共现次数为 {item.get('cooccur')}{copies_hint}。"
        )
        refs.append(["赛事共现统计"])
    tip = current_tip or "当前严格筛选下可执行 combo 较少，建议先按高频共现卡做小样本对局验证。"
    advice = AIAdvice(
        combos=combos,
        play_tip=tip,
        combo_refs=refs if refs else [[] for _ in combos],
        play_tip_refs=["赛事共现统计"],
        confidence="medium",
        insufficient_rules=True if not combos else False,
    )
    advice.play_tip = cleanup_play_tip_text(advice.play_tip)
    return advice


def normalize_official_image_url(url: str | None) -> str | None:
    text = str(url or "").strip()
    if not text:
        return None
    # Historical bad path from asia-tc cardlist HTML: /cardlist/images/cardlist/card/X.png (404).
    text = text.replace("/cardlist/images/cardlist/", "/images/cardlist/")
    if text.startswith("http://") or text.startswith("https://"):
        m = re.search(r"/images/cardlist/card/([^/?#]+)", text, flags=re.IGNORECASE)
        if m:
            stem = m.group(1)
            lower = text.lower()
            if "asia-tc.onepiece-cardgame.com" in lower:
                return f"https://asia-tc.onepiece-cardgame.com/images/cardlist/card/{stem}"
            if "asia-en.onepiece-cardgame.com" in lower:
                return f"https://asia-en.onepiece-cardgame.com/images/cardlist/card/{stem}"
            if "en.onepiece-cardgame.com" in lower:
                return f"https://en.onepiece-cardgame.com/images/cardlist/card/{stem}"
            return f"https://www.onepiece-cardgame.com/images/cardlist/card/{stem}"
        return text
    normalized = text.replace("../", "").replace("./", "")
    if normalized.startswith("/images/"):
        normalized = normalized.lstrip("/")
    if normalized.startswith("images/"):
        return OFFICIAL_IMAGE_HOSTS[0] + normalized
    return text


def _is_english_card_image_url(url: str) -> bool:
    text = str(url or "").lower()
    if not text:
        return False
    if "limitlesstcg" in text and ("_en." in text or "/en/" in text or "_en_" in text):
        return True
    if "en.onepiece-cardgame.com" in text:
        return True
    if "asia-en.onepiece-cardgame.com" in text:
        return True
    return False


def _build_official_image_candidates(img_full_url: str | None, img_url: str | None) -> list[str]:
    candidates: list[str] = []
    full = (img_full_url or "").strip()
    relative = (img_url or "").strip()

    stems: list[str] = []
    if relative:
        normalized = relative.lstrip("./")
        if "images/cardlist/card/" in normalized.replace("\\", "/"):
            fname = normalized.replace("\\", "/").split("images/cardlist/card/", 1)[-1]
            fname = fname.split("?", 1)[0]
            if fname:
                stems.append(fname)
        elif normalized.startswith("images/"):
            for host in OFFICIAL_IMAGE_HOSTS:
                absolute = host + normalized
                candidates.append(absolute)
                if "?" in absolute:
                    candidates.append(absolute.split("?", 1)[0])

    # Prefer asia-tc (繁中) for Chinese HK; JP next; EN/Limitless last.
    mirror_hosts = (
        "https://asia-tc.onepiece-cardgame.com/",
        "https://www.onepiece-cardgame.com/",
        "https://asia-en.onepiece-cardgame.com/",
        "https://en.onepiece-cardgame.com/",
    )

    if full:
        m = re.search(r"/images/cardlist/card/([^/?#]+)", full, flags=re.IGNORECASE)
        if m:
            stems.append(m.group(1))
        # Also try to recover stem from Limitless-style names: OP17-001_EN.webp
        m2 = re.search(r"(OP\d{2}-\d{3}(?:[_-][A-Za-z0-9]+)?)", full, flags=re.IGNORECASE)
        if m2:
            stem = m2.group(1).replace("_", "-").upper()
            stem = re.sub(r"-EN$", "", stem)
            stems.append(f"{stem}.png" if "." not in stem else stem)

    for stem in dict.fromkeys(stems):
        stem_name = stem if "." in stem else f"{stem}.png"
        for host in mirror_hosts:
            candidates.append(f"{host}images/cardlist/card/{stem_name}")

    # Append original index URLs after JP mirrors (skip obvious EN sources until end).
    deferred_en: list[str] = []
    for raw in (full, relative):
        raw = str(raw or "").strip()
        if not raw:
            continue
        if _is_english_card_image_url(raw):
            deferred_en.append(raw)
            if "?" in raw:
                deferred_en.append(raw.split("?", 1)[0])
        else:
            candidates.append(raw)
            if "?" in raw:
                candidates.append(raw.split("?", 1)[0])
    candidates.extend(deferred_en)

    seen: set[str] = set()
    deduped: list[str] = []
    for url in candidates:
        fixed = normalize_official_image_url(url) or url
        # Keep both normalized JP form and regional absolute URLs.
        for item in (fixed, url):
            item = str(item or "").strip()
            if not item or item in seen:
                continue
            seen.add(item)
            deduped.append(item)
    return deduped


def _guess_image_extension(url: str) -> str:
    clean = url.split("?", 1)[0].lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        if clean.endswith(ext):
            return ext
    return ".png"


def _base_card_id(card_id: str) -> str:
    normalized = normalize_card_id(card_id)
    # DON illustrated cards: DON17-10163 — full 3–5 digit id is the base (no -P1 siblings).
    m_don = re.match(r"^(DON[A-Z0-9]*-\d{3,5})", normalized)
    if m_don:
        return m_don.group(1)
    m = re.match(r"^([A-Z]{2,3}\d{2}-\d{3})", normalized)
    return m.group(1) if m else normalized


def _fast_thumbnail_url(normalized_id: str, _seen: set[str] | None = None) -> str:
    """Lightweight thumbnail URL without building full CardResponse (Streamlit sidebar batch)."""
    nid = normalize_card_id(normalized_id)
    if not nid:
        return ""
    if _seen is None:
        _seen = set()
    if nid in _seen or len(_seen) > 8:
        return ""
    _seen.add(nid)
    lu = local_image_url_map.get(nid)
    if lu:
        return lu
    if cards_by_id.get(nid):
        return card_image_proxy_url(nid) or ""
    bid = _base_card_id(nid)
    if bid and bid != nid:
        return _fast_thumbnail_url(bid, _seen)
    return ""


def collect_variant_image_urls(card_id: str) -> list[str]:
    base_id = _base_card_id(card_id)
    target_id = normalize_card_id(card_id)
    # DON cards are standalone listings (yuyutei slugs); do not treat DON17-* siblings as variants.
    if target_id.startswith("DON") or base_id.startswith("DON"):
        return []
    urls: list[str] = []
    # Local synced images first (only variant arts).
    for file_path in sorted(PACKS_DIR.glob(f"{base_id}*.*")):
        stem = normalize_card_id(file_path.stem)
        if stem in {base_id, target_id}:
            continue
        if not stem.startswith(base_id):
            continue
        # Ignore accidental duplicate filenames that don't map to known card ids.
        if stem not in cards_by_id:
            continue
        urls.append(pack_image_public_url(file_path.name))
    # 无本地 packs 时：清单 + local_image_url_map 中的异画（R2 URL）
    for mapped_id, mapped_url in local_image_url_map.items():
        if mapped_id in {base_id, target_id}:
            continue
        if not str(mapped_id).startswith(base_id):
            continue
        if mapped_id not in cards_by_id:
            continue
        urls.append(mapped_url)
    # Fallback to indexed URLs for variant ids (precomputed map for speed).
    for normalized in variant_id_map.get(base_id, []):
        if normalized in {base_id, target_id}:
            continue
        basic = cards_by_id.get(normalized, {})
        img_full = str((basic or {}).get("img_full_url") or "").strip()
        img_rel = str((basic or {}).get("img_url") or "").strip()
        if img_full:
            urls.append(img_full)
            if "?" in img_full:
                urls.append(img_full.split("?", 1)[0])
        if img_rel:
            normalized_rel = img_rel.lstrip("./")
            if normalized_rel.startswith("images/"):
                for host in OFFICIAL_IMAGE_HOSTS:
                    abs_url = host + normalized_rel
                    urls.append(abs_url)
                    if "?" in abs_url:
                        urls.append(abs_url.split("?", 1)[0])
    seen: set[str] = set()
    deduped: list[str] = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped[:12]


def _download_card_image_to_packs(card_key: str, img_full_url: str | None, img_url: str | None) -> Path | None:
    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    existing = [p for p in PACKS_DIR.glob(f"{card_key}.*") if p.is_file()]
    if existing:
        return existing[0]

    candidates = _build_official_image_candidates(img_full_url, img_url)
    for candidate in candidates[:6]:
        try:
            resp = requests.get(
                candidate,
                timeout=IMAGE_FETCH_TIMEOUT_SEC,
                headers={
                    "User-Agent": "Mozilla/5.0 OPCG-API/1.0",
                    "Referer": OFFICIAL_IMAGE_HOSTS[0],
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                },
            )
        except requests.RequestException:
            continue

        content_type = resp.headers.get("content-type", "").lower()
        if resp.status_code != 200 or "image" not in content_type:
            continue

        extension = _guess_image_extension(candidate)
        target = PACKS_DIR / f"{card_key}{extension}"
        try:
            target.write_bytes(resp.content)
            local_image_url_map[card_key] = pack_image_public_url(target.name)
            local_image_path_map[card_key] = target
            return target
        except OSError:
            continue
    return None


def ensure_local_card_image(card_id: str, img_full_url: str | None, img_url: str | None) -> str | None:
    card_key = normalize_card_id(card_id)
    if not card_key:
        return None

    PACKS_DIR.mkdir(parents=True, exist_ok=True)

    existing = list(PACKS_DIR.glob(f"{card_key}.*"))
    if existing:
        return pack_image_public_url(existing[0].name)

    indexed = local_image_url_map.get(card_key)
    if indexed:
        return indexed

    # Keep API responses fast by default; bulk sync should be done by sync_card_images.py.
    if not IMAGE_LAZY_FETCH_ENABLED:
        return card_image_proxy_url(card_key)

    path = _download_card_image_to_packs(
        card_key,
        normalize_official_image_url(img_full_url),
        img_url,
    )
    if path:
        return pack_image_public_url(path.name)
    return card_image_proxy_url(card_key)


def resolve_card_sets(card_id: str, card_basic: dict[str, Any], snapshot_card: dict[str, Any]) -> list[str]:
    """Only return scraped official getInfo — never invent from pack/series."""
    norm = normalize_card_id(card_id)
    snap_sets = [str(x).strip() for x in (snapshot_card.get("card_sets") or []) if str(x).strip()]
    if snap_sets:
        return snap_sets
    # Present in official TC snapshot but no getInfo → unknown (do not use index guesses).
    if norm and norm in official_snapshot_map:
        return []
    sets = [str(x).strip() for x in (card_basic.get("card_sets") or []) if str(x).strip()]
    if not sets:
        return []
    # Index-only (JP limited/promo scrape, DON, …). Drop booster-template clones of the base.
    base = _base_card_id(norm)
    if norm != base and re.search(r"-P\d+$", norm, re.I):
        base_sets = [
            str(x).strip()
            for x in ((cards_by_id.get(base) or {}).get("card_sets") or [])
            if str(x).strip()
        ]
        if sets == base_sets:
            return []
        if all(re.search(r"補充包|【OP-\d+|【ST-\d+|【EB-\d+|【PRB-", s) for s in sets):
            return []
    return sets


def collect_variant_card_sets(card_id: str) -> dict[str, list[str]]:
    """Map base + parallel ids → per-illustration official sources."""
    norm = normalize_card_id(card_id)
    if not norm:
        return {}
    if norm.startswith("DON"):
        sets = resolve_card_sets(norm, cards_by_id.get(norm) or {}, _snapshot_to_card_fields(norm))
        return {norm: sets} if sets else {}
    base = _base_card_id(norm)
    ids = [base, *list(variant_id_map.get(base) or [])]
    if norm not in ids:
        ids.append(norm)
    out: dict[str, list[str]] = {}
    for vid in ids:
        basic = cards_by_id.get(vid) or {}
        if not basic and vid != norm:
            continue
        sets = resolve_card_sets(vid, basic, _snapshot_to_card_fields(vid))
        if sets:
            out[vid] = sets
    return out


def build_card_response(card_id: str, card_basic: dict[str, Any]) -> CardResponse:
    snapshot_card = _snapshot_to_card_fields(card_id)
    pack_id = card_basic.get("pack_id")
    full_card: dict[str, Any] = {}
    effect = None
    power = None

    if pack_id:
        pack_data = load_pack_data(str(pack_id))
        if pack_data is not None:
            full_card = extract_card_from_pack(pack_data, card_id) or {}
            effect, power = extract_extra_from_pack(pack_data, card_id)

    img_url = card_basic.get("img_url") or full_card.get("img_url") or snapshot_card.get("img_url")
    img_full_url = (
        card_basic.get("img_full_url")
        or full_card.get("img_full_url")
        or snapshot_card.get("img_full_url")
    )
    img_local_url = ensure_local_card_image(card_id, img_full_url, img_url)
    alt_image_urls = collect_variant_image_urls(card_id)
    raw_effect = effect or full_card.get("effect") or card_basic.get("effect") or snapshot_card.get("effect")
    effect_text = normalize_effect_text(raw_effect)
    trigger_text = normalize_effect_text(
        full_card.get("trigger") or card_basic.get("trigger") or snapshot_card.get("trigger")
    )
    trigger_en_text = normalize_effect_text(card_basic.get("trigger_en"))
    effect_en_text = normalize_effect_text(card_basic.get("effect_en"))
    if trigger_text:
        effect_text = _compose_effect_with_trigger(effect_text, trigger_text)
    if trigger_en_text:
        effect_en_text = _compose_effect_with_trigger(effect_en_text, trigger_en_text)

    traits = (
        full_card.get("types")
        or card_basic.get("types")
        or snapshot_card.get("types")
        or card_basic.get("traits")
        or []
    )
    if not traits:
        traits = full_card.get("attributes") or card_basic.get("attributes") or []
    traits = [str(x).strip() for x in traits if str(x).strip()]
    traits_en = (
        [str(x).strip() for x in (card_basic.get("traits_en") or []) if str(x).strip()]
        or []
    )
    card_type = full_card.get("category") or card_basic.get("category") or snapshot_card.get("category")
    card_type_en = (
        card_basic.get("card_type_en")
        or card_basic.get("category_en")
        or None
    )
    resolved_power = power if power is not None else full_card.get("power")
    if resolved_power is None:
        if card_basic.get("power") is not None:
            resolved_power = card_basic.get("power")
        elif snapshot_card.get("power") is not None:
            resolved_power = snapshot_card.get("power")
    if isinstance(resolved_power, str) and resolved_power.strip() in {"", "-", "—", "－"}:
        resolved_power = None
    type_hint = str(
        card_type
        or card_basic.get("card_type")
        or snapshot_card.get("card_type")
        or ""
    ).lower()
    if resolved_power is None and ("character" in type_hint or "角色" in type_hint):
        resolved_power = 0
    resolved_attributes = (
        [str(x).strip() for x in (full_card.get("attributes") or []) if str(x).strip()]
        or [str(x).strip() for x in (card_basic.get("attributes") or []) if str(x).strip()]
        or [str(x).strip() for x in (snapshot_card.get("attributes") or []) if str(x).strip()]
        or [str(x).strip() for x in str(card_basic.get("attribute") or "").split("/") if str(x).strip()]
    )
    if not resolved_attributes:
        resolved_attributes = cached_attribute_map.get(normalize_card_id(card_id), [])
    if not resolved_attributes:
        resolved_attributes = _infer_attributes_from_local_image(card_id, img_local_url, img_full_url)

    attributes_en = normalize_attributes(card_basic.get("attributes_en"))
    if not attributes_en:
        attributes_en = normalize_attributes(resolved_attributes)
    resolved_attributes = attributes_en or resolved_attributes

    colors_en = [
        str(x).strip() for x in (card_basic.get("colors_en") or []) if str(x).strip()
    ]

    return CardResponse(
        id=card_id,
        name=card_basic.get("name") or full_card.get("name") or snapshot_card.get("name"),
        name_en=card_basic.get("name_en"),
        rarity=normalize_rarity(
            card_basic.get("rarity") or full_card.get("rarity") or snapshot_card.get("rarity")
        )
        or None,
        colors=(card_basic.get("colors") or full_card.get("colors") or snapshot_card.get("colors") or []),
        colors_en=colors_en,
        pack_id=pack_id,
        img_local_url=img_local_url,
        img_url=img_url,
        img_full_url=img_full_url,
        alt_image_urls=alt_image_urls,
        cost=_zero_cost_if_event_or_stage(
            card_type,
            _first_int(full_card.get("cost"), card_basic.get("cost"), snapshot_card.get("cost")),
        ),
        effect=effect_text,
        effect_en=effect_en_text,
        trigger=trigger_text,
        trigger_en=trigger_en_text,
        power=resolved_power,
        traits=traits,
        traits_en=traits_en,
        card_type=card_type,
        card_type_en=card_type_en,
        counter=_first_int(full_card.get("counter"), card_basic.get("counter"), snapshot_card.get("counter")),
        block_number=_first_int(full_card.get("block_number"), card_basic.get("block_number"), snapshot_card.get("block_number")),
        attributes=resolved_attributes,
        attributes_en=attributes_en,
        card_sets=resolve_card_sets(card_id, card_basic, snapshot_card),
        variant_card_sets=collect_variant_card_sets(card_id),
        market_price=get_market_price_info(card_id),
        life=_to_int(card_basic.get("life") or full_card.get("life") or snapshot_card.get("life")),
    )


def normalize_effect_text(effect: Any) -> str | None:
    if effect is None:
        return None
    text = str(effect)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    return text.strip() or None


def _compose_effect_with_trigger(effect: str | None, trigger: str | None) -> str | None:
    """Official site keeps Trigger in a separate node; fold into effect text when missing."""
    effect_s = str(effect or "").strip()
    trigger_s = str(trigger or "").strip()
    if not trigger_s:
        return effect_s or None
    for label in ("Trigger", "觸發器", "触发器"):
        if trigger_s.startswith(label):
            trigger_s = trigger_s[len(label) :].lstrip(" :：").strip()
    if not trigger_s:
        return effect_s or None
    if trigger_s in effect_s:
        return effect_s or None
    if not effect_s:
        return trigger_s
    return f"{effect_s}\n{trigger_s}"


def build_card_brief(card_id: str, card_basic: dict[str, Any]) -> CardResponse:
    """Battle/detail overlay: name + effect only — no image fetch or market lookup."""
    snapshot_card = _snapshot_to_card_fields(card_id)
    pack_id = card_basic.get("pack_id")
    full_card: dict[str, Any] = {}
    effect = None
    if pack_id:
        pack_data = load_pack_data(str(pack_id))
        if pack_data is not None:
            full_card = extract_card_from_pack(pack_data, card_id) or {}
            effect, _power = extract_extra_from_pack(pack_data, card_id)
    raw_effect = effect or full_card.get("effect") or card_basic.get("effect") or snapshot_card.get("effect")
    effect_text = normalize_effect_text(raw_effect)
    trigger_text = normalize_effect_text(
        full_card.get("trigger") or card_basic.get("trigger") or snapshot_card.get("trigger")
    )
    trigger_en_text = normalize_effect_text(card_basic.get("trigger_en"))
    effect_en_text = normalize_effect_text(card_basic.get("effect_en"))
    if trigger_text:
        effect_text = _compose_effect_with_trigger(effect_text, trigger_text)
    if trigger_en_text:
        effect_en_text = _compose_effect_with_trigger(effect_en_text, trigger_en_text)
    name = str(card_basic.get("name") or snapshot_card.get("name") or "").strip() or None
    name_en = str(card_basic.get("name_en") or snapshot_card.get("name_en") or "").strip() or None
    return CardResponse(
        id=card_id,
        name=name,
        name_en=name_en,
        effect=effect_text,
        effect_en=effect_en_text,
        card_sets=resolve_card_sets(card_id, card_basic, snapshot_card),
    )


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    m = re.search(r"-?\d+", text)
    if not m:
        return None
    try:
        return int(m.group(0))
    except ValueError:
        return None


def _first_int(*values: Any) -> int | None:
    """First numeric value, including 0. Do not use `a or b` for cost/counter."""
    for value in values:
        parsed = _to_int(value)
        if parsed is not None:
            return parsed
    return None


def _zero_cost_if_event_or_stage(card_type: Any, cost: int | None) -> int | None:
    """Official cardlist prints Event/Stage 0 as '-'; treat missing play cost as 0."""
    if cost is not None:
        return cost
    text = str(card_type or "").lower()
    if any(tok in text for tok in ("event", "事件", "stage", "舞台", "场地", "場地")):
        return 0
    return None


COLOR_ALIASES: dict[str, str] = {
    "red": "red",
    "r": "red",
    "红": "red",
    "紅": "red",
    "赤": "red",
    "blue": "blue",
    "b": "blue",
    "蓝": "blue",
    "藍": "blue",
    "青": "blue",
    "green": "green",
    "g": "green",
    "绿": "green",
    "綠": "green",
    "緑": "green",
    "purple": "purple",
    "p": "purple",
    "紫": "purple",
    "black": "black",
    "k": "black",
    "黑": "black",
    "黒": "black",
    "yellow": "yellow",
    "y": "yellow",
    "黄": "yellow",
    "黃": "yellow",
}


def normalize_color_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    return COLOR_ALIASES.get(token, token)


def normalize_rarity(value: Any) -> str:
    """Canonical card rarities.

    DON cards: only Gold DON (former DON-SP) and DON (includes former DON-P).
    SP卡 and SP are the same → SP.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in {"DON-SP", "GOLD DON", "GOLD-DON", "GOLDDON"}:
        return "Gold DON"
    if upper in {"DON", "DON-P", "DONP"}:
        return "DON"
    if upper == "SP" or text == "SP卡":
        return "SP"
    return text


def rarity_match_key(value: Any) -> str:
    """Uppercase key for filter matching (legacy aliases folded via normalize_rarity)."""
    canon = normalize_rarity(value)
    return canon.upper() if canon else ""


# Filter / UI category order (user-specified). Unlisted rarities append after.
RARITY_FILTER_ORDER: tuple[str, ...] = (
    "L",
    "SP",
    "TR",
    "SEC",
    "SR",
    "R",
    "UR",
    "UC",
    "C",
    "P",
    "GOLD DON",
    "DON",
)
_RARITY_FILTER_RANK = {r: i for i, r in enumerate(RARITY_FILTER_ORDER)}


def rarity_sort_key(rarity: str) -> tuple[int, str]:
    r = str(rarity or "").strip().upper()
    return (_RARITY_FILTER_RANK.get(r, len(RARITY_FILTER_ORDER)), r)


def expand_color_tokens(values: Any) -> set[str]:
    tokens: set[str] = set()
    if isinstance(values, (list, tuple, set)):
        raw_items = [str(v or "") for v in values]
    else:
        raw_items = [str(values or "")]

    for item in raw_items:
        parts = re.split(r"[\/／、,，&\s]+", item.strip())
        for p in parts:
            norm = normalize_color_token(p)
            if norm:
                tokens.add(norm)
    return tokens


def infer_series_from_card_id(card_id: str) -> str:
    """Filter series for a card.

    Illustrated DON cards fold into their host set:
      DON17-10163 → OP17
      DONEB03-10082 → EB03
      DONPRB01-10216 → PRB01
    Generic DON00-* are type-only (no series chip).
    """
    text = normalize_card_id(card_id)
    if not text:
        return ""
    # DON00 / bare DON bucket — visible via type=Don only.
    if text.startswith("DON00-") or text == "DON00":
        return ""
    m = re.match(r"^DON(?:EB|PRB)?(\d{2})-", text)
    if m:
        num = m.group(1)
        if text.startswith("DONEB"):
            return f"EB{num}"
        if text.startswith("DONPRB"):
            return f"PRB{num}"
        return f"OP{num}"
    return text.split("-", 1)[0].upper()


def series_sort_key(series: str) -> tuple[str, int, str]:
    """Sort filter series: same prefix together, higher set number first (EB05→EB01)."""
    text = str(series or "").strip().upper()
    m = re.match(r"^([A-Z]+)(\d+)$", text)
    if m:
        prefix, num = m.groups()
        return (prefix, -int(num), text)
    return (text, 0, text)


def card_id_sort_key(card_id: str) -> tuple[int, int, int, str]:
    text = str(card_id or "").strip().upper().replace("_", "-")
    # Map DON host-set ids into the same order bucket as OP/EB/PRB.
    m_don = re.match(r"^DON(?:EB|PRB)?(\d{2})-(\d{3,5})$", text)
    if m_don and not text.startswith("DON00-"):
        num, tail = m_don.groups()
        if text.startswith("DONEB"):
            return (3, int(num), int(tail), "DON")
        if text.startswith("DONPRB"):
            return (4, int(num), int(tail), "DON")
        return (2, int(num), int(tail), "DON")
    if text.startswith("DON00-"):
        m0 = re.match(r"^DON00-(\d{3,5})$", text)
        return (98, 0, int(m0.group(1)) if m0 else 9999, "DON00")
    m = re.match(r"^([A-Z]+)(\d+)-(\d+)(?:-?([A-Z0-9]+))?$", text)
    if not m:
        return (999, 999, 9999, text)
    prefix, series, number, suffix = m.groups()
    prefix_order = {
        "ST": 1,
        "OP": 2,
        "EB": 3,
        "PRB": 4,
    }
    return (
        prefix_order.get(prefix, 99),
        int(series),
        int(number),
        suffix or "",
    )


def _safe_crop_main_art(im: Any) -> Any:
    """
    Crop center artwork area to reduce influence from language text blocks.
    """
    w, h = im.size
    left = int(w * 0.15)
    right = int(w * 0.85)
    top = int(h * 0.14)
    bottom = int(h * 0.74)
    if right <= left or bottom <= top:
        return im
    return im.crop((left, top, right, bottom))


def _compute_art_histogram(im: Any) -> list[float]:
    """
    Lightweight color histogram for artwork region similarity.
    Helps when photos are blurry but overall palette/composition is preserved.
    """
    art = _safe_crop_main_art(im.convert("RGB")).resize((64, 64))
    hist = art.histogram()  # 256 * 3 bins
    total = float(sum(hist) or 1.0)
    return [float(v) / total for v in hist]


def _compute_hash_pack_from_image(im: Any) -> dict[str, Any]:
    rgb = im.convert("RGB")
    art = _safe_crop_main_art(rgb)
    return {
        "full_phash": imagehash.phash(rgb),
        "art_phash": imagehash.phash(art),
        "art_dhash": imagehash.dhash(art),
        "art_hist": _compute_art_histogram(rgb),
    }


def _extract_card_like_crops_from_blob(blob: bytes) -> list[Any]:
    """
    Try to detect card boundary from a photo and return candidate crops.
    Fallback includes the original image.
    """
    if Image is None:
        return []
    crops: list[Any] = []
    try:
        from io import BytesIO

        with Image.open(BytesIO(blob)) as im0:
            base = im0.convert("RGB")
            crops.append(base)
    except Exception:
        return []

    if not _ensure_cv_deps() or cv2 is None:
        return crops
    try:
        np = __import__("numpy")
        arr = cv2.imdecode(np.frombuffer(blob, dtype=np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            return crops
        h, w = arr.shape[:2]
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 60, 150)
        edges = cv2.dilate(edges, None, iterations=1)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = None
        best_area = 0.0
        for cnt in contours:
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) != 4:
                continue
            area = cv2.contourArea(approx)
            if area < (w * h * 0.08):
                continue
            if area > best_area:
                best_area = area
                best = approx
        def _order_points(pts: Any) -> Any:
            # pts shape: (4,2)
            rect = np.zeros((4, 2), dtype="float32")
            s = pts.sum(axis=1)
            rect[0] = pts[np.argmin(s)]  # top-left
            rect[2] = pts[np.argmax(s)]  # bottom-right
            diff = np.diff(pts, axis=1)
            rect[1] = pts[np.argmin(diff)]  # top-right
            rect[3] = pts[np.argmax(diff)]  # bottom-left
            return rect

        if best is not None:
            # Perspective-corrected crop (preferred).
            try:
                pts = best.reshape(4, 2).astype("float32")
                rect = _order_points(pts)
                (tl, tr, br, bl) = rect
                widthA = np.linalg.norm(br - bl)
                widthB = np.linalg.norm(tr - tl)
                maxW = int(max(widthA, widthB))
                heightA = np.linalg.norm(tr - br)
                heightB = np.linalg.norm(tl - bl)
                maxH = int(max(heightA, heightB))
                if maxW > 40 and maxH > 40:
                    dst = np.array(
                        [[0, 0], [maxW - 1, 0], [maxW - 1, maxH - 1], [0, maxH - 1]],
                        dtype="float32",
                    )
                    M = cv2.getPerspectiveTransform(rect, dst)
                    warped = cv2.warpPerspective(arr, M, (maxW, maxH))
                    if warped is not None and warped.size > 0:
                        warp_rgb = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
                        crops.append(Image.fromarray(warp_rgb))
            except Exception:
                pass
            # Bounding-rect crop fallback.
            x, y, cw, ch = cv2.boundingRect(best)
            x = max(0, x)
            y = max(0, y)
            x2 = min(w, x + cw)
            y2 = min(h, y + ch)
            roi = arr[y:y2, x:x2]
            if roi is not None and roi.size > 0:
                roi_rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
                crops.append(Image.fromarray(roi_rgb))
    except Exception:
        pass
    return crops[:3]


def _get_rapidocr_engine() -> Any | None:
    """Process-wide RapidOCR singleton (loading ONNX once is expensive)."""
    global _rapidocr_engine
    if _rapidocr_engine is not None:
        return _rapidocr_engine
    try:
        from rapidocr_onnxruntime import RapidOCR

        _rapidocr_engine = RapidOCR()
        return _rapidocr_engine
    except Exception:
        return None


def _run_rapidocr_on_pil(img: Any) -> list[str]:
    engine = _get_rapidocr_engine()
    if engine is None or img is None:
        return []
    out: list[str] = []
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
            img.save(tmp.name)
            result, _ = engine(tmp.name)
        for item in result or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                txt = str(item[1]).strip()
                if txt:
                    out.append(txt)
    except Exception:
        return []
    return out


def _id_roi_crops_from_image(base: Any) -> list[Any]:
    """Lower-right card-id band (~25%×20%) plus a slightly wider fallback."""
    try:
        w, h = base.size
        rois = [
            base.crop((int(w * 0.75), int(h * 0.80), w, h)),
            base.crop((int(w * 0.58), int(h * 0.78), w, h)),
            base.crop((int(w * 0.50), int(h * 0.72), w, h)),
        ]
        return [r for r in rois if r.width >= 20 and r.height >= 16]
    except Exception:
        return []


def _pil_to_jpeg_bytes(img: Any, quality: int = 92) -> bytes:
    from io import BytesIO

    out = BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()


def _prefer_card_crop_blob(blob: bytes) -> bytes:
    """Prefer a perspective-corrected card crop for visual matching (webcam backgrounds hurt CLIP)."""
    try:
        crops = _extract_card_like_crops_from_blob(blob)
        if len(crops) > 1:
            # crops[0] is full frame; later entries are detected card quads.
            best = max(crops[1:], key=lambda im: int(getattr(im, "width", 0)) * int(getattr(im, "height", 0)))
            if getattr(best, "width", 0) >= 80 and getattr(best, "height", 0) >= 100:
                return _pil_to_jpeg_bytes(best, quality=92)
        # Fallback for handheld photos: card often fills the right/center of the frame.
        if crops:
            base = crops[0]
            w, h = base.size
            # Try a portrait window covering the dominant right/center area.
            for box in (
                (int(w * 0.28), int(h * 0.02), int(w * 0.98), int(h * 0.98)),
                (int(w * 0.18), int(h * 0.05), int(w * 0.88), int(h * 0.95)),
                (int(w * 0.08), int(h * 0.05), int(w * 0.72), int(h * 0.95)),
            ):
                l, t, r, b = box
                if r - l < 80 or b - t < 100:
                    continue
                roi = base.crop((l, t, r, b))
                # Prefer closer to card aspect (~63:88).
                ar = roi.width / max(1, roi.height)
                if 0.55 <= ar <= 0.85:
                    return _pil_to_jpeg_bytes(roi, quality=92)
            # Last resort: largest of the three windows.
            roi = base.crop((int(w * 0.28), int(h * 0.02), int(w * 0.98), int(h * 0.98)))
            return _pil_to_jpeg_bytes(roi, quality=92)
        return blob
    except Exception:
        return blob


def _estimate_card_colors_from_blob(blob: bytes) -> set[str]:
    """
    Rough frame-color estimate from a card crop (yellow/red/green/blue/purple/black).
    Soft signal only — art clothing can look black/red and should not hard-filter.
    """
    try:
        from io import BytesIO

        import numpy as _np
    except Exception:
        return set()
    if Image is None:
        return set()
    try:
        crop_blob = _prefer_card_crop_blob(blob)
        with Image.open(BytesIO(crop_blob)) as im0:
            im = im0.convert("RGB")
        w, h = im.size
        if w < 40 or h < 40:
            return set()
        arr = _np.asarray(im, dtype=_np.int16)
        # Prefer cost-circle / top-left frame (true set color), not character clothing.
        bw = max(2, int(w * 0.05))
        bh = max(2, int(h * 0.05))
        samples = [
            arr[:bh, :, :].reshape(-1, 3),  # top frame
            arr[: int(h * 0.16), : int(w * 0.22), :].reshape(-1, 3),  # cost circle
            arr[:, :bw, :].reshape(-1, 3),
            arr[:, -bw:, :].reshape(-1, 3),
        ]
        rings = _np.concatenate(samples, axis=0)
        if rings.size == 0:
            return set()
        r, g, b = rings[:, 0], rings[:, 1], rings[:, 2]
        scores = {
            "yellow": float(((r > 145) & (g > 125) & (b < 155) & (r > b + 28) & (g > b + 18)).mean()),
            "red": float(((r > 135) & (r > g + 35) & (r > b + 35) & (g < 125)).mean()),
            "green": float(((g > 125) & (g > r + 18) & (g > b + 12) & (r < 145)).mean()),
            "blue": float(((b > 125) & (b > r + 22) & (b > g + 12) & (r < 135)).mean()),
            "purple": float(((r > 95) & (b > 115) & (b > g + 18) & (r > g + 12) & (g < 135)).mean()),
            "black": float(((r < 55) & (g < 55) & (b < 55)).mean()),
        }
        # Prefer chromatic frame colors over black (art clothes are often dark).
        chromatic = {k: v for k, v in scores.items() if k != "black"}
        best_color, best_score = max(chromatic.items(), key=lambda x: x[1])
        if best_score >= 0.08:
            return {best_color}
        if scores["black"] >= 0.25:
            return {"black"}
        return set()
    except Exception:
        return set()


def _ocr_attribute_roi_texts(blob: bytes) -> list[str]:
    """Heavy OCR on cost (TL) / power (TR) / counter (mid-L) / name (bottom) regions."""
    try:
        from PIL import ImageEnhance, ImageOps
    except Exception:
        return []
    if _get_rapidocr_engine() is None:
        return []
    try:
        base_images = _extract_card_like_crops_from_blob(blob)
        if not base_images:
            from io import BytesIO

            with Image.open(BytesIO(blob)) as im0:
                base_images = [im0.convert("RGB")]
        # Prefer cropped card if available.
        bases = base_images[1:2] if len(base_images) > 1 else base_images[:1]
    except Exception:
        return []

    out: list[str] = []
    for base in bases:
        w, h = base.size
        rois = [
            base.crop((0, 0, int(w * 0.26), int(h * 0.20))),  # cost
            base.crop((int(w * 0.58), 0, w, int(h * 0.20))),  # power
            base.crop((0, int(h * 0.30), int(w * 0.20), int(h * 0.58))),  # counter
            base.crop((int(w * 0.08), int(h * 0.74), int(w * 0.92), int(h * 0.92))),  # name
        ]
        variants: list[Any] = []
        for roi in rois:
            if roi.width < 12 or roi.height < 12:
                continue
            big = roi.resize((max(1, roi.width * 3), max(1, roi.height * 3)))
            variants.append(big)
            variants.append(ImageOps.autocontrast(big))
            variants.append(ImageEnhance.Contrast(big).enhance(2.0))
            variants.append(ImageEnhance.Sharpness(big).enhance(2.4))
            gray = ImageOps.grayscale(big)
            for th in (100, 130, 160):
                variants.append(gray.point(lambda p, t=th: 255 if p > t else 0).convert("RGB"))
        for img in variants[:36]:
            out.extend(_run_rapidocr_on_pil(img))
    return list(dict.fromkeys(out))


def _extract_ocr_texts_from_blob(blob: bytes) -> list[str]:
    try:
        from PIL import ImageEnhance, ImageOps
    except Exception:
        return []
    if _get_rapidocr_engine() is None:
        return []
    try:
        base_images = _extract_card_like_crops_from_blob(blob)
        if not base_images:
            from io import BytesIO

            with Image.open(BytesIO(blob)) as im0:
                base_images = [im0.convert("RGB")]
        if len(base_images) > 1:
            base_images = base_images[1:]
    except Exception:
        return []

    variants: list[Any] = []
    for base in base_images[:2]:
        variants.append(base)
        variants.append(ImageEnhance.Contrast(base).enhance(1.45))
        variants.append(ImageOps.autocontrast(base))
        gray = ImageOps.grayscale(base)
        variants.append(gray.convert("RGB"))
        w, h = base.size
        # Match real OPCG print layout: cost TL, power TR, counter mid-L, name bottom.
        regions = [
            (0, 0, int(w * 0.28), int(h * 0.22)),  # cost
            (int(w * 0.55), 0, w, int(h * 0.22)),  # power + attribute
            (0, int(h * 0.28), int(w * 0.22), int(h * 0.62)),  # counter strip
            (int(w * 0.08), int(h * 0.72), int(w * 0.92), int(h * 0.92)),  # name / type
            (int(w * 0.18), int(h * 0.48), int(w * 0.88), int(h * 0.78)),  # effect text
            (int(w * 0.58), int(h * 0.78), w, h),  # optional ID corner
            (int(w * 0.75), int(h * 0.80), w, h),
        ]
        for l, t, r, b in regions:
            if r - l < 20 or b - t < 20:
                continue
            region = base.crop((max(0, l), max(0, t), min(w, r), min(h, b)))
            variants.append(region)
            variants.append(ImageOps.autocontrast(region))
            # Sharpen numeric corners (cost/power/counter).
            if (l <= int(w * 0.05) and t <= int(h * 0.05)) or (l >= int(w * 0.50) and t <= int(h * 0.05)) or (
                l <= int(w * 0.05) and int(h * 0.25) <= t <= int(h * 0.55)
            ):
                variants.append(ImageEnhance.Sharpness(region).enhance(2.4))
                variants.append(ImageEnhance.Contrast(region).enhance(1.9))
                rg = ImageOps.grayscale(region)
                for th in (110, 140):
                    variants.append(rg.point(lambda p, tt=th: 255 if p > tt else 0).convert("RGB"))

    variants = [v.resize((max(1, v.width * 2), max(1, v.height * 2))) for v in variants]
    out: list[str] = []
    for img in variants[:28]:
        out.extend(_run_rapidocr_on_pil(img))
    seen: set[str] = set()
    dedup: list[str] = []
    for t in out:
        if t in seen:
            continue
        seen.add(t)
        dedup.append(t)
    return dedup


def _extract_series_hints_from_text(text_blob: str) -> set[str]:
    text = str(text_blob or "").upper()
    text = text.replace("0P", "OP").replace("5T", "ST").replace("E8", "EB").replace("PR8", "PRB")
    hints: set[str] = set()
    # Prefer full card-id shaped series (OP09-001) — much less noisy than bare "E03".
    for m in re.finditer(r"\b(OP|ST|EB|PRB)\s*[-_ ]?\s*(\d{2})\s*[-_ ]?\s*\d{3}\b", text):
        hints.add(f"{m.group(1)}{m.group(2)}")
    for m in re.finditer(r"\b(?:OPD|OPO|OP)\s*[-_ ]?\s*(\d{1,2})\s*[-_ ]?\s*\d{3}\b", text):
        s = str(m.group(1) or "").zfill(2)[:2]
        hints.add(f"OP{s}")
    # Fallback: explicit series token with prefix letters (not lone E##).
    if not hints:
        for m in re.finditer(r"\b(OP|ST|EB|PRB)\s*[-_ ]?\s*(\d{2})\b", text):
            hints.add(f"{m.group(1)}{m.group(2)}")
    return hints


def _filter_relevant_ocr_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    ui_noise = ("识别这张卡", "識別這張卡", "请拍清", "請拍清", "放入外框", "匹配分", "recognize")
    for raw in lines or []:
        s = str(raw or "").strip()
        if not s:
            continue
        if any(n in s for n in ui_noise):
            continue
        u = s.upper()
        # Drop obvious handwritten date/name noise.
        if re.search(r"\b20\d{2}\b", u):
            continue
        if re.search(r"\b\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{1,2}\b", u):
            continue
        if re.search(r"\b[A-Z]{3,}\s+[A-Z]{3,}\b", u) and not re.search(r"ONE|PIECE|CARD|CHARACTER", u):
            continue
        keep = False
        if re.search(r"(OP|ST|EB|PRB|OPD|OPO)\s*[-_ ]?\d{1,2}\s*[-_ ]?\d{3,4}", u):
            keep = True
        if re.search(r"(CHARACTER|LEADER|EVENT|STAGE|COUNTER|KO|DON|ONE|PIECE)", u):
            keep = True
        if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", s):
            keep = True
        if re.search(r"\b(1000|2000|3000|4000|5000|6000|7000|8000|9000|10000|11000|12000)\b", u):
            keep = True
        # Power OCR often returns 10000O / 100000.
        if re.search(r"[0-9OＯ]{4,6}", u) and re.search(r"\d", u):
            keep = True
        if re.fullmatch(r"\d{1,2}", u):
            keep = True
        if keep:
            out.append(s)
    if out:
        # preserve order and de-dup
        return list(dict.fromkeys(out))
    return lines[:80]


def _ocr_power_values_from_text(text: str) -> list[int]:
    """Extract printed power candidates, including OCR mangling (10000O, 100000)."""
    out: list[int] = []
    for x in re.findall(r"(?<![+＋])\b(\d{4,5})\b", text):
        v = int(x)
        if 1000 <= v <= 15000 and v % 1000 == 0:
            out.append(v)
    for raw in re.findall(r"(?<![+＋\d])[0-9OＯo]{4,6}(?![0-9])", text):
        norm = raw.upper().replace("O", "0").replace("Ｏ", "0")
        if not norm.isdigit():
            continue
        v = int(norm)
        # Extra trailing zero from blur: 100000 → 10000.
        if v > 15000 and len(norm) == 6 and norm.endswith("0"):
            v = int(norm[:-1])
        if 1000 <= v <= 15000 and v % 1000 == 0:
            out.append(v)
    return list(dict.fromkeys(out))


def _extract_structured_hints_from_text(text_blob: str) -> dict[str, Any]:
    text = str(text_blob or "")
    upper = text.upper()
    hints: dict[str, Any] = {
        "series": _extract_series_hints_from_text(upper),
        "cost": None,
        "power": None,
        "counter": None,
        "block": None,
        "cost_candidates": [],
        "power_candidates": [],
        "counter_candidates": [],
        "block_candidates": [],
        "colors": set(),
        "types": set(),
        "rarities": set(),
        "tokens": [],
        "has_ko": False,
        "has_8000": False,
    }

    m_cost = re.search(r"(?:费用|費用|コスト|COST)\D{0,3}(\d{1,2})", text, flags=re.IGNORECASE)
    if m_cost:
        hints["cost"] = int(m_cost.group(1))
    hints["cost_candidates"] = [int(x) for x in re.findall(r"(?:费用|費用|コスト|COST)\D{0,3}(\d{1,2})", text, flags=re.IGNORECASE)]
    # Effect text like 「コスト1以下」must not become the card's play cost.
    effect_cost_noise = bool(
        re.search(r"(?:コスト|费用|費用|COST)\s*\d{1,2}\s*(?:以下|以上|の)", text, flags=re.IGNORECASE)
    )
    m_power = re.search(r"(?:力量|战力|戰力|POWER)\D{0,4}(\d{3,5})", text, flags=re.IGNORECASE)
    if m_power:
        hints["power"] = int(m_power.group(1))
    # Explicit power 0 (common on some Events/utility Characters).
    if hints["power"] is None and re.search(r"(?:力量|战力|戰力|POWER)\D{0,4}(?:0|０)\b", text, flags=re.IGNORECASE):
        hints["power"] = 0
    hints["power_candidates"] = [int(x) for x in re.findall(r"(?:力量|战力|戰力|POWER)\D{0,4}(\d{3,5})", text, flags=re.IGNORECASE)]
    m_counter = re.search(r"(?:反击|反擊|COUNTER|カウンター)\D{0,4}(\d{3,4})", text, flags=re.IGNORECASE)
    if m_counter:
        hints["counter"] = int(m_counter.group(1))
    hints["counter_candidates"] = [
        int(x)
        for x in re.findall(r"(?:反击|反擊|COUNTER|カウンター)\D{0,4}(\d{3,4})", text, flags=re.IGNORECASE)
    ]
    # Printed counter almost always appears as +1000 / +2000 (OCR may keep the plus).
    plus_counters = [int(x) for x in re.findall(r"[+＋]\s*(1000|2000)\b", text)]
    if plus_counters:
        hints["counter_candidates"].extend(plus_counters)
        if hints["counter"] is None:
            hints["counter"] = plus_counters[0]
    # Webcam OCR often truncates "+1000" → "+100" / "-+100". OPCG counters are only 1000/2000.
    if hints["counter"] is None and re.search(r"[+＋]\s*100(?!\d)", text):
        hints["counter"] = 1000
        hints["counter_candidates"].append(1000)
    m_block = re.search(r"(?:BLOCK|ブロック)\D{0,3}(\d{1,2})", text, flags=re.IGNORECASE)
    if m_block:
        hints["block"] = int(m_block.group(1))
    hints["block_candidates"] = [int(x) for x in re.findall(r"(?:BLOCK|ブロック)\D{0,3}(\d{1,2})", text, flags=re.IGNORECASE)]
    # Fallback for standalone power numbers (include 1000/2000; OP powers are xxx000).
    # Also recover mangled OCR like 10000O / 100000.
    p_cands = _ocr_power_values_from_text(text)
    if p_cands:
        hints["power_candidates"].extend(p_cands)
        best_p = max(p_cands)
        if hints["power"] is None:
            hints["power"] = best_p
        elif best_p > int(hints["power"]) and best_p >= 8000:
            # Prefer true high power over smaller OCR noise (e.g. 6000 + 10000O).
            hints["power"] = best_p
    if hints["power"] is None:
        p_cands = [
            int(x)
            for x in re.findall(r"(?<![+＋])\b(\d{4,5})\b", text)
            if 1000 <= int(x) <= 15000 and int(x) % 1000 == 0
        ]
        # Prefer values that are not already claimed as counter.
        counter_v = hints.get("counter")
        filtered = [p for p in p_cands if counter_v is None or p != counter_v]
        use = filtered or p_cands
        if use:
            # Power is usually the largest combat number on the card.
            hints["power"] = max(use)
            hints["power_candidates"].extend(use[:4])
    # Lone 0 / ０ often is printed power on utility characters (e.g. Doc Q).
    if hints["power"] is None and re.search(r"(?<!\d)(?:0|０)(?!\d)", text):
        # Only accept when counter was found — reduces false zeros from OCR noise.
        if hints.get("counter") is not None:
            hints["power"] = 0
    # Cost loose fallback: if no explicit label, infer from standalone 0~10 digits.
    if hints["cost"] is None and not effect_cost_noise:
        # If OCR contains date-like fragments (e.g. 1/5/26), avoid loose fallback.
        if re.search(r"\b\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{1,2}\b", text):
            loose_costs = []
        else:
            loose_costs = [int(x) for x in re.findall(r"(?<!\d)\b([1-9]|10)\b(?!\d)", text)]
        # Digits glued to counter OCR noise ("9-+1000", "P1>9-+1000") are not play cost.
        counter_glued = {
            int(x)
            for x in re.findall(r"(?<!\d)([1-9]|10)\s*[-~～]?\s*[+＋]\s*(?:1000|2000)\b", text)
        }
        loose_costs = [c for c in loose_costs if c not in counter_glued]
        if loose_costs:
            hints["cost_candidates"].extend(loose_costs[:6])
            # Prefer smaller costs (top-left is usually 1-8); avoid picking block/life noise.
            hints["cost"] = min(loose_costs)
    elif effect_cost_noise and hints.get("cost") is not None:
        # Labeled cost hit was likely from effect clause — drop unless no counter/power context.
        if hints.get("counter") is not None or hints.get("power") is not None:
            hints["cost"] = None
    # Final guard: cost that only appears as N-+1000 / N-+2000 is counter OCR junk.
    if hints.get("cost") is not None:
        cost_v = int(hints["cost"])
        glued_only = bool(
            re.search(
                rf"(?<!\d){cost_v}\s*[-~～]?\s*[+＋]\s*(?:1000|2000)\b",
                text,
            )
        )
        if glued_only and not re.search(
            rf"(?:费用|費用|コスト|COST)\D{{0,3}}{cost_v}\b", text, flags=re.IGNORECASE
        ):
            other_hits = [
                m.start()
                for m in re.finditer(rf"(?<!\d){cost_v}(?!\d)", text)
                if not re.match(
                    rf"{cost_v}\s*[-~～]?\s*[+＋]\s*(?:1000|2000)",
                    text[m.start() : m.start() + 12],
                )
            ]
            if not other_hits:
                hints["cost"] = None
                hints["cost_candidates"] = [c for c in hints.get("cost_candidates") or [] if int(c) != cost_v]
    # Keep unique candidate lists, bounded length.
    for k in ("cost_candidates", "power_candidates", "counter_candidates", "block_candidates"):
        uniq = list(dict.fromkeys([int(v) for v in hints.get(k, []) if str(v).isdigit()]))
        hints[k] = uniq[:6]

    color_map = {
        "RED": "red", "红": "red", "赤": "red",
        "BLUE": "blue", "蓝": "blue", "青": "blue",
        "GREEN": "green", "绿": "green", "緑": "green",
        "PURPLE": "purple", "紫": "purple",
        "BLACK": "black", "黑": "black",
        "YELLOW": "yellow", "黄": "yellow",
    }
    for k, v in color_map.items():
        if k in upper:
            hints["colors"].add(v)

    type_map = {
        "LEADER": "leader", "领航": "leader", "領航": "leader", "リーダー": "leader",
        "CHARACTER": "character", "角色": "character", "キャラ": "character",
        "EVENT": "event", "事件": "event",
        "STAGE": "stage", "场地": "stage", "場地": "stage",
    }
    for k, v in type_map.items():
        if k in upper:
            hints["types"].add(v)
    # OCR often corrupts CHARACTER into variants like CNATACTER/CNRAETER/CRIRACTFE.
    if "ACTER" in upper or "ACTFE" in upper or "ACTFI" in upper or "ACTEE" in upper:
        hints["types"].add("character")
    # "to your Leader" in effect text is common noise; if both exist, trust character.
    if "character" in hints["types"] and "leader" in hints["types"]:
        hints["types"].discard("leader")

    for r in ("SEC", "SR", "UC", "R", "C", "L"):
        if re.search(rf"\b{r}\b", upper):
            hints["rarities"].add(r)

    hints["tokens"] = [t for t in re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{2,}", text) if len(t) >= 2][:20]
    hints["has_ko"] = bool(re.search(r"\bKO\b|ＫＯ", upper))
    hints["has_8000"] = "8000" in upper
    return hints


def _to_text(v: Any) -> str:
    return str(v or "").strip().lower()


def _build_structured_candidates(hints: dict[str, Any], top_k: int = 25) -> list[tuple[str, int]]:
    scored: list[tuple[int, str]] = []
    for cid, basic in cards_by_id.items():
        snap = _snapshot_to_card_fields(cid)
        if hints.get("series"):
            pref = get_series_prefix(cid).upper()
            if pref not in hints["series"]:
                continue
        score = 0

        cost = _to_int((basic or {}).get("cost"))
        if cost is None:
            cost = _to_int(snap.get("cost"))
        if hints.get("cost") is not None and cost is not None and hints["cost"] == cost:
            score += 16

        power = _to_int((basic or {}).get("power"))
        if power is None:
            power = _to_int(snap.get("power"))
        if hints.get("power") is not None and power is not None and hints["power"] == power:
            score += 20

        counter = _to_int((basic or {}).get("counter"))
        if counter is None:
            counter = _to_int(snap.get("counter"))
        if hints.get("counter") is not None and counter is not None and hints["counter"] == counter:
            score += 12

        block = _to_int((basic or {}).get("block_number"))
        if block is None:
            block = _to_int(snap.get("block_number"))
        if hints.get("block") is not None and block is not None and hints["block"] == block:
            score += 8

        if hints.get("colors"):
            color_text = _to_text((basic or {}).get("color")) + " " + _to_text(snap.get("color"))
            if any(c in color_text for c in hints["colors"]):
                score += 10
        if hints.get("types"):
            type_text = _to_text((basic or {}).get("type")) + " " + _to_text(snap.get("type"))
            if any(t in type_text for t in hints["types"]):
                score += 10
        if hints.get("rarities"):
            rarity = rarity_match_key((basic or {}).get("rarity") or snap.get("rarity")).lower()
            if rarity and any(r.lower() == rarity for r in hints["rarities"]):
                score += 6

        name = _to_text((basic or {}).get("name")) or _to_text(snap.get("name"))
        effect = _to_text((basic or {}).get("effect")) or _to_text(snap.get("effect"))
        hay = f"{name} {effect}".strip()
        name_hint = _to_text(hints.get("name"))
        if name_hint and len(name_hint) >= 2 and name and name_hint in name:
            score += 22
        if hay and hints.get("tokens"):
            for tk in hints["tokens"]:
                tkl = tk.lower()
                if tkl in hay:
                    score += 2 if len(tkl) <= 3 else 4
        # Effect-level anchor signals from OCR.
        if hints.get("has_ko") and ("ko" in effect or "ｋｏ" in effect):
            score += 6
        if hints.get("has_8000") and "8000" in effect:
            score += 8

        if score > 0:
            scored.append((score, cid))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [(cid, s) for s, cid in scored[: max(1, top_k)]]


def _get_card_numeric_fields(card_id: str) -> dict[str, int | None]:
    basic = cards_by_id.get(card_id, {}) or {}
    snap = _snapshot_to_card_fields(card_id)
    # Snapshot data from official sync is treated as primary source of truth.
    snap_cost = _to_int(snap.get("cost"))
    snap_power = _to_int(snap.get("power"))
    snap_counter = _to_int(snap.get("counter"))
    snap_block = _to_int(snap.get("block_number"))
    return {
        "cost": snap_cost if snap_cost is not None else _to_int((basic or {}).get("cost")),
        "power": snap_power if snap_power is not None else _to_int((basic or {}).get("power")),
        "counter": snap_counter if snap_counter is not None else _to_int((basic or {}).get("counter")),
        "block": snap_block if snap_block is not None else _to_int((basic or {}).get("block_number")),
    }


def _card_color_token_set(card_id: str) -> set[str]:
    basic = cards_by_id.get(card_id, {}) or {}
    snap = _snapshot_to_card_fields(card_id)
    out: set[str] = set()
    for src in (basic.get("colors"), snap.get("colors"), basic.get("colors_en"), snap.get("colors_en")):
        if isinstance(src, list):
            for c in src:
                t = _to_text(c)
                if t:
                    out.add(t)
    color_blob = f"{_to_text(basic.get('color'))} {_to_text(snap.get('color'))}"
    alias = {
        "red": ("red", "红", "赤"),
        "blue": ("blue", "蓝", "青"),
        "green": ("green", "绿", "緑"),
        "purple": ("purple", "紫"),
        "black": ("black", "黑"),
        "yellow": ("yellow", "黄", "黃"),
    }
    for canon, keys in alias.items():
        if any(k in color_blob or k in out for k in keys):
            out.add(canon)
        for k in list(out):
            if k in keys:
                out.add(canon)
    return out


def _card_name_text(card_id: str) -> str:
    basic = cards_by_id.get(card_id, {}) or {}
    snap = _snapshot_to_card_fields(card_id)
    return f"{_to_text(basic.get('name'))} {_to_text(snap.get('name'))}".strip()


def _name_hint_matches(card_id: str, hints: dict[str, Any]) -> bool:
    name = _card_name_text(card_id)
    if not name:
        return False
    name_hint = _to_text(hints.get("name"))
    if name_hint and len(name_hint) >= 2 and name_hint in name:
        return True
    tokens = hints.get("tokens") or []
    hits = 0
    for raw in tokens:
        tk = _to_text(raw)
        if len(tk) < 3:
            continue
        # Skip generic OCR noise.
        if tk in {"character", "leader", "event", "stage", "counter", "power", "cost", "one", "piece"}:
            continue
        if tk in name:
            hits += 1
            if len(tk) >= 5 or hits >= 2:
                return True
    return False


def _count_attr_hint_fields(hints: dict[str, Any]) -> int:
    n = 0
    if hints.get("cost") is not None:
        n += 1
    if hints.get("power") is not None:
        n += 1
    if hints.get("counter") is not None:
        n += 1
    if hints.get("colors"):
        n += 1
    if _to_text(hints.get("name")) or any(len(_to_text(t)) >= 3 for t in (hints.get("tokens") or [])[:8]):
        n += 1
    return n


def _merge_recognize_attr_hints(ocr_hints: dict[str, Any], ds_hints: dict[str, Any]) -> dict[str, Any]:
    """Merge OCR + DeepSeek into attribute hints used to narrow the catalog."""
    out: dict[str, Any] = {
        "cost": None,
        "power": None,
        "counter": None,
        "block": None,
        "cost_candidates": list(ocr_hints.get("cost_candidates") or []),
        "power_candidates": list(ocr_hints.get("power_candidates") or []),
        "counter_candidates": list(ocr_hints.get("counter_candidates") or []),
        "block_candidates": list(ocr_hints.get("block_candidates") or []),
        "colors": set(ocr_hints.get("colors") or set()),
        "types": set(ocr_hints.get("types") or set()),
        "rarities": set(ocr_hints.get("rarities") or set()),
        "tokens": list(ocr_hints.get("tokens") or []),
        "name": "",
        "series": set(ocr_hints.get("series") or set()),
        "has_ko": bool(ocr_hints.get("has_ko")),
        "has_8000": bool(ocr_hints.get("has_8000")),
    }
    # Numerics: prefer agreement; on conflict trust OCR (printed digits are larger than card-id).
    for k in ("cost", "power", "counter", "block"):
        ocr_v = _to_int(ocr_hints.get(k))
        ds_v = _to_int(ds_hints.get(k))
        if ocr_v is not None and ds_v is not None:
            tol = 1 if k in {"cost", "block"} else (1000 if k == "power" else 0)
            out[k] = ocr_v if abs(int(ocr_v) - int(ds_v)) > tol else ds_v
        elif ocr_v is not None:
            out[k] = ocr_v
        elif ds_v is not None:
            out[k] = ds_v
    ds_color = _to_text(ds_hints.get("color"))
    if ds_color:
        out["colors"].add(ds_color)
        for alias, canon in (
            ("red", "red"), ("蓝", "blue"), ("blue", "blue"), ("green", "green"),
            ("purple", "purple"), ("black", "black"), ("yellow", "yellow"),
            ("红", "red"), ("赤", "red"), ("绿", "green"), ("紫", "purple"),
            ("黑", "black"), ("黄", "yellow"),
        ):
            if alias in ds_color:
                out["colors"].add(canon)
    name = str(ds_hints.get("name") or "").strip()
    if name:
        out["name"] = name
    if ds_hints.get("type"):
        out["types"].add(_to_text(ds_hints.get("type")))
    if ds_hints.get("rarity"):
        rk = rarity_match_key(ds_hints.get("rarity"))
        if rk:
            out["rarities"].add(rk)
    return out


def _card_matches_attr_filters(
    card_id: str,
    hints: dict[str, Any],
    *,
    use_power: bool = True,
    use_counter: bool = True,
    use_cost: bool = True,
    cost_tol: int = 0,
    use_color: bool = True,
    use_name: bool = True,
) -> bool:
    fields = _get_card_numeric_fields(card_id)
    if use_power and hints.get("power") is not None:
        pv = fields.get("power")
        hint_p = int(hints["power"])
        if hint_p == 0:
            # Catalog often stores power-0 utility characters as null.
            if pv is not None and int(pv) != 0:
                return False
        elif pv is None or int(pv) != hint_p:
            return False
    if use_counter and hints.get("counter") is not None:
        cv = fields.get("counter")
        # Events / stages often have no counter — allow None only when card type isn't character-like.
        if cv is None:
            type_blob = f"{_to_text((cards_by_id.get(card_id) or {}).get('type'))} {_to_text(_snapshot_to_card_fields(card_id).get('type'))}"
            if "character" in type_blob or "角色" in type_blob or "キャラ" in type_blob:
                return False
        elif int(cv) != int(hints["counter"]):
            return False
    if use_cost and hints.get("cost") is not None:
        cost = fields.get("cost")
        if cost is None or abs(int(cost) - int(hints["cost"])) > cost_tol:
            return False
    if use_color and hints.get("colors"):
        card_colors = _card_color_token_set(card_id)
        want = {_to_text(c) for c in hints["colors"]}
        if not card_colors.intersection(want):
            # Also allow substring on joined color text.
            joined = " ".join(card_colors)
            if not any(w and w in joined for w in want):
                return False
    if use_name and (_to_text(hints.get("name")) or hints.get("tokens")):
        if not _name_hint_matches(card_id, hints):
            # Name is soft when present with other strong filters — caller decides whether to require.
            return False
    return True


def _narrow_cards_by_attributes(
    hints: dict[str, Any],
    *,
    max_pool: int = 80,
    min_fields: int = 2,
) -> tuple[list[str], dict[str, Any]]:
    """
    Hard-narrow catalog by cost/power/counter/color/name.
    Returns (base_card_ids, meta). Empty list means "do not hard-narrow".
    """
    meta: dict[str, Any] = {"field_count": _count_attr_hint_fields(hints), "stage": "skip"}
    if meta["field_count"] < min_fields:
        meta["stage"] = "too_few_hints"
        return [], meta
    # +1000 alone matches thousands of cards — too weak to hard-narrow.
    if (
        hints.get("power") is None
        and hints.get("cost") is None
        and not hints.get("colors")
        and not _to_text(hints.get("name"))
        and hints.get("counter") is not None
    ):
        meta["stage"] = "counter_only_skip"
        return [], meta

    def _scan(**flags: Any) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for cid in cards_by_id:
            base = _base_card_id(cid)
            if base in seen:
                continue
            if _card_matches_attr_filters(base, hints, **flags):
                seen.add(base)
                out.append(base)
        return out

    # Progressive relaxation: strict → relax cost → drop name → drop color → power(+counter) only.
    attempts: list[tuple[str, dict[str, Any]]] = [
        ("strict", {"use_power": True, "use_counter": True, "use_cost": True, "cost_tol": 0, "use_color": True, "use_name": bool(_to_text(hints.get("name")))}),
        ("cost_tol1", {"use_power": True, "use_counter": True, "use_cost": True, "cost_tol": 1, "use_color": True, "use_name": bool(_to_text(hints.get("name")))}),
        ("no_name", {"use_power": True, "use_counter": True, "use_cost": True, "cost_tol": 1, "use_color": True, "use_name": False}),
        ("no_color", {"use_power": True, "use_counter": True, "use_cost": True, "cost_tol": 1, "use_color": False, "use_name": False}),
        ("power_counter", {"use_power": True, "use_counter": True, "use_cost": False, "cost_tol": 0, "use_color": False, "use_name": False}),
    ]
    # If no name hint, skip name-required stages' difference.
    if not _to_text(hints.get("name")) and not hints.get("tokens"):
        attempts = [a for a in attempts if a[0] != "strict"] or attempts

    best: list[str] = []
    for label, flags in attempts:
        # Don't require filters for missing hint fields — _card_matches already no-ops those.
        if hints.get("power") is None:
            flags = {**flags, "use_power": False}
        if hints.get("counter") is None:
            flags = {**flags, "use_counter": False}
        if hints.get("cost") is None:
            flags = {**flags, "use_cost": False}
        if not hints.get("colors"):
            flags = {**flags, "use_color": False}
        pool = _scan(**flags)
        meta["last_attempt"] = label
        meta["last_size"] = len(pool)
        if not pool:
            continue
        if len(pool) <= max_pool:
            meta["stage"] = label
            meta["size"] = len(pool)
            return pool, meta
        best = pool
    if best:
        # Still oversized after relax — keep a wider pool when only numeric attrs matched,
        # so CLIP can still see the true card (structured rank often drops it).
        if len(best) <= max(max_pool * 8, 600):
            meta["stage"] = "oversized_keep"
            meta["size"] = len(best)
            return best, meta
        scored = _rank_cards_by_structured_hints({**hints, "color": next(iter(hints.get("colors") or []), "")}, top_k=max_pool)
        ranked = [c for c, _s in scored if _base_card_id(c) in set(best)]
        if not ranked:
            ranked = best[:max_pool]
        meta["stage"] = "oversized_ranked"
        meta["size"] = len(ranked[:max_pool])
        return ranked[:max_pool], meta
    meta["stage"] = "empty"
    return [], meta


def _attr_match_score(card_id: str, hints: dict[str, Any]) -> int:
    """Soft score for ranking inside an attribute pool."""
    score = 0
    fields = _get_card_numeric_fields(card_id)
    if hints.get("power") is not None and fields.get("power") == hints.get("power"):
        score += 24
    if hints.get("counter") is not None and fields.get("counter") == hints.get("counter"):
        score += 16
    if hints.get("cost") is not None and fields.get("cost") is not None:
        diff = abs(int(fields["cost"]) - int(hints["cost"]))
        if diff == 0:
            score += 18
        elif diff == 1:
            score += 8
    if hints.get("colors"):
        if _card_color_token_set(card_id).intersection({_to_text(c) for c in hints["colors"]}):
            score += 12
    if _name_hint_matches(card_id, hints):
        score += 20
    return score


def _candidate_matches_hard_hints(card_id: str, hints: dict[str, Any], require_series: bool = True) -> bool:
    if not hints:
        return True
    if require_series and hints.get("series"):
        pref = get_series_prefix(card_id).upper()
        if pref not in hints["series"]:
            return False
    fields = _get_card_numeric_fields(card_id)
    def _field_match(name: str, tolerance: int = 0) -> bool:
        hv = hints.get(name)
        cands = [int(x) for x in (hints.get(f"{name}_candidates") or []) if str(x).isdigit()]
        cv = fields.get(name)
        if cv is None:
            return False
        cv_i = int(cv)
        if cands:
            return any(abs(cv_i - int(v)) <= tolerance for v in cands)
        if hv is None:
            return True
        return abs(cv_i - int(hv)) <= tolerance

    # cost OCR is noisy; allow +-1. others stay strict.
    if hints.get("cost") is not None or hints.get("cost_candidates"):
        if not _field_match("cost", tolerance=1):
            return False
    if hints.get("power") is not None or hints.get("power_candidates"):
        if not _field_match("power", tolerance=0):
            return False
    if hints.get("counter") is not None or hints.get("counter_candidates"):
        if not _field_match("counter", tolerance=0):
            return False
    if hints.get("block") is not None or hints.get("block_candidates"):
        if not _field_match("block", tolerance=0):
            return False
    return True


def _filter_candidates_by_hard_hints(
    candidate_ids: list[str],
    hints: dict[str, Any],
    require_series: bool = True,
) -> list[str]:
    if not candidate_ids or not hints:
        return candidate_ids
    out = [cid for cid in candidate_ids if _candidate_matches_hard_hints(cid, hints, require_series=require_series)]
    return out if out else candidate_ids


def _fuzzy_candidates_from_text_blob(
    text_blob: str,
    top_k: int = 20,
    series_hints: set[str] | None = None,
) -> list[str]:
    text = " ".join(str(text_blob or "").lower().split())
    if not text:
        return []
    tokens = [t for t in re.findall(r"[a-z0-9\u4e00-\u9fff]{2,}", text) if len(t) >= 2][:40]
    if not tokens:
        return []
    scored: list[tuple[int, str]] = []
    for cid, basic in cards_by_id.items():
        if series_hints:
            pref = get_series_prefix(cid).upper()
            if pref not in series_hints:
                continue
        name = str((basic or {}).get("name") or "").lower()
        effect = str((basic or {}).get("effect") or "").lower()
        snap = _snapshot_to_card_fields(cid)
        if not effect:
            effect = str(snap.get("effect") or "").lower()
        hay = f"{name} {effect}"
        if not hay.strip():
            continue
        score = 0
        for tk in tokens:
            if tk and tk in hay:
                score += min(8, len(tk))
        if score > 0:
            scored.append((score, cid))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [cid for _s, cid in scored[: max(1, top_k)]]


def _deepseek_pick_from_text(text_blob: str, candidate_ids: list[str]) -> str | None:
    if not RECOGNIZE_USE_DEEPSEEK:
        return None
    if not candidate_ids:
        return None
    api_key = get_api_key()
    if not api_key:
        return None
    # attach short metadata to help LLM choose among candidates.
    lines: list[str] = []
    for cid in candidate_ids[:25]:
        basic = cards_by_id.get(cid, {})
        name = str((basic or {}).get("name") or "").strip()
        effect = str((basic or {}).get("effect") or "").replace("\n", " ").strip()
        if not effect:
            effect = str((_snapshot_to_card_fields(cid).get("effect") or "")).replace("\n", " ").strip()
        lines.append(f"{cid} | {name} | {effect[:120]}")
    prompt = (
        "以下是从模糊照片OCR提取到的残缺文本：\n"
        f"{text_blob[:600]}\n\n"
        "请从候选卡号中选最可能的一张，只返回 JSON：{\"card_id\":\"...\"}\n"
        "候选列表：\n" + "\n".join(lines)
    )
    try:
        if not _ensure_openai() or OpenAI is None:
            raise RuntimeError("OpenAI SDK unavailable")
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        comp = client.chat.completions.create(
            model=DEEPSEEK_RECOGNIZE_MODEL,
            messages=[
                {"role": "system", "content": "你是卡牌识别助手，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=140,
        )
        content = comp.choices[0].message.content if comp.choices else ""
    except Exception:
        return None
    return _parse_deepseek_recognize_card_id(str(content or ""))


def _deepseek_extract_structured_hints(blob: bytes) -> dict[str, Any]:
    if not RECOGNIZE_DEEPSEEK_VISION:
        return {"_error": "deepseek_vision_disabled"}
    if not RECOGNIZE_USE_DEEPSEEK:
        return {"_error": "deepseek_disabled"}
    api_key = get_api_key()
    if not api_key:
        return {"_error": "missing_api_key"}
    def _shrink_for_deepseek(raw: bytes) -> bytes:
        if Image is None:
            return raw
        try:
            from io import BytesIO
            with Image.open(BytesIO(raw)) as im:
                rgb = im.convert("RGB")
                max_side = max(rgb.size)
                if max_side > 1280:
                    ratio = 1280.0 / float(max_side)
                    rgb = rgb.resize((max(1, int(rgb.width * ratio)), max(1, int(rgb.height * ratio))))
                out = BytesIO()
                rgb.save(out, format="JPEG", quality=82, optimize=True)
                data = out.getvalue()
                return data if data else raw
        except Exception:
            return raw

    compact_blob = _shrink_for_deepseek(blob)
    b64 = base64.b64encode(compact_blob).decode("ascii")
    prompt = (
        "你是 One Piece 卡牌识别助手。请只根据图片提取结构化信息并返回 JSON，"
        "字段包含：card_id,name,cost,power,counter,color,type,rarity,block,confidence。"
        "如果不确定可填 null。confidence 只允许 high/medium/low。"
    )
    try:
        if not _ensure_openai() or OpenAI is None:
            raise RuntimeError("OpenAI SDK unavailable")
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=20.0)
        completion = client.chat.completions.create(
            model=DEEPSEEK_RECOGNIZE_MODEL,
            messages=[
                {"role": "system", "content": "你是严谨的图像识别助手，只输出 JSON。"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                },
            ],
            temperature=0,
            max_tokens=260,
        )
        content = completion.choices[0].message.content if completion.choices else ""
        text = _extract_json_text(str(content or ""))
        obj = json.loads(text)
        if not isinstance(obj, dict):
            return {"_error": "invalid_json_payload"}
        out: dict[str, Any] = {}
        cid = normalize_card_id(str(obj.get("card_id") or ""))
        if cid:
            out["card_id"] = _base_card_id(cid)
        for k in ("name", "color", "type", "rarity", "confidence"):
            v = obj.get(k)
            if v is not None:
                out[k] = str(v).strip()
        for k in ("cost", "power", "counter", "block"):
            v = obj.get(k)
            iv = _to_int(v)
            if iv is not None:
                out[k] = iv
        if not out:
            out["_error"] = "empty_structured_payload"
        return out
    except Exception as exc:
        return {"_error": f"deepseek_structured_exception:{type(exc).__name__}:{str(exc)[:160]}"}


def _deepseek_extract_structured_hints_from_text(text_blob: str) -> dict[str, Any]:
    if not RECOGNIZE_USE_DEEPSEEK:
        return {"_error": "deepseek_disabled"}
    api_key = get_api_key()
    if not api_key:
        return {"_error": "missing_api_key"}
    text_blob = str(text_blob or "").strip()
    if not text_blob:
        return {"_error": "empty_text_blob"}
    prompt = (
        "以下是卡图OCR文本（可能有错误/缺字），请提取结构化信息并返回 JSON："
        "card_id,name,cost,power,counter,color,type,rarity,block,confidence。"
        "不确定填 null，confidence 仅 high/medium/low。\n\n"
        f"OCR:\n{text_blob[:1800]}"
    )
    try:
        if not _ensure_openai() or OpenAI is None:
            raise RuntimeError("OpenAI SDK unavailable")
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=20.0)
        completion = client.chat.completions.create(
            model=DEEPSEEK_RECOGNIZE_MODEL,
            messages=[
                {"role": "system", "content": "你是严谨的卡牌信息抽取助手，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=260,
        )
        content = completion.choices[0].message.content if completion.choices else ""
        text = _extract_json_text(str(content or ""))
        obj = json.loads(text)
        if not isinstance(obj, dict):
            return {"_error": "invalid_json_payload"}
        out: dict[str, Any] = {}
        cid = normalize_card_id(str(obj.get("card_id") or ""))
        if cid:
            out["card_id"] = _base_card_id(cid)
        for k in ("name", "color", "type", "rarity", "confidence"):
            v = obj.get(k)
            if v is not None:
                out[k] = str(v).strip()
        for k in ("cost", "power", "counter", "block"):
            iv = _to_int(obj.get(k))
            if iv is not None:
                out[k] = iv
        if not out:
            out["_error"] = "empty_structured_payload"
        return out
    except Exception as exc:
        return {"_error": f"deepseek_text_structured_exception:{type(exc).__name__}:{str(exc)[:160]}"}


def _deepseek_extract_structured_hints_multi(blob: bytes) -> dict[str, Any]:
    """
    Multi-view extraction: full photo + card-like crops + key regions.
    This is much closer to manual "zoom and inspect" behavior.
    """
    views: list[bytes] = [blob]
    if Image is not None:
        try:
            for base in _extract_card_like_crops_from_blob(blob)[:2]:
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
                    base.convert("RGB").save(tmp.name, format="JPEG", quality=92)
                    tmp.seek(0)
                    views.append(Path(tmp.name).read_bytes())
                w, h = base.size
                # top-right (power/attribute), lower-right (card id/block), mid-lower (name/type)
                regions = [
                    (int(w * 0.56), 0, w, int(h * 0.34)),
                    (int(w * 0.58), int(h * 0.78), w, h),
                    (int(w * 0.18), int(h * 0.56), int(w * 0.88), int(h * 0.86)),
                ]
                for l, t, r, b in regions:
                    if r - l < 24 or b - t < 24:
                        continue
                    rg = base.crop((l, t, r, b)).resize((max(1, (r - l) * 2), max(1, (b - t) * 2)))
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp2:
                        rg.convert("RGB").save(tmp2.name, format="JPEG", quality=95)
                        tmp2.seek(0)
                        views.append(Path(tmp2.name).read_bytes())
        except Exception:
            pass
    # Limit external calls — full frame + best crop is enough for latency.
    views = views[:2]

    view_results: list[dict[str, Any]] = []
    hints_list: list[dict[str, Any]] = []
    for vb in views:
        h = _deepseek_extract_structured_hints(vb)
        if h:
            view_results.append(h)
        if any(k in h for k in ("card_id", "cost", "power", "counter", "block", "name", "color", "type", "rarity")):
            hints_list.append(h)
    if not hints_list:
        return {"_views": view_results[:6], "_error": "no_valid_structured_hints"}

    # Aggregate by majority / max-confidence.
    out: dict[str, Any] = {}
    # card_id vote
    cid_count: dict[str, int] = {}
    for h in hints_list:
        cid = normalize_card_id(str(h.get("card_id") or ""))
        if cid:
            base = _base_card_id(cid)
            cid_count[base] = cid_count.get(base, 0) + 1
    if cid_count:
        out["card_id"] = sorted(cid_count.items(), key=lambda x: x[1], reverse=True)[0][0]

    def _pick_num(key: str) -> int | None:
        c: dict[int, int] = {}
        for h in hints_list:
            v = _to_int(h.get(key))
            if v is None:
                continue
            c[v] = c.get(v, 0) + 1
        if not c:
            return None
        return sorted(c.items(), key=lambda x: (x[1], x[0]), reverse=True)[0][0]

    for k in ("cost", "power", "counter", "block"):
        v = _pick_num(k)
        if v is not None:
            out[k] = v

    # keep first non-empty textual hints
    for k in ("name", "color", "type", "rarity"):
        for h in hints_list:
            v = str(h.get(k) or "").strip()
            if v:
                out[k] = v
                break
    conf_rank = {"high": 3, "medium": 2, "low": 1}
    best_conf = "low"
    for h in hints_list:
        c = str(h.get("confidence") or "").strip().lower()
        if conf_rank.get(c, 0) > conf_rank.get(best_conf, 0):
            best_conf = c
    out["confidence"] = best_conf
    out["_views"] = view_results[:6]
    return out


def _rank_cards_by_structured_hints(hints: dict[str, Any], top_k: int = 12) -> list[tuple[str, int]]:
    if not hints:
        return []
    scored: list[tuple[int, str]] = []
    name_hint = str(hints.get("name") or "").strip().lower()
    color_hint = str(hints.get("color") or "").strip().lower()
    type_hint = str(hints.get("type") or "").strip().lower()
    rarity_hint = rarity_match_key(hints.get("rarity"))

    for cid, basic in cards_by_id.items():
        snap = _snapshot_to_card_fields(cid)
        score = 0
        fields = _get_card_numeric_fields(cid)
        if hints.get("cost") is not None and fields.get("cost") == hints.get("cost"):
            score += 18
        if hints.get("power") is not None and fields.get("power") == hints.get("power"):
            score += 24
        if hints.get("counter") is not None and fields.get("counter") == hints.get("counter"):
            score += 16
        if hints.get("block") is not None and fields.get("block") == hints.get("block"):
            score += 10
        if color_hint:
            ctext = f"{_to_text((basic or {}).get('color'))} {_to_text(snap.get('color'))}"
            if color_hint in ctext:
                score += 8
        if type_hint:
            ttext = f"{_to_text((basic or {}).get('type'))} {_to_text(snap.get('type'))} {_to_text((basic or {}).get('category'))}"
            if type_hint in ttext:
                score += 8
        if rarity_hint:
            r = rarity_match_key((basic or {}).get("rarity") or snap.get("rarity"))
            if r == rarity_hint:
                score += 6
        if name_hint:
            nm = f"{_to_text((basic or {}).get('name'))} {_to_text(snap.get('name'))}"
            if name_hint and name_hint in nm:
                score += 12
        if score > 0:
            scored.append((score, cid))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(cid, s) for s, cid in scored[: max(1, top_k)]]


def _sanitize_deepseek_hints(ds_hints: dict[str, Any], ocr_hints: dict[str, Any]) -> dict[str, Any]:
    if not ds_hints:
        return {}
    out: dict[str, Any] = {}
    if "_views" in ds_hints:
        out["_views"] = ds_hints.get("_views")
    if "_error" in ds_hints:
        out["_error"] = ds_hints.get("_error")
    conf = str(ds_hints.get("confidence") or "").strip().lower()
    if conf in {"high", "medium", "low"}:
        out["confidence"] = conf

    cid = normalize_card_id(str(ds_hints.get("card_id") or ""))
    if re.match(r"^(OP|ST|EB|PRB)\d{2}-\d{3}(?:-[A-Z0-9]+)?$", cid or ""):
        base = _base_card_id(cid)
        if base in cards_by_id:
            out["card_id"] = base

    for k in ("name", "color", "type", "rarity"):
        v = str(ds_hints.get(k) or "").strip()
        if v:
            out[k] = v

    # Numeric fields: OCR is usually more reliable than low-confidence LLM extraction.
    for k in ("cost", "power", "counter", "block"):
        ocr_v = _to_int(ocr_hints.get(k))
        ds_v = _to_int(ds_hints.get(k))
        if ds_v is None and ocr_v is not None:
            out[k] = ocr_v
            continue
        if ds_v is None:
            continue
        if ocr_v is None:
            # Low-confidence DeepSeek-only cost is frequently wrong (effect text / counter glue).
            if k == "cost" and conf == "low":
                continue
            out[k] = ds_v
            continue
        # Conflict handling: trust OCR on large mismatch or low confidence.
        if conf == "low":
            out[k] = ocr_v
            continue
        tol = 1 if k in {"cost", "block"} else 1000 if k == "power" else 0
        if abs(int(ds_v) - int(ocr_v)) > tol:
            out[k] = ocr_v
        else:
            out[k] = ds_v
    return out


def _hist_l1_distance(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 1.0
    return sum(abs(x - y) for x, y in zip(a, b))


def _orb_match_score(query_blob: bytes, candidate_path: Path) -> float:
    """
    ORB feature matching score (higher is better).
    Used as a reranker for top visual candidates.
    """
    if not _ensure_cv_deps() or cv2 is None:
        return 0.0
    try:
        q_arr = cv2.imdecode(
            __import__("numpy").frombuffer(query_blob, dtype=__import__("numpy").uint8),
            cv2.IMREAD_COLOR,
        )
        c_arr = cv2.imread(str(candidate_path), cv2.IMREAD_COLOR)
        if q_arr is None or c_arr is None:
            return 0.0
        # Focus on artwork area.
        qh, qw = q_arr.shape[:2]
        ch, cw = c_arr.shape[:2]
        q_crop = q_arr[int(qh * 0.14): int(qh * 0.74), int(qw * 0.15): int(qw * 0.85)]
        c_crop = c_arr[int(ch * 0.14): int(ch * 0.74), int(cw * 0.15): int(cw * 0.85)]
        if q_crop.size == 0 or c_crop.size == 0:
            return 0.0
        orb = cv2.ORB_create(nfeatures=800)
        kp1, des1 = orb.detectAndCompute(q_crop, None)
        kp2, des2 = orb.detectAndCompute(c_crop, None)
        if des1 is None or des2 is None or not kp1 or not kp2:
            return 0.0
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        pairs = bf.knnMatch(des1, des2, k=2)
        good = 0
        for m_n in pairs:
            if len(m_n) < 2:
                continue
            m, n = m_n
            if m.distance < 0.75 * n.distance:
                good += 1
        return float(good)
    except Exception:
        return 0.0


def _best_local_path_for_card(card_id: str) -> Path | None:
    cid = normalize_card_id(card_id)
    if cid in local_image_path_map:
        return local_image_path_map[cid]
    base = _base_card_id(cid)
    for k, p in local_image_path_map.items():
        if k == base or k.startswith(base + "-"):
            return p
    return None


def _clip_available() -> bool:
    _ensure_cv_deps()
    if not _ensure_clip_deps():
        return False
    return bool(np is not None and torch is not None and CLIPModel is not None and CLIPProcessor is not None)


def _load_clip_runtime() -> bool:
    global clip_model, clip_processor
    if not _clip_available():
        return False
    if clip_model is not None and clip_processor is not None:
        return True
    try:
        clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)
        clip_model = CLIPModel.from_pretrained(CLIP_MODEL_NAME)
        clip_model.eval()
        return True
    except Exception:
        clip_model = None
        clip_processor = None
        return False


def _clip_image_feature_tensor(inputs: Any) -> Any | None:
    """
    Normalize CLIP get_image_features across transformers versions.
    transformers>=5 may return BaseModelOutputWithPooling instead of a tensor;
    indexing [0] then wrongly grabs last_hidden_state (1, 50, 768).
    """
    with torch.no_grad():
        feats = clip_model.get_image_features(**inputs)
    if torch.is_tensor(feats):
        return feats
    pooled = getattr(feats, "pooler_output", None)
    if pooled is not None and torch.is_tensor(pooled):
        # Already projected to embed dim in some versions; otherwise project.
        proj = getattr(clip_model, "visual_projection", None)
        if proj is not None and int(pooled.shape[-1]) != int(getattr(proj, "out_features", pooled.shape[-1])):
            return proj(pooled)
        return pooled
    hidden = getattr(feats, "last_hidden_state", None)
    if hidden is not None and torch.is_tensor(hidden):
        # CLS token → projection fallback
        cls = hidden[:, 0]
        proj = getattr(clip_model, "visual_projection", None)
        return proj(cls) if proj is not None else cls
    return None


def _clip_embed_pil_image(im: Any) -> Any | None:
    if not _load_clip_runtime():
        return None
    try:
        inputs = clip_processor(images=im.convert("RGB"), return_tensors="pt")
        feats = _clip_image_feature_tensor(inputs)
        if feats is None or not torch.is_tensor(feats):
            return None
        vec = feats[0].detach().cpu().numpy().astype("float32").reshape(-1)
        norm = float(np.linalg.norm(vec))
        if norm <= 0:
            return None
        return vec / norm
    except Exception:
        return None


def _clip_embed_blob(blob: bytes) -> Any | None:
    if Image is None:
        return None
    try:
        from io import BytesIO
        with Image.open(BytesIO(blob)) as im:
            # Use full + card crop and average them for robustness.
            vecs = []
            v0 = _clip_embed_pil_image(im)
            if v0 is not None:
                vecs.append(v0)
            crop = _safe_crop_main_art(im.convert("RGB"))
            v1 = _clip_embed_pil_image(crop)
            if v1 is not None:
                vecs.append(v1)
            if not vecs:
                return None
            mix = np.mean(np.stack(vecs, axis=0), axis=0)
            norm = float(np.linalg.norm(mix))
            if norm <= 0:
                return None
            return (mix / norm).astype("float32")
    except Exception:
        return None


def ensure_clip_index() -> None:
    global clip_index_ready, clip_embeddings
    if clip_index_ready:
        return
    if not _load_clip_runtime() or Image is None:
        clip_index_ready = True
        clip_embeddings = {}
        return
    try:
        import numpy as _np  # type: ignore
    except Exception:
        clip_index_ready = True
        clip_embeddings = {}
        return

    sig = _packs_index_signature()
    try:
        if PHOTO_CLIP_INDEX_FILE.exists():
            data = _np.load(PHOTO_CLIP_INDEX_FILE, allow_pickle=True)
            cached_sig = {
                "count": int(data["sig_count"]) if "sig_count" in data else -1,
                "mtime_ns": int(data["sig_mtime_ns"]) if "sig_mtime_ns" in data else -1,
            }
            ids = [str(x) for x in data["ids"].tolist()] if "ids" in data else []
            mat = data["emb"] if "emb" in data else None
            # Require flat embedding vectors (N, D). Reject corrupt caches such as
            # (N, 1, 50, 768) produced when transformers returned hidden states.
            mat_ok = (
                mat is not None
                and len(getattr(mat, "shape", ())) == 2
                and int(mat.shape[0]) == len(ids)
                and int(mat.shape[1]) >= 64
            )
            if cached_sig == sig and mat_ok and ids:
                out = {cid: mat[i].astype("float32").reshape(-1) for i, cid in enumerate(ids)}
                clip_embeddings = out
                clip_index_ready = True
                return
    except Exception:
        pass

    out: dict[str, Any] = {}
    for cid, path in local_image_path_map.items():
        try:
            with Image.open(path) as im:
                vec = _clip_embed_pil_image(im)
        except Exception:
            vec = None
        if vec is not None and cid not in out:
            out[cid] = vec
    clip_embeddings = out
    clip_index_ready = True
    try:
        if out:
            ids = list(out.keys())
            mat = _np.stack([out[i] for i in ids], axis=0).astype("float32")
            PHOTO_CLIP_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
            _np.savez_compressed(
                PHOTO_CLIP_INDEX_FILE,
                ids=_np.array(ids, dtype=object),
                emb=mat,
                sig_count=_np.array(sig["count"]),
                sig_mtime_ns=_np.array(sig["mtime_ns"]),
            )
    except Exception:
        pass


def recognize_top_candidates_clip(blob: bytes, top_k: int = 5) -> list[tuple[str, int]]:
    try:
        import numpy as _np  # type: ignore
    except Exception:
        return []
    ensure_clip_index()
    if not clip_embeddings:
        return []
    q = _clip_embed_blob(blob)
    if q is None:
        return []
    base_best: dict[str, float] = {}
    for cid, vec in clip_embeddings.items():
        try:
            sim = float(_np.dot(q, vec))
        except Exception:
            continue
        base = _base_card_id(cid)
        if base not in base_best or sim > base_best[base]:
            base_best[base] = sim
    ranked = sorted(base_best.items(), key=lambda x: x[1], reverse=True)[: max(1, top_k)]
    return [(cid, int(round((1.0 - sim) * 1000))) for cid, sim in ranked]


def _visual_confidence(dist: int | None, gap: int | None, *, use_clip: bool) -> str:
    if dist is None:
        return "low"
    if use_clip:
        if dist <= CLIP_HIGH_DIST and (gap is None or gap >= CLIP_HIGH_GAP):
            return "high"
        if dist <= CLIP_MED_DIST and (gap is None or gap >= CLIP_MED_GAP):
            return "medium"
        return "low"
    if dist <= 8 and (gap is None or gap >= 8):
        return "high"
    if dist <= 16 and (gap is None or gap >= 4):
        return "medium"
    return "low"


def _parse_deepseek_recognize_card_id(content: str) -> str | None:
    text = _extract_json_text(content or "")
    try:
        obj = json.loads(text)
        cid = normalize_card_id(str(obj.get("card_id") or ""))
        if cid:
            base = _base_card_id(cid)
            if base in cards_by_id:
                return base
            if cid in cards_by_id:
                return cid
    except Exception:
        pass
    m = re.search(r"\b((?:OP|ST|EB|PRB)\d{2}-\d{3}(?:-[A-Z0-9]+)?)\b", text.upper())
    if not m:
        return None
    cid = normalize_card_id(m.group(1))
    base = _base_card_id(cid)
    if base in cards_by_id:
        return base
    if cid in cards_by_id:
        return cid
    return None


def recognize_card_id_with_deepseek(blob: bytes, candidate_ids: list[str]) -> str | None:
    if not RECOGNIZE_USE_DEEPSEEK:
        return None
    api_key = get_api_key()
    if not api_key:
        return None
    def _shrink_for_deepseek(raw: bytes) -> bytes:
        if Image is None:
            return raw
        try:
            from io import BytesIO
            with Image.open(BytesIO(raw)) as im:
                rgb = im.convert("RGB")
                max_side = max(rgb.size)
                if max_side > 1280:
                    ratio = 1280.0 / float(max_side)
                    rgb = rgb.resize((max(1, int(rgb.width * ratio)), max(1, int(rgb.height * ratio))))
                out = BytesIO()
                rgb.save(out, format="JPEG", quality=82, optimize=True)
                data = out.getvalue()
                return data if data else raw
        except Exception:
            return raw

    compact_blob = _shrink_for_deepseek(blob)
    b64 = base64.b64encode(compact_blob).decode("ascii")
    candidate_text = ", ".join(candidate_ids[:20]) if candidate_ids else "不限"
    prompt_free = (
        "你是 One Piece 卡牌识别助手。"
        "请只根据图片识别最可能的卡号，不要受任何候选限制。"
        "只返回 JSON：{\"card_id\":\"OPxx-xxx 或 STxx-xxx ...\"}。"
    )
    prompt_limited = (
        "你是 One Piece 卡牌识别助手。"
        "请根据图片识别最可能的卡号。"
        f"优先从候选卡号中选择：{candidate_text}。"
        "只返回 JSON：{\"card_id\":\"OPxx-xxx 或 STxx-xxx ...\"}。"
    )
    try:
        if not _ensure_openai() or OpenAI is None:
            raise RuntimeError("OpenAI SDK unavailable")
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=20.0)
        prompts: list[str] = []
        if RECOGNIZE_DEEPSEEK_FREE_MODE:
            prompts.append(prompt_free)
        prompts.append(prompt_limited)
        content = ""
        for p in prompts:
            completion = client.chat.completions.create(
                model=DEEPSEEK_RECOGNIZE_MODEL,
                messages=[
                    {"role": "system", "content": "你是严谨的图像识别助手，只输出 JSON。"},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": p},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        ],
                    },
                ],
                temperature=0,
                max_tokens=120,
            )
            content = completion.choices[0].message.content if completion.choices else ""
            picked = _parse_deepseek_recognize_card_id(str(content or ""))
            if picked:
                return picked
    except Exception:
        return None
    return _parse_deepseek_recognize_card_id(str(content or ""))


def _compute_query_hash_packs_from_bytes(blob: bytes) -> list[dict[str, Any]]:
    if not imagehash or not Image:
        return []
    packs: list[dict[str, Any]] = []
    try:
        from PIL import ImageEnhance, ImageOps

        for base in _extract_card_like_crops_from_blob(blob):
            rgb = base.convert("RGB")
            variants = [rgb]
            # Blur tolerance: contrast/sharpness/autocontrast variants.
            variants.append(ImageEnhance.Contrast(rgb).enhance(1.35))
            variants.append(ImageEnhance.Sharpness(rgb).enhance(1.8))
            variants.append(ImageOps.autocontrast(rgb))
            for im in variants:
                packs.append(_compute_hash_pack_from_image(im))
    except Exception:
        return packs
    return packs


def _compute_hash_pack_from_bytes(blob: bytes) -> dict[str, Any] | None:
    if not imagehash or not Image:
        return None
    try:
        from io import BytesIO

        with Image.open(BytesIO(blob)) as im:
            return _compute_hash_pack_from_image(im)
    except Exception:
        return None


def _compute_hash_pack_from_path(path: Path) -> dict[str, Any] | None:
    if not imagehash or not Image:
        return None
    try:
        with Image.open(path) as im:
            return _compute_hash_pack_from_image(im)
    except Exception:
        return None


def _packs_index_signature() -> dict[str, Any]:
    files = [p for p in PACKS_DIR.glob("*.*") if p.is_file()]
    if not files:
        return {"count": 0, "mtime_ns": 0}
    return {
        "count": len(files),
        "mtime_ns": max(int(p.stat().st_mtime_ns) for p in files),
    }


def _serialize_hash_pack(pack: dict[str, Any]) -> dict[str, Any]:
    return {
        "full_phash": str(pack["full_phash"]),
        "art_phash": str(pack["art_phash"]),
        "art_dhash": str(pack["art_dhash"]),
        "art_hist": list(pack.get("art_hist") or []),
    }


def _deserialize_hash_pack(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not imagehash:
        return None
    try:
        return {
            "full_phash": imagehash.hex_to_hash(str(raw["full_phash"])),
            "art_phash": imagehash.hex_to_hash(str(raw["art_phash"])),
            "art_dhash": imagehash.hex_to_hash(str(raw["art_dhash"])),
            "art_hist": [float(x) for x in (raw.get("art_hist") or [])],
        }
    except Exception:
        return None


def ensure_photo_hash_index() -> None:
    global photo_hash_index, photo_hash_ready
    if photo_hash_ready:
        return
    sig = _packs_index_signature()
    # Try disk cache first.
    try:
        if PHOTO_HASH_INDEX_FILE.exists():
            payload = json.loads(PHOTO_HASH_INDEX_FILE.read_text(encoding="utf-8"))
            cached_sig = payload.get("signature") if isinstance(payload, dict) else None
            items = payload.get("items") if isinstance(payload, dict) else None
            if cached_sig == sig and isinstance(items, dict) and items:
                restored: dict[str, dict[str, Any]] = {}
                for cid, raw in items.items():
                    pack = _deserialize_hash_pack(raw if isinstance(raw, dict) else {})
                    if pack is not None:
                        restored[str(cid)] = pack
                if restored:
                    photo_hash_index = restored
                    photo_hash_ready = True
                    return
    except Exception:
        pass

    index: dict[str, dict[str, Any]] = {}
    for p in sorted(PACKS_DIR.glob("*.*")):
        if not p.is_file():
            continue
        cid = normalize_card_id(p.stem)
        if not cid:
            continue
        pack = _compute_hash_pack_from_path(p)
        if pack is None:
            continue
        if cid not in index:
            index[cid] = pack
    photo_hash_index = index
    photo_hash_ready = True
    try:
        PHOTO_HASH_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        serial = {cid: _serialize_hash_pack(pack) for cid, pack in index.items()}
        PHOTO_HASH_INDEX_FILE.write_text(
            json.dumps({"signature": sig, "items": serial}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def recognize_card_id_from_photo_bytes(blob: bytes) -> tuple[str | None, int | None]:
    ensure_photo_hash_index()
    query_packs = _compute_query_hash_packs_from_bytes(blob)
    if not query_packs:
        single = _compute_hash_pack_from_bytes(blob)
        if single:
            query_packs = [single]
    if not query_packs or not photo_hash_index:
        return None, None
    best_id = None
    best_dist = 10**9
    for cid, h in photo_hash_index.items():
        dist = 10**9
        for q in query_packs:
            try:
                cand = (
                    int(q["art_phash"] - h["art_phash"]) * 4
                    + int(q["art_dhash"] - h["art_dhash"]) * 3
                    + int(q["full_phash"] - h["full_phash"]) * 1
                    + int(_hist_l1_distance(q.get("art_hist") or [], h.get("art_hist") or []) * 1200)
                )
            except Exception:
                continue
            if cand < dist:
                dist = cand
        if dist < best_dist:
            best_dist = dist
            best_id = cid
    if best_id is None:
        return None, None
    return best_id, best_dist


def recognize_top_candidates_from_photo_bytes(blob: bytes, top_k: int = 3) -> list[tuple[str, int]]:
    ensure_photo_hash_index()
    query_packs = _compute_query_hash_packs_from_bytes(blob)
    if not query_packs:
        single = _compute_hash_pack_from_bytes(blob)
        if single:
            query_packs = [single]
    if not query_packs or not photo_hash_index:
        return []
    # Aggregate by base card id to reduce variant-induced confusion.
    base_best: dict[str, int] = {}
    for cid, h in photo_hash_index.items():
        best = 10**9
        for q in query_packs:
            try:
                dist = (
                    int(q["art_phash"] - h["art_phash"]) * 4
                    + int(q["art_dhash"] - h["art_dhash"]) * 3
                    + int(q["full_phash"] - h["full_phash"]) * 1
                    + int(_hist_l1_distance(q.get("art_hist") or [], h.get("art_hist") or []) * 1200)
                )
            except Exception:
                continue
            if dist < best:
                best = dist
        if best < 10**9:
            base_id = _base_card_id(cid)
            prev = base_best.get(base_id)
            if prev is None or best < prev:
                base_best[base_id] = int(best)
    scored = sorted(base_best.items(), key=lambda x: x[1])
    # ORB rerank on top shortlist for better robustness on blur/angle/noise.
    shortlist = scored[: min(len(scored), max(12, top_k * 3))]
    if _ensure_cv_deps() and cv2 is not None and shortlist:
        reranked: list[tuple[str, float, int]] = []
        for cid, dist in shortlist:
            path = _best_local_path_for_card(cid)
            orb = _orb_match_score(blob, path) if path else 0.0
            # Lower combined score is better; strong ORB matches pull candidate up.
            combined = float(dist) - orb * 1.8
            reranked.append((cid, combined, dist))
        reranked.sort(key=lambda x: x[1])
        return [(cid, raw_dist) for cid, _combined, raw_dist in reranked[: max(1, top_k)]]
    return shortlist[: max(1, top_k)]


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            dele = prev[j] + 1
            rep = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, dele, rep))
        prev = cur
    return prev[-1]


def _light_normalize_ocr_id(raw: str) -> str:
    """Light cleanup only — do not remap every letter to a digit."""
    s = str(raw or "").upper().strip()
    s = s.replace(" ", "").replace("_", "-")
    s = re.sub(r"^0P", "OP", s)
    s = re.sub(r"^5T", "ST", s)
    s = re.sub(r"^E8", "EB", s)
    s = re.sub(r"^PR8", "PRB", s)
    s = re.sub(r"^OPD", "OP0", s)
    s = re.sub(r"^OPO", "OP0", s)
    s = re.sub(r"^OP(\d)-", r"OP0\1-", s)
    # OP09001 / OP09-001-X / OP01-016R → OP09-001 / OP01-016
    m = re.fullmatch(r"((?:OP|ST|EB|PRB)\d{2})(\d{3})([A-Z0-9]*)", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.fullmatch(r"((?:OP|ST|EB|PRB)\d{2})-(\d{3})(?:-[A-Z0-9]+)?", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    # OP01-016R (rarity letter glued, no extra hyphen)
    m = re.fullmatch(r"((?:OP|ST|EB|PRB)\d{2})-(\d{3})[A-Z]+", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return s


def _aggressive_normalize_ocr_id(raw: str) -> str:
    """Digit-confusion remap (for near-match generation only, never auto-accept)."""
    s = str(raw or "").upper().strip()
    s = s.replace(" ", "").replace("_", "-")
    s = re.sub(r"^0P", "OP", s)
    s = re.sub(r"^5T", "ST", s)
    s = re.sub(r"^E8", "EB", s)
    s = re.sub(r"^PR8", "PRB", s)
    s = re.sub(r"^OPD", "OP0", s)
    s = re.sub(r"^OPO", "OP0", s)
    m = re.match(r"^((?:OP|ST|EB|PRB))(.+)$", s)
    if not m:
        return _light_normalize_ocr_id(raw)
    prefix, rest = m.group(1), m.group(2)
    rest = rest.translate(str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8"}))
    rest = rest.replace("-", "")
    m2 = re.match(r"^(\d{2})(\d{3})", rest)
    if m2:
        return f"{prefix}{m2.group(1)}-{m2.group(2)}"
    return _light_normalize_ocr_id(prefix + rest)

def _exact_match_known_card_id(norm: str) -> str | None:
    if not norm:
        return None
    if norm in cards_by_id:
        return norm
    base = _base_card_id(norm)
    # Require norm to be base or base + short rarity/print suffix — not arbitrary trailing OCR junk.
    if base in cards_by_id and re.fullmatch(rf"{re.escape(base)}(?:-[A-Z0-9]{{1,6}})?", norm):
        return base
    return None


def _ocr_confusion_variants(base: str) -> list[str]:
    """Generate a few digit-confusion variants for near matching (never auto-accept)."""
    base = _base_card_id(base)
    m = re.fullmatch(r"((?:OP|ST|EB|PRB)\d{2})-(\d{3})", base)
    if not m:
        return [base]
    prefix, num = m.group(1), m.group(2)
    pairs = [("0", "O"), ("1", "I"), ("1", "L"), ("5", "S"), ("8", "B")]
    out = {base}
    # Single-position digit swaps using common OCR confusions.
    for i, ch in enumerate(num):
        for a, b in pairs:
            if ch == a:
                chars = list(num)
                chars[i] = b
                # After swap, aggressive normalize back to digits for lookup.
                cand = _aggressive_normalize_ocr_id(f"{prefix}-{''.join(chars)}")
                out.add(_base_card_id(cand))
            if ch == b:
                chars = list(num)
                chars[i] = a
                cand = f"{prefix}-{''.join(chars)}"
                out.add(_base_card_id(cand))
    return list(out)


def _near_match_known_card_ids(norm: str) -> list[str]:
    """Controlled near matches that exist in the card index (candidates only)."""
    base = _base_card_id(norm)
    hits: list[str] = []
    for cand in _ocr_confusion_variants(base):
        if cand in cards_by_id:
            hits.append(cand)
        else:
            # Also try aggressive form.
            agg = _base_card_id(_aggressive_normalize_ocr_id(cand))
            if agg in cards_by_id:
                hits.append(agg)
    # Same-series levenshtein-1 only when the OCR string itself is unknown and neighbor is unique.
    series = get_series_prefix(base).upper()
    if (
        series
        and base not in cards_by_id
        and re.fullmatch(r"(?:OP|ST|EB|PRB)\d{2}-\d{3}", base)
    ):
        fuzzy: list[str] = []
        for cid in cards_by_id:
            b = _base_card_id(cid)
            if get_series_prefix(b).upper() != series:
                continue
            if len(b) != len(base):
                continue
            if _levenshtein(b, base) == 1:
                fuzzy.append(b)
        fuzzy = list(dict.fromkeys(fuzzy))
        if len(fuzzy) == 1:
            hits.extend(fuzzy)
    return list(dict.fromkeys(hits))


def _collect_ocr_id_candidates_from_text(text_blob: str) -> list[str]:
    text_blob = str(text_blob or "").upper()
    # Allow common OCR letter/digit confusions in the numeric body (O/0, I/1, S/5, B/8).
    # Suffix is optional short print code only (e.g. -P1), not following English words.
    candidates = re.findall(
        r"\b((?:OP|ST|EB|PRB|0P|5T|E8|PR8)\s*[0-9OILSB]{2}\s*[-_ ]?\s*[0-9OILSB]{3}(?:-[A-Z0-9]{1,6})?)\b",
        text_blob,
        flags=re.IGNORECASE,
    )
    compact_blob = re.sub(r"[^A-Z0-9]", "", text_blob)
    candidates += re.findall(r"(?:OP|ST|EB|PRB|0P|5T|E8|PR8)[0-9OILSB]{5}", compact_blob)
    for m in re.finditer(
        r"\b((?:OPD|OPO|OP)\s*[-_ ]?[0-9OILSB]{1,2}\s*[-_ ]?[0-9OILSB]{3,4})\b",
        text_blob,
        flags=re.IGNORECASE,
    ):
        # Keep raw OCR text — remapping happens later in aggressive near-match only.
        candidates.append(str(m.group(1)))
    for m in re.finditer(
        r"\b(EB\s*[-_ ]?[0-9OILSB]{2}\s*[-_ ]?[0-9OILSB]{3,4})\b",
        text_blob,
        flags=re.IGNORECASE,
    ):
        candidates.append(str(m.group(1)))
    return [str(c) for c in candidates]


def extract_card_id_hits_from_ocr_texts(texts: list[str]) -> tuple[str | None, list[str]]:
    """
    Returns (exact_id_or_none, near_match_ids).
    Auto-jump only when exactly one distinct known ID is found via light normalize.
    Aggressive digit remaps are near-matches only (never auto-accept).
    """
    if not texts:
        return None, []
    text_blob = " ".join(str(t) for t in texts)
    exact_hits: list[str] = []
    near: list[str] = []
    for raw in _collect_ocr_id_candidates_from_text(text_blob):
        light = normalize_card_id(_light_normalize_ocr_id(str(raw)))
        hit = _exact_match_known_card_id(light)
        if hit:
            exact_hits.append(_base_card_id(hit))
            continue
        # Aggressive remap → candidates only (O/0, I/1 confusions etc.)
        agg = normalize_card_id(_aggressive_normalize_ocr_id(str(raw)))
        hit_agg = _exact_match_known_card_id(agg)
        if hit_agg:
            near.append(_base_card_id(hit_agg))
        near.extend(_near_match_known_card_ids(light))
        near.extend(_near_match_known_card_ids(agg))
    exact_unique = list(dict.fromkeys(exact_hits))
    # Ambiguous: effect text / multiple OCR reads of different IDs → no auto-jump.
    exact = exact_unique[0] if len(exact_unique) == 1 else None
    if len(exact_unique) > 1:
        near = exact_unique + near
    return exact, list(dict.fromkeys(near))


def extract_card_id_from_ocr_texts(texts: list[str]) -> str | None:
    exact, _near = extract_card_id_hits_from_ocr_texts(texts)
    return exact


def extract_card_id_from_photo_ocr(
    blob: bytes, extra_texts: list[str] | None = None
) -> tuple[str | None, list[str]]:
    """
    OCR card-code extraction.
    Prefer lower-right ID ROI over full-frame OCR (effect text often cites other IDs).
    Returns (exact_id, near_ids). Only exact_id is safe for auto-jump.
    """
    try:
        from PIL import ImageEnhance, ImageOps
    except Exception:
        return extract_card_id_hits_from_ocr_texts(extra_texts or [])

    near: list[str] = []
    exact_extra, near_extra = extract_card_id_hits_from_ocr_texts(extra_texts or [])
    near.extend(near_extra)

    if _get_rapidocr_engine() is None:
        return exact_extra, list(dict.fromkeys(near))

    try:
        base_images = _extract_card_like_crops_from_blob(blob)
        if not base_images:
            from io import BytesIO

            with Image.open(BytesIO(blob)) as im0:
                base_images = [im0.convert("RGB")]
        if len(base_images) > 1:
            base_images = base_images[1:]
    except Exception:
        return exact_extra, list(dict.fromkeys(near))

    variants: list[Any] = []
    for base in base_images[:2]:
        for id_region in _id_roi_crops_from_image(base):
            variants.append(id_region)
            variants.append(ImageOps.autocontrast(id_region))
            variants.append(ImageEnhance.Sharpness(id_region).enhance(2.6))
            variants.append(ImageEnhance.Contrast(id_region).enhance(1.9))
            id_gray = ImageOps.grayscale(id_region)
            for th in (105, 130, 155):
                variants.append(id_gray.point(lambda p, t=th: 255 if p > t else 0).convert("RGB"))
    variants = [v.resize((max(1, v.width * 2), max(1, v.height * 2))) for v in variants]

    raw_hits: list[str] = []
    for img in variants[:24]:
        raw_hits.extend(_run_rapidocr_on_pil(img))
    exact_roi, near_roi = extract_card_id_hits_from_ocr_texts(raw_hits)
    near.extend(near_roi)

    # ID corner wins when present; full-frame exact is fallback only.
    if exact_roi:
        return exact_roi, list(dict.fromkeys(near))
    if exact_extra:
        # Full-frame hit only if ROI near-matches agree or ROI found nothing useful.
        if not near_roi or _base_card_id(exact_extra) in {_base_card_id(x) for x in near_roi}:
            return exact_extra, list(dict.fromkeys(near))
        near = [_base_card_id(exact_extra)] + near
    return None, list(dict.fromkeys(near))


def build_filter_card_response(card_id: str, card_basic: dict[str, Any]) -> FilterCardResponse:
    snapshot_card = _snapshot_to_card_fields(card_id)
    img_url = card_basic.get("img_url") or snapshot_card.get("img_url")
    img_full_url = card_basic.get("img_full_url") or snapshot_card.get("img_full_url")
    local_img_url = local_image_url_map.get(normalize_card_id(card_id))
    if not img_full_url and local_img_url:
        img_full_url = local_img_url
    if not img_url and local_img_url:
        img_url = local_img_url
    img_full_url = normalize_official_image_url(img_full_url) or img_full_url
    if isinstance(img_url, str) and img_url.strip().startswith("../images/"):
        rewritten = normalize_official_image_url(img_url)
        if rewritten and rewritten.startswith("http"):
            img_full_url = img_full_url or rewritten
    if not local_img_url:
        local_img_url = card_image_proxy_url(card_id)
    cost = _zero_cost_if_event_or_stage(
        card_basic.get("category") or snapshot_card.get("category"),
        _first_int(card_basic.get("cost"), snapshot_card.get("cost")),
    )
    power = _to_int(card_basic.get("power"))
    if power is None:
        power = _to_int(snapshot_card.get("power"))
    counter = _to_int(card_basic.get("counter"))
    if counter is None:
        counter = _to_int(snapshot_card.get("counter"))
    block_number = _to_int(card_basic.get("block_number"))
    if block_number is None:
        block_number = _to_int(snapshot_card.get("block_number"))
    attrs = resolve_card_attributes(card_basic if isinstance(card_basic, dict) else {})
    if not attrs:
        attrs = (
            [str(x).strip() for x in (card_basic.get("attributes") or []) if str(x).strip()]
            or [str(x).strip() for x in (snapshot_card.get("attributes") or []) if str(x).strip()]
            or [str(x).strip() for x in str(card_basic.get("attribute") or "").split("/") if str(x).strip()]
        )
        attrs = normalize_attributes(attrs)
    return FilterCardResponse(
        id=card_id,
        name=card_basic.get("name") or snapshot_card.get("name"),
        name_en=card_basic.get("name_en") or snapshot_card.get("name_en"),
        rarity=normalize_rarity(
            card_basic.get("rarity") or snapshot_card.get("rarity")
        )
        or None,
        colors=(card_basic.get("colors") or snapshot_card.get("colors") or []),
        cost=cost,
        power=power,
        counter=counter,
        card_type=card_basic.get("category") or snapshot_card.get("category"),
        block_number=block_number,
        attributes=attrs,
        img_url=img_url,
        img_full_url=img_full_url,
        img_local_url=local_img_url,
    )


def load_cards_index() -> None:
    global cards_by_id
    if not INDEX_PATH.exists():
        raise RuntimeError(f"cards_by_id.json not found: {INDEX_PATH}")

    with INDEX_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise RuntimeError("cards_by_id.json must be a JSON object (dict)")

    normalized_map: dict[str, dict[str, Any]] = {}
    for raw_id, card in data.items():
        norm_id = normalize_card_id(str(raw_id))
        if not norm_id:
            continue
        if isinstance(card, dict):
            rarity = normalize_rarity(card.get("rarity"))
            if rarity and card.get("rarity") != rarity:
                card = dict(card)
                card["rarity"] = rarity
            normalized_map[norm_id] = card
        else:
            normalized_map[norm_id] = {}
    cards_by_id = normalized_map
    rebuild_variant_id_map()
    load_name_hans_by_en()
    load_name_aliases()
    rebuild_card_search_index()
    rebuild_leader_name_index()


def _read_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_pack_data(pack_id: str) -> Any | None:
    if pack_id in pack_cache:
        return pack_cache[pack_id]

    candidate_files = [
        CARDS_DIR / f"{pack_id}.json",
        CARDS_DIR / "cards" / f"{pack_id}.json",
    ]

    for candidate in candidate_files:
        if candidate.exists():
            data = _read_json_file(candidate)
            pack_cache[pack_id] = data
            return data

    pack_folder = CARDS_DIR / "cards" / pack_id
    if pack_folder.exists() and pack_folder.is_dir():
        merged: dict[str, dict[str, Any]] = {}
        for file_path in pack_folder.glob("*.json"):
            try:
                card_data = _read_json_file(file_path)
            except Exception:
                continue

            if not isinstance(card_data, dict):
                continue

            card_id = str(card_data.get("id") or file_path.stem)
            merged[card_id.upper()] = card_data

        pack_cache[pack_id] = merged
        return merged

    return None


def extract_extra_from_pack(
    pack_data: Any, card_id: str
) -> tuple[str | None, int | str | None]:
    normalized_id = card_id.upper()

    if isinstance(pack_data, dict):
        if normalized_id in pack_data and isinstance(pack_data[normalized_id], dict):
            card = pack_data[normalized_id]
            return card.get("effect"), card.get("power")

        # pack json might directly contain one card object
        if "id" in pack_data and str(pack_data.get("id", "")).upper() == normalized_id:
            return pack_data.get("effect"), pack_data.get("power")

    if isinstance(pack_data, list):
        for item in pack_data:
            if not isinstance(item, dict):
                continue
            if str(item.get("id", "")).upper() == normalized_id:
                return item.get("effect"), item.get("power")

    return None, None


def extract_card_from_pack(pack_data: Any, card_id: str) -> dict[str, Any] | None:
    normalized_id = card_id.upper()

    if isinstance(pack_data, dict):
        if normalized_id in pack_data and isinstance(pack_data[normalized_id], dict):
            return pack_data[normalized_id]
        if "id" in pack_data and str(pack_data.get("id", "")).upper() == normalized_id:
            return pack_data

    if isinstance(pack_data, list):
        for item in pack_data:
            if not isinstance(item, dict):
                continue
            if str(item.get("id", "")).upper() == normalized_id:
                return item

    return None


@app.on_event("startup")
def startup_event() -> None:
    # Validate early so configuration issues are found at startup.
    get_api_key()
    load_official_rules_context()
    load_tournament_meta_context()
    load_card_cooccurrence()
    load_market_price_data()
    load_topdecks_data()
    topdecks_likes.init_topdecks_likes_db()
    card_comments.init_card_comments_db()
    load_official_snapshot_data()
    load_cached_attribute_map()
    load_cards_index()
    rebuild_local_image_url_map()
    rebuild_filter_index()
    # Warm photo hash index in background (loads from disk cache when available).
    threading.Thread(target=ensure_photo_hash_index, daemon=True).start()
    if CLIP_PREWARM_ON_STARTUP and RECOGNIZE_USE_CLIP:
        # Warm CLIP index in background to avoid first-user latency spike.
        threading.Thread(target=ensure_clip_index, daemon=True).start()
    load_ai_advice_cache_from_disk()
    _init_auth_db()
    try:
        from analytics import init_analytics_db

        init_analytics_db()
    except Exception as exc:
        print(f"[warn] analytics db init failed: {exc}")
    try:
        from forum import init_forum_db

        init_forum_db()
    except Exception as exc:
        print(f"[warn] forum db init failed: {exc}")


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "请求参数校验失败，请检查 card_id 是否正确。",
            "path": str(request.url.path),
            "detail": exc.errors(),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler_zh(
    request: Request, exc: HTTPException
) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "请求处理失败。"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "请求处理失败",
            "path": str(request.url.path),
            "detail": detail,
        },
    )


@app.get("/")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "message": "OPCG API 运行正常",
        "opencc": bool(_opencc_s2t and _opencc_t2s),
        "priced_count": _count_visible_priced_entries(),
        "price_entries": len(market_price_map),
        "price_updated_at": market_price_updated_at or None,
    }


def _client_ip(request: Request) -> str:
    xff = str(request.headers.get("x-forwarded-for") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    xri = str(request.headers.get("x-real-ip") or "").strip()
    if xri:
        return xri
    if request.client and request.client.host:
        return str(request.client.host)
    return ""


@app.post("/analytics/event")
def analytics_event(body: AnalyticsEventIn, request: Request) -> dict[str, Any]:
    """Lightweight pageview beacon from the Next.js frontend."""
    try:
        from analytics import analytics_enabled, insert_pageview
    except Exception as exc:
        return {"ok": False, "error": f"analytics unavailable: {exc}"}
    if not analytics_enabled():
        return {"ok": True, "skipped": True}

    user_id: int | None = None
    username: str | None = None
    row = _read_auth_user_from_request(request)
    if row is not None:
        try:
            user_id = int(row["id"])
        except (TypeError, ValueError, KeyError):
            user_id = None
        username = str(row["username"] or "") or None

    try:
        result = insert_pageview(
            path=str(body.path or "/"),
            visitor_id=str(body.visitor_id or ""),
            session_id=str(body.session_id or ""),
            referrer=body.referrer,
            user_id=user_id,
            username=username,
            ip=_client_ip(request),
            user_agent=str(request.headers.get("user-agent") or ""),
            language=body.language,
            screen=body.screen,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        print(f"[analytics] insert failed: {exc}")
        return {"ok": False, "error": "insert failed"}

    return {
        "ok": True,
        "is_excluded": bool(result.get("is_excluded")),
        # Echo ids so the owner can copy into ANALYTICS_EXCLUDE_* after testing.
        "visitor_id": result.get("visitor_id"),
        "ip_hash": result.get("ip_hash"),
    }


@app.post("/analytics/ai-crawl")
def analytics_ai_crawl(body: AnalyticsAiCrawlIn, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Log GPTBot / citation crawlers. Failures are dropped; never block the site."""
    bot = str(body.bot or "").strip()[:64]
    if bot not in _AI_CRAWL_BOTS:
        return {"ok": False, "skipped": True}
    path = str(body.path or "/").strip()[:300] or "/"

    def _write() -> None:
        try:
            from analytics import analytics_enabled, insert_ai_crawl

            if not analytics_enabled():
                return
            insert_ai_crawl(bot=bot, path=path)
        except Exception:
            return

    background_tasks.add_task(_write)
    return {"ok": True}


@app.get("/analytics/report/preview")
def analytics_report_preview(
    request: Request,
    day: str | None = Query(default=None, description="HKT day YYYY-MM-DD"),
) -> dict[str, Any]:
    """Preview daily report. Requires ANALYTICS_ADMIN_TOKEN header/query."""
    token = str(
        request.headers.get("x-analytics-token")
        or request.query_params.get("token")
        or ""
    ).strip()
    expected = str(os.getenv("ANALYTICS_ADMIN_TOKEN") or "").strip()
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    from analytics.report import build_daily_report
    from datetime import date as date_cls

    d = date_cls.fromisoformat(day) if day else None
    subject, body = build_daily_report(d)
    return {"subject": subject, "body": body}


@app.post("/auth/register")
def auth_register(payload: RegisterRequest) -> dict[str, Any]:
    email = _normalize_email(payload.email)
    username = _normalize_username(payload.username)
    password = str(payload.password or "")
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="请输入有效邮箱。")
    if not username or len(username) < 3:
        raise HTTPException(status_code=422, detail="用户名至少 3 位（英文/数字/下划线）。")
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="密码至少 8 位。")
    now = now_iso()
    with auth_db_lock:
        conn = _auth_db()
        try:
            exists_email = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
            if exists_email:
                raise HTTPException(status_code=400, detail="邮箱已被注册。")
            exists_username = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
            if exists_username:
                raise HTTPException(status_code=400, detail="用户名已存在。")
            cur = conn.execute(
                """
                INSERT INTO users (email, username, password_hash, email_verified, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (email, username, _make_password_hash(password), now, now),
            )
            _ = int(cur.lastrowid)
            conn.commit()
        finally:
            conn.close()
    return {"status": "ok", "message": "注册成功。"}


@app.get("/auth/verify-email")
def auth_verify_email(token: str = Query(..., description="邮箱验证 token")) -> dict[str, str]:
    t = str(token or "").strip()
    if not t:
        raise HTTPException(status_code=422, detail="token 不能为空。")
    with auth_db_lock:
        conn = _auth_db()
        try:
            row = conn.execute(
                "SELECT token, user_id, expires_at, used_at FROM email_verify_tokens WHERE token = ?",
                (t,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=400, detail="验证链接无效。")
            if row["used_at"] is not None:
                return {"status": "ok", "message": "邮箱已验证。"}
            exp = _parse_iso_dt(row["expires_at"])
            if exp is None or exp <= datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="验证链接已过期。")
            now = now_iso()
            conn.execute("UPDATE users SET email_verified = 1, updated_at = ? WHERE id = ?", (now, int(row["user_id"])))
            conn.execute("UPDATE email_verify_tokens SET used_at = ? WHERE token = ?", (now, t))
            conn.commit()
        finally:
            conn.close()
    return {"status": "ok", "message": "邮箱验证成功。"}


@app.post("/auth/forgot-password")
def auth_forgot_password(payload: ForgotPasswordRequest) -> dict[str, str]:
    """发送重置密码邮件。无论邮箱是否存在，均返回相同提示，避免枚举账号。"""
    email = _normalize_email(payload.email)
    generic = {"status": "ok", "message": "若该邮箱已注册，重置链接已发送，请查收邮件。"}
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="请输入有效邮箱。")
    with auth_db_lock:
        conn = _auth_db()
        try:
            row = conn.execute(
                "SELECT id, email, username FROM users WHERE email = ? LIMIT 1",
                (email,),
            ).fetchone()
            if row is None:
                print(f"[auth] forgot-password: no account for {_mask_email(email)}")
                return generic
            token = secrets.token_urlsafe(36)
            expires = (
                datetime.now(timezone.utc) + timedelta(hours=AUTH_RESET_TOKEN_HOURS)
            ).replace(microsecond=0).isoformat()
            now = now_iso()
            # Invalidate unused prior tokens for this user.
            conn.execute(
                """
                UPDATE password_reset_tokens
                SET used_at = ?
                WHERE user_id = ? AND used_at IS NULL
                """,
                (now, int(row["id"])),
            )
            conn.execute(
                """
                INSERT INTO password_reset_tokens (token, user_id, expires_at, used_at, created_at)
                VALUES (?, ?, ?, NULL, ?)
                """,
                (token, int(row["id"]), expires, now),
            )
            conn.commit()
            username = str(row["username"])
            to_email = str(row["email"])
        finally:
            conn.close()
    reset_url = f"{_frontend_site_url()}/reset-password?token={token}"
    try:
        _send_reset_password_email(to_email, username, reset_url)
        print(f"[auth] forgot-password: sent reset to {_mask_email(to_email)}")
    except Exception as exc:
        print(f"[auth] reset email failed for {_mask_email(to_email)}: {exc}")
        print(f"[auth] operator reset URL: {reset_url}")
        raise HTTPException(
            status_code=500,
            detail="发送邮件失败。请稍后重试，或联系站长代为重置。",
        ) from exc
    return generic


@app.post("/auth/reset-password")
def auth_reset_password(payload: ResetPasswordRequest) -> dict[str, str]:
    token = str(payload.token or "").strip()
    password = str(payload.password or "")
    if not token:
        raise HTTPException(status_code=422, detail="重置链接无效。")
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="密码至少 8 位。")
    with auth_db_lock:
        conn = _auth_db()
        try:
            row = conn.execute(
                """
                SELECT token, user_id, expires_at, used_at
                FROM password_reset_tokens
                WHERE token = ?
                """,
                (token,),
            ).fetchone()
            if row is None or row["used_at"] is not None:
                raise HTTPException(status_code=400, detail="重置链接无效或已使用。")
            exp = _parse_iso_dt(row["expires_at"])
            if exp is None or exp <= datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="重置链接已过期，请重新申请。")
            now = now_iso()
            user_id = int(row["user_id"])
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (_make_password_hash(password), now, user_id),
            )
            conn.execute(
                "UPDATE password_reset_tokens SET used_at = ? WHERE token = ?",
                (now, token),
            )
            conn.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (now, user_id),
            )
            conn.commit()
        finally:
            conn.close()
    return {"status": "ok", "message": "密码已重置，请使用新密码登录。"}


@app.post("/auth/login", response_model=LoginResponse)
def auth_login(payload: LoginRequest) -> LoginResponse:
    login = str(payload.login or "").strip().lower()
    password = str(payload.password or "")
    if not login or not password:
        raise HTTPException(status_code=422, detail="请输入账号与密码。")
    with auth_db_lock:
        conn = _auth_db()
        try:
            row = conn.execute(
                """
                SELECT * FROM users
                WHERE email = ? OR username = ?
                LIMIT 1
                """,
                (_normalize_email(login), _normalize_username(login)),
            ).fetchone()
            if row is None or not _verify_password(password, str(row["password_hash"])):
                found = "yes" if row is not None else "no"
                print(f"[auth] login failed login={login!r} user_found={found}")
                raise HTTPException(status_code=401, detail="账号或密码错误。")
            token = secrets.token_urlsafe(36)
            expires = (datetime.now(timezone.utc) + timedelta(days=AUTH_SESSION_DAYS)).isoformat()
            conn.execute(
                """
                INSERT INTO auth_sessions (token, user_id, expires_at, revoked_at, created_at)
                VALUES (?, ?, ?, NULL, ?)
                """,
                (token, int(row["id"]), expires, now_iso()),
            )
            conn.commit()
        finally:
            conn.close()
    return LoginResponse(
        token=token,
        username=str(row["username"]),
        email=str(row["email"]),
        email_verified=bool(int(row["email_verified"] or 0)),
    )


@app.get("/auth/me", response_model=MeResponse)
def auth_me(request: Request) -> MeResponse:
    row = _require_auth_user(request)
    try:
        is_admin = bool(int(row["is_admin"] or 0))
    except (KeyError, TypeError, ValueError, IndexError):
        is_admin = False
    return MeResponse(
        username=str(row["username"]),
        email=str(row["email"]),
        email_verified=bool(int(row["email_verified"] or 0)),
        is_admin=is_admin,
    )


@app.get("/packs/{filename}")
def get_pack_image(filename: str) -> Response:
    """Serve local pack images with a fully buffered body.

    Starlette StaticFiles can raise LocalProtocolError (Content-Length mismatch)
    when many card-wall requests hit the same files concurrently.
    """
    safe_name = Path(str(filename or "")).name
    if not safe_name or safe_name != filename:
        raise HTTPException(status_code=404, detail="image not found")
    if Path(safe_name).suffix.lower() not in _PACK_MANIFEST_IMAGE_EXTS:
        raise HTTPException(status_code=404, detail="image not found")
    fp = (PACKS_DIR / safe_name).resolve()
    try:
        packs_root = PACKS_DIR.resolve()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"packs dir error: {exc}") from exc
    if packs_root not in fp.parents and fp != packs_root:
        raise HTTPException(status_code=404, detail="image not found")
    if not fp.is_file():
        raise HTTPException(status_code=404, detail="image not found")
    try:
        data = fp.read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"read image failed: {exc}") from exc
    return Response(
        content=data,
        media_type=_guess_image_media_type(fp),
        headers={
            "Cache-Control": "public, max-age=604800",
            "ETag": f'"{hashlib.md5(data).hexdigest()}"',
        },
    )


@app.get("/images/card/{card_id}")
def get_card_image_proxy(card_id: str) -> Response:
    """代理官方卡图：浏览器无法跨站加载 one-piece-cardgame.com（CORP same-site）。"""
    card_key = normalize_card_id(card_id)
    if not card_key:
        raise HTTPException(status_code=422, detail="card_id 无效")
    basic = cards_by_id.get(card_key)
    if not basic:
        raise HTTPException(status_code=404, detail="card not found")

    # Buffer local files instead of streaming FileResponse.
    # Under concurrent card-wall loads, streamed FileResponse can drop mid-transfer.
    for fp in PACKS_DIR.glob(f"{card_key}.*"):
        if fp.is_file() and fp.suffix.lower() in _PACK_MANIFEST_IMAGE_EXTS:
            try:
                data = fp.read_bytes()
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f"read image failed: {exc}") from exc
            return Response(
                content=data,
                media_type=_guess_image_media_type(fp),
                headers={"Cache-Control": "public, max-age=604800"},
            )

    img_full = normalize_official_image_url(basic.get("img_full_url"))
    img_url = basic.get("img_url")
    cached = _download_card_image_to_packs(card_key, img_full, img_url)
    if cached:
        try:
            data = cached.read_bytes()
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"read image failed: {exc}") from exc
        return Response(
            content=data,
            media_type=_guess_image_media_type(cached),
            headers={"Cache-Control": "public, max-age=604800"},
        )

    for candidate in _build_official_image_candidates(img_full, img_url):
        try:
            resp = requests.get(
                candidate,
                timeout=IMAGE_FETCH_TIMEOUT_SEC,
                headers={
                    "User-Agent": "Mozilla/5.0 OPCG-API/1.0",
                    "Referer": OFFICIAL_IMAGE_HOSTS[0],
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                },
            )
        except requests.RequestException:
            continue
        content_type = resp.headers.get("content-type", "").lower()
        if resp.status_code != 200 or "image" not in content_type:
            continue
        return Response(
            content=resp.content,
            media_type=content_type.split(";", 1)[0],
            headers={"Cache-Control": "public, max-age=86400"},
        )

    raise HTTPException(status_code=404, detail="card image not found")


def _fast_deck_stat_fields(normalized_id: str) -> dict[str, Any] | None:
    """卡组统计用轻量字段（类型/费用/反击/力量/名称/颜色/稀有度），不走 CardResponse / AI。

    异图卡（-P1/-R1 等）索引里常缺 cost；自动回退到基础卡号补齐。
    """
    nid = normalize_card_id(normalized_id)
    basic = cards_by_id.get(nid)
    if not basic:
        return None

    def _pick_fields(card_id: str, card_basic: dict[str, Any]) -> dict[str, Any]:
        cached = card_analysis_cache.get(card_id) if isinstance(card_analysis_cache.get(card_id), dict) else {}
        fields = {
            "card_type": cached.get("card_type"),
            "cost": cached.get("cost"),
            "counter": cached.get("counter"),
            "power": cached.get("power"),
        }
        missing = any(fields.get(key) is None or fields.get(key) == "" for key in ("card_type", "cost", "counter", "power"))
        if missing:
            full_card: dict[str, Any] = {}
            pack_id = card_basic.get("pack_id")
            if pack_id:
                pack_data = load_pack_data(str(pack_id))
                if pack_data is not None:
                    full_card = extract_card_from_pack(pack_data, card_id) or {}
            pack_fields = {
                "card_type": str(full_card.get("category") or card_basic.get("category") or "").lower(),
                "cost": full_card.get("cost") if full_card.get("cost") is not None else card_basic.get("cost"),
                "counter": full_card.get("counter") if full_card.get("counter") is not None else card_basic.get("counter"),
                "power": full_card.get("power") if full_card.get("power") is not None else card_basic.get("power"),
            }
            for key in ("card_type", "cost", "counter", "power"):
                if fields.get(key) is None or fields.get(key) == "":
                    if pack_fields.get(key) is not None and pack_fields.get(key) != "":
                        fields[key] = pack_fields[key]
        return fields

    fields = _pick_fields(nid, basic)
    base_id = _base_card_id(nid)
    if base_id and base_id != nid:
        base_basic = cards_by_id.get(base_id)
        if isinstance(base_basic, dict):
            base_fields = _pick_fields(base_id, base_basic)
            for key in ("card_type", "cost", "counter", "power"):
                if fields.get(key) is None or fields.get(key) == "":
                    if base_fields.get(key) is not None and base_fields.get(key) != "":
                        fields[key] = base_fields.get(key)

    name = str(basic.get("name") or "").strip() or None
    name_en = str(basic.get("name_en") or "").strip() or None
    rarity = normalize_rarity(basic.get("rarity")) or None
    colors = basic.get("colors") if isinstance(basic.get("colors"), list) else []
    if not colors and base_id and base_id != nid:
        base_basic = cards_by_id.get(base_id) or {}
        if isinstance(base_basic.get("colors"), list):
            colors = base_basic.get("colors") or []
        if not rarity:
            rarity = normalize_rarity(base_basic.get("rarity")) or None

    card_type = fields.get("card_type") or basic.get("category")
    return {
        "card_type": fields.get("card_type"),
        "cost": _zero_cost_if_event_or_stage(card_type, _to_int(fields.get("cost"))),
        "counter": _to_int(fields.get("counter")),
        "power": fields.get("power"),
        "name": name,
        "name_en": name_en,
        "colors": colors,
        "rarity": rarity_match_key(rarity) or None,
        # Pre-normalized blob (name TW/Hans/EN + traits) for collection/binder search.
        "search_blob": card_search_norm_by_id.get(nid) or build_card_search_blob(basic),
    }


@app.post("/cards/thumbnails/batch")
def batch_card_thumbnail_urls(payload: CardThumbnailBatchRequest) -> dict[str, str]:
    """侧栏多张卡预览：仅从索引与 local_image_url_map 解析 URL，不走完整 CardResponse。"""
    out: dict[str, str] = {}
    incoming = payload.ids if isinstance(payload.ids, list) else []
    for raw in incoming[:420]:
        nid = normalize_card_id(str(raw).strip())
        if not nid:
            continue
        if nid in out:
            continue
        if nid not in cards_by_id:
            continue
        url = _fast_thumbnail_url(nid)
        if url:
            out[nid] = url
    return out


@app.post("/cards/deck-stats/batch")
def batch_card_deck_stats(payload: CardThumbnailBatchRequest) -> dict[str, dict[str, Any]]:
    """卡组详情统计：批量返回类型/费用/反击/力量/稀有度，避免前端逐张 GET /cards/{id}。"""
    out: dict[str, dict[str, Any]] = {}
    incoming = payload.ids if isinstance(payload.ids, list) else []
    for raw in incoming[:420]:
        nid = normalize_card_id(str(raw).strip())
        if not nid or nid in out:
            continue
        fields = _fast_deck_stat_fields(nid)
        if fields:
            out[nid] = fields
    return out


@app.get("/cards/{card_id}", response_model=CardWithAIResponse)
def get_card(
    card_id: str,
    include_ai: bool = Query(False),
    include_evidence: bool = Query(False),
) -> CardWithAIResponse:
    normalized_id = normalize_card_id(card_id)
    if not normalized_id:
        raise HTTPException(status_code=422, detail="card_id 不能为空，请输入如 ST01-004。")

    card_basic = cards_by_id.get(normalized_id)

    if not card_basic:
        raise HTTPException(
            status_code=404,
            detail=f"未找到卡号 {normalized_id}。请确认格式，如 ST01-004。",
        )

    card_data = build_card_response(normalized_id, card_basic)
    evidence = build_meta_evidence(normalized_id, card_data.colors) if include_evidence else None
    if not include_ai:
        return CardWithAIResponse(card=card_data, meta_evidence=evidence)
    try:
        advice = ask_ai_for_combo(
            normalized_id,
            card_data.name or normalized_id,
            card_data.effect,
            card_data.colors,
            card_data.card_type,
            card_data.cost,
            card_data.power,
            True,
        )
        advice = enforce_same_series(advice, normalized_id)
        return CardWithAIResponse(card=card_data, ai_advice=advice, meta_evidence=evidence)
    except Exception as exc:
        # AI 失败时仍返回基础数据，避免主查询不可用。
        return CardWithAIResponse(
            card=card_data,
            ai_error=f"AI 建议生成失败：{exc}",
            meta_evidence=evidence,
        )


@app.get("/cards/{card_id}/brief", response_model=CardResponse)
def get_card_brief(card_id: str) -> CardResponse:
    """Lightweight card text for in-battle detail (no image download / market)."""
    normalized_id = normalize_card_id(card_id)
    if not normalized_id:
        raise HTTPException(status_code=422, detail="card_id 不能为空，请输入如 ST01-004。")
    card_basic = cards_by_id.get(normalized_id)
    if not card_basic:
        raise HTTPException(
            status_code=404,
            detail=f"未找到卡号 {normalized_id}。请确认格式，如 ST01-004。",
        )
    return build_card_brief(normalized_id, card_basic)


@app.get("/search", response_model=list[CardResponse])
def search_cards_by_name(
    name: str = Query(..., description="输入想搜索的卡名关键字，例如：路飞、魯夫、Luffy")
) -> list[CardResponse]:
    keyword = str(name or "").strip()
    if not keyword:
        raise HTTPException(status_code=422, detail="搜索关键字不能为空。")

    results: list[CardResponse] = []
    q_norms = expand_query_match_norms(keyword)
    for card_id, card_basic in cards_by_id.items():
        card_name = str(card_basic.get("name") or "")
        card_name_en = str(card_basic.get("name_en") or "")
        if card_matches_text_query(
            card_id, card_name, keyword, name_en=card_name_en or None, query_norms=q_norms
        ):
            results.append(build_card_response(card_id, card_basic))

    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"没有找到名称包含“{name.strip()}”的卡牌。",
        )

    return results[:20]


@app.get("/cards/filter", response_model=list[FilterCardResponse])
def filter_cards(
    response: Response,
    color: str | None = Query(None, description="颜色，例如 Red/Blue/Green/Purple/Black/Yellow"),
    colors: str | None = Query(None, description="多颜色，逗号分隔，例如 Red,Yellow"),
    cost: int | None = Query(None, ge=0, le=20),
    costs: str | None = Query(None, description="多费用，逗号分隔，例如 1,3,5"),
    counter: int | None = Query(None, ge=0, le=5000),
    counters: str | None = Query(None, description="多反击值，逗号分隔，例如 0,1000,2000"),
    power: int | None = Query(None, ge=0, le=20000),
    powers: str | None = Query(None, description="多战力，逗号分隔，例如 3000,5000"),
    card_type: str | None = Query(None, description="Leader/Character/Event/Stage/Don"),
    card_types: str | None = Query(None, description="多类型，逗号分隔，例如 Leader,Character"),
    attribute: str | None = Query(None, description="Strike/Slash/Special/Ranged/Wisdom"),
    attributes: str | None = Query(None, description="多属性，逗号分隔，例如 Strike,Slash"),
    series: str | None = Query(None, description="系列，例如 OP15/ST30/EB01"),
    serieses: str | None = Query(None, description="多系列，逗号分隔，例如 OP15,ST30"),
    rarity: str | None = Query(None, description="稀有度，例如 C/UC/R/SR/SEC/L"),
    rarities: str | None = Query(None, description="多稀有度，逗号分隔，例如 SR,R"),
    block: int | None = Query(None, ge=0, le=50),
    blocks: str | None = Query(None, description="多 block，逗号分隔，例如 1,2,3"),
    keyword: str | None = Query(None, description="效果关键字，例如 blocker/rush/don_x1"),
    keywords: str | None = Query(None, description="多效果关键字，逗号分隔，例如 blocker,rush,don_x1"),
    q: str | None = Query(None, description="卡号或卡名关键字（即时搜索）"),
    price_min: int | None = Query(None, ge=0, description="最低市价（日元）"),
    price_max: int | None = Query(None, ge=0, description="最高市价（日元）"),
    sort: str | None = Query(None, description="排序：id|price_desc|price_asc"),
    priced_only: bool = Query(False, description="仅返回有报价的卡"),
    offset: int = Query(0, ge=0),
    limit: int = Query(70, ge=1, le=300),
) -> list[FilterCardResponse]:
    requested_colors: set[str] = set()
    if color:
        requested_colors.add(normalize_color_token(color))
    if colors:
        for token in str(colors).split(","):
            norm = normalize_color_token(token)
            if norm:
                requested_colors.add(norm)
    requested_costs: set[int] = set()
    if cost is not None:
        requested_costs.add(cost)
    if costs:
        for token in str(costs).split(","):
            val = _to_int(token)
            if val is not None:
                requested_costs.add(val)
    requested_counters: set[int] = set()
    if counter is not None:
        requested_counters.add(counter)
    if counters:
        for token in str(counters).split(","):
            val = _to_int(token)
            if val is not None:
                requested_counters.add(val)
    requested_powers: set[int] = set()
    if power is not None:
        requested_powers.add(power)
    if powers:
        for token in str(powers).split(","):
            val = _to_int(token)
            if val is not None:
                requested_powers.add(val)
    requested_types: set[str] = set()
    if card_type:
        requested_types.add(str(card_type).strip().lower())
    if card_types:
        for token in str(card_types).split(","):
            t = str(token).strip().lower()
            if t:
                requested_types.add(t)
    requested_attrs: set[str] = set()
    if attribute:
        requested_attrs.add(str(attribute).strip().lower())
    if attributes:
        for token in str(attributes).split(","):
            a = str(token).strip().lower()
            if a:
                requested_attrs.add(a)
    requested_series: set[str] = set()
    if series:
        s = str(series).strip().upper()
        if s:
            requested_series.add(s)
    if serieses:
        for token in str(serieses).split(","):
            s = str(token).strip().upper()
            if s:
                requested_series.add(s)
    requested_rarities: set[str] = set()
    if rarity:
        r = rarity_match_key(rarity)
        if r:
            requested_rarities.add(r)
    if rarities:
        for token in str(rarities).split(","):
            r = rarity_match_key(token)
            if r:
                requested_rarities.add(r)
    requested_blocks: set[int] = set()
    if block is not None:
        requested_blocks.add(block)
    if blocks:
        for token in str(blocks).split(","):
            b = _to_int(token)
            if b is not None:
                requested_blocks.add(b)
    allowed_keywords = set(FILTER_KEYWORD_IDS)
    requested_keywords: set[str] = set()
    if keyword:
        k = str(keyword).strip().lower()
        if k in allowed_keywords:
            requested_keywords.add(k)
    if keywords:
        for token in str(keywords).split(","):
            k = str(token).strip().lower()
            if k in allowed_keywords:
                requested_keywords.add(k)

    matched: list[FilterCardResponse] = []
    q_text = str(q or "").strip()
    q_norms = expand_query_match_norms(q_text) if q_text else []
    index_rows = filter_index
    index_presorted = bool(index_rows)
    if not index_rows:
        # Fallback if index not warmed (should not happen after startup).
        index_presorted = False
        built: list[FilterIndexEntry] = []
        for cid, basic in cards_by_id.items():
            basic_dict = basic if isinstance(basic, dict) else {}
            resp = build_filter_card_response(cid, basic_dict)
            built.append(
                FilterIndexEntry(
                    id=str(resp.id),
                    sort_key=card_id_sort_key(resp.id),
                    colors=frozenset(expand_color_tokens(resp.colors or [])),
                    card_type=str(resp.card_type or "").strip().lower(),
                    attrs=frozenset(
                        str(a).strip().lower() for a in (resp.attributes or []) if str(a).strip()
                    ),
                    series=infer_series_from_card_id(str(resp.id)),
                    rarity=rarity_match_key(resp.rarity),
                    block=_to_int(resp.block_number),
                    cost=_to_int(resp.cost),
                    counter=_to_int(resp.counter),
                    power=_to_int(resp.power),
                    keywords=card_filter_keywords(cid, basic_dict),
                    name=str(resp.name or ""),
                    name_en=str(resp.name_en or ""),
                    response=resp,
                )
            )
        index_rows = built

    for row in index_rows:
        if requested_colors and row.colors.isdisjoint(requested_colors):
            continue
        if requested_types and row.card_type not in requested_types:
            continue
        if requested_attrs and row.attrs.isdisjoint(requested_attrs):
            continue
        if requested_series and row.series not in requested_series:
            continue
        if requested_rarities and row.rarity not in requested_rarities:
            continue
        if requested_blocks and row.block not in requested_blocks:
            continue
        if requested_costs and row.cost not in requested_costs:
            continue
        if requested_counters and row.counter not in requested_counters:
            continue
        if requested_powers and row.power not in requested_powers:
            continue
        if requested_keywords and row.keywords.isdisjoint(requested_keywords):
            continue
        if q_text and not card_matches_text_query(
            row.id,
            row.name,
            q_text,
            name_en=row.name_en or None,
            query_norms=q_norms,
        ):
            continue
        matched.append(row.response)

    sort_mode = str(sort or "id").strip().lower()
    need_price = (
        price_min is not None
        or price_max is not None
        or priced_only
        or sort_mode in {"price_desc", "price_asc"}
    )
    price_by_id: dict[str, int | None] = {}

    def _price_of(cid: str) -> int | None:
        if cid in price_by_id:
            return price_by_id[cid]
        info = get_market_price_info(cid, exact=False)
        raw = info.get("current_price") if isinstance(info, dict) else None
        try:
            n = int(raw) if raw is not None else None
        except (TypeError, ValueError):
            n = None
        if n is not None and n <= 0:
            n = None
        price_by_id[cid] = n
        return n

    if need_price:
        priced_matched: list[FilterCardResponse] = []
        for card in matched:
            p = _price_of(str(card.id))
            if priced_only and p is None:
                continue
            if price_min is not None and (p is None or p < price_min):
                continue
            if price_max is not None and (p is None or p > price_max):
                continue
            priced_matched.append(card)
        matched = priced_matched

    if sort_mode == "price_desc":
        matched.sort(
            key=lambda x: (
                0 if _price_of(str(x.id)) is not None else 1,
                -(_price_of(str(x.id)) or 0),
                card_id_sort_key(x.id),
            )
        )
    elif sort_mode == "price_asc":
        matched.sort(
            key=lambda x: (
                0 if _price_of(str(x.id)) is not None else 1,
                _price_of(str(x.id)) or 0,
                card_id_sort_key(x.id),
            )
        )
    elif index_presorted:
        # filter_index is already sorted by card id — keep encounter order.
        pass
    else:
        matched.sort(key=lambda x: card_id_sort_key(x.id))
    total_matched = len(matched)
    response.headers["X-Total-Count"] = str(total_matched)
    # Search is catalog-static; short CDN cache speeds repeat browsing.
    if need_price:
        response.headers["Cache-Control"] = "no-store"
    else:
        response.headers["Cache-Control"] = "public, max-age=15, s-maxage=60"
    return matched[offset : offset + limit]


@app.get("/filters/cards", response_model=list[FilterCardResponse])
def filter_cards_v2(
    response: Response,
    color: str | None = Query(None, description="颜色，例如 Red/Blue/Green/Purple/Black/Yellow"),
    colors: str | None = Query(None, description="多颜色，逗号分隔，例如 Red,Yellow"),
    cost: int | None = Query(None, ge=0, le=20),
    costs: str | None = Query(None, description="多费用，逗号分隔，例如 1,3,5"),
    counter: int | None = Query(None, ge=0, le=5000),
    counters: str | None = Query(None, description="多反击值，逗号分隔，例如 0,1000,2000"),
    power: int | None = Query(None, ge=0, le=20000),
    powers: str | None = Query(None, description="多战力，逗号分隔，例如 3000,5000"),
    card_type: str | None = Query(None, description="Leader/Character/Event/Stage/Don"),
    card_types: str | None = Query(None, description="多类型，逗号分隔，例如 Leader,Character"),
    attribute: str | None = Query(None, description="Strike/Slash/Special/Ranged/Wisdom"),
    attributes: str | None = Query(None, description="多属性，逗号分隔，例如 Strike,Slash"),
    series: str | None = Query(None, description="系列，例如 OP15/ST30/EB01"),
    serieses: str | None = Query(None, description="多系列，逗号分隔，例如 OP15,ST30"),
    rarity: str | None = Query(None, description="稀有度，例如 C/UC/R/SR/SEC/L"),
    rarities: str | None = Query(None, description="多稀有度，逗号分隔，例如 SR,R"),
    block: int | None = Query(None, ge=0, le=50),
    blocks: str | None = Query(None, description="多 block，逗号分隔，例如 1,2,3"),
    keyword: str | None = Query(None, description="效果关键字，例如 blocker/rush/don_x1"),
    keywords: str | None = Query(None, description="多效果关键字，逗号分隔，例如 blocker,rush,don_x1"),
    q: str | None = Query(None, description="卡号或卡名关键字（即时搜索）"),
    price_min: int | None = Query(None, ge=0, description="最低市价（日元）"),
    price_max: int | None = Query(None, ge=0, description="最高市价（日元）"),
    sort: str | None = Query(None, description="排序：id|price_desc|price_asc"),
    priced_only: bool = Query(False, description="仅返回有报价的卡"),
    offset: int = Query(0, ge=0),
    limit: int = Query(70, ge=1, le=300),
) -> list[FilterCardResponse]:
    return filter_cards(
        response=response,
        color=color,
        colors=colors,
        cost=cost,
        costs=costs,
        counter=counter,
        counters=counters,
        power=power,
        powers=powers,
        card_type=card_type,
        card_types=card_types,
        attribute=attribute,
        attributes=attributes,
        series=series,
        serieses=serieses,
        rarity=rarity,
        rarities=rarities,
        block=block,
        blocks=blocks,
        keyword=keyword,
        keywords=keywords,
        q=q,
        price_min=price_min,
        price_max=price_max,
        sort=sort,
        priced_only=priced_only,
        offset=offset,
        limit=limit,
    )


@app.get("/filters/options")
def get_filter_options() -> dict[str, list[Any]]:
    series_set: set[str] = set()
    rarity_set: set[str] = set()
    block_set: set[int] = set()
    for cid, basic in cards_by_id.items():
        series = infer_series_from_card_id(cid)
        if series:
            series_set.add(series)
        rarity = rarity_match_key((basic or {}).get("rarity"))
        if rarity:
            rarity_set.add(rarity)
        b = _to_int((basic or {}).get("block_number"))
        if b is not None:
            block_set.add(b)
    return {
        "series": sorted(series_set, key=series_sort_key),
        "rarities": sorted(rarity_set, key=rarity_sort_key),
        "blocks": sorted(block_set),
        "keywords": list(FILTER_KEYWORD_IDS),
        "card_types": ["Leader", "Character", "Event", "Stage", "Don"],
    }


def _get_user_decks_mutable(store: dict[str, Any], user_id: str) -> list[dict[str, Any]]:
    bucket = store.get(user_id)
    if not isinstance(bucket, list):
        bucket = []
        store[user_id] = bucket
    clean_bucket = [x for x in bucket if isinstance(x, dict)]
    if len(clean_bucket) != len(bucket):
        store[user_id] = clean_bucket
    return store[user_id]


def _find_deck_mutable(user_decks: list[dict[str, Any]], deck_id: str) -> dict[str, Any] | None:
    for deck in user_decks:
        if str(deck.get("id") or "") == deck_id:
            return deck
    return None


@app.get("/decks", response_model=DeckListResponse)
def list_decks(request: Request, user_id: str | None = Query(None, description="用户ID（未登录模式）")) -> DeckListResponse:
    if AUTH_BYPASS_FOR_TESTING:
        uid = _deck_owner_id_from_user_row(
            {
                "id": 0,
                "username": "test_user",
                "email": "test@local",
                "email_verified": 1,
            }  # type: ignore[arg-type]
        )
    else:
        auth_user = _read_auth_user_from_request(request)
        if auth_user is not None:
            uid = _deck_owner_id_from_user_row(auth_user)
        else:
            uid = _normalize_user_id(str(user_id or ""))
            if not uid:
                raise HTTPException(status_code=422, detail="未登录时请提供 user_id。")
    with deck_store_lock:
        store = _load_decks_store()
        user_decks = _get_user_decks_mutable(store, uid)
        payload = [_serialize_deck(d) for d in user_decks]
    payload.sort(key=lambda d: d.updated_at, reverse=True)
    return DeckListResponse(user_id=uid, decks=payload)


@app.post("/decks", response_model=DeckResponse)
def create_deck(request: Request, payload: DeckCreateRequest) -> DeckResponse:
    auth_user = _require_auth_user(request)
    uid = _deck_owner_id_from_user_row(auth_user)
    name = str(payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="卡组名称不能为空。")
    leader, cards = _validate_deck_contents(payload.leader_card_id, payload.cards)
    with deck_store_lock:
        store = _load_decks_store()
        user_decks = _get_user_decks_mutable(store, uid)
        if len(user_decks) >= MAX_USER_DECKS:
            raise HTTPException(status_code=400, detail=f"每个用户最多创建 {MAX_USER_DECKS} 个卡组。")
        now = now_iso()
        deck = {
            "id": _new_deck_id(uid, name),
            "name": name[:80],
            "leader_card_id": leader,
            "cards": cards,
            "created_at": now,
            "updated_at": now,
        }
        user_decks.append(deck)
        store[uid] = user_decks
        _save_decks_store(store)
        return _serialize_deck(deck)


@app.delete("/decks/{deck_id}")
def delete_deck(deck_id: str, request: Request) -> dict[str, str]:
    auth_user = _require_auth_user(request)
    uid = _deck_owner_id_from_user_row(auth_user)
    did = str(deck_id or "").strip()
    if not did:
        raise HTTPException(status_code=422, detail="deck_id 不能为空。")
    with deck_store_lock:
        store = _load_decks_store()
        user_decks = _get_user_decks_mutable(store, uid)
        kept = [d for d in user_decks if str(d.get("id") or "") != did]
        if len(kept) == len(user_decks):
            raise HTTPException(status_code=404, detail="未找到该卡组。")
        store[uid] = kept
        _save_decks_store(store)
    return {"status": "ok"}


@app.patch("/decks/{deck_id}/name", response_model=DeckResponse)
def rename_deck(deck_id: str, request: Request, payload: DeckRenameRequest) -> DeckResponse:
    auth_user = _require_auth_user(request)
    uid = _deck_owner_id_from_user_row(auth_user)
    did = str(deck_id or "").strip()
    new_name = str(payload.name or "").strip()
    if not did:
        raise HTTPException(status_code=422, detail="deck_id 不能为空。")
    if not new_name:
        raise HTTPException(status_code=422, detail="卡组名称不能为空。")
    with deck_store_lock:
        store = _load_decks_store()
        user_decks = _get_user_decks_mutable(store, uid)
        deck = _find_deck_mutable(user_decks, did)
        if deck is None:
            raise HTTPException(status_code=404, detail="未找到该卡组。")
        deck["name"] = new_name[:80]
        deck["updated_at"] = now_iso()
        _save_decks_store(store)
        return _serialize_deck(deck)


@app.put("/decks/{deck_id}", response_model=DeckResponse)
def replace_deck(deck_id: str, request: Request, payload: DeckSaveRequest) -> DeckResponse:
    auth_user = _require_auth_user(request)
    uid = _deck_owner_id_from_user_row(auth_user)
    did = str(deck_id or "").strip()
    if not did:
        raise HTTPException(status_code=422, detail="deck_id 不能为空。")
    leader, cards = _validate_deck_contents(payload.leader_card_id, payload.cards)
    with deck_store_lock:
        store = _load_decks_store()
        user_decks = _get_user_decks_mutable(store, uid)
        deck = _find_deck_mutable(user_decks, did)
        if deck is None:
            raise HTTPException(status_code=404, detail="未找到该卡组。")
        new_name = str(payload.name or "").strip()
        if new_name:
            deck["name"] = new_name[:80]
        deck["leader_card_id"] = leader
        deck["cards"] = cards
        deck["updated_at"] = now_iso()
        _save_decks_store(store)
        return _serialize_deck(deck)


@app.post("/decks/{deck_id}/clear", response_model=DeckResponse)
def clear_deck(deck_id: str, request: Request) -> DeckResponse:
    auth_user = _require_auth_user(request)
    uid = _deck_owner_id_from_user_row(auth_user)
    did = str(deck_id or "").strip()
    if not did:
        raise HTTPException(status_code=422, detail="deck_id 不能为空。")
    with deck_store_lock:
        store = _load_decks_store()
        user_decks = _get_user_decks_mutable(store, uid)
        deck = _find_deck_mutable(user_decks, did)
        if deck is None:
            raise HTTPException(status_code=404, detail="未找到该卡组。")
        deck["leader_card_id"] = None
        deck["cards"] = {}
        deck["updated_at"] = now_iso()
        _save_decks_store(store)
        return _serialize_deck(deck)


@app.post("/decks/{deck_id}/leader", response_model=DeckResponse)
def set_deck_leader(deck_id: str, request: Request, payload: DeckCardChangeRequest) -> DeckResponse:
    auth_user = _require_auth_user(request)
    uid = _deck_owner_id_from_user_row(auth_user)
    did = str(deck_id or "").strip()
    cid = normalize_card_id(payload.card_id)
    if not did:
        raise HTTPException(status_code=422, detail="deck_id 不能为空。")
    if not cid:
        raise HTTPException(status_code=422, detail="card_id 不能为空。")
    if cid not in cards_by_id:
        raise HTTPException(status_code=404, detail=f"未找到卡号 {cid}。")
    if not _is_leader_card(cid):
        raise HTTPException(status_code=400, detail="只能将 Leader 卡设置为队长。")
    with deck_store_lock:
        store = _load_decks_store()
        user_decks = _get_user_decks_mutable(store, uid)
        deck = _find_deck_mutable(user_decks, did)
        if deck is None:
            raise HTTPException(status_code=404, detail="未找到该卡组。")
        deck["leader_card_id"] = cid
        deck["updated_at"] = now_iso()
        _save_decks_store(store)
        return _serialize_deck(deck)


@app.post("/decks/{deck_id}/cards", response_model=DeckResponse)
def add_deck_card(deck_id: str, request: Request, payload: DeckCardChangeRequest) -> DeckResponse:
    auth_user = _require_auth_user(request)
    uid = _deck_owner_id_from_user_row(auth_user)
    did = str(deck_id or "").strip()
    cid = normalize_card_id(payload.card_id)
    add_count = _to_int(payload.count) or 1
    if not did:
        raise HTTPException(status_code=422, detail="deck_id 不能为空。")
    if not cid:
        raise HTTPException(status_code=422, detail="card_id 不能为空。")
    if add_count <= 0:
        raise HTTPException(status_code=422, detail="count 必须大于 0。")
    if cid not in cards_by_id:
        raise HTTPException(status_code=404, detail=f"未找到卡号 {cid}。")
    if _is_leader_card(cid):
        raise HTTPException(status_code=400, detail="Leader 不能加入 50 张主卡区，请使用设置 Leader。")
    with deck_store_lock:
        store = _load_decks_store()
        user_decks = _get_user_decks_mutable(store, uid)
        deck = _find_deck_mutable(user_decks, did)
        if deck is None:
            raise HTTPException(status_code=404, detail="未找到该卡组。")
        cards = _normalize_deck_cards(deck.get("cards"))
        current = cards.get(cid, 0)
        current_non_leader = _deck_non_leader_count(cards)
        if current_non_leader + add_count > 50:
            raise HTTPException(status_code=400, detail="非 Leader 卡总数最多 50 张。")
        cards[cid] = current + add_count
        deck["cards"] = cards
        deck["updated_at"] = now_iso()
        _save_decks_store(store)
        return _serialize_deck(deck)


@app.delete("/decks/{deck_id}/cards/{card_id}", response_model=DeckResponse)
def remove_deck_card(
    deck_id: str,
    card_id: str,
    request: Request,
    count: int = Query(1, ge=1, le=50),
) -> DeckResponse:
    auth_user = _require_auth_user(request)
    uid = _deck_owner_id_from_user_row(auth_user)
    did = str(deck_id or "").strip()
    cid = normalize_card_id(card_id)
    if not did:
        raise HTTPException(status_code=422, detail="deck_id 不能为空。")
    if not cid:
        raise HTTPException(status_code=422, detail="card_id 不能为空。")
    with deck_store_lock:
        store = _load_decks_store()
        user_decks = _get_user_decks_mutable(store, uid)
        deck = _find_deck_mutable(user_decks, did)
        if deck is None:
            raise HTTPException(status_code=404, detail="未找到该卡组。")
        cards = _normalize_deck_cards(deck.get("cards"))
        existing = cards.get(cid, 0)
        if existing <= 0:
            raise HTTPException(status_code=404, detail="该卡不在卡组中。")
        left = existing - count
        if left > 0:
            cards[cid] = left
        else:
            cards.pop(cid, None)
        deck["cards"] = cards
        deck["updated_at"] = now_iso()
        _save_decks_store(store)
        return _serialize_deck(deck)


@app.get("/collection", response_model=CollectionResponse)
def get_collection(request: Request) -> CollectionResponse:
    auth_user = _require_auth_user(request)
    owner = _deck_owner_id_from_user_row(auth_user)
    with collection_store_lock:
        store = _load_collection_store()
        cards = store.get(owner)
    return _serialize_collection(owner, cards if isinstance(cards, dict) else {})


@app.post("/collection/cards", response_model=CollectionResponse)
def add_collection_card(request: Request, payload: CollectionCardChangeRequest) -> CollectionResponse:
    auth_user = _require_auth_user(request)
    owner = _deck_owner_id_from_user_row(auth_user)
    cid = normalize_card_id(payload.card_id)
    add_n = _to_int(payload.count) or 1
    if not cid:
        raise HTTPException(status_code=422, detail="card_id 不能为空。")
    if cid not in cards_by_id:
        raise HTTPException(status_code=404, detail=f"未找到卡号 {cid}。")
    if add_n <= 0:
        raise HTTPException(status_code=422, detail="count 必须大于 0。")
    with collection_store_lock:
        store = _load_collection_store()
        owner_cards = _normalize_collection_cards(store.get(owner) if isinstance(store.get(owner), dict) else {})
        owner_cards[cid] = int(owner_cards.get(cid, 0)) + add_n
        store[owner] = owner_cards
        _save_collection_store(store)
    return _serialize_collection(owner, owner_cards)


@app.delete("/collection/cards/{card_id}", response_model=CollectionResponse)
def remove_collection_card(
    card_id: str,
    request: Request,
    count: int = Query(1, ge=1, le=999),
) -> CollectionResponse:
    auth_user = _require_auth_user(request)
    owner = _deck_owner_id_from_user_row(auth_user)
    cid = normalize_card_id(card_id)
    if not cid:
        raise HTTPException(status_code=422, detail="card_id 不能为空。")
    with collection_store_lock:
        store = _load_collection_store()
        owner_cards = _normalize_collection_cards(store.get(owner) if isinstance(store.get(owner), dict) else {})
        cur = int(owner_cards.get(cid, 0))
        if cur <= 0:
            raise HTTPException(status_code=404, detail="该卡不在收藏中。")
        left = cur - int(count)
        if left > 0:
            owner_cards[cid] = left
        else:
            owner_cards.pop(cid, None)
        store[owner] = owner_cards
        _save_collection_store(store)
    return _serialize_collection(owner, owner_cards)


@app.get("/binder", response_model=BinderResponse)
def get_binder(request: Request) -> BinderResponse:
    auth_user = _require_auth_user(request)
    owner = _deck_owner_id_from_user_row(auth_user)
    with binder_store_lock:
        store = _load_binder_store()
        pages, titles = _normalize_binder_payload(store.get(owner))
        store[owner] = {"pages": pages, "page_titles": titles}
        _save_binder_store(store)
    return BinderResponse(owner=owner, pages=pages, page_titles=titles)


@app.put("/binder/slot", response_model=BinderResponse)
def update_binder_slot(request: Request, payload: BinderSlotUpdateRequest) -> BinderResponse:
    auth_user = _require_auth_user(request)
    owner = _deck_owner_id_from_user_row(auth_user)
    page = int(payload.page)
    slot = int(payload.slot)
    if page < 1 or page > 10:
        raise HTTPException(status_code=422, detail="page 必须在 1~10。")
    if slot < 1 or slot > 18:
        raise HTTPException(status_code=422, detail="slot 必须在 1~18。")
    cid = normalize_card_id(str(payload.card_id or ""))
    if cid and cid not in cards_by_id:
        raise HTTPException(status_code=404, detail=f"未找到卡号 {cid}。")
    if cid:
        with collection_store_lock:
            cstore = _load_collection_store()
            owner_cards = _normalize_collection_cards(cstore.get(owner) if isinstance(cstore.get(owner), dict) else {})
        if int(owner_cards.get(cid, 0)) <= 0:
            raise HTTPException(status_code=400, detail="该卡不在你的收藏中，不能放入 Binder。")
    with binder_store_lock:
        store = _load_binder_store()
        pages, titles = _normalize_binder_payload(store.get(owner))
        pages[page - 1][slot - 1] = cid if cid else None
        store[owner] = {"pages": pages, "page_titles": titles}
        _save_binder_store(store)
    return BinderResponse(owner=owner, pages=pages, page_titles=titles)


@app.put("/binder/swap", response_model=BinderResponse)
def swap_binder_slots(request: Request, payload: BinderSwapRequest) -> BinderResponse:
    auth_user = _require_auth_user(request)
    owner = _deck_owner_id_from_user_row(auth_user)
    page = int(payload.page)
    f = int(payload.from_slot)
    t = int(payload.to_slot)
    if page < 1 or page > 10:
        raise HTTPException(status_code=422, detail="page 必须在 1~10。")
    if f < 1 or f > 18 or t < 1 or t > 18:
        raise HTTPException(status_code=422, detail="槽位必须在 1~18。")
    with binder_store_lock:
        store = _load_binder_store()
        pages, titles = _normalize_binder_payload(store.get(owner))
        pages[page - 1][f - 1], pages[page - 1][t - 1] = pages[page - 1][t - 1], pages[page - 1][f - 1]
        store[owner] = {"pages": pages, "page_titles": titles}
        _save_binder_store(store)
    return BinderResponse(owner=owner, pages=pages, page_titles=titles)


@app.put("/binder/page-title", response_model=BinderResponse)
def set_binder_page_title(request: Request, payload: BinderPageTitleRequest) -> BinderResponse:
    auth_user = _require_auth_user(request)
    owner = _deck_owner_id_from_user_row(auth_user)
    page = int(payload.page)
    if page < 1 or page > 10:
        raise HTTPException(status_code=422, detail="page 必须在 1~10。")
    title = str(payload.title or "").strip()[:40]
    with binder_store_lock:
        store = _load_binder_store()
        pages, titles = _normalize_binder_payload(store.get(owner))
        titles[page - 1] = title
        store[owner] = {"pages": pages, "page_titles": titles}
        _save_binder_store(store)
    return BinderResponse(owner=owner, pages=pages, page_titles=titles)


@app.post("/binder/autofill-current-page", response_model=BinderResponse)
def autofill_binder_current_page(
    request: Request,
    page: int = Query(..., ge=1, le=10),
) -> BinderResponse:
    auth_user = _require_auth_user(request)
    owner = _deck_owner_id_from_user_row(auth_user)
    with collection_store_lock:
        cstore = _load_collection_store()
        owner_cards = _normalize_collection_cards(cstore.get(owner) if isinstance(cstore.get(owner), dict) else {})
    # Expand pool by owned counts so duplicate cards can appear multiple times.
    card_pool: list[str] = []
    for cid in sorted(owner_cards.keys(), key=card_id_sort_key):
        cnt = int(owner_cards.get(cid, 0) or 0)
        if cnt <= 0:
            continue
        card_pool.extend([cid] * cnt)
    with binder_store_lock:
        store = _load_binder_store()
        pages, titles = _normalize_binder_payload(store.get(owner))
        row = pages[page - 1]
        # Keep existing cards; fill empty slots from expanded collection pool.
        # Existing cards consume one copy each from pool if available.
        pool = list(card_pool)
        for existing in [str(x) for x in row if x]:
            try:
                pool.remove(existing)
            except ValueError:
                pass
        ptr = 0
        for i in range(18):
            if row[i]:
                continue
            if ptr >= len(pool):
                break
            row[i] = pool[ptr]
            ptr += 1
        pages[page - 1] = row
        store[owner] = {"pages": pages, "page_titles": titles}
        _save_binder_store(store)
    return BinderResponse(owner=owner, pages=pages, page_titles=titles)


@app.post("/binder/clear-current-page", response_model=BinderResponse)
def clear_binder_current_page(
    request: Request,
    page: int = Query(..., ge=1, le=10),
) -> BinderResponse:
    auth_user = _require_auth_user(request)
    owner = _deck_owner_id_from_user_row(auth_user)
    with binder_store_lock:
        store = _load_binder_store()
        pages, titles = _normalize_binder_payload(store.get(owner))
        pages[page - 1] = [None for _ in range(18)]
        store[owner] = {"pages": pages, "page_titles": titles}
        _save_binder_store(store)
    return BinderResponse(owner=owner, pages=pages, page_titles=titles)


@app.post("/binder/share", response_model=BinderShareCreateResponse)
def create_binder_share(request: Request) -> BinderShareCreateResponse:
    """Snapshot current binder into a public share link (stable token per user)."""
    auth_user = _require_auth_user(request)
    owner = _deck_owner_id_from_user_row(auth_user)
    owner_name = str(auth_user["username"] or "")
    with binder_store_lock:
        store = _load_binder_store()
        pages, titles = _normalize_binder_payload(store.get(owner))
        store[owner] = {"pages": pages, "page_titles": titles}
        _save_binder_store(store)
    token = _upsert_binder_share(owner, owner_name, pages, titles)
    return BinderShareCreateResponse(
        token=token,
        url_path=f"/binder/s/{token}",
        owner_name=owner_name,
    )


@app.get("/binder/shared/{token}", response_model=BinderSharedResponse)
def get_shared_binder(token: str) -> BinderSharedResponse:
    """Public read-only binder snapshot — no auth required."""
    tok = str(token or "").strip()
    if not tok or len(tok) > 80:
        raise HTTPException(status_code=404, detail="分享链接无效。")
    with binder_store_lock:
        store = _load_binder_shares()
        entry = store.get(tok)
    if not isinstance(entry, dict):
        raise HTTPException(status_code=404, detail="分享链接不存在或已失效。")
    pages, titles = _normalize_binder_payload(entry)
    return BinderSharedResponse(
        token=tok,
        owner_name=str(entry.get("owner_name") or "")[:40],
        pages=pages,
        page_titles=titles,
    )


@app.post("/recognize/photo", response_model=PhotoRecognizeResponse)
def recognize_photo(payload: PhotoRecognizeRequest) -> PhotoRecognizeResponse:
    raw = str(payload.image_base64 or "").strip()
    if not raw:
        return PhotoRecognizeResponse(message="图片为空。", stage="no_image")
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw, validate=True)
    except Exception:
        return PhotoRecognizeResponse(message="图片格式无法解析。", stage="bad_image")
    if not blob:
        return PhotoRecognizeResponse(message="图片内容为空。", stage="no_image")
    debug_info: dict[str, Any] = {
        "ocr_texts": [],
        "structured_hints": {},
        "attr_hints": {},
        "attr_pool": {},
        "deepseek_structured_hints": {},
        "deepseek_structured_views": [],
        "structured_candidates_top": [],
        "visual_candidates_top": [],
    }

    def _resp(**kwargs: Any) -> PhotoRecognizeResponse:
        if RECOGNIZE_INCLUDE_DEBUG:
            kwargs.setdefault("debug", debug_info)
        else:
            kwargs.pop("debug", None)
            if kwargs.get("stage") in {
                "no_id_ocr",
                "series_mismatch",
                "hard_filter_no_match",
                "blurry",
                "too_few_hints",
            }:
                kwargs["debug"] = {"ocr_texts": (debug_info.get("ocr_texts") or [])[:12]}
        return PhotoRecognizeResponse(**kwargs)

    def _cand_payload(rows: list[tuple[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for c, d in rows:
            base = _base_card_id(c)
            if base in seen:
                continue
            seen.add(base)
            out.append({"card_id": c, "base_card_id": base, "distance": d})
            if len(out) >= limit:
                break
        return out

    # 1) OCR + DeepSeek attributes (card-id is NOT the primary path — often unreadable).
    ocr_texts_raw = _extract_ocr_texts_from_blob(blob)
    ocr_roi_texts = _ocr_attribute_roi_texts(blob)
    if ocr_roi_texts:
        ocr_texts_raw = list(dict.fromkeys(list(ocr_texts_raw) + list(ocr_roi_texts)))
    ocr_texts = _filter_relevant_ocr_lines(ocr_texts_raw)
    debug_info["ocr_texts"] = ocr_texts[:80]
    debug_info["ocr_texts_raw"] = ocr_texts_raw[:80]
    debug_info["ocr_roi_texts"] = ocr_roi_texts[:40]
    ocr_structured_hints = _extract_structured_hints_from_text(" ".join(ocr_texts_raw)) if ocr_texts_raw else {}

    # Prefer vision attributes when OCR is thin (webcam photos rarely have clean labels).
    # Skip slow DeepSeek vision when OCR already found a usable card id.
    ocr_field_n = _count_attr_hint_fields(ocr_structured_hints)
    early_ocr_id, early_near = extract_card_id_hits_from_ocr_texts(ocr_texts_raw)
    ds_hints: dict[str, Any] = {}
    if early_ocr_id:
        debug_info["skip_deepseek_vision"] = "ocr_card_id_found"
    elif ocr_texts and ocr_field_n >= 2:
        ds_hints = _deepseek_extract_structured_hints_from_text(" ".join(ocr_texts))
    if (not early_ocr_id) and not any(
        k in ds_hints for k in ("card_id", "cost", "power", "counter", "block", "name", "color", "type", "rarity")
    ):
        ds_hints = _deepseek_extract_structured_hints_multi(blob)
    ds_hints = _sanitize_deepseek_hints(ds_hints, ocr_structured_hints)
    debug_info["deepseek_structured_hints"] = {k: v for k, v in ds_hints.items() if not str(k).startswith("_")}
    debug_info["deepseek_structured_views"] = ds_hints.get("_views") or []

    attr_hints = _merge_recognize_attr_hints(ocr_structured_hints, ds_hints)
    # DeepSeek-only cost is often effect-text noise (コスト1以下). Require OCR cost support.
    if attr_hints.get("cost") is not None and ocr_structured_hints.get("cost") is None:
        attr_hints["cost"] = None
    # Frame-color estimate is noisy on art-heavy crops — soft boost only, never hard-narrow.
    est_colors = _estimate_card_colors_from_blob(blob)
    if est_colors:
        debug_info["estimated_colors"] = sorted(est_colors)
    debug_info["structured_hints"] = {
        k: (list(v) if isinstance(v, set) else v) for k, v in ocr_structured_hints.items()
    }
    debug_info["attr_hints"] = {
        k: (sorted(list(v)) if isinstance(v, set) else v) for k, v in attr_hints.items()
    }

    # Optional OCR card-id boost only (never auto-accept alone).
    ocr_card_id, ocr_near_ids = extract_card_id_from_photo_ocr(blob, extra_texts=ocr_texts_raw)
    if early_ocr_id and not ocr_card_id:
        ocr_card_id = early_ocr_id
    if early_near:
        ocr_near_ids = list(dict.fromkeys(list(ocr_near_ids) + list(early_near)))
    debug_info["ocr_near_ids"] = ocr_near_ids[:8]
    debug_info["ocr_card_id"] = ocr_card_id
    # DeepSeek may also return a card_id — treat as soft boost when known.
    ds_card_id = _base_card_id(str(ds_hints.get("card_id") or ""))
    if ds_card_id and ds_card_id not in cards_by_id:
        ds_card_id = ""

    # 2) Hard-narrow catalog by attributes (1 strong field is enough to start).
    attr_pool, pool_meta = _narrow_cards_by_attributes(attr_hints, max_pool=80, min_fields=1)
    # Always keep OCR / DeepSeek card ids inside the working pool when known.
    for cid in (ocr_card_id, ds_card_id, *ocr_near_ids):
        b = _base_card_id(str(cid or ""))
        if b and b in cards_by_id and b not in attr_pool:
            attr_pool = [b] + attr_pool
    debug_info["attr_pool"] = pool_meta
    pool_set = {_base_card_id(x) for x in attr_pool}

    # Structured ranking for fallback / scoring.
    ds_ranked = _rank_cards_by_structured_hints(ds_hints, top_k=20) if ds_hints else []
    structured_candidates = _build_structured_candidates(attr_hints, top_k=30)
    debug_info["structured_candidates_top"] = [
        {"card_id": c, "score": s} for c, s in structured_candidates[:12]
    ]

    # 3) Visual retrieval on card crop (ignore webcam background).
    visual_blob = _prefer_card_crop_blob(blob)
    visual_top_k = 48 if pool_set else 16
    clip_candidates = recognize_top_candidates_clip(visual_blob, top_k=visual_top_k) if RECOGNIZE_USE_CLIP else []
    visual_raw = clip_candidates if clip_candidates else recognize_top_candidates_from_photo_bytes(visual_blob, top_k=visual_top_k)
    # Also merge full-frame visual in case crop failed badly.
    if visual_blob is not blob:
        extra_clip = recognize_top_candidates_clip(blob, top_k=8) if RECOGNIZE_USE_CLIP else []
        extra_hash = [] if extra_clip else recognize_top_candidates_from_photo_bytes(blob, top_k=8)
        seen_v = {_base_card_id(c) for c, _d in visual_raw}
        for c, d in list(extra_clip) + list(extra_hash):
            b = _base_card_id(c)
            if b in seen_v:
                continue
            seen_v.add(b)
            visual_raw.append((c, d))
    use_clip = bool(clip_candidates)

    visual_candidates: list[tuple[str, int | None]] = []
    if pool_set:
        in_pool = [(c, d) for c, d in visual_raw if _base_card_id(c) in pool_set]
        out_pool = [(c, d) for c, d in visual_raw if _base_card_id(c) not in pool_set]
        if in_pool:
            # Soft prefer pool members, but never drop strong visual hits.
            visual_candidates = in_pool + out_pool
        else:
            # Attr pool conflicted with vision (noisy OCR cost etc.) — trust vision first.
            visual_candidates = list(out_pool)
            for cid in attr_pool[:8]:
                visual_candidates.append((cid, None))
            debug_info["pool_visual_conflict"] = True
    else:
        visual_candidates = [(c, d) for c, d in visual_raw]

    # Rank by effective distance: attribute-pool members get a discount so a
    # correct power/counter hit can beat a slightly closer wrong CLIP neighbor.
    if visual_candidates and (attr_hints or pool_set or est_colors):
        def _effective_visual_key(row: tuple[str, int | None]) -> tuple[int, int]:
            cid, dist = row
            base = _base_card_id(cid)
            raw = dist if isinstance(dist, int) else 10_000
            bonus = 0
            if base in pool_set:
                bonus += 45
            bonus += _attr_match_score(base, attr_hints)
            if est_colors and _card_color_token_set(base).intersection(est_colors):
                bonus += 20
            return (raw - bonus, -bonus)

        visual_candidates = sorted(visual_candidates, key=_effective_visual_key)

    # ORB rerank on a wider shortlist. CLIP alone is weak on SAMPLE vs webcam /
    # sleeve glare / full-art. Prefer crop; escalate to full frame when weak.
    # Also ORB-scan attribute-pool members CLIP missed entirely.
    if visual_candidates or attr_pool:
        short_ids: list[str] = []
        for c, _d in list(visual_candidates)[:20] + list(visual_raw)[:32]:
            b = _base_card_id(c)
            if b and b not in short_ids:
                short_ids.append(b)
            if len(short_ids) >= 24:
                break
        # CLIP can completely miss full-art / glare photos — ORB the attr pool.
        if attr_pool and len(attr_pool) <= 100:
            power_hint = attr_hints.get("power")
            for cid in attr_pool:
                b = _base_card_id(cid)
                if not b or b in short_ids:
                    continue
                if b not in local_image_path_map:
                    continue
                if power_hint is not None:
                    fields = _get_card_numeric_fields(b)
                    if fields.get("power") is not None and int(fields["power"]) != int(power_hint):
                        continue
                short_ids.append(b)
                if len(short_ids) >= 80:
                    break
        dist_map = {_base_card_id(c): d for c, d in visual_candidates}
        for c, d in visual_raw:
            dist_map.setdefault(_base_card_id(c), d)
        reranked: list[tuple[str, int | None, float]] = []
        for cid in short_ids:
            path = local_image_path_map.get(cid)
            if not path:
                reranked.append((cid, dist_map.get(cid), 0.0))
                continue
            orb = float(_orb_match_score(visual_blob, path) or 0.0)
            reranked.append((cid, dist_map.get(cid), orb))
        reranked.sort(key=lambda row: (-row[2], row[1] if isinstance(row[1], int) else 10_000))
        top_orb = float(reranked[0][2]) if reranked else 0.0
        second_orb = float(reranked[1][2]) if len(reranked) > 1 else 0.0
        need_full = visual_blob is not blob and not (top_orb >= 15 and (top_orb - second_orb) >= 8)
        if need_full:
            boosted: list[tuple[str, int | None, float]] = []
            for cid, dist, orb_crop in reranked[:20]:
                path = local_image_path_map.get(cid)
                if not path:
                    boosted.append((cid, dist, orb_crop))
                    continue
                orb_full = float(_orb_match_score(blob, path) or 0.0)
                boosted.append((cid, dist, max(orb_crop, orb_full)))
            boosted.extend(reranked[20:])
            reranked = boosted
            reranked.sort(key=lambda row: (-row[2], row[1] if isinstance(row[1], int) else 10_000))
        if any(orb >= 5.0 for _c, _d, orb in reranked):
            seen_short = set(short_ids)
            rest = [row for row in visual_candidates if _base_card_id(row[0]) not in seen_short]
            visual_candidates = [(c, d) for c, d, _orb in reranked] + rest
            debug_info["orb_rerank"] = [
                {"card_id": c, "distance": d, "orb": orb} for c, d, orb in reranked[:10]
            ]

    # Optional OCR / DeepSeek id boost — always keep known IDs (don't let attr pool drop them).
    ocr_boost: list[str] = []
    for cid in (ocr_card_id, ds_card_id, *ocr_near_ids):
        if not cid:
            continue
        b = _base_card_id(cid)
        if b in ocr_boost:
            continue
        if b not in cards_by_id:
            continue
        ocr_boost.append(b)
        if b not in pool_set:
            pool_set.add(b)
            attr_pool = [b] + list(attr_pool)

    debug_info["visual_candidates_top"] = [
        {"card_id": c, "distance": d} for c, d in visual_candidates[:12]
    ]

    # DeepSeek pick only inside pool (or visual list if no pool).
    pick_pool = [c for c, _d in visual_candidates] + list(attr_pool[:20]) + ocr_boost
    pick_pool = list(dict.fromkeys(_base_card_id(x) for x in pick_pool if x))
    deepseek_pick = None
    clip_clear = False
    if use_clip and len(visual_candidates) >= 2:
        d0, d1 = visual_candidates[0][1], visual_candidates[1][1]
        if isinstance(d0, int) and isinstance(d1, int) and d0 <= CLIP_HIGH_DIST and (d1 - d0) >= CLIP_HIGH_GAP:
            clip_clear = True
    elif use_clip and len(visual_candidates) == 1:
        d0 = visual_candidates[0][1]
        clip_clear = isinstance(d0, int) and d0 <= CLIP_HIGH_DIST
    if pick_pool and not clip_clear:
        deepseek_pick = recognize_card_id_with_deepseek(blob, pick_pool)
        if deepseek_pick and _base_card_id(deepseek_pick) not in set(pick_pool):
            deepseek_pick = None

    # 4) Merge: visual(+attr) primary, OCR id optional boost, structured last.
    ranked_suggestions: list[tuple[str, Any]] = []
    for cid in ocr_boost[:1]:
        ranked_suggestions.append((cid, 0))
    for c, d in visual_candidates:
        ranked_suggestions.append((c, d))
    for cid in ocr_boost[1:]:
        ranked_suggestions.append((cid, 0))
    if deepseek_pick:
        ranked_suggestions.append((deepseek_pick, None))
    for c, _s in structured_candidates[:8]:
        if (not pool_set) or _base_card_id(c) in pool_set:
            ranked_suggestions.append((c, None))
    for c, _s in ds_ranked[:6]:
        if (not pool_set) or _base_card_id(c) in pool_set:
            ranked_suggestions.append((c, None))

    merged: list[tuple[str, Any]] = []
    seen_m: set[str] = set()
    for c, d in ranked_suggestions:
        b = _base_card_id(c)
        if b in seen_m:
            continue
        seen_m.add(b)
        merged.append((c, d))
        if len(merged) >= 8:
            break

    if not merged:
        if pool_meta.get("stage") == "too_few_hints":
            return _resp(
                message="未能读出费用/力量/反击等线索。请拍清左上费用、力量与卡名区域。",
                stage="too_few_hints",
                confidence="low",
                candidates=[],
            )
        return _resp(
            message="未能匹配到卡片。请拍清费用、力量、反击与卡名，整张卡放入外框。",
            stage="no_id_ocr",
            confidence="low",
            candidates=[],
        )

    top_id, top_dist = merged[0]
    second_dist = merged[1][1] if len(merged) > 1 else None
    gap = None
    if isinstance(top_dist, int) and isinstance(second_dist, int):
        gap = second_dist - top_dist
    conf = _visual_confidence(
        top_dist if isinstance(top_dist, int) else None,
        gap,
        use_clip=use_clip,
    )

    orb_rows = debug_info.get("orb_rerank") or []
    orb_clear = False
    if isinstance(orb_rows, list) and orb_rows:
        top_orb = float((orb_rows[0] or {}).get("orb") or 0)
        second_orb = float((orb_rows[1] or {}).get("orb") or 0) if len(orb_rows) > 1 else 0.0
        if (top_orb >= 12 and (top_orb - second_orb) >= 2) or (
            top_orb >= 7 and (top_orb - second_orb) >= 3
        ):
            orb_clear = True
            conf = "high" if top_orb >= 12 else "medium"
            debug_info["orb_clear"] = True

    # Auto-jump: unique attr pool, or small pool with clear visual top — NOT card-id alone.
    auto = False
    auto_stage = "attr_unique"
    if len(attr_pool) == 1 and _base_card_id(top_id) == _base_card_id(attr_pool[0]):
        auto = True
        auto_stage = "attr_unique"
        conf = "high"
    elif orb_clear and _base_card_id(top_id) == _base_card_id(str((orb_rows[0] or {}).get("card_id") or "")):
        # Strong local-feature match beats weak CLIP distance on SAMPLE vs webcam.
        auto = True
        auto_stage = "orb_clear"
        conf = "high"
    elif pool_set and len(pool_set) <= 5 and clip_clear and _base_card_id(top_id) in pool_set:
        auto = True
        auto_stage = "visual_clear"
        conf = "high"
    elif (
        pool_set
        and len(pool_set) <= 5
        and isinstance(top_dist, int)
        and (
            (use_clip and top_dist <= CLIP_HIGH_DIST and (gap is None or gap >= CLIP_HIGH_GAP))
            or ((not use_clip) and top_dist <= 8 and (gap is None or gap >= 8))
        )
    ):
        auto = True
        auto_stage = "visual_clear"
        conf = "high"

    if auto:
        return _resp(
            card_id=top_id,
            base_card_id=_base_card_id(top_id),
            distance=top_dist if isinstance(top_dist, int) else None,
            confidence=conf,
            message="ok_ocr",
            stage=auto_stage,
            score_gap=gap,
        )

    return _resp(
        card_id=top_id,
        base_card_id=_base_card_id(top_id),
        distance=top_dist if isinstance(top_dist, int) else None,
        confidence=conf,
        message="ok_candidates",
        stage="attr_candidates" if pool_set else ("visual_candidates" if visual_candidates else "structured_candidates"),
        candidates=_cand_payload(merged, limit=6),
        score_gap=gap,
    )


def _compute_topdeck_facets(decks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Normalized facet counts for tournament filters (run once per data load)."""
    from collections import Counter

    country_c: Counter[str] = Counter()
    host_c: Counter[str] = Counter()
    author_c: Counter[str] = Counter()
    tournament_c: Counter[str] = Counter()
    placement_c: Counter[str] = Counter()
    leader_c: Counter[str] = Counter()

    for row in decks:
        if not isinstance(row, dict):
            continue
        ck = norm_country(row.get("country"))
        if ck:
            country_c[ck] += 1
        hk = norm_host(row.get("host"))
        if hk:
            host_c[hk] += 1
        author = str(row.get("author") or "").strip()
        if author:
            author_c[author] += 1
        tk = norm_tournament(row.get("tournament"))
        if tk:
            tournament_c[tk] += 1
        pk = norm_placement(row.get("placement"))
        if pk:
            placement_c[pk] += 1
        lid = normalize_card_id(str(row.get("leader") or "").strip())
        if lid:
            leader_c[lid] += 1

    leader_rows: list[dict[str, Any]] = []

    def _leader_facet_sort_key(lid: str) -> tuple:
        """Newest first: OP → EB → PRB → ST, higher set number first within each."""
        text = normalize_card_id(lid)
        m = re.match(r"^([A-Z]+)(\d*)-(\d+)", text)
        if not m:
            return (9, 0, 0, text)
        prefix, series, number = m.group(1), m.group(2) or "0", m.group(3)
        kind = {"OP": 0, "EB": 1, "PRB": 2, "ST": 3}.get(prefix, 9)
        return (kind, -int(series), -int(number), text)

    for lid, n in sorted(leader_c.items(), key=lambda kv: _leader_facet_sort_key(kv[0])):
        basic = cards_by_id.get(lid) or {}
        name_hant = card_display_name_zh(basic, hans=False)
        name_hans = card_display_name_zh(basic, hans=True)
        name_en = str(basic.get("name_en") or basic.get("name") or "").strip()
        label_hant = f"{lid} {name_hant}".strip() if name_hant else lid
        label_hans = f"{lid} {name_hans}".strip() if name_hans else lid
        label_en = f"{lid} {name_en}".strip() if name_en else lid
        leader_rows.append(
            facet_row(
                lid,
                n,
                {"en": label_en, "zh-Hans": label_hans, "zh-Hant": label_hant},
            )
        )

    return {
        "country": [
            facet_row(k, n, country_labels(k)) for k, n in country_c.most_common()
        ],
        "host": [{"value": k, "count": n} for k, n in host_c.most_common(250)],
        "author": [
            (
                facet_row(
                    k,
                    n,
                    {"en": "Unknown", "zh-Hans": "未知", "zh-Hant": "未知"},
                )
                if str(k).strip().upper() in {"NA", "N/A", "-"}
                else {"value": k, "count": n}
            )
            for k, n in author_c.most_common(250)
        ],
        "tournament": [
            facet_row(k, n, tournament_labels(k)) for k, n in tournament_c.most_common(200)
        ],
        "placement": [
            facet_row(k, n, placement_labels(k)) for k, n in placement_c.most_common(120)
        ],
        "leader": leader_rows,
    }


def _topdeck_facets() -> dict[str, list[dict[str, Any]]]:
    global topdecks_facets_cache
    if topdecks_facets_cache:
        return topdecks_facets_cache
    decks = topdecks_decks_sorted or (
        topdecks_payload.get("decks") if isinstance(topdecks_payload.get("decks"), list) else []
    )
    topdecks_facets_cache = _compute_topdeck_facets([r for r in decks if isinstance(r, dict)])
    return topdecks_facets_cache


def _topdeck_cached_meta_blob(row: dict[str, Any]) -> str:
    did = str(row.get("id") or "")
    if did and did in topdecks_meta_blob_by_id:
        return topdecks_meta_blob_by_id[did]
    blob = _topdeck_row_meta_blob(row)
    if did:
        topdecks_meta_blob_by_id[did] = blob
    return blob


@app.get("/topdecks/meta")
def topdecks_meta(response: Response) -> dict[str, Any]:
    ensure_topdecks_data_fresh()
    formats = topdecks_payload.get("formats") if isinstance(topdecks_payload.get("formats"), dict) else {}
    stats = topdecks_payload.get("stats") if isinstance(topdecks_payload.get("stats"), dict) else {}
    # Anonymous catalog; short CDN/browser cache cuts repeat mounts.
    response.headers["Cache-Control"] = "public, max-age=120, stale-while-revalidate=300"
    return {
        "source": topdecks_payload.get("source") or "https://onepiecetopdecks.com/deck-list/",
        "attribution": topdecks_payload.get("attribution") or "ONE PIECE TOP DECKS",
        "synced_at": topdecks_payload.get("synced_at"),
        "stats": stats,
        "formats": {
            "jp": {
                "label": (formats.get("jp") or {}).get("label") or "Japan / Asia",
                "metas": (formats.get("jp") or {}).get("metas") or [],
            },
            "en": {
                "label": (formats.get("en") or {}).get("label") or "English",
                "metas": (formats.get("en") or {}).get("metas") or [],
            },
        },
        "facets": _topdeck_facets(),
    }


@app.get("/topdecks/metas")
def topdecks_metas(format: str = Query("all", description="all | jp | en")) -> list[dict[str, Any]]:
    ensure_topdecks_data_fresh()
    raw_fmt = str(format or "all").strip().lower()
    formats = topdecks_payload.get("formats") if isinstance(topdecks_payload.get("formats"), dict) else {}
    if raw_fmt in {"en", "english"}:
        keys = ["en"]
    elif raw_fmt in {"jp", "japan", "asia"}:
        keys = ["jp"]
    else:
        keys = ["jp", "en"]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in keys:
        block = formats.get(key) if isinstance(formats.get(key), dict) else {}
        metas = block.get("metas") if isinstance(block.get("metas"), list) else []
        for m in metas:
            if not isinstance(m, dict):
                continue
            slug = str(m.get("slug") or "")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            out.append(m)
    return out





def _topdeck_brief(row: dict[str, Any]) -> dict[str, Any]:
    leader = str(row.get("leader") or "").strip()
    leader_basic = cards_by_id.get(normalize_card_id(leader)) or {}
    country_raw = row.get("country") or ""
    host_raw = row.get("host") or ""
    tournament_raw = row.get("tournament") or ""
    placement_raw = row.get("placement") or ""
    country_key = norm_country(country_raw)
    host_key = norm_host(host_raw)
    tournament_key = norm_tournament(tournament_raw)
    placement_key = norm_placement(placement_raw)
    return {
        "id": row.get("id"),
        "format": row.get("format"),
        "meta_slug": row.get("meta_slug"),
        "meta_title": row.get("meta_title"),
        "name": row.get("name") or "",
        "author": row.get("author") or "",
        "country": country_raw,
        "country_key": country_key,
        "country_labels": country_labels(country_key) if country_key else {},
        "date": row.get("date") or "",
        "placement": placement_raw,
        "placement_key": placement_key,
        "placement_labels": placement_labels(placement_key) if placement_key else {},
        "tournament": tournament_raw,
        "tournament_key": tournament_key,
        "tournament_labels": tournament_labels(tournament_key) if tournament_key else {},
        "host": host_raw,
        "host_key": host_key,
        "leader": leader,
        "leader_name": leader_basic.get("name") or leader_basic.get("name_en") or "",
        "leader_name_en": leader_basic.get("name_en") or "",
        "card_count": row.get("card_count") or sum(int(v or 0) for v in (row.get("cards") or {}).values()),
        "source_url": row.get("source_url") or row.get("meta_url") or "",
        "meta_url": row.get("meta_url") or "",
    }


@app.get("/topdecks/decks")
def topdecks_decks(
    request: Request,
    response: Response,
    format: str = Query("all", description="all | jp | en"),
    meta: str | None = Query(None, description="meta slug filter (comma-separated)"),
    country: str | None = Query(None),
    host: str | None = Query(None),
    author: str | None = Query(None),
    tournament: str | None = Query(None),
    placement: str | None = Query(None),
    leader: str | None = Query(None, description="leader card id filter (comma-separated)"),
    q: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(40, ge=1, le=120),
) -> dict[str, Any]:
    ensure_topdecks_data_fresh()
    raw_fmt = str(format or "all").strip().lower()
    if raw_fmt in {"en", "english"}:
        fmt_filter: str | None = "en"
    elif raw_fmt in {"jp", "japan", "asia"}:
        fmt_filter = "jp"
    else:
        fmt_filter = None  # all
    meta_raw = str(meta or "").strip()
    meta_slugs = {s.strip() for s in re.split(r"[,|]", meta_raw) if s.strip()} if meta_raw else set()

    def _multi(raw: str | None) -> set[str]:
        text = str(raw or "").strip()
        if not text:
            return set()
        return {s.strip() for s in re.split(r"[,|]", text) if s.strip()}

    countries = _multi(country)
    hosts = _multi(host)
    authors = _multi(author)
    tournaments = _multi(tournament)
    placements = _multi(placement)
    leaders = {normalize_card_id(x) for x in _multi(leader)}
    leaders.discard("")
    query = str(q or "").strip()
    query_l = query.lower()
    card_hit_deck_ids: set[str] | None = None
    if query_l:
        matching_bases = _topdeck_query_matching_card_bases(query)
        if matching_bases:
            card_hit_deck_ids = set()
            for base in matching_bases:
                card_hit_deck_ids |= topdecks_by_card_base.get(base, set())

    decks = topdecks_decks_sorted or (
        topdecks_payload.get("decks") if isinstance(topdecks_payload.get("decks"), list) else []
    )
    has_filter = bool(
        fmt_filter
        or meta_slugs
        or countries
        or hosts
        or authors
        or tournaments
        or placements
        or leaders
        or query_l
    )

    if not has_filter:
        # Pre-sorted newest-first — first page is a pure slice.
        total = len(decks)
        page_rows = decks[offset : offset + limit]
    else:
        filtered: list[dict[str, Any]] = []
        for row in decks:
            if not isinstance(row, dict):
                continue
            if fmt_filter and str(row.get("format") or "") != fmt_filter:
                continue
            if meta_slugs and str(row.get("meta_slug") or "") not in meta_slugs:
                continue
            if countries and norm_country(row.get("country")) not in countries:
                continue
            if hosts and norm_host(row.get("host")) not in hosts:
                continue
            if authors and str(row.get("author") or "").strip() not in authors:
                continue
            if tournaments and norm_tournament(row.get("tournament")) not in tournaments:
                continue
            if placements and norm_placement(row.get("placement")) not in placements:
                continue
            if leaders and normalize_card_id(str(row.get("leader") or "")) not in leaders:
                continue
            if query_l:
                did = str(row.get("id") or "")
                meta_hit = query_l in _topdeck_cached_meta_blob(row)
                card_hit = bool(card_hit_deck_ids and did in card_hit_deck_ids)
                if not meta_hit and not card_hit:
                    continue
            filtered.append(row)
        # decks already newest-first; filtered preserves that order — no re-sort.
        total = len(filtered)
        page_rows = filtered[offset : offset + limit]

    items = [_topdeck_brief(row) for row in page_rows if isinstance(row, dict)]
    user = _read_auth_user_from_request(request)
    uid = str(user["id"]) if user is not None else None
    topdecks_likes.attach_likes(items, user_id=uid)
    if uid:
        response.headers["Cache-Control"] = "private, no-store"
    else:
        response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=120"
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": items,
    }


@app.get("/topdecks/decks/{deck_id}")
def topdecks_deck_detail(deck_id: str, request: Request) -> dict[str, Any]:
    ensure_topdecks_data_fresh()
    did = str(deck_id or "").strip()
    row = topdecks_by_id.get(did)
    if not isinstance(row, dict):
        raise HTTPException(status_code=404, detail="未找到该比赛卡组")
    brief = _topdeck_brief(row)
    cards_map = row.get("cards") if isinstance(row.get("cards"), dict) else {}
    cards_out: list[dict[str, Any]] = []
    for raw_id, raw_qty in cards_map.items():
        cid = normalize_card_id(str(raw_id))
        qty = int(raw_qty or 0)
        if not cid or qty <= 0:
            continue
        basic = cards_by_id.get(cid) or {}
        cards_out.append(
            {
                "id": cid,
                "qty": qty,
                "name": basic.get("name") or basic.get("name_en") or cid,
                "name_en": basic.get("name_en") or "",
                "card_type": basic.get("category") or basic.get("card_type") or "",
                "is_leader": cid == normalize_card_id(str(row.get("leader") or "")),
            }
        )
    cards_out.sort(key=lambda c: (0 if c.get("is_leader") else 1, str(c.get("id") or "")))
    brief["cards"] = cards_out
    user = _read_auth_user_from_request(request)
    uid = str(user["id"]) if user is not None else None
    topdecks_likes.attach_likes([brief], user_id=uid)
    return brief


@app.post("/topdecks/likes")
def topdecks_like(request: Request, payload: TopdeckLikeRequest) -> dict[str, Any]:
    user = _require_auth_user(request)
    did = str(payload.deck_id or "").strip()
    ensure_topdecks_data_fresh()
    if did not in topdecks_by_id:
        raise HTTPException(status_code=404, detail="未找到该比赛卡组")
    try:
        return topdecks_likes.set_like(
            user_id=str(user["id"]),
            deck_id=did,
            liked=bool(payload.liked),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _deck_contains_card_base(row: dict[str, Any], base: str) -> tuple[bool, int, bool]:
    """Return (matched, qty, is_leader) for base card id (ignores alt-art suffixes)."""
    leader = normalize_card_id(str(row.get("leader") or ""))
    is_leader = bool(leader and _base_card_id(leader) == base)
    qty = 0
    cards = row.get("cards") if isinstance(row.get("cards"), dict) else {}
    for raw_id, raw_qty in cards.items():
        cid = normalize_card_id(str(raw_id))
        if not cid or _base_card_id(cid) != base:
            continue
        try:
            qty += max(0, int(raw_qty or 0))
        except (TypeError, ValueError):
            continue
    if is_leader and qty <= 0:
        qty = 1
    return (is_leader or qty > 0, qty, is_leader)


@app.get("/cards/{card_id}/tournaments")
def card_recent_tournaments(
    response: Response,
    card_id: str,
    limit: int = Query(10, ge=1, le=30),
) -> dict[str, Any]:
    """Recent tournament decks that include this card (base id; alt arts share one pool)."""
    ensure_topdecks_data_fresh()
    nid = normalize_card_id(card_id)
    if not nid:
        raise HTTPException(status_code=422, detail="card_id 不能为空")
    base = _base_card_id(nid)
    rows = topdecks_appearances_by_card.get(base) or []
    items: list[dict[str, Any]] = []
    for _, did, qty, is_leader in rows[:limit]:
        row = topdecks_by_id.get(did)
        if not isinstance(row, dict):
            continue
        brief = _topdeck_brief(row)
        brief["qty"] = qty
        brief["is_leader"] = is_leader
        items.append(brief)
    response.headers["Cache-Control"] = "public, max-age=30, s-maxage=120"
    return {
        "card_id": nid,
        "card_base_id": base,
        "total_matched": len(rows),
        "items": items,
    }


@app.get("/cards/{card_id}/comments")
def card_comments_list(
    card_id: str,
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(40, ge=1, le=100),
) -> dict[str, Any]:
    nid = normalize_card_id(card_id)
    if not nid:
        raise HTTPException(status_code=422, detail="card_id 不能为空")
    # Per full card id (each alternate art has its own comment thread).
    user = _read_auth_user_from_request(request)
    uid = str(user["id"]) if user is not None else None
    return {
        "card_id": nid,
        "card_base_id": _base_card_id(nid),
        **card_comments.list_comments(card_base_id=nid, viewer_user_id=uid, limit=limit, offset=offset),
    }


@app.post("/cards/{card_id}/comments")
def card_comments_create(card_id: str, request: Request, payload: CardCommentCreateRequest) -> dict[str, Any]:
    user = _require_auth_user(request)
    nid = normalize_card_id(card_id)
    if not nid:
        raise HTTPException(status_code=422, detail="card_id 不能为空")
    try:
        return card_comments.create_comment(
            card_base_id=nid,
            author_user_id=str(user["id"]),
            author_username=str(user["username"] or ""),
            body=payload.body,
            anonymous=bool(payload.anonymous),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/cards/comments/{comment_id}/like")
def card_comment_like(comment_id: int, request: Request, payload: CardCommentLikeRequest) -> dict[str, Any]:
    user = _require_auth_user(request)
    try:
        return card_comments.set_comment_like(
            user_id=str(user["id"]),
            comment_id=int(comment_id),
            liked=bool(payload.liked),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/cards/comments/{comment_id}/report")
def card_comment_report(comment_id: int, request: Request, payload: CardCommentReportRequest) -> dict[str, Any]:
    user = _require_auth_user(request)
    try:
        created = card_comments.create_comment_report(
            reporter_user_id=str(user["id"]),
            comment_id=int(comment_id),
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    to_email = str(
        os.getenv("COMMUNITY_REPORT_EMAIL")
        or os.getenv("BUG_REPORT_EMAIL")
        or os.getenv("RANK_APPEAL_EMAIL")
        or ""
    ).strip()
    if to_email:
        try:
            _send_email(
                to_email,
                f"[OPCG Card Comment Report] #{created.get('report_id')} · {created.get('card_base_id')}",
                (
                    f"Reporter: {user['username']} ({user['id']})\n"
                    f"Card: {created.get('card_base_id')}\n"
                    f"Comment #{created.get('comment_id')} by {created.get('comment_author')}\n"
                    f"Reason: {payload.reason}\n\n"
                    f"--- comment ---\n{created.get('comment_body')}\n"
                ),
            )
        except Exception as exc:
            print(f"[card-comment-report] email failed: {exc}")
    return {"ok": True, "report_id": created.get("report_id")}


@app.delete("/cards/comments/{comment_id}")
def card_comment_delete(comment_id: int, request: Request) -> dict[str, Any]:
    user = _require_auth_user(request)
    try:
        is_admin = bool(int(user["is_admin"] or 0))
    except Exception:
        is_admin = False
    try:
        return card_comments.soft_delete_comment(
            user_id=str(user["id"]),
            comment_id=int(comment_id),
            is_admin=is_admin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/prices/meta")
def prices_meta() -> dict[str, Any]:
    """市价库摘要：更新时间与有价卡数量。"""
    ensure_market_price_data_fresh()
    return {
        "source": "yuyu-tei",
        "currency": "JPY",
        "updated_at": market_price_updated_at or None,
        "priced_count": _count_visible_priced_entries(),
        "total_entries": len(market_price_map),
    }


@app.post("/prices/batch")
def batch_card_prices(payload: CardThumbnailBatchRequest, exact: bool = False) -> dict[str, dict[str, Any]]:
    """批量返回当前市价（不含完整历史，供价格墙使用）。"""
    out: dict[str, dict[str, Any]] = {}
    incoming = payload.ids if isinstance(payload.ids, list) else []
    for raw in incoming[:420]:
        nid = normalize_card_id(str(raw).strip())
        if not nid or nid in out:
            continue
        info = get_market_price_info(nid, exact=exact)
        if not info:
            out[nid] = {
                "card_id": nid,
                "source": "yuyu-tei",
                "currency": "JPY",
                "current_price": None,
            }
            continue
        out[nid] = {
            "card_id": nid,
            "source": info.get("source") or "yuyu-tei",
            "currency": info.get("currency") or "JPY",
            "current_price": info.get("current_price"),
            "last_seen": info.get("last_seen") or "",
            "last_checked": info.get("last_checked") or "",
        }
    return out


def _battle_user_dict(row: Any) -> dict[str, Any]:
    return {
        "user_id": _deck_owner_id_from_user_row(row),
        "username": str(row["username"] if not isinstance(row, dict) else row.get("username") or "Player"),
    }


def _read_auth_user_from_token(token: str) -> dict[str, Any] | None:
    if AUTH_BYPASS_FOR_TESTING:
        return {"user_id": "user_0", "username": "test_user"}
    token = str(token or "").strip()
    if not token:
        return None
    with auth_db_lock:
        conn = _auth_db()
        try:
            row = conn.execute(
                """
                SELECT s.token, s.expires_at, s.revoked_at, u.*
                FROM auth_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = ?
                """,
                (token,),
            ).fetchone()
        finally:
            conn.close()
    if row is None or row["revoked_at"] is not None:
        return None
    exp = _parse_iso_dt(row["expires_at"])
    now = datetime.now(timezone.utc)
    if exp is None or exp <= now:
        return None
    return _battle_user_dict(row)


def _battle_auth_from_request(request: Request) -> dict[str, Any]:
    return _battle_user_dict(_require_auth_user(request))


def _battle_catalog(card_id: str) -> dict[str, Any]:
    cid = normalize_card_id(str(card_id or ""))
    basic = dict(cards_by_id.get(cid) or cards_by_id.get(str(card_id or "")) or {})
    if not basic:
        return {}
    snap = _snapshot_to_card_fields(cid or str(card_id or ""))
    out = dict(snap)
    out.update(basic)
    for key, value in snap.items():
        if out.get(key) in (None, "", [], {}):
            out[key] = value
    if not out.get("card_type_en"):
        out["card_type_en"] = out.get("card_type") or out.get("category")
    if not out.get("colors_en"):
        out["colors_en"] = out.get("colors") or []
    out["id"] = cid or str(card_id or "")
    return out


def _battle_load_deck(user_id: str, deck_id: str) -> dict[str, Any] | None:
    with deck_store_lock:
        store = _load_decks_store()
        for deck in store.get(str(user_id), []) or []:
            if str(deck.get("id") or "") == str(deck_id):
                return {
                    "id": deck.get("id"),
                    "name": deck.get("name"),
                    "leader_card_id": deck.get("leader_card_id"),
                    "cards": _normalize_deck_cards(deck.get("cards") or {}),
                }
    return None


def _battle_ask_llm(prompt: str) -> str:
    try:
        api_key = get_api_key()
    except Exception:
        return ""
    if not _ensure_openai() or OpenAI is None:
        return ""
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=8.0)
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": "Return only compact JSON. No markdown."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=500,
        )
        return str(resp.choices[0].message.content or "").strip()
    except Exception:
        return ""


from battle import mount_battle

mount_battle(
    app,
    catalog=_battle_catalog,
    auth_from_token=_read_auth_user_from_token,
    auth_from_request=_battle_auth_from_request,
    load_deck=_battle_load_deck,
    ask_llm=_battle_ask_llm,
    send_email=_send_email,
)

from forum import mount_forum

mount_forum(
    app,
    require_auth=_require_auth_user,
    optional_auth=_read_auth_user_from_request,
    username_lookup=_username_for_owner_id,
    is_admin_lookup=_is_admin_for_owner_id,
    email_lookup=_email_for_owner_id,
    send_email=_send_email,
    site_url=_frontend_site_url(),
)


@app.get("/prices/{card_id}")
def get_card_price(card_id: str, exact: bool = False) -> dict[str, Any]:
    normalized_id = normalize_card_id(card_id)
    if not normalized_id:
        raise HTTPException(status_code=422, detail="card_id 不能为空，请输入如 ST01-004。")
    info = get_market_price_info(normalized_id, exact=exact)
    if not info:
        return {
            "card_id": normalized_id,
            "source": "yuyu-tei",
            "currency": "JPY",
            "current_price": None,
            "history": [],
            "message": "暂无价格数据，请先运行同步脚本。",
        }
    return {"card_id": normalized_id, **info}
