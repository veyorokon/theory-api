"""
Redaction utilities for sensitive information in logs and error messages.

Redacts API keys, tokens, URLs with credentials, and other sensitive patterns.
"""

import re

# Patterns for sensitive information
PATTERNS = [
    # API keys (various formats)
    r"sk-[A-Za-z0-9]{20,}",  # OpenAI style
    r"[A-Za-z0-9]{32,}:[A-Za-z0-9]{32,}",  # Replicate style
    r"Bearer\s+[A-Za-z0-9\-_=]+",  # Bearer tokens
    # URL credentials
    r"https?://[^@\s]+@[^\s]+",  # URLs with embedded credentials
    # Long hex strings (potential secrets)
    r"[a-fA-F0-9]{40,}",  # SHA1 and longer
    # Percent-encoded sequences
    r"(%[0-9A-Fa-f]{2}){2,}",
]

REDACT = re.compile("|".join(f"({p})" for p in PATTERNS))


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
