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
    SubmitElement,
    SelectOption,
    DataSourceInfo,
    TableColumnInfo,
    DataTableInfo,
    DataTableNode,
    TableActionInfo
} from '../types.js';
import { ensureTempDir, getTempFilePath, generateInstanceId, generateEntityId } from '../parser-utils.js';
import { BusinessRuleDetector } from './BusinessRuleDetector.js';

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
    // Spring form binding patterns
    SPRING_FORM: /<form:form[^>]*(?:modelAttribute|commandName)\s*=\s*["']([^"']+)["'][^>]*>/gi,
    SPRING_INPUT: /<form:(input|password|hidden)[^>]*path\s*=\s*["']([^"']+)["'][^>]*>/gi,
    SPRING_SELECT: /<form:select[^>]*path\s*=\s*["']([^"']+)["'][^>]*>/gi,
    SPRING_TEXTAREA: /<form:textarea[^>]*path\s*=\s*["']([^"']+)["'][^>]*>/gi,
    SPRING_CHECKBOX: /<form:(checkbox|checkboxes)[^>]*path\s*=\s*["']([^"']+)["'][^>]*>/gi,
    SPRING_RADIOBUTTON: /<form:(radiobutton|radiobuttons)[^>]*path\s*=\s*["']([^"']+)["'][^>]*>/gi,
};

/**
 * Represents a Spring form field binding (e.g., <form:input path="entity.field"/>)
 */
export interface FormFieldBindingNode extends AstNode {
    kind: 'FormFieldBinding';
    language: 'JSP';
    properties: {
        fieldPath: string;           // e.g., "entity.fieldName"
        modelAttribute: string;      // e.g., "entity"
        fieldName: string;           // e.g., "fieldName"
        inputType: string;           // input, select, textarea, checkbox, etc.
        required: boolean;
        validationAttributes: string[];
        lineNumber: number;
    };
}

/**
 * Represents an entity field binding discovered from JSP form
 */
