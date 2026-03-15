# pokerena

[![CI](https://github.com/xransum/pokerena/actions/workflows/ci.yml/badge.svg)](https://github.com/xransum/pokerena/actions/workflows/ci.yml)
[![Codecov](https://codecov.io/gh/xransum/pokerena/branch/main/graph/badge.svg)](https://codecov.io/gh/xransum/pokerena)
[![PyPI](https://img.shields.io/pypi/v/pokerena.svg)](https://pypi.org/project/pokerena/)
[![Python Version](https://img.shields.io/pypi/pyversions/pokerena)](https://pypi.org/project/pokerena/)
[![Read the Docs](https://img.shields.io/readthedocs/pokerena/latest.svg?label=Read%20the%20Docs)](https://pokerena.readthedocs.io)
[![License](https://img.shields.io/pypi/l/pokerena)](https://github.com/xransum/pokerena/blob/main/LICENSE)

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
pip install -e .
```

This registers the `pokerena` command. Alternatively, `simulate.py` at the
project root is a thin shim that calls the same entry point without installing.

## Usage

### Run a tournament

```bash
# Gen 1, 20 battles per matchup (default)
pokerena

# Specific generation
pokerena --gen 2

# All generations 1-9 sequentially
pokerena --all-gens

# More battles for higher statistical accuracy
pokerena --battles 100

# Random IVs (0-15 per stat) instead of max (31)
pokerena --rand-ivs

# Random IVs, reproducible across runs
pokerena --rand-ivs --seed 42

# Force re-fetch all data from PokeAPI and Smogon (clears cache)
pokerena --fetch

# Show top 20 in console leaderboards (default: 10)
pokerena --top 20

# Control CPU workers for parallel battle processing
pokerena --workers 8

# Use Gen 1 stat formula instead of Gen 6
pokerena --gen1-mode

# Debug logging to stderr
pokerena --verbose
```

### One-off battle

Pit any two Pokemon against each other directly:

```bash
# Named battle
pokerena battle pikachu mewtwo

# Random matchup from the Gen 1 roster
pokerena battle --random

# Random matchup from Gen 3
pokerena battle --random --gen 3

# All standard flags also apply
pokerena battle pikachu mewtwo --rand-ivs --seed 7 --gen1-mode
```

Output includes the winner, turns taken, HP remaining, and a type advantage flag.

### Search and filter Pokemon

Browse the full roster with optional filters:

```bash
# Show all Gen 1 Pokemon
pokerena search --gen 1

# Substring name match
pokerena search char

# Filter by type, tier, and BST range
pokerena search --type fire --tier ou --min-bst 500

# Sort by BST descending, limit to top 10
pokerena search --sort bst --desc --limit 10

# All filters combined
pokerena search --gen 2 --type water --tier uu --min-bst 400 --max-bst 600 --sort bst --desc
```

Output is a table with columns: Name, Gen, Types, Tier, BST, HP, Atk, Def, SpA, SpD, Spe.

Available `--sort` fields: `name`, `bst`, `tier`, `gen`, `hp`, `attack`, `defense`,
`sp_atk`, `sp_def`, `speed`.

### Manage the cache

```bash
# Pre-populate the cache for a generation before running a tournament
pokerena db fetch --gen 1    # 151 Pokemon (Gen 1 roster)
pokerena db fetch --gen 9    # all 1025 Pokemon
pokerena db fetch --all-gens # every generation

# Force re-fetch even if cached files already exist
pokerena db fetch --gen 1 --force

# Show cache location and per-namespace file counts
pokerena db info

# Show per-generation coverage
pokerena db status

# Clear everything
pokerena db clear

# Clear only Smogon tier data (keeps PokeAPI data)
pokerena db clear smogon

# Clear only PokeAPI data
pokerena db clear pokeapi
```

**What `--gen N` means for the roster:** each generation covers a *cumulative*
national dex range starting from dex 1. It is not a filter for newly introduced
Pokemon -- it defines the full competitive roster for that era:

| `--gen` | Roster |
|---------|--------|
| 1 | dex 1-151 (151 Pokemon) |
| 2 | dex 1-251 (251 Pokemon) |
| 3 | dex 1-386 |
| 4 | dex 1-493 |
| 5 | dex 1-649 |
| 6 | dex 1-721 |
| 7 | dex 1-809 |
| 8 | dex 1-905 |
| 9 | dex 1-1025 (full roster) |

To simulate all Pokemon across all generations, use `--gen 9` or `--all-gens`.

## Output

Results are written to `results/gen{N}/` after each tournament run:

| File | Contents |
|------|----------|
| `tier_{name}_leaderboard.csv` | Full ranked leaderboard for each Smogon tier |
| `playoff_{lower}_{upper}.csv` | Result of each adjacent-tier playoff |
| `grand_final_leaderboard.csv` | Final rankings with source tier and Smogon tier |
| `grand_final_matrix.csv` | Head-to-head win-rate matrix for all finalists |
| `smogon_delta.csv` | Per-Pokemon sim rank vs Smogon placement (UNDERRATED / OVERRATED / CONFIRMED) |
| `evo_line_report.csv` | Evolutionary line performance across tiers |
| `upsets.csv` | Playoffs where the lower-tier champion won |
| `summary.csv` | One-line summary per phase |

## How it works

### Data pipeline

Pokemon stats, moves, types, and evolution lines are fetched from
[PokeAPI](https://pokeapi.co). Smogon tier assignments are parsed directly from
Pokemon Showdown's `formats-data.ts` source files on GitHub. All responses are
cached locally so the network is never hit during simulation once the cache is warm.

Cache is stored at `~/.cache/pokerena/` on Linux/macOS and
`%LOCALAPPDATA%\pokerena\Cache\` on Windows (via `platformdirs`), in two
namespaces:

```
~/.cache/pokerena/
  pokeapi/    -- one JSON file per Pokemon, move, species, and evolution chain
  smogon/     -- one JSON file per generation tier map
```

Cold-cache fetching is parallelized with 20 concurrent threads
(`ThreadPoolExecutor`). Requests to PokeAPI are retried up to 3 times on
transient failures (HTTP 429, 5xx, network errors) using a linear ramp with
random jitter:

| Retry | Base wait | + jitter | Approx range |
|-------|-----------|----------|--------------|
| 1 | 250 ms | 0-100 ms | 250-350 ms |
| 2 | 500 ms | 0-100 ms | 500-600 ms |
| 3 | 750 ms | 0-100 ms | 750-850 ms |

### Moveset selection

For each Pokemon, up to 30 learnable moves are fetched and scored. The final
moveset of 4 is chosen as:

- 3 highest-scoring damaging moves (scored by `power x STAB x accuracy`)
- 1 best status move (by accuracy), or a 4th damaging move if none exist
- Struggle as a guaranteed fallback if no moves load successfully

### Battle mechanics

Every battle is a Level 100, 1v1 simulation capped at 60 turns. The engine is
**fully deterministic** by default -- the same two Pokemon always produce the
same result, making outcomes a pure reflection of relative strength rather than
luck.

**Damage formula (Gen 6, default):**
```
floor((((2*L/5 + 2) * Power * Atk/Def) / 50) + 2) * STAB * TypeMult * AccWeight
```

- STAB: 1.5x when move type matches attacker type
- Type multiplier: full 18-type Gen 6 chart including immunities (0x, 0.25x, 0.5x, 1x, 2x, 4x)
- AccWeight: `accuracy / 100` applied as an expected-value multiplier (no binary miss roll)
- No random damage noise, no critical hits
- Burn halves physical attack damage
- Minimum 1 damage on non-immune hits

**Status conditions:**

| Status | Effect |
|--------|--------|
| Burn | 1/16 max HP per turn; physical damage halved |
| Poison | 1/8 max HP per turn |
| Paralysis | Speed halved (may change turn order); no random skip |
| Sleep | Blocks action for exactly 2 turns, then clears |
| Freeze | Blocks action for exactly 2 turns, then clears |

**Type immunities on status:** Fire cannot be burned, Poison/Steel cannot be
poisoned, Electric cannot be paralyzed, Ice cannot be frozen.

**AI move selection:** each turn the AI picks the damaging move with the
highest expected output (`power x STAB x type_effectiveness x acc_weight`).
An offensive status move (one that applies a debuff or inflicts a status
condition on the opponent) is preferred over attacking when the AI cannot
one-shot the opponent and the opponent has no status yet. Pure self-utility
moves like Recover are never chosen over attacking.

**Speed ties** (identical speed after paralysis halving) are broken by an RNG
coin flip -- the only non-deterministic element when `--rand-ivs` is not used.

**Gen 1 mode (`--gen1-mode`):** uses the Gen 1 stat formula
(`floor(((Base + IV) * 2 * Level) / 100) + 5`) instead of the Gen 3+ formula.

**Timeout:** if 60 turns expire with neither Pokemon fainted, the winner is
determined by highest HP percentage remaining.

### Tournament structure

**Phase 1 -- Tier round robins**

Full round robin within each Smogon tier (Ubers, OU, UU, RU, NU, PU), 20
battles per matchup by default. All matchups are distributed across CPU workers
via `ProcessPoolExecutor`. Ties at the top are broken by a 50-battle tiebreaker.

**Phase 2 -- Adjacent-tier playoffs**

Each tier champion faces the champion one tier above: PU vs NU, NU vs RU,
RU vs UU, UU vs OU, OU vs Ubers. 50 battles per playoff. An upset is flagged
when the lower-tier champion wins.

**Phase 3 -- Grand final**

All five playoff winners enter a full round robin, 100 battles per matchup,
parallelized across CPU workers. The Pokemon with the highest win rate among
finalists is the overall generation champion.

## Performance

Estimates at 20 battles per matchup on an i9 with 20 cores:

| Scope | Pokemon | Total battles | Approx time |
|-------|---------|---------------|-------------|
| Gen 1 | 151 | ~226K | ~15 sec |
| Gen 1-2 | 251 | ~630K | ~45 sec |
| Gen 1-3 | 386 | ~1.5M | ~2 min |
| All gens | 1,025 | ~10.5M | ~10-15 min |

Cold-cache data loading adds roughly 1-3 minutes for Gen 1 (151 Pokemon x ~33
API requests each) at 20 concurrent threads. Subsequent runs use the disk cache
and add negligible overhead.

## Project structure

```
pokerena/
  cli.py              -- argument parsing and command dispatch
  models.py           -- shared data models (Pokemon, Move, tier constants)
  data/
    cache.py          -- namespaced JSON disk cache (platformdirs)
    pokeapi.py        -- PokeAPI HTTP client with retry and caching
    smogon.py         -- Pokemon Showdown tier data parser
    loader.py         -- assembles Pokemon instances (concurrent fetching)
  engine/
    stats.py          -- Gen 1 and Gen 3+ stat formulas, IV generation
    types.py          -- Gen 6 18-type chart
    battle.py         -- single 1v1 battle simulation
  tournament/
    runner.py         -- round robins, playoffs, grand final
  report/
    writers.py        -- CSV output
    console.py        -- terminal output
simulate.py           -- convenience entry point (no install required)
results/              -- output CSVs per generation (gitignored)
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"
# or with uv
uv sync

# Run tests
uv run pytest

# Lint and format check
uv run nox -p 3.13 -s pre-commit

# Fast test feedback (no coverage)
uv run nox -p 3.13 -s tests
```

Coverage is enforced at 80% minimum. `cli.py`, `loader.py`, `pokeapi.py`,
`console.py`, `writers.py`, and `runner.py` are excluded from the coverage
requirement as integration/IO modules.

## License

MIT
