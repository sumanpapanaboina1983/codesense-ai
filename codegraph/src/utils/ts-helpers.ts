import { Node, SyntaxKind, JSDoc, JSDocTag, ts } from 'ts-morph';
import { DocTag, DocumentationInfo } from '../analyzer/types.js';

/**
 * Gets the end column number for a node.
 * @param node - The ts-morph Node.
 * @returns The 0-based end column number.
 */
export function getEndColumn(node: Node): number {
    try {
        const endLine = node.getEndLineNumber();
        const sourceFile = node.getSourceFile();
        const lineStartPos = sourceFile.compilerNode.getPositionOfLineAndCharacter(endLine - 1, 0);
        return node.getEnd() - lineStartPos;
    } catch (e) {
        // console.warn(`Error getting end column for node: ${e}`);
        return 0; // Fallback
    }
}

/**
 * Determines the visibility (public, private, protected) of a class member.
 * Defaults to 'public' if no explicit modifier is found.
 * @param node - The ts-morph Node (e.g., MethodDeclaration, PropertyDeclaration).
 * @returns The visibility modifier string.
 */
export function getVisibility(node: Node): 'public' | 'private' | 'protected' {
    // Use the correct type guard: Node.isModifierable(...)
    if (Node.isModifierable(node)) {
        // Now TypeScript knows 'node' has modifier methods within this block
        if (node.hasModifier(SyntaxKind.PrivateKeyword)) {
            return 'private';
        }
        if (node.hasModifier(SyntaxKind.ProtectedKeyword)) {
            return 'protected';
        }
    }
    return 'public';
}

/**
 * Extracts the combined text content from all JSDoc comments associated with a node.
 * @param node - The ts-morph Node.
 * @returns The combined JSDoc text, or an empty string if none found.
 */
export function getJsDocText(node: Node): string {
    // Use the correct type guard: Node.isJSDocable(...)
    if (Node.isJSDocable(node)) {
        // TypeScript knows 'node' has getJsDocs() here
        const jsDocs: JSDoc[] = node.getJsDocs();
        return jsDocs.map((doc: JSDoc) => doc.getCommentText() || '').join('\n').trim();
    }
    return '';
}

/**
 * Extracts the description part of the first JSDoc comment.
 * @param node The node to extract JSDoc from.
 * @returns The description string or undefined.
 */
export function getJsDocDescription(node: Node): string | undefined {
     // Use the correct type guard: Node.isJSDocable(...)
    if (Node.isJSDocable(node)) {
        const jsDocs: JSDoc[] = node.getJsDocs();
        if (jsDocs.length > 0) {
            // Add nullish coalescing for safety, although getJsDocs should return empty array if none
            return jsDocs[0]?.getDescription().trim() || undefined;
        }
    }
    return undefined;
}

/**
 * Checks if a node has the 'export' keyword modifier.
 * @param node The node to check.
 * @returns True if the node is exported, false otherwise.
 */
export function isNodeExported(node: Node): boolean {
    // Use the correct type guard: Node.isModifierable(...)
    if (Node.isModifierable(node)) {
        return node.hasModifier(SyntaxKind.ExportKeyword);
    }
    // Consider edge cases like `export { name };` if needed later
    return false;
}

/**
 * Checks if a node has the 'async' keyword modifier.
 * @param node The node to check (e.g., FunctionDeclaration, MethodDeclaration, ArrowFunction).
 * @returns True if the node is async, false otherwise.
 */
export function isNodeAsync(node: Node): boolean {
    if (Node.isFunctionDeclaration(node) || Node.isMethodDeclaration(node) || Node.isArrowFunction(node) || Node.isFunctionExpression(node)) {
        return node.isAsync();
    }
    return false;
}

/**
 * Checks if a node has the 'static' keyword modifier.
 * @param node The node to check (e.g., MethodDeclaration, PropertyDeclaration).
 * @returns True if the node is static, false otherwise.
 */
export function isNodeStatic(node: Node): boolean {
     // Use the correct type guard: Node.isModifierable(...)
    if (Node.isModifierable(node)) {
        return node.hasModifier(SyntaxKind.StaticKeyword);
    }
    return false;
}

/**
 * Safely gets the name of a node, returning a default if none exists.
 * Handles various node types that might have names.
 * @param node The node.
 * @param defaultName The default name to return if the node has no name.
 * @returns The node's name or the default name.
 */
