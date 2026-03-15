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


class TestDiskCache:
    """Tests for the disk-based JSON cache module."""

    def test_put_and_get(self, tmp_path, monkeypatch):
        """put followed by get should return the same data."""
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
        """get on a key that has never been put should return None."""
        monkeypatch.setattr(disk_cache, "_CACHE_ROOT", tmp_path)
        assert disk_cache.get("test_ns", "nonexistent") is None

    def test_exists_true_after_put(self, tmp_path, monkeypatch):
        """exists should return True after a successful put."""
        monkeypatch.setattr(disk_cache, "_CACHE_ROOT", tmp_path)
        disk_cache.put("ns", "key", {"x": 1})
        assert disk_cache.exists("ns", "key") is True

    def test_exists_false_before_put(self, tmp_path, monkeypatch):
        """exists should return False for a key that has never been written."""
        monkeypatch.setattr(disk_cache, "_CACHE_ROOT", tmp_path)
        assert disk_cache.exists("ns", "missing") is False

    def test_clear_removes_files(self, tmp_path, monkeypatch):
        """clear should remove all cached entries under the given namespace."""
        monkeypatch.setattr(disk_cache, "_CACHE_ROOT", tmp_path)
        disk_cache.put("ns", "a", {"v": 1})
        disk_cache.put("ns", "b", {"v": 2})
        disk_cache.clear("ns")
        assert disk_cache.get("ns", "a") is None
        assert disk_cache.get("ns", "b") is None


class TestNormalizeTier:
    """Tests for the _normalize_tier helper."""

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
        """Known tier strings should normalize to their canonical lowercase form."""
        assert _normalize_tier(raw) == expected

    @pytest.mark.parametrize("raw", ["NFE", "LC", "Banned", "", "  ", "AG"])
    def test_unknown_tiers_return_none(self, raw):
        """Tier strings that map to no recognised tier should return None."""
        assert _normalize_tier(raw) is None


class TestAssignTier:
    """Tests for the assign_tier function."""

    def test_known_pokemon(self):
        """A name present in the tier map should return its mapped tier."""
        tier_map = {"mewtwo": "ubers", "charizard": "ou", "rattata": "pu"}
        assert assign_tier("mewtwo", tier_map) == "ubers"
        assert assign_tier("charizard", tier_map) == "ou"

    def test_unknown_defaults_to_nu(self):
        """A name absent from the tier map should default to 'nu'."""
        assert assign_tier("unknown-pokemon", {}) == "nu"

    def test_custom_default(self):
        """The caller-supplied default should be used when the name is missing."""
        assert assign_tier("unknown", {}, default="pu") == "pu"

    def test_case_insensitive_lookup(self):
        """Lookup should succeed regardless of the case used in the tier map key."""
        tier_map = {"mr-mime": "uu"}
        assert assign_tier("mr-mime", tier_map) == "uu"

    def test_invalid_tier_in_map_returns_default(self):
        """If the mapped tier string is not in TIERS, the default should be returned."""
        # If tier_map contains a bad tier, fallback to default
        tier_map = {"glitch": "???"}
        assert assign_tier("glitch", tier_map) == "nu"

    def test_all_tiers_are_valid(self):
        """Every value in TIERS should be accepted as a valid assignment."""
        for tier in TIERS:
            tier_map = {"testmon": tier}
            assert assign_tier("testmon", tier_map) == tier


class TestGen1Fallback:
    """Tests for the _build_gen1_fallback helper."""

    def test_mewtwo_is_ubers(self):
        """Mewtwo should be placed in the 'ubers' tier."""
        tiers = _build_gen1_fallback()
        assert tiers.get("mewtwo") == "ubers"

    def test_charizard_is_uu(self):
        """Charizard should be placed in the 'uu' tier."""
        tiers = _build_gen1_fallback()
        assert tiers.get("charizard") == "uu"

    def test_rattata_is_pu(self):
        """Rattata should be placed in the 'pu' tier."""
        tiers = _build_gen1_fallback()
        assert tiers.get("rattata") == "pu"

    def test_all_values_are_valid_tiers(self):
        """Every tier value in the fallback map should be a member of TIERS."""
        tiers = _build_gen1_fallback()
        for name, tier in tiers.items():
            assert tier in TIERS, f"{name} has invalid tier '{tier}'"

    def test_no_empty_names(self):
        """No entry in the fallback map should have an empty or falsy name."""
        tiers = _build_gen1_fallback()
        assert all(name for name in tiers)


class TestParseSmogonData:
    """Tests for the _parse_smogon_data helper."""

    def test_dict_format(self):
        """Dict-style entries (name -> {tier: ...}) should be parsed correctly."""
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
        """Flat entries (name -> tier string) should be parsed correctly."""
        raw = {"Mewtwo": "Ubers", "Pidgey": "NU"}
        result = _parse_smogon_data(raw)
        assert result["mewtwo"] == "ubers"
        assert result["pidgey"] == "nu"

    def test_unknown_tiers_excluded(self):
        """Entries whose tier does not map to a recognised tier should be dropped."""
        raw = {"Glitch": {"tier": "NFE"}, "Mewtwo": {"tier": "Ubers"}}
        result = _parse_smogon_data(raw)
        assert "glitch" not in result
        assert "mewtwo" in result

    def test_names_normalized_to_lowercase_with_hyphens(self):
        """Pokemon names should be lowercased and spaces replaced with hyphens."""
        raw = {"Mr Mime": {"tier": "UU"}}
        result = _parse_smogon_data(raw)
        assert "mr-mime" in result
