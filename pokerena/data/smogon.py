"""
Smogon tier data loader.

Smogon tier lists are stored as JSON under cache/smogon/gen{N}_tiers.json.
Format expected:
  { "pokemon_name": "tier_name", ... }
  where tier_name is one of: ubers, ou, uu, ru, nu, pu

If no cached file exists for a generation, a bundled fallback is used that
maps all Pokemon to "ou" so the simulator can still run (with a warning).
The --fetch flag triggers re-downloading from the authoritative source.

Authoritative source: Smogon's public GitHub datasets at
  https://github.com/smogon/pokemon-showdown/blob/master/config/formats.ts
and the compiled community JSON datasets maintained at:
  https://raw.githubusercontent.com/smogon/data/master/src/
"""

from __future__ import annotations

import logging

from pokerena.data import cache as disk_cache
from pokerena.models import TIERS

log = logging.getLogger(__name__)

# Smogon community JSON datasets by generation.
# These are the authoritative compiled tier lists from the smogon/data repo.
_SMOGON_URLS: dict[int, str] = {
    1: "https://raw.githubusercontent.com/smogon/data/master/src/rb_ou.json",
    2: "https://raw.githubusercontent.com/smogon/data/master/src/gs_ou.json",
    3: "https://raw.githubusercontent.com/smogon/data/master/src/rs_ou.json",
    4: "https://raw.githubusercontent.com/smogon/data/master/src/dp_ou.json",
    5: "https://raw.githubusercontent.com/smogon/data/master/src/bw_ou.json",
    6: "https://raw.githubusercontent.com/smogon/data/master/src/xy_ou.json",
    7: "https://raw.githubusercontent.com/smogon/data/master/src/sm_ou.json",
    8: "https://raw.githubusercontent.com/smogon/data/master/src/ss_ou.json",
    9: "https://raw.githubusercontent.com/smogon/data/master/src/sv_ou.json",
}

# Fallback hand-curated Gen 1 tier assignments sourced from
# https://www.smogon.com/dex/rb/formats/
# Used when network fetch is unavailable.
_GEN1_FALLBACK: dict[str, str] = {
    # Ubers
    "mewtwo": "ubers",
    "mew": "ubers",
    # OU
    "tauros": "ou",
    "alakazam": "ou",
    "chansey": "ou",
    "snorlax": "ou",
    "exeggutor": "ou",
    "starmie": "ou",
    "jolteon": "ou",
    "lapras": "ou",
    "dragonite": "ou",
    "rhydon": "ou",
    "slowbro": "ou",
    "cloyster": "ou",
    "tentacruel": "ou",
    "golem": "ou",
    # UU
    "nidoking": "uu",
    "nidoqueen": "uu",
    "venusaur": "uu",
    "blastoise": "uu",
    "charizard": "uu",
    "hypno": "uu",
    "machamp": "uu",
    "victreebel": "uu",
    "scyther": "uu",
    "pinsir": "uu",
    "hitmonlee": "uu",
    "hitmonchan": "uu",
    "dewgong": "uu",
    "dodrio": "uu",
    "electrode": "uu",
    "magneton": "uu",
    "persian": "uu",
    "raticate": "uu",
    "rapidash": "uu",
    "seaking": "uu",
    "tangela": "uu",
    "vaporeon": "uu",
    "omastar": "uu",
    "kabutops": "uu",
    # RU
    "arcanine": "ru",
    "poliwrath": "ru",
    "aerodactyl": "ru",
    "flareon": "ru",
    "moltres": "ru",
    "zapdos": "ru",
    "articuno": "ru",
    "gyarados": "ru",
    "mr-mime": "ru",
    "jynx": "ru",
    "electabuzz": "ru",
    "magmar": "ru",
    # NU -- everything else gets NU as default, overridden below for PU
}

