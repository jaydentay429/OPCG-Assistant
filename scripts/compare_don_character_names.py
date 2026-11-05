#!/usr/bin/env python3
"""Read-only: DON!! subtitles whose Chinese name differs from the character cards.

Pairs each illustrated DON!! card with character or leader cards that share its
English name or Japanese name, then compares the Traditional Chinese wording.
Simplified and Traditional spellings of the same words count as the same name.
A shorter name inside a longer one (凱薩 / 凱薩克勞恩) counts as the same name.

Prints one row per character. Does not write the index or the nickname table.

    python3 scripts/compare_don_character_names.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from card_nicknames import nickname_groups, normalize_nickname, text_variants  # noqa: E402

INDEX_PATH = ROOT / "index" / "cards_by_id.json"
JA_PATH = ROOT / "index" / "card_names_ja.json"

_DON_EN = re.compile(r"^DON!!\s*Card\s*\((.*)\)\s*$", re.IGNORECASE)
_ZH_NOISE = re.compile(r"(?:[（(][^）)]*[）)])|異圖卡|异图卡")
_EN_NOISE = re.compile(r"[^a-z0-9]")
_PARALLEL_ZH = {"平行", "超級平行", "超级平行"}
_PARALLEL_EN = {"parallel", "super parallel"}
_PARALLEL_JP = {"パラレル", "スーパーパラレル"}
_CHARACTER_TYPES = {"character", "leader", "角色", "領袖", "领袖", "領航", "领航"}


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _fold_zh(text: str) -> str:
    raw = _ZH_NOISE.sub("", str(text or ""))
    folded = []
    for variant in text_variants(raw) or [raw]:
        norm = normalize_nickname(variant)
        if norm:
            folded.append(norm)
    # Prefer the traditional form when OpenCC produced one.
    return folded[-1] if folded else ""


def _fold_en(text: str) -> str:
    return _EN_NOISE.sub("", str(text or "").lower())


def _same_wording(a: str, b: str) -> bool:
    left, right = _fold_zh(a), _fold_zh(b)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _card_type(row: dict) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in ("card_type", "category", "card_type_en", "category_en")
    ).lower()


def _is_don(card_id: str, row: dict) -> bool:
    return card_id.startswith("DON") or "don" in _card_type(row)


def _is_character(row: dict) -> bool:
    text = _card_type(row)
    return any(token in text for token in _CHARACTER_TYPES)


def _don_en_core(name_en: str) -> str:
    match = _DON_EN.match(str(name_en or "").strip())
    if not match:
        return ""
    parts = [part.strip() for part in match.group(1).split("/") if part.strip()]
    parts = [part for part in parts if part.lower() not in _PARALLEL_EN]
    return parts[0] if parts else ""


def _don_zh_core(name: str) -> str:
    text = str(name or "").strip()
    if text.startswith("咚卡"):
        text = text[2:].lstrip("・")
    parts = [part.strip() for part in text.split("・") if part.strip()]
    parts = [part for part in parts if part not in _PARALLEL_ZH]
    return "・".join(parts)


def _don_jp_core(name_jp: str) -> str:
    parts = re.findall(r"\(([^()]*)\)", str(name_jp or ""))
    parts = [part.strip() for part in parts if part.strip() and part.strip() not in _PARALLEL_JP]
    parts = [part for part in parts if "パラレル" not in part]
    return parts[0] if parts else ""


def _ja_name(row: dict, card_id: str, ja_by_id: dict[str, str]) -> str:
    return str(row.get("name_ja") or row.get("name_jp") or ja_by_id.get(card_id) or "").strip()


def _norms(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for variant in text_variants(text):
        norm = normalize_nickname(variant)
        if norm and norm not in seen:
            seen.add(norm)
            found.append(norm)
    return found


def _mentioned(group, text: str) -> bool:
    """True when a surface of this group appears in ``text`` (or is the whole name)."""
    norms = _norms(text)
    for surface in group.surfaces:
        for surface_norm in _norms(surface):
            # A one-character nickname only counts when it is the whole name.
            # Otherwise 羅 would mark unrelated names as already linked.
            if any(
                surface_norm == norm or (len(surface_norm) >= 2 and surface_norm in norm)
                for norm in norms
            ):
                return True
    return False


def _linked(don_zh: str, character_zh: str) -> bool:
    for group in nickname_groups():
        if _mentioned(group, don_zh) and _mentioned(group, character_zh):
            return True
    return False


def mismatches() -> list[dict[str, str]]:
    cards = _load_json(INDEX_PATH)
    ja_by_id = _load_json(JA_PATH)
    by_en: dict[str, list[str]] = {}
    by_jp: dict[str, list[str]] = {}
    for card_id, row in cards.items():
        if not isinstance(row, dict) or _is_don(str(card_id), row) or not _is_character(row):
            continue
        en = _fold_en(str(row.get("name_en") or ""))
        if en:
            by_en.setdefault(en, []).append(str(card_id))
        jp = _ja_name(row, str(card_id), ja_by_id)
        # Character-card Japanese names are the whole title. DON cores match that title.
        if jp and not jp.startswith("ドン"):
            by_jp.setdefault(jp, []).append(str(card_id))

    grouped: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for card_id, row in cards.items():
        if not isinstance(row, dict) or not _is_don(str(card_id), row):
            continue
        en_core = _don_en_core(str(row.get("name_en") or ""))
        zh_core = _don_zh_core(str(row.get("name") or ""))
        jp_core = _don_jp_core(str(row.get("name_jp") or _ja_name(row, str(card_id), ja_by_id)))
        if not zh_core or not (en_core or jp_core):
            continue
        if jp_core.endswith("モチーフ") or zh_core.endswith("圖案"):
            continue
        ids: list[str] = []
        if en_core:
            ids.extend(by_en.get(_fold_en(en_core), []))
        if jp_core:
            ids.extend(by_jp.get(jp_core, []))
        character_ids: list[str] = []
        seen_ids: set[str] = set()
        for cid in ids:
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            character_ids.append(cid)
        if not character_ids:
            continue
        names = [
            _ZH_NOISE.sub("", str(cards[cid].get("name") or "")).strip("・ ")
            for cid in character_ids
        ]
        names = [name for name in names if name]
        if not names:
            continue
        primary, _count = Counter(names).most_common(1)[0]
        if _same_wording(zh_core, primary):
            continue
        key = (en_core, jp_core, zh_core, primary)
        slot = grouped.get(key)
        if slot is None:
            slot = {
                "en": en_core,
                "jp": jp_core,
                "don_zh": zh_core,
                "character_zh": primary,
                "character_ids": character_ids[0],
                "don_ids": str(card_id),
                "nickname": "linked" if _linked(zh_core, primary) else "missing",
            }
            grouped[key] = slot
        elif str(card_id) not in slot["don_ids"].split(","):
            slot["don_ids"] += "," + str(card_id)
    return sorted(grouped.values(), key=lambda row: (row["nickname"], row["en"].lower(), row["don_zh"]))


def main() -> int:
    rows = mismatches()
    if not rows:
        print("No DON!! / character-card name mismatches.")
        return 0
    missing = sum(1 for row in rows if row["nickname"] == "missing")
    print(f"{len(rows)} mismatched character names ({missing} not in card_nicknames.json)")
    print("nickname\ten\tjp\tdon_zh\tcharacter_zh\texample_card\tdon_ids")
    for row in rows:
        print(
            "\t".join(
                [
                    row["nickname"],
                    row["en"],
                    row["jp"],
                    row["don_zh"],
                    row["character_zh"],
                    row["character_ids"],
                    row["don_ids"],
                ]
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
