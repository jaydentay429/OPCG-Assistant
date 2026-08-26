#!/usr/bin/env python3
"""LLM-repair cards with semantic issues using diagnosis as repair instructions.

Usage:
  .venv/bin/python scripts/fix_semantic_batch.py --limit 40 --checkpoint-every 5
  .venv/bin/python scripts/fix_semantic_batch.py --ids-file meta/logs/semantic_issue_ids.txt
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

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import (  # noqa: E402
    ability_is_runnable,
    normalize_ability,
    normalize_card_entry,
    sanitize_ops_list,
)
from battle.effects import effect_blob, get_deepseek_asker  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"


def _base(cid: str) -> str:
    return re.sub(r"-(?:P|R)\d+$", "", cid)


def _issue_ids(limit: int = 0) -> list[str]:
    data = json.loads(SEM.read_text(encoding="utf-8"))
    ids = []
    for cid, rev in (data.get("cards") or {}).items():
        if rev.get("verdict") != "issue":
            continue
        ids.append(cid)
    ids.sort()
    if limit > 0:
        ids = ids[:limit]
    return ids


def _repair_prompt(cid: str, info: dict, abilities: list, issues: list) -> str:
    diag = []
    for iss in issues:
        if not isinstance(iss, dict):
            continue
        diag.append(
            {
                "timing": iss.get("timing"),
                "severity": iss.get("severity"),
                "problem": iss.get("problem"),
                "expected": iss.get("expected"),
                "actual": iss.get("actual"),
            }
        )
    return (
        "You are fixing an OPTCG effect compilation to match paper text EXACTLY.\n"
        "Return JSON ONLY: "
        '{"abilities":[{"timing":"...","summary":"...","ops":[...],'
        '"status":"compiled","confidence":0.0,"once":false,"require_leader_trait":null}]}\n'
        "Rules:\n"
        "- Fix EVERY listed diagnosis. Do not leave known wrong ops.\n"
        "- buff/buff_self/buff_all_own MUST have nonzero amount when paper has +/- power.\n"
        "- Play from trash → play_from_hand with from_zone=trash.\n"
        "- Prefer runnable ops. Use unsupported only if truly inexpressible.\n"
        "- Keep timings that exist on the paper; remove invented timings.\n"
        "- DON!!−N cost → return_don count N (often as_cost).\n"
        "- Optional costs → optional:true / as_cost:true as appropriate.\n"
        f"Card: {cid} {info.get('name_en') or info.get('name')}\n"
        f"Paper effect:\n{effect_blob(info)}\n"
        f"Current abilities JSON:\n{json.dumps(abilities, ensure_ascii=False)}\n"
        f"Diagnoses to fix:\n{json.dumps(diag, ensure_ascii=False)}\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--sleep", type=float, default=0.12)
    ap.add_argument("--checkpoint-every", type=int, default=5)
    ap.add_argument("--ids", type=str, default="")
    ap.add_argument("--ids-file", type=str, default="")
    ap.add_argument("--severity", type=str, default="", help="Only cards that have an issue with this severity")
    args = ap.parse_args(argv)

    ask = get_deepseek_asker()
    if ask is None:
        print("ERROR: DeepSeek unavailable", file=sys.stderr)
        return 2

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    semantic = json.loads(SEM.read_text(encoding="utf-8"))
    lib_path, _ = library_paths()
    raw = json.loads(lib_path.read_text(encoding="utf-8"))
    cards = raw.setdefault("cards", {})

    if args.ids:
        targets = [x.strip().upper() for x in args.ids.split(",") if x.strip()]
    elif args.ids_file:
        targets = [
            ln.strip().upper()
            for ln in Path(args.ids_file).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
    else:
        targets = _issue_ids(0)

    sev = str(args.severity or "").strip().lower()
    filtered = []
    for cid in targets:
        rev = (semantic.get("cards") or {}).get(cid) or {}
        if rev.get("verdict") != "issue":
            continue
        issues = [i for i in (rev.get("issues") or []) if isinstance(i, dict)]
        if sev and not any(str(i.get("severity") or "").lower() == sev for i in issues):
            continue
        filtered.append(cid)
    # Prefer unique bases, one printing each
    seen = set()
    bases = []
    for cid in filtered:
        b = _base(cid)
        if b in seen:
            continue
        seen.add(b)
        bases.append(cid)
    if args.limit > 0:
        bases = bases[: int(args.limit)]

    print(f"Selected {len(bases)} unique bases", flush=True)

    def flush() -> None:
        payload = {
            "version": 1,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "cards": cards,
        }
        tmp = lib_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(lib_path)

    improved = 0
    errors = 0
    changed_ids: list[str] = []
    for i, cid in enumerate(bases):
        info = catalog.get(cid) or {}
        # Prefer printing with text
        if not effect_blob(info).strip():
            for alt in sorted(k for k in catalog if _base(k) == _base(cid)):
                if effect_blob(catalog.get(alt) or {}).strip():
                    cid = alt
                    info = catalog[alt]
                    break
        rev = (semantic.get("cards") or {}).get(cid) or {}
        # fall back to base review
        if rev.get("verdict") != "issue":
            rev = (semantic.get("cards") or {}).get(_base(cid)) or rev
        issues = [x for x in (rev.get("issues") or []) if isinstance(x, dict)]
        prev = list((cards.get(cid) or {}).get("abilities") or [])
        before = sum(1 for a in prev if ability_is_runnable(a))
        try:
            raw_txt = ask(_repair_prompt(cid, info, prev, issues))
            cleaned = raw_txt.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S)
            data = json.loads(cleaned)
            abs_in = data.get("abilities") if isinstance(data, dict) else None
            if not isinstance(abs_in, list):
                raise ValueError("no abilities")
            new_abs = []
            for a in abs_in:
                if not isinstance(a, dict):
                    continue
                if a.get("ops"):
                    a["ops"] = sanitize_ops_list(a["ops"])
                na = normalize_ability(a)
                if na:
                    new_abs.append(na)
            if not new_abs:
                raise ValueError("empty after normalize")
            entry = normalize_card_entry(cid, {"version": 1, "abilities": new_abs})
            after = sum(1 for a in entry["abilities"] if ability_is_runnable(a))
            # Never accept a strictly worse compile (lose runnable timings).
            if after < before:
                print(
                    f"[{i+1}/{len(bases)}] {cid} REJECT runnable {before}->{after} (keep previous)",
                    flush=True,
                )
                continue
            cards[cid] = entry
            # propagate to variants of same base
            for variant in sorted(k for k in catalog if _base(k) == _base(cid)):
                if variant == cid:
                    continue
                cards[variant] = normalize_card_entry(variant, {"version": 1, "abilities": entry["abilities"]})
            if entry["abilities"] != prev:
                improved += 1
                changed_ids.append(cid)
            print(
                f"[{i+1}/{len(bases)}] {cid} runnable {before}->{after} "
                f"timings={[a.get('timing') for a in entry['abilities']]}",
                flush=True,
            )
        except Exception as exc:
            errors += 1
            print(f"[{i+1}/{len(bases)}] {cid} ERROR {type(exc).__name__}: {exc}", flush=True)
        if args.sleep > 0:
            time.sleep(float(args.sleep))
        if args.checkpoint_every and (i + 1) % int(args.checkpoint_every) == 0:
            flush()
            print(f"checkpoint saved after {i+1}", flush=True)

    flush()
    reload_effect_library(force=True)
    changed_path = ROOT / "meta" / "logs" / "semantic_fixed_ids.txt"
    changed_path.parent.mkdir(parents=True, exist_ok=True)
    # unique preserve order
    seen: set[str] = set()
    ordered = []
    for cid in changed_ids:
        if cid in seen:
            continue
        seen.add(cid)
        ordered.append(cid)
    changed_path.write_text("\n".join(ordered) + ("\n" if ordered else ""), encoding="utf-8")
    print(
        json.dumps(
            {
                "targets": len(bases),
                "improved": improved,
                "errors": errors,
                "changed_ids": len(ordered),
                "changed_ids_file": str(changed_path),
                "library": str(lib_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
