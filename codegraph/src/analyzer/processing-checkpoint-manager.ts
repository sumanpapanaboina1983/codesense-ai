/**
 * Processing Checkpoint Manager
 *
 * Provides robust crash recovery for code analysis by tracking progress
 * in Neo4j. After each batch is committed, the checkpoint is updated
 * so that analysis can resume from the exact point of failure.
 *
 * Works for both:
 * - Git repositories (uses commit SHA + file hashes)
 * - Manually uploaded repos (uses file hashes only)
 */

import { randomUUID } from 'crypto';
import { Neo4jClient } from '../database/neo4j-client.js';
import { createContextLogger } from '../utils/logger.js';
import { generateEntityId } from './parser-utils.js';

const logger = createContextLogger('ProcessingCheckpointManager');

/**
 * Processing phases in order of execution
 */
export type ProcessingPhase =
    | 'initialized'
    | 'scanning'
    | 'incremental_check'
    | 'parsing'
    | 'storing_nodes'
    | 'storing_relationships'
    | 'computing_pagerank'
    | 'saving_index_state'
    | 'completed'
    | 'failed';

/**
 * Checkpoint data persisted to Neo4j for crash recovery
 */
export interface ProcessingCheckpoint {
    /** Unique entity ID for the checkpoint node */
    entityId: string;
    /** Repository this checkpoint belongs to */
    repositoryId: string;
    /** Unique ID for this analysis run */
    analysisId: string;
    /** Current processing phase */
    phase: ProcessingPhase;

    // === File Tracking ===
    /** Total files discovered in scan */
    totalFilesDiscovered: number;
    /** File paths that have been successfully stored to Neo4j */
    filesProcessed: string[];
    /** File paths that failed during parsing */
    filesFailed: string[];
    /** Files identified as changed (for incremental mode) */
    changedFiles: string[];
    /** Files identified as deleted (for cleanup) */
    deletedFiles: string[];
    /** Files identified as unchanged (to skip) */
    unchangedFiles: string[];

    // === Batch Tracking ===
    /** Current batch index being processed */
    currentBatchIndex: number;
    /** Total batches expected */
    totalBatches: number;

    // === Stats ===
    /** Number of nodes created so far */
    nodesCreated: number;
    /** Number of relationships created so far */
    relationshipsCreated: number;

    // === Timestamps ===
    /** When analysis started */
    startedAt: string;
    /** Last checkpoint update time */
    lastUpdatedAt: string;
    /** When analysis completed (null if incomplete) */
    completedAt: string | null;

    // === Mode Info ===
    /** Whether this is incremental mode */
    incrementalMode: boolean;
    /** Whether this is a full reindex */
    isFullReindex: boolean;
    /** Reason for indexing decision */
    indexingReason: string;

    // === Error Info ===
    /** Error message if failed */
    errorMessage: string | null;
}

/**
 * Options for creating a new checkpoint
 */
export interface CreateCheckpointOptions {
    repositoryId: string;
    incrementalMode: boolean;
    totalFiles: number;
}

/**
 * Options for updating checkpoint after batch processing
 */
export interface BatchCompleteUpdate {
    filesInBatch: string[];
    batchIndex: number;
    nodesInBatch: number;
    relationshipsInBatch?: number;
}

/**
 * Manages processing checkpoints for crash recovery.
 *
 * Usage:
 * 1. Call loadIncompleteCheckpoint() at start to check for resume
 * 2. Call createCheckpoint() to start new analysis
 * 3. Call updatePhase() when entering new phases
 * 4. Call markBatchComplete() after each successful batch commit
 * 5. Call completeCheckpoint() on success
 * 6. Call failCheckpoint() on error
 */
export class ProcessingCheckpointManager {
    private neo4jClient: Neo4jClient;

