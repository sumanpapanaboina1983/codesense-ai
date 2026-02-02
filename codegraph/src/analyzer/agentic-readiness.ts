// src/analyzer/agentic-readiness.ts
/**
 * Agentic Readiness Service
 * Generates a comprehensive assessment of a repository's readiness for agentic automation.
 * Evaluates:
 * - Testing coverage and quality
 * - Documentation coverage and quality
 * - Critical gaps and recommendations
 * - Available enrichment actions
 */

import winston from 'winston';
import { Neo4jClient } from '../database/neo4j-client.js';
import {
    AgenticReadinessReport,
    TestingReadiness,
    DocumentationReadiness,
    ReadinessGrade,
    ReadinessRecommendation,
    EnrichmentAction,
    DocumentationQuality,
    TestFramework,
    Stereotype,
} from './types.js';

// =============================================================================
// Grade Thresholds
// =============================================================================

const GRADE_THRESHOLDS = {
    A: 90,
    B: 75,
    C: 60,
    D: 40,
    F: 0,
};

function scoreToGrade(score: number): ReadinessGrade {
    if (score >= GRADE_THRESHOLDS.A) return 'A';
    if (score >= GRADE_THRESHOLDS.B) return 'B';
    if (score >= GRADE_THRESHOLDS.C) return 'C';
    if (score >= GRADE_THRESHOLDS.D) return 'D';
    return 'F';
}

// =============================================================================
// Readiness Queries
// =============================================================================

