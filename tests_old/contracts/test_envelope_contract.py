# tests/contracts/test_envelope_contract.py
import sys
from pathlib import Path

# Add tests/tools to path
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from asserts import assert_success_envelope, assert_error_envelope


def test_success_envelope_contract_minimal():
    env = {
        "status": "success",
        "execution_id": "abc",
        "outputs": [{"path": "/artifacts/outputs/demo/abc/outputs/response.json"}],
        "index_path": "/artifacts/outputs/demo/abc/outputs.json",
        "meta": {"env_fingerprint": "cpu:1;image:theory-local/llm-litellm-v1:dev;memory:2gb"},
    }
    assert_success_envelope(env)


def test_error_envelope_contract_minimal():
    env = {
        "status": "error",
        "execution_id": "abc",
        "error": {"code": "ERR_CI_SAFETY", "message": "Refusing to run mode=real in CI"},
        "meta": {"env_fingerprint": "cpu:1;image:..."},
    }
    assert_error_envelope(env, code_fragment="ERR_CI_SAFETY")
