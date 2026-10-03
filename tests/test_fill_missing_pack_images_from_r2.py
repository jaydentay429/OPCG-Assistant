"""Daily R2 download: copy missing card images into packs, never overwrite."""

from __future__ import annotations

import fnmatch
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fill_missing_pack_images_from_r2 import (  # noqa: E402
    EXCLUDE_GLOBS,
    IMAGE_GLOBS,
    FillResult,
    build_rclone_fill_command,
    copied_new_names,
    fill_missing_pack_images,
)


class _Proc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_fill_command_ignores_existing_and_filters_images(tmp_path: Path):
    packs = tmp_path / "packs"
    cmd = build_rclone_fill_command("opcg-r2:opcg-packs/", packs)
    assert cmd[0] == "rclone"
    assert cmd[1] == "copy"
    assert cmd[2] == "opcg-r2:opcg-packs"
    assert cmd[3] == str(packs)
    assert "sync" not in cmd
    assert "--ignore-existing" in cmd
    assert "--update" not in cmd
    assert "--checksum" not in cmd
    assert not any(arg == "sync" or arg.startswith("--delete") for arg in cmd)
    assert "-v" in cmd
    assert "--include" not in cmd
    assert "--exclude" not in cmd
    rules = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--filter"]
    assert rules[0].startswith("- ")
    assert "- * 2.*" in rules
    assert "- *-HEROINES-*" in rules
    assert any(rule.startswith("- *-") and "[0-9]" in rule for rule in rules)
    assert any(rule.startswith("- *.") and "[0-9]" in rule for rule in rules)
    includes = [rule[2:] for rule in rules if rule.startswith("+ ")]
    assert includes == ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif"]
    assert rules[-1] == "- *"
    assert rules.index("- * 2.*") < rules.index("+ *.png")
    assert rules.index("+ *.gif") < rules.index("- *")


def test_op18_025_png_is_kept_by_the_fill_filter(tmp_path: Path):
    rules = [f"- {pattern}" for pattern in EXCLUDE_GLOBS]
    rules.extend(f"+ {pattern}" for pattern in IMAGE_GLOBS)
    rules.append("- *")

    def kept(name: str) -> bool:
        for rule in rules:
            if fnmatch.fnmatchcase(name, rule[2:]):
                return rule.startswith("+")
        return False

    assert kept("OP18-025.png") is True
    assert kept("OP18-044.png") is True
    assert kept("OP18-076.png") is True
    assert kept("OP18-089.png") is True
    assert kept("P-160.png") is True
    assert kept("OP18-005.webp") is True
    assert kept("OP13-001.w320.870e05eb.webp") is False
    assert kept("OP13-001.w200.870e05eb.webp") is False
    assert kept("OP13-001.870e05eb.webp") is False
    cmd = build_rclone_fill_command("opcg-r2:opcg-packs", tmp_path / "packs")
    assert "OP18-025" not in cmd
    assert "OP18-044" not in cmd
    assert "--ignore-existing" in cmd
    assert not any("OP18-025" in arg and arg.startswith("-") for arg in cmd)
    assert not any("OP18-044" in arg and arg.startswith("-") for arg in cmd)


def test_copied_new_names_reads_verbose_lines_and_skips_ignored():
    output = "\n".join(
        [
            "2026/09/29 10:00:00 INFO  : OP13-001.png: Copied (new)",
            "2026/09/29 10:00:01 INFO  : EB05-016.png: Not copying as --ignore-existing is set",
            "INFO  : nested/P-136.png: Copied (new)",
            "Transferred:            2 / 5, 40%",
        ]
    )
    assert copied_new_names(output) == ["OP13-001.png", "P-136.png"]
    assert copied_new_names("") == []


def test_fill_logs_each_new_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    packs = tmp_path / "packs"
    packs.mkdir()

    def runner(cmd, **kwargs):
        assert kwargs.get("timeout") == 1200
        assert cmd[1] == "copy"
        assert "--ignore-existing" in cmd
        return _Proc(
            0,
            stderr="\n".join(
                [
                    "INFO  : OP13-001.png: Copied (new)",
                    "INFO  : OP18-002.jpg: Copied (new)",
                    "Transferred:            2 / 2, 100%",
                ]
            ),
        )

    result = fill_missing_pack_images(packs, "opcg-r2:opcg-packs", runner=runner)
    assert isinstance(result, FillResult)
    assert result.exit_code == 0
    assert result.copied == 2
    assert result.filled == ("OP13-001.png", "OP18-002.jpg")
    assert result.continued is True
    assert "rc=0" in result.log_line
    assert "copied=2" in result.log_line
    logged = capsys.readouterr().out
    assert logged.index("filled OP13-001.png") < logged.index("filled OP18-002.jpg")
    assert logged.index("filled OP18-002.jpg") < logged.index("rc=0 copied=2")


