// src/analyzer/repository-overview.ts
/**
 * Repository Overview Service
 * Aggregates analysis results into a comprehensive repository summary.
 * Provides Neo4j queries for statistics, hotspots, and recommendations.
 */

import winston from 'winston';
import { Neo4jClient } from '../database/neo4j-client.js';
import {
    AstNode,
    RepositoryOverview,
    ModuleStats,
    ComplexityHotspot,
    EntryPointSummary,
    TestCoverageSummary,
    CodeQualitySummary,
    ArchitecturePattern,
    StartingPointRecommendation,
    DetectedFramework,
    Stereotype,
    CodeSmellSeverity,
    CodeSmellCategory,
    HttpMethod,
    GraphQLOperationType,
    TestFramework,
    UIRoutingFramework,
} from './types.js';

// =============================================================================
// Neo4j Query Templates
// =============================================================================

const QUERIES = {
    // Summary statistics
    SUMMARY_STATS: `
        MATCH (r:Repository {repositoryId: $repositoryId})
        OPTIONAL MATCH (r)-[:BELONGS_TO]-(f:File)
        OPTIONAL MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION*1..2]->(fn)
        WHERE fn:Function OR fn:Method OR fn:JavaMethod OR fn:GoFunction OR fn:CSharpMethod
        OPTIONAL MATCH (f)-[:CONTAINS|DEFINES_CLASS*1..2]->(c)
        WHERE c:Class OR c:JavaClass OR c:CSharpClass OR c:GoStruct
        RETURN
            count(DISTINCT f) as totalFiles,
            count(DISTINCT fn) as totalFunctions,
            count(DISTINCT c) as totalClasses,
            sum(f.loc) as totalLoc
    `,

    // Language distribution
    LANGUAGE_DISTRIBUTION: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        RETURN f.language as language, count(f) as fileCount, sum(f.loc) as loc
        ORDER BY fileCount DESC
    `,

    // Module statistics
    MODULE_STATS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:HAS_MODULE]->(m:JavaModule)
        OPTIONAL MATCH (m)-[:CONTAINS_FILE]->(f:File)
        OPTIONAL MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION*1..2]->(fn)
        WHERE fn:Function OR fn:Method OR fn:JavaMethod
        OPTIONAL MATCH (f)-[:CONTAINS|DEFINES_CLASS*1..2]->(c)
        WHERE c:Class OR c:JavaClass
        OPTIONAL MATCH (m)-[:DEPENDS_ON_MODULE]->(dep:JavaModule)
        RETURN
            m.name as name,
            m.path as path,
            count(DISTINCT f) as fileCount,
            count(DISTINCT fn) as functionCount,
            count(DISTINCT c) as classCount,
            sum(f.loc) as totalLoc,
            avg(fn.complexity) as avgComplexity,
            max(fn.complexity) as maxComplexity,
            collect(DISTINCT dep.name) as dependencies
    `,

    // Complexity hotspots
    COMPLEXITY_HOTSPOTS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION*1..2]->(fn)
        WHERE (fn:Function OR fn:Method OR fn:JavaMethod OR fn:GoFunction OR fn:CSharpMethod)
            AND (fn.complexity > $complexityThreshold OR fn.cognitiveComplexity > $cognitiveThreshold)
        RETURN
            fn.entityId as entityId,
            fn.name as name,
            fn.filePath as filePath,
            fn.startLine as line,
            labels(fn)[0] as kind,
            fn.complexity as cyclomaticComplexity,
            coalesce(fn.cognitiveComplexity, fn.complexity) as cognitiveComplexity,
            fn.loc as loc
        ORDER BY cognitiveComplexity DESC
        LIMIT $limit
    `,

    // REST endpoints
    REST_ENDPOINTS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[*1..3]->(e:RestEndpoint)
        RETURN
            e.httpMethod as httpMethod,
            count(*) as count
    `,

    // GraphQL operations
    GRAPHQL_OPERATIONS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[*1..3]->(g:GraphQLOperation)
        RETURN
            g.operationType as operationType,
            count(*) as count
    `,

    // Event handlers
    EVENT_HANDLERS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[*1..3]->(e:EventHandler)
        RETURN
            e.eventSource as eventSource,
            count(*) as count
    `,

    // Scheduled tasks count
    SCHEDULED_TASKS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[*1..3]->(s:ScheduledTask)
        RETURN count(s) as count
    `,

    // CLI commands count
    CLI_COMMANDS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[*1..3]->(c:CLICommand)
        RETURN count(c) as count
    `,

    // Test coverage
    TEST_COVERAGE: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        WHERE f.kind = 'File'
        WITH r, collect(f) as allFiles
        OPTIONAL MATCH (r)-[:BELONGS_TO]-(tf:TestFile)
        RETURN
            size(allFiles) as totalFiles,
            count(tf) as testFiles,
            sum(tf.testCount) as testCaseCount
    `,

    // Documentation coverage
    DOC_COVERAGE: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION*1..2]->(fn)
        WHERE fn:Function OR fn:Method OR fn:JavaMethod
        WITH count(fn) as totalFunctions,
             sum(CASE WHEN fn.hasDocumentation = true THEN 1 ELSE 0 END) as documented
        RETURN totalFunctions, documented,
               CASE WHEN totalFunctions > 0 THEN toFloat(documented) / totalFunctions ELSE 0 END as coverage
    `,

    // Code smells by severity
    CODE_SMELLS_BY_SEVERITY: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION|DEFINES_CLASS*1..2]->(n)
        WHERE n.codeSmells IS NOT NULL
        UNWIND n.codeSmells as smell
        RETURN smell.severity as severity, count(*) as count
    `,

    // Stereotype distribution
    STEREOTYPE_DISTRIBUTION: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[:CONTAINS|DEFINES_CLASS*1..2]->(c)
        WHERE c:Class OR c:JavaClass OR c:CSharpClass
        RETURN c.stereotype as stereotype, count(*) as count
        ORDER BY count DESC
    `,

    // Starting point recommendations
    STARTING_POINTS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        OPTIONAL MATCH (f)-[:CONTAINS|DEFINES_CLASS*1..2]->(c)
        WHERE c.stereotype IN ['Controller', 'Service']
        OPTIONAL MATCH (f)-[*1..3]->(e:RestEndpoint)
        OPTIONAL MATCH (f)-[:CONTAINS|DEFINES_FUNCTION*1..2]->(fn)
        WHERE fn.name IN ['main', 'index', 'app', 'bootstrap']
        RETURN DISTINCT
            coalesce(c.entityId, e.entityId, fn.entityId) as entityId,
            coalesce(c.name, e.name, fn.name) as name,
            coalesce(c.filePath, e.filePath, fn.filePath) as filePath,
            CASE
                WHEN c IS NOT NULL AND c.stereotype = 'Controller' THEN 'entry-point'
                WHEN e IS NOT NULL THEN 'entry-point'
                WHEN fn.name IN ['main', 'index', 'app'] THEN 'entry-point'
                WHEN c.stereotype = 'Service' THEN 'core-module'
                ELSE 'core-module'
            END as type,
            CASE
                WHEN c.stereotype = 'Controller' THEN 1
                WHEN e IS NOT NULL THEN 2
                WHEN fn.name = 'main' THEN 3
                ELSE 4
            END as priority
        ORDER BY priority
        LIMIT 10
    `,

    // Module dependency graph
    MODULE_DEPENDENCY_GRAPH: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:HAS_MODULE]->(m1:JavaModule)
        OPTIONAL MATCH (m1)-[d:DEPENDS_ON_MODULE]->(m2:JavaModule)
        RETURN m1.name as source, m2.name as target, coalesce(d.weight, 1) as weight
    `,

    // UI Routes by framework (Phase 1)
    UI_ROUTES: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[*1..3]->(route:UIRoute)
        RETURN
            route.framework as framework,
            count(*) as count
    `,

    // UI Pages by framework (Phase 1)
    UI_PAGES: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[*1..3]->(page:UIPage)
        RETURN
            page.framework as framework,
            count(*) as count
    `,

    // Protected routes count (Phase 1)
    PROTECTED_ROUTES: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[*1..3]->(route:UIRoute)
        WHERE route.requiresAuth = true
        RETURN count(route) as count
    `,

    // UI routes to API connections (Phase 1)
    UI_TO_API_CONNECTIONS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[*1..3]->(route:UIRoute)-[:ROUTE_CALLS_API]->(endpoint:RestEndpoint)
        RETURN route.path as routePath, endpoint.path as apiPath, endpoint.httpMethod as method
        LIMIT 100
    `,
};