const READINESS_QUERIES = {
    // Total functions and methods
    TOTAL_FUNCTIONS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION*1..2]->(fn)
        WHERE fn:Function OR fn:Method OR fn:JavaMethod OR fn:GoFunction OR fn:CSharpMethod
        RETURN count(fn) as total
    `,

    // Functions with tests
    FUNCTIONS_WITH_TESTS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION*1..2]->(fn)
        WHERE (fn:Function OR fn:Method OR fn:JavaMethod OR fn:GoFunction OR fn:CSharpMethod)
        MATCH (test)-[:TESTS|COVERS]->(fn)
        RETURN count(DISTINCT fn) as testedCount
    `,

    // Untested critical functions (controllers, services, entry points)
    UNTESTED_CRITICAL_FUNCTIONS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION*1..2]->(fn)
        WHERE (fn:Function OR fn:Method OR fn:JavaMethod OR fn:GoFunction OR fn:CSharpMethod)
          AND (fn.stereotype IN ['Controller', 'Service'] OR fn.entryPointType IS NOT NULL)
        OPTIONAL MATCH (test)-[:TESTS|COVERS]->(fn)
        WITH fn, count(test) as testCount
        WHERE testCount = 0
        RETURN fn.entityId as entityId, fn.name as name, fn.filePath as filePath,
               fn.stereotype as stereotype,
               CASE
                   WHEN fn.stereotype = 'Controller' THEN 'Controller method without test coverage'
                   WHEN fn.stereotype = 'Service' THEN 'Service method without test coverage'
                   WHEN fn.entryPointType IS NOT NULL THEN 'Entry point without test coverage'
                   ELSE 'Critical function without test coverage'
               END as reason
        LIMIT 50
    `,

    // Test file count and frameworks
    TEST_STATS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(tf:TestFile)
        RETURN count(tf) as testFileCount,
               collect(DISTINCT tf.testFramework) as frameworks,
               sum(tf.testCount) as totalTests
    `,

    // Check for different test types
    TEST_TYPES: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(tf:TestFile)
        RETURN
            sum(CASE WHEN tf.filePath =~ '(?i).*unit.*' OR tf.filePath =~ '(?i).*\\.spec\\..*' THEN 1 ELSE 0 END) as unitTests,
            sum(CASE WHEN tf.filePath =~ '(?i).*integration.*' OR tf.filePath =~ '(?i).*\\.int\\..*' THEN 1 ELSE 0 END) as integrationTests,
            sum(CASE WHEN tf.filePath =~ '(?i).*e2e.*|.*cypress.*|.*playwright.*' THEN 1 ELSE 0 END) as e2eTests
    `,

    // Functions with documentation
    DOCUMENTED_FUNCTIONS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION*1..2]->(fn)
        WHERE fn:Function OR fn:Method OR fn:JavaMethod OR fn:GoFunction OR fn:CSharpMethod
        RETURN
            count(fn) as total,
            sum(CASE WHEN fn.hasDocumentation = true THEN 1 ELSE 0 END) as documented
    `,

    // Public API coverage (exported/public entities)
    PUBLIC_API_COVERAGE: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION|DEFINES_CLASS*1..2]->(n)
        WHERE (n:Function OR n:Method OR n:Class OR n:JavaClass OR n:JavaMethod)
          AND (n.isExported = true OR n.visibility = 'public')
        RETURN
            count(n) as total,
            sum(CASE WHEN n.hasDocumentation = true THEN 1 ELSE 0 END) as documented
    `,

    // Undocumented public APIs
    UNDOCUMENTED_PUBLIC_APIS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION|DEFINES_CLASS*1..2]->(n)
        WHERE (n:Function OR n:Method OR n:Class OR n:JavaClass OR n:JavaMethod)
          AND (n.isExported = true OR n.visibility = 'public')
          AND (n.hasDocumentation IS NULL OR n.hasDocumentation = false)
        RETURN n.entityId as entityId, n.name as name, n.filePath as filePath,
               labels(n)[0] as kind, n.signature as signature
        LIMIT 100
    `,

    // Documentation quality distribution
    DOC_QUALITY_DISTRIBUTION: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION*1..2]->(fn)
        WHERE fn:Function OR fn:Method OR fn:JavaMethod
        RETURN
            sum(CASE WHEN fn.docQuality = 'excellent' THEN 1 ELSE 0 END) as excellent,
            sum(CASE WHEN fn.docQuality = 'good' THEN 1 ELSE 0 END) as good,
            sum(CASE WHEN fn.docQuality = 'partial' THEN 1 ELSE 0 END) as partial,
            sum(CASE WHEN fn.docQuality = 'minimal' THEN 1 ELSE 0 END) as minimal,
            sum(CASE WHEN fn.docQuality IS NULL OR fn.docQuality = 'none' THEN 1 ELSE 0 END) as none
    `,

    // Summary statistics
    SUMMARY_STATS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        OPTIONAL MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION*1..2]->(fn)
        WHERE fn:Function OR fn:Method OR fn:JavaMethod
        OPTIONAL MATCH (f)-[:CONTAINS|DEFINES_CLASS*1..2]->(c)
        WHERE c:Class OR c:JavaClass
        RETURN
            count(DISTINCT fn) + count(DISTINCT c) as totalEntities,
            sum(CASE WHEN fn.hasDocumentation = true OR c.hasDocumentation = true THEN 1 ELSE 0 END) as documented
    `,
};

// =============================================================================
// Agentic Readiness Service
// =============================================================================

export class AgenticReadinessService {
    private logger: winston.Logger;
    private neo4jClient: Neo4jClient;

    constructor(neo4jClient: Neo4jClient, logger: winston.Logger) {
        this.neo4jClient = neo4jClient;
        this.logger = logger;
    }

