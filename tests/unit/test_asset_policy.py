# tests/unit/test_asset_policy.py
"""
Unit tests for asset download policy configuration system.
"""

import pytest
from unittest.mock import patch
import os

from libs.runtime_common.asset_policy import (
    AssetPolicy,
    AssetPolicyRegistry,
    create_default_policy_registry,
    get_asset_policy,
    get_asset_download_config,
    _get_processor_family,
    _detect_environment,
)
from libs.runtime_common.asset_downloader import AssetDownloadConfig


class TestAssetPolicy:
    """Test AssetPolicy dataclass."""

    def test_default_policy(self):
        """Test default policy values."""
        policy = AssetPolicy()

        assert policy.enabled is True
        assert policy.max_bytes == 50 * 1024 * 1024
        assert policy.timeout_s == 30
        assert policy.max_assets_per_execution == 10
        assert policy.allowed_schemes == ["https"]
        assert policy.blocked_domains == []
        assert "image/*" in policy.allowed_content_types
        assert policy.use_deterministic_names is True
        assert policy.include_source_url_metadata is True

    def test_custom_policy(self):
        """Test custom policy configuration."""
        policy = AssetPolicy(
            enabled=False,
            max_bytes=10 * 1024 * 1024,
            timeout_s=15,
            allowed_schemes=["https", "http"],
            blocked_domains=["badsite.com"],
        )

        assert policy.enabled is False
        assert policy.max_bytes == 10 * 1024 * 1024
        assert policy.timeout_s == 15
        assert policy.allowed_schemes == ["https", "http"]
        assert policy.blocked_domains == ["badsite.com"]

    def test_to_download_config(self):
        """Test conversion to AssetDownloadConfig."""
        policy = AssetPolicy(
            enabled=True,
            max_bytes=25 * 1024 * 1024,
            timeout_s=45,
            allowed_schemes=["https"],
        )

        config = policy.to_download_config()

        assert isinstance(config, AssetDownloadConfig)
        assert config.enabled is True
        assert config.max_bytes == 25 * 1024 * 1024
        assert config.timeout_s == 45
        assert config.allowed_schemes == ("https",)


class TestAssetPolicyRegistry:
    """Test AssetPolicyRegistry dataclass."""

    def test_empty_registry(self):
        """Test empty registry creation."""
        registry = AssetPolicyRegistry()

        assert isinstance(registry.default, AssetPolicy)
        assert registry.processors == {}
        assert registry.environments == {}

    def test_registry_with_policies(self):
        """Test registry with custom policies."""
        default_policy = AssetPolicy(enabled=False)
        replicate_policy = AssetPolicy(max_bytes=100 * 1024 * 1024)
        ci_policy = AssetPolicy(enabled=False, timeout_s=5)

        registry = AssetPolicyRegistry(
            default=default_policy,
            processors={"replicate": replicate_policy},
            environments={"ci": ci_policy},
        )

        assert registry.default.enabled is False
        assert registry.processors["replicate"].max_bytes == 100 * 1024 * 1024
        assert registry.environments["ci"].timeout_s == 5


class TestProcessorFamilyExtraction:
    """Test processor family name extraction."""

    def test_get_processor_family(self):
        """Test processor family extraction from various refs."""
        test_cases = [
            ("replicate/generic@1", "replicate"),
            ("llm/litellm@2", "llm"),
            ("custom-processor@1", "custom-processor"),
            ("simple", "simple"),
            ("namespace/processor", "namespace"),
        ]

        for processor_ref, expected_family in test_cases:
            result = _get_processor_family(processor_ref)
            assert result == expected_family, f"Failed for {processor_ref}"


