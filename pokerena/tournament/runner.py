"""
Tournament engine -- runs round robins, playoffs, and the grand final.

Phase 1: Full round robin within each Smogon tier (N*(N-1)/2 matchups).
Phase 2: Adjacent tier playoffs (champion of lower tier vs champion of upper).
Phase 3: Grand final -- all playoff winners in a full round robin.

All phases use multiprocessing for parallelism.
"""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from pokerena.engine.battle import BattleResult, run_battle
from pokerena.models import TIER_ORDER, Pokemon

log = logging.getLogger(__name__)


@dataclass
class MatchupRecord:
    """Aggregated results for a specific A-vs-B matchup."""

    pokemon_a: str
    pokemon_b: str
    battles: int = 0
    wins_a: int = 0
    wins_b: int = 0
    avg_hp_pct_winner: float = 0.0
    type_advantage_wins: int = 0

    @property
    def win_rate_a(self) -> float:
        """Win rate of pokemon_a across all recorded battles."""
        return self.wins_a / self.battles if self.battles else 0.0

    @property
    def win_rate_b(self) -> float:
        """Win rate of pokemon_b across all recorded battles."""
        return self.wins_b / self.battles if self.battles else 0.0


@dataclass
class TierLeaderboard:
    """Leaderboard for a single tier tournament."""

    tier: str
    gen: int
    entries: list[LeaderboardEntry] = field(default_factory=list)
    champion: str | None = None
    champion_win_rate: float = 0.0


@dataclass
class LeaderboardEntry:
    """Single row in a tier leaderboard, ranked by win rate."""

    rank: int
    name: str
    wins: int
    losses: int
    battles: int
    win_rate: float
    avg_hp_pct: float  # average HP% remaining when winning
    tier: str
    bst: int
    types: str  # slash-separated


@dataclass
class PlayoffResult:
    """Outcome of a Phase 2 adjacent-tier playoff."""

    lower_tier: str
    upper_tier: str
    lower_champion: str
    upper_champion: str
    lower_wins: int
    upper_wins: int
    battles: int
    upset: bool  # True if lower tier champion won

    @property
    def winner(self) -> str:
        """Return the name of the winning champion."""
        return self.lower_champion if self.lower_wins > self.upper_wins else self.upper_champion

    @property
    def lower_win_rate(self) -> float:
        """Win rate of the lower-tier champion in this playoff."""
        return self.lower_wins / self.battles if self.battles else 0.0


@dataclass
class GrandFinalResult:
    """Results of the Phase 3 grand final round robin."""

    gen: int
    entries: list[GrandFinalEntry] = field(default_factory=list)
    champion: str | None = None
    matchup_matrix: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class GrandFinalEntry:
    """Single ranked entry in the grand final leaderboard."""

    rank: int
    name: str
    win_rate: float
    source_tier: str
    smogon_tier: str


def _run_matchup_worker(args: tuple) -> MatchupRecord:
    """
    Run N battles between two Pokemon and return aggregated MatchupRecord.
    Module-level so it is picklable by ProcessPoolExecutor.
    Receives gen as an int and reconstructs the rules object inside the worker
    to avoid pickle edge cases with class instances.
    """
    a_dict, b_dict, n_battles, rand_ivs, seed, gen = args

    # Reconstruct Pokemon from dicts (avoids pickling full objects)
    from pokerena.engine.battle import run_battle
    from pokerena.engine.rules import RULES_BY_GEN, Gen6Rules
    from pokerena.models import Move, Pokemon

    rules = RULES_BY_GEN.get(gen, Gen6Rules())

    def _rebuild_move(d: dict) -> Move:
        """Reconstruct a Move instance from a plain dict."""
        return Move(**d)

    def _rebuild_pokemon(d: dict) -> Pokemon:
        """Reconstruct a Pokemon instance from a plain dict, rebuilding its moves."""
        moves = [_rebuild_move(m) for m in d.pop("moves")]
        p = Pokemon(moves=moves, **d)
        return p

    a = _rebuild_pokemon(dict(a_dict))
    b = _rebuild_pokemon(dict(b_dict))

    rng = random.Random(seed)
    record = MatchupRecord(pokemon_a=a.name, pokemon_b=b.name)

    total_hp_pct = 0.0
    for _ in range(n_battles):
        result: BattleResult = run_battle(
            a,
            b,
            rand_ivs=rand_ivs,
            rng=rng,
            rules=rules,
        )
        record.battles += 1
        if result.winner == a.name:
            record.wins_a += 1
        else:
            record.wins_b += 1
        total_hp_pct += result.winner_hp_pct
        if result.attacker_had_advantage:
            record.type_advantage_wins += 1

    record.avg_hp_pct_winner = total_hp_pct / record.battles
    return record