    /**
     * Generate a complete Agentic Readiness Report for a repository.
     */
    async generateReport(repositoryId: string, repositoryName: string): Promise<AgenticReadinessReport> {
        this.logger.info(`Generating Agentic Readiness Report for ${repositoryId}`);
        const startTime = Date.now();

        try {
            // Fetch all metrics in parallel
            const [
                testingReadiness,
                documentationReadiness,
                summaryStats,
            ] = await Promise.all([
                this.assessTestingReadiness(repositoryId),
                this.assessDocumentationReadiness(repositoryId),
                this.fetchSummaryStats(repositoryId),
            ]);

            // Calculate overall score (50% testing, 50% documentation)
            const overallScore = Math.round(
                (testingReadiness.overallScore * 0.5) + (documentationReadiness.overallScore * 0.5)
            );
            const overallGrade = scoreToGrade(overallScore);
            const isAgenticReady = overallScore >= GRADE_THRESHOLDS.B;

            // Generate recommendations
            const recommendations = this.generateRecommendations(testingReadiness, documentationReadiness);

            // Generate enrichment actions
            const enrichmentActions = this.generateEnrichmentActions(testingReadiness, documentationReadiness);

            // Calculate critical gaps
            const criticalGaps = testingReadiness.untestedCriticalFunctions.length +
                documentationReadiness.undocumentedPublicApis.length;

            const report: AgenticReadinessReport = {
                repositoryId,
                repositoryName,
                generatedAt: new Date().toISOString(),

                overallGrade,
                overallScore,
                isAgenticReady,

                testing: testingReadiness,
                documentation: documentationReadiness,

                recommendations,
                enrichmentActions,

                summary: {
                    totalEntities: summaryStats.totalEntities,
                    testedEntities: summaryStats.testedEntities,
                    documentedEntities: summaryStats.documentedEntities,
                    criticalGaps,
                },
            };

            const duration = Date.now() - startTime;
            this.logger.info(`Agentic Readiness Report generated in ${duration}ms`, {
                overallGrade,
                overallScore,
                isAgenticReady,
            });

            return report;
        } catch (error: any) {
            this.logger.error('Failed to generate Agentic Readiness Report', { error: error.message });
            throw error;
        }
    }

    // =========================================================================
    // Testing Readiness Assessment
    // =========================================================================

    private async assessTestingReadiness(repositoryId: string): Promise<TestingReadiness> {
        // Fetch test statistics
        const [
            totalFunctions,
            testedFunctions,
            untestedCritical,
            testStats,
            testTypes,
        ] = await Promise.all([
            this.fetchTotalFunctions(repositoryId),
            this.fetchTestedFunctions(repositoryId),
            this.fetchUntestedCriticalFunctions(repositoryId),
            this.fetchTestStats(repositoryId),
            this.fetchTestTypes(repositoryId),
        ]);

        // Calculate coverage
        const coveragePercentage = totalFunctions > 0
            ? Math.round((testedFunctions / totalFunctions) * 100)
            : 0;
        const coverageGrade = scoreToGrade(coveragePercentage);

        // Calculate overall score
        // Base score from coverage, with penalties for untested critical functions
        let overallScore = coveragePercentage;

        // Penalty for untested critical functions (up to 20 points)
        const criticalPenalty = Math.min(untestedCritical.length * 2, 20);
        overallScore = Math.max(0, overallScore - criticalPenalty);

        // Bonus for having different test types (up to 10 points)
        let testTypeBonus = 0;
        if (testTypes.hasUnitTests) testTypeBonus += 4;
        if (testTypes.hasIntegrationTests) testTypeBonus += 3;
        if (testTypes.hasE2ETests) testTypeBonus += 3;
        overallScore = Math.min(100, overallScore + testTypeBonus);

        const overallGrade = scoreToGrade(overallScore);

        // Generate recommendations
        const recommendations: string[] = [];
        if (coveragePercentage < 50) {
            recommendations.push('Increase test coverage to at least 50%');
        }
        if (untestedCritical.length > 0) {
            recommendations.push(`Add tests for ${untestedCritical.length} critical untested functions`);
        }
        if (!testTypes.hasIntegrationTests) {
            recommendations.push('Add integration tests for API endpoints and service interactions');
        }
        if (!testTypes.hasE2ETests) {
            recommendations.push('Consider adding E2E tests for critical user flows');
        }

        return {
            overallGrade,
            overallScore,
            coverage: {
                percentage: coveragePercentage,
                grade: coverageGrade,
            },
            untestedCriticalFunctions: untestedCritical,
            testQuality: {
                hasUnitTests: testTypes.hasUnitTests,
                hasIntegrationTests: testTypes.hasIntegrationTests,
                hasE2ETests: testTypes.hasE2ETests,
                frameworks: testStats.frameworks as TestFramework[],
            },
            recommendations,
        };
    }

