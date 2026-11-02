#!/usr/bin/env python3
"""Build the card-image manifest from file bytes, not from an R2 etag.

Each entry is ``{"OP13-001": "870e05eb"}``: catalog id → first 8 hex chars of
the MD5 of the file contents. Multipart R2 uploads do not use the content MD5
as the etag, so this script hashes the bytes.

Production (on the VPS, after images are on R2):

The daily official sync first copies packs ``<ID>.png`` keys that are missing
on the remote (``rclone copy --ignore-existing``), then fills local files that
exist on R2 but not in packs/ (same flag; differing local alt arts stay), then runs:

    python3 scripts/build_card_image_manifest.py --rclone-remote "$OPCG_R2_RCLONE_REMOTE"

That runs ``rclone hashsum MD5 --download`` so rclone reads the object body.
``--download`` is required: without it, S3/R2 can report the multipart etag.
While that runs, the script logs a count every 500 objects or 30 seconds.
It does not print object names or the remote string.

The manifest is a local JSON file, ``frontend/src/generated/card-image-manifest.json``
(on the VPS, ``/opt/opcg/app/`` plus that path). It is not an R2 object and it
has no public URL. Card art is ``https://img.optcgassistant.com/<ID>.png?h=<8 hex>``;
the ``h`` value is this file, baked into the frontend at deploy. The write
goes to a unique temp file in the same directory, fsyncs it, then
``os.replace`` onto the destination. A killed process leaves the previous
file in place. A partial temp file is not the manifest.

This VM cannot see the bucket. ``--from-cdn`` GETs
``https://img.optcgassistant.com/<id>.png`` and hashes the response. That is
only for producing a snapshot to commit. A cached 404 or an old edge object
can disagree with R2 for up to max-age (14400s), so the VPS job is the source
of truth for the next deploy.

``--from-etag-listing`` reads a Manager export of ``{"objects": {"OP13-001.png":
"<etag>"}}``. Use it only when every object was a single-part upload: that
ETag is the content MD5. A multipart ETag (``<hex>-<parts>``) is not an MD5
and the command refuses the file.

``--merge-missing-from`` does not hash anything. It adds keys from that file
that ``--output`` does not already have. Entries already in ``--output`` stay,
including when the other file has a different hash. Nothing is deleted. Deploy
uses this so a committed card can ship before the next R2 rebuild, without
replacing hashes the VPS already recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import select
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "frontend" / "src" / "generated" / "card-image-manifest.json"
DEFAULT_INDEX = ROOT / "index" / "cards_by_id.json"
DEFAULT_CDN = "https://img.optcgassistant.com"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
# A new manifest may replace the previous one only when it keeps at least 95%.
MIN_KEEP_NUMERATOR = 95
MIN_KEEP_DENOMINATOR = 100
# rclone hashsum prints nothing until it exits when stdout is captured.
# Log a count on this cadence so a long rebuild is not a silent SSH session.
HASH_PROGRESS_EVERY = 500
HASH_PROGRESS_INTERVAL_S = 30.0


class ManifestRejected(Exception):
    """The new manifest must not replace the previous file."""


def normalize_card_id(raw: str) -> str:
    return str(raw or "").strip().upper().replace("_", "-")


def content_md5_prefix(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()[:8]


# scripts/generate_card_webp.py writes ``<ID>.w320.<8 hex>.webp`` and
# ``<ID>.<8 hex>.webp``. The hash is the PNG content prefix (manifest ``?h=``).
# These are derivatives, not catalog files. A plain ``<ID>.webp`` is left alone.
_GENERATED_WEBP_NAME = re.compile(
    r"^(?P<id>[A-Za-z0-9][A-Za-z0-9-]*)(?:\.w(?P<width>\d+))?\.(?P<hash>[0-9a-f]{8})\.webp$",
    re.IGNORECASE,
)


def is_generated_webp_name(name: str) -> bool:
    """True for WebP derivatives whose object key embeds the PNG content hash."""
    base = Path(str(name or "").replace("\\", "/")).name
    return _GENERATED_WEBP_NAME.match(base) is not None


def filename_card_id(name: str) -> str:
    """Map a bucket filename to a catalog id. Skip duplicate names like ``X 2.png``.

    Generated WebP derivatives are skipped so a manifest rebuild keeps the PNG
    hash and does not invent ids such as ``OP13-001.W320``.
    """
    base = Path(str(name or "").replace("\\", "/")).name
    if not base or " " in base or base.startswith(".") or is_generated_webp_name(base):
        return ""
    suffix = Path(base).suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        return ""
    return normalize_card_id(Path(base).stem)


def below_keep_ratio(new_count: int, previous_count: int) -> bool:
    """True when new_count is more than 5% under previous_count."""
    if previous_count <= 0:
        return False
    return new_count * MIN_KEEP_DENOMINATOR < previous_count * MIN_KEEP_NUMERATOR


def load_manifest(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    out: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, str) or len(value) != 8:
            raise ValueError(f"bad manifest entry: {key!r}")
        out[key] = value
    return out


def validate_replacement(new: dict[str, str], previous: dict[str, str] | None) -> None:
    if not new:
        raise ManifestRejected("new manifest is empty")
    if previous is None:
        return
    if below_keep_ratio(len(new), len(previous)):
        raise ManifestRejected(
            f"new manifest has {len(new)} entries, previous has {len(previous)} "
            f"(refusing a drop of more than 5%)"
        )


def write_manifest(path: Path, new: dict[str, str]) -> None:
    """Replace ``path`` only when the new map passes the count guard.

    A missing previous file is fine. An unreadable previous file, an empty new
    map, or a drop of more than 5% leaves the old bytes in place and raises
    ManifestRejected.
    """
    previous: dict[str, str] | None = None
    if path.exists():
        try:
            previous = load_manifest(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ManifestRejected(f"refusing to overwrite unreadable manifest: {exc}") from exc
    validate_replacement(new, previous)
    payload = json.dumps(dict(sorted(new.items())), ensure_ascii=False, indent=2) + "\n"
    _atomic_write_text(path, payload)


def _atomic_write_text(path: Path, payload: str) -> None:
    """Write ``payload`` and replace ``path`` in one rename.

    The temp file is in the same directory and has a unique name, so a second
    writer cannot rename this writer's half-finished bytes. ``os.replace`` is
    atomic on one filesystem. The destination is not opened until the temp
    file has been fsynced. On failure the temp file is removed and ``path``
    is left as it was.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    dir_fd = None
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
        os.fsync(dir_fd)
    except OSError:
        return
    finally:
        if dir_fd is not None:
            os.close(dir_fd)


