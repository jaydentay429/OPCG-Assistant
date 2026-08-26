from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import time
import warnings
from pathlib import Path
from typing import Any

# Keep OCR backend single-threaded by default to reduce CPU heat.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from rapidocr_onnxruntime import RapidOCR


BASE_DIR = Path(__file__).resolve().parent
INDEX_PATH = BASE_DIR / "index" / "cards_by_id.json"
PACKS_DIR = BASE_DIR / "packs"
OFFICIAL_SNAPSHOT_PATH = BASE_DIR / "cards" / "official_sync" / "latest_cards.json"
OUT_PATH = BASE_DIR / "meta" / "card_attributes_map.json"


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


def infer_attributes(text_blob: str) -> list[str]:
    if not text_blob:
        return []
    mapping = [
        ("STRIKE", "打擊"),
        ("SLASH", "斬擊"),
        ("SPECIAL", "特殊"),
        ("RANGED", "遠程"),
        ("WISDOM", "智慧"),
        ("打擊", "打擊"),
        ("斬擊", "斬擊"),
        ("特殊", "特殊"),
        ("遠程", "遠程"),
        ("遠距離", "遠程"),
        ("智慧", "智慧"),
        ("打", "打擊"),
        ("斬", "斬擊"),
        ("特", "特殊"),
        ("射", "遠程"),
        ("知", "智慧"),
        ("打撃", "打擊"),
        ("斬撃", "斬擊"),
        ("射撃", "遠程"),
        ("知識", "智慧"),
        ("打", "打擊"),
        ("斬", "斬擊"),
        ("特", "特殊"),
        ("射", "遠程"),
        ("知", "智慧"),
    ]
    out: list[str] = []
    upper = text_blob.upper()
    for token, zh in mapping:
        if token in upper and zh not in out:
            out.append(zh)
    return out


def extract_text_from_ocr_result(result: Any) -> str:
    chunks: list[str] = []
    for item in result or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        text_part = item[1]
        if isinstance(text_part, (list, tuple)) and text_part:
            # rapidocr usually returns (text, score) at index 1
            maybe_text = text_part[0]
            if isinstance(maybe_text, str):
                chunks.append(maybe_text)
        elif isinstance(text_part, str):
            chunks.append(text_part)
    return " ".join(chunks)


def ocr_text_with_crops(ocr: RapidOCR, image_file: Path, use_crops: bool = False) -> str:
    blobs: list[str] = []
    try:
        result, _ = ocr(str(image_file))
        full_text = extract_text_from_ocr_result(result)
        if full_text:
            blobs.append(full_text)
    except Exception:
        pass

    if not use_crops:
        return " ".join(blobs)

    try:
        from PIL import Image, ImageEnhance, ImageOps
    except Exception:
        return " ".join(blobs)

    try:
        with Image.open(image_file) as im:
            rgb = im.convert("RGB")
            w, h = rgb.size
            crop_boxes = [
                (int(w * 0.52), int(h * 0.06), int(w * 0.98), int(h * 0.34)),
                (int(w * 0.56), int(h * 0.08), int(w * 0.99), int(h * 0.44)),
            ]
            for box in crop_boxes:
                if box[2] <= box[0] or box[3] <= box[1]:
                    continue
                crop = rgb.crop(box).resize((max(120, (box[2] - box[0]) * 2), max(120, (box[3] - box[1]) * 2)))
                gray = ImageOps.grayscale(crop)
                gray = ImageEnhance.Contrast(gray).enhance(2.2)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
                    gray.save(tmp.name)
                    try:
                        c_result, _ = ocr(tmp.name)
                    except Exception:
                        continue
                    c_text = extract_text_from_ocr_result(c_result)
                    if c_text:
                        blobs.append(c_text)
    except Exception:
        pass
    return " ".join(blobs)


def attrs_from_obj(obj: Any) -> list[str]:
    if isinstance(obj, list):
        return infer_attributes(" ".join(str(x) for x in obj))
    if isinstance(obj, str):
        if obj.strip() in {"", "-", "—", "－", "N/A", "NONE"}:
            return []
        raw = obj.replace("/", " ").replace("・", " ").replace("，", " ")
        return infer_attributes(raw)
    return []


def attrs_from_card_record(record: Any) -> list[str]:
    if not isinstance(record, dict):
        return []
    fields = record.get("fields")
    fields_dict = fields if isinstance(fields, dict) else {}
    candidates: list[Any] = [
        record.get("attributes"),
        record.get("attribute"),
        record.get("attr"),
        fields_dict.get("attributes"),
        fields_dict.get("attribute"),
        fields_dict.get("attr"),
    ]
    for item in candidates:
        attrs = attrs_from_obj(item)
        if attrs:
            return attrs
    return []


