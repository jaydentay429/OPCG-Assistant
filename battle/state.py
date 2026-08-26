from __future__ import annotations

import copy
import secrets
import time
from dataclasses import dataclass, field
from typing import Any


def new_iid(prefix: str = "c") -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


@dataclass
class CardInst:
    iid: str
    card_id: str
    rested: bool = False
    power_mod: int = 0
    # Power that lasts until a specific seat's End Phase cleanup (expire_seat).
    # Entries: {amount: int, expire_seat: int}
    power_until_end: list[dict[str, Any]] = field(default_factory=list)
    don_attached: int = 0
    summoning_sick: bool = True
    keywords: list[str] = field(default_factory=list)
    # Keywords granted "during this turn" (cleared at turn end).
    turn_keywords: list[str] = field(default_factory=list)
    # Keywords lasting until a seat's End Phase. Entries: {keyword: str, expire_seat: int}
    keywords_until_end: list[dict[str, Any]] = field(default_factory=list)
    # 【每回合1次】/启动效果本回合是否已用
    once_used: bool = False
    # This-turn replacement for printed base power (e.g. OP16-055 When Attacking).
    base_power_override: int | None = None
    # Absolute power override (e.g. OP06-009: power becomes equal to opponent Leader).
    power_override: int | None = None
    # This-turn protection from K.O. by effects / battle (grant via cannot_be_ko op).
    cannot_be_ko: bool = False
    # Continuous / this-turn: cannot be rested by opponent effects.
    cannot_be_rested: bool = False
    # Broader: cannot leave field by opponent effects (bounce/bottom/trash/KO).
    cannot_be_removed: bool = False
    # This-turn: card effects are negated.
    effects_negated: bool = False
    # Negation lasting until a seat's End Phase. Entries: {expire_seat: int}
    effects_negated_until_end: list[dict[str, Any]] = field(default_factory=list)
    # Continuous / this-turn: this Character cannot attack.
    cannot_attack: bool = False
    # Continuous: while rested, opponent must attack this Character when able.
    taunt: bool = False
    # This-turn cost modification (e.g. −10 cost from OP14-079).
    cost_mod: int = 0
    # Attributes granted this turn / permanently (e.g. Slash from OP15-093).
    turn_attributes: list[str] = field(default_factory=list)
    granted_attributes: list[str] = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return {
            "iid": self.iid,
            "card_id": self.card_id,
            "rested": self.rested,
            "power_mod": self.power_mod + sum(int(e.get("amount") or 0) for e in self.power_until_end),
            "don_attached": self.don_attached,
            "summoning_sick": self.summoning_sick,
            "keywords": list(self.keywords),
            "turn_keywords": list(self.turn_keywords),
            "once_used": self.once_used,
            "base_power_override": self.base_power_override,
            "power_override": self.power_override,
            "cannot_be_ko": self.cannot_be_ko,
            "effects_negated": self.effects_negated or bool(self.effects_negated_until_end),
            "cannot_attack": self.cannot_attack,
            "taunt": self.taunt,
            "cost_mod": self.cost_mod,
            "turn_attributes": list(self.turn_attributes),
            "granted_attributes": list(self.granted_attributes),
        }


