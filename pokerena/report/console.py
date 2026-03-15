"""
Console output formatter -- renders tournament results to the terminal.
"""

from __future__ import annotations

from pokerena.models import TIER_LABELS, TIER_ORDER
from pokerena.tournament.runner import (
    GrandFinalResult,
    PlayoffResult,
)

_WIDTH = 62


def _line(char: str = "=") -> str:
    return char * _WIDTH


def _center(text: str) -> str:
    return text.center(_WIDTH)


def print_header(
    gen: int,
    total_pokemon: int,
    battles_per_matchup: int,
    total_battles: int,
    workers: int,
) -> None:
    print()
    print(_line())
    print(_center(f"POKERENA -- GEN {gen} TOURNAMENT"))
    print(_line())
    print(f"  Pokemon loaded   : {total_pokemon}")
    print(f"  Battles/matchup  : {battles_per_matchup}")
    print(f"  Total battles    : ~{total_battles:,}")
    print(f"  CPU workers      : {workers}")
    print(_line())
    print()


def print_phase1_header() -> None:
    print("Phase 1 -- Tier Tournaments")


def print_tier_result(tier: str, champion: str, win_rate: float, participants: int) -> None:
    label = TIER_LABELS.get(tier, tier.upper())
    print(
        f"  + {label:<8} -> Champion: {champion:<18} ({win_rate * 100:.1f}% win rate, {participants} Pokemon)"
    )


def print_phase2_header() -> None:
    print()
    print("Phase 2 -- Adjacent Tier Playoffs")


def print_playoff_result(pr: PlayoffResult) -> None:
    upset_flag = "  <- UPSET" if pr.upset else ""
    lower_label = TIER_LABELS.get(pr.lower_tier, pr.lower_tier.upper())
    upper_label = TIER_LABELS.get(pr.upper_tier, pr.upper_tier.upper())
    if pr.winner == pr.lower_champion:
        line = (
            f"  {lower_label:<5} vs {upper_label:<5}  -> "
            f"{pr.lower_champion} wins  "
            f"{pr.lower_win_rate * 100:.0f}% vs {pr.upper_champion}"
            f"{upset_flag}"
        )
    else:
        upper_rate = 1 - pr.lower_win_rate
        line = (
            f"  {lower_label:<5} vs {upper_label:<5}  -> "
            f"{pr.upper_champion} wins  "
            f"{upper_rate * 100:.0f}% vs {pr.lower_champion}"
        )
    print(line)


def print_phase3_header(n_battles: int) -> None:
    print()
    print(f"Phase 3 -- Grand Final ({n_battles} battles/matchup)")
    print("  ...")


def print_grand_final(gf: GrandFinalResult, top: int = 10) -> None:
    print()
    print(_line())
    print(_center(f"GRAND FINAL RESULTS -- GEN {gf.gen}"))
    print(_line())
    for entry in gf.entries[:top]:
        smogon_label = TIER_LABELS.get(entry.smogon_tier, entry.smogon_tier.upper())
        # Compare sim rank to smogon tier
        sim_tier_idx = _tier_index(entry.source_tier)
        smogon_tier_idx = _tier_index(entry.smogon_tier)
        delta = sim_tier_idx - smogon_tier_idx
        if delta > 0:
            verdict = "UNDERRATED"
        elif delta < 0:
            verdict = "OVERRATED"
        else:
            verdict = "CONFIRMED"
        print(
            f"  {entry.rank:>2}. {entry.name:<18} {entry.win_rate * 100:>5.1f}%"
            f"   Smogon: {smogon_label:<6}  {verdict}"
        )
    print()
    if gf.champion:
        print(_center(f"GEN {gf.gen} CHAMPION: {gf.champion.upper()}"))
        if gf.entries:
            print(_center(f"{gf.entries[0].win_rate * 100:.1f}% win rate"))
    print(_line())
    print()


def _tier_index(tier: str) -> int:
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        return -1
