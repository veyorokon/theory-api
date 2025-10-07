"""
Management command utilities.

Helpers for writing testable Django management commands.
"""

import json
from functools import wraps


def capture_stdout(func):
    """
    Decorator for command functions to support stdout capture.

    Allows module-level command functions to work with Django's call_command stdout parameter.

    Usage:
        @capture_stdout
        def cmd_example(args):
            return {"status": "success", "data": 123}

        # In Command.handle():
        func = options.get("func")
        func(argparse.Namespace(**options), stdout=self.stdout)
    """

    @wraps(func)
    def wrapper(args, stdout=None):
        result = func(args)

        if result is None:
            return

        # Serialize result to JSON
        output = json.dumps(result) if isinstance(result, dict) else str(result)

        # Write to provided stdout or fall back to print
        if stdout:
            stdout.write(output)
        else:
            print(output)

    return wrapper
