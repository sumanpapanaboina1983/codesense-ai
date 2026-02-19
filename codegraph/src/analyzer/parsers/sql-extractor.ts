/**
 * SQL Extractor for Java Code
 *
 * Detects SQL statements embedded in Java code including:
 * - @Query annotations (Spring Data JPA)
 * - createQuery/createNativeQuery (JPA EntityManager)
 * - String literals containing SQL patterns
 * - Named queries and JPQL
 *
 * Creates SQLStatement nodes with EXECUTES_SQL relationships.
 */

import Parser from 'tree-sitter';
import { createContextLogger } from '../../utils/logger.js';
import { AstNode, RelationshipInfo, InstanceCounter } from '../types.js';
import { generateInstanceId, generateEntityId } from '../parser-utils.js';

const logger = createContextLogger('SQLExtractor');

/**
 * Represents a detected SQL statement in Java code.
 */
export interface SQLStatementInfo {
    statementType: 'SELECT' | 'INSERT' | 'UPDATE' | 'DELETE' | 'MERGE' | 'CALL' | 'UNKNOWN';
    tableName: string;
    tables: string[];
    columns: string[];
    rawSql: string;
    sourceFile: string;
    lineNumber: number;
    sourceMethod?: string;
    isNativeQuery: boolean;
    isNamedQuery: boolean;
    queryName?: string;
}

/**
 * SQL Statement Node for Neo4j storage.
 */
export interface SQLStatementNode extends AstNode {
    kind: 'SQLStatement';
    language: 'SQL';
    properties: {
        statementType: string;
        tableName: string;
        tables: string[];
        columns: string[];
        rawSql: string;
        isNativeQuery: boolean;
        isNamedQuery: boolean;
        queryName?: string;
        sourceMethod?: string;
    };
}

/**
 * Patterns for detecting SQL in Java code.
 */
const SQL_PATTERNS = {
    // SELECT patterns
    SELECT: /\b(SELECT|select)\s+(?:DISTINCT\s+)?(.+?)\s+(FROM|from)\s+(\w+)/i,
    // INSERT patterns
    INSERT: /\b(INSERT|insert)\s+(INTO|into)\s+(\w+)/i,
    // UPDATE patterns
    UPDATE: /\b(UPDATE|update)\s+(\w+)\s+(SET|set)/i,
    // DELETE patterns
    DELETE: /\b(DELETE|delete)\s+(FROM|from)\s+(\w+)/i,
    // MERGE patterns (Oracle)
    MERGE: /\b(MERGE|merge)\s+(INTO|into)\s+(\w+)/i,
    // Stored procedure calls
    CALL: /\b(CALL|call|EXEC|exec)\s+(\w+)/i,
    // JPQL patterns
    JPQL_SELECT: /\b(SELECT|select)\s+\w+\s+(FROM|from)\s+(\w+)\s+\w+/i,
};

/**
 * Patterns for SQL invocation methods in Java.
 */
