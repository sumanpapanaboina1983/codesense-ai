# AI Accelerator - CodeSense AI

An AI-powered accelerator for analyzing legacy codebases and automatically generating Business Requirements Documents (BRDs), Epics, and Backlog items.

## Overview

This system uses:
- **Neo4j Graph Database** - For storing and querying code structure
- **GitHub Copilot** - With custom skills for intelligent document generation
- **FastAPI** - Backend REST API with WebSocket support
- **Zero Hallucination Verification** - All generated content is verified against actual code

## Features

- Analyze legacy codebases and extract component relationships
- Generate verified BRDs grounded in actual code
- Decompose BRDs into Epics with proper granularity
- Generate Backlog items with acceptance criteria
- Real-time streaming responses via WebSocket
- Export documents in Markdown, JSON, or HTML formats

---

## Prerequisites

- Python 3.11 or higher
- Docker and Docker Compose
- GitHub Copilot API access

```bash
# Verify prerequisites
python --version   # Should be 3.11+
docker --version   # Should be 20.0+
docker-compose --version
```

---

## Installation

### 1. Clone and Setup

```bash
cd /Users/suman.papanaboina/PycharmProjects/codesense-ai

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# OR
.\venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env
```

Edit `.env` with your settings:

```env
# ===========================================
# Application Configuration
# ===========================================
APP_NAME=AI Accelerator
APP_ENV=development
DEBUG=true
HOST=0.0.0.0
PORT=8000

# ===========================================
# IMPORTANT: Your Codebase Path
# ===========================================
# Set this to the root directory of the legacy
# codebase you want to analyze
CODEBASE_PATH=/path/to/your/legacy/codebase

# ===========================================
# GitHub Copilot Configuration
# ===========================================
COPILOT_API_KEY=your-copilot-api-key-here
COPILOT_MODEL=gpt-4

# ===========================================
# Neo4j Configuration (Code Graph Database)
# ===========================================
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# ===========================================
# Redis Configuration (Caching)
# ===========================================
REDIS_URL=redis://localhost:6379/0

# ===========================================
# PostgreSQL Configuration (Optional)
# ===========================================
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_accelerator
```

### 3. Start Infrastructure Services

```bash
# Start Neo4j, Redis, and PostgreSQL
docker-compose up -d

# Verify services are running
docker-compose ps

# Check logs if needed
docker-compose logs -f
```

Expected output:
```
NAME                    STATUS
codesense-neo4j         running (healthy)
codesense-redis         running (healthy)
codesense-postgres      running (healthy)
```

### 4. Run the Application

```bash
# Option 1: Using Python
python -m src.main

# Option 2: Using Make
make run

# Option 3: Using uvicorn with auto-reload
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

The application will start at: **http://localhost:8000**

---

## Accessing the Application

| URL | Description |
|-----|-------------|
| http://localhost:8000 | Root endpoint |
| http://localhost:8000/docs | Swagger API documentation |
| http://localhost:8000/redoc | ReDoc API documentation |
| http://localhost:8000/api/v1/health | Health check |

---

## Configuring Your Codebase

There are three ways to specify which codebase to analyze:

### Option 1: Environment Variable (Recommended for Default)

Set in `.env` file:
```env
CODEBASE_PATH=/Users/yourname/projects/legacy-application
```

### Option 2: Per-Request Parameter

Specify `codebase_path` in each API request:
```json
{
  "codebase_path": "/path/to/specific/codebase"
}
```

### Option 3: Docker Volume Mount

When running with Docker, mount your codebase:
```yaml
# In docker-compose.yml
services:
  api:
    volumes:
      - /path/to/your/codebase:/codebase:ro
```

---

## API Usage Guide

### Step 1: Create a Session

```bash
curl -X POST http://localhost:8000/api/v1/chat/session \
  -H "Content-Type: application/json" \
  -d '{
    "codebase_path": "/path/to/your/codebase"
  }'
```

**Response:**
```json
{
  "session_id": "sess_a1b2c3d4e5f6",
  "status": "active",
  "created_at": "2024-01-15T10:00:00.000Z"
}
```

Save the `session_id` for subsequent requests.

### Step 2: Generate a BRD

```bash
curl -X POST http://localhost:8000/api/v1/documents/generate/brd \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess_a1b2c3d4e5f6",
    "component_name": "UserAuthentication",
    "codebase_path": "/path/to/your/codebase"
  }'
```

**Response:**
```json
{
  "workflow_id": "wf_brd_abc123",
  "workflow_type": "brd",
  "status": "completed",
  "document_id": "doc_xyz789",
  "duration_seconds": 45.2
}
```

### Step 3: Generate Epics from BRD

```bash
curl -X POST http://localhost:8000/api/v1/documents/generate/epics \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess_a1b2c3d4e5f6",
    "brd_document_id": "doc_xyz789",
    "codebase_path": "/path/to/your/codebase"
  }'
```

### Step 4: Generate Backlog Items from Epic

```bash
curl -X POST http://localhost:8000/api/v1/documents/generate/backlog \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess_a1b2c3d4e5f6",
    "epic_id": "doc_epic456",
    "codebase_path": "/path/to/your/codebase"
  }'
```

### Retrieve a Document

```bash
curl http://localhost:8000/api/v1/documents/doc_xyz789
```

### Download Document

```bash
# Download as Markdown
curl -o document.md "http://localhost:8000/api/v1/documents/doc_xyz789/download?format=markdown"

# Download as JSON
curl -o document.json "http://localhost:8000/api/v1/documents/doc_xyz789/download?format=json"

# Download as HTML
curl -o document.html "http://localhost:8000/api/v1/documents/doc_xyz789/download?format=html"
```

### List All Documents

```bash
# List all documents
curl http://localhost:8000/api/v1/documents

