"""Set release and tournament-legal dates shared with the frontend.

The schedule lives in ``index/set_legality.json``. Casual and AI play may use a
card from one of those sets on or after its release date, and only when the
card has runnable battle effect data. Ranked play waits until the
tournament-legal date and still requires effect data. Official banned cards
stay in ``official_restriction`` and are not decided here.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parent.parent
_PATH = _ROOT / "index" / "set_legality.json"
_SET_CODE = re.compile(r"^([A-Z]+\d+)-", re.IGNORECASE)
_ISO_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_BATTLE_TODAY_ENV = "OPCG_BATTLE_TODAY"

BattleMode = Literal["casual", "ranked"]
BlockReason = Literal["unreleased", "no_effect", "not_ranked_legal"]


@lru_cache(maxsize=1)
def load_set_legality() -> dict[str, Any]:
    raw = json.loads(_PATH.read_text(encoding="utf-8"))
    sets = {}
    for row in raw.get("sets") or []:
        code = str(row.get("code") or "").strip().upper()
        if not code:
            continue
        sets[code] = {
            "code": code,
            "release_date": date.fromisoformat(str(row["release_date"])),
            "tournament_legal_date": date.fromisoformat(str(row["tournament_legal_date"])),
            "tournament_legal_assumed": bool(row.get("tournament_legal_assumed")),
        }
    return {
        "timezone": str(raw.get("timezone") or "Asia/Kuala_Lumpur"),
        "sets": sets,
    }


def _env_battle_today() -> date | None:
    raw = os.getenv(_BATTLE_TODAY_ENV, "").strip()
    match = _ISO_DAY.fullmatch(raw)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def battle_today(on_date: date | None = None) -> date:
    if on_date is not None:
        return on_date
    override = _env_battle_today()
    if override is not None:
        return override
    tz = ZoneInfo(load_set_legality()["timezone"])
    return datetime.now(tz).date()


def set_code_of(card_id: str) -> str | None:
    match = _SET_CODE.match(str(card_id or "").strip().upper())
    if not match:
        return None
    return match.group(1).upper()


def card_has_battle_effect_data(card_id: str) -> bool:
    """True when compiled library or override data can actually resolve.

    Parallel arts inherit the base card. Text templates and keyword-only
    reminders are not effect data: a card whose text needs an effect stays
    blocked until a runnable ability exists.
    """
    from battle.effect_library import ensure_loaded, get_abilities
    from battle.effect_schema import ability_is_runnable

    ensure_loaded()
    return any(ability_is_runnable(ability) for ability in get_abilities(card_id))


def _iter_deck_ids(leader_id: str, cards: dict[str, int] | None) -> list[str]:
    ids: list[str] = []
    leader = str(leader_id or "").strip()
    if leader:
        ids.append(leader)
    for cid, qty in (cards or {}).items():
        if int(qty or 0) <= 0:
            continue
        text = str(cid or "").strip()
        if text:
            ids.append(text)
    return ids


def card_legality_block(
    card_id: str,
    *,
    mode: BattleMode,
    on_date: date | None = None,
) -> BlockReason | None:
    spec = load_set_legality()["sets"].get(set_code_of(card_id) or "")
    if not spec:
        return None
    today = battle_today(on_date)
    if today < spec["release_date"]:
        return "unreleased"
    if not card_has_battle_effect_data(card_id):
        return "no_effect"
    if mode == "ranked" and today < spec["tournament_legal_date"]:
        return "not_ranked_legal"
    return None


def _unique(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for cid in ids:
        key = cid.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(cid)
    return out


def legality_blocks(
    leader_id: str,
    cards: dict[str, int] | None,
    *,
    mode: BattleMode,
    on_date: date | None = None,
) -> list[tuple[str, BlockReason]]:
    blocks: list[tuple[str, BlockReason]] = []
    for cid in _unique(_iter_deck_ids(leader_id, cards)):
        reason = card_legality_block(cid, mode=mode, on_date=on_date)
        if reason:
            blocks.append((cid, reason))
    return blocks


def ranked_blocked_card_ids(
    leader_id: str,
    cards: dict[str, int] | None,
    *,
    on_date: date | None = None,
) -> list[str]:
    return sorted(cid for cid, _reason in legality_blocks(leader_id, cards, mode="ranked", on_date=on_date))


def _set_phrase(card_ids: list[str], *, field: str) -> str:
    specs = load_set_legality()["sets"]
    parts: list[str] = []
    seen: set[str] = set()
    for cid in card_ids:
        code = set_code_of(cid)
        spec = specs.get(code or "")
        if not spec or code in seen:
            continue
        seen.add(code)
        when = spec[field].isoformat()
        assumed = ""
        if field == "tournament_legal_date" and spec["tournament_legal_assumed"]:
            assumed = ", assumed from the 7-day rule"
        parts.append(f"{code} {when}{assumed}")
    return "; ".join(parts)


def format_set_legality_error(
    leader_id: str,
    cards: dict[str, int] | None,
    *,
    mode: BattleMode,
    on_date: date | None = None,
) -> str | None:
    grouped: dict[BlockReason, list[str]] = {"unreleased": [], "no_effect": [], "not_ranked_legal": []}
    for cid, reason in legality_blocks(leader_id, cards, mode=mode, on_date=on_date):
        grouped[reason].append(cid)
    parts: list[str] = []
    if grouped["unreleased"]:
        sample = ", ".join(grouped["unreleased"][:8])
        parts.append(
            f"{sample} cannot be used in battle before the set release date "
            f"({_set_phrase(grouped['unreleased'], field='release_date')}, Malaysia time)."
        )
    if grouped["no_effect"]:
        sample = ", ".join(grouped["no_effect"][:8])
        parts.append(
            f"{sample} cannot be used in battle because battle effect data is missing."
        )
    if grouped["not_ranked_legal"]:
        sample = ", ".join(grouped["not_ranked_legal"][:8])
        parts.append(
            f"{sample} cannot be used in ranked before the tournament-legal date "
            f"({_set_phrase(grouped['not_ranked_legal'], field='tournament_legal_date')}, Malaysia time). "
            "Casual and AI play can use the card once it is released and has effect data."
        )
    if not parts:
        return None
    return " ".join(parts)


def casual_deck_legality_error(
    leader_id: str,
    cards: dict[str, int] | None,
    *,
    on_date: date | None = None,
) -> str | None:
    return format_set_legality_error(leader_id, cards, mode="casual", on_date=on_date)


def ranked_set_legality_error(
    leader_id: str,
    cards: dict[str, int] | None,
    *,
    on_date: date | None = None,
) -> str | None:
    return format_set_legality_error(leader_id, cards, mode="ranked", on_date=on_date)
