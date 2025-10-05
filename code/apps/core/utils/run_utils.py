"""Shared utilities for tool run commands (localctl/modalctl)."""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from backend.storage.artifact_store import artifact_store


def parse_inputs(options: Dict[str, Any]) -> Dict[str, Any]:
    """Parse JSON inputs from various sources with priority handling.

    Priority: stdin > file > json > jsonstr
    """
    inputs_jsonstr = options.get("inputs_jsonstr", "{}")
    inputs_json = options.get("inputs_json")
    inputs_file = options.get("inputs_file")
    inputs_stdin = options.get("inputs")

    try:
        if inputs_stdin == "-":
            json_text = sys.stdin.read()
            if not json_text.strip():
                return json.loads("{}")
            return json.loads(json_text)
        elif inputs_file:
            with open(inputs_file, encoding="utf-8") as f:
                return json.load(f)
        elif inputs_json:
            return json.loads(inputs_json)
        else:
            # Legacy string parsing
            if inputs_jsonstr != "{}":
                import warnings

                warnings.warn(
                    "--inputs-jsonstr is deprecated, use --inputs-json for cleaner syntax",
                    DeprecationWarning,
                    stacklevel=2,
                )
            return json.loads(inputs_jsonstr)
    except json.JSONDecodeError as e:
        if inputs_stdin == "-":
            source = "stdin"
        elif inputs_file:
            source = f"file '{inputs_file}'"
        elif inputs_json:
            source = "--inputs-json"
        else:
            source = "--inputs-jsonstr"
        raise RuntimeError(f"Invalid JSON in {source}: {e}") from e
    except FileNotFoundError as e:
        raise RuntimeError(f"Input file not found: {inputs_file}") from e


def materialize_attachments(attachments: List[str]) -> Dict[str, Dict[str, Any]]:
    """Materialize attachment files and return mapping."""
    if not attachments:
        return {}

    attachment_map = {}

    for attach_spec in attachments:
        if "=" not in attach_spec:
            raise ValueError(f"Invalid attachment format: {attach_spec} (expected name=path)")

        name, path = attach_spec.split("=", 1)
        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"Attachment file not found: {path}")

        # Read file data
        with open(file_path, "rb") as f:
            data = f.read()

        # Compute CID
        cid = artifact_store.compute_cid(data)

        # Determine MIME type
        import mimetypes

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"

        # Store in artifact store
        artifact_path = f"/artifacts/inputs/{cid}/{file_path.name}"
        artifact_store.put_bytes(artifact_path, data, mime_type)

        attachment_map[name] = {"$artifact": artifact_path, "cid": cid, "mime": mime_type}

    return attachment_map


def rewrite_attach_references(obj: Any, attachment_map: Dict[str, Dict[str, Any]]) -> Any:
    """Recursively rewrite $attach references to $artifact."""
    if isinstance(obj, dict):
        if "$attach" in obj and len(obj) == 1:
            attach_name = obj["$attach"]
            if attach_name in attachment_map:
                return attachment_map[attach_name]
            else:
                raise ValueError(f"Attachment '{attach_name}' not found")
        return {k: rewrite_attach_references(v, attachment_map) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [rewrite_attach_references(item, attachment_map) for item in obj]
    return obj


def download_all_outputs(outputs: List[Dict[str, Any]], save_dir: str) -> None:
    """Download all outputs to save_dir, mirroring world paths."""
    save_path = Path(save_dir)
    save_path.mkdir(parents=True, exist_ok=True)

    for output in outputs:
        if not isinstance(output, dict) or "path" not in output:
            continue

        world_path = output["path"]
        rel_path = world_path.lstrip("/")
        local_path = save_path / rel_path

        local_path.parent.mkdir(parents=True, exist_ok=True)

        content = artifact_store.get_bytes(world_path)
        with open(local_path, "wb") as f:
            f.write(content)


def download_first_output(outputs: List[Dict[str, Any]], save_path: str) -> None:
    """Download only the first output to save_path."""
    if not outputs or not isinstance(outputs[0], dict) or "path" not in outputs[0]:
        return

    output = outputs[0]
    world_path = output["path"]
    local_path = Path(save_path)

    local_path.parent.mkdir(parents=True, exist_ok=True)

    content = artifact_store.get_bytes(world_path)
    with open(local_path, "wb") as f:
        f.write(content)
