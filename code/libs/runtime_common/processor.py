"""
Django-free processor utilities shared by all processors.

Thin helpers for standard processor operations - no Django imports allowed.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, UTC
from pathlib import Path
from typing import Any, Dict


def parse_args(argv: list[str] = None) -> argparse.Namespace:
    """Parse standard processor arguments."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", required=True, help="Path to inputs.json")
    parser.add_argument("--write-prefix", required=True, help="Output write prefix")
    parser.add_argument("--execution-id", required=True, help="Execution ID")
    return parser.parse_args(argv)


def load_inputs_json(path: str) -> Dict[str, Any]:
    """Load inputs from JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_inputs(path: str) -> Dict[str, Any]:
    """Load inputs from JSON file (alias for backwards compatibility)."""
    return load_inputs_json(path)


def ensure_write_prefix(prefix: str) -> None:
    """Ensure write prefix directory exists."""
    Path(prefix).mkdir(parents=True, exist_ok=True)


def progress(msg: str) -> None:
    """Write progress message to stdout (single line)."""
    print(msg, flush=True)


def utc_now_iso() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


def monotonic_ms(start_ns: int) -> int:
    """Get milliseconds elapsed since start_ns (from time.perf_counter_ns)."""
    return int((time.perf_counter_ns() - start_ns) / 1_000_000)


def write_json(path: str, payload: Dict[str, Any]) -> None:
    """Write JSON payload to file with canonical formatting."""
    json_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(json_str)
