import { Neo4jClient } from '../database/neo4j-client.js';
import { AstNode, RelationshipInfo } from './types.js';
import { createContextLogger } from '../utils/logger.js';
import { generateNodeLabelCypher } from './cypher-utils.js'; // Import the new utility
import config from '../config/index.js';
import { Neo4jError } from '../utils/errors.js';

const logger = createContextLogger('StorageManager');

/**
 * Callback invoked after each batch is successfully committed to Neo4j.
 * Use this for checkpointing to track progress.
 */
export interface BatchCompleteCallback {
    /**
     * Called after a batch of nodes is committed
     * @param batchIndex - The index of the batch (0-based)
     * @param filesInBatch - Unique file paths of nodes in this batch
     * @param nodesInBatch - Number of nodes in this batch
     */
    onNodeBatchComplete?: (batchIndex: number, filesInBatch: string[], nodesInBatch: number) => Promise<void>;

    /**
     * Called after a batch of relationships is committed
     * @param batchIndex - The index of the batch (0-based)
     * @param relationshipType - The type of relationships in this batch
     * @param count - Number of relationships in this batch
     */
    onRelationshipBatchComplete?: (batchIndex: number, relationshipType: string, count: number) => Promise<void>;
}

/**
 * Result of a file data deletion operation.
 */
export interface FileCleanupResult {
    /** Number of nodes deleted */
    nodesDeleted: number;
    /** Number of relationships deleted */
    relationshipsDeleted: number;
    /** File path that was cleaned up */
    filePath: string;
}

/**
 * Result of a batch file deletion operation.
 */
export interface BatchCleanupResult {
    /** Total nodes deleted across all files */
    totalNodesDeleted: number;
    /** Total relationships deleted across all files */
    totalRelationshipsDeleted: number;
    /** File paths that were cleaned up */
    cleanedPaths: string[];
    /** File paths that failed to clean up */
    failedPaths: string[];
}

/**
 * Manages batch writing of nodes and relationships to the Neo4j database.
 */
export class StorageManager {
    private neo4jClient: Neo4jClient;
    private batchSize: number;

    constructor(neo4jClient: Neo4jClient) {
        this.neo4jClient = neo4jClient;
        this.batchSize = config.storageBatchSize;
        logger.info(`StorageManager initialized with batch size: ${this.batchSize}`);
    }

    /**
     * Saves an array of AstNode objects to Neo4j in batches using MERGE.
     * Assumes the input 'nodes' array has already been deduplicated by entityId by the caller.
     * Uses a simple UNWIND + MERGE + SET Cypher query.
     *
     * @param nodes - The array of unique AstNode objects to save.
     * @param callbacks - Optional callbacks for progress tracking and checkpointing.
     * @returns Object containing batch statistics for checkpoint tracking.
     */
    async saveNodesBatch(
        nodes: AstNode[],
        callbacks?: BatchCompleteCallback
    ): Promise<{ totalBatches: number; nodesStored: number }> {
        if (nodes.length === 0) {
            logger.debug('No nodes provided to saveNodesBatch.');
            return { totalBatches: 0, nodesStored: 0 };
        }

        // Assume input `nodes` are already deduplicated by the caller (Parser.collectResults)
        logger.info(`Saving ${nodes.length} unique nodes to database...`);

        // Log node kind distribution for debugging
        const kindCounts: Record<string, number> = {};
        for (const node of nodes) {
            kindCounts[node.kind] = (kindCounts[node.kind] || 0) + 1;
        }
        logger.info(`Node kinds: ${JSON.stringify(kindCounts)}`);

        const { removeClause, setLabelClauses } = generateNodeLabelCypher();
        const totalBatches = Math.ceil(nodes.length / this.batchSize);
        let nodesStored = 0;

        for (let i = 0; i < nodes.length; i += this.batchSize) {
            const batch = nodes.slice(i, i + this.batchSize);
            const batchIndex = Math.floor(i / this.batchSize);

            if (batch.length === 0) {
                continue;
            }

            const preparedBatch = batch.map(node => ({
                entityId: node.entityId,
                kind: node.kind,
                properties: this.prepareNodeProperties(node)
            }));

            // Simple UNWIND + MERGE + SET query
            const cypher = `
                UNWIND $batch AS nodeData
                MERGE (n { entityId: nodeData.entityId })
                SET n += nodeData.properties
                ${removeClause}
                WITH n, nodeData.kind AS kind
                ${setLabelClauses}
            `;

            try {
                // COMMIT POINT: Each batch is committed as a separate transaction
                await this.neo4jClient.runTransaction(cypher, { batch: preparedBatch }, 'WRITE', 'StorageManager-Nodes');
                nodesStored += preparedBatch.length;
                logger.debug(`Saved batch ${batchIndex + 1}/${totalBatches}: ${preparedBatch.length} nodes (Total: ${nodesStored}/${nodes.length})`);

                // CHECKPOINT CALLBACK: Invoke after successful commit
                if (callbacks?.onNodeBatchComplete) {
                    // Extract unique file paths from this batch for checkpoint tracking
                    const filesInBatch = [...new Set(batch.map(n => n.filePath).filter(Boolean))];
                    try {
                        await callbacks.onNodeBatchComplete(batchIndex, filesInBatch, preparedBatch.length);
                    } catch (callbackError: any) {
                        // Log but don't fail - checkpoint errors shouldn't stop analysis
                        logger.warn(`Checkpoint callback failed (non-fatal): ${callbackError.message}`);
                    }
                }

            } catch (error: any) {
                logger.error(`Failed to save node batch (index ${i})`, { error: error.message, code: error.code });
                logger.error(`Failing node batch data (first 5): ${JSON.stringify(preparedBatch.slice(0, 5), null, 2)}`);
                throw new Neo4jError(`Failed to save node batch: ${error.message}`, { originalError: error, code: error.code });
            }
        }

        logger.info(`Finished saving ${nodesStored} unique nodes in ${totalBatches} batches.`);
        return { totalBatches, nodesStored };
    }

