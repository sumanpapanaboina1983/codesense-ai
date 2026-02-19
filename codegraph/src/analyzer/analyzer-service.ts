// src/analyzer/analyzer-service.ts
import path from 'path';
import { FileScanner, FileInfo, ModuleAwareFileInfo } from '../scanner/file-scanner.js';
import { Parser } from './parser.js';
import { RelationshipResolver } from './relationship-resolver.js';
import { StorageManager } from './storage-manager.js';
import {
    IncrementalIndexManager,
    IndexStateData,
    IncrementalIndexResult,
} from './incremental-index-manager.js';
import {
    AstNode,
    RelationshipInfo,
    AnalysisContext,
    RepositoryNode,
    JavaModuleNode,
    GradleDependencyNode,
    MultiModuleProjectStructure,
    ModuleInfo,
} from './types.js';
import { generateEntityId, generateInstanceId } from './parser-utils.js';
import { createContextLogger } from '../utils/logger.js';
import config from '../config/index.js';
import { Project } from 'ts-morph';
import { Neo4jClient } from '../database/neo4j-client.js';
import { Neo4jError } from '../utils/errors.js';
import { GradleParser, isGradleProject, isMavenProject, detectBuildSystem } from './parsers/gradle-parser.js';
import { getCurrentCommitSha, isGitRepository } from '../utils/git-change-detector.js';
import type { CallbackClient } from '../api/callback-client.js';
import { GraphAlgorithms } from './graph-algorithms.js';
// Removed setTimeout import

const logger = createContextLogger('AnalyzerService');

/**
 * Checkpoint data for resuming analysis from a specific point.
 */
export interface ResumeCheckpoint {
    /** Phase to resume from */
    phase: string;
    /** Number of files already processed */
    processedFiles: number;
    /** Total files discovered */
    totalFiles: number;
    /** Last file that was processed */
    lastProcessedFile?: string;
    /** Nodes created before pause */
    nodesCreated: number;
    /** Relationships created before pause */
    relationshipsCreated: number;
    /** Additional checkpoint data (e.g., list of processed file paths) */
    checkpointData?: {
        processedFilePaths?: string[];
        [key: string]: any;
    };
}

/**
 * Result returned from analyze() for stats reporting.
 */
export interface AnalysisResult {
    filesScanned: number;
    nodesCreated: number;
    relationshipsCreated: number;
    /** Whether this was an incremental update vs full reindex */
    wasIncremental: boolean;
    /** Number of files that were skipped (unchanged) */
    filesSkipped: number;
    /** Number of deleted files cleaned up */
    filesDeleted: number;
    /** Reason for the indexing type */
    indexingReason?: string;
}

/**
 * Options for controlling incremental indexing behavior.
 */
export interface IncrementalIndexOptions {
    /** Force a complete re-index, ignoring previous state */
    forceFullReindex?: boolean;
    /** Enable/disable incremental indexing (default: true) */
    incrementalMode?: boolean;
}

/**
 * Orchestrates the code analysis process: scanning, parsing, resolving, and storing.
 */
export class AnalyzerService {
    private parser: Parser;
    private storageManager: StorageManager;
    private neo4jClient: Neo4jClient;
    private incrementalIndexManager: IncrementalIndexManager;
    private graphAlgorithms: GraphAlgorithms;

    constructor() {
        this.parser = new Parser();
        // Instantiate Neo4jClient without overrides to use config defaults
        this.neo4jClient = new Neo4jClient();
        // Pass the client instance to StorageManager
        this.storageManager = new StorageManager(this.neo4jClient);
        // Initialize incremental index manager
        this.incrementalIndexManager = new IncrementalIndexManager(this.neo4jClient);
        // Initialize graph algorithms for PageRank computation
        this.graphAlgorithms = new GraphAlgorithms(this.neo4jClient);
        logger.info('AnalyzerService initialized.');
    }

