"""
Test the dead-code detection tools.
"""

import pytest
import subprocess
import sys
from pathlib import Path


def test_import_reachability_checker_runs():
    """Test that the import reachability checker can run without crashing."""
    # Run the reachability checker
    result = subprocess.run(
        [sys.executable, "-m", "tests.tools.check_import_reachability"],
        cwd=Path(__file__).parent.parent,  # code/ directory
        capture_output=True,
        text=True,
    )

    # Should either succeed (exit 0) or fail with our specific message (exit 1)
    assert result.returncode in [0, 1], f"Unexpected exit code: {result.returncode}"

    # Should not crash with import errors or other exceptions
    if result.returncode == 1:
        assert "Unreachable modules detected:" in result.stdout or "Failed to build import graph:" in result.stdout
    else:
        assert "modules are reachable" in result.stdout


@pytest.mark.skipif(
    subprocess.run(["which", "vulture"], capture_output=True).returncode != 0, reason="vulture not available"
)
def test_vulture_whitelist_format():
    """Test that vulture whitelist file exists and is properly formatted."""
    whitelist_path = Path(__file__).parent.parent / "vulture_whitelist.py"
    assert whitelist_path.exists(), "vulture_whitelist.py should exist"

    # Should be valid Python
    with open(whitelist_path) as f:
        content = f.read()

    # Basic syntax check by attempting to compile
    compile(content, str(whitelist_path), "exec")

    # Should contain some expected entries
    assert "modal_app._exec" in content
    assert "ModalAdapter.invoke" in content


def test_coverage_config_exists():
    """Test that coverage configuration exists."""
    config_path = Path(__file__).parent.parent / ".coveragerc"
    assert config_path.exists(), ".coveragerc should exist for coverage settings"

    with open(config_path) as f:
        content = f.read()

    # Should exclude test files and migrations
    assert "*/tests/*" in content
    assert "*/migrations/*" in content
