// src/analyzer/code-smell-detector.ts
/**
 * Detects code smells in analyzed code.
 * Uses metrics, structure, and patterns to identify potential issues.
 */

import winston from 'winston';
import {
    AstNode,
    CodeSmell,
    CodeSmellSeverity,
    CodeSmellCategory,
    CodeMetrics,
    CODE_SMELL_TYPES,
    RelationshipInfo,
} from './types.js';
import { hasDocumentation } from './documentation-analyzer.js';

// =============================================================================
// Thresholds Configuration
// =============================================================================

/**
 * Configurable thresholds for code smell detection.
 */
export interface CodeSmellThresholds {
    // Method-level thresholds
    longMethodLoc: number;
    tooManyParameters: number;
    deepNesting: number;
    highCyclomaticComplexity: number;
    highCognitiveComplexity: number;

    // Class-level thresholds
    largeClassLoc: number;
    largeClassMethods: number;
    godClassMethods: number;
    godClassComplexity: number;

    // Architecture thresholds
    excessiveImports: number;
}

export const DEFAULT_THRESHOLDS: CodeSmellThresholds = {
    longMethodLoc: 50,
    tooManyParameters: 5,
    deepNesting: 4,
    highCyclomaticComplexity: 15,
    highCognitiveComplexity: 20,
    largeClassLoc: 500,
    largeClassMethods: 20,
    godClassMethods: 30,
    godClassComplexity: 100,
    excessiveImports: 20,
};

// =============================================================================
// Code Smell Definitions
// =============================================================================

interface SmellDefinition {
    type: string;
    name: string;
    category: CodeSmellCategory;
    description: string;
    suggestion: string;
    defaultSeverity: CodeSmellSeverity;
}

