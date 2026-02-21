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


# ============================================================================
# Enhanced Models for BRD Generation (Phase 11)
# ============================================================================

class CodeSnippetInfo(BaseModel):
    """Code snippet from a method or function."""

    method_name: str
    class_name: Optional[str] = None
    file_path: str
    start_line: int
    end_line: int
    snippet: str  # The actual code (5-15 lines)
    language: str = "Java"

    def to_markdown(self) -> str:
        """Format snippet for inclusion in BRD."""
        location = f"{self.file_path}:{self.start_line}-{self.end_line}"
        header = f"**{self.class_name}.{self.method_name}**" if self.class_name else f"**{self.method_name}**"
        return f"{header} (`{location}`)\n```{self.language.lower()}\n{self.snippet}\n```"


class SecurityRuleInfo(BaseModel):
    """Security rule/annotation from code."""

    annotation_type: str  # 'PreAuthorize', 'Secured', 'RolesAllowed', etc.
    annotation_text: str  # Full annotation text
    expression: Optional[str] = None  # SpEL expression for @PreAuthorize
    roles: list[str] = Field(default_factory=list)  # Required roles
    target_name: str  # Method or class name
    target_type: str  # 'method' or 'class'
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    description: Optional[str] = None  # Human-readable description

    def to_markdown(self) -> str:
        """Format security rule for BRD."""
        roles_text = ", ".join(self.roles) if self.roles else "N/A"
        expr_text = f" (`{self.expression}`)" if self.expression else ""
        location = f" at `{self.file_path}:{self.line_number}`" if self.file_path and self.line_number else ""
        return f"- **{self.annotation_type}**{expr_text} on `{self.target_name}` - Roles: {roles_text}{location}"


class ErrorMessageInfo(BaseModel):
    """Error message from code or resource bundles."""

    message_key: Optional[str] = None  # i18n key
    message_text: str  # Actual message text
    source_type: str = "inline"  # 'inline' (from throw) or 'resource_bundle' (.properties)
    source_file: Optional[str] = None
    line_number: Optional[int] = None
    locale: Optional[str] = None
    parameters: list[str] = Field(default_factory=list)  # Placeholders like {0}, {1}
    context_method: Optional[str] = None  # Method where this error occurs

    def to_markdown(self) -> str:
        """Format error message for BRD."""
        key_text = f"`{self.message_key}`: " if self.message_key else ""
        params_text = f" (params: {', '.join(self.parameters)})" if self.parameters else ""
        context = f" in `{self.context_method}`" if self.context_method else ""
        return f"- {key_text}*\"{self.message_text}\"*{params_text}{context}"


class TransitionConditionInfo(BaseModel):
    """Parsed transition condition from WebFlow."""

    flow_name: str
    transition_name: str
    trigger_event: str
    target_state: str
    condition_expression: str
    operator: Optional[str] = None  # 'equals', 'notEquals', 'and', 'or', etc.
    left_operand: Optional[str] = None
    right_operand: Optional[str] = None
    variables: list[str] = Field(default_factory=list)
    method_calls: list[str] = Field(default_factory=list)
    is_spel: bool = False
    description: Optional[str] = None  # Human-readable description

    def to_markdown(self) -> str:
        """Format condition for BRD."""
        desc = self.description or self.condition_expression
        return f"- **{self.transition_name}** (on `{self.trigger_event}`): {desc} → `{self.target_state}`"


class FormFieldDetailInfo(BaseModel):
    """Enhanced form field with label and validation details."""

    field_name: str
    field_type: str
    label: Optional[str] = None
    label_key: Optional[str] = None  # i18n key
    required: bool = False
    placeholder: Optional[str] = None
    help_text: Optional[str] = None
    validation_rules: Optional[dict[str, Any]] = None  # pattern, min, max, etc.
    error_path: Optional[str] = None  # <form:errors path="...">
    css_error_class: Optional[str] = None
    form_name: Optional[str] = None
    jsp_name: Optional[str] = None

    def to_markdown(self) -> str:
        """Format form field for BRD."""
        label_text = self.label or self.label_key or self.field_name
        req_marker = " (Required)" if self.required else ""
        validation_text = ""
        if self.validation_rules:
            rules = [f"{k}={v}" for k, v in self.validation_rules.items() if v]
            if rules:
                validation_text = f" | Validation: {', '.join(rules)}"
        return f"| `{self.field_name}` | {label_text}{req_marker} | {self.field_type}{validation_text} |"


