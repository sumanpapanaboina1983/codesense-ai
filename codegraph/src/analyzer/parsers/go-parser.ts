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
import { AstNode, RelationshipInfo, SingleFileParseResult, InstanceCounter, PackageClauseNode, ImportSpecNode, GoFunctionNode, GoMethodNode, GoStructNode, GoInterfaceNode, MethodSignature, ParameterInfo, generateShortSignature, DocTag, DocumentationInfo } from '../types.js';
import { ensureTempDir, getTempFilePath, generateInstanceId, generateEntityId } from '../parser-utils.js';

const logger = createContextLogger('GoParser');

// Helper to get node text safely
function getNodeText(node: Parser.SyntaxNode | null | undefined): string {
    return node?.text ?? '';
}

// Helper to get location
function getNodeLocation(node: Parser.SyntaxNode): { startLine: number, endLine: number, startColumn: number, endColumn: number } {
    return {
        startLine: node.startPosition.row + 1, endLine: node.endPosition.row + 1,
        startColumn: node.startPosition.column, endColumn: node.endPosition.column,
    };
}

/**
 * Extract Go doc comments preceding a declaration node.
 * In Go, doc comments are // comments immediately before the declaration.
 */
function extractGoDocComment(node: Parser.SyntaxNode, sourceText: string): { rawComment: string; description: string } | null {
    // Get all previous siblings that are comments
    const comments: string[] = [];
    let prevSibling = node.previousSibling;

    while (prevSibling) {
        if (prevSibling.type === 'comment') {
            const commentText = getNodeText(prevSibling);
            // Check if it's a // comment (not a /* */ block comment)
            if (commentText.startsWith('//')) {
                // Check if the comment is on the line immediately before
                const commentEndLine = prevSibling.endPosition.row;
                const nextNodeStartLine = prevSibling.nextSibling?.startPosition.row ?? node.startPosition.row;

                // Only include if there's no blank line between comments
                if (nextNodeStartLine - commentEndLine <= 1) {
                    // Remove the // prefix and trim
                    const cleanComment = commentText.replace(/^\/\/\s?/, '').trim();
                    comments.unshift(cleanComment); // Add to beginning
                    prevSibling = prevSibling.previousSibling;
                    continue;
                }
            }
        }
        break;
    }

    if (comments.length === 0) {
        return null;
    }

    const rawComment = comments.map(c => `// ${c}`).join('\n');
    const description = comments.join(' ');

    return { rawComment, description };
}

/**
 * Parse Go doc comment tags.
 * Go doesn't have formal tags like JSDoc, but common patterns include:
 * - Deprecated: starts with "Deprecated:"
 * - TODO/FIXME comments
 * - Parameter references in the form "paramName is the..."
 */
function parseGoDocTags(docComment: string): DocTag[] {
    const tags: DocTag[] = [];

    if (!docComment) {
        return tags;
    }

    // Check for Deprecated marker
    if (docComment.toLowerCase().includes('deprecated')) {
        const deprecatedMatch = docComment.match(/deprecated:?\s*(.*)$/im);
        tags.push({
            tag: 'deprecated',
            description: deprecatedMatch?.[1]?.trim() || 'This function is deprecated',
        });
    }

    // Check for TODO
    const todoMatch = docComment.match(/TODO:?\s*(.+?)(?:\n|$)/i);
    if (todoMatch) {
        tags.push({
            tag: 'todo',
            description: todoMatch[1].trim(),
        });
    }

    // Check for FIXME
    const fixmeMatch = docComment.match(/FIXME:?\s*(.+?)(?:\n|$)/i);
    if (fixmeMatch) {
        tags.push({
            tag: 'fixme',
            description: fixmeMatch[1].trim(),
        });
    }

    // Check for Example marker (Go convention)
    if (docComment.toLowerCase().includes('example')) {
        const exampleMatch = docComment.match(/example:?\s*(.+?)(?:\n|$)/i);
        if (exampleMatch) {
            tags.push({
                tag: 'example',
                description: exampleMatch[1].trim(),
            });
        }
    }

    // Check for See also
    const seeMatch = docComment.match(/see\s+(?:also\s+)?(\S+)/i);
    if (seeMatch) {
        tags.push({
            tag: 'see',
            description: seeMatch[1].trim(),
        });
    }

    return tags;
}

