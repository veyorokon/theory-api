from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Literal, Mapping, Any

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


def resolve_mode(inputs: Mapping[str, Any] | None) -> ResolvedMode:
    """
    Single source of truth for mode resolution and safety enforcement:
      - default to 'mock' if not provided
      - strictly validate allowed values
      - enforce CI safety: never allow real mode when CI=true
    """
    raw = None
    if isinstance(inputs, Mapping):
        raw = inputs.get("mode")
    v = str(raw).lower() if raw is not None else "mock"
    if v not in _VALID:
        raise ValueError(f"Invalid mode '{v}'. Allowed: {sorted(_VALID)}")

    # CI safety: never allow real mode when CI is set
    if v == "real" and os.getenv("CI", "").lower() == "true":
        raise ModeSafetyError("ERR_CI_SAFETY: Real mode is blocked in CI environments. Use mode=mock.")

    return ResolvedMode(value=v)  # type: ignore[arg-type]


def is_mock(resolved: ResolvedMode) -> bool:
    return resolved.value == "mock"


def is_real(resolved: ResolvedMode) -> bool:
    return resolved.value == "real"