class TestEnvironmentDetection:
    """Test environment detection for policy selection."""

    def test_detect_ci_environment(self):
        """Test CI environment detection."""
        with patch.dict(os.environ, {"CI": "true"}, clear=True):
            result = _detect_environment()
            assert result == "ci"

    def test_detect_smoke_environment(self):
        """Test smoke test environment detection."""
        with patch.dict(os.environ, {"SMOKE": "true"}, clear=True):
            result = _detect_environment()
            assert result == "smoke"

    def test_detect_test_environment(self):
        """Test Django test environment detection."""
        with patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": "backend.settings.test"}, clear=True):
            result = _detect_environment()
            assert result == "test"

    def test_detect_unittest_environment(self):
        """Test Django unittest environment detection."""
        with patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": "backend.settings.unittest"}, clear=True):
            result = _detect_environment()
            assert result == "unittest"

    def test_detect_no_environment(self):
        """Test when no special environment is detected."""
        with patch.dict(os.environ, {}, clear=True):
            result = _detect_environment()
            assert result is None

    def test_ci_environment_priority(self):
        """Test that CI environment takes priority."""
        with patch.dict(
            os.environ, {"CI": "true", "SMOKE": "true", "DJANGO_SETTINGS_MODULE": "backend.settings.test"}, clear=True
        ):
            result = _detect_environment()
            assert result == "ci"


class TestDefaultPolicyRegistry:
    """Test default policy registry creation."""

    def test_create_default_registry(self):
        """Test creation of default policy registry."""
        registry = create_default_policy_registry()

        assert isinstance(registry, AssetPolicyRegistry)
        assert isinstance(registry.default, AssetPolicy)
        assert "replicate" in registry.processors
        assert "llm" in registry.processors
        assert "ci" in registry.environments
        assert "smoke" in registry.environments
        assert "unittest" in registry.environments
        assert "test" in registry.environments

    def test_default_policy_settings(self):
        """Test default policy settings."""
        registry = create_default_policy_registry()

        # Default policy should be conservative
        default = registry.default
        assert default.enabled is True
        assert default.max_bytes == 50 * 1024 * 1024
        assert default.timeout_s == 30
        assert default.allowed_schemes == ["https"]

    def test_replicate_policy_settings(self):
        """Test replicate-specific policy settings."""
        registry = create_default_policy_registry()

        replicate = registry.processors["replicate"]
        assert replicate.enabled is True
        assert replicate.max_bytes == 100 * 1024 * 1024  # Larger for images
        assert replicate.timeout_s == 60  # Longer timeout
        assert "image/*" in replicate.allowed_content_types
        assert "video/*" in replicate.allowed_content_types

    def test_llm_policy_settings(self):
        """Test LLM-specific policy settings."""
        registry = create_default_policy_registry()

        llm = registry.processors["llm"]
        assert llm.enabled is False  # Most LLM processors don't need downloads
        assert llm.max_bytes == 10 * 1024 * 1024
        assert llm.timeout_s == 15

    def test_ci_environment_settings(self):
        """Test CI environment policy settings."""
        registry = create_default_policy_registry()

        ci = registry.environments["ci"]
        assert ci.enabled is False  # Disabled in CI
        assert ci.max_bytes == 1 * 1024 * 1024
        assert ci.timeout_s == 10

    def test_unittest_environment_settings(self):
        """Test unittest environment policy settings."""
        registry = create_default_policy_registry()

        unittest = registry.environments["unittest"]
        assert unittest.enabled is False
        assert unittest.max_bytes == 0
        assert unittest.timeout_s == 1
        assert unittest.max_assets_per_execution == 0


