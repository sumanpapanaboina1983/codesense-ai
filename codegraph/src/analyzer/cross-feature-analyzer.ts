// src/analyzer/cross-feature-analyzer.ts

import {
    AstNode,
    RelationshipInfo,
    MenuItemNode,
    ScreenNode,
    CrossFeatureRelationship,
    InstanceCounter,
} from './types.js';
import { generateEntityId, generateInstanceId } from './parser-utils.js';
import { createContextLogger } from '../utils/logger.js';

const logger = createContextLogger('CrossFeatureAnalyzer');

/**
 * Analyzes cross-feature dependencies and relationships.
 * This identifies how features affect each other through shared entities,
 * services, and cascade effects.
 */
export class CrossFeatureAnalyzer {
    private instanceCounter: InstanceCounter = { count: 0 };
    private now: string = new Date().toISOString();

    /**
     * Analyze cross-feature dependencies between all screens/features.
     */
    analyzeCrossFeatureDependencies(
        menuItems: MenuItemNode[],
        screens: ScreenNode[],
        entities: AstNode[],
        services: AstNode[],
        relationships: RelationshipInfo[]
    ): {
        crossFeatureRelations: CrossFeatureRelationship[];
        sharedEntities: Map<string, string[]>;  // entity -> features
        sharedServices: Map<string, string[]>;  // service -> features
    } {
        logger.info(`Analyzing cross-feature dependencies for ${screens.length} screens`);

        const crossFeatureRelations: CrossFeatureRelationship[] = [];
        const sharedEntities = new Map<string, string[]>();
        const sharedServices = new Map<string, string[]>();

        // Build feature-to-component mapping
        const featureComponents = this.mapFeaturesToComponents(screens, relationships);

        // Find shared entities
        const entityToFeatures = this.findSharedComponents(
            featureComponents,
            entities.map(e => e.name),
            'entity'
        );
        for (const [entity, features] of entityToFeatures) {
            sharedEntities.set(entity, features);
            if (features.length > 1) {
                // Create cross-feature relationships for shared entities
                for (let i = 0; i < features.length; i++) {
                    for (let j = i + 1; j < features.length; j++) {
                        crossFeatureRelations.push({
                            sourceFeature: features[i],
                            targetFeature: features[j],
                            relationshipType: 'SHARES_ENTITY',
                            sharedComponent: entity,
                            implication: `Changes to ${entity} may affect both ${features[i]} and ${features[j]}`,
                        });
                    }
                }
            }
        }

        // Find shared services
        const serviceToFeatures = this.findSharedComponents(
            featureComponents,
            services.map(s => s.name),
            'service'
        );
        for (const [service, features] of serviceToFeatures) {
            sharedServices.set(service, features);
            if (features.length > 1) {
                // Create cross-feature relationships for shared services
                for (let i = 0; i < features.length; i++) {
                    for (let j = i + 1; j < features.length; j++) {
                        crossFeatureRelations.push({
                            sourceFeature: features[i],
                            targetFeature: features[j],
                            relationshipType: 'SHARES_SERVICE',
                            sharedComponent: service,
                            implication: `Both features depend on ${service}`,
                        });
                    }
                }
            }
        }

        // Find cascade relationships based on entity relationships
        const cascadeRelations = this.findCascadeRelationships(entities, relationships);
        crossFeatureRelations.push(...cascadeRelations);

        logger.info(`Found ${crossFeatureRelations.length} cross-feature relationships`);
        logger.info(`Found ${sharedEntities.size} shared entities, ${sharedServices.size} shared services`);

        return { crossFeatureRelations, sharedEntities, sharedServices };
    }

