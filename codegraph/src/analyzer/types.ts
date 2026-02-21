// src/analyzer/types.ts
import winston from 'winston'; // Import Logger type
import ts from 'typescript'; // Needed for ts.Node below, ensure typescript is a dependency if not already
import { SourceFile } from 'ts-morph'; // Import ts-morph SourceFile


// --- Core Types ---

/**
 * Represents a structured documentation tag extracted from code comments.
 * Supports JSDoc, Javadoc, Python docstrings, XML docs, Doxygen, and Go doc comments.
 */
export interface DocTag {
    /** Tag name (e.g., "param", "returns", "throws", "deprecated", "example") */
    tag: string;
    /** Name associated with the tag (e.g., parameter name for @param) */
    name?: string;
    /** Type annotation if present (e.g., {string} in JSDoc or type in Javadoc) */
    type?: string;
    /** Description text for the tag */
    description?: string;
}

/**
 * Structured documentation information extracted from code comments.
 */
export interface DocumentationInfo {
    /** Main description/summary text */
    summary: string;
    /** Raw comment text (unprocessed) */
    rawComment?: string;
    /** Structured tags extracted from the comment */
    tags: DocTag[];
    /** Documentation format detected */
    format: 'jsdoc' | 'javadoc' | 'docstring' | 'xmldoc' | 'doxygen' | 'godoc' | 'unknown';
    /** Whether the entity is marked as deprecated */
    isDeprecated?: boolean;
    /** Deprecation message if deprecated */
    deprecationReason?: string;
    /** Example code snippets */
    examples?: string[];
    /** See also references */
    seeAlso?: string[];
    /** Author information */
    authors?: string[];
    /** Version information */
    version?: string;
    /** Since version */
    since?: string;
}

/**
 * Represents a generic node in the Abstract Syntax Tree (AST).
 * This is the base interface extended by language-specific node types.
 */
export interface AstNode {
    id: string;             // Unique instance ID for this node in this specific parse run
    entityId: string;       // Globally unique identifier for the code entity (e.g., file path + function name + line)
    kind: string;           // Type of the node (e.g., 'File', 'Function', 'Class', 'Import')
    name: string;           // Name of the node (e.g., function name, class name, filename)
    type?: string;          // Optional: Type information (e.g., variable type, function return type)
    filePath: string;       // Absolute path to the file containing this node
    startLine: number;      // Starting line number (1-based)
    endLine: number;        // Ending line number (1-based)
    startColumn: number;    // Starting column number (0-based)
    endColumn: number;      // Ending column number (0-based)
    language: string;       // Programming language (e.g., 'TypeScript', 'Python', 'Java')
    loc?: number;           // Lines of code (optional)
    properties?: Record<string, any>; // Additional language-specific properties
    isExported?: boolean;   // Optional: Indicates if the node is exported
    complexity?: number;    // Optional: Cyclomatic complexity or similar metric
    isAbstract?: boolean;   // Optional: Indicates if a class/method is abstract
    isAsync?: boolean;      // Optional: Indicates if a function/method is async
    isOptional?: boolean;   // Optional: Indicates if a parameter/property is optional
    isStatic?: boolean;     // Optional: Indicates if a member is static
    isGenerator?: boolean;  // Optional: Indicates if a function is a generator
    isRestParameter?: boolean; // Optional: Indicates if a parameter is a rest parameter
    isConstant?: boolean;   // Optional: Indicates if a variable is constant
    visibility?: 'public' | 'private' | 'protected' | 'internal' | 'package' | 'default'; // Optional: Visibility modifier
    returnType?: string;    // Optional: Return type of a function/method
    implementsInterfaces?: string[]; // Optional: List of implemented interface names
    modifierFlags?: string[]; // Optional: List of modifier keywords (e.g., 'export', 'async', 'static')
    tags?: DocTag[];        // Optional: Structured documentation tags (e.g., @param, @returns)
    documentation?: string; // Optional: Documentation summary/description string
    docComment?: string;    // Optional: Raw documentation comment
    documentationInfo?: DocumentationInfo; // Optional: Full structured documentation
    parentId?: string;      // Optional entityId of the parent node (e.g., class containing a method)
    createdAt: string;      // ISO timestamp of creation

    // --- Repository Overview Feature: Extended Properties ---
    /** Computed code metrics (complexity, nesting, etc.) */
    metrics?: CodeMetrics;
    /** Whether the entity has meaningful documentation */
    hasDocumentation?: boolean;
    /** Whether the entity is marked as deprecated */
    isDeprecated?: boolean;
    /** Deprecation reason/message */
    deprecationReason?: string;
    /** Stereotype classification for classes (Controller, Service, Repository, etc.) */
    stereotype?: Stereotype;
    /** Detected code smells on this entity */
    codeSmells?: CodeSmell[];
    /** Entry point type if this node is an entry point handler */
    entryPointType?: 'rest' | 'graphql' | 'event' | 'scheduled' | 'cli';
    /** Associated entry point entityId */
    entryPointId?: string;
}


/**
 * Represents a relationship between two AstNode objects.
 */
export interface RelationshipInfo {
    id: string;             // Unique instance ID for this relationship in this specific parse run
    entityId: string;       // Globally unique identifier for the relationship instance
    type: string;           // Type of the relationship (e.g., 'CALLS', 'IMPORTS', 'EXTENDS')
    sourceId: string;       // entityId of the source node
    targetId: string;       // entityId of the target node
    properties?: Record<string, any>; // Additional properties for the relationship
    weight?: number;        // Optional weight for ranking or analysis
    createdAt: string;      // ISO timestamp of creation
}

/**
 * Represents the result of parsing a single file.
 */
export interface SingleFileParseResult {
    filePath: string;
    nodes: AstNode[];
    relationships: RelationshipInfo[];
}

/**
 * Helper type for generating unique instance IDs during a parse run.
 */
export interface InstanceCounter {
    count: number;
}


/**
 * Context for multi-repository analysis.
 * Contains repository metadata passed from the backend to scope all nodes under a Repository.
 */
export interface AnalysisContext {
    /** UUID from backend identifying the repository */
    repositoryId: string;
    /** Display name of the repository */
    repositoryName: string;
    /** Optional URL of the repository (e.g., GitHub URL) */
    repositoryUrl?: string;
    /** Root directory being analyzed */
    rootDirectory: string;
}

/**
 * Context object passed to parser functions.
 */
export interface ParserContext {
    filePath: string;
    sourceFile: SourceFile; // Use ts-morph SourceFile
    fileNode: FileNode; // Reference to the FileNode being processed
    result: SingleFileParseResult; // The accumulating result for the current file
    addNode: (node: AstNode) => void;
    addRelationship: (rel: RelationshipInfo) => void;
    generateId: (prefix: string, identifier: string, options?: { line?: number; column?: number }) => string;
    generateEntityId: (kind: string, qualifiedName: string) => string;
    logger: winston.Logger;
    resolveImportPath: (sourcePath: string, importPath: string) => string;
    now: string;
    // Add any other properties needed during parsing
}


/**
 * Represents the resolved information about a target declaration, used in Pass 2.
 */
export interface TargetDeclarationInfo {
    name: string;
    kind: string; // e.g., 'Function', 'Class', 'Variable', 'Interface', 'Method', 'Parameter'
    filePath: string; // Absolute, normalized path
    entityId: string; // Globally unique ID matching Pass 1 generation
}

/**
 * Context object passed to relationship resolver functions.
 */
export interface ResolverContext {
    nodeIndex: Map<string, AstNode>;
    addRelationship: (rel: RelationshipInfo) => void;
    generateId: (prefix: string, identifier: string, options?: { line?: number; column?: number }) => string;
    generateEntityId: (kind: string, qualifiedName: string) => string;
    logger: winston.Logger;
    resolveImportPath: (sourcePath: string, importPath: string) => string;
    now: string;
}


// --- Language Agnostic Node Kinds (Examples) ---

export interface FileNode extends AstNode {
    kind: 'File';
    loc: number; // Lines of code for the file
}

/**
 * Represents a Repository node - root node for multi-repository support.
 */
export interface RepositoryNode extends AstNode {
    kind: 'Repository';
    properties: {
        /** UUID from backend */
        repositoryId: string;
        /** Display name of the repository */
        name: string;
        /** Optional URL of the repository */
        url?: string;
        /** Local path where repository is stored */
        rootPath: string;
        /** Timestamp when analysis was performed */
        analyzedAt: string;
        /** Number of files in the repository */
        fileCount: number;
    };
}

// --- Component Node (e.g., for React/Vue/Svelte) ---
export interface ComponentNode extends AstNode {
    kind: 'Component';
    properties?: {
        isExported?: boolean;
        isDefaultExport?: boolean;
    } & Record<string, any>; // Allow other properties
}



// --- JSX Specific Nodes ---

export interface JSXElementNode extends AstNode {
    kind: 'JSXElement';
    properties: {
        tagName: string;
        isSelfClosing: boolean;
    } & Record<string, any>;
}

export interface JSXAttributeNode extends AstNode {
    kind: 'JSXAttribute';
    parentId: string; // entityId of the parent JSXElement
    properties: {
        value?: string | boolean | object; // Attribute value can be complex
    } & Record<string, any>;
}

// --- Tailwind Specific Node (Example) ---
// This might be better represented as a property or relationship
// depending on how you want to model Tailwind usage.
export interface TailwindClassNode extends AstNode {
    kind: 'TailwindClass';
    parentId: string; // entityId of the node using the class (e.g., JSXElement)
    properties: {
        className: string;
    } & Record<string, any>;
}


// --- C/C++ Specific Nodes ---

export interface IncludeDirectiveNode extends AstNode {
    kind: 'IncludeDirective';
    properties: {
        includePath: string;
        isSystemInclude: boolean;
    };
}

export interface MacroDefinitionNode extends AstNode {
    kind: 'MacroDefinition';
    properties: {
        value?: string; // Value might be optional or complex
    };
}

export interface CFunctionNode extends AstNode {
    kind: 'CFunction';
    language: 'C' | 'C++'; // Can be in C or C++ files
    parentId?: string; // Optional link to struct/namespace entityId if applicable
    /** Complete signature information */
    signatureInfo?: MethodSignature;
}

export interface CppClassNode extends AstNode {
    kind: 'CppClass';
    language: 'C++';
    properties?: {
        // TODO: Add base classes, template parameters
    } & Record<string, any>;
}

export interface CppMethodNode extends AstNode {
    kind: 'CppMethod';
    language: 'C++';
    parentId: string; // Link to containing class entityId
    /** Complete signature information */
    signatureInfo?: MethodSignature;
}

// --- Java Specific Nodes ---

export interface PackageDeclarationNode extends AstNode {
    kind: 'PackageDeclaration';
}

export interface ImportDeclarationNode extends AstNode {
    kind: 'ImportDeclaration';
    properties: {
        importPath: string;
        onDemand: boolean; // For wildcard imports like java.util.*
    };
}

export interface JavaClassNode extends AstNode {
    kind: 'JavaClass';
    language: 'Java';
    properties: {
        qualifiedName: string;
        // TODO: Add modifiers, superclass, interfaces
    };
}

export interface JavaInterfaceNode extends AstNode {
    kind: 'JavaInterface';
    language: 'Java';
    properties: {
        qualifiedName: string;
        // TODO: Add modifiers, extends list
    };
}