class TestPolicyResolution:
    """Test policy resolution logic."""

    def test_get_default_policy(self):
        """Test getting default policy."""
        with patch.dict(os.environ, {}, clear=True):  # Clear environment to avoid unittest override
            registry = create_default_policy_registry()

            # Unknown processor should get default policy
            policy = get_asset_policy("unknown/processor@1", registry)

            assert policy.enabled is True
            assert policy.max_bytes == 50 * 1024 * 1024
            assert policy.timeout_s == 30

    def test_get_processor_specific_policy(self):
        """Test getting processor-specific policy."""
        with patch.dict(os.environ, {}, clear=True):  # Clear environment
            registry = create_default_policy_registry()

            # Replicate processor should get replicate-specific policy
            policy = get_asset_policy("replicate/generic@1", registry)

            assert policy.enabled is True
        assert policy.max_bytes == 100 * 1024 * 1024
        assert policy.timeout_s == 60

    def test_environment_override(self):
        """Test environment policy override."""
        registry = create_default_policy_registry()

        with patch.dict(os.environ, {"CI": "true"}, clear=True):
            # Even replicate processor should get CI policy in CI environment
            policy = get_asset_policy("replicate/generic@1", registry)

            assert policy.enabled is False  # CI disables downloads
            assert policy.max_bytes == 1 * 1024 * 1024
            assert policy.timeout_s == 10

    def test_policy_resolution_priority(self):
        """Test policy resolution priority order."""
        # Create custom registry to test priority
        default_policy = AssetPolicy(enabled=True, max_bytes=50 * 1024 * 1024)
        replicate_policy = AssetPolicy(enabled=True, max_bytes=100 * 1024 * 1024)
        ci_policy = AssetPolicy(enabled=False, max_bytes=1 * 1024 * 1024)

        registry = AssetPolicyRegistry(
            default=default_policy,
            processors={"replicate": replicate_policy},
            environments={"ci": ci_policy},
        )

        # Normal environment: processor-specific policy
        with patch.dict(os.environ, {}, clear=True):
            policy = get_asset_policy("replicate/generic@1", registry)
            assert policy.max_bytes == 100 * 1024 * 1024  # Replicate policy

        # CI environment: environment policy overrides
        with patch.dict(os.environ, {"CI": "true"}, clear=True):
            policy = get_asset_policy("replicate/generic@1", registry)
            assert policy.max_bytes == 1 * 1024 * 1024  # CI policy

    def test_get_asset_download_config(self):
        """Test getting AssetDownloadConfig from policy resolution."""
        with patch.dict(os.environ, {}, clear=True):  # Clear environment
            registry = create_default_policy_registry()

            config = get_asset_download_config("replicate/generic@1", registry)

            assert isinstance(config, AssetDownloadConfig)
            assert config.enabled is True
        assert config.max_bytes == 100 * 1024 * 1024
        assert config.timeout_s == 60

    def test_get_policy_with_none_registry(self):
        """Test policy resolution with None registry (uses default)."""
        with patch.dict(os.environ, {}, clear=True):  # Clear environment
            policy = get_asset_policy("replicate/generic@1", registry=None)

            # Should create default registry and resolve from it
            assert policy.enabled is True
        assert policy.max_bytes == 100 * 1024 * 1024  # Replicate policy

    def test_get_download_config_with_none_registry(self):
        """Test download config resolution with None registry."""
        config = get_asset_download_config("llm/litellm@1", registry=None)

        # Should get LLM policy (disabled by default)
        assert isinstance(config, AssetDownloadConfig)
        assert config.enabled is False


class TestPolicyEdgeCases:
    """Test edge cases in policy resolution."""

    def test_empty_processor_ref(self):
        """Test handling of empty processor reference."""
        with patch.dict(os.environ, {}, clear=True):  # Clear environment
            registry = create_default_policy_registry()

            policy = get_asset_policy("", registry)
            # Should fall back to default policy
            assert policy.enabled is True
        assert policy.max_bytes == 50 * 1024 * 1024

    def test_malformed_processor_ref(self):
        """Test handling of malformed processor reference."""
        registry = create_default_policy_registry()

        # Various malformed refs should still work
        test_cases = ["@", "/", "//", "@@@", "proc@"]

        for ref in test_cases:
            policy = get_asset_policy(ref, registry)
            # Should not crash and should return some valid policy
            assert isinstance(policy, AssetPolicy)

    def test_environment_detection_edge_cases(self):
        """Test edge cases in environment detection."""
        # Test CI detection (only "true" is supported per existing codebase pattern)
        with patch.dict(os.environ, {"CI": "true"}, clear=True):
            env = _detect_environment()
            assert env == "ci"

        # Test non-CI values
        for ci_value in ["false", "0", "", "not-true"]:
            with patch.dict(os.environ, {"CI": ci_value}, clear=True):
                env = _detect_environment()
                assert env != "ci" or env is None
