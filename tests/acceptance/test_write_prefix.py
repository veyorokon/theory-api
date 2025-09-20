"""Test write-prefix templating and execution uniqueness."""

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


def _run_processor_with_template(template_prefix: str) -> dict:
    """Run processor with templated write prefix."""
    cmd = [
        "python",
        "manage.py",
        "run_processor",
        "--ref",
        "llm/litellm@1",
        "--adapter",
        "local",
        "--write-prefix",
        template_prefix,
        "--inputs-json",
        '{"messages":[{"role":"user","content":"test templating"}]}',
        "--json",
    ]

    env = os.environ.copy()
    env["LLM_PROVIDER"] = "mock"
    env["PYTHONPATH"] = "."

    result = subprocess.run(cmd, cwd=".", env=env, capture_output=True, text=True)
    assert result.returncode == 0, f"Command failed: {result.stderr}"

    return json.loads(result.stdout)


class TestWritePrefixTemplating:
    """Test write-prefix template expansion and uniqueness."""

    def test_execution_id_templating_expansion(self):
        """Test that {execution_id} template gets expanded properly."""
        _ensure_bucket_exists()

        template = "/artifacts/outputs/template-test/{execution_id}/"
        payload = _run_processor_with_template(template)

        assert payload["status"] == "success"
        exec_id = payload["execution_id"]

        # Verify execution_id is a valid identifier
        assert exec_id
        assert isinstance(exec_id, str)
        assert len(exec_id) > 0

        # Check that actual paths contain the expanded execution_id
        for output in payload["outputs"]:
            path = output["path"]
            assert f"/artifacts/outputs/template-test/{exec_id}/" in path
            assert "{execution_id}" not in path  # Should be expanded

    def test_concurrent_runs_no_collision(self):
        """Test that concurrent runs get different execution IDs and don't collide."""
        _ensure_bucket_exists()

        template = "/artifacts/outputs/concurrent-test/{execution_id}/"

        # Run processor twice
        payload1 = _run_processor_with_template(template)
        payload2 = _run_processor_with_template(template)

        # Both should succeed
        assert payload1["status"] == "success"
        assert payload2["status"] == "success"

        exec_id1 = payload1["execution_id"]
        exec_id2 = payload2["execution_id"]

        # Execution IDs must be different
        assert exec_id1 != exec_id2

        # Verify both sets of objects exist in MinIO
        s3 = _minio_client()
        bucket = os.environ.get("S3_BUCKET", "default")

        # Check first run objects
        response_key1 = f"artifacts/outputs/concurrent-test/{exec_id1}/response.json"
        s3.get_object(Bucket=bucket, Key=response_key1)  # Should not raise

        # Check second run objects
        response_key2 = f"artifacts/outputs/concurrent-test/{exec_id2}/response.json"
        s3.get_object(Bucket=bucket, Key=response_key2)  # Should not raise

        # Keys should be different
        assert response_key1 != response_key2

    def test_nested_template_paths(self):
        """Test complex nested template paths work correctly."""
        _ensure_bucket_exists()

        # Test nested templating with execution_id in multiple places
        template = "/artifacts/outputs/{execution_id}/nested/{execution_id}/data/"
        payload = _run_processor_with_template(template)

        assert payload["status"] == "success"
        exec_id = payload["execution_id"]

        # Verify paths have execution_id expanded in both locations
        for output in payload["outputs"]:
            path = output["path"]
            expected_pattern = f"/artifacts/outputs/{exec_id}/nested/{exec_id}/data/"
            assert expected_pattern in path

    def test_write_prefix_validation(self):
        """Test write-prefix validation for required patterns."""
        # Test invalid prefixes (should fail validation)
        invalid_prefixes = [
            "/invalid/path/",  # Not under /artifacts or /streams
            "artifacts/no-leading-slash/",  # No leading slash
            "/artifacts/no-trailing-slash",  # No trailing slash
            "",  # Empty prefix
        ]

        for invalid_prefix in invalid_prefixes:
            cmd = [
                "python",
                "manage.py",
                "run_processor",
                "--ref",
                "llm/litellm@1",
                "--adapter",
                "local",
                "--write-prefix",
                invalid_prefix,
                "--inputs-json",
                '{"messages":[]}',
                "--json",
            ]

            env = os.environ.copy()
            env["LLM_PROVIDER"] = "mock"
            env["PYTHONPATH"] = "."

            result = subprocess.run(cmd, cwd=".", env=env, capture_output=True, text=True)

            # Should return structured error envelope for validation failure
            try:
                payload = json.loads(result.stdout)
                assert payload.get("status") == "error", f"Expected error status for invalid prefix: {invalid_prefix}"
                assert "ERR_PREFIX_TEMPLATE" in payload.get("error", {}).get("code", ""), (
                    f"Expected prefix validation error: {payload}"
                )
            except json.JSONDecodeError:
                # If JSON parsing fails, expect non-zero exit code (fallback behavior)
                assert result.returncode != 0, f"Expected failure for invalid prefix: {invalid_prefix}"
