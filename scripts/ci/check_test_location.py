#!/usr/bin/env python3
"""CI guard to prevent package-local tests from reappearing."""

import os
import sys
from pathlib import Path


def main():
    """Check for package-local test files and fail if found."""
    repo_root = Path(__file__).parent.parent.parent
    code_dir = repo_root / "code"

    # Find any .py files under apps/*/tests
    test_files = []
    for app_dir in (code_dir / "apps").glob("*/tests"):
        if app_dir.is_dir():
            py_files = list(app_dir.glob("**/*.py"))
            if py_files:
                test_files.extend(py_files)

    if test_files:
        print("❌ Package-local test files found (should be in repo-root tests/):")
        for f in sorted(test_files):
            rel_path = f.relative_to(repo_root)
            print(f"  {rel_path}")
        print("\nMove these to tests/ directory following lane structure:")
        print("  tests/unit/{domain}/")
        print("  tests/integration/{domain}/")
        print("  tests/acceptance/")
        print("  tests/property/")
        return 1

    print("✅ No package-local test files found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