const SMELL_DEFINITIONS: Record<string, SmellDefinition> = {
    [CODE_SMELL_TYPES.LONG_METHOD]: {
        type: CODE_SMELL_TYPES.LONG_METHOD,
        name: 'Long Method',
        category: 'size',
        description: 'Method has too many lines of code, making it hard to understand and maintain.',
        suggestion: 'Extract smaller, focused methods with descriptive names.',
        defaultSeverity: 'medium',
    },
    [CODE_SMELL_TYPES.TOO_MANY_PARAMETERS]: {
        type: CODE_SMELL_TYPES.TOO_MANY_PARAMETERS,
        name: 'Too Many Parameters',
        category: 'size',
        description: 'Function has too many parameters, making it hard to call and understand.',
        suggestion: 'Consider using a parameter object, builder pattern, or splitting the function.',
        defaultSeverity: 'medium',
    },
    [CODE_SMELL_TYPES.DEEPLY_NESTED]: {
        type: CODE_SMELL_TYPES.DEEPLY_NESTED,
        name: 'Deeply Nested Code',
        category: 'complexity',
        description: 'Code has too many levels of nesting, reducing readability.',
        suggestion: 'Use early returns, extract methods, or apply guard clauses.',
        defaultSeverity: 'medium',
    },
    [CODE_SMELL_TYPES.COMPLEX_METHOD]: {
        type: CODE_SMELL_TYPES.COMPLEX_METHOD,
        name: 'Complex Method',
        category: 'complexity',
        description: 'Method has high cyclomatic complexity with many decision points.',
        suggestion: 'Split into smaller methods, use strategy pattern, or simplify conditions.',
        defaultSeverity: 'high',
    },
    [CODE_SMELL_TYPES.HIGH_COGNITIVE_COMPLEXITY]: {
        type: CODE_SMELL_TYPES.HIGH_COGNITIVE_COMPLEXITY,
        name: 'High Cognitive Complexity',
        category: 'complexity',
        description: 'Method is hard to understand due to complex control flow.',
        suggestion: 'Simplify nested conditions, extract helper methods, reduce logical operators.',
        defaultSeverity: 'high',
    },
    [CODE_SMELL_TYPES.LARGE_CLASS]: {
        type: CODE_SMELL_TYPES.LARGE_CLASS,
        name: 'Large Class',
        category: 'size',
        description: 'Class has too many lines or methods, violating single responsibility.',
        suggestion: 'Split into smaller, focused classes with clear responsibilities.',
        defaultSeverity: 'medium',
    },
    [CODE_SMELL_TYPES.GOD_CLASS]: {
        type: CODE_SMELL_TYPES.GOD_CLASS,
        name: 'God Class',
        category: 'complexity',
        description: 'Class knows too much and does too much, centralizing too many responsibilities.',
        suggestion: 'Apply Single Responsibility Principle. Extract classes for each responsibility.',
        defaultSeverity: 'critical',
    },
    [CODE_SMELL_TYPES.DATA_CLASS]: {
        type: CODE_SMELL_TYPES.DATA_CLASS,
        name: 'Data Class',
        category: 'maintainability',
        description: 'Class only holds data with no behavior. Logic using this data is elsewhere.',
        suggestion: 'Consider moving behavior that uses this data into the class.',
        defaultSeverity: 'low',
    },
    [CODE_SMELL_TYPES.FEATURE_ENVY]: {
        type: CODE_SMELL_TYPES.FEATURE_ENVY,
        name: 'Feature Envy',
        category: 'coupling',
        description: 'Method uses more features from another class than its own.',
        suggestion: 'Move the method to the class it envies, or extract the envied features.',
        defaultSeverity: 'medium',
    },
    [CODE_SMELL_TYPES.CIRCULAR_DEPENDENCY]: {
        type: CODE_SMELL_TYPES.CIRCULAR_DEPENDENCY,
        name: 'Circular Dependency',
        category: 'architecture',
        description: 'Modules depend on each other in a cycle, making changes risky.',
        suggestion: 'Break the cycle by extracting shared interfaces or using dependency injection.',
        defaultSeverity: 'high',
    },
    [CODE_SMELL_TYPES.DEAD_CODE]: {
        type: CODE_SMELL_TYPES.DEAD_CODE,
        name: 'Dead Code',
        category: 'maintainability',
        description: 'Code that is never executed or used.',
        suggestion: 'Remove the dead code to reduce maintenance burden.',
        defaultSeverity: 'low',
    },
    [CODE_SMELL_TYPES.INCONSISTENT_NAMING]: {
        type: CODE_SMELL_TYPES.INCONSISTENT_NAMING,
        name: 'Inconsistent Naming',
        category: 'maintainability',
        description: 'Names do not follow consistent conventions.',
        suggestion: 'Apply consistent naming conventions across the codebase.',
        defaultSeverity: 'info',
    },
    [CODE_SMELL_TYPES.MISSING_DOCUMENTATION]: {
        type: CODE_SMELL_TYPES.MISSING_DOCUMENTATION,
        name: 'Missing Documentation',
        category: 'maintainability',
        description: 'Public API lacks documentation.',
        suggestion: 'Add meaningful documentation explaining purpose and usage.',
        defaultSeverity: 'low',
    },
    [CODE_SMELL_TYPES.TIGHT_COUPLING]: {
        type: CODE_SMELL_TYPES.TIGHT_COUPLING,
        name: 'Tight Coupling',
        category: 'coupling',
        description: 'Components are too dependent on each other\'s implementation details.',
        suggestion: 'Use interfaces, dependency injection, or event-driven architecture.',
        defaultSeverity: 'medium',
    },
    [CODE_SMELL_TYPES.EXCESSIVE_IMPORTS]: {
        type: CODE_SMELL_TYPES.EXCESSIVE_IMPORTS,
        name: 'Excessive Imports',
        category: 'coupling',
        description: 'File imports too many dependencies, indicating high coupling.',
        suggestion: 'Review dependencies. Consider if the module has too many responsibilities.',
        defaultSeverity: 'low',
    },
};

// =============================================================================
// Code Smell Detector Class
// =============================================================================

export class CodeSmellDetector {
    private logger: winston.Logger;
    private thresholds: CodeSmellThresholds;

    constructor(logger: winston.Logger, thresholds?: Partial<CodeSmellThresholds>) {
        this.logger = logger;
        this.thresholds = { ...DEFAULT_THRESHOLDS, ...thresholds };
    }