@dataclass
class PlayerState:
    seat: int
    user_id: str
    username: str
    is_ai: bool
    leader_card_id: str
    leader_rested: bool = False
    leader_don: int = 0
    leader_power_mod: int = 0
    # Leader power lasting until a seat's End Phase. Entries: {amount: int, expire_seat: int}
    leader_power_until_end: list[dict[str, Any]] = field(default_factory=list)
    life: list[str] = field(default_factory=list)
    deck: list[str] = field(default_factory=list)
    hand: list[str] = field(default_factory=list)
    trash: list[str] = field(default_factory=list)
    characters: list[CardInst] = field(default_factory=list)
    stages: list[CardInst] = field(default_factory=list)
    don_active: int = 0
    don_rested: int = 0
    don_given: int = 0
    # Printed DON!! deck size (default 10; Enel OP15-058 is 6).
    don_deck_size: int = 10
    # How many of this player's turns have fully ended. 0 = currently their first turn (or not started).
    turns_completed: int = 0
    mulligan_done: bool = False
    # Leader 【每回合1次】 Activate: Main used this turn
    leader_once_used: bool = False
    # AI: Activate: Main sources skipped (declined optional cost) this turn — do not re-open.
    skipped_activate_iids: list[str] = field(default_factory=list)
    # This-turn: character/leader iids that may attack active (non-rested) Characters.
    attack_active_iids: list[str] = field(default_factory=list)
    # This-turn: attackers that already declared an attack — attached DON!! locked (no free remove).
    attacked_this_turn_iids: list[str] = field(default_factory=list)
    # This-turn / this-battle: deny opponent Blocker activation.
    # Each entry: {power_lte?, power_gte?, duration: "battle"|"turn"}
    deny_blocker: list[dict[str, Any]] = field(default_factory=list)
    # True after an effect trashed card(s) from this player's hand this turn (ST33-004 etc.).
    hand_trashed_by_effect_this_turn: bool = False
    # True after a card left opponent Life this turn (P-120 hand-cost etc.).
    opp_life_left_this_turn: bool = False
    # This-turn: may trash 1 hand card instead of battle-KO for own Characters.
    replace_battle_ko: bool = False
    # This-turn: cannot add Life cards to hand via own effects / battle damage take.
    cannot_take_life: bool = False
    # Opponent Characters (iids) that skip the next refresh (will not become active).
    skip_untap_iids: list[str] = field(default_factory=list)
    # Leader skips next refresh (will not become active).
    leader_skip_untap: bool = False
    # Rested DON!! that stay rested through the next refresh (count).
    skip_untap_don: int = 0
    # On Play effects negated for this player (self-aura or granted until opp turn end).
    negate_on_play: bool = False
    # Leader effects negated this turn.
    leader_effects_negated: bool = False
    # Leader negation until a seat's End Phase. Entries: {expire_seat: int}
    leader_effects_negated_until_end: list[dict[str, Any]] = field(default_factory=list)
    # This-turn: restrictions on playing from hand.
    # Each entry: {card_type?: "any"|"character"|..., base_cost_gte?, base_cost_lte?}
    cannot_play_rules: list[dict[str, Any]] = field(default_factory=list)
    # Opponent Character iids that cannot attack (this turn only).
    deny_attack_iids: list[str] = field(default_factory=list)
    # Cannot attack until end of this player's End Phase (restricted player's cleanup).
    deny_attack_until_opp_end_iids: list[str] = field(default_factory=list)
    # True when Leader cannot attack this turn (deny_attack include_leader).
    deny_attack_leader: bool = False
    deny_attack_leader_until_opp_end: bool = False
    # Opponent Character iids that cannot be rested (this turn only).
    deny_rest_iids: list[str] = field(default_factory=list)
    deny_rest_until_opp_end_iids: list[str] = field(default_factory=list)
    # Attack tax: characters must trash N hand cards to declare an attack.
    # Entries: {all?: bool, trash_hand: int, duration?: str}
    attack_tax_rules: list[dict[str, Any]] = field(default_factory=list)
    # Parallel face flags for life pile (True=face-up). Length matches life when used.
    life_face: list[bool] = field(default_factory=list)
    # Temporary hand-play cost reductions from Activate: Main (cleared end of turn).
    # Each: {amount:int, name_contains?:str, cost_gte?:int, next_only?:bool}
    temp_hand_cost_mods: list[dict[str, Any]] = field(default_factory=list)
    # This turn: cannot attack opponent Leader.
    cannot_attack_opp_leader: bool = False
    # OP12-020-style: after Activate, untap Leader when it battles an opponent Character.
    untap_on_char_battle: bool = False
    # Armed by Activate: Main — when you activate an Event this turn matching cost_gte, draw.
    # Entries: {cost_gte: int, count: int, source_iid?: str}
    draw_on_event_rules: list[dict[str, Any]] = field(default_factory=list)
    # Printed costs of Events activated this turn (Main / Counter / effect play).
    event_activated_costs: list[int] = field(default_factory=list)
    # This turn: Leader/Characters cannot attack opponent Characters with printed base cost ≤ N.
    cannot_attack_char_base_cost_lte: int | None = None
    # Ops deferred until end of this player's turn (Event "at end of this turn" clauses).
    pending_end_of_turn_ops: list[dict[str, Any]] = field(default_factory=list)
    # Keywords granted to Leader this turn (e.g. blockerless from Events).
    leader_turn_keywords: list[str] = field(default_factory=list)
    # Leader keywords lasting until a seat's End Phase. Entries: {keyword: str, expire_seat: int}
    leader_keywords_until_end: list[dict[str, Any]] = field(default_factory=list)

    @property
    def life_count(self) -> int:
        return len(self.life)

    @property
    def don_total(self) -> int:
        attached = self.leader_don + sum(c.don_attached for c in self.characters)
        return self.don_active + self.don_rested + attached