    private async fetchTotalFunctions(repositoryId: string): Promise<number> {
        try {
            const result = await this.neo4jClient.runTransaction(
                READINESS_QUERIES.TOTAL_FUNCTIONS,
                { repositoryId },
                'READ',
                'AgenticReadiness'
            );
            return (result as any).records?.[0]?.get('total')?.toNumber?.() || 0;
        } catch (error) {
            this.logger.warn('Failed to fetch total functions', { error });
            return 0;
        }
    }

    private async fetchTestedFunctions(repositoryId: string): Promise<number> {
        try {
            const result = await this.neo4jClient.runTransaction(
                READINESS_QUERIES.FUNCTIONS_WITH_TESTS,
                { repositoryId },
                'READ',
                'AgenticReadiness'
            );
            return (result as any).records?.[0]?.get('testedCount')?.toNumber?.() || 0;
        } catch (error) {
            this.logger.warn('Failed to fetch tested functions', { error });
            return 0;
        }
    }

    private async fetchUntestedCriticalFunctions(repositoryId: string): Promise<
        TestingReadiness['untestedCriticalFunctions']
    > {
        try {
            const result = await this.neo4jClient.runTransaction(
                READINESS_QUERIES.UNTESTED_CRITICAL_FUNCTIONS,
                { repositoryId },
                'READ',
                'AgenticReadiness'
            );
            return ((result as any).records || []).map((r: any) => ({
                entityId: r.get('entityId'),
                name: r.get('name'),
                filePath: r.get('filePath'),
                reason: r.get('reason'),
                stereotype: r.get('stereotype') as Stereotype | undefined,
            }));
        } catch (error) {
            this.logger.warn('Failed to fetch untested critical functions', { error });
            return [];
        }
    }

    private async fetchTestStats(repositoryId: string): Promise<{
        testFileCount: number;
        frameworks: string[];
        totalTests: number;
    }> {
        try {
            const result = await this.neo4jClient.runTransaction(
                READINESS_QUERIES.TEST_STATS,
                { repositoryId },
                'READ',
                'AgenticReadiness'
            );
            const record = (result as any).records?.[0];
            return {
                testFileCount: record?.get('testFileCount')?.toNumber?.() || 0,
                frameworks: record?.get('frameworks') || [],
                totalTests: record?.get('totalTests')?.toNumber?.() || 0,
            };
        } catch (error) {
            this.logger.warn('Failed to fetch test stats', { error });
            return { testFileCount: 0, frameworks: [], totalTests: 0 };
        }
    }

    private async fetchTestTypes(repositoryId: string): Promise<{
        hasUnitTests: boolean;
        hasIntegrationTests: boolean;
        hasE2ETests: boolean;
    }> {
        try {
            const result = await this.neo4jClient.runTransaction(
                READINESS_QUERIES.TEST_TYPES,
                { repositoryId },
                'READ',
                'AgenticReadiness'
            );
            const record = (result as any).records?.[0];
            return {
                hasUnitTests: (record?.get('unitTests')?.toNumber?.() || 0) > 0,
                hasIntegrationTests: (record?.get('integrationTests')?.toNumber?.() || 0) > 0,
                hasE2ETests: (record?.get('e2eTests')?.toNumber?.() || 0) > 0,
            };
        } catch (error) {
            this.logger.warn('Failed to fetch test types', { error });
            return { hasUnitTests: false, hasIntegrationTests: false, hasE2ETests: false };
        }
    }

    // =========================================================================
    // Documentation Readiness Assessment
    // =========================================================================

