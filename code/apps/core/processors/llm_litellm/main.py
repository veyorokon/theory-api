from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

from libs.runtime_common.hashing import inputs_hash
from libs.runtime_common.fingerprint import compose_env_fingerprint
from libs.runtime_common.outputs import write_outputs, write_outputs_index
from libs.runtime_common.receipts import write_dual_receipts
from libs.runtime_common.mode import resolve_mode
from libs.runtime_common.types import ProcessorResult
from apps.core.logging import bind, clear, info, error

from .provider import make_runner  # local provider only


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser("llm_litellm")
    p.add_argument("--inputs", required=True)
    p.add_argument("--write-prefix", required=True)
    p.add_argument("--execution-id", required=True)
    return p.parse_args()


def _load_inputs(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    args = _parse_args()
    write_prefix = args.write_prefix.rstrip("/") + "/"
    payload = _load_inputs(args.inputs)
    mode = resolve_mode(payload)  # single source of truth

    # Bind processor context for logging
    bind(
        trace_id=args.execution_id,
        processor_ref="llm/litellm@1",
        mode=mode.value,
        adapter=os.getenv("RUNTIME_ADAPTER", "local"),
    )

    try:
        ih = inputs_hash(payload)
        info("processor.start", inputs_hash=ih["value"])

        t0 = time.time()

        # Log provider call
        model = payload.get("model", "gpt-4o-mini")
        info("provider.call", provider="litellm", model=model)

        runner = make_runner(config={})
        result: ProcessorResult = runner(payload)

        latency_ms = int((time.time() - t0) * 1000)
        info("provider.response", latency_ms=latency_ms, usage=result.usage)

        abs_paths = write_outputs(write_prefix, result.outputs)
        outputs_bytes = sum(len(output.bytes_) for output in result.outputs)
        info("processor.outputs", outputs_count=len(result.outputs), outputs_bytes=outputs_bytes)

        idx_path = write_outputs_index(
            execution_id=args.execution_id,
            write_prefix=write_prefix,
            paths=abs_paths,
        )

        env_fp = compose_env_fingerprint(
            image=os.getenv("IMAGE_REF", "unknown"),
            cpu=os.getenv("CPU", "1"),
            memory=os.getenv("MEMORY", "2Gi"),
        )

        receipt = {
            "execution_id": args.execution_id,
            "processor_ref": os.getenv("PROCESSOR_REF", "llm/litellm@1"),
            "image_digest": os.getenv("IMAGE_REF", "unknown"),
            "env_fingerprint": env_fp,
            "inputs_hash": ih["value"],
            "hash_schema": ih["hash_schema"],
            "outputs_index": str(idx_path),
            "mode": mode.value,
            "processor_info": result.processor_info,
            "usage": result.usage,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_ms": int((time.time() - t0) * 1000),
        }
        write_dual_receipts(args.execution_id, write_prefix, receipt)
        info("processor.receipt", receipt_path=f"{write_prefix}receipt.json")

        return 0

    except Exception as e:
        error("execution.fail", error={"code": "ERR_PROCESSOR", "message": str(e)})
        return 1

    finally:
        clear()


if __name__ == "__main__":
    sys.exit(main())
