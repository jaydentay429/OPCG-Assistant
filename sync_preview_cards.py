#!/usr/bin/env python3
"""Ingest pre-release set cards (images + catalog) before official cardlist exists.

Sources, in order:
  1. preview/images/{CARD_ID}.png  (manual drops from Twitter / news)
  2. Japanese official product page promotional art
  3. Limitless card search (stats, EN text, og:image)

Only writes new rows or updates cards already marked preview=true.
Does not modify official catalog cards.

Usage:
  python sync_preview_cards.py --set OP17
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
INDEX_PATH = BASE_DIR / "index" / "cards_by_id.json"
PREVIEW_IDS_PATH = BASE_DIR / "index" / "preview_card_ids.json"
PACKS_DIR = BASE_DIR / "packs"
PREVIEW_IMAGES_DIR = BASE_DIR / "preview" / "images"
LIMITLESS_CDN_TMPL = "https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/one-piece/{set}/{stem}_EN.webp"

PRODUCT_PAGES = {
    "OP17": "https://www.onepiece-cardgame.com/products/boosters/op17/",
}
LIMITLESS_SET_PAGES = {
    "OP17": "https://onepiece.limitlesstcg.com/cards/op17-the-worlds-strongest-warriors",
}
SET_NAMES = {
    "OP17": "世界最強の戦士【OP-17】",
}

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 OPCG-PreviewSync/1.0",
    "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
    "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,image/*,*/*;q=0.8",
}

COLOR_EN_TO_ZH = {
    "RED": "紅",
    "GREEN": "綠",
    "BLUE": "藍",
    "PURPLE": "紫",
    "BLACK": "黑",
    "YELLOW": "黃",
}
RARITY_MAP = {
    "LEADER": "L",
    "L": "L",
    "COMMON": "C",
    "C": "C",
    "UNCOMMON": "UC",
    "UC": "UC",
    "RARE": "R",
    "R": "R",
    "SUPER RARE": "SR",
    "SR": "SR",
    "SECRET RARE": "SEC",
    "SEC": "SEC",
    "TREASURE RARE": "TR",
    "TR": "TR",
    "SPECIAL": "SP",
    "SP": "SP",
    "SP卡": "SP",
    "DON!!": "DON",
    "DON": "DON",
    "DON-P": "DON",
    "DON-SP": "Gold DON",
    "GOLD DON": "Gold DON",
}
TYPE_MAP = {
    "LEADER": "Leader",
    "CHARACTER": "Character",
    "EVENT": "Event",
    "STAGE": "Stage",
}

VALID_CARD_ID_RE = re.compile(r"^[A-Z]{2,4}\d{2}-\d{3}(?:-P\d+)?$")
SAFE_INT_RE = re.compile(r"-?\d+")


def normalize_card_id(raw: str) -> str:
    text = str(raw or "").strip().upper().replace("_", "-").replace(" ", "")
    text = text.replace("－", "-")
    text = re.sub(r"[^A-Z0-9-]", "", text)
    text = re.sub(r"-AA(\d*)$", lambda m: f"-P{m.group(1) or '1'}", text)
    m = re.match(r"^([A-Z]{2,4})-?(\d{2})-(\d{3}(?:-[A-Z0-9]+)?)$", text)
    if m:
        text = f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    return text


def card_id_from_match(match: re.Match[str]) -> str:
    prefix, series, num, suffix = match.groups()
    raw = f"{prefix}{series}-{num}"
    if suffix:
        raw = f"{raw}-{suffix}"
    return normalize_card_id(raw)


def safe_int(raw: Any) -> int | None:
    text = str(raw or "").strip().replace(",", "")
    if not text or text in {"-", "—", "－"}:
        return None
    m = SAFE_INT_RE.search(text.replace("+", ""))
    if not m:
        return None
    try:
        return int(m.group(0))
    except ValueError:
        return None


def is_official_card(card: Any) -> bool:
    if not isinstance(card, dict):
        return False
    if card.get("preview"):
        return False
    return bool(str(card.get("name") or "").strip() or str(card.get("effect") or "").strip())


def limitless_cdn_candidates(card_id: str) -> list[str]:
    m = re.match(r"^([A-Z]{2,4})(\d{2})-(\d{3})(?:-P(\d+))?$", card_id)
    if not m:
        return []
    set_code = f"{m.group(1)}{m.group(2)}"
    base = f"{set_code}-{m.group(3)}"
    stems = [base]
    if m.group(4):
        stems = [f"{base}_p{m.group(4)}", f"{base}_P{m.group(4)}", f"{base}-P{m.group(4)}"]
    out = []
    for stem in stems:
        out.append(LIMITLESS_CDN_TMPL.format(set=set_code, stem=stem))
    return out


def pack_has_image(card_id: str) -> bool:
    return any(PACKS_DIR.glob(f"{card_id}.*"))
    return any(PACKS_DIR.glob(f"{card_id}.*"))


def download_image(card_id: str, url: str, session: requests.Session, *, overwrite: bool) -> bool:
    if not url or not card_id:
        return False
    if pack_has_image(card_id) and not overwrite:
        return False
    try:
        resp = session.get(url, timeout=20, headers=REQUEST_HEADERS)
    except requests.RequestException:
        return False
    ctype = (resp.headers.get("content-type") or "").lower()
    if resp.status_code != 200 or ("image" not in ctype and len(resp.content) < 2000):
        return False
    if len(resp.content) < 800:
        return False
    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    target = PACKS_DIR / f"{card_id}.png"
    try:
        target.write_bytes(resp.content)
        return True
    except OSError:
        return False


def copy_local_drops(set_code: str) -> list[str]:
    copied: list[str] = []
    if not PREVIEW_IMAGES_DIR.is_dir():
        return copied
    prefix = set_code.upper()
    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    for src in sorted(PREVIEW_IMAGES_DIR.iterdir()):
        if not src.is_file() or src.name.startswith("."):
            continue
        cid = normalize_card_id(src.stem)
        if not cid.startswith(prefix):
            continue
        dest_png = PACKS_DIR / f"{cid}.png"
        if dest_png.exists():
            continue
        try:
            shutil.copy2(src, dest_png)
            copied.append(cid)
            print(f"[drop] {src.name} -> packs/{dest_png.name}", flush=True)
        except OSError as exc:
            print(f"[drop] skip {src.name}: {exc}", flush=True)
    return copied


def scrape_product_page(set_code: str, session: requests.Session) -> dict[str, str]:
    url = PRODUCT_PAGES.get(set_code.upper(), "")
    out: dict[str, str] = {}
    if not url:
        print(f"[product] no product page mapped for {set_code}")
        return out
    print(f"[product] {url}", flush=True)
    try:
        resp = session.get(url, timeout=25, headers=REQUEST_HEADERS)
    except requests.RequestException as exc:
        print(f"[product] error={exc}")
        return out
    if resp.status_code != 200 or not resp.text.strip():
        print(f"[product] status={resp.status_code}")
        return out
    host = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    prefix = set_code.upper()
    # Official product pages use /images/cards/OP17-079.webp (skip thumbs).
    for rel in re.findall(
        r"""(?:src|data-src|data-original)\s*=\s*['"]([^'"]*images/cards/[^'"]+)['"]""",
        resp.text,
        flags=re.I,
    ):
        if "/thumb/" in rel.lower():
            continue
        fname = Path(rel.split("?", 1)[0]).stem
        cid = normalize_card_id(fname)
        if not cid.startswith(prefix):
            continue
        abs_url = rel if rel.startswith("http") else f"{host}/{rel.lstrip('/')}"
        # Prefer full-size over later duplicates.
        out.setdefault(cid, abs_url)
    print(f"[product] image ids={len(out)}", flush=True)
    return out


