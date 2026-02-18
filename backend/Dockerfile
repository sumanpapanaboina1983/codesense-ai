# =============================================================================
# BRD Generator Backend Dockerfile
# =============================================================================
# Multi-stage build for optimized production image
# Includes: Python 3.11, Node.js (for Copilot CLI), MCP Servers
#
# MCP Servers installed:
# - @modelcontextprotocol/server-filesystem (filesystem access)
# - @neobarrientos/neo4j_mcpserver (Neo4j graph database)
#
# MCP Configuration:
# - Native MCP config is mounted from host or created in container
# - Config location: ~/.copilot/mcp-config.json (or /home/appuser/.copilot/)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Base image with system dependencies
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS base

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 22 (required for Copilot CLI - needs v22+)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub Copilot CLI globally
RUN npm install -g @github/copilot

# Install MCP Servers globally (available in PATH for Copilot SDK)
# These are installed globally so they can be invoked via npx or directly
# - filesystem: Read/write files in codebase
# - neo4j: Query Neo4j code graph database
# - github: Read files directly from GitHub (optional, controlled by MCP_USE_GITHUB_FOR_SOURCE)
# Note: Atlassian MCP server can be added when the package becomes available
RUN npm install -g @modelcontextprotocol/server-filesystem \
    @neobarrientos/neo4j_mcpserver \
    @modelcontextprotocol/server-github

# Verify MCP servers are installed
RUN echo "Verifying MCP server installations..." \
    && npx -y @modelcontextprotocol/server-filesystem --help || true \
    && npx -y @neobarrientos/neo4j_mcpserver --help || true \
    && npx -y @modelcontextprotocol/server-github --help || true

# Install Poetry
RUN pip install poetry==1.7.1

# Set work directory
WORKDIR /app

# -----------------------------------------------------------------------------
# Stage 2: Dependencies installation
# -----------------------------------------------------------------------------
FROM base AS dependencies

# Copy only dependency files first (for better caching)
COPY pyproject.toml poetry.lock* ./

# Configure poetry to not create virtual environment (we're in container)
RUN poetry config virtualenvs.create false

# Install dependencies (without dev dependencies for production)
RUN poetry install --no-dev --no-interaction --no-ansi

# Fix permissions on Copilot SDK binary (it needs to be executable)
RUN chmod +x /usr/local/lib/python3.11/site-packages/copilot/bin/copilot* || true

# -----------------------------------------------------------------------------
# Stage 3: Development image
# -----------------------------------------------------------------------------
FROM dependencies AS development

# Install dev dependencies
RUN poetry install --no-interaction --no-ansi

# Fix permissions on Copilot SDK binary (it needs to be executable)
RUN chmod +x /usr/local/lib/python3.11/site-packages/copilot/bin/copilot* || true

# Copy source code
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Create .copilot directory for MCP config and skills
RUN mkdir -p /home/appuser/.copilot \
    && mkdir -p /home/appuser/.github/skills \
    && chown -R appuser:appuser /home/appuser

# Copy MCP config template
COPY --chown=appuser:appuser docker/mcp-config.docker.json /home/appuser/.copilot/mcp-config.json

# Copy skills directory
COPY --chown=appuser:appuser .github/skills/ /home/appuser/.github/skills/

# Expose port for potential API server
EXPOSE 8000

USER appuser

# Set environment variables for MCP servers
ENV PATH="/usr/local/lib/node_modules/.bin:${PATH}" \
    NODE_PATH="/usr/local/lib/node_modules"

# Default command for development
CMD ["poetry", "run", "python", "-m", "brd_generator.main", "--help"]

# -----------------------------------------------------------------------------
# Stage 4: Production image
# -----------------------------------------------------------------------------
FROM base AS production

# Copy installed packages from dependencies stage
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Fix permissions on Copilot SDK binary (it needs to be executable)
RUN chmod +x /usr/local/lib/python3.11/site-packages/copilot/bin/copilot* || true

# Copy source code
COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY examples/ /app/examples/
COPY pyproject.toml /app/

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

# Create .copilot directory for native MCP configuration
RUN mkdir -p /home/appuser/.copilot \
    && mkdir -p /home/appuser/.github/skills \
    && chown -R appuser:appuser /home/appuser

# Create data directories for repository storage (must exist with correct permissions)
RUN mkdir -p /data/repositories \
    && chown -R appuser:appuser /data

# Copy default MCP config template (will be overwritten by mount if provided)
COPY --chown=appuser:appuser docker/mcp-config.docker.json /home/appuser/.copilot/mcp-config.json

# Copy skills directory
COPY --chown=appuser:appuser .github/skills/ /home/appuser/.github/skills/

USER appuser

# Set environment variables
ENV PYTHONPATH=/app/src \
    HOME=/home/appuser \
    PATH="/usr/local/lib/node_modules/.bin:${PATH}" \
    NODE_PATH="/usr/local/lib/node_modules"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import brd_generator; print('OK')" || exit 1

# Default command
CMD ["python", "-m", "brd_generator.main", "--help"]

# -----------------------------------------------------------------------------
# Stage 5: CLI runner (for one-off commands)
# -----------------------------------------------------------------------------
FROM production AS cli

# Entry point for CLI usage
ENTRYPOINT ["python", "-m", "brd_generator.main"]
CMD ["--help"]
