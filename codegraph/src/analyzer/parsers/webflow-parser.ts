import { DOMParser } from '@xmldom/xmldom';
import xpath from 'xpath';
import path from 'path';
import fs from 'fs/promises';
import { createContextLogger } from '../../utils/logger.js';
import { ParserError } from '../../utils/errors.js';
import { FileInfo } from '../../scanner/file-scanner.js';
import {
    AstNode,
    RelationshipInfo,
    SingleFileParseResult,
    InstanceCounter,
    WebFlowDefinitionNode,
    FlowStateNode,
    FlowTransitionNode,
    FlowActionNode,
    FlowVariable,
    ActionReference,
    ScreenNode,
    TransitionConditionMetadata
} from '../types.js';
import { ensureTempDir, getTempFilePath, generateInstanceId, generateEntityId } from '../parser-utils.js';
import { BusinessRuleDetector } from './BusinessRuleDetector.js';

const logger = createContextLogger('WebFlowParser');

/**
 * Parse a WebFlow condition expression into structured metadata.
 * Extracts operators, variables, method calls, and generates human-readable descriptions.
 */
function parseConditionExpression(condition: string): TransitionConditionMetadata {
    const metadata: TransitionConditionMetadata = {
        expression: condition,
        variables: [],
        methodCalls: [],
        isSpEL: condition.includes('#') || condition.includes('T('),
    };

    // Extract scope variables (flowScope.variable, viewScope.variable, etc.)
    const scopeVariablePattern = /(?:flowScope|viewScope|requestScope|conversationScope|flashScope)\.(\w+)/g;
    let varMatch;
    while ((varMatch = scopeVariablePattern.exec(condition)) !== null) {
        if (varMatch[1] && !metadata.variables.includes(varMatch[1])) {
            metadata.variables.push(varMatch[1]);
        }
    }

    // Also extract simple variable references before operators
    const simpleVarPattern = /\b([a-z]\w*)\b(?=\s*[!=<>]|\s*\.(?!class))/g;
    while ((varMatch = simpleVarPattern.exec(condition)) !== null) {
        if (varMatch[1] && !metadata.variables.includes(varMatch[1]) && !['null', 'true', 'false'].includes(varMatch[1])) {
            metadata.variables.push(varMatch[1]);
        }
    }

    // Extract method calls (pattern: identifier.methodName())
    const methodPattern = /(\w+)\.(\w+)\s*\(/g;
    let methodMatch;
    while ((methodMatch = methodPattern.exec(condition)) !== null) {
        if (methodMatch[2]) {
            const fullMethod = `${methodMatch[1]}.${methodMatch[2]}`;
            if (!metadata.methodCalls.includes(fullMethod)) {
                metadata.methodCalls.push(fullMethod);
            }
        }
    }

    // Determine operator
    if (condition.includes('==')) {
        metadata.operator = 'equals';
        const parts = condition.split('==').map(p => p.trim());
        metadata.leftOperand = parts[0];
        metadata.rightOperand = parts[1];
    } else if (condition.includes('!=')) {
        metadata.operator = 'notEquals';
        const parts = condition.split('!=').map(p => p.trim());
        metadata.leftOperand = parts[0];
        metadata.rightOperand = parts[1];
    } else if (condition.includes('>=')) {
        metadata.operator = 'greaterThanOrEquals';
        const parts = condition.split('>=').map(p => p.trim());
        metadata.leftOperand = parts[0];
        metadata.rightOperand = parts[1];
    } else if (condition.includes('<=')) {
        metadata.operator = 'lessThanOrEquals';
        const parts = condition.split('<=').map(p => p.trim());
        metadata.leftOperand = parts[0];
        metadata.rightOperand = parts[1];
    } else if (condition.includes('>')) {
        metadata.operator = 'greaterThan';
        const parts = condition.split('>').map(p => p.trim());
        metadata.leftOperand = parts[0];
        metadata.rightOperand = parts[1];
    } else if (condition.includes('<')) {
        metadata.operator = 'lessThan';
        const parts = condition.split('<').map(p => p.trim());
        metadata.leftOperand = parts[0];
        metadata.rightOperand = parts[1];
    } else if (condition.includes(' and ') || condition.includes('&&')) {
        metadata.operator = 'and';
    } else if (condition.includes(' or ') || condition.includes('||')) {
        metadata.operator = 'or';
    } else if (condition.startsWith('!') || condition.includes(' not ')) {
        metadata.operator = 'not';
    } else if (condition.includes('.contains(')) {
        metadata.operator = 'contains';
    } else if (condition.includes('.matches(')) {
        metadata.operator = 'matches';
    } else {
        metadata.operator = 'custom';
    }

    // Generate human-readable description
    metadata.description = generateConditionDescription(metadata);

    return metadata;
}

/**
 * Generate a human-readable description from condition metadata.
 */
function generateConditionDescription(meta: TransitionConditionMetadata): string {
    if (meta.operator === 'equals' && meta.leftOperand && meta.rightOperand) {
        return `When ${meta.leftOperand} equals ${meta.rightOperand}`;
    } else if (meta.operator === 'notEquals' && meta.leftOperand && meta.rightOperand) {
        return `When ${meta.leftOperand} is not equal to ${meta.rightOperand}`;
    } else if (meta.operator === 'greaterThan' && meta.leftOperand && meta.rightOperand) {
        return `When ${meta.leftOperand} is greater than ${meta.rightOperand}`;
    } else if (meta.operator === 'lessThan' && meta.leftOperand && meta.rightOperand) {
        return `When ${meta.leftOperand} is less than ${meta.rightOperand}`;
    } else if (meta.operator === 'not') {
        return `When condition is false: ${meta.expression.substring(0, 50)}`;
    } else if (meta.methodCalls.length > 0) {
        return `When ${meta.methodCalls.join(' and ')} returns true`;
    } else if (meta.variables.length > 0) {
        return `Condition based on: ${meta.variables.join(', ')}`;
    }
    return `Custom condition: ${meta.expression.substring(0, 50)}${meta.expression.length > 50 ? '...' : ''}`;
}

export class WebFlowParser {
    private instanceCounter: InstanceCounter = { count: 0 };
    private now: string = new Date().toISOString();

    constructor() {
        logger.debug('Spring Web Flow Parser initialized');
    }

    /**
     * Parses a single Spring Web Flow XML file.
     */
    async parseFile(file: FileInfo): Promise<string> {
        logger.debug(`Parsing Web Flow file: ${file.path}`);

        await ensureTempDir();
        const tempFilePath = getTempFilePath(file.path);

        try {
            const content = await fs.readFile(file.path, 'utf-8');
            const result = await this.parseWebFlowContent(content, file.path);

            await fs.writeFile(tempFilePath, JSON.stringify(result, null, 2));
            logger.debug(`Web Flow parsing completed for ${file.path}`);

            return tempFilePath;
        } catch (error: any) {
            logger.error(`Error parsing Web Flow file ${file.path}:`, { message: error.message });
            throw new ParserError(`Failed to parse Web Flow file: ${file.path}`, { originalError: error });
        }
    }

    /**
     * Parses Spring Web Flow XML content.
     */
    private async parseWebFlowContent(content: string, filePath: string): Promise<SingleFileParseResult> {
        const normalizedPath = path.resolve(filePath).replace(/\\/g, '/');
        const fileName = path.basename(filePath, '.xml');

        const nodes: AstNode[] = [];
        const relationships: RelationshipInfo[] = [];

        try {
            const doc = new DOMParser().parseFromString(content, 'text/xml');

            // Check for parsing errors
            const parseError = doc.getElementsByTagName('parsererror')[0];
            if (parseError) {
                throw new Error(`XML parsing error: ${parseError.textContent}`);
            }

            const flowElement = doc.getElementsByTagName('flow')[0];
            if (!flowElement) {
                throw new Error('No flow element found in XML');
            }

            // Create flow definition node
            const flowNode = this.createFlowDefinitionNode(flowElement, normalizedPath, fileName);
            nodes.push(flowNode);

            // Parse states
            const states = this.parseStates(flowElement, flowNode.entityId);
            nodes.push(...states);

            // Create state relationships
            states.forEach(state => {
                relationships.push(this.createRelationship(
                    'FLOW_DEFINES_STATE',
                    flowNode.entityId,
                    state.entityId
                ));
            });

            // Parse transitions
            const transitions = this.parseTransitions(flowElement, states);
            nodes.push(...transitions);

            // Create transition relationships
            transitions.forEach(transition => {
                // Find source state
                const sourceState = states.find(s =>
                    s.properties.stateId === transition.properties.fromStateId
                );
                if (sourceState) {
                    relationships.push(this.createRelationship(
                        'STATE_HAS_TRANSITION',
                        sourceState.entityId,
                        transition.entityId
                    ));
                }

                // Create transition-to-state relationship
                const targetState = states.find(s =>
                    s.properties.stateId === transition.properties.toStateId
                );
                if (targetState) {
                    relationships.push(this.createRelationship(
                        'FLOW_TRANSITIONS_TO',
                        transition.entityId,
                        targetState.entityId
                    ));
                }
            });

            // Parse actions
            const actions = this.parseActions(flowElement, flowNode.entityId, states);
            nodes.push(...actions);

            // Create action relationships
            actions.forEach(action => {
                if (action.parentId === flowNode.entityId) {
                    relationships.push(this.createRelationship(
                        'FLOW_EXECUTES_ACTION',
                       flowNode.entityId,
                       action.entityId
                   ));
               } else {
                   // Action belongs to a state
                   relationships.push(this.createRelationship(
                       'FLOW_EXECUTES_ACTION',
                       action.parentId,
                       action.entityId
                   ));
               }
           });

           // Business Rule Detection (Phase 3)
           // Extract decision states, transition guards, validators from WebFlow
           const businessRuleDetector = new BusinessRuleDetector(normalizedPath, 'SpringWebFlow');
           const businessRuleResult = businessRuleDetector.detectWebFlowRules(
               content,
               flowNode.properties.flowId
           );

           // Merge business rule nodes
           const businessRuleNodes = businessRuleDetector.getAllNodes();
           const businessRuleRelationships = businessRuleDetector.getRelationships();

           logger.debug(
               `[WebFlowParser] Business rules detected for ${fileName}: ` +
               `${businessRuleResult.totalRulesDetected} rules`
           );

           // Extract Screen nodes from view-states (Phase 1: Menu & Screen Indexing)
           const screens = this.extractScreens(flowElement, flowNode, states, transitions);
           nodes.push(...screens);

           // Create screen relationships
           screens.forEach(screen => {
               // Screen uses flow
               relationships.push(this.createRelationship(
                   'SCREEN_USES_FLOW',
                   screen.entityId,
                   flowNode.entityId
               ));

               // Screen navigates to other screens
               screen.properties.transitionsTo.forEach(targetScreenId => {
                   const targetScreen = screens.find(s => s.properties.screenId === targetScreenId);
                   if (targetScreen) {
                       relationships.push(this.createRelationship(
                           'SCREEN_NAVIGATES_TO',
                           screen.entityId,
                           targetScreen.entityId
                       ));
                   }
               });

               // Screen inherits from parent
               if (screen.properties.parentScreenId) {
                   const parentScreen = screens.find(s => s.properties.screenId === screen.properties.parentScreenId);
                   if (parentScreen) {
                       relationships.push(this.createRelationship(
                           'SCREEN_INHERITS',
                           screen.entityId,
                           parentScreen.entityId
                       ));
                   }
               }
           });

           logger.debug(
               `[WebFlowParser] Extracted ${screens.length} screens from ${fileName}`
           );

           return {
               filePath: normalizedPath,
               nodes: [...nodes, ...businessRuleNodes, ...screens],
               relationships: [...relationships, ...businessRuleRelationships]
           };

       } catch (error: any) {
           logger.error(`Error parsing Web Flow XML: ${error.message}`);
           throw error;
       }
   }

   /**
    * Creates the main Web Flow definition node.
    */
   private createFlowDefinitionNode(flowElement: Element, filePath: string, fileName: string): WebFlowDefinitionNode {
       const flowId = fileName; // Use filename as flow ID
       const startStateAttr = flowElement.getAttribute('start-state');

       // Find start state
       let startState = startStateAttr;
       if (!startState) {
           // Find first view-state or action-state
           const viewStates = flowElement.getElementsByTagName('view-state');
           const actionStates = flowElement.getElementsByTagName('action-state');
           const firstState = (viewStates.length > 0 ? viewStates[0] : 
                              actionStates.length > 0 ? actionStates[0] : null);
           startState = firstState?.getAttribute('id') || 'unknown';
       }

       // Find end states
       const endStateElements = flowElement.getElementsByTagName('end-state');
       const endStates: string[] = [];
       for (let i = 0; i < endStateElements.length; i++) {
           const endStateElement = endStateElements[i];
           if (endStateElement) {
               const endStateId = endStateElement.getAttribute('id');
               if (endStateId) endStates.push(endStateId);
           }
       }

       // Parse flow variables
       const flowVariables = this.parseFlowVariables(flowElement);

       // Parse security attributes
       const securityElements = flowElement.getElementsByTagName('secured');
       const securityAttributes: string[] = [];
       for (let i = 0; i < securityElements.length; i++) {
           const securityElement = securityElements[i];
           if (securityElement) {
               const attributes = securityElement.getAttribute('attributes');
               if (attributes) securityAttributes.push(attributes);
           }
       }

       const entityId = generateEntityId('webflowdefinition', flowId);

       return {
           id: generateInstanceId(this.instanceCounter, 'webflowdefinition', flowId),
           entityId,
           kind: 'WebFlowDefinition',
           name: flowId,
           filePath,
           language: 'SpringWebFlow',
           startLine: 1,
           endLine: 1,
           startColumn: 0,
           endColumn: 0,
           createdAt: this.now,
           properties: {
               flowId,
               startState,
               endStates,
               flowVariables,
               securityAttributes: securityAttributes.length > 0 ? securityAttributes : undefined
           }
       };
   }

   /**
    * Parses all states in the flow.
    */
   private parseStates(flowElement: Element, flowEntityId: string): FlowStateNode[] {
       const states: FlowStateNode[] = [];

       // Parse view states
       const viewStates = flowElement.getElementsByTagName('view-state');
       for (let i = 0; i < viewStates.length; i++) {
           const viewState = viewStates[i];
           if (viewState) {
               states.push(this.parseViewState(viewState, flowEntityId));
           }
       }

       // Parse action states
       const actionStates = flowElement.getElementsByTagName('action-state');
       for (let i = 0; i < actionStates.length; i++) {
           const actionState = actionStates[i];
           if (actionState) {
               states.push(this.parseActionState(actionState, flowEntityId));
           }
       }

       // Parse decision states
       const decisionStates = flowElement.getElementsByTagName('decision-state');
       for (let i = 0; i < decisionStates.length; i++) {
           const decisionState = decisionStates[i];
           if (decisionState) {
               states.push(this.parseDecisionState(decisionState, flowEntityId));
           }
       }

       // Parse end states
       const endStates = flowElement.getElementsByTagName('end-state');
       for (let i = 0; i < endStates.length; i++) {
           const endState = endStates[i];
           if (endState) {
               states.push(this.parseEndState(endState, flowEntityId));
           }
       }

       // Parse subflow states
       const subflowStates = flowElement.getElementsByTagName('subflow-state');
       for (let i = 0; i < subflowStates.length; i++) {
           const subflowState = subflowStates[i];
           if (subflowState) {
               states.push(this.parseSubflowState(subflowState, flowEntityId));
           }
       }

       return states;
   }

   private parseViewState(stateElement: Element, flowEntityId: string): FlowStateNode {
       const stateId = stateElement.getAttribute('id') || 'unknown';
       const view = stateElement.getAttribute('view') || stateId;

       const viewScope = this.parseStateVariables(stateElement, 'view');
       const onEntry = this.parseStateActions(stateElement, 'on-entry');
       const onExit = this.parseStateActions(stateElement, 'on-exit');
       const secured = stateElement.getElementsByTagName('secured').length > 0;

       const entityId = generateEntityId('flowstate', `${flowEntityId}:${stateId}`);

       return {
           id: generateInstanceId(this.instanceCounter, 'flowstate', stateId),
           entityId,
           kind: 'FlowState',
           name: stateId,
           filePath: flowEntityId.split(':')[1] || '', // Extract from flow entity ID
           language: 'SpringWebFlow',
           startLine: 1,
           endLine: 1,
           startColumn: 0,
           endColumn: 0,
           parentId: flowEntityId,
           createdAt: this.now,
           properties: {
               stateId,
               stateType: 'view-state',
               view,
               viewScope: viewScope.length > 0 ? viewScope : undefined,
               onEntry: onEntry.length > 0 ? onEntry : undefined,
               onExit: onExit.length > 0 ? onExit : undefined,
               secured
           }
       };
   }

   private parseActionState(stateElement: Element, flowEntityId: string): FlowStateNode {
       const stateId = stateElement.getAttribute('id') || 'unknown';

       const onEntry = this.parseStateActions(stateElement, 'on-entry');
       const onExit = this.parseStateActions(stateElement, 'on-exit');
       const secured = stateElement.getElementsByTagName('secured').length > 0;

       const entityId = generateEntityId('flowstate', `${flowEntityId}:${stateId}`);

       return {
           id: generateInstanceId(this.instanceCounter, 'flowstate', stateId),
           entityId,
           kind: 'FlowState',
           name: stateId,
           filePath: flowEntityId.split(':')[1] || '',
           language: 'SpringWebFlow',
           startLine: 1,
           endLine: 1,
           startColumn: 0,
           endColumn: 0,
           parentId: flowEntityId,
           createdAt: this.now,
           properties: {
               stateId,
               stateType: 'action-state',
               onEntry: onEntry.length > 0 ? onEntry : undefined,
               onExit: onExit.length > 0 ? onExit : undefined,
               secured
           }
       };
   }

   private parseDecisionState(stateElement: Element, flowEntityId: string): FlowStateNode {
       const stateId = stateElement.getAttribute('id') || 'unknown';

       const onEntry = this.parseStateActions(stateElement, 'on-entry');
       const onExit = this.parseStateActions(stateElement, 'on-exit');

       const entityId = generateEntityId('flowstate', `${flowEntityId}:${stateId}`);

       return {
           id: generateInstanceId(this.instanceCounter, 'flowstate', stateId),
           entityId,
           kind: 'FlowState',
           name: stateId,
           filePath: flowEntityId.split(':')[1] || '',
           language: 'SpringWebFlow',
           startLine: 1,
           endLine: 1,
           startColumn: 0,
           endColumn: 0,
           parentId: flowEntityId,
           createdAt: this.now,
           properties: {
               stateId,
               stateType: 'decision-state',
               onEntry: onEntry.length > 0 ? onEntry : undefined,
               onExit: onExit.length > 0 ? onExit : undefined
           }
       };
   }

   private parseEndState(stateElement: Element, flowEntityId: string): FlowStateNode {
       const stateId = stateElement.getAttribute('id') || 'unknown';
       const view = stateElement.getAttribute('view') || undefined;

       const onEntry = this.parseStateActions(stateElement, 'on-entry');

       const entityId = generateEntityId('flowstate', `${flowEntityId}:${stateId}`);

       return {
           id: generateInstanceId(this.instanceCounter, 'flowstate', stateId),
           entityId,
           kind: 'FlowState',
           name: stateId,
           filePath: flowEntityId.split(':')[1] || '',
           language: 'SpringWebFlow',
           startLine: 1,
           endLine: 1,
           startColumn: 0,
           endColumn: 0,
           parentId: flowEntityId,
           createdAt: this.now,
           properties: {
               stateId,
               stateType: 'end-state',
               view,
               onEntry: onEntry.length > 0 ? onEntry : undefined
           }
       };
   }

   private parseSubflowState(stateElement: Element, flowEntityId: string): FlowStateNode {
       const stateId = stateElement.getAttribute('id') || 'unknown';
       const subflow = stateElement.getAttribute('subflow') || undefined;

       const onEntry = this.parseStateActions(stateElement, 'on-entry');
       const onExit = this.parseStateActions(stateElement, 'on-exit');

       const entityId = generateEntityId('flowstate', `${flowEntityId}:${stateId}`);

       return {
           id: generateInstanceId(this.instanceCounter, 'flowstate', stateId),
           entityId,
           kind: 'FlowState',
           name: stateId,
           filePath: flowEntityId.split(':')[1] || '',
           language: 'SpringWebFlow',
           startLine: 1,
           endLine: 1,
           startColumn: 0,
           endColumn: 0,
           parentId: flowEntityId,
           createdAt: this.now,
           properties: {
               stateId,
               stateType: 'subflow-state',
               view: subflow,
               onEntry: onEntry.length > 0 ? onEntry : undefined,
               onExit: onExit.length > 0 ? onExit : undefined
           }
       };
   }

   /**
    * Parses transitions between states.
    */
   private parseTransitions(flowElement: Element, states: FlowStateNode[]): FlowTransitionNode[] {
       const transitions: FlowTransitionNode[] = [];

       states.forEach(state => {
           const stateElement = this.findStateElement(flowElement, state.properties.stateId);
           if (!stateElement) return;

           const transitionElements = stateElement.getElementsByTagName('transition');
           for (let i = 0; i < transitionElements.length; i++) {
               const transitionElement = transitionElements[i];
               if (!transitionElement) continue;
               
               const transition = this.parseTransition(transitionElement, state);
               if (transition) {
                   transitions.push(transition);
               }
           }
       });

       // Parse global transitions - get direct transition children of flow
       const allTransitions = flowElement.getElementsByTagName('transition');
       const globalTransitions: Element[] = [];
       for (let i = 0; i < allTransitions.length; i++) {
           const transition = allTransitions[i];
           if (transition && transition.parentNode === flowElement) {
               globalTransitions.push(transition);
           }
       }
       for (let i = 0; i < globalTransitions.length; i++) {
           const transitionElement = globalTransitions[i];
           if (!transitionElement) continue;
           
           const transition = this.parseGlobalTransition(transitionElement, flowElement);
           if (transition) {
               transitions.push(transition);
           }
       }

       return transitions;
   }

   private parseTransition(transitionElement: Element, sourceState: FlowStateNode): FlowTransitionNode | null {
       const event = transitionElement.getAttribute('on') || 'default';
       const to = transitionElement.getAttribute('to');

       if (!to) return null;

       const condition = transitionElement.getAttribute('condition') || undefined;
       // BRD Enhancement: Parse condition into structured metadata
       const conditionMetadata = condition ? parseConditionExpression(condition) : undefined;

       const executeBefore = this.parseTransitionActions(transitionElement, 'execute');
       const executeAfter = this.parseTransitionActions(transitionElement, 'execute');

       const entityId = generateEntityId('flowtransition', `${sourceState.entityId}:${event}:${to}`);

       return {
           id: generateInstanceId(this.instanceCounter, 'flowtransition', `${event}:${to}`),
           entityId,
           kind: 'FlowTransition',
           name: `${event}->${to}`,
           filePath: sourceState.filePath,
           language: 'SpringWebFlow',
           startLine: 1,
           endLine: 1,
           startColumn: 0,
           endColumn: 0,
           parentId: sourceState.entityId,
           createdAt: this.now,
           properties: {
               event,
               fromStateId: sourceState.properties.stateId,
               toStateId: to,
               condition,
               conditionMetadata,
               executeBefore: executeBefore.length > 0 ? executeBefore : undefined,
               executeAfter: executeAfter.length > 0 ? executeAfter : undefined
           }
       };
   }

   private parseGlobalTransition(transitionElement: Element, flowElement: Element): FlowTransitionNode | null {
       const event = transitionElement.getAttribute('on') || 'default';
       const to = transitionElement.getAttribute('to');

       if (!to) return null;

       const condition = transitionElement.getAttribute('condition') || undefined;
       // BRD Enhancement: Parse condition into structured metadata
       const conditionMetadata = condition ? parseConditionExpression(condition) : undefined;

       const flowId = flowElement.getAttribute('id') || 'unknown';

       const entityId = generateEntityId('flowtransition', `global:${flowId}:${event}:${to}`);

       return {
           id: generateInstanceId(this.instanceCounter, 'flowtransition', `global:${event}:${to}`),
           entityId,
           kind: 'FlowTransition',
           name: `global:${event}->${to}`,
           filePath: '', // Will be set by caller
           language: 'SpringWebFlow',
           startLine: 1,
           endLine: 1,
           startColumn: 0,
           endColumn: 0,
           parentId: generateEntityId('webflowdefinition', flowId),
           createdAt: this.now,
           properties: {
               event,
               fromStateId: 'global',
               toStateId: to,
               condition,
               conditionMetadata
           }
       };
   }

   /**
    * Parses flow actions.
    */
   private parseActions(flowElement: Element, flowEntityId: string, states: FlowStateNode[]): FlowActionNode[] {
       const actions: FlowActionNode[] = [];

       // Parse flow-level actions
       const flowActions = this.parseFlowLevelActions(flowElement, flowEntityId);
       actions.push(...flowActions);

       // Parse state-level actions
       states.forEach(state => {
           const stateActions = this.parseStateLevelActions(flowElement, state);
           actions.push(...stateActions);
       });

       return actions;
   }

   private parseFlowLevelActions(flowElement: Element, flowEntityId: string): FlowActionNode[] {
       const actions: FlowActionNode[] = [];

       // Parse on-start actions
       const onStartElements = flowElement.getElementsByTagName('on-start');
       for (let i = 0; i < onStartElements.length; i++) {
           const onStartElement = onStartElements[i];
           if (!onStartElement) continue;
           
           const evaluateElements = onStartElement.getElementsByTagName('evaluate');
           const setElements = onStartElement.getElementsByTagName('set');
           const actionElements = [...Array.from(evaluateElements), ...Array.from(setElements)];
           for (let j = 0; j < actionElements.length; j++) {
               const actionElement = actionElements[j];
               if (!actionElement) continue;
               
               const action = this.parseActionElement(actionElement, flowEntityId, 'flow-start');
               if (action) actions.push(action);
           }
       }

       // Parse on-end actions
       const onEndElements = flowElement.getElementsByTagName('on-end');
       for (let i = 0; i < onEndElements.length; i++) {
           const onEndElement = onEndElements[i];
           if (!onEndElement) continue;
           
           const evaluateElements = onEndElement.getElementsByTagName('evaluate');
           const setElements = onEndElement.getElementsByTagName('set');
           const actionElements = [...Array.from(evaluateElements), ...Array.from(setElements)];
           for (let j = 0; j < actionElements.length; j++) {
               const actionElement = actionElements[j];
               if (!actionElement) continue;
               
               const action = this.parseActionElement(actionElement, flowEntityId, 'flow-end');
               if (action) actions.push(action);
           }
       }

       return actions;
   }

   private parseStateLevelActions(flowElement: Element, state: FlowStateNode): FlowActionNode[] {
       const actions: FlowActionNode[] = [];

       const stateElement = this.findStateElement(flowElement, state.properties.stateId);
       if (!stateElement) return actions;

       // Parse on-entry actions
       const onEntryElements = stateElement.getElementsByTagName('on-entry');
       for (let i = 0; i < onEntryElements.length; i++) {
           const onEntryElement = onEntryElements[i];
           if (!onEntryElement) continue;
           
           const evaluateElements = onEntryElement.getElementsByTagName('evaluate');
           const setElements = onEntryElement.getElementsByTagName('set');
           const actionElements = [...Array.from(evaluateElements), ...Array.from(setElements)];
           for (let j = 0; j < actionElements.length; j++) {
               const actionElement = actionElements[j];
               if (!actionElement) continue;
               
               const action = this.parseActionElement(actionElement, state.entityId, 'state-entry');
               if (action) actions.push(action);
           }
       }

       // Parse on-exit actions
       const onExitElements = stateElement.getElementsByTagName('on-exit');
       for (let i = 0; i < onExitElements.length; i++) {
           const onExitElement = onExitElements[i];
           if (!onExitElement) continue;
           
           const evaluateElements = onExitElement.getElementsByTagName('evaluate');
           const setElements = onExitElement.getElementsByTagName('set');
           const actionElements = [...Array.from(evaluateElements), ...Array.from(setElements)];
           for (let j = 0; j < actionElements.length; j++) {
               const actionElement = actionElements[j];
               if (!actionElement) continue;
               
               const action = this.parseActionElement(actionElement, state.entityId, 'state-exit');
               if (action) actions.push(action);
           }
       }

       return actions;
   }

   private parseActionElement(actionElement: Element, parentId: string, context: string): FlowActionNode | null {
       const tagName = actionElement.tagName;
       let actionName = '';
       let actionType: 'evaluate' | 'set' | 'bean-method' = 'evaluate';
       let beanMethod: string | undefined;
       let expression: string | undefined;
       let resultScope: string | undefined;

       if (tagName === 'evaluate') {
           actionType = 'evaluate';
           expression = actionElement.getAttribute('expression') || undefined;
           resultScope = actionElement.getAttribute('result') || actionElement.getAttribute('result-type') || undefined;
           actionName = expression || 'evaluate';
       } else if (tagName === 'set') {
           actionType = 'set';
           const name = actionElement.getAttribute('name');
           const value = actionElement.getAttribute('value');
           actionName = name || 'set';
           expression = `${name} = ${value}`;
           resultScope = actionElement.getAttribute('scope') || undefined;
       } else {
           // Bean method call
           actionType = 'bean-method';
           beanMethod = actionElement.getAttribute('bean') + '.' + actionElement.getAttribute('method');
           actionName = beanMethod;
       }

       if (!actionName) return null;

       const entityId = generateEntityId('flowaction', `${parentId}:${context}:${actionName}`);

       return {
           id: generateInstanceId(this.instanceCounter, 'flowaction', actionName),
           entityId,
           kind: 'FlowAction',
           name: actionName,
           filePath: parentId.split(':')[1] || '',
           language: 'SpringWebFlow',
           startLine: 1,
           endLine: 1,
           startColumn: 0,
           endColumn: 0,
           parentId,
           createdAt: this.now,
           properties: {
               actionName,
               actionType,
               beanMethod,
               expression,
               resultScope: resultScope as any
           }
       };
   }

   // Helper methods
   private parseFlowVariables(flowElement: Element): FlowVariable[] {
       const variables: FlowVariable[] = [];

       const varElements = flowElement.getElementsByTagName('var');
       for (let i = 0; i < varElements.length; i++) {
           const varElement = varElements[i];
           if (!varElement) continue;
           
           const name = varElement.getAttribute('name');
           const type = varElement.getAttribute('class') || undefined;
           const scope = varElement.getAttribute('scope') || 'flow';

           if (name) {
               variables.push({
                   name,
                   type,
                   scope: scope as any
               });
           }
       }

       return variables;
   }

   private parseStateVariables(stateElement: Element, defaultScope: string): FlowVariable[] {
       const variables: FlowVariable[] = [];

       const varElements = stateElement.getElementsByTagName('var');
       for (let i = 0; i < varElements.length; i++) {
           const varElement = varElements[i];
           if (!varElement) continue;
           
           const name = varElement.getAttribute('name');
           const type = varElement.getAttribute('class') || undefined;
           const scope = varElement.getAttribute('scope') || defaultScope;

           if (name) {
               variables.push({
                   name,
                   type,
                   scope: scope as any
               });
           }
       }

       return variables;
   }

   private parseStateActions(stateElement: Element, actionType: string): ActionReference[] {
       const actions: ActionReference[] = [];

       const actionContainers = stateElement.getElementsByTagName(actionType);
       for (let i = 0; i < actionContainers.length; i++) {
           const container = actionContainers[i];
           if (!container) continue;

           const evaluateElements = container.getElementsByTagName('evaluate');
           for (let j = 0; j < evaluateElements.length; j++) {
               const evaluate = evaluateElements[j];
               if (!evaluate) continue;
               
               actions.push({
                   expression: evaluate.getAttribute('expression') || undefined
               });
           }

           const setElements = container.getElementsByTagName('set');
           for (let j = 0; j < setElements.length; j++) {
               const set = setElements[j];
               if (!set) continue;
               
               const name = set.getAttribute('name');
               const value = set.getAttribute('value');
               actions.push({
                   expression: `${name} = ${value}`
               });
           }
       }

       return actions;
   }

   private parseTransitionActions(transitionElement: Element, actionType: string): ActionReference[] {
       // Similar to parseStateActions but for transitions
       return this.parseStateActions(transitionElement, actionType);
   }

   private findStateElement(flowElement: Element, stateId: string): Element | null {
       const stateTypes = [
           'view-state',
           'action-state',
           'decision-state',
           'end-state',
           'subflow-state'
       ];

       for (const stateType of stateTypes) {
           const elements = flowElement.getElementsByTagName(stateType);
           for (let i = 0; i < elements.length; i++) {
               const element = elements[i];
               if (element && element.getAttribute('id') === stateId) {
                   return element;
               }
           }
       }

       return null;
   }

   private createRelationship(type: string, sourceId: string, targetId: string): RelationshipInfo {
       return {
           id: generateInstanceId(this.instanceCounter, type.toLowerCase(), `${sourceId}:${targetId}`),
           entityId: generateEntityId(type.toLowerCase(), `${sourceId}:${targetId}`),
           type,
           sourceId,
           targetId,
           createdAt: this.now,
           weight: 5
       };
   }

   // =============================================================================
   // Phase 1: Screen Extraction for Menu & Screen Indexing
   // =============================================================================

   /**
    * Extracts Screen nodes from view-states with full metadata.
    * Screens represent the actual UI pages users interact with.
    */
   private extractScreens(
       flowElement: Element,
       flowNode: WebFlowDefinitionNode,
       states: FlowStateNode[],
       transitions: FlowTransitionNode[]
   ): ScreenNode[] {
       const screens: ScreenNode[] = [];
       const flowId = flowNode.properties.flowId;

       // Only process view-states as screens
       const viewStates = states.filter(s => s.properties.stateType === 'view-state');

       for (const state of viewStates) {
           const stateElement = this.findStateElement(flowElement, state.properties.stateId);
           if (!stateElement) continue;

           const screenId = state.properties.stateId;

           // Extract screen title from on-entry set expressions
           const title = this.extractScreenTitle(stateElement, screenId);

           // Extract JSP references
           const jsps = this.extractJspReferences(stateElement, screenId);

           // Extract action class and methods from evaluate expressions
           const { actionClass, actionMethods } = this.extractActionInfo(stateElement);

           // Get transitions from this state
           const transitionsTo = transitions
               .filter(t => t.properties.fromStateId === screenId)
               .map(t => t.properties.toStateId);

           // Check for parent attribute
           const parentScreenId = stateElement.getAttribute('parent') || undefined;

           // Infer screen type from naming patterns
           const screenType = this.inferScreenType(screenId, jsps);

           // Check if maintenance mode
           const isMaintenanceMode = screenId.toLowerCase().includes('maintenance') ||
               title.toLowerCase().includes('maintenance');

           // Build URL pattern
           const urlPattern = `${flowId}.html?pageSelect=${screenId}`;

           const screenNode: ScreenNode = {
               id: generateInstanceId(this.instanceCounter, 'screen', screenId),
               entityId: generateEntityId('screen', `${flowId}:${screenId}`),
               kind: 'Screen',
               name: screenId,
               filePath: flowNode.filePath,
               language: 'SpringWebFlow',
               startLine: 1,
               endLine: 1,
               startColumn: 0,
               endColumn: 0,
               createdAt: this.now,
               properties: {
                   screenId,
                   title,
                   flowId,
                   screenType,
                   jsps,
                   entryJsp: jsps.find(j => j.includes('Entry')) || jsps[0],
                   resultsJsp: jsps.find(j => j.includes('Results')),
                   headerJsp: jsps.find(j => j.includes('Header') || j.includes('header')),
                   footerJsp: jsps.find(j => j.includes('Footer') || j.includes('footer') || j.includes('Comments')),
                   actionClass,
                   actionMethods,
                   transitionsTo,
                   parentScreenId,
                   isMaintenanceMode,
                   urlPattern,
               },
           };

           screens.push(screenNode);
       }

       return screens;
   }

   /**
    * Extract screen title from on-entry set expressions.
    */
   private extractScreenTitle(stateElement: Element, defaultTitle: string): string {
       const onEntryElements = stateElement.getElementsByTagName('on-entry');

       for (let i = 0; i < onEntryElements.length; i++) {
           const onEntry = onEntryElements[i];
           if (!onEntry) continue;

           const setElements = onEntry.getElementsByTagName('set');
           for (let j = 0; j < setElements.length; j++) {
               const set = setElements[j];
               if (!set) continue;

               const name = set.getAttribute('name') || '';
               const value = set.getAttribute('value') || '';

               // Look for title-related set expressions
               if (name.toLowerCase().includes('title') ||
                   name.includes('EntryTitle') ||
                   name.includes('ResultsTitle') ||
                   name.includes('LookupTitle')) {
                   // Extract string literal from value
                   const match = value.match(/'([^']+)'|"([^"]+)"/);
                   if (match) {
                       return match[1] || match[2] || defaultTitle;
                   }
               }
           }
       }

       // Try to humanize the screen ID as fallback
       return this.humanizeScreenId(defaultTitle);
   }

   /**
    * Extract JSP file references from the view-state.
    */
   private extractJspReferences(stateElement: Element, screenId: string): string[] {
       const jsps: string[] = [];

       // Check view attribute
       const view = stateElement.getAttribute('view');
       if (view && view.endsWith('.jsp')) {
           jsps.push(view);
       }

       // Check on-entry for JSP assignments
       const onEntryElements = stateElement.getElementsByTagName('on-entry');
       for (let i = 0; i < onEntryElements.length; i++) {
           const onEntry = onEntryElements[i];
           if (!onEntry) continue;

           const setElements = onEntry.getElementsByTagName('set');
           for (let j = 0; j < setElements.length; j++) {
               const set = setElements[j];
               if (!set) continue;

               const name = set.getAttribute('name') || '';
               const value = set.getAttribute('value') || '';

               // Look for JSP assignments
               if (name.includes('Jsp') || name.includes('jsp') || name.includes('JSP')) {
                   // Extract JSP filename from value
                   const jspMatch = value.match(/'([^']+\.jsp)'|"([^"]+\.jsp)"/);
                   if (jspMatch) {
                       jsps.push(jspMatch[1] || jspMatch[2]);
                   } else if (value.endsWith('.jsp')) {
                       jsps.push(value.replace(/['"`]/g, ''));
                   }
               }
           }
       }

       // If no JSPs found, infer from screen ID
       if (jsps.length === 0) {
           jsps.push(`${screenId}Entry.jsp`);
           jsps.push(`${screenId}Results.jsp`);
       }

       return [...new Set(jsps)]; // Remove duplicates
   }

   /**
    * Extract action class and methods from evaluate expressions.
    */
   private extractActionInfo(stateElement: Element): { actionClass: string; actionMethods: string[] } {
       const methods: string[] = [];
       let actionClass = '';

       // Search all evaluate expressions in the state
       const evaluateElements = stateElement.getElementsByTagName('evaluate');
       for (let i = 0; i < evaluateElements.length; i++) {
           const evaluate = evaluateElements[i];
           if (!evaluate) continue;

           const expression = evaluate.getAttribute('expression') || '';

           // Pattern: actionClassName.methodName(...)
           const match = expression.match(/(\w+Action)\.(\w+)\s*\(/);
           if (match) {
               actionClass = actionClass || match[1];
               methods.push(match[2]);
           }

           // Also check for service calls with Action suffix
           const serviceMatch = expression.match(/(\w+)Action\.(\w+)/);
           if (serviceMatch) {
               actionClass = actionClass || serviceMatch[1] + 'Action';
               if (!methods.includes(serviceMatch[2])) {
                   methods.push(serviceMatch[2]);
               }
           }
       }

       // Also check transitions for action methods
       const transitionElements = stateElement.getElementsByTagName('transition');
       for (let i = 0; i < transitionElements.length; i++) {
           const transition = transitionElements[i];
           if (!transition) continue;

           const evalInTransition = transition.getElementsByTagName('evaluate');
           for (let j = 0; j < evalInTransition.length; j++) {
               const evaluate = evalInTransition[j];
               if (!evaluate) continue;

               const expression = evaluate.getAttribute('expression') || '';
               const match = expression.match(/(\w+Action)\.(\w+)\s*\(/);
               if (match) {
                   actionClass = actionClass || match[1];
                   if (!methods.includes(match[2])) {
                       methods.push(match[2]);
                   }
               }
           }
       }

       return { actionClass, actionMethods: methods };
   }

   /**
    * Infer screen type from naming patterns.
    */
   private inferScreenType(screenId: string, jsps: string[]): 'entry' | 'results' | 'inquiry' | 'lookup' | 'wizard' | 'maintenance' | 'search' | 'unknown' {
       const idLower = screenId.toLowerCase();
       const jspString = jsps.join(' ').toLowerCase();

       if (idLower.includes('wizard') || jspString.includes('wizard')) return 'wizard';
       if (idLower.includes('search') || jspString.includes('search')) return 'search';
       if (idLower.includes('lookup') || jspString.includes('lookup')) return 'lookup';
       if (idLower.includes('inquiry') || jspString.includes('inquiry')) return 'inquiry';
       if (idLower.includes('results') || jspString.includes('results')) return 'results';
       if (idLower.includes('maintenance') || jspString.includes('maintenance')) return 'maintenance';
       if (idLower.includes('entry') || jspString.includes('entry')) return 'entry';

       return 'unknown';
   }

   /**
    * Convert a screen ID to a human-readable title.
    */
   private humanizeScreenId(screenId: string): string {
       // Convert camelCase to Title Case with spaces
       return screenId
           .replace(/([A-Z])/g, ' $1')
           .replace(/^./, str => str.toUpperCase())
           .trim();
   }
}