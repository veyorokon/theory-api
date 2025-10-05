SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c
MAKEFLAGS += --no-builtin-rules --no-print-directory

# ---- Paths / Python ---------------------------------------------------------
CODE_DIR := code
PY := python
PIP := $(PY) -m pip
DJANGO_SETTINGS ?= backend.settings.unittest

# ---- Test markers -----------------------------------------------------------
MARK_EXPR_UNIT          := (unit or contracts or property) and not requires_docker and not requires_postgres
MARK_EXPR_INTEGRATION   := (integration and requires_docker)
MARK_EXPR_CONTRACTS     := contracts
MARK_EXPR_SMOKE         := deploy_smoke
MARK_EXPR_ACCEPT_PR     := (acceptance and prlane)
MARK_EXPR_ACCEPT_SUPPLY := (acceptance and supplychain)

#NEED TO TEST AGAINST ALL ENABLED TOOLS
