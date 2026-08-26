#!/usr/bin/env python3
"""Ingest JP limited/promo parallels that never appear on the TC/EN booster cardlist.

Premium collections (e.g. Best Selection vol.6 OP15-075 异画) live in:
  550801 限定商品収録カード
  550901 プロモーションカード

This script adds missing variant ids to cards_by_id.json (cloned from the base
card's TC text) and force-refreshes pack images from the JP CDN.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
INDEX_PATH = BASE_DIR / "index" / "cards_by_id.json"
PACKS_DIR = BASE_DIR / "packs"
JP_CARDLIST_URL = "https://www.onepiece-cardgame.com/cardlist/"
JP_IMAGE_HOST = "https://www.onepiece-cardgame.com/"
DEFAULT_SERIES = ("550801", "550901")
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 OPCG-LimitedSync/1.0",
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
    "Referer": JP_CARDLIST_URL,
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}
CLONE_SKIP_KEYS = {"img_full_url", "img_url", "card_sets", "pack_id", "card_id"}


def normalize_card_id(raw: str) -> str:
    text = str(raw or "").strip().upper().replace("_", "-").replace(" ", "")
    text = text.replace("－", "-")
    text = re.sub(r"[^A-Z0-9-]", "", text)
    text = re.sub(
        r"^([A-Z]{2,4}-?\d{2}-\d{3})([A-Z][A-Z0-9]{0,4})$",
        r"\1-\2",
        text,
    )
    m = re.match(r"^([A-Z]{2,4})-?(\d{2})-(\d{3}(?:-[A-Z0-9]+)?)$", text)
    if m:
        text = f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    return text


def base_card_id(card_id: str) -> str:
    text = normalize_card_id(card_id)
    m = re.match(r"^([A-Z]{2,4}\d{2}-\d{3})", text)
    if m:
        return m.group(1)
    m = re.match(r"^(P-\d{3})", text)
    return m.group(1) if m else text


def jp_image_stem(card_id: str) -> str:
    cid = normalize_card_id(card_id)
    m = re.match(r"^(.+)-P(\d+)$", cid)
    if m:
        return f"{m.group(1)}_p{m.group(2)}"
    return cid


def to_jp_image_url(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        if "/images/" in text:
            return f"{JP_IMAGE_HOST}images/{text.split('/images/', 1)[1].lstrip('/')}"
        return text
    normalized = text.replace("../", "").replace("./", "").lstrip("/")
    return f"{JP_IMAGE_HOST}{normalized}"


def parse_limited_modals(html: str) -> dict[str, dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, dict[str, Any]] = {}
    for modal in soup.select("dl.modalCol[id]"):
        card_id = normalize_card_id(modal.get("id"))
        if not card_id:
            continue
        name_el = modal.select_one("dt .cardName")
        name = name_el.get_text(" ", strip=True) if name_el else ""
        info_spans = modal.select("dt .infoCol span")
        rarity = info_spans[1].get_text(strip=True) if len(info_spans) >= 3 else ""
        card_type = info_spans[2].get_text(strip=True) if len(info_spans) >= 3 else ""

        card_sets: list[str] = []
        back = modal.select_one("dd .backCol")
        if back:
            get_info = back.select_one(".getInfo")
            if get_info:
                for br in get_info.find_all("br"):
                    br.replace_with("\n")
                h3 = get_info.find("h3")
                label = h3.get_text(" ", strip=True) if h3 else ""
                text = get_info.get_text("\n", strip=True)
                if label and text.startswith(label):
                    text = text[len(label) :].strip()
                for raw in text.split("\n"):
                    line = raw.strip().lstrip("-•·").strip()
                    if line and line not in card_sets:
                        card_sets.append(line)

        images: list[str] = []
        for img in modal.select("img[data-src], img[src]"):
            src = str(img.get("data-src") or img.get("src") or "").strip()
            if "cardlist/card/" not in src.lower() or "dummy.gif" in src.lower():
                continue
            images.append(to_jp_image_url(src.split("?", 1)[0]))
        stem_url = f"{JP_IMAGE_HOST}images/cardlist/card/{jp_image_stem(card_id)}.png"
        images.append(stem_url)
        images = list(dict.fromkeys(x for x in images if x))

        out[card_id] = {
            "card_id": card_id,
            "name": name,
            "rarity": rarity,
            "card_type": card_type,
            "card_sets": card_sets,
            "images": images,
        }
    return out


def crawl_series(session: requests.Session, series_values: list[str]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for series in series_values:
        try:
            resp = session.post(
                JP_CARDLIST_URL,
                data={"search": "true", "series": series},
                headers=REQUEST_HEADERS,
                timeout=45,
            )
        except requests.RequestException as exc:
            print(f"[limited] series={series} error={exc}", flush=True)
            continue
        if resp.status_code != 200 or not resp.text.strip():
            print(f"[limited] series={series} status={resp.status_code}", flush=True)
            continue
        parsed = parse_limited_modals(resp.text)
        print(f"[limited] series={series} cards={len(parsed)}", flush=True)
        merged.update(parsed)
    return merged


def clone_variant_record(index: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    variant_id = variant["card_id"]
    base_id = base_card_id(variant_id)
    base = index.get(base_id) if isinstance(index.get(base_id), dict) else {}
    current = index.get(variant_id) if isinstance(index.get(variant_id), dict) else None
    if current is None:
        current = {
            key: value
            for key, value in (base or {}).items()
            if key not in CLONE_SKIP_KEYS
        }
    else:
        current = dict(current)
        if base:
            for key, value in base.items():
                if key in CLONE_SKIP_KEYS:
                    continue
                if key not in current or current.get(key) in (None, "", [], {}):
                    current[key] = value

    current["card_id"] = variant_id
    if variant.get("images"):
        current["img_full_url"] = variant["images"][0]
        current["img_url"] = f"images/cardlist/card/{jp_image_stem(variant_id)}.png"
    if variant.get("rarity") and not current.get("rarity"):
        current["rarity"] = variant["rarity"]
    if variant.get("card_type") and not current.get("card_type"):
        current["card_type"] = str(variant["card_type"]).title()
        current.setdefault("category", current["card_type"])
    if not current.get("name") and variant.get("name"):
        current["name"] = variant["name"]

    # Prefer TC base Chinese name over JP Latin/JP-only variant titles.
    base_name = str((base or {}).get("name") or "").strip()
    cur_name = str(current.get("name") or "").strip()
    base_has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in base_name)
    cur_has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in cur_name)
    if base_has_cjk and not cur_has_cjk:
        current["name"] = base_name
        for key in (
            "effect",
            "traits",
            "attributes",
            "colors",
            "category",
            "card_type",
            "name_en",
            "effect_en",
            "traits_en",
            "attributes_en",
            "category_en",
            "card_type_en",
            "colors_en",
        ):
            if key in base and base.get(key) not in (None, "", [], {}):
                if current.get(key) in (None, "", [], {}) or key == "name_en":
                    current[key] = base[key]

    sets = [str(x).strip() for x in (variant.get("card_sets") or []) if str(x).strip()]
    # Official getInfo is per illustration — do not union base booster onto variants.
    if sets:
        current["card_sets"] = sets
    return current


def download_image(card_id: str, urls: list[str], session: requests.Session, overwrite: bool) -> str:
    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(p for p in PACKS_DIR.glob(f"{card_id}.*") if p.is_file())
    for url in urls:
        try:
            resp = session.get(url, headers=REQUEST_HEADERS, timeout=25)
        except requests.RequestException:
            continue
        ctype = str(resp.headers.get("content-type") or "").lower()
        if resp.status_code != 200 or "image" not in ctype or len(resp.content) < 800:
            continue
        ext = ".png"
        lowered = url.split("?", 1)[0].lower()
        for candidate in (".png", ".jpg", ".jpeg", ".webp"):
            if lowered.endswith(candidate):
                ext = candidate
                break
        target = PACKS_DIR / f"{card_id}{ext}"
        if existing and not overwrite:
            same = any(p.read_bytes() == resp.content for p in existing)
            if same:
                return "skipped"
        if existing:
            for old in existing:
                if old.resolve() != target.resolve():
                    try:
                        old.unlink()
                    except OSError:
                        pass
        target.write_bytes(resp.content)
        return "downloaded" if not existing else "replaced"
    return "failed"


def main() -> None:
    parser = argparse.ArgumentParser(description="同步日文官网限定/宣传异画到索引和图库")
    parser.add_argument(
        "--series",
        default=",".join(DEFAULT_SERIES),
        help="JP cardlist series values, comma-separated",
    )
    parser.add_argument(
        "--no-overwrite-images",
        action="store_true",
        help="已有本地图时不覆盖（默认会用官网图覆盖错图）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只报告，不写索引/图片")
    args = parser.parse_args()

    if not INDEX_PATH.exists():
        raise SystemExit(f"未找到索引文件: {INDEX_PATH}")
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    if not isinstance(index, dict):
        raise SystemExit("cards_by_id.json 格式错误")

    series_values = [x.strip() for x in str(args.series).split(",") if x.strip()]
    session = requests.Session()
    session.trust_env = False
    variants = crawl_series(session, series_values)
    if not variants:
        raise SystemExit("未解析到限定/宣传异画")

    added = 0
    updated = 0
    downloaded = 0
    replaced = 0
    skipped = 0
    failed = 0
    overwrite = not args.no_overwrite_images

    for card_id, variant in sorted(variants.items()):
        existed = card_id in index
        record = clone_variant_record(index, variant)
        if not args.dry_run:
            index[card_id] = record
        if existed:
            updated += 1
        else:
            added += 1

        status = download_image(card_id, variant.get("images") or [], session, overwrite=overwrite)
        if args.dry_run:
            continue
        if status == "downloaded":
            downloaded += 1
        elif status == "replaced":
            replaced += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1
            print(f"[limited] image_fail {card_id}", flush=True)

    if not args.dry_run:
        INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"限定/宣传异画: {len(variants)}")
    print(f"索引新增: {added}")
    print(f"索引更新: {updated}")
    print(f"图片新下: {downloaded}")
    print(f"图片覆盖: {replaced}")
    print(f"图片跳过: {skipped}")
    print(f"图片失败: {failed}")
    print(f"索引总卡牌: {len(index)}")
    print(f"dry_run={bool(args.dry_run)} overwrite_images={overwrite}")


if __name__ == "__main__":
    main()
