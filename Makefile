# Makefile — Clean, digest-first workflow
# ---------------------------------------------------------------------
# Smallest correct, reversible steps. One execution surface. Two modes.
# PR is hermetic (no egress). Staging/Main pinned only. Dev can push.
# ---------------------------------------------------------------------

SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c
MAKEFLAGS += --no-builtin-rules

# ---- Repo dirs -------------------------------------------------------------
CODE_DIR ?= code
TEST_DIR ?= tests

# ---- Python / Django -------------------------------------------------------
PY ?= python
DJANGO_SETTINGS ?= backend.settings.unittest
PYTEST ?= python -m pytest

# ---- Docker / Compose / Modal ---------------------------------------------
DOCKER ?= docker
COMPOSE ?= docker compose
COMPOSE_PROJECT ?= theory
COMPOSE_FILES := -f docker-compose.yml

# ---- GHCR (registry) -------------------------------------------------------
# Example: ghcr.io/<owner>/<repo>
GHCR_NS ?= ghcr.io/$(USER)/theory-api

# ---- Test markers (folder taxonomy = policy) -------------------------------
M_UNIT          := (unit or contracts or property) and not requires_docker and not requires_postgres and not requires_minio
M_INTEGRATION   := (integration and not requires_docker and not requires_postgres and not requires_minio)
M_CONTRACTS     := contracts
M_PROPERTY      := property
M_ACCEPT_PR     := (acceptance and prlane)
M_ACCEPT_PINNED := (acceptance and supplychain)
M_SMOKE         := deploy_smoke

# ---- Utilities -------------------------------------------------------------
define guard_collect
@COUNT="$$(PYTHONPATH=$(CODE_DIR) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) $(PYTEST) --collect-only -q -m '$(1)' | grep -c ':')"; \
 if [ "$$COUNT" -eq 0 ]; then echo "✖ No tests collected for: $(1)" >&2; exit 1; else echo "✓ Collected $$COUNT tests for: $(1)"; fi
endef

define require
@[ -n "$($(1))" ] || { echo "❌ Missing required var: $(1)"; exit 1; }
endef

# ---- Help ------------------------------------------------------------------
.PHONY: help
help:
	@echo ""
	@echo "Targets:"
	@echo "  make tools-check                    - verify required CLIs (jq, yq, docker, modal)"
	@echo "  make lint                           - run linters/formatters (placeholder)"
	@echo "  make test-unit                      - unit+contracts+property (hermetic)"
	@echo "  make test-integration               - integration (hermetic)"
	@echo "  make test-contracts                 - contracts only"
	@echo "  make test-acceptance-pr             - PR lane acceptance (compose base, hermetic)"
	@echo "  make test-acceptance-pinned         - supply-chain acceptance (compose base)"
	@echo "  make test-smoke                     - post-deploy smoke (staging/main)"
	@echo ""
	@echo "Containers (digest-first):"
	@echo "  make build REF=ns/name@v            - build local image for ref"
	@echo "  make push REF=ns/name@v TAG=dev-TS  - push image to GHCR, print digest"
	@echo "  make oci REF=... TAG=...            - convenience: build+push and echo digest"
	@echo ""
	@echo "Modal (deploy by digest, verify, run):"
	@echo "  make deploy-dev REF=... OCI=ghcr.io/...@sha256:...        - deploy modal dev (by digest)"
	@echo "  make verify-modal REF=... OCI=...                         - verify modal bound digest"
	@echo "  make smoke-modal REF=...                                   - run mock via modal adapter"
	@echo "  make real-modal REF=...                                    - run real via modal adapter (dev only)"
	@echo ""
	@echo "Compose:"
	@echo "  make compose-up                       - bring up base (postgres+redis)"
	@echo "  make compose-down                     - tear down stack (remove orphans)"
	@echo ""

# ---- Tooling ---------------------------------------------------------------
.PHONY: tools-check
tools-check:
	@command -v jq >/dev/null || { echo "❌ jq missing (brew install jq)"; exit 1; }
	@command -v yq >/dev/null || { echo "❌ yq missing (brew install yq)"; exit 1; }
	@command -v $(DOCKER) >/dev/null || { echo "❌ docker missing"; exit 1; }
	@command -v modal >/dev/null || { echo "❌ modal CLI missing (pip/uv install modal-client)"; exit 1; }
	@echo "✅ Tools OK"

.PHONY: lint
lint:
	@echo "→ lint not configured; add ruff/black/mypy if desired"

# ---- Tests (hermetic lanes) ------------------------------------------------
.PHONY: test-unit
test-unit:
	$(call guard_collect,$(M_UNIT))
	@PYTHONPATH=$(CODE_DIR) \
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	TEST_LANE=pr LOG_STREAM=stderr JSON_LOGS=1 \
	$(PYTEST) -m '$(M_UNIT)'

.PHONY: test-integration
test-integration:
	$(call guard_collect,$(M_INTEGRATION))
	@PYTHONPATH=$(CODE_DIR) \
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	TEST_LANE=pr LOG_STREAM=stderr JSON_LOGS=1 \
	$(PYTEST) -m '$(M_INTEGRATION)'

.PHONY: test-contracts
test-contracts:
	$(call guard_collect,$(M_CONTRACTS))
	@PYTHONPATH=$(CODE_DIR) \
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	TEST_LANE=pr LOG_STREAM=stderr JSON_LOGS=1 \
	$(PYTEST) -m '$(M_CONTRACTS)'

