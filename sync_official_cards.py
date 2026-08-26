from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
INDEX_PATH = BASE_DIR / "index" / "cards_by_id.json"
SNAPSHOT_DIR = BASE_DIR / "cards" / "official_sync"
SNAPSHOT_PATH = SNAPSHOT_DIR / "latest_cards.json"

OFFICIAL_TC_URL = "https://asia-tc.onepiece-cardgame.com/cardlist/"
OFFICIAL_EN_URL = "https://asia-en.onepiece-cardgame.com/cardlist/"
OFFICIAL_CARDLIST_URLS = [OFFICIAL_TC_URL, OFFICIAL_EN_URL]
PUBLIC_API_BASE = "https://optcg-api.arjunbansal-ai.workers.dev"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) OPCG-OfficialSync/1.0",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}
JAPANESE_IMAGE_HOST = "https://www.onepiece-cardgame.com/"

ID_LINE_RE = re.compile(
    r"^([A-Z]{2,4}-?\d{2}-\d{3}(?:-[A-Z0-9]+)?)\s*\|\s*([^|]*)\|\s*(.*)$"
)
CARD_ID_RE = re.compile(r"^[A-Z]{2,4}-?\d{2}-\d{3}(?:-[A-Z0-9]+)?$")
HEADING_KEYS = {
    "Life": "life",
    "Attribute": "attribute",
    "Power": "power",
    "Counter": "counter",
    "Color": "color",
    "Block Icon": "block_icon",
    "Type": "type",
    "Effect": "effect",
    "Trigger": "trigger",
    "觸發器": "trigger",
    "触发器": "trigger",
    "Card Set(s)": "card_sets",
}


