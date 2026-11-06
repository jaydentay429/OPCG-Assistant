"""Nickname, alternate-translation, and Japanese-name search.

``/filters/cards`` uses ``card_text_query_rank``. An exact official name or a
nickname from ``index/card_nicknames.json`` ranks ahead of a substring.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from card_nicknames import nickname_groups  # noqa: E402

# Character cards the Corazon nicknames have to find, plus -P/-R variants.
CORAZON_BASES = (
    "OP05-022",
    "OP12-061",
    "OP02-108",
    "OP04-119",
    "OP05-030",
    "OP09-032",
    "OP10-072",
    "OP12-048",
    "OP12-108",
    "OP16-070",
    "EB02-025",
    "EB04-038",
)
CORAZON_DON = ("DONPRB01-10285", "DONPRB01-10286", "DONPRB01-10287")


def setup_module() -> None:
    app.load_cards_index()


def _search(q: str) -> list[str]:
    norms = app.expand_query_match_norms(q)
    hits: list[tuple[int, str]] = []
    for cid, basic in app.cards_by_id.items():
        if not isinstance(basic, dict):
            continue
        rank = app.card_text_query_rank(
            cid,
            str(basic.get("name") or ""),
            q,
            name_en=str(basic.get("name_en") or "") or None,
            query_norms=norms,
        )
        if rank is not None:
            hits.append((rank, cid))
    hits.sort(key=lambda item: (item[0], app.card_id_sort_key(item[1])))
    return [cid for _rank, cid in hits]


def _en(cid: str) -> str:
    return str((app.cards_by_id.get(cid) or {}).get("name_en") or "")


def _name(cid: str) -> str:
    return str((app.cards_by_id.get(cid) or {}).get("name") or "")


def test_nickname_table_is_a_small_extendable_file():
    groups = nickname_groups()
    assert 50 <= len(groups) <= 100
    ids = {group.id for group in groups}
    assert {"rosinante", "doflamingo", "luffy", "zoro", "law"} <= ids
    rosinante = next(group for group in groups if group.id == "rosinante")
    for alias in ("柯拉松", "Corazon", "コラソン", "羅西南迪", "罗西南迪"):
        assert alias in rosinante.surfaces
    doflamingo = next(group for group in groups if group.id == "doflamingo")
    assert "多弗朗明哥" in doflamingo.surfaces
    assert "多佛朗明哥" in doflamingo.surfaces


def test_corazon_nicknames_return_character_cards_and_don_variants():
    for query in ("柯拉松", "Corazon", "コラソン", "羅西南迪", "罗西南迪"):
        ids = set(_search(query))
        assert ids, query
        for base in CORAZON_BASES:
            assert base in ids, (query, base)
            for cid in app.cards_by_id:
                if cid.startswith(base + "-"):
                    assert cid in ids, (query, cid)
        for don in CORAZON_DON:
            assert don in ids, (query, don)
        assert _en(_search(query)[0]).startswith("Donquixote Rosinante") or "羅希南特" in _name(
            _search(query)[0]
        )


def test_rosinante_spelling_lines_up_with_corazon_cards():
    """DON!! cards say 羅西南迪; character cards say 羅希南特. Both queries hit both."""
    for query in ("羅希南特", "羅西南迪"):
        ids = set(_search(query))
        assert "OP05-022" in ids
        assert "OP12-061" in ids
        assert "DONPRB01-10285" in ids
        assert "DONPRB01-10287" in ids


def test_doflamingo_alternate_translation():
    ids = _search("多弗朗明哥")
    assert ids
    assert "Doflamingo" in _en(ids[0]) or "多佛朗明哥" in _name(ids[0])
    assert any("Doflamingo" in _en(cid) or "多佛朗明哥" in _name(cid) for cid in ids[:12])
    assert all("Doflamingo" in _en(cid) or "多佛朗明哥" in _name(cid) for cid in ids[:8])


def test_zoro_and_luffy_nicknames_rank_the_character_first():
    zoro = _search("佐罗")
    assert "Zoro" in _en(zoro[0]) or "索隆" in _name(zoro[0])
    tesoro = next(i for i, cid in enumerate(zoro) if "Tesoro" in _en(cid))
    assert tesoro > 0
    assert all("Zoro" in _en(cid) or "索隆" in _name(cid) for cid in zoro[:5])

    luffy = _search("路飞")
    assert _en(luffy[0]).startswith("Monkey.D.Luffy")


def test_short_queries_rank_exact_or_alias_before_substrings():
    """「罗」 and Law used to bury Trafalgar Law under a hundred weaker hits."""
    luo = _search("罗")
    assert len(luo) > 100
    assert _en(luo[0]).startswith("Trafalgar Law")
    assert all(_en(cid).startswith("Trafalgar Law") or "托拉法爾加・羅" in _name(cid) for cid in luo[:12])
    robin = next(i for i, cid in enumerate(luo) if "Robin" in _en(cid))
    assert robin > 12

    law = _search("Law")
    assert len(law) > 50
    assert _en(law[0]).startswith("Trafalgar Law")
    assert all(_en(cid).startswith("Trafalgar Law") or "托拉法爾加・羅" in _name(cid) for cid in law[:12])
    bepo = next(i for i, cid in enumerate(law) if _en(cid).startswith("Law & Bepo"))
    claw = next(i for i, cid in enumerate(law) if "Claw" in _en(cid) or _en(cid) == "Eleclaw")
    assert bepo > 12
    assert claw > bepo


def test_japanese_card_names_are_searchable():
    rosinante_ja = app.card_names_ja_by_id.get("OP05-022")
    assert rosinante_ja
    assert "ロシナンテ" in rosinante_ja
    ids = set(_search(rosinante_ja))
    assert "OP05-022" in ids
    assert "OP12-061" in ids
    # Stored DON name_jp, not only the sidecar.
    name_jp = str(app.cards_by_id["DONPRB01-10285"].get("name_jp") or "")
    assert name_jp
    assert "DONPRB01-10285" in _search(name_jp)
    luffy_ja = app.card_names_ja_by_id.get("ST01-001")
    assert luffy_ja and "ルフィ" in luffy_ja
    assert _en(_search("ルフィ")[0]).startswith("Monkey.D.Luffy") or "魯夫" in _name(_search("ルフィ")[0])


HANNYABAL_DON = ("DONPRB02-10236", "DONPRB02-10237", "DONPRB02-10238")


def test_hannyabal_names_return_character_cards_and_don_cards():
    """Character cards say 般若拔. DON!! cards say 漢尼拔."""
    for query in ("汉尼拔", "漢尼拔", "ハンニャバル"):
        ids = set(_search(query))
        assert "OP02-083" in ids, query
        assert "OP11-076" in ids, query
        assert "EB01-021" in ids, query
        assert "EB01-021-P1" in ids, query
        assert "EB01-021-P2" in ids, query
        for don in HANNYABAL_DON:
            assert don in ids, (query, don)
    # The official character title also finds the DON!! printings.
    brahma = set(_search("般若拔"))
    assert "OP02-083" in brahma
    assert "DONPRB02-10236" in brahma


def test_other_don_translations_find_character_cards():
    """Sample of the other wording gaps the DON!! comparison reported."""
    ivankov = set(_search("艾波利奧・伊凡科夫"))
    assert "OP05-004" in ivankov
    assert "DONPRB01-10237" in ivankov
    assert "DONPRB01-10239" in ivankov

    shanks = set(_search("傑克"))
    assert "OP14-027" in shanks
    assert "DONPRB02-10206" in shanks
    assert "DONPRB02-10208" in shanks


def test_compare_don_character_names_is_read_only():
    nick = ROOT / "index" / "card_nicknames.json"
    index = ROOT / "index" / "cards_by_id.json"
    before = (nick.read_bytes(), index.read_bytes())
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "compare_don_character_names.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert (nick.read_bytes(), index.read_bytes()) == before
    hannyabal = next(line for line in proc.stdout.splitlines() if "\tHannyabal\t" in line)
    assert hannyabal.startswith("linked\t")
    assert "漢尼拔" in hannyabal
    assert "般若拔" in hannyabal
    assert "missing\t" not in proc.stdout
