"""
Main entry point for llm_litellm processor.

This is the new foundation-based structure that will replace processor.py.
"""
import os
import sys
from pathlib import Path
from foundation.cli import parse_args
from foundation.workspace import Workspace
from foundation.io import load_json, write_json
from foundation.progress import log, progress
from libs.runtime_common.llm_runner import run_llm as run_real
from libs.runtime_common.mock_runner import run_llm as run_mock


def select_provider():
    """Select LLM provider with safety guards against mock in production."""
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    has_key = bool(os.getenv("OPENAI_API_KEY"))

    # Hard safety rules:
    # 1) If you have a real key and provider==mock -> refuse (fail fast)
    if has_key and provider == "mock":
        raise RuntimeError("OPENAI_API_KEY is set but LLM_PROVIDER=mock — refusing to run mock with a real key.")

    # 2) Default to real if you have a key (prod behavior)
    if has_key and provider in ("", "auto", "real", "litellm"):
        return "real"

    # 3) Otherwise allow explicit mock (for unit tests / local)
    if provider == "mock":
        return "mock"

    # 4) If no key and not explicitly mock, still fail (don't silently mock)
    if not has_key:
        raise RuntimeError("No OPENAI_API_KEY present and LLM_PROVIDER is not 'mock' — refusing to run.")

    return "real"  # final fallback


def run(ws: Workspace, inputs: dict, write_prefix: str) -> int:
    """Execute LLM LiteLLM processor."""
    log("starting llm_litellm processor")
    progress(0.02, phase="init")
    
    # Select provider based on environment and safety rules
    mode = select_provider()
    log(f"using provider: {mode}")
    
    # Execute with selected provider
    if mode == "real":
        result = run_real(inputs)
    else:
        result = run_mock(inputs)
    
    write_json(ws.outputs / "response.json", result)
    progress(0.85, phase="generate")
    
    # Write receipt for determinism
    receipt = {
        "processor": "llm/litellm@1",
        "status": "completed",
        "inputs_fingerprint": str(hash(str(inputs))),
        "model": result.get("model", "unknown"),
        "provider": mode,
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
