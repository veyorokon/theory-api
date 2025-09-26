"""Digest verification contract tests for supply-chain lanes."""

import pytest
from apps.core.registry.loader import load_processor_spec


@pytest.mark.contracts
@pytest.mark.supplychain
class TestDigestVerification:
    """Test digest verification patterns for supply-chain integrity."""

    def test_registry_has_pinned_digest(self):
        """Test that processor registry contains pinned @sha256: digest."""
        spec = load_processor_spec("llm/litellm@1")

        # Check for pinned image reference
        image_config = spec.get("image", {})
        assert image_config, "Processor spec missing image section"

        # Look for digest in either oci field or platforms
        oci = image_config.get("oci")
        platforms = image_config.get("platforms", {})

        has_digest = False
        if oci and "@sha256:" in oci:
            has_digest = True
        elif platforms:
            for _platform, digest_ref in platforms.items():
                if "@sha256:" in digest_ref:
                    has_digest = True
                    break

        assert has_digest, f"No pinned digest found in image config: {image_config}"

    def test_digest_format_validation(self):
        """Test that digests follow expected format."""
        spec = load_processor_spec("llm/litellm@1")
        image_config = spec.get("image", {})

        def validate_digest_format(ref: str) -> bool:
            """Validate OCI reference has proper digest format."""
            if "@sha256:" not in ref:
                return False
            digest_part = ref.split("@sha256:", 1)[1]
            return len(digest_part) == 64 and all(c in "0123456789abcdef" for c in digest_part)

        # Check oci field
        oci = image_config.get("oci")
        if oci:
            assert validate_digest_format(oci), f"Invalid digest format in oci: {oci}"

        # Check platform digests
        platforms = image_config.get("platforms", {})
        for platform, digest_ref in platforms.items():
            # Allow REPLACE_ placeholders in development
            if "REPLACE_" in digest_ref:
                continue
            assert validate_digest_format(digest_ref), f"Invalid digest format for {platform}: {digest_ref}"

    def test_digest_normalization_helper(self):
        """Test helper function for normalizing digest comparisons."""
        from apps.core.adapters.base_http_adapter import _normalize_digest

        # Test various input formats
        test_cases = [
            ("ghcr.io/org/repo@sha256:abc123def456", "sha256:abc123def456"),
            ("sha256:abc123def456", "sha256:abc123def456"),
            ("abc123def456", None),  # No sha256 prefix
            ("", None),
            ("ghcr.io/org/repo:latest", None),  # No digest
        ]

        for input_ref, expected in test_cases:
            result = _normalize_digest(input_ref)
            assert result == expected, f"Failed for input {input_ref}: got {result}, expected {expected}"

    @pytest.mark.staging
    def test_envelope_digest_matches_pinned(self):
        """Test that envelope meta.image_digest matches pinned registry digest."""
        # This test would run after deployment to verify digest consistency
        # For now, just validate the comparison logic exists
        spec = load_processor_spec("llm/litellm@1")
        image_config = spec.get("image", {})

        # Get expected digest from registry
        expected_oci = image_config.get("oci")
        if not expected_oci:
            # Try default platform
            platforms = image_config.get("platforms", {})
            default_platform = image_config.get("default_platform", "amd64")
            expected_oci = platforms.get(default_platform)

        assert expected_oci, "No expected OCI reference found in registry"
        assert "@sha256:" in expected_oci, f"Expected digest format not found: {expected_oci}"

        # Extract expected digest
        from apps.core.adapters.base_http_adapter import _normalize_digest

        expected_digest = _normalize_digest(expected_oci)
        assert expected_digest, f"Could not extract digest from {expected_oci}"

        # Mock envelope response (in real test, this would come from adapter)
        mock_envelope = {"status": "success", "meta": {"image_digest": expected_digest}}

        # Verify digests match
        envelope_digest = _normalize_digest(mock_envelope["meta"]["image_digest"])
        assert envelope_digest == expected_digest, "Envelope digest doesn't match pinned registry digest"

    def test_drift_detection_logic(self):
        """Test logic for detecting digest drift between registry and deployment."""
        from apps.core.adapters.base_http_adapter import _normalize_digest

        # Test cases for drift detection
        registry_digest = "sha256:abc123def456"

        # Matching cases (no drift)
        matching_cases = [
            "sha256:abc123def456",
            "ghcr.io/org/repo@sha256:abc123def456",
        ]

        for envelope_digest in matching_cases:
            normalized_registry = _normalize_digest(registry_digest)
            normalized_envelope = _normalize_digest(envelope_digest)
            assert normalized_registry == normalized_envelope, f"Should match: {envelope_digest}"

        # Non-matching cases (drift detected)
        drift_cases = [
            "sha256:different123",
            "ghcr.io/org/repo@sha256:different123",
            "sha256:pending",
            "",
        ]

        for envelope_digest in drift_cases:
            normalized_registry = _normalize_digest(registry_digest)
            normalized_envelope = _normalize_digest(envelope_digest)
            assert normalized_registry != normalized_envelope, f"Should detect drift: {envelope_digest}"
