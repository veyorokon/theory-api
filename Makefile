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
CODE_DIR               ?= code
PY                     ?= python
DJANGO_SETTINGS_MODULE ?= backend.settings.unittest   # set to dev/prod in CI/stacks
ADAPTER                ?= local                       # local | modal
ENV                    ?= dev                         # modal env: dev|staging|prod
PLATFORM               ?= $(shell uname -m | sed 's/x86_64/amd64/; s/aarch64/arm64/')
MOCK_MISSING_SECRETS   ?= false                       # true to generate mock values for missing secrets

# Pytest markers (keep simple)
MARK_UNIT          := unit
MARK_CONTRACTS     := contracts
MARK_INTEGRATION   := integration
MARK_ACCEPTANCE    := acceptance

# Helpers
define run_manage
  (cd $(CODE_DIR) && DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(PY) manage.py $(1))
endef

define run_pytest
  @PYTHONPATH=$(CODE_DIR) \
   DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) \
   TEST_ADAPTER=$(ADAPTER) TEST_ENV=$(ENV) \
   LOG_STREAM=stderr JSON_LOGS=1 \
   $(PY) -m pytest -m '$(1)' $(if $(VERBOSE),-v,-q) $(2)
endef

require = @test -n "$($(1))" || { echo "Missing: $(1)"; exit 1; }

# ============================================================================
# Services (docker compose) – only used for local adapter + local MinIO/DB
# ============================================================================
.PHONY: services-up services-down services-ensure
services-up:
	@docker network inspect theory_api_app_network >/dev/null 2>&1 || \
		docker network create theory_api_app_network
	@docker compose --profile full up -d
	# Wait for MinIO to get healthy (compose service name must be 'minio')
	@until docker compose ps minio --format json 2>/dev/null | grep -q '"Health":"healthy"'; do \
		echo "⏳ Waiting for MinIO..."; sleep 1; \
	done
	# Ensure dev bucket exists
	@docker run --rm --network theory_api_app_network \
	  --entrypoint sh quay.io/minio/mc:RELEASE.2025-01-17T23-25-50Z -c ' \
	    mc alias set local http://minio:9000 minioadmin minioadmin && \
	    mc mb --ignore-existing local/$$ARTIFACTS_BUCKET' || true
	@echo "✅ Services ready"

services-down:
	@docker compose down -v

services-ensure:
	@docker compose ps minio 2>/dev/null | grep -q "Up" || $(MAKE) services-up

# ============================================================================
# Image Build/Publish (build once, use everywhere)
# ============================================================================
.PHONY: tools-sync build-images publish-images
tools-sync:
	@$(call run_manage,toolctl sync --json >/dev/null)

build-images:
	@echo "→ Building images for platform=$(PLATFORM)"
	@$(MAKE) tools-sync
	@refs="$$( $(call run_manage,toolctl list --enabled-only --format refs) )"; \
	for ref in $$refs; do \
		echo "  • $$ref: build"; \
		$(call run_manage,imagectl build --ref $$ref --platform $(PLATFORM) --json >/dev/null); \
	done
	@echo "✓ Images built"

publish-images:
	@echo "→ Publishing images to registry for platform=$(PLATFORM)"
	@refs="$$( $(call run_manage,toolctl list --enabled-only --format refs) )"; \
	for ref in $$refs; do \
		echo "  • $$ref: publish"; \
		$(call run_manage,imagectl publish --ref $$ref --platform $(PLATFORM) --json); \
	done
	@echo "✓ Images published and pinned"

# ============================================================================
# Tool Start (from pinned images)
# ============================================================================
.PHONY: start-tools start-tools-local start-tools-modal stop-tools
start-tools:
	@echo "→ Starting tools for adapter=$(ADAPTER) env=$(ENV)"
ifneq ($(ADAPTER),modal)
	@$(MAKE) start-tools-local
else
	@$(MAKE) start-tools-modal ENV=$(ENV)
endif

