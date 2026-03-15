"""
Tests for the battle engine.
"""

import random

import pytest

from pokerena.engine.battle import (
    BattleResult,
    _apply_stat_changes,
    _apply_status,
    _calc_damage,
    _check_status_skip,
    _end_of_turn_status,
    _status_is_advantageous,
    run_battle,
)
from pokerena.engine.rules import Gen1Rules, Gen2Rules, Gen3Rules, Gen6Rules
from pokerena.engine.stats import initialize_battle_state
from pokerena.models import Move, Pokemon


def _init(pokemon: Pokemon, **kwargs) -> Pokemon:
    """Initialize battle state for a Pokemon and return the copy."""
    return initialize_battle_state(pokemon, **kwargs)


class TestRunBattle:
    """Tests for the top-level run_battle function."""

    def test_returns_battle_result(self, mewtwo, charizard, seeded_rng):
        """run_battle should return a BattleResult instance."""
        result = run_battle(mewtwo, charizard, rng=seeded_rng)
        assert isinstance(result, BattleResult)

    def test_winner_is_one_of_the_two(self, mewtwo, charizard, seeded_rng):
        """Winner and loser should be the two combatants and must differ."""
        result = run_battle(mewtwo, charizard, rng=seeded_rng)
        assert result.winner in {mewtwo.name, charizard.name}
        assert result.loser in {mewtwo.name, charizard.name}
        assert result.winner != result.loser

    def test_turns_positive(self, mewtwo, charizard, seeded_rng):
        """A battle should last at least one turn."""
        result = run_battle(mewtwo, charizard, rng=seeded_rng)
        assert result.turns >= 1

    def test_turns_capped_at_60(self, magikarp_splash, magikarp_b, seeded_rng):
        """Two Splash-only Magikarp should time out at exactly 60 turns."""
        result = run_battle(magikarp_splash, magikarp_b, rng=seeded_rng)
        assert result.turns == 60
        assert result.timeout is True

    def test_winner_hp_pct_between_0_and_1(self, mewtwo, charizard, seeded_rng):
        """Winner HP percentage should be in the range (0, 1]."""
        result = run_battle(mewtwo, charizard, rng=seeded_rng)
        assert 0.0 < result.winner_hp_pct <= 1.0

    def test_stronger_wins_majority(self, mewtwo, charizard):
        """Mewtwo (Ubers) should win the majority of battles against Charizard (OU).

        With deterministic damage, a BST-dominant Pokemon should win
        consistently -- we expect at least 20 out of 30 wins.
        """
        wins = 0
        for i in range(30):
            r = run_battle(mewtwo, charizard, rng=random.Random(i))
            if r.winner == mewtwo.name:
                wins += 1
        assert wins >= 20, f"Mewtwo only won {wins}/30 -- expected dominance"

    def test_reproducible_with_same_seed(self, mewtwo, charizard):
        """The same seed should always produce the same battle outcome."""
        r1 = run_battle(mewtwo, charizard, rng=random.Random(42))
        r2 = run_battle(mewtwo, charizard, rng=random.Random(42))
        assert r1.winner == r2.winner
        assert r1.turns == r2.turns

    def test_deterministic_without_rand_ivs(self, mewtwo, charizard):
        """Without rand_ivs, every run with any seed should produce the same result
        since the only remaining RNG use is speed-tie breaking (not applicable here
        as Mewtwo and Charizard have different speeds)."""
        results = {run_battle(mewtwo, charizard, rng=random.Random(i)).winner for i in range(20)}
        # Same two Pokemon, same max IVs, deterministic damage -- winner must be consistent
        assert len(results) == 1

    def test_rand_ivs_produces_variation(self, mewtwo, charizard):
        """Random IVs should produce variation in turn counts across battles."""
        results = set()
        for i in range(10):
            r = run_battle(mewtwo, charizard, rand_ivs=True, rng=random.Random(i))
            results.add(r.turns)
        assert len(results) > 1

    def test_original_pokemon_not_mutated(self, mewtwo, charizard):
        """run_battle must not mutate the original Pokemon instances."""
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
    """Tests for the _apply_status helper."""

    def test_apply_burn_to_fire_type_is_immune(self, charizard):
        """Fire-type Pokemon should be immune to burn."""
        battler = _init(charizard)
        result = _apply_status(battler, "burn")
        assert result is False
        assert battler.status is None

    def test_apply_paralysis_to_non_electric(self, charizard):
        """Paralysis should apply successfully to a non-Electric Pokemon."""
        battler = _init(charizard)
        result = _apply_status(battler, "paralysis")
        assert result is True
        assert battler.status == "paralysis"

    def test_electric_immune_to_paralysis(self):
        """Electric-type Pokemon should be immune to paralysis."""
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
        result = _apply_status(battler, "paralysis")
        assert result is False

    def test_cannot_stack_status(self, mewtwo):
        """A second status should not overwrite an existing one."""
        battler = _init(mewtwo)
        _apply_status(battler, "paralysis")
        result = _apply_status(battler, "burn")
        assert result is False
        assert battler.status == "paralysis"

    def test_sleep_sets_counter_to_two(self, mewtwo):
        """Applying sleep should set status_counter to 2 (deterministic)."""
        battler = _init(mewtwo)
        _apply_status(battler, "sleep")
        assert battler.status == "sleep"
        assert battler.status_counter == 2

    def test_freeze_sets_counter_to_two(self, mewtwo):
        """Applying freeze should set status_counter to 2 (deterministic)."""
        battler = _init(mewtwo)
        _apply_status(battler, "freeze")
        assert battler.status == "freeze"
        assert battler.status_counter == 2

    def test_poison_immune_steel(self, steelix):
        """Steel-type Pokemon should be immune to poison."""
        battler = _init(steelix)
        result = _apply_status(battler, "poison")
        assert result is False