    /**
     * Map features (screens) to their components through relationships.
     */
    private mapFeaturesToComponents(
        screens: ScreenNode[],
        relationships: RelationshipInfo[]
    ): Map<string, Set<string>> {
        const featureComponents = new Map<string, Set<string>>();

        for (const screen of screens) {
            const featureId = `${screen.properties.flowId}:${screen.properties.screenId}`;
            const components = new Set<string>();

            // Add action class
            if (screen.properties.actionClass) {
                components.add(screen.properties.actionClass);
            }

            // Find connected components through relationships
            for (const rel of relationships) {
                if (rel.sourceId === screen.entityId || rel.targetId === screen.entityId) {
                    // Add related component names (extract from entity IDs)
                    const relatedId = rel.sourceId === screen.entityId ? rel.targetId : rel.sourceId;
                    const componentName = this.extractNameFromEntityId(relatedId);
                    if (componentName) {
                        components.add(componentName);
                    }
                }
            }

            featureComponents.set(featureId, components);
        }

        return featureComponents;
    }

    /**
     * Find components shared between multiple features.
     */
    private findSharedComponents(
        featureComponents: Map<string, Set<string>>,
        componentNames: string[],
        componentType: string
    ): Map<string, string[]> {
        const componentToFeatures = new Map<string, string[]>();

        for (const componentName of componentNames) {
            const features: string[] = [];

            for (const [featureId, components] of featureComponents) {
                // Check if this feature uses this component
                for (const comp of components) {
                    if (comp.toLowerCase() === componentName.toLowerCase() ||
                        comp.toLowerCase().includes(componentName.toLowerCase())) {
                        features.push(featureId);
                        break;
                    }
                }
            }

            if (features.length > 0) {
                componentToFeatures.set(componentName, features);
            }
        }

        return componentToFeatures;
    }

    /**
     * Find cascade relationships based on entity foreign keys and annotations.
     */
    private findCascadeRelationships(
        entities: AstNode[],
        relationships: RelationshipInfo[]
    ): CrossFeatureRelationship[] {
        const cascadeRelations: CrossFeatureRelationship[] = [];

        // Find entity-to-entity relationships that might indicate cascades
        for (const rel of relationships) {
            if (rel.type === 'REFERENCES' || rel.type === 'HAS_FIELD') {
                // Check if this represents a cascade relationship
                const sourceEntity = entities.find(e => e.entityId === rel.sourceId);
                const targetEntity = entities.find(e => e.entityId === rel.targetId);

                if (sourceEntity && targetEntity) {
                    // Check for cascade annotations in properties
                    const hasCascade = rel.properties?.cascadeType ||
                        sourceEntity.properties?.annotations?.includes('cascade');

                    if (hasCascade) {
                        cascadeRelations.push({
                            sourceFeature: sourceEntity.name,
                            targetFeature: targetEntity.name,
                            relationshipType: 'CASCADES_TO',
                            sharedComponent: `${sourceEntity.name} -> ${targetEntity.name}`,
                            implication: `Changes to ${sourceEntity.name} may cascade to ${targetEntity.name}`,
                        });
                    }
                }
            }
        }

        return cascadeRelations;
    }

    /**
     * Extract component name from entity ID.
     */
    private extractNameFromEntityId(entityId: string): string | null {
        // Entity IDs typically have format: type:repoId:path:name
        const parts = entityId.split(':');
        return parts.length > 0 ? parts[parts.length - 1] : null;
    }

    /**
     * Get features that depend on a specific component.
     */
    getDependentFeatures(
        componentName: string,
        featureComponents: Map<string, Set<string>>
    ): string[] {
        const dependentFeatures: string[] = [];

        for (const [featureId, components] of featureComponents) {
            for (const comp of components) {
                if (comp.toLowerCase().includes(componentName.toLowerCase())) {
                    dependentFeatures.push(featureId);
                    break;
                }
            }
        }

        return dependentFeatures;
    }

    /**
     * Build a dependency graph for visualization.
     */
    buildDependencyGraph(
        crossFeatureRelations: CrossFeatureRelationship[]
    ): { nodes: string[]; edges: Array<{ from: string; to: string; type: string }> } {
        const nodes = new Set<string>();
        const edges: Array<{ from: string; to: string; type: string }> = [];

        for (const rel of crossFeatureRelations) {
            nodes.add(rel.sourceFeature);
            nodes.add(rel.targetFeature);
            edges.push({
                from: rel.sourceFeature,
                to: rel.targetFeature,
                type: rel.relationshipType,
            });
        }

        return { nodes: Array.from(nodes), edges };
    }
}

export default CrossFeatureAnalyzer;