// =============================================================================
// Repository Overview Service
// =============================================================================

export class RepositoryOverviewService {
    private logger: winston.Logger;
    private neo4jClient: Neo4jClient;

    constructor(neo4jClient: Neo4jClient, logger: winston.Logger) {
        this.neo4jClient = neo4jClient;
        this.logger = logger;
    }

    /**
     * Generate a complete repository overview.
     */
    async generateOverview(
        repositoryId: string,
        repositoryName: string,
        detectedFrameworks: DetectedFramework[] = []
    ): Promise<RepositoryOverview> {
        this.logger.info(`Generating repository overview for ${repositoryId}`);
        const startTime = Date.now();

        try {
            // Fetch all data in parallel for performance
            const [
                summaryStats,
                languageDistribution,
                moduleStats,
                hotspots,
                entryPointSummary,
                testCoverage,
                docCoverage,
                smellsBySeverity,
                stereotypeDistribution,
                startingPoints,
                moduleGraph,
            ] = await Promise.all([
                this.fetchSummaryStats(repositoryId),
                this.fetchLanguageDistribution(repositoryId),
                this.fetchModuleStats(repositoryId),
                this.fetchComplexityHotspots(repositoryId),
                this.fetchEntryPointSummary(repositoryId),
                this.fetchTestCoverage(repositoryId),
                this.fetchDocCoverage(repositoryId),
                this.fetchSmellsBySeverity(repositoryId),
                this.fetchStereotypeDistribution(repositoryId),
                this.fetchStartingPoints(repositoryId),
                this.fetchModuleDependencyGraph(repositoryId),
            ]);

            // Detect architecture patterns
            const architecturePatterns = this.detectArchitecturePatterns(
                stereotypeDistribution,
                moduleStats
            );

            // Generate recommendations
            const recommendations = this.generateRecommendations(
                startingPoints,
                hotspots,
                entryPointSummary
            );

            const overview: RepositoryOverview = {
                repositoryId,
                repositoryName,
                analyzedAt: new Date().toISOString(),

                summary: {
                    totalFiles: summaryStats.totalFiles,
                    totalFunctions: summaryStats.totalFunctions,
                    totalClasses: summaryStats.totalClasses,
                    totalLoc: summaryStats.totalLoc,
                    languages: languageDistribution,
                    frameworks: detectedFrameworks,
                },

                modules: moduleStats,

                architecture: {
                    patterns: architecturePatterns,
                    layers: this.inferLayers(stereotypeDistribution),
                    moduleGraph,
                },

                entryPoints: entryPointSummary,

                codeQuality: {
                    avgCyclomaticComplexity: this.calculateAvgComplexity(hotspots),
                    avgCognitiveComplexity: this.calculateAvgCognitiveComplexity(hotspots),
                    documentationCoverage: docCoverage.coverage,
                    publicApiDocCoverage: docCoverage.coverage, // Simplified
                    hotspots,
                    smellsBySeverity,
                    smellsByCategory: {
                        complexity: 0,
                        size: 0,
                        coupling: 0,
                        naming: 0,
                        duplication: 0,
                        architecture: 0,
                        maintainability: 0,
                        performance: 0,
                    } as Record<CodeSmellCategory, number>, // Would need additional query
                },

                testing: testCoverage,

                recommendations,
            };

            const duration = Date.now() - startTime;
            this.logger.info(`Repository overview generated in ${duration}ms`);

            return overview;
        } catch (error: any) {
            this.logger.error('Failed to generate repository overview', { error: error.message });
            throw error;
        }
    }