def load_official_snapshot() -> dict[str, dict[str, Any]]:
    if not OFFICIAL_SNAPSHOT_PATH.exists():
        return {}
    try:
        raw = json.loads(OFFICIAL_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = raw.get("cards") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        rid = normalize_card_id(row.get("id") or row.get("card_id") or "")
        if rid:
            out[rid] = row
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="同步卡牌属性（优先元数据，OCR补全）")
    parser.add_argument("--deep-ocr", action="store_true", help="启用裁切增强OCR（更慢、更吃资源）")
    parser.add_argument("--max-ocr-bases", type=int, default=0, help="最多OCR多少个基础卡号，0=不限制")
    parser.add_argument("--cooldown-ms", type=int, default=15, help="每次OCR后休眠毫秒数，默认15")
    parser.add_argument("--only-missing", action="store_true", help="仅补全已有输出里缺失的卡（推荐日常跑）")
    args = parser.parse_args()

    warnings.filterwarnings(
        "ignore",
        message="Palette images with Transparency expressed in bytes should be converted to RGBA images",
        category=UserWarning,
    )

    if not INDEX_PATH.exists():
        raise SystemExit(f"找不到索引文件: {INDEX_PATH}")
    index_data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    if not isinstance(index_data, dict):
        raise SystemExit("cards_by_id.json 格式错误")

    snapshot_map = load_official_snapshot()
    ocr = RapidOCR()
    out: dict[str, list[str]] = {}
    existing_map: dict[str, list[str]] = {}
    if args.only_missing and OUT_PATH.exists():
        try:
            old = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            old_cards = old.get("cards") if isinstance(old, dict) else {}
            if isinstance(old_cards, dict):
                for k, v in old_cards.items():
                    nk = normalize_card_id(k)
                    vv = [str(x).strip() for x in (v or []) if str(x).strip()]
                    if nk and vv:
                        existing_map[nk] = vv
        except Exception:
            existing_map = {}
    all_ids: list[str] = []
    ids_by_base: dict[str, list[str]] = {}
    checked = 0
    found = 0
    from_index = 0
    from_snapshot = 0
    from_ocr = 0

    from_sibling = 0

    for raw_id in index_data.keys():
        cid = normalize_card_id(raw_id)
        if not cid:
            continue
        all_ids.append(cid)
        ids_by_base.setdefault(base_card_id(cid), []).append(cid)
        checked += 1
        if cid in existing_map:
            out[cid] = existing_map[cid]
            found += 1
            continue

        # 1) Fast path: use index/offline metadata first.
        attrs = attrs_from_card_record(index_data.get(raw_id))
        if attrs:
            out[cid] = attrs
            found += 1
            from_index += 1
            continue

        # 2) Fallback to official snapshot cache if available.
        snapshot_attrs = attrs_from_card_record(snapshot_map.get(cid))
        if snapshot_attrs:
            out[cid] = snapshot_attrs
            found += 1
            from_snapshot += 1
            continue

    # 3) OCR by base card id only once, then apply to its variants.
    ocr_bases_done = 0
    for base, members in ids_by_base.items():
        if any(m in out for m in members):
            continue
        if args.max_ocr_bases > 0 and ocr_bases_done >= args.max_ocr_bases:
            break
        image_file = None
        for cid in members:
            for p in sorted(PACKS_DIR.glob(f"{cid}*")):
                if p.is_file():
                    image_file = p
                    break
            if image_file:
                break
        if not image_file:
            continue
        try:
            text_blob = ocr_text_with_crops(ocr, image_file, use_crops=args.deep_ocr)
        except Exception:
            continue
        attrs = infer_attributes(text_blob)
        if not attrs:
            continue
        ocr_bases_done += 1
        for cid in members:
            if cid not in out:
                out[cid] = list(attrs)
                found += 1
                from_ocr += 1
        if args.cooldown_ms > 0:
            time.sleep(args.cooldown_ms / 1000.0)

    # Family fallback: variants share the same base card attribute.
    for members in ids_by_base.values():
        seed_attrs: list[str] = []
        for cid in members:
            attrs = out.get(cid)
            if attrs:
                seed_attrs = attrs
                break
        if not seed_attrs:
            continue
        for cid in members:
            if cid not in out:
                out[cid] = list(seed_attrs)
                found += 1
                from_sibling += 1

    payload: dict[str, Any] = {"cards": out}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"扫描卡牌: {checked}")
    print(f"识别到属性: {found}")
    print(f"OCR基础卡扫描数: {ocr_bases_done}")
    print(f"来源统计: index={from_index}, snapshot={from_snapshot}, ocr={from_ocr}, sibling={from_sibling}")
    print(f"输出文件: {OUT_PATH}")


if __name__ == "__main__":
    main()

