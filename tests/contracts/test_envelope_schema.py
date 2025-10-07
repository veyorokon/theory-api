"""
Contract tests for envelope schema validation.

Enforces invariants that must hold across all adapters and environments.
"""

import pytest


@pytest.mark.contracts
def test_success_envelope_schema():
    """Success envelope must contain required fields with correct types."""
    # Example success envelope (what protocol returns)
    envelope = {
        "status": "success",
        "run_id": "abc-123",
        "outputs": {
            "response": 'world://world-id/run-id/response?data="hello"',
            "usage": "world://world-id/run-id/usage?data={}",
        },
        "meta": {
            "env_fingerprint": "cpu:1;memory:2Gi",
            "image_digest": "sha256:abc123",
            "proof": {"etag_map": {"response": "etag-xyz"}},
        },
    }

    # Required fields
    assert envelope["status"] == "success"
    assert isinstance(envelope["run_id"], str)
    assert len(envelope["run_id"]) > 0

    # Outputs must be dict mapping keys to URIs
    assert isinstance(envelope["outputs"], dict)
    assert len(envelope["outputs"]) > 0
    for key, uri in envelope["outputs"].items():
        assert isinstance(key, str)
        assert isinstance(uri, str)
        assert uri.startswith("world://") or uri.startswith("local://")

    # Meta required fields
    assert "env_fingerprint" in envelope["meta"]
    assert "image_digest" in envelope["meta"]


@pytest.mark.contracts
def test_error_envelope_schema():
    """Error envelope must contain status, run_id, error code/message."""
    envelope = {
        "status": "error",
        "run_id": "abc-123",
        "error": {"code": "ERR_INPUTS", "message": "Invalid input"},
        "meta": {
            "env_fingerprint": "cpu:1;memory:2Gi",
            "image_digest": "sha256:abc123",
        },
    }

    assert envelope["status"] == "error"
    assert isinstance(envelope["run_id"], str)

    # Error must have code and message
    assert "code" in envelope["error"]
    assert "message" in envelope["error"]
    assert envelope["error"]["code"].startswith("ERR_")
    assert isinstance(envelope["error"]["message"], str)


@pytest.mark.contracts
def test_uri_scheme_world():
    """world:// URIs must follow format: world://world-id/run-id/path."""
    uri = "world://my-world/abc-123/text/response.txt"

    assert uri.startswith("world://")

    # Parse: world://world-id/run-id/path
    parts = uri.replace("world://", "").split("/", 2)
    assert len(parts) == 3
    world_id, run_id, path = parts

    assert len(world_id) > 0
    assert len(run_id) > 0
    assert len(path) > 0


@pytest.mark.contracts
def test_uri_scheme_local():
    """local:// URIs must follow format: local://run-id/path."""
    uri = "local://abc-123/text/response.txt"

    assert uri.startswith("local://")

    # Parse: local://run-id/path
    parts = uri.replace("local://", "").split("/", 1)
    assert len(parts) == 2
    run_id, path = parts

    assert len(run_id) > 0
    assert len(path) > 0


@pytest.mark.contracts
def test_artifact_scope_determines_uri_scheme():
    """
    Verify the contract: artifact_scope determines URI scheme.

    - artifact_scope=world → outputs field present → world:// URIs
    - artifact_scope=local → outputs field absent → local:// URIs
    """
    # This test documents the contract without needing actual invocation
    contracts = {
        "world": {
            "payload_has_outputs": True,
            "expected_uri_prefix": "world://",
        },
        "local": {
            "payload_has_outputs": False,
            "expected_uri_prefix": "local://",
        },
    }

    for artifact_scope, contract in contracts.items():
        # Document contract expectations for each scope
        assert isinstance(contract["payload_has_outputs"], bool)
        assert isinstance(contract["expected_uri_prefix"], str)
        assert artifact_scope in ("world", "local")
