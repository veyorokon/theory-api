# ============================================================================
# Minimal, Adapter-Agnostic Makefile
# Truth lives in Django models + registry.yaml.
# This file only orchestrates per-adapter prep and test runs.
# ============================================================================

SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c
MAKEFLAGS += --no-builtin-rules --no-print-directory

# --- Core config (env overridable) ------------------------------------------
CODE_DIR            ?= code
PY                  ?= python
DJANGO_SETTINGS     ?= backend.settings.unittest   # set to dev/prod in CI/stacks
ADAPTER             ?= local                       # local | modal
ENV                 ?= dev                         # modal env: dev|staging|prod
PLATFORM            ?= $(shell uname -m | sed 's/x86_64/amd64/; s/aarch64/arm64/')

# Pytest markers (keep simple)
MARK_UNIT          := unit
MARK_CONTRACTS     := contracts
MARK_INTEGRATION   := integration
MARK_ACCEPTANCE    := acceptance

# Helpers
define run_manage
  (cd $(CODE_DIR) && DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) $(PY) manage.py $(1))
endef

define run_pytest
  @PYTHONPATH=$(CODE_DIR) \
   DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
   TEST_ADAPTER=$(ADAPTER) TEST_ENV=$(ENV) \
   LOG_STREAM=stderr JSON_LOGS=1 \
   $(PY) -m pytest -m '$(1)' $(if $(VERBOSE),-v,-q)
endef

require = @test -n "$($(1))" || { echo "Missing: $(1)"; exit 1; }

# ============================================================================
# Services (docker compose) – only used for local adapter + local MinIO/DB
# ============================================================================
.PHONY: services-up services-down services-ensure
services-up:
	@docker compose up -d
	# Wait for MinIO to get healthy (compose service name must be 'minio')
	@until docker compose ps minio --format json 2>/dev/null | grep -q '"Health":"healthy"'; do \
		echo "⏳ Waiting for MinIO..."; sleep 1; \
	done
	# Ensure dev bucket exists
	@docker run --rm --network theory_api_app_network \
	  --entrypoint sh quay.io/minio/mc:latest -c ' \
	    mc alias set local http://minio:9000 minioadmin minioadmin && \
	    mc mb --ignore-existing local/$$ARTIFACTS_BUCKET' || true
	@echo "✅ Services ready"

services-down:
	@docker compose down -v

services-ensure:
	@docker compose ps minio 2>/dev/null | grep -q "Up" || $(MAKE) services-up

# ============================================================================
# Tool prep – dynamic discovery via Django; parity for local/modal
# ============================================================================
.PHONY: tools-sync tools-prepare tools-cleanup
tools-sync:
	@$(call run_manage,toolctl sync --json >/dev/null)

tools-prepare:
	@echo "→ Preparing tools for adapter=$(ADAPTER) env=$(ENV)"
	@$(MAKE) tools-sync
ifneq ($(ADAPTER),modal)
	@$(MAKE) tools-prepare-local
else
	@$(MAKE) tools-prepare-modal ENV=$(ENV)
endif

tools-prepare-local: services-ensure
	@echo "→ Building images (if needed) and starting all enabled tools locally..."
	@refs="$$( $(call run_manage,toolctl list --enabled-only --format refs) )"; \
	for ref in $$refs; do \
		echo "  • $$ref: build"; \
		$(call run_manage,imagectl build --ref $$ref --platforms linux/$(PLATFORM) --json >/dev/null); \
		echo "  • $$ref: start"; \
		$(call run_manage,localctl start --ref $$ref >/dev/null); \
	done
	@echo "✓ Local tools ready (ports allocated dynamically by localctl)"

tools-prepare-modal:
	$(call require,ENV)
	@echo "→ Deploying all enabled tools to Modal ($(ENV)) with pinned digests..."
	@refs="$$( $(call run_manage,toolctl list --enabled-only --format refs) )"; \
	for ref in $$refs; do \
		oci="$$( $(call run_manage,toolctl get-oci --ref $$ref --platform $(PLATFORM)) )"; \
		test -n "$$oci" || { echo "No pinned OCI for $$ref ($(PLATFORM))"; exit 1; } ; \
		echo "  • $$ref: deploy $$oci"; \
		MODAL_ENVIRONMENT=$(ENV) $(call run_manage,modalctl deploy --ref $$ref --env $(ENV) --oci "$$oci"); \
		echo "  • $$ref: sync secrets"; \
		MODAL_ENVIRONMENT=$(ENV) $(call run_manage,modalctl sync-secrets --ref $$ref --env $(ENV)); \
	done
	@echo "✓ Modal tools ready"

