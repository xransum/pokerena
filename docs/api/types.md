# Type chart

Full 18-type Gen 6 type chart including all immunities.

The module-level `TYPE_CHART` singleton is imported by the battle engine and
models. Call `TYPE_CHART.multiplier(attacking_type, defender_types)` to get
the combined damage multiplier for a move.

::: pokerena.engine.types
