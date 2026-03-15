# CLI Reference

The `pokerena` command is the main entry point. It has four modes of operation:

- No subcommand -- run a tournament simulation
- `battle` -- run a single 1v1 battle
- `search` -- browse and filter the Pokemon roster
- `cache` -- inspect or clear the local data cache

---

## `pokerena` -- run a tournament

```
pokerena [options]
```

Runs the full three-phase tournament for one or all generations and writes
results to `results/gen{N}/`.

| Flag | Default | Description |
|------|---------|-------------|
| `--gen N` | `1` | Generation to simulate (1-9). |
| `--all-gens` | off | Run all generations 1-9 sequentially. |
| `--battles N` | `20` | Battles per matchup in Phase 1 tier round robins. |
| `--rand-ivs` | off | Use random IVs (0-15) instead of max IVs (31). |
| `--seed N` | none | Random seed for reproducibility. Use with `--rand-ivs`. |
| `--fetch` | off | Force re-download of all PokeAPI and Smogon data (clears cache). |
| `--top N` | `10` | Number of entries shown in console leaderboards. |
| `--workers N` | CPU count | Number of parallel CPU workers for battle processing. |
| `--gen1-mode` | off | Use Gen 1 stat formula instead of the Gen 3+ default. |
| `-v / --verbose` | off | Enable debug logging to stderr. |

### Examples

```bash
# Gen 1, defaults
pokerena

# Gen 3, 50 battles per matchup, reproducible random IVs
pokerena --gen 3 --battles 50 --rand-ivs --seed 42

# All generations, forcing a fresh data download
pokerena --all-gens --fetch

# Show top 20, use 4 workers
pokerena --top 20 --workers 4
```

---

## `pokerena battle` -- single battle

```
pokerena battle <NAME> <NAME> [options]
pokerena battle --random [options]
```

Runs one battle and prints the winner, turns taken, HP remaining, and a
type advantage flag.

| Argument / Flag | Default | Description |
|-----------------|---------|-------------|
| `NAME NAME` | -- | Names of the two Pokemon to battle (e.g. `pikachu mewtwo`). |
| `--random` | off | Pick two Pokemon at random from the loaded roster. |
| `--gen N` | `1` | Generation to draw from when using `--random`. |
| `--gen1-mode` | off | Use Gen 1 stat formula. |
| `--rand-ivs` | off | Use random IVs instead of max IVs. |
| `--seed N` | none | Random seed for reproducibility. |
| `-v / --verbose` | off | Enable debug logging. |

### Examples

```bash
# Named battle
pokerena battle pikachu mewtwo

# Random matchup from Gen 2
pokerena battle --random --gen 2

# Reproducible random IVs
pokerena battle pikachu charizard --rand-ivs --seed 7
```

### Output

```
  Pikachu [Electric]  BST 320  PU
    vs
  Mewtwo [Psychic]  BST 680  Ubers

  Winner: Mewtwo
  Loser:  Pikachu
  Turns:  3  (faint in turn 3)
  Winner HP remaining: 341/416 (82.0%)
  (winner had a type advantage)
```

---

## `pokerena search` -- browse the roster

```
pokerena search [NAME] [options]
```

Loads one or all generation rosters, applies filters, and prints a table with
columns: Name, Gen, Types, Tier, BST, HP, Atk, Def, SpA, SpD, Spe.

| Argument / Flag | Default | Description |
|-----------------|---------|-------------|
| `NAME` | none | Substring match on Pokemon name (case-insensitive). |
| `--gen N` | all | Filter to a specific generation (1-9). |
| `--type TYPE` | none | Filter by type (e.g. `fire`, `water`). Matches either type slot. |
| `--tier TIER` | none | Filter by Smogon tier (`ubers`, `ou`, `uu`, `ru`, `nu`, `pu`). |
| `--min-bst N` | none | Only show Pokemon with BST >= N. |
| `--max-bst N` | none | Only show Pokemon with BST <= N. |
| `--sort FIELD` | `name` | Sort by field. Choices: `name`, `bst`, `tier`, `gen`, `hp`, `attack`, `defense`, `sp_atk`, `sp_def`, `speed`. |
| `--desc` | off | Reverse sort order (descending). |
| `--limit N` | none | Cap results at N rows. |

### Examples

```bash
# All Gen 1 Pokemon sorted by BST
pokerena search --gen 1 --sort bst --desc

# Fire types with BST over 500
pokerena search --type fire --min-bst 500

# OU-tier Pokemon, top 10 by BST
pokerena search --tier ou --sort bst --desc --limit 10

# Name substring match
pokerena search char --gen 1
```

---

## `pokerena cache` -- manage the cache

All fetched data is cached in `~/.cache/pokerena/` (Linux/macOS) or
`%LOCALAPPDATA%\pokerena\Cache\` (Windows).

### `pokerena cache info`

Prints the cache root path and per-namespace file counts.

```bash
pokerena cache info
# Cache location: /home/user/.cache/pokerena
#   pokeapi: 4821 files
#   smogon: 9 files
```

### `pokerena cache clear [NAMESPACE]`

Deletes cached files. Omit the namespace argument to clear everything.

```bash
# Clear everything
pokerena cache clear

# Clear only Smogon tier data (keeps PokeAPI data)
pokerena cache clear smogon

# Clear only PokeAPI data
pokerena cache clear pokeapi
```
