"""
Stat calculator -- computes final battle stats from base stats and IVs.

The stat formula is generation-dependent and is delegated to the BattleRules
object passed in. See pokerena.engine.rules for the per-gen formula details.
"""

from __future__ import annotations

import copy
import random

from pokerena.models import Pokemon

# Default IVs (31 = max, "perfectly bred")
MAX_IV = 31


def compute_stats(
    pokemon: Pokemon,
    level: int = 100,
    ivs: dict[str, int] | None = None,
    rules=None,
) -> dict[str, int]:
    """
    Compute final battle stats for a Pokemon at a given level.

    Delegates the per-stat formula to rules.compute_stat().
    Defaults to Gen 6 rules when rules is None.

    IVs default to MAX_IV (31) if not provided.
    """
    if rules is None:
        from pokerena.engine.rules import Gen6Rules

        rules = Gen6Rules()

    if ivs is None:
        ivs = dict.fromkeys(pokemon.base_stats, MAX_IV)

    stats: dict[str, int] = {}
    for stat_name, base in pokemon.base_stats.items():
        iv = ivs.get(stat_name, MAX_IV)
        stats[stat_name] = rules.compute_stat(base, iv, level, is_hp=(stat_name == "hp"))

    return stats


def random_ivs(rng: random.Random | None = None, max_iv: int = 15) -> dict[str, int]:
    """
    Generate random IVs (0 to max_iv) for all stats.
    max_iv=15 matches the plan's --rand-ivs flag (0-15 range).
    """
    r = rng or random
    return {
        stat: r.randint(0, max_iv)
        for stat in ("hp", "attack", "defense", "sp_atk", "sp_def", "speed")
    }


def initialize_battle_state(
    pokemon: Pokemon,
    level: int = 100,
    ivs: dict[str, int] | None = None,
    rules=None,
) -> Pokemon:
    """
    Return a deep copy of the Pokemon with computed battle stats and full HP.
    Resets all status conditions and stat stages.
    """
    p = copy.deepcopy(pokemon)
    p.stats = compute_stats(p, level=level, ivs=ivs, rules=rules)
    p.max_hp = p.stats["hp"]
    p.current_hp = p.max_hp
    p.status = None
    p.status_counter = 0
    p.stat_stages = dict.fromkeys(("attack", "defense", "sp_atk", "sp_def", "speed"), 0)
    return p
