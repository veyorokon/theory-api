# tests/unit/core/test_mode_guard.py
import os
import pytest


@pytest.mark.unit
def test_real_mode_allowed(monkeypatch):
    # import here so code path is set by conftest
    from libs.runtime_common.envelope import resolve_mode

    # Real mode should work now without any CI/PR lane restrictions
    inputs = {"schema": "v1", "mode": "real"}
    result = resolve_mode(inputs)
    assert result.value == "real"
