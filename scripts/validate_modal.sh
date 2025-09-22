#!/bin/bash
# Complete Modal validation suite
# Usage: ./scripts/validate_modal.sh [REF]

set -euo pipefail

REF="${1:-llm/litellm@1}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EVIDENCE_DIR="evidence/validation_$TIMESTAMP"

mkdir -p "$EVIDENCE_DIR"

echo "🔍 Modal Validation Suite - REF: $REF"
echo "📁 Evidence: $EVIDENCE_DIR"
echo

# Phase 1: Tools check
echo "=== Phase 1: Tools Check ==="
make tools-check
echo

# Phase 2: Unit tests (hermetic)
echo "=== Phase 2: Unit Tests (hermetic) ==="
echo "→ Running unit tests..."
if make test-unit 2>&1 | tee "$EVIDENCE_DIR/unit_tests.log"; then
    echo "✅ Unit tests passed"
else
    echo "❌ Unit tests failed - see $EVIDENCE_DIR/unit_tests.log"
fi
echo

# Phase 3: Integration tests (no external deps)
echo "=== Phase 3: Integration Tests ==="
echo "→ Running integration tests..."
if make test-integration 2>&1 | tee "$EVIDENCE_DIR/integration_tests.log"; then
    echo "✅ Integration tests passed"
else
    echo "❌ Integration tests failed - see $EVIDENCE_DIR/integration_tests.log"
fi
echo

# Phase 4: Contract tests (behavior locks)
echo "=== Phase 4: Contract Tests ==="
echo "→ Running contract tests..."
if make test-contracts 2>&1 | tee "$EVIDENCE_DIR/contract_tests.log"; then
    echo "✅ Contract tests passed"
else
    echo "❌ Contract tests failed - see $EVIDENCE_DIR/contract_tests.log"
fi
echo

# Phase 5: Local processor build
echo "=== Phase 5: Local Build Test ==="
echo "→ Building processor locally..."
if make build-processor REF="$REF" 2>&1 | tee "$EVIDENCE_DIR/local_build.log"; then
    echo "✅ Local build succeeded"
else
    echo "❌ Local build failed - see $EVIDENCE_DIR/local_build.log"
fi
echo

# Phase 6: Acceptance tests (compose-backed)
echo "=== Phase 6: Acceptance Tests ==="
echo "→ Running PR lane acceptance tests..."
if make test-acceptance-pr 2>&1 | tee "$EVIDENCE_DIR/acceptance_pr.log"; then
    echo "✅ PR acceptance tests passed"
else
    echo "❌ PR acceptance tests failed - see $EVIDENCE_DIR/acceptance_pr.log"
fi
echo

# Phase 7: Stdout purity validation
echo "=== Phase 7: Stdout Purity Validation ==="
echo "→ Testing stdout purity contract..."
cd code
if PYTHONPATH=. DJANGO_SETTINGS_MODULE=backend.settings.unittest python -m pytest ../tests/contracts/test_stdout_purity_contract.py -v 2>&1 | tee "../$EVIDENCE_DIR/stdout_purity.log"; then
    echo "✅ Stdout purity validated"
else
    echo "❌ Stdout purity failed - see $EVIDENCE_DIR/stdout_purity.log"
fi
cd ..
echo

# Phase 8: Retry policy validation
echo "=== Phase 8: Retry Policy Validation ==="
echo "→ Testing retry policy contract..."
cd code
if PYTHONPATH=. DJANGO_SETTINGS_MODULE=backend.settings.unittest python -m pytest ../tests/contracts/test_retry_policy_contract.py -v 2>&1 | tee "../$EVIDENCE_DIR/retry_policy.log"; then
    echo "✅ Retry policy validated"
else
    echo "❌ Retry policy failed - see $EVIDENCE_DIR/retry_policy.log"
fi
cd ..
echo

