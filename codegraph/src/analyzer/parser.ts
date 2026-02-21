// src/analyzer/parser.ts
import path from 'path';
import fs from 'fs/promises';
import { Project, ScriptKind, ScriptTarget, ModuleKind, ModuleResolutionKind } from 'ts-morph';
import { FileInfo } from '../scanner/file-scanner.js';
import { AstNode, RelationshipInfo, SingleFileParseResult, FileNode, AnalysisContext } from './types.js';
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
import { JSPParser } from './parsers/jsp-parser.js';
import { WebFlowParser } from './parsers/webflow-parser.js';
import { EnhancedJavaParser } from './parsers/java-parser-enhanced.js';
import { JSPSpringIntegrator, IntegrationContext } from './integrators/jsp-spring-integrator.js';
import { MenuParser } from './parsers/menu-parser.js';
import { ResourceBundleParser } from './parsers/resource-bundle-parser.js';

import { createContextLogger } from '../utils/logger.js';
import { ParserError } from '../utils/errors.js';
import config from '../config/index.js';
import { generateEntityId, generateInstanceId } from './parser-utils.js';
import ts from 'typescript';
import pLimit from 'p-limit';

const logger = createContextLogger('Parser');

/**
 * Orchestrates the parsing process for different languages.
 */
export class Parser {
    private tsProject: Project;
    private pythonParser: PythonAstParser;
    private cppParser: CCppParser;
    private javaParser: JavaParser;
    private goParser: GoParser;
    private csharpParser: CSharpParser;
    // private sqlParser: SqlParser; // Temporarily disabled
    private tsResults: Map<string, SingleFileParseResult> = new Map(); // Store TS results in memory
    private jspParser: JSPParser;
    private webFlowParser: WebFlowParser;
    private enhancedJavaParser: EnhancedJavaParser;
    private jspSpringIntegrator: JSPSpringIntegrator;
    private menuParser: MenuParser;
    private resourceBundleParser: ResourceBundleParser;
    private analysisContext?: AnalysisContext; // Store analysis context for multi-repository support

    constructor() {
        // Initialize Project with default compiler options (no tsconfig required)
        // This allows parsing TS/JS files from any repository without requiring a tsconfig.json
        this.tsProject = new Project({
            compilerOptions: {
                target: ScriptTarget.ES2020,
                module: ModuleKind.ESNext,
                moduleResolution: ModuleResolutionKind.NodeNext,
                jsx: ts.JsxEmit.React as unknown as number,
                esModuleInterop: true,
                allowJs: true,
                checkJs: false,
                strict: false,
                skipLibCheck: true,
                resolveJsonModule: true,
            },
            skipAddingFilesFromTsConfig: true,
        });
        this.pythonParser = new PythonAstParser();
        this.cppParser = new CCppParser();
        this.javaParser = new JavaParser();
        this.goParser = new GoParser();
        this.csharpParser = new CSharpParser();
        this.jspParser = new JSPParser();
        this.webFlowParser = new WebFlowParser();
        this.enhancedJavaParser = new EnhancedJavaParser();
        this.jspSpringIntegrator = new JSPSpringIntegrator();
        this.menuParser = new MenuParser();
        this.resourceBundleParser = new ResourceBundleParser();

        // this.sqlParser = new SqlParser(); // Temporarily disabled
        // Removed tsParser instantiation
        logger.info('Parser initialized with default compiler options (Menu parser, ResourceBundle parser enabled, SQL parser temporarily disabled).');
    }

