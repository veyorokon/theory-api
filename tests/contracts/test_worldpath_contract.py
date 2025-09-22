# tests/contracts/test_worldpath_contract.py
import pytest
from tests.tools.runner import run_cli, parse_stdout_json_or_fail
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

    args = [
        "run_processor",
        "--ref",
        "llm/litellm@1",
        "--adapter",
        "local",
        "--mode",
        "mock",
        "--build",
        "--write-prefix",
        tmp_write_prefix,
        "--inputs-json",
        '{"schema":"v1","params":{}}',
        "--json",
    ]
    proc = run_cli(args)
    env = parse_stdout_json_or_fail(proc)
    assert_error_envelope(env, code_fragment="ERR_OUTPUT_DUPLICATE")
