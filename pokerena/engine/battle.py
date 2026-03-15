"""
Battle engine -- runs a single 1v1 Pokemon battle.

Implements:
- Gen 6 damage formula (default)
- Strategic AI with status move usage
- All status conditions (burn, paralysis, poison, sleep, freeze)
- Stat stage tracking
- Critical hits, accuracy rolls, STAB, type effectiveness
- 60-turn timeout resolved by HP percentage
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from pokerena.engine.stats import initialize_battle_state, random_ivs
from pokerena.engine.types import TYPE_CHART
from pokerena.models import Move, Pokemon

MAX_TURNS = 60
CRIT_CHANCE = 1 / 24  # Gen 6 base crit rate
CRIT_MULTIPLIER = 1.5
STAB_MULTIPLIER = 1.5
STATUS_MOVE_CHANCE = 0.25  # AI: 25% chance to use status if available
RANDOM_NOISE = 0.05  # ±5% noise on damage


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
    rng: random.Random,
    level: int = 100,
) -> int:
    """
    Gen 6 damage formula:
      Damage = floor((((2*L/5 + 2) * Power * Atk/Def) / 50 + 2)
               * STAB * TypeMultiplier * CritMultiplier * RandomFactor)
    """
    # Accuracy check
    if move.accuracy > 0 and rng.randint(1, 100) > move.accuracy:
        return 0  # miss

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

    # Paralysis halves speed (already applied to speed stat externally,
    # but does not affect damage)

    base = (2 * level / 5 + 2) * move.power * (atk / def_)
    base = base / 50 + 2

    # STAB
    stab = STAB_MULTIPLIER if move.type_ in attacker.types else 1.0

    # Type effectiveness
    type_mult = TYPE_CHART.multiplier(move.type_, defender.types)
    if type_mult == 0.0:
        return 0  # immune

    # Critical hit
    crit = CRIT_MULTIPLIER if rng.random() < CRIT_CHANCE else 1.0

    # Random factor ±5%
    noise = 1.0 + rng.uniform(-RANDOM_NOISE, RANDOM_NOISE)

    damage = int(base * stab * type_mult * crit * noise)
    return max(1, damage)


def _apply_status(target: Pokemon, status: str, rng: random.Random) -> bool:
    """
    Attempt to inflict a status condition.
    Returns True if applied, False if immune or already has status.
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
        target.status_counter = rng.randint(1, 3)
    elif status == "freeze":
        target.status_counter = 0  # thaw by 20% chance each turn
    return True


