from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
INDEX_PATH = BASE_DIR / "index" / "cards_by_id.json"
CARDS_DIR = BASE_DIR / "cards"
PACKS_DIR = BASE_DIR / "packs"
JP_CARDLIST_URL = "https://www.onepiece-cardgame.com/cardlist/"
JP_IMAGE_HOST = "https://www.onepiece-cardgame.com/"
LIMITLESS_BASE = "https://onepiece.limitlesstcg.com/"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 OPCG-ImageSync/1.0",
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
    "Referer": JP_CARDLIST_URL,
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def normalize_card_id(raw: str) -> str:
    text = str(raw or "").strip().upper().replace("_", "-").replace(" ", "")
    text = text.replace("－", "-")
    text = re.sub(r"[^A-Z0-9-]", "", text)
    m = re.match(r"^([A-Z]{2,4})-?(\d{2})-(\d{3}(?:-[A-Z0-9]+)?)$", text)
    if m:
        text = f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    return text


def jp_image_stems(card_id: str) -> list[str]:
    """Japanese official files use OP16-001.png / OP16-001_p1.png."""
    cid = normalize_card_id(card_id)
    if not cid:
        return []
    stems = [cid]
    m = re.match(r"^(.+)-([A-Z][A-Z0-9]{0,4})$", cid)
    if m and not re.match(r"^\d{3}$", m.group(2)):
        stems.append(f"{m.group(1)}_{m.group(2).lower()}")
    # Promo / compact forms already match cid.
    return list(dict.fromkeys(stems))


def guess_ext(url: str) -> str:
    lowered = url.split("?", 1)[0].lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        if lowered.endswith(ext):
            return ext
    return ".png"


