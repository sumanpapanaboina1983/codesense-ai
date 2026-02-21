import { JavaParser } from './java-parser.js';
import { FileInfo } from '../../scanner/file-scanner.js';
import {
    AstNode,
    RelationshipInfo,
    SingleFileParseResult,
    SpringControllerNode,
    FlowActionMethodNode,
    SpringServiceNode,
    RequestMapping,
    FlowParameter
} from '../types.js';
import { createContextLogger } from '../../utils/logger.js';
import { generateEntityId, generateInstanceId } from '../parser-utils.js';

const logger = createContextLogger('EnhancedJavaParser');

// Spring annotation patterns
const SPRING_ANNOTATIONS = {
    CONTROLLER: /@Controller\s*(\([^)]*\))?/,
    REST_CONTROLLER: /@RestController\s*(\([^)]*\))?/,
    SERVICE: /@Service\s*(\([^)]*\))?/,
    REPOSITORY: /@Repository\s*(\([^)]*\))?/,
    COMPONENT: /@Component\s*(\([^)]*\))?/,
    REQUEST_MAPPING: /@RequestMapping\s*\(([^)]*)\)/g,
    GET_MAPPING: /@GetMapping\s*\(([^)]*)\)/g,
    POST_MAPPING: /@PostMapping\s*\(([^)]*)\)/g,
    PUT_MAPPING: /@PutMapping\s*\(([^)]*)\)/g,
    DELETE_MAPPING: /@DeleteMapping\s*\(([^)]*)\)/g,
    TRANSACTIONAL: /@Transactional\s*(\([^)]*\))?/,
    QUALIFIER: /@Qualifier\s*\(\s*["']([^"']+)["']\s*\)/,
    AUTOWIRED: /@Autowired/,
    SESSION_ATTRIBUTES: /@SessionAttributes\s*\(([^)]*)\)/
};

// Web Flow annotation patterns
const WEBFLOW_PATTERNS = {
    ACTION_METHOD: /public\s+\w+\s+(\w+)\s*\([^)]*RequestContext[^)]*\)/g,
    FLOW_HANDLER: /@FlowHandler/,
    FLOW_MAPPING: /@FlowMapping\s*\(([^)]*)\)/,
    FLOW_DEFINITION: /\.createFlow\s*\(\s*["']([^"']+)["']/g
};

export class EnhancedJavaParser extends JavaParser {

    constructor() {
        super();
        logger.debug('Enhanced Java Parser with Spring support initialized');
    }

    /**
     * Enhanced parseFile method that delegates to parent and then enhances with Spring analysis.
     */
    override async parseFile(file: FileInfo): Promise<string> {
        // First run the standard Java parser
        const tempFilePath = await super.parseFile(file);

        // Read the result and enhance it
        const fs = await import('fs/promises');
        const resultContent = await fs.readFile(tempFilePath, 'utf-8');
        const result: SingleFileParseResult = JSON.parse(resultContent);

        // Enhance with Spring-specific analysis
        const enhancedResult = await this.enhanceWithSpringAnalysis(result, file.path);

        // Write back the enhanced result
        await fs.writeFile(tempFilePath, JSON.stringify(enhancedResult, null, 2));

        return tempFilePath;
    }

