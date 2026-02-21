// src/analyzer/parsers/shared-component-detector.ts

import {
    AstNode,
    RelationshipInfo,
    SharedComponentNode,
    InstanceCounter,
} from '../types.js';
import { generateEntityId, generateInstanceId } from '../parser-utils.js';
import { createContextLogger } from '../../utils/logger.js';

const logger = createContextLogger('SharedComponentDetector');

/**
 * Detects and indexes shared components (utilities, helpers, validators, etc.)
 * that are used across multiple features.
 */
export class SharedComponentDetector {
    private instanceCounter: InstanceCounter = { count: 0 };
    private now: string = new Date().toISOString();

    // Patterns that indicate shared/utility classes
    private readonly sharedPatterns: RegExp[] = [
        /Util(s)?$/i,           // PointUtils, StringUtils
        /Helper$/i,             // ValidationHelper
        /Converter$/i,          // DateConverter
        /Formatter$/i,          // NumberFormatter
        /Constants?$/i,         // AppConstants
        /Config(uration)?$/i,   // PointConfiguration
        /Common/i,              // CommonValidator
        /^Base[A-Z]/,           // BaseService
        /^Abstract[A-Z]/,       // AbstractValidator
        /Builder$/i,            // PointBuilder
        /Factory$/i,            // ServiceFactory
        /Provider$/i,           // DataProvider
        /Adapter$/i,            // ApiAdapter
        /Handler$/i,            // ErrorHandler
        /Wrapper$/i,            // ResponseWrapper
    ];

    // Domain keywords for business domain inference
    private readonly domainKeywords: Record<string, string[]> = {
        point: ['point', 'poi', 'location', 'coordinate'],
        legalEntity: ['legalentity', 'legal', 'entity', 'party', 'company'],
        meter: ['meter', 'station', 'measurement'],
        contact: ['contact', 'address', 'phone', 'email'],
        survey: ['survey', 'questionnaire', 'form'],
        edi: ['edi', 'trading', 'partner', 'dataset'],
        farmtap: ['farmtap', 'farm', 'tap', 'region'],
    };

    /**
     * Detect shared components from a list of Java classes.
     */
    detectSharedComponents(javaClasses: AstNode[]): {
        nodes: SharedComponentNode[];
        relationships: RelationshipInfo[];
    } {
        const nodes: SharedComponentNode[] = [];
        const relationships: RelationshipInfo[] = [];

        logger.info(`Scanning ${javaClasses.length} classes for shared components`);

        for (const cls of javaClasses) {
            if (this.isSharedComponent(cls.name)) {
                const componentType = this.inferComponentType(cls.name);
                const businessDomains = this.inferBusinessDomains(cls);

                const sharedNode: SharedComponentNode = {
                    id: generateInstanceId(this.instanceCounter, 'sharedcomponent', cls.name),
                    entityId: generateEntityId('sharedcomponent', cls.entityId),
                    kind: 'SharedComponent',
                    name: cls.name,
                    filePath: cls.filePath,
                    startLine: cls.startLine,
                    endLine: cls.endLine,
                    startColumn: cls.startColumn,
                    endColumn: cls.endColumn,
                    language: cls.language,
                    createdAt: this.now,
                    properties: {
                        componentType,
                        usedByFeatures: [], // Will be populated later by cross-reference analysis
                        usageCount: 0,      // Will be computed later
                        businessDomains,
                        isCrossCutting: this.isCrossCuttingConcern(cls.name),
                    },
                };

                nodes.push(sharedNode);

                // Create relationship from original class to shared component
                relationships.push({
                    id: generateInstanceId(this.instanceCounter, 'is_shared', cls.name),
                    entityId: generateEntityId('is_shared', `${cls.entityId}:${sharedNode.entityId}`),
                    type: 'IS_SHARED_COMPONENT',
                    sourceId: cls.entityId,
                    targetId: sharedNode.entityId,
                    createdAt: this.now,
                    weight: 5,
                });

                logger.debug(`Detected shared component: ${cls.name} (${componentType})`);
            }
        }

        logger.info(`Detected ${nodes.length} shared components`);
        return { nodes, relationships };
    }