const SQL_INVOCATION_PATTERNS = {
    // JPA/Hibernate
    createQuery: /createQuery\s*\(\s*["'](.+?)["']/,
    createNativeQuery: /createNativeQuery\s*\(\s*["'](.+?)["']/,
    // Spring JDBC
    jdbcQuery: /(?:query|update|execute)\s*\(\s*["'](.+?)["']/,
    // MyBatis-style
    sqlSession: /(?:selectOne|selectList|insert|update|delete)\s*\(\s*["'](.+?)["']/,
};

/**
 * Extracts SQL statements from Java source code.
 */
export class SQLExtractor {
    private instanceCounter: InstanceCounter;
    private filePath: string;
    private now: string;
    private nodes: SQLStatementNode[] = [];
    private relationships: RelationshipInfo[] = [];

    constructor(filePath: string, instanceCounter: InstanceCounter) {
        this.filePath = filePath;
        this.instanceCounter = instanceCounter;
        this.now = new Date().toISOString();
    }

    /**
     * Extract SQL statements from a tree-sitter AST node.
     */
    extractFromNode(
        node: Parser.SyntaxNode,
        sourceText: string,
        parentMethodId?: string
    ): { nodes: SQLStatementNode[]; relationships: RelationshipInfo[] } {
        this.nodes = [];
        this.relationships = [];

        // Extract from annotations (@Query)
        this.extractFromAnnotations(node, sourceText, parentMethodId);

        // Extract from method invocations (createQuery, etc.)
        this.extractFromMethodInvocations(node, sourceText, parentMethodId);

        // Extract from string literals
        this.extractFromStringLiterals(node, sourceText, parentMethodId);

        return { nodes: this.nodes, relationships: this.relationships };
    }

    /**
     * Extract SQL from @Query annotations (Spring Data JPA).
     */
    private extractFromAnnotations(
        node: Parser.SyntaxNode,
        sourceText: string,
        parentMethodId?: string
    ): void {
        // Find annotation nodes
        this.traverseForAnnotations(node, (annotationNode) => {
            const annotationText = annotationNode.text;

            // Check for @Query annotation
            if (annotationText.includes('@Query') || annotationText.includes('@NamedQuery')) {
                const isNamedQuery = annotationText.includes('@NamedQuery');
                const isNativeQuery = annotationText.includes('nativeQuery') &&
                                      annotationText.includes('true');

                // Extract the query value
                const valueMatch = annotationText.match(/value\s*=\s*["'](.+?)["']/s) ||
                                   annotationText.match(/@Query\s*\(\s*["'](.+?)["']/s);

                if (valueMatch && valueMatch[1]) {
                    const rawSql = this.cleanSqlString(valueMatch[1]);
                    const sqlInfo = this.parseSqlStatement(rawSql);

                    const sqlNode = this.createSQLStatementNode({
                        ...sqlInfo,
                        rawSql,
                        sourceFile: this.filePath,
                        lineNumber: annotationNode.startPosition.row + 1,
                        sourceMethod: parentMethodId,
                        isNativeQuery,
                        isNamedQuery,
                    });

                    this.nodes.push(sqlNode);

                    // Create relationship to parent method
                    if (parentMethodId) {
                        this.createExecutesSQLRelationship(parentMethodId, sqlNode.entityId,
                            annotationNode.startPosition.row + 1);
                    }
                }
            }
        });
    }

    /**
     * Extract SQL from method invocations like createQuery().
     */
    private extractFromMethodInvocations(
        node: Parser.SyntaxNode,
        sourceText: string,
        parentMethodId?: string
    ): void {
        this.traverseForMethodInvocations(node, (invocationNode) => {
            const invocationText = invocationNode.text;

            for (const [patternName, pattern] of Object.entries(SQL_INVOCATION_PATTERNS)) {
                const match = invocationText.match(pattern);
                if (match && match[1]) {
                    const rawSql = this.cleanSqlString(match[1]);

                    // Skip if too short or doesn't look like SQL
                    if (rawSql.length < 10 || !this.looksLikeSql(rawSql)) {
                        continue;
                    }

                    const sqlInfo = this.parseSqlStatement(rawSql);
                    const isNativeQuery = patternName === 'createNativeQuery';

                    const sqlNode = this.createSQLStatementNode({
                        ...sqlInfo,
                        rawSql,
                        sourceFile: this.filePath,
                        lineNumber: invocationNode.startPosition.row + 1,
                        sourceMethod: parentMethodId,
                        isNativeQuery,
                        isNamedQuery: false,
                    });

                    this.nodes.push(sqlNode);

                    if (parentMethodId) {
                        this.createExecutesSQLRelationship(parentMethodId, sqlNode.entityId,
                            invocationNode.startPosition.row + 1);
                    }
                }
            }
        });
    }

    /**
     * Extract SQL from string literals.
     */
    private extractFromStringLiterals(
        node: Parser.SyntaxNode,
        sourceText: string,
        parentMethodId?: string
    ): void {
        this.traverseForStringLiterals(node, (stringNode) => {
            const stringText = stringNode.text;

            // Remove quotes
            const content = stringText.slice(1, -1);

            // Skip if too short
            if (content.length < 15) return;

            // Check if it looks like SQL
            if (this.looksLikeSql(content)) {
                const rawSql = this.cleanSqlString(content);
                const sqlInfo = this.parseSqlStatement(rawSql);

                // Only create node if we could parse meaningful SQL
                if (sqlInfo.statementType !== 'UNKNOWN' || sqlInfo.tables.length > 0) {
                    const sqlNode = this.createSQLStatementNode({
                        ...sqlInfo,
                        rawSql,
                        sourceFile: this.filePath,
                        lineNumber: stringNode.startPosition.row + 1,
                        sourceMethod: parentMethodId,
                        isNativeQuery: true, // Assume native if in string literal
                        isNamedQuery: false,
                    });

                    this.nodes.push(sqlNode);

                    if (parentMethodId) {
                        this.createExecutesSQLRelationship(parentMethodId, sqlNode.entityId,
                            stringNode.startPosition.row + 1);
                    }
                }
            }
        });
    }

    /**
     * Check if a string looks like SQL.
     */
    private looksLikeSql(text: string): boolean {
        const upperText = text.toUpperCase().trim();
        const sqlKeywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'FROM', 'WHERE',
                            'JOIN', 'SET', 'VALUES', 'INTO', 'MERGE', 'CALL'];

        return sqlKeywords.some(kw => upperText.includes(kw));
    }

    /**
     * Parse a SQL statement to extract type, tables, and columns.
     */
    private parseSqlStatement(sql: string): Omit<SQLStatementInfo, 'rawSql' | 'sourceFile' | 'lineNumber' | 'sourceMethod' | 'isNativeQuery' | 'isNamedQuery'> {
        const result: Omit<SQLStatementInfo, 'rawSql' | 'sourceFile' | 'lineNumber' | 'sourceMethod' | 'isNativeQuery' | 'isNamedQuery'> = {
            statementType: 'UNKNOWN',
            tableName: '',
            tables: [],
            columns: [],
        };

        const upperSql = sql.toUpperCase().trim();

        // Determine statement type and extract tables
        if (upperSql.startsWith('SELECT') || SQL_PATTERNS.SELECT.test(sql)) {
            result.statementType = 'SELECT';
            this.extractSelectInfo(sql, result);
        } else if (upperSql.startsWith('INSERT') || SQL_PATTERNS.INSERT.test(sql)) {
            result.statementType = 'INSERT';
            this.extractInsertInfo(sql, result);
        } else if (upperSql.startsWith('UPDATE') || SQL_PATTERNS.UPDATE.test(sql)) {
            result.statementType = 'UPDATE';
            this.extractUpdateInfo(sql, result);
        } else if (upperSql.startsWith('DELETE') || SQL_PATTERNS.DELETE.test(sql)) {
            result.statementType = 'DELETE';
            this.extractDeleteInfo(sql, result);
        } else if (upperSql.startsWith('MERGE') || SQL_PATTERNS.MERGE.test(sql)) {
            result.statementType = 'MERGE';
            this.extractMergeInfo(sql, result);
        } else if (upperSql.startsWith('CALL') || upperSql.startsWith('EXEC')) {
            result.statementType = 'CALL';
        }

        // Set primary table
        if (result.tables.length > 0) {
            result.tableName = result.tables[0];
        }

        return result;
    }

    /**
     * Extract table and column info from SELECT statement.
     */
    private extractSelectInfo(sql: string, result: Omit<SQLStatementInfo, 'rawSql' | 'sourceFile' | 'lineNumber' | 'sourceMethod' | 'isNativeQuery' | 'isNamedQuery'>): void {
        // Extract columns
        const selectMatch = sql.match(/SELECT\s+(?:DISTINCT\s+)?(.+?)\s+FROM/i);
        if (selectMatch && selectMatch[1]) {
            const columnsStr = selectMatch[1];
            if (columnsStr !== '*') {
                result.columns = columnsStr.split(',')
                    .map(c => c.trim().split(/\s+/).pop() || c.trim())
                    .filter(c => c && c !== '*');
            }
        }

        // Extract tables from FROM clause
        const fromMatch = sql.match(/FROM\s+(\w+(?:\s+\w+)?(?:\s*,\s*\w+(?:\s+\w+)?)*)/i);
        if (fromMatch && fromMatch[1]) {
            result.tables = fromMatch[1].split(',')
                .map(t => t.trim().split(/\s+/)[0])
                .filter(Boolean);
        }

        // Extract tables from JOINs
        const joinMatches = sql.matchAll(/JOIN\s+(\w+)/gi);
        for (const match of joinMatches) {
            if (match[1] && !result.tables.includes(match[1])) {
                result.tables.push(match[1]);
            }
        }
    }

    /**
     * Extract table and column info from INSERT statement.
     */
    private extractInsertInfo(sql: string, result: Omit<SQLStatementInfo, 'rawSql' | 'sourceFile' | 'lineNumber' | 'sourceMethod' | 'isNativeQuery' | 'isNamedQuery'>): void {
        const insertMatch = sql.match(/INSERT\s+INTO\s+(\w+)\s*\(([^)]+)\)/i);
        if (insertMatch) {
            if (insertMatch[1]) result.tables = [insertMatch[1]];
            if (insertMatch[2]) {
                result.columns = insertMatch[2].split(',').map(c => c.trim()).filter(Boolean);
            }
        } else {
            // Simple INSERT INTO table
            const simpleMatch = sql.match(/INSERT\s+INTO\s+(\w+)/i);
            if (simpleMatch && simpleMatch[1]) {
                result.tables = [simpleMatch[1]];
            }
        }
    }

    /**
     * Extract table and column info from UPDATE statement.
     */
    private extractUpdateInfo(sql: string, result: Omit<SQLStatementInfo, 'rawSql' | 'sourceFile' | 'lineNumber' | 'sourceMethod' | 'isNativeQuery' | 'isNamedQuery'>): void {
        const updateMatch = sql.match(/UPDATE\s+(\w+)\s+SET\s+(.+?)(?:\s+WHERE|$)/i);
        if (updateMatch) {
            if (updateMatch[1]) result.tables = [updateMatch[1]];
            if (updateMatch[2]) {
                // Extract column names from SET clause
                const setMatches = updateMatch[2].matchAll(/(\w+)\s*=/g);
                for (const match of setMatches) {
                    if (match[1]) result.columns.push(match[1]);
                }
            }
        }
    }

    /**
     * Extract table info from DELETE statement.
     */
    private extractDeleteInfo(sql: string, result: Omit<SQLStatementInfo, 'rawSql' | 'sourceFile' | 'lineNumber' | 'sourceMethod' | 'isNativeQuery' | 'isNamedQuery'>): void {
        const deleteMatch = sql.match(/DELETE\s+FROM\s+(\w+)/i);
        if (deleteMatch && deleteMatch[1]) {
            result.tables = [deleteMatch[1]];
        }
    }

    /**
     * Extract table info from MERGE statement.
     */
    private extractMergeInfo(sql: string, result: Omit<SQLStatementInfo, 'rawSql' | 'sourceFile' | 'lineNumber' | 'sourceMethod' | 'isNativeQuery' | 'isNamedQuery'>): void {
        const mergeMatch = sql.match(/MERGE\s+INTO\s+(\w+)/i);
        if (mergeMatch && mergeMatch[1]) {
            result.tables = [mergeMatch[1]];
        }

        // Also extract USING table
        const usingMatch = sql.match(/USING\s+(\w+)/i);
        if (usingMatch && usingMatch[1] && !result.tables.includes(usingMatch[1])) {
            result.tables.push(usingMatch[1]);
        }
    }

    /**
     * Clean a SQL string by removing escape characters and normalizing whitespace.
     */
    private cleanSqlString(sql: string): string {
        return sql
            .replace(/\\n/g, ' ')
            .replace(/\\t/g, ' ')
            .replace(/\\"/g, '"')
            .replace(/\\'/g, "'")
            .replace(/\s+/g, ' ')
            .trim();
    }

    /**
     * Create a SQLStatementNode.
     */
    private createSQLStatementNode(info: SQLStatementInfo): SQLStatementNode {
        const entityId = generateEntityId('sqlstatement',
            `${info.sourceFile}:${info.lineNumber}:${info.statementType}:${info.tableName}`);

        return {
            id: generateInstanceId(this.instanceCounter, 'sqlstatement',
                `${info.statementType}_${info.tableName}`, { line: info.lineNumber }),
            entityId,
            kind: 'SQLStatement',
            name: `${info.statementType} ${info.tableName}`.trim(),
            filePath: info.sourceFile,
            language: 'SQL',
            startLine: info.lineNumber,
            endLine: info.lineNumber,
            startColumn: 0,
            endColumn: 0,
            createdAt: this.now,
            properties: {
                statementType: info.statementType,
                tableName: info.tableName,
                tables: info.tables,
                columns: info.columns,
                rawSql: info.rawSql.substring(0, 1000), // Limit size
                isNativeQuery: info.isNativeQuery,
                isNamedQuery: info.isNamedQuery,
                queryName: info.queryName,
                sourceMethod: info.sourceMethod,
            },
        };
    }

    /**
     * Create EXECUTES_SQL relationship.
     */
    private createExecutesSQLRelationship(
        sourceMethodId: string,
        targetSqlId: string,
        lineNumber: number
    ): void {
        const relEntityId = generateEntityId('executes_sql', `${sourceMethodId}:${targetSqlId}`);

        this.relationships.push({
            id: generateInstanceId(this.instanceCounter, 'executes_sql',
                `${sourceMethodId}:${targetSqlId}`),
            entityId: relEntityId,
            type: 'EXECUTES_SQL',
            sourceId: sourceMethodId,
            targetId: targetSqlId,
            properties: {
                lineNumber,
            },
            weight: 8,
            createdAt: this.now,
        });
    }

    /**
     * Traverse tree to find annotation nodes.
     */
    private traverseForAnnotations(
        node: Parser.SyntaxNode,
        callback: (node: Parser.SyntaxNode) => void
    ): void {
        if (node.type === 'marker_annotation' || node.type === 'annotation') {
            callback(node);
        }
        for (const child of node.namedChildren) {
            this.traverseForAnnotations(child, callback);
        }
    }

    /**
     * Traverse tree to find method invocation nodes.
     */
    private traverseForMethodInvocations(
        node: Parser.SyntaxNode,
        callback: (node: Parser.SyntaxNode) => void
    ): void {
        if (node.type === 'method_invocation') {
            callback(node);
        }
        for (const child of node.namedChildren) {
            this.traverseForMethodInvocations(child, callback);
        }
    }

    /**
     * Traverse tree to find string literal nodes.
     */
    private traverseForStringLiterals(
        node: Parser.SyntaxNode,
        callback: (node: Parser.SyntaxNode) => void
    ): void {
        if (node.type === 'string_literal') {
            callback(node);
        }
        for (const child of node.namedChildren) {
            this.traverseForStringLiterals(child, callback);
        }
    }

    /**
     * Get all nodes generated by this extractor.
     */
    getNodes(): SQLStatementNode[] {
        return this.nodes;
    }

    /**
     * Get all relationships generated by this extractor.
     */
    getRelationships(): RelationshipInfo[] {
        return this.relationships;
    }
}

export default SQLExtractor;
