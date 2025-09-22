# Makefile (repo root)
# ------------------------------------------------------------
# Boring, lane-aware test runner with compose orchestration.
# ------------------------------------------------------------

SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c
MAKEFLAGS += --no-builtin-rules

# ---- Directories ------------------------------------------------------------
CODE_DIR := code
TEST_DIR := tests

# ---- Docker Compose ---------------------------------------------------------
COMPOSE ?= docker compose
COMPOSE_PROJECT_NAME ?= theory
COMPOSE_FILES := -f docker-compose.yml

# ---- Django / Python --------------------------------------------------------
DJANGO_SETTINGS ?= backend.settings.unittest
PY := python

# ---- Marker expressions (match how your tests are actually marked) ----------
MARK_EXPR_UNIT := (unit or contracts or property) and not requires_postgres and not requires_docker and not requires_minio
MARK_EXPR_INTEGRATION := (integration and not requires_docker and not requires_postgres and not requires_minio)
MARK_EXPR_ACCEPT_PR := (acceptance and prlane)
MARK_EXPR_ACCEPT_SUPPLY := (acceptance and supplychain)
MARK_EXPR_CONTRACTS := contracts
MARK_EXPR_PROPERTY := property
MARK_EXPR_SMOKE := deploy_smoke

# ---- Utility: guard that at least one test is collected for an expression ---
define guard_collect
@COUNT="$$(PYTHONPATH=$(CODE_DIR) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) TEST_LANE=pr python -m pytest --collect-only -q -m '$(1)' | grep -c ':')"; \
 if [ "$$COUNT" -eq 0 ]; then \
   echo "✖ No tests collected for expression: $(1)" >&2; \
   exit 1; \
 else \
   echo "✓ Collected $$COUNT tests for expression: $(1)"; \
 fi
endef

# ---- Help -------------------------------------------------------------------
.PHONY: help
help:
	@echo ""
	@echo "Targets:"
	@echo "  make lint                - run linters/formatters (placeholder)"
	@echo "  make test-unit           - unit+contracts+property (hermetic)"
	@echo "  make test-integration    - integration (no external services)"
	@echo "  make test-contracts      - contracts only (hermetic)"
	@echo "  make test-property       - property tests only"
	@echo "  make test-acceptance-pr  - PR lane (build-from-source, mock, no secrets)"
	@echo "  make test-acceptance-dev - supply-chain lane (pinned-only, mock)"
	@echo "  make test-smoke          - post-deploy smoke (CI staging/main)"
	@echo "  make compose-up          - start docker stack for acceptance"
	@echo "  make compose-down        - stop docker stack"
	@echo ""
	@echo "Modal dev workflow:"
	@echo "  make build-processor REF=llm/litellm@1     - build processor locally"
	@echo "  make deploy-modal-dev REF=llm/litellm@1    - deploy to Modal dev"
	@echo "  make smoke-modal-dev REF=llm/litellm@1     - smoke test Modal dev (mock)"
	@echo "  make real-modal-dev REF=llm/litellm@1      - real test Modal dev (needs secrets)"
	@echo "  make modal-dev-workflow REF=llm/litellm@1  - full workflow (build→deploy→smoke)"
	@echo ""

# ---- Linters (optional wire-up) ---------------------------------------------
.PHONY: lint
lint:
	@echo "→ lint not configured; add ruff/black/mypy if desired"

# ---- Core hermetic lanes ----------------------------------------------------
.PHONY: test-unit
test-unit:
	$(call guard_collect,$(MARK_EXPR_UNIT))
	@PYTHONPATH=$(CODE_DIR) \
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	TEST_LANE=pr \
	LOG_STREAM=stderr \
	python -m pytest -m '$(MARK_EXPR_UNIT)'

.PHONY: test-integration
test-integration:
	$(call guard_collect,$(MARK_EXPR_INTEGRATION))
	@PYTHONPATH=$(CODE_DIR) \
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	TEST_LANE=pr \
	LOG_STREAM=stderr \
	python -m pytest -m '$(MARK_EXPR_INTEGRATION)'

