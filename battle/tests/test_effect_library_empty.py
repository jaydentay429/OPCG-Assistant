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


def test_library_stats_keeps_uncovered_compiled_timings(tmp_path, monkeypatch):
    saved = _snapshot()
    lib = tmp_path / "card_effects.json"
    ovr = tmp_path / "overrides.json"
    lib.write_text(
        json.dumps(
            {
                "cards": {
                    "CARD-A": {
                        "abilities": [
                            {
                                "timing": "on_play",
                                "ops": [{"op": "draw", "count": 1}],
                                "status": "compiled",
                            },
                            {
                                "timing": "don_attached",
                                "ops": [{"op": "buff_self", "amount": 1000}],
                                "status": "compiled",
                                "require_don_attached_gte": 1,
                            },
                        ]
                    },
                    "CARD-B": {
                        "abilities": [
                            {
                                "timing": "on_ko",
                                "ops": [{"op": "unsupported", "reason": "complex_on_ko"}],
                                "status": "unsupported",
                            }
                        ]
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    ovr.write_text(
        json.dumps(
            {
                "cards": {
                    "CARD-A": {
                        "abilities": [
                            {
                                "timing": "on_play",
                                "ops": [{"op": "draw", "count": 1}],
                                "status": "verified",
                            }
                        ]
                    },
                    "CARD-B": {
                        "abilities": [
                            {
                                "timing": "on_ko",
                                "ops": [{"op": "ko", "count": 1}],
                                "status": "verified",
                            }
                        ]
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPCG_CARD_EFFECTS", str(lib))
    monkeypatch.setenv("OPCG_CARD_EFFECT_OVERRIDES", str(ovr))
    try:
        el.reload_effect_library(force=True)
        stats = el.library_stats()
        assert stats["library_cards"] == 2
        assert stats["override_cards"] == 2
        # on_play and on_ko are replaced; don_attached stays compiled and runnable.
        assert stats["abilities_by_status"]["verified"] == 2
        assert stats["abilities_by_status"]["compiled"] == 1
        assert stats["abilities_by_status"]["unsupported"] == 0
        assert stats["runnable_abilities"] == 3
        assert stats["unsupported_abilities"] == 0
    finally:
        _restore(saved)
