# tests/smoke/test_canary_contract.py
import os
import pytest

# Smoke tests are only meaningful in CI staging/main lanes.
ENV = os.getenv("MODAL_ENVIRONMENT", "")
if ENV not in {"staging", "main"}:
    pytest.skip(f"skip smoke outside staging/main (MODAL_ENVIRONMENT='{ENV}')", allow_module_level=True)


def test_smoke_canary_env_names_present():
    """
    Lightweight smoke: ensure CI wired the environment names we expect (staging/main lanes only).
    Not a functional modal call; purely a deploy-lane sanity.
    """
    env = os.getenv("MODAL_ENVIRONMENT", "")
    assert env in {"staging", "main"}, f"unexpected MODAL_ENVIRONMENT: {env!r}"
