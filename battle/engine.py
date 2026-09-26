from __future__ import annotations

import random
import re
from typing import Any, Callable

from battle.effects import (
    apply_ops,
    card_has_trigger,
    card_type_of,
    detect_keywords,
    event_playable_in_main,
    has_activate_main,
    has_banish,
    has_blocker,
    has_blockerless,
    has_counter_timing,
    has_double_attack,
    has_main_timing,
    has_rush,
    has_rush_character,
    live_keywords,
    max_deck_copies,
    normalize_colors,
)
from battle.effect_library import (
    ability_needs_confirm,
    ensure_loaded,
    resolve_ability,
    resolve_activate_spec,
    resolve_trigger_ops,
)
from battle.rules.checkpoints import (
    cancel_battle,
    combatants_present,
    concede as rules_concede,
    mark_pending_defeat,
    rule_process,
    set_loser as rules_set_loser,
)
from battle.rules import timings as rule_timings
from battle.state import (
    CardInst,
    MatchState,
    PendingAttack,
    PendingChoice,
    PendingEffect,
    PendingSearch,
    PendingTrigger,
    PlayerState,
    new_iid,
)

CatalogFn = Callable[[str], dict[str, Any]]
LlmFn = Callable[[str], str] | None


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "" or str(value).strip() in {"-", "—", "－"}:
            return default
        return int(str(value).strip().split()[0].replace(",", ""))
    except (TypeError, ValueError):
        return default


def printed_power(info: dict[str, Any]) -> int:
    return _to_int(info.get("power"), 0)


def printed_cost(info: dict[str, Any]) -> int:
    return max(0, _to_int(info.get("cost"), 0))


def printed_counter(info: dict[str, Any]) -> int:
    return max(0, _to_int(info.get("counter"), 0))


def effective_counter(state: MatchState, seat: int, card_id: str, catalog: CatalogFn) -> int:
    """Printed Counter, rewritten by in-play ``hand_counter`` auras (become +N)."""
    info = catalog(card_id)
    base = printed_counter(info)
    best = base
    try:
        from battle.effect_library import ability_is_runnable, get_abilities

        player = state.player(seat)
        sources: list[tuple[str, int]] = [(player.leader_card_id, int(player.leader_don or 0))]
        sources.extend((c.card_id, int(c.don_attached or 0)) for c in player.characters)
        sources.extend((s.card_id, 0) for s in player.stages)
        if card_id in player.hand and not any(c.card_id == card_id for c in player.characters):
            sources.append((card_id, 0))
        for src_cid, don in sources:
            if not src_cid:
                continue
            if src_cid in player.hand and src_cid != card_id:
                continue
            for ability in get_abilities(src_cid, "hand_cost"):
                if not ability_is_runnable(ability):
                    continue
                ops = [o for o in (ability.get("ops") or []) if o.get("op") == "hand_counter"]
                if not ops:
                    continue
                if not _ability_board_conditions_ok(
                    state, seat, ability, catalog, don_attached=don
                ):
                    continue
                for op in ops:
                    want_type = str(op.get("card_type") or "character").strip().lower()
                    if want_type and card_type_of(info) != want_type:
                        continue
                    pow_v = printed_power(info)
                    if op.get("power_eq") is not None and pow_v != int(op["power_eq"]):
                        continue
                    if op.get("power_gte") is not None and pow_v < int(op["power_gte"]):
                        continue
                    if op.get("power_lte") is not None and pow_v > int(op["power_lte"]):
                        continue
                    if op.get("require_no_counter") and base > 0:
                        continue
                    amt = int(op.get("amount") or 0)
                    if op.get("add"):
                        best = max(best, base + amt)
                    else:
                        # 「變更成反擊+N」replaces the printed Counter.
                        best = max(best, amt)
    except Exception:
        return base
    return max(0, best)


def live_leader_keywords(state: MatchState, seat: int, catalog: CatalogFn) -> list[str]:
    """Innate Leader keywords plus this-turn grants and board your_turn/opponent_turn auras."""
    player = state.player(seat)
    info = catalog(player.leader_card_id) if player.leader_card_id else {}
    keys = [k for k in detect_keywords(info) if k != "trigger"]
    for k in player.leader_turn_keywords or []:
        if k and k not in keys:
            keys.append(k)
    for e in player.leader_keywords_until_end or []:
        k = str(e.get("keyword") or "")
        if k and k not in keys:
            keys.append(k)
    try:
        from battle.effect_library import ability_is_runnable, get_abilities

        my_turn = state.turn_seat == seat
        want = {"blocker", "rush", "rush_character", "double_attack", "banish", "blockerless"}
        missing = [k for k in want if k not in keys]
        if not missing:
            return keys
        sources: list[tuple[str, str, int]] = [
            ("leader", player.leader_card_id, int(player.leader_don or 0)),
            *[(c.iid, c.card_id, int(c.don_attached or 0)) for c in player.characters],
            *[(s.iid, s.card_id, 0) for s in player.stages],
        ]
        for src_iid, cid, don in sources:
            if not cid:
                continue
            for timing in ("your_turn", "opponent_turn"):
                if timing == "your_turn" and not my_turn:
                    continue
                if timing == "opponent_turn" and my_turn:
                    continue
                for ability in get_abilities(cid, timing):
                    if not ability_is_runnable(ability):
                        continue
                    if not _ability_board_conditions_ok(
                        state, seat, ability, catalog, don_attached=don, source_iid=src_iid
                    ):
                        continue
                    for o in ability.get("ops") or []:
                        if str(o.get("op") or "") != "grant_keyword":
                            continue
                        tk = str(o.get("target_kind") or "").strip().lower()
                        if tk not in {"leader", "own_leader"}:
                            continue
                        kw = str(o.get("keyword") or "").strip().lower()
                        if kw in missing and kw not in keys:
                            keys.append(kw)
                            missing = [k for k in missing if k != kw]
                            if not missing:
                                return keys
    except Exception:
        pass
    return keys


def leader_life_value(info: dict[str, Any]) -> int:
    life = _to_int(info.get("life"), 0)
    if life > 0:
        return min(10, life)
    return 5


def expand_deck(cards: dict[str, int]) -> list[str]:
    out: list[str] = []
    for cid, qty in (cards or {}).items():
        n = max(0, int(qty or 0))
        out.extend([cid] * n)
    return out


# Unreleased / preview sets — allowed in casual & AI, blocked in ranked.
RANKED_BANNED_SET_PREFIXES: frozenset[str] = frozenset({"OP18", "EB05"})


def _ranked_banned_set_of(card_id: str) -> str | None:
    text = str(card_id or "").strip().upper()
    for prefix in RANKED_BANNED_SET_PREFIXES:
        if text == prefix or text.startswith(f"{prefix}-"):
            return prefix
    return None


def deck_has_ranked_banned_cards(leader_id: str, cards: dict[str, int]) -> list[str]:
    """Return sorted unique card ids from leader + main deck that are ranked-banned."""
    banned: set[str] = set()
    lid = str(leader_id or "").strip()
    if lid and _ranked_banned_set_of(lid):
        banned.add(lid)
    for cid, qty in (cards or {}).items():
        if int(qty or 0) <= 0:
            continue
        cid_s = str(cid or "").strip()
        if cid_s and _ranked_banned_set_of(cid_s):
            banned.add(cid_s)
    return sorted(banned)


def ranked_deck_ban_error(leader_id: str, cards: dict[str, int]) -> str | None:
    """Human-readable ranked ban error, or None if the deck is ranked-legal."""
    banned = deck_has_ranked_banned_cards(leader_id, cards)
    if not banned:
        return None
    sets = sorted({s for cid in banned if (s := _ranked_banned_set_of(cid))})
    set_label = " / ".join(sets) if sets else "unreleased"
    sample = ", ".join(banned[:6])
    more = f" (+{len(banned) - 6} more)" if len(banned) > 6 else ""
    return (
        f"Ranked decks cannot include unreleased set(s) {set_label} "
        f"(e.g. {sample}{more}). Use casual / room play instead."
    )


def validate_battle_deck(leader_id: str, cards: dict[str, int], catalog: CatalogFn) -> str | None:
    if not leader_id:
        return "Deck needs a Leader."
    leader = catalog(leader_id)
    if not leader or card_type_of(leader) != "leader":
        return "Invalid Leader."
    ban_event_cost_gte: int | None = None
    try:
        from battle.effect_library import get_abilities, get_card_entry

        entry = get_card_entry(leader_id) or {}
        if entry.get("deck_ban_event_cost_gte") is not None:
            ban_event_cost_gte = int(entry["deck_ban_event_cost_gte"])
        for ab in get_abilities(leader_id):
            if ab.get("deck_ban_event_cost_gte") is not None:
                ban_event_cost_gte = int(ab["deck_ban_event_cost_gte"])
            for op in ab.get("ops") or []:
                if op.get("op") == "rule_ban_events_cost_gte":
                    ban_event_cost_gte = int(op.get("cost_gte") or 2)
    except Exception:
        ban_event_cost_gte = None
    total = 0
    leader_colors = normalize_colors(leader.get("colors_en") or leader.get("colors"))
    for cid, qty in cards.items():
        n = int(qty or 0)
        if n <= 0:
            continue
        info = catalog(cid)
        if not info:
            return f"Unknown card {cid}."
        limit = max_deck_copies(info)
        if n > limit:
            return f"{cid} exceeds the {limit}-copy limit."
        total += n
        if card_type_of(info) == "leader":
            return "Main deck cannot include Leaders."
        if ban_event_cost_gte is not None and card_type_of(info) == "event":
            if printed_cost(info) >= int(ban_event_cost_gte):
                return f"{cid}: Leader forbids Events with cost ≥{ban_event_cost_gte}."
        card_colors = normalize_colors(info.get("colors_en") or info.get("colors"))
        if leader_colors and card_colors and leader_colors.isdisjoint(card_colors):
            return f"{cid} does not match Leader colors."
    if total != 50:
        return "Main deck must contain exactly 50 cards."
    return None


def start_match(
    room_code: str,
    p0: dict[str, Any],
    p1: dict[str, Any],
    catalog: CatalogFn,
    rng: random.Random | None = None,
) -> MatchState:
    """
    Setup per 5-2-1:
      draw 5 → mulligan (first then second) → place Life → first player's turn.
    """
    rng = rng or random.Random()
    seed = rng.randrange(1, 2**31 - 1)
    rng = random.Random(seed)
    first = 0 if rng.random() < 0.5 else 1
    players: list[PlayerState] = []
    for seat, spec in enumerate((p0, p1)):
        leader_id = str(spec["leader_card_id"])
        deck = expand_deck(spec["cards"])
        rng.shuffle(deck)
        # 5-2-1-6: opening hand only — Life is placed AFTER mulligan (5-2-1-7)
        hand = [deck.pop(0) for _ in range(min(5, len(deck)))]
        players.append(
            PlayerState(
                seat=seat,
                user_id=str(spec["user_id"]),
                username=str(spec.get("username") or f"P{seat + 1}"),
                is_ai=bool(spec.get("is_ai")),
                leader_card_id=leader_id,
                deck=deck,
                hand=hand,
                don_deck_size=_leader_don_deck_size(leader_id),
            )
        )
    state = MatchState(
        room_code=room_code,
        status="playing",
        phase="mulligan",
        turn_seat=first,
        first_seat=first,
        turn_number=1,
        players=players,
        mulligan_seat=first,
        rng_seed=seed,
    )
    state.add_log("play.log.first_mulligan", name=state.player(first).username)
    return state


def _rng(state: MatchState) -> random.Random:
    # Derive a working RNG; advance seed so reshuffles differ
    state.rng_seed = (state.rng_seed * 1103515245 + 12345) & 0x7FFFFFFF
    return random.Random(state.rng_seed)


def _place_life(state: MatchState, catalog: CatalogFn) -> None:
    """5-2-1-7: top-of-deck card becomes bottom of Life; damage peels from Life top."""
    for player in state.players:
        info = catalog(player.leader_card_id)
        n = leader_life_value(info)
        taken: list[str] = []
        for _ in range(min(n, len(player.deck))):
            taken.append(player.deck.pop(0))
        # taken[0] was deck top → Life bottom; reverse so life[0] is Life top
        player.life = list(reversed(taken))
        state.add_log("play.log.sets_life", name=player.username, n=len(player.life))


def _finish_mulligan_and_start(state: MatchState, catalog: CatalogFn) -> None:
    _place_life(state, catalog)
    state.mulligan_seat = None
    state.add_log("play.log.starts_turn1", name=state.player(state.first_seat).username)
    _begin_turn(state, state.first_seat, catalog)


def _clear_once_per_turn_flags(player: PlayerState) -> None:
    """【每回合1次】is once during the current turn, not once until the owner's refresh.

    Dual-timing leaders (e.g. OP17-058 [When Attacking]/[On Opponent's Attack]) must
    be usable again on the opponent's turn after firing on the owner's attack.
    """
    player.leader_once_used = False
    player.leader_on_opp_ko_used = False
    player.skipped_activate_iids = []
    for ch in player.characters:
        ch.once_used = False
        if hasattr(ch, "on_opp_ko_used"):
            ch.on_opp_ko_used = False
    for stg in player.stages:
        stg.once_used = False


def _begin_turn(state: MatchState, seat: int, catalog: CatalogFn) -> None:
    player = state.player(seat)
    # New turn: Once Per Turn + hand-trash flags reset for both seats.
    for p in state.players:
        p.hand_trashed_by_effect_this_turn = False
        p.opp_life_left_this_turn = False
        _clear_once_per_turn_flags(p)
    # 6-2-3: return attached DON!! to cost area as rested
    returned = player.leader_don
    player.leader_don = 0
    for ch in player.characters:
        returned += ch.don_attached
        ch.don_attached = 0
    player.don_rested += returned
    # 6-2-4: rest → active
    if getattr(player, "leader_skip_untap", False):
        player.leader_skip_untap = False
        # Leader remains rested this refresh.
    else:
        player.leader_rested = False
    player.leader_power_mod = 0
    skip = set(player.skip_untap_iids)
    player.skip_untap_iids.clear()
    for ch in player.characters:
        if ch.iid in skip:
            # Remains rested for this refresh.
            ch.power_mod = 0
            ch.base_power_override = None
            ch.power_override = None
            ch.cannot_be_ko = False
            ch.cannot_be_removed = False
            ch.summoning_sick = False
            continue
        ch.rested = False
        ch.power_mod = 0
        ch.base_power_override = None
        ch.power_override = None
        ch.cannot_be_ko = False
        ch.cannot_be_removed = False
        ch.summoning_sick = False
    for st in player.stages:
        if st.iid in skip:
            st.once_used = False
            continue
        st.rested = False
        st.once_used = False
    skip_don = max(0, int(getattr(player, "skip_untap_don", 0) or 0))
    player.skip_untap_don = 0
    keep_don = min(skip_don, int(player.don_rested or 0))
    player.don_active += max(0, int(player.don_rested or 0) - keep_don)
    player.don_rested = keep_don
    player.replace_battle_ko = False
    player.cannot_take_life = False
    player.attack_active_iids.clear()
    player.attacked_this_turn_iids.clear()
    player.deny_blocker.clear()
    # Draw (6-3-1)
    is_first_turn = player.turns_completed == 0
    is_first_player_turn_one = is_first_turn and seat == state.first_seat
    if not is_first_player_turn_one:
        if not player.deck:
            mark_pending_defeat(state, seat, "play.log.decks_out", name=player.username)
            rule_process(state)
            return
        player.hand.append(player.deck.pop(0))
        if not player.deck:
            mark_pending_defeat(state, seat, "play.log.decks_out", name=player.username)
    # DON!! (6-4-1 / 6-4-2 / 6-4-3)
    gain = 1 if is_first_player_turn_one else 2
    room = don_deck_room(player)
    gain = min(gain, room)
    player.don_given += gain
    player.don_active += gain
    state.phase = "main"
    state.attack = None
    state.pending_trigger = None
    state.trigger_resume = None
    if is_first_turn:
        state.add_log("play.log.first_turn_no_attack", name=player.username)
    # After DON!! Phase placement (e.g. OP13-003 auto-attach 1 placed DON!! to Leader).
    if gain > 0:
        _fire_board_timing(state, seat, "on_don_phase", catalog)
    # 6-2-2 / 6-5-1 hooks (automatic timings)
    if not _pending_interactive(state):
        _fire_board_timing(state, seat, rule_timings.TURN_START, catalog)
    if not _pending_interactive(state):
        _fire_board_timing(state, seat, rule_timings.MAIN_START, catalog)
    rule_process(state)
    state.touch()


def _set_loser(state: MatchState, loser_seat: int, reason_key: str, **params) -> None:
    """Delegate to Ch.9 checkpoint (keeps call sites stable)."""
    rules_set_loser(state, loser_seat, reason_key, **params)


def _pending_interactive(state: MatchState) -> bool:
    return bool(
        state.pending_choice
        or state.pending_search
        or state.pending_effect
        or state.pending_trigger
        or getattr(state, "pending_replace", None)
    )


def _record_event_activated(state: MatchState, seat: int, event_card_id: str, catalog: CatalogFn) -> None:
    """Track printed costs of Events activated this turn (for Lucy-style gates)."""
    info = catalog(event_card_id) or {}
    try:
        cost = int(info.get("cost") if info.get("cost") is not None else info.get("cost_en") or 0)
    except (TypeError, ValueError):
        cost = 0
    player = state.player(seat)
    costs = list(getattr(player, "event_activated_costs", None) or [])
    costs.append(cost)
    player.event_activated_costs = costs


def _fire_armed_draw_on_event(
    state: MatchState,
    seat: int,
    event_card_id: str,
    catalog: CatalogFn,
) -> bool:
    """Lucy-style arm: after Activate Main arm, draw when an Event with printed cost ≥ N is activated."""
    player = state.player(seat)
    rules = list(getattr(player, "draw_on_event_rules", None) or [])
    if not rules or state.status != "playing":
        return False
    info = catalog(event_card_id) or {}
    try:
        cost = int(info.get("cost") if info.get("cost") is not None else info.get("cost_en") or 0)
    except (TypeError, ValueError):
        cost = 0
    from battle.effects import apply_ops

    fired = False
    for rule in rules:
        need = int(rule.get("cost_gte") or 0)
        if cost < need:
            continue
        draw_n = max(1, min(5, int(rule.get("count") or 1)))
        logs = apply_ops(state, seat, [{"op": "draw", "count": draw_n}], catalog)
        for line in logs:
            state.add_log(line)
        fired = True
        if _pending_interactive(state) or state.status != "playing":
            break
    return fired


def _resume_board_timing(state: MatchState, catalog: CatalogFn) -> bool:
    """Continue a paused `_fire_board_timing` queue after confirm/choice settles."""
    if state.status == "playing" and not _pending_interactive(state):
        _flush_deferred_play_watchers(state, catalog)
        _try_enter_combat_steps(state, catalog)
    resume = getattr(state, "board_timing_resume", None)
    if not resume or state.status != "playing":
        return False
    if _pending_interactive(state):
        return True
    seat = int(resume.get("seat") or 0)
    timing = str(resume.get("timing") or "")
    remaining = list(resume.get("remaining") or [])
    state.board_timing_resume = None
    if not timing or not remaining:
        return False
    paused = _fire_board_timing(state, seat, timing, catalog, sources=remaining)
    if state.status == "playing" and not _pending_interactive(state):
        _try_enter_combat_steps(state, catalog)
    return paused


def _flush_deferred_play_watchers(state: MatchState, catalog: CatalogFn) -> bool:
    """Fire on_own_play_character watchers delayed by an interactive On Play."""
    pending = getattr(state, "deferred_play_watchers", None)
    if not pending or state.status != "playing" or _pending_interactive(state):
        return False
    state.deferred_play_watchers = None
    return _fire_character_play_watchers(
        state,
        int(pending.get("seat") or 0),
        str(pending.get("played_iid") or ""),
        str(pending.get("played_card_id") or ""),
        catalog,
        from_zone=str(pending.get("from_zone") or "hand"),
        by_character_effect=bool(pending.get("by_character_effect")),
    )


def _after_character_enters(
    state: MatchState,
    seat: int,
    played_iid: str,
    played_card_id: str,
    catalog: CatalogFn,
    *,
    from_zone: str = "hand",
    by_character_effect: bool = False,
) -> None:
    """Apply play-from-zone watchers (e.g. OP16-079 Rush), then the card's On Play.

    Watchers run first so Rush is not skipped when On Play opens a choice/search.
    If On Play is interactive before watchers could run, defer them.
    """
    # Prefer immediate watchers so Rush clears summoning sickness before On Play UI.
    if state.status == "playing" and not _pending_interactive(state):
        _fire_character_play_watchers(
            state,
            seat,
            played_iid,
            played_card_id,
            catalog,
            from_zone=from_zone,
            by_character_effect=by_character_effect,
        )
    elif state.status == "playing":
        state.deferred_play_watchers = {
            "seat": seat,
            "played_iid": played_iid,
            "played_card_id": played_card_id,
            "from_zone": from_zone,
            "by_character_effect": by_character_effect,
        }
        return
    if state.status != "playing":
        return
    info = catalog(played_card_id)
    pending = resolve_ability(
        state, seat, played_card_id, played_iid, "on_play", info, None, allow_llm=False, catalog=catalog
    )
    if pending and pending.ops:
        _run_pending_effect(state, pending, catalog)


def _fire_board_timing(
    state: MatchState,
    seat: int,
    timing: str,
    catalog: CatalogFn,
    sources: list[tuple[str, str]] | None = None,
) -> bool:
    """
    Resolve automatic abilities for Leader / Characters / Stages at `timing`.
    Returns True if the game paused for interactive pending (choice/search/effect).
    """
    if state.status != "playing":
        return False
    player = state.player(seat)
    if sources is None:
        src_list: list[tuple[str, str]] = [("leader", player.leader_card_id)]
        src_list.extend((c.iid, c.card_id) for c in list(player.characters))
        src_list.extend((s.iid, s.card_id) for s in list(player.stages))
    else:
        src_list = list(sources)
    for idx, (src_iid, cid) in enumerate(src_list):
        if state.status != "playing":
            return False
        # Source may have left mid-resolution
        if src_iid != "leader":
            if not any(c.iid == src_iid for c in player.characters) and not any(
                s.iid == src_iid for s in player.stages
            ):
                continue
        info = catalog(cid)
        pending = resolve_ability(
            state, seat, cid, src_iid, timing, info, None, allow_llm=False, catalog=catalog
        )
        if not pending or not pending.ops:
            continue
        if any(str(o.get("op") or "") == "unsupported" for o in pending.ops):
            continue
        _run_pending_effect(state, pending, catalog)
        if _pending_interactive(state):
            rest = src_list[idx + 1 :]
            if rest:
                state.board_timing_resume = {
                    "seat": seat,
                    "timing": timing,
                    "remaining": [[a, b] for a, b in rest],
                }
            return True
        rule_process(state)
    return False



def _fire_opp_activation_watchers(
    state: MatchState,
    activator_seat: int,
    catalog: CatalogFn,
    *,
    kind: str,
) -> bool:
    """Fire opponent board watchers when activator plays an Event or accepts a Trigger.

    kind: "event" → on_opp_event; "trigger" → on_opp_trigger (+ on_opp_event with also_on_opp_trigger).
    """
    if state.status != "playing":
        return False
    watcher = state.other(activator_seat)
    if kind == "event":
        return _fire_board_timing(state, watcher, "on_opp_event", catalog)
    if kind == "trigger":
        paused = _fire_board_timing(state, watcher, "on_opp_trigger", catalog)
        if paused:
            return True
        # Also fire on_opp_event abilities that opt into Trigger watches (OP11-102).
        from battle.effect_library import get_abilities, ability_is_runnable

        player = state.player(watcher)
        sources: list[tuple[str, str]] = [("leader", player.leader_card_id)]
        sources.extend((c.iid, c.card_id) for c in list(player.characters))
        sources.extend((s.iid, s.card_id) for s in list(player.stages))
        for src_iid, cid in sources:
            if state.status != "playing":
                return False
            if src_iid != "leader":
                if not any(c.iid == src_iid for c in player.characters) and not any(
                    s.iid == src_iid for s in player.stages
                ):
                    continue
            info = catalog(cid)
            for ab in get_abilities(cid, "on_opp_event"):
                if not ability_is_runnable(ab) or not ab.get("also_on_opp_trigger"):
                    continue
                pending = resolve_ability(
                    state, watcher, cid, src_iid, "on_opp_event", info, None, allow_llm=False, catalog=catalog
                )
                if not pending or not pending.ops:
                    continue
                if any(str(o.get("op") or "") == "unsupported" for o in pending.ops):
                    continue
                _run_pending_effect(state, pending, catalog)
                if _pending_interactive(state):
                    return True
                rule_process(state)
        return False
    return False


def _played_card_gates_ok(
    ability: dict[str, Any],
    played_info: dict[str, Any],
    *,
    from_zone: str | None = None,
    by_character_effect: bool = False,
) -> bool:
    """Ability filters against the Character that just entered the field."""
    from battle.effects import card_has_trigger

    if ability.get("require_played_has_trigger") and not card_has_trigger(played_info):
        return False
    if ability.get("require_played_from_trash") and (from_zone or "").lower() != "trash":
        return False
    trait = str(ability.get("require_played_trait") or "").strip()
    if trait and not _info_has_trait(played_info, trait):
        return False
    # OP12-081: base cost≥N OR played by a Character effect.
    base_gte = ability.get("require_played_base_cost_gte")
    or_by_char = bool(ability.get("or_played_by_character_effect"))
    if base_gte is not None:
        try:
            base = int(played_info.get("cost") or played_info.get("cost_en") or 99)
        except (TypeError, ValueError):
            base = 99
        ok_cost = base >= int(base_gte)
        if or_by_char:
            if not (ok_cost or by_character_effect):
                return False
        elif not ok_cost:
            return False
    elif ability.get("require_played_by_character_effect") and not by_character_effect:
        return False
    return True


def _fire_character_play_watchers(
    state: MatchState,
    seat: int,
    played_iid: str,
    played_card_id: str,
    catalog: CatalogFn,
    *,
    from_zone: str | None = "hand",
    by_character_effect: bool = False,
) -> bool:
    """Fire on_own_play_character / on_opp_play_character / on_opponent_play after a Character enters."""
    if state.status != "playing":
        return False
    from battle.effect_library import ability_is_runnable, get_abilities
    from battle.state import PendingEffect, new_iid

    played_info = catalog(played_card_id) or {}

    def _run_flagged(watcher: int, flag: str, timings: tuple[str, ...]) -> bool:
        player = state.player(watcher)
        sources: list[tuple[str, str]] = [("leader", player.leader_card_id)]
        sources.extend((c.iid, c.card_id) for c in list(player.characters))
        sources.extend((s.iid, s.card_id) for s in list(player.stages))
        for src_iid, cid in sources:
            if state.status != "playing":
                return False
            if src_iid == played_iid:
                # The just-played card itself is not a watcher for its own entrance.
                continue
            if src_iid != "leader":
                if not any(c.iid == src_iid for c in player.characters) and not any(
                    s.iid == src_iid for s in player.stages
                ):
                    continue
            info = catalog(cid)
            for timing in timings:
                for ab in get_abilities(cid, timing):
                    if not ability_is_runnable(ab) or not ab.get(flag):
                        continue
                    my_turn = state.turn_seat == watcher
                    if timing == "your_turn" and not my_turn:
                        continue
                    if timing == "opponent_turn" and my_turn:
                        continue
                    if not _played_card_gates_ok(
                        ab,
                        played_info,
                        from_zone=from_zone,
                        by_character_effect=by_character_effect,
                    ):
                        continue
                    don = 0
                    if src_iid == "leader":
                        don = int(player.leader_don or 0)
                    else:
                        inst = next((c for c in player.characters if c.iid == src_iid), None)
                        don = int(inst.don_attached or 0) if inst else 0
                    if not _ability_board_conditions_ok(
                        state, watcher, ab, catalog, don_attached=don, source_iid=src_iid
                    ):
                        continue
                    if ab.get("once"):
                        if src_iid == "leader" and player.leader_once_used:
                            continue
                        inst = next((c for c in player.characters if c.iid == src_iid), None)
                        if inst is not None and inst.once_used:
                            continue
                        stage = next((s for s in player.stages if s.iid == src_iid), None)
                        if stage is not None and stage.once_used:
                            continue
                    ops = []
                    for o in ab.get("ops") or []:
                        if not isinstance(o, dict):
                            continue
                        oo = dict(o)
                        oo.setdefault("source_iid", src_iid)
                        oo.setdefault("card_id", cid)
                        # OP16-079-class: keyword/buff the Character that just entered.
                        if flag == "on_own_play_character" and oo.get("op") in {
                            "grant_keyword",
                            "buff",
                            "buff_self",
                        }:
                            oo.setdefault("target_iid", played_iid)
                        ops.append(oo)
                    if not ops:
                        continue
                    pending = PendingEffect(
                        effect_id=new_iid("fx"),
                        seat=watcher,
                        card_id=cid,
                        source_iid=src_iid,
                        summary=str(ab.get("summary") or flag)[:240],
                        ops=ops,
                        uncertain=ability_needs_confirm(ab, info),
                        once=bool(ab.get("once")),
                    )
                    _run_pending_effect(state, pending, catalog)
                    if _pending_interactive(state):
                        return True
                    rule_process(state)
                    break
        return False

    def _run_on_opponent_play_timing(watcher: int) -> bool:
        """Fire timing=on_opponent_play with played-card gates (OP12-081)."""
        player = state.player(watcher)
        sources: list[tuple[str, str]] = [("leader", player.leader_card_id)]
        sources.extend((c.iid, c.card_id) for c in list(player.characters))
        for src_iid, cid in sources:
            if state.status != "playing":
                return False
            if src_iid == played_iid:
                continue
            if src_iid != "leader" and not any(c.iid == src_iid for c in player.characters):
                continue
            info = catalog(cid)
            for ab in get_abilities(cid, "on_opponent_play"):
                if not ability_is_runnable(ab):
                    continue
                if not _played_card_gates_ok(
                    ab,
                    played_info,
                    from_zone=from_zone,
                    by_character_effect=by_character_effect,
                ):
                    continue
                don = int(player.leader_don or 0) if src_iid == "leader" else 0
                if src_iid != "leader":
                    inst = next((c for c in player.characters if c.iid == src_iid), None)
                    don = int(inst.don_attached or 0) if inst else 0
                if not _ability_board_conditions_ok(
                    state, watcher, ab, catalog, don_attached=don, source_iid=src_iid
                ):
                    continue
                if ab.get("once"):
                    if src_iid == "leader" and player.leader_once_used:
                        continue
                    inst = next((c for c in player.characters if c.iid == src_iid), None)
                    if inst is not None and inst.once_used:
                        continue
                ops = []
                for o in ab.get("ops") or []:
                    if not isinstance(o, dict):
                        continue
                    oo = dict(o)
                    oo.setdefault("source_iid", src_iid)
                    oo.setdefault("card_id", cid)
                    ops.append(oo)
                if not ops:
                    continue
                pending = PendingEffect(
                    effect_id=new_iid("fx"),
                    seat=watcher,
                    card_id=cid,
                    source_iid=src_iid,
                    summary=str(ab.get("summary") or "on_opponent_play")[:240],
                    ops=ops,
                    uncertain=ability_needs_confirm(ab, info),
                    once=bool(ab.get("once")),
                )
                _run_pending_effect(state, pending, catalog)
                if _pending_interactive(state):
                    return True
                rule_process(state)
                break
        return False

    if _run_flagged(seat, "on_own_play_character", ("your_turn", "opponent_turn", "on_event")):
        return True
    opp = state.other(seat)
    if _run_on_opponent_play_timing(opp):
        return True
    if _run_flagged(opp, "on_opp_play_character", ("your_turn", "opponent_turn", "on_opponent_play")):
        return True
    return False


