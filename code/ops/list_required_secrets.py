#!/usr/bin/env python3
from __future__ import annotations
import json
import sys
from pathlib import Path


def main() -> int:
    base = Path("code/apps/core/registry/processors")
    names = set()
    for y in base.glob("*.yaml"):
        txt = y.read_text(encoding="utf-8")
        # ultra-light parse to find "secrets:\n  required:\n    - NAME"
        # avoids pyyaml dep in CI
        block = False
        for line in txt.splitlines():
            if line.strip().startswith("secrets:"):
                block = True
                continue
            if block and line.strip().startswith("required:"):
                continue
            if block and line.strip().startswith("- "):
                names.add(line.strip()[2:].strip())
                continue
            if block and line and not line.startswith(" "):
                # left the secrets: block
                block = False
    print(json.dumps(sorted(names)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