def _pokemon_to_dict(p: Pokemon) -> dict:
    """Serialize a Pokemon to a plain dict for cross-process passing."""
    moves = [
        {
            "name": m.name,
            "type_": m.type_,
            "category": m.category,
            "power": m.power,
            "accuracy": m.accuracy,
            "pp": m.pp,
            "status_effect": m.status_effect,
            "stat_changes": m.stat_changes,
        }
        for m in p.moves
    ]
    return {
        "name": p.name,
        "types": p.types,
        "base_stats": p.base_stats,
        "moves": moves,
        "generation": p.generation,
        "smogon_tier": p.smogon_tier,
        "bst": p.bst,
        "evo_line": p.evo_line,
        "evo_stage": p.evo_stage,
    }


def run_tier_tournament(
    tier: str,
    pokemon: list[Pokemon],
    n_battles: int = 20,
    rand_ivs: bool = False,
    seed: int | None = None,
    workers: int = 4,
    gen: int = 6,
    progress: Any = None,
) -> tuple[TierLeaderboard, list[MatchupRecord]]:
    """
    Run a full round robin within a tier.
    Returns (leaderboard, all matchup records).
    If progress is a tqdm bar, it is advanced by n_battles per completed matchup.
    """
    if len(pokemon) < 2:
        log.warning("Tier %s has fewer than 2 Pokemon -- skipping.", tier)
        lb = TierLeaderboard(tier=tier, gen=0)
        return lb, []

    pairs = list(combinations(pokemon, 2))
    log.info(
        "Tier %s: %d Pokemon, %d matchups, %d battles each",
        tier,
        len(pokemon),
        len(pairs),
        n_battles,
    )

    # Build worker args
    base_seed = seed if seed is not None else random.randint(0, 2**32)
    tasks = [
        (
            _pokemon_to_dict(a),
            _pokemon_to_dict(b),
            n_battles,
            rand_ivs,
            base_seed + i,
            gen,
        )
        for i, (a, b) in enumerate(pairs)
    ]

    records: list[MatchupRecord] = []
    pool = ProcessPoolExecutor(max_workers=workers)
    try:
        futures = {pool.submit(_run_matchup_worker, t): t for t in tasks}
        for fut in as_completed(futures):
            try:
                records.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                log.error("Matchup failed: %s", exc)
            if progress is not None:
                progress.update(n_battles)
    except KeyboardInterrupt:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)

    leaderboard = _build_leaderboard(tier, pokemon, records)
    return leaderboard, records


def _build_leaderboard(
    tier: str,
    pokemon: list[Pokemon],
    records: list[MatchupRecord],
) -> TierLeaderboard:
    """Tally wins/losses and build a sorted leaderboard."""
    wins: dict[str, int] = defaultdict(int)
    losses: dict[str, int] = defaultdict(int)
    battles: dict[str, int] = defaultdict(int)
    hp_pct_sum: dict[str, float] = defaultdict(float)
    hp_pct_count: dict[str, int] = defaultdict(int)

    for rec in records:
        battles[rec.pokemon_a] += rec.battles
        battles[rec.pokemon_b] += rec.battles
        wins[rec.pokemon_a] += rec.wins_a
        wins[rec.pokemon_b] += rec.wins_b
        losses[rec.pokemon_a] += rec.wins_b
        losses[rec.pokemon_b] += rec.wins_a
        # Average HP pct only for battles that pokemon won
        if rec.wins_a > 0:
            hp_pct_sum[rec.pokemon_a] += rec.avg_hp_pct_winner * rec.wins_a
            hp_pct_count[rec.pokemon_a] += rec.wins_a
        if rec.wins_b > 0:
            hp_pct_sum[rec.pokemon_b] += rec.avg_hp_pct_winner * rec.wins_b
            hp_pct_count[rec.pokemon_b] += rec.wins_b

    poke_map = {p.name: p for p in pokemon}
    entries: list[LeaderboardEntry] = []
    for name in poke_map:
        w = wins[name]
        l = losses[name]  # noqa: E741
        b = battles[name]
        wr = w / b if b else 0.0
        avg_hp = (hp_pct_sum[name] / hp_pct_count[name]) if hp_pct_count[name] else 0.0
        p = poke_map[name]
        entries.append(
            LeaderboardEntry(
                rank=0,
                name=name,
                wins=w,
                losses=l,
                battles=b,
                win_rate=wr,
                avg_hp_pct=avg_hp,
                tier=tier,
                bst=p.bst,
                types="/".join(p.types),
            )
        )

    entries.sort(key=lambda e: (e.win_rate, e.avg_hp_pct), reverse=True)
    for i, entry in enumerate(entries):
        entry.rank = i + 1

    lb = TierLeaderboard(tier=tier, gen=0, entries=entries)
    if entries:
        lb.champion = entries[0].name
        lb.champion_win_rate = entries[0].win_rate
    return lb


