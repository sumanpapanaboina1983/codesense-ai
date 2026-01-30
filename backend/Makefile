.PHONY: install dev-install test lint format clean run health docker-build docker-up docker-down docker-run docker-shell

# =============================================================================
# Local Development
# =============================================================================

# Install dependencies
install:
	poetry install --no-dev

# Install with dev dependencies
dev-install:
	poetry install

# Run tests
test:
	poetry run pytest tests/ -v --cov=src/brd_generator --cov-report=term-missing

# Run specific test
test-one:
	poetry run pytest $(TEST) -v

# Run linting
lint:
	poetry run ruff check src/ tests/
	poetry run mypy src/

# Format code
format:
	poetry run black src/ tests/
	poetry run ruff check --fix src/ tests/

# Clean build artifacts
clean:
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf dist
	rm -rf build
	rm -rf *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Run the BRD generator locally
run:
	poetry run brd-generator $(ARGS)

# Run the API server locally
run-api:
	poetry run uvicorn brd_generator.api.app:app --host 0.0.0.0 --port 8002 --reload

# Run the API server on a custom port
run-api-port:
	poetry run uvicorn brd_generator.api.app:app --host 0.0.0.0 --port $(PORT) --reload

# Run with example
run-example:
	poetry run python scripts/run_example.py

# Run from request file
run-file:
	poetry run brd-generator --request-file examples/sample_request.json

# Health check
health:
	poetry run python scripts/health_check.py

# Setup Neo4j
setup-neo4j:
	poetry run python scripts/setup_neo4j.py

# Build package
build:
	poetry build

# =============================================================================
# Docker Commands (Simplified - MCP servers via npx)
# =============================================================================

# Build Docker image
docker-build:
	docker-compose build

# Start Neo4j (MCP servers started by Copilot CLI via npx)
docker-up:
	docker-compose up -d neo4j
	@echo "Waiting for Neo4j to be healthy..."
	@sleep 15
	@echo "Neo4j is ready!"
	@echo "MCP servers will be started by Copilot CLI via npx"

# Stop all services
docker-down:
	docker-compose down

# Run BRD generator in Docker (one-off command)
docker-run:
	docker-compose run --rm brd-generator python -m brd_generator.main $(ARGS)

# Run BRD generator with a feature description
docker-generate:
	docker-compose run --rm brd-generator python -m brd_generator.main \
		--feature "$(FEATURE)" \
		--output /app/output/brd.md

# Interactive shell in the container
docker-shell:
	docker-compose run --rm brd-generator /bin/bash

# View logs
docker-logs:
	docker-compose logs -f

# View Neo4j logs
docker-logs-neo4j:
	docker-compose logs -f neo4j

# Run health check in Docker
docker-health:
	docker-compose run --rm brd-generator python scripts/health_check.py

# Setup Neo4j in Docker
docker-setup-neo4j:
	docker-compose run --rm brd-generator python scripts/setup_neo4j.py

# Clean Docker resources
docker-clean:
	docker-compose down -v --rmi local
	docker system prune -f

# =============================================================================
# Quick Start Commands
# =============================================================================

# Full Docker setup and run
docker-quickstart:
	@echo "🚀 Starting BRD Generator Stack..."
	@make docker-build
	@make docker-up
	@echo "⏳ Waiting for services..."
	@sleep 5
	@make docker-setup-neo4j
	@echo "✅ Ready! Run: make docker-generate FEATURE='your feature description'"

# =============================================================================
# MCP Configuration
# =============================================================================

# Show MCP config location
mcp-config-show:
	@echo "Host MCP config: ~/.copilot/mcp-config.json"
	@echo ""
	@cat ~/.copilot/mcp-config.json 2>/dev/null || echo "No config found"

# Test MCP servers (filesystem)
mcp-test-filesystem:
	@echo "Testing filesystem MCP server..."
	npx -y @modelcontextprotocol/server-filesystem /Users/suman.papanaboina/PycharmProjects/codesense-ai --help || echo "Install with: npm install -g @modelcontextprotocol/server-filesystem"

# Test MCP servers (neo4j)
mcp-test-neo4j:
	@echo "Testing neo4j MCP server..."
	NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=password npx -y neo4j-mcpserver --help || echo "Install with: npm install -g neo4j-mcpserver"

# =============================================================================
# Help
# =============================================================================

help:
	@echo "BRD Generator Makefile"
	@echo ""
	@echo "Local Development:"
	@echo "  make install        - Install production dependencies"
	@echo "  make dev-install    - Install with dev dependencies"
	@echo "  make test           - Run all tests"
	@echo "  make lint           - Run linting"
	@echo "  make format         - Format code"
	@echo "  make clean          - Clean build artifacts"
	@echo "  make run ARGS='...' - Run BRD generator locally"
	@echo "  make run-example    - Run example script"
	@echo "  make health         - Run health checks"
	@echo "  make setup-neo4j    - Setup Neo4j database"
	@echo "  make build          - Build package"
	@echo ""
	@echo "Docker Commands:"
	@echo "  make docker-build           - Build Docker image"
	@echo "  make docker-up              - Start Neo4j"
	@echo "  make docker-down            - Stop all services"
	@echo "  make docker-run ARGS='...'  - Run BRD generator in Docker"
	@echo "  make docker-generate FEATURE='...' - Generate BRD for feature"
	@echo "  make docker-shell           - Interactive shell in container"
	@echo "  make docker-logs            - View all logs"
	@echo "  make docker-health          - Run health check in Docker"
	@echo "  make docker-setup-neo4j     - Setup Neo4j in Docker"
	@echo "  make docker-clean           - Clean Docker resources"
	@echo "  make docker-quickstart      - Full setup and run"
	@echo ""
	@echo "MCP Configuration:"
	@echo "  make mcp-config-show        - Show MCP config"
	@echo "  make mcp-test-filesystem    - Test filesystem MCP server"
	@echo "  make mcp-test-neo4j         - Test neo4j MCP server"
