SHELL := /bin/bash
.PHONY: compose-up compose-down wait-db migrate makemigrations test-unit test-acceptance test-property test-all docs docs-export docs-drift-check ci-get-image-ref ci-pin-processor test-coverage deadcode import-graph deps-lint lint-deadcode mutmut-run mutmut-reset

# --- Docker services for acceptance/integration ---
compose-up:
	docker compose up -d postgres redis minio

compose-down:
	docker compose down

wait-db:
	until pg_isready -h 127.0.0.1 -p 5432 -U postgres -d postgres >/dev/null 2>&1; do sleep 1; done

# --- Django tasks (always from ./code) ---
migrate:
	cd code && python manage.py migrate --noinput

makemigrations:
	cd code && python manage.py makemigrations

# --- Tests ---
test-unit:
	@echo "DB ENGINE:" && cd code && DJANGO_SETTINGS_MODULE=backend.settings.unittest python -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"
	cd code && DJANGO_SETTINGS_MODULE=backend.settings.unittest python -m pytest -q -m "unit and not integration and not requires_postgres"

test-acceptance:
	$(MAKE) compose-up
	$(MAKE) wait-db
	cd code && DJANGO_SETTINGS_MODULE=backend.settings.test python manage.py migrate --noinput
	@echo "DB ENGINE:" && cd code && DJANGO_SETTINGS_MODULE=backend.settings.test python -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"
	cd code && DJANGO_SETTINGS_MODULE=backend.settings.test python -m pytest -q -m "ledger_acceptance or requires_postgres"

test-property:
	@echo "DB ENGINE:" && cd code && DJANGO_SETTINGS_MODULE=backend.settings.unittest python -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"
	cd code && DJANGO_SETTINGS_MODULE=backend.settings.unittest python -m pytest -q tests/property

test-all:
	DJANGO_SETTINGS_MODULE=backend.settings.unittest \
	pytest -q

# --- Docs as contracts ---
docs-export:
	cd code && python manage.py docs_export --out ../docs/_generated --erd --api --schemas

docs-drift-check: docs-export
	git diff --exit-code -- docs/_generated

docs:
	$(MAKE) docs-drift-check
	make -C docs html

# --- Linting ---
lint-ref-resolver:
	@! rg -n "replace\('/','_'\)" code/apps/core | rg -v "processors/resolver.py" || \
	 (echo "✗ Ref mapping must go through processors/resolver.py"; exit 1)

# --- CI/CD Helpers ---
ci-get-image-ref:
	@set -euo pipefail; \
	if [ ! -f "scripts/ci/get_image_ref.py" ]; then \
		echo "ERROR: scripts/ci/get_image_ref.py not found" >&2; \
		exit 1; \
	fi; \
	python scripts/ci/get_image_ref.py

ci-pin-processor:
	@set -euo pipefail; \
	if [ $$# -ne 3 ]; then \
		echo "Usage: make ci-pin-processor PROCESSOR=<name> IMAGE_BASE=<base> DIGEST=<digest>" >&2; \
		echo "Example: make ci-pin-processor PROCESSOR=llm_litellm IMAGE_BASE=ghcr.io/owner/llm-litellm DIGEST=sha256:abc123..." >&2; \
		exit 1; \
	fi; \
	if [ ! -f "scripts/ci/pin_processor.py" ]; then \
		echo "ERROR: scripts/ci/pin_processor.py not found" >&2; \
		exit 1; \
	fi; \
	python scripts/ci/pin_processor.py "$(PROCESSOR)" "$(IMAGE_BASE)" "$(DIGEST)"

# --- Dead Code Detection ---
# --- Coverage (unit-only, hermetic, SQLite) ---
# Produces coverage.xml/json at repo root for diff-cover.
COVERAGE_ENV = COVERAGE_RCFILE=../.coveragerc COVERAGE_FILE=../.coverage

test-coverage:
	cd code && $(COVERAGE_ENV) coverage erase
	# Sanity: show which DB engine we're about to test with
	@echo "DB ENGINE:" && cd code && DJANGO_SETTINGS_MODULE=backend.settings.unittest python -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"
	cd code && DJANGO_SETTINGS_MODULE=backend.settings.unittest $(COVERAGE_ENV) coverage run -m pytest -q -m "unit and not integration and not requires_postgres"
	cd code && $(COVERAGE_ENV) coverage xml -o ../coverage.xml
	cd code && $(COVERAGE_ENV) coverage json -o ../coverage.json
	cd code && $(COVERAGE_ENV) coverage report

# Static dead-code check with allowlist (to handle dynamic usage)
deadcode:
	vulture code code/vulture_whitelist.py --min-confidence 80 --exclude "*/migrations/*,*/tests/*" > vulture_report.txt || true
	python scripts/ci/vulture_gate.py vulture_report.txt

# Import graph reachability: fails if a module isn't reachable from entrypoints
# NOTE: Disabled for Django code due to dynamic loading false positives
import-graph:
	cd code && python -m tests.tools.check_import_reachability

# Import reachability for pure Python modules only (libs, processors)
import-graph-pure:
	python scripts/ci/reachability_pure_python.py

# Unused deps / missing imports
deps-lint:
	deptry code

# Convenience meta target used in PR checks
lint-deadcode: deadcode import-graph-pure deps-lint

# --- Pre-commit Hooks ---
precommit-install:
	python -m pip install -U pre-commit ruff
	pre-commit install

format:
	ruff check --fix .
	ruff format .

# --- Mutation Testing ---
# Reset mutation testing database
mutmut-reset:
	cd code && mutmut reset

# Run mutation testing (heavy - use sparingly)
mutmut-run:
	cd code && mutmut run --paths-to-mutate apps/core/adapters/,apps/core/utils/ --tests-dir tests/ --runner "python -m pytest -x" --max-mutations 20

# Show mutation testing results
mutmut-results:
	cd code && mutmut show
