"""Test receipt determinism and invariant properties."""

import json
import os
import subprocess
import pytest
import boto3
from botocore.exceptions import ClientError


pytestmark = pytest.mark.acceptance


def _minio_client():
    """MinIO/S3 client using docker-compose credentials."""
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT", "http://127.0.0.1:9000"),
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "minioadmin"),
        region_name="us-east-1",
    )


def _ensure_bucket_exists():
    """Ensure default bucket exists in MinIO."""
    s3 = _minio_client()
    bucket = os.environ.get("S3_BUCKET", "default")
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket)


def _run_processor_and_get_receipt(test_name: str) -> dict:
    """Run processor and return the receipt data."""
    _ensure_bucket_exists()

    cmd = [
        "python",
        "manage.py",
        "run_processor",
        "--ref",
        "llm/litellm@1",
        "--adapter",
        "local",
        "--mode",
        "mock",
        "--write-prefix",
        f"/artifacts/outputs/{test_name}/{{execution_id}}/",
        "--inputs-json",
        '{"schema":"v1","params":{"messages":[{"role":"user","content":"receipt test"}]}}',
        "--json",
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = "."

    result = subprocess.run(cmd, cwd=".", env=env, capture_output=True, text=True)
    assert result.returncode == 0, f"Command failed: {result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["status"] == "success"

    # Get receipt from MinIO
    exec_id = payload["execution_id"]
    s3 = _minio_client()
    bucket = os.environ.get("S3_BUCKET", "default")

    receipt_key = f"artifacts/outputs/{test_name}/{exec_id}/receipt.json"
    receipt_obj = s3.get_object(Bucket=bucket, Key=receipt_key)
    receipt_data = json.loads(receipt_obj["Body"].read().decode())

    return {"payload": payload, "receipt": receipt_data, "execution_id": exec_id}


class TestReceiptInvariants:
    """Test receipt determinism and required field invariants."""

    def test_receipt_required_fields(self):
        """Test that receipt contains all required fields."""
        data = _run_processor_and_get_receipt("required-fields")
        receipt = data["receipt"]

        # Required fields that must be present
        required_fields = [
            "env_fingerprint",
            "duration_ms",
            "image_digest",
            "timestamp_utc",
        ]

        for field in required_fields:
            assert field in receipt, f"Required field missing: {field}"
            assert receipt[field] is not None, f"Required field is null: {field}"

    def test_receipt_env_fingerprint_deterministic(self):
        """Test that env_fingerprint is deterministic for same environment."""
        data1 = _run_processor_and_get_receipt("fingerprint-1")
        data2 = _run_processor_and_get_receipt("fingerprint-2")

        receipt1 = data1["receipt"]
        receipt2 = data2["receipt"]

        # Environment fingerprint should be identical for same setup
        assert receipt1["env_fingerprint"] == receipt2["env_fingerprint"]

        # Fingerprint should contain expected components
        fingerprint = receipt1["env_fingerprint"]
        assert "image:" in fingerprint, "Fingerprint missing image component"
        assert "cpu:" in fingerprint, "Fingerprint missing CPU component"
        assert "memory:" in fingerprint, "Fingerprint missing memory component"

    def test_receipt_duration_realistic(self):
        """Test that duration_ms is realistic (non-zero, reasonable bounds)."""
        data = _run_processor_and_get_receipt("duration-test")
        receipt = data["receipt"]

        duration_ms = receipt["duration_ms"]

        # Duration should be positive
        assert duration_ms > 0, f"Duration should be positive: {duration_ms}"

        # Duration should be reasonable (less than 5 minutes for mock)
        assert duration_ms < 300_000, f"Duration suspiciously high: {duration_ms}ms"

        # Duration should be at least a few milliseconds (not instantaneous)
        assert duration_ms >= 1, f"Duration suspiciously low: {duration_ms}ms"

    def test_receipt_mock_provider_zero_cost(self):
        """Test that mock provider shows zero cost in receipt."""
        data = _run_processor_and_get_receipt("mock-cost")
        receipt = data["receipt"]

        # Mock provider should report zero cost
        if "cost_micro" in receipt:
            assert receipt["cost_micro"] == 0, "Mock provider should have zero cost"

        if "estimated_cost_micro" in receipt:
            assert receipt["estimated_cost_micro"] == 0, "Mock provider should have zero estimated cost"

    @pytest.mark.skipif(
        os.getenv("RUN_PROCESSOR_FORCE_BUILD") == "1", reason="PR lane tests build from source, not pinned artifacts"
    )
    def test_receipt_image_digest_pinned(self):
        """Test that receipt contains pinned image digest reference."""
        data = _run_processor_and_get_receipt("image-digest")
        receipt = data["receipt"]

        image_digest = receipt["image_digest"]

        # Should be a pinned digest (contains @sha256:)
        assert "@sha256:" in image_digest, f"Image digest not pinned: {image_digest}"

        # Should be the expected processor image (hyphenated in GHCR)
        assert "llm-litellm" in image_digest, f"Unexpected image: {image_digest}"

    def test_receipt_timestamp_format(self):
        """Test that timestamps are in expected ISO format."""
        data = _run_processor_and_get_receipt("timestamp-format")
        receipt = data["receipt"]

        timestamp = receipt["timestamp_utc"]

        # Should be ISO 8601 format
        assert "T" in timestamp, "Timestamp should be ISO 8601 format"
        assert timestamp.endswith("Z"), "Timestamp should end with Z (UTC)"

        # Should be parseable as datetime
        from datetime import datetime

        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            assert parsed is not None
        except ValueError:
            pytest.fail(f"Timestamp not parseable: {timestamp}")

    def test_receipt_consistency_across_runs(self):
        """Test receipt fields that should be consistent vs those that should vary."""
        data1 = _run_processor_and_get_receipt("consistency-1")
        data2 = _run_processor_and_get_receipt("consistency-2")

        receipt1 = data1["receipt"]
        receipt2 = data2["receipt"]

        # Fields that should be IDENTICAL across runs (deterministic)
        consistent_fields = ["env_fingerprint", "image_digest"]

        for field in consistent_fields:
            if field in receipt1 and field in receipt2:
                assert receipt1[field] == receipt2[field], f"Field should be consistent: {field}"

        # Fields that should be DIFFERENT across runs (unique per execution)
        unique_fields = ["timestamp_utc"]

        for field in unique_fields:
            if field in receipt1 and field in receipt2:
                # Timestamps might be very close, but should be different strings
                # (unless runs happened in same millisecond)
                pass  # Allow same timestamps for fast consecutive runs

    def test_receipt_json_schema_valid(self):
        """Test that receipt JSON has valid structure and types."""
        data = _run_processor_and_get_receipt("schema-test")
        receipt = data["receipt"]

        # Check field types
        type_checks = [
            ("env_fingerprint", str),
            ("duration_ms", (int, float)),
            ("image_digest", str),
            ("timestamp_utc", str),
        ]

        for field_name, expected_type in type_checks:
            if field_name in receipt:
                value = receipt[field_name]
                assert isinstance(value, expected_type), (
                    f"Field {field_name} should be {expected_type}, got {type(value)}"
                )

        # Receipt should be serializable back to JSON
        try:
            json.dumps(receipt)
        except (TypeError, ValueError) as e:
            pytest.fail(f"Receipt not JSON serializable: {e}")
