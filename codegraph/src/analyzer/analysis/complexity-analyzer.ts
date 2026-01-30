import { Node, SyntaxKind, ts } from 'ts-morph';
import { CodeMetrics } from '../types.js';

const { SyntaxKind: SK } = ts; // Alias for brevity

// =============================================================================
// Cognitive Complexity Constants
// =============================================================================

/**
 * Control flow structures that add to cognitive complexity.
 * Each adds +1 base, and +1 for each nesting level.
 */
const COGNITIVE_CONTROL_FLOW = new Set([
    SK.IfStatement,
    SK.ForStatement,
    SK.ForInStatement,
    SK.ForOfStatement,
    SK.WhileStatement,
    SK.DoStatement,
    SK.SwitchStatement,
    SK.CatchClause,
    SK.ConditionalExpression,
]);

/**
 * Structures that increase nesting level for cognitive complexity.
 */
const NESTING_STRUCTURES = new Set([
    SK.IfStatement,
    SK.ForStatement,
    SK.ForInStatement,
    SK.ForOfStatement,
    SK.WhileStatement,
    SK.DoStatement,
    SK.SwitchStatement,
    SK.CatchClause,
    SK.ConditionalExpression,
    SK.ArrowFunction,
    SK.FunctionExpression,
]);

/**
 * Flow-breaking keywords that add complexity without nesting.
 */
const FLOW_BREAKS = new Set([
    SK.BreakStatement,
    SK.ContinueStatement,
]);

/**
 * Calculates the cyclomatic complexity of a given code block or expression.
 * Complexity = Decision Points + 1
 * Decision Points include: if, for, while, case, &&, ||, ?, ??, catch clauses.
 *
 * @param node - The ts-morph Node representing the function/method body or relevant block.
 * @returns The calculated cyclomatic complexity score.
 */
export function calculateCyclomaticComplexity(node: Node | undefined): number {
    if (!node) {
        return 1; // Default complexity for an empty or undefined body
    }

    let complexity = 1; // Start with 1 for the single entry point

    try {
        node.forEachDescendant((descendant) => {
            const kind = descendant.getKind();

            // Increment for standard decision points
            if (
                kind === SK.IfStatement ||
                kind === SK.ForStatement ||
                kind === SK.ForInStatement ||
                kind === SK.ForOfStatement ||
                kind === SK.WhileStatement ||
                kind === SK.DoStatement ||
                kind === SK.CaseClause ||
                kind === SK.CatchClause ||
                kind === SK.ConditionalExpression // Ternary '?'
            ) {
                complexity++;
            }
            // Increment for logical operators within BinaryExpressions
            else if (Node.isBinaryExpression(descendant)) { // Use type guard
                const operatorKind = descendant.getOperatorToken().getKind();
                if (
                    operatorKind === SK.AmpersandAmpersandToken || // &&
                    operatorKind === SK.BarBarToken ||             // ||
                    operatorKind === SK.QuestionQuestionToken    // ??
                ) {
                    complexity++;
                }
            }

            // Optional: Prevent descending into nested functions/classes
            // if (Node.isFunctionLikeDeclaration(descendant) || Node.isClassDeclaration(descendant)) {
            //     return false; // Stop traversal for this branch
            // }
        });
    } catch (e) {
        console.warn(`Error calculating complexity: ${e}`);
        return 1; // Return default complexity on error
    }

    return complexity;
}

// =============================================================================
// Cognitive Complexity
// =============================================================================

/**
 * Calculates cognitive complexity of a code block.
 *
 * Cognitive complexity measures how difficult code is to understand.
 * It differs from cyclomatic complexity by:
 * - Adding a nesting penalty for nested control structures
 * - Not counting all paths equally (switch cases don't each add 1)
 * - Accounting for flow-breaking constructs (break, continue with labels)
 * - Penalizing recursion
 *
 * Rules:
 * - +1 for each control flow statement (if, for, while, etc.)
 * - +1 additional for each level of nesting
 * - +1 for each "else if" or "else"
 * - +1 for each logical operator sequence break (e.g., a && b || c)
 * - +1 for recursion
 *
 * @param node - The ts-morph Node to analyze
 * @param functionName - Optional function name for recursion detection
 * @returns The cognitive complexity score
 */
