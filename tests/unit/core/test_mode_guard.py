# tests/unit/core/test_mode_guard.py
import os
import pytest


@pytest.mark.unit
def test_ci_guard_blocks_real_mode(monkeypatch):
    # import here so code path is set by conftest
    from libs.runtime_common.envelope import resolve_mode, ModeSafetyError

    monkeypatch.setenv("CI", "true")
    inputs = {"schema": "v1", "mode": "real"}
    with pytest.raises(ModeSafetyError) as e:
        resolve_mode(inputs)
    assert "ERR_CI_SAFETY" in str(e.value)
