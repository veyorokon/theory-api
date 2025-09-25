"""Universal processor interfaces - provider-agnostic."""

from __future__ import annotations
from typing import Protocol

# Import canonical types from runtime_common
from libs.runtime_common.envelope import OutputItem, ProcessorResult


class ProviderRunner(Protocol):
    """Universal provider interface - all providers must return callables matching this Protocol."""

    def __call__(self, inputs: dict) -> ProcessorResult:
        """Execute provider with inputs and return standardized result."""
        ...