    /**
     * Detect all code smells for a single node.
     */
    detectSmells(node: AstNode): CodeSmell[] {
        const smells: CodeSmell[] = [];

        if (this.isFunctionLike(node)) {
            smells.push(...this.detectMethodSmells(node));
        }

        if (this.isClassLike(node)) {
            smells.push(...this.detectClassSmells(node));
        }

        if (this.isFileLike(node)) {
            smells.push(...this.detectFileSmells(node));
        }

        return smells;
    }

    /**
     * Detect method-level code smells.
     */
    private detectMethodSmells(node: AstNode): CodeSmell[] {
        const smells: CodeSmell[] = [];
        const metrics = node.metrics;

        // Long Method
        if (metrics?.loc && metrics.loc > this.thresholds.longMethodLoc) {
            smells.push(this.createSmell(
                CODE_SMELL_TYPES.LONG_METHOD,
                metrics.loc,
                this.thresholds.longMethodLoc,
                this.calculateSeverity(metrics.loc, this.thresholds.longMethodLoc, [1.5, 2, 3])
            ));
        }

        // Too Many Parameters
        if (metrics?.parameterCount && metrics.parameterCount > this.thresholds.tooManyParameters) {
            smells.push(this.createSmell(
                CODE_SMELL_TYPES.TOO_MANY_PARAMETERS,
                metrics.parameterCount,
                this.thresholds.tooManyParameters,
                this.calculateSeverity(metrics.parameterCount, this.thresholds.tooManyParameters, [1.2, 1.5, 2])
            ));
        }

        // Deeply Nested
        if (metrics?.nestingDepth && metrics.nestingDepth > this.thresholds.deepNesting) {
            smells.push(this.createSmell(
                CODE_SMELL_TYPES.DEEPLY_NESTED,
                metrics.nestingDepth,
                this.thresholds.deepNesting,
                this.calculateSeverity(metrics.nestingDepth, this.thresholds.deepNesting, [1.25, 1.5, 2])
            ));
        }

        // Complex Method (Cyclomatic)
        if (metrics?.cyclomaticComplexity && metrics.cyclomaticComplexity > this.thresholds.highCyclomaticComplexity) {
            smells.push(this.createSmell(
                CODE_SMELL_TYPES.COMPLEX_METHOD,
                metrics.cyclomaticComplexity,
                this.thresholds.highCyclomaticComplexity,
                this.calculateSeverity(metrics.cyclomaticComplexity, this.thresholds.highCyclomaticComplexity, [1.5, 2, 3])
            ));
        }

        // High Cognitive Complexity
        if (metrics?.cognitiveComplexity && metrics.cognitiveComplexity > this.thresholds.highCognitiveComplexity) {
            smells.push(this.createSmell(
                CODE_SMELL_TYPES.HIGH_COGNITIVE_COMPLEXITY,
                metrics.cognitiveComplexity,
                this.thresholds.highCognitiveComplexity,
                this.calculateSeverity(metrics.cognitiveComplexity, this.thresholds.highCognitiveComplexity, [1.5, 2, 3])
            ));
        }

        // Missing Documentation (for public methods)
        if ((node.isExported || node.visibility === 'public') && !hasDocumentation(node)) {
            smells.push(this.createSmell(
                CODE_SMELL_TYPES.MISSING_DOCUMENTATION,
                undefined,
                undefined,
                'low'
            ));
        }

        return smells;
    }

