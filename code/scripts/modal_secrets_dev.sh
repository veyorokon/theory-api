#!/usr/bin/env bash
set -euo pipefail

# Modal env: dev
# This script scaffolds secret creation commands.
# Fill in the values or wire them from your CI secret store, then run.

# TODO: set value for LITELLM_API_BASE
# modal secret create LITELLM_API_BASE --from-literal LITELLM_API_BASE="$LITELLM_API_BASE"

# TODO: set value for OPENAI_API_KEY
# modal secret create OPENAI_API_KEY --from-literal OPENAI_API_KEY="$OPENAI_API_KEY"