@dataclass
class PendingAttack:
    attacker_seat: int
    attacker_iid: str  # "leader" or character iid
    target_iid: str  # "leader" or character iid
    declared_power: int
    blocker_iid: str | None = None
    # 7-1-3-1-1: battle-only power buffs keyed by "leader" or character iid
    counter_buffs: dict[str, int] = field(default_factory=dict)
    # "block" | "counter" — entered after When Attacking / 【对方攻击时】 settle.
    combat_phase: str = "block"
    opp_attack_watchers_done: bool = False
    combat_entered: bool = False

    @property
    def counter_bonus(self) -> int:
        return sum(self.counter_buffs.values())


@dataclass
class PendingTrigger:
    """10-1-5: optional Trigger while resolving life damage."""

    seat: int
    card_id: str
    ops: list[dict[str, Any]]
    remaining_hits: int = 0
    banish: bool = False
    summary: str = ""


@dataclass
class PendingEffect:
    effect_id: str
    seat: int
    card_id: str
    source_iid: str
    summary: str
    ops: list[dict[str, Any]]
    confirmations: dict[int, bool] = field(default_factory=dict)
    uncertain: bool = True
    once: bool = False


@dataclass
class PendingSearch:
    """Interactive deck look/search: reveal top N, player picks eligible cards.

    phase:
      - pick: choose cards to add to hand (or play, when destination=play)
      - order: arrange leftovers onto the bottom of the deck
    """

    seat: int
    card_id: str
    source_iid: str
    revealed: list[str]
    eligible: list[int]
    max_add: int = 1
    trait_contains: str = ""
    name_contains: str = ""
    # character | event | stage | any — empty means no type filter was encoded.
    card_type: str = ""
    summary: str = ""
    # Ops to resume after the search resolves (e.g. then play-from-hand).
    remaining_ops: list[dict[str, Any]] = field(default_factory=list)
    phase: str = "pick"  # pick | order
    # During order phase: cards already chosen (first = nearer deck / drawn sooner).
    bottom_order: list[str] = field(default_factory=list)
    # Whether leftovers (≥2) require player-chosen bottom order.
    order_bottom: bool = True
    # Where ordered leftovers go: bottom (search default) or top (look_deck).
    order_dest: str = "bottom"
    # If True, player chooses top vs bottom before ordering leftovers.
    to_top_or_bottom: bool = False
    # Printed name that cannot be added (e.g. "other than [Izo]" / 除了「以藏」以外).
    exclude_name: str = ""
    # hand (default), play (look-then-play), life (look then add to Life top),
    # or life_reorder (put ordered revealed cards back onto Life).
    destination: str = "hand"
    # When destination=life_reorder: which player's Life pile to restore into.
    life_seat: int | None = None
    # Life-face when destination=life: "up" or "down".
    face: str = "down"
    # If True, leftovers after pick go to trash (not deck bottom).
    trash_rest: bool = False
    # Indices chosen during pick (multi-add when max_add > 1).
    selected: list[int] = field(default_factory=list)
    # If True, cards added from this search are revealed to the opponent
    # (restricted searches: name/trait/cost/exclude/trigger filters).
    # Unrestricted searches only disclose the count.
    reveal_adds: bool = False
    # Card ids added this search (public when reveal_adds).
    added_card_ids: list[str] = field(default_factory=list)


