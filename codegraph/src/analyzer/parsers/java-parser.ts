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
import { AstNode, RelationshipInfo, SingleFileParseResult, InstanceCounter, PackageDeclarationNode, ImportDeclarationNode, JavaClassNode, JavaInterfaceNode, JavaMethodNode, JavaFieldNode, JavaEnumNode, MethodSignature, ParameterInfo, AnnotationInfo, generateSignatureString, generateShortSignature, DocTag, DocumentationInfo } from '../types.js'; // Added JavaEnumNode, signature types, doc types
import { ensureTempDir, getTempFilePath, generateInstanceId, generateEntityId } from '../parser-utils.js';

const logger = createContextLogger('JavaParser');

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

// Java visibility modifiers
const JAVA_VISIBILITY_MODIFIERS = ['public', 'private', 'protected'];
const JAVA_METHOD_MODIFIERS = ['static', 'final', 'abstract', 'synchronized', 'native', 'strictfp', 'default'];

/**
 * Extract modifiers from a Java method/constructor/field declaration node.
 */
function extractJavaModifiers(node: Parser.SyntaxNode): {
    visibility: 'public' | 'private' | 'protected' | 'package';
    modifiers: string[];
    isStatic: boolean;
    isAbstract: boolean;
    isFinal: boolean;
    isSynchronized: boolean;
    isNative: boolean;
} {
    const result = {
        visibility: 'package' as 'public' | 'private' | 'protected' | 'package',
        modifiers: [] as string[],
        isStatic: false,
        isAbstract: false,
        isFinal: false,
        isSynchronized: false,
        isNative: false,
    };

    // Find all 'modifiers' children
    for (const child of node.namedChildren) {
        if (child.type === 'modifiers') {
            for (const modifier of child.namedChildren) {
                const modText = modifier.text;
                if (JAVA_VISIBILITY_MODIFIERS.includes(modText)) {
                    result.visibility = modText as 'public' | 'private' | 'protected';
                }
                if (modText === 'static') result.isStatic = true;
                if (modText === 'abstract') result.isAbstract = true;
                if (modText === 'final') result.isFinal = true;
                if (modText === 'synchronized') result.isSynchronized = true;
                if (modText === 'native') result.isNative = true;
                result.modifiers.push(modText);
            }
        }
    }

    return result;
}

/**
 * Extract return type from a Java method declaration.
 */
function extractJavaReturnType(node: Parser.SyntaxNode): string {
    // Find the 'type' field (return type)
    const typeNode = node.childForFieldName('type');
    if (typeNode) {
        return getNodeText(typeNode);
    }
    // For void methods, check for void_type
    for (const child of node.namedChildren) {
        if (child.type === 'void_type') {
            return 'void';
        }
    }
    return 'void';
}

/**
 * Extract parameters from a Java method/constructor declaration.
 */
function extractJavaParameters(node: Parser.SyntaxNode): ParameterInfo[] {
    const parameters: ParameterInfo[] = [];

    // Find the 'parameters' field (formal_parameters node)
    const paramsNode = node.childForFieldName('parameters');
    if (!paramsNode) return parameters;

    let position = 0;
    for (const child of paramsNode.namedChildren) {
        if (child.type === 'formal_parameter' || child.type === 'spread_parameter') {
            const isVariadic = child.type === 'spread_parameter';

            // Extract type
            const typeNode = child.childForFieldName('type');
            let paramType = getNodeText(typeNode) || 'Object';

            // Extract name
            const nameNode = child.childForFieldName('name');
            const paramName = getNodeText(nameNode) || `arg${position}`;

            // Check for annotations like @Nullable, @NotNull
            const annotations: AnnotationInfo[] = [];
            let isOptional = false;
            for (const c of child.namedChildren) {
                if (c.type === 'marker_annotation' || c.type === 'annotation') {
                    const annoText = getNodeText(c);
                    const annoName = annoText.replace(/^@/, '').split('(')[0];
                    annotations.push({
                        name: annoName,
                        text: annoText,
                    });
                    if (annoName.toLowerCase().includes('nullable') || annoName.toLowerCase().includes('optional')) {
                        isOptional = true;
                    }
                }
            }

            parameters.push({
                name: paramName,
                type: paramType,
                isOptional,
                isVariadic,
                position,
                annotations: annotations.length > 0 ? annotations : undefined,
            });
            position++;
        }
    }

    return parameters;
}

