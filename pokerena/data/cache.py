"""
Local disk cache for PokeAPI and Smogon JSON responses.
Reads/writes JSON files under cache/pokeapi/ and cache/smogon/.
"""

from __future__ import annotations

import json
import pathlib

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CACHE_ROOT = _REPO_ROOT / "cache"


def _path(namespace: str, key: str) -> pathlib.Path:
    """Return the filesystem path for a cached entry."""
    return _CACHE_ROOT / namespace / f"{key}.json"


def get(namespace: str, key: str) -> dict | list | None:
    """Return the cached data for a key, or None if not cached."""
    p = _path(namespace, key)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def put(namespace: str, key: str, data: dict | list) -> None:
    """Serialize data as JSON and write it to the cache."""
    p = _path(namespace, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def exists(namespace: str, key: str) -> bool:
    """Return True if a cached file exists for the given namespace and key."""
    return _path(namespace, key).exists()


def clear(namespace: str) -> None:
    """Delete all cached files for a namespace."""
    ns_dir = _CACHE_ROOT / namespace
    if ns_dir.exists():
        for f in ns_dir.glob("*.json"):
            f.unlink()
