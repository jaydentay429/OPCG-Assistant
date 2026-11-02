"""WebP derivative keys, skip/dry-run, and the rule that PNG objects are never written."""

from __future__ import annotations

import io
import json
import subprocess
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
    _rclone_stdout,
    assert_upload_allowed,
    authorization_header,
    encode_variant,
    iter_pack_pngs,
    load_r2_config,
    parse_rclone_config_dump,
    parse_rclone_config_show,
    resolve_r2_config,
    run_generation,
    split_rclone_remote,
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


_RCLONE_DUMP = json.dumps(
    {
        "opcg-r2": {
            "type": "s3",
            "provider": "Cloudflare",
            "access_key_id": "r2-access",
            "secret_access_key": "r2-secret-value",
            "endpoint": "https://abc123.r2.cloudflarestorage.com/",
            "acl": "private",
            "password": "unused-dump-password",
        },
        "other": {
            "access_key_id": "nope",
            "secret_access_key": "other-secret",
            "endpoint": "https://other.example",
        },
    }
)

_RCLONE_SHOW = """
[other]
access_key_id = other-access
secret_access_key = other-show-secret
endpoint = https://zzz.r2.cloudflarestorage.com

[opcg-r2]
type = s3
provider = Cloudflare
access_key_id = "show-access"
secret_access_key = 'show-secret-value'
endpoint = https://abc123.r2.cloudflarestorage.com/
acl = private
password = ignored-password-value
"""


def test_split_rclone_remote_keeps_bucket_and_rejects_prefixes():
    assert split_rclone_remote("opcg-r2:opcg-packs") == ("opcg-r2", "opcg-packs")
    assert split_rclone_remote("opcg-r2:opcg-packs/") == ("opcg-r2", "opcg-packs")
    assert split_rclone_remote("opcg-r2") == ("opcg-r2", "")
    with pytest.raises(R2ConfigError):
        split_rclone_remote("opcg-r2:opcg-packs/prefix")
    with pytest.raises(R2ConfigError):
        split_rclone_remote("opcg-r2:opcg-packs\nexport")
    with pytest.raises(R2ConfigError):
        split_rclone_remote("")
    with pytest.raises(R2ConfigError):
        split_rclone_remote("-opcg-r2:opcg-packs")


def test_rclone_dump_keeps_only_credential_fields_and_hides_values():
    fields = parse_rclone_config_dump(_RCLONE_DUMP, "opcg-r2")
    assert set(fields) == {"access_key_id", "secret_access_key", "endpoint"}
    assert fields["secret_access_key"] == "r2-secret-value"
    assert "unused-dump-password" not in fields.values()
    with pytest.raises(R2ConfigError) as missing_remote:
        parse_rclone_config_dump(_RCLONE_DUMP, "missing")
    assert "not in the config" in str(missing_remote.value)
    assert "r2-secret-value" not in str(missing_remote.value)
    assert "other-secret" not in str(missing_remote.value)
    incomplete = json.dumps(
        {"opcg-r2": {"access_key_id": "a", "secret_access_key": "SUPERSECRET", "type": "s3"}}
    )
    with pytest.raises(R2ConfigError) as missing_endpoint:
        parse_rclone_config_dump(incomplete, "opcg-r2")
    assert "endpoint" in str(missing_endpoint.value)
    assert "SUPERSECRET" not in str(missing_endpoint.value)
    with pytest.raises(R2ConfigError) as not_json:
        parse_rclone_config_dump("not-json SUPERSECRET", "opcg-r2")
    assert str(not_json.value) == "rclone config dump was not JSON"
    assert "SUPERSECRET" not in str(not_json.value)


def test_rclone_show_parses_one_remote_and_quoted_values():
    fields = parse_rclone_config_show(_RCLONE_SHOW, "opcg-r2")
    assert fields == {
        "access_key_id": "show-access",
        "secret_access_key": "show-secret-value",
        "endpoint": "https://abc123.r2.cloudflarestorage.com/",
    }
    headerless = (
        "access_key_id = bare-access\n"
        "secret_access_key = bare-secret\n"
        "endpoint = https://abc123.r2.cloudflarestorage.com\n"
    )
    bare = parse_rclone_config_show(headerless, "opcg-r2")
    assert bare["access_key_id"] == "bare-access"
    assert bare["secret_access_key"] == "bare-secret"
    with pytest.raises(R2ConfigError) as missing:
        parse_rclone_config_show(_RCLONE_SHOW, "absent")
    assert "other-show-secret" not in str(missing.value)
    assert "show-secret-value" not in str(missing.value)


