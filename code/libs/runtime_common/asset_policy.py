# libs/runtime_common/asset_policy.py
"""
Asset download policy configuration system.

Provides centralized policy management for asset downloads with:
- Global and processor-specific policies
- Environment-based policy overrides
- Security and resource limit enforcement
- Configuration validation and defaults
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Dict, List
from .asset_downloader import AssetDownloadConfig


@dataclass
class AssetPolicy:
    """Asset download policy configuration."""

    # Enable/disable asset downloads
    enabled: bool = True

    # Resource limits
    max_bytes: int = 50 * 1024 * 1024  # 50MB default
    timeout_s: int = 30
    max_assets_per_execution: int = 10

    # Security controls
    allowed_schemes: List[str] = field(default_factory=lambda: ["https"])
    blocked_domains: List[str] = field(default_factory=list)
    allowed_content_types: List[str] = field(default_factory=lambda: ["image/*", "application/json", "text/*"])

    # Naming and storage
    use_deterministic_names: bool = True
    include_source_url_metadata: bool = True

    def to_download_config(self) -> AssetDownloadConfig:
        """Convert policy to AssetDownloadConfig for downloader."""
        return AssetDownloadConfig(
            enabled=self.enabled,
            timeout_s=self.timeout_s,
            max_bytes=self.max_bytes,
            allowed_schemes=tuple(self.allowed_schemes),
        )


@dataclass
class AssetPolicyRegistry:
    """Registry of asset policies for different processors and environments."""

    # Global default policy
    default: AssetPolicy = field(default_factory=AssetPolicy)

    # Processor-specific policies
    processors: Dict[str, AssetPolicy] = field(default_factory=dict)

    # Environment overrides (CI, test, etc.)
    environments: Dict[str, AssetPolicy] = field(default_factory=dict)


def _get_processor_family(processor_ref: str) -> str:
    """Extract processor family from reference (e.g., 'replicate/generic@1' -> 'replicate')."""
    if "/" in processor_ref:
        return processor_ref.split("/")[0]
    return processor_ref.split("@")[0] if "@" in processor_ref else processor_ref


def _detect_environment() -> str | None:
    """Detect current execution environment for policy selection."""
    if os.getenv("CI") == "true":
        return "ci"
    if os.getenv("SMOKE") == "true":
        return "smoke"
    if os.getenv("DJANGO_SETTINGS_MODULE", "").endswith(".test"):
        return "test"
    if os.getenv("DJANGO_SETTINGS_MODULE", "").endswith(".unittest"):
        return "unittest"
    return None


def create_default_policy_registry() -> AssetPolicyRegistry:
    """Create default asset policy registry with sensible defaults."""

    # Default policy - conservative settings
    default_policy = AssetPolicy(
        enabled=True,
        max_bytes=50 * 1024 * 1024,  # 50MB
        timeout_s=30,
        max_assets_per_execution=10,
        allowed_schemes=["https"],
        blocked_domains=[],
        allowed_content_types=["image/*", "application/json", "text/*"],
        use_deterministic_names=True,
        include_source_url_metadata=True,
    )

    # Processor-specific policies
    processors = {
        # Replicate processors need larger limits for AI-generated images
        "replicate": AssetPolicy(
            enabled=True,
            max_bytes=100 * 1024 * 1024,  # 100MB for high-res images
            timeout_s=60,  # Longer timeout for image generation
            max_assets_per_execution=20,
            allowed_schemes=["https"],
            blocked_domains=[],
            allowed_content_types=["image/*", "video/*", "application/json"],
            use_deterministic_names=True,
            include_source_url_metadata=True,
        ),
        # LLM processors typically don't need asset downloads
        "llm": AssetPolicy(
            enabled=False,  # Most LLM processors don't generate downloadable assets
            max_bytes=10 * 1024 * 1024,  # 10MB if enabled
            timeout_s=15,
            max_assets_per_execution=5,
            allowed_schemes=["https"],
            allowed_content_types=["application/json", "text/*"],
        ),
    }

    # Environment-specific policies
    environments = {
        # CI environment - minimal downloads
        "ci": AssetPolicy(
            enabled=False,  # Disable downloads in CI by default
            max_bytes=1 * 1024 * 1024,  # 1MB if enabled
            timeout_s=10,
            max_assets_per_execution=3,
            allowed_schemes=["https"],
        ),
        # Smoke testing - disabled
        "smoke": AssetPolicy(
            enabled=False,
            max_bytes=0,
            timeout_s=5,
            max_assets_per_execution=0,
        ),
        # Unit tests - disabled
        "unittest": AssetPolicy(
            enabled=False,
            max_bytes=0,
            timeout_s=1,
            max_assets_per_execution=0,
        ),
        # Integration tests - limited
        "test": AssetPolicy(
            enabled=True,
            max_bytes=10 * 1024 * 1024,  # 10MB
            timeout_s=15,
            max_assets_per_execution=5,
            allowed_schemes=["https"],
        ),
    }

    return AssetPolicyRegistry(
        default=default_policy,
        processors=processors,
        environments=environments,
    )


def get_asset_policy(processor_ref: str, registry: AssetPolicyRegistry | None = None) -> AssetPolicy:
    """
    Get effective asset policy for a processor reference.

    Policy resolution order:
    1. Environment override (if detected)
    2. Processor-specific policy
    3. Default policy

    Args:
        processor_ref: Processor reference (e.g., 'replicate/generic@1')
        registry: Policy registry (uses default if None)

    Returns:
        Effective AssetPolicy for the processor
    """
    if registry is None:
        registry = create_default_policy_registry()

    # Start with default policy
    policy = registry.default

    # Apply processor-specific policy if available
    processor_family = _get_processor_family(processor_ref)
    if processor_family in registry.processors:
        policy = registry.processors[processor_family]

    # Apply environment override if detected
    env = _detect_environment()
    if env and env in registry.environments:
        policy = registry.environments[env]

    return policy


def get_asset_download_config(processor_ref: str, registry: AssetPolicyRegistry | None = None) -> AssetDownloadConfig:
    """
    Get AssetDownloadConfig for a processor reference.

    Convenience function that combines policy resolution with download config creation.

    Args:
        processor_ref: Processor reference (e.g., 'replicate/generic@1')
        registry: Policy registry (uses default if None)

    Returns:
        AssetDownloadConfig ready for use with download_asset()
    """
    policy = get_asset_policy(processor_ref, registry)
    return policy.to_download_config()
