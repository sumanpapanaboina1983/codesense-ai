/**
 * ResourceBundleParser - Parse .properties files to extract error messages and i18n text.
 *
 * This parser extracts message keys and their values from Java resource bundle files,
 * creating ErrorMessage nodes that can be linked to code references.
 */

import path from 'path';
import fs from 'fs/promises';
import { createContextLogger } from '../../utils/logger.js';
import { FileInfo } from '../../scanner/file-scanner.js';
import { AstNode, RelationshipInfo, SingleFileParseResult, InstanceCounter, ErrorMessageNode } from '../types.js';
import { generateInstanceId, generateEntityId, ensureTempDir, getTempFilePath } from '../parser-utils.js';

const logger = createContextLogger('ResourceBundleParser');

/**
 * Parsed property entry from a .properties file.
 */
export interface PropertyEntry {
    key: string;
    value: string;
    lineNumber: number;
    /** Parameters found in the message (e.g., {0}, {1}) */
    parameters: string[];
    /** Whether this looks like an error message */
    isErrorMessage: boolean;
    /** Whether this looks like a label */
    isLabel: boolean;
}

/**
 * Parser for Java .properties files (resource bundles).
 * Extracts message keys and values for BRD generation.
 */
export class ResourceBundleParser {
    private instanceCounter: InstanceCounter = { count: 0 };
    private now: string = new Date().toISOString();

    constructor() {}

    /**
     * Check if this parser can handle the given file.
     */
    canParse(fileInfo: FileInfo): boolean {
        const ext = path.extname(fileInfo.path).toLowerCase();
        return ext === '.properties';
    }

    /**
     * Parse a .properties file and extract message entries.
     * Returns the path to the temp JSON file containing the parse results.
     */
    async parseFile(fileInfo: FileInfo): Promise<string> {
        const filePath = fileInfo.path;
        logger.info(`Parsing resource bundle: ${filePath}`);

        await ensureTempDir();

        try {
            const content = await fs.readFile(filePath, 'utf-8');
            const entries = this.parseProperties(content);

            const nodes: AstNode[] = [];
            const relationships: RelationshipInfo[] = [];

            // Determine locale from filename (e.g., messages_en.properties -> 'en')
            const locale = this.extractLocale(filePath);

            // Create ErrorMessage nodes for each entry
            for (const entry of entries) {
                const entityId = generateEntityId('errormessage', `${filePath}:${entry.key}`);

                const node: ErrorMessageNode = {
                    id: generateInstanceId(this.instanceCounter, 'errormessage', entry.key),
                    entityId,
                    kind: 'ErrorMessage',
                    name: entry.key,
                    filePath,
                    language: 'Properties',
                    startLine: entry.lineNumber,
                    endLine: entry.lineNumber,
                    startColumn: 0,
                    endColumn: entry.value.length,
                    createdAt: this.now,
                    properties: {
                        messageKey: entry.key,
                        messageText: entry.value,
                        sourceFile: filePath,
                        locale: locale || undefined,
                        parameters: entry.parameters.length > 0 ? entry.parameters : undefined,
                    }
                };

                nodes.push(node);
            }

            logger.info(`Parsed ${entries.length} message entries from ${filePath}`);

            // Write results to temp file
            const result: SingleFileParseResult = {
                filePath,
                nodes,
                relationships,
            };

            const tempFilePath = getTempFilePath(filePath);
            await fs.writeFile(tempFilePath, JSON.stringify(result, null, 2), 'utf-8');

            return tempFilePath;

        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            logger.error(`Failed to parse ${filePath}: ${message}`);

            // Write error result to temp file
            const result: SingleFileParseResult = {
                filePath,
                nodes: [],
                relationships: [],
            };

            const tempFilePath = getTempFilePath(filePath);
            await fs.writeFile(tempFilePath, JSON.stringify(result, null, 2), 'utf-8');

            return tempFilePath;
        }
    }

