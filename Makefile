PYTHON := .venv/bin/python

.PHONY: lint lint-fix format test

lint:
	$(PYTHON) -m ruff check .

lint-fix:
	$(PYTHON) -m ruff check --fix .

format:
	$(PYTHON) -m ruff format .

test:
	$(PYTHON) -m pytest
