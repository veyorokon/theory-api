"""Supply-chain drift detection tests for staging deployment."""

import pytest


pytestmark = [pytest.mark.staging, pytest.mark.acceptance]


class TestDriftDetection:
    """Test digest drift detection between registry and deployed processors."""

    def test_deployed_digest_matches_registry(self):
        """Test envelope digest equals pinned registry digest."""
        from apps.core.registry.loader import load_processor_spec
        from apps.core.adapters.modal_adapter import _extract_sha256
        import subprocess
        import json

        # Load registry spec for processor
        spec = load_processor_spec("llm/litellm@1")
        image_config = spec.get("image", {})

        # Get expected digest from registry
        expected_oci = image_config.get("oci")
        if not expected_oci:
            # Try platform-specific digest
            platforms = image_config.get("platforms", {})
            default_platform = image_config.get("default_platform", "amd64")
            expected_oci = platforms.get(default_platform)

        assert expected_oci, "No pinned OCI reference found in registry"
        assert "@sha256:" in expected_oci, f"Registry OCI not pinned: {expected_oci}"

        # Extract expected digest
        expected_digest = _extract_sha256(expected_oci)
        assert expected_digest, f"Could not extract digest from {expected_oci}"

        # Get actual digest from deployment
        result = subprocess.run(
            [
                "python",
                "manage.py",
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "modal",
                "--mode",
                "mock",
                "--write-prefix",
                "/artifacts/outputs/drift-test/{execution_id}/",
                "--inputs-json",
                '{"schema":"v1","params":{"messages":[{"role":"user","content":"drift test"}]}}',
                "--json",
            ],
            cwd="code",
            capture_output=True,
            text=True,
            timeout=60,
            env={"DJANGO_SETTINGS_MODULE": "backend.settings.unittest", "MODAL_ENVIRONMENT": "staging"},
        )

        assert result.returncode == 0, f"Processor execution failed: {result.stderr}"

        # Parse envelope
        envelope = json.loads(result.stdout.splitlines()[0])
        assert envelope["status"] == "success", f"Processor returned error: {envelope}"

        # Extract actual digest from envelope
        actual_digest = _extract_sha256(envelope["meta"]["image_digest"])
        assert actual_digest, f"No digest in envelope meta: {envelope['meta']}"

        # Compare normalized digests
        assert expected_digest == actual_digest, (
            f"Digest drift detected: registry={expected_digest}, deployed={actual_digest}"
        )

    def test_drift_detection_mismatch_simulation(self):
        """Test adapter detects digest mismatch (simulated via mock)."""
        from apps.core.adapters.modal_adapter import ModalAdapter
        from unittest.mock import patch, MagicMock

        # Mock a mismatch scenario
        with (
            patch("apps.core.registry.loader.load_processor_spec") as mock_load_spec,
            patch("modal.lookup") as mock_lookup,
            patch("requests.post") as mock_post,
        ):
            # Mock registry with one digest
            mock_load_spec.return_value = {
                "image": {
                    "oci": "ghcr.io/test/repo@sha256:expected123456789012345678901234567890123456789012345678901234567890"
                }
            }

            # Mock Modal response with different digest
            mock_function = MagicMock()
            mock_function.web_url = "https://test.modal.run"

            mock_app = MagicMock()
            mock_app.__getitem__.return_value = mock_function
            mock_lookup.return_value = mock_app

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "status": "success",
                "execution_id": "drift-test",
                "outputs": [],
                "meta": {"image_digest": "sha256:actual789012345678901234567890123456789012345678901234567890123456"},
            }
            mock_post.return_value = mock_response

            adapter = ModalAdapter()

            payload = {
                "execution_id": "drift-test",
                "write_prefix": "/artifacts/outputs/drift/",
                "schema": "v1",
                "mode": "mock",
                "params": {"messages": [{"role": "user", "content": "drift test"}]},
            }

            import os

            os.environ.update({"MODAL_ENVIRONMENT": "staging", "BRANCH": "staging", "USER": "staging"})

            result = adapter.invoke(processor_ref="llm/litellm@1", payload=payload, timeout_s=60)

            # Should detect drift and return error
            assert result["status"] == "error"
            assert "ERR_REGISTRY_MISMATCH" in result["error"]["code"] or "digest" in result["error"]["message"].lower()

    def test_digest_normalization_robustness(self):
        """Test digest comparison handles different formats correctly."""
        from apps.core.adapters.modal_adapter import _extract_sha256

        test_cases = [
            # Full OCI reference
            {"input": "ghcr.io/user/repo@sha256:abc123def456", "expected": "sha256:abc123def456"},
            # Digest only
            {"input": "sha256:abc123def456", "expected": "sha256:abc123def456"},
            # Mixed case (should normalize)
            {"input": "ghcr.io/user/repo@SHA256:ABC123DEF456", "expected": "sha256:abc123def456"},
            # Invalid formats
            {"input": "ghcr.io/user/repo:latest", "expected": ""},
            {
                "input": "sha256:pending",
                "expected": "",  # Special case for placeholder
            },
            {"input": "", "expected": ""},
        ]

        for case in test_cases:
            result = _extract_sha256(case["input"])
            assert result == case["expected"], f"Input {case['input']} produced {result}, expected {case['expected']}"

    def test_drift_audit_command_integration(self):
        """Test drift audit command detects mismatches."""
        # This would integrate with the drift_audit.py script
        import subprocess

        # Run drift audit (should pass in staging if properly deployed)
        result = subprocess.run(
            ["python", "-c", "from scripts.drift_audit import main; main()"],
            cwd="code",
            capture_output=True,
            text=True,
            timeout=120,
            env={"DJANGO_SETTINGS_MODULE": "backend.settings.unittest"},
        )

        # In staging, this should either pass (no drift) or fail gracefully
        # We can't guarantee the state, but we can verify the command works
        assert result.returncode in [0, 1], f"Drift audit command crashed: {result.stderr}"

        if result.returncode == 1:
            # Drift detected - this is a valid outcome in staging
            assert "drift" in result.stderr.lower() or "mismatch" in result.stderr.lower()

    def test_registry_digest_format_validation(self):
        """Test registry contains properly formatted digests."""
        from apps.core.registry.loader import load_processor_spec

        spec = load_processor_spec("llm/litellm@1")
        image_config = spec.get("image", {})

        # Check OCI field format
        oci = image_config.get("oci")
        if oci:
            assert "@sha256:" in oci, f"OCI reference not properly pinned: {oci}"
            digest_part = oci.split("@sha256:", 1)[1]
            assert len(digest_part) == 64, f"Invalid digest length in {oci}"
            assert all(c in "0123456789abcdef" for c in digest_part), f"Invalid digest format in {oci}"

        # Check platform digests
        platforms = image_config.get("platforms", {})
        for platform, platform_oci in platforms.items():
            assert "@sha256:" in platform_oci, f"Platform {platform} OCI not pinned: {platform_oci}"
            digest_part = platform_oci.split("@sha256:", 1)[1]
            assert len(digest_part) == 64, f"Invalid digest length for {platform}: {platform_oci}"
            assert all(c in "0123456789abcdef" for c in digest_part), (
                f"Invalid digest format for {platform}: {platform_oci}"
            )

    def test_supply_chain_integrity_end_to_end(self):
        """Test complete supply-chain integrity from registry to execution."""
        from apps.core.registry.loader import load_processor_spec
        from apps.core.adapters.modal_adapter import _extract_sha256
        import subprocess
        import json

        # 1. Verify registry has pinned digest
        spec = load_processor_spec("llm/litellm@1")
        image_config = spec.get("image", {})

        expected_oci = image_config.get("oci")
        if not expected_oci:
            platforms = image_config.get("platforms", {})
            default_platform = image_config.get("default_platform", "amd64")
            expected_oci = platforms.get(default_platform)

        assert expected_oci and "@sha256:" in expected_oci, (
            "Registry must contain pinned digest for supply-chain integrity"
        )

        expected_digest = _extract_sha256(expected_oci)

        # 2. Execute via adapter and verify digest matches
        result = subprocess.run(
            [
                "python",
                "manage.py",
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "modal",
                "--mode",
                "mock",
                "--write-prefix",
                "/artifacts/outputs/integrity-test/{execution_id}/",
                "--inputs-json",
                '{"schema":"v1","params":{"messages":[{"role":"user","content":"integrity test"}]}}',
                "--json",
            ],
            cwd="code",
            capture_output=True,
            text=True,
            timeout=60,
            env={"DJANGO_SETTINGS_MODULE": "backend.settings.unittest", "MODAL_ENVIRONMENT": "staging"},
        )

        assert result.returncode == 0, f"Supply-chain execution failed: {result.stderr}"

        envelope = json.loads(result.stdout.splitlines()[0])
        assert envelope["status"] == "success"

        actual_digest = _extract_sha256(envelope["meta"]["image_digest"])

        # 3. Verify end-to-end digest integrity
        assert expected_digest == actual_digest, (
            f"Supply-chain integrity violation: registry={expected_digest}, execution={actual_digest}"
        )
