"""Daily R2 upload: copy missing <ID>.png keys, then rebuild the manifest."""

from __future__ import annotations

import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.copy_new_pack_images_to_r2 import (  # noqa: E402
    CopyResult,
    build_rclone_copy_command,
    copy_new_pack_images,
    is_card_png_filename,
    list_card_pngs,
    parse_copied_count,
)

DAILY_SYNC = ROOT / "deploy" / "optcgassistant" / "run_daily_official_sync.sh"


class _Proc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _write_pack_tree(packs: Path) -> None:
    packs.mkdir(parents=True)
    (packs / "OP13-001.png").write_bytes(b"png-op13")
    (packs / "P-136.png").write_bytes(b"png-p136")
    (packs / "EB05-016.png").write_bytes(b"vps-eb05-016")
    (packs / "notes.txt").write_bytes(b"notes")
    (packs / "readme.png").write_bytes(b"not-a-card-key")
    (packs / "EB01-001-P2 2.png").write_bytes(b"duplicate-name")
    (packs / "OP18-002.jpg").write_bytes(b"jpeg")
    nested = packs / "extra"
    nested.mkdir()
    (nested / "OP18-003.png").write_bytes(b"nested")


def test_card_png_filename_is_canonical_id_png():
    assert is_card_png_filename("OP13-001.png")
    assert is_card_png_filename("P-136.png")
    assert is_card_png_filename("EB05-048.png")
    assert is_card_png_filename("OP18-112.png")
    assert is_card_png_filename("OP18-021-P1.png")
    assert is_card_png_filename("notes.txt") is False
    assert is_card_png_filename("readme.png") is False
    assert is_card_png_filename("EB01-001-P2 2.png") is False
    assert is_card_png_filename("OP18-002.jpg") is False
    assert is_card_png_filename("extra/OP18-003.png") is False
    assert is_card_png_filename(".OP13-001.png") is False


def test_list_card_pngs_skips_other_files(tmp_path: Path):
    packs = tmp_path / "packs"
    _write_pack_tree(packs)
    assert list_card_pngs(packs) == ["EB05-016.png", "OP13-001.png", "P-136.png"]


def test_copy_command_ignores_existing_and_is_not_sync(tmp_path: Path):
    cmd = build_rclone_copy_command(tmp_path / "packs", "opcg-r2:opcg-packs", tmp_path / "files.txt")
    assert cmd[0] == "rclone"
    assert cmd[1] == "copy"
    assert "--ignore-existing" in cmd
    assert "--files-from" in cmd
    assert "sync" not in cmd
    assert "--include" not in cmd
    assert not any(arg == "sync" or arg.startswith("--delete") for arg in cmd)
    assert "--dry-run" not in cmd
    assert "--timeout" in cmd
    assert cmd[cmd.index("--timeout") + 1] == "2m"

    dry = build_rclone_copy_command(
        tmp_path / "packs",
        "opcg-r2:opcg-packs",
        tmp_path / "files.txt",
        dry_run=True,
    )
    assert dry[1] == "copy"
    assert "--ignore-existing" in dry
    assert "sync" not in dry
    assert dry[-1] == "--dry-run"


def test_parse_copied_count_uses_file_summary_not_bytes():
    output = "\n".join(
        [
            "Transferred:   \t    123.456 KiB / 123.456 KiB, 100%, 1.234 MiB/s, ETA 0s",
            "Transferred:            2 / 5, 40%",
            "Elapsed time:         0.4s",
        ]
    )
    assert parse_copied_count(output) == 2
    assert parse_copied_count("Copied (new)\nCopied (new)\n") == 2
    assert parse_copied_count("") == 0


