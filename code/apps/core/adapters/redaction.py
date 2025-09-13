import re

REDACT = re.compile(r"(%[0-9A-Fa-f]{2}){2,}|(sk-[A-Za-z0-9]{20,})")


def redact_msg(s: str) -> str:
    try:
        return REDACT.sub("[REDACTED]", s)
    except Exception:
        return "[REDACTED]"
