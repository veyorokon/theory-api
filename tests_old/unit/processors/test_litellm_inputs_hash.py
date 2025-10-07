"""Unit tests for llm_litellm processor input hashing."""

import pytest
from libs.runtime_common.hashing import inputs_hash
from libs.runtime_common.fingerprint import memo_key


pytestmark = pytest.mark.unit


class TestLiteLLMInputsHash:
    """Test LiteLLM input canonicalization and hashing."""

    def test_inputs_hash_deterministic_message_order(self):
        """Test that inputs hash is deterministic across message key reordering."""
        canon_a = {
            "schema": "litellm-v1",
            "model": "gpt-4o-mini",
            "params": {"messages": [{"role": "user", "content": "hello"}], "temperature": 0.7, "seed": 42},
        }
        canon_b = {
            "schema": "litellm-v1",
            "model": "gpt-4o-mini",
            "params": {"seed": 42, "messages": [{"role": "user", "content": "hello"}], "temperature": 0.7},
        }

        hash_a = inputs_hash(canon_a)
        hash_b = inputs_hash(canon_b)

        assert hash_a["hash_schema"] == "jcs-blake3-v1"
        assert hash_a["value"] == hash_b["value"]

    def test_memo_key_deterministic(self):
        """Test that memo key is deterministic for same inputs."""
        inputs_hash_val = "abc123def456"

        key1 = memo_key(provider="litellm", model="gpt-4o-mini", inputs_hash=inputs_hash_val)
        key2 = memo_key(provider="litellm", model="gpt-4o-mini", inputs_hash=inputs_hash_val)

        assert key1 == key2
        assert isinstance(key1, str)
        assert len(key1) == 64  # BLAKE3 hex

    def test_memo_key_differs_by_model(self):
        """Test that memo key differs when model changes."""
        inputs_hash_val = "abc123def456"

        key1 = memo_key(provider="litellm", model="gpt-4o-mini", inputs_hash=inputs_hash_val)
        key2 = memo_key(provider="litellm", model="gpt-4o", inputs_hash=inputs_hash_val)

        assert key1 != key2

    def test_memo_key_differs_by_provider(self):
        """Test that memo key differs when provider changes."""
        inputs_hash_val = "abc123def456"

        key1 = memo_key(provider="litellm", model="gpt-4o-mini", inputs_hash=inputs_hash_val)
        key2 = memo_key(provider="replicate", model="gpt-4o-mini", inputs_hash=inputs_hash_val)

        assert key1 != key2