def _fire_trigger_activation_watchers(
    state: MatchState,
    activator_seat: int,
    catalog: CatalogFn,
) -> bool:
    """Fire both seats' on_trigger watchers when a Trigger is accepted, then opp-only hooks."""
    if state.status != "playing":
        return False
    for seat in (activator_seat, state.other(activator_seat)):
        if _fire_board_timing(state, seat, "on_trigger", catalog):
            return True
    return _fire_opp_activation_watchers(state, activator_seat, catalog, kind="trigger")


def _attack_tax_needed(player: PlayerState, attacker_iid: str) -> int:
    """Return hand cards that must be trashed to declare this attack (0 = none)."""
    need = 0
    for rule in player.attack_tax_rules or []:
        if rule.get("all") or str(rule.get("iid") or "") == attacker_iid:
            need = max(need, int(rule.get("trash_hand") or 0))
    return need


def _fire_self_rested(state: MatchState, seat: int, source_iid: str, catalog: CatalogFn) -> None:
    """Fire your_turn abilities with trigger_on=self_rested after this character rests."""
    if source_iid == "leader" or state.status != "playing":
        return
    player = state.player(seat)
    inst = next((c for c in player.characters if c.iid == source_iid), None)
    if not inst:
        return
    # Only during the owner's turn (OP14-119 [Your Turn] when this becomes rested).
    if state.turn_seat != seat:
        return
    info = catalog(inst.card_id)
    pending = resolve_ability(
        state,
        seat,
        inst.card_id,
        source_iid,
        "your_turn",
        info,
        None,
        allow_llm=False,
        catalog=catalog,
        trigger_on="self_rested",
    )
    if pending and pending.ops:
        _run_pending_effect(state, pending, catalog)


def _fire_flagged_board_abilities(
    state: MatchState,
    seat: int,
    catalog: CatalogFn,
    *,
    timings: tuple[str, ...],
    trigger_on: str,
) -> bool:
    """Resolve board abilities for seat at given timings with an explicit trigger_on filter."""
    if state.status != "playing":
        return False
    player = state.player(seat)
    sources: list[tuple[str, str]] = [("leader", player.leader_card_id)]
    sources.extend((c.iid, c.card_id) for c in list(player.characters))
    sources.extend((s.iid, s.card_id) for s in list(player.stages))
    for src_iid, cid in sources:
        if state.status != "playing":
            return False
        if src_iid != "leader":
            if not any(c.iid == src_iid for c in player.characters) and not any(
                s.iid == src_iid for s in player.stages
            ):
                continue
        info = catalog(cid)
        for timing in timings:
            pending = resolve_ability(
                state,
                seat,
                cid,
                src_iid,
                timing,
                info,
                None,
                allow_llm=False,
                catalog=catalog,
                trigger_on=trigger_on,
            )
            if not pending or not pending.ops:
                continue
            if any(str(o.get("op") or "") == "unsupported" for o in pending.ops):
                continue
            _run_pending_effect(state, pending, catalog)
            if _pending_interactive(state):
                return True
            rule_process(state)
    return False


def fire_on_life_damage(
    state: MatchState,
    damaged_seat: int,
    catalog: CatalogFn,
) -> bool:
    """Fire on_life_damage watchers when a player takes Life damage (e.g. OP13-002 Ace)."""
    if state.status != "playing":
        return False
    from battle.effect_library import ability_is_runnable, get_abilities

    paused = False
    player = state.player(damaged_seat)
    sources: list[tuple[str, str]] = [("leader", player.leader_card_id)]
    sources.extend((c.iid, c.card_id) for c in list(player.characters))
    for src_iid, cid in sources:
        if state.status != "playing":
            return paused
        if src_iid != "leader" and not any(c.iid == src_iid for c in player.characters):
            continue
        info = catalog(cid)
        for ab in get_abilities(cid, "on_life_damage"):
            if not ability_is_runnable(ab):
                continue
            if ab.get("once"):
                if src_iid == "leader" and player.leader_once_used:
                    continue
                inst = next((c for c in player.characters if c.iid == src_iid), None)
                if inst is not None and inst.once_used:
                    continue
            don_attached = int(player.leader_don or 0) if src_iid == "leader" else 0
            if src_iid != "leader":
                inst = next((c for c in player.characters if c.iid == src_iid), None)
                if inst is not None:
                    don_attached = int(inst.don_attached or 0)
            if not _ability_board_conditions_ok(
                state,
                damaged_seat,
                ab,
                catalog,
                don_attached=don_attached,
                source_iid=src_iid,
            ):
                continue
            pending = resolve_ability(
                state,
                damaged_seat,
                cid,
                src_iid,
                "on_life_damage",
                info,
                None,
                allow_llm=False,
                catalog=catalog,
            )
            if not pending or not pending.ops:
                continue
            if any(str(o.get("op") or "") == "unsupported" for o in pending.ops):
                continue
            if ab.get("once"):
                if src_iid == "leader":
                    player.leader_once_used = True
                else:
                    inst = next((c for c in player.characters if c.iid == src_iid), None)
                    if inst is not None:
                        inst.once_used = True
            _run_pending_effect(state, pending, catalog)
            if _pending_interactive(state):
                paused = True
                break
        if paused:
            break
    return paused


def fire_life_leave(
    state: MatchState,
    life_owner_seat: int,
    catalog: CatalogFn,
) -> bool:
    """Fire your_turn/opponent_turn watchers with on_life_leave when a Life card leaves."""
    if state.status != "playing":
        return False
    # Mark for the opponent of the Life owner (hand-cost 「相手のライフが離れているターン中」).
    try:
        state.player(state.other(life_owner_seat)).opp_life_left_this_turn = True
    except Exception:
        pass
    from battle.effect_library import ability_is_runnable, get_abilities

    paused = False
    for watch_seat in (0, 1):
        if state.status != "playing":
            return paused
        player = state.player(watch_seat)
        my_turn = state.turn_seat == watch_seat
        sources: list[tuple[str, str]] = [("leader", player.leader_card_id)]
        sources.extend((c.iid, c.card_id) for c in list(player.characters))
        sources.extend((s.iid, s.card_id) for s in list(player.stages))
        for src_iid, cid in sources:
            if state.status != "playing":
                return paused
            if src_iid != "leader":
                if not any(c.iid == src_iid for c in player.characters) and not any(
                    s.iid == src_iid for s in player.stages
                ):
                    continue
            info = catalog(cid)
            for ab in get_abilities(cid):
                has_flag = bool(ab.get("on_life_leave")) or any(
                    isinstance(o, dict) and o.get("on_life_leave") for o in (ab.get("ops") or [])
                )
                if not has_flag:
                    continue
                if not ability_is_runnable(ab):
                    continue
                timing = str(ab.get("timing") or "")
                if timing == "opponent_turn" and my_turn:
                    continue
                if timing == "your_turn" and not my_turn:
                    continue
                if timing not in {"your_turn", "opponent_turn"}:
                    continue
                src_from = str(ab.get("on_life_leave_from") or "either").strip().lower()
                if src_from == "self" and life_owner_seat != watch_seat:
                    continue
                if src_from == "opponent" and life_owner_seat == watch_seat:
                    continue
                if ab.get("once"):
                    if src_iid == "leader" and player.leader_once_used:
                        continue
                    inst = next((c for c in player.characters if c.iid == src_iid), None)
                    if inst is not None and inst.once_used:
                        continue
                    stage = next((s for s in player.stages if s.iid == src_iid), None)
                    if stage is not None and stage.once_used:
                        continue
                don_attached = 0
                if src_iid == "leader":
                    don_attached = int(player.leader_don or 0)
                else:
                    inst = next((c for c in player.characters if c.iid == src_iid), None)
                    if inst is not None:
                        don_attached = int(inst.don_attached or 0)
                if not _ability_board_conditions_ok(
                    state,
                    watch_seat,
                    ab,
                    catalog,
                    don_attached=don_attached,
                    source_iid=src_iid,
                ):
                    continue
                pending = resolve_ability(
                    state,
                    watch_seat,
                    cid,
                    src_iid,
                    timing,
                    info,
                    None,
                    allow_llm=False,
                    catalog=catalog,
                    trigger_on="life_leave",
                )
                if not pending or not pending.ops:
                    continue
                if any(str(o.get("op") or "") == "unsupported" for o in pending.ops):
                    continue
                if ab.get("once"):
                    if src_iid == "leader":
                        player.leader_once_used = True
                    else:
                        inst = next((c for c in player.characters if c.iid == src_iid), None)
                        if inst is not None:
                            inst.once_used = True
                        else:
                            stage = next((s for s in player.stages if s.iid == src_iid), None)
                            if stage is not None:
                                stage.once_used = True
                _run_pending_effect(state, pending, catalog)
                if _pending_interactive(state):
                    paused = True
                    return True
                rule_process(state)
    return paused


def _fire_don_returned(state: MatchState, seat: int, count: int, catalog: CatalogFn) -> bool:
    """Fire on_don_returned abilities after DON!! cards leave the field to the DON!! deck."""
    if state.status != "playing" or count <= 0:
        return False
    from battle.effect_library import get_abilities, ability_is_runnable

    player = state.player(seat)
    sources: list[tuple[str, str]] = [("leader", player.leader_card_id)]
    sources.extend((c.iid, c.card_id) for c in list(player.characters))
    for src_iid, cid in sources:
        if state.status != "playing":
            return False
        if src_iid != "leader" and not any(c.iid == src_iid for c in player.characters):
            continue
        info = catalog(cid)
        for ab in get_abilities(cid, "on_don_returned"):
            if not ability_is_runnable(ab):
                continue
            need = int(ab.get("on_return_don_from_field_gte") or ab.get("on_return_don_gte") or 1)
            if count < need:
                continue
            pending = resolve_ability(
                state, seat, cid, src_iid, "on_don_returned", info, None, allow_llm=False, catalog=catalog
            )
            if pending and pending.ops:
                _run_pending_effect(state, pending, catalog)
                if _pending_interactive(state):
                    return True
                rule_process(state)
                break
    return False


def has_continuous_protection(
    state: MatchState,
    seat: int,
    iid: str,
    kind: str,
    catalog: CatalogFn,
) -> bool:
    """Live-evaluate continuous cannot_be_ko / cannot_be_rested auras on a Character."""
    from battle.effect_library import get_abilities, ability_is_runnable

    player = state.player(seat)
    inst = next((c for c in player.characters if c.iid == iid), None)
    if not inst:
        return False
    if kind == "cannot_be_ko" and getattr(inst, "cannot_be_ko", False):
        return True
    if kind == "cannot_be_rested" and getattr(inst, "cannot_be_rested", False):
        return True
    if kind == "cannot_be_removed" and getattr(inst, "cannot_be_removed", False):
        return True
    my_turn = state.turn_seat == seat
    for timing in ("your_turn", "opponent_turn"):
        if timing == "your_turn" and not my_turn:
            continue
        if timing == "opponent_turn" and my_turn:
            continue
        for ability in get_abilities(inst.card_id, timing):
            if not ability_is_runnable(ability):
                continue
            if ability.get("on_opp_blocker") or ability.get("on_opp_blocker_or_event"):
                continue
            ops = ability.get("ops") or []
            if not any(str(o.get("op") or "") == kind for o in ops):
                continue
            if not _ability_board_conditions_ok(
                state, seat, ability, catalog, don_attached=int(inst.don_attached or 0), source_iid=iid
            ):
                continue
            return True
    return False


def _clear_turn_duration_effects(state: MatchState) -> None:
    """6-6-1-2 / 6-6-1-3: clear this-turn power mods and battle buffs."""
    ending_seat = state.turn_seat
    for p in state.players:
        p.leader_power_mod = 0
        p.attack_active_iids.clear()
        if hasattr(p, "attacked_this_turn_iids"):
            p.attacked_this_turn_iids.clear()
        p.deny_blocker.clear()
        p.replace_battle_ko = False
        p.cannot_take_life = False
        p.leader_effects_negated = False
        p.leader_effects_negated_until_end = [
            e for e in (p.leader_effects_negated_until_end or []) if int(e.get("expire_seat", -1)) != ending_seat
        ]
        p.cannot_play_rules.clear()
        p.deny_attack_iids.clear()
        p.deny_attack_leader = False
        p.deny_rest_iids.clear()
        p.temp_hand_cost_mods.clear()
        p.cannot_attack_opp_leader = False
        p.untap_on_char_battle = False
        p.draw_on_event_rules = []
        p.event_activated_costs = []
        p.cannot_attack_char_base_cost_lte = None
        p.pending_end_of_turn_ops = []
        p.leader_turn_keywords = []
        # until_opp_turn_end: expires at the restricted / named End Phase seat.
        if p.seat == ending_seat:
            p.deny_attack_until_opp_end_iids.clear()
            p.deny_attack_leader_until_opp_end = False
            p.deny_rest_until_opp_end_iids.clear()
        p.leader_power_until_end = [
            e for e in (p.leader_power_until_end or []) if int(e.get("expire_seat", -1)) != ending_seat
        ]
        p.leader_keywords_until_end = [
            e for e in (p.leader_keywords_until_end or []) if int(e.get("expire_seat", -1)) != ending_seat
        ]
        kept_tax: list[dict[str, Any]] = []
        for rule in p.attack_tax_rules:
            dur = str(rule.get("duration") or "until_opp_turn_end")
            if dur == "turn":
                continue
            if dur == "until_opp_turn_end" and p.seat == ending_seat:
                continue
            kept_tax.append(rule)
        p.attack_tax_rules = kept_tax
        for ch in p.characters:
            ch.power_mod = 0
            ch.base_power_override = None
            ch.cannot_be_ko = False
            ch.effects_negated = False
            ch.effects_negated_until_end = [
                e for e in (ch.effects_negated_until_end or []) if int(e.get("expire_seat", -1)) != ending_seat
            ]
            ch.cannot_attack = False
            ch.cost_mod = 0
            ch.turn_keywords.clear()
            ch.turn_attributes.clear()
            ch.power_until_end = [
                e for e in (ch.power_until_end or []) if int(e.get("expire_seat", -1)) != ending_seat
            ]
            ch.keywords_until_end = [
                e for e in (ch.keywords_until_end or []) if int(e.get("expire_seat", -1)) != ending_seat
            ]
            # power_override lasts until start of your next turn — cleared in _begin_turn only.
            # taunt is continuous from card text — leave flag; legal_actions re-checks abilities.
    if state.attack:
        state.attack.counter_buffs.clear()


def _character_denied_attack(player: PlayerState, iid: str) -> bool:
    return iid in player.deny_attack_iids or iid in player.deny_attack_until_opp_end_iids


def _leader_denied_attack(player: PlayerState) -> bool:
    return bool(player.deny_attack_leader or player.deny_attack_leader_until_opp_end)


def _character_denied_rest(player: PlayerState, iid: str) -> bool:
    if iid in player.deny_rest_iids or iid in player.deny_rest_until_opp_end_iids:
        return True
    inst = next((c for c in player.characters if c.iid == iid), None)
    if inst is None:
        inst = next((s for s in (getattr(player, "stages", None) or []) if s.iid == iid), None)
    return bool(inst is not None and getattr(inst, "cannot_be_rested", False))


def _clear_battle_deny_blocker(state: MatchState) -> None:
    for p in state.players:
        p.deny_blocker = [d for d in p.deny_blocker if str(d.get("duration")) != "battle"]
        p.leader_power_until_end = [
            e for e in (p.leader_power_until_end or []) if str(e.get("expire_kind") or "") != "battle"
        ]
        for ch in p.characters:
            ch.power_until_end = [
                e for e in (ch.power_until_end or []) if str(e.get("expire_kind") or "") != "battle"
            ]


def _blocker_denied(state: MatchState, attacker_seat: int, blocker: CardInst, catalog: CatalogFn) -> bool:
    """True if attacker's deny_blocker effects prevent this blocker from activating."""
    atk = state.player(attacker_seat)
    if not atk.deny_blocker:
        return False
    power = inst_power(state, state.other(attacker_seat), blocker.iid, catalog)
    info = catalog(blocker.card_id) or {}
    try:
        base_cost = int(info.get("cost") or info.get("cost_en") or 0)
    except (TypeError, ValueError):
        base_cost = 0
    attack = state.attack
    attacker_is_leader = bool(attack and attack.attacker_seat == attacker_seat and attack.attacker_iid == "leader")
    for rule in atk.deny_blocker:
        if rule.get("when_leader_attacks") and not attacker_is_leader:
            continue
        want_atk = str(rule.get("when_attacker_iid") or "").strip()
        if want_atk:
            if not attack or attack.attacker_seat != attacker_seat:
                continue
            got = str(attack.attacker_iid or "")
            if want_atk == "leader":
                if got != "leader":
                    continue
            elif got != want_atk:
                continue
        rule_tid = str(rule.get("target_iid") or "").strip()
        if rule_tid and rule_tid != blocker.iid:
            continue
        if rule.get("power_lte") is not None and power > int(rule["power_lte"]):
            continue
        if rule.get("power_gte") is not None and power < int(rule["power_gte"]):
            continue
        if rule.get("cost_lte") is not None and base_cost > int(rule["cost_lte"]):
            continue
        if rule.get("cost_gte") is not None and base_cost < int(rule["cost_gte"]):
            continue
        if rule.get("cost_eq") is not None and base_cost != int(rule["cost_eq"]):
            continue
        if rule.get("base_cost_lte") is not None and base_cost > int(rule["base_cost_lte"]):
            continue
        if rule.get("base_cost_gte") is not None and base_cost < int(rule["base_cost_gte"]):
            continue
        return True
    return False


def _continue_end_phase(state: MatchState, catalog: CatalogFn) -> dict[str, Any]:
    """Advance 6-6 end phase steps until cleanup completes or interaction pauses."""
    while state.status == "playing" and state.phase == "end":
        if _pending_interactive(state):
            state.touch()
            return {"ok": True}
        step = state.end_phase_step or "your_end"
        if step == "your_end":
            # 6-6-1-1: turn player's 【我方的回合结束时】
            if _fire_board_timing(state, state.turn_seat, rule_timings.END_OF_YOUR_TURN, catalog):
                state.touch()
                return {"ok": True}
            # Event/Character ops queued with at_end_of_turn (e.g. P-058, OP13-066).
            ending = state.player(state.turn_seat)
            queued = list(getattr(ending, "pending_end_of_turn_ops", None) or [])
            if queued:
                ending.pending_end_of_turn_ops = []
                from battle.effects import apply_ops

                apply_ops(state, state.turn_seat, queued, catalog)
                if _pending_interactive(state):
                    state.touch()
                    return {"ok": True}
                rule_process(state)
                if state.status != "playing":
                    return {"ok": True}
            state.end_phase_step = "opp_end"
            continue
        if step == "opp_end":
            # then non-turn player's 【对方的回合结束时】
            if _fire_board_timing(state, state.other(state.turn_seat), rule_timings.END_OF_OPPONENT_TURN, catalog):
                state.touch()
                return {"ok": True}
            state.end_phase_step = "cleanup"
            continue
        if step == "cleanup":
            _clear_turn_duration_effects(state)
            rule_process(state)
            if state.status != "playing":
                return {"ok": True}
            ending = state.player(state.turn_seat)
            ending.turns_completed += 1
            nxt = state.other(state.turn_seat)
            if nxt == state.first_seat:
                state.turn_number += 1
            state.turn_seat = nxt
            state.end_phase_step = None
            state.add_log("play.log.turn_passes", name=state.player(nxt).username)
            _begin_turn(state, nxt, catalog)
            rule_process(state)
            return {"ok": True}
        # Unknown step — bail to next turn
        state.end_phase_step = "cleanup"
    return {"ok": True}


def _resume_end_phase_if_needed(state: MatchState, catalog: CatalogFn) -> None:
    if state.status == "playing" and state.phase == "end" and not _pending_interactive(state):
        _continue_end_phase(state, catalog)


def inst_effects_negated(player, source_iid: str) -> bool:
    """True if Leader/Character effects are currently negated (this turn or until-opp-end)."""
    if source_iid == "leader" or str(source_iid).startswith("leader-"):
        if player.leader_effects_negated:
            return True
        return bool(player.leader_effects_negated_until_end)
    inst = next((c for c in player.characters if c.iid == source_iid), None)
    if not inst:
        return False
    if inst.effects_negated:
        return True
    return bool(getattr(inst, "effects_negated_until_end", None))


def inst_power(state: MatchState, seat: int, iid: str, catalog: CatalogFn) -> int:
    player = state.player(seat)
    # 6-5-5-2: attached DON!! only raise power during that player's turn
    don_counts = state.turn_seat == seat
    battle_buff = 0
    if state.attack and state.attack.attacker_seat != seat:
        battle_buff = int(state.attack.counter_buffs.get(iid, 0))
    if iid == "leader":
        don = player.leader_don * 1000 if don_counts else 0
        until = sum(int(e.get("amount") or 0) for e in (player.leader_power_until_end or []))
        cont_lead = _continuous_leader_base_power(state, seat, catalog)
        printed = cont_lead if cont_lead is not None else printed_power(catalog(player.leader_card_id))
        base = printed + player.leader_power_mod + until + don + battle_buff
        return base + _static_power_bonus(state, seat, "leader", player.leader_card_id, player.leader_don, catalog)
    inst = next((c for c in player.characters if c.iid == iid), None)
    if not inst:
        return 0
    if inst.power_override is not None:
        return int(inst.power_override) + battle_buff
    don = inst.don_attached * 1000 if don_counts else 0
    printed = printed_power(catalog(inst.card_id))
    if inst.base_power_override is not None:
        base_printed = int(inst.base_power_override)
    else:
        cont = _continuous_base_power(state, seat, inst, catalog)
        base_printed = cont if cont is not None else printed
    until = sum(int(e.get("amount") or 0) for e in (inst.power_until_end or []))
    base = base_printed + inst.power_mod + until + don + battle_buff
    total = base + _static_power_bonus(state, seat, iid, inst.card_id, inst.don_attached, catalog)
    total += _foe_character_power_aura(state, seat, iid, catalog)
    return total


def _continuous_base_power(
    state: MatchState,
    seat: int,
    inst: CardInst,
    catalog: CatalogFn,
) -> int | None:
    """Live continuous base-power rewrites (self auras + board all-trait auras)."""
    from battle.effect_library import ability_is_runnable, continuous_base_power_abilities, get_abilities

    player = state.player(seat)
    info = catalog(inst.card_id)
    my_turn = state.turn_seat == seat
    best: int | None = None

    def _op_applies_to_victim(op: dict[str, Any], *, src_iid: str) -> int | None:
        kind = str(op.get("op") or "")
        if kind == "continuous_base_from_own_leader_printed":
            return printed_power(catalog(player.leader_card_id))
        if kind not in {"set_base_power", "continuous_set_base_power"}:
            return None
        tk = str(op.get("target_kind") or "self").strip().lower()
        amt = int(op.get("amount") or 0)
        if amt <= 0:
            return None
        if tk in {"self", ""}:
            if src_iid != inst.iid:
                return None
        elif tk in {"own_character", "own_characters"}:
            # Board-wide rewrite needs all / trait / name filter; bare own_character on self only.
            if not (op.get("all") or op.get("trait_contains") or op.get("name_contains")):
                if src_iid != inst.iid:
                    return None
        elif tk == "leader":
            return None
        else:
            return None
        trait = str(op.get("trait_contains") or "").strip()
        if trait and not _info_has_trait(info, trait):
            return None
        name_raw = str(op.get("name_contains") or "").strip()
        if name_raw and not _card_name_has(info, name_raw.split("|")[0]):
            # Allow multi-alias via any part.
            parts = [p.strip() for p in name_raw.replace("|", "/").split("/") if p.strip()]
            if parts and not any(_card_name_has(info, p) for p in parts):
                return None
        if op.get("require_trigger") and not card_has_trigger(info):
            return None
        if op.get("base_power_eq") is not None:
            if printed_power(info) != int(op["base_power_eq"]):
                return None
        return amt

    for ability in continuous_base_power_abilities(inst.card_id, info):
        timing = str(ability.get("timing") or "")
        if timing == "your_turn" and not my_turn:
            continue
        if timing == "opponent_turn" and my_turn:
            continue
        if not _ability_board_conditions_ok(
            state,
            seat,
            ability,
            catalog,
            don_attached=int(inst.don_attached or 0),
            source_iid=inst.iid,
        ):
            continue
        if ability.get("require_hand_lte") is not None and len(player.hand) > int(ability["require_hand_lte"]):
            continue
        if ability.get("require_hand_gte") is not None and len(player.hand) < int(ability["require_hand_gte"]):
            continue
        for op in ability.get("ops") or []:
            amt = _op_applies_to_victim(op, src_iid=inst.iid)
            if amt is not None:
                best = amt if best is None else max(best, amt)

    # Board auras (e.g. OP13-084: all Five Elders base → 7000).
    sources: list[tuple[str, str, int]] = [
        ("leader", player.leader_card_id, int(player.leader_don or 0)),
        *[(c.iid, c.card_id, int(c.don_attached or 0)) for c in player.characters],
        *[(s.iid, s.card_id, 0) for s in player.stages],
    ]
    for src_iid, cid, don in sources:
        if src_iid == inst.iid:
            continue
        for timing in ("your_turn", "opponent_turn"):
            if timing == "your_turn" and not my_turn:
                continue
            if timing == "opponent_turn" and my_turn:
                continue
            for ability in get_abilities(cid, timing):
                if not ability_is_runnable(ability):
                    continue
                if not any(
                    o.get("op") in {"set_base_power", "continuous_set_base_power"}
                    and (
                        o.get("all")
                        or str(o.get("target_kind") or "") in {"own_character", "own_characters"}
                    )
                    for o in (ability.get("ops") or [])
                ):
                    continue
                if not _ability_board_conditions_ok(
                    state, seat, ability, catalog, don_attached=don, source_iid=src_iid
                ):
                    continue
                for op in ability.get("ops") or []:
                    amt = _op_applies_to_victim(op, src_iid=src_iid)
                    if amt is not None:
                        best = amt if best is None else max(best, amt)
    return best


def _continuous_leader_base_power(
    state: MatchState,
    seat: int,
    catalog: CatalogFn,
) -> int | None:
    """Live continuous Leader base-power rewrite from own board (e.g. OP15-092 trash≥20)."""
    from battle.effect_library import ability_is_runnable, get_abilities

    player = state.player(seat)
    my_turn = state.turn_seat == seat
    best: int | None = None
    sources: list[tuple[str, str, int]] = [
        ("leader", player.leader_card_id, int(player.leader_don or 0)),
        *[(c.iid, c.card_id, int(c.don_attached or 0)) for c in player.characters],
        *[(s.iid, s.card_id, 0) for s in player.stages],
    ]
    for src_iid, cid, don in sources:
        for timing in ("your_turn", "opponent_turn"):
            if timing == "your_turn" and not my_turn:
                continue
            if timing == "opponent_turn" and my_turn:
                continue
            for ability in get_abilities(cid, timing):
                if not ability_is_runnable(ability):
                    continue
                if not any(
                    o.get("op") in {"set_base_power", "continuous_set_base_power"}
                    and str(o.get("target_kind") or "") == "leader"
                    for o in (ability.get("ops") or [])
                ):
                    continue
                if not _ability_board_conditions_ok(
                    state, seat, ability, catalog, don_attached=don, source_iid=src_iid
                ):
                    continue
                for op in ability.get("ops") or []:
                    if op.get("op") not in {"set_base_power", "continuous_set_base_power"}:
                        continue
                    if str(op.get("target_kind") or "") != "leader":
                        continue
                    amt = int(op.get("amount") or 0)
                    if amt > 0:
                        best = amt if best is None else max(best, amt)
    return best


