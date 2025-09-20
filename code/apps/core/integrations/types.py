"""Universal processor interfaces - provider-agnostic."""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Mapping, Protocol


@dataclass
class OutputItem:
    """Single output artifact from processor execution."""

    relpath: str  # posix relative path under write_prefix (must start with outputs/)
    bytes_: bytes  # raw bytes content
    meta: Mapping[str, str] | None = None  # optional metadata


@dataclass
class ProcessorResult:
    """Standard result from any processor execution."""

    outputs: List[OutputItem]  # zero or more output artifacts
    processor_info: str  # processor identification (name, version, etc.)
    usage: Mapping[str, float]  # resource usage metrics (processor-specific)
    extra: Mapping[str, str]  # additional metadata (optional)


class ProviderRunner(Protocol):
    """Universal provider interface - all providers must return callables matching this Protocol."""

    def __call__(self, inputs: dict) -> ProcessorResult:
        """Execute provider with inputs and return standardized result."""
        ...
