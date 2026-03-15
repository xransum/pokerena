"""
Battle rules -- per-generation type charts and stat formulas.

Each generation subclass only overrides what actually changed.
Inheritance chain:

  Gen1Rules
    Gen2Rules(Gen1Rules)   -- adds Dark/Steel, fixes Ghost/Psychic bug
      Gen3Rules(Gen2Rules)  -- switches to Gen 3+ stat formula
        Gen4Rules(Gen3Rules)  -- placeholder, inherits all
          Gen5Rules(Gen4Rules)  -- placeholder, inherits all
            Gen6Rules(Gen5Rules)  -- adds Fairy, Steel loses Ghost/Dark immunity

Use RULES_BY_GEN[n] to get the correct rules object for a generation number.
"""

from __future__ import annotations

from pokerena.engine.types import TypeChart


class BattleRules:
    """Base class for generation-specific battle rules."""

    _chart: dict[str, dict[str, float]]
    gen1_stat_formula: bool

    def __init__(self) -> None:
        self.type_chart = TypeChart(self._chart)

    def compute_stat(self, base: int, iv: int, level: int, is_hp: bool) -> int:
        """
        Compute one final battle stat from base, IV, and level.

        Gen 1/2 formula:
          non-HP = floor(((base + iv) * 2 * level) / 100) + 5
          HP     = floor(((base + iv) * 2 * level) / 100) + level + 10

        Gen 3+ formula:
          non-HP = floor((2 * base + iv) * level / 100) + 5
          HP     = floor((2 * base + iv) * level / 100) + level + 10
        """
        if self.gen1_stat_formula:
            value = ((base + iv) * 2 * level) // 100
        else:
            value = (2 * base + iv) * level // 100

        if is_hp:
            value += level + 10
        else:
            value += 5

        return max(1, value)


class Gen1Rules(BattleRules):
    """
    Gen 1 rules.

    Type chart: 15 types (no Steel, Dark, or Fairy).
    Notable deviations from later gens that are intentionally preserved:
    - Ghost deals 0x to Psychic (famous Gen 1 bug; defined the meta).
    - Poison vs Bug: 2x (reversed in later gens).
    - Ice vs Fire: 1x (not 0.5x).
    - Bug vs Poison: 2x.
    - Bug vs Ghost: 2x.

    Stat formula: Gen 1/2 formula.
    """

    gen1_stat_formula = True

    _chart: dict[str, dict[str, float]] = {
        "normal": {
            "rock": 0.5,
            "ghost": 0.0,
        },
        "fire": {
            "fire": 0.5,
            "water": 0.5,
            "grass": 2.0,
            "ice": 2.0,
            "bug": 2.0,
            "rock": 0.5,
            "dragon": 0.5,
        },
        "water": {
            "fire": 2.0,
            "water": 0.5,
            "grass": 0.5,
            "ground": 2.0,
            "rock": 2.0,
            "dragon": 0.5,
        },
        "electric": {
            "water": 2.0,
            "electric": 0.5,
            "grass": 0.5,
            "ground": 0.0,
            "flying": 2.0,
            "dragon": 0.5,
        },
        "grass": {
            "fire": 0.5,
            "water": 2.0,
            "grass": 0.5,
            "poison": 0.5,
            "ground": 2.0,
            "flying": 0.5,
            "bug": 0.5,
            "rock": 2.0,
            "dragon": 0.5,
        },
        "ice": {
            # fire: 1x in Gen 1 (not 0.5x)
            "water": 0.5,
            "grass": 2.0,
            "ice": 0.5,
            "ground": 2.0,
            "flying": 2.0,
            "dragon": 2.0,
        },
        "fighting": {
            "normal": 2.0,
            "ice": 2.0,
            "poison": 0.5,
            "flying": 0.5,
            "psychic": 0.5,
            "bug": 0.5,
            "rock": 2.0,
            "ghost": 0.0,
        },
        "poison": {
            "grass": 2.0,
            "poison": 0.5,
            "ground": 0.5,
            "rock": 0.5,
            "ghost": 0.5,
            # bug: 2x in Gen 1 (becomes 0.5x in Gen 6+)
            "bug": 2.0,
        },
        "ground": {
            "fire": 2.0,
            "electric": 2.0,
            "grass": 0.5,
            "poison": 2.0,
            "flying": 0.0,
            "bug": 0.5,
            "rock": 2.0,
        },
        "flying": {
            "electric": 0.5,
            "grass": 2.0,
            "fighting": 2.0,
            "bug": 2.0,
            "rock": 0.5,
        },
        "psychic": {
            "fighting": 2.0,
            "poison": 2.0,
            "psychic": 0.5,
            # dark: N/A in Gen 1
        },
        "bug": {
            "fire": 0.5,
            "grass": 2.0,
            "fighting": 0.5,
            # poison: 2x in Gen 1
            "poison": 2.0,
            "flying": 0.5,
            "psychic": 2.0,
            # ghost: 2x in Gen 1 (becomes 0.5x in Gen 6+)
            "ghost": 2.0,
        },
        "rock": {
            "fire": 2.0,
            "ice": 2.0,
            "fighting": 0.5,
            "ground": 0.5,
            "flying": 2.0,
            "bug": 2.0,
        },
        "ghost": {
            "normal": 0.0,
            # psychic: 0x in Gen 1 (the famous bug -- should be 2x but was coded as 0x)
            "psychic": 0.0,
            "ghost": 2.0,
        },
        "dragon": {
            "dragon": 2.0,
        },
    }


