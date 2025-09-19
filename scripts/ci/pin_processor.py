#!/usr/bin/env python3
"""Pin processor image to specific digest with validation."""

import sys
import yaml
import pathlib
import re
import json


def main():
    """Pin processor image to digest with schema validation."""
    if len(sys.argv) != 4:
        print("Usage: pin_processor.py <processor> <image_base> <digest>", file=sys.stderr)
        print("Example: pin_processor.py llm_litellm ghcr.io/owner/llm-litellm sha256:abc123...", file=sys.stderr)
        sys.exit(2)

    processor, image_base, digest = sys.argv[1:]

    # Validate digest format
    if not re.match(r"^sha256:[0-9a-f]{64}$", digest):
        print(f"ERROR: Invalid digest format: {digest}", file=sys.stderr)
        print("Expected format: sha256:64-hex-chars", file=sys.stderr)
        sys.exit(2)

    # Locate registry file
    registry_path = pathlib.Path(f"code/apps/core/registry/processors/{processor}.yaml")
    if not registry_path.exists():
        print(f"ERROR: Registry file not found: {registry_path}", file=sys.stderr)
        sys.exit(2)

    # Load and validate current registry
    try:
        doc = yaml.safe_load(registry_path.read_text())
    except yaml.YAMLError as e:
        print(f"ERROR: Invalid YAML in {registry_path}: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"ERROR: Cannot read {registry_path}: {e}", file=sys.stderr)
        sys.exit(2)

    # Minimal schema validation
    if "image" not in doc or not isinstance(doc["image"], dict):
        print(f"ERROR: Registry file missing or invalid image block: {registry_path}", file=sys.stderr)
        sys.exit(2)

    # Record old reference for audit
    old_ref = doc["image"].get("oci", "")
    new_ref = f"{image_base}@{digest}"

    # Update image reference
    doc["image"]["oci"] = new_ref

    # Write back to registry
    try:
        registry_path.write_text(yaml.safe_dump(doc, sort_keys=False))
    except Exception as e:
        print(f"ERROR: Cannot write {registry_path}: {e}", file=sys.stderr)
        sys.exit(2)

    # Output audit information as JSON
    result = {"processor": processor, "old": old_ref, "new": new_ref, "file": str(registry_path)}
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
