"""
Loader -- assembles Pokemon model instances from PokeAPI + Smogon data.

Responsible for:
- Fetching/caching raw API data
- Selecting the curated 4-move moveset
- Assigning Smogon tiers
- Resolving evolutionary lines
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from pokerena.data import pokeapi, smogon
from pokerena.models import Move, Pokemon

log = logging.getLogger(__name__)

# Categories of status effects keyed by move name fragments or effect entries.
# PokeAPI move data includes "meta" with "ailment" info.
_AILMENT_MAP = {
    "paralysis": "paralysis",
    "burn": "burn",
    "poison": "poison",
    "bad-poison": "poison",
    "sleep": "sleep",
    "freeze": "freeze",
}

# Maximum number of moves to load per Pokemon (via PokeAPI) before scoring.
# Loading all moves would require hundreds of extra API calls per Pokemon.
# We cap at the top N by power heuristic from the move list names.
_MAX_MOVE_FETCH = 30

# Number of concurrent threads used when fetching from PokeAPI.
# PokeAPI has no rate limit (static hosting since 2018), so higher values
# are safe. 20 is a good balance between speed and courtesy.
_FETCH_WORKERS = 20


def _parse_move(raw: dict) -> Move | None:
    """Parse a raw PokeAPI /move/{name} payload into a Move instance."""
    if raw is None:
        return None
    meta = raw.get("meta") or {}
    ailment_name = (meta.get("ailment") or {}).get("name", "none")
    status_effect = _AILMENT_MAP.get(ailment_name)

    category = (raw.get("damage_class") or {}).get("name", "status")
    power = raw.get("power") or 0
    accuracy = raw.get("accuracy") or 0
    pp = raw.get("pp") or 5
    type_ = (raw.get("type") or {}).get("name", "normal")

    # Stat changes
    stat_changes: dict[str, int] = {}
    for change in raw.get("stat_changes", []):
        stat_name = change["stat"]["name"]
        stat_changes[stat_name] = change["change"]

    return Move(
        name=raw["name"],
        type_=type_,
        category=category,
        power=power,
        accuracy=accuracy,
        pp=pp,
        status_effect=status_effect,
        stat_changes=stat_changes,
    )


def _select_moveset(
    move_names: list[str], user_types: list[str], force_fetch: bool = False
) -> list[Move]:
    """
    Fetch up to _MAX_MOVE_FETCH moves and return the best 4:
    - 3 highest-scoring damaging moves
    - 1 status move (best by accuracy, or first available)
    Falls back to all damaging if no status moves exist.
    """
    # Heuristic pre-filter: prefer moves that sound strong
    # (avoids fetching hundreds of tiny moves like "scratch" and "leer" when
    # there are high-power alternatives in the list)
    fetched: list[Move] = []
    fetched_count = 0
    for name in move_names:
        if fetched_count >= _MAX_MOVE_FETCH:
            break
        try:
            raw = pokeapi.fetch_move(name, force=force_fetch)
            move = _parse_move(raw)
            if move is not None:
                fetched.append(move)
                fetched_count += 1
        except Exception as exc:  # noqa: BLE001
            log.debug("Skipping move %s: %s", name, exc)

    damaging = [m for m in fetched if m.category in ("physical", "special") and m.power > 0]
    status = [m for m in fetched if m.category == "status"]

    # Score damaging moves (without type chart -- just STAB + power + accuracy)
    def _score(m: Move) -> float:
        """Score a move by power, STAB, and accuracy without a type chart."""
        stab = 1.5 if m.type_ in user_types else 1.0
        acc = (m.accuracy / 100.0) if m.accuracy > 0 else 1.0
        return m.power * stab * acc

    damaging.sort(key=_score, reverse=True)
    status.sort(key=lambda m: m.accuracy, reverse=True)

    chosen: list[Move] = damaging[:3]
    if status:
        chosen.append(status[0])

    # If fewer than 4, pad with more damaging moves
    if len(chosen) < 4 and len(damaging) > 3:
        extras = [m for m in damaging[3:] if m not in chosen]
        chosen += extras[: 4 - len(chosen)]

    # Guarantee at least 1 move (Struggle fallback)
    if not chosen:
        chosen = [
            Move(
                name="struggle",
                type_="normal",
                category="physical",
                power=50,
                accuracy=100,
                pp=1,
            )
        ]

    return chosen[:4]


def _load_one_entry(
    name: str, tier_map: dict[str, str], force_fetch: bool = False
) -> Pokemon | None:
    """
    Fetch and assemble a single Pokemon by name.
    Returns None on unrecoverable error (caller should log and skip).
    Safe to call from multiple threads -- all I/O goes through _fetch_cached
    which is thread-safe (disk writes are atomic enough for our purposes).
    """
    try:
        pdata = pokeapi.fetch_pokemon(name, force=force_fetch)
        base_stats = pokeapi.parse_base_stats(pdata)
        types = pokeapi.parse_types(pdata)
        move_names = pokeapi.get_candidate_move_names(pdata)
        generation = pokeapi.get_generation_number(pdata)
        tier = smogon.assign_tier(name, tier_map)
        moves = _select_moveset(move_names, types, force_fetch=force_fetch)

        try:
            species_data = pokeapi.fetch_species(name, force=force_fetch)
            chain_url = species_data["evolution_chain"]["url"]
            chain_data = pokeapi.fetch_evolution_chain(chain_url, force=force_fetch)
            lines = pokeapi.get_evo_lines(chain_data)
            evo_line: list[str] = [name]
            evo_stage = 0
            for line in lines:
                if name in line:
                    evo_line = line
                    evo_stage = line.index(name)
                    break
        except Exception as exc:  # noqa: BLE001
            log.debug("Evo line lookup failed for %s: %s", name, exc)
            evo_line = [name]
            evo_stage = 0

        bst = sum(base_stats.values())
        return Pokemon(
            name=name,
            types=types,
            base_stats=base_stats,
            moves=moves,
            generation=generation,
            smogon_tier=tier,
            bst=bst,
            evo_line=evo_line,
            evo_stage=evo_stage,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to load %s: %s", name, exc)
        return None


def load_all(gen: int, force_fetch: bool = False) -> list[Pokemon]:
    """
    Load all Pokemon for a given generation.
    Returns a list of Pokemon instances with full stats, moves, and tier data.
    """
    from tqdm import tqdm

    tier_map = smogon.load_tiers(gen, force_fetch=force_fetch)

    # Generation dex ranges (national dex id)
    gen_ranges = {
        1: (1, 151),
        2: (1, 251),
        3: (1, 386),
        4: (1, 493),
        5: (1, 649),
        6: (1, 721),
        7: (1, 809),
        8: (1, 905),
        9: (1, 1025),
    }
    dex_start, dex_end = gen_ranges.get(gen, (1, 151))

    log.info("Fetching Pokemon list...")
    all_species = pokeapi.fetch_pokemon_list(limit=dex_end, force=force_fetch)
    species_for_gen = all_species[dex_start - 1 : dex_end]

    results: list[Pokemon | None] = [None] * len(species_for_gen)

    with tqdm(
        total=len(species_for_gen),
        unit="mon",
        desc=f"Loading Gen {gen}",
        dynamic_ncols=True,
        leave=False,
    ) as bar:
        with ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
            future_to_idx = {
                pool.submit(_load_one_entry, entry["name"], tier_map, force_fetch): i
                for i, entry in enumerate(species_for_gen)
            }
            for fut in as_completed(future_to_idx):
                idx = future_to_idx[fut]
                name = species_for_gen[idx]["name"]
                bar.set_postfix_str(name, refresh=False)
                results[idx] = fut.result()
                bar.update(1)

    pokemon_list = [p for p in results if p is not None]
    log.info("Loaded %d Pokemon for Gen %d", len(pokemon_list), gen)
    return pokemon_list
