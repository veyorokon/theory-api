# tests/integration/adapters/test_local_index_path_contract.py
import pytest
from tests.tools.runner import run_cli, parse_stdout_json_or_fail
from tests.tools.asserts import assert_success_envelope, assert_index_under_prefix


@pytest.mark.requires_docker
def test_local_adapter_index_path_under_prefix(tmp_write_prefix):
    # Run via manage.py with --build (PR lane behavior)
    args = [
        "run_processor",
        "--ref",
        "llm/litellm@1",
        "--adapter",
        "local",
        "--mode",
        "mock",
        "--write-prefix",
        tmp_write_prefix,
        "--inputs-json",
        '{"schema":"v1","params":{"messages":[{"role":"user","content":"hi"}]}}',
        "--json",
        "--build",
    ]
    proc = run_cli(args, env={"LOG_STREAM": "stderr"})
    env = parse_stdout_json_or_fail(proc)
    assert_success_envelope(env)
    # Verify path relationship - expand template with actual execution_id
    expected_prefix = tmp_write_prefix.replace("{execution_id}", env["execution_id"])
    assert_index_under_prefix(env["index_path"], expected_prefix)
