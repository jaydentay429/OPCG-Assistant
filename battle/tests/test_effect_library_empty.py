"""The runtime loader must survive a missing or empty card_effects.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import battle.effect_library as el  # noqa: E402


def _snapshot():
    with el._lock:
        return (
            el._library,
            el._overrides,
            el._loaded,
            el._library_mtime,
            el._overrides_mtime,
        )


def _restore(saved) -> None:
    with el._lock:
        (
            el._library,
            el._overrides,
            el._loaded,
            el._library_mtime,
            el._overrides_mtime,
        ) = saved


def test_loader_tolerates_missing_empty_and_whitespace(tmp_path, monkeypatch):
    saved = _snapshot()
    overrides = tmp_path / "overrides.json"
    overrides.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OPCG_CARD_EFFECT_OVERRIDES", str(overrides))
    try:
        missing = tmp_path / "absent" / "card_effects.json"
        monkeypatch.setenv("OPCG_CARD_EFFECTS", str(missing))
        el.reload_effect_library(force=True)
        entry = el.get_card_entry("OP01-001")
        assert entry["card_id"] == "OP01-001"
        assert entry["abilities"] == []
        assert el.lookup_runnable_ability("OP01-001", "on_play") is None
        el.ensure_loaded()

        empty = tmp_path / "empty.json"
        empty.write_bytes(b"")
        monkeypatch.setenv("OPCG_CARD_EFFECTS", str(empty))
        el.reload_effect_library(force=True)
        assert el.get_card_entry("OP01-001")["abilities"] == []

        blank = tmp_path / "blank.json"
        blank.write_text("\n\t  \n", encoding="utf-8")
        monkeypatch.setenv("OPCG_CARD_EFFECTS", str(blank))
        el.reload_effect_library(force=True)
        assert el.get_card_entry("OP99-999")["abilities"] == []

        good = tmp_path / "good.json"
        good.write_text(
            json.dumps(
                {
                    "cards": {
                        "OP01-001": {
                            "version": 1,
                            "abilities": [
                                {
                                    "timing": "on_play",
                                    "summary": "draw",
                                    "ops": [{"op": "draw", "count": 1}],
                                    "status": "compiled",
                                }
                            ],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("OPCG_CARD_EFFECTS", str(good))
        el.reload_effect_library(force=True)
        ability = el.lookup_runnable_ability("OP01-001", "on_play")
        assert ability is not None
        assert ability["ops"][0]["op"] == "draw"
    finally:
        _restore(saved)