@dataclass
class PendingChoice:
    """Interactive target selection for rest/KO/buff/return effects."""

    seat: int
    card_id: str
    source_iid: str
    target_kind: str
    # Eligible target iids ("leader" or character iid)
    options: list[str]
    # Remaining ops to apply after a choice (first op is the one needing target)
    remaining_ops: list[dict[str, Any]] = field(default_factory=list)
    optional: bool = True
    summary: str = ""
    # UI purpose: ko | trash | buff | rest | return_hand | bottom | play | attach_don | choose_effect | life | general
    purpose: str = ""
    then_op: dict[str, Any] | None = None
    # For choose_one: branch payloads keyed by option token (opt:0, …).
    option_branches: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # Human-readable labels for effect_option tokens (and similar).
    option_labels: dict[str, str] = field(default_factory=dict)
    # Seat whose effects run after a choice (may differ from chooser seat).
    controller_seat: int | None = None
    # True for trash-any-number (and similar): UI uses「完成」and tap-to-pick.
    multi_select: bool = False
    # Defer Activate once-per-turn until cost is paid / interactive clears.
    mark_once: bool = False
    mark_once_source_iid: str = ""


@dataclass
class PendingReplace:
    """Paused optional replace_leave / replace_rest waiting for confirm or cost pick."""

    owner_seat: int
    victim_iid: str
    victim_card_id: str
    source_iid: str
    card_id: str
    op: dict[str, Any]
    once: bool = False
    summary: str = ""
    kind: str = "leave"  # leave | rest
    leave_kind: str = "ko"  # ko | return_hand | bottom | trash | battle_ko
    apply_seat: int = 0
    remaining_ops: list[dict[str, Any]] = field(default_factory=list)
    by_opponent: bool = True
    by_ko: bool = True


@dataclass
class MatchState:
    room_code: str
    status: str = "waiting"  # waiting | playing | finished
    # mulligan | main | block | counter | trigger | gameover
    phase: str = "main"
    turn_seat: int = 0
    first_seat: int = 0
    turn_number: int = 1
    winner_seat: int | None = None
    players: list[PlayerState] = field(default_factory=list)
    attack: PendingAttack | None = None
    pending_effect: PendingEffect | None = None
    pending_trigger: PendingTrigger | None = None
    pending_search: PendingSearch | None = None
    pending_choice: PendingChoice | None = None
    pending_replace: PendingReplace | None = None
    # After Trigger accept/decline opens a choice/search/effect, stash remaining
    # double-attack hits so combat can finish when interactive clears.
    # Shape: {"seat": int, "remaining_hits": int, "banish": bool}
    trigger_resume: dict[str, Any] | None = None
    # Last search add disclosure for the opponent (restricted → ids; else count only).
    # Shape: {"seat": int, "n": int, "ids": list[str]}
    public_search_adds: dict[str, Any] | None = None
    # Resume 【对方攻击时】/ board timings after optional confirm (remaining sources).
    # Shape: {"seat": int, "timing": str, "remaining": list[[src_iid, card_id], ...]}
    board_timing_resume: dict[str, Any] | None = None
    # Play-from-zone watchers deferred until On Play interactive settles.
    # Shape: {"seat": int, "played_iid": str, "played_card_id": str, "from_zone": str}
    deferred_play_watchers: dict[str, Any] | None = None
    # Whose mulligan decision is pending (first player, then second)
    mulligan_seat: int | None = None
    # End phase pipeline (6-6): your_end → opp_end → cleanup
    end_phase_step: str | None = None
    # Seats that meet defeat conditions pending Ch.9 rule processing
    pending_defeats: dict[int, dict[str, Any]] = field(default_factory=dict)
    rng_seed: int = 0
    log: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def other(self, seat: int) -> int:
        return 1 - seat

    def player(self, seat: int) -> PlayerState:
        return self.players[seat]

    def touch(self) -> None:
        self.updated_at = time.time()

    def add_log(self, key: str | dict[str, Any], **params: Any) -> None:
        """Append a structured log entry for client-side i18n (`play.log.*` keys)."""
        if isinstance(key, dict):
            entry = {k: v for k, v in key.items() if v is not None}
            if "key" not in entry:
                entry = {"key": "play.log.raw", "text": str(key)}
        else:
            entry = {"key": key, **{k: v for k, v in params.items() if v is not None}}
        self.log.append(entry)
        if len(self.log) > 100:
            self.log = self.log[-100:]


def clone_state(state: MatchState) -> MatchState:
    return copy.deepcopy(state)
