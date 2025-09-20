from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Mapping, Any

Mode = Literal["mock", "real"]

_VALID: set[str] = {"mock", "real"}


@dataclass(frozen=True)
class ResolvedMode:
    value: Mode


def resolve_mode(inputs: Mapping[str, Any] | None) -> ResolvedMode:
    """
    Single source of truth:
      - default to 'mock' if not provided
      - strictly validate allowed values
    """
    raw = None
    if isinstance(inputs, Mapping):
        raw = inputs.get("mode")
    v = str(raw).lower() if raw is not None else "mock"
    if v not in _VALID:
        raise ValueError(f"Invalid mode '{v}'. Allowed: {sorted(_VALID)}")
    return ResolvedMode(value=v)  # type: ignore[arg-type]


def is_mock(resolved: ResolvedMode) -> bool:
    return resolved.value == "mock"


def is_real(resolved: ResolvedMode) -> bool:
    return resolved.value == "real"