def _static_power_bonus(
    state: MatchState,
    seat: int,
    iid: str,
    card_id: str,
    don_attached: int,
    catalog: CatalogFn,
) -> int:
    """Continuous [DON!! xN] self-power from ability text / effect library."""
    from battle.effect_library import static_power_abilities

    player = state.player(seat)
    foe = state.player(state.other(seat))
    info = catalog(card_id)
    my_turn = state.turn_seat == seat
    bonus = 0
    for ability in static_power_abilities(card_id, info):
        timing = str(ability.get("timing") or "")
        if timing == "your_turn" and not my_turn:
            continue
        if timing == "opponent_turn" and my_turn:
            continue
        if not _ability_board_conditions_ok(
            state, seat, ability, catalog, don_attached=don_attached
        ):
            continue
        for op in ability.get("ops") or []:
            if op.get("op") == "buff_self":
                amt = int(op.get("amount") or 0)
                if op.get("per_rested_don"):
                    step = max(1, int(op["per_rested_don"]))
                    amt *= int(player.don_rested or 0) // step
                elif op.get("per_trash_cards"):
                    step = max(1, int(op["per_trash_cards"]))
                    amt *= len(player.trash) // step
                elif op.get("per_trash_events"):
                    step = max(1, int(op["per_trash_events"]))
                    ev = 0
                    for tid in player.trash:
                        tinfo = catalog(tid)
                        if card_type_of(tinfo) == "event":
                            ev += 1
                    amt *= ev // step
                elif op.get("per_distinct_own_char_names"):
                    names = set()
                    for ch in player.characters:
                        ninfo = catalog(ch.card_id) or {}
                        # HK paper uses Chinese card names; prefer name then name_en.
                        # Normalize middle-dot variants so 「蒙其・D・魯夫」==「蒙其·D·鲁夫」.
                        raw = str(ninfo.get("name") or ninfo.get("name_en") or ch.card_id).strip().lower()
                        for a, b in (("・", "."), ("·", "."), ("．", "."), (" ", ""), ("-", ".")):
                            raw = raw.replace(a, b)
                        if raw:
                            names.add(raw)
                    amt *= max(0, len(names))
                elif op.get("per_own_chars"):
                    step = max(1, int(op["per_own_chars"]))
                    amt *= len(player.characters) // step
                bonus += amt
    # Continuous board auras from other own cards (stages / characters / leader).
    bonus += _board_power_aura_bonus(state, seat, iid, card_id, catalog)
    return bonus


def _aura_cost_ok(
    _state: MatchState,
    _seat: int,
    target_iid: str,
    target_info: dict[str, Any],
    op: dict[str, Any],
    _catalog: CatalogFn,
    _player: PlayerState,
) -> bool:
    """Honor cost_lte / cost_eq / cost_gte / base_cost_* on live board auras (printed cost)."""
    if target_iid == "leader":
        return not any(
            op.get(k) is not None
            for k in ("cost_lte", "cost_eq", "cost_gte", "base_cost_lte", "base_cost_gte")
        )
    printed = printed_cost(target_info)
    cost = printed
    if op.get("cost_lte") is not None and cost > int(op["cost_lte"]):
        return False
    if op.get("cost_gte") is not None and cost < int(op["cost_gte"]):
        return False
    if op.get("cost_eq") is not None and cost != int(op["cost_eq"]):
        return False
    if op.get("base_cost_lte") is not None and printed > int(op["base_cost_lte"]):
        return False
    if op.get("base_cost_gte") is not None and printed < int(op["base_cost_gte"]):
        return False
    return True


def _board_power_aura_bonus(
    state: MatchState,
    seat: int,
    target_iid: str,
    target_card_id: str,
    catalog: CatalogFn,
) -> int:
    """Live +power from own board your_turn/opponent_turn buff_all_own / buff-leader auras."""
    from battle.effect_library import get_abilities, ability_is_runnable

    player = state.player(seat)
    my_turn = state.turn_seat == seat
    bonus = 0
    sources: list[tuple[str, str, int]] = [
        ("leader", player.leader_card_id, int(player.leader_don or 0)),
    ]
    sources.extend((c.iid, c.card_id, int(c.don_attached or 0)) for c in player.characters)
    sources.extend((s.iid, s.card_id, 0) for s in player.stages)
    target_info = catalog(target_card_id)
    for src_iid, src_cid, don_att in sources:
        for timing in ("your_turn", "opponent_turn"):
            if timing == "your_turn" and not my_turn:
                continue
            if timing == "opponent_turn" and my_turn:
                continue
            for ability in get_abilities(src_cid, timing):
                if not ability_is_runnable(ability):
                    continue
                if not _ability_board_conditions_ok(
                    state, seat, ability, catalog, don_attached=don_att, source_iid=src_iid
                ):
                    continue
                for op in ability.get("ops") or []:
                    kind = str(op.get("op") or "")
                    amt = int(op.get("amount") or 0)
                    if not amt:
                        continue
                    board_wide = bool(
                        op.get("all")
                        or op.get("name_contains")
                        or op.get("trait_contains")
                        or op.get("trait_includes")
                        or op.get("trait_all")
                        or op.get("trait_any")
                    )
                    if src_iid == target_iid:
                        if kind == "buff_all_own":
                            if op.get("exclude_self"):
                                continue
                        elif kind == "buff":
                            if not board_wide:
                                continue
                        else:
                            continue
                    if kind == "buff_all_own":
                        if target_iid == "leader":
                            if not op.get("include_leader", True):
                                continue
                            if not _op_traits_ok(target_info, op):
                                continue
                        else:
                            if not _op_traits_ok(target_info, op):
                                continue
                            if op.get("exclude_self") and src_iid == target_iid:
                                continue
                        if not _aura_cost_ok(state, seat, target_iid, target_info, op, catalog, player):
                            continue
                        bonus += amt
                    elif kind == "buff":
                        tk = str(op.get("target_kind") or "")
                        if target_iid == "leader":
                            if tk not in {"leader", "own_leader_or_character"}:
                                continue
                        else:
                            if tk not in {"own_character", "own_leader_or_character", "own_characters"}:
                                continue
                            if not board_wide:
                                # targeted buffs are not live auras
                                continue
                        needle = str(op.get("name_contains") or "").strip()
                        if needle and not any(
                            _card_name_has(target_info, p) for p in needle.split("|") if p.strip()
                        ):
                            continue
                        trait = str(op.get("trait_contains") or op.get("trait_includes") or "").strip()
                        if (trait or op.get("trait_all") or op.get("trait_any")) and not _op_traits_ok(
                            target_info, op
                        ):
                            continue
                        if not _aura_cost_ok(state, seat, target_iid, target_info, op, catalog, player):
                            continue
                        bonus += amt
    return bonus


def _foe_character_power_aura(
    state: MatchState,
    seat: int,
    target_iid: str,
    catalog: CatalogFn,
) -> int:
    """Live −power from opponent's board auras (e.g. OP09-004 Jack: all opp Characters −1000)."""
    if target_iid == "leader":
        return 0
    from battle.effect_library import ability_is_runnable, get_abilities

    foe_seat = state.other(seat)
    foe = state.player(foe_seat)
    bonus = 0
    sources: list[tuple[str, str, int]] = [
        ("leader", foe.leader_card_id, int(foe.leader_don or 0)),
    ]
    sources.extend((c.iid, c.card_id, int(c.don_attached or 0)) for c in foe.characters)
    sources.extend((s.iid, s.card_id, 0) for s in foe.stages)
    for src_iid, src_cid, don_att in sources:
        for timing in ("your_turn", "opponent_turn"):
            # Timing is relative to the aura controller (foe).
            if timing == "your_turn" and state.turn_seat != foe_seat:
                continue
            if timing == "opponent_turn" and state.turn_seat == foe_seat:
                continue
            for ability in get_abilities(src_cid, timing):
                if not ability_is_runnable(ability):
                    continue
                if not _ability_board_conditions_ok(
                    state, foe_seat, ability, catalog, don_attached=don_att, source_iid=src_iid
                ):
                    continue
                for op in ability.get("ops") or []:
                    if str(op.get("op") or "") != "buff":
                        continue
                    amt = int(op.get("amount") or 0)
                    if amt >= 0:
                        continue
                    tk = str(op.get("target_kind") or "").strip().lower()
                    if tk not in {"opponent_character", "opponent_characters", "all_opponent_characters"}:
                        continue
                    # Continuous all-opp Character debuff (Jack / rested auras).
                    if not (op.get("all") or op.get("optional") is False):
                        continue
                    bonus += amt
    return bonus


def _don_on_field(player: PlayerState) -> int:
    """Total DON!! cards on a player's field (cost area + attached)."""
    attached = int(player.leader_don or 0) + sum(int(c.don_attached or 0) for c in player.characters)
    return int(player.don_active or 0) + int(player.don_rested or 0) + attached


def don_deck_cap(player: PlayerState) -> int:
    """Printed DON!! deck size (10 unless a leader rule shrinks it)."""
    n = int(getattr(player, "don_deck_size", 0) or 0)
    return n if n > 0 else 10


def don_deck_room(player: PlayerState) -> int:
    return max(0, don_deck_cap(player) - int(player.don_given or 0))


def _leader_don_deck_size(leader_card_id: str) -> int:
    from battle.effect_library import get_abilities

    cap = 10
    for ab in get_abilities(leader_card_id) or []:
        for op in ab.get("ops") or []:
            if str(op.get("op") or "") == "rule_don_deck_size":
                try:
                    cap = max(1, min(10, int(op.get("count") or 10)))
                except (TypeError, ValueError):
                    cap = 10
    return cap


def _card_name_has(info: dict[str, Any], needle: str) -> bool:
    names = f"{info.get('name') or ''} {info.get('name_en') or ''}".lower()
    return (needle or "").strip().lower() in names


def _ability_board_conditions_ok(
    state: MatchState,
    seat: int,
    ability: dict[str, Any],
    catalog: CatalogFn,
    *,
    don_attached: int = 0,
    source_iid: str | None = None,
) -> bool:
    """Shared gates for continuous cost / hand-cost abilities."""
    player = state.player(seat)
    foe = state.player(state.other(seat))
    my_turn = state.turn_seat == seat
    if ability.get("require_your_turn") and not my_turn:
        return False
    if ability.get("require_opponent_turn") and my_turn:
        return False
    if ability.get("require_all_don_rested"):
        # All DON!! on field are rested ⇒ no active DON!! remaining.
        if int(player.don_active or 0) > 0:
            return False
    if ability.get("require_source_active"):
        src = None
        if source_iid and source_iid != "leader":
            src = next((c for c in player.characters if c.iid == source_iid), None)
        if src is None or bool(getattr(src, "rested", False)):
            return False
    if ability.get("require_source_rested") or ability.get("while_rested"):
        src = None
        if source_iid and source_iid != "leader":
            src = next((c for c in player.characters if c.iid == source_iid), None)
            if src is None:
                src = next((s for s in player.stages if s.iid == source_iid), None)
        if src is None or not bool(getattr(src, "rested", False)):
            return False
    if ability.get("require_source_power_gte") is not None:
        need = int(ability["require_source_power_gte"])
        if not source_iid or source_iid == "leader":
            return False
        if inst_power(state, seat, source_iid, catalog) < need:
            return False
    if ability.get("require_source_cost_gte") is not None:
        need = int(ability["require_source_cost_gte"])
        if not source_iid or source_iid == "leader":
            return False
        src = next((c for c in player.characters if c.iid == source_iid), None)
        if src is None:
            return False
        if effective_character_cost(state, seat, src, catalog) < need:
            return False
    if ability.get("require_played_this_turn"):
        # Proxy: summoning_sick stays True until next refresh → played this turn.
        src = None
        if source_iid and source_iid != "leader":
            src = next((c for c in player.characters if c.iid == source_iid), None)
        if src is None:
            # Fallback: any matching source card_id on ability summary is not available;
            # require at least one summoning-sick character when source unknown is too loose.
            return False
        if not src.summoning_sick:
            return False
    if ability.get("require_activated_this_turn"):
        # Once-per-turn activate already happened this turn.
        if source_iid == "leader":
            if not player.leader_once_used:
                return False
        else:
            src = None
            if source_iid:
                src = next((c for c in player.characters if c.iid == source_iid), None)
            if src is None or not src.once_used:
                return False
    need_don = int(ability.get("require_don_attached_gte") or 0)
    if don_attached < need_don:
        return False
    if ability.get("require_hand_gte") is not None and len(player.hand) < int(ability["require_hand_gte"]):
        return False
    if ability.get("require_hand_lte") is not None and len(player.hand) > int(ability["require_hand_lte"]):
        return False
    if ability.get("require_hand_trashed_by_effect_this_turn") and not bool(
        getattr(player, "hand_trashed_by_effect_this_turn", False)
    ):
        return False
    if ability.get("require_opp_life_left_this_turn") and not bool(
        getattr(player, "opp_life_left_this_turn", False)
    ):
        return False
    if ability.get("require_opp_hand_gte") is not None and len(foe.hand) < int(ability["require_opp_hand_gte"]):
        return False
    if ability.get("require_opp_hand_lte") is not None and len(foe.hand) > int(ability["require_opp_hand_lte"]):
        return False
    if ability.get("require_chars_gte") is not None and len(player.characters) < int(ability["require_chars_gte"]):
        return False
    if ability.get("require_chars_lte") is not None and len(player.characters) > int(ability["require_chars_lte"]):
        return False
    if ability.get("require_no_other_name"):
        name = str(ability.get("require_no_other_name") or "").strip()
        if name:
            opts = [x.strip() for x in name.split("|") if x.strip()] or [name]
            base_eq = ability.get("require_no_other_base_cost_eq")
            n = 0
            for c in player.characters:
                if not any(_card_name_has(catalog(c.card_id), o) for o in opts):
                    continue
                if base_eq is not None:
                    try:
                        if int(printed_cost(catalog(c.card_id))) != int(base_eq):
                            continue
                    except (TypeError, ValueError):
                        continue
                n += 1
            if n > 1:
                return False
    if ability.get("require_life_gte") is not None and len(player.life) < int(ability["require_life_gte"]):
        return False
    if ability.get("require_life_lte") is not None and len(player.life) > int(ability["require_life_lte"]):
        return False
    if ability.get("require_life_less_than_opponent") and not (len(player.life) < len(foe.life)):
        return False
    if ability.get("require_life_lte_opponent") and not (len(player.life) <= len(foe.life)):
        return False
    if ability.get("require_other_chars_trait"):
        trait = str(ability["require_other_chars_trait"])
        opts = [t.strip() for t in trait.split("|") if t.strip()] or [trait]
        src = source_iid
        color = str(ability.get("require_chars_color") or "").strip()
        excl = str(ability.get("require_other_exclude_name") or "").strip()
        found = False
        for c in player.characters:
            if src and c.iid == src:
                continue
            info = catalog(c.card_id)
            if not any(_info_has_trait(info, t) for t in opts):
                continue
            if color and not _info_has_color(info, color):
                continue
            if excl and any(_card_name_has(info, p) for p in excl.split("|") if p.strip()):
                continue
            found = True
            break
        if not found:
            return False
    elif ability.get("require_chars_color"):
        color = str(ability["require_chars_color"]).strip()
        if color and not any(_info_has_color(catalog(c.card_id), color) for c in player.characters):
            return False
    if ability.get("require_don_active_lte") is not None:
        if int(player.don_active or 0) > int(ability["require_don_active_lte"]):
            return False
    if ability.get("require_deck_lte") is not None and len(player.deck) > int(ability["require_deck_lte"]):
        return False
    if ability.get("require_trash_gte") is not None and len(player.trash) < int(ability["require_trash_gte"]):
        return False
    if ability.get("require_trash_events_gte") is not None:
        n = sum(1 for cid in player.trash if card_type_of(catalog(cid)) == "event")
        if n < int(ability["require_trash_events_gte"]):
            return False
    if ability.get("require_opp_rested_chars_gte") is not None:
        rested = sum(1 for c in foe.characters if c.rested)
        if rested < int(ability["require_opp_rested_chars_gte"]):
            return False
    if ability.get("require_don_field_deficit_gte") is not None:
        if _don_on_field(player) > _don_on_field(foe) - int(ability["require_don_field_deficit_gte"]):
            return False
    if ability.get("require_don_field_gte") is not None:
        if _don_on_field(player) < int(ability["require_don_field_gte"]):
            return False
    if ability.get("require_don_rested_gte") is not None:
        if int(player.don_rested or 0) < int(ability["require_don_rested_gte"]):
            return False
    if ability.get("require_opp_don_field_gte") is not None:
        if _don_on_field(foe) < int(ability["require_opp_don_field_gte"]):
            return False
    if ability.get("require_either_don_field_gte") is not None:
        need = int(ability["require_either_don_field_gte"])
        if _don_on_field(player) < need and _don_on_field(foe) < need:
            return False
    if ability.get("require_either_don_field_lte") is not None:
        need = int(ability["require_either_don_field_lte"])
        if _don_on_field(player) > need and _don_on_field(foe) > need:
            return False
    if ability.get("require_either_life_lte") is not None:
        need = int(ability["require_either_life_lte"])
        if len(player.life) > need and len(foe.life) > need:
            return False
    if ability.get("require_either_life_gte") is not None:
        need = int(ability["require_either_life_gte"])
        if len(player.life) < need and len(foe.life) < need:
            return False
    if ability.get("require_don_field_lte") is not None:
        if _don_on_field(player) > int(ability["require_don_field_lte"]):
            return False
    if ability.get("require_turn_gte") is not None:
        # Paper 「自己第N回合之後」= this player's Nth turn or later (turns_completed is ended turns).
        my_turn_n = int(player.turns_completed or 0) + 1
        if my_turn_n < int(ability["require_turn_gte"]):
            return False
    if ability.get("require_don_field_0_or_gte") is not None:
        n = _don_on_field(player)
        gte = int(ability["require_don_field_0_or_gte"])
        if not (n == 0 or n >= gte):
            return False
    if ability.get("require_opp_char_power_gte") is not None:
        need = int(ability["require_opp_char_power_gte"])
        if not any(inst_power(state, state.other(seat), c.iid, catalog) >= need for c in foe.characters):
            return False
    if ability.get("require_own_name_gte") is not None:
        names = str(ability.get("require_own_name_contains") or "")
        name_opts = [x for x in names.split("|") if x] if names else []
        need_n = int(ability["require_own_name_gte"])
        n = 0
        for c in player.characters:
            cinfo = catalog(c.card_id)
            if name_opts and not any(_card_name_has(cinfo, nm) for nm in name_opts):
                continue
            n += 1
        if n < need_n:
            return False
    if ability.get("require_given_don_gte") is not None:
        given = int(player.leader_don or 0) + sum(int(c.don_attached or 0) for c in player.characters)
        if given < int(ability["require_given_don_gte"]):
            return False
    if ability.get("require_opp_given_don_gte") is not None:
        given = int(foe.leader_don or 0) + sum(int(c.don_attached or 0) for c in foe.characters)
        if given < int(ability["require_opp_given_don_gte"]):
            return False
    if ability.get("require_chars_base_cost_count_gte") is not None:
        need_cost = int(ability.get("require_chars_base_cost_gte") or 0)
        need_n = int(ability["require_chars_base_cost_count_gte"])
        n = 0
        for c in player.characters:
            try:
                n += 1 if printed_cost(catalog(c.card_id)) >= need_cost else 0
            except Exception:
                pass
        if n < need_n:
            return False
    if ability.get("require_chars_base_power_count_gte") is not None:
        need_pow = int(ability.get("require_chars_base_power_gte") or 0)
        need_n = int(ability["require_chars_base_power_count_gte"])
        n = 0
        for c in player.characters:
            try:
                n += 1 if printed_power(catalog(c.card_id)) >= need_pow else 0
            except Exception:
                pass
        if n < need_n:
            return False
    if ability.get("require_don_active_gte") is not None:
        if int(player.don_active or 0) < int(ability["require_don_active_gte"]):
            return False
    if ability.get("require_own_name_on_field"):
        needle = str(ability["require_own_name_on_field"]).strip()
        if needle:
            needles = [x.strip() for x in needle.split("|") if x.strip()] or [needle]
            found = any(_card_name_has(catalog(player.leader_card_id), n) for n in needles)
            if not found:
                found = any(
                    any(_card_name_has(catalog(c.card_id), n) for n in needles) for c in player.characters
                )
            if not found:
                found = any(
                    any(_card_name_has(catalog(s.card_id), n) for n in needles)
                    for s in (getattr(player, "stages", None) or [])
                )
            if not found:
                return False
    if ability.get("require_own_name_all"):
        # Every entry (pipe = OR aliases) must match at least one own Character/Leader.
        raw = ability.get("require_own_name_all")
        needles: list[str] = []
        if isinstance(raw, list):
            needles = [str(x).strip() for x in raw if str(x).strip()]
        elif isinstance(raw, str) and raw.strip():
            needles = [x.strip() for x in raw.split(";") if x.strip()]
        need_pow = ability.get("require_chars_base_power_eq")
        for needle in needles:
            opts = [x.strip() for x in needle.split("|") if x.strip()] or [needle]
            found = False
            if need_pow is not None:
                want = int(need_pow)
                for c in player.characters:
                    info = catalog(c.card_id)
                    if printed_power(info) != want:
                        continue
                    if any(_card_name_has(info, opt) for opt in opts):
                        found = True
                        break
            else:
                pool = [catalog(player.leader_card_id)] + [catalog(c.card_id) for c in player.characters]
                found = any(_card_name_has(info, opt) for info in pool for opt in opts)
            if not found:
                return False
    elif ability.get("require_chars_base_power_eq") is not None:
        want = int(ability["require_chars_base_power_eq"])
        if not any(printed_power(catalog(c.card_id)) == want for c in player.characters):
            return False
    if ability.get("require_no_own_name_on_field"):
        needle = str(ability["require_no_own_name_on_field"]).strip()
        if needle:
            opts = [x.strip() for x in needle.split("|") if x.strip()] or [needle]
            if any(_card_name_has(catalog(c.card_id), opt) for c in player.characters for opt in opts):
                return False
    if ability.get("require_no_name_on_field"):
        needle = str(ability["require_no_name_on_field"]).strip()
        if needle:
            opts = [x.strip() for x in needle.split("|") if x.strip()] or [needle]
            for s in (seat, state.other(seat)):
                for c in state.player(s).characters:
                    if any(_card_name_has(catalog(c.card_id), opt) for opt in opts):
                        return False
    if ability.get("require_chars_base_cost_count_lte") is not None:
        need_cost = int(ability.get("require_chars_base_cost_gte") or 0)
        need_n = int(ability["require_chars_base_cost_count_lte"])
        n = 0
        for c in player.characters:
            try:
                n += 1 if printed_cost(catalog(c.card_id)) >= need_cost else 0
            except Exception:
                pass
        if n > need_n:
            return False
    if ability.get("require_own_char_cost_gte") is not None:
        gte = int(ability["require_own_char_cost_gte"])
        trait = str(ability.get("require_chars_trait") or "").strip()
        ok = False
        for c in player.characters:
            if effective_character_cost(state, seat, c, catalog) < gte:
                continue
            if trait and not _info_has_trait(catalog(c.card_id), trait):
                continue
            ok = True
            break
        if not ok:
            return False
    if ability.get("vs_leader_only") or ability.get("require_vs_leader"):
        tgt = getattr(state, "_attack_target_iid", None)
        if tgt is None and state.attack:
            tgt = state.attack.target_iid
        if tgt != "leader":
            return False
    if ability.get("require_field_char_cost_gte") is not None:
        gte = int(ability["require_field_char_cost_gte"])
        has = False
        for s in (seat, state.other(seat)):
            for c in state.player(s).characters:
                if effective_character_cost(state, s, c, catalog) >= gte:
                    has = True
                    break
            if has:
                break
        if not has:
            return False
    if ability.get("require_field_char_base_power_gte") is not None:
        gte = int(ability["require_field_char_base_power_gte"])
        has = False
        for s in (seat, state.other(seat)):
            for c in state.player(s).characters:
                try:
                    base = int(catalog(c.card_id).get("power") or catalog(c.card_id).get("power_en") or 0)
                except (TypeError, ValueError):
                    base = 0
                if base >= gte:
                    has = True
                    break
            if has:
                break
        if not has:
            return False
    if ability.get("require_field_char_power_gte") is not None:
        gte = int(ability["require_field_char_power_gte"])
        has = False
        for s in (seat, state.other(seat)):
            for c in state.player(s).characters:
                if inst_power(state, s, c.iid, catalog) >= gte:
                    has = True
                    break
            if has:
                break
        if not has:
            return False
    if ability.get("require_opp_chars_count_gte") is not None:
        need_n = int(ability["require_opp_chars_count_gte"])
        need_pow = ability.get("require_opp_chars_base_power_gte")
        if need_pow is not None:
            count = 0
            for fc in foe.characters:
                try:
                    base = int(catalog(fc.card_id).get("power") or catalog(fc.card_id).get("power_en") or 0)
                except (TypeError, ValueError):
                    base = 0
                if base >= int(need_pow):
                    count += 1
            if count < need_n:
                return False
        elif len(foe.characters) < need_n:
            return False
    if ability.get("require_chars_cost_sum_gte") is not None:
        total = 0
        for c in player.characters:
            try:
                total += int(printed_cost(catalog(c.card_id)))
            except Exception:
                pass
        if total < int(ability["require_chars_cost_sum_gte"]):
            return False
    if ability.get("require_chars_deficit_gte") is not None:
        if len(player.characters) > len(foe.characters) - int(ability["require_chars_deficit_gte"]):
            return False
    if ability.get("require_rested_cards_gte") is not None:
        rested = int(player.don_rested or 0) + sum(1 for c in player.characters if c.rested)
        if player.leader_rested:
            rested += 1
        rested += sum(1 for s in (getattr(player, "stages", None) or []) if getattr(s, "rested", False))
        if rested < int(ability["require_rested_cards_gte"]):
            return False
    if ability.get("require_opp_life_lte") is not None and len(foe.life) > int(ability["require_opp_life_lte"]):
        return False
    if ability.get("require_opp_life_gte") is not None and len(foe.life) < int(ability["require_opp_life_gte"]):
        return False
    if ability.get("require_total_life_lte") is not None:
        if len(player.life) + len(foe.life) > int(ability["require_total_life_lte"]):
            return False
    if ability.get("require_life_plus_hand_lte") is not None:
        if len(player.life) + len(player.hand) > int(ability["require_life_plus_hand_lte"]):
            return False
    if ability.get("require_rested_own_chars_gte") is not None:
        trait = str(ability.get("require_rested_own_chars_trait") or "").strip()
        opts = [t.strip() for t in trait.split("|") if t.strip()] if trait else []
        rested = 0
        for c in player.characters:
            if not c.rested:
                continue
            if opts and not any(_info_has_trait(catalog(c.card_id), t) for t in opts):
                continue
            rested += 1
        if rested < int(ability["require_rested_own_chars_gte"]):
            return False
    elif ability.get("require_rested_own_chars_trait"):
        # Trait filter without count still requires at least one matching rested Character.
        trait = str(ability["require_rested_own_chars_trait"])
        opts = [t.strip() for t in trait.split("|") if t.strip()] or [trait]
        if not any(
            c.rested and any(_info_has_trait(catalog(c.card_id), t) for t in opts) for c in player.characters
        ):
            return False
    if ability.get("require_field_chars_cost_count_gte") is not None:
        need_cost = int(ability.get("require_field_chars_cost_gte") or ability.get("require_chars_base_cost_gte") or 0)
        need_n = int(ability["require_field_chars_cost_count_gte"])
        n = 0
        for s in (seat, state.other(seat)):
            for c in state.player(s).characters:
                try:
                    if effective_character_cost(state, s, c, catalog) >= need_cost:
                        n += 1
                except Exception:
                    pass
        if n < need_n:
            return False
    if ability.get("require_own_trigger_chars_gte") is not None:
        need_n = int(ability["require_own_trigger_chars_gte"])
        n = sum(1 for c in player.characters if card_has_trigger(catalog(c.card_id)))
        if n < need_n:
            return False
    if ability.get("require_hand_only_chars_no_counter"):
        for cid in player.hand:
            info = catalog(cid)
            if card_type_of(info) != "character":
                return False
            if printed_counter(info) > 0:
                return False
    if ability.get("require_all_chars_trait"):
        if not _chars_all_have_trait(player, str(ability["require_all_chars_trait"]), catalog):
            return False
    if ability.get("require_chars_trait") and ability.get("require_chars_trait_gte") is not None:
        trait = str(ability["require_chars_trait"])
        opts = [t.strip() for t in trait.split("|") if t.strip()] or [trait]
        n = sum(
            1
            for c in player.characters
            if any(_info_has_trait(catalog(c.card_id), t) for t in opts)
        )
        if n < int(ability["require_chars_trait_gte"]):
            return False
    if ability.get("require_distinct_own_chars_trait_gte") is not None:
        trait = str(
            ability.get("require_distinct_own_chars_trait")
            or ability.get("require_chars_trait")
            or ""
        )
        opts = [t.strip() for t in trait.split("|") if t.strip()] if trait else []
        names: set[str] = set()
        for c in player.characters:
            info = catalog(c.card_id) or {}
            if opts and not any(_info_has_trait(info, t) for t in opts):
                continue
            raw = str(info.get("name") or info.get("name_en") or c.card_id).strip().lower()
            for a, b in (("・", "."), ("·", "."), ("．", "."), (" ", ""), ("-", ".")):
                raw = raw.replace(a, b)
            if raw:
                names.add(raw)
        if len(names) < int(ability["require_distinct_own_chars_trait_gte"]):
            return False
    if ability.get("require_trash_names_all"):
        # AND of OR-groups: "NameA|別名A&NameB|別名B"
        groups = [g.strip() for g in str(ability["require_trash_names_all"]).split("&") if g.strip()]
        trash_blob = " ".join(
            f"{(catalog(cid) or {}).get('name') or ''} {(catalog(cid) or {}).get('name_en') or ''}"
            for cid in player.trash
        ).lower()
        for g in groups:
            needles = [x.strip().lower() for x in g.split("|") if x.strip()]
            if needles and not any(n in trash_blob for n in needles):
                return False
    if ability.get("require_leader_trait") and not ability.get("require_leader_name_or_trait"):
        lead = catalog(player.leader_card_id)
        trait_req = str(ability["require_leader_trait"])
        # Support OR lists encoded as "A|B" (e.g. Land of Wano|Whitebeard Pirates).
        opts = [t.strip() for t in trait_req.split("|") if t.strip()] or [trait_req]
        if not any(_info_has_trait(lead, t) for t in opts):
            return False
    if ability.get("require_leader_name") and not ability.get("require_leader_name_or_trait"):
        needles = [x.strip() for x in str(ability["require_leader_name"]).split("|") if x.strip()]
        info = catalog(player.leader_card_id)
        if needles and not any(_card_name_has(info, n) for n in needles):
            return False
    if ability.get("require_leader_multicolor"):
        lead = catalog(player.leader_card_id)
        colors = normalize_colors(lead.get("colors_en") or lead.get("colors"))
        if len(colors) < 2:
            return False
    if ability.get("require_leader_monocolor"):
        lead = catalog(player.leader_card_id)
        colors = normalize_colors(lead.get("colors_en") or lead.get("colors"))
        if len(colors) != 1:
            return False
    if ability.get("require_leader_color"):
        lead = catalog(player.leader_card_id)
        colors = normalize_colors(lead.get("colors_en") or lead.get("colors"))
        want = str(ability["require_leader_color"]).strip().lower()
        aliases = {
            "blue": {"blue", "藍", "蓝"},
            "red": {"red", "紅", "红"},
            "green": {"green", "綠", "绿"},
            "yellow": {"yellow", "黃", "黄"},
            "black": {"black", "黑"},
            "purple": {"purple", "紫"},
        }
        opts = [x.strip() for x in want.split("|") if x.strip()] or [want]
        expanded: set[str] = set()
        for o in opts:
            expanded |= {a.lower() for a in aliases.get(o, (o,))}
            expanded.add(o)
        color_blob = {str(c).strip().lower() for c in colors}
        if not (expanded & color_blob):
            return False
    if ability.get("require_leader_name_or_multicolor"):
        needles = [x.strip() for x in str(ability.get("require_leader_name") or "").split("|") if x.strip()]
        info = catalog(player.leader_card_id)
        name_ok = bool(needles) and any(_card_name_has(info, n) for n in needles)
        colors = normalize_colors(info.get("colors_en") or info.get("colors"))
        if not name_ok and len(colors) < 2:
            return False
    if ability.get("require_leader_attribute"):
        want = str(ability["require_leader_attribute"]).strip().lower()
        info = catalog(player.leader_card_id)
        from battle.effects import card_attr_blob, attr_alias_keys

        blob = card_attr_blob(info).lower()
        opts = [a.strip().lower() for a in want.split("|") if a.strip()] or [want]
        if opts and not any(any(k in blob for k in attr_alias_keys(o)) for o in opts):
            return False
    if ability.get("require_opp_leader_attribute"):
        want = str(ability["require_opp_leader_attribute"]).strip().lower()
        info = catalog(foe.leader_card_id)
        from battle.effects import card_attr_blob, attr_alias_keys

        blob = card_attr_blob(info).lower()
        opts = [a.strip().lower() for a in want.split("|") if a.strip()] or [want]
        if opts and not any(any(k in blob for k in attr_alias_keys(o)) for o in opts):
            return False
    if ability.get("require_no_own_char_cost_gte") is not None:
        need = int(ability["require_no_own_char_cost_gte"])
        trait = str(ability.get("require_chars_trait") or "")
        found = False
        for c in player.characters:
            cinfo = catalog(c.card_id)
            if printed_cost(cinfo) < need:
                continue
            if trait and not _info_has_trait(cinfo, trait):
                continue
            found = True
            break
        if found:
            return False
    if ability.get("require_own_char_power_gte") is not None:
        need = int(ability["require_own_char_power_gte"])
        names = str(ability.get("require_own_name_contains") or "")
        name_opts = [x for x in names.split("|") if x] if names else []
        trait = str(ability.get("require_chars_trait") or "")
        ok = False
        # 「場上有力量值N以上的『Name』」— Leader or Character.
        lead_info = catalog(player.leader_card_id)
        if (not name_opts or any(_card_name_has(lead_info, n) for n in name_opts)) and (
            not trait or _info_has_trait(lead_info, trait)
        ):
            if inst_power(state, seat, "leader", catalog) >= need:
                ok = True
        if not ok:
            for c in player.characters:
                cinfo = catalog(c.card_id)
                if name_opts and not any(_card_name_has(cinfo, n) for n in name_opts):
                    continue
                if trait and not _info_has_trait(cinfo, trait):
                    continue
                if inst_power(state, seat, c.iid, catalog) >= need:
                    ok = True
                    break
        if not ok:
            return False
    if ability.get("require_own_char_base_power_gte") is not None:
        # 「自己原本力量值N以上」— own Characters only, printed/base power.
        need = int(ability["require_own_char_base_power_gte"])
        ok = False
        for c in player.characters:
            cinfo = catalog(c.card_id)
            try:
                raw = cinfo.get("power") or cinfo.get("power_en") or 0
                base = int(str(raw).split()[0].replace(",", "") or 0)
            except (TypeError, ValueError):
                base = 0
            if getattr(c, "base_power_override", None) is not None:
                try:
                    base = int(c.base_power_override)
                except (TypeError, ValueError):
                    pass
            if base >= need:
                ok = True
                break
        if not ok:
            return False
    if ability.get("require_other_own_char_power_gte") is not None:
        need = int(ability["require_other_own_char_power_gte"])
        ok = False
        for c in player.characters:
            if source_iid and c.iid == source_iid:
                continue
            if inst_power(state, seat, c.iid, catalog) >= need:
                ok = True
                break
        if not ok:
            return False
    if ability.get("require_opp_chars_count_lte") is not None:
        if len(foe.characters) > int(ability["require_opp_chars_count_lte"]):
            return False
    if ability.get("require_leader_name_or_trait"):
        needles = [x.strip() for x in str(ability.get("require_leader_name") or "").split("|") if x.strip()]
        info = catalog(player.leader_card_id)
        name_ok = bool(needles) and any(_card_name_has(info, n) for n in needles)
        trait = str(ability.get("require_leader_trait") or "")
        trait_ok = bool(trait) and _info_has_trait(info, trait)
        if not name_ok and not trait_ok:
            return False
    if ability.get("require_opp_char_base_power_gte") is not None:
        need = int(ability["require_opp_char_base_power_gte"])
        lead_pow = printed_power(catalog(foe.leader_card_id))
        if lead_pow < need and not any(printed_power(catalog(c.card_id)) >= need for c in foe.characters):
            return False
    if ability.get("require_opp_field_char_base_power_gte") is not None:
        need = int(ability["require_opp_field_char_base_power_gte"])
        if not any(printed_power(catalog(c.card_id)) >= need for c in foe.characters):
            return False
    if ability.get("require_opp_char_cost_eq") is not None:
        need = int(ability["require_opp_char_cost_eq"])
        if not any(effective_character_cost(state, state.other(seat), c, catalog) == need for c in foe.characters):
            return False
    if ability.get("require_leader_power_lte") is not None:
        if inst_power(state, seat, "leader", catalog) > int(ability["require_leader_power_lte"]):
            return False
    if ability.get("require_opp_leader_power_gte") is not None:
        need = int(ability["require_opp_leader_power_gte"])
        if inst_power(state, state.other(seat), "leader", catalog) < need:
            return False
    if ability.get("require_field_char_cost_eq") is not None:
        need = int(ability["require_field_char_cost_eq"])
        has = False
        for s in (seat, state.other(seat)):
            for c in state.player(s).characters:
                if effective_character_cost(state, s, c, catalog) == need:
                    has = True
                    break
            if has:
                break
        if not has:
            return False
    if ability.get("require_field_char_cost_0_or_gte") is not None:
        gte = int(ability["require_field_char_cost_0_or_gte"])
        has = False
        for s in (seat, state.other(seat)):
            for c in state.player(s).characters:
                cost = effective_character_cost(state, s, c, catalog)
                if cost == 0 or cost >= gte:
                    has = True
                    break
            if has:
                break
        if not has:
            return False
    return True


