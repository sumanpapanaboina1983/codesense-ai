import { JSDOM } from 'jsdom';
import path from 'path';
import fs from 'fs/promises';
import { createContextLogger } from '../../utils/logger.js';
import { ParserError } from '../../utils/errors.js';
import { FileInfo } from '../../scanner/file-scanner.js';
import {
    AstNode,
    RelationshipInfo,
    SingleFileParseResult,
    InstanceCounter,
    JSPPageNode,
    JSPFormNode,
    JSPIncludeNode,
    JSPTagLibNode,
    TagLibrary,
    FormField,
    SubmitElement
} from '../types.js';
import { ensureTempDir, getTempFilePath, generateInstanceId, generateEntityId } from '../parser-utils.js';

const logger = createContextLogger('JSPParser');

// JSP directive patterns
const JSP_PATTERNS = {
    PAGE_DIRECTIVE: /<%@\s*page\s+([^%]*)%>/g,
    INCLUDE_DIRECTIVE: /<%@\s*include\s+file\s*=\s*["']([^"']+)["'][^%]*%>/g,
    TAGLIB_DIRECTIVE: /<%@\s*taglib\s+([^%]*)%>/g,
    SCRIPTLET: /<%[^@!][^%]*%>/g,
    EXPRESSION: /<%=([^%]*)%>/g,
    EL_EXPRESSION: /\$\{([^}]*)\}/g,
    JSP_ACTION: /<jsp:(\w+)([^>]*)>/g,
    FORWARD: /<jsp:forward\s+page\s*=\s*["']([^"']+)["'][^>]*>/g,
    REDIRECT: /<c:redirect\s+url\s*=\s*["']([^"']+)["'][^>]*>/g,
    FORM_ACTION: /<form[^>]+action\s*=\s*["']([^"']+)["'][^>]*>/gi,
};

export class JSPParser {
    private instanceCounter: InstanceCounter = { count: 0 };
    private now: string = new Date().toISOString();

    constructor() {
        logger.debug('JSP Parser initialized');
    }

    /**
     * Parses a single JSP file.
     */
    async parseFile(file: FileInfo): Promise<string> {
        logger.debug(`Parsing JSP file: ${file.path}`);

        await ensureTempDir();
        const tempFilePath = getTempFilePath(file.path);

        try {
            const content = await fs.readFile(file.path, 'utf-8');
            const result = await this.parseJSPContent(content, file.path);

            await fs.writeFile(tempFilePath, JSON.stringify(result, null, 2));
            logger.debug(`JSP parsing completed for ${file.path}`);

            return tempFilePath;
        } catch (error: any) {
            logger.error(`Error parsing JSP file ${file.path}:`, { message: error.message });
            throw new ParserError(`Failed to parse JSP file: ${file.path}`, { originalError: error });
        }
    }

    /**
     * Parses JSP content and returns structured result.
     */
    private async parseJSPContent(content: string, filePath: string): Promise<SingleFileParseResult> {
        const normalizedPath = path.resolve(filePath).replace(/\\/g, '/');
        const fileName = path.basename(filePath);

        const nodes: AstNode[] = [];
        const relationships: RelationshipInfo[] = [];

        // Create main JSP page node
        const jspPageNode = this.createJSPPageNode(content, normalizedPath, fileName);
        nodes.push(jspPageNode);

        // Parse forms within the JSP
        const forms = this.parseForms(content, jspPageNode.entityId);
        nodes.push(...forms);

        // Create form relationships
        forms.forEach(form => {
            relationships.push(this.createRelationship(
                'CONTAINS_FORM',
                jspPageNode.entityId,
                form.entityId
            ));
        });

        // Parse includes
        const includes = this.parseIncludes(content, jspPageNode.entityId);
        nodes.push(...includes);

        // Create include relationships
        includes.forEach(include => {
            relationships.push(this.createRelationship(
                'INCLUDES_JSP',
                jspPageNode.entityId,
                include.entityId
            ));
        });

        // Parse tag libraries
        const taglibs = this.parseTagLibraries(content, jspPageNode.entityId);
        nodes.push(...taglibs);

        // Create taglib relationships
        taglibs.forEach(taglib => {
            relationships.push(this.createRelationship(
                'USES_TAGLIB',
                jspPageNode.entityId,
                taglib.entityId
            ));
        });

        return {
            filePath: normalizedPath,
            nodes,
            relationships
        };
    }