def run_tiebreaker(
    a: Pokemon,
    b: Pokemon,
    n_battles: int = 50,
    rand_ivs: bool = False,
    seed: int | None = None,
    gen: int = 6,
) -> str:
    """
    Run a tiebreaker between two tied Pokemon.
    Returns the name of the winner.
    """
    from pokerena.engine.rules import RULES_BY_GEN, Gen6Rules

    rules = RULES_BY_GEN.get(gen, Gen6Rules())
    rng = random.Random(seed)
    wins_a = wins_b = 0
    for _ in range(n_battles):
        result = run_battle(a, b, rand_ivs=rand_ivs, rng=rng, rules=rules)
        if result.winner == a.name:
            wins_a += 1
        else:
            wins_b += 1
    return a.name if wins_a >= wins_b else b.name


def run_playoff(
    lower_tier: str,
    upper_tier: str,
    lower_champion: Pokemon,
    upper_champion: Pokemon,
    n_battles: int = 50,
    rand_ivs: bool = False,
    seed: int | None = None,
    gen: int = 6,
) -> PlayoffResult:
    """
    Run a best-of-N playoff between two tier champions.
    """
    from pokerena.engine.rules import RULES_BY_GEN, Gen6Rules

    rules = RULES_BY_GEN.get(gen, Gen6Rules())
    rng = random.Random(seed)
    wins_lower = wins_upper = 0
    for _ in range(n_battles):
        result = run_battle(
            lower_champion,
            upper_champion,
            rand_ivs=rand_ivs,
            rng=rng,
            rules=rules,
        )
        if result.winner == lower_champion.name:
            wins_lower += 1
        else:
            wins_upper += 1

    upset = wins_lower > wins_upper
    return PlayoffResult(
        lower_tier=lower_tier,
        upper_tier=upper_tier,
        lower_champion=lower_champion.name,
        upper_champion=upper_champion.name,
        lower_wins=wins_lower,
        upper_wins=wins_upper,
        battles=n_battles,
        upset=upset,
    )


def run_grand_final(
    gen: int,
    finalists: list[tuple[Pokemon, str]],  # (pokemon, source_tier)
    tier_leaderboards: dict[str, TierLeaderboard],
    n_battles: int = 100,
    rand_ivs: bool = False,
    seed: int | None = None,
    workers: int = 4,
    progress: Any = None,
) -> GrandFinalResult:
    """
    Full round robin among playoff winners.
    Returns a GrandFinalResult with rankings and win-rate matrix.
    If progress is a tqdm bar, it is advanced by n_battles per completed matchup.
    """
    pokemon_list = [p for p, _ in finalists]
    source_map = {p.name: t for p, t in finalists}
    smogon_map = {p.name: p.smogon_tier for p, _ in finalists}

    pairs = list(combinations(pokemon_list, 2))
    base_seed = seed if seed is not None else random.randint(0, 2**32)
    tasks = [
        (
            _pokemon_to_dict(a),
            _pokemon_to_dict(b),
            n_battles,
            rand_ivs,
            base_seed + i,
            gen,
        )
        for i, (a, b) in enumerate(pairs)
    ]

    records: list[MatchupRecord] = []
    pool = ProcessPoolExecutor(max_workers=workers)
    try:
        futures = {pool.submit(_run_matchup_worker, t): t for t in tasks}
        for fut in as_completed(futures):
            try:
                records.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                log.error("Grand final matchup failed: %s", exc)
            if progress is not None:
                progress.update(n_battles)
    except KeyboardInterrupt:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)

    # Build win totals
    wins: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)
    matrix: dict[str, dict[str, float]] = {p.name: {} for p in pokemon_list}

    for rec in records:
        wins[rec.pokemon_a] += rec.wins_a
        wins[rec.pokemon_b] += rec.wins_b
        total[rec.pokemon_a] += rec.battles
        total[rec.pokemon_b] += rec.battles
        matrix[rec.pokemon_a][rec.pokemon_b] = rec.win_rate_a
        matrix[rec.pokemon_b][rec.pokemon_a] = rec.win_rate_b

    entries: list[GrandFinalEntry] = []
    for p in pokemon_list:
        wr = wins[p.name] / total[p.name] if total[p.name] else 0.0
        entries.append(
            GrandFinalEntry(
                rank=0,
                name=p.name,
                win_rate=wr,
                source_tier=source_map.get(p.name, "unknown"),
                smogon_tier=smogon_map.get(p.name, "unknown"),
            )
        )

    entries.sort(key=lambda e: e.win_rate, reverse=True)
    for i, entry in enumerate(entries):
        entry.rank = i + 1

    result = GrandFinalResult(gen=gen, entries=entries, matchup_matrix=matrix)
    if entries:
        result.champion = entries[0].name
    return result


