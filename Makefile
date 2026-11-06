# Cross-platform targets (make on macOS/Linux, or Git Bash / WSL on Windows)
PY ?= $(if $(wildcard backend/.venv/bin/python),backend/.venv/bin/python,backend/.venv/Scripts/python)

.PHONY: install test coverage load-data backend frontend run

backend/.venv:
	$(if $(shell python3 -c 'import sys' 2>/dev/null && echo ok),python3,python) -m venv backend/.venv

install: backend/.venv
	$(PY) -m pip install -r backend/requirements-dev.txt
	npm ci --prefix frontend

test:
	$(PY) -m pytest

coverage:
	$(PY) -m pytest --cov --cov-report=term

load-data:
	cd backend && ../$(PY) -m etl.edgar_ingest --fetch --load

backend:
	cd backend && ../$(PY) -m uvicorn main:app --port 8000

frontend:
	npm run dev --prefix frontend

run:
	./run.sh
