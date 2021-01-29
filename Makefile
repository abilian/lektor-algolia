SHELL := bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c
.DELETE_ON_ERROR:
MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules

.PHONY:
all: typecheck lint test ## Run all checks (test, lint, typecheck)


.PHONY:
install:  # Install the app locally
	poetry install

.PHONY:
test:  ## Run tests
	poetry run pytest .

.PHONY:
lint:  ## Run linting
	poetry run black --check .
	poetry run isort -c .
	poetry run flake8 .
	# poetry run pydocstyle .

.PHONY:
fix:  ## Run autoformatters
	poetry run black .
	poetry run isort .

.PHONY:
typecheck:  ## Run typechecking
	poetry run mypy --show-error-codes --pretty .

help: Makefile
	@grep -E '(^[a-zA-Z_-]+:.*?##.*$$)|(^##)' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[32m%-30s\033[0m %s\n", $$1, $$2}' | sed -e 's/\[32m##/[33m/'
