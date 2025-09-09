"""
RuntimeAdapter abstract base class for processor execution.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class RuntimeAdapter(ABC):
    """Abstract base class for runtime execution adapters."""
    
    @abstractmethod
    def invoke(
        self,
        processor_ref: str,
        image_digest: str,
        inputs_json: str,
        write_prefix: str,
        plan_id: str,
        timeout_s: Optional[int] = None,
        secrets: Optional[List[str]] = None,
        adapter_opts_json: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Invoke a processor with the given configuration.
        
        Args:
            processor_ref: Processor reference (e.g., 'llm/litellm@1')
            image_digest: Container image digest or identifier
            inputs_json: JSON string with processor inputs
            write_prefix: Prefix path for writing outputs (must end with /)
            plan_id: Plan identifier for tracking
            timeout_s: Optional timeout in seconds
            secrets: Optional list of secret names to resolve
            adapter_opts_json: Optional adapter-specific options as JSON string
            
        Returns:
            Execution result dictionary with:
                - status: 'success' or 'error'
                - outputs: Dict of output paths to content
                - seed: Execution seed
                - memo_key: Cache key for memoization
                - env_fingerprint: Environment specification
                - output_cids: List of content identifiers
                - estimate_micro: Estimated cost in micro-USD
                - actual_micro: Actual cost in micro-USD
        """
        pass
    
    def validate_write_prefix(self, write_prefix: str) -> bool:
        """
        Validate that write prefix follows requirements.
        
        Args:
            write_prefix: Prefix path to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not write_prefix:
            return False
        if not write_prefix.startswith('/'):
            return False
        if not write_prefix.endswith('/'):
            return False
        # Must be under /artifacts or /streams
        if not (write_prefix.startswith('/artifacts/') or write_prefix.startswith('/streams/')):
            return False
        return True
    
    def resolve_secrets(self, secret_names: Optional[List[str]]) -> Dict[str, str]:
        """
        Resolve secret names to values (default no-op).
        
        Args:
            secret_names: List of secret names
            
        Returns:
            Dictionary of secret name to value (empty by default)
        """
        return {}