def parse_rclone_hashsum(text: str) -> dict[str, str]:
    """Parse ``rclone hashsum MD5`` lines: ``<digest><spaces><path>``."""
    found: dict[str, list[tuple[str, str]]] = {}
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        parts = raw.split(None, 1)
        if len(parts) != 2:
            continue
        digest, name = parts
        digest = digest.strip().lower()
        if len(digest) < 8 or any(ch not in "0123456789abcdef" for ch in digest):
            continue
        cid = filename_card_id(name)
        if not cid:
            continue
        suffix = Path(name).suffix.lower()
        found.setdefault(cid, []).append((suffix, digest[:8]))
    out: dict[str, str] = {}
    for cid, rows in found.items():
        rows.sort(key=lambda row: 0 if row[0] == ".png" else 1)
        out[cid] = rows[0][1]
    return out


def _log_manifest(message: str) -> None:
    """Progress line. Callers must not pass secrets, remotes, or object names."""
    print(f"[manifest] {message}", file=sys.stderr, flush=True)


def _clip(text: str, limit: int = 300) -> str:
    flat = " ".join(str(text or "").split())
    if len(flat) > limit:
        return flat[:limit] + "..."
    return flat


def _iter_proc_lines(proc, interval_s: float, on_timeout):
    """Yield stdout chunks. Call ``on_timeout`` when ``interval_s`` passes with no data."""
    stream = proc.stdout
    if stream is None:
        return
    try:
        fd = stream.fileno()
    except (AttributeError, OSError, ValueError):
        yield from stream
        return
    while True:
        ready, _, _ = select.select([fd], [], [], interval_s)
        if not ready:
            if proc.poll() is not None:
                leftover = stream.read()
                if leftover:
                    yield leftover
                return
            on_timeout()
            continue
        line = stream.readline()
        if line == "":
            return
        yield line


