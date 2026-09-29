SHELL := /bin/bash
VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help venv install dev-install lint type check test seed demo db-up alembic api worker beat docker-build docker-up clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

venv: ## Create the virtualenv
	python3 -m venv $(VENV)

install: venv ## Install the project into the venv
	$(PIP) install --upgrade pip
	$(PIP) install -e .

dev-install: install ## Install with dev/CI extras (pytest, mypy, ruff, celery)
	$(PIP) install -e ".[dev]"

lint: ## Ruff lint (app, scripts, tests)
	$(VENV)/bin/ruff check app scripts tests

type: ## mypy type-check (app, scripts)
	$(VENV)/bin/mypy app scripts

check: lint type ## Static checks

test: ## Run the pytest suite (SQLite, no services required)
	@rm -f /tmp/cybercrime-pytest.db
	$(PY) -m pytest tests -q

seed: ## Idempotent RBAC + admin bootstrap (env-driven)
	$(PY) -m scripts.seed

demo: ## Seed roles + admin + synthetic demo dataset
	$(PY) -m scripts.seed --demo

db-up: ## Start ephemeral PostGIS + Redis via docker compose
	docker compose up -d postgres redis

alembic: ## Upgrade the database to the latest schema revision
	$(VENV)/bin/alembic upgrade head

api: ## Run the FastAPI dev server on :8000
	$(VENV)/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker: ## Run the Celery worker
	$(VENV)/bin/celery -A app.workers.celery_app:celery_app worker --loglevel=info

beat: ## Run the Celery beat scheduler
	$(VENV)/bin/celery -A app.workers.celery_app:celery_app beat --loglevel=info

docker-build: ## Build the API/worker image
	docker compose build

docker-up: ## Bring up the full stack (postgres, redis, api, worker, beat)
	docker compose up -d --build

clean: ## Remove caches and build artifacts
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf var/ml .pytest_cache .mypy_cache $(VENV)