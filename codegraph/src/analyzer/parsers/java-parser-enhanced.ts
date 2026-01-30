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
}