def test_copy_lists_only_card_pngs_and_passes_timeout(tmp_path: Path):
    packs = tmp_path / "packs"
    _write_pack_tree(packs)
    seen: dict = {}

    def runner(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["timeout"] = kwargs.get("timeout")
        files_from = Path(cmd[cmd.index("--files-from") + 1])
        seen["names"] = files_from.read_text(encoding="utf-8").splitlines()
        return _Proc(0, stderr="Transferred:            3 / 3, 100%\n")

    result = copy_new_pack_images(packs, "opcg-r2:opcg-packs", timeout_seconds=1200, runner=runner)
    assert isinstance(result, CopyResult)
    assert result.exit_code == 0
    assert result.copied == 3
    assert result.continued is True
    assert "rc=0" in result.log_line
    assert "copied=3" in result.log_line
    assert seen["timeout"] == 1200
    assert seen["cmd"][1] == "copy"
    assert "--ignore-existing" in seen["cmd"]
    assert "sync" not in seen["cmd"]
    assert seen["names"] == ["EB05-016.png", "OP13-001.png", "P-136.png"]
    assert "notes.txt" not in seen["names"]
    assert "OP18-002.jpg" not in seen["names"]
    assert "EB01-001-P2 2.png" not in seen["names"]
    assert "OP18-003.png" not in seen["names"]


def test_rclone_failure_logs_exit_code_and_copied_count_and_continues(tmp_path: Path):
    packs = tmp_path / "packs"
    packs.mkdir()
    (packs / "P-136.png").write_bytes(b"png")

    def runner(cmd, **kwargs):
        return _Proc(
            1,
            stderr="\n".join(
                [
                    "ERROR : permission denied",
                    "Transferred:            2 / 10, 20%",
                ]
            ),
        )

    result = copy_new_pack_images(packs, "opcg-r2:opcg-packs", runner=runner)
    assert result.exit_code == 1
    assert result.copied == 2
    assert result.continued is True
    assert "FAILED" in result.log_line
    assert "rc=1" in result.log_line
    assert "copied=2" in result.log_line
    assert "permission denied" in result.log_line


def test_rclone_timeout_logs_and_continues(tmp_path: Path):
    packs = tmp_path / "packs"
    packs.mkdir()
    (packs / "P-136.png").write_bytes(b"png")

    def runner(cmd, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=cmd,
            timeout=kwargs.get("timeout"),
            output="",
            stderr="Transferred:            4 / 9, 44%\n",
        )

    result = copy_new_pack_images(packs, "opcg-r2:opcg-packs", timeout_seconds=30, runner=runner)
    assert result.exit_code == 124
    assert result.copied == 4
    assert result.continued is True
    assert "rc=124" in result.log_line
    assert "copied=4" in result.log_line
    assert "timed out after 30s" in result.log_line


def test_unexpected_runner_error_is_logged_and_does_not_raise(tmp_path: Path):
    packs = tmp_path / "packs"
    packs.mkdir()
    (packs / "P-136.png").write_bytes(b"png")

    def runner(cmd, **kwargs):
        raise RuntimeError("remote opcg-r2 is not configured")

    result = copy_new_pack_images(packs, "opcg-r2:opcg-packs", runner=runner)
    assert result.exit_code == 1
    assert result.copied == 0
    assert result.continued is True
    assert "rc=1" in result.log_line
    assert "copied=0" in result.log_line
    assert "not configured" in result.log_line


def test_missing_rclone_logs_and_continues(tmp_path: Path):
    packs = tmp_path / "packs"
    packs.mkdir()
    (packs / "P-136.png").write_bytes(b"png")

    def runner(cmd, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "rclone")

    result = copy_new_pack_images(packs, "opcg-r2:opcg-packs", runner=runner)
    assert result.exit_code == 127
    assert result.copied == 0
    assert result.continued is True
    assert "rc=127" in result.log_line
    assert "copied=0" in result.log_line
    assert "rclone not found" in result.log_line


def test_daily_sync_source_copies_before_manifest_and_does_not_sync():
    text = DAILY_SYNC.read_text(encoding="utf-8")
    copy_at = text.index("scripts/copy_new_pack_images_to_r2.py")
    fill_at = text.index("scripts/fill_missing_pack_images_from_r2.py")
    manifest_at = text.index("scripts/build_card_image_manifest.py")
    assert copy_at < fill_at < manifest_at
    between = text[copy_at:manifest_at]
    assert "exit " not in between
    assert "rclone sync" not in text
    assert "continuing to card image manifest" in text
    assert "--ignore-existing" in text
    assert between.count("--packs") == 2
    assert between.count('"$APP_ROOT/packs"') == 2
    assert between.count('"$remote"') == 2
    assert "opcg-r2:" not in text
    assert "/opt/opcg/app/packs" not in text


def _fake_python(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import os, sys",
                "with open(os.environ['CALL_LOG'], 'a', encoding='utf-8') as fh:",
                "    fh.write(' '.join(sys.argv[1:]) + '\\n')",
                "if any(arg.endswith('copy_new_pack_images_to_r2.py') for arg in sys.argv):",
                "    raise SystemExit(7)",
                "if any(arg.endswith('fill_missing_pack_images_from_r2.py') for arg in sys.argv):",
                "    raise SystemExit(int(os.environ.get('FILL_EXIT', '0')))",
                "raise SystemExit(0)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_daily_sync_continues_to_manifest_when_copy_fails(tmp_path: Path):
    app = tmp_path / "app"
    logs = tmp_path / "logs"
    app.mkdir()
    (app / ".env").write_text("OPCG_R2_RCLONE_REMOTE=opcg-r2:opcg-packs\n", encoding="utf-8")
    fake_py = tmp_path / "fake-python.py"
    call_log = tmp_path / "calls.txt"
    _fake_python(fake_py)
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "OPCG_APP_ROOT": str(app),
        "OPCG_LOG_DIR": str(logs),
        "OPCG_SYNC_PYTHON": str(fake_py),
        "CALL_LOG": str(call_log),
    }
    proc = subprocess.run(
        ["bash", str(DAILY_SYNC)],
        cwd=str(app),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    calls = call_log.read_text(encoding="utf-8").splitlines()
    copy_at = next(i for i, line in enumerate(calls) if "copy_new_pack_images_to_r2.py" in line)
    fill_at = next(i for i, line in enumerate(calls) if "fill_missing_pack_images_from_r2.py" in line)
    manifest_at = next(i for i, line in enumerate(calls) if "build_card_image_manifest.py" in line)
    assert copy_at < fill_at < manifest_at
    assert "--packs" in calls[copy_at]
    assert f"--packs {app / 'packs'}" in calls[copy_at]
    assert f"--packs {app / 'packs'}" in calls[fill_at]
    assert "opcg-r2:opcg-packs" in calls[copy_at]
    assert "opcg-r2:opcg-packs" in calls[fill_at]
    log = (logs / "daily_official_latest.log").read_text(encoding="utf-8")
    assert "copy new pack images FAILED rc=7; continuing to card image manifest" in log
    assert "card image manifest from opcg-r2:opcg-packs" in log
    assert log.index("copy new pack images to opcg-r2:opcg-packs") < log.index(
        "fill missing pack images from opcg-r2:opcg-packs"
    )
    assert log.index("fill missing pack images from opcg-r2:opcg-packs") < log.index(
        "card image manifest from opcg-r2:opcg-packs"
    )


def test_daily_sync_continues_to_manifest_when_fill_fails(tmp_path: Path):
    app = tmp_path / "app"
    logs = tmp_path / "logs"
    app.mkdir()
    (app / ".env").write_text("OPCG_R2_RCLONE_REMOTE=opcg-r2:opcg-packs\n", encoding="utf-8")
    fake_py = tmp_path / "fake-python.py"
    call_log = tmp_path / "calls.txt"
    _fake_python(fake_py)
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "OPCG_APP_ROOT": str(app),
        "OPCG_LOG_DIR": str(logs),
        "OPCG_SYNC_PYTHON": str(fake_py),
        "CALL_LOG": str(call_log),
        "FILL_EXIT": "9",
    }
    proc = subprocess.run(
        ["bash", str(DAILY_SYNC)],
        cwd=str(app),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    calls = call_log.read_text(encoding="utf-8").splitlines()
    fill_at = next(i for i, line in enumerate(calls) if "fill_missing_pack_images_from_r2.py" in line)
    manifest_at = next(i for i, line in enumerate(calls) if "build_card_image_manifest.py" in line)
    assert fill_at < manifest_at
    log = (logs / "daily_official_latest.log").read_text(encoding="utf-8")
    assert "fill missing pack images from R2 FAILED rc=9; continuing to card image manifest" in log
    assert log.index("fill missing pack images from R2 FAILED rc=9") < log.index(
        "card image manifest from opcg-r2:opcg-packs"
    )


@pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone is not installed")
def test_real_rclone_does_not_overwrite_existing_objects(tmp_path: Path):
    src = tmp_path / "packs"
    dst = tmp_path / "bucket"
    _write_pack_tree(src)
    dst.mkdir()
    (dst / "EB05-016.png").write_bytes(b"hand-replaced")
    result = copy_new_pack_images(src, str(dst), timeout_seconds=60)
    assert result.exit_code == 0, result.log_line
    assert (dst / "EB05-016.png").read_bytes() == b"hand-replaced"
    assert (dst / "P-136.png").read_bytes() == b"png-p136"
    assert (dst / "OP13-001.png").read_bytes() == b"png-op13"
    assert not (dst / "notes.txt").exists()
    assert not (dst / "readme.png").exists()
    assert not (dst / "OP18-002.jpg").exists()
    assert not (dst / "OP18-003.png").exists()
    assert not (dst / "EB01-001-P2 2.png").exists()
    assert result.copied == 2