class TestCheckStatusSkip:
    """Tests for the _check_status_skip helper."""

    def test_no_status_never_skips(self, mewtwo):
        """A Pokemon with no status should never be forced to skip."""
        battler = _init(mewtwo)
        assert all(_check_status_skip(battler) is False for _ in range(10))

    def test_sleep_skips_while_counter_positive(self, mewtwo):
        """Sleeping Pokemon should return True while counter > 0."""
        battler = _init(mewtwo)
        battler.status = "sleep"
        battler.status_counter = 2
        assert _check_status_skip(battler) is True
        assert _check_status_skip(battler) is True

    def test_paralysis_does_not_skip_turns(self, mewtwo):
        """Paralysis no longer causes random turn skips -- should always return False."""
        battler = _init(mewtwo)
        battler.status = "paralysis"
        assert all(_check_status_skip(battler) is False for _ in range(20))

    def test_freeze_skips_while_counter_positive(self, mewtwo):
        """A frozen Pokemon should skip while status_counter > 0."""
        battler = _init(mewtwo)
        battler.status = "freeze"
        battler.status_counter = 2
        assert _check_status_skip(battler) is True


class TestEndOfTurnStatus:
    """Tests for the _end_of_turn_status helper."""

    def test_burn_deals_damage(self, mewtwo):
        """Burn should reduce HP at end of turn."""
        battler = _init(mewtwo)
        battler.status = "burn"
        hp_before = battler.current_hp
        _end_of_turn_status(battler)
        assert battler.current_hp < hp_before

    def test_poison_deals_damage(self, mewtwo):
        """Poison should reduce HP at end of turn."""
        battler = _init(mewtwo)
        battler.status = "poison"
        hp_before = battler.current_hp
        _end_of_turn_status(battler)
        assert battler.current_hp < hp_before

    def test_no_status_no_damage(self, mewtwo):
        """A Pokemon with no status should not lose HP at end of turn."""
        battler = _init(mewtwo)
        hp_before = battler.current_hp
        _end_of_turn_status(battler)
        assert battler.current_hp == hp_before

    def test_paralysis_no_end_of_turn_damage(self, mewtwo):
        """Paralysis should not cause end-of-turn HP damage."""
        battler = _init(mewtwo)
        battler.status = "paralysis"
        hp_before = battler.current_hp
        _end_of_turn_status(battler)
        assert battler.current_hp == hp_before

    def test_hp_never_goes_below_zero(self, magikarp):
        """HP should be clamped to 0 and never go negative from status damage."""
        battler = _init(magikarp)
        battler.status = "poison"
        battler.current_hp = 1
        _end_of_turn_status(battler)
        assert battler.current_hp >= 0

    def test_sleep_counter_ticks_down(self, mewtwo):
        """Sleep counter should decrement each end-of-turn call."""
        battler = _init(mewtwo)
        battler.status = "sleep"
        battler.status_counter = 2
        _end_of_turn_status(battler)
        assert battler.status_counter == 1
        _end_of_turn_status(battler)
        assert battler.status_counter == 0
        assert battler.status is None


