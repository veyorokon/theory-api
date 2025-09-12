#!/usr/bin/env python3
"""
Vulture gate: filter Django false positives from vulture output.

Usage: python vulture_gate.py vulture_report.txt
"""

import sys
import re
from pathlib import Path


ALLOWED_PATTERNS = [
    r"/migrations/",
    r"/admin\.py$",
    r"/apps\.py$", 
    r"/wsgi\.py$",
    r"/asgi\.py$",
    r"/management/commands/",
    r"/tests/",
    r"/conftest\.py$",
    r"vulture_whitelist\.py$",
]


def allowed(line: str) -> bool:
    """Check if a vulture finding should be ignored (Django patterns)."""
    return any(re.search(pattern, line) for pattern in ALLOWED_PATTERNS)


def main():
    if len(sys.argv) != 2:
        print("Usage: python vulture_gate.py <vulture_report.txt>", file=sys.stderr)
        sys.exit(1)
        
    report_path = Path(sys.argv[1])
    
    if not report_path.exists():
        print(f"Vulture report file not found: {report_path}", file=sys.stderr)
        sys.exit(1)
        
    text = report_path.read_text(encoding="utf-8")
    violations = [
        line.strip() 
        for line in text.splitlines() 
        if line.strip() and not allowed(line.strip())
    ]
    
    if violations:
        print("🔍 Vulture high-confidence findings (filtered):")
        for violation in violations:
            print(f"  ❌ {violation}")
        print(f"\n💡 Found {len(violations)} potential dead code issues.")
        print("💡 Review these findings or add to vulture_whitelist.py if intentional.")
        sys.exit(1)
        
    print("✅ Vulture: no blocking findings after filtering Django patterns.")
    sys.exit(0)


if __name__ == "__main__":
    main()