    /**
     * Parse .properties file content into structured entries.
     */
    private parseProperties(content: string): PropertyEntry[] {
        const entries: PropertyEntry[] = [];
        const lines = content.split('\n');

        let currentKey = '';
        let currentValue = '';
        let startLineNumber = 0;
        let isContinuation = false;

        for (let i = 0; i < lines.length; i++) {
            const lineNumber = i + 1;
            let line = lines[i];

            // Skip empty lines and comments
            if (line.trim() === '' || line.trim().startsWith('#') || line.trim().startsWith('!')) {
                // If we were building a value, finish it
                if (currentKey && currentValue) {
                    entries.push(this.createPropertyEntry(currentKey, currentValue, startLineNumber));
                    currentKey = '';
                    currentValue = '';
                    isContinuation = false;
                }
                continue;
            }

            // Handle line continuation (backslash at end)
            const isLineEndsWithBackslash = line.trimEnd().endsWith('\\');
            if (isLineEndsWithBackslash) {
                line = line.trimEnd().slice(0, -1); // Remove trailing backslash
            }

            if (isContinuation) {
                // Continue building the value
                currentValue += line.trimStart();
            } else {
                // New key-value pair
                // Find the separator (= or :)
                const separatorMatch = line.match(/^([^=:]+)[=:]\s*(.*)/);
                if (separatorMatch) {
                    // Save previous entry if exists
                    if (currentKey && currentValue) {
                        entries.push(this.createPropertyEntry(currentKey, currentValue, startLineNumber));
                    }

                    currentKey = separatorMatch[1].trim();
                    currentValue = separatorMatch[2] || '';
                    startLineNumber = lineNumber;
                }
            }

            isContinuation = isLineEndsWithBackslash;
        }

        // Don't forget the last entry
        if (currentKey && currentValue) {
            entries.push(this.createPropertyEntry(currentKey, currentValue, startLineNumber));
        }

        return entries;
    }

    /**
     * Create a PropertyEntry with metadata analysis.
     */
    private createPropertyEntry(key: string, value: string, lineNumber: number): PropertyEntry {
        // Extract parameters (e.g., {0}, {1}, {fieldName})
        const paramPattern = /\{(\w+)\}/g;
        const parameters: string[] = [];
        let match;
        while ((match = paramPattern.exec(value)) !== null) {
            if (match[1] && !parameters.includes(match[1])) {
                parameters.push(match[1]);
            }
        }

        // Determine if this is an error message based on key patterns
        const errorKeywords = ['error', 'err', 'fail', 'invalid', 'required', 'notfound', 'exception', 'warn', 'warning'];
        const isErrorMessage = errorKeywords.some(kw => key.toLowerCase().includes(kw)) ||
                              value.toLowerCase().includes('error') ||
                              value.toLowerCase().includes('invalid') ||
                              value.toLowerCase().includes('required') ||
                              value.toLowerCase().includes('failed');

        // Determine if this is a label based on key patterns
        const labelKeywords = ['label', 'title', 'header', 'button', 'menu', 'tab', 'field'];
        const isLabel = labelKeywords.some(kw => key.toLowerCase().includes(kw));

        return {
            key,
            value: this.unescapePropertyValue(value),
            lineNumber,
            parameters,
            isErrorMessage,
            isLabel
        };
    }

    /**
     * Unescape Java properties file escape sequences.
     */
    private unescapePropertyValue(value: string): string {
        return value
            .replace(/\\n/g, '\n')
            .replace(/\\t/g, '\t')
            .replace(/\\r/g, '\r')
            .replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)))
            .replace(/\\\\/g, '\\')
            .replace(/\\=/g, '=')
            .replace(/\\:/g, ':');
    }

    /**
     * Extract locale from filename (e.g., messages_en_US.properties -> 'en_US').
     */
    private extractLocale(filePath: string): string | null {
        const basename = path.basename(filePath, '.properties');

        // Pattern: name_locale (e.g., messages_en, messages_en_US, ValidationMessages_fr)
        const localeMatch = basename.match(/_([a-z]{2}(?:_[A-Z]{2})?)$/);

        return localeMatch ? localeMatch[1] : null;
    }
}

/**
 * Create a singleton instance for use by the main parser.
 */
export const resourceBundleParser = new ResourceBundleParser();
