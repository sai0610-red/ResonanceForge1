PYTHON ?= python3

.PHONY: dev test lint eval eval-live docker help

help:
	@echo "make dev     - run the API on http://127.0.0.1:8000"
	@echo "make test    - run pytest (no live Groq calls)"
	@echo "make lint    - run ruff on app/, tests/ and evals/"
	@echo "make eval    - run golden-case evals offline (stubbed LLM, no key)"
	@echo "make eval-live - run evals against the real model (uses quota)"
	@echo "make docker  - build and run via docker compose"

dev:
	$(PYTHON) -m uvicorn app.api:app --host 127.0.0.1 --port 8000 --reload

test:
	$(PYTHON) -m pytest tests/ -q

lint:
	$(PYTHON) -m ruff check app tests evals

eval:
	$(PYTHON) -m evals.run

eval-live:
	EVAL_LIVE=1 $(PYTHON) -m evals.run

docker:
	docker compose up --build
