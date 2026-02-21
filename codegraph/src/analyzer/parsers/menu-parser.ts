// src/analyzer/parsers/menu-parser.ts

import fs from 'fs/promises';
import path from 'path';
import { DOMParser, XMLSerializer } from '@xmldom/xmldom';
import xpath from 'xpath';
import { FileInfo } from '../../scanner/file-scanner.js';
import {
    AstNode,
    RelationshipInfo,
    SingleFileParseResult,
    FileNode,
    MenuItemNode,
    MenuHierarchyNode,
    InstanceCounter,
} from '../types.js';
import { generateEntityId, generateInstanceId, ensureTempDir, getTempFilePath } from '../parser-utils.js';
import { createContextLogger } from '../../utils/logger.js';

const logger = createContextLogger('MenuParser');

/**
 * Parses Spring menu-config.xml files to extract menu structure.
 * This provides user-facing navigation labels that map to WebFlows and screens.
 */
export class MenuParser {
    private repositoryId: string = '';

    /**
     * Sets the repository ID for entity ID generation.
     */
    setRepositoryId(repoId: string): void {
        this.repositoryId = repoId;
    }

    /**
     * Check if a file is a menu configuration file.
     */
    isMenuConfigFile(filePath: string): boolean {
        const fileName = path.basename(filePath).toLowerCase();
        const patterns = [
            'menu-config.xml',
            'menu.xml',
            'navigation.xml',
            'nav-config.xml',
            'menu-items.xml',
        ];
        return patterns.some(pattern => fileName.includes(pattern.replace('.xml', '')));
    }

    /**
     * Parse a menu configuration file.
     */
    async parseFile(file: FileInfo): Promise<string | null> {
        if (!this.isMenuConfigFile(file.path)) {
            return null;
        }

        try {
            await ensureTempDir();
            const content = await fs.readFile(file.path, 'utf-8');
            const result = await this.parseMenuConfig(content, file.path);

            if (result.nodes.length === 0) {
                logger.debug(`No menu items found in ${file.path}`);
                return null;
            }

            const tempFilePath = getTempFilePath(file.path);
            await fs.writeFile(tempFilePath, JSON.stringify(result, null, 2));
            logger.info(`Parsed ${result.nodes.length} menu items from ${file.path}`);
            return tempFilePath;
        } catch (error: any) {
            logger.error(`Failed to parse menu config ${file.path}: ${error.message}`);
            return null;
        }
    }