    /**
     * Parses a list of files, delegating to the appropriate language parser.
     * For TS/JS files, it adds them to the ts-morph project but doesn't generate separate JSON.
     * @param files - An array of FileInfo objects.
     * @param context - Optional analysis context for multi-repository support.
     * @returns A promise that resolves when all files have been parsed (Pass 1).
     */
    async parseFiles(files: FileInfo[], context?: AnalysisContext): Promise<void> {
        this.analysisContext = context; // Store context for use in other methods
        logger.info(`Starting Pass 1 processing for ${files.length} files (concurrency: ${config.parseConcurrency})...${context ? ` (Repository: ${context.repositoryName})` : ''}`);

        // Create concurrency limiter to prevent OOM when parsing many files
        const limit = pLimit(config.parseConcurrency);
        const parsePromises: Promise<string | null>[] = [];
        // Store normalized paths of all files passed to this specific run
        const targetFilePaths = new Set(files.map(f => path.resolve(f.path).replace(/\\/g, '/')));

        const tsFilesToAdd: string[] = [];

        for (const file of files) {
            let parsePromise: Promise<string | null> | null = null;
            try {
                switch (file.extension) {
                    case '.py':
                        parsePromise = limit(() => this.pythonParser.parseFile(file));
                        break;
                    case '.c':
                    case '.cpp':
                    case '.h':
                    case '.hpp':
                        parsePromise = limit(() => this.cppParser.parseFile(file));
                        break;
                    case '.java':
                        parsePromise = limit(() => this.enhancedJavaParser.parseFile(file));
                        break;
                    case '.go':
                        parsePromise = limit(() => this.goParser.parseFile(file));
                        break;
                    case '.cs':
                        parsePromise = limit(() => this.csharpParser.parseFile(file));
                        break;
                    // case '.sql': // Temporarily disabled
                    //     parsePromise = limit(() => this.sqlParser.parseFile(file));
                    //     break;
                    case '.ts':
                    case '.tsx':
                    case '.js':
                    case '.jsx':
                    case '.mjs':
                    case '.cjs':
                        // Add TS/JS files to the project instead of calling a separate parser
                        logger.debug(`Adding TS/JS file to project: ${file.path}`);
                        tsFilesToAdd.push(file.path);
                        parsePromise = Promise.resolve(null); // No JSON file generated for TS/JS in Pass 1
                        break;
                    case '.jsp':
                    case '.jspx':
                        parsePromise = limit(() => this.jspParser.parseFile(file));
                        break;
                    case '.properties':
                        // Parse resource bundle files for error messages and i18n
                        parsePromise = limit(() => this.resourceBundleParser.parseFile(file));
                        break;
                    case '.xml':
                        // Check if it's a menu config file first
                        if (this.menuParser.isMenuConfigFile(file.path)) {
                            // Set repository ID if available
                            if (context?.repositoryId) {
                                this.menuParser.setRepositoryId(context.repositoryId);
                            }
                            parsePromise = limit(() => this.menuParser.parseFile(file));
                        } else if (this.isWebFlowFile(file.path)) {
                            // Check if it's a Spring Web Flow file
                            parsePromise = limit(() => this.webFlowParser.parseFile(file));
                        } else {
                            parsePromise = Promise.resolve(null);
                        }
                        break;
                    default:
                        const supportedNonSql = config.supportedExtensions.filter(ext => ext !== '.sql');
                        if (!supportedNonSql.includes(file.extension)) {
                            logger.warn(`Unsupported file type: ${file.extension} for ${file.path}`);
                        } else if (file.extension === '.sql') {
                             logger.info(`Skipping SQL file due to parser being temporarily disabled: ${file.path}`);
                        }
                        parsePromise = Promise.resolve(null);
                }
            } catch (error: any) {
                 logger.error(`Error initiating processing for ${file.path}: ${error.message}`);
                 parsePromise = Promise.resolve(null);
            }
             if (parsePromise) {
                 parsePromises.push(
                     parsePromise.catch(err => {
                         logger.error(`Parsing failed for ${file.path}: ${err.message}`);
                         return null;
                     })
                 );
             }
        }

        if (tsFilesToAdd.length > 0) {
            this.tsProject.addSourceFilesAtPaths(tsFilesToAdd);
            logger.info(`Added ${tsFilesToAdd.length} TS/JS files to the ts-morph project.`);
            // Now parse the added TS/JS files
            // Pass the set of target file paths to filter which sourceFiles get fully parsed
            await this._parseTsProjectFiles(targetFilePaths);
        }

        await Promise.all(parsePromises);
        logger.info('Pass 1 processing completed for all initiated files.');
    }

    // Add method to check if XML file is a Web Flow definition
    private isWebFlowFile(filePath: string): boolean {
        // Check file path patterns
        const flowPatterns = [
            '/flows/',
            '/webflow/',
            '/flow/',
            '-flow.xml',
            'flow.xml'
        ];

        const pathLower = filePath.toLowerCase();
        return flowPatterns.some(pattern => pathLower.includes(pattern));
    }