/**
 * Extract throws clause from a Java method declaration.
 */
function extractJavaThrows(node: Parser.SyntaxNode): string[] {
    const throwsExceptions: string[] = [];

    // Find the 'throws' clause
    for (const child of node.namedChildren) {
        if (child.type === 'throws') {
            for (const exceptionNode of child.namedChildren) {
                const exceptionType = getNodeText(exceptionNode);
                if (exceptionType) {
                    throwsExceptions.push(exceptionType);
                }
            }
        }
    }

    return throwsExceptions;
}

/**
 * Extract annotations from a Java method/class declaration.
 */
function extractJavaAnnotations(node: Parser.SyntaxNode): AnnotationInfo[] {
    const annotations: AnnotationInfo[] = [];

    for (const child of node.namedChildren) {
        if (child.type === 'modifiers') {
            for (const modifier of child.namedChildren) {
                if (modifier.type === 'marker_annotation' || modifier.type === 'annotation') {
                    const annoText = getNodeText(modifier);
                    const annoName = annoText.replace(/^@/, '').split('(')[0];

                    // Try to extract arguments
                    const args: Record<string, string | number | boolean> = {};
                    const argsNode = modifier.childForFieldName('arguments');
                    if (argsNode) {
                        // Simple extraction - could be enhanced
                        for (const argChild of argsNode.namedChildren) {
                            if (argChild.type === 'element_value_pair') {
                                const keyNode = argChild.childForFieldName('key');
                                const valueNode = argChild.childForFieldName('value');
                                if (keyNode && valueNode) {
                                    args[getNodeText(keyNode)] = getNodeText(valueNode);
                                }
                            }
                        }
                    }

                    annotations.push({
                        name: annoName,
                        text: annoText,
                        arguments: Object.keys(args).length > 0 ? args : undefined,
                    });
                }
            }
        }
    }

    return annotations;
}

/**
 * Extract Javadoc comment from a Java declaration node.
 * Finds the comment node immediately preceding the declaration.
 */
function extractJavadoc(node: Parser.SyntaxNode, sourceText: string): { rawComment: string; description: string } | null {
    // Look for block_comment (Javadoc starts with /**)
    let prevSibling = node.previousSibling;

    // Skip whitespace/newlines to find the comment
    while (prevSibling && (prevSibling.type === 'line_comment' || prevSibling.type === '\n')) {
        prevSibling = prevSibling.previousSibling;
    }

    // Check if we have a block comment that starts with /**
    if (prevSibling && prevSibling.type === 'block_comment') {
        const commentText = getNodeText(prevSibling);
        if (commentText.startsWith('/**')) {
            // Parse the Javadoc content
            const description = extractJavadocDescription(commentText);
            return {
                rawComment: commentText,
                description,
            };
        }
    }

    // Also check parent's previous sibling for class-level comments
    if (!prevSibling && node.parent) {
        return extractJavadoc(node.parent, sourceText);
    }

    return null;
}

/**
 * Extract the description part of a Javadoc comment (text before the first @tag).
 */
function extractJavadocDescription(javadoc: string): string {
    // Remove /** and */ delimiters
    let content = javadoc.replace(/^\/\*\*/, '').replace(/\*\/$/, '');

    // Split into lines and clean each line
    const lines = content.split('\n').map(line => {
        // Remove leading * and whitespace
        return line.replace(/^\s*\*\s?/, '').trim();
    });

    // Find where the first @tag starts
    const tagIndex = lines.findIndex(line => line.startsWith('@'));

    // Get description lines (before the first @tag)
    const descLines = tagIndex >= 0 ? lines.slice(0, tagIndex) : lines;

    return descLines.filter(line => line.length > 0).join(' ').trim();
}

/**
 * Parse Javadoc tags from a Javadoc comment.
 */