/**
 * Extract complete documentation info from a Go node.
 */
function extractGoDocumentationInfo(node: Parser.SyntaxNode, sourceText: string): DocumentationInfo | undefined {
    const docComment = extractGoDocComment(node, sourceText);
    if (!docComment) {
        return undefined;
    }

    const tags = parseGoDocTags(docComment.description);

    // Extract specific metadata from tags
    const isDeprecated = tags.some(t => t.tag === 'deprecated');
    const deprecationReason = tags.find(t => t.tag === 'deprecated')?.description;
    const seeAlso = tags.filter(t => t.tag === 'see').map(t => t.description).filter(Boolean) as string[];

    return {
        summary: docComment.description,
        rawComment: docComment.rawComment,
        tags,
        format: 'godoc',
        isDeprecated: isDeprecated || undefined,
        deprecationReason,
        seeAlso: seeAlso.length > 0 ? seeAlso : undefined,
    };
}

/**
 * Extract parameters from a Go function/method declaration.
 * Go parameter format: func foo(a int, b, c string, d ...int)
 */
function extractGoParameters(node: Parser.SyntaxNode): ParameterInfo[] {
    const parameters: ParameterInfo[] = [];
    const paramsNode = node.childForFieldName('parameters');
    if (!paramsNode) return parameters;

    let position = 0;

    // Go groups parameters with same type: (a, b int, c string)
    // Each parameter_declaration contains names and a type
    for (const paramDecl of paramsNode.namedChildren) {
        if (paramDecl.type === 'parameter_declaration') {
            // Get the type (last child is usually the type)
            const typeNode = paramDecl.childForFieldName('type');
            let paramType = getNodeText(typeNode) || 'any';
            let isVariadic = false;

            // Check for variadic parameter (... prefix on type)
            if (paramDecl.namedChildren.some(c => c.type === 'variadic_parameter_declaration')) {
                isVariadic = true;
            }
            // Also check if the type starts with ...
            if (paramType.startsWith('...')) {
                isVariadic = true;
                paramType = paramType.substring(3);
            }

            // Get all names in this declaration
            const names: string[] = [];
            for (const child of paramDecl.namedChildren) {
                if (child.type === 'identifier') {
                    names.push(getNodeText(child));
                }
            }

            // If no names found but there's a type, it's an unnamed parameter
            if (names.length === 0) {
                parameters.push({
                    name: `_${position}`,
                    type: paramType,
                    isOptional: false,
                    isVariadic,
                    position,
                });
                position++;
            } else {
                // Create a parameter entry for each name
                for (const name of names) {
                    parameters.push({
                        name,
                        type: paramType,
                        isOptional: false,
                        isVariadic: isVariadic && name === names[names.length - 1], // Only last can be variadic
                        position,
                    });
                    position++;
                }
            }
        } else if (paramDecl.type === 'variadic_parameter_declaration') {
            // Handle explicit variadic: func foo(args ...int)
            const typeNode = paramDecl.childForFieldName('type');
            const nameNode = paramDecl.childForFieldName('name');
            parameters.push({
                name: getNodeText(nameNode) || `_${position}`,
                type: getNodeText(typeNode) || 'any',
                isOptional: false,
                isVariadic: true,
                position,
            });
            position++;
        }
    }

    return parameters;
}

/**
 * Extract return types from a Go function/method declaration.
 * Go can have multiple return values: func foo() (int, error)
 */
