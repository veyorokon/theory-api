SHELL := /bin/bash
.PHONY: compose-up compose-down wait-db migrate makemigrations test-unit test-acceptance test-property test-all docs docs-export docs-drift-check

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
	DJANGO_SETTINGS_MODULE=backend.settings.unittest \
	pytest -q -m "unit and not integration and not requires_postgres"

test-acceptance:
	$(MAKE) compose-up
	$(MAKE) wait-db
	DJANGO_SETTINGS_MODULE=backend.settings.test \
	cd code && python manage.py migrate --noinput
	DJANGO_SETTINGS_MODULE=backend.settings.test \
	pytest -q -m "ledger_acceptance or requires_postgres"

test-property:
	$(MAKE) compose-up
	$(MAKE) wait-db
	DJANGO_SETTINGS_MODULE=backend.settings.test \
	cd code && python manage.py migrate --noinput
	DJANGO_SETTINGS_MODULE=backend.settings.test \
	pytest -q tests/property

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