function parseJavadocTags(javadoc: string): DocTag[] {
    const tags: DocTag[] = [];

    // Remove /** and */ delimiters
    let content = javadoc.replace(/^\/\*\*/, '').replace(/\*\/$/, '');

    // Split into lines and clean each line
    const lines = content.split('\n').map(line => {
        return line.replace(/^\s*\*\s?/, '').trim();
    });

    // Find all @tag lines
    let currentTag: { tag: string; name?: string; type?: string; content: string[] } | null = null;

    for (const line of lines) {
        if (line.startsWith('@')) {
            // Save previous tag
            if (currentTag) {
                tags.push(buildJavadocTag(currentTag));
            }

            // Parse new tag
            const tagMatch = line.match(/^@(\w+)(?:\s+(.*))?$/);
            if (tagMatch) {
                const tagName = tagMatch[1]!;
                const rest = tagMatch[2] || '';

                currentTag = { tag: tagName, content: [] };

                // Parse tag-specific content
                switch (tagName) {
                    case 'param': {
                        // Format: @param name description
                        const paramMatch = rest.match(/^(\w+)\s*(.*)$/);
                        if (paramMatch) {
                            currentTag.name = paramMatch[1];
                            if (paramMatch[2]) currentTag.content.push(paramMatch[2]);
                        }
                        break;
                    }
                    case 'return':
                    case 'returns': {
                        // Format: @return description
                        if (rest) currentTag.content.push(rest);
                        break;
                    }
                    case 'throws':
                    case 'exception': {
                        // Format: @throws ExceptionType description
                        const throwsMatch = rest.match(/^(\S+)\s*(.*)$/);
                        if (throwsMatch) {
                            currentTag.type = throwsMatch[1];
                            if (throwsMatch[2]) currentTag.content.push(throwsMatch[2]);
                        }
                        break;
                    }
                    case 'deprecated':
                    case 'see':
                    case 'since':
                    case 'version':
                    case 'author': {
                        if (rest) currentTag.content.push(rest);
                        break;
                    }
                    default: {
                        if (rest) currentTag.content.push(rest);
                    }
                }
            }
        } else if (currentTag && line.length > 0) {
            // Continuation of previous tag
            currentTag.content.push(line);
        }
    }

    // Save last tag
    if (currentTag) {
        tags.push(buildJavadocTag(currentTag));
    }

    return tags;
}

/**
 * Build a DocTag from parsed Javadoc tag info.
 */
function buildJavadocTag(info: { tag: string; name?: string; type?: string; content: string[] }): DocTag {
    return {
        tag: info.tag === 'return' ? 'returns' : info.tag, // Normalize @return to @returns
        name: info.name,
        type: info.type,
        description: info.content.join(' ').trim() || undefined,
    };
}

/**
 * Extract complete documentation info from a Java node.
 */
function extractJavaDocumentationInfo(node: Parser.SyntaxNode, sourceText: string): DocumentationInfo | undefined {
    const javadoc = extractJavadoc(node, sourceText);
    if (!javadoc) {
        return undefined;
    }

    const tags = parseJavadocTags(javadoc.rawComment);

    // Extract specific metadata from tags
    const isDeprecated = tags.some(t => t.tag === 'deprecated');
    const deprecationReason = tags.find(t => t.tag === 'deprecated')?.description;
    const seeAlso = tags.filter(t => t.tag === 'see').map(t => t.description).filter(Boolean) as string[];
    const authors = tags.filter(t => t.tag === 'author').map(t => t.description).filter(Boolean) as string[];
    const version = tags.find(t => t.tag === 'version')?.description;
    const since = tags.find(t => t.tag === 'since')?.description;

    return {
        summary: javadoc.description,
        rawComment: javadoc.rawComment,
        tags,
        format: 'javadoc',
        isDeprecated: isDeprecated || undefined,
        deprecationReason,
        seeAlso: seeAlso.length > 0 ? seeAlso : undefined,
        authors: authors.length > 0 ? authors : undefined,
        version,
        since,
    };
}

/**
 * Build a complete MethodSignature for a Java method.
 */