    /**
     * Runs the full analysis pipeline for a given directory.
     * Supports incremental indexing when context is provided.
     * @param directory - The root directory to analyze.
     * @param context - Optional analysis context for multi-repository support.
     * @param callback - Optional callback client for progress reporting.
     * @param resumeFrom - Optional checkpoint data for resuming a paused/failed analysis.
     * @param incrementalOptions - Options for controlling incremental indexing.
     */
    async analyze(
        directory: string,
        context?: AnalysisContext,
        callback?: CallbackClient,
        resumeFrom?: ResumeCheckpoint,
        incrementalOptions?: IncrementalIndexOptions
    ): Promise<AnalysisResult> {
        const repoInfo = context ? ` (Repository: ${context.repositoryName}, ID: ${context.repositoryId})` : '';
        const isResume = !!resumeFrom;

        if (isResume) {
            logger.info(`RESUMING analysis for directory: ${directory}${repoInfo}`);
            logger.info(`  Resume from phase: ${resumeFrom.phase}`);
            logger.info(`  Previously processed: ${resumeFrom.processedFiles}/${resumeFrom.totalFiles} files`);
            logger.info(`  Previous nodes created: ${resumeFrom.nodesCreated}`);
            logger.info(`  Previous relationships: ${resumeFrom.relationshipsCreated}`);
        } else {
            logger.info(`Starting analysis for directory: ${directory}${repoInfo}`);
        }

        const absoluteDirectory = path.resolve(directory);
        let scanner: FileScanner;
        let filesScanned = 0;

        // Get set of already-processed files for resume
        const processedFilePaths = new Set<string>(
            resumeFrom?.checkpointData?.processedFilePaths || []
        );
        const skipProcessedFiles = isResume && processedFilePaths.size > 0;
        if (skipProcessedFiles) {
            logger.info(`Will skip ${processedFilePaths.size} already-processed files`);
        }

        try {
            // Instantiate FileScanner here with directory and config
            // Use config.supportedExtensions and config.ignorePatterns directly
            scanner = new FileScanner(absoluteDirectory, config.supportedExtensions, config.ignorePatterns);

            // 0. Detect and parse multi-module project structure
            let projectStructure: MultiModuleProjectStructure | null = null;
            const buildSystem = detectBuildSystem(absoluteDirectory);

            if (buildSystem === 'gradle' && context) {
                logger.info('Detected Gradle project, parsing module structure...');
                const gradleParser = new GradleParser(absoluteDirectory, context.repositoryId);
                projectStructure = await gradleParser.parseProject();

                if (projectStructure) {
                    logger.info(`Found ${projectStructure.modules.length} modules in Gradle project`);
                    for (const module of projectStructure.modules) {
                        logger.debug(`  - Module: ${module.name} (${module.moduleType}) at ${module.path}`);
                    }
                }
            } else if (buildSystem === 'maven' && context) {
                logger.info('Detected Maven project (Maven parsing not yet implemented)');
                // TODO: Implement Maven parser
            }

            // 1. Scan Files (with hashes for incremental indexing)
            logger.info('Scanning files...');
            if (callback) {
                await callback.updateProgress({
                    phase: 'indexing_files',
                    progress_pct: 15,
                    total_files: resumeFrom?.totalFiles || 0,
                    processed_files: resumeFrom?.processedFiles || 0,
                    nodes_created: resumeFrom?.nodesCreated || 0,
                    relationships_created: resumeFrom?.relationshipsCreated || 0,
                    message: isResume ? 'Resuming: Scanning files...' : 'Scanning files...',
                });
                callback.addLog({
                    level: 'info',
                    phase: 'indexing_files',
                    message: isResume ? 'Resuming: Scanning files...' : 'Scanning files...'
                });
            }

            // Determine if we should use incremental indexing
            const useIncremental = context && (incrementalOptions?.incrementalMode !== false);
            const forceFullReindex = incrementalOptions?.forceFullReindex === true;

            // Scan files with hashes for incremental comparison
            let allFiles: FileInfo[];
            if (useIncremental && !forceFullReindex) {
                logger.info('Scanning files with hashes for incremental indexing...');
                allFiles = await scanner.scanWithHashes();
            } else {
                allFiles = await scanner.scan();
            }
            const totalFilesFound = allFiles.length;

            // Incremental indexing: determine which files need processing
            let incrementalResult: IncrementalIndexResult | null = null;
            let files: FileInfo[] = allFiles;
            let deletedFiles: string[] = [];
            let unchangedFiles: string[] = [];

            if (useIncremental && context) {
                logger.info('Determining files to process (incremental mode)...');
                await this.neo4jClient.initializeDriver('AnalyzerService-Incremental');

                incrementalResult = await this.incrementalIndexManager.determineFilesToProcess(
                    absoluteDirectory,
                    context.repositoryId,
                    allFiles,
                    forceFullReindex
                );

                files = incrementalResult.changedFiles;
                deletedFiles = incrementalResult.deletedFiles;
                unchangedFiles = incrementalResult.unchangedFiles;

                logger.info(`Incremental analysis: ${files.length} changed, ${unchangedFiles.length} unchanged, ${deletedFiles.length} deleted`);
                logger.info(`Reason: ${incrementalResult.reason}`);

                if (callback) {
                    callback.addLog({
                        level: 'info',
                        phase: 'indexing_files',
                        message: incrementalResult.isFullReindex
                            ? `Full reindex: ${incrementalResult.reason}`
                            : `Incremental: ${files.length} changed, ${unchangedFiles.length} unchanged, ${deletedFiles.length} deleted`
                    });
                }

                // Clean up deleted files FIRST before processing new/changed files
                if (deletedFiles.length > 0) {
                    logger.info(`Cleaning up ${deletedFiles.length} deleted files...`);
                    if (callback) {
                        callback.addLog({
                            level: 'info',
                            phase: 'cleanup',
                            message: `Cleaning up ${deletedFiles.length} deleted files...`
                        });
                    }
                    const cleanupResult = await this.incrementalIndexManager.cleanupDeletedFiles(
                        context.repositoryId,
                        deletedFiles
                    );
                    logger.info(`Cleanup complete: ${cleanupResult.nodesDeleted} nodes removed`);
                }
            }

            // Filter out already-processed files when resuming
            if (skipProcessedFiles) {
                const originalCount = files.length;
                files = files.filter(f => !processedFilePaths.has(f.path));
                const skippedCount = originalCount - files.length;
                logger.info(`Resume: Skipping ${skippedCount} already-processed files, ${files.length} remaining`);
                if (callback) {
                    callback.addLog({
                        level: 'info',
                        phase: 'indexing_files',
                        message: `Resume: Skipping ${skippedCount} already-processed files, ${files.length} remaining`
                    });
                }
            }

            filesScanned = totalFilesFound;
            if (files.length === 0) {
                if (isResume) {
                    logger.info('All files already processed. Analysis complete.');
                    return {
                        filesScanned: totalFilesFound,
                        nodesCreated: resumeFrom?.nodesCreated || 0,
                        relationshipsCreated: resumeFrom?.relationshipsCreated || 0,
                        wasIncremental: true,
                        filesSkipped: unchangedFiles.length,
                        filesDeleted: deletedFiles.length,
                        indexingReason: 'Resume - all files processed'
                    };
                }
                if (incrementalResult && !incrementalResult.isFullReindex) {
                    logger.info('No changed files to process. Index is up to date.');

                    // Save index state even when no changes (update timestamp)
                    if (context) {
                        const commitSha = await isGitRepository(absoluteDirectory)
                            ? await getCurrentCommitSha(absoluteDirectory)
                            : null;
                        const indexState = this.incrementalIndexManager.createIndexState(
                            context.repositoryId,
                            allFiles,
                            commitSha
                        );
                        await this.incrementalIndexManager.saveIndexState(indexState);
                    }

                    return {
                        filesScanned: totalFilesFound,
                        nodesCreated: 0,
                        relationshipsCreated: 0,
                        wasIncremental: true,
                        filesSkipped: unchangedFiles.length,
                        filesDeleted: deletedFiles.length,
                        indexingReason: incrementalResult.reason
                    };
                }
                logger.warn('No files found to analyze.');
                return { filesScanned: 0, nodesCreated: 0, relationshipsCreated: 0, wasIncremental: false, filesSkipped: 0, filesDeleted: 0 };
            }
            logger.info(`Found ${totalFilesFound} files total, ${files.length} to process.`);
            if (callback) {
                callback.addLog({
                    level: 'info',
                    phase: 'indexing_files',
                    message: isResume
                        ? `Found ${totalFilesFound} files, ${files.length} remaining to process`
                        : `Found ${files.length} files to analyze`
                });
            }

            // 1.5 Enrich files with module information
            let moduleAwareFiles: ModuleAwareFileInfo[] = [];
            if (projectStructure) {
                moduleAwareFiles = scanner.enrichWithModuleInfo(files, projectStructure);
                const filesByModule = scanner.groupFilesByModule(moduleAwareFiles);
                logger.info(`Files grouped by module:`);
                for (const [moduleName, moduleFiles] of filesByModule) {
                    logger.debug(`  - ${moduleName || 'root'}: ${moduleFiles.length} files`);
                }
            }

            // 2. Parse Files (Pass 1) - pass context for multi-repository support
            logger.info('Parsing files (Pass 1)...');
            if (callback) {
                await callback.updateProgress({
                    phase: 'parsing_code',
                    progress_pct: 30,
                    total_files: filesScanned,
                    processed_files: 0,
                    nodes_created: 0,
                    relationships_created: 0,
                    message: 'Parsing files (Pass 1)...',
                });
                callback.addLog({ level: 'info', phase: 'parsing_code', message: `Parsing ${filesScanned} files...` });
            }
            await this.parser.parseFiles(files, context);

            // 3. Collect Pass 1 Results
            logger.info('Collecting Pass 1 results...');
            const { allNodes: pass1Nodes, allRelationships: pass1Relationships } = await this.parser.collectResults();
            logger.info(`Collected ${pass1Nodes.length} nodes and ${pass1Relationships.length} relationships from Pass 1.`);
            if (callback) {
                await callback.updateProgress({
                    phase: 'parsing_code',
                    progress_pct: 50,
                    total_files: filesScanned,
                    processed_files: filesScanned,
                    nodes_created: pass1Nodes.length,
                    relationships_created: pass1Relationships.length,
                    message: `Collected ${pass1Nodes.length} nodes and ${pass1Relationships.length} relationships`,
                });
                callback.addLog({ level: 'info', phase: 'parsing_code', message: `Pass 1 complete: ${pass1Nodes.length} nodes, ${pass1Relationships.length} relationships` });
            }

            if (pass1Nodes.length === 0) {
                logger.warn('No nodes were generated during Pass 1. Aborting further analysis.');
                return {
                    filesScanned,
                    nodesCreated: 0,
                    relationshipsCreated: 0,
                    wasIncremental: incrementalResult ? !incrementalResult.isFullReindex : false,
                    filesSkipped: unchangedFiles.length,
                    filesDeleted: deletedFiles.length,
                    indexingReason: 'No nodes generated in Pass 1'
                };
            }

            // 3.5 Create Repository node and BELONGS_TO relationships for multi-repository support
            if (context) {
                const { repositoryNode, belongsToRelationships } = this.createRepositoryStructure(
                    context,
                    pass1Nodes,
                    files.length
                );
                pass1Nodes.unshift(repositoryNode); // Add Repository node at the beginning
                pass1Relationships.push(...belongsToRelationships);
                logger.info(`Created Repository node and ${belongsToRelationships.length} BELONGS_TO relationships.`);

                // 3.6 Create module nodes and relationships
                if (projectStructure && projectStructure.modules.length > 0) {
                    const { moduleNodes, moduleRelationships } = this.createModuleStructure(
                        context,
                        projectStructure,
                        repositoryNode,
                        pass1Nodes,
                        moduleAwareFiles
                    );
                    pass1Nodes.push(...moduleNodes);
                    pass1Relationships.push(...moduleRelationships);
                    logger.info(`Created ${moduleNodes.length} module nodes and ${moduleRelationships.length} module relationships.`);

                    // Log module details for debugging
                    for (const moduleNode of moduleNodes) {
                        logger.debug(`Module node created: ${moduleNode.name}, entityId: ${moduleNode.entityId}, kind: ${moduleNode.kind}`);
                    }
                    for (const rel of moduleRelationships.filter(r => r.type === 'HAS_MODULE')) {
                        logger.debug(`HAS_MODULE relationship: source=${rel.sourceId}, target=${rel.targetId}`);
                    }
                } else {
                    logger.warn(`No modules created: projectStructure=${!!projectStructure}, modules.length=${projectStructure?.modules?.length ?? 0}`);
                }
            }

            // 4. Resolve Relationships (Pass 2)
            logger.info('Resolving relationships (Pass 2)...');
            const tsProject: Project = this.parser.getTsProject();
            const resolver = new RelationshipResolver(pass1Nodes, pass1Relationships);
            const pass2Relationships = await resolver.resolveRelationships(tsProject);
            logger.info(`Resolved ${pass2Relationships.length} relationships in Pass 2.`);

            const finalNodes = pass1Nodes;
            const finalRelationships = [...pass1Relationships, ...pass2Relationships];
            const uniqueRelationships = Array.from(new Map(finalRelationships.map(r => [r.entityId, r])).values());
            logger.info(`Total unique relationships after combining passes: ${uniqueRelationships.length}`);

            // 5. Store Results
            logger.info('Storing analysis results...');
            if (callback) {
                await callback.updateProgress({
                    phase: 'building_graph',
                    progress_pct: 70,
                    total_files: filesScanned,
                    processed_files: filesScanned,
                    nodes_created: finalNodes.length,
                    relationships_created: uniqueRelationships.length,
                    message: `Storing ${finalNodes.length} nodes to database...`,
                });
                callback.addLog({ level: 'info', phase: 'building_graph', message: `Storing ${finalNodes.length} nodes to Neo4j...` });
            }
            // Ensure driver is initialized before storing
            await this.neo4jClient.initializeDriver('AnalyzerService-Store');

            // --- Database clearing is now handled by beforeEach in tests ---

            await this.storageManager.saveNodesBatch(finalNodes);
            if (callback) {
                callback.addLog({ level: 'info', phase: 'building_graph', message: `Saved ${finalNodes.length} nodes successfully` });
            }

            // Group relationships by type before saving
            const relationshipsByType: { [type: string]: RelationshipInfo[] } = {};
            for (const rel of uniqueRelationships) {
                if (!relationshipsByType[rel.type]) {
                    relationshipsByType[rel.type] = [];
                }
                // Push directly, using non-null assertion to satisfy compiler
                relationshipsByType[rel.type]!.push(rel);
            }

            // Save relationships batch by type
            if (callback) {
                await callback.updateProgress({
                    phase: 'building_graph',
                    progress_pct: 85,
                    total_files: filesScanned,
                    processed_files: filesScanned,
                    nodes_created: finalNodes.length,
                    relationships_created: uniqueRelationships.length,
                    message: `Storing ${uniqueRelationships.length} relationships...`,
                });
                callback.addLog({ level: 'info', phase: 'building_graph', message: `Storing ${uniqueRelationships.length} relationships...` });
            }
            for (const type in relationshipsByType) {
                 const batch = relationshipsByType[type];
                 // --- TEMPORARY DEBUG LOG ---
                 logger.debug(`[AnalyzerService] Processing relationship type: ${type}, Batch size: ${batch?.length ?? 0}`);
                 if (type === 'HAS_METHOD') {
                     logger.debug(`[AnalyzerService] Found HAS_METHOD batch. Calling saveRelationshipsBatch...`);
                 }
                 // --- END TEMPORARY DEBUG LOG ---
                 // Ensure batch is not undefined before passing (still good practice)
                 if (batch) {
                    await this.storageManager.saveRelationshipsBatch(type, batch);
                 }
            }

            logger.info('Analysis results stored successfully.');

            // 5.5 Compute PageRank scores for relevance-based retrieval
            if (context) {
                logger.info('Computing PageRank scores...');
                if (callback) {
                    await callback.updateProgress({
                        phase: 'computing_relevance',
                        progress_pct: 92,
                        total_files: filesScanned,
                        processed_files: filesScanned,
                        nodes_created: finalNodes.length,
                        relationships_created: uniqueRelationships.length,
                        message: 'Computing relevance scores (PageRank)...',
                    });
                    callback.addLog({ level: 'info', phase: 'computing_relevance', message: 'Computing PageRank scores for components...' });
                }

                try {
                    const pageRankResult = await this.graphAlgorithms.computePageRank(context.repositoryId);
                    logger.info(`PageRank computed: ${pageRankResult.nodesUpdated} nodes updated in ${pageRankResult.executionTimeMs}ms`);

                    if (callback && pageRankResult.topNodes.length > 0) {
                        const topNames = pageRankResult.topNodes.slice(0, 5).map(n => n.name).join(', ');
                        callback.addLog({
                            level: 'info',
                            phase: 'computing_relevance',
                            message: `PageRank computed. Top components: ${topNames}`
                        });
                    }
                } catch (error: any) {
                    logger.warn(`PageRank computation failed (non-fatal): ${error.message}`);
                    if (callback) {
                        callback.addLog({
                            level: 'warning',
                            phase: 'computing_relevance',
                            message: `PageRank computation skipped: ${error.message}`
                        });
                    }
                }
            }

            // 6. Save Index State for incremental indexing
            if (context && useIncremental) {
                logger.info('Saving index state for future incremental indexing...');
                try {
                    const commitSha = await isGitRepository(absoluteDirectory)
                        ? await getCurrentCommitSha(absoluteDirectory)
                        : null;

                    // Create or update index state
                    let indexState: IndexStateData;
                    const existingState = await this.incrementalIndexManager.loadIndexState(context.repositoryId);

                    if (existingState && !incrementalResult?.isFullReindex) {
                        // Update existing state with changes
                        indexState = this.incrementalIndexManager.updateIndexState(
                            existingState,
                            files, // changed files
                            deletedFiles,
                            commitSha
                        );
                    } else {
                        // Create new state with all files
                        indexState = this.incrementalIndexManager.createIndexState(
                            context.repositoryId,
                            allFiles,
                            commitSha
                        );
                    }

                    await this.incrementalIndexManager.saveIndexState(indexState);
                    logger.info(`Index state saved: ${indexState.totalFilesIndexed} files tracked`);

                    if (callback) {
                        callback.addLog({
                            level: 'info',
                            phase: 'completed',
                            message: `Index state saved: ${indexState.totalFilesIndexed} files tracked`
                        });
                    }
                } catch (error: any) {
                    // Log but don't fail the analysis if index state saving fails
                    logger.warn(`Failed to save index state: ${error.message}`);
                }
            }

            if (callback) {
                await callback.updateProgress({
                    phase: 'completed',
                    progress_pct: 100,
                    total_files: filesScanned,
                    processed_files: filesScanned,
                    nodes_created: finalNodes.length,
                    relationships_created: uniqueRelationships.length,
                    message: 'Analysis completed successfully',
                });
                callback.addLog({ level: 'info', phase: 'completed', message: 'Analysis completed successfully' });
            }

            return {
                filesScanned,
                nodesCreated: finalNodes.length,
                relationshipsCreated: uniqueRelationships.length,
                wasIncremental: incrementalResult ? !incrementalResult.isFullReindex : false,
                filesSkipped: unchangedFiles.length,
                filesDeleted: deletedFiles.length,
                indexingReason: incrementalResult?.reason,
            };

        } catch (error: any) {
            logger.error(`Analysis failed: ${error.message}`, { stack: error.stack });
            throw error; // Re-throw the error for higher-level handling
        } finally {
            // 6. Cleanup & Disconnect
            logger.info('Closing Neo4j driver...');
            await this.neo4jClient.closeDriver('AnalyzerService-Cleanup');
            logger.info('Analysis complete.');
        }
    }