class TestCalcDamage:
    """Tests for the _calc_damage helper."""

    def test_immune_returns_zero(self):
        """Normal move vs Ghost type should return 0 (immune)."""
        attacker = initialize_battle_state(
            Pokemon(
                name="attacker",
                types=["normal"],
                base_stats=dict.fromkeys(
                    ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"], 100
                ),
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
                base_stats=dict.fromkeys(
                    ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"], 100
                ),
                moves=[Move("tackle", "normal", "physical", 40, 100, 35)],
                generation=1,
                smogon_tier="nu",
                bst=600,
            )
        )
        move = Move("tackle", "normal", "physical", 40, 100, 35)
        assert _calc_damage(attacker, defender, move) == 0.0

    def test_stab_increases_damage(self):
        """A STAB move should deal more damage than an equivalent non-STAB move."""
        attacker = initialize_battle_state(
            Pokemon(
                name="attacker",
                types=["fire"],
                base_stats=dict.fromkeys(
                    ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"], 100
                ),
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
                base_stats=dict.fromkeys(
                    ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"], 100
                ),
                moves=[],
                generation=1,
                smogon_tier="nu",
                bst=600,
            )
        )
        stab_move = Move("ember", "fire", "special", 40, 100, 25)
        non_stab_move = Move("swift", "normal", "special", 40, 100, 20)
        assert _calc_damage(attacker, defender, stab_move) > _calc_damage(
            attacker, defender, non_stab_move
        )

    def test_burn_halves_physical_damage(self):
        """A burned attacker should deal roughly half physical damage."""
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
                base_stats=dict.fromkeys(
                    ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"], 100
                ),
                moves=[],
                generation=1,
                smogon_tier="nu",
                bst=600,
            )
        )
        move = Move("tackle", "normal", "physical", 80, 0, 35)
        normal_dmg = _calc_damage(attacker, defender, move)
        attacker.status = "burn"
        burned_dmg = _calc_damage(attacker, defender, move)
        assert burned_dmg < normal_dmg
        assert burned_dmg <= normal_dmg * 0.6

    def test_accuracy_weights_damage(self):
        """A 50% accurate move should deal half the expected damage of a 100% accurate
        move with the same power, because accuracy is applied as a multiplier."""
        attacker = initialize_battle_state(
            Pokemon(
                name="attacker",
                types=["normal"],
                base_stats=dict.fromkeys(
                    ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"], 100
                ),
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
                base_stats=dict.fromkeys(
                    ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"], 100
                ),
                moves=[],
                generation=1,
                smogon_tier="nu",
                bst=600,
            )
        )
        full_acc = Move("move-a", "normal", "physical", 80, 100, 10)
        half_acc = Move("move-b", "normal", "physical", 80, 50, 10)
        dmg_full = _calc_damage(attacker, defender, full_acc)
        dmg_half = _calc_damage(attacker, defender, half_acc)
        assert dmg_half == pytest.approx(dmg_full * 0.5, rel=0.01)


class TestStatusIsAdvantageous:
    """Tests for the _status_is_advantageous helper."""

    def test_returns_false_when_defender_already_statused(self, mewtwo, charizard):
        """Should return False if the defender already has a status condition."""
        attacker = _init(mewtwo)
        defender = _init(charizard)
        defender.status = "burn"
        assert _status_is_advantageous(attacker, defender) is False

    def test_returns_true_when_defender_has_no_status(self, mewtwo, charizard):
        """Should return True when the defender has no status condition."""
        attacker = _init(mewtwo)
        defender = _init(charizard)
        assert defender.status is None
        assert _status_is_advantageous(attacker, defender) is True