function buildJavaMethodSignature(
    name: string,
    node: Parser.SyntaxNode,
    isConstructor: boolean = false
): MethodSignature {
    const modifiers = extractJavaModifiers(node);
    const parameters = extractJavaParameters(node);
    const returnType = isConstructor ? name : extractJavaReturnType(node);
    const throwsExceptions = extractJavaThrows(node);
    const annotations = extractJavaAnnotations(node);

    const signature: MethodSignature = {
        signature: '', // Will be generated
        shortSignature: generateShortSignature(name, parameters),
        returnType,
        returnsVoid: returnType === 'void',
        parameters,
        parameterCount: parameters.length,
        visibility: modifiers.visibility === 'package' ? 'default' : modifiers.visibility,
        modifiers: modifiers.modifiers,
        isStatic: modifiers.isStatic,
        isAsync: false, // Java doesn't have async keyword
        isAbstract: modifiers.isAbstract,
        isFinal: modifiers.isFinal,
        isConstructor,
        throwsExceptions: throwsExceptions.length > 0 ? throwsExceptions : undefined,
        annotations: annotations.length > 0 ? annotations : undefined,
    };

    // Generate full signature string
    signature.signature = generateSignatureString('Java', name, signature);

    return signature;
}

// --- Tree-sitter Visitor ---
class JavaAstVisitor {
    public nodes: AstNode[] = [];
    public relationships: RelationshipInfo[] = [];
    private instanceCounter: InstanceCounter = { count: 0 };
    private fileNode: AstNode;
    private now: string = new Date().toISOString();
    private currentPackage: string | null = null;
    private currentClassOrInterfaceId: string | null = null; // Store entityId

    constructor(private filepath: string, private sourceText: string) {
        const filename = path.basename(filepath);
        const fileEntityId = generateEntityId('file', filepath);
        this.fileNode = {
            id: generateInstanceId(this.instanceCounter, 'file', filename),
            entityId: fileEntityId, kind: 'File', name: filename, filePath: filepath,
            startLine: 1, endLine: 0, startColumn: 0, endColumn: 0,
            language: 'Java', createdAt: this.now,
        };
        this.nodes.push(this.fileNode);
    }

    visit(node: Parser.SyntaxNode) {
        // Process the current node first
        this.visitNode(node); // Always process the node

        // Always recurse into children
        for (const child of node.namedChildren) {
            this.visit(child);
        }

        if (node.type === 'program') { // Root node type for Java
             this.fileNode.endLine = node.endPosition.row + 1;
             this.fileNode.loc = this.fileNode.endLine;
        }
    }

    private visitNode(node: Parser.SyntaxNode) {
        try {
            switch (node.type) {
                case 'package_declaration':
                    this.visitPackageDeclaration(node);
                    break;
                case 'import_declaration':
                    this.visitImportDeclaration(node);
                    break;
                case 'class_declaration':
                    this.visitClassOrInterfaceDeclaration(node, 'JavaClass');
                    break;
                case 'interface_declaration':
                     this.visitClassOrInterfaceDeclaration(node, 'JavaInterface');
                     break;
                case 'enum_declaration':
                     this.visitEnumDeclaration(node);
                     break;
                case 'method_declaration':
                     this.visitMethodDeclaration(node);
                     break;
                case 'constructor_declaration': // Handle constructors explicitly
                     this.visitConstructorDeclaration(node);
                     break;
                case 'field_declaration':
                     this.visitFieldDeclaration(node);
                     break;
                // No need to explicitly handle body nodes here, main visit loop handles recursion
            }
        } catch (error: any) {
             logger.warn(`[JavaAstVisitor] Error visiting node type ${node.type} in ${this.filepath}: ${error.message}`);
        }
    }