function extractGoReturnTypes(node: Parser.SyntaxNode): string[] {
    const returnTypes: string[] = [];
    const resultNode = node.childForFieldName('result');

    if (!resultNode) {
        return []; // No return type (void equivalent)
    }

    // Could be a single type or a parameter_list (multiple returns)
    if (resultNode.type === 'parameter_list') {
        // Multiple returns: (int, error) or (result int, err error)
        for (const child of resultNode.namedChildren) {
            if (child.type === 'parameter_declaration') {
                const typeNode = child.childForFieldName('type');
                if (typeNode) {
                    returnTypes.push(getNodeText(typeNode));
                }
            } else {
                // Direct type in the list
                returnTypes.push(getNodeText(child));
            }
        }
    } else {
        // Single return type
        returnTypes.push(getNodeText(resultNode));
    }

    return returnTypes;
}

/**
 * Extract receiver info from a Go method declaration.
 */
function extractGoReceiver(node: Parser.SyntaxNode): { receiverType: string; isPointer: boolean; receiverName: string } | null {
    const receiverNode = node.childForFieldName('receiver');
    if (!receiverNode) return null;

    const paramDecl = receiverNode.namedChild(0);
    if (!paramDecl) return null;

    const typeNode = paramDecl.childForFieldName('type');
    let receiverType = getNodeText(typeNode) || '';
    let isPointer = false;

    // Check if it's a pointer receiver (*Type)
    if (receiverType.startsWith('*')) {
        isPointer = true;
        receiverType = receiverType.substring(1);
    }

    // Get receiver name (e.g., 'r' in func (r *Repository))
    const nameNode = paramDecl.namedChildren.find(c => c.type === 'identifier');
    const receiverName = getNodeText(nameNode) || 'r';

    return { receiverType, isPointer, receiverName };
}

/**
 * Build a MethodSignature for a Go function/method.
 */
function buildGoFunctionSignature(
    name: string,
    node: Parser.SyntaxNode,
    isMethod: boolean = false,
    receiverInfo?: { receiverType: string; isPointer: boolean; receiverName: string } | null
): MethodSignature {
    const parameters = extractGoParameters(node);
    const returnTypes = extractGoReturnTypes(node);

    // Format return type string
    let returnTypeStr = 'void';
    if (returnTypes.length === 1) {
        returnTypeStr = returnTypes[0];
    } else if (returnTypes.length > 1) {
        returnTypeStr = `(${returnTypes.join(', ')})`;
    }

    const signature: MethodSignature = {
        signature: '', // Will be generated below
        shortSignature: generateShortSignature(name, parameters),
        returnType: returnTypeStr,
        returnsVoid: returnTypes.length === 0,
        returnTypes: returnTypes.length > 0 ? returnTypes : undefined,
        parameters,
        parameterCount: parameters.length,
        visibility: name[0] === name[0].toUpperCase() ? 'public' : 'private', // Go convention: Uppercase = exported
        modifiers: [],
        isStatic: !isMethod, // Functions are "static", methods are not
        isAsync: false, // Go doesn't have async keyword (uses goroutines)
        isAbstract: false,
        isFinal: false,
        isConstructor: false,
        receiverType: receiverInfo?.receiverType,
        isPointerReceiver: receiverInfo?.isPointer,
    };

    // Generate signature string
    const paramStr = parameters.map(p => `${p.name} ${p.isVariadic ? '...' : ''}${p.type}`).join(', ');
    if (isMethod && receiverInfo) {
        const ptr = receiverInfo.isPointer ? '*' : '';
        signature.signature = `func (${receiverInfo.receiverName} ${ptr}${receiverInfo.receiverType}) ${name}(${paramStr}) ${returnTypeStr}`;
    } else {
        signature.signature = `func ${name}(${paramStr}) ${returnTypeStr}`;
    }

    // Trim trailing "void" for cleaner display
    if (signature.returnsVoid) {
        signature.signature = signature.signature.replace(/ void$/, '');
    }

    return signature;
}