def test_fill_failure_logs_copied_names_and_continues(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    packs = tmp_path / "packs"
    packs.mkdir()

    def runner(cmd, **kwargs):
        return _Proc(
            1,
            stderr="\n".join(
                [
                    "INFO  : OP13-001.png: Copied (new)",
                    "ERROR : permission denied",
                    "Transferred:            1 / 4, 25%",
                ]
            ),
        )

    result = fill_missing_pack_images(packs, "opcg-r2:opcg-packs", runner=runner)
    assert result.exit_code == 1
    assert result.copied == 1
    assert result.filled == ("OP13-001.png",)
    assert result.continued is True
    assert "FAILED" in result.log_line
    assert "rc=1" in result.log_line
    assert "permission denied" in result.log_line
    logged = capsys.readouterr().out
    assert logged.index("filled OP13-001.png") < logged.index("FAILED rc=1")


def test_fill_timeout_logs_and_continues(tmp_path: Path):
    packs = tmp_path / "packs"
    packs.mkdir()

    def runner(cmd, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=cmd,
            timeout=kwargs.get("timeout"),
            output="",
            stderr="INFO  : OP13-001.png: Copied (new)\n",
        )

    result = fill_missing_pack_images(packs, "opcg-r2:opcg-packs", timeout_seconds=30, runner=runner)
    assert result.exit_code == 124
    assert result.copied == 1
    assert result.filled == ("OP13-001.png",)
    assert result.continued is True
    assert "timed out after 30s" in result.log_line


def test_missing_rclone_and_bad_inputs_do_not_raise(tmp_path: Path):
    packs = tmp_path / "packs"
    packs.mkdir()

    def missing(cmd, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "rclone")

    result = fill_missing_pack_images(packs, "opcg-r2:opcg-packs", runner=missing)
    assert result.exit_code == 127
    assert result.filled == ()
    assert "rclone not found" in result.log_line

    def boom(cmd, **kwargs):
        raise RuntimeError("remote opcg-r2 is not configured")

    result = fill_missing_pack_images(packs, "opcg-r2:opcg-packs", runner=boom)
    assert result.exit_code == 1
    assert result.continued is True
    assert "not configured" in result.log_line

    empty = fill_missing_pack_images(packs, "  ")
    assert empty.exit_code == 2
    assert "remote is empty" in empty.log_line
    missing_dir = fill_missing_pack_images(tmp_path / "nope", "opcg-r2:opcg-packs")
    assert missing_dir.exit_code == 2
    assert "does not exist" in missing_dir.log_line


@pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone is not installed")
def test_real_rclone_fills_missing_images_and_does_not_overwrite(tmp_path: Path):
    source = tmp_path / "r2"
    packs = tmp_path / "packs"
    nested = source / "extra"
    source.mkdir()
    nested.mkdir()
    packs.mkdir()
    (source / "EB05-016.png").write_bytes(b"r2-different")
    (source / "OP13-001.png").write_bytes(b"from-r2")
    (source / "OP18-025.png").write_bytes(b"gonbe")
    (source / "OP18-044.png").write_bytes(b"beans")
    (source / "OP18-002.jpg").write_bytes(b"jpeg")
    (source / "OP18-004.jpeg").write_bytes(b"jpeg-long")
    (source / "OP18-005.webp").write_bytes(b"webp")
    (source / "OP13-001.w320.870e05eb.webp").write_bytes(b"thumb")
    (source / "OP13-001.870e05eb.webp").write_bytes(b"fullwebp")
    (source / "OP18-006.gif").write_bytes(b"gif")
    (source / "EB01-001-P2 2.png").write_bytes(b"duplicate")
    (source / "EB05-016-HEROINES-alt.png").write_bytes(b"heroines")
    (source / "EB05-016-20260929.png").write_bytes(b"date-suffix")
    (source / "EB05-016-2026-09-29.png").write_bytes(b"date-dashed")
    (source / "EB05-016.png.20260929").write_bytes(b"date-ext")
    (source / "notes.txt").write_bytes(b"notes")
    (nested / "OP18-003.png").write_bytes(b"nested")
    (packs / "EB05-016.png").write_bytes(b"local-alt")
    (packs / "OP18-002.jpg").write_bytes(b"local-jpeg")

    result = fill_missing_pack_images(packs, str(source), timeout_seconds=60)
    assert result.exit_code == 0, result.log_line
    assert (packs / "EB05-016.png").read_bytes() == b"local-alt"
    assert (packs / "OP18-002.jpg").read_bytes() == b"local-jpeg"
    assert (packs / "OP13-001.png").read_bytes() == b"from-r2"
    assert (packs / "OP18-025.png").read_bytes() == b"gonbe"
    assert (packs / "OP18-044.png").read_bytes() == b"beans"
    assert (packs / "OP18-004.jpeg").read_bytes() == b"jpeg-long"
    assert (packs / "OP18-005.webp").read_bytes() == b"webp"
    assert not (packs / "OP13-001.w320.870e05eb.webp").exists()
    assert not (packs / "OP13-001.870e05eb.webp").exists()
    assert (packs / "OP18-006.gif").read_bytes() == b"gif"
    assert not (packs / "EB01-001-P2 2.png").exists()
    assert not (packs / "EB05-016-HEROINES-alt.png").exists()
    assert not (packs / "EB05-016-20260929.png").exists()
    assert not (packs / "EB05-016-2026-09-29.png").exists()
    assert not (packs / "EB05-016.png.20260929").exists()
    assert not (packs / "notes.txt").exists()
    assert not (packs / "OP18-003.png").exists()
    assert not (packs / "extra").exists()
    assert "OP13-001.png" in result.filled
    assert "OP18-025.png" in result.filled
    assert "OP18-044.png" in result.filled
    assert "EB05-016.png" not in result.filled
    assert "EB01-001-P2 2.png" not in result.filled
    assert result.copied == 6
