"""Supported models configuration for BRD generation.

This module defines the available LLM models that can be used with GitHub Copilot SDK.
Models are categorized by provider and tier availability.
"""

from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class ModelProvider(str, Enum):
    """LLM model providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    XAI = "xai"


class CopilotTier(str, Enum):
    """GitHub Copilot subscription tiers."""
    FREE = "free"
    PRO = "pro"
    PRO_PLUS = "pro+"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class ModelInfo(BaseModel):
    """Information about a supported model."""
    id: str = Field(..., description="Model identifier used in API calls")
    name: str = Field(..., description="Human-readable model name")
    provider: ModelProvider = Field(..., description="Model provider")
    description: str = Field(..., description="Brief description of model capabilities")
    min_tier: CopilotTier = Field(CopilotTier.FREE, description="Minimum Copilot tier required")
    is_recommended: bool = Field(False, description="Whether this is a recommended model")
    is_default: bool = Field(False, description="Whether this is the default model")
    context_window: Optional[int] = Field(None, description="Context window size in tokens")
    strengths: list[str] = Field(default_factory=list, description="Model strengths")
    status: str = Field("ga", description="Model status: ga, preview, deprecated")


# Supported models configuration
SUPPORTED_MODELS: list[ModelInfo] = [
    # OpenAI Models
    ModelInfo(
        id="gpt-4.1",
        name="GPT-4.1",
        provider=ModelProvider.OPENAI,
        description="Fast, efficient model good for most tasks",
        min_tier=CopilotTier.FREE,
        is_default=True,
        context_window=128000,
        strengths=["Fast responses", "Cost efficient", "Good for general tasks"],
        status="ga",
    ),
    ModelInfo(
        id="gpt-5-mini",
        name="GPT-5 Mini",
        provider=ModelProvider.OPENAI,
        description="Compact GPT-5 variant, fast and efficient",
        min_tier=CopilotTier.FREE,
        context_window=128000,
        strengths=["Very fast", "Cost efficient", "Good reasoning"],
        status="ga",
    ),
    ModelInfo(
        id="gpt-5.1",
        name="GPT-5.1",
        provider=ModelProvider.OPENAI,
        description="Latest GPT-5 series with improved reasoning",
        min_tier=CopilotTier.PRO,
        context_window=200000,
        strengths=["Strong reasoning", "Code generation", "Long context"],
        status="ga",
    ),
    ModelInfo(
        id="gpt-5.2",
        name="GPT-5.2",
        provider=ModelProvider.OPENAI,
        description="Most capable GPT model with advanced reasoning",
        min_tier=CopilotTier.PRO,
        context_window=200000,
        strengths=["Best reasoning", "Complex tasks", "Multimodal"],
        status="ga",
    ),
    ModelInfo(
        id="gpt-5.1-codex",
        name="GPT-5.1 Codex",
        provider=ModelProvider.OPENAI,
        description="Optimized for code generation and analysis",
        min_tier=CopilotTier.PRO,
        context_window=200000,
        strengths=["Code optimization", "Technical accuracy", "Agentic coding"],
        status="ga",
    ),
    ModelInfo(
        id="gpt-5.1-codex-max",
        name="GPT-5.1 Codex Max",
        provider=ModelProvider.OPENAI,
        description="Maximum capability Codex for complex code tasks",
        min_tier=CopilotTier.BUSINESS,
        context_window=200000,
        strengths=["Complex refactoring", "Architecture design", "Multi-file edits"],
        status="ga",
    ),

    # Anthropic Models
    ModelInfo(
        id="claude-haiku-4.5",
        name="Claude Haiku 4.5",
        provider=ModelProvider.ANTHROPIC,
        description="Fast Claude model, good for quick tasks",
        min_tier=CopilotTier.FREE,
        context_window=200000,
        strengths=["Very fast", "Concise responses", "Good for simple tasks"],
        status="ga",
    ),
    ModelInfo(
        id="claude-sonnet-4",
        name="Claude Sonnet 4",
        provider=ModelProvider.ANTHROPIC,
        description="Balanced Claude model for most tasks",
        min_tier=CopilotTier.PRO,
        context_window=200000,
        strengths=["Balanced performance", "Good reasoning", "Reliable"],
        status="ga",
    ),
    ModelInfo(
        id="claude-sonnet-4.5",
        name="Claude Sonnet 4.5",
        provider=ModelProvider.ANTHROPIC,
        description="Latest Sonnet with improved capabilities",
        min_tier=CopilotTier.PRO,
        is_recommended=True,
        context_window=200000,
        strengths=["Strong reasoning", "Excellent writing", "Code understanding"],
        status="ga",
    ),
    ModelInfo(
        id="claude-opus-4.5",
        name="Claude Opus 4.5",
        provider=ModelProvider.ANTHROPIC,
        description="Most capable Claude model for complex tasks",
        min_tier=CopilotTier.PRO_PLUS,
        context_window=200000,
        strengths=["Best reasoning", "Complex analysis", "Nuanced understanding"],
        status="ga",
    ),
    ModelInfo(
        id="claude-opus-4.6",
        name="Claude Opus 4.6",
        provider=ModelProvider.ANTHROPIC,
        description="Latest Opus with cutting-edge capabilities",
        min_tier=CopilotTier.BUSINESS,
        context_window=200000,
        strengths=["State-of-art reasoning", "Research quality", "Complex tasks"],
        status="ga",
    ),

    # Google Models
    ModelInfo(
        id="gemini-2.5-pro",
        name="Gemini 2.5 Pro",
        provider=ModelProvider.GOOGLE,
        description="Google's production model with strong multimodal",
        min_tier=CopilotTier.PRO,
        context_window=1000000,
        strengths=["Very long context", "Multimodal", "Fast"],
        status="ga",
    ),
    ModelInfo(
        id="gemini-3-pro-preview",
        name="Gemini 3 Pro",
        provider=ModelProvider.GOOGLE,
        description="Latest Gemini with improved reasoning",
        min_tier=CopilotTier.PRO,
        context_window=1000000,
        strengths=["Massive context", "Strong reasoning", "Multimodal"],
        status="preview",
    ),
    ModelInfo(
        id="gemini-3-flash",
        name="Gemini 3 Flash",
        provider=ModelProvider.GOOGLE,
        description="Fast Gemini variant for quick responses",
        min_tier=CopilotTier.PRO,
        context_window=1000000,
        strengths=["Very fast", "Long context", "Efficient"],
        status="preview",
    ),

    # xAI Models
    ModelInfo(
        id="grok-code-fast-1",
        name="Grok Code Fast 1",
        provider=ModelProvider.XAI,
        description="xAI's fast coding model",
        min_tier=CopilotTier.PRO,
        context_window=128000,
        strengths=["Fast code generation", "Unique perspective", "Direct responses"],
        status="ga",
    ),
]


def get_default_model() -> ModelInfo:
    """Get the default model."""
    for model in SUPPORTED_MODELS:
        if model.is_default:
            return model
    return SUPPORTED_MODELS[0]


def get_model_by_id(model_id: str) -> Optional[ModelInfo]:
    """Get model info by ID."""
    for model in SUPPORTED_MODELS:
        if model.id == model_id:
            return model
    return None


def get_models_for_tier(tier: CopilotTier) -> list[ModelInfo]:
    """Get all models available for a given tier."""
    tier_order = [CopilotTier.FREE, CopilotTier.PRO, CopilotTier.PRO_PLUS,
                  CopilotTier.BUSINESS, CopilotTier.ENTERPRISE]
    tier_index = tier_order.index(tier)

    return [
        model for model in SUPPORTED_MODELS
        if tier_order.index(model.min_tier) <= tier_index
    ]


def get_recommended_models() -> list[ModelInfo]:
    """Get recommended models."""
    return [model for model in SUPPORTED_MODELS if model.is_recommended]
