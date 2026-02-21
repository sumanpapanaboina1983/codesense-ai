"""Enhanced Context Retrieval using Graph-Based Traversal.

This module implements COMPOUND TERM DETECTION and GRAPH-BASED TRAVERSAL
for finding truly relevant code components for a feature.

Key improvements over keyword-based search:
1. Extracts compound terms (e.g., "Legal Entity" -> "legalentity")
2. Finds entry points (Controllers/Actions) first
3. Traverses dependency graph from entry points
4. Eliminates false positives from loose keyword matching

Usage:
    from brd_generator.core.enhanced_context import EnhancedContextRetriever

    retriever = EnhancedContextRetriever(neo4j_client)
    components, entry_points, warnings = await retriever.get_relevant_context(
        "Legal Entity Maintenance"
    )
"""

from __future__ import annotations

from typing import Any, Optional
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Prefix for all enhanced context logs - easy to grep
LOG_PREFIX = "[ENHANCED-CONTEXT]"


def extract_compound_terms(keywords: list[str]) -> tuple[str, list[str]]:
    """
    Extract compound terms from keywords.

    "Legal Entity Maintenance" -> compound="legalentity", actions=["maintenance"]

    Logic: Consecutive words before common action words form the compound subject.
    This is the key to eliminating false positives.

    Args:
        keywords: List of keywords from feature description

    Returns:
        Tuple of (compound_term, action_words)
    """
    action_words = {
        'maintenance', 'search', 'create', 'update', 'delete', 'merge',
        'wizard', 'inquiry', 'report', 'list', 'view', 'edit', 'add',
        'replace', 'contact', 'history', 'status', 'detail', 'summary',
        'lookup', 'entry', 'results', 'conflicts', 'process', 'manage',
        'import', 'export', 'validate', 'verify', 'approve', 'reject'
    }

    subject_parts = []
    action_parts = []

    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in action_words:
            action_parts.append(kw_lower)
        else:
            subject_parts.append(kw_lower)

    # Compound term is all subject parts joined
    compound_term = ''.join(subject_parts) if subject_parts else ''

    logger.info(f"{LOG_PREFIX} Compound term extraction: '{' '.join(keywords)}' -> compound='{compound_term}', actions={action_parts}")

    return compound_term, action_parts