    private async assessDocumentationReadiness(repositoryId: string): Promise<DocumentationReadiness> {
        const [
            docCoverage,
            publicApiCoverage,
            undocumentedApis,
            qualityDistribution,
        ] = await Promise.all([
            this.fetchDocCoverage(repositoryId),
            this.fetchPublicApiCoverage(repositoryId),
            this.fetchUndocumentedPublicApis(repositoryId),
            this.fetchDocQualityDistribution(repositoryId),
        ]);

        const coverageGrade = scoreToGrade(docCoverage.percentage);
        const publicApiGrade = scoreToGrade(publicApiCoverage.percentage);

        // Calculate overall score
        // Weight public API coverage more heavily (60% public API, 40% overall)
        let overallScore = Math.round(
            (publicApiCoverage.percentage * 0.6) + (docCoverage.percentage * 0.4)
        );

        // Penalty for undocumented public APIs (up to 15 points)
        const undocPenalty = Math.min(undocumentedApis.length * 0.5, 15);
        overallScore = Math.max(0, overallScore - undocPenalty);

        const overallGrade = scoreToGrade(overallScore);

        // Generate recommendations
        const recommendations: string[] = [];
        if (publicApiCoverage.percentage < 80) {
            recommendations.push('Document all public APIs (exported functions, classes, interfaces)');
        }
        if (undocumentedApis.length > 10) {
            recommendations.push(`Add documentation to ${undocumentedApis.length} undocumented public entities`);
        }
        if (qualityDistribution.minimal > qualityDistribution.good + qualityDistribution.excellent) {
            recommendations.push('Improve documentation quality with more detailed descriptions and examples');
        }

        return {
            overallGrade,
            overallScore,
            coverage: {
                percentage: docCoverage.percentage,
                grade: coverageGrade,
            },
            publicApiCoverage: {
                percentage: publicApiCoverage.percentage,
                grade: publicApiGrade,
            },
            undocumentedPublicApis: undocumentedApis,
            qualityDistribution,
            recommendations,
        };
    }

    private async fetchDocCoverage(repositoryId: string): Promise<{ percentage: number }> {
        try {
            const result = await this.neo4jClient.runTransaction(
                READINESS_QUERIES.DOCUMENTED_FUNCTIONS,
                { repositoryId },
                'READ',
                'AgenticReadiness'
            );
            const record = (result as any).records?.[0];
            const total = record?.get('total')?.toNumber?.() || 0;
            const documented = record?.get('documented')?.toNumber?.() || 0;
            return {
                percentage: total > 0 ? Math.round((documented / total) * 100) : 0,
            };
        } catch (error) {
            this.logger.warn('Failed to fetch doc coverage', { error });
            return { percentage: 0 };
        }
    }

    private async fetchPublicApiCoverage(repositoryId: string): Promise<{ percentage: number }> {
        try {
            const result = await this.neo4jClient.runTransaction(
                READINESS_QUERIES.PUBLIC_API_COVERAGE,
                { repositoryId },
                'READ',
                'AgenticReadiness'
            );
            const record = (result as any).records?.[0];
            const total = record?.get('total')?.toNumber?.() || 0;
            const documented = record?.get('documented')?.toNumber?.() || 0;
            return {
                percentage: total > 0 ? Math.round((documented / total) * 100) : 0,
            };
        } catch (error) {
            this.logger.warn('Failed to fetch public API coverage', { error });
            return { percentage: 0 };
        }
    }

    private async fetchUndocumentedPublicApis(repositoryId: string): Promise<
        DocumentationReadiness['undocumentedPublicApis']
    > {
        try {
            const result = await this.neo4jClient.runTransaction(
                READINESS_QUERIES.UNDOCUMENTED_PUBLIC_APIS,
                { repositoryId },
                'READ',
                'AgenticReadiness'
            );
            return ((result as any).records || []).map((r: any) => ({
                entityId: r.get('entityId'),
                name: r.get('name'),
                filePath: r.get('filePath'),
                kind: r.get('kind'),
                signature: r.get('signature'),
            }));
        } catch (error) {
            this.logger.warn('Failed to fetch undocumented public APIs', { error });
            return [];
        }
    }

