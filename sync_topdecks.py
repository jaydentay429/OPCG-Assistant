#!/usr/bin/env python3
"""Sync tournament decks from ONE PIECE TOP DECKS (Japan/Asia + English).

Source: https://onepiecetopdecks.com/deck-list/
Uses WordPress REST (pages parent=1198) and parses TablePress `deckgen?dg=…` links.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
OUT_PATH = BASE_DIR / "meta" / "topdecks_decks.json"
INDEX_PATH = BASE_DIR / "index" / "cards_by_id.json"

WP_PAGES = "https://onepiecetopdecks.com/wp-json/wp/v2/pages"
PARENT_ID = 1198
SITE_ORIGIN = "https://onepiecetopdecks.com"

REQUEST_HEADERS = {
    "User-Agent": "OPCGAssistant/1.0 (+https://optcgassistant.com; tournament-deck sync)",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}

DG_TOKEN_RE = re.compile(
    r"(\d+)n((?:OP|ST|EB|PRB|P)[A-Z0-9]*-?\d{2,4}-\d{3}(?:-[A-Z0-9]+)?)",
    re.I,
)
JP_SLUG_RE = re.compile(r"^(japan|japanese|jp-format)", re.I)
EN_SLUG_RE = re.compile(r"^(english|en-format)", re.I)
CARD_ID_NORM_RE = re.compile(
    r"^([A-Z]{1,4})-?(\d{2})-(\d{3}(?:-[A-Z0-9]+)?)$",
    re.I,
)


def normalize_card_id(raw: str) -> str:
    text = str(raw or "").strip().upper().replace("_", "-").replace(" ", "")
    text = text.replace("－", "-")
    text = re.sub(r"[^A-Z0-9-]", "", text)
    m = CARD_ID_NORM_RE.match(text)
    if m:
        return f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    # Promo P-096
    m2 = re.match(r"^(P-\d{3}(?:-[A-Z0-9]+)?)$", text)
    return m2.group(1) if m2 else text


def classify_format(slug: str, title: str) -> str | None:
    s = (slug or "").strip()
    t = (title or "").strip().lower()
    if JP_SLUG_RE.search(s) or t.startswith("japan:"):
        return "jp"
    if EN_SLUG_RE.search(s) or t.startswith("english:"):
        return "en"
    return None


def parse_dg(dg: str) -> tuple[str | None, dict[str, int]]:
    """Decode 1nOP14-041a4nOP17-109… → (leader, {id: qty}). Leader = first entry."""
    text = unquote(str(dg or "")).strip()
    if not text:
        return None, {}
    cards: dict[str, int] = {}
    leader: str | None = None
    for qty_s, cid_raw in DG_TOKEN_RE.findall(text):
        cid = normalize_card_id(cid_raw)
        qty = max(0, int(qty_s))
        if not cid or qty <= 0:
            continue
        if leader is None:
            leader = cid
        cards[cid] = cards.get(cid, 0) + qty
    return leader, cards


def deck_id_for(meta_slug: str, dg: str, author: str, date: str, leader: str | None) -> str:
    raw = f"{meta_slug}|{dg}|{author}|{date}|{leader or ''}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def strip_html_title(raw: str) -> str:
    text = html.unescape(str(raw or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_json(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> Any:
    resp = session.get(url, params=params, headers=REQUEST_HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


def list_meta_pages(session: requests.Session) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = fetch_json(
            session,
            WP_PAGES,
            {
                "parent": PARENT_ID,
                "per_page": 100,
                "page": page,
                "_fields": "id,slug,title,link,modified",
            },
        )
        if not isinstance(batch, list) or not batch:
            break
        pages.extend(batch)
        if len(batch) < 100:
            break
        page += 1
        time.sleep(0.35)
    return pages


def fetch_page_content(session: requests.Session, page_id: int) -> str:
    data = fetch_json(
        session,
        f"{WP_PAGES}/{page_id}",
        {"_fields": "id,slug,title,link,content,modified"},
    )
    content = data.get("content") or {}
    return str(content.get("rendered") or "")


def parse_deckgen_href(href: str) -> dict[str, str]:
    raw = html.unescape(str(href or "").strip())
    if "deckgen" not in raw.lower():
        return {}
    if "://" not in raw and not raw.startswith("/"):
        # relative deckgen?...
        raw = f"{SITE_ORIGIN}/deck-list/{raw.lstrip('./')}"
    elif raw.startswith("/"):
        raw = f"{SITE_ORIGIN}{raw}"
    # Some hrefs are deckgen?dn=... without path
    if raw.startswith("deckgen?"):
        raw = f"{SITE_ORIGIN}/deck-list/{raw}"
    parsed = urlparse(raw)
    qs = parse_qs(parsed.query)
    out: dict[str, str] = {}
    for key in ("dg", "dn", "au", "cn", "date", "pl", "tn", "hs", "cs"):
        vals = qs.get(key) or []
        if vals:
            out[key] = unquote(str(vals[0]))
    return out


def extract_decks_from_html(
    html_body: str,
    *,
    meta_slug: str,
    meta_title: str,
    meta_link: str,
    fmt: str,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html_body, "html.parser")
    decks: list[dict[str, Any]] = []
    seen: set[str] = set()

    for a in soup.select("a[href*='deckgen']"):
        href = str(a.get("href") or "")
        params = parse_deckgen_href(href)
        dg = params.get("dg") or ""
        if not dg:
            continue
        leader, cards = parse_dg(dg)
        if not cards:
            continue
        did = deck_id_for(
            meta_slug,
            dg,
            params.get("au", ""),
            params.get("date", ""),
            leader,
        )
        if did in seen:
            continue
        seen.add(did)

        # Source page for this deck viewer
        source_url = href if href.startswith("http") else f"{meta_link.rstrip('/')}/deckgen/?{urlparse('?' + href.split('?', 1)[-1]).query if '?' in href else ''}"
        if href.startswith("deckgen?"):
            source_url = f"{meta_link.rstrip('/')}/deckgen/?{href.split('?', 1)[1]}"
        elif "deckgen" in href and not href.startswith("http"):
            source_url = f"{SITE_ORIGIN}/deck-list/{href.lstrip('./')}"

        decks.append(
            {
                "id": did,
                "format": fmt,
                "meta_slug": meta_slug,
                "meta_title": meta_title,
                "meta_url": meta_link,
                "name": params.get("dn") or "",
                "author": params.get("au") or "",
                "country": params.get("cn") or "",
                "date": params.get("date") or "",
                "placement": params.get("pl") or "",
                "tournament": params.get("tn") or "",
                "host": params.get("hs") or "",
                "leader": leader,
                "cards": cards,
                "card_count": sum(cards.values()),
                "source_url": source_url,
                "dg": dg,
            }
        )
    return decks


def load_known_ids() -> set[str]:
    if not INDEX_PATH.exists():
        return set()
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, dict):
        return set()
    return {str(k).upper() for k in data.keys()}


def load_existing_payload() -> dict[str, Any]:
    if not OUT_PATH.exists():
        return {}
    try:
        data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def stored_meta_modified(payload: dict[str, Any]) -> dict[str, str]:
    """slug → modified ISO from last sync."""
    out: dict[str, str] = {}
    formats = payload.get("formats") if isinstance(payload.get("formats"), dict) else {}
    for fmt in ("jp", "en"):
        block = formats.get(fmt) if isinstance(formats.get(fmt), dict) else {}
        metas = block.get("metas") if isinstance(block.get("metas"), list) else []
        for row in metas:
            if not isinstance(row, dict):
                continue
            slug = str(row.get("slug") or "").strip()
            modified = str(row.get("modified") or "").strip()
            if slug:
                out[slug] = modified
    return out


def content_fingerprint(decks: list[dict[str, Any]], meta_mods: dict[str, str]) -> str:
    """Stable hash of deck ids + meta modified stamps (ignore synced_at)."""
    deck_ids = sorted(str(d.get("id") or "") for d in decks if isinstance(d, dict))
    meta_parts = [f"{k}={meta_mods[k]}" for k in sorted(meta_mods)]
    raw = "\n".join(meta_parts) + "\n" + "\n".join(deck_ids)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def collect_unknown_ids(decks: list[dict[str, Any]], known: set[str]) -> set[str]:
    unknown: set[str] = set()
    if not known:
        return unknown
    for d in decks:
        cards = d.get("cards") if isinstance(d.get("cards"), dict) else {}
        for cid in cards:
            cid_s = str(cid)
            if cid_s not in known and normalize_card_id(cid_s) not in known:
                unknown.add(cid_s)
    return unknown


def write_payload(
    *,
    formats: dict[str, dict[str, Any]],
    decks_out: list[dict[str, Any]],
    skipped: int,
    unknown_ids: set[str],
    fetched: int,
    reused: int,
) -> dict[str, Any]:
    payload = {
        "source": SITE_ORIGIN + "/deck-list/",
        "attribution": "ONE PIECE TOP DECKS",
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "formats": formats,
        "decks": decks_out,
        "stats": {
            "metas_jp": len(formats["jp"]["metas"]),
            "metas_en": len(formats["en"]["metas"]),
            "decks": len(decks_out),
            "skipped_pages": skipped,
            "fetched_metas": fetched,
            "reused_metas": reused,
            "unknown_card_ids": sorted(unknown_ids)[:80],
            "unknown_card_id_count": len(unknown_ids),
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync tournament decks from onepiecetopdecks.com")
    parser.add_argument("--sleep", type=float, default=0.4, help="Delay between meta fetches")
    parser.add_argument("--limit-metas", type=int, default=0, help="Debug: only first N metas")
    parser.add_argument(
        "--always-refetch-newest",
        type=int,
        default=8,
        help="Always re-fetch the N most recently modified metas (TablePress can change without page.modified)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Re-fetch every meta page (ignore stored modified stamps)",
    )
    parser.add_argument(
        "--force-write",
        action="store_true",
        help="Write JSON even when deck/meta fingerprint is unchanged",
    )
    args = parser.parse_args()

    session = requests.Session()
    session.trust_env = False
    known = load_known_ids()
    existing = load_existing_payload()
    prev_mods = stored_meta_modified(existing) if not args.full else {}
    prev_decks = existing.get("decks") if isinstance(existing.get("decks"), list) else []
    prev_by_slug: dict[str, list[dict[str, Any]]] = {}
    for d in prev_decks:
        if not isinstance(d, dict):
            continue
        slug = str(d.get("meta_slug") or "").strip()
        if slug:
            prev_by_slug.setdefault(slug, []).append(d)

    print("Listing meta pages…", flush=True)
    metas_raw = list_meta_pages(session)
    print(f"Found {len(metas_raw)} child pages under parent={PARENT_ID}", flush=True)

    formats: dict[str, dict[str, Any]] = {
        "jp": {"label": "Japan / Asia", "metas": []},
        "en": {"label": "English", "metas": []},
    }
    all_decks: list[dict[str, Any]] = []
    skipped = 0
    fetched = 0
    reused = 0
    meta_mods: dict[str, str] = {}

    metas_sorted = sorted(
        metas_raw,
        key=lambda p: str(p.get("modified") or ""),
        reverse=True,
    )
    if args.limit_metas > 0:
        metas_sorted = metas_sorted[: args.limit_metas]

    # TablePress/Elementor rows can change without WordPress bumping page.modified.
    # Always re-fetch the newest N metas so current-format lists do not go stale.
    always_refetch_slugs = {
        str(p.get("slug") or "")
        for p in metas_sorted[: max(0, args.always_refetch_newest)]
        if str(p.get("slug") or "").strip()
    }

    for i, page in enumerate(metas_sorted, 1):
        slug = str(page.get("slug") or "")
        title = strip_html_title((page.get("title") or {}).get("rendered") or "")
        link = str(page.get("link") or "")
        fmt = classify_format(slug, title)
        if not fmt:
            skipped += 1
            continue
        page_id = int(page.get("id") or 0)
        if not page_id:
            continue

        modified = str(page.get("modified") or "").strip()
        meta_mods[slug] = modified
        always_newest = slug in always_refetch_slugs
        need_fetch = (
            args.full
            or always_newest
            or prev_mods.get(slug) != modified
            or slug not in prev_by_slug
        )

        if not need_fetch:
            decks = list(prev_by_slug.get(slug) or [])
            # Refresh light meta fields on cached decks
            for d in decks:
                d["meta_title"] = title
                d["meta_url"] = link or d.get("meta_url") or ""
                d["format"] = fmt
            reused += 1
            print(
                f"[{i}/{len(metas_sorted)}] {fmt} {slug} (cached, decks={len(decks)})",
                flush=True,
            )
        else:
            why = "always-newest" if always_newest and prev_mods.get(slug) == modified else "modified"
            print(f"[{i}/{len(metas_sorted)}] {fmt} {slug} (fetch, {why})", flush=True)
            try:
                body = fetch_page_content(session, page_id)
            except requests.RequestException as exc:
                print(f"  fail: {exc}", flush=True)
                # Keep previous decks for this slug if any
                decks = list(prev_by_slug.get(slug) or [])
                time.sleep(args.sleep)
                formats[fmt]["metas"].append(
                    {
                        "slug": slug,
                        "title": title,
                        "url": link,
                        "modified": modified or prev_mods.get(slug),
                        "deck_count": len(decks),
                        "fetch_error": str(exc),
                    }
                )
                all_decks.extend(decks)
                continue

            decks = extract_decks_from_html(
                body,
                meta_slug=slug,
                meta_title=title,
                meta_link=link or f"{SITE_ORIGIN}/deck-list/{slug}/",
                fmt=fmt,
            )
            fetched += 1
            print(f"  decks={len(decks)}", flush=True)
            time.sleep(args.sleep)

        formats[fmt]["metas"].append(
            {
                "slug": slug,
                "title": title,
                "url": link,
                "modified": modified,
                "deck_count": len(decks),
            }
        )
        all_decks.extend(decks)

    by_id: dict[str, dict[str, Any]] = {}
    for d in all_decks:
        by_id[d["id"]] = d
    decks_out = list(by_id.values())
    decks_out.sort(
        key=lambda d: (d.get("format") or "", d.get("meta_slug") or "", d.get("date") or "", d.get("name") or ""),
        reverse=False,
    )

    unknown_ids = collect_unknown_ids(decks_out, known)
    new_fp = content_fingerprint(decks_out, meta_mods)
    old_fp = content_fingerprint(
        [d for d in prev_decks if isinstance(d, dict)],
        prev_mods,
    )

    prev_count = len([d for d in prev_decks if isinstance(d, dict)])
    # --limit-metas is for debugging; never replace the full library unless forced.
    if args.limit_metas > 0 and not args.force_write and prev_count > 0:
        print(
            f"Refusing to write: --limit-metas={args.limit_metas} would replace "
            f"{prev_count} stored decks with {len(decks_out)}. Re-run with --force-write "
            f"only if intentional.",
            flush=True,
        )
        return
    # Guard against wiping the library when WP returns a partial/empty page set.
    if (
        not args.force_write
        and prev_count >= 200
        and len(decks_out) < max(50, int(prev_count * 0.5))
    ):
        print(
            f"Refusing to write: new deck count {len(decks_out)} is far below "
            f"stored {prev_count} (possible upstream/API failure). Use --force-write to override.",
            flush=True,
        )
        return

    if not args.force_write and existing and new_fp == old_fp and fetched == 0:
        print(
            f"No updates (decks={len(decks_out)} metas_jp={len(formats['jp']['metas'])} "
            f"metas_en={len(formats['en']['metas'])} reused={reused})",
            flush=True,
        )
        return

    if not args.force_write and existing and new_fp == old_fp:
        # Still refresh synced_at / stats so ops and UI show the check ran.
        print(
            f"Fetched {fetched} meta(s); decks unchanged — refreshing synced_at "
            f"(decks={len(decks_out)} reused={reused})",
            flush=True,
        )

    payload = write_payload(
        formats=formats,
        decks_out=decks_out,
        skipped=skipped,
        unknown_ids=unknown_ids,
        fetched=fetched,
        reused=reused,
    )
    print(f"Wrote {OUT_PATH}", flush=True)
    print(
        f"JP metas={payload['stats']['metas_jp']} EN metas={payload['stats']['metas_en']} "
        f"decks={payload['stats']['decks']} fetched={fetched} reused={reused} "
        f"unknown_ids={payload['stats']['unknown_card_id_count']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
