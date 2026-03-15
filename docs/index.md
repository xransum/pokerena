# pokerena

A Pokemon battle tournament simulator. Runs millions of simulated battles to
determine the statistically strongest Pokemon at every competitive tier, then
compares results against Smogon's 25 years of community tier placements.

## What it does

- Fetches real Pokemon stats and moves from [PokeAPI](https://pokeapi.co) and
  tier assignments from [Pokemon Showdown](https://github.com/smogon/pokemon-showdown)
- Runs full round-robin tournaments within each Smogon tier (Ubers, OU, UU, RU, NU, PU)
- Runs adjacent-tier playoffs (PU champion vs NU champion, NU vs RU, etc.)
- Runs a grand final among all playoff winners
- Produces a Smogon delta report showing where simulation agrees or disagrees with official tier placements
- Tracks evolutionary line performance across tiers
- Supports all 9 generations with generation-accurate mechanics

## Installation

Requires Python 3.11+.

```
pip install pokerena
```

This registers the `pokerena` command on your PATH.

## Quick start

```bash
# Gen 1 tournament with default settings
pokerena

# One-off battle
pokerena battle pikachu mewtwo

# Search for high-BST Fire types in OU
pokerena search --type fire --tier ou --min-bst 500 --sort bst --desc

# Show cache info
pokerena db info
```

See the [CLI Reference](cli.md) for the full command documentation and the
[API Reference](api/models.md) for programmatic usage.
