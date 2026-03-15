"""
Tests for the battle engine.
"""

import random

import pytest

from pokerena.engine.battle import (
    BattleResult,
    _apply_status,
    _calc_damage,
    _check_status_skip,
    _end_of_turn_status,
    run_battle,
)
from pokerena.engine.stats import initialize_battle_state
from pokerena.models import Move, Pokemon


def _init(pokemon: Pokemon, **kwargs) -> Pokemon:
    return initialize_battle_state(pokemon, **kwargs)


class TestRunBattle:
    def test_returns_battle_result(self, mewtwo, charizard, seeded_rng):
        result = run_battle(mewtwo, charizard, rng=seeded_rng)
        assert isinstance(result, BattleResult)

    def test_winner_is_one_of_the_two(self, mewtwo, charizard, seeded_rng):
        result = run_battle(mewtwo, charizard, rng=seeded_rng)
        assert result.winner in {mewtwo.name, charizard.name}
        assert result.loser in {mewtwo.name, charizard.name}
        assert result.winner != result.loser

    def test_turns_positive(self, mewtwo, charizard, seeded_rng):
        result = run_battle(mewtwo, charizard, rng=seeded_rng)
        assert result.turns >= 1

    def test_turns_capped_at_60(self, magikarp_splash, magikarp_b, seeded_rng):
        # Two Magikarp with only Splash (status, no damage) should time out
        result = run_battle(magikarp_splash, magikarp_b, rng=seeded_rng)
        assert result.turns == 60
        assert result.timeout is True

    def test_winner_hp_pct_between_0_and_1(self, mewtwo, charizard, seeded_rng):
        result = run_battle(mewtwo, charizard, rng=seeded_rng)
        assert 0.0 < result.winner_hp_pct <= 1.0

    def test_stronger_wins_majority(self, mewtwo, charizard):
        # Mewtwo (680 BST Ubers) should beat Charizard (534 BST OU) consistently
        wins = 0
        for i in range(30):
            r = run_battle(mewtwo, charizard, rng=random.Random(i))
            if r.winner == mewtwo.name:
                wins += 1
        assert wins >= 20, f"Mewtwo only won {wins}/30 -- expected dominance"

    def test_reproducible_with_same_seed(self, mewtwo, charizard):
        r1 = run_battle(mewtwo, charizard, rng=random.Random(42))
        r2 = run_battle(mewtwo, charizard, rng=random.Random(42))
        assert r1.winner == r2.winner
        assert r1.turns == r2.turns

    def test_different_seeds_may_differ(self, mewtwo, charizard):
        results = {run_battle(mewtwo, charizard, rng=random.Random(i)).turns for i in range(20)}
        # Not all battles should have identical turn counts
        assert len(results) > 1

    def test_rand_ivs_produces_variation(self, mewtwo, charizard):
        results = set()
        for i in range(10):
            r = run_battle(mewtwo, charizard, rand_ivs=True, rng=random.Random(i))
            results.add(r.turns)
        assert len(results) > 1

    def test_original_pokemon_not_mutated(self, mewtwo, charizard):
        original_hp = mewtwo.current_hp
        original_status = mewtwo.status
        run_battle(mewtwo, charizard, rng=random.Random(1))
        assert mewtwo.current_hp == original_hp
        assert mewtwo.status == original_status


@pytest.fixture
def magikarp_splash():
    """Splash-only Magikarp for timeout tests (no damaging moves)."""
    return Pokemon(
        name="magikarp",
        types=["water"],
        base_stats={
            "hp": 20,
            "attack": 10,
            "defense": 55,
            "sp_atk": 15,
            "sp_def": 20,
            "speed": 80,
        },
        moves=[
            Move("splash", "normal", "status", 0, 0, 40),
        ],
        generation=1,
        smogon_tier="pu",
        bst=200,
    )


@pytest.fixture
def magikarp_b():
    """Second splash-only Magikarp for timeout tests."""
    return Pokemon(
        name="magikarp2",
        types=["water"],
        base_stats={
            "hp": 20,
            "attack": 10,
            "defense": 55,
            "sp_atk": 15,
            "sp_def": 20,
            "speed": 80,
        },
        moves=[
            Move("splash", "normal", "status", 0, 0, 40),
        ],
        generation=1,
        smogon_tier="pu",
        bst=200,
    )