def static_opp_cost_aura(state: MatchState, owner_seat: int, catalog: CatalogFn) -> int:
    """Sum of continuous −cost auras affecting Characters owned by owner_seat."""
    from battle.effect_library import static_cost_abilities

    controller = state.other(owner_seat)
    if state.turn_seat != controller:
        return 0
    player = state.player(controller)
    total = 0
    for ability in static_cost_abilities(player.leader_card_id, catalog(player.leader_card_id)):
        if not _ability_board_conditions_ok(
            state, controller, ability, catalog, don_attached=int(player.leader_don or 0)
        ):
            continue
        for op in ability.get("ops") or []:
            if op.get("op") == "static_reduce_opp_cost":
                total += int(op.get("amount") or 0)
    for ch in player.characters:
        for ability in static_cost_abilities(ch.card_id, catalog(ch.card_id)):
            if not _ability_board_conditions_ok(
                state, controller, ability, catalog, don_attached=int(ch.don_attached or 0)
            ):
                continue
            for op in ability.get("ops") or []:
                if op.get("op") == "static_reduce_opp_cost":
                    total += int(op.get("amount") or 0)
    return total


def effective_character_cost(
    state: MatchState,
    owner_seat: int,
    inst: CardInst,
    catalog: CatalogFn,
) -> int:
    from battle.effect_library import ability_is_runnable, get_abilities
    from battle.effects import parse_static_self_cost

    info = catalog(inst.card_id)
    base = printed_cost(info) + int(getattr(inst, "cost_mod", 0) or 0)
    base += static_opp_cost_aura(state, owner_seat, catalog)
    # Continuous self +cost (plain or scaled by trash) + board all-trait auras (e.g. OP14-086).
    player = state.player(owner_seat)
    my_turn = state.turn_seat == owner_seat
    seen_static: set[tuple[Any, ...]] = set()
    printed = printed_cost(info)

    def _grant_amt(op: dict[str, Any]) -> int:
        amt = int(op.get("amount") or 0)
        if op.get("per_trash_cards"):
            step = max(1, int(op["per_trash_cards"]))
            amt *= len(player.trash) // step
        elif op.get("per_trash_events"):
            step = max(1, int(op["per_trash_events"]))
            ev = sum(1 for tid in player.trash if card_type_of(catalog(tid)) == "event")
            amt *= ev // step
        return amt

    def _op_applies_to_victim(op: dict[str, Any], *, src_iid: str) -> int | None:
        if op.get("op") != "grant_cost":
            return None
        tk = str(op.get("target_kind") or "self").strip().lower()
        trait = str(op.get("trait_contains") or op.get("trait_includes") or "").strip()
        name_needle = str(op.get("name_contains") or "").strip()
        board_wide = bool(op.get("all") or tk in {"all_own", "own_characters"})
        if tk in {"self", ""}:
            if src_iid != inst.iid:
                return None
        elif tk in {"own_character", "own_characters", "all_own"}:
            # Bare own_character without filters is self-only continuous; board auras need all/trait.
            if not board_wide and not trait and not name_needle:
                if src_iid != inst.iid:
                    return None
            # Optional one-shot named grants are not continuous auras.
            if name_needle and not board_wide and not op.get("all") and tk != "self":
                return None
        else:
            return None
        if trait and not _info_has_trait(info, trait):
            return None
        if name_needle:
            blob = " ".join(
                str(x or "")
                for x in (info.get("name"), info.get("name_en"), info.get("name_cn"), inst.card_id)
            ).lower()
            parts = [p.strip().lower() for p in name_needle.replace("|", "/").split("/") if p.strip()]
            if parts and not any(p in blob for p in parts):
                return None
        if op.get("cost_gte") is not None and printed < int(op["cost_gte"]):
            return None
        if op.get("cost_lte") is not None and printed > int(op["cost_lte"]):
            return None
        if op.get("cost_eq") is not None and printed != int(op["cost_eq"]):
            return None
        return _grant_amt(op)

    ability_lists: list[list[dict[str, Any]]] = []
    for timing in ("your_turn", "opponent_turn"):
        if timing == "your_turn" and not my_turn:
            continue
        if timing == "opponent_turn" and my_turn:
            continue
        ability_lists.append(list(get_abilities(inst.card_id, timing)))
    # Template fallback for untimed "這張角色卡的費用+N" when not curated.
    for ab in parse_static_self_cost(info):
        timing = str(ab.get("timing") or "")
        if timing == "your_turn" and not my_turn:
            continue
        if timing == "opponent_turn" and my_turn:
            continue
        ability_lists.append([ab])
    for abilities in ability_lists:
        for ability in abilities:
            if not ability_is_runnable(ability):
                continue
            if not any(o.get("op") == "grant_cost" for o in (ability.get("ops") or [])):
                continue
            key = (
                "self",
                ability.get("timing"),
                ability.get("require_trash_gte"),
                ability.get("require_leader_trait"),
                tuple(
                    (
                        o.get("op"),
                        o.get("amount"),
                        o.get("target_kind"),
                        o.get("trait_contains") or o.get("trait_includes"),
                        o.get("per_trash_cards"),
                        o.get("per_trash_events"),
                    )
                    for o in (ability.get("ops") or [])
                    if o.get("op") == "grant_cost"
                ),
            )
            if key in seen_static:
                continue
            if not _ability_board_conditions_ok(
                state,
                owner_seat,
                ability,
                catalog,
                don_attached=int(inst.don_attached or 0),
                source_iid=inst.iid,
            ):
                continue
            applied = False
            for op in ability.get("ops") or []:
                amt = _op_applies_to_victim(op, src_iid=inst.iid)
                if amt is None:
                    continue
                base += amt
                applied = True
            if applied:
                seen_static.add(key)

    # Board auras from other own Characters / Leader / Stages (OP14-086, OP10-042, …).
    sources: list[tuple[str, str, int]] = [
        ("leader", player.leader_card_id, int(player.leader_don or 0)),
        *[(c.iid, c.card_id, int(c.don_attached or 0)) for c in player.characters],
        *[(s.iid, s.card_id, 0) for s in player.stages],
    ]
    for src_iid, cid, don in sources:
        if src_iid == inst.iid:
            continue
        for timing in ("your_turn", "opponent_turn"):
            if timing == "your_turn" and not my_turn:
                continue
            if timing == "opponent_turn" and my_turn:
                continue
            for ability in get_abilities(cid, timing):
                if not ability_is_runnable(ability):
                    continue
                if not any(
                    o.get("op") == "grant_cost"
                    and (
                        o.get("all")
                        or str(o.get("target_kind") or "") in {"all_own", "own_characters", "own_character"}
                    )
                    for o in (ability.get("ops") or [])
                ):
                    continue
                key = (
                    "aura",
                    src_iid,
                    ability.get("timing"),
                    ability.get("require_trash_gte"),
                    tuple(
                        (
                            o.get("amount"),
                            o.get("target_kind"),
                            o.get("trait_contains") or o.get("trait_includes"),
                            o.get("cost_gte"),
                            o.get("cost_lte"),
                            o.get("cost_eq"),
                        )
                        for o in (ability.get("ops") or [])
                        if o.get("op") == "grant_cost"
                    ),
                )
                if key in seen_static:
                    continue
                if not _ability_board_conditions_ok(
                    state, owner_seat, ability, catalog, don_attached=don, source_iid=src_iid
                ):
                    continue
                applied = False
                for op in ability.get("ops") or []:
                    amt = _op_applies_to_victim(op, src_iid=src_iid)
                    if amt is None:
                        continue
                    base += amt
                    applied = True
                if applied:
                    seen_static.add(key)
    return max(0, base)


def effective_play_cost(state: MatchState, seat: int, card_id: str, catalog: CatalogFn) -> int:
    """Printed cost after hand_cost reductions from the card itself and board auras."""
    from battle.effect_library import hand_cost_abilities

    info = catalog(card_id)
    cost = printed_cost(info)
    player = state.player(seat)

    def _apply_ability(ability: dict[str, Any], *, don_attached: int, source_on_board: bool) -> None:
        nonlocal cost
        if ability.get("hand_color") or ability.get("hand_card_type"):
            if not source_on_board:
                return
            want_color = str(ability.get("hand_color") or "").lower()
            want_type = str(ability.get("hand_card_type") or "").lower()
            colors = normalize_colors(info.get("colors_en") or info.get("colors"))
            ctype = card_type_of(info)
            if want_type and ctype != want_type:
                return
            if want_color and want_color not in colors:
                return
        else:
            # "This card in hand −N" only applies when evaluating that card itself.
            # Board auras that filter via op trait/name/cost still apply from the board.
            has_board_filter = any(
                (
                    o.get("trait_contains")
                    or o.get("name_contains")
                    or o.get("cost_gte") is not None
                    or o.get("cost_lte") is not None
                )
                for o in (ability.get("ops") or [])
                if isinstance(o, dict) and o.get("op") == "hand_cost_reduce"
            )
            if source_on_board and not has_board_filter:
                return
            if (not source_on_board) and has_board_filter:
                return
        if not _ability_board_conditions_ok(state, seat, ability, catalog, don_attached=don_attached):
            return
        for op in ability.get("ops") or []:
            if op.get("op") != "hand_cost_reduce":
                continue
            trait = str(op.get("trait_contains") or "").strip()
            if trait and not _info_has_trait(info, trait):
                continue
            name_raw = str(op.get("name_contains") or "").strip().lower()
            if name_raw:
                blob = " ".join(
                    str(x or "")
                    for x in (info.get("name"), info.get("name_en"), info.get("name_cn"), card_id)
                ).lower()
                parts = [p.strip() for p in name_raw.replace("|", "/").split("/") if p.strip()]
                if parts and not any(p in blob for p in parts):
                    continue
            if op.get("cost_gte") is not None and printed_cost(info) < int(op["cost_gte"]):
                continue
            cost += int(op.get("amount") or 0)

    for ability in hand_cost_abilities(card_id, info):
        _apply_ability(ability, don_attached=0, source_on_board=False)
    for ability in hand_cost_abilities(player.leader_card_id, catalog(player.leader_card_id)):
        _apply_ability(ability, don_attached=int(player.leader_don or 0), source_on_board=True)
    for ch in player.characters:
        for ability in hand_cost_abilities(ch.card_id, catalog(ch.card_id)):
            _apply_ability(ability, don_attached=int(ch.don_attached or 0), source_on_board=True)
    for stg in player.stages:
        for ability in hand_cost_abilities(stg.card_id, catalog(stg.card_id)):
            _apply_ability(ability, don_attached=0, source_on_board=True)
    # Activate: Main temporary reductions (e.g. OP12-061).
    for mod in list(getattr(player, "temp_hand_cost_mods", None) or []):
        name_raw = str(mod.get("name_contains") or "").strip().lower()
        if name_raw:
            blob = " ".join(
                str(x or "")
                for x in (info.get("name"), info.get("name_en"), info.get("name_cn"), card_id)
            ).lower()
            parts = [p.strip() for p in name_raw.replace("|", "/").split("/") if p.strip()]
            if parts and not any(p in blob for p in parts):
                continue
        if mod.get("cost_gte") is not None and printed_cost(info) < int(mod["cost_gte"]):
            continue
        cost += int(mod.get("amount") or 0)
    return max(0, cost)


def _return_attached_don(player: PlayerState, amount: int) -> None:
    if amount > 0:
        player.don_rested += amount


def _remove_character(player: PlayerState, iid: str, *, to_trash: bool = True) -> CardInst | None:
    inst = next((c for c in player.characters if c.iid == iid), None)
    if not inst:
        return None
    _return_attached_don(player, inst.don_attached)
    inst.don_attached = 0
    player.characters = [c for c in player.characters if c.iid != iid]
    if to_trash:
        player.trash.append(inst.card_id)
    return inst


def apply_battle_character_ko(
    state: MatchState,
    def_seat: int,
    inst: CardInst,
    catalog: CatalogFn,
) -> None:
    """Finish a battle K.O. after replace_leave was declined or did not apply."""
    defender = state.player(def_seat)
    ko_cid = inst.card_id
    target_iid = inst.iid
    ko_info = catalog(ko_cid)
    removed = _remove_character(defender, inst.iid, to_trash=True)
    if not removed:
        return
    state.add_log("play.log.ko", id=removed.card_id)
    pending = resolve_ability(
        state, def_seat, ko_cid, target_iid, rule_timings.ON_KO, ko_info, None, allow_llm=False, catalog=catalog
    )
    if pending and pending.ops:
        _run_pending_effect(state, pending, catalog)
    fire_own_trait_leave_or_ko(
        state,
        def_seat,
        ko_cid,
        catalog,
        by_opponent_effect=True,
        by_ko=True,
    )
    fire_on_opp_ko(state, def_seat, catalog)
    atk = state.attack
    if atk and atk.attacker_iid and atk.attacker_iid != "leader":
        atk_seat = atk.attacker_seat
        atk_player = state.player(atk_seat)
        atk_inst = next((c for c in atk_player.characters if c.iid == atk.attacker_iid), None)
        if atk_inst:
            from battle.effect_library import ability_is_runnable, get_abilities

            for ab in get_abilities(atk_inst.card_id, "on_ko"):
                if not ab.get("on_ko_caused_by_battle"):
                    continue
                if not ability_is_runnable(ab):
                    continue
                if ab.get("once") and atk_inst.once_used:
                    continue
                need_don = int(ab.get("require_don_attached_gte") or 0)
                if int(atk_inst.don_attached or 0) < need_don:
                    continue
                pending_a = resolve_ability(
                    state,
                    atk_seat,
                    atk_inst.card_id,
                    atk_inst.iid,
                    rule_timings.ON_KO,
                    catalog(atk_inst.card_id),
                    None,
                    allow_llm=False,
                    catalog=catalog,
                )
                if pending_a and pending_a.ops:
                    if ab.get("once"):
                        atk_inst.once_used = True
                    _run_pending_effect(state, pending_a, catalog)
                break


def fire_own_trait_leave_or_ko(
    state: MatchState,
    owner_seat: int,
    victim_card_id: str,
    catalog: CatalogFn,
    *,
    by_opponent_effect: bool = False,
    by_ko: bool = True,
) -> None:
    """Fire board watchers with on_own_trait_leave_or_ko when an own Character leaves/KO.

    Leaders with this flag are included (e.g. OP16-041 Buggy, OP10-042 Usopp).
    Abilities with on_any_leave fire on any leave (bounce/bottom/trash), not only KO/opp.
    """
    from battle.effect_library import ability_is_runnable, get_abilities
    from battle.state import PendingEffect, new_iid

    owner = state.player(owner_seat)
    victim_info = catalog(victim_card_id) or {}
    # (card_id, source_iid, don_attached, once_used)
    watchers: list[tuple[str, str, int, bool]] = [
        (
            owner.leader_card_id,
            "leader",
            int(owner.leader_don or 0),
            bool(owner.leader_once_used),
        )
    ]
    watchers.extend(
        (
            c.card_id,
            c.iid,
            int(c.don_attached or 0),
            bool(getattr(c, "once_used", False)),
        )
        for c in list(owner.characters)
    )
    for card_id, source_iid, don_att, once_used in watchers:
        for ab in get_abilities(card_id):
            trait = str(ab.get("on_own_trait_leave_or_ko") or "").strip()
            ko_only = str(ab.get("on_own_trait_ko") or "").strip()
            any_own_ko = bool(ab.get("on_own_char_ko"))
            if not trait and by_ko:
                trait = ko_only
            if not trait and not any_own_ko:
                continue
            if any_own_ko and not by_ko:
                continue
            if ko_only and not str(ab.get("on_own_trait_leave_or_ko") or "").strip() and not by_ko and not any_own_ko:
                continue
            if not ability_is_runnable(ab):
                continue
            timing = str(ab.get("timing") or "")
            my_turn = state.turn_seat == owner_seat
            if timing == "opponent_turn" and my_turn:
                continue
            if timing == "your_turn" and not my_turn:
                continue
            any_leave = bool(ab.get("on_any_leave"))
            if not any_leave and not by_ko and not by_opponent_effect:
                continue
            if trait and not _info_has_trait(victim_info, trait):
                continue
            if ab.get("require_victim_base_power_gte") is not None:
                if printed_power(victim_info) < int(ab["require_victim_base_power_gte"]):
                    continue
            if ab.get("require_victim_attr"):
                from battle.effects import attr_alias_keys, card_attr_blob

                needle = str(ab.get("require_victim_attr") or "").strip().lower()
                opts = [x.strip() for x in needle.split("|") if x.strip()] or [needle]
                blob = card_attr_blob(victim_info).lower()
                if not any(any(k in blob for k in attr_alias_keys(o)) for o in opts):
                    continue
            if ab.get("require_victim_without_keyword"):
                from battle.effects import has_blocker, live_keywords

                ban = str(ab.get("require_victim_without_keyword") or "").strip().lower()
                # Victim is often already off the board; use printed/granted keywords on card info.
                if ban == "blocker":
                    if has_blocker(victim_info):
                        continue
                elif ban in live_keywords(victim_info):
                    continue
            if ab.get("once") and once_used:
                continue
            if not _ability_board_conditions_ok(
                state,
                owner_seat,
                ab,
                catalog,
                don_attached=don_att,
                source_iid=source_iid,
            ):
                continue
            ops = list(ab.get("ops") or [])
            if not ops:
                continue
            # Annotate source so apply_ops can resolve self targets.
            annotated = []
            for o in ops:
                if not isinstance(o, dict):
                    continue
                oo = dict(o)
                oo.setdefault("source_iid", source_iid)
                oo.setdefault("card_id", card_id)
                annotated.append(oo)
            pending = PendingEffect(
                effect_id=new_iid("fx"),
                seat=owner_seat,
                card_id=card_id,
                source_iid=source_iid,
                summary=str(ab.get("summary") or "on_own_trait_leave_or_ko")[:240],
                ops=annotated,
                uncertain=ability_needs_confirm(ab, catalog(card_id) or {}),
                once=bool(ab.get("once")),
            )
            _run_pending_effect(state, pending, catalog)
            break


def fire_hand_trash_by_effect(
    state: MatchState,
    hand_owner_seat: int,
    catalog: CatalogFn,
    *,
    effect_card_id: str = "",
    by_own_effect: bool = True,
    trashed_count: int = 1,
) -> None:
    """Fire watchers when cards are trashed from hand by an effect (OP12-040 / OP14-049 / ST33-004)."""
    from battle.effect_library import ability_is_runnable, get_abilities
    from battle.state import PendingEffect, new_iid

    if state.status != "playing" or trashed_count <= 0:
        return
    owner = state.player(hand_owner_seat)
    owner.hand_trashed_by_effect_this_turn = True
    setattr(owner, "_last_trash_hand_count", int(trashed_count))
    effect_info = catalog(effect_card_id) if effect_card_id else {}
    my_turn = state.turn_seat == hand_owner_seat
    watchers: list[tuple[str, str, int, bool]] = [
        (
            owner.leader_card_id,
            "leader",
            int(owner.leader_don or 0),
            bool(owner.leader_once_used),
        )
    ]
    watchers.extend(
        (
            c.card_id,
            c.iid,
            int(c.don_attached or 0),
            bool(getattr(c, "once_used", False)),
        )
        for c in list(owner.characters)
    )
    for card_id, source_iid, don_att, once_used in watchers:
        for ab in get_abilities(card_id):
            own_flag = bool(ab.get("on_hand_trash_by_own_effect"))
            any_flag = bool(ab.get("on_hand_trashed_by_effect"))
            if not own_flag and not any_flag:
                continue
            if own_flag and not by_own_effect:
                continue
            if not ability_is_runnable(ab):
                continue
            timing = str(ab.get("timing") or "")
            if timing == "opponent_turn" and my_turn:
                continue
            if timing == "your_turn" and not my_turn:
                continue
            if timing not in {"your_turn", "opponent_turn", ""}:
                # hand_cost abilities are evaluated continuously — skip here
                if timing == "hand_cost":
                    continue
            src_trait = str(ab.get("require_effect_source_trait") or "").strip()
            if src_trait:
                if not effect_card_id or not _info_has_trait(effect_info, src_trait):
                    continue
            if ab.get("once") and once_used:
                continue
            if not _ability_board_conditions_ok(
                state,
                hand_owner_seat,
                ab,
                catalog,
                don_attached=don_att,
                source_iid=source_iid,
            ):
                continue
            ops = list(ab.get("ops") or [])
            if not ops:
                continue
            annotated = []
            for o in ops:
                if not isinstance(o, dict):
                    continue
                oo = dict(o)
                oo.setdefault("source_iid", source_iid)
                oo.setdefault("card_id", card_id)
                annotated.append(oo)
            pending = PendingEffect(
                effect_id=new_iid("fx"),
                seat=hand_owner_seat,
                card_id=card_id,
                source_iid=source_iid,
                summary=str(ab.get("summary") or "on_hand_trash")[:240],
                ops=annotated,
                uncertain=ability_needs_confirm(ab, catalog(card_id) or {}),
                once=bool(ab.get("once")),
            )
            _run_pending_effect(state, pending, catalog)
            break


