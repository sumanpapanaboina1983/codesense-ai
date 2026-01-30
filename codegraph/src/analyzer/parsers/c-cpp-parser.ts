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
import { AstNode, RelationshipInfo, SingleFileParseResult, InstanceCounter, IncludeDirectiveNode, CFunctionNode, CppClassNode, CppMethodNode, MethodSignature, ParameterInfo, generateShortSignature, DocTag, DocumentationInfo } from '../types.js'; // Added CppClassNode & CppMethodNode, signature types, doc types
import { ensureTempDir, getTempFilePath, generateInstanceId, generateEntityId } from '../parser-utils.js';

const logger = createContextLogger('CCppParser');

// Helper to get node text safely
function getNodeText(node: Parser.SyntaxNode | null | undefined): string {
    return node?.text ?? '';
}

// Helper to get location
function getNodeLocation(node: Parser.SyntaxNode): { startLine: number, endLine: number, startColumn: number, endColumn: number } {
    // Tree-sitter positions are 0-based, AstNode expects 1-based lines
    return {
        startLine: node.startPosition.row + 1,
        endLine: node.endPosition.row + 1,
        startColumn: node.startPosition.column,
        endColumn: node.endPosition.column,
    };
}

/**
 * Extract Doxygen comments preceding a declaration node.
 * Supports: /** *\/, /*! *\/, ///, //!
 */
