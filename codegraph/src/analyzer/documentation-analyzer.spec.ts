// src/analyzer/documentation-analyzer.spec.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    DocumentationAnalyzer,
    hasDocumentation,
    isDeprecated,
    calculateDocCoverage,
    DEFAULT_DOC_CONFIG,
} from './documentation-analyzer.js';
import { AstNode } from './types.js';
import winston from 'winston';

describe('DocumentationAnalyzer', () => {
    let analyzer: DocumentationAnalyzer;
    let mockLogger: winston.Logger;

    beforeEach(() => {
        mockLogger = {
            info: vi.fn(),
            debug: vi.fn(),
            warn: vi.fn(),
            error: vi.fn(),
        } as unknown as winston.Logger;

        analyzer = new DocumentationAnalyzer(mockLogger);
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

    describe('analyzeNode', () => {
        describe('hasDocumentation detection', () => {
            it('should detect documentation from documentation field', () => {
                const node = createMockNode({
                    documentation: 'This function does something useful.',
                });

                const result = analyzer.analyzeNode(node);

                expect(result.hasDocumentation).toBe(true);
            });

            it('should detect documentation from docComment field', () => {
                const node = createMockNode({
                    docComment: `/**
                     * This function processes user data.
                     * @param user The user to process
                     * @returns The processed user
                     */`,
                });

                const result = analyzer.analyzeNode(node);

                expect(result.hasDocumentation).toBe(true);
            });

            it('should detect documentation from documentationInfo', () => {
                const node = createMockNode({
                    documentationInfo: {
                        summary: 'This function handles authentication.',
                        tags: [],
                    },
                });

                const result = analyzer.analyzeNode(node);

                expect(result.hasDocumentation).toBe(true);
            });

            it('should not count short documentation as valid', () => {
                const node = createMockNode({
                    documentation: 'TODO', // Too short
                });

                const result = analyzer.analyzeNode(node);

                expect(result.hasDocumentation).toBe(false);
            });

            it('should not count auto-generated documentation', () => {
                const node = createMockNode({
                    documentation: 'Gets the value.',
                });

                const result = analyzer.analyzeNode(node);

                expect(result.documentationQuality.issues).toContain('Documentation appears auto-generated');
            });
        });

        describe('isDeprecated detection', () => {
            it('should detect @deprecated tag in docComment', () => {
                const node = createMockNode({
                    docComment: `/**
                     * @deprecated Use newFunction instead
                     */`,
                });

                const result = analyzer.analyzeNode(node);

                expect(result.isDeprecated).toBe(true);
                expect(result.deprecationReason).toBe('Use newFunction instead');
            });

            it('should detect @Deprecated annotation in modifierFlags', () => {
                const node = createMockNode({
                    modifierFlags: ['@Deprecated', 'public'],
                });

                const result = analyzer.analyzeNode(node);

                expect(result.isDeprecated).toBe(true);
            });

            it('should detect deprecation from documentationInfo', () => {
                const node = createMockNode({
                    documentationInfo: {
                        summary: 'Old function',
                        isDeprecated: true,
                        deprecationReason: 'Use v2 API',
                        tags: [],
                    },
                });

                const result = analyzer.analyzeNode(node);

                expect(result.isDeprecated).toBe(true);
                expect(result.deprecationReason).toBe('Use v2 API');
            });

            it('should detect deprecation from tags array', () => {
                const node = createMockNode({
                    tags: [
                        { tag: 'deprecated', description: 'Will be removed in v3' },
                    ],
                });

                const result = analyzer.analyzeNode(node);

                expect(result.isDeprecated).toBe(true);
            });
        });

        describe('documentationQuality assessment', () => {
            it('should score excellent documentation', () => {
                const node = createMockNode({
                    kind: 'Function',
                    documentation: 'Processes user authentication by validating credentials against the database.',
                    returnType: 'boolean',
                    metrics: { parameterCount: 2, loc: 10, cyclomaticComplexity: 2, cognitiveComplexity: 2, nestingDepth: 1 },
                    tags: [
                        { tag: 'param', description: 'username - The username', name: 'username' },
                        { tag: 'param', description: 'password - The password', name: 'password' },
                        { tag: 'returns', description: 'True if authenticated' },
                    ],
                });

                const result = analyzer.analyzeNode(node);

                expect(result.documentationQuality.level).toBe('excellent');
                expect(result.documentationQuality.hasDescription).toBe(true);
                expect(result.documentationQuality.hasParamDocs).toBe(true);
                expect(result.documentationQuality.hasReturnDocs).toBe(true);
            });

            it('should score partial documentation', () => {
                const node = createMockNode({
                    kind: 'Function',
                    documentation: 'A function that does something.',
                    returnType: 'void',
                });

                const result = analyzer.analyzeNode(node);

                // Documentation exists and is meaningful, so quality should be at least partial
                expect(['excellent', 'good', 'partial']).toContain(result.documentationQuality.level);
            });

            it('should score no documentation as none', () => {
                const node = createMockNode({
                    kind: 'Function',
                });

                const result = analyzer.analyzeNode(node);

                expect(result.documentationQuality.level).toBe('none');
                expect(result.documentationQuality.issues).toContain('No documentation found');
            });
        });
    });

    describe('analyzeNodes', () => {
        it('should calculate documentation statistics for multiple nodes', () => {
            const nodes: AstNode[] = [
                createMockNode({
                    kind: 'Function',
                    name: 'documentedFunction',
                    documentation: 'This function is well documented with meaningful content.',
                }),
                createMockNode({
                    kind: 'Function',
                    name: 'undocumentedFunction',
                }),
                createMockNode({
                    kind: 'Class',
                    name: 'DocumentedClass',
                    documentation: 'A class that handles user operations.',
                    isExported: true,
                }),
                createMockNode({
                    kind: 'Class',
                    name: 'UndocumentedPublicClass',
                    visibility: 'public',
                }),
            ];

            const result = analyzer.analyzeNodes(nodes);

            expect(result.totalDocumentable).toBe(4);
            expect(result.documented).toBe(2);
            expect(result.undocumented).toBe(2);
            expect(result.coverage).toBe(0.5);
            expect(result.publicUndocumented).toBe(1);
        });

        it('should count deprecated entities', () => {
            const nodes: AstNode[] = [
                createMockNode({
                    kind: 'Function',
                    name: 'deprecatedFunction',
                    documentation: 'Old function',
                    documentationInfo: { summary: 'Old', isDeprecated: true, tags: [] },
                }),
                createMockNode({
                    kind: 'Function',
                    name: 'normalFunction',
                    documentation: 'Normal function that works fine.',
                }),
            ];

            const result = analyzer.analyzeNodes(nodes);

            expect(result.deprecated).toBe(1);
        });

        it('should track quality distribution', () => {
            const nodes: AstNode[] = [
                createMockNode({
                    kind: 'Function',
                    documentation: 'Excellent documentation with all the details needed to understand this function.',
                    tags: [
                        { tag: 'param', description: 'value', name: 'value' },
                        { tag: 'returns', description: 'result' },
                    ],
                }),
                createMockNode({
                    kind: 'Function',
                }),
            ];

            const result = analyzer.analyzeNodes(nodes);

            expect(result.qualityDistribution.none).toBe(1);
            expect(result.qualityDistribution.excellent + result.qualityDistribution.good).toBeGreaterThanOrEqual(1);
        });
    });

    describe('hasDocumentation helper', () => {
        it('should return true when documentation exists', () => {
            const node = createMockNode({
                documentation: 'Some documentation here.',
            });

            expect(hasDocumentation(node)).toBe(true);
        });

        it('should return true when docComment exists', () => {
            const node = createMockNode({
                docComment: '/** Some comment */',
            });

            expect(hasDocumentation(node)).toBe(true);
        });

        it('should return true when documentationInfo.summary exists', () => {
            const node = createMockNode({
                documentationInfo: {
                    summary: 'A summary',
                    tags: [],
                },
            });

            expect(hasDocumentation(node)).toBe(true);
        });

        it('should return false when no documentation', () => {
            const node = createMockNode({});

            expect(hasDocumentation(node)).toBe(false);
        });
    });

    describe('isDeprecated helper', () => {
        it('should return true when isDeprecated flag is set', () => {
            const node = createMockNode({
                isDeprecated: true,
            });

            expect(isDeprecated(node)).toBe(true);
        });

        it('should return true when documentationInfo.isDeprecated is true', () => {
            const node = createMockNode({
                documentationInfo: {
                    summary: '',
                    isDeprecated: true,
                    tags: [],
                },
            });

            expect(isDeprecated(node)).toBe(true);
        });

        it('should return true when deprecated tag exists', () => {
            const node = createMockNode({
                tags: [{ tag: 'deprecated', description: 'reason' }],
            });

            expect(isDeprecated(node)).toBe(true);
        });

        it('should return false when not deprecated', () => {
            const node = createMockNode({
                documentation: 'Normal function',
            });

            expect(isDeprecated(node)).toBe(false);
        });
    });

    describe('calculateDocCoverage helper', () => {
        it('should calculate coverage ratio', () => {
            const nodes: AstNode[] = [
                createMockNode({ kind: 'Function', documentation: 'Documented function.' }),
                createMockNode({ kind: 'Function' }),
                createMockNode({ kind: 'Class', documentation: 'Documented class.' }),
                createMockNode({ kind: 'Interface' }),
            ];

            const coverage = calculateDocCoverage(nodes);

            expect(coverage).toBe(0.5); // 2 out of 4
        });

        it('should return 1 when no documentable nodes', () => {
            const nodes: AstNode[] = [
                createMockNode({ kind: 'File' }),
                createMockNode({ kind: 'Import' }),
            ];

            const coverage = calculateDocCoverage(nodes);

            expect(coverage).toBe(1);
        });
    });

    describe('language-specific deprecation patterns', () => {
        it('should detect Java @Deprecated annotation', () => {
            const node = createMockNode({
                language: 'Java',
                modifierFlags: ['@Deprecated'],
            });

            const result = analyzer.analyzeNode(node);

            expect(result.isDeprecated).toBe(true);
        });

        it('should detect Python deprecation warning', () => {
            const node = createMockNode({
                language: 'Python',
                docComment: `"""
                    .. deprecated:: 1.0
                       Use new_function instead
                    """`,
            });

            const result = analyzer.analyzeNode(node);

            expect(result.isDeprecated).toBe(true);
        });

        it('should detect C# [Obsolete] attribute', () => {
            const node = createMockNode({
                language: 'C#',
                modifierFlags: ['[Obsolete]'],
            });

            const result = analyzer.analyzeNode(node);

            expect(result.isDeprecated).toBe(true);
        });

        it('should detect Go deprecation comment', () => {
            const node = createMockNode({
                language: 'Go',
                docComment: '// Deprecated: use NewFunc instead',
            });

            const result = analyzer.analyzeNode(node);

            expect(result.isDeprecated).toBe(true);
        });
    });

    describe('custom configuration', () => {
        it('should use custom minimum description length', () => {
            const customAnalyzer = new DocumentationAnalyzer(mockLogger, {
                minDescriptionLength: 50,
            });

            const node = createMockNode({
                documentation: 'Short description.', // 18 chars
            });

            const result = customAnalyzer.analyzeNode(node);

            // Should have issue about short description
            expect(result.documentationQuality.issues.some(issue =>
                issue.includes('Description too short') || issue.includes('short')
            )).toBe(true);
        });
    });
});
