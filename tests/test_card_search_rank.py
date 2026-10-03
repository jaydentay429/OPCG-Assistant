"""Card search matches ids exactly or as a prefix, and ranks names ahead of substrings.

``/filters/cards``, ``/search``, and topdeck text search all call
``card_text_query_rank``. ``/filters/cards`` sorts by that rank, then card id.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402


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


def test_exact_card_number_ranks_first_and_is_not_a_substring():
    ids = _search("P-160")
    assert ids[0] == "P-160"
    assert ids == ["P-160"]
    assert "OP16-001" not in ids
    for query in ("p-160", "P160", "p160"):
        assert _search(query) == ["P-160"]

    assert _search("OP18-076") == ["OP18-076"]
    assert _search("op18076") == ["OP18-076"]
    assert _search("EB05-049") == ["EB05-049"]
    assert _search("eb05049") == ["EB05-049"]


def test_set_code_is_a_prefix_not_a_cross_set_substring():
    ids = _search("OP18")
    assert ids[0] == "OP18-001"
    assert "OP18-076" in ids
    assert "OP18-106" in ids
    assert all(card_id.startswith("OP18-") for card_id in ids)
    assert "P-160" not in ids
    assert "OP16-001" not in ids

    prefixed = _search("OP18-0")
    assert prefixed
    assert all(card_id.startswith("OP18-0") for card_id in prefixed)
    assert "OP18-076" in prefixed
    assert "OP18-106" not in prefixed
    assert "OP16-001" not in prefixed


def test_digits_inside_names_do_not_match_card_numbers():
    assert _search("鯊魚潛水3號") == ["OP18-076"]
    merry = _search("迷你梅利2號")
    assert merry[0] == "OP18-078"
    assert merry == ["OP18-078", "EB01-011"]


def test_normal_name_search_ranks_exact_name_before_a_substring():
    doberman = _search("鬥犬")
    assert doberman[0] == "OP02-107"
    assert len(doberman) < 20

    luffy = _search("魯夫")
    assert luffy[0] == "ST01-001"
    assert len(luffy) == 244
    assert "OP18-076" not in luffy
    assert "P-160" not in luffy
    assert "OP02-107" not in luffy


def test_letter_digit_names_search_names_and_traits():
    """CP9 / Mr.1 / GERMA 66 are not card numbers. Counts are the live catalog."""
    expected = {
        "CP9": (44, "OP03-076"),
        "CP0": (35, "ST29-003"),
        "Mr.1": (13, "OP01-083"),
        "Mr.2": (14, "ST08-013"),
        "Mr.3": (16, "ST30-014"),
        "GERMA 66": (58, "OP06-078"),
        "Don": (444, "ST03-009"),
        "P-160": (1, "P-160"),
        "鯊魚潛水3號": (1, "OP18-076"),
        "迷你梅利2號": (2, "OP18-078"),
        "OP18": (26, "OP18-001"),
        "EB05": (43, "EB05-001"),
        "魯夫": (244, "ST01-001"),
    }
    for query, (count, first) in expected.items():
        ids = _search(query)
        assert len(ids) == count, query
        assert ids[0] == first, query

    don = _search("Don")
    assert sum(card_id.startswith("DONPRB") for card_id in don) == 180
    assert sum(card_id.startswith("DONEB") for card_id in don) == 10
    assert sum(
        card_id.startswith("DON") and not card_id.startswith(("DONPRB", "DONEB"))
        for card_id in don
    ) == 56
    assert _search("DONPRB")[0].startswith("DONPRB")
    assert len(_search("DONPRB")) == 180
    assert len(_search("DONEB")) == 10


def test_unknown_full_card_id_falls_back_to_name_and_trait():
    assert app.canonical_full_card_id("OP99-999") == "OP99-999"
    assert app.catalog_has_card_id_match("OP99-999") is False
    assert app.card_text_query_rank("OP01-001", "OP99-999 special", "OP99-999") is not None
    assert _search("OP99-999") == []
    assert app.canonical_full_card_id("CP9") is None
    assert app.canonical_full_card_id("Mr.1") is None
    assert app.canonical_full_card_id("Don") is None
    assert app.canonical_full_card_id("GERMA 66") is None