class Gen2Rules(Gen1Rules):
    """
    Gen 2 rules.

    Changes from Gen 1:
    - Adds Steel and Dark types.
    - Fixes Ghost vs Psychic: now 2x (was bugged to 0x in Gen 1).
    - Steel is immune (0x) to Ghost and Dark (changed to 0.5x in Gen 6).
    - Ice vs Fire becomes 0.5x (was 1x in Gen 1).
    - Poison vs Bug becomes 0.5x (was 2x in Gen 1).
    - Bug vs Poison becomes 0.5x (was 2x in Gen 1).
    - Bug vs Ghost becomes 0.5x (was 2x in Gen 1).

    Stat formula: still Gen 1/2 formula (unchanged from Gen 1 to Gen 2).
    """

    # gen1_stat_formula inherited as True

    _chart: dict[str, dict[str, float]] = {
        "normal": {
            "rock": 0.5,
            "ghost": 0.0,
            "steel": 0.5,
        },
        "fire": {
            "fire": 0.5,
            "water": 0.5,
            "grass": 2.0,
            "ice": 2.0,
            "bug": 2.0,
            "rock": 0.5,
            "dragon": 0.5,
            "steel": 2.0,
        },
        "water": {
            "fire": 2.0,
            "water": 0.5,
            "grass": 0.5,
            "ground": 2.0,
            "rock": 2.0,
            "dragon": 0.5,
        },
        "electric": {
            "water": 2.0,
            "electric": 0.5,
            "grass": 0.5,
            "ground": 0.0,
            "flying": 2.0,
            "dragon": 0.5,
        },
        "grass": {
            "fire": 0.5,
            "water": 2.0,
            "grass": 0.5,
            "poison": 0.5,
            "ground": 2.0,
            "flying": 0.5,
            "bug": 0.5,
            "rock": 2.0,
            "dragon": 0.5,
            "steel": 0.5,
        },
        "ice": {
            "fire": 0.5,
            "water": 0.5,
            "grass": 2.0,
            "ice": 0.5,
            "ground": 2.0,
            "flying": 2.0,
            "dragon": 2.0,
            "steel": 0.5,
        },
        "fighting": {
            "normal": 2.0,
            "ice": 2.0,
            "poison": 0.5,
            "flying": 0.5,
            "psychic": 0.5,
            "bug": 0.5,
            "rock": 2.0,
            "ghost": 0.0,
            "dark": 2.0,
            "steel": 2.0,
        },
        "poison": {
            "grass": 2.0,
            "poison": 0.5,
            "ground": 0.5,
            "rock": 0.5,
            "ghost": 0.5,
            "bug": 0.5,
            "steel": 0.0,
        },
        "ground": {
            "fire": 2.0,
            "electric": 2.0,
            "grass": 0.5,
            "poison": 2.0,
            "flying": 0.0,
            "bug": 0.5,
            "rock": 2.0,
            "steel": 2.0,
        },
        "flying": {
            "electric": 0.5,
            "grass": 2.0,
            "fighting": 2.0,
            "bug": 2.0,
            "rock": 0.5,
            "steel": 0.5,
        },
        "psychic": {
            "fighting": 2.0,
            "poison": 2.0,
            "psychic": 0.5,
            "dark": 0.0,
            "steel": 0.5,
        },
        "bug": {
            "fire": 0.5,
            "grass": 2.0,
            "fighting": 0.5,
            "poison": 0.5,
            "flying": 0.5,
            "psychic": 2.0,
            "ghost": 0.5,
            "dark": 2.0,
            "steel": 0.5,
        },
        "rock": {
            "fire": 2.0,
            "ice": 2.0,
            "fighting": 0.5,
            "ground": 0.5,
            "flying": 2.0,
            "bug": 2.0,
            "steel": 0.5,
        },
        "ghost": {
            "normal": 0.0,
            "psychic": 2.0,
            "ghost": 2.0,
            "dark": 0.5,
            # steel: 0x in Gen 2-5 (immune; changed to 0.5x in Gen 6)
            "steel": 0.0,
        },
        "dragon": {
            "dragon": 2.0,
            "steel": 0.5,
        },
        "dark": {
            "fighting": 0.5,
            "psychic": 2.0,
            "ghost": 2.0,
            "dark": 0.5,
            # steel: 0x in Gen 2-5 (immune; changed to 0.5x in Gen 6)
            "steel": 0.0,
        },
        "steel": {
            "fire": 0.5,
            "water": 0.5,
            "electric": 0.5,
            "ice": 2.0,
            "rock": 2.0,
            "steel": 0.5,
        },
    }


