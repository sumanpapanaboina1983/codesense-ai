"""Feature Flow Service for End-to-End Traceability.

This module provides the FeatureFlowService class that extracts complete
feature flows from UI to database, enabling auto-generation of BRD
Sections 7 (Technical Architecture) and 9 (Implementation Mapping).
"""

from __future__ import annotations

import os
from typing import Any, Optional

from ..models.flow_context import (
    CallChainRequest,
    CallChainResponse,
    DataMapping,
    FeatureFlow,
    FeatureFlowRequest,
    FeatureFlowResponse,
    FlowStep,
    ImplementationMapping,
    LayerType,
    SQLOperation,
    TechnicalArchitectureView,
)
from ..queries import flow_queries
from ..utils.logger import get_logger

logger = get_logger(__name__)


class FeatureFlowService:
    """Service for extracting feature flows from code graph.

    This service provides methods to:
    1. Extract complete feature flows from entry points (JSP, WebFlow, Controller)
    2. Get call chains with line numbers and signatures
    3. Map data flow from UI fields to database columns
    4. Find SQL operations executed by DAOs
    5. Generate implementation mapping tables for BRDs

    Example:
        service = FeatureFlowService(neo4j_client)
        flow = await service.extract_feature_flow("LegalEntityForm.jsp")
        print(flow.to_implementation_table_row())
    """

    def __init__(self, neo4j_client):
        """Initialize the feature flow service.

        Args:
            neo4j_client: Neo4j MCP client for executing queries
        """
        self.neo4j = neo4j_client
        logger.info("FeatureFlowService initialized")

    async def extract_feature_flow(
        self,
        entry_point: str,
        entry_point_type: str = "auto",
        include_sql: bool = True,
        include_data_mappings: bool = True,
        max_depth: int = 10,
    ) -> FeatureFlowResponse:
        """Extract complete feature flow from an entry point.

        Args:
            entry_point: File path, name, or entity ID of entry point
            entry_point_type: Type hint (jsp, webflow, controller, auto)
            include_sql: Whether to include SQL operations
            include_data_mappings: Whether to include data mappings
            max_depth: Maximum traversal depth

        Returns:
            FeatureFlowResponse with the extracted flow
        """
        logger.info(f"Extracting feature flow from: {entry_point}")

        try:
            # Determine entry point type if auto
            if entry_point_type == "auto":
                entry_point_type = self._detect_entry_point_type(entry_point)

            # Find the entry point in the graph
            entry_point_id = await self._resolve_entry_point(entry_point, entry_point_type)
            if not entry_point_id:
                return FeatureFlowResponse(
                    success=False,
                    error=f"Entry point not found: {entry_point}",
                )

            # Extract the flow based on entry type
            if entry_point_type == "jsp":
                flow = await self._extract_jsp_flow(entry_point_id, max_depth)
            elif entry_point_type == "webflow":
                flow = await self._extract_webflow_flow(entry_point_id, max_depth)
            else:
                flow = await self._extract_generic_flow(entry_point_id, max_depth)

            # Add SQL operations if requested
            if include_sql and flow:
                flow.sql_operations = await self._get_sql_operations_for_flow(flow)
                # Add source class info to SQL operations
                for sql_op in flow.sql_operations:
                    for step in flow.flow_steps:
                        if step.layer == LayerType.DAO:
                            sql_op.source_class = step.component_name
                            break

            # Add data mappings if requested
            if include_data_mappings and flow:
                flow.data_mappings = await self._get_data_mappings_for_flow(
                    entry_point_id, entry_point_type
                )

            # Enrich flow with validation information
            if flow:
                flow = await self.enrich_flow_with_validations(flow)

            # Group steps by layer
            if flow:
                flow.layers = self._group_steps_by_layer(flow.flow_steps)

            return FeatureFlowResponse(
                success=True,
                feature_flow=flow,
            )

        except Exception as e:
            logger.error(f"Feature flow extraction failed: {e}")
            return FeatureFlowResponse(
                success=False,
                error=str(e),
            )

    async def get_call_chain(
        self,
        method_id: str,
        direction: str = "downstream",
        max_depth: int = 10,
    ) -> CallChainResponse:
        """Get call chain for a method.

        Args:
            method_id: Entity ID of the method
            direction: "downstream" (who this calls) or "upstream" (who calls this)
            max_depth: Maximum traversal depth

        Returns:
            CallChainResponse with the call chain
        """
        logger.info(f"Getting {direction} call chain for: {method_id}")

        try:
            if direction == "upstream":
                query = flow_queries.GET_UPSTREAM_CALL_CHAIN.replace("$maxDepth", str(max_depth))
            else:
                query = flow_queries.GET_METHOD_CALL_CHAIN.replace("$maxDepth", str(max_depth))

            result = await self.neo4j.query_code_structure(query, {"methodId": method_id})

            # Parse results into FlowSteps
            chain = []
            for record in result.get("nodes", []):
                step = FlowStep(
                    layer=LayerType(record.get("layer", "Unknown")),
                    component_name=record.get("parentClass") or record.get("name", ""),
                    method_name=record.get("name"),
                    file_path=record.get("filePath", ""),
                    line_start=record.get("startLine", 0),
                    line_end=record.get("endLine", 0),
                    signature=record.get("signature"),
                    node_id=record.get("nodeId"),
                    depth=record.get("depth", 0),
                )
                chain.append(step)

            # Create entry point step
            entry_step = chain[0] if chain else FlowStep(
                layer=LayerType.UNKNOWN,
                component_name="",
                file_path="",
                line_start=0,
                line_end=0,
            )

            return CallChainResponse(
                entry_point=entry_step,
                chain=chain[1:] if len(chain) > 1 else [],
            )

        except Exception as e:
            logger.error(f"Call chain extraction failed: {e}")
            return CallChainResponse(
                entry_point=FlowStep(
                    layer=LayerType.UNKNOWN,
                    component_name="",
                    file_path="",
                    line_start=0,
                    line_end=0,
                ),
                chain=[],
            )

    async def map_data_flow(
        self,
        form_field: str,
        jsp_file: Optional[str] = None,
    ) -> list[DataMapping]:
        """Map data flow from UI field to entity field.

        Args:
            form_field: Field name or path to trace
            jsp_file: Optional JSP file to scope the search

        Returns:
            List of DataMapping objects
        """
        logger.info(f"Mapping data flow for field: {form_field}")

        try:
            result = await self.neo4j.query_code_structure(
                flow_queries.GET_DATA_FLOW_MAPPING,
                {"fieldName": form_field},
            )

            mappings = []
            for record in result.get("nodes", []):
                mapping = DataMapping(
                    ui_field=record.get("uiField", form_field),
                    ui_component=record.get("uiComponent"),
                    ui_line=record.get("uiLine", 0),
                    entity_field=record.get("entityField", ""),
                    entity_class=record.get("entityClass"),
                    db_column=record.get("inferredColumn"),
                    db_table=record.get("dbTable"),
                    data_type=record.get("fieldType"),
                    is_required=record.get("isRequired", False),
                    validation_rules=record.get("validationRules", []),
                )
                mappings.append(mapping)

            return mappings

        except Exception as e:
            logger.error(f"Data flow mapping failed: {e}")
            return []

    async def find_sql_operations(
        self,
        dao_class: str,
    ) -> list[SQLOperation]:
        """Find SQL operations in a DAO class.

        Args:
            dao_class: Name or entity ID of the DAO class

        Returns:
            List of SQLOperation objects
        """
        logger.info(f"Finding SQL operations for: {dao_class}")

        try:
            result = await self.neo4j.query_code_structure(
                flow_queries.GET_SQL_FOR_DAO,
                {"daoId": dao_class, "daoName": dao_class},
            )

            operations = []
            for record in result.get("nodes", []):
                if record.get("statementType"):
                    op = SQLOperation(
                        statement_type=record.get("statementType", "UNKNOWN"),
                        table_name=record.get("tableName", ""),
                        columns=record.get("columns", []),
                        raw_sql=record.get("rawSql"),
                        source_method=record.get("methodName"),
                        line_number=record.get("sqlLineNumber", 0),
                    )
                    operations.append(op)

            return operations

        except Exception as e:
            logger.error(f"SQL operation extraction failed: {e}")
            return []

    async def find_entry_points(
        self,
        keyword: str,
        limit: int = 20,
    ) -> list[dict]:
        """Find entry points matching a keyword.

        Args:
            keyword: Keyword to search for
            limit: Maximum number of results

        Returns:
            List of entry point dictionaries
        """
        logger.info(f"Finding entry points for: {keyword}")

        try:
            result = await self.neo4j.query_code_structure(
                flow_queries.FIND_ENTRY_POINTS,
                {"keyword": keyword},
            )

            return result.get("nodes", [])[:limit]

        except Exception as e:
            logger.error(f"Entry point search failed: {e}")
            return []

    async def generate_implementation_mapping(
        self,
        entry_points: list[str],
    ) -> ImplementationMapping:
        """Generate implementation mapping table for BRD Section 9.

        Args:
            entry_points: List of entry point IDs or paths

        Returns:
            ImplementationMapping ready for markdown generation
        """
        logger.info(f"Generating implementation mapping for {len(entry_points)} entry points")

        flows = []
        for entry_point in entry_points:
            response = await self.extract_feature_flow(entry_point)
            if response.success and response.feature_flow:
                flows.append(response.feature_flow)

        return ImplementationMapping.from_feature_flows(flows)

    async def generate_technical_architecture(
        self,
        entry_point: str,
    ) -> TechnicalArchitectureView:
        """Generate technical architecture view for BRD Section 7.

        Args:
            entry_point: Entry point ID or path

        Returns:
            TechnicalArchitectureView ready for markdown generation
        """
        logger.info(f"Generating technical architecture for: {entry_point}")

        response = await self.extract_feature_flow(entry_point)
        if response.success and response.feature_flow:
            return TechnicalArchitectureView.from_feature_flow(response.feature_flow)

        return TechnicalArchitectureView(feature_name="Unknown")

    async def generate_sequence_diagram(
        self,
        entry_point_id: str,
    ) -> str:
        """Generate Mermaid sequence diagram for a feature flow.

        Args:
            entry_point_id: Entity ID of the entry point

        Returns:
            Mermaid sequence diagram markdown
        """
        logger.info(f"Generating sequence diagram for: {entry_point_id}")

        try:
            # Get the feature flow
            response = await self.extract_feature_flow(entry_point_id)
            if not response.success or not response.feature_flow:
                return "```mermaid\nsequenceDiagram\n    Note over System: No flow data available\n```"

            flow = response.feature_flow

            # Build mermaid diagram
            lines = ["```mermaid", "sequenceDiagram"]

            # Define participants
            participants = set()
            for step in flow.flow_steps:
                participant = f"{step.layer.value}_{step.component_name}"
                if participant not in participants:
                    lines.append(f"    participant {step.layer.value} as {step.component_name}")
                    participants.add(participant)

            # Add interactions
            prev_layer = None
            for step in flow.flow_steps:
                if prev_layer and prev_layer != step.layer:
                    method = step.method_name or "process"
                    lines.append(f"    {prev_layer.value}->>+{step.layer.value}: {method}()")
                prev_layer = step.layer

            # Add SQL operations
            for sql_op in flow.sql_operations:
                lines.append(f"    DAO->>+Database: {sql_op.statement_type} {sql_op.table_name}")

            lines.append("```")
            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Sequence diagram generation failed: {e}")
            return "```mermaid\nsequenceDiagram\n    Note over System: Error generating diagram\n```"

    # Private helper methods

    def _detect_entry_point_type(self, entry_point: str) -> str:
        """Detect entry point type from path/name."""
        lower = entry_point.lower()
        if lower.endswith(".jsp"):
            return "jsp"
        elif "flow" in lower and lower.endswith(".xml"):
            return "webflow"
        elif lower.endswith("action") or lower.endswith("controller"):
            return "controller"
        return "auto"

    async def _resolve_entry_point(
        self,
        entry_point: str,
        entry_point_type: str,
    ) -> Optional[str]:
        """Resolve entry point to entity ID."""
        # Try direct match first
        query = """
            MATCH (n)
            WHERE n.entityId = $entry
               OR n.name = $entry
               OR n.filePath CONTAINS $entry
            RETURN n.entityId AS entityId
            LIMIT 1
        """

        result = await self.neo4j.query_code_structure(query, {"entry": entry_point})
        nodes = result.get("nodes", [])

        if nodes:
            return nodes[0].get("entityId")

        # Try type-specific search
        if entry_point_type == "jsp":
            query = """
                MATCH (n:JSPPage)
                WHERE n.name CONTAINS $entry OR n.filePath CONTAINS $entry
                RETURN n.entityId AS entityId
                LIMIT 1
            """
        elif entry_point_type == "webflow":
            query = """
                MATCH (n:WebFlowDefinition)
                WHERE n.name CONTAINS $entry OR n.filePath CONTAINS $entry
                RETURN n.entityId AS entityId
                LIMIT 1
            """
        else:
            query = """
                MATCH (n)
                WHERE (n:JavaClass OR n:SpringController)
                  AND (n.name CONTAINS $entry OR n.filePath CONTAINS $entry)
                RETURN n.entityId AS entityId
                LIMIT 1
            """

        result = await self.neo4j.query_code_structure(query, {"entry": entry_point})
        nodes = result.get("nodes", [])

        return nodes[0].get("entityId") if nodes else None

    async def _extract_jsp_flow(
        self,
        entry_point_id: str,
        max_depth: int,
    ) -> FeatureFlow:
        """Extract flow starting from a JSP page."""
        result = await self.neo4j.query_code_structure(
            flow_queries.TRACE_JSP_TO_DATABASE,
            {
                "jspId": entry_point_id,
                "jspName": "",
                "jspPath": "",
            },
        )

        # Parse results into FlowSteps
        flow_steps = []
        feature_name = ""

        for record in result.get("nodes", []):
            # UI Layer
            ui_layer = record.get("uiLayer", {})
            if ui_layer and ui_layer.get("name"):
                feature_name = ui_layer.get("name", "").replace(".jsp", "")
                flow_steps.append(FlowStep(
                    layer=LayerType.UI,
                    component_name=ui_layer.get("name", ""),
                    file_path=ui_layer.get("path", ""),
                    line_start=ui_layer.get("line", 1),
                    line_end=ui_layer.get("line", 1),
                ))

            # Flow Layer
            flow_layer = record.get("flowLayer", {})
            if flow_layer and flow_layer.get("name"):
                flow_steps.append(FlowStep(
                    layer=LayerType.FLOW,
                    component_name=flow_layer.get("name", ""),
                    file_path=flow_layer.get("path", ""),
                    line_start=1,
                    line_end=1,
                ))

            # Controller Layer
            ctrl_layer = record.get("controllerLayer", {})
            if ctrl_layer and ctrl_layer.get("class"):
                flow_steps.append(FlowStep(
                    layer=LayerType.CONTROLLER,
                    component_name=ctrl_layer.get("class", ""),
                    method_name=ctrl_layer.get("method"),
                    file_path=ctrl_layer.get("path", ""),
                    line_start=ctrl_layer.get("startLine", 0),
                    line_end=ctrl_layer.get("endLine", 0),
                    signature=ctrl_layer.get("signature"),
                ))

            # Service Layer
            svc_layer = record.get("serviceLayer", {})
            if svc_layer and svc_layer.get("class"):
                flow_steps.append(FlowStep(
                    layer=LayerType.SERVICE,
                    component_name=svc_layer.get("class", ""),
                    method_name=svc_layer.get("method"),
                    file_path=svc_layer.get("path", ""),
                    line_start=svc_layer.get("startLine", 0),
                    line_end=svc_layer.get("endLine", 0),
                    signature=svc_layer.get("signature"),
                ))

            # DAO Layer
            dao_layer = record.get("daoLayer", {})
            if dao_layer and dao_layer.get("class"):
                flow_steps.append(FlowStep(
                    layer=LayerType.DAO,
                    component_name=dao_layer.get("class", ""),
                    method_name=dao_layer.get("method"),
                    file_path=dao_layer.get("path", ""),
                    line_start=dao_layer.get("startLine", 0),
                    line_end=dao_layer.get("endLine", 0),
                ))

        return FeatureFlow(
            feature_name=feature_name or "Unknown Feature",
            entry_point=entry_point_id,
            entry_point_type=LayerType.UI,
            flow_steps=flow_steps,
        )

    async def _extract_webflow_flow(
        self,
        entry_point_id: str,
        max_depth: int,
    ) -> FeatureFlow:
        """Extract flow starting from a WebFlow definition."""
        # Similar to JSP but starts from WebFlow
        return await self._extract_generic_flow(entry_point_id, max_depth)

    async def _extract_generic_flow(
        self,
        entry_point_id: str,
        max_depth: int,
    ) -> FeatureFlow:
        """Extract flow from a generic entry point."""
        result = await self.neo4j.query_code_structure(
            flow_queries.TRACE_FULL_FLOW,
            {
                "entryPointId": entry_point_id,
                "entryPointPath": "",
                "entryPointName": "",
            },
        )

        flow_steps = []
        feature_name = "Unknown Feature"

        for record in result.get("nodes", []):
            entry_name = record.get("entryName")
            if entry_name:
                feature_name = entry_name

            # Add controllers
            for ctrl in record.get("controllers", []):
                if ctrl.get("name"):
                    flow_steps.append(FlowStep(
                        layer=LayerType.CONTROLLER,
                        component_name=ctrl.get("name", ""),
                        file_path=ctrl.get("path", ""),
                        line_start=0,
                        line_end=0,
                    ))

            # Add services
            for svc in record.get("services", []):
                if svc.get("name"):
                    flow_steps.append(FlowStep(
                        layer=LayerType.SERVICE,
                        component_name=svc.get("name", ""),
                        file_path=svc.get("path", ""),
                        line_start=0,
                        line_end=0,
                    ))

            # Add DAOs
            for dao in record.get("daos", []):
                if dao.get("name"):
                    flow_steps.append(FlowStep(
                        layer=LayerType.DAO,
                        component_name=dao.get("name", ""),
                        file_path=dao.get("path", ""),
                        line_start=0,
                        line_end=0,
                    ))

        return FeatureFlow(
            feature_name=feature_name,
            entry_point=entry_point_id,
            flow_steps=flow_steps,
        )

    async def _get_sql_operations_for_flow(
        self,
        flow: FeatureFlow,
    ) -> list[SQLOperation]:
        """Get SQL operations for all DAO methods in the flow."""
        operations = []

        for step in flow.flow_steps:
            if step.layer == LayerType.DAO:
                dao_ops = await self.find_sql_operations(step.component_name)
                operations.extend(dao_ops)

        return operations

    async def _get_data_mappings_for_flow(
        self,
        entry_point_id: str,
        entry_point_type: str,
    ) -> list[DataMapping]:
        """Get data mappings for a flow entry point."""
        if entry_point_type != "jsp":
            return []

        result = await self.neo4j.query_code_structure(
            flow_queries.GET_FORM_BINDINGS,
            {"jspId": entry_point_id},
        )

        mappings = []
        for record in result.get("nodes", []):
            if record.get("fieldPath"):
                mapping = DataMapping(
                    ui_field=record.get("fieldPath", ""),
                    entity_field=record.get("fieldName", ""),
                    is_required=record.get("required", False),
                    validation_rules=record.get("validationAttributes", []),
                )
                mappings.append(mapping)

        return mappings

    def _group_steps_by_layer(
        self,
        steps: list[FlowStep],
    ) -> dict[str, list[FlowStep]]:
        """Group flow steps by architectural layer."""
        layers: dict[str, list[FlowStep]] = {
            "ui": [],
            "flow": [],
            "controller": [],
            "service": [],
            "dao": [],
            "database": [],
        }

        for step in steps:
            layer_key = step.layer.value.lower()
            if layer_key in layers:
                layers[layer_key].append(step)

        return layers

    async def _get_business_rules_for_component(
        self,
        component_name: str,
    ) -> list[str]:
        """Get business rules associated with a component.

        Args:
            component_name: Name of the component

        Returns:
            List of business rule descriptions
        """
        try:
            result = await self.neo4j.query_code_structure(
                flow_queries.GET_BUSINESS_RULES_FOR_COMPONENT,
                {"componentId": component_name, "componentName": component_name},
            )

            rules = []
            for record in result.get("nodes", []):
                # Extract business rules
                for rule in record.get("businessRules", []):
                    if rule.get("ruleName"):
                        rule_desc = f"{rule.get('ruleType', 'Rule')}: {rule.get('ruleName')}"
                        if rule.get("description"):
                            rule_desc += f" - {rule['description']}"
                        rules.append(rule_desc)

                # Extract method validations
                for val in record.get("methodValidations", []):
                    if val.get("ruleName"):
                        rules.append(f"Validation: {val['ruleName']}")

                # Extract field validations
                for field in record.get("fieldValidations", []):
                    if field.get("validations"):
                        for v in field.get("validations", []):
                            rules.append(f"@{v} on {field.get('fieldName', 'field')}")

            return list(set(rules))  # Deduplicate

        except Exception as e:
            logger.debug(f"Could not get business rules for {component_name}: {e}")
            return []

    async def enrich_flow_with_validations(
        self,
        flow: FeatureFlow,
    ) -> FeatureFlow:
        """Enrich a feature flow with validation information.

        Args:
            flow: FeatureFlow to enrich

        Returns:
            Enriched FeatureFlow with validations_applied populated
        """
        for step in flow.flow_steps:
            # Get business rules for this component
            rules = await self._get_business_rules_for_component(step.component_name)
            step.validations_applied = rules

            # Infer operation type from method name
            if step.method_name:
                method_lower = step.method_name.lower()
                if any(kw in method_lower for kw in ["get", "find", "search", "load", "read"]):
                    step.operation_type = "read"
                elif any(kw in method_lower for kw in ["save", "create", "insert", "add", "persist"]):
                    step.operation_type = "write"
                elif any(kw in method_lower for kw in ["update", "modify", "edit"]):
                    step.operation_type = "write"
                elif any(kw in method_lower for kw in ["delete", "remove"]):
                    step.operation_type = "write"
                elif any(kw in method_lower for kw in ["validate", "check", "verify"]):
                    step.operation_type = "validate"
                elif any(kw in method_lower for kw in ["build", "convert", "transform", "map"]):
                    step.operation_type = "transform"

        return flow

    async def get_data_model_info(
        self,
        entity_pattern: str,
    ) -> list[dict]:
        """Get data model information for entities matching a pattern.

        Args:
            entity_pattern: Pattern to match entity names

        Returns:
            List of entity information dictionaries
        """
        try:
            result = await self.neo4j.query_code_structure(
                flow_queries.GET_DATA_MODEL_INFO,
                {"entityPattern": entity_pattern},
            )

            entities = []
            for record in result.get("nodes", []):
                entity_info = {
                    "name": record.get("entityName"),
                    "file_path": record.get("entityPath"),
                    "annotations": record.get("entityAnnotations", []),
                    "fields": record.get("fields", []),
                    "relationships": record.get("relationships", []),
                }
                entities.append(entity_info)

            return entities

        except Exception as e:
            logger.error(f"Data model extraction failed: {e}")
            return []
