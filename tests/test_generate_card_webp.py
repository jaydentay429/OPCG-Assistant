"""WebP derivative keys, skip/dry-run, and the rule that PNG objects are never written."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_card_image_manifest import (  # noqa: E402
    content_md5_prefix,
    filename_card_id,
    is_generated_webp_name,
)
from scripts.generate_card_webp import (  # noqa: E402
    ALL_KINDS,
    CACHE_CONTROL,
    CONTENT_TYPE,
    EMPTY_SHA256,
    KIND_WIDTH,
    R2ConfigError,
    UnsafeUpload,
    assert_upload_allowed,
    authorization_header,
    encode_variant,
    iter_pack_pngs,
    load_r2_config,
    run_generation,
    webp_object_key,
)


class FakeStore:
    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects = dict(objects or {})
        self.puts: list[str] = []

    def put_webp(self, key: str, body: bytes) -> None:
        assert_upload_allowed(key)
        self.puts.append(key)
        self.objects[key] = body


def _png(width: int, height: int, color=(180, 20, 20)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def _raising_encoder(png_bytes: bytes, kind: str) -> bytes:
    raise AssertionError(f"encoder should not run for {kind}")


def test_object_keys_embed_the_png_content_hash():
    assert webp_object_key("op13-001", "870E05EB", "w200") == "OP13-001.w200.870e05eb.webp"
    assert webp_object_key("OP13-001", "870e05eb", "w320") == "OP13-001.w320.870e05eb.webp"
    assert webp_object_key("OP13-001-P1", "f0de3b59", "full") == "OP13-001-P1.f0de3b59.webp"
    for kind in ALL_KINDS:
        key = webp_object_key("DON00-10001", "5c6cb6fa", kind)
        assert is_generated_webp_name(key)
        assert filename_card_id(key) == ""
        assert not key.endswith(".png")
    with pytest.raises(UnsafeUpload):
        assert_upload_allowed("OP13-001.png")
    with pytest.raises(UnsafeUpload):
        assert_upload_allowed("OP18-005.webp")


def test_encode_widths_do_not_upscale_and_full_size_keeps_pixels():
    wide = _png(600, 838)
    thumb = encode_variant(wide, "w320")
    small = encode_variant(wide, "w200")
    full = encode_variant(wide, "full")
    assert thumb.startswith(b"RIFF") and thumb[8:12] == b"WEBP"
    with Image.open(io.BytesIO(thumb)) as im:
        assert im.size == (320, round(838 * 320 / 600))
    with Image.open(io.BytesIO(small)) as im:
        assert im.size == (200, round(838 * 200 / 600))
    with Image.open(io.BytesIO(full)) as im:
        assert im.size == (600, 838)
    narrow = _png(100, 140)
    with Image.open(io.BytesIO(encode_variant(narrow, "w320"))) as im:
        assert im.size == (100, 140)
    assert KIND_WIDTH["w200"] == 200
    assert KIND_WIDTH["w320"] == 320
    assert KIND_WIDTH["full"] is None


def test_skip_existing_webp_and_dry_run_does_not_write(tmp_path: Path):
    png = _png(40, 56)
    digest = content_md5_prefix(png)
    card_id = "OP13-001"
    existing_key = webp_object_key(card_id, digest, "w200")
    png_key = f"{card_id}.png"
    store = FakeStore({png_key: png, existing_key: b"already-webp"})
    stats = run_generation(
        [(card_id, png)],
        store,
        existing=set(store.objects),
        dry_run=False,
        force=False,
        encoder=encode_variant,
    )
    assert stats.scanned == 1
    assert stats.skipped == 1
    assert stats.uploaded == 2
    assert stats.failed == 0
    assert existing_key not in store.puts
    assert png_key not in store.puts
    assert store.objects[png_key] == png
    assert store.objects[existing_key] == b"already-webp"
    for key in store.puts:
        assert is_generated_webp_name(key)
        assert key.endswith(f".{digest}.webp")

    dry = FakeStore({png_key: png, existing_key: b"already-webp"})
    dry_stats = run_generation(
        [(card_id, png)],
        dry,
        existing=set(dry.objects),
        dry_run=True,
        encoder=_raising_encoder,
    )
    assert dry.puts == []
    assert dry.objects[png_key] == png
    assert dry_stats.would_upload == 2
    assert dry_stats.skipped == 1
    assert dry_stats.uploaded == 0
    assert set(dry_stats.sample_keys) == {
        webp_object_key(card_id, digest, "w320"),
        webp_object_key(card_id, digest, "full"),
    }


def test_force_rewrites_webp_but_not_png():
    png = _png(30, 42)
    digest = content_md5_prefix(png)
    card_id = "ST01-001"
    keys = [webp_object_key(card_id, digest, kind) for kind in ALL_KINDS]
    store = FakeStore({f"{card_id}.png": b"original-png", keys[0]: b"old"})
    stats = run_generation(
        [(card_id, png)],
        store,
        existing=set(store.objects),
        force=True,
        encoder=lambda _png, _kind: b"RIFF-webp",
    )
    assert stats.uploaded == 3
    assert stats.skipped == 0
    assert store.objects[f"{card_id}.png"] == b"original-png"
    assert store.puts == keys
    assert store.objects[keys[0]] == b"RIFF-webp"


def test_limit_counts_source_pngs_not_variants():
    first = _png(20, 28)
    second = _png(22, 30)
    store = FakeStore()
    stats = run_generation(
        [("OP13-001", first), ("OP13-002", second)],
        store,
        existing=set(),
        limit=1,
        dry_run=True,
        encoder=_raising_encoder,
    )
    assert stats.scanned == 1
    assert stats.would_upload == 3
    assert all(key.startswith("OP13-001.") for key in stats.sample_keys)
    assert store.puts == []


def test_changed_png_hash_adds_a_new_key_and_leaves_the_old_webp():
    original = _png(24, 32, (1, 2, 3))
    changed = _png(24, 32, (9, 9, 9))
    old_hash = content_md5_prefix(original)
    new_hash = content_md5_prefix(changed)
    assert old_hash != new_hash
    old_key = webp_object_key("OP18-025", old_hash, "w320")
    store = FakeStore({old_key: b"old-thumb", "OP18-025.png": original})
    stats = run_generation(
        [("OP18-025", changed)],
        store,
        existing={old_key, "OP18-025.png"},
        encoder=lambda _png, _kind: b"new-webp",
    )
    assert stats.skipped == 0
    assert stats.uploaded == 3
    assert store.objects[old_key] == b"old-thumb"
    assert store.objects["OP18-025.png"] == original
    assert webp_object_key("OP18-025", new_hash, "w320") in store.puts


def test_packs_reader_does_not_modify_or_pick_derivatives(tmp_path: Path):
    png = b"\x89PNG\r\n\x1a\n-not-decoded"
    (tmp_path / "OP13-001.png").write_bytes(png)
    (tmp_path / "notes.txt").write_bytes(b"nope")
    (tmp_path / "OP13-001.w320.870e05eb.webp").write_bytes(b"deriv")
    before = sorted(path.name for path in tmp_path.iterdir())
    rows = list(iter_pack_pngs(tmp_path))
    assert rows == [("OP13-001", png)]
    assert (tmp_path / "OP13-001.png").read_bytes() == png
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_config_names_variables_and_builds_endpoint_without_echoing_secrets():
    cfg = load_r2_config(
        {
            "R2_ACCESS_KEY_ID": "access-key",
            "R2_SECRET_ACCESS_KEY": "secret-key",
            "R2_ACCOUNT_ID": "abc123",
        }
    )
    assert cfg.endpoint == "https://abc123.r2.cloudflarestorage.com"
    assert cfg.bucket == "opcg-packs"
    explicit = load_r2_config(
        {
            "R2_ACCESS_KEY_ID": "access-key",
            "R2_SECRET_ACCESS_KEY": "secret-key",
            "R2_ENDPOINT": "https://example.r2.cloudflarestorage.com/",
            "OPCG_R2_BUCKET": "opcg-packs",
        }
    )
    assert explicit.endpoint == "https://example.r2.cloudflarestorage.com"
    with pytest.raises(R2ConfigError) as exc:
        load_r2_config({"R2_ACCESS_KEY_ID": "AKIAsecretvalue", "R2_ACCOUNT_ID": "abc123"})
    assert "R2_SECRET_ACCESS_KEY" in str(exc.value)
    assert "AKIAsecretvalue" not in str(exc.value)


def test_sigv4_matches_the_aws_s3_header_example():
    auth = authorization_header(
        method="GET",
        canonical_uri="/test.txt",
        canonical_query="",
        host="examplebucket.s3.amazonaws.com",
        amz_date="20130524T000000Z",
        payload_hash=EMPTY_SHA256,
        access_key="AKIAIOSFODNN7EXAMPLE",
        secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
        extra_headers={"Range": "bytes=0-9"},
    )
    assert auth == (
        "AWS4-HMAC-SHA256 "
        "Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )


def test_cache_control_constant_is_immutable_for_a_year():
    assert CACHE_CONTROL == "public, max-age=31536000, immutable"
    assert CONTENT_TYPE == "image/webp"
