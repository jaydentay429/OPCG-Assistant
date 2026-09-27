"""Card-image manifest: content MD5 prefix and the 95% replacement guard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_card_image_manifest import (  # noqa: E402
    ManifestRejected,
    below_keep_ratio,
    content_md5_prefix,
    load_manifest,
    parse_rclone_hashsum,
    write_manifest,
)

MANIFEST = ROOT / "frontend" / "src" / "generated" / "card-image-manifest.json"


def test_content_md5_prefix_is_first_eight_hex_chars():
    assert content_md5_prefix(b"") == "d41d8cd9"
    assert content_md5_prefix(b"opcg") == "bd4551ef"
    assert len(content_md5_prefix(b"opcg")) == 8


def test_below_keep_ratio_rejects_more_than_five_percent():
    assert below_keep_ratio(94, 100) is True
    assert below_keep_ratio(95, 100) is False
    assert below_keep_ratio(100, 100) is False
    assert below_keep_ratio(0, 0) is False


def test_write_keeps_previous_when_new_count_drops_more_than_five_percent(tmp_path: Path):
    path = tmp_path / "card-image-manifest.json"
    previous = {f"ID-{i:04d}": "abcd1234" for i in range(100)}
    write_manifest(path, previous)
    original = path.read_bytes()
    shrunk = {f"ID-{i:04d}": "abcd1234" for i in range(94)}
    try:
        write_manifest(path, shrunk)
    except ManifestRejected as exc:
        assert "more than 5%" in str(exc)
    else:
        raise AssertionError("expected ManifestRejected")
    assert path.read_bytes() == original


def test_write_allows_exactly_ninety_five_percent(tmp_path: Path):
    path = tmp_path / "card-image-manifest.json"
    previous = {f"ID-{i:04d}": "abcd1234" for i in range(100)}
    write_manifest(path, previous)
    kept = {f"ID-{i:04d}": "abcd1234" for i in range(95)}
    write_manifest(path, kept)
    assert len(load_manifest(path)) == 95


def test_write_rejects_empty_and_leaves_previous(tmp_path: Path):
    path = tmp_path / "card-image-manifest.json"
    previous = {"OP13-001": "870e05eb"}
    write_manifest(path, previous)
    original = path.read_bytes()
    try:
        write_manifest(path, {})
    except ManifestRejected as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("expected ManifestRejected")
    assert path.read_bytes() == original


def test_write_refuses_unreadable_previous(tmp_path: Path):
    path = tmp_path / "card-image-manifest.json"
    path.write_text("{", encoding="utf-8")
    try:
        write_manifest(path, {"OP13-001": "870e05eb"})
    except ManifestRejected as exc:
        assert "unreadable" in str(exc)
    else:
        raise AssertionError("expected ManifestRejected")
    assert path.read_text(encoding="utf-8") == "{"


def test_first_write_does_not_need_a_previous_file(tmp_path: Path):
    path = tmp_path / "nested" / "card-image-manifest.json"
    write_manifest(path, {"EB05-048": "f7a50a1d"})
    assert load_manifest(path) == {"EB05-048": "f7a50a1d"}


def test_rclone_hashsum_uses_filename_and_prefers_png():
    text = "\n".join(
        [
            "870e05eb5391791e66ce8fb538a17b27 OP13-001.png",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa OP13-001.jpg",
            "f7a50a1dec01b54fec9493bb029fdb6a EB05-048.png",
            "deadbeefdeadbeefdeadbeefdeadbeef EB01-001-P2 2.png",
            "not-a-hash notes.txt",
        ]
    )
    parsed = parse_rclone_hashsum(text)
    assert parsed["OP13-001"] == "870e05eb"
    assert parsed["EB05-048"] == "f7a50a1d"
    assert "EB01-001-P2" not in parsed
    assert "notes" not in parsed


def test_committed_snapshot_matches_known_cdn_bytes():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["OP13-001"] == "870e05eb"
    assert data["EB05-048"] == "f7a50a1d"
    for missing in ("EB05-046", "OP18-112", "OP16-098-P2"):
        assert missing not in data
    assert data
