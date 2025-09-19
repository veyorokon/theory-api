import os
import platform
from typing import Dict, Iterable, List
from .hashing import blake3_hex


def compose_env_fingerprint(**kv) -> str:
    """
    Compose environment fingerprint from key-value pairs.

    Args:
        **kv: Environment key-value pairs

    Returns:
        Semicolon-separated sorted key=value string
    """
    items = [f"{k}={v}" for k, v in kv.items() if v not in (None, "")]
    return ";".join(sorted(items))


def memo_key(*, provider: str, model: str, inputs_hash: str) -> str:
    """
    Generate deterministic memo key for caching/idempotency.

    Args:
        provider: Provider name (e.g., "litellm", "replicate")
        model: Model name/identifier
        inputs_hash: Hash of canonicalized inputs

    Returns:
        BLAKE3 hex hash of memo key components
    """
    parts = [
        f"provider={provider}",
        f"model={model}",
        f"inputs_hash={inputs_hash}",
        f"code_version={os.getenv('CODE_VERSION', 'dev')}",
        f"env_lite=py={platform.python_version()};arch={platform.machine()}",
    ]
    return blake3_hex(";".join(parts).encode("utf-8"))


def collect_present_env_keys(
    base_keys: Iterable[str] | None = None,
    additional_keys: Iterable[str] | None = None,
) -> List[str]:
    """
    Collect the union of env var names from the provided lists that are present in os.environ.
    Values are NEVER included. The result is sorted for stability.
    """
    keys = set()
    for src in (base_keys or []), (additional_keys or []):
        for k in src:
            if k and k in os.environ:
                keys.add(k)
    return sorted(keys)


def _norm_gpu(gpu: object) -> str:
    if gpu is None:
        return "none"
    s = str(gpu).strip()
    return s if s else "none"


def compose_env_fingerprint_extended(
    *,
    image_digest: str,
    runtime: Dict[str, object],
    versions: Dict[str, str] | None = None,
    present_env_keys: Iterable[str] | None = None,
    snapshot: str = "off",
    region: str | None = None,
    adapter: str,
) -> str:
    """
    Produce a stable, human-readable fingerprint string. Field order is fixed.
    Example:
      "adapter=modal,image=ghcr.io/x@sha256:abc...,gpu=none,memory_gb=4,timeout_s=120,snapshot=off,region=us-east-1,env=[OPENAI_API_KEY,LITELLM_API_BASE]"
    """
    mem = runtime.get("memory_gb", "")
    timeout = runtime.get("timeout_s", "")
    gpu = _norm_gpu(runtime.get("gpu"))
    keys = list(present_env_keys or [])
    parts: List[str] = [
        f"adapter={adapter}",
        f"image={image_digest}",
        f"gpu={gpu}",
        f"memory_gb={mem}",
        f"timeout_s={timeout}",
        f"snapshot={snapshot or 'off'}",
        f"region={region}" if region else "region=",
    ]
    if versions:
        # Include sorted tool versions if provided (optional)
        ver_str = ",".join([f"{k}={versions[k]}" for k in sorted(versions)])
        parts.append(f"versions=[{ver_str}]")
    if keys:
        parts.append(f"env=[{','.join(sorted(keys))}]")
    else:
        parts.append("env=[]")
    return ",".join(parts)
