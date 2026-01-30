// src/analyzer/code-smell-detector.spec.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    CodeSmellDetector,
    DEFAULT_THRESHOLDS,
    getSeverityColor,
    CodeSmellThresholds,
} from './code-smell-detector.js';
import { AstNode, RelationshipInfo, CODE_SMELL_TYPES } from './types.js';
import winston from 'winston';

describe('CodeSmellDetector', () => {
    let detector: CodeSmellDetector;
    let mockLogger: winston.Logger;

    beforeEach(() => {
        mockLogger = {
            info: vi.fn(),
            debug: vi.fn(),
            warn: vi.fn(),
            error: vi.fn(),
        } as unknown as winston.Logger;

        detector = new CodeSmellDetector(mockLogger);
    });

    const createMockNode = (overrides: Partial<AstNode>): AstNode => ({
        id: 'test-id',
        entityId: 'test-entity-id',
        kind: 'Method',
        name: 'testMethod',
        filePath: '/test/TestClass.java',
        language: 'Java',
        startLine: 1,
        endLine: 100,
        startColumn: 0,
        endColumn: 0,
        createdAt: new Date().toISOString(),
        ...overrides,
    });

    describe('detectSmells - Method level', () => {
        it('should detect long method', () => {
            const node = createMockNode({
                kind: 'Method',
                metrics: {
                    cyclomaticComplexity: 5,
                    cognitiveComplexity: 10,
                    nestingDepth: 2,
                    loc: 100, // Exceeds default threshold of 50
                    parameterCount: 3,
                },
            });

            const smells = detector.detectSmells(node);

            expect(smells).toContainEqual(
                expect.objectContaining({
                    type: CODE_SMELL_TYPES.LONG_METHOD,
                    name: 'Long Method',
                })
            );
        });

        it('should detect too many parameters', () => {
            const node = createMockNode({
                kind: 'Function',
                metrics: {
                    cyclomaticComplexity: 5,
                    cognitiveComplexity: 10,
                    nestingDepth: 2,
                    loc: 30,
                    parameterCount: 8, // Exceeds default threshold of 5
                },
            });

            const smells = detector.detectSmells(node);

            expect(smells).toContainEqual(
                expect.objectContaining({
                    type: CODE_SMELL_TYPES.TOO_MANY_PARAMETERS,
                })
            );
        });

        it('should detect deeply nested code', () => {
            const node = createMockNode({
                kind: 'Method',
                metrics: {
                    cyclomaticComplexity: 5,
                    cognitiveComplexity: 10,
                    nestingDepth: 6, // Exceeds default threshold of 4
                    loc: 30,
                    parameterCount: 2,
                },
            });

            const smells = detector.detectSmells(node);

            expect(smells).toContainEqual(
                expect.objectContaining({
                    type: CODE_SMELL_TYPES.DEEPLY_NESTED,
                })
            );
        });

        it('should detect complex method (high cyclomatic complexity)', () => {
            const node = createMockNode({
                kind: 'Method',
                metrics: {
                    cyclomaticComplexity: 25, // Exceeds default threshold of 15
                    cognitiveComplexity: 10,
                    nestingDepth: 2,
                    loc: 30,
                    parameterCount: 2,
                },
            });

            const smells = detector.detectSmells(node);

            expect(smells).toContainEqual(
                expect.objectContaining({
                    type: CODE_SMELL_TYPES.COMPLEX_METHOD,
                })
            );
        });

        it('should detect high cognitive complexity', () => {
            const node = createMockNode({
                kind: 'Method',
                metrics: {
                    cyclomaticComplexity: 10,
                    cognitiveComplexity: 30, // Exceeds default threshold of 20
                    nestingDepth: 2,
                    loc: 30,
                    parameterCount: 2,
                },
            });

            const smells = detector.detectSmells(node);

            expect(smells).toContainEqual(
                expect.objectContaining({
                    type: CODE_SMELL_TYPES.HIGH_COGNITIVE_COMPLEXITY,
                })
            );
        });

        it('should detect missing documentation on public methods', () => {
            const node = createMockNode({
                kind: 'Method',
                visibility: 'public',
                metrics: {
                    cyclomaticComplexity: 5,
                    cognitiveComplexity: 5,
                    nestingDepth: 2,
                    loc: 20,
                    parameterCount: 2,
                },
            });

            const smells = detector.detectSmells(node);

            expect(smells).toContainEqual(
                expect.objectContaining({
                    type: CODE_SMELL_TYPES.MISSING_DOCUMENTATION,
                })
            );
        });
    });

    describe('detectSmells - Class level', () => {
        it('should detect large class by LOC', () => {
            const node = createMockNode({
                kind: 'Class',
                loc: 600, // Exceeds default threshold of 500
                properties: {
                    methodCount: 10,
                    avgComplexity: 5,
                },
            });

            const smells = detector.detectSmells(node);

            expect(smells).toContainEqual(
                expect.objectContaining({
                    type: CODE_SMELL_TYPES.LARGE_CLASS,
                })
            );
        });

        it('should detect large class by method count', () => {
            const node = createMockNode({
                kind: 'Class',
                loc: 300,
                properties: {
                    methodCount: 25, // Exceeds default threshold of 20
                    avgComplexity: 5,
                },
            });

            const smells = detector.detectSmells(node);

            expect(smells).toContainEqual(
                expect.objectContaining({
                    type: CODE_SMELL_TYPES.LARGE_CLASS,
                })
            );
        });

        it('should detect god class', () => {
            const node = createMockNode({
                kind: 'Class',
                loc: 1500,
                properties: {
                    methodCount: 35, // Exceeds god class threshold of 30
                    avgComplexity: 15,
                },
            });

            const smells = detector.detectSmells(node);

            expect(smells).toContainEqual(
                expect.objectContaining({
                    type: CODE_SMELL_TYPES.GOD_CLASS,
                    severity: 'critical',
                })
            );
        });

        it('should detect data class', () => {
            const node = createMockNode({
                kind: 'Class',
                loc: 100,
                properties: {
                    methodCount: 10,
                    getterSetterCount: 9, // 90% are getters/setters
                    avgComplexity: 1,
                },
            });

            const smells = detector.detectSmells(node);

            expect(smells).toContainEqual(
                expect.objectContaining({
                    type: CODE_SMELL_TYPES.DATA_CLASS,
                })
            );
        });
    });

    describe('detectSmells - File level', () => {
        it('should detect excessive imports', () => {
            const node = createMockNode({
                kind: 'File',
                properties: {
                    importCount: 30, // Exceeds default threshold of 20
                },
            });

            const smells = detector.detectSmells(node);

            expect(smells).toContainEqual(
                expect.objectContaining({
                    type: CODE_SMELL_TYPES.EXCESSIVE_IMPORTS,
                })
            );
        });
    });

    describe('detectCircularDependencies', () => {
        it('should detect simple circular dependency', () => {
            const nodes: AstNode[] = [
                createMockNode({ kind: 'File', entityId: 'file1', filePath: '/src/a.ts' }),
                createMockNode({ kind: 'File', entityId: 'file2', filePath: '/src/b.ts' }),
            ];

            const relationships: RelationshipInfo[] = [
                {
                    id: 'rel1',
                    entityId: 'rel1',
                    type: 'IMPORTS',
                    sourceId: 'file1',
                    targetId: 'file2',
                    createdAt: new Date().toISOString(),
                },
                {
                    id: 'rel2',
                    entityId: 'rel2',
                    type: 'IMPORTS',
                    sourceId: 'file2',
                    targetId: 'file1',
                    createdAt: new Date().toISOString(),
                },
            ];

            const smells = detector.detectCircularDependencies(nodes, relationships);

            expect(smells.length).toBeGreaterThan(0);
            expect(smells[0].type).toBe(CODE_SMELL_TYPES.CIRCULAR_DEPENDENCY);
        });

        it('should detect multi-node circular dependency', () => {
            const nodes: AstNode[] = [
                createMockNode({ kind: 'File', entityId: 'file1', filePath: '/src/a.ts' }),
                createMockNode({ kind: 'File', entityId: 'file2', filePath: '/src/b.ts' }),
                createMockNode({ kind: 'File', entityId: 'file3', filePath: '/src/c.ts' }),
            ];

            const relationships: RelationshipInfo[] = [
                { id: 'rel1', entityId: 'rel1', type: 'IMPORTS', sourceId: 'file1', targetId: 'file2', createdAt: new Date().toISOString() },
                { id: 'rel2', entityId: 'rel2', type: 'IMPORTS', sourceId: 'file2', targetId: 'file3', createdAt: new Date().toISOString() },
                { id: 'rel3', entityId: 'rel3', type: 'IMPORTS', sourceId: 'file3', targetId: 'file1', createdAt: new Date().toISOString() },
            ];

            const smells = detector.detectCircularDependencies(nodes, relationships);

            expect(smells.length).toBeGreaterThan(0);
            expect(smells[0].type).toBe(CODE_SMELL_TYPES.CIRCULAR_DEPENDENCY);
        });

        it('should not report false positives for linear dependencies', () => {
            const nodes: AstNode[] = [
                createMockNode({ kind: 'File', entityId: 'file1', filePath: '/src/a.ts' }),
                createMockNode({ kind: 'File', entityId: 'file2', filePath: '/src/b.ts' }),
                createMockNode({ kind: 'File', entityId: 'file3', filePath: '/src/c.ts' }),
            ];

            const relationships: RelationshipInfo[] = [
                { id: 'rel1', entityId: 'rel1', type: 'IMPORTS', sourceId: 'file1', targetId: 'file2', createdAt: new Date().toISOString() },
                { id: 'rel2', entityId: 'rel2', type: 'IMPORTS', sourceId: 'file2', targetId: 'file3', createdAt: new Date().toISOString() },
            ];

            const smells = detector.detectCircularDependencies(nodes, relationships);

            expect(smells.length).toBe(0);
        });
    });

    describe('detectDeadCode', () => {
        it('should detect unreferenced exports', () => {
            const nodes: AstNode[] = [
                createMockNode({
                    kind: 'Function',
                    entityId: 'func1',
                    name: 'unusedFunction',
                    isExported: true,
                }),
                createMockNode({
                    kind: 'Function',
                    entityId: 'func2',
                    name: 'usedFunction',
                    isExported: true,
                }),
            ];

            const relationships: RelationshipInfo[] = [
                {
                    id: 'rel1',
                    entityId: 'rel1',
                    type: 'CALLS',
                    sourceId: 'some-caller',
                    targetId: 'func2',
                    createdAt: new Date().toISOString(),
                },
            ];

            const smells = detector.detectDeadCode(nodes, relationships);

            expect(smells.length).toBe(1);
            expect(smells[0].type).toBe(CODE_SMELL_TYPES.DEAD_CODE);
            expect(smells[0].description).toContain('unusedFunction');
        });

        it('should not flag entry points as dead code', () => {
            const nodes: AstNode[] = [
                createMockNode({
                    kind: 'Class',
                    entityId: 'ctrl1',
                    name: 'UserController',
                    isExported: true,
                }),
                createMockNode({
                    kind: 'Function',
                    entityId: 'main1',
                    name: 'main',
                    isExported: true,
                }),
            ];

            const relationships: RelationshipInfo[] = [];

            const smells = detector.detectDeadCode(nodes, relationships);

            expect(smells.length).toBe(0);
        });
    });

    describe('analyzeAll', () => {
        it('should aggregate smell statistics', () => {
            const nodes: AstNode[] = [
                createMockNode({
                    kind: 'Method',
                    entityId: 'method1',
                    metrics: {
                        cyclomaticComplexity: 20,
                        cognitiveComplexity: 25,
                        nestingDepth: 5,
                        loc: 80,
                        parameterCount: 7,
                    },
                }),
                createMockNode({
                    kind: 'Class',
                    entityId: 'class1',
                    loc: 600,
                    properties: {
                        methodCount: 25,
                        avgComplexity: 10,
                    },
                }),
            ];

            const result = detector.analyzeAll(nodes);

            expect(result.totalSmells).toBeGreaterThan(0);
            expect(result.smellsBySeverity).toBeDefined();
            expect(result.smellsByCategory).toBeDefined();
            expect(result.smellsByType).toBeDefined();
            expect(result.technicalDebtMinutes).toBeGreaterThan(0);
            expect(result.technicalDebtHours).toBeGreaterThan(0);
        });
    });

    describe('severity calculation', () => {
        it('should calculate severity based on threshold exceedance', () => {
            // Method with slightly exceeding LOC - should be low/medium
            const lowNode = createMockNode({
                kind: 'Method',
                metrics: {
                    cyclomaticComplexity: 5,
                    cognitiveComplexity: 5,
                    nestingDepth: 2,
                    loc: 60, // 1.2x threshold
                    parameterCount: 2,
                },
            });

            // Method with greatly exceeding LOC - should be higher severity
            const highNode = createMockNode({
                kind: 'Method',
                metrics: {
                    cyclomaticComplexity: 5,
                    cognitiveComplexity: 5,
                    nestingDepth: 2,
                    loc: 150, // 3x threshold
                    parameterCount: 2,
                },
            });

            const lowSmells = detector.detectSmells(lowNode);
            const highSmells = detector.detectSmells(highNode);

            const lowSmell = lowSmells.find(s => s.type === CODE_SMELL_TYPES.LONG_METHOD);
            const highSmell = highSmells.find(s => s.type === CODE_SMELL_TYPES.LONG_METHOD);

            // Lower exceedance should have lower severity
            expect(['low', 'medium']).toContain(lowSmell?.severity);
            // Higher exceedance should have higher severity
            expect(['high', 'critical']).toContain(highSmell?.severity);
        });
    });

    describe('custom thresholds', () => {
        it('should use custom thresholds when provided', () => {
            const customThresholds: Partial<CodeSmellThresholds> = {
                longMethodLoc: 20, // Lower threshold
            };

            const customDetector = new CodeSmellDetector(mockLogger, customThresholds);

            const node = createMockNode({
                kind: 'Method',
                metrics: {
                    cyclomaticComplexity: 5,
                    cognitiveComplexity: 5,
                    nestingDepth: 2,
                    loc: 25, // Below default (50) but above custom (20)
                    parameterCount: 2,
                },
            });

            const smells = customDetector.detectSmells(node);

            expect(smells).toContainEqual(
                expect.objectContaining({
                    type: CODE_SMELL_TYPES.LONG_METHOD,
                })
            );
        });
    });

    describe('getSeverityColor', () => {
        it('should return correct colors for severities', () => {
            expect(getSeverityColor('info')).toBe('blue');
            expect(getSeverityColor('low')).toBe('green');
            expect(getSeverityColor('medium')).toBe('yellow');
            expect(getSeverityColor('high')).toBe('orange');
            expect(getSeverityColor('critical')).toBe('red');
        });
    });
});