def fire_on_opp_ko(
    state: MatchState,
    victim_owner_seat: int,
    catalog: CatalogFn,
) -> None:
    """When a Character is KO'd, fire the other seat's on_opp_ko watchers (e.g. EB04-044)."""
    from battle.effect_library import ability_is_runnable, get_abilities
    from battle.state import PendingEffect, new_iid

    if state.status != "playing":
        return
    watcher_seat = state.other(victim_owner_seat)
    watcher = state.player(watcher_seat)
    my_turn = state.turn_seat == watcher_seat
    sources: list[tuple[str, str, CardInst | None]] = [
        (c.card_id, c.iid, c) for c in list(watcher.characters)
    ]
    sources.append((watcher.leader_card_id, "leader", None))
    for card_id, source_iid, inst in sources:
        if state.status != "playing":
            return
        for ab in get_abilities(card_id):
            ops_raw = [o for o in (ab.get("ops") or []) if isinstance(o, dict)]
            flagged = bool(ab.get("on_opp_ko")) or any(o.get("on_opp_ko") for o in ops_raw)
            if not flagged:
                continue
            if not ability_is_runnable(ab):
                continue
            timing = str(ab.get("timing") or "")
            if timing == "opponent_turn" and my_turn:
                continue
            if timing == "your_turn" and not my_turn:
                continue
            once = bool(ab.get("once") or any(o.get("once") for o in ops_raw))
            if once:
                if inst is None:
                    if getattr(watcher, "leader_on_opp_ko_used", False):
                        continue
                elif getattr(inst, "on_opp_ko_used", False):
                    continue
            don = int(inst.don_attached or 0) if inst is not None else int(watcher.leader_don or 0)
            if not _ability_board_conditions_ok(
                state,
                watcher_seat,
                ab,
                catalog,
                don_attached=don,
                source_iid=source_iid,
            ):
                continue
            ops = []
            ability_flag = bool(ab.get("on_opp_ko"))
            for o in ops_raw:
                if o.get("on_opp_ko") or ability_flag:
                    oo = dict(o)
                    oo.setdefault("source_iid", source_iid)
                    oo.setdefault("card_id", card_id)
                    ops.append(oo)
            if not ops:
                continue
            if once:
                if inst is None:
                    watcher.leader_on_opp_ko_used = True
                else:
                    inst.on_opp_ko_used = True
            pending = PendingEffect(
                effect_id=new_iid("fx"),
                seat=watcher_seat,
                card_id=card_id,
                source_iid=source_iid,
                summary=str(ab.get("summary") or "on_opp_ko")[:240],
                ops=ops,
                uncertain=ability_needs_confirm(ab, catalog(card_id) or {}),
                once=False,
            )
            _run_pending_effect(state, pending, catalog)
            break


def _trait_aliases(needle: str) -> tuple[str, ...]:
    key = (needle or "").strip().lower()
    aliases = {
        "impel down": ("impel down", "推進城", "推进城", "インペルダウン"),
        "推進城": ("impel down", "推進城", "推进城", "インペルダウン"),
        "推进城": ("impel down", "推進城", "推进城", "インペルダウン"),
        "インペルダウン": ("impel down", "推進城", "推进城", "インペルダウン"),
        "straw hat crew": ("straw hat crew", "草帽一行人"),
        "草帽一行人": ("straw hat crew", "草帽一行人"),
        "land of wano": ("land of wano", "和之國", "和之国"),
        "和之國": ("land of wano", "和之國", "和之国"),
        "和之国": ("land of wano", "和之國", "和之国"),
        "minks": ("minks", "純毛族", "纯毛族"),
        "純毛族": ("minks", "純毛族", "纯毛族"),
        "纯毛族": ("minks", "純毛族", "纯毛族"),
        "navy": ("navy", "海軍", "海军"),
        "海軍": ("navy", "海軍", "海军"),
        "海军": ("navy", "海軍", "海军"),
        "dressrosa": ("dressrosa", "多雷斯羅薩", "多雷斯罗萨"),
        "多雷斯羅薩": ("dressrosa", "多雷斯羅薩", "多雷斯罗萨"),
        "多雷斯罗萨": ("dressrosa", "多雷斯羅薩", "多雷斯罗萨"),
        "music": ("music", "音樂", "音乐"),
        "音樂": ("music", "音樂", "音乐"),
        "音乐": ("music", "音樂", "音乐"),
        "animal kingdom pirates": ("animal kingdom pirates", "百獣海賊団", "百獸海賊團", "百兽海贼团"),
        "百獣海賊団": ("animal kingdom pirates", "百獣海賊団", "百獸海賊團", "百兽海贼团"),
        "百獸海賊團": ("animal kingdom pirates", "百獣海賊団", "百獸海賊團", "百兽海贼团"),
        "百兽海贼团": ("animal kingdom pirates", "百獣海賊団", "百獸海賊團", "百兽海贼团"),
        "w7": ("w7", "W7", "water seven", "水之七島", "水之七岛"),
        "water seven": ("w7", "W7", "water seven", "水之七島", "水之七岛"),
        "水之七島": ("w7", "W7", "water seven", "水之七島", "水之七岛"),
        "水之七岛": ("w7", "W7", "water seven", "水之七島", "水之七岛"),
        "film": ("film", "FILM"),
        "foxy pirates": ("foxy pirates", "弗克西海賊團", "弗克西海贼团"),
        "弗克西海賊團": ("foxy pirates", "弗克西海賊團", "弗克西海贼团"),
        "弗克西海贼团": ("foxy pirates", "弗克西海賊團", "弗克西海贼团"),
        "baroque works": ("baroque works", "b・w", "b.w", "b·w", "B・W", "巴洛克工作社"),
        "b・w": ("baroque works", "b・w", "b.w", "b·w", "B・W", "巴洛克工作社"),
        "b.w": ("baroque works", "b・w", "b.w", "b·w", "B・W", "巴洛克工作社"),
        "b·w": ("baroque works", "b・w", "b.w", "b·w", "B・W", "巴洛克工作社"),
        "巴洛克工作社": ("baroque works", "b・w", "b.w", "b·w", "B・W", "巴洛克工作社"),
        "thriller bark pirates": ("thriller bark pirates", "恐怖三桅帆船海賊團", "恐怖三桅帆船海贼团"),
        "恐怖三桅帆船海賊團": ("thriller bark pirates", "恐怖三桅帆船海賊團", "恐怖三桅帆船海贼团"),
        "恐怖三桅帆船海贼团": ("thriller bark pirates", "恐怖三桅帆船海賊團", "恐怖三桅帆船海贼团"),
        "dressrosa": ("dressrosa", "多雷斯羅薩", "多雷斯罗萨"),
        "多雷斯羅薩": ("dressrosa", "多雷斯羅薩", "多雷斯罗萨"),
        "多雷斯罗萨": ("dressrosa", "多雷斯羅薩", "多雷斯罗萨"),
        "homies": ("homies", "歡樂友人", "欢乐友人"),
        "歡樂友人": ("homies", "歡樂友人", "欢乐友人"),
        "欢乐友人": ("homies", "歡樂友人", "欢乐友人"),
        "kid pirates": ("kid pirates", "基德海賊團", "基德海贼团"),
        "基德海賊團": ("kid pirates", "基德海賊團", "基德海贼团"),
        "基德海贼团": ("kid pirates", "基德海賊團", "基德海贼团"),
        "shandian warrior": ("shandian warrior", "shandian warriors", "香朵拉的戰士", "香朵拉的战士"),
        "shandian warriors": ("shandian warrior", "shandian warriors", "香朵拉的戰士", "香朵拉的战士"),
        "香朵拉的戰士": ("shandian warrior", "shandian warriors", "香朵拉的戰士", "香朵拉的战士"),
        "香朵拉的战士": ("shandian warrior", "shandian warriors", "香朵拉的戰士", "香朵拉的战士"),
        "red-haired pirates": ("red-haired pirates", "red hair pirates", "紅髮海賊團", "红发海贼团"),
        "紅髮海賊團": ("red-haired pirates", "red hair pirates", "紅髮海賊團", "红发海贼团"),
        "红发海贼团": ("red-haired pirates", "red hair pirates", "紅髮海賊團", "红发海贼团"),
        "scientist": ("scientist", "科學家", "科学家"),
        "科學家": ("scientist", "科學家", "科学家"),
        "科学家": ("scientist", "科學家", "科学家"),
        "amazon lily": ("amazon lily", "亞馬遜百合", "亚马逊百合"),
        "亞馬遜百合": ("amazon lily", "亞馬遜百合", "亚马逊百合"),
        "亚马逊百合": ("amazon lily", "亞馬遜百合", "亚马逊百合"),
        "kuja pirates": ("kuja pirates", "九蛇海賊團", "九蛇海贼团"),
        "九蛇海賊團": ("kuja pirates", "九蛇海賊團", "九蛇海贼团"),
        "九蛇海贼团": ("kuja pirates", "九蛇海賊團", "九蛇海贼团"),
        "supernovas": ("supernovas", "超新星"),
        "超新星": ("supernovas", "超新星"),
        "heart pirates": ("heart pirates", "哈特海賊團", "哈特海贼团"),
        "哈特海賊團": ("heart pirates", "哈特海賊團", "哈特海贼团"),
        "哈特海贼团": ("heart pirates", "哈特海賊團", "哈特海贼团"),
        "neptunian": ("neptunian", "海王類", "海王类"),
        "海王類": ("neptunian", "海王類", "海王类"),
        "海王类": ("neptunian", "海王類", "海王类"),
        "fish-man island": ("fish-man island", "fish man island", "魚人島", "鱼人岛"),
        "魚人島": ("fish-man island", "fish man island", "魚人島", "鱼人岛"),
        "鱼人岛": ("fish-man island", "fish man island", "魚人島", "鱼人岛"),
        "firetank pirates": ("firetank pirates", "火戰車海賊團", "火战车海贼团"),
        "火戰車海賊團": ("firetank pirates", "火戰車海賊團", "火战车海贼团"),
        "alabasta": ("alabasta", "阿拉巴斯坦王國", "阿拉巴斯坦王国"),
        "阿拉巴斯坦王國": ("alabasta", "阿拉巴斯坦王國", "阿拉巴斯坦王国"),
        "merfolk": ("merfolk", "人魚族", "人鱼族"),
        "人魚族": ("merfolk", "人魚族", "人鱼族"),
        "big mom pirates": ("big mom pirates", "big-mom pirates", "BIG MOM海賊團", "BIG MOM海贼团"),
        "big mom海賊團": ("big mom pirates", "BIG MOM海賊團", "BIG MOM海贼团"),
        "revolutionary army": ("revolutionary army", "革命軍", "革命军"),
        "革命軍": ("revolutionary army", "革命軍", "革命军"),
        "blackbeard pirates": ("blackbeard pirates", "黑鬍子海賊團", "黑胡子海贼团"),
        "黑鬍子海賊團": ("blackbeard pirates", "黑鬍子海賊團", "黑胡子海贼团"),
        "egghead": ("egghead", "蛋頭", "蛋头"),
        "蛋頭": ("egghead", "蛋頭", "蛋头"),
        "蛋头": ("egghead", "蛋頭", "蛋头"),
        "animal": ("animal", "動物", "动物"),
        "動物": ("animal", "動物", "动物"),
        "动物": ("animal", "動物", "动物"),
        "celestial dragons": ("celestial dragons", "天龍人", "天龙人"),
        "天龍人": ("celestial dragons", "天龍人", "天龙人"),
        "天龙人": ("celestial dragons", "天龍人", "天龙人"),
        "sky island": ("sky island", "空島", "空岛"),
        "空島": ("sky island", "空島", "空岛"),
        "空岛": ("sky island", "空島", "空岛"),
        "fish-man": ("fish-man", "fish man", "魚人族", "鱼人族"),
        "魚人族": ("fish-man", "fish man", "魚人族", "鱼人族"),
        "鱼人族": ("fish-man", "fish man", "魚人族", "鱼人族"),
        "rocks pirates": ("rocks pirates", "洛克斯海賊團", "洛克斯海贼团"),
        "洛克斯海賊團": ("rocks pirates", "洛克斯海賊團", "洛克斯海贼团"),
        "洛克斯海贼团": ("rocks pirates", "洛克斯海賊團", "洛克斯海贼团"),
        "bonney pirates": ("bonney pirates", "波妮海賊團", "波妮海贼团"),
        "波妮海賊團": ("bonney pirates", "波妮海賊團", "波妮海贼团"),
        "波妮海贼团": ("bonney pirates", "波妮海賊團", "波妮海贼团"),
        "cross guild": ("cross guild", "十字公會", "十字公会"),
        "十字公會": ("cross guild", "十字公會", "十字公会"),
        "十字公会": ("cross guild", "十字公會", "十字公会"),
        "punk hazard": ("punk hazard", "龐克哈薩特", "庞克哈萨特", "パンクハザード"),
        "龐克哈薩特": ("punk hazard", "龐克哈薩特", "庞克哈萨特", "パンクハザード"),
        "庞克哈萨特": ("punk hazard", "龐克哈薩特", "庞克哈萨特", "パンクハザード"),
        "パンクハザード": ("punk hazard", "龐克哈薩特", "庞克哈萨特", "パンクハザード"),
    }
    return aliases.get(key, (needle,))


def _info_has_color(info: dict[str, Any], needle: str) -> bool:
    """True if printed colors match a color name or ZH alias (pipe OR)."""
    want = str(needle or "").strip().lower()
    if not want:
        return True
    aliases = {
        "blue": {"blue", "藍", "蓝"},
        "red": {"red", "紅", "红"},
        "green": {"green", "綠", "绿"},
        "yellow": {"yellow", "黃", "黄"},
        "black": {"black", "黑"},
        "purple": {"purple", "紫"},
    }
    opts = [x.strip() for x in want.split("|") if x.strip()] or [want]
    expanded: set[str] = set()
    for o in opts:
        expanded |= {a.lower() for a in aliases.get(o, (o,))}
        expanded.add(o)
    colors = normalize_colors(info.get("colors_en") or info.get("colors"))
    blob = {str(c).strip().lower() for c in colors}
    for key in ("colors", "colors_en", "color"):
        v = info.get(key)
        if isinstance(v, list):
            blob.update(str(x).strip().lower() for x in v if x)
        elif v:
            blob.add(str(v).strip().lower())
    return bool(expanded & blob)


def _info_has_trait(info: dict[str, Any], trait: str) -> bool:
    opts = [t.strip() for t in str(trait or "").split("|") if t.strip()] or [str(trait or "").strip()]
    raw: list[Any] = []
    for key in ("traits", "traits_en", "trait", "trait_en"):
        v = info.get(key)
        if isinstance(v, list):
            raw.extend(v)
        elif v:
            raw.append(v)
    traits = " ".join(str(x or "") for x in raw).lower()
    for opt in opts:
        keys = _trait_aliases(opt)
        if any(k.lower() in traits for k in keys):
            return True
    return False


def _op_traits_ok(info: dict[str, Any], op: dict[str, Any]) -> bool:
    """AND-all (`trait_all`) then OR (`trait_contains` / `trait_any`)."""
    ta = op.get("trait_all")
    if isinstance(ta, list) and ta:
        if not all(_info_has_trait(info, str(t)) for t in ta):
            return False
    trait = str(op.get("trait_contains") or op.get("trait_includes") or "").strip()
    if trait and not _info_has_trait(info, trait):
        return False
    trait_any = op.get("trait_any")
    if isinstance(trait_any, list) and trait_any:
        if not any(_info_has_trait(info, str(t)) for t in trait_any):
            return False
    return True


def _chars_all_have_trait(player: PlayerState, trait: str, catalog: CatalogFn) -> bool:
    """True iff there is at least one character and every character has the trait.

    Empty board fails: 「角色卡只有擁有《…》」requires characters that are all of that type,
    not vacuously true with zero characters (e.g. OP16-022).
    Pipe-separated trait aliases (GERMA|杰爾馬) count as OR matches per character.
    """
    if not trait:
        return True
    if not player.characters:
        return False
    opts = [t.strip() for t in str(trait).split("|") if t.strip()] or [trait]
    for ch in player.characters:
        info = catalog(ch.card_id)
        if not any(_info_has_trait(info, t) for t in opts):
            return False
    return True


def _activate_spec_legal(
    player: PlayerState,
    spec: dict[str, Any],
    catalog: CatalogFn,
    *,
    is_leader: bool,
    source_rested: bool = False,
    source_once_used: bool = False,
) -> bool:
    if not spec or not spec.get("ops"):
        return False
    if spec.get("once") and (source_once_used or (is_leader and player.leader_once_used)):
        return False
    if spec.get("rest_self") and (source_rested or (is_leader and player.leader_rested)):
        return False
    if int(spec.get("cost_don") or 0) > player.don_active:
        return False
    ops = list(spec.get("ops") or [])
    ret_n = sum(int(o.get("count") or 0) for o in ops if o.get("op") == "return_don")
    if ret_n and _don_on_field(player) < ret_n:
        return False
    rest_don_n = sum(
        int(o.get("count") or 0)
        for o in ops
        if o.get("op") == "rest_don" and not o.get("any_number") and not o.get("optional")
    )
    if rest_don_n and int(player.don_active or 0) < rest_don_n:
        return False
    attached_ret = sum(
        int(o.get("count") or 0)
        for o in ops
        if o.get("op") == "return_attached_don" and (o.get("as_cost") or not o.get("optional"))
    )
    if attached_ret:
        total_attached = int(player.leader_don or 0) + sum(int(c.don_attached or 0) for c in player.characters)
        if total_attached < attached_ret:
            return False
    if spec.get("require_trash_gte") is not None and len(player.trash) < int(spec["require_trash_gte"]):
        return False
    lead_name = str(spec.get("require_leader_name") or "").strip()
    if lead_name:
        needles = [x.strip() for x in lead_name.split("|") if x.strip()] or [lead_name]
        lead = catalog(player.leader_card_id)
        if not any(_card_name_has(lead, n) for n in needles):
            return False
    if spec.get("require_own_name_all"):
        raw = spec.get("require_own_name_all")
        needles_all: list[str] = []
        if isinstance(raw, list):
            needles_all = [str(x).strip() for x in raw if str(x).strip()]
        elif isinstance(raw, str) and raw.strip():
            needles_all = [x.strip() for x in raw.split(";") if x.strip()]
        pool = [catalog(player.leader_card_id)] + [catalog(c.card_id) for c in player.characters]
        for needle in needles_all:
            opts = [x.strip() for x in needle.split("|") if x.strip()] or [needle]
            if not any(_card_name_has(info, opt) for info in pool for opt in opts):
                return False
    if any(o.get("op") == "active_don" for o in ops):
        # Optional / gated active_don (e.g. OP14-020: only if field has cost≥5) must not
        # block paying the colon-cost when there is currently no rested DON!! to stand.
        hard = [
            o
            for o in ops
            if o.get("op") == "active_don"
            and not o.get("optional")
            and o.get("require_field_char_cost_gte") is None
            and o.get("require_field_char_cost_eq") is None
            and o.get("require_field_char_cost_0_or_gte") is None
        ]
        if hard:
            need = max(int(o.get("count") or 1) for o in hard)
            available_rested = player.don_rested
            if ret_n:
                overflow = max(0, ret_n - player.don_active)
                available_rested = max(0, player.don_rested - overflow)
            if available_rested <= 0:
                return False
            if available_rested < need and need > 0:
                pass
    req = str(spec.get("require_all_chars_trait") or "").strip()
    if req and not _chars_all_have_trait(player, req, catalog):
        return False
    lead_req = str(spec.get("require_leader_trait") or "").strip()
    if lead_req:
        lead = catalog(player.leader_card_id)
        opts = [t.strip() for t in lead_req.split("|") if t.strip()] or [lead_req]
        if not any(_info_has_trait(lead, t) for t in opts):
            return False
    if spec.get("require_chars_gte") is not None and len(player.characters) < int(spec["require_chars_gte"]):
        return False
    if spec.get("require_chars_lte") is not None and len(player.characters) > int(spec["require_chars_lte"]):
        return False
    if spec.get("require_no_other_name"):
        name = str(spec.get("require_no_other_name") or "").strip()
        if name:
            opts = [x.strip() for x in name.split("|") if x.strip()] or [name]
            n = sum(
                1
                for c in player.characters
                if any(_card_name_has(catalog(c.card_id), o) for o in opts)
            )
            if n > 1:
                return False
    pow_req = int(spec.get("require_char_power_gte") or 0)
    if pow_req > 0:
        ok = False
        for ch in player.characters:
            try:
                raw = catalog(ch.card_id).get("power")
                p = int(str(raw).split()[0].replace(",", "") or 0) + ch.power_mod + ch.don_attached * 1000
            except Exception:
                p = ch.power_mod
            if p >= pow_req:
                ok = True
                break
        if not ok:
            return False
    return True


def _character_cannot_attack(
    state: MatchState, seat: int, ch: CardInst, catalog: CatalogFn
) -> bool:
    """True if this Character is currently barred from attacking."""
    if ch.cannot_attack:
        return True
    from battle.effect_library import get_card_entry

    entry = get_card_entry(ch.card_id)
    foe = state.player(state.other(seat))
    for ability in entry.get("abilities") or []:
        if not any(o.get("op") == "cannot_attack" for o in (ability.get("ops") or [])):
            continue
        # Negated this turn (e.g. OP14-056 after hand trash).
        if ability.get("negated_when_hand_trashed") and ch.effects_negated:
            continue
        need_n = ability.get("require_opp_chars_count_gte")
        need_pow = ability.get("require_opp_chars_base_power_gte")
        if need_n is not None and need_pow is not None:
            # Cannot attack UNLESS opponent has N chars with base power ≥ X.
            count = 0
            for fc in foe.characters:
                info = catalog(fc.card_id)
                try:
                    base = int(info.get("power") or info.get("power_en") or 0)
                except (TypeError, ValueError):
                    base = 0
                if base >= int(need_pow):
                    count += 1
            if count >= int(need_n):
                continue  # condition met → may attack
            return True
        return True
    return False


def _taunt_targets(state: MatchState, owner_seat: int, catalog: CatalogFn) -> list[str]:
    """Iids of rested taunt Characters the opponent must attack."""
    from battle.effect_library import get_card_entry

    owner = state.player(owner_seat)
    out: list[str] = []
    for ch in owner.characters:
        if not ch.rested and not ch.taunt:
            # Library-driven taunt only while rested.
            pass
        entry = get_card_entry(ch.card_id)
        is_taunt = ch.taunt or any(
            o.get("op") == "taunt" for a in (entry.get("abilities") or []) for o in (a.get("ops") or [])
        )
        if not is_taunt:
            continue
        while_rested = any(
            a.get("while_rested") or any(o.get("while_rested") for o in (a.get("ops") or []))
            for a in (entry.get("abilities") or [])
        )
        if while_rested and not ch.rested:
            continue
        if ch.rested or ch.taunt:
            out.append(ch.iid)
    return out


def legal_actions(state: MatchState, seat: int, catalog: CatalogFn) -> list[dict[str, Any]]:
    if state.status != "playing":
        return []
    # 1-2-3: concede is always available while playing (except during opponent-only prompts
    # we still allow it — official: any time).
    concede_action = {"type": "concede"}
    if state.pending_choice and state.pending_choice.seat == seat:
        actions: list[dict[str, Any]] = [concede_action]
        if state.pending_choice.optional:
            actions.append({"type": "skip_choice"})
        for tid in state.pending_choice.options:
            actions.append({"type": "select_choice", "target_iid": tid})
        return actions
    # Waiting on the other player — do not allow voluntary actions that skip their prompt.
    if state.pending_choice and state.pending_choice.seat != seat:
        return [concede_action]
    if state.pending_search and state.pending_search.seat == seat:
        pending = state.pending_search
        if pending.phase == "choose_dest":
            return [
                concede_action,
                {"type": "select_choice", "target_iid": "deck:top"},
                {"type": "select_choice", "target_iid": "deck:bottom"},
            ]
        if pending.phase == "order":
            actions = [concede_action]
            if pending.bottom_order:
                actions.append({"type": "undo_search_order"})
            for idx in range(len(pending.revealed)):
                actions.append(
                    {
                        "type": "order_search_bottom",
                        "index": idx,
                        "card_id": pending.revealed[idx],
                    }
                )
            return actions
        actions = [concede_action, {"type": "skip_search"}]
        if pending.selected:
            actions.append({"type": "confirm_search", "n": len(pending.selected)})
        for idx in pending.eligible:
            actions.append(
                {
                    "type": "select_search",
                    "index": idx,
                    "card_id": pending.revealed[idx],
                    "selected": idx in pending.selected,
                }
            )
        return actions
    if state.pending_search and state.pending_search.seat != seat:
        return [concede_action]
    if state.pending_effect:
        if state.pending_effect.seat != seat:
            return [concede_action]
        pe = state.pending_effect
        return [
            concede_action,
            {
                "type": "confirm_effect",
                "accept": True,
                "source_iid": pe.source_iid,
                "card_id": pe.card_id,
            },
            {
                "type": "confirm_effect",
                "accept": False,
                "source_iid": pe.source_iid,
                "card_id": pe.card_id,
            },
        ]
    # End phase (6-6): wait for interactive resolution; otherwise no voluntary actions
    if state.phase == "end":
        return [concede_action]
    # 5-2-1-6 mulligan
    if state.phase == "mulligan":
        if state.mulligan_seat != seat:
            return [concede_action]
        return [
            concede_action,
            {"type": "mulligan", "redraw": False},
            {"type": "mulligan", "redraw": True},
        ]
    # 10-1-5 Trigger choice
    if state.phase == "trigger" and state.pending_trigger and state.pending_trigger.seat == seat:
        return [
            concede_action,
            {"type": "trigger", "accept": True},
            {"type": "trigger", "accept": False},
        ]
    actions = [concede_action]
    player = state.player(seat)
    # Attack declared; When Attacking / 【对方攻击时】 still settling — no main-phase plays.
    if state.attack and not state.attack.combat_entered:
        return actions
    if state.phase == "block" and state.attack and state.attack.attacker_seat != seat:
        actions.append({"type": "block", "blocker_iid": None})
        attacked_iid = state.attack.target_iid
        for ch in player.characters:
            if ch.iid == attacked_iid:
                continue
            info = catalog(ch.card_id)
            if (not ch.rested) and has_blocker(info, ch, state=state, owner_seat=seat, catalog=catalog):
                if _character_denied_rest(player, ch.iid):
                    continue
                if _blocker_denied(state, state.attack.attacker_seat, ch, catalog):
                    continue
                actions.append({"type": "block", "blocker_iid": ch.iid})
        return actions
    if state.phase == "counter" and state.attack and state.attack.attacker_seat != seat:
        actions.append({"type": "pass_counter"})
        defended = state.attack.blocker_iid or state.attack.target_iid
        buff_targets = ["leader"]
        if defended != "leader":
            buff_targets.append(defended)
        for idx, cid in enumerate(player.hand):
            info = catalog(cid)
            ctype = card_type_of(info)
            counter = effective_counter(state, seat, cid, catalog)
            if ctype == "event":
                if (has_counter_timing(info) or counter > 0) and effective_play_cost(state, seat, cid, catalog) <= player.don_active:
                    if has_main_timing(info) and not has_counter_timing(info) and counter <= 0:
                        continue
                    if counter > 0:
                        for bt in buff_targets:
                            actions.append(
                                {
                                    "type": "counter",
                                    "hand_index": idx,
                                    "card_id": cid,
                                    "counter": counter,
                                    "buff_target": bt,
                                }
                            )
                    else:
                        actions.append(
                            {
                                "type": "counter",
                                "hand_index": idx,
                                "card_id": cid,
                                "counter": 0,
                                "buff_target": defended,
                            }
                        )
            elif ctype == "character" and counter > 0:
                for bt in buff_targets:
                    actions.append(
                        {
                            "type": "counter",
                            "hand_index": idx,
                            "card_id": cid,
                            "counter": counter,
                            "buff_target": bt,
                        }
                    )
        return actions
    if state.phase != "main" or state.turn_seat != seat:
        # Attacker during block/counter (or any non-main wait) — concede only.
        return [concede_action]
    # Play cards
    for idx, cid in enumerate(player.hand):
        info = catalog(cid)
        cost = effective_play_cost(state, seat, cid, catalog)
        ctype = card_type_of(info)
        if cost > player.don_active:
            continue
        if ctype == "event" and not event_playable_in_main(info):
            continue
        if ctype == "character":
            if len(player.characters) < 5:
                actions.append({"type": "play_card", "hand_index": idx, "card_id": cid, "cost": cost, "card_type": ctype})
            else:
                for ch in player.characters:
                    actions.append(
                        {
                            "type": "play_card",
                            "hand_index": idx,
                            "card_id": cid,
                            "cost": cost,
                            "card_type": ctype,
                            "replace_iid": ch.iid,
                        }
                    )
        elif ctype in {"event", "stage"}:
            actions.append({"type": "play_card", "hand_index": idx, "card_id": cid, "cost": cost, "card_type": ctype})
    # 【启动主要】 characters + leader + stages
    ensure_loaded()
    for ch in player.characters:
        info = catalog(ch.card_id)
        if not has_activate_main(info):
            continue
        spec = resolve_activate_spec(ch.card_id, info)
        if not spec:
            continue
        if spec.get("rest_self") and _character_denied_rest(player, ch.iid):
            continue
        if not _activate_spec_legal(
            player,
            spec,
            catalog,
            is_leader=False,
            source_rested=ch.rested,
            source_once_used=ch.once_used,
        ):
            continue
        if not _ability_board_conditions_ok(
            state,
            seat,
            spec,
            catalog,
            don_attached=int(ch.don_attached or 0),
            source_iid=ch.iid,
        ):
            continue
        actions.append(
            {
                "type": "activate_main",
                "source_iid": ch.iid,
                "card_id": ch.card_id,
                "summary": spec.get("summary") or "Activate: Main",
            }
        )
    for st in player.stages:
        info = catalog(st.card_id)
        if not has_activate_main(info):
            continue
        spec = resolve_activate_spec(st.card_id, info)
        if not spec:
            continue
        if not _activate_spec_legal(
            player,
            spec,
            catalog,
            is_leader=False,
            source_rested=st.rested,
            source_once_used=st.once_used,
        ):
            continue
        actions.append(
            {
                "type": "activate_main",
                "source_iid": st.iid,
                "card_id": st.card_id,
                "summary": spec.get("summary") or "Activate: Main",
            }
        )
    leader_info = catalog(player.leader_card_id)
    if has_activate_main(leader_info):
        spec = resolve_activate_spec(player.leader_card_id, leader_info)
        if (
            spec
            and _activate_spec_legal(
                player,
                spec,
                catalog,
                is_leader=True,
                source_rested=player.leader_rested,
                source_once_used=player.leader_once_used,
            )
            and _ability_board_conditions_ok(
                state,
                seat,
                spec,
                catalog,
                don_attached=int(player.leader_don or 0),
                source_iid="leader",
            )
        ):
            actions.append(
                {
                    "type": "activate_main",
                    "source_iid": "leader",
                    "card_id": player.leader_card_id,
                    "summary": spec.get("summary") or "Activate: Main",
                }
            )
    # Attach DON from cost area (6-5-5). Free detach allowed until that unit attacks this turn.
    if player.don_active > 0:
        actions.append({"type": "attach_don", "target_iid": "leader", "amount": 1})
        for ch in player.characters:
            actions.append({"type": "attach_don", "target_iid": ch.iid, "amount": 1})
    locked = set(getattr(player, "attacked_this_turn_iids", None) or [])
    if player.leader_don > 0 and "leader" not in locked:
        actions.append({"type": "remove_don", "target_iid": "leader", "amount": 1})
    for ch in player.characters:
        if int(ch.don_attached or 0) > 0 and ch.iid not in locked:
            actions.append({"type": "remove_don", "target_iid": ch.iid, "amount": 1})
    # Attacks — 6-5-6-1
    if player.turns_completed >= 1:
        foe = state.player(state.other(seat))
        rested_targets = [c.iid for c in foe.characters if c.rested]
        active_targets = [c.iid for c in foe.characters if not c.rested]

        def _char_targets_for(attacker_iid: str) -> list[str]:
            out = list(rested_targets)
            if attacker_iid in player.attack_active_iids:
                out.extend(active_targets)
            return out

        if not player.leader_rested:
            if _leader_denied_attack(player):
                pass
            elif _attack_tax_needed(player, "leader") > len(player.hand):
                pass
            else:
                taunt_tgts = _taunt_targets(state, state.other(seat), catalog)
                if taunt_tgts:
                    for t in taunt_tgts:
                        actions.append({"type": "attack", "attacker_iid": "leader", "target_iid": t})
                else:
                    if not getattr(player, "cannot_attack_opp_leader", False):
                        actions.append({"type": "attack", "attacker_iid": "leader", "target_iid": "leader"})
                    for t in _char_targets_for("leader"):
                        actions.append({"type": "attack", "attacker_iid": "leader", "target_iid": t})
        for ch in player.characters:
            info = catalog(ch.card_id)
            if ch.rested:
                continue
            # Attack declaration rests the attacker (7-1-1). Rest-lock (Hancock OP16-032,
            # ST32-002, etc.) therefore also bars declaring an attack.
            if _character_denied_rest(player, ch.iid):
                continue
            if _character_denied_attack(player, ch.iid):
                continue
            if _character_cannot_attack(state, seat, ch, catalog):
                continue
            tax = _attack_tax_needed(player, ch.iid)
            if tax > len(player.hand):
                continue
            full_rush = has_rush(info, ch, state=state, owner_seat=seat, catalog=catalog)
            char_rush = has_rush_character(info, ch, state=state, owner_seat=seat, catalog=catalog)
            can_leader = (not ch.summoning_sick) or full_rush
            can_char = (not ch.summoning_sick) or full_rush or char_rush
            taunt_tgts = _taunt_targets(state, state.other(seat), catalog)
            if taunt_tgts:
                if can_leader or can_char:
                    for t in taunt_tgts:
                        actions.append({"type": "attack", "attacker_iid": ch.iid, "target_iid": t})
                continue
            if can_leader:
                if not getattr(player, "cannot_attack_opp_leader", False):
                    actions.append({"type": "attack", "attacker_iid": ch.iid, "target_iid": "leader"})
            if can_char:
                for t in _char_targets_for(ch.iid):
                    actions.append({"type": "attack", "attacker_iid": ch.iid, "target_iid": t})
    actions.append({"type": "end_turn"})
    return actions


