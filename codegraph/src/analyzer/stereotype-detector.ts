// src/analyzer/stereotype-detector.ts
/**
 * Detects architectural stereotypes for classes and modules.
 * Stereotypes help understand the role of code in the overall architecture.
 */

import winston from 'winston';
import { AstNode, Stereotype, AnnotationInfo } from './types.js';

// =============================================================================
// Detection Patterns
// =============================================================================

/**
 * Annotation patterns for stereotype detection.
 */
interface AnnotationPattern {
    /** Annotation names that indicate this stereotype */
    annotations: string[];
    /** Confidence when detected via annotation */
    confidence: number;
}

/**
 * Naming patterns for stereotype detection.
 */
interface NamingPattern {
    /** Suffix patterns (e.g., 'Controller', 'Service') */
    suffixes: string[];
    /** Prefix patterns (e.g., 'I' for interfaces) */
    prefixes?: string[];
    /** Full name patterns (regex) */
    patterns?: RegExp[];
    /** Confidence when detected via naming */
    confidence: number;
}

/**
 * Structure patterns for stereotype detection.
 */
interface StructurePattern {
    /** Required methods or method patterns */
    methods?: string[];
    /** Required interfaces or base classes */
    implements?: string[];
    /** Required fields or field patterns */
    fields?: string[];
    /** Confidence when detected via structure */
    confidence: number;
}

/**
 * Complete stereotype detection configuration.
 */
interface StereotypeConfig {
    stereotype: Stereotype;
    annotations: AnnotationPattern;
    naming: NamingPattern;
    structure?: StructurePattern;
}

// =============================================================================
// Stereotype Configurations
// =============================================================================

