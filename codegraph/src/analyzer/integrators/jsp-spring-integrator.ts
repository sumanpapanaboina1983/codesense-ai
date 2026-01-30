import {
    AstNode,
    RelationshipInfo,
    JSPPageNode,
    JSPFormNode,
    WebFlowDefinitionNode,
    FlowStateNode,
    FlowActionNode,
    SpringControllerNode,
    FlowActionMethodNode,
    SpringServiceNode
} from '../types.js';
import { generateEntityId, generateInstanceId } from '../parser-utils.js';
import { createContextLogger } from '../../utils/logger.js';
import path from 'path';

const logger = createContextLogger('JSPSpringIntegrator');

export interface IntegrationContext {
    jspNodes: JSPPageNode[];
    jspFormNodes: JSPFormNode[];
    webFlowNodes: WebFlowDefinitionNode[];
    flowStateNodes: FlowStateNode[];
    flowActionNodes: FlowActionNode[];
    springControllerNodes: SpringControllerNode[];
    flowActionMethodNodes: FlowActionMethodNode[];
    springServiceNodes: SpringServiceNode[];
    allNodes: AstNode[];
}

export class JSPSpringIntegrator {
    private instanceCounter = { count: 0 };
    private now = new Date().toISOString();

    /**
     * Main integration method that creates cross-layer relationships.
     */
    async integrateAll(context: IntegrationContext): Promise<RelationshipInfo[]> {
        logger.info('Starting JSP-Spring integration process');

        const relationships: RelationshipInfo[] = [];

        // 1. Link JSP forms to Web Flows
        relationships.push(...this.linkJSPFormsToFlows(context));

        // 2. Link Flow view states to JSP pages
        relationships.push(...this.linkFlowStatesToViews(context));

        // 3. Link Flow actions to Java methods
        relationships.push(...this.linkFlowActionsToMethods(context));

        // 4. Link Controllers to Flows
        relationships.push(...this.linkControllersToFlows(context));

        // 5. Link Flow actions to Service methods
        relationships.push(...this.linkActionsToServices(context));

        // 6. Create JSP navigation chains
        relationships.push(...this.createJSPNavigationChains(context));

        // 7. Link JSP EL expressions to model objects
        relationships.push(...this.linkELExpressionsToModels(context));

        logger.info(`Integration completed. Created ${relationships.length} cross-layer relationships`);
        return relationships;
    }

    /**
     * Links JSP forms to Web Flow definitions based on form action patterns.
     */
    private linkJSPFormsToFlows(context: IntegrationContext): RelationshipInfo[] {
        const relationships: RelationshipInfo[] = [];

        context.jspFormNodes.forEach(form => {
            const action = form.properties.action;

            // Match action patterns to flow IDs
            const matchingFlow = this.findFlowByActionPattern(action, context.webFlowNodes);

            if (matchingFlow) {
                relationships.push(this.createRelationship(
                    'SUBMITS_TO_FLOW',
                    form.entityId,
                    matchingFlow.entityId,
                    {
                        actionPath: action,
                        method: form.properties.method,
                        formFields: form.properties.fields.map(f => f.name)
                    }
                ));

                logger.debug(`Linked JSP form ${form.name} to flow ${matchingFlow.properties.flowId}`);
            }
        });

        return relationships;
    }

    /**
     * Links Flow view states to JSP pages.
     */
    private linkFlowStatesToViews(context: IntegrationContext): RelationshipInfo[] {
        const relationships: RelationshipInfo[] = [];

        context.flowStateNodes.forEach(state => {
            if (state.properties.stateType === 'view-state' && state.properties.view) {
                const viewName = state.properties.view;
                const matchingJSP = this.findJSPByViewName(viewName, context.jspNodes);

                if (matchingJSP) {
                    relationships.push(this.createRelationship(
                        'FLOW_RENDERS_VIEW',
                        state.entityId,
                        matchingJSP.entityId,
                        {
                            viewName,
                            stateId: state.properties.stateId
                        }
                    ));

                    logger.debug(`Linked flow state ${state.properties.stateId} to JSP ${matchingJSP.name}`);
                }
            }
        });

        return relationships;
    }

