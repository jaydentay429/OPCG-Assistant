from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
META_DIR = BASE_DIR / "meta"
LOG_FILE = META_DIR / "sync_daily_pipeline.log"
STATUS_FILE = META_DIR / "sync_daily_status.json"
INDEX_FILE = BASE_DIR / "index" / "cards_by_id.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def append_log(line: str) -> None:
    META_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


def run_step(name: str, cmd: list[str]) -> dict[str, Any]:
    started_at = now_iso()
    append_log(f"[{started_at}] START {name}: {' '.join(cmd)}")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        ended_at = now_iso()
        append_log(f"[{ended_at}] ERROR {name}: {exc}")
        return {
            "name": name,
            "command": cmd,
            "started_at": started_at,
            "ended_at": ended_at,
            "return_code": -1,
            "ok": False,
            "stdout": "",
            "stderr": str(exc),
        }

    ended_at = now_iso()
    if proc.stdout.strip():
        append_log(proc.stdout.strip())
    if proc.stderr.strip():
        append_log(proc.stderr.strip())
    append_log(f"[{ended_at}] END {name}: rc={proc.returncode}")
    return {
        "name": name,
        "command": cmd,
        "started_at": started_at,
        "ended_at": ended_at,
        "return_code": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def load_index_ids() -> set[str]:
    if not INDEX_FILE.exists():
        return set()
    try:
        raw = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if not isinstance(raw, dict):
        return set()
    return {str(k).strip().upper() for k in raw.keys() if str(k).strip()}


def main() -> None:
    parser = argparse.ArgumentParser(description="每日同步：官方新卡、价格、比赛数据、属性")
    parser.add_argument("--python", default=sys.executable, help="Python 解释器路径")
    parser.add_argument("--batch-size", type=int, default=250, help="价格同步每批数量")
    parser.add_argument("--batch-sleep", type=float, default=15.0, help="价格同步批间休眠秒数")
    parser.add_argument("--retry-sleep-on-429", type=float, default=60.0, help="价格同步遇到 429 额外休眠秒数")
    parser.add_argument("--attr-max-ocr-bases", type=int, default=300, help="新卡属性补全最大OCR基础卡数")
    parser.add_argument("--attr-cooldown-ms", type=int, default=40, help="新卡属性补全OCR间隔毫秒")
    parser.add_argument("--force-attr-sync", action="store_true", help="即使没有新卡也执行属性补全")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="某一步失败后继续执行后续步骤",
    )
    args = parser.parse_args()

    started_at = now_iso()
    steps: list[dict[str, Any]] = []
    before_ids = load_index_ids()

    # 1) 官方卡池轻量同步（每日）
    steps.append(
        run_step(
            "official_cards_sync_light",
            [args.python, "sync_official_cards.py", "--with-images"],
        )
    )
    if not steps[-1]["ok"] and not args.continue_on_error:
        finalize_status(started_at, steps)
        raise SystemExit(1)
    after_ids = load_index_ids()
    new_ids = sorted(after_ids - before_ids)
    append_log(f"[{now_iso()}] NEW_CARDS detected: {len(new_ids)}")

    # 1.5) 只有检测到新卡时才补属性（低负载）
    if new_ids or args.force_attr_sync:
        steps.append(
            run_step(
                "attributes_sync_missing_only",
                [
                    args.python,
                    "sync_card_attributes.py",
                    "--only-missing",
                    "--max-ocr-bases",
                    str(args.attr_max_ocr_bases),
                    "--cooldown-ms",
                    str(args.attr_cooldown_ms),
                ],
            )
        )
        if not steps[-1]["ok"] and not args.continue_on_error:
            finalize_status(started_at, steps, extra={"new_cards_count": len(new_ids), "new_cards": new_ids[:200]})
            raise SystemExit(1)

    # 2) 比赛环境（Limitless）同步
    steps.append(
        run_step(
            "limitless_sync",
            [args.python, "sync_limitless.py"],
        )
    )
    if not steps[-1]["ok"] and not args.continue_on_error:
        finalize_status(started_at, steps)
        raise SystemExit(1)

    # 3) 价格同步（严格异画 + 分批防限流）
    steps.append(
        run_step(
            "yuyutei_price_sync",
            [
                args.python,
                "sync_yuyutei_prices.py",
                "--strict-variant",
                "--two-pass",
                "--batch-size",
                str(args.batch_size),
                "--batch-sleep",
                str(args.batch_sleep),
                "--retry-sleep-on-429",
                str(args.retry_sleep_on_429),
            ],
        )
    )

    finalize_status(
        started_at,
        steps,
        extra={
            "new_cards_count": len(new_ids),
            "new_cards": new_ids[:200],
            "attr_sync_triggered": bool(new_ids or args.force_attr_sync),
        },
    )
    if any(not s.get("ok") for s in steps):
        raise SystemExit(1)


def finalize_status(started_at: str, steps: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> None:
    payload = {
        "started_at": started_at,
        "ended_at": now_iso(),
        "ok": all(bool(s.get("ok")) for s in steps),
        "steps": steps,
    }
    if extra:
        payload.update(extra)
    META_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
