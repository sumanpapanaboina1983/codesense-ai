import express, { Request, Response, NextFunction } from 'express';
import cors from 'cors';
import path from 'path';
import { createContextLogger } from '../utils/logger.js';
import { AnalyzerService } from '../analyzer/analyzer-service.js';
import { AnalysisContext } from '../analyzer/types.js';
import { Neo4jClient } from '../database/neo4j-client.js';
import { SchemaManager } from '../database/schema.js';
import { cloneRepository, cleanupRepository, isGitUrl, parseGitUrl, CloneResult } from '../utils/git-utils.js';
import config from '../config/index.js';

const logger = createContextLogger('CodeGraphAPI');

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
    };
    /** Clone result for cleanup */
    cloneResult?: CloneResult;
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
        const job: AnalysisJob = {
            id: jobId,
            status: 'pending',
            directory: body.directory || 'pending-clone',
            gitUrl: body.gitUrl,
            startedAt: new Date()
        };

        jobs.set(jobId, job);

        // Return immediately with job ID
        res.status(202).json({
            message: 'Analysis started',
            jobId: jobId,
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
    app.get('/jobs/:id', (req: Request<{ id: string }>, res: Response) => {
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
        res.json(job);
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

    try {
        const client = await initializeNeo4jClient();

        // Handle git URL cloning
        let analysisDirectory: string;

        if (options.gitUrl) {
            logger.info(`[${jobId}] Cloning repository from: ${options.gitUrl}`);
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
        const analyzerService = new AnalyzerService();
        await analyzerService.analyze(analysisDirectory, analysisContext);

        job.status = 'completed';
        job.completedAt = new Date();
        logger.info(`[${jobId}] Analysis completed successfully`);

    } catch (error: any) {
        job.status = 'failed';
        job.completedAt = new Date();
        job.error = error.message;
        logger.error(`[${jobId}] Analysis failed`, { error: error.message });
    } finally {
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
