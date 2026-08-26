#!/usr/bin/env python3
"""Dump why AI self-play games get stuck (local only)."""

from __future__ import annotations

import json
import random
import sys
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from battle.ai import _acting_seat, ai_must_act, pick_ai_action, step_ai_once  # noqa: E402
from battle.engine import legal_actions, start_match  # noqa: E402

POOL_PATH = ROOT / "meta" / "ai_eval_pool.json"
CARDS_PATH = ROOT / "index" / "cards_by_id.json"
_MAX_STEPS = 800


def _catalog_fn(cards: dict[str, Any]):
    def catalog(cid: str) -> dict[str, Any]:
        row = cards.get(cid) or cards.get(str(cid))
        if isinstance(row, dict):
            return row
        return {"card_id": cid, "id": cid, "name": cid, "cost": 0, "power": 0}

    return catalog


def _spec(deck: dict[str, Any], *, seat: int) -> dict[str, Any]:
    return {
        "user_id": f"ai{seat}",
        "username": f"AI-{deck.get('leader_card_id')}",
        "is_ai": True,
        "leader_card_id": deck["leader_card_id"],
        "cards": dict(deck["cards"]),
    }


def _pending_snap(state) -> dict[str, Any]:
    pc = state.pending_choice
    ps = state.pending_search
    pe = state.pending_effect
    pt = state.pending_trigger
    pr = getattr(state, "pending_replace", None)
    return {
        "phase": state.phase,
        "end_phase_step": getattr(state, "end_phase_step", None),
        "turn": state.turn_number,
        "turn_seat": state.turn_seat,
        "status": state.status,
        "attack": None
        if not state.attack
        else {
            "attacker": state.attack.attacker_iid,
            "target": state.attack.target_iid,
            "combat_entered": bool(state.attack.combat_entered),
            "opp_watchers": getattr(state.attack, "opp_attack_watchers_done", None),
        },
        "choice": None
        if not pc
        else {
            "seat": pc.seat,
            "kind": pc.target_kind,
            "purpose": pc.purpose,
            "optional": pc.optional,
            "n_opts": len(pc.options or []),
            "opts": list(pc.options or [])[:8],
            "summary": (pc.summary or "")[:80],
            "then_op": (pc.then_op or {}).get("op") if isinstance(pc.then_op, dict) else None,
        },
        "search": None
        if not ps
        else {
            "seat": ps.seat,
            "phase": ps.phase,
            "max_add": ps.max_add,
            "n_rev": len(ps.revealed or []),
            "eligible": list(ps.eligible or [])[:8],
            "selected": list(ps.selected or []),
            "summary": (ps.summary or "")[:80],
        },
        "effect": None
        if not pe
        else {
            "seat": pe.seat,
            "summary": (pe.summary or "")[:80],
            "ops": [o.get("op") for o in (pe.ops or [])[:6]],
            "uncertain": pe.uncertain,
        },
        "trigger": None
        if not pt
        else {"seat": pt.seat, "n_ops": len(pt.ops or [])},
        "replace": None
        if not pr
        else {"owner": pr.owner_seat, "cost": (pr.op or {}).get("cost"), "kind": pr.kind},
        "board_resume": bool(getattr(state, "board_timing_resume", None)),
        "trigger_resume": bool(getattr(state, "trigger_resume", None)),
    }


def diagnose_one(seed: int, d0: dict, d1: dict, catalog) -> dict[str, Any]:

    rng = random.Random(seed)
    state = start_match(
        f"diag-{seed}",
        _spec(d0, seat=0),
        _spec(d1, seat=1),
        catalog,
        rng=rng,
    )
    steps = 0
    idle = 0
    last_false_reason = ""
    try:
        while state.status == "playing" and steps < _MAX_STEPS:
            advanced = step_ai_once(state, catalog, ask_llm=None)
            steps += 1
            if not advanced:
                idle += 1
                seat = _acting_seat(state)
                acts = legal_actions(state, seat, catalog) if seat is not None else []
                pick = pick_ai_action(state, seat, catalog) if seat is not None else None
                last_false_reason = (
                    f"must={ai_must_act(state)} acting={seat} n_legal={len(acts)} "
                    f"pick={None if pick is None else pick.get('type')} "
                    f"types={[a.get('type') for a in acts[:12]]}"
                )
                if idle >= 3:
                    snap = _pending_snap(state)
                    logs = [e.get("key") for e in (state.log or [])[-12:]]
                    return {
                        "kind": "idle",
                        "seed": seed,
                        "leaders": [d0.get("leader_card_id"), d1.get("leader_card_id")],
                        "names": [d0.get("name"), d1.get("name")],
                        "steps": steps,
                        "reason": last_false_reason,
                        "snap": snap,
                        "logs": logs,
                    }
                continue
            idle = 0
        if state.status == "playing":
            return {
                "kind": "max_steps",
                "seed": seed,
                "leaders": [d0.get("leader_card_id"), d1.get("leader_card_id")],
                "names": [d0.get("name"), d1.get("name")],
                "steps": steps,
                "reason": last_false_reason,
                "snap": _pending_snap(state),
                "logs": [e.get("key") for e in (state.log or [])[-12:]],
            }
        return {"kind": "ok", "seed": seed, "winner": state.winner_seat, "turns": state.turn_number, "steps": steps}
    except Exception as exc:  # noqa: BLE001
        return {
            "kind": "error",
            "seed": seed,
            "leaders": [d0.get("leader_card_id"), d1.get("leader_card_id")],
            "error": f"{type(exc).__name__}: {exc}",
            "tb": traceback.format_exc(limit=6),
            "snap": _pending_snap(state) if "state" in locals() else None,
        }


def main() -> None:
    decks = json.loads(POOL_PATH.read_text(encoding="utf-8"))["decks"]
    cards = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    catalog = _catalog_fn(cards)
    seed0 = 20260826
    jobs: list[tuple[int, dict, dict]] = []
    g = 0
    # Mirrors + a few cross pairs (same schedule start as eval).
    for deck in decks:
        for _ in range(4):
            jobs.append((seed0 + g, deck, deck))
            g += 1
    for i, j in [(0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (1, 8), (3, 7)]:
        jobs.append((seed0 + g, decks[i], decks[j]))
        g += 1
        jobs.append((seed0 + g, decks[j], decks[i]))
        g += 1

    kinds: Counter[str] = Counter()
    stuck_snaps: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []
    for i, (seed, d0, d1) in enumerate(jobs, 1):
        r = diagnose_one(seed, d0, d1, catalog)
        kinds[r["kind"]] += 1
        if r["kind"] != "ok":
            snap = r.get("snap") or {}
            key = (
                f"{r['kind']}|{snap.get('phase')}|ch={bool(snap.get('choice'))}"
                f"|se={bool(snap.get('search'))}|ef={bool(snap.get('effect'))}"
                f"|tr={bool(snap.get('trigger'))}|re={bool(snap.get('replace'))}"
            )
            stuck_snaps[key] += 1
            if len(samples) < 12:
                samples.append(r)
        if i % 10 == 0 or i == len(jobs):
            print(f"  … {i}/{len(jobs)}  {dict(kinds)}", flush=True)

    print("\n======== stuck diagnose ========")
    print("kinds:", dict(kinds))
    print("stuck buckets:")
    for k, n in stuck_snaps.most_common():
        print(f"  {n:3d}  {k}")
    print("\n--- samples ---")
    for r in samples:
        print(json.dumps({k: r[k] for k in r if k != "tb"}, ensure_ascii=False, indent=2)[:1800])
        print("---")


if __name__ == "__main__":
    main()