// --- Tree-sitter Visitor ---
class GoAstVisitor {
    public nodes: AstNode[] = [];
    public relationships: RelationshipInfo[] = [];
    private instanceCounter: InstanceCounter = { count: 0 };
    private fileNode: AstNode;
    private now: string = new Date().toISOString();
    private currentPackage: string | null = null;
    private currentReceiverType: string | null = null; // For methods

    constructor(private filepath: string, private sourceText: string) {
        const filename = path.basename(filepath);
        const fileEntityId = generateEntityId('file', filepath);
        this.fileNode = {
            id: generateInstanceId(this.instanceCounter, 'file', filename),
            entityId: fileEntityId, kind: 'File', name: filename, filePath: filepath,
            startLine: 1, endLine: 0, startColumn: 0, endColumn: 0,
            language: 'Go', createdAt: this.now,
        };
        this.nodes.push(this.fileNode);
    }

    // Corrected visit method: process node, then always recurse unless stopped
    visit(node: Parser.SyntaxNode) {
        const stopRecursion = this.visitNode(node); // Process the current node first

        if (!stopRecursion) { // Only recurse if the handler didn't stop it
            for (const child of node.namedChildren) {
                this.visit(child);
            }
        }

        if (node.type === 'source_file') { // Root node type for Go
             this.fileNode.endLine = node.endPosition.row + 1;
             this.fileNode.loc = this.fileNode.endLine;
        }
    }

    // Helper to decide if recursion should stop for certain node types
    private shouldStopRecursion(node: Parser.SyntaxNode): boolean {
        // Stop recursion after handling the entire import block here
        return node.type === 'import_declaration';
    }

    private visitNode(node: Parser.SyntaxNode): boolean {
        try {
            switch (node.type) {
                case 'package_clause':
                    this.visitPackageClause(node);
                    return false;
                case 'import_declaration':
                    this.visitImportDeclaration(node);
                    return true; // Stop recursion for imports here
                // case 'import_spec': // Removed - handled by visitImportDeclaration
                //     break;
                case 'function_declaration':
                    this.visitFunctionDeclaration(node);
                    return false;
                case 'method_declaration':
                    this.visitMethodDeclaration(node);
                    return false;
                case 'type_alias':
                case 'type_spec': // Handle type specs (like structs) which might not be definitions
                case 'type_definition':
                    this.visitTypeDefinition(node);
                    return false;
                // Removed var_declaration handling for now
                // case 'short_var_declaration':
                // case 'var_declaration':
                //     this.visitVarDeclaration(node);
                //     return false;
                default:
                    return false; // Allow recursion for unhandled types
            }
        } catch (error: any) {
             logger.warn(`[GoAstVisitor] Error visiting node type ${node.type} in ${this.filepath}: ${error.message}`);
             return false; // Allow recursion even on error
        }
    }

    private visitPackageClause(node: Parser.SyntaxNode) {
        const location = getNodeLocation(node);
        let nameNode: Parser.SyntaxNode | null = node.childForFieldName('name');
        if (!nameNode) {
            const foundNode = node.children.find(c => c.type === 'package_identifier');
            nameNode = foundNode ?? null;
        }
        const name = getNodeText(nameNode);
        if (!name) {
             logger.warn(`[GoAstVisitor] Could not find name for package_clause at ${this.filepath}:${location.startLine}`);
             return;
        }
        this.currentPackage = name;

        const entityId = generateEntityId('packageclause', `${this.filepath}:${name}`);

        const packageNode: PackageClauseNode = {
            id: generateInstanceId(this.instanceCounter, 'package', name, { line: location.startLine, column: location.startColumn }),
            entityId: entityId, kind: 'PackageClause', name: name,
            filePath: this.filepath, language: 'Go', ...location, createdAt: this.now,
        };
        this.nodes.push(packageNode);

        const relEntityId = generateEntityId('declares_package', `${this.fileNode.entityId}:${entityId}`);
        const rel: RelationshipInfo = {
            id: generateInstanceId(this.instanceCounter, 'declares_package', `${this.fileNode.id}:${packageNode.id}`),
            entityId: relEntityId, type: 'DECLARES_PACKAGE',
            sourceId: this.fileNode.entityId, targetId: entityId,
            createdAt: this.now, weight: 9,
        };
        this.relationships.push(rel);
    }

