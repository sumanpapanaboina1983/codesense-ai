// src/analyzer/integrators/menu-screen-linker.ts

import {
    AstNode,
    RelationshipInfo,
    MenuItemNode,
    ScreenNode,
    WebFlowDefinitionNode,
    JSPPageNode,
    JavaClassNode,
    InstanceCounter,
} from '../types.js';
import { generateEntityId, generateInstanceId } from '../parser-utils.js';
import { createContextLogger } from '../../utils/logger.js';

const logger = createContextLogger('MenuScreenLinker');

/**
 * Links menu items to their corresponding screens, WebFlows, JSPs, and action classes.
 * This creates the navigation-to-code traceability required for feature discovery.
 */
export class MenuScreenLinker {
    private instanceCounter: InstanceCounter = { count: 0 };
    private now: string = new Date().toISOString();

    /**
     * Link all menu items to their corresponding code components.
     */
    linkMenusToCode(
        menuItems: MenuItemNode[],
        screens: ScreenNode[],
        webFlows: WebFlowDefinitionNode[],
        jspPages: JSPPageNode[],
        javaClasses: AstNode[]
    ): RelationshipInfo[] {
        const relationships: RelationshipInfo[] = [];

        logger.info(`Linking ${menuItems.length} menu items to ${screens.length} screens, ${webFlows.length} flows, ${jspPages.length} JSPs`);

        for (const menuItem of menuItems) {
            const { flowId, viewStateId } = menuItem.properties;

            if (!flowId) continue;

            // 1. Link MenuItem -> Screen (most specific)
            if (viewStateId) {
                const screen = screens.find(s =>
                    s.properties.flowId === flowId &&
                    s.properties.screenId === viewStateId
                );
                if (screen) {
                    relationships.push(this.createRelationship(
                        'MENU_OPENS_SCREEN',
                        menuItem.entityId,
                        screen.entityId,
                        { menuLabel: menuItem.properties.label, screenId: screen.properties.screenId }
                    ));
                    logger.debug(`Linked menu "${menuItem.properties.label}" to screen "${screen.properties.screenId}"`);

                    // Also link to the screen's action class
                    if (screen.properties.actionClass) {
                        const actionClass = javaClasses.find(c =>
                            c.name.toLowerCase() === screen.properties.actionClass?.toLowerCase() ||
                            c.name === screen.properties.actionClass
                        );
                        if (actionClass) {
                            relationships.push(this.createRelationship(
                                'SCREEN_CALLS_ACTION',
                                screen.entityId,
                                actionClass.entityId,
                                { actionClass: screen.properties.actionClass }
                            ));
                        }
                    }

                    // Link screen to JSPs
                    for (const jspName of screen.properties.jsps) {
                        const jsp = jspPages.find(j =>
                            j.name.toLowerCase().includes(jspName.toLowerCase().replace('.jsp', '')) ||
                            j.name === jspName
                        );
                        if (jsp) {
                            relationships.push(this.createRelationship(
                                'SCREEN_RENDERS_JSP',
                                screen.entityId,
                                jsp.entityId,
                                { jspName }
                            ));
                        }
                    }
                }
            }

            // 2. Link MenuItem -> WebFlowDefinition
            const webFlow = webFlows.find(w => w.properties.flowId === flowId || w.name === flowId);
            if (webFlow) {
                relationships.push(this.createRelationship(
                    'MENU_OPENS_FLOW',
                    menuItem.entityId,
                    webFlow.entityId,
                    { flowId }
                ));
            }
        }

        // 3. Link screens to their JSPs and action classes (for screens not covered by menu items)
        for (const screen of screens) {
            // Link to action class
            if (screen.properties.actionClass) {
                const actionClass = javaClasses.find(c =>
                    c.name.toLowerCase() === screen.properties.actionClass?.toLowerCase() ||
                    c.name === screen.properties.actionClass
                );
                if (actionClass) {
                    // Check if relationship already exists
                    const exists = relationships.some(r =>
                        r.type === 'SCREEN_CALLS_ACTION' &&
                        r.sourceId === screen.entityId &&
                        r.targetId === actionClass.entityId
                    );
                    if (!exists) {
                        relationships.push(this.createRelationship(
                            'SCREEN_CALLS_ACTION',
                            screen.entityId,
                            actionClass.entityId,
                            { actionClass: screen.properties.actionClass }
                        ));
                    }
                }
            }

            // Link to JSPs
            for (const jspName of screen.properties.jsps) {
                const jsp = jspPages.find(j =>
                    j.name.toLowerCase().includes(jspName.toLowerCase().replace('.jsp', '')) ||
                    j.name === jspName
                );
                if (jsp) {
                    const exists = relationships.some(r =>
                        r.type === 'SCREEN_RENDERS_JSP' &&
                        r.sourceId === screen.entityId &&
                        r.targetId === jsp.entityId
                    );
                    if (!exists) {
                        relationships.push(this.createRelationship(
                            'SCREEN_RENDERS_JSP',
                            screen.entityId,
                            jsp.entityId,
                            { jspName }
                        ));
                    }
                }
            }
        }

        logger.info(`Created ${relationships.length} menu-screen-code relationships`);
        return relationships;
    }