    /**
     * Creates a Repository node and BELONGS_TO relationships for multi-repository support.
     * @param context - The analysis context containing repository metadata.
     * @param nodes - All parsed nodes from Pass 1.
     * @param fileCount - Total number of files in the repository.
     * @returns The Repository node and BELONGS_TO relationships.
     */
    private createRepositoryStructure(
        context: AnalysisContext,
        nodes: AstNode[],
        fileCount: number
    ): { repositoryNode: RepositoryNode; belongsToRelationships: RelationshipInfo[] } {
        const now = new Date().toISOString();
        const instanceCounter = { count: 0 };

        // Create Repository node
        const repositoryEntityId = generateEntityId('repository', context.repositoryId);
        const repositoryNode: RepositoryNode = {
            id: generateInstanceId(instanceCounter, 'repository', context.repositoryId),
            entityId: repositoryEntityId,
            kind: 'Repository',
            name: context.repositoryName,
            filePath: context.rootDirectory, // Use rootDirectory as filePath for consistency
            language: 'Repository', // Special marker for Repository nodes
            startLine: 0,
            endLine: 0,
            startColumn: 0,
            endColumn: 0,
            createdAt: now,
            properties: {
                repositoryId: context.repositoryId,
                name: context.repositoryName,
                url: context.repositoryUrl,
                rootPath: context.rootDirectory,
                analyzedAt: now,
                fileCount: fileCount,
            },
        };

        // Create BELONGS_TO relationships from File nodes to Repository node
        const belongsToRelationships: RelationshipInfo[] = [];
        const fileNodes = nodes.filter(node => node.kind === 'File');

        for (const fileNode of fileNodes) {
            const relationshipEntityId = generateEntityId(
                'belongs_to',
                `${fileNode.entityId}:${repositoryEntityId}`
            );
            const relationship: RelationshipInfo = {
                id: generateInstanceId(instanceCounter, 'belongs_to', `${fileNode.name}:${context.repositoryName}`),
                entityId: relationshipEntityId,
                type: 'BELONGS_TO',
                sourceId: fileNode.entityId,
                targetId: repositoryEntityId,
                createdAt: now,
            };
            belongsToRelationships.push(relationship);
        }

        logger.debug(`Created Repository node: ${repositoryEntityId} with ${belongsToRelationships.length} BELONGS_TO relationships.`);
        return { repositoryNode, belongsToRelationships };
    }