# Phase 9: Environment validation
echo "=== Phase 9: Environment Validation ==="
{
    echo "=== Django Settings Check ==="
    cd code
    PYTHONPATH=. DJANGO_SETTINGS_MODULE=backend.settings.unittest python -c "
from apps.core.adapters.retry_policy import is_retryable
from apps.core.errors import ERR_OUTPUT_DUPLICATE, ERR_ADAPTER_INVOCATION
print('✓ Retry policy imports work')
print('✓ ERR_OUTPUT_DUPLICATE retryable:', is_retryable(ERR_OUTPUT_DUPLICATE))
print('✓ ERR_ADAPTER_INVOCATION retryable:', is_retryable(ERR_ADAPTER_INVOCATION))
"
    cd ..
    echo
    echo "=== Modal App Import Check ==="
    cd code
    PYTHONPATH=. IMAGE_REF="test/image@sha256:0123456789abcdef" python -c "
import modal_app
print('✓ Modal app imports successfully')
"
    cd ..
} 2>&1 | tee "$EVIDENCE_DIR/environment_check.log"
echo

# Generate dynamic validation summary
echo "=== Generating Validation Summary ==="
cat > "$EVIDENCE_DIR/VALIDATION_SUMMARY.md" <<EOF
# Modal Deploy & Test Validation Summary

## Overview
Complete validation suite for Modal execution system with surgical fixes applied.
Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")

## Test Results

EOF

# Parse actual test results
if [ -f "$EVIDENCE_DIR/unit_tests.log" ]; then
    UNIT_PASSED=$(grep -o "[0-9]* passed" "$EVIDENCE_DIR/unit_tests.log" | head -1 | cut -d' ' -f1)
    UNIT_FAILED=$(grep -o "[0-9]* failed" "$EVIDENCE_DIR/unit_tests.log" | head -1 | cut -d' ' -f1 || echo "0")
    echo "### Unit Tests" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
    echo "- **Status**: $(if [ "${UNIT_FAILED:-0}" -eq 0 ]; then echo "✅ PASS"; else echo "❌ FAIL"; fi)" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
    echo "- **Results**: ${UNIT_PASSED:-0} passed, ${UNIT_FAILED:-0} failed" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
    echo "" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
fi

if [ -f "$EVIDENCE_DIR/integration_tests.log" ]; then
    INT_PASSED=$(grep -o "[0-9]* passed" "$EVIDENCE_DIR/integration_tests.log" | head -1 | cut -d' ' -f1)
    INT_FAILED=$(grep -o "[0-9]* failed" "$EVIDENCE_DIR/integration_tests.log" | head -1 | cut -d' ' -f1 || echo "0")
    echo "### Integration Tests" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
    echo "- **Status**: $(if [ "${INT_FAILED:-0}" -eq 0 ]; then echo "✅ PASS"; else echo "❌ FAIL"; fi)" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
    echo "- **Results**: ${INT_PASSED:-0} passed, ${INT_FAILED:-0} failed" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
    echo "" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
fi

if [ -f "$EVIDENCE_DIR/contract_tests.log" ]; then
    CONTRACT_PASSED=$(grep -o "[0-9]* passed" "$EVIDENCE_DIR/contract_tests.log" | head -1 | cut -d' ' -f1)
    CONTRACT_FAILED=$(grep -o "[0-9]* failed" "$EVIDENCE_DIR/contract_tests.log" | head -1 | cut -d' ' -f1 || echo "0")
    echo "### Contract Tests" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
    echo "- **Status**: $(if [ "${CONTRACT_FAILED:-0}" -eq 0 ]; then echo "✅ PASS"; else echo "❌ FAIL"; fi)" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
    echo "- **Results**: ${CONTRACT_PASSED:-0} passed, ${CONTRACT_FAILED:-0} failed" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
    echo "" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
fi