interface FormFieldBindingInfo {
    fieldPath: string;
    modelAttribute: string;
    fieldName: string;
    inputType: string;
    required: boolean;
    validationAttributes: string[];
    lineNumber: number;
}

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

        // Parse Spring form field bindings (Feature Traceability)
        const { bindingNodes, bindingRelationships } = this.parseSpringFormBindings(
            content,
            normalizedPath,
            jspPageNode.entityId
        );
        nodes.push(...bindingNodes);
        relationships.push(...bindingRelationships);

        if (bindingNodes.length > 0) {
            logger.debug(
                `[JSPParser] Spring form bindings detected for ${fileName}: ` +
                `${bindingNodes.length} field bindings`
            );
        }

        // Business Rule Detection (Phase 3)
        // Extract validation constraints, conditionals, and guards from JSP
        const businessRuleDetector = new BusinessRuleDetector(normalizedPath, 'JSP');
        const businessRuleResult = businessRuleDetector.detectJSPRules(
            content,
            jspPageNode.properties.servletPath
        );

        // Merge business rule nodes
        const businessRuleNodes = businessRuleDetector.getAllNodes();
        const businessRuleRelationships = businessRuleDetector.getRelationships();

        logger.debug(
            `[JSPParser] Business rules detected for ${fileName}: ` +
            `${businessRuleResult.totalRulesDetected} rules`
        );

        // Business Logic Blueprint: Extract data tables
        const { nodes: tableNodes, relationships: tableRelationships } =
            this.extractDataTables(content, normalizedPath, jspPageNode.entityId);

        if (tableNodes.length > 0) {
            logger.debug(
                `[JSPParser] Data tables detected for ${fileName}: ${tableNodes.length} tables`
            );
        }

        // Business Logic Blueprint: Extract Spring select options and store on JSP node
        const springSelectOptions = this.extractSpringSelectOptions(content);
        if (springSelectOptions.size > 0) {
            jspPageNode.properties.springSelectOptions = Object.fromEntries(springSelectOptions);
            logger.debug(
                `[JSPParser] Spring select options detected for ${fileName}: ${springSelectOptions.size} fields`
            );
        }

        return {
            filePath: normalizedPath,
            nodes: [...nodes, ...businessRuleNodes, ...tableNodes],
            relationships: [...relationships, ...businessRuleRelationships, ...tableRelationships]
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
                // Extract label for this field
                const label = this.extractFieldLabel(form, name, input as Element);

                // Extract validation rules from HTML5 attributes
                const validationRules: FormField['validationRules'] = {};

                const pattern = input.getAttribute('pattern');
                if (pattern) validationRules.pattern = pattern;

                const min = input.getAttribute('min');
                if (min) validationRules.min = min;

                const max = input.getAttribute('max');
                if (max) validationRules.max = max;

                const minLength = input.getAttribute('minlength');
                if (minLength) validationRules.minLength = parseInt(minLength, 10);

                const maxLength = input.getAttribute('maxlength');
                if (maxLength) validationRules.maxLength = parseInt(maxLength, 10);

                const step = input.getAttribute('step');
                if (step) validationRules.step = parseFloat(step);

                // Extract CSS classes for error styling detection
                const cssClasses = (input.getAttribute('class') || '')
                    .split(/\s+/)
                    .filter(c => c.length > 0);

                // Extract cssErrorClass from Spring form tags
                const cssErrorClass = input.getAttribute('cssErrorClass') || undefined;

                // Extract select options if this is a select element
                let selectOptions: SelectOption[] | undefined;
                let dataSource: DataSourceInfo | undefined;
                if (input.tagName.toLowerCase() === 'select') {
                    const optionResult = this.extractSelectOptions(input as Element);
                    selectOptions = optionResult.options;
                    dataSource = optionResult.dataSource;
                }

                // Check for read-only and disabled states
                const readOnly = input.hasAttribute('readonly');
                const disabled = input.hasAttribute('disabled');

                fields.push({
                    name,
                    type: input.getAttribute('type') || input.tagName.toLowerCase(),
                    required: input.hasAttribute('required'),
                    defaultValue: input.getAttribute('value') || undefined,
                    // BRD Enhancement: Label text
                    label,
                    // BRD Enhancement: Placeholder and help text
                    placeholder: input.getAttribute('placeholder') || undefined,
                    helpText: input.getAttribute('title') || undefined,
                    // BRD Enhancement: Validation rules
                    validationRules: Object.keys(validationRules).length > 0 ? validationRules : undefined,
                    // BRD Enhancement: CSS classes
                    cssClasses: cssClasses.length > 0 ? cssClasses : undefined,
                    cssErrorClass,
                    // Blueprint Enhancement: Select options
                    selectOptions,
                    dataSource,
                    readOnly,
                    disabled,
                });
            }
        });

        return fields;
    }

    /**
     * Extract options from a <select> element.
     * Handles both static <option> tags and dynamic data sources.
     */
    private extractSelectOptions(select: Element): { options: SelectOption[]; dataSource?: DataSourceInfo } {
        const options: SelectOption[] = [];
        let dataSource: DataSourceInfo | undefined;

        // Extract static options
        const optionElements = select.querySelectorAll('option');
        optionElements.forEach(opt => {
            const value = opt.getAttribute('value') || opt.textContent || '';
            const label = opt.textContent?.trim() || value;
            const isDefault = opt.hasAttribute('selected');
            const disabled = opt.hasAttribute('disabled');

            options.push({
                value,
                label,
                isDefault,
                disabled: disabled || undefined,
            });
        });

        // Check for dynamic data source (items attribute pattern)
        // This handles patterns like: items="${stateHolder.types}"
        const itemsAttr = select.getAttribute('items');
        if (itemsAttr) {
            const itemValueAttr = select.getAttribute('itemValue') || 'value';
            const itemLabelAttr = select.getAttribute('itemLabel') || 'label';

            dataSource = {
                type: 'items-attribute',
                itemsPath: itemsAttr,
                itemValue: itemValueAttr,
                itemLabel: itemLabelAttr,
            };
        }

        return { options, dataSource };
    }

    /**
     * Extract Spring form:select options from raw JSP content.
     * Handles <form:select>, <form:option>, <form:options> tags.
     */
    private extractSpringSelectOptions(content: string): Map<string, { options: SelectOption[]; dataSource?: DataSourceInfo }> {
        const selectMap = new Map<string, { options: SelectOption[]; dataSource?: DataSourceInfo }>();

        // Pattern for <form:select path="..." items="...">
        const selectPattern = /<form:select[^>]*path\s*=\s*["']([^"']+)["'][^>]*>/gi;
        let selectMatch;

        while ((selectMatch = selectPattern.exec(content)) !== null) {
            const fieldPath = selectMatch[1];
            const fullTag = selectMatch[0];
            const options: SelectOption[] = [];
            let dataSource: DataSourceInfo | undefined;

            // Check for items attribute (dynamic options)
            const itemsMatch = fullTag.match(/items\s*=\s*["']\$?\{?([^"'}]+)\}?["']/);
            if (itemsMatch) {
                const itemValueMatch = fullTag.match(/itemValue\s*=\s*["']([^"']+)["']/);
                const itemLabelMatch = fullTag.match(/itemLabel\s*=\s*["']([^"']+)["']/);

                dataSource = {
                    type: 'items-attribute',
                    itemsPath: itemsMatch[1],
                    itemValue: itemValueMatch?.[1] || 'value',
                    itemLabel: itemLabelMatch?.[1] || 'label',
                };
            }

            // Look for nested <form:option> tags
            const selectEndIndex = content.indexOf('</form:select>', selectMatch.index);
            if (selectEndIndex > selectMatch.index) {
                const selectContent = content.substring(selectMatch.index, selectEndIndex);

                // Extract <form:option value="..." label="...">
                const optionPattern = /<form:option[^>]*value\s*=\s*["']([^"']+)["'][^>]*(?:label\s*=\s*["']([^"']+)["'])?[^>]*>/gi;
                let optionMatch;

                while ((optionMatch = optionPattern.exec(selectContent)) !== null) {
                    options.push({
                        value: optionMatch[1],
                        label: optionMatch[2] || optionMatch[1],
                    });
                }

                // Extract <form:options items="...">
                const optionsPattern = /<form:options[^>]*items\s*=\s*["']\$?\{?([^"'}]+)\}?["'][^>]*>/gi;
                const optionsMatch = optionsPattern.exec(selectContent);
                if (optionsMatch && !dataSource) {
                    const itemValueMatch = optionsMatch[0].match(/itemValue\s*=\s*["']([^"']+)["']/);
                    const itemLabelMatch = optionsMatch[0].match(/itemLabel\s*=\s*["']([^"']+)["']/);

                    dataSource = {
                        type: 'items-attribute',
                        itemsPath: optionsMatch[1],
                        itemValue: itemValueMatch?.[1] || 'value',
                        itemLabel: itemLabelMatch?.[1] || 'label',
                    };
                }
            }

            selectMap.set(fieldPath, { options, dataSource });
        }

        return selectMap;
    }

    /**
     * Extract data tables from JSP content.
     * Handles <table>, <display:table>, and custom grid components.
     */
    private extractDataTables(content: string, filePath: string, parentId: string): { nodes: DataTableNode[]; relationships: RelationshipInfo[] } {
        const nodes: DataTableNode[] = [];
        const relationships: RelationshipInfo[] = [];

        try {
            const cleanedContent = this.cleanJSPForHTMLParsing(content);
            const dom = new JSDOM(cleanedContent);
            const document = dom.window.document;

            // Extract standard HTML tables with data attributes
            const tables = document.querySelectorAll('table[id], table.data-table, table.display-table');
            let tableIndex = 0;

            tables.forEach(table => {
                const tableId = table.getAttribute('id') || `table_${tableIndex++}`;
                const columns = this.extractTableColumns(table);

                if (columns.length > 0) {
                    const tableEntityId = generateEntityId('datatable', `${filePath}:${tableId}`);

                    const tableNode: DataTableNode = {
                        id: generateInstanceId(this.instanceCounter, 'datatable', tableId),
                        entityId: tableEntityId,
                        kind: 'DataTable',
                        name: tableId,
                        filePath,
                        language: 'JSP',
                        startLine: 1,
                        endLine: 1,
                        startColumn: 0,
                        endColumn: 0,
                        parentId,
                        createdAt: this.now,
                        properties: {
                            id: tableId,
                            dataSource: table.getAttribute('data-source') || '',
                            columns,
                            paginated: table.classList.contains('paginated') || table.hasAttribute('data-paginated'),
                            selectable: table.classList.contains('selectable') || table.hasAttribute('data-selectable'),
                        },
                    };

                    nodes.push(tableNode);

                    relationships.push({
                        id: generateInstanceId(this.instanceCounter, 'has_data_table', `${parentId}:${tableEntityId}`),
                        entityId: generateEntityId('has_data_table', `${parentId}:${tableEntityId}`),
                        type: 'HAS_DATA_TABLE',
                        sourceId: parentId,
                        targetId: tableEntityId,
                        weight: 5,
                        createdAt: this.now,
                    });
                }
            });

        } catch (error: any) {
            logger.warn(`Error extracting tables from JSP: ${error.message}`);
        }

        // Also extract display:table tags from raw content
        const displayTableResult = this.extractDisplayTables(content, filePath, parentId);
        nodes.push(...displayTableResult.nodes);
        relationships.push(...displayTableResult.relationships);

        return { nodes, relationships };
    }

    /**
     * Extract column information from an HTML table.
     */
    private extractTableColumns(table: Element): TableColumnInfo[] {
        const columns: TableColumnInfo[] = [];

        // Look for thead > tr > th
        const headerRow = table.querySelector('thead tr') || table.querySelector('tr:first-child');
        if (!headerRow) return columns;

        const headers = headerRow.querySelectorAll('th, td');
        headers.forEach((th, index) => {
            const header = th.textContent?.trim() || `Column ${index + 1}`;
            const dataField = th.getAttribute('data-field') || th.getAttribute('property') || undefined;
            const sortable = th.hasAttribute('data-sortable') || th.classList.contains('sortable');
            const width = th.getAttribute('width') || undefined;

            // Detect column type from CSS classes or data attributes
            let dataType: TableColumnInfo['dataType'] = 'text';
            if (th.classList.contains('number') || th.classList.contains('numeric')) dataType = 'number';
            if (th.classList.contains('date')) dataType = 'date';
            if (th.classList.contains('currency')) dataType = 'currency';
            if (th.classList.contains('actions') || th.classList.contains('action')) dataType = 'action';

            // Extract action buttons if action column
            let actions: TableActionInfo[] | undefined;
            if (dataType === 'action') {
                actions = this.extractTableActions(th);
            }

            columns.push({
                header,
                dataField,
                dataType,
                sortable,
                width,
                actions,
            });
        });

        return columns;
    }

    /**
     * Extract action buttons from a table action column.
     */
    private extractTableActions(cell: Element): TableActionInfo[] {
        const actions: TableActionInfo[] = [];

        const buttons = cell.querySelectorAll('a, button, input[type="button"], input[type="submit"]');
        buttons.forEach(btn => {
            const label = btn.textContent?.trim() || btn.getAttribute('title') || btn.getAttribute('value') || 'Action';
            const name = btn.getAttribute('name') || btn.getAttribute('data-action') || label.toLowerCase();
            const urlPattern = btn.getAttribute('href') || undefined;
            const confirmMessage = btn.getAttribute('data-confirm') || btn.getAttribute('onclick')?.match(/confirm\(['"]([^'"]+)['"]\)/)?.[1];

            actions.push({
                name,
                label,
                urlPattern,
                confirmMessage,
            });
        });

        return actions;
    }

    /**
     * Extract display:table tags (DisplayTag library).
     */
    private extractDisplayTables(content: string, filePath: string, parentId: string): { nodes: DataTableNode[]; relationships: RelationshipInfo[] } {
        const nodes: DataTableNode[] = [];
        const relationships: RelationshipInfo[] = [];

        // Pattern for <display:table name="..." id="...">
        const displayTablePattern = /<display:table[^>]*>/gi;
        let tableIndex = 0;
        let match;

        while ((match = displayTablePattern.exec(content)) !== null) {
            const tagContent = match[0];

            // Extract attributes
            const idMatch = tagContent.match(/id\s*=\s*["']([^"']+)["']/);
            const nameMatch = tagContent.match(/name\s*=\s*["']([^"']+)["']/);
            const pageSizeMatch = tagContent.match(/pagesize\s*=\s*["'](\d+)["']/);

            const tableId = idMatch?.[1] || `displaytable_${tableIndex++}`;
            const dataSource = nameMatch?.[1] || '';

            // Find closing tag and extract columns
            const closeTagIndex = content.indexOf('</display:table>', match.index);
            const columns: TableColumnInfo[] = [];

            if (closeTagIndex > match.index) {
                const tableContent = content.substring(match.index, closeTagIndex);

                // Extract <display:column> tags
                const columnPattern = /<display:column[^>]*>/gi;
                let colMatch;

                while ((colMatch = columnPattern.exec(tableContent)) !== null) {
                    const colTag = colMatch[0];

                    const propertyMatch = colTag.match(/property\s*=\s*["']([^"']+)["']/);
                    const titleMatch = colTag.match(/title\s*=\s*["']([^"']+)["']/);
                    const titleKeyMatch = colTag.match(/titleKey\s*=\s*["']([^"']+)["']/);
                    const sortableMatch = colTag.match(/sortable\s*=\s*["'](\w+)["']/);
                    const formatMatch = colTag.match(/format\s*=\s*["']([^"']+)["']/);

                    columns.push({
                        header: titleMatch?.[1] || propertyMatch?.[1] || 'Column',
                        headerKey: titleKeyMatch?.[1],
                        dataField: propertyMatch?.[1],
                        sortable: sortableMatch?.[1] === 'true',
                        format: formatMatch?.[1],
                    });
                }
            }

            if (columns.length > 0 || dataSource) {
                const tableEntityId = generateEntityId('datatable', `${filePath}:${tableId}`);

                const tableNode: DataTableNode = {
                    id: generateInstanceId(this.instanceCounter, 'datatable', tableId),
                    entityId: tableEntityId,
                    kind: 'DataTable',
                    name: tableId,
                    filePath,
                    language: 'JSP',
                    startLine: this.getLineNumber(content, match.index),
                    endLine: closeTagIndex > 0 ? this.getLineNumber(content, closeTagIndex) : this.getLineNumber(content, match.index),
                    startColumn: 0,
                    endColumn: 0,
                    parentId,
                    createdAt: this.now,
                    properties: {
                        id: tableId,
                        dataSource,
                        columns,
                        paginated: !!pageSizeMatch,
                        pageSize: pageSizeMatch ? parseInt(pageSizeMatch[1], 10) : undefined,
                    },
                };

                nodes.push(tableNode);

                relationships.push({
                    id: generateInstanceId(this.instanceCounter, 'has_data_table', `${parentId}:${tableEntityId}`),
                    entityId: generateEntityId('has_data_table', `${parentId}:${tableEntityId}`),
                    type: 'HAS_DATA_TABLE',
                    sourceId: parentId,
                    targetId: tableEntityId,
                    weight: 5,
                    createdAt: this.now,
                });
            }
        }

        return { nodes, relationships };
    }

    /**
     * Extract label text for a form field.
     * Looks for:
     * 1. <label for="fieldId"> tags
     * 2. Parent <label> element
     * 3. aria-label attribute
     * 4. Adjacent text nodes with "label" class
     * 5. <fmt:message key="..."> patterns
     */
    private extractFieldLabel(form: Element, fieldName: string, input: Element): string | undefined {
        // 1. Look for explicit label with 'for' attribute
        const fieldId = input.getAttribute('id') || fieldName;
        const labels = form.querySelectorAll(`label[for="${fieldId}"]`);
        if (labels.length > 0 && labels[0]) {
            const labelText = labels[0].textContent?.trim();
            if (labelText) return labelText;
        }

        // 2. Check for parent label
        const parentLabel = input.closest('label');
        if (parentLabel) {
            // Get text content excluding the input element itself
            const clone = parentLabel.cloneNode(true) as Element;
            clone.querySelectorAll('input, select, textarea').forEach(el => el.remove());
            const labelText = clone.textContent?.trim();
            if (labelText) return labelText;
        }

        // 3. Check aria-label
        const ariaLabel = input.getAttribute('aria-label');
        if (ariaLabel) return ariaLabel;

        // 4. Look for preceding text/label sibling with "label" class
        const prevSibling = input.previousElementSibling;
        if (prevSibling) {
            const classList = prevSibling.getAttribute('class') || '';
            if (classList.includes('label') || prevSibling.tagName.toLowerCase() === 'label') {
                const labelText = prevSibling.textContent?.trim();
                if (labelText) return labelText;
            }
        }

        // 5. Check parent's previous sibling (common pattern: <td class="label">...</td><td><input></td>)
        const parentTd = input.closest('td');
        if (parentTd && parentTd.previousElementSibling) {
            const prevTd = parentTd.previousElementSibling;
            const classList = prevTd.getAttribute('class') || '';
            if (classList.includes('label')) {
                const labelText = prevTd.textContent?.trim();
                if (labelText) return labelText;
            }
        }

        return undefined;
    }

    /**
     * Extract <form:errors> elements and their paths from raw JSP content.
     * Returns a map of field path -> error display configuration.
     */
    private extractFormErrors(content: string): Map<string, { path: string; cssClass?: string }> {
        const errors = new Map<string, { path: string; cssClass?: string }>();

        // Pattern for <form:errors path="..." ...>
        const errorPattern = /<form:errors\s+([^>]*)>/gi;
        let match;

        while ((match = errorPattern.exec(content)) !== null) {
            const attributes = match[1];
            const pathMatch = attributes.match(/path\s*=\s*["']([^"']+)["']/);
            const cssClassMatch = attributes.match(/cssClass\s*=\s*["']([^"']+)["']/);

            if (pathMatch && pathMatch[1]) {
                errors.set(pathMatch[1], {
                    path: pathMatch[1],
                    cssClass: cssClassMatch?.[1]
                });
            }
        }

        return errors;
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

    /**
     * Parse Spring form field bindings (form:input, form:select, etc.)
     * Creates BINDS_TO relationships for UI-to-Entity field tracing
     */
    private parseSpringFormBindings(
        content: string,
        filePath: string,
        jspPageEntityId: string
    ): { bindingNodes: FormFieldBindingNode[]; bindingRelationships: RelationshipInfo[] } {
        const bindingNodes: FormFieldBindingNode[] = [];
        const bindingRelationships: RelationshipInfo[] = [];

        // First, find all Spring forms and their model attributes
        const forms = this.extractSpringForms(content);

        // Pattern to extract all Spring form input fields with path attribute
        const fieldPatterns = [
            { pattern: JSP_PATTERNS.SPRING_INPUT, type: 'input' },
            { pattern: JSP_PATTERNS.SPRING_SELECT, type: 'select' },
            { pattern: JSP_PATTERNS.SPRING_TEXTAREA, type: 'textarea' },
            { pattern: JSP_PATTERNS.SPRING_CHECKBOX, type: 'checkbox' },
            { pattern: JSP_PATTERNS.SPRING_RADIOBUTTON, type: 'radio' },
        ];

        for (const { pattern, type } of fieldPatterns) {
            pattern.lastIndex = 0;
            let match;

            while ((match = pattern.exec(content)) !== null) {
                // Extract path (field binding)
                const fullMatch = match[0];
                const fieldPath = match[2] || match[1]; // Different capture groups for different patterns

                if (!fieldPath) continue;

                // Determine model attribute from enclosing form or default
                const modelAttribute = this.findEnclosingFormModel(content, match.index, forms);

                // Parse field path (e.g., "entity.fieldName" -> fieldName)
                const fieldName = fieldPath.includes('.')
                    ? fieldPath.split('.').pop() || fieldPath
                    : fieldPath;

                // Check for required attribute
                const required = /required\s*=\s*["']true["']/.test(fullMatch) ||
                                /\brequired\b/.test(fullMatch);

                // Extract validation attributes
                const validationAttributes: string[] = [];
                if (/maxlength\s*=\s*["'](\d+)["']/.test(fullMatch)) {
                    const maxMatch = fullMatch.match(/maxlength\s*=\s*["'](\d+)["']/);
                    if (maxMatch) validationAttributes.push(`maxLength:${maxMatch[1]}`);
                }
                if (/size\s*=\s*["'](\d+)["']/.test(fullMatch)) {
                    const sizeMatch = fullMatch.match(/size\s*=\s*["'](\d+)["']/);
                    if (sizeMatch) validationAttributes.push(`size:${sizeMatch[1]}`);
                }
                if (required) validationAttributes.push('required');

                const lineNumber = this.getLineNumber(content, match.index);

                // Create FormFieldBinding node
                const bindingEntityId = generateEntityId('formfieldbinding',
                    `${filePath}:${lineNumber}:${fieldPath}`);

                const bindingNode: FormFieldBindingNode = {
                    id: generateInstanceId(this.instanceCounter, 'formfieldbinding',
                        `${fieldPath}:${lineNumber}`),
                    entityId: bindingEntityId,
                    kind: 'FormFieldBinding',
                    name: fieldPath,
                    filePath,
                    language: 'JSP',
                    startLine: lineNumber,
                    endLine: lineNumber,
                    startColumn: 0,
                    endColumn: 0,
                    parentId: jspPageEntityId,
                    createdAt: this.now,
                    properties: {
                        fieldPath,
                        modelAttribute,
                        fieldName,
                        inputType: type,
                        required,
                        validationAttributes,
                        lineNumber,
                    },
                };

                bindingNodes.push(bindingNode);

                // Create HAS_FIELD_BINDING relationship from JSP page to binding
                bindingRelationships.push({
                    id: generateInstanceId(this.instanceCounter, 'has_field_binding',
                        `${jspPageEntityId}:${bindingEntityId}`),
                    entityId: generateEntityId('has_field_binding',
                        `${jspPageEntityId}:${bindingEntityId}`),
                    type: 'HAS_FIELD_BINDING',
                    sourceId: jspPageEntityId,
                    targetId: bindingEntityId,
                    properties: {
                        lineNumber,
                        fieldPath,
                        inputType: type,
                    },
                    weight: 6,
                    createdAt: this.now,
                });

                // Create BINDS_TO relationship for entity field resolution
                // Note: Actual entity field resolution happens in Pass 2 or at query time
                // Here we create a placeholder relationship that can be resolved later
                const entityFieldId = generateEntityId('javafield',
                    `${modelAttribute}.${fieldName}`);

                bindingRelationships.push({
                    id: generateInstanceId(this.instanceCounter, 'binds_to',
                        `${bindingEntityId}:${entityFieldId}`),
                    entityId: generateEntityId('binds_to',
                        `${bindingEntityId}:${entityFieldId}`),
                    type: 'BINDS_TO',
                    sourceId: bindingEntityId,
                    targetId: entityFieldId,
                    properties: {
                        fieldPath,
                        modelAttribute,
                        fieldName,
                        inputType: type,
                        isResolved: false, // Will be resolved in Pass 2
                    },
                    weight: 8,
                    createdAt: this.now,
                });
            }
        }

        return { bindingNodes, bindingRelationships };
    }

    /**
     * Extract Spring form definitions and their model attributes
     */
    private extractSpringForms(content: string): Map<number, string> {
        const forms = new Map<number, string>();

        JSP_PATTERNS.SPRING_FORM.lastIndex = 0;
        let match;

        while ((match = JSP_PATTERNS.SPRING_FORM.exec(content)) !== null) {
            const modelAttribute = match[1];
            if (modelAttribute) {
                forms.set(match.index, modelAttribute);
            }
        }

        return forms;
    }

    /**
     * Find the model attribute for the form enclosing a given position
     */
    private findEnclosingFormModel(
        content: string,
        position: number,
        forms: Map<number, string>
    ): string {
        let closestFormPosition = -1;
        let closestModelAttribute = 'command'; // Default Spring form command name

        for (const [formPosition, modelAttribute] of forms.entries()) {
            if (formPosition < position && formPosition > closestFormPosition) {
                // Check if form is closed before our position
                const formEndMatch = content.substring(formPosition, position).match(/<\/form:form>/i);
                if (!formEndMatch) {
                    closestFormPosition = formPosition;
                    closestModelAttribute = modelAttribute;
                }
            }
        }

        return closestModelAttribute;
    }
}