def apply_action(
    state: MatchState,
    seat: int,
    action: dict[str, Any],
    catalog: CatalogFn,
    ask_llm: LlmFn = None,
) -> dict[str, Any]:
    if state.status != "playing":
        return {"ok": False, "error": "Match is over."}
    legal = legal_actions(state, seat, catalog)
    if not _action_allowed(action, legal):
        return {"ok": False, "error": "Illegal action."}

    kind = str(action.get("type") or "")
    if kind == "mulligan":
        result = _do_mulligan(state, seat, bool(action.get("redraw")), catalog)
    elif kind == "trigger":
        result = _resolve_trigger(state, seat, bool(action.get("accept")), catalog)
    elif kind == "confirm_effect":
        result = _confirm_effect(state, seat, bool(action.get("accept")), catalog)
    elif kind == "select_search":
        result = _toggle_or_resolve_search(state, seat, int(action["index"]), catalog)
    elif kind == "confirm_search":
        pending = state.pending_search
        if not pending or pending.seat != seat or pending.phase != "pick":
            result = {"ok": False, "error": "No pending search to confirm."}
        else:
            result = _resolve_search(state, seat, list(pending.selected), catalog)
    elif kind == "skip_search":
        result = _resolve_search(state, seat, [], catalog)
    elif kind == "order_search_bottom":
        result = _order_search_bottom(state, seat, int(action["index"]), catalog)
    elif kind == "undo_search_order":
        result = _undo_search_order(state, seat)
    elif kind == "select_choice":
        tid = str(action.get("target_iid") or "")
        if (
            state.pending_search
            and state.pending_search.seat == seat
            and state.pending_search.phase == "choose_dest"
            and tid in {"deck:top", "deck:bottom"}
        ):
            result = _resolve_search_dest(state, seat, tid, catalog)
        else:
            result = _resolve_choice(state, seat, tid, catalog)
    elif kind == "skip_choice":
        result = _resolve_choice(state, seat, None, catalog)
    elif kind == "play_card":
        result = _play_card(
            state,
            seat,
            int(action["hand_index"]),
            catalog,
            ask_llm,
            replace_iid=None if action.get("replace_iid") in (None, "", "null") else str(action.get("replace_iid")),
        )
    elif kind == "activate_main":
        result = _activate_main(state, seat, str(action["source_iid"]), catalog)
    elif kind == "attach_don":
        result = _attach_don(state, seat, str(action.get("target_iid") or "leader"), catalog)
    elif kind == "remove_don":
        result = _remove_don(state, seat, str(action.get("target_iid") or "leader"))
    elif kind == "attack":
        result = _declare_attack(state, seat, str(action["attacker_iid"]), str(action["target_iid"]), catalog)
    elif kind == "block":
        blocker = action.get("blocker_iid")
        result = _choose_block(state, seat, None if blocker in (None, "", "null") else str(blocker), catalog)
    elif kind == "counter":
        result = _play_counter(
            state,
            seat,
            int(action["hand_index"]),
            catalog,
            buff_target=str(action.get("buff_target") or (state.attack.target_iid if state.attack else "leader")),
        )
    elif kind == "pass_counter":
        result = _resolve_attack(state, catalog)
    elif kind == "end_turn":
        result = _end_turn(state, catalog)
    elif kind == "concede":
        result = rules_concede(state, seat)
    else:
        result = {"ok": False, "error": "Unknown action."}

    if result.get("ok") and kind != "end_turn":
        _resume_end_phase_if_needed(state, catalog)
        rule_process(state)
    return result


def _action_allowed(action: dict[str, Any], legal: list[dict[str, Any]]) -> bool:
    kind = action.get("type")
    for item in legal:
        if item.get("type") != kind:
            continue
        if kind == "mulligan" and bool(item.get("redraw")) == bool(action.get("redraw")):
            return True
        if kind == "trigger" and bool(item.get("accept")) == bool(action.get("accept")):
            return True
        if kind == "play_card" and int(item.get("hand_index", -1)) == int(action.get("hand_index", -2)):
            left = item.get("replace_iid")
            right = action.get("replace_iid")
            if left in (None, "") and right in (None, "", "null"):
                return True
            if left == right:
                return True
        if kind == "activate_main" and item.get("source_iid") == action.get("source_iid"):
            return True
        if kind == "attach_don" and item.get("target_iid") == action.get("target_iid"):
            return True
        if kind == "remove_don" and item.get("target_iid") == action.get("target_iid"):
            return True
        if kind == "attack" and item.get("attacker_iid") == action.get("attacker_iid") and item.get("target_iid") == action.get("target_iid"):
            return True
        if kind == "block":
            left = item.get("blocker_iid")
            right = action.get("blocker_iid")
            if left in (None, "") and right in (None, "", "null"):
                return True
            if left == right:
                return True
        if kind == "counter" and int(item.get("hand_index", -1)) == int(action.get("hand_index", -2)):
            left = item.get("buff_target")
            right = action.get("buff_target")
            if left in (None, "") or right in (None, "", "null") or left == right:
                return True
        if kind in {"pass_counter", "end_turn", "concede"}:
            return True
        if kind == "confirm_effect" and bool(item.get("accept")) == bool(action.get("accept")):
            return True
        if kind == "select_search" and int(item.get("index", -1)) == int(action.get("index", -2)):
            return True
        if kind == "confirm_search":
            return True
        if kind == "skip_search":
            return True
        if kind == "order_search_bottom" and int(item.get("index", -1)) == int(action.get("index", -2)):
            return True
        if kind == "undo_search_order":
            return True
        if kind == "select_choice" and str(item.get("target_iid") or "") == str(action.get("target_iid") or ""):
            return True
        if kind == "skip_choice":
            return True
    return False


def _do_mulligan(state: MatchState, seat: int, redraw: bool, catalog: CatalogFn) -> dict[str, Any]:
    player = state.player(seat)
    if redraw:
        rng = _rng(state)
        player.deck.extend(player.hand)
        player.hand.clear()
        rng.shuffle(player.deck)
        player.hand = [player.deck.pop(0) for _ in range(min(5, len(player.deck)))]
        state.add_log("play.log.mulligans", name=player.username)
    else:
        state.add_log("play.log.keeps_hand", name=player.username)
    player.mulligan_done = True
    # First player then second (5-2-1-6)
    if seat == state.first_seat:
        other = state.other(seat)
        if not state.player(other).mulligan_done:
            state.mulligan_seat = other
            state.touch()
            return {"ok": True}
    if all(p.mulligan_done for p in state.players):
        _finish_mulligan_and_start(state, catalog)
    else:
        # Second finished before first somehow — wait for remaining
        for i, p in enumerate(state.players):
            if not p.mulligan_done:
                state.mulligan_seat = i
                break
    state.touch()
    return {"ok": True}


def _spend_don(player: PlayerState, cost: int) -> bool:
    if cost > player.don_active:
        return False
    player.don_active -= cost
    player.don_rested += cost
    return True


def _run_pending_effect(state: MatchState, pending: PendingEffect, catalog: CatalogFn) -> None:
    if not pending.ops:
        return
    # Optional / uncertain abilities wait for the controller to accept before applying
    # (and before consuming once-per-turn).
    if pending.uncertain:
        pending.confirmations = {}
        state.pending_effect = pending
        state.add_log("play.log.effect_pending", id=pending.card_id, summary=pending.summary)
        return
    if pending.once:
        player = state.player(pending.seat)
        if pending.source_iid == "leader":
            player.leader_once_used = True
        else:
            inst = next((c for c in player.characters if c.iid == pending.source_iid), None)
            if inst is not None:
                inst.once_used = True
            else:
                stage = next((s for s in player.stages if s.iid == pending.source_iid), None)
                if stage is not None:
                    stage.once_used = True
    logs = apply_ops(state, pending.seat, pending.ops, catalog)
    for line in logs:
        state.add_log(line)
    if not state.pending_search and not state.pending_choice:
        state.add_log("play.log.effect_applied", id=pending.card_id, summary=pending.summary)


def _blocked_by_cannot_play(player: PlayerState, info: dict[str, Any], ctype: str) -> bool:
    """True if this-turn cannot_play_from_hand rules forbid playing this card."""
    if not player.cannot_play_rules:
        return False
    try:
        base_cost = int(info.get("cost") or info.get("cost_en") or 0)
    except (TypeError, ValueError):
        base_cost = 0
    for rule in player.cannot_play_rules:
        want = str(rule.get("card_type") or "any").lower()
        if want not in {"any", ctype}:
            continue
        if rule.get("base_cost_gte") is not None and base_cost < int(rule["base_cost_gte"]):
            continue
        if rule.get("base_cost_lte") is not None and base_cost > int(rule["base_cost_lte"]):
            continue
        return True
    return False


def _play_card(
    state: MatchState,
    seat: int,
    hand_index: int,
    catalog: CatalogFn,
    ask_llm: LlmFn,
    replace_iid: str | None = None,
) -> dict[str, Any]:
    player = state.player(seat)
    if hand_index < 0 or hand_index >= len(player.hand):
        return {"ok": False, "error": "Invalid hand index."}
    cid = player.hand[hand_index]
    info = catalog(cid)
    cost = effective_play_cost(state, seat, cid, catalog)
    ctype = card_type_of(info)
    if ctype == "event" and not event_playable_in_main(info):
        return {"ok": False, "error": "This event is Counter-only."}
    if _blocked_by_cannot_play(player, info, ctype):
        return {"ok": False, "error": "Cannot play this card from hand this turn."}
    if ctype == "character" and len(player.characters) >= 5:
        if not replace_iid or not any(c.iid == replace_iid for c in player.characters):
            return {"ok": False, "error": "Character area is full — choose a character to trash (3-7-6-1)."}
    if not _spend_don(player, cost):
        return {"ok": False, "error": "Not enough active DON!!."}
    # Consume matching next_only temp hand-cost mods after a successful pay.
    kept_mods: list[dict[str, Any]] = []
    consumed_one = False
    for mod in list(getattr(player, "temp_hand_cost_mods", None) or []):
        if consumed_one or not mod.get("next_only"):
            kept_mods.append(mod)
            continue
        name_raw = str(mod.get("name_contains") or "").strip().lower()
        matched = True
        if name_raw:
            blob = " ".join(
                str(x or "")
                for x in (info.get("name"), info.get("name_en"), info.get("name_cn"), cid)
            ).lower()
            parts = [p.strip() for p in name_raw.replace("|", "/").split("/") if p.strip()]
            matched = bool(parts) and any(p in blob for p in parts)
        if matched and (mod.get("cost_gte") is None or printed_cost(info) >= int(mod["cost_gte"])):
            consumed_one = True
            continue
        kept_mods.append(mod)
    player.temp_hand_cost_mods = kept_mods
    leader_colors = normalize_colors(catalog(player.leader_card_id).get("colors_en") or catalog(player.leader_card_id).get("colors"))
    card_colors = normalize_colors(info.get("colors_en") or info.get("colors"))
    if leader_colors and card_colors and leader_colors.isdisjoint(card_colors):
        player.don_active += cost
        player.don_rested -= cost
        return {"ok": False, "error": "Card color does not match Leader."}
    player.hand.pop(hand_index)
    keywords = detect_keywords(info)
    if ctype == "character":
        replace_at: int | None = None
        if len(player.characters) >= 5 and replace_iid:
            replace_at = next((i for i, c in enumerate(player.characters) if c.iid == replace_iid), None)
            removed = _remove_character(player, replace_iid, to_trash=True)
            if removed:
                state.add_log("play.log.trash_for_space", name=player.username, id=removed.card_id)
        rush_full = has_rush(info)
        enter_rested = False
        try:
            from battle.effect_library import get_abilities

            for board_ch in player.characters:
                for ab in get_abilities(board_ch.card_id):
                    if ab.get("characters_enter_rested"):
                        enter_rested = True
                        break
                    if any(o.get("op") == "play_characters_rested" for o in (ab.get("ops") or [])):
                        enter_rested = True
                        break
                if enter_rested:
                    break
            if not enter_rested:
                for ab in get_abilities(player.leader_card_id):
                    if ab.get("characters_enter_rested") or any(
                        o.get("op") == "play_characters_rested" for o in (ab.get("ops") or [])
                    ):
                        enter_rested = True
                        break
        except Exception:
            enter_rested = False
        inst = CardInst(
            iid=new_iid("ch"),
            card_id=cid,
            summoning_sick=not rush_full,
            keywords=keywords,
            rested=enter_rested,
        )
        if replace_at is not None:
            player.characters.insert(min(replace_at, len(player.characters)), inst)
        else:
            player.characters.append(inst)
        state.add_log("play.log.plays", name=player.username, id=cid)
        _after_character_enters(state, seat, inst.iid, cid, catalog, from_zone="hand")
    elif ctype == "stage":
        if player.stages:
            old = player.stages.pop(0)
            player.trash.append(old.card_id)
        inst = CardInst(iid=new_iid("st"), card_id=cid, summoning_sick=False, keywords=keywords)
        player.stages.append(inst)
        state.add_log("play.log.sets_stage", name=player.username, id=cid)
        pending = resolve_ability(
            state, seat, cid, inst.iid, "on_play", info, None, allow_llm=False, catalog=catalog
        )
        if pending and pending.ops:
            _run_pending_effect(state, pending, catalog)
    else:
        player.trash.append(cid)
        state.add_log("play.log.plays_event", name=player.username, id=cid)
        _record_event_activated(state, seat, cid, catalog)
        pending = _resolve_event_play_ability(state, seat, cid, info, catalog)
        if pending and pending.ops:
            _run_pending_effect(state, pending, catalog)
        if state.status == "playing" and not _pending_interactive(state):
            _fire_armed_draw_on_event(state, seat, cid, catalog)
        if state.status == "playing" and not _pending_interactive(state):
            _fire_board_timing(state, seat, "on_event", catalog)
        if state.status == "playing" and not _pending_interactive(state):
            _fire_opp_activation_watchers(state, seat, catalog, kind="event")
    state.touch()
    return {"ok": True}


def _activate_don_cost_to_spend(spec: dict[str, Any]) -> int:
    """DON!! rest cost encoded as cost_don must not double-pay rest_don/return_don as_cost ops."""
    cost = int(spec.get("cost_don") or 0)
    if cost <= 0:
        return 0
    for o in spec.get("ops") or []:
        if not isinstance(o, dict) or not o.get("as_cost"):
            continue
        if o.get("op") in {"rest_don", "return_don"}:
            return 0
    return cost


def _resolve_event_play_ability(
    state: MatchState,
    seat: int,
    cid: str,
    info: dict[str, Any],
    catalog: CatalogFn,
) -> Any:
    pending = resolve_ability(state, seat, cid, cid, "on_play", info, None, allow_llm=False, catalog=catalog)
    if (not pending or not pending.ops):
        pending = resolve_ability(state, seat, cid, cid, "main_start", info, None, allow_llm=False, catalog=catalog)
    return pending


def _activate_main(state: MatchState, seat: int, source_iid: str, catalog: CatalogFn) -> dict[str, Any]:
    player = state.player(seat)
    if source_iid == "leader":
        info = catalog(player.leader_card_id)
        cid = player.leader_card_id
        spec = resolve_activate_spec(cid, info)
        if not spec or not spec.get("ops"):
            return {"ok": False, "error": "No Activate: Main effect."}
        if not _activate_spec_legal(
            player, spec, catalog, is_leader=True, source_rested=player.leader_rested, source_once_used=player.leader_once_used
        ):
            return {"ok": False, "error": "Activate: Main conditions not met."}
        if not _ability_board_conditions_ok(
            state, seat, spec, catalog, don_attached=int(player.leader_don or 0), source_iid="leader"
        ):
            return {"ok": False, "error": "Activate: Main conditions not met."}
        cost = _activate_don_cost_to_spend(spec)
        if cost and not _spend_don(player, cost):
            return {"ok": False, "error": "Not enough DON!!."}
        if spec.get("rest_self"):
            player.leader_rested = True
        ops = list(spec.get("ops") or [])
        for op in ops:
            op.setdefault("source_iid", "leader")
            op.setdefault("card_id", cid)
            if op.get("op") == "buff_self":
                op["source_iid"] = "leader"
            if op.get("op") == "search_deck":
                op["summary"] = str(spec.get("summary") or "")
        logs = apply_ops(state, seat, ops, catalog)
        _stamp_activate_once(state, seat, "leader", bool(spec.get("once")))
        state.add_log("play.log.activate_main", name=player.username, id=cid)
        for line in logs:
            state.add_log(line)
        state.touch()
        return {"ok": True}

    inst = next((c for c in player.characters if c.iid == source_iid), None)
    stage = None if inst else next((s for s in player.stages if s.iid == source_iid), None)
    if not inst and not stage:
        return {"ok": False, "error": "Invalid source."}
    src = inst or stage
    assert src is not None
    info = catalog(src.card_id)
    spec = resolve_activate_spec(src.card_id, info)
    if not spec or not spec.get("ops"):
        return {"ok": False, "error": "No Activate: Main effect."}
    if not _activate_spec_legal(
        player,
        spec,
        catalog,
        is_leader=False,
        source_rested=src.rested,
        source_once_used=src.once_used,
    ):
        return {"ok": False, "error": "Activate: Main conditions not met."}
    if not _ability_board_conditions_ok(
        state,
        seat,
        spec,
        catalog,
        don_attached=int(getattr(src, "don_attached", 0) or 0),
        source_iid=src.iid,
    ):
        return {"ok": False, "error": "Activate: Main conditions not met."}
    cost = _activate_don_cost_to_spend(spec)
    if cost and not _spend_don(player, cost):
        return {"ok": False, "error": "Not enough DON!!."}
    if spec.get("rest_self"):
        if inst is not None and _character_denied_rest(player, src.iid):
            return {"ok": False, "error": "This Character cannot be rested."}
        was_active = not src.rested
        src.rested = True
        if was_active:
            _fire_self_rested(state, seat, src.iid, catalog)
    ops = list(spec.get("ops") or [])
    for op in ops:
        op.setdefault("source_iid", src.iid)
        op.setdefault("card_id", src.card_id)
        if op.get("op") == "buff_self":
            op["source_iid"] = src.iid
        if op.get("op") == "search_deck":
            op["summary"] = str(spec.get("summary") or "")
    logs = apply_ops(state, seat, ops, catalog)
    _stamp_activate_once(state, seat, src.iid, bool(spec.get("once")))
    state.add_log("play.log.activate_main", name=player.username, id=src.card_id)
    for line in logs:
        state.add_log(line)
    state.touch()
    return {"ok": True}


def _set_activate_once_used(state: MatchState, seat: int, source_iid: str) -> None:
    player = state.player(seat)
    if source_iid == "leader":
        player.leader_once_used = True
        return
    inst = next((c for c in player.characters if c.iid == source_iid), None)
    if inst is not None:
        inst.once_used = True
        return
    stage = next((s for s in player.stages if s.iid == source_iid), None)
    if stage is not None:
        stage.once_used = True


def _stamp_activate_once(state: MatchState, seat: int, source_iid: str, once: bool) -> None:
    """Mark once-per-turn only after cost is paid; defer while a choice/search is open."""
    if not once:
        return
    if state.pending_choice is not None:
        state.pending_choice.mark_once = True
        state.pending_choice.mark_once_source_iid = source_iid
        return
    if _pending_interactive(state):
        # Search / effect confirm still open — treat as paid activation (cost already applied).
        _set_activate_once_used(state, seat, source_iid)
        return
    _set_activate_once_used(state, seat, source_iid)


def _propagate_or_commit_once(state: MatchState, pending: PendingChoice, controller: int, *, paid: bool) -> None:
    """After resolving a choice: decline as_cost → no once; else commit or re-stamp."""
    if not pending.mark_once:
        return
    src = pending.mark_once_source_iid or pending.source_iid
    if not paid:
        return
    if state.pending_choice is not None:
        state.pending_choice.mark_once = True
        state.pending_choice.mark_once_source_iid = src
        return
    if _pending_interactive(state):
        _set_activate_once_used(state, controller, src)
        return
    _set_activate_once_used(state, controller, src)


def _attach_don(state: MatchState, seat: int, target_iid: str, catalog: CatalogFn) -> dict[str, Any]:
    player = state.player(seat)
    if player.don_active <= 0:
        return {"ok": False, "error": "No active DON!!."}
    player.don_active -= 1
    if target_iid == "leader":
        player.leader_don += 1
        src_cid = player.leader_card_id
        src_iid = "leader"
    else:
        inst = next((c for c in player.characters if c.iid == target_iid), None)
        if not inst:
            player.don_active += 1
            return {"ok": False, "error": "Invalid DON target."}
        inst.don_attached += 1
        src_cid = inst.card_id
        src_iid = inst.iid
    state.add_log("play.log.attach_don", name=player.username)
    info = catalog(src_cid)
    pending = resolve_ability(
        state, seat, src_cid, src_iid, "on_don_attached", info, None, allow_llm=False, catalog=catalog
    )
    if pending and pending.ops:
        _run_pending_effect(state, pending, catalog)
    # Board watchers: "when this Leader or 1 of your Characters is given a DON!!"
    watchers: list[tuple[str, str, dict[str, Any]]] = []
    lead_info = catalog(player.leader_card_id)
    if src_iid != "leader" or True:
        watchers.append((player.leader_card_id, "leader", lead_info))
    for ch in player.characters:
        watchers.append((ch.card_id, ch.iid, catalog(ch.card_id)))
    seen_src = {(src_cid, src_iid)}
    for w_cid, w_iid, w_info in watchers:
        if (w_cid, w_iid) in seen_src and w_iid == src_iid:
            # Target already resolved above; still allow watchers with on_any_own_don_attach
            pass
        pending_w = resolve_ability(
            state, seat, w_cid, w_iid, "on_don_attached", w_info, None, allow_llm=False, catalog=catalog
        )
        if not pending_w or not pending_w.ops:
            continue
        # Prefer library ability flag
        from battle.effect_library import get_abilities, ability_is_runnable

        watch_ok = False
        for ab in get_abilities(w_cid, "on_don_attached"):
            if ability_is_runnable(ab) and ab.get("on_any_own_don_attach"):
                watch_ok = True
                break
        if not watch_ok:
            continue
        if w_iid == src_iid:
            continue  # already fired as target
        if pending_w.ops:
            _run_pending_effect(state, pending_w, catalog)
            if _pending_interactive(state):
                break
    state.touch()
    return {"ok": True}


def _remove_don(state: MatchState, seat: int, target_iid: str) -> dict[str, Any]:
    player = state.player(seat)
    locked = set(getattr(player, "attacked_this_turn_iids", None) or [])
    if target_iid in locked:
        return {"ok": False, "error": "Cannot remove DON!! after this card attacked this turn."}
    if target_iid == "leader":
        if player.leader_don <= 0:
            return {"ok": False, "error": "No DON!! attached to Leader."}
        player.leader_don -= 1
    else:
        inst = next((c for c in player.characters if c.iid == target_iid), None)
        if not inst:
            return {"ok": False, "error": "Invalid DON target."}
        if inst.don_attached <= 0:
            return {"ok": False, "error": "No DON!! attached to Character."}
        inst.don_attached -= 1
    player.don_active += 1
    state.add_log("play.log.remove_don", name=player.username)
    state.touch()
    return {"ok": True}


def _try_enter_combat_steps(state: MatchState, catalog: CatalogFn) -> None:
    """Enter Block/Counter only after When Attacking (and then 【对方攻击时】) settle.

    Unblockable attacks skip Block → Counter. Stamping ``phase=counter`` while the
    attacker still had a When Attacking prompt kept hotseat ``_acting_seat`` on the
    attacker, so the board never flipped to the defender.
    """
    attack = state.attack
    if not attack or state.status != "playing" or attack.combat_entered:
        return
    if _pending_interactive(state):
        return
    if not attack.opp_attack_watchers_done:
        attack.opp_attack_watchers_done = True
        def_seat = state.other(attack.attacker_seat)
        if str(attack.target_iid or "") == "leader":
            _fire_board_timing(state, def_seat, "on_own_leader_battle", catalog)
            if state.status != "playing" or _pending_interactive(state):
                return
        _fire_board_timing(state, def_seat, rule_timings.ON_OPPONENT_ATTACK, catalog)
        if state.status != "playing" or _pending_interactive(state):
            return
    if not combatants_present(state):
        cancel_battle(state)
        rule_process(state)
        return
    phase = str(attack.combat_phase or "block")
    if phase not in {"block", "counter"}:
        phase = "block"
    state.phase = phase
    attack.combat_entered = True
    atk = state.player(attack.attacker_seat)
    if phase == "counter":
        state.add_log(
            "play.log.attack_blockerless",
            name=atk.username,
            attacker=attack.attacker_iid,
            target=attack.target_iid,
            power=attack.declared_power,
        )
    else:
        state.add_log(
            "play.log.attack",
            name=atk.username,
            attacker=attack.attacker_iid,
            target=attack.target_iid,
            power=attack.declared_power,
        )
    rule_process(state)
    state.touch()


def _resume_trigger_tail(state: MatchState, catalog: CatalogFn) -> bool:
    """
    Finish Trigger aftermath after a nested choice/search/effect clears.

    Without this, phase can stay ``trigger`` with ``pending_trigger is None`` and
    ``attack.combat_entered`` already True — nobody acts (AI / hotseat freeze).
    """
    if state.status != "playing" or _pending_interactive(state):
        return False
    resume = getattr(state, "trigger_resume", None)
    orphan = state.phase == "trigger" and state.pending_trigger is None
    if not resume and not orphan:
        return False

    remaining = 0
    banish = False
    seat = state.turn_seat
    if isinstance(resume, dict):
        try:
            seat = int(resume.get("seat", seat))
        except (TypeError, ValueError):
            seat = state.turn_seat
        try:
            remaining = int(resume.get("remaining_hits") or 0)
        except (TypeError, ValueError):
            remaining = 0
        banish = bool(resume.get("banish"))
    state.trigger_resume = None

    if remaining > 0:
        paused = _deal_leader_damage_batch(state, seat, catalog, hits=remaining, banish=banish)
        if paused or _pending_interactive(state):
            return True

    # Trigger chain done — leave battle and return to main.
    if not _pending_interactive(state):
        state.attack = None
        if state.status == "playing" and state.phase == "trigger":
            state.phase = "main"
    rule_process(state)
    state.touch()
    return True


