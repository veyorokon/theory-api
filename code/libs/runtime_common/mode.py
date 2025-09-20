from __future__ import annotations
from typing import Dict, Any

_ALLOWED = {"real", "mock", "smoke"}


class ModeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code  # e.g., "ERR_INPUT_UNSUPPORTED" or "ERR_POLICY_CI_NO_EGRESS"


def resolve_mode(inputs: Dict[str, Any], *, default: str = "mock") -> str:
    """
    Single source of truth for processor mode.
    - default = "mock" so tests & local dev are safe by default.
    - CI guardrail: blocks real mode in CI environment.
    """
    import os

    raw = inputs.get("mode", default)
    if not isinstance(raw, str):
        raise ModeError("ERR_INPUT_UNSUPPORTED", f"invalid mode type: {type(raw).__name__}")
    mode = raw.strip().lower()
    if mode not in _ALLOWED:
        raise ModeError("ERR_INPUT_UNSUPPORTED", f"invalid mode '{mode}' (allowed: {','.join(sorted(_ALLOWED))})")

    # CI guardrail: block real mode in CI environment
    if os.getenv("CI") == "true" and mode == "real":
        raise ModeError("ERR_CI_SAFETY", "Real mode is blocked in CI. Set inputs.mode to 'mock' or 'smoke'.")

    return mode


def is_mock(mode: str) -> bool:
    return mode == "mock"


def is_smoke(mode: str) -> bool:
    return mode == "smoke"