# Filter by session
curl "http://localhost:8000/api/v1/documents?session_id=sess_a1b2c3d4e5f6"

# Filter by type
curl "http://localhost:8000/api/v1/documents?doc_type=brd"
```

### Chat Interface

```bash
curl -X POST http://localhost:8000/api/v1/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Analyze the payment processing module and identify its main components",
    "context": {
      "codebase_path": "/path/to/your/codebase"
    }
  }'
```

---

## Analysis Endpoints

### Analyze Codebase

```bash
curl -X POST http://localhost:8000/api/v1/analysis/codebase \
  -H "Content-Type: application/json" \
  -d '{
    "component_name": "PaymentService",
    "codebase_path": "/path/to/your/codebase",
    "analysis_type": "standard"
  }'
```

Analysis types:
- `quick` - Fast overview of codebase structure
- `standard` - Detailed analysis with component relationships
- `deep` - Comprehensive analysis with architecture patterns

### Get Dependency Graph

```bash
curl "http://localhost:8000/api/v1/analysis/dependencies?codebase_path=/path/to/codebase&max_depth=3"
```

### Search Codebase

```bash
curl -X POST http://localhost:8000/api/v1/analysis/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "authentication logic",
    "search_type": "semantic",
    "codebase_path": "/path/to/your/codebase"
  }'
```

---

## WebSocket Streaming

For real-time streaming responses, connect via WebSocket:

```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/ws/chat/sess_a1b2c3d4e5f6');

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'chat',
    data: {
      message: 'Generate a BRD for the user service',
      context: { codebase_path: '/path/to/codebase' }
    }
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Received:', message);
};
```

---

## Project Structure

```
codesense-ai/
├── src/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── health.py       # Health check endpoints
│   │   │   ├── chat.py         # Chat/conversation endpoints
│   │   │   ├── documents.py    # Document management endpoints
│   │   │   ├── analysis.py     # Codebase analysis endpoints
│   │   │   └── websocket.py    # WebSocket handler
│   │   └── deps.py             # Dependency injection
│   ├── agentic/
│   │   ├── reasoning_engine.py # Multi-step reasoning
│   │   ├── verification_engine.py # Zero-hallucination verification
│   │   └── context_manager.py  # Context window management
│   ├── copilot/
│   │   ├── sdk_client.py       # Copilot API client
│   │   ├── conversation_handler.py
│   │   └── skill_injector.py   # Skill injection
│   ├── core/
│   │   ├── config.py           # Application configuration
│   │   ├── constants.py        # Enums and constants
│   │   ├── exceptions.py       # Custom exceptions
│   │   └── logging.py          # Structured logging
│   ├── domain/
│   │   ├── session.py          # Session model
│   │   └── document.py         # Document models
│   ├── mcp/
│   │   ├── neo4j_client.py     # Neo4j MCP client
│   │   ├── filesystem_client.py # Filesystem MCP client
│   │   └── tool_registry.py    # Tool registration
│   ├── orchestration/
│   │   ├── workflow_engine.py  # Workflow orchestration
│   │   ├── state_machine.py    # State management
│   │   └── workflows/
│   │       ├── brd_workflow.py
│   │       ├── epic_workflow.py
│   │       └── backlog_workflow.py
│   ├── repositories/
│   │   ├── session_repo.py
│   │   ├── document_repo.py
│   │   └── cache_repo.py
│   ├── services/
│   │   ├── document_service.py
│   │   ├── analysis_service.py
│   │   └── session_manager.py
│   ├── skills/
│   │   ├── base.py
│   │   ├── loader.py
│   │   └── registry.py
│   └── main.py                 # Application entry point
├── skills_definitions/         # YAML skill definitions
├── tests/
├── deploy/
│   └── docker/
│       └── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
├── Makefile
└── README.md
```

---

## Make Commands

```bash
make install      # Install dependencies
make run          # Run the application
make test         # Run tests
make lint         # Run linting
make format       # Format code
make docker-build # Build Docker image
make docker-up    # Start all services with Docker
make docker-down  # Stop all services
make clean        # Clean build artifacts
```

---

## Troubleshooting

### Services won't start

```bash
# Check Docker logs
docker-compose logs neo4j
docker-compose logs redis

# Restart services
docker-compose down
docker-compose up -d
```

### Connection refused errors

Ensure all services are healthy:
```bash
docker-compose ps
```

Wait for Neo4j to fully initialize (can take 30-60 seconds on first start).

### API returns 500 errors

Check application logs:
```bash
# If running directly
python -m src.main

# Check for missing environment variables
cat .env
```

### Neo4j authentication failed

Reset Neo4j password:
```bash
docker-compose down -v  # Warning: This deletes data
docker-compose up -d
```

---

## Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_NAME` | Application name | AI Accelerator |
| `APP_ENV` | Environment (development/production) | development |
| `DEBUG` | Enable debug mode | true |
| `HOST` | Server host | 0.0.0.0 |
| `PORT` | Server port | 8000 |
| `CODEBASE_PATH` | Default codebase path | /codebase |
| `COPILOT_API_KEY` | GitHub Copilot API key | (required) |
| `COPILOT_MODEL` | Copilot model to use | gpt-4 |
| `NEO4J_URI` | Neo4j connection URI | bolt://localhost:7687 |
| `NEO4J_USER` | Neo4j username | neo4j |
| `NEO4J_PASSWORD` | Neo4j password | password |
| `REDIS_URL` | Redis connection URL | redis://localhost:6379/0 |
| `DATABASE_URL` | PostgreSQL connection URL | (optional) |

---

## License

MIT License - See LICENSE file for details.

---

## Support

For issues and feature requests, please open an issue on the repository.
