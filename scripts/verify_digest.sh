#!/bin/bash
# Verify image digest format and availability
# Usage: ./scripts/verify_digest.sh <digest_ref>

set -euo pipefail

DIGEST_REF="${1:-}"

if [ -z "$DIGEST_REF" ]; then
    echo "Usage: $0 <digest_ref>"
    echo "Example: $0 ghcr.io/username/image@sha256:abc123..."
    exit 1
fi

echo "🔍 Verifying digest: $DIGEST_REF"

# Validate digest format
if [[ ! "$DIGEST_REF" =~ @sha256:[a-f0-9]{64}$ ]]; then
    echo "❌ Invalid digest format. Expected: registry/image@sha256:<64-hex-chars>"
    exit 1
fi

echo "✅ Digest format valid"

# Extract components
REGISTRY_IMAGE="${DIGEST_REF%@*}"
DIGEST="${DIGEST_REF#*@}"

echo "📦 Registry/Image: $REGISTRY_IMAGE"
echo "🔒 Digest: $DIGEST"

# Test digest availability (requires Docker)
if command -v docker >/dev/null 2>&1; then
    echo "🐳 Testing digest availability..."
    if docker manifest inspect "$DIGEST_REF" >/dev/null 2>&1; then
        echo "✅ Digest is accessible"

        # Show manifest info
        echo "📋 Manifest info:"
        docker manifest inspect "$DIGEST_REF" | jq -r '
          "  Architecture: " + (.architecture // "unknown") +
          "\n  OS: " + (.os // "unknown") +
          "\n  Size: " + ((.config.size // 0) | tostring) + " bytes"
        ' 2>/dev/null || echo "  (manifest details unavailable)"
    else
        echo "❌ Digest not accessible or requires authentication"
        exit 1
    fi
else
    echo "⚠️  Docker not available - skipping availability check"
fi

echo "✅ Digest verification complete"