def _limitless_search_ids(set_code: str, session: requests.Session) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    prefix = set_code.upper()

    def add_cid(raw: str) -> None:
        cid = normalize_card_id(raw)
        if not re.match(r"^[A-Z]{2,4}\d{2}-\d{3}(?:-P\d+)?$", cid):
            return
        if cid.startswith(prefix) and cid not in seen:
            seen.add(cid)
            ids.append(cid)

    set_url = LIMITLESS_SET_PAGES.get(prefix)
    if set_url:
        try:
            resp = session.get(set_url, timeout=25, headers=REQUEST_HEADERS)
            if resp.status_code == 200:
                for href in re.findall(r"""href=["'](/cards/[^"'?#]+)""", resp.text, flags=re.I):
                    slug = href.split("/cards/", 1)[-1].strip("/")
                    add_cid(slug.split("/")[0])
                print(f"[limitless] set page ids={len(ids)}", flush=True)
        except requests.RequestException as exc:
            print(f"[limitless] set page error={exc}")

    url = f"{LIMITLESS_BASE}cards?q=set%3A{prefix}&show=all&language=English"
    try:
        resp = session.get(url, timeout=30, headers=REQUEST_HEADERS)
    except requests.RequestException as exc:
        print(f"[limitless] list error {exc}")
        return ids
    if resp.status_code != 200:
        return ids
    for href in re.findall(r"""href=["'](/cards/[^"']+)["']""", resp.text, flags=re.I):
        path, _, query = href.partition("?")
        slug = path.split("/cards/", 1)[-1].strip("/")
        raw = slug.split("/")[0]
        v_m = re.search(r"(?:^|&)v=(\d+)", query)
        if v_m:
            raw = f"{raw}-P{v_m.group(1)}"
        add_cid(raw)
    print(f"[limitless] unique ids={len(ids)}", flush=True)
    return ids


