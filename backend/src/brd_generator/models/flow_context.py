"""Flow context models for feature traceability.

This module provides data models for representing complete feature flows
from UI to database, enabling auto-generation of BRD Sections 7 and 9.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class LayerType(str, Enum):
    """Architectural layer types for feature flow."""

    UI = "UI"
    FLOW = "Flow"
    CONTROLLER = "Controller"
    SERVICE = "Service"
    DAO = "DAO"
    DATABASE = "Database"
    ENTITY = "Entity"
    UNKNOWN = "Unknown"


class FlowStep(BaseModel):
    """Represents a single step in a feature flow.

    Example:
        FlowStep(
            layer=LayerType.CONTROLLER,
            component_name="LegalEntityWizardAction",
            method_name="saveEntity",
            file_path="/src/main/java/.../LegalEntityWizardAction.java",
            line_start=234,
            line_end=267,
            signature="public String saveEntity(LegalEntityForm form)",
        )
    """

    layer: LayerType
    component_name: str
    method_name: Optional[str] = None
    file_path: str
    line_start: int
    line_end: int
    signature: Optional[str] = None
    node_id: Optional[str] = None
    relationship: Optional[str] = None
    depth: int = 0

    # Enhanced metadata for richer documentation
    operation_type: Optional[str] = None  # "read", "write", "validate", "transform"
    description: Optional[str] = None  # Brief description of what this step does
    validations_applied: list[str] = Field(default_factory=list)  # Business rules enforced here
    input_params: list[str] = Field(default_factory=list)  # Input parameters
    output_type: Optional[str] = None  # Return type
    exceptions_thrown: list[str] = Field(default_factory=list)  # Exceptions this method can throw

    def to_display_string(self) -> str:
        """Format for display in BRD."""
        if self.method_name and self.signature:
            return f"{self.component_name}.{self.method_name}():{self.line_start}"
        elif self.method_name:
            return f"{self.component_name}.{self.method_name}:{self.line_start}"
        else:
            return f"{self.component_name}:{self.line_start}"

    def to_detailed_string(self) -> str:
        """Format with full details for Technical Architecture section."""
        base = f"`{self.component_name}"
        if self.method_name:
            base += f".{self.method_name}()`"
        else:
            base += "`"

        location = f"({self.file_path}:{self.line_start}"
        if self.line_end and self.line_end != self.line_start:
            location += f"-{self.line_end})"
        else:
            location += ")"

        return f"{base} {location}"


class SQLOperation(BaseModel):
    """Represents a SQL operation detected in code.

    Example:
        SQLOperation(
            statement_type="INSERT",
            table_name="les_legal_entity",
            columns=["entity_name", "tax_id", "status"],
            raw_sql="INSERT INTO les_legal_entity (entity_name, tax_id) VALUES (?, ?)",
            source_method="persist",
            source_file="/src/main/java/.../LeslegalEntityDao.java",
            line_number=123,
        )
    """

    statement_type: str  # SELECT, INSERT, UPDATE, DELETE, MERGE
    table_name: str
    columns: list[str] = Field(default_factory=list)
    raw_sql: Optional[str] = None
    source_method: Optional[str] = None
    source_class: Optional[str] = None  # DAO class name
    source_file: Optional[str] = None
    line_number: int = 0

    # Enhanced metadata for richer documentation
    where_clause: Optional[str] = None  # WHERE conditions
    join_tables: list[str] = Field(default_factory=list)  # Tables involved in JOINs
    is_parameterized: bool = True  # Whether uses prepared statements
    estimated_rows: Optional[str] = None  # "single", "multiple", "batch"

    def to_display_string(self) -> str:
        """Format for display in tables."""
        cols = ", ".join(self.columns[:3]) if self.columns else "*"
        if len(self.columns) > 3:
            cols += "..."
        return f"{self.statement_type} {self.table_name} ({cols})"

    def to_detailed_string(self) -> str:
        """Format with full details for Technical Architecture."""
        result = f"`{self.statement_type} {self.table_name}`"
        if self.columns:
            cols = ", ".join(self.columns[:5])
            if len(self.columns) > 5:
                cols += f"... (+{len(self.columns) - 5} more)"
            result += f"\n  - Columns: {cols}"
        if self.source_class and self.source_method:
            result += f"\n  - Source: `{self.source_class}.{self.source_method}()` (line {self.line_number})"
        return result


class DataMapping(BaseModel):
    """Represents a data flow mapping from UI field to database column.

    Example:
        DataMapping(
            ui_field="entityName",
            ui_component="LegalEntityForm.jsp",
            ui_line=45,
            entity_field="entityName",
            entity_class="LeslegalEntity",
            db_column="entity_name",
            db_table="les_legal_entity",
            data_type="VARCHAR(100)",
            is_required=True,
        )
    """

    ui_field: str
    ui_component: Optional[str] = None
    ui_line: int = 0
    entity_field: str
    entity_class: Optional[str] = None
    db_column: Optional[str] = None
    db_table: Optional[str] = None
    data_type: Optional[str] = None
    is_required: bool = False
    validation_rules: list[str] = Field(default_factory=list)

    # Enhanced metadata for richer documentation
    transformation: Optional[str] = None  # Any data transformation applied
    max_length: Optional[int] = None  # For string fields
    default_value: Optional[str] = None  # Default value if any
    db_constraints: list[str] = Field(default_factory=list)  # NOT NULL, UNIQUE, FK, etc.
    input_type: Optional[str] = None  # text, select, checkbox, etc.

    def to_table_row(self) -> dict[str, str]:
        """Format as a row for data mapping table."""
        validations = ", ".join(self.validation_rules[:3]) if self.validation_rules else "-"
        if len(self.validation_rules) > 3:
            validations += "..."
        return {
            "ui_field": f"{self.ui_field}" + (f" ({self.input_type})" if self.input_type else ""),
            "validation": validations,
            "entity_field": f"{self.entity_class}.{self.entity_field}" if self.entity_class else self.entity_field,
            "db_column": f"{self.db_table}.{self.db_column}" if self.db_table and self.db_column else "-",
            "data_type": self.data_type or "-",
            "required": "Yes" if self.is_required else "No",
        }


class FeatureFlow(BaseModel):
    """Complete feature flow from UI to database.

    This is the main model used for BRD Section 7 (Technical Architecture)
    and Section 9 (Implementation Mapping) auto-generation.

    Example:
        FeatureFlow(
            feature_name="Save Legal Entity",
            entry_point="LegalEntityForm.jsp",
            flow_steps=[...],
            sql_operations=[...],
            data_mappings=[...],
        )
    """

    feature_name: str
    entry_point: str
    entry_point_type: LayerType = LayerType.UI
    flow_steps: list[FlowStep] = Field(default_factory=list)
    sql_operations: list[SQLOperation] = Field(default_factory=list)
    data_mappings: list[DataMapping] = Field(default_factory=list)

    # Grouped by layer for Section 7
    layers: dict[str, list[FlowStep]] = Field(default_factory=dict)

    def get_steps_by_layer(self, layer: LayerType) -> list[FlowStep]:
        """Get all steps for a specific layer."""
        return [step for step in self.flow_steps if step.layer == layer]

    def get_all_validations(self) -> list[tuple[str, str, str]]:
        """Get all validation rules from all steps.

        Returns:
            List of (layer, component, rule) tuples
        """
        validations = []
        for step in self.flow_steps:
            for rule in step.validations_applied:
                component = f"{step.component_name}.{step.method_name}()" if step.method_name else step.component_name
                validations.append((step.layer.value, component, rule))
        return validations

    def get_critical_path(self) -> list[FlowStep]:
        """Get the critical path (main flow) through the layers."""
        # Get one step from each layer in order
        layer_order = [LayerType.UI, LayerType.FLOW, LayerType.CONTROLLER, LayerType.SERVICE, LayerType.DAO]
        critical_path = []
        for layer in layer_order:
            steps = self.get_steps_by_layer(layer)
            if steps:
                critical_path.append(steps[0])
        return critical_path

    def to_implementation_table_row(self) -> dict[str, str]:
        """Generate a row for Section 9 Implementation Mapping table."""
        ui_step = next((s for s in self.flow_steps if s.layer == LayerType.UI), None)
        controller_step = next(
            (s for s in self.flow_steps if s.layer == LayerType.CONTROLLER), None
        )
        service_step = next(
            (s for s in self.flow_steps if s.layer == LayerType.SERVICE), None
        )
        dao_step = next((s for s in self.flow_steps if s.layer == LayerType.DAO), None)
        sql_op = self.sql_operations[0] if self.sql_operations else None

        return {
            "operation": self.feature_name,
            "ui": ui_step.to_display_string() if ui_step else "-",
            "controller": controller_step.to_display_string() if controller_step else "-",
            "service": service_step.to_display_string() if service_step else "-",
            "dao": dao_step.to_display_string() if dao_step else "-",
            "database": f"{sql_op.statement_type} {sql_op.table_name}" if sql_op else "-",
        }

    def to_detailed_implementation_row(self) -> dict[str, Any]:
        """Generate a detailed row with additional metadata."""
        ui_step = next((s for s in self.flow_steps if s.layer == LayerType.UI), None)
        controller_step = next(
            (s for s in self.flow_steps if s.layer == LayerType.CONTROLLER), None
        )
        service_step = next(
            (s for s in self.flow_steps if s.layer == LayerType.SERVICE), None
        )
        dao_step = next((s for s in self.flow_steps if s.layer == LayerType.DAO), None)

        # Collect all SQL operations
        sql_ops = [f"{op.statement_type} {op.table_name}" for op in self.sql_operations]

        # Collect all validations
        validations = []
        for step in self.flow_steps:
            validations.extend(step.validations_applied)

        return {
            "operation": self.feature_name,
            "entry_point": self.entry_point,
            "entry_type": self.entry_point_type.value,
            "ui": {
                "component": ui_step.component_name if ui_step else None,
                "file": ui_step.file_path if ui_step else None,
                "line": ui_step.line_start if ui_step else None,
            },
            "controller": {
                "class": controller_step.component_name if controller_step else None,
                "method": controller_step.method_name if controller_step else None,
                "signature": controller_step.signature if controller_step else None,
                "file": controller_step.file_path if controller_step else None,
                "lines": f"{controller_step.line_start}-{controller_step.line_end}" if controller_step else None,
            },
            "service": {
                "class": service_step.component_name if service_step else None,
                "method": service_step.method_name if service_step else None,
                "signature": service_step.signature if service_step else None,
                "file": service_step.file_path if service_step else None,
                "lines": f"{service_step.line_start}-{service_step.line_end}" if service_step else None,
            },
            "dao": {
                "class": dao_step.component_name if dao_step else None,
                "method": dao_step.method_name if dao_step else None,
                "file": dao_step.file_path if dao_step else None,
                "lines": f"{dao_step.line_start}-{dao_step.line_end}" if dao_step else None,
            },
            "database": {
                "operations": sql_ops,
                "tables": list(set(op.table_name for op in self.sql_operations)),
            },
            "validations": validations,
            "data_mappings_count": len(self.data_mappings),
        }


class CallChainRequest(BaseModel):
    """Request for extracting a call chain."""

    entry_point_id: str
    direction: str = "downstream"  # downstream or upstream
    max_depth: int = 10


class CallChainResponse(BaseModel):
    """Response containing call chain results."""

    entry_point: FlowStep
    chain: list[FlowStep] = Field(default_factory=list)
    sql_statements: list[SQLOperation] = Field(default_factory=list)
    data_bindings: list[DataMapping] = Field(default_factory=list)


class FeatureFlowRequest(BaseModel):
    """Request for extracting a feature flow."""

    entry_point: str  # File path or entity ID
    entry_point_type: str = "jsp"  # jsp, webflow, controller
    include_sql: bool = True
    include_data_mappings: bool = True
    max_depth: int = 10


class FeatureFlowResponse(BaseModel):
    """Response containing feature flow results."""

    success: bool = True
    feature_flow: Optional[FeatureFlow] = None
    error: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class ImplementationMapping(BaseModel):
    """Implementation mapping for BRD Section 9.

    Provides a tabular view of operation -> component mappings.
    """

    operations: list[dict[str, str]] = Field(default_factory=list)
    data_operations: list[dict[str, str]] = Field(default_factory=list)  # Field-level operations
    validation_checkpoints: list[dict[str, str]] = Field(default_factory=list)

    @classmethod
    def from_feature_flows(cls, flows: list[FeatureFlow]) -> "ImplementationMapping":
        """Create implementation mapping from multiple feature flows."""
        operations = []
        data_operations = []
        validation_checkpoints = []

        for flow in flows:
            # Main operation row
            operations.append(flow.to_implementation_table_row())

            # Data field operations (from data mappings)
            for dm in flow.data_mappings:
                data_operations.append({
                    "field": dm.ui_field,
                    "ui": f"{dm.ui_component}:{dm.ui_line}" if dm.ui_component else "-",
                    "entity": f"{dm.entity_class}.{dm.entity_field}" if dm.entity_class else dm.entity_field,
                    "database": f"{dm.db_table}.{dm.db_column}" if dm.db_table and dm.db_column else "-",
                    "validation": ", ".join(dm.validation_rules[:2]) if dm.validation_rules else "-",
                    "required": "Yes" if dm.is_required else "No",
                })

            # Validation checkpoints (from flow steps)
            for step in flow.flow_steps:
                for rule in step.validations_applied:
                    validation_checkpoints.append({
                        "layer": step.layer.value,
                        "component": f"{step.component_name}.{step.method_name}()" if step.method_name else step.component_name,
                        "validation": rule,
                        "line": str(step.line_start),
                    })

        return cls(
            operations=operations,
            data_operations=data_operations,
            validation_checkpoints=validation_checkpoints,
        )

    def to_markdown_table(self) -> str:
        """Generate comprehensive markdown tables for BRD Section 9."""
        sections = []

        # Main Operations Mapping Table
        sections.append("### Operation-to-Implementation Mapping\n")
        sections.append("*Maps each business operation to the implementing component at each architectural layer*\n")

        if self.operations:
            headers = ["Operation", "UI", "Controller", "Service", "DAO", "Database"]
            sections.append("| " + " | ".join(headers) + " |")
            sections.append("| " + " | ".join(["---"] * len(headers)) + " |")

            for op in self.operations:
                row = [
                    op.get("operation", "-"),
                    f"`{op.get('ui', '-')}`" if op.get('ui') != '-' else "-",
                    f"`{op.get('controller', '-')}`" if op.get('controller') != '-' else "-",
                    f"`{op.get('service', '-')}`" if op.get('service') != '-' else "-",
                    f"`{op.get('dao', '-')}`" if op.get('dao') != '-' else "-",
                    f"`{op.get('database', '-')}`" if op.get('database') != '-' else "-",
                ]
                sections.append("| " + " | ".join(row) + " |")
            sections.append("")
        else:
            sections.append("*No operation mappings available*\n")

        # Data Field Mapping Table
        if self.data_operations:
            sections.append("### Field-Level Data Mapping\n")
            sections.append("*Traces each data field from UI input through to database column*\n")

            headers = ["Field", "UI Location", "Entity Property", "DB Column", "Validations", "Required"]
            sections.append("| " + " | ".join(headers) + " |")
            sections.append("| " + " | ".join(["---"] * len(headers)) + " |")

            for field_op in self.data_operations[:20]:  # Limit to 20 fields
                row = [
                    f"`{field_op.get('field', '-')}`",
                    field_op.get("ui", "-"),
                    f"`{field_op.get('entity', '-')}`" if field_op.get('entity') != '-' else "-",
                    f"`{field_op.get('database', '-')}`" if field_op.get('database') != '-' else "-",
                    field_op.get("validation", "-"),
                    field_op.get("required", "-"),
                ]
                sections.append("| " + " | ".join(row) + " |")
            sections.append("")

        # Validation Checkpoints Table
        if self.validation_checkpoints:
            sections.append("### Validation Checkpoints\n")
            sections.append("*Shows where each validation rule is enforced in the code*\n")

            headers = ["Layer", "Component", "Validation Rule", "Line"]
            sections.append("| " + " | ".join(headers) + " |")
            sections.append("| " + " | ".join(["---"] * len(headers)) + " |")

            for checkpoint in self.validation_checkpoints[:15]:  # Limit to 15 rules
                row = [
                    checkpoint.get("layer", "-"),
                    f"`{checkpoint.get('component', '-')}`",
                    checkpoint.get("validation", "-"),
                    checkpoint.get("line", "-"),
                ]
                sections.append("| " + " | ".join(row) + " |")
            sections.append("")

        # Legend
        sections.append("**Legend:**")
        sections.append("- Format for code references: `ClassName.methodName():lineNumber`")
        sections.append("- UI references: `filename:lineNumber`")
        sections.append("- Database operations: `OPERATION tableName`")
        sections.append("")

        return "\n".join(sections)

    def to_compact_table(self) -> str:
        """Generate compact markdown table for limited space."""
        if not self.operations:
            return "No implementation mappings found."

        headers = ["Operation", "UI", "Controller", "Service", "DAO", "Database"]
        rows = []

        rows.append("| " + " | ".join(headers) + " |")
        rows.append("| " + " | ".join(["---"] * len(headers)) + " |")

        for op in self.operations:
            row = [
                op.get("operation", "-"),
                op.get("ui", "-"),
                op.get("controller", "-"),
                op.get("service", "-"),
                op.get("dao", "-"),
                op.get("database", "-"),
            ]
            rows.append("| " + " | ".join(row) + " |")

        return "\n".join(rows)


class TechnicalArchitectureView(BaseModel):
    """Technical architecture view for BRD Section 7.

    Provides a layered view of components involved in a feature.
    """

    feature_name: str
    ui_components: list[dict[str, Any]] = Field(default_factory=list)
    flow_components: list[dict[str, Any]] = Field(default_factory=list)
    controller_components: list[dict[str, Any]] = Field(default_factory=list)
    service_components: list[dict[str, Any]] = Field(default_factory=list)
    dao_components: list[dict[str, Any]] = Field(default_factory=list)
    database_tables: list[dict[str, Any]] = Field(default_factory=list)
    data_mappings: list[dict[str, Any]] = Field(default_factory=list)
    validations: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def from_feature_flow(cls, flow: FeatureFlow) -> "TechnicalArchitectureView":
        """Create technical architecture view from a feature flow."""
        # Collect validations from all steps
        validations = []
        for step in flow.flow_steps:
            for rule in step.validations_applied:
                validations.append({
                    "layer": step.layer.value,
                    "component": step.component_name,
                    "rule": rule,
                })

        return cls(
            feature_name=flow.feature_name,
            ui_components=[
                {
                    "name": s.component_name,
                    "file": s.file_path,
                    "line": s.line_start,
                    "description": s.description,
                }
                for s in flow.get_steps_by_layer(LayerType.UI)
            ],
            flow_components=[
                {
                    "name": s.component_name,
                    "file": s.file_path,
                    "line": s.line_start,
                    "description": s.description,
                }
                for s in flow.get_steps_by_layer(LayerType.FLOW)
            ],
            controller_components=[
                {
                    "name": s.component_name,
                    "method": s.method_name,
                    "signature": s.signature,
                    "file": s.file_path,
                    "line_start": s.line_start,
                    "line_end": s.line_end,
                    "description": s.description,
                    "validations": s.validations_applied,
                }
                for s in flow.get_steps_by_layer(LayerType.CONTROLLER)
            ],
            service_components=[
                {
                    "name": s.component_name,
                    "method": s.method_name,
                    "signature": s.signature,
                    "file": s.file_path,
                    "line_start": s.line_start,
                    "line_end": s.line_end,
                    "description": s.description,
                    "validations": s.validations_applied,
                }
                for s in flow.get_steps_by_layer(LayerType.SERVICE)
            ],
            dao_components=[
                {
                    "name": s.component_name,
                    "method": s.method_name,
                    "file": s.file_path,
                    "line_start": s.line_start,
                    "line_end": s.line_end,
                    "description": s.description,
                }
                for s in flow.get_steps_by_layer(LayerType.DAO)
            ],
            database_tables=[
                {
                    "table": op.table_name,
                    "operation": op.statement_type,
                    "columns": op.columns,
                    "source_class": op.source_class,
                    "source_method": op.source_method,
                    "line": op.line_number,
                }
                for op in flow.sql_operations
            ],
            data_mappings=[
                {
                    "ui_field": dm.ui_field,
                    "entity_field": dm.entity_field,
                    "db_column": dm.db_column,
                    "validation": dm.validation_rules,
                    "required": dm.is_required,
                }
                for dm in flow.data_mappings
            ],
            validations=validations,
        )

    def to_markdown(self) -> str:
        """Generate comprehensive markdown for BRD Section 7 - Technical Architecture."""
        sections = []
        sections.append(f"### {self.feature_name} - End-to-End Technical Flow\n")

        # Add flow visualization hint
        sections.append("**Data Flow:** UI → Flow/Navigation → Controller → Service → DAO → Database\n")

        # UI Layer
        if self.ui_components:
            sections.append("#### UI Layer (Entry Point)")
            sections.append("*Handles user input and form submission*\n")
            for comp in self.ui_components:
                file_ref = f"{comp['file']}:{comp['line']}" if comp.get('file') else "N/A"
                sections.append(f"| Component | `{comp['name']}` |")
                sections.append(f"| File | `{file_ref}` |")
                if comp.get('description'):
                    sections.append(f"| Purpose | {comp['description']} |")
                sections.append("")

        # Flow/Navigation Layer
        if self.flow_components:
            sections.append("#### Flow/Navigation Layer")
            sections.append("*Manages page flow and state transitions*\n")
            for comp in self.flow_components:
                file_ref = f"{comp['file']}:{comp['line']}" if comp.get('file') else "N/A"
                sections.append(f"- **{comp['name']}** (`{file_ref}`)")
                if comp.get('description'):
                    sections.append(f"  - {comp['description']}")
            sections.append("")

        # Controller Layer
        if self.controller_components:
            sections.append("#### Controller Layer (Request Processing)")
            sections.append("*Processes HTTP requests and coordinates business logic*\n")
            for comp in self.controller_components:
                method = comp.get('method', 'process')
                line_ref = f"{comp.get('line_start', 0)}-{comp.get('line_end', 0)}"
                sections.append(f"**Class:** `{comp['name']}`")
                sections.append(f"- **Method:** `{method}()` (lines {line_ref})")
                if comp.get('signature'):
                    sections.append(f"- **Signature:** `{comp['signature']}`")
                if comp.get('file'):
                    sections.append(f"- **File:** `{comp['file']}`")
                if comp.get('validations'):
                    sections.append(f"- **Validations:** {', '.join(comp['validations'])}")
                sections.append("")

        # Service Layer
        if self.service_components:
            sections.append("#### Service Layer (Business Logic)")
            sections.append("*Contains core business rules and data transformation*\n")
            for comp in self.service_components:
                method = comp.get('method', 'execute')
                line_ref = f"{comp.get('line_start', 0)}-{comp.get('line_end', 0)}"
                sections.append(f"**Class:** `{comp['name']}`")
                sections.append(f"- **Method:** `{method}()` (lines {line_ref})")
                if comp.get('signature'):
                    sections.append(f"- **Signature:** `{comp['signature']}`")
                if comp.get('file'):
                    sections.append(f"- **File:** `{comp['file']}`")
                if comp.get('validations'):
                    sections.append("- **Business Rules Applied:**")
                    for v in comp['validations']:
                        sections.append(f"  - {v}")
                sections.append("")

        # DAO Layer
        if self.dao_components:
            sections.append("#### Data Access Layer (Persistence)")
            sections.append("*Handles database operations and entity persistence*\n")
            for comp in self.dao_components:
                method = comp.get('method', 'persist')
                line_ref = f"{comp.get('line_start', 0)}-{comp.get('line_end', 0)}"
                sections.append(f"**Class:** `{comp['name']}`")
                sections.append(f"- **Method:** `{method}()` (lines {line_ref})")
                if comp.get('file'):
                    sections.append(f"- **File:** `{comp['file']}`")
                sections.append("")

        # Database Layer
        if self.database_tables:
            sections.append("#### Database Layer")
            sections.append("*SQL operations executed against the database*\n")
            sections.append("| Operation | Table | Columns | Source |")
            sections.append("|-----------|-------|---------|--------|")
            for tbl in self.database_tables:
                cols = ", ".join(tbl.get("columns", [])[:4]) if tbl.get("columns") else "*"
                if tbl.get("columns") and len(tbl["columns"]) > 4:
                    cols += "..."
                source = ""
                if tbl.get('source_class') and tbl.get('source_method'):
                    source = f"`{tbl['source_class']}.{tbl['source_method']}():{tbl.get('line', 0)}`"
                sections.append(f"| {tbl['operation']} | `{tbl['table']}` | {cols} | {source} |")
            sections.append("")

        # Data Mappings (Field-Level Traceability)
        if self.data_mappings:
            sections.append("#### Field-Level Data Mapping")
            sections.append("*Traces data from UI field to database column*\n")
            sections.append("| UI Field | Entity Field | DB Column | Required | Validations |")
            sections.append("|----------|--------------|-----------|----------|-------------|")
            for dm in self.data_mappings:
                validations = ", ".join(dm.get("validation", [])[:2]) if dm.get("validation") else "-"
                if dm.get("validation") and len(dm["validation"]) > 2:
                    validations += "..."
                required = "Yes" if dm.get("required") else "No"
                db_col = dm.get("db_column") or "-"
                sections.append(f"| `{dm['ui_field']}` | `{dm['entity_field']}` | `{db_col}` | {required} | {validations} |")
            sections.append("")

        return "\n".join(sections)

    def to_compact_markdown(self) -> str:
        """Generate compact markdown for limited space."""
        sections = []
        sections.append(f"### {self.feature_name}\n")

        if self.ui_components:
            sections.append("**UI Layer:**")
            for comp in self.ui_components:
                sections.append(f"- `{comp['name']}` ({comp.get('file', 'N/A')}:{comp.get('line', 0)})")

        if self.flow_components:
            sections.append("\n**Flow Layer:**")
            for comp in self.flow_components:
                sections.append(f"- `{comp['name']}` ({comp.get('file', 'N/A')}:{comp.get('line', 0)})")

        if self.controller_components:
            sections.append("\n**Controller Layer:**")
            for comp in self.controller_components:
                sections.append(
                    f"- `{comp['name']}.{comp.get('method', '')}()` ({comp.get('file', 'N/A')}:{comp.get('line_start', 0)}-{comp.get('line_end', 0)})"
                )

        if self.service_components:
            sections.append("\n**Service Layer:**")
            for comp in self.service_components:
                sections.append(
                    f"- `{comp['name']}.{comp.get('method', '')}()` ({comp.get('file', 'N/A')}:{comp.get('line_start', 0)}-{comp.get('line_end', 0)})"
                )

        if self.dao_components:
            sections.append("\n**Data Access Layer:**")
            for comp in self.dao_components:
                sections.append(
                    f"- `{comp['name']}.{comp.get('method', '')}()` ({comp.get('file', 'N/A')}:{comp.get('line_start', 0)}-{comp.get('line_end', 0)})"
                )

        if self.database_tables:
            sections.append("\n**Database:**")
            for tbl in self.database_tables:
                cols = ", ".join(tbl.get("columns", [])[:3]) if tbl.get("columns") else "*"
                sections.append(f"- `{tbl['operation']} {tbl['table']}` ({cols})")

        return "\n".join(sections)
