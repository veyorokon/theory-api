"""End-to-end integration tests for local adapter with MinIO storage."""

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


class TestE2ELocal:
    """Test end-to-end execution through local adapter."""

    def test_local_adapter_e2e_minio_success(self):
        """Test complete local adapter execution with MinIO storage."""
        _ensure_bucket_exists()

        # Use templated write prefix with execution_id
        prefix = "/artifacts/outputs/text/{execution_id}/"

        cmd = [
            "python",
            "manage.py",
            "run_processor",
            "--ref",
            "llm/litellm@1",
            "--adapter",
            "local",
            "--write-prefix",
            prefix,
            "--mode",
            "mock",
            "--inputs-json",
            '{"schema":"v1","params":{"messages":[{"role":"user","content":"Hello integration test"}]}}',
            "--json",
        ]

        # Set environment for execution
        env = os.environ.copy()
        env["PYTHONPATH"] = "."

        # Execute processor
        result = subprocess.run(cmd, cwd=".", env=env, capture_output=True, text=True)

        # Debug output for CI diagnostics
        if result.returncode != 0:
            print("❌ Processor command failed:")
            print(f"Command: {' '.join(cmd)}")
            print(f"Return code: {result.returncode}")
            print(f"STDERR: {result.stderr}")
            print(f"STDOUT: {result.stdout}")

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Parse JSON response
        payload = json.loads(result.stdout)

        # Debug output for error envelopes
        if payload.get("status") == "error":
            print("❌ Processor returned error envelope:")
            print(json.dumps(payload, indent=2))

        # Verify success envelope shape
        assert payload["status"] == "success"
        assert "execution_id" in payload
        assert "outputs" in payload
        assert "index_path" in payload
        assert "meta" in payload

        exec_id = payload["execution_id"]
        bucket = os.environ.get("S3_BUCKET", "default")

        # Verify MinIO objects exist
        s3 = _minio_client()

        # Check response.json exists
        response_key = f"artifacts/outputs/text/{exec_id}/response.json"
        response_obj = s3.get_object(Bucket=bucket, Key=response_key)
        response_data = json.loads(response_obj["Body"].read().decode())

        # Verify response contains mock LLM output
        assert response_data["model"] == "mock-model"
        assert response_data["mode"] == "mock"
        assert "choices" in response_data
        assert response_data["choices"][0]["message"]["content"] == "this is a mock reply"

        # Check receipt.json exists
        receipt_key = f"artifacts/outputs/text/{exec_id}/receipt.json"
        receipt_obj = s3.get_object(Bucket=bucket, Key=receipt_key)
        receipt_data = json.loads(receipt_obj["Body"].read().decode())

        # Verify receipt shape
        assert "env_fingerprint" in receipt_data
        assert "duration_ms" in receipt_data

        # Verify outputs metadata
        assert len(payload["outputs"]) >= 2  # At least response.json + receipt.json
        output_paths = [output["path"] for output in payload["outputs"]]
        assert any("response.json" in path for path in output_paths)
        assert any("receipt.json" in path for path in output_paths)

    def test_local_adapter_error_handling(self):
        """Test local adapter properly handles processor failures."""
        cmd = [
            "python",
            "manage.py",
            "run_processor",
            "--ref",
            "nonexistent/processor@1",
            "--adapter",
            "local",
            "--mode",
            "mock",
            "--write-prefix",
            "/artifacts/outputs/error/",
            "--inputs-json",
            '{"schema":"v1","messages":[]}',
            "--json",
        ]

        env = os.environ.copy()
        env["PYTHONPATH"] = "."

        result = subprocess.run(cmd, cwd=".", env=env, capture_output=True, text=True)

        # Should fail gracefully with error envelope
        try:
            payload = json.loads(result.stdout)
            assert payload.get("status") == "error", "Expected error status for nonexistent processor"
            assert "ERR_ADAPTER_INVOCATION" in payload.get("error", {}).get("code", ""), (
                f"Expected adapter invocation error: {payload}"
            )
        except json.JSONDecodeError:
            # If JSON parsing fails, expect non-zero exit code (fallback behavior)
            assert result.returncode != 0
        # Error details should be in stderr or error envelope format
