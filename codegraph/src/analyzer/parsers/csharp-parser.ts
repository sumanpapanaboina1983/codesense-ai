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
import { AstNode, RelationshipInfo, SingleFileParseResult, InstanceCounter, NamespaceDeclarationNode, UsingDirectiveNode, CSharpClassNode, CSharpInterfaceNode, CSharpStructNode, CSharpMethodNode, PropertyNode, FieldNode, MethodSignature, ParameterInfo, AnnotationInfo, generateShortSignature, DocTag, DocumentationInfo } from '../types.js';
import { ensureTempDir, getTempFilePath, generateInstanceId, generateEntityId } from '../parser-utils.js';

const logger = createContextLogger('CSharpParser');

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
 * Extract C# XML doc comments (/// comments) preceding a declaration node.
 */
function extractCSharpXmlDocComment(node: Parser.SyntaxNode, sourceText: string): { rawComment: string; xmlContent: string } | null {
    // Get all previous siblings that are comments
    const comments: string[] = [];
    let prevSibling = node.previousSibling;

    while (prevSibling) {
        // C# XML doc comments are stored as 'comment' nodes with /// prefix
        if (prevSibling.type === 'comment') {
            const commentText = getNodeText(prevSibling);
            // Check if it's a /// XML doc comment
            if (commentText.startsWith('///')) {
                // Check if the comment is on the line immediately before
                const commentEndLine = prevSibling.endPosition.row;
                const nextNodeStartLine = prevSibling.nextSibling?.startPosition.row ?? node.startPosition.row;

                // Only include if there's no blank line between comments
                if (nextNodeStartLine - commentEndLine <= 1) {
                    // Remove the /// prefix and trim
                    const cleanComment = commentText.replace(/^\/\/\/\s?/, '').trim();
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

    const rawComment = comments.map(c => `/// ${c}`).join('\n');
    const xmlContent = comments.join('\n');

    return { rawComment, xmlContent };
}

/**
 * Parse C# XML doc comment tags.
 * Extracts structured information from XML elements.
 */
function parseCSharpXmlDocTags(xmlContent: string): DocTag[] {
    const tags: DocTag[] = [];

    if (!xmlContent) {
        return tags;
    }

    // Extract <param> tags
    const paramRegex = /<param\s+name=["']([^"']+)["']>\s*([\s\S]*?)\s*<\/param>/gi;
    let match;
    while ((match = paramRegex.exec(xmlContent)) !== null) {
        tags.push({
            tag: 'param',
            name: match[1],
            description: cleanXmlContent(match[2]),
        });
    }

    // Extract <returns> tags
    const returnsRegex = /<returns>\s*([\s\S]*?)\s*<\/returns>/gi;
    while ((match = returnsRegex.exec(xmlContent)) !== null) {
        tags.push({
            tag: 'returns',
            description: cleanXmlContent(match[1]),
        });
    }

    // Extract <exception> tags
    const exceptionRegex = /<exception\s+cref=["']([^"']+)["']>\s*([\s\S]*?)\s*<\/exception>/gi;
    while ((match = exceptionRegex.exec(xmlContent)) !== null) {
        tags.push({
            tag: 'throws',
            type: match[1],
            description: cleanXmlContent(match[2]),
        });
    }

    // Extract <typeparam> tags
    const typeParamRegex = /<typeparam\s+name=["']([^"']+)["']>\s*([\s\S]*?)\s*<\/typeparam>/gi;
    while ((match = typeParamRegex.exec(xmlContent)) !== null) {
        tags.push({
            tag: 'typeparam',
            name: match[1],
            description: cleanXmlContent(match[2]),
        });
    }

    // Extract <example> tags
    const exampleRegex = /<example>\s*([\s\S]*?)\s*<\/example>/gi;
    while ((match = exampleRegex.exec(xmlContent)) !== null) {
        tags.push({
            tag: 'example',
            description: cleanXmlContent(match[1]),
        });
    }

    // Extract <see> and <seealso> tags
    const seeRegex = /<see(?:also)?\s+cref=["']([^"']+)["']\s*\/?>/gi;
    while ((match = seeRegex.exec(xmlContent)) !== null) {
        tags.push({
            tag: 'see',
            description: match[1],
        });
    }

    // Extract <remarks> tags
    const remarksRegex = /<remarks>\s*([\s\S]*?)\s*<\/remarks>/gi;
    while ((match = remarksRegex.exec(xmlContent)) !== null) {
        tags.push({
            tag: 'remarks',
            description: cleanXmlContent(match[1]),
        });
    }

    return tags;
}

/**
 * Extract summary text from C# XML doc comment.
 */
function extractCSharpSummary(xmlContent: string): string {
    const summaryMatch = xmlContent.match(/<summary>\s*([\s\S]*?)\s*<\/summary>/i);
    if (summaryMatch) {
        return cleanXmlContent(summaryMatch[1]);
    }

    // If no <summary> tag, try to get the first paragraph of text
    const firstLine = xmlContent.split('\n')[0]?.trim();
    if (firstLine && !firstLine.startsWith('<')) {
        return cleanXmlContent(firstLine);
    }

    return '';
}

/**
 * Clean XML content by removing nested tags and normalizing whitespace.
 */
function cleanXmlContent(content: string): string {
    return content
        .replace(/<[^>]+>/g, '') // Remove XML tags
        .replace(/\s+/g, ' ') // Normalize whitespace
        .trim();
}

/**
 * Extract complete documentation info from a C# node.
 */
function extractCSharpDocumentationInfo(node: Parser.SyntaxNode, sourceText: string): DocumentationInfo | undefined {
    const docComment = extractCSharpXmlDocComment(node, sourceText);
    if (!docComment) {
        return undefined;
    }

    const tags = parseCSharpXmlDocTags(docComment.xmlContent);
    const summary = extractCSharpSummary(docComment.xmlContent);

    // Extract specific metadata from tags
    const seeAlso = tags.filter(t => t.tag === 'see').map(t => t.description).filter(Boolean) as string[];
    const examples = tags.filter(t => t.tag === 'example').map(t => t.description).filter(Boolean) as string[];
    const remarks = tags.filter(t => t.tag === 'remarks').map(t => t.description).filter(Boolean) as string[];

    return {
        summary: summary || undefined,
        rawComment: docComment.rawComment,
        tags,
        format: 'xmldoc',
        seeAlso: seeAlso.length > 0 ? seeAlso : undefined,
        examples: examples.length > 0 ? examples : undefined,
    };
}

// C# visibility and other modifiers
const CSHARP_VISIBILITY_MODIFIERS = ['public', 'private', 'protected', 'internal'];
const CSHARP_METHOD_MODIFIERS = ['static', 'virtual', 'override', 'abstract', 'sealed', 'extern', 'async', 'partial', 'new', 'unsafe'];

/**
 * Extract modifiers from a C# method declaration.
 */
function extractCSharpModifiers(node: Parser.SyntaxNode): {
    visibility: 'public' | 'private' | 'protected' | 'internal' | 'default';
    modifiers: string[];
    isStatic: boolean;
    isVirtual: boolean;
    isOverride: boolean;
    isAbstract: boolean;
    isSealed: boolean;
    isAsync: boolean;
    isExtern: boolean;
    isPartial: boolean;
} {
    const result = {
        visibility: 'private' as 'public' | 'private' | 'protected' | 'internal' | 'default',
        modifiers: [] as string[],
        isStatic: false,
        isVirtual: false,
        isOverride: false,
        isAbstract: false,
        isSealed: false,
        isAsync: false,
        isExtern: false,
        isPartial: false,
    };

    // Find modifiers node
    for (const child of node.namedChildren) {
        if (child.type === 'modifier') {
            const modText = getNodeText(child);
            result.modifiers.push(modText);

            if (CSHARP_VISIBILITY_MODIFIERS.includes(modText)) {
                result.visibility = modText as 'public' | 'private' | 'protected' | 'internal';
            }
            if (modText === 'static') result.isStatic = true;
            if (modText === 'virtual') result.isVirtual = true;
            if (modText === 'override') result.isOverride = true;
            if (modText === 'abstract') result.isAbstract = true;
            if (modText === 'sealed') result.isSealed = true;
            if (modText === 'async') result.isAsync = true;
            if (modText === 'extern') result.isExtern = true;
            if (modText === 'partial') result.isPartial = true;
        }
    }

    return result;
}

/**
 * Extract return type from a C# method declaration.
 */
function extractCSharpReturnType(node: Parser.SyntaxNode): string {
    const returnTypeNode = node.childForFieldName('type');
    if (returnTypeNode) {
        return getNodeText(returnTypeNode);
    }
    // Check for 'void' keyword
    for (const child of node.children) {
        if (child.type === 'predefined_type' && getNodeText(child) === 'void') {
            return 'void';
        }
    }
    return 'void';
}

/**
 * Extract parameters from a C# method declaration.
 */
function extractCSharpParameters(node: Parser.SyntaxNode): ParameterInfo[] {
    const parameters: ParameterInfo[] = [];
    const paramsNode = node.childForFieldName('parameters');
    if (!paramsNode) return parameters;

    let position = 0;
    for (const child of paramsNode.namedChildren) {
        if (child.type === 'parameter') {
            const typeNode = child.childForFieldName('type');
            const nameNode = child.childForFieldName('name');
            const defaultValueNode = child.childForFieldName('default_value');

            let paramType = getNodeText(typeNode) || 'object';
            const paramName = getNodeText(nameNode) || `arg${position}`;
            const defaultValue = defaultValueNode ? getNodeText(defaultValueNode) : undefined;

            // Check for ref/out/in/params modifiers
            let isByReference = false;
            let referenceModifier: 'ref' | 'out' | 'in' | undefined;
            let isVariadic = false;

            for (const modifier of child.namedChildren) {
                if (modifier.type === 'parameter_modifier') {
                    const modText = getNodeText(modifier);
                    if (modText === 'ref') { isByReference = true; referenceModifier = 'ref'; }
                    if (modText === 'out') { isByReference = true; referenceModifier = 'out'; }
                    if (modText === 'in') { isByReference = true; referenceModifier = 'in'; }
                    if (modText === 'params') isVariadic = true;
                }
            }

            // Extract attributes
            const annotations: AnnotationInfo[] = [];
            for (const attrList of child.namedChildren) {
                if (attrList.type === 'attribute_list') {
                    for (const attr of attrList.namedChildren) {
                        if (attr.type === 'attribute') {
                            const attrName = getNodeText(attr.childForFieldName('name'));
                            annotations.push({
                                name: attrName,
                                text: getNodeText(attr),
                            });
                        }
                    }
                }
            }

            parameters.push({
                name: paramName,
                type: paramType,
                defaultValue,
                isOptional: defaultValue !== undefined,
                isVariadic,
                isByReference,
                referenceModifier,
                annotations: annotations.length > 0 ? annotations : undefined,
                position,
            });
            position++;
        }
    }

    return parameters;
}

/**
 * Extract attributes (decorators) from a C# method declaration.
 */
function extractCSharpAttributes(node: Parser.SyntaxNode): AnnotationInfo[] {
    const annotations: AnnotationInfo[] = [];

    for (const child of node.namedChildren) {
        if (child.type === 'attribute_list') {
            for (const attr of child.namedChildren) {
                if (attr.type === 'attribute') {
                    const attrName = getNodeText(attr.childForFieldName('name'));
                    const argsNode = attr.childForFieldName('arguments');

                    // Simple argument extraction
                    const args: Record<string, string | number | boolean> = {};
                    if (argsNode) {
                        for (const argChild of argsNode.namedChildren) {
                            if (argChild.type === 'attribute_argument') {
                                const nameNode = argChild.childForFieldName('name');
                                const exprNode = argChild.childForFieldName('expression');
                                if (nameNode && exprNode) {
                                    args[getNodeText(nameNode)] = getNodeText(exprNode);
                                }
                            }
                        }
                    }

                    annotations.push({
                        name: attrName,
                        text: getNodeText(attr),
                        arguments: Object.keys(args).length > 0 ? args : undefined,
                    });
                }
            }
        }
    }

    return annotations;
}

/**
 * Build a MethodSignature for a C# method.
 */
function buildCSharpMethodSignature(
    name: string,
    node: Parser.SyntaxNode,
    isConstructor: boolean = false
): MethodSignature {
    const modifiers = extractCSharpModifiers(node);
    const parameters = extractCSharpParameters(node);
    const returnType = isConstructor ? name : extractCSharpReturnType(node);
    const annotations = extractCSharpAttributes(node);

    const signature: MethodSignature = {
        signature: '', // Will be generated below
        shortSignature: generateShortSignature(name, parameters),
        returnType,
        returnsVoid: returnType === 'void',
        parameters,
        parameterCount: parameters.length,
        visibility: modifiers.visibility === 'default' ? 'private' : modifiers.visibility,
        modifiers: modifiers.modifiers,
        isStatic: modifiers.isStatic,
        isAsync: modifiers.isAsync,
        isAbstract: modifiers.isAbstract,
        isFinal: modifiers.isSealed,
        isVirtual: modifiers.isVirtual,
        isOverride: modifiers.isOverride,
        isConstructor,
        annotations: annotations.length > 0 ? annotations : undefined,
    };

    // Generate signature string
    const modifierStr = modifiers.modifiers.join(' ');
    const paramStr = parameters.map(p => {
        let prefix = '';
        if (p.referenceModifier) prefix = p.referenceModifier + ' ';
        if (p.isVariadic) prefix = 'params ';
        return `${prefix}${p.type} ${p.name}${p.defaultValue ? ' = ' + p.defaultValue : ''}`;
    }).join(', ');

    signature.signature = `${modifierStr ? modifierStr + ' ' : ''}${returnType} ${name}(${paramStr})`.trim();

    return signature;
}

// --- Tree-sitter Visitor ---
class CSharpAstVisitor {
    public nodes: AstNode[] = [];
    public relationships: RelationshipInfo[] = [];
    private instanceCounter: InstanceCounter = { count: 0 };
    private fileNode: AstNode;
    private now: string = new Date().toISOString();
    private currentNamespace: string | null = null;
    private currentNamespaceId: string | null = null; // Store entityId of namespace
    private currentContainerId: string | null = null; // Class, Struct, Interface entityId

    constructor(private filepath: string, private sourceText: string) {
        const filename = path.basename(filepath);
        const fileEntityId = generateEntityId('file', filepath);
        this.fileNode = {
            id: generateInstanceId(this.instanceCounter, 'file', filename),
            entityId: fileEntityId, kind: 'File', name: filename, filePath: filepath,
            startLine: 1, endLine: 0, startColumn: 0, endColumn: 0,
            language: 'C#', createdAt: this.now,
        };
        this.nodes.push(this.fileNode);
    }

    // Corrected visit method: process node, then always recurse
    visit(node: Parser.SyntaxNode) {
        const originalNamespaceId = this.currentNamespaceId; // Backup context
        const originalContainerId = this.currentContainerId; // Backup context

        const stopRecursion = this.visitNode(node); // Process the current node first

        if (!stopRecursion) { // Only recurse if the handler didn't stop it
            for (const child of node.namedChildren) {
                this.visit(child);
            }
        }

        // Restore context if we are exiting the node where it was set
        if (this.currentNamespaceId !== originalNamespaceId && node.type === 'namespace_declaration') {
             this.currentNamespaceId = originalNamespaceId;
        }
         if (this.currentContainerId !== originalContainerId && ['class_declaration', 'interface_declaration', 'struct_declaration'].includes(node.type)) {
             this.currentContainerId = originalContainerId;
         }


        if (node.type === 'compilation_unit') { // Root node type for C#
             this.fileNode.endLine = node.endPosition.row + 1;
             this.fileNode.loc = this.fileNode.endLine;
        }
    }

    // Helper to decide if recursion should stop for certain node types
    private shouldStopRecursion(node: Parser.SyntaxNode): boolean {
        // Stop recursion after handling the entire import block here
        return node.type === 'using_directive'; // Using directives don't have relevant children to recurse into here
    }


    private visitNode(node: Parser.SyntaxNode): boolean { // Return boolean to indicate if recursion should stop
        try {
            switch (node.type) {
                case 'namespace_declaration':
                    this.visitNamespaceDeclaration(node);
                    return false; // Allow recursion
                case 'using_directive':
                    this.visitUsingDirective(node);
                    return true; // Stop recursion
                case 'class_declaration':
                    this.visitContainerDeclaration(node, 'CSharpClass');
                    return false; // Allow recursion
                case 'interface_declaration':
                     this.visitContainerDeclaration(node, 'CSharpInterface');
                     return false; // Allow recursion
                case 'struct_declaration':
                     this.visitContainerDeclaration(node, 'CSharpStruct');
                     return false; // Allow recursion
                case 'method_declaration':
                     this.visitMethodDeclaration(node);
                     return false; // Allow recursion
                case 'property_declaration':
                     this.visitPropertyDeclaration(node);
                     return false; // Allow recursion
                case 'field_declaration':
                     this.visitFieldDeclaration(node);
                     return false; // Allow recursion
                default:
                    return false; // Allow recursion for unhandled types
            }
        } catch (error: any) {
             logger.warn(`[CSharpAstVisitor] Error visiting node type ${node.type} in ${this.filepath}: ${error.message}`);
             return false; // Allow recursion even on error
        }
    }

    private visitNamespaceDeclaration(node: Parser.SyntaxNode) {
        const location = getNodeLocation(node);
        const nameNode = node.childForFieldName('name');
        const name = getNodeText(nameNode);
        if (!name) return;

        this.currentNamespace = name;
        const entityId = generateEntityId('namespacedeclaration', `${this.filepath}:${name}`);
        this.currentNamespaceId = entityId;

        const nsNode: NamespaceDeclarationNode = {
            id: generateInstanceId(this.instanceCounter, 'namespace', name, { line: location.startLine, column: location.startColumn }),
            entityId: entityId, kind: 'NamespaceDeclaration', name: name,
            filePath: this.filepath, language: 'C#', ...location, createdAt: this.now,
        };
        this.nodes.push(nsNode);

        const relEntityId = generateEntityId('declares_namespace', `${this.fileNode.entityId}:${entityId}`);
        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, 'declares_namespace', `${this.fileNode.id}:${nsNode.id}`),
            entityId: relEntityId, type: 'DECLARES_NAMESPACE',
            sourceId: this.fileNode.entityId, targetId: entityId,
            createdAt: this.now, weight: 9,
        });
    }

    private visitUsingDirective(node: Parser.SyntaxNode) {
        const location = getNodeLocation(node);
        const aliasNode = node.childForFieldName('alias');
        const alias = aliasNode ? getNodeText(aliasNode.childForFieldName('name')) : undefined;
        const isStatic = node.children.some((c: Parser.SyntaxNode) => c.type === 'static');

        // Find the first named child that is an identifier or qualified name
        const nameNode = node.namedChildren.find(c => c.type === 'identifier' || c.type === 'qualified_name');
        const namespaceOrType = getNodeText(nameNode);

        if (!namespaceOrType) {
             logger.warn(`[CSharpAstVisitor] Could not extract name for using_directive at ${this.filepath}:${location.startLine}`);
             return;
        }

        const entityId = generateEntityId('usingdirective', `${this.filepath}:${namespaceOrType}:${location.startLine}`);
        const usingNode: UsingDirectiveNode = {
            id: generateInstanceId(this.instanceCounter, 'using', namespaceOrType, { line: location.startLine, column: location.startColumn }),
            entityId: entityId, kind: 'UsingDirective', name: namespaceOrType,
            filePath: this.filepath, language: 'C#', ...location, createdAt: this.now,
            properties: { namespaceOrType, isStatic, alias }
        };
        this.nodes.push(usingNode);

        const relEntityId = generateEntityId('csharp_using', `${this.fileNode.entityId}:${entityId}`);
        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, 'csharp_using', `${this.fileNode.id}:${usingNode.id}`),
            entityId: relEntityId, type: 'CSHARP_USING',
            sourceId: this.fileNode.entityId, targetId: entityId,
            createdAt: this.now, weight: 5,
        });
    }

    private visitContainerDeclaration(node: Parser.SyntaxNode, kind: 'CSharpClass' | 'CSharpInterface' | 'CSharpStruct') {
        const location = getNodeLocation(node);
        const nameNode = node.childForFieldName('name');
        const name = getNodeText(nameNode);
        if (!name) return;

        const qualifiedName = this.currentNamespace ? `${this.currentNamespace}.${name}` : name;
        const entityId = generateEntityId(kind.toLowerCase(), qualifiedName);

        // Extract documentation
        const documentationInfo = extractCSharpDocumentationInfo(node, this.sourceText);
        const docTags = documentationInfo?.tags || [];

        const containerNode: AstNode = {
            id: generateInstanceId(this.instanceCounter, kind.toLowerCase(), name, { line: location.startLine, column: location.startColumn }),
            entityId: entityId, kind: kind, name: name,
            filePath: this.filepath, language: 'C#', ...location, createdAt: this.now,
            properties: { qualifiedName },
            parentId: this.currentNamespaceId ?? undefined,
            // Documentation
            documentation: documentationInfo?.summary,
            docComment: documentationInfo?.rawComment,
            documentationInfo: documentationInfo,
            tags: docTags.length > 0 ? docTags : undefined,
        };
        this.nodes.push(containerNode);
        this.currentContainerId = entityId;

        const parentNodeId = this.currentNamespaceId ?? this.fileNode.entityId;
        const relType = kind === 'CSharpClass' ? 'DEFINES_CLASS' : (kind === 'CSharpInterface' ? 'DEFINES_INTERFACE' : 'DEFINES_STRUCT');
        const relEntityId = generateEntityId(relType.toLowerCase(), `${parentNodeId}:${entityId}`);
        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, relType.toLowerCase(), `${parentNodeId}:${containerNode.id}`),
            entityId: relEntityId, type: relType,
            sourceId: parentNodeId, targetId: entityId,
            createdAt: this.now, weight: 9,
        });

        // TODO: Add relationships for base types
    }

     private visitMethodDeclaration(node: Parser.SyntaxNode) {
        if (!this.currentContainerId) return;

        const location = getNodeLocation(node);
        const nameNode = node.childForFieldName('name');
        const name = getNodeText(nameNode);
        if (!name) return;

        // Extract complete signature information
        const signatureInfo = buildCSharpMethodSignature(name, node, false);

        // Extract documentation
        const documentationInfo = extractCSharpDocumentationInfo(node, this.sourceText);
        const docTags = documentationInfo?.tags || [];

        const methodEntityId = generateEntityId('csharpmethod', `${this.currentContainerId}.${name}`);
        const methodNode: CSharpMethodNode = {
            id: generateInstanceId(this.instanceCounter, 'csharpmethod', name, { line: location.startLine, column: location.startColumn }),
            entityId: methodEntityId, kind: 'CSharpMethod', name: name,
            filePath: this.filepath, language: 'C#', ...location, createdAt: this.now,
            parentId: this.currentContainerId,
            // Signature information
            signatureInfo,
            // Documentation
            documentation: documentationInfo?.summary,
            docComment: documentationInfo?.rawComment,
            documentationInfo: documentationInfo,
            tags: docTags.length > 0 ? docTags : undefined,
            // Also set top-level properties for backward compatibility
            returnType: signatureInfo.returnType,
            visibility: signatureInfo.visibility === 'default' ? 'private' : signatureInfo.visibility as 'public' | 'private' | 'protected' | 'internal',
            isStatic: signatureInfo.isStatic,
            isAsync: signatureInfo.isAsync,
            isAbstract: signatureInfo.isAbstract,
            modifierFlags: signatureInfo.modifiers,
        };
        this.nodes.push(methodNode);

        // Relationship: Container -> HAS_METHOD -> Method
        const relEntityId = generateEntityId('has_method', `${this.currentContainerId}:${methodEntityId}`);
        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, 'has_method', `${this.currentContainerId}:${methodNode.id}`),
            entityId: relEntityId, type: 'HAS_METHOD',
            sourceId: this.currentContainerId, targetId: methodEntityId,
            createdAt: this.now, weight: 8,
        });
    }

     private visitPropertyDeclaration(node: Parser.SyntaxNode) {
        if (!this.currentContainerId) return;

        // Reverting static check for now
        // const modifiersNode = node.children.find(c => c.type === 'modifiers');
        // const isStatic = modifiersNode?.children.some(m => m.type === 'modifier' && m.text === 'static') ?? false;
        // if (isStatic) {
        //     return;
        // }

        const location = getNodeLocation(node);
        const nameNode = node.childForFieldName('name');
        const name = getNodeText(nameNode);
        if (!name) return;

        // Extract documentation
        const documentationInfo = extractCSharpDocumentationInfo(node, this.sourceText);
        const docTags = documentationInfo?.tags || [];

        const propEntityId = generateEntityId('property', `${this.currentContainerId}.${name}`);
        const propNode: PropertyNode = {
            id: generateInstanceId(this.instanceCounter, 'property', name, { line: location.startLine, column: location.startColumn }),
            entityId: propEntityId, kind: 'Property', name: name,
            filePath: this.filepath, language: 'C#', ...location, createdAt: this.now,
            parentId: this.currentContainerId,
            // Documentation
            documentation: documentationInfo?.summary,
            docComment: documentationInfo?.rawComment,
            documentationInfo: documentationInfo,
            tags: docTags.length > 0 ? docTags : undefined,
            // TODO: Extract type, modifiers, getter/setter info
        };
        this.nodes.push(propNode);

        // Relationship: Container -> HAS_PROPERTY -> Property
        const relEntityId = generateEntityId('has_property', `${this.currentContainerId}:${propEntityId}`);
        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, 'has_property', `${this.currentContainerId}:${propNode.id}`),
            entityId: relEntityId, type: 'HAS_PROPERTY',
            sourceId: this.currentContainerId, targetId: propEntityId,
            createdAt: this.now, weight: 7,
        });
    }

     private visitFieldDeclaration(node: Parser.SyntaxNode) {
        if (!this.currentContainerId) return;

        // Reverting static check for now
        // const modifiersNode = node.children.find(c => c.type === 'modifiers');
        // const isStatic = modifiersNode?.children.some(m => m.type === 'modifier' && m.text === 'static') ?? false;
        // if (isStatic) {
        //      return;
        // }

        const location = getNodeLocation(node);
        // Field declaration can have multiple variables (e.g., public int x, y;)
        const declarationNode = node.childForFieldName('declaration'); // Or similar based on grammar
        if (!declarationNode) return;

        // Extract documentation (applies to all declarators in the field)
        const documentationInfo = extractCSharpDocumentationInfo(node, this.sourceText);
        const docTags = documentationInfo?.tags || [];

        for (const declarator of declarationNode.namedChildren) {
             if (declarator.type === 'variable_declarator') {
                 const nameNode = declarator.childForFieldName('name');
                 const name = getNodeText(nameNode);
                 if (!name) continue;

                 const fieldEntityId = generateEntityId('field', `${this.currentContainerId}.${name}`);
                 const fieldNode: FieldNode = {
                     id: generateInstanceId(this.instanceCounter, 'field', name, { line: location.startLine, column: location.startColumn }),
                     entityId: fieldEntityId, kind: 'Field', name: name,
                     filePath: this.filepath, language: 'C#', ...location, createdAt: this.now,
                     parentId: this.currentContainerId,
                     // Documentation
                     documentation: documentationInfo?.summary,
                     docComment: documentationInfo?.rawComment,
                     documentationInfo: documentationInfo,
                     tags: docTags.length > 0 ? docTags : undefined,
                     // TODO: Extract type, modifiers
                 };
                 this.nodes.push(fieldNode);

                 // Relationship: Container -> HAS_FIELD -> Field
                 const relEntityId = generateEntityId('has_field', `${this.currentContainerId}:${fieldEntityId}`);
                 this.relationships.push({
                     id: generateInstanceId(this.instanceCounter, 'has_field', `${this.currentContainerId}:${fieldNode.id}`),
                     entityId: relEntityId, type: 'HAS_FIELD',
                     sourceId: this.currentContainerId, targetId: fieldEntityId,
                     createdAt: this.now, weight: 7,
                 });
             }
        }
    }
}

