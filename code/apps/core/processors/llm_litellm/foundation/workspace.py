"""Workspace management for processor execution."""
import os
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Workspace:
    """Standard workspace layout for processor execution."""
    work: Path = Path("/work")
    outputs: Path = Path("/work/out")
    source: Path = Path("/work/src")
    
    @classmethod
    def setup(cls) -> 'Workspace':
        """Create workspace directories and return workspace instance."""
        ws = cls()
        ws.outputs.mkdir(parents=True, exist_ok=True)
        ws.source.mkdir(parents=True, exist_ok=True)
        return ws