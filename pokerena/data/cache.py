"""
Local disk cache for PokeAPI and Smogon JSON responses.

Cache files are stored under the platform user cache directory:
  Linux/macOS: ~/.cache/pokerena/<namespace>/<key>.json
  Windows:     %LOCALAPPDATA%/pokerena/Cache/<namespace>/<key>.json

Use the `pokerena cache` sub-command to inspect or clear cached data.
"""

from __future__ import annotations

import json
import pathlib

from platformdirs import user_cache_dir

_CACHE_ROOT = pathlib.Path(user_cache_dir("pokerena"))


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


def clear(namespace: str | None = None) -> int:
    """
    Delete cached files.

    If namespace is given, only files under that namespace are removed.
    If namespace is None, the entire cache root is cleared.
    Returns the number of files deleted.
    """
    target = _CACHE_ROOT / namespace if namespace else _CACHE_ROOT
    count = 0
    if target.exists():
        for f in target.rglob("*.json"):
            f.unlink()
            count += 1
    return count


def cache_size() -> dict[str, int]:
    """
    Return a mapping of namespace -> file count for all cached namespaces.
    Only namespaces that have at least one .json file are included.
    """
    sizes: dict[str, int] = {}
    if not _CACHE_ROOT.exists():
        return sizes
    for ns_dir in sorted(_CACHE_ROOT.iterdir()):
        if ns_dir.is_dir():
            count = sum(1 for _ in ns_dir.glob("*.json"))
            if count:
                sizes[ns_dir.name] = count
    return sizes
