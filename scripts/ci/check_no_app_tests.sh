#!/bin/bash
# CI guard against app-local tests creeping back
set -euo pipefail

if find code/apps -type d -name tests -print -quit | grep -q .; then
  echo "Fail: app-local tests found under code/apps/**/tests"; exit 1
fi

if [ -d code/tests ]; then
  echo "Fail: legacy code/tests/ exists"; exit 1
fi

echo "Pass: no app-local tests found"
