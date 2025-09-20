#!/usr/bin/env python3
"""Extract pinned image reference from registry YAML with validation."""

import sys
import yaml
import pathlib


def main():
    """Extract and validate image reference from registry."""
    registry_path = pathlib.Path("code/apps/core/registry/processors/llm_litellm.yaml")

    if not registry_path.exists():
        print(f"ERROR: Registry file not found: {registry_path}", file=sys.stderr)
        sys.exit(2)

    try:
        doc = yaml.safe_load(registry_path.read_text())
    except yaml.YAMLError as e:
        print(f"ERROR: Invalid YAML in {registry_path}: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"ERROR: Cannot read {registry_path}: {e}", file=sys.stderr)
        sys.exit(2)

    # Extract image reference
    image_section = doc.get("image", {})
    if not isinstance(image_section, dict):
        print("ERROR: Missing or invalid image section in registry", file=sys.stderr)
        sys.exit(2)

    ref = image_section.get("oci")
    if not ref:
        print("ERROR: Missing image.oci field in registry", file=sys.stderr)
        sys.exit(2)

    # Validate digest format
    if "@sha256:" not in ref:
        print(f"ERROR: Image reference not pinned by digest: {ref}", file=sys.stderr)
        sys.exit(2)

    # Output clean reference
    print(ref)
    return 0


if __name__ == "__main__":
    sys.exit(main())
