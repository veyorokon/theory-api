"""I/O utilities for processors."""
import json
import io
import tarfile
import os
from pathlib import Path
from typing import Any

JSON_SEPARATORS = (",", ":")


def write_json(path: Path, obj: Any) -> None:
    """Write JSON with compact separators."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=JSON_SEPARATORS)


def load_json(path: Path) -> dict:
    """Load JSON from file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def tar_dir_as_bytes(root: str) -> bytes:
    """Create gzipped tar of directory as bytes."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for base, _, files in os.walk(root):
            for fn in files:
                full = os.path.join(base, fn)
                arc = os.path.relpath(full, root)
                tf.add(full, arcname=arc)
    buf.seek(0)
    return buf.read()