class EnhancedMethodContext(BaseModel):
    """Enhanced method context with code snippets, errors, and security."""

    method_name: str
    class_name: Optional[str] = None
    signature: Optional[str] = None
    file_path: str
    start_line: int
    end_line: int
    code_snippet: Optional[str] = None
    error_messages: list[ErrorMessageInfo] = Field(default_factory=list)
    security_rules: list[SecurityRuleInfo] = Field(default_factory=list)
    invoked_methods: list[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        """Format method context for BRD."""
        lines = []
        header = f"### `{self.class_name}.{self.method_name}`" if self.class_name else f"### `{self.method_name}`"
        lines.append(header)
        lines.append(f"**Location:** `{self.file_path}:{self.start_line}-{self.end_line}`")

        if self.signature:
            lines.append(f"**Signature:** `{self.signature}`")

        if self.code_snippet:
            lines.append("\n**Implementation:**")
            lines.append(f"```java\n{self.code_snippet}\n```")

        if self.security_rules:
            lines.append("\n**Security:**")
            for rule in self.security_rules:
                lines.append(rule.to_markdown())

        if self.error_messages:
            lines.append("\n**Error Messages:**")
            for err in self.error_messages:
                lines.append(err.to_markdown())

        return "\n".join(lines)


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


class MenuItemInfo(BaseModel):
    """Information about a menu item from the application."""

    name: str
    label: str
    url: str
    flow_id: str
    view_state_id: Optional[str] = None
    menu_level: int = 0
    parent_menu: Optional[str] = None
    required_roles: list[str] = Field(default_factory=list)


class SubFeatureInfo(BaseModel):
    """Information about a sub-feature (screen) within a menu item."""

    screen_id: str
    title: str
    screen_type: str  # 'entry', 'results', 'inquiry', 'maintenance', etc.
    jsps: list[str] = Field(default_factory=list)
    action_class: Optional[str] = None
    action_methods: list[str] = Field(default_factory=list)
    transitions_to: list[str] = Field(default_factory=list)
    url_pattern: Optional[str] = None


class ValidationStep(BaseModel):
    """A step in a validation chain."""

    order: int
    step_type: str  # 'action', 'validator', 'entity'
    class_name: str
    method_name: Optional[str] = None
    rules: list[str] = Field(default_factory=list)


class ValidationChainInfo(BaseModel):
    """Information about a validation chain from action to entity."""

    entry_point: str  # e.g., "PointInfoAction.save"
    validation_steps: list[ValidationStep] = Field(default_factory=list)
    total_rules: int = 0
    validated_fields: list[str] = Field(default_factory=list)


class CrossFeatureDependency(BaseModel):
    """Information about cross-feature dependencies."""

    source_feature: str
    target_feature: str
    relationship_type: str  # 'SHARES_ENTITY', 'SHARES_SERVICE', 'CASCADES_TO'
    shared_component: str
    implication: str


class CrossFeatureContext(BaseModel):
    """Cross-feature dependency context."""

    dependencies: list[CrossFeatureDependency] = Field(default_factory=list)
    shared_entities: dict[str, list[str]] = Field(default_factory=dict)  # entity -> [features]
    shared_services: dict[str, list[str]] = Field(default_factory=dict)  # service -> [features]
    impact_summary: Optional[str] = None


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

    # Phase 6: Enhanced context from menu/screen indexing
    menu_items: list[MenuItemInfo] = Field(
        default_factory=list,
        description="Menu items discovered for the feature"
    )
    sub_features: list[SubFeatureInfo] = Field(
        default_factory=list,
        description="Sub-features (screens) with their URLs, actions, methods, and JSPs"
    )
    validation_chains: list[ValidationChainInfo] = Field(
        default_factory=list,
        description="Validation chains from action → service → validator → entity"
    )
    cross_feature_context: Optional[CrossFeatureContext] = Field(
        default=None,
        description="Cross-feature dependencies, shared entities, and shared services"
    )
    enriched_business_rules: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Business rules enriched with feature context (menu, screen, action)"
    )

    # Phase 11: Enhanced context for BRD generation
    code_snippets: list[CodeSnippetInfo] = Field(
        default_factory=list,
        description="Code snippets from key methods (5-15 lines each)"
    )
    security_rules: list[SecurityRuleInfo] = Field(
        default_factory=list,
        description="Security annotations and access control rules"
    )
    error_messages: list[ErrorMessageInfo] = Field(
        default_factory=list,
        description="Error messages from code and resource bundles"
    )
    transition_conditions: list[TransitionConditionInfo] = Field(
        default_factory=list,
        description="Parsed WebFlow transition conditions with semantics"
    )
    form_field_details: list[FormFieldDetailInfo] = Field(
        default_factory=list,
        description="Enhanced form fields with labels and validation details"
    )
    enhanced_methods: list[EnhancedMethodContext] = Field(
        default_factory=list,
        description="Methods with code snippets, errors, and security context"
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
