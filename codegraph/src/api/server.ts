import express, { Request, Response, NextFunction } from 'express';
import cors from 'cors';
import path from 'path';
import { createContextLogger } from '../utils/logger.js';
import { AnalyzerService } from '../analyzer/analyzer-service.js';
import { AnalysisContext } from '../analyzer/types.js';
import { Neo4jClient } from '../database/neo4j-client.js';
import { SchemaManager } from '../database/schema.js';
import { cloneRepository, cleanupRepository, isGitUrl, parseGitUrl, CloneResult } from '../utils/git-utils.js';
import { createCallbackClient, CallbackClient } from './callback-client.js';
import config from '../config/index.js';

const logger = createContextLogger('CodeGraphAPI');

// Types for resume checkpoint data
interface ResumeCheckpoint {
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
    /** Additional checkpoint data (e.g., list of processed files) */
    checkpointData?: Record<string, any>;
}

// Types for API requests
interface AnalyzeRequest {
    /** Local directory path (required if gitUrl not provided) */
    directory?: string;
    /** Git URL to clone (required if directory not provided) */
    gitUrl?: string;
    /** Branch to checkout when cloning (optional) */
    branch?: string;
    /** Authentication token for private repos (optional) */
    gitToken?: string;
    /** Required: UUID from backend identifying the repository */
    repositoryId: string;
    /** Optional: Display name of the repository */
    repositoryName?: string;
    /** Optional: URL of the repository (e.g., GitHub URL) */
    repositoryUrl?: string;
    extensions?: string[];
    ignorePatterns?: string[];
    updateSchema?: boolean;
    resetDb?: boolean;
    /** Keep cloned repository after analysis (default: false for git URLs) */
    keepClone?: boolean;
    jspPaths?: string[];
    webflowPaths?: string[];
    enableElResolution?: boolean;
    includeTaglibs?: boolean;
    /** Backend callback URL for progress reporting */
    callbackUrl?: string;
    /** Analysis run ID in backend (for callback reporting) */
    analysisRunId?: string;
    /** Resume from checkpoint data (for resuming paused/failed jobs) */
    resumeFrom?: ResumeCheckpoint;
    /** Force complete re-indexing (ignores previous index state) */
    forceFullReindex?: boolean;
    /** Enable/disable incremental indexing (default: true) */
    incrementalMode?: boolean;
}

interface AnalysisJob {
    id: string;
    status: 'pending' | 'running' | 'completed' | 'failed';
    directory: string;
    gitUrl?: string;
    startedAt: Date;
    completedAt?: Date;
    error?: string;
    stats?: {
        filesScanned: number;
        nodesCreated: number;
        relationshipsCreated: number;
        /** Whether this was an incremental update */
        wasIncremental?: boolean;
        /** Number of files skipped (unchanged) */
        filesSkipped?: number;
        /** Number of files deleted and cleaned up */
        filesDeleted?: number;
    };
    /** Clone result for cleanup */
    cloneResult?: CloneResult;
    /** Backend analysis run ID for tracking */
    analysisRunId?: string;
    /** Callback client for progress reporting */
    callbackClient?: CallbackClient;
    /** Resume checkpoint data */
    resumeFrom?: ResumeCheckpoint;
}

// In-memory job store (could be replaced with Redis for production)
const jobs = new Map<string, AnalysisJob>();

// Neo4j client instance
let neo4jClient: Neo4jClient | null = null;

