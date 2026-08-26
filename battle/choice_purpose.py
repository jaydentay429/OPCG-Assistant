"""UI purpose labels for PendingChoice (ko / trash / play / …)."""

from __future__ import annotations

from typing import Any

# Keep in sync with frontend play.choice_purpose_* keys.
KNOWN_PURPOSES = frozenset(
    {
        "ko",
        "trash",
        "buff",
        "rest",
        "return_hand",
        "bottom",
        "play",
    "attach_don",
    "return_don",
    "choose_effect",
    "life",
    "grant_keyword",
    "grant_cost",
    "reduce_cost",
    "set_active",
    "skip_untap",
    "deck_order",
    "general",
}
)

_OP_PURPOSE: dict[str, str] = {
    "ko": "ko",
    "trash": "trash",
    "trash_hand": "trash",
    "trash_character": "trash",
    "trash_stage": "trash",
    "trash_top": "trash",
    "trash_life": "trash",
    "buff": "buff",
    "buff_self": "buff",
    "buff_all_own": "buff",
    "set_base_power": "buff",
    "set_base_power_from_character": "buff",
    "rest": "rest",
    "rest_character": "rest",
    "rest_opponent_character": "rest",
    "rest_opponent_char_or_don": "rest",
    "rest_don": "rest",
    "skip_untap": "skip_untap",
    "return_to_hand": "return_hand",
    "add_from_trash": "return_hand",
    "life_to_hand": "return_hand",
    "play_from_hand": "play",
    "play_from_trash": "play",
    "place_on_bottom": "bottom",
    "bottom_deck": "bottom",
    "deck_bottom": "bottom",
    "return_to_bottom": "bottom",
    "opponent_hand_to_bottom": "bottom",
    "attach_don": "attach_don",
    "return_don": "return_don",
    "choose_one": "choose_effect",
    "choose_effect": "choose_effect",
    "hand_to_life": "life",
    "place_on_life": "life",
    "flip_life": "life",
    "add_life": "life",
    "deck_top_to_life": "life",
    "grant_keyword": "grant_keyword",
    "grant_cost": "grant_cost",
    "reduce_cost": "reduce_cost",
    "set_cost": "reduce_cost",
    "set_character_active": "set_active",
}


_KW_SUMMARY = {
    "blockerless": "Gain Unblockable / 獲得【防禦不可】",
    "rush": "Gain Rush / 獲得【速攻】",
    "rush_character": "Gain Rush (Characters) / 獲得【速攻：角色】",
    "blocker": "Gain Blocker / 獲得【防禦】",
    "double_attack": "Gain Double Attack / 獲得【雙重攻擊】",
    "banish": "Gain Banish / 獲得【排除】",
}


def grant_keyword_choice_summary(op: dict[str, Any] | None) -> str:
    """Human-readable choice title for grant_keyword target picks."""
    if not op:
        return "Grant keyword"
    if op.get("summary"):
        return str(op.get("summary"))[:160]
    kw = str(op.get("keyword") or "").strip().lower()
    return _KW_SUMMARY.get(kw, f"Grant {kw or 'keyword'}")[:160]


def purpose_from_op(op: dict[str, Any] | None) -> str:
    if not op:
        return "general"
    explicit = str(op.get("purpose") or "").strip().lower()
    if explicit in KNOWN_PURPOSES:
        return explicit
    kind = str(op.get("op") or "").strip().lower()
    if kind in _OP_PURPOSE:
        return _OP_PURPOSE[kind]
    if op.get("as_cost") and kind.startswith("trash"):
        return "trash"
    return "general"


def purpose_from_summary(summary: str) -> str:
    s = str(summary or "").strip().lower()
    if not s:
        return "general"
    # Order matters: more specific cues before generic「手牌」.
    if any(x in s for x in ("登場", "登场", "play a", "play from", "play character", "play the")):
        return "play"
    if "play" in s and "hand" in s:
        return "play"
    if any(x in s for x in ("擊破", "击破", "k.o", "ko ")):
        return "ko"
    if s in {"ko", "k.o.", "k.o"} or s.startswith("ko ") or s.startswith("k.o"):
        return "ko"
    if any(x in s for x in ("生命", "life")):
        return "life"
    if any(x in s for x in ("卡組下面", "卡组下面", "deck bottom", "bottom of", "on bottom", "place on bottom")):
        return "bottom"
    if any(x in s for x in ("廢棄", "废弃", "trash", "送入廢棄", "送入废弃")):
        return "trash"
    if any(x in s for x in ("放回手牌", "加入手牌", "return to hand", "add to hand", "to owner's hand", "to the own")):
        return "return_hand"
    if any(x in s for x in ("休息", "rest")):
        return "rest"
    if any(x in s for x in ("力量", "power", "buff", "+power", "−power", "-power")):
        return "buff"
    if "don!!" in s or "don" in s and "attach" in s:
        return "attach_don"
    if any(
        x in s
        for x in (
            "unblockable",
            "blockerless",
            "防禦不可",
            "防御不可",
            "速攻",
            "rush",
            "grant ",
            "獲得【",
            "获得【",
            "gains [",
            "gain [",
        )
    ):
        return "grant_keyword"
    if any(x in s for x in ("費用+", "费用+", "cost +", "+cost", "grant_cost", "費用−", "费用−", "−cost", "-cost")):
        if any(x in s for x in ("−", "-", "reduce", "減少", "减少")):
            return "reduce_cost"
        return "grant_cost"
    if any(x in s for x in ("選擇效果", "选择效果", "choose effect", "choose one", "choose:")):
        return "choose_effect"
    return "general"


def pending_choice_purpose(pending: Any) -> str:
    """Resolve UI purpose for a PendingChoice (never invent trash for hand picks)."""
    purpose = str(getattr(pending, "purpose", "") or "").strip().lower()
    if purpose in KNOWN_PURPOSES and purpose != "general":
        return purpose

    then = getattr(pending, "then_op", None)
    if isinstance(then, dict) and then.get("op"):
        p = purpose_from_op(then)
        if p != "general":
            return p

    ops = list(getattr(pending, "remaining_ops", None) or [])
    if ops and isinstance(ops[0], dict):
        p = purpose_from_op(ops[0])
        if p != "general":
            return p

    summary_p = purpose_from_summary(str(getattr(pending, "summary", "") or ""))
    if summary_p != "general":
        return summary_p

    target = str(getattr(pending, "target_kind", "") or "").strip().lower()
    if target == "effect_option":
        return "choose_effect"
    if target == "life_position":
        return "life"
    # Explicit empty/general purpose wins over inventing trash for hand_card.
    if purpose == "general":
        return "general"
    return "general"
