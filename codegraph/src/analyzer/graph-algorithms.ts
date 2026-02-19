/**
 * Graph algorithms for computing relevance scores.
 *
 * This module computes PageRank scores for code components after indexing,
 * enabling relevance-based retrieval instead of hardcoded limits.
 */

import { Neo4jClient } from '../database/neo4j-client.js';
import { createContextLogger } from '../utils/logger.js';

const logger = createContextLogger('GraphAlgorithms');

/**
 * Result of PageRank computation.
 */
export interface PageRankResult {
    nodesUpdated: number;
    executionTimeMs: number;
    topNodes: Array<{ name: string; pageRank: number }>;
}

/**
 * Represents a step in a call chain.
 */
export interface CallChainStep {
    nodeId: string;
    name: string;
    type: string;
    filePath: string;
    startLine: number;
    endLine: number;
    signature?: string;
    layer: 'UI' | 'Flow' | 'Controller' | 'Service' | 'DAO' | 'Entity' | 'Unknown';
    depth: number;
    relationship?: string;
    arguments?: string[];
}

/**
 * Result of call chain extraction.
 */
export interface CallChainResult {
    entryPoint: CallChainStep;
    chain: CallChainStep[];
    sqlStatements: Array<{
        statementType: string;
        tableName: string;
        rawSql: string;
        lineNumber: number;
        sourceMethod: string;
    }>;
    dataBindings: Array<{
        uiField: string;
        entityField: string;
        lineNumber: number;
    }>;
}

/**
 * Result of feature flow extraction.
 */
export interface FeatureFlowResult {
    flowName: string;
    layers: {
        ui: CallChainStep[];
        flow: CallChainStep[];
        controller: CallChainStep[];
        service: CallChainStep[];
        dao: CallChainStep[];
        entity: CallChainStep[];
    };
    callChain: CallChainStep[];
    sqlOperations: Array<{
        statementType: string;
        tableName: string;
        columns: string[];
        sourceMethod: string;
        lineNumber: number;
    }>;
    dataFlow: Array<{
        uiField: string;
        entityField: string;
        dbColumn?: string;
    }>;
}

/**
 * Computes and stores graph-based relevance scores for code components.
 */
export class GraphAlgorithms {
    private neo4jClient: Neo4jClient;