    /**
     * Fetch summary statistics.
     */
    private async fetchSummaryStats(repositoryId: string): Promise<{
        totalFiles: number;
        totalFunctions: number;
        totalClasses: number;
        totalLoc: number;
    }> {
        try {
            const result = await this.neo4jClient.runTransaction(
                QUERIES.SUMMARY_STATS,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );

            const record = (result as any).records?.[0];
            return {
                totalFiles: record?.get('totalFiles')?.toNumber?.() || 0,
                totalFunctions: record?.get('totalFunctions')?.toNumber?.() || 0,
                totalClasses: record?.get('totalClasses')?.toNumber?.() || 0,
                totalLoc: record?.get('totalLoc')?.toNumber?.() || 0,
            };
        } catch (error) {
            this.logger.warn('Failed to fetch summary stats', { error });
            return { totalFiles: 0, totalFunctions: 0, totalClasses: 0, totalLoc: 0 };
        }
    }

    /**
     * Fetch language distribution.
     */
    private async fetchLanguageDistribution(repositoryId: string): Promise<
        { language: string; fileCount: number; loc: number }[]
    > {
        try {
            const result = await this.neo4jClient.runTransaction(
                QUERIES.LANGUAGE_DISTRIBUTION,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );

            return ((result as any).records || []).map((r: any) => ({
                language: r.get('language') || 'Unknown',
                fileCount: r.get('fileCount')?.toNumber?.() || 0,
                loc: r.get('loc')?.toNumber?.() || 0,
            }));
        } catch (error) {
            this.logger.warn('Failed to fetch language distribution', { error });
            return [];
        }
    }

