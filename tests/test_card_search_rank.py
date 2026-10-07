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


def test_set_prefixes_and_fullwidth_card_numbers():
    """Partial set codes match ids only. Counts are the live catalog."""
    expected = {
        "P-": (259, "P-001"),
        "P": (259, "P-001"),
        "OP": (3578, "OP01-001"),
        "Op": (3578, "OP01-001"),
        "OP1": (1418, "OP10-001"),
        "OP18": (38, "OP18-001"),
        "OP18-0": (31, "OP18-001"),
        "PRB": (41, "PRB01-001"),
        "PRB0": (41, "PRB01-001"),
        "ST": (783, "ST01-001"),
        "ST1": (221, "ST10-001"),
        "EB": (465, "EB01-001"),
        "EB0": (465, "EB01-001"),
        "ＯＰ１８－０７６": (1, "OP18-076"),
    }
    for query, (count, first) in expected.items():
        ids = _search(query)
        assert len(ids) == count, query
        assert ids[0] == first, (query, ids[0] if ids else None)

    assert all(card_id.startswith("P-") for card_id in _search("P-"))
    assert all(card_id.startswith("OP1") for card_id in _search("OP1"))
    assert "OP01-001" not in _search("OP1")
    assert "P-160" not in _search("Op")
    assert "PRB01-001" not in _search("P")
    assert _search("ＯＰ１８－０７６") == ["OP18-076"]


def test_letter_digit_names_search_names_and_traits():
    """CP9 / Mr.1 / GERMA 66 are not card numbers. Counts are the live catalog."""
    expected = {
        "CP9": (46, "OP03-076"),
        "CP0": (35, "ST29-003"),
        "Mr.1": (14, "OP01-083"),
        "Mr.2": (14, "ST08-013"),
        "Mr.3": (16, "ST30-014"),
        "GERMA 66": (60, "OP06-078"),
        "Germa66": (60, "OP06-078"),
        "Don": (447, "ST03-009"),
        "don": (447, "ST03-009"),
        "DON": (447, "ST03-009"),
        "DON!!": (447, "ST03-009"),
        "P-160": (1, "P-160"),
        "OP18-076": (1, "OP18-076"),
        "EB05-049": (1, "EB05-049"),
        "OP18-106": (1, "OP18-106"),
        "P-159": (2, "P-159"),
        "ST01-001": (4, "ST01-001"),
        "鯊魚潛水3號": (1, "OP18-076"),
        "迷你梅利2號": (2, "OP18-078"),
        "OP18": (38, "OP18-001"),
        "EB05": (69, "EB05-001"),
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


def test_search_reuses_precomputed_name_norms_and_cache_header():
    """OpenCC runs when the index loads, not once per card on every query."""
    assert app.FILTER_CARDS_CACHE_CONTROL == "public, max-age=300, s-maxage=300"
    assert len(app.card_search_name_norms_by_id) == len(app.cards_by_id)

    calls = {"n": 0}
    original = app._opencc_convert

    def _counting(text, converter):
        calls["n"] += 1
        return original(text, converter)

    app._opencc_convert = _counting
    try:
        ids = _search("魯夫")
    finally:
        app._opencc_convert = original
    assert ids[0] == "ST01-001"
    assert len(ids) == 244
    # Query-side conversion only. The old per-card loop was ~150k calls.
    assert calls["n"] < 100


def test_unknown_full_card_id_falls_back_to_name_and_trait():
    assert app.canonical_full_card_id("OP99-999") == "OP99-999"
    assert app.catalog_has_card_id_match("OP99-999") is False
    assert app.card_text_query_rank("OP01-001", "OP99-999 special", "OP99-999") is not None
    assert _search("OP99-999") == []
    assert app.canonical_full_card_id("CP9") is None
    assert app.canonical_full_card_id("Mr.1") is None
    assert app.canonical_full_card_id("Don") is None
    assert app.canonical_full_card_id("GERMA 66") is None