const STEREOTYPE_CONFIGS: StereotypeConfig[] = [
    // Controller - handles HTTP requests
    {
        stereotype: 'Controller',
        annotations: {
            annotations: [
                '@Controller', '@RestController', '@RequestMapping',
                '@Get', '@Post', '@Put', '@Delete', '@Patch',
                '@ApiController', '@Route', '@HttpGet', '@HttpPost',
                '@app.route', '@router.route', '@api.route',
            ],
            confidence: 0.95,
        },
        naming: {
            suffixes: ['Controller', 'Resource', 'Endpoint', 'Api', 'Handler'],
            confidence: 0.75,
        },
        structure: {
            methods: ['get', 'post', 'put', 'delete', 'patch', 'handle'],
            implements: ['Controller', 'IController'],
            confidence: 0.60,
        },
    },

    // Service - business logic layer
    {
        stereotype: 'Service',
        annotations: {
            annotations: [
                '@Service', '@Injectable', '@Component',
                '@Transactional', '@ApplicationScoped',
            ],
            confidence: 0.90,
        },
        naming: {
            suffixes: ['Service', 'ServiceImpl', 'Manager', 'Coordinator', 'Orchestrator'],
            confidence: 0.80,
        },
        structure: {
            implements: ['Service', 'IService'],
            confidence: 0.60,
        },
    },

    // Repository - data access layer
    {
        stereotype: 'Repository',
        annotations: {
            annotations: [
                '@Repository', '@Dao', '@Mapper',
                '@PersistenceContext', '@DataJpaTest',
            ],
            confidence: 0.95,
        },
        naming: {
            suffixes: ['Repository', 'Repo', 'Dao', 'DataAccess', 'Store', 'Persistence'],
            confidence: 0.85,
        },
        structure: {
            methods: ['find', 'findAll', 'findById', 'save', 'delete', 'update', 'get', 'create'],
            implements: ['Repository', 'CrudRepository', 'JpaRepository', 'IRepository'],
            confidence: 0.70,
        },
    },

    // Entity - domain/data model
    {
        stereotype: 'Entity',
        annotations: {
            annotations: [
                '@Entity', '@Table', '@Document', '@Model',
                '@Id', '@Column', '@ManyToOne', '@OneToMany',
                '@dataclass', '@attr.s',
            ],
            confidence: 0.95,
        },
        naming: {
            suffixes: ['Entity', 'Model', 'Domain', 'Aggregate'],
            confidence: 0.60,
        },
        structure: {
            fields: ['id', 'createdAt', 'updatedAt'],
            confidence: 0.50,
        },
    },

    // DTO - data transfer object
    {
        stereotype: 'DTO',
        annotations: {
            annotations: [
                '@Data', '@Value', '@Builder',
                '@JsonProperty', '@Serializable',
            ],
            confidence: 0.70,
        },
        naming: {
            suffixes: ['DTO', 'Dto', 'Request', 'Response', 'Payload', 'Input', 'Output', 'View', 'VM'],
            patterns: [/^Get\w+Response$/, /^Create\w+Request$/, /^\w+DTO$/],
            confidence: 0.90,
        },
    },

    // Configuration - config classes
    {
        stereotype: 'Configuration',
        annotations: {
            annotations: [
                '@Configuration', '@ConfigurationProperties', '@Bean',
                '@Module', '@Settings', '@Config',
                '@EnableAutoConfiguration', '@ComponentScan',
            ],
            confidence: 0.95,
        },
        naming: {
            suffixes: ['Config', 'Configuration', 'Settings', 'Properties', 'Options'],
            confidence: 0.80,
        },
    },

    // Utility - static helper classes
    {
        stereotype: 'Utility',
        annotations: {
            annotations: ['@UtilityClass', '@NoArgsConstructor(access = AccessLevel.PRIVATE)'],
            confidence: 0.90,
        },
        naming: {
            suffixes: ['Utils', 'Util', 'Helper', 'Helpers', 'Utilities', 'Tools'],
            confidence: 0.90,
        },
        structure: {
            // Utility classes typically have mostly static methods
            confidence: 0.70,
        },
    },

    // Factory - factory pattern
    {
        stereotype: 'Factory',
        annotations: {
            annotations: ['@Factory'],
            confidence: 0.90,
        },
        naming: {
            suffixes: ['Factory', 'Creator', 'Builder', 'Maker'],
            patterns: [/^Create\w+$/, /^\w+Factory$/],
            confidence: 0.85,
        },
        structure: {
            methods: ['create', 'build', 'make', 'getInstance', 'newInstance'],
            confidence: 0.70,
        },
    },

    // Builder - builder pattern
    {
        stereotype: 'Builder',
        annotations: {
            annotations: ['@Builder'],
            confidence: 0.95,
        },
        naming: {
            suffixes: ['Builder'],
            confidence: 0.90,
        },
        structure: {
            methods: ['build', 'with', 'set'],
            confidence: 0.70,
        },
    },

    // Middleware - request/response middleware
    {
        stereotype: 'Middleware',
        annotations: {
            annotations: [
                '@Middleware', '@UseInterceptors', '@UseGuards',
                '@UseFilters', '@Intercept',
            ],
            confidence: 0.90,
        },
        naming: {
            suffixes: ['Middleware', 'Interceptor', 'Filter'],
            confidence: 0.85,
        },
        structure: {
            methods: ['intercept', 'use', 'handle', 'invoke'],
            implements: ['Middleware', 'NestMiddleware', 'Interceptor'],
            confidence: 0.70,
        },
    },

    // Guard - authorization guards
    {
        stereotype: 'Guard',
        annotations: {
            annotations: ['@Guard', '@CanActivate', '@Authorize'],
            confidence: 0.90,
        },
        naming: {
            suffixes: ['Guard', 'AuthGuard', 'RoleGuard'],
            confidence: 0.85,
        },
        structure: {
            methods: ['canActivate', 'authorize', 'validate'],
            implements: ['CanActivate', 'Guard', 'IAuthorizationHandler'],
            confidence: 0.70,
        },
    },

    // Filter - exception/request filters
    {
        stereotype: 'Filter',
        annotations: {
            annotations: ['@ExceptionHandler', '@Catch', '@Filter'],
            confidence: 0.90,
        },
        naming: {
            suffixes: ['Filter', 'ExceptionFilter', 'ExceptionHandler'],
            confidence: 0.80,
        },
        structure: {
            methods: ['catch', 'filter', 'doFilter', 'handleException'],
            implements: ['ExceptionFilter', 'Filter', 'IExceptionHandler'],
            confidence: 0.70,
        },
    },

    // Validator - validation classes
    {
        stereotype: 'Validator',
        annotations: {
            annotations: ['@Validator', '@Valid', '@Validated'],
            confidence: 0.85,
        },
        naming: {
            suffixes: ['Validator', 'Validation', 'Constraint'],
            confidence: 0.85,
        },
        structure: {
            methods: ['validate', 'isValid', 'check'],
            implements: ['Validator', 'ConstraintValidator', 'IValidator'],
            confidence: 0.70,
        },
    },

    // Mapper - object mappers
    {
        stereotype: 'Mapper',
        annotations: {
            annotations: ['@Mapper', '@Mapping'],
            confidence: 0.95,
        },
        naming: {
            suffixes: ['Mapper', 'Converter', 'Transformer', 'Assembler'],
            confidence: 0.85,
        },
        structure: {
            methods: ['map', 'convert', 'transform', 'toEntity', 'toDto', 'from'],
            implements: ['Mapper', 'Converter', 'IMapper'],
            confidence: 0.70,
        },
    },

    // Client - external service clients
    {
        stereotype: 'Client',
        annotations: {
            annotations: ['@FeignClient', '@WebClient', '@HttpClient'],
            confidence: 0.95,
        },
        naming: {
            suffixes: ['Client', 'Api', 'Gateway', 'Proxy', 'Adapter'],
            patterns: [/^\w+Client$/, /^\w+Api$/],
            confidence: 0.80,
        },
    },

    // Handler - event/message handlers
    {
        stereotype: 'Handler',
        annotations: {
            annotations: [
                '@EventHandler', '@MessageHandler', '@CommandHandler',
                '@EventListener', '@KafkaListener', '@RabbitListener',
            ],
            confidence: 0.95,
        },
        naming: {
            suffixes: ['Handler', 'Listener', 'Consumer', 'Subscriber'],
            confidence: 0.80,
        },
        structure: {
            methods: ['handle', 'on', 'process', 'consume'],
            confidence: 0.60,
        },
    },

    // Provider - dependency providers
    {
        stereotype: 'Provider',
        annotations: {
            annotations: ['@Provider', '@Provides', '@Bean'],
            confidence: 0.85,
        },
        naming: {
            suffixes: ['Provider', 'Supplier'],
            confidence: 0.80,
        },
        structure: {
            methods: ['provide', 'get', 'supply'],
            confidence: 0.60,
        },
    },

    // Module - framework modules
    {
        stereotype: 'Module',
        annotations: {
            annotations: ['@Module', '@NgModule'],
            confidence: 0.95,
        },
        naming: {
            suffixes: ['Module'],
            confidence: 0.70,
        },
    },
];