    /**
     * Saves an array of RelationshipInfo objects to Neo4j in batches using MERGE.
     * Assumes the input 'relationships' array has already been deduplicated by entityId.
     *
     * @param relationshipType - The specific type of relationships in this batch.
     * @param relationships - The array of unique RelationshipInfo objects to save.
     * @param callbacks - Optional callbacks for progress tracking and checkpointing.
     * @returns Object containing batch statistics for checkpoint tracking.
     */
    async saveRelationshipsBatch(
        relationshipType: string,
        relationships: RelationshipInfo[],
        callbacks?: BatchCompleteCallback
    ): Promise<{ totalBatches: number; relationshipsStored: number }> {
        if (relationships.length === 0) {
            logger.debug(`No relationships of type ${relationshipType} provided to saveRelationshipsBatch.`);
            return { totalBatches: 0, relationshipsStored: 0 };
        }

        // Assume input `relationships` are already deduplicated by the caller (Parser.collectResults)
        logger.info(`Saving ${relationships.length} unique relationships of type ${relationshipType} to database...`);

        const totalBatches = Math.ceil(relationships.length / this.batchSize);
        let relationshipsStored = 0;

        for (let i = 0; i < relationships.length; i += this.batchSize) {
            const batch = relationships.slice(i, i + this.batchSize);
            const batchIndex = Math.floor(i / this.batchSize);

            if (batch.length === 0) {
                continue;
            }

            const preparedBatch = batch.map(rel => this.prepareRelationshipProperties(rel));

            // Use MERGE for nodes, assuming they were created in saveNodesBatch
            const cypher = `
                UNWIND $batch AS relData
                MERGE (source { entityId: relData.sourceId })
                MERGE (target { entityId: relData.targetId })
                MERGE (source)-[r:\`${relationshipType}\` { entityId: relData.entityId }]->(target)
                ON CREATE SET r = relData.properties, r.type = relData.type, r.createdAt = relData.createdAt, r.weight = relData.weight
                ON MATCH SET r += relData.properties
            `;

            try {
                // COMMIT POINT: Each batch is committed as a separate transaction
                await this.neo4jClient.runTransaction(cypher, { batch: preparedBatch }, 'WRITE', 'StorageManager-Rels');
                relationshipsStored += preparedBatch.length;
                logger.debug(`Saved batch ${batchIndex + 1}/${totalBatches}: ${preparedBatch.length} ${relationshipType} relationships (Total: ${relationshipsStored}/${relationships.length})`);

                // CHECKPOINT CALLBACK: Invoke after successful commit
                if (callbacks?.onRelationshipBatchComplete) {
                    try {
                        await callbacks.onRelationshipBatchComplete(batchIndex, relationshipType, preparedBatch.length);
                    } catch (callbackError: any) {
                        // Log but don't fail - checkpoint errors shouldn't stop analysis
                        logger.warn(`Checkpoint callback failed (non-fatal): ${callbackError.message}`);
                    }
                }

            } catch (error: any) {
                logger.error(`Failed to save relationship batch (index ${i}, type: ${relationshipType})`, { error: error.message, code: error.code });
                logger.error(`Failing relationship batch data (first 5): ${JSON.stringify(preparedBatch.slice(0, 5), null, 2)}`);
                throw new Neo4jError(`Failed to save relationship batch (type ${relationshipType}): ${error.message}`, { originalError: error, code: error.code, context: { batch: preparedBatch.slice(0, 5) } });
            }
        }

        logger.info(`Finished saving ${relationshipsStored} unique relationships of type ${relationshipType} in ${totalBatches} batches.`);
        return { totalBatches, relationshipsStored };
    }

