# ED Finder — developer convenience targets.
#
# Real builds happen via docker compose / yarn / pytest directly; this
# Makefile just collects the most-used recipes so you don't have to
# remember the env-var incantations.
.PHONY: help lint typecheck test seed-check api-smoke state-check state-check-docs test-env-check test-unit test-operator test-db test-db-isolation test-integration test-ci-local review-preflight review-quick review-full clean

PYTHON ?= python

help:  ## Show this help
	@awk 'BEGIN{FS=":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ── DB / seed ────────────────────────────────────────────────────────────────
seed-check:  ## Apply every sql/*.sql with ON_ERROR_STOP=1 + invariants
	bash scripts/seed_check.sh

# ── Backend ──────────────────────────────────────────────────────────────────
test:  ## Run backend unit + integration tests
	python -m unittest discover -s tests -p test_smoke.py
	DATABASE_URL=$${DATABASE_URL:-postgresql://edfinder:edfinder@127.0.0.1:55432/edfinder} \
	REDIS_URL=$${REDIS_URL:-redis://localhost:6379/15} \
	CORS_ORIGINS=$${CORS_ORIGINS:-http://test} \
	ADMIN_TOKEN=$${ADMIN_TOKEN:-test-admin-token} \
	LOG_LEVEL=$${LOG_LEVEL:-WARNING} \
	EXPOSE_ERROR_DETAIL=true \
	python -m pytest tests/integration/ -q

test-env-check:  ## Run the local test-environment preflight without writes
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/dev/test_env_preflight.py

state-check:  ## Resolve Stage 19/test-env state authority before operational work
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/dev/resolve_project_state.py --strict

state-check-docs:  ## Resolve Stage 19/test-env state authority for docs-only work
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/dev/resolve_project_state.py --strict --allow-docs-only

test-unit:  ## Run tests that do not require external services
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B -m pytest -m "unit or not (integration or db or operator or e2e or slow)"

test-operator:  ## Run Stage 19 operator safety tests
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B -m pytest tests/test_stage19ar_operator_script.py tests/test_stage19ap_operator_visibility.py -m operator

test-db:  ## Run DB-marked tests, including explicit skips for absent real services
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B -m pytest -m db -rs

test-db-isolation:  ## Run DB isolation guardrails and real Postgres readiness checks
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B -m pytest tests/test_db_isolation_guardrails.py tests/test_stage19_real_postgres_readiness.py -p no:cacheprovider -rs
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B -m py_compile tests/helpers/db_isolation.py

test-integration:  ## Run integration-marked tests
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B -m pytest -m integration -rs

test-ci-local: test-env-check test-db-isolation  ## Run focused local CI checks for the test environment stack
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B -m pytest tests/test_test_env_preflight.py tests/test_stage19ar_operator_script.py tests/test_stage19ap_operator_visibility.py -rs
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B -m py_compile scripts/dev/test_env_preflight.py scripts/operator/stage19ar_edsm_25_row_staging_pilot.py scripts/operator/stage19as_au_edsm_100_row_controlled_expansion.py tests/helpers/db_isolation.py
	git diff --check

# ── Disposable Review Lab ────────────────────────────────────────────────────
review-preflight:  ## Check the isolated Review Lab contract without Docker writes
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/dev/review_environment.py preflight

review-quick:  ## Smoke-test Finder → Detail → Planner against the isolated Docker stack
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/dev/review_environment.py verify --mode quick --scenario planner_core --confirm-local-review-environment

review-full:  ## Run the full isolated Review Lab, including browser and accessibility checks
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/dev/review_environment.py verify --mode full --scenario all --confirm-local-review-environment

# ── Frontend ──────────────────────────────────────────────────────────────────
typecheck:  ## yarn typecheck the frontend
	cd frontend-v2 && yarn typecheck

lint:  ## ruff backend + eslint frontend
	ruff check apps tests
	cd frontend-v2 && yarn lint

# ── Cleanup ──────────────────────────────────────────────────────────────────
clean:  ## Remove caches
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	rm -rf frontend-v2/dist frontend-v2/playwright-report