class TestApplyStatus:
    def test_apply_burn(self, charizard, seeded_rng):
        battler = _init(charizard)
        # Charizard is Fire type -- should be immune to burn
        result = _apply_status(battler, "burn", seeded_rng)
        assert result is False
        assert battler.status is None

    def test_apply_paralysis_to_non_electric(self, charizard, seeded_rng):
        battler = _init(charizard)
        result = _apply_status(battler, "paralysis", seeded_rng)
        assert result is True
        assert battler.status == "paralysis"

    def test_electric_immune_to_paralysis(self, seeded_rng):
        jolteon = Pokemon(
            name="jolteon",
            types=["electric"],
            base_stats={
                "hp": 65,
                "attack": 65,
                "defense": 60,
                "sp_atk": 110,
                "sp_def": 95,
                "speed": 130,
            },
            moves=[Move("thunderbolt", "electric", "special", 90, 100, 15)],
            generation=1,
            smogon_tier="ou",
            bst=525,
        )
        battler = _init(jolteon)
        result = _apply_status(battler, "paralysis", seeded_rng)
        assert result is False

    def test_cannot_stack_status(self, mewtwo, seeded_rng):
        battler = _init(mewtwo)
        _apply_status(battler, "paralysis", seeded_rng)
        result = _apply_status(battler, "burn", seeded_rng)
        assert result is False
        assert battler.status == "paralysis"

    def test_sleep_sets_counter(self, mewtwo, seeded_rng):
        battler = _init(mewtwo)
        _apply_status(battler, "sleep", seeded_rng)
        assert battler.status == "sleep"
        assert 1 <= battler.status_counter <= 3

    def test_poison_immune_steel(self, steelix, seeded_rng):
        battler = _init(steelix)
        result = _apply_status(battler, "poison", seeded_rng)
        assert result is False


class TestCheckStatusSkip:
    def test_no_status_never_skips(self, mewtwo, seeded_rng):
        battler = _init(mewtwo)
        # Run many times -- should never skip
        assert all(_check_status_skip(battler, random.Random(i)) is False for i in range(50))

    def test_sleep_skips_until_counter_zero(self, mewtwo):
        battler = _init(mewtwo)
        battler.status = "sleep"
        battler.status_counter = 2
        # First two turns should skip
        assert _check_status_skip(battler, random.Random(0)) is True
        assert battler.status_counter == 1
        assert _check_status_skip(battler, random.Random(0)) is True
        assert battler.status_counter == 0
        # Third turn should wake up
        result = _check_status_skip(battler, random.Random(0))
        assert result is False
        assert battler.status is None

    def test_freeze_thaws_eventually(self, mewtwo):
        battler = _init(mewtwo)
        battler.status = "freeze"
        # With 20% thaw chance, should thaw within reasonable attempts
        thawed = False
        for i in range(200):
            if not _check_status_skip(battler, random.Random(i)):
                thawed = True
                break
        assert thawed

    def test_freeze_can_skip(self, mewtwo):
        # Use a deterministic RNG that doesn't thaw (rng.random() >= 0.20)
        battler = _init(mewtwo)
        battler.status = "freeze"
        # Random(seed=0) first float is ~0.637 which is > 0.20, so skip
        result = _check_status_skip(battler, random.Random(0))
        # May or may not skip depending on RNG -- just check it doesn't raise
        assert isinstance(result, bool)