    /**
     * Recursively serializes complex objects to Neo4j-compatible primitives.
     * Converts Maps to plain objects, handles arrays, and preserves primitive types.
     * Special handling for objects that might cause Neo4j Map issues.
     */
    private serializeForNeo4j(value: any): any {
        try {
            if (value === null || value === undefined) {
                return value;
            }

            // Handle primitive types
            if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
                return value;
            }

            // Handle Maps - convert to plain objects
            if (value instanceof Map) {
                const obj: Record<string, any> = {};
                for (const [key, val] of value.entries()) {
                    obj[String(key)] = this.serializeForNeo4j(val);
                }
                return obj;
            }

            // Handle Sets - convert to arrays
            if (value instanceof Set) {
                return Array.from(value).map(item => this.serializeForNeo4j(item));
            }

            // Handle Arrays - for complex objects, serialize to JSON strings to avoid Map issues
            if (Array.isArray(value)) {
                return value.map(item => {
                    if (item && typeof item === 'object' && !(item instanceof Date)) {
                        // Convert complex objects in arrays to JSON strings to avoid Neo4j Map interpretation
                        try {
                            return JSON.stringify(this.serializeForNeo4j(item));
                        } catch {
                            return String(item);
                        }
                    }
                    return this.serializeForNeo4j(item);
                });
            }

            // Handle Date objects
            if (value instanceof Date) {
                return value.toISOString();
            }

            // Handle plain objects - convert to JSON string to avoid Neo4j Map issues
            if (typeof value === 'object' && value.constructor === Object) {
                try {
                    const serialized: Record<string, any> = {};
                    for (const [key, val] of Object.entries(value)) {
                        serialized[key] = this.serializeForNeo4j(val);
                    }
                    // Convert to JSON string to avoid Neo4j Map interpretation
                    return JSON.stringify(serialized);
                } catch {
                    return String(value);
                }
            }

            // For other object types, attempt JSON serialization as fallback
            if (typeof value === 'object') {
                try {
                    return JSON.stringify(JSON.parse(JSON.stringify(value)));
                } catch {
                    // If JSON serialization fails, convert to string representation
                    logger.warn(`Unable to serialize complex object, converting to string: ${value.constructor?.name || 'unknown'}`);
                    return String(value);
                }
            }

            return value;
        } catch (error: any) {
            logger.error(`Error serializing value for Neo4j:`, { error: error.message, value: typeof value });
            return String(value); // Fallback to string representation
        }
    }

    /**
     * Prepares AstNode properties for Neo4j storage.
     */
    private prepareNodeProperties(node: AstNode): Record<string, any> {
        const { kind, id, entityId, properties: nestedProperties, ...baseProperties } = node;
        const finalProperties: Record<string, any> = { ...baseProperties };
         if (nestedProperties && typeof nestedProperties === 'object') {
             Object.assign(finalProperties, nestedProperties);
         }
        
        // Serialize all properties to ensure Neo4j compatibility
        const serializedProperties: Record<string, any> = {};
        Object.keys(finalProperties).forEach(key => {
            if (finalProperties[key] !== undefined) {
                serializedProperties[key] = this.serializeForNeo4j(finalProperties[key]);
            }
        });
        
        serializedProperties.entityId = entityId; // Ensure entityId is part of the properties for SET
        return serializedProperties;
    }


    /**
     * Prepares RelationshipInfo properties for Neo4j storage.
     */
    private prepareRelationshipProperties(rel: RelationshipInfo): Record<string, any> {
        const preparedProps = { ...rel.properties };
         for (const key in preparedProps) {
             if (preparedProps[key] === undefined) {
                 preparedProps[key] = null; // Use null instead of deleting
             } else {
                 // Serialize complex objects for Neo4j compatibility
                 preparedProps[key] = this.serializeForNeo4j(preparedProps[key]);
             }
         }
        return {
            entityId: rel.entityId,
            sourceId: rel.sourceId,
            targetId: rel.targetId,
            type: rel.type,
            weight: rel.weight ?? 0,
            createdAt: rel.createdAt,
            properties: preparedProps,
        };
    }

    /**
     * Deletes all nodes and relationships belonging to a specific file.
     * Used for incremental indexing cleanup.
     * @param repositoryId - The repository ID.
     * @param filePath - The file path to delete data for.
     * @returns FileCleanupResult with deletion counts.
     */
    async deleteFileData(repositoryId: string, filePath: string): Promise<FileCleanupResult> {
        // First, count relationships that will be deleted
        const countCypher = `
            MATCH (n)
            WHERE n.filePath = $filePath AND n.repositoryId = $repositoryId
            OPTIONAL MATCH (n)-[r]-()
            RETURN count(DISTINCT n) as nodeCount, count(r) as relCount
        `;

        // Then delete nodes and their relationships
        const deleteCypher = `
            MATCH (n)
            WHERE n.filePath = $filePath AND n.repositoryId = $repositoryId
            DETACH DELETE n
            RETURN count(n) as nodesDeleted
        `;

        try {
            // Get counts first
            const countResult = await this.neo4jClient.runTransaction<any>(
                countCypher,
                { filePath, repositoryId },
                'READ',
                'StorageManager-CountFileData'
            );

            const countRecord = countResult.records?.[0];
            const expectedNodes = countRecord?.get('nodeCount')?.toNumber?.() ?? countRecord?.get('nodeCount') ?? 0;
            const expectedRels = countRecord?.get('relCount')?.toNumber?.() ?? countRecord?.get('relCount') ?? 0;

            if (expectedNodes === 0) {
                logger.debug(`No nodes found for file: ${filePath}`);
                return { nodesDeleted: 0, relationshipsDeleted: 0, filePath };
            }

            // Delete nodes and relationships
            const deleteResult = await this.neo4jClient.runTransaction<any>(
                deleteCypher,
                { filePath, repositoryId },
                'WRITE',
                'StorageManager-DeleteFileData'
            );

            const deleteRecord = deleteResult.records?.[0];
            const nodesDeleted = deleteRecord?.get('nodesDeleted')?.toNumber?.() ?? deleteRecord?.get('nodesDeleted') ?? 0;

            logger.debug(`Deleted ${nodesDeleted} nodes and ~${expectedRels} relationships for file: ${filePath}`);

            return {
                nodesDeleted,
                relationshipsDeleted: expectedRels,
                filePath,
            };
        } catch (error: any) {
            logger.error(`Failed to delete file data for ${filePath}: ${error.message}`);
            throw new Neo4jError(`Failed to delete file data: ${error.message}`, { originalError: error });
        }
    }

    /**
     * Batch deletes nodes and relationships for multiple files.
     * More efficient than calling deleteFileData repeatedly.
     * @param repositoryId - The repository ID.
     * @param filePaths - Array of file paths to delete data for.
     * @returns BatchCleanupResult with total counts and status.
     */
    async deleteFilesDataBatch(repositoryId: string, filePaths: string[]): Promise<BatchCleanupResult> {
        if (filePaths.length === 0) {
            return {
                totalNodesDeleted: 0,
                totalRelationshipsDeleted: 0,
                cleanedPaths: [],
                failedPaths: [],
            };
        }

        logger.info(`Batch deleting data for ${filePaths.length} files in repository ${repositoryId}`);

        let totalNodesDeleted = 0;
        let totalRelationshipsDeleted = 0;
        const cleanedPaths: string[] = [];
        const failedPaths: string[] = [];

        // Process in batches to avoid overwhelming the database
        const batchSize = 50;
        for (let i = 0; i < filePaths.length; i += batchSize) {
            const batch = filePaths.slice(i, i + batchSize);

            // Count relationships first
            const countCypher = `
                UNWIND $filePaths AS filePath
                MATCH (n)
                WHERE n.filePath = filePath AND n.repositoryId = $repositoryId
                OPTIONAL MATCH (n)-[r]-()
                RETURN sum(count(DISTINCT n)) as totalNodes, sum(count(r)) as totalRels
            `;

            // Delete nodes
            const deleteCypher = `
                UNWIND $filePaths AS filePath
                MATCH (n)
                WHERE n.filePath = filePath AND n.repositoryId = $repositoryId
                DETACH DELETE n
            `;

            try {
                // Get rough counts
                const countResult = await this.neo4jClient.runTransaction<any>(
                    `
                    MATCH (n)
                    WHERE n.filePath IN $filePaths AND n.repositoryId = $repositoryId
                    OPTIONAL MATCH (n)-[r]-()
                    RETURN count(DISTINCT n) as totalNodes, count(r) as totalRels
                    `,
                    { filePaths: batch, repositoryId },
                    'READ',
                    'StorageManager-CountBatch'
                );

                const countRecord = countResult.records?.[0];
                const batchNodes = countRecord?.get('totalNodes')?.toNumber?.() ?? countRecord?.get('totalNodes') ?? 0;
                const batchRels = countRecord?.get('totalRels')?.toNumber?.() ?? countRecord?.get('totalRels') ?? 0;

                // Delete
                await this.neo4jClient.runTransaction<any>(
                    `
                    MATCH (n)
                    WHERE n.filePath IN $filePaths AND n.repositoryId = $repositoryId
                    DETACH DELETE n
                    `,
                    { filePaths: batch, repositoryId },
                    'WRITE',
                    'StorageManager-DeleteBatch'
                );

                totalNodesDeleted += batchNodes;
                totalRelationshipsDeleted += batchRels;
                cleanedPaths.push(...batch);

                logger.debug(`Deleted batch ${Math.floor(i / batchSize) + 1}: ${batchNodes} nodes`);

            } catch (error: any) {
                logger.error(`Failed to delete batch starting at index ${i}: ${error.message}`);
                failedPaths.push(...batch);
            }
        }

        logger.info(`Batch cleanup complete: ${totalNodesDeleted} nodes, ${totalRelationshipsDeleted} relationships deleted`);

        return {
            totalNodesDeleted,
            totalRelationshipsDeleted,
            cleanedPaths,
            failedPaths,
        };
    }

    /**
     * Deletes all data for a repository (for full reset/reindex).
     * @param repositoryId - The repository ID.
     * @returns Total count of deleted nodes.
     */
    async deleteRepositoryData(repositoryId: string): Promise<number> {
        logger.info(`Deleting all data for repository ${repositoryId}`);

        const cypher = `
            MATCH (n)
            WHERE n.repositoryId = $repositoryId
            DETACH DELETE n
            RETURN count(n) as nodesDeleted
        `;

        try {
            const result = await this.neo4jClient.runTransaction<any>(
                cypher,
                { repositoryId },
                'WRITE',
                'StorageManager-DeleteRepository'
            );

            const record = result.records?.[0];
            const nodesDeleted = record?.get('nodesDeleted')?.toNumber?.() ?? record?.get('nodesDeleted') ?? 0;

            logger.info(`Deleted ${nodesDeleted} nodes for repository ${repositoryId}`);
            return nodesDeleted;
        } catch (error: any) {
            logger.error(`Failed to delete repository data: ${error.message}`);
            throw new Neo4jError(`Failed to delete repository data: ${error.message}`, { originalError: error });
        }
    }
}