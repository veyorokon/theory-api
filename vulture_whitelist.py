"""Vulture whitelist of intentionally dynamic entrypoints.

Keep this list short and tie items back to docs/tests when possible.
"""

# Django signal receivers auto-discovered by dotted path
UNUSED = [
    "apps.core.signals.on_user_created",
]

# Console scripts exported via entry_points
CONSOLE_SCRIPTS = [
    "theory-modalctl",
]
