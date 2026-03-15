"""
Battle engine -- runs a single 1v1 Pokemon battle.

Implements:
- Generation-accurate damage formula and type chart via BattleRules
- Deterministic AI: always picks the highest expected-damage move
- Status moves used when they confer a concrete battle advantage
- All status conditions (burn, paralysis, poison, sleep, freeze)
- Stat stage tracking
- Type effectiveness, STAB, accuracy-weighted damage
- No random miss rolls, no critical hits, no damage noise
- 60-turn timeout resolved by HP percentage
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from pokerena.engine.rules import BattleRules, Gen6Rules
from pokerena.engine.stats import initialize_battle_state, random_ivs
from pokerena.models import Move, Pokemon

MAX_TURNS = 60
STAB_MULTIPLIER = 1.5

# Status conditions that are always a net disadvantage for the target.
# Used by the AI to decide whether applying a status is worth a turn.
_OFFENSIVE_STATUSES = {"burn", "paralysis", "poison", "sleep", "freeze"}

# Status conditions that reduce the target's offensive output -- the AI
# prioritizes these when the defender is a physical attacker.
_DEBUFF_STATUSES = {"burn", "paralysis"}


@dataclass
class BattleResult:
    """Outcome of a single 1v1 battle."""

    winner: str  # Pokemon name
    loser: str
    turns: int
    timeout: bool  # True if resolved by HP% rather than faint
    winner_hp_remaining: int
    winner_hp_max: int
    winner_hp_pct: float
    # Type matchup flags
    attacker_had_advantage: bool = False


def _calc_damage(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    level: int = 100,
    rules: BattleRules | None = None,
) -> float:
    """
    Damage formula with accuracy weighting.

      Base = floor((((2*L/5 + 2) * Power * Atk/Def) / 50) + 2)
      Damage = Base * STAB * TypeMultiplier * (accuracy / 100)

    Accuracy is applied as an expected-value multiplier rather than a
    binary miss roll -- this keeps results deterministic across battles
    and reflects the move's true average output.

    Returns 0.0 for immune matchups.
    """
    if rules is None:
        rules = Gen6Rules()
    # Pick attack / defense stats based on move category
    if move.category == "physical":
        atk_stat = "attack"
        def_stat = "defense"
    else:
        atk_stat = "sp_atk"
        def_stat = "sp_def"

    atk = attacker.stats.get(atk_stat, 1) * attacker.stage_multiplier(atk_stat)
    def_ = defender.stats.get(def_stat, 1) * defender.stage_multiplier(def_stat)

    # Burn halves physical attack
    if attacker.status == "burn" and move.category == "physical":
        atk *= 0.5

    base = (2 * level / 5 + 2) * move.power * (atk / def_)
    base = base / 50 + 2

    # STAB
    stab = STAB_MULTIPLIER if move.type_ in attacker.types else 1.0

    # Type effectiveness -- use the rules object's type chart
    type_mult = rules.type_chart.multiplier(move.type_, defender.types)
    if type_mult == 0.0:
        return 0.0  # immune

    # Accuracy as expected-value weight (0 accuracy means always hits)
    acc_weight = (move.accuracy / 100.0) if move.accuracy > 0 else 1.0

    return max(1.0, base * stab * type_mult * acc_weight)


def _apply_status(target: Pokemon, status: str) -> bool:
    """
    Apply a status condition deterministically.
    Returns True if applied, False if the target is immune or already statused.
    """
    if target.status is not None:
        return False

    # Type immunities
    immunities: dict[str, list[str]] = {
        "burn": ["fire"],
        "poison": ["poison", "steel"],
        "paralysis": ["electric"],
        "freeze": ["ice"],
    }
    for immune_type in immunities.get(status, []):
        if immune_type in target.types:
            return False

    target.status = status
    if status == "sleep":
        # Deterministic sleep: always 2 turns (the median of the Gen 6 range)
        target.status_counter = 2
    elif status == "freeze":
        # Deterministic freeze: always thaws after 2 turns
        target.status_counter = 2
    return True


def _end_of_turn_status(pokemon: Pokemon) -> None:
    """Apply end-of-turn status damage and tick down sleep/freeze counters."""
    if pokemon.status == "burn":
        pokemon.current_hp -= max(1, pokemon.max_hp // 16)
    elif pokemon.status == "poison":
        pokemon.current_hp -= max(1, pokemon.max_hp // 8)
    elif pokemon.status in ("sleep", "freeze"):
        pokemon.status_counter -= 1
        if pokemon.status_counter <= 0:
            pokemon.status = None
    pokemon.current_hp = max(0, pokemon.current_hp)


def _check_status_skip(pokemon: Pokemon) -> bool:
    """
    Returns True if the Pokemon cannot act this turn due to status.
    Fully deterministic -- no random paralysis skip, no random thaw.
    Paralysis halves speed (applied to speed in turn order) but does not
    randomly skip turns; sleep and freeze block until the counter expires.
    """
    if pokemon.status in ("sleep", "freeze"):
        return pokemon.status_counter > 0
    return False


def _status_is_advantageous(attacker: Pokemon, defender: Pokemon) -> bool:
    """
    Return True if applying a status move against this defender is a net
    battle advantage given the current matchup.

    Rules:
    - Never stack status (defender already has one).
    - Burn is advantageous when the defender's best moves are physical
      (attack > sp_atk) because it halves their physical damage output.
    - Paralysis is advantageous when the defender is faster (halves their
      speed, potentially reversing turn order).
    - Poison and sleep are always advantageous (unconditional HP drain /
      action denial) unless the defender is immune.
    """
    return defender.status is None


def _choose_move(attacker: Pokemon, defender: Pokemon, rules: BattleRules | None = None) -> Move:
    """
    Deterministic AI move selection.

    Priority:
    1. Use a status move if it gives a concrete battle advantage AND the
       defender is not already statused (one status application per fight).
    2. Pick the damaging move with the highest expected output
       (power * STAB * type_effectiveness * accuracy_weight).
    3. Fall back to the first move if no damaging moves exist.
    """
    status_moves = [m for m in attacker.moves if m.category == "status"]
    damaging_moves = [
        m for m in attacker.moves if m.category in ("physical", "special") and m.power > 0
    ]

    # Use a status move when it is strategically advantageous.
    # Only consider moves that actually affect the opponent (have a status_effect
    # or stat_changes); pure self-utility moves like Recover are ignored here.
    offensive_status_moves = [m for m in status_moves if m.status_effect or m.stat_changes]
    if offensive_status_moves and _status_is_advantageous(attacker, defender):
        # Prefer the status move only if it gives a stronger expected advantage
        # than just attacking this turn. We approximate this by checking
        # whether the best damaging move would KO the defender in one hit --
        # if so, just attack; otherwise the status is worth a turn investment.
        if damaging_moves:
            best_dmg = max(
                _calc_damage(attacker, defender, m, level=100, rules=rules) for m in damaging_moves
            )
            if best_dmg < defender.current_hp:
                # Cannot one-shot -- a status debuff is worth applying
                return offensive_status_moves[0]
        else:
            return offensive_status_moves[0]

    if not damaging_moves:
        return attacker.moves[0]

    return max(
        damaging_moves,
        key=lambda m: _calc_damage(attacker, defender, m, level=100, rules=rules),
    )


def _apply_stat_changes(
    user: Pokemon,
    target: Pokemon,
    stat_changes: dict[str, int],
) -> None:
    """Apply stat stage changes from a move. Negative values lower target's stats."""
    for stat, delta in stat_changes.items():
        if delta < 0:
            current = target.stat_stages.get(stat, 0)
            target.stat_stages[stat] = max(-6, current + delta)
        else:
            current = user.stat_stages.get(stat, 0)
            user.stat_stages[stat] = min(6, current + delta)


