"""Request models for BRD generation."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class BRDRequest(BaseModel):
    """User request for BRD generation."""

    feature_description: str = Field(
        ...,
        description="Natural language description of the feature",
        min_length=10,
    )

    scope: str = Field(
        default="full",
        description="Scope of analysis: 'full', 'component', or 'service'",
    )

    affected_components: Optional[list[str]] = Field(
        default=None,
        description="Specific components to analyze (if known)",
    )

    include_similar_features: bool = Field(
        default=True,
        description="Search for similar existing features",
    )

    output_format: str = Field(
        default="markdown",
        description="Output format: 'markdown', 'json', or 'jira'",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "feature_description": "Add OAuth2 authentication to user service",
                    "scope": "full",
                    "affected_components": ["auth-service", "user-service"],
                    "include_similar_features": True,
                    "output_format": "markdown",
                }
            ]
        }
    }
