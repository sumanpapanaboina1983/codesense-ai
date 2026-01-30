# =============================================================================
# CodeGraph Dockerfile
# Multi-stage build for the codebase analysis tool
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies and compile TypeScript
# -----------------------------------------------------------------------------
FROM node:20-slim AS builder

WORKDIR /app

# Install build dependencies for native modules (tree-sitter)
RUN apt-get update && apt-get install -y \
    python3 \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy package files first for better caching
COPY package.json package-lock.json* ./

# Install all dependencies (including devDependencies for building)
# Use --legacy-peer-deps to resolve tree-sitter peer dependency conflicts
RUN npm ci --legacy-peer-deps

# Copy source code
COPY tsconfig.json ./
COPY src/ ./src/

# Build TypeScript
RUN npm run build

# Prune dev dependencies for production
RUN npm prune --omit=dev --legacy-peer-deps

# -----------------------------------------------------------------------------
# Stage 2: Production - Minimal runtime image
# -----------------------------------------------------------------------------
FROM node:20-slim AS production

WORKDIR /app

# Install runtime dependencies for Python AST parsing and native modules
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r codegraph && useradd -r -g codegraph codegraph

# Copy built artifacts from builder
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package.json ./

# Create directory for analysis data
RUN mkdir -p /app/analysis-data && chown -R codegraph:codegraph /app

# Switch to non-root user
USER codegraph

# Environment variables (can be overridden at runtime)
ENV NODE_ENV=production
ENV PORT=3001
ENV NEO4J_URL=bolt://neo4j:7687
ENV NEO4J_USER=neo4j
ENV NEO4J_PASSWORD=password
ENV NEO4J_DATABASE=codegraph
ENV LOG_LEVEL=info
ENV PYTHON_EXECUTABLE=python3

# Expose API port
EXPOSE 3001

# Health check
HEALTHCHECK --interval=10s --timeout=10s --start-period=30s --retries=5 \
    CMD node -e "fetch('http://localhost:3001/health').then(r => r.ok ? process.exit(0) : process.exit(1)).catch(() => process.exit(1))"

# Default command: start API server
CMD ["node", "dist/index.js", "serve", "--port", "3001"]

# -----------------------------------------------------------------------------
# Stage 3: Development - For local development with hot reload
# -----------------------------------------------------------------------------
FROM node:20-slim AS development

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy package files
COPY package.json package-lock.json* ./

# Install all dependencies
RUN npm ci --legacy-peer-deps

# Copy source
COPY . .

# Environment variables
ENV NODE_ENV=development
ENV PORT=3001

# Expose API port
EXPOSE 3001

# Development command with ts-node
CMD ["npm", "run", "dev:serve"]
