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
    ActionReference
} from '../types.js';
import { ensureTempDir, getTempFilePath, generateInstanceId, generateEntityId } from '../parser-utils.js';
import { BusinessRuleDetector } from './BusinessRuleDetector.js';

const logger = createContextLogger('WebFlowParser');

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

           return {
               filePath: normalizedPath,
               nodes: [...nodes, ...businessRuleNodes],
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
               condition
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
}