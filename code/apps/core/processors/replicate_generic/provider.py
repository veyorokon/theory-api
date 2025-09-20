# apps/core/processors/replicate_generic/provider.py
from __future__ import annotations
import json
import mimetypes
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple
from urllib.parse import urlparse

# Import from runtime_common instead of defining locally
from libs.runtime_common.outputs import OutputItem
from libs.runtime_common.asset_downloader import download_asset, AssetDownloadError
from libs.runtime_common.asset_policy import get_asset_download_config
from libs.runtime_common.asset_naming import create_asset_receipt


@dataclass
class ProcessorResult:
    outputs: List[OutputItem]
    processor_info: str
    usage: Mapping[str, float]
    extra: Mapping[str, Any]


# --- Helpers (no Django; keep container friendly) --------------------------------


def _is_mock_mode(inputs: Dict[str, Any], config: Dict[str, Any]) -> bool:
    if str(inputs.get("mode", "")).lower() == "mock":
        return True
    if os.getenv("CI") == "true" or os.getenv("SMOKE") == "true":
        return True
    return False


def _now_utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _serialize_result(obj: Any) -> Any:
    """Convert Replicate result objects to JSON-serializable format."""
    if hasattr(obj, "url"):  # FileOutput object
        return str(obj.url)
    elif isinstance(obj, list):
        return [_serialize_result(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: _serialize_result(v) for k, v in obj.items()}
    else:
        # For primitive types, return as-is
        return obj


def _looks_url(x: Any) -> bool:
    if not isinstance(x, str):
        return False
    try:
        u = urlparse(x)
        return u.scheme in ("http", "https") and bool(u.netloc)
    except Exception:
        return False


def _flatten_assets(obj: Any) -> List[str]:
    """
    Extract candidate asset URLs from Replicate results. Replicate can return:
      - a single URL string
      - a list of URL strings
      - nested dicts/lists with URLs in values
    """
    out: List[str] = []

    def rec(v: Any) -> None:
        if _looks_url(v):
            out.append(v)  # type: ignore[arg-type]
            return
        if isinstance(v, list):
            for it in v:
                rec(it)
        elif isinstance(v, dict):
            for it in v.values():
                rec(it)

    rec(obj)
    return out


def _safe_ext_from_content_type(content_type: str | None) -> str:
    # Map common image content types; otherwise guess via mimetypes
    if not content_type:
        return ".bin"
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "application/json": ".json",
        "text/plain": ".txt",
    }
    return mapping.get(content_type.split(";")[0].strip().lower(), mimetypes.guess_extension(content_type) or ".bin")


# Legacy function - replaced by deterministic naming
# Kept for backward compatibility but no longer used
def _basename_from_url(u: str) -> str:
    name = os.path.basename(urlparse(u).path) or "file"
    # sanitize to avoid traversal or weird chars
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name[:100]  # cap length


# --- Asset download configuration (using centralized downloader) ----------------

# --- Mock payload ----------------------------------------------------------------


def _mock_payload(model: str, params: Dict[str, Any]) -> Dict[str, Any]:
    prompt = params.get("prompt")
    desc = f"mock replicate result for {model}"
    if isinstance(prompt, str) and prompt:
        desc += f" | prompt={prompt[:80]}"
    return {
        "id": "mock-replicate-0000",
        "model": model,
        "created": _now_utc_iso(),
        "result": {
            "images": ["mock://image-0", "mock://image-1"],
            "note": desc,
        },
        "usage": {"credits": 0.0},
    }


def _normalize_usage(raw: Any) -> Dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, float] = {}
    for k in ("credits", "input_tokens", "output_tokens", "total_tokens"):
        v = raw.get(k)
        if isinstance(v, (int, float)):
            out[k] = float(v)
    return out


# --- Public provider factory ------------------------------------------------------


def make_runner(config):
    """
    Factory returning a callable runner for Replicate from ProviderConfig.
    """
    from libs.runtime_common.processor import ProviderConfig

    default_model = config.model or "black-forest-labs/flux-schnell"
    mock_mode = config.mock

    # Get asset download configuration from policy system
    dl_cfg = get_asset_download_config("replicate/generic@1")

    def runner(inputs: Dict[str, Any]) -> ProcessorResult:
        model = str(inputs.get("model") or default_model)
        params: Dict[str, Any] = dict(inputs.get("params") or {})

        # Zero-egress path
        if mock_mode or _is_mock_mode(inputs, {}):
            payload = _mock_payload(model, params)
            out = OutputItem(
                relpath="outputs/response.json",
                bytes_=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            )
            # (No binary assets in mock mode)
            return ProcessorResult(
                outputs=[out],
                processor_info=f"replicate:{model}",
                usage=_normalize_usage(payload.get("usage")),
                extra={"mock": "true"},
            )

        # Real path — import SDK only when needed
        try:
            import replicate  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("replicate SDK not installed in this image") from e

        token = os.getenv("REPLICATE_API_TOKEN", "")
        if not token.strip():
            raise RuntimeError("missing API token in REPLICATE_API_TOKEN")

        try:
            client = replicate.Client(api_token=token)
            # Replicate “run” accepts "owner/model:version" and input params
            result = client.run(model, input=params)

            # The result can be URL(s), lists, dicts. Build a response payload
            # Convert FileOutput objects to strings for JSON serialization
            serializable_result = _serialize_result(result)
            payload = {
                "id": getattr(result, "id", None) or f"replicate-run-{int(time.time())}",
                "model": model,
                "created": _now_utc_iso(),
                "result": serializable_result,
            }

            outputs: List[OutputItem] = [
                OutputItem(
                    relpath="outputs/response.json",
                    bytes_=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                )
            ]

            # Optional asset downloads (safe, bounded)
            if dl_cfg.enabled:
                urls = _flatten_assets(serializable_result)
                for idx, url in enumerate(urls):
                    # only http(s) (mock:// is ignored)
                    if not _looks_url(url):
                        continue
                    try:
                        data, content_type = download_asset(url, dl_cfg)
                    except AssetDownloadError as e:
                        # Skip failed asset, but still produce canonical response.json
                        continue

                    # Create deterministic asset receipt
                    receipt = create_asset_receipt(
                        content=data,
                        source_url=url,
                        content_type=content_type,
                        additional_metadata={"asset_index": str(idx)},
                    )

                    # Use deterministic filename with index prefix for ordering
                    rel = f"outputs/assets/{idx:02d}_{receipt.filename}"
                    outputs.append(
                        OutputItem(
                            relpath=rel,
                            bytes_=data,
                            meta={
                                "source_url": url,
                                "content_hash": receipt.content_hash,
                                "content_size": str(receipt.content_size),
                                "download_timestamp": receipt.download_timestamp,
                                "content_type": receipt.content_type or "unknown",
                            },
                        )
                    )

            return ProcessorResult(
                outputs=outputs,
                processor_info=f"replicate:{model}",
                usage={},  # Replicate credits usage isn’t always in the run result; keep empty unless you collect it separately
                extra={},
            )
        except Exception:
            # Bubble up; the outer main/adapter will map to canonical error envelope
            raise

    return runner
