"""
Base adapter protocol for HTTP transport.
"""

from typing import Protocol, Dict, Any, Iterator


class Adapter(Protocol):
    """Transport-only adapter protocol."""

    def invoke(
        self, *, ref: str, payload: Dict[str, Any], timeout_s: int, oci: str | None = None, stream: bool = False
    ) -> Dict[str, Any] | Iterator[Dict[str, Any]]:
        """
        Invoke processor via HTTP.

        Args:
            ref: Processor reference (e.g., llm/litellm@1)
            payload: Request payload matching canonical contract
            timeout_s: Timeout in seconds
            oci: Expected OCI digest for validation (optional)
            stream: If True, return SSE iterator

        Returns:
            Envelope dict or SSE event iterator
        """
        ...
