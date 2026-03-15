"""
CLI entry point for pokerena.

Commands:
  pokerena [options]                run a tournament simulation
  pokerena battle <name> <name>     run a single battle between two named Pokemon
  pokerena battle --random          pick two random Pokemon and battle them
  pokerena cache info               show cached namespaces and file counts
  pokerena cache clear [NAMESPACE]  delete cached data
  pokerena search                   list and filter Pokemon by name/type/tier/gen/BST
"""

from __future__ import annotations

import logging
import os
import sys
from collections import defaultdict
from typing import TYPE_CHECKING

import click

from pokerena.data import cache as disk_cache
from pokerena.data.loader import load_all

if TYPE_CHECKING:
    from pokerena.models import Pokemon
from pokerena.models import TIER_ORDER, TIERS
from pokerena.report import console as con
from pokerena.report import writers
from pokerena.tournament.runner import run_full_tournament

_TIERS_DISPLAY = "/".join(TIERS)


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


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


def _run_gen(gen: int, args: dict) -> None:
    """Load Pokemon, run the full tournament for one generation, and write outputs."""
    from tqdm import tqdm

    pokemon = load_all(gen, force_fetch=args["fetch"])
    if not pokemon:
        click.echo(f"No Pokemon loaded for Gen {gen}. Run with --fetch to download data.")
        return

    pokemon_by_tier: dict[str, list] = defaultdict(list)
    for p in pokemon:
        pokemon_by_tier[p.smogon_tier].append(p)

    phase1_battles = sum(
        len(pokes) * (len(pokes) - 1) // 2 * args["battles"]
        for pokes in pokemon_by_tier.values()
        if len(pokes) >= 2
    )
    n_phases2_pairs = sum(
        1
        for t1, t2 in zip(TIER_ORDER, TIER_ORDER[1:], strict=False)
        if pokemon_by_tier.get(t1) and pokemon_by_tier.get(t2)
    )
    phase2_battles = n_phases2_pairs * 50
    phase3_battles = n_phases2_pairs * (n_phases2_pairs - 1) // 2 * 100
    total_battles = phase1_battles + phase2_battles + phase3_battles

    workers = args["workers"] or os.cpu_count() or 4

    con.print_header(
        gen=gen,
        total_pokemon=len(pokemon),
        battles_per_matchup=args["battles"],
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
            n_battles_phase1=args["battles"],
            n_battles_phase2=50,
            n_battles_phase3=100,
            rand_ivs=args["rand_ivs"],
            seed=args["seed"],
            workers=workers,
            gen1_mode=args["gen1_mode"],
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
        con.print_grand_final(gf, top=args["top"])

    writers.write_all(gen=gen, results=results, pokemon_by_tier=dict(pokemon_by_tier))


@click.group(invoke_without_command=True)
@click.option(
    "--gen", default=1, metavar="N", show_default=True, help="Generation to simulate (1-9)."
)
@click.option("--all-gens", is_flag=True, help="Run all generations 1-9 sequentially.")
@click.option(
    "--battles",
    default=20,
    metavar="N",
    show_default=True,
    help="Battles per matchup in Phase 1 tier round robins.",
)
@click.option("--rand-ivs", is_flag=True, help="Use random IVs (0-15) instead of max IVs (31).")
@click.option(
    "--seed",
    default=None,
    type=int,
    metavar="N",
    help="Random seed for reproducibility. Use with --rand-ivs.",
)
@click.option(
    "--fetch", is_flag=True, help="Force re-fetch of PokeAPI and Smogon data (clears cache)."
)
@click.option(
    "--top",
    default=10,
    metavar="N",
    show_default=True,
    help="Number of entries to show in console leaderboards.",
)
@click.option(
    "--workers",
    default=None,
    type=int,
    metavar="N",
    help="CPU workers for parallel battles. Default: CPU count.",
)
@click.option("--gen1-mode", is_flag=True, help="Use Gen 1 stat formula instead of Gen 3+ default.")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging to stderr.")
@click.pass_context
def cli(
    ctx: click.Context,
    gen: int,
    all_gens: bool,
    battles: int,
    rand_ivs: bool,
    seed: int | None,
    fetch: bool,
    top: int,
    workers: int | None,
    gen1_mode: bool,
    verbose: bool,
) -> None:
    """Pokemon battle tournament simulator.

    Runs full round-robin tournaments within each Smogon tier, adjacent-tier
    playoffs, and a grand final. Results are written to results/gen{N}/.

    Run without a subcommand to start a simulation. Use a subcommand for
    individual battles, roster search, or cache management.
    """
    _setup_logging(verbose)
    if ctx.invoked_subcommand is None:
        args = {
            "battles": battles,
            "rand_ivs": rand_ivs,
            "seed": seed,
            "fetch": fetch,
            "top": top,
            "workers": workers,
            "gen1_mode": gen1_mode,
        }
        if all_gens:
            for g in range(1, 10):
                _run_gen(g, args)
        else:
            _run_gen(gen, args)


@cli.command()
@click.argument("pokemon", nargs=-1, metavar="NAME")
@click.option(
    "--random",
    "use_random",
    is_flag=True,
    help="Pick two Pokemon at random instead of specifying names.",
)
@click.option(
    "--gen",
    default=1,
    metavar="N",
    show_default=True,
    help="Generation to draw Pokemon from when using --random.",
)
@click.option("--gen1-mode", is_flag=True, help="Use Gen 1 stat formula.")
@click.option("--rand-ivs", is_flag=True, help="Use random IVs instead of max IVs.")
@click.option(
    "--seed", default=None, type=int, metavar="N", help="Random seed for reproducibility."
)
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
def battle(
    pokemon: tuple[str, ...],
    use_random: bool,
    gen: int,
    gen1_mode: bool,
    rand_ivs: bool,
    seed: int | None,
    verbose: bool,
) -> None:
    """Run a single 1v1 battle and print the result.

    Provide two Pokemon names to battle them directly, or use --random to pick
    two at random from the loaded generation roster.

    Examples:

    \b
        pokerena battle pikachu mewtwo
        pokerena battle --random --gen 2
        pokerena battle pikachu charizard --rand-ivs --seed 7
    """
    import random as _random

    from pokerena.engine.battle import run_battle
    from pokerena.models import TIER_LABELS

    _setup_logging(verbose)
    rng = _random.Random(seed)

    if use_random:
        click.echo(f"Loading Gen {gen} roster...")
        roster = load_all(gen)
        if len(roster) < 2:
            click.echo("Not enough Pokemon loaded. Run with --fetch first.")
            return
        poke_a, poke_b = rng.sample(roster, 2)
    elif len(pokemon) == 2:
        name_a, name_b = pokemon
        click.echo(f"Loading {name_a} and {name_b}...")
        try:
            poke_a = _load_one(name_a, gen)
            poke_b = _load_one(name_b, gen)
        except Exception as exc:  # noqa: BLE001
            click.echo(f"Failed to load Pokemon: {exc}")
            return
    else:
        click.echo("Provide two Pokemon names or use --random.")
        click.echo("  pokerena battle pikachu mewtwo")
        click.echo("  pokerena battle --random --gen 1")
        return

    tier_a = TIER_LABELS.get(poke_a.smogon_tier, poke_a.smogon_tier.upper())
    tier_b = TIER_LABELS.get(poke_b.smogon_tier, poke_b.smogon_tier.upper())
    types_a = "/".join(t.capitalize() for t in poke_a.types)
    types_b = "/".join(t.capitalize() for t in poke_b.types)

    click.echo("")
    click.echo(f"  {poke_a.name.capitalize()} [{types_a}]  BST {poke_a.bst}  {tier_a}")
    click.echo("    vs")
    click.echo(f"  {poke_b.name.capitalize()} [{types_b}]  BST {poke_b.bst}  {tier_b}")
    click.echo("")

    result = run_battle(poke_a, poke_b, rand_ivs=rand_ivs, rng=rng, gen1_mode=gen1_mode)

    loser = poke_b.name if result.winner == poke_a.name else poke_a.name
    resolved = "timeout (HP%)" if result.timeout else f"faint in turn {result.turns}"
    hp_pct = f"{result.winner_hp_pct * 100:.1f}%"

    click.echo(f"  Winner: {result.winner.capitalize()}")
    click.echo(f"  Loser:  {loser.capitalize()}")
    click.echo(f"  Turns:  {result.turns}  ({resolved})")
    click.echo(
        f"  Winner HP remaining: {result.winner_hp_remaining}/{result.winner_hp_max} ({hp_pct})"
    )
    if result.attacker_had_advantage:
        click.echo("  (winner had a type advantage)")
    click.echo("")


@cli.group()
def cache() -> None:
    """Manage the local PokeAPI and Smogon data cache.

    Cached data lives at ~/.cache/pokerena/ (Linux/macOS) or
    %LOCALAPPDATA%\\pokerena\\Cache\\ (Windows).
    """


@cache.command("info")
def cache_info() -> None:
    """Show the cache location and per-namespace file counts."""
    sizes = disk_cache.cache_size()
    root = disk_cache._CACHE_ROOT
    if not sizes:
        click.echo(f"Cache is empty ({root})")
        return
    click.echo(f"Cache location: {root}")
    for ns, count in sizes.items():
        click.echo(f"  {ns}: {count} file{'s' if count != 1 else ''}")


@cache.command("clear")
@click.argument("namespace", required=False, default=None, metavar="NAMESPACE")
def cache_clear(namespace: str | None) -> None:
    """Delete cached files.

    Omit NAMESPACE to clear everything. Specify 'smogon' or 'pokeapi' to
    clear only that namespace.

    Examples:

    \b
        pokerena cache clear
        pokerena cache clear smogon
        pokerena cache clear pokeapi
    """
    count = disk_cache.clear(namespace)
    scope = namespace if namespace else "all namespaces"
    click.echo(f"Cleared {count} file{'s' if count != 1 else ''} from {scope}.")


@cli.command()
@click.argument("name", required=False, default=None, metavar="NAME")
@click.option(
    "--gen",
    default=None,
    type=int,
    metavar="N",
    help="Filter to a specific generation (1-9). Omit to search all gens.",
)
@click.option(
    "--type",
    "type_filter",
    default=None,
    metavar="TYPE",
    help="Filter by type (e.g. fire, water). Matches either type slot.",
)
@click.option(
    "--tier", default=None, metavar="TIER", help=f"Filter by Smogon tier ({_TIERS_DISPLAY})."
)
@click.option(
    "--min-bst", default=None, type=int, metavar="N", help="Only show Pokemon with BST >= N."
)
@click.option(
    "--max-bst", default=None, type=int, metavar="N", help="Only show Pokemon with BST <= N."
)
@click.option(
    "--sort",
    default="name",
    metavar="FIELD",
    type=click.Choice(
        ["name", "bst", "tier", "gen", "hp", "attack", "defense", "sp_atk", "sp_def", "speed"],
        case_sensitive=False,
    ),
    show_default=True,
    help="Sort results by field.",
)
@click.option("--desc", is_flag=True, help="Reverse sort order (descending).")
@click.option(
    "--limit", default=None, type=int, metavar="N", help="Maximum number of results to show."
)
def search(
    name: str | None,
    gen: int | None,
    type_filter: str | None,
    tier: str | None,
    min_bst: int | None,
    max_bst: int | None,
    sort: str,
    desc: bool,
    limit: int | None,
) -> None:
    """List and filter Pokemon by name, type, tier, generation, or BST.

    NAME is an optional case-insensitive substring match on Pokemon name.
    Results are printed as a table with columns:
    Name, Gen, Types, Tier, BST, HP, Atk, Def, SpA, SpD, Spe.

    Examples:

    \b
        pokerena search --gen 1 --sort bst --desc
        pokerena search char --gen 1
        pokerena search --type fire --tier ou --min-bst 500
        pokerena search --sort bst --desc --limit 10
    """
    from pokerena.models import TIER_LABELS, TIER_ORDER

    name_q = name.lower().strip() if name else None
    type_q = type_filter.lower().strip() if type_filter else None
    tier_q = tier.lower().strip() if tier else None

    if tier_q and tier_q not in TIERS:
        click.echo(f"Unknown tier '{tier_q}'. Valid tiers: {', '.join(TIERS)}")
        return

    gens = [gen] if gen else list(range(1, 10))

    seen: set[str] = set()
    roster: list = []
    for g in gens:
        click.echo(f"Loading Gen {g}...")
        for p in load_all(g):
            if p.name not in seen:
                seen.add(p.name)
                roster.append(p)

    if not roster:
        click.echo("No Pokemon loaded.")
        return

    results = roster
    if name_q:
        results = [p for p in results if name_q in p.name]
    if type_q:
        results = [p for p in results if type_q in p.types]
    if tier_q:
        results = [p for p in results if p.smogon_tier == tier_q]
    if min_bst is not None:
        results = [p for p in results if p.bst >= min_bst]
    if max_bst is not None:
        results = [p for p in results if p.bst <= max_bst]

    if not results:
        click.echo("No Pokemon matched your filters.")
        return

    stat_fields = {"hp", "attack", "defense", "sp_atk", "sp_def", "speed"}
    tier_rank = {t: i for i, t in enumerate(TIER_ORDER)}

    def _sort_key(p):
        if sort == "name":
            return p.name
        if sort == "bst":
            return p.bst
        if sort == "tier":
            return tier_rank.get(p.smogon_tier, -1)
        if sort == "gen":
            return p.generation
        if sort in stat_fields:
            return p.base_stats.get(sort, 0)
        return p.name

    results.sort(key=_sort_key, reverse=desc)

    if limit:
        results = results[:limit]

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

    widths = [len(h) for h in col_headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    sep = "  "
    header_line = sep.join(h.ljust(widths[i]) for i, h in enumerate(col_headers))
    divider = sep.join("-" * widths[i] for i in range(len(col_headers)))

    click.echo("")
    click.echo(header_line)
    click.echo(divider)
    for row in rows:
        click.echo(sep.join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
    click.echo("")
    click.echo(f"{len(results)} result{'s' if len(results) != 1 else ''}")


def main() -> None:
    """Entry point registered in pyproject.toml [project.scripts]."""
    cli()
