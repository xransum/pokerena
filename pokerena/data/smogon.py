"""
Smogon tier data loader.

Smogon tier lists are stored as JSON under cache/smogon/gen{N}_tiers.json.
Format expected:
  { "pokemon_name": "tier_name", ... }
  where tier_name is one of: ubers, ou, uu, ru, nu, pu

If no cached file exists for a generation, a bundled fallback is used that
maps all Pokemon to "ou" so the simulator can still run (with a warning).
The --fetch flag triggers re-downloading from the authoritative source.

Authoritative source: smogon/pokemon-showdown on GitHub:
  Gen 1-8: https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data/mods/gen{N}/formats-data.ts
  Gen 9:   https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data/formats-data.ts
"""

from __future__ import annotations

import logging

from pokerena.data import cache as disk_cache
from pokerena.models import TIERS

log = logging.getLogger(__name__)

# Pokemon Showdown formats-data.ts URLs by generation.
# Gen 1-8 use per-gen mod files; Gen 9 uses the main data file.
_PS_BASE = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data"
_SMOGON_URLS: dict[int, str] = {
    1: f"{_PS_BASE}/mods/gen1/formats-data.ts",
    2: f"{_PS_BASE}/mods/gen2/formats-data.ts",
    3: f"{_PS_BASE}/mods/gen3/formats-data.ts",
    4: f"{_PS_BASE}/mods/gen4/formats-data.ts",
    5: f"{_PS_BASE}/mods/gen5/formats-data.ts",
    6: f"{_PS_BASE}/mods/gen6/formats-data.ts",
    7: f"{_PS_BASE}/mods/gen7/formats-data.ts",
    8: f"{_PS_BASE}/mods/gen8/formats-data.ts",
    9: f"{_PS_BASE}/formats-data.ts",
}

# Fallback hand-curated Gen 1 tier assignments sourced from
# smogon/pokemon-showdown data/mods/gen1/formats-data.ts.
# Used when network fetch is unavailable.
_GEN1_FALLBACK: dict[str, str] = {
    # Uber
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
    "cloyster": "ou",
    "gengar": "ou",
    "rhydon": "ou",
    "zapdos": "ou",
    "jynx": "ou",
    # UU
    "raichu": "uu",
    "clefable": "uu",
    "ninetales": "uu",
    "persian": "uu",
    "dugtrio": "uu",
    "rapidash": "uu",
    "slowbro": "uu",
    "dodrio": "uu",
    "haunter": "uu",
    "hypno": "uu",
    "electabuzz": "uu",
    "gyarados": "uu",
    "lapras": "uu",
    "articuno": "uu",
    "moltres": "uu",
    "dragonite": "uu",
    "kangaskhan": "uu",
    # NU
    "venusaur": "nu",
    "charizard": "nu",
    "blastoise": "nu",
    "raticate": "nu",
    "fearow": "nu",
    "arcanine": "nu",
    "poliwhirl": "nu",
    "poliwrath": "nu",
    "kadabra": "nu",
    "victreebel": "nu",
    "tentacruel": "nu",
    "golem": "nu",
    "electrode": "nu",
    "magneton": "nu",
    "mrmime": "nu",
    "mr-mime": "nu",
    "vaporeon": "nu",
    "omastar": "nu",
    "kabutops": "nu",
    "aerodactyl": "nu",
    "tangela": "nu",
    "seadra": "nu",
    "venomoth": "nu",
    "dewgong": "nu",
    "machamp": "nu",
    # PU
    "nidoking": "pu",
    "golduck": "pu",
    "primeape": "pu",
    "abra": "pu",
    "exeggcute": "pu",
    "graveler": "pu",
    "gastly": "pu",
    "scyther": "pu",
    "magmar": "pu",
    "porygon": "pu",
    "seaking": "pu",
    "staryu": "pu",
    "pidgeot": "pu",
}

# PU-or-lower assignments for Gen 1 (ZU maps to pu in our scale)
_GEN1_PU: set[str] = {
    "butterfree",
    "beedrill",
    "nidoqueen",
    "wigglytuff",
    "golbat",
    "vileplume",
    "parasect",
    "sandslash",
    "arbok",
    "machamp",
    "slowpoke",
    "farfetchd",
    "muk",
    "onix",
    "drowzee",
    "kingler",
    "marowak",
    "hitmonlee",
    "hitmonchan",
    "lickitung",
    "weezing",
    "tentacool",
    "omanyte",
    "flareon",
    "ditto",
    "poliwag",
    "dragonair",
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

    # Try to fetch from smogon/pokemon-showdown repo
    try:
        import requests

        url = _SMOGON_URLS.get(gen)
        if url:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            tiers = _parse_ps_formats_data(resp.text)
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


def _parse_ps_formats_data(text: str) -> dict[str, str]:
    """
    Parse a Pokemon Showdown formats-data.ts file into {name: tier}.

    The TypeScript source has blocks like:
        pokemonname: {
            tier: "OU",
        },
    We extract names and tier values using a simple line-by-line scan.
    Non-standard entries (Illegal, NFE, LC, ZU, ZUBL, UUBL, etc.) are
    mapped to our internal tier scale or dropped.
    """
    import re

    result: dict[str, str] = {}
    current_name: str | None = None
    for line in text.splitlines():
        # Match a top-level entry key:  \tpokemonname: {
        name_match = re.match(r"^\t(\w+):\s*\{", line)
        if name_match:
            current_name = name_match.group(1)
            continue
        # Match a tier value inside the current block:  \t\ttier: "OU",
        tier_match = re.match(r'^\t\ttier:\s*"([^"]+)"', line)
        if tier_match and current_name is not None:
            normalized = _normalize_tier(tier_match.group(1))
            if normalized:
                result[_normalize_name(current_name)] = normalized
            current_name = None
            continue
        # Any other property resets interest in the current entry
        if re.match(r"^\t\t\w+:", line):
            current_name = None
    return result


def _parse_smogon_data(raw: dict) -> dict[str, str]:
    """
    Parse the old smogon/data JSON format into {name: tier}.
    The smogon/data JSON has entries like:
      { "Pokemon": { "tier": "OU", ... }, ... }
    or a flat { "name": "tier" } mapping.

    Kept for backwards compatibility with any cached JSON files written
    by earlier versions of this loader.
    """
    result: dict[str, str] = {}
    for name, entry in raw.items():
        tier = entry.get("tier", "").lower() if isinstance(entry, dict) else str(entry).lower()
        normalized_tier = _normalize_tier(tier)
        if normalized_tier:
            result[_normalize_name(name)] = normalized_tier
    return result


def _normalize_tier(tier: str) -> str | None:
    """
    Map raw Pokemon Showdown tier strings to our internal tier keys.

    BL (borderline) tiers are placed in the tier above:
      UUBL -> ou, RUBL -> uu, NUBL -> ru, PUBL -> nu, ZUBL -> pu
    ZU maps to pu (the lowest fully-supported tier in our scale).
    LC, NFE, Illegal, AG, and other non-standard strings are dropped.
    """
    mapping = {
        "uber": "ubers",
        "ubers": "ubers",
        "ou": "ou",
        "uubl": "ou",
        "uu": "uu",
        "rubl": "uu",
        "ru": "ru",
        "nubl": "ru",
        "nu": "nu",
        "publ": "nu",
        "pu": "pu",
        "zubl": "pu",
        "zu": "pu",
        # parenthesised "almost" variants count as that tier
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
