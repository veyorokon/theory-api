"""Reusable test helpers for WebSocket integration tests."""

import asyncio
import json
from typing import Dict, Any, List, Tuple, Optional


async def collect_ws_messages(
    websocket, max_messages: int = 50, timeout: float = 30.0
) -> Tuple[List[Dict[str, Any]], Dict[str, Any] | None]:
    """
    Collect WebSocket messages until RunResult.

    Args:
        websocket: WebSocket connection
        max_messages: Maximum messages to collect
        timeout: Timeout per message receive

    Returns:
        Tuple of (all_messages, final_envelope)
        final_envelope is None if no RunResult received
    """
    messages = []

    for _ in range(max_messages):
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout=timeout)
            data = json.loads(message)
            messages.append(data)

            if data.get("kind") == "RunResult":
                return messages, data["content"]
        except TimeoutError:
            break

    return messages, None
