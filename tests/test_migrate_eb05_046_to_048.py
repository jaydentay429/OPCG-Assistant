"""EB05-046 user-data migration: dry-run, apply/merge, backup restore, one-shot."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "migrate_eb05_046_to_048.py"


def _load():
    spec = importlib.util.spec_from_file_location("migrate_eb05_046_to_048", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mig = _load()


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _seed(meta: Path) -> None:
    meta.mkdir(parents=True)
    _write(
        meta / "user_decks.json",
        {
            "user_1": [
                {
                    "id": "deck-a",
                    "name": "刺猬",
                    "leader_card_id": "OP01-001",
                    "cards": {"EB05-046": 2, "EB05-048": 1, "OP01-003": 4},
                },
                {
                    "id": "deck-b",
                    "name": "异画",
                    "leader_card_id": "OP02-001",
                    "cards": {"EB05-046-P1": 1, "EB05-0460": 3},
                },
            ]
        },
    )
    _write(
        meta / "user_collections.json",
        {
            "user_1": {"eb05-046": 4, "EB05-048": 2, "OP01-003": 1},
            "user_2": {"OP01-001": 1},
        },
    )
    _write(
        meta / "user_binders.json",
        {"user_1": {"pages": [["EB05-046", None, "EB05-046-P1"]], "page_titles": ["EB05-046 标题不要改"]}},
    )
    _write(
        meta / "binder_shares.json",
        {"tok": {"owner": "user_1", "pages": [["EB05-046"]], "page_titles": ["share"]}},
    )
    conn = sqlite3.connect(meta / "card_comments.db")
    conn.execute(
        """
        CREATE TABLE card_comments (
            id INTEGER PRIMARY KEY,
            card_base_id TEXT NOT NULL,
            body TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO card_comments (card_base_id, body) VALUES (?, ?)",
        ("EB05-046", "刺猬"),
    )
    conn.execute(
        "INSERT INTO card_comments (card_base_id, body) VALUES (?, ?)",
        ("OP01-001", "别的"),
    )
    conn.commit()
    conn.close()


def _decks(meta: Path) -> dict:
    return json.loads((meta / "user_decks.json").read_text(encoding="utf-8"))


def test_dry_run_does_not_write(tmp_path: Path, capsys) -> None:
    meta = tmp_path / "meta"
    _seed(meta)
    before = {
        name: (meta / name).read_bytes()
        for name in (
            "user_decks.json",
            "user_collections.json",
            "user_binders.json",
            "binder_shares.json",
            "card_comments.db",
        )
    }
    assert mig.run(meta, apply=False) == 0
    after = {name: (meta / name).read_bytes() for name in before}
    assert after == before
    assert not (meta / "backups").exists()
    assert not (meta / "user_data_migrations.db").exists()
    out = capsys.readouterr().out
    assert "卡组: 2 条" in out
    assert "收藏: 1 条" in out
    assert "dry-run" in out


def test_apply_merges_and_second_run_refuses(tmp_path: Path) -> None:
    meta = tmp_path / "meta"
    _seed(meta)
    original_decks = (meta / "user_decks.json").read_bytes()
    original_comments = (meta / "card_comments.db").read_bytes()
    assert mig.run(meta, apply=True) == 0

    decks = _decks(meta)
    cards = decks["user_1"][0]["cards"]
    assert "EB05-046" not in cards
    assert cards["EB05-048"] == 3
    assert cards["OP01-003"] == 4
    alt = decks["user_1"][1]["cards"]
    assert alt["EB05-048-P1"] == 1
    assert alt["EB05-0460"] == 3
    assert decks["user_1"][0]["leader_card_id"] == "OP01-001"

    coll = json.loads((meta / "user_collections.json").read_text(encoding="utf-8"))
    assert coll["user_1"]["EB05-048"] == 6
    assert "eb05-046" not in coll["user_1"]
    assert "EB05-046" not in coll["user_1"]
    assert coll["user_2"] == {"OP01-001": 1}

    binder = json.loads((meta / "user_binders.json").read_text(encoding="utf-8"))
    assert binder["user_1"]["pages"][0][0] == "EB05-048"
    assert binder["user_1"]["pages"][0][2] == "EB05-048-P1"
    assert binder["user_1"]["page_titles"] == ["EB05-046 标题不要改"]

    shares = json.loads((meta / "binder_shares.json").read_text(encoding="utf-8"))
    assert shares["tok"]["pages"] == [["EB05-048"]]

    conn = sqlite3.connect(meta / "card_comments.db")
    rows = dict(conn.execute("SELECT body, card_base_id FROM card_comments").fetchall())
    conn.close()
    assert rows["刺猬"] == "EB05-048"
    assert rows["别的"] == "OP01-001"

    backups = list((meta / "backups" / mig.MIGRATION_ID).iterdir())
    assert len(backups) == 1
    backup = backups[0]
    assert (backup / "user_decks.json").read_bytes() == original_decks
    assert (backup / "card_comments.db").is_file()
    restored = tmp_path / "restored"
    restored.mkdir()
    mig.restore_backup(backup, restored)
    assert (restored / "user_decks.json").read_bytes() == original_decks
    check = sqlite3.connect(restored / "card_comments.db")
    body = check.execute(
        "SELECT card_base_id FROM card_comments WHERE body = ?",
        ("刺猬",),
    ).fetchone()[0]
    check.close()
    assert body == "EB05-046"
    assert original_comments  # backup API rewrites pages; logical content is what we restore

    # A later EB05-046 is the real Yamato and must survive a second run.
    coll["user_2"]["EB05-046"] = 9
    _write(meta / "user_collections.json", coll)
    assert mig.run(meta, apply=True) == 2
    again = json.loads((meta / "user_collections.json").read_text(encoding="utf-8"))
    assert again["user_2"]["EB05-046"] == 9
    assert again["user_1"]["EB05-048"] == 6


def test_backup_failure_does_not_write(tmp_path: Path) -> None:
    meta = tmp_path / "meta"
    _seed(meta)
    before = (meta / "user_decks.json").read_bytes()
    (meta / "backups").write_text("not-a-directory", encoding="utf-8")
    assert mig.run(meta, apply=True) == 1
    assert (meta / "user_decks.json").read_bytes() == before
    assert not (meta / "user_data_migrations.db").exists()
    conn = sqlite3.connect(meta / "card_comments.db")
    card_id = conn.execute(
        "SELECT card_base_id FROM card_comments WHERE body = ?",
        ("刺猬",),
    ).fetchone()[0]
    conn.close()
    assert card_id == "EB05-046"


def test_remap_rules() -> None:
    assert mig.remap_card_id("EB05-046") == "EB05-048"
    assert mig.remap_card_id("eb05-046-p1") == "EB05-048-P1"
    assert mig.remap_card_id("EB05-046_P2") == "EB05-048-P2"
    assert mig.remap_card_id("EB05-0460") is None
    assert mig.remap_card_id("EB05-048") is None
    assert mig.remap_card_id("OP18-112") is None
