import os
import pytest

# Auto-mark by folder conventions
def pytest_collection_modifyitems(config, items):
    for item in items:
        p = str(item.fspath)
        if "/tests/acceptance/" in p:
            item.add_marker(pytest.mark.ledger_acceptance)
            item.add_marker(pytest.mark.requires_postgres)
        elif "/tests/integration/" in p:
            item.add_marker(pytest.mark.integration)
        # Optional: default-mark plain tests as unit to be explicit
        elif "/tests/" in p:
            item.add_marker(pytest.mark.unit)

# Skip requires_postgres when not on a Postgres settings module
def pytest_runtest_setup(item):
    if item.get_closest_marker("requires_postgres"):
        # Fast check via env; falls back to Django settings if set up
        dj = os.environ.get("DJANGO_SETTINGS_MODULE", "")
        if "backend.settings.test" not in dj:
            pytest.skip("requires_postgres: running on non-Postgres settings")