    /**
     * Creates the main JSP page node.
     */
    private createJSPPageNode(content: string, filePath: string, fileName: string): JSPPageNode {
        const servletPath = this.extractServletPath(filePath);
        const pageDirectives = this.extractPageDirectives(content);
        const formActions = this.extractFormActions(content);
        const includes = this.extractIncludePaths(content);
        const taglibs = this.extractTagLibraryInfo(content);
        const elExpressions = this.extractELExpressions(content);
        const hasScriptlets = JSP_PATTERNS.SCRIPTLET.test(content);

        const entityId = generateEntityId('jsppage', servletPath);

        return {
            id: generateInstanceId(this.instanceCounter, 'jsppage', fileName),
            entityId,
            kind: 'JSPPage',
            name: fileName,
            filePath,
            language: 'JSP',
            startLine: 1,
            endLine: content.split('\n').length,
            startColumn: 0,
            endColumn: 0,
            createdAt: this.now,
            properties: {
                servletPath,
                hasForm: formActions.length > 0,
                formActions,
                includes,
                taglibs,
                elExpressions,
                hasScriptlets,
                encoding: pageDirectives.encoding,
                contentType: pageDirectives.contentType
            }
        };
    }

    /**
     * Parses form elements within the JSP.
     */
    private parseForms(content: string, parentId: string): JSPFormNode[] {
        const forms: JSPFormNode[] = [];

        try {
            // Clean JSP content for HTML parsing
            const cleanedContent = this.cleanJSPForHTMLParsing(content);
            const dom = new JSDOM(cleanedContent);
            const document = dom.window.document;

            const formElements = document.querySelectorAll('form');

            formElements.forEach((form, index) => {
                const action = form.getAttribute('action') || '';
                const method = (form.getAttribute('method') || 'GET').toUpperCase() as 'GET' | 'POST';
                const enctype = form.getAttribute('enctype') || undefined;

                const fields = this.extractFormFields(form);
                const submitElements = this.extractSubmitElements(form);

                const formEntityId = generateEntityId('jspform', `${parentId}:form${index}`);

                const formNode: JSPFormNode = {
                    id: generateInstanceId(this.instanceCounter, 'jspform', `form${index}`),
                    entityId: formEntityId,
                    kind: 'JSPForm',
                    name: `form${index}`,
                    filePath: parentId.split(':')[1] || '', // Extract file path from parent entityId
                    language: 'JSP',
                    startLine: 1, // Would need more sophisticated parsing for exact line numbers
                    endLine: 1,
                    startColumn: 0,
                    endColumn: 0,
                    parentId,
                    createdAt: this.now,
                    properties: {
                        action,
                        method,
                        enctype,
                        fields,
                        submitElements
                    }
                };

                forms.push(formNode);
            });
        } catch (error: any) {
            logger.warn(`Error parsing forms in JSP: ${error.message}`);
        }

        return forms;
    }

    /**
     * Parses include directives and actions.
     */
    private parseIncludes(content: string, parentId: string): JSPIncludeNode[] {
        const includes: JSPIncludeNode[] = [];

        // Parse include directives
        let match;
        JSP_PATTERNS.INCLUDE_DIRECTIVE.lastIndex = 0;
        while ((match = JSP_PATTERNS.INCLUDE_DIRECTIVE.exec(content)) !== null) {
            const includePath = match[1];
            if (!includePath) continue;
            
            const includeEntityId = generateEntityId('jspinclude', `${parentId}:${includePath}`);

            includes.push({
                id: generateInstanceId(this.instanceCounter, 'jspinclude', includePath),
                entityId: includeEntityId,
                kind: 'JSPInclude',
                name: path.basename(includePath),
                filePath: parentId.split(':')[1] || '',
                language: 'JSP',
                startLine: this.getLineNumber(content, match.index),
                endLine: this.getLineNumber(content, match.index + match[0].length),
                startColumn: 0,
                endColumn: 0,
                parentId,
                createdAt: this.now,
                properties: {
                    includePath,
                    includeType: 'directive',
                    isStatic: true
                }
            });
        }

        // Parse jsp:include actions
        JSP_PATTERNS.JSP_ACTION.lastIndex = 0;
        while ((match = JSP_PATTERNS.JSP_ACTION.exec(content)) !== null) {
            if (match[1] === 'include' && match[2]) {
                const pageMatch = match[2].match(/page\s*=\s*["']([^"']+)["']/);
                if (pageMatch && pageMatch[1]) {
                    const includePath = pageMatch[1];
                    const includeEntityId = generateEntityId('jspinclude', `${parentId}:${includePath}:action`);

                    includes.push({
                        id: generateInstanceId(this.instanceCounter, 'jspinclude', `${includePath}:action`),
                        entityId: includeEntityId,
                        kind: 'JSPInclude',
                        name: path.basename(includePath),
                        filePath: parentId.split(':')[1] || '',
                        language: 'JSP',
                        startLine: this.getLineNumber(content, match.index),
                        endLine: this.getLineNumber(content, match.index + match[0].length),
                        startColumn: 0,
                        endColumn: 0,
                        parentId,
                        createdAt: this.now,
                        properties: {
                            includePath,
                            includeType: 'action',
                            isStatic: false
                        }
                    });
                }
            }
        }

        return includes;
    }

