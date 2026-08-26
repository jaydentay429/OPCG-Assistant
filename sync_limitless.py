from __future__ import annotations

import json
import os
import re
import time
from collections import Counter, defaultdict
from itertools import combinations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
META_DIR = BASE_DIR / "meta"
OUTPUT_FILE = META_DIR / "limitless_meta.json"
DEBUG_TOP_DECKS_FILE = META_DIR / "limitless_debug_top_decks.txt"
COOCCURRENCE_FILE = META_DIR / "card_cooccurrence.json"
SOURCE_URL = "https://onepiece.limitlesstcg.com/"
SOURCE_URL_FALLBACK = "https://onepiece.limitlesstcg.com/decks"
MAX_LISTING_PAGES = int(os.getenv("LIMITLESS_MAX_LISTING_PAGES", "80"))
MAX_ARCHETYPE_PAGES = int(os.getenv("LIMITLESS_MAX_ARCHETYPE_PAGES", "240"))
MAX_TOURNAMENT_PAGES = int(os.getenv("LIMITLESS_MAX_TOURNAMENT_PAGES", "220"))
MAX_ARCHETYPE_FETCH = int(os.getenv("LIMITLESS_MAX_ARCHETYPE_FETCH", "800"))
MAX_DECKLIST_PAGES = int(os.getenv("LIMITLESS_MAX_DECKLIST_PAGES", "1000"))
FETCH_STABILITY_ROUNDS = int(os.getenv("LIMITLESS_FETCH_STABILITY_ROUNDS", "3"))