def _consume_hashsum_stdout(
    proc,
    *,
    every: int,
    interval_s: float,
    clock,
    log,
) -> str:
    """Read rclone stdout and log a count every ``every`` lines or ``interval_s``."""
    parts: list[str] = []
    seen = 0
    start = clock()
    last = start
    log("hashsum start")

    def emit(now: float | None = None) -> None:
        nonlocal last
        current = clock() if now is None else now
        elapsed = max(0.0, current - start)
        log(f"hashsum running objects={seen} elapsed_s={elapsed:.0f}")
        last = current

    for chunk in _iter_proc_lines(proc, interval_s, emit):
        parts.append(chunk)
        added = chunk.count("\n")
        previous = seen
        seen += added
        now = clock()
        crossed = every > 0 and added > 0 and seen // every > previous // every
        if crossed or now - last >= interval_s:
            emit(now)
    elapsed = max(0.0, clock() - start)
    log(f"hashsum done objects={seen} elapsed_s={elapsed:.0f}")
    return "".join(parts)


def manifest_from_rclone(
    remote: str,
    *,
    popen=None,
    clock=None,
    log=None,
    every: int = HASH_PROGRESS_EVERY,
    interval_s: float = HASH_PROGRESS_INTERVAL_S,
) -> dict[str, str]:
    """Hash object bodies on an rclone remote. Never trust the R2 etag.

    Stdout is the hash listing and is not logged. Progress lines are a count
    and an elapsed time only.
    """
    import subprocess

    remote = remote.strip().rstrip("/")
    if not remote:
        raise ManifestRejected("rclone remote is empty")
    cmd = ["rclone", "hashsum", "MD5", "--download", remote]
    if any(part == "sync" or part.startswith("--delete") for part in cmd):
        raise ManifestRejected("rclone hashsum must not sync or delete")
    opener = popen or subprocess.Popen
    proc = opener(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stderr_parts: list[str] = []

    def _drain_stderr() -> None:
        pipe = getattr(proc, "stderr", None)
        if pipe is None:
            return
        try:
            stderr_parts.append(pipe.read() or "")
        except Exception:
            return

    drainer = threading.Thread(target=_drain_stderr, daemon=True)
    drainer.start()
    code = None
    try:
        stdout_text = _consume_hashsum_stdout(
            proc,
            every=every,
            interval_s=interval_s,
            clock=clock or time.monotonic,
            log=log or _log_manifest,
        )
    finally:
        wait = getattr(proc, "wait", None)
        if callable(wait):
            try:
                code = wait()
            except Exception:
                code = getattr(proc, "returncode", 1)
        drainer.join(timeout=5)
    if code is None:
        code = getattr(proc, "returncode", None)
    if code not in (0, None):
        detail = _clip("".join(stderr_parts))
        raise ManifestRejected(f"rclone hashsum failed ({code}): {detail}")
    parsed = parse_rclone_hashsum(stdout_text)
    if not parsed:
        raise ManifestRejected("rclone hashsum returned no card images")
    return parsed


def _cdn_hash_one(base: str, card_id: str) -> tuple[str, str | None]:
    url = f"{base.rstrip('/')}/{card_id}.png"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "OPCG-manifest/1.0", "Accept": "image/png,*/*"},
    )
    data = b""
    last_error: Exception | None = None
    for _attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status != 200:
                    return card_id, None
                data = resp.read()
            last_error = None
            break
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 403, 410):
                return card_id, None
            last_error = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
    if last_error is not None:
        print(f"[manifest] skip {card_id}: {last_error}", file=sys.stderr)
        return card_id, None
    if not _looks_like_image(data):
        return card_id, None
    return card_id, content_md5_prefix(data)


def _looks_like_image(data: bytes) -> bool:
    """Reject HTML error pages. Real art may be PNG or, rarely, WebP/JPEG bytes."""
    if len(data) < 32:
        return False
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if data.startswith(b"\xff\xd8\xff"):
        return True
    if data.startswith((b"GIF87a", b"GIF89a")):
        return True
    return data.startswith(b"RIFF") and data[8:12] == b"WEBP"


def manifest_from_cdn(card_ids: list[str], base: str = DEFAULT_CDN, workers: int = 32) -> dict[str, str]:
    ids = [normalize_card_id(cid) for cid in card_ids]
    ids = sorted({cid for cid in ids if cid})
    out: dict[str, str] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_cdn_hash_one, base, cid) for cid in ids]
        for fut in as_completed(futures):
            cid, prefix = fut.result()
            done += 1
            if prefix:
                out[cid] = prefix
            if done % 400 == 0 or done == len(ids):
                print(f"[manifest] hashed {done}/{len(ids)} kept {len(out)}", file=sys.stderr)
    return out


