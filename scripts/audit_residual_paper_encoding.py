#!/usr/bin/env python3
"""Paper-vs-encoding residual auditor for Chinese HK OPCG effects.

Flags true positives for:
  - missing timing abilities (skipping 持有【觸發器】 / 對手的【登場時】 false positives)
  - DON!! −N without matching return_don / cost_don
  - restricted deck searches encoded without filters
  - choose_one missing when 選擇下列
  - DON!!×N missing require_don_attached_gte
  - 對手的生命值 gate encoded as own-life (or missing opp gate)
  - Event 【主要】 without on_play
  - 放回費用區 attached-DON cost without return_attached_don

Usage:
  .venv/bin/python scripts/audit_residual_paper_encoding.py

Writes meta/residual_audit.json and exits 0 only when empty.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effect_schema import ability_is_runnable  # noqa: E402


def is_real_timing(text: str, marker: str) -> bool:
    for m in re.finditer(re.escape(marker), text):
        pre = text[max(0, m.start() - 8) : m.start()]
        if any(pre.endswith(p) for p in ("持有", "未持有", "自己的", "對手的", "发动", "發動", "或")):
            continue
        return True
    return False


def chunk_after(text: str, marker: str) -> str:
    for m in re.finditer(re.escape(marker), text):
        pre = text[max(0, m.start() - 8) : m.start()]
        if any(pre.endswith(p) for p in ("持有", "未持有", "自己的", "對手的", "发动", "發動", "或")):
            continue
        return re.split(r"【", text[m.end() :], maxsplit=1)[0].strip()
    return ""


def _iter_ops(abilities: list[dict[str, Any]]):
    for a in abilities or []:
        for o in a.get("ops") or []:
            yield a, o
            if o.get("op") == "choose_one":
                for opt in o.get("options") or []:
                    for nested in opt.get("ops") or []:
                        yield a, nested


def _blob(abilities: list[dict[str, Any]]) -> str:
    return json.dumps(abilities, ensure_ascii=False)


def main() -> int:
    reload_effect_library(force=True)
    cards = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    issues: list[dict[str, str]] = []

    for cid, c in cards.items():
        text = c.get("effect") or ""
        if not str(text).strip():
            continue
        entry = get_card_entry(cid)
        ctype = c.get("card_type")
        abs_ = list((entry or {}).get("abilities") or [])
        blob = _blob(abs_)

        markers = [
            ("activate_main", "【啟動主要】"),
            ("on_play", "【登場時】"),
            ("when_attacking", "【攻擊時】"),
            ("on_opponent_attack", "【對方攻擊時】"),
            ("on_ko", "【KO時】"),
            ("counter_event", "【反擊】"),
            ("trigger", "【觸發器】"),
        ]
        if "【對手攻擊時】" in text and "【對方攻擊時】" not in text:
            markers = [
                (t, "【對手攻擊時】") if t == "on_opponent_attack" else (t, m) for t, m in markers
            ]

        for timing, marker in markers:
            if not is_real_timing(text, marker):
                continue
            acts = [a for a in abs_ if a.get("timing") == timing]
            if not acts:
                if timing == "activate_main" and ctype == "Event" and any(
                    a.get("timing") == "on_play" for a in abs_
                ):
                    continue
                issues.append(
                    {
                        "sev": "high",
                        "kind": "missing_timing",
                        "id": cid,
                        "detail": f"{timing}: {chunk_after(text, marker)[:70]}",
                    }
                )
            elif not any(ability_is_runnable(a) for a in acts):
                issues.append({"sev": "high", "kind": "nonrunnable", "id": cid, "detail": timing})

        for timing, marker in [
            ("activate_main", "【啟動主要】"),
            ("counter_event", "【反擊】"),
            ("on_play", "【登場時】"),
            ("when_attacking", "【攻擊時】"),
            ("on_opponent_attack", "【對方攻擊時】"),
        ]:
            if timing == "on_opponent_attack" and "【對方攻擊時】" not in text and "【對手攻擊時】" in text:
                marker = "【對手攻擊時】"
            if not is_real_timing(text, marker):
                continue
            chunk = chunk_after(text, marker)
            md = re.search(r"咚‼?\s*[-−－–]\s*(\d+)|咚‼?-(\d+)", chunk)
            if not md:
                continue
            n = int(md.group(1) or md.group(2))
            acts = [a for a in abs_ if a.get("timing") == timing]
            ops: list[dict] = []
            cost_don = 0
            for a in acts:
                ops.extend(a.get("ops") or [])
                cost_don = max(cost_don, int(a.get("cost_don") or 0))
            ret = sum(int(o.get("count") or 0) for o in ops if o.get("op") == "return_don")
            if ret != n and cost_don != n:
                issues.append(
                    {
                        "sev": "high",
                        "kind": "don_minus",
                        "id": cid,
                        "detail": f"{timing} paper={n} ret={ret} cost_don={cost_don}",
                    }
                )

        for timing, marker in [
            ("activate_main", "【啟動主要】"),
            ("on_play", "【登場時】"),
            ("trigger", "【觸發器】"),
        ]:
            if not is_real_timing(text, marker):
                continue
            chunk = chunk_after(text, marker)
            if not re.search(r"從自己的卡組上面查看", chunk):
                continue
            has_filter = bool(
                re.search(
                    r"擁有《|費用\d+|「[^」]+」|\(斬\)|綠色|紅色|藍色|黃色|黑色|紫色|事件卡|力量值\d+|持有【觸發器】",
                    chunk,
                )
            )
            ops = [
                o
                for a in abs_
                if a.get("timing") == timing
                for o in (a.get("ops") or [])
                if o.get("op") == "search_deck"
            ]
            if not ops and re.search(r"公開最多|使最多1張「", chunk):
                issues.append({"sev": "high", "kind": "search_missing", "id": cid, "detail": timing})
                continue
            for o in ops:
                restricted = any(
                    [
                        o.get("trait_contains"),
                        o.get("trait_any"),
                        o.get("name_contains"),
                        o.get("cost_lte") is not None,
                        o.get("cost_gte") is not None,
                        o.get("cost_eq") is not None,
                        o.get("power_lte") is not None,
                        o.get("power_gte") is not None,
                        o.get("power_eq") is not None,
                        o.get("attr_contains"),
                        o.get("color"),
                        o.get("or_event"),
                        o.get("require_trigger"),
                        o.get("exclude_name"),
                        o.get("card_type") in {"event", "stage", "character"},
                    ]
                )
                if has_filter and not restricted:
                    issues.append(
                        {
                            "sev": "high",
                            "kind": "search_unfiltered",
                            "id": cid,
                            "detail": f"{timing} {chunk[:70]}",
                        }
                    )

        # choose_one
        if re.search(r"選擇下列其中一項|选择下列其中一项", text):
            if not any(o.get("op") == "choose_one" for _, o in _iter_ops(abs_)):
                issues.append(
                    {"sev": "high", "kind": "missing_choose_one", "id": cid, "detail": "選擇下列"}
                )

        # DON!! ×N attached gate
        m_don = re.search(r"【咚‼?\s*[×xX]\s*(\d+)】|【咚!!\s*[×xX]\s*(\d+)】", text)
        if m_don:
            n = int(m_don.group(1) or m_don.group(2))
            if f'"require_don_attached_gte": {n}' not in blob and f'"require_don_attached_gte":{n}' not in blob:
                # also accept ability-level without space
                has = any(int(a.get("require_don_attached_gte") or 0) >= n for a in abs_)
                if not has:
                    issues.append(
                        {
                            "sev": "high",
                            "kind": "missing_don_x",
                            "id": cid,
                            "detail": f"DON!!×{n}",
                        }
                    )

        # Opponent life gate ownership
        for m in re.finditer(r"對手的生命值卡在\s*(\d+)\s*張(以上|以下)", text):
            n = int(m.group(1))
            kind = m.group(2)
            need = f"require_opp_life_{'gte' if kind == '以上' else 'lte'}"
            wrong = f"require_life_{'gte' if kind == '以上' else 'lte'}"
            has_need = need in blob or "require_either_life" in blob or "require_total_life" in blob
            # also check op-level nested
            if not has_need:
                has_need = any(o.get(need) is not None for _, o in _iter_ops(abs_))
            has_wrong = wrong in blob or any(o.get(wrong) is not None for _, o in _iter_ops(abs_))
            if not has_need and has_wrong:
                issues.append(
                    {
                        "sev": "high",
                        "kind": "opp_life_as_own",
                        "id": cid,
                        "detail": f"{m.group(0)} encoded as {wrong}",
                    }
                )
            elif not has_need:
                issues.append(
                    {
                        "sev": "high",
                        "kind": "missing_opp_life_gate",
                        "id": cid,
                        "detail": f"{m.group(0)} need {need}",
                    }
                )

        # Event Main → on_play
        if ctype == "Event" and re.search(r"【主要】|【MAIN】|\[Main\]", text, re.I):
            if not any(a.get("timing") == "on_play" for a in abs_):
                issues.append(
                    {"sev": "high", "kind": "event_main_missing_on_play", "id": cid, "detail": ""}
                )

        # Attached DON!! → cost area
        if re.search(r"已附加的咚‼?卡.{0,24}放回費用區|已附加的咚!!卡.{0,24}放回费用区", text):
            if not any(o.get("op") == "return_attached_don" for _, o in _iter_ops(abs_)):
                issues.append(
                    {
                        "sev": "high",
                        "kind": "missing_return_attached_don",
                        "id": cid,
                        "detail": "放回費用區",
                    }
                )

        # either-life / reorder ownership
        if re.search(r"查看最多\d*張?自己或對手生命值|查看最多1張自己或對手生命", text):
            has = False
            for _, o in _iter_ops(abs_):
                if o.get("op") in {"reorder_life", "look_life"} and o.get("owner") == "self_or_opponent":
                    has = True
                    break
            if not has:
                issues.append(
                    {
                        "sev": "high",
                        "kind": "either_life_owner",
                        "id": cid,
                        "detail": "自己或對手生命 without self_or_opponent reorder",
                    }
                )

        # Trigger-activate watcher: 發動【觸發器】時 (not 持有【觸發器】)
        if re.search(r"(?<![持未])發動【觸發器】時", text) or re.search(
            r"【對方回合中】發動【觸發器】時", text
        ):
            if not any(a.get("timing") in {"on_trigger", "on_opp_trigger"} for a in abs_):
                # also accept on_event only if paper is Event-play watch — exclude here
                issues.append(
                    {
                        "sev": "high",
                        "kind": "missing_on_trigger",
                        "id": cid,
                        "detail": "發動【觸發器】時",
                    }
                )

        # Unqualified field Character cost/power gate → bilateral require_field_char_*
        for m in re.finditer(r"若場上有(力量值(\d+)以上|費用(\d+)以上)的角色卡", text):
            pre = text[max(0, m.start() - 6) : m.start()]
            if "自己的" in pre or "對手的" in pre:
                continue
            # Skip when immediately preceded by 自己/對手 without 的 in rare forms
            if re.search(r"(自己|對手)$", pre):
                continue
            if m.group(2):
                need = f"require_field_char_base_power_gte"
                n = int(m.group(2))
            else:
                need = "require_field_char_cost_gte"
                n = int(m.group(3))
            has = need in blob or any(o.get(need) == n for _, o in _iter_ops(abs_))
            has = has or any(int(a.get(need) or -1) == n for a in abs_)
            if not has:
                issues.append(
                    {
                        "sev": "medium",
                        "kind": "missing_bilateral_field_gate",
                        "id": cid,
                        "detail": f"{m.group(0)} need {need}={n}",
                    }
                )

        # Continuous per-count self power missing scaler flags
        if re.search(
            r"(每有\d+張|每有\d+张|for every \d+|自己每有\d+張).{0,40}(力量|power)|"
            r"(力量[值]?[＋+]\d{3,5}|gains? \+\d{3,5} power).{0,40}(每有|for every)",
            text,
            re.I,
        ):
            # Skip one-shot battle/Main scalers (not continuous static power).
            if re.search(r"【對方攻擊時】|【对手攻击时】|在這場對戰中|在这场对战中", text):
                pass
            elif re.search(r"^【主要】|【MAIN】", text) and not re.search(
                r"【我方回合中】|【咚‼?\s*[×xX]", text
            ):
                pass
            else:
                expect_keys: list[str] = []
                if re.search(r"名稱不同|different card name|カード名の異なる", text, re.I):
                    expect_keys.append("per_distinct_own_char_names")
                if re.search(r"休息狀態的咚|rested DON", text, re.I):
                    expect_keys.append("per_rested_don")
                if re.search(r"廢棄區中每有\d+張事件|Events? in your trash", text, re.I):
                    expect_keys.append("per_trash_events")
                elif re.search(r"廢棄區中每有\d+張卡片|cards? in your trash", text, re.I):
                    expect_keys.append("per_trash_cards")
                if expect_keys:
                    got = set()
                    for _, o in _iter_ops(abs_):
                        if o.get("op") != "buff_self":
                            continue
                        for k in expect_keys:
                            if o.get(k):
                                got.add(k)
                    missing = [k for k in expect_keys if k not in got]
                    if missing:
                        issues.append(
                            {
                                "sev": "high",
                                "kind": "missing_power_scaler",
                                "id": cid,
                                "detail": ",".join(missing),
                            }
                        )

        # Continuous per-count self power missing scaler flags
        # DON!!×N must not be compiled as return_don cost (unless paper also has 咚−N)
        if m_don and not re.search(r"咚‼?\s*[-−－–]\s*\d+|咚‼?-\d+", text):
            for a, o in _iter_ops(abs_):
                if o.get("op") == "return_don" and int(o.get("count") or 0) == int(
                    m_don.group(1) or m_don.group(2)
                ):
                    # Heuristic: when_attacking/your_turn with only return_don+buff is wrong for ×N
                    if a.get("timing") in {"when_attacking", "your_turn", "on_opp_event", "opponent_turn"}:
                        issues.append(
                            {
                                "sev": "medium",
                                "kind": "don_x_as_return_don",
                                "id": cid,
                                "detail": f"{a.get('timing')} return_don for DON!!×",
                            }
                        )
                        break

    out = ROOT / "meta" / "residual_audit.json"
    out.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")
    by = Counter(i["kind"] for i in issues)
    print({"total": len(issues), "by_kind": dict(by), "wrote": str(out)})
    for i in issues[:80]:
        print(f"[{i['kind']}] {i['id']}: {i['detail']}")
    if len(issues) > 80:
        print(f"... +{len(issues) - 80} more")
    if issues:
        print("RESIDUAL_REMAINING")
        return 1
    print("ZERO_RESIDUAL_REACHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
