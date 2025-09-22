# tests/tools/markers.py
from __future__ import annotations
import pytest

# The canonical set of markers we expect in pytest.ini
_EXPECTED = {
    "unit",
    "integration",
    "contracts",
    "property",
    "acceptance",
    "prlane",
    "supplychain",
    "modal",
    "requires_postgres",
    "requires_docker",
    "deploy_smoke",
}


def pytest_configure(config: pytest.Config) -> None:
    # Discover all registered markers
    registered = {info.name for info in config.getini("markers")}
    missing = sorted(_EXPECTED - registered)
    if missing:
        raise SystemExit("pytest.ini is missing required markers (strict-markers is on): " + ", ".join(missing))