function extractDoxygenComment(node: Parser.SyntaxNode, sourceText: string): { rawComment: string; content: string } | null {
    // Get all previous siblings that are comments
    const comments: string[] = [];
    let prevSibling = node.previousSibling;

    while (prevSibling) {
        if (prevSibling.type === 'comment') {
            const commentText = getNodeText(prevSibling);

            // Check if the comment is on the line immediately before
            const commentEndLine = prevSibling.endPosition.row;
            const nextNodeStartLine = prevSibling.nextSibling?.startPosition.row ?? node.startPosition.row;

            // Only include if there's no blank line between comments
            if (nextNodeStartLine - commentEndLine <= 1) {
                // Check for Doxygen block comment: /** or /*!
                if (commentText.startsWith('/**') || commentText.startsWith('/*!')) {
                    // Remove delimiters and return
                    const content = cleanDoxygenBlockComment(commentText);
                    return { rawComment: commentText, content };
                }

                // Check for Doxygen line comment: /// or //!
                if (commentText.startsWith('///') || commentText.startsWith('//!')) {
                    const cleanComment = commentText.replace(/^\/\/[\/!]\s?/, '').trim();
                    comments.unshift(cleanComment);
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
    const content = comments.join('\n');

    return { rawComment, content };
}

/**
 * Clean a Doxygen block comment by removing delimiters and line prefixes.
 */
function cleanDoxygenBlockComment(comment: string): string {
    // Remove /** or /*! and */
    let content = comment.replace(/^\/\*[\*!]\s?/, '').replace(/\s*\*\/$/, '');

    // Split into lines and clean each line
    const lines = content.split('\n').map(line => {
        // Remove leading * and whitespace
        return line.replace(/^\s*\*\s?/, '').trim();
    });

    return lines.filter(line => line.length > 0).join('\n');
}

/**
 * Parse Doxygen tags from comment content.
 * Supports both @ and \ style tags.
 */
function parseDoxygenTags(content: string): DocTag[] {
    const tags: DocTag[] = [];

    if (!content) {
        return tags;
    }

    // Normalize \ to @ for easier parsing
    const normalizedContent = content.replace(/\\(param|return|returns|throws|throw|brief|details?|deprecated|author|version|since|see|example|note|warning|todo|bug|file|class|struct|fn)/g, '@$1');

    // Parse @param tags: @param name description
    const paramRegex = /@param\s+(?:\[(?:in|out|in,out)\]\s+)?(\w+)\s+([\s\S]*?)(?=@\w+|$)/gi;
    let match;
    while ((match = paramRegex.exec(normalizedContent)) !== null) {
        tags.push({
            tag: 'param',
            name: match[1],
            description: match[2].trim().replace(/\s+/g, ' '),
        });
    }

    // Parse @return/@returns tags
    const returnRegex = /@returns?\s+([\s\S]*?)(?=@\w+|$)/gi;
    while ((match = returnRegex.exec(normalizedContent)) !== null) {
        tags.push({
            tag: 'returns',
            description: match[1].trim().replace(/\s+/g, ' '),
        });
    }

    // Parse @throws/@throw tags: @throws ExceptionType description
    const throwsRegex = /@throws?\s+(\w+)\s+([\s\S]*?)(?=@\w+|$)/gi;
    while ((match = throwsRegex.exec(normalizedContent)) !== null) {
        tags.push({
            tag: 'throws',
            type: match[1],
            description: match[2].trim().replace(/\s+/g, ' '),
        });
    }

    // Parse @deprecated
    const deprecatedRegex = /@deprecated\s*([\s\S]*?)(?=@\w+|$)/gi;
    while ((match = deprecatedRegex.exec(normalizedContent)) !== null) {
        tags.push({
            tag: 'deprecated',
            description: match[1].trim().replace(/\s+/g, ' ') || 'This is deprecated',
        });
    }

    // Parse @author
    const authorRegex = /@author\s+([\s\S]*?)(?=@\w+|$)/gi;
    while ((match = authorRegex.exec(normalizedContent)) !== null) {
        tags.push({
            tag: 'author',
            description: match[1].trim().replace(/\s+/g, ' '),
        });
    }

    // Parse @version
    const versionRegex = /@version\s+([\s\S]*?)(?=@\w+|$)/gi;
    while ((match = versionRegex.exec(normalizedContent)) !== null) {
        tags.push({
            tag: 'version',
            description: match[1].trim().replace(/\s+/g, ' '),
        });
    }

    // Parse @since
    const sinceRegex = /@since\s+([\s\S]*?)(?=@\w+|$)/gi;
    while ((match = sinceRegex.exec(normalizedContent)) !== null) {
        tags.push({
            tag: 'since',
            description: match[1].trim().replace(/\s+/g, ' '),
        });
    }

    // Parse @see
    const seeRegex = /@see\s+([\s\S]*?)(?=@\w+|$)/gi;
    while ((match = seeRegex.exec(normalizedContent)) !== null) {
        tags.push({
            tag: 'see',
            description: match[1].trim().replace(/\s+/g, ' '),
        });
    }

    // Parse @example
    const exampleRegex = /@example\s+([\s\S]*?)(?=@\w+|$)/gi;
    while ((match = exampleRegex.exec(normalizedContent)) !== null) {
        tags.push({
            tag: 'example',
            description: match[1].trim(),
        });
    }

    // Parse @note
    const noteRegex = /@note\s+([\s\S]*?)(?=@\w+|$)/gi;
    while ((match = noteRegex.exec(normalizedContent)) !== null) {
        tags.push({
            tag: 'note',
            description: match[1].trim().replace(/\s+/g, ' '),
        });
    }

    // Parse @warning
    const warningRegex = /@warning\s+([\s\S]*?)(?=@\w+|$)/gi;
    while ((match = warningRegex.exec(normalizedContent)) !== null) {
        tags.push({
            tag: 'warning',
            description: match[1].trim().replace(/\s+/g, ' '),
        });
    }

    // Parse @todo
    const todoRegex = /@todo\s+([\s\S]*?)(?=@\w+|$)/gi;
    while ((match = todoRegex.exec(normalizedContent)) !== null) {
        tags.push({
            tag: 'todo',
            description: match[1].trim().replace(/\s+/g, ' '),
        });
    }

    return tags;
}

/**
 * Extract brief/summary from Doxygen content.
 */
function extractDoxygenSummary(content: string): string {
    if (!content) {
        return '';
    }

    // Normalize \ to @
    const normalizedContent = content.replace(/\\brief\s+/g, '@brief ').replace(/\\details?\s+/g, '@details ');

    // Try to find @brief tag
    const briefMatch = normalizedContent.match(/@brief\s+([\s\S]*?)(?=@\w+|$)/i);
    if (briefMatch) {
        return briefMatch[1].trim().replace(/\s+/g, ' ');
    }

    // If no @brief, take the first paragraph (text before first @tag or blank line)
    const lines = content.split('\n');
    const summaryLines: string[] = [];

    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('@') || trimmed.startsWith('\\')) {
            break;
        }
        summaryLines.push(trimmed);
    }

    return summaryLines.join(' ');
}

/**
 * Extract complete documentation info from a C/C++ node.
 */
function extractDoxygenDocumentationInfo(node: Parser.SyntaxNode, sourceText: string): DocumentationInfo | undefined {
    const docComment = extractDoxygenComment(node, sourceText);
    if (!docComment) {
        return undefined;
    }

    const tags = parseDoxygenTags(docComment.content);
    const summary = extractDoxygenSummary(docComment.content);

    // Extract specific metadata from tags
    const isDeprecated = tags.some(t => t.tag === 'deprecated');
    const deprecationReason = tags.find(t => t.tag === 'deprecated')?.description;
    const seeAlso = tags.filter(t => t.tag === 'see').map(t => t.description).filter(Boolean) as string[];
    const examples = tags.filter(t => t.tag === 'example').map(t => t.description).filter(Boolean) as string[];
    const authors = tags.filter(t => t.tag === 'author').map(t => t.description).filter(Boolean) as string[];
    const version = tags.find(t => t.tag === 'version')?.description;
    const since = tags.find(t => t.tag === 'since')?.description;

    return {
        summary: summary || undefined,
        rawComment: docComment.rawComment,
        tags,
        format: 'doxygen',
        isDeprecated: isDeprecated || undefined,
        deprecationReason,
        seeAlso: seeAlso.length > 0 ? seeAlso : undefined,
        examples: examples.length > 0 ? examples : undefined,
        authors: authors.length > 0 ? authors : undefined,
        version,
        since,
    };
}

// C/C++ storage class and type modifiers
const CPP_STORAGE_MODIFIERS = ['static', 'extern', 'register', 'mutable', 'thread_local'];
const CPP_FUNCTION_MODIFIERS = ['inline', 'virtual', 'explicit', 'constexpr', 'consteval', 'friend'];
const CPP_QUALIFIER_MODIFIERS = ['const', 'volatile', 'noexcept'];

/**
 * Extract parameters from a C/C++ function declaration.
 * C/C++ format: void foo(int a, const char* b, ...)
 */
function extractCppParameters(node: Parser.SyntaxNode): ParameterInfo[] {
    const parameters: ParameterInfo[] = [];

    // Find the declarator, then the parameter_list
    const declarator = node.childForFieldName('declarator');
    if (!declarator) return parameters;

    const paramList = declarator.childForFieldName('parameters');
    if (!paramList) return parameters;

    let position = 0;
    for (const child of paramList.namedChildren) {
        if (child.type === 'parameter_declaration') {
            // Get type from the type specifier(s)
            const typeNode = child.childForFieldName('type');
            let paramType = getNodeText(typeNode) || 'auto';

            // Get declarator which may contain pointer/reference modifiers
            const paramDeclarator = child.childForFieldName('declarator');
            let paramName = '';

            if (paramDeclarator) {
                // Handle pointer declarators (*name), reference declarators (&name)
                if (paramDeclarator.type === 'pointer_declarator' ||
                    paramDeclarator.type === 'reference_declarator' ||
                    paramDeclarator.type === 'abstract_pointer_declarator' ||
                    paramDeclarator.type === 'abstract_reference_declarator') {
                    // Extract the inner identifier
                    const innerDecl = paramDeclarator.namedChildren.find(c => c.type === 'identifier');
                    paramName = getNodeText(innerDecl) || `_${position}`;
                    // Prepend pointer/reference to type
                    const prefix = paramDeclarator.type.includes('pointer') ? '*' : '&';
                    paramType = `${paramType}${prefix}`;
                } else if (paramDeclarator.type === 'identifier') {
                    paramName = getNodeText(paramDeclarator);
                } else {
                    paramName = getNodeText(paramDeclarator) || `_${position}`;
                }
            } else {
                paramName = `_${position}`;
            }

            // Check for const qualifier
            const hasConst = child.namedChildren.some(c =>
                c.type === 'type_qualifier' && getNodeText(c) === 'const');
            if (hasConst && !paramType.includes('const')) {
                paramType = `const ${paramType}`;
            }

            parameters.push({
                name: paramName,
                type: paramType,
                isOptional: false, // C++ doesn't have optional params (use default values)
                isVariadic: false,
                position,
            });
            position++;
        } else if (child.type === 'variadic_parameter') {
            // Handle ... (varargs)
            parameters.push({
                name: '...',
                type: '...',
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
 * Extract return type from a C/C++ function definition.
 */
function extractCppReturnType(node: Parser.SyntaxNode): string {
    const typeNode = node.childForFieldName('type');
    if (typeNode) {
        return getNodeText(typeNode);
    }

    // Check for type qualifiers (const, volatile) before type
    const qualifiers: string[] = [];
    for (const child of node.namedChildren) {
        if (child.type === 'type_qualifier') {
            qualifiers.push(getNodeText(child));
        }
        if (child.type === 'primitive_type' || child.type === 'type_identifier' ||
            child.type === 'sized_type_specifier') {
            const baseType = getNodeText(child);
            return qualifiers.length > 0 ? `${qualifiers.join(' ')} ${baseType}` : baseType;
        }
    }

    return 'void';
}

/**
 * Extract modifiers from a C/C++ function definition.
 */
function extractCppModifiers(node: Parser.SyntaxNode): {
    modifiers: string[];
    isStatic: boolean;
    isVirtual: boolean;
    isInline: boolean;
    isConst: boolean;
    isConstexpr: boolean;
    isExplicit: boolean;
    isOverride: boolean;
    isFinal: boolean;
    isNoexcept: boolean;
} {
    const result = {
        modifiers: [] as string[],
        isStatic: false,
        isVirtual: false,
        isInline: false,
        isConst: false,
        isConstexpr: false,
        isExplicit: false,
        isOverride: false,
        isFinal: false,
        isNoexcept: false,
    };

    // Check storage class and function specifiers
    for (const child of node.namedChildren) {
        const text = getNodeText(child);
        if (child.type === 'storage_class_specifier') {
            if (text === 'static') result.isStatic = true;
            result.modifiers.push(text);
        } else if (child.type === 'function_specifier' || child.type === 'virtual_specifier') {
            if (text === 'virtual') result.isVirtual = true;
            if (text === 'inline') result.isInline = true;
            if (text === 'explicit') result.isExplicit = true;
            if (text === 'constexpr') result.isConstexpr = true;
            if (text === 'override') result.isOverride = true;
            if (text === 'final') result.isFinal = true;
            result.modifiers.push(text);
        } else if (child.type === 'type_qualifier') {
            if (text === 'const') result.isConst = true;
            result.modifiers.push(text);
        } else if (child.type === 'noexcept') {
            result.isNoexcept = true;
            result.modifiers.push('noexcept');
        }
    }

    // Also check declarator for trailing modifiers (const, override, final after params)
    const declarator = node.childForFieldName('declarator');
    if (declarator) {
        for (const child of declarator.namedChildren) {
            const text = getNodeText(child);
            if (child.type === 'type_qualifier' && text === 'const') {
                result.isConst = true;
                if (!result.modifiers.includes('const')) result.modifiers.push('const');
            }
            if (child.type === 'virtual_specifier') {
                if (text === 'override') result.isOverride = true;
                if (text === 'final') result.isFinal = true;
                result.modifiers.push(text);
            }
        }
    }

    return result;
}

/**
 * Build a MethodSignature for a C/C++ function/method.
 */
function buildCppFunctionSignature(
    name: string,
    node: Parser.SyntaxNode,
    isMethod: boolean = false,
    language: 'C' | 'C++' = 'C++'
): MethodSignature {
    const parameters = extractCppParameters(node);
    const returnType = extractCppReturnType(node);
    const modifiers = extractCppModifiers(node);

    const signature: MethodSignature = {
        signature: '', // Will be generated below
        shortSignature: generateShortSignature(name, parameters),
        returnType,
        returnsVoid: returnType === 'void',
        parameters,
        parameterCount: parameters.length,
        visibility: 'public', // C++ default; TODO: track public/private/protected sections
        modifiers: modifiers.modifiers,
        isStatic: modifiers.isStatic,
        isAsync: false, // C++ doesn't have async keyword
        isAbstract: false, // Pure virtual = 0; TODO: detect
        isFinal: modifiers.isFinal,
        isVirtual: modifiers.isVirtual,
        isOverride: modifiers.isOverride,
        isConst: modifiers.isConst,
        isConstructor: false, // TODO: detect constructors
        isDestructor: name.startsWith('~'),
    };

    // Generate signature string
    const modifierStr = modifiers.modifiers.filter(m => m !== 'const').join(' ');
    const paramStr = parameters.map(p => `${p.type} ${p.name}`).join(', ');
    const constSuffix = modifiers.isConst ? ' const' : '';
    const overrideSuffix = modifiers.isOverride ? ' override' : '';
    const finalSuffix = modifiers.isFinal ? ' final' : '';

    signature.signature = `${modifierStr ? modifierStr + ' ' : ''}${returnType} ${name}(${paramStr})${constSuffix}${overrideSuffix}${finalSuffix}`.trim();

    return signature;
}

// --- Tree-sitter Visitor ---
class CCppAstVisitor {
    public nodes: AstNode[] = [];
    public relationships: RelationshipInfo[] = [];
    private instanceCounter: InstanceCounter = { count: 0 };
    private fileNode: AstNode; // Represents the file being parsed
    private now: string = new Date().toISOString();
    private currentClassEntityId: string | undefined = undefined; // Track current class context (use undefined)

    constructor(private filepath: string, private language: 'C' | 'C++', private sourceText: string) {
        // Create the File node representation for this parse
        const filename = path.basename(filepath);
        const fileEntityId = generateEntityId('file', filepath); // Use 'file' kind for consistency
        this.fileNode = {
            id: generateInstanceId(this.instanceCounter, 'file', filename),
            entityId: fileEntityId,
            kind: 'File', // Use standard 'File' kind
            name: filename,
            filePath: filepath,
            startLine: 1, // File starts at 1
            endLine: 0, // Will be updated after parsing
            startColumn: 0,
            endColumn: 0,
            language: language,
            createdAt: this.now,
        };
        this.nodes.push(this.fileNode);
    }

    visit(node: Parser.SyntaxNode) {
        // Process the current node first
        this.visitNode(node); // Always process the node

        // Always recurse into children, let visitNode handle specific logic
        for (const child of node.namedChildren) {
            this.visit(child);
        }

        // Update file end line after visiting all nodes
        if (node.type === 'translation_unit') { // Root node type for C/C++
             this.fileNode.endLine = node.endPosition.row + 1;
             this.fileNode.loc = this.fileNode.endLine;
        }
    }

    // Returns true if the node type was handled and recursion should potentially stop, false otherwise
    private visitNode(node: Parser.SyntaxNode): boolean {
        try {
            switch (node.type) {
                case 'preproc_include':
                case 'preproc_def':
                    this.visitIncludeOrDefine(node);
                    return true; // Handled, stop recursion here
                case 'namespace_definition':
                     return false; // Allow recursion into namespace body
                case 'function_definition':
                    // Workaround for grammar issue: Check if it looks like a class/struct/namespace
                    const nodeText = node.text;
                    if (nodeText.startsWith('class ') || nodeText.startsWith('struct ')) {
                        // logger.warn(`[CCppAstVisitor] Treating misidentified function_definition at ${this.filepath}:${node.startPosition.row + 1} as class/struct.`);
                        this.visitClassSpecifier(node); // Try processing as class
                        return false; // Allow recursion
                    } else if (nodeText.startsWith('namespace ')) {
                         // logger.warn(`[CCppAstVisitor] Treating misidentified function_definition at ${this.filepath}:${node.startPosition.row + 1} as namespace.`);
                         return false; // Allow recursion
                    }
                    // If it's likely a real function, process it
                    this.visitFunctionDefinition(node);
                    return false; // Allow recursion into function body
                case 'class_specifier':
                    this.visitClassSpecifier(node);
                    return false; // Allow recursion into class body/members
                // Add cases for struct_specifier, etc. later
                default:
                    return false; // Not specifically handled, allow generic recursion
            }
        } catch (error: any) {
             logger.warn(`[CCppAstVisitor] Error visiting node type ${node.type} in ${this.filepath}: ${error.message}`);
             return false; // Continue traversal even if one node fails
        }
    }

    private visitIncludeOrDefine(node: Parser.SyntaxNode) {
        const location = getNodeLocation(node);
        let name = 'unknown_directive';
        let kind: 'IncludeDirective' | 'MacroDefinition' = 'IncludeDirective'; // Default, adjust later
        let properties: Record<string, any> = {};

        if (node.type === 'preproc_include') {
            kind = 'IncludeDirective';
            const pathNode = node.childForFieldName('path');
            const includePath = getNodeText(pathNode);
            const isSystemInclude = includePath.startsWith('<') && includePath.endsWith('>');
            name = includePath; // Use the path as the name for includes
            properties = {
                includePath: includePath.substring(1, includePath.length - 1), // Remove <> or ""
                isSystemInclude: isSystemInclude,
            };
        } else if (node.type === 'preproc_def') {
            kind = 'MacroDefinition'; // Placeholder kind
            name = getNodeText(node.childForFieldName('name'));
            properties = { value: getNodeText(node.childForFieldName('value')) };
        }

        const entityId = generateEntityId(kind.toLowerCase(), `${this.filepath}:${name}:${location.startLine}`);
        const directiveNode: AstNode = { // Use base AstNode, cast later if needed
            id: generateInstanceId(this.instanceCounter, kind.toLowerCase(), name, { line: location.startLine, column: location.startColumn }),
            entityId: entityId,
            kind: kind,
            name: name,
            filePath: this.filepath,
            language: this.language,
            ...location,
            createdAt: this.now,
            properties: properties,
        };
        this.nodes.push(directiveNode);

        // Add INCLUDES relationship (File -> IncludeDirective/MacroDefinition)
        if (kind === 'IncludeDirective') {
            const relEntityId = generateEntityId('includes', `${this.fileNode.entityId}:${entityId}`);
            this.relationships.push({
                id: generateInstanceId(this.instanceCounter, 'includes', `${this.fileNode.id}:${directiveNode.id}`),
                entityId: relEntityId,
                type: 'INCLUDES',
                sourceId: this.fileNode.entityId,
                targetId: entityId,
                createdAt: this.now,
                weight: 5,
            });
        }
    }

     private visitFunctionDefinition(node: Parser.SyntaxNode) {
        const location = getNodeLocation(node);
        const declarator = node.childForFieldName('declarator');
        const nameNode = declarator?.childForFieldName('declarator'); // Function name is often nested
        const name = getNodeText(nameNode);

        if (!name) {
             logger.debug(`[CCppAstVisitor] Skipping function_definition without a clear name at ${this.filepath}:${location.startLine}`);
             return; // Skip anonymous or malformed/misidentified
        }

        // Determine if it's a method (inside a class) or a standalone function
        const kind: 'CFunction' | 'CppMethod' = this.currentClassEntityId ? 'CppMethod' : 'CFunction';
        const parentId = this.currentClassEntityId; // undefined if not in a class

        // Extract complete signature information
        const signatureInfo = buildCppFunctionSignature(name, node, kind === 'CppMethod', this.language);

        // Extract documentation
        const documentationInfo = extractDoxygenDocumentationInfo(node, this.sourceText);
        const docTags = documentationInfo?.tags || [];

        const entityId = generateEntityId(kind.toLowerCase(), `${this.filepath}:${name}:${location.startLine}`);

        // Create the base object with signature info
        const baseFuncNode = {
            id: generateInstanceId(this.instanceCounter, kind.toLowerCase(), name, { line: location.startLine, column: location.startColumn }),
            entityId: entityId,
            kind: kind,
            name: name,
            filePath: this.filepath,
            language: this.language,
            ...location,
            loc: location.endLine - location.startLine + 1,
            createdAt: this.now,
            parentId: parentId, // Link method to class (undefined is fine)
            // Signature information
            signatureInfo,
            // Documentation
            documentation: documentationInfo?.summary,
            docComment: documentationInfo?.rawComment,
            documentationInfo: documentationInfo,
            tags: docTags.length > 0 ? docTags : undefined,
            // Also set top-level properties for backward compatibility
            returnType: signatureInfo.returnType,
            isStatic: signatureInfo.isStatic,
            modifierFlags: signatureInfo.modifiers,
        };

        // Explicitly cast based on kind before pushing
        let funcNode: CFunctionNode | CppMethodNode;
        if (kind === 'CppMethod') {
            funcNode = baseFuncNode as CppMethodNode;
        } else {
            funcNode = baseFuncNode as CFunctionNode;
        }
        this.nodes.push(funcNode);


        // Add relationship File -> CFunction (DEFINES_FUNCTION) or Class -> CppMethod (HAS_METHOD)
        if (kind === 'CppMethod' && parentId) {
            const relEntityId = generateEntityId('has_method', `${parentId}:${entityId}`);
            this.relationships.push({
                id: generateInstanceId(this.instanceCounter, 'has_method', `${parentId}:${funcNode.id}`),
                entityId: relEntityId, type: 'HAS_METHOD',
                sourceId: parentId, targetId: entityId,
                createdAt: this.now, weight: 8,
            });
        } else if (kind === 'CFunction') {
            const relEntityId = generateEntityId('defines_function', `${this.fileNode.entityId}:${entityId}`);
            this.relationships.push({
                id: generateInstanceId(this.instanceCounter, 'defines_function', `${this.fileNode.id}:${funcNode.id}`),
                entityId: relEntityId, type: 'DEFINES_FUNCTION',
                sourceId: this.fileNode.entityId, targetId: entityId,
                createdAt: this.now, weight: 8,
            });
        }

        // Context restoration for nested functions/classes needs careful handling
        // For now, we let the main visit loop handle body recursion
    }

    private visitClassSpecifier(node: Parser.SyntaxNode) {
        const location = getNodeLocation(node);
        // Try standard name field first
        let nameNode: Parser.SyntaxNode | null | undefined = node.childForFieldName('name');

        // Workaround: If nameNode is null AND the original type was function_definition,
        // find the 'identifier' child that follows the 'type_identifier' child.
        if (!nameNode && node.type === 'function_definition') {
            let typeIdentifierFound = false;
            for (const child of node.namedChildren) {
                if (child.type === 'type_identifier') {
                    typeIdentifierFound = true;
                } else if (typeIdentifierFound && child.type === 'identifier') {
                    nameNode = child;
                    logger.debug(`[CCppAstVisitor] Using identifier child as name for misidentified class at ${this.filepath}:${location.startLine}`);
                    break;
                }
            }
        }

        const name = getNodeText(nameNode);

        if (!name) {
            logger.warn(`[CCppAstVisitor] Skipping class_specifier/misidentified node without a name at ${this.filepath}:${location.startLine}`);
            return; // Skip anonymous classes or nodes we can't name
        }

        const originalClassId = this.currentClassEntityId; // Save outer class context if nested

        const entityId = generateEntityId('cppclass', `${this.filepath}:${name}`);
        // logger.debug(`[CCppAstVisitor] Found class: ${name}, EntityId: ${entityId}`);

        // Extract documentation
        const documentationInfo = extractDoxygenDocumentationInfo(node, this.sourceText);
        const docTags = documentationInfo?.tags || [];

        const classNode: CppClassNode = {
            id: generateInstanceId(this.instanceCounter, 'cppclass', name, { line: location.startLine, column: location.startColumn }),
            entityId: entityId,
            kind: 'CppClass',
            name: name,
            filePath: this.filepath,
            language: 'C++', // Explicitly set to C++ for CppClassNode
            ...location,
            createdAt: this.now,
            // Documentation
            documentation: documentationInfo?.summary,
            docComment: documentationInfo?.rawComment,
            documentationInfo: documentationInfo,
            tags: docTags.length > 0 ? docTags : undefined,
            // TODO: Handle inheritance (base_clause)
        };
        this.nodes.push(classNode);
        this.currentClassEntityId = entityId; // Set context for methods/nested members

        // Add relationship File -> CppClass (DEFINES_CLASS)
        const relEntityId = generateEntityId('defines_class', `${this.fileNode.entityId}:${entityId}`);
        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, 'defines_class', `${this.fileNode.id}:${classNode.id}`),
            entityId: relEntityId, type: 'DEFINES_CLASS', // Reusing type
            sourceId: this.fileNode.entityId, targetId: entityId,
            createdAt: this.now, weight: 9,
        });

        // Let the main visit loop handle recursion into the body/member list
        // Restore context AFTER visiting children (handled by main visit loop now)
        // This is tricky without explicit exit events. Defer proper context stack management.
        // this.currentClassEntityId = originalClassId; // Restore outer class context - DEFERRED
    }

    // Add visitStructSpecifier etc. later
}


/**
 * Parses C/C++ files using Tree-sitter.
 */
export class CCppParser {
    private parser: Parser;

    constructor() {
        this.parser = new Parser();
        logger.debug('C/C++ Tree-sitter Parser initialized');
    }

    /**
     * Parses a single C/C++ file.
     * @param file - FileInfo object for the C/C++ file.
     * @returns A promise resolving to the path of the temporary result file.
     */
    async parseFile(file: FileInfo): Promise<string> {
        logger.info(`[CCppParser] Starting C/C++ parsing for: ${file.name}`);
        await ensureTempDir();
        const tempFilePath = getTempFilePath(file.path);
        const absoluteFilePath = path.resolve(file.path);
        const normalizedFilePath = absoluteFilePath.replace(/\\/g, '/');

        try {
            const fileContent = await fs.readFile(absoluteFilePath, 'utf-8');
            const language = file.extension === '.c' || file.extension === '.h' ? 'C' : 'C++';
            const grammar = language === 'C' ? C : Cpp;

            this.parser.setLanguage(grammar as any); // Cast to any to bypass type conflict
            const tree = this.parser.parse(fileContent);

            const visitor = new CCppAstVisitor(normalizedFilePath, language, fileContent);
            visitor.visit(tree.rootNode);

            const result: SingleFileParseResult = {
                filePath: normalizedFilePath,
                nodes: visitor.nodes,
                relationships: visitor.relationships,
            };

            await fs.writeFile(tempFilePath, JSON.stringify(result, null, 2));
            logger.info(`[CCppParser] Pass 1 completed for: ${file.name}. Nodes: ${result.nodes.length}, Rels: ${result.relationships.length}. Saved to ${path.basename(tempFilePath)}`);
            return tempFilePath;

        } catch (error: any) {
            logger.error(`[CCppParser] Error during C/C++ Pass 1 for ${file.path}`, {
                 errorMessage: error.message,
                 stack: error.stack?.substring(0, 500)
            });
            try { await fs.unlink(tempFilePath); } catch { /* ignore */ }
            throw new ParserError(`Failed C/C++ Pass 1 parsing for ${file.path}`, { originalError: error });
        }
    }
}