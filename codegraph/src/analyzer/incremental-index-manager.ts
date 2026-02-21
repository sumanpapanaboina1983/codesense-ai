/**
 * Incremental Index Manager
 *
 * Manages incremental indexing by tracking index state and determining
 * which files need to be processed, skipped, or cleaned up.
 *
 * Supports two modes:
 * 1. Git-based: Uses git diff for fast change detection (for git repos)
 * 2. Hash-based: Compares file content hashes (for non-git repos or as fallback)
 *
 * Both modes use content hashes as the source of truth to ensure
 * only truly changed files are reprocessed.
 */
import { Neo4jClient } from '../database/neo4j-client.js';
import { FileInfo } from '../scanner/file-scanner.js';
import { createContextLogger } from '../utils/logger.js';
import { generateEntityId } from './parser-utils.js';
import {
    isGitRepository,
    getCurrentCommitSha,
    getChangesSinceCommit,
    GitDiffResult,
} from '../utils/git-change-detector.js';

const logger = createContextLogger('IncrementalIndexManager');

/**
 * Index state data stored in Neo4j.
 */
export interface IndexStateData {
    /** Entity ID for the IndexState node */
    entityId: string;
    /** Repository ID this state belongs to */
    repositoryId: string;
    /** Last indexed commit SHA (for git repos) */
    lastCommitSha: string | null;
    /** ISO timestamp of last indexing */
    lastIndexedAt: string;
    /** JSON-encoded map of filePath -> contentHash */
    fileHashes: Record<string, string>;
    /** Total number of files indexed */
    totalFilesIndexed: number;
    /** Index version for schema migrations */
    indexVersion: number;
}

/**
 * File change status.
 */
export type FileChangeStatus = 'added' | 'modified' | 'deleted' | 'unchanged';

/**
 * Information about a file's change status.
 */
export interface FileChangeInfo {
    /** File path */
    path: string;
    /** Change status */
    status: FileChangeStatus;
    /** File info (for added/modified files) */
    fileInfo?: FileInfo;
}

/**
 * Result of incremental index analysis.
 */
export interface IncrementalIndexResult {
    /** Files that need to be indexed (added or modified) */
    changedFiles: FileInfo[];
    /** Paths of files that were deleted and need cleanup */
    deletedFiles: string[];
    /** Paths of files that are unchanged and can be skipped */
    unchangedFiles: string[];
    /** Whether this is a full reindex (no previous state) */
    isFullReindex: boolean;
    /** Reason for the indexing decision */
    reason: string;
}

/**
 * Result of cleanup operation.
 */
export interface CleanupResult {
    /** Number of nodes deleted */
    nodesDeleted: number;
    /** Number of relationships deleted */
    relationshipsDeleted: number;
    /** File paths that were cleaned up */
    cleanedPaths: string[];
}

/**
 * Current index version. Increment this when making breaking schema changes
 * that require a full reindex.
 */
const CURRENT_INDEX_VERSION = 1;

/**
 * Result of filtering files by already-processed status
 */
export interface FilteredFilesResult {
    /** Files that still need processing */
    filesToProcess: FileInfo[];
    /** Files that were already processed (from checkpoint) */
    alreadyProcessed: string[];
    /** Number of files skipped */
    skippedCount: number;
}

/**
 * Manages incremental indexing state and operations.
 */
export class IncrementalIndexManager {
    private neo4jClient: Neo4jClient;