export interface JavaMethodNode extends AstNode {
    kind: 'JavaMethod';
    language: 'Java';
    parentId?: string;
    /** Complete signature information */
    signatureInfo?: MethodSignature;
    // Enhanced properties for BRD generation
    /** Code snippet from method body (5-15 lines) */
    codeSnippet?: string;
    /** Line range of the code snippet */
    codeSnippetLines?: { start: number; end: number };
    /** Error messages extracted from throw statements */
    errorMessages?: string[];
    /** Security annotations (@PreAuthorize, @Secured, etc.) */
    securityAnnotations?: AnnotationInfo[];
}

export interface JavaFieldNode extends AstNode {
    kind: 'JavaField';
    language: 'Java';
    parentId?: string;
    fieldType?: string;
    visibility?: 'public' | 'private' | 'protected' | 'package';
    isStatic?: boolean;
}

export interface JavaEnumNode extends AstNode {
    kind: 'JavaEnum';
    language: 'Java';
    properties: {
        qualifiedName: string;
        // TODO: Add implements list, enum constants
    };
}

/**
 * Represents a security rule/constraint on a method or class.
 * Extracted from @PreAuthorize, @PostAuthorize, @Secured, @RolesAllowed, etc.
 */
export interface SecurityRuleNode extends AstNode {
    kind: 'SecurityRule';
    language: 'Java';
    /** Method or Class entityId this rule applies to */
    parentId: string;
    properties: {
        /** Security annotation type */
        annotationType: 'PreAuthorize' | 'PostAuthorize' | 'Secured' | 'RolesAllowed' | 'PermitAll' | 'DenyAll' | 'RunAs';
        /** Full annotation text */
        annotationText: string;
        /** SpEL expression for @PreAuthorize/@PostAuthorize */
        expression?: string;
        /** Required roles extracted from annotation */
        roles?: string[];
        /** Target type */
        targetType: 'method' | 'class';
        /** Human-readable description */
        ruleDescription: string;
        /** Confidence score */
        confidence: number;
    };
}

/**
 * Represents an error message key and its resolved text.
 * Used to link message keys in code to actual message text from .properties files.
 */
export interface ErrorMessageNode extends AstNode {
    kind: 'ErrorMessage';
    language: 'Properties';
    properties: {
        /** Message key like "poi.notfound" */
        messageKey: string;
        /** Resolved message text */
        messageText: string;
        /** Properties file this came from */
        sourceFile: string;
        /** Locale if applicable */
        locale?: string;
        /** Parameters in the message (e.g., {0}, {1}) */
        parameters?: string[];
    };
}


// --- Go Specific Nodes ---

export interface PackageClauseNode extends AstNode {
    kind: 'PackageClause';
    language: 'Go';
}

export interface ImportSpecNode extends AstNode {
    kind: 'ImportSpec';
    language: 'Go';
    properties: {
        importPath: string;
        alias?: string;
    };
}

export interface GoFunctionNode extends AstNode {
    kind: 'GoFunction';
    language: 'Go';
    properties: {
        qualifiedName: string;
    };
    /** Complete signature information */
    signatureInfo?: MethodSignature;
}

export interface GoMethodNode extends AstNode {
    kind: 'GoMethod';
    language: 'Go';
    parentId?: string; // Link to receiver type entityId
    properties: {
        receiverType: string;
    };
    /** Complete signature information */
    signatureInfo?: MethodSignature;
}

export interface GoStructNode extends AstNode {
    kind: 'GoStruct';
    language: 'Go';
    properties: {
        qualifiedName: string;
        // TODO: Add fields
    };
}

export interface GoInterfaceNode extends AstNode {
    kind: 'GoInterface';
    language: 'Go';
    properties: {
        qualifiedName: string;
        // TODO: Add methods
    };
}

export interface TypeAlias extends AstNode { // For Go type aliases
    kind: 'TypeAlias';
    language: 'Go';
    properties: {
        qualifiedName: string;
        aliasedType: string; // Store the underlying type as string for now
    };
}



// --- C# Specific Nodes ---

export interface NamespaceDeclarationNode extends AstNode {
    kind: 'NamespaceDeclaration';
    language: 'C#';
}

export interface UsingDirectiveNode extends AstNode {
    kind: 'UsingDirective';
    language: 'C#';
    properties: {
        namespaceOrType: string;
        isStatic: boolean;
        alias?: string;
    };
}

export interface CSharpClassNode extends AstNode {
    kind: 'CSharpClass';
    language: 'C#';
    properties: {
        qualifiedName: string;
        // TODO: Add modifiers, base list
    };
}

export interface CSharpInterfaceNode extends AstNode {
    kind: 'CSharpInterface';
    language: 'C#';
    properties: {
        qualifiedName: string;
        // TODO: Add modifiers, base list
    };
}

export interface CSharpStructNode extends AstNode {
    kind: 'CSharpStruct';
    language: 'C#';
    properties: {
        qualifiedName: string;
        // TODO: Add modifiers, base list
    };
}

export interface CSharpMethodNode extends AstNode {
    kind: 'CSharpMethod';
    language: 'C#';
    parentId?: string; // Link to containing class/struct/interface entityId
    /** Complete signature information */
    signatureInfo?: MethodSignature;
}

export interface PropertyNode extends AstNode { // For C# Properties
    kind: 'Property';
    language: 'C#';
    parentId?: string; // Link to containing class/struct/interface entityId
    // TODO: Add type, modifiers, accessors
}

export interface FieldNode extends AstNode { // For C# Fields
    kind: 'Field';
    language: 'C#';
    parentId?: string; // Link to containing class/struct/interface entityId
    // TODO: Add type, modifiers
}

// --- SQL Specific Nodes ---

export interface SQLTableNode extends AstNode {
    kind: 'SQLTable';
    language: 'SQL';
    properties: {
        qualifiedName: string;
        schema?: string | null;
    };
}

export interface SQLColumnNode extends AstNode {
    kind: 'SQLColumn';
    language: 'SQL';
    parentId: string; // entityId of the parent table
    properties: {
        dataType: string;
        // TODO: Add constraints (PK, FK, NULL, UNIQUE, DEFAULT)
    };
}

export interface SQLViewNode extends AstNode {
    kind: 'SQLView';
    language: 'SQL';
    properties: {
        qualifiedName: string;
        schema?: string | null;
        queryText: string; // Store the underlying query
    };
}

// Base type for different SQL statement kinds
export interface SQLStatementNode extends AstNode {
    kind: 'SQLSelectStatement' | 'SQLInsertStatement' | 'SQLUpdateStatement' | 'SQLDeleteStatement'; // Add other DML/DDL types as needed
    language: 'SQL';
    properties: {
        queryText: string; // Store the full statement text
    };
}


// --- Python Specific Nodes ---
// (Add Python-specific interfaces here if needed, e.g., PythonFunction, PythonClass)

// --- TypeScript/JavaScript Specific Nodes ---
// (Add TS/JS-specific interfaces here if needed)
export interface TSFunction extends AstNode {
    kind: 'TSFunction';
    properties?: {
        isExported?: boolean;
        isDefaultExport?: boolean;
        isAsync?: boolean;
    } & Record<string, any>;
}

// Add these new interfaces to the existing types.ts file

// --- JSP Specific Nodes ---

export interface JSPPageNode extends AstNode {
    kind: 'JSPPage';
    language: 'JSP';
    properties: {
        servletPath: string;
        hasForm: boolean;
        formActions: string[];
        includes: string[];
        taglibs: TagLibrary[];
        elExpressions: string[];
        hasScriptlets: boolean;
        encoding?: string;
        contentType?: string;
    };
}

export interface JSPFormNode extends AstNode {
    kind: 'JSPForm';
    language: 'JSP';
    parentId: string; // JSP page entityId
    properties: {
        action: string;
        method: 'GET' | 'POST';
        enctype?: string;
        fields: FormField[];
        submitElements: SubmitElement[];
    };
}

export interface JSPIncludeNode extends AstNode {
    kind: 'JSPInclude';
    language: 'JSP';
    parentId: string; // JSP page entityId
    properties: {
        includePath: string;
        includeType: 'directive' | 'action';
        isStatic: boolean;
    };
}

export interface JSPTagLibNode extends AstNode {
    kind: 'JSPTagLib';
    language: 'JSP';
    parentId: string; // JSP page entityId
    properties: {
        uri: string;
        prefix: string;
        usedTags: string[];
    };
}

// --- Spring Web Flow Nodes ---

export interface WebFlowDefinitionNode extends AstNode {
    kind: 'WebFlowDefinition';
    language: 'SpringWebFlow';
    properties: {
        flowId: string;
        startState: string;
        endStates: string[];
        flowVariables: FlowVariable[];
        securityAttributes?: string[];
        parentFlow?: string;
    };
}

export interface FlowStateNode extends AstNode {
    kind: 'FlowState';
    language: 'SpringWebFlow';
    parentId: string; // Flow definition entityId
    properties: {
        stateId: string;
        stateType: 'view-state' | 'action-state' | 'decision-state' | 'end-state' | 'subflow-state';
        view?: string;
        viewScope?: FlowVariable[];
        onEntry?: ActionReference[];
        onExit?: ActionReference[];
        secured?: boolean;
    };
}

/**
 * Parsed condition metadata from WebFlow transition.
 * Provides structured information about transition guards.
 */
export interface TransitionConditionMetadata {
    /** Original condition expression */
    expression: string;
    /** Parsed operator */
    operator?: 'equals' | 'notEquals' | 'greaterThan' | 'lessThan' | 'greaterThanOrEquals' | 'lessThanOrEquals' | 'and' | 'or' | 'not' | 'contains' | 'matches' | 'custom';
    /** Left operand (usually a variable or method call) */
    leftOperand?: string;
    /** Right operand (value being compared) */
    rightOperand?: string;
    /** Variables referenced in condition */
    variables: string[];
    /** Methods called in condition */
    methodCalls: string[];
    /** Whether this is a SpEL expression */
    isSpEL: boolean;
    /** Human-readable description */
    description?: string;
}

export interface FlowTransitionNode extends AstNode {
    kind: 'FlowTransition';
    language: 'SpringWebFlow';
    parentId: string; // Source state entityId
    properties: {
        event: string;
        fromStateId: string;
        toStateId: string;
        condition?: string;
        /** Parsed condition metadata for BRD generation */
        conditionMetadata?: TransitionConditionMetadata;
        executeBefore?: ActionReference[];
        executeAfter?: ActionReference[];
    };
}

export interface FlowActionNode extends AstNode {
    kind: 'FlowAction';
    language: 'SpringWebFlow';
    parentId: string; // Flow or state entityId
    properties: {
        actionName: string;
        beanMethod?: string;
        expression?: string;
        actionType: 'evaluate' | 'set' | 'bean-method';
        resultScope?: 'request' | 'flash' | 'view' | 'flow' | 'conversation' | 'application';
    };
}

// --- Enhanced Java Nodes ---

export interface SpringControllerNode extends AstNode {
    kind: 'SpringController';
    language: 'Java';
    properties: {
        qualifiedName: string;
        requestMappings: RequestMapping[];
        isFlowController: boolean;
        sessionAttributes?: string[];
        controllerAdvice?: boolean;
    };
}