    /**
     * Find all sub-features (screens) for a given menu item.
     */
    getSubFeatures(
        menuItem: MenuItemNode,
        screens: ScreenNode[]
    ): ScreenNode[] {
        const { flowId } = menuItem.properties;

        if (!flowId) return [];

        // Get all screens in the same flow
        return screens.filter(s => s.properties.flowId === flowId);
    }

    /**
     * Build a complete feature context from a menu item.
     */
    buildFeatureContext(
        menuItem: MenuItemNode,
        screens: ScreenNode[],
        javaClasses: AstNode[]
    ): {
        menuItem: MenuItemNode;
        mainScreen: ScreenNode | undefined;
        subScreens: ScreenNode[];
        actionClasses: AstNode[];
        methods: string[];
    } {
        const { flowId, viewStateId } = menuItem.properties;

        // Find main screen
        const mainScreen = viewStateId
            ? screens.find(s => s.properties.flowId === flowId && s.properties.screenId === viewStateId)
            : undefined;

        // Find all screens in the flow (sub-features)
        const subScreens = screens.filter(s =>
            s.properties.flowId === flowId &&
            s.properties.screenId !== viewStateId
        );

        // Collect all action classes from screens
        const actionClassNames = new Set<string>();
        const allScreens = mainScreen ? [mainScreen, ...subScreens] : subScreens;
        for (const screen of allScreens) {
            if (screen.properties.actionClass) {
                actionClassNames.add(screen.properties.actionClass);
            }
        }

        // Find action class nodes
        const actionClasses = javaClasses.filter(c =>
            actionClassNames.has(c.name) ||
            Array.from(actionClassNames).some(name =>
                c.name.toLowerCase() === name.toLowerCase()
            )
        );

        // Collect all methods
        const methods: string[] = [];
        for (const screen of allScreens) {
            methods.push(...screen.properties.actionMethods);
        }

        return {
            menuItem,
            mainScreen,
            subScreens,
            actionClasses,
            methods: [...new Set(methods)],
        };
    }

    /**
     * Create a relationship with properties.
     */
    private createRelationship(
        type: string,
        sourceId: string,
        targetId: string,
        properties?: Record<string, any>
    ): RelationshipInfo {
        return {
            id: generateInstanceId(this.instanceCounter, type.toLowerCase(), `${sourceId}:${targetId}`),
            entityId: generateEntityId(type.toLowerCase(), `${sourceId}:${targetId}`),
            type,
            sourceId,
            targetId,
            createdAt: this.now,
            properties,
            weight: 10,
        };
    }
}

export default MenuScreenLinker;