    constructor(neo4jClient: Neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    /**
     * Generates a unique analysis ID for a new run
     */
    generateAnalysisId(): string {
        return randomUUID();
    }

    /**
     * Loads an incomplete checkpoint for a repository.
     * Returns null if no incomplete checkpoint exists.
     */
    async loadIncompleteCheckpoint(repositoryId: string): Promise<ProcessingCheckpoint | null> {
        const cypher = `
            MATCH (c:ProcessingCheckpoint {repositoryId: $repositoryId})
            WHERE c.phase <> 'completed' AND c.phase <> 'failed'
            RETURN c {
                .entityId,
                .repositoryId,
                .analysisId,
                .phase,
                .totalFilesDiscovered,
                .filesProcessed,
                .filesFailed,
                .changedFiles,
                .deletedFiles,
                .unchangedFiles,
                .currentBatchIndex,
                .totalBatches,
                .nodesCreated,
                .relationshipsCreated,
                .startedAt,
                .lastUpdatedAt,
                .completedAt,
                .incrementalMode,
                .isFullReindex,
                .indexingReason,
                .errorMessage
            } as checkpoint
        `;

        try {
            const result = await this.neo4jClient.runTransaction<any>(
                cypher,
                { repositoryId },
                'READ',
                'CheckpointManager-Load'
            );

            const record = result.records?.[0];
            if (!record) {
                logger.debug(`No incomplete checkpoint found for repository: ${repositoryId}`);
                return null;
            }

            const checkpoint = record.get('checkpoint');

            // Parse JSON arrays
            const parsed: ProcessingCheckpoint = {
                ...checkpoint,
                filesProcessed: this.parseJsonArray(checkpoint.filesProcessed),
                filesFailed: this.parseJsonArray(checkpoint.filesFailed),
                changedFiles: this.parseJsonArray(checkpoint.changedFiles),
                deletedFiles: this.parseJsonArray(checkpoint.deletedFiles),
                unchangedFiles: this.parseJsonArray(checkpoint.unchangedFiles),
                currentBatchIndex: this.toNumber(checkpoint.currentBatchIndex),
                totalBatches: this.toNumber(checkpoint.totalBatches),
                nodesCreated: this.toNumber(checkpoint.nodesCreated),
                relationshipsCreated: this.toNumber(checkpoint.relationshipsCreated),
                totalFilesDiscovered: this.toNumber(checkpoint.totalFilesDiscovered),
            };

            logger.info(`Loaded incomplete checkpoint for ${repositoryId}:`);
            logger.info(`  - Analysis ID: ${parsed.analysisId}`);
            logger.info(`  - Phase: ${parsed.phase}`);
            logger.info(`  - Files processed: ${parsed.filesProcessed.length}/${parsed.totalFilesDiscovered}`);
            logger.info(`  - Nodes created: ${parsed.nodesCreated}`);
            logger.info(`  - Started: ${parsed.startedAt}`);

            return parsed;

        } catch (error: any) {
            logger.error(`Failed to load checkpoint: ${error.message}`);
            return null;
        }
    }

    /**
     * Creates a new checkpoint when starting analysis.
     */
    async createCheckpoint(options: CreateCheckpointOptions): Promise<ProcessingCheckpoint> {
        const now = new Date().toISOString();
        const analysisId = this.generateAnalysisId();
        const entityId = generateEntityId('processingcheckpoint', `${options.repositoryId}:${analysisId}`);

        const checkpoint: ProcessingCheckpoint = {
            entityId,
            repositoryId: options.repositoryId,
            analysisId,
            phase: 'initialized',
            totalFilesDiscovered: options.totalFiles,
            filesProcessed: [],
            filesFailed: [],
            changedFiles: [],
            deletedFiles: [],
            unchangedFiles: [],
            currentBatchIndex: 0,
            totalBatches: 0,
            nodesCreated: 0,
            relationshipsCreated: 0,
            startedAt: now,
            lastUpdatedAt: now,
            completedAt: null,
            incrementalMode: options.incrementalMode,
            isFullReindex: false,
            indexingReason: '',
            errorMessage: null,
        };

        // Delete any existing incomplete checkpoints for this repo first
        await this.deleteCheckpoint(options.repositoryId);

        const cypher = `
            CREATE (c:ProcessingCheckpoint {
                entityId: $entityId,
                repositoryId: $repositoryId,
                analysisId: $analysisId,
                phase: $phase,
                totalFilesDiscovered: $totalFilesDiscovered,
                filesProcessed: $filesProcessed,
                filesFailed: $filesFailed,
                changedFiles: $changedFiles,
                deletedFiles: $deletedFiles,
                unchangedFiles: $unchangedFiles,
                currentBatchIndex: $currentBatchIndex,
                totalBatches: $totalBatches,
                nodesCreated: $nodesCreated,
                relationshipsCreated: $relationshipsCreated,
                startedAt: $startedAt,
                lastUpdatedAt: $lastUpdatedAt,
                completedAt: $completedAt,
                incrementalMode: $incrementalMode,
                isFullReindex: $isFullReindex,
                indexingReason: $indexingReason,
                errorMessage: $errorMessage
            })
        `;

        try {
            await this.neo4jClient.runTransaction(
                cypher,
                {
                    ...checkpoint,
                    filesProcessed: JSON.stringify(checkpoint.filesProcessed),
                    filesFailed: JSON.stringify(checkpoint.filesFailed),
                    changedFiles: JSON.stringify(checkpoint.changedFiles),
                    deletedFiles: JSON.stringify(checkpoint.deletedFiles),
                    unchangedFiles: JSON.stringify(checkpoint.unchangedFiles),
                },
                'WRITE',
                'CheckpointManager-Create'
            );

            logger.info(`Created checkpoint for repository ${options.repositoryId}, analysis ${analysisId}`);
            return checkpoint;

        } catch (error: any) {
            logger.error(`Failed to create checkpoint: ${error.message}`);
            throw error;
        }
    }

    /**
     * Updates the checkpoint phase and optional metadata.
     */
    async updatePhase(
        analysisId: string,
        phase: ProcessingPhase,
        metadata?: Partial<Pick<ProcessingCheckpoint,
            'changedFiles' | 'deletedFiles' | 'unchangedFiles' |
            'isFullReindex' | 'indexingReason' | 'totalBatches' | 'totalFilesDiscovered'
        >>
    ): Promise<void> {
        const now = new Date().toISOString();

        let setClauses = ['c.phase = $phase', 'c.lastUpdatedAt = $lastUpdatedAt'];
        const params: Record<string, any> = {
            analysisId,
            phase,
            lastUpdatedAt: now,
        };

        if (metadata) {
            if (metadata.changedFiles !== undefined) {
                setClauses.push('c.changedFiles = $changedFiles');
                params.changedFiles = JSON.stringify(metadata.changedFiles);
            }
            if (metadata.deletedFiles !== undefined) {
                setClauses.push('c.deletedFiles = $deletedFiles');
                params.deletedFiles = JSON.stringify(metadata.deletedFiles);
            }
            if (metadata.unchangedFiles !== undefined) {
                setClauses.push('c.unchangedFiles = $unchangedFiles');
                params.unchangedFiles = JSON.stringify(metadata.unchangedFiles);
            }
            if (metadata.isFullReindex !== undefined) {
                setClauses.push('c.isFullReindex = $isFullReindex');
                params.isFullReindex = metadata.isFullReindex;
            }
            if (metadata.indexingReason !== undefined) {
                setClauses.push('c.indexingReason = $indexingReason');
                params.indexingReason = metadata.indexingReason;
            }
            if (metadata.totalBatches !== undefined) {
                setClauses.push('c.totalBatches = $totalBatches');
                params.totalBatches = metadata.totalBatches;
            }
            if (metadata.totalFilesDiscovered !== undefined) {
                setClauses.push('c.totalFilesDiscovered = $totalFilesDiscovered');
                params.totalFilesDiscovered = metadata.totalFilesDiscovered;
            }
        }

        const cypher = `
            MATCH (c:ProcessingCheckpoint {analysisId: $analysisId})
            SET ${setClauses.join(', ')}
        `;

        try {
            await this.neo4jClient.runTransaction(
                cypher,
                params,
                'WRITE',
                'CheckpointManager-UpdatePhase'
            );

            logger.debug(`Updated checkpoint phase to '${phase}' for analysis ${analysisId}`);

        } catch (error: any) {
            logger.error(`Failed to update checkpoint phase: ${error.message}`);
            throw error;
        }
    }

    /**
     * Marks a batch as complete and records processed files.
     * Call this AFTER the batch has been committed to Neo4j.
     */
    async markBatchComplete(
        analysisId: string,
        update: BatchCompleteUpdate
    ): Promise<void> {
        const now = new Date().toISOString();

        // We need to append to the existing filesProcessed array
        // Neo4j doesn't support array concatenation in SET, so we use APOC or do it manually
        const cypher = `
            MATCH (c:ProcessingCheckpoint {analysisId: $analysisId})
            SET c.filesProcessed = $newFilesProcessed,
                c.currentBatchIndex = $batchIndex,
                c.nodesCreated = c.nodesCreated + $nodesInBatch,
                c.relationshipsCreated = c.relationshipsCreated + $relationshipsInBatch,
                c.lastUpdatedAt = $lastUpdatedAt
            RETURN c.filesProcessed as currentFiles
        `;

        try {
            // First, get current files
            const getResult = await this.neo4jClient.runTransaction<any>(
                `MATCH (c:ProcessingCheckpoint {analysisId: $analysisId}) RETURN c.filesProcessed as files`,
                { analysisId },
                'READ',
                'CheckpointManager-GetFiles'
            );

            const currentFilesJson = getResult.records?.[0]?.get('files') || '[]';
            const currentFiles = this.parseJsonArray(currentFilesJson);
            const newFiles = [...currentFiles, ...update.filesInBatch];

            // Update with merged array
            await this.neo4jClient.runTransaction(
                cypher,
                {
                    analysisId,
                    newFilesProcessed: JSON.stringify(newFiles),
                    batchIndex: update.batchIndex,
                    nodesInBatch: update.nodesInBatch,
                    relationshipsInBatch: update.relationshipsInBatch || 0,
                    lastUpdatedAt: now,
                },
                'WRITE',
                'CheckpointManager-MarkBatch'
            );

            logger.debug(`Checkpoint updated: batch ${update.batchIndex}, +${update.filesInBatch.length} files (total: ${newFiles.length})`);

        } catch (error: any) {
            logger.error(`Failed to mark batch complete: ${error.message}`);
            // Don't throw - checkpoint update failure shouldn't stop analysis
            // The worst case is we re-process some files on resume
        }
    }

    /**
     * Marks files as failed during parsing.
     */
    async markFilesFailed(analysisId: string, failedFiles: string[]): Promise<void> {
        if (failedFiles.length === 0) return;

        const now = new Date().toISOString();

        try {
            // Get current failed files
            const getResult = await this.neo4jClient.runTransaction<any>(
                `MATCH (c:ProcessingCheckpoint {analysisId: $analysisId}) RETURN c.filesFailed as files`,
                { analysisId },
                'READ',
                'CheckpointManager-GetFailed'
            );

            const currentFilesJson = getResult.records?.[0]?.get('files') || '[]';
            const currentFiles = this.parseJsonArray(currentFilesJson);
            const newFiles = [...currentFiles, ...failedFiles];

            await this.neo4jClient.runTransaction(
                `
                MATCH (c:ProcessingCheckpoint {analysisId: $analysisId})
                SET c.filesFailed = $filesFailed, c.lastUpdatedAt = $lastUpdatedAt
                `,
                {
                    analysisId,
                    filesFailed: JSON.stringify(newFiles),
                    lastUpdatedAt: now,
                },
                'WRITE',
                'CheckpointManager-MarkFailed'
            );

            logger.debug(`Marked ${failedFiles.length} files as failed`);

        } catch (error: any) {
            logger.error(`Failed to mark files as failed: ${error.message}`);
        }
    }

    /**
     * Marks analysis as complete and cleans up checkpoint.
     */
    async completeCheckpoint(analysisId: string): Promise<void> {
        const now = new Date().toISOString();

        const cypher = `
            MATCH (c:ProcessingCheckpoint {analysisId: $analysisId})
            SET c.phase = 'completed',
                c.completedAt = $completedAt,
                c.lastUpdatedAt = $lastUpdatedAt
        `;

        try {
            await this.neo4jClient.runTransaction(
                cypher,
                { analysisId, completedAt: now, lastUpdatedAt: now },
                'WRITE',
                'CheckpointManager-Complete'
            );

            logger.info(`Analysis ${analysisId} completed successfully`);

            // Delete the checkpoint after successful completion
            await this.neo4jClient.runTransaction(
                `MATCH (c:ProcessingCheckpoint {analysisId: $analysisId}) DELETE c`,
                { analysisId },
                'WRITE',
                'CheckpointManager-DeleteCompleted'
            );

            logger.debug(`Deleted completed checkpoint for analysis ${analysisId}`);

        } catch (error: any) {
            logger.error(`Failed to complete checkpoint: ${error.message}`);
        }
    }

    /**
     * Marks analysis as failed with error message.
     */
    async failCheckpoint(analysisId: string, errorMessage: string): Promise<void> {
        const now = new Date().toISOString();

        const cypher = `
            MATCH (c:ProcessingCheckpoint {analysisId: $analysisId})
            SET c.phase = 'failed',
                c.errorMessage = $errorMessage,
                c.lastUpdatedAt = $lastUpdatedAt
        `;

        try {
            await this.neo4jClient.runTransaction(
                cypher,
                { analysisId, errorMessage, lastUpdatedAt: now },
                'WRITE',
                'CheckpointManager-Fail'
            );

            logger.error(`Analysis ${analysisId} failed: ${errorMessage}`);

        } catch (error: any) {
            logger.error(`Failed to update checkpoint with failure: ${error.message}`);
        }
    }

    /**
     * Deletes checkpoint for a repository.
     */
    async deleteCheckpoint(repositoryId: string): Promise<void> {
        const cypher = `
            MATCH (c:ProcessingCheckpoint {repositoryId: $repositoryId})
            DELETE c
        `;

        try {
            await this.neo4jClient.runTransaction(
                cypher,
                { repositoryId },
                'WRITE',
                'CheckpointManager-Delete'
            );

            logger.debug(`Deleted checkpoint(s) for repository ${repositoryId}`);

        } catch (error: any) {
            logger.warn(`Failed to delete checkpoint: ${error.message}`);
        }
    }

    /**
     * Gets checkpoint statistics for logging/monitoring
     */
    async getCheckpointStats(analysisId: string): Promise<{
        phase: ProcessingPhase;
        filesProcessed: number;
        totalFiles: number;
        nodesCreated: number;
        percentComplete: number;
    } | null> {
        const cypher = `
            MATCH (c:ProcessingCheckpoint {analysisId: $analysisId})
            RETURN c.phase as phase,
                   c.filesProcessed as filesProcessed,
                   c.totalFilesDiscovered as totalFiles,
                   c.nodesCreated as nodesCreated
        `;

        try {
            const result = await this.neo4jClient.runTransaction<any>(
                cypher,
                { analysisId },
                'READ',
                'CheckpointManager-Stats'
            );

            const record = result.records?.[0];
            if (!record) return null;

            const filesProcessed = this.parseJsonArray(record.get('filesProcessed')).length;
            const totalFiles = this.toNumber(record.get('totalFiles'));

            return {
                phase: record.get('phase'),
                filesProcessed,
                totalFiles,
                nodesCreated: this.toNumber(record.get('nodesCreated')),
                percentComplete: totalFiles > 0 ? Math.round((filesProcessed / totalFiles) * 100) : 0,
            };

        } catch (error: any) {
            logger.error(`Failed to get checkpoint stats: ${error.message}`);
            return null;
        }
    }

    // === Helper Methods ===

    private parseJsonArray(value: any): string[] {
        if (!value) return [];
        if (Array.isArray(value)) return value;
        if (typeof value === 'string') {
            try {
                const parsed = JSON.parse(value);
                return Array.isArray(parsed) ? parsed : [];
            } catch {
                return [];
            }
        }
        return [];
    }

    private toNumber(value: any): number {
        if (typeof value === 'number') return value;
        if (value?.toNumber) return value.toNumber();
        if (typeof value === 'string') return parseInt(value, 10) || 0;
        return 0;
    }
}
