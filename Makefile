.PHONY: install test test-live frontend-build docker-build ci

PYTHON ?= python

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest -m "not live"

test-live:
	$(PYTHON) -m pytest -m live -s

frontend-build:
	npm --prefix frontend ci
	npm --prefix frontend run build

docker-build:
	docker build -t enterprise-ai-agent-backend ./backend

ci: test frontend-build docker-build