export interface FlowActionMethodNode extends AstNode {
    kind: 'FlowActionMethod';
    language: 'Java';
    parentId?: string;
    properties: {
        flowBindings: string[];
        flowParameters: FlowParameter[];
        flowReturnType?: string;
        canThrowFlowException: boolean;
    };
}

export interface SpringServiceNode extends AstNode {
    kind: 'SpringService';
    language: 'Java';
    properties: {
        qualifiedName: string;
        serviceType: 'service' | 'repository' | 'component';
        transactional: boolean;
        qualifier?: string;
        /** Transaction boundary details */
        transactionInfo?: TransactionBoundaryInfo;
    };
}

// --- Business Logic Blueprint Nodes ---

/**
 * Represents a data table extracted from JSP
 */
export interface DataTableNode extends AstNode {
    kind: 'DataTable';
    language: 'JSP';
    parentId: string; // Parent JSP page entityId
    properties: DataTableInfo;
}

/**
 * Represents a business constant extracted from code
 */
export interface BusinessConstantNode extends AstNode {
    kind: 'BusinessConstant';
    language: 'Java';
    parentId?: string; // Parent class entityId
    properties: BusinessConstantInfo;
}

/**
 * Represents a screen with mode information
 */
export interface ScreenModeNode extends AstNode {
    kind: 'ScreenMode';
    language: 'SpringWebFlow';
    parentId: string; // Parent Screen/FlowState entityId
    properties: {
        /** Screen modes available */
        modes: ScreenModeInfo[];
        /** How mode is determined */
        modeSource: 'url-param' | 'flow-variable' | 'request-param' | 'conditional';
        /** Mode parameter name */
        modeParameter?: string;
        /** Default mode */
        defaultMode?: string;
    };
}

/**
 * Represents a feature with full business logic context
 * Used for Blueprint generation
 */
export interface FeatureBlueprintNode extends AstNode {
    kind: 'FeatureBlueprint';
    language: 'Application';
    properties: {
        /** Feature name from menu */
        featureName: string;
        /** Menu path (e.g., "Point > Point Maintenance") */
        menuPath: string[];
        /** Flow/screen count */
        screenCount: number;
        /** Total field count */
        fieldCount: number;
        /** Total validation count */
        validationCount: number;
        /** Total action count */
        actionCount: number;
        /** Security roles that can access */
        accessRoles: string[];
        /** Confidence level of extraction */
        confidence: 'high' | 'medium' | 'low';
        /** Sections with missing data */
        missingData?: string[];
    };
}

// --- Supporting Types ---

export interface TagLibrary {
    uri: string;
    prefix: string;
    location?: string;
}

export interface FormField {
    name: string;
    type: string;
    required: boolean;
    defaultValue?: string;
    // Enhanced properties for BRD generation
    /** Extracted label text from <label> tags or adjacent elements */
    label?: string;
    /** i18n message key like "selectedGroup.groupName" from <fmt:message> */
    labelKey?: string;
    /** HTML5 placeholder attribute */
    placeholder?: string;
    /** Help text from title attribute or adjacent help elements */
    helpText?: string;
    /** Path from <form:errors path="..."> */
    errorPath?: string;
    /** HTML5 and Spring validation attributes */
    validationRules?: {
        pattern?: string;
        min?: string | number;
        max?: string | number;
        minLength?: number;
        maxLength?: number;
        step?: number;
    };
    /** CSS classes for styling detection */
    cssClasses?: string[];
    /** Error CSS class from cssErrorClass attribute */
    cssErrorClass?: string;
    // Business Logic Blueprint enhancements
    /** Options for select/dropdown fields */
    selectOptions?: SelectOption[];
    /** Data source for dynamic options (e.g., service call, enum) */
    dataSource?: DataSourceInfo;
    /** Whether field is read-only */
    readOnly?: boolean;
    /** Whether field is disabled */
    disabled?: boolean;
    /** Conditional visibility expression */
    visibilityCondition?: string;
    /** Conditional editability expression */
    editabilityCondition?: string;
    /** Cross-field dependencies (fields that affect this field) */
    dependsOnFields?: string[];
    /** Fields that this field affects */
    affectsFields?: string[];
}

/**
 * Represents an option in a select/dropdown field
 */
export interface SelectOption {
    /** The value submitted with the form */
    value: string;
    /** The display label shown to users */
    label: string;
    /** i18n message key for the label */
    labelKey?: string;
    /** Whether this is the default selected option */
    isDefault?: boolean;
    /** Whether this option is disabled */
    disabled?: boolean;
    /** Parent value for cascading dropdowns */
    parentValue?: string;
}

/**
 * Represents the data source for dynamic field options
 */
export interface DataSourceInfo {
    /** Type of data source */
    type: 'static' | 'enum' | 'service' | 'database' | 'items-attribute';
    /** Service/bean name if type is 'service' */
    serviceName?: string;
    /** Method name if type is 'service' */
    methodName?: string;
    /** Enum class name if type is 'enum' */
    enumClass?: string;
    /** Items attribute path (e.g., "${itemList}") */
    itemsPath?: string;
    /** Item value property (e.g., "id") */
    itemValue?: string;
    /** Item label property (e.g., "name") */
    itemLabel?: string;
}

/**
 * Represents a column in a data table/grid
 */
export interface TableColumnInfo {
    /** Column header text */
    header: string;
    /** i18n key for header */
    headerKey?: string;
    /** Property/field path for data binding */
    dataField?: string;
    /** Column data type */
    dataType?: 'text' | 'number' | 'date' | 'boolean' | 'currency' | 'link' | 'action';
    /** Whether column is sortable */
    sortable?: boolean;
    /** Whether column is filterable */
    filterable?: boolean;
    /** Whether column is hidden */
    hidden?: boolean;
    /** Column width */
    width?: string;
    /** Display format (e.g., date format) */
    format?: string;
    /** Link URL pattern if type is 'link' */
    linkPattern?: string;
    /** Action buttons if type is 'action' */
    actions?: TableActionInfo[];
}

/**
 * Represents an action button in a table row
 */
export interface TableActionInfo {
    /** Action name/type */
    name: string;
    /** Display label */
    label: string;
    /** Icon name */
    icon?: string;
    /** Event triggered */
    event?: string;
    /** URL pattern */
    urlPattern?: string;
    /** Confirmation message before action */
    confirmMessage?: string;
    /** Visibility condition */
    visibilityCondition?: string;
}

/**
 * Represents a data table/grid in a screen
 */
export interface DataTableInfo {
    /** Table identifier */
    id: string;
    /** Data source expression */
    dataSource: string;
    /** Column definitions */
    columns: TableColumnInfo[];
    /** Whether table supports pagination */
    paginated?: boolean;
    /** Default page size */
    pageSize?: number;
    /** Whether table supports selection */
    selectable?: boolean;
    /** Selection mode */
    selectionMode?: 'single' | 'multiple';
    /** Whether table supports inline editing */
    inlineEditable?: boolean;
    /** Row click action */
    rowClickAction?: string;
    /** Bulk actions available */
    bulkActions?: TableActionInfo[];
}

/**
 * Represents screen mode information (Create/Edit/View)
 */
export interface ScreenModeInfo {
    /** Mode identifier */
    mode: 'create' | 'edit' | 'view' | 'clone' | 'approve' | 'delete';
    /** How the mode is determined (URL param, flow variable, etc.) */
    determinedBy: 'url-param' | 'flow-variable' | 'request-param' | 'model-attribute';
    /** Parameter/variable name */
    parameterName?: string;
    /** Expected value for this mode */
    parameterValue?: string;
    /** Fields visible in this mode */
    visibleFields?: string[];
    /** Fields editable in this mode */
    editableFields?: string[];
    /** Fields hidden in this mode */
    hiddenFields?: string[];
    /** Fields required in this mode */
    requiredFields?: string[];
    /** Actions available in this mode */
    availableActions?: string[];
}

/**
 * Represents transaction boundary information
 */
export interface TransactionBoundaryInfo {
    /** Transaction propagation */
    propagation?: 'REQUIRED' | 'REQUIRES_NEW' | 'NESTED' | 'SUPPORTS' | 'NOT_SUPPORTED' | 'MANDATORY' | 'NEVER';
    /** Transaction isolation level */
    isolation?: 'DEFAULT' | 'READ_UNCOMMITTED' | 'READ_COMMITTED' | 'REPEATABLE_READ' | 'SERIALIZABLE';
    /** Read-only flag */
    readOnly?: boolean;
    /** Timeout in seconds */
    timeout?: number;
    /** Rollback for exceptions */
    rollbackFor?: string[];
    /** No rollback for exceptions */
    noRollbackFor?: string[];
    /** Transaction manager name */
    transactionManager?: string;
}

/**
 * Represents a business constant/magic number
 */
export interface BusinessConstantInfo {
    /** Constant name */
    name: string;
    /** Constant value */
    value: string | number | boolean;
    /** Data type */
    type: 'string' | 'number' | 'boolean' | 'date' | 'enum';
    /** Business meaning/purpose */
    description?: string;
    /** Where it's used (class.method references) */
    usedIn?: string[];
    /** Whether it's configurable (from properties file) */
    configurable?: boolean;
    /** Configuration key if configurable */
    configKey?: string;
    /** Source location */
    sourceFile?: string;
    /** Line number */
    lineNumber?: number;
}

export interface SubmitElement {
    type: 'submit' | 'button' | 'image';
    name?: string;
    value?: string;
}

export interface FlowVariable {
    name: string;
    type?: string;
    value?: string;
    scope: 'request' | 'flash' | 'view' | 'flow' | 'conversation' | 'application';
}

export interface ActionReference {
    bean?: string;
    method?: string;
    expression?: string;
}

export interface RequestMapping {
    path: string;
    method: string[];
    params?: string[];
    headers?: string[];
    consumes?: string[];
    produces?: string[];
}

export interface FlowParameter {
    name: string;
    type: string;
    required: boolean;
    scope?: string;
}

// Add new relationship types
// Add these new relationship types to your existing types.ts file
export const JSP_SPRING_RELATIONSHIPS = [
    'SUBMITS_TO_FLOW',        // JSP Form -> Web Flow
    'INCLUDES_JSP',           // JSP -> JSP
    'FORWARDS_TO_JSP',        // JSP -> JSP
    'REDIRECTS_TO_JSP',       // JSP -> JSP
    'USES_TAGLIB',           // JSP -> TagLib
    'CONTAINS_FORM',         // JSP -> JSP Form
    'FLOW_RENDERS_VIEW',     // Flow State -> JSP
    'FLOW_EXECUTES_ACTION',  // Flow State -> Flow Action
    'FLOW_TRANSITIONS_TO',   // Flow State -> Flow State
    'CONTROLLER_HANDLES_FLOW', // Spring Controller -> Web Flow
    'ACTION_CALLS_SERVICE',  // Flow Action -> Service Method
    'FLOW_USES_MODEL',       // Flow -> Model Class
    'STATE_HAS_TRANSITION',  // Flow State -> Flow Transition
    'FLOW_DEFINES_STATE',    // Web Flow -> Flow State
    'ACTION_EVALUATES_EXPRESSION', // Flow Action -> Expression/Bean Method
    'VIEW_BINDS_MODEL',      // JSP -> Model Object
] as const;

// --- Relationship Types (Examples - can be language-specific) ---
// CALLS, IMPORTS, EXTENDS, IMPLEMENTS, DEFINES_FUNCTION, DEFINES_CLASS, HAS_METHOD, HAS_FIELD, etc.


