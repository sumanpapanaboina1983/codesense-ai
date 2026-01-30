import { Command } from 'commander';
import path from 'path';
import { createContextLogger } from '../utils/logger.js';
import { AnalyzerService } from '../analyzer/analyzer-service.js';
import { AnalysisContext } from '../analyzer/types.js';
import { Neo4jClient } from '../database/neo4j-client.js';
import { SchemaManager } from '../database/schema.js';
import { cloneRepository, cleanupRepository, isGitUrl, parseGitUrl, CloneResult } from '../utils/git-utils.js';
import config from '../config/index.js';

const logger = createContextLogger('AnalyzeCmd');

interface AnalyzeOptions {
    extensions?: string;
    ignore?: string; // Commander uses the long option name here
    updateSchema?: boolean;
    resetDb?: boolean; // Commander uses camelCase for flags
    // Multi-repository support options
    repositoryId?: string;
    repositoryName?: string;
    repositoryUrl?: string;
    // Git clone options
    branch?: string;
    gitToken?: string;
    keepClone?: boolean;
    // Add Neo4j connection options
    neo4jUrl?: string;
    neo4jUser?: string;
    neo4jPassword?: string;
    neo4jDatabase?: string;
    // JSP/Spring specific options
    jspPaths?: string;
    webflowPaths?: string;
    enableElResolution?: boolean;
    includeTaglibs?: boolean;
    skipIntegration?: boolean;
}