    // Visit the import declaration block (e.g., import "fmt" or import (...))
    private visitImportDeclaration(node: Parser.SyntaxNode) {
        // Find all import_spec nodes within this declaration
        const importSpecs = node.descendantsOfType('import_spec');
        for (const importSpecNode of importSpecs) {
            this.visitImportSpec(importSpecNode);
        }
    }


    private visitImportSpec(node: Parser.SyntaxNode) {
        // This method is now only called by visitImportDeclaration
        const location = getNodeLocation(node);
        const pathNode = node.childForFieldName('path');
        const importPath = getNodeText(pathNode).replace(/"/g, ''); // Remove quotes
        const aliasNode = node.childForFieldName('name'); // Alias comes before path in Go grammar
        const alias = aliasNode ? getNodeText(aliasNode) : undefined;

        if (!importPath) return;

        const entityId = generateEntityId('importspec', `${this.filepath}:${importPath}:${location.startLine}`);
        const importNode: ImportSpecNode = {
            id: generateInstanceId(this.instanceCounter, 'import', importPath, { line: location.startLine, column: location.startColumn }),
            entityId: entityId, kind: 'ImportSpec', name: importPath,
            filePath: this.filepath, language: 'Go', ...location, createdAt: this.now,
            properties: { importPath, alias }
        };
        this.nodes.push(importNode);

        // Relationship: File -> GO_IMPORTS -> ImportSpec
        const relEntityId = generateEntityId('go_imports', `${this.fileNode.entityId}:${entityId}`);
        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, 'go_imports', `${this.fileNode.id}:${importNode.id}`),
            entityId: relEntityId, type: 'GO_IMPORTS',
            sourceId: this.fileNode.entityId, targetId: entityId, // Target is the import spec node for now
            createdAt: this.now, weight: 5,
        });
    }

    private visitFunctionDeclaration(node: Parser.SyntaxNode) {
        const location = getNodeLocation(node);
        const nameNode = node.childForFieldName('name');
        const name = getNodeText(nameNode);
        if (!name) return;

        this.createGoFunctionNode(name, node, location);
        // TODO: Visit body for calls
    }

    private visitMethodDeclaration(node: Parser.SyntaxNode) {
        const location = getNodeLocation(node);
        const nameNode = node.childForFieldName('name');
        const name = getNodeText(nameNode);
        if (!name) return;

        // Extract receiver info using helper function
        const receiverInfo = extractGoReceiver(node);
        if (!receiverInfo) return;

        const receiverTypeName = receiverInfo.receiverType;
        const receiverQualifiedName = this.currentPackage ? `${this.currentPackage}.${receiverTypeName}` : receiverTypeName;
        const receiverEntityId = generateEntityId('gostruct', receiverQualifiedName); // Assume receiver is a struct for now

        // Extract complete signature information
        const signatureInfo = buildGoFunctionSignature(name, node, true, receiverInfo);

        // Extract documentation
        const documentationInfo = extractGoDocumentationInfo(node, this.sourceText);
        const docTags = documentationInfo?.tags || [];

        const qualifiedName = `${receiverTypeName}.${name}`; // Method name qualified by receiver type
        const methodEntityId = generateEntityId('gomethod', qualifiedName);

        const methodNode: GoMethodNode = {
            id: generateInstanceId(this.instanceCounter, 'gomethod', name, { line: location.startLine, column: location.startColumn }),
            entityId: methodEntityId, kind: 'GoMethod', name: name,
            filePath: this.filepath, language: 'Go', ...location, createdAt: this.now,
            parentId: receiverEntityId, // Link to the receiver struct/type
            properties: { receiverType: receiverTypeName },
            // Signature information
            signatureInfo,
            // Documentation
            documentation: documentationInfo?.summary,
            docComment: documentationInfo?.rawComment,
            documentationInfo: documentationInfo,
            tags: docTags.length > 0 ? docTags : undefined,
            // Also set top-level properties for backward compatibility
            returnType: signatureInfo.returnType,
            visibility: signatureInfo.visibility,
        };
        this.nodes.push(methodNode);

        // Relationship: Struct -> HAS_METHOD -> Method
        const relEntityId = generateEntityId('has_method', `${receiverEntityId}:${methodEntityId}`);
        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, 'has_method', `${receiverEntityId}:${methodNode.id}`),
            entityId: relEntityId, type: 'HAS_METHOD', // Reusing HAS_METHOD
            sourceId: receiverEntityId, targetId: methodEntityId,
            createdAt: this.now, weight: 8,
        });
    }

    private visitTypeDefinition(node: Parser.SyntaxNode) {
        const location = getNodeLocation(node);
        const nameNode = node.childForFieldName('name');
        const typeNode = node.childForFieldName('type');
        const name = getNodeText(nameNode);
        if (!name || !typeNode) return;

        // --- TEMPORARY DEBUG LOG ---
        logger.debug(`[GoAstVisitor] visitTypeDefinition Name: ${name}, TypeNode Type: ${typeNode.type}`);
        // --- END TEMPORARY DEBUG LOG ---

        // Ensure qualified name includes package, consistent with method receiver lookup
        const qualifiedName = this.currentPackage ? `${this.currentPackage}.${name}` : name;
        let kind: 'GoStruct' | 'GoInterface' | 'TypeAlias' = 'TypeAlias'; // Default
        let entityIdPrefix = 'typealias';

        if (typeNode.type === 'struct_type') {
            kind = 'GoStruct';
            entityIdPrefix = 'gostruct';
        } else if (typeNode.type === 'interface_type') {
            kind = 'GoInterface';
            entityIdPrefix = 'gointerface';
        }

        // Extract documentation
        const documentationInfo = extractGoDocumentationInfo(node, this.sourceText);
        const docTags = documentationInfo?.tags || [];

        // Use the package-qualified name for entity ID generation
        const entityId = generateEntityId(entityIdPrefix, qualifiedName);
        const typeDefNode: AstNode = {
            id: generateInstanceId(this.instanceCounter, entityIdPrefix, name, { line: location.startLine, column: location.startColumn }),
            entityId: entityId, kind: kind, name: name,
            filePath: this.filepath, language: 'Go', ...location, createdAt: this.now,
            properties: { qualifiedName },
            // Documentation
            documentation: documentationInfo?.summary,
            docComment: documentationInfo?.rawComment,
            documentationInfo: documentationInfo,
            tags: docTags.length > 0 ? docTags : undefined,
            // TODO: Extract fields for structs/methods for interfaces if not handled by recursion
        };
        this.nodes.push(typeDefNode);
        // Add relationship File -> DEFINES_STRUCT/DEFINES_INTERFACE -> GoStruct/GoInterface
        if (kind === 'GoStruct' || kind === 'GoInterface') {
            const relKind = kind === 'GoStruct' ? 'DEFINES_STRUCT' : 'DEFINES_INTERFACE';
            const relEntityId = generateEntityId(relKind.toLowerCase(), `${this.fileNode.entityId}:${entityId}`);
            this.relationships.push({
                id: generateInstanceId(this.instanceCounter, relKind.toLowerCase(), `${this.fileNode.id}:${typeDefNode.id}`),
                entityId: relEntityId, type: relKind,
                sourceId: this.fileNode.entityId, targetId: entityId,
                createdAt: this.now, weight: 9,
            });
        }
        // TODO: Add relationship File -> DEFINES_STRUCT/DEFINES_INTERFACE -> GoStruct/GoInterface
    }

    // Removed visitVarDeclaration as it wasn't correctly identifying function literals in this fixture

    // Helper to create GoFunctionNode (used by func declaration and func literal assignment)
    private createGoFunctionNode(name: string, node: Parser.SyntaxNode, location: { startLine: number, endLine: number, startColumn: number, endColumn: number }) {
        const qualifiedName = this.currentPackage ? `${this.currentPackage}.${name}` : name;
        const entityId = generateEntityId('gofunction', qualifiedName);

        // Use the location of the name identifier, but potentially the end line of the whole node (func literal or declaration)
        const endLine = getNodeLocation(node).endLine;

        // Extract complete signature information
        const signatureInfo = buildGoFunctionSignature(name, node, false);

        // Extract documentation
        const documentationInfo = extractGoDocumentationInfo(node, this.sourceText);
        const docTags = documentationInfo?.tags || [];

        const funcNode: GoFunctionNode = {
            id: generateInstanceId(this.instanceCounter, 'gofunction', name, { line: location.startLine, column: location.startColumn }),
            entityId: entityId, kind: 'GoFunction', name: name,
            filePath: this.filepath, language: 'Go',
            startLine: location.startLine, endLine: endLine, // Use calculated end line
            startColumn: location.startColumn, endColumn: location.endColumn, // Use name location end column for now
            createdAt: this.now,
            properties: { qualifiedName },
            // Signature information
            signatureInfo,
            // Documentation
            documentation: documentationInfo?.summary,
            docComment: documentationInfo?.rawComment,
            documentationInfo: documentationInfo,
            tags: docTags.length > 0 ? docTags : undefined,
            // Also set top-level properties for backward compatibility
            returnType: signatureInfo.returnType,
            visibility: signatureInfo.visibility,
        };
        this.nodes.push(funcNode);

        // Add relationship File -> DEFINES_FUNCTION -> GoFunction
         const relEntityId = generateEntityId('defines_function', `${this.fileNode.entityId}:${entityId}`);
         this.relationships.push({
             id: generateInstanceId(this.instanceCounter, 'defines_function', `${this.fileNode.id}:${funcNode.id}`),
             entityId: relEntityId, type: 'DEFINES_FUNCTION',
             sourceId: this.fileNode.entityId, targetId: entityId,
             createdAt: this.now, weight: 8,
         });
    }
}

