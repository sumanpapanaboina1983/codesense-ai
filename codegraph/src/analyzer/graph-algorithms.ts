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
        logger.info(`Top components by PageRank: ${topNodes.slice(0, 5).map(n => `${n.name}(${n.pageRank.toFixed(3)})`).join(', ')}`);

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
}
