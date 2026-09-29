#!/usr/bin/env python3
"""Copy card images that are on R2 but missing from the local packs directory.

The daily official sync runs this after ``scripts/copy_new_pack_images_to_r2.py``
and before ``scripts/build_card_image_manifest.py``. The manifest hashes R2
object bytes, so this fill does not change which hashes are written. It runs
first so a failure is logged and the rebuild still happens.

``rclone copy --ignore-existing`` only creates files the destination does not
already have. It does not overwrite the VPS alt arts whose bytes differ from
R2, and it does not delete anything. ``rclone sync`` is not used.

Filters keep card images only: png, jpg, jpeg, webp, and gif (the suffixes
``/packs`` already serves). Duplicate ``* 2.png`` names, ``*-HEROINES-*``
hand copies, and date-suffixed backups are left on R2.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.copy_new_pack_images_to_r2 import (  # noqa: E402
    DEFAULT_TIMEOUT_SECONDS,
    RCLONE_NOT_FOUND,
    RCLONE_TIMED_OUT,
    parse_copied_count,
)

# Manifest suffixes, plus .gif which app.py serves from /packs.
IMAGE_GLOBS = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif")
# First matching rclone rule wins. Excludes stay ahead of the includes.
EXCLUDE_GLOBS = (
    "* 2.*",
    "*-HEROINES-*",
    "*-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].*",
    "*-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].*",
    "*.[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]",
)


@dataclass(frozen=True)
class FillResult:
    """Outcome of one fill attempt. ``continued`` is always true."""

    exit_code: int
    copied: int
    filled: tuple[str, ...]
    continued: bool
    log_line: str


def build_rclone_fill_command(remote: str, packs_dir: Path) -> list[str]:
    """Build ``rclone copy --ignore-existing`` from the remote onto ``packs_dir``.

    The subcommand is ``copy``. There is no ``sync`` and no delete flag.
    ``--ignore-existing`` skips any file that is already in packs, whatever
    its size or mtime.
    """
    cmd = [
        "rclone",
        "copy",
        remote.strip().rstrip("/"),
        str(packs_dir),
        "--ignore-existing",
        "--max-depth",
        "1",
    ]
    for pattern in EXCLUDE_GLOBS:
        cmd.extend(["--exclude", pattern])
    for pattern in IMAGE_GLOBS:
        cmd.extend(["--include", pattern])
    cmd.extend(
        [
            "-v",
            "--contimeout",
            "30s",
            "--timeout",
            "2m",
            "--retries",
            "2",
            "--low-level-retries",
            "5",
        ]
    )
    return cmd


def copied_new_names(output: str) -> list[str]:
    """Filenames rclone reported as ``Copied (new)``."""
    names: list[str] = []
    seen: set[str] = set()
    for line in (output or "").splitlines():
        if "Copied (new)" not in line:
            continue
        left = line.split("Copied (new)", 1)[0].rstrip()
        if left.endswith(":"):
            left = left[:-1].rstrip()
        name = Path(left.rsplit(":", 1)[-1].strip()).name
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _one_line(text: str, limit: int = 400) -> str:
    flat = " ".join((text or "").split())
    if len(flat) > limit:
        return flat[:limit] + "..."
    return flat


def _merge_output(stdout: object, stderr: object) -> str:
    parts: list[str] = []
    for chunk in (stdout, stderr):
        if not chunk:
            continue
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8", "replace")
        parts.append(str(chunk))
    return "\n".join(parts)


def _emit(message: str) -> str:
    line = f"[{_timestamp()}] {message}"
    print(line, flush=True)
    return line


def _result(exit_code: int, copied: int, filled: tuple[str, ...], message: str) -> FillResult:
    return FillResult(
        exit_code=exit_code,
        copied=copied,
        filled=filled,
        continued=True,
        log_line=_emit(message),
    )


def _log_filled(names: list[str]) -> None:
    for name in names:
        _emit(f"filled {name}")


def _fill_missing_pack_images(
    packs_dir: Path,
    remote: str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    runner=None,
) -> FillResult:
    if runner is None:
        runner = subprocess.run
    source = (remote or "").strip().rstrip("/")
    if not source:
        return _result(2, 0, (), "fill missing pack images FAILED rc=2 copied=0: rclone remote is empty")
    if timeout_seconds <= 0:
        return _result(
            2,
            0,
            (),
            "fill missing pack images FAILED rc=2 copied=0: timeout must be positive",
        )
    if not packs_dir.is_dir():
        return _result(
            2,
            0,
            (),
            "fill missing pack images FAILED rc=2 copied=0: "
            f"packs directory does not exist: {packs_dir}",
        )

    cmd = build_rclone_fill_command(source, packs_dir)
    try:
        proc = runner(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        output = _merge_output(getattr(exc, "stdout", None) or exc.output, exc.stderr)
        names = copied_new_names(output)
        copied = len(names) if names else parse_copied_count(output)
        _log_filled(names)
        return _result(
            RCLONE_TIMED_OUT,
            copied,
            tuple(names),
            "fill missing pack images FAILED "
            f"rc={RCLONE_TIMED_OUT} copied={copied}: "
            f"rclone timed out after {timeout_seconds}s",
        )
    except FileNotFoundError:
        return _result(
            RCLONE_NOT_FOUND,
            0,
            (),
            "fill missing pack images FAILED "
            f"rc={RCLONE_NOT_FOUND} copied=0: rclone not found",
        )
    except OSError as exc:
        return _result(
            1,
            0,
            (),
            f"fill missing pack images FAILED rc=1 copied=0: could not run rclone: {exc}",
        )

    output = _merge_output(getattr(proc, "stdout", ""), getattr(proc, "stderr", ""))
    names = copied_new_names(output)
    copied = len(names) if names else parse_copied_count(output)
    _log_filled(names)
    raw_code = getattr(proc, "returncode", 1)
    code = 1 if raw_code is None else int(raw_code)
    if code == 0:
        return _result(
            0,
            copied,
            tuple(names),
            f"fill missing pack images from {source} rc=0 copied={copied}",
        )
    detail = _one_line(getattr(proc, "stderr", "") or getattr(proc, "stdout", "") or "rclone copy failed")
    return _result(
        code,
        copied,
        tuple(names),
        f"fill missing pack images FAILED rc={code} copied={copied}: {detail}",
    )


def fill_missing_pack_images(
    packs_dir: Path,
    remote: str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    runner=None,
) -> FillResult:
    """Copy missing card images from R2. Logs and returns on failure; never raises."""
    try:
        return _fill_missing_pack_images(
            packs_dir,
            remote,
            timeout_seconds=timeout_seconds,
            runner=runner,
        )
    except Exception as exc:
        detail = _one_line(str(exc)) or exc.__class__.__name__
        return _result(1, 0, (), f"fill missing pack images FAILED rc=1 copied=0: {detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy R2 card images that are missing in the local packs directory",
    )
    parser.add_argument("--packs", type=Path, default=ROOT / "packs")
    parser.add_argument("--rclone-remote", default=os.getenv("OPCG_R2_RCLONE_REMOTE", ""))
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.getenv("OPCG_R2_COPY_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
    )
    args = parser.parse_args(argv)
    result = fill_missing_pack_images(
        args.packs,
        args.rclone_remote,
        timeout_seconds=args.timeout_seconds,
    )
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