     private buildIntegrationContext(allNodes: AstNode[]): IntegrationContext {
        return {
            jspNodes: allNodes.filter(n => n.kind === 'JSPPage') as any[],
            jspFormNodes: allNodes.filter(n => n.kind === 'JSPForm') as any[],
            webFlowNodes: allNodes.filter(n => n.kind === 'WebFlowDefinition') as any[],
            flowStateNodes: allNodes.filter(n => n.kind === 'FlowState') as any[],
            flowActionNodes: allNodes.filter(n => n.kind === 'FlowAction') as any[],
            springControllerNodes: allNodes.filter(n => n.kind === 'SpringController') as any[],
            flowActionMethodNodes: allNodes.filter(n => n.kind === 'FlowActionMethod') as any[],
            springServiceNodes: allNodes.filter(n => n.kind === 'SpringService') as any[],
            allNodes
        };
    }
     /**
     * Collects all nodes and relationships from the temporary JSON files
     * generated during Pass 1 (for non-TS languages).
     * Uses Maps to ensure entityId uniqueness.
     * @returns An object containing arrays of all nodes and relationships.
     * Includes results from in-memory TS parsing.
     */
     async collectResults(): Promise<{ allNodes: AstNode[], allRelationships: RelationshipInfo[] }> {
        logger.info('Starting collection of Pass 1 results (JSON + TS)...');
        const nodeMap = new Map<string, AstNode>(); // Use Map for nodes
        const relationshipMap = new Map<string, RelationshipInfo>(); // Use Map for relationships
        const tempDir = config.tempDir;

        try {
            const files = await fs.readdir(tempDir);
            const jsonFiles = files.filter(f => f.endsWith('.json'));
            logger.info(`Found ${jsonFiles.length} temporary JSON files to process.`);
            let processedJsonCount = 0;

            for (const file of jsonFiles) {
                processedJsonCount++;
                const filePath = path.join(tempDir, file);
                // logger.debug(`[collectResults] Processing JSON file ${processedJsonCount}/${jsonFiles.length}: ${file}`); // Removed log
                try {
                    const content = await fs.readFile(filePath, 'utf-8');
                    const result: SingleFileParseResult = JSON.parse(content);
                    // logger.debug(`[collectResults] Parsed JSON for: ${file} (Source Path: ${result.filePath})`); // Removed log

                    if (result.filePath && result.nodes && result.relationships) {
                        // Deduplicate nodes within this specific JSON file first
                        const fileNodeMap = new Map<string, AstNode>();
                        let intraFileDuplicates = 0;
                        for (const node of result.nodes) {
                            if (fileNodeMap.has(node.entityId)) {
                                // logger.warn(`[collectResults] Intra-file duplicate node entityId found in ${result.filePath}: ${node.entityId} (Kind: ${node.kind})`); // Removed log
                                intraFileDuplicates++;
                            }
                            fileNodeMap.set(node.entityId, node);
                        }
                        if (intraFileDuplicates > 0) {
                            logger.warn(`[collectResults] Found ${intraFileDuplicates} intra-file duplicate nodes in ${result.filePath}.`);
                        }

                        // Add unique nodes from this file to the main map
                        for (const [entityId, node] of fileNodeMap.entries()) {
                            if (nodeMap.has(entityId)) {
                                const existingNode = nodeMap.get(entityId);
                                if (node.kind === 'File' && existingNode?.kind === 'File') {
                                     logger.warn(`[collectResults] Overwriting File node with entityId: ${entityId} (Incoming: ${node.filePath}, Existing: ${existingNode?.filePath})`);
                                } else if (existingNode?.filePath !== node.filePath) {
                                    // logger.warn(`[collectResults] Cross-file duplicate node entityId (overwriting): ${entityId} (Kind: ${node.kind}, Incoming: ${node.filePath}, Existing: ${existingNode?.filePath})`); // Removed log
                                }
                            }
                            nodeMap.set(entityId, node);
                        }

                        // Add relationships to map (duplicates less likely but handle anyway)
                        for (const rel of result.relationships) {
                             if (relationshipMap.has(rel.entityId)) {
                                 // logger.warn(`[collectResults] Overwriting relationship with duplicate entityId: ${rel.entityId} (Type: ${rel.type})`); // Removed log
                             }
                             relationshipMap.set(rel.entityId, rel);
                        }
                        // logger.debug(`[collectResults] Processed ${fileNodeMap.size} unique nodes and ${result.relationships.length} relationships from ${file}`); // Removed log

                    } else {
                        logger.warn(`Skipping invalid JSON structure in file: ${file}`);
                    }
                     // Temporarily disable temp file cleanup for debugging
                     // await fs.unlink(filePath).catch(err => logger.warn(`Failed to delete temp file ${filePath}: ${err.message}`));

                } catch (error: any) {
                    logger.error(`Error processing or deleting temp file ${filePath}: ${error.message}`);
                     try { await fs.unlink(filePath); } catch { /* ignore cleanup error */ }
                }
            }

             // --- REMOVED TS/JS File Node Generation Logic ---
             // --- REMOVED Directory Node Generation Logic ---

        } catch (error: any) {
            logger.error(`Error reading temp directory ${tempDir}: ${error.message}`);
        }

        // Add results from in-memory TS parsing
        logger.info(`Adding results from ${this.tsResults.size} parsed TS/JS files...`);
        for (const [filePath, result] of this.tsResults.entries()) {
            // Deduplicate nodes within this specific TS file result first
            const fileNodeMap = new Map<string, AstNode>();
            let intraFileDuplicates = 0;
            for (const node of result.nodes) {
                if (fileNodeMap.has(node.entityId)) {
                    intraFileDuplicates++;
                }
                fileNodeMap.set(node.entityId, node);
            }
            if (intraFileDuplicates > 0) {
                logger.warn(`[collectResults-TS] Found ${intraFileDuplicates} intra-file duplicate nodes in ${filePath}.`);
            }

            // Add unique nodes from this file to the main map
            for (const [entityId, node] of fileNodeMap.entries()) {
                if (nodeMap.has(entityId)) {
                     logger.warn(`[collectResults-TS] Overwriting node with duplicate entityId: ${entityId} (Kind: ${node.kind}, File: ${node.filePath})`);
                }
                nodeMap.set(entityId, node);
            }

            // Add relationships from this file to the main map
            for (const rel of result.relationships) {
                 if (relationshipMap.has(rel.entityId)) {
                     logger.warn(`[collectResults-TS] Overwriting relationship with duplicate entityId: ${rel.entityId} (Type: ${rel.type})`);
                 }
                 relationshipMap.set(rel.entityId, rel);
            }
        }
        this.tsResults.clear(); // Clear memory after collection

        const allNodes = Array.from(nodeMap.values());
        let allRelationships = Array.from(relationshipMap.values());

        // Perform JSP-Spring-WebFlow integration
        logger.info('Starting JSP-Spring-WebFlow integration...');
        try {
            const integrationContext = this.buildIntegrationContext(allNodes);
            const integrationRelationships = await this.jspSpringIntegrator.integrateAll(integrationContext);
            
            // Add integration relationships to the main collection
            for (const rel of integrationRelationships) {
                if (!relationshipMap.has(rel.entityId)) {
                    relationshipMap.set(rel.entityId, rel);
                    allRelationships.push(rel);
                }
            }
            
            logger.info(`Integration completed. Added ${integrationRelationships.length} cross-layer relationships.`);
        } catch (error: any) {
            logger.error(`Integration failed: ${error.message}`);
        }

        logger.info(`Collected ${allNodes.length} unique nodes and ${allRelationships.length} unique relationships from all sources.`);
        return { allNodes, allRelationships };
    }

