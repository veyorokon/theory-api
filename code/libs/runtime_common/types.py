from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Mapping
from libs.runtime_common.outputs import OutputItem


@dataclass
class ProcessorResult:
    """Standard result for all processors."""

    outputs: List[OutputItem] = field(default_factory=list)
    processor_info: str = ""
    usage: Mapping[str, Any] = field(default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict)