export function getNodeName(node: Node, defaultName: string = 'anonymous'): string {
    // Use specific type guards for nodes known to have names
    if (Node.isVariableDeclaration(node) || Node.isFunctionDeclaration(node) || Node.isClassDeclaration(node) || Node.isInterfaceDeclaration(node) || Node.isMethodDeclaration(node) || Node.isPropertyDeclaration(node) || Node.isParameterDeclaration(node) || Node.isEnumDeclaration(node) || Node.isTypeAliasDeclaration(node) || Node.isBindingElement(node) || Node.isPropertySignature(node) || Node.isMethodSignature(node)) {
        // TypeScript knows these have getName()
        return node.getName() ?? defaultName;
    }
    // Add other types like EnumMember, NamespaceDeclaration if needed
    return defaultName;
}


/**
 * Safely gets the type text of a node, returning 'any' if resolution fails.
 * @param node The node (e.g., VariableDeclaration, ParameterDeclaration, PropertyDeclaration).
 * @returns The type text or 'any'.
 */
export function getNodeType(node: Node): string {
     try {
        // Use specific type guards for nodes known to have types
        if (Node.isVariableDeclaration(node) || Node.isParameterDeclaration(node) || Node.isPropertyDeclaration(node) || Node.isPropertySignature(node) || Node.isBindingElement(node)) {
             // TypeScript knows these have getType()
             return node.getType().getText() || 'any';
        }
     } catch (e) {
         // console.warn(`Could not get type for node kind ${node.getKindName()}: ${e}`);
     }
     return 'any'; // Default fallback
}

/**
 * Safely gets the return type text of a function-like node.
 * @param node The function-like node.
 * @returns The return type text or 'any'.
 */
export function getFunctionReturnType(node: Node): string {
     try {
         // Use specific type guards for function-like nodes
         if (Node.isFunctionDeclaration(node) || Node.isMethodDeclaration(node) || Node.isArrowFunction(node) || Node.isFunctionExpression(node) || Node.isMethodSignature(node)) {
             // TypeScript knows these have getReturnType()
             return node.getReturnType().getText() || 'any';
         }
     } catch (e) {
         // console.warn(`Could not get return type for node kind ${node.getKindName()}: ${e}`);
     }
     return 'any';
}

/**
 * Extracts structured JSDoc tags from a node.
 * Handles @param, @returns, @throws, @deprecated, @example, @see, @since, @version, @author.
 * @param node The node to extract JSDoc tags from.
 * @returns Array of structured DocTag objects.
 */
export function getJsDocTags(node: Node): DocTag[] {
    const tags: DocTag[] = [];

    if (!Node.isJSDocable(node)) {
        return tags;
    }

    const jsDocs: JSDoc[] = node.getJsDocs();
    for (const jsDoc of jsDocs) {
        const jsDocTags = jsDoc.getTags();
        for (const tag of jsDocTags) {
            const tagName = tag.getTagName();
            const docTag = parseJsDocTag(tag, tagName);
            if (docTag) {
                tags.push(docTag);
            }
        }
    }

    return tags;
}

/**
 * Parse a single JSDoc tag into a structured DocTag.
 */
