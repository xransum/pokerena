# pokerena

A Pokemon battle tournament simulator. Runs millions of simulated battles to
determine the statistically strongest Pokemon at every competitive tier, then
compares results against Smogon's 25 years of community tier placements.

---

## What it does

- Runs full round-robin tournaments within each Smogon tier (Ubers, OU, UU, RU, NU, PU)
- Runs adjacent-tier playoffs (PU champion vs NU champion, NU vs RU, etc.)
- Runs a grand final among all playoff winners
- Produces a Smogon delta report showing where the simulation agrees or disagrees with official tier placements
- Tracks evolutionary line performance across tiers
- Supports all 9 generations with generation-accurate mechanics

---

## Setup

```
pip install -e .
```

Or without installing:

```
pip install requests tqdm
```

---

## Usage

```bash
# Gen 1 only, 20 battles/matchup, max IVs (default)
python simulate.py

# Specific generation
python simulate.py --gen 2

# All available generations sequentially
python simulate.py --all-gens

# More battles for higher statistical accuracy
python simulate.py --battles 100

# Random IVs (0-15 per stat)
python simulate.py --rand-ivs

# Random IVs, reproducible
python simulate.py --rand-ivs --seed 42

# Force re-fetch data from PokeAPI and Smogon
python simulate.py --fetch

# Show top N in console leaderboards
python simulate.py --top 20

# Control CPU workers
python simulate.py --workers 8

# Use Gen 1 stat formula
python simulate.py --gen1-mode

# Debug logging
python simulate.py --verbose
```

---

## Output

Results are written to `results/gen{N}/` after each run:

| File | Contents |
|------|----------|
| `tier_{name}_leaderboard.csv` | Full ranked leaderboard for each tier |
| `playoff_{lower}_{upper}.csv` | Playoff result between adjacent tier champions |
| `grand_final_leaderboard.csv` | Grand final rankings |
| `grand_final_matrix.csv` | Head-to-head win rate matrix |
| `smogon_delta.csv` | Where simulation ranking diverges from Smogon placement |
| `evo_line_report.csv` | Evolutionary line performance across tiers |
| `upsets.csv` | Playoffs where the lower-tier champion won |
| `summary.csv` | One-line summary per phase |

---

## How it works

### Data

Pokemon stats and moves are fetched from [PokeAPI](https://pokeapi.co) and
cached locally under `cache/pokeapi/`. Smogon tier assignments are fetched
from the [smogon/data](https://github.com/smogon/data) repository and cached
under `cache/smogon/`. The network is never hit during simulation.

### Battle mechanics

- Level 100, 1v1, capped at 60 turns
- Gen 6 damage formula (default), switchable to Gen 1 with `--gen1-mode`
- Full 18-type Gen 6 type chart including immunities
- STAB, critical hits (1/24 chance, 1.5x), accuracy rolls
- All status conditions: burn, paralysis, poison, sleep, freeze
- Stat stage tracking (+/- 6 stages)
- Strategic AI: uses status moves 25% of the time when available, otherwise
  picks highest-scoring damaging move with small random noise

### Tournament structure

**Phase 1** -- full round robin within each Smogon tier, 20 battles per matchup
by default. Ties broken by a 50-battle tiebreaker.

**Phase 2** -- adjacent tier playoffs. Each tier champion faces the champion
one tier up. 50 battles per playoff.

**Phase 3** -- grand final. All five playoff winners in a full round robin,
100 battles per matchup.

---

## Compute estimates (20 battles/matchup, i9 20 cores)

| Scope | Pokemon | Total battles | Time |
|-------|---------|--------------|------|
| Gen 1 | 151 | ~226K | ~15 sec |
| Gen 1-2 | 251 | ~630K | ~45 sec |
| Gen 1-3 | 386 | ~1.5M | ~2 min |
| All gens | 1,025 | ~10.5M | ~10-15 min |

---

## Project structure

```
pokerena/
  data/
    cache.py        -- local disk cache (JSON)
    pokeapi.py      -- PokeAPI client
    smogon.py       -- Smogon tier loader
    loader.py       -- assembles Pokemon model instances
  engine/
    stats.py        -- stat formula, IV handling
    types.py        -- Gen 6 type chart
    battle.py       -- single battle simulation
  tournament/
    runner.py       -- round robins, playoffs, grand final
  report/
    writers.py      -- CSV output
    console.py      -- terminal output
  models.py         -- shared data models (Pokemon, Move)
  cli.py            -- argument parsing and orchestration
simulate.py         -- convenience entry point
cache/              -- cached API responses (gitignored)
results/            -- output CSVs (gitignored)
```

---

## License

MIT
