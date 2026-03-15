"""
CLI entry point -- simulate.py equivalent.

Usage:
  pokerena [options]                run a tournament simulation
  pokerena battle <name-a> <name-b> run a single battle between two named Pokemon
  pokerena battle --random          pick two random Pokemon and battle them
  pokerena cache info               show cached namespaces and file counts
  pokerena cache clear              delete all cached data
  pokerena cache clear smogon       delete only the smogon namespace
  pokerena search                   list and filter Pokemon by name/type/tier/gen/BST
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import defaultdict
from typing import TYPE_CHECKING

from pokerena.data import cache as disk_cache
from pokerena.data.loader import load_all

if TYPE_CHECKING:
    from pokerena.models import Pokemon
from pokerena.models import TIER_ORDER, TIERS
from pokerena.report import console as con
from pokerena.report import writers
from pokerena.tournament.runner import run_full_tournament


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    p = argparse.ArgumentParser(
        prog="pokerena",
        description="Pokemon battle tournament simulator.",
    )

    sub = p.add_subparsers(dest="command", metavar="command")

    # -- battle sub-command
    battle_p = sub.add_parser(
        "battle",
        help="Run a single battle and print the result.",
    )
    battle_p.add_argument(
        "pokemon",
        nargs="*",
        metavar="NAME",
        help="Names of the two Pokemon to battle (e.g. pikachu mewtwo).",
    )
    battle_p.add_argument(
        "--random",
        action="store_true",
        help="Pick two Pokemon at random instead of specifying names.",
    )
    battle_p.add_argument(
        "--gen",
        type=int,
        default=1,
        metavar="N",
        help="Generation to draw Pokemon from when using --random. Default: 1",
    )
    battle_p.add_argument(
        "--gen1-mode",
        action="store_true",
        help="Use Gen 1 stat formula.",
    )
    battle_p.add_argument(
        "--rand-ivs",
        action="store_true",
        help="Use random IVs instead of max IVs.",
    )
    battle_p.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="N",
        help="Random seed for reproducibility.",
    )
    battle_p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging.",
    )

    # -- cache sub-command
    cache_p = sub.add_parser("cache", help="Manage the local data cache.")
    cache_sub = cache_p.add_subparsers(dest="cache_action", metavar="action")

    cache_sub.add_parser("info", help="Show cached namespaces and file counts.")

    clear_p = cache_sub.add_parser("clear", help="Delete cached files.")
    clear_p.add_argument(
        "namespace",
        nargs="?",
        default=None,
        metavar="NAMESPACE",
        help="Namespace to clear (e.g. smogon, pokeapi). Omit to clear everything.",
    )

    # -- search sub-command
    search_p = sub.add_parser(
        "search",
        help="List and filter Pokemon by name, type, tier, gen, or BST.",
    )
    search_p.add_argument(
        "name",
        nargs="?",
        default=None,
        metavar="NAME",
        help="Substring to match against Pokemon names (case-insensitive).",
    )
    search_p.add_argument(
        "--gen",
        type=int,
        default=None,
        metavar="N",
        help="Filter to a specific generation (1-9). Omit to search all gens.",
    )
    search_p.add_argument(
        "--type",
        dest="type_filter",
        default=None,
        metavar="TYPE",
        help="Filter by type (e.g. fire, water, grass). Matches either type slot.",
    )
    search_p.add_argument(
        "--tier",
        default=None,
        metavar="TIER",
        help=f"Filter by Smogon tier ({', '.join(TIERS)}).",
    )
    search_p.add_argument(
        "--min-bst",
        type=int,
        default=None,
        metavar="N",
        help="Only show Pokemon with BST >= N.",
    )
    search_p.add_argument(
        "--max-bst",
        type=int,
        default=None,
        metavar="N",
        help="Only show Pokemon with BST <= N.",
    )
    search_p.add_argument(
        "--sort",
        default="name",
        choices=[
            "name",
            "bst",
            "tier",
            "gen",
            "hp",
            "attack",
            "defense",
            "sp_atk",
            "sp_def",
            "speed",
        ],
        metavar="FIELD",
        help=(
            "Sort results by field. Choices: name, bst, tier, gen, "
            "hp, attack, defense, sp_atk, sp_def, speed. Default: name"
        ),
    )
    search_p.add_argument(
        "--desc",
        action="store_true",
        help="Reverse the sort order (descending).",
    )
    search_p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of results to show.",
    )

    # -- simulate options (the default command when none is given)
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


def _cmd_cache_info() -> None:
    """Print cached namespaces and their file counts."""
    sizes = disk_cache.cache_size()
    root = disk_cache._CACHE_ROOT
    if not sizes:
        print(f"Cache is empty ({root})")
        return
    print(f"Cache location: {root}")
    for ns, count in sizes.items():
        print(f"  {ns}: {count} file{'s' if count != 1 else ''}")


def _cmd_cache_clear(namespace: str | None) -> None:
    """Delete cached files, optionally scoped to a single namespace."""
    count = disk_cache.clear(namespace)
    scope = namespace if namespace else "all namespaces"
    print(f"Cleared {count} file{'s' if count != 1 else ''} from {scope}.")


def _load_one(name: str, gen: int) -> Pokemon:
    """Load a single Pokemon by name using the same pipeline as load_all."""
    from pokerena.data import pokeapi, smogon
    from pokerena.data.loader import _select_moveset
    from pokerena.models import Pokemon

    tier_map = smogon.load_tiers(gen)
    pdata = pokeapi.fetch_pokemon(name.lower())
    base_stats = pokeapi.parse_base_stats(pdata)
    types = pokeapi.parse_types(pdata)
    move_names = pokeapi.get_candidate_move_names(pdata)
    generation = pokeapi.get_generation_number(pdata)
    tier = smogon.assign_tier(name.lower(), tier_map)
    moves = _select_moveset(move_names, types)
    bst = sum(base_stats.values())
    return Pokemon(
        name=name.lower(),
        types=types,
        base_stats=base_stats,
        moves=moves,
        generation=generation,
        smogon_tier=tier,
        bst=bst,
    )


def _cmd_battle(args: argparse.Namespace) -> None:
    """Run a single battle and print a human-readable result."""
    import random as _random

    from pokerena.engine.battle import run_battle
    from pokerena.models import TIER_LABELS

    rng = _random.Random(args.seed)

    if args.random:
        from pokerena.data.loader import load_all

        print(f"Loading Gen {args.gen} roster...")
        roster = load_all(args.gen)
        if len(roster) < 2:
            print("Not enough Pokemon loaded. Run with --fetch first.")
            return
        poke_a, poke_b = rng.sample(roster, 2)
    elif len(args.pokemon) == 2:
        name_a, name_b = args.pokemon
        print(f"Loading {name_a} and {name_b}...")
        try:
            poke_a = _load_one(name_a, args.gen)
            poke_b = _load_one(name_b, args.gen)
        except Exception as exc:
            print(f"Failed to load Pokemon: {exc}")
            return
    else:
        print("Provide two Pokemon names  or use --random.")
        print("  pokerena battle pikachu mewtwo")
        print("  pokerena battle --random --gen 1")
        return

    tier_a = TIER_LABELS.get(poke_a.smogon_tier, poke_a.smogon_tier.upper())
    tier_b = TIER_LABELS.get(poke_b.smogon_tier, poke_b.smogon_tier.upper())

    types_a = "/".join(t.capitalize() for t in poke_a.types)
    types_b = "/".join(t.capitalize() for t in poke_b.types)
    print()
    print(f"  {poke_a.name.capitalize()} [{types_a}]  BST {poke_a.bst}  {tier_a}")
    print("    vs")
    print(f"  {poke_b.name.capitalize()} [{types_b}]  BST {poke_b.bst}  {tier_b}")
    print()

    result = run_battle(
        poke_a,
        poke_b,
        rand_ivs=args.rand_ivs,
        rng=rng,
        gen1_mode=args.gen1_mode,
    )

    loser = poke_b.name if result.winner == poke_a.name else poke_a.name
    resolved = "timeout (HP%)" if result.timeout else f"faint in turn {result.turns}"
    hp_pct = f"{result.winner_hp_pct * 100:.1f}%"

    print(f"  Winner: {result.winner.capitalize()}")
    print(f"  Loser:  {loser.capitalize()}")
    print(f"  Turns:  {result.turns}  ({resolved})")
    print(f"  Winner HP remaining: {result.winner_hp_remaining}/{result.winner_hp_max} ({hp_pct})")
    if result.attacker_had_advantage:
        print("  (winner had a type advantage)")
    print()


def _cmd_search(args: argparse.Namespace) -> None:
    """Load one or all generation rosters and print a filtered, sorted table."""
    from pokerena.models import TIER_LABELS, TIER_ORDER

    # Normalise filter inputs
    name_q = args.name.lower().strip() if args.name else None
    type_q = args.type_filter.lower().strip() if args.type_filter else None
    tier_q = args.tier.lower().strip() if args.tier else None

    # Validate tier filter early so the user gets a clear message
    if tier_q and tier_q not in TIERS:
        valid = ", ".join(TIERS)
        print(f"Unknown tier '{tier_q}'. Valid tiers: {valid}")
        return

    # Determine which gens to load
    gens = [args.gen] if args.gen else list(range(1, 10))

    # Load rosters; deduplicate by name (higher gens re-include lower-gen Pokemon)
    seen: set[str] = set()
    roster: list = []
    for gen in gens:
        print(f"Loading Gen {gen}...")
        for p in load_all(gen):
            if p.name not in seen:
                seen.add(p.name)
                roster.append(p)

    if not roster:
        print("No Pokemon loaded.")
        return

    # Apply filters
    results = roster
    if name_q:
        results = [p for p in results if name_q in p.name]
    if type_q:
        results = [p for p in results if type_q in p.types]
    if tier_q:
        results = [p for p in results if p.smogon_tier == tier_q]
    if args.min_bst is not None:
        results = [p for p in results if p.bst >= args.min_bst]
    if args.max_bst is not None:
        results = [p for p in results if p.bst <= args.max_bst]

    if not results:
        print("No Pokemon matched your filters.")
        return

    # Sort
    stat_fields = {"hp", "attack", "defense", "sp_atk", "sp_def", "speed"}
    sort_key = args.sort
    tier_rank = {t: i for i, t in enumerate(TIER_ORDER)}  # pu=0 ... ubers=5

    def _sort_key(p):
        if sort_key == "name":
            return p.name
        if sort_key == "bst":
            return p.bst
        if sort_key == "tier":
            return tier_rank.get(p.smogon_tier, -1)
        if sort_key == "gen":
            return p.generation
        if sort_key in stat_fields:
            return p.base_stats.get(sort_key, 0)
        return p.name

    results.sort(key=_sort_key, reverse=args.desc)

    if args.limit:
        results = results[: args.limit]

    # Render table
    # Columns: Name | Gen | Types | Tier | BST | HP | Atk | Def | SpA | SpD | Spe
    col_headers = ["Name", "Gen", "Types", "Tier", "BST", "HP", "Atk", "Def", "SpA", "SpD", "Spe"]
    rows = []
    for p in results:
        tier_label = TIER_LABELS.get(p.smogon_tier, p.smogon_tier.upper())
        types_str = "/".join(t.capitalize() for t in p.types)
        bs = p.base_stats
        rows.append(
            [
                p.name.capitalize(),
                str(p.generation),
                types_str,
                tier_label,
                str(p.bst),
                str(bs.get("hp", 0)),
                str(bs.get("attack", 0)),
                str(bs.get("defense", 0)),
                str(bs.get("sp_atk", 0)),
                str(bs.get("sp_def", 0)),
                str(bs.get("speed", 0)),
            ]
        )

    # Compute column widths
    widths = [len(h) for h in col_headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    sep = "  "
    header_line = sep.join(h.ljust(widths[i]) for i, h in enumerate(col_headers))
    divider = sep.join("-" * widths[i] for i in range(len(col_headers)))

    print()
    print(header_line)
    print(divider)
    for row in rows:
        print(sep.join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
    print()
    print(f"{len(results)} result{'s' if len(results) != 1 else ''}")


def _run_gen(
    gen: int,
    args: argparse.Namespace,
    workers: int,
) -> None:
    """Load Pokemon, run the full tournament for one generation, and write outputs."""
    from tqdm import tqdm

    pokemon = load_all(gen, force_fetch=args.fetch)
    if not pokemon:
        print(f"No Pokemon loaded for Gen {gen}. Run with --fetch to download data.")
        return

    pokemon_by_tier: dict[str, list] = defaultdict(list)
    for p in pokemon:
        pokemon_by_tier[p.smogon_tier].append(p)

    # Phase 1: sum of matchup battles per tier
    phase1_battles = sum(
        len(pokes) * (len(pokes) - 1) // 2 * args.battles
        for pokes in pokemon_by_tier.values()
        if len(pokes) >= 2
    )
    # Phase 2: one playoff per adjacent tier pair that could both have champions
    n_phases2_pairs = sum(
        1
        for t1, t2 in zip(TIER_ORDER, TIER_ORDER[1:], strict=False)
        if pokemon_by_tier.get(t1) and pokemon_by_tier.get(t2)
    )
    phase2_battles = n_phases2_pairs * 50
    # Phase 3: rough upper bound -- all phase 2 winners in a round robin
    phase3_battles = n_phases2_pairs * (n_phases2_pairs - 1) // 2 * 100
    total_battles = phase1_battles + phase2_battles + phase3_battles

    con.print_header(
        gen=gen,
        total_pokemon=len(pokemon),
        battles_per_matchup=args.battles,
        total_battles=total_battles,
        workers=workers,
    )

    con.print_phase1_header()

    with tqdm(
        total=total_battles,
        unit="battle",
        desc=f"Gen {gen}",
        dynamic_ncols=True,
        leave=True,
    ) as bar:
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
            progress=bar,
        )

    for tier in TIER_ORDER:
        lb = results["tier_leaderboards"].get(tier)
        if lb and lb.champion:
            con.print_tier_result(
                tier=tier,
                champion=lb.champion,
                win_rate=lb.champion_win_rate,
                participants=len(lb.entries),
            )

    con.print_phase2_header()
    for pr in results.get("playoffs", []):
        con.print_playoff_result(pr)

    gf = results.get("grand_final")
    if gf:
        con.print_phase3_header(100)
        con.print_grand_final(gf, top=args.top)

    writers.write_all(gen=gen, results=results, pokemon_by_tier=dict(pokemon_by_tier))


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate handler."""
    parser = _build_parser()
    args = parser.parse_args()

    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if args.command == "battle":
        _cmd_battle(args)
        return

    if args.command == "search":
        _cmd_search(args)
        return

    if args.command == "cache":
        if args.cache_action == "info":
            _cmd_cache_info()
        elif args.cache_action == "clear":
            _cmd_cache_clear(args.namespace)
        else:
            # `pokerena cache` with no action -- show help
            parser.parse_args(["cache", "--help"])
        return

    # Default: run the simulator
    workers = args.workers or os.cpu_count() or 4
    if args.all_gens:
        for gen in range(1, 10):
            _run_gen(gen, args, workers)
    else:
        _run_gen(args.gen, args, workers)


if __name__ == "__main__":
    main()