// =============================================================================
// Method/Function Signature Support
// =============================================================================

/**
 * Represents a parameter in a method/function signature.
 * Used for storing detailed parameter information inline.
 */
export interface ParameterInfo {
    /** Parameter name */
    name: string;
    /** Parameter type (language-specific format) */
    type: string;
    /** Default value if any */
    defaultValue?: string;
    /** Whether the parameter is optional (TypeScript ?, Java @Nullable, etc.) */
    isOptional: boolean;
    /** Whether this is a rest/varargs parameter (TypeScript ...args, Java String..., Go ...string) */
    isVariadic: boolean;
    /** Whether the parameter is passed by reference (C++ &, C# ref/out) */
    isByReference?: boolean;
    /** Reference modifier (C# ref, out, in) */
    referenceModifier?: 'ref' | 'out' | 'in';
    /** Annotations/attributes on the parameter */
    annotations?: AnnotationInfo[];
    /** Position in parameter list (0-based) */
    position: number;
}

/**
 * Represents an annotation/attribute on a method, parameter, or class.
 */
export interface AnnotationInfo {
    /** Annotation name (e.g., @Override, @NotNull, [Authorize]) */
    name: string;
    /** Annotation arguments if any */
    arguments?: Record<string, string | number | boolean>;
    /** Full annotation text */
    text: string;
}

/**
 * Represents a type parameter for generics/templates.
 */
export interface TypeParameterInfo {
    /** Type parameter name (e.g., T, K, V) */
    name: string;
    /** Constraint/bound (e.g., extends Comparable<T>, : IComparable) */
    constraint?: string;
    /** Variance (in/out for C#, covariant/contravariant) */
    variance?: 'in' | 'out' | 'invariant';
    /** Default type if any */
    defaultType?: string;
}

/**
 * Comprehensive method/function signature information.
 * This is the main interface for storing signature metadata.
 */
export interface MethodSignature {
    /**
     * Human-readable signature string for display and search.
     * Format varies by language:
     * - Java: "public String getUserById(Long id) throws UserNotFoundException"
     * - TypeScript: "async getUserById(id: number): Promise<User>"
     * - Go: "func (r *UserRepo) GetUserById(id int64) (*User, error)"
     * - C#: "public async Task<User> GetUserById(long id)"
     * - C++: "virtual User* getUserById(long id) const override"
     */
    signature: string;

    /**
     * Short signature for compact display (name + params only).
     * Example: "getUserById(Long, boolean)"
     */
    shortSignature: string;

    /** Return type as string */
    returnType: string;

    /** Whether the method returns void/nothing */
    returnsVoid: boolean;

    /** For languages with multiple returns (Go), array of return types */
    returnTypes?: string[];

    /** Whether the return type is nullable */
    isReturnNullable?: boolean;

    /** Detailed parameter information */
    parameters: ParameterInfo[];

    /** Parameter count for quick filtering */
    parameterCount: number;

    /** Type parameters for generics */
    typeParameters?: TypeParameterInfo[];

    /** Visibility modifier */
    visibility: 'public' | 'private' | 'protected' | 'internal' | 'package' | 'default';

    /** All modifiers as array (for search and filtering) */
    modifiers: string[];

    /** Whether the method is static */
    isStatic: boolean;

    /** Whether the method is async/coroutine */
    isAsync: boolean;

    /** Whether the method is abstract */
    isAbstract: boolean;

    /** Whether the method is final/sealed */
    isFinal: boolean;

    /** Whether the method is virtual (C++, C#) */
    isVirtual?: boolean;

    /** Whether the method is override */
    isOverride?: boolean;

    /** Whether the method is const (C++) */
    isConst?: boolean;

    /** Whether the method is a constructor */
    isConstructor: boolean;

    /** Whether the method is a destructor (C++) */
    isDestructor?: boolean;

    /** Whether the method is a getter */
    isGetter?: boolean;

    /** Whether the method is a setter */
    isSetter?: boolean;

    /** Thrown exceptions (Java throws, C# /// <exception>) */
    throwsExceptions?: string[];

    /** Annotations/decorators on the method */
    annotations?: AnnotationInfo[];

    /** Receiver type for Go methods */
    receiverType?: string;

    /** Whether receiver is pointer (Go) */
    isPointerReceiver?: boolean;
}

/**
 * Helper to generate a signature string from MethodSignature.
 */
export function generateSignatureString(
    language: string,
    name: string,
    sig: Partial<MethodSignature>
): string {
    const params = sig.parameters || [];
    const paramStr = params.map(p => {
        if (language === 'Java' || language === 'C#' || language === 'C' || language === 'C++') {
            return `${p.type} ${p.name}${p.isVariadic ? '...' : ''}`;
        } else if (language === 'TypeScript' || language === 'JavaScript') {
            return `${p.name}${p.isOptional ? '?' : ''}: ${p.type}`;
        } else if (language === 'Go') {
            return `${p.name} ${p.type}`;
        } else if (language === 'Python') {
            return p.type && p.type !== 'any' ? `${p.name}: ${p.type}` : p.name;
        }
        return `${p.name}: ${p.type}`;
    }).join(', ');

    const modifiers: string[] = [];
    if (sig.visibility && sig.visibility !== 'default') modifiers.push(sig.visibility);
    if (sig.isStatic) modifiers.push('static');
    if (sig.isAbstract) modifiers.push('abstract');
    if (sig.isFinal) modifiers.push('final');
    if (sig.isVirtual) modifiers.push('virtual');
    if (sig.isAsync) modifiers.push('async');
    if (sig.isConst) modifiers.push('const');
    if (sig.isOverride) modifiers.push('override');

    const modifierStr = modifiers.length > 0 ? modifiers.join(' ') + ' ' : '';
    const returnType = sig.returnType || 'void';
    const throwsStr = sig.throwsExceptions?.length
        ? ` throws ${sig.throwsExceptions.join(', ')}`
        : '';

    switch (language) {
        case 'Java':
            return `${modifierStr}${returnType} ${name}(${paramStr})${throwsStr}`;
        case 'C#':
            return `${modifierStr}${returnType} ${name}(${paramStr})`;
        case 'TypeScript':
        case 'JavaScript':
            return `${sig.isAsync ? 'async ' : ''}${name}(${paramStr}): ${returnType}`;
        case 'Go':
            if (sig.receiverType) {
                const ptr = sig.isPointerReceiver ? '*' : '';
                return `func (r ${ptr}${sig.receiverType}) ${name}(${paramStr}) ${returnType}`;
            }
            return `func ${name}(${paramStr}) ${returnType}`;
        case 'C':
        case 'C++':
            const constStr = sig.isConst ? ' const' : '';
            const overrideStr = sig.isOverride ? ' override' : '';
            return `${modifierStr}${returnType} ${name}(${paramStr})${constStr}${overrideStr}`;
        case 'Python':
            const asyncStr = sig.isAsync ? 'async ' : '';
            const retStr = sig.returnType && sig.returnType !== 'None' ? ` -> ${sig.returnType}` : '';
            return `${asyncStr}def ${name}(${paramStr})${retStr}`;
        default:
            return `${name}(${paramStr}): ${returnType}`;
    }
}

/**
 * Generate a short signature (name + parameter types only).
 */
export function generateShortSignature(name: string, params: ParameterInfo[]): string {
    const typeList = params.map(p => p.type).join(', ');
    return `${name}(${typeList})`;
}


// =============================================================================
// Gradle/Maven Multi-Module Support
// =============================================================================

/**
 * Represents a Java module (Gradle subproject or Maven module).
 */
export interface JavaModuleNode extends AstNode {
    kind: 'JavaModule';
    language: 'Java';
    properties: {
        /** Module name from settings.gradle include() */
        moduleName: string;
        /** Path to module directory relative to repository root */
        modulePath: string;
        /** Path to build file (build.gradle or pom.xml) */
        buildFilePath: string;
        /** Build system type */
        buildSystem: 'gradle' | 'maven';
        /** Group ID (from build.gradle or pom.xml) */
        group?: string;
        /** Artifact ID / project name */
        artifact?: string;
        /** Version */
        version?: string;
        /** Applied plugins */
        plugins: string[];
        /** Source directories */
        sourceDirs: string[];
        /** Test directories */
        testDirs: string[];
        /** Resource directories */
        resourceDirs: string[];
        /** Module type inferred from plugins/structure */
        moduleType: 'java-library' | 'application' | 'war' | 'ear' | 'spring-boot' | 'unknown';
        /** Description from build file */
        description?: string;
        /** Java/Kotlin source compatibility */
        sourceCompatibility?: string;
        /** Java/Kotlin target compatibility */
        targetCompatibility?: string;
    };
}

/**
 * Represents a Gradle/Maven dependency.
 */
export interface GradleDependencyNode extends AstNode {
    kind: 'GradleDependency';
    language: 'Gradle';
    properties: {
        /** Group ID (e.g., org.springframework.boot) */
        group: string;
        /** Artifact ID (e.g., spring-boot-starter-web) */
        artifact: string;
        /** Version (can include variables like $springBootVersion) */
        version: string;
        /** Resolved version if variable was used */
        resolvedVersion?: string;
        /** Configuration/scope (implementation, api, compileOnly, testImplementation, etc.) */
        configuration: string;
        /** Whether this is a project dependency (implementation project(':module-name')) */
        isProjectDependency: boolean;
        /** For project dependencies, the referenced module name */
        projectPath?: string;
        /** Whether this is a platform/BOM dependency */
        isPlatform: boolean;
        /** Exclusions applied to this dependency */
        exclusions?: DependencyExclusion[];
        /** Whether version is managed by a platform/BOM */
        isVersionManaged: boolean;
    };
}

/**
 * Represents a Gradle plugin applied to a module.
 */
export interface GradlePluginNode extends AstNode {
    kind: 'GradlePlugin';
    language: 'Gradle';
    properties: {
        /** Plugin ID (e.g., 'java', 'org.springframework.boot') */
        pluginId: string;
        /** Plugin version if specified */
        version?: string;
        /** Whether applied via plugins {} block or apply plugin: */
        appliedVia: 'plugins-block' | 'apply-statement' | 'buildscript';
        /** Whether this is a core Gradle plugin */
        isCore: boolean;
    };
}

/**
 * Dependency exclusion
 */
export interface DependencyExclusion {
    group?: string;
    module?: string;
}

/**
 * Result from parsing Gradle settings file.
 */
export interface GradleSettingsParseResult {
    /** Root project name */
    rootProjectName: string;
    /** List of included module paths */
    includedModules: string[];
    /** Plugin management repositories */
    pluginRepositories: string[];
    /** Dependency management settings */
    dependencyManagement?: {
        defaultVersion?: Record<string, string>;
    };
}

/**
 * Result from parsing a module's build.gradle file.
 */
export interface GradleBuildParseResult {
    /** Module path */
    modulePath: string;
    /** Plugins applied */
    plugins: GradlePluginInfo[];
    /** Dependencies declared */
    dependencies: GradleDependencyInfo[];
    /** Project dependencies (other modules) */
    projectDependencies: ProjectDependencyInfo[];
    /** Ext properties defined */
    extProperties: Record<string, string>;
    /** Source sets configuration */
    sourceSets: SourceSetInfo[];
    /** Group ID */
    group?: string;
    /** Version */
    version?: string;
    /** Java source compatibility */
    sourceCompatibility?: string;
    /** Java target compatibility */
    targetCompatibility?: string;
    /** Repositories */
    repositories: string[];
}

