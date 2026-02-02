// src/analyzer/feature-detector.ts
/**
 * Feature Detector
 * Discovers end-to-end customer-facing features by tracing:
 * UI Routes -> API Endpoints -> Services -> Database Entities
 *
 * Features are auto-inferred from route paths and component names,
 * with support for user overrides.
 */

import winston from 'winston';
import { Neo4jClient } from '../database/neo4j-client.js';
import {
    AstNode,
    FeatureNode,
    FeatureDiscoveryResult,
    FeatureCategory,
    FeatureComplexity,
    RelationshipInfo,
    UIRouteNode,
    UIPageNode,
    RestEndpointNode,
} from './types.js';

// =============================================================================
// Feature Detection Queries
// =============================================================================

const FEATURE_QUERIES = {
    // Trace UI Route to API endpoints via component calls
    TRACE_UI_TO_API: `
        MATCH (route:UIRoute)-[:RENDERS_PAGE]->(comp)
        MATCH (comp)-[:CALLS*1..3]->(endpoint:RestEndpoint)
        WHERE route.entityId IN $routeIds
        RETURN route.entityId as routeId, route.path as routePath,
               collect(DISTINCT {
                   endpointId: endpoint.entityId,
                   path: endpoint.path,
                   method: endpoint.httpMethod
               }) as endpoints
    `,

    // Trace UI Page to API endpoints
    TRACE_PAGE_TO_API: `
        MATCH (page:UIPage)-[:RENDERS_PAGE]->(file:File)
        MATCH (file)-[:CONTAINS|DEFINES_FUNCTION*1..2]->(fn)
        MATCH (fn)-[:CALLS*1..3]->(endpoint:RestEndpoint)
        WHERE page.entityId IN $pageIds
        RETURN page.entityId as pageId, page.routePath as routePath,
               collect(DISTINCT {
                   endpointId: endpoint.entityId,
                   path: endpoint.path,
                   method: endpoint.httpMethod
               }) as endpoints
    `,

    // Trace API endpoint to services
    TRACE_API_TO_SERVICE: `
        MATCH (endpoint:RestEndpoint)<-[:EXPOSES_ENDPOINT]-(handler)
        MATCH (handler)-[:CALLS*1..3]->(service)
        WHERE endpoint.entityId IN $endpointIds
          AND (service.stereotype = 'Service' OR service:SpringService)
        RETURN endpoint.entityId as endpointId,
               collect(DISTINCT {
                   serviceId: service.entityId,
                   serviceName: service.name,
                   stereotype: service.stereotype
               }) as services
    `,

    // Trace service to repositories/database entities
    TRACE_SERVICE_TO_DATA: `
        MATCH (service)-[:CALLS*1..3]->(repo)
        WHERE service.entityId IN $serviceIds
          AND (repo.stereotype IN ['Repository', 'Entity'] OR repo:SQLTable)
        RETURN service.entityId as serviceId,
               collect(DISTINCT {
                   entityId: repo.entityId,
                   entityName: repo.name,
                   entityType: CASE
                       WHEN repo:SQLTable THEN 'table'
                       WHEN repo.stereotype = 'Entity' THEN 'entity'
                       ELSE 'repository'
                   END
               }) as dataEntities
    `,

    // Get all UI routes for a repository
    GET_UI_ROUTES: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[*1..3]->(route:UIRoute)
        RETURN route.entityId as entityId, route.path as path,
               route.fullPath as fullPath, route.framework as framework,
               route.componentName as componentName, route.requiresAuth as requiresAuth
    `,

    // Get all UI pages for a repository
    GET_UI_PAGES: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[*1..3]->(page:UIPage)
        RETURN page.entityId as entityId, page.routePath as routePath,
               page.framework as framework, page.isLayout as isLayout
        ORDER BY page.routePath
    `,

    // Get unmapped API endpoints (not connected to any UI)
    UNMAPPED_ENDPOINTS: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[*1..3]->(endpoint:RestEndpoint)
        WHERE NOT EXISTS {
            MATCH (route:UIRoute)-[:ROUTE_CALLS_API]->(endpoint)
        } AND NOT EXISTS {
            MATCH (page:UIPage)-[:ROUTE_CALLS_API]->(endpoint)
        }
        RETURN endpoint.entityId as entityId, endpoint.path as path, endpoint.httpMethod as method
    `,

    // Get unmapped UI routes (not connected to any API)
    UNMAPPED_ROUTES: `
        MATCH (r:Repository {repositoryId: $repositoryId})-[:BELONGS_TO]-(f:File)
        MATCH (f)-[*1..3]->(route:UIRoute)
        WHERE NOT EXISTS {
            MATCH (route)-[:ROUTE_CALLS_API]->(:RestEndpoint)
        }
        RETURN route.entityId as entityId, route.path as path
    `,
};

// =============================================================================
// Feature Name Inference
// =============================================================================

interface FeatureNameRule {
    pattern: RegExp;
    name: (match: RegExpMatchArray) => string;
    confidence: number;
}

const FEATURE_NAME_RULES: FeatureNameRule[] = [
    // User management patterns
    { pattern: /\/users?(\/|$)/i, name: () => 'User Management', confidence: 0.9 },
    { pattern: /\/profile(\/|$)/i, name: () => 'User Profile', confidence: 0.9 },
    { pattern: /\/account(\/|$)/i, name: () => 'Account Management', confidence: 0.9 },
    { pattern: /\/settings(\/|$)/i, name: () => 'Settings', confidence: 0.85 },

    // Authentication patterns
    { pattern: /\/login(\/|$)/i, name: () => 'Authentication', confidence: 0.95 },
    { pattern: /\/signup|\/register(\/|$)/i, name: () => 'User Registration', confidence: 0.95 },
    { pattern: /\/forgot-password|\/reset-password(\/|$)/i, name: () => 'Password Recovery', confidence: 0.95 },
    { pattern: /\/auth(\/|$)/i, name: () => 'Authentication', confidence: 0.9 },

    // E-commerce patterns
    { pattern: /\/products?(\/|$)/i, name: () => 'Product Catalog', confidence: 0.9 },
    { pattern: /\/cart(\/|$)/i, name: () => 'Shopping Cart', confidence: 0.95 },
    { pattern: /\/checkout(\/|$)/i, name: () => 'Checkout', confidence: 0.95 },
    { pattern: /\/orders?(\/|$)/i, name: () => 'Order Management', confidence: 0.9 },
    { pattern: /\/payments?(\/|$)/i, name: () => 'Payment Processing', confidence: 0.9 },

    // Content patterns
    { pattern: /\/blog|\/posts?(\/|$)/i, name: () => 'Blog', confidence: 0.85 },
    { pattern: /\/articles?(\/|$)/i, name: () => 'Articles', confidence: 0.85 },
    { pattern: /\/news(\/|$)/i, name: () => 'News', confidence: 0.85 },
    { pattern: /\/pages?(\/|$)/i, name: () => 'Content Pages', confidence: 0.7 },

    // Admin patterns
    { pattern: /\/admin(\/|$)/i, name: () => 'Admin Dashboard', confidence: 0.9 },
    { pattern: /\/dashboard(\/|$)/i, name: () => 'Dashboard', confidence: 0.85 },
    { pattern: /\/analytics(\/|$)/i, name: () => 'Analytics', confidence: 0.9 },
    { pattern: /\/reports?(\/|$)/i, name: () => 'Reporting', confidence: 0.85 },

    // Communication patterns
    { pattern: /\/messages?|\/inbox(\/|$)/i, name: () => 'Messaging', confidence: 0.9 },
    { pattern: /\/notifications?(\/|$)/i, name: () => 'Notifications', confidence: 0.9 },
    { pattern: /\/chat(\/|$)/i, name: () => 'Chat', confidence: 0.9 },

    // Search patterns
    { pattern: /\/search(\/|$)/i, name: () => 'Search', confidence: 0.9 },

    // Generic detail pattern with entity name extraction
    {
        pattern: /\/(\w+)\/[:*\[\]]\w+$/i,
        name: (match) => `${capitalize(match[1].replace(/-/g, ' '))} Details`,
        confidence: 0.75
    },

    // Generic list pattern
    {
        pattern: /\/(\w+)s$/i,
        name: (match) => `${capitalize(match[1].replace(/-/g, ' '))} Management`,
        confidence: 0.6
    },
];

function capitalize(str: string): string {
    return str
        .split(' ')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
        .join(' ');
}

// =============================================================================
// Feature Detector Class
// =============================================================================

export class FeatureDetector {
    private logger: winston.Logger;
    private neo4jClient: Neo4jClient;

    constructor(neo4jClient: Neo4jClient, logger: winston.Logger) {
        this.neo4jClient = neo4jClient;
        this.logger = logger;
    }

    /**
     * Discover features for a repository.
     */
    async discoverFeatures(repositoryId: string): Promise<FeatureDiscoveryResult> {
        this.logger.info(`Starting feature discovery for repository: ${repositoryId}`);

        try {
            // 1. Get all UI routes and pages
            const uiRoutes = await this.getUIRoutes(repositoryId);
            const uiPages = await this.getUIPages(repositoryId);

            this.logger.info(`Found ${uiRoutes.length} UI routes and ${uiPages.length} UI pages`);

            // 2. Group routes by base path to identify features
            const routeGroups = this.groupRoutesByFeature([...uiRoutes, ...uiPages]);

            // 3. For each group, trace through to API, services, and data
            const features: FeatureNode[] = [];
            const relationships: RelationshipInfo[] = [];

            for (const [basePath, routes] of routeGroups) {
                const feature = await this.buildFeatureFromRoutes(basePath, routes, repositoryId);
                if (feature) {
                    features.push(feature.feature);
                    relationships.push(...feature.relationships);
                }
            }

            // 4. Get unmapped endpoints and routes
            const unmappedEndpoints = await this.getUnmappedEndpoints(repositoryId);
            const unmappedRoutes = await this.getUnmappedRoutes(repositoryId);

            // 5. Calculate statistics
            const stats = this.calculateStats(features, uiRoutes.length + uiPages.length);

            this.logger.info(`Feature discovery complete: ${features.length} features found`);

            return {
                features,
                unmappedEndpoints,
                unmappedRoutes,
                stats,
            };
        } catch (error: any) {
            this.logger.error('Feature discovery failed', { error: error.message });
            throw error;
        }
    }

    /**
     * Rename a discovered feature (user override).
     */
    async renameFeature(featureId: string, newName: string): Promise<void> {
        const query = `
            MATCH (f:Feature {entityId: $featureId})
            SET f.userOverrideName = $newName, f.featureName = $newName
            RETURN f
        `;
        await this.neo4jClient.runTransaction(query, { featureId, newName }, 'WRITE', 'FeatureDetector');
        this.logger.info(`Renamed feature ${featureId} to "${newName}"`);
    }

    // =========================================================================
    // Private Methods
    // =========================================================================

    private async getUIRoutes(repositoryId: string): Promise<RouteInfo[]> {
        const result = await this.neo4jClient.runTransaction(
            FEATURE_QUERIES.GET_UI_ROUTES,
            { repositoryId },
            'READ',
            'FeatureDetector'
        );

        return ((result as any).records || []).map((r: any) => ({
            entityId: r.get('entityId'),
            path: r.get('path') || r.get('fullPath'),
            type: 'route' as const,
            framework: r.get('framework'),
            componentName: r.get('componentName'),
            requiresAuth: r.get('requiresAuth'),
        }));
    }

    private async getUIPages(repositoryId: string): Promise<RouteInfo[]> {
        const result = await this.neo4jClient.runTransaction(
            FEATURE_QUERIES.GET_UI_PAGES,
            { repositoryId },
            'READ',
            'FeatureDetector'
        );

        return ((result as any).records || [])
            .filter((r: any) => !r.get('isLayout'))
            .map((r: any) => ({
                entityId: r.get('entityId'),
                path: r.get('routePath'),
                type: 'page' as const,
                framework: r.get('framework'),
            }));
    }

    private groupRoutesByFeature(routes: RouteInfo[]): Map<string, RouteInfo[]> {
        const groups = new Map<string, RouteInfo[]>();

        for (const route of routes) {
            const basePath = this.extractBasePath(route.path);
            if (!groups.has(basePath)) {
                groups.set(basePath, []);
            }
            groups.get(basePath)!.push(route);
        }

        return groups;
    }

    private extractBasePath(path: string): string {
        // Remove dynamic segments and get the base feature path
        const segments = path.split('/').filter(Boolean);
        if (segments.length === 0) return '/';

        // Take the first non-dynamic segment as the base
        const baseSegments: string[] = [];
        for (const segment of segments) {
            if (segment.startsWith(':') || segment.startsWith('[') || segment.startsWith('*')) {
                break;
            }
            baseSegments.push(segment);
            // Usually the feature is identified by the first 1-2 segments
            if (baseSegments.length >= 2) break;
        }

        return '/' + baseSegments.join('/');
    }

    private async buildFeatureFromRoutes(
        basePath: string,
        routes: RouteInfo[],
        repositoryId: string
    ): Promise<{ feature: FeatureNode; relationships: RelationshipInfo[] } | null> {
        if (routes.length === 0) return null;

        // Infer feature name
        const { name, confidence } = this.inferFeatureName(basePath, routes);

        // Get entity IDs for tracing
        const routeIds = routes.filter(r => r.type === 'route').map(r => r.entityId);
        const pageIds = routes.filter(r => r.type === 'page').map(r => r.entityId);

        // Trace to APIs
        const apiEndpoints = await this.traceToAPIs(routeIds, pageIds);

        // Trace to services
        const endpointIds = apiEndpoints.map(e => e.endpointId);
        const services = await this.traceToServices(endpointIds);

        // Trace to data entities
        const serviceIds = services.map(s => s.serviceId);
        const dataEntities = await this.traceToData(serviceIds);

        // Determine category
        const category = this.determineCategory(basePath, routes);

        // Determine complexity
        const complexity = this.determineComplexity(routes.length, apiEndpoints.length, services.length);

        // Build trace path
        const tracePath = this.buildTracePath(routes, apiEndpoints, services, dataEntities);

        // Create feature node
        const entityId = this.generateEntityId('feature', basePath);
        const feature: FeatureNode = {
            id: entityId,
            entityId,
            kind: 'Feature',
            name,
            filePath: routes[0]?.path || basePath,
            language: 'mixed',
            startLine: 0,
            endLine: 0,
            startColumn: 0,
            endColumn: 0,
            createdAt: new Date().toISOString(),
            properties: {
                featureName: name,
                description: `Feature covering ${basePath} routes`,
                category,
                confidence,
                uiEntryPoints: routes.map(r => r.entityId),
                apiEndpoints: apiEndpoints.map(e => e.endpointId),
                services: services.map(s => s.serviceId),
                databaseEntities: dataEntities.map(d => d.entityName),
                complexity,
                tracePath,
            },
        };

        // Build relationships
        const relationships: RelationshipInfo[] = [];

        // Feature -> UI routes
        for (const route of routes) {
            relationships.push(this.createRelationship(entityId, route.entityId, 'FEATURE_HAS_UI'));
        }

        // Feature -> API endpoints
        for (const endpoint of apiEndpoints) {
            relationships.push(this.createRelationship(entityId, endpoint.endpointId, 'FEATURE_HAS_API'));
        }

        // Feature -> Services
        for (const service of services) {
            relationships.push(this.createRelationship(entityId, service.serviceId, 'FEATURE_HAS_SERVICE'));
        }

        // Feature -> Data entities
        for (const data of dataEntities) {
            relationships.push(this.createRelationship(entityId, data.entityId, 'FEATURE_HAS_DATA'));
        }

        return { feature, relationships };
    }

    private inferFeatureName(basePath: string, routes: RouteInfo[]): { name: string; confidence: number } {
        // Try pattern matching first
        for (const rule of FEATURE_NAME_RULES) {
            const match = basePath.match(rule.pattern);
            if (match) {
                return {
                    name: rule.name(match),
                    confidence: rule.confidence,
                };
            }
        }

        // Fall back to component name if available
        const componentName = routes.find(r => r.componentName)?.componentName;
        if (componentName) {
            return {
                name: this.formatComponentName(componentName),
                confidence: 0.7,
            };
        }

        // Fall back to path-based name
        const segments = basePath.split('/').filter(Boolean);
        const name = segments.length > 0
            ? capitalize(segments[segments.length - 1].replace(/-/g, ' '))
            : 'Home';

        return { name, confidence: 0.5 };
    }

    private formatComponentName(name: string): string {
        // Convert PascalCase/camelCase to Title Case
        return name
            .replace(/([a-z])([A-Z])/g, '$1 $2')
            .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
            .replace(/Page$|Component$|View$/i, '')
            .trim();
    }

    private determineCategory(basePath: string, routes: RouteInfo[]): FeatureCategory {
        // Admin routes
        if (/\/admin|\/dashboard|\/manage/i.test(basePath)) {
            return 'admin';
        }

        // API-only routes
        if (/\/api\//i.test(basePath)) {
            return 'api-only';
        }

        // Internal routes
        if (/\/internal|\/system/i.test(basePath)) {
            return 'internal';
        }

        // Check if any route requires auth (admin indicator)
        if (routes.some(r => r.requiresAuth)) {
            // Could be user-facing or admin - default to user-facing
            return 'user-facing';
        }

        return 'user-facing';
    }

    private determineComplexity(
        routeCount: number,
        apiCount: number,
        serviceCount: number
    ): FeatureComplexity {
        const totalComponents = routeCount + apiCount + serviceCount;

        if (totalComponents <= 3) return 'simple';
        if (totalComponents <= 8) return 'moderate';
        return 'complex';
    }

    private buildTracePath(
        routes: RouteInfo[],
        apis: ApiInfo[],
        services: ServiceInfo[],
        data: DataInfo[]
    ): string[] {
        const path: string[] = [];

        // Add route paths
        if (routes.length > 0) {
            path.push(`UI: ${routes.map(r => r.path).slice(0, 3).join(', ')}${routes.length > 3 ? '...' : ''}`);
        }

        // Add API paths
        if (apis.length > 0) {
            path.push(`API: ${apis.map(a => `${a.method} ${a.path}`).slice(0, 3).join(', ')}${apis.length > 3 ? '...' : ''}`);
        }

        // Add services
        if (services.length > 0) {
            path.push(`Services: ${services.map(s => s.serviceName).slice(0, 3).join(', ')}${services.length > 3 ? '...' : ''}`);
        }

        // Add data entities
        if (data.length > 0) {
            path.push(`Data: ${data.map(d => d.entityName).slice(0, 3).join(', ')}${data.length > 3 ? '...' : ''}`);
        }

        return path;
    }

    private async traceToAPIs(routeIds: string[], pageIds: string[]): Promise<ApiInfo[]> {
        const apis: ApiInfo[] = [];

        if (routeIds.length > 0) {
            try {
                const result = await this.neo4jClient.runTransaction(
                    FEATURE_QUERIES.TRACE_UI_TO_API,
                    { routeIds },
                    'READ',
                    'FeatureDetector'
                );

                for (const r of (result as any).records || []) {
                    const endpoints = r.get('endpoints') || [];
                    for (const ep of endpoints) {
                        apis.push({
                            endpointId: ep.endpointId,
                            path: ep.path,
                            method: ep.method,
                        });
                    }
                }
            } catch (error) {
                this.logger.debug('Failed to trace routes to APIs', { error });
            }
        }

        if (pageIds.length > 0) {
            try {
                const result = await this.neo4jClient.runTransaction(
                    FEATURE_QUERIES.TRACE_PAGE_TO_API,
                    { pageIds },
                    'READ',
                    'FeatureDetector'
                );

                for (const r of (result as any).records || []) {
                    const endpoints = r.get('endpoints') || [];
                    for (const ep of endpoints) {
                        if (!apis.some(a => a.endpointId === ep.endpointId)) {
                            apis.push({
                                endpointId: ep.endpointId,
                                path: ep.path,
                                method: ep.method,
                            });
                        }
                    }
                }
            } catch (error) {
                this.logger.debug('Failed to trace pages to APIs', { error });
            }
        }

        return apis;
    }

    private async traceToServices(endpointIds: string[]): Promise<ServiceInfo[]> {
        if (endpointIds.length === 0) return [];

        try {
            const result = await this.neo4jClient.runTransaction(
                FEATURE_QUERIES.TRACE_API_TO_SERVICE,
                { endpointIds },
                'READ',
                'FeatureDetector'
            );

            const services: ServiceInfo[] = [];
            for (const r of (result as any).records || []) {
                const svcs = r.get('services') || [];
                for (const svc of svcs) {
                    if (!services.some(s => s.serviceId === svc.serviceId)) {
                        services.push({
                            serviceId: svc.serviceId,
                            serviceName: svc.serviceName,
                            stereotype: svc.stereotype,
                        });
                    }
                }
            }
            return services;
        } catch (error) {
            this.logger.debug('Failed to trace APIs to services', { error });
            return [];
        }
    }

    private async traceToData(serviceIds: string[]): Promise<DataInfo[]> {
        if (serviceIds.length === 0) return [];

        try {
            const result = await this.neo4jClient.runTransaction(
                FEATURE_QUERIES.TRACE_SERVICE_TO_DATA,
                { serviceIds },
                'READ',
                'FeatureDetector'
            );

            const data: DataInfo[] = [];
            for (const r of (result as any).records || []) {
                const entities = r.get('dataEntities') || [];
                for (const entity of entities) {
                    if (!data.some(d => d.entityId === entity.entityId)) {
                        data.push({
                            entityId: entity.entityId,
                            entityName: entity.entityName,
                            entityType: entity.entityType,
                        });
                    }
                }
            }
            return data;
        } catch (error) {
            this.logger.debug('Failed to trace services to data', { error });
            return [];
        }
    }

    private async getUnmappedEndpoints(repositoryId: string): Promise<string[]> {
        try {
            const result = await this.neo4jClient.runTransaction(
                FEATURE_QUERIES.UNMAPPED_ENDPOINTS,
                { repositoryId },
                'READ',
                'FeatureDetector'
            );

            return ((result as any).records || []).map((r: any) =>
                `${r.get('method')} ${r.get('path')}`
            );
        } catch (error) {
            this.logger.debug('Failed to get unmapped endpoints', { error });
            return [];
        }
    }

    private async getUnmappedRoutes(repositoryId: string): Promise<string[]> {
        try {
            const result = await this.neo4jClient.runTransaction(
                FEATURE_QUERIES.UNMAPPED_ROUTES,
                { repositoryId },
                'READ',
                'FeatureDetector'
            );

            return ((result as any).records || []).map((r: any) => r.get('path'));
        } catch (error) {
            this.logger.debug('Failed to get unmapped routes', { error });
            return [];
        }
    }

    private calculateStats(
        features: FeatureNode[],
        totalRoutes: number
    ): FeatureDiscoveryResult['stats'] {
        const byCategory: Record<FeatureCategory, number> = {
            'user-facing': 0,
            'admin': 0,
            'internal': 0,
            'api-only': 0,
        };

        const byComplexity: Record<FeatureComplexity, number> = {
            'simple': 0,
            'moderate': 0,
            'complex': 0,
        };

        let coveredRoutes = 0;

        for (const feature of features) {
            byCategory[feature.properties.category]++;
            byComplexity[feature.properties.complexity]++;
            coveredRoutes += feature.properties.uiEntryPoints.length;
        }

        return {
            totalFeatures: features.length,
            byCategory,
            byComplexity,
            coveragePercent: totalRoutes > 0 ? (coveredRoutes / totalRoutes) * 100 : 0,
        };
    }

    private createRelationship(sourceId: string, targetId: string, type: string): RelationshipInfo {
        const relId = this.generateEntityId('rel', `${type}:${sourceId}:${targetId}`);
        return {
            id: relId,
            entityId: relId,
            type,
            sourceId,
            targetId,
            createdAt: new Date().toISOString(),
        };
    }

    private generateEntityId(prefix: string, identifier: string): string {
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

interface RouteInfo {
    entityId: string;
    path: string;
    type: 'route' | 'page';
    framework?: string;
    componentName?: string;
    requiresAuth?: boolean;
}

interface ApiInfo {
    endpointId: string;
    path: string;
    method: string;
}

interface ServiceInfo {
    serviceId: string;
    serviceName: string;
    stereotype?: string;
}

interface DataInfo {
    entityId: string;
    entityName: string;
    entityType: string;
}

// =============================================================================
// Factory Function
// =============================================================================

export function createFeatureDetector(
    neo4jClient: Neo4jClient,
    logger: winston.Logger
): FeatureDetector {
    return new FeatureDetector(neo4jClient, logger);
}