    /**
     * Check if a class name matches shared component patterns.
     */
    private isSharedComponent(className: string): boolean {
        return this.sharedPatterns.some(pattern => pattern.test(className));
    }

    /**
     * Infer the type of shared component from its name.
     */
    private inferComponentType(
        className: string
    ): 'utility' | 'helper' | 'validator' | 'converter' | 'formatter' | 'constants' | 'base' | 'abstract' {
        const nameLower = className.toLowerCase();

        if (nameLower.includes('util')) return 'utility';
        if (nameLower.includes('helper')) return 'helper';
        if (nameLower.includes('validator') || nameLower.includes('validation')) return 'validator';
        if (nameLower.includes('converter')) return 'converter';
        if (nameLower.includes('formatter')) return 'formatter';
        if (nameLower.includes('constant')) return 'constants';
        if (className.startsWith('Base')) return 'base';
        if (className.startsWith('Abstract')) return 'abstract';

        return 'utility';
    }

    /**
     * Infer business domains from class name and file path.
     */
    private inferBusinessDomains(cls: AstNode): string[] {
        const domains: string[] = [];
        const nameLower = cls.name.toLowerCase();
        const pathLower = cls.filePath?.toLowerCase() || '';

        for (const [domain, keywords] of Object.entries(this.domainKeywords)) {
            for (const keyword of keywords) {
                if (nameLower.includes(keyword) || pathLower.includes(keyword)) {
                    if (!domains.includes(domain)) {
                        domains.push(domain);
                    }
                    break;
                }
            }
        }

        // Check path segments for domain hints
        const pathSegments = pathLower.split('/');
        for (const segment of pathSegments) {
            for (const [domain, keywords] of Object.entries(this.domainKeywords)) {
                if (keywords.some(kw => segment.includes(kw))) {
                    if (!domains.includes(domain)) {
                        domains.push(domain);
                    }
                }
            }
        }

        return domains;
    }

    /**
     * Check if a component is a cross-cutting concern.
     */
    private isCrossCuttingConcern(className: string): boolean {
        const crossCuttingPatterns = [
            /logger/i,
            /logging/i,
            /audit/i,
            /security/i,
            /auth/i,
            /cache/i,
            /transaction/i,
            /exception/i,
            /error/i,
            /message/i,
            /notification/i,
            /email/i,
            /validation/i,
        ];

        return crossCuttingPatterns.some(pattern => pattern.test(className));
    }

    /**
     * Analyze usage of shared components across features.
     * This should be called after initial detection to populate usage stats.
     */
    analyzeUsage(
        sharedComponents: SharedComponentNode[],
        allRelationships: RelationshipInfo[],
        menuItems: AstNode[]
    ): void {
        // Build a map of component usages
        const usageMap = new Map<string, Set<string>>();

        for (const component of sharedComponents) {
            usageMap.set(component.entityId, new Set());
        }

        // Analyze relationships to find usages
        for (const rel of allRelationships) {
            if (['USES', 'CALLS', 'DEPENDS_ON', 'JAVA_IMPORTS'].includes(rel.type)) {
                // Check if target is a shared component
                const component = sharedComponents.find(c => c.entityId === rel.targetId);
                if (component) {
                    usageMap.get(component.entityId)?.add(rel.sourceId);
                }
            }
        }

        // Update usage counts
        for (const component of sharedComponents) {
            const usages = usageMap.get(component.entityId);
            if (usages) {
                component.properties.usageCount = usages.size;
            }
        }

        logger.info(`Analyzed usage for ${sharedComponents.length} shared components`);
    }
}

export default SharedComponentDetector;