    /**
     * Detect class-level code smells.
     */
    private detectClassSmells(node: AstNode): CodeSmell[] {
        const smells: CodeSmell[] = [];

        // Get class metrics from properties
        const methodCount = node.properties?.methodCount as number || 0;
        const loc = node.loc || 0;
        const avgComplexity = node.properties?.avgComplexity as number || 0;
        const getterSetterCount = node.properties?.getterSetterCount as number || 0;

        // Large Class (by LOC)
        if (loc > this.thresholds.largeClassLoc) {
            smells.push(this.createSmell(
                CODE_SMELL_TYPES.LARGE_CLASS,
                loc,
                this.thresholds.largeClassLoc,
                this.calculateSeverity(loc, this.thresholds.largeClassLoc, [1.5, 2, 3])
            ));
        }

        // Large Class (by method count)
        if (methodCount > this.thresholds.largeClassMethods) {
            smells.push(this.createSmell(
                CODE_SMELL_TYPES.LARGE_CLASS,
                methodCount,
                this.thresholds.largeClassMethods,
                this.calculateSeverity(methodCount, this.thresholds.largeClassMethods, [1.5, 2, 2.5])
            ));
        }

        // God Class
        const isGodClass = (
            methodCount > this.thresholds.godClassMethods ||
            (methodCount > 15 && avgComplexity > 10) ||
            (loc > 1000 && methodCount > 20)
        );
        if (isGodClass) {
            smells.push(this.createSmell(
                CODE_SMELL_TYPES.GOD_CLASS,
                methodCount,
                this.thresholds.godClassMethods,
                'critical'
            ));
        }

        // Data Class (mostly getters/setters)
        if (methodCount > 0 && getterSetterCount / methodCount > 0.8 && methodCount > 5) {
            smells.push(this.createSmell(
                CODE_SMELL_TYPES.DATA_CLASS,
                getterSetterCount,
                undefined,
                'low'
            ));
        }

        // Missing Documentation (for public classes)
        if ((node.isExported || node.visibility === 'public') && !hasDocumentation(node)) {
            smells.push(this.createSmell(
                CODE_SMELL_TYPES.MISSING_DOCUMENTATION,
                undefined,
                undefined,
                'low'
            ));
        }

        return smells;
    }

    /**
     * Detect file-level code smells.
     */
    private detectFileSmells(node: AstNode): CodeSmell[] {
        const smells: CodeSmell[] = [];

        const importCount = node.properties?.importCount as number || 0;

        // Excessive Imports
        if (importCount > this.thresholds.excessiveImports) {
            smells.push(this.createSmell(
                CODE_SMELL_TYPES.EXCESSIVE_IMPORTS,
                importCount,
                this.thresholds.excessiveImports,
                this.calculateSeverity(importCount, this.thresholds.excessiveImports, [1.5, 2, 3])
            ));
        }

        return smells;
    }

    /**
     * Detect circular dependencies in relationships.
     */
    detectCircularDependencies(
        nodes: AstNode[],
        relationships: RelationshipInfo[]
    ): CodeSmell[] {
        const smells: CodeSmell[] = [];

        // Build dependency graph (file -> files it imports)
        const depGraph = new Map<string, Set<string>>();
        const nodeMap = new Map<string, AstNode>();

        for (const node of nodes) {
            if (node.kind === 'File') {
                nodeMap.set(node.entityId, node);
                depGraph.set(node.filePath, new Set());
            }
        }

        // Populate edges from IMPORTS relationships
        for (const rel of relationships) {
            if (rel.type === 'IMPORTS' || rel.type === 'DEPENDS_ON') {
                const sourceNode = nodeMap.get(rel.sourceId);
                const targetNode = nodeMap.get(rel.targetId);
                if (sourceNode && targetNode) {
                    depGraph.get(sourceNode.filePath)?.add(targetNode.filePath);
                }
            }
        }

        // Find cycles using DFS
        const visited = new Set<string>();
        const recursionStack = new Set<string>();
        const cycles: string[][] = [];

        const findCycles = (node: string, path: string[]): void => {
            if (recursionStack.has(node)) {
                // Found a cycle
                const cycleStart = path.indexOf(node);
                if (cycleStart !== -1) {
                    cycles.push(path.slice(cycleStart));
                }
                return;
            }

            if (visited.has(node)) return;

            visited.add(node);
            recursionStack.add(node);
            path.push(node);

            const deps = depGraph.get(node);
            if (deps) {
                for (const dep of deps) {
                    findCycles(dep, [...path]);
                }
            }

            recursionStack.delete(node);
        };

        for (const filePath of depGraph.keys()) {
            if (!visited.has(filePath)) {
                findCycles(filePath, []);
            }
        }

        // Create smells for each unique cycle
        const seenCycles = new Set<string>();
        for (const cycle of cycles) {
            const cycleKey = cycle.sort().join('->');
            if (!seenCycles.has(cycleKey)) {
                seenCycles.add(cycleKey);
                const smell = this.createSmell(
                    CODE_SMELL_TYPES.CIRCULAR_DEPENDENCY,
                    cycle.length,
                    undefined,
                    cycle.length > 3 ? 'critical' : 'high'
                );
                smell.description = `Circular dependency detected: ${cycle.map(f => f.split('/').pop()).join(' -> ')}`;
                smells.push(smell);
            }
        }

        return smells;
    }

