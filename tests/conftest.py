"""
Pytest configuration and shared fixtures for all test types.

Test Adapter Selection:
- Set TEST_ADAPTER=local or TEST_ADAPTER=modal (required)
- Local: Uses docker containers via localctl
- Modal: Uses Modal functions (requires MODAL_TOKEN_ID/SECRET)

Settings:
- Unit tests: DJANGO_SETTINGS_MODULE=backend.settings.unittest (SQLite :memory:)
- Integration: DJANGO_SETTINGS_MODULE=backend.settings.dev_local (Postgres via compose)
"""

import os
import sys
import pathlib
import pytest


def require_env(name: str) -> str:
    """
    Load environment variable or fail test.

    Args:
        name: Environment variable name

    Returns:
        str: Environment variable value

    Raises:
        pytest.fail: If environment variable is not set
    """
    val = os.getenv(name)
    if val is None:
        pytest.fail(f"{name} environment variable required")
    return val


# Ensure code/ is importable
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CODE_DIR = _REPO_ROOT / "code"
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))


# ============================================================================
# Auto-apply markers based on folder structure
# ============================================================================
FOLDER_MARKS = [
    (("tests", "unit"), ("unit",)),
    (("tests", "contracts"), ("contracts",)),
    (("tests", "integration"), ("integration",)),
]


def _under(path_posix: str, *segments: str) -> bool:
    return f"/{'/'.join(segments)}/" in path_posix


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-apply markers from FOLDER_MARKS."""
    for item in items:
        p = pathlib.Path(str(item.fspath)).as_posix()
        for segs, marks in FOLDER_MARKS:
            if _under(p, *segs):
                for m in marks:
                    item.add_marker(getattr(pytest.mark, m))


# ============================================================================
# Global environment setup
# ============================================================================
@pytest.fixture(autouse=True)
def _stable_env(monkeypatch: pytest.MonkeyPatch):
    """Set stable environment for all tests."""
    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.setenv("PYTHONUNBUFFERED", "1")

    # Default Django settings if not provided
    if not os.getenv("DJANGO_SETTINGS_MODULE"):
        monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "backend.settings.unittest")

    yield


# ============================================================================
# Adapter selection
# ============================================================================
@pytest.fixture(scope="session")
def adapter_type():
    """
    Get adapter type from environment.

    Returns:
        str: "local" or "modal"
    """
    return require_env("TEST_ADAPTER")


@pytest.fixture(scope="session")
def test_env():
    """
    Get test environment for Modal adapter.

    Returns:
        str: "dev", "staging", or "main"
    """
    return require_env("MODAL_ENVIRONMENT")