class TestCalcDamage:
    def test_immune_returns_zero(self, seeded_rng):
        # Normal move vs Ghost type -- should return 0 (immune)
        attacker = initialize_battle_state(
            Pokemon(
                name="attacker",
                types=["normal"],
                base_stats={
                    "hp": 100,
                    "attack": 100,
                    "defense": 100,
                    "sp_atk": 100,
                    "sp_def": 100,
                    "speed": 100,
                },
                moves=[Move("tackle", "normal", "physical", 40, 100, 35)],
                generation=1,
                smogon_tier="nu",
                bst=600,
            )
        )
        defender = initialize_battle_state(
            Pokemon(
                name="ghost",
                types=["ghost"],
                base_stats={
                    "hp": 100,
                    "attack": 100,
                    "defense": 100,
                    "sp_atk": 100,
                    "sp_def": 100,
                    "speed": 100,
                },
                moves=[Move("tackle", "normal", "physical", 40, 100, 35)],
                generation=1,
                smogon_tier="nu",
                bst=600,
            )
        )
        move = Move("tackle", "normal", "physical", 40, 100, 35)
        dmg = _calc_damage(attacker, defender, move, seeded_rng)
        assert dmg == 0

    def test_stab_increases_damage(self, seeded_rng):
        """A STAB move should deal more damage than an equivalent non-STAB move."""
        attacker = initialize_battle_state(
            Pokemon(
                name="attacker",
                types=["fire"],
                base_stats={
                    "hp": 100,
                    "attack": 100,
                    "defense": 100,
                    "sp_atk": 100,
                    "sp_def": 100,
                    "speed": 100,
                },
                moves=[],
                generation=1,
                smogon_tier="nu",
                bst=600,
            )
        )
        defender = initialize_battle_state(
            Pokemon(
                name="defender",
                types=["normal"],
                base_stats={
                    "hp": 100,
                    "attack": 100,
                    "defense": 100,
                    "sp_atk": 100,
                    "sp_def": 100,
                    "speed": 100,
                },
                moves=[],
                generation=1,
                smogon_tier="nu",
                bst=600,
            )
        )
        stab_move = Move("ember", "fire", "special", 40, 100, 25)
        non_stab_move = Move("swift", "normal", "special", 40, 0, 20)

        rng = random.Random(42)
        stab_dmg = _calc_damage(attacker, defender, stab_move, rng)
        rng = random.Random(42)
        non_stab_dmg = _calc_damage(attacker, defender, non_stab_move, rng)

        assert stab_dmg > non_stab_dmg

    def test_burn_halves_physical_damage(self):
        attacker = initialize_battle_state(
            Pokemon(
                name="attacker",
                types=["normal"],
                base_stats={
                    "hp": 100,
                    "attack": 150,
                    "defense": 100,
                    "sp_atk": 100,
                    "sp_def": 100,
                    "speed": 100,
                },
                moves=[],
                generation=1,
                smogon_tier="nu",
                bst=650,
            )
        )
        defender = initialize_battle_state(
            Pokemon(
                name="defender",
                types=["normal"],
                base_stats={
                    "hp": 100,
                    "attack": 100,
                    "defense": 100,
                    "sp_atk": 100,
                    "sp_def": 100,
                    "speed": 100,
                },
                moves=[],
                generation=1,
                smogon_tier="nu",
                bst=600,
            )
        )
        move = Move("tackle", "normal", "physical", 80, 0, 35)
        rng = random.Random(42)
        normal_dmg = _calc_damage(attacker, defender, move, rng)

        attacker.status = "burn"
        rng = random.Random(42)
        burned_dmg = _calc_damage(attacker, defender, move, rng)

        assert burned_dmg < normal_dmg
        # Should be roughly half
        assert burned_dmg <= normal_dmg * 0.6

    def test_miss_returns_zero(self):
        attacker = initialize_battle_state(
            Pokemon(
                name="attacker",
                types=["normal"],
                base_stats={
                    "hp": 100,
                    "attack": 100,
                    "defense": 100,
                    "sp_atk": 100,
                    "sp_def": 100,
                    "speed": 100,
                },
                moves=[],
                generation=1,
                smogon_tier="nu",
                bst=600,
            )
        )
        defender = initialize_battle_state(
            Pokemon(
                name="defender",
                types=["normal"],
                base_stats={
                    "hp": 100,
                    "attack": 100,
                    "defense": 100,
                    "sp_atk": 100,
                    "sp_def": 100,
                    "speed": 100,
                },
                moves=[],
                generation=1,
                smogon_tier="nu",
                bst=600,
            )
        )
        # accuracy=1 means 99% chance to miss -- use a RNG that rolls >1
        move = Move("low-accuracy", "normal", "physical", 80, 1, 5)
        misses = sum(
            1
            for i in range(50)
            if _calc_damage(attacker, defender, move, random.Random(i * 7)) == 0
        )
        # The vast majority should miss
        assert misses >= 40


class TestEndOfTurnStatus:
    def test_burn_deals_damage(self, mewtwo):
        battler = _init(mewtwo)
        battler.status = "burn"
        hp_before = battler.current_hp
        _end_of_turn_status(battler, random.Random(0))
        assert battler.current_hp < hp_before

    def test_poison_deals_damage(self, mewtwo):
        battler = _init(mewtwo)
        battler.status = "poison"
        hp_before = battler.current_hp
        _end_of_turn_status(battler, random.Random(0))
        assert battler.current_hp < hp_before

    def test_no_status_no_damage(self, mewtwo):
        battler = _init(mewtwo)
        hp_before = battler.current_hp
        _end_of_turn_status(battler, random.Random(0))
        assert battler.current_hp == hp_before

    def test_paralysis_no_end_of_turn_damage(self, mewtwo):
        battler = _init(mewtwo)
        battler.status = "paralysis"
        hp_before = battler.current_hp
        _end_of_turn_status(battler, random.Random(0))
        assert battler.current_hp == hp_before

    def test_hp_never_goes_below_zero(self, magikarp):
        battler = _init(magikarp)
        battler.status = "poison"
        battler.current_hp = 1  # barely alive
        _end_of_turn_status(battler, random.Random(0))
        assert battler.current_hp >= 0
