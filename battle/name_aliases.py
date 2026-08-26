"""Load spoken/regional card-name aliases from meta/name_aliases.json."""

from __future__ import annotations

import json
import threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_ALIASES_PATH = _ROOT / "meta" / "name_aliases.json"

_lock = threading.RLock()
_aliases_by_en: dict[str, dict] = {}
_loaded = False
_mtime: float | None = None


def _normalize_en(name_en: str | None) -> str:
    return (
        str(name_en or "")
        .strip()
        .replace(" (Parallel)", "")
        .replace("  ", " ")
    )


def reload_name_aliases(*, force: bool = False) -> None:
    global _aliases_by_en, _loaded, _mtime
    with _lock:
        try:
            mt = _ALIASES_PATH.stat().st_mtime
        except OSError:
            mt = None
        if not force and _loaded and mt == _mtime:
            return
        if not _ALIASES_PATH.is_file():
            _aliases_by_en = {}
            _mtime = mt
            _loaded = True
            return
        try:
            payload = json.loads(_ALIASES_PATH.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        out: dict[str, dict] = {}
        if isinstance(payload, dict):
            for k, v in payload.items():
                key = _normalize_en(str(k))
                if key and isinstance(v, dict):
                    out[key] = v
        _aliases_by_en = out
        _mtime = mt
        _loaded = True


def alias_texts_for_en(name_en: str | None) -> list[str]:
    """Return display + alias strings for an English card name."""
    reload_name_aliases(force=False)
    key = _normalize_en(name_en)
    if not key:
        return []
    with _lock:
        row = _aliases_by_en.get(key) or {}
    out: list[str] = []
    for item in row.get("aliases") or []:
        text = str(item or "").strip()
        if text:
            out.append(text)
    for field in ("display_hans", "display_hant"):
        text = str(row.get(field) or "").strip()
        if text:
            out.append(text)
    # de-dupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq
