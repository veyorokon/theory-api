"""
RuntimeAdapter abstract base class for processor execution.
"""

from __future__ import annotations
from typing import Any, Dict, List


class RuntimeAdapter:
    """
    All adapters should expose a keyword-only invoke() with the new signature.

    def invoke(
        self,
        *,
        processor_ref: str,
        inputs_json: Dict[str, Any],
        write_prefix: str,
        execution_id: str,
        registry_snapshot: Dict[str, Any],
        adapter_opts: Dict[str, Any],
        secrets_present: List[str],
    ) -> Dict[str, Any]:
        ...
    """

    def invoke(
        self,
        *,
        processor_ref: str,
        inputs_json: Dict[str, Any],
        write_prefix: str,
        execution_id: str,
        registry_snapshot: Dict[str, Any],
        adapter_opts: Dict[str, Any],
        secrets_present: List[str],
    ) -> Dict[str, Any]:
        """
        Invoke a processor with the given configuration.

        Args:
            processor_ref: Processor reference (e.g., 'llm/litellm@1')
            inputs_json: Dict with processor inputs (not JSON string)
            write_prefix: Prefix path for writing outputs (must end with /)
            execution_id: Unique execution identifier
            registry_snapshot: Registry snapshot containing processor specs
            adapter_opts: Adapter-specific options (not JSON string)
            secrets_present: List of secret names available in environment

        Returns:
            Execution result dictionary (canonical):
                - status: 'success'|'error'
                - execution_id: str
                - outputs: List[{path,cid,size_bytes,mime}]
                - index_path: str (path to outputs.json)
                - meta: {image_digest, env_fingerprint, duration_ms, ...}
        """
        raise NotImplementedError("Subclasses must implement invoke method")

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
        if not write_prefix.startswith("/"):
            return False
        if not write_prefix.endswith("/"):
            return False
        # Must be under /artifacts or /streams
        if not (write_prefix.startswith("/artifacts/") or write_prefix.startswith("/streams/")):
            return False
        return True

    def resolve_secrets(self, secret_names: List[str] | None) -> Dict[str, str]:
        """
        Resolve secret names to values (default no-op).

        Args:
            secret_names: List of secret names

        Returns:
            Dictionary of secret name to value (empty by default)
        """
        return {}


def guard_no_duplicates(canon_paths: List[str], execution_id: str) -> Dict[str, Any] | None:
    """
    Check for duplicates after canonicalization.

    Args:
        canon_paths: List of canonicalized paths
        execution_id: Execution ID for error envelope

    Returns:
        Error envelope dict if duplicates found, None otherwise
    """
    from .envelope import error_envelope
    from apps.core.errors import ERR_OUTPUT_DUPLICATE

    seen = set()
    for p in canon_paths:
        if p in seen:
            return error_envelope(
                execution_id, ERR_OUTPUT_DUPLICATE, f"Duplicate target after canonicalization: {p}", "adapter"
            )
        seen.add(p)
    return None


# write_outputs_index moved to envelope.py for single source of truth
