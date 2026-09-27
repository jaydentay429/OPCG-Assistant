#!/usr/bin/env python3
"""Move saved EB05-046 (Stinger Hedgehog) user data to EB05-048.

The catalog row that used to be filed as EB05-046 is the event Stinger Hedgehog.
Its printed number is EB05-048. Run this once, while writes are stopped, before
the deploy that publishes the real EB05-046 Yamato. A second run is refused so
Yamato is not rewritten later.

Default is dry-run. Pass --apply to backup, then rewrite.

User inventory is JSON, not a SQL table. Card comments are SQLite. This script
does not start with the API and is not called from deploy.yml.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_ID = "eb05_046_hedgehog_to_048"
OLD_ID = "EB05-046"
NEW_ID = "EB05-048"

DECKS_NAME = "user_decks.json"
COLLECTIONS_NAME = "user_collections.json"
BINDERS_NAME = "user_binders.json"
SHARES_NAME = "binder_shares.json"
COMMENTS_NAME = "card_comments.db"
MARKER_NAME = "user_data_migrations.db"


def normalize_card_id(raw: str) -> str:
    cleaned = str(raw or "").strip().upper().replace("_", "-").replace(" ", "")
    cleaned = cleaned.replace("－", "-")
    return re.sub(r"[^A-Z0-9-]", "", cleaned)


def remap_card_id(raw: str) -> str | None:
    """EB05-046 and EB05-046-P1 (any suffix) become EB05-048 / EB05-048-P1."""
    norm = normalize_card_id(raw)
    if norm == OLD_ID or norm.startswith(OLD_ID + "-"):
        return NEW_ID + norm[len(OLD_ID) :]
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


@dataclass
class Change:
    store: str
    where: str
    before: str
    after: str


@dataclass
class Plan:
    decks: int = 0
    deck_entries: int = 0
    collections: int = 0
    collection_entries: int = 0
    binder_slots: int = 0
    share_slots: int = 0
    comment_rows: int = 0
    samples: list[Change] = field(default_factory=list)
    decks_doc: Any = None
    collections_doc: Any = None
    binders_doc: Any = None
    shares_doc: Any = None
    comment_updates: list[tuple[str, str]] = field(default_factory=list)

    def any_changes(self) -> bool:
        return bool(
            self.decks
            or self.collections
            or self.binder_slots
            or self.share_slots
            or self.comment_rows
        )


def _note(plan: Plan, change: Change, limit: int = 8) -> None:
    if len(plan.samples) < limit:
        plan.samples.append(change)


def remap_count_map(cards: dict[str, Any], plan: Plan, store: str, where: str) -> tuple[dict[str, Any], int]:
    """Return a new map. Quantities of 046 and an existing 048 are summed."""
    incoming: dict[str, Any] = {}
    touched = 0
    for raw_key, raw_count in cards.items():
        mapped = remap_card_id(str(raw_key))
        dest = mapped if mapped is not None else str(raw_key)
        if mapped is not None:
            touched += 1
            count_txt = raw_count
            _note(
                plan,
                Change(store, where, f"{raw_key} x{count_txt}", f"{dest}（合并数量）"),
            )
        if dest in incoming:
            left = _as_int(incoming[dest])
            right = _as_int(raw_count)
            if left is not None and right is not None:
                incoming[dest] = left + right
            else:
                incoming[dest] = raw_count
        else:
            incoming[dest] = raw_count
    return incoming, touched


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _remap_pages(pages: Any, plan: Plan, store: str, where: str) -> int:
    if not isinstance(pages, list):
        return 0
    slots = 0
    for page in pages:
        if not isinstance(page, list):
            continue
        for idx, slot in enumerate(page):
            if not isinstance(slot, str) or not slot.strip():
                continue
            mapped = remap_card_id(slot)
            if mapped is None:
                continue
            page[idx] = mapped
            slots += 1
            _note(plan, Change(store, where, slot, mapped))
    return slots


def plan_changes(meta: Path) -> Plan:
    plan = Plan()
    decks_path = meta / DECKS_NAME
    decks = _load_json(decks_path)
    if isinstance(decks, dict):
        plan.decks_doc = decks
        for user_id, bucket in decks.items():
            if not isinstance(bucket, list):
                continue
            for deck in bucket:
                if not isinstance(deck, dict):
                    continue
                deck_hits = 0
                where = f"user={user_id} deck={deck.get('id') or ''} name={deck.get('name') or ''}"
                leader = deck.get("leader_card_id")
                if isinstance(leader, str):
                    mapped = remap_card_id(leader)
                    if mapped is not None:
                        deck["leader_card_id"] = mapped
                        deck_hits += 1
                        _note(plan, Change("user_decks", where, f"leader {leader}", mapped))
                cards = deck.get("cards")
                if isinstance(cards, dict):
                    remapped, n = remap_count_map(cards, plan, "user_decks", where)
                    if n:
                        deck["cards"] = remapped
                        deck_hits += n
                        plan.deck_entries += n
                if deck_hits:
                    plan.decks += 1

    collections = _load_json(meta / COLLECTIONS_NAME)
    if isinstance(collections, dict):
        plan.collections_doc = collections
        for owner, cards in collections.items():
            if not isinstance(cards, dict):
                continue
            remapped, n = remap_count_map(cards, plan, "user_collections", f"owner={owner}")
            if n:
                collections[owner] = remapped
                plan.collections += 1
                plan.collection_entries += n

    binders = _load_json(meta / BINDERS_NAME)
    if isinstance(binders, dict):
        plan.binders_doc = binders
        for owner, raw in binders.items():
            pages = raw.get("pages") if isinstance(raw, dict) else raw
            plan.binder_slots += _remap_pages(pages, plan, "user_binders", f"owner={owner}")

    shares = _load_json(meta / SHARES_NAME)
    if isinstance(shares, dict):
        plan.shares_doc = shares
        for token, entry in shares.items():
            if not isinstance(entry, dict):
                continue
            plan.share_slots += _remap_pages(
                entry.get("pages"),
                plan,
                "binder_shares",
                f"token={token}",
            )

    comments = meta / COMMENTS_NAME
    if comments.is_file():
        conn = sqlite3.connect(f"file:{comments}?mode=ro", uri=True)
        try:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='card_comments'"
            ).fetchone()
            if exists:
                rows = conn.execute(
                    "SELECT id, card_base_id FROM card_comments"
                ).fetchall()
                for row_id, card_base_id in rows:
                    mapped = remap_card_id(str(card_base_id or ""))
                    if mapped is None:
                        continue
                    plan.comment_updates.append((mapped, str(row_id)))
                    plan.comment_rows += 1
                    _note(
                        plan,
                        Change("card_comments", f"id={row_id}", str(card_base_id), mapped),
                    )
        finally:
            conn.close()
    return plan


def print_plan(plan: Plan) -> None:
    print("EB05-046（刺針刺蝟）→ EB05-048 迁移预览")
    print(f"  user_decks.json 卡组: {plan.decks} 条（卡号条目 {plan.deck_entries}）")
    print(f"  user_collections.json 收藏: {plan.collections} 条（卡号条目 {plan.collection_entries}）")
    print(f"  user_binders.json 卡册格子: {plan.binder_slots}")
    print(f"  binder_shares.json 分享卡册格子: {plan.share_slots}")
    print(f"  card_comments.card_base_id 评论: {plan.comment_rows} 行")
    if not plan.samples:
        print("  样例: （无）")
        return
    print("  样例:")
    for sample in plan.samples:
        print(f"    [{sample.store}] {sample.where}: {sample.before} -> {sample.after}")


def marker_applied(meta: Path) -> bool:
    path = meta / MARKER_NAME
    if not path.is_file():
        return False
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE id = ?",
            (MIGRATION_ID,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def write_marker(meta: Path) -> None:
    path = meta / MARKER_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        conn.execute("BEGIN")
        conn.execute(
            "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)",
            (MIGRATION_ID, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _backup_sqlite(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(src)
    target = sqlite3.connect(dest)
    try:
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()
    check = sqlite3.connect(dest)
    try:
        check.execute("PRAGMA integrity_check").fetchone()
    finally:
        check.close()


def _backup_bytes(src: Path, dest: Path) -> None:
    data = src.read_bytes()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=str(dest.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, dest)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    if dest.read_bytes() != data:
        raise RuntimeError(f"备份校验失败: {dest}")


def backup_sources(meta: Path, stamp: str) -> Path:
    """Full snapshot of files that exist. Failure must happen before any rewrite."""
    backup_root = meta / "backups" / MIGRATION_ID / stamp
    names = [DECKS_NAME, COLLECTIONS_NAME, BINDERS_NAME, SHARES_NAME, COMMENTS_NAME]
    present = [name for name in names if (meta / name).is_file()]
    if not present:
        backup_root.mkdir(parents=True, exist_ok=False)
        return backup_root
    # Create the directory first so a failure here precedes writes.
    backup_root.mkdir(parents=True, exist_ok=False)
    for name in present:
        src = meta / name
        dest = backup_root / name
        if name.endswith(".db"):
            _backup_sqlite(src, dest)
        else:
            _backup_bytes(src, dest)
    return backup_root


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def apply_comments(meta: Path, updates: list[tuple[str, str]]) -> None:
    if not updates:
        return
    path = meta / COMMENTS_NAME
    conn = sqlite3.connect(path)
    try:
        conn.execute("BEGIN")
        conn.executemany(
            "UPDATE card_comments SET card_base_id = ? WHERE id = ?",
            updates,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_plan(meta: Path, plan: Plan) -> None:
    if plan.decks_doc is not None and (plan.decks or plan.deck_entries):
        _atomic_write_json(meta / DECKS_NAME, plan.decks_doc)
    if plan.collections_doc is not None and plan.collections:
        _atomic_write_json(meta / COLLECTIONS_NAME, plan.collections_doc)
    if plan.binders_doc is not None and plan.binder_slots:
        _atomic_write_json(meta / BINDERS_NAME, plan.binders_doc)
    if plan.shares_doc is not None and plan.share_slots:
        _atomic_write_json(meta / SHARES_NAME, plan.shares_doc)
    apply_comments(meta, plan.comment_updates)


def restore_backup(backup_root: Path, meta: Path) -> None:
    """Put backed-up files back. SQLite files go through the backup API."""
    if not backup_root.is_dir():
        raise RuntimeError(f"找不到备份目录: {backup_root}")
    for src in sorted(backup_root.iterdir()):
        if not src.is_file():
            continue
        dest = meta / src.name
        if src.suffix == ".db":
            if dest.exists():
                dest.unlink()
            _backup_sqlite(src, dest)
        else:
            _backup_bytes(src, dest)


def run(meta: Path, apply: bool) -> int:
    meta = meta.resolve()
    if marker_applied(meta):
        print(
            f"拒绝：迁移 {MIGRATION_ID} 已经执行过（{meta / MARKER_NAME}）。"
            "不再改写，避免把后来上线的 EB05-046 大和也改成 048。",
            file=sys.stderr,
        )
        return 2
    plan = plan_changes(meta)
    print_plan(plan)
    if not apply:
        print("dry-run：没有写入。加 --apply 才会备份并修改。")
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        backup_root = backup_sources(meta, stamp)
    except Exception as exc:
        print(f"备份失败，未修改任何数据: {exc}", file=sys.stderr)
        return 1
    print(f"备份目录: {backup_root}")
    try:
        apply_plan(meta, plan)
        write_marker(meta)
    except Exception as exc:
        print(f"写入失败，正在从备份恢复: {exc}", file=sys.stderr)
        try:
            restore_backup(backup_root, meta)
        except Exception as restore_exc:
            print(f"恢复也失败，请按备份目录手工还原: {restore_exc}", file=sys.stderr)
        return 1
    print(f"已写入。标记 {MIGRATION_ID}。再次运行会被拒绝。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--meta-dir",
        type=Path,
        default=ROOT / "meta",
        help="目录，内含 user_decks.json 等（服务器上是 /opt/opcg/app/meta）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="备份并真正改写。省略时只打印条数和样例。",
    )
    args = parser.parse_args(argv)
    return run(args.meta_dir, apply=bool(args.apply))


if __name__ == "__main__":
    sys.exit(main())
