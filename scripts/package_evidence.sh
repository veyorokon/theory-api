#!/bin/bash
# Evidence packaging script with privacy filters
# Usage: ./scripts/package_evidence.sh [output_dir]

set -euo pipefail

OUTPUT_DIR="${1:-evidence/packaged_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUTPUT_DIR"

echo "📦 Packaging evidence to: $OUTPUT_DIR"

# Core evidence files (copy from project evidence directory)
echo "→ Copying core evidence files..."
if [ -d "evidence" ]; then
    # Copy all evidence except the target directory itself
    find evidence -mindepth 1 -maxdepth 1 ! -name "$(basename "$OUTPUT_DIR")" -exec cp -r {} "$OUTPUT_DIR/" \;
    echo "  ✅ Copied project evidence files"
else
    echo "  (no evidence/ directory found)"
fi

# Test outputs with privacy filtering
echo "→ Collecting test outputs (filtered)..."
mkdir -p "$OUTPUT_DIR/test_outputs"

# Filter sensitive data from test outputs
find /tmp -name "modal_*_mock.json" -o -name "modal_*_real.json" 2>/dev/null | while read -r file; do
    if [ -f "$file" ]; then
        # Remove API keys, tokens, and secrets
        jq 'walk(if type == "string" then gsub("sk-[a-zA-Z0-9]{48,}"; "sk-REDACTED") | gsub("Bearer [a-zA-Z0-9_.-]+"; "Bearer REDACTED") else . end)' \
           "$file" > "$OUTPUT_DIR/test_outputs/$(basename "$file")"
    fi
done

# Also capture and filter recent stdout/stderr examples if they exist
for logfile in /tmp/stdout.log /tmp/stderr.log; do
    if [ -f "$logfile" ]; then
        # Apply same privacy filtering to log files
        if [[ "$logfile" == *.json ]] || head -1 "$logfile" | jq . >/dev/null 2>&1; then
            # JSON file - use jq filtering
            jq 'walk(if type == "string" then gsub("sk-[a-zA-Z0-9]{48,}"; "sk-REDACTED") | gsub("Bearer [a-zA-Z0-9_.-]+"; "Bearer REDACTED") else . end)' \
               "$logfile" > "$OUTPUT_DIR/test_outputs/$(basename "$logfile")" 2>/dev/null || cp "$logfile" "$OUTPUT_DIR/test_outputs/$(basename "$logfile")"
        else
            # Text file - use sed filtering
            sed -E 's/sk-[a-zA-Z0-9]{20,}/sk-REDACTED/g; s/Bearer [a-zA-Z0-9._-]+/Bearer REDACTED/g' \
                "$logfile" > "$OUTPUT_DIR/test_outputs/$(basename "$logfile")"
        fi
    fi
done

# System info (non-sensitive)
echo "→ Collecting system info..."
{
    echo "=== System Info ==="
    uname -a
    echo
    echo "=== Python Version ==="
    python --version
    echo
    echo "=== Docker Version ==="
    docker --version
    echo
    echo "=== Environment (filtered) ==="
    env | grep -E "^(PATH|USER|HOME|SHELL|DJANGO_SETTINGS_MODULE|TEST_LANE)" | sort
} > "$OUTPUT_DIR/system_info.txt"

# Git status (safe)
echo "→ Collecting git status..."
{
    echo "=== Git Status ==="
    git status --porcelain
    echo
    echo "=== Recent Commits ==="
    git log --oneline -10
    echo
    echo "=== Current Branch ==="
    git branch --show-current
} > "$OUTPUT_DIR/git_status.txt" 2>/dev/null || echo "  (git not available)"

# Test collection summary
echo "→ Collecting test collection info..."
mkdir -p "$OUTPUT_DIR"
cd code 2>/dev/null || cd .
{
    echo "=== Unit Tests Collection ==="
    PYTHONPATH=. DJANGO_SETTINGS_MODULE=backend.settings.unittest python -m pytest --collect-only -q -m "unit" 2>/dev/null | head -20
    echo
    echo "=== Integration Tests Collection ==="
    PYTHONPATH=. DJANGO_SETTINGS_MODULE=backend.settings.unittest python -m pytest --collect-only -q -m "integration" 2>/dev/null | head -20
    echo
    echo "=== Contract Tests Collection ==="
    PYTHONPATH=. DJANGO_SETTINGS_MODULE=backend.settings.unittest python -m pytest --collect-only -q -m "contracts" 2>/dev/null | head -20
} > "../$OUTPUT_DIR/test_collection.txt" 2>/dev/null || echo "  (test collection failed)"
cd .. 2>/dev/null || cd .

# Create archive in evidence directory
echo "→ Creating evidence archive..."
ARCHIVE_NAME="$(basename "$OUTPUT_DIR").tar.gz"
tar -czf "evidence/$ARCHIVE_NAME" -C "$(dirname "$OUTPUT_DIR")" "$(basename "$OUTPUT_DIR")"

echo "✅ Evidence packaged: evidence/$ARCHIVE_NAME"
echo "📊 Size: $(du -h "evidence/$ARCHIVE_NAME" | cut -f1)"
echo "📁 Contents:"
find "$OUTPUT_DIR" -type f | sort | sed 's/^/  /'
echo ""
echo "📍 Evidence location: $(pwd)/evidence/"
echo "   - Validation logs: evidence/validation_*/"
echo "   - Archive: evidence/$ARCHIVE_NAME"
echo "   - Summary: evidence/validation_*/VALIDATION_SUMMARY.md"