    private visitPackageDeclaration(node: Parser.SyntaxNode) {
        const location = getNodeLocation(node);
        const packageName = getNodeText(node.namedChild(0)); // Assuming name is the first named child
        this.currentPackage = packageName;

        const entityId = generateEntityId('packagedeclaration', `${this.filepath}:${packageName}`);
        const packageNode: PackageDeclarationNode = {
            id: generateInstanceId(this.instanceCounter, 'package', packageName, { line: location.startLine, column: location.startColumn }),
            entityId: entityId, kind: 'PackageDeclaration', name: packageName,
            filePath: this.filepath, language: 'Java', ...location, createdAt: this.now,
        };
        this.nodes.push(packageNode);

        // Relationship: File -> DECLARES_PACKAGE -> PackageDeclaration
        const relEntityId = generateEntityId('declares_package', `${this.fileNode.entityId}:${entityId}`);
        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, 'declares_package', `${this.fileNode.id}:${packageNode.id}`),
            entityId: relEntityId, type: 'DECLARES_PACKAGE',
            sourceId: this.fileNode.entityId, targetId: entityId,
            createdAt: this.now, weight: 9,
        });
    }

    private visitImportDeclaration(node: Parser.SyntaxNode) {
        const location = getNodeLocation(node);
        const importPath = getNodeText(node.namedChild(0)); // Assuming path is first named child
        const onDemand = getNodeText(node).endsWith('.*'); // Simple check for wildcard

        const entityId = generateEntityId('importdeclaration', `${this.filepath}:${importPath}:${location.startLine}`);
        const importNode: ImportDeclarationNode = {
            id: generateInstanceId(this.instanceCounter, 'import', importPath, { line: location.startLine, column: location.startColumn }),
            entityId: entityId, kind: 'ImportDeclaration', name: importPath,
            filePath: this.filepath, language: 'Java', ...location, createdAt: this.now,
            properties: { importPath, onDemand }
        };
        this.nodes.push(importNode);

        // Relationship: File -> JAVA_IMPORTS -> ImportDeclaration
        // Target resolution happens in Pass 2
        const relEntityId = generateEntityId('java_imports', `${this.fileNode.entityId}:${entityId}`);
        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, 'java_imports', `${this.fileNode.id}:${importNode.id}`),
            entityId: relEntityId, type: 'JAVA_IMPORTS',
            sourceId: this.fileNode.entityId, targetId: entityId, // Target is the import node itself for now
            createdAt: this.now, weight: 5,
        });
    }

    private visitClassOrInterfaceDeclaration(node: Parser.SyntaxNode, kind: 'JavaClass' | 'JavaInterface') {
        const location = getNodeLocation(node);
        const nameNode = node.childForFieldName('name');
        const name = getNodeText(nameNode);
        if (!name) return;

        const originalClassOrInterfaceId = this.currentClassOrInterfaceId; // Backup context
        const qualifiedName = this.currentPackage ? `${this.currentPackage}.${name}` : name;
        const entityId = generateEntityId(kind.toLowerCase(), qualifiedName); // Use qualified name for entity ID

        // Extract Javadoc documentation
        const documentationInfo = extractJavaDocumentationInfo(node, this.sourceText);
        const docTags = documentationInfo?.tags || [];

        const classNode: AstNode = { // Use base AstNode, specific type depends on kind
            id: generateInstanceId(this.instanceCounter, kind.toLowerCase(), name, { line: location.startLine, column: location.startColumn }),
            entityId: entityId, kind: kind, name: name,
            filePath: this.filepath, language: 'Java', ...location, createdAt: this.now,
            properties: { qualifiedName },
            documentation: documentationInfo?.summary,
            docComment: documentationInfo?.rawComment,
            documentationInfo: documentationInfo,
            tags: docTags.length > 0 ? docTags : undefined,
            // TODO: Add extends/implements info to properties
        };
        this.nodes.push(classNode);
        this.currentClassOrInterfaceId = entityId; // Set context for methods/fields

        // Relationship: File -> DEFINES_CLASS/DEFINES_INTERFACE -> Class/Interface
        const relType = kind === 'JavaClass' ? 'DEFINES_CLASS' : 'DEFINES_INTERFACE';
        const relEntityId = generateEntityId(relType.toLowerCase(), `${this.fileNode.entityId}:${entityId}`);
        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, relType.toLowerCase(), `${this.fileNode.id}:${classNode.id}`),
            entityId: relEntityId, type: relType,
            sourceId: this.fileNode.entityId, targetId: entityId,
            createdAt: this.now, weight: 9,
        });

        // TODO: Add relationships for extends/implements based on 'superclass'/'interfaces' fields

        // Let main visit loop handle recursion into body
        // const bodyNode = node.childForFieldName('body');
        // if (bodyNode) {
        //     this.visit(bodyNode); // Recurse into the body
        // }

        // Restore context AFTER visiting children (handled by main visit loop finishing siblings)
        // this.currentClassOrInterfaceId = originalClassOrInterfaceId; // Defer restoration
    }

     private visitMethodDeclaration(node: Parser.SyntaxNode) {
        if (!this.currentClassOrInterfaceId) return; // Only process methods within a class/interface context

        const location = getNodeLocation(node);
        // Use 'name' field which works for regular methods
        const nameNode = node.childForFieldName('name');
        const name = getNodeText(nameNode);

        if (!name) {
            logger.warn(`[JavaAstVisitor] Could not find name for method_declaration at ${this.filepath}:${location.startLine}`);
            return;
        }

        // Extract complete signature information
        const signatureInfo = buildJavaMethodSignature(name, node, false);

        // Extract Javadoc documentation
        const documentationInfo = extractJavaDocumentationInfo(node, this.sourceText);
        const docTags = documentationInfo?.tags || [];

        const methodEntityId = generateEntityId('javamethod', `${this.currentClassOrInterfaceId}.${name}`); // ID relative to parent
        const methodNode: JavaMethodNode = {
            id: generateInstanceId(this.instanceCounter, 'javamethod', name, { line: location.startLine, column: location.startColumn }),
            entityId: methodEntityId, kind: 'JavaMethod', name: name,
            filePath: this.filepath, language: 'Java', ...location, createdAt: this.now,
            parentId: this.currentClassOrInterfaceId,
            // Signature information
            signatureInfo,
            // Documentation
            documentation: documentationInfo?.summary,
            docComment: documentationInfo?.rawComment,
            documentationInfo: documentationInfo,
            tags: docTags.length > 0 ? docTags : undefined,
            // Also set top-level properties for backward compatibility
            returnType: signatureInfo.returnType,
            visibility: signatureInfo.visibility === 'default' ? 'package' : signatureInfo.visibility,
            isStatic: signatureInfo.isStatic,
            isAbstract: signatureInfo.isAbstract,
            modifierFlags: signatureInfo.modifiers,
        };
        this.nodes.push(methodNode);

        // Relationship: Class/Interface -> HAS_METHOD -> Method
        const relEntityId = generateEntityId('has_method', `${this.currentClassOrInterfaceId}:${methodEntityId}`);
        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, 'has_method', `${this.currentClassOrInterfaceId}:${methodNode.id}`),
            entityId: relEntityId, type: 'HAS_METHOD',
            sourceId: this.currentClassOrInterfaceId, targetId: methodEntityId,
            createdAt: this.now, weight: 8,
        });
    }

    // Separate visitor for constructors
    private visitConstructorDeclaration(node: Parser.SyntaxNode) {
        if (!this.currentClassOrInterfaceId) return;

        const location = getNodeLocation(node);
        const nameNode = node.childForFieldName('name'); // Constructor name is in 'name' field
        const name = getNodeText(nameNode);

        if (!name) {
            logger.warn(`[JavaAstVisitor] Could not find name for constructor_declaration at ${this.filepath}:${location.startLine}`);
            return;
        }

        // Verify name matches the current class context
        const parentClassNode = this.nodes.find(n => n.entityId === this.currentClassOrInterfaceId);
        if (!parentClassNode || name !== parentClassNode.name) {
             logger.warn(`[JavaAstVisitor] Constructor name "${name}" does not match class name "${parentClassNode?.name}" at ${this.filepath}:${location.startLine}`);
             return; // Likely a parsing error or unexpected structure
        }

        // Extract complete signature information (isConstructor = true)
        const signatureInfo = buildJavaMethodSignature(name, node, true);

        // Extract Javadoc documentation
        const documentationInfo = extractJavaDocumentationInfo(node, this.sourceText);
        const docTags = documentationInfo?.tags || [];

        const methodEntityId = generateEntityId('javamethod', `${this.currentClassOrInterfaceId}.${name}`); // Use same kind for simplicity
        const methodNode: JavaMethodNode = {
            id: generateInstanceId(this.instanceCounter, 'javamethod', name, { line: location.startLine, column: location.startColumn }),
            entityId: methodEntityId, kind: 'JavaMethod', name: name, // Treat as a method
            filePath: this.filepath, language: 'Java', ...location, createdAt: this.now,
            parentId: this.currentClassOrInterfaceId,
            properties: { isConstructor: true }, // Add property to distinguish
            // Signature information
            signatureInfo,
            // Documentation
            documentation: documentationInfo?.summary,
            docComment: documentationInfo?.rawComment,
            documentationInfo: documentationInfo,
            tags: docTags.length > 0 ? docTags : undefined,
            // Also set top-level properties for backward compatibility
            visibility: signatureInfo.visibility === 'default' ? 'package' : signatureInfo.visibility,
            modifierFlags: signatureInfo.modifiers,
        };
        this.nodes.push(methodNode);

        // Relationship: Class -> HAS_METHOD -> Constructor
        const relEntityId = generateEntityId('has_method', `${this.currentClassOrInterfaceId}:${methodEntityId}`);
        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, 'has_method', `${this.currentClassOrInterfaceId}:${methodNode.id}`),
            entityId: relEntityId, type: 'HAS_METHOD',
            sourceId: this.currentClassOrInterfaceId, targetId: methodEntityId,
            createdAt: this.now, weight: 8,
        });
    }


     private visitFieldDeclaration(node: Parser.SyntaxNode) {
        if (!this.currentClassOrInterfaceId) return; // Only process fields within a class/interface context

        const location = getNodeLocation(node);
        // Field declaration can have multiple variables (e.g., int x, y;)
        // The structure is typically: modifiers type declarator(s);
        const declaratorList = node.namedChildren.filter(c => c.type === 'variable_declarator');

        if (declaratorList.length === 0) {
             logger.warn(`[JavaAstVisitor] No variable_declarator found in field_declaration at ${this.filepath}:${location.startLine}`);
             return;
        }

        // Extract Javadoc documentation for the field declaration (applies to all declarators)
        const documentationInfo = extractJavaDocumentationInfo(node, this.sourceText);
        const docTags = documentationInfo?.tags || [];

        // Extract modifiers for the field
        const modifiers = extractJavaModifiers(node);

        // Extract type from the field declaration
        const typeNode = node.childForFieldName('type');
        const fieldType = getNodeText(typeNode) || 'Object';

        for (const declarator of declaratorList) {
             const nameNode = declarator.childForFieldName('name'); // Tree-sitter Java uses 'name'
             const name = getNodeText(nameNode);
             if (!name) continue;

             const fieldEntityId = generateEntityId('javafield', `${this.currentClassOrInterfaceId}.${name}`);
             const fieldNode: JavaFieldNode = {
                 id: generateInstanceId(this.instanceCounter, 'javafield', name, { line: location.startLine, column: location.startColumn }), // Use declarator location?
                 entityId: fieldEntityId, kind: 'JavaField', name: name,
                 filePath: this.filepath, language: 'Java', ...getNodeLocation(declarator), createdAt: this.now, // Use declarator location
                 parentId: this.currentClassOrInterfaceId,
                 // Type and modifiers
                 fieldType: fieldType,
                 visibility: modifiers.visibility,
                 isStatic: modifiers.isStatic,
                 modifierFlags: modifiers.modifiers,
                 // Documentation
                 documentation: documentationInfo?.summary,
                 docComment: documentationInfo?.rawComment,
                 documentationInfo: documentationInfo,
                 tags: docTags.length > 0 ? docTags : undefined,
             };
             this.nodes.push(fieldNode);

             // Relationship: Class/Interface -> HAS_FIELD -> Field
             const relEntityId = generateEntityId('has_field', `${this.currentClassOrInterfaceId}:${fieldEntityId}`);
             this.relationships.push({
                 id: generateInstanceId(this.instanceCounter, 'has_field', `${this.currentClassOrInterfaceId}:${fieldNode.id}`),
                 entityId: relEntityId, type: 'HAS_FIELD',
                 sourceId: this.currentClassOrInterfaceId, targetId: fieldEntityId,
                 createdAt: this.now, weight: 7,
             });
        }
    }

    private visitEnumDeclaration(node: Parser.SyntaxNode) {
        const location = getNodeLocation(node);
        const nameNode = node.childForFieldName('name');
        const name = getNodeText(nameNode);
        if (!name) return;

        const qualifiedName = this.currentPackage ? `${this.currentPackage}.${name}` : name;
        const entityId = generateEntityId('javaenum', qualifiedName);

        // Extract Javadoc documentation
        const documentationInfo = extractJavaDocumentationInfo(node, this.sourceText);
        const docTags = documentationInfo?.tags || [];

        const enumNode: JavaEnumNode = {
            id: generateInstanceId(this.instanceCounter, 'javaenum', name, { line: location.startLine, column: location.startColumn }),
            entityId: entityId, kind: 'JavaEnum', name: name,
            filePath: this.filepath, language: 'Java', ...location, createdAt: this.now,
            properties: { qualifiedName },
            // Documentation
            documentation: documentationInfo?.summary,
            docComment: documentationInfo?.rawComment,
            documentationInfo: documentationInfo,
            tags: docTags.length > 0 ? docTags : undefined,
            // TODO: Extract enum constants from body
        };
        this.nodes.push(enumNode);

        // Relationship: File -> DEFINES_ENUM -> Enum
        const relEntityId = generateEntityId('defines_enum', `${this.fileNode.entityId}:${entityId}`);
        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, 'defines_enum', `${this.fileNode.id}:${enumNode.id}`),
            entityId: relEntityId, type: 'DEFINES_ENUM',
            sourceId: this.fileNode.entityId, targetId: entityId,
            createdAt: this.now, weight: 9,
        });

        // Let main visit loop handle recursion into body
        // const bodyNode = node.childForFieldName('body');
        // if (bodyNode) {
        //     this.visit(bodyNode);
        // }
    }
}