    constructor(neo4jClient: Neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    /**
     * Loads existing index state from Neo4j.
     * @param repositoryId - The repository ID.
     * @returns IndexStateData or null if not found.
     */
    async loadIndexState(repositoryId: string): Promise<IndexStateData | null> {
        const cypher = `
            MATCH (s:IndexState {repositoryId: $repositoryId})
            RETURN s.entityId as entityId,
                   s.repositoryId as repositoryId,
                   s.lastCommitSha as lastCommitSha,
                   s.lastIndexedAt as lastIndexedAt,
                   s.fileHashes as fileHashes,
                   s.totalFilesIndexed as totalFilesIndexed,
                   s.indexVersion as indexVersion
        `;

        try {
            const result = await this.neo4jClient.runTransaction<any>(
                cypher,
                { repositoryId },
                'READ',
                'IncrementalIndexManager-Load'
            );

            const record = result.records?.[0];
            if (!record) {
                logger.debug(`No index state found for repository: ${repositoryId}`);
                return null;
            }

            // Parse fileHashes from JSON string if needed
            let fileHashes: Record<string, string> = {};
            const rawFileHashes = record.get('fileHashes');
            if (rawFileHashes) {
                if (typeof rawFileHashes === 'string') {
                    try {
                        fileHashes = JSON.parse(rawFileHashes);
                    } catch {
                        logger.warn('Failed to parse fileHashes JSON, treating as empty');
                    }
                } else if (typeof rawFileHashes === 'object') {
                    fileHashes = rawFileHashes;
                }
            }

            const state: IndexStateData = {
                entityId: record.get('entityId'),
                repositoryId: record.get('repositoryId'),
                lastCommitSha: record.get('lastCommitSha'),
                lastIndexedAt: record.get('lastIndexedAt'),
                fileHashes,
                totalFilesIndexed: record.get('totalFilesIndexed')?.toNumber?.() ?? record.get('totalFilesIndexed') ?? 0,
                indexVersion: record.get('indexVersion')?.toNumber?.() ?? record.get('indexVersion') ?? 1,
            };

            logger.info(`Loaded index state for ${repositoryId}: ${state.totalFilesIndexed} files, version ${state.indexVersion}`);
            return state;
        } catch (error: any) {
            logger.error(`Failed to load index state: ${error.message}`);
            return null;
        }
    }

    /**
     * Determines which files need processing based on current state and previous index.
     * @param repoPath - Path to the repository.
     * @param repositoryId - Repository ID.
     * @param allFiles - All files discovered in the current scan.
     * @param forceFullReindex - Whether to force a full reindex.
     * @returns IncrementalIndexResult with files categorized by action.
     */
    async determineFilesToProcess(
        repoPath: string,
        repositoryId: string,
        allFiles: FileInfo[],
        forceFullReindex: boolean = false
    ): Promise<IncrementalIndexResult> {
        // If forced full reindex, return all files
        if (forceFullReindex) {
            logger.info('Forced full reindex requested');
            return {
                changedFiles: allFiles,
                deletedFiles: [],
                unchangedFiles: [],
                isFullReindex: true,
                reason: 'Forced full reindex requested',
            };
        }

        // Load existing state
        const existingState = await this.loadIndexState(repositoryId);

        // If no existing state, do full index
        if (!existingState) {
            logger.info('No existing index state, performing full index');
            return {
                changedFiles: allFiles,
                deletedFiles: [],
                unchangedFiles: [],
                isFullReindex: true,
                reason: 'No existing index state found',
            };
        }

        // Check for index version mismatch
        if (existingState.indexVersion !== CURRENT_INDEX_VERSION) {
            logger.info(`Index version mismatch (${existingState.indexVersion} vs ${CURRENT_INDEX_VERSION}), performing full reindex`);
            // Get all previously indexed files as deleted
            const deletedFiles = Object.keys(existingState.fileHashes);
            return {
                changedFiles: allFiles,
                deletedFiles,
                unchangedFiles: [],
                isFullReindex: true,
                reason: `Index version upgraded from ${existingState.indexVersion} to ${CURRENT_INDEX_VERSION}`,
            };
        }

        // Check if it's a git repository and use git diff if possible
        const isGit = await isGitRepository(repoPath);
        if (isGit && existingState.lastCommitSha) {
            const currentCommit = await getCurrentCommitSha(repoPath);
            if (currentCommit && currentCommit !== existingState.lastCommitSha) {
                logger.info(`Using git diff from ${existingState.lastCommitSha} to ${currentCommit}`);
                return this.processGitDiff(
                    repoPath,
                    allFiles,
                    existingState,
                    currentCommit
                );
            }
        }

        // Fall back to hash comparison
        logger.info('Using hash comparison for incremental indexing');
        return this.processHashComparison(allFiles, existingState);
    }

    /**
     * Process files using git diff for change detection.
     */
    private async processGitDiff(
        repoPath: string,
        allFiles: FileInfo[],
        existingState: IndexStateData,
        currentCommit: string
    ): Promise<IncrementalIndexResult> {
        try {
            const gitDiff = await getChangesSinceCommit(repoPath, existingState.lastCommitSha!);

            const changedPaths = new Set([...gitDiff.added, ...gitDiff.modified]);
            const deletedPaths = new Set(gitDiff.deleted);

            // Build file map for quick lookup
            const fileMap = new Map(allFiles.map(f => [f.path, f]));

            const changedFiles: FileInfo[] = [];
            const unchangedFiles: string[] = [];
            const deletedFiles: string[] = [];

            // Categorize current files
            for (const file of allFiles) {
                if (changedPaths.has(file.path)) {
                    changedFiles.push(file);
                } else {
                    unchangedFiles.push(file.path);
                }
            }

            // Check for deleted files (in previous state but not in current scan)
            for (const prevPath of Object.keys(existingState.fileHashes)) {
                if (!fileMap.has(prevPath) || deletedPaths.has(prevPath)) {
                    deletedFiles.push(prevPath);
                }
            }

            logger.info(`Git diff analysis: ${changedFiles.length} changed, ${unchangedFiles.length} unchanged, ${deletedFiles.length} deleted`);

            return {
                changedFiles,
                deletedFiles,
                unchangedFiles,
                isFullReindex: false,
                reason: `Git diff from ${existingState.lastCommitSha?.substring(0, 8)} to ${currentCommit.substring(0, 8)}`,
            };
        } catch (error: any) {
            logger.warn(`Git diff failed, falling back to hash comparison: ${error.message}`);
            return this.processHashComparison(allFiles, existingState);
        }
    }

    /**
     * Process files using hash comparison for change detection.
     */
    private processHashComparison(
        allFiles: FileInfo[],
        existingState: IndexStateData
    ): IncrementalIndexResult {
        const changedFiles: FileInfo[] = [];
        const unchangedFiles: string[] = [];
        const deletedFiles: string[] = [];

        // Build set of current file paths
        const currentFilePaths = new Set(allFiles.map(f => f.path));

        // Check each current file against stored hashes
        for (const file of allFiles) {
            const storedHash = existingState.fileHashes[file.path];

            if (!storedHash) {
                // New file
                changedFiles.push(file);
            } else if (file.contentHash && file.contentHash !== storedHash) {
                // Modified file
                changedFiles.push(file);
            } else if (!file.contentHash) {
                // No hash computed yet - need to process to be safe
                changedFiles.push(file);
            } else {
                // Unchanged
                unchangedFiles.push(file.path);
            }
        }

        // Find deleted files (in previous state but not in current)
        for (const prevPath of Object.keys(existingState.fileHashes)) {
            if (!currentFilePaths.has(prevPath)) {
                deletedFiles.push(prevPath);
            }
        }

        logger.info(`Hash comparison: ${changedFiles.length} changed, ${unchangedFiles.length} unchanged, ${deletedFiles.length} deleted`);

        return {
            changedFiles,
            deletedFiles,
            unchangedFiles,
            isFullReindex: false,
            reason: 'Hash comparison against previous index state',
        };
    }

    /**
     * Saves the updated index state after successful indexing.
     * @param state - The index state to save.
     */
    async saveIndexState(state: IndexStateData): Promise<void> {
        const cypher = `
            MERGE (s:IndexState {repositoryId: $repositoryId})
            SET s.entityId = $entityId,
                s.lastCommitSha = $lastCommitSha,
                s.lastIndexedAt = $lastIndexedAt,
                s.fileHashes = $fileHashes,
                s.totalFilesIndexed = $totalFilesIndexed,
                s.indexVersion = $indexVersion
        `;

        try {
            await this.neo4jClient.runTransaction(
                cypher,
                {
                    repositoryId: state.repositoryId,
                    entityId: state.entityId,
                    lastCommitSha: state.lastCommitSha,
                    lastIndexedAt: state.lastIndexedAt,
                    fileHashes: JSON.stringify(state.fileHashes),
                    totalFilesIndexed: state.totalFilesIndexed,
                    indexVersion: state.indexVersion,
                },
                'WRITE',
                'IncrementalIndexManager-Save'
            );

            logger.info(`Saved index state for ${state.repositoryId}: ${state.totalFilesIndexed} files`);
        } catch (error: any) {
            logger.error(`Failed to save index state: ${error.message}`);
            throw error;
        }
    }

    /**
     * Creates a new IndexStateData object for a repository.
     * @param repositoryId - Repository ID.
     * @param files - Files that were indexed.
     * @param commitSha - Current commit SHA (for git repos).
     */
    createIndexState(
        repositoryId: string,
        files: FileInfo[],
        commitSha: string | null
    ): IndexStateData {
        const fileHashes: Record<string, string> = {};
        for (const file of files) {
            if (file.contentHash) {
                fileHashes[file.path] = file.contentHash;
            }
        }

        return {
            entityId: generateEntityId('indexstate', repositoryId),
            repositoryId,
            lastCommitSha: commitSha,
            lastIndexedAt: new Date().toISOString(),
            fileHashes,
            totalFilesIndexed: files.length,
            indexVersion: CURRENT_INDEX_VERSION,
        };
    }

    /**
     * Updates an existing index state with new file hashes.
     * @param existingState - Existing index state.
     * @param changedFiles - Files that were changed/added.
     * @param deletedFiles - Files that were deleted.
     * @param commitSha - Current commit SHA.
     */
    updateIndexState(
        existingState: IndexStateData,
        changedFiles: FileInfo[],
        deletedFiles: string[],
        commitSha: string | null
    ): IndexStateData {
        const fileHashes = { ...existingState.fileHashes };

        // Add/update changed files
        for (const file of changedFiles) {
            if (file.contentHash) {
                fileHashes[file.path] = file.contentHash;
            }
        }

        // Remove deleted files
        for (const deletedPath of deletedFiles) {
            delete fileHashes[deletedPath];
        }

        return {
            ...existingState,
            lastCommitSha: commitSha,
            lastIndexedAt: new Date().toISOString(),
            fileHashes,
            totalFilesIndexed: Object.keys(fileHashes).length,
        };
    }

    /**
     * Cleans up nodes and relationships for deleted files.
     * @param repositoryId - Repository ID.
     * @param deletedPaths - Array of file paths to clean up.
     * @returns CleanupResult with counts.
     */
    async cleanupDeletedFiles(repositoryId: string, deletedPaths: string[]): Promise<CleanupResult> {
        if (deletedPaths.length === 0) {
            return { nodesDeleted: 0, relationshipsDeleted: 0, cleanedPaths: [] };
        }

        logger.info(`Cleaning up ${deletedPaths.length} deleted files for repository ${repositoryId}`);

        let totalNodesDeleted = 0;
        let totalRelationshipsDeleted = 0;
        const cleanedPaths: string[] = [];

        // Process in batches to avoid overwhelming the database
        const batchSize = 100;
        for (let i = 0; i < deletedPaths.length; i += batchSize) {
            const batch = deletedPaths.slice(i, i + batchSize);

            const cypher = `
                UNWIND $filePaths AS filePath
                MATCH (n)
                WHERE n.filePath = filePath AND n.repositoryId = $repositoryId
                OPTIONAL MATCH (n)-[r]-()
                WITH n, count(r) as relCount
                DETACH DELETE n
                RETURN count(n) as nodesDeleted, sum(relCount) as relsDeleted
            `;

            try {
                const result = await this.neo4jClient.runTransaction<any>(
                    cypher,
                    { filePaths: batch, repositoryId },
                    'WRITE',
                    'IncrementalIndexManager-Cleanup'
                );

                const record = result.records?.[0];
                if (record) {
                    const nodesDeleted = record.get('nodesDeleted')?.toNumber?.() ?? record.get('nodesDeleted') ?? 0;
                    const relsDeleted = record.get('relsDeleted')?.toNumber?.() ?? record.get('relsDeleted') ?? 0;
                    totalNodesDeleted += nodesDeleted;
                    totalRelationshipsDeleted += relsDeleted;
                }
                cleanedPaths.push(...batch);

            } catch (error: any) {
                logger.error(`Failed to cleanup batch: ${error.message}`);
                // Continue with other batches
            }
        }

        logger.info(`Cleanup complete: ${totalNodesDeleted} nodes, ${totalRelationshipsDeleted} relationships deleted`);

        return {
            nodesDeleted: totalNodesDeleted,
            relationshipsDeleted: totalRelationshipsDeleted,
            cleanedPaths,
        };
    }

    /**
     * Deletes the index state for a repository (used when doing full reset).
     * @param repositoryId - Repository ID.
     */
    async deleteIndexState(repositoryId: string): Promise<void> {
        const cypher = `
            MATCH (s:IndexState {repositoryId: $repositoryId})
            DELETE s
        `;

        try {
            await this.neo4jClient.runTransaction(
                cypher,
                { repositoryId },
                'WRITE',
                'IncrementalIndexManager-Delete'
            );
            logger.info(`Deleted index state for repository ${repositoryId}`);
        } catch (error: any) {
            logger.warn(`Failed to delete index state: ${error.message}`);
        }
    }

    /**
     * Filters out files that have already been processed (from a checkpoint).
     * Used when resuming from a crash.
     *
     * @param allFiles - All files to potentially process
     * @param processedFilePaths - File paths already processed (from checkpoint)
     * @returns Filtered files result
     */
    filterAlreadyProcessedFiles(
        allFiles: FileInfo[],
        processedFilePaths: string[]
    ): FilteredFilesResult {
        if (processedFilePaths.length === 0) {
            return {
                filesToProcess: allFiles,
                alreadyProcessed: [],
                skippedCount: 0,
            };
        }

        const processedSet = new Set(processedFilePaths);
        const filesToProcess: FileInfo[] = [];
        const alreadyProcessed: string[] = [];

        for (const file of allFiles) {
            if (processedSet.has(file.path)) {
                alreadyProcessed.push(file.path);
            } else {
                filesToProcess.push(file);
            }
        }

        logger.info(`Resume filter: ${alreadyProcessed.length} already processed, ${filesToProcess.length} remaining`);

        return {
            filesToProcess,
            alreadyProcessed,
            skippedCount: alreadyProcessed.length,
        };
    }

    /**
     * Verifies which files have actually changed by comparing content hashes.
     * This is the source of truth for both git and non-git workflows.
     *
     * Even if git says a file changed, if the hash is the same, we skip it.
     * This handles cases like:
     * - Whitespace-only changes that don't affect parsing
     * - Files that were reverted
     * - Git metadata changes without content changes
     *
     * @param files - Files to verify
     * @param existingHashes - Previously stored file hashes
     * @returns Object with truly changed and unchanged files
     */
    verifyChangesWithHashes(
        files: FileInfo[],
        existingHashes: Record<string, string>
    ): { changed: FileInfo[]; unchanged: FileInfo[] } {
        const changed: FileInfo[] = [];
        const unchanged: FileInfo[] = [];

        for (const file of files) {
            const storedHash = existingHashes[file.path];
            const currentHash = file.contentHash;

            if (!storedHash) {
                // New file - definitely changed
                changed.push(file);
            } else if (!currentHash) {
                // No hash computed - need to process to be safe
                changed.push(file);
            } else if (currentHash !== storedHash) {
                // Hash differs - content changed
                changed.push(file);
            } else {
                // Same hash - no real change
                unchanged.push(file);
            }
        }

        if (unchanged.length > 0) {
            logger.info(`Hash verification: ${unchanged.length} files unchanged despite being flagged, ${changed.length} truly changed`);
        }

        return { changed, unchanged };
    }

    /**
     * Partially updates index state with newly processed files.
     * Used for incremental checkpoint saves during processing.
     *
     * @param repositoryId - Repository ID
     * @param processedFiles - Files that have been successfully stored
     * @param commitSha - Current commit SHA (if git repo)
     */
    async partialSaveIndexState(
        repositoryId: string,
        processedFiles: FileInfo[],
        commitSha: string | null
    ): Promise<void> {
        if (processedFiles.length === 0) {
            return;
        }

        const now = new Date().toISOString();

        // Build file hashes map for processed files
        const newHashes: Record<string, string> = {};
        for (const file of processedFiles) {
            if (file.contentHash) {
                newHashes[file.path] = file.contentHash;
            }
        }

        // Load existing state
        const existingState = await this.loadIndexState(repositoryId);

        if (existingState) {
            // Merge with existing hashes
            const mergedHashes = { ...existingState.fileHashes, ...newHashes };

            const cypher = `
                MATCH (s:IndexState {repositoryId: $repositoryId})
                SET s.fileHashes = $fileHashes,
                    s.lastIndexedAt = $lastIndexedAt,
                    s.totalFilesIndexed = $totalFilesIndexed
                    ${commitSha ? ', s.lastCommitSha = $lastCommitSha' : ''}
            `;

            await this.neo4jClient.runTransaction(
                cypher,
                {
                    repositoryId,
                    fileHashes: JSON.stringify(mergedHashes),
                    lastIndexedAt: now,
                    totalFilesIndexed: Object.keys(mergedHashes).length,
                    lastCommitSha: commitSha,
                },
                'WRITE',
                'IncrementalIndexManager-PartialSave'
            );

            logger.debug(`Partial index state save: added ${processedFiles.length} files (total: ${Object.keys(mergedHashes).length})`);

        } else {
            // Create new state with just these files
            const entityId = generateEntityId('indexstate', repositoryId);

            const cypher = `
                CREATE (s:IndexState {
                    entityId: $entityId,
                    repositoryId: $repositoryId,
                    lastCommitSha: $lastCommitSha,
                    lastIndexedAt: $lastIndexedAt,
                    fileHashes: $fileHashes,
                    totalFilesIndexed: $totalFilesIndexed,
                    indexVersion: $indexVersion
                })
            `;

            await this.neo4jClient.runTransaction(
                cypher,
                {
                    entityId,
                    repositoryId,
                    lastCommitSha: commitSha,
                    lastIndexedAt: now,
                    fileHashes: JSON.stringify(newHashes),
                    totalFilesIndexed: Object.keys(newHashes).length,
                    indexVersion: CURRENT_INDEX_VERSION,
                },
                'WRITE',
                'IncrementalIndexManager-PartialCreate'
            );

            logger.debug(`Created partial index state with ${processedFiles.length} files`);
        }
    }

    /**
     * Determines files to process with enhanced hash verification.
     * Works for both git and non-git repositories.
     *
     * For git repos: Uses git diff first, then verifies with hash comparison
     * For non-git repos: Uses hash comparison directly
     *
     * @param repoPath - Path to the repository
     * @param repositoryId - Repository ID
     * @param allFiles - All files discovered in scan (must have contentHash)
     * @param forceFullReindex - Force full reindex
     * @param isGitRepo - Whether this is a git repository
     */
    async determineFilesToProcessWithHashVerification(
        repoPath: string,
        repositoryId: string,
        allFiles: FileInfo[],
        forceFullReindex: boolean = false,
        isGitRepo: boolean = false
    ): Promise<IncrementalIndexResult> {
        // Ensure all files have hashes for accurate comparison
        const filesWithoutHash = allFiles.filter(f => !f.contentHash);
        if (filesWithoutHash.length > 0) {
            logger.warn(`${filesWithoutHash.length} files missing content hash - they will be processed`);
        }

        // Delegate to standard method first
        const result = await this.determineFilesToProcess(
            repoPath,
            repositoryId,
            allFiles,
            forceFullReindex
        );

        // If full reindex, no need for hash verification
        if (result.isFullReindex) {
            return result;
        }

        // Load existing state for hash verification
        const existingState = await this.loadIndexState(repositoryId);
        if (!existingState) {
            return result;
        }

        // Verify "changed" files using hash comparison
        // This catches false positives from git diff (whitespace changes, etc.)
        const { changed, unchanged } = this.verifyChangesWithHashes(
            result.changedFiles,
            existingState.fileHashes
        );

        if (unchanged.length > 0) {
            logger.info(`Hash verification filtered out ${unchanged.length} false-positive changes`);
        }

        return {
            changedFiles: changed,
            deletedFiles: result.deletedFiles,
            unchangedFiles: [...result.unchangedFiles, ...unchanged.map(f => f.path)],
            isFullReindex: false,
            reason: result.reason + (unchanged.length > 0 ? ` (${unchanged.length} filtered by hash check)` : ''),
        };
    }
}