.PHONY: test-contracts
test-contracts:
	$(call guard_collect,$(MARK_EXPR_CONTRACTS))
	@PYTHONPATH=$(CODE_DIR) \
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	TEST_LANE=pr \
	LOG_STREAM=stderr \
	python -m pytest -m '$(MARK_EXPR_CONTRACTS)'

.PHONY: test-property
test-property:
	$(call guard_collect,$(MARK_EXPR_PROPERTY))
	@PYTHONPATH=$(CODE_DIR) \
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	TEST_LANE=pr \
	LOG_STREAM=stderr \
	python -m pytest -m '$(MARK_EXPR_PROPERTY)'

# ---- Acceptance (compose-backed) --------------------------------------------
.PHONY: compose-up
compose-up:
	@$(COMPOSE) $(COMPOSE_FILES) -p $(COMPOSE_PROJECT_NAME) up -d --wait

.PHONY: compose-down
compose-down:
	@$(COMPOSE) $(COMPOSE_FILES) -p $(COMPOSE_PROJECT_NAME) down -v || true

.PHONY: _wait-db
_wait-db:
	@echo "Waiting for Postgres..."
	@for i in $$(seq 1 60); do \
	  if $(COMPOSE) $(COMPOSE_FILES) -p $(COMPOSE_PROJECT_NAME) logs postgres | grep -qi "database system is ready"; then \
	    echo "Postgres ready"; exit 0; fi; \
	  sleep 1; \
	done; \
	echo "Postgres not ready in time" >&2; exit 1

# PR lane acceptance: build-from-source, mock mode, no secrets, filesystem storage.
.PHONY: test-acceptance-pr
test-acceptance-pr: compose-up _wait-db
	$(call guard_collect,$(MARK_EXPR_ACCEPT_PR))
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) $(PY) manage.py migrate --noinput
	@cd $(CODE_DIR); \
	  DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	  PYTHONPATH=$(CODE_DIR) \
	  TEST_LANE=pr \
	  RUN_PROCESSOR_FORCE_BUILD=1 \
	  CI=true \
	  LOG_STREAM=stderr \
	  python -m pytest -m '$(MARK_EXPR_ACCEPT_PR)'
	@$(MAKE) compose-down

# Supply-chain acceptance: pinned-only, mock, still hermetic by default.
.PHONY: test-acceptance-dev
test-acceptance-dev: compose-up _wait-db
	$(call guard_collect,$(MARK_EXPR_ACCEPT_SUPPLY))
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) $(PY) manage.py migrate --noinput
	@cd $(CODE_DIR); \
	  DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	  PYTHONPATH=$(CODE_DIR) \
	  TEST_LANE=supplychain \
	  RUN_PROCESSOR_FORCE_BUILD=0 \
	  CI=true \
	  LOG_STREAM=stderr \
	  python -m pytest -m '$(MARK_EXPR_ACCEPT_SUPPLY)'
	@$(MAKE) compose-down

# ---- Smoke (post-deploy; CI) -----------------------------------------------
.PHONY: test-smoke
test-smoke:
	$(call guard_collect,$(MARK_EXPR_SMOKE))
	@PYTHONPATH=$(CODE_DIR) \
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	TEST_LANE=staging \
	LOG_STREAM=stderr \
	python -m pytest -m '$(MARK_EXPR_SMOKE)'

# ---- Modal dev workflow (manual sandbox) ----------------------------------
# Usage: make build-processor REF=llm/litellm@1
.PHONY: build-processor
build-processor:
ifndef REF
	$(error REF is required. Usage: make build-processor REF=llm/litellm@1)
endif
	@echo "Building processor $(REF) locally from current source..."
	@cd $(CODE_DIR) && PYTHONPATH=. \
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	python manage.py run_processor \
	  --ref $(REF) --adapter local --mode mock --build \
	  --write-prefix "/artifacts/outputs/dev/{execution_id}/" \
	  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"build test"}]}}' \
	  --json >/dev/null
	@echo "Build completed for $(REF)"

