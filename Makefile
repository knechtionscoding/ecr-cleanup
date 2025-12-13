UV ?= uv

install:
	pre-commit install
	$(UV) sync --extra dev

lint: install
	pre-commit run --all-files

test: lint
	$(UV) run -- pytest -v

run:
	$(UV) run -- python ./main.py

push: test
	git push all main

dry-run:
	DRY_RUN=true $(UV) run -- python ./main.py

all: install lint test dry-run
.PHONY: all lint test run dry-run install
.DEFAULT_GOAL :=all
