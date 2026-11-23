"""ST37 / ST38 leaked cards: unconfirmed screenshot rows that official sync replaces."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sync_card_images  # noqa: E402
from manual_cards import apply_manual_cards, load_manual_cards  # noqa: E402
from sync_official_cards import ParsedCard, merge_index  # noqa: E402

LEAKED = (
    "ST37-001",
    "ST37-006",
    "ST37-007",
    "ST37-015",
    "ST38-001",
    "ST38-004",
    "ST38-008",
    "ST38-015",
)


def _index() -> dict:
    return json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def test_only_the_eight_revealed_cards_are_added():
    index = _index()
    st37_38 = sorted(k for k in index if k.startswith(("ST37", "ST38")))
    assert st37_38 == sorted(LEAKED)
    for cid in LEAKED:
        row = index[cid]
        assert row["preview"] is True
        assert row["manual_source"] == "screenshot"
        assert row["text_origin"] == "self_translated_temporary"
        assert row["unconfirmed"] is True
        assert row["temp_image"] is True
        assert row["image_source"].startswith("https://akihabara-cardshop.com/")
        assert row["reveal_source"] == "https://www.youtube.com/watch?v=JZFCeHhv_nY"
        assert row["name"] and row["name_en"] and row["name_ja"] and row["effect"] and row["effect_en"]


def test_leaked_card_stats_match_the_cross_checked_sources():
    index = _index()
    luffy = index["ST37-001"]
    assert (luffy["card_type"], luffy["life"], luffy["power"]) == ("Leader", 3, 5000)
    assert luffy["colors_en"] == ["Red", "Blue"]
    ace = index["ST37-006"]
    assert (ace["cost"], ace["power"], ace["rarity"]) == (8, 8000, "C")
    assert "−3000" in ace["effect_en"] and "-3000" in ace["effect"]
    croc = index["ST38-001"]
    assert (croc["card_type"], croc["life"], croc["power"]) == ("Leader", 4, 5000)
    assert croc["colors_en"] == ["Blue", "Black"]
    gw = index["ST38-004"]
    assert (gw["cost"], gw["power"], gw["counter"]) == (4, 5000, 1000)
    assert index["ST38-015"]["traits_en"] == ["The Seven Warlords of the Sea", "Baroque Works"]
    assert index["ST37-015"]["name_ja"] == "お前の方が 小物だろ!!!"
    assert {index[c]["rarity"] for c in ("ST37-007", "ST38-008")} == {"SR"}


def test_daily_apply_keeps_leaked_rows_until_official():
    index: dict = {}
    apply_manual_cards(index)
    for cid in LEAKED:
        assert index[cid]["unconfirmed"] is True
        assert index[cid]["preview"] is True


def test_official_text_clears_unconfirmed_but_keeps_temp_image():
    seed = load_manual_cards()
    existing = {"ST38-001": dict(seed["ST38-001"])}
    parsed = {
        "ST38-001": ParsedCard(
            card_id="ST38-001",
            name="Mr.0(克洛克達爾)",
            fields={"effect": "【攻擊時】官方文字", "power": "5000", "life": "4"},
        )
    }
    merged = merge_index(existing, parsed, "https://asia-tc.onepiece-cardgame.com/cardlist/")
    row = merged["ST38-001"]
    for key in ("preview", "manual_source", "text_origin", "unconfirmed", "reveal_source", "reveal_announcement"):
        assert key not in row, key
    # Art is replaced by sync_card_images, not by the text merge.
    assert row["temp_image"] is True
    # An official row is not overwritten by the screenshot seed again.
    assert apply_manual_cards(merged, {"ST38-001": seed["ST38-001"]}) == 0


def test_temp_image_candidates_are_official_and_japanese_first():
    urls = sync_card_images.temp_image_candidates("ST37-001")
    assert urls[0] == "https://www.onepiece-cardgame.com/images/cardlist/card/ST37-001.png"
    assert all(sync_card_images.is_official_cdn_url(u) for u in urls)
    assert not any("limitless" in u or "akihabara" in u for u in urls)


def test_temp_image_replaced_by_official_download(tmp_path, monkeypatch):
    index_path = tmp_path / "cards_by_id.json"
    manual_path = tmp_path / "manual_cards.json"
    queue_path = tmp_path / "temp_images_replaced.json"
    packs = tmp_path / "packs"
    packs.mkdir()
    (packs / "ST37-001.png").write_bytes(b"shop scan")
    row = dict(load_manual_cards()["ST37-001"])
    index_path.write_text(json.dumps({"ST37-001": row}, ensure_ascii=False), encoding="utf-8")
    manual_path.write_text(json.dumps({"cards": {"ST37-001": dict(row)}}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(sync_card_images, "INDEX_PATH", index_path)
    monkeypatch.setattr(sync_card_images, "MANUAL_CARDS_PATH", manual_path)
    monkeypatch.setattr(sync_card_images, "TEMP_IMAGE_REPLACED_PATH", queue_path)
    monkeypatch.setattr(sync_card_images, "PACKS_DIR", packs)
    monkeypatch.setattr(sync_card_images, "CARDS_DIR", tmp_path / "no-cards")
    monkeypatch.setattr(sync_card_images, "crawl_jp_cardlist_images", lambda session: {})
    monkeypatch.setattr(sync_card_images, "load_preview_ids", lambda: set())
    seen: list[list[str]] = []

    def fake_download(card_id, candidates, session):
        seen.append(list(candidates))
        (packs / f"{card_id}.png").write_bytes(b"official art")
        return True, candidates[0]

    monkeypatch.setattr(sync_card_images, "download_image", fake_download)
    monkeypatch.setattr(sys, "argv", ["sync_card_images.py", "--card-id", "ST37-001"])
    sync_card_images.main()

    assert seen and all(sync_card_images.is_official_cdn_url(u) for u in seen[0])
    assert (packs / "ST37-001.png").read_bytes() == b"official art"
    data = json.loads(index_path.read_text(encoding="utf-8"))["ST37-001"]
    assert "temp_image" not in data and "image_source" not in data
    manual = json.loads(manual_path.read_text(encoding="utf-8"))["cards"]["ST37-001"]
    assert "temp_image" not in manual
    assert json.loads(queue_path.read_text(encoding="utf-8")) == ["ST37-001"]


def test_temp_image_kept_when_official_art_missing(tmp_path, monkeypatch):
    index_path = tmp_path / "cards_by_id.json"
    packs = tmp_path / "packs"
    packs.mkdir()
    (packs / "ST38-001.png").write_bytes(b"shop scan")
    row = dict(load_manual_cards()["ST38-001"])
    index_path.write_text(json.dumps({"ST38-001": row}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sync_card_images, "INDEX_PATH", index_path)
    monkeypatch.setattr(sync_card_images, "TEMP_IMAGE_REPLACED_PATH", tmp_path / "q.json")
    monkeypatch.setattr(sync_card_images, "PACKS_DIR", packs)
    monkeypatch.setattr(sync_card_images, "CARDS_DIR", tmp_path / "no-cards")
    monkeypatch.setattr(sync_card_images, "crawl_jp_cardlist_images", lambda session: {})
    monkeypatch.setattr(sync_card_images, "load_preview_ids", lambda: set())
    monkeypatch.setattr(sync_card_images, "download_image", lambda cid, c, s: (False, ""))
    monkeypatch.setattr(sys, "argv", ["sync_card_images.py", "--card-id", "ST38-001"])
    sync_card_images.main()
    assert (packs / "ST38-001.png").read_bytes() == b"shop scan"
    assert json.loads(index_path.read_text(encoding="utf-8"))["ST38-001"]["temp_image"] is True
    assert not (tmp_path / "q.json").exists()


@pytest.mark.parametrize("cid", LEAKED)
def test_card_response_exposes_unconfirmed_labels(cid):
    import app

    row = _index()[cid]
    fields = app._provisional_fields(row)
    assert fields["unconfirmed"] is True
    assert fields["temp_image"] is True
    assert fields["reveal_source"].startswith("https://www.youtube.com/")
    assert app._provisional_fields({"name": "official"}) == {
        "unconfirmed": False,
        "temp_image": False,
        "reveal_source": None,
        "image_source": None,
    }
