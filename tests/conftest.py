import os
import socket
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


# Network egress guard for unit/integration tests
@pytest.fixture(autouse=True)
def _no_net_in_unit_integration(request, monkeypatch):
    if request.node.get_closest_marker("acceptance"):
        return
    if request.node.get_closest_marker("smoke"):
        return
    # deny outbound sockets
    orig = socket.socket

    def deny(*a, **k):
        raise RuntimeError("Network disabled in this lane")

    monkeypatch.setattr(socket, "socket", deny)


# Skip requires_postgres when not on a Postgres settings module
def pytest_runtest_setup(item):
    if item.get_closest_marker("requires_postgres"):
        # Fast check via env; falls back to Django settings if set up
        dj = os.environ.get("DJANGO_SETTINGS_MODULE", "")
        if "backend.settings.test" not in dj:
            pytest.skip("requires_postgres: running on non-Postgres settings")
