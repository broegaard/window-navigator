.PHONY: lint format test

lint:
	ruff check .

format:
	ruff format .

test:
	pytest
