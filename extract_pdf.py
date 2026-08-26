from __future__ import annotations

from pathlib import Path

import pdfplumber


BASE_DIR = Path(__file__).resolve().parent
RULES_DIR = BASE_DIR / "official_rules"
OUTPUT_FILE = BASE_DIR / "official_rules.txt"


def extract_text_from_pdf(pdf_path: Path) -> str:
    chunks: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            chunks.append(f"[Page {page_index}]\n{text}")
    return "\n\n".join(chunks).strip()


def main() -> None:
    if not RULES_DIR.exists() or not RULES_DIR.is_dir():
        raise SystemExit(f"未找到规则目录：{RULES_DIR}")

    pdf_files = sorted(RULES_DIR.rglob("*.pdf"))
    if not pdf_files:
        raise SystemExit(f"在 {RULES_DIR} 中没有找到 PDF 文件。")

    output_chunks: list[str] = []
    extracted_count = 0

    for pdf_file in pdf_files:
        relative_path = pdf_file.relative_to(RULES_DIR)
        print(f"正在处理：{relative_path}")
        text = extract_text_from_pdf(pdf_file)
        if not text:
            print(f"  - 跳过（无可提取文本）：{relative_path}")
            continue

        output_chunks.append(f"===== {relative_path} =====\n{text}")
        extracted_count += 1

    if extracted_count == 0:
        raise SystemExit("所有 PDF 都未提取到文本，未生成 official_rules.txt。")

    OUTPUT_FILE.write_text("\n\n".join(output_chunks) + "\n", encoding="utf-8")
    print(f"\n完成：共处理 {len(pdf_files)} 个 PDF，成功提取 {extracted_count} 个。")
    print(f"输出文件：{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