    /**
     * Creates JavaModule nodes and related relationships for multi-module projects.
     * @param context - The analysis context
     * @param projectStructure - The parsed multi-module project structure
     * @param repositoryNode - The Repository node
     * @param allNodes - All parsed nodes from Pass 1
     * @param moduleAwareFiles - Files enriched with module information
     * @returns Module nodes and relationships
     */
    private createModuleStructure(
        context: AnalysisContext,
        projectStructure: MultiModuleProjectStructure,
        repositoryNode: RepositoryNode,
        allNodes: AstNode[],
        moduleAwareFiles: ModuleAwareFileInfo[]
    ): { moduleNodes: AstNode[]; moduleRelationships: RelationshipInfo[] } {
        const now = new Date().toISOString();
        const instanceCounter = { count: 0 };

        const moduleNodes: AstNode[] = [];
        const moduleRelationships: RelationshipInfo[] = [];

        // Map to track module entityIds for dependency relationships
        const moduleEntityIdMap = new Map<string, string>();

        // Create JavaModule nodes
        for (const module of projectStructure.modules) {
            const moduleEntityId = generateEntityId('javamodule', `${context.repositoryId}:${module.name}`);
            moduleEntityIdMap.set(module.name, moduleEntityId);

            const moduleNode: JavaModuleNode = {
                id: generateInstanceId(instanceCounter, 'javamodule', module.name),
                entityId: moduleEntityId,
                kind: 'JavaModule',
                name: module.name,
                filePath: module.absolutePath,
                language: 'Java',
                startLine: 0,
                endLine: 0,
                startColumn: 0,
                endColumn: 0,
                createdAt: now,
                properties: {
                    moduleName: module.name,
                    modulePath: module.path,
                    buildFilePath: module.buildFilePath,
                    buildSystem: 'gradle',
                    group: module.buildResult?.group,
                    artifact: module.name,
                    version: module.buildResult?.version,
                    plugins: module.buildResult?.plugins.map(p => p.id) || [],
                    sourceDirs: module.buildResult?.sourceSets.flatMap(ss => ss.srcDirs) || ['src/main/java'],
                    testDirs: ['src/test/java'],
                    resourceDirs: module.buildResult?.sourceSets.flatMap(ss => ss.resourceDirs) || ['src/main/resources'],
                    moduleType: module.moduleType,
                    sourceCompatibility: module.buildResult?.sourceCompatibility,
                    targetCompatibility: module.buildResult?.targetCompatibility,
                },
            };
            moduleNodes.push(moduleNode);

            // Create HAS_MODULE relationship from Repository to Module
            const hasModuleRelationship: RelationshipInfo = {
                id: generateInstanceId(instanceCounter, 'has_module', `${context.repositoryName}:${module.name}`),
                entityId: generateEntityId('has_module', `${repositoryNode.entityId}:${moduleEntityId}`),
                type: 'HAS_MODULE',
                sourceId: repositoryNode.entityId,
                targetId: moduleEntityId,
                createdAt: now,
            };
            moduleRelationships.push(hasModuleRelationship);
        }

        // Create DEPENDS_ON_MODULE relationships between modules
        for (const module of projectStructure.modules) {
            const sourceModuleEntityId = moduleEntityIdMap.get(module.name);
            if (!sourceModuleEntityId) continue;

            for (const depModuleName of module.moduleDependencies) {
                const targetModuleEntityId = moduleEntityIdMap.get(depModuleName);
                if (!targetModuleEntityId) {
                    logger.warn(`Dependency module not found: ${depModuleName} (referenced by ${module.name})`);
                    continue;
                }

                // Find the configuration for this dependency
                const depInfo = module.buildResult?.projectDependencies.find(
                    d => d.moduleName === depModuleName
                );

                const dependsOnRelationship: RelationshipInfo = {
                    id: generateInstanceId(instanceCounter, 'depends_on_module', `${module.name}:${depModuleName}`),
                    entityId: generateEntityId('depends_on_module', `${sourceModuleEntityId}:${targetModuleEntityId}`),
                    type: 'DEPENDS_ON_MODULE',
                    sourceId: sourceModuleEntityId,
                    targetId: targetModuleEntityId,
                    createdAt: now,
                    properties: {
                        configuration: depInfo?.configuration || 'implementation',
                        projectPath: depInfo?.projectPath,
                    },
                };
                moduleRelationships.push(dependsOnRelationship);
            }
        }

        // Create CONTAINS_FILE relationships from modules to files
        const fileNodes = allNodes.filter(node => node.kind === 'File');

        for (const fileInfo of moduleAwareFiles) {
            if (!fileInfo.moduleName) continue;

            const moduleEntityId = moduleEntityIdMap.get(fileInfo.moduleName);
            if (!moduleEntityId) continue;

            // Find the File node for this path
            const fileNode = fileNodes.find(node => node.filePath === fileInfo.path);
            if (!fileNode) continue;

            const containsFileRelationship: RelationshipInfo = {
                id: generateInstanceId(instanceCounter, 'contains_file', `${fileInfo.moduleName}:${fileInfo.name}`),
                entityId: generateEntityId('contains_file', `${moduleEntityId}:${fileNode.entityId}`),
                type: 'CONTAINS_FILE',
                sourceId: moduleEntityId,
                targetId: fileNode.entityId,
                createdAt: now,
                properties: {
                    sourceType: fileInfo.sourceType,
                    moduleRelativePath: fileInfo.moduleRelativePath,
                },
            };
            moduleRelationships.push(containsFileRelationship);
        }

        // Create DEFINED_IN_MODULE relationships for classes/interfaces
        const classNodes = allNodes.filter(node =>
            ['Class', 'Interface', 'JavaClass', 'JavaInterface', 'PythonClass'].includes(node.kind)
        );

        for (const classNode of classNodes) {
            // Find which module this class belongs to based on its file path
            const classFileInfo = moduleAwareFiles.find(f => f.path === classNode.filePath);
            if (!classFileInfo || !classFileInfo.moduleName) continue;

            const moduleEntityId = moduleEntityIdMap.get(classFileInfo.moduleName);
            if (!moduleEntityId) continue;

            const definedInModuleRelationship: RelationshipInfo = {
                id: generateInstanceId(instanceCounter, 'defined_in_module', `${classNode.name}:${classFileInfo.moduleName}`),
                entityId: generateEntityId('defined_in_module', `${classNode.entityId}:${moduleEntityId}`),
                type: 'DEFINED_IN_MODULE',
                sourceId: classNode.entityId,
                targetId: moduleEntityId,
                createdAt: now,
            };
            moduleRelationships.push(definedInModuleRelationship);
        }

        // Create GradleDependency nodes and HAS_DEPENDENCY relationships for external dependencies
        const createdDependencies = new Set<string>();

        for (const module of projectStructure.modules) {
            const moduleEntityId = moduleEntityIdMap.get(module.name);
            if (!moduleEntityId || !module.buildResult) continue;

            for (const dep of module.buildResult.dependencies) {
                // Create unique key for dependency
                const depKey = `${dep.group}:${dep.artifact}:${dep.version}`;

                // Create dependency node if not already created
                if (!createdDependencies.has(depKey)) {
                    const depEntityId = generateEntityId('gradledependency', depKey);
                    const depNode: GradleDependencyNode = {
                        id: generateInstanceId(instanceCounter, 'gradledependency', depKey),
                        entityId: depEntityId,
                        kind: 'GradleDependency',
                        name: `${dep.group}:${dep.artifact}`,
                        filePath: module.buildFilePath,
                        language: 'Gradle',
                        startLine: 0,
                        endLine: 0,
                        startColumn: 0,
                        endColumn: 0,
                        createdAt: now,
                        properties: {
                            group: dep.group,
                            artifact: dep.artifact,
                            version: dep.version,
                            configuration: dep.configuration,
                            isProjectDependency: false,
                            isPlatform: dep.isPlatform,
                            isVersionManaged: false,
                        },
                    };
                    moduleNodes.push(depNode);
                    createdDependencies.add(depKey);
                }

                // Create HAS_DEPENDENCY relationship
                const depEntityId = generateEntityId('gradledependency', depKey);
                const hasDependencyRelationship: RelationshipInfo = {
                    id: generateInstanceId(instanceCounter, 'has_dependency', `${module.name}:${depKey}`),
                    entityId: generateEntityId('has_dependency', `${moduleEntityId}:${depEntityId}`),
                    type: 'HAS_DEPENDENCY',
                    sourceId: moduleEntityId,
                    targetId: depEntityId,
                    createdAt: now,
                    properties: {
                        configuration: dep.configuration,
                    },
                };
                moduleRelationships.push(hasDependencyRelationship);
            }
        }

        logger.debug(`Created ${moduleNodes.length} module-related nodes and ${moduleRelationships.length} module relationships.`);
        return { moduleNodes, moduleRelationships };
    }
}