    /**
     * Detect dead code (unreferenced exports).
     */
    detectDeadCode(
        nodes: AstNode[],
        relationships: RelationshipInfo[]
    ): CodeSmell[] {
        const smells: CodeSmell[] = [];

        // Find all exported entities
        const exports = nodes.filter(n =>
            n.isExported &&
            ['Function', 'Class', 'Interface', 'TSFunction', 'JavaClass', 'JavaMethod'].includes(n.kind)
        );

        // Find all referenced entities
        const referenced = new Set<string>();
        for (const rel of relationships) {
            if (['CALLS', 'IMPORTS', 'EXTENDS', 'IMPLEMENTS', 'USES'].includes(rel.type)) {
                referenced.add(rel.targetId);
            }
        }

        // Find unreferenced exports (potential dead code)
        for (const exp of exports) {
            if (!referenced.has(exp.entityId)) {
                // Check if it's an entry point (controllers, main, etc.)
                if (!this.isLikelyEntryPoint(exp)) {
                    const smell = this.createSmell(
                        CODE_SMELL_TYPES.DEAD_CODE,
                        undefined,
                        undefined,
                        'low'
                    );
                    smell.description = `Exported ${exp.kind} '${exp.name}' appears to be unused`;
                    smells.push(smell);
                }
            }
        }

        return smells;
    }

    /**
     * Check if a node is likely an entry point.
     */
    private isLikelyEntryPoint(node: AstNode): boolean {
        const entryPointPatterns = [
            /^main$/i,
            /^index$/i,
            /controller$/i,
            /handler$/i,
            /endpoint$/i,
            /^app$/i,
            /^server$/i,
            /^bootstrap$/i,
        ];

        return entryPointPatterns.some(p => p.test(node.name));
    }

    /**
     * Create a code smell object.
     */
    private createSmell(
        type: string,
        metricValue?: number,
        threshold?: number,
        severity?: CodeSmellSeverity
    ): CodeSmell {
        const def = SMELL_DEFINITIONS[type];
        if (!def) {
            return {
                type,
                name: type,
                description: `Code smell: ${type}`,
                severity: severity || 'medium',
                category: 'maintainability',
            };
        }

        return {
            type: def.type,
            name: def.name,
            description: def.description,
            severity: severity || def.defaultSeverity,
            category: def.category,
            suggestion: def.suggestion,
            metricValue,
            threshold,
        };
    }

    /**
     * Calculate severity based on how much threshold is exceeded.
     */
    private calculateSeverity(
        value: number,
        threshold: number,
        multipliers: [number, number, number] // [medium, high, critical]
    ): CodeSmellSeverity {
        const ratio = value / threshold;

        if (ratio >= multipliers[2]) return 'critical';
        if (ratio >= multipliers[1]) return 'high';
        if (ratio >= multipliers[0]) return 'medium';
        return 'low';
    }

    /**
     * Check if node is a function-like construct.
     */
    private isFunctionLike(node: AstNode): boolean {
        return [
            'Function', 'Method', 'TSFunction',
            'JavaMethod', 'GoFunction', 'GoMethod',
            'CSharpMethod', 'CppMethod', 'CFunction',
        ].includes(node.kind);
    }

    /**
     * Check if node is a class-like construct.
     */
    private isClassLike(node: AstNode): boolean {
        return [
            'Class', 'JavaClass', 'CppClass', 'CSharpClass', 'GoStruct',
        ].includes(node.kind);
    }

