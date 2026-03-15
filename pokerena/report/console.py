"""
Console output formatter -- renders tournament results to the terminal.
"""

from __future__ import annotations

import click

from pokerena.models import TIER_LABELS, TIER_ORDER
from pokerena.tournament.runner import (
    GrandFinalResult,
    PlayoffResult,
)

_WIDTH = 62

# Per-tier foreground colors used throughout the output.
_TIER_COLORS: dict[str, str] = {
    "ubers": "red",
    "ou": "yellow",
    "uu": "green",
    "ru": "cyan",
    "nu": "blue",
    "pu": "white",
}


def _c(text: str, color: str | None = None, bold: bool = False, dim: bool = False) -> str:
    """Thin wrapper around click.style for brevity."""
    return click.style(str(text), fg=color, bold=bold, dim=dim)


def _tier_color(tier: str) -> str:
    """Return the display color for a given tier key."""
    return _TIER_COLORS.get(tier, "white")


def _win_rate_color(rate: float) -> str:
    """Return a color reflecting how dominant the win rate is."""
    if rate >= 0.70:
        return "green"
    if rate >= 0.50:
        return "yellow"
    return "red"


def _line(char: str = "=") -> str:
    """Return a full-width horizontal rule using the given character."""
    return _c(char * _WIDTH, color="cyan", bold=True)


def _center(text: str) -> str:
    """Center text within the standard console width."""
    return text.center(_WIDTH)


def print_header(
    gen: int,
    total_pokemon: int,
    battles_per_matchup: int,
    total_battles: int,
    workers: int,
) -> None:
    """Print the top-level tournament header with run statistics."""
    title = _c(f"POKERENA -- GEN {gen} TOURNAMENT", color="cyan", bold=True)
    print()
    print(_line())
    print(_center(title))
    print(_line())
    print(f"  {_c('Pokemon loaded  ', bold=True)} : {total_pokemon}")
    print(f"  {_c('Battles/matchup ', bold=True)} : {battles_per_matchup}")
    print(f"  {_c('Total battles   ', bold=True)} : ~{total_battles:,}")
    print(f"  {_c('CPU workers     ', bold=True)} : {workers}")
    print(_line())
    print()


def print_phase1_header() -> None:
    """Print the Phase 1 section header."""
    print(_c("Phase 1 -- Tier Tournaments", bold=True))


def print_tier_result(tier: str, champion: str, win_rate: float, participants: int) -> None:
    """Print a single tier champion result line."""
    label = TIER_LABELS.get(tier, tier.upper())
    color = _tier_color(tier)
    wr_color = _win_rate_color(win_rate)
    print(
        f"  + {_c(f'{label:<8}', color=color, bold=True)}"
        f" -> Champion: {_c(f'{champion:<18}', bold=True)}"
        f" ({_c(f'{win_rate * 100:.1f}%', color=wr_color)} win rate,"
        f" {participants} Pokemon)"
    )


def print_phase2_header() -> None:
    """Print the Phase 2 section header."""
    print()
    print(_c("Phase 2 -- Adjacent Tier Playoffs", bold=True))


def print_playoff_result(pr: PlayoffResult) -> None:
    """Print a single playoff matchup result line."""
    lower_label = TIER_LABELS.get(pr.lower_tier, pr.lower_tier.upper())
    upper_label = TIER_LABELS.get(pr.upper_tier, pr.upper_tier.upper())
    lower_color = _tier_color(pr.lower_tier)
    upper_color = _tier_color(pr.upper_tier)

    lower_styled = _c(f"{lower_label:<5}", color=lower_color, bold=True)
    upper_styled = _c(f"{upper_label:<5}", color=upper_color, bold=True)

    if pr.winner == pr.lower_champion:
        wr_color = _win_rate_color(pr.lower_win_rate)
        upset_flag = "  " + _c("<- UPSET", color="red", bold=True) if pr.upset else ""
        line = (
            f"  {lower_styled} vs {upper_styled}  -> "
            f"{_c(pr.lower_champion, bold=True)} wins  "
            f"{_c(f'{pr.lower_win_rate * 100:.0f}%', color=wr_color)}"
            f" vs {pr.upper_champion}"
            f"{upset_flag}"
        )
    else:
        upper_rate = 1 - pr.lower_win_rate
        wr_color = _win_rate_color(upper_rate)
        line = (
            f"  {lower_styled} vs {upper_styled}  -> "
            f"{_c(pr.upper_champion, bold=True)} wins  "
            f"{_c(f'{upper_rate * 100:.0f}%', color=wr_color)}"
            f" vs {pr.lower_champion}"
        )
    print(line)


def print_phase3_header(n_battles: int) -> None:
    """Print the Phase 3 grand final section header."""
    print()
    print(_c(f"Phase 3 -- Grand Final ({n_battles} battles/matchup)", bold=True))


def print_grand_final(gf: GrandFinalResult, top: int = 10) -> None:
    """Print the grand final leaderboard with Smogon tier comparison verdicts."""
    title = _c(f"GRAND FINAL RESULTS -- GEN {gf.gen}", color="cyan", bold=True)
    print()
    print(_line())
    print(_center(title))
    print(_line())
    for entry in gf.entries[:top]:
        smogon_label = TIER_LABELS.get(entry.smogon_tier, entry.smogon_tier.upper())
        sim_tier_idx = _tier_index(entry.source_tier)
        smogon_tier_idx = _tier_index(entry.smogon_tier)
        delta = sim_tier_idx - smogon_tier_idx
        if delta > 0:
            verdict = _c("UNDERRATED", color="green", bold=True)
        elif delta < 0:
            verdict = _c("OVERRATED", color="red", bold=True)
        else:
            verdict = _c("CONFIRMED", color="yellow")
        wr_color = _win_rate_color(entry.win_rate)
        smogon_color = _tier_color(entry.smogon_tier)
        print(
            f"  {entry.rank:>2}. {_c(f'{entry.name:<18}', bold=True)}"
            f" {_c(f'{entry.win_rate * 100:>5.1f}%', color=wr_color)}"
            f"   Smogon: {_c(f'{smogon_label:<6}', color=smogon_color)}"
            f"  {verdict}"
        )
    print()
    if gf.champion:
        champ_line = _c(f"GEN {gf.gen} CHAMPION: {gf.champion.upper()}", color="magenta", bold=True)
        print(_center(champ_line))
        if gf.entries:
            wr = gf.entries[0].win_rate
            wr_line = _c(f"{wr * 100:.1f}% win rate", color=_win_rate_color(wr))
            print(_center(wr_line))
    print(_line())
    print()


def _tier_index(tier: str) -> int:
    """Return the numeric position of a tier in TIER_ORDER, or -1 if unknown."""
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        return -1
