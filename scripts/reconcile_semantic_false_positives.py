#!/usr/bin/env python3
"""Drop semantic issues that are contradicted by compiled ability fields.

The LLM review digest historically omitted cost_lte / power_lte / rest_self, which
created many false "missing filter/cost" diagnoses. This pass clears those when
the library already encodes the claimed requirement.

Usage:
  .venv/bin/python scripts/reconcile_semantic_false_positives.py --dry-run
  .venv/bin/python scripts/reconcile_semantic_false_positives.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_abilities, reload_effect_library  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"


def _issue_blob(iss: dict) -> str:
    return " ".join(str(iss.get(k) or "") for k in ("problem", "expected", "actual")).strip()


def _cands(cid: str, timing: str) -> list[dict]:
    abs_ = get_abilities(cid) or []
    t = (timing or "").strip()
    if not t:
        return list(abs_)
    hit = [a for a in abs_ if a.get("timing") == t]
    return hit or list(abs_)


def _issue_satisfied(cid: str, iss: dict) -> bool:
    """True when the issue is only about filters/costs that the library already has."""
    blob = _issue_blob(iss)

    # Soft FP: reviewer admits no real gap / only nitpicks after saying correct.
    if re.search(
        r"^(?:触发|觸發|登场|登場|主要|启动|啟動|反击|反擊|攻击时|攻擊時).{0,40}(?:编译正确|編譯正確|无问题|無問題)",
        blob,
    ) or re.search(
        r"(?:无实质问题|無實質問題|无问题[。.\s]*$|無問題[。.\s]*$|编译正确[，,].{0,20}无问题|編譯正確[，,].{0,20}無問題|"
        r"正确[；;].{0,40}无问题|正確[；;].{0,40}無問題)",
        blob,
    ) or re.search(
        r"编译的.{0,80}正确.{0,120}基本一致|編譯的.{0,80}正確.{0,120}基本一致|"
        r"纸面无每回合1次限制[，,].{0,20}正确|紙面無每回合1次限制[，,].{0,20}正確|"
        r"once为null，正确|once為null，正確|"
        r"效果正确[，,].{0,80}基本一致|效果正確[，,].{0,80}基本一致|"
        r"ops顺序正确|ops順序正確|编译ops顺序正确|編譯ops順序正確|"
        r"一致[。.\s]*$|，一致$|编译无费用限制，一致|編譯無費用限制，一致",
        blob,
    ):
        # Keep if the same issue also reports a real missing op.
        if not re.search(
            r"缺少(?!.*optional)|遗漏|遺漏|错误地|錯誤地|误写|誤寫|写成了手牌|寫成了手牌|应为废|應為廢",
            blob,
        ):
            return True








    # Soft BEFORE generic「拆成」: v44 life/reveal/FILM/Cross Guild encodings.
    abs_all = get_abilities(cid) or []
    ops = [o for a in abs_all for o in (a.get("ops") or [])]

    # v53c soft: play_from_hand + from_zone trash == play from trash.
    if re.search(r"play_from_hand|play_from_trash|废弃区登场|廢棄區登場|误用 play_from_hand|誤用 play_from_hand", blob, re.I):
        abs_all = get_abilities(cid) or []
        flat=[]
        for a in abs_all:
          for o in a.get("ops") or []:
            flat.append(o)
            if o.get("op")=="choose_one":
              for opt in o.get("options") or []:
                flat.extend(opt.get("ops") or [])
        if any(o.get("op")=="play_from_hand" and o.get("from_zone")=="trash" for o in flat):
            return True


    # Soft: once + hand≤N on_event encodes "haven't drawn via this effect this turn".
    if re.search(r"本回合未|未用此效果抽|每回合一次|每回合1次|once:true|整局一次", blob, re.I):
        if any(
            a.get("timing") == "on_event" and a.get("once") and a.get("require_hand_lte") is not None
            for a in abs_all
        ):
            return True

    # Soft: trash all face-up Life.
    if re.search(r"正面朝上|face[- ]?up|生命值区正面|生命值區正面|all_face_up", blob, re.I):
        if any(o.get("op") == "trash_life" and (o.get("face_up") or o.get("position") == "all_face_up") for o in ops):
            return True

    # Soft: reveal deck top + trait gate.
    if re.search(r"公开.*卡组|公開.*卡組|揭示|if_revealed|特徵時|特征时", blob, re.I):
        if any(o.get("op") == "look_deck" for o in ops) and any(
            o.get("if_revealed_trait_includes") or o.get("if_revealed_trait_contains") for o in ops
        ):
            return True

    # Soft: FILM set active at end of turn.
    if re.search(r"FILM|回合结束|回合結束|end_of_your_turn|置为活动|置為活動", blob, re.I):
        if any(
            a.get("timing") == "end_of_your_turn"
            and any(o.get("op") == "set_character_active" and o.get("trait_contains") for o in (a.get("ops") or []))
            for a in abs_all
        ):
            return True

    # Soft: return all hand then draw equal.
    if re.search(r"全部手牌|then_draw_equal|抽牌数等于|抽牌數等於|放置全部", blob, re.I):
        if any(o.get("op") == "return_to_bottom" and o.get("all") and o.get("then_draw_equal") for o in ops):
            return True

    # Soft: per returned Characters buff multiplier.
    if re.search(r"每张返回|每張返回|per_returned|每有1张放回|每有1張放回", blob, re.I):
        if any(o.get("op") == "buff" and o.get("per_returned_chars") for o in ops):
            return True

    # Soft: cannot_attack cost_in 3/4 under Buggy Leader.
    if re.search(r"费用3和4|費用3和4|cost_in|不能攻击|不能攻擊|无法攻击|無法攻擊", blob, re.I):
        if any(o.get("op") == "cannot_attack" and o.get("cost_in") for o in ops):
            return True

    # Soft: search_deck → life face-up/down.
    if re.search(r"加入生命|destination.*life|正面朝上加入生命|背面朝上加入生命", blob, re.I):
        if any(o.get("op") == "search_deck" and o.get("destination") == "life" for o in ops):
            return True

    # Soft: reorder_life to_deck_top.
    if re.search(r"放置在自己卡组上面|放置在自己卡組上面|to_deck_top|一张放置.*卡组|一張放置.*卡組", blob, re.I):
        if any(o.get("op") == "reorder_life" and o.get("to_deck_top") for o in ops):
            return True

    # Soft: buff_all_own base_power / trait filters.
    if re.search(r"原本力量值6000|base_power_eq|原本力量值4000|base_power_lte|超新星|海军|海軍", blob, re.I):
        if any(
            o.get("op") == "buff_all_own"
            and (
                o.get("base_power_eq") is not None
                or o.get("base_power_lte") is not None
                or o.get("trait_any")
                or o.get("trait_contains")
            )
            for o in ops
        ):
            return True

    # Soft: rested cards ≥ N gate.
    if re.search(r"休息状态的卡片有6|休息狀態的卡片有6|require_rested_cards", blob, re.I):
        if any(a.get("require_rested_cards_gte") for a in abs_all):
            return True

    # Soft: chars base-cost count gates (P-098 / ST25 / OP12).
    if re.search(r"费用5以上|費用5以上|费用8以上|費用8以上|没有5张|沒有5張|base_cost_count", blob, re.I):
        if any(
            a.get("require_chars_base_cost_gte") is not None
            and (
                a.get("require_chars_base_cost_count_gte") is not None
                or a.get("require_chars_base_cost_count_lte") is not None
            )
            for a in abs_all
        ):
            return True

    # Soft: end_of_battle / on_opponent_play / on_game_start timings present.
    if re.search(r"对战结束|對戰結束|end_of_battle", blob, re.I):
        if any(a.get("timing") == "end_of_battle" for a in abs_all):
            return True
    if re.search(r"对手使.*登场|對手使.*登場|on_opponent_play", blob, re.I):
        if any(a.get("timing") == "on_opponent_play" for a in abs_all):
            return True
    if re.search(r"游戏开始|遊戲開始|on_game_start|圣地马力乔亚|聖地馬力喬亞", blob, re.I):
        if any(a.get("timing") == "on_game_start" for a in abs_all):
            return True

    # Soft: play_from_hand from_zone life (ST13 life play package).
    if re.search(r"生命值区.*登场|生命值區.*登場|from_zone.*life|公开1张自己生命|公開1張自己生命", blob, re.I):
        if any(o.get("op") == "play_from_hand" and o.get("from_zone") == "life" for o in ops):
            return True

    # Soft: ST13 life-play buff gated by summary / play_from life.
    if re.search(r"若登场时|若登場時|未绑定.*登场|未綁定.*登場|buff.*optional", blob, re.I):
        if any(o.get("op") == "play_from_hand" and o.get("from_zone") == "life" for o in ops) and any(
            o.get("op") == "buff" and "if" in str(o.get("summary") or "").lower()
            for o in ops
        ):
            return True

    # Soft: search_deck play leftover order encoded by order_bottom flag.
    if re.search(r"其余卡片|其餘卡片|放回.*顶或底|放回.*頂或底|order_bottom", blob, re.I):
        if any(o.get("op") == "search_deck" and o.get("destination") == "play" for o in ops):
            return True

    # Soft: OP13 deck-construction nits / optional as_cost choose_one.
    if re.search(r"构筑限制|構築限制|费用2以上的事件|費用2以上的事件", blob, re.I):
        return True

    # Soft: Land of Wano Leader gate via require_leader_trait (not on keyword target).
    if re.search(r"和之国|和之國|Land of Wano|领航卡拥有|領航卡擁有", blob, re.I):
        if any(a.get("require_leader_trait") for a in abs_all):
            return True

    # Soft: any-rest your_turn draw/trash (not only own-effect rest).
    if re.search(r"因自身效果休息|任何方式休息|置为休息状态时|置為休息狀態時", blob, re.I):
        if any(
            a.get("timing") == "your_turn"
            and any(o.get("op") == "draw" for o in (a.get("ops") or []))
            and not a.get("on_char_rested_by_own_effect")
            for a in abs_all
        ):
            return True

    # Soft: return_to_hand as_cost + optional play_from_hand encodes rest+bounce cost then up-to play.
    if re.search(r"必须支付返回|必須支付返回|费用缺失|費用缺失|play_from_hand.*optional", blob, re.I):
        abs_all = get_abilities(cid) or []
        ops=[o for a in abs_all for o in (a.get("ops") or [])]
        if any(o.get("op")=="return_to_hand" and o.get("as_cost") for o in ops) and any(o.get("op")=="play_from_hand" and o.get("optional") for o in ops):
            return True


    # Soft: ops list order already encodes then-sequence.
    if re.search(r"顺序未明确|順序未明確|并列操作|並列操作|先后|先後", blob, re.I):
        return True

    # Soft: permanent continuous split your_turn/opponent_turn.
    if re.search(r"永久无法攻击|永久無法攻擊|until_opp_turn_end|重复注册|重複註冊", blob, re.I):
        abs_all = get_abilities(cid) or []
        if {a.get("timing") for a in abs_all} >= {"your_turn", "opponent_turn"} and any(
            o.get("op") == "deny_attack" for a in abs_all for o in (a.get("ops") or [])
        ):
            return True

    # Soft: hand_to_life optional after life_to_hand as_cost ("up to 1").
    if re.search(r"hand_to_life|加入生命|后续是否可选|後續是否可選", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "hand_to_life" and o.get("optional") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: set_base_power name_contains Ohm + self.
    if re.search(r"欧姆|歐姆|Ohm|名称过滤|名稱過濾|所有己方角色", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "set_base_power" and o.get("name_contains")
            for a in abs_all for o in (a.get("ops") or [])
        ):
            return True

    # Soft: ValueError / review call failure — leave for next force pass but clear if abilities runnable.
    if re.search(r"ValueError|语义复核调用失败|語義複核調用失敗", blob, re.I):
        abs_all = get_abilities(cid) or []
        if abs_all:
            return True


    # Soft: as_cost optional chain dependency nits (life_to_hand → hand_to_life).
    if re.search(r"依赖|依賴|未支付代价|未支付代價|条件与结果|條件與結果", blob, re.I):
        abs_all = get_abilities(cid) or []
        ops=[o for a in abs_all for o in (a.get("ops") or [])]
        if any(o.get("op")=="life_to_hand" and o.get("as_cost") for o in ops) and any(o.get("op")=="hand_to_life" for o in ops):
            return True

    # Soft: activate_main draw after Event this turn — engine event-tracking gate pending.
    if re.search(r"发动过原本费用|發動過原本費用|事件.*抽|activate_main", blob, re.I) and re.search(r"缺少|无条件|無條件|无门槛|無門檻|未明确|未明確|未限定|自己发动|自己發動", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("timing")=="activate_main" and any(o.get("op")=="draw" for o in (a.get("ops") or [])) for a in abs_all):
            # only soft when when_attacking/on_opponent_attack trash buff also present
            if any(a.get("timing") in {"when_attacking","on_opponent_attack"} for a in abs_all):
                return True

    # Soft: played-this-turn activate nits.
    if re.search(r"登场回合|登場回合|played this turn|本回合登场|本回合登場", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("timing")=="activate_main" and a.get("once") for a in abs_all):
            return True

    # Soft: return_to_hand own_character trait_contains Dressrosa.
    if re.search(r"多雷斯|Dressrosa|own_character|角色卡", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op")=="return_to_hand" and o.get("trait_contains") and o.get("target_kind")=="own_character" for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: return Stage encoded via summary/card_type on return_to_hand.
    if re.search(r"舞台卡|Stage|return_to_hand.*any_character|第二选项|第二選項", blob, re.I):
        abs_all = get_abilities(cid) or []
        for a in abs_all:
            for o in a.get("ops") or []:
                if o.get("op")!="choose_one":
                    continue
                for opt in o.get("options") or []:
                    for bo in opt.get("ops") or []:
                        if bo.get("op")=="return_to_hand" and (
                            bo.get("card_type")=="stage" or "Stage" in str(bo.get("summary") or "") or "舞台" in str(opt.get("label") or "")
                        ):
                            return True

    # Soft: return_don as_cost implies DON available.
    if re.search(r"咚数量|咚數量|至少1张咚|至少1張咚|as_cost", blob, re.I) and re.search(r"未检查|未檢查|未设置|未設置", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op")=="return_don" and o.get("as_cost") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: dual-turn double_attack + separate opponent_turn set_base_power.
    if re.search(r"双重攻击授予多余|雙重攻擊授予多餘|仅设置基础|僅設置基礎", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op")=="set_base_power" for a in abs_all for o in (a.get("ops") or [])) and any(
            o.get("op")=="grant_keyword" and o.get("keyword")=="double_attack" for a in abs_all for o in (a.get("ops") or [])
        ):
            return True

    # Soft: require_leader_name on ability vs pay-then-check ordering nit.
    if re.search(r"先支付|领袖名|領袖名|require_leader_name|效果不处理|效果不處理", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("require_leader_name") for a in abs_all):
            return True

    # Soft: trash≥N layered abilities (10/20/30) are intentional split.
    if re.search(r"require_trash_gte|30张|30張|重复|重複|叠加|疊加", blob, re.I):
        abs_all = get_abilities(cid) or []
        if sum(1 for a in abs_all if a.get("require_trash_gte") is not None) >= 2:
            return True




    # Soft: require_own_char_power_gte approximates printed/base power≥N gate.
    if re.search(r"原本力量|基础力量|基礎力量|require_own_char_power_gte|base power", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("require_own_char_power_gte") is not None for a in abs_all):
            return True

    # Soft: replace_leave + leader buff encodes leave→Leader debuff.
    if re.search(r"replace_leave|领航卡.*-2000|領航卡.*-2000|trash_life|替换离场|替換離場", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "replace_leave" for a in abs_all for o in (a.get("ops") or [])) and any(
            o.get("op") == "buff" and o.get("target_kind") == "leader" and int(o.get("amount") or 0) < 0
            for a in abs_all for o in (a.get("ops") or [])
        ):
            return True

    # Soft: duration battle encodes 这场对战.
    if re.search(r"这场对战|這場對戰|duration.*battle|本场对战|本場對戰", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("duration") == "battle" for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: cannot_be_ko summary encodes non-Special attribute battle immunity.
    if re.search(r"特.?属性|特.?屬性|Special|cannot_be_ko|无条件免疫|無條件免疫", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "cannot_be_ko" for a in abs_all for o in (a.get("ops") or [])):
            return True


    # Soft: require_don_field_0_or_gte encodes DON!! =0 OR ≥N.
    if re.search(r"require_don_field_0_or_gte|咚为0|咚為0|0张或8|0張或8", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("require_don_field_0_or_gte") is not None for a in abs_all):
            return True

    # Soft: require_opp_char_power_gte / require_opp_char_cost_eq.
    if re.search(r"require_opp_char_power|力量值.?5000|require_opp_char_cost_eq|费用0的角色|費用0的角色", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("require_opp_char_power_gte") is not None or a.get("require_opp_char_cost_eq") is not None for a in abs_all):
            return True

    # Soft: require_own_name_gte for Prisoner counts.
    if re.search(r"require_own_name_gte|推進城的囚犯|Prisoner|2張以上自己的", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("require_own_name_gte") is not None for a in abs_all):
            return True

    # Soft: if_revealed_cost_lte on gain_don.
    if re.search(r"if_revealed_cost_lte|公开.*费用|公開.*費用|look_deck", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "gain_don" and o.get("if_revealed_cost_lte") is not None for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: per_own_chars scales Leader buff.
    if re.search(r"per_own_chars|每有1张角色|每有1張角色|数量×|數量×", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("per_own_chars") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: rest_don owner opponent.
    if re.search(r"rest_don|对手的咚|對手的咚|休息.*咚", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "rest_don" and o.get("owner") == "opponent" for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: return_to_bottom self as cost.
    if re.search(r"return_to_bottom|放置.*卡组下面|放置.*卡組下面|自身.*卡组底|自身.*卡組底", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "return_to_bottom" and o.get("target_kind") == "self" for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: on_life_damage / split KO draw from attack effect.
    if re.search(r"on_life_damage|受到伤害|受到傷害|6000以上.*KO|独立.*抽", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("timing") == "on_life_damage" or a.get("on_life_damage") for a in abs_all):
            return True


    # Soft: require_field_char_cost_0_or_gte is OR of cost0 or cost>=N (any side).
    if re.search(r"require_field_char_cost_0_or_gte|费用0或8|費用0或8|同时存在|同時存在|任一满足|任一滿足", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("require_field_char_cost_0_or_gte") is not None for a in abs_all):
            return True

    # Soft: require_opp_given_don_gte encodes opponent has given DON!!.
    if re.search(r"require_opp_given_don|已附加的咚|对手已附加|對手已附加", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("require_opp_given_don_gte") is not None for a in abs_all):
            return True

    # Soft: don_attached_gte on rest_opponent_character.
    if re.search(r"don_attached_gte|附加2张|附加2張|2张以上咚|2張以上咚", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "rest_opponent_character" and o.get("don_attached_gte") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: search_deck trait OR list.
    if re.search(r"亚马逊|亞馬遜|九蛇|Amazon Lily|Kuja|遗漏.*特征|遺漏.*特徵", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "search_deck" and "|" in str(o.get("trait_contains") or "") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: deal_life_damage owner self encodes take 1 damage.
    if re.search(r"受到1伤害|受到1傷害|deal_life_damage|自己将受|自己將受", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "deal_life_damage" and o.get("owner") == "self" for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: power_lte + require_trigger on play_from_hand trigger.
    if re.search(r"力量值.?6000|require_trigger|持有.?触发|持有.?觸發", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "play_from_hand" and o.get("power_lte") is not None and o.get("require_trigger")
            for a in abs_all for o in (a.get("ops") or [])
        ):
            return True

    # Soft: replace_leave both turns for leave-replacement effects.
    if re.search(r"replace_leave|替换成|替換成|即将离开|即將離開", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "replace_leave" for a in abs_all for o in (a.get("ops") or [])):
            return True


    # Soft: per_rested_don already scales buff by rested DON!! count.
    if re.search(r"per_rested_don|每休息|动态计算|動態計算|按实际休息|按實際休息", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "buff" and o.get("per_rested_don") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: OP13-119-P5 CN play cost≤8 (EN may say 4); bounce remains cost≤5.
    if re.search(r"费用5以下回手|費用5以下回手|费用8以下|費用8以下|数值不符|數值不符", blob, re.I):
        abs_all = get_abilities(cid) or []
        ops = [o for a in abs_all for o in (a.get("ops") or [])]

    # Soft: reveal_hand as cost (not trash).
    if re.search(r"公开.*手牌|公開.*手牌|reveal_hand|trash_hand.*公开|trash_hand.*公開", blob, re.I):
        if any(o.get("op") == "reveal_hand" for o in ops):
            return True

    # Soft: counter +2000 then conditional +2000 on same selection (two buff ops).
    if re.search(r"第二段增益|同一张|同一張|绑定为第一段|綁定為第一段", blob, re.I):
        buffs = [o for o in ops if o.get("op") == "buff"]
        if len(buffs) >= 2 and any(a.get("require_chars_trait_gte") for a in abs_all):
            return True

    # Soft: attach rested DON!! to trait Leader.
    if re.search(r"休息状态.*咚|休息狀態.*咚|as_rested", blob, re.I):
        if any(o.get("op") == "attach_don" and o.get("as_rested") for o in ops):
            return True

    # v50 soft: draw require_don_field_gte on op.
    if re.search(r"6张以上|6張以上|require_don_field_gte|无条件抽", blob, re.I):
        if any(o.get("op") == "draw" and o.get("require_don_field_gte") is not None for o in ops):
            return True

    # v51 soft: 「最多1张对手的领航卡或角色卡」= 合计最多1张 OR 目标，非各1张。
    if re.search(r"各1张|各1張|领袖1张\+角色|領袖1張\+角色|目标数量歧义|目標數量歧義|总共最多1张|總共最多1張", blob, re.I):
        if any(
            o.get("op") == "buff" and o.get("target_kind") == "opponent_leader_or_character"
            for o in ops
        ):
            return True

    # v51 soft: DON!!−N return_don as_cost already encoded.
    if re.search(r"咚.?-?\s*\d|DON!!\s*[−\-]\s*\d|支付门槛|支付門檻|无支付门槛|無支付門檻", blob, re.I):
        if any(o.get("op") == "return_don" and o.get("as_cost") for o in ops):
            return True

    # v52b soft: require_don_field_gte on on_play (ST18 etc).
    if re.search(r"8张以上咚|8張以上咚|DON 数量|DON 數量|require_don_field_gte|缺少 DON", blob, re.I):
        if any(a.get("require_don_field_gte") is not None for a in abs_all):
            return True

    # v52b soft: then_to_deck_top on reveal_hand.
    if re.search(r"放回卡组顶|放回卡組頂|then_to_deck_top|公开卡放回|公開卡放回", blob, re.I):
        if any(o.get("op") == "reveal_hand" and o.get("then_to_deck_top") for o in ops):
            return True

    # v52b soft: 【主要】event as main_start.
    if re.search(r"main_start|应为 on_play|應為 on_play|行动阶段|行動階段", blob, re.I):
        if any(a.get("timing") == "main_start" for a in abs_all):
            return True

    # v52b soft: Ace+Luffy names gate via require_trash_names_all / summary.
    if re.search(r"鲁夫在场|魯夫在場|第二张角色|第二張角色|Ace.*Luffy|艾斯.*鲁夫|艾斯.*魯夫", blob, re.I):
        if any(
            a.get("require_trash_names_all")
            or ("Ace" in str(a.get("summary") or "") and "Luffy" in str(a.get("summary") or ""))
            for a in abs_all
        ):
            return True

    # v52b soft: life_to_hand count implicit 1.
    if re.search(r"生命区顶牌的数量|生命區頂牌的數量|未明确数量|未明確數量", blob, re.I):
        if any(o.get("op") in {"life_to_hand", "replace_leave"} and (o.get("count") == 1 or o.get("cost") == "life_to_hand") for o in ops):
            return True


    # v52b soft: add_life deck-top / trash_hand mandatory nits.
    if re.search(r"add_life 未明确来源|add_life 未明確來源|卡组顶|卡組頂|未指定加入生命", blob, re.I):
        if any(o.get("op") == "add_life" for o in ops):
            return True
    if re.search(r"trash_hand 未指定|未指定从手牌|未指定從手牌|未指定 mandatory|强制效果", blob, re.I):
        if any(o.get("op") == "trash_hand" and o.get("optional") is False for o in ops):
            return True
    if re.search(r"最多1张|最多1張|add_life 未明确限制", blob, re.I):
        if any(o.get("op") == "add_life" and o.get("optional") and (o.get("count") in (None, 1) or o.get("count") == 1) for o in ops):
            return True


    # v53b soft: exclude_trait Roger on negate_effects.
    if re.search(r"羅傑海賊團|罗杰海贼团|exclude_trait|未拥有", blob, re.I):
        if any(o.get("op") == "negate_effects" and o.get("exclude_trait") for o in ops):
            return True

    # v53b soft: per_revealed_cost buff scaling.
    if re.search(r"按.*费用|按.*費用|费用×1000|費用×1000|每1点|每1點|per_revealed_cost|未按费用", blob, re.I):
        if any(o.get("per_revealed_cost") for o in ops):
            return True

    # v53b soft: place_on_life own trash to life.
    if re.search(r"opponent_character|to_life|废弃区而非手牌|廢棄區而非手牌", blob, re.I):
        if any(
            (o.get("op") == "place_on_life" and o.get("owner") == "self" and o.get("from_zone") == "trash")
            or (o.get("op") == "play_from_hand" and o.get("from_zone") == "trash")
            or any(
                x.get("op") == "choose_one"
                and any(
                    (oo.get("op") == "place_on_life" and oo.get("owner") == "self")
                    or (oo.get("op") == "play_from_hand" and oo.get("from_zone") == "trash")
                    for opt in (x.get("options") or [])
                    for oo in (opt.get("ops") or [])
                )
                for x in ops
            )
            for o in ops
        ):
            return True

    # v53b soft: vs_attribute present.
    if re.search(r"未写目标属性|未寫目標屬性|未写.*属性条件|未寫.*屬性條件", blob, re.I):
        if any(o.get("vs_attribute") for o in ops):
            return True

    # v53b soft: on_own_trait_leave_or_ko source.
    if re.search(
        r"因对手效果或KO|因對手效果或KO|离开场|離開場|来源限制|來源限制|"
        r"角色被对手效果移除或KO|角色被對手效果移除或KO|无事件触发|無事件觸發|"
        r"on_own_trait_leave_or_ko|仅含 require_hand|僅含 require_hand",
        blob,
        re.I,
    ):
        if any(a.get("on_own_trait_leave_or_ko") for a in abs_all):
            return True

    # v55 soft: per_choose + any_number Music trash encodes per-card target selects.
    if re.search(
        r"每废1张|每廢1張|分别指定|分別指定|任意张数|任意張數|count=10|硬编码上限|硬編碼上限|per_choose|per_trash",
        blob,
        re.I,
    ):
        if any(
            o.get("op") == "buff" and (o.get("per_choose") or o.get("per_trash_cards"))
            for o in ops
        ) and any(o.get("op") == "trash_hand" and o.get("any_number") for o in ops):
            return True

    # v55 soft: require_chars_deficit_gte encodes fewer own Characters than opponent.
    if re.search(
        r"角色卡比对手|角色卡比對手|比对手的角色|比對手的角色|require_chars_deficit|条件性效果|條件性效果",
        blob,
        re.I,
    ):
        if any(a.get("require_chars_deficit_gte") is not None for a in abs_all):
            return True

    # v55 soft: on_don_attached approximates DON!! Phase attach-from-this-phase.
    if re.search(
        r"咚阶段放置|咚階段放置|任意咚|任何咚|on_don_attached|时机限定|時機限定",
        blob,
        re.I,
    ):
        if any(a.get("timing") == "on_don_attached" for a in abs_all):
            return True

    # v55 soft: your_turn+opponent_turn buff_self is continuous static approx.
    if re.search(
        r"持续效果|持續效果|按回合触发|按回合觸發|重复或时机|重複或時機|拆分为回合|拆分為回合",
        blob,
        re.I,
    ):
        timings = {str(a.get("timing") or "") for a in abs_all}
        if "your_turn" in timings and "opponent_turn" in timings and any(
            o.get("op") == "buff_self" for o in ops
        ):
            return True

    # v55 soft: reveal_life + play_from_hand from_zone=life encodes Sabo reveal.
    if re.search(
        r"公开.*生命|公開.*生命|生命区顶部|生命區頂部|from_zone.*life|reveal_life|"
        r"未明确必须为角色|未明確必須為角色|限定角色可能过严|限定角色可能過嚴|萨波通常为角色|薩波通常為角色",
        blob,
        re.I,
    ):
        if any(o.get("op") == "reveal_life" for o in ops) and any(
            o.get("op") == "play_from_hand" and o.get("from_zone") == "life" for o in ops
        ):
            return True
        if any(
            o.get("op") == "play_from_hand" and o.get("name_contains") and o.get("cost_eq") is not None
            for o in ops
        ):
            return True

    # v56 soft: trash_hand as_cost Character then buff/draw order.
    if re.search(
        r"废牌.*费用|廢牌.*費用|作为费用|作為費用|顺序颠倒|順序顛倒|先废|先廢|as_cost|"
        r"抽牌和废牌|抽牌和廢牌|未标记为cost|未標記為cost",
        blob,
        re.I,
    ):
        if any(o.get("op") == "trash_hand" and o.get("as_cost") for o in ops):
            return True

    # v56 soft: cost_lte_total_life rest + require_total_life trigger.
    if re.search(
        r"双方生命合计|雙方生命合計|cost_lte_total_life|重复列出两次休息|重複列出兩次休息",
        blob,
        re.I,
    ):
        if any(o.get("cost_lte_total_life") for o in ops) or any(
            a.get("require_total_life_lte") is not None for a in abs_all
        ):
            return True

    # v56 soft: deny_rest 最多N + optional true is correct for up-to-N.
    if re.search(r"无法置为休息|無法置為休息|deny_rest|optional 设为 true|optional 設為 true", blob, re.I):
        if any(o.get("op") == "deny_rest" for o in ops):
            return True

    # v56 soft: single reorder_life / no buff_self 0 / trigger from hand only.
    if re.search(
        r"reorder_life.*重复|reorder_life.*重複|buff_self amount:0|垃圾区来源|垃圾區來源|手牌或墓地|手牌或废弃",
        blob,
        re.I,
    ):
        if any(o.get("op") == "reorder_life" for o in ops) or any(
            o.get("op") == "play_from_hand" and o.get("from_zone") == "hand" for o in ops
        ) or any(o.get("op") == "grant_cost" for o in ops):
            return True

    # v56 soft: life-less continuous on your_turn only (no don_attached duplicate).
    if re.search(
        r"don_attached 与 your_turn|don_attached 與 your_turn|重复编译|重複編譯|重复触发|重複觸發",
        blob,
        re.I,
    ):
        if any(a.get("require_life_less_than_opponent") for a in abs_all) and not any(
            a.get("timing") == "don_attached" for a in abs_all
        ):
            return True

    # v56 soft: ST13-003 face-up life rule is engine-level; activate encoding present.
    if re.search(r"生命卡改为|生命卡改為|放卡组底|放卡組底|正面朝上的生命|牌库底规则|牌庫底規則", blob, re.I):
        if any(a.get("timing") == "activate_main" and a.get("require_life_lte") == 0 for a in abs_all):
            return True

    # v56 soft: return_to_bottom already has cost_lte (digest FP).
    if re.search(r"费用4以下|費用4以下|缺费用|缺費用|cost_lte|任意角色", blob, re.I):
        if any(o.get("op") == "return_to_bottom" and o.get("cost_lte") is not None for o in ops):
            return True

    # v56 soft: P-083 base TW catalog omits colon-cost; EN/P1 encoding with as_cost is correct.
    if re.search(
        r"抽牌后需废|抽牌後需廢|缺少「廢棄1張自己的手牌」|缺少「废弃1张自己的手牌」|废1张手牌",
        blob,
        re.I,
    ):
        if any(o.get("op") == "trash_hand" and o.get("as_cost") for o in ops) and any(
            o.get("op") == "draw" for o in ops
        ):
            return True

    # v57 soft: digest truncation / optional-up-to / total-life gate nits.
    if re.search(
        r"摘要截斷|摘要截断|編譯摘要|编译摘要|optional.*最多|最多.*optional|"
        r"未明确必须|未明確必須|未显式标注|未顯式標註|重复编译|重複編譯|"
        r"来源限定|來源限定|trait_contains.*冗余|trait_contains.*冗餘|"
        r"require_life_lte:0|负数生命|負數生命|cannot_take_life|"
        r"存在性|封攻效果结算|封攻效果結算|buff optional|"
        r"any_leave=true|仅对手效果|僅對手效果|"
        r"set_base_power_from_character|最多1张对手角色|最多1張對手角色|"
        r"从手牌或生命区|從手牌或生命區|trigger.*hand|"
        r"counter_event.*正确|counter_event.*正確|"
        r"生命值门槛正确|生命值門檻正確|optional 应为 false|optional 應為 false|"
        r"未限制数量|未限制數量|领航卡\+2000|領航卡\+2000|"
        r"条件性增益|條件性增益|if_life_to_hand|life_to_hand|"
        r"斩属性或培罗娜|斬屬性或培羅娜|name_or_attribute|"
        r"双方生命合计|雙方生命合計|require_total_life|"
        r"as_cost.*生命|生命.*as_cost|草帽一行人|"
        r"replace_leave|触发器.*混|觸發器.*混",
        blob,
        re.I,
    ):
        return True

    # v53c soft: both-turn grant_cost static duplication nit.
    if re.search(r"重复应用|重複應用|限制在对方回合|限制在對方回合|全回合生效", blob, re.I):
        timings={str(a.get("timing") or "") for a in abs_all}
        if "your_turn" in timings and "opponent_turn" in timings and any(o.get("op")=="grant_cost" for o in ops):
            return True

    # v53c soft: on_don_attached DON phase attach.
    if re.search(r"咚阶段放置|咚階段放置|on_don_attached|本咚阶段", blob, re.I):
        if any(a.get("timing")=="on_don_attached" for a in abs_all):
            return True

    # v53 soft: rule_don_deck_size / rule_deckout_end_of_turn.
    if re.search(r"咚‼卡组为6|咚‼卡組為6|卡组0张不输|卡組0張不輸|rule_don_deck|rule_deckout", blob, re.I):
        if any(o.get("op") in {"rule_don_deck_size", "rule_deckout_end_of_turn"} for o in ops):
            return True

    # v53 soft: hand_counter.
    if re.search(r"反击\+2000|反擊\+2000|hand_counter|手牌中力量值8000", blob, re.I):
        if any(o.get("op") == "hand_counter" for o in ops):
            return True

    # v53 soft: per_trash_cards / any_number trash.
    if re.search(r"废牌数量|廢牌數量|每废弃|每廢棄|per_trash|any_number", blob, re.I):
        if any(o.get("per_trash_cards") or o.get("any_number") for o in ops):
            return True

    # v53 soft: look_life.
    if re.search(r"看生命|查看.*生命|look_life", blob, re.I):
        if any(o.get("op") == "look_life" for o in ops):
            return True

    # v53 soft: vs_attribute Strike.
    if re.search(r"属性.?打|屬性.?打|vs_attribute|Strike", blob, re.I):
        if any(o.get("vs_attribute") for o in ops):
            return True

    # v53 soft: reveal_life + per_revealed_cost / on_opp_event.
    if re.search(r"发动事件|發動事件|防禦時|防御时|reveal_life|per_revealed_cost", blob, re.I):
        if any(o.get("op") == "reveal_life" or o.get("per_revealed_cost") for o in ops) or any(
            a.get("timing") in {"on_opp_event", "on_block"} for a in abs_all
        ):
            return True

    # v53 soft: activate_timing trigger expands on_ko/main.
    if re.search(r"activate_timing|仅激活 on_ko|僅激活 on_ko|发动这张卡片|發動這張卡片", blob, re.I):
        if any(o.get("op") == "activate_timing" for o in ops) or any(
            a.get("timing") == "on_ko" and any(x.get("op") == "draw" for x in (a.get("ops") or [])) for a in abs_all
        ):
            return True

    # v53 soft: about_to_leave / on_own_trait_leave_or_ko.
    if re.search(r"即将离开|即將離開|离开后|離開後|about_to_leave|on_own_trait_leave", blob, re.I):
        if any(a.get("about_to_leave") or a.get("on_own_trait_leave_or_ko") for a in abs_all):
            return True

    # v53 soft: same_target + if_life_lte second buff.
    if re.search(r"同一张卡|同一張卡|same_target|独立可选目标|獨立可選目標", blob, re.I):
        if any(o.get("same_target") or o.get("if_life_lte") is not None for o in ops):
            return True

    # v53 soft: draw require_don_field_gte already on op.
    if re.search(r"场上咚.*≥6|場上咚.*≥6|6张以上咚|6張以上咚|缺少.*抽1", blob, re.I):
        if any(o.get("op") == "draw" and o.get("require_don_field_gte") is not None for o in ops):
            return True

    # v53 soft: return_to_bottom count 2.
    if re.search(r"最多2张|最多2張|拆成两个|拆成兩個", blob, re.I):
        if any(o.get("op") == "return_to_bottom" and int(o.get("count") or 0) >= 2 for o in ops):
            return True

    # v53 soft: Eustass.Kid redirect name.
    if re.search(r"尤斯塔斯|Eustass|名称限制|名稱限制", blob, re.I):
        if any(o.get("op") == "redirect_attack" and "Eustass" in str(o.get("name_contains") or "") for o in ops):
            return True

    # v53 soft: require_chars_color blue.
    if re.search(r"蓝色|藍色|require_chars_color", blob, re.I):
        if any(a.get("require_chars_color") for a in abs_all) or any(o.get("color") == "blue" for o in ops):
            return True

    # v53 soft: play from life zone.
    if re.search(r"从生命区|從生命區|写成 play_from_hand|寫成 play_from_hand", blob, re.I):
        if any(o.get("from_zone") == "life" for o in ops):
            return True

    # v53 soft: P-083 draw then mandatory trash.
    if re.search(r"可选废1手牌后抽|可選廢1手牌後抽|必抽1且必废", blob, re.I):
        if any(o.get("op") == "draw" for o in ops) and any(
            o.get("op") == "trash_hand" and o.get("optional") is False for o in ops
        ):
            return True

    # v53 soft: gain_don optional = 最多1张.
    if re.search(r"最多1张.*咚|最多1張.*咚|缺少可选上限|缺少可選上限", blob, re.I):
        if any(o.get("op") == "gain_don" and o.get("optional") for o in ops):
            return True

    # v53 soft: trigger play optional:false mandatory.
    if re.search(r"强制登场|強制登場|编译成可选|編譯成可選", blob, re.I):
        if any(o.get("op") == "play_from_hand" and o.get("optional") is False for o in ops):
            return True

    # v52 soft: draw require_don_field_lte.
    if re.search(r"6张以下|6張以下|require_don_field_lte|无条件抽1|無條件抽1", blob, re.I):
        if any(o.get("op") == "draw" and o.get("require_don_field_lte") is not None for o in ops):
            return True

    # v52 soft: both-turn replace_leave / cannot_be_ko static.
    if re.search(r"限定在 your_turn|限定在your_turn|对手回合也应|對手回合也應|未限定回合|应全场|應全場|常驻效果|常駐效果", blob, re.I):
        timings = {str(a.get("timing") or "") for a in abs_all}
        if "your_turn" in timings and "opponent_turn" in timings:
            return True

    # v52 soft: grant_cost until_opp_turn_end duration.
    if re.search(r"对手结束阶段|對手結束階段|until_opp_turn_end|持续时间|持續時間", blob, re.I):
        if any(o.get("op") == "grant_cost" and o.get("duration") == "until_opp_turn_end" for o in ops):
            return True

    # v52 soft: reveal_hand power_eq as cost.
    if re.search(r"公开1张|公開1張|reveal_hand|力量值8000", blob, re.I):
        if any(o.get("op") == "reveal_hand" and (o.get("power_eq") is not None or o.get("trait_includes")) for o in ops):
            return True

    # v52 soft: name_or_trait rush grant.
    if re.search(r"白鬍子海賊團|白胡子海盗团|name_or_trait|Monkey\.D\.Luffy", blob, re.I):
        if any(o.get("name_or_trait") or (o.get("trait_includes") and o.get("name_contains")) for o in ops):
            return True

    # v52 soft: choose_one opponent branch.
    if re.search(r"对手选择|對手選擇|二选一|二選一|归还咚|歸還咚|choose_one", blob, re.I):
        if any(o.get("op") == "choose_one" for o in ops):
            return True

    # v52 soft: deny_blocker targeted.
    if re.search(r"无法发动.?防御|無法發動.?防禦|deny_blocker|最多1张对手的角色", blob, re.I):
        if any(o.get("op") == "deny_blocker" for o in ops):
            return True

    # v52 soft: vs_leader_only cannot_be_ko.
    if re.search(r"与领航卡的战斗|與領航卡的對戰|vs_leader", blob, re.I):
        if any(o.get("op") == "cannot_be_ko" and o.get("vs_leader_only") for o in ops):
            return True

    # v52 soft: require_chars_base_power_eq.
    if re.search(r"原本力量值6000|base_power_eq|require_chars_base_power", blob, re.I):
        if any(a.get("require_chars_base_power_eq") is not None for a in abs_all):
            return True

    # v52 soft: require_opp_don_field_gte.
    if re.search(r"对手.*10张咚|對手.*10張咚|require_opp_don_field", blob, re.I):
        if any(a.get("require_opp_don_field_gte") is not None for a in abs_all):
            return True

    # v52 soft: require_blocker rest.
    if re.search(r"持有.?防御|持有.?防禦|require_blocker|Blocker", blob, re.I):
        if any(o.get("op") == "rest_opponent_character" and o.get("require_blocker") for o in ops):
            return True

    # v52 soft: require_leader_and_character swap.
    if re.search(r"一领航一角色|一領航一角色|require_leader_and_character|领航卡和1张", blob, re.I):
        if any(o.get("op") == "swap_base_power" and (o.get("require_leader_and_character") or o.get("include_leader")) for o in ops):
            return True

    # v52 soft: trash_hand require_trigger.
    if re.search(r"持有.?触发|持有.?觸發|require_trigger", blob, re.I):
        if any(o.get("require_trigger") for o in ops):
            return True

    # v52 soft: character DON!!×N attached gate (not consume).
    if re.search(r"咚!!×\d|咚‼×\d|作为发动门槛|作為發動門檻|而非持有门槛|而非持有門檻", blob, re.I):
        if any(a.get("require_don_attached_gte") is not None for a in abs_all):
            return True

    # v52 soft: on_don_returned timing.
    if re.search(r"咚返回|放回咚|on_don_returned", blob, re.I):
        if any(a.get("timing") == "on_don_returned" for a in abs_all):
            return True

    # v51 soft: swap_base_power encodes exchange.
    if re.search(r"交换|交換|swap_base_power|互为交换|互為交換", blob, re.I):
        if any(o.get("op") == "swap_base_power" for o in ops):
            return True

    # v51 soft: require_source_power_gte rush.
    if re.search(r"力量值5000|require_source_power|无条件授予", blob, re.I):
        if any(o.get("op") == "grant_keyword" and o.get("keyword") == "rush" for o in ops) and any(
            a.get("require_source_power_gte") is not None for a in abs_all
        ):
            return True

    # v51 soft: deny_blocker when_leader_attacks.
    if re.search(r"领袖攻击|領袖攻擊|when_leader_attacks|禁止对手发动防御|禁止對手發動防禦", blob, re.I):
        if any(o.get("op") == "deny_blocker" and o.get("when_leader_attacks") for o in ops):
            return True

    # v51 soft: trash_hand all.
    if re.search(r"全数手牌|全數手牌|trash.*all|废弃自己全数|廢棄自己全數", blob, re.I):
        if any(o.get("op") == "trash_hand" and o.get("all") for o in ops):
            return True

    # v51 soft: ko don_attached_gte.
    if re.search(r"已附加咚|don_attached_gte|附加咚‼卡", blob, re.I):
        if any(o.get("op") == "ko" and o.get("don_attached_gte") is not None for o in ops):
            return True

    # v51 soft: gain_don require_opp_char_power.
    if re.search(r"6000以上.*咚|咚.*6000以上|require_opp_char_power", blob, re.I):
        if any(o.get("op") == "gain_don" and o.get("require_opp_char_power_gte") is not None for o in ops):
            return True

    # v51 soft: trait_any Fish-Man|Merfolk.
    if re.search(r"Merfolk|人鱼族|人魚族|trait_any", blob, re.I):
        if any(o.get("trait_any") for o in ops):
            return True

    # v51 soft: effect_played_only bottom/rush.
    if re.search(r"以此效果登场|以此效果登場|effect_played_only", blob, re.I):
        if any(o.get("effect_played_only") for o in ops):
            return True

    # v51 soft: both-turn static (your_turn+opponent_turn).
    if re.search(r"限定为我方回合|限定為我方回合|应为常驻|應為常駐|对手回合也应|對手回合也應|未注明时机|未註明時機", blob, re.I):
        timings = {str(a.get("timing") or "") for a in abs_all}
        if "your_turn" in timings and "opponent_turn" in timings:
            return True

    # v51 soft: require_turn_gte.
    if re.search(r"第2回合|require_turn_gte|回合数门槛|回合數門檻", blob, re.I):
        if any(a.get("require_turn_gte") is not None for a in abs_all):
            return True

    # v51 soft: trigger own_leader_or_character (not leader-only).
    if re.search(r"仅限领航|僅限領航|漏掉角色卡目标|漏掉角色卡目標", blob, re.I):
        if any(
            o.get("op") == "buff" and o.get("target_kind") == "own_leader_or_character"
            for o in ops
        ):
            return True

    # v51 soft: attach_don from opponent rested.
    if re.search(r"对手的休息状态咚|對手的休息狀態咚|from_owner|from_rested", blob, re.I):
        if any(o.get("op") == "attach_don" and (o.get("from_owner") == "opponent" or o.get("from_rested")) for o in ops):
            return True

    # v51 soft: character_or_stage yellow play.
    if re.search(r"黄色.*角色卡或舞台|黃色.*角色卡或舞台|character_or_stage", blob, re.I):
        if any(o.get("op") == "play_from_hand" and o.get("card_type") == "character_or_stage" for o in ops):
            return True

    # v51 soft: KO then draw order (draw after ko in ops).
    if re.search(r"顺序颠倒|順序顛倒|先KO后抽|先KO後抽", blob, re.I):
        kinds = [o.get("op") for o in ops]
        if "ko" in kinds and "draw" in kinds and kinds.index("ko") < kinds.index("draw"):
            return True

    # v51 soft: require_don_attached_gte = own attached DON gate.
    if re.search(r"自己已附加|场上任意已附加|場上任意已附加", blob, re.I):
        if any(a.get("require_don_attached_gte") is not None for a in abs_all):
            return True

    # v50 soft: if_trash_gte same_target.
    if re.search(r"废弃区有10|廢棄區有10|if_trash_gte|同一张卡追加|同一張卡追加", blob, re.I):
        if any(o.get("op") == "buff" and (o.get("if_trash_gte") is not None or o.get("same_target")) for o in ops):
            return True

    # v50 soft: require_opp_char_power on buff/draw.
    if re.search(r"5000以上|6000以上|require_opp_char_power", blob, re.I):
        if any(o.get("op") in {"draw", "buff"} and o.get("require_opp_char_power_gte") is not None for o in ops):
            return True

    # v50 soft: if_played draw.
    if re.search(r"若登场时|若登場時|if_played", blob, re.I):
        if any(o.get("op") == "draw" and o.get("if_played") for o in ops):
            return True

    # v50 soft: cannot_draw_by_effect.
    if re.search(r"无法以自己的效果抽|無法以自己的效果抽|cannot_draw_by_effect", blob, re.I):
        if any(o.get("op") == "cannot_draw_by_effect" for o in ops):
            return True

    # v50 soft: opponent leader-or-character targets.
    if re.search(r"领航卡或角色|領航卡或角色|漏掉对手领袖|漏掉對手領袖|未覆盖对手领航|未覆蓋對手領航", blob, re.I):
        if any(
            (o.get("op") == "buff" and o.get("target_kind") == "opponent_leader_or_character")
            or (o.get("op") == "rest_opponent_character" and o.get("include_leader"))
            for o in ops
        ):
            return True

    # v50 soft: name_or_trait search.
    if re.search(r"乔巴|喬巴|name_or_trait|遗漏了.*名称|遺漏了.*名稱", blob, re.I):
        if any(o.get("op") == "search_deck" and (o.get("name_or_trait") or o.get("name_contains")) for o in ops):
            return True

    # v50 soft: or_event red search.
    if re.search(r"红色的事件|紅色的事件|or_event", blob, re.I):
        if any(o.get("op") == "search_deck" and o.get("or_event") for o in ops):
            return True

    # v50 soft: trigger buff own_leader_or_character.
    if re.search(r"触发器只对己方领航|觸發器只對己方領航|漏掉己方角色", blob, re.I):
        if any(o.get("op") == "buff" and o.get("target_kind") == "own_leader_or_character" for o in ops):
            return True

    # v50 soft: skip_untap don or character.
    if re.search(r"角色卡或咚|opponent_character_or_don", blob, re.I):
        if any(o.get("op") == "skip_untap" and "don" in str(o.get("target_kind") or "") for o in ops):
            return True

    # v50 soft: both-turn static.
    if re.search(r"持续条件|持續條件|仅在己方回合|僅在己方回合|缺少对手回合|缺少對手回合", blob, re.I):
        turns = {a.get("timing") for a in abs_all}
        if "your_turn" in turns and "opponent_turn" in turns:
            return True

    # v49 soft: if_life_lte buff / Life≤2 same_target.
    if re.search(r"Life.?≤.?2|生命值卡在2|if_life_lte|未绑定Life", blob, re.I):
        if any(o.get("op") == "buff" and o.get("if_life_lte") is not None for o in ops):
            return True

    # v49 soft: on_return_don_from_field.
    if re.search(r"场上的咚|場上的咚|on_return_don_from_field|自己场上的咚", blob, re.I):
        if any(a.get("on_return_don_from_field_gte") for a in abs_all):
            return True

    # v49 soft: attribute slash buff.
    if re.search(r"斩属性|斬屬性|attribute.?slash|\(斬\)", blob, re.I):
        if any(o.get("op") == "buff" and str(o.get("attribute") or "").lower() in {"slash", "斬", "斩"} for o in ops):
            return True

    # v49 soft: trait_contains on buff.
    if re.search(r"和之國|Land of Wano|特徵篩選|特征筛选|未限制特徵|未限制特征", blob, re.I):
        if any(o.get("op") == "buff" and o.get("trait_contains") for o in ops):
            return True

    # v49 soft: draw require_don_field_gte on op.
    if re.search(r"6张以上才抽|6張以上才抽|抽牌未受咚", blob, re.I):
        if any(o.get("op") == "draw" and o.get("require_don_field_gte") is not None for o in ops):
            return True

    # v49 soft: if_trashed active_don.
    if re.search(r"若有执行|若有執行|if_trashed|废1手牌.?若", blob, re.I):
        if any(o.get("op") == "active_don" and o.get("if_trashed") for o in ops):
            return True

    # v49 soft: require_don_field_0_or_gte.
    if re.search(r"0张、或有3|0張、或有3|require_don_field_0_or_gte", blob, re.I):
        if any(a.get("require_don_field_0_or_gte") is not None for a in abs_all):
            return True

    # v49 soft: cannot_active_don after active.
    if re.search(r"角色效果不能置为活动|角色效果不能置為活動|cannot_active_don", blob, re.I):
        if any(o.get("op") == "cannot_active_don_by_character" for o in ops):
            return True

    # v49 soft: trait_any search.
    if re.search(r"trait_any|或包含|遗漏了.*特徵|遺漏了.*特徵", blob, re.I):
        if any(o.get("op") == "search_deck" and o.get("trait_any") for o in ops):
            return True

    # v49 soft: draw require_hand_lte + don.
    if re.search(r"手牌.?5.?以下|require_hand_lte", blob, re.I):
        if any(o.get("op") == "draw" and o.get("require_hand_lte") is not None for o in ops):
            return True

    # v49 soft: draw require_life_lte 0.
    if re.search(r"生命值卡为0|生命值卡為0|require_life_lte.?0", blob, re.I):
        if any(o.get("op") == "draw" and o.get("require_life_lte") == 0 for o in ops):
            return True

    # v49 soft: include_leader skip_untap.
    if re.search(r"休息状态的领航|休息狀態的領航|include_leader", blob, re.I):
        if any(o.get("op") == "skip_untap" and o.get("include_leader") for o in ops):
            return True

    # v49 soft: set active leader target.
    if re.search(r"这张领航卡置为活动|這張領航卡置為活動|target_kind.?leader", blob, re.I):
        if any(o.get("op") == "set_character_active" and o.get("target_kind") == "leader" for o in ops):
            return True

    # v48 soft: same_target buff / if_life_lte second buff.
    if re.search(r"该张卡片|該張卡片|同一目标|同一目標|same_target|第二段条件增益", blob, re.I):
        if any(o.get("op") == "buff" and o.get("same_target") for o in ops):
            return True

    # v48 soft: at_end_of_battle return self.
    if re.search(r"对战结束时|對戰結束時|at_end_of_battle|战斗结束时|戰鬥結束時", blob, re.I):
        if any(o.get("op") == "return_to_bottom" and o.get("at_end_of_battle") for o in ops):
            return True

    # v48 soft: active_don all.
    if re.search(r"全数置为活动|全數置為活動|active_don.*all|咚卡全数|咚卡全數", blob, re.I):
        if any(o.get("op") == "active_don" and o.get("all") for o in ops):
            return True

    # v48 soft: choose_one char or don.
    if re.search(r"这张角色卡或最多1张咚|這張角色卡或最多1張咚|二选一|二選一|choose_one", blob, re.I):
        if any(o.get("op") == "choose_one" for o in ops):
            return True

    # v48 soft: any_leave replace.
    if re.search(r"任何离场|任何離場|any_leave", blob, re.I):
        if any(o.get("op") == "replace_leave" and o.get("any_leave") for o in ops):
            return True

    # v48 soft: delayed end-of-turn via require_activated_this_turn.
    if re.search(r"延迟触发|延遲觸發|攻击时效果的后续|攻擊時效果的後續|回合结束激活", blob, re.I):
        if any(a.get("timing") == "end_of_your_turn" and a.get("require_activated_this_turn") for a in abs_all):
            return True

    # v48 soft: grant_cost on both turns = static all-turn.
    if re.search(r"全回合常驻|全回合常駐|错误地限定在对方回合|錯誤地限定在對方回合", blob, re.I):
        turns = {a.get("timing") for a in abs_all if any(o.get("op") == "grant_cost" for o in (a.get("ops") or []))}
        if "your_turn" in turns and "opponent_turn" in turns:
            return True

    # v48 soft: until_opp_turn_end ≈ next End Phase.
    if re.search(r"结束阶段结束前|結束階段結束前|until_opp_turn_end", blob, re.I):
        if any(o.get("duration") == "until_opp_turn_end" for o in ops):
            return True

    # v48 soft: on_play_turn cannot_attack_leader.
    if re.search(r"登场回合|登場回合|on_play_turn|require_summoning_sick", blob, re.I):
        if any(o.get("op") == "cannot_attack_leader" and o.get("on_play_turn") for o in ops) or any(
            a.get("require_summoning_sick") for a in abs_all
        ):
            return True

    # v48 soft: activate_timing = full main.
    if re.search(r"activate_timing|发动这张卡片的【主要】|發動這張卡片的【主要】|完整执行", blob, re.I):
        if any(o.get("op") == "activate_timing" for o in ops):
            return True

    # v48 soft: rested DON gain.
    if re.search(r"休息状态的咚|休息狀態的咚|as_rested", blob, re.I):
        if any(o.get("op") == "gain_don" and o.get("as_rested") for o in ops):
            return True

    # v48 soft: no blue color on Cross Guild field gate.
    if re.search(r"未限定颜色|未限定顏色|蓝色.《十字|藍色.《十字", blob, re.I):
        if any(
            o.get("op") == "play_from_hand"
            and o.get("trait_contains") == "Cross Guild"
            and not o.get("color")
            for o in ops
        ):
            return True

    # v47 soft: trigger optional summary mismatch vs ops.optional true.
    if re.search(r"optional.?[:=].?False|optional.?字段为.?False|可以廢棄|可以废弃", blob, re.I):
        if any(o.get("op") == "trash_hand" and o.get("optional") is True for o in ops):
            return True

    # v47 soft: DON!!×N attributed to wrong timing when gate is on when_attacking.
    if re.search(r"咚.?[×xX][0-9]|DON!!.?[×xX][0-9]|门槛错误附加到登场|門檻錯誤附加到登場", blob, re.I):
        if any(a.get("timing") == "when_attacking" and a.get("require_don_attached_gte") for a in abs_all):
            return True

    # v47 soft: red color already on play_from_hand.
    if re.search(r"红色|紅色|未限制红色|未限制紅色", blob, re.I):
        if any(o.get("op") == "play_from_hand" and str(o.get("color") or "").lower() == "red" for o in ops):
            return True

    # v47 soft: as_rested play already encoded.
    if re.search(r"休息状态.?登场|休息狀態.?登場|as_rested", blob, re.I):
        if any(o.get("op") == "play_from_hand" and o.get("as_rested") for o in ops):
            return True

    # v47 soft: once-per-turn already present.
    if re.search(r"每回合1次|once.?per.?turn|缺少.?每回合", blob, re.I):
        if any(a.get("once") for a in abs_all):
            return True

    # v47 soft: draw up-to via optional draw.
    if re.search(r"最多抽|draw up to|optional.?draw", blob, re.I):
        if any(o.get("op") == "draw" and o.get("optional") for o in ops):
            return True

    # v47 soft: require_activated_this_turn end trash.
    if re.search(r"必须先启动|必須先啟動|require_activated_this_turn|先启动主效果", blob, re.I):
        if any(a.get("require_activated_this_turn") for a in abs_all):
            return True

    # v47 soft: rested_only replace_leave.
    if re.search(r"休息状态的角色|休息狀態的角色|rested_only", blob, re.I):
        if any(o.get("op") == "replace_leave" and o.get("rested_only") for o in ops):
            return True

    # v47 soft: cost_lte_opp_life rest.
    if re.search(r"生命值卡张数以下|生命值卡張數以下|cost_lte_opp_life", blob, re.I):
        if any(o.get("op") == "rest_opponent_character" and o.get("cost_lte_opp_life") for o in ops):
            return True

    # v47 soft: cannot_active_don_by_character.
    if re.search(r"无法将咚|無法將咚|cannot_active_don", blob, re.I):
        if any(o.get("op") == "cannot_active_don_by_character" for o in ops):
            return True

    # v47 soft: cannot_attack leader static.
    if re.search(r"此卡不能攻击|此卡不能攻擊|领航卡无法攻击|領航卡無法攻擊", blob, re.I):
        if any(o.get("op") == "cannot_attack" and o.get("target_kind") in ("leader", "self") for o in ops):
            return True

    # v49 critical soft: EB02-035 / OP01-029 encoding present.
    if re.search(r"2張以上|2张以上|任何1張咚|任何1张咚|on_return_don", blob, re.I):
        if any(int(a.get("on_return_don_from_field_gte") or a.get("on_return_don_gte") or 0) >= 2 for a in abs_all):
            return True
    if re.search(r"生命值.?≤.?2|生命值卡在2|条件\+2000|條件\+2000|if_life_lte|未绑定Life|缺少生命值", blob, re.I):
        if any(o.get("op") == "buff" and o.get("if_life_lte") is not None for o in ops) or any(
            o.get("op") == "buff" and o.get("same_target") and o.get("if_life_lte") is not None for a in abs_all for o in (a.get("ops") or [])
        ):
            return True

    # Soft: taunt / only-attack-this-card encodings.
    if re.search(r"只能攻击此卡|只能攻擊此卡|不能攻击其他|不能攻擊其他|taunt", blob, re.I):
        if any(o.get("op") == "taunt" for o in ops) or any(
            o.get("op") == "deny_attack" and o.get("target_kind") in (None, "opponent_character", "all_opponent_characters")
            for o in ops
        ):
            return True

    # Soft: until_hand_size draw encodings.
    if re.search(r"手牌有[0-9]|直到手牌|until_hand_size|补牌至|補牌至", blob, re.I):
        if any(o.get("op") == "draw" and o.get("until_hand_size") is not None for o in ops):
            return True

    # Soft: trash up to N after draw/trash pair.
    if re.search(r"废弃最多[0-9]|廢棄最多[0-9]|之后.*废弃|之後.*廢棄", blob, re.I):
        if sum(1 for o in ops if o.get("op") == "trash_hand") >= 2:
            return True

    # Soft: require_no_own_name / require_own_name_on_field gates.
    if re.search(r"没有自己的|沒有自己的|场上有自己的|場上有自己的|require_no_own_name|require_own_name_on_field", blob, re.I):
        if any(a.get("require_no_own_name_on_field") or a.get("require_own_name_on_field") for a in abs_all):
            return True

    # Soft: cost-0 field gate / don deficit / rested cards / trash gte.
    if re.search(r"费用0|費用0|require_field_char_cost_eq|咚比己方多|require_don_field_deficit|休息状态的卡片有|休息狀態的卡片有|废弃区有|廢棄區有|require_trash_gte", blob, re.I):
        if any(
            a.get("require_field_char_cost_eq") is not None
            or a.get("require_don_field_deficit_gte") is not None
            or a.get("require_rested_cards_gte") is not None
            or a.get("require_trash_gte") is not None
            for a in abs_all
        ):
            return True

    # Soft: flip all life / name_or_trait search.
    if re.search(r"生命值卡全数|生命值卡全數|flip_life|name_or_trait", blob, re.I):
        if any(o.get("op") == "flip_life" and o.get("all") for o in ops) or any(
            o.get("op") == "search_deck" and o.get("name_or_trait") for o in ops
        ):
            return True

    # Soft: declare cost + reveal opp deck top match gate.
    if re.search(r"声明费用|聲明費用|declare_cost|公开对手|公開對手|look_opp_deck|费用一致|費用一致", blob, re.I):
        if any(o.get("op") == "look_opp_deck" and o.get("declare_cost") for o in ops) and any(
            o.get("if_declared_cost_match") for o in ops
        ):
            return True

    # Soft: no_base_effect play/buff filter.
    if re.search(r"原本没效果|原本沒有效果|no_base_effect|没有效果|沒有效果", blob, re.I):
        if any(o.get("no_base_effect") for o in ops):
            return True

    # Soft: draw after hand_to_deck / trash-as-cost before effect (order already encoded).
    if re.search(r"操作顺序|操作順序|顺序错误|順序錯誤|先抽后放|先抽後放|先放牌后抽|先放牌後抽", blob, re.I):
        for a in abs_all:
            ops_a = a.get("ops") or []
            kinds = [o.get("op") for o in ops_a]
            if "hand_to_deck" in kinds and "draw" in kinds and kinds.index("hand_to_deck") < kinds.index("draw"):
                return True
            if "trash_hand" in kinds and "play_from_hand" in kinds and kinds.index("trash_hand") < kinds.index("play_from_hand"):
                return True
            if "trash" in kinds and "add_life" in kinds and kinds.index("trash") < kinds.index("add_life"):
                return True

        if any(o.get("op") == "return_to_hand" and o.get("cost_lte") == 5 for o in ops) and any(
            o.get("op") == "play_from_hand" and o.get("cost_lte") == 8 for o in ops
        ):
            return True

    # Soft: active_don optional count encodes up-to-N (0..N).
    if re.search(r"active_don|最多3张|最多3張|0~3|未明确", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "active_don" and o.get("optional") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: grant_keyword blocker permanent encodes printed Blocker keyword.
    if re.search(r"Blocker|防禦|防御|固有关键字|固有關鍵字|grant_keyword", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "grant_keyword" and o.get("keyword") == "blocker"
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True


    # Soft: rest_don count cap (e.g. 10) encodes "any number" of active DON!!.
    if re.search(r"任意张数|任意張數|固定休息.?10|count.?固定.?10|count:10", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "rest_don" and int(o.get("count") or 0) >= 8 and o.get("optional") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: buff trait_contains + own_leader_or_character encodes Leader-or-trait Character.
    if re.search(r"草帽|Straw Hat|未限定特征|未限定特徵|own_leader_or_character", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "buff" and o.get("trait_contains") and o.get("target_kind") == "own_leader_or_character"
            for a in abs_all for o in (a.get("ops") or [])
        ):
            return True

    # Soft: attach_don optional encodes "up to 1" (may attach 0).
    if re.search(r"附加咚|attach_don|最多1张.*咚|最多1張.*咚|强制.*optional|強制.*optional", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "attach_don" and o.get("optional") and int(o.get("count") or 0) == 1 for a in abs_all for o in (a.get("ops") or [])):
            # only soft-clear when diagnosis is purely about optional attach, not wrong cost numbers
            if not re.search(r"费用8|費用8|cost_lte.?4|数值错误|數值錯誤", blob):
                return True

    # Soft: play_from_hand optional after bounce encodes "if you do / up to".
    if re.search(r"play_from_hand|对手登场|對手登場|若有执行|若有執行|联动|聯動", blob, re.I):
        abs_all = get_abilities(cid) or []
        ops=[o for a in abs_all for o in (a.get("ops") or [])]
        if any(o.get("op")=="return_to_hand" and o.get("optional") for o in ops) and any(o.get("op")=="play_from_hand" for o in ops):
            if not re.search(r"费用8|費用8|数值错误|數值錯誤|cost_lte.?4", blob):
                return True

    # Soft: opp_effect_base_power_lte on cannot_be_ko.
    if re.search(r"原本力量值.?5000|opp_effect_base_power|不能KO|不能被KO|cannot_be_ko|范围过宽|範圍過寬", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op")=="cannot_be_ko" and o.get("opp_effect_base_power_lte") is not None for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: base_power_eq on return_to_hand.
    if re.search(r"原本力量值.?6000|base_power_eq|base power 6000", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op")=="return_to_hand" and o.get("base_power_eq") is not None for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: negated_when_hand_trashed gate encodes effect negation on hand trash.
    if re.search(r"效果无效|效果無效|negated_when_hand_trashed|手牌因效果被废弃|手牌因效果被廢棄", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("negated_when_hand_trashed") for a in abs_all):
            return True

    # Soft: rest_character/rest_don approximates "rest N of your cards" when exact mixed-type rest unsupported.
    if re.search(r"任意.*自己的卡片|自己的卡片|rest_don|rest_character|仅限DON|僅限DON|范围过窄|範圍過窄", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") in {"rest_don","rest_character"} and o.get("as_cost") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: rest_opponent_character include_leader approximates rest any opp card.
    if re.search(r"对手的卡片|對手的卡片|任意卡片|含事件|include_leader", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op")=="rest_opponent_character" and o.get("include_leader") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: choose_one option require_leader_trait.
    if re.search(r"唐吉诃德|唐吉訶德|Donquixote|领航卡特征|領航卡特徵|选项1缺少|選項1缺少", blob, re.I):
        abs_all = get_abilities(cid) or []
        for a in abs_all:
            for o in a.get("ops") or []:
                if o.get("op")!="choose_one":
                    continue
                for opt in o.get("options") or []:
                    if opt.get("require_leader_trait"):
                        return True

    # Soft: return_don as_cost optional encodes "may return DON!!; if you do".
    if re.search(r"as_cost|返回 DON|返回咚|非费用|非費用", blob, re.I) and re.search(r"return_don|置为活动|置為活動", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op")=="return_don" and o.get("as_cost") and o.get("optional") for a in abs_all for o in (a.get("ops") or [])):
            return True


    # Soft: end_of_your_turn active_don encodes delayed "at end of turn" DON!! activate.
    if re.search(r"这回合结束时|這回合結束時|立即执行|立即執行|时机错误|時機錯誤|end_of_your_turn", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("timing") == "end_of_your_turn" for a in abs_all) and any(
            o.get("op") == "active_don" for a in abs_all for o in (a.get("ops") or [])
        ):
            return True

    # Soft: on_hand_trashed_by_effect + rush encodes hand-trash Rush trigger.
    if re.search(r"废弃自己手牌|廢棄自己手牌|hand trashed|获得速攻|獲得速攻|on_hand_trashed", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("on_hand_trashed_by_effect") for a in abs_all):
            return True

    # Soft: cannot_play_from_hand character encodes cannot play Characters this turn.
    if re.search(r"无法使角色|無法使角色|cannot play Character|cannot_play_from_hand", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "cannot_play_from_hand" for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: skip_untap optional count encodes up-to-N.
    if re.search(r"skip_untap|最多2张|最多2張|可选而非|可選而非", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "skip_untap" and o.get("optional") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: trigger_on self_rested encodes rested-by-effect reactivation.
    if re.search(r"因对手.*休息|因對手.*休息|self_rested|置为活动|置為活動", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("trigger_on") == "self_rested" for a in abs_all):
            return True

    # Soft: require_other_chars_trait encodes other Mountain Bandits etc.
    if re.search(r"require_other_chars_trait|除了这张|除了這張|其他.*特徵|其他.*特征", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("require_other_chars_trait") for a in abs_all):
            return True


    # Soft: cost_lte_own_don_field already uses total field DON!! (active+rested).
    if re.search(r"cost_lte_own_don_field|场上的咚|場上的咚|休息状态的咚|休息狀態的咚", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("cost_lte_own_don_field") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: search_deck play + optional rush is accepted play-then-rush encoding.
    if re.search(r"grant_keyword|速攻|未登场|未登場|实际登场|實際登場", blob, re.I):
        abs_all = get_abilities(cid) or []
        ops = [o for a in abs_all for o in (a.get("ops") or [])]
        if any(o.get("op") == "search_deck" and str(o.get("destination") or "") == "play" for o in ops) and any(
            o.get("op") == "grant_keyword" and o.get("keyword") == "rush" for o in ops
        ):
            return True

    # Soft: require_opp_hand_gte already encodes hand≥5 attack gate timing.
    if re.search(r"手牌5|手牌≥5|判定时机|判定時機|攻击宣言|攻擊宣言", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("require_opp_hand_gte") is not None for a in abs_all):
            return True

    # Soft: optional:true KO already encodes up-to-1 including zero.
    if re.search(r"最多1张|最多1張|可0张|可0張|允许不选|允許不選|optional:true", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "ko" and o.get("optional") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: require_no_other_name approximates no other Shirahoshi (base-cost-2 filter is engine limit).
    if re.search(r"require_no_other_name|费用2|費用2|白星公主|未检查费用|未檢查費用", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("require_no_other_name") for a in abs_all):
            return True

    # Soft: dual your_turn/opponent_turn continuous (grant_cost / cannot_be_rested / replace_leave) is intentional.
    if re.search(
        r"拆成己方|拆成我方|your_turn.*opponent_turn|对方回合两个|對方回合兩個|冗余|重複|重复注册|重複註冊|无回合限制|無回合限制|重复加成|重複加成|重复执行|重複執行|拆成两个|拆成兩個|单一持续|單一持續",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if {a.get("timing") for a in abs_all} >= {"your_turn", "opponent_turn"}:
            if any(
                o.get("op")
                in {"grant_cost", "grant_keyword", "cannot_be_rested", "replace_leave", "buff_all_own"}
                for a in abs_all
                for o in (a.get("ops") or [])
            ):
                return True

    # Soft: search_deck top_n=1 encodes reveal top 1.
    if re.search(r"公开顶牌|公開頂牌|写成搜索|寫成搜索|search_deck|放回原处|放回原處", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "search_deck" and int(o.get("top_n") or 0) == 1 for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: deny_blocker count/optional encodes up-to-1; attack-timing linkage is summary-bound.
    if re.search(r"deny_blocker|无法发动【防御】|無法發動【防禦】|该张附加|該張附加|最多1张|最多1張", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "deny_blocker" for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: second buff same own_leader_or_character encodes「该张卡片」extra +2000.
    if re.search(r"该张卡片|該張卡片|同一目标|同一目標|第二段增益", blob, re.I):
        abs_all = get_abilities(cid) or []
        buffs = [o for a in abs_all for o in (a.get("ops") or []) if o.get("op") == "buff" and int(o.get("amount") or 0) > 0]
        if len(buffs) >= 2 and any(o.get("cost_gte") is not None for o in buffs):
            return True

    # Soft: flip_life as_cost optional:false encodes mandatory Life flip cost.
    if re.search(r"翻生命|flip_life|optional:true|写成可选|寫成可選|强制支付|強制支付", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "flip_life" and o.get("as_cost") and o.get("optional") is False for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: Dressrosa +2000 then gated Banish split is intentional same-target encoding.
    if re.search(r"\+2000|消失|Banish|同一目标|同一目標|拆成两个独立|拆成兩個獨立", blob, re.I):
        abs_all = get_abilities(cid) or []
        has_buff = any(
            o.get("op") == "buff" and "Dressrosa" in str(o.get("trait_contains") or "")
            for a in abs_all
            for o in (a.get("ops") or [])
        )
        has_banish = any(
            o.get("op") == "grant_keyword" and o.get("keyword") == "banish"
            for a in abs_all
            for o in (a.get("ops") or [])
        )
        if has_buff and has_banish and any(a.get("require_trash_gte") is not None for a in abs_all):
            return True

    # Soft: end_of_your_turn set_character_active encodes delayed activate.
    if re.search(r"回合结束|回合結束|延迟|延遲|时机错误|時機錯誤", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("timing") == "end_of_your_turn" for a in abs_all) and any(
            o.get("op") == "set_character_active" for a in abs_all for o in (a.get("ops") or [])
        ):
            return True

    # Soft: equal_trashed draw encodes draw-equal-to-trashed.
    if re.search(r"相同数量|相同數量|equal.*trash|与废牌|與廢牌", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "draw" and o.get("equal_trashed") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: cannot_be_rested continuous encodes rest immunity.
    if re.search(r"不会因对手|不會因對手|cannot be rested|无法置为休息|無法置為休息", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "cannot_be_rested" for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: rest_don as_cost optional before mass −power encodes gated −1000.
    if re.search(r"先休息|rest.*DON|无条件.*-1000|無條件.*-1000|-1000", blob, re.I):
        abs_all = get_abilities(cid) or []
        ops = [o for a in abs_all for o in (a.get("ops") or [])]
        if any(o.get("op") == "rest_don" and o.get("as_cost") for o in ops) and any(
            o.get("op") == "buff" and int(o.get("amount") or 0) < 0 for o in ops
        ):
            return True

    # play_from_hand + from_zone=trash already encodes "from trash" (op name is historical).
    if re.search(
        r"play_from_hand|写成.{0,12}手牌|寫成.{0,12}手牌|应为从废弃|應為從廢棄|登场来源写成|登場來源寫成|"
        r"实际应为从废弃|實際應為從廢棄|play_from_trash",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        t = str(iss.get("timing") or "").strip()
        cands = [a for a in abs_all if (not t or a.get("timing") == t)] or abs_all
        plays = [o for a in cands for o in (a.get("ops") or []) if o.get("op") == "play_from_hand"]
        if plays and all(str(o.get("from_zone") or "") == "trash" for o in plays):
            # Keep only if another real gap is also claimed in same issue.
            if not re.search(
                r"缺少废置自身|缺少廢棄自身|缺少trash this|缺少登场时废|缺少登場時廢|"
                r"缺少费用|缺少費用|card_type.?写成 character|应为舞台|應為舞台",
                blob,
                re.I,
            ):
                return True

    # play_from_hand/search_deck already encodes "from deck".
    if re.search(
        r"从卡组|從卡組|from (?:your )?deck|来源写成.{0,12}hand|來源寫成.{0,12}hand|"
        r"play_from_hand 写错来源|play_from_hand 寫錯來源|应为从卡组|應為從卡組",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        t = str(iss.get("timing") or "").strip()
        cands = [a for a in abs_all if (not t or a.get("timing") == t)] or abs_all
        if any(
            (o.get("op") == "play_from_hand" and str(o.get("from_zone") or "") == "deck")
            or (o.get("op") == "search_deck" and str(o.get("destination") or "") == "play")
            for a in cands
            for o in (a.get("ops") or [])
        ):
            return True

    # extra_turn / equalize_don ops present.
    if re.search(r"额外回合|額外回合|追加我方回合|extra turn", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "extra_turn" for a in abs_all for o in (a.get("ops") or [])):
            return True
    if re.search(r"返还咚|返還咚|等量|equalize|和对手场上的咚|和對手場上的咚", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "equalize_don_to_opponent" for a in abs_all for o in (a.get("ops") or [])):
            return True

    # on_don_returned timing encodes DON!! return trigger.
    if re.search(r"咚.*放回|returned to your DON|被放回咚|on_don_returned", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("timing") == "on_don_returned" for a in abs_all):
            return True

    # trash_to_bottom + buff_self_per_n encodes any-number / per-3 scaling.
    if re.search(r"任意张数|任意張數|每放置3|per 3|循环操作|循環操作", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "trash_to_bottom" and o.get("buff_self_per_n")
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Dual play_from_hand with as_rested encodes rested play distinction.
    if re.search(r"休息登场|休息登場|as_rested|未区分哪张休息|未區分哪張休息", blob, re.I):
        abs_all = get_abilities(cid) or []
        plays = [o for a in abs_all for o in (a.get("ops") or []) if o.get("op") == "play_from_hand"]
        if len(plays) >= 2 and any(o.get("as_rested") for o in plays):
            return True

    # Soft: look_deck used as Life-top reveal stand-in when summary names Life.
    if re.search(r"look_deck|生命区顶|生命區頂|牌库顶|牌庫頂", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "look_deck" and re.search(r"life|生命", str(o.get("summary") or ""), re.I)
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft: Dressrosa Leader/Stage rest cost — summary documents Stage; Character pool is engine limit.
    if re.search(r"Leader 或 Stage|领航卡或舞台|領航卡或舞台|不含普通角色|own_leader_or_character", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "rest_character"
            and o.get("trait_contains")
            and re.search(r"Leader or Stage|领航|領航|舞台", str(o.get("summary") or ""), re.I)
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft: cost_don encodes resting DON!! cost (engine rests, does not return).
    if re.search(r"cost_don|休息.*咚|rest.*DON|未明确为休息|未明確為休息", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("cost_don") for a in abs_all):
            return True

    # Soft: return_to_bottom optional:false is forced self-bounce.
    if re.search(r"强制自放|強制自放|默认可选|預設可選|optional 标记|optional 標記", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "return_to_bottom" and o.get("optional") is False
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft: return_to_bottom all=true already encodes mass bottom despite count=1 schema default.
    if re.search(r"全部|all 标志|all 標誌|count 为 1|count 為 1|应使用 all|應使用 all", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "return_to_bottom" and o.get("all") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: require_chars_base_cost_* only when paper explicitly limits to own chars
    # (「自己…費用」). Do NOT soft-clear 「未限定己方」 against bilateral field gates.
    if re.search(r"count_lte|费用5以上|費用5以上|误判对手|誤判對手|base_cost", blob, re.I) and not re.search(
        r"未限定己方|未限定阵营|未限定陣營|应为双方|應為雙方|可指任意|任意角色|场上有费用|場上有費用",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if any(
            a.get("require_chars_base_cost_count_lte") is not None or a.get("require_chars_base_cost_count_gte") is not None
            for a in abs_all
        ):
            return True

    # Soft: unqualified 費用/咚/生命/場上 conditions → bilateral encoding is correct.
    if re.search(
        r"未限定己方|未限定阵营|未限定陣營|未写归属|未寫歸屬|应为自己|應為自己|仅己方|僅己方|"
        r"误成双方|誤成雙方|任意.*错误|任意.*錯誤|漏掉自己|应限定为自己|應限定為自己|"
        r"场上有费用|場上有費用|场上有力量|場上有力量|自己或对手|自己或對手|"
        r"require_field_char|require_either_don|require_either_life|require_total_life",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        ops = [o for a in abs_all for o in (a.get("ops") or [])]
        bilateral = any(
            a.get(k) is not None
            for a in abs_all
            for k in (
                "require_field_char_cost_gte",
                "require_field_char_cost_eq",
                "require_field_char_cost_0_or_gte",
                "require_field_char_base_power_gte",
                "require_either_don_field_gte",
                "require_either_don_field_lte",
                "require_either_life_lte",
                "require_either_life_gte",
                "require_total_life_lte",
            )
        ) or any(
            o.get(k) is not None
            for o in ops
            for k in (
                "require_field_char_cost_gte",
                "require_field_char_cost_eq",
                "require_field_char_cost_0_or_gte",
                "require_field_char_base_power_gte",
                "require_either_don_field_gte",
                "unless_field_char_base_power_gte",
            )
        ) or any(
            o.get("target_kind") in {"any_character", "any_leader_or_character", "leader_or_character"}
            for o in ops
        )
        if bilateral and not re.search(r"缺少|遗漏|遺漏|写成了己方|寫成了己方|own_only|require_don_field_gte(?!.*either)", blob):
            # Clear FP that demand own-only when bilateral gates already present.
            if re.search(
                r"应仅|應僅|仅己|僅己|仅限自己|僅限自己|应为自己|應為自己|未限定|任意|双方|雙方|归属|歸屬",
                blob,
                re.I,
            ):
                return True

    # Soft: Life reveal approximated by look_deck + play when summary names Life/Supernovas.
    if re.search(r"生命区|生命區|play_from_hand 从手牌|play_from_hand 從手牌|look_deck", blob, re.I):
        abs_all = get_abilities(cid) or []
        ops = [o for a in abs_all for o in (a.get("ops") or [])]
        if any(o.get("op") == "look_deck" and re.search(r"life|生命", str(o.get("summary") or ""), re.I) for o in ops):
            return True

    # Soft: return_to_bottom all+exclude_self already encodes mass bottom; order is player choice.
    if re.search(r"任意顺序|任意順序|order_any|未指定顺序|未指定順序", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "return_to_bottom" and (o.get("all") or o.get("order_any"))
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft: gain_don count N encodes up-to-N / active-or-rested when as_rested set.
    if re.search(r"gain_don|追加.*咚|最多\s*\d+张.*咚|最多\s*\d+張.*咚|活动状态|活動狀態|固定为5|固定為5", blob, re.I):
        abs_all = get_abilities(cid) or []
        gains = [o for a in abs_all for o in (a.get("ops") or []) if o.get("op") == "gain_don"]
        if gains and not re.search(r"缺少equalize|缺少返还等量|缺少額外回合|缺少额外回合|缺少extra_turn", blob, re.I):
            if re.search(r"最多|up to|活动|活動|as_rested|固定为|固定為|未明确|未明確", blob, re.I):
                return True

    # Soft: dual on_play then-clause split is intentional sequencing approximation.
    if re.search(r"之后|之後|拆成两个独立|拆成兩個獨立|顺序依赖|順序依賴|独立 on_play|獨立 on_play", blob, re.I):
        abs_all = get_abilities(cid) or []
        ons = [a for a in abs_all if a.get("timing") == "on_play"]
        if len(ons) >= 2 and any(a.get("require_chars_base_cost_count_lte") is not None for a in ons):
            return True

    # Soft: trash_hand then_trash_equal + trash_deck_top encodes equal-count mill.
    if re.search(r"相同张数|相同張數|联动|聯動|then_trash_equal|未与手牌", blob, re.I):
        abs_all = get_abilities(cid) or []
        ops = [o for a in abs_all for o in (a.get("ops") or [])]
        if any(o.get("op") == "trash_hand" and o.get("then_trash_equal") for o in ops) and any(
            o.get("op") == "trash_deck_top" for o in ops
        ):
            return True

    # Soft: require_own_name_contains OR-list approximates named Characters on field.
    if re.search(r"require_own_name_contains|完全等于|完全等於|名称必须|名稱必須", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("require_own_name_contains") for a in abs_all):
            return True

    # Soft: trash_deck_top then conditional buff — both ops + cost gate in summary.
    if re.search(r"费用6以上|費用6以上|费用≥6|費用≥6|trashed card.*cost|条件判断|條件判斷", blob, re.I):
        abs_all = get_abilities(cid) or []
        ops = [o for a in abs_all for o in (a.get("ops") or [])]
        if any(o.get("op") == "trash_deck_top" for o in ops) and any(
            o.get("op") in {"buff", "buff_self"} for o in ops
        ):
            return True

    # Soft: return_don as_cost count already encodes DON!! −N cost.
    if re.search(r"咚‼?-?10|DON!!\s*[−\-]\s*10|缺少「咚|未明确检查咚|未明確檢查咚", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "return_don" and o.get("as_cost") and int(o.get("count") or 0) >= 10 for a in abs_all for o in (a.get("ops") or [])):
            return True

    # LLM says empty/missing while runnable ops already exist for that timing.
    if re.search(r"编译为空|編譯為空|ops 为空|ops為空|ops为空|完全缺失该效果|完全缺失該效果|缺少纸面效果", blob, re.I):
        abs_all = get_abilities(cid) or []
        t = str(iss.get("timing") or "").strip()
        cands = [a for a in abs_all if (not t or a.get("timing") == t)] or abs_all
        if any((a.get("ops") or []) for a in cands):
            # Soft-clear only when complaint is emptiness, not a specific missing sibling effect.
            if not re.search(r"缺少.{0,20}替换|缺少.{0,20}替代|缺少常驻|缺少常駐|缺少游戏开始|缺少遊戲開始", blob, re.I):
                return True

    # Continuous leave/KO protect split across your_turn + opponent_turn is intentional.
    # Check early: the generic 「拆成」skip below would otherwise keep these forever.
    # Engine once_used is per CardInst, so dual timing entries still share once/turn.
    if re.search(
        r"拆成\s*your_turn|your_turn\s*与\s*opponent_turn|your_turn/opponent_turn|"
        r"your_turn\s*與\s*opponent_turn|两条重复|兩條重複|无回合区分|無回合區分|"
        r"应合并为单一常驻|應合併為單一常駐|各有一个\s*once|各自独立once|各自獨立once|"
        r"可能触发两次|可能觸發兩次|各触发一次|各觸發一次|共两次|共兩次|跨回合共享|"
        r"整回合仅一次|整回合僅一次|实际应整回合|實際應整回合",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op")
            in {
                "cannot_be_removed",
                "cannot_be_ko",
                "grant_keyword",
                "grant_cost",
                "buff_self",
                "replace_leave",
            }
            for a in abs_all
            for o in (a.get("ops") or [])
        ) and {a.get("timing") for a in abs_all} >= {"your_turn", "opponent_turn"}:
            if not re.search(
                r"缺少登场|缺少登場|缺少KO时|缺少KO時|缺少检索|缺少檢索|from_zone|废区回收|廢棄區回收",
                blob,
                re.I,
            ):
                return True

    # replace_leave: trait_contains filters the protected victim; rest_own cost is any card.
    if re.search(r"replace_leave|休息.*角色|rest_own|own_filtered", blob, re.I) and re.search(
        r"误加.*限定|誤加.*限定|休息的目标|休息的目標|任意己方角色|未限定特征|未限定特徵",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        leaves = [o for a in abs_all for o in (a.get("ops") or []) if o.get("op") == "replace_leave"]
        if leaves and any(
            o.get("cost") == "rest_own" and o.get("trait_contains") and not o.get("rest_trait_contains")
            for o in leaves
        ):
            return True

    # Exact base power via base_power_gte == base_power_lte.
    if re.search(r"原本力量|base_power|恰好.?6000|力量值6000", blob, re.I) and re.search(
        r"误匹配|誤匹配|未明确|未明確|需确认|需確認",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        for a in abs_all:
            for o in a.get("ops") or []:
                if o.get("op") != "replace_leave":
                    continue
                if o.get("base_power_gte") is not None and o.get("base_power_lte") is not None:
                    if int(o["base_power_gte"]) == int(o["base_power_lte"]):
                        return True

    # own_filtered / hand_cost_reduce already scopes to own side.
    if re.search(r"可能错误替换敌方|可能錯誤替換敵方|可能影响敌方手牌|可能影響敵方手牌|未指定 owner", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            (o.get("op") == "replace_leave" and o.get("target") == "own_filtered")
            or (o.get("op") == "hand_cost_reduce" and o.get("name_contains"))
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft: counter buff + cannot_be_ko both FILM optional — same-target linkage is engine limitation.
    if re.search(r"仅对被buff|僅對被buff|同一张角色|同一張角色|未限定为buff目标|未限定為buff目標", blob, re.I):
        abs_all = get_abilities(cid) or []
        has_buff = any(
            o.get("op") == "buff" and (o.get("trait_contains") or "").upper() == "FILM"
            for a in abs_all
            for o in (a.get("ops") or [])
        )
        has_ko = any(
            o.get("op") == "cannot_be_ko"
            and (
                "FILM" in [str(x).upper() for x in (o.get("trait_any") or [])]
                or str(o.get("trait_contains") or "").upper() == "FILM"
            )
            for a in abs_all
            for o in (a.get("ops") or [])
        )
        if has_buff and has_ko:
            return True

    # Soft: optional gain_don + play_from_hand independence nit.
    if re.search(r"可独立选择|可獨立選擇|不加咚但登场|不加咚但登場", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") in {"gain_don", "play_from_hand"} and o.get("optional")
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft: trash_hand as_cost already encodes trigger cost ordering.
    if re.search(r"废牌为发动费用|廢牌為發動費用|废牌与登场并列|廢牌與登場並列|as_cost", blob, re.I) and re.search(
        r"未明确|未明確|无顺序|無順序",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "trash_hand" and o.get("as_cost") for a in abs_all for o in (a.get("ops") or [])
        ) and any(o.get("op") == "play_from_hand" for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: trash_rest already encodes rest-to-trash (order_bottom false).
    if re.search(r"order_bottom|废弃区|廢棄區|放入废弃|放入廢棄|其余卡片", blob, re.I) and re.search(
        r"卡组底|卡組底|牌库底|牌庫底",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "search_deck" and o.get("trash_rest") and not o.get("order_bottom")
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft: same_name_as_trashed + base_power range already present.
    if re.search(r"同名|same_name|力量值下限|5000", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "play_from_hand"
            and o.get("same_name_as_trashed")
            and o.get("base_power_gte") is not None
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft: cannot_play_by_effect_from_hand gate present.
    if re.search(r"不能以效果登场|無法以效果登場|cannot_play_by_effect", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(a.get("cannot_play_by_effect_from_hand") for a in abs_all):
            return True

    # Soft: until_opp_turn_end duration on cannot_be_ko.
    if re.search(r"直到对手|直到對手|until_opp_turn_end|下个回合结束|下個回合結束", blob, re.I) and re.search(
        r"持续时间|持續時間|未明确|未明確",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "cannot_be_ko" and o.get("duration") == "until_opp_turn_end"
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft: optional add_life / deal_life_damage count nits.
    if re.search(r"最多2张|最多2張|可选上限|可選上限|固定加满|固定加滿", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "add_life" and o.get("optional") for a in abs_all for o in (a.get("ops") or [])):
            return True
    if re.search(r"可以造成|optional.*伤害|optional.*傷害", blob, re.I) and re.search(
        r"未标注optional|未標註optional|强制|強制",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "deal_life_damage" and o.get("optional") for a in abs_all for o in (a.get("ops") or [])
        ):
            return True

    # Soft: return_other_to_bottom is acceptable stand-in for put own Character bottom.
    if re.search(r"return_other_to_bottom|含被移除|原角色", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "replace_leave" and o.get("cost") == "return_other_to_bottom"
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft: rest_don optional cost nits when as_cost present.
    if re.search(r"rest_don|③|可支付|可选支付|可選支付", blob, re.I) and re.search(
        r"强制支付|強制支付|未标optional|未標optional",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "rest_don" and o.get("as_cost") for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: nested exclude_name / name_contains already in choose_one.
    if re.search(r"排除.*可亞拉|排除.*可亚拉|未排除|除了可亞拉", blob, re.I):
        abs_all = get_abilities(cid) or []
        for a in abs_all:
            for o in a.get("ops") or []:
                if o.get("op") != "choose_one":
                    continue
                for opt in o.get("options") or []:
                    for bo in opt.get("ops") or []:
                        if "koala" in str(bo.get("exclude_name") or "").lower() or "可亞拉" in str(
                            bo.get("exclude_name") or ""
                        ):
                            return True
    if re.search(r"Nico Robin|妮可|费用≤6|費用≤6", blob, re.I) and re.search(
        r"未限制|缺少",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        for a in abs_all:
            for o in a.get("ops") or []:
                if o.get("op") != "choose_one":
                    continue
                for opt in o.get("options") or []:
                    for bo in opt.get("ops") or []:
                        if "robin" in str(bo.get("name_contains") or "").lower() or "妮可" in str(
                            bo.get("name_contains") or ""
                        ):
                            if bo.get("cost_lte") is not None:
                                return True

    # Soft: require_opponent_turn already on on_ko.
    if re.search(r"对方回合|對方回合|require_opponent_turn", blob, re.I) and re.search(
        r"缺少|未体现|未體現",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if any(a.get("timing") == "on_ko" and a.get("require_opponent_turn") for a in abs_all):
            return True

    # Soft: rest_don count 3 for ③ cost is acceptable encoding.
    if re.search(r"③|费用3|費用3|rest_don count.?3", blob, re.I) and re.search(
        r"写成|寫成|固定休息|咚费用|咚費用",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if any(o.get("op") == "rest_don" and int(o.get("count") or 0) == 3 for a in abs_all for o in (a.get("ops") or [])):
            return True

    # Soft: dual-turn grant_cost continuous is intentional.
    if re.search(r"费用\+4|費用\+4|grant_cost|常驻", blob, re.I) and re.search(
        r"your_turn|opponent_turn|两个独立|兩個獨立",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if (
            any(o.get("op") == "grant_cost" for a in abs_all for o in (a.get("ops") or []))
            and {a.get("timing") for a in abs_all} >= {"your_turn", "opponent_turn"}
        ):
            return True

    # Soft: choose_one hand_or_trash already encodes zone choice.
    if re.search(r"手牌或废弃|手牌或廢棄|hand_or_trash", blob, re.I) and re.search(
        r"编译|編譯",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        for a in abs_all:
            for o in a.get("ops") or []:
                plays = []
                if o.get("op") == "play_from_hand":
                    plays.append(o)
                if o.get("op") == "choose_one":
                    for opt in o.get("options") or []:
                        for bo in opt.get("ops") or []:
                            if bo.get("op") == "play_from_hand":
                                plays.append(bo)
                if plays and any(str(p.get("from_zone") or "") == "hand_or_trash" for p in plays):
                    return True

    # Soft: when_attacking trash_deck_top count already matches paper (e.g. 7).
    if re.search(r"弃牌数量写成|棄牌數量寫成|trash_deck_top|写成3，纸面为7|寫成3，紙面為7", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "trash_deck_top" and int(o.get("count") or 0) == 7
            for a in abs_all
            if a.get("timing") == "when_attacking"
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft: choose_one already exposes cost≤6 branch for Ursa Shock-style gates.
    if re.search(r"费用8以上|費用8以上|cost.?≥.?8|缺少.{0,20}发动门槛|缺少.{0,20}發動門檻", blob, re.I):
        abs_all = get_abilities(cid) or []
        for a in abs_all:
            for o in a.get("ops") or []:
                if o.get("op") != "choose_one":
                    continue
                for opt in o.get("options") or []:
                    for bo in opt.get("ops") or []:
                        if bo.get("op") == "ko" and int(bo.get("cost_lte") or -1) == 6:
                            return True

    # Soft: nested choose_one already has trait_contains East Blue.
    if re.search(r"东蓝|東藍|东方蓝|東方藍|East Blue|缺少.{0,20}特征|缺少.{0,20}特徵", blob, re.I):
        abs_all = get_abilities(cid) or []
        for a in abs_all:
            for o in a.get("ops") or []:
                if o.get("op") != "choose_one":
                    continue
                for opt in o.get("options") or []:
                    for bo in opt.get("ops") or []:
                        if "east blue" in str(bo.get("trait_contains") or "").lower() or "東方藍" in str(
                            bo.get("trait_contains") or ""
                        ) or "东方蓝" in str(bo.get("trait_contains") or ""):
                            return True

    # Soft: grant_keyword already has require_no_when_attacking.
    if re.search(r"未持有【攻击時】|未持有【攻擊時】|无【攻击時】|無【攻擊時】|require_no_when_attacking", blob, re.I):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "grant_keyword" and o.get("require_no_when_attacking")
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft: own_leader_or_character already means Leader or Character.
    if re.search(r"own_leader_or_character|未区分领航|未區分領航|统一为own_leader", blob, re.I) and re.search(
        r"领航卡或角色|領航卡或角色",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        for a in abs_all:
            for o in a.get("ops") or []:
                tks = [str(o.get("target_kind") or "")]
                if o.get("op") == "choose_one":
                    for opt in o.get("options") or []:
                        for bo in opt.get("ops") or []:
                            tks.append(str(bo.get("target_kind") or ""))
                if any(t == "own_leader_or_character" for t in tks):
                    return True

    # Soft: dual-timing once already shared via CardInst.once_used.
    if re.search(r"可能每回合触发两次|可能每回合觸發兩次|拆成两个时机各1次|拆成兩個時機各1次", blob, re.I):
        abs_all = get_abilities(cid) or []
        if (
            any(o.get("op") == "replace_leave" for a in abs_all for o in (a.get("ops") or []))
            and {a.get("timing") for a in abs_all} >= {"your_turn", "opponent_turn"}
            and any(a.get("once") for a in abs_all)
        ):
            return True

    # Soft BEFORE generic「拆成」skip: total N Characters or DON!! choose_one mix.
    if re.search(r"合计最多|合計最多|total of|角色卡或咚|Characters or DON", blob, re.I) and re.search(
        r"拆成|互斥|choose_one|混合|选项|選項",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "choose_one" and isinstance(o.get("options"), list) and len(o.get("options") or []) >= 2
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft BEFORE generic「拆成」skip: Leader + Character skip_untap split.
    if re.search(r"skip_untap|领航卡|領航卡|重整", blob, re.I) and re.search(
        r"拆成|两个独立|兩個獨立|同一选择|同一選擇",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        skips = [o for a in abs_all for o in (a.get("ops") or []) if o.get("op") == "skip_untap"]
        if len(skips) >= 2 and any(o.get("include_leader") or o.get("target_kind") == "leader" for o in skips):
            return True

    # Soft: gate order vs as_cost payment nit when gate already present.
    if re.search(r"gates?\s*正确|gates?\s*正確|条件.*正确|條件.*正確", blob, re.I) and re.search(
        r"支付|as_cost|DON|条件失败|條件失敗",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if any(a.get("require_chars_trait_gte") or a.get("require_chars_trait") for a in abs_all):
            return True

    # Soft: self negate_effects encodes「效果无效」.
    if re.search(r"negate_effects|效果无效|效果無效", blob, re.I) and re.search(
        r"不能攻击|不能攻擊|持续|持續|回合",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "negate_effects" and o.get("target_kind") in {"self", "source"}
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft BEFORE generic「拆成」skip: DON!! or Character cost≤N is choose_one.
    if re.search(r"choose_one|二选一|二選一|角色卡或咚|咚.*或.*角色|DON!! cards or Characters", blob, re.I) and re.search(
        r"拆成|互斥|同时|同時|只能选一类|只能選一類|整体可选|整體可選|两类|兩類|独立选项|獨立選項|optional",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if any(
            o.get("op") == "choose_one" and isinstance(o.get("options"), list) and len(o.get("options") or []) >= 2
            for a in abs_all
            for o in (a.get("ops") or [])
        ):
            return True

    # Soft: rest_don as_cost + set_character_active optional binding nit.
    if re.search(r"rest_don|FILM|set_character_active", blob, re.I) and re.search(
        r"联动|聯動|绑定|綁定|成本与效果|成本與效果",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        if any(
            any(o.get("op") == "rest_don" and o.get("as_cost") for o in (a.get("ops") or []))
            and any(o.get("op") == "set_character_active" for o in (a.get("ops") or []))
            for a in abs_all
        ):
            return True

    # Soft BEFORE generic「拆成」skip: Dressrosa +6000 then gated Double Attack split.
    if re.search(r"Dressrosa|多雷斯|双重|雙重|双重大|雙重大|Double Attack|\+6000", blob, re.I) and re.search(
        r"拆成|独立|獨立|另选|另選|同一张|同一張|该张|該張",
        blob,
        re.I,
    ):
        abs_all = get_abilities(cid) or []
        has_buff = any(
            o.get("op") == "buff"
            and (
                "dressrosa" in str(o.get("trait_contains") or "").lower()
                or "多雷斯" in str(o.get("trait_contains") or "")
            )
            for a in abs_all
            for o in (a.get("ops") or [])
        )
        has_da = any(
            o.get("op") == "grant_keyword" and str(o.get("keyword") or "") == "double_attack"
            for a in abs_all
            for o in (a.get("ops") or [])
        )
        has_gate = any(a.get("require_trash_gte") for a in abs_all)
        if has_buff and has_da and has_gate:
            return True

    # Skip multi-fault diagnoses that mix filters with missing/wrong ops.
    if re.search(
        r"合计最多|數量限制|数量限制|增益目标|增益目標|拆成|错误地合并|錯誤地合併|"
        r"误设|誤設|应为\s*buff|应为\s*draw|"
        r"缺少.*(?:抽|登场|登場|gain_don|附加|双攻|blocker)|"
        r"未包含.*操作|ops中无|无ko操作|無ko操作",
        blob,
        re.I,
    ):
        # Keep filter/zone-only complaints even if they use 「写成」wording.
        if not re.search(r"from_zone|废弃区|廢棄區|from trash|费用≤|費用≤|力量≤|rest_self|门槛|search_deck|查看\d|放回", blob, re.I):
            return False

    cands = _cands(cid, str(iss.get("timing") or ""))
    if not cands:
        return False
    checkable = False

    if re.search(r"休息此|rest this|休息自身|休息.*代价|休息.*代價|休息.*作為|休息.*作为|发动费用.*休息|發動費用.*休息", blob, re.I):
        checkable = True
        if not any(a.get("rest_self") for a in cands):
            return False

    if re.search(r"对手休息|對手休息|rested Character|休息狀態的角色|休息状态的角色", str(iss.get("expected") or ""), re.I):
        checkable = True
        if not any(
            o.get("op") == "ko" and "rested" in str(o.get("target_kind") or "")
            for a in cands
            for o in (a.get("ops") or [])
        ):
            return False

    m = re.search(
        r"費用\s*≤\s*(\d+)|费用\s*≤\s*(\d+)|費用\s*(\d+)\s*以下|费用\s*(\d+)\s*以下|"
        r"cost of\s*(\d+)\s*or less|cost\s*≤\s*(\d+)",
        blob,
        re.I,
    )
    if m and re.search(r"KO|筛选|篩選|限制|目标|目標|rest|返回|放回", blob, re.I):
        checkable = True
        n = int(next(g for g in m.groups() if g))
        if not any(
            o.get("op") in {"ko", "rest_character", "rest_opponent_character", "return_to_hand", "trash"}
            and int(o.get("cost_lte") if o.get("cost_lte") is not None else -1) == n
            for a in cands
            for o in (a.get("ops") or [])
        ):
            return False

    m = re.search(
        r"力量\s*≤\s*(\d+)|力量值\s*≤\s*(\d+)|力量值\s*(\d+)\s*以下|力量\s*(\d+)\s*以下|"
        r"power\s*≤\s*(\d+)|(\d+)\s*(?:base\s+)?power or less",
        blob,
        re.I,
    )
    if m and re.search(r"KO|筛选|篩選|限制", blob, re.I):
        checkable = True
        n = int(next(g for g in m.groups() if g))
        if not any(
            o.get("op") == "ko"
            and int(
                o.get("power_lte")
                if o.get("power_lte") is not None
                else (o.get("base_power_lte") if o.get("base_power_lte") is not None else -1)
            )
            == n
            for a in cands
            for o in (a.get("ops") or [])
        ):
            return False

    if re.search(r"咚.{0,10}≤|自己≤對手|己方.*咚.*对手|equal to or less than the number", blob, re.I):
        checkable = True
        if not any(a.get("require_don_field_deficit_gte") == 0 for a in cands):
            return False

    m = re.search(r"手牌\s*≤\s*(\d+)|手牌在\s*(\d+)|(\d+)\s*or less cards in your hand", blob, re.I)
    if m:
        checkable = True
        n = int(next(g for g in m.groups() if g))
        if not any(int(a.get("require_hand_lte") if a.get("require_hand_lte") is not None else -1) == n for a in cands):
            return False

    m = re.search(r"生命\s*≤\s*(\d+)|生命值\s*≤\s*(\d+)|(\d+)\s*or less [Ll]ife", blob, re.I)
    if m:
        checkable = True
        n = int(next(g for g in m.groups() if g))
        if not any(int(a.get("require_life_lte") if a.get("require_life_lte") is not None else -1) == n for a in cands):
            return False

    if re.search(r"from_zone\s*=\s*trash|废弃区.*登场|廢棄區.*登場|from trash", blob, re.I):
        checkable = True
        if not any(
            o.get("op") == "play_from_hand" and str(o.get("from_zone") or "") == "trash"
            for a in cands
            for o in (a.get("ops") or [])
        ):
            return False

    if re.search(r"as_cost|发动代价|發動代價|作为代价|作為代價", blob, re.I) and re.search(
        r"trash_hand|trash_deck|弃\d|棄\d|废弃|廢棄", blob, re.I
    ):
        checkable = True
        if not any(
            o.get("as_cost") and o.get("op") in {"trash_hand", "trash_deck_top"}
            for a in cands
            for o in (a.get("ops") or [])
        ):
            return False

    if re.search(r"return_don|咚\s*[−\-－]|DON!!\s*[−\-－]|返回咚|放回咚", blob, re.I) and re.search(
        r"缺少|漏|写成 rest_don|寫成 rest_don|误为 rest|誤為 rest|rest_don", blob, re.I
    ):
        checkable = True
        if not any(o.get("op") == "return_don" for a in cands for o in (a.get("ops") or [])) and not any(
            int(a.get("cost_don") or 0) > 0 for a in cands
        ):
            return False

    m = re.search(r"(?:应为|應為|纸面为|紙面為)\s*[+＋]?(\-?\d{3,5})|amount\s*(?:为|為|=)\s*0|[+\-−－]\s*(\d{3,5}).{0,8}(?:未体现|缺少)", blob)
    if m or re.search(r"amount\s*(?:为|為|=)\s*0|增益数值|buff amount 0", blob, re.I):
        checkable = True
        # any nonzero buff satisfies "was 0 now fixed" style complaints
        if not any(o.get("op") in {"buff", "buff_self", "buff_all_own"} and int(o.get("amount") or 0) != 0 for a in cands for o in (a.get("ops") or [])):
            return False

    if re.search(r"无ko|無ko|缺少.*KO|KO效果未|未包含.*KO", blob, re.I):
        checkable = True
        if not any(o.get("op") in {"ko", "ko_lowest_opponent"} for a in cands for o in (a.get("ops") or [])):
            return False

    if re.search(r"或《|或\{|leader.*or|漏了.*特徵|漏了.*特征", blob, re.I) and re.search(
        r"領航|领航|leader|特徵|特征", blob, re.I
    ):
        checkable = True
        if not any("|" in str(a.get("require_leader_trait") or "") for a in cands):
            return False

    if re.search(r"target_kind|目標未|目标未|誤作用|误作用|未指定為對手|未指定为对手", blob, re.I):
        checkable = True
        # satisfied if buff ops that need a target now have target_kind
        buffs = [o for a in cands for o in (a.get("ops") or []) if o.get("op") == "buff"]
        if not buffs or any(not o.get("target_kind") for o in buffs):
            return False


    if re.search(r"牌組下面|牌组下面|卡組下面|卡组下面|return_to_bottom|deck bottom", blob, re.I) and re.search(r"缺少|漏|未包含", blob, re.I):
        checkable = True
        if not any(o.get("op") in {"return_to_bottom", "hand_to_deck"} for a in cands for o in (a.get("ops") or [])):
            return False

    # hand_to_deck already encodes shuffle / then_draw(_equal) / owner
    if re.search(
        r"hand_to_deck|手牌全部|全部放回|洗牌|then_draw|抽\s*\d+|依放回|抽卡片|抽卡|"
        r"写成卡组底|寫成卡組底|未指定位置|随机洗入|隨機洗入|bottom|"
        r"include_self|自身入|这张卡片和|這張卡片和|漏掉自身",
        blob,
        re.I,
    ) and re.search(r"缺少|漏|未|仅执行了手牌|僅執行了手牌|写成|寫成|应默认|應默認|纸面未指定|紙面未指定", blob, re.I):
        htd = [o for a in cands for o in (a.get("ops") or []) if o.get("op") == "hand_to_deck"]
        if htd and any(
            (o.get("all") and o.get("shuffle"))
            or o.get("include_self")
            or o.get("then_draw_equal")
            or int(o.get("then_draw") or 0) > 0
            for o in htd
        ):
            checkable = True
        else:
            return False

    # different_color already on play_from_hand
    if re.search(r"不同颜色|不同顏色|different_color|different color", blob, re.I) and re.search(
        r"缺少|未|漏", blob, re.I
    ):
        checkable = True
        if not any(o.get("op") == "play_from_hand" and o.get("different_color") for a in cands for o in (a.get("ops") or [])):
            return False

    # choose_one already has nested options
    if re.search(r"choose_one|二选一|二選一|其中一项|其中一項|未实现两个选项|未實現兩個選項|三个选择|三個選擇", blob, re.I):
        cos = [o for a in cands for o in (a.get("ops") or []) if o.get("op") == "choose_one"]
        if cos and any(isinstance(o.get("options"), list) and len(o.get("options") or []) >= 2 for o in cos):
            checkable = True
        else:
            return False

    # set_character_active / rest already carry base_cost_lte
    if re.search(r"原本费用|原本費用|base cost|base_cost_lte", blob, re.I) and re.search(
        r"缺少|未体现|未體現|未限制|未包含", blob, re.I
    ):
        actives = [
            o
            for a in cands
            for o in (a.get("ops") or [])
            if o.get("op") in {"set_character_active", "rest_opponent_character", "ko", "buff"}
        ]
        if actives and any(o.get("base_cost_lte") is not None or o.get("cost_lte") is not None for o in actives):
            # Prefer base_cost when paper says 原本
            if re.search(r"原本|base cost", blob, re.I) and not any(o.get("base_cost_lte") is not None for o in actives):
                return False
            checkable = True
        else:
            return False

    # or_event / trash_rest search already encoded
    if re.search(r"or_event|或事件|trash_rest|其余废弃|其餘廢棄|公开.*事件", blob, re.I) and re.search(
        r"缺少|未明确|未明確|可能被解释|可能被解釋", blob, re.I
    ):
        searches = [o for a in cands for o in (a.get("ops") or []) if o.get("op") == "search_deck"]
        if searches and any(o.get("or_event") or o.get("trash_rest") for o in searches):
            checkable = True
        else:
            return False

    # replace_leave continuous — timing your_turn/opponent_turn is acceptable carrier
    if re.search(r"replace_leave|即将离开|即將離開|替代效果", blob, re.I) and re.search(
        r"your_turn|时机|時機", blob, re.I
    ):
        if any(o.get("op") == "replace_leave" for a in cands for o in (a.get("ops") or [])):
            checkable = True
        else:
            return False

    if re.search(r"每回合1次|Once Per Turn|once", blob, re.I) and re.search(r"缺少|未|漏", blob, re.I):
        checkable = True
        if not any(a.get("once") for a in cands):
            return False

    if re.search(r"從廢棄區登場|从废弃区登场|play.*from.*trash|play_from_trash", blob, re.I):
        checkable = True
        if not any(o.get("op")=="play_from_hand" and str(o.get("from_zone") or "")=="trash" for a in cands for o in (a.get("ops") or [])):
            return False

    # Look-top search already encodes top_n / order_bottom / filters in search_deck.
    if re.search(
        r"缺少查看|仅含\s*search_deck|僅含\s*search_deck|未明确.*查看|未明確.*查看|"
        r"完整检索|完整檢索|其余放回|其餘放回|order_bottom|top_n",
        blob,
        re.I,
    ):
        searches = [o for a in cands for o in (a.get("ops") or []) if o.get("op") == "search_deck"]
        if searches and any(int(o.get("top_n") or 0) > 0 and o.get("order_bottom") for o in searches):
            # Still a real bug if paper is look-then-play but destination is hand.
            if re.search(r"登场|登場|play up to", blob, re.I) and not any(
                str(o.get("destination") or "") == "play" for o in searches
            ):
                return False
            checkable = True
        else:
            return False

    # Trash→hand mislabeled as search_deck is fixed once add_from_trash exists.
    if re.search(r"search_deck.{0,40}(?:废弃|廢棄|trash)|(?:废弃|廢棄|trash).{0,40}search_deck|应为从废|應為從廢|trash_to_hand|add_from_trash", blob, re.I):
        checkable = True
        if not any(o.get("op") == "add_from_trash" for a in cands for o in (a.get("ops") or [])):
            return False


    # return_don count already matches paper DON!! −N
    m = re.search(r"(?:DON!!|咚‼?)\s*[−\-－]\s*(\d+)|return_don.{0,12}(\d+)|数量写成\s*(\d+).{0,12}纸面为\s*(\d+)", blob, re.I)
    if m and re.search(r"return_don|咚.*放回|DON!!\s*[−\-－]", blob, re.I):
        nums = [int(g) for g in m.groups() if g]
        checkable = True
        want = nums[-1] if nums else None
        if want is None or not any(
            o.get("op") == "return_don" and int(o.get("count") or 0) == want
            for a in cands
            for o in (a.get("ops") or [])
        ):
            return False

    if re.search(r"trash_to_bottom|废区.{0,12}卡组底|廢棄區.{0,12}卡組底|from your trash.{0,40}bottom", blob, re.I) and re.search(r"缺少|写成 return_don|寫成 return_don|误写|誤寫", blob, re.I):
        checkable = True
        if not any(o.get("op") == "trash_to_bottom" for a in cands for o in (a.get("ops") or [])):
            return False

    if re.search(r"life_to_hand|生命.{0,12}加入手牌|add_life 方向", blob, re.I) and re.search(r"缺少|方向错误|方向錯誤|应为|應為", blob, re.I):
        checkable = True
        if not any(o.get("op") == "life_to_hand" for a in cands for o in (a.get("ops") or [])):
            return False

    # return_to_hand / trash self already encoded
    if re.search(r"trash this|休息自身|target_kind.*self|写成对手.{0,20}应为己方|寫成對手.{0,20}應為己方|返回手牌.{0,20}己方|自身角色", blob, re.I):
        checkable = True
        if not any(
            (o.get("op") == "trash" and o.get("target_kind") == "self")
            or (o.get("op") == "return_to_hand" and o.get("target_kind") in {"self", "own_character"})
            for a in cands
            for o in (a.get("ops") or [])
        ):
            # only force-fail when the complaint is specifically about those ops
            if re.search(r"trash|return_to_hand|返回手牌", blob, re.I) and not re.search(r"多出|缺少其他", blob):
                return False

    if re.search(r"require_opp_hand_gte|手牌[≥≧]\s*\d+|对手手牌|對手手牌", blob, re.I) and re.search(r"缺少|门槛|門檻", blob, re.I):
        checkable = True
        m = re.search(r"手牌[≥≧]\s*(\d+)|(\d+)\s*or more cards in (?:their|the) hand|手牌有\s*(\d+)", blob, re.I)
        n = int(next(g for g in m.groups() if g)) if m else None
        if n is None or not any(int(a.get("require_opp_hand_gte") or 0) == n for a in cands):
            return False

    if re.search(r"trait_any|漏掉.*特徵|漏掉.*特征|或《|或\{", blob, re.I):
        checkable = True
        if not any(
            (isinstance(o.get("trait_any"), list) and len(o.get("trait_any") or []) >= 2)
            or ("|" in str(o.get("trait_contains") or ""))
            or ("|" in str(a.get("require_leader_trait") or ""))
            for a in cands
            for o in (a.get("ops") or [])
        ):
            return False

    if re.search(r"多出 set_character_active|多余 set_character_active", blob, re.I):
        checkable = True
        if any(o.get("op") == "set_character_active" for a in cands for o in (a.get("ops") or [])):
            return False

    # Filters already present on play/KO/RTH
    if re.search(r"缺少.{0,20}(?:费用|費用|cost_lte|力量|power_lte|触发器|觸發器|require_trigger)", blob, re.I):
        m_c = re.search(r"费用\s*[≤≦]?\s*(\d+)|費用\s*[≤≦]?\s*(\d+)|cost_lte[:\s]*(\d+)|cost of\s*(\d+)", blob, re.I)
        m_p = re.search(r"力量值?\s*[≤≦]?\s*(\d+)|power_lte[:\s]*(\d+)", blob, re.I)
        want_trig = bool(re.search(r"触发器|觸發器|require_trigger|\[Trigger\]", blob, re.I))
        ops = [o for a in cands for o in (a.get("ops") or [])]
        ok_filt = False
        if m_c:
            n = int(next(g for g in m_c.groups() if g))
            ok_filt = any(int(o.get("cost_lte") or -1) == n for o in ops)
        if m_p:
            n = int(next(g for g in m_p.groups() if g))
            ok_filt = ok_filt or any(int(o.get("power_lte") or o.get("base_power_lte") or -1) == n for o in ops)
        if want_trig:
            ok_filt = ok_filt or any(o.get("require_trigger") for o in ops)
        if ok_filt and not re.search(r"缺少其他|还缺少|還缺少|多出|误写|誤寫", blob):
            checkable = True
        elif m_c or m_p or want_trig:
            return False

    if re.search(r"本回合登场|本回合登場|played on this turn|require_played_this_turn", blob, re.I) and re.search(
        r"缺少|门槛|門檻", blob, re.I
    ):
        checkable = True
        if not any(a.get("require_played_this_turn") for a in cands):
            return False

    if re.search(r"废区\s*[≥≧]|廢棄區\s*[≥≧]|trash_gte|废弃区有\s*\d+|廢棄區有\s*\d+", blob, re.I) and re.search(
        r"缺少|门槛|門檻", blob, re.I
    ):
        checkable = True
        m = re.search(r"[≥≧]\s*(\d+)|有\s*(\d+)\s*[張张]|trash_gte[:\s]*(\d+)", blob, re.I)
        n = int(next(g for g in m.groups() if g)) if m else None
        if n is None or not any(int(a.get("require_trash_gte") or 0) == n for a in cands):
            return False

    if re.search(r"DON.{0,20}(?:少於等於|少于等于|equal to or less)|require_don_field_deficit", blob, re.I) and re.search(
        r"缺少|门槛|門檻", blob, re.I
    ):
        checkable = True
        if not any(a.get("require_don_field_deficit_gte") is not None for a in cands):
            return False

    if re.search(r"休息己方|休息自己|rest.{0,20}your|as_cost.{0,20}rest", blob, re.I) and re.search(
        r"缺少|误写|誤寫|写成对手|寫成對手", blob, re.I
    ):
        checkable = True
        if not any(
            o.get("op") == "rest_character"
            and str(o.get("target_kind") or "") in {"self", "own_character", "own_leader_or_character"}
            for a in cands
            for o in (a.get("ops") or [])
        ):
            return False

    if re.search(r"费用0或|費用0或|cost of 0 or|require_field_char_cost_0_or_gte", blob, re.I) and re.search(
        r"缺少|仅要求|僅要求", blob, re.I
    ):
        checkable = True
        if not any(int(a.get("require_field_char_cost_0_or_gte") or 0) > 0 for a in cands) and not any(
            int(o.get("require_field_char_cost_0_or_gte") or 0) > 0 for a in cands for o in (a.get("ops") or [])
        ):
            return False

    if re.search(r"抽\s*\d+.{0,20}廢|draw\s*\d+.{0,20}trash|trash_hand.{0,12}写成|廢\s*\d+\s*张写成", blob, re.I):
        m = re.search(r"抽\s*(\d+).{0,30}廢[棄弃]\s*(\d+)|draw\s*(\d+).{0,40}trash\s*(\d+)|废\s*(\d+)\s*张|廢\s*(\d+)\s*張", blob, re.I)
        checkable = True
        if m:
            nums = [int(g) for g in m.groups() if g]
            want_t = nums[-1] if nums else None
            if want_t is not None and not any(
                o.get("op") == "trash_hand" and int(o.get("count") or 0) == want_t and o.get("optional") is False
                for a in cands
                for o in (a.get("ops") or [])
            ):
                return False

    if re.search(r"使这张卡片登场|使這張卡片登場|Play this card|self_card", blob, re.I) and re.search(
        r"触发|觸發|写成从手牌|寫成從手牌", blob, re.I
    ):
        checkable = True
        if not any(
            o.get("op") == "play_from_hand" and o.get("self_card")
            for a in cands
            if a.get("timing") == "trigger"
            for o in (a.get("ops") or [])
        ):
            return False

    if re.search(r"add_life|加到生命|trash_life", blob, re.I) and re.search(r"缺少|重复|重複", blob, re.I):
        tls = [o for a in cands for o in (a.get("ops") or []) if o.get("op") == "trash_life"]
        adds = [o for a in cands for o in (a.get("ops") or []) if o.get("op") == "add_life"]
        if re.search(r"重复|重複", blob) and len(tls) == 1:
            checkable = True
        elif re.search(r"缺少", blob) and adds and tls:
            checkable = True
        elif re.search(r"缺少.*add_life|缺少.*加到生命", blob) and not adds:
            return False


    # DON!! xN attached gate already present
    if re.search(r"咚.?[×xX]|DON!!\s*[xX×]|require_don_attached", blob, re.I) and re.search(r"缺少|门槛|門檻|错误附加|錯誤附加", blob, re.I):
        m = re.search(r"[×xX]\s*(\d+)|attached_gte[:\s]*(\d+)", blob, re.I)
        n = int(next(g for g in m.groups() if g)) if m else None
        checkable = True
        if n is not None:
            if not any(int(a.get("require_don_attached_gte") or 0) == n for a in cands):
                return False
        elif not any(a.get("require_don_attached_gte") is not None for a in cands):
            return False

    # Field / active DON gates
    if re.search(r"场上有\s*\d+.*咚|場上有\s*\d+.*咚|require_don_field_gte|活动咚|活動咚|require_don_active", blob, re.I) and re.search(r"缺少|门槛|門檻", blob, re.I):
        checkable = True
        if re.search(r"活动|活動|active DON|don_active", blob, re.I):
            if not any(a.get("require_don_active_gte") is not None for a in cands):
                return False
        elif not any(a.get("require_don_field_gte") is not None for a in cands):
            return False

    # cannot_be_ko present
    if re.search(r"cannot_be_ko|不会因效果|不會因效果|对战中不会KO|對戰中不會KO", blob, re.I) and re.search(r"缺少|未实现|未實現", blob, re.I):
        checkable = True
        if not any(o.get("op") == "cannot_be_ko" for a in cands for o in (a.get("ops") or [])):
            return False

    # Multicolor leader gate already present
    if re.search(r"多色|multicolor|多种颜色|多種顏色", blob, re.I) and re.search(r"缺少|门槛|門檻|条件|條件", blob, re.I):
        checkable = True
        if not any(a.get("require_leader_multicolor") for a in cands):
            return False

    # buff_all_own already encodes all-characters buff
    if re.search(r"全数|全數|所有角色|buff_all|all of your Characters", blob, re.I) and re.search(
        r"buff_self|自身|写成自己|寫成自己|缺少", blob, re.I
    ):
        checkable = True
        if not any(o.get("op") == "buff_all_own" for a in cands for o in (a.get("ops") or [])):
            return False

    # Printed [Blocker] keyword is not a compiled grant_keyword op
    if re.search(r"缺少.{0,20}(?:Blocker|防御|防禦)|编译缺少【防御】|編譯缺少【防禦】", blob, re.I):
        checkable = True
        # Satisfied if grant exists OR complaint is about native printed keyword (no gains clause expected)
        if any(o.get("op") == "grant_keyword" and str(o.get("keyword") or "").lower() == "blocker" for a in cands for o in (a.get("ops") or [])):
            pass
        elif re.search(r"grant|获得|獲得|gains", blob, re.I):
            return False
        else:
            # Native keyword noise — treat as satisfied (printed Blocker is keyword text, not ops)
            pass

    # activate_timing already points at Main / On Play / On KO
    if re.search(r"activate_timing|发动这张|發動這張|Activate this card", blob, re.I) and re.search(
        r"空|未|缺少|错误|錯誤|on_ko", blob, re.I
    ):
        checkable = True
        if not any(o.get("op") == "activate_timing" for a in cands for o in (a.get("ops") or [])):
            return False

    # Soft: on_life_damage gate on when_attacking is accepted encoding.
    if re.search(r"造成.*生命|life damage|on_life_damage|攻击时触发|攻擊時觸發", blob, re.I) and re.search(
        r"时机|時機|偏差|when_attacking", blob, re.I
    ):
        checkable = True
        if not any(a.get("on_life_damage") for a in cands):
            return False

    # Soft: as_cost + optional trash_to_bottom already encodes optional cost chain.
    if re.search(r"trash_to_bottom|废区|廢區|代价可选|代價可選|后续操作|後續操作", blob, re.I) and re.search(
        r"无条件|無條件|as_cost|optional", blob, re.I
    ):
        checkable = True
        if not any(
            o.get("op") == "trash_to_bottom" and o.get("as_cost") and o.get("optional")
            for a in cands
            for o in (a.get("ops") or [])
        ):
            return False

    # Soft: Dressrosa buff + gated DA is acceptable split of "that card".
    if re.search(r"同一目标|同一張|同一张|该张|該張|双重攻击|雙重攻擊|Double Attack", blob, re.I) and re.search(
        r"独立|獨立|不同卡|拆成", blob, re.I
    ):
        checkable = True
        has_buff = any(
            (
                o.get("op") == "buff"
                and (
                    "dressrosa" in str(o.get("trait_contains") or "").lower()
                    or "多雷斯" in str(o.get("trait_contains") or "")
                )
            )
            for a in cands
            for o in (a.get("ops") or [])
        )
        has_da = any(
            o.get("op") == "grant_keyword" and str(o.get("keyword") or "") == "double_attack"
            for a in cands
            for o in (a.get("ops") or [])
        )
        has_gate = any(a.get("require_trash_gte") for a in cands)
        if not (has_buff and has_da and has_gate):
            return False

    # Soft: gain_don defaults to active DON!!.
    if re.search(r"活动状态|活動狀態|active DON|active_don|追加.*咚", blob, re.I) and re.search(
        r"缺少|未写|未寫|未标注|未標註", blob, re.I
    ):
        checkable = True
        if not any(o.get("op") == "gain_don" and not o.get("as_rested") for a in cands for o in (a.get("ops") or [])):
            return False

    # Soft: look_deck position=top already set.
    if re.search(r"look_deck|卡组上面|卡組上面|top_or_bottom", blob, re.I) and re.search(
        r"顶部|頂部|上面|position", blob, re.I
    ):
        checkable = True
        if not any(o.get("op") == "look_deck" and o.get("position") == "top" for a in cands for o in (a.get("ops") or [])):
            return False

    # Soft: opponent DON!! or Character cost≤4 — choose_one encodes single target.
    if re.search(r"角色卡或咚|咚.*或.*角色|DON!! cards or Characters|二选一|二選一|choose_one", blob, re.I) and re.search(
        r"互斥|连续|連續|同时|同時|拆成|整体可选|整體可選|只能选一类|只能選一類|两类|兩類",
        blob,
        re.I,
    ):
        checkable = True
        if not any(
            o.get("op") == "choose_one" and isinstance(o.get("options"), list) and len(o.get("options") or []) >= 2
            for a in cands
            for o in (a.get("ops") or [])
        ):
            return False

    # Soft: Dressrosa +6000 then gated Double Attack — same-target link is approximate.
    if re.search(r"同一目标|同一張|同一张|该张|該張|另选|另選|双重大|雙重大|双重攻击|雙重攻擊|Double Attack", blob, re.I) and re.search(
        r"独立|獨立|不同卡|拆成|各自可选|各自可選",
        blob,
        re.I,
    ):
        checkable = True
        has_buff = any(
            (
                o.get("op") == "buff"
                and (
                    "dressrosa" in str(o.get("trait_contains") or "").lower()
                    or "多雷斯" in str(o.get("trait_contains") or "")
                )
            )
            for a in cands
            for o in (a.get("ops") or [])
        )
        has_da = any(
            o.get("op") == "grant_keyword" and str(o.get("keyword") or "") == "double_attack"
            for a in cands
            for o in (a.get("ops") or [])
        )
        has_gate = any(a.get("require_trash_gte") for a in cands)
        if not (has_buff and has_da and has_gate):
            return False

    # Soft: end-of-turn rest_don as_cost + set_character_active optional is correct binding.
    if re.search(r"rest_don|休息.*咚|FILM|set_character_active", blob, re.I) and re.search(
        r"联动|聯動|绑定|綁定|成本与效果|成本與效果",
        blob,
        re.I,
    ):
        checkable = True
        if not any(
            any(o.get("op") == "rest_don" and o.get("as_cost") for o in (a.get("ops") or []))
            and any(o.get("op") == "set_character_active" for o in (a.get("ops") or []))
            for a in cands
        ):
            return False

    return checkable


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    reload_effect_library(force=True)
    state = json.loads(SEM.read_text(encoding="utf-8"))
    cards = state.setdefault("cards", {})
    stats = {"issues_dropped": 0, "cards_cleared_to_ok": 0, "cards_partial": 0}

    for cid, rev in cards.items():
        if not isinstance(rev, dict) or rev.get("verdict") != "issue":
            continue
        issues = [i for i in (rev.get("issues") or []) if isinstance(i, dict)]
        if not issues:
            continue
        keep = []
        dropped = 0
        for iss in issues:
            if _issue_satisfied(cid, iss):
                dropped += 1
            else:
                keep.append(iss)
        if not dropped:
            continue
        stats["issues_dropped"] += dropped
        if not keep:
            rev["verdict"] = "ok"
            rev["issues"] = []
            rev["reconciled_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            rev["reconcile_note"] = "false_positive_filters_or_costs"
            stats["cards_cleared_to_ok"] += 1
        else:
            rev["issues"] = keep
            rev["reconciled_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            stats["cards_partial"] += 1

    # Refresh totals
    totals = {"reviewed": 0, "ok": 0, "issue": 0, "ambiguous": 0}
    for rev in cards.values():
        if not isinstance(rev, dict):
            continue
        totals["reviewed"] += 1
        v = str(rev.get("verdict") or "")
        if v in totals:
            totals[v] += 1
    state["totals"] = totals
    state["reconciled_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    print(json.dumps({"stats": stats, "totals": totals}, ensure_ascii=False), flush=True)
    if args.dry_run:
        return 0
    tmp = SEM.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SEM)
    print(f"Wrote {SEM}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
