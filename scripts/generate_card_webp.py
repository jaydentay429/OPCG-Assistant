#!/usr/bin/env python3
"""Write WebP derivatives next to the card PNGs on R2. Never touch the PNGs.

Reads ``<ID>.png`` from the ``opcg-packs`` bucket (``--from-r2``) or from a
local packs directory (``--packs``). For each file it uploads three new
objects, keyed by the same 8-character MD5 prefix the card-image manifest
stores as ``?h=``:

    <ID>.w200.<hash>.webp     list thumbnail, max width 200, quality 75
    <ID>.w320.<hash>.webp     list thumbnail, max width 320, quality 75
    <ID>.<hash>.webp          full pixel size, quality 80 (for the card page)

When the PNG bytes change, the hash changes, so the next run adds new keys.
Old WebP objects are left in place. This script has no delete call. ``put``
refuses any key that is not one of those derivatives, so a PNG cannot be
replaced. Existing derivative keys are skipped unless ``--force``.

Credentials come from the environment only (or the untracked ``.env`` that
``load_dotenv`` already uses for other scripts). Nothing is written back.

    R2_ACCESS_KEY_ID
    R2_SECRET_ACCESS_KEY
    R2_ENDPOINT                 or OPCG_R2_ENDPOINT
    R2_ACCOUNT_ID               or OPCG_R2_ACCOUNT_ID or CLOUDFLARE_ACCOUNT_ID
    R2_BUCKET                   or OPCG_R2_BUCKET (default opcg-packs)

From the repo root, against the bucket (read every PNG, upload only missing
WebP). ``--dry-run`` lists keys and does not encode or upload:

    python3 scripts/generate_card_webp.py --from-r2 --dry-run --limit 20
    python3 scripts/generate_card_webp.py --from-r2

``--limit`` counts source PNGs, not variant objects. A re-run skips keys that
already exist, so a stopped upload can be continued. ``--dry-run`` still reads
source bytes so it can print the content-hash keys, and it does not encode or
upload. Cache-Control on each new object is ``public, max-age=31536000, immutable``.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_card_image_manifest import (  # noqa: E402
    content_md5_prefix,
    filename_card_id,
    is_generated_webp_name,
    normalize_card_id,
)
from scripts.copy_new_pack_images_to_r2 import is_card_png_filename, list_card_pngs  # noqa: E402

THUMB_KINDS = ("w200", "w320")
ALL_KINDS = ("w200", "w320", "full")
KIND_WIDTH = {"w200": 200, "w320": 320, "full": None}
KIND_QUALITY = {"w200": 75, "w320": 75, "full": 80}
WEBP_METHOD = 4
CONTENT_TYPE = "image/webp"
CACHE_CONTROL = "public, max-age=31536000, immutable"
R2_REGION = "auto"
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class UnsafeUpload(ValueError):
    """The key is a PNG or anything other than a generated WebP derivative."""


class R2ConfigError(ValueError):
    """Missing credential or endpoint. The message names variables, not values."""


@dataclass(frozen=True)
class R2Config:
    access_key: str
    secret_key: str
    endpoint: str
    bucket: str
    region: str = R2_REGION


@dataclass
class RunStats:
    scanned: int = 0
    skipped: int = 0
    uploaded: int = 0
    would_upload: int = 0
    failed: int = 0
    dry_run: bool = False
    elapsed_s: float = 0.0
    sample_keys: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed == 0


def webp_object_key(card_id: str, hash8: str, kind: str) -> str:
    """Object key for one derivative. The hash is the PNG content prefix."""
    cid = normalize_card_id(card_id)
    digest = str(hash8 or "").strip().lower()
    if not cid or len(digest) != 8 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("card id and 8-char lowercase content hash are required")
    if kind == "full":
        name = f"{cid}.{digest}.webp"
    elif kind in THUMB_KINDS:
        name = f"{cid}.{kind}.{digest}.webp"
    else:
        raise ValueError(f"unknown variant {kind}")
    if not is_generated_webp_name(name):
        raise ValueError(f"refusing key {name}")
    return name


def assert_upload_allowed(key: str) -> None:
    """Reject PNG keys and any name that is not a generated derivative."""
    text = str(key or "")
    if not text or text != Path(text).name or "/" in text or "\\" in text:
        raise UnsafeUpload(f"refusing key {key!r}")
    if text.lower().endswith(".png"):
        raise UnsafeUpload("refusing to upload or overwrite a PNG")
    if not is_generated_webp_name(text):
        raise UnsafeUpload(f"refusing non-derivative key {key!r}")


def encode_variant(png_bytes: bytes, kind: str) -> bytes:
    """Resize (thumbs only, never upscale) and encode WebP. Does not write a file."""
    if kind not in KIND_WIDTH:
        raise ValueError(f"unknown variant {kind}")
    from PIL import Image

    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    with Image.open(io.BytesIO(png_bytes)) as raw:
        rgba = raw.convert("RGBA")
        opaque = rgba.getextrema()[3][0] == 255
        im = rgba.convert("RGB") if opaque else rgba
        width = KIND_WIDTH[kind]
        if width is not None and im.width > width:
            height = max(1, round(im.height * width / im.width))
            im = im.resize((width, height), resample)
        buf = io.BytesIO()
        im.save(buf, format="WEBP", quality=KIND_QUALITY[kind], method=WEBP_METHOD)
        return buf.getvalue()


def _first_env(env: dict[str, str], *names: str) -> str:
    for name in names:
        value = str(env.get(name) or "").strip()
        if value:
            return value
    return ""


def load_r2_config(env: dict[str, str] | None = None) -> R2Config:
    """Read R2 settings from env. Error text lists variable names, never values."""
    source = os.environ if env is None else env
    access = _first_env(source, "R2_ACCESS_KEY_ID")
    secret = _first_env(source, "R2_SECRET_ACCESS_KEY")
    endpoint = _first_env(source, "R2_ENDPOINT", "OPCG_R2_ENDPOINT")
    account = _first_env(source, "R2_ACCOUNT_ID", "OPCG_R2_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID")
    bucket = _first_env(source, "R2_BUCKET", "OPCG_R2_BUCKET") or "opcg-packs"
    missing = []
    if not access:
        missing.append("R2_ACCESS_KEY_ID")
    if not secret:
        missing.append("R2_SECRET_ACCESS_KEY")
    if not endpoint and not account:
        missing.append("R2_ENDPOINT or R2_ACCOUNT_ID")
    if missing:
        raise R2ConfigError("missing " + ", ".join(missing))
    if not endpoint:
        if not account or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" for ch in account):
            raise R2ConfigError("R2_ACCOUNT_ID must be a hostname label, or set R2_ENDPOINT")
        endpoint = f"https://{account}.r2.cloudflarestorage.com"
    endpoint = endpoint.strip().rstrip("/")
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme not in ("https", "http") or not parsed.netloc or parsed.path not in ("", "/"):
        raise R2ConfigError("R2_ENDPOINT must be https://<account>.r2.cloudflarestorage.com")
    if "/" in bucket or not bucket:
        raise R2ConfigError("R2_BUCKET must be a single path segment")
    return R2Config(access_key=access, secret_key=secret, endpoint=endpoint, bucket=bucket)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sign(secret: str, datestamp: str, region: str, service: str, string_to_sign: str) -> str:
    key = ("AWS4" + secret).encode("utf-8")
    for part in (datestamp, region, service, "aws4_request"):
        key = hmac.new(key, part.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()


def authorization_header(
    *,
    method: str,
    canonical_uri: str,
    canonical_query: str,
    host: str,
    amz_date: str,
    payload_hash: str,
    access_key: str,
    secret_key: str,
    region: str,
    extra_headers: dict[str, str] | None = None,
    service: str = "s3",
) -> str:
    """SigV4 Authorization value. ``extra_headers`` are lower-cased and signed."""
    headers = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    for name, value in (extra_headers or {}).items():
        headers[name.strip().lower()] = " ".join(str(value).split())
    signed = sorted(headers)
    canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in signed)
    canonical = "\n".join(
        [
            method,
            canonical_uri,
            canonical_query,
            canonical_headers,
            ";".join(signed),
            payload_hash,
        ]
    )
    datestamp = amz_date[:8]
    scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            _sha256_hex(canonical.encode("utf-8")),
        ]
    )
    signature = _sign(secret_key, datestamp, region, service, string_to_sign)
    return (
        "AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{scope}, "
        f"SignedHeaders={';'.join(signed)}, "
        f"Signature={signature}"
    )


def _canonical_query(params: list[tuple[str, str]]) -> str:
    parts = []
    for key, value in params:
        parts.append(
            (
                urllib.parse.quote(str(key), safe="-_.~"),
                urllib.parse.quote(str(value), safe="-_.~"),
            )
        )
    parts.sort()
    return "&".join(f"{key}={value}" for key, value in parts)


def _xml_text(root: ET.Element, tag: str) -> str:
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}", 1)[0] + "}"
    node = root.find(f"{ns}{tag}")
    return (node.text or "").strip() if node is not None and node.text else ""


def _xml_keys(root: ET.Element) -> list[str]:
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}", 1)[0] + "}"
    keys: list[str] = []
    for node in root.iter(f"{ns}Key"):
        if node.text:
            keys.append(node.text)
    return keys


class R2Client:
    """Path-style S3 client for one bucket. There is no delete method."""

    def __init__(self, config: R2Config, opener=None) -> None:
        self.config = config
        parsed = urllib.parse.urlsplit(config.endpoint)
        self._scheme = parsed.scheme
        self._host = parsed.netloc
        self._opener = opener or urllib.request.urlopen

    def keys(self) -> set[str]:
        found: set[str] = set()
        token = ""
        while True:
            params = [("list-type", "2"), ("max-keys", "1000")]
            if token:
                params.append(("continuation-token", token))
            status, body, _headers = self._request("GET", "", query=params)
            if status != 200:
                raise R2ConfigError(f"list failed with HTTP {status}: {_clip(body)}")
            root = ET.fromstring(body)
            found.update(_xml_keys(root))
            truncated = _xml_text(root, "IsTruncated").lower() == "true"
            token = _xml_text(root, "NextContinuationToken")
            if not truncated or not token:
                break
        return found

    def get_bytes(self, key: str) -> bytes:
        status, body, _headers = self._request("GET", key)
        if status != 200:
            raise OSError(f"GET {key} failed with HTTP {status}: {_clip(body)}")
        return body

    def put_webp(self, key: str, body: bytes) -> None:
        assert_upload_allowed(key)
        status, response, _headers = self._request(
            "PUT",
            key,
            body=body,
            extra_headers={
                "content-type": CONTENT_TYPE,
                "cache-control": CACHE_CONTROL,
            },
        )
        if status not in (200, 201):
            raise OSError(f"PUT {key} failed with HTTP {status}: {_clip(response)}")

    def _request(
        self,
        method: str,
        key: str,
        *,
        query: list[tuple[str, str]] | None = None,
        body: bytes = b"",
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes, dict[str, str]]:
        canonical_uri = "/" + urllib.parse.quote(self.config.bucket, safe="-_.~")
        if key:
            canonical_uri += "/" + urllib.parse.quote(key, safe="-_.~")
        canonical_query = _canonical_query(query or [])
        payload_hash = _sha256_hex(body)
        amz_date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        auth = authorization_header(
            method=method,
            canonical_uri=canonical_uri,
            canonical_query=canonical_query,
            host=self._host,
            amz_date=amz_date,
            payload_hash=payload_hash,
            access_key=self.config.access_key,
            secret_key=self.config.secret_key,
            region=self.config.region,
            extra_headers=extra_headers,
        )
        headers = {
            "Host": self._host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
            "Authorization": auth,
            "User-Agent": "OPCG-webp/1.0",
        }
        for name, value in (extra_headers or {}).items():
            headers[name] = value
        url = f"{self._scheme}://{self._host}{canonical_uri}"
        if canonical_query:
            url = f"{url}?{canonical_query}"
        request = urllib.request.Request(url, data=body if method != "GET" else None, headers=headers, method=method)
        delay = 1.0
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with self._opener(request, timeout=120) as response:
                    payload = response.read()
                    return response.status, payload, dict(response.headers.items())
            except urllib.error.HTTPError as exc:
                payload = exc.read()
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(delay)
                    delay *= 2
                    last_error = exc
                    continue
                return exc.code, payload, {}
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        raise OSError(f"{method} {key or self.config.bucket} failed: {last_error}")


def iter_pack_pngs(packs_dir: Path) -> Iterator[tuple[str, bytes]]:
    for name in list_card_pngs(packs_dir):
        card_id = filename_card_id(name)
        if not card_id:
            continue
        yield card_id, (packs_dir / name).read_bytes()


def iter_r2_pngs(client: R2Client, keys: Iterable[str]) -> Iterator[tuple[str, bytes]]:
    names = sorted(name for name in keys if is_card_png_filename(name))
    for name in names:
        card_id = filename_card_id(name)
        if not card_id:
            continue
        yield card_id, client.get_bytes(name)


def run_generation(
    sources: Iterable[tuple[str, bytes]],
    store,
    *,
    existing: set[str] | None = None,
    dry_run: bool = False,
    force: bool = False,
    limit: int | None = None,
    workers: int = 1,
    encoder=encode_variant,
) -> RunStats:
    """Upload missing derivatives. ``store`` needs ``put_webp`` only.

    Does not delete. Does not call ``put_webp`` for a key that already exists
    unless ``force``. ``dry_run`` does not encode and does not call ``put_webp``.
    """
    stats = RunStats(dry_run=dry_run)
    present = set(existing or ())
    lock = threading.Lock()
    started = time.monotonic()

    def process(item: tuple[str, bytes]) -> None:
        card_id, png_bytes = item
        try:
            digest = content_md5_prefix(png_bytes)
            for kind in ALL_KINDS:
                key = webp_object_key(card_id, digest, kind)
                assert_upload_allowed(key)
                with lock:
                    already = key in present
                if already and not force:
                    with lock:
                        stats.skipped += 1
                    continue
                if dry_run:
                    with lock:
                        stats.would_upload += 1
                        if len(stats.sample_keys) < 80:
                            stats.sample_keys.append(key)
                    continue
                body = encoder(png_bytes, kind)
                store.put_webp(key, body)
                with lock:
                    present.add(key)
                    stats.uploaded += 1
                    if len(stats.sample_keys) < 80:
                        stats.sample_keys.append(key)
        except Exception as exc:  # noqa: BLE001 — one card must not abort the run
            with lock:
                stats.failed += 1
            _log(f"FAILED {card_id}: {_clip(str(exc).encode('utf-8', 'replace'))}")

    pending: list = []

    def drain(block: bool) -> None:
        if not pending:
            return
        if block or len(pending) >= max(1, workers):
            pending.pop(0).result()

    if workers <= 1:
        for card_id, png_bytes in sources:
            if limit is not None and stats.scanned >= limit:
                break
            stats.scanned += 1
            process((card_id, png_bytes))
            if stats.scanned % 200 == 0:
                _log(
                    f"progress scanned={stats.scanned} skipped={stats.skipped} "
                    f"uploaded={stats.uploaded} would_upload={stats.would_upload} failed={stats.failed}"
                )
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for card_id, png_bytes in sources:
                if limit is not None and stats.scanned >= limit:
                    break
                stats.scanned += 1
                pending.append(pool.submit(process, (card_id, png_bytes)))
                if len(pending) >= workers * 2:
                    drain(True)
                if stats.scanned % 200 == 0:
                    _log(
                        f"progress scanned={stats.scanned} skipped={stats.skipped} "
                        f"uploaded={stats.uploaded} would_upload={stats.would_upload} failed={stats.failed}"
                    )
            while pending:
                drain(True)
    stats.elapsed_s = time.monotonic() - started
    return stats


def _clip(data: bytes | str, limit: int = 300) -> str:
    if isinstance(data, bytes):
        text = data.decode("utf-8", "replace")
    else:
        text = data
    flat = " ".join(text.split())
    if len(flat) > limit:
        return flat[:limit] + "..."
    return flat


def _log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{stamp}] [webp] {message}", flush=True)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env", override=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upload WebP derivatives for card PNGs. Never writes a PNG.")
    parser.add_argument("--packs", type=Path, default=None, help="Local packs directory of <ID>.png files")
    parser.add_argument("--from-r2", action="store_true", help="Read source PNGs from the R2 bucket")
    parser.add_argument("--dry-run", action="store_true", help="List new keys. Do not encode or upload")
    parser.add_argument("--force", action="store_true", help="Re-upload derivative WebP keys that already exist")
    parser.add_argument("--limit", type=int, default=None, help="Max source PNGs to consider")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)

    if bool(args.packs) == bool(args.from_r2):
        print("Pass exactly one of --packs or --from-r2", file=sys.stderr)
        return 2
    if args.limit is not None and args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return 2
    if args.workers <= 0:
        print("--workers must be positive", file=sys.stderr)
        return 2
    if args.packs is not None and not args.packs.is_dir():
        print(f"packs directory does not exist: {args.packs}", file=sys.stderr)
        return 2

    _load_dotenv()
    try:
        config = load_r2_config()
    except R2ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    client = R2Client(config)
    try:
        existing = client.keys()
    except (R2ConfigError, OSError, ET.ParseError, urllib.error.URLError) as exc:
        print(f"error: list bucket failed: {exc}", file=sys.stderr)
        return 1

    if args.from_r2:
        sources: Iterable[tuple[str, bytes]] = iter_r2_pngs(client, existing)
    else:
        sources = iter_pack_pngs(args.packs)

    mode = "dry-run" if args.dry_run else "upload"
    _log(
        f"start {mode} bucket={config.bucket} force={int(args.force)} "
        f"limit={args.limit if args.limit is not None else '-'} workers={args.workers}"
    )
    stats = run_generation(
        sources,
        client,
        existing=existing,
        dry_run=args.dry_run,
        force=args.force,
        limit=args.limit,
        workers=args.workers,
    )
    for key in stats.sample_keys:
        _log(("would upload " if args.dry_run else "uploaded ") + key)
    _log(
        "done "
        f"scanned={stats.scanned} skipped={stats.skipped} uploaded={stats.uploaded} "
        f"would_upload={stats.would_upload} failed={stats.failed} "
        f"elapsed_s={stats.elapsed_s:.1f} dry_run={int(args.dry_run)}"
    )
    return 0 if stats.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
