#!/usr/bin/env python3
"""
Validate chat meta.yaml files against the canonical schema.
Usage: python validate_chat_meta.py path/to/meta.yaml [path/to/another.yaml ...]
"""

import sys
import yaml
import json
from pathlib import Path
from jsonschema import validate, ValidationError

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["id", "slug", "area", "title", "owner", "state", "branch", "created", "scope", "acceptance", "outputs"],
    "properties": {
        "id": {"type": "string", "pattern": "^\\d{4}$"},
        "slug": {"type": "string", "pattern": "^[a-z0-9-]+$"},
        "area": {"type": "string", "enum": ["rt", "ld", "st", "ui", "dx", "ad", "dc"]},
        "title": {"type": "string", "minLength": 3},
        "owner": {"type": "string", "enum": ["twin", "architect", "engineer"]},
        "state": {"type": "string", "enum": ["open", "review", "merged", "closed"]},
        "branch": {"type": "string", "pattern": "^(feat|fix|chore)/[a-z]{2}-[a-z0-9-]+-\\d{4}$"},
        "created": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T"},
        "closed": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T"},
        "scope": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "non_goals": {"type": "array", "items": {"type": "string"}},
        "acceptance": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "outputs": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "gh": {
            "type": "object",
            "properties": {
                "sync_mode": {"type": "string", "enum": ["none", "issue-dryrun", "issue-live"]},
                "title_pattern": {"type": "string"},
                "labels": {"type": "array", "items": {"type": "string"}},
                "issue_body_source": {"type": "string", "enum": ["SUMMARY.md", "META"]}
            },
            "additionalProperties": False
        },
        "ci_gates": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"}
    },
    "additionalProperties": False
}


def validate_meta_file(filepath):
    """Validate a single meta.yaml file."""
    path = Path(filepath)
    if not path.exists():
        return f"ERROR: File not found: {filepath}"
    
    try:
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        validate(instance=data, schema=SCHEMA)
        return f"✅ {filepath}"
    
    except yaml.YAMLError as e:
        return f"❌ {filepath}: YAML parse error: {e}"
    
    except ValidationError as e:
        return f"❌ {filepath}: Schema validation error: {e.message}"
    
    except Exception as e:
        return f"❌ {filepath}: Unexpected error: {e}"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    errors = []
    for filepath in sys.argv[1:]:
        result = validate_meta_file(filepath)
        print(result)
        if result.startswith("❌"):
            errors.append(result)
    
    if errors:
        print(f"\n{len(errors)} validation error(s) found")
        sys.exit(1)
    else:
        print(f"\n✅ All {len(sys.argv)-1} meta.yaml files are valid")


if __name__ == "__main__":
    main()