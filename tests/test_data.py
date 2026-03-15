"""
Tests for the data layer -- cache, smogon tier loading, and model assembly.
"""

import pytest

from pokerena.data import cache as disk_cache
from pokerena.data.smogon import (
    _build_gen1_fallback,
    _normalize_tier,
    _parse_smogon_data,
    assign_tier,
)
from pokerena.models import TIERS

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TestDiskCache:
    def test_put_and_get(self, tmp_path, monkeypatch):
        # Redirect cache root to a temp directory
        monkeypatch.setattr(
            disk_cache,
            "_CACHE_ROOT",
            tmp_path,
        )
        data = {"foo": "bar", "count": 42}
        disk_cache.put("test_ns", "test_key", data)
        result = disk_cache.get("test_ns", "test_key")
        assert result == data

    def test_get_missing_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(disk_cache, "_CACHE_ROOT", tmp_path)
        assert disk_cache.get("test_ns", "nonexistent") is None

    def test_exists_true_after_put(self, tmp_path, monkeypatch):
        monkeypatch.setattr(disk_cache, "_CACHE_ROOT", tmp_path)
        disk_cache.put("ns", "key", {"x": 1})
        assert disk_cache.exists("ns", "key") is True

    def test_exists_false_before_put(self, tmp_path, monkeypatch):
        monkeypatch.setattr(disk_cache, "_CACHE_ROOT", tmp_path)
        assert disk_cache.exists("ns", "missing") is False

    def test_clear_removes_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(disk_cache, "_CACHE_ROOT", tmp_path)
        disk_cache.put("ns", "a", {"v": 1})
        disk_cache.put("ns", "b", {"v": 2})
        disk_cache.clear("ns")
        assert disk_cache.get("ns", "a") is None
        assert disk_cache.get("ns", "b") is None

    def test_overwrite_existing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(disk_cache, "_CACHE_ROOT", tmp_path)
        disk_cache.put("ns", "key", {"v": 1})
        disk_cache.put("ns", "key", {"v": 99})
        result = disk_cache.get("ns", "key")
        assert result["v"] == 99

    def test_list_data_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(disk_cache, "_CACHE_ROOT", tmp_path)
        data = [{"name": "bulbasaur"}, {"name": "ivysaur"}]
        disk_cache.put("ns", "list_key", data)
        result = disk_cache.get("ns", "list_key")
        assert result == data


# ---------------------------------------------------------------------------
# Smogon tier normalization
# ---------------------------------------------------------------------------


class TestNormalizeTier:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("OU", "ou"),
            ("ou", "ou"),
            ("(OU)", "ou"),
            ("Ubers", "ubers"),
            ("uber", "ubers"),
            ("UU", "uu"),
            ("RU", "ru"),
            ("NU", "nu"),
            ("PU", "pu"),
            ("(PU)", "pu"),
        ],
    )
    def test_known_tiers(self, raw, expected):
        assert _normalize_tier(raw) == expected

    @pytest.mark.parametrize("raw", ["NFE", "LC", "Banned", "", "  ", "AG"])
    def test_unknown_tiers_return_none(self, raw):
        assert _normalize_tier(raw) is None


# ---------------------------------------------------------------------------
# Smogon tier assignment
# ---------------------------------------------------------------------------


class TestAssignTier:
    def test_known_pokemon(self):
        tier_map = {"mewtwo": "ubers", "charizard": "ou", "rattata": "pu"}
        assert assign_tier("mewtwo", tier_map) == "ubers"
        assert assign_tier("charizard", tier_map) == "ou"

    def test_unknown_defaults_to_nu(self):
        assert assign_tier("unknown-pokemon", {}) == "nu"

    def test_custom_default(self):
        assert assign_tier("unknown", {}, default="pu") == "pu"

    def test_case_insensitive_lookup(self):
        tier_map = {"mr-mime": "uu"}
        assert assign_tier("mr-mime", tier_map) == "uu"

    def test_invalid_tier_in_map_returns_default(self):
        # If tier_map contains a bad tier, fallback to default
        tier_map = {"glitch": "???"}
        assert assign_tier("glitch", tier_map) == "nu"

    def test_all_tiers_are_valid(self):
        for tier in TIERS:
            tier_map = {"testmon": tier}
            assert assign_tier("testmon", tier_map) == tier


# ---------------------------------------------------------------------------
# Gen 1 fallback data
# ---------------------------------------------------------------------------


class TestGen1Fallback:
    def test_mewtwo_is_ubers(self):
        tiers = _build_gen1_fallback()
        assert tiers.get("mewtwo") == "ubers"

    def test_charizard_is_uu(self):
        tiers = _build_gen1_fallback()
        assert tiers.get("charizard") == "uu"

    def test_rattata_is_pu(self):
        tiers = _build_gen1_fallback()
        assert tiers.get("rattata") == "pu"

    def test_all_values_are_valid_tiers(self):
        tiers = _build_gen1_fallback()
        for name, tier in tiers.items():
            assert tier in TIERS, f"{name} has invalid tier '{tier}'"

    def test_no_empty_names(self):
        tiers = _build_gen1_fallback()
        assert all(name for name in tiers)


# ---------------------------------------------------------------------------
# _parse_smogon_data
# ---------------------------------------------------------------------------


class TestParseSmogonData:
    def test_dict_format(self):
        raw = {
            "Mewtwo": {"tier": "Ubers"},
            "Charizard": {"tier": "OU"},
            "Rattata": {"tier": "PU"},
        }
        result = _parse_smogon_data(raw)
        assert result["mewtwo"] == "ubers"
        assert result["charizard"] == "ou"
        assert result["rattata"] == "pu"

    def test_flat_format(self):
        raw = {"Mewtwo": "Ubers", "Pidgey": "NU"}
        result = _parse_smogon_data(raw)
        assert result["mewtwo"] == "ubers"
        assert result["pidgey"] == "nu"

    def test_unknown_tiers_excluded(self):
        raw = {"Glitch": {"tier": "NFE"}, "Mewtwo": {"tier": "Ubers"}}
        result = _parse_smogon_data(raw)
        assert "glitch" not in result
        assert "mewtwo" in result

    def test_names_normalized_to_lowercase_with_hyphens(self):
        raw = {"Mr Mime": {"tier": "UU"}}
        result = _parse_smogon_data(raw)
        assert "mr-mime" in result