/**
 * Plugin info from build.gradle
 */
export interface GradlePluginInfo {
    id: string;
    version?: string;
    appliedVia: 'plugins-block' | 'apply-statement' | 'buildscript';
}

/**
 * Dependency info from build.gradle
 */
export interface GradleDependencyInfo {
    group: string;
    artifact: string;
    version: string;
    configuration: string;
    isProjectDependency: boolean;
    projectPath?: string;
    isPlatform: boolean;
    exclusions?: DependencyExclusion[];
}

/**
 * Project dependency info (inter-module dependency)
 */
export interface ProjectDependencyInfo {
    /** Configuration (implementation, api, etc.) */
    configuration: string;
    /** Project path (e.g., ':ple-model') */
    projectPath: string;
    /** Normalized module name (e.g., 'ple-model') */
    moduleName: string;
}

/**
 * Source set configuration
 */
export interface SourceSetInfo {
    name: string;
    srcDirs: string[];
    resourceDirs: string[];
    outputDir?: string;
}

/**
 * Complete multi-module project structure.
 */
export interface MultiModuleProjectStructure {
    /** Root project name */
    rootProjectName: string;
    /** Repository ID */
    repositoryId: string;
    /** Root directory path */
    rootPath: string;
    /** Build system detected */
    buildSystem: 'gradle' | 'maven' | 'unknown';
    /** All discovered modules */
    modules: ModuleInfo[];
    /** Module dependency graph (moduleName -> dependencies) */
    moduleDependencyGraph: Map<string, string[]>;
}

/**
 * Information about a single module.
 */
export interface ModuleInfo {
    /** Module name (from include statement) */
    name: string;
    /** Relative path to module directory */
    path: string;
    /** Absolute path to module directory */
    absolutePath: string;
    /** Build file path */
    buildFilePath: string;
    /** Parsed build result */
    buildResult?: GradleBuildParseResult;
    /** Detected module type */
    moduleType: 'java-library' | 'application' | 'war' | 'ear' | 'spring-boot' | 'unknown';
    /** Dependencies on other modules */
    moduleDependencies: string[];
}

/**
 * Module-aware file info extending standard file info.
 */
export interface ModuleAwareFileInfo {
    /** Absolute file path */
    filePath: string;
    /** Relative path from repository root */
    relativePath: string;
    /** Module this file belongs to (null for root-level files) */
    moduleName: string | null;
    /** Module path */
    modulePath: string | null;
    /** Whether file is in src/main, src/test, or other */
    sourceType: 'main' | 'test' | 'resource' | 'other';
}

/**
 * Relationship types for multi-module support.
 */
export const MODULE_RELATIONSHIPS = [
    'HAS_MODULE',              // Repository -> JavaModule
    'DEPENDS_ON_MODULE',       // JavaModule -> JavaModule
    'CONTAINS_FILE',           // JavaModule -> File
    'HAS_DEPENDENCY',          // JavaModule -> GradleDependency
    'APPLIES_PLUGIN',          // JavaModule -> GradlePlugin
    'PARENT_MODULE',           // JavaModule -> JavaModule (for nested modules)
    'DEFINED_IN_MODULE',       // Class/Interface -> JavaModule
] as const;


// =============================================================================
// Repository Overview Feature - New Types
// =============================================================================

// --- Code Metrics ---

/**
 * Code metrics computed for functions, methods, and classes.
 * Used for complexity analysis and hotspot detection.
 */
export interface CodeMetrics {
    /** Traditional cyclomatic complexity (decision points + 1) */
    cyclomaticComplexity: number;
    /** Cognitive complexity (accounts for nesting and flow breaks) */
    cognitiveComplexity: number;
    /** Maximum nesting depth of control structures */
    nestingDepth: number;
    /** Lines of code (excluding comments and blank lines) */
    loc: number;
    /** Number of parameters (for functions/methods) */
    parameterCount: number;
    /** Halstead metrics (optional, for detailed analysis) */
    halstead?: {
        vocabulary: number;
        length: number;
        difficulty: number;
        effort: number;
        bugs: number;
    };
}

// --- Stereotype Classification ---

/**
 * Stereotype classifications for classes/modules.
 * Based on architectural patterns and naming conventions.
 */
export type Stereotype =
    | 'Controller'      // Handles HTTP requests (@Controller, @RestController)
    | 'Service'         // Business logic layer (@Service)
    | 'Repository'      // Data access layer (@Repository, DAO)
    | 'Entity'          // Domain/data model (@Entity, JPA entities)
    | 'DTO'             // Data transfer object (*DTO, *Request, *Response)
    | 'Configuration'   // Configuration class (@Configuration)
    | 'Utility'         // Static helper class (*Utils, *Helper)
    | 'Factory'         // Factory pattern implementation
    | 'Builder'         // Builder pattern implementation
    | 'Middleware'      // Express/NestJS middleware
    | 'Guard'           // NestJS guards, Spring interceptors
    | 'Filter'          // Exception filters, servlet filters
    | 'Validator'       // Validation classes
    | 'Mapper'          // Object mappers (*Mapper)
    | 'Client'          // External service clients (*Client, *Api)
    | 'Handler'         // Event/message handlers
    | 'Provider'        // Dependency providers
    | 'Module'          // NestJS/Angular modules
    | 'Unknown';        // Unclassified

// --- Framework Detection ---

/**
 * Supported framework categories.
 */
export type FrameworkCategory = 'backend' | 'frontend' | 'testing' | 'build' | 'database' | 'messaging';

/**
 * Information about a detected framework.
 */
export interface DetectedFramework {
    /** Framework name (e.g., 'Spring Boot', 'FastAPI', 'React') */
    name: string;
    /** Framework category */
    category: FrameworkCategory;
    /** Detected version if available */
    version?: string;
    /** Confidence score (0-1) */
    confidence: number;
    /** How the framework was detected */
    detectedBy: 'package-file' | 'import' | 'annotation' | 'pattern';
    /** Evidence that led to detection */
    evidence: string[];
}

/**
 * Repository-level framework detection result.
 */
export interface FrameworkDetectionResult {
    /** All detected frameworks */
    frameworks: DetectedFramework[];
    /** Primary backend framework (if any) */
    primaryBackend?: DetectedFramework;
    /** Primary frontend framework (if any) */
    primaryFrontend?: DetectedFramework;
    /** Testing frameworks detected */
    testingFrameworks: DetectedFramework[];
}

// --- Code Smell Detection ---

/**
 * Code smell severity levels.
 */
export type CodeSmellSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';

/**
 * Code smell categories.
 */
export type CodeSmellCategory =
    | 'complexity'      // Complexity-related smells
    | 'size'            // Size-related smells (long method, large class)
    | 'coupling'        // High coupling, dependencies
    | 'naming'          // Naming convention violations
    | 'duplication'     // Code duplication
    | 'architecture'    // Architectural smells (circular deps)
    | 'maintainability' // General maintainability issues
    | 'performance';    // Potential performance issues

/**
 * Detected code smell.
 */
export interface CodeSmell {
    /** Smell type identifier */
    type: string;
    /** Human-readable name */
    name: string;
    /** Detailed description */
    description: string;
    /** Severity level */
    severity: CodeSmellSeverity;
    /** Category */
    category: CodeSmellCategory;
    /** Suggested fix */
    suggestion?: string;
    /** Metric value that triggered the smell (if applicable) */
    metricValue?: number;
    /** Threshold that was exceeded */
    threshold?: number;
}

/**
 * Common code smell types.
 */
export const CODE_SMELL_TYPES = {
    // Method-level smells
    LONG_METHOD: 'long-method',
    TOO_MANY_PARAMETERS: 'too-many-parameters',
    DEEPLY_NESTED: 'deeply-nested',
    COMPLEX_METHOD: 'complex-method',
    HIGH_COGNITIVE_COMPLEXITY: 'high-cognitive-complexity',

    // Class-level smells
    LARGE_CLASS: 'large-class',
    GOD_CLASS: 'god-class',
    DATA_CLASS: 'data-class',
    FEATURE_ENVY: 'feature-envy',

    // Architecture smells
    CIRCULAR_DEPENDENCY: 'circular-dependency',
    DEAD_CODE: 'dead-code',
    INCONSISTENT_NAMING: 'inconsistent-naming',
    MISSING_DOCUMENTATION: 'missing-documentation',

    // Coupling smells
    TIGHT_COUPLING: 'tight-coupling',
    EXCESSIVE_IMPORTS: 'excessive-imports',
} as const;

// --- Entry Point Node Types ---

/**
 * HTTP method types for REST endpoints.
 */
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS' | 'TRACE';

// =============================================================================
// UI Routing Types (Phase 1: UI Entry Points)
// =============================================================================

/**
 * Supported UI routing frameworks.
 */
export type UIRoutingFramework =
    | 'react-router'
    | 'next-js'
    | 'vue-router'
    | 'angular-router'
    | 'svelte-kit'
    | 'nuxt'
    | 'remix'
    | 'unknown';

/**
 * Route guard information for protected routes.
 */
export interface RouteGuard {
    /** Guard name/type */
    name: string;
    /** Guard type: auth, role, permission, custom */
    type: 'auth' | 'role' | 'permission' | 'custom';
    /** Required roles if role-based */
    roles?: string[];
    /** Required permissions if permission-based */
    permissions?: string[];
}

/**
 * Represents a UI route defined in code (React Router, Vue Router, Angular).
 * These are routes defined programmatically via router configuration.
 */
export interface UIRouteNode extends AstNode {
    kind: 'UIRoute';
    properties: {
        /** Route path pattern (e.g., '/users/:id') */
        path: string;
        /** Full resolved path including parent routes */
        fullPath: string;
        /** Path parameters extracted from the path */
        pathParameters: string[];
        /** Component entityId that renders this route */
        componentId?: string;
        /** Component name */
        componentName?: string;
        /** Layout component name if applicable */
        layoutName?: string;
        /** Route guards/middleware */
        guards?: RouteGuard[];
        /** Whether the route requires authentication */
        requiresAuth?: boolean;
        /** Framework that defines this route */
        framework: UIRoutingFramework;
        /** Whether this is an index/default route */
        isIndex: boolean;
        /** Whether the route has dynamic segments */
        isDynamic: boolean;
        /** Whether the route is lazily loaded */
        isLazy: boolean;
        /** Parent route entityId for nested routes */
        parentRouteId?: string;
        /** Child route entityIds */
        childRouteIds?: string[];
        /** Query parameters expected */
        queryParameters?: string[];
        /** API endpoints called from this route's component */
        apiEndpointIds?: string[];
    };
}

/**
 * Represents a UI page from file-based routing (Next.js, Nuxt, SvelteKit, Remix).
 * These are pages where the route is inferred from the file system structure.
 */
