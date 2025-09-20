"""
Django-free processor utilities shared by all processors.

Thin helpers for standard processor operations - no Django imports allowed.
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict


# Canonical error messages - used across all processors
ERR_SECRET_MISSING = "ERR_SECRET_MISSING"
ERR_INPUT_UNSUPPORTED = "ERR_INPUT_UNSUPPORTED"
ERR_IMAGE_UNPINNED = "ERR_IMAGE_UNPINNED"
ERR_DEP_MISSING = "ERR_DEP_MISSING"


@dataclass
class ProviderConfig:
    """Generic provider configuration for processors."""

    mock: bool = False
    api_key: str | None = None
    api_token: str | None = None
    model: str | None = None
    extra: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}


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


def ensure_write_prefix(prefix: str) -> str:
    """Ensure write prefix directory exists and return the prefix."""
    Path(prefix).mkdir(parents=True, exist_ok=True)
    return prefix


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


def validate_and_normalize_v1(inputs: Dict[str, Any], *, allowed_modes=None) -> Dict[str, Any]:
    """
    Validate and normalize inputs to v1 schema.

    Args:
        inputs: Raw input dictionary
        allowed_modes: Set of allowed mode values (default: {"default", "mock"})

    Returns:
        Normalized v1 inputs: {schema, model?, params, files[], mode, metadata?}

    Raises:
        ValueError: Invalid inputs or unsupported mode
    """
    if allowed_modes is None:
        allowed_modes = {"default", "mock"}

    # If already v1 schema, validate and return
    if inputs.get("schema") == "v1":
        normalized = inputs.copy()
    else:
        # Legacy shape normalization
        normalized = {"schema": "v1"}

        # LiteLLM legacy: {"messages": [...]} → params
        if "messages" in inputs:
            normalized["params"] = {"messages": inputs["messages"]}
            # Copy other llm params
            for key in ["model", "temperature", "max_tokens"]:
                if key in inputs:
                    if key == "model":
                        normalized["model"] = inputs[key]
                    else:
                        normalized["params"][key] = inputs[key]

        # Replicate legacy: {"model": "...", "input": {...}} → model + params
        elif "input" in inputs:
            normalized["params"] = inputs["input"]
            if "model" in inputs:
                normalized["model"] = inputs["model"]

        # Generic params passthrough
        else:
            normalized["params"] = {
                k: v for k, v in inputs.items() if k not in ["schema", "model", "files", "mode", "metadata"]
            }
            if "model" in inputs:
                normalized["model"] = inputs["model"]

    # Ensure required fields exist
    if "params" not in normalized:
        normalized["params"] = {}
    if "files" not in normalized:
        normalized["files"] = []
    if "mode" not in normalized:
        normalized["mode"] = "default"

    # Validate mode
    mode = normalized["mode"]
    if mode not in allowed_modes:
        raise ValueError(f"{ERR_INPUT_UNSUPPORTED}: mode '{mode}' not in allowed modes {allowed_modes}")

    # Mode guardrails: mock only allowed in CI/SMOKE environments
    if mode == "mock":
        ci = os.getenv("CI") == "true" or os.getenv("SMOKE") == "true"
        if not ci:
            # Downgrade to default in non-CI environments
            normalized["mode"] = "default"

    # Validate files is a list
    if not isinstance(normalized["files"], list):
        # Best effort coercion
        if isinstance(normalized["files"], dict):
            normalized["files"] = [normalized["files"]]
        else:
            normalized["files"] = []

    return normalized


def build_config_from_env() -> Dict[str, Any]:
    """
    Build provider config from environment variables.

    Returns:
        Config dict with CI detection, tokens, timeouts
    """
    ci = os.getenv("CI") == "true" or os.getenv("SMOKE") == "true"

    return {
        "ci": ci,
        "openai_token": os.getenv("OPENAI_API_KEY", ""),
        "replicate_token": os.getenv("REPLICATE_API_TOKEN", ""),
        "litellm_timeout": int(os.getenv("LITELLM_TIMEOUT_S", "30")),
        "replicate_timeout": int(os.getenv("REPLICATE_TIMEOUT_S", "120")),
        "llm_provider": os.getenv("LLM_PROVIDER", "auto"),
    }


def validate_outputs_prefix(outputs) -> None:
    """
    Validate that all OutputItem relpath start with 'outputs/'.

    Args:
        outputs: List of OutputItem objects

    Raises:
        ValueError: If any output doesn't start with 'outputs/'
    """
    for output in outputs:
        if not output.relpath.startswith("outputs/"):
            raise ValueError(f"OutputItem relpath must start with 'outputs/', got: {output.relpath}")


def canonical_error_message(error_code: str, detail: str) -> str:
    """
    Create canonical error message format.

    Args:
        error_code: One of the ERR_* constants
        detail: Specific error details

    Returns:
        Formatted error message
    """
    return f"{error_code}: {detail}"
