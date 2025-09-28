"""Write prefix expansion contract tests (HTTP-first)."""

import os
import json
import pytest
from fastapi.testclient import TestClient


def _import_fastapi_app():
    """
    Import the FastAPI app object for the processor under test.

    You can override the import path with TEST_PROCESSOR_IMPORT, e.g.:
      TEST_PROCESSOR_IMPORT=apps.core.processors.llm_litellm.app.http:app
    """
    import_path = os.getenv(
        "TEST_PROCESSOR_IMPORT",
        "apps.core.processors.llm_litellm.app.http:app",
    )
    module_path, _, attr = import_path.partition(":")
    if not module_path or not attr:
        raise RuntimeError(f"Invalid TEST_PROCESSOR_IMPORT '{import_path}' (expected 'pkg.mod:app')")
    mod = __import__(module_path, fromlist=[attr])
    return getattr(mod, attr)


@pytest.fixture(scope="module")
def client():
    app = _import_fastapi_app()
    return TestClient(app)


@pytest.fixture
def mock_image_digest(monkeypatch):
    # Enforce digest is present (our handler requires it for meta.image_digest)
    monkeypatch.setenv("IMAGE_DIGEST", "sha256:deadbeef")


@pytest.mark.contracts
class TestWritePrefixExpansion:
    """Test write_prefix {execution_id} expansion and validation via HTTP."""

    def _payload(self, execution_id: str, write_prefix: str) -> dict:
        # Minimal valid payload for our LLM scaffold
        return {
            "execution_id": execution_id,
            "write_prefix": write_prefix,
            "schema": "v1",
            "mode": "mock",
            "inputs": {
                "schema": "v1",
                "params": {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "test"}],
                },
            },
        }

    def _assert_expanded(self, envelope: dict, expected_prefix: str):
        # Outputs must live under expanded prefix
        assert envelope["status"] == "success"
        for out in envelope.get("outputs", []):
            path = out.get("path", "")
            assert path.startswith(expected_prefix), f"{path} !startswith {expected_prefix}"
            assert "{execution_id}" not in path

        # Index must live under expanded prefix
        index_path = envelope.get("index_path", "")
        assert index_path.startswith(expected_prefix), f"{index_path} !startswith {expected_prefix}"
        assert "{execution_id}" not in index_path

    def test_basic_expansion(self, client, mock_image_digest, tmp_path):
        execution_id = "wp-basic-001"
        write_prefix = f"{tmp_path}/outputs/{{execution_id}}/"
        resp = client.post("/run", json=self._payload(execution_id, write_prefix))
        assert resp.status_code == 200, resp.text
        env = resp.json()
        expected = f"{tmp_path}/outputs/{execution_id}/"
        self._assert_expanded(env, expected)

    def test_multiple_placeholders(self, client, mock_image_digest, tmp_path):
        execution_id = "wp-multi-002"
        # Appears twice; both must expand
        write_prefix = f"{tmp_path}/{{execution_id}}/nested/{{execution_id}}/"
        resp = client.post("/run", json=self._payload(execution_id, write_prefix))
        assert resp.status_code == 200, resp.text
        expected = f"{tmp_path}/{execution_id}/nested/{execution_id}/"
        self._assert_expanded(resp.json(), expected)

    def test_case_sensitivity(self, client, mock_image_digest, tmp_path):
        execution_id = "CaseSensitive-XYZ"
        write_prefix = f"{tmp_path}/cs/{{execution_id}}/out/"
        resp = client.post("/run", json=self._payload(execution_id, write_prefix))
        assert resp.status_code == 200, resp.text
        expected = f"{tmp_path}/cs/{execution_id}/out/"
        self._assert_expanded(resp.json(), expected)

    def test_special_characters(self, client, mock_image_digest, tmp_path):
        execution_id = "test-123_456.789"
        write_prefix = f"{tmp_path}/sp/{{execution_id}}/"
        resp = client.post("/run", json=self._payload(execution_id, write_prefix))
        assert resp.status_code == 200, resp.text
        expected = f"{tmp_path}/sp/{execution_id}/"
        self._assert_expanded(resp.json(), expected)

    def test_trailing_slash_normalization(self, client, mock_image_digest, tmp_path):
        execution_id = "wp-slash-003"
        # No trailing slash; handler should normalize to include one
        write_prefix = f"{tmp_path}/trail/{{execution_id}}"
        resp = client.post("/run", json=self._payload(execution_id, write_prefix))
        assert resp.status_code == 200, resp.text
        expected = f"{tmp_path}/trail/{execution_id}/"
        self._assert_expanded(resp.json(), expected)

    def test_static_prefix_allowed(self, client, mock_image_digest, tmp_path):
        execution_id = "wp-static-004"
        # No placeholder: allowed; nothing to expand
        static_prefix = f"{tmp_path}/static/output/path/"
        resp = client.post("/run", json=self._payload(execution_id, static_prefix))
        assert resp.status_code == 200, resp.text
        env = resp.json()
        # Even with a static prefix, outputs/index must live under that prefix
        for out in env.get("outputs", []):
            assert out["path"].startswith(static_prefix)
        assert env.get("index_path", "").startswith(static_prefix)

    def test_consistency_across_all_artifacts(self, client, mock_image_digest, tmp_path):
        execution_id = "wp-consistent-005"
        # One placeholder, nested path
        write_prefix = f"{tmp_path}/consistent/{{execution_id}}/test/"
        resp = client.post("/run", json=self._payload(execution_id, write_prefix))
        assert resp.status_code == 200, resp.text
        expected = f"{tmp_path}/consistent/{execution_id}/test/"
        env = resp.json()
        self._assert_expanded(env, expected)
