from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Literal, Mapping, Any, Union

Mode = Literal["mock", "real"]

_VALID: set[str] = {"mock", "real"}


class ModeSafetyError(Exception):
    """Raised when the selected mode violates environment safety rules."""

    code = "ERR_CI_SAFETY"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class ResolvedMode:
    value: Mode


def resolve_mode(flag_value: str | Mapping[str, Any] | None) -> ResolvedMode:
    """
    Single source of truth for mode resolution and safety enforcement.
    Accepts:
    - String flag: "mock" | "real" | None
    - Dict with mode key: {"mode": "mock"} (for backward compatibility)
    - None (defaults to "mock")

    Enforcement:
    - default to 'mock' if not provided
    - strictly validate allowed values
    - enforce CI safety: never allow real mode when CI=true
    """
    # Extract mode value from various input types
    raw = flag_value
    if isinstance(flag_value, Mapping):
        raw = flag_value.get("mode")

    v = (str(raw) if raw is not None else "mock").lower()
    if v not in _VALID:
        raise ValueError(f"Invalid mode '{v}'. Allowed: {sorted(_VALID)}")

    # CI safety: never allow real mode when CI is set OR when explicitly in PR lane
    ci = os.getenv("CI", "")
    lane_env = os.getenv("LANE") or os.getenv("TEST_LANE")
    lane = lane_env.lower() if lane_env else None

    # Block real mode if CI is set OR if explicitly in PR lane
    if v == "real" and (ci or lane == "pr"):
        raise ModeSafetyError("ERR_CI_SAFETY: Real mode is blocked in CI environments. Use mode=mock.")

    return ResolvedMode(value=v)  # type: ignore[arg-type]


def is_mock(resolved: ResolvedMode) -> bool:
    return resolved.value == "mock"


def is_real(resolved: ResolvedMode) -> bool:
    return resolved.value == "real"
