# tests/integration/adapters/test_local_index_path_contract.py
import pytest
from apps.core.orchestrator import run as orch_run
from tests.tools.asserts import assert_success_envelope, assert_index_under_prefix


@pytest.mark.requires_docker
def test_local_adapter_index_path_under_prefix(tmp_write_prefix):
    # Prepare inputs
    inputs = {
        "schema": "v1",
        "params": {"messages": [{"role": "user", "content": "hi"}]},
    }

    # Execute via orchestrator with build=True (PR lane behavior)
    envelope = orch_run(
        adapter="local",
        ref="llm/litellm@1",
        mode="mock",
        inputs=inputs,
        write_prefix=tmp_write_prefix,
        expected_oci=None,
        build=True,
    )

    assert_success_envelope(envelope)
    # Verify path relationship - expand template with actual execution_id
    expected_prefix = tmp_write_prefix.replace("{execution_id}", envelope["execution_id"])
    assert_index_under_prefix(envelope["index_path"], expected_prefix)