/**
 * Parses Java files using Tree-sitter.
 */
export class JavaParser {
    private parser: Parser;

    constructor() {
        this.parser = new Parser();
        this.parser.setLanguage(Java as any); // Cast to any to bypass type conflict
        logger.debug('Java Tree-sitter Parser initialized');
    }

    /**
     * Parses a single Java file.
     */
    async parseFile(file: FileInfo): Promise<string> {
        logger.info(`[JavaParser] Starting Java parsing for: ${file.name}`);
        await ensureTempDir();
        const tempFilePath = getTempFilePath(file.path);
        const absoluteFilePath = path.resolve(file.path);
        const normalizedFilePath = absoluteFilePath.replace(/\\/g, '/');

        try {
            const fileContent = await fs.readFile(absoluteFilePath, 'utf-8');
            const tree = this.parser.parse(fileContent);
            const visitor = new JavaAstVisitor(normalizedFilePath, fileContent);
            visitor.visit(tree.rootNode);

            const result: SingleFileParseResult = {
                filePath: normalizedFilePath,
                nodes: visitor.nodes,
                relationships: visitor.relationships,
            };

            await fs.writeFile(tempFilePath, JSON.stringify(result, null, 2));
            logger.info(`[JavaParser] Pass 1 completed for: ${file.name}. Nodes: ${result.nodes.length}, Rels: ${result.relationships.length}. Saved to ${path.basename(tempFilePath)}`);
            return tempFilePath;

        } catch (error: any) {
            logger.error(`[JavaParser] Error during Java Pass 1 for ${file.path}`, {
                 errorMessage: error.message, stack: error.stack?.substring(0, 500)
            });
            try { await fs.unlink(tempFilePath); } catch { /* ignore */ }
            throw new ParserError(`Failed Java Pass 1 parsing for ${file.path}`, { originalError: error });
        }
    }
}