// src/analyzer/entry-point-detector.ts
/**
 * Detects entry points (REST endpoints, GraphQL operations, event handlers, etc.)
 * from analyzed code.
 */

import winston from 'winston';
import {
    AstNode,
    RestEndpointNode,
    GraphQLOperationNode,
    EventHandlerNode,
    ScheduledTaskNode,
    CLICommandNode,
    HttpMethod,
    GraphQLOperationType,
    ParameterInfo,
    CLIOption,
    RelationshipInfo,
    AnnotationInfo,
} from './types.js';
import { DetectedFramework } from './types.js';

// =============================================================================
// REST Endpoint Detection Patterns
// =============================================================================

interface RestAnnotationPattern {
    /** Framework name */
    framework: string;
    /** Annotation/decorator pattern (regex) */
    pattern: RegExp;
    /** HTTP method (or extract from pattern) */
    method?: HttpMethod | 'EXTRACT';
    /** Path extraction group index */
    pathGroup?: number;
}

const REST_PATTERNS: RestAnnotationPattern[] = [
    // Spring Boot / Spring MVC
    { framework: 'Spring', pattern: /@GetMapping\s*\(\s*["']?([^"')]+)["']?\s*\)/i, method: 'GET', pathGroup: 1 },
    { framework: 'Spring', pattern: /@PostMapping\s*\(\s*["']?([^"')]+)["']?\s*\)/i, method: 'POST', pathGroup: 1 },
    { framework: 'Spring', pattern: /@PutMapping\s*\(\s*["']?([^"')]+)["']?\s*\)/i, method: 'PUT', pathGroup: 1 },
    { framework: 'Spring', pattern: /@DeleteMapping\s*\(\s*["']?([^"')]+)["']?\s*\)/i, method: 'DELETE', pathGroup: 1 },
    { framework: 'Spring', pattern: /@PatchMapping\s*\(\s*["']?([^"')]+)["']?\s*\)/i, method: 'PATCH', pathGroup: 1 },
    { framework: 'Spring', pattern: /@RequestMapping\s*\([^)]*value\s*=\s*["']([^"']+)["'][^)]*method\s*=\s*RequestMethod\.(\w+)/i, method: 'EXTRACT', pathGroup: 1 },
    { framework: 'Spring', pattern: /@RequestMapping\s*\(\s*["']([^"']+)["']\s*\)/i, method: 'GET', pathGroup: 1 },

    // NestJS
    { framework: 'NestJS', pattern: /@Get\s*\(\s*['"]?([^'")\s]*)['"]?\s*\)/i, method: 'GET', pathGroup: 1 },
    { framework: 'NestJS', pattern: /@Post\s*\(\s*['"]?([^'")\s]*)['"]?\s*\)/i, method: 'POST', pathGroup: 1 },
    { framework: 'NestJS', pattern: /@Put\s*\(\s*['"]?([^'")\s]*)['"]?\s*\)/i, method: 'PUT', pathGroup: 1 },
    { framework: 'NestJS', pattern: /@Delete\s*\(\s*['"]?([^'")\s]*)['"]?\s*\)/i, method: 'DELETE', pathGroup: 1 },
    { framework: 'NestJS', pattern: /@Patch\s*\(\s*['"]?([^'")\s]*)['"]?\s*\)/i, method: 'PATCH', pathGroup: 1 },

    // FastAPI (Python)
    { framework: 'FastAPI', pattern: /@app\.get\s*\(\s*["']([^"']+)["']/i, method: 'GET', pathGroup: 1 },
    { framework: 'FastAPI', pattern: /@app\.post\s*\(\s*["']([^"']+)["']/i, method: 'POST', pathGroup: 1 },
    { framework: 'FastAPI', pattern: /@app\.put\s*\(\s*["']([^"']+)["']/i, method: 'PUT', pathGroup: 1 },
    { framework: 'FastAPI', pattern: /@app\.delete\s*\(\s*["']([^"']+)["']/i, method: 'DELETE', pathGroup: 1 },
    { framework: 'FastAPI', pattern: /@router\.get\s*\(\s*["']([^"']+)["']/i, method: 'GET', pathGroup: 1 },
    { framework: 'FastAPI', pattern: /@router\.post\s*\(\s*["']([^"']+)["']/i, method: 'POST', pathGroup: 1 },

    // Flask (Python)
    { framework: 'Flask', pattern: /@app\.route\s*\(\s*["']([^"']+)["'][^)]*methods\s*=\s*\[["'](\w+)["']/i, method: 'EXTRACT', pathGroup: 1 },
    { framework: 'Flask', pattern: /@app\.route\s*\(\s*["']([^"']+)["']\s*\)/i, method: 'GET', pathGroup: 1 },
    { framework: 'Flask', pattern: /@blueprint\.route\s*\(\s*["']([^"']+)["']/i, method: 'GET', pathGroup: 1 },

    // Express.js
    { framework: 'Express', pattern: /app\.get\s*\(\s*['"]([^'"]+)['"]/i, method: 'GET', pathGroup: 1 },
    { framework: 'Express', pattern: /app\.post\s*\(\s*['"]([^'"]+)['"]/i, method: 'POST', pathGroup: 1 },
    { framework: 'Express', pattern: /app\.put\s*\(\s*['"]([^'"]+)['"]/i, method: 'PUT', pathGroup: 1 },
    { framework: 'Express', pattern: /app\.delete\s*\(\s*['"]([^'"]+)['"]/i, method: 'DELETE', pathGroup: 1 },
    { framework: 'Express', pattern: /router\.get\s*\(\s*['"]([^'"]+)['"]/i, method: 'GET', pathGroup: 1 },
    { framework: 'Express', pattern: /router\.post\s*\(\s*['"]([^'"]+)['"]/i, method: 'POST', pathGroup: 1 },

    // Gin (Go)
    { framework: 'Gin', pattern: /\.GET\s*\(\s*["']([^"']+)["']/i, method: 'GET', pathGroup: 1 },
    { framework: 'Gin', pattern: /\.POST\s*\(\s*["']([^"']+)["']/i, method: 'POST', pathGroup: 1 },
    { framework: 'Gin', pattern: /\.PUT\s*\(\s*["']([^"']+)["']/i, method: 'PUT', pathGroup: 1 },
    { framework: 'Gin', pattern: /\.DELETE\s*\(\s*["']([^"']+)["']/i, method: 'DELETE', pathGroup: 1 },

    // ASP.NET Core
    { framework: 'ASP.NET', pattern: /\[HttpGet\s*\(\s*["']?([^"'\])]*)["']?\s*\)\]/i, method: 'GET', pathGroup: 1 },
    { framework: 'ASP.NET', pattern: /\[HttpPost\s*\(\s*["']?([^"'\])]*)["']?\s*\)\]/i, method: 'POST', pathGroup: 1 },
    { framework: 'ASP.NET', pattern: /\[HttpPut\s*\(\s*["']?([^"'\])]*)["']?\s*\)\]/i, method: 'PUT', pathGroup: 1 },
    { framework: 'ASP.NET', pattern: /\[HttpDelete\s*\(\s*["']?([^"'\])]*)["']?\s*\)\]/i, method: 'DELETE', pathGroup: 1 },
    { framework: 'ASP.NET', pattern: /\[Route\s*\(\s*["']([^"']+)["']\s*\)\]/i, method: 'GET', pathGroup: 1 },

    // Django (urls.py pattern matching)
    { framework: 'Django', pattern: /path\s*\(\s*['"]([^'"]+)['"]/i, method: 'GET', pathGroup: 1 },
];

// =============================================================================
// GraphQL Detection Patterns
// =============================================================================

interface GraphQLPattern {
    framework: string;
    pattern: RegExp;
    operationType: GraphQLOperationType | 'EXTRACT';
    nameGroup?: number;
}

const GRAPHQL_PATTERNS: GraphQLPattern[] = [
    // Apollo Server / type-graphql
    { framework: 'Apollo', pattern: /@Query\s*\(\s*\)\s*(?:async\s+)?(\w+)/i, operationType: 'Query', nameGroup: 1 },
    { framework: 'Apollo', pattern: /@Mutation\s*\(\s*\)\s*(?:async\s+)?(\w+)/i, operationType: 'Mutation', nameGroup: 1 },
    { framework: 'Apollo', pattern: /@Subscription\s*\(\s*\)\s*(?:async\s+)?(\w+)/i, operationType: 'Subscription', nameGroup: 1 },

    // NestJS GraphQL
    { framework: 'NestJS', pattern: /@Query\s*\([^)]*\)\s*(?:async\s+)?(\w+)/i, operationType: 'Query', nameGroup: 1 },
    { framework: 'NestJS', pattern: /@Mutation\s*\([^)]*\)\s*(?:async\s+)?(\w+)/i, operationType: 'Mutation', nameGroup: 1 },

    // Spring GraphQL
    { framework: 'Spring', pattern: /@QueryMapping\s*(?:\([^)]*\))?\s*(?:public\s+)?(?:\w+\s+)?(\w+)/i, operationType: 'Query', nameGroup: 1 },
    { framework: 'Spring', pattern: /@MutationMapping\s*(?:\([^)]*\))?\s*(?:public\s+)?(?:\w+\s+)?(\w+)/i, operationType: 'Mutation', nameGroup: 1 },
    { framework: 'Spring', pattern: /@SubscriptionMapping\s*(?:\([^)]*\))?\s*(?:public\s+)?(?:\w+\s+)?(\w+)/i, operationType: 'Subscription', nameGroup: 1 },
];

// =============================================================================
// Event Handler Detection Patterns
// =============================================================================

interface EventPattern {
    framework: string;
    pattern: RegExp;
    eventSource: string;
    eventTypeGroup?: number;
}

const EVENT_PATTERNS: EventPattern[] = [
    // Spring Events
    { framework: 'Spring', pattern: /@EventListener\s*\(([^)]+)\)/i, eventSource: 'Spring Events', eventTypeGroup: 1 },
    { framework: 'Spring', pattern: /@KafkaListener\s*\([^)]*topics?\s*=\s*["']([^"']+)["']/i, eventSource: 'Kafka', eventTypeGroup: 1 },
    { framework: 'Spring', pattern: /@RabbitListener\s*\([^)]*queues?\s*=\s*["']([^"']+)["']/i, eventSource: 'RabbitMQ', eventTypeGroup: 1 },
    { framework: 'Spring', pattern: /@JmsListener\s*\([^)]*destination\s*=\s*["']([^"']+)["']/i, eventSource: 'JMS', eventTypeGroup: 1 },
    { framework: 'Spring', pattern: /@SqsListener\s*\([^)]*value\s*=\s*["']([^"']+)["']/i, eventSource: 'AWS SQS', eventTypeGroup: 1 },

    // Node.js EventEmitter
    { framework: 'Node.js', pattern: /\.on\s*\(\s*['"]([^'"]+)['"]/i, eventSource: 'EventEmitter', eventTypeGroup: 1 },
    { framework: 'Node.js', pattern: /\.addEventListener\s*\(\s*['"]([^'"]+)['"]/i, eventSource: 'EventEmitter', eventTypeGroup: 1 },

    // Celery (Python)
    { framework: 'Celery', pattern: /@(?:app\.)?task\s*\(/i, eventSource: 'Celery' },
    { framework: 'Celery', pattern: /@shared_task\s*\(/i, eventSource: 'Celery' },

    // NestJS
    { framework: 'NestJS', pattern: /@EventPattern\s*\(\s*['"]([^'"]+)['"]/i, eventSource: 'Microservice', eventTypeGroup: 1 },
    { framework: 'NestJS', pattern: /@MessagePattern\s*\(\s*['"]([^'"]+)['"]/i, eventSource: 'Microservice', eventTypeGroup: 1 },
];

// =============================================================================
// Scheduled Task Detection Patterns
// =============================================================================

interface ScheduledPattern {
    framework: string;
    pattern: RegExp;
    scheduleType: 'cron' | 'fixedRate' | 'fixedDelay' | 'interval';
    valueGroup?: number;
}

const SCHEDULED_PATTERNS: ScheduledPattern[] = [
    // Spring @Scheduled
    { framework: 'Spring', pattern: /@Scheduled\s*\([^)]*cron\s*=\s*["']([^"']+)["']/i, scheduleType: 'cron', valueGroup: 1 },
    { framework: 'Spring', pattern: /@Scheduled\s*\([^)]*fixedRate\s*=\s*(\d+)/i, scheduleType: 'fixedRate', valueGroup: 1 },
    { framework: 'Spring', pattern: /@Scheduled\s*\([^)]*fixedDelay\s*=\s*(\d+)/i, scheduleType: 'fixedDelay', valueGroup: 1 },

    // NestJS @Cron
    { framework: 'NestJS', pattern: /@Cron\s*\(\s*['"]([^'"]+)['"]/i, scheduleType: 'cron', valueGroup: 1 },
    { framework: 'NestJS', pattern: /@Interval\s*\(\s*(\d+)\s*\)/i, scheduleType: 'interval', valueGroup: 1 },

    // Python APScheduler
    { framework: 'APScheduler', pattern: /@scheduler\.scheduled_job\s*\(\s*['"]cron['"]\s*,/i, scheduleType: 'cron' },
    { framework: 'APScheduler', pattern: /@scheduler\.scheduled_job\s*\(\s*['"]interval['"]\s*,/i, scheduleType: 'interval' },

    // Celery Beat
    { framework: 'Celery', pattern: /schedule\s*=\s*crontab\s*\(/i, scheduleType: 'cron' },

    // Go cron
    { framework: 'Go', pattern: /c\.AddFunc\s*\(\s*["']([^"']+)["']/i, scheduleType: 'cron', valueGroup: 1 },
];

// =============================================================================
// CLI Command Detection Patterns
// =============================================================================

interface CLIPattern {
    framework: string;
    pattern: RegExp;
    commandGroup?: number;
}

const CLI_PATTERNS: CLIPattern[] = [
    // Spring Boot CommandLineRunner
    { framework: 'Spring', pattern: /implements\s+CommandLineRunner/i },
    { framework: 'Spring', pattern: /implements\s+ApplicationRunner/i },

    // Python Click
    { framework: 'Click', pattern: /@click\.command\s*\(\s*(?:['"]([^'"]+)['"])?\s*\)/i, commandGroup: 1 },
    { framework: 'Click', pattern: /@click\.group\s*\(\s*(?:['"]([^'"]+)['"])?\s*\)/i, commandGroup: 1 },

    // Python argparse
    { framework: 'argparse', pattern: /parser\.add_subparsers\s*\(/i },
    { framework: 'argparse', pattern: /add_parser\s*\(\s*['"]([^'"]+)['"]/i, commandGroup: 1 },

    // Node.js Commander
    { framework: 'Commander', pattern: /\.command\s*\(\s*['"]([^'"]+)['"]/i, commandGroup: 1 },
    { framework: 'Commander', pattern: /program\.name\s*\(\s*['"]([^'"]+)['"]/i, commandGroup: 1 },

    // Go Cobra
    { framework: 'Cobra', pattern: /&cobra\.Command\s*{\s*Use:\s*["']([^"']+)["']/i, commandGroup: 1 },
];

// =============================================================================
// Entry Point Detector Class
// =============================================================================

export class EntryPointDetector {
    private logger: winston.Logger;
    private detectedFrameworks: DetectedFramework[];

    constructor(logger: winston.Logger, detectedFrameworks: DetectedFramework[] = []) {
        this.logger = logger;
        this.detectedFrameworks = detectedFrameworks;
    }

    /**
     * Detect all entry points from a list of AST nodes.
     */
    detectEntryPoints(
        nodes: AstNode[],
        sourceTexts: Map<string, string>
    ): EntryPointDetectionResult {
        const restEndpoints: RestEndpointNode[] = [];
        const graphqlOperations: GraphQLOperationNode[] = [];
        const eventHandlers: EventHandlerNode[] = [];
        const scheduledTasks: ScheduledTaskNode[] = [];
        const cliCommands: CLICommandNode[] = [];
        const relationships: RelationshipInfo[] = [];

        // Build class-to-base-path map for controllers
        const controllerBasePaths = this.extractControllerBasePaths(nodes, sourceTexts);

        for (const node of nodes) {
            if (!this.isMethodOrFunction(node)) continue;

            const sourceText = sourceTexts.get(node.filePath);
            if (!sourceText) continue;

            // Extract the relevant portion of source for this node
            const nodeText = this.extractNodeText(sourceText, node);

            // Detect REST endpoints
            const restResult = this.detectRestEndpoint(node, nodeText, controllerBasePaths);
            if (restResult) {
                restEndpoints.push(restResult.endpoint);
                relationships.push(restResult.relationship);
            }

            // Detect GraphQL operations
            const graphqlResult = this.detectGraphQLOperation(node, nodeText);
            if (graphqlResult) {
                graphqlOperations.push(graphqlResult.operation);
                relationships.push(graphqlResult.relationship);
            }

            // Detect event handlers
            const eventResult = this.detectEventHandler(node, nodeText);
            if (eventResult) {
                eventHandlers.push(eventResult.handler);
                relationships.push(eventResult.relationship);
            }

            // Detect scheduled tasks
            const scheduledResult = this.detectScheduledTask(node, nodeText);
            if (scheduledResult) {
                scheduledTasks.push(scheduledResult.task);
                relationships.push(scheduledResult.relationship);
            }

            // Detect CLI commands
            const cliResult = this.detectCLICommand(node, nodeText);
            if (cliResult) {
                cliCommands.push(cliResult.command);
                relationships.push(cliResult.relationship);
            }
        }

        this.logger.info('Entry point detection complete', {
            restEndpoints: restEndpoints.length,
            graphqlOperations: graphqlOperations.length,
            eventHandlers: eventHandlers.length,
            scheduledTasks: scheduledTasks.length,
            cliCommands: cliCommands.length,
        });

        return {
            restEndpoints,
            graphqlOperations,
            eventHandlers,
            scheduledTasks,
            cliCommands,
            relationships,
        };
    }

    /**
     * Extract base paths from controller annotations.
     */
    private extractControllerBasePaths(
        nodes: AstNode[],
        sourceTexts: Map<string, string>
    ): Map<string, string> {
        const basePaths = new Map<string, string>();

        for (const node of nodes) {
            if (!this.isClassLike(node)) continue;

            const sourceText = sourceTexts.get(node.filePath);
            if (!sourceText) continue;

            const nodeText = this.extractNodeText(sourceText, node);

            // Look for @RequestMapping, @Controller, @RestController base paths
            const patterns = [
                /@RequestMapping\s*\(\s*["']([^"']+)["']\s*\)/i,
                /@RequestMapping\s*\([^)]*value\s*=\s*["']([^"']+)["']/i,
                /@Controller\s*\(\s*["']([^"']+)["']\s*\)/i,
                /@RestController\s*\(\s*["']([^"']+)["']\s*\)/i,
            ];

            for (const pattern of patterns) {
                const match = nodeText.match(pattern);
                if (match && match[1]) {
                    basePaths.set(node.entityId, match[1]);
                    break;
                }
            }
        }

        return basePaths;
    }

    /**
     * Detect REST endpoint from a method/function.
     */
    private detectRestEndpoint(
        node: AstNode,
        nodeText: string,
        controllerBasePaths: Map<string, string>
    ): { endpoint: RestEndpointNode; relationship: RelationshipInfo } | null {
        for (const pattern of REST_PATTERNS) {
            const match = nodeText.match(pattern.pattern);
            if (match) {
                let method: HttpMethod = pattern.method === 'EXTRACT'
                    ? this.extractHttpMethod(match[2] || 'GET')
                    : pattern.method!;

                let path = pattern.pathGroup ? (match[pattern.pathGroup] || '/') : '/';

                // Add base path from controller
                const basePath = node.parentId ? controllerBasePaths.get(node.parentId) : undefined;
                const fullPath = this.combinePaths(basePath, path);

                // Extract path parameters
                const pathParams = this.extractPathParameters(fullPath);

                const endpointId = this.generateEntityId('rest_endpoint', `${node.filePath}:${method}:${fullPath}`);

                const endpoint: RestEndpointNode = {
                    id: endpointId,
                    entityId: endpointId,
                    kind: 'RestEndpoint',
                    name: `${method} ${fullPath}`,
                    filePath: node.filePath,
                    language: node.language,
                    startLine: node.startLine,
                    endLine: node.endLine,
                    startColumn: node.startColumn,
                    endColumn: node.endColumn,
                    createdAt: new Date().toISOString(),
                    properties: {
                        httpMethod: method,
                        path,
                        fullPath,
                        pathParameters: pathParams,
                        framework: pattern.framework,
                        handlerMethodId: node.entityId,
                        handlerClassId: node.parentId,
                    },
                };

                const relationship: RelationshipInfo = {
                    id: this.generateEntityId('exposes_endpoint', `${node.entityId}:${endpointId}`),
                    entityId: this.generateEntityId('exposes_endpoint', `${node.entityId}:${endpointId}`),
                    type: 'EXPOSES_ENDPOINT',
                    sourceId: node.entityId,
                    targetId: endpointId,
                    createdAt: new Date().toISOString(),
                };

                return { endpoint, relationship };
            }
        }

        return null;
    }

    /**
     * Detect GraphQL operation from a method/function.
     */
    private detectGraphQLOperation(
        node: AstNode,
        nodeText: string
    ): { operation: GraphQLOperationNode; relationship: RelationshipInfo } | null {
        for (const pattern of GRAPHQL_PATTERNS) {
            const match = nodeText.match(pattern.pattern);
            if (match) {
                const operationType = pattern.operationType as GraphQLOperationType;
                const operationName = pattern.nameGroup ? (match[pattern.nameGroup] || node.name) : node.name;

                const operationId = this.generateEntityId('graphql_operation', `${node.filePath}:${operationType}:${operationName}`);

                const operation: GraphQLOperationNode = {
                    id: operationId,
                    entityId: operationId,
                    kind: 'GraphQLOperation',
                    name: `${operationType} ${operationName}`,
                    filePath: node.filePath,
                    language: node.language,
                    startLine: node.startLine,
                    endLine: node.endLine,
                    startColumn: node.startColumn,
                    endColumn: node.endColumn,
                    createdAt: new Date().toISOString(),
                    properties: {
                        operationType,
                        operationName,
                        arguments: [],
                        returnType: node.returnType || 'unknown',
                        isNullable: true,
                        isList: false,
                        framework: pattern.framework,
                        resolverMethodId: node.entityId,
                        resolverClassId: node.parentId,
                    },
                };

                const relationship: RelationshipInfo = {
                    id: this.generateEntityId('resolves_operation', `${node.entityId}:${operationId}`),
                    entityId: this.generateEntityId('resolves_operation', `${node.entityId}:${operationId}`),
                    type: 'RESOLVES_OPERATION',
                    sourceId: node.entityId,
                    targetId: operationId,
                    createdAt: new Date().toISOString(),
                };

                return { operation, relationship };
            }
        }

        return null;
    }

    /**
     * Detect event handler from a method/function.
     */
    private detectEventHandler(
        node: AstNode,
        nodeText: string
    ): { handler: EventHandlerNode; relationship: RelationshipInfo } | null {
        for (const pattern of EVENT_PATTERNS) {
            const match = nodeText.match(pattern.pattern);
            if (match) {
                const eventType = pattern.eventTypeGroup ? (match[pattern.eventTypeGroup] || node.name) : node.name;

                const handlerId = this.generateEntityId('event_handler', `${node.filePath}:${pattern.eventSource}:${eventType}`);

                const handler: EventHandlerNode = {
                    id: handlerId,
                    entityId: handlerId,
                    kind: 'EventHandler',
                    name: `${pattern.eventSource}: ${eventType}`,
                    filePath: node.filePath,
                    language: node.language,
                    startLine: node.startLine,
                    endLine: node.endLine,
                    startColumn: node.startColumn,
                    endColumn: node.endColumn,
                    createdAt: new Date().toISOString(),
                    properties: {
                        eventType,
                        eventSource: pattern.eventSource,
                        isAsync: node.isAsync || false,
                        framework: pattern.framework,
                        handlerMethodId: node.entityId,
                        handlerClassId: node.parentId,
                    },
                };

                const relationship: RelationshipInfo = {
                    id: this.generateEntityId('handles_event', `${node.entityId}:${handlerId}`),
                    entityId: this.generateEntityId('handles_event', `${node.entityId}:${handlerId}`),
                    type: 'HANDLES_EVENT',
                    sourceId: node.entityId,
                    targetId: handlerId,
                    createdAt: new Date().toISOString(),
                };

                return { handler, relationship };
            }
        }

        return null;
    }

    /**
     * Detect scheduled task from a method/function.
     */
    private detectScheduledTask(
        node: AstNode,
        nodeText: string
    ): { task: ScheduledTaskNode; relationship: RelationshipInfo } | null {
        for (const pattern of SCHEDULED_PATTERNS) {
            const match = nodeText.match(pattern.pattern);
            if (match) {
                const scheduleValue = pattern.valueGroup ? match[pattern.valueGroup] : undefined;

                const taskId = this.generateEntityId('scheduled_task', `${node.filePath}:${node.name}`);

                const task: ScheduledTaskNode = {
                    id: taskId,
                    entityId: taskId,
                    kind: 'ScheduledTask',
                    name: `Scheduled: ${node.name}`,
                    filePath: node.filePath,
                    language: node.language,
                    startLine: node.startLine,
                    endLine: node.endLine,
                    startColumn: node.startColumn,
                    endColumn: node.endColumn,
                    createdAt: new Date().toISOString(),
                    properties: {
                        scheduleType: pattern.scheduleType,
                        cronExpression: pattern.scheduleType === 'cron' ? scheduleValue : undefined,
                        fixedRate: pattern.scheduleType === 'fixedRate' ? parseInt(scheduleValue || '0') : undefined,
                        fixedDelay: pattern.scheduleType === 'fixedDelay' ? parseInt(scheduleValue || '0') : undefined,
                        framework: pattern.framework,
                        taskMethodId: node.entityId,
                        taskClassId: node.parentId,
                        isEnabled: true,
                    },
                };

                const relationship: RelationshipInfo = {
                    id: this.generateEntityId('scheduled_by', `${node.entityId}:${taskId}`),
                    entityId: this.generateEntityId('scheduled_by', `${node.entityId}:${taskId}`),
                    type: 'SCHEDULED_BY',
                    sourceId: node.entityId,
                    targetId: taskId,
                    createdAt: new Date().toISOString(),
                };

                return { task, relationship };
            }
        }

        return null;
    }

    /**
     * Detect CLI command from a method/function/class.
     */
    private detectCLICommand(
        node: AstNode,
        nodeText: string
    ): { command: CLICommandNode; relationship: RelationshipInfo } | null {
        for (const pattern of CLI_PATTERNS) {
            const match = nodeText.match(pattern.pattern);
            if (match) {
                const commandName = pattern.commandGroup ? (match[pattern.commandGroup] || node.name) : node.name;

                const commandId = this.generateEntityId('cli_command', `${node.filePath}:${commandName}`);

                const command: CLICommandNode = {
                    id: commandId,
                    entityId: commandId,
                    kind: 'CLICommand',
                    name: `CLI: ${commandName}`,
                    filePath: node.filePath,
                    language: node.language,
                    startLine: node.startLine,
                    endLine: node.endLine,
                    startColumn: node.startColumn,
                    endColumn: node.endColumn,
                    createdAt: new Date().toISOString(),
                    properties: {
                        commandName,
                        arguments: [],
                        framework: pattern.framework,
                        handlerMethodId: node.entityId,
                        handlerClassId: node.parentId,
                        isSubcommand: false,
                    },
                };

                const relationship: RelationshipInfo = {
                    id: this.generateEntityId('invoked_by_cli', `${node.entityId}:${commandId}`),
                    entityId: this.generateEntityId('invoked_by_cli', `${node.entityId}:${commandId}`),
                    type: 'INVOKED_BY_CLI',
                    sourceId: node.entityId,
                    targetId: commandId,
                    createdAt: new Date().toISOString(),
                };

                return { command, relationship };
            }
        }

        return null;
    }

    // Helper methods

    private isMethodOrFunction(node: AstNode): boolean {
        return [
            'Function', 'Method', 'TSFunction',
            'JavaMethod', 'GoFunction', 'GoMethod',
            'CSharpMethod', 'CppMethod', 'CFunction',
        ].includes(node.kind);
    }

    private isClassLike(node: AstNode): boolean {
        return [
            'Class', 'JavaClass', 'CppClass', 'CSharpClass', 'GoStruct',
        ].includes(node.kind);
    }

    private extractNodeText(sourceText: string, node: AstNode): string {
        const lines = sourceText.split('\n');
        // Include some context before the node (for annotations)
        const startLine = Math.max(0, node.startLine - 10);
        const endLine = Math.min(lines.length, node.endLine + 1);
        return lines.slice(startLine, endLine).join('\n');
    }

    private extractHttpMethod(methodStr: string): HttpMethod {
        const upper = methodStr.toUpperCase();
        if (['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS', 'TRACE'].includes(upper)) {
            return upper as HttpMethod;
        }
        return 'GET';
    }

    private combinePaths(basePath: string | undefined, path: string): string {
        if (!basePath) return path.startsWith('/') ? path : `/${path}`;
        const base = basePath.endsWith('/') ? basePath.slice(0, -1) : basePath;
        const sub = path.startsWith('/') ? path : `/${path}`;
        return `${base}${sub}`;
    }

    private extractPathParameters(path: string): string[] {
        const params: string[] = [];
        // Match {param}, :param, <param>
        const matches = path.matchAll(/\{(\w+)\}|:(\w+)|<(\w+)>/g);
        for (const match of matches) {
            params.push(match[1] || match[2] || match[3]);
        }
        return params;
    }

    private generateEntityId(prefix: string, identifier: string): string {
        // Simple hash function for consistent IDs
        let hash = 0;
        const str = `${prefix}:${identifier}`;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return `${prefix}_${Math.abs(hash).toString(16)}`;
    }
}

// =============================================================================
// Types
// =============================================================================

export interface EntryPointDetectionResult {
    restEndpoints: RestEndpointNode[];
    graphqlOperations: GraphQLOperationNode[];
    eventHandlers: EventHandlerNode[];
    scheduledTasks: ScheduledTaskNode[];
    cliCommands: CLICommandNode[];
    relationships: RelationshipInfo[];
}

// =============================================================================
// Convenience Functions
// =============================================================================

export function createEntryPointDetector(
    logger: winston.Logger,
    detectedFrameworks?: DetectedFramework[]
): EntryPointDetector {
    return new EntryPointDetector(logger, detectedFrameworks);
}