class Gen3Rules(Gen2Rules):
    """
    Gen 3 rules.

    Changes from Gen 2:
    - Switches to Gen 3+ stat formula.

    Type chart is identical to Gen 2.
    """

    gen1_stat_formula = False


class Gen4Rules(Gen3Rules):
    """
    Gen 4 rules.

    No type chart or formula changes from Gen 3.
    Placeholder for future accuracy work.
    """


class Gen5Rules(Gen4Rules):
    """
    Gen 5 rules.

    No type chart or formula changes from Gen 4.
    Placeholder for future accuracy work.
    """


class Gen6Rules(Gen5Rules):
    """
    Gen 6 rules.

    Changes from Gen 5:
    - Adds Fairy type.
    - Steel loses its Ghost and Dark immunities (now 0.5x instead of 0x).

    Verified source: Bulbapedia Type/Type_chart -- "Generation VI onward" table.
    """

    _chart: dict[str, dict[str, float]] = {
        "normal": {
            "rock": 0.5,
            "ghost": 0.0,
            "steel": 0.5,
        },
        "fire": {
            "fire": 0.5,
            "water": 0.5,
            "grass": 2.0,
            "ice": 2.0,
            "bug": 2.0,
            "rock": 0.5,
            "dragon": 0.5,
            "steel": 2.0,
        },
        "water": {
            "fire": 2.0,
            "water": 0.5,
            "grass": 0.5,
            "ground": 2.0,
            "rock": 2.0,
            "dragon": 0.5,
        },
        "electric": {
            "water": 2.0,
            "electric": 0.5,
            "grass": 0.5,
            "ground": 0.0,
            "flying": 2.0,
            "dragon": 0.5,
        },
        "grass": {
            "fire": 0.5,
            "water": 2.0,
            "grass": 0.5,
            "poison": 0.5,
            "ground": 2.0,
            "flying": 0.5,
            "bug": 0.5,
            "rock": 2.0,
            "dragon": 0.5,
            "steel": 0.5,
        },
        "ice": {
            "fire": 0.5,
            "water": 0.5,
            "grass": 2.0,
            "ice": 0.5,
            "ground": 2.0,
            "flying": 2.0,
            "dragon": 2.0,
            "steel": 0.5,
        },
        "fighting": {
            "normal": 2.0,
            "ice": 2.0,
            "poison": 0.5,
            "flying": 0.5,
            "psychic": 0.5,
            "bug": 0.5,
            "rock": 2.0,
            "ghost": 0.0,
            "dark": 2.0,
            "steel": 2.0,
            "fairy": 0.5,
        },
        "poison": {
            "grass": 2.0,
            "poison": 0.5,
            "ground": 0.5,
            "rock": 0.5,
            "ghost": 0.5,
            "steel": 0.0,
            "fairy": 2.0,
        },
        "ground": {
            "fire": 2.0,
            "electric": 2.0,
            "grass": 0.5,
            "poison": 2.0,
            "flying": 0.0,
            "bug": 0.5,
            "rock": 2.0,
            "steel": 2.0,
        },
        "flying": {
            "electric": 0.5,
            "grass": 2.0,
            "fighting": 2.0,
            "bug": 2.0,
            "rock": 0.5,
            "steel": 0.5,
        },
        "psychic": {
            "fighting": 2.0,
            "poison": 2.0,
            "psychic": 0.5,
            "dark": 0.0,
            "steel": 0.5,
        },
        "bug": {
            "fire": 0.5,
            "grass": 2.0,
            "fighting": 0.5,
            "poison": 0.5,
            "flying": 0.5,
            "psychic": 2.0,
            "ghost": 0.5,
            "dark": 2.0,
            "steel": 0.5,
            "fairy": 0.5,
        },
        "rock": {
            "fire": 2.0,
            "ice": 2.0,
            "fighting": 0.5,
            "ground": 0.5,
            "flying": 2.0,
            "bug": 2.0,
            "steel": 0.5,
        },
        "ghost": {
            "normal": 0.0,
            "psychic": 2.0,
            "ghost": 2.0,
            "dark": 0.5,
            # steel: 0.5x in Gen 6+ (was immune in Gen 2-5)
            "steel": 0.5,
        },
        "dragon": {
            "dragon": 2.0,
            "steel": 0.5,
            "fairy": 0.0,
        },
        "dark": {
            "fighting": 0.5,
            "psychic": 2.0,
            "ghost": 2.0,
            "dark": 0.5,
            "fairy": 0.5,
            # steel: 0.5x in Gen 6+ (was immune in Gen 2-5)
            "steel": 0.5,
        },
        "steel": {
            "fire": 0.5,
            "water": 0.5,
            "electric": 0.5,
            "ice": 2.0,
            "rock": 2.0,
            "steel": 0.5,
            "fairy": 2.0,
        },
        "fairy": {
            "fire": 0.5,
            "fighting": 2.0,
            "poison": 0.5,
            "dragon": 2.0,
            "dark": 2.0,
            "steel": 0.5,
        },
    }