def _end_of_turn_status(pokemon: Pokemon, rng: random.Random) -> None:
    """Apply end-of-turn status damage."""
    if pokemon.status == "burn":
        pokemon.current_hp -= max(1, pokemon.max_hp // 16)
    elif pokemon.status == "poison":
        pokemon.current_hp -= max(1, pokemon.max_hp // 8)
    pokemon.current_hp = max(0, pokemon.current_hp)


def _check_status_skip(pokemon: Pokemon, rng: random.Random) -> bool:
    """
    Returns True if the Pokemon cannot act this turn due to status.
    Also handles sleep/freeze thaw and paralysis skip.
    """
    if pokemon.status == "sleep":
        if pokemon.status_counter > 0:
            pokemon.status_counter -= 1
            return True
        else:
            pokemon.status = None
            return False

    if pokemon.status == "freeze":
        if rng.random() < 0.20:  # 20% thaw chance
            pokemon.status = None
            return False
        return True

    return pokemon.status == "paralysis" and rng.random() < 0.25  # 25% full paralysis chance


def _apply_stat_changes(
    user: Pokemon,
    target: Pokemon,
    stat_changes: dict[str, int],
) -> None:
    """Apply stat stage changes from a move. Negative values lower target's stats."""
    for stat, delta in stat_changes.items():
        if delta < 0:
            # Lowers target's stat
            current = target.stat_stages.get(stat, 0)
            target.stat_stages[stat] = max(-6, current + delta)
        else:
            # Raises user's stat
            current = user.stat_stages.get(stat, 0)
            user.stat_stages[stat] = min(6, current + delta)


def _choose_move(
    attacker: Pokemon,
    defender: Pokemon,
    rng: random.Random,
) -> Move:
    """
    Strategic AI:
    1. If defender has no status AND a status move is available: 25% chance to use it
    2. Otherwise pick highest-scoring damaging move (with small noise)
    3. Fall back to first move if no damaging moves
    """
    status_moves = [m for m in attacker.moves if m.category == "status"]
    damaging_moves = [
        m for m in attacker.moves if m.category in ("physical", "special") and m.power > 0
    ]

    # Status move attempt
    if status_moves and defender.status is None and rng.random() < STATUS_MOVE_CHANCE:
        return rng.choice(status_moves)

    if not damaging_moves:
        return attacker.moves[0]

    # Score damaging moves with noise
    def _score(m: Move) -> float:
        """Score a move using type-chart effectiveness plus random noise."""
        base = m.score(attacker.types, defender.types, TYPE_CHART)
        return base * (1.0 + rng.uniform(-RANDOM_NOISE, RANDOM_NOISE))

    return max(damaging_moves, key=_score)


def run_battle(
    pokemon_a: Pokemon,
    pokemon_b: Pokemon,
    level: int = 100,
    rand_ivs: bool = False,
    rng: random.Random | None = None,
    gen1_mode: bool = False,
) -> BattleResult:
    """
    Run a single battle between two Pokemon.
    Returns a BattleResult with winner, turns, and HP data.
    Pokemon instances are not mutated -- deep copies are used internally.
    """
    if rng is None:
        rng = random.Random()

    ivs_a = random_ivs(rng) if rand_ivs else None
    ivs_b = random_ivs(rng) if rand_ivs else None

    a = initialize_battle_state(pokemon_a, level=level, ivs=ivs_a, gen1_mode=gen1_mode)
    b = initialize_battle_state(pokemon_b, level=level, ivs=ivs_b, gen1_mode=gen1_mode)

    # Apply paralysis speed penalty at init
    # (handled during turn via stage_multiplier; no separate init needed)

    turns = 0
    while turns < MAX_TURNS:
        turns += 1

        # Determine move order by speed (ties broken randomly)
        spd_a = a.stats.get("speed", 1) * a.stage_multiplier("speed")
        spd_b = b.stats.get("speed", 1) * b.stage_multiplier("speed")
        if a.status == "paralysis":
            spd_a *= 0.5
        if b.status == "paralysis":
            spd_b *= 0.5

        if spd_a > spd_b:
            first, second = a, b
        elif spd_b > spd_a:
            first, second = b, a
        else:
            first, second = (a, b) if rng.random() < 0.5 else (b, a)

        for attacker, defender in ((first, second), (second, first)):
            if attacker.is_fainted() or defender.is_fainted():
                break

            # Status skip check
            if _check_status_skip(attacker, rng):
                continue

            move = _choose_move(attacker, defender, rng)

            if move.category == "status":
                if move.status_effect:
                    _apply_status(defender, move.status_effect, rng)
                if move.stat_changes:
                    _apply_stat_changes(attacker, defender, move.stat_changes)
            else:
                dmg = _calc_damage(attacker, defender, move, rng, level=level)
                defender.current_hp = max(0, defender.current_hp - dmg)
                # Move may also inflict status (e.g. Flamethrower burn chance)
                if move.status_effect and rng.random() < 0.30:
                    _apply_status(defender, move.status_effect, rng)

            if defender.is_fainted():
                break

        # End-of-turn status damage
        _end_of_turn_status(a, rng)
        _end_of_turn_status(b, rng)

        if a.is_fainted() or b.is_fainted():
            break

    # Determine winner
    timeout = turns >= MAX_TURNS and not a.is_fainted() and not b.is_fainted()
    if timeout:
        # Resolve by highest HP percentage remaining
        pct_a = a.current_hp / a.max_hp
        pct_b = b.current_hp / b.max_hp
        winner, loser = (a, b) if pct_a >= pct_b else (b, a)
    elif a.is_fainted():
        winner, loser = b, a
    else:
        winner, loser = a, b

    # Check if the winner had a type advantage
    winner_has_adv = TYPE_CHART.multiplier(winner.types[0], loser.types) > 1.0

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
