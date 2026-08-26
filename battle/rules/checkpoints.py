"""Chapter 9 rule-processing checkpoints and combat integrity helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from battle.state import MatchState


def set_loser(state: MatchState, loser_seat: int, reason_key: str, **params: Any) -> None:
    """Apply immediate loss (also used by concede 1-2-3)."""
    if state.status != "playing":
        return
    state.winner_seat = state.other(loser_seat)
    state.status = "finished"
    state.phase = "gameover"
    state.end_phase_step = None
    state.attack = None
    state.pending_trigger = None
    state.trigger_resume = None
    state.pending_effect = None
    state.pending_search = None
    state.pending_choice = None
    state.add_log(reason_key, **params)
    state.add_log("play.log.wins", name=state.player(state.winner_seat).username)
    state.touch()


def mark_pending_defeat(state: MatchState, seat: int, reason_key: str, **params: Any) -> None:
    """Record that seat meets a defeat condition (applied at next rule_process)."""
    if state.status != "playing":
        return
    flags = getattr(state, "pending_defeats", None)
    if flags is None:
        state.pending_defeats = {}
        flags = state.pending_defeats
    flags[int(seat)] = {"key": reason_key, "params": dict(params)}


def concede(state: MatchState, seat: int) -> dict[str, Any]:
    """1-2-3: player concedes and loses immediately."""
    if state.status != "playing":
        return {"ok": False, "error": "Match is not in progress."}
    if seat not in (0, 1):
        return {"ok": False, "error": "Invalid seat."}
    set_loser(state, seat, "play.log.concedes", name=state.player(seat).username)
    return {"ok": True}


def rule_process(state: MatchState) -> None:
    """
    9-1 / 9-2: apply pending defeats and check deck-empty defeat conditions.
    Life-at-0 + Leader damage is usually marked when damage is dealt.
    """
    if state.status != "playing":
        return
    # Deck empty (1-2-1-1-2). Ignore while a seat is mid-search: revealed cards
    # are held out of the deck until the search finishes (order / trash rest).
    for seat, player in enumerate(state.players):
        if not player.deck:
            pending = state.pending_search
            if pending and pending.seat == seat and (pending.revealed or pending.bottom_order):
                continue
            mark_pending_defeat(state, seat, "play.log.decks_out", name=player.username)
    flags = getattr(state, "pending_defeats", None) or {}
    if not flags:
        return
    # If both would lose, turn player loses first is not official; apply lower seat first
    # then stop (simultaneous → both conditions rare in local sim).
    for seat in sorted(flags.keys()):
        if state.status != "playing":
            return
        info = flags.get(seat)
        if not info:
            continue
        set_loser(state, int(seat), str(info.get("key") or "play.log.decks_out"), **(info.get("params") or {}))
        return


def combatants_present(state: MatchState) -> bool:
    """
    7-1-3-1-3: after Counter step, attacker and the attack target must still be
    on the field (Leader always 'present'; Character must still be in characters).
    """
    attack = state.attack
    if not attack:
        return False
    atk_seat = attack.attacker_seat
    def_seat = state.other(atk_seat)
    attacker = state.player(atk_seat)
    defender = state.player(def_seat)

    if attack.attacker_iid == "leader":
        pass  # Leader cannot leave leader area in this engine
    else:
        if not any(c.iid == attack.attacker_iid for c in attacker.characters):
            return False

    target_iid = attack.blocker_iid or attack.target_iid
    if target_iid == "leader":
        return True
    return any(c.iid == target_iid for c in defender.characters)


def cancel_battle(state: MatchState, reason_key: str = "play.log.battle_cancelled") -> None:
    """Clear pending attack without dealing damage (7-1-3-1-3)."""
    if state.attack:
        state.add_log(reason_key)
    state.attack = None
    if state.status == "playing" and state.phase in {"block", "counter", "trigger"}:
        state.phase = "main"
    state.touch()
