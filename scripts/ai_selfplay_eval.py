#!/usr/bin/env python3
"""Local AI vs AI self-play eval over meta/ai_eval_pool.json (no API / no GPU)."""

from __future__ import annotations

import argparse
import json
import os
import random
import resource
import time
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POOL_PATH = ROOT / "meta" / "ai_eval_pool.json"
CARDS_PATH = ROOT / "index" / "cards_by_id.json"
BASELINE_PATH = ROOT / "meta" / "ai_eval_baseline.json"

# Soft limit so stuck matches don't hang forever.
_MAX_STEPS_PER_GAME = 1500


def _load_pool(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    decks = data.get("decks") if isinstance(data, dict) else data
    if not isinstance(decks, list) or not decks:
        raise SystemExit(f"empty pool: {path}")
    return decks


def _catalog_fn(cards: dict[str, Any]):
    def catalog(cid: str) -> dict[str, Any]:
        row = cards.get(cid) or cards.get(str(cid))
        if isinstance(row, dict):
            return row
        return {"card_id": cid, "id": cid, "name": cid, "cost": 0, "power": 0}

    return catalog


def _leader_label(catalog, leader_id: str) -> str:
    info = catalog(leader_id) or {}
    name = str(info.get("name") or info.get("name_en") or "").strip()
    return f"{leader_id} ({name})" if name else leader_id


def _spec(deck: dict[str, Any], *, seat: int) -> dict[str, Any]:
    return {
        "user_id": f"ai{seat}",
        "username": f"AI-{deck.get('leader_card_id')}",
        "is_ai": True,
        "leader_card_id": deck["leader_card_id"],
        "cards": dict(deck["cards"]),
    }


def _play_one(args: tuple[Any, ...]) -> dict[str, Any]:
    """Worker entry: (seed, deck0_json, deck1_json, cards_path_str) -> result dict."""
    seed, d0, d1, cards_path = args
    # Lazy import inside worker for process pool.
    from battle.ai import step_ai_once
    from battle.engine import start_match

    cards = json.loads(Path(cards_path).read_text(encoding="utf-8"))
    catalog = _catalog_fn(cards)
    t0 = time.perf_counter()
    action_types: Counter[str] = Counter()
    steps = 0
    error = None
    stuck = False
    try:
        rng = random.Random(seed)
        state = start_match(
            f"eval-{seed}",
            _spec(d0, seat=0),
            _spec(d1, seat=1),
            catalog,
            rng=rng,
        )
        idle = 0
        while state.status == "playing" and steps < _MAX_STEPS_PER_GAME:
            before = (state.phase, state.turn_seat, state.turn_number, state.winner_seat)
            advanced = step_ai_once(state, catalog, ask_llm=None)
            steps += 1
            if not advanced:
                idle += 1
                if idle >= 3:
                    stuck = True
                    break
                continue
            idle = 0
            # Best-effort action type from last log is hard; count phase transitions instead.
            after = (state.phase, state.turn_seat, state.turn_number, state.winner_seat)
            if after != before:
                action_types[str(state.phase)] += 1
        if state.status == "playing" and not stuck:
            stuck = steps >= _MAX_STEPS_PER_GAME
    except Exception as exc:  # noqa: BLE001 — eval must survive bad decks
        error = f"{type(exc).__name__}: {exc}"
        return {
            "ok": False,
            "error": error,
            "traceback": traceback.format_exc(limit=4),
            "seed": seed,
            "leader0": d0.get("leader_card_id"),
            "leader1": d1.get("leader_card_id"),
            "name0": d0.get("name"),
            "name1": d1.get("name"),
            "steps": steps,
            "turns": None,
            "winner_seat": None,
            "stuck": False,
            "elapsed_sec": time.perf_counter() - t0,
            "phases": dict(action_types),
        }

    return {
        "ok": error is None and not stuck and state.status != "playing",
        "error": error,
        "seed": seed,
        "leader0": d0.get("leader_card_id"),
        "leader1": d1.get("leader_card_id"),
        "name0": d0.get("name"),
        "name1": d1.get("name"),
        "steps": steps,
        "turns": getattr(state, "turn_number", None),
        "winner_seat": state.winner_seat,
        "status": state.status,
        "stuck": stuck,
        "elapsed_sec": time.perf_counter() - t0,
        "phases": dict(action_types),
    }


def _build_schedule(
    decks: list[dict[str, Any]],
    *,
    mirror_games: int,
    pair_games: int,
    max_pairs: int,
    seed: int,
) -> list[tuple[int, dict, dict]]:
    rng = random.Random(seed)
    jobs: list[tuple[int, dict, dict]] = []
    g = 0
    for deck in decks:
        for i in range(mirror_games):
            # Swap seats half the time for symmetry.
            if i % 2 == 0:
                jobs.append((seed + g, deck, deck))
            else:
                jobs.append((seed + g, deck, deck))
            g += 1

    n = len(decks)
    pairs: list[tuple[int, int]] = [(i, j) for i in range(n) for j in range(i + 1, n)]
    rng.shuffle(pairs)
    pairs = pairs[: max(0, max_pairs)]
    for i, j in pairs:
        for _ in range(pair_games):
            a, b = decks[i], decks[j]
            if rng.random() < 0.5:
                a, b = b, a
            jobs.append((seed + g, a, b))
            g += 1
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pool", type=Path, default=POOL_PATH)
    ap.add_argument("--seed", type=int, default=20260826)
    ap.add_argument("--mirror-games", type=int, default=8, help="games per deck vs itself")
    ap.add_argument("--pair-games", type=int, default=2, help="games per sampled cross pair")
    ap.add_argument("--max-pairs", type=int, default=20, help="how many unique cross pairs")
    ap.add_argument("--workers", type=int, default=max(1, min(4, (os.cpu_count() or 2) // 2)))
    ap.add_argument("--save-baseline", type=Path, default=None)
    ap.add_argument("--compare-baseline", type=Path, default=BASELINE_PATH)
    args = ap.parse_args()

    decks = _load_pool(args.pool)
    cards = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    catalog = _catalog_fn(cards)

    jobs_meta = _build_schedule(
        decks,
        mirror_games=args.mirror_games,
        pair_games=args.pair_games,
        max_pairs=args.max_pairs,
        seed=args.seed,
    )
    work = [(seed, d0, d1, str(CARDS_PATH)) for seed, d0, d1 in jobs_meta]

    print(f"pool decks: {len(decks)}")
    print(f"scheduled games: {len(work)}  workers: {args.workers}")
    for d in decks:
        print(f"  - {_leader_label(catalog, d['leader_card_id'])}  |  {d.get('name')}")

    t0 = time.perf_counter()
    ru0 = resource.getrusage(resource.RUSAGE_SELF)
    results: list[dict[str, Any]] = []

    if args.workers <= 1:
        for item in work:
            results.append(_play_one(item))
            done = len(results)
            if done % 10 == 0 or done == len(work):
                print(f"  … {done}/{len(work)}")
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(_play_one, item) for item in work]
            for i, fut in enumerate(as_completed(futs), 1):
                results.append(fut.result())
                if i % 10 == 0 or i == len(work):
                    print(f"  … {i}/{len(work)}")

    wall = time.perf_counter() - t0
    ru1 = resource.getrusage(resource.RUSAGE_SELF)
    # Children CPU is in RUSAGE_CHILDREN after process pool joins.
    ruc = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_user = (ru1.ru_utime - ru0.ru_utime) + ruc.ru_utime
    cpu_sys = (ru1.ru_stime - ru0.ru_stime) + ruc.ru_stime
    max_rss_mb = max(ru1.ru_maxrss, ruc.ru_maxrss) / (1024 * 1024 if os.uname().sysname == "Darwin" else 1024)
    # macOS ru_maxrss is bytes; Linux is KB. Detect roughly:
    if os.uname().sysname == "Darwin":
        max_rss_mb = max(ru1.ru_maxrss, ruc.ru_maxrss) / (1024 * 1024)
    else:
        max_rss_mb = max(ru1.ru_maxrss, ruc.ru_maxrss) / 1024

    finished = [r for r in results if r.get("ok")]
    stuck = [r for r in results if r.get("stuck")]
    errors = [r for r in results if r.get("error")]
    incomplete = [r for r in results if not r.get("ok")]

    leader_games: Counter[str] = Counter()
    leader_wins: Counter[str] = Counter()
    mirror_wins_seat0 = 0
    mirror_done = 0

    for r in results:
        l0, l1 = r.get("leader0"), r.get("leader1")
        if l0:
            leader_games[l0] += 1
        if l1:
            leader_games[l1] += 1
        if r.get("ok") and r.get("winner_seat") in (0, 1):
            w = l0 if r["winner_seat"] == 0 else l1
            if w:
                leader_wins[w] += 1
        if l0 == l1 and r.get("ok") and r.get("winner_seat") in (0, 1):
            mirror_done += 1
            if r["winner_seat"] == 0:
                mirror_wins_seat0 += 1

    phase_sum: Counter[str] = Counter()
    for r in results:
        phase_sum.update(r.get("phases") or {})

    avg_steps = sum(r.get("steps") or 0 for r in results) / max(1, len(results))
    avg_turns = sum((r.get("turns") or 0) for r in finished) / max(1, len(finished))
    avg_game_sec = sum(r.get("elapsed_sec") or 0 for r in results) / max(1, len(results))

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "pool": str(args.pool),
        "seed": args.seed,
        "games_scheduled": len(work),
        "games_finished": len(finished),
        "games_stuck": len(stuck),
        "games_error": len(errors),
        "games_incomplete": len(incomplete),
        "finish_rate": round(len(finished) / max(1, len(work)), 4),
        "wall_sec": round(wall, 2),
        "cpu_user_sec": round(cpu_user, 2),
        "cpu_sys_sec": round(cpu_sys, 2),
        "cpu_total_sec": round(cpu_user + cpu_sys, 2),
        "workers": args.workers,
        "approx_max_rss_mb": round(max_rss_mb, 1),
        "avg_steps": round(avg_steps, 1),
        "avg_turns_finished": round(avg_turns, 1),
        "avg_game_wall_sec": round(avg_game_sec, 3),
        "mirror_finished": mirror_done,
        "mirror_seat0_winrate": round(mirror_wins_seat0 / mirror_done, 4) if mirror_done else None,
        "leader_games": dict(leader_games),
        "leader_wins": dict(leader_wins),
        "phase_counts": dict(phase_sum),
        "note": (
            "This run measures stability of the CURRENT heuristic AI. "
            "It does not train or auto-improve the AI. "
            "Strength delta requires a before/after compare after editing battle/ai.py."
        ),
    }

    # Human-readable summary
    print("\n======== AI self-play report ========")
    print(f"games: {len(finished)} finished / {len(work)} scheduled "
          f"(stuck={len(stuck)} error={len(errors)})")
    print(f"wall time: {wall:.1f}s   CPU time: {cpu_user + cpu_sys:.1f}s "
          f"(user {cpu_user:.1f} + sys {cpu_sys:.1f})  workers={args.workers}")
    print(f"approx peak RSS: {max_rss_mb:.0f} MB  (CPU only — no GPU, no API tokens)")
    print(f"avg steps/game: {avg_steps:.0f}   avg turns (finished): {avg_turns:.1f}")
    if mirror_done:
        print(f"mirror seat0 winrate: {mirror_wins_seat0 / mirror_done:.1%}  (n={mirror_done})")
    print("\nLeader involvement (appearances / wins when game finished with winner):")
    for lid, n in sorted(leader_games.items(), key=lambda x: -x[1]):
        wins = leader_wins.get(lid, 0)
        label = _leader_label(catalog, lid)
        print(f"  {label:48s}  games={n:3d}  wins={wins:3d}")

    if errors[:3]:
        print("\nSample errors:")
        for r in errors[:3]:
            print(f"  {r.get('leader0')} vs {r.get('leader1')}: {r.get('error')}")

    # Baseline compare if present
    compare_path = args.compare_baseline
    if compare_path and compare_path.is_file():
        prev = json.loads(compare_path.read_text(encoding="utf-8"))
        print("\n--- vs saved baseline ---")
        for key in ("finish_rate", "games_stuck", "games_error", "avg_turns_finished", "mirror_seat0_winrate"):
            a, b = prev.get(key), report.get(key)
            print(f"  {key}: {a} → {b}")
        print("AI strength uplift: N/A unless battle/ai.py scoring changed between runs.")
    else:
        print("\nAI strength uplift: N/A (first/baseline run — no prior scoring change).")

    out_path = args.save_baseline or BASELINE_PATH
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nsaved {out_path}")


if __name__ == "__main__":
    main()
