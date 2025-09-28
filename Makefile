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

# ---- Helpers ----------------------------------------------------------------
define guard_collect
@COUNT="$$(PYTHONPATH=$(CODE_DIR) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) TEST_LANE=pr $(PY) -m pytest --collect-only -q -m '$(1)' | grep -c ':')"; \
 if [ "$$COUNT" -eq 0 ]; then echo "✖ No tests collected for expression: $(1)" >&2; exit 1; else echo "✓ Collected $$COUNT tests for expression: $(1)"; fi
endef

require = @test -n "$($(1))" || { echo "Missing required var: $(1)"; exit 2; }

# ---- Help -------------------------------------------------------------------
.PHONY: help
help:
	@echo ""
	@echo "Targets:"
	@echo "  make tools-check                     - verify jq/yq present"
	@echo "  make test-unit                       - unit/contract/property (hermetic)"
	@echo "  make test-contracts                  - contracts only (hermetic)"
	@echo "  make integration-local               - integration via local adapter (pinned)"
	@echo "  make integration-local-build         - integration via local adapter (build fresh)"
	@echo "  make integration-modal ENV=dev       - integration via modal adapter"
	@echo "  make test-smoke                      - post-deploy smoke (modal-only)"
	@echo ""
	@echo "  make services-up                     - start test services (postgres, redis, minio)"
	@echo "  make services-down                   - stop test services"
	@echo "  make services-status                 - show test services status"
	@echo ""
	@echo "  make build-processor REF=ns/name@ver - build local image"
	@echo "  make push-processor REF=ns/name@ver TARGET=ghcr.io/you/repo:tag"
	@echo "  make pin-processor REF=ns/name@ver OCI=ghcr.io/...@sha256:..."
	@echo ""
	@echo "  make build-and-pin REGISTRY=ghcr.io/you/repo - build, push, pin all processors"
	@echo ""
	@echo "  make modal-deploy REF=ns/name@ver ENV=dev OCI=ghcr.io/...@sha256:..."
	@echo "  make modal-sync-secrets REF=ns/name@ver ENV=dev"
	@echo "  make modal-logs REF=ns/name@ver ENV=dev"
	@echo ""
	@echo "  make smoke-local-build               - local HTTP run (newest build)"
	@echo "  make smoke-local-pinned              - local HTTP run (pinned registry)"
	@echo "  make smoke-modal ENV=dev             - modal HTTP run"
	@echo ""

# ---- Tools preflight --------------------------------------------------------
.PHONY: tools-check
tools-check:
	@command -v jq >/dev/null || { echo "❌ jq missing"; exit 1; }
	@command -v yq >/dev/null || { echo "❌ yq missing"; exit 1; }
	@echo "✅ Required tools available (jq, yq)"

# ---- Dev setup --------------------------------------------------------------
.PHONY: setup-dev
setup-dev:
	@$(PY) --version
	@$(PIP) install -U pip
	@$(PIP) install -r requirements-dev.txt

# ---- Tests ------------------------------------------------------------------
.PHONY: test-unit
test-unit:
	$(call guard_collect,$(MARK_EXPR_UNIT))
	@PYTHONPATH=$(CODE_DIR) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) TEST_LANE=pr LOG_STREAM=stderr JSON_LOGS=1 \
	$(PY) -m pytest -m '$(MARK_EXPR_UNIT)'

.PHONY: test-contracts
test-contracts:
	$(call guard_collect,$(MARK_EXPR_CONTRACTS))
	@PYTHONPATH=$(CODE_DIR) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) TEST_LANE=pr LOG_STREAM=stderr JSON_LOGS=1 \
	$(PY) -m pytest -m '$(MARK_EXPR_CONTRACTS)'

# Core parametric integration: TARGET=local (default) or modal; BUILD=1 for local builds
.PHONY: test-integration
test-integration:
	$(call guard_collect,$(MARK_EXPR_INTEGRATION))
	@PYTHONPATH=$(CODE_DIR) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) TEST_LANE=pr \
	RUN_TARGET=$(if $(TARGET),$(TARGET),local) \
	$(if $(filter modal,$(TARGET)),MODAL_ENVIRONMENT=$(ENV),) \
	$(if $(filter 1,$(BUILD)),BUILD=1,BUILD=0) \
	LOG_STREAM=stderr JSON_LOGS=1 \
	$(PY) -m pytest -m '$(MARK_EXPR_INTEGRATION)'

# Explicit aliases following smoke pattern
.PHONY: integration-local
integration-local-pinned:
	@$(MAKE) test-integration TARGET=local BUILD=0

.PHONY: integration-local-build
integration-local-build:
	@$(MAKE) test-integration TARGET=local BUILD=1

.PHONY: integration-modal
integration-modal:
	$(call require,ENV)
	@$(MAKE) test-integration TARGET=modal ENV=$(ENV)

.PHONY: test-smoke
test-smoke:
	$(call guard_collect,$(MARK_EXPR_SMOKE))
	@PYTHONPATH=$(CODE_DIR) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) TEST_LANE=staging LOG_STREAM=stderr JSON_LOGS=1 \
	RUN_TARGET=modal MODAL_ENVIRONMENT=$(ENV) \
	$(PY) -m pytest -m '$(MARK_EXPR_SMOKE)'