export function registerAnalyzeCommand(program: Command): void {
    program
        .command('analyze <target>')
        .description('Analyze a codebase and store results in Neo4j. Target can be a local directory path or a Git URL (https://github.com/owner/repo).')
        .option('-e, --extensions <exts>', `Comma-separated list of file extensions to include (default: ${config.supportedExtensions.join(',')})`)
        .option('-i, --ignore <patterns>', 'Comma-separated glob patterns to ignore (appends to default ignores)')
        .option('--update-schema', 'Force update Neo4j schema (constraints/indexes) before analysis', false)
        .option('--reset-db', 'WARNING: Deletes ALL nodes and relationships before analysis', false)
        // Multi-repository support options
        .option('--repository-id <id>', 'UUID identifying the repository (required for multi-repository support)')
        .option('--repository-name <name>', 'Display name of the repository')
        .option('--repository-url <url>', 'URL of the repository (e.g., GitHub URL)')
        // Git clone options
        .option('--branch <branch>', 'Branch to checkout when cloning a Git URL')
        .option('--git-token <token>', 'Authentication token for private repositories')
        .option('--keep-clone', 'Keep cloned repository after analysis (default: cleanup)', false)
        // Define Neo4j connection options
        .option('--neo4j-url <url>', 'Neo4j connection URL')
        .option('--neo4j-user <user>', 'Neo4j username')
        .option('--neo4j-password <password>', 'Neo4j password')
        .option('--neo4j-database <database>', 'Neo4j database name')
        .option('--jsp-paths <paths>', 'Comma-separated JSP source paths (supports glob patterns)')
        .option('--webflow-paths <paths>', 'Comma-separated Web Flow definition paths (supports glob patterns)')
        .option('--enable-el-resolution', 'Enable EL expression resolution to Java models')
        .option('--include-taglibs', 'Include tag library analysis')
        .option('--skip-integration', 'Skip cross-layer integration (faster but less comprehensive)')
        .action(async (target: string, options: AnalyzeOptions) => {
            logger.info(`Received analyze command for target: ${target}`);

            // Detect if target is a Git URL or local path
            const isGitTarget = isGitUrl(target);
            let absoluteDirPath: string;
            let cloneResult: CloneResult | undefined;

            if (isGitTarget) {
                logger.info(`Target is a Git URL, cloning repository...`);
                try {
                    cloneResult = await cloneRepository(target, {
                        branch: options.branch,
                        token: options.gitToken,
                        depth: 1, // Shallow clone for faster analysis
                    });
                    absoluteDirPath = cloneResult.localPath;
                    logger.info(`Repository cloned to: ${absoluteDirPath}`);
                } catch (cloneError: any) {
                    logger.error(`Failed to clone repository: ${cloneError.message}`);
                    process.exitCode = 1;
                    return;
                }
            } else {
                // Local directory path
                absoluteDirPath = path.resolve(target);
            }
            if (options.jspPaths) {
                config.jspSpringConfig.jspSourcePaths = options.jspPaths.split(',');
            }

            if (options.webflowPaths) {
                config.jspSpringConfig.webFlowDefinitionPaths = options.webflowPaths.split(',');
            }

            if (options.enableElResolution !== undefined) {
                config.jspSpringConfig.enableELResolution = options.enableElResolution;
            }

            if (options.includeTaglibs !== undefined) {
                config.jspSpringConfig.includeTagLibs = options.includeTaglibs;
            }
            const finalOptions = {
                ...options,
                extensions: options.extensions ? options.extensions.split(',').map(ext => ext.trim().startsWith('.') ? ext.trim() : `.${ext.trim()}`) : config.supportedExtensions,
                ignorePatterns: config.ignorePatterns.concat(options.ignore ? options.ignore.split(',').map(p => p.trim()) : []),
            };

            logger.debug('Effective options:', finalOptions);

            // Pass potential CLI overrides to the Neo4jClient constructor
            const neo4jClient = new Neo4jClient({
                uri: options.neo4jUrl, // Will be undefined if not passed, constructor handles default
                username: options.neo4jUser,
                password: options.neo4jPassword,
                database: options.neo4jDatabase,
            });
            let connected = false;

            try {
                // 1. Initialize Neo4j Connection
                await neo4jClient.initializeDriver('Analyzer'); // Use initializeDriver
                connected = true;
                logger.info('Neo4j connection established.');

                // 2. Handle Schema and Reset Options
                const schemaManager = new SchemaManager(neo4jClient);

                if (finalOptions.resetDb) {
                    logger.warn('Resetting database: Deleting ALL nodes and relationships...');
                    await schemaManager.resetDatabase();
                    logger.info('Database reset complete.');
                    // Schema will be applied next anyway
                }

                if (finalOptions.updateSchema || finalOptions.resetDb) {
                    logger.info('Applying Neo4j schema (constraints and indexes)...');
                    await schemaManager.applySchema(true); // Force update if requested or after reset
                    logger.info('Schema application complete.');
                } else {
                     // Optionally apply schema if it doesn't exist, without forcing
                     // await schemaManager.applySchema(false);
                     logger.debug('Skipping schema update (use --update-schema to force).');
                }


                // 3. Run Analysis
                // AnalyzerService now creates its own Neo4jClient
                const analyzerService = new AnalyzerService();
                logger.info(`Starting analysis of directory: ${absoluteDirPath}`);

                // Determine repository name
                let repoName = options.repositoryName;
                if (!repoName) {
                    if (isGitTarget) {
                        const parsed = parseGitUrl(target);
                        repoName = parsed?.repo || path.basename(absoluteDirPath);
                    } else {
                        repoName = path.basename(absoluteDirPath);
                    }
                }

                // Create analysis context for multi-repository support
                let analysisContext: AnalysisContext | undefined;
                if (options.repositoryId) {
                    analysisContext = {
                        repositoryId: options.repositoryId,
                        repositoryName: repoName,
                        repositoryUrl: options.repositoryUrl || (isGitTarget ? target : undefined),
                        rootDirectory: absoluteDirPath,
                    };
                    logger.info(`Repository context: ${analysisContext.repositoryName} (${analysisContext.repositoryId})`);
                } else {
                    logger.warn('No --repository-id provided. Running without multi-repository support.');
                }

                // Use the analyze method with optional context
                await analyzerService.analyze(absoluteDirPath, analysisContext);

                logger.info('Analysis command finished successfully.');

            } catch (error: any) {
                logger.error(`Analysis command failed: ${error.message}`, { stack: error.stack });
                process.exitCode = 1; // Indicate failure
            } finally {
                // 4. Close Neo4j Connection
                if (connected) {
                    logger.info('Closing Neo4j connection...');
                    await neo4jClient.closeDriver('Analyzer'); // Use closeDriver
                    logger.info('Neo4j connection closed.');
                }

                // 5. Cleanup cloned repository if not keeping
                if (cloneResult && cloneResult.isTemporary && !options.keepClone) {
                    logger.info('Cleaning up cloned repository...');
                    await cleanupRepository(cloneResult.localPath);
                }
            }
        });
}