    /**
     * Parse the menu configuration XML content.
     */
    private async parseMenuConfig(content: string, filePath: string): Promise<SingleFileParseResult> {
        const nodes: AstNode[] = [];
        const relationships: RelationshipInfo[] = [];
        const now = new Date().toISOString();
        const counter: InstanceCounter = { count: 0 };

        // Create file node
        const fileEntityId = generateEntityId('file', filePath, this.repositoryId);
        const fileNode: FileNode = {
            id: generateInstanceId(counter, 'file', path.basename(filePath)),
            entityId: fileEntityId,
            kind: 'File',
            name: path.basename(filePath),
            filePath,
            startLine: 1,
            endLine: content.split('\n').length,
            startColumn: 0,
            endColumn: 0,
            language: 'XML',
            loc: content.split('\n').length,
            createdAt: now,
        };
        nodes.push(fileNode);

        // Parse XML
        const doc = new DOMParser().parseFromString(content, 'text/xml');

        // Find all MenuItem beans
        const menuBeans = this.findMenuItemBeans(doc);

        if (menuBeans.length === 0) {
            logger.debug(`No MenuItem beans found in ${filePath}`);
            return { filePath, nodes, relationships };
        }

        // Track menu hierarchy
        const topLevelMenus: string[] = [];
        const menuItemMap = new Map<string, MenuItemNode>();

        // Process each menu bean
        for (const bean of menuBeans) {
            const menuItems = this.extractMenuItems(bean, filePath, counter, now);

            for (const menuItem of menuItems) {
                nodes.push(menuItem);
                menuItemMap.set(menuItem.properties.label, menuItem);

                // Track top-level menus
                if (menuItem.properties.menuLevel === 1) {
                    topLevelMenus.push(menuItem.properties.label);
                }

                // Create relationship to parent menu
                if (menuItem.properties.parentMenu) {
                    const parentItem = menuItemMap.get(menuItem.properties.parentMenu);
                    if (parentItem) {
                        relationships.push({
                            id: generateInstanceId(counter, 'rel', `parent-${menuItem.name}`),
                            entityId: generateEntityId('rel', `${parentItem.entityId}:PARENT_MENU_ITEM:${menuItem.entityId}`, this.repositoryId),
                            type: 'PARENT_MENU_ITEM',
                            sourceId: parentItem.entityId,
                            targetId: menuItem.entityId,
                            createdAt: now,
                        });
                    }
                }

                // Create relationship to file
                relationships.push({
                    id: generateInstanceId(counter, 'rel', `file-${menuItem.name}`),
                    entityId: generateEntityId('rel', `${fileEntityId}:CONTAINS:${menuItem.entityId}`, this.repositoryId),
                    type: 'CONTAINS',
                    sourceId: fileEntityId,
                    targetId: menuItem.entityId,
                    createdAt: now,
                });
            }
        }

        // Create menu hierarchy node
        if (topLevelMenus.length > 0) {
            const hierarchyNode: MenuHierarchyNode = {
                id: generateInstanceId(counter, 'menuhierarchy', 'main'),
                entityId: generateEntityId('menuhierarchy', filePath, this.repositoryId),
                kind: 'MenuHierarchy',
                name: 'MainMenu',
                filePath,
                startLine: 1,
                endLine: 1,
                startColumn: 0,
                endColumn: 0,
                language: 'XML',
                createdAt: now,
                properties: {
                    topLevelMenus,
                    totalItems: menuItemMap.size,
                    configSource: filePath,
                },
            };
            nodes.push(hierarchyNode);

            // Link hierarchy to top-level menu items
            for (const menuLabel of topLevelMenus) {
                const menuItem = menuItemMap.get(menuLabel);
                if (menuItem) {
                    relationships.push({
                        id: generateInstanceId(counter, 'rel', `hierarchy-${menuLabel}`),
                        entityId: generateEntityId('rel', `${hierarchyNode.entityId}:HAS_MENU_ITEM:${menuItem.entityId}`, this.repositoryId),
                        type: 'HAS_MENU_ITEM',
                        sourceId: hierarchyNode.entityId,
                        targetId: menuItem.entityId,
                        createdAt: now,
                    });
                }
            }
        }

        return { filePath, nodes, relationships };
    }

    /**
     * Find top-level MenuItem bean definitions in the XML.
     * Only returns beans that are direct children of util:list or the top-level beans element,
     * not nested menu items (those are handled recursively).
     */
    private findMenuItemBeans(doc: Document): Element[] {
        const beans: Element[] = [];
        const processedBeans = new Set<Element>();

        // Look for util:list with id="pleMenu" or similar patterns
        const allLists = doc.getElementsByTagName('list');
        for (let i = 0; i < allLists.length; i++) {
            const list = allLists[i];
            const listId = list.getAttribute('id');

            // Check if this is a top-level menu list (e.g., "pleMenu")
            if (listId && listId.toLowerCase().includes('menu')) {
                // Get direct children beans only
                const childNodes = list.childNodes;
                for (let j = 0; j < childNodes.length; j++) {
                    const child = childNodes[j];
                    if (child.nodeType === 1 && (child as Element).tagName === 'bean') {
                        const bean = child as Element;
                        const classAttr = bean.getAttribute('class');
                        if (classAttr && classAttr.toLowerCase().includes('menuitem')) {
                            if (!processedBeans.has(bean)) {
                                beans.push(bean);
                                processedBeans.add(bean);
                            }
                        }
                    }
                }
            }
        }

        // Also check for util:list elements
        const utilLists = doc.getElementsByTagNameNS('http://www.springframework.org/schema/util', 'list');
        for (let i = 0; i < utilLists.length; i++) {
            const list = utilLists[i];
            const valueType = list.getAttribute('value-type');

            // Check if this list contains MenuItems
            if (valueType && valueType.toLowerCase().includes('menuitem')) {
                // Get direct children beans only
                const childNodes = list.childNodes;
                for (let j = 0; j < childNodes.length; j++) {
                    const child = childNodes[j];
                    if (child.nodeType === 1 && (child as Element).tagName === 'bean') {
                        const bean = child as Element;
                        if (!processedBeans.has(bean)) {
                            beans.push(bean);
                            processedBeans.add(bean);
                        }
                    }
                }
            }
        }

        // Fallback: look for property-based menu items lists
        const properties = doc.getElementsByTagName('property');
        for (let i = 0; i < properties.length; i++) {
            const prop = properties[i];
            if (prop.getAttribute('name') === 'menuItems') {
                const innerList = prop.getElementsByTagName('list');
                if (innerList.length > 0) {
                    const innerBeans = innerList[0].childNodes;
                    for (let j = 0; j < innerBeans.length; j++) {
                        const child = innerBeans[j];
                        if (child.nodeType === 1 && (child as Element).tagName === 'bean') {
                            const bean = child as Element;
                            if (!processedBeans.has(bean)) {
                                beans.push(bean);
                                processedBeans.add(bean);
                            }
                        }
                    }
                }
            }
        }

        logger.info(`Found ${beans.length} top-level MenuItem beans`);
        return beans;
    }