class EnhancedContextRetriever:
    """
    Enhanced context retrieval using graph-based traversal.

    This class provides the COMPOUND TERM DETECTION + TRAVERSAL-BASED approach
    that eliminates false positives and finds truly relevant components.
    """

    def __init__(self, neo4j_client):
        """
        Initialize the enhanced context retriever.

        Args:
            neo4j_client: Neo4j MCP client for executing queries
        """
        self.neo4j = neo4j_client
        logger.info(f"{LOG_PREFIX} Initialized EnhancedContextRetriever")

    async def get_relevant_context(
        self,
        feature_description: str,
        max_entry_points: int = 20,
        max_components: int = 100,
    ) -> tuple[list[dict], list[str], list[str]]:
        """
        Get relevant context using graph-based traversal.

        This approach:
        1. Extracts compound term from feature description
        2. Finds entry points (Actions/Controllers) matching the compound term
        3. Traverses the dependency graph from those entry points
        4. Returns only components that are actually connected

        Args:
            feature_description: Description of the feature
            max_entry_points: Maximum entry points to find
            max_components: Maximum total components to return

        Returns:
            Tuple of (components, entry_point_names, warnings)
        """
        logger.info(f"{LOG_PREFIX} ========================================")
        logger.info(f"{LOG_PREFIX} Starting ENHANCED context retrieval")
        logger.info(f"{LOG_PREFIX} Feature: {feature_description[:80]}...")
        logger.info(f"{LOG_PREFIX} ========================================")

        warnings = []

        # Extract keywords
        keywords = [w for w in feature_description.split() if len(w) > 2][:8]

        if not keywords:
            warnings.append("No keywords extracted from feature description")
            logger.warning(f"{LOG_PREFIX} No keywords extracted")
            return [], [], warnings

        logger.info(f"{LOG_PREFIX} Keywords: {keywords}")

        # =====================================================================
        # NEW: Try menu-based lookup FIRST (Phase 1: Menu & Screen Indexing)
        # This is the most accurate method - uses user-facing menu labels
        # =====================================================================
        menu_result = await self._find_entry_points_by_menu(feature_description, max_entry_points)

        if menu_result.get("found"):
            logger.info(f"{LOG_PREFIX} [MENU-BASED] Found menu match: {menu_result.get('menuLabel')}")
            entry_points = menu_result.get("entry_points", [])
            sub_features = menu_result.get("sub_features", [])
            warnings.insert(0, f"Menu match: '{menu_result.get('menuLabel')}' -> {len(sub_features)} sub-features")
        else:
            logger.info(f"{LOG_PREFIX} [MENU-BASED] No menu match, falling back to compound term detection")
            # Step 1: Find entry points using compound term detection (original approach)
            entry_points = await self._find_entry_points(keywords, max_entry_points)

        if not entry_points:
            warnings.append(f"No entry points found for keywords: {keywords}")
            logger.warning(f"{LOG_PREFIX} No entry points found - falling back")
            return [], [], warnings

        # Group entry points by layer
        ui_entry_points = [ep for ep in entry_points if ep.get("layer") == "ui"]
        flow_entry_points = [ep for ep in entry_points if ep.get("layer") == "flow"]
        controller_entry_points = [ep for ep in entry_points if ep.get("layer") == "controller"]

        logger.info(f"{LOG_PREFIX} Entry points found: UI={len(ui_entry_points)}, Flow={len(flow_entry_points)}, Controller={len(controller_entry_points)}")

        # Use controller entry points for traversal (they have richest relationships)
        traversal_entry_names = [ep.get("name") for ep in controller_entry_points if ep.get("name")]
        if not traversal_entry_names:
            traversal_entry_names = [ep.get("name") for ep in flow_entry_points if ep.get("name")]

        entry_point_names = [ep.get("name") for ep in entry_points if ep.get("name")]

        # Step 2: Traverse from entry points
        traversal_result = await self._traverse_dependencies(
            traversal_entry_names,
            keywords=keywords,
            max_components=max_components
        )

        # Step 3: Combine entry points with traversed nodes
        all_nodes = []
        seen_names = set()

        # Add entry points first (they're the most relevant)
        for ep in entry_points:
            name = ep.get("name")
            if name and name not in seen_names:
                all_nodes.append({
                    "name": name,
                    "type": ep.get("type", "unknown"),
                    "path": ep.get("path", ""),
                    "description": "Entry point for feature",
                    "distance": 0,
                    "is_entry_point": True,
                    "layer": ep.get("layer", "unknown"),
                })
                seen_names.add(name)

        # Add traversed nodes
        for node in traversal_result.get("nodes", []):
            name = node.get("name")
            if name and name not in seen_names:
                all_nodes.append({
                    "name": name,
                    "type": node.get("type", "unknown"),
                    "path": node.get("path", ""),
                    "description": node.get("description", ""),
                    "distance": node.get("distance", 1),
                    "is_entry_point": False,
                    "layer": self._determine_layer(node.get("type", ""), name),
                })
                seen_names.add(name)

        logger.info(f"{LOG_PREFIX} ========================================")
        logger.info(f"{LOG_PREFIX} ENHANCED context retrieval COMPLETE")
        logger.info(f"{LOG_PREFIX} Total components: {len(all_nodes)}")
        logger.info(f"{LOG_PREFIX} Entry points: {len(entry_points)}")
        logger.info(f"{LOG_PREFIX} Traversed nodes: {len(traversal_result.get('nodes', []))}")
        logger.info(f"{LOG_PREFIX} ========================================")

        # Build entry point summary
        entry_point_summary = []
        if ui_entry_points:
            entry_point_summary.append(f"UI: {len(ui_entry_points)} JSP pages")
        if flow_entry_points:
            entry_point_summary.append(f"Flow: {len(flow_entry_points)} WebFlows")
        if controller_entry_points:
            controller_names = [ep.get("name") for ep in controller_entry_points[:3]]
            entry_point_summary.append(f"Controllers: {', '.join(controller_names)}")

        if entry_point_summary:
            warnings.insert(0, f"Entry points by layer: {' | '.join(entry_point_summary)}")

        return all_nodes, entry_point_names, warnings

    # =========================================================================
    # Phase 1: Menu-Based Entry Point Discovery
    # =========================================================================

    async def _find_entry_points_by_menu(
        self,
        feature_description: str,
        max_entry_points: int = 20,
    ) -> dict:
        """
        Find entry points by matching against menu item labels.

        This is the most accurate method - uses user-facing menu labels
        that directly map to screens, actions, and code.

        Args:
            feature_description: The feature description (e.g., "Point Maintenance")
            max_entry_points: Maximum entry points to return

        Returns:
            Dict with keys: found, menuLabel, entry_points, sub_features
        """
        search_term = feature_description.lower().strip()

        # Build a fuzzy search pattern
        # "Point Maintenance" -> matches "Point Maintenance", "Point Info Maintenance", etc.
        search_words = search_term.split()
        fuzzy_pattern = '.*'.join(search_words)

        menu_query = f"""
            // Find menu items matching the search term
            MATCH (m:MenuItem)
            WHERE toLower(m.label) CONTAINS '{search_term}'
               OR toLower(m.label) =~ '.*{fuzzy_pattern}.*'
               OR toLower(m.name) CONTAINS '{search_term}'

            // Follow menu -> screen -> action chain
            OPTIONAL MATCH (m)-[:MENU_OPENS_SCREEN]->(s:Screen)
            OPTIONAL MATCH (s)-[:SCREEN_CALLS_ACTION]->(a:JavaClass)
            OPTIONAL MATCH (s)-[:SCREEN_RENDERS_JSP]->(j:JSPPage)
            OPTIONAL MATCH (m)-[:MENU_OPENS_FLOW]->(f:WebFlowDefinition)

            // Get all screens in the same flow for sub-features
            OPTIONAL MATCH (f)-[:FLOW_DEFINES_STATE]->(fs:FlowState)
            WHERE fs.stateType = 'view-state'

            RETURN m.label AS menuLabel,
                   m.url AS menuUrl,
                   m.parentMenu AS parentMenu,
                   m.flowId AS flowId,
                   m.viewStateId AS viewStateId,
                   s.screenId AS screenId,
                   s.title AS screenTitle,
                   s.actionClass AS actionClass,
                   s.actionMethods AS actionMethods,
                   collect(DISTINCT a.name) AS actionClasses,
                   collect(DISTINCT j.name) AS jspPages,
                   f.name AS flowName,
                   collect(DISTINCT fs.stateId) AS flowStates
            ORDER BY
                CASE WHEN toLower(m.label) = '{search_term}' THEN 0 ELSE 1 END,
                m.menuLevel
            LIMIT {max_entry_points}
        """

        try:
            result = await self.neo4j.query_code_structure(menu_query)
            menu_items = result.get("nodes", [])

            if not menu_items:
                logger.debug(f"{LOG_PREFIX} [MENU-BASED] No menu items found for '{search_term}'")
                return {"found": False}

            # Process the first (best) match
            best_match = menu_items[0]
            menu_label = best_match.get("menuLabel", "")
            flow_id = best_match.get("flowId", "")

            logger.info(f"{LOG_PREFIX} [MENU-BASED] Best match: '{menu_label}' -> flow={flow_id}")

            # Build entry points from menu match
            entry_points = []

            # Add screen as entry point
            if best_match.get("screenId"):
                entry_points.append({
                    "name": best_match.get("screenId"),
                    "type": "Screen",
                    "path": "",
                    "layer": "ui",
                    "layer_score": 100,
                    "title": best_match.get("screenTitle", ""),
                    "is_menu_match": True,
                })

            # Add action classes as entry points
            action_classes = best_match.get("actionClasses", [])
            action_class = best_match.get("actionClass")
            if action_class and action_class not in action_classes:
                action_classes.append(action_class)

            for ac in action_classes:
                if ac:
                    entry_points.append({
                        "name": ac,
                        "type": "JavaClass",
                        "path": "",
                        "layer": "controller",
                        "layer_score": 80,
                        "is_menu_match": True,
                    })

            # Add flow as entry point
            flow_name = best_match.get("flowName")
            if flow_name:
                entry_points.append({
                    "name": flow_name,
                    "type": "WebFlowDefinition",
                    "path": "",
                    "layer": "flow",
                    "layer_score": 90,
                    "is_menu_match": True,
                })

            # Get sub-features (other screens in the same flow)
            sub_features = await self._get_sub_features(flow_id)

            return {
                "found": True,
                "menuLabel": menu_label,
                "menuUrl": best_match.get("menuUrl", ""),
                "flowId": flow_id,
                "entry_points": entry_points,
                "sub_features": sub_features,
                "actionMethods": best_match.get("actionMethods", []),
            }

        except Exception as e:
            logger.warning(f"{LOG_PREFIX} [MENU-BASED] Menu query failed: {e}")
            return {"found": False}

    async def _get_sub_features(self, flow_id: str) -> list[dict]:
        """
        Get all sub-features (screens) for a given flow.

        Args:
            flow_id: The flow ID (e.g., "pointWizard")

        Returns:
            List of sub-feature dicts with screenId, title, actionClass, methods, jsps
        """
        if not flow_id:
            return []

        sub_feature_query = f"""
            MATCH (s:Screen)
            WHERE s.flowId = '{flow_id}'

            OPTIONAL MATCH (s)-[:SCREEN_CALLS_ACTION]->(a:JavaClass)
            OPTIONAL MATCH (s)-[:SCREEN_RENDERS_JSP]->(j:JSPPage)

            RETURN s.screenId AS screenId,
                   s.title AS title,
                   s.screenType AS screenType,
                   s.actionClass AS actionClass,
                   s.actionMethods AS actionMethods,
                   s.urlPattern AS urlPattern,
                   s.isMaintenanceMode AS isMaintenanceMode,
                   collect(DISTINCT j.name) AS jsps,
                   a.name AS linkedActionClass
            ORDER BY s.screenId
        """

        try:
            result = await self.neo4j.query_code_structure(sub_feature_query)
            sub_features = result.get("nodes", [])

            logger.info(f"{LOG_PREFIX} [MENU-BASED] Found {len(sub_features)} sub-features for flow '{flow_id}'")

            # Format sub-features
            formatted = []
            for sf in sub_features:
                formatted.append({
                    "screenId": sf.get("screenId"),
                    "title": sf.get("title", sf.get("screenId")),
                    "screenType": sf.get("screenType", "unknown"),
                    "actionClass": sf.get("actionClass") or sf.get("linkedActionClass"),
                    "actionMethods": sf.get("actionMethods", []),
                    "urlPattern": sf.get("urlPattern", f"{flow_id}.html?pageSelect={sf.get('screenId')}"),
                    "jsps": sf.get("jsps", []),
                    "isMaintenanceMode": sf.get("isMaintenanceMode", False),
                })

            return formatted

        except Exception as e:
            logger.warning(f"{LOG_PREFIX} [MENU-BASED] Sub-feature query failed: {e}")
            return []

    # =========================================================================
    # Phase 5: Cross-Feature Analysis
    # =========================================================================

    async def get_cross_feature_dependencies(self, flow_id: str) -> dict:
        """
        Get comprehensive cross-feature dependencies for a flow.

        This finds other features that:
        - Share entities (data coupling)
        - Share services (service coupling)
        - Have cascade effects
        - Are triggered by common events

        Args:
            flow_id: The flow ID

        Returns:
            Dict with cross-feature relationships
        """
        all_cross_features = []

        # Query 1: Shared entities
        shared_entity_query = f"""
            MATCH (s:Screen {{flowId: '{flow_id}'}})
            OPTIONAL MATCH (s)-[:SCREEN_CALLS_ACTION]->()-[:USES|CALLS*1..3]->(entity:JavaClass)
            WHERE entity.name ENDS WITH 'Entity' OR entity.name ENDS WITH 'Model'
              OR entity.name ENDS WITH 'DTO'

            WITH entity
            WHERE entity IS NOT NULL

            MATCH (other:Screen)-[:SCREEN_CALLS_ACTION]->()-[:USES|CALLS*1..3]->(entity)
            WHERE other.flowId <> '{flow_id}'

            RETURN DISTINCT other.flowId AS relatedFlow,
                   other.screenId AS relatedScreen,
                   other.title AS relatedTitle,
                   entity.name AS sharedComponent,
                   'SHARES_ENTITY' AS relationshipType,
                   'Changes to ' + entity.name + ' may affect this feature' AS implication
            LIMIT 500
        """

        # Query 2: Shared services
        shared_service_query = f"""
            MATCH (s:Screen {{flowId: '{flow_id}'}})
            OPTIONAL MATCH (s)-[:SCREEN_CALLS_ACTION]->()-[:CALLS|USES*1..2]->(service)
            WHERE (service:SpringService OR service:JavaClass)
              AND (
                toLower(service.name) CONTAINS 'service'
                OR toLower(service.name) CONTAINS 'validator'
              )

            WITH service
            WHERE service IS NOT NULL

            MATCH (other:Screen)-[:SCREEN_CALLS_ACTION]->()-[:CALLS|USES*1..2]->(service)
            WHERE other.flowId <> '{flow_id}'

            RETURN DISTINCT other.flowId AS relatedFlow,
                   other.screenId AS relatedScreen,
                   other.title AS relatedTitle,
                   service.name AS sharedComponent,
                   'SHARES_SERVICE' AS relationshipType,
                   'Both features depend on ' + service.name AS implication
            LIMIT 500
        """

        # Query 3: Menu hierarchy relationships
        menu_relation_query = f"""
            MATCH (m1:MenuItem)-[:MENU_OPENS_SCREEN|MENU_OPENS_FLOW]->(:Screen {{flowId: '{flow_id}'}})
            MATCH (m2:MenuItem)-[:PARENT_MENU_ITEM*1..2]-(m1)
            MATCH (m2)-[:MENU_OPENS_SCREEN]->(s2:Screen)
            WHERE s2.flowId <> '{flow_id}'

            RETURN DISTINCT s2.flowId AS relatedFlow,
                   s2.screenId AS relatedScreen,
                   s2.title AS relatedTitle,
                   m2.label AS sharedComponent,
                   'SIBLING_FEATURE' AS relationshipType,
                   'Part of same menu group: ' + m1.parentMenu AS implication
            LIMIT 500
        """

        queries = [
            (shared_entity_query, "shared_entity"),
            (shared_service_query, "shared_service"),
            (menu_relation_query, "menu_sibling"),
        ]

        for query, query_type in queries:
            try:
                result = await self.neo4j.query_code_structure(query)
                features = result.get("nodes", [])
                logger.debug(f"{LOG_PREFIX} [CROSS-FEATURE] {query_type}: found {len(features)} relationships")
                all_cross_features.extend(features)
            except Exception as e:
                logger.warning(f"{LOG_PREFIX} [CROSS-FEATURE] {query_type} query failed: {e}")

        # Deduplicate by relatedFlow + relatedScreen
        seen = set()
        unique_features = []
        for feat in all_cross_features:
            key = f"{feat.get('relatedFlow')}:{feat.get('relatedScreen')}"
            if key not in seen:
                seen.add(key)
                unique_features.append(feat)

        logger.info(f"{LOG_PREFIX} [CROSS-FEATURE] Found {len(unique_features)} cross-feature relationships for {flow_id}")

        return {
            "flowId": flow_id,
            "crossFeatures": unique_features,
            "count": len(unique_features),
            "byType": {
                "sharedEntity": len([f for f in unique_features if f.get("relationshipType") == "SHARES_ENTITY"]),
                "sharedService": len([f for f in unique_features if f.get("relationshipType") == "SHARES_SERVICE"]),
                "siblingFeature": len([f for f in unique_features if f.get("relationshipType") == "SIBLING_FEATURE"]),
            }
        }

    async def get_feature_impact_analysis(
        self,
        component_name: str,
        component_type: str = "entity",
    ) -> dict:
        """
        Analyze the impact of changing a component on all features.

        Args:
            component_name: Name of the component (entity, service, etc.)
            component_type: Type of component (entity, service, validator)

        Returns:
            Dict with impact analysis
        """
        logger.info(f"{LOG_PREFIX} [IMPACT] Analyzing impact of {component_type}: {component_name}")

        # Find all features affected by this component
        impact_query = f"""
            MATCH (component:JavaClass)
            WHERE toLower(component.name) = toLower('{component_name}')
               OR component.name = '{component_name}'

            // Find screens that use this component
            MATCH (screen:Screen)-[:SCREEN_CALLS_ACTION]->()-[*1..4]->(component)

            RETURN DISTINCT screen.flowId AS flowId,
                   screen.screenId AS screenId,
                   screen.title AS title,
                   screen.actionClass AS actionClass
            ORDER BY screen.flowId
            LIMIT 150
        """

        affected_features = []
        try:
            result = await self.neo4j.query_code_structure(impact_query)
            affected_features = result.get("nodes", [])
            logger.info(f"{LOG_PREFIX} [IMPACT] Found {len(affected_features)} affected features")

        except Exception as e:
            logger.warning(f"{LOG_PREFIX} [IMPACT] Query failed: {e}")

        return {
            "component": component_name,
            "componentType": component_type,
            "affectedFeatures": affected_features,
            "totalAffected": len(affected_features),
            "impactLevel": self._calculate_impact_level(len(affected_features)),
        }

    def _calculate_impact_level(self, affected_count: int) -> str:
        """Calculate impact level based on number of affected features."""
        if affected_count == 0:
            return "none"
        elif affected_count <= 2:
            return "low"
        elif affected_count <= 5:
            return "medium"
        elif affected_count <= 10:
            return "high"
        else:
            return "critical"

    async def _find_entry_points(
        self,
        keywords: list[str],
        max_entry_points: int = 20,
    ) -> list[dict]:
        """
        Find entry points using COMPOUND TERM DETECTION + TRAVERSAL-BASED UI DISCOVERY.

        Approach:
        1. Extract compound term from keywords (e.g., "Legal Entity" -> "legalentity")
        2. Find Controller entry points that match the compound term
        3. Traverse from Controllers to find connected WebFlows and JSPs
        4. This eliminates false positives (e.g., pointMaintenance when searching legalEntityMaintenance)
        """
        if not keywords:
            return []

        all_entry_points = []
        seen_names = set()

        # Extract compound term and action words
        compound_term, action_words = extract_compound_terms(keywords)
        logger.info(f"{LOG_PREFIX} [ENTRY-POINTS] Compound term: '{compound_term}', Actions: {action_words}")

        # =================================================================
        # Step 1: Find Controller Entry Points (using compound term)
        # =================================================================

        if compound_term:
            compound_filter = f"toLower(n.name) CONTAINS '{compound_term}'"
            if action_words:
                score_boost = " + ".join([f"CASE WHEN toLower(n.name) CONTAINS '{aw}' THEN 10 ELSE 0 END" for aw in action_words])
            else:
                score_boost = "0"
        else:
            # Fallback to OR logic if no compound term
            compound_filter = " OR ".join([f"toLower(n.name) CONTAINS '{kw.lower()}'" for kw in keywords])
            score_boost = "0"

        controller_query = f"""
            MATCH (n)
            WHERE (n:SpringService OR n:JavaClass OR n:SpringController)
              AND ({compound_filter})
              AND (
                toLower(n.name) ENDS WITH 'action'
                OR toLower(n.name) ENDS WITH 'controller'
              )
              AND NOT toLower(n.name) CONTAINS 'test'
            WITH n,
                 ({score_boost}) AS action_score,
                 COALESCE(n.pageRank, 0.1) AS pagerank
            RETURN n.name AS name,
                   labels(n)[0] AS type,
                   n.filePath AS path,
                   'controller' AS layer,
                   80 AS layer_score,
                   action_score + pagerank * 10 AS relevance_score
            ORDER BY relevance_score DESC
            LIMIT 500
        """

        try:
            result = await self.neo4j.query_code_structure(controller_query)
            controllers = result.get("nodes", [])
            logger.info(f"{LOG_PREFIX} [ENTRY-POINTS] Found {len(controllers)} controllers with compound term '{compound_term}'")

            for node in controllers:
                name = node.get("name")
                if name and name not in seen_names:
                    all_entry_points.append(node)
                    seen_names.add(name)
                    logger.debug(f"{LOG_PREFIX} [ENTRY-POINTS]   + Controller: {name}")
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} [ENTRY-POINTS] Controller query failed: {e}")
            controllers = []

        # =================================================================
        # Step 2: Find WebFlows CONNECTED to the Controllers
        # =================================================================

        if controllers:
            controller_names = [c.get("name") for c in controllers[:5] if c.get("name")]
            webflow_patterns = []
            for cn in controller_names:
                base = cn.replace("Action", "").replace("Controller", "")
                webflow_patterns.append(f"toLower(w.name) CONTAINS toLower('{base}')")

            webflow_filter = " OR ".join(webflow_patterns) if webflow_patterns else "false"

            webflow_query = f"""
                MATCH (w:WebFlowDefinition)
                WHERE {webflow_filter}
                RETURN w.name AS name,
                       'WebFlowDefinition' AS type,
                       w.filePath AS path,
                       'flow' AS layer,
                       90 AS layer_score
                LIMIT 500
            """

            try:
                result = await self.neo4j.query_code_structure(webflow_query)
                webflows = result.get("nodes", [])
                logger.info(f"{LOG_PREFIX} [ENTRY-POINTS] Found {len(webflows)} WebFlows connected to controllers")

                for node in webflows:
                    name = node.get("name")
                    if name and name not in seen_names:
                        all_entry_points.append(node)
                        seen_names.add(name)
                        logger.debug(f"{LOG_PREFIX} [ENTRY-POINTS]   + WebFlow: {name}")
            except Exception as e:
                logger.warning(f"{LOG_PREFIX} [ENTRY-POINTS] WebFlow query failed: {e}")

        # =================================================================
        # Step 3: Find JSPs CONNECTED to the Controllers/WebFlows
        # =================================================================

        if controllers and compound_term:
            controller_names = [c.get("name") for c in controllers[:5] if c.get("name")]

            jsp_patterns = []
            for cn in controller_names:
                base = cn.replace("Action", "").replace("Controller", "")
                jsp_patterns.append(f"toLower(j.name) STARTS WITH toLower('{base}')")

            # Also require compound term to be in JSP name
            jsp_patterns.append(f"toLower(j.name) CONTAINS '{compound_term}'")

            jsp_filter = " OR ".join(list(set(jsp_patterns))) if jsp_patterns else "false"

            if action_words:
                action_bonus = " OR ".join([f"toLower(j.name) CONTAINS '{aw}'" for aw in action_words])
                jsp_query = f"""
                    MATCH (j:JSPPage)
                    WHERE ({jsp_filter})
                    WITH j,
                         CASE WHEN toLower(j.name) CONTAINS '{compound_term}' THEN 20 ELSE 0 END +
                         CASE WHEN {action_bonus} THEN 10 ELSE 0 END AS relevance
                    WHERE relevance >= 20
                    RETURN j.name AS name,
                           'JSPPage' AS type,
                           j.filePath AS path,
                           'ui' AS layer,
                           100 AS layer_score,
                           relevance
                    ORDER BY relevance DESC
                    LIMIT 500
                """
            else:
                jsp_query = f"""
                    MATCH (j:JSPPage)
                    WHERE {jsp_filter}
                    RETURN j.name AS name,
                           'JSPPage' AS type,
                           j.filePath AS path,
                           'ui' AS layer,
                           100 AS layer_score
                    LIMIT 500
                """

            try:
                result = await self.neo4j.query_code_structure(jsp_query)
                jsps = result.get("nodes", [])
                logger.info(f"{LOG_PREFIX} [ENTRY-POINTS] Found {len(jsps)} JSPs connected to controllers")

                for node in jsps:
                    name = node.get("name")
                    if name and name not in seen_names:
                        all_entry_points.append(node)
                        seen_names.add(name)
                        logger.debug(f"{LOG_PREFIX} [ENTRY-POINTS]   + JSP: {name}")
            except Exception as e:
                logger.warning(f"{LOG_PREFIX} [ENTRY-POINTS] JSP query failed: {e}")

        # Sort by layer_score (UI first, then flow, then controller)
        all_entry_points.sort(key=lambda x: x.get("layer_score", 0), reverse=True)

        logger.info(f"{LOG_PREFIX} [ENTRY-POINTS] Total: {len(all_entry_points)} entry points")
        for ep in all_entry_points[:5]:
            logger.info(f"{LOG_PREFIX} [ENTRY-POINTS]   - {ep.get('name')} ({ep.get('type')}) layer={ep.get('layer')}")

        return all_entry_points[:max_entry_points]

    async def _traverse_dependencies(
        self,
        entry_points: list[str],
        keywords: list[str] = None,
        max_components: int = 100,
    ) -> dict:
        """
        Traverse the dependency graph from entry points to find all related components.

        This follows actual code relationships:
        - Method calls (HAS_METHOD, CALLS)
        - Field access (HAS_FIELD, USES)
        - Inheritance (EXTENDS, IMPLEMENTS)
        - Imports (JAVA_IMPORTS)
        - WebFlow transitions (FLOW_TRANSITIONS_TO, FLOW_EXECUTES_ACTION)
        - DAOs/Repositories in persistence layer
        """
        keywords = keywords or []
        if not entry_points:
            return {"nodes": [], "edges": []}

        logger.info(f"{LOG_PREFIX} [TRAVERSE] Starting traversal from {len(entry_points)} entry points")

        # Build entry point filter
        safe_entry_points = [ep.replace("'", "\\'") for ep in entry_points[:5]]
        entry_filter = " OR ".join([f"start.name = '{name}'" for name in safe_entry_points])

        all_nodes = []
        seen_names = set()

        # Define queries to run
        queries = self._build_traversal_queries(entry_filter, safe_entry_points, keywords)

        for query, label in queries:
            try:
                result = await self.neo4j.query_code_structure(query)
                nodes = result.get("nodes", [])
                logger.info(f"{LOG_PREFIX} [TRAVERSE-{label}] Found {len(nodes)} nodes")

                for node in nodes:
                    name = node.get("name")
                    if name and name not in seen_names and len(all_nodes) < max_components:
                        all_nodes.append(node)
                        seen_names.add(name)
            except Exception as e:
                logger.warning(f"{LOG_PREFIX} [TRAVERSE-{label}] Query failed: {e}")

        logger.info(f"{LOG_PREFIX} [TRAVERSE] Total: {len(all_nodes)} connected components")
        return {"nodes": all_nodes, "entry_points": entry_points}

    def _build_traversal_queries(
        self,
        entry_filter: str,
        entry_points: list[str],
        keywords: list[str],
    ) -> list[tuple[str, str]]:
        """Build the list of traversal queries to execute."""

        queries = []

        # Query 1: Direct relationships (depth 1)
        query_depth1 = f"""
            MATCH (start)-[r]->(related)
            WHERE ({entry_filter})
              AND type(r) IN [
                'HAS_METHOD', 'HAS_FIELD', 'CALLS', 'USES', 'DEPENDS_ON',
                'EXTENDS', 'IMPLEMENTS', 'JAVA_IMPORTS',
                'FLOW_TRANSITIONS_TO', 'FLOW_EXECUTES_ACTION', 'FLOW_RENDERS_VIEW',
                'CONTAINS_FORM', 'INCLUDES_JSP', 'USES_TAGLIB',
                'BELONGS_TO', 'DEFINED_IN_MODULE', 'INSTANTIATES'
              ]
            RETURN DISTINCT related.name AS name,
                   labels(related)[0] AS type,
                   related.filePath AS path,
                   related.description AS description,
                   1 AS distance,
                   type(r) AS relationship
            LIMIT 500
        """
        queries.append((query_depth1, "depth1"))

        # Query 2: Two-hop relationships (depth 2)
        query_depth2 = f"""
            MATCH (start)-[r1]->(mid)-[r2]->(related)
            WHERE ({entry_filter})
              AND type(r1) IN ['HAS_METHOD', 'HAS_FIELD', 'CALLS', 'USES', 'DEPENDS_ON', 'EXTENDS', 'IMPLEMENTS', 'JAVA_IMPORTS']
              AND type(r2) IN ['HAS_METHOD', 'HAS_FIELD', 'CALLS', 'USES', 'DEPENDS_ON', 'EXTENDS', 'IMPLEMENTS', 'JAVA_IMPORTS', 'INSTANTIATES']
            RETURN DISTINCT related.name AS name,
                   labels(related)[0] AS type,
                   related.filePath AS path,
                   related.description AS description,
                   2 AS distance,
                   type(r2) AS relationship
            LIMIT 500
        """
        queries.append((query_depth2, "depth2"))

        # Query 3: Injected services (field name -> service name pattern)
        query_injected = f"""
            MATCH (start)-[:HAS_FIELD]->(field:JavaField)
            WHERE ({entry_filter})
            WITH field, toLower(field.name) AS field_name
            MATCH (service)
            WHERE (service:SpringService OR service:JavaClass OR service:JavaInterface)
              AND toLower(service.name) = field_name
            RETURN DISTINCT service.name AS name,
                   labels(service)[0] AS type,
                   service.filePath AS path,
                   'Injected service' AS description,
                   1 AS distance,
                   'INJECTED_SERVICE' AS relationship
            LIMIT 150
        """
        queries.append((query_injected, "injected"))

        # Query 4: Related services by naming pattern
        entry_base_names = [ep.replace("Action", "").replace("Controller", "").lower() for ep in entry_points[:3]]
        if entry_base_names:
            base_name_filter = " OR ".join([f"toLower(s.name) CONTAINS '{base}'" for base in entry_base_names])
            query_related = f"""
                MATCH (s)
                WHERE (s:SpringService OR s:JavaInterface)
                  AND ({base_name_filter})
                  AND NOT toLower(s.name) ENDS WITH 'action'
                  AND NOT toLower(s.name) ENDS WITH 'test'
                WITH DISTINCT s, COALESCE(s.pageRank, 0.0) AS rank
                ORDER BY rank DESC
                RETURN s.name AS name,
                       labels(s)[0] AS type,
                       s.filePath AS path,
                       s.description AS description,
                       2 AS distance,
                       'RELATED_BY_NAME' AS relationship
                LIMIT 500
            """
            queries.append((query_related, "related"))

        # Query 5: DAOs/Repositories
        if keywords:
            keyword_filter = " OR ".join([f"toLower(d.name) CONTAINS '{kw.lower()}'" for kw in keywords[:3]])
            query_daos = f"""
                MATCH (d)
                WHERE (d:SpringService OR d:JavaClass)
                  AND ({keyword_filter})
                  AND (toLower(d.name) CONTAINS 'dao' OR toLower(d.name) CONTAINS 'repository' OR toLower(d.name) CONTAINS 'mapper')
                  AND NOT toLower(d.name) ENDS WITH 'test'
                WITH DISTINCT d, COALESCE(d.pageRank, 0.0) AS rank
                ORDER BY rank DESC
                RETURN d.name AS name,
                       labels(d)[0] AS type,
                       d.filePath AS path,
                       'Data access layer' AS description,
                       3 AS distance,
                       'DATA_LAYER' AS relationship
                LIMIT 500
            """
            queries.append((query_daos, "daos"))

        # =================================================================
        # Phase 2: Deep Traversal Queries (4-6 hops)
        # =================================================================

        # Query 6: Deep chain traversal (up to 4 hops)
        query_deep_chain = f"""
            MATCH path = (start)-[*1..4]->(target)
            WHERE ({entry_filter})
              AND (target:JavaClass OR target:JavaInterface OR target:SpringService)
              AND NOT toLower(target.name) CONTAINS 'test'
              AND NOT target.name = start.name
            WITH DISTINCT target, length(path) AS distance
            ORDER BY distance
            RETURN target.name AS name,
                   labels(target)[0] AS type,
                   target.filePath AS path,
                   'Deep chain component' AS description,
                   distance,
                   'DEEP_CHAIN' AS relationship
            LIMIT 200
        """
        queries.append((query_deep_chain, "deep_chain"))

        # Query 7: Validators connected to entry points
        if entry_points:
            entry_base_names = [ep.replace("Action", "").replace("Controller", "").lower() for ep in entry_points[:3]]
            if entry_base_names:
                validator_filter = " OR ".join([f"toLower(v.name) CONTAINS '{base}'" for base in entry_base_names])
                query_validators = f"""
                    MATCH (v)
                    WHERE (v:JavaClass OR v:SpringService)
                      AND (toLower(v.name) CONTAINS 'validator' OR toLower(v.name) CONTAINS 'validation')
                      AND ({validator_filter})
                      AND NOT toLower(v.name) CONTAINS 'test'
                    RETURN DISTINCT v.name AS name,
                           labels(v)[0] AS type,
                           v.filePath AS path,
                           'Validation component' AS description,
                           2 AS distance,
                           'VALIDATOR' AS relationship
                    LIMIT 500
                """
                queries.append((query_validators, "validators"))

        # Query 8: Utility/Helper classes used by entry points
        query_utilities = f"""
            MATCH (start)-[*1..3]->(util)
            WHERE ({entry_filter})
              AND (util:JavaClass OR util:SpringService)
              AND (
                toLower(util.name) CONTAINS 'util'
                OR toLower(util.name) CONTAINS 'helper'
                OR toLower(util.name) CONTAINS 'converter'
                OR toLower(util.name) CONTAINS 'formatter'
                OR toLower(util.name) CONTAINS 'builder'
              )
              AND NOT toLower(util.name) CONTAINS 'test'
            RETURN DISTINCT util.name AS name,
                   labels(util)[0] AS type,
                   util.filePath AS path,
                   'Utility/Helper class' AS description,
                   3 AS distance,
                   'UTILITY' AS relationship
            LIMIT 500
        """
        queries.append((query_utilities, "utilities"))

        # Query 9: Entity classes used by services (for business rule extraction)
        query_entities = f"""
            MATCH (start)-[*1..4]->(entity)
            WHERE ({entry_filter})
              AND entity:JavaClass
              AND (
                toLower(entity.name) CONTAINS 'entity'
                OR toLower(entity.name) CONTAINS 'model'
                OR toLower(entity.name) CONTAINS 'dto'
                OR toLower(entity.name) CONTAINS 'vo'
              )
              AND NOT toLower(entity.name) CONTAINS 'test'
              AND NOT toLower(entity.name) CONTAINS 'builder'
            RETURN DISTINCT entity.name AS name,
                   labels(entity)[0] AS type,
                   entity.filePath AS path,
                   'Entity/Model class' AS description,
                   3 AS distance,
                   'ENTITY' AS relationship
            LIMIT 500
        """
        queries.append((query_entities, "entities"))

        return queries

    def _determine_layer(self, node_type: str, node_name: str) -> str:
        """Determine the architectural layer for a node."""
        type_lower = node_type.lower()
        name_lower = node_name.lower()

        if any(t in type_lower for t in ['jsp', 'jsppage']):
            return 'ui'
        if any(t in type_lower for t in ['webflow', 'flowdefinition']):
            return 'flow'
        if 'action' in name_lower or 'controller' in name_lower:
            return 'controller'
        if 'dao' in name_lower or 'repository' in name_lower:
            return 'data'
        if 'service' in name_lower or 'validator' in name_lower or 'builder' in name_lower:
            return 'service'
        return 'service'

    async def get_entity_details(
        self,
        keywords: list[str],
        max_entities: int = 20,
    ) -> list[dict]:
        """
        Get entity/model details including fields and validations.

        This extracts:
        - Entity names and their fields
        - Validation annotations (@NotNull, @Size, etc.)
        - Relationships between entities

        Args:
            keywords: Keywords to filter entities
            max_entities: Maximum entities to return

        Returns:
            List of entity details with fields
        """
        logger.info(f"{LOG_PREFIX} [ENTITIES] Starting entity extraction for keywords: {keywords}")

        if not keywords:
            return []

        # Extract compound term
        compound_term, _ = extract_compound_terms(keywords)

        # Build keyword filter
        if compound_term:
            keyword_filter = f"toLower(e.name) CONTAINS '{compound_term}'"
        else:
            keyword_filter = " OR ".join([f"toLower(e.name) CONTAINS '{kw.lower()}'" for kw in keywords[:3]])

        # Query for entities with their fields
        entity_query = f"""
            MATCH (e:JavaClass)
            WHERE ({keyword_filter})
              AND NOT toLower(e.name) CONTAINS 'test'
              AND NOT toLower(e.name) CONTAINS 'action'
              AND NOT toLower(e.name) CONTAINS 'controller'
              AND NOT toLower(e.name) CONTAINS 'service'
              AND NOT toLower(e.name) CONTAINS 'dao'
              AND NOT toLower(e.name) CONTAINS 'builder'
              AND NOT toLower(e.name) CONTAINS 'validator'
            OPTIONAL MATCH (e)-[:HAS_FIELD]->(f:JavaField)
            WITH e, collect(DISTINCT {{
                name: f.name,
                type: f.fieldType,
                annotations: f.annotations
            }}) AS fields
            RETURN e.name AS name,
                   e.filePath AS path,
                   labels(e)[0] AS type,
                   e.annotations AS annotations,
                   e.description AS description,
                   fields
            ORDER BY size(fields) DESC
            LIMIT {max_entities}
        """

        entities = []
        try:
            result = await self.neo4j.query_code_structure(entity_query)
            raw_entities = result.get("nodes", [])
            logger.info(f"{LOG_PREFIX} [ENTITIES] Found {len(raw_entities)} entities")

            for entity in raw_entities:
                fields = entity.get("fields", [])
                # Filter out null fields
                valid_fields = [f for f in fields if f.get("name")]

                entities.append({
                    "name": entity.get("name", ""),
                    "path": entity.get("path", ""),
                    "type": "Entity",
                    "annotations": entity.get("annotations", ""),
                    "description": entity.get("description", ""),
                    "fields": valid_fields,
                    "field_count": len(valid_fields),
                })

                if valid_fields:
                    logger.debug(f"{LOG_PREFIX} [ENTITIES]   - {entity.get('name')}: {len(valid_fields)} fields")

        except Exception as e:
            logger.warning(f"{LOG_PREFIX} [ENTITIES] Query failed: {e}")

        return entities

    # =========================================================================
    # Phase 3: Shared Component Detection
    # =========================================================================

    async def get_shared_components(
        self,
        feature_components: list[str],
        max_components: int = 30,
    ) -> list[dict]:
        """
        Find shared utilities and helpers used by feature components.

        This extracts:
        - Utility classes (Utils, Helper, Converter, Formatter)
        - Shared validators
        - Base/Abstract classes
        - Cross-cutting concerns

        Args:
            feature_components: List of component names from the feature
            max_components: Maximum shared components to return

        Returns:
            List of shared component details
        """
        logger.info(f"{LOG_PREFIX} [SHARED] Finding shared components for {len(feature_components)} feature components")

        if not feature_components:
            return []

        # Build component filter
        component_filter = " OR ".join([f"fc.name = '{c}'" for c in feature_components[:10]])

        shared_query = f"""
            // Start from feature's components
            MATCH (fc:JavaClass)
            WHERE {component_filter}

            // Find shared components they use (direct and 2-hop)
            MATCH (fc)-[:USES|CALLS|JAVA_IMPORTS|DEPENDS_ON*1..2]->(shared)
            WHERE (shared:JavaClass OR shared:SpringService OR shared:SharedComponent)
              AND (
                toLower(shared.name) CONTAINS 'util'
                OR toLower(shared.name) CONTAINS 'helper'
                OR toLower(shared.name) CONTAINS 'converter'
                OR toLower(shared.name) CONTAINS 'formatter'
                OR toLower(shared.name) CONTAINS 'constant'
                OR toLower(shared.name) CONTAINS 'common'
                OR shared.name STARTS WITH 'Base'
                OR shared.name STARTS WITH 'Abstract'
                OR toLower(shared.name) CONTAINS 'builder'
                OR toLower(shared.name) CONTAINS 'factory'
              )
              AND NOT toLower(shared.name) CONTAINS 'test'

            // Count usage across features
            WITH shared, count(DISTINCT fc) AS usageCount

            RETURN shared.name AS name,
                   labels(shared)[0] AS type,
                   shared.filePath AS path,
                   CASE
                     WHEN toLower(shared.name) CONTAINS 'util' THEN 'utility'
                     WHEN toLower(shared.name) CONTAINS 'helper' THEN 'helper'
                     WHEN toLower(shared.name) CONTAINS 'validator' THEN 'validator'
                     WHEN toLower(shared.name) CONTAINS 'converter' THEN 'converter'
                     WHEN toLower(shared.name) CONTAINS 'formatter' THEN 'formatter'
                     WHEN toLower(shared.name) CONTAINS 'constant' THEN 'constants'
                     WHEN shared.name STARTS WITH 'Base' THEN 'base'
                     WHEN shared.name STARTS WITH 'Abstract' THEN 'abstract'
                     ELSE 'utility'
                   END AS componentType,
                   usageCount
            ORDER BY usageCount DESC, shared.name
            LIMIT {max_components}
        """

        shared_components = []
        try:
            result = await self.neo4j.query_code_structure(shared_query)
            raw_components = result.get("nodes", [])
            logger.info(f"{LOG_PREFIX} [SHARED] Found {len(raw_components)} shared components")

            for comp in raw_components:
                shared_components.append({
                    "name": comp.get("name", ""),
                    "type": comp.get("type", "JavaClass"),
                    "path": comp.get("path", ""),
                    "componentType": comp.get("componentType", "utility"),
                    "usageCount": comp.get("usageCount", 1),
                    "description": f"Shared {comp.get('componentType', 'utility')} class",
                })
                logger.debug(f"{LOG_PREFIX} [SHARED]   + {comp.get('name')} ({comp.get('componentType')})")

        except Exception as e:
            logger.warning(f"{LOG_PREFIX} [SHARED] Query failed: {e}")

        return shared_components

    # =========================================================================
    # Phase 4: Business Rule Enrichment
    # =========================================================================

    async def get_enriched_business_rules(
        self,
        entry_points: list[str],
        feature_context: dict,
        max_rules: int = 50,
    ) -> list[dict]:
        """
        Get business rules enriched with feature context.

        This extracts:
        - Validation constraints (annotations)
        - Guard clauses (preconditions)
        - Business logic conditions
        - Error messages

        Args:
            entry_points: Entry point class names
            feature_context: Context dict with menuItem, screen, action
            max_rules: Maximum rules to return

        Returns:
            List of enriched business rules
        """
        logger.info(f"{LOG_PREFIX} [RULES] Extracting business rules for {len(entry_points)} entry points")

        if not entry_points:
            return []

        # Build entry point filter
        entry_filter = " OR ".join([f"toLower(start.name) = '{ep.lower()}'" for ep in entry_points[:5]])

        # Query for business rules connected to entry points
        rules_query = f"""
            // Find business rules from entry points
            MATCH (start)-[*1..4]->(rule)
            WHERE ({entry_filter})
              AND (
                rule:BusinessRule
                OR rule:ValidationConstraint
                OR rule:GuardClause
                OR rule:ConditionalBusinessLogic
              )

            RETURN DISTINCT rule.name AS name,
                   labels(rule)[0] AS ruleType,
                   rule.filePath AS path,
                   rule.condition AS condition,
                   rule.errorMessage AS errorMessage,
                   rule.targetName AS targetField,
                   rule.severity AS severity,
                   rule.confidence AS confidence,
                   rule.ruleText AS ruleText
            ORDER BY rule.confidence DESC
            LIMIT {max_rules}
        """

        rules = []
        try:
            result = await self.neo4j.query_code_structure(rules_query)
            raw_rules = result.get("nodes", [])
            logger.info(f"{LOG_PREFIX} [RULES] Found {len(raw_rules)} business rules")

            for rule in raw_rules:
                # Enrich with feature context
                enriched_rule = {
                    "name": rule.get("name", ""),
                    "ruleType": self._map_rule_type(rule.get("ruleType", "")),
                    "path": rule.get("path", ""),
                    "condition": rule.get("condition", ""),
                    "ruleText": rule.get("ruleText", rule.get("condition", "")),
                    "errorMessage": rule.get("errorMessage"),
                    "targetField": rule.get("targetField"),
                    "severity": rule.get("severity", "error"),
                    "confidence": rule.get("confidence", 0.8),
                    "featureContext": {
                        "menuItem": feature_context.get("menuItem"),
                        "screen": feature_context.get("screen"),
                        "action": feature_context.get("action"),
                    },
                    "triggeredBy": self._infer_triggers(feature_context.get("action", "")),
                }
                rules.append(enriched_rule)
                logger.debug(f"{LOG_PREFIX} [RULES]   + {rule.get('name')} ({rule.get('ruleType')})")

        except Exception as e:
            logger.warning(f"{LOG_PREFIX} [RULES] Query failed: {e}")

        # Also get entity validation annotations
        entity_validations = await self._get_entity_validations(entry_points)
        rules.extend(entity_validations)

        return rules

    async def _get_entity_validations(
        self,
        entry_points: list[str],
        max_validations: int = 30,
    ) -> list[dict]:
        """
        Extract validation annotations from entities used by entry points.
        """
        if not entry_points:
            return []

        entry_filter = " OR ".join([f"toLower(start.name) = '{ep.lower()}'" for ep in entry_points[:5]])

        validation_query = f"""
            // Find entities used by entry points
            MATCH (start)-[*1..4]->(entity:JavaClass)
            WHERE ({entry_filter})
              AND (
                toLower(entity.name) CONTAINS 'entity'
                OR toLower(entity.name) CONTAINS 'model'
                OR toLower(entity.name) CONTAINS 'dto'
              )
              AND NOT toLower(entity.name) CONTAINS 'test'

            // Get fields with validation annotations
            OPTIONAL MATCH (entity)-[:HAS_FIELD]->(field:JavaField)
            WHERE field.annotations IS NOT NULL
              AND (
                field.annotations CONTAINS '@NotNull'
                OR field.annotations CONTAINS '@NotEmpty'
                OR field.annotations CONTAINS '@Size'
                OR field.annotations CONTAINS '@Min'
                OR field.annotations CONTAINS '@Max'
                OR field.annotations CONTAINS '@Pattern'
                OR field.annotations CONTAINS '@Email'
                OR field.annotations CONTAINS '@Valid'
              )

            RETURN entity.name AS entityName,
                   field.name AS fieldName,
                   field.fieldType AS fieldType,
                   field.annotations AS annotations
            LIMIT {max_validations}
        """

        validations = []
        try:
            result = await self.neo4j.query_code_structure(validation_query)
            raw_validations = result.get("nodes", [])

            for val in raw_validations:
                annotations = val.get("annotations", "")
                if not annotations:
                    continue

                # Parse validation annotations
                parsed_rules = self._parse_validation_annotations(
                    annotations,
                    val.get("entityName", ""),
                    val.get("fieldName", ""),
                    val.get("fieldType", "")
                )
                validations.extend(parsed_rules)

            logger.info(f"{LOG_PREFIX} [RULES] Found {len(validations)} entity validations")

        except Exception as e:
            logger.warning(f"{LOG_PREFIX} [RULES] Entity validation query failed: {e}")

        return validations

    def _parse_validation_annotations(
        self,
        annotations: str,
        entity_name: str,
        field_name: str,
        field_type: str,
    ) -> list[dict]:
        """Parse validation annotations into rule dictionaries."""
        rules = []

        validation_patterns = [
            (r"@NotNull", "required", f"{field_name} is required"),
            (r"@NotEmpty", "required", f"{field_name} cannot be empty"),
            (r"@NotBlank", "required", f"{field_name} cannot be blank"),
            (r"@Size\s*\([^)]+\)", "length", f"{field_name} must meet size constraints"),
            (r"@Min\s*\([^)]+\)", "range", f"{field_name} minimum value constraint"),
            (r"@Max\s*\([^)]+\)", "range", f"{field_name} maximum value constraint"),
            (r"@Pattern\s*\([^)]+\)", "format", f"{field_name} must match pattern"),
            (r"@Email", "format", f"{field_name} must be a valid email"),
            (r"@Valid", "nested", f"{field_name} nested validation"),
        ]

        import re
        for pattern, rule_type, error_msg in validation_patterns:
            if re.search(pattern, annotations):
                rules.append({
                    "name": f"{entity_name}.{field_name}.{rule_type}",
                    "ruleType": "validation",
                    "path": "",
                    "condition": f"@{rule_type.title()} on {field_name}",
                    "ruleText": error_msg,
                    "errorMessage": error_msg,
                    "targetField": f"{entity_name}.{field_name}",
                    "severity": "error",
                    "confidence": 1.0,
                    "featureContext": {},
                    "triggeredBy": ["save", "update"],
                })

        return rules

    def _map_rule_type(self, rule_type: str) -> str:
        """Map Neo4j rule type label to standard type."""
        mapping = {
            "ValidationConstraint": "validation",
            "GuardClause": "guard",
            "ConditionalBusinessLogic": "condition",
            "BusinessRule": "business",
            "TestAssertion": "assertion",
        }
        return mapping.get(rule_type, "validation")

    def _infer_triggers(self, action: str) -> list[str]:
        """Infer what triggers a rule based on action name."""
        action_lower = action.lower() if action else ""
        triggers = []

        if "save" in action_lower or "create" in action_lower or "add" in action_lower:
            triggers.extend(["save", "create"])
        if "update" in action_lower or "edit" in action_lower or "modify" in action_lower:
            triggers.append("update")
        if "delete" in action_lower or "remove" in action_lower:
            triggers.append("delete")
        if "validate" in action_lower or "check" in action_lower:
            triggers.append("validate")

        return triggers if triggers else ["save", "update"]

    async def get_webflow_details(
        self,
        keywords: list[str],
        max_flows: int = 10,
    ) -> list[dict]:
        """
        Get WebFlow definitions with states and transitions.

        This extracts:
        - WebFlow names and paths
        - View states (JSP pages)
        - Action states (controller methods)
        - Transitions between states

        Args:
            keywords: Keywords to filter WebFlows
            max_flows: Maximum flows to return

        Returns:
            List of WebFlow details with states
        """
        logger.info(f"{LOG_PREFIX} [WEBFLOWS] Starting WebFlow extraction for keywords: {keywords}")

        if not keywords:
            return []

        compound_term, _ = extract_compound_terms(keywords)

        if compound_term:
            keyword_filter = f"toLower(w.name) CONTAINS '{compound_term}'"
        else:
            keyword_filter = " OR ".join([f"toLower(w.name) CONTAINS '{kw.lower()}'" for kw in keywords[:3]])

        # Query for WebFlows with their states
        webflow_query = f"""
            MATCH (w:WebFlowDefinition)
            WHERE {keyword_filter}
            OPTIONAL MATCH (w)-[:HAS_VIEW_STATE]->(v)
            OPTIONAL MATCH (w)-[:HAS_ACTION_STATE]->(a)
            OPTIONAL MATCH (w)-[:FLOW_TRANSITIONS_TO]->(t)
            WITH w,
                 collect(DISTINCT v.name) AS view_states,
                 collect(DISTINCT a.name) AS action_states,
                 collect(DISTINCT t.name) AS transitions
            RETURN w.name AS name,
                   w.filePath AS path,
                   'WebFlowDefinition' AS type,
                   view_states,
                   action_states,
                   transitions
            LIMIT {max_flows}
        """

        webflows = []
        try:
            result = await self.neo4j.query_code_structure(webflow_query)
            raw_flows = result.get("nodes", [])
            logger.info(f"{LOG_PREFIX} [WEBFLOWS] Found {len(raw_flows)} WebFlows")

            for flow in raw_flows:
                view_states = [v for v in flow.get("view_states", []) if v]
                action_states = [a for a in flow.get("action_states", []) if a]
                transitions = [t for t in flow.get("transitions", []) if t]

                webflows.append({
                    "name": flow.get("name", ""),
                    "path": flow.get("path", ""),
                    "type": "WebFlow",
                    "view_states": view_states,
                    "action_states": action_states,
                    "transitions": transitions,
                })

                logger.debug(f"{LOG_PREFIX} [WEBFLOWS]   - {flow.get('name')}: {len(view_states)} views, {len(action_states)} actions")

        except Exception as e:
            logger.warning(f"{LOG_PREFIX} [WEBFLOWS] Query failed: {e}")

        return webflows

    async def get_implementation_layers(
        self,
        keywords: list[str],
    ) -> dict:
        """
        Get components organized by implementation layer.

        This provides a clear UI → Controller → Service → DAO → Entity mapping.

        Args:
            keywords: Keywords to filter components

        Returns:
            Dict with components grouped by layer
        """
        logger.info(f"{LOG_PREFIX} [LAYERS] Starting layer extraction for keywords: {keywords}")

        layers = {
            "ui": [],        # JSP pages
            "flow": [],      # WebFlows
            "controller": [],  # Actions/Controllers
            "service": [],   # Services/Builders/Validators
            "data": [],      # DAOs/Repositories
            "entity": [],    # Entity classes
        }

        if not keywords:
            return layers

        compound_term, _ = extract_compound_terms(keywords)

        if compound_term:
            keyword_filter = f"toLower(n.name) CONTAINS '{compound_term}'"
        else:
            keyword_filter = " OR ".join([f"toLower(n.name) CONTAINS '{kw.lower()}'" for kw in keywords[:3]])

        # Single comprehensive query
        layer_query = f"""
            MATCH (n)
            WHERE ({keyword_filter})
              AND NOT toLower(n.name) CONTAINS 'test'
            WITH n, labels(n)[0] AS label
            RETURN n.name AS name,
                   n.filePath AS path,
                   label AS type,
                   CASE
                     WHEN label IN ['JSPPage', 'JSP'] THEN 'ui'
                     WHEN label = 'WebFlowDefinition' THEN 'flow'
                     WHEN toLower(n.name) ENDS WITH 'action' OR toLower(n.name) ENDS WITH 'controller' THEN 'controller'
                     WHEN toLower(n.name) CONTAINS 'dao' OR toLower(n.name) CONTAINS 'repository' THEN 'data'
                     WHEN toLower(n.name) CONTAINS 'service' OR toLower(n.name) CONTAINS 'builder' OR toLower(n.name) CONTAINS 'validator' THEN 'service'
                     ELSE 'entity'
                   END AS layer
            ORDER BY layer, n.name
            LIMIT 500
        """

        try:
            result = await self.neo4j.query_code_structure(layer_query)
            nodes = result.get("nodes", [])
            logger.info(f"{LOG_PREFIX} [LAYERS] Found {len(nodes)} components across layers")

            for node in nodes:
                layer = node.get("layer", "entity")
                if layer in layers:
                    layers[layer].append({
                        "name": node.get("name", ""),
                        "path": node.get("path", ""),
                        "type": node.get("type", ""),
                    })

            for layer, components in layers.items():
                if components:
                    logger.info(f"{LOG_PREFIX} [LAYERS]   {layer}: {len(components)} components")

        except Exception as e:
            logger.warning(f"{LOG_PREFIX} [LAYERS] Query failed: {e}")

        return layers

    async def get_full_technical_context(
        self,
        feature_description: str,
    ) -> dict:
        """
        Get comprehensive technical context for development planning.

        This combines:
        - Components by layer (UI → Backend → Database)
        - Entity details with fields
        - WebFlow details with states
        - Entry points and traversal

        Args:
            feature_description: Feature description

        Returns:
            Complete technical context dict
        """
        logger.info(f"{LOG_PREFIX} [TECH-CONTEXT] Getting full technical context for: {feature_description[:50]}...")

        keywords = [w for w in feature_description.split() if len(w) > 2][:8]

        # Get all technical details in parallel-ish fashion
        components, entry_points, warnings = await self.get_relevant_context(feature_description)
        entities = await self.get_entity_details(keywords)
        webflows = await self.get_webflow_details(keywords)
        layers = await self.get_implementation_layers(keywords)

        technical_context = {
            "feature": feature_description,
            "components": components,
            "entry_points": entry_points,
            "entities": entities,
            "webflows": webflows,
            "layers": layers,
            "warnings": warnings,
            "summary": {
                "total_components": len(components),
                "entry_point_count": len(entry_points),
                "entity_count": len(entities),
                "webflow_count": len(webflows),
                "ui_count": len(layers.get("ui", [])),
                "controller_count": len(layers.get("controller", [])),
                "service_count": len(layers.get("service", [])),
                "data_count": len(layers.get("data", [])),
            }
        }

        logger.info(f"{LOG_PREFIX} [TECH-CONTEXT] Complete: {technical_context['summary']}")

        return technical_context
