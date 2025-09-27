# tests/contracts/test_worldpath_contract.py
import pytest
from apps.core.orchestrator import run as orch_run
from tests.tools.asserts import assert_error_envelope

pytestmark = [pytest.mark.acceptance, pytest.mark.requires_docker, pytest.mark.requires_minio]


@pytest.mark.skip(reason="FORCE_DUPLICATE_OUTPUTS not implemented in processor")
def test_duplicate_after_canon_returns_canonical_error(
    tmp_write_prefix,
    pr_lane_env,  # hermetic environment
    logs_to_stderr,  # clean JSON output
    monkeypatch,
):
    """
    Contract: If two outputs collide after canonicalization, adapter returns ERR_OUTPUT_DUPLICATE.
    (This uses a tiny dummy module toggled by env to force duplicate relpaths.)
    """
    # Force the processor to emit two outputs with the same relpath after canon.
    monkeypatch.setenv("FORCE_DUPLICATE_OUTPUTS", "1")

    # Prepare inputs
    inputs = {"schema": "v1", "params": {}}

    # Execute via orchestrator
    envelope = orch_run(
        adapter="local",
        ref="llm/litellm@1",
        mode="mock",
        inputs=inputs,
        write_prefix=tmp_write_prefix,
        expected_oci=None,
        build=True,
    )

    assert_error_envelope(envelope, code_fragment="ERR_OUTPUT_DUPLICATE")
