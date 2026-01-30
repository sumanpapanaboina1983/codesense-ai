// src/analyzer/repository-overview.spec.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    RepositoryOverviewService,
    createRepositoryOverviewService,
} from './repository-overview.js';
import { Neo4jClient } from '../database/neo4j-client.js';
import { DetectedFramework } from './types.js';
import winston from 'winston';

describe('RepositoryOverviewService', () => {
    let service: RepositoryOverviewService;
    let mockLogger: winston.Logger;
    let mockNeo4jClient: Neo4jClient;

    beforeEach(() => {
        mockLogger = {
            info: vi.fn(),
            debug: vi.fn(),
            warn: vi.fn(),
            error: vi.fn(),
        } as unknown as winston.Logger;

        mockNeo4jClient = {
            runTransaction: vi.fn(),
        } as unknown as Neo4jClient;

        service = new RepositoryOverviewService(mockNeo4jClient, mockLogger);
    });

    // Helper to create mock Neo4j record results
    const createMockRecord = (data: Record<string, any>) => ({
        get: (key: string) => {
            const value = data[key];
            // Simulate Neo4j integer wrapper
            if (typeof value === 'number') {
                return { toNumber: () => value };
            }
            return value;
        },
    });

    const createMockResult = (records: Record<string, any>[]) => ({
        records: records.map(createMockRecord),
    });

    describe('generateOverview', () => {
        it('should generate a complete repository overview', async () => {
            // Mock all Neo4j queries
            vi.mocked(mockNeo4jClient.runTransaction).mockImplementation(
                async (query: string) => {
                    // Match query to return appropriate mock data
                    if (query.includes('totalFiles')) {
                        return createMockResult([{
                            totalFiles: 50,
                            totalFunctions: 200,
                            totalClasses: 30,
                            totalLoc: 10000,
                        }]);
                    }
                    if (query.includes('f.language as language')) {
                        return createMockResult([
                            { language: 'TypeScript', fileCount: 30, loc: 6000 },
                            { language: 'Java', fileCount: 20, loc: 4000 },
                        ]);
                    }
                    if (query.includes('HAS_MODULE')) {
                        return createMockResult([{
                            name: 'core',
                            path: '/modules/core',
                            fileCount: 10,
                            functionCount: 50,
                            classCount: 10,
                            totalLoc: 2000,
                            avgComplexity: 5,
                            maxComplexity: 15,
                            dependencies: ['utils'],
                        }]);
                    }
                    if (query.includes('complexityThreshold')) {
                        return createMockResult([{
                            entityId: 'func1',
                            name: 'complexFunction',
                            filePath: '/src/complex.ts',
                            line: 10,
                            kind: 'Function',
                            cyclomaticComplexity: 20,
                            cognitiveComplexity: 25,
                            loc: 100,
                        }]);
                    }
                    if (query.includes('RestEndpoint')) {
                        return createMockResult([
                            { httpMethod: 'GET', count: 10 },
                            { httpMethod: 'POST', count: 5 },
                        ]);
                    }
                    if (query.includes('GraphQLOperation')) {
                        return createMockResult([
                            { operationType: 'Query', count: 8 },
                            { operationType: 'Mutation', count: 3 },
                        ]);
                    }
                    if (query.includes('EventHandler')) {
                        return createMockResult([
                            { eventSource: 'Kafka', count: 5 },
                        ]);
                    }
                    if (query.includes('ScheduledTask')) {
                        return createMockResult([{ count: 2 }]);
                    }
                    if (query.includes('CLICommand')) {
                        return createMockResult([{ count: 1 }]);
                    }
                    if (query.includes('TestFile')) {
                        return createMockResult([{
                            totalFiles: 50,
                            testFiles: 20,
                            testCaseCount: 100,
                        }]);
                    }
                    if (query.includes('hasDocumentation')) {
                        return createMockResult([{
                            totalFunctions: 200,
                            documented: 150,
                            coverage: 0.75,
                        }]);
                    }
                    if (query.includes('codeSmells')) {
                        return createMockResult([
                            { severity: 'low', count: 10 },
                            { severity: 'medium', count: 5 },
                            { severity: 'high', count: 2 },
                        ]);
                    }
                    if (query.includes('c.stereotype')) {
                        return createMockResult([
                            { stereotype: 'Controller', count: 5 },
                            { stereotype: 'Service', count: 10 },
                            { stereotype: 'Repository', count: 8 },
                        ]);
                    }
                    if (query.includes('STARTING_POINTS') || query.includes('starting')) {
                        return createMockResult([{
                            entityId: 'ctrl1',
                            name: 'UserController',
                            filePath: '/src/controllers/UserController.java',
                            type: 'entry-point',
                            priority: 1,
                        }]);
                    }
                    if (query.includes('DEPENDS_ON_MODULE')) {
                        return createMockResult([
                            { source: 'core', target: 'utils', weight: 1 },
                        ]);
                    }
                    return createMockResult([]);
                }
            );

            const frameworks: DetectedFramework[] = [
                { name: 'Spring Boot', version: '3.0', confidence: 0.95, category: 'backend', evidence: [] },
            ];

            const overview = await service.generateOverview('repo-123', 'MyProject', frameworks);

            expect(overview.repositoryId).toBe('repo-123');
            expect(overview.repositoryName).toBe('MyProject');
            expect(overview.analyzedAt).toBeDefined();

            // Summary
            expect(overview.summary.totalFiles).toBe(50);
            expect(overview.summary.totalFunctions).toBe(200);
            expect(overview.summary.totalClasses).toBe(30);
            expect(overview.summary.totalLoc).toBe(10000);
            expect(overview.summary.languages).toHaveLength(2);
            expect(overview.summary.frameworks).toContainEqual(
                expect.objectContaining({ name: 'Spring Boot' })
            );

            // Modules
            expect(overview.modules).toHaveLength(1);
            expect(overview.modules[0].name).toBe('core');

            // Architecture
            expect(overview.architecture.patterns).toBeDefined();
            expect(overview.architecture.layers).toBeDefined();

            // Entry points
            expect(overview.entryPoints.restEndpointCount).toBeGreaterThanOrEqual(0);
            expect(overview.entryPoints.graphqlOperationCount).toBeGreaterThanOrEqual(0);
            expect(overview.entryPoints.eventHandlerCount).toBeGreaterThanOrEqual(0);

            // Code quality
            expect(overview.codeQuality.hotspots).toHaveLength(1);
            expect(overview.codeQuality.documentationCoverage).toBe(0.75);

            // Testing
            expect(overview.testing.testFileCount).toBeGreaterThanOrEqual(0);
            expect(overview.testing.testCaseCount).toBeGreaterThanOrEqual(0);

            // Recommendations
            expect(overview.recommendations).toBeDefined();
        });

        it('should handle Neo4j errors gracefully', async () => {
            // Make the first call throw, subsequent calls return empty
            let callCount = 0;
            vi.mocked(mockNeo4jClient.runTransaction).mockImplementation(async () => {
                callCount++;
                if (callCount === 1) {
                    throw new Error('Neo4j connection failed');
                }
                return createMockResult([]);
            });

            // The service handles individual query errors gracefully and returns defaults
            // So the overall generateOverview should still succeed with empty/default values
            const overview = await service.generateOverview('repo-123', 'MyProject');

            expect(overview.repositoryId).toBe('repo-123');
            // Default values when queries fail
            expect(overview.summary.totalFiles).toBe(0);
        });

        it('should handle partial data gracefully', async () => {
            vi.mocked(mockNeo4jClient.runTransaction).mockResolvedValue(
                createMockResult([])
            );

            const overview = await service.generateOverview('repo-123', 'MyProject');

            // Should still return valid structure with zeros
            expect(overview.summary.totalFiles).toBe(0);
            expect(overview.modules).toHaveLength(0);
            expect(overview.codeQuality.hotspots).toHaveLength(0);
        });
    });

    describe('detectArchitecturePatterns', () => {
        it('should detect layered architecture', async () => {
            vi.mocked(mockNeo4jClient.runTransaction).mockImplementation(
                async (query: string) => {
                    if (query.includes('c.stereotype')) {
                        return createMockResult([
                            { stereotype: 'Controller', count: 5 },
                            { stereotype: 'Service', count: 10 },
                            { stereotype: 'Repository', count: 8 },
                        ]);
                    }
                    if (query.includes('HAS_MODULE')) {
                        return createMockResult([]);
                    }
                    return createMockResult([{
                        totalFiles: 0, totalFunctions: 0, totalClasses: 0, totalLoc: 0,
                    }]);
                }
            );

            const overview = await service.generateOverview('repo-123', 'Test');

            const layeredPattern = overview.architecture.patterns.find(
                p => p.name === 'Layered Architecture'
            );
            expect(layeredPattern).toBeDefined();
            expect(layeredPattern?.confidence).toBeGreaterThan(0.8);
            expect(layeredPattern?.layers).toContain('presentation');
            expect(layeredPattern?.layers).toContain('business');
            expect(layeredPattern?.layers).toContain('data');
        });

        it('should detect MVC pattern', async () => {
            vi.mocked(mockNeo4jClient.runTransaction).mockImplementation(
                async (query: string) => {
                    if (query.includes('c.stereotype')) {
                        return createMockResult([
                            { stereotype: 'Controller', count: 5 },
                            { stereotype: 'Entity', count: 10 },
                        ]);
                    }
                    if (query.includes('HAS_MODULE')) {
                        return createMockResult([]);
                    }
                    return createMockResult([{
                        totalFiles: 0, totalFunctions: 0, totalClasses: 0, totalLoc: 0,
                    }]);
                }
            );

            const overview = await service.generateOverview('repo-123', 'Test');

            const mvcPattern = overview.architecture.patterns.find(
                p => p.name === 'MVC Pattern'
            );
            expect(mvcPattern).toBeDefined();
        });

        it('should detect modular architecture', async () => {
            vi.mocked(mockNeo4jClient.runTransaction).mockImplementation(
                async (query: string) => {
                    if (query.includes('HAS_MODULE')) {
                        return createMockResult([
                            { name: 'module1', path: '/m1', fileCount: 10, functionCount: 20, classCount: 5, totalLoc: 500, avgComplexity: 5, maxComplexity: 10, dependencies: ['utils'] },
                            { name: 'module2', path: '/m2', fileCount: 8, functionCount: 15, classCount: 4, totalLoc: 400, avgComplexity: 4, maxComplexity: 8, dependencies: [] },
                            { name: 'module3', path: '/m3', fileCount: 12, functionCount: 25, classCount: 6, totalLoc: 600, avgComplexity: 6, maxComplexity: 12, dependencies: ['utils'] },
                            { name: 'utils', path: '/utils', fileCount: 5, functionCount: 10, classCount: 2, totalLoc: 200, avgComplexity: 3, maxComplexity: 6, dependencies: [] },
                        ]);
                    }
                    if (query.includes('c.stereotype')) {
                        return createMockResult([]);
                    }
                    return createMockResult([{
                        totalFiles: 35, totalFunctions: 70, totalClasses: 17, totalLoc: 1700,
                    }]);
                }
            );

            const overview = await service.generateOverview('repo-123', 'Test');

            const modularPattern = overview.architecture.patterns.find(
                p => p.name === 'Modular Architecture'
            );
            expect(modularPattern).toBeDefined();
            expect(modularPattern?.evidence).toContainEqual(
                expect.stringContaining('independent modules')
            );
        });
    });

    describe('inferLayers', () => {
        it('should infer presentation layer', async () => {
            vi.mocked(mockNeo4jClient.runTransaction).mockImplementation(
                async (query: string) => {
                    if (query.includes('c.stereotype')) {
                        return createMockResult([
                            { stereotype: 'Controller', count: 5 },
                            { stereotype: 'DTO', count: 10 },
                        ]);
                    }
                    return createMockResult([{
                        totalFiles: 0, totalFunctions: 0, totalClasses: 0, totalLoc: 0,
                    }]);
                }
            );

            const overview = await service.generateOverview('repo-123', 'Test');

            expect(overview.architecture.layers).toContain('presentation');
        });

        it('should infer business layer', async () => {
            vi.mocked(mockNeo4jClient.runTransaction).mockImplementation(
                async (query: string) => {
                    if (query.includes('c.stereotype')) {
                        return createMockResult([
                            { stereotype: 'Service', count: 10 },
                            { stereotype: 'Handler', count: 5 },
                        ]);
                    }
                    return createMockResult([{
                        totalFiles: 0, totalFunctions: 0, totalClasses: 0, totalLoc: 0,
                    }]);
                }
            );

            const overview = await service.generateOverview('repo-123', 'Test');

            expect(overview.architecture.layers).toContain('business');
        });

        it('should infer data layer', async () => {
            vi.mocked(mockNeo4jClient.runTransaction).mockImplementation(
                async (query: string) => {
                    if (query.includes('c.stereotype')) {
                        return createMockResult([
                            { stereotype: 'Repository', count: 8 },
                            { stereotype: 'Entity', count: 12 },
                        ]);
                    }
                    return createMockResult([{
                        totalFiles: 0, totalFunctions: 0, totalClasses: 0, totalLoc: 0,
                    }]);
                }
            );

            const overview = await service.generateOverview('repo-123', 'Test');

            expect(overview.architecture.layers).toContain('data');
        });

        it('should infer infrastructure layer', async () => {
            vi.mocked(mockNeo4jClient.runTransaction).mockImplementation(
                async (query: string) => {
                    if (query.includes('c.stereotype')) {
                        return createMockResult([
                            { stereotype: 'Configuration', count: 5 },
                            { stereotype: 'Client', count: 3 },
                        ]);
                    }
                    return createMockResult([{
                        totalFiles: 0, totalFunctions: 0, totalClasses: 0, totalLoc: 0,
                    }]);
                }
            );

            const overview = await service.generateOverview('repo-123', 'Test');

            expect(overview.architecture.layers).toContain('infrastructure');
        });
    });

    describe('generateRecommendations', () => {
        it('should generate entry point recommendations', async () => {
            vi.mocked(mockNeo4jClient.runTransaction).mockImplementation(
                async (query: string) => {
                    if (query.includes('STARTING_POINTS') || query.includes('starting') || query.includes("stereotype IN ['Controller', 'Service']")) {
                        return createMockResult([
                            {
                                entityId: 'ctrl1',
                                name: 'UserController',
                                filePath: '/src/UserController.java',
                                type: 'entry-point',
                                priority: 1,
                            },
                            {
                                entityId: 'svc1',
                                name: 'UserService',
                                filePath: '/src/UserService.java',
                                type: 'core-module',
                                priority: 4,
                            },
                        ]);
                    }
                    return createMockResult([{
                        totalFiles: 0, totalFunctions: 0, totalClasses: 0, totalLoc: 0,
                    }]);
                }
            );

            const overview = await service.generateOverview('repo-123', 'Test');

            expect(overview.recommendations.length).toBeGreaterThan(0);
            expect(overview.recommendations[0].type).toBe('entry-point');
            expect(overview.recommendations[0].reason).toContain('Entry point');
        });

        it('should generate hotspot recommendations', async () => {
            vi.mocked(mockNeo4jClient.runTransaction).mockImplementation(
                async (query: string) => {
                    if (query.includes('complexityThreshold')) {
                        return createMockResult([{
                            entityId: 'func1',
                            name: 'complexFunction',
                            filePath: '/src/complex.ts',
                            line: 10,
                            kind: 'Function',
                            cyclomaticComplexity: 30,
                            cognitiveComplexity: 40,
                            loc: 150,
                        }]);
                    }
                    return createMockResult([{
                        totalFiles: 10, totalFunctions: 50, totalClasses: 5, totalLoc: 1000,
                    }]);
                }
            );

            const overview = await service.generateOverview('repo-123', 'Test');

            const hotspotRec = overview.recommendations.find(
                r => r.type === 'documentation' && r.reason.includes('complexity')
            );
            expect(hotspotRec).toBeDefined();
            expect(hotspotRec?.reason).toContain('refactoring');
        });

        it('should sort recommendations by priority', async () => {
            vi.mocked(mockNeo4jClient.runTransaction).mockImplementation(
                async (query: string) => {
                    if (query.includes('STARTING_POINTS') || query.includes('starting') || query.includes("stereotype IN ['Controller', 'Service']")) {
                        return createMockResult([
                            {
                                entityId: 'svc1',
                                name: 'UserService',
                                filePath: '/src/UserService.java',
                                type: 'core-module',
                                priority: 4,
                            },
                            {
                                entityId: 'ctrl1',
                                name: 'UserController',
                                filePath: '/src/UserController.java',
                                type: 'entry-point',
                                priority: 1,
                            },
                        ]);
                    }
                    return createMockResult([{
                        totalFiles: 0, totalFunctions: 0, totalClasses: 0, totalLoc: 0,
                    }]);
                }
            );

            const overview = await service.generateOverview('repo-123', 'Test');

            // Should be sorted by priority (1 before 4)
            expect(overview.recommendations[0].priority).toBeLessThanOrEqual(
                overview.recommendations[overview.recommendations.length - 1].priority
            );
        });
    });

    describe('calculateAvgComplexity', () => {
        it('should calculate average complexity from hotspots', async () => {
            vi.mocked(mockNeo4jClient.runTransaction).mockImplementation(
                async (query: string) => {
                    if (query.includes('complexityThreshold')) {
                        return createMockResult([
                            { entityId: 'f1', name: 'func1', filePath: '/f1.ts', line: 1, kind: 'Function', cyclomaticComplexity: 20, cognitiveComplexity: 25, loc: 50 },
                            { entityId: 'f2', name: 'func2', filePath: '/f2.ts', line: 1, kind: 'Function', cyclomaticComplexity: 30, cognitiveComplexity: 35, loc: 80 },
                        ]);
                    }
                    return createMockResult([{
                        totalFiles: 10, totalFunctions: 50, totalClasses: 5, totalLoc: 1000,
                    }]);
                }
            );

            const overview = await service.generateOverview('repo-123', 'Test');

            expect(overview.codeQuality.avgCyclomaticComplexity).toBe(25); // (20 + 30) / 2
            expect(overview.codeQuality.avgCognitiveComplexity).toBe(30); // (25 + 35) / 2
        });

        it('should return 0 when no hotspots', async () => {
            vi.mocked(mockNeo4jClient.runTransaction).mockResolvedValue(
                createMockResult([])
            );

            const overview = await service.generateOverview('repo-123', 'Test');

            expect(overview.codeQuality.avgCyclomaticComplexity).toBe(0);
            expect(overview.codeQuality.avgCognitiveComplexity).toBe(0);
        });
    });

    describe('createRepositoryOverviewService', () => {
        it('should create a new service instance', () => {
            const newService = createRepositoryOverviewService(mockNeo4jClient, mockLogger);

            expect(newService).toBeInstanceOf(RepositoryOverviewService);
        });
    });
});
