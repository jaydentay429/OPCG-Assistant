"""Effect-data gate for sets listed in ``index/set_legality.json``.

Release dates and tournament-legal dates in that file do not block casual, AI,
or ranked play. Any catalog card can be played on any day. Sets listed there
still need runnable battle effect data. Official banned cards stay in
``official_restriction`` and are not decided here. ``OPCG_BATTLE_TODAY`` is
ignored.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parent.parent
_PATH = _ROOT / "index" / "set_legality.json"
_SET_CODE = re.compile(r"^([A-Z]+\d+)-", re.IGNORECASE)

BattleMode = Literal["casual", "ranked"]
BlockReason = Literal["no_effect"]


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


def battle_today(on_date: date | None = None) -> date:
    """Malaysia calendar day. An explicit ``on_date`` wins. ``OPCG_BATTLE_TODAY`` is ignored."""
    if on_date is not None:
        return on_date
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
    """``mode`` and ``on_date`` do not apply a release or tournament-date gate."""
    del mode, on_date
    spec = load_set_legality()["sets"].get(set_code_of(card_id) or "")
    if not spec:
        return None
    if not card_has_battle_effect_data(card_id):
        return "no_effect"
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


def format_set_legality_error(
    leader_id: str,
    cards: dict[str, int] | None,
    *,
    mode: BattleMode,
    on_date: date | None = None,
) -> str | None:
    missing = [
        cid
        for cid, reason in legality_blocks(leader_id, cards, mode=mode, on_date=on_date)
        if reason == "no_effect"
    ]
    if not missing:
        return None
    sample = ", ".join(missing[:8])
    return f"{sample} cannot be used in battle because battle effect data is missing."


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
