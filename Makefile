.PHONY: setup dev test eval lint format clean

# ============================================================================
# Agent Orchestration Platform — Development Commands
# ============================================================================

setup:
	pip install -r requirements.txt
	cp .env.example .env
	@echo "Setup complete. Edit .env with your API keys."

dev:
	docker compose up -d db redis
	uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

dev-all:
	docker compose up --build

test:
	pytest tests/ -v --cov=src --cov-report=term-missing

eval:
	python -m evals.runner --project agent-orchestration

lint:
	ruff check src/ tests/
	mypy src/ --ignore-missing-imports

format:
	ruff format src/ tests/

clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Agent operations
agent-status:
	curl -s http://localhost:8000/api/v1/agents/status | python -m json.tool

agent-cost:
	curl -s http://localhost:8000/api/v1/cost/summary | python -m json.tool

health:
	curl -s http://localhost:8000/api/v1/health | python -m json.tool

# Database
db-migrate:
	@for f in schema/*.sql; do \
		echo "Running $$f..."; \
		PGPASSWORD=postgres psql -h localhost -U postgres -d agent_orchestration -f $$f; \
	done

db-reset:
	docker compose down -v
	docker compose up -d db
	sleep 3
	make db-migrate