def manifest_from_etag_listing(path: Path) -> dict[str, str]:
    """Turn a Manager key→ETag export into a manifest.

    Single-part uploads only. The ETag must be the content MD5. Multipart
    ETags contain a hyphen and a part count and are rejected.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    objects = data.get("objects") if isinstance(data, dict) else None
    if not isinstance(objects, dict) or not objects:
        raise ManifestRejected("etag listing must be a JSON object with a non-empty 'objects' map")
    found: dict[str, list[tuple[str, str]]] = {}
    for name, etag in objects.items():
        cid = filename_card_id(str(name))
        if not cid:
            continue
        digest = str(etag or "").strip().lower().strip('"')
        if "-" in digest:
            raise ManifestRejected(
                f"{name}: multipart etag is not a content md5; "
                "--from-etag-listing is for single-part uploads only"
            )
        if len(digest) != 32 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ManifestRejected(f"{name}: etag is not a 32-char hex md5")
        suffix = Path(str(name)).suffix.lower()
        found.setdefault(cid, []).append((suffix, digest[:8]))
    if not found:
        raise ManifestRejected("etag listing contained no card images")
    out: dict[str, str] = {}
    for cid, rows in found.items():
        rows.sort(key=lambda row: 0 if row[0] == ".png" else 1)
        out[cid] = rows[0][1]
    return out


def merge_missing_entries(base: dict[str, str], additions: dict[str, str]) -> dict[str, str]:
    """Return ``base`` plus keys that exist only in ``additions``.

    Values already in ``base`` are kept. Keys only in ``base`` are kept.
    Nothing is deleted.
    """
    merged = dict(base)
    for key, value in additions.items():
        if key not in merged:
            merged[key] = value
    return merged


def apply_missing_entries(base_path: Path, additions_path: Path) -> list[str]:
    """Add keys from ``additions_path`` that ``base_path`` does not have.

    Existing base entries are not changed or removed. When nothing is missing,
    ``base_path`` is left byte-for-byte. Returns the added ids, sorted.
    """
    base = load_manifest(base_path)
    additions = load_manifest(additions_path)
    added = sorted(key for key in additions if key not in base)
    if not added:
        return []
    write_manifest(base_path, merge_missing_entries(base, additions))
    return added


def catalog_ids(index_path: Path) -> list[str]:
    data = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("cards_by_id.json must be an object")
    return sorted(normalize_card_id(str(key)) for key in data if str(key).strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the card-image content-hash manifest")
    parser.add_argument("--output", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--merge-missing-from",
        type=Path,
        default=None,
        help="Add keys from this manifest that --output does not already have. "
        "Existing output entries are not changed or removed",
    )
    parser.add_argument("--rclone-remote", default=os.getenv("OPCG_R2_RCLONE_REMOTE", ""))
    parser.add_argument("--from-cdn", action="store_true", help="Hash public CDN bytes (snapshot only)")
    parser.add_argument(
        "--from-etag-listing",
        type=Path,
        default=None,
        help="Manager JSON of key→ETag. Single-part uploads only; the ETag must be the content MD5",
    )
    parser.add_argument("--cdn-base", default=DEFAULT_CDN)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args(argv)
    supplied = list(sys.argv[1:] if argv is None else argv)
    explicit_remote = any(
        item == "--rclone-remote" or item.startswith("--rclone-remote=") for item in supplied
    )
    merging = args.merge_missing_from is not None
    if merging and (explicit_remote or args.from_cdn or args.from_etag_listing is not None):
        print("Do not combine --merge-missing-from with a rebuild source", file=sys.stderr)
        return 2
    if merging:
        if not args.output.is_file():
            print(f"error: --output does not exist: {args.output}", file=sys.stderr)
            return 1
        try:
            added = apply_missing_entries(args.output, args.merge_missing_from)
        except (OSError, json.JSONDecodeError, ValueError, ManifestRejected) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"added {len(added)}")
        if added:
            print("added keys: " + ",".join(added))
        return 0

    modes = [bool(args.rclone_remote), bool(args.from_cdn), args.from_etag_listing is not None]
    if sum(modes) != 1:
        print("Pass exactly one of --rclone-remote, --from-cdn, or --from-etag-listing", file=sys.stderr)
        return 2
    try:
        if args.rclone_remote:
            fresh = manifest_from_rclone(args.rclone_remote)
        elif args.from_etag_listing is not None:
            fresh = manifest_from_etag_listing(args.from_etag_listing)
        else:
            fresh = manifest_from_cdn(catalog_ids(args.index), args.cdn_base, args.workers)
        write_manifest(args.output, fresh)
    except ManifestRejected as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {len(fresh)} entries to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