def _load_previous_payload() -> dict[str, Any]:
    try:
        if OUTPUT_FILE.exists():
            return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def parse_top_decks(page_text: str) -> list[dict[str, Any]]:
    decks: list[dict[str, Any]] = []

    normalized_text = re.sub(r"\s+", " ", page_text).strip()
    lower = normalized_text.lower()
    start = lower.find("top decks")
    end_marker = lower.find("complete leader ranking", start if start != -1 else 0)
    if end_marker == -1:
        end_marker = lower.find("recent tournaments", start if start != -1 else 0)
    if start != -1:
        if end_marker != -1 and end_marker > start:
            target_text = normalized_text[start:end_marker]
        else:
            target_text = normalized_text[start : start + 6000]
    else:
        target_text = normalized_text

    # Robust parser for compact text:
    # optional leader card id + rank + archetype + share percent.
    entry_pattern = re.compile(
        r"(?:(OP\d{2}-\d{3}|EB\d{2}-\d{3})\s*)?"
        r"(\d+)\.\s*"
        r"(.+?)\s+"
        r"(\d+(?:[.,]\d+)?)%\s*"
        r"(?:Featured\s+Decklist)?",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in entry_pattern.finditer(target_text):
        leader_card, rank, archetype, share = match.groups()
        rank_value = int(rank)
        if rank_value > 200:
            continue
        archetype_clean = " ".join(archetype.split()).strip(" -|")
        if not is_valid_archetype(archetype_clean):
            continue
        decks.append(
            {
                "leader_card": (leader_card or "").upper(),
                "rank": rank_value,
                "archetype": archetype_clean,
                "share_percent": float(share.replace(",", ".")),
            }
        )
        if len(decks) >= 20:
            break

    # Deduplicate by (leader_card, rank)
    seen: set[tuple[str, int]] = set()
    deduped: list[dict[str, Any]] = []
    for deck in decks:
        if not deck["archetype"]:
            continue
        if not is_valid_archetype(str(deck["archetype"])):
            continue
        key = (deck["leader_card"], deck["rank"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(deck)
    decks = deduped

    META_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_TOP_DECKS_FILE.write_text(target_text[:8000], encoding="utf-8")

    return decks


def fetch_best_page_snapshot(url: str, rounds: int = FETCH_STABILITY_ROUNDS) -> tuple[BeautifulSoup, str]:
    """
    Fetch the same page multiple times and keep the richest snapshot.
    This reduces random under-populated responses from dynamic pages/CDN variance.
    """
    rounds = max(1, int(rounds))
    best_soup: BeautifulSoup | None = None
    best_text = ""
    best_score = -1
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 OPCG-MetaBot/1.0"})
    for i in range(rounds):
        try:
            resp = session.get(url, timeout=25)
            resp.raise_for_status()
        except requests.RequestException:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        score = (
            len(parse_top_decks(text)) * 6
            + len(extract_tournament_links(soup)) * 2
            + len(extract_decks_listing_links(soup))
        )
        if score > best_score:
            best_score = score
            best_soup = soup
            best_text = text
        if i < rounds - 1:
            time.sleep(0.4)
    if best_soup is None:
        # One-shot fallback URL can be more stable than homepage.
        if url.rstrip("/") == SOURCE_URL.rstrip("/"):
            try:
                resp = session.get(SOURCE_URL_FALLBACK, timeout=25)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                text = soup.get_text(" ", strip=True)
                if text.strip():
                    return soup, text
            except requests.RequestException:
                pass
        raise requests.RequestException(f"failed to fetch stable snapshot: {url}")
    return best_soup, best_text


def parse_recent_tournaments(page_text: str) -> list[dict[str, Any]]:
    tournaments: list[dict[str, Any]] = []
    normalized_text = re.sub(r"\s+", " ", page_text).strip()
    lower = normalized_text.lower()
    start = lower.find("recent tournaments")
    end = lower.find("all completed tournaments", start if start != -1 else 0)
    if start != -1:
        section = normalized_text[start : end if end != -1 else start + 10000]
    else:
        section = normalized_text

    # Example:
    # Regional Lille 11th April 2026 • 1536 Players • OP15 FR
    pattern = re.compile(
        r"(.+?)\s+(\d{1,2}(?:st|nd|rd|th)\s+[A-Za-z]+\s+\d{4})\s+•\s+(\d+)\s+Players\s+•\s+([A-Z0-9\.\s]+?)(?=\s+[A-Za-z].+?\d{1,2}(?:st|nd|rd|th)\s+[A-Za-z]+\s+\d{4}\s+•|\s+All Completed Tournaments|$)",
        flags=re.DOTALL,
    )
    for match in pattern.finditer(section):
        name, date_text, players, region_format = match.groups()
        clean_name = " ".join(name.split()).strip(" -|")
        # Remove common prefix contamination when source text is compact.
        clean_name = re.sub(
            r"^(Recent Tournaments|Complete Leader Ranking)\s+",
            "",
            clean_name,
            flags=re.IGNORECASE,
        )
        if len(clean_name) < 3:
            continue
        tournaments.append(
            {
                "name": clean_name,
                "date_text": date_text.strip(),
                "players": int(players),
                "region_format": region_format.strip(),
            }
        )
        if len(tournaments) >= 50:
            break
    return tournaments


def crawl_recent_tournaments_details(
    tournament_links: list[str], max_items: int = 40
) -> list[dict[str, Any]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 OPCG-MetaBot/1.0"})
    out: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for link in tournament_links[: max_items * 2]:
        if not re.search(r"/tournaments/\d+", link):
            continue
        try:
            resp = session.get(link, timeout=20)
            resp.raise_for_status()
        except requests.RequestException:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        title_tag = soup.find("h1") or soup.find("title")
        name = " ".join((title_tag.get_text(" ", strip=True) if title_tag else "").split())
        if not name:
            continue
        name = re.sub(r"\s*[-|–].*$", "", name).strip()
        if not name or name in seen_names:
            continue

        text = soup.get_text(" ", strip=True)
        date_m = re.search(r"(\d{1,2}(?:st|nd|rd|th)\s+[A-Za-z]+\s+\d{4})", text)
        players_m = re.search(r"(\d{2,5})\s+Players", text, flags=re.IGNORECASE)
        format_m = re.search(r"\b(OP\d+(?:\.\d+)?)\b", text, flags=re.IGNORECASE)
        row = {
            "name": name,
            "date_text": date_m.group(1) if date_m else "",
            "players": int(players_m.group(1)) if players_m else 0,
            "region_format": format_m.group(1).upper() if format_m else "",
        }
        seen_names.add(name)
        out.append(row)
        if len(out) >= max_items:
            break
    return out


def extract_complete_leader_ranking_link(soup: BeautifulSoup) -> str | None:
    for a in soup.find_all("a", href=True):
        label = a.get_text(" ", strip=True).lower()
        href = a.get("href", "").strip()
        if not href:
            continue
        if "complete leader ranking" in label or "leader ranking" in label:
            return urljoin(SOURCE_URL, href)
        if "leader" in href.lower() and "ranking" in href.lower():
            return urljoin(SOURCE_URL, href)
    return None


def extract_decks_listing_links(soup: BeautifulSoup) -> list[str]:
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        if "/decks" not in href:
            continue
        full = urljoin(SOURCE_URL, href)
        links.append(full)
    seen: set[str] = set()
    deduped: list[str] = []
    for link in links:
        if link not in seen:
            seen.add(link)
            deduped.append(link)
    return deduped


def expand_listing_pagination(seed_links: list[str], max_pages: int) -> list[str]:
    """
    Proactively expand likely deck listing pagination URLs.
    Helps when the site does not expose all page links in current HTML.
    """
    out = list(seed_links)
    seen = set(out)
    page_cap = max(1, min(max_pages, 300))
    for base in list(seed_links):
        if "/decks" not in base:
            continue
        # keep query style pages; append ?page=N for base deck listing.
        for p in range(2, page_cap + 1):
            if "?" in base:
                candidate = f"{base}&page={p}"
            else:
                candidate = f"{base}?page={p}"
            if candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
    return out


def build_decks_seed_links(max_pages: int) -> list[str]:
    """
    Build explicit deck-related listing seeds from known entry points,
    so crawling does not depend on homepage-exposed links only.
    """
    page_cap = max(1, min(max_pages, 300))
    seeds: list[str] = []
    base_urls = [
        f"{SOURCE_URL.rstrip('/')}/decks",
        f"{SOURCE_URL.rstrip('/')}/decks/list",
    ]
    for base in base_urls:
        seeds.append(base)
        for p in range(2, page_cap + 1):
            seeds.append(f"{base}?page={p}")
    # Dedup preserve order.
    return list(dict.fromkeys(seeds))


def extract_archetype_links(soup: BeautifulSoup) -> list[str]:
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        # Archetype pages are typically like /decks/98
        if not re.search(r"/decks/\d+$", href):
            continue
        links.append(urljoin(SOURCE_URL, href))
    seen: set[str] = set()
    deduped: list[str] = []
    for link in links:
        if link not in seen:
            seen.add(link)
            deduped.append(link)
    return deduped


def parse_decks_listing_entries(page_text: str) -> list[dict[str, Any]]:
    text = re.sub(r"\s+", " ", page_text).strip()
    entries: list[dict[str, Any]] = []

    # Pattern A: rank + archetype + share %
    pattern_share = re.compile(
        r"(\d+)\.\s+(.+?)\s+(\d+(?:[.,]\d+)?)%\s*(?:Featured\s+Decklist)?",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for m in pattern_share.finditer(text):
        rank = int(m.group(1))
        archetype = " ".join(m.group(2).split()).strip(" -|")
        if rank <= 0 or rank > 200 or not is_valid_archetype(archetype):
            continue
        entries.append(
            {
                "leader_card": "",
                "rank": rank,
                "archetype": archetype,
                "share_percent": float(m.group(3).replace(",", ".")),
            }
        )

    # Pattern B: rank + archetype + sample count (no percentage)
    pattern_count = re.compile(
        r"(\d+)\.\s+(.+?)\s+(\d+)(?=\s+\d+\.\s+|\s+All|\s+Complete|$)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for m in pattern_count.finditer(text):
        rank = int(m.group(1))
        archetype = " ".join(m.group(2).split()).strip(" -|")
        sample_count = int(m.group(3))
        if rank <= 0 or rank > 800 or sample_count <= 0:
            continue
        if not is_valid_archetype(archetype):
            continue
        entries.append(
            {
                "leader_card": "",
                "rank": rank,
                "archetype": archetype,
                "share_percent": 0.0,
                "sample_count": sample_count,
            }
        )
        if len(entries) >= 480:
            break

    # Dedup local listing rows by (archetype, rank) to prevent page duplicates.
    dedup: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for e in entries:
        key = (str(e.get("archetype") or "").lower(), int(e.get("rank") or 0))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(e)
    entries = dedup

    return entries


def _guess_archetype_from_deck_href(href: str) -> str:
    h = str(href or "").strip()
    if not h:
        return ""
    m = re.search(r"/decks(?:/list)?/([^/?#]+)", h, flags=re.IGNORECASE)
    if not m:
        return ""
    slug = m.group(1)
    slug = re.sub(r"[-_]+", " ", slug).strip()
    slug = re.sub(r"\b(op|st|eb|prb)\d{1,2}\b", "", slug, flags=re.IGNORECASE).strip()
    slug = " ".join(slug.split())
    if not slug:
        return ""
    # Preserve slash archetypes like blue/yellow.
    slug = slug.replace(" / ", "/")
    return slug.title()


def parse_decks_listing_from_links(soup: BeautifulSoup) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_arch: set[str] = set()
    index = 1
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if "/decks/" not in href:
            continue
        label = " ".join(a.get_text(" ", strip=True).split()).strip(" -|")
        if not is_valid_archetype(label):
            label = _guess_archetype_from_deck_href(href)
        if not is_valid_archetype(label):
            continue
        key = label.lower()
        if key in seen_arch:
            continue
        seen_arch.add(key)
        entries.append(
            {
                "leader_card": "",
                "rank": 1000 + index,
                "archetype": label,
                "share_percent": 0.0,
                "sample_count": 0,
            }
        )
        index += 1
        if len(entries) >= 200:
            break
    return entries


def parse_decks_listing_script_data(soup: BeautifulSoup) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_arch: set[str] = set()

    def _push(archetype: str, rank: int, share: float = 0.0, sample_count: int = 0) -> None:
        name = " ".join(str(archetype or "").split()).strip(" -|")
        if not is_valid_archetype(name):
            return
        key = name.lower()
        if key in seen_arch:
            return
        seen_arch.add(key)
        entries.append(
            {
                "leader_card": "",
                "rank": rank if rank > 0 else 1300 + len(entries) + 1,
                "archetype": name,
                "share_percent": float(share or 0.0),
                "sample_count": int(sample_count or 0),
            }
        )

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            arch = obj.get("archetype") or obj.get("deckName") or obj.get("name") or obj.get("title")
            rank_val = obj.get("rank") or obj.get("position") or obj.get("place") or 0
            share_val = obj.get("share_percent") or obj.get("share") or obj.get("percentage") or 0
            sample_val = obj.get("sample_count") or obj.get("sample") or obj.get("count") or 0
            try:
                rank_num = int(rank_val)
            except Exception:
                rank_num = 0
            try:
                share_num = float(str(share_val).replace("%", "").replace(",", "."))
            except Exception:
                share_num = 0.0
            try:
                sample_num = int(sample_val)
            except Exception:
                sample_num = 0
            if isinstance(arch, str) and (rank_num > 0 or share_num > 0 or sample_num > 0):
                _push(arch, rank_num, share_num, sample_num)
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    for script in soup.find_all("script"):
        content = script.string or script.get_text() or ""
        if not content:
            continue
        low = content.lower()
        if "archetype" not in low and "deck" not in low:
            continue
        if script.get("type", "").lower() in {"application/json", "application/ld+json"}:
            try:
                _walk(json.loads(content))
            except Exception:
                pass
        if "__next_data__" in low or "decks" in low:
            frag_pattern = re.compile(r"\{[^{}]{30,500}\}")
            for m in frag_pattern.finditer(content):
                frag = m.group(0)
                if "archetype" not in frag.lower() and "deck" not in frag.lower():
                    continue
                try:
                    _walk(json.loads(frag.replace("'", '"')))
                except Exception:
                    continue
        if len(entries) >= 240:
            return entries
    return entries


def parse_leader_ranking_dom(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """
    DOM-first parser for ranking-like pages where plain-text regex is unstable.
    """
    entries: list[dict[str, Any]] = []
    seen_arch: set[str] = set()
    rank_re = re.compile(r"\b(\d{1,3})\b")
    share_re = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")

    row_selectors = [
        "tr",
        "li",
        "article",
        "div[class*='row']",
        "div[class*='item']",
        "div[class*='deck']",
    ]
    for selector in row_selectors:
        for node in soup.select(selector):
            text = " ".join(node.get_text(" ", strip=True).split())
            if not text:
                continue
            share_m = share_re.search(text)
            # ranking rows almost always contain share/sample marker.
            contains_deck_link = bool(node.select_one("a[href*='/decks/']"))
            if not share_m and "sample" not in text.lower() and not contains_deck_link:
                continue

            archetype = ""
            for a in node.find_all("a", href=True):
                href = a.get("href", "").strip()
                label = " ".join(a.get_text(" ", strip=True).split()).strip(" -|")
                if not label or not is_valid_archetype(label):
                    continue
                if "/decks/" in href:
                    archetype = label
                    break
                if not archetype:
                    archetype = label
            if not archetype:
                text_clean = share_re.sub("", text)
                text_clean = re.sub(r"\b\d+\b", " ", text_clean)
                text_clean = " ".join(text_clean.split()).strip(" -|")
                if is_valid_archetype(text_clean):
                    archetype = text_clean
            if not archetype:
                continue

            rank = 0
            rank_m = re.match(r"^\s*(\d{1,3})[.)]?\s+", text)
            if rank_m:
                rank = int(rank_m.group(1))
            else:
                nums = [int(m.group(1)) for m in rank_re.finditer(text)]
                if nums:
                    rank = min(nums)
            if rank <= 0 or rank > 300:
                rank = 900 + len(entries) + 1

            key = archetype.lower()
            if key in seen_arch:
                continue
            seen_arch.add(key)
            entries.append(
                {
                    "leader_card": "",
                    "rank": rank,
                    "archetype": archetype,
                    "share_percent": float(share_m.group(1).replace(",", ".")) if share_m else 0.0,
                }
            )
            if len(entries) >= 120:
                return entries

    # Secondary pass: when ranking page is client-rendered/compressed,
    # keep archetype labels from visible decklist links as low-confidence fallback.
    if len(entries) < 40:
        rank_base = 1200 + len(entries)
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if "/decks/list/" not in href and "/decks/" not in href:
                continue
            label = " ".join(a.get_text(" ", strip=True).split()).strip(" -|")
            if not is_valid_archetype(label):
                continue
            key = label.lower()
            if key in seen_arch:
                continue
            seen_arch.add(key)
            rank_base += 1
            entries.append(
                {
                    "leader_card": "",
                    "rank": rank_base,
                    "archetype": label,
                    "share_percent": 0.0,
                    "sample_count": 1,
                }
            )
            if len(entries) >= 120:
                break
    return entries


def parse_leader_ranking_script_data(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """
    Parse ranking candidates from embedded JSON/script payloads.
    Useful when visible DOM rows are sparse.
    """
    entries: list[dict[str, Any]] = []
    seen_arch: set[str] = set()

    def _push(archetype: str, rank: int, share: float = 0.0, sample_count: int = 0) -> None:
        name = " ".join(str(archetype or "").split()).strip(" -|")
        if not is_valid_archetype(name):
            return
        key = name.lower()
        if key in seen_arch:
            return
        seen_arch.add(key)
        entries.append(
            {
                "leader_card": "",
                "rank": rank if rank > 0 else 1500 + len(entries) + 1,
                "archetype": name,
                "share_percent": float(share or 0.0),
                "sample_count": int(sample_count or 0),
            }
        )

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            # Candidate archetype fields found in modern frontend payloads.
            arch = (
                obj.get("archetype")
                or obj.get("deckName")
                or obj.get("name")
                or obj.get("title")
            )
            rank_val = obj.get("rank") or obj.get("position") or obj.get("place") or 0
            share_val = obj.get("share_percent") or obj.get("share") or obj.get("percentage") or 0
            sample_val = obj.get("sample_count") or obj.get("sample") or obj.get("count") or 0
            try:
                rank_num = int(rank_val)
            except Exception:
                rank_num = 0
            try:
                share_num = float(str(share_val).replace("%", "").replace(",", "."))
            except Exception:
                share_num = 0.0
            try:
                sample_num = int(sample_val)
            except Exception:
                sample_num = 0

            if isinstance(arch, str) and (
                rank_num > 0 or share_num > 0 or sample_num > 0 or "deck" in str(obj).lower()
            ):
                _push(arch, rank_num, share_num, sample_num)

            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    for script in soup.find_all("script"):
        content = script.string or script.get_text() or ""
        if not content:
            continue
        low = content.lower()
        if "archetype" not in low and "leader" not in low and "deck" not in low:
            continue

        parsed_any = False
        # 1) Direct JSON script blocks.
        if script.get("type", "").lower() in {"application/json", "application/ld+json"}:
            try:
                obj = json.loads(content)
                _walk(obj)
                parsed_any = True
            except Exception:
                pass

        # 2) Heuristic object fragments inside JS.
        if not parsed_any:
            frag_pattern = re.compile(r"\{[^{}]{20,400}\}")
            for m in frag_pattern.finditer(content):
                frag = m.group(0)
                if "archetype" not in frag.lower() and "deck" not in frag.lower():
                    continue
                try:
                    js_like = frag.replace("'", '"')
                    obj = json.loads(js_like)
                except Exception:
                    continue
                _walk(obj)
                if len(entries) >= 180:
                    return entries
        if len(entries) >= 180:
            return entries

    return entries


def parse_archetype_name_from_page(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag_name in ("h1", "title"):
        tag = soup.find(tag_name)
        if not tag:
            continue
        text = " ".join(tag.get_text(" ", strip=True).split())
        text = re.sub(r"\s*[-|–].*$", "", text).strip()
        text = re.sub(r"^\d+\.\s*", "", text).strip()
        if is_valid_archetype(text):
            return text

    page_text = soup.get_text(" ", strip=True)
    m = re.search(r"\d+\.\s+(.+?)\s+\d+(?:[.,]\d+)?%", page_text)
    if m:
        guess = " ".join(m.group(1).split()).strip()
        if is_valid_archetype(guess):
            return guess
    return ""


def crawl_archetype_pages(
    archetype_links: list[str], max_pages: int = MAX_ARCHETYPE_PAGES
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for idx, url in enumerate(archetype_links[:max_pages], start=1):
        try:
            resp = requests.get(
                url,
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 OPCG-MetaBot/1.0"},
            )
            resp.raise_for_status()
        except requests.RequestException:
            continue

        archetype = parse_archetype_name_from_page(resp.text)
        if not archetype:
            continue

        entries.append(
            {
                "leader_card": "",
                "rank": 2000 + idx,
                "archetype": archetype,
                "share_percent": 0.0,
                "sample_count": 0,
            }
        )
    return entries


def crawl_decks_listings(seed_links: list[str], max_pages: int = MAX_LISTING_PAGES) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    queue = list(seed_links)
    seen_arch: set[str] = set()
    rank_cursor = 2500

    while queue and len(seen_urls) < max_pages:
        url = queue.pop(0)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        try:
            resp = requests.get(
                url,
                timeout=25,
                headers={"User-Agent": "Mozilla/5.0 OPCG-MetaBot/1.0"},
            )
            resp.raise_for_status()
        except requests.RequestException:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = soup.get_text(" ", strip=True)
        parsed = parse_decks_listing_entries(page_text)
        if parsed:
            for row in parsed:
                arch = str(row.get("archetype") or "").strip()
                key = arch.lower()
                if not arch or key in seen_arch:
                    continue
                seen_arch.add(key)
                collected.append(row)
        else:
            # Fallback when page is heavily client-rendered:
            # script/json payload first, then visible links/slug fallback.
            script_rows = parse_decks_listing_script_data(soup)
            if script_rows:
                for row in script_rows:
                    arch = str(row.get("archetype") or "").strip()
                    key = arch.lower()
                    if not arch or key in seen_arch:
                        continue
                    seen_arch.add(key)
                    collected.append(row)
            else:
                link_rows = parse_decks_listing_from_links(soup)
                if link_rows:
                    for row in link_rows:
                        arch = str(row.get("archetype") or "").strip()
                        key = arch.lower()
                        if not arch or key in seen_arch:
                            continue
                        seen_arch.add(key)
                        collected.append(row)
                else:
                    # Last fallback: infer archetype from the current listing URL itself.
                    guessed = _guess_archetype_from_deck_href(url)
                    if is_valid_archetype(guessed):
                        gk = guessed.lower()
                        if gk not in seen_arch:
                            seen_arch.add(gk)
                            rank_cursor += 1
                            collected.append(
                                {
                                    "leader_card": "",
                                    "rank": rank_cursor,
                                    "archetype": guessed,
                                    "share_percent": 0.0,
                                    "sample_count": 1,
                                }
                            )

        # Enqueue additional deck listing pages discovered from this page.
        for link in extract_decks_listing_links(soup):
            if link not in seen_urls and link not in queue:
                queue.append(link)

    return collected


def merge_top_decks(primary: list[dict[str, Any]], extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for item in primary + extra:
        archetype = str(item.get("archetype") or "").strip()
        rank = int(item.get("rank") or 0)
        if not archetype or rank <= 0:
            continue
        if not is_valid_archetype(archetype):
            continue
        sample = int(item.get("sample_count") or 0)
        key = (archetype.lower(), rank, sample)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    # Prioritize lower rank then higher share/sample count.
    merged.sort(
        key=lambda x: (
            int(x.get("rank") or 9999),
            -(float(x.get("share_percent") or 0.0)),
            -(int(x.get("sample_count") or 0)),
        )
    )
    return merged[:1200]


def build_context(top_decks: list[dict[str, Any]], tournaments: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("Limitless OP TCG Meta Snapshot")
    lines.append("Top Decks:")
    for deck in top_decks[:10]:
        lines.append(
            f"- #{deck['rank']} {deck['archetype']} ({deck['leader_card']}, {deck['share_percent']}%)"
        )
    lines.append("Recent Tournaments:")
    for tour in tournaments[:20]:
        lines.append(
            f"- {tour['name']} | {tour['date_text']} | {tour['players']} players | {tour['region_format']}"
        )
    return "\n".join(lines)


def is_valid_archetype(name: str) -> bool:
    clean = " ".join(name.split()).strip()
    if len(clean) < 3:
        return False
    # Must contain letters (Latin/CJK), not mostly numeric artifacts.
    if not re.search(r"[A-Za-z\u4e00-\u9fff]", clean):
        return False
    # Reject common malformed fragments from compressed percentages/ranks.
    if re.search(r"^\d", clean):
        return False
    if re.search(r"\d+%|\b\d+\b.*\b\d+\b", clean):
        # allow archetypes with a single number if needed, but reject noisy numeric chunks.
        if len(re.findall(r"\d", clean)) > 2:
            return False
    return True


def extract_tournament_links(soup: BeautifulSoup) -> list[str]:
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        if "/tournaments/" not in href:
            continue
        full = urljoin(SOURCE_URL, href)
        links.append(full)
    # Deduplicate while keeping order.
    seen: set[str] = set()
    deduped: list[str] = []
    for link in links:
        if link not in seen:
            seen.add(link)
            deduped.append(link)
    return deduped


def discover_tournament_links(soup: BeautifulSoup, max_pages: int = MAX_TOURNAMENT_PAGES) -> list[str]:
    """
    Discover tournament detail links by crawling both:
    - direct tournament detail links (/tournaments/<id>)
    - tournament listing pages (/tournaments, /tournaments?page=...)
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 OPCG-MetaBot/1.0"})

    detail_links: list[str] = []
    seen_details: set[str] = set()
    seen_listing_pages: set[str] = set()
    queue: list[str] = []

    def _push_detail(url: str) -> None:
        if re.search(r"/tournaments/\d+", url) and url not in seen_details:
            seen_details.add(url)
            detail_links.append(url)

    # Seed from homepage.
    for link in extract_tournament_links(soup):
        _push_detail(link)
    # Proactively seed tournament listing pagination to avoid relying on visible pagination links only.
    for p in range(1, max(2, min(max_pages, 300)) + 1):
        list_url = f"{SOURCE_URL.rstrip('/')}/tournaments?page={p}"
        if list_url not in seen_listing_pages and list_url not in queue:
            queue.append(list_url)
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        full = urljoin(SOURCE_URL, href)
        low = full.lower()
        if "/tournaments" in low and not re.search(r"/tournaments/\d+", low):
            if full not in seen_listing_pages and full not in queue:
                queue.append(full)

    # Crawl listing pages and collect detail links.
    crawled = 0
    while queue and crawled < max_pages:
        url = queue.pop(0)
        if url in seen_listing_pages:
            continue
        seen_listing_pages.add(url)
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException:
            continue
        crawled += 1
        page_soup = BeautifulSoup(resp.text, "html.parser")
        for link in extract_tournament_links(page_soup):
            _push_detail(link)
        for a in page_soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href:
                continue
            full = urljoin(SOURCE_URL, href)
            low = full.lower()
            if "/tournaments" in low and not re.search(r"/tournaments/\d+", low):
                if full not in seen_listing_pages and full not in queue:
                    queue.append(full)
    return detail_links


def extract_decklist_links(soup: BeautifulSoup) -> list[str]:
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        if not re.search(r"/decks/list/\d+", href):
            continue
        links.append(urljoin(SOURCE_URL, href))
    seen: set[str] = set()
    deduped: list[str] = []
    for link in links:
        if link not in seen:
            seen.add(link)
            deduped.append(link)
    return deduped


def parse_players_from_page_text(text: str) -> int:
    normalized = re.sub(r"\s+", " ", str(text or ""))
    nums = []
    for m in re.finditer(r"(\d{2,5})\s+Players", normalized, flags=re.IGNORECASE):
        try:
            nums.append(int(m.group(1)))
        except ValueError:
            continue
    return max(nums) if nums else 0


def normalize_card_code(raw: str) -> str:
    code = raw.upper().replace(" ", "").replace("－", "-")
    m = re.match(r"^(OP|ST|EB|PRB|P)(\d{2})-?(\d{3})(?:[_-]?([A-Z0-9]+))?$", code)
    if not m:
        return code
    prefix, series, card_no, suffix = m.groups()
    normalized = f"{prefix}{series}-{card_no}"
    if suffix:
        normalized = f"{normalized}_{suffix}"
    return normalized


def extract_card_ids(text: str) -> list[str]:
    # Match common One Piece card IDs, with optional suffixes like _p1/_r1.
    pattern = re.compile(
        r"\b(?:OP|ST|EB|P|PRB)\s?\d{2}[- ]?\d{3}(?:[_-]?[A-Za-z0-9]+)?\b",
        re.IGNORECASE,
    )
    ids = [normalize_card_code(m.group(0)) for m in pattern.finditer(text)]
    # Deduplicate, keep order.
    seen: set[str] = set()
    deduped: list[str] = []
    for card_id in ids:
        if card_id not in seen:
            seen.add(card_id)
            deduped.append(card_id)
    return deduped


def extract_card_count_mentions(text: str) -> list[tuple[str, int]]:
    mentions: list[tuple[str, int]] = []
    patterns = [
        re.compile(
            r"\b([1-4])\s*[xX]?\s*((?:OP|ST|EB|P|PRB)\s?\d{2}[- ]?\d{3}(?:[_-]?[A-Za-z0-9]+)?)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b((?:OP|ST|EB|P|PRB)\s?\d{2}[- ]?\d{3}(?:[_-]?[A-Za-z0-9]+)?)\s*[xX]?\s*([1-4])\b",
            re.IGNORECASE,
        ),
    ]
    for pattern in patterns:
        for m in pattern.finditer(text):
            if pattern is patterns[0]:
                count = int(m.group(1))
                card_id = normalize_card_code(m.group(2))
            else:
                card_id = normalize_card_code(m.group(1))
                count = int(m.group(2))
            mentions.append((card_id, count))
    return mentions


def parse_decklist_card_counts(soup: BeautifulSoup) -> list[tuple[str, int]]:
    """
    Prefer structured extraction from decklist DOM:
    - capture card id and count on the same local block/row
    - fallback to line-based parsing only when structured info is unavailable
    """
    out: list[tuple[str, int]] = []

    def _add(card_id_raw: str, count_raw: Any) -> None:
        cid = normalize_card_code(str(card_id_raw or "").strip())
        if not cid:
            return
        try:
            cnt = int(str(count_raw).strip())
        except (TypeError, ValueError):
            return
        if cnt < 1 or cnt > 4:
            return
        out.append((cid, cnt))

    # Path 1: scan likely row/container blocks.
    row_selectors = [
        "[class*='deck'] [class*='card']",
        "[class*='list'] [class*='card']",
        "[class*='decklist'] [class*='row']",
        "[class*='decklist'] li",
        "tr",
    ]
    id_re = re.compile(
        r"\b((?:OP|ST|EB|P|PRB)\s?\d{2}[- ]?\d{3}(?:[_-]?[A-Za-z0-9]+)?)\b",
        re.IGNORECASE,
    )
    count_re = re.compile(r"\b([1-4])\b")
    for sel in row_selectors:
        for node in soup.select(sel):
            text = " ".join(node.get_text(" ", strip=True).split())
            if not text:
                continue
            m_id = id_re.search(text)
            if not m_id:
                continue
            # Pick nearest legal count in same block.
            counts = [int(x) for x in count_re.findall(text)]
            if not counts:
                continue
            _add(m_id.group(1), counts[0])

    if out:
        # Deduplicate by card id, keep highest count seen in structured blocks.
        merged: dict[str, int] = {}
        for cid, cnt in out:
            merged[cid] = max(cnt, merged.get(cid, 0))
        return sorted(merged.items(), key=lambda x: x[0])

    # Path 2: line-based fallback from full text.
    text_all = soup.get_text("\n", strip=True)
    for cid, cnt in extract_card_count_mentions(text_all):
        _add(cid, cnt)
    if out:
        merged: dict[str, int] = {}
        for cid, cnt in out:
            merged[cid] = max(cnt, merged.get(cid, 0))
        return sorted(merged.items(), key=lambda x: x[0])
    return []


def build_tournament_archetype_ranking(
    tournament_links: list[str],
    max_pages: int = MAX_TOURNAMENT_PAGES,
    max_archetype_fetch: int = MAX_ARCHETYPE_FETCH,
) -> list[dict[str, Any]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 OPCG-MetaBot/1.0"})

    archetype_link_counter: Counter[str] = Counter()
    visited_tournaments = 0

    for link in tournament_links[:max_pages]:
        try:
            resp = session.get(link, timeout=20)
            resp.raise_for_status()
        except requests.RequestException:
            continue

        visited_tournaments += 1
        soup = BeautifulSoup(resp.text, "html.parser")
        for archetype_link in extract_archetype_links(soup):
            archetype_link_counter[archetype_link] += 1

    if not archetype_link_counter:
        return []

    ranking_entries: list[dict[str, Any]] = []
    for idx, (archetype_link, count) in enumerate(
        archetype_link_counter.most_common(max_archetype_fetch), start=1
    ):
        try:
            resp = session.get(archetype_link, timeout=20)
            resp.raise_for_status()
        except requests.RequestException:
            continue

        archetype = parse_archetype_name_from_page(resp.text)
        if not archetype:
            continue

        ranking_entries.append(
            {
                "leader_card": "",
                # Keep rank space separate from homepage ranks.
                "rank": 50 + idx,
                "archetype": archetype,
                "share_percent": 0.0,
                "sample_count": count,
                "from_tournaments": visited_tournaments,
            }
        )

    return ranking_entries


def build_card_cooccurrence(
    tournament_links: list[str], seed_decklist_links: list[str], max_pages: int = 30
) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 OPCG-MetaBot/1.0"})

    pair_counter: Counter[tuple[str, str]] = Counter()
    card_counter: Counter[str] = Counter()
    weighted_card_counter: defaultdict[str, float] = defaultdict(float)
    card_count_counter: dict[str, Counter[int]] = defaultdict(Counter)
    crawled_pages = 0
    decklist_links: set[str] = set(seed_decklist_links)
    decklist_weight: dict[str, float] = {link: 1.0 for link in seed_decklist_links}

    for link in tournament_links[:max_pages]:
        try:
            resp = session.get(link, timeout=20)
            resp.raise_for_status()
        except requests.RequestException:
            continue

        crawled_pages += 1
        soup = BeautifulSoup(resp.text, "html.parser")
        players = parse_players_from_page_text(resp.text)
        # tournament size weight: small events keep 1.0, larger events higher weight
        weight = max(1.0, min(6.0, players / 256.0)) if players > 0 else 1.0
        for dl in extract_decklist_links(soup):
            decklist_links.add(dl)
            prev = decklist_weight.get(dl, 0.0)
            if weight > prev:
                decklist_weight[dl] = weight

    decklists_crawled = 0
    for link in sorted(decklist_links)[:MAX_DECKLIST_PAGES]:
        try:
            resp = session.get(link, timeout=20)
            resp.raise_for_status()
        except requests.RequestException:
            continue

        decklists_crawled += 1
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        parsed_counts = parse_decklist_card_counts(soup)
        if parsed_counts:
            card_ids = [cid for cid, _ in parsed_counts]
        else:
            card_ids = extract_card_ids(text)
        page_weight = float(decklist_weight.get(link, 1.0))
        if parsed_counts:
            for card_id, count in parsed_counts:
                card_count_counter[card_id][count] += 1
        else:
            for card_id, count in extract_card_count_mentions(text):
                card_count_counter[card_id][count] += 1
        if len(card_ids) < 2:
            continue

        # Keep page contribution bounded.
        card_ids = card_ids[:120]
        for cid in card_ids:
            card_counter[cid] += 1
            weighted_card_counter[cid] += page_weight
        for a, b in combinations(sorted(card_ids), 2):
            pair_counter[(a, b)] += 1

    related: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (a, b), count in pair_counter.items():
        related[a].append({"card_id": b, "cooccur": count})
        related[b].append({"card_id": a, "cooccur": count})

    # Sort and keep top related cards per card.
    related_top: dict[str, list[dict[str, Any]]] = {}
    for card_id, items in related.items():
        sorted_items = sorted(items, key=lambda x: x["cooccur"], reverse=True)
        related_top[card_id] = sorted_items[:20]

    card_count_stats: dict[str, dict[str, Any]] = {}
    for card_id, counter in card_count_counter.items():
        total_mentions = sum(counter.values())
        if total_mentions <= 0:
            continue
        most_common_count, freq = counter.most_common(1)[0]
        weighted_avg = sum(k * v for k, v in counter.items()) / total_mentions
        weighted_mentions = float(weighted_card_counter.get(card_id, float(total_mentions)))
        card_count_stats[card_id] = {
            "most_common_count": most_common_count,
            "most_common_ratio": round(freq / total_mentions, 3),
            "avg_count": round(weighted_avg, 2),
            "mentions": total_mentions,
            "mentions_weighted": round(weighted_mentions, 2),
            "distribution": {str(k): v for k, v in sorted(counter.items())},
        }

    return {
        "source": SOURCE_URL,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "crawled_tournament_pages": crawled_pages,
        "decklist_links_collected": len(decklist_links),
        "crawled_decklist_pages": decklists_crawled,
        "tracked_cards": len(card_counter),
        "related_cards": related_top,
        "card_count_stats": card_count_stats,
    }


def sync_limitless_data() -> dict[str, Any]:
    prev_payload = _load_previous_payload()
    try:
        soup, page_text = fetch_best_page_snapshot(SOURCE_URL, rounds=FETCH_STABILITY_ROUNDS)
    except requests.RequestException:
        # Reuse previous payload instead of hard failure when remote endpoint is flaky.
        if prev_payload:
            prev_payload["fetched_at_utc"] = datetime.now(timezone.utc).isoformat()
            prev_payload["sync_warning"] = "live_fetch_failed_reused_previous_payload"
            META_DIR.mkdir(parents=True, exist_ok=True)
            OUTPUT_FILE.write_text(
                json.dumps(prev_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return prev_payload
        raise

    top_decks = parse_top_decks(page_text)
    leader_ranking_url = extract_complete_leader_ranking_link(soup)
    archetype_links = extract_archetype_links(soup)
    ranking_decks: list[dict[str, Any]] = []
    ranking_parse_source = "none"
    if leader_ranking_url:
        try:
            ranking_soup, ranking_text = fetch_best_page_snapshot(
                leader_ranking_url, rounds=max(2, FETCH_STABILITY_ROUNDS)
            )
            parsed_top = parse_top_decks(ranking_text)
            parsed_script = parse_leader_ranking_script_data(ranking_soup)
            parsed_dom = parse_leader_ranking_dom(ranking_soup)
            parsed_entries = parse_decks_listing_entries(ranking_text)
            parsed_links = parse_decks_listing_from_links(ranking_soup)

            candidates = [
                ("parse_top_decks", parsed_top),
                ("parse_leader_ranking_script_data", parsed_script),
                ("parse_leader_ranking_dom", parsed_dom),
                ("parse_decks_listing_entries", parsed_entries),
                ("parse_decks_listing_from_links", parsed_links),
            ]
            # Pick richest parser as primary, then merge with others for stability.
            best_name, best_rows = max(candidates, key=lambda x: len(x[1]))
            ranking_decks = list(best_rows)
            ranking_parse_source = best_name if best_rows else "none"
            for name, rows in candidates:
                if not rows or name == best_name:
                    continue
                ranking_decks = merge_top_decks(ranking_decks, rows)
            # Keep ranking-focused list compact but sufficiently rich.
            ranking_decks = ranking_decks[:200]
        except requests.RequestException:
            ranking_decks = []
            ranking_parse_source = "request_error"

    deck_listing_links = extract_decks_listing_links(soup)
    if leader_ranking_url and leader_ranking_url not in deck_listing_links:
        deck_listing_links.insert(0, leader_ranking_url)
    # Explicitly include /decks and /decks/list paginations.
    for u in build_decks_seed_links(MAX_LISTING_PAGES):
        if u not in deck_listing_links:
            deck_listing_links.append(u)
    deck_listing_links = expand_listing_pagination(deck_listing_links, MAX_LISTING_PAGES)
    listing_decks = crawl_decks_listings(deck_listing_links, max_pages=MAX_LISTING_PAGES)
    if not ranking_decks and listing_decks:
        ranking_decks = listing_decks[:80]
        ranking_parse_source = "fallback_from_listing_decks"
    archetype_page_decks = crawl_archetype_pages(
        archetype_links, max_pages=MAX_ARCHETYPE_PAGES
    )
    recent_tournaments = parse_recent_tournaments(page_text)
    tournament_links = discover_tournament_links(soup, max_pages=MAX_TOURNAMENT_PAGES)
    crawled_tournaments = crawl_recent_tournaments_details(tournament_links, max_items=40)
    if crawled_tournaments:
        merged_tours: list[dict[str, Any]] = []
        seen_tours: set[str] = set()
        for t in crawled_tournaments + recent_tournaments:
            name = str(t.get("name") or "").strip()
            if not name or name in seen_tours:
                continue
            seen_tours.add(name)
            merged_tours.append(t)
        recent_tournaments = merged_tours[:40]
    seed_decklist_links = extract_decklist_links(soup)

    # Expand seed decklists from listing and archetype pages to improve coverage.
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 OPCG-MetaBot/1.0"})
    for url in deck_listing_links[:MAX_LISTING_PAGES]:
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException:
            continue
        seed_decklist_links.extend(extract_decklist_links(BeautifulSoup(resp.text, "html.parser")))
    for url in archetype_links[:MAX_ARCHETYPE_PAGES]:
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException:
            continue
        seed_decklist_links.extend(extract_decklist_links(BeautifulSoup(resp.text, "html.parser")))
    # Dedup
    seed_decklist_links = list(dict.fromkeys(seed_decklist_links))
    tournament_ranking_decks = build_tournament_archetype_ranking(
        tournament_links,
        max_pages=MAX_TOURNAMENT_PAGES,
        max_archetype_fetch=MAX_ARCHETYPE_FETCH,
    )

    top_decks = merge_top_decks(
        top_decks,
        ranking_decks + listing_decks + archetype_page_decks + tournament_ranking_decks,
    )
    context = build_context(top_decks, recent_tournaments)
    cooccurrence = build_card_cooccurrence(
        tournament_links,
        seed_decklist_links,
        max_pages=min(MAX_TOURNAMENT_PAGES, 400),
    )

    payload = {
        "source": SOURCE_URL,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "top_decks": top_decks,
        "leader_ranking_source": leader_ranking_url,
        "leader_ranking_decks_count": len(ranking_decks),
        "leader_ranking_parse_source": ranking_parse_source,
        "max_listing_pages": MAX_LISTING_PAGES,
        "max_archetype_pages": MAX_ARCHETYPE_PAGES,
        "max_tournament_pages": MAX_TOURNAMENT_PAGES,
        "max_archetype_fetch": MAX_ARCHETYPE_FETCH,
        "max_decklist_pages": MAX_DECKLIST_PAGES,
        "deck_listing_links_sample": deck_listing_links[:20],
        "listing_decks_count": len(listing_decks),
        "listing_decks_sample": listing_decks[:20],
        "archetype_links_sample": archetype_links[:20],
        "archetype_page_decks_count": len(archetype_page_decks),
        "tournament_ranking_decks_count": len(tournament_ranking_decks),
        "recent_tournaments": recent_tournaments,
        "tournament_links_sample": tournament_links[:30],
        "tournament_links_discovered": len(tournament_links),
        "crawled_tournament_pages": cooccurrence.get("crawled_tournament_pages", 0),
        "decklist_links_seeded": len(seed_decklist_links),
        "context_for_ai": context,
    }

    META_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    COOCCURRENCE_FILE.write_text(
        json.dumps(cooccurrence, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    payload = sync_limitless_data()
    print(f"抓取完成：{payload['source']}")
    print(f"Top decks: {len(payload['top_decks'])}")
    print(f"Recent tournaments: {len(payload['recent_tournaments'])}")
    print(
        "Leader ranking decks: "
        f"{payload.get('leader_ranking_decks_count', 0)} "
        f"(source={payload.get('leader_ranking_parse_source', 'unknown')})"
    )
    print(f"Tournament links discovered: {payload.get('tournament_links_discovered', 0)}")
    print(f"输出文件：{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