    /**
     * Enhances the parsed Java result with Spring-specific analysis.
     */
    private async enhanceWithSpringAnalysis(result: SingleFileParseResult, filePath: string): Promise<SingleFileParseResult> {
        const fs = await import('fs/promises');
        const content = await fs.readFile(filePath, 'utf-8');

        const enhancedNodes: AstNode[] = [...result.nodes];
        const enhancedRelationships: RelationshipInfo[] = [...result.relationships];

        // Find Java class nodes and enhance them
        const classNodes = result.nodes.filter(node => node.kind === 'JavaClass');
        logger.debug(`Found ${classNodes.length} Java class nodes to enhance: ${classNodes.map(n => n.name).join(', ')}`);

        for (const classNode of classNodes) {
            // Use the entire file content for annotation detection since annotations appear before class
            logger.debug(`Checking ${classNode.name} for Spring annotations in file content (length: ${content.length})`);

            // Check if it's a Flow Handler first (Component with RequestContext methods)
            if (this.isFlowHandler(content)) {
                logger.debug(`${classNode.name} is a Flow Handler`);
                const serviceNode = this.createSpringServiceNode(classNode, content);
                const index = enhancedNodes.findIndex(n => n.entityId === classNode.entityId);
                if (index >= 0) {
                    enhancedNodes[index] = serviceNode;
                }
            }
            // Check if it's a Spring Controller
            else if (this.isSpringController(content)) {
                logger.debug(`${classNode.name} is a Spring Controller`);
                const controllerNode = this.createSpringControllerNode(classNode, content);
                const index = enhancedNodes.findIndex(n => n.entityId === classNode.entityId);
                if (index >= 0) {
                    enhancedNodes[index] = controllerNode;
                }

                // Parse controller methods
                const controllerMethods = this.parseControllerMethods(content, controllerNode.entityId);
                enhancedNodes.push(...controllerMethods);

                // Create method relationships
                controllerMethods.forEach(method => {
                    enhancedRelationships.push({
                        id: generateInstanceId({ count: 0 }, 'hasmethods', `${controllerNode.entityId}:${method.entityId}`),
                        entityId: generateEntityId('hasmethod', `${controllerNode.entityId}:${method.entityId}`),
                        type: 'HAS_METHOD',
                        sourceId: controllerNode.entityId,
                        targetId: method.entityId,
                        createdAt: new Date().toISOString(),
                        weight: 8
                    });
                });
            }

            // Check if it's a Spring Service
            else if (this.isSpringService(content)) {
                logger.debug(`${classNode.name} is a Spring Service`);
                const serviceNode = this.createSpringServiceNode(classNode, content);
                const index = enhancedNodes.findIndex(n => n.entityId === classNode.entityId);
                if (index >= 0) {
                    enhancedNodes[index] = serviceNode;
                }
            }
            else {
                logger.debug(`${classNode.name} is not a recognized Spring component`);
            }
        }

        // Find and enhance methods that might be flow actions
        const methodNodes = result.nodes.filter(node => node.kind === 'JavaMethod');

        for (const methodNode of methodNodes) {
            const methodContent = this.extractMethodContent(content, methodNode.name);

            if (this.isFlowActionMethod(methodContent)) {
                const flowActionMethod = this.createFlowActionMethodNode(methodNode, methodContent);
                const index = enhancedNodes.findIndex(n => n.entityId === methodNode.entityId);
                if (index >= 0) {
                    enhancedNodes[index] = flowActionMethod;
                }
            }
        }

        return {
            filePath: result.filePath,
            nodes: enhancedNodes,
            relationships: enhancedRelationships
        };
    }

    /**
     * Checks if a class is a Spring Controller.
     */
    private isSpringController(classContent: string): boolean {
        return SPRING_ANNOTATIONS.CONTROLLER.test(classContent) ||
               SPRING_ANNOTATIONS.REST_CONTROLLER.test(classContent);
    }

    /**
     * Checks if a class is a Spring Service.
     */
    private isSpringService(classContent: string): boolean {
        return SPRING_ANNOTATIONS.SERVICE.test(classContent) ||
               SPRING_ANNOTATIONS.REPOSITORY.test(classContent) ||
               SPRING_ANNOTATIONS.COMPONENT.test(classContent);
    }

    /**
     * Checks if a class is a Flow Handler (Component with flow methods).
     */
    private isFlowHandler(classContent: string): boolean {
        return SPRING_ANNOTATIONS.COMPONENT.test(classContent) &&
               (classContent.includes('RequestContext') || classContent.includes('FlowRequestContext'));
    }

    /**
     * Checks if a method is a Web Flow action method.
     */
    private isFlowActionMethod(methodContent: string): boolean {
        return methodContent.includes('RequestContext') ||
               methodContent.includes('FlowRequestContext') ||
               WEBFLOW_PATTERNS.FLOW_HANDLER.test(methodContent);
    }

    /**
     * Creates a Spring Controller node from a Java class node.
     */
    private createSpringControllerNode(classNode: AstNode, classContent: string): SpringControllerNode {
        const requestMappings = this.parseRequestMappings(classContent);
        const sessionAttributes = this.parseSessionAttributes(classContent);
        const isFlowController = this.isFlowController(classContent);

        return {
            ...classNode,
            kind: 'SpringController',properties: {
               ...classNode.properties,
               requestMappings,
               isFlowController,
               sessionAttributes: sessionAttributes.length > 0 ? sessionAttributes : undefined,
               controllerAdvice: SPRING_ANNOTATIONS.CONTROLLER.test(classContent) &&
                                classContent.includes('@ControllerAdvice')
           }
       } as SpringControllerNode;
   }

   /**
    * Creates a Spring Service node from a Java class node.
    */
   private createSpringServiceNode(classNode: AstNode, classContent: string): SpringServiceNode {
       let serviceType: 'service' | 'repository' | 'component' = 'service';

       if (SPRING_ANNOTATIONS.REPOSITORY.test(classContent)) {
           serviceType = 'repository';
       } else if (SPRING_ANNOTATIONS.COMPONENT.test(classContent)) {
           serviceType = 'component';
       }

       const transactional = SPRING_ANNOTATIONS.TRANSACTIONAL.test(classContent);
       const qualifierMatch = classContent.match(SPRING_ANNOTATIONS.QUALIFIER);
       const qualifier = qualifierMatch ? qualifierMatch[1] : undefined;

       return {
           ...classNode,
           kind: 'SpringService',
           properties: {
               ...classNode.properties,
               serviceType,
               transactional,
               qualifier
           }
       } as SpringServiceNode;
   }

