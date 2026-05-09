# ED Finder — developer convenience targets.
#
# Real builds happen via docker compose / yarn / pytest directly; this
# Makefile just collects the most-used recipes so you don't have to
# remember the env-var incantations.
.PHONY: help lint typecheck test seed-check api-smoke clean

help:  ## Show this help
	@awk 'BEGIN{FS=":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ── DB / seed ────────────────────────────────────────────────────────────────
seed-check:  ## Apply every sql/*.sql with ON_ERROR_STOP=1 + invariants
	bash scripts/seed_check.sh

# ── Backend ──────────────────────────────────────────────────────────────────
test:  ## Run backend unit + integration tests
	python -m unittest discover -s tests -p test_smoke.py
	DATABASE_URL=$${DATABASE_URL:-postgresql://edfinder:edfinder@localhost:5432/edfinder} \
	REDIS_URL=$${REDIS_URL:-redis://localhost:6379/15} \
	CORS_ORIGINS=$${CORS_ORIGINS:-http://test} \
	ADMIN_TOKEN=$${ADMIN_TOKEN:-test-admin-token} \
	LOG_LEVEL=$${LOG_LEVEL:-WARNING} \
	EXPOSE_ERROR_DETAIL=true \
	python -m pytest tests/integration/ -q

api-smoke:  ## Curl the Phase-2 happy paths against a running API
	@API=$${API:-http://localhost:8000}; \
	echo "▶ /api/health"        && curl -fsS $$API/api/health | python3 -m json.tool; \
	echo "▶ search HighTech"    && curl -fsS -X POST $$API/api/local/search -H 'Content-Type: application/json' \
	    -d '{"reference_coords":{"x":0,"y":0,"z":0},"filters":{"distance":{"min":0,"max":1000},"economy":"HighTech"},"size":3}' \
	    | python3 -c "import sys,json;d=json.load(sys.stdin);print(f\"  {d.get('count')} results, total={d.get('total')}, capped={d.get('total_is_capped')}\")"; \
	echo "▶ events recent"      && curl -fsS $$API/api/events/recent | python3 -m json.tool | head -10

# ── Frontend ────────────────────────────────────────────────────────────────
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
