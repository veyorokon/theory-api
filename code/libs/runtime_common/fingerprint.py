import os
import platform
import sys
from typing import Dict, Iterable, List
from .hashing import blake3_hex


def env_fingerprint() -> str:
    frags = {
        "os": platform.system(),
        "arch": platform.machine(),
        "py": ".".join(map(str, sys.version_info[:3])),
        "cpu": platform.processor() or "unknown",
    }
    return "|".join(f"{k}:{frags[k]}" for k in sorted(frags))


def compose_env_fingerprint(**kv) -> str:
    """
    Compose environment fingerprint from key-value pairs.

    Args:
        **kv: Environment key-value pairs

    Returns:
        Semicolon-separated sorted key=value string (special-case image as image:value)
    """
    items = []
    for k, v in kv.items():
        if v not in (None, ""):
            # Use colon format for all components for consistency
            items.append(f"{k}:{v}")
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


SAFE_PASSTHROUGH = {
    "PYTHONPATH",
    "DJANGO_SETTINGS_MODULE",
    "LOG_STREAM",
    "TEST_LANE",
    "CI",
    "LANE",
    "MODAL_ENVIRONMENT",
    "APP_REV",
}

SECRET_PREFIXES = ("OPENAI_", "REPLICATE_", "ANTHROPIC_", "AZURE_OPENAI_", "GOOGLE_")


def build_clean_env(base: dict[str, str] | None = None, *, allow_secrets: bool = False) -> dict[str, str]:
    """
    Return a deterministic child env for subprocesses:
    - Always passes core plumbing vars.
    - Strips known secret prefixes unless allow_secrets=True.
    - Carries PATH so Python can spawn children.
    """
    src = dict(base or os.environ)
    out = {"PATH": src.get("PATH", ""), "PYTHONHASHSEED": src.get("PYTHONHASHSEED", "0")}

    # Always pass through safe vars
    for k in SAFE_PASSTHROUGH:
        if k in src:
            out[k] = src[k]

    if allow_secrets:
        # Include all secrets when explicitly allowed
        for k, v in src.items():
            if k.startswith(SECRET_PREFIXES):
                out[k] = v

    # Note: secrets are stripped by default (when allow_secrets=False)
    return out
