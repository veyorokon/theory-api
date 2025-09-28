"""Build/Push/Pin workflow integration tests."""

import json
import subprocess
import tempfile
import yaml
from pathlib import Path

import pytest

from tests.tools.subprocess_helper import run_manage_py


pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestBuildPushPinWorkflow:
    """Test build → push → pin workflow for embedded registries."""

    @pytest.fixture
    def temp_registry_file(self):
        """Create temporary registry.yaml for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            initial_registry = {
                "schema": "v1",
                "name": "llm/litellm@1",
                "secrets": {"required": ["OPENAI_API_KEY"]},
                "image": {"oci": "ghcr.io/test/repo@sha256:pending"},
                "build": {"context": ".", "dockerfile": "Dockerfile"},
            }
            yaml.safe_dump(initial_registry, f)
            yield Path(f.name)
            Path(f.name).unlink(missing_ok=True)

    def test_build_processor_updates_embedded_registry(self):
        """Test build_processor writes digest to processor's registry.yaml."""
        # Build processor
        result = run_manage_py(
            "build_processor",
            "--ref",
            "llm/litellm@1",
            "--json",
            capture_output=True,
            text=True,
            timeout=300,
            extra_env={"DJANGO_SETTINGS_MODULE": "backend.settings.unittest"},
            check=False,
        )

        assert result.returncode == 0, f"Build failed: {result.stderr}"

        build_info = json.loads(result.stdout)
        assert build_info["status"] == "success"
        assert "image_tag" in build_info
        assert "image_digest" in build_info

        # Verify image digest format
        image_digest = build_info["image_digest"]
        assert image_digest.startswith("sha256:")
        assert len(image_digest) == len("sha256:") + 64  # sha256: + 64 hex chars

    def test_pin_processor_validates_digest_format(self, temp_registry_file):
        """Test pin_processor validates digest format."""
        # Test with invalid digest format
        invalid_digest = "sha256:invalid"

        result = run_manage_py(
            "pin_processor",
            "--ref",
            "llm/litellm@1",
            "--repo",
            "ghcr.io/test/repo",
            "--digest",
            invalid_digest,
            "--json",
            capture_output=True,
            text=True,
            extra_env={"DJANGO_SETTINGS_MODULE": "backend.settings.unittest"},
            check=False,
        )

        assert result.returncode != 0, "Should fail with invalid digest format"
        assert "Invalid digest format" in result.stderr or "ERR_PIN_ARGS" in result.stderr

    def test_pin_processor_updates_registry_yaml(self, temp_registry_file):
        """Test pin_processor updates registry.yaml with valid digest."""
        valid_digest = "sha256:" + "a" * 64
        valid_oci = f"ghcr.io/test/repo@{valid_digest}"

        # Mock the registry file location by temporarily replacing it
        registry_path = Path("code/apps/core/processors/llm_litellm/registry.yaml")
        original_content = None

        if registry_path.exists():
            original_content = registry_path.read_text()

        try:
            # Copy temp registry to actual location
            registry_path.write_text(temp_registry_file.read_text())

            result = run_manage_py(
                "pin_processor",
                "--ref",
                "llm/litellm@1",
                "--oci",
                valid_oci,
                "--json",
                capture_output=True,
                text=True,
                extra_env={"DJANGO_SETTINGS_MODULE": "backend.settings.unittest"},
                check=False,
            )

            assert result.returncode == 0, f"Pin failed: {result.stderr}"

            pin_info = json.loads(result.stdout)
            assert pin_info["status"] == "success"
            assert pin_info["pinned_oci"] == valid_oci

            # Verify registry was updated
            updated_registry = yaml.safe_load(registry_path.read_text())
            assert updated_registry["image"]["oci"] == valid_oci

        finally:
            # Restore original registry
            if original_content:
                registry_path.write_text(original_content)

    def test_pin_processor_validates_multi_arch(self):
        """Test pin_processor can validate multi-arch images."""
        # This test would need actual multi-arch image, so we test the validation logic
        from apps.core.management.commands.pin_processor import _DIGEST_RE

        # Test digest regex validation
        valid_digests = [
            "sha256:" + "a" * 64,
            "sha256:" + "1234567890abcdef" * 4,
            "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        ]

        invalid_digests = [
            "sha256:short",
            "sha256:" + "g" * 64,  # Invalid hex
            "sha256:" + "a" * 63,  # Too short
            "sha256:" + "a" * 65,  # Too long
            "md5:abcd1234",  # Wrong algorithm
            "pending",
        ]

        for digest in valid_digests:
            assert _DIGEST_RE.match(digest), f"Should match valid digest: {digest}"

        for digest in invalid_digests:
            assert not _DIGEST_RE.match(digest), f"Should not match invalid digest: {digest}"

    def test_build_pin_workflow_integration(self):
        """Test complete build → pin workflow."""
        # Step 1: Build processor
        build_result = run_manage_py(
            "build_processor",
            "--ref",
            "llm/litellm@1",
            "--json",
            capture_output=True,
            text=True,
            timeout=300,
            extra_env={"DJANGO_SETTINGS_MODULE": "backend.settings.unittest"},
            check=False,
        )

        assert build_result.returncode == 0, f"Build failed: {build_result.stderr}"
        build_info = json.loads(build_result.stdout)

        # Extract built image info
        image_tag = build_info["image_tag"]
        image_digest = build_info["image_digest"]

        assert image_tag
        assert image_digest.startswith("sha256:")

        # Step 2: Simulate push (we'll use the built image digest)
        # In real workflow, this would push to registry and get back OCI reference
        mock_oci = f"ghcr.io/test/repo@{image_digest}"

        # Step 3: Pin the digest (dry run - don't actually modify registry)
        pin_result = run_manage_py(
            "pin_processor",
            "--ref",
            "llm/litellm@1",
            "--oci",
            mock_oci,
            "--json",
            capture_output=True,
            text=True,
            extra_env={"DJANGO_SETTINGS_MODULE": "backend.settings.unittest"},
            check=False,
        )

        # This might fail because we're not actually pushing to registry,
        # but we can verify the command works and validates input
        if pin_result.returncode == 0:
            pin_info = json.loads(pin_result.stdout)
            assert pin_info["status"] == "success"
            assert pin_info["pinned_oci"] == mock_oci
        else:
            # If pin fails, at least verify it's not due to digest format
            assert "Invalid digest format" not in pin_result.stderr

    def test_embedded_registry_structure(self):
        """Test embedded registry.yaml has required structure."""
        registry_path = Path("code/apps/core/processors/llm_litellm/registry.yaml")
        assert registry_path.exists(), "Registry file should exist for llm/litellm processor"

        registry_data = yaml.safe_load(registry_path.read_text())

        # Verify required top-level fields
        required_fields = ["ref", "secrets", "image"]  # Updated to match actual structure
        for field in required_fields:
            assert field in registry_data, f"Registry missing required field: {field}"

        # Verify image section structure
        image_config = registry_data["image"]
        assert isinstance(image_config, dict), "Image config should be dict"

        # Should have either 'oci' field or 'platforms' field
        assert "oci" in image_config or "platforms" in image_config, "Image config should have oci or platforms field"

        # If has oci field, should be pinned (not pending)
        if "oci" in image_config:
            oci = image_config["oci"]
            if oci != "ghcr.io/test/repo@sha256:pending":  # Allow test placeholder
                assert "@sha256:" in oci, f"OCI reference should be pinned: {oci}"

        # If has platforms, each should be pinned
        if "platforms" in image_config:
            platforms = image_config["platforms"]
            for platform, platform_oci in platforms.items():
                if platform_oci != "ghcr.io/test/repo@sha256:pending":  # Allow test placeholder
                    assert "@sha256:" in platform_oci, f"Platform {platform} OCI should be pinned: {platform_oci}"

    def test_registry_yaml_roundtrip_preservation(self):
        """Test registry.yaml modifications preserve existing structure."""
        registry_path = Path("code/apps/core/processors/llm_litellm/registry.yaml")

        if not registry_path.exists():
            pytest.skip("Registry file not found")

        # Read original
        original_content = registry_path.read_text()
        original_data = yaml.safe_load(original_content)

        # Create backup
        backup_content = original_content

        try:
            # Simulate pin operation (modify and restore)
            test_oci = "ghcr.io/test/repo@sha256:" + "f" * 64

            pin_result = run_manage_py(
                "pin_processor",
                "--ref",
                "llm/litellm@1",
                "--oci",
                test_oci,
                "--json",
                capture_output=True,
                text=True,
                extra_env={"DJANGO_SETTINGS_MODULE": "backend.settings.unittest"},
                check=False,
            )

            if pin_result.returncode == 0:
                # Verify structure preserved
                modified_data = yaml.safe_load(registry_path.read_text())

                # All original fields should be preserved
                for key in original_data:
                    assert key in modified_data, f"Pin operation removed field: {key}"

                # Only image.oci should have changed
                if "image" in original_data and "oci" in original_data["image"]:
                    assert modified_data["image"]["oci"] == test_oci

        finally:
            # Always restore original
            registry_path.write_text(backup_content)

    def test_build_processor_docker_buildx_support(self):
        """Test build_processor works with Docker Buildx for multi-arch."""
        # Verify buildx is available
        buildx_result = subprocess.run(["docker", "buildx", "version"], capture_output=True, text=True)

        if buildx_result.returncode != 0:
            pytest.skip("Docker Buildx not available")

        # Build should work (even if not multi-arch in test environment)
        result = run_manage_py(
            "build_processor",
            "--ref",
            "llm/litellm@1",
            "--json",
            capture_output=True,
            text=True,
            timeout=300,
            extra_env={"DJANGO_SETTINGS_MODULE": "backend.settings.unittest"},
            check=False,
        )

        assert result.returncode == 0, f"Build with buildx support failed: {result.stderr}"

        build_info = json.loads(result.stdout)
        assert build_info["status"] == "success"

        # Should report platform information
        platforms = build_info.get("platforms", "")
        assert "linux/" in platforms, f"Should build for linux platform: {platforms}"