export interface UIPageNode extends AstNode {
    kind: 'UIPage';
    properties: {
        /** Inferred route path from file location */
        routePath: string;
        /** Path segments (e.g., ['app', 'users', '[id]']) */
        segments: string[];
        /** Whether this is a layout component */
        isLayout: boolean;
        /** Whether this is a loading state component */
        isLoading: boolean;
        /** Whether this is an error boundary component */
        isError: boolean;
        /** Whether this is a not-found page */
        isNotFound: boolean;
        /** Router type for the framework */
        routerType: 'app-router' | 'pages-router' | 'nuxt-pages' | 'svelte-routes' | 'remix-routes';
        /** Framework */
        framework: UIRoutingFramework;
        /** Whether this is a server component (Next.js App Router) */
        isServerComponent?: boolean;
        /** Whether this is a client component */
        isClientComponent?: boolean;
        /** Data fetching methods present */
        dataFetching?: string[];
        /** API methods if this is an API route */
        apiMethods?: HttpMethod[];
        /** Whether the page is dynamic */
        isDynamic: boolean;
        /** Dynamic segment names */
        dynamicSegments?: string[];
        /** Whether this is a catch-all route */
        isCatchAll: boolean;
        /** Whether this is an optional catch-all route */
        isOptionalCatchAll: boolean;
        /** Metadata/SEO exports */
        hasMetadata?: boolean;
        /** Parent layout entityId */
        parentLayoutId?: string;
        /** API endpoints called from this page */
        apiEndpointIds?: string[];
    };
}

/**
 * Represents a REST API endpoint.
 */
export interface RestEndpointNode extends AstNode {
    kind: 'RestEndpoint';
    properties: {
        /** HTTP method (GET, POST, etc.) */
        httpMethod: HttpMethod;
        /** URL path pattern (e.g., '/api/users/{id}') */
        path: string;
        /** Full URL path including base path */
        fullPath: string;
        /** Path parameters extracted from the path */
        pathParameters: string[];
        /** Query parameters expected */
        queryParameters?: ParameterInfo[];
        /** Request body type */
        requestBodyType?: string;
        /** Response type */
        responseType?: string;
        /** HTTP status codes returned */
        statusCodes?: number[];
        /** Content types consumed */
        consumes?: string[];
        /** Content types produced */
        produces?: string[];
        /** Framework that defines this endpoint */
        framework: string;
        /** Security requirements (if any) */
        security?: string[];
        /** Associated controller/handler class entityId */
        handlerClassId?: string;
        /** Associated method entityId */
        handlerMethodId: string;
        /** API documentation summary */
        apiDocSummary?: string;
    };
}

/**
 * GraphQL operation types.
 */
export type GraphQLOperationType = 'Query' | 'Mutation' | 'Subscription';

/**
 * Represents a GraphQL operation (Query, Mutation, or Subscription).
 */
export interface GraphQLOperationNode extends AstNode {
    kind: 'GraphQLOperation';
    properties: {
        /** Operation type */
        operationType: GraphQLOperationType;
        /** Operation name */
        operationName: string;
        /** Input arguments */
        arguments: ParameterInfo[];
        /** Return type */
        returnType: string;
        /** Whether return type is nullable */
        isNullable: boolean;
        /** Whether return type is a list */
        isList: boolean;
        /** Framework (Apollo, type-graphql, Spring GraphQL, etc.) */
        framework: string;
        /** Associated resolver class entityId */
        resolverClassId?: string;
        /** Associated resolver method entityId */
        resolverMethodId: string;
        /** Schema definition location (if external) */
        schemaLocation?: string;
    };
}

/**
 * Represents an event handler (message queue consumer, event listener).
 */
export interface EventHandlerNode extends AstNode {
    kind: 'EventHandler';
    properties: {
        /** Event type/name being handled */
        eventType: string;
        /** Event source (Kafka, RabbitMQ, Redis, EventEmitter, etc.) */
        eventSource: string;
        /** Topic/queue/channel name */
        channelName?: string;
        /** Consumer group (for Kafka) */
        consumerGroup?: string;
        /** Whether handler is async */
        isAsync: boolean;
        /** Framework */
        framework: string;
        /** Associated handler class entityId */
        handlerClassId?: string;
        /** Associated handler method entityId */
        handlerMethodId: string;
        /** Message/payload type */
        payloadType?: string;
        /** Error handling strategy */
        errorHandling?: 'retry' | 'dlq' | 'ignore' | 'custom';
    };
}

/**
 * Represents a scheduled task (cron job, fixed-rate task).
 */
export interface ScheduledTaskNode extends AstNode {
    kind: 'ScheduledTask';
    properties: {
        /** Schedule type */
        scheduleType: 'cron' | 'fixedRate' | 'fixedDelay' | 'interval';
        /** Cron expression (if cron type) */
        cronExpression?: string;
        /** Fixed rate in milliseconds */
        fixedRate?: number;
        /** Fixed delay in milliseconds */
        fixedDelay?: number;
        /** Initial delay before first execution */
        initialDelay?: number;
        /** Timezone (for cron) */
        timezone?: string;
        /** Framework */
        framework: string;
        /** Associated task class entityId */
        taskClassId?: string;
        /** Associated task method entityId */
        taskMethodId: string;
        /** Whether task is enabled/active */
        isEnabled: boolean;
        /** Task description */
        taskDescription?: string;
    };
}

/**
 * Represents a CLI command entry point.
 */
export interface CLICommandNode extends AstNode {
    kind: 'CLICommand';
    properties: {
        /** Command name (e.g., 'generate', 'migrate') */
        commandName: string;
        /** Command aliases */
        aliases?: string[];
        /** Command description */
        description?: string;
        /** Command arguments */
        arguments: ParameterInfo[];
        /** Command options/flags */
        options?: CLIOption[];
        /** Framework (Click, Commander, Cobra, argparse, etc.) */
        framework: string;
        /** Associated handler class entityId */
        handlerClassId?: string;
        /** Associated handler method entityId */
        handlerMethodId: string;
        /** Parent command (for subcommands) */
        parentCommand?: string;
        /** Whether this is a subcommand */
        isSubcommand: boolean;
    };
}

/**
 * CLI option/flag definition.
 */
export interface CLIOption {
    /** Option name (long form) */
    name: string;
    /** Short form (e.g., '-v' for '--verbose') */
    shortName?: string;
    /** Option type */
    type: string;
    /** Description */
    description?: string;
    /** Default value */
    defaultValue?: string;
    /** Whether option is required */
    isRequired: boolean;
    /** Whether option accepts multiple values */
    isMultiple: boolean;
}

// --- Test Detection ---

/**
 * Supported test frameworks.
 */
export type TestFramework =
    | 'JUnit'       // Java
    | 'JUnit5'      // Java
    | 'TestNG'      // Java
    | 'Jest'        // JavaScript/TypeScript
    | 'Mocha'       // JavaScript/TypeScript
    | 'Vitest'      // JavaScript/TypeScript
    | 'pytest'      // Python
    | 'unittest'    // Python
    | 'Go testing'  // Go
    | 'xUnit'       // C#
    | 'NUnit'       // C#
    | 'MSTest'      // C#
    | 'GoogleTest'  // C++
    | 'Catch2'      // C++
    | 'RSpec'       // Ruby
    | 'Unknown';

/**
 * Represents a test file.
 */
export interface TestFileNode extends AstNode {
    kind: 'TestFile';
    properties: {
        /** Test framework used */
        testFramework: TestFramework;
        /** Number of test cases in the file */
        testCount: number;
        /** Number of test suites/describe blocks */
        testSuiteCount: number;
        /** Source file being tested (if determinable) */
        testedFilePath?: string;
        /** entityId of source file being tested */
        testedFileId?: string;
        /** Test categories/tags */
        testTags?: string[];
        /** Whether file contains integration tests */
        hasIntegrationTests: boolean;
        /** Whether file contains unit tests */
        hasUnitTests: boolean;
        /** Whether file contains e2e tests */
        hasE2ETests: boolean;
        /** Test setup/teardown presence */
        hasSetup: boolean;
        hasTeardown: boolean;
        /** Mocking frameworks detected */
        mockingFrameworks?: string[];
    };
}

/**
 * Represents a single test case within a test file.
 */
export interface TestCaseNode extends AstNode {
    kind: 'TestCase';
    properties: {
        /** Test name/description */
        testName: string;
        /** Parent test suite name (if nested) */
        suiteName?: string;
        /** Test framework */
        testFramework: TestFramework;
        /** Test tags/categories */
        tags?: string[];
        /** Whether test is skipped/disabled */
        isSkipped: boolean;
        /** Whether test is focused (only/fit) */
        isFocused: boolean;
        /** Timeout if specified */
        timeout?: number;
        /** Functions/methods being tested (entityIds) */
        testedEntityIds?: string[];
    };
}

// --- Extended AstNode Properties ---

/**
 * Extended properties to be added to AstNode.
 * These can be added via optional properties on AstNode or through
 * the properties bag.
 */
export interface ExtendedNodeProperties {
    /** Computed code metrics */
    metrics?: CodeMetrics;
    /** Whether the entity has meaningful documentation */
    hasDocumentation?: boolean;
    /** Whether the entity is deprecated */
    isDeprecated?: boolean;
    /** Deprecation message */
    deprecationReason?: string;
    /** Stereotype classification for classes */
    stereotype?: Stereotype;
    /** Detected code smells */
    codeSmells?: CodeSmell[];
    /** Entry point type (if this node is an entry point handler) */
    entryPointType?: 'rest' | 'graphql' | 'event' | 'scheduled' | 'cli';
    /** Associated entry point entityId */
    entryPointId?: string;
}

// --- Entry Point Relationship Types ---

/**
 * Relationship types for entry points and testing.
 */
export const ENTRY_POINT_RELATIONSHIPS = [
    'EXPOSES_ENDPOINT',    // Class/Method -> RestEndpoint
    'RESOLVES_OPERATION',  // Class/Method -> GraphQLOperation
    'HANDLES_EVENT',       // Class/Method -> EventHandler
    'SCHEDULED_BY',        // Method -> ScheduledTask
    'INVOKED_BY_CLI',      // Method -> CLICommand
    'TESTS',               // TestFile/TestCase -> Function/Class
    'MOCKS',               // TestFile -> Dependency (mocked)
    'COVERS',              // TestCase -> Function (coverage relationship)
] as const;

// --- Repository Overview API Types ---

/**
 * Module statistics for repository overview.
 */
export interface ModuleStats {
    /** Module name */
    name: string;
    /** Module path */
    path: string;
    /** Number of files */
    fileCount: number;
    /** Number of functions/methods */
    functionCount: number;
    /** Number of classes */
    classCount: number;
    /** Total lines of code */
    totalLoc: number;
    /** Average complexity */
    avgComplexity: number;
    /** Max complexity */
    maxComplexity: number;
    /** Documentation coverage (0-1) */
    docCoverage: number;
    /** Test coverage estimate (0-1) */
    testCoverage: number;
    /** Number of code smells */
    smellCount: number;
    /** Dependencies on other modules */
    dependencies: string[];
    /** Modules that depend on this one */
    dependents: string[];
}

/**
 * Complexity hotspot information.
 */
export interface ComplexityHotspot {
    /** Entity ID */
    entityId: string;
    /** Entity name */
    name: string;
    /** File path */
    filePath: string;
    /** Line number */
    line: number;
    /** Entity kind (Function, Method, Class) */
    kind: string;
    /** Cyclomatic complexity */
    cyclomaticComplexity: number;
    /** Cognitive complexity */
    cognitiveComplexity: number;
    /** Lines of code */
    loc: number;
    /** Why this is a hotspot */
    reason: string;
}

/**
 * Entry point summary for API surface analysis.
 */