    constructor(neo4jClient: Neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    /**
     * Computes PageRank scores for all code components and stores them as node properties.
     *
     * This enables relevance-based retrieval:
     * - Components with higher PageRank are more "central" in the codebase
     * - Can be used to rank search results by structural importance
     *
     * @param repositoryId - The repository to compute PageRank for
     * @returns PageRank computation result
     */
    async computePageRank(repositoryId: string): Promise<PageRankResult> {
        const startTime = Date.now();
        logger.info(`Computing PageRank for repository: ${repositoryId}`);

        try {
            // Check if GDS (Graph Data Science) library is available
            const gdsAvailable = await this.checkGDSAvailable();

            if (gdsAvailable) {
                return await this.computePageRankWithGDS(repositoryId, startTime);
            } else {
                // Fallback: Use native Cypher-based approximation
                return await this.computePageRankNative(repositoryId, startTime);
            }
        } catch (error: any) {
            logger.error(`PageRank computation failed: ${error.message}`);
            // Return empty result on failure - don't break indexing
            return {
                nodesUpdated: 0,
                executionTimeMs: Date.now() - startTime,
                topNodes: [],
            };
        }
    }

    /**
     * Check if Neo4j Graph Data Science library is available.
     */
    private async checkGDSAvailable(): Promise<boolean> {
        try {
            const result = await this.neo4jClient.runTransaction<any>(
                `RETURN gds.version() AS version`,
                {},
                'READ',
                'GraphAlgorithms-GDSCheck'
            );
            const version = result.records?.[0]?.get('version');
            logger.info(`GDS library available: version ${version}`);
            return true;
        } catch {
            logger.info('GDS library not available, using native PageRank approximation');
            return false;
        }
    }

    /**
     * Compute PageRank using Neo4j GDS library (optimal).
     */
    private async computePageRankWithGDS(repositoryId: string, startTime: number): Promise<PageRankResult> {
        const graphName = `pagerank_graph_${repositoryId.replace(/-/g, '_')}`;

        try {
            // Drop existing graph projection if exists
            try {
                await this.neo4jClient.runTransaction<any>(
                    `CALL gds.graph.drop($graphName, false)`,
                    { graphName },
                    'WRITE',
                    'GraphAlgorithms-DropGraph'
                );
            } catch {
                // Graph doesn't exist, that's fine
            }

            // Create graph projection with all code components and relationships
            await this.neo4jClient.runTransaction<any>(
                `CALL gds.graph.project(
                    $graphName,
                    {
                        Component: { label: 'Class|Interface|Function|Method|JavaClass|JavaInterface|JavaMethod|SpringController|SpringService|PythonClass|PythonFunction' }
                    },
                    {
                        DEPENDS: {
                            type: 'CALLS|IMPORTS|EXTENDS|IMPLEMENTS|DEPENDS_ON|DEPENDS_ON_MODULE',
                            orientation: 'NATURAL'
                        }
                    },
                    { nodeProperties: ['repositoryId'] }
                )`,
                { graphName },
                'WRITE',
                'GraphAlgorithms-CreateProjection'
            );

            // Run PageRank and write results back
            const pageRankResult = await this.neo4jClient.runTransaction<any>(
                `CALL gds.pageRank.write($graphName, {
                    writeProperty: 'pageRank',
                    dampingFactor: 0.85,
                    maxIterations: 20
                })
                YIELD nodePropertiesWritten, ranIterations, didConverge, centralityDistribution
                RETURN nodePropertiesWritten, ranIterations, didConverge`,
                { graphName },
                'WRITE',
                'GraphAlgorithms-RunPageRank'
            );

            const record = pageRankResult.records?.[0];
            const nodesUpdated = record?.get('nodePropertiesWritten')?.toNumber?.() ?? record?.get('nodePropertiesWritten') ?? 0;

            // Get top nodes
            const topNodesResult = await this.neo4jClient.runTransaction<any>(
                `MATCH (n)
                 WHERE n.repositoryId = $repositoryId AND n.pageRank IS NOT NULL
                 RETURN n.name AS name, n.pageRank AS pageRank
                 ORDER BY n.pageRank DESC
                 LIMIT 10`,
                { repositoryId },
                'READ',
                'GraphAlgorithms-TopNodes'
            );

            const topNodes = topNodesResult.records?.map((r: any) => ({
                name: r.get('name'),
                pageRank: r.get('pageRank'),
            })) ?? [];

            // Cleanup graph projection
            await this.neo4jClient.runTransaction<any>(
                `CALL gds.graph.drop($graphName, false)`,
                { graphName },
                'WRITE',
                'GraphAlgorithms-CleanupGraph'
            );

            const executionTimeMs = Date.now() - startTime;
            logger.info(`PageRank computed with GDS: ${nodesUpdated} nodes updated in ${executionTimeMs}ms`);

            return { nodesUpdated, executionTimeMs, topNodes };
        } catch (error: any) {
            logger.error(`GDS PageRank failed: ${error.message}, falling back to native`);
            return this.computePageRankNative(repositoryId, startTime);
        }
    }

    /**
     * Compute PageRank approximation using native Cypher (fallback).
     *
     * This uses a simplified approach based on incoming relationship count,
     * normalized by total relationships. Not as accurate as true PageRank
     * but provides useful relevance signals without GDS.
     */
    private async computePageRankNative(repositoryId: string, startTime: number): Promise<PageRankResult> {
        logger.info('Computing PageRank using native Cypher approximation...');

        // Step 1: Count total dependency relationships for normalization
        const totalRelsResult = await this.neo4jClient.runTransaction<any>(
            `MATCH (n)-[r:CALLS|IMPORTS|EXTENDS|IMPLEMENTS|DEPENDS_ON|DEPENDS_ON_MODULE]->(m)
             WHERE n.repositoryId = $repositoryId
             RETURN count(r) AS totalRels`,
            { repositoryId },
            'READ',
            'GraphAlgorithms-CountRels'
        );
        const totalRels = totalRelsResult.records?.[0]?.get('totalRels')?.toNumber?.() ?? 1;

        // Step 2: Compute incoming degree centrality as PageRank approximation
        // Higher incoming = more depended upon = higher importance
        const updateResult = await this.neo4jClient.runTransaction<any>(
            `MATCH (n)
             WHERE n.repositoryId = $repositoryId
               AND (n:Class OR n:Interface OR n:Function OR n:Method
                    OR n:JavaClass OR n:JavaInterface OR n:JavaMethod
                    OR n:SpringController OR n:SpringService
                    OR n:PythonClass OR n:PythonFunction
                    OR n:Component)
             OPTIONAL MATCH (caller)-[r:CALLS|IMPORTS|EXTENDS|IMPLEMENTS|DEPENDS_ON|DEPENDS_ON_MODULE]->(n)
             WITH n, count(r) AS inDegree
             SET n.pageRank = CASE
                 WHEN $totalRels > 0 THEN toFloat(inDegree) / $totalRels + 0.15
                 ELSE 0.15
             END
             RETURN count(n) AS nodesUpdated`,
            { repositoryId, totalRels },
            'WRITE',
            'GraphAlgorithms-NativePageRank'
        );

        const nodesUpdated = updateResult.records?.[0]?.get('nodesUpdated')?.toNumber?.() ?? 0;

        // Step 3: Normalize to 0-1 range
        await this.neo4jClient.runTransaction<any>(
            `MATCH (n)
             WHERE n.repositoryId = $repositoryId AND n.pageRank IS NOT NULL
             WITH max(n.pageRank) AS maxRank
             MATCH (n)
             WHERE n.repositoryId = $repositoryId AND n.pageRank IS NOT NULL
             SET n.pageRank = CASE
                 WHEN maxRank > 0 THEN n.pageRank / maxRank
                 ELSE 0.15
             END`,
            { repositoryId },
            'WRITE',
            'GraphAlgorithms-NormalizePageRank'
        );

        // Get top nodes
        const topNodesResult = await this.neo4jClient.runTransaction<any>(
            `MATCH (n)
             WHERE n.repositoryId = $repositoryId AND n.pageRank IS NOT NULL
             RETURN n.name AS name, n.pageRank AS pageRank
             ORDER BY n.pageRank DESC
             LIMIT 10`,
            { repositoryId },
            'READ',
            'GraphAlgorithms-TopNodes'
        );

        const topNodes = topNodesResult.records?.map((r: any) => ({
            name: r.get('name'),
            pageRank: r.get('pageRank'),
        })) ?? [];

        const executionTimeMs = Date.now() - startTime;
        logger.info(`Native PageRank computed: ${nodesUpdated} nodes updated in ${executionTimeMs}ms`);
        logger.info(`Top components by PageRank: ${topNodes.slice(0, 5).map((n: { name: string; pageRank: number }) => `${n.name}(${n.pageRank.toFixed(3)})`).join(', ')}`);

        return { nodesUpdated, executionTimeMs, topNodes };
    }

    /**
     * Computes dependency depth scores for components.
     * Components deeper in the call graph get higher depth scores.
     */
    async computeDependencyDepth(repositoryId: string): Promise<void> {
        logger.info(`Computing dependency depth for repository: ${repositoryId}`);

        // Find entry points (components with no incoming calls)
        // and compute BFS depth from them
        await this.neo4jClient.runTransaction<any>(
            `MATCH (entry)
             WHERE entry.repositoryId = $repositoryId
               AND (entry:RestEndpoint OR entry:UIRoute OR entry:CLICommand OR entry:ScheduledTask)
             WITH collect(entry) AS entryPoints
             UNWIND entryPoints AS ep
             MATCH path = (ep)-[:CALLS|RENDERS|ROUTE_USES_SERVICE*0..10]->(n)
             WHERE n.repositoryId = $repositoryId
             WITH n, min(length(path)) AS depth
             SET n.dependencyDepth = depth`,
            { repositoryId },
            'WRITE',
            'GraphAlgorithms-DependencyDepth'
        );

        logger.info('Dependency depth computed');
    }

    /**
     * Extract call chain starting from an entry point.
     * Traverses downstream through CALLS, INVOKES, HAS_METHOD relationships.
     *
     * @param entryPointId - Entity ID of the starting point (JSP, Controller, etc.)
     * @param maxDepth - Maximum traversal depth (default: 10)
     * @returns CallChainResult with ordered steps
     */
    async extractCallChain(entryPointId: string, maxDepth: number = 10): Promise<CallChainResult> {
        logger.info(`Extracting call chain from: ${entryPointId}`);

        const callChainQuery = `
            MATCH (entry {entityId: $entryPointId})
            OPTIONAL MATCH path = (entry)-[:CALLS|INVOKES|HAS_METHOD|FLOW_EXECUTES_ACTION|ACTION_CALLS_SERVICE*1..${maxDepth}]->(target)
            WITH entry, path, target,
                 [node IN nodes(path) | {
                     nodeId: node.entityId,
                     name: node.name,
                     type: labels(node)[0],
                     filePath: node.filePath,
                     startLine: node.startLine,
                     endLine: node.endLine,
                     signature: COALESCE(node.signature, node.signatureInfo.signature, ''),
                     layer: CASE
                         WHEN 'JSPPage' IN labels(node) THEN 'UI'
                         WHEN 'WebFlowDefinition' IN labels(node) OR 'FlowState' IN labels(node) THEN 'Flow'
                         WHEN toLower(node.name) ENDS WITH 'action' OR toLower(node.name) ENDS WITH 'controller' THEN 'Controller'
                         WHEN toLower(node.name) CONTAINS 'dao' OR toLower(node.name) CONTAINS 'repository' THEN 'DAO'
                         WHEN toLower(node.name) CONTAINS 'service' OR toLower(node.name) CONTAINS 'builder' THEN 'Service'
                         ELSE 'Unknown'
                     END
                 }] AS pathNodes,
                 [rel IN relationships(path) | {
                     type: type(rel),
                     lineNumber: rel.lineNumber,
                     arguments: rel.arguments
                 }] AS pathRels
            RETURN entry, pathNodes, pathRels
            ORDER BY length(path)
        `;

        try {
            const result = await this.neo4jClient.runTransaction<any>(
                callChainQuery,
                { entryPointId },
                'READ',
                'GraphAlgorithms-ExtractCallChain'
            );

            const entryRecord = result.records?.[0];
            if (!entryRecord) {
                logger.warn(`No entry point found for: ${entryPointId}`);
                return { entryPoint: {} as CallChainStep, chain: [], sqlStatements: [], dataBindings: [] };
            }

            const entry = entryRecord.get('entry');
            const entryStep: CallChainStep = {
                nodeId: entry.properties.entityId,
                name: entry.properties.name,
                type: entry.labels[0],
                filePath: entry.properties.filePath,
                startLine: entry.properties.startLine?.toNumber?.() ?? entry.properties.startLine ?? 0,
                endLine: entry.properties.endLine?.toNumber?.() ?? entry.properties.endLine ?? 0,
                signature: entry.properties.signature || '',
                layer: this.determineLayer(entry.labels[0], entry.properties.name),
                depth: 0,
            };

            // Collect unique chain steps
            const chainMap = new Map<string, CallChainStep>();
            for (const record of result.records || []) {
                const pathNodes = record.get('pathNodes') || [];
                const pathRels = record.get('pathRels') || [];

                for (let i = 0; i < pathNodes.length; i++) {
                    const node = pathNodes[i];
                    if (node && node.nodeId && !chainMap.has(node.nodeId)) {
                        chainMap.set(node.nodeId, {
                            nodeId: node.nodeId,
                            name: node.name,
                            type: node.type,
                            filePath: node.filePath,
                            startLine: node.startLine?.toNumber?.() ?? node.startLine ?? 0,
                            endLine: node.endLine?.toNumber?.() ?? node.endLine ?? 0,
                            signature: node.signature,
                            layer: node.layer || this.determineLayer(node.type, node.name),
                            depth: i + 1,
                            relationship: pathRels[i]?.type,
                            arguments: pathRels[i]?.arguments,
                        });
                    }
                }
            }

            const chain = Array.from(chainMap.values()).sort((a, b) => a.depth - b.depth);

            // Get SQL statements for DAO methods
            const sqlStatements = await this.getSQLStatementsForChain(chain);

            // Get data bindings for UI fields
            const dataBindings = await this.getDataBindingsForEntry(entryPointId);

            return { entryPoint: entryStep, chain, sqlStatements, dataBindings };
        } catch (error: any) {
            logger.error(`Call chain extraction failed: ${error.message}`);
            return { entryPoint: {} as CallChainStep, chain: [], sqlStatements: [], dataBindings: [] };
        }
    }

    /**
     * Get SQL statements executed by methods in the call chain.
     */
    private async getSQLStatementsForChain(chain: CallChainStep[]): Promise<Array<{
        statementType: string;
        tableName: string;
        rawSql: string;
        lineNumber: number;
        sourceMethod: string;
    }>> {
        const daoMethods = chain.filter(step => step.layer === 'DAO' || step.layer === 'Service');
        if (daoMethods.length === 0) return [];

        const methodIds = daoMethods.map(m => m.nodeId);

        const sqlQuery = `
            MATCH (method)-[:EXECUTES_SQL]->(sql:SQLStatement)
            WHERE method.entityId IN $methodIds
            RETURN sql.statementType AS statementType,
                   sql.tableName AS tableName,
                   sql.rawSql AS rawSql,
                   sql.lineNumber AS lineNumber,
                   method.name AS sourceMethod
        `;

        try {
            const result = await this.neo4jClient.runTransaction<any>(
                sqlQuery,
                { methodIds },
                'READ',
                'GraphAlgorithms-GetSQLStatements'
            );

            return (result.records || []).map((r: any) => ({
                statementType: r.get('statementType'),
                tableName: r.get('tableName'),
                rawSql: r.get('rawSql'),
                lineNumber: r.get('lineNumber')?.toNumber?.() ?? r.get('lineNumber') ?? 0,
                sourceMethod: r.get('sourceMethod'),
            }));
        } catch (error: any) {
            logger.warn(`SQL statement extraction failed: ${error.message}`);
            return [];
        }
    }

    /**
     * Get data bindings (UI field -> Entity field) for an entry point.
     */
    private async getDataBindingsForEntry(entryPointId: string): Promise<Array<{
        uiField: string;
        entityField: string;
        lineNumber: number;
    }>> {
        const bindingQuery = `
            MATCH (entry {entityId: $entryPointId})-[:HAS_FIELD_BINDING|CONTAINS_FORM*1..3]->(binding:FormFieldBinding)
            OPTIONAL MATCH (binding)-[:BINDS_TO]->(field:JavaField)
            RETURN binding.fieldPath AS uiField,
                   COALESCE(field.name, binding.fieldName) AS entityField,
                   binding.lineNumber AS lineNumber
        `;

        try {
            const result = await this.neo4jClient.runTransaction<any>(
                bindingQuery,
                { entryPointId },
                'READ',
                'GraphAlgorithms-GetDataBindings'
            );

            return (result.records || []).map((r: any) => ({
                uiField: r.get('uiField'),
                entityField: r.get('entityField'),
                lineNumber: r.get('lineNumber')?.toNumber?.() ?? r.get('lineNumber') ?? 0,
            }));
        } catch (error: any) {
            logger.warn(`Data binding extraction failed: ${error.message}`);
            return [];
        }
    }

    /**
     * Extract complete feature flow from JSP through to database.
     *
     * @param jspPageId - Entity ID of the JSP page
     * @returns FeatureFlowResult with layers and data flow
     */
    async extractFeatureFlow(jspPageId: string): Promise<FeatureFlowResult> {
        logger.info(`Extracting feature flow from: ${jspPageId}`);

        const flowQuery = `
            // Start from JSP page
            MATCH (jsp:JSPPage {entityId: $jspPageId})

            // Find forms and their actions
            OPTIONAL MATCH (jsp)-[:CONTAINS_FORM]->(form:JSPForm)

            // Find WebFlows connected to the JSP
            OPTIONAL MATCH (flow:WebFlowDefinition)-[:FLOW_RENDERS_VIEW]->(jsp)

            // Find Controllers/Actions
            OPTIONAL MATCH (flow)-[:FLOW_EXECUTES_ACTION]->(action)
            WHERE action:FlowAction OR action:JavaMethod

            // Find parent class for action methods
            OPTIONAL MATCH (controller)-[:HAS_METHOD]->(action)
            WHERE controller:JavaClass OR controller:SpringController

            // Find Services called by Controller
            OPTIONAL MATCH (controller)-[:HAS_METHOD]->(ctrlMethod:JavaMethod)-[:INVOKES]->(serviceCall:MethodInvocation)
            OPTIONAL MATCH (serviceClass)-[:HAS_METHOD]->(serviceMethod:JavaMethod)
            WHERE toLower(serviceClass.name) CONTAINS 'service' OR toLower(serviceClass.name) CONTAINS 'builder'

            // Find DAOs called by Services
            OPTIONAL MATCH (daoClass)-[:HAS_METHOD]->(daoMethod:JavaMethod)
            WHERE toLower(daoClass.name) CONTAINS 'dao' OR toLower(daoClass.name) CONTAINS 'repository'

            // Collect all layers
            RETURN jsp,
                   collect(DISTINCT form) AS forms,
                   collect(DISTINCT flow) AS flows,
                   collect(DISTINCT controller) AS controllers,
                   collect(DISTINCT serviceClass) AS services,
                   collect(DISTINCT daoClass) AS daos
        `;

        try {
            const result = await this.neo4jClient.runTransaction<any>(
                flowQuery,
                { jspPageId },
                'READ',
                'GraphAlgorithms-ExtractFeatureFlow'
            );

            // Process results into FeatureFlowResult structure
            const record = result.records?.[0];
            if (!record) {
                return this.emptyFeatureFlowResult();
            }

            // Get call chain
            const callChainResult = await this.extractCallChain(jspPageId);

            const layers = {
                ui: callChainResult.chain.filter(s => s.layer === 'UI'),
                flow: callChainResult.chain.filter(s => s.layer === 'Flow'),
                controller: callChainResult.chain.filter(s => s.layer === 'Controller'),
                service: callChainResult.chain.filter(s => s.layer === 'Service'),
                dao: callChainResult.chain.filter(s => s.layer === 'DAO'),
                entity: callChainResult.chain.filter(s => s.layer === 'Entity'),
            };

            // Add entry point to UI layer
            if (callChainResult.entryPoint.nodeId) {
                layers.ui.unshift(callChainResult.entryPoint);
            }

            return {
                flowName: record.get('jsp')?.properties?.name || 'Unknown',
                layers,
                callChain: [callChainResult.entryPoint, ...callChainResult.chain],
                sqlOperations: callChainResult.sqlStatements.map(sql => ({
                    statementType: sql.statementType,
                    tableName: sql.tableName,
                    columns: [],
                    sourceMethod: sql.sourceMethod,
                    lineNumber: sql.lineNumber,
                })),
                dataFlow: callChainResult.dataBindings.map(b => ({
                    uiField: b.uiField,
                    entityField: b.entityField,
                })),
            };
        } catch (error: any) {
            logger.error(`Feature flow extraction failed: ${error.message}`);
            return this.emptyFeatureFlowResult();
        }
    }

    /**
     * Determine the architectural layer for a node.
     */
    private determineLayer(nodeType: string, nodeName: string): 'UI' | 'Flow' | 'Controller' | 'Service' | 'DAO' | 'Entity' | 'Unknown' {
        const typeLower = nodeType.toLowerCase();
        const nameLower = nodeName.toLowerCase();

        if (typeLower.includes('jsp') || typeLower === 'jsppage') return 'UI';
        if (typeLower.includes('webflow') || typeLower.includes('flowstate')) return 'Flow';
        if (nameLower.endsWith('action') || nameLower.endsWith('controller')) return 'Controller';
        if (nameLower.includes('dao') || nameLower.includes('repository')) return 'DAO';
        if (nameLower.includes('service') || nameLower.includes('builder') || nameLower.includes('validator')) return 'Service';
        if (typeLower === 'javaclass' && !nameLower.includes('action') && !nameLower.includes('service')) return 'Entity';

        return 'Unknown';
    }

    /**
     * Return empty feature flow result.
     */
    private emptyFeatureFlowResult(): FeatureFlowResult {
        return {
            flowName: '',
            layers: {
                ui: [],
                flow: [],
                controller: [],
                service: [],
                dao: [],
                entity: [],
            },
            callChain: [],
            sqlOperations: [],
            dataFlow: [],
        };
    }

    /**
     * Create indexes for feature flow queries.
     */
    async createFeatureFlowIndexes(): Promise<void> {
        logger.info('Creating indexes for feature flow queries...');

        const indexes = [
            'CREATE INDEX IF NOT EXISTS FOR (n:SQLStatement) ON (n.entityId)',
            'CREATE INDEX IF NOT EXISTS FOR (n:SQLStatement) ON (n.tableName)',
            'CREATE INDEX IF NOT EXISTS FOR (n:MethodInvocation) ON (n.entityId)',
            'CREATE INDEX IF NOT EXISTS FOR (n:FormFieldBinding) ON (n.entityId)',
            'CREATE INDEX IF NOT EXISTS FOR (n:FormFieldBinding) ON (n.fieldPath)',
        ];

        for (const indexQuery of indexes) {
            try {
                await this.neo4jClient.runTransaction<any>(
                    indexQuery,
                    {},
                    'WRITE',
                    'GraphAlgorithms-CreateIndex'
                );
            } catch (error: any) {
                // Index might already exist
                logger.debug(`Index creation note: ${error.message}`);
            }
        }

        logger.info('Feature flow indexes created');
    }
}