function generateJobId(): string {
    return `job-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

async function initializeNeo4jClient(): Promise<Neo4jClient> {
    if (!neo4jClient) {
        neo4jClient = new Neo4jClient();
        await neo4jClient.initializeDriver('API');
    }
    return neo4jClient;
}

export function createApp(): express.Application {
    const app = express();

    // Middleware
    app.use(cors());
    app.use(express.json());

    // Request logging middleware
    app.use((req: Request, _res: Response, next: NextFunction) => {
        logger.info(`${req.method} ${req.path}`, {
            query: req.query,
            body: req.method === 'POST' ? req.body : undefined
        });
        next();
    });

    // Health check endpoint
    app.get('/health', async (_req: Request, res: Response) => {
        try {
            const client = await initializeNeo4jClient();
            // Quick connectivity check
            await client.runTransaction('RETURN 1 as check', {}, 'READ', 'HealthCheck');
            res.json({
                status: 'healthy',
                neo4j: 'connected',
                timestamp: new Date().toISOString()
            });
        } catch (error: any) {
            res.status(503).json({
                status: 'unhealthy',
                neo4j: 'disconnected',
                error: error.message,
                timestamp: new Date().toISOString()
            });
        }
    });

    // Get API info
    app.get('/', (_req: Request, res: Response) => {
        res.json({
            name: 'CodeGraph API',
            version: '1.0.0',
            description: 'Codebase analysis tool generating a Neo4j graph',
            endpoints: {
                'GET /health': 'Health check',
                'GET /config': 'Get current configuration',
                'POST /analyze': 'Start codebase analysis',
                'GET /jobs': 'List all analysis jobs',
                'GET /jobs/:id': 'Get job status',
                'POST /schema/apply': 'Apply Neo4j schema',
                'POST /schema/reset': 'Reset database (delete all nodes)',
                'GET /graph/stats': 'Get graph statistics'
            }
        });
    });

    // Get current configuration (without sensitive data)
    app.get('/config', (_req: Request, res: Response) => {
        res.json({
            neo4jUrl: config.neo4jUrl,
            neo4jDatabase: config.neo4jDatabase,
            supportedExtensions: config.supportedExtensions,
            ignorePatterns: config.ignorePatterns,
            storageBatchSize: config.storageBatchSize,
            jspSpringConfig: config.jspSpringConfig
        });
    });

    // Start codebase analysis
    app.post('/analyze', async (req: Request, res: Response) => {
        const body = req.body as AnalyzeRequest;

        // Validate: either directory or gitUrl must be provided
        if (!body.directory && !body.gitUrl) {
            res.status(400).json({ error: 'Either directory or gitUrl is required' });
            return;
        }

        if (body.directory && body.gitUrl) {
            res.status(400).json({ error: 'Provide either directory or gitUrl, not both' });
            return;
        }

        if (!body.repositoryId) {
            res.status(400).json({ error: 'repositoryId is required for multi-repository support' });
            return;
        }

        const jobId = generateJobId();

        // Create callback client if backend URL and analysis run ID provided
        const callbackClient = createCallbackClient(body.callbackUrl, body.analysisRunId);

        const job: AnalysisJob = {
            id: jobId,
            status: 'pending',
            directory: body.directory || 'pending-clone',
            gitUrl: body.gitUrl,
            startedAt: new Date(),
            analysisRunId: body.analysisRunId,
            callbackClient: callbackClient || undefined,
            resumeFrom: body.resumeFrom,
        };

        jobs.set(jobId, job);

        // Return immediately with job ID
        res.status(202).json({
            message: 'Analysis started',
            jobId: jobId,
            analysisRunId: body.analysisRunId,
            repositoryId: body.repositoryId,
            gitUrl: body.gitUrl,
            statusUrl: `/jobs/${jobId}`
        });

        // Run analysis asynchronously
        runAnalysis(jobId, body).catch(error => {
            logger.error(`Job ${jobId} failed with unhandled error`, { error: error.message });
        });
    });

    // List all jobs
    app.get('/jobs', (_req: Request, res: Response) => {
        const jobList = Array.from(jobs.values()).map(job => ({
            id: job.id,
            status: job.status,
            directory: job.directory,
            gitUrl: job.gitUrl,
            startedAt: job.startedAt,
            completedAt: job.completedAt,
            error: job.error,
            stats: job.stats
        }));
        res.json({ jobs: jobList });
    });

    // Get job status
    app.get('/jobs/:id', async (req: Request<{ id: string }>, res: Response) => {
        const jobId = req.params.id;
        if (!jobId) {
            res.status(400).json({ error: 'Job ID is required' });
            return;
        }
        const job = jobs.get(jobId);
        if (!job) {
            res.status(404).json({ error: 'Job not found' });
            return;
        }

        // Helper to serialize job without non-serializable fields
        const serializeJob = (j: AnalysisJob, statsOverride?: typeof j.stats) => ({
            id: j.id,
            status: j.status,
            directory: j.directory,
            gitUrl: j.gitUrl,
            startedAt: j.startedAt,
            completedAt: j.completedAt,
            error: j.error,
            stats: statsOverride || j.stats,
            analysisRunId: j.analysisRunId,
        });

        // For running jobs, fetch live stats from Neo4j
        if (job.status === 'running' && !job.stats) {
            try {
                const client = await initializeNeo4jClient();
                const result = await client.runTransaction<any>(
                    `MATCH (n) WITH count(n) as nodes
                     OPTIONAL MATCH ()-[r]->()
                     RETURN nodes, count(r) as relationships`,
                    {},
                    'READ',
                    'JobStats'
                );
                const record = result.records?.[0];
                if (record) {
                    const liveStats = {
                        filesScanned: 0, // We don't track this during analysis
                        nodesCreated: record.get('nodes')?.toNumber?.() || record.get('nodes') || 0,
                        relationshipsCreated: record.get('relationships')?.toNumber?.() || record.get('relationships') || 0,
                    };
                    res.json(serializeJob(job, liveStats));
                    return;
                }
            } catch (error: any) {
                logger.warn('Failed to get live stats from Neo4j', { error: error.message });
            }
        }

        res.json(serializeJob(job));
    });

    // Delete a job
    app.delete('/jobs/:id', (req: Request<{ id: string }>, res: Response) => {
        const jobId = req.params.id;
        if (!jobId) {
            res.status(400).json({ error: 'Job ID is required' });
            return;
        }
        const job = jobs.get(jobId);
        if (!job) {
            res.status(404).json({ error: 'Job not found' });
            return;
        }

        // If job is running, mark it as cancelled (it will stop on next iteration)
        if (job.status === 'running' || job.status === 'pending') {
            job.status = 'failed';
            job.error = 'Cancelled by user';
            job.completedAt = new Date();
        }

        // Remove from jobs map
        jobs.delete(jobId);

        logger.info(`Job ${jobId} deleted`);
        res.json({
            success: true,
            message: 'Job deleted successfully',
            job_id: jobId
        });
    });

    // Cancel a running job
    app.post('/jobs/:id/cancel', (req: Request<{ id: string }>, res: Response) => {
        const jobId = req.params.id;
        if (!jobId) {
            res.status(400).json({ error: 'Job ID is required' });
            return;
        }
        const job = jobs.get(jobId);
        if (!job) {
            res.status(404).json({ error: 'Job not found' });
            return;
        }

        if (job.status !== 'running' && job.status !== 'pending') {
            res.status(400).json({ error: `Cannot cancel job with status: ${job.status}` });
            return;
        }

        job.status = 'failed';
        job.error = 'Cancelled by user';
        job.completedAt = new Date();

        logger.info(`Job ${jobId} cancelled`);
        res.json({
            success: true,
            message: 'Job cancelled successfully',
            job_id: jobId
        });
    });

    // Apply Neo4j schema
    app.post('/schema/apply', async (_req: Request, res: Response) => {
        try {
            const client = await initializeNeo4jClient();
            const schemaManager = new SchemaManager(client);
            await schemaManager.applySchema(true);
            res.json({ message: 'Schema applied successfully' });
        } catch (error: any) {
            logger.error('Failed to apply schema', { error: error.message });
            res.status(500).json({ error: error.message });
        }
    });

    // Reset database
    app.post('/schema/reset', async (_req: Request, res: Response) => {
        try {
            const client = await initializeNeo4jClient();
            const schemaManager = new SchemaManager(client);
            await schemaManager.resetDatabase();
            res.json({ message: 'Database reset successfully' });
        } catch (error: any) {
            logger.error('Failed to reset database', { error: error.message });
            res.status(500).json({ error: error.message });
        }
    });

    // Get graph statistics
    app.get('/graph/stats', async (_req: Request, res: Response) => {
        try {
            const client = await initializeNeo4jClient();

            // Get node counts by label
            const nodeCountsResult = await client.runTransaction<any>(
                `CALL db.labels() YIELD label
                 CALL apoc.cypher.run('MATCH (n:\`' + label + '\`) RETURN count(n) as count', {}) YIELD value
                 RETURN label, value.count as count
                 ORDER BY count DESC`,
                {},
                'READ',
                'GraphStats'
            );

            // Get relationship counts by type
            const relCountsResult = await client.runTransaction<any>(
                `CALL db.relationshipTypes() YIELD relationshipType
                 CALL apoc.cypher.run('MATCH ()-[r:\`' + relationshipType + '\`]->() RETURN count(r) as count', {}) YIELD value
                 RETURN relationshipType, value.count as count
                 ORDER BY count DESC`,
                {},
                'READ',
                'GraphStats'
            );

            // Get total counts
            const totalsResult = await client.runTransaction<any>(
                `MATCH (n) WITH count(n) as nodeCount
                 MATCH ()-[r]->()
                 RETURN nodeCount, count(r) as relationshipCount`,
                {},
                'READ',
                'GraphStats'
            );

            const nodesByLabel: Record<string, number> = {};
            nodeCountsResult.records?.forEach((record: any) => {
                nodesByLabel[record.get('label')] = record.get('count').toNumber?.() || record.get('count');
            });

            const relationshipsByType: Record<string, number> = {};
            relCountsResult.records?.forEach((record: any) => {
                relationshipsByType[record.get('relationshipType')] = record.get('count').toNumber?.() || record.get('count');
            });

            const totals = totalsResult.records?.[0];

            res.json({
                totalNodes: totals?.get('nodeCount')?.toNumber?.() || totals?.get('nodeCount') || 0,
                totalRelationships: totals?.get('relationshipCount')?.toNumber?.() || totals?.get('relationshipCount') || 0,
                nodesByLabel,
                relationshipsByType
            });
        } catch (error: any) {
            logger.error('Failed to get graph stats', { error: error.message });
            // Return basic stats if APOC is not available
            try {
                const client = await initializeNeo4jClient();
                const basicResult = await client.runTransaction<any>(
                    `MATCH (n) WITH count(n) as nodes
                     OPTIONAL MATCH ()-[r]->()
                     RETURN nodes, count(r) as relationships`,
                    {},
                    'READ',
                    'GraphStats'
                );
                const record = basicResult.records?.[0];
                res.json({
                    totalNodes: record?.get('nodes')?.toNumber?.() || record?.get('nodes') || 0,
                    totalRelationships: record?.get('relationships')?.toNumber?.() || record?.get('relationships') || 0,
                    note: 'Detailed stats require APOC plugin'
                });
            } catch (fallbackError: any) {
                res.status(500).json({ error: fallbackError.message });
            }
        }
    });

    // Execute custom Cypher query (read-only)
    app.post('/query', async (req: Request, res: Response) => {
        const { query, params } = req.body;

        if (!query) {
            res.status(400).json({ error: 'query is required' });
            return;
        }

        // Basic safety check - only allow read queries
        const upperQuery = query.toUpperCase().trim();
        if (upperQuery.includes('CREATE') ||
            upperQuery.includes('MERGE') ||
            upperQuery.includes('DELETE') ||
            upperQuery.includes('SET') ||
            upperQuery.includes('REMOVE') ||
            upperQuery.includes('DROP')) {
            res.status(403).json({ error: 'Only read queries are allowed through this endpoint' });
            return;
        }

        try {
            const client = await initializeNeo4jClient();
            const result = await client.runTransaction<any>(
                query,
                params || {},
                'READ',
                'CustomQuery'
            );

            const records = result.records?.map((record: any) => {
                const obj: Record<string, any> = {};
                record.keys.forEach((key: string) => {
                    const value = record.get(key);
                    obj[key] = value?.toNumber?.() || value;
                });
                return obj;
            }) || [];

            res.json({ records, count: records.length });
        } catch (error: any) {
            logger.error('Query execution failed', { error: error.message });
            res.status(500).json({ error: error.message });
        }
    });

    // Get module dependencies for a repository
    app.get('/repositories/:repositoryId/modules', async (req: Request<{ repositoryId: string }>, res: Response) => {
        const { repositoryId } = req.params;

        if (!repositoryId) {
            res.status(400).json({ error: 'repositoryId is required' });
            return;
        }

        try {
            const client = await initializeNeo4jClient();

            // First, check if repository exists and has modules
            const debugQuery = `
                MATCH (r:Repository {repositoryId: $repositoryId})
                OPTIONAL MATCH (r)-[rel:HAS_MODULE]->(m:JavaModule)
                RETURN r.repositoryId as repoId, r.name as repoName,
                       count(m) as moduleCount, collect(m.name) as moduleNames
            `;
            const debugResult = await client.runTransaction<any>(
                debugQuery,
                { repositoryId },
                'READ',
                'ModuleDebug'
            );

            if (debugResult.records && debugResult.records.length > 0) {
                const record = debugResult.records[0];
                logger.info('Module debug info', {
                    repositoryId,
                    foundRepoId: record.get('repoId'),
                    repoName: record.get('repoName'),
                    moduleCount: record.get('moduleCount')?.toNumber?.() || record.get('moduleCount'),
                    moduleNames: record.get('moduleNames'),
                });
            } else {
                logger.warn('No repository found with repositoryId', { repositoryId });
            }

            // Query for module statistics
            const moduleStatsQuery = `
                MATCH (r:Repository {repositoryId: $repositoryId})-[:HAS_MODULE]->(m:JavaModule)
                OPTIONAL MATCH (m)-[:CONTAINS_FILE]->(f:File)
                OPTIONAL MATCH (f)-[:CONTAINS|HAS_METHOD|DEFINES_FUNCTION*1..2]->(fn)
                WHERE fn:Function OR fn:Method OR fn:JavaMethod
                OPTIONAL MATCH (f)-[:CONTAINS|DEFINES_CLASS*1..2]->(c)
                WHERE c:Class OR c:JavaClass
                OPTIONAL MATCH (m)-[:DEPENDS_ON_MODULE]->(dep:JavaModule)
                OPTIONAL MATCH (dependent:JavaModule)-[:DEPENDS_ON_MODULE]->(m)
                RETURN
                    m.name as name,
                    m.path as path,
                    count(DISTINCT f) as fileCount,
                    count(DISTINCT fn) as functionCount,
                    count(DISTINCT c) as classCount,
                    sum(f.loc) as totalLoc,
                    avg(fn.complexity) as avgComplexity,
                    max(fn.complexity) as maxComplexity,
                    collect(DISTINCT dep.name) as dependencies,
                    collect(DISTINCT dependent.name) as dependents
            `;

            const moduleStatsResult = await client.runTransaction<any>(
                moduleStatsQuery,
                { repositoryId },
                'READ',
                'ModuleStats'
            );

            // Helper to safely convert Neo4j integers to plain numbers
            const toInt = (val: any): number => {
                if (val === null || val === undefined) return 0;
                if (typeof val === 'number') return val;
                if (typeof val?.toNumber === 'function') return val.toNumber();
                if (typeof val === 'object' && 'low' in val) return val.low; // Neo4j Long
                return 0;
            };
            const toFloat = (val: any): number | null => {
                if (val === null || val === undefined) return null;
                if (typeof val === 'number') return val;
                if (typeof val?.toNumber === 'function') return val.toNumber();
                return null;
            };

            const modules = (moduleStatsResult.records || []).map((record: any) => ({
                name: record.get('name') || '',
                path: record.get('path') || '',
                fileCount: toInt(record.get('fileCount')),
                functionCount: toInt(record.get('functionCount')),
                classCount: toInt(record.get('classCount')),
                totalLoc: toInt(record.get('totalLoc')),
                avgComplexity: toFloat(record.get('avgComplexity')),
                maxComplexity: toFloat(record.get('maxComplexity')),
                dependencies: record.get('dependencies')?.filter((d: string) => d) || [],
                dependents: record.get('dependents')?.filter((d: string) => d) || [],
            }));

            // If no modules found, return 404
            if (modules.length === 0) {
                res.status(404).json({ error: 'No modules found for this repository' });
                return;
            }

            // Query for dependency graph edges
            const dependencyGraphQuery = `
                MATCH (r:Repository {repositoryId: $repositoryId})-[:HAS_MODULE]->(m1:JavaModule)
                OPTIONAL MATCH (m1)-[d:DEPENDS_ON_MODULE]->(m2:JavaModule)
                WHERE m2 IS NOT NULL
                RETURN m1.name as source, m2.name as target, coalesce(d.weight, 1) as weight
            `;

            const graphResult = await client.runTransaction<any>(
                dependencyGraphQuery,
                { repositoryId },
                'READ',
                'ModuleDependencyGraph'
            );

            const dependencyGraph = (graphResult.records || [])
                .filter((record: any) => record.get('target'))
                .map((record: any) => ({
                    source: record.get('source') || '',
                    target: record.get('target') || '',
                    weight: toInt(record.get('weight')) || 1,
                }));

            res.json({
                modules,
                dependencyGraph,
            });
        } catch (error: any) {
            logger.error('Failed to get module dependencies', { error: error.message, repositoryId });
            res.status(500).json({ error: error.message });
        }
    });

    // Debug endpoint to check module data in Neo4j
    app.get('/debug/modules/:repositoryId', async (req: Request<{ repositoryId: string }>, res: Response) => {
        const { repositoryId } = req.params;

        try {
            const client = await initializeNeo4jClient();

            // Check for repository
            const repoQuery = `
                MATCH (r:Repository)
                WHERE r.repositoryId = $repositoryId OR r.entityId CONTAINS $repositoryId
                RETURN r.repositoryId as repoId, r.name as name, r.entityId as entityId, labels(r) as labels
            `;
            const repoResult = await client.runTransaction<any>(repoQuery, { repositoryId }, 'READ', 'DebugRepo');

            // Check for JavaModule nodes (any)
            const moduleQuery = `
                MATCH (m:JavaModule)
                RETURN m.name as name, m.entityId as entityId, m.repositoryId as repoId LIMIT 10
            `;
            const moduleResult = await client.runTransaction<any>(moduleQuery, {}, 'READ', 'DebugModules');

            // Check for HAS_MODULE relationships
            const relQuery = `
                MATCH ()-[r:HAS_MODULE]->()
                RETURN count(r) as count
            `;
            const relResult = await client.runTransaction<any>(relQuery, {}, 'READ', 'DebugRels');

            // Check nodes by kind property
            const kindQuery = `
                MATCH (n) WHERE n.kind = 'JavaModule' OR n.kind = 'Repository'
                RETURN n.kind as kind, n.name as name, n.entityId as entityId, labels(n) as labels LIMIT 20
            `;
            const kindResult = await client.runTransaction<any>(kindQuery, {}, 'READ', 'DebugKind');

            res.json({
                repositories: repoResult.records?.map((r: any) => ({
                    repoId: r.get('repoId'),
                    name: r.get('name'),
                    entityId: r.get('entityId'),
                    labels: r.get('labels'),
                })) || [],
                javaModules: moduleResult.records?.map((r: any) => ({
                    name: r.get('name'),
                    entityId: r.get('entityId'),
                    repoId: r.get('repoId'),
                })) || [],
                hasModuleRelationships: relResult.records?.[0]?.get('count')?.toNumber?.() || relResult.records?.[0]?.get('count') || 0,
                nodesByKind: kindResult.records?.map((r: any) => ({
                    kind: r.get('kind'),
                    name: r.get('name'),
                    entityId: r.get('entityId'),
                    labels: r.get('labels'),
                })) || [],
            });
        } catch (error: any) {
            logger.error('Debug endpoint error', { error: error.message });
            res.status(500).json({ error: error.message });
        }
    });

    // Error handling middleware
    app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
        logger.error('Unhandled error', { error: err.message, stack: err.stack });
        res.status(500).json({ error: 'Internal server error' });
    });

    return app;
}

async function runAnalysis(jobId: string, options: AnalyzeRequest): Promise<void> {
    const job = jobs.get(jobId);
    if (!job) return;

    job.status = 'running';
    let cloneResult: CloneResult | undefined;
    const callback = job.callbackClient;

    // Check if this is a resume operation
    const isResume = !!job.resumeFrom;
    const resumePhase = job.resumeFrom?.phase;
    const resumeProcessedFiles = job.resumeFrom?.processedFiles || 0;

    // Notify backend that analysis has started
    if (callback) {
        await callback.notifyStart(jobId);
        if (isResume) {
            callback.addLog({
                level: 'info',
                phase: 'startup',
                message: `Resuming analysis job ${jobId} from phase ${resumePhase}, ${resumeProcessedFiles} files already processed`,
            });
        } else {
            callback.addLog({
                level: 'info',
                phase: 'startup',
                message: `Analysis job ${jobId} started`,
            });
        }
    }

    try {
        const client = await initializeNeo4jClient();

        // Handle git URL cloning
        let analysisDirectory: string;

        if (options.gitUrl) {
            logger.info(`[${jobId}] Cloning repository from: ${options.gitUrl}`);
            if (callback) {
                await callback.updateProgress({
                    phase: 'cloning',
                    progress_pct: 0,
                    total_files: 0,
                    processed_files: 0,
                    nodes_created: 0,
                    relationships_created: 0,
                    message: 'Cloning repository...',
                });
                callback.addLog({
                    level: 'info',
                    phase: 'cloning',
                    message: `Cloning from ${options.gitUrl}`,
                });
            }
            try {
                cloneResult = await cloneRepository(options.gitUrl, {
                    branch: options.branch,
                    token: options.gitToken,
                    depth: 1, // Shallow clone for faster analysis
                });
                analysisDirectory = cloneResult.localPath;
                job.directory = analysisDirectory;
                job.cloneResult = cloneResult;
                logger.info(`[${jobId}] Repository cloned to: ${analysisDirectory}`);
                if (callback) {
                    callback.addLog({
                        level: 'info',
                        phase: 'cloning',
                        message: `Repository cloned to ${analysisDirectory}`,
                    });
                }
            } catch (cloneError: any) {
                throw new Error(`Failed to clone repository: ${cloneError.message}`);
            }
        } else {
            analysisDirectory = options.directory!;
        }

        // Apply JSP/Spring config overrides
        if (options.jspPaths) {
            config.jspSpringConfig.jspSourcePaths = options.jspPaths;
        }
        if (options.webflowPaths) {
            config.jspSpringConfig.webFlowDefinitionPaths = options.webflowPaths;
        }
        if (options.enableElResolution !== undefined) {
            config.jspSpringConfig.enableELResolution = options.enableElResolution;
        }
        if (options.includeTaglibs !== undefined) {
            config.jspSpringConfig.includeTagLibs = options.includeTaglibs;
        }

        // Handle schema and reset
        const schemaManager = new SchemaManager(client);

        if (options.resetDb) {
            logger.info(`[${jobId}] Resetting database...`);
            await schemaManager.resetDatabase();
        }

        if (options.updateSchema || options.resetDb) {
            logger.info(`[${jobId}] Applying schema...`);
            await schemaManager.applySchema(true);
        }

        // Determine repository name
        let repoName = options.repositoryName;
        if (!repoName) {
            if (options.gitUrl) {
                const parsed = parseGitUrl(options.gitUrl);
                repoName = parsed?.repo || 'unknown';
            } else {
                repoName = path.basename(analysisDirectory);
            }
        }

        // Create analysis context for multi-repository support
        const analysisContext: AnalysisContext = {
            repositoryId: options.repositoryId,
            repositoryName: repoName,
            repositoryUrl: options.repositoryUrl || options.gitUrl,
            rootDirectory: analysisDirectory,
        };

        // Run analysis with context
        logger.info(`[${jobId}] Starting analysis of: ${analysisDirectory} (Repository: ${analysisContext.repositoryName})`);
        if (callback) {
            await callback.updateProgress({
                phase: 'parsing',
                progress_pct: 10,
                total_files: 0,
                processed_files: 0,
                nodes_created: 0,
                relationships_created: 0,
                message: 'Starting code analysis...',
            });
            callback.addLog({
                level: 'info',
                phase: 'parsing',
                message: `Starting analysis of ${analysisContext.repositoryName}`,
            });
        }

        const analyzerService = new AnalyzerService();

        // Pass callback, resume data, and incremental options to analyzer
        const analysisResult = await analyzerService.analyze(
            analysisDirectory,
            analysisContext,
            callback || undefined,
            job.resumeFrom,
            {
                forceFullReindex: options.forceFullReindex,
                incrementalMode: options.incrementalMode,
            }
        );

        // Get final stats from Neo4j
        const statsResult = await client.runTransaction<any>(
            `MATCH (n) WITH count(n) as nodes
             OPTIONAL MATCH ()-[r]->()
             RETURN nodes, count(r) as relationships`,
            {},
            'READ',
            'FinalStats'
        );
        const statsRecord = statsResult.records?.[0];
        const finalNodes = statsRecord?.get('nodes')?.toNumber?.() || statsRecord?.get('nodes') || 0;
        const finalRels = statsRecord?.get('relationships')?.toNumber?.() || statsRecord?.get('relationships') || 0;

        job.status = 'completed';
        job.completedAt = new Date();
        job.stats = {
            filesScanned: analysisResult?.filesScanned || 0,
            nodesCreated: finalNodes,
            relationshipsCreated: finalRels,
            wasIncremental: analysisResult?.wasIncremental,
            filesSkipped: analysisResult?.filesSkipped,
            filesDeleted: analysisResult?.filesDeleted,
        };

        // Log incremental stats
        if (analysisResult?.wasIncremental) {
            logger.info(`[${jobId}] Incremental analysis completed: ${analysisResult.filesSkipped} files unchanged, ${analysisResult.filesDeleted} files cleaned up`);
        }
        logger.info(`[${jobId}] Analysis completed successfully`);

        // Notify backend of completion
        if (callback) {
            await callback.notifyComplete({
                success: true,
                stats: job.stats,
            });
        }

    } catch (error: any) {
        job.status = 'failed';
        job.completedAt = new Date();
        job.error = error.message;
        logger.error(`[${jobId}] Analysis failed`, { error: error.message });

        // Notify backend of failure
        if (callback) {
            callback.addLog({
                level: 'error',
                phase: 'error',
                message: `Analysis failed: ${error.message}`,
            });
            await callback.notifyComplete({
                success: false,
                error: error.message,
            });
        }
    } finally {
        // Cleanup callback client
        if (callback) {
            callback.cleanup();
        }

        // Cleanup cloned repository if not keeping
        if (cloneResult && cloneResult.isTemporary && !options.keepClone) {
            logger.info(`[${jobId}] Cleaning up cloned repository...`);
            await cleanupRepository(cloneResult.localPath);
        }
    }
}

export async function startServer(port: number = 3001): Promise<void> {
    const app = createApp();

    // Initialize Neo4j connection on startup
    try {
        await initializeNeo4jClient();
        logger.info('Neo4j connection established');
    } catch (error: any) {
        logger.error('Failed to connect to Neo4j on startup', { error: error.message });
        // Continue anyway - connection will be retried on first request
    }

    app.listen(port, '0.0.0.0', () => {
        logger.info(`CodeGraph API server running on http://0.0.0.0:${port}`);
    });
}

// Graceful shutdown
process.on('SIGTERM', async () => {
    logger.info('Received SIGTERM, shutting down...');
    if (neo4jClient) {
        await neo4jClient.closeDriver('Shutdown');
    }
    process.exit(0);
});

process.on('SIGINT', async () => {
    logger.info('Received SIGINT, shutting down...');
    if (neo4jClient) {
        await neo4jClient.closeDriver('Shutdown');
    }
    process.exit(0);
});
