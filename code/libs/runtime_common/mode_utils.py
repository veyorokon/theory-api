"""Mode resolution utilities with CI safety."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal, Mapping


class ModeSafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedMode:
    value: Literal["mock", "real"]


def resolve_mode(flag_value: str | Mapping[str, Any] | None) -> ResolvedMode:
    """
    Resolve "mock"|"real" with CI safety.

    Accepts a string or mapping containing a "mode" key; defaults to "mock".
    """
    raw = flag_value
    if isinstance(flag_value, Mapping):
        raw = flag_value.get("mode")

    v = (str(raw) if raw is not None else "mock").lower()
    if v not in ("mock", "real"):
        raise ValueError("Invalid mode '%s'. Allowed: ['mock', 'real']" % v)

    return ResolvedMode(value=v)  # type: ignore[arg-type]


def is_mock(resolved: ResolvedMode) -> bool:
    return resolved.value == "mock"


def is_real(resolved: ResolvedMode) -> bool:
    return resolved.value == "real"
