// src/analyzer/metrics-analyzer.ts
/**
 * Language-agnostic code metrics analyzer.
 * Provides unified interface for computing metrics across different languages.
 */

import winston from 'winston';
import { AstNode, CodeMetrics, ComplexityHotspot } from './types.js';

// =============================================================================
// Thresholds Configuration
// =============================================================================

/**
 * Default thresholds for code metrics.
 * Can be overridden per-project.
 */
export interface MetricsThresholds {
    /** Max cyclomatic complexity before flagging */
    cyclomaticComplexity: number;
    /** Max cognitive complexity before flagging */
    cognitiveComplexity: number;
    /** Max nesting depth before flagging */
    nestingDepth: number;
    /** Max lines of code for a function/method */
    methodLoc: number;
    /** Max lines of code for a class */
    classLoc: number;
    /** Max parameter count */
    parameterCount: number;
    /** Max methods per class */
    methodsPerClass: number;
}

export const DEFAULT_THRESHOLDS: MetricsThresholds = {
    cyclomaticComplexity: 15,
    cognitiveComplexity: 20,
    nestingDepth: 4,
    methodLoc: 50,
    classLoc: 500,
    parameterCount: 5,
    methodsPerClass: 20,
};

// =============================================================================
// Text-Based Metrics (Language Agnostic)
// =============================================================================

/**
 * Calculate metrics from source text (language-agnostic fallback).
 * Used when AST-based analysis is not available.
 */
export function calculateTextBasedMetrics(sourceText: string): Partial<CodeMetrics> {
    const lines = sourceText.split('\n');
    let loc = 0;
    let maxNesting = 0;
    let currentNesting = 0;
    let inBlockComment = false;

    // Patterns for control flow (generic across languages)
    const controlFlowPattern = /\b(if|else|for|while|do|switch|case|catch|try)\b/;
    const blockStartPattern = /[{(]/g;
    const blockEndPattern = /[})]/g;

    for (const line of lines) {
        const trimmed = line.trim();

        // Handle block comments
        if (inBlockComment) {
            if (trimmed.includes('*/') || trimmed.includes('"""') || trimmed.includes("'''")) {
                inBlockComment = false;
            }
            continue;
        }

        // Skip empty lines
        if (trimmed === '') continue;

        // Skip single-line comments
        if (trimmed.startsWith('//') || trimmed.startsWith('#') || trimmed.startsWith('--')) {
            continue;
        }

        // Check for block comment start
        if (trimmed.startsWith('/*') || trimmed.startsWith('"""') || trimmed.startsWith("'''")) {
            if (!trimmed.endsWith('*/') && !(trimmed.length > 3 && (trimmed.endsWith('"""') || trimmed.endsWith("'''")))) {
                inBlockComment = true;
            }
            continue;
        }

        loc++;

        // Track nesting depth (approximate)
        const opens = (line.match(blockStartPattern) || []).length;
        const closes = (line.match(blockEndPattern) || []).length;
        currentNesting += opens - closes;
        maxNesting = Math.max(maxNesting, currentNesting);
    }

    return {
        loc,
        nestingDepth: Math.max(0, maxNesting),
    };
}

/**
 * Estimate cyclomatic complexity from source text.
 * This is an approximation when AST is not available.
 */
export function estimateCyclomaticComplexityFromText(sourceText: string): number {
    let complexity = 1; // Base complexity

    // Control flow keywords (generic)
    const patterns = [
        /\bif\b/g,
        /\belse\s+if\b/g,
        /\bfor\b/g,
        /\bforeach\b/g,
        /\bwhile\b/g,
        /\bdo\b/g,
        /\bcase\b/g,
        /\bcatch\b/g,
        /\?\s*[^:]/g,  // Ternary operator
        /&&/g,
        /\|\|/g,
        /\?\?/g,
    ];

    for (const pattern of patterns) {
        const matches = sourceText.match(pattern);
        if (matches) {
            complexity += matches.length;
        }
    }

    return complexity;
}