export function calculateCognitiveComplexity(
    node: Node | undefined,
    functionName?: string
): number {
    if (!node) {
        return 0;
    }

    let complexity = 0;

    try {
        const processNode = (currentNode: Node, nestingLevel: number) => {
            const kind = currentNode.getKind();

            // Control flow structures: +1 base + nesting penalty
            if (COGNITIVE_CONTROL_FLOW.has(kind)) {
                complexity += 1 + nestingLevel;
            }

            // "else" and "else if" add +1 each (handled separately from if)
            if (kind === SK.IfStatement) {
                const ifStmt = currentNode as any;
                const elseStatement = ifStmt.getElseStatement?.();
                if (elseStatement) {
                    // Check if it's "else if" or plain "else"
                    if (elseStatement.getKind() === SK.IfStatement) {
                        // "else if" - the if will be counted in next iteration
                        // but we don't add nesting penalty for else if
                    } else {
                        // Plain "else" - add 1
                        complexity += 1;
                    }
                }
            }

            // Logical operator sequences
            if (Node.isBinaryExpression(currentNode)) {
                const operatorKind = currentNode.getOperatorToken().getKind();
                if (operatorKind === SK.AmpersandAmpersandToken || operatorKind === SK.BarBarToken) {
                    // Check if parent is also a binary expression with different operator
                    const parent = currentNode.getParent();
                    if (Node.isBinaryExpression(parent)) {
                        const parentOp = parent.getOperatorToken().getKind();
                        if (parentOp !== operatorKind &&
                            (parentOp === SK.AmpersandAmpersandToken || parentOp === SK.BarBarToken)) {
                            // Sequence break: a && b || c
                            complexity += 1;
                        }
                    } else {
                        // First in a logical sequence
                        complexity += 1;
                    }
                }
            }

            // Flow-breaking statements with labels add complexity
            if (FLOW_BREAKS.has(kind)) {
                const stmt = currentNode as any;
                if (stmt.getLabel?.()) {
                    complexity += 1; // Labeled break/continue
                }
            }

            // Recursion detection
            if (functionName && kind === SK.CallExpression) {
                const callExpr = currentNode as any;
                const calledName = callExpr.getExpression?.().getText?.();
                if (calledName === functionName) {
                    complexity += 1; // Recursion penalty
                }
            }

            // Calculate new nesting level for children
            let newNestingLevel = nestingLevel;
            if (NESTING_STRUCTURES.has(kind)) {
                newNestingLevel = nestingLevel + 1;
            }

            // Process children
            currentNode.forEachChild(child => {
                // Don't descend into nested function declarations (they have their own complexity)
                const childKind = child.getKind();
                if (childKind !== SK.FunctionDeclaration &&
                    childKind !== SK.MethodDeclaration &&
                    childKind !== SK.Constructor) {
                    processNode(child, newNestingLevel);
                }
            });
        };

        processNode(node, 0);
    } catch (e) {
        console.warn(`Error calculating cognitive complexity: ${e}`);
        return 0;
    }

    return complexity;
}

// =============================================================================
// Nesting Depth
// =============================================================================

/**
 * Calculates the maximum nesting depth of control structures.
 *
 * @param node - The ts-morph Node to analyze
 * @returns The maximum nesting depth (0 if no nesting)
 */
export function calculateNestingDepth(node: Node | undefined): number {
    if (!node) {
        return 0;
    }

    let maxDepth = 0;

    try {
        const processNode = (currentNode: Node, currentDepth: number) => {
            const kind = currentNode.getKind();

            // Check if this is a nesting structure
            let newDepth = currentDepth;
            if (NESTING_STRUCTURES.has(kind)) {
                newDepth = currentDepth + 1;
                maxDepth = Math.max(maxDepth, newDepth);
            }

            // Process children
            currentNode.forEachChild(child => {
                // Don't descend into nested function declarations
                const childKind = child.getKind();
                if (childKind !== SK.FunctionDeclaration &&
                    childKind !== SK.MethodDeclaration &&
                    childKind !== SK.Constructor) {
                    processNode(child, newDepth);
                }
            });
        };

        processNode(node, 0);
    } catch (e) {
        console.warn(`Error calculating nesting depth: ${e}`);
        return 0;
    }

    return maxDepth;
}

// =============================================================================
// Lines of Code
// =============================================================================

