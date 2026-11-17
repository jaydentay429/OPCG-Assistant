"""OP18 official cardlist coverage after the JP/EN official import."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def _op18_bases() -> list[str]:
    return [f"OP18-{i:03d}" for i in range(1, 120)]


def test_op18_has_all_official_base_cards() -> None:
    missing = [cid for cid in _op18_bases() if cid not in INDEX]
    assert missing == []
    assert len(_op18_bases()) == 119


def test_op18_026_is_sanji_not_chimney() -> None:
    row = INDEX["OP18-026"]
    assert row["name_en"] == "Sanji"
    assert row["name"] == "香吉士"
    assert row.get("preview") in (None, False)
    chimney = INDEX["OP18-028"]
    assert chimney["name_en"] == "Chimney"
    assert chimney["name"] == "琪姆妮"


def test_op18_official_rows_are_not_preview() -> None:
    for cid in _op18_bases():
        row = INDEX[cid]
        assert not row.get("preview"), cid
        assert not row.get("manual_source"), cid
        assert row.get("name")
        assert row.get("name_en")
        assert row.get("pack_id") == "OP-18"


def test_op18_english_comes_from_official_en() -> None:
    assert INDEX["OP18-001"]["name_en"] == "Karoo"
    assert INDEX["OP18-060"]["name_en"] == "Saint Gunko"
    assert INDEX["OP18-119"]["name_en"] == "Saint Shamrock"


def test_op18_existing_parallels_remain_preview() -> None:
    for cid in ("OP18-021-P1", "OP18-060-P1", "OP18-119-P1", "OP18-119-P2"):
        row = INDEX[cid]
        assert row.get("preview") is True
        assert row["name"] == INDEX[cid.split("-P")[0]]["name"]
