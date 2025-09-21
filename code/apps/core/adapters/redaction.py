"""
Redaction utilities for sensitive information in logs and error messages.

Redacts API keys, tokens, URLs with credentials, and other sensitive patterns.
"""

import re

# Enhanced patterns for sensitive information (consolidated from logging.py)
PATTERNS = [
    # Authorization headers (full header pattern)
    r"\bAuthorization:\s+Bearer\s+[A-Za-z0-9._-]+",
    # Bearer tokens (standalone)
    r"\bBearer\s+[A-Za-z0-9._-]+",
    # API keys and tokens (key=value pattern)
    r"\b(api[_-]?key|token)\b[:=]\s*[^,\s]+",
    # URL credentials (user:pass@host)
    r"(https?://)[^/\s]+:[^/@\s]+@",
    # OpenAI style keys
    r"sk-[A-Za-z0-9]{20,}",
    # Replicate style keys
    r"[A-Za-z0-9]{32,}:[A-Za-z0-9]{32,}",
    # Long hex strings (potential secrets)
    r"\b[0-9a-fA-F]{32,}\b",
    # Percent-encoded sequences
    r"(%[0-9A-Fa-f]{2}){2,}",
]

# Use case-insensitive flag at the regex level instead of inline
REDACT = re.compile("|".join(f"({p})" for p in PATTERNS), re.IGNORECASE)


def redact_msg(s: str) -> str:
    """
    Redact sensitive information from a message.

    Args:
        s: Message to redact

    Returns:
        Message with sensitive parts replaced by [REDACTED]
    """
    if not s:
        return s
    try:
        return REDACT.sub("[REDACTED]", s)
    except Exception:
        # If any error, better to redact everything than leak
        return "[REDACTED]"