# Deploy to Modal dev environment
.PHONY: deploy-modal-dev
deploy-modal-dev:
ifndef REF
	$(error REF is required. Usage: make deploy-modal-dev REF=llm/litellm@1)
endif
	@echo "Deploying $(REF) to Modal dev environment..."
	@cd $(CODE_DIR) && DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	MODAL_ENVIRONMENT=dev \
	python manage.py deploy_modal --ref $(REF) --env dev
	@echo "Deployed $(REF) to Modal dev"

# Build → Push → Deploy with image override (dev convenience)
.PHONY: modal-dev-build-push-deploy
modal-dev-build-push-deploy:
ifndef REF
	$(error REF is required. Usage: make modal-dev-build-push-deploy REF=llm/litellm@1)
endif
	@echo "Building, pushing, and deploying $(REF) to Modal dev..."
	@cd $(CODE_DIR) && set -euo pipefail; \
	DIGEST=$$(DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) python manage.py build_processor --ref $(REF)); \
	echo "Built digest: $$DIGEST"; \
	OCI=$$(DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) python manage.py push_processor --digest $$DIGEST --repo ghcr.io/$(USER)/theory-api); \
	echo "Pushed OCI: $$OCI"; \
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) MODAL_ENVIRONMENT=dev \
	python manage.py deploy_modal --ref $(REF) --env dev --image-override $$OCI --app-rev $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
	@echo "✅ Dev build-push-deploy completed for $(REF)"

# Smoke test Modal dev deployment (mock mode)
.PHONY: smoke-modal-dev
smoke-modal-dev:
ifndef REF
	$(error REF is required. Usage: make smoke-modal-dev REF=llm/litellm@1)
endif
	$(eval SAFE_REF := $(shell echo $(REF) | tr '/@' '___'))
	@echo "Smoke testing $(REF) on Modal dev (mock mode)..."
	@cd $(CODE_DIR) && PYTHONPATH=. \
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	MODAL_ENVIRONMENT=dev \
	python manage.py run_processor \
	  --ref $(REF) --adapter modal --mode mock \
	  --write-prefix "/artifacts/outputs/smoke/{execution_id}/" \
	  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"smoke test"}]}}' \
	  --json \
	  --adapter-opt function=smoke \
	  1>/tmp/modal_$(SAFE_REF)_mock.json \
	  2>/tmp/modal_$(SAFE_REF)_mock.ndjson
	@echo "Results saved to /tmp/modal_$(SAFE_REF)_mock.json"
	@jq . /tmp/modal_$(SAFE_REF)_mock.json

# Real test Modal dev deployment (requires secrets)
.PHONY: real-modal-dev
real-modal-dev:
ifndef REF
	$(error REF is required. Usage: make real-modal-dev REF=llm/litellm@1)
endif
	$(eval SAFE_REF := $(shell echo $(REF) | tr '/@' '___'))
	@echo "Real testing $(REF) on Modal dev (requires secrets)..."
	@cd $(CODE_DIR) && PYTHONPATH=. \
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	MODAL_ENVIRONMENT=dev \
	python manage.py run_processor \
	  --ref $(REF) --adapter modal --mode real \
	  --write-prefix "/artifacts/outputs/dev/{execution_id}/" \
	  --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"real test"}]}}' \
	  --json \
	  --adapter-opt function=run \
	  1>/tmp/modal_$(SAFE_REF)_real.json \
	  2>/tmp/modal_$(SAFE_REF)_real.ndjson
	@echo "Results saved to /tmp/modal_$(SAFE_REF)_real.json"
	@jq . /tmp/modal_$(SAFE_REF)_real.json

# Full Modal dev workflow: build → deploy → smoke test
.PHONY: modal-dev-workflow
modal-dev-workflow:
ifndef REF
	$(error REF is required. Usage: make modal-dev-workflow REF=llm/litellm@1)
endif
	@echo "Running full Modal dev workflow for $(REF)..."
	@$(MAKE) build-processor REF=$(REF)
	@$(MAKE) deploy-modal-dev REF=$(REF)
	@$(MAKE) smoke-modal-dev REF=$(REF)
	@echo "Modal dev workflow completed for $(REF)"