.PHONY: test-acceptance-pr
test-acceptance-pr: compose-up
	$(call guard_collect,$(M_ACCEPT_PR))
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) $(PY) manage.py migrate --noinput
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) PYTHONPATH=$(CODE_DIR) \
	  TEST_LANE=pr CI=true LOG_STREAM=stderr JSON_LOGS=1 \
	  $(PYTEST) -m '$(M_ACCEPT_PR)'
	@$(MAKE) compose-down

.PHONY: test-acceptance-pinned
test-acceptance-pinned: compose-up
	$(call guard_collect,$(M_ACCEPT_PINNED))
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) $(PY) manage.py migrate --noinput
	@cd $(CODE_DIR); DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) PYTHONPATH=$(CODE_DIR) \
	  TEST_LANE=supplychain CI=true LOG_STREAM=stderr JSON_LOGS=1 \
	  $(PYTEST) -m '$(M_ACCEPT_PINNED)'
	@$(MAKE) compose-down

.PHONY: test-smoke
test-smoke:
	$(call guard_collect,$(M_SMOKE))
	@PYTHONPATH=$(CODE_DIR) DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	TEST_LANE=staging LOG_STREAM=stderr JSON_LOGS=1 \
	$(PYTEST) -m '$(M_SMOKE)'

# ---- Compose (base only: postgres+redis) -----------------------------------
.PHONY: compose-up
compose-up:
	@$(COMPOSE) $(COMPOSE_FILES) -p $(COMPOSE_PROJECT) up -d --wait

.PHONY: compose-down
compose-down:
	@$(COMPOSE) $(COMPOSE_FILES) -p $(COMPOSE_PROJECT) down -v --remove-orphans || true

# ---- Image build/push (digest-first) ---------------------------------------
# REF example: ns/name@1  -> image slug: ns-name-v1
# TAG example: dev-20250101-120000 (or any CI tag)
.PHONY: build
build:
	$(call require,REF)
	@cd $(CODE_DIR); \
	  DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) \
	  $(PY) manage.py build_processor --ref $(REF) --json | jq -r .

.PHONY: push
push:
	$(call require,REF)
	$(call require,TAG)
	@cd $(CODE_DIR); \
	  DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS); \
	  OUT=$$($(PY) manage.py build_processor --ref $(REF) --json); \
	  IMG=$$(echo "$$OUT" | jq -r '.image_tag'); \
	  REFSLUG=$$(echo "$(REF)" | tr '/@' '-'); \
	  TARGET="$(GHCR_NS)/$$REFSLUG:$(TAG)"; \
	  echo "→ Pushing $$IMG -> $$TARGET"; \
	  PJSON=$$($(PY) manage.py push_processor --image $$IMG --target $$TARGET --json); \
	  echo "$$PJSON" | jq -r .; \
	  echo "OCI=$$(echo "$$PJSON" | jq -r '.digest_ref')" > /tmp/oci.out; \
	  echo "✅ Digest: $$(cat /tmp/oci.out | cut -d= -f2)"

.PHONY: oci
oci: ## convenience: build+push+print digest (requires REF,TAG)
	$(call require,REF)
	$(call require,TAG)
	@$(MAKE) push REF="$(REF)" TAG="$(TAG)"; \
	OCI=$$(cut -d= -f2 /tmp/oci.out); echo "$$OCI"

# ---- Modal (deploy by digest ONLY) -----------------------------------------
.PHONY: deploy-dev
deploy-dev:
	$(call require,REF)
	$(call require,OCI)
	@cd $(CODE_DIR); \
	  DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) MODAL_ENVIRONMENT=dev \
	  $(PY) manage.py deploy_modal --ref $(REF) --env dev --oci "$(OCI)"
	@$(MAKE) verify-modal REF="$(REF)" OCI="$(OCI)"

.PHONY: verify-modal
verify-modal:
	$(call require,REF)
	$(call require,OCI)
	@cd $(CODE_DIR); \
	  DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) MODAL_ENVIRONMENT=dev \
	  $(PY) manage.py verify_modal_digest --ref $(REF) --env dev --oci "$(OCI)"

# ---- Run via adapters (single execution surface) ---------------------------
# Smoke/real via Modal. Stdout must be ONE JSON envelope; all logs -> stderr.
.PHONY: smoke-modal
smoke-modal:
	$(call require,REF)
	@cd $(CODE_DIR); \
	  DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) MODAL_ENVIRONMENT=dev \
	  $(PY) manage.py run_processor \
	    --ref $(REF) --adapter modal --mode mock \
	    --write-prefix "/artifacts/outputs/smoke/{execution_id}/" \
	    --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"smoke"}]}}' \
	    --json | jq -r .

.PHONY: real-modal
real-modal:
	$(call require,REF)
	@cd $(CODE_DIR); \
	  DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS) MODAL_ENVIRONMENT=dev \
	  $(PY) manage.py run_processor \
	    --ref $(REF) --adapter modal --mode real \
	    --write-prefix "/artifacts/outputs/dev/{execution_id}/" \
	    --inputs-json '{"schema":"v1","params":{"messages":[{"role":"user","content":"real"}]}}' \
	    --json | jq -r .