class Gen7Rules(Gen6Rules):
    """
    Gen 7 rules (Sun/Moon, Ultra Sun/Ultra Moon).

    Type chart: unchanged from Gen 6.
    Stat formula: unchanged from Gen 3+.

    No type chart or formula changes from Gen 6.
    Placeholder for future accuracy work (Z-moves, abilities, etc.).

    Verified source: Bulbapedia Type/Type_chart -- chart is "Generation VI onward".
    """


class Gen8Rules(Gen7Rules):
    """
    Gen 8 rules (Sword/Shield, Brilliant Diamond/Shining Pearl, Legends: Arceus).

    Type chart: unchanged from Gen 6.
    Stat formula: unchanged from Gen 3+.

    No type chart or formula changes from Gen 7.
    Placeholder for future accuracy work (Dynamax, abilities, etc.).

    Verified source: Bulbapedia Type/Type_chart -- chart is "Generation VI onward".
    """


class Gen9Rules(Gen8Rules):
    """
    Gen 9 rules (Scarlet/Violet).

    Type chart: unchanged from Gen 6.
    Stat formula: unchanged from Gen 3+.

    No type chart or formula changes from Gen 8.
    Placeholder for future accuracy work (Terastal, abilities, etc.).

    Verified source: Bulbapedia Type/Type_chart -- chart is "Generation VI onward".
    """


# Dispatch table: generation number -> rules object.
RULES_BY_GEN: dict[int, BattleRules] = {
    1: Gen1Rules(),
    2: Gen2Rules(),
    3: Gen3Rules(),
    4: Gen4Rules(),
    5: Gen5Rules(),
    6: Gen6Rules(),
    7: Gen7Rules(),
    8: Gen8Rules(),
    9: Gen9Rules(),
}
