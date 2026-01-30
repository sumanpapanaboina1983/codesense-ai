"""FastAPI Application for BRD Generator."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routes import router
from .repository_routes import router as repository_router
from ..core.generator import BRDGenerator
from ..database.config import init_db, close_db
from ..services.repository_service import RepositoryService
from ..utils.logger import get_logger, setup_logging

logger = get_logger(__name__)

# API metadata
API_TITLE = "BRD Generator API"
API_DESCRIPTION = """
# BRD Generator API

AI-powered Business Requirements Document generation using MCP servers and LLM synthesis.

## Four-Phase Workflow

This API implements a four-phase workflow for BRD generation with user review at each stage:

### Phase 1: Generate BRD
- **Endpoint**: `POST /api/v1/brd/generate`
- **Input**: Feature description + optional template configuration
- **Output**: Business Requirements Document
- **User Action**: Review and approve BRD

### Phase 2: Generate Epics
- **Endpoint**: `POST /api/v1/epics/generate`
- **Input**: Approved BRD from Phase 1
- **Output**: Epics (high-level work packages)
- **User Action**: Review and approve Epics

### Phase 3: Generate Backlogs
- **Endpoint**: `POST /api/v1/backlogs/generate`
- **Input**: Approved Epics + BRD for context
- **Output**: User Stories with acceptance criteria
- **User Action**: Review and approve Stories

### Phase 4: Create JIRA Issues
- **Endpoint**: `POST /api/v1/jira/create`
- **Input**: Approved Epics and Stories
- **Output**: Created JIRA issues with keys
- **Requires**: Atlassian MCP server configured

## MCP Servers Used

- **Filesystem MCP**: Read source files from codebase
- **Neo4j MCP**: Query code graph for dependencies
- **Atlassian MCP**: Create issues in JIRA (Phase 4 only)

## Repository Management

Before generating BRDs, onboard repositories:

1. **POST /api/v1/repositories** - Onboard a GitHub/GitLab repository
2. **GET /api/v1/repositories/{id}** - Check onboarding status
3. Once status is READY, generate BRDs with repository context
"""

API_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    logger.info("Starting BRD Generator API...")
    setup_logging("INFO")

    # Initialize database
    logger.info("Initializing database...")
    await init_db()

    # Initialize generator
    from .routes import _generator
    import brd_generator.api.routes as routes_module
    import brd_generator.api.repository_routes as repo_routes_module

    generator = BRDGenerator()
    await generator.initialize()
    routes_module._generator = generator

    # Initialize repository service
    repository_service = RepositoryService()
    repo_routes_module._repository_service = repository_service

    logger.info("BRD Generator API started successfully")

    yield

    # Shutdown
    logger.info("Shutting down BRD Generator API...")
    if routes_module._generator:
        await routes_module._generator.cleanup()
    if repo_routes_module._repository_service:
        await repo_routes_module._repository_service.close()

    # Close database connections
    await close_db()
    logger.info("BRD Generator API shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=API_TITLE,
        description=API_DESCRIPTION,
        version=API_VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routes
    app.include_router(router, prefix="/api/v1")
    app.include_router(repository_router, prefix="/api/v1")

    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root():
        """Root endpoint with API info."""
        return {
            "name": API_TITLE,
            "version": API_VERSION,
            "docs": "/docs",
            "openapi": "/openapi.json",
            "endpoints": {
                "health": "/api/v1/health",
                "repositories": "/api/v1/repositories",
                "generate_brd": "/api/v1/brd/generate",
                "generate_epics": "/api/v1/epics/generate",
                "generate_backlogs": "/api/v1/backlogs/generate",
                "create_jira": "/api/v1/jira/create",
            },
        }

    # Exception handlers
    @app.exception_handler(Exception)
    async def generic_exception_handler(request, exc):
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Internal server error",
                "detail": str(exc),
            },
        )

    return app


# Create app instance
app = create_app()


def main():
    """Run the API server."""
    import uvicorn

    uvicorn.run(
        "brd_generator.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
