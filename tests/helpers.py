"""Test helpers for invoking processors via orchestrator."""

from typing import Any, Dict, Optional
from apps.core.tool_runner import ToolRunner
from apps.core.registry.loader import load_processor_spec
from apps.storage.service import storage_service


def invoke_processor(
    ref: str,
    inputs: Dict[str, Any],
    *,
    mode: str = "mock",
    build: bool = True,
    stream: bool = False,
    write_prefix: str | None = None,
    timeout_s: int = 120,
    adapter: str = "local",
) -> Dict[str, Any]:
    """
    Invoke processor via ToolRunner (same path as production).

    This exercises the full prod flow:
    1. Load registry.yaml (declared outputs)
    2. Generate put_urls with storage_service.get_upload_url()
    3. Send RunInvoke over WS
    4. Validate resulting envelope

    Args:
        ref: Processor reference (e.g., "llm/litellm@1")
        inputs: Input payload for processor
        mode: Execution mode ("mock" or "real")
        build: Whether to build image locally (True for tests)
        stream: Whether to stream events (usually False for assertions)
        write_prefix: Custom write prefix (defaults to /artifacts/outputs/test/{execution_id}/)
        timeout_s: Timeout in seconds
        adapter: Adapter to use ("local" for tests)

    Returns:
        Success envelope dict with status, outputs, meta, etc.

    Raises:
        Exception: If processor invocation fails
    """
    orch = ToolRunner()

    return orch.invoke(
        ref=ref,
        mode=mode,
        inputs=inputs,
        build=build,
        stream=stream,
        timeout_s=timeout_s,
        write_prefix=write_prefix or "/artifacts/outputs/test/{execution_id}/",
        world_facet="artifacts",
        adapter=adapter,
    )


def build_put_urls(write_prefix: str, outputs_decl: list[dict], bucket: str = "media") -> dict[str, str]:
    """
    Build presigned PUT URLs for processor outputs (mirrors orchestrator logic).

    This is only used for direct WS protocol testing. Normal tests should use
    invoke_processor() which exercises the full orchestration flow.

    Args:
        write_prefix: Write prefix template (e.g., "/artifacts/{execution_id}/")
        outputs_decl: Processor outputs declaration from registry
        bucket: Storage bucket name

    Returns:
        Dict mapping output keys to presigned PUT URLs
    """

    def _key(prefix: str, tail: str) -> str:
        p = prefix[1:] if prefix.startswith("/") else prefix
        if not p.endswith("/"):
            p += "/"
        return f"{p}{tail}"

    put_urls = {}

    # Index (always last)
    put_urls["outputs.json"] = storage_service.get_upload_url(
        bucket=bucket, key=_key(write_prefix, "outputs.json"), expires_in=900, content_type="application/json"
    )

    # Declared outputs
    for o in outputs_decl or []:
        rel = o.get("path")
        if not rel:
            continue
        put_urls[f"outputs/{rel}"] = storage_service.get_upload_url(
            bucket=bucket,
            key=_key(write_prefix, f"outputs/{rel}"),
            expires_in=900,
            content_type=(o.get("mime") or "application/octet-stream"),
        )

    return put_urls


def build_ws_payload(
    ref: str, execution_id: str, write_prefix: str, mode: str = "mock", inputs: Dict = None, bucket: str = "media"
) -> Dict:
    """
    Build complete WebSocket RunOpen payload with presigned URLs.

    DRY helper that loads processor spec and builds put_urls automatically.

    Args:
        ref: Processor reference (e.g., "llm/litellm@1")
        execution_id: Execution ID
        write_prefix: Write prefix template
        mode: Execution mode ("mock" or "real")
        inputs: Input payload
        bucket: Storage bucket

    Returns:
        Complete RunOpen frame payload
    """
    spec = load_processor_spec(ref)
    outputs_decl = spec.get("outputs", [])
    put_urls = build_put_urls(write_prefix, outputs_decl, bucket)

    return {
        "kind": "RunOpen",
        "content": {
            "role": "client",
            "execution_id": execution_id,
            "payload": {
                "execution_id": execution_id,
                "write_prefix": write_prefix,
                "schema": "v1",
                "mode": mode,
                "put_urls": put_urls,
                "inputs": inputs or {},
            },
        },
    }
