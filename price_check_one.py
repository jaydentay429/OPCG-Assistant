from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests


def main() -> None:
    parser = argparse.ArgumentParser(description="单张卡价格检测")
    parser.add_argument("--card-id", required=True, help="例如 OP15-002-P1")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端地址")
    parser.add_argument("--save", action="store_true", help="保存到 meta/price_check_result.json")
    args = parser.parse_args()

    card_id = args.card_id.strip().upper()
    url = f"{args.base_url.rstrip('/')}/prices/{card_id}"

    try:
        resp = requests.get(url, params={"exact": "true"}, timeout=20)
    except requests.RequestException as exc:
        raise SystemExit(f"请求失败: {exc}")

    print(f"HTTP: {resp.status_code}")
    try:
        data = resp.json()
    except ValueError:
        print(resp.text)
        raise SystemExit("返回不是 JSON")

    print(json.dumps(data, ensure_ascii=False, indent=2))

    if args.save:
        out = Path("meta") / "price_check_result.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已保存: {out}")


if __name__ == "__main__":
    main()

