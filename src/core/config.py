"""
Configuration management using Pydantic Settings.
Loads settings from environment variables and .env files.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration settings."""

    model_config = SettingsConfigDict(env_prefix="DATABASE_")

    url: str = Field(
        default="postgresql+asyncpg://user:password@localhost:5432/ai_accelerator",
        description="PostgreSQL connection URL",
    )
    pool_size: int = Field(default=10, description="Connection pool size")
    max_overflow: int = Field(default=20, description="Max overflow connections")
    echo: bool = Field(default=False, description="Echo SQL statements")


class RedisSettings(BaseSettings):
    """Redis configuration settings."""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    session_ttl: int = Field(default=86400, description="Session TTL in seconds (24 hours)")


class Neo4jSettings(BaseSettings):
    """Neo4j configuration settings."""

    model_config = SettingsConfigDict(env_prefix="NEO4J_")

    uri: str = Field(default="bolt://localhost:7687", description="Neo4j Bolt URI")
    user: str = Field(default="neo4j", description="Neo4j username")
    password: str = Field(default="password", description="Neo4j password")
    mcp_url: str = Field(default="http://localhost:3000", description="Neo4j MCP server URL")
    max_connection_pool_size: int = Field(default=50, description="Max connection pool size")


class FilesystemSettings(BaseSettings):
    """Filesystem MCP configuration settings."""

    model_config = SettingsConfigDict(env_prefix="FILESYSTEM_")

    mcp_url: str = Field(default="http://localhost:3001", description="Filesystem MCP server URL")
    codebase_root: str = Field(default="/codebase", description="Root path for codebase access")
    max_file_size_mb: int = Field(default=10, description="Maximum file size to read in MB")


class CopilotSettings(BaseSettings):
    """GitHub Copilot configuration settings."""

    model_config = SettingsConfigDict(env_prefix="COPILOT_")

    # Authentication - uses GH_TOKEN or GITHUB_TOKEN environment variables
    api_key: str = Field(
        default="",
        description="GitHub Personal Access Token (PAT) with Copilot Requests permission",
    )

    # CLI Settings
    cli_path: Optional[str] = Field(
        default=None,
        description="Path to Copilot CLI executable (defaults to 'copilot' in PATH)",
    )

    # Model settings
    model: str = Field(
        default="claude-sonnet-4-5",
        description="Model to use (e.g., claude-sonnet-4-5, gpt-4)",
    )
    max_tokens: int = Field(default=4096, description="Max tokens per response")
    temperature: float = Field(default=0.7, description="Sampling temperature")
    timeout: int = Field(default=60, description="Request timeout in seconds")

    # SDK Settings
    auto_start: bool = Field(
        default=True,
        description="Auto-start Copilot CLI server when SDK initializes",
    )


class ContextSettings(BaseSettings):
    """Context management configuration."""

    model_config = SettingsConfigDict(env_prefix="CONTEXT_")

    max_tokens: int = Field(default=8000, description="Max context window tokens")
    window_size: int = Field(default=10, description="Number of recent messages to always keep")
    importance_threshold: float = Field(
        default=0.5, description="Minimum importance score for historical messages"
    )


class VerificationSettings(BaseSettings):
    """Verification engine configuration."""

    model_config = SettingsConfigDict(env_prefix="VERIFICATION_")

    confidence_threshold: float = Field(
        default=0.7, description="Minimum confidence for verified status"
    )
    max_retries: int = Field(default=3, description="Max verification retries")
    enable_code_verification: bool = Field(
        default=True, description="Enable source code verification"
    )
    enable_graph_verification: bool = Field(
        default=True, description="Enable graph verification"
    )


class SecuritySettings(BaseSettings):
    """Security configuration."""

    model_config = SettingsConfigDict(env_prefix="SECURITY_")

    secret_key: str = Field(default="change-me-in-production", description="Secret key for signing")
    api_key_header: str = Field(default="X-API-Key", description="API key header name")
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:3001"],
        description="CORS allowed origins",
    )


class Settings(BaseSettings):
    """Main application settings aggregating all sub-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="ai-accelerator", description="Application name")
    app_env: str = Field(default="development", description="Environment (development/staging/production)")
    debug: bool = Field(default=True, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    # Skills
    skills_directory: str = Field(
        default="skills_definitions", description="Directory containing skill YAML files"
    )

    # Sub-settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    filesystem: FilesystemSettings = Field(default_factory=FilesystemSettings)
    copilot: CopilotSettings = Field(default_factory=CopilotSettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    verification: VerificationSettings = Field(default_factory=VerificationSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v.lower() not in allowed:
            raise ValueError(f"app_env must be one of {allowed}")
        return v.lower()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v.upper()

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()


# Convenience function for accessing settings
settings = get_settings()
