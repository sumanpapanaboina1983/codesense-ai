.PHONY: help install install-dev format lint test test-unit test-integration test-e2e coverage run clean \
        docker-build docker-up docker-up-dev docker-up-webui docker-down docker-logs docker-ps docker-clean \
        db-migrate db-rollback db-revision

# ===========================================
# Help
# ===========================================
help:
	@echo "CodeSense AI - Available Commands"
	@echo "=================================="
	@echo ""
	@echo "Local Development:"
	@echo "  install        Install production dependencies"
	@echo "  install-dev    Install development dependencies"
	@echo "  format         Format code with black and ruff"
	@echo "  lint           Run linting checks"
	@echo "  test           Run all tests"
	@echo "  test-unit      Run unit tests only"
	@echo "  test-integration Run integration tests"
	@echo "  test-e2e       Run end-to-end tests"
	@echo "  coverage       Run tests with coverage report"
	@echo "  run            Run the development server locally"
	@echo "  clean          Remove build artifacts"
	@echo ""
	@echo "Docker Commands:"
	@echo "  docker-build   Build all Docker images"
	@echo "  docker-up      Start all services (production mode)"
	@echo "  docker-up-dev  Start all services (development mode with hot reload)"
	@echo "  docker-up-webui Start all services + OpenWebUI frontend"
	@echo "  docker-down    Stop all services"
	@echo "  docker-logs    View logs from all services"
	@echo "  docker-ps      Show running containers status"
	@echo "  docker-clean   Remove all containers, volumes, and images"
	@echo ""
	@echo "Database Commands:"
	@echo "  db-migrate     Run database migrations"
	@echo "  db-rollback    Rollback last migration"
	@echo "  db-revision    Create new migration"
	@echo ""
	@echo "Service URLs (when running):"
	@echo "  API:           http://localhost:8000"
	@echo "  API Docs:      http://localhost:8000/docs"
	@echo "  Neo4j Browser: http://localhost:7474"
	@echo "  Neo4j MCP:     http://localhost:3006"
	@echo "  Filesystem MCP: http://localhost:3004"
	@echo "  OpenWebUI:     http://localhost:3080 (with --profile webui)"

# ===========================================
# Local Development
# ===========================================
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

format:
	black src tests
	ruff check --fix src tests

lint:
	ruff check src tests
	black --check src tests
	mypy src

test:
	pytest tests/

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v -m integration

test-e2e:
	pytest tests/e2e/ -v -m e2e

coverage:
	pytest --cov=src --cov-report=html --cov-report=term-missing tests/

run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true

# ===========================================
# Docker Commands
# ===========================================
docker-build:
	@echo "Building all Docker images..."
	docker-compose build
	@echo "Build complete!"

docker-up:
	@echo "Starting all services in production mode..."
	docker-compose up -d
	@echo ""
	@echo "Services starting. Check status with 'make docker-ps'"
	@echo ""
	@echo "Service URLs:"
	@echo "  API:           http://localhost:8000"
	@echo "  API Docs:      http://localhost:8000/docs"
	@echo "  Neo4j Browser: http://localhost:7474"
	@echo "  Neo4j MCP:     http://localhost:3006"
	@echo "  Filesystem MCP: http://localhost:3004"

docker-up-dev:
	@echo "Starting all services in development mode (with hot reload)..."
	docker-compose --profile dev up -d postgres redis neo4j neo4j-mcp filesystem-mcp api-dev
	@echo ""
	@echo "Development services starting with hot reload..."
	@echo "API will be available at http://localhost:8000"

docker-up-webui:
	@echo "Starting all services with OpenWebUI frontend..."
	docker-compose --profile webui up -d
	@echo ""
	@echo "Services starting. OpenWebUI available at http://localhost:3080"

docker-down:
	@echo "Stopping all services..."
	docker-compose --profile dev --profile webui down
	@echo "All services stopped."

docker-logs:
	docker-compose logs -f

docker-ps:
	@echo "Running containers:"
	@echo ""
	docker-compose --profile dev --profile webui ps

docker-clean:
	@echo "WARNING: This will remove all containers, volumes, and images for this project!"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	docker-compose --profile dev --profile webui down -v --rmi local
	@echo "Cleanup complete."

# ===========================================
# Database Commands
# ===========================================
db-migrate:
	alembic upgrade head

db-rollback:
	alembic downgrade -1

db-revision:
	@read -p "Enter migration message: " msg; \
	alembic revision --autogenerate -m "$$msg"

# ===========================================
# Quick Start
# ===========================================
quickstart: docker-build docker-up
	@echo ""
	@echo "============================================"
	@echo "CodeSense AI is starting up!"
	@echo "============================================"
	@echo ""
	@echo "Wait for services to be healthy, then visit:"
	@echo "  http://localhost:8000/docs"
	@echo ""
	@echo "Check service status with: make docker-ps"
