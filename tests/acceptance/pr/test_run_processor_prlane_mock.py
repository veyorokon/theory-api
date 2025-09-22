# tests/acceptance/pr/test_run_processor_prlane_mock.py
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from typing import Iterable, Tuple

import pytest

# Optional registry-driven parametrization (preferred).
# Falls back to a single processor when registry tools aren't available.
try:
    from tests.tools.registry import iter_mockable_refs  # type: ignore
except Exception:  # pragma: no cover
    iter_mockable_refs = lambda: ["llm/litellm@1"]  # noqa: E731


@pytest.mark.parametrize("processor_ref", list(iter_mockable_refs()))
def test_run_processor_prlane_mock_builds_from_source_and_writes_index(
    processor_ref: str,
    tmp_write_prefix: str,
    assert_envelope_success,  # from conftest.py
    pr_lane_env,  # lane fixture: CI=true, no secrets, RUN_PROCESSOR_FORCE_BUILD=1
    logs_to_stderr,  # opt-in stderr logging for CLI --json
    monkeypatch: pytest.MonkeyPatch,
):
    """
    PR-lane acceptance: build-from-source (--build), mock mode, hermetic.
    Verifies:
      - CLI exits 0
      - stdout is a single canonical envelope (JSON)
      - index_path lies under rendered write_prefix and ends with outputs.json
      - logs emitted to stderr (non-empty)
    """
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    code_dir = repo_root / "code"
    assert code_dir.is_dir(), f"Expected code/ directory at {code_dir}"

    # logs_to_stderr fixture already set LOG_STREAM=stderr
    # Force build-from-source explicitly for clarity (PR lane also sets RUN_PROCESSOR_FORCE_BUILD=1)
    cmd = [
        sys.executable,
        "manage.py",
        "run_processor",
        "--ref",
        processor_ref,
        "--adapter",
        "local",
        "--mode",
        "mock",
        "--build",
        "--write-prefix",
        tmp_write_prefix,  # contains {execution_id}
        "--inputs-json",
        '{"schema":"v1","params":{"messages":[{"role":"user","content":"hi"}]}}',
        "--json",
    ]

    # Run the command from code/ so manage.py is importable.
    proc = subprocess.run(
        cmd,
        cwd=str(code_dir),
        env={**os.environ},
        text=True,
        capture_output=True,
        check=False,
    )

    # PR lane must not fail. If it does, surface stderr for fast RCA.
    assert proc.returncode == 0, f"run_processor failed (rc={proc.returncode})\nSTDERR:\n{proc.stderr}"

    # Logs should be on stderr (structured JSON lines). Not asserting schema here—just non-empty is enough.
    assert proc.stderr.strip(), "expected structured logs on stderr; got empty stderr"

    # Stdout must be exactly one JSON envelope.
    try:
        env = json.loads(proc.stdout)
    except json.JSONDecodeError as e:  # pragma: no cover
        raise AssertionError(f"stdout was not a single JSON envelope:\n{proc.stdout}\n\nerr={e}") from e

    # Canonical success envelope assertions (helper checks index_path suffix and fingerprint fragments).
    assert_envelope_success(env)

    # Extra: ensure index_path falls under the rendered write_prefix.
    # Render the write_prefix with the envelope's execution_id (same expansion the adapter performs).
    execution_id = env["execution_id"]
    rendered_prefix = tmp_write_prefix.format(execution_id=execution_id).rstrip("/") + "/"
    index_path = env.get("index_path", "")
    assert index_path.startswith(rendered_prefix), (
        f"index_path must live under write_prefix; got index_path={index_path} rendered_prefix={rendered_prefix}"
    )
