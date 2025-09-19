"""Replicate processor - universal thin pattern."""

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
from apps.core.integrations.replicate_provider import select_replicate_runner


def process_inputs(inputs: dict) -> ProcessorResult:
    """Process inputs using Replicate provider."""
    # Select runner (mock vs real decided by provider)
    ci = (os.getenv("CI") == "true") or (os.getenv("SMOKE") == "true")
    token = os.getenv("REPLICATE_API_TOKEN", "")
    runner = select_replicate_runner(ci=ci, token_or_key=token)

    # Execute provider
    result = runner(inputs)

    # Convert to universal format
    outputs = []

    # Handle different output types from Replicate
    if isinstance(result, dict):
        # Handle structured output
        if "output" in result:
            output_data = result["output"]
            if isinstance(output_data, str):
                # Text output
                output = OutputItem(relpath="outputs/result.txt", bytes_=output_data.encode("utf-8"))
                outputs.append(output)
            elif isinstance(output_data, list):
                # Multiple outputs
                for i, item in enumerate(output_data):
                    if isinstance(item, str):
                        if item.startswith("http"):
                            # URL - we'd need to download, for now just save URL
                            output = OutputItem(relpath=f"outputs/url_{i}.txt", bytes_=item.encode("utf-8"))
                        else:
                            # Text content
                            output = OutputItem(relpath=f"outputs/result_{i}.txt", bytes_=item.encode("utf-8"))
                        outputs.append(output)

        # Always save full response
        response_output = OutputItem(
            relpath="outputs/response.json",
            bytes_=json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )
        outputs.append(response_output)

    # Extract usage/metrics if available
    usage = {}
    if isinstance(result, dict) and "metrics" in result:
        metrics = result["metrics"]
        usage = {
            "predict_time": float(metrics.get("predict_time", 0)),
            "total_time": float(metrics.get("total_time", 0)),
        }

    return ProcessorResult(
        outputs=outputs,
        processor_info=f"replicate/{inputs.get('version', 'unknown')}",
        usage=usage,
        extra={"provider": "mock" if ci else "replicate"},
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
        "processor_ref": os.getenv("PROCESSOR_REF", "replicate/generic@1"),
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