    /**
     * Extract menu items from a bean element.
     * Supports both property-based and constructor-arg based bean definitions.
     */
    private extractMenuItems(
        bean: Element,
        filePath: string,
        counter: InstanceCounter,
        now: string,
        parentMenu?: string,
        level: number = 1
    ): MenuItemNode[] {
        const menuItems: MenuItemNode[] = [];

        // Get bean properties - try property elements first, then constructor-arg
        let label = this.getPropertyValue(bean, 'label') || this.getPropertyValue(bean, 'name') || '';
        let url = this.getPropertyValue(bean, 'url') || this.getPropertyValue(bean, 'href') || '';

        // If not found via properties, try constructor-arg (Spring constructor injection)
        if (!label || !url) {
            const constructorArgs = this.getConstructorArgs(bean);
            if (constructorArgs.length >= 1 && !label) {
                label = constructorArgs[0] || '';
            }
            if (constructorArgs.length >= 2 && !url) {
                url = constructorArgs[1] || '';
            }
        }

        const beanId = bean.getAttribute('id') || '';

        // Skip separators for main processing but track them
        const isSeparator = label === '---' || label === '-' || label.toLowerCase() === 'separator';

        // Extract roles
        const requiredRoles = this.extractRoles(bean);

        // Parse URL to extract flowId and viewStateId
        const { flowId, viewStateId } = this.parseMenuUrl(url);

        // Create menu item node
        if (label && !isSeparator) {
            const menuItem: MenuItemNode = {
                id: generateInstanceId(counter, 'menuitem', label),
                entityId: generateEntityId('menuitem', `${filePath}:${label}`, this.repositoryId),
                kind: 'MenuItem',
                name: label,
                filePath,
                startLine: this.getLineNumber(bean),
                endLine: this.getLineNumber(bean),
                startColumn: 0,
                endColumn: 0,
                language: 'XML',
                createdAt: now,
                properties: {
                    label,
                    url,
                    flowId,
                    viewStateId,
                    requiredRoles,
                    parentMenu,
                    menuLevel: level,
                    isSeparator: false,
                    beanId,
                },
            };
            menuItems.push(menuItem);

            // Process nested menu items
            const nestedItems = this.getNestedMenuItems(bean);
            for (const nested of nestedItems) {
                const childItems = this.extractMenuItems(nested, filePath, counter, now, label, level + 1);
                menuItems.push(...childItems);
            }
        }

        return menuItems;
    }

    /**
     * Get constructor argument values from a bean element.
     * Used for Spring beans that use constructor injection.
     * Example: <constructor-arg value="Label" />
     */
    private getConstructorArgs(bean: Element): string[] {
        const args: string[] = [];
        const constructorArgs = bean.getElementsByTagName('constructor-arg');

        for (let i = 0; i < constructorArgs.length; i++) {
            const arg = constructorArgs[i];
            // Only process direct children (not nested constructor-args)
            if (arg.parentNode !== bean) continue;

            // Check for value attribute
            const value = arg.getAttribute('value');
            if (value) {
                args.push(value);
            } else {
                // Check for nested value element
                const valueElements = arg.getElementsByTagName('value');
                if (valueElements.length > 0) {
                    args.push(valueElements[0].textContent || '');
                } else {
                    // This might be a list (for nested menus), push empty string as placeholder
                    args.push('');
                }
            }
        }

        return args;
    }

