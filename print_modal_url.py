#!/usr/bin/env python3
"""Get Modal web URL for deployed processor."""

import os
import sys

sys.path.insert(0, "code")

import modal
from apps.core.management.commands._modal_common import modal_app_name


def main():
    APP_ENV = os.getenv("MODAL_ENV", "dev")
    REF = os.getenv("REF", "llm/litellm@1")
    BRANCH = os.getenv("BRANCH", "feat-three-lane-cicd")
    USER = os.getenv("USER", "veyorokon")

    if APP_ENV == "dev":
        app_name = modal_app_name(REF, env=APP_ENV, branch=BRANCH, user=USER)
    else:
        app_name = modal_app_name(REF, env=APP_ENV)

    try:
        fn = modal.Function.from_name(app_name, "fastapi_app")
        print(fn.web_url)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        print(f"App name: {app_name}", file=sys.stderr)
        print(f"Environment: {APP_ENV}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