/**
 * Counts lines of code (excluding comments and blank lines).
 *
 * @param node - The ts-morph Node to analyze
 * @returns Number of lines of actual code
 */
export function calculateLinesOfCode(node: Node | undefined): number {
    if (!node) {
        return 0;
    }

    try {
        const text = node.getText();
        const lines = text.split('\n');

        let loc = 0;
        let inBlockComment = false;

        for (const line of lines) {
            const trimmed = line.trim();

            // Handle block comments
            if (inBlockComment) {
                if (trimmed.includes('*/')) {
                    inBlockComment = false;
                }
                continue;
            }

            // Skip empty lines
            if (trimmed === '') {
                continue;
            }

            // Skip single-line comments
            if (trimmed.startsWith('//')) {
                continue;
            }

            // Check for block comment start
            if (trimmed.startsWith('/*')) {
                if (!trimmed.includes('*/')) {
                    inBlockComment = true;
                }
                continue;
            }

            // Count as code line
            loc++;
        }

        return loc;
    } catch (e) {
        console.warn(`Error calculating LOC: ${e}`);
        return 0;
    }
}

// =============================================================================
// Parameter Count
// =============================================================================

/**
 * Counts the number of parameters in a function/method.
 *
 * @param node - The ts-morph Node (should be function-like)
 * @returns Number of parameters
 */
export function calculateParameterCount(node: Node | undefined): number {
    if (!node) {
        return 0;
    }

    try {
        // Check if node has getParameters method
        if (Node.isFunctionDeclaration(node) ||
            Node.isMethodDeclaration(node) ||
            Node.isArrowFunction(node) ||
            Node.isFunctionExpression(node) ||
            Node.isConstructorDeclaration(node)) {
            return node.getParameters().length;
        }
    } catch (e) {
        console.warn(`Error calculating parameter count: ${e}`);
    }

    return 0;
}

// =============================================================================
// Unified Metrics Function
// =============================================================================

/**
 * Calculates all code metrics for a function/method node.
 *
 * @param node - The ts-morph Node to analyze
 * @param functionName - Optional function name for recursion detection
 * @returns CodeMetrics object with all computed metrics
 */
export function calculateCodeMetrics(
    node: Node | undefined,
    functionName?: string
): CodeMetrics {
    return {
        cyclomaticComplexity: calculateCyclomaticComplexity(node),
        cognitiveComplexity: calculateCognitiveComplexity(node, functionName),
        nestingDepth: calculateNestingDepth(node),
        loc: calculateLinesOfCode(node),
        parameterCount: calculateParameterCount(node),
    };
}

/**
 * Determines if metrics indicate a complexity hotspot.
 *
 * @param metrics - The computed metrics
 * @returns Object with isHotspot flag and reasons
 */
export function isComplexityHotspot(metrics: CodeMetrics): {
    isHotspot: boolean;
    reasons: string[];
} {
    const reasons: string[] = [];

    // Thresholds for hotspot detection
    const THRESHOLDS = {
        cyclomaticComplexity: 15,
        cognitiveComplexity: 20,
        nestingDepth: 4,
        loc: 100,
        parameterCount: 5,
    };

    if (metrics.cyclomaticComplexity > THRESHOLDS.cyclomaticComplexity) {
        reasons.push(`High cyclomatic complexity: ${metrics.cyclomaticComplexity} (threshold: ${THRESHOLDS.cyclomaticComplexity})`);
    }

    if (metrics.cognitiveComplexity > THRESHOLDS.cognitiveComplexity) {
        reasons.push(`High cognitive complexity: ${metrics.cognitiveComplexity} (threshold: ${THRESHOLDS.cognitiveComplexity})`);
    }

    if (metrics.nestingDepth > THRESHOLDS.nestingDepth) {
        reasons.push(`Deep nesting: ${metrics.nestingDepth} levels (threshold: ${THRESHOLDS.nestingDepth})`);
    }

    if (metrics.loc > THRESHOLDS.loc) {
        reasons.push(`Long method: ${metrics.loc} LOC (threshold: ${THRESHOLDS.loc})`);
    }

    if (metrics.parameterCount > THRESHOLDS.parameterCount) {
        reasons.push(`Too many parameters: ${metrics.parameterCount} (threshold: ${THRESHOLDS.parameterCount})`);
    }

    return {
        isHotspot: reasons.length > 0,
        reasons,
    };
}