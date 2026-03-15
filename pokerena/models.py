"""
Shared data models used across the entire simulator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pokerena.engine.types import TypeChart


TIERS = ["ubers", "ou", "uu", "ru", "nu", "pu"]

# Ordered from weakest to strongest for playoff chain
TIER_ORDER = ["pu", "nu", "ru", "uu", "ou", "ubers"]

TIER_LABELS = {
    "ubers": "Ubers",
    "ou": "OU",
    "uu": "UU",
    "ru": "RU",
    "nu": "NU",
    "pu": "PU",
}


@dataclass
class Move:
    name: str
    type_: str  # e.g. "fire"
    category: str  # "physical", "special", "status"
    power: int  # 0 for status moves
    accuracy: int  # 0-100; 0 means always hits
    pp: int
    # Status effect this move may inflict, e.g. "burn", "paralysis", None
    status_effect: str | None = None
    # Stat stage changes: dict mapping stat name to stage delta, e.g. {"attack": -1}
    stat_changes: dict = field(default_factory=dict)

    def score(
        self, user_types: list[str], defender_types: list[str], type_chart: TypeChart
    ) -> float:  # noqa: F821
        """Scoring heuristic used by the AI to pick moves."""
        if self.category == "status":
            return 0.0
        stab = 1.5 if self.type_ in user_types else 1.0
        effectiveness = type_chart.multiplier(self.type_, defender_types)
        acc = (self.accuracy / 100.0) if self.accuracy > 0 else 1.0
        return self.power * stab * effectiveness * acc


@dataclass
class Pokemon:
    name: str
    types: list[str]  # 1 or 2 type strings, lower-case
    base_stats: dict  # {"hp": int, "attack": int, ...}
    moves: list[Move]  # exactly 4 after moveset selection
    generation: int
    smogon_tier: str  # lower-case key into TIERS
    bst: int
    # Evolutionary line info
    evo_line: list[str] = field(default_factory=list)  # names, stage 0 first
    evo_stage: int = 0
    # Runtime battle state -- reset before each battle
    current_hp: int = 0
    max_hp: int = 0
    stats: dict = field(default_factory=dict)  # computed battle stats
    status: str | None = None  # burn/paralysis/poison/sleep/freeze
    status_counter: int = 0  # turns remaining for sleep/freeze
    stat_stages: dict = field(default_factory=dict)  # {"attack": 0, ...}

    def __post_init__(self) -> None:
        self.bst = sum(self.base_stats.values())

    def is_fainted(self) -> bool:
        return self.current_hp <= 0

    def stage_multiplier(self, stat: str) -> float:
        stage = self.stat_stages.get(stat, 0)
        if stage >= 0:
            return (2 + stage) / 2.0
        return 2.0 / (2 - stage)
