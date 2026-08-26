from battle.choice_purpose import pending_choice_purpose, purpose_from_op
from battle.state import PendingChoice


def test_hand_card_no_longer_defaults_to_trash():
    empty = PendingChoice(
        seat=0,
        card_id="X",
        source_iid="s",
        target_kind="hand_card",
        options=["hand:0:A"],
    )
    assert pending_choice_purpose(empty) == "general"


def test_play_from_hand_purpose():
    pc = PendingChoice(
        seat=0,
        card_id="OP15-054",
        source_iid="s",
        target_kind="hand_card",
        options=["hand:0:A"],
        purpose="play",
        then_op={"op": "play_from_hand"},
        summary="使費用4以下《多雷斯羅薩》角色卡登場",
    )
    assert pending_choice_purpose(pc) == "play"
    assert purpose_from_op({"op": "play_from_hand"}) == "play"


def test_trash_hand_still_trash():
    pc = PendingChoice(
        seat=0,
        card_id="X",
        source_iid="s",
        target_kind="hand_card",
        options=["hand:0:A"],
        purpose="trash",
        remaining_ops=[{"op": "trash_hand"}],
    )
    assert pending_choice_purpose(pc) == "trash"


def test_bottom_and_life_hand_choices():
    bottom = PendingChoice(
        seat=1,
        card_id="X",
        source_iid="s",
        target_kind="hand_card",
        options=["hand:0:A"],
        remaining_ops=[{"op": "opponent_hand_to_bottom"}],
        summary="Opponent: place 1 hand card(s) on deck bottom",
    )
    assert pending_choice_purpose(bottom) == "bottom"

    life = PendingChoice(
        seat=0,
        card_id="X",
        source_iid="s",
        target_kind="hand_card",
        options=["hand:0:A"],
        then_op={"op": "hand_to_life", "count": 1},
        summary="Add 1 card from hand to Life",
    )
    assert pending_choice_purpose(life) == "life"


def test_field_ops_from_remaining():
    assert (
        pending_choice_purpose(
            PendingChoice(
                seat=0,
                card_id="X",
                source_iid="s",
                target_kind="opponent_character",
                options=["c1"],
                remaining_ops=[{"op": "return_to_hand"}],
            )
        )
        == "return_hand"
    )
    assert (
        pending_choice_purpose(
            PendingChoice(
                seat=0,
                card_id="X",
                source_iid="s",
                target_kind="opponent_character",
                options=["c1"],
                remaining_ops=[{"op": "trash"}],
            )
        )
        == "trash"
    )
    assert purpose_from_op({"op": "rest_opponent_character"}) == "rest"
