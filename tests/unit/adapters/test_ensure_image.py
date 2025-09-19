"""Unit tests for ensure_image functionality."""

import pytest
from unittest.mock import patch, MagicMock
from apps.core.adapters.ensure_image import ensure_image, is_valid_sha256_digest


class TestDigestValidation:
    """Test digest validation helper."""

    def test_valid_digest(self):
        """Test valid SHA256 digest recognition."""
        valid_ref = "ghcr.io/user/repo@sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        assert is_valid_sha256_digest(valid_ref) is True

    def test_pending_placeholder(self):
        """Test pending placeholder is not considered pinned."""
        pending_ref = "ghcr.io/user/repo@sha256:pending"
        assert is_valid_sha256_digest(pending_ref) is False

    def test_short_digest(self):
        """Test short digest is not considered valid."""
        short_ref = "ghcr.io/user/repo@sha256:abc123"
        assert is_valid_sha256_digest(short_ref) is False

    def test_no_digest(self):
        """Test ref without digest is not pinned."""
        no_digest_ref = "ghcr.io/user/repo:latest"
        assert is_valid_sha256_digest(no_digest_ref) is False

    def test_none_ref(self):
        """Test None reference is not pinned."""
        assert is_valid_sha256_digest("") is False


class TestEnsureImageLogic:
    """Test ensure_image prioritization logic."""

    @patch("apps.core.adapters.ensure_image._build_local_image")
    def test_force_build_takes_priority(self, mock_build):
        """Test force_build bypasses everything else."""
        mock_build.return_value = "local-build:tag"

        proc_spec = {
            "image": {
                "oci": "ghcr.io/user/repo@sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
            },
            "build": {"context": ".", "dockerfile": "Dockerfile"},
        }

        result = ensure_image(proc_spec, adapter="local", force_build=True)

        assert result == "local-build:tag"
        mock_build.assert_called_once()

    @patch("apps.core.adapters.ensure_image._build_local_image")
    def test_build_with_pending_digest(self, mock_build):
        """Test build is used when OCI has pending placeholder."""
        mock_build.return_value = "local-build:tag"

        proc_spec = {
            "image": {"oci": "ghcr.io/user/repo@sha256:pending"},
            "build": {"context": ".", "dockerfile": "Dockerfile"},
        }

        result = ensure_image(proc_spec, adapter="local", build=True)

        assert result == "local-build:tag"
        mock_build.assert_called_once()

    @pytest.mark.integration
    @patch("apps.core.adapters.ensure_image._ensure_image_pulled")
    def test_valid_digest_is_pulled(self, mock_pull):
        """Test valid digest is pulled instead of building."""
        mock_pull.return_value = None

        valid_digest = "ghcr.io/user/repo@sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        proc_spec = {"image": {"oci": valid_digest}, "build": {"context": ".", "dockerfile": "Dockerfile"}}

        result = ensure_image(proc_spec, adapter="local", build=True)

        assert result == valid_digest
        mock_pull.assert_called_once_with(valid_digest)

    @pytest.mark.integration
    def test_no_valid_options_raises_error(self):
        """Test error when no valid image options available."""
        proc_spec = {
            "image": {"oci": "ghcr.io/user/repo@sha256:pending"},
            # No build spec
        }

        with pytest.raises(RuntimeError, match="ERR_IMAGE_UNPINNED"):
            ensure_image(proc_spec, adapter="local", build=True)

    @patch("apps.core.adapters.ensure_image._ensure_image_pulled")
    def test_remote_adapter_requires_pinned(self, mock_pull):
        """Test remote adapters require pinned digests."""
        mock_pull.return_value = None

        valid_digest = "ghcr.io/user/repo@sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        proc_spec = {"image": {"oci": valid_digest}}

        result = ensure_image(proc_spec, adapter="modal")

        assert result == valid_digest
        mock_pull.assert_called_once_with(valid_digest)

    def test_remote_adapter_pending_digest_fails(self):
        """Test remote adapters fail with pending digest."""
        proc_spec = {"image": {"oci": "ghcr.io/user/repo@sha256:pending"}}

        with pytest.raises(RuntimeError, match="Remote adapters require a pinned image digest"):
            ensure_image(proc_spec, adapter="modal")