def _finish_cleared_interactive(state: MatchState, catalog: CatalogFn) -> None:
    """Shared post-choice / post-effect progress (combat enter + trigger tail + board resume)."""
    if state.status != "playing" or _pending_interactive(state):
        return
    _try_enter_combat_steps(state, catalog)
    if state.status != "playing" or _pending_interactive(state):
        return
    _resume_trigger_tail(state, catalog)
    if state.status != "playing" or _pending_interactive(state):
        return
    _resume_board_timing(state, catalog)
    if state.status != "playing" or _pending_interactive(state):
        return
    _resume_end_phase_if_needed(state, catalog)


def _declare_attack(
    state: MatchState,
    seat: int,
    attacker_iid: str,
    target_iid: str,
    catalog: CatalogFn,
) -> dict[str, Any]:
    player = state.player(seat)
    foe = state.player(state.other(seat))
    if player.turns_completed == 0:
        return {"ok": False, "error": "Cannot attack on your first turn."}
    if target_iid != "leader":
        tgt = next((c for c in foe.characters if c.iid == target_iid), None)
        if not tgt or not tgt.rested:
            return {"ok": False, "error": "Can only attack Leader or rested Characters (7-1-1-2)."}
        # OP12-020-style: cannot attack Characters with printed base cost ≤ N this turn.
        lim = player.cannot_attack_char_base_cost_lte
        if lim is not None:
            try:
                if printed_cost(catalog(tgt.card_id)) <= int(lim):
                    return {"ok": False, "error": f"Cannot attack Characters with base cost ≤{lim} this turn."}
            except Exception:
                pass
    attacker_info = None
    attacker_inst = None
    tax = _attack_tax_needed(player, attacker_iid)
    if tax > len(player.hand):
        return {"ok": False, "error": "Not enough hand cards to pay attack tax."}
    if attacker_iid == "leader":
        if _leader_denied_attack(player):
            return {"ok": False, "error": "Leader cannot attack this turn."}
        if player.leader_rested:
            return {"ok": False, "error": "Leader is rested."}
        player.leader_rested = True
        attacker_info = catalog(player.leader_card_id)
    else:
        inst = next((c for c in player.characters if c.iid == attacker_iid), None)
        if not inst or inst.rested:
            return {"ok": False, "error": "Invalid attacker."}
        if _character_denied_rest(player, attacker_iid):
            return {"ok": False, "error": "This Character cannot be rested."}
        if _character_denied_attack(player, attacker_iid):
            return {"ok": False, "error": "This Character cannot attack."}
        info = catalog(inst.card_id)
        if inst.summoning_sick:
            if target_iid == "leader" and not has_rush(
                info, inst, state=state, owner_seat=seat, catalog=catalog
            ):
                return {"ok": False, "error": "Cannot attack Leader this turn (no Rush)."}
            if target_iid != "leader" and not (
                has_rush(info, inst, state=state, owner_seat=seat, catalog=catalog)
                or has_rush_character(info, inst, state=state, owner_seat=seat, catalog=catalog)
            ):
                return {"ok": False, "error": "Cannot attack this turn (summoning sickness)."}
        inst.rested = True
        attacker_info = info
        attacker_inst = inst
        _fire_self_rested(state, seat, attacker_iid, catalog)
    # Lock attached DON!! on this attacker for the rest of the turn.
    if attacker_iid not in player.attacked_this_turn_iids:
        player.attacked_this_turn_iids.append(attacker_iid)
    # Pay attack tax (trash N from hand) before When Attacking.
    if tax > 0:
        for _ in range(tax):
            if not player.hand:
                break
            player.trash.append(player.hand.pop(0))
        state.add_log("play.log.trash_hand", name=player.username, n=tax)
    # When Attacking abilities first (may change base power this turn) — 7-1 / 10-2-2
    if attacker_info:
        atk_cid = player.leader_card_id if attacker_iid == "leader" else (attacker_inst.card_id if attacker_inst else "")
        atk_src = attacker_iid
        if atk_cid:
            state._attack_target_iid = target_iid
            try:
                pending = resolve_ability(
                    state, seat, atk_cid, atk_src, rule_timings.WHEN_ATTACKING, attacker_info, None, allow_llm=False, catalog=catalog
                )
                if pending and pending.ops:
                    _run_pending_effect(state, pending, catalog)
            finally:
                state._attack_target_iid = None
    if attacker_iid == "leader":
        if _fire_board_timing(state, seat, "on_own_leader_battle", catalog):
            if state.status != "playing":
                return {"ok": True}
            if _pending_interactive(state):
                return {"ok": True}
    power = inst_power(state, seat, attacker_iid, catalog)
    blockerless = bool(
        attacker_info
        and (
            has_blockerless(attacker_info, attacker_inst)
            or (
                attacker_iid == "leader"
                and "blockerless" in live_leader_keywords(state, seat, catalog)
            )
        )
    )
    state.attack = PendingAttack(
        attacker_seat=seat,
        attacker_iid=attacker_iid,
        target_iid=target_iid,
        declared_power=power,
        combat_phase="counter" if blockerless else "block",
    )
    # Keep phase=main while When Attacking is interactive; then 【对方攻击时】 → Block/Counter.
    _try_enter_combat_steps(state, catalog)
    if state.status != "playing":
        return {"ok": True}
    state.touch()
    return {"ok": True}


def _choose_block(state: MatchState, seat: int, blocker_iid: str | None, catalog: CatalogFn) -> dict[str, Any]:
    if not state.attack:
        return {"ok": False, "error": "No attack."}
    if blocker_iid:
        player = state.player(seat)
        inst = next((c for c in player.characters if c.iid == blocker_iid), None)
        if not inst:
            return {"ok": False, "error": "Invalid blocker."}
        if _character_denied_rest(player, blocker_iid):
            return {"ok": False, "error": "This Character cannot be rested."}
        inst.rested = True
        state.attack.blocker_iid = blocker_iid
        state.attack.target_iid = blocker_iid
        state.add_log("play.log.blocks", name=player.username, id=inst.card_id)
        # 7-1-2-2 / 10-2-6: 【阻挡时】
        info = catalog(inst.card_id)
        pending = resolve_ability(
            state, seat, inst.card_id, blocker_iid, rule_timings.ON_BLOCK, info, None, allow_llm=False, catalog=catalog
        )
        if pending and pending.ops:
            _run_pending_effect(state, pending, catalog)
        # Opponent activated Blocker → fire attacker's on_opp_blocker watchers (e.g. OP09-118, OP06-048).
        atk_seat = state.attack.attacker_seat if state.attack else state.other(seat)
        _fire_flagged_board_abilities(
            state,
            atk_seat,
            catalog,
            timings=("your_turn", "opponent_turn"),
            trigger_on="opp_blocker",
        )
        if not combatants_present(state):
            cancel_battle(state)
            rule_process(state)
            return {"ok": True}
    else:
        state.add_log("play.log.no_block", name=state.player(seat).username)
    if state.status == "playing" and state.attack:
        state.phase = "counter"
    rule_process(state)
    state.touch()
    return {"ok": True}


def _play_counter(
    state: MatchState,
    seat: int,
    hand_index: int,
    catalog: CatalogFn,
    buff_target: str = "leader",
) -> dict[str, Any]:
    if not state.attack:
        return {"ok": False, "error": "No attack."}
    player = state.player(seat)
    cid = player.hand.pop(hand_index)
    info = catalog(cid)
    cost = effective_play_cost(state, seat, cid, catalog)
    if card_type_of(info) == "event":
        if not _spend_don(player, cost):
            player.hand.insert(hand_index, cid)
            return {"ok": False, "error": "Not enough DON!! for counter event."}
    player.trash.append(cid)
    bonus = effective_counter(state, seat, cid, catalog)
    if bonus > 0:
        key = buff_target if buff_target else "leader"
        state.attack.counter_buffs[key] = state.attack.counter_buffs.get(key, 0) + bonus
        state.add_log("play.log.counters", name=player.username, id=cid, bonus=bonus, target=key)
    else:
        state.add_log("play.log.counter_event", name=player.username, id=cid)
    # Text-based Counter event effects (library / templates; no live LLM mid-battle)
    if card_type_of(info) == "event":
        _record_event_activated(state, seat, cid, catalog)
    if card_type_of(info) == "event" and has_counter_timing(info):
        pending = resolve_ability(state, seat, cid, cid, "counter_event", info, None, allow_llm=False, catalog=catalog)
        if pending and pending.ops:
            _run_pending_effect(state, pending, catalog)
        else:
            # Fall back to on_play-shaped counter text when timing tag is shared
            pending = resolve_ability(
                state, seat, cid, cid, "on_play", info, None, allow_llm=False, catalog=catalog
            )
            if pending and pending.ops and not bonus:
                _run_pending_effect(state, pending, catalog)
    if state.status == "playing" and not _pending_interactive(state):
        if card_type_of(info) == "event":
            _fire_armed_draw_on_event(state, seat, cid, catalog)
        if state.status == "playing" and not _pending_interactive(state) and card_type_of(info) == "event":
            _fire_board_timing(state, seat, "on_event", catalog)
        if state.status == "playing" and not _pending_interactive(state):
            _fire_opp_activation_watchers(state, seat, catalog, kind="event")
    state.touch()
    return {"ok": True}


def _resolve_attack(state: MatchState, catalog: CatalogFn) -> dict[str, Any]:
    attack = state.attack
    if not attack:
        state.phase = "main"
        return {"ok": True}
    # 7-1-3-1-3: if attacker or target left during Counter step, cancel damage
    if not combatants_present(state):
        cancel_battle(state)
        rule_process(state)
        return {"ok": True}
    atk_seat = attack.attacker_seat
    def_seat = state.other(atk_seat)
    atk_power = inst_power(state, atk_seat, attack.attacker_iid, catalog)
    target_iid = attack.blocker_iid or attack.target_iid
    def_power = inst_power(state, def_seat, "leader" if target_iid == "leader" else target_iid, catalog)
    double = False
    banish = False
    attacker_player = state.player(atk_seat)
    if attack.attacker_iid == "leader":
        info = catalog(attacker_player.leader_card_id)
        lead_keys = live_leader_keywords(state, atk_seat, catalog)
        double = "double_attack" in lead_keys
        banish = "banish" in lead_keys
    else:
        inst = next((c for c in attacker_player.characters if c.iid == attack.attacker_iid), None)
        if not inst:
            cancel_battle(state)
            rule_process(state)
            return {"ok": True}
        info = catalog(inst.card_id)
        double = has_double_attack(info, inst)
        banish = has_banish(info, inst)

    hits = 2 if double and target_iid == "leader" else 1
    success = atk_power >= def_power

    # OP12-020: if Leader battles an opponent Character this turn, set Leader active.
    if (
        attack.attacker_iid == "leader"
        and getattr(attacker_player, "untap_on_char_battle", False)
        and (attack.target_iid != "leader" or (attack.blocker_iid and attack.blocker_iid != "leader"))
    ):
        attacker_player.leader_rested = False
        state.add_log("play.log.effect_applied", summary="untap_on_char_battle")

    if target_iid == "leader":
        if success:
            paused = _deal_leader_damage_batch(state, def_seat, catalog, hits=hits, banish=banish)
            if paused:
                return {"ok": True}
        else:
            state.add_log("play.log.attack_leader_fails")
    elif success:
        defender = state.player(def_seat)
        inst = next((c for c in defender.characters if c.iid == target_iid), None)
        if inst:
            # Counter/protection: trash 1 hand instead of battle KO.
            if defender.replace_battle_ko and defender.hand:
                cid = defender.hand.pop(0)
                defender.trash.append(cid)
                state.add_log("play.log.trashes", name=defender.username, id=cid)
                state.add_log("play.log.effect_applied", summary="replace_battle_ko")
            else:
                from battle.leave_replace import stash_replace_resume, try_replace_leave

                if try_replace_leave(
                    state, def_seat, inst, by_opponent=True, catalog=catalog
                ):
                    if stash_replace_resume(
                        state,
                        leave_kind="battle_ko",
                        apply_seat=int(getattr(state.attack, "attacker_seat", 0) or 0),
                    ):
                        state.touch()
                        return {"ok": True}
                else:
                    apply_battle_character_ko(state, def_seat, inst, catalog)
                    # Keep On K.O. / leave prompts; do not let rule_process (e.g. decks_out)
                    # wipe pending_choice via set_loser before the controller finishes.
                    if (
                        state.pending_choice
                        or state.pending_search
                        or state.pending_effect
                        or state.pending_trigger
                    ):
                        _clear_battle_deny_blocker(state)
                        state.attack = None
                        if state.status == "playing":
                            state.phase = "main"
                        state.touch()
                        return {"ok": True}
    else:
        state.add_log("play.log.attack_fails")

    _clear_battle_deny_blocker(state)
    state.attack = None
    if state.status == "playing":
        state.phase = "main"
    rule_process(state)
    state.touch()
    return {"ok": True}


def _deal_leader_damage_batch(
    state: MatchState,
    seat: int,
    catalog: CatalogFn,
    hits: int,
    banish: bool,
) -> bool:
    """Deal up to `hits` life damage. Returns True if paused on Trigger choice."""
    for i in range(hits):
        if state.status != "playing":
            return False
        remaining = hits - 1 - i
        paused = _deal_one_life_damage(state, seat, catalog, banish=banish, remaining_hits=remaining)
        if paused:
            return True
    return False


def _offer_replace_life_damage(
    state: MatchState,
    seat: int,
    catalog: CatalogFn,
    *,
    banish: bool,
    remaining_hits: int,
) -> bool:
    """Optional 「即將受到傷害時，可廢棄這張角色卡代替」. True if paused for a choice."""
    if state.pending_choice or state.pending_trigger or state.pending_search or state.pending_effect:
        return False
    from battle.effect_library import ability_is_runnable, get_abilities

    player = state.player(seat)
    options: list[str] = []
    card_id = ""
    for ch in list(player.characters):
        hit = False
        for timing in ("your_turn", "opponent_turn"):
            for ab in get_abilities(ch.card_id, timing):
                if not ability_is_runnable(ab):
                    continue
                if any(str(o.get("op") or "") == "replace_life_damage" for o in (ab.get("ops") or [])):
                    hit = True
                    card_id = ch.card_id
                    break
            if hit:
                break
        if hit:
            options.append(ch.iid)
    if not options:
        return False
    state.pending_choice = PendingChoice(
        seat=seat,
        card_id=card_id,
        source_iid=options[0],
        target_kind="own_character",
        options=options,
        remaining_ops=[
            {
                "op": "_life_damage_resume",
                "seat": seat,
                "banish": banish,
                "remaining_hits": int(remaining_hits or 0),
            }
        ],
        optional=True,
        summary="You may trash this Character instead of taking damage",
        purpose="replace_life_damage",
    )
    state.add_log({"key": "play.log.choice_offer", "name": player.username})
    state.touch()
    return True


def _deal_one_life_damage(
    state: MatchState,
    seat: int,
    catalog: CatalogFn,
    banish: bool = False,
    remaining_hits: int = 0,
    skip_replace: bool = False,
) -> bool:
    """
    Returns True if the game paused for optional Trigger (10-1-5).
    """
    player = state.player(seat)
    if not skip_replace and _offer_replace_life_damage(
        state, seat, catalog, banish=banish, remaining_hits=remaining_hits
    ):
        return True
    if not player.life:
        # 1-2-1-1-1: life already 0 and Leader takes damage → defeat at rule processing
        mark_pending_defeat(state, seat, "play.log.damage_at_zero", name=player.username)
        rule_process(state)
        return False
    card_id = player.life.pop(0)
    # Keep life_face aligned with remaining Life (index 0 = top / damage order).
    if player.life_face:
        player.life_face.pop(0)
    while len(player.life_face) > len(player.life):
        player.life_face.pop()
    while len(player.life_face) < len(player.life):
        player.life_face.append(False)
    try:
        fire_on_life_damage(state, seat, catalog)
    except Exception:
        pass
    if banish:
        player.trash.append(card_id)
        state.add_log("play.log.life_banish", name=player.username, left=len(player.life))
        try:
            if fire_life_leave(state, seat, catalog):
                return True
        except Exception:
            pass
        return False
    info = catalog(card_id)
    if card_has_trigger(info):
        ops = []
        for raw in resolve_trigger_ops(card_id, info):
            op = dict(raw)
            op.setdefault("card_id", card_id)
            op.setdefault("source_iid", card_id)
            ops.append(op)
        summary = f"Trigger on {card_id}"
        try:
            from battle.effect_library import lookup_runnable_ability

            ab = lookup_runnable_ability(card_id, "trigger")
            if ab and ab.get("summary"):
                summary = str(ab.get("summary"))[:240]
            elif info.get("effect"):
                # Prefer trigger clause from paper text when present.
                import re as _re

                m = _re.search(r"(【觸發器】|【触发器】|【触发】|\[Trigger\])[^\n【\[]*", str(info.get("effect") or ""))
                if m:
                    summary = m.group(0).strip()[:240]
        except Exception:
            pass
        state.pending_trigger = PendingTrigger(
            seat=seat,
            card_id=card_id,
            ops=ops,
            remaining_hits=remaining_hits,
            banish=banish,
            summary=summary,
        )
        state.phase = "trigger"
        state.add_log("play.log.trigger_offer", name=player.username, id=card_id)
        state.touch()
        return True
    player.hand.append(card_id)
    state.add_log("play.log.life_taken", name=player.username, left=len(player.life))
    try:
        if fire_life_leave(state, seat, catalog):
            return True
    except Exception:
        pass
    return False


def _resolve_trigger(state: MatchState, seat: int, accept: bool, catalog: CatalogFn) -> dict[str, Any]:
    pending = state.pending_trigger
    if not pending or pending.seat != seat:
        return {"ok": False, "error": "No pending Trigger."}
    player = state.player(seat)
    card_id = pending.card_id
    remaining = pending.remaining_hits
    banish = pending.banish
    state.pending_trigger = None
    state.trigger_resume = None
    if accept:
        # Park in trash first so 「使這張卡片登場」can find self_card (10-1-5-3
        # default destination is trash unless the effect plays the card).
        state.add_log("play.log.trigger_yes", name=player.username, id=card_id)
        player.trash.append(card_id)
        if pending.ops:
            stamped = []
            for raw in pending.ops:
                op = dict(raw)
                op.setdefault("card_id", card_id)
                op.setdefault("source_iid", card_id)
                stamped.append(op)
            logs = apply_ops(state, seat, stamped, catalog)
            for line in logs:
                state.add_log(line)
        if state.status == "playing" and not _pending_interactive(state):
            _fire_trigger_activation_watchers(state, seat, catalog)
    else:
        player.hand.append(card_id)
        state.add_log("play.log.trigger_no", name=player.username, id=card_id)
    try:
        if state.status == "playing" and not _pending_interactive(state):
            fire_life_leave(state, seat, catalog)
    except Exception:
        pass
    # Nested choice/search/effect from Trigger ops — stash remaining hits and wait.
    if state.status == "playing" and _pending_interactive(state):
        state.trigger_resume = {
            "seat": seat,
            "remaining_hits": int(remaining or 0),
            "banish": bool(banish),
        }
        rule_process(state)
        state.touch()
        return {"ok": True}
    # Continue remaining double-attack hits
    if remaining > 0 and state.status == "playing" and not _pending_interactive(state):
        paused = _deal_leader_damage_batch(state, seat, catalog, hits=remaining, banish=banish)
        if paused:
            return {"ok": True}
    # Finish battle
    if not _pending_interactive(state):
        state.attack = None
        if state.status == "playing":
            state.phase = "main"
    rule_process(state)
    state.touch()
    return {"ok": True}


def _end_turn(state: MatchState, catalog: CatalogFn) -> dict[str, Any]:
    # 6-6 End phase pipeline
    state.phase = "end"
    state.end_phase_step = "your_end"
    state.attack = None
    return _continue_end_phase(state, catalog)


def _check_winner(state: MatchState) -> None:
    """Compatibility wrapper — prefer Ch.9 rule_process."""
    rule_process(state)


def _confirm_effect(state: MatchState, seat: int, accept: bool, catalog: CatalogFn) -> dict[str, Any]:
    pending = state.pending_effect
    if not pending:
        return {"ok": False, "error": "No pending effect."}
    # Only the effect controller accepts / declines optional activations.
    if seat != pending.seat:
        return {"ok": False, "error": "Waiting for the effect controller."}
    pending.confirmations[seat] = accept
    if not accept:
        from battle.leave_replace import finish_optional_replace

        if getattr(state, "pending_replace", None):
            logs = finish_optional_replace(state, catalog, accept=False)
            for line in logs:
                state.add_log(line)
        else:
            state.add_log("play.log.effect_skipped")
            state.pending_effect = None
        state.touch()
        if state.status == "playing" and not _pending_interactive(state):
            _finish_cleared_interactive(state, catalog)
        return {"ok": True}
    # Accept: consume once-per-turn, then resolve ops.
    if getattr(state, "pending_replace", None):
        from battle.leave_replace import finish_optional_replace

        logs = finish_optional_replace(state, catalog, accept=True)
        for line in logs:
            state.add_log(line)
        state.touch()
        if state.status == "playing" and not _pending_interactive(state):
            _finish_cleared_interactive(state, catalog)
        return {"ok": True}
    if pending.once:
        player = state.player(pending.seat)
        if pending.source_iid == "leader":
            player.leader_once_used = True
        else:
            inst = next((c for c in player.characters if c.iid == pending.source_iid), None)
            if inst is not None:
                inst.once_used = True
            else:
                stage = next((s for s in player.stages if s.iid == pending.source_iid), None)
                if stage is not None:
                    stage.once_used = True
    for op in pending.ops:
        op.setdefault("card_id", pending.card_id)
        op.setdefault("source_iid", pending.source_iid)
        if op.get("op") == "search_deck":
            op.setdefault("card_id", pending.card_id)
            op.setdefault("source_iid", pending.source_iid)
    logs = apply_ops(state, pending.seat, pending.ops, catalog)
    for line in logs:
        state.add_log(line)
    if not state.pending_search and not state.pending_choice:
        state.add_log("play.log.effect_applied", id=pending.card_id, summary=pending.summary)
    state.pending_effect = None
    state.touch()
    if state.status == "playing" and not _pending_interactive(state):
        _finish_cleared_interactive(state, catalog)
    return {"ok": True}


def _resolve_choice(state: MatchState, seat: int, target_iid: str | None, catalog: CatalogFn) -> dict[str, Any]:
    pending = state.pending_choice
    if not pending or pending.seat != seat:
        return {"ok": False, "error": "No pending choice."}
    if pending.purpose == "replace_life_damage":
        if target_iid is not None and target_iid not in pending.options:
            return {"ok": False, "error": "Invalid choice target."}
        resume = (pending.remaining_ops or [{}])[0] if pending.remaining_ops else {}
        try:
            remaining = int(resume.get("remaining_hits") or 0)
        except (TypeError, ValueError):
            remaining = 0
        banish = bool(resume.get("banish"))
        try:
            dmg_seat = int(resume.get("seat", seat))
        except (TypeError, ValueError):
            dmg_seat = seat
        player = state.player(dmg_seat)
        state.pending_choice = None
        if target_iid is not None:
            inst = next((c for c in player.characters if c.iid == target_iid), None)
            if inst is not None:
                if inst.don_attached:
                    player.don_rested = int(player.don_rested or 0) + int(inst.don_attached or 0)
                    inst.don_attached = 0
                player.characters = [c for c in player.characters if c.iid != inst.iid]
                player.trash.append(inst.card_id)
                state.add_log(
                    {"key": "play.log.effect_applied", "summary": "replace_life_damage", "id": inst.card_id}
                )
            if remaining > 0 and state.status == "playing":
                paused = _deal_leader_damage_batch(
                    state, dmg_seat, catalog, hits=remaining, banish=banish
                )
                if paused:
                    state.touch()
                    return {"ok": True}
        else:
            paused = _deal_one_life_damage(
                state,
                dmg_seat,
                catalog,
                banish=banish,
                remaining_hits=remaining,
                skip_replace=True,
            )
            if paused:
                state.touch()
                return {"ok": True}
            if remaining > 0 and state.status == "playing":
                paused = _deal_leader_damage_batch(
                    state, dmg_seat, catalog, hits=remaining, banish=banish
                )
                if paused:
                    state.touch()
                    return {"ok": True}
        state.touch()
        if state.status == "playing" and not _pending_interactive(state):
            _finish_cleared_interactive(state, catalog)
        return {"ok": True}
    if pending.purpose == "replace_leave":
        if target_iid is not None and target_iid not in pending.options:
            return {"ok": False, "error": "Invalid choice target."}
        from battle.leave_replace import finish_optional_replace

        state.pending_choice = None
        logs = finish_optional_replace(
            state, catalog, accept=target_iid is not None, target_iid=target_iid
        )
        for line in logs:
            state.add_log(line)
        state.touch()
        if state.status == "playing" and not _pending_interactive(state):
            _finish_cleared_interactive(state, catalog)
        return {"ok": True}
    remaining = list(pending.remaining_ops or [])
    then_op = pending.then_op
    target_kind = pending.target_kind
    controller = pending.controller_seat if pending.controller_seat is not None else seat
    state.pending_choice = None
    if target_iid is None:
        # Skip optional choice
        first = remaining[0] if remaining else None
        # Colon-cost declined: cancel everything after the colon (do not run remaining).
        if isinstance(first, dict) and first.get("as_cost"):
            paid = 0
            try:
                paid = int(getattr(state.player(controller), "_last_trash_hand_count", 0) or 0)
            except Exception:
                paid = 0
            # Any-number cost already paid at least once: stop trashing and resolve the rest.
            if first.get("op") == "trash_hand" and first.get("any_number") and paid > 0:
                rest = remaining[1:]
                if rest:
                    logs = apply_ops(state, controller, rest, catalog)
                    for line in logs:
                        state.add_log(line)
                _propagate_or_commit_once(state, pending, controller, paid=True)
                state.touch()
                if state.status == "playing" and not _pending_interactive(state):
                    _finish_cleared_interactive(state, catalog)
                return {"ok": True}
            rest_paid = 0
            try:
                rest_paid = int(getattr(state.player(controller), "_last_rest_don_count", 0) or 0)
            except Exception:
                rest_paid = 0
            if first.get("op") == "rest_don" and first.get("any_number") and rest_paid > 0:
                rest = remaining[1:]
                if rest:
                    logs = apply_ops(state, controller, rest, catalog)
                    for line in logs:
                        state.add_log(line)
                _propagate_or_commit_once(state, pending, controller, paid=True)
                state.touch()
                if state.status == "playing" and not _pending_interactive(state):
                    _finish_cleared_interactive(state, catalog)
                return {"ok": True}
            ret_paid = 0
            try:
                ret_paid = int(getattr(state.player(controller), "_last_return_don_count", 0) or 0)
            except Exception:
                ret_paid = 0
            if first.get("op") == "return_don" and first.get("any_number") and ret_paid > 0:
                rest = remaining[1:]
                if rest:
                    logs = apply_ops(state, controller, rest, catalog)
                    for line in logs:
                        state.add_log(line)
                _propagate_or_commit_once(state, pending, controller, paid=True)
                state.touch()
                if state.status == "playing" and not _pending_interactive(state):
                    _finish_cleared_interactive(state, catalog)
                return {"ok": True}
            _propagate_or_commit_once(state, pending, controller, paid=False)
            state.touch()
            if state.status == "playing" and not _pending_interactive(state):
                _finish_cleared_interactive(state, catalog)
            return {"ok": True}
        if then_op is None and target_kind != "hand_card" and remaining:
            # Legacy: first remaining op was the one needing a target — drop it.
            remaining = remaining[1:]
        if remaining:
            logs = apply_ops(state, controller, remaining, catalog)
            for line in logs:
                state.add_log(line)
        _propagate_or_commit_once(state, pending, controller, paid=True)
        state.touch()
        if state.status == "playing" and not _pending_interactive(state):
            _finish_cleared_interactive(state, catalog)
        return {"ok": True}
    if target_iid not in pending.options:
        return {"ok": False, "error": "Invalid choice target."}

    logs: list[dict[str, Any]] = []
    if target_kind == "effect_option":
        branch = list((pending.option_branches or {}).get(str(target_iid)) or [])
        if branch:
            logs = apply_ops(state, controller, branch, catalog)
        if remaining:
            logs.extend(apply_ops(state, controller, remaining, catalog))
    elif target_kind == "life_owner":
        if remaining:
            first = dict(remaining[0])
            if target_iid in {"life_owner:opponent", "opponent"}:
                first["owner"] = "opponent"
                first["life_owner"] = "opponent"
            else:
                first["owner"] = "self"
                first["life_owner"] = "self"
            first.pop("target_iid", None)
            logs = apply_ops(state, controller, [first, *remaining[1:]], catalog)
    elif target_kind == "life_position":
        if remaining:
            first = dict(remaining[0])
            first["target_iid"] = target_iid
            first["position"] = "bottom" if target_iid == "life:bottom" else "top"
            logs = apply_ops(state, controller, [first, *remaining[1:]], catalog)
    elif remaining and isinstance(remaining[0], dict) and remaining[0].get("op") in {
        "trash_hand",
        "opponent_hand_to_bottom",
        "reveal_hand",
    }:
        first = dict(remaining[0])
        first["target_iid"] = target_iid
        first["optional"] = False
        logs = apply_ops(state, controller, [first, *remaining[1:]], catalog)
    elif target_kind == "hand_card" or str(target_iid).startswith("hand:") or str(target_iid).startswith("trash:"):
        if then_op and then_op.get("op") == "hand_to_life":
            op = dict(then_op)
            op["target_iid"] = target_iid
            logs = apply_ops(state, controller, [op, *remaining], catalog)
        elif then_op and then_op.get("op") == "add_from_trash":
            # Choice picked a trash:idx:cid token — move that card to hand or Life.
            from battle.effects import _deliver_trash_card

            m = re.match(r"^trash:(\d+):(.+)$", str(target_iid))
            player = state.player(controller)
            if m:
                idx = int(m.group(1))
                cid = m.group(2)
                moved_cid = ""
                if 0 <= idx < len(player.trash) and player.trash[idx] == cid:
                    moved_cid = player.trash.pop(idx)
                elif cid in player.trash:
                    player.trash.remove(cid)
                    moved_cid = cid
                if moved_cid:
                    dest = _deliver_trash_card(player, moved_cid, then_op)
                    key = "play.log.add_life" if dest == "life" else "play.log.draws"
                    logs.append({"key": key, "name": player.username, "n": 1})
            if remaining:
                logs.extend(apply_ops(state, controller, remaining, catalog))
        else:
            as_rested = bool(then_op and then_op.get("as_rested"))
            replace_iid = str((then_op or {}).get("replace_iid") or "") or None
            src = str((then_op or {}).get("source_iid") or pending.source_iid or "")
            by_char = bool(
                (then_op or {}).get("by_character_effect")
                or (src and src != "leader" and any(c.iid == src for c in state.player(controller).characters))
            )
            played = _effect_play_from_hand_token(
                state,
                controller,
                target_iid,
                catalog,
                as_rested=as_rested,
                replace_iid=replace_iid,
                by_character_effect=by_char,
            )
            if not played.get("ok") and played.get("need_replace"):
                # Board full — ask which Character to trash for space (same slot).
                options = [c.iid for c in state.player(controller).characters]
                if options:
                    play_then = dict(then_op or {"op": "play_from_hand", "optional": True})
                    play_then["token"] = target_iid
                    state.pending_choice = PendingChoice(
                        seat=controller,
                        card_id=str((then_op or {}).get("card_id") or pending.card_id or ""),
                        source_iid=str((then_op or {}).get("source_iid") or pending.source_iid or ""),
                        target_kind="own_character",
                        options=options,
                        remaining_ops=list(remaining),
                        optional=bool((then_op or {}).get("optional", True)),
                        summary="Choose a Character to trash for space",
                        purpose="replace",
                        then_op={
                            "op": "play_token_after_replace",
                            "token": target_iid,
                            "as_rested": as_rested,
                        },
                    )
                    state.add_log("play.log.choice_offer", name=state.player(controller).username)
                    state.touch()
                    return {"ok": True}
            if not played.get("ok"):
                state.add_log({"key": "play.log.effect_unsupported", "id": str(played.get("error") or "play_from_hand")})
            else:
                logs.extend(played.get("logs") or [])
                if remaining and str(target_iid).startswith(("hand:", "trash:")):
                    m_play = re.match(r"^(hand|trash):(\d+):(.+)$", str(target_iid))
                    played_cid = m_play.group(3) if m_play else ""
                    if played_cid:
                        patched_remaining: list[dict[str, Any]] = []
                        skipped_cont = False
                        for rop in remaining:
                            if (
                                not skipped_cont
                                and isinstance(rop, dict)
                                and rop.get("op") == "play_from_hand"
                            ):
                                rop = dict(rop)
                                if rop.get("total_cost_lte") is not None:
                                    nb = int(rop["total_cost_lte"]) - printed_cost(catalog(played_cid))
                                    if nb <= 0:
                                        skipped_cont = True
                                        continue
                                    rop["total_cost_lte"] = nb
                                if rop.get("different_names"):
                                    info = catalog(played_cid)
                                    nm = str(info.get("name") or info.get("name_en") or played_cid)
                                    prior = str(rop.get("exclude_name") or "").strip()
                                    rop["exclude_name"] = f"{prior}|{nm}" if prior else nm
                                skipped_cont = True
                            patched_remaining.append(rop)
                        remaining = patched_remaining
            if remaining:
                logs.extend(apply_ops(state, controller, remaining, catalog))
    elif then_op and then_op.get("op") == "play_token_after_replace":
        src = str(then_op.get("source_iid") or pending.source_iid or "")
        by_char = bool(
            then_op.get("by_character_effect")
            or (src and src != "leader" and any(c.iid == src for c in state.player(controller).characters))
        )
        played = _effect_play_from_hand_token(
            state,
            controller,
            str(then_op.get("token") or ""),
            catalog,
            as_rested=bool(then_op.get("as_rested")),
            replace_iid=target_iid,
            by_character_effect=by_char,
        )
        if played.get("ok"):
            logs.extend(played.get("logs") or [])
        if remaining:
            logs.extend(apply_ops(state, controller, remaining, catalog))
    elif then_op and isinstance(then_op, dict):
        op = dict(then_op)
        op["target_iid"] = target_iid
        logs = apply_ops(state, controller, [op, *remaining], catalog)
    elif remaining:
        first = dict(remaining[0])
        first["target_iid"] = target_iid
        logs = apply_ops(state, controller, [first, *remaining[1:]], catalog)
    for line in logs:
        state.add_log(line)
    # If a When Attacking choice rewrote base power, refresh declared attack power.
    if state.attack and state.attack.attacker_seat == controller:
        state.attack.declared_power = inst_power(state, controller, state.attack.attacker_iid, catalog)
    _propagate_or_commit_once(state, pending, controller, paid=True)
    state.touch()
    if state.status == "playing" and not _pending_interactive(state):
        _finish_cleared_interactive(state, catalog)
    return {"ok": True}


