PYTHON ?= python3

.PHONY: install-dev lint typecheck test qa build clean publish-dry-run publish-testpypi publish-pypi

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy src

test:
	$(PYTHON) -m pytest -q

qa: lint typecheck test

clean:
	rm -rf build dist
	find . -maxdepth 1 -type d -name "*.egg-info" -exec rm -rf {} +

build: clean
	$(PYTHON) -m build
	$(PYTHON) -m twine check dist/*

publish-dry-run:
	./scripts/publish.sh --dry-run

publish-testpypi:
	./scripts/publish.sh --repository testpypi

publish-pypi:
	./scripts/publish.sh --repository pypi