if [ -f "$EVIDENCE_DIR/acceptance_pr.log" ]; then
    # Check for acceptance test failures
    ACCEPTANCE_STATUS="✅ PASS"
    ACCEPTANCE_RESULT="Tests executed successfully"

    if grep -q "no tests ran" "$EVIDENCE_DIR/acceptance_pr.log"; then
        ACCEPTANCE_STATUS="❌ FAIL"
        ACCEPTANCE_RESULT="No tests executed (marker mismatch)"
    elif grep -q "make.*Error [0-9]" "$EVIDENCE_DIR/acceptance_pr.log"; then
        ACCEPTANCE_STATUS="❌ FAIL"
        ACCEPTANCE_RESULT="Make command failed with exit code"
    elif grep -q "[0-9]* failed" "$EVIDENCE_DIR/acceptance_pr.log"; then
        FAILED_COUNT=$(grep -o "[0-9]* failed" "$EVIDENCE_DIR/acceptance_pr.log" | head -1 | cut -d' ' -f1)
        ACCEPTANCE_STATUS="❌ FAIL"
        ACCEPTANCE_RESULT="$FAILED_COUNT test failures"
    elif grep -q "[0-9]* passed" "$EVIDENCE_DIR/acceptance_pr.log"; then
        PASSED_COUNT=$(grep -o "[0-9]* passed" "$EVIDENCE_DIR/acceptance_pr.log" | head -1 | cut -d' ' -f1)
        ACCEPTANCE_RESULT="$PASSED_COUNT passed"
    fi

    echo "### Acceptance Tests" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
    echo "- **Status**: $ACCEPTANCE_STATUS" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
    echo "- **Results**: $ACCEPTANCE_RESULT" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
    echo "" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
fi

# Add infrastructure status
cat >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md" <<EOF
### Infrastructure
- **Local Build**: $(if grep -q "✅.*succeeded" "$EVIDENCE_DIR/local_build.log" 2>/dev/null; then echo "✅ SUCCESS"; else echo "❌ ISSUES"; fi)
- **Environment**: $(if grep -q "All refactored functionality works" "$EVIDENCE_DIR/environment_check.log" 2>/dev/null; then echo "✅ VALIDATED"; else echo "❌ ISSUES"; fi)

## Evidence Location
- **Log files**: \`$EVIDENCE_DIR/*.log\`
- **Archive command**: \`make package-evidence\`

## Overall Status
EOF

# Calculate overall status with comprehensive failure detection
FAILED=0

# Check each log file for various failure patterns
for log in "$EVIDENCE_DIR"/*.log; do
    if [ -f "$log" ]; then
        # Standard failure patterns
        if grep -qE "FAILED|ERROR|❌|failed.*[0-9]|make.*Error [0-9]|no tests ran" "$log" 2>/dev/null; then
            FAILED=1
            break
        fi
    fi
done

# Also check if any test suite in summary shows FAIL status
if [ -f "$EVIDENCE_DIR/VALIDATION_SUMMARY.md" ]; then
    if grep -q "Status.*❌ FAIL" "$EVIDENCE_DIR/VALIDATION_SUMMARY.md" 2>/dev/null; then
        FAILED=1
    fi
fi

if [ $FAILED -eq 0 ]; then
    echo "**🎉 READY FOR DEPLOYMENT** - All validation phases passed" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
else
    echo "**⚠️ ISSUES FOUND** - Review logs for details" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"
fi

echo "Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")" >> "$EVIDENCE_DIR/VALIDATION_SUMMARY.md"

# Summary
echo "=== Validation Summary ==="
echo "📊 Evidence collected in: $EVIDENCE_DIR"
echo "📋 Log files:"
find "$EVIDENCE_DIR" -name "*.log" | sort | sed 's/^/  /'

# Quick status check
echo
echo "🔍 Quick Status Check:"
for log in "$EVIDENCE_DIR"/*.log; do
    if grep -q "FAILED\|ERROR\|❌" "$log" 2>/dev/null; then
        echo "  ❌ $(basename "$log" .log): ISSUES FOUND"
        FAILED=1
    else
        echo "  ✅ $(basename "$log" .log): CLEAN"
    fi
done

if [ $FAILED -eq 0 ]; then
    echo
    echo "🎉 All validation phases passed!"
else
    echo
    echo "⚠️  Some validation phases have issues - check logs above"
fi

echo
echo "📄 Validation summary: $EVIDENCE_DIR/VALIDATION_SUMMARY.md"
echo "📦 To package evidence: make package-evidence"
