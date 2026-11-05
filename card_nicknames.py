"""Nickname and alternate-translation groups for card search.

Edit ``index/card_nicknames.json`` to add a character. Each group:

- ``canonical``: traditional-Chinese name search should treat as the real name
- ``match``: official or distinctive names that attach the group to a card
  (substring). Short Latin keys (under 5 letters) attach only when the whole
  name equals them, so ``Law`` does not stick to ``Claw``.
- ``equals``: names that attach only on a whole-field match (``King``, ``Queen``)
- ``aliases``: extra queries, including short nicknames and wrong translations

Short nicknames belong in ``aliases``, not ``match``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
NICKNAMES_PATH = _ROOT / "index" / "card_nicknames.json"
_NORM_RE = re.compile(r"[^0-9a-z\u4e00-\u9fffぁ-んァ-ヶー]")
_LATIN_RE = re.compile(r"[0-9a-z]+")

try:
    from opencc import OpenCC as _OpenCC

    _T2S = _OpenCC("t2s")
    _S2T = _OpenCC("s2t")
except Exception:
    _T2S = None
    _S2T = None


def normalize_nickname(text: str) -> str:
    raw = str(text or "").strip().lower()
    raw = re.sub(r"\s+", "", raw)
    return _NORM_RE.sub("", raw)


def _convert(text: str, converter: object) -> str:
    if not text or converter is None:
        return str(text or "")
    try:
        return str(converter.convert(text))  # type: ignore[attr-defined]
    except Exception:
        return str(text or "")


def text_variants(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in (raw, _convert(raw, _T2S), _convert(raw, _S2T)):
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _variant_norms(text: str) -> list[str]:
    norms: list[str] = []
    seen: set[str] = set()
    for variant in text_variants(text):
        norm = normalize_nickname(variant)
        if norm and norm not in seen:
            seen.add(norm)
            norms.append(norm)
    return norms


@dataclass
class NicknameGroup:
    id: str
    canonical: str
    match: list[str] = field(default_factory=list)
    equals: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    surfaces: list[str] = field(default_factory=list)
    contains_norms: list[str] = field(default_factory=list)
    equals_norms: list[str] = field(default_factory=list)
    surface_norms: set[str] = field(default_factory=set)
    # Distinctive names added when the query is exactly one surface of this group.
    expansions: list[str] = field(default_factory=list)


_groups: list[NicknameGroup] = []


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _add_contains(bucket: list[str], seen: set[str], text: str) -> None:
    for norm in _variant_norms(text):
        if norm in seen:
            continue
        latin = _LATIN_RE.fullmatch(norm) is not None
        if latin and len(norm) < 5:
            continue
        if len(norm) < 2:
            continue
        seen.add(norm)
        bucket.append(norm)


def _add_equals(bucket: list[str], seen: set[str], text: str) -> None:
    for norm in _variant_norms(text):
        if norm and norm not in seen:
            seen.add(norm)
            bucket.append(norm)


def _absorb_match_key(
    contains: list[str],
    contains_seen: set[str],
    equals_norms: list[str],
    equals_seen: set[str],
    text: str,
) -> None:
    """Long keys attach by substring. Short Latin and 1-character keys attach by equality."""
    _add_contains(contains, contains_seen, text)
    for norm in _variant_norms(text):
        latin = _LATIN_RE.fullmatch(norm) is not None
        if (latin and len(norm) < 5) or len(norm) < 2:
            _add_equals(equals_norms, equals_seen, text)
            break


def reload_card_nicknames() -> list[NicknameGroup]:
    """Read the JSON table. Safe to call again after the file changes."""
    global _groups
    if not NICKNAMES_PATH.is_file():
        _groups = []
        return _groups
    try:
        payload = json.loads(NICKNAMES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _groups = []
        return _groups
    rows = payload.get("groups") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        _groups = []
        return _groups
    loaded: list[NicknameGroup] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        gid = str(row.get("id") or "").strip()
        canonical = str(row.get("canonical") or "").strip()
        if not gid or not canonical:
            continue
        match = [str(x).strip() for x in (row.get("match") or []) if str(x).strip()]
        equals = [str(x).strip() for x in (row.get("equals") or []) if str(x).strip()]
        aliases = [str(x).strip() for x in (row.get("aliases") or []) if str(x).strip()]
        surfaces = _dedupe([canonical, *match, *equals, *aliases])
        contains: list[str] = []
        contains_seen: set[str] = set()
        equals_norms: list[str] = []
        equals_seen: set[str] = set()
        for text in (canonical, *match):
            _absorb_match_key(contains, contains_seen, equals_norms, equals_seen, text)
        for text in equals:
            _add_equals(equals_norms, equals_seen, text)
        surface_norms: set[str] = set()
        for text in surfaces:
            surface_norms.update(_variant_norms(text))
        loaded.append(
            NicknameGroup(
                id=gid,
                canonical=canonical,
                match=match,
                equals=equals,
                aliases=aliases,
                surfaces=surfaces,
                contains_norms=contains,
                equals_norms=equals_norms,
                surface_norms=surface_norms,
                expansions=_dedupe([canonical, *match, *equals]),
            )
        )
    _groups = loaded
    return _groups


def nickname_groups() -> list[NicknameGroup]:
    if not _groups:
        reload_card_nicknames()
    return _groups


def _field_norms(text: str) -> list[str]:
    return _variant_norms(text)


def surface_forms_for_texts(*parts: str | None) -> list[str]:
    """Alias and alternate names to index on a card that matches any group."""
    field_norms: list[str] = []
    for part in parts:
        field_norms.extend(_field_norms(str(part or "")))
    if not field_norms:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for group in nickname_groups():
        matched = False
        for norm in field_norms:
            if norm in group.equals_norms or any(key and key in norm for key in group.contains_norms):
                matched = True
                break
        if not matched:
            continue
        for surface in group.surfaces:
            if surface not in seen:
                seen.add(surface)
                out.append(surface)
    return out


def extra_query_texts(query: str) -> list[str]:
    """When the whole query is one nickname, also search that group's real names.

    Short aliases are not copied onto unrelated queries. 「罗宾」 does not expand
    just because 「罗」 is a Law nickname.
    """
    query_norms = set(_field_norms(query))
    if not query_norms:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for group in nickname_groups():
        if not (query_norms & group.surface_norms):
            continue
        for text in group.expansions:
            if text not in seen:
                seen.add(text)
                out.append(text)
    return out
