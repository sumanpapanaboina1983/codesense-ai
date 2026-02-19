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

    # Enhanced fields for better documentation
    file_path: Optional[str] = None
    table_name: Optional[str] = None  # Mapped database table
    validations: dict[str, list[str]] = Field(default_factory=dict)  # field -> [validation annotations]
    primary_key: Optional[str] = None
    foreign_keys: list[dict[str, str]] = Field(default_factory=list)  # [{field, references_table, references_column}]

    def to_markdown(self) -> str:
        """Generate markdown for this data model."""
        lines = []
        lines.append(f"#### Entity: `{self.name}`")
        if self.file_path:
            lines.append(f"**File:** `{self.file_path}`")
        if self.table_name:
            lines.append(f"**Database Table:** `{self.table_name}`")
        lines.append("")

        if self.fields:
            lines.append("| Field | Type | Validations |")
            lines.append("|-------|------|-------------|")
            for field_name, field_type in self.fields.items():
                validations = ", ".join(self.validations.get(field_name, [])) or "-"
                pk_marker = " (PK)" if field_name == self.primary_key else ""
                lines.append(f"| `{field_name}`{pk_marker} | {field_type} | {validations} |")
            lines.append("")

        if self.relationships:
            lines.append("**Relationships:**")
            for rel in self.relationships:
                lines.append(f"- {rel}")
            lines.append("")

        return "\n".join(lines)


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
    business_logic: Optional[Any] = Field(
        default=None,
        description="Extracted business rules from codebase (validation constraints, guards, etc.)"
    )
    # Feature flow data for auto-generating BRD Sections 7 & 9
    feature_flows: Optional[list[Any]] = Field(
        default=None,
        description="End-to-end feature flows from UI to database for Section 7 (Technical Architecture) and Section 9 (Implementation Mapping)"
    )
    implementation_mapping: Optional[str] = Field(
        default=None,
        description="Pre-generated markdown table for BRD Section 9"
    )
    technical_architecture: Optional[str] = Field(
        default=None,
        description="Pre-generated markdown for BRD Section 7"
    )

    @property
    def estimated_tokens(self) -> int:
        """Rough token count estimation."""
        # Simple heuristic: ~4 chars per token
        total_chars = len(self.model_dump_json())
        return total_chars // 4


# Import BusinessLogicContext for type annotation after class definition to avoid circular imports
def _rebuild_models():
    """Rebuild models after all imports are resolved."""
    try:
        from .business_logic import BusinessLogicContext
        AggregatedContext.model_rebuild()
    except ImportError:
        pass  # BusinessLogicContext not available yet

_rebuild_models()
