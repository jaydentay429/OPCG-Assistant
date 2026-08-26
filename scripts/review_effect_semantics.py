#!/usr/bin/env python3
"""LLM semantic review: paper text vs compiled abilities (diagnosis-level).

Usage:
  .venv/bin/python scripts/review_effect_semantics.py --limit 20
  .venv/bin/python scripts/review_effect_semantics.py --resume
  .venv/bin/python scripts/review_effect_semantics.py --ids OP14-120,OP16-048

Writes:
  meta/effect_semantic_review.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from battle.effect_library import get_abilities, reload_effect_library  # noqa: E402
from battle.effect_schema import ability_is_runnable  # noqa: E402
from battle.effects import detect_keywords, effect_blob, has_meaningful_effect_text  # noqa: E402

OUT_PATH = ROOT / "meta" / "effect_semantic_review.json"


def _base_card_id(cid: str) -> str:
    return re.sub(r"-(?:P|R)\d+$", "", cid)


def _make_asker(*, max_tokens: int = 1200, timeout: int = 60):
    api_key = str(os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    def ask(prompt: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an OPTCG rules engineer. Compare paper card text to compiled "
                        "battle abilities. Return ONLY compact JSON. Prefer Chinese short diagnoses."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        return str(resp.choices[0].message.content or "").strip()

    return ask


def _abilities_digest(abilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for a in abilities:
        if not isinstance(a, dict):
            continue
        ops = []
        for o in a.get("ops") or []:
            if not isinstance(o, dict) or not o.get("op"):
                continue
            slim = {"op": o.get("op")}
            for k in (
                "count",
                "amount",
                "target_kind",
                "keyword",
                "once",
                "as_cost",
                "cost_don",
                "cost_lte",
                "cost_eq",
                "cost_gte",
                "power_lte",
                "base_power_lte",
                'opp_effect_power_lte',
                'opp_effect_base_power_lte',
                'base_power_eq',
                "base_power_gte",
                "base_cost_lte",
                "base_cost_gte",
                "from_zone",
                "trait_contains",
                "trait_any",
                "name_contains",
                "exclude_name",
                "top_n",
                "max_add",
                "order_bottom",
                "destination",
                "card_type",
                "color",
                "require_trigger",
                "require_don_attached_gte",
                "require_opp_char_cost_0_or_gte",
                "require_field_char_cost_eq",
                "require_field_char_cost_gte",
                "require_opp_char_cost_eq",
                "require_chars_base_cost_gte",
                "require_chars_base_cost_count_gte",
                "require_chars_base_cost_count_lte",
                "require_chars_cost_sum_gte",
                "require_no_own_name_on_field",
                "require_own_name_contains",
                "on_char_rested_by_own_effect",
                "on_don_returned",
                "as_rested",
                "as_cost",
                "buff_self_per_n",
                "buff_self_amount",
                "include_leader",
                "don_attached_gte",
                "if_revealed_cost_lte",
                "if_revealed_trait_contains",
                "if_revealed_trait_includes",
                "if_declared_cost_match",
                "declare_cost",
                "no_base_effect",
                "require_trigger",
                "per_own_chars",
                "per_returned_chars",
                "per_own_trait",
                "trait_includes",
                "power_eq",
                "self_card",
                "exclude_self",
                "all",
                "optional",
                "reason",
                "owner",
                "position",
                "face",
                "face_up",
                "to_deck_top",
                "attribute",
                "cost_in",
                "duration",
                "self_card",
                "until_life_eq",
                "per_rested_don",
                "per_trash_cards",
                "per_trash_events",
                "per_choose",
                "timing",
                "shuffle",
                "then_draw",
                "then_draw_equal",
                "include_self",
                "or_event",
                "trash_rest",
                "different_color",
                "as_rested",
                "require_opp_chars_count_gte",
                "require_opp_chars_count_lte",
                "rested_only",
                "name_or_trait",
                "per_own_trait",
                "then_trash_equal",
                "include_leader",
                "don_count",
                "per_hand_cards",
                "no_base_effect",
                "unless_field_char_base_power_gte",
                "trash_count",
                "different_names",
                "on_opp_ko",
                "on_life_damage",
                "require_opp_char_base_power_gte",
                "power_gte",
                "cost_gte",
                "color",
                "until_hand_size",
                "next_only",
                "any_leave",
                "cost_lte_opp_don_field",
                "cost_lte_own_don_field",
                "cost_lte_total_life",
                "cost_lte_opp_life",
                "equal_trashed",
                "from_zone",
                "trigger",
                "target",
                "cost",
                "rest_count",
                "rest_name_contains",
                "rest_trait_contains",
                "require_no_on_play",
                "hand_trait_contains",
                "attribute",
                "require_no_when_attacking",
                "if_revealed_power_gte",
                "trash_rest",
                "destination",
                "same_name_as_trashed",
                "base_power_gte",
                "base_power_lte",
                "power_lte",
            ):
                if o.get(k) is not None and o.get(k) != "" and o.get(k) is not False:
                    slim[k] = o.get(k)
            then = o.get("then_op")
            if isinstance(then, dict) and then.get("op"):
                then_slim = {"op": then.get("op")}
                for k in (
                    "count",
                    "amount",
                    "target_kind",
                    "cost_lte",
                    "cost_eq",
                    "power_lte",
                    "base_power_lte",
                    "owner",
                    "position",
                    "face",
                    "optional",
                    "as_cost",
                ):
                    if then.get(k) is not None and then.get(k) != "" and then.get(k) is not False:
                        then_slim[k] = then.get(k)
                slim["then_op"] = then_slim
            # Nested choose_one branches — without this the reviewer invents "empty choose_one".
            if o.get("op") == "choose_one" and isinstance(o.get("options"), list):
                opt_slim = []
                for opt in o.get("options") or []:
                    if not isinstance(opt, dict):
                        continue
                    branch = {"id": opt.get("id"), "label": (opt.get("label") or "")[:80]}
                    for gk, gv in opt.items():
                        if str(gk).startswith("require_") and gv is not None and gv is not False and gv != "":
                            branch[gk] = gv
                    bops = []
                    for bo in opt.get("ops") or []:
                        if not isinstance(bo, dict) or not bo.get("op"):
                            continue
                        bs = {"op": bo.get("op")}
                        for k in (
                            "count",
                            "amount",
                            "target_kind",
                            "cost_lte",
                            "cost_eq",
                            "cost_gte",
                            "owner",
                            "face",
                            "all",
                            "position",
                            "optional",
                            "duration",
                            "trait_contains",
                            "include_leader",
                            "require_no_when_attacking",
                            "require_no_on_play",
                            "name_contains",
                            "exclude_name",
                            "from_zone",
                        ):
                            if bo.get(k) is not None and bo.get(k) != "" and bo.get(k) is not False:
                                bs[k] = bo.get(k)
                        bops.append(bs)
                    branch["ops"] = bops
                    if bops:
                        opt_slim.append(branch)
                if opt_slim:
                    slim["options"] = opt_slim
            ops.append(slim)
        gates = {
            k: a.get(k)
            for k in a
            if (
                str(k).startswith("require_")
                or k
                in {
                    "on_opp_ko",
                    "on_life_damage",
                    "on_opp_play_character",
                    "cannot_play_by_effect_from_hand",
                    "characters_enter_rested",
                    "on_ko_caused_by_battle",
                    "on_char_rested_by_own_effect",
                    "on_char_leave_by_own_effect",
                    "on_any_own_don_attach",
                    "on_hand_trashed_by_effect",
                    "negated_when_hand_trashed",
                    "trigger_on",
                    "on_own_trait_leave_or_ko",
                    "on_own_trait_ko",
                    "on_ko_by_opp_effect",
                    "about_to_leave",
                    "on_ko_caused_by_battle",
                }
            )
            and a.get(k) is not None
        }
        entry: dict[str, Any] = {
            "timing": a.get("timing"),
            "status": a.get("status"),
            "once": a.get("once"),
            "summary": str(a.get("summary") or "")[:160],
            "runnable": ability_is_runnable(a),
            "gates": gates or None,
            "ops": ops[:16],
        }
        if a.get("rest_self"):
            entry["rest_self"] = True
        if a.get("cost_don"):
            entry["cost_don"] = a.get("cost_don")
        out.append(entry)
    return out


def _parse_json_payload(raw: str) -> dict[str, Any] | None:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S)
    try:
        data = json.loads(cleaned)
    except Exception:
        m = re.search(r"\{.*\}", cleaned, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
    return data if isinstance(data, dict) else None


def _normalize_review(card_id: str, data: dict[str, Any]) -> dict[str, Any]:
    verdict = str(data.get("verdict") or "ambiguous").strip().lower()
    if verdict not in {"ok", "issue", "ambiguous"}:
        verdict = "ambiguous"
    issues_in = data.get("issues") if isinstance(data.get("issues"), list) else []
    issues: list[dict[str, Any]] = []
    for it in issues_in:
        if not isinstance(it, dict):
            continue
        problem = str(it.get("problem") or it.get("detail") or "").strip()
        if not problem:
            continue
        sev = str(it.get("severity") or "high").strip().lower()
        if sev not in {"critical", "high", "medium", "low"}:
            sev = "high"
        issues.append(
            {
                "timing": str(it.get("timing") or "")[:40] or None,
                "problem": problem[:240],
                "expected": str(it.get("expected") or "")[:160] or None,
                "actual": str(it.get("actual") or "")[:160] or None,
                "severity": sev,
            }
        )
    if verdict == "ok" and issues:
        verdict = "issue"
    if verdict == "issue" and not issues:
        verdict = "ambiguous"
    return {
        "card_id": card_id,
        "base_id": _base_card_id(card_id),
        "verdict": verdict,
        "issues": issues,
        "notes": str(data.get("notes") or "")[:240] or None,
    }


def build_prompt(card_id: str, info: dict[str, Any], abilities: list[dict[str, Any]]) -> str:
    blob = effect_blob(info)
    digest = _abilities_digest(abilities)
    kws = detect_keywords(info)
    return (
        "Compare OPTCG paper text to compiled battle abilities.\n"
        "Return JSON ONLY:\n"
        '{"verdict":"ok|issue|ambiguous","issues":[{"timing":"on_play|...|null",'
        '"problem":"中文短句说明纸面与编译的具体差异","expected":"纸面应有",'
        '"actual":"库里实际","severity":"critical|high|medium|low"}],"notes":""}\n'
        "Rules:\n"
        "- ok = runnable abilities faithfully cover paper battle effects (keywords OK).\n"
        "- issue = wrong timing/target/amount/gate/missing clause/grant-vs-self keyword error.\n"
        "- ambiguous = text too unclear OR engine cannot express it; still list best-guess issues.\n"
        "- Ignore deck-construction-only lines. Ignore reminder text for Blocker/Rush if keyword present.\n"
        "- Ownership: 「自己的」=own only; 「對手的」=opponent only; if paper omits ownership on "
        "targets OR on 費用/咚‼/生命/場上 conditions, either side is correct "
        "(require_field_* / require_either_* / any_*). Do NOT flag bilateral encoding as wrong "
        "and do NOT demand own-only when paper has no 自己的/對手的.\n"
        "- Be specific like a human debug note (e.g. 「攻击时缺 DON×1 门槛」「KO 目标写成己方」).\n"
        f"Card: {card_id} {info.get('name') or ''} / {info.get('name_en') or ''}\n"
        f"Detected keywords: {kws}\n"
        f"Effect text:\n{blob[:3500]}\n"
        f"Compiled abilities JSON:\n{json.dumps(digest, ensure_ascii=False)}\n"
    )


def load_catalog() -> dict[str, dict]:
    path = ROOT / "index" / "cards_by_id.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def iter_base_ids(catalog: dict[str, dict]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for cid in sorted(catalog.keys()):
        base = _base_card_id(cid)
        if base in seen:
            continue
        if base in catalog:
            seen.add(base)
            out.append(base)
        else:
            seen.add(base)
            out.append(cid)
    return out


def load_state() -> dict[str, Any]:
    if not OUT_PATH.is_file():
        return {"version": 1, "cards": {}}
    try:
        data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "cards": {}}
    if not isinstance(data, dict):
        return {"version": 1, "cards": {}}
    cards = data.get("cards")
    if not isinstance(cards, dict):
        data["cards"] = {}
    return data


def save_state(state: dict[str, Any]) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUT_PATH)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LLM semantic review of card effects")
    parser.add_argument("--limit", type=int, default=0, help="Max cards to newly review this run")
    parser.add_argument("--sleep", type=float, default=0.2, help="Sleep between API calls")
    parser.add_argument("--resume", action="store_true", help="Skip cards already in review file")
    parser.add_argument("--force", action="store_true", help="Re-review even if present")
    parser.add_argument("--ids", type=str, default="", help="Comma-separated card ids")
    parser.add_argument("--ids-file", type=str, default="", help="File with one card id per line")
    parser.add_argument(
        "--only-verdict",
        type=str,
        default="",
        help="Only (re)review cards whose current saved verdict matches (e.g. issue)",
    )
    parser.add_argument("--progress-every", type=int, default=25)
    args = parser.parse_args(argv)

    ask = _make_asker()
    if ask is None:
        print("ERROR: DeepSeek asker unavailable (DEEPSEEK_API_KEY / openai).", file=sys.stderr)
        return 2

    reload_effect_library(force=True)
    catalog = load_catalog()
    state = load_state()
    cards_out: dict[str, Any] = state.setdefault("cards", {})

    if args.ids or args.ids_file:
        targets = []
        raw_ids: list[str] = []
        if args.ids:
            raw_ids.extend(str(args.ids).split(","))
        if args.ids_file:
            p = Path(args.ids_file)
            if p.exists():
                raw_ids.extend(p.read_text(encoding="utf-8").splitlines())
        for raw in raw_ids:
            cid = raw.strip().upper()
            if cid.startswith("#") or not cid:
                continue
            if cid in catalog:
                targets.append(cid)
    else:
        targets = [
            cid
            for cid in iter_base_ids(catalog)
            if has_meaningful_effect_text(catalog.get(cid) or {})
        ]

    only_verdict = str(args.only_verdict or "").strip().lower()
    pending: list[str] = []
    for cid in targets:
        if only_verdict:
            prev = str((cards_out.get(cid) or {}).get("verdict") or "").strip().lower()
            if prev != only_verdict:
                continue
            pending.append(cid)
            continue
        if args.force:
            pending.append(cid)
            continue
        if cid in cards_out and not args.force:
            continue
        pending.append(cid)

    if args.limit and args.limit > 0:
        pending = pending[: int(args.limit)]

    print(
        json.dumps(
            {
                "targets": len(targets),
                "pending": len(pending),
                "already": len(cards_out),
                "out": str(OUT_PATH),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    ok = issue = amb = err = 0
    t0 = time.time()
    for i, cid in enumerate(pending, 1):
        info = catalog.get(cid) or {}
        abilities = get_abilities(cid)
        prompt = build_prompt(cid, info, abilities)
        try:
            raw = ask(prompt)
            parsed = _parse_json_payload(raw)
            if not parsed:
                raise ValueError("non-json response")
            review = _normalize_review(cid, parsed)
        except Exception as exc:
            review = {
                "card_id": cid,
                "base_id": _base_card_id(cid),
                "verdict": "ambiguous",
                "issues": [
                    {
                        "timing": None,
                        "problem": f"语义复核调用失败: {type(exc).__name__}",
                        "expected": None,
                        "actual": None,
                        "severity": "medium",
                    }
                ],
                "notes": str(exc)[:200],
                "error": True,
            }
            err += 1

        review["name"] = info.get("name") or info.get("name_en") or cid
        review["reviewed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        cards_out[cid] = review
        v = review.get("verdict")
        if v == "ok":
            ok += 1
        elif v == "issue":
            issue += 1
        else:
            amb += 1

        if i % max(1, int(args.progress_every)) == 0 or i == len(pending):
            state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            state["totals"] = {
                "reviewed": len(cards_out),
                "ok": sum(1 for x in cards_out.values() if x.get("verdict") == "ok"),
                "issue": sum(1 for x in cards_out.values() if x.get("verdict") == "issue"),
                "ambiguous": sum(1 for x in cards_out.values() if x.get("verdict") == "ambiguous"),
            }
            save_state(state)
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(pending) - i) / rate if rate > 0 else 0
            print(
                f"[{i}/{len(pending)}] ok={ok} issue={issue} amb={amb} err={err} "
                f"rate={rate:.2f}/s eta={eta/60:.1f}m last={cid}:{v}",
                flush=True,
            )

        if args.sleep > 0:
            time.sleep(float(args.sleep))

    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["totals"] = {
        "reviewed": len(cards_out),
        "ok": sum(1 for x in cards_out.values() if x.get("verdict") == "ok"),
        "issue": sum(1 for x in cards_out.values() if x.get("verdict") == "issue"),
        "ambiguous": sum(1 for x in cards_out.values() if x.get("verdict") == "ambiguous"),
    }
    save_state(state)
    print(json.dumps({"done": True, "totals": state["totals"], "out": str(OUT_PATH)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
