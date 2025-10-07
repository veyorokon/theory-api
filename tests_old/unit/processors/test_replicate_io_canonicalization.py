"""Unit tests for shared input canonicalization."""

import pytest
from libs.runtime_common.hashing import canonicalize_inputs
from libs.runtime_common.hashing import inputs_hash


pytestmark = pytest.mark.unit


class TestInputCanonicalization:
    """Test shared input canonicalization."""

    def test_inputs_hash_stable(self):
        """Test that inputs hash is stable across key reordering."""
        a = {"model": "owner/m:1", "params": {"prompt": "hi", "seed": 0}, "outputs": []}
        b = {"model": "owner/m:1", "params": {"seed": 0, "prompt": "hi"}, "outputs": []}
        ca, cb = canonicalize_inputs(a), canonicalize_inputs(b)
        ha, hb = inputs_hash(ca), inputs_hash(cb)
        assert ha["hash_schema"] == "jcs-blake3-v1"
        assert ha["value"] == hb["value"]

    def test_canonicalize_sorts_keys(self):
        """Test that canonicalization sorts keys recursively."""
        input_data = {"z": 1, "a": {"c": 3, "b": 2}}
        canonical = canonicalize_inputs(input_data)
        assert list(canonical.keys()) == ["a", "z"]
        assert list(canonical["a"].keys()) == ["b", "c"]