    /**
     * Fetch module statistics.
     */
    private async fetchModuleStats(repositoryId: string): Promise<ModuleStats[]> {
        try {
            const result = await this.neo4jClient.runTransaction(
                QUERIES.MODULE_STATS,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );

            return ((result as any).records || []).map((r: any) => ({
                name: r.get('name') || '',
                path: r.get('path') || '',
                fileCount: r.get('fileCount')?.toNumber?.() || 0,
                functionCount: r.get('functionCount')?.toNumber?.() || 0,
                classCount: r.get('classCount')?.toNumber?.() || 0,
                totalLoc: r.get('totalLoc')?.toNumber?.() || 0,
                avgComplexity: r.get('avgComplexity')?.toNumber?.() || 0,
                maxComplexity: r.get('maxComplexity')?.toNumber?.() || 0,
                docCoverage: 0, // Would need separate query
                testCoverage: 0, // Would need separate query
                smellCount: 0, // Would need separate query
                dependencies: r.get('dependencies') || [],
                dependents: [], // Would need reverse query
            }));
        } catch (error) {
            this.logger.warn('Failed to fetch module stats', { error });
            return [];
        }
    }

    /**
     * Fetch complexity hotspots.
     */
    private async fetchComplexityHotspots(repositoryId: string): Promise<ComplexityHotspot[]> {
        try {
            const result = await this.neo4jClient.runTransaction(
                QUERIES.COMPLEXITY_HOTSPOTS,
                {
                    repositoryId,
                    complexityThreshold: 15,
                    cognitiveThreshold: 20,
                    limit: 10,
                },
                'READ',
                'RepositoryOverview'
            );

            return ((result as any).records || []).map((r: any) => ({
                entityId: r.get('entityId') || '',
                name: r.get('name') || '',
                filePath: r.get('filePath') || '',
                line: r.get('line')?.toNumber?.() || 0,
                kind: r.get('kind') || 'Function',
                cyclomaticComplexity: r.get('cyclomaticComplexity')?.toNumber?.() || 0,
                cognitiveComplexity: r.get('cognitiveComplexity')?.toNumber?.() || 0,
                loc: r.get('loc')?.toNumber?.() || 0,
                reason: 'High complexity',
            }));
        } catch (error) {
            this.logger.warn('Failed to fetch complexity hotspots', { error });
            return [];
        }
    }