/**
 * Parses Go files using Tree-sitter.
 */
export class GoParser {
    private parser: Parser;

    constructor() {
        this.parser = new Parser();
        this.parser.setLanguage(Go as any); // Cast to any to bypass type conflict
        logger.debug('Go Tree-sitter Parser initialized');
    }

    /**
     * Parses a single Go file.
     */
    async parseFile(file: FileInfo): Promise<string> {
        logger.info(`[GoParser] Starting Go parsing for: ${file.name}`);
        await ensureTempDir();
        const tempFilePath = getTempFilePath(file.path);
        const absoluteFilePath = path.resolve(file.path);
        const normalizedFilePath = absoluteFilePath.replace(/\\/g, '/');

        try { // Restore try...catch
            const fileContent = await fs.readFile(absoluteFilePath, 'utf-8');
            const tree = this.parser.parse(fileContent);
            const visitor = new GoAstVisitor(normalizedFilePath, fileContent);
            visitor.visit(tree.rootNode);

            const result: SingleFileParseResult = {
                filePath: normalizedFilePath,
                nodes: visitor.nodes,
                relationships: visitor.relationships,
            };

            await fs.writeFile(tempFilePath, JSON.stringify(result, null, 2));
            logger.info(`[GoParser] Pass 1 completed for: ${file.name}. Nodes: ${result.nodes.length}, Rels: ${result.relationships.length}. Saved to ${path.basename(tempFilePath)}`);
            return tempFilePath;

        } catch (error: any) {
            logger.error(`[GoParser] Error during Go Pass 1 for ${file.path}`, {
                 errorMessage: error.message, stack: error.stack?.substring(0, 500)
            });
            try { await fs.unlink(tempFilePath); } catch { /* ignore */ }
            throw new ParserError(`Failed Go Pass 1 parsing for ${file.path}`, { originalError: error });
        }
    }
}