def test_missing_env_uses_rclone_dump_without_calling_show(capsys):
    def boom():
        raise AssertionError("show should not run")

    cfg = resolve_r2_config(
        {},
        "opcg-r2:opcg-packs",
        dump_text=_RCLONE_DUMP,
        show_reader=boom,
    )
    assert cfg.access_key == "r2-access"
    assert cfg.secret_key == "r2-secret-value"
    assert cfg.endpoint == "https://abc123.r2.cloudflarestorage.com"
    assert cfg.bucket == "opcg-packs"
    assert "r2-secret-value" not in repr(cfg)
    assert "r2-access" not in repr(cfg)
    assert "abc123" not in repr(cfg)
    logged = capsys.readouterr().out
    assert "R2 credentials from rclone config" in logged
    assert "r2-secret-value" not in logged
    assert "r2-access" not in logged
    assert "unused-dump-password" not in logged
    assert "abc123" not in logged

    from_env_name = resolve_r2_config(
        {"OPCG_R2_RCLONE_REMOTE": "opcg-r2:opcg-packs"},
        dump_text=_RCLONE_DUMP,
        show_reader=boom,
    )
    assert from_env_name.secret_key == "r2-secret-value"
    assert from_env_name.bucket == "opcg-packs"


def test_complete_env_wins_and_does_not_read_rclone():
    def boom():
        raise AssertionError("rclone should not be read")

    cfg = resolve_r2_config(
        {
            "R2_ACCESS_KEY_ID": "env-access",
            "R2_SECRET_ACCESS_KEY": "env-secret",
            "R2_ACCOUNT_ID": "abc123",
        },
        "opcg-r2:other-bucket",
        dump_reader=boom,
        show_reader=boom,
    )
    assert cfg.access_key == "env-access"
    assert cfg.secret_key == "env-secret"
    assert cfg.bucket == "opcg-packs"
    assert "env-secret" not in repr(cfg)


def test_show_fallback_and_errors_do_not_echo_secrets():
    cfg = resolve_r2_config(
        {},
        "opcg-r2:opcg-packs",
        dump_text="not-json DUMPSECRET",
        show_text=_RCLONE_SHOW,
    )
    assert cfg.access_key == "show-access"
    assert cfg.secret_key == "show-secret-value"
    assert cfg.endpoint == "https://abc123.r2.cloudflarestorage.com"

    with pytest.raises(R2ConfigError) as exc:
        resolve_r2_config(
            {"R2_ACCESS_KEY_ID": "AKIAsecretvalue"},
            "opcg-r2:opcg-packs",
            dump_text="DUMPSECRET not json",
            show_text="[other]\naccess_key_id = x\nsecret_access_key = SHOWSECRET\nendpoint = https://abc.example\n",
        )
    text = str(exc.value)
    assert "DUMPSECRET" not in text
    assert "SHOWSECRET" not in text
    assert "AKIAsecretvalue" not in text
    assert "missing " in text

    def show_should_not_run():
        raise AssertionError("show should not run")

    with pytest.raises(R2ConfigError) as missing_remote:
        resolve_r2_config(
            {},
            "missing:opcg-packs",
            dump_text=_RCLONE_DUMP,
            show_reader=show_should_not_run,
        )
    assert "not in the config" in str(missing_remote.value)
    assert "r2-secret-value" not in str(missing_remote.value)
    assert "other-secret" not in str(missing_remote.value)


class _RcloneProc:
    def __init__(self, code: int, stdout: str, stderr: str) -> None:
        self.returncode = code
        self.stdout = stdout
        self.stderr = stderr


def test_rclone_stdout_errors_omit_captured_secrets():
    def runner(args, **kwargs):
        assert args == ["rclone", "config", "dump"]
        assert kwargs.get("check") is False
        assert "shell" not in kwargs
        return _RcloneProc(1, "STDOUT-SECRET", "STDERR-SECRET")

    with pytest.raises(R2ConfigError) as failed:
        _rclone_stdout(["rclone", "config", "dump"], runner=runner)
    assert "STDOUT-SECRET" not in str(failed.value)
    assert "STDERR-SECRET" not in str(failed.value)
    assert "failed (1)" in str(failed.value)
    assert failed.value.__cause__ is None

    def timed_out(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 30, output=b"TIMEOUT-SECRET")

    with pytest.raises(R2ConfigError) as timeout:
        _rclone_stdout(["rclone", "config", "dump"], runner=timed_out)
    assert "TIMEOUT-SECRET" not in str(timeout.value)
    assert timeout.value.__cause__ is None

    def missing(args, **kwargs):
        raise FileNotFoundError(2, "No such file", "rclone")

    with pytest.raises(R2ConfigError) as not_found:
        _rclone_stdout(["rclone", "config", "dump"], runner=missing)
    assert "not installed" in str(not_found.value)