# ---- Build / Push / Pin -----------------------------------------------------
.PHONY: build-processor
build-processor:
	$(call require,REF)
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	$(PY) manage.py build_processor --ref $(REF) $(if $(PLATFORMS),--platforms $(PLATFORMS),) --json | jq .

.PHONY: push-processor
push-processor:
	$(call require,IMAGE)
	$(call require,TARGET)
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	$(PY) manage.py push_processor --image "$(IMAGE)" --target "$(TARGET)" --json | jq .

.PHONY: pin-processor
pin-processor:
	$(call require,REF)
	$(call require,OCI)
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	$(PY) manage.py pin_processor --ref $(REF) --oci "$(OCI)" $(if $(PLATFORM),--platform $(PLATFORM),) --json | jq .

# ---- Modal control ----------------------------------------------------------
.PHONY: modal-deploy
modal-deploy:
	$(call require,REF)
	$(call require,ENV)
	$(call require,OCI)
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) MODAL_ENVIRONMENT=$(ENV) \
	$(PY) manage.py modalctl deploy --ref $(REF) --env $(ENV) --oci "$(OCI)"

.PHONY: modal-sync-secrets
modal-sync-secrets:
	$(call require,REF)
	$(call require,ENV)
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) MODAL_ENVIRONMENT=$(ENV) \
	$(PY) manage.py modalctl sync-secrets --ref $(REF) --env $(ENV) --json

.PHONY: modal-logs
modal-logs:
	$(call require,REF)
	$(call require,ENV)
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) MODAL_ENVIRONMENT=$(ENV) \
	$(PY) manage.py modalctl logs --ref $(REF) --env $(ENV)

# ---- Smoke (HTTP-first via orchestrator; transport set by RUN_TARGET) ----
JSON_INPUT    ?= {"schema":"v1","params":{"model":"gpt-4o-mini","messages":[{"role":"user","content":"smoke"}]}}
WRITE_PREFIX  ?= /tmp/outputs/{execution_id}/
REF           ?= llm/litellm@1
ENV           ?= dev     # used by modal smoke

# Core, parametric local smoke: BUILD=1 uses newest local build; BUILD=0 uses pinned
.PHONY: smoke-local
smoke-local:
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	RUN_TARGET=local \
	$(PY) manage.py run_processor \
	  --ref "$(REF)" \
	  --adapter local \
	  $(if $(filter 1,$(BUILD)),--build,) \
	  --mode mock \
	  --write-prefix "$(WRITE_PREFIX)" \
	  --inputs-json '$(JSON_INPUT)' \
	  --json | jq .

# Friendly aliases
.PHONY: smoke-local-build
smoke-local-build:
	@$(MAKE) smoke-local BUILD=1 REF="$(REF)"

.PHONY: smoke-local-pinned
smoke-local-pinned:
	@$(MAKE) smoke-local BUILD=0 REF="$(REF)"

# Modal smoke (unchanged; build flag ignored by adapter)
.PHONY: smoke-modal
smoke-modal:
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	RUN_TARGET=modal MODAL_ENVIRONMENT=$(ENV) \
	$(PY) manage.py run_processor \
	  --ref "$(REF)" \
	  --adapter modal \
	  --mode mock \
	  --write-prefix "$(WRITE_PREFIX)" \
	  --inputs-json '$(JSON_INPUT)' \
	  --json | jq .

# ---- Service lifecycle -----------------------------------------------------
.PHONY: services-up
services-up:
	@docker compose --profile full up -d
	@echo "✅ Test services started (postgres, redis, minio)"

.PHONY: services-down
services-down:
	@docker compose down
	@echo "✅ Test services stopped"

.PHONY: services-status
services-status:
	@docker compose ps

# ---- Build and Pin Pipeline (Staging) -------------------------------------

# Auto-discover all processors and convert to REF format
PROCESSOR_REFS := $(patsubst %,%@1, $(subst _,/, $(shell find code/apps/core/processors -name "registry.yaml" -exec dirname {} \; | xargs -I {} basename {})))

# Detect platform for pinning (can be overridden)
PLATFORM ?= $(shell uname -m | sed 's/x86_64/amd64/' | sed 's/aarch64/arm64/')

.PHONY: build-and-pin
build-and-pin:
	$(call require,REGISTRY)
	@for ref in $(PROCESSOR_REFS); do \
		build_result=$$($(MAKE) build-processor REF=$$ref PLATFORMS=linux/$(PLATFORM) 2>/dev/null); \
		image_tag=$$(echo "$$build_result" | jq -r '.image_tag'); \
		target="$(REGISTRY)/$$(echo $$ref | sed 's/@.*//' | sed 's/\//-/g'):staging-$$(date +%Y%m%d%H%M%S)"; \
		push_result=$$($(MAKE) push-processor IMAGE=$$image_tag TARGET=$$target 2>/dev/null); \
		oci=$$(echo "$$push_result" | jq -r '.digest_ref'); \
		$(MAKE) pin-processor REF=$$ref OCI=$$oci PLATFORM=$(PLATFORM); \
	done
