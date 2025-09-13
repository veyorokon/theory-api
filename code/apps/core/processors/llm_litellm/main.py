"""
Main entry point for llm_litellm processor.

This is the new foundation-based structure that will replace processor.py.
"""

import os
import sys
from pathlib import Path
from typing import Optional, Tuple
from foundation.cli import parse_args
from foundation.workspace import Workspace
from foundation.io import load_json, write_json
from foundation.progress import log, progress
from libs.runtime_common.llm_runner import run_llm as run_real
from libs.runtime_common.mock_runner import run_llm as run_mock


PLACEHOLDER_KEYS = {"", "placeholder", "fake", "test", "dummy", "mock"}


def _looks_real_key(val: str | None) -> bool:
    """Check if an API key looks real (non-empty and not a placeholder)."""
    v = (val or "").strip()
    return bool(v) and v.lower() not in PLACEHOLDER_KEYS


def select_provider() -> Tuple[str, str | None]:
    """
    Resolve (provider, api_key) with sane safety + CI semantics.

    Rules:
    - provider in {"auto","",None}: "openai" if real key, else "mock"
    - provider == "mock": always mock; warn if a real key is present, but ignore it
    - provider == "openai": require a real key
    """
    provider = (os.getenv("LLM_PROVIDER") or "auto").strip().lower()
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    has_real_key = _looks_real_key(api_key)

    if provider in ("", "auto"):
        return ("openai", api_key) if has_real_key else ("mock", None)

    if provider == "mock":
        if has_real_key:
            # Don't crash CI; make the choice explicit and safe.
            print("[llm] LLM_PROVIDER=mock but OPENAI_API_KEY appears set; ignoring key.", file=sys.stderr)
        return ("mock", None)

    if provider == "openai":
        if not has_real_key:
            raise RuntimeError("LLM_PROVIDER=openai requires a non-empty OPENAI_API_KEY")
        return ("openai", api_key)

    raise RuntimeError(f"Unknown LLM_PROVIDER={provider!r}")


def run(ws: Workspace, inputs: dict, write_prefix: str) -> int:
    """Execute LLM LiteLLM processor."""
    log("starting llm_litellm processor")
    progress(0.02, phase="init")

    # Select provider based on environment and safety rules
    provider, api_key = select_provider()
    log(f"using provider: {provider}")

    # Execute with selected provider
    if provider == "mock":
        result = run_mock(inputs)
    else:  # "openai"
        result = run_real(inputs)

    write_json(ws.outputs / "response.json", result)
    progress(0.85, phase="generate")

    # Write receipt for determinism
    receipt = {
        "processor": "llm/litellm@1",
        "status": "completed",
        "inputs_fingerprint": str(hash(str(inputs))),
        "model": result.get("model", "unknown"),
        "provider": provider,
    }
    write_json(ws.outputs / "receipt.json", receipt)

    progress(1.0, phase="finalize")
    log("llm_litellm processor completed")
    return 0


def main(argv: list[str]) -> int:
    """Main entry point for processor execution."""
    args = parse_args(argv)
    ws = Workspace.setup()
    inputs = load_json(Path(args.inputs))
    return run(ws, inputs, args.write_prefix)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