    /**
     * Links Flow actions to Java methods.
     */
    private linkFlowActionsToMethods(context: IntegrationContext): RelationshipInfo[] {
        const relationships: RelationshipInfo[] = [];

        context.flowActionNodes.forEach(action => {
            if (action.properties.beanMethod) {
                const beanMethodParts = action.properties.beanMethod.split('.');
                if (beanMethodParts.length >= 2) {
                    const beanName = beanMethodParts[0];
                    const methodName = beanMethodParts[1];
                    if (beanName && methodName) {
                        const matchingMethod = this.findMethodByBeanAndName(beanName, methodName, context);

                        if (matchingMethod) {
                        relationships.push(this.createRelationship(
                            'ACTION_EVALUATES_EXPRESSION',
                            action.entityId,
                            matchingMethod.entityId,
                            {
                                beanMethod: action.properties.beanMethod,
                                actionType: action.properties.actionType
                            }
                        ));

                        logger.debug(`Linked flow action ${action.name} to method ${matchingMethod.name}`);
                        }
                    }
                }
            } else if (action.properties.expression) {
                // Try to resolve expression to methods or services
                const expressionMethods = this.resolveExpressionToMethods(action.properties.expression, context);

                expressionMethods.forEach(method => {
                    relationships.push(this.createRelationship(
                        'ACTION_EVALUATES_EXPRESSION',
                        action.entityId,
                        method.entityId,
                        {
                            expression: action.properties.expression,
                            actionType: action.properties.actionType
                        }
                    ));
                });
            }
        });

        return relationships;
    }

    /**
     * Links Spring Controllers to Web Flows they handle.
     */
    private linkControllersToFlows(context: IntegrationContext): RelationshipInfo[] {
        const relationships: RelationshipInfo[] = [];

        context.springControllerNodes.forEach(controller => {
            if (controller.properties.isFlowController) {
                // Find flows that this controller might handle
                const handledFlows = this.findFlowsHandledByController(controller, context.webFlowNodes);

                handledFlows.forEach(flow => {
                    relationships.push(this.createRelationship(
                        'CONTROLLER_HANDLES_FLOW',
                        controller.entityId,
                        flow.entityId,
                        {
                            controllerType: 'FlowController',
                            requestMappings: controller.properties.requestMappings?.map(rm => rm.path)
                        }
                    ));

                    logger.debug(`Linked controller ${controller.name} to flow ${flow.properties.flowId}`);
                });
            }
        });

        return relationships;
    }

    /**
     * Links Flow action methods to Service methods they call.
     */
    private linkActionsToServices(context: IntegrationContext): RelationshipInfo[] {
        const relationships: RelationshipInfo[] = [];

        context.flowActionMethodNodes.forEach(actionMethod => {
            // Analyze method body to find service calls
            const serviceCalls = this.findServiceCallsInMethod(actionMethod, context);

            serviceCalls.forEach(serviceCall => {
                relationships.push(this.createRelationship(
                    'ACTION_CALLS_SERVICE',
                    actionMethod.entityId,
                    serviceCall.entityId,
                    {
                        callType: 'service_invocation',
                        methodName: serviceCall.name
                    }
                ));

                logger.debug(`Linked action method ${actionMethod.name} to service ${serviceCall.name}`);
            });
        });

        return relationships;
    }

    /**
     * Creates JSP navigation chains (includes, forwards, redirects).
     */
    private createJSPNavigationChains(context: IntegrationContext): RelationshipInfo[] {
        const relationships: RelationshipInfo[] = [];

        context.jspNodes.forEach(jsp => {
            // Handle includes
            jsp.properties.includes.forEach(includePath => {
                const targetJSP = this.findJSPByPath(includePath, context.jspNodes);
                if (targetJSP) {
                    relationships.push(this.createRelationship(
                        'INCLUDES_JSP',
                        jsp.entityId,
                        targetJSP.entityId,
                        { includePath }
                    ));
                }
            });

            // Handle forwards and redirects (would need to parse JSP content more deeply)
            const navigationTargets = this.extractNavigationTargets(jsp);
            navigationTargets.forEach(target => {
                const targetJSP = this.findJSPByPath(target.path, context.jspNodes);
                if (targetJSP) {
                    relationships.push(this.createRelationship(
                        target.type === 'forward' ? 'FORWARDS_TO_JSP' : 'REDIRECTS_TO_JSP',
                        jsp.entityId,
                        targetJSP.entityId,
                        { navigationPath: target.path }
                    ));
                }
            });
        });

        return relationships;
    }

