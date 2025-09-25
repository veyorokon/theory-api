# Makefile — HTTP-first, container-only, Modal via modalctl

SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c
MAKEFLAGS += --no-builtin-rules

# ---- Paths / Python ---------------------------------------------------------
CODE_DIR := code
PY := python
PIP := $(PY) -m pip
DJANGO_SETTINGS ?= backend.settings.unittest

# ---- Compose (only if your tests still need it) -----------------------------
COMPOSE ?= docker compose
COMPOSE_PROJECT_NAME ?= theory
COMPOSE_FILES := -f docker-compose.yml

# ---- Test markers -----------------------------------------------------------
MARK_EXPR_UNIT          := (unit or contracts or property) and not requires_docker
MARK_EXPR_INTEGRATION   := (integration and requires_docker)
MARK_EXPR_CONTRACTS     := contracts
MARK_EXPR_SMOKE         := deploy_smoke
MARK_EXPR_ACCEPT_PR     := (acceptance and prlane)
MARK_EXPR_ACCEPT_SUPPLY := (acceptance and supplychain)

# ---- Helpers ----------------------------------------------------------------
define guard_collect
@COUNT="$$(PYTHONPATH=$(CODE_DIR) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) TEST_LANE=pr $(PY) -m pytest --collect-only -q -m '$(1)' | grep -c ':')"; \
 if [ "$$COUNT" -eq 0 ]; then \
   echo "✖ No tests collected for expression: $(1)" >&2; \
   exit 1; \
 else \
   echo "✓ Collected $$COUNT tests for expression: $(1)"; \
 fi
endef

require = @test -n "$($(1))" || { echo "Missing required var: $(1)"; exit 2; }

# ---- Help -------------------------------------------------------------------
.PHONY: help
help:
	@echo ""
	@echo "Targets:"
	@echo "  make tools-check                     - verify jq/yq present"
	@echo "  make test-unit                       - unit/contract/property (no docker)"
	@echo "  make test-contracts                  - contracts only"
	@echo "  make test-integration                - integration (docker) "
	@echo "  make test-smoke                      - post-deploy smoke (CI)"
	@echo ""
	@echo "  make build-processor REF=ns/name@ver - build local image from embedded registry.yaml"
	@echo "  make push-processor REF=ns/name@ver TARGET=ghcr.io/you/repo:tag"
	@echo "  make pin-processor REF=ns/name@ver OCI=ghcr.io/...@sha256:..."
	@echo ""
	@echo "  make modal-deploy REF=ns/name@ver ENV=dev OCI=ghcr.io/...@sha256:..."
	@echo "  make modal-sync-secrets REF=ns/name@ver ENV=dev"
	@echo "  make modal-logs REF=ns/name@ver ENV=dev"
	@echo ""
	@echo "  make smoke-local REF=ns/name@ver     - run via Local adapter (HTTP)"
	@echo "  make smoke-modal REF=ns/name@ver ENV=dev - run via Modal adapter (HTTP)"
	@echo ""

# ---- Tools preflight --------------------------------------------------------
.PHONY: tools-check
tools-check:
	@command -v jq >/dev/null || { echo "❌ jq missing"; exit 1; }
	@command -v yq >/dev/null || { echo "❌ yq missing"; exit 1; }
	@echo "✅ Required tools available (jq, yq)"

# ---- Tests ------------------------------------------------------------------
.PHONY: setup-dev
setup-dev:
	@$(PY) --version
	@$(PIP) install -U pip
	@$(PIP) install -r requirements-dev.txt

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

.PHONY: test-integration
test-integration:
	$(call guard_collect,$(MARK_EXPR_INTEGRATION))
	@PYTHONPATH=$(CODE_DIR) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) TEST_LANE=pr LOG_STREAM=stderr JSON_LOGS=1 \
	$(PY) -m pytest -m '$(MARK_EXPR_INTEGRATION)'

.PHONY: test-smoke
test-smoke:
	$(call guard_collect,$(MARK_EXPR_SMOKE))
	@PYTHONPATH=$(CODE_DIR) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) TEST_LANE=staging LOG_STREAM=stderr JSON_LOGS=1 \
	$(PY) -m pytest -m '$(MARK_EXPR_SMOKE)'

# ---- Build / Push / Pin (embedded registry) --------------------------------
.PHONY: build-processor
build-processor:
	$(call require,REF)
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	$(PY) manage.py build_processor --ref $(REF) --json | jq .

.PHONY: push-processor
push-processor:
	$(call require,REF)
	$(call require,TARGET)
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	$(PY) manage.py push_processor --ref $(REF) --target "$(TARGET)" --json | jq .

.PHONY: pin-processor
pin-processor:
	$(call require,REF)
	$(call require,OCI)
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	$(PY) manage.py pin_processor --ref $(REF) --oci "$(OCI)" --json | jq .

# ---- Modal control via modalctl (no legacy commands) -----------------------
.PHONY: modal-deploy
modal-deploy:
	$(call require,REF)
	$(call require,ENV)
	$(call require,OCI)
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) MODAL_ENVIRONMENT=$(ENV) \
	$(PY) manage.py modalctl deploy --ref $(REF) --env $(ENV) --oci "$(OCI)" --json | jq .

.PHONY: modal-sync-secrets
modal-sync-secrets:
	$(call require,REF)
	$(call require,ENV)
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) MODAL_ENVIRONMENT=$(ENV) \
	$(PY) manage.py modalctl sync-secrets --ref $(REF) --env $(ENV) --json | jq .

.PHONY: modal-logs
modal-logs:
	$(call require,REF)
	$(call require,ENV)
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) MODAL_ENVIRONMENT=$(ENV) \
	$(PY) manage.py modalctl logs --ref $(REF) --env $(ENV)

# ---- Smokes (HTTP-first via adapters) --------------------------------------
JSON_INPUT ?= {"schema":"v1","params":{"model":"gpt-4o-mini","messages":[{"role":"user","content":"smoke"}]}}
WRITE_PREFIX ?= /artifacts/outputs/{execution_id}/

.PHONY: smoke-local
smoke-local:
	$(call require,REF)
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	$(PY) manage.py run_processor \
	  --ref $(REF) --adapter local --mode mock \
	  --write-prefix "$(WRITE_PREFIX)" \
	  --inputs-json '$(JSON_INPUT)' --json | jq .

.PHONY: smoke-modal
smoke-modal:
	$(call require,REF)
	$(call require,ENV)
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) MODAL_ENVIRONMENT=$(ENV) \
	$(PY) manage.py run_processor \
	  --ref $(REF) --adapter modal --mode mock \
	  --write-prefix "$(WRITE_PREFIX)" \
	  --inputs-json '$(JSON_INPUT)' --json | jq .
