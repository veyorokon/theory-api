from pathlib import Path
from .hashing import blake3_hex


def content_cid8(b: bytes) -> str:
    """Generate 8-character content identifier from bytes."""
    return blake3_hex(b)[:8]


def write_text_file(root: Path, name: str, idx: int, text: str, ext: str = "txt") -> Path:
    """
    Write text file with content-addressed naming.

    Args:
        root: Root directory for output
        name: Base name for file
        idx: Index for multiple outputs
        text: Text content to write
        ext: File extension

    Returns:
        Path to written file
    """
    b = text.encode("utf-8")
    fp = root / f"{name}-{idx}-{content_cid8(b)}.{ext}"
    fp.write_text(text, encoding="utf-8")
    return fp


def write_json_file(root: Path, name: str, idx: int, obj: dict) -> Path:
    """
    Write JSON file with content-addressed naming.

    Args:
        root: Root directory for output
        name: Base name for file
        idx: Index for multiple outputs
        obj: Object to serialize as JSON

    Returns:
        Path to written file
    """
    import json

    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    fp = root / f"{name}-{idx}-{content_cid8(s.encode('utf-8'))}.json"
    fp.write_text(s, encoding="utf-8")
    return fp
