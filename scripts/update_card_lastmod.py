#!/usr/bin/env python3
"""Maintain index/card_lastmod.json: the date each card page's content last changed.

The sitemap publishes these dates as <lastmod>. A card's content is its row in
index/cards_by_id.json plus its image hash in the frontend card-image manifest.
A card whose content hash differs from the stored hash (or is new) gets the
current UTC time; unchanged cards keep their date.

  python3 scripts/update_card_lastmod.py            # update after editing cards
  python3 scripts/update_card_lastmod.py --check    # exit 1 when the file is stale
  python3 scripts/update_card_lastmod.py --bootstrap-git
      # rebuild every date from git history of the two source files
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CARDS_PATH = ROOT / "index" / "cards_by_id.json"
MANIFEST_PATH = ROOT / "frontend" / "src" / "generated" / "card-image-manifest.json"
LASTMOD_PATH = ROOT / "index" / "card_lastmod.json"
CARDS_REL = "index/cards_by_id.json"
MANIFEST_REL = "frontend/src/generated/card-image-manifest.json"


def card_content_hash(row: Any, image_hash: str | None) -> str:
    payload = json.dumps(
        {"row": row if isinstance(row, dict) else {}, "img": image_hash or ""},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def content_hashes(cards: dict[str, Any], manifest: dict[str, Any]) -> dict[str, str]:
    return {
        cid: card_content_hash(row, str(manifest.get(cid) or "") or None)
        for cid, row in cards.items()
        if cid
    }


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def apply_hashes(
    stored: dict[str, dict[str, str]],
    hashes: dict[str, str],
    when: str,
) -> tuple[dict[str, dict[str, str]], int]:
    """New dict for exactly the ids in `hashes`; changed or new ids get `when`."""
    out: dict[str, dict[str, str]] = {}
    changed = 0
    for cid in sorted(hashes):
        digest = hashes[cid]
        prev = stored.get(cid) if isinstance(stored.get(cid), dict) else None
        if prev and prev.get("hash") == digest and prev.get("lastmod"):
            out[cid] = {"hash": digest, "lastmod": str(prev["lastmod"])}
        else:
            out[cid] = {"hash": digest, "lastmod": when}
            changed += 1
    return out, changed


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def load_stored() -> dict[str, dict[str, str]]:
    data = load_json(LASTMOD_PATH, {})
    cards = data.get("cards") if isinstance(data, dict) else None
    return cards if isinstance(cards, dict) else {}


def write_stored(cards: dict[str, dict[str, str]]) -> None:
    """One card per line so diffs stay readable."""
    lines = [
        "{",
        '"about": "Per-card content date for the sitemap. Maintained by scripts/update_card_lastmod.py.",',
        '"cards": {',
    ]
    items = sorted(cards.items())
    for i, (cid, rec) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append(
            f"{json.dumps(cid)}: {json.dumps({'hash': rec['hash'], 'lastmod': rec['lastmod']})}{comma}"
        )
    lines.append("}")
    lines.append("}")
    LASTMOD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def current_hashes() -> dict[str, str]:
    cards = load_json(CARDS_PATH, {})
    manifest = load_json(MANIFEST_PATH, {})
    return content_hashes(cards if isinstance(cards, dict) else {}, manifest if isinstance(manifest, dict) else {})


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def _git_json(rev: str, rel: str) -> dict[str, Any]:
    try:
        raw = _git("show", f"{rev}:{rel}")
    except subprocess.CalledProcessError:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def bootstrap_from_git() -> dict[str, dict[str, str]]:
    log = _git("log", "--reverse", "--format=%H %cI", "--", CARDS_REL, MANIFEST_REL)
    stored: dict[str, dict[str, str]] = {}
    for line in log.splitlines():
        rev, _, when = line.partition(" ")
        if not rev:
            continue
        cards = _git_json(rev, CARDS_REL)
        manifest = _git_json(rev, MANIFEST_REL)
        if not cards:
            continue
        stamp = iso_utc(datetime.fromisoformat(when))
        stored, _ = apply_hashes(stored, content_hashes(cards, manifest), stamp)
    return stored


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="exit 1 when any card date is stale")
    parser.add_argument("--bootstrap-git", action="store_true", help="rebuild dates from git history")
    args = parser.parse_args()

    hashes = current_hashes()
    if args.check:
        stored = load_stored()
        stale = [cid for cid, digest in hashes.items() if (stored.get(cid) or {}).get("hash") != digest]
        extra = [cid for cid in stored if cid not in hashes]
        if stale or extra:
            print(
                f"card_lastmod.json is stale: {len(stale)} changed/new, {len(extra)} removed "
                f"(e.g. {(stale or extra)[:5]}). Run python3 scripts/update_card_lastmod.py",
                file=sys.stderr,
            )
            return 1
        print(f"card_lastmod.json ok: {len(hashes)} cards")
        return 0

    base = bootstrap_from_git() if args.bootstrap_git else load_stored()
    cards, changed = apply_hashes(base, hashes, iso_utc(datetime.now(timezone.utc)))
    write_stored(cards)
    print(f"card_lastmod.json: {len(cards)} cards, {changed} dated now")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
