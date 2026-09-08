# Basic developer tasks for battery_health.
#
# Everything runs against the Python on PATH by default; override with
#   make PYTHON=path/to/python <target>

PYTHON      ?= python
PIP         := $(PYTHON) -m pip
VERSION     := $(shell $(PYTHON) scripts/build.py --print-version)
EXE_NAME    := $(shell $(PYTHON) scripts/build.py --print-name)
SOURCES     := battery_health.py scripts/build.py tests

.DEFAULT_GOAL := help

.PHONY: help version install run test lint typecheck check build package clean distclean

help: ## Show this help
	@echo "battery_health $(VERSION)"
	@echo
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "This environment builds: $(EXE_NAME)"

version: ## Print the project version
	@echo $(VERSION)

install: ## Install the project plus its development dependencies
	$(PIP) install -e ".[dev]"

run: ## Run the battery health checker
	$(PYTHON) battery_health.py

test: ## Run the unit tests
	$(PYTHON) -m pytest -q

lint: ## Run ruff
	$(PYTHON) -m ruff check $(SOURCES)

typecheck: ## Run mypy
	$(PYTHON) -m mypy $(SOURCES)

check: lint typecheck test ## Lint, typecheck and test

build: ## Build a standalone executable for this platform into dist/
	$(PYTHON) scripts/build.py

package: check ## Build and archive a release for this platform into release/
	$(PYTHON) scripts/build.py --package

clean: ## Remove build intermediates and caches
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['build', '.mypy_cache', '.pytest_cache', '.ruff_cache', '__pycache__', 'tests/__pycache__']]"

distclean: clean ## Also remove built executables and archives
	$(PYTHON) -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ['dist', 'release']]"