    /**
     * Links JSP EL expressions to Java model objects.
     */
    private linkELExpressionsToModels(context: IntegrationContext): RelationshipInfo[] {
        const relationships: RelationshipInfo[] = [];

        context.jspNodes.forEach(jsp => {
            jsp.properties.elExpressions.forEach(expression => {
                const modelReferences = this.resolveELExpressionToModels(expression, context);

                modelReferences.forEach(model => {
                    relationships.push(this.createRelationship(
                        'VIEW_BINDS_MODEL',
                        jsp.entityId,
                        model.entityId,
                        {
                            expression,
                            modelProperty: this.extractModelProperty(expression)
                        }
                    ));
                });
            });
        });

        return relationships;
    }

    // Helper methods for pattern matching and resolution

    private findFlowByActionPattern(action: string, flows: WebFlowDefinitionNode[]): WebFlowDefinitionNode | undefined {
        // Common patterns:
        // /app/checkout -> checkout flow
        // /flow/user-registration -> user-registration flow
        // /myapp/flows/payment -> payment flow

        const normalizedAction = action.toLowerCase().replace(/^\/+/, '');

        return flows.find(flow => {
            const flowId = flow.properties.flowId.toLowerCase();

            // Direct match
            if (normalizedAction.includes(flowId)) {
                return true;
            }

            // Check if action ends with flow name
            if (normalizedAction.endsWith(flowId)) {
                return true;
            }

            // Check common URL patterns
            const actionParts = normalizedAction.split('/');
            const lastPart = actionParts[actionParts.length - 1];

            if (lastPart && (lastPart === flowId || lastPart.includes(flowId))) {
                return true;
            }

            return false;
        });
    }

    private findJSPByViewName(viewName: string, jsps: JSPPageNode[]): JSPPageNode | undefined {
        // View name might be:
        // - Simple name: "checkout"
        // - Path: "/views/checkout"
        // - Full path: "/WEB-INF/views/checkout.jsp"

        return jsps.find(jsp => {
            const jspName = path.basename(jsp.name, '.jsp');
            const jspPath = jsp.properties.servletPath;

            // Direct name match
            if (jspName === viewName || jsp.name === viewName) {
                return true;
            }

            // Path contains view name
            if (jspPath.includes(viewName)) {
                return true;
            }

            // Check if view name is a path segment
            const viewParts = viewName.split('/');
            const lastViewPart = viewParts[viewParts.length - 1];

            if (lastViewPart && jspName === lastViewPart) {
                return true;
            }

            return false;
        });
    }

    private findMethodByBeanAndName(beanName: string, methodName: string, context: IntegrationContext): AstNode | undefined {
        // Look in services first, then controllers
        const allMethods = [
            ...context.flowActionMethodNodes,
            ...context.allNodes.filter(n => n.kind === 'JavaMethod')
        ];

        return allMethods.find(method => {
            // Check if method belongs to a class that could be the bean
            const parentClass = context.allNodes.find(n =>
                n.entityId === method.parentId &&
                (n.kind === 'SpringService' || n.kind === 'SpringController' || n.kind === 'JavaClass')
            );

            if (parentClass) {
                const className = parentClass.name.toLowerCase();
                const beanNameLower = beanName.toLowerCase();

                // Check various naming conventions
                if (className === beanNameLower ||
                    className === beanNameLower + 'service' ||
                    className === beanNameLower + 'controller' ||
                    className === beanNameLower + 'impl') {
                    return method.name === methodName;
                }
            }

            return false;
        });
    }