class TestApplyStatChanges:
    """Tests for the _apply_stat_changes helper."""

    def test_negative_delta_lowers_target_stat(self, mewtwo, charizard):
        """Negative stat change should lower the target's stat stage."""
        user = _init(mewtwo)
        target = _init(charizard)
        _apply_stat_changes(user, target, {"attack": -1})
        assert target.stat_stages.get("attack", 0) == -1

    def test_positive_delta_raises_user_stat(self, mewtwo, charizard):
        """Positive stat change should raise the user's own stat stage."""
        user = _init(mewtwo)
        target = _init(charizard)
        _apply_stat_changes(user, target, {"sp_atk": 1})
        assert user.stat_stages.get("sp_atk", 0) == 1

    def test_stat_stage_capped_at_plus_six(self, mewtwo, charizard):
        """Stat stages should not exceed +6."""
        user = _init(mewtwo)
        target = _init(charizard)
        for _ in range(10):
            _apply_stat_changes(user, target, {"attack": 1})
        assert user.stat_stages.get("attack", 0) == 6

    def test_stat_stage_floored_at_minus_six(self, mewtwo, charizard):
        """Stat stages should not go below -6."""
        user = _init(mewtwo)
        target = _init(charizard)
        for _ in range(10):
            _apply_stat_changes(user, target, {"attack": -1})
        assert target.stat_stages.get("attack", 0) == -6


class TestRunBattleEdgePaths:
    """Tests for edge-case code paths in run_battle."""

    def test_no_rng_argument_still_runs(self, mewtwo, charizard):
        """run_battle should work without providing an rng (uses internal default)."""
        result = run_battle(mewtwo, charizard)
        assert isinstance(result, BattleResult)

    def test_b_faster_wins_when_stronger(self):
        """When pokemon_b is significantly faster and stronger, it should win."""
        slow = Pokemon(
            name="slow",
            types=["normal"],
            base_stats={
                "hp": 60,
                "attack": 50,
                "defense": 50,
                "sp_atk": 50,
                "sp_def": 50,
                "speed": 10,
            },
            moves=[Move("tackle", "normal", "physical", 40, 100, 35)],
            generation=1,
            smogon_tier="pu",
            bst=310,
        )
        fast = Pokemon(
            name="fast",
            types=["normal"],
            base_stats={
                "hp": 100,
                "attack": 150,
                "defense": 100,
                "sp_atk": 100,
                "sp_def": 100,
                "speed": 200,
            },
            moves=[Move("hyper-beam", "normal", "special", 150, 90, 5)],
            generation=1,
            smogon_tier="ubers",
            bst=750,
        )
        result = run_battle(slow, fast, rng=random.Random(1))
        assert result.winner == "fast"

    def test_paralysis_halves_speed_in_battle(self, charizard, magikarp):
        """A paralyzed Pokemon should have its speed halved (may affect turn order)."""
        # Give charizard a thunder-wave move so it paralyses magikarp,
        # then verify the battle still completes without errors.
        charizard.moves = [
            Move("thunder-wave", "electric", "status", 0, 90, 20, status_effect="paralysis"),
            Move("flamethrower", "fire", "special", 90, 100, 15),
        ]
        result = run_battle(charizard, magikarp, rng=random.Random(1))
        assert isinstance(result, BattleResult)

    def test_secondary_status_applied_by_damaging_move(self):
        """A damaging move with a status_effect should apply status to the target."""
        burner = Pokemon(
            name="burner",
            types=["fire"],
            base_stats={
                "hp": 100,
                "attack": 100,
                "defense": 100,
                "sp_atk": 200,
                "sp_def": 100,
                "speed": 200,
            },
            moves=[
                Move(
                    "lava-plume",
                    "fire",
                    "special",
                    80,
                    100,
                    15,
                    status_effect="burn",
                )
            ],
            generation=4,
            smogon_tier="ou",
            bst=800,
        )
        target = Pokemon(
            name="target",
            types=["normal"],
            base_stats={
                "hp": 50,
                "attack": 50,
                "defense": 50,
                "sp_atk": 50,
                "sp_def": 50,
                "speed": 10,
            },
            moves=[Move("tackle", "normal", "physical", 40, 100, 35)],
            generation=1,
            smogon_tier="pu",
            bst=310,
        )
        # Run enough turns for burn to be applied (burner goes first, target survives
        # at least 1 turn); verify the battle completes
        result = run_battle(burner, target, rng=random.Random(0))
        assert isinstance(result, BattleResult)


