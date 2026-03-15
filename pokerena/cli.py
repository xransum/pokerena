"""
CLI entry point -- simulate.py equivalent.

Usage:
  python -m pokerena [options]
  pokerena [options]          (if installed via pip)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import defaultdict

from pokerena.data.loader import load_all
from pokerena.models import TIER_ORDER
from pokerena.report import console as con
from pokerena.report import writers
from pokerena.tournament.runner import run_full_tournament


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pokerena",
        description="Pokemon battle tournament simulator.",
    )
    p.add_argument(
        "--gen",
        type=int,
        default=1,
        metavar="N",
        help="Generation to simulate (1-9). Default: 1",
    )
    p.add_argument(
        "--all-gens",
        action="store_true",
        help="Run all available generations sequentially.",
    )
    p.add_argument(
        "--battles",
        type=int,
        default=20,
        metavar="N",
        help="Battles per matchup in Phase 1 (tier round robins). Default: 20",
    )
    p.add_argument(
        "--rand-ivs",
        action="store_true",
        help="Use random IVs (0-15) instead of max IVs.",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="N",
        help="Random seed for reproducibility. Use with --rand-ivs.",
    )
    p.add_argument(
        "--fetch",
        action="store_true",
        help="Force re-fetch of PokeAPI and Smogon data (clears cache).",
    )
    p.add_argument(
        "--top",
        type=int,
        default=10,
        metavar="N",
        help="Number of entries to show in console leaderboards. Default: 10",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=None,
        metavar="N",
        help="Number of CPU workers for parallel battles. Default: CPU count.",
    )
    p.add_argument(
        "--gen1-mode",
        action="store_true",
        help="Use Gen 1 stat formula (instead of Gen 3+ default).",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    return p


def _run_gen(
    gen: int,
    args: argparse.Namespace,
    workers: int,
) -> None:
    # Load Pokemon
    pokemon = load_all(gen, force_fetch=args.fetch)
    if not pokemon:
        print(f"No Pokemon loaded for Gen {gen}. Run with --fetch to download data.")
        return

    # Group by tier
    pokemon_by_tier: dict[str, list] = defaultdict(list)
    for p in pokemon:
        pokemon_by_tier[p.smogon_tier].append(p)

    # Estimate total battles for Phase 1
    total_battles = sum(
        len(pokes) * (len(pokes) - 1) // 2 * args.battles
        for pokes in pokemon_by_tier.values()
        if len(pokes) >= 2
    )
    # Phase 2 + 3 approximations
    total_battles += 5 * 50 + 10 * 100

    con.print_header(
        gen=gen,
        total_pokemon=len(pokemon),
        battles_per_matchup=args.battles,
        total_battles=total_battles,
        workers=workers,
    )

    con.print_phase1_header()

    results = run_full_tournament(
        gen=gen,
        pokemon_by_tier=dict(pokemon_by_tier),
        n_battles_phase1=args.battles,
        n_battles_phase2=50,
        n_battles_phase3=100,
        rand_ivs=args.rand_ivs,
        seed=args.seed,
        workers=workers,
        gen1_mode=args.gen1_mode,
    )

    # Print Phase 1 results
    for tier in TIER_ORDER:
        lb = results["tier_leaderboards"].get(tier)
        if lb and lb.champion:
            con.print_tier_result(
                tier=tier,
                champion=lb.champion,
                win_rate=lb.champion_win_rate,
                participants=len(lb.entries),
            )

    # Print Phase 2 results
    con.print_phase2_header()
    for pr in results.get("playoffs", []):
        con.print_playoff_result(pr)

    # Print Phase 3 results
    gf = results.get("grand_final")
    if gf:
        con.print_phase3_header(100)
        con.print_grand_final(gf, top=args.top)

    # Write CSVs
    writers.write_all(gen=gen, results=results, pokemon_by_tier=dict(pokemon_by_tier))


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    workers = args.workers or os.cpu_count() or 4

    if args.all_gens:
        for gen in range(1, 10):
            _run_gen(gen, args, workers)
    else:
        _run_gen(args.gen, args, workers)


if __name__ == "__main__":
    main()
