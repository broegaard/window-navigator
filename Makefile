PYTHON := .venv/bin/python

.PHONY: lint format test

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .

test:
	$(PYTHON) -m pytest
