#!/usr/bin/env python3
"""Merge gap/audit/fidelity/semantic/smoke reports into one problem queue.

Usage:
  .venv/bin/python scripts/build_effect_problem_queue.py

Writes:
  meta/effect_problem_queue.json
  meta/effect_problem_queue.md
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effects import effect_blob  # noqa: E402

META = ROOT / "meta"
SEV_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def _base(cid: str) -> str:
    return re.sub(r"-(?:P|R)\d+$", "", str(cid or ""))


def _load(name: str) -> dict[str, Any] | list[Any] | None:
    path = META / name
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _ensure_item(bucket: dict[str, dict[str, Any]], cid: str, *, name: str = "") -> dict[str, Any]:
    base = _base(cid)
    key = base or cid
    item = bucket.get(key)
    if item is None:
        item = {
            "id": key,
            "name": name or key,
            "status": "open",
            "severity": "medium",
            "reasons": [],
            "diagnosis": [],
            "timings": [],
            "sources": [],
            "effect_preview": "",
            "notes": "",
        }
        bucket[key] = item
    if name and (not item.get("name") or item["name"] == key):
        item["name"] = name
    return item


def _add_reason(item: dict[str, Any], reason: str) -> None:
    if reason and reason not in item["reasons"]:
        item["reasons"].append(reason)


def _add_source(item: dict[str, Any], source: str) -> None:
    if source and source not in item["sources"]:
        item["sources"].append(source)


def _add_diagnosis(item: dict[str, Any], text: str, *, severity: str = "high", timing: str | None = None) -> None:
    text = str(text or "").strip()
    if not text:
        return
    entry = {"problem": text[:240], "severity": severity, "timing": timing}
    # de-dupe by problem text
    for old in item["diagnosis"]:
        if old.get("problem") == entry["problem"]:
            return
    item["diagnosis"].append(entry)
    if SEV_RANK.get(severity, 0) > SEV_RANK.get(str(item.get("severity") or ""), 0):
        item["severity"] = severity


def _add_timing(item: dict[str, Any], timing: str | None) -> None:
    t = str(timing or "").strip()
    if t and t not in item["timings"]:
        item["timings"].append(t)


def main() -> int:
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    bucket: dict[str, dict[str, Any]] = {}

    # Preserve previous status/notes if present
    prev = _load("effect_problem_queue.json")
    prev_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(prev, dict):
        for it in prev.get("items") or []:
            if isinstance(it, dict) and it.get("id"):
                prev_by_id[str(it["id"])] = it

    gap = _load("effect_gap_tracker.json")
    if isinstance(gap, dict):
        for row in gap.get("top_gaps") or []:
            if not isinstance(row, dict):
                continue
            cid = str(row.get("id") or "")
            if not cid:
                continue
            item = _ensure_item(bucket, cid, name=str(row.get("name") or ""))
            timing = str(row.get("timing") or "")
            reason = str(row.get("reason") or "unsupported")
            _add_reason(item, f"unsupported:{timing or '?'}")
            _add_source(item, "gap_tracker")
            _add_timing(item, timing)
            _add_diagnosis(
                item,
                f"不可运行能力 ({timing or '?'}): {reason}",
                severity="high",
                timing=timing or None,
            )
            if not item["effect_preview"]:
                item["effect_preview"] = str(row.get("effect") or "")[:160]
        for row in gap.get("empty_samples") or []:
            if not isinstance(row, dict):
                continue
            cid = str(row.get("id") or "")
            if not cid:
                continue
            item = _ensure_item(bucket, cid, name=str(row.get("name") or ""))
            _add_reason(item, "empty_with_text")
            _add_source(item, "gap_tracker")
            _add_diagnosis(item, "有正文效果但库中无能力", severity="critical")
            item["effect_preview"] = str(row.get("effect") or "")[:160]
            item["severity"] = "critical"

    # Full gaps list may live only in md; also pull empty_with_text from compile report if needed
    compile_rep = _load("effect_compile_report.json")
    # Prefer scanning library for empty/unsupported if gap file only has samples
    if isinstance(gap, dict) and int((gap.get("totals") or {}).get("empty_with_text") or 0) > len(
        gap.get("empty_samples") or []
    ):
        lib_path = ROOT / "index" / "card_effects.json"
        if lib_path.is_file():
            raw = json.loads(lib_path.read_text(encoding="utf-8"))
            lib = raw["cards"] if isinstance(raw.get("cards"), dict) else raw
            from battle.effect_schema import ability_is_runnable
            from battle.effects import has_meaningful_effect_text

            for cid, info in catalog.items():
                if not isinstance(info, dict):
                    continue
                if not has_meaningful_effect_text(info):
                    continue
                abs_ = (lib.get(cid) or {}).get("abilities") or []
                if not abs_:
                    item = _ensure_item(
                        bucket, cid, name=str(info.get("name") or info.get("name_en") or cid)
                    )
                    _add_reason(item, "empty_with_text")
                    _add_source(item, "library_scan")
                    _add_diagnosis(item, "有正文效果但库中无能力", severity="critical")
                    item["effect_preview"] = effect_blob(info)[:160]
                    item["severity"] = "critical"
                    continue
                for a in abs_:
                    if ability_is_runnable(a):
                        continue
                    timing = str(a.get("timing") or "?")
                    reason = "unsupported"
                    for o in a.get("ops") or []:
                        if isinstance(o, dict) and o.get("op") == "unsupported":
                            reason = str(o.get("reason") or "unsupported")
                            break
                    item = _ensure_item(
                        bucket, cid, name=str(info.get("name") or info.get("name_en") or cid)
                    )
                    _add_reason(item, f"unsupported:{timing}")
                    _add_source(item, "library_scan")
                    _add_timing(item, timing)
                    _add_diagnosis(
                        item,
                        f"不可运行能力 ({timing}): {reason}",
                        severity="high",
                        timing=timing,
                    )
                    if not item["effect_preview"]:
                        item["effect_preview"] = effect_blob(info)[:160]

    audit = _load("effect_audit_report.json")
    if isinstance(audit, dict):
        for f in audit.get("findings") or []:
            if not isinstance(f, dict):
                continue
            cid = str(f.get("id") or f.get("card_id") or "")
            if not cid:
                continue
            item = _ensure_item(bucket, cid, name=str(f.get("name") or ""))
            cat = str(f.get("category") or "audit")
            _add_reason(item, f"audit:{cat}")
            _add_source(item, "audit")
            _add_timing(item, str(f.get("timing") or "") or None)
            sev = "high" if cat in {"ko_own_as_opp", "look_at_as_draw", "empty_with_text"} else "medium"
            _add_diagnosis(item, str(f.get("detail") or cat), severity=sev, timing=f.get("timing"))

    fidelity = _load("effect_fidelity_full_report.json")
    if isinstance(fidelity, dict):
        for f in fidelity.get("findings") or []:
            if not isinstance(f, dict):
                continue
            cid = str(f.get("card_id") or f.get("base_id") or "")
            if not cid:
                continue
            item = _ensure_item(bucket, cid)
            cat = str(f.get("category") or "fidelity")
            sev = str(f.get("severity") or "medium")
            _add_reason(item, f"fidelity:{cat}")
            _add_source(item, "fidelity")
            _add_timing(item, str(f.get("timing") or "") or None)
            _add_diagnosis(item, str(f.get("detail") or cat), severity=sev, timing=f.get("timing"))

    semantic = _load("effect_semantic_review.json")
    if isinstance(semantic, dict):
        for cid, rev in (semantic.get("cards") or {}).items():
            if not isinstance(rev, dict):
                continue
            verdict = str(rev.get("verdict") or "")
            if verdict == "ok":
                continue
            item = _ensure_item(bucket, str(cid), name=str(rev.get("name") or ""))
            _add_reason(item, f"semantic:{verdict or 'issue'}")
            _add_source(item, "semantic_review")
            if verdict == "ambiguous":
                item["status"] = "ambiguous" if item.get("status") == "open" else item["status"]
            for iss in rev.get("issues") or []:
                if not isinstance(iss, dict):
                    continue
                _add_diagnosis(
                    item,
                    str(iss.get("problem") or ""),
                    severity=str(iss.get("severity") or "high"),
                    timing=iss.get("timing"),
                )
                _add_timing(item, iss.get("timing"))
            if not item["effect_preview"]:
                info = catalog.get(_base(str(cid))) or catalog.get(str(cid)) or {}
                if isinstance(info, dict):
                    item["effect_preview"] = effect_blob(info)[:160]

    smoke = _load("effect_runtime_smoke.json")
    if isinstance(smoke, dict):
        for e in smoke.get("errors") or []:
            if not isinstance(e, dict):
                continue
            cid = str(e.get("card_id") or "")
            if not cid:
                continue
            item = _ensure_item(bucket, cid, name=str(e.get("name") or ""))
            _add_reason(item, "runtime_error")
            _add_source(item, "runtime_smoke")
            _add_timing(item, e.get("timing"))
            _add_diagnosis(
                item,
                f"运行时报错 ({e.get('timing')}): {e.get('error')}",
                severity="critical",
                timing=e.get("timing"),
            )

    # Merge previous fixed/wontfix/notes
    for key, item in bucket.items():
        old = prev_by_id.get(key)
        if not old:
            continue
        if old.get("status") in {"fixed", "wontfix"}:
            item["status"] = old["status"]
        if old.get("notes"):
            item["notes"] = old["notes"]

    items = list(bucket.values())
    items.sort(
        key=lambda x: (
            0 if x.get("status") == "open" else 1 if x.get("status") == "ambiguous" else 2,
            -SEV_RANK.get(str(x.get("severity") or ""), 0),
            str(x.get("id") or ""),
        )
    )

    by_status: dict[str, int] = defaultdict(int)
    by_sev: dict[str, int] = defaultdict(int)
    for it in items:
        by_status[str(it.get("status") or "open")] += 1
        by_sev[str(it.get("severity") or "medium")] += 1

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "totals": {
            "items": len(items),
            "open": by_status.get("open", 0),
            "ambiguous": by_status.get("ambiguous", 0),
            "fixed": by_status.get("fixed", 0),
            "wontfix": by_status.get("wontfix", 0),
            "compile_runnable": (compile_rep or {}).get("totals", {}).get("runnable")
            if isinstance(compile_rep, dict)
            else None,
        },
        "by_severity": dict(by_sev),
        "by_status": dict(by_status),
        "items": items,
    }

    META.mkdir(parents=True, exist_ok=True)
    json_path = META / "effect_problem_queue.json"
    md_path = META / "effect_problem_queue.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Effect problem queue\n\n",
        f"Generated: `{report['generated_at']}`\n\n",
        f"- Items: **{report['totals']['items']}**\n",
        f"- Open: **{report['totals']['open']}** | Ambiguous: **{report['totals']['ambiguous']}** | "
        f"Fixed: **{report['totals']['fixed']}**\n\n",
        "## Top open / ambiguous\n\n",
        "| ID | Sev | Status | Diagnosis |\n|----|-----|--------|-----------|\n",
    ]
    shown = 0
    for it in items:
        if it.get("status") not in {"open", "ambiguous"}:
            continue
        diag = "；".join(d.get("problem") or "" for d in (it.get("diagnosis") or [])[:2])[:120]
        lines.append(
            f"| {it.get('id')} | {it.get('severity')} | {it.get('status')} | {diag.replace('|', '/')} |\n"
        )
        shown += 1
        if shown >= 120:
            break
    md_path.write_text("".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {"totals": report["totals"], "by_severity": report["by_severity"], "json": str(json_path)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