def normalize_rarity(raw: str) -> str:
    """Canonical rarities: Gold DON / DON for DON cards; SP卡 → SP."""
    text = str(raw or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in {"DON-SP", "GOLD DON", "GOLD-DON", "GOLDDON"}:
        return "Gold DON"
    if upper in {"DON", "DON-P", "DONP"}:
        return "DON"
    if upper == "SP" or text == "SP卡":
        return "SP"
    return text


def strip_field_label(text: str, labels: tuple[str, ...]) -> str:
    out = str(text or "").strip()
    for label in labels:
        if out.startswith(label):
            out = out[len(label) :].strip()
            # optional colon / fullwidth colon
            out = out.lstrip(":：").strip()
    return out


def compose_effect_with_trigger(effect: str, trigger: str) -> str:
    """Append official Trigger text to Effect when the site stores them separately."""
    effect = str(effect or "").strip()
    trigger = str(trigger or "").strip()
    if not trigger:
        return effect
    trigger = strip_field_label(trigger, ("Trigger", "觸發器", "触发器"))
    if not trigger:
        return effect
    # Already present (full line or keyword body).
    if trigger in effect:
        return effect
    if not effect:
        return trigger
    return f"{effect}\n{trigger}"


def normalize_card_id(raw: str) -> str:
    text = str(raw or "").strip().upper().replace("_", "-").replace(" ", "")
    text = text.replace("－", "-")
    text = re.sub(r"[^A-Z0-9-]", "", text)
    m = re.match(r"^([A-Z]{2,4})-?(\d{2})-(\d{3}(?:-[A-Z0-9]+)?)$", text)
    if m:
        text = f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    return text


def base_card_id(card_id: str) -> str:
    text = normalize_card_id(card_id)
    m = re.match(r"^([A-Z]{2,4}\d{2}-\d{3})", text)
    return m.group(1) if m else text


def drop_underscore_alias_keys(index: dict[str, Any]) -> int:
    """Remove ST22-001_p1-style duplicate keys when ST22-001-P1 already exists."""
    removed = 0
    for cid in list(index.keys()):
        if "_" not in str(cid):
            continue
        normalized = normalize_card_id(cid)
        if normalized != str(cid) and (normalized in index or base_card_id(normalized) in index):
            index.pop(cid, None)
            removed += 1
    return removed


def safe_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "—"}:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def split_multi(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    parts = re.split(r"[,/]+", text)
    return [p.strip() for p in parts if p.strip()]


@dataclass
class ParsedCard:
    card_id: str
    rarity: str = ""
    card_type: str = ""
    name: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    card_sets: list[str] = field(default_factory=list)
    image_candidates: list[str] = field(default_factory=list)

    def score(self) -> int:
        score = 0
        if self.name:
            score += 1
        for key in ("effect", "power", "color", "type"):
            if self.fields.get(key):
                score += 1
        if self.image_candidates:
            score += 1
        return score


def _union_card_sets(*groups: list[str]) -> list[str]:
    out: list[str] = []
    for group in groups:
        for item in group or []:
            text = str(item).strip()
            if text and text not in out:
                out.append(text)
    return out


def merge_parsed_cards(base: dict[str, ParsedCard], extra: dict[str, ParsedCard]) -> dict[str, ParsedCard]:
    """Merge series crawls. Same id across series keeps richer text and unions getInfo."""
    merged = dict(base)
    for cid, card in extra.items():
        old = merged.get(cid)
        if old is None:
            merged[cid] = card
            continue
        sets = _union_card_sets(old.card_sets, card.card_sets)
        if card.score() >= old.score():
            card.card_sets = sets
            merged[cid] = card
        else:
            old.card_sets = sets
    return merged


def extract_get_info_lines(node: Any) -> list[str]:
    """Parse official .getInfo; keep one product label per line (br / newline)."""
    if node is None:
        return []
    for br in node.find_all("br"):
        br.replace_with("\n")
    h3 = node.find("h3")
    label = h3.get_text(" ", strip=True) if h3 else ""
    text = node.get_text("\n", strip=True)
    if label and text.startswith(label):
        text = text[len(label) :].strip()
    lines: list[str] = []
    for raw in text.split("\n"):
        line = raw.strip().lstrip("-•·").strip()
        if line and line not in lines:
            lines.append(line)
    return lines


def _clean_image_ref(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    text = text.replace("../", "").replace("./", "")
    return text


def _to_jp_image_url(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        # Force all synced images to Japanese official host.
        if "/images/" in text:
            text = text.split("/images/", 1)[1]
            return f"{JAPANESE_IMAGE_HOST}images/{text}"
        return text
    normalized = text.replace("../", "").replace("./", "")
    if normalized.startswith("/"):
        normalized = normalized[1:]
    return f"{JAPANESE_IMAGE_HOST}{normalized}"


def parse_cards_from_modal_html(html: str) -> dict[str, ParsedCard]:
    soup = BeautifulSoup(html, "html.parser")
    cards: dict[str, ParsedCard] = {}
    for modal in soup.select("dl.modalCol[id]"):
        card_id = normalize_card_id(modal.get("id"))
        if not card_id:
            continue

        rarity = ""
        card_type = ""
        name = ""

        info_spans = modal.select("dt .infoCol span")
        if len(info_spans) >= 3:
            rarity = info_spans[1].get_text(strip=True)
            card_type = info_spans[2].get_text(strip=True)
        name_el = modal.select_one("dt .cardName")
        if name_el:
            name = name_el.get_text(" ", strip=True)

        fields: dict[str, str] = {}
        card_sets: list[str] = []
        back = modal.select_one("dd .backCol")

        def class_text(cls: str) -> str:
            if not back:
                return ""
            node = back.select_one(f".{cls}")
            if not node:
                return ""
            h3 = node.find("h3")
            label = h3.get_text(" ", strip=True) if h3 else ""
            text = node.get_text(" ", strip=True)
            if label and text.startswith(label):
                text = text[len(label) :].strip()
            return text.strip()

        # Class-based extraction is stable across language switch.
        fields["life"] = class_text("cost")
        fields["attribute"] = class_text("attribute")
        fields["power"] = class_text("power")
        fields["counter"] = class_text("counter")
        fields["color"] = class_text("color")
        fields["block_icon"] = class_text("block")
        fields["type"] = class_text("feature")
        fields["effect"] = class_text("text")
        fields["trigger"] = class_text("trigger")
        if fields.get("trigger"):
            fields["effect"] = compose_effect_with_trigger(
                fields.get("effect", ""), fields["trigger"]
            )
        if back:
            card_sets = extract_get_info_lines(back.select_one(".getInfo"))

        fields = {k: v for k, v in fields.items() if v not in (None, "")}

        image_candidates: list[str] = []
        for img in modal.select("img[data-src]"):
            src = _clean_image_ref(img.get("data-src"))
            if src:
                image_candidates.append(_to_jp_image_url(src))
        # keep order and dedupe
        image_candidates = list(dict.fromkeys(image_candidates))

        cards[card_id] = ParsedCard(
            card_id=card_id,
            rarity=rarity,
            card_type=card_type,
            name=name,
            fields=fields,
            card_sets=card_sets,
            image_candidates=image_candidates,
        )
    return cards


def parse_cards_from_html(html: str) -> dict[str, ParsedCard]:
    parsed = parse_cards_from_modal_html(html)
    if parsed:
        return parsed
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    image_map = extract_image_candidates(html)
    parsed = parse_cards_from_text(text, image_map)
    if parsed:
        return parsed
    return parse_cards_id_only_from_html(html, image_map)


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


def fetch_cards_from_official_url(
    url: str,
    session: requests.Session | None = None,
) -> dict[str, ParsedCard]:
    own_session = session is None
    if own_session:
        session = requests.Session()
        session.trust_env = False

    try:
        resp = session.get(url, headers=REQUEST_HEADERS, timeout=25)
    except requests.RequestException as exc:
        print(f"[probe] {url} error={exc}")
        return {}
    if resp.status_code != 200 or not resp.text.strip():
        print(f"[probe] {url} status={resp.status_code}")
        return {}

    html = resp.text
    parsed = parse_cards_from_html(html)
    print(f"[probe] {url} -> parsed_cards={len(parsed)}")

    # If only a small subset is returned (e.g. default OP15 list),
    # crawl each series option via POST to obtain full card coverage.
    if len(parsed) < 500:
        series_values = extract_series_values(html)
        if series_values:
            for series in series_values:
                try:
                    series_resp = session.post(
                        url,
                        data={"search": "true", "series": series},
                        headers=REQUEST_HEADERS,
                        timeout=25,
                    )
                except requests.RequestException:
                    continue
                if series_resp.status_code != 200 or not series_resp.text.strip():
                    continue
                series_cards = parse_cards_from_html(series_resp.text)
                if series_cards:
                    parsed = merge_parsed_cards(parsed, series_cards)
            print(f"[probe] {url} -> expanded_by_series={len(parsed)}")

    return parsed


def fetch_and_parse_best_source() -> tuple[str, str, dict[str, ParsedCard]]:
    last_err = ""
    best_url = ""
    best_html = ""
    best_cards: dict[str, ParsedCard] = {}
    session = requests.Session()
    session.trust_env = False

    for url in OFFICIAL_CARDLIST_URLS:
        parsed = fetch_cards_from_official_url(url, session=session)
        if not parsed:
            last_err = f"{url} parsed=0"
            continue
        if len(parsed) > len(best_cards):
            best_url = url
            best_cards = parsed

    if best_cards:
        return best_url, "", best_cards

    raise RuntimeError(f"无法解析官方 cardlist 页面：{last_err}")


def fetch_cards_from_public_api() -> dict[str, ParsedCard]:
    cards: dict[str, ParsedCard] = {}
    page = 1
    page_size = 500
    session = requests.Session()
    session.trust_env = False
    last_reason = ""
    while True:
        url = f"{PUBLIC_API_BASE}/cards?page={page}&page_size={page_size}"
        try:
            resp = session.get(url, headers=REQUEST_HEADERS, timeout=30)
            if resp.status_code != 200:
                last_reason = f"status={resp.status_code}"
                break
            try:
                data = resp.json()
            except ValueError:
                data = None
        except requests.RequestException as exc:
            last_reason = str(exc)
            break

        rows: list[Any] = []
        if isinstance(data, dict):
            rows = data.get("data") or data.get("cards") or data.get("results") or []
        elif isinstance(data, list):
            rows = data
        else:
            last_reason = "response is not JSON object/list"
            break

        if not isinstance(rows, list) or not rows:
            if isinstance(data, dict):
                last_reason = f"empty rows, keys={list(data.keys())[:8]}"
            else:
                last_reason = "empty rows"
            break

        for row in rows:
            if not isinstance(row, dict):
                continue
            cid = normalize_card_id(row.get("id") or row.get("card_number"))
            if not cid:
                continue
            pc = ParsedCard(
                card_id=cid,
                rarity=str(row.get("rarity") or "").strip(),
                card_type=str(row.get("category") or "").strip(),
                name=str(row.get("name") or "").strip(),
                fields={
                    "effect": str(row.get("effect") or "").strip(),
                    "power": str(row.get("power") or "").strip(),
                    "counter": str(row.get("counter") or "").strip(),
                    "color": "/".join(row.get("colors") or []),
                    "type": "/".join(row.get("types") or []),
                    "attribute": "/".join(row.get("attributes") or []),
                },
                card_sets=[
                    str(s.get("label") or "").strip()
                    for s in (row.get("sets") or [])
                    if isinstance(s, dict) and str(s.get("label") or "").strip()
                ],
                image_candidates=[str(row.get("image_url") or "").strip()],
            )
            cards[cid] = pc
        print(f"[api] page={page} rows={len(rows)} total_cards={len(cards)}")
        page += 1
    if not cards and last_reason:
        print(f"[api] fallback failed: {last_reason}")
    return cards


def extract_image_candidates(html: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    # absolute URLs with card id
    for m in re.finditer(
        r"https?://[^\"'\s>]+(?:png|jpg|jpeg|webp)", html, flags=re.IGNORECASE
    ):
        url = m.group(0)
        upper = url.upper()
        card_match = re.search(r"([A-Z]{2,4}-?\d{2}-\d{3}(?:-[A-Z0-9]+)?)", upper)
        if not card_match:
            continue
        cid = normalize_card_id(card_match.group(1))
        out.setdefault(cid, []).append(url)
    # relative cardlist image paths
    for m in re.finditer(
        r"(?:\.{0,2}/)?images/cardlist/[^\"'\s>]+(?:png|jpg|jpeg|webp)",
        html,
        flags=re.IGNORECASE,
    ):
        rel = m.group(0)
        upper = rel.upper()
        card_match = re.search(r"([A-Z]{2,4}-?\d{2}-\d{3}(?:-[A-Z0-9]+)?)", upper)
        if not card_match:
            continue
        cid = normalize_card_id(card_match.group(1))
        out.setdefault(cid, []).append(rel)
    # dedupe
    for cid, items in list(out.items()):
        seen: set[str] = set()
        deduped: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        out[cid] = deduped
    return out


def parse_cards_id_only_from_html(
    html: str, image_map: dict[str, list[str]]
) -> dict[str, ParsedCard]:
    cards: dict[str, ParsedCard] = {}
    for m in re.finditer(r"([A-Z]{2,4}-?\d{2}-\d{3}(?:-[A-Z0-9]+)?)", html.upper()):
        cid = normalize_card_id(m.group(1))
        if not cid:
            continue
        if cid not in cards:
            cards[cid] = ParsedCard(
                card_id=cid,
                image_candidates=image_map.get(cid, []),
            )
    return cards


def parse_cards_from_text(text: str, image_map: dict[str, list[str]]) -> dict[str, ParsedCard]:
    cards: dict[str, ParsedCard] = {}
    lines = [ln.strip() for ln in text.splitlines()]
    i = 0
    current: ParsedCard | None = None
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line:
            continue
        m = ID_LINE_RE.match(line)
        if m:
            cid = normalize_card_id(m.group(1))
            rarity = m.group(2).strip()
            ctype = m.group(3).strip()
            candidate = ParsedCard(
                card_id=cid,
                rarity=rarity,
                card_type=ctype,
                image_candidates=image_map.get(cid, []),
            )
            # Name is usually next non-empty line, unless it's a heading.
            j = i
            while j < len(lines) and not lines[j]:
                j += 1
            if j < len(lines) and lines[j] not in {f"### {k}" for k in HEADING_KEYS}:
                maybe_name = lines[j].strip()
                if maybe_name and not CARD_ID_RE.match(maybe_name) and maybe_name != "ボタン":
                    candidate.name = maybe_name
                    i = j + 1
            existing = cards.get(cid)
            if existing is None or candidate.score() >= existing.score():
                cards[cid] = candidate
                current = candidate
            else:
                current = existing
            continue

        if current is None:
            continue

        if line.startswith("### "):
            label = line.replace("### ", "", 1).strip()
            key = HEADING_KEYS.get(label)
            if not key:
                continue
            value_lines: list[str] = []
            while i < len(lines):
                nxt = lines[i].strip()
                if not nxt:
                    i += 1
                    if value_lines:
                        break
                    continue
                if nxt.startswith("### "):
                    break
                if ID_LINE_RE.match(nxt) or CARD_ID_RE.match(nxt):
                    break
                if nxt == "ボタン":
                    i += 1
                    continue
                value_lines.append(nxt)
                i += 1
            value = "\n".join(value_lines).strip()
            if key == "card_sets":
                for ln in value_lines:
                    current.card_sets.append(ln.lstrip("-").strip())
            elif key == "trigger":
                current.fields["trigger"] = value
                current.fields["effect"] = compose_effect_with_trigger(
                    current.fields.get("effect", ""), value
                )
            else:
                current.fields[key] = value
                if key == "effect" and current.fields.get("trigger"):
                    current.fields["effect"] = compose_effect_with_trigger(
                        value, current.fields["trigger"]
                    )
    return cards


def merge_index(existing: dict[str, Any], parsed_cards: dict[str, ParsedCard], base_url: str) -> dict[str, Any]:
    merged: dict[str, Any] = dict(existing)
    for card_id, pc in parsed_cards.items():
        # Keep each official illustration id (incl. treasure-box _p1/_p2) as its own
        # row with that modal's getInfo only — do not fold reprint sources into base.
        current = merged.get(card_id, {})
        if not isinstance(current, dict):
            current = {}

        colors = split_multi(pc.fields.get("color", ""))
        traits = split_multi(pc.fields.get("type", ""))
        attributes = split_multi(pc.fields.get("attribute", ""))

        for rel in pc.image_candidates:
            if rel.startswith("http://") or rel.startswith("https://"):
                img_url = _to_jp_image_url(rel)
            else:
                img_url = _to_jp_image_url(rel)
            current.setdefault("img_full_url", img_url)
            current.setdefault("img_url", rel)
            break

        if pc.name:
            current["name"] = pc.name
        if pc.rarity:
            current["rarity"] = normalize_rarity(pc.rarity) or pc.rarity
        if pc.card_type:
            current["category"] = pc.card_type.title()
            current["card_type"] = pc.card_type.title()

        if colors:
            current["colors"] = colors
        if traits:
            current["traits"] = traits
        if attributes:
            current["attributes"] = attributes
        if pc.fields.get("effect"):
            current["effect"] = pc.fields["effect"]
        if pc.fields.get("trigger"):
            current["trigger"] = strip_field_label(
                pc.fields["trigger"], ("Trigger", "觸發器", "触发器")
            )
            current["effect"] = compose_effect_with_trigger(
                str(current.get("effect") or ""), pc.fields["trigger"]
            )

        power_int = safe_int(pc.fields.get("power"))
        if power_int is not None:
            current["power"] = power_int
        counter_int = safe_int(pc.fields.get("counter"))
        if counter_int is not None:
            current["counter"] = counter_int
        block_int = safe_int(pc.fields.get("block_icon"))
        if block_int is not None:
            current["block_number"] = block_int
        # Official asia cardlist often stores Character/Event/Stage cost in the
        # "Life" field. Leaders keep real life separately.
        cost_int = safe_int(pc.fields.get("cost"))
        life_int = safe_int(pc.fields.get("life"))
        card_type_u = str(pc.card_type or current.get("card_type") or current.get("category") or "").upper()
        is_leader = "LEADER" in card_type_u or "領袖" in card_type_u or "领航" in card_type_u
        if cost_int is not None:
            current["cost"] = cost_int
        elif not is_leader:
            if life_int is not None:
                current["cost"] = life_int
            else:
                raw = str(pc.fields.get("life") or pc.fields.get("cost") or "").strip()
                # Official asia cardlist stores printed 0 as "-" in the cost node.
                if raw in {"", "-", "—", "－"}:
                    current["cost"] = 0
        if life_int is not None:
            current["life"] = life_int

        if pc.card_sets:
            current["card_sets"] = pc.card_sets
            if "pack_id" not in current or not str(current.get("pack_id") or "").strip():
                set_code = re.search(r"\[([A-Z]{2,4}-\d{2})\]", " ".join(pc.card_sets))
                if set_code:
                    current["pack_id"] = set_code.group(1)

        if pc.name or pc.fields.get("effect"):
            current.pop("preview", None)

        merged[card_id] = current
    return merged


def merge_english_fields(merged: dict[str, Any], en_cards: dict[str, ParsedCard]) -> dict[str, Any]:
    """Merge asia-en cardlist text into name_en / effect_en / traits_en fields."""
    for card_id, pc in en_cards.items():
        current = merged.get(card_id, {})
        if not isinstance(current, dict):
            current = {}

        if pc.name:
            current["name_en"] = pc.name
        if pc.fields.get("effect"):
            current["effect_en"] = pc.fields["effect"]
        if pc.fields.get("trigger"):
            current["trigger_en"] = strip_field_label(
                pc.fields["trigger"], ("Trigger", "觸發器", "触发器")
            )
            current["effect_en"] = compose_effect_with_trigger(
                str(current.get("effect_en") or ""), pc.fields["trigger"]
            )

        traits = split_multi(pc.fields.get("type", ""))
        if traits:
            current["traits_en"] = traits

        attributes = split_multi(pc.fields.get("attribute", ""))
        if attributes:
            current["attributes_en"] = attributes

        colors = split_multi(pc.fields.get("color", ""))
        if colors:
            current["colors_en"] = colors

        if pc.card_type:
            current["category_en"] = pc.card_type.title()
            current["card_type_en"] = pc.card_type.title()

        merged[card_id] = current
    return merged


def write_snapshot(parsed_cards: dict[str, ParsedCard]) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for cid, pc in sorted(parsed_cards.items()):
        rows.append(
            {
                "id": cid,
                "name": pc.name,
                "rarity": normalize_rarity(pc.rarity) or pc.rarity,
                "card_type": pc.card_type,
                "fields": pc.fields,
                "card_sets": pc.card_sets,
                "image_candidates": pc.image_candidates,
            }
        )
    SNAPSHOT_PATH.write_text(
        json.dumps({"cards": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def apply_official_card_sets(
    index: dict[str, Any],
    parsed_cards: dict[str, ParsedCard],
) -> int:
    """Overwrite card_sets from official parse; strip guessed multi-sources not on paper."""
    updated = 0
    stale_extra = re.compile(
        r"Heroines Edition vol\.2|【EB-05】|Treasure Chest|寶藏箱|宝藏箱",
        re.I,
    )
    for cid, pc in parsed_cards.items():
        row = index.get(cid)
        if not isinstance(row, dict):
            continue
        sets = [str(x).strip() for x in (pc.card_sets or []) if str(x).strip()]
        prev = [str(x).strip() for x in (row.get("card_sets") or []) if str(x).strip()]
        if sets != prev:
            if sets:
                row["card_sets"] = sets
            else:
                row.pop("card_sets", None)
            updated += 1

    # Drop non-official EB-05/treasure extras on rows that were never in this parse
    # (keeps DON / manually curated single labels that are not treasure/EB-05 pollution).
    parsed_ids = set(parsed_cards.keys())
    for cid, row in index.items():
        if not isinstance(row, dict) or cid in parsed_ids:
            continue
        if str(cid).upper().startswith("DON"):
            continue
        sets = [str(x).strip() for x in (row.get("card_sets") or []) if str(x).strip()]
        if len(sets) <= 1:
            continue
        cleaned = [s for s in sets if not stale_extra.search(s)]
        if cleaned != sets:
            if cleaned:
                row["card_sets"] = cleaned
            else:
                row.pop("card_sets", None)
            updated += 1
    return updated


def run_image_sync() -> None:
    cmd = [sys.executable, str(BASE_DIR / "sync_card_images.py")]
    subprocess.run(cmd, check=False)


def run_limited_variant_sync() -> None:
    cmd = [sys.executable, str(BASE_DIR / "sync_limited_variants.py")]
    subprocess.run(cmd, check=False)


def run_attribute_sync() -> None:
    cmd = [sys.executable, str(BASE_DIR / "sync_card_attributes.py")]
    subprocess.run(cmd, check=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从官方 cardlist 同步卡牌详情到本地 index/cards_by_id.json"
    )
    parser.add_argument(
        "--with-images",
        action="store_true",
        help="同步详情后，自动执行 sync_card_images.py 下载图片",
    )
    parser.add_argument(
        "--with-attributes",
        action="store_true",
        help="同步详情后，自动执行 sync_card_attributes.py 预计算属性",
    )
    parser.add_argument(
        "--full-sync",
        action="store_true",
        help="一键执行：官方详情 + 图片同步 + 属性预计算",
    )
    parser.add_argument(
        "--skip-limited-variants",
        action="store_true",
        help="跳过日文限定/宣传异画补全（默认在 --with-images / --full-sync 时执行）",
    )
    args = parser.parse_args()
    with_images = bool(args.with_images or args.full_sync)
    with_attributes = bool(args.with_attributes or args.full_sync)
    with_limited = bool(with_images and not args.skip_limited_variants)

    if not INDEX_PATH.exists():
        raise SystemExit(f"未找到索引文件: {INDEX_PATH}")

    try:
        existing = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"读取索引失败: {exc}") from exc
    if not isinstance(existing, dict):
        raise SystemExit("cards_by_id.json 格式错误，应为对象映射。")

    session = requests.Session()
    session.trust_env = False

    parsed_cards = fetch_cards_from_official_url(OFFICIAL_TC_URL, session=session)
    source_url = OFFICIAL_TC_URL if parsed_cards else ""

    if not parsed_cards:
        print("繁中 cardlist 解析为空，尝试其他官方源...")
        try:
            source_url, _html, parsed_cards = fetch_and_parse_best_source()
        except RuntimeError:
            parsed_cards = {}

    if not parsed_cards:
        print("官方页面解析为空，启用 API 兜底数据源...")
        parsed_cards = fetch_cards_from_public_api()
        source_url = PUBLIC_API_BASE

    if not parsed_cards:
        raise SystemExit("官方与兜底数据源都未解析到卡牌，请稍后重试。")

    en_cards = fetch_cards_from_official_url(OFFICIAL_EN_URL, session=session)

    merged = merge_index(existing, parsed_cards, source_url)
    if en_cards:
        merged = merge_english_fields(merged, en_cards)
    sets_fixed = apply_official_card_sets(merged, parsed_cards)
    dropped = drop_underscore_alias_keys(merged)
    INDEX_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    write_snapshot(parsed_cards)

    print(f"官方来源: {source_url}")
    print(f"本次解析卡牌: {len(parsed_cards)}")
    print(f"英文卡牌: {len(en_cards)}")
    print(f"索引总卡牌: {len(merged)}")
    print(f"card_sets 校正: {sets_fixed}")
    print(f"清理 _p/_r 重复键: {dropped}")
    print(f"快照已写入: {SNAPSHOT_PATH}")

    if with_limited:
        print("开始同步限定/宣传异画...")
        run_limited_variant_sync()
    if with_images:
        print("开始同步图片...")
        run_image_sync()
    if with_attributes:
        print("开始预计算卡牌属性...")
        run_attribute_sync()


if __name__ == "__main__":
    main()