export interface EntryPointSummary {
    /** Total REST endpoints */
    restEndpointCount: number;
    /** REST endpoints by HTTP method */
    restByMethod: Record<HttpMethod, number>;
    /** Total GraphQL operations */
    graphqlOperationCount: number;
    /** GraphQL by operation type */
    graphqlByType: Record<GraphQLOperationType, number>;
    /** Total event handlers */
    eventHandlerCount: number;
    /** Event handlers by source */
    eventsBySource: Record<string, number>;
    /** Total scheduled tasks */
    scheduledTaskCount: number;
    /** Total CLI commands */
    cliCommandCount: number;
    // UI Entry Points (Phase 1)
    /** Total UI routes (programmatic routing) */
    uiRouteCount: number;
    /** Total UI pages (file-based routing) */
    uiPageCount: number;
    /** UI routes/pages by framework */
    uiByFramework: Record<UIRoutingFramework, number>;
    /** Count of routes requiring authentication */
    protectedRouteCount: number;
}

/**
 * Test coverage summary.
 */
export interface TestCoverageSummary {
    /** Total test files */
    testFileCount: number;
    /** Total test cases */
    testCaseCount: number;
    /** Files with tests */
    filesWithTests: number;
    /** Files without tests */
    filesWithoutTests: number;
    /** Functions with tests */
    functionsWithTests: number;
    /** Functions without tests */
    functionsWithoutTests: number;
    /** Test frameworks in use */
    frameworks: TestFramework[];
    /** Untested critical modules */
    untestedCriticalModules: string[];
}

/**
 * Code quality summary.
 */
export interface CodeQualitySummary {
    /** Average cyclomatic complexity */
    avgCyclomaticComplexity: number;
    /** Average cognitive complexity */
    avgCognitiveComplexity: number;
    /** Documentation coverage (0-1) */
    documentationCoverage: number;
    /** Public API documentation coverage */
    publicApiDocCoverage: number;
    /** Complexity hotspots */
    hotspots: ComplexityHotspot[];
    /** Code smells by severity */
    smellsBySeverity: Record<CodeSmellSeverity, number>;
    /** Code smells by category */
    smellsByCategory: Record<CodeSmellCategory, number>;
    /** Total technical debt estimate (in hours) */
    technicalDebtHours?: number;
}

/**
 * Architecture pattern detection result.
 */
export interface ArchitecturePattern {
    /** Pattern name */
    name: string;
    /** Confidence (0-1) */
    confidence: number;
    /** Evidence supporting the pattern */
    evidence: string[];
    /** Layers detected (for layered architecture) */
    layers?: string[];
}

/**
 * "Where to start" recommendation.
 */
export interface StartingPointRecommendation {
    /** Recommendation type */
    type: 'entry-point' | 'core-module' | 'configuration' | 'documentation';
    /** Entity ID */
    entityId: string;
    /** Entity name */
    name: string;
    /** File path */
    filePath: string;
    /** Why this is recommended */
    reason: string;
    /** Priority (1 = highest) */
    priority: number;
}

/**
 * Complete repository overview response.
 */
export interface RepositoryOverview {
    /** Repository ID */
    repositoryId: string;
    /** Repository name */
    repositoryName: string;
    /** Analysis timestamp */
    analyzedAt: string;

    /** Summary statistics */
    summary: {
        totalFiles: number;
        totalFunctions: number;
        totalClasses: number;
        totalLoc: number;
        languages: { language: string; fileCount: number; loc: number }[];
        frameworks: DetectedFramework[];
    };

    /** Module structure */
    modules: ModuleStats[];

    /** Architecture analysis */
    architecture: {
        patterns: ArchitecturePattern[];
        layers?: string[];
        moduleGraph: { source: string; target: string; weight: number }[];
    };

    /** Entry points (API surface) */
    entryPoints: EntryPointSummary;

    /** Code quality metrics */
    codeQuality: CodeQualitySummary;

    /** Test coverage */
    testing: TestCoverageSummary;

    /** Recommendations for new developers */
    recommendations: StartingPointRecommendation[];
}

// =============================================================================
// Phase 2: Feature Discovery Types
// =============================================================================

/**
 * Feature category classification.
 */
export type FeatureCategory = 'user-facing' | 'admin' | 'internal' | 'api-only';

/**
 * Feature complexity level.
 */
export type FeatureComplexity = 'simple' | 'moderate' | 'complex';

/**
 * Represents a discovered end-to-end feature in the application.
 * Features are traced from UI entry points through API endpoints,
 * services, and down to database entities.
 */
export interface FeatureNode extends AstNode {
    kind: 'Feature';
    properties: {
        /** Auto-inferred or user-provided feature name */
        featureName: string;
        /** Feature description */
        description: string;
        /** Feature category */
        category: FeatureCategory;
        /** Confidence score for the auto-inferred name (0-1) */
        confidence: number;
        /** UI entry point entityIds (routes/pages) */
        uiEntryPoints: string[];
        /** API endpoint entityIds */
        apiEndpoints: string[];
        /** Service entityIds involved */
        services: string[];
        /** Database entity/table names */
        databaseEntities: string[];
        /** Feature complexity assessment */
        complexity: FeatureComplexity;
        /** Full trace path from UI to database */
        tracePath: string[];
        /** User override for the feature name */
        userOverrideName?: string;
        /** Tags for categorization */
        tags?: string[];
        /** Related feature entityIds */
        relatedFeatures?: string[];
    };
}

/**
 * Result from feature discovery analysis.
 */
export interface FeatureDiscoveryResult {
    /** Discovered features */
    features: FeatureNode[];
    /** API endpoints not mapped to any feature */
    unmappedEndpoints: string[];
    /** UI routes not mapped to any feature */
    unmappedRoutes: string[];
    /** Statistics about the discovery */
    stats: {
        totalFeatures: number;
        byCategory: Record<FeatureCategory, number>;
        byComplexity: Record<FeatureComplexity, number>;
        coveragePercent: number;
    };
}

// =============================================================================
// Phase 3: Agentic Readiness Types
// =============================================================================

/**
 * Readiness grade from A to F.
 */
export type ReadinessGrade = 'A' | 'B' | 'C' | 'D' | 'F';

/**
 * Testing readiness assessment.
 */
export interface TestingReadiness {
    /** Overall testing grade */
    overallGrade: ReadinessGrade;
    /** Overall testing score (0-100) */
    overallScore: number;
    /** Test coverage metrics */
    coverage: {
        /** Coverage percentage */
        percentage: number;
        /** Grade based on coverage */
        grade: ReadinessGrade;
    };
    /** Critical functions without tests */
    untestedCriticalFunctions: {
        entityId: string;
        name: string;
        filePath: string;
        /** Why this function is critical */
        reason: string;
        /** Stereotype of the containing class */
        stereotype?: Stereotype;
    }[];
    /** Test quality assessment */
    testQuality: {
        hasUnitTests: boolean;
        hasIntegrationTests: boolean;
        hasE2ETests: boolean;
        /** Test frameworks detected */
        frameworks: TestFramework[];
        /** Mocking coverage */
        mockingCoverage?: number;
    };
    /** Recommendations for improving testing */
    recommendations: string[];
}

/**
 * Documentation quality level.
 */
export type DocumentationQuality = 'excellent' | 'good' | 'partial' | 'minimal' | 'none';

/**
 * Documentation readiness assessment.
 */
export interface DocumentationReadiness {
    /** Overall documentation grade */
    overallGrade: ReadinessGrade;
    /** Overall documentation score (0-100) */
    overallScore: number;
    /** Documentation coverage metrics */
    coverage: {
        /** Coverage percentage */
        percentage: number;
        /** Grade based on coverage */
        grade: ReadinessGrade;
    };
    /** Public API documentation coverage */
    publicApiCoverage: {
        /** Coverage percentage */
        percentage: number;
        /** Grade based on coverage */
        grade: ReadinessGrade;
    };
    /** Undocumented public APIs */
    undocumentedPublicApis: {
        entityId: string;
        name: string;
        filePath: string;
        kind: string;
        /** Signature if method/function */
        signature?: string;
    }[];
    /** Distribution of documentation quality */
    qualityDistribution: Record<DocumentationQuality, number>;
    /** Recommendations for improving documentation */
    recommendations: string[];
}

/**
 * Recommendation priority level.
 */
export type RecommendationPriority = 'high' | 'medium' | 'low';

/**
 * Recommendation category.
 */
export type RecommendationCategory = 'testing' | 'documentation';

/**
 * A recommendation for improving agentic readiness.
 */
export interface ReadinessRecommendation {
    /** Priority level */
    priority: RecommendationPriority;
    /** Category */
    category: RecommendationCategory;
    /** Short title */
    title: string;
    /** Detailed description */
    description: string;
    /** Number of entities affected */
    affectedCount: number;
    /** Specific entity IDs affected (limited) */
    affectedEntities?: string[];
    /** Estimated effort to address */
    estimatedEffort?: 'low' | 'medium' | 'high';
}

/**
 * Enrichment action that can be taken.
 */
export interface EnrichmentAction {
    /** Unique action ID */
    id: string;
    /** Action name */
    name: string;
    /** Action description */
    description: string;
    /** Number of entities that would be affected */
    affectedEntities: number;
    /** Category of enrichment */
    category: 'documentation' | 'testing';
    /** Whether the action is automated or requires manual intervention */
    isAutomated: boolean;
}

/**
 * Complete Agentic Readiness Report.
 */
export interface AgenticReadinessReport {
    /** Repository ID */
    repositoryId: string;
    /** Repository name */
    repositoryName: string;
    /** Report generation timestamp */
    generatedAt: string;

    /** Overall readiness grade */
    overallGrade: ReadinessGrade;
    /** Overall readiness score (0-100) */
    overallScore: number;
    /** Whether the repository meets agentic readiness threshold (score >= 75) */
    isAgenticReady: boolean;

    /** Testing readiness assessment */
    testing: TestingReadiness;
    /** Documentation readiness assessment */
    documentation: DocumentationReadiness;

    /** Prioritized recommendations */
    recommendations: ReadinessRecommendation[];

    /** Available enrichment actions */
    enrichmentActions: EnrichmentAction[];

    /** Summary statistics */
    summary: {
        totalEntities: number;
        testedEntities: number;
        documentedEntities: number;
        criticalGaps: number;
    };
}

// =============================================================================
// Phase 4: Codebase Enrichment Types
// =============================================================================

/**
 * Documentation style for generation.
 */
export type DocumentationStyle = 'jsdoc' | 'javadoc' | 'docstring' | 'xmldoc' | 'godoc';

/**
 * Request for documentation enrichment.
 */
export interface DocumentationEnrichmentRequest {
    /** Entity IDs to enrich, or 'all-undocumented' */
    entityIds: string[] | 'all-undocumented';
    /** Documentation style to use */
    style: DocumentationStyle;
    /** Include usage examples */
    includeExamples: boolean;
    /** Include parameter descriptions */
    includeParameters: boolean;
    /** Include return type descriptions */
    includeReturns: boolean;
    /** Include thrown exceptions */
    includeThrows: boolean;
    /** Maximum entities to process (for 'all-undocumented') */
    maxEntities?: number;
}

/**
 * Test type for generation.
 */
export type TestType = 'unit' | 'integration';

/**
 * Request for test enrichment.
 */
