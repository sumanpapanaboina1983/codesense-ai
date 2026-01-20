"""
FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.deps import container
from src.api.v1 import chat, documents, analysis, health, openai_compat
from src.core.config import settings
from src.core.constants import API_PREFIX
from src.core.exceptions import AIAcceleratorError
from src.core.logging import get_logger, setup_logging

# Initialize logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info(
        "Starting AI Accelerator",
        app_name=settings.app_name,
        env=settings.app_env,
    )

    # Initialize service container
    try:
        container.initialize()
        logger.info("Service container initialized")
    except Exception as e:
        logger.warning(
            "Service container initialization failed (some services may not be available)",
            error=str(e)
        )

    yield

    # Shutdown
    logger.info("Shutting down AI Accelerator")

    # Cleanup active sessions
    try:
        if hasattr(container, '_session_manager'):
            await container.session_manager.cleanup_inactive_sessions(inactive_hours=0)
    except Exception as e:
        logger.warning("Failed to cleanup sessions", error=str(e))


# Create FastAPI application
app = FastAPI(
    title="AI Accelerator API",
    description="AI-powered accelerator for analyzing legacy codebases and generating BRDs, Epics, and Backlogs",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.security.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(AIAcceleratorError)
async def ai_accelerator_error_handler(
    request: Request,
    exc: AIAcceleratorError,
) -> JSONResponse:
    """Handle custom application errors."""
    logger.error(
        "Application error",
        error_code=exc.code,
        error_message=exc.message,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handle unexpected errors."""
    logger.exception(
        "Unexpected error",
        error=str(exc),
        path=request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
            }
        },
    )


# Include routers
app.include_router(health.router, prefix=API_PREFIX, tags=["Health"])
app.include_router(chat.router, prefix=API_PREFIX, tags=["Chat"])
app.include_router(documents.router, prefix=API_PREFIX, tags=["Documents"])
app.include_router(analysis.router, prefix=API_PREFIX, tags=["Analysis"])

# OpenAI-compatible API (for Open WebUI integration)
app.include_router(openai_compat.router, prefix="/v1", tags=["OpenAI Compatible"])


# Root endpoint
@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs" if settings.debug else "Disabled in production",
    }


# API info endpoint
@app.get("/api")
async def api_info() -> dict[str, Any]:
    """API information endpoint."""
    return {
        "name": "AI Accelerator API",
        "version": "1.0.0",
        "prefix": API_PREFIX,
        "endpoints": {
            "health": f"{API_PREFIX}/health",
            "chat": f"{API_PREFIX}/chat",
            "documents": f"{API_PREFIX}/documents",
            "analysis": f"{API_PREFIX}/analysis",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
    )
