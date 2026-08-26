"""Rank system tests."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import battle.rank as rank_mod
from battle.matchmaking import RankedMatchmaker
from battle.rank import (
    DEFAULT_RATING,
    apply_match_result,
    base_tier,
    compute_elite_titles,
    elite_badges_for_user_ids,
    get_user_profile,
    match_window,
)
from battle.rooms import RoomManager


def _catalog(cid: str) -> dict:
    base = {"card_id": cid, "name": cid, "colors_en": ["Red"], "colors": ["Red"]}
    if cid == "LDR":
        return {**base, "card_type_en": "LEADER", "card_type": "LEADER", "life": 5, "power": 5000, "cost": 0}
    return {**base, "card_type_en": "CHARACTER", "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _deck_cards() -> dict[str, int]:
    cards: dict[str, int] = {}
    for i in range(1, 13):
        cards[f"C{i:02d}"] = 4
    cards["C13"] = 2
    return cards


def _player(uid: str, name: str) -> dict:
    return {
        "user_id": uid,
        "username": name,
        "leader_card_id": "LDR",
        "cards": _deck_cards(),
        "deck_id": f"d-{uid}",
        "deck_name": f"{name} deck",
    }


def _temp_rank_db(monkeypatch, tmp_path: Path):
    db = tmp_path / "rank.db"
    monkeypatch.setattr(rank_mod, "RANK_DB_FILE", db)
    rank_mod._init_db()
    return db


def test_default_rating_is_1000(monkeypatch, tmp_path) -> None:
    _temp_rank_db(monkeypatch, tmp_path)
    profile = get_user_profile("user_1")
    assert profile["rating"] == DEFAULT_RATING == 1000
    assert profile["peak_rating"] == 1000


def test_tier_boundaries() -> None:
    assert base_tier(998) == "trainee"
    assert base_tier(999) == "trainee"
    assert base_tier(1000) == "crew"
    assert base_tier(1199) == "crew"
    assert base_tier(1200) == "captain_rank"
    assert base_tier(1399) == "captain_rank"
    assert base_tier(1400) == "captain"
    assert base_tier(1599) == "captain"
    assert base_tier(1600) == "bounty"
    assert base_tier(1799) == "bounty"
    assert base_tier(1800) == "supernova"
    assert base_tier(1999) == "supernova"
    assert base_tier(2500) == "supernova"


def test_match_window_expands() -> None:
    assert match_window(0) == 300
    assert match_window(9) == 300
    assert match_window(10) == 500
    assert match_window(20) == 700


def test_elite_title_assignment() -> None:
    rows = [{"user_id": f"user_{i}", "rating": 2400 + i} for i in range(15)]
    elite = compute_elite_titles(rows)
    kings = [uid for uid, t in elite.items() if t == "pirate_king"]
    emperors = [uid for uid, t in elite.items() if t == "emperor"]
    warlords = [uid for uid, t in elite.items() if t == "warlord"]
    assert len(kings) == 1
    assert len(emperors) == 4
    assert len(warlords) == 7
    assert len(set(elite)) == 12


def test_ranked_match_within_window_only(monkeypatch, tmp_path) -> None:
    _temp_rank_db(monkeypatch, tmp_path)
    rooms = RoomManager(_catalog)
    mm = RankedMatchmaker(rooms)

    with patch("battle.matchmaking.get_rating", side_effect=lambda uid: {"user_a": 1000, "user_b": 1400}.get(uid, 1000)):
        first = mm.join(_player("user_a", "A"))
        assert first["status"] == "queued"
        second = mm.join(_player("user_b", "B"))
        assert second["status"] == "queued"
        assert len(mm.waiting) == 2

        mm.waiting[0].joined_at = time.time() - 11
        mm.waiting[1].joined_at = time.time() - 11
        mm.by_user["user_a"].joined_at = time.time() - 11
        third = mm.join(_player("user_b", "B"))
        assert third["status"] == "matched"


def test_guest_cannot_join_ranked() -> None:
    rooms = RoomManager(_catalog)
    mm = RankedMatchmaker(rooms)
    try:
        mm.join(_player("guest_abc", "G"))
        assert False, "expected PermissionError"
    except PermissionError:
        pass


def test_apply_match_result_idempotent(monkeypatch, tmp_path) -> None:
    _temp_rank_db(monkeypatch, tmp_path)

    room = SimpleNamespace(
        ranked=True,
        code="ABC123",
        replay_id="r1",
        seats=[
            SimpleNamespace(user_id="user_1", username="A", is_ai=False),
            SimpleNamespace(user_id="user_2", username="B", is_ai=False),
        ],
        match=SimpleNamespace(status="finished", winner_seat=0),
    )
    first = apply_match_result(room)
    assert first is not None
    second = apply_match_result(room)
    assert second is None

    p1 = get_user_profile("user_1")
    p2 = get_user_profile("user_2")
    assert p1["games"] == 1
    assert p2["games"] == 1
    assert p1["wins"] == 1
    assert p2["losses"] == 1


def test_appeal_review_token_and_email_approve(monkeypatch, tmp_path) -> None:
    _temp_rank_db(monkeypatch, tmp_path)
    monkeypatch.setenv("RANK_APPEAL_ADMIN_TOKEN", "test-secret-token")
    from battle.rank import (
        make_appeal_review_token,
        review_ranked_appeal,
        submit_ranked_appeal,
        verify_appeal_review_token,
    )

    room = SimpleNamespace(
        ranked=True,
        code="APL001",
        replay_id="rp1",
        seats=[
            SimpleNamespace(user_id="user_30", username="A", is_ai=False),
            SimpleNamespace(user_id="user_31", username="B", is_ai=False),
        ],
        match=SimpleNamespace(status="finished", winner_seat=1),
    )
    apply_match_result(room)
    appeal = submit_ranked_appeal(
        "user_30",
        "A",
        room_code="APL001",
        description="第三回合无法阻挡，界面卡住",
        replay_id="rp1",
    )
    aid = int(appeal["appeal_id"])
    tok = make_appeal_review_token(aid, "approve")
    assert verify_appeal_review_token(aid, "approve", tok)
    assert not verify_appeal_review_token(aid, "reject", tok)

    review_ranked_appeal(aid, "approve", note="email-link")
    p0 = get_user_profile("user_30")
    p1 = get_user_profile("user_31")
    assert p0["rating"] == 1000 and p1["rating"] == 1000
    assert p0["games"] == 0 and p1["games"] == 0

    _temp_rank_db(monkeypatch, tmp_path)
    from battle.rank import revert_ranked_match

    room = SimpleNamespace(
        ranked=True,
        code="REV001",
        replay_id="r1",
        seats=[
            SimpleNamespace(user_id="user_20", username="A", is_ai=False),
            SimpleNamespace(user_id="user_21", username="B", is_ai=False),
        ],
        match=SimpleNamespace(status="finished", winner_seat=0),
    )
    apply_match_result(room)
    p1 = get_user_profile("user_20")
    p2 = get_user_profile("user_21")
    assert p1["games"] == 1 and p1["wins"] == 1
    assert p2["games"] == 1 and p2["losses"] == 1

    revert_ranked_match("REV001")
    p1b = get_user_profile("user_20")
    p2b = get_user_profile("user_21")
    assert p1b["rating"] == 1000
    assert p2b["rating"] == 1000
    assert p1b["games"] == 0
    assert p2b["games"] == 0

    again = revert_ranked_match("REV001")
    assert again.get("already_reverted") is True

    _temp_rank_db(monkeypatch, tmp_path)
    room = SimpleNamespace(
        ranked=True,
        code="DRAW01",
        replay_id=None,
        seats=[
            SimpleNamespace(user_id="user_10", username="A", is_ai=False),
            SimpleNamespace(user_id="user_11", username="B", is_ai=False),
        ],
        match=SimpleNamespace(status="finished", winner_seat=None),
    )
    apply_match_result(room)
    p1 = get_user_profile("user_10")
    p2 = get_user_profile("user_11")
    assert p1["draws"] == 1
    assert p2["draws"] == 1


def test_elite_badges_for_user_ids(monkeypatch, tmp_path) -> None:
    _temp_rank_db(monkeypatch, tmp_path)
    from battle.rank import _db, _ensure_user, _rank_lock

    with _rank_lock:
        conn = _db()
        try:
            _ensure_user(conn, "user_king")
            conn.execute(
                "UPDATE user_ratings SET rating = ?, peak_rating = ? WHERE user_id = ?",
                (2600, 2600, "user_king"),
            )
            conn.commit()
        finally:
            conn.close()

    badges = elite_badges_for_user_ids(["user_king", "user_plain", "guest_1"])
    assert badges["user_king"]["elite_title"] == "pirate_king"
    assert badges["user_king"]["elite_title_zh"] == "海賊王"
    assert badges["user_plain"]["elite_title"] is None
    assert "guest_1" not in badges
