// src/analyzer/parsers/route-parser.ts
/**
 * UI Route Parser
 * Detects frontend routes and pages from various routing frameworks:
 * - React Router (v5, v6)
 * - Next.js (App Router, Pages Router)
 * - Vue Router
 * - Angular Router
 * - Nuxt
 * - SvelteKit
 * - Remix
 */

import winston from 'winston';
import * as path from 'path';
import {
    AstNode,
    UIRouteNode,
    UIPageNode,
    UIRoutingFramework,
    HttpMethod,
    RouteGuard,
    RelationshipInfo,
} from '../types.js';

// =============================================================================
// Route Detection Patterns
// =============================================================================

interface RoutePattern {
    framework: UIRoutingFramework;
    pattern: RegExp;
    pathGroup?: number;
    componentGroup?: number;
    isIndex?: boolean;
    isLazy?: boolean;
}

// React Router patterns
const REACT_ROUTER_PATTERNS: RoutePattern[] = [
    // React Router v6: <Route path="/users" element={<Users />} />
    {
        framework: 'react-router',
        pattern: /<Route\s+[^>]*path\s*=\s*["']([^"']+)["'][^>]*element\s*=\s*\{?\s*<(\w+)/i,
        pathGroup: 1,
        componentGroup: 2,
    },
    // React Router v6: <Route path="/users" element={Users} />
    {
        framework: 'react-router',
        pattern: /<Route\s+[^>]*path\s*=\s*["']([^"']+)["'][^>]*element\s*=\s*\{(\w+)\}/i,
        pathGroup: 1,
        componentGroup: 2,
    },
    // React Router v6: index route
    {
        framework: 'react-router',
        pattern: /<Route\s+[^>]*index[^>]*element\s*=\s*\{?\s*<(\w+)/i,
        componentGroup: 1,
        isIndex: true,
    },
    // React Router v5: <Route path="/users" component={Users} />
    {
        framework: 'react-router',
        pattern: /<Route\s+[^>]*path\s*=\s*["']([^"']+)["'][^>]*component\s*=\s*\{(\w+)\}/i,
        pathGroup: 1,
        componentGroup: 2,
    },
    // createBrowserRouter / createHashRouter routes array
    {
        framework: 'react-router',
        pattern: /\{\s*path\s*:\s*["']([^"']+)["']\s*,\s*(?:element|component)\s*:/i,
        pathGroup: 1,
    },
    // useRoutes hook
    {
        framework: 'react-router',
        pattern: /useRoutes\s*\(\s*\[\s*\{\s*path\s*:\s*["']([^"']+)["']/i,
        pathGroup: 1,
    },
    // Lazy route: lazy: () => import('./Users')
    {
        framework: 'react-router',
        pattern: /\{\s*path\s*:\s*["']([^"']+)["'][^}]*lazy\s*:\s*\(\)\s*=>\s*import/i,
        pathGroup: 1,
        isLazy: true,
    },
];

// Vue Router patterns
const VUE_ROUTER_PATTERNS: RoutePattern[] = [
    // Vue Router: { path: '/users', component: Users }
    {
        framework: 'vue-router',
        pattern: /\{\s*path\s*:\s*['"]([^'"]+)['"]\s*,\s*component\s*:\s*(\w+)/i,
        pathGroup: 1,
        componentGroup: 2,
    },
    // Vue Router lazy: component: () => import('./Users.vue')
    {
        framework: 'vue-router',
        pattern: /\{\s*path\s*:\s*['"]([^'"]+)['"]\s*,\s*component\s*:\s*\(\)\s*=>\s*import/i,
        pathGroup: 1,
        isLazy: true,
    },
    // createRouter({ routes: [...] })
    {
        framework: 'vue-router',
        pattern: /createRouter\s*\(\s*\{[^}]*routes\s*:\s*\[/i,
    },
];

// Angular Router patterns
const ANGULAR_ROUTER_PATTERNS: RoutePattern[] = [
    // { path: 'users', component: UsersComponent }
    {
        framework: 'angular-router',
        pattern: /\{\s*path\s*:\s*['"]([^'"]+)['"]\s*,\s*component\s*:\s*(\w+)/i,
        pathGroup: 1,
        componentGroup: 2,
    },
    // loadChildren lazy loading
    {
        framework: 'angular-router',
        pattern: /\{\s*path\s*:\s*['"]([^'"]+)['"]\s*,\s*loadChildren\s*:/i,
        pathGroup: 1,
        isLazy: true,
    },
    // canActivate guards
    {
        framework: 'angular-router',
        pattern: /\{\s*path\s*:\s*['"]([^'"]+)['"]\s*,[^}]*canActivate\s*:\s*\[([^\]]+)\]/i,
        pathGroup: 1,
    },
    // RouterModule.forRoot(routes)
    {
        framework: 'angular-router',
        pattern: /RouterModule\.forRoot\s*\(\s*(\w+)/i,
    },
];

// File-based routing patterns for Next.js, Nuxt, SvelteKit, Remix

interface FileRoutePattern {
    framework: UIRoutingFramework;
    routerType: 'app-router' | 'pages-router' | 'nuxt-pages' | 'svelte-routes' | 'remix-routes';
    /** Regex to match file paths */
    filePattern: RegExp;
    /** Function to extract route path from file path */
    extractRoute: (filePath: string, match: RegExpMatchArray) => string;
    /** Check for specific content patterns */
    contentPatterns?: {
        isLayout?: RegExp;
        isLoading?: RegExp;
        isError?: RegExp;
        isNotFound?: RegExp;
        isServerComponent?: RegExp;
        isClientComponent?: RegExp;
        dataFetching?: RegExp[];
        apiMethods?: RegExp;
    };
}

const FILE_ROUTE_PATTERNS: FileRoutePattern[] = [
    // Next.js App Router
    {
        framework: 'next-js',
        routerType: 'app-router',
        filePattern: /[\/\\]app[\/\\](.+)[\/\\](page|layout|loading|error|not-found)\.(tsx?|jsx?)$/,
        extractRoute: (filePath, match) => {
            const matchGroup = match[1] || '';
            const segments = matchGroup.split(/[\/\\]/);
            return '/' + segments
                .filter(s => s !== '(.)' && !s.startsWith('(') && !s.startsWith('@'))
                .map(s => s.replace(/^\[\.\.\.(.+)\]$/, '*$1').replace(/^\[(.+)\]$/, ':$1'))
                .join('/');
        },
        contentPatterns: {
            isLayout: /^export\s+default\s+function\s+\w*Layout/m,
            isLoading: /^export\s+default\s+function\s+Loading/m,
            isError: /^['"]use client['"];?\s*\n.*error/im,
            isNotFound: /^export\s+default\s+function\s+NotFound/m,
            isServerComponent: /^(?!['"]use client['"])/m,
            isClientComponent: /^['"]use client['"]/m,
            dataFetching: [
                /export\s+async\s+function\s+generateStaticParams/,
                /export\s+async\s+function\s+generateMetadata/,
            ],
        },
    },
    // Next.js Pages Router
    {
        framework: 'next-js',
        routerType: 'pages-router',
        filePattern: /[\/\\]pages[\/\\](.+)\.(tsx?|jsx?)$/,
        extractRoute: (filePath, match) => {
            let route = match[1] || '';
            // Handle index routes
            if (route.endsWith('/index') || route === 'index') {
                route = route.replace(/\/?index$/, '') || '/';
            }
            // Handle dynamic routes
            route = route
                .replace(/\[\.\.\.(.+)\]/g, '*$1')
                .replace(/\[(.+)\]/g, ':$1');
            return route.startsWith('/') ? route : '/' + route;
        },
        contentPatterns: {
            dataFetching: [
                /export\s+(async\s+)?function\s+getServerSideProps/,
                /export\s+(async\s+)?function\s+getStaticProps/,
                /export\s+(async\s+)?function\s+getStaticPaths/,
            ],
        },
    },
    // Next.js API Routes (App Router)
    {
        framework: 'next-js',
        routerType: 'app-router',
        filePattern: /[\/\\]app[\/\\](.+)[\/\\]route\.(tsx?|jsx?)$/,
        extractRoute: (filePath, match) => {
            const matchGroup = match[1] || '';
            const segments = matchGroup.split(/[\/\\]/);
            return '/api/' + segments
                .filter(s => !s.startsWith('(') && !s.startsWith('@'))
                .map(s => s.replace(/^\[\.\.\.(.+)\]$/, '*$1').replace(/^\[(.+)\]$/, ':$1'))
                .join('/');
        },
        contentPatterns: {
            apiMethods: /export\s+(async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)/,
        },
    },
    // Nuxt Pages
    {
        framework: 'nuxt',
        routerType: 'nuxt-pages',
        filePattern: /[\/\\]pages[\/\\](.+)\.vue$/,
        extractRoute: (filePath, match) => {
            let route = match[1] || '';
            if (route.endsWith('/index') || route === 'index') {
                route = route.replace(/\/?index$/, '') || '/';
            }
            route = route.replace(/\[(.+)\]/g, ':$1');
            return route.startsWith('/') ? route : '/' + route;
        },
    },
    // SvelteKit Routes
    {
        framework: 'svelte-kit',
        routerType: 'svelte-routes',
        filePattern: /[\/\\]src[\/\\]routes[\/\\](.+)[\/\\]\+page\.svelte$/,
        extractRoute: (filePath, match) => {
            const matchGroup = match[1] || '';
            const segments = matchGroup.split(/[\/\\]/);
            return '/' + segments
                .filter(s => !s.startsWith('('))
                .map(s => s.replace(/^\[\.\.\.(.+)\]$/, '*$1').replace(/^\[(.+)\]$/, ':$1'))
                .join('/');
        },
        contentPatterns: {
            isLayout: /\+layout\.svelte$/,
            isError: /\+error\.svelte$/,
        },
    },
    // Remix Routes
    {
        framework: 'remix',
        routerType: 'remix-routes',
        filePattern: /[\/\\]app[\/\\]routes[\/\\](.+)\.(tsx?|jsx?)$/,
        extractRoute: (filePath, match) => {
            let route = match[1] || '';
            // Remix uses dots for nesting
            route = route
                .replace(/\./g, '/')
                .replace(/_index$/, '')
                .replace(/\$(.+)/g, ':$1');
            return route.startsWith('/') ? route : '/' + route;
        },
        contentPatterns: {
            dataFetching: [
                /export\s+(async\s+)?function\s+loader/,
                /export\s+(async\s+)?function\s+action/,
            ],
        },
    },
];

// =============================================================================
// Route Parser Class
// =============================================================================

export class UIRouteParser {
    private logger: winston.Logger;

    constructor(logger: winston.Logger) {
        this.logger = logger;
    }

    /**
     * Detect UI routes from code-based routing (React Router, Vue Router, Angular).
     */
    detectCodeRoutes(
        nodes: AstNode[],
        sourceTexts: Map<string, string>
    ): { routes: UIRouteNode[]; relationships: RelationshipInfo[] } {
        const routes: UIRouteNode[] = [];
        const relationships: RelationshipInfo[] = [];
        const allPatterns = [
            ...REACT_ROUTER_PATTERNS,
            ...VUE_ROUTER_PATTERNS,
            ...ANGULAR_ROUTER_PATTERNS,
        ];

        for (const node of nodes) {
            const sourceText = sourceTexts.get(node.filePath);
            if (!sourceText) continue;

            // Only check files that might contain route definitions
            if (!this.mightContainRoutes(node.filePath, sourceText)) continue;

            for (const pattern of allPatterns) {
                const matches = sourceText.matchAll(new RegExp(pattern.pattern, 'gi'));
                for (const match of matches) {
                    const routePath = pattern.pathGroup ? (match[pattern.pathGroup] || '/') : '/';
                    const componentName = pattern.componentGroup ? match[pattern.componentGroup] : undefined;

                    const routeNode = this.createRouteNode(
                        node,
                        routePath,
                        pattern.framework,
                        componentName,
                        pattern.isIndex || false,
                        pattern.isLazy || false,
                        match.index || 0
                    );

                    routes.push(routeNode);

                    // Create relationship to component if found
                    if (componentName) {
                        const componentNode = this.findComponentNode(nodes, componentName, node.filePath);
                        if (componentNode) {
                            relationships.push(this.createRouteRelationship(
                                routeNode.entityId,
                                componentNode.entityId,
                                'RENDERS_PAGE'
                            ));
                        }
                    }
                }
            }
        }

        // Extract nested route relationships
        this.extractNestedRoutes(routes, relationships);

        // Detect route guards
        this.detectRouteGuards(routes, sourceTexts);

        this.logger.info(`Detected ${routes.length} code-based UI routes`);
        return { routes, relationships };
    }

    /**
     * Detect UI pages from file-based routing (Next.js, Nuxt, SvelteKit, Remix).
     */
    detectFileRoutes(
        nodes: AstNode[],
        sourceTexts: Map<string, string>
    ): { pages: UIPageNode[]; relationships: RelationshipInfo[] } {
        const pages: UIPageNode[] = [];
        const relationships: RelationshipInfo[] = [];

        for (const node of nodes) {
            if (node.kind !== 'File') continue;

            for (const pattern of FILE_ROUTE_PATTERNS) {
                const match = node.filePath.match(pattern.filePattern);
                if (!match) continue;

                const routePath = pattern.extractRoute(node.filePath, match);
                const sourceText = sourceTexts.get(node.filePath) || '';

                const pageNode = this.createPageNode(
                    node,
                    routePath,
                    pattern,
                    sourceText
                );

                pages.push(pageNode);

                // Create relationship to file
                relationships.push(this.createRouteRelationship(
                    pageNode.entityId,
                    node.entityId,
                    'RENDERS_PAGE'
                ));
            }
        }

        // Link layouts to pages
        this.linkLayoutsToPages(pages, relationships);

        this.logger.info(`Detected ${pages.length} file-based UI pages`);
        return { pages, relationships };
    }

    /**
     * Detect all UI routes and pages.
     */
    detectAllRoutes(
        nodes: AstNode[],
        sourceTexts: Map<string, string>
    ): UIRouteDetectionResult {
        const codeRoutes = this.detectCodeRoutes(nodes, sourceTexts);
        const fileRoutes = this.detectFileRoutes(nodes, sourceTexts);

        return {
            routes: codeRoutes.routes,
            pages: fileRoutes.pages,
            relationships: [...codeRoutes.relationships, ...fileRoutes.relationships],
        };
    }

    // =========================================================================
    // Helper Methods
    // =========================================================================

    private mightContainRoutes(filePath: string, sourceText: string): boolean {
        const routeKeywords = [
            'Route', 'Router', 'createBrowserRouter', 'createHashRouter',
            'useRoutes', 'RouterModule', 'createRouter', 'routes',
        ];
        return routeKeywords.some(kw => sourceText.includes(kw));
    }

    private createRouteNode(
        parentNode: AstNode,
        routePath: string,
        framework: UIRoutingFramework,
        componentName: string | undefined,
        isIndex: boolean,
        isLazy: boolean,
        matchIndex: number
    ): UIRouteNode {
        const pathParams = this.extractPathParameters(routePath);
        const entityId = this.generateEntityId('ui_route', `${parentNode.filePath}:${routePath}`);

        return {
            id: entityId,
            entityId,
            kind: 'UIRoute',
            name: componentName || this.inferRouteName(routePath),
            filePath: parentNode.filePath,
            language: parentNode.language,
            startLine: this.estimateLine(matchIndex, parentNode),
            endLine: this.estimateLine(matchIndex, parentNode),
            startColumn: 0,
            endColumn: 0,
            createdAt: new Date().toISOString(),
            properties: {
                path: routePath,
                fullPath: routePath, // Will be resolved for nested routes
                pathParameters: pathParams,
                componentName,
                framework,
                isIndex,
                isDynamic: pathParams.length > 0,
                isLazy,
            },
        };
    }

    private createPageNode(
        fileNode: AstNode,
        routePath: string,
        pattern: FileRoutePattern,
        sourceText: string
    ): UIPageNode {
        const segments = routePath.split('/').filter(Boolean);
        const entityId = this.generateEntityId('ui_page', `${fileNode.filePath}:${routePath}`);

        // Detect page characteristics from content
        const isLayout = pattern.contentPatterns?.isLayout?.test(sourceText) ||
                        fileNode.filePath.includes('layout.');
        const isLoading = pattern.contentPatterns?.isLoading?.test(sourceText) ||
                         fileNode.filePath.includes('loading.');
        const isError = pattern.contentPatterns?.isError?.test(sourceText) ||
                       fileNode.filePath.includes('error.');
        const isNotFound = pattern.contentPatterns?.isNotFound?.test(sourceText) ||
                          fileNode.filePath.includes('not-found.');
        const isServerComponent = pattern.contentPatterns?.isServerComponent?.test(sourceText);
        const isClientComponent = pattern.contentPatterns?.isClientComponent?.test(sourceText);

        // Detect data fetching methods
        const dataFetching: string[] = [];
        if (pattern.contentPatterns?.dataFetching) {
            for (const dfPattern of pattern.contentPatterns.dataFetching) {
                const match = sourceText.match(dfPattern);
                if (match) {
                    dataFetching.push(match[2] || match[1] || 'unknown');
                }
            }
        }

        // Detect API methods for API routes
        const apiMethods: HttpMethod[] = [];
        if (pattern.contentPatterns?.apiMethods) {
            const matches = sourceText.matchAll(new RegExp(pattern.contentPatterns.apiMethods, 'g'));
            for (const match of matches) {
                const method = match[2] as HttpMethod;
                if (method && !apiMethods.includes(method)) {
                    apiMethods.push(method);
                }
            }
        }

        // Detect dynamic segments
        const dynamicSegments = segments.filter(s => s.startsWith(':') || s.startsWith('*'));
        const isCatchAll = segments.some(s => s.startsWith('*'));
        const isOptionalCatchAll = routePath.includes('[[');

        return {
            id: entityId,
            entityId,
            kind: 'UIPage',
            name: this.inferPageName(fileNode.filePath, routePath),
            filePath: fileNode.filePath,
            language: fileNode.language,
            startLine: 1,
            endLine: fileNode.endLine || 1,
            startColumn: 0,
            endColumn: 0,
            createdAt: new Date().toISOString(),
            properties: {
                routePath,
                segments,
                isLayout,
                isLoading,
                isError,
                isNotFound,
                routerType: pattern.routerType,
                framework: pattern.framework,
                isServerComponent,
                isClientComponent,
                dataFetching: dataFetching.length > 0 ? dataFetching : undefined,
                apiMethods: apiMethods.length > 0 ? apiMethods : undefined,
                isDynamic: dynamicSegments.length > 0,
                dynamicSegments: dynamicSegments.length > 0 ? dynamicSegments : undefined,
                isCatchAll,
                isOptionalCatchAll,
                hasMetadata: /generateMetadata|metadata\s*=/.test(sourceText),
            },
        };
    }

    private createRouteRelationship(
        sourceId: string,
        targetId: string,
        type: string
    ): RelationshipInfo {
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

    private extractPathParameters(routePath: string): string[] {
        const params: string[] = [];
        // Match :param, {param}, [param]
        const matches = routePath.matchAll(/[:*]\w+|\{(\w+)\}|\[(\w+)\]/g);
        for (const match of matches) {
            const param = match[1] || match[2] || match[0].slice(1);
            if (!params.includes(param)) {
                params.push(param);
            }
        }
        return params;
    }

    private inferRouteName(routePath: string): string {
        if (routePath === '/' || routePath === '') return 'Home';
        const segments = routePath.split('/').filter(Boolean);
        if (segments.length === 0) return 'Home';
        const lastSegment = segments[segments.length - 1]!;
        if (lastSegment.startsWith(':') || lastSegment.startsWith('[')) {
            return segments.length > 1
                ? this.capitalize(segments[segments.length - 2]!) + 'Detail'
                : 'Detail';
        }
        return this.capitalize(lastSegment.replace(/-/g, ' '));
    }

    private inferPageName(filePath: string, routePath: string): string {
        const fileName = path.basename(filePath, path.extname(filePath));
        if (fileName === 'page' || fileName === 'index') {
            return this.inferRouteName(routePath);
        }
        return this.capitalize(fileName.replace(/[-_]/g, ' '));
    }

    private capitalize(str: string): string {
        return str
            .split(' ')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
            .join(' ');
    }

    private findComponentNode(
        nodes: AstNode[],
        componentName: string,
        currentFilePath: string
    ): AstNode | undefined {
        // First try to find in the same file
        let found = nodes.find(n =>
            n.name === componentName &&
            n.filePath === currentFilePath &&
            (n.kind === 'Component' || n.kind === 'Function' || n.kind === 'Class')
        );
        if (found) return found;

        // Then try to find in any file
        return nodes.find(n =>
            n.name === componentName &&
            (n.kind === 'Component' || n.kind === 'Function' || n.kind === 'Class')
        );
    }

    private extractNestedRoutes(routes: UIRouteNode[], relationships: RelationshipInfo[]): void {
        // Build parent-child relationships based on route paths
        for (const route of routes) {
            const parentPath = this.getParentPath(route.properties.path);
            if (parentPath) {
                const parent = routes.find(r => r.properties.path === parentPath);
                if (parent) {
                    route.properties.parentRouteId = parent.entityId;
                    parent.properties.childRouteIds = parent.properties.childRouteIds || [];
                    parent.properties.childRouteIds.push(route.entityId);

                    // Update fullPath
                    route.properties.fullPath = parent.properties.fullPath + route.properties.path;

                    // Add relationship
                    relationships.push(this.createRouteRelationship(
                        parent.entityId,
                        route.entityId,
                        'CHILD_ROUTE'
                    ));
                }
            }
        }
    }

    private getParentPath(routePath: string): string | undefined {
        const segments = routePath.split('/').filter(Boolean);
        if (segments.length <= 1) return undefined;
        return '/' + segments.slice(0, -1).join('/');
    }

    private linkLayoutsToPages(pages: UIPageNode[], relationships: RelationshipInfo[]): void {
        const layouts = pages.filter(p => p.properties.isLayout);
        const nonLayouts = pages.filter(p => !p.properties.isLayout);

        for (const page of nonLayouts) {
            // Find the closest parent layout
            const layout = this.findParentLayout(page, layouts);
            if (layout) {
                page.properties.parentLayoutId = layout.entityId;
                relationships.push(this.createRouteRelationship(
                    layout.entityId,
                    page.entityId,
                    'LAYOUT_FOR'
                ));
            }
        }
    }

    private findParentLayout(page: UIPageNode, layouts: UIPageNode[]): UIPageNode | undefined {
        const pageDir = path.dirname(page.filePath);

        // Sort layouts by path depth (deepest first)
        const sortedLayouts = [...layouts].sort((a, b) =>
            b.filePath.split(path.sep).length - a.filePath.split(path.sep).length
        );

        for (const layout of sortedLayouts) {
            const layoutDir = path.dirname(layout.filePath);
            if (pageDir.startsWith(layoutDir)) {
                return layout;
            }
        }
        return undefined;
    }

    private detectRouteGuards(routes: UIRouteNode[], sourceTexts: Map<string, string>): void {
        const guardPatterns = [
            // React Router
            { pattern: /requireAuth|ProtectedRoute|AuthGuard|PrivateRoute/i, type: 'auth' as const },
            { pattern: /RoleGuard|RequireRole|hasRole/i, type: 'role' as const },
            { pattern: /PermissionGuard|RequirePermission|hasPermission/i, type: 'permission' as const },
            // Angular
            { pattern: /canActivate\s*:\s*\[([^\]]+)\]/i, type: 'auth' as const },
            { pattern: /AuthGuard/i, type: 'auth' as const },
            // Vue Router
            { pattern: /beforeEnter.*auth/i, type: 'auth' as const },
            { pattern: /meta\s*:\s*\{[^}]*requiresAuth\s*:\s*true/i, type: 'auth' as const },
        ];

        for (const route of routes) {
            const sourceText = sourceTexts.get(route.filePath);
            if (!sourceText) continue;

            const guards: RouteGuard[] = [];
            for (const gp of guardPatterns) {
                if (gp.pattern.test(sourceText)) {
                    guards.push({
                        name: (gp.pattern.source.split('|')[0] || 'Unknown').replace(/[^a-zA-Z]/g, ''),
                        type: gp.type,
                    });
                    if (gp.type === 'auth') {
                        route.properties.requiresAuth = true;
                    }
                }
            }
            if (guards.length > 0) {
                route.properties.guards = guards;
            }
        }
    }

    private estimateLine(matchIndex: number, node: AstNode): number {
        // Rough estimation - would be more accurate with actual line mapping
        return node.startLine + Math.floor(matchIndex / 80);
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

export interface UIRouteDetectionResult {
    routes: UIRouteNode[];
    pages: UIPageNode[];
    relationships: RelationshipInfo[];
}

// =============================================================================
// Factory Function
// =============================================================================

export function createUIRouteParser(logger: winston.Logger): UIRouteParser {
    return new UIRouteParser(logger);
}
