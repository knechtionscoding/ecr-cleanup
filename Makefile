install:
	pre-commit install
	poetry install

lint: install
	pre-commit run --all

test: lint
	poetry run pytest -v

run:
	poetry run ./main.py

dry-run:
	DRY_RUN=true poetry run ./main.py

all: install lint test dry-run
.PHONY: all lint test run dry-run install
.DEFAULT_GOAL :=all
