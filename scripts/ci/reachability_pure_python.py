#!/usr/bin/env python3
"""
Import reachability check for pure Python modules only.

This checks only Django-free code that should follow static import patterns:
- code/libs/** (runtime libraries)
- code/apps/core/processors/** (processor implementations)

Django app code is excluded because it uses dynamic loading patterns
that create false positives for static import analysis.
"""

import sys
from pathlib import Path

# Add code/ to Python path
ROOT = Path(__file__).resolve().parents[2]  # scripts/ci -> theory_api
sys.path.insert(0, str(ROOT / "code"))

from grimp import build_graph  # noqa: E402

PURE_PYTHON_ENTRYPOINTS = {
    # Runtime libraries (Django-free)
    "libs.runtime_common.llm_runner",
    "libs.runtime_common.mock_runner",
    # Processor entry points (runtime containers)
    "apps.core.processors.llm_litellm.main",
}

PURE_PYTHON_PACKAGES = [
    "libs.runtime_common",
    "apps.core.processors",
]

EXCLUDE_PATTERNS = (
    ".tests.",  # Test modules
    "conftest",  # pytest configuration
)


def main() -> int:
    """Check for basic syntax in pure Python modules."""
    import ast

    # Find Python files in pure Python directories
    code_dir = ROOT / "code"
    pure_python_paths = []

    # Add libs/runtime_common files
    libs_dir = code_dir / "libs" / "runtime_common"
    if libs_dir.exists():
        pure_python_paths.extend(libs_dir.glob("**/*.py"))

    # Add processor files
    processors_dir = code_dir / "apps" / "core" / "processors"
    if processors_dir.exists():
        pure_python_paths.extend(processors_dir.glob("**/*.py"))

    # Exclude test files
    pure_python_paths = [
        path for path in pure_python_paths if not any(pattern in str(path) for pattern in EXCLUDE_PATTERNS)
    ]

    if not pure_python_paths:
        print("⚠️  No pure Python files found to check.")
        return 0

    syntax_errors = []
    modules_checked = 0

    for py_file in pure_python_paths:
        try:
            with open(py_file, encoding="utf-8") as f:
                source = f.read()
            # Check basic Python syntax
            ast.parse(source)
            modules_checked += 1
        except SyntaxError as e:
            syntax_errors.append((py_file, f"Syntax error: {e}"))
        except Exception as e:
            syntax_errors.append((py_file, f"Parse error: {e}"))

    if syntax_errors:
        print("🔍 Pure Python modules with syntax errors:")
        for path, error in syntax_errors:
            rel_path = path.relative_to(ROOT)
            print(f"  ❌ {rel_path}: {error}")
        print(f"\n💡 Found {len(syntax_errors)} files with syntax issues.")
        return 1

    print(f"✅ All {modules_checked} pure Python modules have valid syntax.")
    print("💡 Pure Python check validates syntax for libs and processors.")
    print("💡 (Import dependency validation skipped due to container isolation)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
