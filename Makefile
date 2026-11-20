.PHONY: help setup dev lint test audit clean

PYTHON := $(shell which python3)
VENV ?= venv
VENV_BIN ?= $(VENV)/bin
PATH := $(VENV_BIN):$(PATH)

help:
	@echo "Tinkr Development & Build Tasks:"
	@echo "  make setup   - Create virtual environment, install dev dependencies, seed DB"
	@echo "  make dev     - Run Flask API server"
	@echo "  make lint    - Run ruff linter on all python files"
	@echo "  make test    - Run pytest test suite"
	@echo "  make audit   - Run pip-audit security vulnerability scan"

setup:
	@if command -v uv >/dev/null 2>&1; then \
		uv venv $(VENV) --python 3.12; \
		uv pip install --python $(VENV_BIN)/python -r requirements-dev.txt; \
	else \
		$(PYTHON) -m venv $(VENV); \
		$(VENV_BIN)/pip install --upgrade pip; \
		$(VENV_BIN)/pip install -r requirements-dev.txt; \
	fi
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi
	@if [ ! -f company_data.db ]; then \
		$(VENV_BIN)/python setup_db.py; \
	fi

dev:
	@if [ -x "$(VENV_BIN)/python" ]; then \
		$(VENV_BIN)/python api_server.py; \
	else \
		python3 api_server.py; \
	fi

lint:
	@if [ -x "$(VENV_BIN)/ruff" ]; then \
		$(VENV_BIN)/ruff check .; \
	else \
		ruff check .; \
	fi

test:
	@if [ -x "$(VENV_BIN)/pytest" ]; then \
		$(VENV_BIN)/pytest -v; \
	else \
		pytest -v; \
	fi

audit:
	@if [ -x "$(VENV_BIN)/pip-audit" ]; then \
		$(VENV_BIN)/pip-audit -r requirements.txt; \
	else \
		pip-audit -r requirements.txt; \
	fi

clean:
	rm -rf __pycache__ *.pyc .pytest_cache .ruff_cache