    /**
     * Fetch entry point summary.
     */
    private async fetchEntryPointSummary(repositoryId: string): Promise<EntryPointSummary> {
        const summary: EntryPointSummary = {
            restEndpointCount: 0,
            restByMethod: {} as Record<HttpMethod, number>,
            graphqlOperationCount: 0,
            graphqlByType: {} as Record<GraphQLOperationType, number>,
            eventHandlerCount: 0,
            eventsBySource: {},
            scheduledTaskCount: 0,
            cliCommandCount: 0,
            // UI Entry Points (Phase 1)
            uiRouteCount: 0,
            uiPageCount: 0,
            uiByFramework: {} as Record<UIRoutingFramework, number>,
            protectedRouteCount: 0,
        };

        try {
            // REST endpoints
            const restResult = await this.neo4jClient.runTransaction(
                QUERIES.REST_ENDPOINTS,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );
            for (const r of (restResult as any).records || []) {
                const method = r.get('httpMethod') as HttpMethod;
                const count = r.get('count')?.toNumber?.() || 0;
                summary.restByMethod[method] = count;
                summary.restEndpointCount += count;
            }

            // GraphQL operations
            const graphqlResult = await this.neo4jClient.runTransaction(
                QUERIES.GRAPHQL_OPERATIONS,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );
            for (const r of (graphqlResult as any).records || []) {
                const type = r.get('operationType') as GraphQLOperationType;
                const count = r.get('count')?.toNumber?.() || 0;
                summary.graphqlByType[type] = count;
                summary.graphqlOperationCount += count;
            }

            // Event handlers
            const eventResult = await this.neo4jClient.runTransaction(
                QUERIES.EVENT_HANDLERS,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );
            for (const r of (eventResult as any).records || []) {
                const source = r.get('eventSource') || 'Unknown';
                const count = r.get('count')?.toNumber?.() || 0;
                summary.eventsBySource[source] = count;
                summary.eventHandlerCount += count;
            }

            // Scheduled tasks
            const scheduledResult = await this.neo4jClient.runTransaction(
                QUERIES.SCHEDULED_TASKS,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );
            summary.scheduledTaskCount = (scheduledResult as any).records?.[0]?.get('count')?.toNumber?.() || 0;

            // CLI commands
            const cliResult = await this.neo4jClient.runTransaction(
                QUERIES.CLI_COMMANDS,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );
            summary.cliCommandCount = (cliResult as any).records?.[0]?.get('count')?.toNumber?.() || 0;

            // UI Routes (Phase 1)
            const uiRoutesResult = await this.neo4jClient.runTransaction(
                QUERIES.UI_ROUTES,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );
            for (const r of (uiRoutesResult as any).records || []) {
                const framework = r.get('framework') as UIRoutingFramework;
                const count = r.get('count')?.toNumber?.() || 0;
                summary.uiByFramework[framework] = (summary.uiByFramework[framework] || 0) + count;
                summary.uiRouteCount += count;
            }

            // UI Pages (Phase 1)
            const uiPagesResult = await this.neo4jClient.runTransaction(
                QUERIES.UI_PAGES,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );
            for (const r of (uiPagesResult as any).records || []) {
                const framework = r.get('framework') as UIRoutingFramework;
                const count = r.get('count')?.toNumber?.() || 0;
                summary.uiByFramework[framework] = (summary.uiByFramework[framework] || 0) + count;
                summary.uiPageCount += count;
            }

            // Protected routes (Phase 1)
            const protectedResult = await this.neo4jClient.runTransaction(
                QUERIES.PROTECTED_ROUTES,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );
            summary.protectedRouteCount = (protectedResult as any).records?.[0]?.get('count')?.toNumber?.() || 0;

        } catch (error) {
            this.logger.warn('Failed to fetch entry point summary', { error });
        }

        return summary;
    }

    /**
     * Fetch test coverage summary.
     */
    private async fetchTestCoverage(repositoryId: string): Promise<TestCoverageSummary> {
        try {
            const result = await this.neo4jClient.runTransaction(
                QUERIES.TEST_COVERAGE,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );

            const record = (result as any).records?.[0];
            const totalFiles = record?.get('totalFiles')?.toNumber?.() || 0;
            const testFiles = record?.get('testFiles')?.toNumber?.() || 0;
            const testCaseCount = record?.get('testCaseCount')?.toNumber?.() || 0;

            return {
                testFileCount: testFiles,
                testCaseCount,
                filesWithTests: testFiles, // Simplified
                filesWithoutTests: totalFiles - testFiles,
                functionsWithTests: 0, // Would need more complex query
                functionsWithoutTests: 0,
                frameworks: [], // Would need additional query
                untestedCriticalModules: [],
            };
        } catch (error) {
            this.logger.warn('Failed to fetch test coverage', { error });
            return {
                testFileCount: 0,
                testCaseCount: 0,
                filesWithTests: 0,
                filesWithoutTests: 0,
                functionsWithTests: 0,
                functionsWithoutTests: 0,
                frameworks: [],
                untestedCriticalModules: [],
            };
        }
    }

