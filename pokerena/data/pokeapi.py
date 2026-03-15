"""
PokeAPI client -- fetches and caches Pokemon data.

Fetches once per Pokemon per generation and writes to cache/pokeapi/.
Never hits the network during simulation if cache is warm.
"""

from __future__ import annotations

import logging

import requests

from pokerena.data import cache as disk_cache

log = logging.getLogger(__name__)

_BASE = "https://pokeapi.co/api/v2"


def _get(url: str) -> dict:
    """Make a GET request and return the parsed JSON response."""
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _fetch_cached(namespace: str, key: str, url: str) -> dict:
    """Return cached data if present, otherwise fetch from URL, cache, and return."""
    cached = disk_cache.get(namespace, key)
    if cached is not None:
        return cached  # type: ignore[return-value]
    log.debug("Fetching %s", url)
    data = _get(url)
    disk_cache.put(namespace, key, data)
    return data


def fetch_pokemon_list(limit: int = 2000) -> list[dict]:
    """Return the raw PokeAPI species list (name + url pairs)."""
    data = _fetch_cached("pokeapi", "pokemon_list", f"{_BASE}/pokemon?limit={limit}")
    return data["results"]


def fetch_pokemon(name: str) -> dict:
    """Return raw PokeAPI /pokemon/{name} payload, cached."""
    return _fetch_cached("pokeapi", f"pokemon_{name}", f"{_BASE}/pokemon/{name}")


def fetch_species(name: str) -> dict:
    """Return raw PokeAPI /pokemon-species/{name} payload, cached."""
    return _fetch_cached("pokeapi", f"species_{name}", f"{_BASE}/pokemon-species/{name}")


def fetch_move(name: str) -> dict:
    """Return raw PokeAPI /move/{name} payload, cached."""
    return _fetch_cached("pokeapi", f"move_{name}", f"{_BASE}/move/{name}")


def fetch_evolution_chain(url: str) -> dict:
    """Fetch an evolution chain by its full URL."""
    # Derive a stable cache key from the URL id
    chain_id = url.rstrip("/").split("/")[-1]
    return _fetch_cached("pokeapi", f"evochain_{chain_id}", url)


def get_generation_number(pokemon_data: dict) -> int:
    """Extract the generation number (1-9) from a PokeAPI pokemon payload."""
    # PokeAPI gives generation via species; caller must pass species data or
    # we derive it from the id range as a fallback.
    pid = pokemon_data.get("id", 0)
    # Approximate by national dex id
    if pid <= 151:
        return 1
    if pid <= 251:
        return 2
    if pid <= 386:
        return 3
    if pid <= 493:
        return 4
    if pid <= 649:
        return 5
    if pid <= 721:
        return 6
    if pid <= 809:
        return 7
    if pid <= 905:
        return 8
    return 9


def parse_base_stats(pokemon_data: dict) -> dict[str, int]:
    """Return {stat_name: base_value} from raw PokeAPI pokemon payload."""
    stat_map = {
        "hp": "hp",
        "attack": "attack",
        "defense": "defense",
        "special-attack": "sp_atk",
        "special-defense": "sp_def",
        "speed": "speed",
    }
    result: dict[str, int] = {}
    for entry in pokemon_data["stats"]:
        key = entry["stat"]["name"]
        if key in stat_map:
            result[stat_map[key]] = entry["base_stat"]
    return result


def parse_types(pokemon_data: dict) -> list[str]:
    """Return list of type name strings (lower-case)."""
    return [slot["type"]["name"] for slot in pokemon_data["types"]]


def get_candidate_move_names(pokemon_data: dict) -> list[str]:
    """Return all move names this Pokemon can learn (any method)."""
    return [m["move"]["name"] for m in pokemon_data["moves"]]


def _walk_evo_chain(chain_node: dict) -> list[list[str]]:
    """
    Recursively walk an evolution chain node and return a list of paths,
    where each path is an ordered list of species names from base -> final.
    Handles branching (e.g. Eevee).
    """
    name = chain_node["species"]["name"]
    evolves_to = chain_node.get("evolves_to", [])
    if not evolves_to:
        return [[name]]
    paths: list[list[str]] = []
    for child in evolves_to:
        for sub_path in _walk_evo_chain(child):
            paths.append([name] + sub_path)
    return paths


def get_evo_lines(evolution_chain_data: dict) -> list[list[str]]:
    """
    Return all evolutionary paths in a chain.
    Each path is a list of species names ordered from base to final stage.
    """
    return _walk_evo_chain(evolution_chain_data["chain"])
