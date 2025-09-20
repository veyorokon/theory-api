"""Unit tests for llm_litellm processor refactor - integration tests."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from libs.runtime_common.hashing import inputs_hash
from libs.runtime_common.fingerprint import memo_key


pytestmark = pytest.mark.unit


class TestLiteLLMRefactorSharedHelpers:
    """Test that shared helpers work correctly for LiteLLM canonicalization."""

    def test_canonicalization_deterministic(self):
        """Test that input canonicalization produces deterministic hashes."""
        # Same content, different key order
        canon_a = {
            "schema": "litellm-v1",
            "model": "gpt-4o-mini",
            "params": {"messages": [{"role": "user", "content": "hello"}], "temperature": 0.7, "seed": 42},
        }
        canon_b = {
            "schema": "litellm-v1",
            "model": "gpt-4o-mini",
            "params": {"seed": 42, "temperature": 0.7, "messages": [{"role": "user", "content": "hello"}]},
        }

        hash_a = inputs_hash(canon_a)
        hash_b = inputs_hash(canon_b)

        assert hash_a["value"] == hash_b["value"]

        # Memo keys should also be identical
        memo_a = memo_key(provider="litellm", model="gpt-4o-mini", inputs_hash=hash_a["value"])
        memo_b = memo_key(provider="litellm", model="gpt-4o-mini", inputs_hash=hash_b["value"])

        assert memo_a == memo_b

    def test_memo_key_includes_all_components(self):
        """Test that memo key includes all required components."""
        import os
        import platform

        memo = memo_key(provider="litellm", model="test-model", inputs_hash="abc123")

        # Memo key should be deterministic BLAKE3 hash
        assert isinstance(memo, str)
        assert len(memo) == 64  # BLAKE3 hex length

        # Different inputs should produce different keys
        memo2 = memo_key(provider="litellm", model="different-model", inputs_hash="abc123")
        assert memo != memo2

    def test_env_fingerprint_components(self):
        """Test environment fingerprint composition."""
        from libs.runtime_common.fingerprint import compose_env_fingerprint

        fingerprint = compose_env_fingerprint(py="3.11.0", arch="x86_64", empty_value="", none_value=None)

        # Should exclude empty and None values, sort keys
        assert fingerprint == "arch:x86_64;py:3.11.0"
