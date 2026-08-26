#!/usr/bin/env python3
"""Semantic fixes v58 open-34 batch.

Rebuilds 34 base-card encodings with correct ops, gates, and structure.
Dual-writes library + overrides. Syncs P/R variants.
Writes meta/logs/ops_v58_open34_ids.txt.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry, sanitize_ops_list  # noqa: E402

OUT_IDS = ROOT / "meta" / "logs" / "ops_v58_open34_ids.txt"


def _base(cid: str) -> str:
    return re.sub(r"-(P\d+|R\d+|SP\d+|ALT)$", "", cid)


def _ab(timing: str, ops: list[dict[str, Any]], summary: str, **gates: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "timing": timing,
        "summary": summary,
        "ops": sanitize_ops_list(ops),
        "status": "compiled",
        "confidence": 0.95,
    }
    out.update(gates)
    return out


REBUILDS: dict[str, list[dict[str, Any]]] = {
    # EB01-052 碧歐菈 – on_play choose_one: reorder opp life OR flip all own life face-down
    "EB01-052": [
        _ab(
            "on_play",
            [
                {
                    "op": "choose_one",
                    "chooser": "self",
                    "options": [
                        {
                            "id": "reorder",
                            "label": "查看對手全數的生命值卡，並依任意順序放置",
                            "ops": [{"op": "reorder_life", "owner": "opponent"}],
                        },
                        {
                            "id": "flip",
                            "label": "將自己的生命值卡全數翻成背面朝上",
                            "ops": [{"op": "flip_life", "face": "down", "optional": False, "all": True}],
                        },
                    ],
                }
            ],
            "【登場時】選擇下列其中一項：查看對手全數生命值卡任意順序放置，或將自己生命值卡全數翻成背面朝上。",
        ),
    ],

    # EB04-055 大熊 – on_ko: play ≤4 cost Rev Army char from hand (no gate); trigger: total life≤5 + leader RevArmy
    "EB04-055": [
        _ab(
            "on_ko",
            [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 4,
                    "trait_contains": "Revolutionary Army|革命軍",
                    "from_zone": "hand",
                }
            ],
            "【KO時】使最多1張自己手牌中費用4以下擁有《革命軍》特徵的角色卡登場。",
        ),
        _ab(
            "trigger",
            [{"op": "play_from_hand", "count": 1, "card_type": "character", "optional": True, "from_zone": "hand"}],
            "【觸發器】若自己的領航卡擁有《革命軍》特徵、雙方的生命值卡合計張數在5張以下時，使這張卡片登場。",
            require_total_life_lte=5,
            require_leader_trait="Revolutionary Army|革命軍",
        ),
    ],

    # OP01-002 羅 (L) – activate_main once don×2: if own chars≥5, return 1 own char, play ≤5 cost different-color char
    "OP01-002": [
        _ab(
            "activate_main",
            [
                {"op": "rest_don", "count": 2, "owner": "self", "as_cost": True},
                {"op": "return_to_hand", "target_kind": "own_character", "optional": False},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 5,
                    "from_zone": "hand",
                },
            ],
            "【啟動主要】【每回合1次】②：若場上有5張自己的角色卡時，將1張自己的角色卡放回手牌，並從手牌中使最多1張不同顏色費用5以下的角色卡登場。",
            once=True,
            cost_don=2,
            rest_self=False,
            require_chars_gte=5,
        ),
    ],

    # OP03-041 騙人布 – when_attacking don×1: on life damage, trash top 7 own deck
    "OP03-041": [
        _ab(
            "when_attacking",
            [{"op": "trash_deck_top", "count": 7, "optional": True, "on_life_damage": True}],
            "【咚‼×1】因為這張角色卡的攻擊，而造成對手生命值傷害時，可將7張自己卡組上面的卡片放置到廢棄區。",
            require_don_attached_gte=1,
        ),
    ],

    # OP04-094 轟雷破壞劍 (Event) – main: KO ≤4 (≤6 if trash≥15); trigger: rest own leader → KO ≤5
    "OP04-094": [
        _ab(
            "on_play",
            [{"op": "ko", "target_kind": "opponent_character", "optional": True, "cost_lte": 4}],
            "【主要】選擇最多1張對手費用4以下的角色卡，並KO。",
        ),
        _ab(
            "on_play",
            [{"op": "ko", "target_kind": "opponent_character", "optional": True, "cost_lte": 6}],
            "【主要】（若自己廢棄區有15張以上卡片時）選擇最多1張對手費用6以下的角色卡，並KO。",
            require_trash_gte=15,
        ),
        _ab(
            "trigger",
            [
                {"op": "rest_character", "target_kind": "leader", "as_cost": True, "optional": True},
                {"op": "ko", "target_kind": "opponent_character", "optional": True, "cost_lte": 5},
            ],
            "【觸發器】可將自己的領航卡置為休息狀態：KO最多1張對手費用5以下的角色卡。",
        ),
    ],

    # OP05-005 卡拉司 – on_play if RevArmy leader: opp -1000; when_attacking if power≥7000: opp -1000
    "OP05-005": [
        _ab(
            "on_play",
            [
                {
                    "op": "buff",
                    "amount": -1000,
                    "target_kind": "opponent_leader_or_character",
                    "optional": True,
                }
            ],
            "【登場時】若自己的領航卡擁有《革命軍》特徵時，最多1張對手的領航卡或角色卡，在這個回合，力量值-1000。",
            require_leader_trait="Revolutionary Army|革命軍",
        ),
        _ab(
            "when_attacking",
            [
                {
                    "op": "buff",
                    "amount": -1000,
                    "target_kind": "opponent_leader_or_character",
                    "optional": True,
                }
            ],
            "【攻擊時】若這張角色卡的力量值7000以上時，最多1張對手的領航卡或角色卡，在這個回合，力量值-1000。",
            require_source_power_gte=7000,
        ),
    ],

    # OP05-099 愛紗 – on_opponent_attack rest self: opp may trash their top life; if not, opp -2000
    "OP05-099": [
        _ab(
            "on_opponent_attack",
            [
                {"op": "trash_life", "count": 1, "position": "top", "owner": "opponent", "optional": True},
                {
                    "op": "buff",
                    "amount": -2000,
                    "target_kind": "opponent_leader_or_character",
                    "optional": True,
                },
            ],
            "【對方攻擊時】可將這張角色卡置為休息狀態：對手可將1張自身生命值區上面的卡片放置到廢棄區。若沒有執行此動作時，最多1張對手的領航卡或角色卡，在這個回合，力量值-2000。",
            rest_self=True,
        ),
    ],

    # OP06-065 尼吉士 – on_play if own DON≤opp DON: choose_one KO≤2 OR return≤4 to hand
    "OP06-065": [
        _ab(
            "on_play",
            [
                {
                    "op": "choose_one",
                    "chooser": "self",
                    "options": [
                        {
                            "id": "ko",
                            "label": "KO最多1張對手費用2以下的角色卡",
                            "ops": [
                                {
                                    "op": "ko",
                                    "target_kind": "opponent_character",
                                    "optional": True,
                                    "cost_lte": 2,
                                }
                            ],
                        },
                        {
                            "id": "return",
                            "label": "將最多1張對手費用4以下的角色卡放回持有者的手牌",
                            "ops": [
                                {
                                    "op": "return_to_hand",
                                    "target_kind": "opponent_character",
                                    "optional": True,
                                    "cost_lte": 4,
                                }
                            ],
                        },
                    ],
                }
            ],
            "【登場時】若自己場上的咚‼卡少於等於對手場上的咚‼卡時，選擇下列其中一項：KO最多1張對手費用2以下的角色卡，或將最多1張對手費用4以下的角色卡放回持有者的手牌。",
            require_don_field_deficit_gte=0,
        ),
    ],

    # OP06-099 愛紗 – on_play: look top 1 of own or opp life, place to top or bottom
    "OP06-099": [
        _ab(
            "on_play",
            [
                {
                    "op": "look_life",
                    "count": 1,
                    "owner": "self_or_opponent",
                    "position": "top",
                    "to_top_or_bottom": True,
                    "optional": True,
                }
            ],
            "【登場時】查看最多1張自己或對手生命值區上面的卡片，並放置在生命值區的上面或下面。",
        ),
    ],

    # OP07-029 霍金斯 – continuous blocker if Supernovas leader; replace_leave opp_remove: rest 1 opp char
    "OP07-029": [
        _ab(
            "your_turn",
            [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
            "若自己的領航卡擁有《超新星》特徵時，這張角色卡獲得【防禦】。",
            require_leader_trait="Supernovas|超新星",
        ),
        _ab(
            "opponent_turn",
            [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
            "若自己的領航卡擁有《超新星》特徵時，這張角色卡獲得【防禦】。",
            require_leader_trait="Supernovas|超新星",
        ),
        _ab(
            "your_turn",
            [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "self",
                    "cost": "rest_other_character",
                    "rest_count": 1,
                    "optional": True,
                }
            ],
            "【每回合1次】若這張角色卡因對手的效果即將離開場上時，可以替換成將1張對手的角色卡置為休息狀態。",
            once=True,
        ),
        _ab(
            "opponent_turn",
            [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "self",
                    "cost": "rest_other_character",
                    "rest_count": 1,
                    "optional": True,
                }
            ],
            "【每回合1次】若這張角色卡因對手的效果即將離開場上時，可以替換成將1張對手的角色卡置為休息狀態。",
            once=True,
        ),
    ],

    # OP08-057 KING (L) – activate_main don-2: choose_one draw(if hand≤5) OR reduce_cost -2 opp char
    "OP08-057": [
        _ab(
            "activate_main",
            [
                {"op": "return_don", "count": 2, "owner": "self", "as_cost": True},
                {
                    "op": "choose_one",
                    "chooser": "self",
                    "options": [
                        {
                            "id": "draw",
                            "label": "若自己的手牌在5張以下時，抽1張卡片",
                            "ops": [{"op": "draw", "count": 1}],
                            "require_hand_lte": 5,
                        },
                        {
                            "id": "reduce",
                            "label": "最多1張對手的角色卡，在這個回合，費用-2",
                            "ops": [
                                {
                                    "op": "reduce_cost",
                                    "amount": -2,
                                    "count": 1,
                                    "target_kind": "opponent_character",
                                    "optional": True,
                                }
                            ],
                        },
                    ],
                },
            ],
            "【啟動主要】【每回合1次】咚‼-2：選擇下列其中一項：若手牌5張以下，抽1張；或最多1張對手角色卡費用-2。",
            once=True,
            cost_don=0,
            rest_self=False,
        ),
    ],

    # OP09-009 班・貝克曼 – on_play: trash up to 1 opp char with power ≤6000
    "OP09-009": [
        _ab(
            "on_play",
            [
                {
                    "op": "trash",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "power_lte": 6000,
                }
            ],
            "【登場時】將最多1張對手力量值6000以下的角色卡放置到廢棄區。",
        ),
    ],

    # OP11-012 佛朗基 – on_opp_event your_turn once: all own chars +2000 this turn
    "OP11-012": [
        _ab(
            "on_opp_event",
            [{"op": "buff_all_own", "amount": 2000, "include_leader": False}],
            "【我方回合中】【每回合1次】對手發動事件卡時，自己的角色卡全數，在這個回合，力量值+2000。",
            once=True,
            require_your_turn=True,
        ),
    ],

    # OP11-065 夏洛特・亞娜娜 – continuous blocker if other own purple BIG MOM char on field
    "OP11-065": [
        _ab(
            "your_turn",
            [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
            "若場上有除了「夏洛特・亞娜娜」以外自己紫色擁有《BIG MOM海賊團》特徵的角色卡時，這張角色卡獲得【防禦】。",
            require_other_chars_trait="BIG MOM海賊団|BIG MOM海賊團|Big Mom Pirates",
        ),
        _ab(
            "opponent_turn",
            [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
            "若場上有除了「夏洛特・亞娜娜」以外自己紫色擁有《BIG MOM海賊團》特徵的角色卡時，這張角色卡獲得【防禦】。",
            require_other_chars_trait="BIG MOM海賊団|BIG MOM海賊團|Big Mom Pirates",
        ),
    ],

    # OP11-073 莉莉 – on_opponent_attack once don-5 if BIG MOM leader: declare cost, look top opp deck;
    # if cost matches, own leader +2000
    "OP11-073": [
        _ab(
            "on_opponent_attack",
            [
                {"op": "return_don", "count": 5, "owner": "self", "as_cost": True},
                {"op": "look_opp_deck", "count": 1, "position": "top", "declare_cost": True},
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "if_declared_cost_match": True,
                },
            ],
            "【對方攻擊時】【每回合1次】咚‼-5：聲明任意費用，公開1張對手卡組上面的卡片。若費用一致時，最多1張自己的領航卡，在這個回合，力量值+2000。",
            once=True,
            require_leader_trait="BIG MOM海賊団|BIG MOM海賊團|Big Mom Pirates",
            cost_don=0,
        ),
    ],

    # OP12-020 索隆 (L) – activate_main once don×3: set SELF active this turn; then leader can't attack ≤7 base cost chars
    "OP12-020": [
        _ab(
            "activate_main",
            [
                {"op": "set_character_active", "count": 1, "target_kind": "self", "optional": False},
                {
                    "op": "deny_attack",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "base_cost_lte": 7,
                    "duration": "turn",
                },
            ],
            "【咚‼×3】【啟動主要】【每回合1次】在這個回合，將這張領航卡置為活動狀態。之後，這張領航卡，在這個回合，無法攻擊對手原本費用7以下的角色卡。",
            once=True,
            cost_don=0,
            rest_self=False,
            require_don_attached_gte=3,
        ),
    ],

    # OP14-016 X・多雷古 – opponent_turn once: if own Supernovas char would leave by opp effect,
    # replace with leader -2000 this turn; when_attacking don×1: opp char -2000
    "OP14-016": [
        _ab(
            "opponent_turn",
            [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "self_power_minus",
                    "amount": -2000,
                    "trait_contains": "Supernovas|超新星",
                    "optional": True,
                }
            ],
            "【對方回合中】【每回合1次】若自己擁有《超新星》特徵的角色卡因對手的效果即將離開場上時，可以替換成自己的領航卡，在這個回合，力量值-2000。",
            once=True,
        ),
        _ab(
            "when_attacking",
            [
                {
                    "op": "buff",
                    "amount": -2000,
                    "target_kind": "opponent_character",
                    "optional": True,
                }
            ],
            "【咚‼×1】【攻擊時】最多1張對手的角色卡，在這個回合，力量值-2000。",
            require_don_attached_gte=1,
        ),
    ],

    # OP15-026 傑克斯 – on_play: look top 3 search East Blue trait to hand;
    # activate_main: attach opp rested DON to opp char (cost) → attach own rested DON to own leader/char
    "OP15-026": [
        _ab(
            "on_play",
            [
                {
                    "op": "search_deck",
                    "trait_contains": "East Blue|東方藍",
                    "top_n": 3,
                    "max_add": 1,
                    "order_bottom": True,
                    "destination": "hand",
                    "reveal_adds": True,
                }
            ],
            "【登場時】從自己的卡組上面查看3張卡片，公開最多1張擁有《東方藍》特徵的卡片，並加入手牌。之後，將其餘卡片依任意順序放到卡組下面。",
        ),
        _ab(
            "activate_main",
            [
                {
                    "op": "attach_don",
                    "count": 1,
                    "target_kind": "opponent_character",
                    "from_owner": "opponent",
                    "as_rested": True,
                    "as_cost": True,
                    "optional": False,
                },
                {
                    "op": "attach_don",
                    "count": 1,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                },
            ],
            "【啟動主要】可以附加1張對手休息狀態的咚‼卡在1張對手的角色卡：附加最多1張持有者休息狀態的咚‼卡在1張領航卡或角色卡。",
            once=False,
            cost_don=0,
            rest_self=False,
        ),
    ],

    # OP16-003 紐蓋特 – your_turn: leader gets Double Attack + power +2000;
    # on_play: reveal 2 hand power-8000 chars → opp char -6000
    "OP16-003": [
        _ab(
            "your_turn",
            [
                {"op": "buff_self", "amount": 2000},
                {"op": "grant_keyword", "keyword": "double_attack", "target_kind": "self", "duration": "turn"},
            ],
            "【我方回合中】自己的領航卡獲得【雙重攻擊】、力量值+2000。",
        ),
        _ab(
            "on_play",
            [
                {
                    "op": "reveal_hand",
                    "count": 2,
                    "card_type": "character",
                    "power_eq": 8000,
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "buff",
                    "amount": -6000,
                    "target_kind": "opponent_character",
                    "optional": True,
                },
            ],
            "【登場時】可以公開2張自己手牌中力量值8000的角色卡：最多1張對手的角色卡，在這個回合，力量值-6000。",
        ),
    ],

    # P-088 羅 – trigger: play self; gate total life≤5 + Supernovas leader
    "P-088": [
        _ab(
            "trigger",
            [{"op": "play_from_hand", "count": 1, "card_type": "character", "optional": True, "from_zone": "hand"}],
            "【觸發器】若自己的領航卡擁有《超新星》特徵、雙方的生命值卡合計張數在5張以下時，使這張卡片登場。",
            require_total_life_lte=5,
            require_leader_trait="Supernovas|超新星",
        ),
    ],

    # ST11-003 逆光 (Event) – main: if leader is Uta, choose_one: rest ≤5 opp char OR KO ≤5 rested opp char
    "ST11-003": [
        _ab(
            "on_play",
            [
                {
                    "op": "choose_one",
                    "chooser": "self",
                    "options": [
                        {
                            "id": "rest",
                            "label": "將最多1張對手費用5以下的角色卡置為休息狀態",
                            "ops": [{"op": "rest_opponent_character", "count": 1, "cost_lte": 5, "optional": True}],
                        },
                        {
                            "id": "ko",
                            "label": "KO最多1張對手休息狀態費用5以下的角色卡",
                            "ops": [
                                {
                                    "op": "ko",
                                    "target_kind": "opponent_character_rested",
                                    "optional": True,
                                    "cost_lte": 5,
                                }
                            ],
                        },
                    ],
                }
            ],
            "【主要】若自己的領航卡是「美音」時，選擇下列其中一項：將最多1張對手費用5以下的角色卡置為休息狀態，或KO最多1張對手休息狀態費用5以下的角色卡。",
            require_leader_name="Uta|美音",
        ),
    ],

    # ST16-005 魯夫 – continuous: if own Uta is rested, this char +1000
    "ST16-005": [
        _ab(
            "your_turn",
            [{"op": "buff_self", "amount": 1000}],
            "若自己的「美音」在休息狀態時，這張角色卡的力量值+1000。",
            require_rested_own_chars_gte=1,
            require_rested_own_chars_trait="Uta|美音",
        ),
        _ab(
            "opponent_turn",
            [{"op": "buff_self", "amount": 1000}],
            "若自己的「美音」在休息狀態時，這張角色卡的力量值+1000。",
            require_rested_own_chars_gte=1,
            require_rested_own_chars_trait="Uta|美音",
        ),
    ],

    # ST20-003 布璃叡 – trigger: look top 1 own or opp life, place to top/bottom (add this card to hand = auto)
    "ST20-003": [
        _ab(
            "trigger",
            [
                {
                    "op": "look_life",
                    "count": 1,
                    "owner": "self_or_opponent",
                    "position": "top",
                    "to_top_or_bottom": True,
                    "optional": True,
                }
            ],
            "【觸發器】查看最多1張自己或對手生命值區上面的卡片，並放置在生命值區的上面或下面。之後，將這張卡片加入手牌。",
        ),
    ],

    # OP03-114 莉莉 – on_play if BIG MOM leader: add top 1 own deck to own life top; trash top 1 opp life
    "OP03-114": [
        _ab(
            "on_play",
            [
                {"op": "add_life", "count": 1},
                {"op": "trash_life", "count": 1, "position": "top", "owner": "opponent", "optional": True},
            ],
            "【登場時】若自己的領航卡擁有《BIG MOM海賊團》特徵時，將最多1張自己卡組上面的卡片加入生命值區上面。之後，將最多1張對手生命值區上面的卡片放置到廢棄區。",
            require_leader_trait="BIG MOM海賊団|BIG MOM海賊團|Big Mom Pirates",
        ),
    ],

    # OP06-067 約吉士 – continuous both turns: if own DON≤opp DON, +1000
    "OP06-067": [
        _ab(
            "your_turn",
            [{"op": "buff_self", "amount": 1000}],
            "若自己場上的咚‼卡少於等於對手場上的咚‼卡時，這張角色卡的力量值+1000。",
            require_don_field_deficit_gte=0,
        ),
        _ab(
            "opponent_turn",
            [{"op": "buff_self", "amount": 1000}],
            "若自己場上的咚‼卡少於等於對手場上的咚‼卡時，這張角色卡的力量值+1000。",
            require_don_field_deficit_gte=0,
        ),
    ],

    # OP15-017 蒙卡 – activate_main once: attach opp rested DON to opp char (cost) → attach own rested DON to own leader/char
    "OP15-017": [
        _ab(
            "activate_main",
            [
                {
                    "op": "attach_don",
                    "count": 1,
                    "target_kind": "opponent_character",
                    "from_owner": "opponent",
                    "as_rested": True,
                    "as_cost": True,
                    "optional": False,
                },
                {
                    "op": "attach_don",
                    "count": 1,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                },
            ],
            "【啟動主要】【每回合1次】可以附加1張對手休息狀態的咚‼卡在1張對手的角色卡：附加最多1張持有者休息狀態的咚‼卡在1張領航卡或角色卡。",
            once=True,
            cost_don=0,
            rest_self=False,
        ),
    ],

    # ST10-007 奇拉 – on_don_returned your_turn once: KO ≤3 cost rested opp char
    "ST10-007": [
        _ab(
            "on_don_returned",
            [{"op": "ko", "target_kind": "opponent_character_rested", "optional": True, "cost_lte": 3}],
            "【我方回合中】【每回合1次】自己場上的咚‼卡被放回咚‼卡組時，KO最多1張對手休息狀態費用3以下的角色卡。",
            require_your_turn=True,
            once=True,
        ),
    ],

    # ST12-013 哲普 – on_play: look top 3, reorder; when_attacking: reveal top 1, play ≤2 cost char as rested
    "ST12-013": [
        _ab(
            "on_play",
            [{"op": "look_deck", "count": 3, "position": "top_or_bottom", "optional": False}],
            "【登場時】從自己的卡組上面查看3張卡片，並任意變換排列順序放到卡組上面或下面。",
        ),
        _ab(
            "when_attacking",
            [
                {
                    "op": "search_deck",
                    "top_n": 1,
                    "max_add": 1,
                    "cost_lte": 2,
                    "card_type": "character",
                    "destination": "play",
                    "as_rested": True,
                    "order_bottom": True,
                    "reveal_adds": True,
                }
            ],
            "【攻擊時】公開1張自己卡組上面的卡片，並使最多1張費用2的角色卡以休息狀態登場。之後，將其餘卡片放到卡組上面或下面。",
        ),
    ],

    # ST16-003 卡塔克利 – continuous both turns: if FILM leader + rested cards≥6, +2000
    "ST16-003": [
        _ab(
            "your_turn",
            [{"op": "buff_self", "amount": 2000}],
            "若自己的領航卡擁有《FILM》特徵，自己休息狀態的卡片有6張以上時，這張角色卡的力量值+2000。",
            require_leader_trait="FILM",
            require_rested_cards_gte=6,
        ),
        _ab(
            "opponent_turn",
            [{"op": "buff_self", "amount": 2000}],
            "若自己的領航卡擁有《FILM》特徵，自己休息狀態的卡片有6張以上時，這張角色卡的力量值+2000。",
            require_leader_trait="FILM",
            require_rested_cards_gte=6,
        ),
    ],

    # ST30-001 魯夫&艾斯 (L) – continuous both turns: if own char base≥7000, leader -2000;
    # opponent_turn: all own Ace/Luffy chars +3000
    "ST30-001": [
        _ab(
            "your_turn",
            [{"op": "buff_self", "amount": -2000}],
            "若場上有自己原本力量值7000以上的角色卡時，這張領航卡的力量值-2000。",
            require_field_char_base_power_gte=7000,
        ),
        _ab(
            "opponent_turn",
            [{"op": "buff_self", "amount": -2000}],
            "若場上有自己原本力量值7000以上的角色卡時，這張領航卡的力量值-2000。",
            require_field_char_base_power_gte=7000,
        ),
        _ab(
            "opponent_turn",
            [{"op": "buff_all_own", "amount": 3000, "include_leader": False}],
            "【對方回合中】自己的「波特卡斯・D・艾斯」和「蒙其・D・魯夫」全數，力量值+3000。",
        ),
    ],

    # ST30-011 巴其 – both turns: replace_leave opp_remove own filtered (base≥6000) cost rest_self
    "ST30-011": [
        _ab(
            "your_turn",
            [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "rest_self",
                    "base_power_gte": 6000,
                    "optional": True,
                }
            ],
            "自己原本力量值6000的角色卡因對手的效果即將離開場上時，可以替換成將這張角色卡置為休息狀態。",
        ),
        _ab(
            "opponent_turn",
            [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "rest_self",
                    "base_power_gte": 6000,
                    "optional": True,
                }
            ],
            "自己原本力量值6000的角色卡因對手的效果即將離開場上時，可以替換成將這張角色卡置為休息狀態。",
        ),
    ],

    # OP04-028 帝雅曼鐵 – end_of_your_turn don×1: if active DON≥2, set self active (soft fix)
    "OP04-028": [
        _ab(
            "end_of_your_turn",
            [{"op": "set_character_active", "count": 1, "target_kind": "self", "optional": False}],
            "【咚‼×1】【我方回合結束時】若自己活動狀態的咚‼卡有2張以上時，將這張角色卡置為活動狀態。",
            require_don_attached_gte=1,
            require_don_active_gte=2,
        ),
    ],

    # OP06-039 (Event) – on_play choose_one: rest ≤6 opp char OR KO ≤6 rested opp char; trigger: activate on_play
    "OP06-039": [
        _ab(
            "on_play",
            [
                {
                    "op": "choose_one",
                    "chooser": "self",
                    "options": [
                        {
                            "id": "rest",
                            "label": "將最多1張對手費用6以下的角色卡置為休息狀態",
                            "ops": [{"op": "rest_opponent_character", "count": 1, "cost_lte": 6, "optional": True}],
                        },
                        {
                            "id": "ko",
                            "label": "KO最多1張對手休息狀態費用6以下的角色卡",
                            "ops": [
                                {
                                    "op": "ko",
                                    "target_kind": "opponent_character_rested",
                                    "optional": True,
                                    "cost_lte": 6,
                                }
                            ],
                        },
                    ],
                }
            ],
            "【主要】選擇下列其中一項：將最多1張對手費用6以下的角色卡置為休息狀態，或KO最多1張對手休息狀態費用6以下的角色卡。",
        ),
        _ab(
            "trigger",
            [{"op": "activate_timing", "timing": "on_play"}],
            "【觸發器】發動這張卡片的【主要】效果。",
        ),
    ],

    # OP11-001 克比 (L) – your_turn: SWORD chars can attack chars on play turn;
    # your_turn + opponent_turn: replace_leave opp_remove trash_to_bottom×3 Navy ≤7000 once
    "OP11-001": [
        _ab(
            "your_turn",
            [
                {
                    "op": "allow_attack_active",
                    "count": 1,
                    "target_kind": "own_character",
                    "trait_contains": "SWORD",
                    "optional": False,
                }
            ],
            "自己擁有《SWORD》特徵的角色卡，在登場的回合即可攻擊角色卡。",
        ),
        _ab(
            "your_turn",
            [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "trash_to_bottom",
                    "trash_count": 3,
                    "trait_contains": "Navy|海軍",
                    "base_power_lte": 7000,
                    "optional": True,
                }
            ],
            "【每回合1次】自己原本力量值7000以下擁有《海軍》特徵的角色卡因對手的效果即將離開場上時，可以替換成將3張自己廢棄區中的卡片依任意順序放置在卡組下面。",
            once=True,
        ),
        _ab(
            "opponent_turn",
            [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "trash_to_bottom",
                    "trash_count": 3,
                    "trait_contains": "Navy|海軍",
                    "base_power_lte": 7000,
                    "optional": True,
                }
            ],
            "【每回合1次】自己原本力量值7000以下擁有《海軍》特徵的角色卡因對手的效果即將離開場上時，可以替換成將3張自己廢棄區中的卡片依任意順序放置在卡組下面。",
            once=True,
        ),
    ],
}


def main() -> None:
    lib_path, ovr_path = library_paths()
    lib = json.loads(lib_path.read_text())
    ovr = json.loads(ovr_path.read_text()) if ovr_path.exists() else {"cards": {}}
    cards = lib.setdefault("cards", {})
    ovc = ovr.setdefault("cards", {})
    idx = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    all_ids = set(cards) | set(idx)

    def variants(base_id: str) -> list[str]:
        return sorted({c for c in all_ids if c == base_id or c.startswith(base_id + "-")})

    def write(cid: str, abilities: list[dict[str, Any]]) -> None:
        cleaned = []
        for ab in abilities:
            if ab.get("timing") == "on_block" and not (ab.get("ops") or []):
                continue
            cleaned.append(ab)
        entry = normalize_card_entry(cid, {"version": 1, "abilities": cleaned})
        cards[cid] = entry
        ovc[cid] = entry

    written: list[str] = []
    for base, abs_ in REBUILDS.items():
        vs = variants(base)
        for cid in vs:
            write(cid, copy.deepcopy(abs_))
            written.append(cid)
        print(f"{base} -> {len(vs)} variant(s)")

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    lib["generated_at"] = now
    ovr["generated_at"] = now
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, separators=(",", ":")))
    ovr_path.write_text(json.dumps(ovr, ensure_ascii=False, separators=(",", ":")))
    reload_effect_library(force=True)

    merged: list[str] = []
    seen: set[str] = set()
    for x in written:
        if x not in seen:
            seen.add(x)
            merged.append(x)
    OUT_IDS.write_text("\n".join(merged) + "\n")
    print(f"wrote_ids {len(merged)} -> {OUT_IDS}")


if __name__ == "__main__":
    main()