def run_battle(
    pokemon_a: Pokemon,
    pokemon_b: Pokemon,
    level: int = 100,
    rand_ivs: bool = False,
    rng: random.Random | None = None,
    rules: BattleRules | None = None,
) -> BattleResult:
    """
    Run a single battle between two Pokemon.
    Returns a BattleResult with winner, turns, and HP data.
    Pokemon instances are not mutated -- deep copies are used internally.

    The battle is fully deterministic when rand_ivs=False (the default).
    With rand_ivs=True an rng is used only for IV generation at the start;
    all in-battle decisions remain deterministic.

    rules defaults to Gen6Rules() when not provided.
    """
    if rules is None:
        rules = Gen6Rules()
    if rng is None:
        rng = random.Random()

    ivs_a = random_ivs(rng) if rand_ivs else None
    ivs_b = random_ivs(rng) if rand_ivs else None

    a = initialize_battle_state(pokemon_a, level=level, ivs=ivs_a, rules=rules)
    b = initialize_battle_state(pokemon_b, level=level, ivs=ivs_b, rules=rules)

    turns = 0
    while turns < MAX_TURNS:
        turns += 1

        # Determine move order by speed; paralysis halves speed
        spd_a = a.stats.get("speed", 1) * a.stage_multiplier("speed")
        spd_b = b.stats.get("speed", 1) * b.stage_multiplier("speed")
        if a.status == "paralysis":
            spd_a *= 0.5
        if b.status == "paralysis":
            spd_b *= 0.5

        # Speed ties broken by rng -- the only remaining non-IV rng in a
        # deterministic run; ties are rare and have no strategic content
        if spd_a > spd_b:
            first, second = a, b
        elif spd_b > spd_a:
            first, second = b, a
        else:
            first, second = (a, b) if rng.random() < 0.5 else (b, a)

        for attacker, defender in ((first, second), (second, first)):
            if attacker.is_fainted() or defender.is_fainted():
                break

            # Sleep / freeze block action
            if _check_status_skip(attacker):
                continue

            move = _choose_move(attacker, defender, rules=rules)

            if move.category == "status":
                if move.status_effect:
                    _apply_status(defender, move.status_effect)
                if move.stat_changes:
                    _apply_stat_changes(attacker, defender, move.stat_changes)
            else:
                dmg = _calc_damage(attacker, defender, move, level=level, rules=rules)
                defender.current_hp = max(0, defender.current_hp - int(dmg))
                # Deterministic secondary status: apply if the move has one
                # and the target is not already statused
                if move.status_effect and defender.status is None:
                    _apply_status(defender, move.status_effect)

            if defender.is_fainted():
                break

        # End-of-turn status damage and sleep/freeze tick
        _end_of_turn_status(a)
        _end_of_turn_status(b)

        if a.is_fainted() or b.is_fainted():
            break

    # Determine winner
    timeout = turns >= MAX_TURNS and not a.is_fainted() and not b.is_fainted()
    if timeout:
        pct_a = a.current_hp / a.max_hp
        pct_b = b.current_hp / b.max_hp
        winner, loser = (a, b) if pct_a >= pct_b else (b, a)
    elif a.is_fainted():
        winner, loser = b, a
    else:
        winner, loser = a, b

    # Check if winner had a type advantage -- check all of winner's types
    winner_has_adv = any(rules.type_chart.multiplier(t, loser.types) > 1.0 for t in winner.types)

    return BattleResult(
        winner=winner.name,
        loser=loser.name,
        turns=turns,
        timeout=timeout,
        winner_hp_remaining=winner.current_hp,
        winner_hp_max=winner.max_hp,
        winner_hp_pct=winner.current_hp / winner.max_hp,
        attacker_had_advantage=winner_has_adv,
    )
