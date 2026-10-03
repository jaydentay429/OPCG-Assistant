"""Card-image manifest: content MD5 prefix and the 95% replacement guard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_card_image_manifest import (  # noqa: E402
    ManifestRejected,
    apply_missing_entries,
    below_keep_ratio,
    content_md5_prefix,
    filename_card_id,
    is_generated_webp_name,
    load_manifest,
    main,
    manifest_from_etag_listing,
    merge_missing_entries,
    parse_rclone_hashsum,
    write_manifest,
)

DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"

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


def test_first_rclone_run_can_replace_the_committed_snapshot(tmp_path: Path):
    """No previous file, or a previous file that is the CDN snapshot, both write.

    A VPS run after the first deploy sees the seeded snapshot. New R2 files
    (the snapshot plus later uploads) must replace it. A drop of more than 5%
    still refuses.
    """
    path = tmp_path / "card-image-manifest.json"
    snapshot = load_manifest(MANIFEST)
    assert snapshot["OP13-001"] == "870e05eb"
    write_manifest(path, snapshot)
    extra = {"OP18-112": "4567abcd", "OP16-098-P2": "89abcdef"}
    assert all(key not in snapshot for key in extra)
    fresh = dict(snapshot)
    fresh.update(extra)
    write_manifest(path, fresh)
    saved = load_manifest(path)
    assert saved["OP18-112"] == "4567abcd"
    assert saved["OP16-098-P2"] == "89abcdef"
    assert saved["OP13-001"] == "870e05eb"
    assert len(saved) == len(snapshot) + len(extra)


def test_rclone_hashsum_uses_filename_and_prefers_png():
    text = "\n".join(
        [
            "870e05eb5391791e66ce8fb538a17b27 OP13-001.png",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa OP13-001.jpg",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb OP13-001.w320.870e05eb.webp",
            "cccccccccccccccccccccccccccccccc OP13-001.w200.870e05eb.webp",
            "dddddddddddddddddddddddddddddddd OP13-001.870e05eb.webp",
            "f7a50a1dec01b54fec9493bb029fdb6a EB05-048.png",
            "deadbeefdeadbeefdeadbeefdeadbeef EB01-001-P2 2.png",
            "not-a-hash notes.txt",
        ]
    )
    parsed = parse_rclone_hashsum(text)
    assert parsed["OP13-001"] == "870e05eb"
    assert parsed["EB05-048"] == "f7a50a1d"
    assert "EB01-001-P2" not in parsed
    assert "OP13-001.W320.870E05EB" not in parsed
    assert "notes" not in parsed
    assert filename_card_id("OP13-001.w320.870e05eb.webp") == ""
    assert filename_card_id("OP13-001.870e05eb.webp") == ""
    assert filename_card_id("OP18-005.webp") == "OP18-005"
    assert is_generated_webp_name("OP13-001.w200.870e05eb.webp") is True
    assert is_generated_webp_name("OP18-005.webp") is False


def test_etag_listing_rejects_multipart(tmp_path: Path):
    path = tmp_path / "listing.json"
    path.write_text(
        json.dumps({"objects": {"OP13-001.png": "870e05eb5391791e66ce8fb538a17b27-2"}}),
        encoding="utf-8",
    )
    try:
        manifest_from_etag_listing(path)
    except ManifestRejected as exc:
        assert "single-part" in str(exc)
    else:
        raise AssertionError("expected ManifestRejected")


def test_committed_snapshot_matches_known_cdn_bytes():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["OP13-001"] == "870e05eb"
    assert data["EB05-048"] == "f7a50a1d"
    assert data["EB05-046"] == "92194e1d"
    assert data["EB05-016"] == "9f53b217"
    assert data["EB05-016-P1"] == "f0de3b59"
    assert data["OP18-016"] == "cb8ad5a3"
    assert data["OP18-025"] == "136e365c"
    assert data["OP18-044"] == "274c36d9"
    assert data["OP18-076"] == "a09c5157"
    assert data["OP18-089"] == "02533aad"
    assert data["P-160"] == "aee899d7"
    assert data["OP18-106"] == "c6bb3598"
    assert data["EB05-049"] == "b5ea7367"
    assert len(data) == 5281
    for missing in ("OP18-112", "OP16-098-P2"):
        assert missing not in data


def test_merge_missing_keeps_server_hashes_and_adds_repo_only_keys():
    base = {"OP13-001": "870e05eb", "OP18-025": "136e365c"}
    additions = {"OP13-001": "ffffffff", "OP18-044": "274c36d9"}
    merged = merge_missing_entries(base, additions)
    assert merged["OP13-001"] == "870e05eb"
    assert merged["OP18-025"] == "136e365c"
    assert merged["OP18-044"] == "274c36d9"
    assert set(merged) == {"OP13-001", "OP18-025", "OP18-044"}


def test_apply_missing_entries_writes_only_when_a_key_is_new(tmp_path: Path, capsys):
    server = tmp_path / "server.json"
    repo = tmp_path / "repo.json"
    write_manifest(server, {"OP13-001": "870e05eb", "OP18-025": "136e365c"})
    write_manifest(repo, {"OP13-001": "ffffffff", "OP18-044": "274c36d9"})
    added = apply_missing_entries(server, repo)
    assert added == ["OP18-044"]
    saved = load_manifest(server)
    assert saved["OP13-001"] == "870e05eb"
    assert saved["OP18-025"] == "136e365c"
    assert saved["OP18-044"] == "274c36d9"
    untouched = server.read_bytes()
    assert apply_missing_entries(server, repo) == []
    assert server.read_bytes() == untouched

    assert main(["--merge-missing-from", str(repo), "--output", str(server)]) == 0
    out = capsys.readouterr().out
    assert "added 0\n" in out
    assert server.read_bytes() == untouched

    fresh = tmp_path / "missing.json"
    assert main(["--merge-missing-from", str(repo), "--output", str(fresh)]) == 1
    assert main(["--merge-missing-from", str(repo), "--output", str(server), "--from-cdn"]) == 2


def test_deploy_workflow_merges_repo_only_manifest_entries():
    text = DEPLOY.read_text(encoding="utf-8")
    pull_at = text.index("Pull card image manifest from VPS")
    build_at = text.index("name: Build frontend")
    publish_at = text.index("Add repo-only card image manifest entries on the VPS")
    assert pull_at < build_at < publish_at
    pull = text[pull_at:build_at]
    assert "card-image-manifest.repo.json" in pull
    assert "--merge-missing-from" in pull
    assert "using the VPS card-image manifest plus repo-only entries for this build" in pull
    publish = text[publish_at:]
    assert "--merge-missing-from" in publish
    assert '[ "${added:-0}" != "0" ]' in publish
    assert "wrote ${added} repo-only manifest entries onto the VPS" in publish
    assert "left it unchanged" in publish
    assert "seeded the VPS manifest from the committed snapshot" in publish
    assert "leaving the existing VPS card-image manifest in place" not in text
    assert "--exclude 'frontend/src/generated/card-image-manifest.json'" in text
