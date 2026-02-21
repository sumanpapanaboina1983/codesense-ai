// src/analyzer/analyzer-service.ts
import path from 'path';
import { FileScanner, FileInfo, ModuleAwareFileInfo } from '../scanner/file-scanner.js';
import { Parser } from './parser.js';
import { RelationshipResolver } from './relationship-resolver.js';
import { StorageManager, BatchCompleteCallback } from './storage-manager.js';
import {
    IncrementalIndexManager,
    IndexStateData,
    IncrementalIndexResult,
} from './incremental-index-manager.js';
import {
    ProcessingCheckpointManager,
    ProcessingCheckpoint,
    ProcessingPhase,
} from './processing-checkpoint-manager.js';
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
 *
 * Features:
 * - Robust crash recovery via ProcessingCheckpointManager
 * - Incremental indexing (only process changed files)
 * - Hash-based change detection for both git and non-git repos
 * - Batch-level progress tracking
 */
export class AnalyzerService {
    private parser: Parser;
    private storageManager: StorageManager;
    private neo4jClient: Neo4jClient;
    private incrementalIndexManager: IncrementalIndexManager;
    private checkpointManager: ProcessingCheckpointManager;
    private graphAlgorithms: GraphAlgorithms;

    constructor() {
        this.parser = new Parser();
        // Instantiate Neo4jClient without overrides to use config defaults
        this.neo4jClient = new Neo4jClient();
        // Pass the client instance to StorageManager
        this.storageManager = new StorageManager(this.neo4jClient);
        // Initialize incremental index manager
        this.incrementalIndexManager = new IncrementalIndexManager(this.neo4jClient);
        // Initialize checkpoint manager for crash recovery
        this.checkpointManager = new ProcessingCheckpointManager(this.neo4jClient);
        // Initialize graph algorithms for PageRank computation
        this.graphAlgorithms = new GraphAlgorithms(this.neo4jClient);
        logger.info('AnalyzerService initialized with checkpoint support.');
    }

