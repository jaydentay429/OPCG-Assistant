from __future__ import annotations

import argparse
import json
import os
import time
import re
import warnings
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    import imagehash
    from PIL import Image
except Exception:  # pragma: no cover - optional runtime dependency
    imagehash = None
    Image = None

warnings.filterwarnings(
    "ignore",
    message="Palette images with Transparency expressed in bytes should be converted to RGBA images",
    category=UserWarning,
)


BASE_DIR = Path(__file__).resolve().parent
INDEX_PATH = BASE_DIR / "index" / "cards_by_id.json"
PACKS_DIR = BASE_DIR / "packs"
PRICE_PATH = BASE_DIR / "meta" / "market_prices.json"
SEARCH_TEMPLATE = os.getenv(
    "YUYUTEI_SEARCH_URL_TEMPLATE",
    "https://yuyu-tei.jp/sell/opc/s/search?search_word={query}",
)
SEARCH_TEMPLATE_FALLBACK = os.getenv(
    "YUYUTEI_SEARCH_URL_TEMPLATE_FALLBACK",
    "https://yuyu-tei.jp/buy/opc/s/search?search_word={query}",
)
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) OPCG-YuyuTeiSync/1.0",
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
}
# When yuyu-tei returns heavy 429s, short sleeps cause "busy work" with almost no success.
YUYUTEI_HTTP_RETRIES = max(0, int(os.getenv("YUYUTEI_HTTP_RETRIES", "3")))
YUYUTEI_429_BACKOFF_CAP_SEC = float(os.getenv("YUYUTEI_429_BACKOFF_CAP_SEC", "600"))
SEARCH_SP_URL = "https://yuyu-tei.jp/sell/opc/s/searchSP"
DEFAULT_SEARCH_TEMPLATES = [
    "https://yuyu-tei.jp/sell/opc/s/search?search_word={query}",
    "https://yuyu-tei.jp/buy/opc/s/search?search_word={query}",
]
MIN_REASONABLE_PRICE_JPY = 1
VARIANT_HASH_MAX_DIST = 16
VARIANT_HASH_MIN_GAP = 0
VARIANT_HASH_RESCUE_MAX_DIST = 24
VARIANT_HASH_RESCUE_MAX_DELTA = 2
VARIANT_HASH_RESCUE_STRONG_MARGIN = 2


def _is_reasonable_price(value: int) -> bool:
    return int(value) >= MIN_REASONABLE_PRICE_JPY


def _series_bucket_from_base(base_id: str) -> str:
    """
    OP13-118 -> op13
    ST29-001 -> st29
    EB02-010 -> eb02
    """
    base = normalize_card_id(base_id)
    m = re.match(r"^([A-Z]{2,4}\d{2})-\d{3}", base)
    if not m:
        return ""
    return m.group(1).lower()


def _trace_debug(msg: str) -> None:
    trace = getattr(fetch_price_from_yuyutei, "_last_trace", None)  # type: ignore[name-defined]
    if isinstance(trace, list) and len(trace) < 220:
        trace.append(msg)


def normalize_card_id(raw: str) -> str:
    text = str(raw or "").strip().upper().replace("_", "-").replace(" ", "")
    text = text.replace("－", "-")
    text = re.sub(r"[^A-Z0-9-]", "", text)
    m_don = re.match(r"^(DON[A-Z0-9]*)-(\d{3,5}(?:-[A-Z0-9]+)?)$", text)
    if m_don:
        return f"{m_don.group(1)}-{m_don.group(2)}"
    # Normalize variant ids without separator: OP15-002P1 -> OP15-002-P1
    text = re.sub(
        r"^([A-Z]{2,4}-?\d{2}-\d{3})([A-Z][A-Z0-9]{0,4})$",
        r"\1-\2",
        text,
    )
    m = re.match(r"^([A-Z]{2,4})-?(\d{2})-(\d{3}(?:-[A-Z0-9]+)?)$", text)
    if m:
        text = f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    return text


def is_don_card_id(card_id: str) -> bool:
    return normalize_card_id(card_id).startswith("DON")


def notify_progress(message: str) -> None:
    """Loud terminal marker + macOS notification (best-effort)."""
    line = str(message or "").strip()
    if not line:
        return
    # Bell + banner so it's easy to spot in Terminal/Cursor.
    print("\a", end="", flush=True)
    print("=" * 60, flush=True)
    print(f"[通知] {line}", flush=True)
    print("=" * 60, flush=True)
    try:
        import subprocess

        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification {json.dumps(line, ensure_ascii=False)} with title "OPCG 市价同步"',
            ],
            check=False,
            timeout=5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso_ts(raw: Any) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def has_ok_price(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if not str(row.get("status") or "").startswith("ok"):
        return False
    return row.get("current_price") is not None


def has_usable_price(row: Any) -> bool:
    """True when we already store a positive current price (worth daily refresh)."""
    if not isinstance(row, dict):
        return False
    try:
        return int(row.get("current_price") or 0) > 0
    except (TypeError, ValueError):
        return False


def price_status(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    return str(row.get("status") or "").strip()


# Soft-fail statuses worth retrying soon; hard misses only rotate via stale window.
RETRY_SOON_STATUSES = {
    "http_429",
    "http_error",
    "request_error",
    "network_error",
    "error",
}
HARD_MISS_PREFIXES = (
    "variant_not_found",
    "price_not_found",
)


def is_hard_miss_status(status: str) -> bool:
    s = str(status or "").strip().lower()
    return any(s.startswith(p) for p in HARD_MISS_PREFIXES)


def base_card_id(card_id: str) -> str:
    text = normalize_card_id(card_id)
    m = re.match(r"^([A-Z]{2,4}\d{2}-\d{3})", text)
    if m:
        return m.group(1)
    m = re.match(r"^(P-\d{3})", text)
    return m.group(1) if m else text


def is_variant_card_id(card_id: str) -> bool:
    text = normalize_card_id(card_id)
    if re.match(r"^P-\d{3}-[A-Z0-9]+$", text):
        return True
    return bool(re.match(r"^[A-Z]{2,4}\d{2}-\d{3}-[A-Z0-9]+$", text))


_PARALLEL_NAME_RE = re.compile(r"パラレル|PARALLEL", re.IGNORECASE)
_SPECIAL_NAME_RE = re.compile(
    r"スーパーパラレル|SUPER\s*PARALLEL|コミパラ|漫画|箔押し|LECAFIG|金箔|銀箔|プロモ箔|特装",
    re.IGNORECASE,
)
_STAMP_NONE_RE = re.compile(r"刻印なし|無刻印", re.IGNORECASE)
_STAMP_ARI_RE = re.compile(r"刻印あり|有刻印", re.IGNORECASE)
_CARD_ID_IN_TEXT_RE = re.compile(
    r"\b("
    r"(?:[A-Z]{2,4}-?\d{2}-\d{3}(?:[-_ ]?[A-Z][A-Z0-9]{0,4})?)"
    r"|(?:P-\d{3}(?:-[A-Z0-9]+)?)"
    r")\b",
    re.IGNORECASE,
)
_PROMO_CARD_ID_RE = re.compile(r"^P-\d{3}(?:-[A-Z0-9]+)?$", re.IGNORECASE)
_YEN_RE = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})*)\s*円")


def classify_listing_name(name: str) -> str:
    """Return base | parallel | special for a yuyu-tei product title."""
    text = str(name or "").strip()
    if not text:
        return "base"
    if _SPECIAL_NAME_RE.search(text):
        return "special"
    if _PARALLEL_NAME_RE.search(text):
        return "parallel"
    return "base"


def _section_rarity_near(node) -> str:
    """Best-effort rarity bucket from nearest 'P-L Card List' / 'L Card List' header."""
    cur = node
    for _ in range(8):
        if cur is None:
            break
        header = None
        if getattr(cur, "select_one", None):
            header = cur.select_one(".text-primary.fs-4, .fs-4.text-primary")
        if header is not None:
            ht = header.get_text(" ", strip=True).upper().replace(" ", "")
            m = re.match(r"^(P-[A-Z]+|[A-Z]+(?:-[A-Z]+)?)CARDLIST", ht)
            if m:
                return m.group(1)
            m2 = re.match(r"^(P-[A-Z]+|[A-Z]+)\b", ht)
            if m2 and "LIST" in ht:
                return m2.group(1)
        # Walk previous siblings for a list header.
        sib = getattr(cur, "previous_sibling", None)
        steps = 0
        while sib is not None and steps < 6:
            steps += 1
            if getattr(sib, "get_text", None):
                ht = sib.get_text(" ", strip=True).upper().replace(" ", "")
                if "CARDLIST" in ht:
                    m = re.match(r"^(P-[A-Z]+|[A-Z]+(?:-[A-Z]+)?)CARDLIST", ht)
                    if m:
                        return m.group(1)
            sib = getattr(sib, "previous_sibling", None)
        cur = getattr(cur, "parent", None)
    return ""