    /**
     * Parses tag library directives.
     */
    private parseTagLibraries(content: string, parentId: string): JSPTagLibNode[] {
        const taglibs: JSPTagLibNode[] = [];

        let match;
        JSP_PATTERNS.TAGLIB_DIRECTIVE.lastIndex = 0;
        while ((match = JSP_PATTERNS.TAGLIB_DIRECTIVE.exec(content)) !== null) {
            const directiveContent = match[1];
            if (!directiveContent) continue;
            
            const uriMatch = directiveContent.match(/uri\s*=\s*["']([^"']+)["']/);
            const prefixMatch = directiveContent.match(/prefix\s*=\s*["']([^"']+)["']/);

            if (uriMatch && prefixMatch && uriMatch[1] && prefixMatch[1]) {
                const uri = uriMatch[1];
                const prefix = prefixMatch[1];
                const usedTags = this.findUsedTags(content, prefix);

                const taglibEntityId = generateEntityId('jsptaglib', `${parentId}:${prefix}`);

                taglibs.push({
                    id: generateInstanceId(this.instanceCounter, 'jsptaglib', prefix),
                    entityId: taglibEntityId,
                    kind: 'JSPTagLib',
                    name: prefix,
                    filePath: parentId.split(':')[1] || '',
                    language: 'JSP',
                    startLine: this.getLineNumber(content, match.index),
                    endLine: this.getLineNumber(content, match.index + match[0].length),
                    startColumn: 0,
                    endColumn: 0,
                    parentId,
                    createdAt: this.now,
                    properties: {
                        uri,
                        prefix,
                        usedTags
                    }
                });
            }
        }

        return taglibs;
    }

    // Helper methods
    private extractServletPath(filePath: string): string {
        // Convert file system path to servlet path
        // Example: /webapp/pages/user/profile.jsp -> /pages/user/profile.jsp
        const webappIndex = filePath.indexOf('/webapp/');
        if (webappIndex !== -1) {
            return filePath.substring(webappIndex + 7); // Remove '/webapp'
        }

        const srcIndex = filePath.indexOf('/src/main/webapp/');
        if (srcIndex !== -1) {
            return filePath.substring(srcIndex + 16); // Remove '/src/main/webapp'
        }

        return '/' + path.basename(filePath);
    }

    private extractPageDirectives(content: string): { encoding?: string; contentType?: string } {
        const result: { encoding?: string; contentType?: string } = {};

        let match;
        JSP_PATTERNS.PAGE_DIRECTIVE.lastIndex = 0;
        while ((match = JSP_PATTERNS.PAGE_DIRECTIVE.exec(content)) !== null) {
            const directiveContent = match[1];
            if (!directiveContent) continue;

            const encodingMatch = directiveContent.match(/pageEncoding\s*=\s*["']([^"']+)["']/);
            if (encodingMatch && encodingMatch[1]) {
                result.encoding = encodingMatch[1];
            }

            const contentTypeMatch = directiveContent.match(/contentType\s*=\s*["']([^"']+)["']/);
            if (contentTypeMatch && contentTypeMatch[1]) {
                result.contentType = contentTypeMatch[1];
            }
        }

        return result;
    }