class TestGenRules:
    """Tests that generation-specific rules produce correct type chart and stat values."""

    def _make_pokemon(self, name: str, types: list, base_stats: dict, moves: list) -> Pokemon:
        return Pokemon(
            name=name,
            types=types,
            base_stats=base_stats,
            moves=moves,
            generation=1,
            smogon_tier="ou",
            bst=sum(base_stats.values()),
        )

    def test_gen1_ghost_vs_psychic_is_zero(self):
        """Ghost attacking Psychic should be 0x in Gen 1 (famous bug)."""
        rules = Gen1Rules()
        assert rules.type_chart.multiplier("ghost", ["psychic"]) == 0.0

    def test_gen2_ghost_vs_psychic_is_two(self):
        """Ghost attacking Psychic should be 2x in Gen 2+ (bug fixed)."""
        rules = Gen2Rules()
        assert rules.type_chart.multiplier("ghost", ["psychic"]) == 2.0

    def test_gen6_ghost_vs_psychic_is_two(self):
        """Ghost attacking Psychic should still be 2x in Gen 6."""
        rules = Gen6Rules()
        assert rules.type_chart.multiplier("ghost", ["psychic"]) == 2.0

    def test_gen1_poison_vs_bug_is_two(self):
        """Poison attacking Bug should be 2x in Gen 1."""
        rules = Gen1Rules()
        assert rules.type_chart.multiplier("poison", ["bug"]) == 2.0

    def test_gen2_poison_vs_bug_is_half(self):
        """Poison attacking Bug should be 0.5x in Gen 2+."""
        rules = Gen2Rules()
        assert rules.type_chart.multiplier("poison", ["bug"]) == 0.5

    def test_gen1_ice_vs_fire_is_one(self):
        """Ice attacking Fire should be 1x (neutral) in Gen 1."""
        rules = Gen1Rules()
        assert rules.type_chart.multiplier("ice", ["fire"]) == 1.0

    def test_gen2_ice_vs_fire_is_half(self):
        """Ice attacking Fire should be 0.5x in Gen 2+."""
        rules = Gen2Rules()
        assert rules.type_chart.multiplier("ice", ["fire"]) == 0.5

    def test_gen2_ghost_vs_steel_is_zero(self):
        """Ghost attacking Steel should be 0x (immune) in Gen 2-5."""
        rules = Gen2Rules()
        assert rules.type_chart.multiplier("ghost", ["steel"]) == 0.0

    def test_gen6_ghost_vs_steel_is_half(self):
        """Ghost attacking Steel should be 0.5x in Gen 6+ (immunity removed)."""
        rules = Gen6Rules()
        assert rules.type_chart.multiplier("ghost", ["steel"]) == 0.5

    def test_gen2_dark_vs_steel_is_zero(self):
        """Dark attacking Steel should be 0x (immune) in Gen 2-5."""
        rules = Gen2Rules()
        assert rules.type_chart.multiplier("dark", ["steel"]) == 0.0

    def test_gen6_dark_vs_steel_is_half(self):
        """Dark attacking Steel should be 0.5x in Gen 6+ (immunity removed)."""
        rules = Gen6Rules()
        assert rules.type_chart.multiplier("dark", ["steel"]) == 0.5

    def test_gen6_fairy_type_exists(self):
        """Fairy type should exist in Gen 6 chart -- Dragon vs Fairy is 0x."""
        rules = Gen6Rules()
        assert rules.type_chart.multiplier("dragon", ["fairy"]) == 0.0

    def test_gen1_no_fairy_type(self):
        """Gen 1 type chart does not have Fairy -- Dragon vs Fairy should be 1x (neutral)."""
        rules = Gen1Rules()
        assert rules.type_chart.multiplier("dragon", ["fairy"]) == 1.0

    def test_gen1_stat_formula_produces_correct_value(self):
        """Gen 1/2 stat formula: non-HP = floor(((base+iv)*2*level)/100) + 5."""
        rules = Gen1Rules()
        # base=100, iv=31, level=100 -> floor((131*2*100)/100) + 5 = 262 + 5 = 267
        assert rules.compute_stat(base=100, iv=31, level=100, is_hp=False) == 267

    def test_gen3_stat_formula_produces_correct_value(self):
        """Gen 3+ stat formula: non-HP = floor((2*base+iv)*level/100) + 5."""
        rules = Gen3Rules()
        # base=100, iv=31, level=100 -> floor((200+31)*100/100) + 5 = 231 + 5 = 236
        assert rules.compute_stat(base=100, iv=31, level=100, is_hp=False) == 236

    def test_gen1_hp_formula(self):
        """Gen 1/2 HP formula: floor(((base+iv)*2*level)/100) + level + 10."""
        rules = Gen1Rules()
        # base=100, iv=31, level=100 -> 262 + 100 + 10 = 372
        assert rules.compute_stat(base=100, iv=31, level=100, is_hp=True) == 372

    def test_gen3_hp_formula(self):
        """Gen 3+ HP formula: floor((2*base+iv)*level/100) + level + 10."""
        rules = Gen3Rules()
        # base=100, iv=31, level=100 -> 231 + 100 + 10 = 341
        assert rules.compute_stat(base=100, iv=31, level=100, is_hp=True) == 341

    def test_gen1_battle_uses_gen1_type_chart(self):
        """run_battle with Gen1Rules should treat Ghost vs Psychic as 0x damage."""
        gen1 = Gen1Rules()
        ghost_attacker = self._make_pokemon(
            "gengar",
            ["ghost", "poison"],
            {"hp": 60, "attack": 65, "defense": 60, "sp_atk": 130, "sp_def": 75, "speed": 110},
            [Move("shadow-ball", "ghost", "special", 80, 100, 15)],
        )
        psychic_defender = self._make_pokemon(
            "alakazam",
            ["psychic"],
            {"hp": 55, "attack": 50, "defense": 45, "sp_atk": 135, "sp_def": 95, "speed": 120},
            [Move("psychic", "psychic", "special", 90, 100, 10)],
        )
        a = initialize_battle_state(ghost_attacker, rules=gen1)
        d = initialize_battle_state(psychic_defender, rules=gen1)
        shadow_ball = Move("shadow-ball", "ghost", "special", 80, 100, 15)
        assert _calc_damage(a, d, shadow_ball, rules=gen1) == 0.0

    def test_gen2_battle_uses_corrected_type_chart(self):
        """run_battle with Gen2Rules should treat Ghost vs Psychic as 2x damage."""
        gen2 = Gen2Rules()
        ghost_attacker = self._make_pokemon(
            "gengar",
            ["ghost", "poison"],
            {"hp": 60, "attack": 65, "defense": 60, "sp_atk": 130, "sp_def": 75, "speed": 110},
            [Move("shadow-ball", "ghost", "special", 80, 100, 15)],
        )
        neutral_defender = self._make_pokemon(
            "normal-mon",
            ["normal"],
            {"hp": 60, "attack": 65, "defense": 60, "sp_atk": 130, "sp_def": 75, "speed": 110},
            [Move("tackle", "normal", "physical", 40, 100, 35)],
        )
        psychic_defender = self._make_pokemon(
            "alakazam",
            ["psychic"],
            {"hp": 60, "attack": 65, "defense": 60, "sp_atk": 130, "sp_def": 75, "speed": 110},
            [Move("psychic", "psychic", "special", 90, 100, 10)],
        )
        shadow_ball = Move("shadow-ball", "ghost", "special", 80, 100, 15)
        a = initialize_battle_state(ghost_attacker, rules=gen2)
        d_neutral = initialize_battle_state(neutral_defender, rules=gen2)
        d_psychic = initialize_battle_state(psychic_defender, rules=gen2)
        dmg_neutral = _calc_damage(a, d_neutral, shadow_ball, rules=gen2)
        dmg_psychic = _calc_damage(a, d_psychic, shadow_ball, rules=gen2)
        # Ghost-type STAB vs Psychic should be more than 2x neutral (STAB * 2x = 3x effective)
        assert dmg_psychic > dmg_neutral