def run_full_tournament(
    gen: int,
    pokemon_by_tier: dict[str, list[Pokemon]],
    n_battles_phase1: int = 20,
    n_battles_phase2: int = 50,
    n_battles_phase3: int = 100,
    rand_ivs: bool = False,
    seed: int | None = None,
    workers: int = 4,
    progress: Any = None,
) -> dict:
    """
    Run the full 3-phase tournament for one generation.
    Returns a results dict with all leaderboards, playoff results, and grand final.
    If progress is a tqdm bar, it is advanced throughout all three phases.
    """
    results: dict = {
        "gen": gen,
        "tier_leaderboards": {},
        "tier_records": {},
        "playoffs": [],
        "grand_final": None,
        "upsets": [],
    }

    # --- Phase 1: Tier round robins ---
    champions: dict[str, Pokemon] = {}
    poke_map = {p.name: p for tier_pokes in pokemon_by_tier.values() for p in tier_pokes}

    for tier in TIER_ORDER:
        pokes = pokemon_by_tier.get(tier, [])
        if not pokes:
            log.info("Tier %s: no Pokemon, skipping.", tier)
            continue

        lb, records = run_tier_tournament(
            tier=tier,
            pokemon=pokes,
            n_battles=n_battles_phase1,
            rand_ivs=rand_ivs,
            seed=seed,
            workers=workers,
            gen=gen,
            progress=progress,
        )
        lb.gen = gen
        results["tier_leaderboards"][tier] = lb
        results["tier_records"][tier] = records

        if not lb.champion:
            continue

        # Tiebreaker if top two tied
        if len(lb.entries) >= 2 and lb.entries[0].win_rate == lb.entries[1].win_rate:
            a = poke_map[lb.entries[0].name]
            b = poke_map[lb.entries[1].name]
            winner_name = run_tiebreaker(
                a,
                b,
                n_battles=50,
                rand_ivs=rand_ivs,
                seed=seed,
                gen=gen,
            )
            if winner_name == b.name:
                lb.entries[0], lb.entries[1] = lb.entries[1], lb.entries[0]
                lb.champion = winner_name
            log.info("Tiebreaker for %s champion: %s wins", tier, winner_name)

        champion_name = lb.champion
        champions[tier] = poke_map[champion_name]
        log.info(
            "  %s champion: %s (%.1f%%)",
            tier.upper(),
            champion_name,
            lb.champion_win_rate * 100,
        )

    # --- Phase 2: Adjacent tier playoffs ---
    playoff_winners: list[tuple[Pokemon, str]] = []  # (pokemon, source_tier)
    adjacent_pairs = list(zip(TIER_ORDER, TIER_ORDER[1:], strict=False))

    for lower_tier, upper_tier in adjacent_pairs:
        if lower_tier not in champions or upper_tier not in champions:
            log.info("Skipping playoff %s vs %s -- missing champion.", lower_tier, upper_tier)
            continue

        pr = run_playoff(
            lower_tier=lower_tier,
            upper_tier=upper_tier,
            lower_champion=champions[lower_tier],
            upper_champion=champions[upper_tier],
            n_battles=n_battles_phase2,
            rand_ivs=rand_ivs,
            seed=seed,
            gen=gen,
        )
        results["playoffs"].append(pr)
        if progress is not None:
            progress.update(n_battles_phase2)
        if pr.upset:
            results["upsets"].append(pr)
            log.info(
                "  UPSET: %s (%s) beats %s (%s) %d-%d",
                pr.lower_champion,
                lower_tier,
                pr.upper_champion,
                upper_tier,
                pr.lower_wins,
                pr.upper_wins,
            )

        winner_pokemon = champions[
            pr.winner.replace(pr.lower_champion, lower_tier)
            if pr.winner == pr.lower_champion
            else upper_tier
        ]
        # Simpler: look up by name
        winner_pokemon = champions.get(lower_tier if pr.winner == pr.lower_champion else upper_tier)
        if winner_pokemon:
            source_tier = lower_tier if pr.winner == pr.lower_champion else upper_tier
            playoff_winners.append((winner_pokemon, source_tier))

    # --- Phase 3: Grand final ---
    if len(playoff_winners) >= 2:
        gf = run_grand_final(
            gen=gen,
            finalists=playoff_winners,
            tier_leaderboards=results["tier_leaderboards"],
            n_battles=n_battles_phase3,
            rand_ivs=rand_ivs,
            seed=seed,
            workers=workers,
            progress=progress,
        )
        results["grand_final"] = gf
        log.info(
            "Gen %d Champion: %s (%.1f%%)",
            gen,
            gf.champion,
            (gf.entries[0].win_rate * 100) if gf.entries else 0,
        )
    else:
        log.warning("Not enough playoff winners for grand final.")

    return results