    /**
     * Provides access to the ts-morph Project instance.
     * Useful for Pass 2 relationship resolution.
     */
    getTsProject(): Project {
        return this.tsProject;
    }

    /**
     * Returns the current analysis context.
     * Used by AnalyzerService to create Repository node and BELONGS_TO relationships.
     */
    getAnalysisContext(): AnalysisContext | undefined {
        return this.analysisContext;
    }

    /**
     * Parses all TypeScript/JavaScript SourceFile objects currently in the ts-morph project.
     * Only processes files whose paths are included in the targetFiles set.
     * @param targetFiles - A Set containing the normalized absolute paths of the files to be parsed.
     */
    private async _parseTsProjectFiles(targetFiles: Set<string>): Promise<void> {
        logger.info(`Starting TS/JS parsing. Project has ${this.tsProject.getSourceFiles().length} files. Filtering for ${targetFiles.size} target files.`);
        const now = new Date().toISOString();
        const instanceCounter = { count: 0 }; // Simple counter for instance IDs per run

        for (const sourceFile of this.tsProject.getSourceFiles()) {
            const filePath = sourceFile.getFilePath().replace(/\\/g, '/'); // Normalize path
            logger.debug(`Parsing TS/JS file: ${filePath}`);

            // Only process files that were part of the initial target scan for this run
            if (!targetFiles.has(filePath)) {
                // logger.trace(`Skipping non-target TS/JS file: ${filePath}`); // Optional: trace logging
                continue;
            }

            // 1. Create FileNode (include repositoryId for multi-repository support)
            const repositoryId = this.analysisContext?.repositoryId;
            const fileEntityId = generateEntityId('file', filePath, repositoryId);
            const fileNode: FileNode = { // Explicitly type as FileNode
                id: generateInstanceId(instanceCounter, 'file', path.basename(filePath)),
                entityId: fileEntityId,
                kind: 'File',
                name: path.basename(filePath),
                filePath: filePath,
                language: sourceFile.getLanguageVariant() === ts.LanguageVariant.JSX ? 'TSX' : 'TypeScript', // Basic language detection
                startLine: 1,
                endLine: sourceFile.getEndLineNumber(),
                startColumn: 0,
                endColumn: 0,
                loc: sourceFile.getEndLineNumber(),
                createdAt: now,
            };

            // 2. Prepare result and context for this file
            const result: SingleFileParseResult = {
                filePath: filePath,
                nodes: [fileNode], // Start with the file node
                relationships: [],
            };

            const addNode = (node: AstNode) => { result.nodes.push(node); };
            const addRelationship = (rel: RelationshipInfo) => { result.relationships.push(rel); };

            const context = { // Create ParserContext
                filePath: filePath,
                sourceFile: sourceFile,
                fileNode: fileNode, // Pass the created FileNode
                result: result,     // Pass the result object
                addNode: addNode,
                addRelationship: addRelationship,
                generateId: (prefix: string, identifier: string, options?: { line?: number; column?: number }) =>
                    generateInstanceId(instanceCounter, prefix, identifier, options),
                // Wrap generateEntityId to always include repositoryId for multi-repository support
                generateEntityId: (kind: string, qualifiedName: string) =>
                    generateEntityId(kind, qualifiedName, repositoryId),
                logger: createContextLogger(`Parser-${path.basename(filePath)}`), // File-specific logger context
                resolveImportPath: (source: string, imp: string) => { /* TODO: Implement proper import resolution */ return imp; },
                now: now,
            };

            try {
                // 3. Call individual parsers
                parseImports(context); // Add call to import parser
                parseFunctions(context);
                parseClasses(context);
                parseVariables(context);
                parseInterfaces(context);
                parseTypeAliases(context);
                // Check language from the fileNode within the context
                if (context.fileNode.language === 'TSX') { // Only parse JSX if applicable
                   parseJsx(context);
                }
                // Call other parsers (e.g., parseExports)

                // Store the result for this file
                this.tsResults.set(filePath, result);
                logger.debug(`Finished parsing TS/JS file: ${filePath}. Nodes: ${result.nodes.length}, Rels: ${result.relationships.length}`);

            } catch (error: any) {
                logger.error(`Error parsing TS/JS file ${filePath}: ${error.message}`, { stack: error.stack?.substring(0, 300) });
            }
        }
        logger.info(`Finished parsing ${targetFiles.size} target TS/JS files.`);
    }
}

// Helper function to ensure ts-morph compiler options are compatible
function ensureTsConfig(project: Project): void {
    const currentSettings = project.compilerOptions.get();
    if (!currentSettings.jsx) {
        project.compilerOptions.set({ jsx: ts.JsxEmit.React });
        logger.info('Set default JSX compiler option for ts-morph project.');
    }
}