def to_jp_image_url(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    text = text.replace("/cardlist/images/cardlist/", "/images/cardlist/")
    if text.startswith("http://") or text.startswith("https://"):
        if "/images/" in text:
            return f"{JP_IMAGE_HOST}images/{text.split('/images/', 1)[1].split('?', 1)[0]}"
        return text.split("?", 1)[0]
    normalized = text.replace("../", "").replace("./", "").lstrip("/")
    return f"{JP_IMAGE_HOST}{normalized.split('?', 1)[0]}"


# Chinese HK site: prefer Traditional Chinese plates, then JP; EN is last resort only.
OFFICIAL_IMAGE_MIRRORS_TC_FIRST = (
    "https://asia-tc.onepiece-cardgame.com/",
    JP_IMAGE_HOST,
    "https://asia-en.onepiece-cardgame.com/",
    "https://en.onepiece-cardgame.com/",
)
# Legacy alias kept for readability in logs/comments.
OFFICIAL_IMAGE_MIRRORS_JP_FIRST = OFFICIAL_IMAGE_MIRRORS_TC_FIRST
OFFICIAL_IMAGE_MIRRORS_EN_FIRST = OFFICIAL_IMAGE_MIRRORS_TC_FIRST


def official_image_mirrors_for(card_id: str) -> tuple[str, ...]:
    return OFFICIAL_IMAGE_MIRRORS_TC_FIRST


def official_candidates(card: dict) -> list[str]:
    out: list[str] = []
    cid = normalize_card_id(str(card.get("card_id") or card.get("id") or ""))
    mirrors = official_image_mirrors_for(cid)
    for stem in jp_image_stems(cid):
        for host in mirrors:
            out.append(f"{host}images/cardlist/card/{stem}.png")
    for key in ("img_full_url", "img_url"):
        raw = str(card.get(key) or "").strip()
        if not raw:
            continue
        # Keep index URLs as fallbacks after regional mirrors.
        out.append(to_jp_image_url(raw))
        if "?" in raw:
            out.append(to_jp_image_url(raw.split("?", 1)[0]))
    return dedupe([x for x in out if x])


def direct_official_candidates(card_id: str) -> list[str]:
    out: list[str] = []
    mirrors = official_image_mirrors_for(card_id)
    for stem in jp_image_stems(card_id):
        for host in mirrors:
            out.append(f"{host}images/cardlist/card/{stem}.png")
    return dedupe(out)


def extract_series_values(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    select = soup.find("select", attrs={"name": "series"})
    if not select:
        return []
    values: list[str] = []
    for opt in select.find_all("option"):
        value = str(opt.get("value") or "").strip()
        if value.isdigit():
            values.append(value)
    return list(dict.fromkeys(values))


def parse_jp_cardlist_images(html: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    soup = BeautifulSoup(html, "html.parser")
    for modal in soup.select("dl.modalCol[id]"):
        card_id = normalize_card_id(modal.get("id"))
        if not card_id:
            continue
        urls: list[str] = []
        for img in modal.select("img[data-src], img[src]"):
            src = str(img.get("data-src") or img.get("src") or "").strip()
            if "cardlist/card/" not in src.lower():
                continue
            if "dummy.gif" in src.lower():
                continue
            urls.append(to_jp_image_url(src))
        if urls:
            out.setdefault(card_id, [])
            out[card_id].extend(urls)
    # Fallback: filename scan if modal parse missed some.
    for fname in re.findall(
        r"cardlist/card/([^\"'?]+\.(?:png|jpg|jpeg|webp))",
        html,
        flags=re.IGNORECASE,
    ):
        stem = Path(fname).stem
        card_id = normalize_card_id(stem)
        if not card_id:
            continue
        out.setdefault(card_id, []).append(f"{JP_IMAGE_HOST}images/cardlist/card/{fname}")
    return {cid: dedupe(urls) for cid, urls in out.items()}


def crawl_jp_cardlist_images(session: requests.Session) -> dict[str, list[str]]:
    print(f"抓取日文官网卡表: {JP_CARDLIST_URL}", flush=True)
    try:
        resp = session.get(JP_CARDLIST_URL, headers=REQUEST_HEADERS, timeout=25)
    except requests.RequestException as exc:
        print(f"[jp-cardlist] error={exc}")
        return {}
    if resp.status_code != 200 or not resp.text.strip():
        print(f"[jp-cardlist] status={resp.status_code}")
        return {}

    merged = parse_jp_cardlist_images(resp.text)
    series_values = extract_series_values(resp.text)
    print(f"[jp-cardlist] default={len(merged)} series={len(series_values)}", flush=True)
    for series in series_values:
        try:
            series_resp = session.post(
                JP_CARDLIST_URL,
                data={"search": "true", "series": series},
                headers=REQUEST_HEADERS,
                timeout=30,
            )
        except requests.RequestException:
            continue
        if series_resp.status_code != 200 or not series_resp.text.strip():
            continue
        extra = parse_jp_cardlist_images(series_resp.text)
        for cid, urls in extra.items():
            merged.setdefault(cid, [])
            merged[cid].extend(urls)
            merged[cid] = dedupe(merged[cid])
    print(f"[jp-cardlist] total image ids={len(merged)}", flush=True)
    return merged


def limitless_page_candidates(card_id: str) -> list[str]:
    page_paths = [
        f"cards/{card_id.lower()}",
        f"cards/{card_id.upper()}",
        f"cards/{card_id.lower().replace('-', '')}",
    ]
    out: list[str] = []
    for path in page_paths:
        url = urljoin(LIMITLESS_BASE, path)
        try:
            resp = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0 OPCG-ImageSync/1.0"})
            if resp.status_code != 200:
                continue
        except requests.RequestException:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        meta = soup.find("meta", attrs={"property": "og:image"})
        if meta and meta.get("content"):
            out.append(str(meta.get("content")).strip())
        for img in soup.find_all("img", src=True):
            src = str(img.get("src") or "").strip()
            if src and ("card" in src.lower() or card_id.lower() in src.lower()):
                out.append(urljoin(url, src))
                break
    return dedupe(out)


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def collect_sync_entries(index_data: dict) -> dict[str, dict]:
    entries: dict[str, dict] = {}

    for raw_id, card in index_data.items():
        card_id = normalize_card_id(raw_id)
        if not card_id:
            continue
        entries[card_id] = card if isinstance(card, dict) else {}

    if CARDS_DIR.exists():
        for json_file in CARDS_DIR.rglob("*.json"):
            try:
                payload = json.loads(json_file.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue

            records: list[dict] = []
            if isinstance(payload, list):
                records = [x for x in payload if isinstance(x, dict)]
            elif isinstance(payload, dict):
                if "id" in payload:
                    records = [payload]
                else:
                    records = [x for x in payload.values() if isinstance(x, dict)]

            for record in records:
                card_id = normalize_card_id(record.get("id"))
                if not card_id:
                    continue
                existing = entries.get(card_id, {})
                merged = dict(existing)
                for field in ("img_full_url", "img_url"):
                    if record.get(field):
                        merged[field] = record.get(field)
                entries[card_id] = merged

    return entries


def load_preview_ids() -> set[str]:
    path = BASE_DIR / "index" / "preview_card_ids.json"
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if isinstance(payload, dict):
        ids = payload.get("ids") or []
        return {normalize_card_id(str(x)) for x in ids if str(x).strip()}
    if isinstance(payload, list):
        return {normalize_card_id(str(x)) for x in payload if str(x).strip()}
    return set()


def write_preview_ids(remaining: set[str]) -> None:
    path = BASE_DIR / "index" / "preview_card_ids.json"
    payload: dict = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ids": sorted(remaining),
    }
    try:
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if isinstance(old, dict) and old.get("set"):
            payload["set"] = old["set"]
    except (OSError, json.JSONDecodeError):
        pass
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_official_cdn_url(url: str) -> bool:
    host = (url or "").lower()
    return "onepiece-cardgame.com" in host and "/images/cardlist/card/" in host


def _fetch_host_md5(session: requests.Session, host: str, card_id: str) -> str | None:
    url = f"{host}images/cardlist/card/{card_id}.png"
    try:
        resp = session.get(url, timeout=15, headers=REQUEST_HEADERS)
    except requests.RequestException:
        return None
    if resp.status_code != 200 or "image" not in resp.headers.get("content-type", "").lower():
        return None
    if len(resp.content) < 800:
        return None
    return hashlib.md5(resp.content).hexdigest()


def local_pack_md5(card_id: str) -> str | None:
    for fp in PACKS_DIR.glob(f"{card_id}.*"):
        if fp.is_file() and fp.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            try:
                return hashlib.md5(fp.read_bytes()).hexdigest()
            except OSError:
                return None
    return None


def needs_en_art_fix(card_id: str, session: requests.Session) -> bool:
    """Local pack matches EN official art but not asia-tc (繁中)."""
    loc = local_pack_md5(card_id)
    if not loc:
        return False
    tc = _fetch_host_md5(session, "https://asia-tc.onepiece-cardgame.com/", card_id)
    en = _fetch_host_md5(session, "https://en.onepiece-cardgame.com/", card_id)
    if not tc or not en:
        return False
    return loc == en and loc != tc


def download_image(card_id: str, candidates: list[str], session: requests.Session) -> tuple[bool, str]:
    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    for url in candidates:
        try:
            resp = session.get(url, timeout=15, headers=REQUEST_HEADERS)
        except requests.RequestException:
            continue
        ctype = resp.headers.get("content-type", "").lower()
        if resp.status_code != 200 or "image" not in ctype:
            continue
        if len(resp.content) < 800:
            continue
        ext = guess_ext(url)
        target = PACKS_DIR / f"{card_id}{ext}"
        try:
            target.write_bytes(resp.content)
            return True, url
        except OSError:
            continue
    return False, ""


def main() -> None:
    parser = argparse.ArgumentParser(description="从日文官网同步卡图到本地 packs 目录")
    parser.add_argument("--card-id", type=str, default="", help="只下载单一卡号，例如 OP13-118-P2")
    parser.add_argument(
        "--card-ids",
        type=str,
        default="",
        help="下载多个卡号（逗号分隔），例如 OP13-118,OP13-118-P1,OP13-118-P2",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="已有本地图也重新下载覆盖（用于修正错图）",
    )
    parser.add_argument(
        "--overwrite-preview",
        action="store_true",
        help="只重下 preview 标记的卡；官网 CDN 成功后清掉 preview",
    )
    parser.add_argument(
        "--fix-en-art",
        action="store_true",
        help="只重下本地图与英文官网相同、但与 asia-tc 繁中不同的卡（修正 OP 旧系列英文卡面）",
    )
    args = parser.parse_args()

    if not INDEX_PATH.exists():
        raise SystemExit(f"未找到索引文件: {INDEX_PATH}")
    data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("cards_by_id.json 格式错误，应该是对象映射。")

    entries = collect_sync_entries(data)
    session = requests.Session()
    session.trust_env = False
    jp_map = crawl_jp_cardlist_images(session)
    for cid, urls in jp_map.items():
        entries.setdefault(cid, {})

    target_ids: set[str] = set()
    if args.card_id:
        cid = normalize_card_id(args.card_id)
        if cid:
            target_ids.add(cid)
    if args.card_ids:
        for raw in str(args.card_ids).split(","):
            cid = normalize_card_id(raw.strip())
            if cid:
                target_ids.add(cid)
    work_items = sorted(entries.items(), key=lambda x: x[0])
    if target_ids:
        work_items = [row for row in work_items if row[0] in target_ids]
        if not work_items:
            raise SystemExit("未找到指定卡号，请检查 --card-id / --card-ids 输入。")

    preview_ids = load_preview_ids()
    if args.overwrite_preview:
        work_items = [
            row
            for row in work_items
            if row[0] in preview_ids
            or (isinstance(row[1], dict) and bool(row[1].get("preview")))
        ]
        if not work_items:
            print("没有 preview 卡需要覆盖。")
            return
        preview_ids = {row[0] for row in work_items} | preview_ids

    total = 0
    skipped = 0
    downloaded = 0
    failed = 0
    cleared_preview: list[str] = []
    index_dirty = False

    for card_id, card in work_items:
        total += 1
        existing = list(PACKS_DIR.glob(f"{card_id}.*"))
        force = bool(args.overwrite or args.overwrite_preview)
        if args.fix_en_art:
            if not needs_en_art_fix(card_id, session):
                skipped += 1
                continue
            force = True
        elif existing and not force:
            skipped += 1
            continue

        # asia-tc (繁中) → JP official → EN last.
        candidates = list(direct_official_candidates(card_id))
        candidates.extend(official_candidates(card if isinstance(card, dict) else {}))
        candidates.extend(jp_map.get(card_id) or [])
        if not args.overwrite_preview and not candidates:
            candidates.extend(limitless_page_candidates(card_id))
        candidates = dedupe(candidates)
        if not candidates:
            failed += 1
            continue

        ok, used_url = download_image(card_id, candidates, session)
        if ok:
            downloaded += 1
            if args.overwrite_preview and is_official_cdn_url(used_url):
                row = data.get(card_id)
                if isinstance(row, dict) and row.get("preview"):
                    row.pop("preview", None)
                    data[card_id] = row
                    index_dirty = True
                preview_ids.discard(card_id)
                cleared_preview.append(card_id)
        else:
            failed += 1

    if index_dirty:
        INDEX_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.overwrite_preview:
        write_preview_ids(preview_ids)

    print(f"总卡数: {total}")
    print(f"已存在跳过: {skipped}")
    print(f"本次下载成功: {downloaded}")
    print(f"下载失败: {failed}")
    if args.overwrite_preview:
        print(f"清掉 preview 标记: {len(cleared_preview)}")
    print(f"本地图库目录: {PACKS_DIR}")


if __name__ == "__main__":
    main()