def _split_traits(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    parts = re.split(r"[\/／,，|]+", text)
    return [p.strip() for p in parts if p.strip()]


def parse_limitless_card_html(html: str, card_id: str) -> dict[str, Any] | None:
    soup = BeautifulSoup(html, "html.parser")
    name_el = soup.select_one(".card-text-name")
    type_el = soup.select_one(".card-text-type")
    sections = [el.get_text(" ", strip=True) for el in soup.select(".card-text-section")]
    name = name_el.get_text(" ", strip=True) if name_el else ""
    type_line = type_el.get_text(" ", strip=True) if type_el else ""

    card_type = ""
    for key, mapped in TYPE_MAP.items():
        if re.search(rf"\b{key}\b", type_line or html, flags=re.I):
            card_type = mapped
            break

    colors_en: list[str] = []
    for en in ("Red", "Green", "Blue", "Purple", "Black", "Yellow"):
        if re.search(rf"\b{en}\b", type_line):
            colors_en.append(en)

    life_m = re.search(r"(\d+)\s*Life", type_line or "", flags=re.I)
    cost_m = re.search(r"(\d+)\s*Cost", type_line or "", flags=re.I)
    life = int(life_m.group(1)) if life_m else None
    cost = int(cost_m.group(1)) if cost_m else None

    power = None
    counter = None
    attributes_en: list[str] = []
    effect_en = ""
    traits_en: list[str] = []
    rarity = ""

    for section in sections:
        if name and card_id and name in section and card_id in section:
            continue
        if " • " in section and card_id in section:
            continue
        if re.match(r"\d+\s*Power\b", section, flags=re.I):
            pm = re.search(r"(\d+)\s*Power", section, flags=re.I)
            if pm:
                power = int(pm.group(1))
            cm = re.search(r"\+(\d+)\s*Counter", section, flags=re.I)
            if cm:
                counter = int(cm.group(1))
            for attr in ("Slash", "Strike", "Ranged", "Special", "Wisdom"):
                if re.search(rf"\b{attr}\b", section):
                    attributes_en.append(attr)
            continue
        if section.lower().startswith("illustrated"):
            continue
        if section.startswith("[") or re.match(
            r"^(?:Activate:|On Play|When Attacking|On Block|On K\.?O|Trigger|Counter|All of your|Your |If your)",
            section,
            flags=re.I,
        ):
            effect_en = (effect_en + " " + section).strip() if effect_en else section
            continue
        if "/" in section or "Pirates" in section or "Emperors" in section or "Giants" in section:
            if "Illustrated" not in section and len(section) < 160:
                traits_en = _split_traits(section)
                continue
        # Static abilities without a leading [timing] tag (e.g. Luffy OP17-079).
        if len(section) > 20 and not effect_en:
            effect_en = section

    prints = soup.select_one(".prints-current-details, .card-prints-current")
    if prints:
        ptxt = prints.get_text(" ", strip=True)
        for label, code in RARITY_MAP.items():
            if re.search(rf"\b{re.escape(label)}\b", ptxt, flags=re.I):
                rarity = code
                break

    img_url = ""
    meta = soup.find("meta", attrs={"property": "og:image"})
    if meta and meta.get("content"):
        img_url = str(meta.get("content")).strip()

    if not card_type:
        return None
    is_leader = card_type == "Leader"
    if is_leader and life is None:
        return None
    if not is_leader and cost is None:
        if power is None and not effect_en:
            return None
        cost = 0

    colors_zh = [COLOR_EN_TO_ZH[c.upper()] for c in colors_en if c.upper() in COLOR_EN_TO_ZH]
    out: dict[str, Any] = {
        "card_id": card_id,
        "name_en": name,
        "name": name,
        "card_type": card_type,
        "category": card_type,
        "card_type_en": card_type,
        "category_en": card_type,
        "colors_en": colors_en,
        "colors": colors_zh or colors_en,
        "preview": True,
    }
    if life is not None:
        out["life"] = life
    if cost is not None and not is_leader:
        out["cost"] = cost
    if power is not None:
        out["power"] = power
    if counter is not None:
        out["counter"] = counter
    if rarity:
        out["rarity"] = rarity
    elif is_leader:
        out["rarity"] = "L"
    if attributes_en:
        out["attributes_en"] = attributes_en
    if traits_en:
        out["traits_en"] = traits_en
    if effect_en:
        out["effect_en"] = effect_en
        out["effect"] = effect_en
    if img_url:
        out["img_url"] = img_url
        out["img_full_url"] = img_url
    return out


def scrape_limitless_card(card_id: str, session: requests.Session) -> dict[str, Any] | None:
    base = re.sub(r"-P(\d+)$", "", card_id, flags=re.I)
    v_m = re.search(r"-P(\d+)$", card_id, flags=re.I)
    urls = []
    if v_m:
        urls.append(urljoin(LIMITLESS_BASE, f"cards/{base}?v={v_m.group(1)}"))
    urls.extend(
        [
            urljoin(LIMITLESS_BASE, f"cards/{card_id}"),
            urljoin(LIMITLESS_BASE, f"cards/{base}"),
        ]
    )
    for url in urls:
        try:
            resp = session.get(url, timeout=20, headers=REQUEST_HEADERS)
        except requests.RequestException:
            continue
        if resp.status_code != 200 or not resp.text.strip():
            continue
        parsed = parse_limitless_card_html(resp.text, card_id)
        if parsed:
            if v_m:
                parsed["card_id"] = card_id
            return parsed
    return None


def scrape_limitless(set_code: str, session: requests.Session, sleep_s: float) -> dict[str, dict[str, Any]]:
    ids = _limitless_search_ids(set_code, session)
    print(f"[limitless] unique ids={len(ids)}", flush=True)
    out: dict[str, dict[str, Any]] = {}
    for i, cid in enumerate(ids, 1):
        parsed = scrape_limitless_card(cid, session)
        if parsed:
            out[cid] = parsed
        else:
            print(f"[limitless] skip {cid} (no stats)", flush=True)
        if i % 20 == 0:
            print(f"[limitless] fetched {i}/{len(ids)} kept={len(out)}", flush=True)
        time.sleep(max(0.0, sleep_s))
    # Clone P-variants from base if the alt page had no extra stats.
    for cid in ids:
        if cid in out or "-P" not in cid:
            continue
        base = re.sub(r"-P\d+$", "", cid)
        if base not in out:
            continue
        cloned = dict(out[base])
        cloned["card_id"] = cid
        out[cid] = cloned
    print(f"[limitless] parsed cards={len(out)}", flush=True)
    return out


def merge_preview_card(existing: dict[str, Any] | None, incoming: dict[str, Any], set_name: str) -> dict[str, Any]:
    current = dict(existing) if isinstance(existing, dict) else {}
    if is_official_card(current):
        return current
    for key, value in incoming.items():
        if value in (None, "", [], {}):
            continue
        current[key] = value
    current["preview"] = True
    current["card_sets"] = [set_name]
    pack = re.search(r"[\[【]([A-Z]{2,4}-\d{2})[\]】]", set_name)
    if pack:
        current["pack_id"] = pack.group(1)
    current.setdefault("block_number", 5)
    if not current.get("traits") and current.get("traits_en"):
        current["traits"] = list(current["traits_en"])
    return current


def write_preview_ids(index: dict[str, Any], set_code: str) -> list[str]:
    prefix = set_code.upper()
    ids = sorted(
        cid
        for cid, card in index.items()
        if str(cid).upper().startswith(prefix) and isinstance(card, dict) and card.get("preview")
    )
    payload = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "set": prefix,
        "ids": ids,
    }
    PREVIEW_IDS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description="预览系列：本地图 + 商品页 + Limitless → index/packs")
    parser.add_argument("--set", default="OP17", help="系列代码，例如 OP17")
    parser.add_argument("--skip-limitless", action="store_true")
    parser.add_argument("--skip-product", action="store_true")
    parser.add_argument(
        "--images-only",
        action="store_true",
        help="只补缺图，不重新抓 Limitless 卡表",
    )
    parser.add_argument("--sleep", type=float, default=0.25)
    args = parser.parse_args()
    set_code = str(args.set).strip().upper()
    set_name = SET_NAMES.get(set_code, f"{set_code}")

    if not INDEX_PATH.exists():
        raise SystemExit(f"未找到索引文件: {INDEX_PATH}")
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    if not isinstance(index, dict):
        raise SystemExit("cards_by_id.json 格式错误")

    dropped_junk = 0
    for cid in list(index.keys()):
        if str(cid).upper().startswith(set_code) and not VALID_CARD_ID_RE.match(str(cid)):
            row = index.get(cid)
            if isinstance(row, dict) and row.get("preview"):
                index.pop(cid, None)
                dropped_junk += 1
    if dropped_junk:
        print(f"[cleanup] removed invalid preview ids={dropped_junk}", flush=True)

    session = requests.Session()
    session.trust_env = False

    dropped = copy_local_drops(set_code)
    for cid in dropped:
        current = index.get(cid)
        if is_official_card(current):
            continue
        stub = merge_preview_card(
            current if isinstance(current, dict) else None,
            {"card_id": cid, "name": cid, "name_en": cid, "preview": True},
            set_name,
        )
        index[cid] = stub

    product_images: dict[str, str] = {}
    if not args.skip_product:
        product_images = scrape_product_page(set_code, session)

    limitless: dict[str, dict[str, Any]] = {}
    if not args.skip_limitless and not args.images_only:
        limitless = scrape_limitless(set_code, session, args.sleep)

    added = 0
    updated = 0
    skipped_official = 0
    images_ok = 0

    all_ids = sorted(set(product_images) | set(limitless) | set(dropped))
    if args.images_only:
        all_ids = sorted(
            cid
            for cid, card in index.items()
            if str(cid).upper().startswith(set_code)
            and isinstance(card, dict)
            and card.get("preview")
            and VALID_CARD_ID_RE.match(str(cid))
        )
    for cid in all_ids:
        existing = index.get(cid)
        if is_official_card(existing):
            skipped_official += 1
            continue
        if args.images_only:
            merged = existing if isinstance(existing, dict) else {"card_id": cid, "preview": True}
        else:
            incoming = dict(limitless.get(cid) or {})
            incoming["card_id"] = cid
            was_new = cid not in index or not isinstance(existing, dict)
            merged = merge_preview_card(existing if isinstance(existing, dict) else None, incoming, set_name)
            if not merged.get("card_type") and cid not in product_images and cid not in dropped:
                continue
            index[cid] = merged
            if was_new:
                added += 1
            else:
                updated += 1

        img_candidates = []
        img_candidates.extend(limitless_cdn_candidates(cid))
        for key in ("img_full_url", "img_url"):
            raw_url = str((merged.get(key) or "")).strip()
            if raw_url:
                img_candidates.append(raw_url)
        if cid in product_images:
            img_candidates.append(product_images[cid])
        seen_urls: set[str] = set()
        for url in img_candidates:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            if download_image(cid, url, session, overwrite=not pack_has_image(cid)):
                images_ok += 1
                break

    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    preview_ids = write_preview_ids(index, set_code)
    print(f"新增卡: {added}")
    print(f"更新预览卡: {updated}")
    print(f"跳过正式卡: {skipped_official}")
    print(f"本地下载图: {images_ok}")
    print(f"本地 drop: {len(dropped)}")
    print(f"preview ids ({len(preview_ids)}): {PREVIEW_IDS_PATH}")
    print(f"index: {INDEX_PATH}")
    print(f"packs: {PACKS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
