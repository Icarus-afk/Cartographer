.PHONY: install install-dev lint test test-verbose clean build

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pip install ruff pytest

lint:
	ruff check cartographer/ tests/

lint-fix:
	ruff check --fix cartographer/ tests/

test:
	python -m pytest tests/ -v

test-quick:
	python -m pytest tests/ -x --tb=short

clean:
	rm -rf build/ dist/ *.egg-info/ __pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

build:
	pip install build
	python -m build

all: install lint test
