SHELL := /bin/sh
DB_PATH ?= data/dev.sqlite3
FT_MANIFEST_PATH ?= data/training/fine_tuning_dataset_manifest.json
ADAPTER_ARTIFACT_ROOT ?= data/models/adapters
MODEL_EVALUATION_INPUT ?= data/evaluation/model_evaluation_input.json
MODEL_EVALUATION_REPORT ?= data/evaluation/model_evaluation_report.json

REQUIRED_DIRS := \
	apps/api \
	apps/web \
	packages/ontology \
	packages/ingestion \
	packages/extraction \
	packages/fusion \
	packages/labelling \
	packages/training \
	packages/evaluation \
	packages/contracts \
	packages/storage \
	packages/model-registry \
	packages/model_registry

REQUIRED_FILES := \
	README.md \
	CONTRIBUTING.md \
	.env.example \
	Makefile

.PHONY: help setup check test test-backend test-frontend dev db-migrate db-seed db-dev fine-tuning-prepare adapter-train model-evaluate

help:
	@printf '%s\n' 'Local tasks:'
	@printf '%s\n' '  make setup  - create local placeholder directories'
	@printf '%s\n' '  make check  - verify skeleton files, local env ignore rules, and tests'
	@printf '%s\n' '  make test   - run backend and frontend tests from the repo root'
	@printf '%s\n' '  make test-backend  - run backend/unit contract tests'
	@printf '%s\n' '  make test-frontend - run frontend tests'
	@printf '%s\n' '  make dev    - print local placeholder app flow'
	@printf '%s\n' '  make db-migrate - apply local SQLite migrations'
	@printf '%s\n' '  make db-seed    - seed local SQLite dev data'
	@printf '%s\n' '  make db-dev     - migrate and seed the local dev database'
	@printf '%s\n' '  make fine-tuning-prepare - write a local fine-tuning dataset manifest stub'
	@printf '%s\n' '  make adapter-train - write local sport adapter and label-head artifacts'
	@printf '%s\n' '  make model-evaluate - compare current and candidate model runs locally'

setup:
	@for dir in $(REQUIRED_DIRS); do mkdir -p "$$dir"; done
	@printf '%s\n' 'Local skeleton directories are present.'

check:
	@for dir in $(REQUIRED_DIRS); do test -d "$$dir" || { printf '%s\n' "Missing directory: $$dir"; exit 1; }; done
	@for file in $(REQUIRED_FILES); do test -f "$$file" || { printf '%s\n' "Missing file: $$file"; exit 1; }; done
	@test -z "$$(git ls-files .env .envrc)" || { printf '%s\n' '.env or .envrc is tracked'; exit 1; }
	@git check-ignore -q .env
	@git check-ignore -q .envrc
	@git check-ignore -q .env.local
	@! git check-ignore -q .env.example
	@printf '%s\n' 'Skeleton checks passed.'
	@$(MAKE) test

test: test-backend test-frontend

test-backend:
	@python -m unittest discover -s tests

test-frontend:
	@test -d apps/web/node_modules || npm --prefix apps/web ci
	@npm --prefix apps/web test

dev:
	@printf '%s\n' 'Run the local API: python -m apps.api.server --host 127.0.0.1 --port 8000'
	@printf '%s\n' 'Run the frontend: npm --prefix apps/web run dev -- --host 127.0.0.1'

db-migrate:
	@python -m packages.storage.migrate --db-path "$(DB_PATH)"

db-seed:
	@python -m packages.storage.seed --db-path "$(DB_PATH)"

db-dev: db-seed
	@printf '%s\n' 'Local dev database is ready at $(DB_PATH).'

fine-tuning-prepare:
	@python -m packages.training.prepare_finetuning --db-path "$(DB_PATH)" --output-path "$(FT_MANIFEST_PATH)"

adapter-train:
	@python -m packages.training.adapter_training --db-path "$(DB_PATH)" --artifact-root "$(ADAPTER_ARTIFACT_ROOT)"

model-evaluate:
	@python -m packages.evaluation.model_evaluation "$(MODEL_EVALUATION_INPUT)" --output-path "$(MODEL_EVALUATION_REPORT)"
