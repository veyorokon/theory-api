"""Contract test: clean environment behavior."""

import os
import pytest
from libs.runtime_common.fingerprint import build_clean_env


@pytest.mark.contracts
def test_clean_env_strips_secrets_by_default():
    """Contract: build_clean_env strips secrets by default."""
    test_env = {
        "PATH": "/usr/bin",
        "DJANGO_SETTINGS_MODULE": "backend.settings.unittest",
        "OPENAI_API_KEY": "sk-test123",
        "REPLICATE_API_TOKEN": "r8_test456",
        "ANTHROPIC_API_KEY": "ant_test789",
    }

    clean = build_clean_env(base=test_env)

    # Should keep safe vars
    assert clean["PATH"] == "/usr/bin"
    assert clean["DJANGO_SETTINGS_MODULE"] == "backend.settings.unittest"

    # Should strip secrets
    assert "OPENAI_API_KEY" not in clean
    assert "REPLICATE_API_TOKEN" not in clean
    assert "ANTHROPIC_API_KEY" not in clean


@pytest.mark.contracts
def test_clean_env_allows_secrets_when_opted_in():
    """Contract: build_clean_env includes secrets when allow_secrets=True."""
    test_env = {
        "PATH": "/usr/bin",
        "OPENAI_API_KEY": "sk-test123",
        "REPLICATE_API_TOKEN": "r8_test456",
    }

    clean = build_clean_env(base=test_env, allow_secrets=True)

    # Should keep everything
    assert clean["PATH"] == "/usr/bin"
    assert clean["OPENAI_API_KEY"] == "sk-test123"
    assert clean["REPLICATE_API_TOKEN"] == "r8_test456"


@pytest.mark.contracts
def test_clean_env_preserves_safe_passthrough():
    """Contract: build_clean_env always preserves safe passthrough vars."""
    test_env = {
        "PYTHONPATH": "/app/code",
        "DJANGO_SETTINGS_MODULE": "backend.settings.test",
        "LOG_STREAM": "stderr",
        "TEST_LANE": "pr",
        "CI": "true",
        "MODAL_ENVIRONMENT": "dev",
        "OPENAI_API_KEY": "should-be-stripped",
    }

    clean = build_clean_env(base=test_env)

    # All safe vars should be preserved
    assert clean["PYTHONPATH"] == "/app/code"
    assert clean["DJANGO_SETTINGS_MODULE"] == "backend.settings.test"
    assert clean["LOG_STREAM"] == "stderr"
    assert clean["TEST_LANE"] == "pr"
    assert clean["CI"] == "true"
    assert clean["MODAL_ENVIRONMENT"] == "dev"

    # Secrets should be stripped
    assert "OPENAI_API_KEY" not in clean