    /**
     * Get a property value from a bean element.
     */
    private getPropertyValue(bean: Element, propertyName: string): string | null {
        const properties = bean.getElementsByTagName('property');
        for (let i = 0; i < properties.length; i++) {
            const prop = properties[i];
            if (prop.getAttribute('name') === propertyName) {
                // Check for value attribute
                const value = prop.getAttribute('value');
                if (value) return value;

                // Check for nested value element
                const valueElements = prop.getElementsByTagName('value');
                if (valueElements.length > 0) {
                    return valueElements[0].textContent || null;
                }
            }
        }
        return null;
    }

    /**
     * Extract required roles from a bean.
     */
    private extractRoles(bean: Element): string[] {
        const roles: string[] = [];
        const properties = bean.getElementsByTagName('property');

        for (let i = 0; i < properties.length; i++) {
            const prop = properties[i];
            const name = prop.getAttribute('name');
            if (name === 'requiredRoles' || name === 'roles' || name === 'authorities') {
                // Check for list of values
                const list = prop.getElementsByTagName('list');
                if (list.length > 0) {
                    const values = list[0].getElementsByTagName('value');
                    for (let j = 0; j < values.length; j++) {
                        const role = values[j].textContent;
                        if (role) roles.push(role.trim());
                    }
                }
                // Check for single value
                const value = prop.getAttribute('value');
                if (value) {
                    roles.push(value.trim());
                }
            }
        }

        return roles;
    }

    /**
     * Get nested menu items from a bean.
     * Supports both property-based and constructor-arg based definitions.
     */
    private getNestedMenuItems(bean: Element): Element[] {
        const nested: Element[] = [];

        // Check property elements first
        const properties = bean.getElementsByTagName('property');
        for (let i = 0; i < properties.length; i++) {
            const prop = properties[i];
            if (prop.getAttribute('name') === 'menuItems' || prop.getAttribute('name') === 'subMenus' || prop.getAttribute('name') === 'children') {
                const list = prop.getElementsByTagName('list');
                if (list.length > 0) {
                    const beans = list[0].getElementsByTagName('bean');
                    for (let j = 0; j < beans.length; j++) {
                        // Only get direct children, not nested
                        if (beans[j].parentNode === list[0]) {
                            nested.push(beans[j]);
                        }
                    }
                }
            }
        }

        // Also check constructor-arg elements (Spring constructor injection)
        // Nested menus are typically in the second constructor-arg as a list
        const constructorArgs = bean.getElementsByTagName('constructor-arg');
        for (let i = 0; i < constructorArgs.length; i++) {
            const arg = constructorArgs[i];
            // Only process direct children
            if (arg.parentNode !== bean) continue;

            // Look for list containing beans
            const lists = arg.getElementsByTagName('list');
            for (let j = 0; j < lists.length; j++) {
                const list = lists[j];
                // Only process direct child lists
                if (list.parentNode !== arg) continue;

                const beans = list.getElementsByTagName('bean');
                for (let k = 0; k < beans.length; k++) {
                    const nestedBean = beans[k];
                    // Only get direct children of the list
                    if (nestedBean.parentNode === list) {
                        // Check if it's a MenuItem bean
                        const classAttr = nestedBean.getAttribute('class');
                        if (classAttr && classAttr.toLowerCase().includes('menuitem')) {
                            nested.push(nestedBean);
                        }
                    }
                }
            }
        }

        return nested;
    }

    /**
     * Parse a menu URL to extract flow ID and view state ID.
     */
    private parseMenuUrl(url: string): { flowId: string; viewStateId?: string } {
        if (!url) return { flowId: '' };

        // Pattern: "pointWizard.html?pageSelect=pointInfoMaintenance"
        const match = url.match(/^(\w+)\.html(?:\?pageSelect=(\w+))?/);
        if (match) {
            return {
                flowId: match[1],
                viewStateId: match[2],
            };
        }

        // Pattern: "flowName.html" or "flowName"
        const simpleMatch = url.match(/^(\w+)(?:\.html)?$/);
        if (simpleMatch) {
            return { flowId: simpleMatch[1] };
        }

        // Pattern with mode: "pointWizard.html?mode=maintenance"
        const modeMatch = url.match(/^(\w+)\.html\?mode=/);
        if (modeMatch) {
            return { flowId: modeMatch[1] };
        }

        return { flowId: '' };
    }

    /**
     * Get approximate line number for an element.
     */
    private getLineNumber(element: Element): number {
        // XMLDom doesn't provide line numbers, so we estimate
        // In a production scenario, you might use a different parser
        return 1;
    }
}

export default MenuParser;