   /**
    * Creates a Flow Action Method node from a Java method node.
    */
   private createFlowActionMethodNode(methodNode: AstNode, methodContent: string): FlowActionMethodNode {
       const flowBindings = this.parseFlowBindings(methodContent);
       const flowParameters = this.parseFlowParameters(methodContent);
       const flowReturnType = this.parseFlowReturnType(methodContent);
       const canThrowFlowException = methodContent.includes('FlowExecutionException') ||
                                    methodContent.includes('throws') && methodContent.includes('Exception');

       return {
           ...methodNode,
           kind: 'FlowActionMethod',
           properties: {
               ...methodNode.properties,
               flowBindings,
               flowParameters,
               flowReturnType,
               canThrowFlowException
           }
       } as FlowActionMethodNode;
   }

   /**
    * Parses controller methods from class content.
    */
   private parseControllerMethods(classContent: string, parentEntityId: string): AstNode[] {
       const methods: AstNode[] = [];
       const methodPattern = /@(RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|FlowMapping)\s*\([^)]*\)\s*(?:public|private|protected)?\s*\w+\s+(\w+)\s*\([^)]*\)/g;

       let match;
       while ((match = methodPattern.exec(classContent)) !== null) {
           const annotation = match[1];
           const methodName = match[2];

           if (!methodName) continue;

           const requestMappings = this.parseMethodRequestMappings(match[0]);
           const isFlowMethod = annotation === 'FlowMapping' || match[0].includes('RequestContext');

           const methodEntityId = generateEntityId('javamethod', `${parentEntityId}.${methodName}`);

           methods.push({
               id: generateInstanceId({ count: 0 }, 'javamethod', methodName),
               entityId: methodEntityId,
               kind: isFlowMethod ? 'FlowActionMethod' : 'JavaMethod',
               name: methodName,
               filePath: parentEntityId.split(':')[1] || '',
               language: 'Java',
               startLine: this.getLineNumber(classContent, match.index),
               endLine: this.getLineNumber(classContent, match.index + match[0].length),
               startColumn: 0,
               endColumn: 0,
               parentId: parentEntityId,
               createdAt: new Date().toISOString(),
               properties: {
                   requestMappings: requestMappings.length > 0 ? requestMappings : undefined,
                   isFlowMethod,
                   annotation
               }
           });
       }

       return methods;
   }

   /**
    * Parses request mappings from class content.
    */
   private parseRequestMappings(classContent: string): RequestMapping[] {
       const mappings: RequestMapping[] = [];

       // Parse @RequestMapping annotations
       this.parseSpecificMapping(classContent, SPRING_ANNOTATIONS.REQUEST_MAPPING, ['GET', 'POST'], mappings);
       this.parseSpecificMapping(classContent, SPRING_ANNOTATIONS.GET_MAPPING, ['GET'], mappings);
       this.parseSpecificMapping(classContent, SPRING_ANNOTATIONS.POST_MAPPING, ['POST'], mappings);
       this.parseSpecificMapping(classContent, SPRING_ANNOTATIONS.PUT_MAPPING, ['PUT'], mappings);
       this.parseSpecificMapping(classContent, SPRING_ANNOTATIONS.DELETE_MAPPING, ['DELETE'], mappings);

       return mappings;
   }

   /**
    * Parses method-level request mappings.
    */
   private parseMethodRequestMappings(methodAnnotation: string): RequestMapping[] {
       const mappings: RequestMapping[] = [];

       // Extract path from annotation
       const pathMatch = methodAnnotation.match(/(?:value|path)\s*=\s*(?:\{[^}]*\}|"([^"]+)"|'([^']+)')/);
       const path = pathMatch ? (pathMatch[1] || pathMatch[2] || '') : '';

       // Extract method from annotation type
       let method = ['GET']; // default
       if (methodAnnotation.includes('@PostMapping')) method = ['POST'];
       else if (methodAnnotation.includes('@PutMapping')) method = ['PUT'];
       else if (methodAnnotation.includes('@DeleteMapping')) method = ['DELETE'];
       else if (methodAnnotation.includes('@RequestMapping')) {
           const methodMatch = methodAnnotation.match(/method\s*=\s*RequestMethod\.(\w+)/);
           if (methodMatch && methodMatch[1]) {
               method = [methodMatch[1]];
           }
       }

       mappings.push({
           path,
           method,
           params: this.extractArrayAttribute(methodAnnotation, 'params'),
           headers: this.extractArrayAttribute(methodAnnotation, 'headers'),
           consumes: this.extractArrayAttribute(methodAnnotation, 'consumes'),
           produces: this.extractArrayAttribute(methodAnnotation, 'produces')
       });

       return mappings;
   }

   /**
    * Parses session attributes from @SessionAttributes annotation.
    */
   private parseSessionAttributes(classContent: string): string[] {
       const match = classContent.match(SPRING_ANNOTATIONS.SESSION_ATTRIBUTES);
       if (!match) return [];

       const attributesContent = match[1];
       const attributes: string[] = [];

       if (!attributesContent) return attributes;

       // Parse array of strings
       const arrayMatch = attributesContent.match(/\{([^}]+)\}/);
       if (arrayMatch && arrayMatch[1]) {
           const items = arrayMatch[1].split(',');
           items.forEach(item => {
               const cleaned = item.trim().replace(/["']/g, '');
               if (cleaned) attributes.push(cleaned);
           });
       } else {
           // Single string
           const singleMatch = attributesContent.match(/["']([^"']+)["']/);
           if (singleMatch && singleMatch[1]) {
               attributes.push(singleMatch[1]);
           }
       }

       return attributes;
   }

   /**
    * Checks if a controller is a Flow Controller.
    */
   private isFlowController(classContent: string): boolean {
       return WEBFLOW_PATTERNS.FLOW_HANDLER.test(classContent) ||
              classContent.includes('FlowController') ||
              classContent.includes('RequestContext') ||
              WEBFLOW_PATTERNS.FLOW_MAPPING.test(classContent);
   }

   /**
    * Parses flow bindings from method content.
    */
   private parseFlowBindings(methodContent: string): string[] {
       const bindings: string[] = [];

       // Look for @FlowMapping annotations
       const flowMappingMatches = methodContent.match(WEBFLOW_PATTERNS.FLOW_MAPPING);
       if (flowMappingMatches) {
           flowMappingMatches.forEach(match => {
               const valueMatch = match.match(/value\s*=\s*["']([^"']+)["']/);
               if (valueMatch && valueMatch[1]) {
                   bindings.push(valueMatch[1]);
               }
           });
       }

       // Look for flow definition references
       const flowDefMatches = methodContent.match(WEBFLOW_PATTERNS.FLOW_DEFINITION);
       if (flowDefMatches) {
           flowDefMatches.forEach(match => {
               if (match[1]) {
                   bindings.push(match[1]);
               }
           });
       }

       return bindings;
   }

   /**
    * Parses flow parameters from method signature.
    */
   private parseFlowParameters(methodContent: string): FlowParameter[] {
       const parameters: FlowParameter[] = [];

       // Extract method signature
       const methodMatch = methodContent.match(/(\w+)\s*\(([^)]*)\)/);
       if (!methodMatch) return parameters;

       const paramString = methodMatch[2];
       if (!paramString) return parameters;
       
       const params = paramString.split(',');

       params.forEach(param => {
           const trimmed = param.trim();
           if (trimmed) {
               const parts = trimmed.split(/\s+/);
               if (parts.length >= 2) {
                   const type = parts[parts.length - 2];
                   const name = parts[parts.length - 1];

                   if (type && name) {
                       parameters.push({
                           name,
                           type,
                           required: !type.includes('Optional') && !trimmed.includes('@RequestParam(required=false)'),
                           scope: this.extractParameterScope(trimmed)
                       });
                   }
               }
           }
       });

       return parameters;
   }

   /**
    * Parses flow return type from method signature.
    */
   private parseFlowReturnType(methodContent: string): string | undefined {
       const methodMatch = methodContent.match(/(?:public|private|protected)?\s*(\w+(?:<[^>]+>)?)\s+\w+\s*\(/);
       if (methodMatch) {
           const returnType = methodMatch[1];
           if (returnType !== 'void') {
               return returnType;
           }
       }
       return undefined;
   }

   // Helper methods
   private parseSpecificMapping(content: string, pattern: RegExp, defaultMethods: string[], mappings: RequestMapping[]): void {
       let match;
       pattern.lastIndex = 0;
       while ((match = pattern.exec(content)) !== null) {
           const annotationContent = match[1] || '';

           const pathMatch = annotationContent.match(/(?:value|path)\s*=\s*(?:"([^"]+)"|'([^']+)'|\{[^}]*"([^"]+)")/);

           const path = pathMatch ? (pathMatch[1] || pathMatch[2] || pathMatch[3] || '') : '';

           let method = defaultMethods;
           const methodMatch = annotationContent.match(/method\s*=\s*(?:RequestMethod\.(\w+)|\{[^}]*RequestMethod\.(\w+))/);
           if (methodMatch) {
               const matchedMethod = methodMatch[1] || methodMatch[2];
               if (matchedMethod) {
                   method = [matchedMethod];
               }
           }

           mappings.push({
               path,
               method,
               params: this.extractArrayAttribute(annotationContent, 'params'),
               headers: this.extractArrayAttribute(annotationContent, 'headers'),
               consumes: this.extractArrayAttribute(annotationContent, 'consumes'),
               produces: this.extractArrayAttribute(annotationContent, 'produces')
           });
       }
   }

   private extractArrayAttribute(content: string, attributeName: string): string[] | undefined {
       const pattern = new RegExp(`${attributeName}\\s*=\\s*(?:\\{([^}]+)\\}|"([^"]+)"|'([^']+)')`, 'g');
       const match = pattern.exec(content);

       if (!match) return undefined;

       if (match[1]) {
           // Array format: {item1, item2, item3}
           return match[1].split(',').map(item => item.trim().replace(/["']/g, ''));
       } else {
           // Single item
           const singleItem = match[2] || match[3];
           return singleItem ? [singleItem] : undefined;
       }
   }

   private extractParameterScope(paramString: string): string | undefined {
       if (paramString.includes('@FlowScope')) return 'flow';
       if (paramString.includes('@ViewScope')) return 'view';
       if (paramString.includes('@RequestScope')) return 'request';
       if (paramString.includes('@SessionScope')) return 'session';
       return undefined;
   }

   private extractClassContent(fullContent: string, className: string): string {
       const classPattern = new RegExp(`class\\s+${className}[^{]*\\{`, 'g');
       const match = classPattern.exec(fullContent);

       if (!match) return '';

       const classStartIndex = match.index;
       
       // Find the start of annotations before the class
       // Look backwards from class declaration to find annotations
       let annotationStartIndex = classStartIndex;
       const lines = fullContent.substring(0, classStartIndex).split('\n');
       
       for (let i = lines.length - 1; i >= 0; i--) {
           const line = lines[i]?.trim() || '';
           if (line.startsWith('@') || line === '' || line.startsWith('//') || line.startsWith('/*')) {
               // This line is an annotation, comment, or empty - include it
               if (line.startsWith('@') && lines[i]) {
                   const searchStartPos = i === 0 ? 0 : fullContent.lastIndexOf('\n', annotationStartIndex - 1);
                   annotationStartIndex = fullContent.indexOf(lines[i]!, searchStartPos >= 0 ? searchStartPos : 0);
               }
               continue;
           } else {
               // Found a non-annotation line, stop looking backwards
               break;
           }
       }

       // Find the end of the class by counting braces
       let braceCount = 0;
       let endIndex = classStartIndex;

       for (let i = classStartIndex; i < fullContent.length; i++) {
           if (fullContent[i] === '{') braceCount++;
           if (fullContent[i] === '}') braceCount--;
           if (braceCount === 0) {
               endIndex = i + 1;
               break;
           }
       }

       return fullContent.substring(annotationStartIndex, endIndex);
   }

   private extractMethodContent(fullContent: string, methodName: string): string {
       const methodPattern = new RegExp(`\\b${methodName}\\s*\\([^)]*\\)\\s*(?:throws[^{]*)?\\{`, 'g');
       const match = methodPattern.exec(fullContent);

       if (!match) return '';

       const startIndex = match.index;
       let braceCount = 0;
       let endIndex = startIndex;

       for (let i = startIndex; i < fullContent.length; i++) {
           if (fullContent[i] === '{') braceCount++;
           if (fullContent[i] === '}') braceCount--;
           if (braceCount === 0) {
               endIndex = i + 1;
               break;
           }
       }

       return fullContent.substring(startIndex, endIndex);
   }

   private getLineNumber(content: string, index: number): number {
       return content.substring(0, index).split('\n').length;
   }

   // =============================================================================
   // Phase 2: Deep Dependency Traversal - Method Call Extraction
   // =============================================================================

   /**
    * Extract method calls from a method body.
    * This enables deep traversal by identifying service-to-service calls.
    */
   extractMethodCalls(methodContent: string): MethodCallInfo[] {
       const calls: MethodCallInfo[] = [];

       // Pattern: variableName.methodName(...) or ClassName.methodName(...)
       const callPattern = /(\w+)\.(\w+)\s*\(/g;
       let match;

       while ((match = callPattern.exec(methodContent)) !== null) {
           const target = match[1];
           const methodName = match[2];

           // Skip common non-service calls
           if (this.isCommonUtilCall(target, methodName)) continue;

           calls.push({
               targetVariable: target,
               targetMethod: methodName,
               lineNumber: this.getLineNumber(methodContent, match.index),
               isServiceCall: this.isServiceCall(target),
               isDAOCall: this.isDAOCall(target, methodName),
               isValidatorCall: this.isValidatorCall(target, methodName),
           });
       }

       return calls;
   }

   /**
    * Extract all injected dependencies from a class.
    */
   extractInjectedDependencies(classContent: string): InjectedDependency[] {
       const dependencies: InjectedDependency[] = [];

       // Pattern: @Autowired followed by field declaration
       const autowiredPattern = /@Autowired[^;]*?\s+(?:private|protected|public)?\s*(\w+(?:<[^>]+>)?)\s+(\w+)\s*;/g;
       let match;

       while ((match = autowiredPattern.exec(classContent)) !== null) {
           dependencies.push({
               type: match[1],
               fieldName: match[2],
               isService: match[1].toLowerCase().includes('service'),
               isDAO: match[1].toLowerCase().includes('dao') || match[1].toLowerCase().includes('repository'),
               isValidator: match[1].toLowerCase().includes('validator'),
           });
       }

       // Pattern: Constructor injection
       const constructorPattern = /(?:public|protected)\s+\w+\s*\(([^)]+)\)/g;
       while ((match = constructorPattern.exec(classContent)) !== null) {
           const params = match[1].split(',');
           for (const param of params) {
               const parts = param.trim().split(/\s+/);
               if (parts.length >= 2) {
                   const type = parts[parts.length - 2];
                   const name = parts[parts.length - 1];
                   if (type && name && (type.includes('Service') || type.includes('DAO') || type.includes('Repository'))) {
                       dependencies.push({
                           type,
                           fieldName: name,
                           isService: type.toLowerCase().includes('service'),
                           isDAO: type.toLowerCase().includes('dao') || type.toLowerCase().includes('repository'),
                           isValidator: type.toLowerCase().includes('validator'),
                       });
                   }
               }
           }
       }

       return dependencies;
   }

   /**
    * Extract entities used in a method.
    */
   extractEntityUsage(methodContent: string): string[] {
       const entities: Set<string> = new Set();

       // Pattern: new EntityName(...) or EntityName.class or EntityName variable
       const entityPatterns = [
           /new\s+(\w+Entity)\s*\(/g,
           /new\s+(\w+Model)\s*\(/g,
           /(\w+Entity)\.class/g,
           /(\w+Model)\.class/g,
           /List<(\w+Entity)>/g,
           /List<(\w+Model)>/g,
       ];

       for (const pattern of entityPatterns) {
           let match;
           while ((match = pattern.exec(methodContent)) !== null) {
               if (match[1]) entities.add(match[1]);
           }
       }

       return Array.from(entities);
   }

   /**
    * Check if a call is to a common utility (not a service call).
    */
   private isCommonUtilCall(target: string, method: string): boolean {
       const skipTargets = ['this', 'super', 'String', 'Integer', 'Long', 'Boolean', 'Double', 'Float',
           'List', 'ArrayList', 'Set', 'HashSet', 'Map', 'HashMap', 'Optional', 'Stream',
           'Arrays', 'Collections', 'Objects', 'System', 'Math', 'logger', 'log', 'LOG'];
       const skipMethods = ['equals', 'hashCode', 'toString', 'compareTo', 'size', 'length',
           'isEmpty', 'get', 'set', 'add', 'remove', 'contains', 'clear', 'put', 'append', 'valueOf'];

       return skipTargets.includes(target) || skipMethods.includes(method);
   }

   /**
    * Check if target appears to be a service.
    */
   private isServiceCall(target: string): boolean {
       return target.toLowerCase().endsWith('service') ||
              target.toLowerCase().endsWith('action') ||
              target.toLowerCase().endsWith('handler') ||
              target.toLowerCase().endsWith('manager');
   }

   /**
    * Check if this appears to be a DAO/repository call.
    */
   private isDAOCall(target: string, method: string): boolean {
       const daoTargets = ['dao', 'repository', 'repo', 'mapper'];
       const daoMethods = ['find', 'save', 'update', 'delete', 'insert', 'select', 'query', 'get', 'load', 'persist', 'merge'];

       return daoTargets.some(t => target.toLowerCase().includes(t)) ||
              daoMethods.some(m => method.toLowerCase().startsWith(m));
   }

   /**
    * Check if this appears to be a validator call.
    */
   private isValidatorCall(target: string, method: string): boolean {
       const validatorTargets = ['validator', 'validation'];
       const validatorMethods = ['validate', 'check', 'verify', 'assert', 'ensure'];

       return validatorTargets.some(t => target.toLowerCase().includes(t)) ||
              validatorMethods.some(m => method.toLowerCase().startsWith(m));
   }

   // =============================================================================
   // Phase 7: Business Logic Blueprint - Constants & Transaction Extraction
   // =============================================================================

   /**
    * Extract business constants from a Java class.
    * Looks for static final fields, magic numbers, and configurable thresholds.
    */
   extractBusinessConstants(classContent: string, className: string): BusinessConstantExtracted[] {
       const constants: BusinessConstantExtracted[] = [];

       // Pattern: static final TYPE NAME = VALUE;
       const staticFinalPattern = /(?:private|public|protected)?\s*static\s+final\s+(\w+)\s+(\w+)\s*=\s*([^;]+);/g;
       let match;

       while ((match = staticFinalPattern.exec(classContent)) !== null) {
           const type = match[1];
           const name = match[2];
           const valueRaw = match[3]?.trim();

           if (!type || !name || !valueRaw) continue;

           // Skip common non-business constants
           if (this.isNonBusinessConstant(name)) continue;

           const { value, dataType } = this.parseConstantValue(type, valueRaw);

           constants.push({
               name,
               value,
               dataType,
               type,
               className,
               description: this.inferConstantDescription(name),
               lineNumber: this.getLineNumber(classContent, match.index),
               isConfigurable: this.isConfigurableConstant(classContent, name),
           });
       }

       // Look for magic numbers in code (hardcoded values in conditions/calculations)
       const magicNumbers = this.extractMagicNumbers(classContent, className);
       constants.push(...magicNumbers);

       return constants;
   }

   /**
    * Extract @Transactional annotation details.
    */
   extractTransactionInfo(content: string): TransactionInfoExtracted | undefined {
       const transactionalMatch = content.match(/@Transactional\s*(?:\(([^)]*)\))?/);
       if (!transactionalMatch) return undefined;

       const attributes = transactionalMatch[1] || '';

       const propagationMatch = attributes.match(/propagation\s*=\s*Propagation\.(\w+)/);
       const isolationMatch = attributes.match(/isolation\s*=\s*Isolation\.(\w+)/);
       const readOnlyMatch = attributes.match(/readOnly\s*=\s*(true|false)/);
       const timeoutMatch = attributes.match(/timeout\s*=\s*(\d+)/);
       const rollbackForMatch = attributes.match(/rollbackFor\s*=\s*\{?([^}]+)\}?/);
       const noRollbackForMatch = attributes.match(/noRollbackFor\s*=\s*\{?([^}]+)\}?/);
       const managerMatch = attributes.match(/(?:value|transactionManager)\s*=\s*["']([^"']+)["']/);

       return {
           propagation: propagationMatch?.[1] as any || 'REQUIRED',
           isolation: isolationMatch?.[1] as any,
           readOnly: readOnlyMatch?.[1] === 'true',
           timeout: timeoutMatch ? parseInt(timeoutMatch[1], 10) : undefined,
           rollbackFor: rollbackForMatch ? this.parseExceptionList(rollbackForMatch[1]) : undefined,
           noRollbackFor: noRollbackForMatch ? this.parseExceptionList(noRollbackForMatch[1]) : undefined,
           transactionManager: managerMatch?.[1],
       };
   }

   /**
    * Parse exception list from annotation value.
    */
   private parseExceptionList(value: string): string[] {
       return value
           .replace(/\.class/g, '')
           .split(',')
           .map(e => e.trim())
           .filter(e => e.length > 0);
   }

   /**
    * Check if a constant name suggests non-business purpose.
    */
   private isNonBusinessConstant(name: string): boolean {
       const skipPrefixes = ['LOG', 'LOGGER', 'SERIAL_VERSION', 'serialVersionUID'];
       const skipPatterns = [/^LOG$/i, /^LOGGER$/i, /SERIAL/i, /^_/];

       return skipPrefixes.some(p => name.startsWith(p)) ||
              skipPatterns.some(p => p.test(name));
   }

   /**
    * Parse constant value and determine data type.
    */
   private parseConstantValue(javaType: string, rawValue: string): { value: string | number | boolean; dataType: 'string' | 'number' | 'boolean' | 'date' | 'enum' } {
       // Remove trailing L for longs, D for doubles, F for floats
       const cleanValue = rawValue.replace(/[LDFld]$/, '').trim();

       // Boolean
       if (javaType === 'boolean' || javaType === 'Boolean') {
           return { value: cleanValue === 'true', dataType: 'boolean' };
       }

       // Numeric types
       if (['int', 'Integer', 'long', 'Long', 'double', 'Double', 'float', 'Float', 'BigDecimal', 'BigInteger'].includes(javaType)) {
           const numValue = parseFloat(cleanValue);
           return { value: isNaN(numValue) ? cleanValue : numValue, dataType: 'number' };
       }

       // String
       if (javaType === 'String' && cleanValue.startsWith('"') && cleanValue.endsWith('"')) {
           return { value: cleanValue.slice(1, -1), dataType: 'string' };
       }

       // Enum reference
       if (cleanValue.includes('.') && !cleanValue.includes('"')) {
           return { value: cleanValue, dataType: 'enum' };
       }

       return { value: cleanValue, dataType: 'string' };
   }

   /**
    * Infer a description for the constant based on its name.
    */
   private inferConstantDescription(name: string): string {
       // Convert SNAKE_CASE to readable text
       return name
           .toLowerCase()
           .replace(/_/g, ' ')
           .replace(/\b\w/g, c => c.toUpperCase());
   }

   /**
    * Check if a constant is referenced via configuration.
    */
   private isConfigurableConstant(classContent: string, constantName: string): boolean {
       // Check for @Value annotation referencing this constant
       const valueAnnotationPattern = new RegExp(`@Value\\s*\\([^)]*\\$\\{[^}]*${constantName}[^}]*\\}[^)]*\\)`, 'i');
       return valueAnnotationPattern.test(classContent) ||
              classContent.includes(`@ConfigurationProperties`) ||
              classContent.includes(`getProperty("${constantName.toLowerCase()}")`);
   }

   /**
    * Extract magic numbers from code (hardcoded values in conditions).
    */
   private extractMagicNumbers(classContent: string, className: string): BusinessConstantExtracted[] {
       const magicNumbers: BusinessConstantExtracted[] = [];

       // Pattern: comparisons with literal numbers (e.g., if (x > 100), amount >= 50000)
       const comparisonPattern = /(\w+)\s*([<>=!]+)\s*(\d+(?:\.\d+)?)/g;
       let match;

       while ((match = comparisonPattern.exec(classContent)) !== null) {
           const variable = match[1];
           const operator = match[2];
           const value = match[3];

           if (!variable || !value) continue;

           // Skip common non-business values
           const numValue = parseFloat(value);
           if (numValue === 0 || numValue === 1 || numValue === -1) continue;
           if (numValue < 2 || !Number.isFinite(numValue)) continue;

           // Check if this looks like a business threshold
           if (this.isBusinessThreshold(variable, numValue)) {
               const name = `${variable.toUpperCase()}_THRESHOLD_${numValue}`;

               // Check if we already have this constant
               if (magicNumbers.some(c => c.name === name)) continue;

               magicNumbers.push({
                   name,
                   value: numValue,
                   dataType: 'number',
                   type: 'inferred',
                   className,
                   description: `Threshold: ${variable} ${operator} ${value}`,
                   lineNumber: this.getLineNumber(classContent, match.index),
                   isConfigurable: false,
                   isMagicNumber: true,
               });
           }
       }

       return magicNumbers;
   }

   /**
    * Check if a comparison looks like a business threshold.
    */
   private isBusinessThreshold(variable: string, value: number): boolean {
       const businessVariables = ['amount', 'total', 'quantity', 'count', 'size', 'limit', 'max', 'min',
           'threshold', 'days', 'hours', 'minutes', 'age', 'rate', 'percent', 'percentage', 'fee', 'price'];

       const lowerVar = variable.toLowerCase();
       return businessVariables.some(bv => lowerVar.includes(bv)) ||
              value >= 100 || // Likely a business threshold
              (value > 10 && value % 10 === 0); // Round numbers often business rules
   }
}

// Types for business constant extraction
export interface BusinessConstantExtracted {
   name: string;
   value: string | number | boolean;
   dataType: 'string' | 'number' | 'boolean' | 'date' | 'enum';
   type: string; // Java type
   className: string;
   description?: string;
   lineNumber: number;
   isConfigurable: boolean;
   isMagicNumber?: boolean;
}

export interface TransactionInfoExtracted {
   propagation?: 'REQUIRED' | 'REQUIRES_NEW' | 'NESTED' | 'SUPPORTS' | 'NOT_SUPPORTED' | 'MANDATORY' | 'NEVER';
   isolation?: 'DEFAULT' | 'READ_UNCOMMITTED' | 'READ_COMMITTED' | 'REPEATABLE_READ' | 'SERIALIZABLE';
   readOnly?: boolean;
   timeout?: number;
   rollbackFor?: string[];
   noRollbackFor?: string[];
   transactionManager?: string;
}

// Types for method call extraction
export interface MethodCallInfo {
   targetVariable: string;
   targetMethod: string;
   lineNumber: number;
   isServiceCall: boolean;
   isDAOCall: boolean;
   isValidatorCall: boolean;
}

export interface InjectedDependency {
   type: string;
   fieldName: string;
   isService: boolean;
   isDAO: boolean;
   isValidator: boolean;
}