    private resolveExpressionToMethods(expression: string, context: IntegrationContext): AstNode[] {
        const methods: AstNode[] = [];

        // Parse expression for method calls
        // Example: "userService.validateUser(user)" -> look for validateUser method in userService
        const methodCallPattern = /(\w+)\.(\w+)\s*\(/g;
        let match;

        while ((match = methodCallPattern.exec(expression)) !== null) {
            const beanName = match[1];
            const methodName = match[2];

            if (beanName && methodName) {
                const method = this.findMethodByBeanAndName(beanName, methodName, context);
                if (method) {
                    methods.push(method);
                }
            }
        }

        return methods;
    }

    private findFlowsHandledByController(controller: SpringControllerNode, flows: WebFlowDefinitionNode[]): WebFlowDefinitionNode[] {
        const handledFlows: WebFlowDefinitionNode[] = [];

        // Check request mappings against flow patterns
        controller.properties.requestMappings?.forEach(mapping => {
            const path = mapping.path.toLowerCase();

            flows.forEach(flow => {
                const flowId = flow.properties.flowId.toLowerCase();

                if (path.includes(flowId) || path.includes('flow')) {
                    handledFlows.push(flow);
                }
            });
        });

        return handledFlows;
    }

    private findServiceCallsInMethod(actionMethod: FlowActionMethodNode, context: IntegrationContext): AstNode[] {
        const serviceCalls: AstNode[] = [];

        // This would require analyzing the actual method body
        // For now, we'll use the flow bindings as hints
        actionMethod.properties.flowBindings.forEach(binding => {
            const relatedServices = context.springServiceNodes.filter(service =>
                binding.toLowerCase().includes(service.name.toLowerCase().replace('service', ''))
            );

            serviceCalls.push(...relatedServices);
        });

        return serviceCalls;
    }

    private findJSPByPath(includePath: string, jsps: JSPPageNode[]): JSPPageNode | undefined {
        const normalizedPath = includePath.replace(/^\/+/, '');

        return jsps.find(jsp => {
            const jspPath = jsp.properties.servletPath.replace(/^\/+/, '');
            return jspPath === normalizedPath || jspPath.endsWith(normalizedPath);
        });
    }

private extractNavigationTargets(jsp: JSPPageNode): Array<{type: 'forward' | 'redirect', path: string}> {
       // This would require parsing JSP content for forward/redirect patterns
       // Implementation would analyze jsp:forward, c:redirect, response.sendRedirect, etc.
       return [];
   }

   private resolveELExpressionToModels(expression: string, context: IntegrationContext): AstNode[] {
       const models: AstNode[] = [];

       // Parse EL expression for model references
       // Example: "${user.name}" -> look for User model
       // Example: "${sessionScope.cart.items}" -> look for Cart model

       const modelPattern = /\$\{(?:\w+Scope\.)?(\w+)(?:\.(\w+))?\}/;
       const match = expression.match(modelPattern);

       if (match) {
           const modelName = match[1];
           const property = match[2];

           if (modelName) {
               // Look for Java classes that might represent this model
               const potentialModels = context.allNodes.filter(node =>
                   (node.kind === 'JavaClass' || node.kind === 'SpringService') &&
                   this.isModelMatch(node.name, modelName)
               );

               models.push(...potentialModels);
           }
       }

       return models;
   }

   private isModelMatch(className: string, modelName: string): boolean {
       const classNameLower = className.toLowerCase();
       const modelNameLower = modelName.toLowerCase();

       // Direct match
       if (classNameLower === modelNameLower) return true;

       // Class name contains model name
       if (classNameLower.includes(modelNameLower)) return true;

       // Model name is plural of class name
       if (modelNameLower === classNameLower + 's') return true;

       // Common naming patterns
       if (classNameLower === modelNameLower + 'model' ||
           classNameLower === modelNameLower + 'entity' ||
           classNameLower === modelNameLower + 'dto') return true;

       return false;
   }

   private extractModelProperty(expression: string): string | undefined {
       const match = expression.match(/\$\{\w+\.(\w+)(?:\.\w+)*\}/);
       return match ? match[1] : undefined;
   }

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
           properties,
           createdAt: this.now,
           weight: 7
       };
   }
}