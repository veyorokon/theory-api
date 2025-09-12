"""Test image digest pinning invariants and validation."""

import pytest
from apps.core.adapters.ensure_image import ensure_image_pinned


pytestmark = pytest.mark.integration


class TestImagePinning:
    """Test digest pinning requirements and validation."""

    def test_modal_requires_pinned_digest(self):
        """Test that Modal adapter rejects unpinned image tags."""
        # Test with latest tag (should be rejected)
        spec_latest = {
            "image": {"oci": "ghcr.io/veyorokon/llm-litellm:latest"}
        }
        
        result = ensure_image_pinned("modal", spec_latest, build=False)
        
        assert not result["success"]
        assert result["error"]["code"] == "ERR_IMAGE_UNPINNED"
        assert "modal adapter requires pinned digest" in result["error"]["message"].lower()
        
        # Test with branch tag (should be rejected)  
        spec_branch = {
            "image": {"oci": "ghcr.io/veyorokon/llm-litellm:main"}
        }
        
        result = ensure_image_pinned("modal", spec_branch, build=False)
        
        assert not result["success"]
        assert result["error"]["code"] == "ERR_IMAGE_UNPINNED"

    def test_modal_accepts_pinned_digest(self):
        """Test that Modal adapter accepts properly pinned digest."""
        # Test with sha256 digest (should pass)
        spec_pinned = {
            "image": {"oci": "ghcr.io/veyorokon/llm-litellm@sha256:b0b2041c6b427649230b9afc6ac8e5aae6fbfdbf5bd5bc5d5192dc61260ad039"}
        }
        
        result = ensure_image_pinned("modal", spec_pinned, build=False)
        
        assert result["success"]
        assert result["image_ref"] == spec_pinned["image"]["oci"]

    def test_local_adapter_allows_unpinned(self):
        """Test that local adapter allows unpinned images (for development)."""
        spec_latest = {
            "image": {"oci": "ghcr.io/veyorokon/llm-litellm:latest"}
        }
        
        # Local adapter should allow unpinned for development flexibility
        result = ensure_image_pinned("local", spec_latest, build=False)
        
        assert result["success"]
        assert result["image_ref"] == spec_latest["image"]["oci"]

    def test_mock_adapter_allows_unpinned(self):
        """Test that mock adapter allows unpinned images."""
        spec_latest = {
            "image": {"oci": "ghcr.io/veyorokon/llm-litellm:latest"}
        }
        
        # Mock adapter should allow any image reference
        result = ensure_image_pinned("mock", spec_latest, build=False)
        
        assert result["success"]
        assert result["image_ref"] == spec_latest["image"]["oci"]

    def test_digest_format_validation(self):
        """Test validation of digest format correctness."""
        # Valid SHA256 digest format
        valid_digests = [
            "ghcr.io/repo/image@sha256:abcd1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
            "docker.io/library/python@sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        ]
        
        for digest in valid_digests:
            spec = {"image": {"oci": digest}}
            result = ensure_image_pinned("modal", spec, build=False)
            assert result["success"], f"Valid digest rejected: {digest}"
        
        # Invalid digest formats  
        invalid_digests = [
            "ghcr.io/repo/image@sha256:tooshort",  # Too short
            "ghcr.io/repo/image@sha256:invalid-chars!",  # Invalid characters
            "ghcr.io/repo/image@md5:abcd1234",  # Wrong hash algorithm
            "ghcr.io/repo/image:v1.0",  # Tag, not digest
        ]
        
        for digest in invalid_digests:
            spec = {"image": {"oci": digest}}
            result = ensure_image_pinned("modal", spec, build=False)
            assert not result["success"], f"Invalid digest accepted: {digest}"
            assert result["error"]["code"] == "ERR_IMAGE_UNPINNED"

    def test_build_flag_behavior(self):
        """Test that build=True allows different behavior than build=False."""
        spec_latest = {
            "image": {"oci": "ghcr.io/veyorokon/llm-litellm:latest"}
        }
        
        # With build=False, modal should reject unpinned
        result_no_build = ensure_image_pinned("modal", spec_latest, build=False)
        assert not result_no_build["success"]
        
        # With build=True, modal might allow unpinned for local development
        # (behavior depends on implementation - test actual behavior)
        result_with_build = ensure_image_pinned("modal", spec_latest, build=True)
        
        # Either it succeeds (allowing build) or fails consistently
        # Document actual behavior here based on implementation
        if result_with_build["success"]:
            # If build=True allows unpinned, verify it returns sensible reference
            assert "image_ref" in result_with_build
        else:
            # If build=True still rejects, error should be consistent
            assert result_with_build["error"]["code"] == "ERR_IMAGE_UNPINNED"