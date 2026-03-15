# CSV writers

Writes all tournament results to `results/gen{N}/` as CSV files.

| File | Contents |
|------|----------|
| `tier_{name}_leaderboard.csv` | Full ranked leaderboard per Smogon tier |
| `playoff_{lower}_{upper}.csv` | Adjacent-tier playoff result |
| `grand_final_leaderboard.csv` | Final rankings with source and Smogon tier |
| `grand_final_matrix.csv` | Head-to-head win-rate matrix for finalists |
| `smogon_delta.csv` | Per-Pokemon sim rank vs Smogon placement |
| `evo_line_report.csv` | Evolutionary line performance across tiers |
| `upsets.csv` | Playoffs where the lower-tier champion won |
| `summary.csv` | One-line summary per phase |

::: pokerena.report.writers
