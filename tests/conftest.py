"""
Shared test fixtures for pokerena tests.
"""

import random

import pytest

from pokerena.models import Move, Pokemon


@pytest.fixture
def physical_move():
    """A standard physical Normal-type move (Tackle)."""
    return Move(
        name="tackle",
        type_="normal",
        category="physical",
        power=40,
        accuracy=100,
        pp=35,
    )


@pytest.fixture
def special_move():
    """A standard special Fire-type move (Flamethrower)."""
    return Move(
        name="flamethrower",
        type_="fire",
        category="special",
        power=90,
        accuracy=100,
        pp=15,
    )


@pytest.fixture
def status_move():
    """A status Electric-type move that inflicts paralysis (Thunder Wave)."""
    return Move(
        name="thunder-wave",
        type_="electric",
        category="status",
        power=0,
        accuracy=90,
        pp=20,
        status_effect="paralysis",
    )


@pytest.fixture
def always_hits_move():
    """Move with accuracy=0, meaning it always hits."""
    return Move(
        name="swift",
        type_="normal",
        category="special",
        power=60,
        accuracy=0,
        pp=20,
    )


def _make_mewtwo():
    """Create a Mewtwo Pokemon instance with a standard Ubers moveset."""
    return Pokemon(
        name="mewtwo",
        types=["psychic"],
        base_stats={
            "hp": 106,
            "attack": 110,
            "defense": 90,
            "sp_atk": 154,
            "sp_def": 90,
            "speed": 130,
        },
        moves=[
            Move("psychic", "psychic", "special", 90, 100, 10),
            Move("ice-beam", "ice", "special", 90, 100, 10),
            Move("thunderbolt", "electric", "special", 90, 100, 15),
            Move("recover", "normal", "status", 0, 0, 10),
        ],
        generation=1,
        smogon_tier="ubers",
        bst=680,
    )


def _make_charizard():
    """Create a Charizard Pokemon instance with a standard OU moveset."""
    return Pokemon(
        name="charizard",
        types=["fire", "flying"],
        base_stats={
            "hp": 78,
            "attack": 84,
            "defense": 78,
            "sp_atk": 109,
            "sp_def": 85,
            "speed": 100,
        },
        moves=[
            Move("flamethrower", "fire", "special", 90, 100, 15),
            Move("dragon-claw", "dragon", "physical", 80, 100, 15),
            Move("air-slash", "flying", "special", 75, 95, 15),
            Move("fire-blast", "fire", "special", 110, 85, 5),
        ],
        generation=1,
        smogon_tier="ou",
        bst=534,
    )


def _make_magikarp():
    """Create a Magikarp Pokemon instance with minimal moves."""
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
            Move("tackle", "normal", "physical", 40, 100, 35),
        ],
        generation=1,
        smogon_tier="pu",
        bst=200,
    )


def _make_steelix():
    """Steel/Ground -- useful for type immunity tests."""
    return Pokemon(
        name="steelix",
        types=["steel", "ground"],
        base_stats={
            "hp": 75,
            "attack": 85,
            "defense": 200,
            "sp_atk": 55,
            "sp_def": 65,
            "speed": 30,
        },
        moves=[
            Move("iron-tail", "steel", "physical", 100, 75, 15),
            Move("earthquake", "ground", "physical", 100, 100, 10),
            Move("rock-slide", "rock", "physical", 75, 90, 10),
            Move("crunch", "dark", "physical", 80, 100, 15),
        ],
        generation=2,
        smogon_tier="uu",
        bst=510,
    )


@pytest.fixture
def mewtwo():
    """Mewtwo fixture for battle tests."""
    return _make_mewtwo()


@pytest.fixture
def charizard():
    """Charizard fixture for battle tests."""
    return _make_charizard()


@pytest.fixture
def magikarp():
    """Magikarp fixture for battle tests."""
    return _make_magikarp()


@pytest.fixture
def steelix():
    """Steelix fixture for type immunity tests."""
    return _make_steelix()


@pytest.fixture
def seeded_rng():
    """A seeded Random instance for reproducible tests."""
    return random.Random(42)
