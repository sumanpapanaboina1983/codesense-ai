"""Context models for aggregated information."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class SchemaInfo(BaseModel):
    """Schema information from Neo4j code graph."""

    node_labels: list[str] = Field(default_factory=list)
    component_labels: list[str] = Field(default_factory=list)
    relationship_types: list[str] = Field(default_factory=list)
    dependency_relationships: list[str] = Field(default_factory=list)


class ComponentInfo(BaseModel):
    """Information about a code component."""

    name: str
    type: str  # 'service', 'module', 'class', etc.
    path: str
    description: str = ""
    dependencies: list[str] = Field(default_factory=list)
    dependents: list[str] = Field(default_factory=list)


class APIContract(BaseModel):
    """API contract definition."""

    endpoint: str
    method: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    response_schema: Optional[dict[str, Any]] = None
    service: str


class DataModel(BaseModel):
    """Data model/entity definition."""

    name: str
    fields: dict[str, str] = Field(default_factory=dict)
    relationships: list[str] = Field(default_factory=list)


class FileContext(BaseModel):
    """Context from a source file."""

    path: str
    content: str
    summary: Optional[str] = None
    relevance: str = ""  # Why this file is relevant
    relevance_score: float = 0.0


class ArchitectureContext(BaseModel):
    """Aggregated architecture context."""

    components: list[ComponentInfo] = Field(default_factory=list)
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    api_contracts: list[APIContract] = Field(default_factory=list)
    data_models: list[DataModel] = Field(default_factory=list)


class ImplementationContext(BaseModel):
    """Implementation details context."""

    key_files: list[FileContext] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    configs: dict[str, Any] = Field(default_factory=dict)


class AggregatedContext(BaseModel):
    """Complete aggregated context for BRD generation."""

    request: str
    architecture: ArchitectureContext
    implementation: ImplementationContext
    similar_features: list[str] = Field(default_factory=list)
    test_coverage: Optional[dict[str, float]] = None
    schema: Optional[SchemaInfo] = None  # Discovered schema from Neo4j

    @property
    def estimated_tokens(self) -> int:
        """Rough token count estimation."""
        # Simple heuristic: ~4 chars per token
        total_chars = len(self.model_dump_json())
        return total_chars // 4
