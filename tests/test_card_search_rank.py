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
    assert 20 < len(luffy) < 400
    assert "OP18-076" not in luffy
    assert "P-160" not in luffy
    assert "OP02-107" not in luffy