    private async fetchDocQualityDistribution(repositoryId: string): Promise<
        Record<DocumentationQuality, number>
    > {
        const defaultDist: Record<DocumentationQuality, number> = {
            excellent: 0,
            good: 0,
            partial: 0,
            minimal: 0,
            none: 0,
        };

        try {
            const result = await this.neo4jClient.runTransaction(
                READINESS_QUERIES.DOC_QUALITY_DISTRIBUTION,
                { repositoryId },
                'READ',
                'AgenticReadiness'
            );
            const record = (result as any).records?.[0];
            if (record) {
                return {
                    excellent: record.get('excellent')?.toNumber?.() || 0,
                    good: record.get('good')?.toNumber?.() || 0,
                    partial: record.get('partial')?.toNumber?.() || 0,
                    minimal: record.get('minimal')?.toNumber?.() || 0,
                    none: record.get('none')?.toNumber?.() || 0,
                };
            }
            return defaultDist;
        } catch (error) {
            this.logger.warn('Failed to fetch doc quality distribution', { error });
            return defaultDist;
        }
    }

    // =========================================================================
    // Summary Statistics
    // =========================================================================

    private async fetchSummaryStats(repositoryId: string): Promise<{
        totalEntities: number;
        testedEntities: number;
        documentedEntities: number;
    }> {
        try {
            const [summaryResult, testedCount] = await Promise.all([
                this.neo4jClient.runTransaction(
                    READINESS_QUERIES.SUMMARY_STATS,
                    { repositoryId },
                    'READ',
                    'AgenticReadiness'
                ),
                this.fetchTestedFunctions(repositoryId),
            ]);

            const record = (summaryResult as any).records?.[0];
            return {
                totalEntities: record?.get('totalEntities')?.toNumber?.() || 0,
                testedEntities: testedCount,
                documentedEntities: record?.get('documented')?.toNumber?.() || 0,
            };
        } catch (error) {
            this.logger.warn('Failed to fetch summary stats', { error });
            return { totalEntities: 0, testedEntities: 0, documentedEntities: 0 };
        }
    }

    // =========================================================================
    // Recommendations Generator
    // =========================================================================

