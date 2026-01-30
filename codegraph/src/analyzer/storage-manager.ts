import { Neo4jClient } from '../database/neo4j-client.js';
import { AstNode, RelationshipInfo } from './types.js';
import { createContextLogger } from '../utils/logger.js';
import { generateNodeLabelCypher } from './cypher-utils.js'; // Import the new utility
import config from '../config/index.js';
import { Neo4jError } from '../utils/errors.js';

const logger = createContextLogger('StorageManager');

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
     * @param nodes - The array of unique AstNode objects to save.
     */
    async saveNodesBatch(nodes: AstNode[]): Promise<void> {
        if (nodes.length === 0) {
            logger.debug('No nodes provided to saveNodesBatch.');
            return;
        }

        // Assume input `nodes` are already deduplicated by the caller (Parser.collectResults)
        logger.info(`Saving ${nodes.length} unique nodes to database...`);

        const { removeClause, setLabelClauses } = generateNodeLabelCypher();

        for (let i = 0; i < nodes.length; i += this.batchSize) {
             const batch = nodes.slice(i, i + this.batchSize);

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
                await this.neo4jClient.runTransaction(cypher, { batch: preparedBatch }, 'WRITE', 'StorageManager-Nodes');
                logger.debug(`Saved batch of ${preparedBatch.length} nodes (Total processed: ${Math.min(i + preparedBatch.length, nodes.length)}/${nodes.length})`);
            } catch (error: any) {
                logger.error(`Failed to save node batch (index ${i})`, { error: error.message, code: error.code });
                 logger.error(`Failing node batch data (first 5): ${JSON.stringify(preparedBatch.slice(0, 5), null, 2)}`);
                throw new Neo4jError(`Failed to save node batch: ${error.message}`, { originalError: error, code: error.code });
            }
        }
        logger.info(`Finished saving ${nodes.length} unique nodes.`);
    }

    /**
     * Saves an array of RelationshipInfo objects to Neo4j in batches using MERGE.
     * Assumes the input 'relationships' array has already been deduplicated by entityId.
     * @param relationshipType - The specific type of relationships in this batch.
     * @param relationships - The array of unique RelationshipInfo objects to save.
     */
    async saveRelationshipsBatch(relationshipType: string, relationships: RelationshipInfo[]): Promise<void> {
        if (relationships.length === 0) {
            logger.debug(`No relationships of type ${relationshipType} provided to saveRelationshipsBatch.`);
            return;
        }

        // Assume input `relationships` are already deduplicated by the caller (Parser.collectResults)
        logger.info(`Saving ${relationships.length} unique relationships of type ${relationshipType} to database...`);

        for (let i = 0; i < relationships.length; i += this.batchSize) {
            const batch = relationships.slice(i, i + this.batchSize);

             if (batch.length === 0) {
                 continue;
             }

             const preparedBatch = batch.map(rel => this.prepareRelationshipProperties(rel));

            // Use MATCH for nodes, assuming they were created in saveNodesBatch
            const cypher = `
                UNWIND $batch AS relData
                 MERGE (source { entityId: relData.sourceId })
 // Use MERGE instead of MATCH
                 MERGE (target { entityId: relData.targetId })
 // Use MERGE instead of MATCH
                 MERGE (source)-[r:\`${relationshipType}\` { entityId: relData.entityId }]->(target) // Merge relationship on entityId
                ON CREATE SET r = relData.properties, r.type = relData.type, r.createdAt = relData.createdAt, r.weight = relData.weight
                ON MATCH SET r += relData.properties
            `;

            try {
                await this.neo4jClient.runTransaction(cypher, { batch: preparedBatch }, 'WRITE', 'StorageManager-Rels');
                logger.debug(`Saved batch of ${preparedBatch.length} relationships (Total processed: ${Math.min(i + preparedBatch.length, relationships.length)}/${relationships.length})`);
            } catch (error: any) {
                logger.error(`Failed to save relationship batch (index ${i}, type: ${relationshipType})`, { error: error.message, code: error.code });
                 logger.error(`Failing relationship batch data (first 5): ${JSON.stringify(preparedBatch.slice(0, 5), null, 2)}`);
                throw new Neo4jError(`Failed to save relationship batch (type ${relationshipType}): ${error.message}`, { originalError: error, code: error.code, context: { batch: preparedBatch.slice(0,5) } });
            }
        }
        logger.info(`Finished saving ${relationships.length} unique relationships of type ${relationshipType}.`);
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
}