    private extractFormActions(content: string): string[] {
        const actions: string[] = [];

        let match;
        JSP_PATTERNS.FORM_ACTION.lastIndex = 0;
        while ((match = JSP_PATTERNS.FORM_ACTION.exec(content)) !== null) {
            if (match[1]) {
                actions.push(match[1]);
            }
        }

        return [...new Set(actions)]; // Remove duplicates
    }

    private extractIncludePaths(content: string): string[] {
        const includes: string[] = [];

        let match;
        JSP_PATTERNS.INCLUDE_DIRECTIVE.lastIndex = 0;
        while ((match = JSP_PATTERNS.INCLUDE_DIRECTIVE.exec(content)) !== null) {
            if (match[1]) {
                includes.push(match[1]);
            }
        }

        return includes;
    }

    private extractTagLibraryInfo(content: string): TagLibrary[] {
        const taglibs: TagLibrary[] = [];

        let match;
        JSP_PATTERNS.TAGLIB_DIRECTIVE.lastIndex = 0;
        while ((match = JSP_PATTERNS.TAGLIB_DIRECTIVE.exec(content)) !== null) {
            const directiveContent = match[1];
            if (!directiveContent) continue;
            
            const uriMatch = directiveContent.match(/uri\s*=\s*["']([^"']+)["']/);
            const prefixMatch = directiveContent.match(/prefix\s*=\s*["']([^"']+)["']/);

            if (uriMatch && prefixMatch && uriMatch[1] && prefixMatch[1]) {
                taglibs.push({
                    uri: uriMatch[1],
                    prefix: prefixMatch[1]
                });
            }
        }

        return taglibs;
    }

    private extractELExpressions(content: string): string[] {
        const expressions: string[] = [];

        let match;
        JSP_PATTERNS.EL_EXPRESSION.lastIndex = 0;
        while ((match = JSP_PATTERNS.EL_EXPRESSION.exec(content)) !== null) {
            if (match[1]) {
                expressions.push(match[1].trim());
            }
        }

        return [...new Set(expressions)]; // Remove duplicates
    }

    private cleanJSPForHTMLParsing(content: string): string {
        return content
            // Remove JSP comments
            .replace(/<%--[\s\S]*?--%>/g, '')
            // Remove JSP directives
            .replace(/<%@[^%]*%>/g, '')
            // Remove scriptlets but keep their content as comments
            .replace(/<%[^@=][^%]*%>/g, '<!-- scriptlet removed -->')
            // Remove expressions
            .replace(/<%=[^%]*%>/g, '<!-- expression removed -->')
            // Simplify EL expressions
            .replace(/\$\{[^}]*\}/g, 'placeholder');
    }

    private extractFormFields(form: Element): FormField[] {
        const fields: FormField[] = [];

        const inputs = form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            const name = input.getAttribute('name');
            if (name) {
                fields.push({
                    name,
                    type: input.getAttribute('type') || input.tagName.toLowerCase(),
                    required: input.hasAttribute('required'),
                    defaultValue: input.getAttribute('value') || undefined
                });
            }
        });

        return fields;
    }

    private extractSubmitElements(form: Element): SubmitElement[] {
        const submits: SubmitElement[] = [];

        const submitInputs = form.querySelectorAll('input[type="submit"], input[type="button"], input[type="image"], button');
        submitInputs.forEach(submit => {
            const type = submit.getAttribute('type') || 'button';
            submits.push({
                type: type as 'submit' | 'button' | 'image',
                name: submit.getAttribute('name') || undefined,
                value: submit.getAttribute('value') || submit.textContent || undefined
            });
        });

        return submits;
    }

    private findUsedTags(content: string, prefix: string): string[] {
        const tags: string[] = [];
        const tagPattern = new RegExp(`<${prefix}:(\\w+)`, 'g');

        let match;
        while ((match = tagPattern.exec(content)) !== null) {
            if (match[1]) {
                tags.push(match[1]);
            }
        }

        return [...new Set(tags)]; // Remove duplicates
    }

    private getLineNumber(content: string, index: number): number {
        return content.substring(0, index).split('\n').length;
    }

    private createRelationship(type: string, sourceId: string, targetId: string): RelationshipInfo {
        return {
            id: generateInstanceId(this.instanceCounter, type.toLowerCase(), `${sourceId}:${targetId}`),
            entityId: generateEntityId(type.toLowerCase(), `${sourceId}:${targetId}`),
            type,
            sourceId,
            targetId,
            createdAt: this.now,
            weight: 5
        };
    }
}