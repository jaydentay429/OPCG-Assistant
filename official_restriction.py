"""Official ONE PIECE CARD GAME banned / restricted / pair list.

The list is `index/official_restriction_list.json`. Variants such as ``-P1``
inherit the base card number, the same way deck copy limits already do.

``effective_date`` is the English-site date and is what badges and checks use.
``asia_effective_date`` is recorded only when the Asia English site publishes
a different date. Both regions are already in effect for every current entry.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LIST_PATH = ROOT / "index" / "official_restriction_list.json"

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_OFFICIAL_HOSTS = (
    "https://en.onepiece-cardgame.com/",
    "https://asia-en.onepiece-cardgame.com/",
)


def normalize_restriction_id(raw: str) -> str:
    cleaned = str(raw or "").strip().upper().replace("_", "-").replace(" ", "")
    cleaned = cleaned.replace("－", "-")
    cleaned = re.sub(r"[^A-Z0-9-]", "", cleaned)
    folded = re.match(r"^([A-Z]{2,4})-?(\d{2})-(\d{3}(?:-[A-Z0-9]+)?)$", cleaned)
    if folded:
        cleaned = f"{folded.group(1)}{folded.group(2)}-{folded.group(3)}"
    return cleaned


def restriction_base_id(raw: str) -> str:
    """Base card number. ``OP14-020-P1`` and ``op14-020-p1`` are ``OP14-020``."""
    card_id = normalize_restriction_id(raw)
    don = re.match(r"^(DON[A-Z0-9]*-\d{3,5})(?:-[A-Z0-9]+)?$", card_id)
    if don:
        return don.group(1)
    promo = re.match(r"^(P-\d{3})(?:-[A-Z0-9]+)?$", card_id)
    if promo:
        return promo.group(1)
    matched = re.match(r"^([A-Z]{2,4}\d{0,2}-\d{3})", card_id)
    return matched.group(1) if matched else card_id


@dataclass(frozen=True)
class RestrictionHit:
    kind: str
    effective_date: str
    card_ids: tuple[str, ...] = ()
    left_ids: tuple[str, ...] = ()
    right_ids: tuple[str, ...] = ()


def _entry_card_ids(entry: dict[str, Any]) -> list[str]:
    kind = str(entry.get("type") or "")
    if kind == "pair":
        raw_ids = entry.get("card_ids") or []
        return [restriction_base_id(str(item)) for item in raw_ids]
    card_id = str(entry.get("card_id") or "")
    return [restriction_base_id(card_id)] if card_id else []


def _require_https(url: str, label: str) -> None:
    if not any(str(url).startswith(host) for host in _OFFICIAL_HOSTS):
        raise ValueError(f"{label} is not an official restriction URL: {url}")


def validate_restriction_document(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("restriction list is missing entries")
    seen_banned: set[str] = set()
    seen_restricted: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"restriction entry {index} is not an object")
        kind = str(entry.get("type") or "")
        if kind not in {"banned", "restricted", "pair"}:
            raise ValueError(f"restriction entry {index} has type {kind!r}")
        effective = str(entry.get("effective_date") or "")
        if not _DATE.match(effective):
            raise ValueError(f"restriction entry {index} has no ISO effective_date")
        date.fromisoformat(effective)
        _require_https(str(entry.get("source_url") or ""), f"entry {index} source_url")
        asia_date = entry.get("asia_effective_date")
        if asia_date is not None:
            if not _DATE.match(str(asia_date)):
                raise ValueError(f"restriction entry {index} has a bad Asia date")
            date.fromisoformat(str(asia_date))
            _require_https(str(entry.get("asia_source_url") or ""), f"entry {index} asia_source_url")
        ids = _entry_card_ids(entry)
        if kind == "pair":
            if len(ids) != 2 or not ids[0] or not ids[1] or ids[0] == ids[1]:
                raise ValueError(f"restriction pair {index} needs two different card ids")
            key = (ids[0], ids[1])
            if key in seen_pairs:
                raise ValueError(f"duplicate banned pair {key}")
            seen_pairs.add(key)
            continue
        if len(ids) != 1 or not ids[0]:
            raise ValueError(f"restriction entry {index} needs one card_id")
        bucket = seen_banned if kind == "banned" else seen_restricted
        if ids[0] in bucket:
            raise ValueError(f"duplicate {kind} card {ids[0]}")
        bucket.add(ids[0])
    return entries


@lru_cache(maxsize=1)
def load_restriction_entries() -> tuple[dict[str, Any], ...]:
    payload = json.loads(LIST_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("restriction list must be an object")
    return tuple(validate_restriction_document(payload))


def _as_of(on_date: date | None) -> date:
    return on_date or date.today()


def _is_effective(entry: dict[str, Any], on_date: date) -> bool:
    return date.fromisoformat(str(entry["effective_date"])) <= on_date


def _deck_presence(leader_id: str, cards: dict[str, Any] | None) -> dict[str, list[str]]:
    """Base card id → actual ids present with a positive count."""
    present: dict[str, list[str]] = {}

    def add(raw: str, qty: int) -> None:
        if qty <= 0:
            return
        actual = normalize_restriction_id(raw)
        if not actual:
            return
        base = restriction_base_id(actual)
        bucket = present.setdefault(base, [])
        if actual not in bucket:
            bucket.append(actual)

    add(leader_id, 1 if str(leader_id or "").strip() else 0)
    for raw, qty in (cards or {}).items():
        try:
            count = int(qty or 0)
        except (TypeError, ValueError):
            count = 0
        add(str(raw), count)
    return present


def restriction_violations(
    leader_id: str,
    cards: dict[str, Any] | None,
    *,
    on_date: date | None = None,
    entries: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> list[RestrictionHit]:
    """Effective official violations for a leader plus main deck.

    ``entries`` overrides the on-disk list so tests can cover restricted cards
    without adding any to the official file.
    """
    today = _as_of(on_date)
    rows = list(entries) if entries is not None else list(load_restriction_entries())
    present = _deck_presence(leader_id, cards)
    counts: dict[str, int] = {}
    leader_actual = normalize_restriction_id(leader_id)
    if leader_actual:
        counts[restriction_base_id(leader_actual)] = 1
    for raw, qty in (cards or {}).items():
        try:
            count = int(qty or 0)
        except (TypeError, ValueError):
            count = 0
        if count <= 0:
            continue
        actual = normalize_restriction_id(str(raw))
        if not actual:
            continue
        base = restriction_base_id(actual)
        if actual == leader_actual:
            continue
        counts[base] = counts.get(base, 0) + count

    hits: list[RestrictionHit] = []
    for entry in rows:
        if not _is_effective(entry, today):
            continue
        kind = str(entry["type"])
        effective = str(entry["effective_date"])
        ids = _entry_card_ids(entry)
        if kind in {"banned", "restricted"}:
            base = ids[0]
            if base not in present:
                continue
            if kind == "restricted" and counts.get(base, 0) <= 1:
                continue
            hits.append(
                RestrictionHit(
                    kind=kind,
                    effective_date=effective,
                    card_ids=tuple(sorted(present[base])),
                )
            )
            continue
        left, right = ids
        if left in present and right in present:
            hits.append(
                RestrictionHit(
                    kind="pair",
                    effective_date=effective,
                    left_ids=tuple(sorted(present[left])),
                    right_ids=tuple(sorted(present[right])),
                )
            )
    hits.sort(key=lambda hit: (hit.kind, hit.card_ids, hit.left_ids, hit.right_ids, hit.effective_date))
    return hits


def _join_ids(ids: tuple[str, ...], *, lang: str) -> str:
    return ("、" if lang == "zh" else ", ").join(ids)


def format_restriction_error(hits: list[RestrictionHit], *, lang: str = "en") -> str | None:
    if not hits:
        return None
    parts: list[str] = []
    for hit in hits:
        if hit.kind == "banned":
            ids = _join_ids(hit.card_ids, lang=lang)
            if lang == "zh":
                parts.append(f"禁用卡 {ids} 不能放入卡组（{hit.effective_date} 起禁用）。")
            else:
                parts.append(
                    f"Banned card {ids} cannot be included in a deck (banned from {hit.effective_date})."
                )
        elif hit.kind == "restricted":
            ids = _join_ids(hit.card_ids, lang=lang)
            if lang == "zh":
                parts.append(f"限制卡 {ids} 每套卡组最多 1 张（{hit.effective_date} 起限制）。")
            else:
                parts.append(
                    f"Restricted card {ids} is limited to 1 copy (restricted from {hit.effective_date})."
                )
        else:
            left = _join_ids(hit.left_ids, lang=lang)
            right = _join_ids(hit.right_ids, lang=lang)
            if lang == "zh":
                parts.append(f"禁用组合 {left} 与 {right} 不能放在同一套卡组（{hit.effective_date} 起）。")
            else:
                parts.append(
                    f"Banned pair {left} and {right} cannot be in the same deck (from {hit.effective_date})."
                )
    return " ".join(parts)


def official_restriction_error(
    leader_id: str,
    cards: dict[str, Any] | None,
    *,
    lang: str = "en",
    on_date: date | None = None,
) -> str | None:
    return format_restriction_error(
        restriction_violations(leader_id, cards, on_date=on_date),
        lang=lang,
    )
