"""
Reporters -- write tournament results to CSV files under results/gen{N}/.
"""

from __future__ import annotations

import csv
import logging
import pathlib
from typing import Any

from pokerena.models import TIER_ORDER, TIER_LABELS
from pokerena.tournament.runner import (
    TierLeaderboard,
    MatchupRecord,
    PlayoffResult,
    GrandFinalResult,
    LeaderboardEntry,
)

log = logging.getLogger(__name__)

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_RESULTS_ROOT = _REPO_ROOT / "results"


def _out_dir(gen: int) -> pathlib.Path:
    d = _RESULTS_ROOT / f"gen{gen}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_csv(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        log.debug("No rows for %s -- skipping.", path.name)
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    log.debug("Wrote %d rows -> %s", len(rows), path)


# ---------------------------------------------------------------------------
# Tier leaderboards
# ---------------------------------------------------------------------------


def write_tier_leaderboard(lb: TierLeaderboard) -> None:
    out = _out_dir(lb.gen)
    path = out / f"tier_{lb.tier}_leaderboard.csv"
    rows = [
        {
            "rank": e.rank,
            "name": e.name,
            "tier": e.tier,
            "wins": e.wins,
            "losses": e.losses,
            "battles": e.battles,
            "win_rate": f"{e.win_rate:.4f}",
            "avg_hp_pct_when_winning": f"{e.avg_hp_pct:.4f}",
            "bst": e.bst,
            "types": e.types,
        }
        for e in lb.entries
    ]
    _write_csv(path, rows)


# ---------------------------------------------------------------------------
# Playoff results
# ---------------------------------------------------------------------------


def write_playoffs(gen: int, playoffs: list[PlayoffResult]) -> None:
    out = _out_dir(gen)
    for pr in playoffs:
        fname = f"playoff_{pr.lower_tier}_{pr.upper_tier}.csv"
        rows = [
            {
                "lower_tier": pr.lower_tier,
                "upper_tier": pr.upper_tier,
                "lower_champion": pr.lower_champion,
                "upper_champion": pr.upper_champion,
                "lower_wins": pr.lower_wins,
                "upper_wins": pr.upper_wins,
                "battles": pr.battles,
                "lower_win_rate": f"{pr.lower_win_rate:.4f}",
                "upset": pr.upset,
                "winner": pr.winner,
            }
        ]
        _write_csv(out / fname, rows)


# ---------------------------------------------------------------------------
# Grand final
# ---------------------------------------------------------------------------


def write_grand_final(gf: GrandFinalResult) -> None:
    out = _out_dir(gf.gen)

    # Leaderboard
    rows = [
        {
            "rank": e.rank,
            "name": e.name,
            "win_rate": f"{e.win_rate:.4f}",
            "source_tier": e.source_tier,
            "smogon_tier": e.smogon_tier,
        }
        for e in gf.entries
    ]
    _write_csv(out / "grand_final_leaderboard.csv", rows)

    # Win-rate matrix
    names = [e.name for e in gf.entries]
    matrix_rows = []
    for name_a in names:
        row: dict[str, Any] = {"pokemon": name_a}
        for name_b in names:
            if name_a == name_b:
                row[name_b] = "--"
            else:
                pct = gf.matchup_matrix.get(name_a, {}).get(name_b)
                row[name_b] = f"{pct:.2%}" if pct is not None else "N/A"
        matrix_rows.append(row)
    _write_csv(out / "grand_final_matrix.csv", matrix_rows)


# ---------------------------------------------------------------------------
# Smogon delta report
# ---------------------------------------------------------------------------


def write_smogon_delta(
    gen: int,
    tier_leaderboards: dict[str, TierLeaderboard],
) -> None:
    """
    Compare sim rank within tier vs Smogon tier placement.
    Flags Pokemon as UNDERRATED, OVERRATED, or CONFIRMED.
    """
    out = _out_dir(gen)

    # Build a cross-tier rank list
    all_entries: list[LeaderboardEntry] = []
    for tier in TIER_ORDER:
        lb = tier_leaderboards.get(tier)
        if lb:
            all_entries.extend(lb.entries)

    # Assign global sim rank
    all_entries.sort(
        key=lambda e: (
            TIER_ORDER.index(e.tier),  # tier order (pu=0, ubers=5)
            -e.win_rate,
        ),
        reverse=False,
    )
    # Reverse so ubers are ranked #1
    all_entries = list(reversed(all_entries))

    tier_rank = {tier: 0 for tier in TIER_ORDER}
    rows = []
    for i, e in enumerate(all_entries):
        tier_rank[e.tier] += 1
        rows.append(
            {
                "pokemon": e.name,
                "sim_rank_in_tier": e.rank,
                "sim_tier": e.tier,
                "win_rate": f"{e.win_rate:.4f}",
                "bst": e.bst,
                "types": e.types,
            }
        )
    _write_csv(out / "smogon_delta.csv", rows)


