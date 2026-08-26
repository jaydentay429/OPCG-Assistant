#!/usr/bin/env python3
"""Sync illustrated DON!! cards from yuyu-tei into index/cards_by_id.json + packs/ + market_prices.json.

Official Bandai cardlist does not catalog per-card DON art; yuyu-tei hosts scan-quality images
at card.yuyu-tei.jp/opc/front/{set}/{num}.jpg which we treat as the canonical art source.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
INDEX_PATH = BASE_DIR / "index" / "cards_by_id.json"
PACKS_DIR = BASE_DIR / "packs"
PRICE_PATH = BASE_DIR / "meta" / "market_prices.json"
SEARCH_URL = "https://yuyu-tei.jp/sell/opc/s/search?search_word={query}"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) OPCG-DonSync/1.0",
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
}
_YEN_RE = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})*)\s*円")
_PARALLEL_RE = re.compile(r"パラレル|PARALLEL", re.IGNORECASE)
_SUPER_PARALLEL_RE = re.compile(r"スーパーパラレル|SUPER\s*PARALLEL", re.IGNORECASE)
_DON_NAME_RE = re.compile(r"^ドン!!カード\s*(.*)$")
_SOURCE_HINT_RE = re.compile(
    r"(パック|大会|イベント|記念|プロモ|PROMO|ANNIVERSARY|BOX|Vol\.?|チャンピオンシップ|スタンダードバトル)",
    re.IGNORECASE,
)
_PARALLEL_TAG_RE = re.compile(r"^\(?\s*(スーパーパラレル|パラレル)\s*\)?$", re.IGNORECASE)

# JP subtitle → (zh-Hant, en)
DON_SUBTITLE_I18N: dict[str, tuple[str, str]] = {
    "ナミ": ("娜美", "Nami"),
    "ニコ・ロビン": ("妮可・羅賓", "Nico Robin"),
    "ウタ": ("烏塔", "Uta"),
    "ボア・ハンコック": ("波雅・漢考克", "Boa Hancock"),
    "ポートガス・D・エース": ("波特卡斯・D・艾斯", "Portgas D. Ace"),
    "ネフェルタリ・ビビ": ("娜菲魯塔利・薇薇", "Nefertari Vivi"),
    "クロコダイル": ("克洛克達爾", "Crocodile"),
    "ドンキホーテ・ドフラミンゴ": ("唐吉訶德・多佛朗明哥", "Donquixote Doflamingo"),
    "ドンキホーテ・ロシナンテ": ("唐吉訶德・羅西南迪", "Donquixote Rosinante"),
    "エネル": ("艾尼路", "Enel"),
    "ホーディ・ジョーンズ": ("荷帝・瓊斯", "Hody Jones"),
    "アイスバーグ": ("冰山", "Iceburg"),
    "エンポリオ・イワンコフ": ("艾波利奧・伊凡科夫", "Emporio Ivankov"),
    "カイドウ": ("凱多", "Kaido"),
    "ロブ・ルッチ": ("羅布・路基", "Rob Lucci"),
    "ヤマト": ("大和", "Yamato"),
    "ウソップ": ("烏索普", "Usopp"),
    "サンジ": ("香吉士", "Sanji"),
    "トニートニー・チョッパー": ("多尼多尼・喬巴", "Tony Tony.Chopper"),
    "ジンベエ": ("甚平", "Jinbe"),
    "トラファルガー・ロー": ("托拉法爾加・羅", "Trafalgar Law"),
    "ロロノア・ゾロ": ("羅羅亞・索隆", "Roronoa Zoro"),
    "モンキー・D・ルフィ": ("蒙其・D・魯夫", "Monkey D. Luffy"),
    "モンキー・D・ルフィ ギア4": ("蒙其・D・魯夫 4檔", "Monkey D. Luffy Gear 4"),
    "モンキー・D・ルフィ ギア5": ("蒙其・D・魯夫 5檔", "Monkey D. Luffy Gear 5"),
    "モンキー・D・ドラゴン": ("蒙其・D・龍", "Monkey D. Dragon"),
    "モンキー・Dガープ＆モンキー・D・ルフィ(10年前": ("蒙其・D・卡普＆蒙其・D・魯夫（10年前）", "Monkey D. Garp & Monkey D. Luffy (10 years ago)"),
    "シャンクス": ("香克斯", "Shanks"),
    "サボ": ("薩波", "Sabo"),
    "サカズキ": ("赤犬", "Sakazuki"),
    "スモーカー": ("斯摩格", "Smoker"),
    "マルコ": ("馬爾科", "Marco"),
    "マーシャル・D・ティーチ": ("馬歇爾・D・汀奇", "Marshall D. Teach"),
    "エドワード・ニューゲート": ("艾德華・紐蓋特", "Edward Newgate"),
    "シャーロット・リンリン": ("夏洛特・玲玲", "Charlotte Linlin"),
    "シャーロット・カタクリ": ("夏洛特・卡塔克利", "Charlotte Katakuri"),
    "シャーロット・プリン": ("夏洛特・布琳", "Charlotte Pudding"),
    "ジュエリー・ボニー": ("珠寶・波妮", "Jewelry Bonney"),
    "ユースタス・キッド": ("尤斯塔斯・基德", "Eustass Kid"),
    "レベッカ": ("蕾貝卡", "Rebecca"),
    "ペローナ": ("培羅娜", "Perona"),
    "バギー": ("巴基", "Buggy"),
    "フォクシー": ("佛克西", "Foxy"),
    "シュガー": ("砂糖", "Sugar"),
    "シーザー": ("凱薩", "Caesar"),
    "キング": ("King", "King"),
    "クイーン": ("Queen", "Queen"),
    "キャロット": ("蘿蔔", "Carrot"),
    "キュロス": ("居洛斯", "Kyros"),
    "コビー": ("柯比", "Koby"),
    "カルガラ": ("卡爾葛拉", "Calgara"),
    "ゲッコー・モリア": ("月光・摩利亞", "Gecko Moria"),
    "ベガパンク": ("貝加龐克", "Vegapunk"),
    "マゼラン": ("麥哲倫", "Magellan"),
    "ハンニャバル": ("漢尼拔", "Hannyabal"),
    "ヴィンスモーク・レイジュ": ("文斯莫克・蕾玖", "Vinsmoke Reiju"),
    "光月おでん": ("光月御田", "Kozuki Oden"),
    "しらほし": ("白星", "Shirahoshi"),
    "リム": ("莉姆", "Lilith"),
    "インペルダウン": ("推進城", "Impel Down"),
    "EGG HEAD": ("蛋頭島", "Egghead"),
    "ロックス海賊団": ("洛克斯海賊團", "Rocks Pirates"),
    "旧四皇": ("舊四皇", "Former Four Emperors"),
    "ルフィ＆ロキ": ("魯夫＆洛基", "Luffy & Loki"),
    "ルフィVSカイドウ": ("魯夫 VS 凱多", "Luffy vs Kaido"),
    '海賊"王下七武海"': ("海賊「王下七武海」", 'Pirate "Seven Warlords of the Sea"'),
    "世界最強の剣士\"鷹の目のミホーク”": ("世界最強的劍士「鷹眼密佛格」", 'World\'s Strongest Swordsman "Hawk-Eye Mihawk"'),
    "ナミモチーフ": ("娜美圖案", "Nami motif"),
    "ルフィモチーフ": ("魯夫圖案", "Luffy motif"),
    "ゾロモチーフ": ("索隆圖案", "Zoro motif"),
    "ウソップモチーフ": ("烏索普圖案", "Usopp motif"),
    "サンジモチーフ": ("香吉士圖案", "Sanji motif"),
    "チョッパーモチーフ": ("喬巴圖案", "Chopper motif"),
    "ロビンモチーフ": ("羅賓圖案", "Robin motif"),
    "フランキーモチーフ": ("佛朗基圖案", "Franky motif"),
    "ブルックモチーフ": ("布魯克圖案", "Brook motif"),
    "ジンベエモチーフ": ("甚平圖案", "Jinbe motif"),
    "箔押し": ("燙金", "Foil stamped"),
    "金文字白背景/白背景裏面": ("金字白底／白底背面", "Gold text on white / white back"),
    "黒文字白背景/白背景裏面": ("黑字白底／白底背面", "Black text on white / white back"),
    "赤文字黒背景/白背景裏面": ("紅字黑底／白底背面", "Red text on black / white back"),
    "黒文字白背景/ホロ銀あり": ("黑字白底／銀色全息", "Black text on white / silver holo"),
    "黒文字白背景/ホロ虹あり": ("黑字白底／彩虹全息", "Black text on white / rainbow holo"),
    "黒文字白背景/ONE PIECE FILM RED裏面": ("黑字白底／FILM RED 背面", "Black text on white / FILM RED back"),
    "3rd ANNIVERSARY SET": ("3rd ANNIVERSARY SET", "3rd ANNIVERSARY SET"),
    "ONE PIECE DAY’24": ("ONE PIECE DAY’24", "ONE PIECE DAY’24"),
    "海賊王におれはなる!!!!": ("我要成為海賊王!!!!", "I'm gonna be King of the Pirates!!!!"),
    "「四皇」はおれが全部倒すつもりだから!!!": ("「四皇」我打算全部打倒!!!", "I'll take down all the Four Emperors!!!"),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slug_to_card_id(slug: str) -> str:
    set_part, num = str(slug or "").strip().lower().split("/", 1)
    if set_part == "don":
        prefix = "DON00"
    elif set_part.startswith("op"):
        prefix = f"DON{set_part[2:]}"
    elif set_part.startswith("eb"):
        prefix = f"DONEB{set_part[2:]}"
    elif set_part.startswith("prb"):
        prefix = f"DONPRB{set_part[3:]}"
    else:
        prefix = f"DON{set_part.upper()}"
    return f"{prefix}-{num}"


def slug_to_pack_id(slug: str) -> str:
    set_part, _ = str(slug or "").strip().lower().split("/", 1)
    if set_part == "don":
        return "DON"
    m = re.match(r"^(op|eb|prb)(\d{2})$", set_part)
    if m:
        return f"{m.group(1).upper()}-{int(m.group(2))}"
    return set_part.upper()


def classify_don_rarity(name: str) -> str:
    """Only two DON rarities: Gold DON (super parallel) and DON (all others)."""
    text = str(name or "")
    if _SUPER_PARALLEL_RE.search(text):
        return "Gold DON"
    return "DON"


def _split_don_subtitle(raw_subtitle: str) -> tuple[str, list[str]]:
    """Split core subtitle and trailing parallel tags from yuyu-tei naming."""
    text = str(raw_subtitle or "").strip().strip("()- ")
    tags: list[str] = []
    while True:
        m = re.search(r"(?:\)?\(|（)?\s*(スーパーパラレル|パラレル)\s*(?:\)|）)?\s*$", text)
        if not m:
            break
        tags.append(m.group(1))
        text = text[: m.start()].rstrip("()（） ")
    if ")(" in text:
        head, *rest = text.split(")(")
        text = head.strip("() ")
        for part in rest:
            part = part.strip("() ")
            pm = _PARALLEL_TAG_RE.match(part)
            if pm:
                tags.append(pm.group(1))
            elif part and part not in text:
                text = f"{text}/{part}" if text else part
    return text.strip(), tags


def _translate_don_tag(tag: str, *, lang: str) -> str:
    key = str(tag or "").strip()
    if key == "スーパーパラレル":
        return {"en": "Super Parallel", "hans": "超级平行"}.get(lang, "超級平行")
    if key == "パラレル":
        return {"en": "Parallel", "hans": "平行"}.get(lang, "平行")
    return key


def _translate_don_core(core: str) -> tuple[str, str]:
    text = str(core or "").strip()
    if not text:
        return "", ""
    if text in DON_SUBTITLE_I18N:
        return DON_SUBTITLE_I18N[text]
    if text.endswith("モチーフ"):
        base = text[: -len("モチーフ")]
        zh, en = _translate_don_core(base)
        if zh != base or en != base:
            return (f"{zh}圖案" if zh else text, f"{en} motif" if en else text)
    return text, text


def don_display_name(name_jp: str) -> tuple[str, str]:
    """Return (zh-Hant name, English name) for a yuyu-tei DON product title."""
    raw = str(name_jp or "").strip()
    m = _DON_NAME_RE.match(raw)
    subtitle = (m.group(1).strip() if m else raw).strip()
    # Prefer segmenting all (...) groups: (箔押し)(金文字...)(パラレル)
    segments = [s.strip() for s in re.findall(r"\(([^()]*)\)", subtitle) if str(s).strip()]
    if not segments:
        core, tags = _split_don_subtitle(subtitle)
        segments = [core, *tags] if core or tags else ([subtitle] if subtitle else [])
    zh_bits: list[str] = []
    en_bits: list[str] = []
    for seg in segments:
        if _PARALLEL_TAG_RE.match(seg):
            zh_bits.append(_translate_don_tag(seg, lang="hant"))
            en_bits.append(_translate_don_tag(seg, lang="en"))
            continue
        zh_core, en_core = _translate_don_core(seg)
        if zh_core:
            zh_bits.append(zh_core)
        if en_core:
            en_bits.append(en_core)
    name_zh = "咚卡・" + "・".join(zh_bits) if zh_bits else "咚卡"
    name_en = f"DON!! Card ({' / '.join(en_bits)})" if en_bits else "DON!! Card"
    return name_zh, name_en


def extract_don_source_labels(name_jp: str) -> list[str]:
    """Extract explicit source text from yuyu-tei card name when present."""
    raw = str(name_jp or "").strip()
    if not raw:
        return []
    labels: list[str] = []
    for m in re.finditer(r"\(([^()]{2,120})\)", raw):
        text = str(m.group(1) or "").strip()
        if not text:
            continue
        if not _SOURCE_HINT_RE.search(text):
            continue
        if text not in labels:
            labels.append(text)
    return labels


def _pack_code_keys(code: str) -> list[str]:
    text = str(code or "").strip().upper().replace(" ", "")
    if not text:
        return []
    keys = [text]
    m = re.match(r"^(OP|EB|ST|PRB)-?(\d+)$", text)
    if m:
        prefix, num = m.group(1), int(m.group(2))
        keys.extend([f"{prefix}-{num}", f"{prefix}{num:02d}", f"{prefix}-{num:02d}"])
    out: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def build_official_set_label_map(index: dict[str, Any]) -> dict[str, str]:
    """Map OP-17 / PRB01 / EB03 → Traditional Chinese official card_sets label."""
    out: dict[str, str] = {}
    for cid, row in index.items():
        if str(cid).upper().startswith("DON"):
            continue
        if not isinstance(row, dict):
            continue
        for label in row.get("card_sets") or []:
            text = str(label).strip()
            if not text:
                continue
            m = re.search(r"【([^】]+)】", text)
            if not m:
                continue
            for key in _pack_code_keys(m.group(1)):
                out.setdefault(key, text)
    return out


def parse_set_page_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    # "[OP17]世界最強の戦士 | シングルカード販売 | ..."
    head = title.split("|", 1)[0].strip()
    head = re.sub(r"\s*販売\s*$", "", head).strip()
    return head


def fetch_yuyutei_set_titles(session: requests.Session, set_parts: set[str]) -> dict[str, str]:
    """Fetch yuyu-tei set listing titles once per slug prefix (op17/prb01/don...)."""
    out: dict[str, str] = {}
    for set_part in sorted(set_parts):
        key = str(set_part or "").strip().lower()
        if not key:
            continue
        url = f"https://yuyu-tei.jp/sell/opc/s/{key}"
        try:
            resp = session.get(url, headers=REQUEST_HEADERS, timeout=30)
            if resp.status_code != 200 or not resp.text.strip():
                continue
            title = parse_set_page_title(resp.text)
            if title:
                out[key] = title
        except requests.RequestException:
            continue
        time.sleep(0.05)
    return out


def parse_detail_breadcrumb_set(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for sc in soup.select('script[type="application/ld+json"]'):
        raw = sc.string or sc.get_text() or ""
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("@type") != "BreadcrumbList":
            continue
        items = data.get("itemListElement") or []
        if len(items) < 3 or not isinstance(items[2], dict):
            continue
        name = str(items[2].get("name") or "").strip()
        name = re.sub(r"\s*販売\s*$", "", name).strip()
        return name
    return ""


def fetch_detail_set_labels(
    session: requests.Session,
    items: list[dict[str, Any]],
    *,
    only_generic: bool = True,
) -> dict[str, str]:
    """Scrape product-page breadcrumb set label. By default only for generic /don/ cards."""
    out: dict[str, str] = {}
    for item in items:
        slug = str(item.get("slug") or "")
        set_part = slug.split("/", 1)[0].lower() if slug else ""
        if only_generic and set_part != "don":
            continue
        url = str(item.get("detail_url") or "").strip()
        if not url:
            continue
        try:
            resp = session.get(url, headers=REQUEST_HEADERS, timeout=30)
            if resp.status_code != 200 or not resp.text.strip():
                continue
            label = parse_detail_breadcrumb_set(resp.text)
            if label:
                out[str(item.get("card_id") or "")] = label
        except requests.RequestException:
            continue
        time.sleep(0.05)
    return out


def resolve_don_card_sets(
    item: dict[str, Any],
    *,
    official_set_map: dict[str, str],
    set_titles: dict[str, str],
    detail_sets: dict[str, str],
) -> list[str]:
    """Prefer official Chinese set label; fall back to yuyu-tei set/product title + name hints."""
    labels: list[str] = []
    slug = str(item.get("slug") or "").strip().lower()
    set_part = slug.split("/", 1)[0] if slug else ""
    card_id = str(item.get("card_id") or "")

    # 1) Name-embedded explicit product (anniversary / battle pack / promo...).
    for label in extract_don_source_labels(str(item.get("name_jp") or "")):
        if label not in labels:
            labels.append(label)

    # 2) Map slug set → official TC card_sets (from Bandai-synced non-DON cards).
    if set_part and set_part != "don":
        for key in _pack_code_keys(set_part):
            official = official_set_map.get(key)
            if official:
                if official not in labels:
                    labels.insert(0, official)
                break
        else:
            jp_title = set_titles.get(set_part) or ""
            if jp_title and jp_title not in labels:
                labels.insert(0, jp_title)

    # 3) Product-page breadcrumb (useful for /don/ generics and verification).
    crumb = detail_sets.get(card_id) or ""
    if crumb and crumb not in {"ドン!!カード", "ドン!!カード 販売"} and crumb not in labels:
        labels.append(crumb)

    # 4) Generic DON category with no better source.
    if set_part == "don" and not labels:
        labels.append("通用咚卡")

    return labels


def front_image_url(thumb_url: str) -> str:
    text = str(thumb_url or "").strip()
    if not text:
        return ""
    if text.startswith("//"):
        text = "https:" + text
    text = text.replace("/100_140/", "/front/")
    if "/front/" not in text:
        m = re.search(r"card\.yuyu-tei\.jp/opc/(?:100_140|front)/([a-z0-9]+/[0-9]+)\.(?:jpg|png|webp)", text, re.I)
        if m:
            text = f"https://card.yuyu-tei.jp/opc/front/{m.group(1)}.jpg"
    return text


def fetch_search_html(session: requests.Session, query: str = "ドン!!カード") -> str:
    url = SEARCH_URL.format(query=quote_plus(query))
    resp = session.get(url, headers=REQUEST_HEADERS, timeout=45)
    resp.raise_for_status()
    return resp.text


def parse_don_products(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for prod in soup.select(".card-product"):
        text = prod.get_text(" ", strip=True)
        if "ドン!!カード" not in text:
            continue
        link = prod.select_one('a[href*="/sell/opc/card/"]')
        if not link:
            continue
        href = str(link.get("href") or "")
        m = re.search(r"/sell/opc/card/([a-z0-9]+/[0-9]+)", href)
        if not m:
            continue
        slug = m.group(1)
        if slug in seen:
            continue
        seen.add(slug)
        name_el = prod.select_one(".text-primary.fw-bold")
        name_jp = name_el.get_text(" ", strip=True) if name_el else ""
        if not name_jp:
            alt = prod.select_one("img[alt]")
            name_jp = str(alt.get("alt") or "").strip() if alt else ""
        price = None
        price_el = prod.select_one("strong.d-block.text-end")
        price_txt = price_el.get_text(" ", strip=True) if price_el else text
        pm = _YEN_RE.search(price_txt)
        if pm:
            try:
                price = int(pm.group(1).replace(",", ""))
            except ValueError:
                price = None
        img_url = ""
        for img in prod.find_all("img"):
            src = str(img.get("data-src") or img.get("src") or "").strip()
            if "card.yuyu-tei.jp/opc/" in src:
                img_url = src if src.startswith("http") else urljoin("https://yuyu-tei.jp/", src)
                break
        classes = prod.get("class") or []
        in_stock = "sold-out" not in classes
        card_id = slug_to_card_id(slug)
        name_zh, name_en = don_display_name(name_jp)
        out.append(
            {
                "card_id": card_id,
                "slug": slug,
                "name_jp": name_jp,
                "name": name_zh,
                "name_en": name_en,
                "rarity": classify_don_rarity(name_jp),
                "price": price,
                "in_stock": in_stock,
                "thumb_url": img_url,
                "front_url": front_image_url(img_url),
                "detail_url": urljoin("https://yuyu-tei.jp/", href),
            }
        )
    out.sort(key=lambda row: row["card_id"])
    return out


def host_series_from_card_id(card_id: str) -> str:
    """DON17 → OP17, DONEB03 → EB03, DONPRB01 → PRB01, DON00 → ''."""
    text = str(card_id or "").strip().upper()
    if text.startswith("DON00-") or text == "DON00":
        return ""
    m = re.match(r"^DON(?:EB|PRB)?(\d{2})-", text)
    if not m:
        return text.split("-", 1)[0]
    num = m.group(1)
    if text.startswith("DONEB"):
        return f"EB{num}"
    if text.startswith("DONPRB"):
        return f"PRB{num}"
    return f"OP{num}"


def build_index_row(item: dict[str, Any]) -> dict[str, Any]:
    card_id = item["card_id"]
    slug = item["slug"]
    pack_id = slug_to_pack_id(slug)
    series = host_series_from_card_id(card_id)
    packs_url = f"https://api.optcgassistant.com/packs/{card_id}.png"
    source_labels = [str(x).strip() for x in (item.get("card_sets") or []) if str(x).strip()]
    if not source_labels:
        source_labels = extract_don_source_labels(str(item.get("name_jp") or ""))
    return {
        "card_id": card_id,
        "name": item["name"],
        "name_en": item["name_en"],
        "name_jp": item.get("name_jp") or "",
        "category": "Don",
        "card_type": "Don",
        "category_en": "DON card",
        "card_type_en": "DON card",
        "rarity": item.get("rarity") or "DON",
        "colors": [],
        "colors_en": [],
        "cost": None,
        "power": None,
        "counter": None,
        "life": None,
        "block_number": None,
        "traits": [],
        "traits_en": [],
        "attributes": [],
        "attributes_en": [],
        "card_sets": source_labels,
        "effect": "",
        "effect_en": "",
        "pack_id": pack_id,
        "series": series,
        "yuyutei_slug": slug,
        "yuyutei_url": item.get("detail_url") or "",
        "img_url": packs_url,
        "img_full_url": packs_url,
        "img_source_url": item.get("front_url") or "",
    }


def download_image(session: requests.Session, url: str, dest: Path) -> bool:
    if not url:
        return False
    try:
        resp = session.get(url, headers=REQUEST_HEADERS, timeout=45)
        resp.raise_for_status()
        data = resp.content
        if len(data) < 500:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Normalize to PNG when possible.
        try:
            from PIL import Image

            im = Image.open(BytesIO(data))
            im.save(dest, format="PNG")
        except Exception:
            dest.write_bytes(data)
        return True
    except requests.RequestException:
        return False


def merge_prices(items: list[dict[str, Any]], ts: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": "yuyu-tei",
        "updated_at": ts,
        "cards": {},
    }
    if PRICE_PATH.exists():
        try:
            raw = json.loads(PRICE_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                payload.update({k: v for k, v in raw.items() if k not in {"cards"} and not str(k).startswith("DON")})
                cards = raw.get("cards")
                if isinstance(cards, dict):
                    payload["cards"] = dict(cards)
                # Recover from earlier flat DON writes at root.
                for key, val in raw.items():
                    if str(key).startswith("DON") and isinstance(val, dict):
                        payload["cards"][str(key)] = val
        except (OSError, json.JSONDecodeError):
            pass
    cards = payload.setdefault("cards", {})
    if not isinstance(cards, dict):
        cards = {}
        payload["cards"] = cards
    for item in items:
        cid = item["card_id"]
        price = item.get("price")
        if price is None:
            continue
        prev = cards.get(cid) if isinstance(cards.get(cid), dict) else {}
        history = prev.get("history") if isinstance(prev.get("history"), list) else []
        if not history or history[-1].get("price") != price:
            history = history + [{"ts": ts, "price": price}]
            history = history[-30:]
        cards[cid] = {
            "source": "yuyu-tei",
            "currency": "JPY",
            "current_price": price,
            "last_checked": ts,
            "last_seen": ts,
            "history": history,
            "status": "ok_don_detail",
            "yuyutei_url": item.get("detail_url") or "",
        }
    payload["updated_at"] = ts
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync DON!! cards from yuyu-tei into local index/packs/prices.")
    parser.add_argument("--dry-run", action="store_true", help="Parse only; do not write files or download images.")
    parser.add_argument("--skip-images", action="store_true", help="Update index/prices but skip image downloads.")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of cards (debug).")
    args = parser.parse_args()

    session = requests.Session()
    session.trust_env = False
    html = fetch_search_html(session)
    items = parse_don_products(html)
    if args.limit and args.limit > 0:
        items = items[: args.limit]

    print(f"Parsed {len(items)} DON cards from yuyu-tei")
    if not items:
        raise SystemExit("No DON cards found.")

    index = {}
    if INDEX_PATH.exists():
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    if not isinstance(index, dict):
        raise SystemExit("cards_by_id.json must be a dict")

    official_set_map = build_official_set_label_map(index)
    set_parts = {
        str(item.get("slug") or "").split("/", 1)[0].lower()
        for item in items
        if str(item.get("slug") or "").strip()
    }
    print(f"Fetching yuyu-tei set titles for {len(set_parts)} sets...")
    set_titles = fetch_yuyutei_set_titles(session, set_parts)
    print(f"  set titles: {len(set_titles)}")
    print("Fetching product-page breadcrumbs for generic DON cards...")
    detail_sets = fetch_detail_set_labels(session, items, only_generic=True)
    print(f"  detail breadcrumbs: {len(detail_sets)}")

    for item in items:
        item["card_sets"] = resolve_don_card_sets(
            item,
            official_set_map=official_set_map,
            set_titles=set_titles,
            detail_sets=detail_sets,
        )

    added = updated = 0
    downloaded = skipped = 0
    ts = now_iso()
    for item in items:
        cid = item["card_id"]
        row = build_index_row(item)
        if cid in index:
            # Preserve any manual overrides; refresh sync fields.
            current = index[cid]
            current.update(row)
            index[cid] = current
            updated += 1
        else:
            index[cid] = row
            added += 1
        if args.dry_run or args.skip_images:
            continue
        dest = PACKS_DIR / f"{cid}.png"
        if dest.exists() and dest.stat().st_size > 500:
            skipped += 1
            continue
        ok = download_image(session, item.get("front_url") or "", dest)
        if ok:
            downloaded += 1
        else:
            print(f"  image fail {cid} {item.get('front_url')}")
        time.sleep(0.08)

    if args.dry_run:
        for item in items[:8]:
            print(json.dumps({"id": item["card_id"], "sets": item.get("card_sets"), "name": item.get("name_jp")}, ensure_ascii=False))
        with_sets = sum(1 for i in items if i.get("card_sets"))
        print(f"dry-run: would add {added}, update {updated}; with sources {with_sets}/{len(items)}")
        return

    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prices = merge_prices(items, ts)
    PRICE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRICE_PATH.write_text(json.dumps(prices, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cards = prices.get("cards") if isinstance(prices.get("cards"), dict) else {}
    with_sets = sum(1 for i in items if i.get("card_sets"))
    print(f"Index: +{added} new, ~{updated} updated -> {INDEX_PATH}")
    print(f"Sources: {with_sets}/{len(items)} DON cards have card_sets")
    print(f"Images: downloaded {downloaded}, skipped {skipped}")
    print(f"Prices: wrote {sum(1 for i in items if i.get('price') is not None)} DON rows -> {PRICE_PATH} ({len(cards)} total priced cards)")


if __name__ == "__main__":
    main()
