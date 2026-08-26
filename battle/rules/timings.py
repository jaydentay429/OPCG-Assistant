"""Official keyword timings ↔ engine timing strings (综合规则 第8 / 第10章)."""

from __future__ import annotations

# Engine timing ids (must stay in sync with battle.effect_schema.TIMINGS).
ON_PLAY = "on_play"
WHEN_ATTACKING = "when_attacking"
ON_BLOCK = "on_block"
ON_OPPONENT_ATTACK = "on_opponent_attack"
ON_KO = "on_ko"
END_OF_YOUR_TURN = "end_of_your_turn"
END_OF_OPPONENT_TURN = "end_of_opponent_turn"
TURN_START = "turn_start"
MAIN_START = "main_start"
ACTIVATE_MAIN = "activate_main"
TRIGGER = "trigger"
COUNTER_EVENT = "counter_event"
YOUR_TURN = "your_turn"
OPPONENT_TURN = "opponent_turn"
DON_ATTACHED = "don_attached"
ON_DON_ATTACHED = "on_don_attached"

# Chinese / English text markers → engine timing (best-effort).
TEXT_TO_TIMING: dict[str, str] = {
    "【登場時】": ON_PLAY,
    "【登场时】": ON_PLAY,
    "[on play]": ON_PLAY,
    "【攻擊時】": WHEN_ATTACKING,
    "【攻击时】": WHEN_ATTACKING,
    "[when attacking]": WHEN_ATTACKING,
    "【阻擋時】": ON_BLOCK,
    "【阻挡时】": ON_BLOCK,
    "【防禦時】": ON_BLOCK,
    "【防御时】": ON_BLOCK,
    "[on block]": ON_BLOCK,
    "【對方的攻擊時】": ON_OPPONENT_ATTACK,
    "【对方的攻击时】": ON_OPPONENT_ATTACK,
    "【對方攻擊時】": ON_OPPONENT_ATTACK,
    "【对方攻击时】": ON_OPPONENT_ATTACK,
    "[on your opponent's attack]": ON_OPPONENT_ATTACK,
    "【KO時】": ON_KO,
    "【KO时】": ON_KO,
    "[on k.o.]": ON_KO,
    "【我方的回合結束時】": END_OF_YOUR_TURN,
    "【我方的回合结束时】": END_OF_YOUR_TURN,
    "[end of your turn]": END_OF_YOUR_TURN,
    "【對方的回合結束時】": END_OF_OPPONENT_TURN,
    "【对方的回合结束时】": END_OF_OPPONENT_TURN,
    "[end of your opponent's turn]": END_OF_OPPONENT_TURN,
    "【我方的回合開始時】": TURN_START,
    "【我方的回合开始时】": TURN_START,
    "[start of your turn]": TURN_START,
    "【啟動主要】": ACTIVATE_MAIN,
    "【启动主要】": ACTIVATE_MAIN,
    "[activate: main]": ACTIVATE_MAIN,
    "【觸發器】": TRIGGER,
    "【触发器】": TRIGGER,
    "[trigger]": TRIGGER,
    "【反擊】": COUNTER_EVENT,
    "【反击】": COUNTER_EVENT,
    "[counter]": COUNTER_EVENT,
    "【我方回合中】": YOUR_TURN,
    "[your turn]": YOUR_TURN,
    "【對方回合中】": OPPONENT_TURN,
    "【对方回合中】": OPPONENT_TURN,
    "[opponent's turn]": OPPONENT_TURN,
}

# Regex used to detect which timings appear in card text (compile stubs / fill-gaps).
TIMING_DETECT_PATTERNS: dict[str, str] = {
    # Events: [Main]/【主要】 resolve when played → on_play. Character [Activate: Main] is ACTIVATE_MAIN
    # (different brackets/text; 【啟動主要】 does not contain a separate 【主要】 token).
    ON_PLAY: r"\[on play\]|【登場時】|【登场时】|\[main\]|【主要】",
    WHEN_ATTACKING: r"\[when attacking\]|【攻擊時】|【攻击时】",
    ON_BLOCK: r"\[on block\]|【阻擋時】|【阻挡时】|【防禦時】|【防御时】",
    ON_OPPONENT_ATTACK: (
        r"\[on your opponent'?s attack\]|【對方的?攻擊時】|【对方的?攻击时】|"
        r"【對方攻擊時】|【对方攻击时】"
    ),
    ON_KO: r"\[on\s*k\.?o\.?\]|【KO時】|【KO时】",
    END_OF_YOUR_TURN: r"\[end of your turn\]|【我方的?回合結束時】|【我方的?回合结束时】",
    END_OF_OPPONENT_TURN: r"\[end of your opponent'?s turn\]|【對方的?回合結束時】|【对方的?回合结束时】",
    TURN_START: r"\[start of your turn\]|【我方的?回合開始時】|【我方的?回合开始时】",
    ACTIVATE_MAIN: r"\[activate:\s*main\]|【啟動主要】|【启动主要】",
    TRIGGER: r"\[trigger\]|【觸發器】|【触发器】|【触发】",
    COUNTER_EVENT: r"\[counter\]|【反擊】|【反击】",
    YOUR_TURN: r"\[your turn\]|【我方回合中】",
    OPPONENT_TURN: r"\[opponent'?s turn\]|【對方回合中】|【对方回合中】",
    ON_DON_ATTACHED: r"\[when (?:this card is )?don!! attached\]|【咚‼?附加時】|【咚附加时】",
}

# Rule ids that define when each automatic timing fires.
TIMING_RULE_REFS: dict[str, tuple[str, ...]] = {
    ON_PLAY: ("8-1-3-1-1", "10-2-1"),
    WHEN_ATTACKING: ("7-1-1", "10-2-2"),
    ON_BLOCK: ("7-1-2-2", "10-2-6"),
    ON_OPPONENT_ATTACK: ("8-1-3-1-1",),
    ON_KO: ("8-1-3-1-1", "10-2-5"),
    END_OF_YOUR_TURN: ("6-6-1-1", "10-2-7"),
    END_OF_OPPONENT_TURN: ("6-6-1-1", "10-2-8"),
    TURN_START: ("6-2-2",),
    MAIN_START: ("6-5-1",),
}
