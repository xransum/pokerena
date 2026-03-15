"""
Tests for the stat calculator.
"""

from pokerena.engine.stats import compute_stats, initialize_battle_state, random_ivs
from pokerena.models import Move, Pokemon


def _simple_pokemon(**overrides):
    """Build a minimal Pokemon fixture with sensible defaults, accepting keyword overrides."""
    base = {
        "name": "testmon",
        "types": ["normal"],
        "base_stats": {
            "hp": 45,
            "attack": 49,
            "defense": 49,
            "sp_atk": 65,
            "sp_def": 65,
            "speed": 45,
        },
        "moves": [Move("tackle", "normal", "physical", 40, 100, 35)],
        "generation": 1,
        "smogon_tier": "nu",
        "bst": 318,
    }
    base.update(overrides)
    return Pokemon(**base)


class TestComputeStats:
    """Tests for the compute_stats function."""

    def test_hp_higher_than_other_stats_for_bulky(self):
        """A Pokemon with very high base HP should have HP exceed its defensive stats."""
        # Chansey: 250 base HP
        chansey = _simple_pokemon(
            name="chansey",
            base_stats={
                "hp": 250,
                "attack": 5,
                "defense": 5,
                "sp_atk": 35,
                "sp_def": 105,
                "speed": 50,
            },
            bst=450,
        )
        stats = compute_stats(chansey, level=100)
        assert stats["hp"] > stats["defense"]
        assert stats["hp"] > stats["sp_def"]

    def test_max_ivs_produce_higher_stats_than_zero_ivs(self):
        """Max IVs (31) should produce strictly higher stats than zero IVs across every stat."""
        p = _simple_pokemon()
        max_stats = compute_stats(p, level=100, ivs=dict.fromkeys(p.base_stats, 31))
        zero_stats = compute_stats(p, level=100, ivs=dict.fromkeys(p.base_stats, 0))
        for stat in p.base_stats:
            assert max_stats[stat] > zero_stats[stat]

    def test_higher_base_stat_produces_higher_final_stat(self):
        """A Pokemon with higher base stats should have higher final stats than one with lower base stats."""
        low = _simple_pokemon(
            base_stats={
                "hp": 45,
                "attack": 45,
                "defense": 45,
                "sp_atk": 45,
                "sp_def": 45,
                "speed": 45,
            },
            bst=270,
        )
        high = _simple_pokemon(
            base_stats={
                "hp": 100,
                "attack": 100,
                "defense": 100,
                "sp_atk": 100,
                "sp_def": 100,
                "speed": 100,
            },
            bst=600,
        )
        low_stats = compute_stats(low, level=100)
        high_stats = compute_stats(high, level=100)
        for stat in low.base_stats:
            assert high_stats[stat] > low_stats[stat]

    def test_hp_formula_gen3(self):
        """HP stat should match the Gen 3 formula: floor((2*base + iv) * level / 100) + level + 10."""
        # HP = floor((2 * base + iv) * level / 100) + level + 10
        # base=45, iv=31, level=100 => floor((90+31)*100/100) + 100 + 10 = 121+110 = 231... wait
        # => floor(121) + 110 = 231
        p = _simple_pokemon(
            base_stats={
                "hp": 45,
                "attack": 45,
                "defense": 45,
                "sp_atk": 45,
                "sp_def": 45,
                "speed": 45,
            },
            bst=270,
        )
        stats = compute_stats(p, level=100, ivs=dict.fromkeys(p.base_stats, 31))
        expected_hp = (2 * 45 + 31) * 100 // 100 + 100 + 10
        assert stats["hp"] == expected_hp

    def test_non_hp_formula_gen3(self):
        """Non-HP stats should match the Gen 3 formula: floor((2*base + iv) * level / 100) + 5."""
        p = _simple_pokemon(
            base_stats={
                "hp": 45,
                "attack": 49,
                "defense": 49,
                "sp_atk": 65,
                "sp_def": 65,
                "speed": 45,
            },
            bst=318,
        )
        stats = compute_stats(p, level=100, ivs=dict.fromkeys(p.base_stats, 31))
        expected_atk = (2 * 49 + 31) * 100 // 100 + 5
        assert stats["attack"] == expected_atk

    def test_gen1_formula_differs_from_gen3(self):
        """Gen 1 stat formula should produce different values from the Gen 3 formula."""
        p = _simple_pokemon()
        gen3 = compute_stats(p, level=100, gen1_mode=False)
        gen1 = compute_stats(p, level=100, gen1_mode=True)
        # The two formulas produce different values
        assert gen3 != gen1

    def test_stat_minimum_is_one(self):
        """Every computed stat should be at least 1, even with base 1 and zero IVs at level 1."""
        p = _simple_pokemon(
            base_stats={"hp": 1, "attack": 1, "defense": 1, "sp_atk": 1, "sp_def": 1, "speed": 1},
            bst=6,
        )
        stats = compute_stats(p, level=1, ivs=dict.fromkeys(p.base_stats, 0))
        for val in stats.values():
            assert val >= 1

    def test_level_scales_stats(self):
        """Stats computed at level 100 should be strictly higher than at level 50."""
        p = _simple_pokemon()
        lv50 = compute_stats(p, level=50)
        lv100 = compute_stats(p, level=100)
        for stat in p.base_stats:
            assert lv100[stat] > lv50[stat]


class TestRandomIvs:
    """Tests for the random_ivs function."""

    def test_returns_all_stats(self):
        """random_ivs should return a dict with keys for all six stats."""
        import random

        ivs = random_ivs(random.Random(0))
        expected = {"hp", "attack", "defense", "sp_atk", "sp_def", "speed"}
        assert set(ivs.keys()) == expected

    def test_values_in_range(self):
        """All IV values should fall within [0, max_iv]."""
        import random

        rng = random.Random(0)
        for _ in range(100):
            ivs = random_ivs(rng, max_iv=15)
            for v in ivs.values():
                assert 0 <= v <= 15

    def test_seeded_is_reproducible(self):
        """Two calls with the same seed should return identical IVs."""
        import random

        ivs1 = random_ivs(random.Random(99))
        ivs2 = random_ivs(random.Random(99))
        assert ivs1 == ivs2


class TestInitializeBattleState:
    """Tests for the initialize_battle_state function."""

    def test_hp_set_to_max(self):
        """The battler's current_hp should equal max_hp and be positive after initialization."""
        p = _simple_pokemon()
        battler = initialize_battle_state(p)
        assert battler.current_hp == battler.max_hp
        assert battler.max_hp > 0

    def test_status_cleared(self):
        """Any pre-existing status on the source Pokemon should be cleared in the battler."""
        p = _simple_pokemon()
        p.status = "burn"
        battler = initialize_battle_state(p)
        assert battler.status is None

    def test_stat_stages_zeroed(self):
        """All stat stages should be initialised to zero."""
        p = _simple_pokemon()
        battler = initialize_battle_state(p)
        for v in battler.stat_stages.values():
            assert v == 0

    def test_original_not_mutated(self):
        """Calling initialize_battle_state should not modify the original Pokemon object."""
        p = _simple_pokemon()
        original_hp = p.current_hp
        initialize_battle_state(p)
        assert p.current_hp == original_hp

    def test_stats_dict_populated(self):
        """The battler's stats dict should contain all stat keys with positive values."""
        p = _simple_pokemon()
        battler = initialize_battle_state(p)
        assert "attack" in battler.stats
        assert "speed" in battler.stats
        assert all(v > 0 for v in battler.stats.values())