// =============================================================================
// Stereotype Detector Class
// =============================================================================

export class StereotypeDetector {
    private logger: winston.Logger;

    constructor(logger: winston.Logger) {
        this.logger = logger;
    }

    /**
     * Detect stereotype for a class/module node.
     */
    detectStereotype(node: AstNode): {
        stereotype: Stereotype;
        confidence: number;
        evidence: string[];
    } {
        const candidates: Array<{
            stereotype: Stereotype;
            confidence: number;
            evidence: string[];
        }> = [];

        for (const config of STEREOTYPE_CONFIGS) {
            const result = this.matchConfig(node, config);
            if (result.confidence > 0) {
                candidates.push({
                    stereotype: config.stereotype,
                    confidence: result.confidence,
                    evidence: result.evidence,
                });
            }
        }

        // Sort by confidence and return the best match
        candidates.sort((a, b) => b.confidence - a.confidence);

        if (candidates.length > 0 && candidates[0].confidence >= 0.5) {
            return candidates[0];
        }

        return {
            stereotype: 'Unknown',
            confidence: 0,
            evidence: [],
        };
    }

    /**
     * Match a node against a stereotype configuration.
     */
    private matchConfig(
        node: AstNode,
        config: StereotypeConfig
    ): { confidence: number; evidence: string[] } {
        let totalConfidence = 0;
        const evidence: string[] = [];
        let matchCount = 0;

        // Check annotations
        const annotationMatch = this.matchAnnotations(node, config.annotations);
        if (annotationMatch.matched) {
            totalConfidence += annotationMatch.confidence;
            evidence.push(...annotationMatch.evidence);
            matchCount++;
        }

        // Check naming patterns
        const namingMatch = this.matchNaming(node.name, config.naming);
        if (namingMatch.matched) {
            totalConfidence += namingMatch.confidence;
            evidence.push(...namingMatch.evidence);
            matchCount++;
        }

        // Check structure patterns
        if (config.structure) {
            const structureMatch = this.matchStructure(node, config.structure);
            if (structureMatch.matched) {
                totalConfidence += structureMatch.confidence;
                evidence.push(...structureMatch.evidence);
                matchCount++;
            }
        }

        // Calculate average confidence if multiple matches
        const avgConfidence = matchCount > 0 ? totalConfidence / matchCount : 0;

        // Boost confidence for multiple matches
        const boostedConfidence = matchCount > 1
            ? Math.min(avgConfidence * (1 + (matchCount - 1) * 0.1), 1.0)
            : avgConfidence;

        return {
            confidence: boostedConfidence,
            evidence,
        };
    }

