This file is a merged representation of the entire codebase, combined into a single document by Repomix.
The content has been processed where content has been compressed (code blocks are separated by ⋮---- delimiter).

# File Summary

## Purpose
This file contains a packed representation of the entire repository's contents.
It is designed to be easily consumable by AI systems for analysis, code review,
or other automated processes.

## File Format
The content is organized as follows:
1. This summary section
2. Repository information
3. Directory structure
4. Multiple file entries, each consisting of:
  a. A header with the file path (## File: path/to/file)
  b. The full contents of the file in a code block

## Usage Guidelines
- This file should be treated as read-only. Any changes should be made to the
  original repository files, not this packed version.
- When processing this file, use the file path to distinguish
  between different files in the repository.
- Be aware that this file may contain sensitive information. Handle it with
  the same level of security as you would the original repository.

## Notes
- Some files may have been excluded based on .gitignore rules and Repomix's configuration
- Binary files are not included in this packed representation. Please refer to the Repository Structure section for a complete list of file paths, including binary files
- Files matching patterns in .gitignore are excluded
- Files matching default ignore patterns are excluded
- Content has been compressed - code blocks are separated by ⋮---- delimiter
- Files are sorted by Git change count (files with more changes are at the bottom)

## Additional Info

# Directory Structure
```
.roo/
  mcp.json
mcp/
  src/
    index.ts
  package.json
  tsconfig.json
src/
  analyzer/
    analysis/
      analyzer-utils.ts
      assignment-analyzer.ts
      call-analyzer.ts
      complexity-analyzer.ts
      control-flow-analyzer.ts
    parsers/
      c-cpp-parser.spec.ts
      c-cpp-parser.ts
      class-parser.ts
      component-parser.ts
      csharp-parser.spec.ts
      csharp-parser.ts
      function-parser.ts
      go-parser.spec.ts
      go-parser.ts
      import-parser.ts
      interface-parser.ts
      java-parser.spec.ts
      java-parser.ts
      jsx-parser.ts
      parameter-parser.ts
      sql-parser.ts
      type-alias-parser.ts
      variable-parser.ts
    resolvers/
      c-cpp-resolver.ts
      ts-resolver.ts
    analyzer-service.ts
    cypher-utils.ts
    parser-utils.ts
    parser.ts
    python-parser.spec.ts
    python-parser.ts
    relationship-resolver.spec.ts
    relationship-resolver.ts
    storage-manager.ts
    types.ts
  cli/
    analyze.ts
  config/
    index.ts
  database/
    neo4j-client.ts
    schema.ts
  scanner/
    file-scanner.ts
  utils/
    errors.ts
    logger.ts
    ts-helpers.ts
  index.ts
.gitignore
package.json
python_parser.py
README.md
run_neo4j_server.sh
tsconfig.json
```

# Files

## File: .roo/mcp.json
````json
{
  "mcpServers": {
    "bmcp-code-analyzer": {
      "command": "node",
      "args": [
        "c:/code/bmcp/mcp/dist/index.js"
      ],
      "disabled": false,
      "alwaysAllow": [
        "run_analyzer",
        "start_watcher",
        "stop_watcher"
      ]
    }
  }
}
````

## File: mcp/src/index.ts
````typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js"; // Use McpServer, import type
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { execa } from 'execa';
import path from 'path';
// import { spawn } from 'child_process'; // Remove spawn import
import { fileURLToPath } from 'url';
import { McpError, ErrorCode } from "@modelcontextprotocol/sdk/types.js"; // Import error types
⋮----
// Define __dirname for ESM
⋮----
// Path to the compiled main script
⋮----
// Define the input schema for the run_analyzer tool - used for validation internally by SDK
⋮----
// Define the expected shape of the arguments for the handler based on the schema
type RunAnalyzerArgs = z.infer<typeof RunAnalyzerInputSchema>;
⋮----
// Create an MCP server
⋮----
// Add the run_analyzer tool
⋮----
// Provide the parameter shape, not the full schema object
⋮----
// Let types be inferred for args and context, remove explicit McpResponse return type
⋮----
// Type assertion for args based on the shape provided above
⋮----
const projectRootDir = path.resolve(__dirname, '..', '..'); // c:/code/amcp
⋮----
// --- Construct the manual command string ---
⋮----
// Quote path
⋮----
// Quote path
⋮----
// Return the command details as JSON within the text content
⋮----
_meta: { requires_execute_command: true } // Add metadata hint
⋮----
// Error handling (optional but recommended)
// server.onerror = (error) => console.error('[MCP Error]', error);
// Remove - Property 'onerror' does not exist on type 'McpServer'.
⋮----
// Start receiving messages on stdin and sending messages on stdout
async function startServer()
````

## File: mcp/package.json
````json
{
  "name": "code-analyzer-mcp-server",
  "version": "0.1.0",
  "description": "MCP server to run the code analyzer CLI",
  "main": "dist/index.js",
  "type": "module",
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "start": "node dist/index.js",
    "dev": "ts-node src/index.ts",
    "test": "echo \"Error: no test specified\" && exit 1"
  },
  "keywords": [
    "mcp",
    "code-analysis"
  ],
  "author": "Roo",
  "license": "MIT",
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.8.0",
    "execa": "^8.0.1",
    "zod": "^3.22.4",
    "zod-to-json-schema": "^3.24.5"
  },
  "devDependencies": {
    "@types/node": "^20.11.24",
    "ts-node": "^10.9.2",
    "typescript": "^5.2.2"
  }
}
````

## File: mcp/tsconfig.json
````json
{
  "compilerOptions": {
    "target": "ES2022", // Target modern ECMAScript version
    "module": "NodeNext", // Use Node.js's native ES module support
    "moduleResolution": "NodeNext", // Resolve modules like Node.js
    "outDir": "./dist", // Output directory for compiled JavaScript
    "rootDir": "./src", // Root directory of source files
    "strict": true, // Enable all strict type-checking options
    "esModuleInterop": true, // Allows default imports from CommonJS modules
    "skipLibCheck": true, // Skip type checking of declaration files
    "forceConsistentCasingInFileNames": true, // Disallow inconsistently-cased references
    "declaration": true, // Generate corresponding '.d.ts' file
    "sourceMap": true // Generate source maps for debugging
  },
  "include": ["src/**/*"], // Include all files in the src directory
  "exclude": ["node_modules", "dist"] // Exclude node_modules and dist directories
}
````

## File: src/analyzer/analysis/analyzer-utils.ts
````typescript
// src/analyzer/analysis/analyzer-utils.ts
import { Node, SyntaxKind as SK, ClassDeclaration, InterfaceDeclaration, FunctionDeclaration, MethodDeclaration, ArrowFunction, FunctionExpression, MethodSignature, VariableDeclaration, ParameterDeclaration, TypeAliasDeclaration, EnumDeclaration, EnumMember, Expression } from 'ts-morph';
import { TargetDeclarationInfo } from '../types.js'; // Assuming TargetDeclarationInfo is defined here
import { generateEntityId } from '../parser-utils.js';
import winston from 'winston';
⋮----
/**
 * Represents the resolved information about a target declaration.
 */
// export interface TargetDeclarationInfo { // Moved to types.ts
//     name: string;
//     kind: string; // e.g., 'Function', 'Class', 'Variable', 'Interface', 'Method', 'Parameter'
//     filePath: string; // Absolute, normalized path
//     entityId: string; // Globally unique ID matching Pass 1 generation
// }
⋮----
/**
 * Resolves the declaration information for a given expression node.
 * Tries to find the original declaration, handling aliases (imports).
 * Generates an entityId consistent with Pass 1 parsers.
 *
 * @param expression - The expression node to resolve (e.g., identifier, property access).
 * @param currentFilePath - The absolute, normalized path of the file containing the expression.
 * @param resolveImportPath - Function to resolve relative import paths.
 * @param logger - Winston logger instance.
 * @returns TargetDeclarationInfo object or null if resolution fails.
 */
export function getTargetDeclarationInfo(
    expression: Node,
    currentFilePath: string,
    resolveImportPath: (sourcePath: string, importPath: string) => string,
    logger: winston.Logger
): TargetDeclarationInfo | null
⋮----
// logger.debug(`Symbol not found for expression: ${expression.getText().substring(0, 50)}...`); // Keep this commented unless needed
⋮----
// If the direct symbol is an alias (like an import), get the original symbol
⋮----
// logger.debug(`Symbol '${symbol.getName()}' is an alias. Using aliased symbol '${aliasedSymbol.getName()}'.`); // Keep commented unless needed
⋮----
// It's possible the aliased symbol also has no declarations (e.g., importing a type from a declaration file)
⋮----
// Resolve path relative to the *current* file, not the declaration file
const resolvedFilePath = resolveImportPath(currentFilePath, originalFilePath).replace(/\\/g, '/'); // Normalize path
⋮----
// Determine kind and base qualified name
⋮----
name = (Node.isFunctionDeclaration(declaration) || Node.isFunctionExpression(declaration)) ? declaration.getName() ?? name : name; // Use getName() if available for named functions
⋮----
// Use simplified ID format (filePath:Parent.method)
⋮----
kind = 'Function'; // Treat variable assigned functions as Function kind
⋮----
// Use simplified ID format (filePath:name) for functions
⋮----
// Variables might still need line numbers if declared multiple times in scope?
// For now, keep it simple: filePath:name
⋮----
// Find the containing function/method using ancestor traversal
⋮----
// Added MethodSignature check
⋮----
const resolvedParentFilePath = resolveImportPath(currentFilePath, parentFilePath).replace(/\\/g, '/'); // Use currentFilePath & normalize
// Construct the parent's qualified name string (consistent with function/method parsers)
// Need to include line number for parent function/method here too for consistency
⋮----
const parentQualifiedName = `${resolvedParentFilePath}:${parentName}:${parentStartLine}`; // Add line number
// Use the parent's qualified name string to build the parameter's qualified name
qualifiedNameForId = `${parentQualifiedName}:${name}`; // Parameter ID includes parent context
⋮----
kind = 'TypeAlias'; // Treat enums like type aliases for simplicity
⋮----
kind = 'TypeAlias'; // Treat enum members like type aliases
⋮----
qualifiedNameForId = `${resolvedFilePath}:${enumName}`; // ID based on the Enum itself
⋮----
// Add other kinds like ImportSpecifier, NamespaceImport if needed
⋮----
// Fallback or if kind is still unknown
⋮----
// If no specific kind was determined, try a fallback or return null
⋮----
// Maybe try symbol flags? e.g., symbol.getFlags() & ts.SymbolFlags.Function
⋮----
// Add start line to qualifier for functions and methods to match parser
// This ensures consistency with entity IDs generated in function-parser.ts
⋮----
// Generate the final entityId
// IMPORTANT: This MUST match the entityId generation logic in Pass 1 parsers
⋮----
// logger.debug(`[getTargetDeclarationInfo] Resolved: ${expression.getText()} -> Target: ${name} (Kind: ${kind}, File: ${resolvedFilePath}, EntityId: ${entityId})`);
````

## File: src/analyzer/analysis/assignment-analyzer.ts
````typescript
import { Node, SyntaxKind, ts, Identifier, BinaryExpression, PropertyAccessExpression } from 'ts-morph';
import { AstNode, ParserContext } from '../types.js';
import { getTargetDeclarationInfo } from './analyzer-utils.js'; // Shared util
⋮----
/**
 * Analyzes a code block (function/method body) for assignment expressions
 * that potentially mutate state (e.g., assigning to `this.property` or module variables).
 * Creates intra-file MUTATES_STATE relationships during Pass 1.
 * Cross-file mutations are handled in Pass 2.
 * @param body - The ts-morph Node representing the code block to analyze.
 * @param parentNode - The AstNode of the containing function or method.
 * @param context - The parser context.
 */
