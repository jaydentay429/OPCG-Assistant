#!/usr/bin/env python3
"""Copy card images that are not already on R2.

The daily official sync runs this before ``scripts/build_card_image_manifest.py``.
New art is uploaded with ``rclone copy --ignore-existing`` so an object that
already exists on the remote is left untouched. ``rclone sync`` is not used:
nothing on R2 is deleted, and hand-replaced art (EB05-016, EB05-048, OP18-112)
is not replaced by the VPS file.

Only top-level ``<ID>.png`` names are candidates. Other files in the packs
directory stay local. A missing rclone binary, a bad remote, a permission
error, or a timeout is logged (exit code and copied count) and does not raise.
The caller keeps going and rebuilds the manifest.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_card_image_manifest import filename_card_id  # noqa: E402

DEFAULT_PACKS = ROOT / "packs"
DEFAULT_TIMEOUT_SECONDS = 1200
RCLONE_NOT_FOUND = 127
RCLONE_TIMED_OUT = 124


@dataclass(frozen=True)
class CopyResult:
    """Outcome of one copy attempt. ``continued`` is always true."""

    exit_code: int
    copied: int
    continued: bool
    log_line: str


def is_card_png_filename(name: str) -> bool:
    """True when ``name`` is a bare ``<ID>.png`` key, not a path or other file."""
    if not name or name != Path(name).name:
        return False
    if "/" in name or "\\" in name or " " in name or name.startswith("."):
        return False
    card_id = filename_card_id(name)
    return bool(card_id) and name == f"{card_id}.png"


def list_card_pngs(packs_dir: Path) -> list[str]:
    """Top-level card png filenames. Does not walk subdirectories."""
    names: list[str] = []
    for entry in packs_dir.iterdir():
        if not entry.is_file():
            continue
        if is_card_png_filename(entry.name):
            names.append(entry.name)
    names.sort()
    return names


def build_rclone_copy_command(
    source: Path,
    remote: str,
    files_from: Path,
    *,
    dry_run: bool = False,
) -> list[str]:
    """Build ``rclone copy --ignore-existing`` for missing ``<ID>.png`` keys.

    The subcommand is ``copy``. There is no ``sync`` and no delete flag, so
    existing R2 objects stay as they are.
    """
    # --files-from is the whole filter. rclone 1.60 rejects combining it with
    # --include. The list itself is only canonical <ID>.png names.
    cmd = [
        "rclone",
        "copy",
        str(source),
        remote.strip().rstrip("/"),
        "--ignore-existing",
        "--files-from",
        str(files_from),
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
    if dry_run:
        cmd.append("--dry-run")
    return cmd


_TRANSFERRED_FILES = re.compile(
    r"Transferred:\s+(\d+)\s*/\s*\d+(?:,\s*(?:\d+(?:\.\d+)?%|-))?"
)
_COPIED_NEW = re.compile(r"Copied \(new\)")


def parse_copied_count(output: str) -> int:
    """Read how many files rclone transferred.

    Prefers the file summary ``Transferred: N / M, P%`` (not the byte line).
    Falls back to ``Copied (new)`` lines when the summary is missing.
    """
    file_counts = [int(match) for match in _TRANSFERRED_FILES.findall(output)]
    if file_counts:
        return file_counts[-1]
    return len(_COPIED_NEW.findall(output))


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


def _result(exit_code: int, copied: int, message: str) -> CopyResult:
    return CopyResult(
        exit_code=exit_code,
        copied=copied,
        continued=True,
        log_line=_emit(message),
    )


def _copy_new_pack_images(
    packs_dir: Path,
    remote: str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    dry_run: bool = False,
    runner=None,
) -> CopyResult:
    if runner is None:
        runner = subprocess.run
    destination = (remote or "").strip().rstrip("/")
    if not destination:
        return _result(2, 0, "copy new pack images FAILED rc=2 copied=0: rclone remote is empty")
    if timeout_seconds <= 0:
        return _result(
            2,
            0,
            "copy new pack images FAILED rc=2 copied=0: timeout must be positive",
        )
    if not packs_dir.is_dir():
        return _result(
            2,
            0,
            "copy new pack images FAILED rc=2 copied=0: "
            f"packs directory does not exist: {packs_dir}",
        )
    names = list_card_pngs(packs_dir)
    if not names:
        return _result(
            0,
            0,
            f"copy new pack images to {destination} rc=0 copied=0 (no card png files)",
        )

    fd, raw_list = tempfile.mkstemp(prefix="opcg-pack-pngs-", suffix=".txt")
    files_from = Path(raw_list)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(names) + "\n")
        cmd = build_rclone_copy_command(packs_dir, destination, files_from, dry_run=dry_run)
        try:
            proc = runner(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            output = _merge_output(getattr(exc, "stdout", None) or exc.output, exc.stderr)
            copied = parse_copied_count(output)
            return _result(
                RCLONE_TIMED_OUT,
                copied,
                "copy new pack images FAILED "
                f"rc={RCLONE_TIMED_OUT} copied={copied}: "
                f"rclone timed out after {timeout_seconds}s",
            )
        except FileNotFoundError:
            return _result(
                RCLONE_NOT_FOUND,
                0,
                "copy new pack images FAILED "
                f"rc={RCLONE_NOT_FOUND} copied=0: rclone not found",
            )
        except OSError as exc:
            return _result(
                1,
                0,
                f"copy new pack images FAILED rc=1 copied=0: could not run rclone: {exc}",
            )
        output = _merge_output(getattr(proc, "stdout", ""), getattr(proc, "stderr", ""))
        copied = parse_copied_count(output)
        raw_code = getattr(proc, "returncode", 1)
        code = 1 if raw_code is None else int(raw_code)
        if code == 0:
            suffix = " (dry-run)" if dry_run else ""
            return _result(
                0,
                copied,
                f"copy new pack images to {destination} rc=0 copied={copied}{suffix}",
            )
        detail = _one_line(getattr(proc, "stderr", "") or getattr(proc, "stdout", "") or "rclone copy failed")
        return _result(
            code,
            copied,
            f"copy new pack images FAILED rc={code} copied={copied}: {detail}",
        )
    finally:
        files_from.unlink(missing_ok=True)


def copy_new_pack_images(
    packs_dir: Path,
    remote: str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    dry_run: bool = False,
    runner=None,
) -> CopyResult:
    """Copy missing card pngs. Logs and returns on failure; never raises."""
    try:
        return _copy_new_pack_images(
            packs_dir,
            remote,
            timeout_seconds=timeout_seconds,
            dry_run=dry_run,
            runner=runner,
        )
    except Exception as exc:
        detail = _one_line(str(exc)) or exc.__class__.__name__
        return _result(1, 0, f"copy new pack images FAILED rc=1 copied=0: {detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy packs/<ID>.png keys that are missing on an rclone remote",
    )
    parser.add_argument("--packs", type=Path, default=DEFAULT_PACKS)
    parser.add_argument("--rclone-remote", default=os.getenv("OPCG_R2_RCLONE_REMOTE", ""))
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.getenv("OPCG_R2_COPY_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pass rclone --dry-run. Still uses copy --ignore-existing",
    )
    args = parser.parse_args(argv)
    result = copy_new_pack_images(
        args.packs,
        args.rclone_remote,
        timeout_seconds=args.timeout_seconds,
        dry_run=args.dry_run,
    )
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