export interface TestEnrichmentRequest {
    /** Entity IDs to generate tests for, or 'all-untested' */
    entityIds: string[] | 'all-untested';
    /** Test framework to use */
    framework: string;
    /** Types of tests to generate */
    testTypes: TestType[];
    /** Include mock setup */
    includeMocks: boolean;
    /** Include edge case tests */
    includeEdgeCases: boolean;
    /** Maximum entities to process (for 'all-untested') */
    maxEntities?: number;
}

/**
 * Generated content for a single entity.
 */
export interface GeneratedContent {
    /** Entity ID that was enriched */
    entityId: string;
    /** Entity name */
    entityName: string;
    /** File path for the generated content */
    filePath: string;
    /** Generated content */
    content: string;
    /** Where to insert the content */
    insertPosition: {
        line: number;
        column: number;
    };
    /** Content type */
    contentType: 'documentation' | 'test';
    /** Whether this is a new file or insertion */
    isNewFile: boolean;
}

/**
 * Result from enrichment operation.
 */
export interface EnrichmentResult {
    /** Whether the operation succeeded */
    success: boolean;
    /** Number of entities processed */
    entitiesProcessed: number;
    /** Number of entities enriched */
    entitiesEnriched: number;
    /** Number of entities skipped */
    entitiesSkipped: number;
    /** Generated content for each entity */
    generatedContent: GeneratedContent[];
    /** Errors encountered */
    errors: {
        entityId: string;
        error: string;
    }[];
    /** Enrichment type */
    enrichmentType: 'documentation' | 'testing';
}

// =============================================================================
// UI Route Relationship Types
// =============================================================================

/**
 * Relationship types for UI routes and features.
 */
export const UI_ROUTE_RELATIONSHIPS = [
    'RENDERS_PAGE',        // UIRoute -> Component (route renders a page component)
    'ROUTE_CALLS_API',     // UIRoute/UIPage -> RestEndpoint (route calls an API)
    'ROUTE_USES_SERVICE',  // UIRoute/UIPage -> Service (route uses a service)
    'CHILD_ROUTE',         // UIRoute -> UIRoute (parent-child route relationship)
    'LAYOUT_FOR',          // UIPage -> UIPage (layout wraps page)
    'GUARDS_ROUTE',        // Guard -> UIRoute (guard protects route)
] as const;

/**
 * Relationship types for feature discovery.
 */
export const FEATURE_RELATIONSHIPS = [
    'FEATURE_HAS_UI',      // Feature -> UIRoute/UIPage
    'FEATURE_HAS_API',     // Feature -> RestEndpoint/GraphQLOperation
    'FEATURE_HAS_SERVICE', // Feature -> Service class
    'FEATURE_HAS_DATA',    // Feature -> Entity/Repository
    'RELATED_FEATURE',     // Feature -> Feature
] as const;

// =============================================================================
// Phase 1: Menu & Screen Indexing Types
// =============================================================================

/**
 * Represents a menu item from menu-config.xml or similar navigation configuration.
 * This provides the user-facing navigation structure that maps to code.
 */
export interface MenuItemNode extends AstNode {
    kind: 'MenuItem';
    properties: {
        /** Display label shown in the UI menu */
        label: string;
        /** URL/path this menu item navigates to */
        url: string;
        /** Extracted flow ID from URL (e.g., "pointWizard" from "pointWizard.html") */
        flowId: string;
        /** Extracted view-state ID from URL (e.g., "pointInfoMaintenance" from "?pageSelect=pointInfoMaintenance") */
        viewStateId?: string;
        /** Required roles for accessing this menu item */
        requiredRoles: string[];
        /** Parent menu label for hierarchical navigation */
        parentMenu?: string;
        /** Menu nesting level (1 = top level, 2 = sub-menu, etc.) */
        menuLevel: number;
        /** Whether this is a separator item */
        isSeparator: boolean;
        /** Bean ID in Spring config if applicable */
        beanId?: string;
    };
}

/**
 * Represents the top-level menu hierarchy structure.
 */
export interface MenuHierarchyNode extends AstNode {
    kind: 'MenuHierarchy';
    properties: {
        /** List of top-level menu names */
        topLevelMenus: string[];
        /** Total number of menu items */
        totalItems: number;
        /** Source file for this menu configuration */
        configSource: string;
    };
}

/**
 * Represents a screen/view-state within a WebFlow.
 * Screens are the actual UI pages users interact with.
 */
export interface ScreenNode extends AstNode {
    kind: 'Screen';
    properties: {
        /** Screen identifier (view-state ID) */
        screenId: string;
        /** Display title for the screen */
        title: string;
        /** Parent WebFlow ID */
        flowId: string;
        /** Type of screen based on naming/usage patterns */
        screenType: 'entry' | 'results' | 'inquiry' | 'lookup' | 'wizard' | 'maintenance' | 'search' | 'unknown';
        /** JSP files used by this screen */
        jsps: string[];
        /** Entry JSP for data entry */
        entryJsp?: string;
        /** Results JSP for displaying results */
        resultsJsp?: string;
        /** Header JSP */
        headerJsp?: string;
        /** Footer JSP */
        footerJsp?: string;
        /** Action class that handles this screen */
        actionClass?: string;
        /** Methods called from this screen */
        actionMethods: string[];
        /** Screens this can transition to */
        transitionsTo: string[];
        /** Parent screen ID for inherited screens */
        parentScreenId?: string;
        /** Whether this is a maintenance mode screen */
        isMaintenanceMode: boolean;
        /** URL pattern to access this screen */
        urlPattern?: string;
    };
}

/**
 * Relationship types for menu and screen navigation.
 */
export const MENU_SCREEN_RELATIONSHIPS = [
    'HAS_MENU_ITEM',        // MenuHierarchy -> MenuItem
    'PARENT_MENU_ITEM',     // MenuItem -> MenuItem (nested menus)
    'MENU_OPENS_SCREEN',    // MenuItem -> Screen
    'MENU_OPENS_FLOW',      // MenuItem -> WebFlowDefinition
    'SCREEN_USES_FLOW',     // Screen -> WebFlowDefinition
    'SCREEN_CALLS_ACTION',  // Screen -> JavaClass (action class)
    'SCREEN_RENDERS_JSP',   // Screen -> JSPPage
    'SCREEN_NAVIGATES_TO',  // Screen -> Screen (transitions)
    'SCREEN_INHERITS',      // Screen -> Screen (parent attribute)
] as const;

// =============================================================================
// Phase 2: Deep Dependency Traversal Types
// =============================================================================

/**
 * Represents a method within a service with detailed call information.
 * Used for deep traversal of business logic.
 */
export interface ServiceMethodNode extends AstNode {
    kind: 'ServiceMethod';
    properties: {
        /** Parent class name */
        className: string;
        /** Method name */
        methodName: string;
        /** Return type */
        returnType: string;
        /** Method parameters */
        parameters: Array<{ name: string; type: string }>;
        /** Other services this method calls */
        callsServices: string[];
        /** Specific methods called */
        callsMethods: string[];
        /** Entity classes used */
        usesEntities: string[];
        /** Whether method has @Transactional annotation */
        hasTransaction: boolean;
        /** Access level */
        accessLevel: 'public' | 'protected' | 'private' | 'package';
        /** Whether this is a validation method */
        isValidation: boolean;
        /** Whether this is a DAO/repository method */
        isDataAccess: boolean;
    };
}

/**
 * Relationship types for deep dependency traversal.
 */
export const DEEP_TRAVERSAL_RELATIONSHIPS = [
    'METHOD_CALLS_METHOD',      // ServiceMethod -> ServiceMethod
    'METHOD_USES_ENTITY',       // ServiceMethod -> JavaClass (entity)
    'METHOD_QUERIES_DAO',       // ServiceMethod -> DAO method
    'METHOD_VALIDATES_WITH',    // ServiceMethod -> Validator
    'SERVICE_DELEGATES_TO',     // Service -> Service
    'INJECTS_SERVICE',          // Class -> Service (autowired)
] as const;

// =============================================================================
// Phase 3: Shared Component Detection Types
// =============================================================================

/**
 * Represents a shared utility, helper, or common component.
 */
export interface SharedComponentNode extends AstNode {
    kind: 'SharedComponent';
    properties: {
        /** Type of shared component */
        componentType: 'utility' | 'helper' | 'validator' | 'converter' | 'formatter' | 'constants' | 'base' | 'abstract';
        /** Features that use this component */
        usedByFeatures: string[];
        /** Number of places using this component */
        usageCount: number;
        /** Inferred business domains */
        businessDomains: string[];
        /** Whether this is a cross-cutting concern */
        isCrossCutting: boolean;
    };
}

// =============================================================================
// Phase 4: Business Rule Enrichment Types
// =============================================================================

/**
 * Enhanced business rule with full context linkage.
 */
export interface EnrichedBusinessRuleNode extends AstNode {
    kind: 'EnrichedBusinessRule';
    properties: {
        /** Type of rule */
        ruleType: 'validation' | 'constraint' | 'calculation' | 'workflow' | 'authorization' | 'guard';
        /** Human-readable description */
        ruleDescription: string;
        /** Source method where rule is defined */
        sourceMethod: string;
        /** Source class */
        sourceClass: string;
        /** The actual condition code */
        condition: string;
        /** Associated error message */
        errorMessage?: string;
        /** Entity fields this rule affects */
        affectsFields: string[];
        /** What triggers this rule */
        triggeredBy: string[];
        /** Other rules this depends on */
        dependencies: string[];
        /** Severity level */
        severity: 'error' | 'warning' | 'info';
        /** Feature context linkage */
        featureContext: {
            menuItem?: string;
            screen?: string;
            action?: string;
            subFeature?: string;
        };
        /** Confidence score for auto-detected rules */
        confidence: number;
    };
}

/**
 * Represents a validation chain from UI to database.
 */
export interface ValidationChainNode extends AstNode {
    kind: 'ValidationChain';
    properties: {
        /** Entry point (action method) */
        entryPoint: string;
        /** Validation steps in order */
        validationSteps: Array<{
            order: number;
            type: 'action' | 'service' | 'validator' | 'entity';
            className: string;
            methodName?: string;
            rules: string[];
        }>;
        /** Total number of rules in chain */
        totalRules: number;
        /** Fields validated */
        validatedFields: string[];
    };
}

// =============================================================================
// Phase 5: Cross-Feature Analysis Types
// =============================================================================

/**
 * Represents a cross-feature relationship.
 */
export interface CrossFeatureRelationship {
    /** Source feature/screen */
    sourceFeature: string;
    /** Target feature/screen */
    targetFeature: string;
    /** Type of relationship */
    relationshipType: 'SHARES_ENTITY' | 'SHARES_SERVICE' | 'CASCADES_TO' | 'DEPENDS_ON';
    /** Shared component name */
    sharedComponent?: string;
    /** Implication of this relationship */
    implication: string;
}

/**
 * Relationship types for cross-feature analysis.
 */
export const CROSS_FEATURE_RELATIONSHIPS = [
    'FEATURE_DEPENDS_ON',       // MenuItem -> MenuItem
    'SHARES_ENTITY',            // Screen -> Screen
    'SHARES_SERVICE',           // Screen -> Screen
    'TRIGGERS_VALIDATION_IN',   // Action -> Action
    'CASCADES_TO',              // Entity change cascades
    'FEATURE_AFFECTS',          // Feature -> Feature
] as const;