/**
 * Estimate cognitive complexity from source text.
 */
export function estimateCognitiveComplexityFromText(sourceText: string): number {
    let complexity = 0;
    const lines = sourceText.split('\n');
    let nestingLevel = 0;

    const nestingKeywords = /\b(if|for|foreach|while|do|switch|try|catch)\b/;
    const blockStart = /{/;
    const blockEnd = /}/;

    for (const line of lines) {
        const trimmed = line.trim();

        // Skip comments
        if (trimmed.startsWith('//') || trimmed.startsWith('#') || trimmed.startsWith('*')) {
            continue;
        }

        // Check for nesting keywords
        if (nestingKeywords.test(trimmed)) {
            complexity += 1 + nestingLevel;
        }

        // Track nesting via braces
        if (blockStart.test(trimmed)) {
            if (nestingKeywords.test(trimmed)) {
                nestingLevel++;
            }
        }
        if (blockEnd.test(trimmed)) {
            nestingLevel = Math.max(0, nestingLevel - 1);
        }

        // Check for else
        if (/\belse\b/.test(trimmed) && !/\belse\s+if\b/.test(trimmed)) {
            complexity += 1;
        }

        // Check for logical operators
        const logicalOps = (trimmed.match(/&&|\|\|/g) || []).length;
        if (logicalOps > 0) {
            complexity += 1; // One for the sequence
        }
    }

    return complexity;
}

// =============================================================================
// Metrics Analyzer Class
// =============================================================================

/**
 * Analyzes code metrics for AST nodes.
 */
export class MetricsAnalyzer {
    private logger: winston.Logger;
    private thresholds: MetricsThresholds;

    constructor(logger: winston.Logger, thresholds?: Partial<MetricsThresholds>) {
        this.logger = logger;
        this.thresholds = { ...DEFAULT_THRESHOLDS, ...thresholds };
    }

    /**
     * Compute metrics for a function/method node from source text.
     * Used when the node doesn't have pre-computed metrics.
     */
    computeMetricsFromText(
        sourceText: string,
        startLine: number,
        endLine: number
    ): CodeMetrics {
        // Extract the relevant portion of source
        const lines = sourceText.split('\n');
        const relevantLines = lines.slice(startLine - 1, endLine);
        const relevantText = relevantLines.join('\n');

        const textMetrics = calculateTextBasedMetrics(relevantText);

        return {
            cyclomaticComplexity: estimateCyclomaticComplexityFromText(relevantText),
            cognitiveComplexity: estimateCognitiveComplexityFromText(relevantText),
            nestingDepth: textMetrics.nestingDepth || 0,
            loc: textMetrics.loc || (endLine - startLine + 1),
            parameterCount: 0, // Cannot determine from text alone
        };
    }

    /**
     * Check if a node's metrics exceed thresholds.
     */
    checkThresholds(metrics: CodeMetrics, nodeKind: string): {
        exceeds: boolean;
        violations: string[];
    } {
        const violations: string[] = [];

        if (metrics.cyclomaticComplexity > this.thresholds.cyclomaticComplexity) {
            violations.push(`Cyclomatic complexity ${metrics.cyclomaticComplexity} exceeds ${this.thresholds.cyclomaticComplexity}`);
        }

        if (metrics.cognitiveComplexity > this.thresholds.cognitiveComplexity) {
            violations.push(`Cognitive complexity ${metrics.cognitiveComplexity} exceeds ${this.thresholds.cognitiveComplexity}`);
        }

        if (metrics.nestingDepth > this.thresholds.nestingDepth) {
            violations.push(`Nesting depth ${metrics.nestingDepth} exceeds ${this.thresholds.nestingDepth}`);
        }

        // LOC threshold depends on node type
        const locThreshold = nodeKind === 'Class' ? this.thresholds.classLoc : this.thresholds.methodLoc;
        if (metrics.loc > locThreshold) {
            violations.push(`LOC ${metrics.loc} exceeds ${locThreshold}`);
        }

        if (metrics.parameterCount > this.thresholds.parameterCount) {
            violations.push(`Parameter count ${metrics.parameterCount} exceeds ${this.thresholds.parameterCount}`);
        }

        return {
            exceeds: violations.length > 0,
            violations,
        };
    }

