// src/analyzer/metrics-analyzer.spec.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    MetricsAnalyzer,
    calculateTextBasedMetrics,
    estimateCyclomaticComplexityFromText,
    estimateCognitiveComplexityFromText,
    countParametersFromSignature,
    extractPythonMetrics,
    extractGoMetrics,
    isGodClass,
    isDataClass,
    DEFAULT_THRESHOLDS,
} from './metrics-analyzer.js';
import { AstNode } from './types.js';
import winston from 'winston';

describe('MetricsAnalyzer', () => {
    let analyzer: MetricsAnalyzer;
    let mockLogger: winston.Logger;

    beforeEach(() => {
        mockLogger = {
            info: vi.fn(),
            debug: vi.fn(),
            warn: vi.fn(),
            error: vi.fn(),
        } as unknown as winston.Logger;

        analyzer = new MetricsAnalyzer(mockLogger);
    });

    const createMockNode = (overrides: Partial<AstNode>): AstNode => ({
        id: 'test-id',
        entityId: 'test-entity-id',
        kind: 'Function',
        name: 'testFunction',
        filePath: '/test/file.ts',
        language: 'TypeScript',
        startLine: 1,
        endLine: 10,
        startColumn: 0,
        endColumn: 0,
        createdAt: new Date().toISOString(),
        ...overrides,
    });

    describe('calculateTextBasedMetrics', () => {
        it('should calculate LOC correctly', () => {
            const sourceText = `
function test() {
    const a = 1;
    const b = 2;
    return a + b;
}
            `.trim();

            const metrics = calculateTextBasedMetrics(sourceText);

            expect(metrics.loc).toBe(5); // Non-empty, non-comment lines
        });

        it('should skip comments', () => {
            const sourceText = `
// This is a comment
function test() {
    // Another comment
    const a = 1;
}
            `.trim();

            const metrics = calculateTextBasedMetrics(sourceText);

            expect(metrics.loc).toBe(3); // Only function, const, and closing brace
        });

        it('should skip block comments', () => {
            const sourceText = `
/*
 * Block comment
 */
function test() {
    return 1;
}
            `.trim();

            const metrics = calculateTextBasedMetrics(sourceText);

            expect(metrics.loc).toBe(3);
        });

        it('should track nesting depth', () => {
            const sourceText = `
function test() {
    if (true) {
        if (true) {
            return 1;
        }
    }
}
            `.trim();

            const metrics = calculateTextBasedMetrics(sourceText);

            expect(metrics.nestingDepth).toBeGreaterThan(0);
        });
    });

    describe('estimateCyclomaticComplexityFromText', () => {
        it('should return 1 for simple function', () => {
            const sourceText = `
function simple() {
    return 1;
}
            `;

            const complexity = estimateCyclomaticComplexityFromText(sourceText);

            expect(complexity).toBe(1);
        });

        it('should count if statements', () => {
            const sourceText = `
function withIf() {
    if (condition) {
        return 1;
    }
    return 2;
}
            `;

            const complexity = estimateCyclomaticComplexityFromText(sourceText);

            expect(complexity).toBe(2); // 1 base + 1 if
        });

        it('should count loops', () => {
            const sourceText = `
function withLoops() {
    for (let i = 0; i < 10; i++) {
        while (true) {
            break;
        }
    }
}
            `;

            const complexity = estimateCyclomaticComplexityFromText(sourceText);

            expect(complexity).toBe(3); // 1 base + 1 for + 1 while
        });

        it('should count logical operators', () => {
            const sourceText = `
function withLogical() {
    if (a && b || c) {
        return true;
    }
}
            `;

            const complexity = estimateCyclomaticComplexityFromText(sourceText);

            expect(complexity).toBeGreaterThan(2); // 1 base + 1 if + logical operators
        });

        it('should count ternary operators', () => {
            const sourceText = `
function withTernary() {
    return condition ? 1 : 2;
}
            `;

            const complexity = estimateCyclomaticComplexityFromText(sourceText);

            expect(complexity).toBe(2); // 1 base + 1 ternary
        });

        it('should count switch cases', () => {
            const sourceText = `
function withSwitch() {
    switch (value) {
        case 1: return 'one';
        case 2: return 'two';
        case 3: return 'three';
        default: return 'other';
    }
}
            `;

            const complexity = estimateCyclomaticComplexityFromText(sourceText);

            expect(complexity).toBeGreaterThanOrEqual(4); // 1 base + 3 cases
        });
    });

    describe('estimateCognitiveComplexityFromText', () => {
        it('should return 0 for simple function', () => {
            const sourceText = `
function simple() {
    return 1;
}
            `;

            const complexity = estimateCognitiveComplexityFromText(sourceText);

            expect(complexity).toBe(0);
        });

        it('should add increment for nesting', () => {
            const sourceText = `
function nested() {
    if (a) {
        if (b) {
            return 1;
        }
    }
}
            `;

            const complexity = estimateCognitiveComplexityFromText(sourceText);

            // First if: 1 (no nesting), second if: 1 + 1 (nested) = 3 total
            expect(complexity).toBeGreaterThan(1);
        });

        it('should count else as additional complexity', () => {
            const sourceText = `
function withElse() {
    if (a) {
        return 1;
    } else {
        return 2;
    }
}
            `;

            const complexity = estimateCognitiveComplexityFromText(sourceText);

            expect(complexity).toBeGreaterThan(0);
        });
    });

    describe('computeMetricsFromText', () => {
        it('should extract metrics for a code section', () => {
            const sourceText = `
line1
function test() {
    if (condition) {
        for (let i = 0; i < 10; i++) {
            doSomething();
        }
    }
}
line9
            `;

            const metrics = analyzer.computeMetricsFromText(sourceText, 2, 8);

            expect(metrics.loc).toBeGreaterThan(0);
            expect(metrics.cyclomaticComplexity).toBeGreaterThan(1);
            expect(metrics.cognitiveComplexity).toBeGreaterThan(0);
        });
    });

    describe('checkThresholds', () => {
        it('should detect no violations for normal metrics', () => {
            const metrics = {
                cyclomaticComplexity: 5,
                cognitiveComplexity: 10,
                nestingDepth: 2,
                loc: 30,
                parameterCount: 3,
            };

            const result = analyzer.checkThresholds(metrics, 'Function');

            expect(result.exceeds).toBe(false);
            expect(result.violations).toHaveLength(0);
        });

        it('should detect cyclomatic complexity violation', () => {
            const metrics = {
                cyclomaticComplexity: 20, // Exceeds 15
                cognitiveComplexity: 10,
                nestingDepth: 2,
                loc: 30,
                parameterCount: 3,
            };

            const result = analyzer.checkThresholds(metrics, 'Function');

            expect(result.exceeds).toBe(true);
            expect(result.violations.some(v => v.includes('Cyclomatic'))).toBe(true);
        });

        it('should use different LOC threshold for classes', () => {
            const metrics = {
                cyclomaticComplexity: 5,
                cognitiveComplexity: 10,
                nestingDepth: 2,
                loc: 400, // Below class threshold (500) but above method (50)
                parameterCount: 0,
            };

            const methodResult = analyzer.checkThresholds(metrics, 'Method');
            const classResult = analyzer.checkThresholds(metrics, 'Class');

            expect(methodResult.exceeds).toBe(true);
            expect(classResult.exceeds).toBe(false);
        });
    });

    describe('findHotspots', () => {
        it('should find complexity hotspots', () => {
            const nodes: AstNode[] = [
                createMockNode({
                    kind: 'Function',
                    entityId: 'func1',
                    name: 'simpleFunction',
                    metrics: {
                        cyclomaticComplexity: 5,
                        cognitiveComplexity: 5,
                        nestingDepth: 2,
                        loc: 20,
                        parameterCount: 2,
                    },
                }),
                createMockNode({
                    kind: 'Method',
                    entityId: 'func2',
                    name: 'complexMethod',
                    metrics: {
                        cyclomaticComplexity: 25,
                        cognitiveComplexity: 30,
                        nestingDepth: 6,
                        loc: 100,
                        parameterCount: 8,
                    },
                }),
            ];

            const hotspots = analyzer.findHotspots(nodes);

            expect(hotspots.length).toBe(1);
            expect(hotspots[0].name).toBe('complexMethod');
            expect(hotspots[0].reason).toContain('Cyclomatic');
        });

        it('should sort hotspots by cognitive complexity', () => {
            const nodes: AstNode[] = [
                createMockNode({
                    kind: 'Function',
                    entityId: 'func1',
                    name: 'highCyclomatic',
                    metrics: {
                        cyclomaticComplexity: 30,
                        cognitiveComplexity: 25,
                        nestingDepth: 5,
                        loc: 80,
                        parameterCount: 3,
                    },
                }),
                createMockNode({
                    kind: 'Function',
                    entityId: 'func2',
                    name: 'highCognitive',
                    metrics: {
                        cyclomaticComplexity: 20,
                        cognitiveComplexity: 40, // Higher cognitive
                        nestingDepth: 5,
                        loc: 80,
                        parameterCount: 3,
                    },
                }),
            ];

            const hotspots = analyzer.findHotspots(nodes);

            expect(hotspots[0].name).toBe('highCognitive');
        });

        it('should limit number of hotspots', () => {
            const nodes: AstNode[] = Array(20).fill(null).map((_, i) =>
                createMockNode({
                    kind: 'Function',
                    entityId: `func${i}`,
                    name: `complexFunction${i}`,
                    metrics: {
                        cyclomaticComplexity: 20,
                        cognitiveComplexity: 25 + i,
                        nestingDepth: 5,
                        loc: 80,
                        parameterCount: 6,
                    },
                })
            );

            const hotspots = analyzer.findHotspots(nodes, 5);

            expect(hotspots.length).toBe(5);
        });
    });

    describe('calculateAggregateMetrics', () => {
        it('should calculate aggregate metrics for multiple nodes', () => {
            const nodes: AstNode[] = [
                createMockNode({
                    kind: 'File',
                    loc: 500,
                }),
                createMockNode({
                    kind: 'Function',
                    metrics: {
                        cyclomaticComplexity: 10,
                        cognitiveComplexity: 15,
                        nestingDepth: 3,
                        loc: 50,
                        parameterCount: 3,
                    },
                }),
                createMockNode({
                    kind: 'Method',
                    metrics: {
                        cyclomaticComplexity: 20,
                        cognitiveComplexity: 25,
                        nestingDepth: 4,
                        loc: 80,
                        parameterCount: 5,
                    },
                }),
                createMockNode({
                    kind: 'Class',
                }),
            ];

            const aggregate = analyzer.calculateAggregateMetrics(nodes);

            expect(aggregate.totalLoc).toBe(500);
            expect(aggregate.functionCount).toBe(2);
            expect(aggregate.classCount).toBe(1);
            expect(aggregate.avgCyclomaticComplexity).toBe(15); // (10 + 20) / 2
            expect(aggregate.avgCognitiveComplexity).toBe(20); // (15 + 25) / 2
            expect(aggregate.maxCyclomaticComplexity).toBe(20);
            expect(aggregate.maxCognitiveComplexity).toBe(25);
            expect(aggregate.maxNestingDepth).toBe(4);
        });
    });

    describe('countParametersFromSignature', () => {
        it('should count simple parameters', () => {
            expect(countParametersFromSignature('function test(a, b, c)')).toBe(3);
            expect(countParametersFromSignature('def func(x, y)')).toBe(2);
        });

        it('should return 0 for no parameters', () => {
            expect(countParametersFromSignature('function test()')).toBe(0);
            expect(countParametersFromSignature('def func()')).toBe(0);
        });

        it('should handle generic types', () => {
            expect(countParametersFromSignature('function test(list: Array<string>, map: Map<string, number>)')).toBe(2);
        });
    });

    describe('extractPythonMetrics', () => {
        it('should extract Python function metrics', () => {
            const sourceText = `
def process_data(data, options, callback):
    if data:
        for item in data:
            if item.valid:
                callback(item)
    return True
            `;

            const metrics = extractPythonMetrics(sourceText, 1, 8);

            expect(metrics.parameterCount).toBe(3);
            expect(metrics.cyclomaticComplexity).toBeGreaterThan(1);
            expect(metrics.loc).toBeGreaterThan(0);
        });

        it('should exclude self and cls from parameter count', () => {
            const sourceText = `
def method(self, arg1, arg2):
    return arg1 + arg2
            `;

            const metrics = extractPythonMetrics(sourceText, 1, 3);

            expect(metrics.parameterCount).toBe(2); // Excludes self
        });
    });

    describe('extractGoMetrics', () => {
        it('should extract Go function metrics', () => {
            const sourceText = `
func ProcessData(data []string, options *Options) error {
    if len(data) == 0 {
        return errors.New("empty data")
    }
    for _, item := range data {
        if err := process(item); err != nil {
            return err
        }
    }
    return nil
}
            `;

            const metrics = extractGoMetrics(sourceText, 1, 12);

            expect(metrics.parameterCount).toBe(2);
            expect(metrics.cyclomaticComplexity).toBeGreaterThan(1);
        });
    });

    describe('isGodClass', () => {
        it('should identify god class by method count', () => {
            expect(isGodClass(25, 400, 5)).toBe(true);
        });

        it('should identify god class by LOC', () => {
            expect(isGodClass(10, 600, 5)).toBe(true);
        });

        it('should identify god class by combined metrics', () => {
            expect(isGodClass(15, 300, 12)).toBe(true); // methodCount > 10 && avgComplexity > 10
        });

        it('should not flag normal class', () => {
            expect(isGodClass(10, 300, 5)).toBe(false);
        });
    });

    describe('isDataClass', () => {
        it('should identify data class by getter/setter ratio', () => {
            expect(isDataClass(10, 8, 5)).toBe(true); // 80% getters/setters
        });

        it('should identify data class with few methods', () => {
            expect(isDataClass(2, 0, 10)).toBe(true);
        });

        it('should not flag class with behavior', () => {
            expect(isDataClass(10, 2, 2)).toBe(false);
        });
    });

    describe('custom thresholds', () => {
        it('should use custom thresholds', () => {
            const customAnalyzer = new MetricsAnalyzer(mockLogger, {
                cyclomaticComplexity: 5, // Stricter threshold
            });

            const metrics = {
                cyclomaticComplexity: 7,
                cognitiveComplexity: 10,
                nestingDepth: 2,
                loc: 30,
                parameterCount: 3,
            };

            const result = customAnalyzer.checkThresholds(metrics, 'Function');

            expect(result.exceeds).toBe(true);
        });
    });
});