start-tools-local: services-ensure
	@echo "→ Pulling published images and starting local containers..."
	@refs="$$( $(call run_manage,toolctl list --enabled-only --format refs) )"; \
	for ref in $$refs; do \
		oci="$$( $(call run_manage,toolctl get-oci --ref $$ref --platform $(PLATFORM)) )"; \
		test -n "$$oci" || { echo "No pinned OCI for $$ref ($(PLATFORM))"; exit 1; }; \
		echo "  • $$ref: pull $$oci"; \
		docker pull "$$oci" >/dev/null 2>&1; \
		echo "  • $$ref: start"; \
		$(call run_manage,localctl start --ref $$ref --platform $(PLATFORM) \
			$(if $(filter true,$(MOCK_MISSING_SECRETS)),--mock-missing-secrets,) >/dev/null); \
	done
	@echo "✓ Local tools ready (from registry)"

start-tools-modal:
	$(call require,ENV)
	@echo "→ Deploying tools to Modal ($(ENV)) with pinned digests..."
	@refs="$$( $(call run_manage,toolctl list --enabled-only --format refs) )"; \
	for ref in $$refs; do \
		oci="$$( $(call run_manage,toolctl get-oci --ref $$ref --platform $(PLATFORM)) )"; \
		test -n "$$oci" || { echo "No pinned OCI for $$ref ($(PLATFORM))"; exit 1; }; \
		echo "  • $$ref: deploy $$oci"; \
		MODAL_ENVIRONMENT=$(ENV) $(call run_manage,modalctl start --ref $$ref --oci "$$oci" \
			$(if $(filter true,$(MOCK_MISSING_SECRETS)),--mock-missing-secrets,)); \
		echo "  • $$ref: sync secrets"; \
		MODAL_ENVIRONMENT=$(ENV) $(call run_manage,modalctl sync-secrets --ref $$ref \
			$(if $(filter true,$(MOCK_MISSING_SECRETS)),--mock-missing-secrets,)); \
	done
	@echo "✓ Modal tools ready"

stop-tools:
ifneq ($(ADAPTER),modal)
	@$(call run_manage,localctl stop --all || true)
else
	@echo "Modal cleanup is optional; deployments are long-lived. Use modalctl stop if desired."
endif

# ============================================================================
# Tests (assumes tools already started)
# ============================================================================
.PHONY: test-unit test-contracts test-integration test-acceptance test-all
test-unit:
	$(call run_pytest,$(MARK_UNIT),--ignore=tests/integration)

test-contracts:
	$(call run_pytest,$(MARK_CONTRACTS),--ignore=tests/integration)

test-integration:
	$(call run_pytest,$(MARK_INTEGRATION))

test-acceptance:
	$(call run_pytest,$(MARK_ACCEPTANCE))

# ============================================================================
# Combined build+publish (for CI convenience)
# ============================================================================
.PHONY: build-and-publish-all
build-and-publish-all:
	@$(MAKE) build-images PLATFORM=$(PLATFORM)
	@$(MAKE) publish-images PLATFORM=$(PLATFORM)

# ============================================================================
# Help
# ============================================================================
.PHONY: help
help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Image Build/Publish:"
	@echo "  build-images           Build images for PLATFORM (no push)"
	@echo "  publish-images         Push + pin digests to registry"
	@echo "  build-and-publish-all  Build + publish (combined)"
	@echo ""
	@echo "Tool Start/Stop:"
	@echo "  start-tools            Pull pinned images + start (ADAPTER=local|modal)"
	@echo "  stop-tools             Stop tools"
	@echo ""
	@echo "Tests (assumes tools started):"
	@echo "  test-unit              Run unit tests"
	@echo "  test-contracts         Run contract tests"
	@echo "  test-integration       Run integration tests"
	@echo "  test-acceptance        Run acceptance tests"
	@echo ""
	@echo "Services:"
	@echo "  services-up            Start MinIO + Postgres"
	@echo "  services-down          Stop services"
	@echo ""
	@echo "Environment Variables:"
	@echo "  DJANGO_SETTINGS_MODULE Backend settings module (unittest|dev_local|dev_remote)"
	@echo "  ADAPTER                Tool adapter (local|modal)"
	@echo "  ENV                    Modal environment (dev|staging|prod)"
	@echo "  PLATFORM               Build platform (amd64|arm64)"
	@echo "  MOCK_MISSING_SECRETS   Generate mock secrets (true|false)"
