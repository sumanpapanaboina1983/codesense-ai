// src/analyzer/analyzer-service.ts
import path from 'path';
import { FileScanner, FileInfo, ModuleAwareFileInfo } from '../scanner/file-scanner.js';
import { Parser } from './parser.js';
import { RelationshipResolver } from './relationship-resolver.js';
import { StorageManager } from './storage-manager.js';
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
// Removed setTimeout import

const logger = createContextLogger('AnalyzerService');

/**
 * Orchestrates the code analysis process: scanning, parsing, resolving, and storing.
 */
export class AnalyzerService {
    private parser: Parser;
    private storageManager: StorageManager;
    private neo4jClient: Neo4jClient;

    constructor() {
        this.parser = new Parser();
        // Instantiate Neo4jClient without overrides to use config defaults
        this.neo4jClient = new Neo4jClient();
        // Pass the client instance to StorageManager
        this.storageManager = new StorageManager(this.neo4jClient);
        logger.info('AnalyzerService initialized.');
    }

    /**
     * Runs the full analysis pipeline for a given directory.
     * Assumes database is cleared externally (e.g., via test setup).
     * @param directory - The root directory to analyze.
     * @param context - Optional analysis context for multi-repository support.
     */
    async analyze(directory: string, context?: AnalysisContext): Promise<void> {
        const repoInfo = context ? ` (Repository: ${context.repositoryName}, ID: ${context.repositoryId})` : '';
        logger.info(`Starting analysis for directory: ${directory}${repoInfo}`);
        const absoluteDirectory = path.resolve(directory);
        let scanner: FileScanner;

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

            // 1. Scan Files
            logger.info('Scanning files...');
            const files: FileInfo[] = await scanner.scan(); // No argument needed
            if (files.length === 0) {
                logger.warn('No files found to analyze.');
                return;
            }
            logger.info(`Found ${files.length} files.`);

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
            await this.parser.parseFiles(files, context);

            // 3. Collect Pass 1 Results
            logger.info('Collecting Pass 1 results...');
            const { allNodes: pass1Nodes, allRelationships: pass1Relationships } = await this.parser.collectResults();
            logger.info(`Collected ${pass1Nodes.length} nodes and ${pass1Relationships.length} relationships from Pass 1.`);

            if (pass1Nodes.length === 0) {
                logger.warn('No nodes were generated during Pass 1. Aborting further analysis.');
                return;
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
            // Ensure driver is initialized before storing
            await this.neo4jClient.initializeDriver('AnalyzerService-Store');

            // --- Database clearing is now handled by beforeEach in tests ---

            await this.storageManager.saveNodesBatch(finalNodes);

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