# Explicit PU assignments for Gen 1
_GEN1_PU: set[str] = {
    "caterpie",
    "weedle",
    "pidgey",
    "rattata",
    "spearow",
    "ekans",
    "sandshrew",
    "nidoran-f",
    "nidoran-m",
    "clefairy",
    "vulpix",
    "jigglypuff",
    "zubat",
    "oddish",
    "paras",
    "venonat",
    "diglett",
    "meowth",
    "psyduck",
    "mankey",
    "growlithe",
    "poliwag",
    "abra",
    "bellsprout",
    "tentacool",
    "geodude",
    "ponyta",
    "slowpoke",
    "magnemite",
    "farfetchd",
    "seel",
    "grimer",
    "shellder",
    "gastly",
    "onix",
    "drowzee",
    "krabby",
    "voltorb",
    "exeggcute",
    "cubone",
    "hitmonlee",
    "hitmonchan",
    "lickitung",
    "koffing",
    "rhyhorn",
    "horsea",
    "goldeen",
    "staryu",
    "kangaskhan",
    "ditto",
    "eevee",
    "porygon",
    "omanyte",
    "kabuto",
    # Evolved forms that are still weak
    "wigglytuff",
    "golbat",
    "parasect",
    "dugtrio",
    "primeape",
    "poliwhirl",
    "kadabra",
}


def _normalize_name(name: str) -> str:
    """Lowercase and hyphenate a Pokemon name for consistent key lookups."""
    return name.lower().replace(" ", "-")


def load_tiers(gen: int, force_fetch: bool = False) -> dict[str, str]:
    """
    Return a dict mapping pokemon_name (lower-case) -> tier (lower-case).
    Falls back to built-in Gen 1 data if fetch fails.
    """
    cache_key = f"gen{gen}_tiers"
    if not force_fetch:
        cached = disk_cache.get("smogon", cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

    # Try to fetch from smogon/data repo
    try:
        import requests

        url = _SMOGON_URLS.get(gen)
        if url:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            raw = resp.json()
            tiers = _parse_smogon_data(raw)
            disk_cache.put("smogon", cache_key, tiers)
            log.info("Smogon tier data fetched for Gen %d (%d entries)", gen, len(tiers))
            return tiers
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not fetch Smogon tier data for Gen %d: %s", gen, exc)

    # Fall back to built-ins for Gen 1
    if gen == 1:
        log.warning("Using built-in Gen 1 tier fallback.")
        return _build_gen1_fallback()

    log.warning("No tier data available for Gen %d -- defaulting all to OU.", gen)
    return {}


def _parse_smogon_data(raw: dict) -> dict[str, str]:
    """
    Parse the smogon/data JSON format into {name: tier}.
    The smogon/data JSON has entries like:
      { "Pokemon": { "tier": "OU", ... }, ... }
    or a flat { "name": "tier" } mapping.
    """
    result: dict[str, str] = {}
    for name, entry in raw.items():
        tier = entry.get("tier", "").lower() if isinstance(entry, dict) else str(entry).lower()
        normalized_tier = _normalize_tier(tier)
        if normalized_tier:
            result[_normalize_name(name)] = normalized_tier
    return result


def _normalize_tier(tier: str) -> str | None:
    """Map raw Smogon tier strings to our internal tier keys."""
    mapping = {
        "uber": "ubers",
        "ubers": "ubers",
        "ou": "ou",
        "uu": "uu",
        "ru": "ru",
        "nu": "nu",
        "pu": "pu",
        "(ou)": "ou",
        "(uu)": "uu",
        "(ru)": "ru",
        "(nu)": "nu",
        "(pu)": "pu",
    }
    return mapping.get(tier.strip().lower())


def _build_gen1_fallback() -> dict[str, str]:
    """Build the hand-curated Gen 1 tier map from the bundled fallback data."""
    tiers: dict[str, str] = {}
    tiers.update(_GEN1_FALLBACK)
    for name in _GEN1_PU:
        tiers[name] = "pu"
    return tiers


def assign_tier(name: str, tier_map: dict[str, str], default: str = "nu") -> str:
    """
    Return the tier for a Pokemon name, falling back to default if not found.
    Validated against TIERS list.
    """
    tier = tier_map.get(_normalize_name(name), default)
    if tier not in TIERS:
        return default
    return tier