    /**
     * Runs the full analysis pipeline for a given directory.
     * Supports incremental indexing and robust crash recovery via checkpointing.
     *
     * Features:
     * - Automatic crash recovery: Resumes from last successful batch
     * - Incremental indexing: Only processes changed files
     * - Hash-based verification: Works for both git and non-git repos
     * - Batch-level progress tracking: Updates checkpoint after each batch commit
     *
     * @param directory - The root directory to analyze.
     * @param context - Optional analysis context for multi-repository support.
     * @param callback - Optional callback client for progress reporting.
     * @param resumeFrom - Optional checkpoint data for resuming (legacy, prefer auto-resume).
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
        const absoluteDirectory = path.resolve(directory);
        let filesScanned = 0;
        let analysisId: string | null = null;
        let checkpoint: ProcessingCheckpoint | null = null;
        let isResuming = false;

        // Track files processed during this run for checkpoint
        const filesProcessedThisRun: string[] = [];
        let nodesCreatedThisRun = 0;
        let relationshipsCreatedThisRun = 0;

        try {
            // Initialize Neo4j connection first (needed for checkpoint operations)
            await this.neo4jClient.initializeDriver('AnalyzerService-Init');

            // === PHASE 0: Check for incomplete checkpoint (auto-resume) ===
            if (context) {
                const existingCheckpoint = await this.checkpointManager.loadIncompleteCheckpoint(context.repositoryId);

                if (existingCheckpoint && !incrementalOptions?.forceFullReindex) {
                    checkpoint = existingCheckpoint;
                    analysisId = checkpoint.analysisId;
                    isResuming = true;

                    logger.info(`=== RESUMING FROM CHECKPOINT ===`);
                    logger.info(`  Analysis ID: ${analysisId}`);
                    logger.info(`  Phase: ${checkpoint.phase}`);
                    logger.info(`  Files processed: ${checkpoint.filesProcessed.length}/${checkpoint.totalFilesDiscovered}`);
                    logger.info(`  Nodes created: ${checkpoint.nodesCreated}`);
                    logger.info(`  Relationships created: ${checkpoint.relationshipsCreated}`);

                    if (callback) {
                        callback.addLog({
                            level: 'info',
                            phase: 'resuming',
                            message: `Resuming from checkpoint: ${checkpoint.filesProcessed.length} files already processed`
                        });
                    }
                }
            }

            // Also handle legacy resumeFrom parameter
            const legacyResumeFiles = new Set<string>(resumeFrom?.checkpointData?.processedFilePaths || []);
            if (legacyResumeFiles.size > 0 && !isResuming) {
                isResuming = true;
                logger.info(`Legacy resume: ${legacyResumeFiles.size} files already processed`);
            }

            logger.info(`${isResuming ? 'RESUMING' : 'Starting'} analysis for directory: ${directory}${repoInfo}`);

            // Instantiate FileScanner
            const scanner = new FileScanner(absoluteDirectory, config.supportedExtensions, config.ignorePatterns);

            // === PHASE 1: Detect project structure ===
            let projectStructure: MultiModuleProjectStructure | null = null;
            const buildSystem = detectBuildSystem(absoluteDirectory);

            if (buildSystem === 'gradle' && context) {
                logger.info('Detected Gradle project, parsing module structure...');
                const gradleParser = new GradleParser(absoluteDirectory, context.repositoryId);
                projectStructure = await gradleParser.parseProject();

                if (projectStructure) {
                    logger.info(`Found ${projectStructure.modules.length} modules in Gradle project`);
                }
            } else if (buildSystem === 'maven' && context) {
                logger.info('Detected Maven project (Maven parsing not yet implemented)');
            }

            // === PHASE 2: Scan files with hashes ===
            logger.info('Scanning files with content hashes...');
            if (callback) {
                await callback.updateProgress({
                    phase: 'indexing_files',
                    progress_pct: 10,
                    total_files: checkpoint?.totalFilesDiscovered || 0,
                    processed_files: checkpoint?.filesProcessed.length || 0,
                    nodes_created: checkpoint?.nodesCreated || 0,
                    relationships_created: checkpoint?.relationshipsCreated || 0,
                    message: isResuming ? 'Resuming: Scanning files...' : 'Scanning files...',
                });
            }

            // Always scan with hashes for accurate change detection
            const allFiles = await scanner.scanWithHashes();
            const totalFilesFound = allFiles.length;
            filesScanned = totalFilesFound;

            // Check if this is a git repository
            const isGitRepo = await isGitRepository(absoluteDirectory);
            const currentCommitSha = isGitRepo ? await getCurrentCommitSha(absoluteDirectory) : null;

            // === PHASE 3: Determine files to process (incremental) ===
            const useIncremental = context && (incrementalOptions?.incrementalMode !== false);
            const forceFullReindex = incrementalOptions?.forceFullReindex === true;

            let incrementalResult: IncrementalIndexResult | null = null;
            let files: FileInfo[] = allFiles;
            let deletedFiles: string[] = [];
            let unchangedFiles: string[] = [];

            if (useIncremental && context) {
                logger.info('Determining files to process (incremental mode with hash verification)...');

                // Use enhanced method with hash verification
                incrementalResult = await this.incrementalIndexManager.determineFilesToProcessWithHashVerification(
                    absoluteDirectory,
                    context.repositoryId,
                    allFiles,
                    forceFullReindex,
                    isGitRepo
                );

                files = incrementalResult.changedFiles;
                deletedFiles = incrementalResult.deletedFiles;
                unchangedFiles = incrementalResult.unchangedFiles;

                logger.info(`Incremental analysis: ${files.length} changed, ${unchangedFiles.length} unchanged, ${deletedFiles.length} deleted`);
                logger.info(`Detection method: ${isGitRepo ? 'Git + Hash verification' : 'Hash-based comparison'}`);
                logger.info(`Reason: ${incrementalResult.reason}`);

                if (callback) {
                    callback.addLog({
                        level: 'info',
                        phase: 'indexing_files',
                        message: incrementalResult.isFullReindex
                            ? `Full reindex: ${incrementalResult.reason}`
                            : `Incremental (${isGitRepo ? 'git+hash' : 'hash'}): ${files.length} changed, ${unchangedFiles.length} unchanged`
                    });
                }

                // Clean up deleted files FIRST
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

            // === PHASE 4: Filter out already-processed files (for resume) ===
            if (isResuming) {
                // Combine checkpoint files and legacy resume files
                const alreadyProcessed = new Set<string>([
                    ...(checkpoint?.filesProcessed || []),
                    ...legacyResumeFiles
                ]);

                if (alreadyProcessed.size > 0) {
                    const filterResult = this.incrementalIndexManager.filterAlreadyProcessedFiles(files, [...alreadyProcessed]);
                    files = filterResult.filesToProcess;

                    logger.info(`Resume filter: Skipping ${filterResult.skippedCount} already-processed files, ${files.length} remaining`);

                    if (callback) {
                        callback.addLog({
                            level: 'info',
                            phase: 'indexing_files',
                            message: `Resume: Skipping ${filterResult.skippedCount} files, ${files.length} remaining`
                        });
                    }
                }
            }

            // === PHASE 5: Create or update checkpoint ===
            if (context && !checkpoint) {
                // Create new checkpoint
                checkpoint = await this.checkpointManager.createCheckpoint({
                    repositoryId: context.repositoryId,
                    incrementalMode: useIncremental ?? true,
                    totalFiles: files.length,
                });
                analysisId = checkpoint.analysisId;

                // Update with incremental info
                await this.checkpointManager.updatePhase(analysisId, 'incremental_check', {
                    changedFiles: files.map(f => f.path),
                    deletedFiles,
                    unchangedFiles,
                    isFullReindex: incrementalResult?.isFullReindex ?? true,
                    indexingReason: incrementalResult?.reason || 'Initial analysis',
                    totalFilesDiscovered: totalFilesFound,
                });

                logger.info(`Created checkpoint: ${analysisId}`);
            }

            // === Handle edge cases ===
            if (files.length === 0) {
                if (isResuming && checkpoint) {
                    logger.info('All files already processed. Completing checkpoint...');
                    await this.checkpointManager.completeCheckpoint(checkpoint.analysisId);
                    return {
                        filesScanned: totalFilesFound,
                        nodesCreated: checkpoint.nodesCreated,
                        relationshipsCreated: checkpoint.relationshipsCreated,
                        wasIncremental: true,
                        filesSkipped: unchangedFiles.length + checkpoint.filesProcessed.length,
                        filesDeleted: deletedFiles.length,
                        indexingReason: 'Resume - all files processed'
                    };
                }

                if (incrementalResult && !incrementalResult.isFullReindex) {
                    logger.info('No changed files to process. Index is up to date.');

                    // Save index state and complete checkpoint
                    if (context) {
                        const indexState = this.incrementalIndexManager.createIndexState(
                            context.repositoryId,
                            allFiles,
                            currentCommitSha
                        );
                        await this.incrementalIndexManager.saveIndexState(indexState);

                        if (analysisId) {
                            await this.checkpointManager.completeCheckpoint(analysisId);
                        }
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
                if (analysisId) {
                    await this.checkpointManager.completeCheckpoint(analysisId);
                }
                return { filesScanned: 0, nodesCreated: 0, relationshipsCreated: 0, wasIncremental: false, filesSkipped: 0, filesDeleted: 0 };
            }

            logger.info(`Found ${totalFilesFound} files total, ${files.length} to process.`);

            // Update checkpoint phase
            if (analysisId) {
                const totalBatches = Math.ceil(files.length / config.storageBatchSize);
                await this.checkpointManager.updatePhase(analysisId, 'parsing', {
                    totalBatches,
                });
            }

            // === PHASE 6: Enrich files with module information ===
            let moduleAwareFiles: ModuleAwareFileInfo[] = [];
            if (projectStructure) {
                moduleAwareFiles = scanner.enrichWithModuleInfo(files, projectStructure);
                const filesByModule = scanner.groupFilesByModule(moduleAwareFiles);
                logger.info(`Files grouped by module:`);
                for (const [moduleName, moduleFiles] of filesByModule) {
                    logger.debug(`  - ${moduleName || 'root'}: ${moduleFiles.length} files`);
                }
            }

            // === PHASE 7: Parse Files (Pass 1) ===
            logger.info('Parsing files (Pass 1)...');
            if (callback) {
                await callback.updateProgress({
                    phase: 'parsing_code',
                    progress_pct: 30,
                    total_files: filesScanned,
                    processed_files: checkpoint?.filesProcessed.length || 0,
                    nodes_created: checkpoint?.nodesCreated || 0,
                    relationships_created: checkpoint?.relationshipsCreated || 0,
                    message: 'Parsing files (Pass 1)...',
                });
                callback.addLog({ level: 'info', phase: 'parsing_code', message: `Parsing ${files.length} files...` });
            }

            await this.parser.parseFiles(files, context);

            // Collect Pass 1 Results
            logger.info('Collecting Pass 1 results...');
            const { allNodes: pass1Nodes, allRelationships: pass1Relationships } = await this.parser.collectResults();
            logger.info(`Collected ${pass1Nodes.length} nodes and ${pass1Relationships.length} relationships from Pass 1.`);

            if (callback) {
                await callback.updateProgress({
                    phase: 'parsing_code',
                    progress_pct: 50,
                    total_files: filesScanned,
                    processed_files: files.length,
                    nodes_created: pass1Nodes.length,
                    relationships_created: pass1Relationships.length,
                    message: `Collected ${pass1Nodes.length} nodes and ${pass1Relationships.length} relationships`,
                });
            }

            if (pass1Nodes.length === 0) {
                logger.warn('No nodes were generated during Pass 1. Aborting further analysis.');
                if (analysisId) {
                    await this.checkpointManager.completeCheckpoint(analysisId);
                }
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

            // === PHASE 8: Create Repository and Module structure ===
            if (context) {
                const { repositoryNode, belongsToRelationships } = this.createRepositoryStructure(
                    context,
                    pass1Nodes,
                    files.length
                );
                pass1Nodes.unshift(repositoryNode);
                pass1Relationships.push(...belongsToRelationships);
                logger.info(`Created Repository node and ${belongsToRelationships.length} BELONGS_TO relationships.`);

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
                }
            }

            // === PHASE 9: Resolve Relationships (Pass 2) ===
            logger.info('Resolving relationships (Pass 2)...');
            const tsProject: Project = this.parser.getTsProject();
            const resolver = new RelationshipResolver(pass1Nodes, pass1Relationships);
            const pass2Relationships = await resolver.resolveRelationships(tsProject);
            logger.info(`Resolved ${pass2Relationships.length} relationships in Pass 2.`);

            const finalNodes = pass1Nodes;
            const finalRelationships = [...pass1Relationships, ...pass2Relationships];
            const uniqueRelationships = Array.from(new Map(finalRelationships.map(r => [r.entityId, r])).values());
            logger.info(`Total unique relationships: ${uniqueRelationships.length}`);

            // === PHASE 10: Store Nodes with Checkpointing ===
            logger.info('Storing analysis results with checkpointing...');
            if (analysisId) {
                await this.checkpointManager.updatePhase(analysisId, 'storing_nodes');
            }

            if (callback) {
                await callback.updateProgress({
                    phase: 'building_graph',
                    progress_pct: 70,
                    total_files: filesScanned,
                    processed_files: files.length,
                    nodes_created: finalNodes.length,
                    relationships_created: uniqueRelationships.length,
                    message: `Storing ${finalNodes.length} nodes to database...`,
                });
            }

            // Create checkpoint callback for batch-level progress tracking
            const checkpointCallbacks: BatchCompleteCallback = {
                onNodeBatchComplete: async (batchIndex: number, filesInBatch: string[], nodesInBatch: number) => {
                    filesProcessedThisRun.push(...filesInBatch);
                    nodesCreatedThisRun += nodesInBatch;

                    if (analysisId) {
                        await this.checkpointManager.markBatchComplete(analysisId, {
                            filesInBatch,
                            batchIndex,
                            nodesInBatch,
                        });
                    }

                    // Log progress every 10 batches
                    if ((batchIndex + 1) % 10 === 0) {
                        logger.info(`Checkpoint: Batch ${batchIndex + 1} committed, ${filesProcessedThisRun.length} files stored`);
                    }
                },
                onRelationshipBatchComplete: async (batchIndex: number, relationshipType: string, count: number) => {
                    relationshipsCreatedThisRun += count;

                    if (analysisId) {
                        // Update checkpoint with relationship progress
                        await this.checkpointManager.markBatchComplete(analysisId, {
                            filesInBatch: [],
                            batchIndex,
                            nodesInBatch: 0,
                            relationshipsInBatch: count,
                        });
                    }
                },
            };

            // Store nodes with checkpoint callbacks
            const nodeResult = await this.storageManager.saveNodesBatch(finalNodes, checkpointCallbacks);
            logger.info(`Stored ${nodeResult.nodesStored} nodes in ${nodeResult.totalBatches} batches`);

            if (callback) {
                callback.addLog({ level: 'info', phase: 'building_graph', message: `Saved ${nodeResult.nodesStored} nodes successfully` });
            }

            // === PHASE 11: Store Relationships with Checkpointing ===
            if (analysisId) {
                await this.checkpointManager.updatePhase(analysisId, 'storing_relationships');
            }

            // Group relationships by type
            const relationshipsByType: { [type: string]: RelationshipInfo[] } = {};
            for (const rel of uniqueRelationships) {
                if (!relationshipsByType[rel.type]) {
                    relationshipsByType[rel.type] = [];
                }
                relationshipsByType[rel.type]!.push(rel);
            }

            if (callback) {
                await callback.updateProgress({
                    phase: 'building_graph',
                    progress_pct: 85,
                    total_files: filesScanned,
                    processed_files: files.length,
                    nodes_created: finalNodes.length,
                    relationships_created: uniqueRelationships.length,
                    message: `Storing ${uniqueRelationships.length} relationships...`,
                });
            }

            // Store relationships with checkpoint callbacks
            for (const type in relationshipsByType) {
                const batch = relationshipsByType[type];
                if (batch) {
                    await this.storageManager.saveRelationshipsBatch(type, batch, checkpointCallbacks);
                }
            }

            logger.info('Analysis results stored successfully.');

            // === PHASE 12: Compute PageRank ===
            if (context) {
                if (analysisId) {
                    await this.checkpointManager.updatePhase(analysisId, 'computing_pagerank');
                }

                logger.info('Computing PageRank scores...');
                if (callback) {
                    await callback.updateProgress({
                        phase: 'computing_relevance',
                        progress_pct: 92,
                        total_files: filesScanned,
                        processed_files: files.length,
                        nodes_created: finalNodes.length,
                        relationships_created: uniqueRelationships.length,
                        message: 'Computing relevance scores (PageRank)...',
                    });
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

            // === PHASE 13: Save Index State ===
            if (context && useIncremental) {
                if (analysisId) {
                    await this.checkpointManager.updatePhase(analysisId, 'saving_index_state');
                }

                logger.info('Saving index state for future incremental indexing...');
                try {
                    // Create or update index state
                    let indexState: IndexStateData;
                    const existingState = await this.incrementalIndexManager.loadIndexState(context.repositoryId);

                    if (existingState && !incrementalResult?.isFullReindex) {
                        // Update existing state with changes
                        indexState = this.incrementalIndexManager.updateIndexState(
                            existingState,
                            files,
                            deletedFiles,
                            currentCommitSha
                        );
                    } else {
                        // Create new state with all files
                        indexState = this.incrementalIndexManager.createIndexState(
                            context.repositoryId,
                            allFiles,
                            currentCommitSha
                        );
                    }

                    await this.incrementalIndexManager.saveIndexState(indexState);
                    logger.info(`Index state saved: ${indexState.totalFilesIndexed} files tracked (commit: ${currentCommitSha?.substring(0, 8) || 'N/A'})`);

                    if (callback) {
                        callback.addLog({
                            level: 'info',
                            phase: 'completed',
                            message: `Index state saved: ${indexState.totalFilesIndexed} files tracked`
                        });
                    }
                } catch (error: any) {
                    logger.warn(`Failed to save index state: ${error.message}`);
                }
            }

            // === PHASE 14: Complete checkpoint ===
            if (analysisId) {
                await this.checkpointManager.completeCheckpoint(analysisId);
                logger.info(`Checkpoint completed and removed: ${analysisId}`);
            }

            if (callback) {
                await callback.updateProgress({
                    phase: 'completed',
                    progress_pct: 100,
                    total_files: filesScanned,
                    processed_files: files.length + (checkpoint?.filesProcessed.length || 0),
                    nodes_created: finalNodes.length + (checkpoint?.nodesCreated || 0),
                    relationships_created: uniqueRelationships.length + (checkpoint?.relationshipsCreated || 0),
                    message: 'Analysis completed successfully',
                });
                callback.addLog({ level: 'info', phase: 'completed', message: 'Analysis completed successfully' });
            }

            // Calculate totals including resumed data
            const totalNodesCreated = finalNodes.length + (isResuming && checkpoint ? checkpoint.nodesCreated : 0);
            const totalRelationshipsCreated = uniqueRelationships.length + (isResuming && checkpoint ? checkpoint.relationshipsCreated : 0);
            const totalFilesSkipped = unchangedFiles.length + (isResuming && checkpoint ? checkpoint.filesProcessed.length : 0);

            return {
                filesScanned,
                nodesCreated: totalNodesCreated,
                relationshipsCreated: totalRelationshipsCreated,
                wasIncremental: incrementalResult ? !incrementalResult.isFullReindex : false,
                filesSkipped: totalFilesSkipped,
                filesDeleted: deletedFiles.length,
                indexingReason: incrementalResult?.reason,
            };

        } catch (error: any) {
            logger.error(`Analysis failed: ${error.message}`, { stack: error.stack });

            // Mark checkpoint as failed
            if (analysisId) {
                try {
                    await this.checkpointManager.failCheckpoint(analysisId, error.message);
                    logger.info(`Checkpoint marked as failed: ${analysisId}`);
                    logger.info(`Resume will be possible from: ${filesProcessedThisRun.length} files processed`);
                } catch (checkpointError: any) {
                    logger.warn(`Failed to update checkpoint on error: ${checkpointError.message}`);
                }
            }

            throw error;
        } finally {
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