    /**
     * Match node against annotation patterns.
     */
    private matchAnnotations(
        node: AstNode,
        pattern: AnnotationPattern
    ): { matched: boolean; confidence: number; evidence: string[] } {
        const evidence: string[] = [];

        // Check node's tags for annotations
        const annotations = this.extractAnnotations(node);

        for (const annotation of annotations) {
            const normalized = annotation.startsWith('@') ? annotation : `@${annotation}`;
            if (pattern.annotations.some(p =>
                p.toLowerCase() === normalized.toLowerCase() ||
                normalized.toLowerCase().includes(p.toLowerCase().replace('@', ''))
            )) {
                evidence.push(`Annotation: ${annotation}`);
            }
        }

        return {
            matched: evidence.length > 0,
            confidence: evidence.length > 0 ? pattern.confidence : 0,
            evidence,
        };
    }

    /**
     * Extract annotations from a node.
     */
    private extractAnnotations(node: AstNode): string[] {
        const annotations: string[] = [];

        // Check modifierFlags for annotations
        if (node.modifierFlags) {
            for (const flag of node.modifierFlags) {
                if (flag.startsWith('@')) {
                    annotations.push(flag);
                }
            }
        }

        // Check properties for annotations
        if (node.properties?.annotations) {
            for (const anno of node.properties.annotations as AnnotationInfo[]) {
                annotations.push(anno.name);
            }
        }

        // Check tags for decorator-like annotations
        if (node.tags) {
            for (const tag of node.tags) {
                if (tag.tag === 'decorator' || tag.tag === 'annotation') {
                    if (tag.name) annotations.push(tag.name);
                }
            }
        }

        // Check documentation for annotation patterns
        if (node.docComment) {
            const annoMatches = node.docComment.match(/@\w+/g);
            if (annoMatches) {
                annotations.push(...annoMatches);
            }
        }

        return annotations;
    }

    /**
     * Match node name against naming patterns.
     */
    private matchNaming(
        name: string,
        pattern: NamingPattern
    ): { matched: boolean; confidence: number; evidence: string[] } {
        const evidence: string[] = [];

        // Check suffixes
        for (const suffix of pattern.suffixes) {
            if (name.endsWith(suffix)) {
                evidence.push(`Name ends with: ${suffix}`);
                break;
            }
        }

        // Check prefixes
        if (pattern.prefixes) {
            for (const prefix of pattern.prefixes) {
                if (name.startsWith(prefix)) {
                    evidence.push(`Name starts with: ${prefix}`);
                    break;
                }
            }
        }

        // Check regex patterns
        if (pattern.patterns) {
            for (const regex of pattern.patterns) {
                if (regex.test(name)) {
                    evidence.push(`Name matches pattern: ${regex.source}`);
                    break;
                }
            }
        }

        return {
            matched: evidence.length > 0,
            confidence: evidence.length > 0 ? pattern.confidence : 0,
            evidence,
        };
    }