    /**
     * Find complexity hotspots in a list of nodes.
     */
    findHotspots(nodes: AstNode[], limit: number = 10): ComplexityHotspot[] {
        const hotspots: ComplexityHotspot[] = [];

        for (const node of nodes) {
            // Only analyze functions, methods, and classes
            if (!['Function', 'Method', 'Class', 'JavaMethod', 'GoFunction', 'GoMethod',
                  'CSharpMethod', 'CppMethod', 'CFunction', 'TSFunction'].includes(node.kind)) {
                continue;
            }

            const metrics = node.metrics;
            if (!metrics) continue;

            const { exceeds, violations } = this.checkThresholds(metrics, node.kind);
            if (exceeds) {
                hotspots.push({
                    entityId: node.entityId,
                    name: node.name,
                    filePath: node.filePath,
                    line: node.startLine,
                    kind: node.kind,
                    cyclomaticComplexity: metrics.cyclomaticComplexity,
                    cognitiveComplexity: metrics.cognitiveComplexity,
                    loc: metrics.loc,
                    reason: violations.join('; '),
                });
            }
        }

        // Sort by cognitive complexity (primary) and cyclomatic (secondary)
        hotspots.sort((a, b) => {
            const cogDiff = b.cognitiveComplexity - a.cognitiveComplexity;
            if (cogDiff !== 0) return cogDiff;
            return b.cyclomaticComplexity - a.cyclomaticComplexity;
        });

        return hotspots.slice(0, limit);
    }

    /**
     * Calculate aggregate metrics for a module/file.
     */
    calculateAggregateMetrics(nodes: AstNode[]): {
        totalLoc: number;
        avgCyclomaticComplexity: number;
        avgCognitiveComplexity: number;
        maxCyclomaticComplexity: number;
        maxCognitiveComplexity: number;
        maxNestingDepth: number;
        functionCount: number;
        classCount: number;
    } {
        let totalLoc = 0;
        let totalCyclomatic = 0;
        let totalCognitive = 0;
        let maxCyclomatic = 0;
        let maxCognitive = 0;
        let maxNesting = 0;
        let functionCount = 0;
        let classCount = 0;

        const functionKinds = ['Function', 'Method', 'JavaMethod', 'GoFunction', 'GoMethod',
                               'CSharpMethod', 'CppMethod', 'CFunction', 'TSFunction'];
        const classKinds = ['Class', 'JavaClass', 'CppClass', 'CSharpClass', 'GoStruct'];

        for (const node of nodes) {
            if (node.kind === 'File' && node.loc) {
                totalLoc += node.loc;
            }

            if (functionKinds.includes(node.kind)) {
                functionCount++;
                if (node.metrics) {
                    totalCyclomatic += node.metrics.cyclomaticComplexity;
                    totalCognitive += node.metrics.cognitiveComplexity;
                    maxCyclomatic = Math.max(maxCyclomatic, node.metrics.cyclomaticComplexity);
                    maxCognitive = Math.max(maxCognitive, node.metrics.cognitiveComplexity);
                    maxNesting = Math.max(maxNesting, node.metrics.nestingDepth);
                }
            }

            if (classKinds.includes(node.kind)) {
                classCount++;
            }
        }

        return {
            totalLoc,
            avgCyclomaticComplexity: functionCount > 0 ? totalCyclomatic / functionCount : 0,
            avgCognitiveComplexity: functionCount > 0 ? totalCognitive / functionCount : 0,
            maxCyclomaticComplexity: maxCyclomatic,
            maxCognitiveComplexity: maxCognitive,
            maxNestingDepth: maxNesting,
            functionCount,
            classCount,
        };
    }
}

// =============================================================================
// Language-Specific Metrics Helpers
// =============================================================================