function parseJsDocTag(tag: JSDocTag, tagName: string): DocTag | null {
    try {
        const tagText = tag.getText();

        switch (tagName) {
            case 'param':
            case 'arg':
            case 'argument': {
                // Format: @param {type} name description
                // or: @param name description
                const paramMatch = tagText.match(/@(?:param|arg|argument)\s+(?:\{([^}]+)\}\s+)?(\w+)(?:\s+-\s*|\s+)?(.*)$/s);
                if (paramMatch) {
                    return {
                        tag: 'param',
                        type: paramMatch[1] || undefined,
                        name: paramMatch[2],
                        description: paramMatch[3]?.trim() || undefined,
                    };
                }
                break;
            }

            case 'returns':
            case 'return': {
                // Format: @returns {type} description
                const returnMatch = tagText.match(/@returns?\s+(?:\{([^}]+)\}\s+)?(.*)$/s);
                if (returnMatch) {
                    return {
                        tag: 'returns',
                        type: returnMatch[1] || undefined,
                        description: returnMatch[2]?.trim() || undefined,
                    };
                }
                break;
            }

            case 'throws':
            case 'exception': {
                // Format: @throws {type} description
                const throwsMatch = tagText.match(/@(?:throws|exception)\s+(?:\{([^}]+)\}\s+)?(.*)$/s);
                if (throwsMatch) {
                    return {
                        tag: 'throws',
                        type: throwsMatch[1] || undefined,
                        description: throwsMatch[2]?.trim() || undefined,
                    };
                }
                break;
            }

            case 'deprecated': {
                // Format: @deprecated reason
                const deprecatedMatch = tagText.match(/@deprecated\s*(.*)$/s);
                return {
                    tag: 'deprecated',
                    description: deprecatedMatch?.[1]?.trim() || undefined,
                };
            }

            case 'example': {
                // Format: @example code
                const exampleMatch = tagText.match(/@example\s*(.*)$/s);
                return {
                    tag: 'example',
                    description: exampleMatch?.[1]?.trim() || undefined,
                };
            }

            case 'see': {
                // Format: @see reference
                const seeMatch = tagText.match(/@see\s+(.*)$/s);
                return {
                    tag: 'see',
                    description: seeMatch?.[1]?.trim() || undefined,
                };
            }

            case 'since': {
                // Format: @since version
                const sinceMatch = tagText.match(/@since\s+(.*)$/s);
                return {
                    tag: 'since',
                    description: sinceMatch?.[1]?.trim() || undefined,
                };
            }

            case 'version': {
                // Format: @version number
                const versionMatch = tagText.match(/@version\s+(.*)$/s);
                return {
                    tag: 'version',
                    description: versionMatch?.[1]?.trim() || undefined,
                };
            }

            case 'author': {
                // Format: @author name
                const authorMatch = tagText.match(/@author\s+(.*)$/s);
                return {
                    tag: 'author',
                    description: authorMatch?.[1]?.trim() || undefined,
                };
            }

            case 'type': {
                // Format: @type {type}
                const typeMatch = tagText.match(/@type\s+\{([^}]+)\}/);
                return {
                    tag: 'type',
                    type: typeMatch?.[1] || undefined,
                };
            }

            case 'typedef': {
                // Format: @typedef {type} name
                const typedefMatch = tagText.match(/@typedef\s+\{([^}]+)\}\s+(\w+)/);
                if (typedefMatch) {
                    return {
                        tag: 'typedef',
                        type: typedefMatch[1],
                        name: typedefMatch[2],
                    };
                }
                break;
            }

            case 'property':
            case 'prop': {
                // Format: @property {type} name description
                const propMatch = tagText.match(/@(?:property|prop)\s+(?:\{([^}]+)\}\s+)?(\w+)(?:\s+-\s*|\s+)?(.*)$/s);
                if (propMatch) {
                    return {
                        tag: 'property',
                        type: propMatch[1] || undefined,
                        name: propMatch[2],
                        description: propMatch[3]?.trim() || undefined,
                    };
                }
                break;
            }

            case 'template': {
                // Format: @template T description
                const templateMatch = tagText.match(/@template\s+(\w+)(?:\s+-\s*|\s+)?(.*)$/s);
                if (templateMatch) {
                    return {
                        tag: 'template',
                        name: templateMatch[1],
                        description: templateMatch[2]?.trim() || undefined,
                    };
                }
                break;
            }

            default: {
                // Generic tag handling
                const genericMatch = tagText.match(/@(\w+)\s*(.*)$/s);
                if (genericMatch && genericMatch[1]) {
                    return {
                        tag: genericMatch[1],
                        description: genericMatch[2]?.trim() || undefined,
                    };
                }
            }
        }
    } catch (e) {
        // Silently fail for unparseable tags
    }

    return null;
}

/**
 * Extracts complete structured documentation from a node.
 * @param node The node to extract documentation from.
 * @returns DocumentationInfo object with summary, tags, and metadata.
 */
export function getDocumentationInfo(node: Node): DocumentationInfo | undefined {
    if (!Node.isJSDocable(node)) {
        return undefined;
    }

    const jsDocs: JSDoc[] = node.getJsDocs();
    if (jsDocs.length === 0) {
        return undefined;
    }

    // Get the last (most recent) JSDoc block
    const lastJsDoc = jsDocs[jsDocs.length - 1];
    if (!lastJsDoc) {
        return undefined;
    }

    const summary = lastJsDoc.getDescription().trim();
    const rawComment = lastJsDoc.getText();
    const tags = getJsDocTags(node);

    // Extract specific metadata from tags
    const isDeprecated = tags.some(t => t.tag === 'deprecated');
    const deprecationReason = tags.find(t => t.tag === 'deprecated')?.description;
    const examples = tags.filter(t => t.tag === 'example').map(t => t.description).filter(Boolean) as string[];
    const seeAlso = tags.filter(t => t.tag === 'see').map(t => t.description).filter(Boolean) as string[];
    const authors = tags.filter(t => t.tag === 'author').map(t => t.description).filter(Boolean) as string[];
    const version = tags.find(t => t.tag === 'version')?.description;
    const since = tags.find(t => t.tag === 'since')?.description;

    return {
        summary,
        rawComment,
        tags,
        format: 'jsdoc',
        isDeprecated: isDeprecated || undefined,
        deprecationReason,
        examples: examples.length > 0 ? examples : undefined,
        seeAlso: seeAlso.length > 0 ? seeAlso : undefined,
        authors: authors.length > 0 ? authors : undefined,
        version,
        since,
    };
}