    /**
     * Check if node is a file.
     */
    private isFileLike(node: AstNode): boolean {
        return node.kind === 'File';
    }

    /**
     * Analyze all nodes and return aggregated smell statistics.
     */
    analyzeAll(
        nodes: AstNode[],
        relationships: RelationshipInfo[] = []
    ): CodeSmellAnalysisResult {
        const allSmells: Array<CodeSmell & { entityId: string; filePath: string }> = [];
        const smellsBySeverity: Record<CodeSmellSeverity, number> = {
            info: 0,
            low: 0,
            medium: 0,
            high: 0,
            critical: 0,
        };
        const smellsByCategory: Record<CodeSmellCategory, number> = {
            complexity: 0,
            size: 0,
            coupling: 0,
            naming: 0,
            duplication: 0,
            architecture: 0,
            maintainability: 0,
            performance: 0,
        };
        const smellsByType: Record<string, number> = {};

        // Detect smells for each node
        for (const node of nodes) {
            const smells = this.detectSmells(node);
            for (const smell of smells) {
                allSmells.push({
                    ...smell,
                    entityId: node.entityId,
                    filePath: node.filePath,
                });
                smellsBySeverity[smell.severity]++;
                smellsByCategory[smell.category]++;
                smellsByType[smell.type] = (smellsByType[smell.type] || 0) + 1;
            }
        }

        // Detect architectural smells
        const circularDeps = this.detectCircularDependencies(nodes, relationships);
        for (const smell of circularDeps) {
            allSmells.push({
                ...smell,
                entityId: '',
                filePath: '',
            });
            smellsBySeverity[smell.severity]++;
            smellsByCategory[smell.category]++;
            smellsByType[smell.type] = (smellsByType[smell.type] || 0) + 1;
        }

        // Detect dead code
        const deadCode = this.detectDeadCode(nodes, relationships);
        for (const smell of deadCode) {
            allSmells.push({
                ...smell,
                entityId: '',
                filePath: '',
            });
            smellsBySeverity[smell.severity]++;
            smellsByCategory[smell.category]++;
            smellsByType[smell.type] = (smellsByType[smell.type] || 0) + 1;
        }

        // Estimate technical debt (rough estimate: 30min per medium, 1hr per high, 2hr per critical)
        const technicalDebtMinutes =
            smellsBySeverity.low * 15 +
            smellsBySeverity.medium * 30 +
            smellsBySeverity.high * 60 +
            smellsBySeverity.critical * 120;

        return {
            totalSmells: allSmells.length,
            smells: allSmells,
            smellsBySeverity,
            smellsByCategory,
            smellsByType,
            technicalDebtMinutes,
            technicalDebtHours: Math.round(technicalDebtMinutes / 60 * 10) / 10,
        };
    }
}

// =============================================================================
// Types
// =============================================================================

export interface CodeSmellAnalysisResult {
    totalSmells: number;
    smells: Array<CodeSmell & { entityId: string; filePath: string }>;
    smellsBySeverity: Record<CodeSmellSeverity, number>;
    smellsByCategory: Record<CodeSmellCategory, number>;
    smellsByType: Record<string, number>;
    technicalDebtMinutes: number;
    technicalDebtHours: number;
}

// =============================================================================
// Convenience Functions
// =============================================================================

/**
 * Create a code smell detector.
 */
export function createCodeSmellDetector(
    logger: winston.Logger,
    thresholds?: Partial<CodeSmellThresholds>
): CodeSmellDetector {
    return new CodeSmellDetector(logger, thresholds);
}

/**
 * Quick check for smells on a single node.
 */
export function detectSmells(node: AstNode, logger: winston.Logger): CodeSmell[] {
    const detector = new CodeSmellDetector(logger);
    return detector.detectSmells(node);
}

/**
 * Get smell severity color for display.
 */
export function getSeverityColor(severity: CodeSmellSeverity): string {
    const colors: Record<CodeSmellSeverity, string> = {
        info: 'blue',
        low: 'green',
        medium: 'yellow',
        high: 'orange',
        critical: 'red',
    };
    return colors[severity];
}
