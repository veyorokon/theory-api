"""LiteLLM processor - universal thin pattern."""

from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

from libs.runtime_common.processor import parse_args, load_inputs_json, ensure_write_prefix
from libs.runtime_common.hashing import inputs_hash
from libs.runtime_common.fingerprint import compose_env_fingerprint
from libs.runtime_common.outputs import write_outputs, write_outputs_index
from libs.runtime_common.receipts import write_dual_receipts
from apps.core.integrations.types import ProcessorResult, OutputItem
from apps.core.integrations.litellm_provider import select_litellm_runner


def process_inputs(inputs: dict) -> ProcessorResult:
    """Process LLM inputs using LiteLLM provider."""
    # Select runner (mock vs real decided by provider)
    ci = (os.getenv("CI") == "true") or (os.getenv("SMOKE") == "true")
    key = os.getenv("OPENAI_API_KEY", "")
    runner = select_litellm_runner(ci=ci, token_or_key=key)

    # Execute provider
    result = runner(inputs)

    # Convert to universal format
    outputs = []

    # Write text choices
    choices = result.get("choices", [])
    for i, choice in enumerate(choices):
        content = choice.get("message", {}).get("content", "")
        if content:
            output = OutputItem(relpath=f"outputs/choice_{i}.txt", bytes_=content.encode("utf-8"))
            outputs.append(output)

    # Write structured response
    response_output = OutputItem(
        relpath="outputs/response.json",
        bytes_=json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
    )
    outputs.append(response_output)

    # Extract usage info
    usage = {}
    if "usage" in result:
        usage_data = result["usage"]
        usage = {
            "tokens_input": float(usage_data.get("prompt_tokens", 0)),
            "tokens_output": float(usage_data.get("completion_tokens", 0)),
        }

    return ProcessorResult(
        outputs=outputs,
        processor_info=f"litellm/{result.get('model', 'unknown')}",
        usage=usage,
        extra={"provider": "mock" if ci else "openai"},
    )


def main() -> int:
    """Universal thin processor main entry point."""
    args = parse_args()
    ensure_write_prefix(args.write_prefix)
    payload = load_inputs_json(args.inputs)

    # Canonical inputs hash
    ih = inputs_hash(payload)

    # Process inputs
    t0 = time.time()
    result = process_inputs(payload)
    duration_ms = int((time.time() - t0) * 1000)

    # Write outputs and index
    abs_paths = write_outputs(args.write_prefix, result.outputs)
    idx_path = write_outputs_index(execution_id=args.execution_id, write_prefix=args.write_prefix, paths=abs_paths)

    # Environment fingerprint
    env_fp = compose_env_fingerprint(
        image=os.getenv("IMAGE_REF", "unknown"), cpu=os.getenv("CPU", "1"), memory=os.getenv("MEMORY", "2Gi")
    )

    # Dual receipts
    receipt = {
        "execution_id": args.execution_id,
        "processor_ref": os.getenv("PROCESSOR_REF", "llm/litellm@1"),
        "image_digest": os.getenv("IMAGE_REF", "unknown"),
        "env_fingerprint": env_fp,
        "inputs_hash": ih["value"],
        "hash_schema": ih["hash_schema"],
        "outputs_index": str(idx_path),
        "processor_info": result.processor_info,
        "usage": result.usage,
        "extra": result.extra,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_ms": duration_ms,
    }
    write_dual_receipts(args.execution_id, args.write_prefix, receipt)

    # Optional CLI response
    resp_path = Path(args.write_prefix) / "response.json"
    resp_path.write_text(
        json.dumps(
            {"ok": True, "processor_info": result.processor_info, "outputs": [str(p) for p in abs_paths]},
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
