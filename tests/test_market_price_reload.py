"""Atomic market_prices.json writes, and the API loader must not drop a good snapshot."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as appmod  # noqa: E402
from atomic_io import atomic_write_text  # noqa: E402
import sync_don_cards  # noqa: E402
import sync_yuyutei_prices  # noqa: E402


def _payload(price: int, updated_at: str) -> dict:
    return {
        "source": "yuyu-tei",
        "updated_at": updated_at,
        "cards": {
            "OP01-001": {
                "current_price": price,
                "status": "ok",
                "currency": "JPY",
            }
        },
    }


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class _SavedPrices:
    def __enter__(self) -> _SavedPrices:
        self.saved = (
            appmod.market_price_map,
            appmod.market_price_mtime,
            appmod.market_price_updated_at,
            appmod.MARKET_PRICE_FILE,
        )
        return self

    def __exit__(self, *exc: object) -> None:
        (
            appmod.market_price_map,
            appmod.market_price_mtime,
            appmod.market_price_updated_at,
            appmod.MARKET_PRICE_FILE,
        ) = self.saved


def test_atomic_write_text_fsyncs_then_replaces_same_directory(tmp_path, monkeypatch):
    dest = tmp_path / "market_prices.json"
    dest.write_text('{"cards":{"OLD":1}}', encoding="utf-8")
    order: list[str] = []
    real_fsync = os.fsync
    real_replace = os.replace

    def spy_fsync(fd: int) -> None:
        order.append("fsync")
        assert dest.read_text(encoding="utf-8") == '{"cards":{"OLD":1}}'
        real_fsync(fd)

    def spy_replace(src: str, dst: str) -> None:
        order.append("replace")
        src_path = Path(src)
        assert src_path.parent == dest.parent
        assert src_path.name != dest.name
        assert json.loads(src_path.read_text(encoding="utf-8")) == {"cards": {"NEW": 2}}
        assert dest.read_text(encoding="utf-8") == '{"cards":{"OLD":1}}'
        real_replace(src, dst)

    monkeypatch.setattr("atomic_io.os.fsync", spy_fsync)
    monkeypatch.setattr("atomic_io.os.replace", spy_replace)

    atomic_write_text(dest, json.dumps({"cards": {"NEW": 2}}))

    assert order == ["fsync", "replace"]
    assert json.loads(dest.read_text(encoding="utf-8")) == {"cards": {"NEW": 2}}
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_text_keeps_original_when_fsync_fails(tmp_path, monkeypatch):
    dest = tmp_path / "market_prices.json"
    dest.write_text("OLD", encoding="utf-8")

    def boom(_fd: int) -> None:
        raise OSError("fsync failed")

    monkeypatch.setattr("atomic_io.os.fsync", boom)
    try:
        atomic_write_text(dest, "NEW")
    except OSError as exc:
        assert "fsync failed" in str(exc)
    else:
        raise AssertionError("fsync failure must surface")
    assert dest.read_text(encoding="utf-8") == "OLD"
    assert list(tmp_path.glob("*.tmp")) == []


def test_sync_writers_use_atomic_helper(tmp_path, monkeypatch):
    dest = tmp_path / "market_prices.json"
    seen: list[tuple[str, Path, str]] = []

    def spy(path: Path, text: str) -> None:
        seen.append(("call", Path(path), text))

    monkeypatch.setattr(sync_yuyutei_prices, "atomic_write_text", spy)
    monkeypatch.setattr(sync_yuyutei_prices, "PRICE_PATH", dest)
    sync_yuyutei_prices.write_market_price_file({"source": "yuyu-tei", "cards": {}})

    monkeypatch.setattr(sync_don_cards, "atomic_write_text", spy)
    monkeypatch.setattr(sync_don_cards, "PRICE_PATH", dest)
    sync_don_cards.write_market_price_file({"source": "yuyu-tei", "cards": {"DON!!-001": {}}})

    assert len(seen) == 2
    assert all(path == dest for _, path, _ in seen)
    yuyu_text = seen[0][2]
    don_text = seen[1][2]
    assert json.loads(yuyu_text)["source"] == "yuyu-tei"
    assert not yuyu_text.endswith("\n")
    assert json.loads(don_text)["cards"]["DON!!-001"] == {}
    assert don_text.endswith("\n")


def test_loader_keeps_previous_data_on_corrupt_file(tmp_path, monkeypatch, caplog):
    path = tmp_path / "market_prices.json"
    _write(path, _payload(100, "2026-01-01T00:00:00+00:00"))
    with _SavedPrices():
        monkeypatch.setattr(appmod, "MARKET_PRICE_FILE", path)
        appmod.market_price_map = {}
        appmod.market_price_mtime = 0.0
        appmod.market_price_updated_at = ""
        appmod.load_market_price_data()
        assert appmod.market_price_map["OP01-001"]["current_price"] == 100
        kept_map = appmod.market_price_map
        kept_mtime = appmod.market_price_mtime
        kept_updated = appmod.market_price_updated_at
        assert kept_mtime > 0

        path.write_text("{", encoding="utf-8")
        os.utime(path, (time.time() + 10, time.time() + 10))
        assert path.stat().st_mtime > kept_mtime

        with caplog.at_level(logging.WARNING):
            appmod.load_market_price_data()
            appmod.ensure_market_price_data_fresh()

        assert appmod.market_price_map is kept_map
        assert appmod.market_price_mtime == kept_mtime
        assert appmod.market_price_updated_at == kept_updated
        assert appmod.market_price_map["OP01-001"]["current_price"] == 100
        assert any(
            "keeping previous price data" in record.getMessage() for record in caplog.records
        )

        path.write_bytes(b"\xff")
        os.utime(path, (time.time() + 20, time.time() + 20))
        appmod.load_market_price_data()
        assert appmod.market_price_map is kept_map
        assert appmod.market_price_mtime == kept_mtime


def test_only_one_reload_under_concurrency(tmp_path, monkeypatch):
    path = tmp_path / "market_prices.json"
    _write(path, _payload(100, "2026-01-01T00:00:00+00:00"))
    with _SavedPrices():
        monkeypatch.setattr(appmod, "MARKET_PRICE_FILE", path)
        appmod.market_price_map = {}
        appmod.market_price_mtime = 0.0
        appmod.market_price_updated_at = ""
        appmod.load_market_price_data()

        _write(path, _payload(250, "2026-01-02T00:00:00+00:00"))
        os.utime(path, (time.time() + 10, time.time() + 10))

        calls = {"n": 0}
        started = threading.Event()
        release = threading.Event()
        real = appmod.load_market_price_data

        def slow_load() -> None:
            calls["n"] += 1
            started.set()
            assert release.wait(timeout=5)
            real()

        monkeypatch.setattr(appmod, "load_market_price_data", slow_load)

        errors: list[BaseException] = []

        def worker() -> None:
            try:
                appmod.ensure_market_price_data_fresh()
            except BaseException as exc:  # pragma: no cover - fail the test via errors
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        try:
            for thread in threads:
                thread.start()
            assert started.wait(timeout=2)
            for _ in range(8):
                appmod.ensure_market_price_data_fresh()
            assert calls["n"] == 1
            assert appmod.market_price_map["OP01-001"]["current_price"] == 100
        finally:
            release.set()
            for thread in threads:
                thread.join(timeout=5)
        assert all(not thread.is_alive() for thread in threads)
        assert errors == []
        assert calls["n"] == 1
        assert appmod.market_price_map["OP01-001"]["current_price"] == 250
        assert appmod.market_price_updated_at == "2026-01-02T00:00:00+00:00"