    /**
     * Fetch documentation coverage.
     */
    private async fetchDocCoverage(repositoryId: string): Promise<{
        coverage: number;
        documented: number;
        total: number;
    }> {
        try {
            const result = await this.neo4jClient.runTransaction(
                QUERIES.DOC_COVERAGE,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );

            const record = (result as any).records?.[0];
            return {
                coverage: record?.get('coverage')?.toNumber?.() || 0,
                documented: record?.get('documented')?.toNumber?.() || 0,
                total: record?.get('totalFunctions')?.toNumber?.() || 0,
            };
        } catch (error) {
            this.logger.warn('Failed to fetch doc coverage', { error });
            return { coverage: 0, documented: 0, total: 0 };
        }
    }

    /**
     * Fetch code smells by severity.
     */
    private async fetchSmellsBySeverity(repositoryId: string): Promise<Record<CodeSmellSeverity, number>> {
        const result: Record<CodeSmellSeverity, number> = {
            info: 0,
            low: 0,
            medium: 0,
            high: 0,
            critical: 0,
        };

        try {
            const queryResult = await this.neo4jClient.runTransaction(
                QUERIES.CODE_SMELLS_BY_SEVERITY,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );

            for (const r of (queryResult as any).records || []) {
                const severity = r.get('severity') as CodeSmellSeverity;
                const count = r.get('count')?.toNumber?.() || 0;
                if (severity in result) {
                    result[severity] = count;
                }
            }
        } catch (error) {
            this.logger.warn('Failed to fetch smells by severity', { error });
        }

        return result;
    }

    /**
     * Fetch stereotype distribution.
     */
    private async fetchStereotypeDistribution(repositoryId: string): Promise<Record<string, number>> {
        const result: Record<string, number> = {};

        try {
            const queryResult = await this.neo4jClient.runTransaction(
                QUERIES.STEREOTYPE_DISTRIBUTION,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );

            for (const r of (queryResult as any).records || []) {
                const stereotype = r.get('stereotype') || 'Unknown';
                const count = r.get('count')?.toNumber?.() || 0;
                result[stereotype] = count;
            }
        } catch (error) {
            this.logger.warn('Failed to fetch stereotype distribution', { error });
        }

        return result;
    }

    /**
     * Fetch starting points for new developers.
     */
    private async fetchStartingPoints(repositoryId: string): Promise<any[]> {
        try {
            const result = await this.neo4jClient.runTransaction(
                QUERIES.STARTING_POINTS,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );

            return ((result as any).records || []).map((r: any) => ({
                entityId: r.get('entityId'),
                name: r.get('name'),
                filePath: r.get('filePath'),
                type: r.get('type'),
                priority: r.get('priority')?.toNumber?.() || 10,
            }));
        } catch (error) {
            this.logger.warn('Failed to fetch starting points', { error });
            return [];
        }
    }

    /**
     * Fetch module dependency graph.
     */
    private async fetchModuleDependencyGraph(repositoryId: string): Promise<
        { source: string; target: string; weight: number }[]
    > {
        try {
            const result = await this.neo4jClient.runTransaction(
                QUERIES.MODULE_DEPENDENCY_GRAPH,
                { repositoryId },
                'READ',
                'RepositoryOverview'
            );

            return ((result as any).records || [])
                .filter((r: any) => r.get('target'))
                .map((r: any) => ({
                    source: r.get('source') || '',
                    target: r.get('target') || '',
                    weight: r.get('weight')?.toNumber?.() || 1,
                }));
        } catch (error) {
            this.logger.warn('Failed to fetch module dependency graph', { error });
            return [];
        }
    }