# ---------------------------------------------------------------------------
# Evolutionary line report
# ---------------------------------------------------------------------------


def write_evo_line_report(
    gen: int,
    tier_leaderboards: dict[str, TierLeaderboard],
    pokemon_by_tier: dict,
) -> None:
    """
    Report on evolutionary line performance across tiers.
    """
    out = _out_dir(gen)

    # Build name -> entry map
    entry_map: dict[str, LeaderboardEntry] = {}
    for tier, lb in tier_leaderboards.items():
        for e in lb.entries:
            entry_map[e.name] = e

    # Build evo line groups
    poke_map = {p.name: p for pokes in pokemon_by_tier.values() for p in pokes}
    seen_lines: set[tuple] = set()
    rows = []
    for poke in poke_map.values():
        line_key = tuple(poke.evo_line)
        if line_key in seen_lines:
            continue
        seen_lines.add(line_key)
        for stage, member in enumerate(poke.evo_line):
            if member in entry_map:
                e = entry_map[member]
                rows.append(
                    {
                        "evo_line": "/".join(poke.evo_line),
                        "stage": stage,
                        "name": member,
                        "tier": e.tier,
                        "win_rate": f"{e.win_rate:.4f}",
                        "rank_in_tier": e.rank,
                        "bst": e.bst,
                    }
                )

    rows.sort(key=lambda r: (r["evo_line"], r["stage"]))
    _write_csv(out / "evo_line_report.csv", rows)


# ---------------------------------------------------------------------------
# Upsets report
# ---------------------------------------------------------------------------


def write_upsets(gen: int, upsets: list[PlayoffResult]) -> None:
    out = _out_dir(gen)
    rows = [
        {
            "lower_tier": u.lower_tier,
            "upper_tier": u.upper_tier,
            "upset_winner": u.lower_champion,
            "defeated": u.upper_champion,
            "win_rate": f"{u.lower_win_rate:.4f}",
            "battles": u.battles,
        }
        for u in upsets
    ]
    _write_csv(out / "upsets.csv", rows)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def write_summary(gen: int, results: dict) -> None:
    out = _out_dir(gen)
    rows = []

    for tier in TIER_ORDER:
        lb: TierLeaderboard | None = results["tier_leaderboards"].get(tier)
        if lb and lb.champion:
            rows.append(
                {
                    "phase": "tier_tournament",
                    "tier": tier,
                    "champion": lb.champion,
                    "champion_win_rate": f"{lb.champion_win_rate:.4f}",
                    "participants": len(lb.entries),
                }
            )

    for pr in results.get("playoffs", []):
        rows.append(
            {
                "phase": "playoff",
                "tier": f"{pr.lower_tier}_vs_{pr.upper_tier}",
                "champion": pr.winner,
                "champion_win_rate": f"{pr.lower_win_rate:.4f}"
                if pr.upset
                else f"{1 - pr.lower_win_rate:.4f}",
                "participants": 2,
            }
        )

    gf: GrandFinalResult | None = results.get("grand_final")
    if gf and gf.champion:
        rows.append(
            {
                "phase": "grand_final",
                "tier": "all",
                "champion": gf.champion,
                "champion_win_rate": f"{gf.entries[0].win_rate:.4f}"
                if gf.entries
                else "0",
                "participants": len(gf.entries),
            }
        )

    _write_csv(out / "summary.csv", rows)


# ---------------------------------------------------------------------------
# Write all results for a generation
# ---------------------------------------------------------------------------


def write_all(gen: int, results: dict, pokemon_by_tier: dict) -> None:
    """Write every output file for a completed generation tournament."""
    tier_leaderboards = results.get("tier_leaderboards", {})

    for tier, lb in tier_leaderboards.items():
        write_tier_leaderboard(lb)

    write_playoffs(gen, results.get("playoffs", []))

    gf = results.get("grand_final")
    if gf:
        write_grand_final(gf)

    write_smogon_delta(gen, tier_leaderboards)
    write_evo_line_report(gen, tier_leaderboards, pokemon_by_tier)
    write_upsets(gen, results.get("upsets", []))
    write_summary(gen, results)

    log.info("Results written to results/gen%d/", gen)