def parse_card_products(html: str) -> list[dict[str, Any]]:
    """
    Structured parse of yuyu-tei search/detail product cards.
    Each item: card_id, name, price, kind(base|parallel|special), rarity, in_stock, image_url
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, Any]] = []
    for prod in soup.select(".card-product"):
        text = prod.get_text(" ", strip=True)
        if not text:
            continue
        id_match = _CARD_ID_IN_TEXT_RE.search(text)
        if not id_match:
            continue
        card_id = normalize_card_id(id_match.group(1))
        if not card_id:
            continue
        name_el = prod.select_one(".text-primary.fw-bold")
        name = name_el.get_text(" ", strip=True) if name_el else ""
        if not name:
            # Fallback: strip id / price / stock chrome from text.
            name = re.sub(r"\b[A-Z]{2,4}-?\d{2}-\d{3}(?:[-_ ]?[A-Z0-9]+)?\b", "", text, count=1)
            name = re.sub(r"[0-9]{1,3}(?:,[0-9]{3})*\s*円.*$", "", name).strip()
        price_el = prod.select_one("strong.d-block.text-end")
        price_txt = price_el.get_text(" ", strip=True) if price_el else text
        pm = _YEN_RE.search(price_txt)
        if not pm:
            continue
        try:
            price = int(pm.group(1).replace(",", ""))
        except ValueError:
            continue
        if not _is_reasonable_price(price):
            continue
        classes = prod.get("class") or []
        in_stock = "sold-out" not in classes
        img_url = ""
        for img in prod.find_all("img"):
            src = str(img.get("data-src") or img.get("src") or "").strip()
            if not src:
                continue
            full = urljoin("https://yuyu-tei.jp/", src)
            fu = full.upper()
            if "CARD.YUYU-TEI.JP/OPC/" in fu or "/OPC/" in fu:
                img_url = full
                break
        kind = classify_listing_name(name)
        rarity = _section_rarity_near(prod)
        # P-* rarity sections are almost always alternate/parallel printings
        # (e.g. OP cards under "P-L Card List"). Do NOT reclassify true promo ids
        # like P-096 whose printed rarity is also "P".
        if rarity.startswith("P-") and kind == "base" and not _PROMO_CARD_ID_RE.match(card_id):
            kind = "parallel"
        out.append(
            {
                "card_id": card_id,
                "base_id": base_card_id(card_id),
                "name": name,
                "price": price,
                "kind": kind,
                "rarity": rarity,
                "in_stock": in_stock,
                "image_url": img_url,
            }
        )
    return out


def _pick_best_price(rows: list[dict[str, Any]]) -> int | None:
    if not rows:
        return None
    stocked = [r for r in rows if r.get("in_stock")]
    pool = stocked or rows
    return min(int(r["price"]) for r in pool)


def _yuyu_image_candidates(url: str) -> list[str]:
    text = str(url or "").strip()
    if not text:
        return []
    out: list[str] = []
    if "/100_140/" in text:
        out.append(text.replace("/100_140/", "/front/"))
        out.append(text.replace("/100_140/", "/400_560/"))
    elif "/400_560/" in text:
        out.append(text.replace("/400_560/", "/front/"))
    out.append(text)
    return list(dict.fromkeys(out))


def _card_index() -> dict[str, Any]:
    cached = getattr(_card_index, "_data", None)
    if isinstance(cached, dict):
        return cached
    data = load_json(INDEX_PATH, {})
    index = data if isinstance(data, dict) else {}
    setattr(_card_index, "_data", index)
    return index


def _index_row(card_id: str) -> dict[str, Any]:
    index = _card_index()
    cid = normalize_card_id(card_id)
    row = index.get(cid)
    if isinstance(row, dict):
        return row
    row = index.get(card_id)
    return row if isinstance(row, dict) else {}


def _is_prize_or_event_variant(card_id: str) -> bool:
    row = _index_row(card_id)
    blob = " ".join(
        [
            str(row.get("name") or ""),
            str(row.get("rarity") or ""),
            " ".join(str(x) for x in (row.get("card_sets") or [])),
        ]
    )
    return bool(
        re.search(
            r"記念|優勝|準優勝|ベスト\d+|CHAMPIONSHIP|チャンピオンシップ|NOT FOR SALE|大会|シリアル|編號|ゲットキャンペーン|番号入り",
            blob,
            flags=re.IGNORECASE,
        )
    )


def _is_stamp_special_name(name: str) -> bool:
    text = str(name or "")
    if not (_STAMP_NONE_RE.search(text) or _STAMP_ARI_RE.search(text)):
        return False
    return bool(
        re.search(r"スーパーパラレル|コミパラ|SUPER\s*PARALLEL", text, flags=re.IGNORECASE)
    )


def _is_manga_special_name(name: str) -> bool:
    text = str(name or "")
    return bool(re.search(r"スーパーパラレル|コミパラ|SUPER\s*PARALLEL", text, flags=re.IGNORECASE))


def _is_likely_manga_variant(card_id: str) -> bool:
    """Booster manga rare is usually the highest same-set 異圖 P-variant."""
    cid = normalize_card_id(card_id)
    if not re.search(r"-P\d+$", cid) or _is_prize_or_event_variant(cid):
        return False
    row = _index_row(cid)
    name = str(row.get("name") or "")
    rarity = str(row.get("rarity") or "")
    sets = [str(x) for x in (row.get("card_sets") or [])]
    blob = " ".join([name, rarity, *sets])
    if re.search(r"SP卡|ANNIVERSARY|THE BEST|PRB-|チャンピオン", blob, flags=re.IGNORECASE):
        return False
    if "異圖" not in name and "異画" not in name:
        return False
    my_sets = set(sets)
    same: list[str] = []
    for oid in _known_family_ids(base_card_id(cid)):
        if not re.search(r"-P\d+$", oid) or _is_prize_or_event_variant(oid):
            continue
        orow = _index_row(oid)
        oname = str(orow.get("name") or "")
        if "異圖" not in oname and "異画" not in oname:
            continue
        osets = {str(x) for x in (orow.get("card_sets") or [])}
        if my_sets & osets:
            same.append(oid)
    if not same:
        return False
    same.sort(key=lambda x: int(re.search(r"-P(\d+)$", x).group(1)))
    if len(same) == 1:
        sets_blob = " ".join(sets)
        promo_like = bool(re.search(r"プロモ|推廣|限定|PREMIUM|プレミアム|コレクション", sets_blob, flags=re.IGNORECASE))
        booster_like = bool(re.search(r"【OP-\d+】|【EB-\d+】|【ST-\d+】", sets_blob))
        return promo_like and not booster_like and same[0] == cid
    return same[-1] == cid


def _resolve_from_card_products(
    session: requests.Session,
    products: list[dict[str, Any]],
    card_id: str,
    *,
    allow_image_hash: bool = True,
) -> tuple[int | None, str]:
    """Accurate resolve using structured product cards (no base↔variant mixing)."""
    normalized = normalize_card_id(card_id)
    base = base_card_id(normalized)
    family = [p for p in products if p.get("base_id") == base or p.get("card_id") == base]
    if not family:
        # Some pages only label the exact id once; keep products whose text id equals base.
        family = [p for p in products if base_card_id(str(p.get("card_id") or "")) == base]
    if not family:
        return None, "price_not_found"

    if not is_variant_card_id(normalized):
        base_rows = [p for p in family if p.get("kind") == "base"]
        price = _pick_best_price(base_rows)
        if price is not None:
            return price, "ok_exact"
        return None, "price_not_found"

    # Variants: never use base listings.
    parallel_rows = [p for p in family if p.get("kind") in {"parallel", "special"}]
    if not parallel_rows:
        return None, "variant_not_found"

    # Exact id on listing (rare on yuyu-tei, but strongest).
    exact_rows = [p for p in parallel_rows if p.get("card_id") == normalized]
    price = _pick_best_price(exact_rows)
    if price is not None:
        return price, "ok_variant_id_exact"

    # If the family has only one parallel listing and our index has only one
    # parallel variant id, assign safely (no image download needed).
    non_special = [p for p in parallel_rows if p.get("kind") == "parallel"]
    known = sorted(
        cid
        for cid in _known_family_ids(base)
        if is_variant_card_id(cid) and not re.search(r"-(SP|TR|SEC)$", cid)
    )
    # Prefer -P* style ids.
    p_ids = [cid for cid in known if re.search(r"-P\d+$", cid)]
    if len(non_special) == 1 and len(p_ids) == 1 and p_ids[0] == normalized:
        return int(non_special[0]["price"]), "ok_variant_single_parallel"

    # Image-hash against local packs for P1/P2 disambiguation (slow; optional).
    if allow_image_hash:
        by_hash = _resolve_variant_by_image_hash_from_products(session, parallel_rows, normalized)
        if by_hash is not None:
            return by_hash, "ok_variant_imagehash"
        remainder = _resolve_unmatched_special_remainder(session, parallel_rows, normalized)
        if remainder is not None:
            return remainder, "ok_variant_remainder_single"

    return None, "variant_not_found"


def _resolve_variant_by_image_hash_from_products(
    session: requests.Session,
    products: list[dict[str, Any]],
    normalized_variant: str,
) -> int | None:
    if not is_variant_card_id(normalized_variant):
        return None
    local_hashes = _local_variant_hashes(base_card_id(normalized_variant))
    if not local_hashes or normalized_variant not in local_hashes:
        _trace_debug(f"hash missing local image for {normalized_variant}")
        return None
    items = [
        (str(p.get("image_url") or ""), int(p["price"]))
        for p in products
        if p.get("image_url") and not _is_manga_special_name(str(p.get("name") or ""))
    ]
    if not items:
        return None

    scored: list[tuple[int, int, int]] = []  # dist, second_dist, price
    for img_url, price in items:
        hh = None
        for candidate in _yuyu_image_candidates(img_url):
            try:
                resp = session.get(candidate, timeout=15, headers=REQUEST_HEADERS)
            except requests.RequestException:
                continue
            if resp.status_code != 200 or not resp.content:
                continue
            hh = _compute_phash_from_bytes(resp.content)
            if hh is not None:
                break
        if hh is None:
            continue
        family_dist: list[tuple[int, str]] = []
        for cid, h in local_hashes.items():
            try:
                d = int(h - hh)
            except Exception:
                continue
            family_dist.append((d, cid))
        if not family_dist:
            continue
        family_dist.sort(key=lambda x: x[0])
        best_dist, best_cid = family_dist[0]
        second_dist = family_dist[1][0] if len(family_dist) > 1 else 999
        _trace_debug(
            f"hash product best={best_cid} dist={best_dist} second={second_dist} "
            f"price={price} img={img_url}"
        )
        if best_cid != normalized_variant:
            continue
        # Require clear win over other family members.
        if best_dist <= VARIANT_HASH_MAX_DIST and (second_dist - best_dist) >= max(VARIANT_HASH_MIN_GAP, 2):
            scored.append((best_dist, second_dist, int(price)))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0])
    return scored[0][2]


def _resolve_unmatched_special_remainder(
    session: requests.Session,
    products: list[dict[str, Any]],
    normalized_variant: str,
) -> int | None:
    """If hash used every listing except one special, assign it to the last non-prize variant."""
    if not is_variant_card_id(normalized_variant):
        return None
    if _is_prize_or_event_variant(normalized_variant):
        return None
    base = base_card_id(normalized_variant)
    local_hashes = _local_variant_hashes(base)
    if normalized_variant not in local_hashes:
        return None
    variant_ids = [
        cid
        for cid in _known_family_ids(base)
        if is_variant_card_id(cid) and re.search(r"-P\d+$", cid) and not _is_prize_or_event_variant(cid)
    ]
    if normalized_variant not in variant_ids:
        return None

    claimed: set[str] = set()
    unused_rows: list[dict[str, Any]] = []
    for prod in products:
        # Manga/super-parallel shop photos vs SAMPLE arts are unstable; never consume via hash.
        if _is_manga_special_name(str(prod.get("name") or "")):
            unused_rows.append(prod)
            continue
        img_url = str(prod.get("image_url") or "")
        if not img_url:
            unused_rows.append(prod)
            continue
        hh = None
        for candidate in _yuyu_image_candidates(img_url):
            try:
                resp = session.get(candidate, timeout=15, headers=REQUEST_HEADERS)
            except requests.RequestException:
                continue
            if resp.status_code != 200 or not resp.content:
                continue
            hh = _compute_phash_from_bytes(resp.content)
            if hh is not None:
                break
        if hh is None:
            unused_rows.append(prod)
            continue
        family_dist: list[tuple[int, str]] = []
        for cid, h in local_hashes.items():
            if cid not in variant_ids and cid != normalized_variant:
                continue
            try:
                d = int(h - hh)
            except Exception:
                continue
            family_dist.append((d, cid))
        if not family_dist:
            unused_rows.append(prod)
            continue
        family_dist.sort(key=lambda x: x[0])
        best_dist, best_cid = family_dist[0]
        second_dist = family_dist[1][0] if len(family_dist) > 1 else 999
        if best_dist <= VARIANT_HASH_MAX_DIST and (second_dist - best_dist) >= max(VARIANT_HASH_MIN_GAP, 2):
            claimed.add(best_cid)
        else:
            unused_rows.append(prod)

    leftover_variants = [cid for cid in variant_ids if cid not in claimed]
    special_unused = [p for p in unused_rows if p.get("kind") == "special"]
    pool = special_unused or unused_rows
    stamp_price = _unstamped_manga_price(special_unused)
    if stamp_price is not None and normalized_variant in leftover_variants:
        manga_left = [cid for cid in leftover_variants if _is_likely_manga_variant(cid)]
        if leftover_variants == [normalized_variant] or manga_left == [normalized_variant]:
            _trace_debug(f"remainder stamp-unstamped {normalized_variant} price={stamp_price}")
            return stamp_price
    super_price = _single_super_parallel_price(special_unused, red=False)
    if super_price is not None and normalized_variant in leftover_variants:
        manga_left = [cid for cid in leftover_variants if _is_likely_manga_variant(cid)]
        if manga_left == [normalized_variant]:
            _trace_debug(f"remainder super-parallel {normalized_variant} price={super_price}")
            return super_price
    red_price = _single_super_parallel_price(special_unused, red=True)
    if (
        red_price is not None
        and leftover_variants == [normalized_variant]
        and not _is_likely_manga_variant(normalized_variant)
    ):
        _trace_debug(f"remainder red-super {normalized_variant} price={red_price}")
        return red_price
    if leftover_variants != [normalized_variant]:
        _trace_debug(
            f"remainder skip target={normalized_variant} leftover={leftover_variants} "
            f"unused={len(unused_rows)} special_unused={len(special_unused)}"
        )
        return None
    if len(pool) != 1:
        _trace_debug(
            f"remainder skip target={normalized_variant} leftover={leftover_variants} "
            f"unused={len(unused_rows)} special_unused={len(special_unused)}"
        )
        return None
    price = _pick_best_price(pool)
    _trace_debug(f"remainder assign {normalized_variant} price={price}")
    return price


def _unstamped_manga_price(rows: list[dict[str, Any]]) -> int | None:
    """Manga SAMPLE arts map to 刻印なし; 刻印あり is a stamped serial premium."""
    stamp_rows = [r for r in rows if _is_stamp_special_name(str(r.get("name") or ""))]
    none_rows = [r for r in stamp_rows if _STAMP_NONE_RE.search(str(r.get("name") or ""))]
    ari_rows = [
        r
        for r in stamp_rows
        if _STAMP_ARI_RE.search(str(r.get("name") or ""))
        and not _STAMP_NONE_RE.search(str(r.get("name") or ""))
    ]
    if not none_rows or not ari_rows:
        return None
    return _pick_best_price(none_rows)


def _single_super_parallel_price(rows: list[dict[str, Any]], *, red: bool) -> int | None:
    picked: list[dict[str, Any]] = []
    for row in rows:
        name = str(row.get("name") or "")
        if _is_stamp_special_name(name):
            continue
        is_red = "レッドスーパーパラレル" in name
        is_super = bool(re.search(r"スーパーパラレル|コミパラ|SUPER\s*PARALLEL", name, flags=re.IGNORECASE))
        if not is_super:
            continue
        if red and is_red:
            picked.append(row)
        elif not red and not is_red:
            picked.append(row)
    if len(picked) != 1:
        return None
    return _pick_best_price(picked)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def load_card_ids(limit: int | None) -> list[str]:
    data = load_json(INDEX_PATH, {})
    if not isinstance(data, dict):
        return []
    ids = [normalize_card_id(k) for k in data.keys()]
    ids = [x for x in ids if x]
    ids = list(dict.fromkeys(ids))
    ids.sort()
    if limit and limit > 0:
        return ids[:limit]
    return ids


def extract_price_jpy(html: str, card_id: str) -> int | None:
    upper = html.upper()
    target = normalize_card_id(card_id)
    alt_target = target.replace("-", "")
    is_variant = is_variant_card_id(target)

    # Avoid mixing base cards with variant ids like OP15-002-P1.
    if is_variant:
        vm = re.match(r"^([A-Z]{2,4}\d{2}-\d{3})-([A-Z][A-Z0-9]{0,4})$", target)
        if vm:
            base, suf = vm.groups()
            id_pat = rf"{re.escape(base)}(?:-|_)?{re.escape(suf)}"
            alt_pat = rf"{re.escape(base.replace('-', ''))}{re.escape(suf)}"
        else:
            id_pat = re.escape(target)
            alt_pat = re.escape(alt_target)
    else:
        id_pat = rf"{re.escape(target)}(?!-[A-Z0-9])"
        alt_pat = rf"{re.escape(alt_target)}(?![A-Z0-9])"

    near_re = re.compile(
        rf"(?:{id_pat}|{alt_pat})[\s\S]{{0,120}}?([0-9]{{1,3}}(?:,[0-9]{{3}})*)\s*円",
        re.IGNORECASE,
    )
    m = near_re.search(upper)
    if m:
        value = int(m.group(1).replace(",", ""))
        return value if _is_reasonable_price(value) else None
    return None


def extract_price_map_from_html(html: str) -> dict[str, int]:
    upper = html.upper()
    out: dict[str, int] = {}
    id_pat = (
        r"(?:[A-Z]{2,4}-?\d{2}-\d{3}(?:[-_ ]?[A-Z][A-Z0-9]{0,4})?|"
        r"P-\d{3}(?:-[A-Z0-9]+)?)"
    )
    # Pattern A: card id appears before price.
    forward = re.compile(
        rf"({id_pat})"
        r"[\s\S]{0,260}?"
        r"([0-9]{1,3}(?:,[0-9]{3})*)\s*円",
        re.IGNORECASE,
    )
    # Pattern B: price appears before card id (some page layouts do this).
    backward = re.compile(
        r"([0-9]{1,3}(?:,[0-9]{3})*)\s*円"
        r"[\s\S]{0,260}?"
        rf"({id_pat})",
        re.IGNORECASE,
    )

    for m in forward.finditer(upper):
        cid = normalize_card_id(m.group(1))
        if not cid:
            continue
        value = int(m.group(2).replace(",", ""))
        if not _is_reasonable_price(value):
            continue
        if cid in out:
            out[cid] = min(out[cid], value)
        else:
            out[cid] = value

    for m in backward.finditer(upper):
        value = int(m.group(1).replace(",", ""))
        if not _is_reasonable_price(value):
            continue
        cid = normalize_card_id(m.group(2))
        if not cid:
            continue
        if cid in out:
            out[cid] = min(out[cid], value)
        else:
            out[cid] = value
    return out


def extract_variant_price_loose(html: str, variant_id: str) -> int | None:
    """
    Variant-specific fallback parser for layouts where suffix is split/separated.
    """
    target = normalize_card_id(variant_id)
    vm = re.match(r"^([A-Z]{2,4}\d{2}-\d{3})-([A-Z][A-Z0-9]{0,4})$", target)
    if not vm:
        return None
    base, suffix = vm.groups()
    upper = html.upper()

    base_pat = re.compile(re.escape(base).replace(r"\-", r"[-_ ]?"), re.IGNORECASE)
    suffix_pat = re.compile(
        rf"(?:[-_ ]|&NBSP;|&#45;|&#95;)?{re.escape(suffix)}",
        re.IGNORECASE,
    )
    yen_pat = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})*)\s*円", re.IGNORECASE)
    hits: list[int] = []

    for bm in base_pat.finditer(upper):
        start = max(0, bm.start() - 180)
        end = min(len(upper), bm.end() + 320)
        block = upper[start:end]
        if not suffix_pat.search(block):
            continue
        for ym in yen_pat.finditer(block):
            try:
                value = int(ym.group(1).replace(",", ""))
            except (TypeError, ValueError):
                continue
            if value > 0:
                if not _is_reasonable_price(value):
                    continue
                hits.append(value)

    if not hits:
        return None
    return min(hits)


def extract_base_price_pool(html: str, base_id: str) -> list[int]:
    """
    Collect multiple visible prices around the same base card id.
    Useful when yuyutei does not expose explicit P1/R1 suffix in text.
    """
    upper = html.upper()
    base = normalize_card_id(base_id)
    bm = re.match(r"^([A-Z]{2,4}\d{2}-\d{3})$", base)
    if not bm:
        return []
    base = bm.group(1)
    base_pat = re.compile(re.escape(base).replace(r"\-", r"[-_ ]?"), re.IGNORECASE)
    yen_pat = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})*)\s*円", re.IGNORECASE)
    vals: list[int] = []

    for m in base_pat.finditer(upper):
        start = max(0, m.start() - 220)
        end = min(len(upper), m.end() + 380)
        block = upper[start:end]
        for ym in yen_pat.finditer(block):
            try:
                v = int(ym.group(1).replace(",", ""))
            except (TypeError, ValueError):
                continue
            if v > 0:
                if not _is_reasonable_price(v):
                    continue
                vals.append(v)
    if not vals:
        return []
    vals = sorted(set(vals))
    return vals


def _compute_phash_from_bytes(blob: bytes) -> Any | None:
    if not imagehash or not Image:
        return None
    try:
        with Image.open(BytesIO(blob)) as im:
            return imagehash.phash(im.convert("RGB"))
    except Exception:
        return None


def _compute_phash_from_path(path: Path) -> Any | None:
    if not imagehash or not Image:
        return None
    try:
        with Image.open(path) as im:
            return imagehash.phash(im.convert("RGB"))
    except Exception:
        return None


def _known_family_ids(base_id: str) -> set[str]:
    base = normalize_card_id(base_id)
    if not base:
        return set()
    cache = getattr(_known_family_ids, "_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(_known_family_ids, "_cache", cache)
    if base in cache:
        return set(cache[base])

    data = load_json(INDEX_PATH, {})
    known: set[str] = set()
    if isinstance(data, dict):
        prefix = f"{base}-"
        for raw in data.keys():
            cid = normalize_card_id(raw)
            if not cid:
                continue
            if cid == base or cid.startswith(prefix):
                known.add(cid)
    cache[base] = sorted(known)
    return known


def _local_variant_hashes(base_id: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    base = normalize_card_id(base_id)
    if not base:
        return out
    known_ids = _known_family_ids(base)
    for p in sorted(PACKS_DIR.glob(f"{base}*")):
        if not p.is_file():
            continue
        cid = normalize_card_id(p.stem)
        if not cid:
            continue
        # Guard against noisy duplicate filenames (e.g. "... 2.png")
        # by only keeping ids known in our official index family.
        if known_ids and cid not in known_ids:
            continue
        h = _compute_phash_from_path(p)
        if h is not None:
            out[cid] = h
    return out


def _extract_variant_image_price_items(
    html: str,
    base_id: str,
    *,
    require_base_match: bool = True,
) -> list[tuple[str, int]]:
    upper_base = normalize_card_id(base_id)
    if not upper_base:
        return []
    compact = upper_base.replace("-", "")
    series_bucket = _series_bucket_from_base(upper_base)
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, int]] = []

    yen_re = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})*)\s*円", re.IGNORECASE)
    for node in soup.find_all(string=yen_re):
        text = str(node)
        m = yen_re.search(text)
        if not m:
            continue
        try:
            price = int(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if not _is_reasonable_price(price):
            continue

        parent = node.parent
        block = parent
        matched_base = False
        for _ in range(4):
            if not block:
                break
            block_text = block.get_text(" ", strip=True).upper()
            if upper_base in block_text or compact in block_text:
                matched_base = True
                break
            block = block.parent
        if not block:
            continue
        if require_base_match and not matched_base:
            continue

        img = block.find("img")
        if not img:
            continue
        src = str(img.get("data-src") or img.get("src") or "").strip()
        if not src:
            continue
        full = urljoin("https://yuyu-tei.jp/", src)
        fu = full.upper()
        # Keep only likely card product image hosts/paths.
        if "CARD.YUYU-TEI.JP/OPC/" not in fu and "/OPC/" not in fu:
            continue
        # Reduce cross-series noise (e.g. OP13 matching OP15 thumbnails).
        if series_bucket and (f"/{series_bucket}/" not in full.lower()):
            continue
        out.append((full, price))

    # Fallback parser: scan images first, then read nearest text block price.
    # Some yuyu-tei pages do not keep "card id + price" in the same text node.
    for img in soup.find_all("img"):
        src = str(img.get("data-src") or img.get("src") or "").strip()
        if not src:
            continue
        full = urljoin("https://yuyu-tei.jp/", src)
        fu = full.upper()
        if "CARD.YUYU-TEI.JP/OPC/" not in fu and "/OPC/" not in fu:
            continue
        if series_bucket and (f"/{series_bucket}/" not in full.lower()):
            continue
        block = img
        picked_price: int | None = None
        matched_base = False
        for _ in range(5):
            if not block:
                break
            txt = block.get_text(" ", strip=True)
            txt_upper = (txt or "").upper()
            if upper_base in txt_upper or compact in txt_upper:
                matched_base = True
            mm = yen_re.search(txt or "")
            if mm:
                try:
                    val = int(mm.group(1).replace(",", ""))
                except ValueError:
                    val = 0
                if _is_reasonable_price(val) and (matched_base or not require_base_match):
                    picked_price = val
                    break
            block = block.parent
        if picked_price is not None:
            out.append((full, picked_price))

    # dedupe
    dedup: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for item in out:
        key = (item[0], item[1])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
    return dedup


def _resolve_variant_by_image_hash(
    session: requests.Session,
    html: str,
    normalized_variant: str,
    *,
    require_base_match: bool = True,
) -> int | None:
    if not is_variant_card_id(normalized_variant):
        return None
    local_hashes = _local_variant_hashes(base_card_id(normalized_variant))
    _trace_debug(
        f"hash local family={base_card_id(normalized_variant)} "
        f"target={normalized_variant} local_hashes={len(local_hashes)}"
    )
    if not local_hashes:
        return None
    items = _extract_variant_image_price_items(
        html,
        base_card_id(normalized_variant),
        require_base_match=require_base_match,
    )
    _trace_debug(f"hash candidate items={len(items)}")
    if not items:
        return None

    scored: list[tuple[int, int, int]] = []  # (dist, second_dist, price)
    rescue: list[tuple[int, int, int, str]] = []  # (target_dist, best_dist, price, best_cid)
    best_by_variant: dict[str, int] = {}
    for img_url, price in items:
        try:
            resp = session.get(img_url, timeout=15, headers=REQUEST_HEADERS)
        except requests.RequestException:
            continue
        if resp.status_code != 200 or not resp.content:
            continue
        hh = _compute_phash_from_bytes(resp.content)
        if hh is None:
            continue
        # Family-wise matching: compare this yuyutei image against all local
        # variants of the same base id, then only accept when target variant
        # is the nearest neighbor.
        family_dist: list[tuple[int, str]] = []
        for cid, h in local_hashes.items():
            try:
                d = int(h - hh)
            except Exception:
                continue
            family_dist.append((d, cid))
        if not family_dist:
            continue
        family_dist.sort(key=lambda x: x[0])
        best_dist, best_cid = family_dist[0]
        second_dist = family_dist[1][0] if len(family_dist) > 1 else 999
        prev_best = best_by_variant.get(best_cid)
        if prev_best is None or best_dist < prev_best:
            best_by_variant[best_cid] = best_dist

        target_dist: int | None = None
        for d, cid in family_dist:
            if cid == normalized_variant:
                target_dist = d
                break
        _trace_debug(
            f"hash candidate best={best_cid} dist={best_dist} "
            f"second={second_dist} price={price} img={img_url}"
        )
        if best_cid != normalized_variant:
            if target_dist is not None:
                rescue.append((target_dist, best_dist, int(price), best_cid))
            continue
        scored.append((best_dist, second_dist, int(price)))

    if scored:
        scored.sort(key=lambda x: x[0])
        best_dist, second_dist, best_price = scored[0]
        _trace_debug(f"hash target-best dist={best_dist} second={second_dist} price={best_price}")

        # Strict acceptance only — no near-tie rescue (that caused wrong variants).
        if best_dist <= VARIANT_HASH_MAX_DIST and (second_dist - best_dist >= max(VARIANT_HASH_MIN_GAP, 2)):
            return best_price
        _trace_debug("hash rejected by threshold/gap")
    else:
        _trace_debug("hash scored=0 for target variant")

    _trace_debug("hash unmatched (rescue disabled)")
    return None


def _extract_candidate_detail_links(html: str, base_id: str) -> list[str]:
    base = normalize_card_id(base_id)
    if not base:
        return []
    compact = base.replace("-", "")
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    for a in soup.find_all("a"):
        href = str(a.get("href") or "").strip()
        if not href:
            # yuyu-tei sometimes stores link in onclick/data-* attributes
            for key in ("data-href", "data-url", "onclick"):
                raw = str(a.get(key) or "").strip()
                if not raw:
                    continue
                m = re.search(r"(https?://[^\s'\"()]+|/[A-Za-z0-9_./?=&%-]+)", raw)
                if m:
                    href = m.group(1)
                    break
        if not href:
            continue
        text = (a.get_text(" ", strip=True) or "").upper()
        hu = href.upper()
        if base in text or compact in text or base in hu or compact in hu:
            out.append(urljoin("https://yuyu-tei.jp/", href))
            continue
        if "/SELL/" in hu and ("DETAIL" in hu or "PRICE" in hu or "CARD" in hu):
            out.append(urljoin("https://yuyu-tei.jp/", href))
    dedup: list[str] = []
    seen: set[str] = set()
    for u in out:
        if u in seen:
            continue
        seen.add(u)
        dedup.append(u)
    return dedup[:12]


def _resolve_variant_from_detail_pages(
    session: requests.Session,
    search_html: str,
    variant_id: str,
) -> tuple[int | None, str]:
    links = _extract_candidate_detail_links(search_html, base_card_id(variant_id))
    _trace_debug(f"detail links count={len(links)} for {variant_id}")
    if not links:
        return None, "detail_links_not_found"
    for link in links:
        detail_html, _ = request_html(session, link, timeout=20, retries=1)
        if not detail_html:
            continue
        # Detail pages often don't repeat base card-id text near image/price.
        # Use relaxed extraction there, but still keep hash family matching.
        by_hash_detail = _resolve_variant_by_image_hash(
            session,
            detail_html,
            variant_id,
            require_base_match=False,
        )
        if by_hash_detail is not None:
            return by_hash_detail, "ok_variant_detail"
        price, status = resolve_price_from_html(session, detail_html, variant_id)
        if price is None:
            continue
        if status in {
            "ok_variant_imagehash",
            "ok_variant_id_exact",
            "ok_variant_single_parallel",
            "ok_variant_remainder_single",
            "ok_variant_stamp_unstamped",
        }:
            return price, "ok_variant_detail"
    return None, "detail_variant_not_found"


def resolve_price_from_html(
    session: requests.Session,
    html: str,
    card_id: str,
    *,
    allow_image_hash: bool = True,
) -> tuple[int | None, str]:
    normalized = normalize_card_id(card_id)
    base = base_card_id(normalized)

    # 1) Preferred: structured .card-product parsing (avoids base/parallel mixups).
    products = parse_card_products(html)
    if products:
        price, status = _resolve_from_card_products(
            session,
            products,
            normalized,
            allow_image_hash=allow_image_hash,
        )
        if price is not None:
            return price, status
        # For variants, do not fall through to legacy base-price heuristics.
        if is_variant_card_id(normalized):
            # One more try: legacy image-hash over whole HTML, still no base fallback.
            if allow_image_hash:
                by_hash = _resolve_variant_by_image_hash(session, html, normalized)
                if by_hash is not None:
                    return by_hash, "ok_variant_imagehash"
            return None, status if status != "price_not_found" else "variant_not_found"

    # 2) Legacy map for pages without .card-product markup.
    parsed = extract_price_map_from_html(html)
    if is_variant_card_id(normalized):
        if normalized in parsed:
            return parsed[normalized], "ok_variant_id_exact"
        if allow_image_hash:
            by_hash = _resolve_variant_by_image_hash(session, html, normalized)
            if by_hash is not None:
                return by_hash, "ok_variant_imagehash"
            loose = extract_variant_price_loose(html, normalized)
            if loose is not None:
                return loose, "ok_variant_loose"
        # INTENTIONAL: never return base price for a variant id.
        return None, "variant_not_found"

    # Base card: exact id only. Ignore sibling parallel rows that share the same printed id.
    if normalized in parsed and not products:
        # Map may still be polluted; prefer regex that forbids trailing -SUFFIX.
        price = extract_price_jpy(html, normalized)
        if price is not None:
            return price, "ok_exact"
    price = extract_price_jpy(html, normalized)
    if price is not None:
        return price, "ok_exact"
    # Last resort for base: pool of nearby prices, but only if no parallel keyword in window.
    # Safer to miss than to take a parallel price.
    if base in parsed and base == normalized:
        # If HTML clearly has a non-parallel listing text near base id, accept map value
        # only when パラレル is not between id and price in a short window — handled by
        # extract_price_jpy already via (?!-[A-Z0-9]). Still reject if only parallel rows exist.
        upper = html.upper()
        if "パラレル" in html or "PARALLEL" in upper:
            # Without product cards we cannot safely separate; miss instead of guessing.
            return None, "price_not_found"
        return parsed[base], "ok_base_map"
    return None, "price_not_found"


def extract_bulk_prices_from_searchsp(html: str) -> dict[str, int]:
    upper = html.upper()
    out: dict[str, int] = {}
    pattern = re.compile(
        r"([A-Z]{2,4}-?\d{2}-\d{3}(?:-[A-Z0-9]+)?|P-\d{3}(?:-[A-Z0-9]+)?)"
        r"[\s\S]{0,260}?"
        r"([0-9]{1,3}(?:,[0-9]{3})*)\s*円",
        re.IGNORECASE,
    )
    for m in pattern.finditer(upper):
        cid = normalize_card_id(m.group(1))
        if not cid:
            continue
        value = int(m.group(2).replace(",", ""))
        if value <= 0:
            continue
        # Keep lowest visible selling price if multiple entries appear.
        if cid in out:
            out[cid] = min(out[cid], value)
        else:
            out[cid] = value
    return out


def request_html(
    session: requests.Session,
    url: str,
    *,
    timeout: int = 25,
    retries: int | None = None,
) -> tuple[str | None, str]:
    if retries is None:
        retries = YUYUTEI_HTTP_RETRIES
    last_status = "request_error"
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, timeout=timeout, headers=REQUEST_HEADERS)
        except requests.RequestException as exc:
            last_status = f"request_error: {exc}"
            if attempt < retries:
                time.sleep(0.9 + attempt * 0.7)
            continue

        if resp.status_code == 200:
            return resp.text, "ok"

        if resp.status_code == 429:
            last_status = "http_429"
            # Fail fast: one short cool-down + one retry max, then bubble up
            # so the main loop can apply a longer global pause (avoids stacking
            # multi-minute sleeps on every single family request).
            if attempt < min(retries, 1):
                time.sleep(2.5 + attempt)
                continue
            break

        if resp.status_code >= 500 and attempt < retries:
            last_status = f"http_{resp.status_code}"
            time.sleep(1.0 + attempt * 0.8)
            continue

        last_status = f"http_{resp.status_code}"
        break
    return None, last_status


def build_search_urls(card_id: str, *, quick: bool = False) -> list[str]:
    base = base_card_id(card_id)
    if quick:
        # Fast path: one sell-page query with base id covers base + parallels.
        return [DEFAULT_SEARCH_TEMPLATES[0].format(query=quote_plus(base))]

    query_variants = [
        card_id,
        base,
        card_id.replace("-", ""),
        base.replace("-", ""),
        card_id.replace("-", " "),
        base.replace("-", " "),
    ]
    query_variants = [q for q in query_variants if q]
    query_variants = list(dict.fromkeys(query_variants))

    templates = list(DEFAULT_SEARCH_TEMPLATES)
    for extra in (SEARCH_TEMPLATE, SEARCH_TEMPLATE_FALLBACK):
        if isinstance(extra, str) and "{query}" in extra and extra not in templates:
            templates.append(extra)

    urls: list[str] = []
    for q in query_variants:
        for tmpl in templates:
            urls.append(tmpl.format(query=quote_plus(q)))
    return list(dict.fromkeys(urls))


def _html_cache_get(url: str) -> str | None:
    cache = getattr(fetch_price_from_yuyutei, "_html_cache", None)
    if not isinstance(cache, dict):
        return None
    val = cache.get(url)
    return val if isinstance(val, str) and val else None


def _html_cache_set(url: str, html: str) -> None:
    cache = getattr(fetch_price_from_yuyutei, "_html_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(fetch_price_from_yuyutei, "_html_cache", cache)
    # Bound cache size for long runs.
    if len(cache) > 800:
        # Drop arbitrary oldest-ish entries.
        for k in list(cache.keys())[:200]:
            cache.pop(k, None)
    cache[url] = html


def request_html_cached(
    session: requests.Session,
    url: str,
    *,
    timeout: int = 25,
    retries: int | None = None,
) -> tuple[str | None, str]:
    cached = _html_cache_get(url)
    if cached:
        return cached, "ok_cache"
    html, status = request_html(session, url, timeout=timeout, retries=retries)
    if html:
        _html_cache_set(url, html)
    return html, status


def fetch_don_price_from_yuyutei(
    session: requests.Session,
    card_id: str,
) -> tuple[int | None, str]:
    row = _index_row(card_id)
    slug = str(row.get("yuyutei_slug") or "").strip()
    detail_url = str(row.get("yuyutei_url") or "").strip()
    if not slug and not detail_url:
        return None, "don_slug_missing"
    url = detail_url or f"https://yuyu-tei.jp/sell/opc/card/{slug}"
    html, status = request_html_cached(session, url, timeout=25)
    if not html:
        return None, status or "http_error"
    soup = BeautifulSoup(html, "html.parser")
    price_el = soup.select_one("strong.d-block.text-end")
    price_txt = price_el.get_text(" ", strip=True) if price_el else html
    pm = _YEN_RE.search(price_txt)
    if not pm:
        return None, "price_not_found"
    try:
        price = int(pm.group(1).replace(",", ""))
    except ValueError:
        return None, "price_not_found"
    if not _is_reasonable_price(price):
        return None, "price_not_found"
    return price, "ok_don_detail"


def fetch_price_from_yuyutei(
    session: requests.Session,
    card_id: str,
    *,
    deep_variant_check: bool = True,
) -> tuple[int | None, str]:
    trace: list[str] = []
    setattr(fetch_price_from_yuyutei, "_last_trace", trace)

    def _t(msg: str) -> None:
        if len(trace) < 120:
            trace.append(msg)

    # Bulk map is only safe for exact non-variant ids (searchSP often collapses parallels).
    bulk_map = getattr(fetch_price_from_yuyutei, "_bulk_map", None)
    normalized = normalize_card_id(card_id)
    if is_don_card_id(normalized):
        return fetch_don_price_from_yuyutei(session, normalized)

    if isinstance(bulk_map, dict) and not is_variant_card_id(normalized):
        direct = bulk_map.get(normalized)
        if isinstance(direct, int) and direct > 0:
            _t(f"bulk_map hit: {normalized} -> {direct}")
            return direct, "ok"

    base = base_card_id(card_id)
    _t(f"start normalized={normalized} base={base}")
    allow_hash = bool(deep_variant_check)

    def _scan_urls(urls_to_scan: list[str], target_id: str, last_error: str) -> tuple[int | None, str]:
        detail_seed_html = None
        for url in urls_to_scan:
            _t(f"scan url: {url}")
            html, status = request_html_cached(session, url, timeout=25)
            if not html:
                last_error = status
                _t(f"request failed: {status}")
                continue
            price, resolved_status = resolve_price_from_html(
                session,
                html,
                target_id,
                allow_image_hash=allow_hash,
            )
            if price is not None:
                _t(f"resolved in search html: status={resolved_status} price={price}")
                return price, resolved_status
            if deep_variant_check and is_variant_card_id(target_id) and detail_seed_html is None:
                # Keep first successful search HTML for a single detail-pass later.
                detail_seed_html = html
            last_error = resolved_status if resolved_status else "price_not_found"
            _t(f"search html unresolved: {last_error}")
        if deep_variant_check and is_variant_card_id(target_id) and detail_seed_html:
            d_price, d_status = _resolve_variant_from_detail_pages(session, detail_seed_html, target_id)
            if d_price is not None:
                _t(f"resolved in detail pages: status={d_status} price={d_price}")
                return d_price, d_status
            last_error = d_status
            _t(f"detail pass failed: {d_status}")
        return None, last_error

    # Fast path: one base-id sell search (covers almost all listings).
    urls = build_search_urls(base, quick=True)
    _t(f"quick urls count={len(urls)}")
    last_err = "price_not_found"
    price, status = _scan_urls(urls, normalized, last_err)
    if price is not None:
        return price, status
    last_err = status
    _t(f"quick scan miss: {status}")

    # Broader URL set only on miss.
    urls = build_search_urls(normalized, quick=False)
    _t(f"primary urls count={len(urls)}")
    price, status = _scan_urls(urls, normalized, last_err)
    if price is not None:
        return price, status
    last_err = status
    _t(f"primary scan miss: {status}")

    # Variant-specific fallback:
    # yuyu-tei often lists alternate arts under base id pages without suffix labels.
    if is_variant_card_id(normalized):
        base_urls = build_search_urls(base, quick=False)
        _t(f"base fallback urls count={len(base_urls)}")
        price, status = _scan_urls(base_urls, normalized, last_err)
        if price is not None:
            return price, status
        last_err = status
        _t(f"base scan miss: {status}")

    # Final fallback: parse global sell search page once.
    try:
        if not hasattr(fetch_price_from_yuyutei, "_searchsp_cache"):
            html, status = request_html(session, SEARCH_SP_URL, timeout=25)
            if html:
                setattr(fetch_price_from_yuyutei, "_searchsp_cache", html)
            else:
                setattr(fetch_price_from_yuyutei, "_searchsp_cache", "")
                last_err = status
                _t(f"searchSP request failed: {status}")
        searchsp_html = getattr(fetch_price_from_yuyutei, "_searchsp_cache")
        if searchsp_html:
            price, resolved_status = resolve_price_from_html(
                session,
                searchsp_html,
                normalized,
                allow_image_hash=allow_hash,
            )
            if price is not None:
                _t(f"resolved in searchSP: status={resolved_status} price={price}")
                return price, resolved_status
            _t("searchSP unresolved")
    except requests.RequestException:
        _t("searchSP request exception")
    _t(f"final miss: {last_err}")
    return None, last_err


def fetch_family_prices_from_yuyutei(
    session: requests.Session,
    family_ids: list[str],
    *,
    deep_variant_check: bool = True,
) -> dict[str, tuple[int | None, str]]:
    """
    Resolve a whole base-id family from one (cached) search page.
    Dramatically fewer HTTP requests than per-card fetching.
    """
    ids = [normalize_card_id(x) for x in family_ids if normalize_card_id(x)]
    ids = list(dict.fromkeys(ids))
    out: dict[str, tuple[int | None, str]] = {cid: (None, "price_not_found") for cid in ids}
    if not ids:
        return out
    base = base_card_id(ids[0])
    url = DEFAULT_SEARCH_TEMPLATES[0].format(query=quote_plus(base))
    html, status = request_html_cached(session, url, timeout=25)
    if not html:
        for cid in ids:
            out[cid] = (None, status)
        return out
    products = parse_card_products(html)
    allow_hash = bool(deep_variant_check)
    for cid in ids:
        if products:
            price, st = _resolve_from_card_products(
                session,
                products,
                cid,
                allow_image_hash=allow_hash,
            )
        else:
            price, st = resolve_price_from_html(
                session,
                html,
                cid,
                allow_image_hash=allow_hash,
            )
        if price is None and deep_variant_check and is_variant_card_id(cid):
            d_price, d_status = _resolve_variant_from_detail_pages(session, html, cid)
            if d_price is not None:
                price, st = d_price, d_status
        out[cid] = (price, st)
    return out


def merge_price_record(
    old: dict[str, Any],
    price: int | None,
    ts: str,
    source_url: str,
    *,
    reset_history: bool = False,
) -> dict[str, Any]:
    row = {} if reset_history else (dict(old) if isinstance(old, dict) else {})
    row.setdefault("source", "yuyu-tei")
    row.setdefault("currency", "JPY")
    row["source_url"] = source_url
    row["last_checked"] = ts
    history = row.get("history")
    if not isinstance(history, list):
        history = []
    if price is not None:
        row["current_price"] = price
        row["last_seen"] = ts
        if not history or history[-1].get("price") != price:
            history.append({"ts": ts, "price": price})
    row["history"] = history[-180:]
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="同步 yuyu-tei 卡牌市场价格与历史数据")
    parser.add_argument("--card-id", type=str, default="", help="只同步单一卡号，例如 OP15-002")
    parser.add_argument(
        "--card-ids",
        type=str,
        default="",
        help="同步多个卡号（逗号分隔），例如 OP15-002,OP15-002-P1,ST30-001",
    )
    parser.add_argument("--limit", type=int, default=0, help="只同步前 N 张卡（调试用）")
    parser.add_argument("--batch-size", type=int, default=80, help="每批家族数量（--by-family 时），默认 80")
    parser.add_argument("--batch-sleep", type=float, default=4.0, help="批次之间休眠秒数，默认 4")
    parser.add_argument("--retry-sleep-on-429", type=float, default=45.0, help="遇到 429 后额外休眠秒数")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="每处理 N 张打印一次进度（默认 25）",
    )
    parser.add_argument(
        "--request-sleep",
        type=float,
        default=0.35,
        help="每个家族请求后的短休眠（秒），默认 0.35（遇 429 会自动加大）",
    )
    parser.add_argument(
        "--cooldown-on-429",
        type=float,
        default=90.0,
        help="连续/单次 429 后的全局冷却秒数，默认 90",
    )
    parser.add_argument(
        "--by-family",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="按基础卡号家族一次抓取（默认开启，显著加速）",
    )
    parser.add_argument(
        "--skip-ok",
        action="store_true",
        help="跳过已有 ok 状态且带现价的卡（用于断点续跑）",
    )
    parser.add_argument(
        "--priced-or-new",
        action="store_true",
        help="每日模式：只刷新已有现价的卡 + 目录里尚未建价的新卡；跳过已知无价/miss",
    )
    parser.add_argument(
        "--stale-hours",
        type=float,
        default=0.0,
        help="增量模式：仍刷新 last_checked 超过 N 小时的 ok/硬 miss 卡（0=关闭）",
    )
    parser.add_argument(
        "--stale-limit",
        type=int,
        default=0,
        help="增量模式每次最多刷新多少张过期 ok 卡（0=不限制；建议每日 400~800）",
    )
    parser.add_argument(
        "--miss-limit",
        type=int,
        default=0,
        help="增量模式每次最多重试多少张硬 miss（variant/price_not_found；0=不限制）",
    )
    parser.add_argument(
        "--two-pass",
        action="store_true",
        help="两阶段同步：先快速扫全量（不做异图哈希），再仅对 miss 异图做深度匹配",
    )
    parser.add_argument(
        "--strict-variant",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="异画卡严格模式（默认开启）：未精确/图像命中则不回退基础版价格",
    )
    parser.add_argument(
        "--allow-variant-heuristic",
        action="store_true",
        help="配合 --strict-variant 使用：允许 ok_variant_heuristic 作为临时价格",
    )
    parser.add_argument(
        "--reset-history",
        action="store_true",
        help="重置本次同步卡号的历史价格，只保留本次结果（用于清理旧误抓数据）",
    )
    parser.add_argument(
        "--debug-variant",
        action="store_true",
        help="输出异画匹配调试轨迹（建议配合 --card-id 使用）",
    )
    args = parser.parse_args()

    target_id = normalize_card_id(args.card_id) if args.card_id else ""
    multi_ids: list[str] = []
    if args.card_ids:
        for raw in str(args.card_ids).split(","):
            cid = normalize_card_id(raw.strip())
            if cid:
                multi_ids.append(cid)
        # keep order, remove duplicates
        multi_ids = list(dict.fromkeys(multi_ids))

    if multi_ids:
        card_ids = multi_ids
    elif target_id:
        card_ids = [target_id]
    else:
        card_ids = load_card_ids(args.limit if args.limit > 0 else None)

    if not card_ids:
        raise SystemExit("没有可同步的卡号。")

    payload = load_json(PRICE_PATH, {})
    if not isinstance(payload, dict):
        payload = {}
    cards = payload.get("cards")
    if not isinstance(cards, dict):
        cards = {}

    if args.priced_or_new:
        before = len(card_ids)
        priced_ids: list[str] = []
        new_ids: list[str] = []
        for cid in card_ids:
            row = cards.get(cid) if isinstance(cards.get(cid), dict) else None
            if row is None:
                new_ids.append(cid)
            elif has_usable_price(row):
                priced_ids.append(cid)
        card_ids = list(dict.fromkeys([*priced_ids, *new_ids]))
        skipped = before - len(card_ids)
        print(
            f"每日筛选（priced-or-new）：总数 {before} → 待同步 {len(card_ids)}"
            f"（已有现价 {len(priced_ids)}，新卡 {len(new_ids)}，跳过无价 {skipped}）",
            flush=True,
        )
        if not card_ids:
            print("没有需要同步的卡号。")
            return

    if args.skip_ok or args.stale_hours > 0:
        before = len(card_ids)
        must: list[str] = []
        stale_ok: list[tuple[datetime, str]] = []
        stale_miss: list[tuple[datetime, str]] = []
        now = datetime.now(timezone.utc)
        stale_cutoff = (
            now.timestamp() - float(args.stale_hours) * 3600.0
            if args.stale_hours > 0
            else None
        )
        for cid in card_ids:
            row = cards.get(cid) if isinstance(cards.get(cid), dict) else None
            if row is None:
                must.append(cid)
                continue
            if has_ok_price(row):
                if args.skip_ok and not (args.stale_hours > 0):
                    continue
                if stale_cutoff is None:
                    continue
                checked = parse_iso_ts(row.get("last_checked"))
                if checked is None or checked.timestamp() <= stale_cutoff:
                    stale_ok.append((checked or datetime.fromtimestamp(0, tz=timezone.utc), cid))
                continue

            status = price_status(row)
            checked = parse_iso_ts(row.get("last_checked"))
            # Never-checked / soft errors: always include.
            if (not status) or status in RETRY_SOON_STATUSES or not checked:
                must.append(cid)
                continue
            if args.skip_ok and not (args.stale_hours > 0):
                # Classic gap-fill: include every non-ok.
                must.append(cid)
                continue
            # Hard misses: only rotate when stale.
            if is_hard_miss_status(status):
                if stale_cutoff is not None and (
                    checked is None or checked.timestamp() <= stale_cutoff
                ):
                    stale_miss.append((checked or datetime.fromtimestamp(0, tz=timezone.utc), cid))
                continue
            # Unknown non-ok: treat like soft retry.
            must.append(cid)

        stale_ok.sort(key=lambda x: x[0])
        stale_miss.sort(key=lambda x: x[0])
        if args.stale_limit and args.stale_limit > 0:
            stale_ok = stale_ok[: int(args.stale_limit)]
        if args.miss_limit and args.miss_limit > 0:
            stale_miss = stale_miss[: int(args.miss_limit)]
        elif args.stale_hours > 0 and not args.skip_ok:
            # Default cap for daily hard-miss rotation when miss-limit omitted.
            stale_miss = stale_miss[:200]
        stale_ok_ids = [cid for _, cid in stale_ok]
        stale_miss_ids = [cid for _, cid in stale_miss]
        card_ids = list(dict.fromkeys([*must, *stale_ok_ids, *stale_miss_ids]))
        print(
            f"增量筛选：总数 {before} → 待同步 {len(card_ids)}"
            f"（新卡/软错误 {len(must)}，过期 ok {len(stale_ok_ids)}，"
            f"过期硬 miss {len(stale_miss_ids)}）",
            flush=True,
        )
        if not card_ids:
            print("没有需要同步的卡号。")
            return

    session = requests.Session()
    session.trust_env = False
    setattr(fetch_price_from_yuyutei, "_html_cache", {})
    setattr(fetch_price_from_yuyutei, "_bulk_map", {})

    # searchSP 整页经常很慢/卡住；家族模式不依赖它，默认跳过以加快启动。
    if not args.by_family:
        print("预热 searchSP 批量价目（非家族模式）...", flush=True)
        try:
            searchsp_html, _ = request_html(session, SEARCH_SP_URL, timeout=12, retries=1)
            if searchsp_html:
                bulk_map = extract_bulk_prices_from_searchsp(searchsp_html)
                bulk_map = {
                    k: v
                    for k, v in bulk_map.items()
                    if isinstance(v, int) and v > 0 and not is_variant_card_id(k)
                }
                setattr(fetch_price_from_yuyutei, "_bulk_map", bulk_map)
                setattr(fetch_price_from_yuyutei, "_searchsp_cache", searchsp_html)
                print(f"searchSP 预热完成: {len(bulk_map)} 条基础价", flush=True)
            else:
                print("searchSP 预热失败，继续按卡抓取", flush=True)
        except requests.RequestException as exc:
            print(f"searchSP 预热异常: {exc}", flush=True)

    checked = 0
    found = 0
    not_found = 0
    errors = 0
    hit_429 = 0
    network_errors = 0

    batch_size = args.batch_size if args.batch_size and args.batch_size > 0 else 80
    batch_sleep = max(0.0, float(args.batch_sleep))
    retry_sleep_on_429 = max(0.0, float(args.retry_sleep_on_429))
    progress_every = max(1, int(args.progress_every))
    request_sleep = max(0.05, float(args.request_sleep))
    cooldown_on_429 = max(15.0, float(args.cooldown_on_429))
    adaptive_sleep = request_sleep
    consecutive_429 = 0

    miss_ids: list[str] = []

    def _record(card_id: str, price: int | None, status: str, ts: str) -> None:
        nonlocal found, not_found, errors, network_errors, hit_429, consecutive_429
        source_url = DEFAULT_SEARCH_TEMPLATES[0].format(query=quote_plus(base_card_id(card_id)))
        final_price, final_status = price, status
        if args.strict_variant and is_variant_card_id(card_id):
            allowed = {
                "ok_variant_imagehash",
                "ok_variant_id_exact",
                "ok_variant_detail",
                "ok_variant_single_parallel",
                "ok_variant_remainder_single",
            }
            # stamp-unstamped manga uses the same remainder status
            if args.allow_variant_heuristic:
                allowed.update({"ok_variant_heuristic", "ok_variant_loose", "ok_variant_regex"})
            if final_status not in allowed:
                final_price = None
                final_status = "variant_not_found_strict"
        cards[card_id] = merge_price_record(
            cards.get(card_id, {}),
            final_price,
            ts,
            source_url,
            reset_history=args.reset_history,
        )
        cards[card_id]["status"] = final_status
        if final_status.startswith("ok"):
            found += 1
            consecutive_429 = 0
        elif final_status in {"price_not_found", "variant_not_found", "variant_not_found_strict"}:
            not_found += 1
            miss_ids.append(card_id)
        elif final_status.startswith("request_error"):
            errors += 1
            network_errors += 1
            miss_ids.append(card_id)
        else:
            errors += 1
            miss_ids.append(card_id)
            if final_status == "http_429":
                hit_429 += 1
                # 家族模式由主循环做全局冷却，避免每张卡叠加长 sleep
                if not args.by_family:
                    consecutive_429 += 1
                    if retry_sleep_on_429 > 0:
                        sleep_s = min(
                            YUYUTEI_429_BACKOFF_CAP_SEC,
                            retry_sleep_on_429 * (2 ** min(consecutive_429 - 1, 3)),
                        )
                        time.sleep(sleep_s)
            else:
                consecutive_429 = 0

    # Group by base id for family fetch.
    families: dict[str, list[str]] = {}
    for cid in card_ids:
        families.setdefault(base_card_id(cid), []).append(cid)
    family_keys = sorted(families.keys())

    def _persist(label: str) -> None:
        # Long runs can race with other writers (e.g. sync_don_cards). Re-read disk and
        # keep any card rows we did not touch in this process so they are not wiped.
        on_disk = load_json(PRICE_PATH, {})
        disk_cards = on_disk.get("cards") if isinstance(on_disk, dict) else {}
        if isinstance(disk_cards, dict):
            for cid, row in disk_cards.items():
                if cid in cards or not isinstance(row, dict):
                    continue
                cards[cid] = row
        payload["source"] = "yuyu-tei"
        payload["updated_at"] = now_iso()
        payload["cards"] = cards
        PRICE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PRICE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(label)

    if args.by_family:
        print(f"家族模式：{len(family_keys)} 个基础卡号 / {len(card_ids)} 张卡", flush=True)
        print(
            f"限速：基础 sleep={request_sleep:.2f}s，429 冷却={cooldown_on_429:.0f}s",
            flush=True,
        )
        for start in range(0, len(family_keys), batch_size):
            batch_bases = family_keys[start:start + batch_size]
            for base in batch_bases:
                members = families[base]
                ts = now_iso()
                results = fetch_family_prices_from_yuyutei(
                    session,
                    members,
                    deep_variant_check=not args.two_pass,
                )
                for cid in members:
                    checked += 1
                    price, status = results.get(cid, (None, "price_not_found"))
                    _record(cid, price, status, ts)
                    if checked % progress_every == 0:
                        notify_progress(
                            f"进度: {checked}/{len(card_ids)} "
                            f"(ok={found}, miss={not_found}, err={errors}, 429={hit_429}, "
                            f"sleep={adaptive_sleep:.2f}s)"
                        )
                any_429 = any(st == "http_429" for _, st in results.values())
                if any_429:
                    consecutive_429 += 1
                    hit_429 += 1
                    adaptive_sleep = min(2.5, max(adaptive_sleep * 1.35, request_sleep + 0.15))
                    cool = min(
                        YUYUTEI_429_BACKOFF_CAP_SEC,
                        cooldown_on_429 * (1.0 + 0.35 * min(consecutive_429 - 1, 4)),
                    )
                    print(
                        f"[429] {base} → 冷却 {cool:.0f}s，之后 sleep={adaptive_sleep:.2f}s",
                        flush=True,
                    )
                    time.sleep(cool)
                else:
                    consecutive_429 = 0
                    # slowly relax after clean responses
                    adaptive_sleep = max(request_sleep, adaptive_sleep * 0.97)
                    time.sleep(adaptive_sleep)

            _persist(
                f"批次完成: {min(start + batch_size, len(family_keys))}/{len(family_keys)} 家族 "
                f"/ 卡 {checked}/{len(card_ids)} "
                f"(ok={found}, miss={not_found}, err={errors}, net_err={network_errors}, http_429={hit_429})"
            )
            notify_progress(
                f"批次完成: 卡 {checked}/{len(card_ids)} "
                f"(ok={found}, miss={not_found}, err={errors}, 429={hit_429})"
            )
            if start + batch_size < len(family_keys) and batch_sleep > 0:
                time.sleep(batch_sleep)
    else:
        for start in range(0, len(card_ids), batch_size):
            batch = card_ids[start:start + batch_size]
            for card_id in batch:
                checked += 1
                ts = now_iso()
                price, status = fetch_price_from_yuyutei(
                    session,
                    card_id,
                    deep_variant_check=not args.two_pass,
                )
                if args.debug_variant and is_variant_card_id(card_id):
                    trace = getattr(fetch_price_from_yuyutei, "_last_trace", [])
                    print(f"[debug] {card_id} final_status={status} price={price}")
                    for row in trace:
                        print(f"[debug] {row}")
                _record(card_id, price, status, ts)
                time.sleep(request_sleep if str(status).startswith("ok") else max(request_sleep, 0.25))
                if checked % progress_every == 0:
                    notify_progress(
                        f"进度: {checked}/{len(card_ids)} "
                        f"(ok={found}, miss={not_found}, err={errors}, 429={hit_429})"
                    )

            _persist(
                f"批次完成: {min(start + batch_size, len(card_ids))}/{len(card_ids)} "
                f"(ok={found}, miss={not_found}, err={errors}, net_err={network_errors}, http_429={hit_429})"
            )
            if start + batch_size < len(card_ids) and batch_sleep > 0:
                time.sleep(batch_sleep)

    if args.two_pass and miss_ids:
        retry_ids = [cid for cid in dict.fromkeys(miss_ids) if is_variant_card_id(cid)]
        print(f"二阶段重试开始: {len(retry_ids)} 张 miss 异图卡")
        retry_families: dict[str, list[str]] = {}
        for cid in retry_ids:
            retry_families.setdefault(base_card_id(cid), []).append(cid)
        done = 0
        for _base, members in sorted(retry_families.items()):
            ts = now_iso()
            results = fetch_family_prices_from_yuyutei(
                session,
                members,
                deep_variant_check=True,
            )
            for cid in members:
                done += 1
                price, status = results.get(cid, (None, "variant_not_found"))
                old_status = str((cards.get(cid) or {}).get("status") or "")
                if old_status.startswith("ok"):
                    found = max(0, found - 1)
                elif old_status in {"price_not_found", "variant_not_found", "variant_not_found_strict"}:
                    not_found = max(0, not_found - 1)
                else:
                    errors = max(0, errors - 1)
                _record(cid, price, status, ts)
                if done % progress_every == 0 or done == len(retry_ids):
                    notify_progress(f"二阶段细进度: {done}/{len(retry_ids)}")
            time.sleep(request_sleep)
            if done % 100 == 0 or done == len(retry_ids):
                _persist(f"二阶段进度: {done}/{len(retry_ids)}")

    # Final write: same preserve-on-disk merge as _persist.
    on_disk = load_json(PRICE_PATH, {})
    disk_cards = on_disk.get("cards") if isinstance(on_disk, dict) else {}
    if isinstance(disk_cards, dict):
        for cid, row in disk_cards.items():
            if cid in cards or not isinstance(row, dict):
                continue
            cards[cid] = row
    payload["source"] = "yuyu-tei"
    payload["updated_at"] = now_iso()
    payload["cards"] = cards
    PRICE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRICE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Recompute final stats after optional second pass.
    final_found = 0
    final_not_found = 0
    final_errors = 0
    for cid in card_ids:
        st = str(cards.get(cid, {}).get("status") or "")
        if st.startswith("ok"):
            final_found += 1
        elif st in {"price_not_found", "variant_not_found_strict"}:
            final_not_found += 1
        else:
            final_errors += 1

    print(f"总检查: {checked}")
    print(f"找到价格: {final_found}")
    print(f"未找到价格: {final_not_found}")
    print(f"请求错误: {final_errors}")
    print(f"网络错误: {network_errors}")
    print(f"429 次数: {hit_429}")
    print(f"输出文件: {PRICE_PATH}")


if __name__ == "__main__":
    main()