    /**
     * Detect architecture patterns from stereotype distribution.
     */
    private detectArchitecturePatterns(
        stereotypes: Record<string, number>,
        modules: ModuleStats[]
    ): ArchitecturePattern[] {
        const patterns: ArchitecturePattern[] = [];

        // Check for layered architecture
        const hasControllers = (stereotypes['Controller'] || 0) > 0;
        const hasServices = (stereotypes['Service'] || 0) > 0;
        const hasRepositories = (stereotypes['Repository'] || 0) > 0;

        if (hasControllers && hasServices && hasRepositories) {
            patterns.push({
                name: 'Layered Architecture',
                confidence: 0.85,
                evidence: [
                    'Controllers detected (presentation layer)',
                    'Services detected (business layer)',
                    'Repositories detected (data layer)',
                ],
                layers: ['presentation', 'business', 'data'],
            });
        }

        // Check for MVC
        if (hasControllers && (stereotypes['Entity'] || 0) > 0) {
            patterns.push({
                name: 'MVC Pattern',
                confidence: 0.75,
                evidence: [
                    'Controllers detected',
                    'Entity/Model classes detected',
                ],
            });
        }

        // Check for microservices (multiple modules with clear boundaries)
        if (modules.length > 3) {
            const avgDeps = modules.reduce((sum, m) => sum + m.dependencies.length, 0) / modules.length;
            if (avgDeps < 3) {
                patterns.push({
                    name: 'Modular Architecture',
                    confidence: 0.70,
                    evidence: [
                        `${modules.length} independent modules detected`,
                        'Low inter-module coupling',
                    ],
                });
            }
        }

        return patterns;
    }

    /**
     * Infer architectural layers from stereotypes.
     */
    private inferLayers(stereotypes: Record<string, number>): string[] {
        const layers: string[] = [];

        if ((stereotypes['Controller'] || 0) > 0 || (stereotypes['DTO'] || 0) > 0) {
            layers.push('presentation');
        }
        if ((stereotypes['Service'] || 0) > 0 || (stereotypes['Handler'] || 0) > 0) {
            layers.push('business');
        }
        if ((stereotypes['Repository'] || 0) > 0 || (stereotypes['Entity'] || 0) > 0) {
            layers.push('data');
        }
        if ((stereotypes['Configuration'] || 0) > 0 || (stereotypes['Client'] || 0) > 0) {
            layers.push('infrastructure');
        }

        return layers;
    }

    /**
     * Generate recommendations for new developers.
     */
    private generateRecommendations(
        startingPoints: any[],
        hotspots: ComplexityHotspot[],
        entryPoints: EntryPointSummary
    ): StartingPointRecommendation[] {
        const recommendations: StartingPointRecommendation[] = [];

        // Add entry points as starting recommendations
        for (const sp of startingPoints.slice(0, 5)) {
            let reason = 'Starting point for understanding the codebase';
            if (sp.type === 'entry-point') {
                reason = 'Entry point - start here to understand the API surface';
            } else if (sp.type === 'core-module') {
                reason = 'Core service - contains important business logic';
            }

            recommendations.push({
                type: sp.type,
                entityId: sp.entityId,
                name: sp.name,
                filePath: sp.filePath,
                reason,
                priority: sp.priority,
            });
        }

        // Add recommendations to address hotspots
        if (hotspots.length > 0) {
            const worstHotspot = hotspots[0]!;
            recommendations.push({
                type: 'documentation',
                entityId: worstHotspot.entityId,
                name: worstHotspot.name,
                filePath: worstHotspot.filePath,
                reason: `High complexity (${worstHotspot.cognitiveComplexity}) - consider refactoring`,
                priority: 5,
            });
        }

        // Sort by priority
        return recommendations.sort((a, b) => a.priority - b.priority);
    }

    /**
     * Calculate average complexity from hotspots.
     */
    private calculateAvgComplexity(hotspots: ComplexityHotspot[]): number {
        if (hotspots.length === 0) return 0;
        const sum = hotspots.reduce((acc, h) => acc + h.cyclomaticComplexity, 0);
        return Math.round(sum / hotspots.length * 10) / 10;
    }

    /**
     * Calculate average cognitive complexity from hotspots.
     */
    private calculateAvgCognitiveComplexity(hotspots: ComplexityHotspot[]): number {
        if (hotspots.length === 0) return 0;
        const sum = hotspots.reduce((acc, h) => acc + h.cognitiveComplexity, 0);
        return Math.round(sum / hotspots.length * 10) / 10;
    }
}

// =============================================================================
// Convenience Functions
// =============================================================================

export function createRepositoryOverviewService(
    neo4jClient: Neo4jClient,
    logger: winston.Logger
): RepositoryOverviewService {
    return new RepositoryOverviewService(neo4jClient, logger);
}