def _effect_play_from_hand_token(
    state: MatchState,
    seat: int,
    token: str,
    catalog: CatalogFn,
    *,
    as_rested: bool = False,
    replace_iid: str | None = None,
    by_character_effect: bool = False,
) -> dict[str, Any]:
    """Play a hand/trash card for free via effect (no DON!! cost).

    Token: hand:{idx}:{card_id} or trash:{idx}:{card_id}.
    """
    player = state.player(seat)
    m = re.match(r"^(hand|trash):(\d+):(.+)$", str(token))
    if not m:
        return {"ok": False, "error": "Bad hand/trash token."}
    zone = m.group(1)
    idx = int(m.group(2))
    cid = m.group(3)
    pile = player.hand if zone == "hand" else player.trash
    if idx < 0 or idx >= len(pile) or pile[idx] != cid:
        # Index may have drifted; find first matching card id.
        try:
            idx = pile.index(cid)
        except ValueError:
            return {"ok": False, "error": f"Card no longer in {zone}."}
    info = catalog(cid)
    ctype = card_type_of(info)
    if ctype == "stage":
        pile.pop(idx)
        if player.stages:
            old = player.stages.pop(0)
            player.trash.append(old.card_id)
        keywords = detect_keywords(info)
        inst = CardInst(
            iid=new_iid("st"),
            card_id=cid,
            rested=bool(as_rested),
            summoning_sick=False,
            keywords=keywords,
        )
        player.stages.append(inst)
        logs: list[dict[str, Any]] = [{"key": "play.log.sets_stage", "name": player.username, "id": cid}]
        prev = int(getattr(player, "_last_play_from_hand_count", 0) or 0)
        setattr(player, "_last_play_from_hand_count", prev + 1)
        pending = resolve_ability(
            state, seat, cid, inst.iid, "on_play", info, None, allow_llm=False, catalog=catalog
        )
        if pending and pending.ops:
            _run_pending_effect(state, pending, catalog)
        return {"ok": True, "logs": logs}
    if ctype == "event":
        # Activate Event from hand/trash via effect (usually free; e.g. OP15-046 Sabo).
        pile.pop(idx)
        player.trash.append(cid)
        logs = [{"key": "play.log.plays_event", "name": player.username, "id": cid}]
        _record_event_activated(state, seat, cid, catalog)
        # Prefer Main/on_play text; Counter-only events still resolve counter_event ops if present.
        pending = _resolve_event_play_ability(state, seat, cid, info, catalog)
        if (not pending or not pending.ops) and has_counter_timing(info):
            pending = resolve_ability(
                state, seat, cid, cid, "counter_event", info, None, allow_llm=False, catalog=catalog
            )
        if pending and pending.ops:
            _run_pending_effect(state, pending, catalog)
        if state.status == "playing" and not _pending_interactive(state):
            _fire_armed_draw_on_event(state, seat, cid, catalog)
        if state.status == "playing" and not _pending_interactive(state):
            _fire_board_timing(state, seat, "on_event", catalog)
        if state.status == "playing" and not _pending_interactive(state):
            _fire_opp_activation_watchers(state, seat, catalog, kind="event")
        return {"ok": True, "logs": logs}
    if ctype != "character":
        return {"ok": False, "error": "Only characters/stages/events supported for play_from_hand."}
    replace_at: int | None = None
    if len(player.characters) >= 5:
        if not replace_iid or not any(c.iid == replace_iid for c in player.characters):
            return {"ok": False, "error": "Character area full.", "need_replace": True}
        replace_at = next(i for i, c in enumerate(player.characters) if c.iid == replace_iid)
        removed = _remove_character(player, replace_iid, to_trash=True)
        if removed:
            state.add_log("play.log.trash_for_space", name=player.username, id=removed.card_id)
    pile.pop(idx)
    keywords = detect_keywords(info)
    rush_full = has_rush(info)
    inst = CardInst(
        iid=new_iid("ch"),
        card_id=cid,
        rested=bool(as_rested),
        summoning_sick=not rush_full,
        keywords=keywords,
    )
    if replace_at is not None:
        player.characters.insert(min(replace_at, len(player.characters)), inst)
    else:
        player.characters.append(inst)
    logs = [{"key": "play.log.plays", "name": player.username, "id": cid}]
    player._last_effect_played_iids = [inst.iid]
    prev = int(getattr(player, "_last_play_from_hand_count", 0) or 0)
    setattr(player, "_last_play_from_hand_count", prev + 1)
    _after_character_enters(
        state,
        seat,
        inst.iid,
        cid,
        catalog,
        from_zone=zone,
        by_character_effect=by_character_effect,
    )
    return {"ok": True, "logs": logs}


def _toggle_or_resolve_search(state: MatchState, seat: int, index: int, catalog: CatalogFn) -> dict[str, Any]:
    """Toggle a search pick. Auto-resolve when max_add == 1; otherwise wait for confirm_search."""
    pending = state.pending_search
    if not pending or pending.seat != seat:
        return {"ok": False, "error": "No pending search."}
    if pending.phase != "pick":
        return {"ok": False, "error": "Search pick already resolved."}
    idx = int(index)
    if idx not in pending.eligible:
        return {"ok": False, "error": "Card is not eligible."}
    selected = list(pending.selected or [])
    if idx in selected:
        selected = [x for x in selected if x != idx]
    else:
        if len(selected) >= max(1, int(pending.max_add or 1)):
            if int(pending.max_add or 1) <= 1:
                selected = [idx]
            else:
                return {"ok": False, "error": "Already selected the maximum number of cards."}
        else:
            selected.append(idx)
    pending.selected = selected
    # Single-add searches keep one-tap UX.
    if int(pending.max_add or 1) <= 1 and selected:
        return _resolve_search(state, seat, selected, catalog)
    state.touch()
    return {"ok": True}


def _finish_search(state: MatchState, seat: int, remaining: list[dict[str, Any]], catalog: CatalogFn) -> dict[str, Any]:
    state.pending_search = None
    if remaining:
        logs = apply_ops(state, seat, remaining, catalog)
        for line in logs:
            state.add_log(line)
    state.touch()
    return {"ok": True}


def _resolve_search(state: MatchState, seat: int, picks: list[int], catalog: CatalogFn) -> dict[str, Any]:
    pending = state.pending_search
    if not pending or pending.seat != seat:
        return {"ok": False, "error": "No pending search."}
    if pending.phase != "pick":
        return {"ok": False, "error": "Search pick already resolved."}
    player = state.player(seat)
    selected: list[str] = []
    leftovers: list[str] = []
    pick_set = {int(i) for i in picks}
    for i, cid in enumerate(pending.revealed):
        if i in pick_set and i in pending.eligible and len(selected) < pending.max_add:
            selected.append(cid)
        else:
            leftovers.append(cid)
    if selected:
        if str(pending.destination or "hand") == "play":
            for cid in selected:
                # Park into hand briefly so the free-play helper can consume it.
                player.hand.append(cid)
                token = f"hand:{len(player.hand) - 1}:{cid}"
                played = _effect_play_from_hand_token(state, seat, token, catalog)
                if not played.get("ok"):
                    # Could not play (board full etc.) — leave in hand as fallback.
                    state.add_log(
                        {
                            "key": "play.log.effect_unsupported",
                            "id": str(played.get("error") or "search_play"),
                        }
                    )
                else:
                    for line in played.get("logs") or []:
                        state.add_log(line)
            if pending.reveal_adds:
                state.add_log(
                    {
                        "key": "play.log.searches_reveal",
                        "name": player.username,
                        "n": len(selected),
                        "ids": ", ".join(selected),
                    }
                )
            else:
                state.add_log({"key": "play.log.searches", "name": player.username, "n": len(selected)})
        elif str(pending.destination or "hand") == "life":
            from battle.effects import _place_cid_on_life

            face_up = str(getattr(pending, "face", None) or "down").strip().lower() == "up"
            for cid in selected:
                _place_cid_on_life(player, cid, top=True, face_up=face_up)
            if pending.reveal_adds:
                state.add_log(
                    {
                        "key": "play.log.searches_reveal",
                        "name": player.username,
                        "n": len(selected),
                        "ids": ", ".join(selected),
                    }
                )
                state.public_search_adds = {"seat": seat, "n": len(selected), "ids": list(selected)}
            else:
                state.add_log({"key": "play.log.searches", "name": player.username, "n": len(selected)})
                state.public_search_adds = {"seat": seat, "n": len(selected), "ids": []}
            state.add_log({"key": "play.log.add_life", "name": player.username, "n": len(selected)})
        elif str(pending.destination or "") == "deck_top_life_rest":
            # ST13-016 style: selected → deck top; leftovers → reorder onto Life.
            remaining = list(pending.remaining_ops or [])
            life_seat = getattr(pending, "life_seat", None)
            life_owner = state.player(int(life_seat)) if life_seat is not None else player
            if selected:
                player.deck = list(selected) + player.deck
                state.add_log({"key": "play.log.effect_applied", "summary": "life_to_deck_top", "n": len(selected)})
            if leftovers:
                if len(leftovers) == 1:
                    life_owner.life = list(leftovers)
                    life_owner.life_face = [False]
                    return _finish_search(state, seat, remaining, catalog)
                state.pending_search = PendingSearch(
                    seat=pending.seat,
                    card_id=pending.card_id,
                    source_iid=pending.source_iid,
                    revealed=list(leftovers),
                    eligible=list(range(len(leftovers))),
                    max_add=0,
                    summary=pending.summary,
                    remaining_ops=remaining,
                    phase="order",
                    bottom_order=[],
                    order_bottom=True,
                    destination="life_reorder",
                    life_seat=life_owner.seat,
                    order_dest="top",
                    reveal_adds=pending.reveal_adds,
                    added_card_ids=list(selected),
                )
                state.add_log("play.log.search_order", name=player.username, n=len(leftovers))
                state.touch()
                return {"ok": True}
            return _finish_search(state, seat, remaining, catalog)
        else:
            player.hand.extend(selected)
            if pending.reveal_adds:
                state.add_log(
                    {
                        "key": "play.log.searches_reveal",
                        "name": player.username,
                        "n": len(selected),
                        "ids": ", ".join(selected),
                    }
                )
                state.public_search_adds = {"seat": seat, "n": len(selected), "ids": list(selected)}
            else:
                state.add_log({"key": "play.log.searches", "name": player.username, "n": len(selected)})
                state.public_search_adds = {"seat": seat, "n": len(selected), "ids": []}
    remaining = list(pending.remaining_ops or [])
    # Trash-the-rest looks: leftovers go to trash (no bottom order).
    if leftovers and bool(getattr(pending, "trash_rest", False)):
        player.trash.extend(leftovers)
        state.add_log({"key": "play.log.trashes_many", "name": player.username, "n": len(leftovers)})
        return _finish_search(state, seat, remaining, catalog)
    # Unchosen / ineligible revealed cards go to bottom; ask for order when ≥2.
    if len(leftovers) >= 2 and pending.order_bottom:
        to_tb = bool(getattr(pending, "to_top_or_bottom", False))
        dest = str(getattr(pending, "order_dest", None) or "").strip().lower()
        if to_tb and dest not in {"top", "bottom"}:
            phase = "choose_dest"
            dest = ""
        else:
            phase = "order"
            if dest not in {"top", "bottom"}:
                dest = "bottom"
        state.pending_search = PendingSearch(
            seat=pending.seat,
            card_id=pending.card_id,
            source_iid=pending.source_iid,
            revealed=list(leftovers),
            eligible=list(range(len(leftovers))),
            max_add=0,
            trait_contains=pending.trait_contains,
            name_contains=pending.name_contains,
            card_type=pending.card_type,
            summary=pending.summary,
            remaining_ops=remaining,
            phase=phase,
            bottom_order=[],
            order_bottom=True,
            exclude_name=pending.exclude_name,
            destination=pending.destination,
            face=str(getattr(pending, "face", None) or "down"),
            trash_rest=False,
            reveal_adds=pending.reveal_adds,
            added_card_ids=list(selected),
            order_dest=dest,
            to_top_or_bottom=to_tb,
        )
        if phase == "choose_dest":
            state.add_log("play.log.choice_offer", name=player.username)
        else:
            state.add_log("play.log.search_order", name=player.username, n=len(leftovers))
        state.touch()
        return {"ok": True}
    # Single leftover (or no order): still respect top vs bottom when to_top_or_bottom.
    if leftovers:
        to_tb = bool(getattr(pending, "to_top_or_bottom", False))
        dest = str(getattr(pending, "order_dest", None) or "bottom").strip().lower()
        if to_tb and dest not in {"top", "bottom"}:
            state.pending_search = PendingSearch(
                seat=pending.seat,
                card_id=pending.card_id,
                source_iid=pending.source_iid,
                revealed=list(leftovers),
                eligible=list(range(len(leftovers))),
                max_add=0,
                trait_contains=pending.trait_contains,
                name_contains=pending.name_contains,
                card_type=pending.card_type,
                summary=pending.summary,
                remaining_ops=remaining,
                phase="choose_dest",
                bottom_order=[],
                order_bottom=bool(pending.order_bottom),
                exclude_name=pending.exclude_name,
                destination=pending.destination,
                face=str(getattr(pending, "face", None) or "down"),
                trash_rest=False,
                reveal_adds=pending.reveal_adds,
                added_card_ids=list(selected),
                order_dest="",
                to_top_or_bottom=True,
            )
            state.add_log("play.log.choice_offer", name=player.username)
            state.touch()
            return {"ok": True}
        if dest == "top":
            player.deck = list(leftovers) + player.deck
        else:
            player.deck.extend(leftovers)
        return _finish_search(state, seat, remaining, catalog)
    return _finish_search(state, seat, remaining, catalog)


def _order_search_bottom(state: MatchState, seat: int, index: int, catalog: CatalogFn) -> dict[str, Any]:
    pending = state.pending_search
    if not pending or pending.seat != seat or pending.phase != "order":
        return {"ok": False, "error": "No pending search order."}
    if index < 0 or index >= len(pending.revealed):
        return {"ok": False, "error": "Invalid order index."}
    cid = pending.revealed.pop(index)
    pending.bottom_order.append(cid)
    pending.eligible = list(range(len(pending.revealed)))
    if pending.revealed:
        state.touch()
        return {"ok": True}
    player = state.player(seat)
    dest = str(getattr(pending, "order_dest", None) or "bottom").strip().lower()
    destination = str(getattr(pending, "destination", None) or "hand")
    if destination == "life_reorder":
        life_seat = getattr(pending, "life_seat", None)
        life_owner = state.player(int(life_seat)) if life_seat is not None else player
        # First chosen = Life top (index 0).
        life_owner.life = list(pending.bottom_order)
        life_owner.life_face = [False] * len(life_owner.life)
        state.add_log(
            {
                "key": "play.log.effect_applied",
                "summary": "reorder_life",
                "n": len(life_owner.life),
            }
        )
        remaining = list(pending.remaining_ops or [])
        return _finish_search(state, seat, remaining, catalog)
    if dest == "top":
        player.deck = list(pending.bottom_order) + player.deck
    else:
        player.deck.extend(pending.bottom_order)
    remaining = list(pending.remaining_ops or [])
    return _finish_search(state, seat, remaining, catalog)


def _resolve_search_dest(state: MatchState, seat: int, target_iid: str, catalog: CatalogFn) -> dict[str, Any]:
    """Choose top vs bottom for search leftovers (paper: 卡組上面或下面)."""
    pending = state.pending_search
    if not pending or pending.seat != seat or pending.phase != "choose_dest":
        return {"ok": False, "error": "No pending search destination."}
    dest = "top" if target_iid == "deck:top" else "bottom"
    leftovers = list(pending.revealed)
    remaining = list(pending.remaining_ops or [])
    if len(leftovers) >= 2 and pending.order_bottom:
        state.pending_search = PendingSearch(
            seat=pending.seat,
            card_id=pending.card_id,
            source_iid=pending.source_iid,
            revealed=leftovers,
            eligible=list(range(len(leftovers))),
            max_add=0,
            trait_contains=pending.trait_contains,
            name_contains=pending.name_contains,
            card_type=pending.card_type,
            summary=pending.summary,
            remaining_ops=remaining,
            phase="order",
            bottom_order=[],
            order_bottom=True,
            exclude_name=pending.exclude_name,
            destination=pending.destination,
            face=str(getattr(pending, "face", None) or "down"),
            trash_rest=False,
            reveal_adds=pending.reveal_adds,
            added_card_ids=list(getattr(pending, "added_card_ids", None) or []),
            order_dest=dest,
            to_top_or_bottom=True,
        )
        state.add_log("play.log.search_order", name=state.player(seat).username, n=len(leftovers))
        state.touch()
        return {"ok": True}
    player = state.player(seat)
    if dest == "top":
        player.deck = leftovers + player.deck
    else:
        player.deck.extend(leftovers)
    return _finish_search(state, seat, remaining, catalog)


def _undo_search_order(state: MatchState, seat: int) -> dict[str, Any]:
    pending = state.pending_search
    if not pending or pending.seat != seat or pending.phase != "order":
        return {"ok": False, "error": "No pending search order."}
    if not pending.bottom_order:
        return {"ok": False, "error": "Nothing to undo."}
    cid = pending.bottom_order.pop()
    pending.revealed.append(cid)
    pending.eligible = list(range(len(pending.revealed)))
    state.touch()
    return {"ok": True}


def _purpose_from_op(op: dict[str, Any] | None) -> str:
    from battle.choice_purpose import purpose_from_op

    return purpose_from_op(op)


def _pending_choice_purpose(pending: Any) -> str:
    from battle.choice_purpose import pending_choice_purpose

    return pending_choice_purpose(pending)


def public_view(state: MatchState, viewer_seat: int | None, catalog: CatalogFn) -> dict[str, Any]:
    def enrich_char(p: PlayerState, c: CardInst) -> dict[str, Any]:
        info = catalog(c.card_id)
        keys = [k for k in live_keywords(info, c, state=state, owner_seat=p.seat, catalog=catalog) if k != "trigger"]
        pub = c.to_public()
        pub["keywords"] = keys
        pub["power"] = inst_power(state, p.seat, c.iid, catalog)
        pub["cost"] = effective_character_cost(state, p.seat, c, catalog)
        pub["cannot_attack"] = (
            _character_cannot_attack(state, p.seat, c, catalog)
            or _character_denied_attack(p, c.iid)
            or _character_denied_rest(p, c.iid)
        )
        pub["cannot_rest"] = _character_denied_rest(p, c.iid)
        return pub

    def player_view(p: PlayerState, hide_hand: bool) -> dict[str, Any]:
        leader_keys = live_leader_keywords(state, p.seat, catalog)
        # Face-up Life cards are public to both players (card id); face-down stay opaque.
        life_faces: list[dict[str, Any]] = []
        faces = list(p.life_face or [])
        if faces and len(faces) != len(p.life):
            # Keep aligned defensively.
            while len(faces) < len(p.life):
                faces.append(False)
            faces = faces[: len(p.life)]
        if not faces:
            life_faces = [{"face_up": False, "card_id": None} for _ in p.life]
        else:
            for cid, up in zip(p.life, faces):
                life_faces.append(
                    {
                        "face_up": bool(up),
                        "card_id": cid if up else None,
                    }
                )
        return {
            "seat": p.seat,
            "user_id": p.user_id,
            "username": p.username,
            "is_ai": p.is_ai,
            "leader_card_id": p.leader_card_id,
            "leader_rested": p.leader_rested,
            "leader_don": p.leader_don,
            "leader_power": inst_power(state, p.seat, "leader", catalog) if state.players else 0,
            "leader_keywords": leader_keys,
            "leader_cannot_attack": bool(_leader_denied_attack(p)),
            "life": p.life_count,
            "life_faces": life_faces,
            "deck_count": len(p.deck),
            "hand_count": len(p.hand),
            "hand": [] if hide_hand else list(p.hand),
            # Trash is public; send the full pile so either player can inspect it.
            "trash": list(p.trash),
            "characters": [enrich_char(p, c) for c in p.characters],
            "stages": [enrich_char(p, c) for c in p.stages],
            "don_active": p.don_active,
            "don_rested": p.don_rested,
            "don_given": p.don_given,
            "don_deck_size": don_deck_cap(p),
            "mulligan_done": p.mulligan_done,
        }

    return {
        "room_code": state.room_code,
        "status": state.status,
        "phase": state.phase,
        "turn_seat": state.turn_seat,
        "first_seat": state.first_seat,
        "turn_number": state.turn_number,
        "mulligan_seat": state.mulligan_seat,
        "winner_seat": state.winner_seat,
        "viewer_seat": viewer_seat,
        "acting_seat": viewer_seat,
        "vs_ai": any(bool(getattr(p, "is_ai", False)) for p in state.players),
        "log": list(state.log[-24:]),
        "attack": None
        if not state.attack
        else {
            "attacker_seat": state.attack.attacker_seat,
            "attacker_iid": state.attack.attacker_iid,
            "target_iid": state.attack.target_iid,
            "declared_power": state.attack.declared_power,
            "blocker_iid": state.attack.blocker_iid,
            "counter_bonus": state.attack.counter_bonus,
            "counter_buffs": dict(state.attack.counter_buffs),
            "combat_entered": bool(state.attack.combat_entered),
            "combat_phase": str(state.attack.combat_phase or "block"),
        },
        "pending_effect": None
        if not state.pending_effect
        else {
            "effect_id": state.pending_effect.effect_id,
            "seat": state.pending_effect.seat,
            "card_id": state.pending_effect.card_id,
            "source_iid": state.pending_effect.source_iid,
            "summary": state.pending_effect.summary,
            "ops": state.pending_effect.ops,
            "uncertain": state.pending_effect.uncertain,
            "confirmations": state.pending_effect.confirmations,
        },
        "pending_trigger": None
        if not state.pending_trigger
        else {
            "seat": state.pending_trigger.seat,
            "card_id": state.pending_trigger.card_id,
            "summary": state.pending_trigger.summary,
            "ops": state.pending_trigger.ops,
            "remaining_hits": state.pending_trigger.remaining_hits,
        },
        "pending_search": None
        if not state.pending_search
        else {
            "seat": state.pending_search.seat,
            "card_id": state.pending_search.card_id,
            "source_iid": state.pending_search.source_iid,
            "phase": state.pending_search.phase,
            "revealed": list(state.pending_search.revealed)
            if viewer_seat is not None and viewer_seat == state.pending_search.seat
            else [None] * len(state.pending_search.revealed),
            "eligible": list(state.pending_search.eligible)
            if viewer_seat is not None and viewer_seat == state.pending_search.seat
            else [],
            "bottom_order": list(state.pending_search.bottom_order)
            if viewer_seat is not None and viewer_seat == state.pending_search.seat
            else [None] * len(state.pending_search.bottom_order),
            "max_add": state.pending_search.max_add,
            "selected": list(state.pending_search.selected)
            if viewer_seat is not None and viewer_seat == state.pending_search.seat
            else [],
            "trait_contains": state.pending_search.trait_contains,
            "name_contains": state.pending_search.name_contains,
            "card_type": state.pending_search.card_type,
            "exclude_name": state.pending_search.exclude_name,
            "summary": state.pending_search.summary,
            "order_bottom": state.pending_search.order_bottom,
            "to_top_or_bottom": bool(getattr(state.pending_search, "to_top_or_bottom", False)),
            "order_dest": str(getattr(state.pending_search, "order_dest", None) or ""),
            "trash_rest": bool(getattr(state.pending_search, "trash_rest", False)),
            "reveal_adds": bool(state.pending_search.reveal_adds),
            "destination": state.pending_search.destination,
        },
        "public_search_adds": None
        if not state.public_search_adds
        else {
            "seat": state.public_search_adds.get("seat"),
            "n": int(state.public_search_adds.get("n") or len(state.public_search_adds.get("ids") or [])),
            # Restricted search: expose selected card ids to both players.
            # Unrestricted: ids stay empty (count-only disclosure).
            "ids": list(state.public_search_adds.get("ids") or []),
        },
        "pending_choice": None
        if not state.pending_choice
        else {
            "seat": state.pending_choice.seat,
            "card_id": state.pending_choice.card_id,
            "source_iid": state.pending_choice.source_iid,
            "target_kind": state.pending_choice.target_kind,
            "options": list(state.pending_choice.options)
            if viewer_seat is not None and viewer_seat == state.pending_choice.seat
            else [],
            "option_labels": dict(state.pending_choice.option_labels)
            if viewer_seat is not None and viewer_seat == state.pending_choice.seat
            else {},
            "optional": state.pending_choice.optional,
            "multi_select": bool(state.pending_choice.multi_select),
            "summary": state.pending_choice.summary,
            "purpose": _pending_choice_purpose(state.pending_choice),
        },
        "players": [
            player_view(p, hide_hand=(viewer_seat is None or p.seat != viewer_seat))
            for p in state.players
        ],
        "legal_actions": legal_actions(state, viewer_seat, catalog) if viewer_seat is not None else [],
    }