/**
 * Count parameters from a parameter list string.
 * Works for most C-style languages.
 */
export function countParametersFromSignature(signature: string): number {
    // Extract content between parentheses
    const match = signature.match(/\(([^)]*)\)/);
    if (!match || !match[1].trim()) {
        return 0;
    }

    const params = match[1];
    // Count commas + 1 (handling empty case)
    if (params.trim() === '') {
        return 0;
    }

    // Handle generic types with commas inside angle brackets
    let depth = 0;
    let count = 1;
    for (const char of params) {
        if (char === '<' || char === '[') depth++;
        if (char === '>' || char === ']') depth--;
        if (char === ',' && depth === 0) count++;
    }

    return count;
}

/**
 * Extract metrics from Python function with decorators.
 */
export function extractPythonMetrics(
    sourceText: string,
    startLine: number,
    endLine: number
): CodeMetrics {
    const lines = sourceText.split('\n').slice(startLine - 1, endLine);
    const functionText = lines.join('\n');

    // Count parameters from def line
    const defMatch = functionText.match(/def\s+\w+\s*\(([^)]*)\)/);
    let paramCount = 0;
    if (defMatch && defMatch[1].trim()) {
        // Remove 'self' and 'cls' from count
        const params = defMatch[1].split(',')
            .map(p => p.trim())
            .filter(p => p && p !== 'self' && p !== 'cls');
        paramCount = params.length;
    }

    const textMetrics = calculateTextBasedMetrics(functionText);

    return {
        cyclomaticComplexity: estimateCyclomaticComplexityFromText(functionText),
        cognitiveComplexity: estimateCognitiveComplexityFromText(functionText),
        nestingDepth: textMetrics.nestingDepth || 0,
        loc: textMetrics.loc || lines.length,
        parameterCount: paramCount,
    };
}

/**
 * Extract metrics from Go function.
 */
export function extractGoMetrics(
    sourceText: string,
    startLine: number,
    endLine: number
): CodeMetrics {
    const lines = sourceText.split('\n').slice(startLine - 1, endLine);
    const functionText = lines.join('\n');

    // Count parameters from func signature
    const funcMatch = functionText.match(/func\s*(?:\([^)]*\))?\s*\w*\s*\(([^)]*)\)/);
    let paramCount = 0;
    if (funcMatch && funcMatch[1].trim()) {
        // Go parameters can be grouped: (a, b int, c string)
        const params = funcMatch[1].split(',').filter(p => p.trim());
        paramCount = params.length;
    }

    const textMetrics = calculateTextBasedMetrics(functionText);

    return {
        cyclomaticComplexity: estimateCyclomaticComplexityFromText(functionText),
        cognitiveComplexity: estimateCognitiveComplexityFromText(functionText),
        nestingDepth: textMetrics.nestingDepth || 0,
        loc: textMetrics.loc || lines.length,
        parameterCount: paramCount,
    };
}

// =============================================================================
// Convenience Functions
// =============================================================================

/**
 * Create a default metrics analyzer.
 */
export function createMetricsAnalyzer(
    logger: winston.Logger,
    thresholds?: Partial<MetricsThresholds>
): MetricsAnalyzer {
    return new MetricsAnalyzer(logger, thresholds);
}

/**
 * Check if metrics indicate a "god class" (too large/complex).
 */
export function isGodClass(
    methodCount: number,
    totalLoc: number,
    avgComplexity: number
): boolean {
    return (
        methodCount > 20 ||
        totalLoc > 500 ||
        (methodCount > 10 && avgComplexity > 10)
    );
}

/**
 * Check if metrics indicate a "data class" (no behavior).
 */
export function isDataClass(
    methodCount: number,
    getterSetterCount: number,
    publicFieldCount: number
): boolean {
    // A data class has mostly getters/setters and public fields
    const totalAccessors = getterSetterCount + publicFieldCount;
    return methodCount <= 2 || (getterSetterCount / methodCount > 0.7);
}
