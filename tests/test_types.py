"""
Tests for the type chart.
"""

from pokerena.engine.types import TYPE_CHART, TypeChart


class TestTypeChartMultiplier:
    def test_super_effective(self):
        assert TYPE_CHART.multiplier("fire", ["grass"]) == 2.0

    def test_not_very_effective(self):
        assert TYPE_CHART.multiplier("fire", ["water"]) == 0.5

    def test_immune(self):
        assert TYPE_CHART.multiplier("normal", ["ghost"]) == 0.0

    def test_neutral(self):
        assert TYPE_CHART.multiplier("normal", ["normal"]) == 1.0

    def test_dual_type_both_weak(self):
        # Rock vs Fire/Flying = 2 * 2 = 4x
        assert TYPE_CHART.multiplier("rock", ["fire", "flying"]) == 4.0

    def test_dual_type_one_immune(self):
        # Ground vs Electric/Flying -- flying is immune to ground
        assert TYPE_CHART.multiplier("ground", ["electric", "flying"]) == 0.0

    def test_dual_type_cancel_out(self):
        # Fire vs Water/Grass = 0.5 * 2 = 1.0
        assert TYPE_CHART.multiplier("fire", ["water", "grass"]) == 1.0

    def test_dual_type_double_resist(self):
        # Water vs Water/Dragon = 0.5 * 0.5 = 0.25
        assert TYPE_CHART.multiplier("water", ["water", "dragon"]) == 0.25

    def test_unknown_attacking_type_is_neutral(self):
        # Unknown types should not raise; default to 1.0
        assert TYPE_CHART.multiplier("???", ["normal"]) == 1.0

    def test_fairy_vs_dragon_immune(self):
        # Dragon moves don't affect Fairy types
        assert TYPE_CHART.multiplier("dragon", ["fairy"]) == 0.0

    def test_fighting_vs_ghost_immune(self):
        assert TYPE_CHART.multiplier("fighting", ["ghost"]) == 0.0

    def test_steel_resists_many(self):
        # Steel resists fire (0.5), not 2x
        assert TYPE_CHART.multiplier("fire", ["steel"]) == 2.0  # fire is SE vs steel
        assert TYPE_CHART.multiplier("steel", ["fire"]) == 0.5  # steel is NVE vs fire

    def test_poison_immune_to_steel(self):
        assert TYPE_CHART.multiplier("poison", ["steel"]) == 0.0


class TestIsImmune:
    def test_normal_vs_ghost(self):
        assert TYPE_CHART.is_immune("normal", ["ghost"]) is True

    def test_fire_vs_grass_not_immune(self):
        assert TYPE_CHART.is_immune("fire", ["grass"]) is False

    def test_ground_vs_flying(self):
        assert TYPE_CHART.is_immune("ground", ["flying"]) is True


class TestTypeChartSingleton:
    def test_is_singleton(self):
        from pokerena.engine.types import TYPE_CHART as tc2

        assert TYPE_CHART is tc2

    def test_is_typechart_instance(self):
        assert isinstance(TYPE_CHART, TypeChart)