tools-cleanup:
ifneq ($(ADAPTER),modal)
	@$(call run_manage,localctl stop --all || true)
else
	@echo "Modal cleanup is optional; deployments are long-lived. Use modalctl stop if desired."
endif

# ============================================================================
# Tests – adapter agnostic; pytest discovers enabled tools from DB
# ============================================================================
.PHONY: test-unit test-contracts test-integration test-acceptance test-all
test-unit:
	$(call run_pytest,$(MARK_UNIT))

test-contracts:
	$(call run_pytest,$(MARK_CONTRACTS))

test-integration: tools-prepare
	$(call run_pytest,$(MARK_INTEGRATION))

test-acceptance: tools-prepare
	$(call run_pytest,$(MARK_ACCEPTANCE))

test-all: test-unit test-contracts test-integration test-acceptance

# ============================================================================
# Low-level convenience (optional; single-tool ops when debugging)
# ============================================================================
.PHONY: local-start local-stop local-status modal-deploy modal-secrets modal-stop
local-start:
	$(call require,REF)
	@$(call run_manage,localctl start --ref $(REF) $(if $(PORT),--port $(PORT),))

local-stop:
	@$(call run_manage,localctl stop --all || true)

local-status:
	@$(call run_manage,localctl status)

modal-deploy:
	$(call require,REF)
	$(call require,ENV)
	$(call require,OCI)
	@MODAL_ENVIRONMENT=$(ENV) $(call run_manage,modalctl deploy --ref $(REF) --env $(ENV) --oci "$(OCI)")

modal-secrets:
	$(call require,REF)
	$(call require,ENV)
	@MODAL_ENVIRONMENT=$(ENV) $(call run_manage,modalctl sync-secrets --ref $(REF) --env $(ENV))

modal-stop:
	$(call require,REF)
	$(call require,ENV)
	@MODAL_ENVIRONMENT=$(ENV) $(call run_manage,modalctl stop --ref $(REF) --env $(ENV))

# ============================================================================
# CI lanes – keep simple; choose adapter via env
# ============================================================================
.PHONY: ci-pr ci-pr-modal ci-staging
ci-pr:
	@echo "→ PR lane (local adapter): unit + contracts + integration"
	@$(MAKE) test-unit
	@$(MAKE) test-contracts
	@$(MAKE) test-integration ADAPTER=local
	@$(MAKE) tools-cleanup ADAPTER=local

ci-pr-modal:
	@echo "→ PR lane (modal dev): integration + acceptance"
	@$(MAKE) test-integration ADAPTER=modal ENV=dev
	@$(MAKE) test-acceptance ADAPTER=modal ENV=dev

# Staging assumes digests already pinned in registry.yaml; no registry args required here.
ci-staging:
	@echo "→ Staging acceptance against modal-staging"
	@$(MAKE) test-acceptance ADAPTER=modal ENV=staging

# ============================================================================
# Help
# ============================================================================
.PHONY: help
help:
	@echo "Targets:"
	@echo "  make test-unit|test-contracts|test-integration|test-acceptance|test-all"
	@echo "     ADAPTER=local|modal (default local)  ENV=dev|staging|prod (for modal)"
	@echo "  make tools-prepare [ADAPTER=...]        - Build+start (local) OR deploy+sync (modal)"
	@echo "  make tools-cleanup                      - Stop local containers"
	@echo "  make services-up|services-down          - Local stack (MinIO, etc.)"
	@echo "  make local-start REF=ns/name@ver        - Start single tool locally"
	@echo "  make modal-deploy REF=... ENV=... OCI=... - Deploy single tool"
	@echo ""
	@echo "Env:"
	@echo "  DJANGO_SETTINGS=backend.settings.unittest|development|prod"
	@echo "  ADAPTER=local|modal  ENV=dev|staging|prod  PLATFORM=amd64|arm64"