/**
 * Parses C# files using Tree-sitter.
 */
export class CSharpParser {
    private parser: Parser;

    constructor() {
        this.parser = new Parser();
        this.parser.setLanguage(CSharp as any); // Cast to any to bypass type conflict
        logger.debug('C# Tree-sitter Parser initialized');
    }

    /**
     * Parses a single C# file.
     */
    async parseFile(file: FileInfo): Promise<string> {
        logger.info(`[CSharpParser] Starting C# parsing for: ${file.name}`);
        await ensureTempDir();
        const tempFilePath = getTempFilePath(file.path);
        const absoluteFilePath = path.resolve(file.path);
        const normalizedFilePath = absoluteFilePath.replace(/\\/g, '/');

        try {
            const fileContent = await fs.readFile(absoluteFilePath, 'utf-8');
            const tree = this.parser.parse(fileContent);
            const visitor = new CSharpAstVisitor(normalizedFilePath, fileContent);
            visitor.visit(tree.rootNode);

            const result: SingleFileParseResult = {
                filePath: normalizedFilePath,
                nodes: visitor.nodes,
                relationships: visitor.relationships,
            };

            await fs.writeFile(tempFilePath, JSON.stringify(result, null, 2));
            logger.info(`[CSharpParser] Pass 1 completed for: ${file.name}. Nodes: ${result.nodes.length}, Rels: ${result.relationships.length}. Saved to ${path.basename(tempFilePath)}`);
            return tempFilePath;

        } catch (error: any) {
            logger.error(`[CSharpParser] Error during C# Pass 1 for ${file.path}`, {
                 errorMessage: error.message, stack: error.stack?.substring(0, 500)
            });
            try { await fs.unlink(tempFilePath); } catch { /* ignore */ }
            throw new ParserError(`Failed C# Pass 1 parsing for ${file.path}`, { originalError: error });
        }
    }
}