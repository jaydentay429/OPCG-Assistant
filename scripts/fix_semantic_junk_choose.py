#!/usr/bin/env python3
"""Replace junk empty choose_target (Blocker / buff / deny_attack).

Writes library + overrides.
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

from battle.effect_library import get_card_entry, library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability, normalize_card_entry  # noqa: E402
from battle.effects import _enrich_ops_with_target_filters, _parse_ko_op, effect_blob  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "junk_choose_fixed_ids.txt"

AMT_RE = re.compile(
    r"(?:gains?|give|gets?|力量值)\s*([+\-−－＋]\s*\d{3,5})|"
    r"([+\-−－＋]\s*\d{3,5})\s*(?:power|力量)",
    re.I,
)
LEADER_OR_CHAR_RE = re.compile(
    r"Leader or Character|領航卡或角色卡|领航卡或角色卡",
    re.I,
)


def _parse_amt(raw: str) -> int | None:
    s = (raw or "").replace("−", "-").replace("－", "-").replace("＋", "+").strip()
    s = re.sub(r"[^\d+\-]", "", s)
    if not s or s in {"+", "-"}:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    semantic = json.loads(SEM.read_text(encoding="utf-8")) if SEM.exists() else {"cards": {}}
    lib_path, ovr_path = library_paths()
    raw = json.loads(lib_path.read_text(encoding="utf-8"))
    cards = raw.get("cards") or raw
    ovr_raw = json.loads(ovr_path.read_text(encoding="utf-8")) if ovr_path.is_file() else {"cards": {}}
    overrides = ovr_raw.get("cards") if isinstance(ovr_raw.get("cards"), dict) else {}

    stats = {"blocker": 0, "buff": 0, "deny_attack": 0, "ko": 0, "dropped": 0, "cards_touched": 0}
    touched: list[str] = []
    reload_effect_library(force=True)

    for cid, rev in (semantic.get("cards") or {}).items():
        if rev.get("verdict") != "issue":
            continue
        merged = get_card_entry(cid)
        abilities = [dict(a) for a in (merged.get("abilities") or []) if isinstance(a, dict)]
        if not abilities:
            continue
        blob = effect_blob(catalog.get(cid) or {})
        changed = False
        new_abs: list[dict] = []

        for ability in abilities:
            summary = str(ability.get("summary") or "").strip()
            scope = summary or blob
            ops = [dict(o) for o in (ability.get("ops") or [])]
            rebuilt: list[dict] = []

            is_blocker_ability = bool(
                re.search(
                    r"^(?:Blocker|【Blocker】|【阻擋者】|【阻挡者】)|"
                    r"rest this (?:card|Character) to make it the new target|"
                    r"rest this card to become the new (?:target|attack target)|"
                    r"置為休息狀態.{0,20}攻擊的對象|置为休息状态.{0,20}攻击的对象",
                    scope,
                    re.I,
                )
            )

            if is_blocker_ability and any(o.get("op") == "choose_target" and not o.get("then_op") for o in ops):
                ops = [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self"}]
                stats["blocker"] += 1
                changed = True
            else:
                for o in ops:
                    if o.get("op") != "choose_target" or o.get("then_op"):
                        rebuilt.append(o)
                        continue

                    if re.search(
                        r"cannot attack|無法進行攻擊|无法进行攻击|不能攻擊|不能攻击",
                        scope,
                        re.I,
                    ):
                        tk = (
                            "opponent_leader_or_character"
                            if LEADER_OR_CHAR_RE.search(scope)
                            else "opponent_character"
                        )
                        rebuilt.append(
                            {
                                "op": "deny_attack",
                                "target_kind": tk,
                                "optional": True,
                                "duration": "turn",
                            }
                        )
                        stats["deny_attack"] += 1
                        changed = True
                        continue

                    m = AMT_RE.search(scope)
                    if m and not re.search(r"give\s+\d+\s+active DON|附加.{0,12}咚", scope, re.I):
                        amt = _parse_amt(next(g for g in m.groups() if g))
                        if amt is not None:
                            if amt < 0:
                                tk = (
                                    "opponent_leader_or_character"
                                    if LEADER_OR_CHAR_RE.search(scope)
                                    else "opponent_character"
                                )
                            else:
                                tk = (
                                    "own_leader_or_character"
                                    if LEADER_OR_CHAR_RE.search(scope)
                                    else "own_character"
                                    if re.search(r"Character|角色", scope, re.I)
                                    else "leader"
                                )
                            rebuilt.append(
                                {"op": "buff", "amount": amt, "target_kind": tk, "optional": True}
                            )
                            stats["buff"] += 1
                            changed = True
                            continue

                    ko = _parse_ko_op(scope)
                    if ko and re.search(r"K\.?O|KO", scope, re.I):
                        rebuilt.append(ko)
                        stats["ko"] += 1
                        changed = True
                        continue

                    # orphan empty choose with other concrete ops → drop
                    if any(x.get("op") not in {"choose_target", "unsupported"} for x in ops):
                        stats["dropped"] += 1
                        changed = True
                        continue

                    rebuilt.append(o)
                ops = rebuilt

            ops = _enrich_ops_with_target_filters(ops, scope)
            ability["ops"] = ops
            na = normalize_ability(ability)
            if na:
                new_abs.append(na)

        if not changed:
            continue
        fixed = normalize_card_entry(cid, {"version": 1, "abilities": new_abs})
        cards[cid] = fixed
        overrides[cid] = fixed
        stats["cards_touched"] += 1
        touched.append(cid)

    print(json.dumps(stats, ensure_ascii=False), flush=True)
    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    OUT_IDS.write_text("\n".join(touched) + ("\n" if touched else ""), encoding="utf-8")
    print(f"Wrote ids {OUT_IDS} ({len(touched)})", flush=True)
    if args.dry_run:
        return 0

    payload = {"version": 1, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cards": cards}
    tmp = lib_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(lib_path)

    ovr_payload = dict(ovr_raw) if isinstance(ovr_raw, dict) else {}
    ovr_payload["cards"] = overrides
    ovr_payload["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp_o = ovr_path.with_suffix(".json.tmp")
    tmp_o.write_text(json.dumps(ovr_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp_o.replace(ovr_path)
    reload_effect_library(force=True)
    print(f"Wrote {lib_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
