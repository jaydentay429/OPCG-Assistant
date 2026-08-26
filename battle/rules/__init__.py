"""Official OPTCG comprehensive rules (V1.2.0) as code — battle-facing surface."""

from __future__ import annotations

from battle.rules.catalog import RULES, RuleEntry, all_rule_ids, get_rule, rules_by_status
from battle.rules.checkpoints import (
    cancel_battle,
    combatants_present,
    concede,
    mark_pending_defeat,
    rule_process,
    set_loser,
)
from battle.rules import timings

__all__ = [
    "RULES",
    "RuleEntry",
    "all_rule_ids",
    "get_rule",
    "rules_by_status",
    "cancel_battle",
    "combatants_present",
    "concede",
    "mark_pending_defeat",
    "rule_process",
    "set_loser",
    "timings",
]
