from __future__ import annotations

from pathlib import Path
from typing import Callable


BASE_DIR = Path(__file__).resolve().parent
RULES_DIR = BASE_DIR / "official_rules"
OUTPUT_FILE = RULES_DIR / "official_rules_images.txt"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}


def _ocr_with_rapidocr(image_path: Path) -> str:
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    result, _ = engine(str(image_path))
    if not result:
        return ""
    lines = [str(item[1]).strip() for item in result if item and len(item) > 1]
    return "\n".join([x for x in lines if x]).strip()


def _ocr_with_tesseract(image_path: Path) -> str:
    import pytesseract
    from PIL import Image

    img = Image.open(image_path)
    # chi_sim+eng works for Simplified Chinese + English snippets.
    text = pytesseract.image_to_string(img, lang="chi_sim+eng")
    return text.strip()


def _pick_ocr_runner() -> tuple[Callable[[Path], str], str]:
    try:
        import rapidocr_onnxruntime  # noqa: F401

        return _ocr_with_rapidocr, "rapidocr_onnxruntime"
    except Exception:
        pass

    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401

        return _ocr_with_tesseract, "pytesseract"
    except Exception:
        pass

    raise SystemExit(
        "未找到可用 OCR 依赖。请安装其一：\n"
        "1) pip3 install rapidocr_onnxruntime\n"
        "2) pip3 install pytesseract pillow （并安装 tesseract 可执行程序）"
    )


def main() -> None:
    if not RULES_DIR.exists() or not RULES_DIR.is_dir():
        raise SystemExit(f"未找到规则目录：{RULES_DIR}")

    images = sorted(
        [p for p in RULES_DIR.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    )
    if not images:
        raise SystemExit(f"在 {RULES_DIR} 及其子目录中没有找到图片文件。")

    runner, engine_name = _pick_ocr_runner()
    print(f"OCR 引擎：{engine_name}")
    print(f"待处理图片数：{len(images)}")

    chunks: list[str] = []
    ok = 0
    skipped = 0

    for img_path in images:
        relative = img_path.relative_to(RULES_DIR)
        print(f"处理：{relative}")
        try:
            text = runner(img_path).strip()
        except Exception as exc:
            print(f"  - 失败：{exc}")
            skipped += 1
            continue
        if not text:
            print("  - 跳过：未识别到文本")
            skipped += 1
            continue
        chunks.append(f"===== {relative} =====\n{text}")
        ok += 1

    if not chunks:
        raise SystemExit("没有可写入的 OCR 文本，未生成输出文件。")

    OUTPUT_FILE.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")
    print(f"\n完成：成功 {ok}，跳过/失败 {skipped}")
    print(f"输出：{OUTPUT_FILE}")


if __name__ == "__main__":
    main()

