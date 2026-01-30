# BRD Generator Backend

AI-powered Business Requirements Document generation using code graph analysis.

## Overview

This backend generates Business Requirements Documents (BRDs), Epics, and Backlogs by:
1. Querying Neo4j for code structure/relationships
2. Reading relevant source files via filesystem
3. Aggregating context intelligently
4. Using GitHub Copilot SDK to synthesize requirements documents

## Prerequisites

- Python 3.11+
- Neo4j 5.x (running locally or remote)
- GitHub Copilot subscription
- GitHub Copilot CLI installed

## Quick Start

### Option 1: Docker (Recommended)

```bash
cd backend

# Set your GitHub token for Copilot
export GH_TOKEN=ghp_your_token_here

# Set path to codebase you want to analyze
export CODEBASE_PATH=/path/to/your/codebase

# Quick start - builds and starts everything
make docker-quickstart

# Generate a BRD
make docker-generate FEATURE="Add user authentication with OAuth2"

# Or run interactively
make docker-shell
```

### Option 2: Local Development

```bash
# Install dependencies
poetry install

# Copy environment template
cp .env.example .env
# Edit .env with your credentials

# Run example
poetry run brd-generator --feature "Add OAuth2 authentication to user service"
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      BRD Generator                          │
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │  BRDRequest │───>│ContextAggr. │───>│ LLMSynthesizer│  │
│  └─────────────┘    └──────────────┘    └───────────────┘  │
│                            │                     │          │
│                     ┌──────┴──────┐              │          │
│                     ▼             ▼              ▼          │
│              ┌───────────┐ ┌───────────┐  ┌───────────┐    │
│              │Neo4j MCP  │ │Filesystem │  │Copilot SDK│    │
│              │Client     │ │MCP Client │  │Session    │    │
│              └───────────┘ └───────────┘  └───────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## CLI Usage

```bash
# Basic usage
poetry run brd-generator --request "Add user authentication"

# Specify scope and components
poetry run brd-generator \
  --request "Add OAuth2 authentication" \
  --scope full \
  --components auth-service user-service \
  --output ./output \
  --format markdown
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--request` | Feature description (required) | - |
| `--scope` | Analysis scope: full, component, service | full |
| `--components` | Specific components to analyze | - |
| `--output` | Output directory | ./output |
| `--format` | Output format: markdown, json, jira | markdown |

## Development

```bash
# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=brd_generator

# Format code
poetry run black .

# Lint
poetry run ruff check .

# Type check
poetry run mypy src/
```

## Project Structure

```
backend/
├── pyproject.toml              # Poetry/pip configuration
├── README.md                   # This file
├── .env.example                # Environment variables template
│
├── src/
│   └── brd_generator/
│       ├── __init__.py
│       ├── main.py             # Entry point
│       │
│       ├── core/
│       │   ├── generator.py    # BRDGenerator orchestrator
│       │   ├── aggregator.py   # ContextAggregator
│       │   └── synthesizer.py  # LLMSynthesizer
│       │
│       ├── mcp_clients/
│       │   ├── base.py         # Base MCP client
│       │   ├── neo4j_client.py
│       │   └── filesystem_client.py
│       │
│       ├── models/
│       │   ├── request.py      # BRDRequest model
│       │   ├── context.py      # Context models
│       │   └── output.py       # BRD/Epic/Backlog models
│       │
│       ├── templates/          # Jinja2 templates
│       ├── prompts/            # LLM prompts
│       └── utils/              # Utilities
│
├── tests/                      # Test suite
├── examples/                   # Example requests and outputs
└── scripts/                    # Helper scripts
```

## Output Format

The generator produces:

1. **BRD Document** (`BRD.md`) - Business Requirements Document
2. **Epics** (`epics.json`) - High-level feature groupings
3. **Backlogs** (`backlogs.json`) - User stories with acceptance criteria

## Configuration

### Neo4j Connection

The generator queries Neo4j for:
- Component dependencies
- API contracts
- Data models
- Similar existing features

### Copilot SDK

Uses GitHub Copilot SDK for:
- Context analysis
- BRD generation
- Epic/story synthesis

## Docker

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐                                        │
│  │  BRD Generator  │──────┐                                 │
│  │  (Python CLI)   │      │                                 │
│  └─────────────────┘      │                                 │
│           │               │                                 │
│           ▼               ▼                                 │
│  ┌─────────────┐  ┌─────────────────┐                      │
│  │ Neo4j MCP   │  │ Filesystem MCP  │                      │
│  │ Server      │  │ Server          │                      │
│  │ :3006       │  │ :3004           │                      │
│  └──────┬──────┘  └────────┬────────┘                      │
│         │                  │                                │
│         ▼                  ▼                                │
│  ┌─────────────┐  ┌─────────────────┐                      │
│  │   Neo4j     │  │   /codebase     │                      │
│  │   :7474     │  │   (volume)      │                      │
│  └─────────────┘  └─────────────────┘                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Docker Commands

```bash
# Build the Docker image
make docker-build

# Start all services (Neo4j, MCP servers)
make docker-up

# Generate a BRD
make docker-generate FEATURE="Add caching layer"

# Run with custom arguments
make docker-run ARGS="--feature 'Add logging' --output /app/output/brd.md"

# Interactive shell
make docker-shell

# View logs
make docker-logs

# Stop all services
make docker-down

# Clean up
make docker-clean
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GH_TOKEN` | GitHub token for Copilot | Required |
| `CODEBASE_PATH` | Path to codebase to analyze | `./codebase` |
| `COPILOT_MODEL` | Model to use | `claude-sonnet-4-5` |
| `NEO4J_PASSWORD` | Neo4j password | `password` |

### Running from Main Project

The BRD Generator is also available in the main `docker-compose.yml`:

```bash
cd /path/to/codesense-ai

# Start with BRD profile
docker-compose --profile brd up -d

# Run BRD generation
docker-compose run --rm brd-generator python -m brd_generator.main \
  --feature "Add user authentication"
```

## License

MIT