export function analyzeAssignments(body: Node, parentNode: AstNode, context: ParserContext): void
⋮----
// Find BinaryExpressions with an assignment operator (=)
⋮----
// --- Target Resolution ---
⋮----
// Try to resolve the variable/property being assigned to
// Handle `this.property = ...` and `variable = ...`
⋮----
// Potentially `this.prop` or `obj.prop`. Need to resolve `prop`.
// For MUTATES_STATE, we are often interested in the property itself.
// Let's try resolving the property name node.
⋮----
// Simple variable assignment `var = ...`
⋮----
// Skip other complex LHS assignments (e.g., array destructuring) for now
⋮----
// Check if the resolved target is within the current file
⋮----
// Only consider mutations to Variables or Properties (represented as Variables for now)
if (targetInfo.kind === 'Variable' || targetInfo.kind === 'Parameter') { // Allow mutating params? Maybe not ideal. Let's stick to Variable for now.
⋮----
continue; // Skip cross-file in Pass 1
⋮----
continue; // Skip unresolved in Pass 1
⋮----
// --- Create Relationship ---
⋮----
// Could add info about the RHS value type if needed
// valueType: assignment.getRight().getType().getText() || 'unknown'
⋮----
targetId: targetEntityId, // Guaranteed string
weight: 8, // Mutations are significant
````

## File: src/analyzer/analysis/call-analyzer.ts
````typescript
import { Node, SyntaxKind, ts, Identifier, CallExpression } from 'ts-morph';
import { AstNode, ParserContext } from '../types.js';
import { getTargetDeclarationInfo } from './analyzer-utils.js'; // Assuming a shared util for target resolution
⋮----
/**
 * Analyzes a code block (function/method body) for CallExpressions.
 * Creates intra-file CALLS relationships during Pass 1.
 * Cross-file calls are handled in Pass 2.
 * @param body - The ts-morph Node representing the code block to analyze.
 * @param parentNode - The AstNode of the containing function or method.
 * @param context - The parser context.
 */
export function analyzeCalls(body: Node, parentNode: AstNode, context: ParserContext): void
⋮----
const expression = callExpr.getExpression(); // The part being called (e.g., function name, this.method)
⋮----
// Check for conditional context
⋮----
// Attempt to resolve the called function/method declaration
⋮----
// Check if the resolved target is within the current file being parsed
⋮----
// Skip creating relationship in Pass 1
⋮----
// Cannot resolve target, skip in Pass 1
⋮----
// Only proceed if we have a valid intra-file targetEntityId
⋮----
// Use resolved info if available, otherwise fallback
⋮----
resolutionHint: 'symbol_declaration', // Since we resolved it to an intra-file node
⋮----
// Now guaranteed to be string
weight: 7, // Adjust weight as needed
````

## File: src/analyzer/analysis/complexity-analyzer.ts
````typescript
import { Node, SyntaxKind, ts } from 'ts-morph';
⋮----
const { SyntaxKind: SK } = ts; // Alias for brevity
⋮----
/**
 * Calculates the cyclomatic complexity of a given code block or expression.
 * Complexity = Decision Points + 1
 * Decision Points include: if, for, while, case, &&, ||, ?, ??, catch clauses.
 *
 * @param node - The ts-morph Node representing the function/method body or relevant block.
 * @returns The calculated cyclomatic complexity score.
 */
export function calculateCyclomaticComplexity(node: Node | undefined): number
⋮----
return 1; // Default complexity for an empty or undefined body
⋮----
let complexity = 1; // Start with 1 for the single entry point
⋮----
// Increment for standard decision points
⋮----
kind === SK.ConditionalExpression // Ternary '?'
⋮----
// Increment for logical operators within BinaryExpressions
else if (Node.isBinaryExpression(descendant)) { // Use type guard
⋮----
operatorKind === SK.AmpersandAmpersandToken || // &&
operatorKind === SK.BarBarToken ||             // ||
operatorKind === SK.QuestionQuestionToken    // ??
⋮----
// Optional: Prevent descending into nested functions/classes
// if (Node.isFunctionLikeDeclaration(descendant) || Node.isClassDeclaration(descendant)) {
//     return false; // Stop traversal for this branch
// }
⋮----
return 1; // Return default complexity on error
````

## File: src/analyzer/analysis/control-flow-analyzer.ts
````typescript
import { Node, SyntaxKind, ts, TryStatement, CatchClause } from 'ts-morph';
import { AstNode, ParserContext } from '../types.js';
import { getNodeName } from '../../utils/ts-helpers.js'; // If needed for catch block naming
⋮----
/**
 * Analyzes a code block (function/method body) for TryStatements and CatchClauses.
 * Creates HANDLES_ERROR relationships during Pass 1.
 * @param body - The ts-morph Node representing the code block to analyze.
 * @param parentNode - The AstNode of the containing function or method.
 * @param context - The parser context.
 */
export function analyzeControlFlow(body: Node, parentNode: AstNode, context: ParserContext): void
⋮----
if (!catchClause) continue; // Skip try without catch
⋮----
// For simplicity, link the parent function/method directly to the catch clause parameter (if any)
// or create a generic target representing the error handling block.
⋮----
// Option 1: Link to Catch Parameter (if it exists)
⋮----
// Find the corresponding Parameter AstNode created by parameter-parser (might be tricky)
// Or generate a parameter entity ID based on the catch binding
⋮----
// Generate ID relative to the parent function, similar to parameters
⋮----
targetEntityId = generateEntityId('parameter', paramQualifiedName); // Treat catch var as a parameter
⋮----
// We might not have actually created a separate AstNode for the catch parameter,
// so this relationship might point to a non-existent node initially.
// Pass 2 resolver would need to handle this or we adjust parameter parsing.
// For now, let's assume the ID is sufficient.
⋮----
// Option 2: Link to a generic "ErrorHandler" concept for the catch block
⋮----
targetEntityId = generateEntityId('error_handler', handlerQualifiedName); // Use a custom kind
⋮----
// We would need to ensure 'error_handler' is a valid node label in the schema
// or adjust the relationship target logic. Let's stick with Option 1 for now,
// assuming the parameter ID is the intended target. Revert to Option 1 logic:
targetName = 'errorParam'; // Default name if no binding
⋮----
// Create HANDLES_ERROR relationship (Function/Method -> Catch Parameter/Handler)
⋮----
sourceId: parentNode.entityId, // Source is the function/method containing the try-catch
targetId: targetEntityId,     // Target is the conceptual parameter/handler
weight: 5, // Adjust weight as needed
````

## File: src/analyzer/parsers/c-cpp-parser.spec.ts
````typescript
import { describe, it, expect, beforeAll } from 'vitest';
import path from 'path';
import fs from 'fs/promises';
import { CCppParser } from './c-cpp-parser.js'; // Adjust path as needed
import { FileInfo } from '../../scanner/file-scanner.js'; // Adjust path as needed
import { AstNode, RelationshipInfo, SingleFileParseResult } from '../types.js'; // Adjust path as needed
import config from '../../config/index.js'; // Adjust path as needed
⋮----
// Helper to parse a fixture file and return the result
async function parseFixture(fixturePath: string): Promise<SingleFileParseResult>
⋮----
// Ensure temp dir exists (parser might rely on it)
⋮----
} catch (e) { /* Ignore if exists */ }
⋮----
await fs.unlink(tempFilePath); // Clean up temp file
⋮----
const funcNodes = result.nodes.filter(n => n.kind === 'CFunction'); // Using CFunction for now
⋮----
expect(funcNodes.length).toBe(2); // printShapeDetails, main
⋮----
expect(includeNodes.length).toBe(8); // iostream, vector, memory, stdexcept, Shape.h, Rectangle.h, Circle.h, MathUtils.h
⋮----
// Check relationship source
⋮----
// Note: Current parser doesn't explicitly create CppClass nodes yet.
// This test will fail until class parsing is implemented.
⋮----
expect(classNode).toBeDefined(); // This will fail initially
⋮----
// Note: Current parser uses CFunction for methods. Test reflects this.
⋮----
const methodNodes = result.nodes.filter(n => n.kind === 'CFunction'); // Expecting CFunction for now
⋮----
expect(methodNodes.length).toBeGreaterThanOrEqual(7); // Constructor, area, perimeter, getName, getDescription, getRadius, setRadius, getDiameter, validateRadius
⋮----
// Add more tests for other files, classes, relationships as parser evolves
````

## File: src/analyzer/parsers/c-cpp-parser.ts
````typescript
// src/analyzer/parsers/c-cpp-parser.ts
// @ts-ignore - Suppress type error due to potential module resolution/typing issues
import Parser from 'tree-sitter';
// @ts-ignore - Suppress type error due to potential module resolution/typing issues
import C from 'tree-sitter-c';
// @ts-ignore - Suppress type error due to potential module resolution/typing issues
import Cpp from 'tree-sitter-cpp';
import path from 'path';
import fs from 'fs/promises';
import { createContextLogger } from '../../utils/logger.js'; // Adjusted path
import { ParserError } from '../../utils/errors.js'; // Adjusted path
import { FileInfo } from '../../scanner/file-scanner.js'; // Adjusted path
import { AstNode, RelationshipInfo, SingleFileParseResult, InstanceCounter, IncludeDirectiveNode, CFunctionNode, CppClassNode, CppMethodNode } from '../types.js'; // Added CppClassNode & CppMethodNode
import { ensureTempDir, getTempFilePath, generateInstanceId, generateEntityId } from '../parser-utils.js';
⋮----
// Helper to get node text safely
function getNodeText(node: Parser.SyntaxNode | null | undefined): string
⋮----
// Helper to get location
function getNodeLocation(node: Parser.SyntaxNode):
⋮----
// Tree-sitter positions are 0-based, AstNode expects 1-based lines
⋮----
// --- Tree-sitter Visitor ---
class CCppAstVisitor
⋮----
private fileNode: AstNode; // Represents the file being parsed
⋮----
private currentClassEntityId: string | undefined = undefined; // Track current class context (use undefined)
⋮----
constructor(private filepath: string, private language: 'C' | 'C++')
⋮----
// Create the File node representation for this parse
⋮----
const fileEntityId = generateEntityId('file', filepath); // Use 'file' kind for consistency
⋮----
kind: 'File', // Use standard 'File' kind
⋮----
startLine: 1, // File starts at 1
endLine: 0, // Will be updated after parsing
⋮----
visit(node: Parser.SyntaxNode)
⋮----
// Process the current node first
this.visitNode(node); // Always process the node
⋮----
// Always recurse into children, let visitNode handle specific logic
⋮----
// Update file end line after visiting all nodes
if (node.type === 'translation_unit') { // Root node type for C/C++
⋮----
// Returns true if the node type was handled and recursion should potentially stop, false otherwise
private visitNode(node: Parser.SyntaxNode): boolean
⋮----
return true; // Handled, stop recursion here
⋮----
return false; // Allow recursion into namespace body
⋮----
// Workaround for grammar issue: Check if it looks like a class/struct/namespace
⋮----
// logger.warn(`[CCppAstVisitor] Treating misidentified function_definition at ${this.filepath}:${node.startPosition.row + 1} as class/struct.`);
this.visitClassSpecifier(node); // Try processing as class
return false; // Allow recursion
⋮----
// logger.warn(`[CCppAstVisitor] Treating misidentified function_definition at ${this.filepath}:${node.startPosition.row + 1} as namespace.`);
return false; // Allow recursion
⋮----
// If it's likely a real function, process it
⋮----
return false; // Allow recursion into function body
⋮----
return false; // Allow recursion into class body/members
// Add cases for struct_specifier, etc. later
⋮----
return false; // Not specifically handled, allow generic recursion
⋮----
return false; // Continue traversal even if one node fails
⋮----
private visitIncludeOrDefine(node: Parser.SyntaxNode)
⋮----
let kind: 'IncludeDirective' | 'MacroDefinition' = 'IncludeDirective'; // Default, adjust later
⋮----
name = includePath; // Use the path as the name for includes
⋮----
includePath: includePath.substring(1, includePath.length - 1), // Remove <> or ""
⋮----
kind = 'MacroDefinition'; // Placeholder kind
⋮----
const directiveNode: AstNode = { // Use base AstNode, cast later if needed
⋮----
// Add INCLUDES relationship (File -> IncludeDirective/MacroDefinition)
⋮----
private visitFunctionDefinition(node: Parser.SyntaxNode)
⋮----
const nameNode = declarator?.childForFieldName('declarator'); // Function name is often nested
⋮----
return; // Skip anonymous or malformed/misidentified
⋮----
// Determine if it's a method (inside a class) or a standalone function
⋮----
const parentId = this.currentClassEntityId; // undefined if not in a class
⋮----
// Create the base object first
⋮----
parentId: parentId, // Link method to class (undefined is fine)
// TODO: Extract parameters, return type
⋮----
// Explicitly cast based on kind before pushing
⋮----
// Add relationship File -> CFunction (DEFINES_FUNCTION) or Class -> CppMethod (HAS_METHOD)
⋮----
// Context restoration for nested functions/classes needs careful handling
// For now, we let the main visit loop handle body recursion
⋮----
private visitClassSpecifier(node: Parser.SyntaxNode)
⋮----
// Try standard name field first
⋮----
// Workaround: If nameNode is null AND the original type was function_definition,
// find the 'identifier' child that follows the 'type_identifier' child.
⋮----
return; // Skip anonymous classes or nodes we can't name
⋮----
const originalClassId = this.currentClassEntityId; // Save outer class context if nested
⋮----
// logger.debug(`[CCppAstVisitor] Found class: ${name}, EntityId: ${entityId}`);
⋮----
language: 'C++', // Explicitly set to C++ for CppClassNode
⋮----
// TODO: Handle inheritance (base_clause)
⋮----
this.currentClassEntityId = entityId; // Set context for methods/nested members
⋮----
// Add relationship File -> CppClass (DEFINES_CLASS)
⋮----
entityId: relEntityId, type: 'DEFINES_CLASS', // Reusing type
⋮----
// Let the main visit loop handle recursion into the body/member list
// Restore context AFTER visiting children (handled by main visit loop now)
// This is tricky without explicit exit events. Defer proper context stack management.
// this.currentClassEntityId = originalClassId; // Restore outer class context - DEFERRED
⋮----
// Add visitStructSpecifier etc. later
⋮----
/**
 * Parses C/C++ files using Tree-sitter.
 */
export class CCppParser
⋮----
constructor()
⋮----
/**
     * Parses a single C/C++ file.
     * @param file - FileInfo object for the C/C++ file.
     * @returns A promise resolving to the path of the temporary result file.
     */
async parseFile(file: FileInfo): Promise<string>
⋮----
this.parser.setLanguage(grammar as any); // Cast to any to bypass type conflict
⋮----
try { await fs.unlink(tempFilePath); } catch { /* ignore */ }
````

## File: src/analyzer/parsers/class-parser.ts
````typescript
import { ClassDeclaration, MethodDeclaration, PropertyDeclaration, Node, ts } from 'ts-morph';
import { AstNode, ParserContext } from '../types.js';
import { getEndColumn, getVisibility, getJsDocText } from '../../utils/ts-helpers.js'; // Assuming ts-helpers.ts will be created
import { calculateCyclomaticComplexity } from '../analysis/complexity-analyzer.js'; // Assuming complexity-analyzer.ts will be created
import { parseParameters } from './parameter-parser.js'; // Assuming parameter-parser.ts will be created
⋮----
/**
 * Parses ClassDeclarations within a source file to create Class and Method nodes
 * and HAS_METHOD relationships (Pass 1).
 * @param context - The parser context for the current file.
 */
export function parseClasses(context: ParserContext): void
⋮----
// Define a consistent qualified name for entity ID generation
⋮----
// Existing doc extraction
⋮----
// Extract JSDoc tags
⋮----
tags = lastJsDoc!.getTags().map(tag => tag.getTagName()); // Use non-null assertion
⋮----
language: 'TypeScript', // Add language property
⋮----
// memberProperties will be populated by parseClassProperties if called
⋮----
// Parse members (methods, properties)
⋮----
// parseClassProperties(declaration, classNode, context); // Optionally parse properties
⋮----
// Note: Inheritance (EXTENDS, IMPLEMENTS) is handled in Pass 2
⋮----
/**
 * Parses MethodDeclarations within a ClassDeclaration (Pass 1).
 */
function parseClassMethods(classDeclaration: ClassDeclaration, classNode: AstNode, context: ParserContext): void
⋮----
// Qualified name includes class name for uniqueness
⋮----
const complexity = calculateCyclomaticComplexity(declaration); // Calculate complexity
⋮----
language: 'TypeScript', // Add language property
⋮----
properties: { parentId: classNode.entityId }, // Store parent ID
⋮----
// Add HAS_METHOD relationship (Intra-file)
⋮----
weight: 10, // High weight for structural containment
⋮----
// Parse parameters for this method
⋮----
// Note: Body analysis (CALLS, MUTATES_STATE, etc.) is done in AstParser after all nodes are created
⋮----
// Optional: Function to parse properties if needed in Pass 1
/*
function parseClassProperties(classDeclaration: ClassDeclaration, classNode: AstNode, context: ParserContext): void {
    const { logger, now } = context;
    const properties = classDeclaration.getProperties();

    if (!classNode.memberProperties) {
        classNode.memberProperties = [];
    }

    for (const declaration of properties) {
        try {
            const name = declaration.getName() || 'anonymousProperty';
            const docs = getJsDocText(declaration);

            // Create a simple representation for the property list on the class node
            classNode.memberProperties.push({
                name,
                type: declaration.getType().getText() || 'any',
                visibility: getVisibility(declaration),
                isStatic: declaration.isStatic(),
                // isReadonly: declaration.isReadonly(), // Add if needed
                // startLine: declaration.getStartLineNumber(), // Add if needed
                // endLine: declaration.getEndLineNumber(), // Add if needed
                // documentation: docs || undefined, // Add if needed
            });

            // Optionally create separate Variable nodes for properties if needed for detailed analysis
            // const qualifiedName = `${classNode.filePath}:${classNode.name}.${name}`;
            // const entityId = generateEntityId('variable', qualifiedName); // Or 'property' kind?
            // ... create AstNode for property ...
            // addNode(propertyNode);
            // ... add HAS_PROPERTY relationship ...

        } catch (e: any) {
             logger.warn(`Error parsing property ${declaration.getName() ?? 'anonymous'} in class ${classNode.name} (${classNode.filePath})`, { message: e.message });
        }
    }
}
*/
````

## File: src/analyzer/parsers/component-parser.ts
````typescript
// src/analyzer/parsers/component-parser.ts
import { Node, SyntaxKind as SK, FunctionDeclaration, VariableDeclaration, ClassDeclaration, ArrowFunction, FunctionExpression } from 'ts-morph';
import { AstNode, ComponentNode } from '../types.js'; // Import ComponentNode
import { generateEntityId, generateInstanceId } from '../parser-utils.js';
import { createContextLogger } from '../../utils/logger.js';
⋮----
/**
 * Checks if a node represents a potential component (React/Vue/Svelte style).
 * Heuristic: Checks if it's a function/class that returns JSX or has JSX within.
 * @param node - The ts-morph node to check.
 * @returns True if the node looks like a component, false otherwise.
 */
function isPotentialComponent(node: Node): node is FunctionDeclaration | VariableDeclaration | ClassDeclaration
⋮----
// Check if name starts with uppercase (common convention)
⋮----
// Check if it explicitly returns JSX or contains JSX elements
⋮----
// For classes, check for a render method returning JSX
⋮----
// Also check if class itself contains JSX (less common but possible)
⋮----
return false; // Default if no JSX found
⋮----
// Check return type annotation if available on variable declaration
⋮----
// Check initializer body for JSX
⋮----
/**
 * Parses a potential component node (FunctionDeclaration, ClassDeclaration, or VariableDeclaration with ArrowFunction/FunctionExpression).
 * @param node - The ts-morph node representing the component.
 * @param filePath - The absolute path to the file containing the node.
 * @param instanceCounter - The counter for generating unique instance IDs.
 * @param now - The current timestamp string.
 * @returns An AstNode representing the component, or null if it's not a valid component.
 */
export function parseComponent(
    node: FunctionDeclaration | VariableDeclaration | ClassDeclaration,
    filePath: string,
    instanceCounter: { count: number },
    now: string
): ComponentNode | null
⋮----
let declarationNode: Node = node; // The node representing the core declaration for location info
⋮----
// Use initializer for location if it's a function/arrow function
⋮----
} else { // FunctionDeclaration or ClassDeclaration
⋮----
return null; // Cannot identify component without a name
⋮----
// Double-check with the heuristic if needed (might be redundant if called correctly)
⋮----
const language = filePath.endsWith('.tsx') || filePath.endsWith('.jsx') ? 'TSX' : 'TypeScript'; // Basic detection
⋮----
// Determine export status
⋮----
isDefaultExport = varStatement?.hasDefaultKeyword() ?? false; // Variable statements can have default export (e.g., export default MyComponent = ...)
⋮----
// Generate IDs
// Entity ID should be stable based on file path and component name
⋮----
properties: { // Add properties object
⋮----
// Add other relevant properties like props, state analysis results later
````

## File: src/analyzer/parsers/csharp-parser.spec.ts
````typescript
import { describe, it, expect, beforeAll } from 'vitest';
import path from 'path';
import fs from 'fs/promises';
import { CSharpParser } from './csharp-parser.js'; // Adjust path as needed
import { FileInfo } from '../../scanner/file-scanner.js'; // Adjust path as needed
import { AstNode, RelationshipInfo, SingleFileParseResult } from '../types.js'; // Adjust path as needed
import config from '../../config/index.js'; // Adjust path as needed
⋮----
// Helper to parse a fixture file and return the result
async function parseFixture(fixturePath: string): Promise<SingleFileParseResult>
⋮----
const parser = new CSharpParser(); // Create a new parser instance for each call
⋮----
// Ensure temp dir exists (parser might rely on it)
⋮----
} catch (e) { /* Ignore if exists */ }
⋮----
await fs.unlink(tempFilePath); // Clean up temp file
⋮----
// Assuming CSharpParser creates 'UsingDirective' nodes
⋮----
expect(usingNodes.length).toBe(3); // Corrected: Models, Services, Interfaces (System is implicit)
⋮----
// expect(usingNodes.find(n => n.name === 'System')).toBeDefined(); // System is implicit
⋮----
expect(usingRels.length).toBe(3); // Corrected
⋮----
// Assuming CSharpParser creates 'NamespaceDeclaration' nodes
⋮----
// Assuming CSharpParser creates 'CSharpClass' nodes
⋮----
const nsNode = result.nodes.find(n => n.kind === 'NamespaceDeclaration'); // Class is inside namespace
⋮----
expect(classRel?.sourceId).toBe(nsNode?.entityId); // Class defined within Namespace
⋮----
// Assuming CSharpParser creates 'CSharpMethod' nodes
⋮----
expect(methodNodes.length).toBe(1); // Only Main
⋮----
expect(mainMethod?.parentId).toBe(classNode?.entityId); // Check parent linkage
⋮----
it('should identify interface definition in IInventoryItem.cs', async () => { // Corrected filename and interface name
const fixturePath = path.join(fixtureDir, 'Interfaces/IInventoryItem.cs'); // Corrected filename
⋮----
// Assuming CSharpParser creates 'CSharpInterface' nodes
const interfaceNode = result.nodes.find(n => n.kind === 'CSharpInterface' && n.name === 'IInventoryItem'); // Corrected interface name
⋮----
// Assuming CSharpParser creates 'Property' nodes
⋮----
expect(propertyNodes.length).toBe(5); // Reverted expectation: Id, Name, Quantity, Price, DefaultCategory
⋮----
// Add tests for structs, enums, calls, inheritance etc.
````

## File: src/analyzer/parsers/csharp-parser.ts
````typescript
// src/analyzer/parsers/csharp-parser.ts
// @ts-ignore - Suppress type error due to potential module resolution/typing issues
import Parser from 'tree-sitter';
// @ts-ignore - Suppress type error for grammar module
import CSharp from 'tree-sitter-c-sharp';
import path from 'path';
import fs from 'fs/promises';
import { createContextLogger } from '../../utils/logger.js';
import { ParserError } from '../../utils/errors.js';
import { FileInfo } from '../../scanner/file-scanner.js';
import { AstNode, RelationshipInfo, SingleFileParseResult, InstanceCounter, NamespaceDeclarationNode, UsingDirectiveNode, CSharpClassNode, CSharpInterfaceNode, CSharpStructNode, CSharpMethodNode, PropertyNode, FieldNode } from '../types.js';
import { ensureTempDir, getTempFilePath, generateInstanceId, generateEntityId } from '../parser-utils.js';
⋮----
// Helper to get node text safely
function getNodeText(node: Parser.SyntaxNode | null | undefined): string
⋮----
// Helper to get location
function getNodeLocation(node: Parser.SyntaxNode):
⋮----
// --- Tree-sitter Visitor ---
class CSharpAstVisitor
⋮----
private currentNamespaceId: string | null = null; // Store entityId of namespace
private currentContainerId: string | null = null; // Class, Struct, Interface entityId
⋮----
constructor(private filepath: string)
⋮----
// Corrected visit method: process node, then always recurse
visit(node: Parser.SyntaxNode)
⋮----
const originalNamespaceId = this.currentNamespaceId; // Backup context
const originalContainerId = this.currentContainerId; // Backup context
⋮----
const stopRecursion = this.visitNode(node); // Process the current node first
⋮----
if (!stopRecursion) { // Only recurse if the handler didn't stop it
⋮----
// Restore context if we are exiting the node where it was set
⋮----
if (node.type === 'compilation_unit') { // Root node type for C#
⋮----
// Helper to decide if recursion should stop for certain node types
private shouldStopRecursion(node: Parser.SyntaxNode): boolean
⋮----
// Stop recursion after handling the entire import block here
return node.type === 'using_directive'; // Using directives don't have relevant children to recurse into here
⋮----
private visitNode(node: Parser.SyntaxNode): boolean { // Return boolean to indicate if recursion should stop
        try {
switch (node.type)
⋮----
return false; // Allow recursion
⋮----
return true; // Stop recursion
⋮----
return false; // Allow recursion
⋮----
return false; // Allow recursion
⋮----
return false; // Allow recursion
⋮----
return false; // Allow recursion
⋮----
return false; // Allow recursion
⋮----
return false; // Allow recursion
⋮----
return false; // Allow recursion for unhandled types
⋮----
return false; // Allow recursion even on error
⋮----
private visitNamespaceDeclaration(node: Parser.SyntaxNode)
⋮----
private visitUsingDirective(node: Parser.SyntaxNode)
⋮----
// Find the first named child that is an identifier or qualified name
⋮----
private visitContainerDeclaration(node: Parser.SyntaxNode, kind: 'CSharpClass' | 'CSharpInterface' | 'CSharpStruct')
⋮----
// TODO: Add relationships for base types
⋮----
private visitMethodDeclaration(node: Parser.SyntaxNode)
⋮----
// TODO: Extract parameters, return type, modifiers (public, static, async, etc.)
⋮----
// Relationship: Container -> HAS_METHOD -> Method
⋮----
// TODO: Visit parameters
// TODO: Visit body for calls
⋮----
private visitPropertyDeclaration(node: Parser.SyntaxNode)
⋮----
// Reverting static check for now
// const modifiersNode = node.children.find(c => c.type === 'modifiers');
// const isStatic = modifiersNode?.children.some(m => m.type === 'modifier' && m.text === 'static') ?? false;
// if (isStatic) {
//     return;
// }
⋮----
// TODO: Extract type, modifiers, getter/setter info
⋮----
// Relationship: Container -> HAS_PROPERTY -> Property
⋮----
private visitFieldDeclaration(node: Parser.SyntaxNode)
⋮----
// Reverting static check for now
// const modifiersNode = node.children.find(c => c.type === 'modifiers');
// const isStatic = modifiersNode?.children.some(m => m.type === 'modifier' && m.text === 'static') ?? false;
// if (isStatic) {
//      return;
// }
⋮----
// Field declaration can have multiple variables (e.g., public int x, y;)
const declarationNode = node.childForFieldName('declaration'); // Or similar based on grammar
⋮----
// TODO: Extract type, modifiers
⋮----
// Relationship: Container -> HAS_FIELD -> Field
⋮----
/**
 * Parses C# files using Tree-sitter.
 */
export class CSharpParser
⋮----
constructor()
⋮----
this.parser.setLanguage(CSharp as any); // Cast to any to bypass type conflict
⋮----
/**
     * Parses a single C# file.
     */
async parseFile(file: FileInfo): Promise<string>
⋮----
try { await fs.unlink(tempFilePath); } catch { /* ignore */ }
````

## File: src/analyzer/parsers/function-parser.ts
````typescript
import { FunctionDeclaration, FunctionExpression, ArrowFunction, VariableDeclaration, Node, ts } from 'ts-morph';
import { AstNode, ParserContext } from '../types.js';
import { getEndColumn, getVisibility, getJsDocText, getNodeName, getFunctionReturnType } from '../../utils/ts-helpers.js';
import { calculateCyclomaticComplexity } from '../analysis/complexity-analyzer.js';
import { parseParameters } from './parameter-parser.js';
// Assuming this exists and works
⋮----
/**
 * Parses FunctionDeclarations, FunctionExpressions, and ArrowFunctions within a source file
 * to create Function nodes (Pass 1).
 * @param context - The parser context for the current file.
 */
export function parseFunctions(context: ParserContext): void
⋮----
// Find all relevant function-like declarations/expressions
⋮----
...sourceFile.getFunctions(), // FunctionDeclarations
⋮----
// Initialize variables with defaults to satisfy definite assignment
⋮----
let isCallback = false; // Flag for callbacks
⋮----
// Handle functions assigned to variables (const myFunc = () => {})
⋮----
// Likely an IIFE or callback argument
⋮----
name = 'anonymousLambda'; // Fallback for IIFE or other cases
⋮----
// Keep isExported as false
// Keep location/docs as initialized from the function/arrow expression itself
⋮----
} else if (Node.isFunctionDeclaration(nodeToParse)) { // FunctionDeclaration
⋮----
// Keep location/docs as initialized from the declaration
⋮----
// Ensure name was assigned
⋮----
continue; // Skip this node if name couldn't be determined
⋮----
// Define a consistent qualified name
⋮----
const complexity = calculateCyclomaticComplexity(nodeToParse); // Pass the node itself
const modifiers = declaration.getModifiers?.() ?? []; // Use optional chaining for ArrowFunction which might not have getModifiers
⋮----
// Check if it's a generator (Arrow functions cannot be generators)
⋮----
// Extract JSDoc tags
⋮----
// Use the last JSDoc block before the declaration
⋮----
// Add non-null assertion to satisfy TS, although length check should guarantee it's defined
⋮----
language: 'TypeScript', // Add language property
⋮----
isGenerator: isGenerator, // Use the calculated value
⋮----
tags: tags.length > 0 ? tags : undefined, // Add tags, omit if empty
modifierFlags: modifierFlags, // Add modifier flags
properties: { isCallback }, // Keep existing custom properties
⋮----
// Parse parameters for this function
⋮----
// Note: Body analysis (CALLS, MUTATES_STATE, etc.) is done in Pass 2 (RelationshipResolver)
````

## File: src/analyzer/parsers/go-parser.spec.ts
````typescript
import { describe, it, expect, beforeAll } from 'vitest';
import path from 'path';
import fs from 'fs/promises';
import { GoParser } from './go-parser.js'; // Adjust path as needed
import { FileInfo } from '../../scanner/file-scanner.js'; // Adjust path as needed
import { AstNode, RelationshipInfo, SingleFileParseResult } from '../types.js'; // Adjust path as needed
import config from '../../config/index.js'; // Adjust path as needed
import { FileSystemError } from '../../utils/errors.js'; // Import error type
⋮----
// Helper to parse a fixture file and return the result
async function parseFixture(fixturePath: string): Promise<SingleFileParseResult>
⋮----
const parser = new GoParser(); // Create a new parser instance for each call
⋮----
// Ensure temp dir exists (parser might rely on it)
⋮----
} catch (e) { /* Ignore if exists */ }
⋮----
await fs.unlink(tempFilePath); // Clean up temp file
⋮----
const goFileName = 'main.go'; // Corrected filename
⋮----
const fixturePath = path.join(fixtureDir, goFileName); // Use variable
⋮----
expect(fileNode?.name).toBe(goFileName); // Use variable
⋮----
const fixturePath = path.join(fixtureDir, goFileName); // Use variable
⋮----
const fixturePath = path.join(fixtureDir, goFileName); // Use variable
⋮----
expect(importNodes.length).toBe(6); // Corrected expectation
⋮----
expect(importRels.length).toBe(6); // Corrected expectation
⋮----
const fixturePath = path.join(fixtureDir, goFileName); // Use variable
⋮----
expect(funcNodes.length).toBe(2); // Corrected expectation: main, init
⋮----
expect(mainFunc?.startLine).toBe(17); // Corrected line
⋮----
expect(initFunc?.startLine).toBe(72); // Corrected line
⋮----
// Check relationship File -> DEFINES_FUNCTION -> Function
⋮----
// Add tests for structs, methods (if any), calls etc.
````

## File: src/analyzer/parsers/go-parser.ts
````typescript
// src/analyzer/parsers/go-parser.ts
// @ts-ignore - Suppress type error due to potential module resolution/typing issues
import Parser from 'tree-sitter';
// @ts-ignore - Suppress type error for grammar module
import Go from 'tree-sitter-go';
import path from 'path';
import fs from 'fs/promises';
import { createContextLogger } from '../../utils/logger.js';
import { ParserError } from '../../utils/errors.js';
import { FileInfo } from '../../scanner/file-scanner.js';
import { AstNode, RelationshipInfo, SingleFileParseResult, InstanceCounter, PackageClauseNode, ImportSpecNode, GoFunctionNode, GoMethodNode, GoStructNode, GoInterfaceNode } from '../types.js';
import { ensureTempDir, getTempFilePath, generateInstanceId, generateEntityId } from '../parser-utils.js';
⋮----
// Helper to get node text safely
function getNodeText(node: Parser.SyntaxNode | null | undefined): string
⋮----
// Helper to get location
function getNodeLocation(node: Parser.SyntaxNode):
⋮----
// --- Tree-sitter Visitor ---
class GoAstVisitor
⋮----
private currentReceiverType: string | null = null; // For methods
⋮----
constructor(private filepath: string)
⋮----
// Corrected visit method: process node, then always recurse unless stopped
visit(node: Parser.SyntaxNode)
⋮----
const stopRecursion = this.visitNode(node); // Process the current node first
⋮----
if (!stopRecursion) { // Only recurse if the handler didn't stop it
⋮----
if (node.type === 'source_file') { // Root node type for Go
⋮----
// Helper to decide if recursion should stop for certain node types
private shouldStopRecursion(node: Parser.SyntaxNode): boolean
⋮----
// Stop recursion after handling the entire import block here
⋮----
private visitNode(node: Parser.SyntaxNode): boolean
⋮----
return true; // Stop recursion for imports here
// case 'import_spec': // Removed - handled by visitImportDeclaration
//     break;
⋮----
case 'type_spec': // Handle type specs (like structs) which might not be definitions
⋮----
// Removed var_declaration handling for now
// case 'short_var_declaration':
// case 'var_declaration':
//     this.visitVarDeclaration(node);
//     return false;
⋮----
return false; // Allow recursion for unhandled types
⋮----
return false; // Allow recursion even on error
⋮----
private visitPackageClause(node: Parser.SyntaxNode)
⋮----
// Visit the import declaration block (e.g., import "fmt" or import (...))
private visitImportDeclaration(node: Parser.SyntaxNode)
⋮----
// Find all import_spec nodes within this declaration
⋮----
private visitImportSpec(node: Parser.SyntaxNode)
⋮----
// This method is now only called by visitImportDeclaration
⋮----
const importPath = getNodeText(pathNode).replace(/"/g, ''); // Remove quotes
const aliasNode = node.childForFieldName('name'); // Alias comes before path in Go grammar
⋮----
// Relationship: File -> GO_IMPORTS -> ImportSpec
⋮----
sourceId: this.fileNode.entityId, targetId: entityId, // Target is the import spec node for now
⋮----
private visitFunctionDeclaration(node: Parser.SyntaxNode)
⋮----
// TODO: Visit body for calls
⋮----
private visitMethodDeclaration(node: Parser.SyntaxNode)
⋮----
// Try to find the receiver type (simplistic)
⋮----
const receiverEntityId = generateEntityId('gostruct', receiverQualifiedName); // Assume receiver is a struct for now
⋮----
const qualifiedName = `${receiverTypeName}.${name}`; // Method name qualified by receiver type
⋮----
parentId: receiverEntityId, // Link to the receiver struct/type
⋮----
// TODO: Extract parameters, return type
⋮----
// Relationship: Struct -> HAS_METHOD -> Method
⋮----
entityId: relEntityId, type: 'HAS_METHOD', // Reusing HAS_METHOD
⋮----
// TODO: Visit parameters
// TODO: Visit body for calls
⋮----
private visitTypeDefinition(node: Parser.SyntaxNode)
⋮----
// --- TEMPORARY DEBUG LOG ---
⋮----
// --- END TEMPORARY DEBUG LOG ---
⋮----
// Ensure qualified name includes package, consistent with method receiver lookup
⋮----
let kind: 'GoStruct' | 'GoInterface' | 'TypeAlias' = 'TypeAlias'; // Default
⋮----
// Use the package-qualified name for entity ID generation
⋮----
// TODO: Extract fields for structs/methods for interfaces if not handled by recursion
⋮----
// Add relationship File -> DEFINES_STRUCT/DEFINES_INTERFACE -> GoStruct/GoInterface
⋮----
// TODO: Add relationship File -> DEFINES_STRUCT/DEFINES_INTERFACE -> GoStruct/GoInterface
⋮----
// Removed visitVarDeclaration as it wasn't correctly identifying function literals in this fixture
⋮----
// Helper to create GoFunctionNode (used by func declaration and func literal assignment)
private createGoFunctionNode(name: string, node: Parser.SyntaxNode, location:
⋮----
// Use the location of the name identifier, but potentially the end line of the whole node (func literal or declaration)
⋮----
startLine: location.startLine, endLine: endLine, // Use calculated end line
startColumn: location.startColumn, endColumn: location.endColumn, // Use name location end column for now
⋮----
// TODO: Extract parameters, return type from node or its children
⋮----
// Add relationship File -> DEFINES_FUNCTION -> GoFunction
⋮----
/**
 * Parses Go files using Tree-sitter.
 */
export class GoParser
⋮----
constructor()
⋮----
this.parser.setLanguage(Go as any); // Cast to any to bypass type conflict
⋮----
/**
     * Parses a single Go file.
     */
async parseFile(file: FileInfo): Promise<string>
⋮----
try { // Restore try...catch
⋮----
try { await fs.unlink(tempFilePath); } catch { /* ignore */ }
````

## File: src/analyzer/parsers/import-parser.ts
````typescript
// src/analyzer/parsers/import-parser.ts
import { Node, SyntaxKind } from 'ts-morph';
import { ParserContext, AstNode, RelationshipInfo } from '../types.js';
import { getJsDocDescription } from '../../utils/ts-helpers.js'; // Assuming this helper exists
⋮----
/**
 * Parses import declarations in a TypeScript source file.
 * Creates Import nodes and File->IMPORTS->Import relationships.
 */
export function parseImports(context: ParserContext): void
⋮----
// Create a unique name/identifier for the import node itself
// Using module specifier and line number for uniqueness within the file
⋮----
const entityId = generateEntityId('import', qualifiedName); // Use 'import' kind
⋮----
// Extract named imports, default import, namespace import
⋮----
const importNode: AstNode = { // Consider creating a specific ImportNode type if more props needed
⋮----
name: importName, // Use combined name
⋮----
language: 'TypeScript', // Or TSX based on fileNode?
⋮----
endColumn: declaration.getEnd() - declaration.getStartLinePos(), // Adjust if needed
⋮----
documentation: getJsDocDescription(declaration), // Get JSDoc if available
⋮----
// Create relationship: File IMPORTS ImportNode
⋮----
weight: 1, // Adjust weight as needed
⋮----
// logger.debug(`Added Import node for "${moduleSpecifier}" and IMPORTS relationship from ${fileNode.name}`);
````

## File: src/analyzer/parsers/interface-parser.ts
````typescript
import { InterfaceDeclaration, MethodSignature, PropertySignature, Node, ts } from 'ts-morph';
import { AstNode, ParserContext } from '../types.js';
import { getEndColumn, getVisibility, getJsDocText, getFunctionReturnType } from '../../utils/ts-helpers.js';
// Assuming complexity calculation isn't typically done for interface methods
// import { calculateCyclomaticComplexity } from '../analysis/complexity-analyzer.js';
import { parseParameters } from './parameter-parser.js'; // For method parameters
⋮----
/**
 * Parses InterfaceDeclarations within a source file to create Interface and Method nodes
 * and HAS_METHOD relationships (Pass 1).
 * @param context - The parser context for the current file.
 */
export function parseInterfaces(context: ParserContext): void
⋮----
language: 'TypeScript', // Add language property
⋮----
// memberProperties will be populated if parseInterfaceProperties is called
⋮----
// Parse members (method signatures, property signatures)
⋮----
// parseInterfaceProperties(declaration, interfaceNode, context); // Optional
⋮----
// Note: Inheritance (EXTENDS) is handled in Pass 2
⋮----
/**
 * Parses MethodSignatures within an InterfaceDeclaration (Pass 1).
 * Creates Method nodes (representing the signature) and HAS_METHOD relationships.
 */
function parseInterfaceMethods(interfaceDeclaration: InterfaceDeclaration, interfaceNode: AstNode, context: ParserContext): void
⋮----
const methods = interfaceDeclaration.getMethods(); // Gets MethodSignatures
⋮----
for (const signature of methods) { // signature is MethodSignature
⋮----
// Qualified name includes interface name
⋮----
// Treat MethodSignature as a Method node for graph consistency
⋮----
const returnType = getFunctionReturnType(signature); // Use helper
⋮----
id: generateId('method', qualifiedName), // Use 'method' prefix
⋮----
filePath: interfaceNode.filePath, // Belongs to the interface's file
language: 'TypeScript', // Add language property
⋮----
// Complexity doesn't apply to signatures
⋮----
// Visibility/Static/Async don't apply to interface methods
⋮----
properties: { parentId: interfaceNode.entityId, isSignature: true }, // Mark as signature, link parent
⋮----
// Add HAS_METHOD relationship (Interface -> Method)
⋮----
// Parse parameters for this method signature
⋮----
// Optional: Function to parse PropertySignatures if needed
/*
function parseInterfaceProperties(interfaceDeclaration: InterfaceDeclaration, interfaceNode: AstNode, context: ParserContext): void {
    const { logger, now } = context;
    const properties = interfaceDeclaration.getProperties(); // Gets PropertySignatures

    if (!interfaceNode.memberProperties) {
        interfaceNode.memberProperties = [];
    }

    for (const signature of properties) { // signature is PropertySignature
        try {
            const name = signature.getName() || 'anonymousPropSig';
            const docs = getJsDocText(signature);

            interfaceNode.memberProperties.push({
                name,
                type: signature.getType().getText() || 'any',
                // visibility: undefined, // Not applicable
                // isStatic: undefined, // Not applicable
                // isReadonly: signature.isReadonly(), // Add if needed
            });

            // Optionally create separate Variable nodes for properties if needed
            // const qualifiedName = `${interfaceNode.filePath}:${interfaceNode.name}.${name}`;
            // const entityId = generateEntityId('variable', qualifiedName); // Or 'property'?
            // ... create AstNode ...
            // addNode(propertyNode);
            // ... add HAS_PROPERTY relationship ...

        } catch (e: any) {
            logger.warn(`Error parsing property signature ${signature.getName() ?? 'anonymous'} in interface ${interfaceNode.name} (${interfaceNode.filePath})`, { message: e.message });
        }
    }
}
*/
````

## File: src/analyzer/parsers/java-parser.spec.ts
````typescript
import { describe, it, expect, beforeAll } from 'vitest';
import path from 'path';
import fs from 'fs/promises';
import { JavaParser } from './java-parser.js'; // Adjust path as needed
import { FileInfo } from '../../scanner/file-scanner.js'; // Adjust path as needed
import { AstNode, RelationshipInfo, SingleFileParseResult } from '../types.js'; // Adjust path as needed
import config from '../../config/index.js'; // Adjust path as needed
import { FileSystemError } from '../../utils/errors.js'; // Import error type
⋮----
// Helper to parse a fixture file and return the result
async function parseFixture(fixturePath: string): Promise<SingleFileParseResult>
⋮----
const parser = new JavaParser(); // Create a new parser instance for each call
⋮----
// Ensure temp dir exists (parser might rely on it)
⋮----
} catch (e) { /* Ignore if exists */ }
⋮----
await fs.unlink(tempFilePath); // Clean up temp file
⋮----
// Removed debug log
⋮----
expect(methodNodes.length).toBe(7); // Corrected expectation: Constructor, registerOp, performOp, getAvailable, store, recall, clear
⋮----
// Check a specific method like performOperation
⋮----
expect(performOpMethod?.parentId).toBe(classNode?.entityId); // Check parent linkage
⋮----
const constructorMethod = methodNodes.find(n => n.name === 'Calculator'); // Constructor name matches class name
⋮----
// Check for 'memory' field instead of 'history'
⋮----
expect(importNodes.length).toBe(3); // Corrected expectation: InputMismatchException, Scanner, Set
⋮----
it('should identify interface definition in Operation.java', async () => { // Corrected test description
// Corrected path to include 'operations' subdirectory
⋮----
// Corrected kind to 'JavaInterface'
⋮----
// Corrected relationship type
⋮----
expect(interfaceNode?.startLine).toBe(6); // Corrected line
⋮----
// Add more tests for calls, inheritance, interfaces etc.
````

## File: src/analyzer/parsers/java-parser.ts
````typescript
// src/analyzer/parsers/java-parser.ts
// @ts-ignore - Suppress type error due to potential module resolution/typing issues
import Parser from 'tree-sitter';
// @ts-ignore - Suppress type error for grammar module
import Java from 'tree-sitter-java';
import path from 'path';
import fs from 'fs/promises';
import { createContextLogger } from '../../utils/logger.js';
import { ParserError } from '../../utils/errors.js';
import { FileInfo } from '../../scanner/file-scanner.js';
import { AstNode, RelationshipInfo, SingleFileParseResult, InstanceCounter, PackageDeclarationNode, ImportDeclarationNode, JavaClassNode, JavaInterfaceNode, JavaMethodNode, JavaFieldNode, JavaEnumNode } from '../types.js'; // Added JavaEnumNode
import { ensureTempDir, getTempFilePath, generateInstanceId, generateEntityId } from '../parser-utils.js';
⋮----
// Helper to get node text safely
function getNodeText(node: Parser.SyntaxNode | null | undefined): string
⋮----
// Helper to get location
function getNodeLocation(node: Parser.SyntaxNode):
⋮----
// --- Tree-sitter Visitor ---
class JavaAstVisitor
⋮----
private currentClassOrInterfaceId: string | null = null; // Store entityId
⋮----
constructor(private filepath: string)
⋮----
visit(node: Parser.SyntaxNode)
⋮----
// Process the current node first
this.visitNode(node); // Always process the node
⋮----
// Always recurse into children
⋮----
if (node.type === 'program') { // Root node type for Java
⋮----
private visitNode(node: Parser.SyntaxNode)
⋮----
case 'constructor_declaration': // Handle constructors explicitly
⋮----
// No need to explicitly handle body nodes here, main visit loop handles recursion
⋮----
private visitPackageDeclaration(node: Parser.SyntaxNode)
⋮----
const packageName = getNodeText(node.namedChild(0)); // Assuming name is the first named child
⋮----
// Relationship: File -> DECLARES_PACKAGE -> PackageDeclaration
⋮----
private visitImportDeclaration(node: Parser.SyntaxNode)
⋮----
const importPath = getNodeText(node.namedChild(0)); // Assuming path is first named child
const onDemand = getNodeText(node).endsWith('.*'); // Simple check for wildcard
⋮----
// Relationship: File -> JAVA_IMPORTS -> ImportDeclaration
// Target resolution happens in Pass 2
⋮----
sourceId: this.fileNode.entityId, targetId: entityId, // Target is the import node itself for now
⋮----
private visitClassOrInterfaceDeclaration(node: Parser.SyntaxNode, kind: 'JavaClass' | 'JavaInterface')
⋮----
const originalClassOrInterfaceId = this.currentClassOrInterfaceId; // Backup context
⋮----
const entityId = generateEntityId(kind.toLowerCase(), qualifiedName); // Use qualified name for entity ID
⋮----
const classNode: AstNode = { // Use base AstNode, specific type depends on kind
⋮----
// TODO: Add extends/implements info to properties
⋮----
this.currentClassOrInterfaceId = entityId; // Set context for methods/fields
⋮----
// Relationship: File -> DEFINES_CLASS/DEFINES_INTERFACE -> Class/Interface
⋮----
// TODO: Add relationships for extends/implements based on 'superclass'/'interfaces' fields
⋮----
// Let main visit loop handle recursion into body
// const bodyNode = node.childForFieldName('body');
// if (bodyNode) {
//     this.visit(bodyNode); // Recurse into the body
// }
⋮----
// Restore context AFTER visiting children (handled by main visit loop finishing siblings)
// this.currentClassOrInterfaceId = originalClassOrInterfaceId; // Defer restoration
⋮----
private visitMethodDeclaration(node: Parser.SyntaxNode)
⋮----
if (!this.currentClassOrInterfaceId) return; // Only process methods within a class/interface context
⋮----
// Use 'name' field which works for regular methods
⋮----
const methodEntityId = generateEntityId('javamethod', `${this.currentClassOrInterfaceId}.${name}`); // ID relative to parent
⋮----
// TODO: Extract parameters, return type, modifiers
⋮----
// Relationship: Class/Interface -> HAS_METHOD -> Method
⋮----
// TODO: Visit parameters within the method signature
// TODO: Visit method body for calls
⋮----
// Separate visitor for constructors
private visitConstructorDeclaration(node: Parser.SyntaxNode)
⋮----
const nameNode = node.childForFieldName('name'); // Constructor name is in 'name' field
⋮----
// Verify name matches the current class context
⋮----
return; // Likely a parsing error or unexpected structure
⋮----
const methodEntityId = generateEntityId('javamethod', `${this.currentClassOrInterfaceId}.${name}`); // Use same kind for simplicity
⋮----
entityId: methodEntityId, kind: 'JavaMethod', name: name, // Treat as a method
⋮----
properties: { isConstructor: true } // Add property to distinguish
// TODO: Extract parameters, modifiers
⋮----
// Relationship: Class -> HAS_METHOD -> Constructor
⋮----
// TODO: Visit parameters
// TODO: Visit body
⋮----
private visitFieldDeclaration(node: Parser.SyntaxNode)
⋮----
if (!this.currentClassOrInterfaceId) return; // Only process fields within a class/interface context
⋮----
// Field declaration can have multiple variables (e.g., int x, y;)
// The structure is typically: modifiers type declarator(s);
⋮----
const nameNode = declarator.childForFieldName('name'); // Tree-sitter Java uses 'name'
⋮----
id: generateInstanceId(this.instanceCounter, 'javafield', name, { line: location.startLine, column: location.startColumn }), // Use declarator location?
⋮----
filePath: this.filepath, language: 'Java', ...getNodeLocation(declarator), createdAt: this.now, // Use declarator location
⋮----
// TODO: Extract type, modifiers from parent 'field_declaration' node
⋮----
// Relationship: Class/Interface -> HAS_FIELD -> Field
⋮----
private visitEnumDeclaration(node: Parser.SyntaxNode)
⋮----
// TODO: Extract enum constants from body
⋮----
// Relationship: File -> DEFINES_ENUM -> Enum
⋮----
// Let main visit loop handle recursion into body
// const bodyNode = node.childForFieldName('body');
// if (bodyNode) {
//     this.visit(bodyNode);
// }
⋮----
/**
 * Parses Java files using Tree-sitter.
 */
export class JavaParser
⋮----
constructor()
⋮----
this.parser.setLanguage(Java as any); // Cast to any to bypass type conflict
⋮----
/**
     * Parses a single Java file.
     */
async parseFile(file: FileInfo): Promise<string>
⋮----
try { await fs.unlink(tempFilePath); } catch { /* ignore */ }
````

## File: src/analyzer/parsers/jsx-parser.ts
````typescript
// src/analyzer/parsers/jsx-parser.ts
import {
    SyntaxKind, Node, JsxElement, JsxSelfClosingElement, JsxAttribute, StringLiteral,
    JsxExpression, Identifier, Block
} from 'ts-morph';
import { ts } from 'ts-morph';
import { createContextLogger } from '../../utils/logger.js';
import { ParserContext, JSXElementNode, JSXAttributeNode, ComponentNode, TailwindClassNode } from '../types.js';
⋮----
/**
 * Parses JSX elements and attributes within a source file.
 * Creates JSXElement and JSXAttribute nodes, and RENDERS_ELEMENT / HAS_PROP relationships.
 * Assumes Component nodes have already been created by component-parser.
 */
export function parseJsx(context: ParserContext): void
⋮----
// This case should theoretically not be reached.
⋮----
language: 'TypeScript', // Assuming TS/JS context for JSX
⋮----
tagName: tagName, // Add the missing tagName
⋮----
// --- Create RENDERS_ELEMENT Relationship ---
⋮----
n.startLine === currentParent!.getStartLineNumber() && // Non-null assertion ok due to while condition
⋮----
startLine: parentJsxNode.getStartLineNumber(), // Use typed parentJsxNode
⋮----
// Get parent for next iteration safely
// @ts-ignore - TS control flow analysis seems confused here, but loop condition ensures currentParent is defined.
⋮----
currentParent = nextParent; // Assign potentially undefined value
⋮----
// --- Create HAS_PROP Relationships ---
⋮----
parentId: jsxElementNode.entityId, // Link to parent JSX element
⋮----
language: 'TypeScript', // Assuming TS/JS context
⋮----
// --- Tailwind CSS Class Parsing ---
⋮----
// Explicitly type as TailwindClassNode
⋮----
parentId: jsxElementNode.entityId, // Link to the element using the class
⋮----
filePath: fileNode.filePath, // File where the class usage occurs
language: 'TypeScript', // Assuming TS/JS context
// Start/end lines for a class itself aren't really applicable here
⋮----
properties: { className: tailwindClassName } // Store the class name
⋮----
// Ensure tailwindNode exists before creating relationship
⋮----
// Now tailwindNode is guaranteed to be defined here
⋮----
// Use tailwindEntityId which is always defined
⋮----
// And here
⋮----
// This case should not happen if cache logic is correct, but log just in case
````

## File: src/analyzer/parsers/parameter-parser.ts
````typescript
import { FunctionDeclaration, MethodDeclaration, ArrowFunction, FunctionExpression, ParameterDeclaration, Node, MethodSignature } from 'ts-morph';
import { AstNode, ParserContext } from '../types.js';
import { getEndColumn, getNodeType, getJsDocDescription } from '../../utils/ts-helpers.js';
⋮----
/**
 * Parses parameters of a function or method declaration.
 * Creates Parameter nodes and HAS_PARAMETER relationships.
 * @param declarationNode - The ts-morph node for the function/method.
 * @param parentNode - The AstNode for the owning function/method.
 * @param context - The parser context.
 */
export function parseParameters(
    declarationNode: FunctionDeclaration | MethodDeclaration | ArrowFunction | FunctionExpression | MethodSignature,
    parentNode: AstNode, // The AstNode of the function/method owning the parameters
    context: ParserContext
): void
⋮----
parentNode: AstNode, // The AstNode of the function/method owning the parameters
⋮----
// Entity ID needs context from the parent function/method
const qualifiedName = `${parentNode.entityId}:${name}`; // Use parent entityId for context
⋮----
const type = getNodeType(param); // Use helper
const docs = getJsDocDescription(param); // Use helper
⋮----
language: 'TypeScript', // Add language property
⋮----
properties: { parentId: parentNode.entityId }, // Link back to parent function/method
⋮----
// Avoid adding duplicate nodes if analysis runs multiple times (though less likely with new structure)
⋮----
// Add HAS_PARAMETER relationship (Function/Method -> Parameter)
⋮----
weight: 8, // Parameters are important parts of a function signature
````

## File: src/analyzer/parsers/sql-parser.ts
````typescript
// src/analyzer/parsers/sql-parser.ts
import Parser from 'tree-sitter';
// Try named import for the language object, ignore missing types
// @ts-ignore
import { language as SQL } from 'tree-sitter-sql';
import path from 'path';
import fs from 'fs/promises';
import { createContextLogger } from '../../utils/logger.js';
import { ParserError } from '../../utils/errors.js';
import { FileInfo } from '../../scanner/file-scanner.js';
import { AstNode, RelationshipInfo, SingleFileParseResult, InstanceCounter, SQLTableNode, SQLColumnNode, SQLViewNode, SQLStatementNode } from '../types.js';
import { ensureTempDir, getTempFilePath, generateInstanceId, generateEntityId } from '../parser-utils.js';
⋮----
// Helper to get node text safely
function getNodeText(node: Parser.SyntaxNode | null | undefined): string
⋮----
// Helper to get location
function getNodeLocation(node: Parser.SyntaxNode):
⋮----
// --- Tree-sitter Visitor ---
class SqlAstVisitor
⋮----
private currentSchema: string | null = null; // Track current schema context if applicable
⋮----
constructor(private filepath: string)
⋮----
visit(node: Parser.SyntaxNode)
⋮----
// Selectively recurse
⋮----
if (node.type === 'source_file') { // Assuming root is source_file for tree-sitter-sql
⋮----
private visitNode(node: Parser.SyntaxNode)
⋮----
// DML Statements (Capture basic info)
⋮----
// Potentially add CREATE SCHEMA, CREATE FUNCTION, CREATE PROCEDURE later
⋮----
private visitCreateTable(node: Parser.SyntaxNode)
⋮----
const nameNode = node.childForFieldName('name'); // Adjust field name based on grammar
⋮----
// Basic schema handling - assumes schema.table format if present
⋮----
if (!simpleTableName) return; // Add check for undefined simple name
⋮----
// Relationship: File -> DEFINES_TABLE -> SQLTable
⋮----
// Visit columns within the table definition
const columnDefs = node.descendantsOfType('column_definition'); // Adjust type based on grammar
⋮----
this.visitColumnDefinition(colDef, entityId); // Pass table entityId as parentId
⋮----
private visitColumnDefinition(node: Parser.SyntaxNode, parentTableId: string)
⋮----
const nameNode = node.childForFieldName('name'); // Adjust field name
const typeNode = node.childForFieldName('type'); // Adjust field name
⋮----
// Relationship: SQLTable -> HAS_COLUMN -> SQLColumn
⋮----
private visitCreateView(node: Parser.SyntaxNode)
⋮----
const nameNode = node.childForFieldName('name'); // Adjust field name
⋮----
if (!simpleViewName) return; // Add check for undefined simple name
⋮----
properties: { qualifiedName, schema: schemaName, queryText: getNodeText(node.childForFieldName('query')) } // Store query text
⋮----
// Relationship: File -> DEFINES_VIEW -> SQLView
⋮----
// Pass 2 will analyze queryText to create REFERENCES_TABLE/VIEW relationships
⋮----
private visitDMLStatement(node: Parser.SyntaxNode)
⋮----
let kind: SQLStatementNode['kind'] = 'SQLSelectStatement'; // Default
⋮----
const name = `${kind}_${location.startLine}`; // Simple name based on type and line
⋮----
properties: { queryText: statementText } // Store full query text
⋮----
// Pass 2 will analyze queryText to create REFERENCES_TABLE/VIEW relationships
⋮----
/**
 * Parses SQL files using Tree-sitter.
 */
export class SqlParser
⋮----
constructor()
⋮----
// Use the named import 'language' aliased as SQL
if (!SQL || typeof (SQL as any).parse !== 'function') { // Check if the imported object is valid (using 'as any' due to missing types)
⋮----
this.parser.setLanguage(SQL as any); // Pass the imported language object, cast to any
⋮----
// Rethrow or handle appropriately - maybe disable SQL parsing
⋮----
/**
     * Parses a single SQL file.
     */
async parseFile(file: FileInfo): Promise<string>
⋮----
try { await fs.unlink(tempFilePath); } catch { /* ignore */ }
````

## File: src/analyzer/parsers/type-alias-parser.ts
````typescript
import { TypeAliasDeclaration, EnumDeclaration, Node, ts } from 'ts-morph';
import { AstNode, ParserContext } from '../types.js';
import { getEndColumn, getJsDocText, getNodeName } from '../../utils/ts-helpers.js';
⋮----
/**
 * Parses TypeAliasDeclarations and EnumDeclarations within a source file
 * to create TypeAlias nodes (Pass 1).
 * @param context - The parser context for the current file.
 */
export function parseTypeAliases(context: ParserContext): void
⋮----
// Parse Type Aliases
⋮----
const entityId = generateEntityId('typealias', qualifiedName); // Use lowercase 'typealias'
⋮----
const typeText = declaration.getTypeNode()?.getText() || 'unknown'; // Get the actual type definition
⋮----
language: 'TypeScript', // Add language property
⋮----
type: typeText, // Store the type definition text
⋮----
// Parse Enums (Treating them as a form of TypeAlias for simplicity in the graph)
⋮----
const entityId = generateEntityId('typealias', qualifiedName); // Use 'typealias' kind
⋮----
// Could store enum members in properties if needed
// const members = declaration.getMembers().map(m => ({ name: m.getName(), value: m.getValue() }));
⋮----
id: generateId('typealias', qualifiedName), // Use 'typealias' prefix
⋮----
filePath: fileNode.filePath, // Use 'TypeAlias' kind
language: 'TypeScript', // Add language property
⋮----
properties: { isEnum: true }, // Add a flag to distinguish enums
````

## File: src/analyzer/parsers/variable-parser.ts
````typescript
import { VariableStatement, VariableDeclaration, Node, ts, VariableDeclarationKind } from 'ts-morph'; // Import VariableDeclarationKind
import { AstNode, ParserContext } from '../types.js';
import { getEndColumn, getNodeType, getJsDocText, getNodeName } from '../../utils/ts-helpers.js';
⋮----
/**
 * Parses VariableDeclarations within a source file to create Variable nodes (Pass 1).
 * Skips variables that initialize functions, as those are handled by function-parser.
 * @param context - The parser context for the current file.
 */
export function parseVariables(context: ParserContext): void
⋮----
// Get VariableStatements first, as they contain export status and docs
⋮----
// Get docs from the statement, as it often precedes the declaration list
⋮----
// Skip if the variable is initializing a function (handled by function-parser)
⋮----
continue; // Skip function variables
⋮----
// Qualified name includes file path
⋮----
// Add line number for potentially non-unique variable names within a file
⋮----
// Use unique name for ID
⋮----
// Use imported enum
⋮----
// Add 'const', 'let', or 'var' to modifier flags for clarity
⋮----
// Use imported enum
⋮----
// Use imported enum
else modifierFlags.push('var'); // Assume var if not const or let
⋮----
language: 'TypeScript', // Add language property
⋮----
endLine: declaration.getEndLineNumber(), // Often same as start for simple vars
⋮----
documentation: docs || undefined, // Use docs from statement
⋮----
isExported: isExported, // Use export status from statement
⋮----
// Note: Relationships involving variables (MUTATES_STATE, potentially READS_VARIABLE)
// are typically handled during body analysis in Pass 1 (AstParser) or Pass 2.
````

## File: src/analyzer/resolvers/c-cpp-resolver.ts
````typescript
// src/analyzer/resolvers/c-cpp-resolver.ts
import { SourceFile } from 'ts-morph'; // Keep for consistency, though not used directly for C++ AST
import { AstNode, RelationshipInfo, ResolverContext, IncludeDirectiveNode } from '../types.js';
import { generateEntityId, generateInstanceId } from '../parser-utils.js';
⋮----
/**
 * Resolves INCLUDES relationships for C/C++ files.
 * Note: Actual path resolution for includes is complex and not fully implemented here.
 * This creates relationships based on the path string found.
 */
export function resolveCIncludes(sourceFile: SourceFile, fileNode: AstNode, context: ResolverContext): void
⋮----
// Only process C/C++ files (double check, though called conditionally)
⋮----
// Find IncludeDirective nodes created in Pass 1 for this file
⋮----
) as IncludeDirectiveNode[]; // Type assertion
⋮----
// --- Basic Path Resolution Placeholder ---
// TODO: Implement proper C/C++ include path resolution logic (search paths, etc.)
// For now, we'll just create a placeholder target entity ID based on the path string.
// We won't try to find the actual file node in the index yet.
const targetFileEntityId = generateEntityId('file', includePath); // Placeholder based on path string
const isPlaceholder = true; // Mark as placeholder until resolution is implemented
// --- End Placeholder ---
⋮----
sourceId: fileNode.entityId, // Source is the file containing the #include
targetId: targetFileEntityId, // Target is the (placeholder) included file
⋮----
// Add other C/C++ specific resolution functions here later (e.g., resolveCalls)
````

## File: src/analyzer/resolvers/ts-resolver.ts
````typescript
// src/analyzer/resolvers/ts-resolver.ts
import { SourceFile, Node, SyntaxKind as SK, BinaryExpression, ClassDeclaration, InterfaceDeclaration, CallExpression, TryStatement, JsxElement, JsxSelfClosingElement, ImportDeclaration, NamedImports } from 'ts-morph'; // Corrected NamedImports
import { AstNode, RelationshipInfo, ResolverContext, ComponentNode } from '../types.js'; // Corrected import path
import { getTargetDeclarationInfo } from '../analysis/analyzer-utils.js';
import { generateEntityId } from '../parser-utils.js'; // Only need generateEntityId here potentially
import winston from 'winston'; // Import Logger type
⋮----
// Helper function moved from relationship-resolver.ts
function isInsideConditionalContext(node: Node, boundaryNode: Node): boolean
⋮----
// Helper function moved and adapted from relationship-resolver.ts
// Corrected to handle simple absolute-like paths used in tests
function findNodeByFilePath(filePath: string, context: ResolverContext): AstNode | undefined
⋮----
// Use the normalized path directly if it looks like a simple absolute path (for tests)
// Otherwise, assume it needs full resolution for generateEntityId
⋮----
// Also check for PythonModule kind if the path matches
⋮----
/**
 * Resolves IMPORTS and EXPORTS relationships for a TS/JS file.
 * Also adds RESOLVES_IMPORT relationships between ImportDeclaration nodes and their targets.
 */
export function resolveTsModules(sourceFile: SourceFile, fileNode: AstNode, context: ResolverContext): void
⋮----
// --- Imports ---
⋮----
// Use ts-morph's resolution which should handle in-memory paths correctly
⋮----
const resolvedImportPath = resolvedSourceFile?.getFilePath() ?? resolveImportPath(fileNode.filePath, moduleSpecifier); // Fallback if ts-morph fails
⋮----
let targetFileNode = findNodeByFilePath(resolvedImportPath, context); // Use corrected helper
⋮----
// Use the resolved path directly for placeholder generation
⋮----
const namedImports = impDecl.getNamedImports(); // Keep original ts-morph nodes
⋮----
// 1. Create IMPORTS relationship (File -> File)
⋮----
// 2. Create RESOLVES_IMPORT relationship (ImportDeclaration Node -> Target Node)
// Find the corresponding ImportDeclaration AstNode from Pass 1
⋮----
// Use generateEntityId consistent with how it was created in the test
// Use 'import' kind to match the kind used in import-parser.ts
⋮----
continue; // Skip RESOLVES_IMPORT if we can't find the source node
⋮----
if (targetFileNode) { // Only resolve specific symbols if target file exists in index
// Resolve named imports
for (const namedImport of namedImports) { // Iterate original ts-morph nodes
⋮----
// const importLine = namedImport.getNameNode().getStartLineNumber(); // Line number not needed/reliable for target lookup
⋮----
// Find the exported node in the target file
⋮----
// Try finding function first using the simplified ID format
⋮----
// If not found as function, try other common exportable kinds
⋮----
// Try variable (also likely without line number for lookup)
⋮----
// Add more kinds if necessary (enum, typealias)
⋮----
// Resolve default import
⋮----
// Cast n to AstNode
⋮----
(n as AstNode).properties?.isDefaultExport === true // Find the default export
) as AstNode | undefined; // Add type assertion
⋮----
if (targetNode) { // Check if targetNode is found
⋮----
// Resolve namespace import (links to the target file node)
⋮----
sourceId: importAstNode.entityId, targetId: targetFileNode.entityId, // Namespace import resolves to the file/module itself
⋮----
// --- Exports --- (Keep existing logic, might need refinement later)
⋮----
if (moduleSpecifier) { // Re-export
⋮----
const targetFileNode = findNodeByFilePath(resolvedExportPath, context); // Use helper
⋮----
} else { // Export local names
⋮----
// Direct exports are handled within the main RelationshipResolver loop for now, as it iterates all nodes.
// Could be moved here if needed, but requires passing the full nodeIndex or iterating it again.
⋮----
/**
 * Resolves EXTENDS and IMPLEMENTS relationships for TS/JS.
 */
export function resolveTsInheritance(sourceFile: SourceFile, fileNode: AstNode, context: ResolverContext): void
⋮----
// Use generateEntityId consistent with Pass 1 (filePath:name for classes/interfaces)
⋮----
// Use generateEntityId consistent with Pass 1
⋮----
/**
 * Resolves cross-file CALLS and MUTATES_STATE relationships for TS/JS.
 */
export function resolveTsCrossFileInteractions(sourceFile: SourceFile, fileNode: AstNode, context: ResolverContext): void
⋮----
const { logger, nodeIndex } = context; // Destructure only what's needed directly
⋮----
// --- DEBUG LOG ---
⋮----
// --- END DEBUG LOG ---
⋮----
// --- DEBUG LOG ---
// Use type guard before accessing getName
⋮----
// --- END DEBUG LOG ---
⋮----
/**
 * Helper to analyze calls and assignments within a TS/JS function/method body for Pass 2.
 */
function analyzeTsBodyInteractions(body: Node, sourceNode: AstNode, context: ResolverContext): void
⋮----
// Analyze Calls
⋮----
// Analyze Assignments (Mutations)
⋮----
// Analyze Try/Catch (HANDLES_ERROR)
⋮----
/**
 * Resolves USES_COMPONENT relationships based on JSX element usage.
 */
export function resolveTsComponentUsage(sourceFile: SourceFile, fileNode: AstNode, context: ResolverContext): void
⋮----
// Check if sourceComponentNode is defined before logging
⋮----
// Check targetComponentNode exists before accessing filePath
const isCrossFile = targetComponentNode ? sourceComponentNode.filePath !== targetComponentNode.filePath : true; // Assume cross-file if target not found
````

## File: src/analyzer/analyzer-service.ts
````typescript
// src/analyzer/analyzer-service.ts
import path from 'path';
import { FileScanner, FileInfo } from '../scanner/file-scanner.js';
import { Parser } from './parser.js';
import { RelationshipResolver } from './relationship-resolver.js';
import { StorageManager } from './storage-manager.js';
import { AstNode, RelationshipInfo } from './types.js';
import { createContextLogger } from '../utils/logger.js';
import config from '../config/index.js';
import { Project } from 'ts-morph';
import { Neo4jClient } from '../database/neo4j-client.js';
import { Neo4jError } from '../utils/errors.js';
// Removed setTimeout import
⋮----
/**
 * Orchestrates the code analysis process: scanning, parsing, resolving, and storing.
 */
export class AnalyzerService
⋮----
constructor()
⋮----
// Instantiate Neo4jClient without overrides to use config defaults
⋮----
// Pass the client instance to StorageManager
⋮----
/**
     * Runs the full analysis pipeline for a given directory.
     * Assumes database is cleared externally (e.g., via test setup).
     * @param directory - The root directory to analyze.
     */
async analyze(directory: string): Promise<void>
⋮----
// Instantiate FileScanner here with directory and config
// Use config.supportedExtensions and config.ignorePatterns directly
⋮----
// 1. Scan Files
⋮----
const files: FileInfo[] = await scanner.scan(); // No argument needed
⋮----
// 2. Parse Files (Pass 1)
⋮----
// 3. Collect Pass 1 Results
⋮----
// 4. Resolve Relationships (Pass 2)
⋮----
// 5. Store Results
⋮----
// Ensure driver is initialized before storing
⋮----
// --- Database clearing is now handled by beforeEach in tests ---
⋮----
// Group relationships by type before saving
⋮----
// Push directly, using non-null assertion to satisfy compiler
⋮----
// Save relationships batch by type
⋮----
// --- TEMPORARY DEBUG LOG ---
⋮----
// --- END TEMPORARY DEBUG LOG ---
// Ensure batch is not undefined before passing (still good practice)
⋮----
throw error; // Re-throw the error for higher-level handling
⋮----
// 6. Cleanup & Disconnect
````

## File: src/analyzer/cypher-utils.ts
````typescript
// src/analyzer/cypher-utils.ts
import { NODE_LABELS } from '../database/schema.js'; // Import labels from schema
⋮----
/**
 * Generates the Cypher clauses for removing old labels and setting the correct new label
 * based on the 'kind' property during a node MERGE operation.
 *
 * @returns An object containing the removeClause and setLabelClauses.
 */
export function generateNodeLabelCypher():
⋮----
// Use the imported NODE_LABELS
⋮----
const removeClause = allLabels.map((label: string) => `\`${label}\``).join(':'); // Generates `:File:Directory:...`
⋮----
// Generate the FOREACH clauses dynamically based on NODE_LABELS
⋮----
).join('\n                '); // Indentation for readability in the final query
⋮----
// Add other Cypher generation utilities here if needed in the future
````

## File: src/analyzer/parser-utils.ts
````typescript
import fsPromises from 'fs/promises';
import * as fsSync from 'fs'; // Keep sync version for path resolution checks
import { FileSystemError } from '../utils/errors.js';
import { InstanceCounter } from './types.js';
import config from '../config/index.js'; // Import config for TEMP_DIR
⋮----
const TEMP_DIR = config.tempDir; // Use tempDir from config
⋮----
/**
 * Ensures the temporary directory for intermediate results exists.
 */
export async function ensureTempDir(): Promise<void>
⋮----
/**
 * Generates a unique temporary file path based on the source file path hash.
 * @param sourceFilePath - The absolute path of the source file.
 * @returns The absolute path for the temporary JSON file.
 */
export function getTempFilePath(sourceFilePath: string): string
⋮----
// Normalize path before hashing for consistency
⋮----
/**
 * Resolves a relative import path to an absolute path, attempting to find the correct file extension.
 * @param sourcePath - The absolute path of the file containing the import.
 * @param importPath - The relative or module path string from the import statement.
 * @returns The resolved absolute path or the original importPath if it's likely a node module or alias.
 */
export function resolveImportPath(sourcePath: string, importPath: string): string
⋮----
// If it's not a relative path, assume it's a node module or alias (handled later by resolver)
⋮----
// Remove .js/.jsx extension if present, as we want to find the .ts/.tsx source
⋮----
// Attempt to resolve extension if missing
⋮----
const extensions = config.supportedExtensions; // Use extensions from config
⋮----
// Check for file with extension
⋮----
} catch { /* Ignore */ }
⋮----
// Check for index file in directory if file wasn't found directly
⋮----
} catch { /* Ignore */ }
⋮----
// If still not found, return the original resolved path without extension.
// The relationship resolver might handle this later based on available nodes.
⋮----
// Normalize path separators for consistency
⋮----
/**
 * Generates a stable, unique identifier for a code entity based on its type and qualified name.
 * Ensures consistency across analysis runs. Normalizes path separators and converts to lowercase.
 * @param prefix - The type of the entity (e.g., 'class', 'function', 'file', 'directory'). Lowercase.
 * @param qualifiedName - A unique name within the project context (e.g., 'path/to/file:ClassName').
 *                        Should be consistently generated by the parsers.
 * @returns The generated entity ID string.
 */
export function generateEntityId(prefix: string, qualifiedName: string): string
⋮----
// Potentially throw an error or return a placeholder
return `${prefix || 'unknown'}:${qualifiedName || 'unknown'}:${Date.now()}`; // Add timestamp for some uniqueness
⋮----
// Normalize path separators, convert to lowercase, and sanitize characters
⋮----
.replace(/\\/g, '/') // Normalize slashes FIRST
.toLowerCase()       // Convert to lowercase for case-insensitivity
.replace(/[^a-z0-9_.:/-]/g, '_'); // Allow specific chars (adjusted for lowercase), replace others
return `${prefix.toLowerCase()}:${safeIdentifier}`; // Ensure prefix is lowercase too
⋮----
/**
 * Generates a unique instance ID for a node or relationship within the context of a single file parse.
 * Primarily used for temporary identification during parsing.
 * @param instanceCounter - The counter object for the current file parse.
 * @param prefix - The type of the element (e.g., 'class', 'function', 'calls'). Lowercase.
 * @param identifier - A descriptive identifier (e.g., qualified name, source:target).
 * @param options - Optional line and column numbers for added uniqueness context.
 * @returns The generated instance ID string.
 */
export function generateInstanceId(
    instanceCounter: InstanceCounter,
    prefix: string,
    identifier: string,
    options: { line?: number; column?: number } = {}
): string
⋮----
// Include line/column if available for better debugging/uniqueness
⋮----
const counter = ++instanceCounter.count; // Increment counter for uniqueness within the file
// Format: type:identifier:Lline:Ccol:counter
````

## File: src/analyzer/parser.ts
````typescript
// src/analyzer/parser.ts
import path from 'path';
import fs from 'fs/promises';
import { Project, ScriptKind } from 'ts-morph';
import { FileInfo } from '../scanner/file-scanner.js';
import { AstNode, RelationshipInfo, SingleFileParseResult, FileNode } from './types.js';
// Import FileNode
import { PythonAstParser } from './python-parser.js';
import { CCppParser } from './parsers/c-cpp-parser.js';
import { JavaParser } from './parsers/java-parser.js';
import { GoParser } from './parsers/go-parser.js';
import { CSharpParser } from './parsers/csharp-parser.js';
// import { SqlParser } from './parsers/sql-parser.js'; // Temporarily disabled
// Import individual TS parsers
import { parseFunctions } from './parsers/function-parser.js';
import { parseClasses } from './parsers/class-parser.js';
import { parseVariables } from './parsers/variable-parser.js';
import { parseInterfaces } from './parsers/interface-parser.js';
import { parseTypeAliases } from './parsers/type-alias-parser.js';
import { parseJsx } from './parsers/jsx-parser.js';
// Assuming an import parser exists:
import { parseImports } from './parsers/import-parser.js'; // Add import parser
⋮----
import { createContextLogger } from '../utils/logger.js';
import { ParserError } from '../utils/errors.js';
import config from '../config/index.js';
import { generateEntityId, generateInstanceId } from './parser-utils.js';
import ts from 'typescript';
⋮----
/**
 * Orchestrates the parsing process for different languages.
 */
export class Parser
⋮----
// private sqlParser: SqlParser; // Temporarily disabled
private tsResults: Map<string, SingleFileParseResult> = new Map(); // Store TS results in memory
⋮----
constructor()
⋮----
// Initialize Project using the main tsconfig.json
⋮----
// Optionally skip adding source files automatically if we add them manually later
// skipAddingFilesFromTsConfig: true,
⋮----
// this.sqlParser = new SqlParser(); // Temporarily disabled
// Removed tsParser instantiation
⋮----
/**
     * Parses a list of files, delegating to the appropriate language parser.
     * For TS/JS files, it adds them to the ts-morph project but doesn't generate separate JSON.
     * @param files - An array of FileInfo objects.
     * @returns A promise that resolves when all files have been parsed (Pass 1).
     */
async parseFiles(files: FileInfo[]): Promise<void>
⋮----
// Store normalized paths of all files passed to this specific run
⋮----
// case '.sql': // Temporarily disabled
//     parsePromise = this.sqlParser.parseFile(file);
//     break;
⋮----
// Add TS/JS files to the project instead of calling a separate parser
⋮----
parsePromise = Promise.resolve(null); // No JSON file generated for TS/JS in Pass 1
⋮----
// Now parse the added TS/JS files
// Pass the set of target file paths to filter which sourceFiles get fully parsed
⋮----
/**
     * Collects all nodes and relationships from the temporary JSON files
     * generated during Pass 1 (for non-TS languages).
     * Uses Maps to ensure entityId uniqueness.
     * @returns An object containing arrays of all nodes and relationships.
     * Includes results from in-memory TS parsing.
     */
async collectResults(): Promise<
⋮----
const nodeMap = new Map<string, AstNode>(); // Use Map for nodes
const relationshipMap = new Map<string, RelationshipInfo>(); // Use Map for relationships
⋮----
// logger.debug(`[collectResults] Processing JSON file ${processedJsonCount}/${jsonFiles.length}: ${file}`); // Removed log
⋮----
// logger.debug(`[collectResults] Parsed JSON for: ${file} (Source Path: ${result.filePath})`); // Removed log
⋮----
// Deduplicate nodes within this specific JSON file first
⋮----
// logger.warn(`[collectResults] Intra-file duplicate node entityId found in ${result.filePath}: ${node.entityId} (Kind: ${node.kind})`); // Removed log
⋮----
// Add unique nodes from this file to the main map
⋮----
// logger.warn(`[collectResults] Cross-file duplicate node entityId (overwriting): ${entityId} (Kind: ${node.kind}, Incoming: ${node.filePath}, Existing: ${existingNode?.filePath})`); // Removed log
⋮----
// Add relationships to map (duplicates less likely but handle anyway)
⋮----
// logger.warn(`[collectResults] Overwriting relationship with duplicate entityId: ${rel.entityId} (Type: ${rel.type})`); // Removed log
⋮----
// logger.debug(`[collectResults] Processed ${fileNodeMap.size} unique nodes and ${result.relationships.length} relationships from ${file}`); // Removed log
⋮----
try { await fs.unlink(filePath); } catch { /* ignore cleanup error */ }
⋮----
// --- REMOVED TS/JS File Node Generation Logic ---
// --- REMOVED Directory Node Generation Logic ---
⋮----
// Add results from in-memory TS parsing
⋮----
// Deduplicate nodes within this specific TS file result first
⋮----
// Add unique nodes from this file to the main map
⋮----
// Add relationships from this file to the main map
⋮----
this.tsResults.clear(); // Clear memory after collection
⋮----
/**
     * Provides access to the ts-morph Project instance.
     * Useful for Pass 2 relationship resolution.
     */
getTsProject(): Project
⋮----
/**
     * Parses all TypeScript/JavaScript SourceFile objects currently in the ts-morph project.
     * Only processes files whose paths are included in the targetFiles set.
     * @param targetFiles - A Set containing the normalized absolute paths of the files to be parsed.
     */
private async _parseTsProjectFiles(targetFiles: Set<string>): Promise<void>
⋮----
const instanceCounter = { count: 0 }; // Simple counter for instance IDs per run
⋮----
const filePath = sourceFile.getFilePath().replace(/\\/g, '/'); // Normalize path
⋮----
// Only process files that were part of the initial target scan for this run
⋮----
// logger.trace(`Skipping non-target TS/JS file: ${filePath}`); // Optional: trace logging
⋮----
// 1. Create FileNode
⋮----
const fileNode: FileNode = { // Explicitly type as FileNode
⋮----
language: sourceFile.getLanguageVariant() === ts.LanguageVariant.JSX ? 'TSX' : 'TypeScript', // Basic language detection
⋮----
// 2. Prepare result and context for this file
⋮----
nodes: [fileNode], // Start with the file node
⋮----
const addNode = (node: AstNode) =>
const addRelationship = (rel: RelationshipInfo) =>
⋮----
const context = { // Create ParserContext
⋮----
fileNode: fileNode, // Pass the created FileNode
result: result,     // Pass the result object
⋮----
logger: createContextLogger(`Parser-${path.basename(filePath)}`), // File-specific logger context
resolveImportPath: (source: string, imp: string) => { /* TODO: Implement proper import resolution */ return imp; },
⋮----
// 3. Call individual parsers
parseImports(context); // Add call to import parser
⋮----
// Check language from the fileNode within the context
if (context.fileNode.language === 'TSX') { // Only parse JSX if applicable
⋮----
// Call other parsers (e.g., parseExports)
⋮----
// Store the result for this file
⋮----
// Helper function to ensure ts-morph compiler options are compatible
function ensureTsConfig(project: Project): void
````

## File: src/analyzer/python-parser.spec.ts
````typescript
import { describe, it, expect, beforeAll } from 'vitest';
import path from 'path';
import fs from 'fs/promises';
import { PythonAstParser } from './python-parser.js'; // Adjust path as needed
import { FileInfo } from '../scanner/file-scanner.js'; // Adjust path as needed
import { AstNode, RelationshipInfo, SingleFileParseResult } from './types.js'; // Adjust path as needed
import config from '../config/index.js'; // Adjust path as needed
⋮----
// Helper to load fixture content
async function loadFixture(fixturePath: string): Promise<string>
⋮----
// Helper to parse a fixture file and return the result
async function parseFixture(fixturePath: string): Promise<SingleFileParseResult>
⋮----
// Ensure temp dir exists (parser might rely on it)
⋮----
} catch (e) { /* Ignore if exists */ }
⋮----
await fs.unlink(tempFilePath); // Clean up temp file
⋮----
const fixturePath = 'test_fixtures/python/simple_test.py'; // Use the correct fixture
⋮----
const fileNode = result.nodes.find(n => n.kind === 'File'); // Expect 'File' kind
⋮----
expect(funcNodes.length).toBe(1); // greet
expect(methodNodes.length).toBe(2); // __init__, get_value
⋮----
expect(greetFunc?.startLine).toBe(3); // Adjusted line
expect(greetFunc?.endLine).toBe(5); // Adjusted line
⋮----
expect(paramNodes.length).toBe(4); // name, self, value, self
⋮----
expect(nameParam?.parentId).toContain(':greet'); // Check parent linkage
⋮----
expect(valueParam?.parentId).toContain(':SimpleClass.__init__'); // Check parent linkage
⋮----
expect(callRels.length).toBeGreaterThanOrEqual(2); // print() inside greet, greet() at top level
⋮----
// Find the call to 'print' (targetId is placeholder 'unknown:print')
⋮----
expect(printCallRel?.sourceId).toContain(':greet'); // Called from greet
⋮----
// Find the call to 'greet' (targetId is placeholder 'unknown:greet')
⋮----
expect(greetCallRel?.sourceId).toContain('file:'); // Called from module/file level
⋮----
expect(varNodes.length).toBe(1); // instance
⋮----
expect(instanceVar?.parentId).toContain('file:'); // Assigned at module/file level
````

## File: src/analyzer/python-parser.ts
````typescript
// src/analyzer/python-parser.ts
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs/promises';
import { existsSync } from 'fs'; // Import synchronous existsSync
import { createContextLogger } from '../utils/logger.js';
import { ParserError, FileSystemError } from '../utils/errors.js';
import { FileInfo } from '../scanner/file-scanner.js';
import { AstNode, RelationshipInfo, SingleFileParseResult, InstanceCounter } from './types.js';
import { ensureTempDir, getTempFilePath, generateInstanceId, generateEntityId } from './parser-utils.js'; // Reusing utils
⋮----
// Interface matching the JSON structure output by python_parser.py
interface PythonParseOutput extends SingleFileParseResult {
    error?: string; // Optional error field
}
⋮----
error?: string; // Optional error field
⋮----
/**
 * Parses Python files using an external Python script (`python_parser.py`)
 * and translates the output into the common AstNode/RelationshipInfo format.
 */
export class PythonAstParser
⋮----
private pythonExecutable: string; // Path to python executable (e.g., 'python' or 'python3')
⋮----
constructor(pythonExecutable: string = 'python') { // Default to 'python'
        this.pythonExecutable = pythonExecutable;
logger.debug(`Python AST Parser initialized with executable: $
⋮----
/**
     * Parses a single Python file by executing the external script.
     * @param file - FileInfo object for the Python file.
     * @returns A promise resolving to the path of the temporary result file.
     * @throws {ParserError} If the Python script fails or returns an error.
     */
async parseFile(file: FileInfo): Promise<string>
⋮----
await ensureTempDir(); // Ensure temp directory exists
⋮----
const absoluteFilePath = path.resolve(file.path); // Ensure absolute path for the script
⋮----
// Basic validation of the received structure (can be expanded)
⋮----
// --- DEBUG LOG: Inspect raw result ---
⋮----
// --- END DEBUG LOG ---
⋮----
// --- Data Transformation (if needed) ---
// The python script is designed to output data largely matching SingleFileParseResult.
// If transformations were needed (e.g., renaming fields, calculating LOC), they'd happen here.
// For now, we assume the structure is compatible. We just need to add instance IDs.
⋮----
filePath: result.filePath, // Use path from result
⋮----
// Generate instance ID based on Python output location/name
⋮----
createdAt: new Date().toISOString(), // Add timestamp
⋮----
// Generate instance ID for relationship
id: generateInstanceId(instanceCounter, rel.type.toLowerCase(), `${rel.sourceId}:${rel.targetId}`), // Simple ID for rel
createdAt: new Date().toISOString(), // Add timestamp
weight: rel.weight ?? 1, // Default weight
⋮----
// Attempt to clean up temp file if created
try { await fs.unlink(tempFilePath); } catch { /* ignore cleanup error */ }
// Re-throw as a ParserError
⋮----
/**
     * Executes the python_parser.py script.
     * @param filePath - Absolute path to the Python file to parse.
     * @returns A promise resolving to the JSON string output from the script.
     */
private runPythonScript(filePath: string): Promise<string>
⋮----
// --- Debug: Check if Node.js can see the file ---
⋮----
// --- End Debug ---
const scriptPath = path.resolve(process.cwd(), 'python_parser.py'); // Assuming script is in root
⋮----
const childProcess = spawn(this.pythonExecutable, [scriptPath, filePath], { cwd: process.cwd() }); // Explicitly set CWD
// Renamed variable
⋮----
// Use childProcess
⋮----
// Use childProcess
⋮----
// Use childProcess
⋮----
// Use childProcess
⋮----
// Try to parse stderr for a JSON error message from the script
⋮----
} catch { /* Ignore JSON parse error on stderr */ }
// Fallback error
````

## File: src/analyzer/relationship-resolver.spec.ts
````typescript
import { describe, it, expect, beforeAll } from 'vitest';
import path from 'path';
import fs from 'fs/promises';
import { Project } from 'ts-morph'; // Import ts-morph Project
import { RelationshipResolver } from './relationship-resolver.js'; // Adjust path
import { AstNode, RelationshipInfo, SingleFileParseResult } from './types.js'; // Adjust path
import { generateEntityId, generateInstanceId } from './parser-utils.js'; // Adjust path
import config from '../config/index.js'; // Adjust path
import { createContextLogger } from '../utils/logger.js'; // Import logger
⋮----
const testLogger = createContextLogger('RelationshipResolverSpec'); // Create a logger for the test
⋮----
// Mock data representing parsed results from multiple files
⋮----
// --- File A (src/a.ts) ---
const fileAPath = 'src/a.ts'; // Use relative-like path for mock data consistency
const fileAAbsolutePath = '/' + fileAPath; // Path used by ts-morph in-memory
⋮----
const fileAEntityId = generateEntityId('file', fileAAbsolutePath); // Use absolute-like path
⋮----
entityId: fileAEntityId, kind: 'File', name: 'a.ts', filePath: fileAAbsolutePath, // Use absolute-like path
⋮----
// Entity ID generation for import (assuming it uses line number)
const importBEntityId = generateEntityId('importdeclaration', `${fileAAbsolutePath}:./b:2`); // Line 2 in content
const importBNode: AstNode = { // Simplified ImportDeclaration node
⋮----
properties: { importPath: './b', importedNames: ['funcB'] } // Assume funcB is imported
⋮----
// Corrected Entity ID generation for function (Use 'function' kind, NO line number)
⋮----
id: generateInstanceId(instanceCounter, 'tsfunction', 'funcA', { line: 3, column: 0 }), // Instance ID can keep 'tsfunction'
entityId: funcAEntityId, kind: 'TSFunction', name: 'funcA', // Keep original kind for node data
⋮----
// Relationship: File A IMPORTS ImportDeclaration B
⋮----
// Relationship: funcA CALLS funcB (initially unresolved target)
// Corrected Entity ID generation for call relationship (Use 'function' kind, NO line number in source entity ID)
const callRelEntityId = generateEntityId('calls', `${funcAEntityId}:funcB:4`); // Line 4 for call site info
⋮----
entityId: callRelEntityId, type: 'CALLS', sourceId: funcAEntityId, targetId: 'unresolved:funcB', // Mark as unresolved
⋮----
// --- File B (src/b.ts) ---
const fileBPath = 'src/b.ts'; // Use relative-like path
const fileBAbsolutePath = '/' + fileBPath; // Path used by ts-morph in-memory
⋮----
const fileBEntityId = generateEntityId('file', fileBAbsolutePath); // Use absolute-like path
⋮----
entityId: fileBEntityId, kind: 'File', name: 'b.ts', filePath: fileBAbsolutePath, // Use absolute-like path
⋮----
// Corrected Entity ID generation for function (Use 'function' kind, NO line number)
⋮----
id: generateInstanceId(instanceCounter, 'tsfunction', 'funcB', { line: 2, column: 0 }), // Instance ID can keep 'tsfunction'
entityId: funcBEntityId, kind: 'TSFunction', name: 'funcB', // Keep original kind for node data
⋮----
properties: { isExported: true } // Mark as exported
⋮----
// Relationship: File B DEFINES_FUNCTION funcB
⋮----
// Instantiate the resolver with mock data
⋮----
// --- DEBUG LOG ---
⋮----
// --- END DEBUG LOG ---
⋮----
// Create a ts-morph project and add mock files
// Use absolute-like paths for ts-morph in-memory system
⋮----
project.createSourceFile(fileAAbsolutePath, fileAContent); // Use absolute-like path
project.createSourceFile(fileBAbsolutePath, fileBContent); // Use absolute-like path
⋮----
const pass2Relationships = await resolver.resolveRelationships(project); // Pass the project
⋮----
r.type === 'RESOLVES_IMPORT' && // Check for RESOLVES_IMPORT now
r.sourceId === importBEntityId && // Source is the ImportDeclaration node
r.targetId === funcBEntityId // Target should now be the actual function node
⋮----
// expect(resolvedImportRel?.properties?.resolved).toBe(true); // RESOLVES_IMPORT doesn't have 'resolved' property
⋮----
const pass2Relationships = await resolver.resolveRelationships(project); // Pass the project
⋮----
r.targetId === funcBEntityId // Target should now be the actual function node
⋮----
expect(resolvedCallRel?.properties?.isPlaceholder).toBe(false); // Check if placeholder is false
⋮----
// Add more tests:
// - Unresolved imports/calls
// - Calls within the same file (should already be resolved in pass 1 ideally)
// - Inheritance resolution (EXTENDS)
// - Interface implementation resolution (IMPLEMENTS)
// - Tests for other languages once resolver supports them
````

## File: src/analyzer/relationship-resolver.ts
````typescript
import { Project, SourceFile, Node } from 'ts-morph'; // Keep SourceFile for TS resolvers
import { AstNode, RelationshipInfo, ResolverContext } from './types.js';
import { generateEntityId, generateInstanceId, resolveImportPath } from './parser-utils.js';
import { createContextLogger } from '../utils/logger.js';
// Import new resolver functions
import { resolveTsModules, resolveTsInheritance, resolveTsCrossFileInteractions, resolveTsComponentUsage } from './resolvers/ts-resolver.js';
import { resolveCIncludes } from './resolvers/c-cpp-resolver.js';
⋮----
/**
 * Resolves cross-file and deferred relationships (Pass 2).
 * Delegates resolution logic to language-specific handlers.
 */
export class RelationshipResolver
⋮----
private nodeIndex: Map<string, AstNode>; // Map entityId -> AstNode
⋮----
private pass1RelationshipIds: Set<string>; // Store entityIds of relationships found in Pass 1
private context: ResolverContext | null = null; // Context for Pass 2 operations
⋮----
constructor(allNodes: AstNode[], pass1Relationships: RelationshipInfo[])
⋮----
/**
     * Resolves relationships using the ts-morph project (for TS/JS) and collected node data.
     * @param project - The ts-morph Project containing parsed TS/JS source files.
     * @returns An array of resolved RelationshipInfo objects.
     */
async resolveRelationships(project: Project): Promise<RelationshipInfo[]>
⋮----
this.relationships = []; // Reset relationships array for this run
⋮----
let instanceCounter = { count: 0 }; // Simple counter for Pass 2 instance IDs
const addedRelEntityIds = new Set<string>(); // Track relationships added in THIS pass
⋮----
// Iterate through all files represented by nodes from Pass 1
const fileNodes = Array.from(this.nodeIndex.values()).filter(node => node.kind === 'File' || node.kind === 'PythonModule'); // Include PythonModule
⋮----
// Resolve TS/JS specific relationships using ts-morph SourceFile
⋮----
// Resolve C/C++ Includes (placeholder resolution)
// Note: sourceFile is passed for consistency but not used for C/C++ AST access here
⋮----
// We need a way to get the ts-morph SourceFile even for C/C++ if we want to use it
// For now, pass undefined or handle differently if ts-morph isn't used for C/C++ resolution
const cSourceFile = project.getSourceFile(fileNode.filePath); // Attempt to get it anyway
⋮----
// TODO: Add calls to language-specific resolvers for Python, Java, Go, C#, SQL etc.
// These would likely NOT use the ts-morph `sourceFile` object but operate on `fileNode` and `nodeIndex`.
// Example:
// if (fileNode.language === 'Python') {
//     resolvePythonImports(fileNode, currentContext);
//     resolvePythonCalls(fileNode, currentContext);
// }
⋮----
// --- Helper Methods --- (Only keep essential ones if needed by the class itself)
⋮----
private findNodeByFilePath(filePath: string): AstNode | undefined
⋮----
// Also check for PythonModule kind if the path matches
⋮----
// Removed resolveModules, resolveInheritance, resolveCrossFileInteractions,
// analyzeBodyInteractions, resolveComponentUsage, resolveCIncludes
// Removed isInsideConditionalContext (moved to ts-resolver.ts)
````

## File: src/analyzer/storage-manager.ts
````typescript
import { Neo4jClient } from '../database/neo4j-client.js';
import { AstNode, RelationshipInfo } from './types.js';
import { createContextLogger } from '../utils/logger.js';
import { generateNodeLabelCypher } from './cypher-utils.js'; // Import the new utility
import config from '../config/index.js';
import { Neo4jError } from '../utils/errors.js';
⋮----
/**
 * Manages batch writing of nodes and relationships to the Neo4j database.
 */
export class StorageManager
⋮----
constructor(neo4jClient: Neo4jClient)
⋮----
/**
     * Saves an array of AstNode objects to Neo4j in batches using MERGE.
     * Assumes the input 'nodes' array has already been deduplicated by entityId by the caller.
     * Uses a simple UNWIND + MERGE + SET Cypher query.
     * @param nodes - The array of unique AstNode objects to save.
     */
async saveNodesBatch(nodes: AstNode[]): Promise<void>
⋮----
// Assume input `nodes` are already deduplicated by the caller (Parser.collectResults)
⋮----
// Simple UNWIND + MERGE + SET query
⋮----
/**
     * Saves an array of RelationshipInfo objects to Neo4j in batches using MERGE.
     * Assumes the input 'relationships' array has already been deduplicated by entityId.
     * @param relationshipType - The specific type of relationships in this batch.
     * @param relationships - The array of unique RelationshipInfo objects to save.
     */
async saveRelationshipsBatch(relationshipType: string, relationships: RelationshipInfo[]): Promise<void>
⋮----
// Assume input `relationships` are already deduplicated by the caller (Parser.collectResults)
⋮----
// Use MATCH for nodes, assuming they were created in saveNodesBatch
⋮----
/**
     * Prepares AstNode properties for Neo4j storage.
     */
private prepareNodeProperties(node: AstNode): Record<string, any>
⋮----
finalProperties.entityId = entityId; // Ensure entityId is part of the properties for SET
⋮----
/**
     * Prepares RelationshipInfo properties for Neo4j storage.
     */
private prepareRelationshipProperties(rel: RelationshipInfo): Record<string, any>
⋮----
preparedProps[key] = null; // Use null instead of deleting
````

## File: src/analyzer/types.ts
````typescript
// src/analyzer/types.ts
import winston from 'winston'; // Import Logger type
import ts from 'typescript'; // Needed for ts.Node below, ensure typescript is a dependency if not already
import { SourceFile } from 'ts-morph'; // Import ts-morph SourceFile
⋮----
// --- Core Types ---
⋮----
/**
 * Represents a generic node in the Abstract Syntax Tree (AST).
 * This is the base interface extended by language-specific node types.
 */
export interface AstNode {
    id: string;             // Unique instance ID for this node in this specific parse run
    entityId: string;       // Globally unique identifier for the code entity (e.g., file path + function name + line)
    kind: string;           // Type of the node (e.g., 'File', 'Function', 'Class', 'Import')
    name: string;           // Name of the node (e.g., function name, class name, filename)
    type?: string;          // Optional: Type information (e.g., variable type, function return type)
    filePath: string;       // Absolute path to the file containing this node
    startLine: number;      // Starting line number (1-based)
    endLine: number;        // Ending line number (1-based)
    startColumn: number;    // Starting column number (0-based)
    endColumn: number;      // Ending column number (0-based)
    language: string;       // Programming language (e.g., 'TypeScript', 'Python', 'Java')
    loc?: number;           // Lines of code (optional)
    properties?: Record<string, any>; // Additional language-specific properties
    isExported?: boolean;   // Optional: Indicates if the node is exported
    complexity?: number;    // Optional: Cyclomatic complexity or similar metric
    isAbstract?: boolean;   // Optional: Indicates if a class/method is abstract
    isAsync?: boolean;      // Optional: Indicates if a function/method is async
    isOptional?: boolean;   // Optional: Indicates if a parameter/property is optional
    isStatic?: boolean;     // Optional: Indicates if a member is static
    isGenerator?: boolean;  // Optional: Indicates if a function is a generator
    isRestParameter?: boolean; // Optional: Indicates if a parameter is a rest parameter
    isConstant?: boolean;   // Optional: Indicates if a variable is constant
    visibility?: 'public' | 'private' | 'protected' | 'internal' | 'package'; // Optional: Visibility modifier
    returnType?: string;    // Optional: Return type of a function/method
    implementsInterfaces?: string[]; // Optional: List of implemented interface names
    modifierFlags?: string[]; // Optional: List of modifier keywords (e.g., 'export', 'async', 'static')
    tags?: string[];        // Optional: List of tags (e.g., from JSDoc @tags)
    documentation?: string; // Optional: Documentation string (e.g., from JSDoc)
    docComment?: string;    // Optional: Raw documentation comment
    parentId?: string;      // Optional entityId of the parent node (e.g., class containing a method)
    createdAt: string;      // ISO timestamp of creation
}
⋮----
id: string;             // Unique instance ID for this node in this specific parse run
entityId: string;       // Globally unique identifier for the code entity (e.g., file path + function name + line)
kind: string;           // Type of the node (e.g., 'File', 'Function', 'Class', 'Import')
name: string;           // Name of the node (e.g., function name, class name, filename)
type?: string;          // Optional: Type information (e.g., variable type, function return type)
filePath: string;       // Absolute path to the file containing this node
startLine: number;      // Starting line number (1-based)
endLine: number;        // Ending line number (1-based)
startColumn: number;    // Starting column number (0-based)
endColumn: number;      // Ending column number (0-based)
language: string;       // Programming language (e.g., 'TypeScript', 'Python', 'Java')
loc?: number;           // Lines of code (optional)
properties?: Record<string, any>; // Additional language-specific properties
isExported?: boolean;   // Optional: Indicates if the node is exported
complexity?: number;    // Optional: Cyclomatic complexity or similar metric
isAbstract?: boolean;   // Optional: Indicates if a class/method is abstract
isAsync?: boolean;      // Optional: Indicates if a function/method is async
isOptional?: boolean;   // Optional: Indicates if a parameter/property is optional
isStatic?: boolean;     // Optional: Indicates if a member is static
isGenerator?: boolean;  // Optional: Indicates if a function is a generator
isRestParameter?: boolean; // Optional: Indicates if a parameter is a rest parameter
isConstant?: boolean;   // Optional: Indicates if a variable is constant
visibility?: 'public' | 'private' | 'protected' | 'internal' | 'package'; // Optional: Visibility modifier
returnType?: string;    // Optional: Return type of a function/method
implementsInterfaces?: string[]; // Optional: List of implemented interface names
modifierFlags?: string[]; // Optional: List of modifier keywords (e.g., 'export', 'async', 'static')
tags?: string[];        // Optional: List of tags (e.g., from JSDoc @tags)
documentation?: string; // Optional: Documentation string (e.g., from JSDoc)
docComment?: string;    // Optional: Raw documentation comment
parentId?: string;      // Optional entityId of the parent node (e.g., class containing a method)
createdAt: string;      // ISO timestamp of creation
⋮----
/**
 * Represents a relationship between two AstNode objects.
 */
export interface RelationshipInfo {
    id: string;             // Unique instance ID for this relationship in this specific parse run
    entityId: string;       // Globally unique identifier for the relationship instance
    type: string;           // Type of the relationship (e.g., 'CALLS', 'IMPORTS', 'EXTENDS')
    sourceId: string;       // entityId of the source node
    targetId: string;       // entityId of the target node
    properties?: Record<string, any>; // Additional properties for the relationship
    weight?: number;        // Optional weight for ranking or analysis
    createdAt: string;      // ISO timestamp of creation
}
⋮----
id: string;             // Unique instance ID for this relationship in this specific parse run
entityId: string;       // Globally unique identifier for the relationship instance
type: string;           // Type of the relationship (e.g., 'CALLS', 'IMPORTS', 'EXTENDS')
sourceId: string;       // entityId of the source node
targetId: string;       // entityId of the target node
properties?: Record<string, any>; // Additional properties for the relationship
weight?: number;        // Optional weight for ranking or analysis
createdAt: string;      // ISO timestamp of creation
⋮----
/**
 * Represents the result of parsing a single file.
 */
export interface SingleFileParseResult {
    filePath: string;
    nodes: AstNode[];
    relationships: RelationshipInfo[];
}
⋮----
/**
 * Helper type for generating unique instance IDs during a parse run.
 */
export interface InstanceCounter {
    count: number;
}
⋮----
/**
 * Context object passed to parser functions.
 */
export interface ParserContext {
    filePath: string;
    sourceFile: SourceFile; // Use ts-morph SourceFile
    fileNode: FileNode; // Reference to the FileNode being processed
    result: SingleFileParseResult; // The accumulating result for the current file
    addNode: (node: AstNode) => void;
    addRelationship: (rel: RelationshipInfo) => void;
    generateId: (prefix: string, identifier: string, options?: { line?: number; column?: number }) => string;
    generateEntityId: (kind: string, qualifiedName: string) => string;
    logger: winston.Logger;
    resolveImportPath: (sourcePath: string, importPath: string) => string;
    now: string;
    // Add any other properties needed during parsing
}
⋮----
sourceFile: SourceFile; // Use ts-morph SourceFile
fileNode: FileNode; // Reference to the FileNode being processed
result: SingleFileParseResult; // The accumulating result for the current file
⋮----
// Add any other properties needed during parsing
⋮----
/**
 * Represents the resolved information about a target declaration, used in Pass 2.
 */
export interface TargetDeclarationInfo {
    name: string;
    kind: string; // e.g., 'Function', 'Class', 'Variable', 'Interface', 'Method', 'Parameter'
    filePath: string; // Absolute, normalized path
    entityId: string; // Globally unique ID matching Pass 1 generation
}
⋮----
kind: string; // e.g., 'Function', 'Class', 'Variable', 'Interface', 'Method', 'Parameter'
filePath: string; // Absolute, normalized path
entityId: string; // Globally unique ID matching Pass 1 generation
⋮----
/**
 * Context object passed to relationship resolver functions.
 */
export interface ResolverContext {
    nodeIndex: Map<string, AstNode>;
    addRelationship: (rel: RelationshipInfo) => void;
    generateId: (prefix: string, identifier: string, options?: { line?: number; column?: number }) => string;
    generateEntityId: (kind: string, qualifiedName: string) => string;
    logger: winston.Logger;
    resolveImportPath: (sourcePath: string, importPath: string) => string;
    now: string;
}
⋮----
// --- Language Agnostic Node Kinds (Examples) ---
⋮----
export interface FileNode extends AstNode {
    kind: 'File';
    loc: number; // Lines of code for the file
}
⋮----
loc: number; // Lines of code for the file
⋮----
// --- Component Node (e.g., for React/Vue/Svelte) ---
export interface ComponentNode extends AstNode {
    kind: 'Component';
    properties?: {
        isExported?: boolean;
        isDefaultExport?: boolean;
    } & Record<string, any>; // Allow other properties
}
⋮----
} & Record<string, any>; // Allow other properties
⋮----
// --- JSX Specific Nodes ---
⋮----
export interface JSXElementNode extends AstNode {
    kind: 'JSXElement';
    properties: {
        tagName: string;
        isSelfClosing: boolean;
    } & Record<string, any>;
}
⋮----
export interface JSXAttributeNode extends AstNode {
    kind: 'JSXAttribute';
    parentId: string; // entityId of the parent JSXElement
    properties: {
        value?: string | boolean | object; // Attribute value can be complex
    } & Record<string, any>;
}
⋮----
parentId: string; // entityId of the parent JSXElement
⋮----
value?: string | boolean | object; // Attribute value can be complex
⋮----
// --- Tailwind Specific Node (Example) ---
// This might be better represented as a property or relationship
// depending on how you want to model Tailwind usage.
export interface TailwindClassNode extends AstNode {
    kind: 'TailwindClass';
    parentId: string; // entityId of the node using the class (e.g., JSXElement)
    properties: {
        className: string;
    } & Record<string, any>;
}
⋮----
parentId: string; // entityId of the node using the class (e.g., JSXElement)
⋮----
// --- C/C++ Specific Nodes ---
⋮----
export interface IncludeDirectiveNode extends AstNode {
    kind: 'IncludeDirective';
    properties: {
        includePath: string;
        isSystemInclude: boolean;
    };
}
⋮----
export interface MacroDefinitionNode extends AstNode {
    kind: 'MacroDefinition';
    properties: {
        value?: string; // Value might be optional or complex
    };
}
⋮----
value?: string; // Value might be optional or complex
⋮----
export interface CFunctionNode extends AstNode {
    kind: 'CFunction';
    language: 'C' | 'C++'; // Can be in C or C++ files
    parentId?: string; // Optional link to struct/namespace entityId if applicable
    // TODO: Add parameters, return type
}
⋮----
language: 'C' | 'C++'; // Can be in C or C++ files
parentId?: string; // Optional link to struct/namespace entityId if applicable
// TODO: Add parameters, return type
⋮----
export interface CppClassNode extends AstNode {
    kind: 'CppClass';
    language: 'C++';
    properties?: {
        // TODO: Add base classes, template parameters
    } & Record<string, any>;
}
⋮----
// TODO: Add base classes, template parameters
⋮----
export interface CppMethodNode extends AstNode {
    kind: 'CppMethod';
    language: 'C++';
    parentId: string; // Link to containing class entityId
    // TODO: Add parameters, return type, modifiers (const, virtual, static)
}
⋮----
parentId: string; // Link to containing class entityId
// TODO: Add parameters, return type, modifiers (const, virtual, static)
⋮----
// --- Java Specific Nodes ---
⋮----
export interface PackageDeclarationNode extends AstNode {
    kind: 'PackageDeclaration';
}
⋮----
export interface ImportDeclarationNode extends AstNode {
    kind: 'ImportDeclaration';
    properties: {
        importPath: string;
        onDemand: boolean; // For wildcard imports like java.util.*
    };
}
⋮----
onDemand: boolean; // For wildcard imports like java.util.*
⋮----
export interface JavaClassNode extends AstNode {
    kind: 'JavaClass';
    language: 'Java';
    properties: {
        qualifiedName: string;
        // TODO: Add modifiers, superclass, interfaces
    };
}
⋮----
// TODO: Add modifiers, superclass, interfaces
⋮----
export interface JavaInterfaceNode extends AstNode {
    kind: 'JavaInterface';
    language: 'Java';
    properties: {
        qualifiedName: string;
        // TODO: Add modifiers, extends list
    };
}
⋮----
// TODO: Add modifiers, extends list
⋮----
export interface JavaMethodNode extends AstNode {
    kind: 'JavaMethod';
    language: 'Java';
    parentId?: string;
    // TODO: Add return type, parameters, modifiers, throws
}
⋮----
// TODO: Add return type, parameters, modifiers, throws
⋮----
export interface JavaFieldNode extends AstNode {
    kind: 'JavaField';
    language: 'Java';
    parentId?: string;
    // TODO: Add type, modifiers
}
⋮----
// TODO: Add type, modifiers
⋮----
export interface JavaEnumNode extends AstNode {
    kind: 'JavaEnum';
    language: 'Java';
    properties: {
        qualifiedName: string;
        // TODO: Add implements list, enum constants
    };
}
⋮----
// TODO: Add implements list, enum constants
⋮----
// --- Go Specific Nodes ---
⋮----
export interface PackageClauseNode extends AstNode {
    kind: 'PackageClause';
    language: 'Go';
}
⋮----
export interface ImportSpecNode extends AstNode {
    kind: 'ImportSpec';
    language: 'Go';
    properties: {
        importPath: string;
        alias?: string;
    };
}
⋮----
export interface GoFunctionNode extends AstNode {
    kind: 'GoFunction';
    language: 'Go';
    properties: {
        qualifiedName: string;
        // TODO: Add parameters, return type
    };
}
⋮----
// TODO: Add parameters, return type
⋮----
export interface GoMethodNode extends AstNode {
    kind: 'GoMethod';
    language: 'Go';
    parentId?: string; // Link to receiver type entityId
    properties: {
        receiverType: string;
        // TODO: Add parameters, return type
    };
}
⋮----
parentId?: string; // Link to receiver type entityId
⋮----
// TODO: Add parameters, return type
⋮----
export interface GoStructNode extends AstNode {
    kind: 'GoStruct';
    language: 'Go';
    properties: {
        qualifiedName: string;
        // TODO: Add fields
    };
}
⋮----
// TODO: Add fields
⋮----
export interface GoInterfaceNode extends AstNode {
    kind: 'GoInterface';
    language: 'Go';
    properties: {
        qualifiedName: string;
        // TODO: Add methods
    };
}
⋮----
// TODO: Add methods
⋮----
export interface TypeAlias extends AstNode { // For Go type aliases
    kind: 'TypeAlias';
    language: 'Go';
    properties: {
        qualifiedName: string;
        aliasedType: string; // Store the underlying type as string for now
    };
}
⋮----
aliasedType: string; // Store the underlying type as string for now
⋮----
// --- C# Specific Nodes ---
⋮----
export interface NamespaceDeclarationNode extends AstNode {
    kind: 'NamespaceDeclaration';
    language: 'C#';
}
⋮----
export interface UsingDirectiveNode extends AstNode {
    kind: 'UsingDirective';
    language: 'C#';
    properties: {
        namespaceOrType: string;
        isStatic: boolean;
        alias?: string;
    };
}
⋮----
export interface CSharpClassNode extends AstNode {
    kind: 'CSharpClass';
    language: 'C#';
    properties: {
        qualifiedName: string;
        // TODO: Add modifiers, base list
    };
}
⋮----
// TODO: Add modifiers, base list
⋮----
export interface CSharpInterfaceNode extends AstNode {
    kind: 'CSharpInterface';
    language: 'C#';
    properties: {
        qualifiedName: string;
        // TODO: Add modifiers, base list
    };
}
⋮----
// TODO: Add modifiers, base list
⋮----
export interface CSharpStructNode extends AstNode {
    kind: 'CSharpStruct';
    language: 'C#';
    properties: {
        qualifiedName: string;
        // TODO: Add modifiers, base list
    };
}
⋮----
// TODO: Add modifiers, base list
⋮----
export interface CSharpMethodNode extends AstNode {
    kind: 'CSharpMethod';
    language: 'C#';
    parentId?: string; // Link to containing class/struct/interface entityId
    // TODO: Add return type, parameters, modifiers
}
⋮----
parentId?: string; // Link to containing class/struct/interface entityId
// TODO: Add return type, parameters, modifiers
⋮----
export interface PropertyNode extends AstNode { // For C# Properties
    kind: 'Property';
    language: 'C#';
    parentId?: string; // Link to containing class/struct/interface entityId
    // TODO: Add type, modifiers, accessors
}
⋮----
parentId?: string; // Link to containing class/struct/interface entityId
// TODO: Add type, modifiers, accessors
⋮----
export interface FieldNode extends AstNode { // For C# Fields
    kind: 'Field';
    language: 'C#';
    parentId?: string; // Link to containing class/struct/interface entityId
    // TODO: Add type, modifiers
}
⋮----
parentId?: string; // Link to containing class/struct/interface entityId
// TODO: Add type, modifiers
⋮----
// --- SQL Specific Nodes ---
⋮----
export interface SQLTableNode extends AstNode {
    kind: 'SQLTable';
    language: 'SQL';
    properties: {
        qualifiedName: string;
        schema?: string | null;
    };
}
⋮----
export interface SQLColumnNode extends AstNode {
    kind: 'SQLColumn';
    language: 'SQL';
    parentId: string; // entityId of the parent table
    properties: {
        dataType: string;
        // TODO: Add constraints (PK, FK, NULL, UNIQUE, DEFAULT)
    };
}
⋮----
parentId: string; // entityId of the parent table
⋮----
// TODO: Add constraints (PK, FK, NULL, UNIQUE, DEFAULT)
⋮----
export interface SQLViewNode extends AstNode {
    kind: 'SQLView';
    language: 'SQL';
    properties: {
        qualifiedName: string;
        schema?: string | null;
        queryText: string; // Store the underlying query
    };
}
⋮----
queryText: string; // Store the underlying query
⋮----
// Base type for different SQL statement kinds
export interface SQLStatementNode extends AstNode {
    kind: 'SQLSelectStatement' | 'SQLInsertStatement' | 'SQLUpdateStatement' | 'SQLDeleteStatement'; // Add other DML/DDL types as needed
    language: 'SQL';
    properties: {
        queryText: string; // Store the full statement text
    };
}
⋮----
kind: 'SQLSelectStatement' | 'SQLInsertStatement' | 'SQLUpdateStatement' | 'SQLDeleteStatement'; // Add other DML/DDL types as needed
⋮----
queryText: string; // Store the full statement text
⋮----
// --- Python Specific Nodes ---
// (Add Python-specific interfaces here if needed, e.g., PythonFunction, PythonClass)
⋮----
// --- TypeScript/JavaScript Specific Nodes ---
// (Add TS/JS-specific interfaces here if needed)
export interface TSFunction extends AstNode {
    kind: 'TSFunction';
    properties?: {
        isExported?: boolean;
        isDefaultExport?: boolean;
        isAsync?: boolean;
    } & Record<string, any>;
}
⋮----
// --- Relationship Types (Examples - can be language-specific) ---
// CALLS, IMPORTS, EXTENDS, IMPLEMENTS, DEFINES_FUNCTION, DEFINES_CLASS, HAS_METHOD, HAS_FIELD, etc.
````

## File: src/cli/analyze.ts
````typescript
import { Command } from 'commander';
import path from 'path';
import { createContextLogger } from '../utils/logger.js';
import { AnalyzerService } from '../analyzer/analyzer-service.js'; // Assuming analyzer-service.ts will be created
import { Neo4jClient } from '../database/neo4j-client.js';
import { SchemaManager } from '../database/schema.js'; // Assuming schema.ts will be created
import config from '../config/index.js';
⋮----
interface AnalyzeOptions {
    extensions?: string;
    ignore?: string; // Commander uses the long option name here
    updateSchema?: boolean;
    resetDb?: boolean; // Commander uses camelCase for flags
    // Add Neo4j connection options
    neo4jUrl?: string;
    neo4jUser?: string;
    neo4jPassword?: string;
    neo4jDatabase?: string;
}
⋮----
ignore?: string; // Commander uses the long option name here
⋮----
resetDb?: boolean; // Commander uses camelCase for flags
// Add Neo4j connection options
⋮----
export function registerAnalyzeCommand(program: Command): void
⋮----
// Define Neo4j connection options
⋮----
// The directory argument received from the MCP server is already absolute.
⋮----
// Pass potential CLI overrides to the Neo4jClient constructor
⋮----
uri: options.neo4jUrl, // Will be undefined if not passed, constructor handles default
⋮----
// 1. Initialize Neo4j Connection
await neo4jClient.initializeDriver('Analyzer'); // Use initializeDriver
⋮----
// 2. Handle Schema and Reset Options
⋮----
// Schema will be applied next anyway
⋮----
await schemaManager.applySchema(true); // Force update if requested or after reset
⋮----
// Optionally apply schema if it doesn't exist, without forcing
// await schemaManager.applySchema(false);
⋮----
// 3. Run Analysis
// AnalyzerService now creates its own Neo4jClient
⋮----
// Use the simplified analyze method
⋮----
process.exitCode = 1; // Indicate failure
⋮----
// 4. Close Neo4j Connection
⋮----
await neo4jClient.closeDriver('Analyzer'); // Use closeDriver
````

## File: src/config/index.ts
````typescript
import dotenv from 'dotenv';
import path from 'path';
⋮----
// Load environment variables from .env file
⋮----
/**
 * Defines the structure of the application configuration.
 */
interface Config {
  /** The logging level (e.g., 'debug', 'info', 'warn', 'error'). */
  logLevel: string;
  /** Neo4j database connection URL. */
  neo4jUrl: string;
  /** Neo4j database username. */
  neo4jUser: string;
  /** Neo4j database password. */
  neo4jPassword: string;
  /** Neo4j database name. */
  neo4jDatabase: string;
  /** Batch size for writing nodes/relationships to Neo4j. */
  storageBatchSize: number;
  /** Directory to store temporary analysis files. */
  tempDir: string;
  /** Glob patterns for files/directories to ignore during scanning. */
  ignorePatterns: string[];
  /** Supported file extensions for parsing. */
  supportedExtensions: string[];
}
⋮----
/** The logging level (e.g., 'debug', 'info', 'warn', 'error'). */
⋮----
/** Neo4j database connection URL. */
⋮----
/** Neo4j database username. */
⋮----
/** Neo4j database password. */
⋮----
/** Neo4j database name. */
⋮----
/** Batch size for writing nodes/relationships to Neo4j. */
⋮----
/** Directory to store temporary analysis files. */
⋮----
/** Glob patterns for files/directories to ignore during scanning. */
⋮----
/** Supported file extensions for parsing. */
⋮----
neo4jPassword: process.env.NEO4J_PASSWORD || 'password', // Replace with your default password
⋮----
'**/.next/**', // Next.js build output
'**/.svelte-kit/**', // SvelteKit build output
'**/.venv/**', // Python virtualenv
'**/venv/**', // Python virtualenv
'**/env/**', // Python virtualenv
'**/__pycache__/**', // Python cache
'**/*.pyc', // Python compiled files
'**/bin/**', // Common build output (e.g., C#)
'**/obj/**', // Common build output (e.g., C#)
'**/*.class', // Java compiled files
'**/target/**', // Java/Maven build output
⋮----
'**/*.test.tsx', // Ignore React test files
'**/*.spec.tsx', // Ignore React spec files
'**/*.test.js',  // Ignore JS test files
'**/*.spec.js',  // Ignore JS spec files
// '**/__tests__/**', // Line removed
'**/playwright-report/**', // Ignore playwright report artifacts
'**/public/**', // Ignore public assets directory
⋮----
'.DS_Store', // macOS specific
⋮----
// Corrected array syntax
'.ts', '.tsx', '.js', '.jsx', // TS/JS/JSX
'.py',                       // Python
'.c', '.h', '.cpp', '.hpp', '.cc', '.hh' // C/C++
, '.java',                   // Java
'.cs',                       // C#
'.go',                       // Go
'.sql'                       // SQL
⋮----
// Basic validation (optional but recommended)
````

## File: src/database/neo4j-client.ts
````typescript
import neo4j, { Driver, Session, Transaction, ManagedTransaction } from 'neo4j-driver';
import config from '../config/index.js';
import { createContextLogger } from '../utils/logger.js';
import { Neo4jError } from '../utils/errors.js'; // Assuming errors.ts will be created
⋮----
/**
 * Manages the connection and interaction with the Neo4j database.
 */
export class Neo4jClient
⋮----
/**
     * Creates an instance of Neo4jClient.
     * @param configOverride - Optional configuration to override defaults from src/config/index.js.
     */
constructor(configOverride?:
⋮----
uri: this.neo4jConfig.uri, // Log URI
username: this.neo4jConfig.username, // Log user
database: this.neo4jConfig.database, // Log db
// Avoid logging password directly
⋮----
// Driver initialization is deferred until first use or explicit call
⋮----
/**
     * Initializes the Neo4j driver instance if it hasn't been already.
     * Verifies connectivity to the database.
     * @param context - Optional context string for logging (e.g., 'Analyzer', 'API').
     * @throws {Neo4jError} If connection fails.
     */
public async initializeDriver(context: string = 'Default'): Promise<void>
⋮----
// Optionally add a connectivity check here even if initialized
⋮----
// Configure driver options if needed (e.g., maxConnectionPoolSize)
⋮----
level: config.logLevel === 'debug' ? 'debug' : 'info', // Map our log level
⋮----
this.driver = null; // Ensure driver is null on failure
⋮----
/**
     * Verifies the connection to the Neo4j database.
     * @param context - Optional context string for logging.
     * @throws {Neo4jError} If verification fails.
     */
private async verifyConnectivity(context: string): Promise<void>
⋮----
// verifyConnectivity checks authentication and connectivity.
⋮----
// Attempt to close the driver if verification fails after initial creation attempt
⋮----
/**
     * Gets the initialized Neo4j driver instance. Initializes it if necessary.
     * @param context - Optional context string for logging.
     * @returns The Neo4j Driver instance.
     * @throws {Neo4jError} If driver initialization fails.
     */
public async getDriver(context: string = 'Default'): Promise<Driver>
⋮----
// We check driver again because initializeDriver could throw
⋮----
/**
     * Gets a Neo4j session for the configured database.
     * Ensures the driver is initialized.
     * @param accessMode - The access mode for the session (READ or WRITE).
     * @param context - Optional context string for logging.
     * @returns A Neo4j Session instance.
     * @throws {Neo4jError} If getting the driver or session fails.
     */
public async getSession(accessMode: 'READ' | 'WRITE' = 'WRITE', context: string = 'Default'): Promise<Session>
⋮----
const driver = await this.getDriver(context); // Ensures driver is initialized
⋮----
/**
     * Executes a Cypher query within a managed transaction.
     * Handles session acquisition and closing automatically.
     *
     * @param cypher - The Cypher query string.
     * @param params - Optional parameters for the query.
     * @param accessMode - 'READ' or 'WRITE'.
     * @param context - Optional context string for logging.
     * @returns The result of the query execution.
     * @throws {Neo4jError} If the transaction fails.
     */
public async runTransaction<T>(
        cypher: string,
        params: Record<string, any> = {},
        accessMode: 'READ' | 'WRITE' = 'WRITE',
        context: string = 'Default'
): Promise<T>
⋮----
const work = async (tx: ManagedTransaction): Promise<T> =>
⋮----
// Often, you might want to process the result records here
// For simplicity, returning the raw result object for now
// You might adapt this to return result.records, summary, etc.
return result as T; // Cast might be needed depending on expected return
⋮----
code: error.code, // Neo4j error code if available
⋮----
// Decide if this should throw or just be logged
⋮----
/**
     * Closes the Neo4j driver connection if it's open.
     * @param context - Optional context string for logging.
     */
public async closeDriver(context: string = 'Default'): Promise<void>
⋮----
// Consider if this should throw an error
⋮----
// Optional: Export a singleton instance if desired for simple use cases
// export const neo4jClient = new Neo4jClient();
````

## File: src/database/schema.ts
````typescript
import { Neo4jClient } from './neo4j-client.js';
import { createContextLogger } from '../utils/logger.js';
import { Neo4jError } from '../utils/errors.js';
⋮----
// Define Node Labels used in the graph
⋮----
'MacroDefinition', // Added MacroDefinition
⋮----
// Added SQL labels
⋮----
// Define Relationship Types used in the graph
⋮----
'CONTAINS',      // Directory->File
'IMPORTS',       // File->File or File->Module (Placeholder)
'EXPORTS',       // File->Variable/Function/Class/Interface/TypeAlias
'CALLS',         // Function/Method->Function/Method
'EXTENDS',       // Class->Class, Interface->Interface
'IMPLEMENTS',    // Class->Interface
'HAS_METHOD',    // Class/Interface->Method
'HAS_PARAMETER', // Function/Method->Parameter
'MUTATES_STATE', // Function/Method->Variable/Property
'HANDLES_ERROR', // TryStatement->CatchClause (or Function/Method)
'DEFINES_COMPONENT', // File->Component
'RENDERS_ELEMENT',   // Component/JSXElement -> JSXElement
'USES_COMPONENT',    // Component -> Component (via JSX tag)
'HAS_PROP',          // JSXElement -> JSXAttribute
'USES_TAILWIND_CLASS', // JSXElement -> TailwindClass
'PYTHON_IMPORTS',          // PythonModule -> PythonModule (placeholder)
'PYTHON_CALLS',            // PythonFunction/PythonMethod -> Unknown (placeholder)
'PYTHON_DEFINES_FUNCTION', // PythonModule/PythonClass -> PythonFunction
'PYTHON_DEFINES_CLASS',    // PythonModule -> PythonClass
'PYTHON_HAS_METHOD',       // PythonClass -> PythonMethod
'PYTHON_HAS_PARAMETER',    // PythonFunction/PythonMethod -> PythonParameter
'INCLUDES',                // C/C++: File -> IncludeDirective (or directly to File in Pass 2)
'DECLARES_PACKAGE',        // Java: File -> PackageDeclaration
'JAVA_IMPORTS',            // Java: File -> ImportDeclaration (or Class/Package)
'HAS_FIELD',               // Java/C#: Class/Interface/Struct -> Field
'DECLARES_NAMESPACE',      // C#: File -> NamespaceDeclaration
'USES_NAMESPACE',          // C#: File -> UsingDirective (or Namespace)
'HAS_PROPERTY',            // C#: Class/Interface/Struct -> Property
'GO_IMPORTS',              // Go: File -> ImportSpec (or Package)
// Added SQL relationship types
'DEFINES_TABLE',           // SQL: Schema/File -> SQLTable
'DEFINES_VIEW',            // SQL: Schema/File -> SQLView
'HAS_COLUMN',              // SQL: Table/View -> SQLColumn
'REFERENCES_TABLE',        // SQL: Statement/View/Function/Procedure -> SQLTable
'REFERENCES_VIEW',         // SQL: Statement/View/Function/Procedure -> SQLView
'CALLS_FUNCTION',          // SQL: Statement/Function/Procedure -> SQLFunction
'CALLS_PROCEDURE'          // SQL: Statement/Function/Procedure -> SQLProcedure
⋮----
// Define relationship types that can cross file boundaries
⋮----
.filter((type): type is string => typeof type === 'string') // Ensure only strings are processed
.filter(type => ['IMPORTS', 'EXPORTS', 'CALLS', 'EXTENDS', 'IMPLEMENTS', 'MUTATES_STATE', 'INCLUDES', 'JAVA_IMPORTS', 'USES_NAMESPACE', 'GO_IMPORTS', 'REFERENCES_TABLE', 'REFERENCES_VIEW', 'CALLS_FUNCTION', 'CALLS_PROCEDURE'].includes(type)) // Added SQL cross-file types
.map(type => `CROSS_FILE_${type}`); // Prefix for clarity in queries if needed
⋮----
// --- Schema Definitions ---
⋮----
// Node Uniqueness Constraints (Crucial for merging nodes correctly)
⋮----
// Indexes for faster lookups (Essential for performance)
⋮----
`CREATE INDEX file_kind_index IF NOT EXISTS FOR (n:File) ON (n.kind)`, // Example
⋮----
/**
 * Manages the application of schema (constraints and indexes) to the Neo4j database.
 */
export class SchemaManager
⋮----
constructor(neo4jClient: Neo4jClient)
⋮----
/**
     * Applies all defined constraints and indexes to the database.
     * @param forceUpdate - If true, drops existing schema elements before applying.
     */
async applySchema(forceUpdate: boolean = false): Promise<void>
⋮----
// Relationship constraints removed for simplicity for now
⋮----
/**
     * Drops all known user-defined constraints and indexes.
     * WARNING: Use with caution.
     */
async dropAllSchemaElements(): Promise<void>
⋮----
// @ts-ignore TODO: Fix type casting from runTransaction
⋮----
// @ts-ignore TODO: Fix type casting from runTransaction
⋮----
/**
     * Deletes all nodes and relationships from the database.
     * WARNING: This is destructive and irreversible.
     */
async resetDatabase(): Promise<void>
````

## File: src/scanner/file-scanner.ts
````typescript
import fsPromises from 'fs/promises';
import { Dirent } from 'fs';
import path from 'path';
import micromatch from 'micromatch'; // For glob pattern matching
import { createContextLogger } from '../utils/logger.js';
import { FileSystemError } from '../utils/errors.js';
import config from '../config/index.js'; // Import config to access default ignore patterns
⋮----
/**
 * Represents basic information about a scanned file.
 */
export interface FileInfo {
    /** Absolute path to the file. */
    path: string;
    /** File name. */
    name: string;
    /** File extension (including the dot). */
    extension: string;
    // Optional: Add size, modified time if needed later
    // size?: number;
    // modifiedTime?: Date;
}
⋮----
/** Absolute path to the file. */
⋮----
/** File name. */
⋮----
/** File extension (including the dot). */
⋮----
// Optional: Add size, modified time if needed later
// size?: number;
// modifiedTime?: Date;
⋮----
/**
 * Scans a directory recursively for files matching specified extensions,
 * respecting ignore patterns.
 */
export class FileScanner
⋮----
private readonly combinedIgnorePatterns: string[]; // Store the final combined list
⋮----
/**
     * Creates an instance of FileScanner.
     * @param targetDirectory - The absolute path to the directory to scan.
     * @param extensions - An array of file extensions to include (e.g., ['.ts', '.js']).
     * @param ignorePatterns - An array of glob patterns to ignore.
     */
constructor(targetDirectory: string, extensions: string[], userIgnorePatterns: string[] = [])
⋮----
// Combine default (from config) and user-provided ignore patterns
⋮----
// --- Fix: Prevent ignoring fixtures when scanning within __tests__ ---
// This logic might be redundant now with the simplified isIgnored, but keep for clarity
⋮----
// console.log('[FileScanner Diag] Scanning within __tests__, filtering out **/__tests__/** ignore pattern.'); // Removed log
⋮----
// --- End Fix ---
⋮----
// console.log('[FileScanner Diag] Final Combined Ignore Patterns:', this.combinedIgnorePatterns); // Removed log
⋮----
/**
     * Performs the recursive file scan.
     * @returns A promise that resolves to an array of FileInfo objects.
     * @throws {FileSystemError} If the target directory cannot be accessed.
     */
async scan(): Promise<FileInfo[]>
⋮----
/**
     * Recursive helper function to scan directories.
     */
private async scanDirectoryRecursive(
        currentPath: string,
        foundFiles: FileInfo[],
        updateScannedCount: (count: number) => void,
        updateErrorCount: (count: number) => void,
        currentScannedCount: number = 0,
        currentErrorCount: number = 0
): Promise<void>
⋮----
// console.log(`[FileScanner Diag] Entering scanDirectoryRecursive for path: ${currentPath}`); // Removed log
⋮----
// --- Restore ignore checks ---
// Check ignore patterns *before* reading directory
⋮----
logger.debug(`Ignoring path (pre-check): ${currentPath}`); // Use logger.debug
⋮----
// --- End restore ---
⋮----
localScannedCount += entries.length; // Count items read in this directory
⋮----
return; // Skip this directory if unreadable
⋮----
// --- Restore ignore checks ---
// Check ignore patterns for each entry
⋮----
logger.debug(`Ignoring path (entry check): ${entryPath}`); // Use logger.debug
⋮----
// --- End restore ---
⋮----
// console.log(`[FileScanner Diag] Checking file: ${entryPath} with extension: ${extension}`); // Removed log
⋮----
// console.log(`[FileScanner Diag] Found matching file: ${entryPath}`); // Removed log
⋮----
path: entryPath.replace(/\\/g, '/'), // Normalize path separators
⋮----
// Ignore other entry types (symlinks, sockets, etc.) for now
⋮----
/**
     * Checks if a given path should be ignored based on configured patterns.
     * Uses micromatch for robust glob pattern matching.
     * @param filePath - Absolute path to check.
     * @returns True if the path should be ignored, false otherwise.
     */
private isIgnored(filePath: string): boolean
⋮----
// --- Restore original logic ---
// Normalize path for consistent matching, especially on Windows
⋮----
// Use the combined list of ignore patterns (now potentially filtered in constructor)
⋮----
// if (isMatch) { // Optional: Log when a path is ignored by patterns
//     logger.debug(`Path ignored by pattern: ${filePath} (Normalized: ${normalizedPath})`);
// }
⋮----
// --- End restore ---
````

## File: src/utils/errors.ts
````typescript
/**
 * Base class for custom application errors.
 */
export class AppError extends Error
⋮----
public readonly code?: string | number; // Optional code for specific errors
⋮----
constructor(message: string, options:
⋮----
this.name = this.constructor.name; // Set the error name to the class name
⋮----
// Capture stack trace (excluding constructor call)
⋮----
/**
 * Error related to file system operations.
 */
export class FileSystemError extends AppError
⋮----
/**
 * Error related to parsing source code.
 */
export class ParserError extends AppError
⋮----
/**
 * Error related to Neo4j database operations.
 */
export class Neo4jError extends AppError
⋮----
/**
 * Error related to configuration issues.
 */
export class ConfigError extends AppError
⋮----
/**
 * Error for unexpected states or logic failures.
 */
export class InternalError extends AppError
````

## File: src/utils/logger.ts
````typescript
import winston from 'winston';
import path from 'path';
import config from '../config/index.js'; // Assuming config will be created later
⋮----
// Ensure logs directory exists (optional, Winston can create files but not dirs)
// import fs from 'fs';
// if (!fs.existsSync(logsDir)) {
//   fs.mkdirSync(logsDir, { recursive: true });
// }
⋮----
// Custom format for console logging
⋮----
// Include stack trace for errors if available
⋮----
// Include metadata if any exists
⋮----
// Avoid printing empty metadata objects
⋮----
// Custom format for file logging
⋮----
errors({ stack: true }), // Log stack traces
json() // Log in JSON format
⋮----
level: config.logLevel || 'info', // Restore using config level
⋮----
timestamp({ format: 'YYYY-MM-DDTHH:mm:ss.SSSZ' }), // ISO 8601 format
errors({ stack: true }) // Ensure errors format includes stack trace
⋮----
// Console Transport
⋮----
colorize(), // Add colors to console output
consoleFormat // Use the custom console format
⋮----
handleExceptions: true, // Log uncaught exceptions
handleRejections: true, // Log unhandled promise rejections
⋮----
// File Transport - All Logs
⋮----
format: fileFormat, // Use JSON format for files
maxsize: 5242880, // 5MB
⋮----
// File Transport - Error Logs
⋮----
format: fileFormat, // Use JSON format for error file
maxsize: 5242880, // 5MB
⋮----
exitOnError: false, // Do not exit on handled exceptions
⋮----
/**
 * Creates a child logger with a specific context label.
 * @param context - The context label (e.g., 'AstParser', 'Neo4jClient').
 * @returns A child logger instance.
 */
export const createContextLogger = (context: string): winston.Logger =>
⋮----
// Ensure child logger inherits the level set on the parent
⋮----
// Export the main logger instance if needed directly
````

## File: src/utils/ts-helpers.ts
````typescript
import { Node, SyntaxKind, JSDoc, ts } from 'ts-morph';
⋮----
/**
 * Gets the end column number for a node.
 * @param node - The ts-morph Node.
 * @returns The 0-based end column number.
 */
export function getEndColumn(node: Node): number
⋮----
// console.warn(`Error getting end column for node: ${e}`);
return 0; // Fallback
⋮----
/**
 * Determines the visibility (public, private, protected) of a class member.
 * Defaults to 'public' if no explicit modifier is found.
 * @param node - The ts-morph Node (e.g., MethodDeclaration, PropertyDeclaration).
 * @returns The visibility modifier string.
 */
export function getVisibility(node: Node): 'public' | 'private' | 'protected'
⋮----
// Use the correct type guard: Node.isModifierable(...)
⋮----
// Now TypeScript knows 'node' has modifier methods within this block
⋮----
/**
 * Extracts the combined text content from all JSDoc comments associated with a node.
 * @param node - The ts-morph Node.
 * @returns The combined JSDoc text, or an empty string if none found.
 */
export function getJsDocText(node: Node): string
⋮----
// Use the correct type guard: Node.isJSDocable(...)
⋮----
// TypeScript knows 'node' has getJsDocs() here
⋮----
/**
 * Extracts the description part of the first JSDoc comment.
 * @param node The node to extract JSDoc from.
 * @returns The description string or undefined.
 */
export function getJsDocDescription(node: Node): string | undefined
⋮----
// Use the correct type guard: Node.isJSDocable(...)
⋮----
// Add nullish coalescing for safety, although getJsDocs should return empty array if none
⋮----
/**
 * Checks if a node has the 'export' keyword modifier.
 * @param node The node to check.
 * @returns True if the node is exported, false otherwise.
 */
export function isNodeExported(node: Node): boolean
⋮----
// Use the correct type guard: Node.isModifierable(...)
⋮----
// Consider edge cases like `export { name };` if needed later
⋮----
/**
 * Checks if a node has the 'async' keyword modifier.
 * @param node The node to check (e.g., FunctionDeclaration, MethodDeclaration, ArrowFunction).
 * @returns True if the node is async, false otherwise.
 */
export function isNodeAsync(node: Node): boolean
⋮----
/**
 * Checks if a node has the 'static' keyword modifier.
 * @param node The node to check (e.g., MethodDeclaration, PropertyDeclaration).
 * @returns True if the node is static, false otherwise.
 */
export function isNodeStatic(node: Node): boolean
⋮----
// Use the correct type guard: Node.isModifierable(...)
⋮----
/**
 * Safely gets the name of a node, returning a default if none exists.
 * Handles various node types that might have names.
 * @param node The node.
 * @param defaultName The default name to return if the node has no name.
 * @returns The node's name or the default name.
 */
export function getNodeName(node: Node, defaultName: string = 'anonymous'): string
⋮----
// Use specific type guards for nodes known to have names
⋮----
// TypeScript knows these have getName()
⋮----
// Add other types like EnumMember, NamespaceDeclaration if needed
⋮----
/**
 * Safely gets the type text of a node, returning 'any' if resolution fails.
 * @param node The node (e.g., VariableDeclaration, ParameterDeclaration, PropertyDeclaration).
 * @returns The type text or 'any'.
 */
export function getNodeType(node: Node): string
⋮----
// Use specific type guards for nodes known to have types
⋮----
// TypeScript knows these have getType()
⋮----
// console.warn(`Could not get type for node kind ${node.getKindName()}: ${e}`);
⋮----
return 'any'; // Default fallback
⋮----
/**
 * Safely gets the return type text of a function-like node.
 * @param node The function-like node.
 * @returns The return type text or 'any'.
 */
export function getFunctionReturnType(node: Node): string
⋮----
// Use specific type guards for function-like nodes
⋮----
// TypeScript knows these have getReturnType()
⋮----
// console.warn(`Could not get return type for node kind ${node.getKindName()}: ${e}`);
````

## File: src/index.ts
````typescript
import { Command } from 'commander';
import { registerAnalyzeCommand } from './cli/analyze.js';
import { createContextLogger } from './utils/logger.js';
import { AppError } from './utils/errors.js';
// Import package.json to get version (requires appropriate tsconfig settings)
// If using ES Modules, need to handle JSON imports correctly
// Option 1: Assert type (requires "resolveJsonModule": true, "esModuleInterop": true in tsconfig)
// import pkg from '../package.json' assert { type: 'json' };
// Option 2: Read file and parse (more robust)
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
⋮----
// Function to read and parse package.json
function getPackageVersion(): string
⋮----
// Handle ES Module __dirname equivalent
⋮----
// When running from dist/index.js, __dirname is dist. package.json is one level up.
⋮----
const pkgPath = path.resolve(distDir, '../package.json'); // Go up one level from dist
⋮----
async function main()
⋮----
.name('code-analyzer-cli') // Replace with your actual CLI name
⋮----
// Register commands
⋮----
// Register other commands here if needed
⋮----
// Log known application errors gracefully
⋮----
// Avoid logging originalError stack twice if logger already handles it
// originalError: error.originalError instanceof Error ? error.originalError.message : error.originalError
⋮----
// Log unexpected errors
⋮----
// Log non-error exceptions
⋮----
process.exitCode = 1; // Ensure failure exit code
````

## File: .gitignore
````
# Node.js / npm
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
package-lock.json # Optional: Some teams commit this, others don't. Assuming ignore for now.
yarn.lock # If using Yarn

# TypeScript compilation output
dist/
*.tsbuildinfo

# MCP Server specific ignores
mcp-server/node_modules/
mcp-server/dist/
mcp-server/logs/

# Logs
logs/
*.log

# Environment variables
.env
.env.*
!.env.example

# Analysis data (generated, potentially large)
analysis-data/
# If you want to keep the JSON results but ignore temp files:
# analysis-data/temp/

# Operating System generated files
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db

# IDE / Editor specific files
.vscode/
*.suo
*.ntvs*
*.njsproj
*.sln
*.sw?

# Test Results & Coverage
coverage/
junit.xml
````

## File: package.json
````json
{
  "name": "amcp-rebuilt",
  "version": "1.0.0",
  "description": "Codebase analysis tool generating a Neo4j graph",
  "main": "dist/index.js",
  "type": "module",
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "start": "node dist/index.js",
    "dev": "ts-node src/index.ts",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:integration": "vitest run src/__tests__/integration",
    "test:unit": "vitest run src/**/*.spec.ts",
    "lint": "eslint src/**/*.ts",
    "format": "prettier --write \"src/**/*.ts\"",
    "analyze": "npm run build && node dist/index.js analyze --update-schema"
  },
  "keywords": [
    "code-analysis",
    "neo4j",
    "typescript",
    "javascript",
    "ast",
    "static-analysis",
    "codegraph"
  ],
  "author": "AI Assistant Roo",
  "license": "MIT",
  "dependencies": {
    "@alanse/mcp-neo4j-server": "^0.1.1",
    "@modelcontextprotocol/sdk": "^1.8.0",
    "@xenova/transformers": "^2.17.2",
    "chokidar": "^3.5.3",
    "chromadb-client": "^2.1.0",
    "commander": "^11.0.0",
    "dotenv": "^16.3.1",
    "ignore": "^7.0.3",
    "neo4j-driver": "^5.12.0",
    "neo4j-driver-bolt-connection": "^5.28.1",
    "tree-sitter": "^0.22.4",
    "tree-sitter-c": "^0.23.5",
    "tree-sitter-c-sharp": "^0.23.1",
    "tree-sitter-cpp": "^0.23.4",
    "tree-sitter-go": "^0.23.4",
    "tree-sitter-java": "^0.23.5",
    "tree-sitter-sql": "^0.1.0",
    "ts-morph": "^20.0.0",
    "winston": "^3.10.0"
  },
  "devDependencies": {
    "@testcontainers/neo4j": "^10.23.0",
    "@types/commander": "^2.12.0",
    "@types/micromatch": "^4.0.9",
    "@types/node": "^20.17.28",
    "@typescript-eslint/eslint-plugin": "^6.6.0",
    "@typescript-eslint/parser": "^6.6.0",
    "cross-env": "^7.0.3",
    "eslint": "^8.48.0",
    "prettier": "^3.0.3",
    "testcontainers": "^10.23.0",
    "ts-node": "^10.9.2",
    "typescript": "^5.2.2",
    "vitest": "^3.1.1"
  }
}
````

## File: python_parser.py
````python
# python_parser.py
⋮----
# --- Node Visitor ---
class PythonAstVisitor(ast.NodeVisitor)
⋮----
def __init__(self, filepath)
⋮----
# Normalize path immediately in constructor for consistency
⋮----
self.current_func_entity_id = None # Can be function or method
self.module_entity_id = None # Store the module/file entity id
⋮----
def _get_location(self, node)
⋮----
# ast line numbers are 1-based, columns are 0-based
⋮----
# Module node represents the whole file, return default location
⋮----
# Attempt to get standard location attributes
⋮----
# Fallback for nodes that might unexpectedly lack location info
# print(f"DEBUG: Node type {type(node).__name__} lacks location attributes.", file=sys.stderr) # Optional debug
⋮----
def _generate_entity_id(self, kind, qualified_name, line_number=None)
⋮----
# Simple entity ID generation - can be refined
# Use lowercase kind for consistency
# Include line number for kinds prone to name collision within the same file scope
⋮----
unique_qualifier = f"{qualified_name}:{line_number}"
⋮----
unique_qualifier = qualified_name
return f"{kind.lower()}:{self.filepath}:{unique_qualifier}" # Added closing brace
⋮----
def _add_node(self, kind, name, node, parent_id=None, extra_props=None)
⋮----
location = self._get_location(node)
# Generate qualified name based on context (Original simpler logic)
⋮----
qualified_name = f"{self.current_class_name}.{name}"
⋮----
qualified_name = name
⋮----
# Pass line number to entity ID generation for relevant kinds
entity_id = self._generate_entity_id(kind, qualified_name, location['startLine'])
⋮----
node_data = {
⋮----
"filePath": self.filepath, # Use normalized path from constructor
⋮----
# Store module entity id when creating the File node
⋮----
return entity_id # Return entityId for linking relationships
⋮----
def _add_relationship(self, type, source_id, target_id, extra_props=None)
⋮----
# Simple entity ID for relationships
rel_entity_id = f"{type.lower()}:{source_id}:{target_id}"
⋮----
def visit_FunctionDef(self, node)
⋮----
parent_id = None
kind = 'PythonFunction' # Use specific kind
⋮----
kind = 'PythonMethod' # Use specific kind
parent_id = self.current_class_entity_id
⋮----
# Store current func/method ID for parameters
original_parent_func_id = self.current_func_entity_id
func_entity_id = self._add_node(kind, node.name, node, parent_id=parent_id)
⋮----
# Add relationship from class to method
⋮----
# Add relationship from file/module to function
⋮----
# Visit arguments (parameters)
⋮----
param_entity_id = self._add_node('PythonParameter', arg.arg, arg, parent_id=func_entity_id)
⋮----
# Handle *args, **kwargs if needed
⋮----
# Visit function body
⋮----
# Restore parent func ID
⋮----
def visit_AsyncFunctionDef(self, node)
⋮----
# Treat async functions similarly to regular functions for now
self.visit_FunctionDef(node) # Reuse logic, maybe add isAsync property
⋮----
def visit_ClassDef(self, node)
⋮----
original_class_name = self.current_class_name
original_class_entity_id = self.current_class_entity_id
⋮----
# Add relationship from file/module to class
⋮----
# Visit class body (methods, nested classes, etc.)
⋮----
def visit_Import(self, node)
⋮----
# Simple import relationship (Module -> Module Name)
# More complex resolution (finding the actual file) is deferred
target_name = alias.name
target_entity_id = self._generate_entity_id('pythonmodule', target_name) # Placeholder ID for module
# Use the stored module/file entityId as source
# Explicitly create the target module node (placeholder)
self._add_node('PythonModule', target_name, node) # Use import node for location approximation
⋮----
def visit_ImportFrom(self, node)
⋮----
module_name = node.module or '.' # Handle relative imports
# Placeholder ID for the imported module
target_module_entity_id = self._generate_entity_id('pythonmodule', module_name)
# Explicitly create the target module node (placeholder)
self._add_node('PythonModule', module_name, node) # Use import node for location approximation
# Use the stored module/file entityId as source
⋮----
imported_names = []
⋮----
# Could potentially create relationships for specific imported items later
⋮----
def visit_Assign(self, node)
⋮----
# Basic variable assignment detection
# More complex assignments (tuples, etc.) require more logic
⋮----
# Determine parent scope (function, method, class, or module)
parent_scope_id = self.current_func_entity_id or self.current_class_entity_id or self.module_entity_id
if parent_scope_id: # Ensure parent scope exists
⋮----
self.generic_visit(node) # Visit the value being assigned
⋮----
def visit_Call(self, node)
⋮----
# Basic call detection
func_name = None
if isinstance(node.func, ast.Name): # Direct function call like my_func()
func_name = node.func.id
elif isinstance(node.func, ast.Attribute): # Method call like obj.method() or Class.method()
# Try to reconstruct the full call name (e.g., 'self.method', 'ClassName.static_method')
# This is complex and requires symbol resolution beyond basic AST walking
# For now, just use the attribute name
func_name = node.func.attr
⋮----
# Capture calls from module level as well
source_entity_id = self.current_func_entity_id or self.module_entity_id
⋮----
# Target ID is tricky without resolution - use a placeholder based on name
# Use 'pythonfunction' as a placeholder kind instead of 'unknown'
target_entity_id = self._generate_entity_id('pythonfunction', func_name)
⋮----
self.generic_visit(node) # Visit arguments
⋮----
# --- Main Execution ---
⋮----
filepath_arg = sys.argv[1]
# Normalize the path within Python using os.path.abspath
filepath = os.path.abspath(filepath_arg)
# print(f"DEBUG: Received path: '{filepath_arg}', Absolute path: '{filepath}'", file=sys.stderr) # Keep debug if needed
⋮----
# Use the normalized, absolute path
⋮----
content = f.read()
tree = ast.parse(content, filename=filepath)
⋮----
# Pass the normalized, absolute path to the visitor
visitor = PythonAstVisitor(filepath)
# Add the File node itself using the correct kind
visitor._add_node('File', os.path.basename(filepath), tree) # Use 'File' kind
⋮----
result = {
⋮----
"filePath": visitor.filepath, # Already normalized in visitor
⋮----
print(json.dumps(result, indent=2)) # Output JSON to stdout
⋮----
# Use the normalized, absolute path in the error message
````

## File: run_neo4j_server.sh
````bash
#!/bin/bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USERNAME="neo4j"
export NEO4J_PASSWORD="test@123"
export NEO4J_DATABASE="codegraph"

# Execute the actual server script
node ./node_modules/@alanse/mcp-neo4j-server/build/server.js
````

## File: tsconfig.json
````json
{
  "compilerOptions": {
    /* Base Options: */
    "esModuleInterop": true,
    "skipLibCheck": true,
    "target": "ES2022",
    "allowJs": true,
    "resolveJsonModule": true,
    "moduleDetection": "force",
    "isolatedModules": true,
    /* Strictness */
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    /* If NOT transpiling with TypeScript: */
    "moduleResolution": "NodeNext",
    "module": "NodeNext", // Changed from ES2022 to NodeNext
    "noEmit": false, // Allow emitting compiled files
    /* If your code runs in the DOM: */
    "lib": ["es2022", "dom", "dom.iterable"],
    /* If your code doesn't run in the DOM: */
    // "lib": ["es2022"],
    /* If you're building for a library: */
    // "declaration": true,
    /* If you're building for a library in a monorepo: */
    // "composite": true,
    // "sourceMap": true,
    // "declarationMap": true,
    /* If you're using framework features: */
    "jsx": "react-jsx", // Example for React
    /* Project Structure */
    "rootDir": "./src", // Specify root directory of source files
    "outDir": "./dist", // Specify output directory for compiled files
    "baseUrl": ".", // Base directory for non-relative module resolution
    "paths": { // Optional: Define path mappings
      "@/*": ["src/*"]
    },
    "typeRoots": ["./node_modules/@types", "./src/types"] // Include custom types
  },
  "include": ["src/**/*.ts", "src/**/*.tsx", "src/**/*.js", "src/**/*.jsx"], // Include all relevant files in src
  "exclude": ["node_modules", "dist", "**/__tests__/**", "**/*.spec.ts", "**/*.test.ts"] // Exclude build output, tests, etc.
}
````

## File: README.md
````markdown
# CodeGraph Analyzer: The Universal Code Intelligence Platform

<div align="center">

[![GitHub stars](https://img.shields.io/github/stars/ChrisRoyse/CodeGraph.svg?style=social&label=Star&maxAge=2592000)](https://github.com/ChrisRoyse/CodeGraph/stargazers/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Neo4j Compatible](https://img.shields.io/badge/Neo4j-Compatible-brightgreen.svg)](https://neo4j.com/)
[![TypeScript](https://img.shields.io/badge/TypeScript-4.9+-blue.svg)](https://www.typescriptlang.org/)

**Revolutionize how you understand, visualize, and interact with your multi-language codebase**

<a href="https://paypal.me/ChrisRoyseAI" target="_blank">
  <img src="https://img.shields.io/badge/SUPPORT_THIS_PROJECT-00457C?style=for-the-badge&logo=paypal&logoColor=white" alt="Support This Project" width="300"/>
</a>

</div>

## 📋 Overview

**CodeGraph Analyzer** is a powerful static analysis engine that transforms your codebase into a rich, queryable Neo4j graph database. It now supports **multiple programming languages and frameworks**, creating a comprehensive "digital twin" of your entire software ecosystem. This enables unprecedented code comprehension, visualization, and AI-driven development workflows across complex, multi-language projects.

## 🌟 What's New: Multi-Language Support

CodeGraph Analyzer now provides robust support for a wide spectrum of programming languages and frameworks:

### Programming Languages
- **TypeScript/JavaScript** - Full support for modern TS/JS features with ts-morph
- **Python** - Complete parsing via Python's native AST module
- **Java** - Advanced analysis using tree-sitter-java
- **C#** - Comprehensive parsing with tree-sitter-c-sharp
- **C/C++** - Detailed analysis of headers, includes, and implementation
- **Go** - Complete structure and package relationship mapping
- **SQL** - Table, view, and query analysis from SQL files
- **HTML/CSS** - Structure and style mapping

### Frameworks & Technologies
- **React/Preact** - Component hierarchies, JSX elements, prop mapping
- **Tailwind CSS** - Class usage and relationships
- **Supabase** - Database schema and API relationships
- **Deno** - Module, import, and runtime analysis

## 🚀 Key Features

- **Cross-Language Analysis**: Analyze relationships between different languages in the same project
- **Comprehensive Scanning**: Intelligently identifies supported file types across your entire project
- **Two-Pass Analysis**: First builds detailed ASTs for each file, then resolves complex cross-file relationships
- **Rich Element Identification**: Extracts files, directories, classes, interfaces, functions, methods, variables, parameters, type aliases, components, SQL tables, and more
- **Relationship Mapping**: Maps IMPORTS, EXPORTS, CALLS, EXTENDS, IMPLEMENTS, HAS_METHOD, RENDERS_ELEMENT, USES_COMPONENT, REFERENCES_TABLE, and many others
- **Neo4j Integration**: Creates a queryable knowledge graph with optimized schema management
- **MCP Integration**: Works seamlessly with Model Context Protocol for AI-powered codebase interaction

## 🔍 Why Multi-Language Support Matters

Modern software development rarely happens in a single language. The expanded language support in CodeGraph Analyzer addresses critical challenges:

- **Unified View**: See your entire tech stack as a coherent system instead of isolated silos
- **Cross-Language Dependencies**: Trace relationships between frontend and backend components (e.g., React components calling Python APIs)
- **Microservice Architecture**: Understand service boundaries and communication patterns across different languages
- **Multi-Team Collaboration**: Enable specialists in different languages to see how their code impacts the broader system
- **Legacy Integration**: Map connections between newer and older components written in different languages
- **Complete AI Context**: Give AI assistants holistic understanding of your entire codebase regardless of language

## 📈 Visualize, Understand, and Talk to Your Entire Codebase

With CodeGraph Analyzer, you can:

- **Navigate Complex Systems**: Easily explore relationships across language boundaries
- **Perform Intelligent Refactoring**: Understand the full impact of changes across your tech stack
- **Onboard Developers Faster**: Help new team members grasp the architecture regardless of their language expertise
- **Empower AI Assistance**: Enable AI tools to understand your codebase at a deeper level
- **Document Automatically**: Generate architecture diagrams that span language boundaries
- **Ensure Architectural Compliance**: Verify cross-language dependencies adhere to your design principles

## 🧠 The Power of Neo4j MCP: Natural Language → Code Understanding

The true breakthrough of CodeGraph isn't just in what languages it parses, but in how it enables AI to **truly understand your code** through the Model Context Protocol (MCP) integration with Neo4j.

### How It Works: The Neural Bridge Between Human, AI, and Code

1. **Natural Language → Cypher Translation**: When you ask your AI assistant a question about your codebase ("How does the login system work?"), the Neo4j MCP tools automatically translate this into optimized Cypher queries.

2. **Knowledge Graph Traversal**: These queries intelligently navigate the comprehensive code graph that CodeGraph has built, finding exactly the code relationships that answer your question.

3. **Contextual Understanding**: The AI receives the precise code context it needs - not just individual files, but the actual relationships, dependencies, and structures that connect them.

4. **Intelligent Response**: With this deep structural understanding, the AI can provide accurate, contextualized answers and generate code that respects your existing architecture.

### Why This Matters: Unprecedented AI Capabilities

- **Beyond Text Understanding**: AI no longer just reads code as text - it sees the actual structure and relationships between components
  
- **True Code Comprehension**: AI assistants can "see" how your Python backend connects to your React frontend, how data flows through your system, and what would break if you changed a specific function

- **Architectural Awareness**: Generate code that respects your existing patterns and integrates properly with your architecture, without breaking hidden dependencies

- **Intelligent Refactoring**: AI can confidently recommend refactoring across language boundaries, understanding the full impact of changes

- **Complexity Navigation**: Handle questions about massive codebases no human could fully keep in their head ("Show me all places where user data is accessed across our entire stack")

### Example Queries That Become Possible

```
"Show me all React components that fetch data from our Python API endpoints"

"Which SQL queries modify the user table and what services call them?"

"How does data flow from our frontend form to the database?"

"What would break if I changed the return type of this C++ function?"

"Generate a new endpoint that follows our existing API patterns"
```

Each of these questions is automatically translated to precise Cypher queries, enabling your AI assistant to provide accurate, contextual responses based on your actual codebase architecture - not just guesswork.

## 🔄 Neo4j MCP Integration: The Technical Details

### The Complete AI-Codebase Intelligence Stack

CodeGraph Analyzer works together with two critical MCP components to create a complete code understanding system:
- **GitHub Repository**: [https://github.com/neo4j-contrib/mcp-neo4j](https://github.com/neo4j-contrib/mcp-neo4j)

1. **code-analyzer-mcp**: This MCP server provides AI assistants with the ability to:
   - Trigger codebase analysis on demand
   - Watch for code changes to keep the knowledge graph updated
   - Customize analysis parameters without requiring technical knowledge

2. **github.com/neo4j-contrib/mcp-neo4j**: This powerful MCP server is the bridge between natural language and code knowledge, providing:
   - **read-neo4j-cypher**: Translates natural questions into Cypher queries that extract precisely the right information
   - **write-neo4j-cypher**: Enables AI to update the knowledge graph as needed
   - **get-neo4j-schema**: Allows AI to understand the structure of your code graph

### Simplified Setup with Integrated Configuration

The CodeGraph setup package includes pre-configured MCP settings for both servers, enabling seamless integration with AI assistants. A typical configuration looks like:

```json
{
  "mcpServers": {
    "github.com/neo4j-contrib/mcp-neo4j": {
      "command": "mcp-neo4j-cypher",
      "args": [
        "--db-url",
        "bolt://localhost:7687?database=codegraph",
        "--username",
        "neo4j",
        "--password",
        "test1234"
      ],
      "disabled": false,
      "autoApprove": [
        "read-neo4j-cypher",
        "write-neo4j-cypher",
        "get-neo4j-schema"
      ]
    },
    "code-analyzer-mcp": {
      "command": "node",
      "args": [
        "c:/code/amcp/mcp/dist/index.js"
      ],
      "cwd": "c:/code/amcp/mcp",
      "disabled": false,
      "alwaysAllow": [
        "run_analyzer",
        "start_watcher",
        "stop_watcher"
      ]
    }
  }
}
```

## 🛠️ Installation and Prerequisites

### Prerequisites
- **Neo4j Database**: Tested with Neo4j Desktop v5.26.4 (Community or Enterprise)
- **Neo4j Plugins** (Recommended):
  - APOC Core
  - Graph Data Science (GDS) Library
- **Node.js & npm**: Latest LTS version
- **Python 3**: For Python code analysis (accessible in your PATH)

### Installation Options

#### Option 1: Easiest Setup (Recommended)
1. **Download**: Get the pre-packaged zip file containing the analyzer and necessary configurations
   
   [📦 Download CodeGraph_Setup.zip](https://drive.google.com/file/d/1lc9qrupxXHaBzWlTFwcjClM8ygPsmH4Y/view?usp=sharing)

2. **Unzip**: Extract the contents to `C:\code\amcp\` (or your preferred location)
3. **Configure MCP**: Set up your MCP servers
4. **Start Neo4j**: Ensure your Neo4j instance is running
5. **Run Analysis**: Use the code-analyzer-mcp tool via your AI assistant

#### Option 2: Manual Setup (from GitHub)
1. **Clone the Repository**:
   ```bash
   git clone https://github.com/ChrisRoyse/CodeGraph.git amcp
   cd amcp
   ```

2. **Install Dependencies**:
   ```bash
   npm install
   ```

3. **Compile TypeScript**:
   ```bash
   npm run build
   ```

4. **Configure Environment**: Create a `.env` file for Neo4j credentials
5. **Configure MCP**: Set up your MCP servers
6. **Start Neo4j**: Ensure your Neo4j instance is running
7. **Run Analysis**: Use the CLI directly or the code-analyzer-mcp tool

## 📊 Usage (CLI)

```bash
# Navigate to the project directory
cd c:/code/amcp

# Run the analyzer (using compiled code in dist/)
# Replace <path/to/your/codebase> with the actual path
node dist/index.js analyze <path/to/your/codebase> [options]

# Example: Analyze a multi-language project with specific extensions
node dist/index.js analyze . -e .ts,.py,.java,.cs,.go,.sql,.jsx,.tsx --reset-db --update-schema

# Example: Analyze a different project, ignoring node_modules and dist
node dist/index.js analyze ../my-other-project --ignore "**/node_modules/**,**/dist/**"
```

### Options:
- `<directory>`: Required: Path to the directory to analyze
- `-e, --extensions <exts>`: Comma-separated file extensions (default now includes all supported languages)
- `-i, --ignore <patterns>`: Comma-separated glob patterns to ignore
- `--update-schema`: Force update Neo4j schema (constraints/indexes)
- `--reset-db`: WARNING: Deletes ALL data in the target Neo4j DB before analysis
- `--neo4j-url <url>`: Neo4j connection URL (overrides .env)
- `--neo4j-user <user>`: Neo4j username (overrides .env)
- `--neo4j-password <password>`: Neo4j password (overrides .env)
- `--neo4j-database <database>`: Neo4j database name (overrides .env)
- `-h, --help`: Display help information
- `-v, --version`: Display version information

## 🔮 Powering the Next Generation of AI-Assisted Development

The expanded language support in CodeGraph Analyzer enables entirely new possibilities for AI-assisted development:

- **Truly Context-Aware AI**: Instead of guessing, AI assistants can query the graph to understand exactly how components interact across language boundaries
- **Natural Language Queries**: Ask questions like "Show me all React components that fetch data from Python APIs" or "Find SQL queries that affect the user profile table"
- **Precise, Cross-Language Refactoring**: AI can confidently refactor code, knowing it has identified ALL relevant locations through graph traversal, even across language boundaries
- **Architectural Adherence**: AI can generate new code that aligns with existing patterns and structures by querying the graph for examples, regardless of implementation language

## 🌐 Future Roadmap

We're continuing to expand CodeGraph Analyzer's capabilities:

- **Additional Language Support**: Rust, Ruby, PHP, and more
- **Deeper Semantic Analysis**: Data flow analysis and taint tracking
- **Enhanced AI Integrations**: Advanced MCP tools for tasks like automated testing and security analysis
- **Rich Visualization Tools**: Interactive visual exploration of the code graph

## 🤝 Support & Contribution

This is an open-source project under the MIT License.

<div align="center">
  <h2>⭐ SUPPORT CODEGRAPH ⭐</h2>
  <p><b>Help fund continued development and new features!</b></p>
  
  <a href="https://paypal.me/ChrisRoyseAI" target="_blank">
    <img src="https://img.shields.io/badge/DONATE_NOW-00457C?style=for-the-badge&logo=paypal&logoColor=white" alt="Donate Now" width="300"/>
  </a>
  
  <h3>❤️ Your support makes a huge difference! ❤️</h3>
  <p>CodeGraph is maintained by a single developer<br>Every donation directly helps improve the tool</p>
</div>

Contributions (bug reports, feature requests, pull requests) are welcome on the [GitHub Repository](https://github.com/ChrisRoyse/CodeGraph).

---

## 🔄 Supported Languages & Key Parsers

- **TypeScript/JavaScript/TSX/JSX:** `ts-morph`
- **Python:** Python script using Python's built-in `ast` module
- **Java:** `tree-sitter-java`
- **C#:** `tree-sitter-c-sharp`
- **Go:** `tree-sitter-go`
- **C/C++:** `tree-sitter-c`, `tree-sitter-cpp`
- **SQL:** `tree-sitter-sql`
- **HTML/CSS:** Specialized parsers

---

Unlock the complete structure within your polyglot codebase. Start graphing today!
````