    /**
     * Match node against structure patterns.
     */
    private matchStructure(
        node: AstNode,
        pattern: StructurePattern
    ): { matched: boolean; confidence: number; evidence: string[] } {
        const evidence: string[] = [];

        // Check implements/extends
        if (pattern.implements && node.implementsInterfaces) {
            for (const iface of pattern.implements) {
                if (node.implementsInterfaces.some(i =>
                    i.toLowerCase().includes(iface.toLowerCase())
                )) {
                    evidence.push(`Implements: ${iface}`);
                }
            }
        }

        // Check for methods in properties
        if (pattern.methods && node.properties?.methods) {
            const methods = node.properties.methods as string[];
            for (const method of pattern.methods) {
                if (methods.some(m => m.toLowerCase().includes(method.toLowerCase()))) {
                    evidence.push(`Has method: ${method}`);
                }
            }
        }

        // Check for fields in properties
        if (pattern.fields && node.properties?.fields) {
            const fields = node.properties.fields as string[];
            for (const field of pattern.fields) {
                if (fields.some(f => f.toLowerCase() === field.toLowerCase())) {
                    evidence.push(`Has field: ${field}`);
                }
            }
        }

        return {
            matched: evidence.length > 0,
            confidence: evidence.length > 0 ? pattern.confidence : 0,
            evidence,
        };
    }

    /**
     * Batch detect stereotypes for multiple nodes.
     */
    detectStereotypes(nodes: AstNode[]): Map<string, Stereotype> {
        const results = new Map<string, Stereotype>();

        for (const node of nodes) {
            // Only detect for class-like nodes
            if (this.isClassLikeNode(node)) {
                const detection = this.detectStereotype(node);
                if (detection.confidence >= 0.5) {
                    results.set(node.entityId, detection.stereotype);
                    this.logger.debug(`Detected stereotype ${detection.stereotype} for ${node.name}`, {
                        confidence: detection.confidence,
                        evidence: detection.evidence,
                    });
                }
            }
        }

        return results;
    }

    /**
     * Check if a node is a class-like construct.
     */
    private isClassLikeNode(node: AstNode): boolean {
        const classKinds = [
            'Class', 'JavaClass', 'CppClass', 'CSharpClass',
            'GoStruct', 'Interface', 'JavaInterface', 'CSharpInterface',
            'GoInterface', 'Component',
        ];
        return classKinds.includes(node.kind);
    }
}

// =============================================================================
// Convenience Functions
// =============================================================================

/**
 * Create a stereotype detector.
 */
export function createStereotypeDetector(logger: winston.Logger): StereotypeDetector {
    return new StereotypeDetector(logger);
}

/**
 * Detect stereotype for a single node.
 */
export function detectStereotype(
    node: AstNode,
    logger: winston.Logger
): Stereotype {
    const detector = new StereotypeDetector(logger);
    const result = detector.detectStereotype(node);
    return result.stereotype;
}

/**
 * Check if a stereotype indicates a "layer" in layered architecture.
 */
export function getArchitectureLayer(stereotype: Stereotype): string | undefined {
    const layerMapping: Record<Stereotype, string | undefined> = {
        'Controller': 'presentation',
        'Service': 'business',
        'Repository': 'data',
        'Entity': 'domain',
        'DTO': 'presentation',
        'Configuration': 'infrastructure',
        'Utility': 'infrastructure',
        'Factory': 'business',
        'Builder': 'business',
        'Middleware': 'presentation',
        'Guard': 'presentation',
        'Filter': 'presentation',
        'Validator': 'business',
        'Mapper': 'business',
        'Client': 'infrastructure',
        'Handler': 'business',
        'Provider': 'infrastructure',
        'Module': 'infrastructure',
        'Unknown': undefined,
    };
    return layerMapping[stereotype];
}

/**
 * Get stereotype statistics for a list of nodes.
 */
export function getStereotypeStats(nodes: AstNode[]): Record<Stereotype, number> {
    const stats: Record<string, number> = {};

    for (const node of nodes) {
        if (node.stereotype) {
            stats[node.stereotype] = (stats[node.stereotype] || 0) + 1;
        }
    }

    return stats as Record<Stereotype, number>;
}