    private generateRecommendations(
        testing: TestingReadiness,
        documentation: DocumentationReadiness
    ): ReadinessRecommendation[] {
        const recommendations: ReadinessRecommendation[] = [];

        // High priority: Untested critical functions
        if (testing.untestedCriticalFunctions.length > 0) {
            recommendations.push({
                priority: 'high',
                category: 'testing',
                title: 'Add Tests for Critical Functions',
                description: `${testing.untestedCriticalFunctions.length} critical functions (controllers, services, entry points) lack test coverage. These are high-risk areas that should be tested.`,
                affectedCount: testing.untestedCriticalFunctions.length,
                affectedEntities: testing.untestedCriticalFunctions.slice(0, 10).map(f => f.entityId),
                estimatedEffort: testing.untestedCriticalFunctions.length > 20 ? 'high' : 'medium',
            });
        }

        // High priority: Low test coverage
        if (testing.coverage.percentage < 50) {
            recommendations.push({
                priority: 'high',
                category: 'testing',
                title: 'Increase Test Coverage',
                description: `Current test coverage is ${testing.coverage.percentage}%. Aim for at least 70% coverage for reliable agentic automation.`,
                affectedCount: 0,
                estimatedEffort: 'high',
            });
        }

        // High priority: Undocumented public APIs
        if (documentation.undocumentedPublicApis.length > 10) {
            recommendations.push({
                priority: 'high',
                category: 'documentation',
                title: 'Document Public APIs',
                description: `${documentation.undocumentedPublicApis.length} public APIs lack documentation. This impacts code understanding and API discoverability.`,
                affectedCount: documentation.undocumentedPublicApis.length,
                affectedEntities: documentation.undocumentedPublicApis.slice(0, 10).map(a => a.entityId),
                estimatedEffort: documentation.undocumentedPublicApis.length > 50 ? 'high' : 'medium',
            });
        }

        // Medium priority: Missing integration tests
        if (!testing.testQuality.hasIntegrationTests) {
            recommendations.push({
                priority: 'medium',
                category: 'testing',
                title: 'Add Integration Tests',
                description: 'No integration tests detected. Integration tests are crucial for validating service interactions and API contracts.',
                affectedCount: 0,
                estimatedEffort: 'medium',
            });
        }

        // Medium priority: Low documentation coverage
        if (documentation.coverage.percentage < 50) {
            recommendations.push({
                priority: 'medium',
                category: 'documentation',
                title: 'Improve Documentation Coverage',
                description: `Only ${documentation.coverage.percentage}% of functions are documented. Better documentation improves maintainability and onboarding.`,
                affectedCount: 0,
                estimatedEffort: 'medium',
            });
        }

        // Low priority: Missing E2E tests
        if (!testing.testQuality.hasE2ETests) {
            recommendations.push({
                priority: 'low',
                category: 'testing',
                title: 'Consider Adding E2E Tests',
                description: 'No end-to-end tests detected. E2E tests validate complete user flows and catch integration issues.',
                affectedCount: 0,
                estimatedEffort: 'high',
            });
        }

        // Sort by priority
        const priorityOrder = { high: 0, medium: 1, low: 2 };
        return recommendations.sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority]);
    }

    // =========================================================================
    // Enrichment Actions Generator
    // =========================================================================

    private generateEnrichmentActions(
        testing: TestingReadiness,
        documentation: DocumentationReadiness
    ): EnrichmentAction[] {
        const actions: EnrichmentAction[] = [];

        // Documentation enrichment
        if (documentation.undocumentedPublicApis.length > 0) {
            actions.push({
                id: 'enrich-docs-public-api',
                name: 'Generate Documentation for Public APIs',
                description: 'Auto-generate JSDoc/JavaDoc documentation for all undocumented public functions and classes.',
                affectedEntities: documentation.undocumentedPublicApis.length,
                category: 'documentation',
                isAutomated: true,
            });
        }

        // Test generation for critical functions
        if (testing.untestedCriticalFunctions.length > 0) {
            actions.push({
                id: 'enrich-tests-critical',
                name: 'Generate Tests for Critical Functions',
                description: 'Auto-generate test skeletons for untested controller and service methods.',
                affectedEntities: testing.untestedCriticalFunctions.length,
                category: 'testing',
                isAutomated: true,
            });
        }

        // General test enrichment
        const testedPercentage = testing.coverage.percentage;
        if (testedPercentage < 70) {
            const untested = Math.round(((100 - testedPercentage) / 100) * 100); // Rough estimate
            actions.push({
                id: 'enrich-tests-coverage',
                name: 'Boost Test Coverage',
                description: 'Generate unit tests for functions and methods to increase overall test coverage.',
                affectedEntities: untested,
                category: 'testing',
                isAutomated: true,
            });
        }

        // Documentation quality improvement
        const lowQualityDocs = documentation.qualityDistribution.minimal + documentation.qualityDistribution.partial;
        if (lowQualityDocs > 10) {
            actions.push({
                id: 'enrich-docs-quality',
                name: 'Improve Documentation Quality',
                description: 'Enhance existing minimal documentation with more detailed descriptions and examples.',
                affectedEntities: lowQualityDocs,
                category: 'documentation',
                isAutomated: true,
            });
        }

        return actions;
    }
}

// =============================================================================
// Factory Function
// =============================================================================

export function createAgenticReadinessService(
    neo4jClient: Neo4jClient,
    logger: winston.Logger
): AgenticReadinessService {
    return new AgenticReadinessService(neo4jClient, logger);
}
