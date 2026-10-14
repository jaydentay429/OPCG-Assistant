"""Atomic library writes, and load_existing must not clobber a bad file."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_compile_module():
    path = ROOT / "scripts" / "compile_card_effects.py"
    spec = importlib.util.spec_from_file_location("compile_card_effects_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_compile_module()


def test_load_existing_missing_empty_and_whitespace(tmp_path, capsys):
    missing = tmp_path / "missing.json"
    assert mod.load_existing(missing) == {}

    empty = tmp_path / "empty.json"
    empty.write_bytes(b"")
    assert mod.load_existing(empty) == {}

    blank = tmp_path / "blank.json"
    blank.write_text(" \n\t\n", encoding="utf-8")
    assert mod.load_existing(blank) == {}

    err = capsys.readouterr().err
    assert "missing" in err
    assert "empty" in err
    assert "whitespace-only" in err
    assert err.count("WARNING:") == 3


def test_load_existing_reads_wrapped_cards(tmp_path, capsys):
    path = tmp_path / "card_effects.json"
    path.write_text(
        json.dumps({"version": 1, "cards": {"OP01-001": {"abilities": []}}}),
        encoding="utf-8",
    )
    assert mod.load_existing(path) == {"OP01-001": {"abilities": []}}
    assert capsys.readouterr().err == ""


def test_load_existing_corrupt_json_does_not_return(tmp_path):
    path = tmp_path / "card_effects.json"
    original = '{"cards": '
    path.write_text(original, encoding="utf-8")
    with pytest.raises(SystemExit, match="not overwritten"):
        mod.load_existing(path)
    assert path.read_text(encoding="utf-8") == original


def test_main_refuses_corrupt_library_without_overwrite(tmp_path, monkeypatch):
    path = tmp_path / "card_effects.json"
    original = "{not json"
    path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(mod, "load_catalog", lambda: {"OP01-001": {}})
    monkeypatch.setattr(mod, "library_paths", lambda: (path, tmp_path / "overrides.json"))
    monkeypatch.setattr(sys, "argv", ["compile_card_effects.py"])

    def fail_write(*_args, **_kwargs):
        raise AssertionError("corrupt library must not be overwritten")

    monkeypatch.setattr(mod, "write_library_atomic", fail_write)
    monkeypatch.setattr(mod, "write_compile_report", fail_write)
    monkeypatch.setattr(mod, "refresh_gap_tracker", fail_write)

    def boom():
        raise AssertionError("DeepSeek must not be called")

    monkeypatch.setattr(mod, "get_deepseek_asker", boom)

    with pytest.raises(SystemExit, match="not overwritten"):
        mod.main()
    assert path.read_text(encoding="utf-8") == original


def test_write_library_atomic_fsyncs_then_replaces_same_directory(tmp_path, monkeypatch):
    dest = tmp_path / "card_effects.json"
    dest.write_text('{"cards":{"OLD":1}}', encoding="utf-8")
    order: list[str] = []
    real_fsync = os.fsync
    real_replace = os.replace
    payload = {"version": 1, "cards": {"OP01-001": {"abilities": []}}}

    def spy_fsync(fd: int) -> None:
        order.append("fsync")
        assert dest.read_text(encoding="utf-8") == '{"cards":{"OLD":1}}'
        real_fsync(fd)

    def spy_replace(src: str, dst: str) -> None:
        order.append("replace")
        src_path = Path(src)
        assert src_path.parent == dest.parent
        assert src_path.name.startswith(".card_effects.json.")
        assert src_path.name.endswith(".tmp")
        assert json.loads(src_path.read_text(encoding="utf-8")) == payload
        assert dest.read_text(encoding="utf-8") == '{"cards":{"OLD":1}}'
        real_replace(src, dst)

    monkeypatch.setattr("atomic_io.os.fsync", spy_fsync)
    monkeypatch.setattr("atomic_io.os.replace", spy_replace)

    mod.write_library_atomic(dest, payload)

    assert order == ["fsync", "replace"]
    text = dest.read_text(encoding="utf-8")
    assert text == json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    assert " " not in text
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob(".card_effects.json.*")) == []


def test_write_library_atomic_keeps_original_when_fsync_fails(tmp_path, monkeypatch):
    dest = tmp_path / "card_effects.json"
    dest.write_text('{"cards":{"OLD":1}}', encoding="utf-8")

    def boom(_fd: int) -> None:
        raise OSError("fsync failed")

    monkeypatch.setattr("atomic_io.os.fsync", boom)
    with pytest.raises(OSError, match="fsync failed"):
        mod.write_library_atomic(dest, {"version": 1, "cards": {}})
    assert dest.read_text(encoding="utf-8") == '{"cards":{"OLD":1}}'
    assert list(tmp_path.glob("*.tmp")) == []


def test_main_compiles_empty_library_without_llm(tmp_path, monkeypatch):
    path = tmp_path / "card_effects.json"
    path.write_bytes(b"")
    reports: list[dict] = []
    monkeypatch.setattr(mod, "load_catalog", lambda: {"OP01-001": {"effect": "", "effect_en": ""}})
    monkeypatch.setattr(mod, "library_paths", lambda: (path, tmp_path / "overrides.json"))
    monkeypatch.setattr(mod, "write_compile_report", lambda report: reports.append(report) or path)
    monkeypatch.setattr(mod, "refresh_gap_tracker", lambda: None)
    monkeypatch.setattr(sys, "argv", ["compile_card_effects.py"])

    def boom():
        raise AssertionError("DeepSeek must not be called")

    monkeypatch.setattr(mod, "get_deepseek_asker", boom)

    assert mod.main() == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert "OP01-001" in data["cards"]
    assert reports and reports[0]["used_llm"] is False
    assert reports[0]["totals"]["llm_calls"] == 0
    assert list(tmp_path.glob(".card_effects.json.*")) == []


def test_deploy_workflow_excludes_server_card_effects_without_delete():
    text = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    start = text.index('name: "Sync backend code')
    end = text.index("name: Add repo-only card image manifest")
    block = text[start:end]
    run_at = block.index("run: |")
    script = block[run_at:]
    assert "--exclude 'index/card_effects.json'" in script
    assert "--exclude 'index/card_effects.json.tmp'" in script
    assert "--exclude 'index/card_effects.json.new'" in script
    assert "--exclude 'index/.card_effects.json.*.tmp'" in script
    assert "rsync -avz \\" in script
    assert "--delete" not in script

    warn = text.index("name: Warn if server card_effects.json is missing or empty")
    smoke = text.index("name: Smoke test")
    warn_block = text[warn:smoke]
    assert "/opt/opcg/app/index/card_effects.json" in warn_block
    assert "exit 0" in warn_block
    assert "compile_card_effects.py" not in warn_block
    assert "did not create, delete, or regenerate it." in warn_block
