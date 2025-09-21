## Summary
<!-- One-liner: smallest correct change that keeps CI green -->

## Lane & Architecture
- **Lane**: <!-- PR (test current source) OR Dev/Main (test pinned artifacts) -->
- **Contract Impact**: <!-- Envelope/paths/error codes/fingerprints affected -->
- **Processor Changes**: <!-- Django-free compliance if touching processors -->

## Traceability
- Issue: <!-- #123 or link (if applicable) -->
- Follow-up: <!-- Issues this creates/blocks (if any) -->

## Engineering Checklist
- [ ] **Smallest change**: ≤3 files, ≤150 LoC (unless justified)
- [ ] **Tests first**: Positive test + negative test included
- [ ] **No cross-layer leaks**: Processors Django-free, adapters return envelopes
- [ ] **Lane correct**: PR lane uses `--build`, Dev/Main uses pinned artifacts
- [ ] **CI green**: All tests pass before requesting review

## Tests & Validation
- [ ] Unit tests: `make test-unit` passes
- [ ] Integration tests pass (if applicable)
- [ ] PR lane acceptance: `make test-acceptance-pr` passes (if PR lane)
- [ ] No dead code: `make deadcode` passes

## Risk & Rollout
- Risk: <!-- low/med/high + why -->
- Backout: <!-- exact steps -->

## Contract Changes (if applicable)
- **Envelope format**: <!-- Success/error envelope changes -->
- **Error codes**: <!-- New ERR_* codes or changes to existing -->
- **Fingerprint**: <!-- env_fingerprint component changes -->
- **Receipts**: <!-- Receipt field additions/changes -->

## Local Verification
```bash
# Run appropriate test suite for your lane
make test-unit                    # Always run
make test-acceptance-pr          # If PR lane (testing current source)
make test-acceptance             # If Dev/Main lane (testing pinned artifacts)
make deadcode                    # Dead code check
```

## Screenshots / Artifacts
<!-- Include any relevant outputs, logs, or artifacts -->
