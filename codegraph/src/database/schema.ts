import { Neo4jClient } from './neo4j-client.js';
import { createContextLogger } from '../utils/logger.js';
import { Neo4jError } from '../utils/errors.js';

const logger = createContextLogger('SchemaManager');

// Define Node Labels used in the graph
export const NODE_LABELS = [
    'Repository', // Root node for multi-repository support
    'IndexState', // Tracks last indexed state per repository for incremental indexing
    'File', 'Directory', 'Class', 'Interface', 'Function', 'Method',
    'Variable', 'Parameter', 'TypeAlias', 'Import', 'Export',
    'Component', 'JSXElement', 'JSXAttribute',
    'TailwindClass',
    'PythonModule', 'PythonFunction', 'PythonClass', 'PythonMethod', 'PythonParameter', 'PythonVariable',
    'CFunction', 'CppClass', 'CppMethod', 'IncludeDirective',
    'MacroDefinition', // Added MacroDefinition
    'JavaClass', 'JavaInterface', 'JavaMethod', 'JavaField', 'PackageDeclaration', 'ImportDeclaration',
    'CSharpClass', 'CSharpInterface', 'CSharpStruct', 'CSharpMethod', 'Property', 'Field', 'NamespaceDeclaration', 'UsingDirective',
    'GoFunction', 'GoMethod', 'GoStruct', 'GoInterface', 'PackageClause', 'ImportSpec',
    // Added SQL labels
    'SQLSchema', 'SQLTable', 'SQLView', 'SQLColumn', 'SQLSelectStatement', 'SQLInsertStatement', 'SQLUpdateStatement', 'SQLDeleteStatement', 'SQLFunction', 'SQLProcedure',
    // Added JSP/Spring labels
    'JSPPage',
    'JSPForm',
    'JSPInclude',
    'JSPTagLib',
    'WebFlowDefinition',
    'FlowState',
    'FlowTransition',
    'FlowAction',
    'SpringController',
    'FlowActionMethod',
    'SpringService',
    // Added Gradle/Maven multi-module support labels
    'JavaModule',           // Represents a Gradle/Maven module (subproject)
    'GradleDependency',     // External dependency from build.gradle
    'MavenDependency',      // External dependency from pom.xml
    'GradlePlugin',         // Gradle plugin applied to a module
    'GradleConfiguration',  // Gradle configuration (implementation, api, testImplementation, etc.)
    // Repository Overview Feature - Entry Point labels
    'RestEndpoint',         // REST API endpoint
    'GraphQLOperation',     // GraphQL Query/Mutation/Subscription
    'EventHandler',         // Message queue consumer, event listener
    'ScheduledTask',        // Cron job, scheduled task
    'CLICommand',           // CLI command entry point
    // Repository Overview Feature - Test labels
    'TestFile',             // Test file
    'TestCase',             // Individual test case
    // UI Entry Points (Phase 1)
    'UIRoute',              // Programmatic UI route (React Router, Vue Router, Angular)
    'UIPage',               // File-based UI page (Next.js, Nuxt, SvelteKit, Remix)
    // Feature Discovery (Phase 2)
    'Feature',              // Discovered end-to-end feature
    // Business Rule Extraction (Phase 3)
    'BusinessRule',         // Generic business rule
    'ValidationConstraint', // Annotation-based validation (@NotNull, @Min, etc.)
    'GuardClause',          // Precondition guard (if (x == null) throw)
    'ConditionalBusinessLogic', // Business conditional logic (if (amount > 50000))
    'TestAssertion',        // Test-derived business rule
    // Menu & Screen Indexing (Phase 1 - Menu Navigation)
    'MenuItem',             // Menu item from menu-config.xml
    'MenuHierarchy',        // Top-level menu structure
    'Screen',               // WebFlow view-state/screen
    // Deep Traversal (Phase 2)
    'ServiceMethod',        // Method with call chain details
    // Shared Components (Phase 3)
    'SharedComponent',      // Utility, helper, common classes
    // Enhanced Business Rules (Phase 4)
    'EnrichedBusinessRule', // Business rule with full context
    'ValidationChain',      // Validation chain from UI to DB
    // Security & Error Messages (Phase 5 - BRD Enhancement)
    'SecurityRule',         // Security constraint from @PreAuthorize, @Secured, etc.
    'ErrorMessage',         // Error message from .properties files
    // Business Logic Blueprint (Phase 6)
    'DataTable',            // Data table/grid from JSP
    'BusinessConstant',     // Magic number/threshold from code
    'ScreenMode',           // Screen mode information (Create/Edit/View)
    'FeatureBlueprint',     // Complete feature blueprint
    'SelectOption',         // Dropdown option from JSP
];

// Define Relationship Types used in the graph
export const RELATIONSHIP_TYPES = [
    'BELONGS_TO',    // File->Repository (for multi-repository support)
    'HAS_INDEX_STATE', // Repository->IndexState (for incremental indexing)
    'CONTAINS',      // Directory->File
    'IMPORTS',       // File->File or File->Module (Placeholder)
    'EXPORTS',       // File->Variable/Function/Class/Interface/TypeAlias
    'CALLS',         // Function/Method->Function/Method
    'EXTENDS',       // Class->Class, Interface->Interface
    'IMPLEMENTS',    // Class->Interface
    'HAS_METHOD',    // Class/Interface->Method
    'HAS_PARAMETER', // Function/Method->Parameter
    'MUTATES_STATE', // Function/Method->Variable/Property
    'HANDLES_ERROR', // TryStatement->CatchClause (or Function/Method)
    'DEFINES_COMPONENT', // File->Component
    'RENDERS_ELEMENT',   // Component/JSXElement -> JSXElement
    'USES_COMPONENT',    // Component -> Component (via JSX tag)
    'HAS_PROP',          // JSXElement -> JSXAttribute
    'USES_TAILWIND_CLASS', // JSXElement -> TailwindClass
    'PYTHON_IMPORTS',          // PythonModule -> PythonModule (placeholder)
    'PYTHON_CALLS',            // PythonFunction/PythonMethod -> Unknown (placeholder)
    'PYTHON_DEFINES_FUNCTION', // PythonModule/PythonClass -> PythonFunction
    'PYTHON_DEFINES_CLASS',    // PythonModule -> PythonClass
    'PYTHON_HAS_METHOD',       // PythonClass -> PythonMethod
    'PYTHON_HAS_PARAMETER',    // PythonFunction/PythonMethod -> PythonParameter
    'INCLUDES',                // C/C++: File -> IncludeDirective (or directly to File in Pass 2)
    'DECLARES_PACKAGE',        // Java: File -> PackageDeclaration
    'JAVA_IMPORTS',            // Java: File -> ImportDeclaration (or Class/Package)
    'HAS_FIELD',               // Java/C#: Class/Interface/Struct -> Field
    'DECLARES_NAMESPACE',      // C#: File -> NamespaceDeclaration
    'USES_NAMESPACE',          // C#: File -> UsingDirective (or Namespace)
    'HAS_PROPERTY',            // C#: Class/Interface/Struct -> Property
    'GO_IMPORTS',              // Go: File -> ImportSpec (or Package)
    // Added SQL relationship types
    'DEFINES_TABLE',           // SQL: Schema/File -> SQLTable
    'DEFINES_VIEW',            // SQL: Schema/File -> SQLView
    'HAS_COLUMN',              // SQL: Table/View -> SQLColumn
    'REFERENCES_TABLE',        // SQL: Statement/View/Function/Procedure -> SQLTable
    'REFERENCES_VIEW',         // SQL: Statement/View/Function/Procedure -> SQLView
    'CALLS_FUNCTION',          // SQL: Statement/Function/Procedure -> SQLFunction
    'CALLS_PROCEDURE',         // SQL: Statement/Function/Procedure -> SQLProcedure
    // Added JSP/Spring relationship types
    'SUBMITS_TO_FLOW',         // JSP Form -> Web Flow
    'INCLUDES_JSP',            // JSP -> JSP
    'FORWARDS_TO_JSP',         // JSP -> JSP
    'REDIRECTS_TO_JSP',        // JSP -> JSP
    'USES_TAGLIB',             // JSP -> TagLib
    'CONTAINS_FORM',           // JSP -> JSP Form
    'FLOW_RENDERS_VIEW',       // Flow State -> JSP
    'FLOW_EXECUTES_ACTION',    // Flow State -> Flow Action
    'FLOW_TRANSITIONS_TO',     // Flow State -> Flow State
    'CONTROLLER_HANDLES_FLOW', // Spring Controller -> Web Flow
    'ACTION_CALLS_SERVICE',    // Flow Action -> Service Method
    'FLOW_USES_MODEL',         // Flow -> Model Class
    'STATE_HAS_TRANSITION',    // Flow State -> Flow Transition
    'FLOW_DEFINES_STATE',      // Web Flow -> Flow State
    'ACTION_EVALUATES_EXPRESSION', // Flow Action -> Expression/Bean Method
    'VIEW_BINDS_MODEL',        // JSP -> Model Object
    // Added Gradle/Maven multi-module relationship types
    'HAS_MODULE',              // Repository -> JavaModule (repository contains module)
    'DEPENDS_ON_MODULE',       // JavaModule -> JavaModule (module dependency from build.gradle)
    'CONTAINS_FILE',           // JavaModule -> File (module contains source file)
    'HAS_DEPENDENCY',          // JavaModule -> GradleDependency/MavenDependency (external dependency)
    'APPLIES_PLUGIN',          // JavaModule -> GradlePlugin (plugin applied to module)
    'PARENT_MODULE',           // JavaModule -> JavaModule (parent-child module relationship)
    'DEFINED_IN_MODULE',       // Class/Interface -> JavaModule (reverse lookup for classes)
    // Repository Overview Feature - Entry Point relationship types
    'EXPOSES_ENDPOINT',        // Class/Method -> RestEndpoint (exposes a REST endpoint)
    'RESOLVES_OPERATION',      // Class/Method -> GraphQLOperation (resolves a GraphQL operation)
    'HANDLES_EVENT',           // Class/Method -> EventHandler (handles an event)
    'SCHEDULED_BY',            // Method -> ScheduledTask (executed by a scheduled task)
    'INVOKED_BY_CLI',          // Method -> CLICommand (invoked by CLI command)
    // Repository Overview Feature - Test relationship types
    'TESTS',                   // TestFile/TestCase -> Function/Class (tests a code unit)
    'MOCKS',                   // TestFile -> Dependency (mocks a dependency)
    'COVERS',                  // TestCase -> Function (covers a function)
    // UI Entry Points (Phase 1) - Route relationship types
    'RENDERS_PAGE',            // UIRoute -> Component (route renders a page component)
    'ROUTE_CALLS_API',         // UIRoute/UIPage -> RestEndpoint (route calls an API)
    'ROUTE_USES_SERVICE',      // UIRoute/UIPage -> Service (route uses a service)
    'CHILD_ROUTE',             // UIRoute -> UIRoute (parent-child route relationship)
    'LAYOUT_FOR',              // UIPage -> UIPage (layout wraps page)
    'GUARDS_ROUTE',            // Guard -> UIRoute (guard protects route)
    // Feature Discovery (Phase 2) - Feature relationship types
    'FEATURE_HAS_UI',          // Feature -> UIRoute/UIPage
    'FEATURE_HAS_API',         // Feature -> RestEndpoint/GraphQLOperation
    'FEATURE_HAS_SERVICE',     // Feature -> Service class
    'FEATURE_HAS_DATA',        // Feature -> Entity/Repository
    'RELATED_FEATURE',         // Feature -> Feature
    // Business Rule Extraction (Phase 3) - Rule relationship types
    'VALIDATES_FIELD',         // ValidationConstraint -> Field/Parameter
    'GUARDS_METHOD',           // GuardClause -> Method
    'ENFORCES_RULE',           // Method/Class -> BusinessRule
    'TESTS_RULE',              // TestAssertion -> BusinessRule
    'DERIVED_FROM',            // BusinessRule -> Source (annotation, if statement, etc.)
    'APPLIES_TO_PARAMETER',    // ValidationConstraint -> Parameter
    'THROWS_ON_VIOLATION',     // GuardClause -> Exception type
    'CONDITIONAL_AFFECTS',     // ConditionalBusinessLogic -> Method/Field
    // Menu & Screen Indexing (Phase 1)
    'HAS_MENU_ITEM',           // MenuHierarchy -> MenuItem
    'PARENT_MENU_ITEM',        // MenuItem -> MenuItem (nested)
    'MENU_OPENS_SCREEN',       // MenuItem -> Screen
    'MENU_OPENS_FLOW',         // MenuItem -> WebFlowDefinition
    'SCREEN_USES_FLOW',        // Screen -> WebFlowDefinition
    'SCREEN_CALLS_ACTION',     // Screen -> JavaClass (action)
    'SCREEN_RENDERS_JSP',      // Screen -> JSPPage
    'SCREEN_NAVIGATES_TO',     // Screen -> Screen
    'SCREEN_INHERITS',         // Screen -> Screen (parent)
    // Deep Traversal (Phase 2)
    'METHOD_CALLS_METHOD',     // ServiceMethod -> ServiceMethod
    'METHOD_USES_ENTITY',      // ServiceMethod -> JavaClass
    'METHOD_QUERIES_DAO',      // ServiceMethod -> DAO method
    'METHOD_VALIDATES_WITH',   // ServiceMethod -> Validator
    'SERVICE_DELEGATES_TO',    // Service -> Service
    'INJECTS_SERVICE',         // Class -> Service (autowired)
    // Cross-Feature Analysis (Phase 5)
    'FEATURE_DEPENDS_ON',      // MenuItem -> MenuItem
    'SHARES_ENTITY',           // Screen -> Screen
    'SHARES_SERVICE',          // Screen -> Screen
    'TRIGGERS_VALIDATION_IN',  // Action -> Action
    'CASCADES_TO',             // Entity cascade
    'FEATURE_AFFECTS',         // Feature -> Feature
    // Security & Error Messages (Phase 6 - BRD Enhancement)
    'SECURED_BY',              // Method/Class -> SecurityRule
    'HAS_ERROR_MESSAGE',       // Method/GuardClause -> ErrorMessage
    'REFERENCES_MESSAGE',      // Code -> ErrorMessage (by key)
    // Business Logic Blueprint (Phase 7)
    'HAS_DATA_TABLE',          // Screen/JSP -> DataTable
    'HAS_TABLE_COLUMN',        // DataTable -> TableColumn (embedded in properties)
    'HAS_SELECT_OPTIONS',      // FormField -> SelectOption
    'OPTIONS_FROM',            // FormField -> Service/Enum (data source)
    'HAS_SCREEN_MODE',         // Screen -> ScreenMode
    'HAS_CONSTANT',            // Class -> BusinessConstant
    'USES_CONSTANT',           // Method -> BusinessConstant
    'HAS_BLUEPRINT',           // MenuItem -> FeatureBlueprint
    'FIELD_DEPENDS_ON',        // FormField -> FormField (cross-field dependency)
    'ACTION_TRIGGERS',         // ScreenAction -> Method
    'HAS_TRANSACTION',         // Method -> TransactionBoundary (embedded)
];

// Define relationship types that can cross file boundaries
const CROSS_FILE_RELATIONSHIP_TYPES = RELATIONSHIP_TYPES
    .filter(type => ['IMPORTS', 'EXPORTS', 'CALLS', 'EXTENDS', 'IMPLEMENTS', 'MUTATES_STATE', 'INCLUDES', 'JAVA_IMPORTS', 'USES_NAMESPACE', 'GO_IMPORTS', 'REFERENCES_TABLE', 'REFERENCES_VIEW', 'CALLS_FUNCTION', 'CALLS_PROCEDURE', 'SUBMITS_TO_FLOW', 'CONTROLLER_HANDLES_FLOW', 'ACTION_CALLS_SERVICE'].includes(type))
    .map(type => `CROSS_FILE_${type}`);

// Export cross-file relationship types
export { CROSS_FILE_RELATIONSHIP_TYPES };

// Add JSP/Spring specific constraints
const JSP_SPRING_CONSTRAINTS = [
    `CREATE CONSTRAINT jsp_page_path IF NOT EXISTS FOR (n:JSPPage) REQUIRE n.servletPath IS UNIQUE`,
    `CREATE CONSTRAINT webflow_id IF NOT EXISTS FOR (n:WebFlowDefinition) REQUIRE n.flowId IS UNIQUE`,
    `CREATE CONSTRAINT flow_state_id IF NOT EXISTS FOR (n:FlowState) REQUIRE (n.parentId, n.stateId) IS UNIQUE`,
    `CREATE CONSTRAINT spring_controller_class IF NOT EXISTS FOR (n:SpringController) REQUIRE n.name IS UNIQUE`,
];

// Add JSP/Spring specific indexes
const JSP_SPRING_INDEXES = [
    `CREATE INDEX jsp_form_action_idx IF NOT EXISTS FOR (n:JSPForm) ON (n.action)`,
    `CREATE INDEX flow_transition_event_idx IF NOT EXISTS FOR (n:FlowTransition) ON (n.event)`,
    `CREATE INDEX spring_controller_mapping_idx IF NOT EXISTS FOR (n:SpringController) ON (n.requestMappings)`,
    `CREATE INDEX jsp_servlet_path_idx IF NOT EXISTS FOR (n:JSPPage) ON (n.servletPath)`,
    `CREATE INDEX flow_state_type_idx IF NOT EXISTS FOR (n:FlowState) ON (n.stateType)`,
    `CREATE INDEX spring_service_type_idx IF NOT EXISTS FOR (n:SpringService) ON (n.serviceType)`,
];

// Add Repository-specific constraints for multi-repository support
const REPOSITORY_CONSTRAINTS = [
    `CREATE CONSTRAINT repository_id_unique IF NOT EXISTS FOR (n:Repository) REQUIRE n.repositoryId IS UNIQUE`,
];

// Add IndexState-specific constraints for incremental indexing
const INDEX_STATE_CONSTRAINTS = [
    `CREATE CONSTRAINT indexstate_repoid_unique IF NOT EXISTS FOR (n:IndexState) REQUIRE n.repositoryId IS UNIQUE`,
];

// Add IndexState-specific indexes
const INDEX_STATE_INDEXES = [
    `CREATE INDEX indexstate_lastindexedat_idx IF NOT EXISTS FOR (n:IndexState) ON (n.lastIndexedAt)`,
    `CREATE INDEX indexstate_lastcommitsha_idx IF NOT EXISTS FOR (n:IndexState) ON (n.lastCommitSha)`,
];

// Add Repository-specific indexes
const REPOSITORY_INDEXES = [
    `CREATE INDEX repository_name_idx IF NOT EXISTS FOR (n:Repository) ON (n.name)`,
];

// Add Gradle/Maven module-specific constraints
const MODULE_CONSTRAINTS = [
    `CREATE CONSTRAINT javamodule_name_repo_unique IF NOT EXISTS FOR (n:JavaModule) REQUIRE (n.repositoryId, n.name) IS UNIQUE`,
    `CREATE CONSTRAINT gradledependency_gav_unique IF NOT EXISTS FOR (n:GradleDependency) REQUIRE (n.group, n.artifact, n.version) IS UNIQUE`,
];

// Add Gradle/Maven module-specific indexes
const MODULE_INDEXES = [
    `CREATE INDEX javamodule_name_idx IF NOT EXISTS FOR (n:JavaModule) ON (n.name)`,
    `CREATE INDEX javamodule_path_idx IF NOT EXISTS FOR (n:JavaModule) ON (n.path)`,
    `CREATE INDEX javamodule_repoid_idx IF NOT EXISTS FOR (n:JavaModule) ON (n.repositoryId)`,
    `CREATE INDEX gradledependency_group_idx IF NOT EXISTS FOR (n:GradleDependency) ON (n.group)`,
    `CREATE INDEX gradledependency_artifact_idx IF NOT EXISTS FOR (n:GradleDependency) ON (n.artifact)`,
    `CREATE INDEX gradleplugin_id_idx IF NOT EXISTS FOR (n:GradlePlugin) ON (n.pluginId)`,
];

// Repository Overview Feature - Entry Point constraints
const ENTRY_POINT_CONSTRAINTS = [
    `CREATE CONSTRAINT restendpoint_entityid_unique IF NOT EXISTS FOR (n:RestEndpoint) REQUIRE n.entityId IS UNIQUE`,
    `CREATE CONSTRAINT graphqloperation_entityid_unique IF NOT EXISTS FOR (n:GraphQLOperation) REQUIRE n.entityId IS UNIQUE`,
    `CREATE CONSTRAINT eventhandler_entityid_unique IF NOT EXISTS FOR (n:EventHandler) REQUIRE n.entityId IS UNIQUE`,
    `CREATE CONSTRAINT scheduledtask_entityid_unique IF NOT EXISTS FOR (n:ScheduledTask) REQUIRE n.entityId IS UNIQUE`,
    `CREATE CONSTRAINT clicommand_entityid_unique IF NOT EXISTS FOR (n:CLICommand) REQUIRE n.entityId IS UNIQUE`,
    `CREATE CONSTRAINT testfile_entityid_unique IF NOT EXISTS FOR (n:TestFile) REQUIRE n.entityId IS UNIQUE`,
    `CREATE CONSTRAINT testcase_entityid_unique IF NOT EXISTS FOR (n:TestCase) REQUIRE n.entityId IS UNIQUE`,
];

// Repository Overview Feature - Entry Point and Analysis indexes
const ENTRY_POINT_INDEXES = [
    // RestEndpoint indexes
    `CREATE INDEX restendpoint_httpmethod_idx IF NOT EXISTS FOR (n:RestEndpoint) ON (n.httpMethod)`,
    `CREATE INDEX restendpoint_path_idx IF NOT EXISTS FOR (n:RestEndpoint) ON (n.path)`,
    `CREATE INDEX restendpoint_fullpath_idx IF NOT EXISTS FOR (n:RestEndpoint) ON (n.fullPath)`,
    `CREATE INDEX restendpoint_framework_idx IF NOT EXISTS FOR (n:RestEndpoint) ON (n.framework)`,
    // GraphQLOperation indexes
    `CREATE INDEX graphqloperation_type_idx IF NOT EXISTS FOR (n:GraphQLOperation) ON (n.operationType)`,
    `CREATE INDEX graphqloperation_name_idx IF NOT EXISTS FOR (n:GraphQLOperation) ON (n.operationName)`,
    // EventHandler indexes
    `CREATE INDEX eventhandler_eventtype_idx IF NOT EXISTS FOR (n:EventHandler) ON (n.eventType)`,
    `CREATE INDEX eventhandler_eventsource_idx IF NOT EXISTS FOR (n:EventHandler) ON (n.eventSource)`,
    // ScheduledTask indexes
    `CREATE INDEX scheduledtask_scheduletype_idx IF NOT EXISTS FOR (n:ScheduledTask) ON (n.scheduleType)`,
    `CREATE INDEX scheduledtask_cron_idx IF NOT EXISTS FOR (n:ScheduledTask) ON (n.cronExpression)`,
    // CLICommand indexes
    `CREATE INDEX clicommand_name_idx IF NOT EXISTS FOR (n:CLICommand) ON (n.commandName)`,
    // TestFile indexes
    `CREATE INDEX testfile_framework_idx IF NOT EXISTS FOR (n:TestFile) ON (n.testFramework)`,
    `CREATE INDEX testfile_testedfile_idx IF NOT EXISTS FOR (n:TestFile) ON (n.testedFilePath)`,
    // TestCase indexes
    `CREATE INDEX testcase_name_idx IF NOT EXISTS FOR (n:TestCase) ON (n.testName)`,
    `CREATE INDEX testcase_suite_idx IF NOT EXISTS FOR (n:TestCase) ON (n.suiteName)`,
    // UIRoute indexes (Phase 1)
    `CREATE INDEX uiroute_path_idx IF NOT EXISTS FOR (n:UIRoute) ON (n.path)`,
    `CREATE INDEX uiroute_fullpath_idx IF NOT EXISTS FOR (n:UIRoute) ON (n.fullPath)`,
    `CREATE INDEX uiroute_framework_idx IF NOT EXISTS FOR (n:UIRoute) ON (n.framework)`,
    `CREATE INDEX uiroute_requiresauth_idx IF NOT EXISTS FOR (n:UIRoute) ON (n.requiresAuth)`,
    `CREATE INDEX uiroute_isdynamic_idx IF NOT EXISTS FOR (n:UIRoute) ON (n.isDynamic)`,
    // UIPage indexes (Phase 1)
    `CREATE INDEX uipage_routepath_idx IF NOT EXISTS FOR (n:UIPage) ON (n.routePath)`,
    `CREATE INDEX uipage_framework_idx IF NOT EXISTS FOR (n:UIPage) ON (n.framework)`,
    `CREATE INDEX uipage_routertype_idx IF NOT EXISTS FOR (n:UIPage) ON (n.routerType)`,
    `CREATE INDEX uipage_islayout_idx IF NOT EXISTS FOR (n:UIPage) ON (n.isLayout)`,
    `CREATE INDEX uipage_isdynamic_idx IF NOT EXISTS FOR (n:UIPage) ON (n.isDynamic)`,
    // Feature indexes (Phase 2)
    `CREATE INDEX feature_name_idx IF NOT EXISTS FOR (n:Feature) ON (n.featureName)`,
    `CREATE INDEX feature_category_idx IF NOT EXISTS FOR (n:Feature) ON (n.category)`,
    `CREATE INDEX feature_complexity_idx IF NOT EXISTS FOR (n:Feature) ON (n.complexity)`,
    `CREATE INDEX feature_confidence_idx IF NOT EXISTS FOR (n:Feature) ON (n.confidence)`,
];

// Full-text search indexes for semantic relevance-based queries
const FULLTEXT_INDEXES = [
    // Component full-text search (name + documentation + docComment)
    // Note: Uses actual AstNode property names from types.ts
    `CREATE FULLTEXT INDEX component_fulltext_search IF NOT EXISTS
     FOR (n:Class|Interface|Function|Method|JavaClass|JavaInterface|JavaMethod|SpringController|SpringService|PythonClass|PythonFunction|CSharpClass|GoFunction|GoStruct|Component)
     ON EACH [n.name, n.documentation, n.docComment]`,
    // File full-text search
    `CREATE FULLTEXT INDEX file_fulltext_search IF NOT EXISTS
     FOR (n:File)
     ON EACH [n.name, n.filePath]`,
    // API endpoint full-text search
    `CREATE FULLTEXT INDEX api_fulltext_search IF NOT EXISTS
     FOR (n:RestEndpoint|GraphQLOperation)
     ON EACH [n.name, n.path, n.fullPath, n.description]`,
    // Feature full-text search
    `CREATE FULLTEXT INDEX feature_fulltext_search IF NOT EXISTS
     FOR (n:Feature)
     ON EACH [n.featureName, n.description, n.category]`,
    // JSP/Spring full-text search
    `CREATE FULLTEXT INDEX jsp_spring_fulltext_search IF NOT EXISTS
     FOR (n:JSPPage|WebFlowDefinition|FlowState)
     ON EACH [n.name, n.description, n.servletPath, n.flowId]`,
    // Business Rule full-text search (Phase 3)
    `CREATE FULLTEXT INDEX businessrule_fulltext_search IF NOT EXISTS
     FOR (n:BusinessRule|ValidationConstraint|GuardClause|ConditionalBusinessLogic|TestAssertion)
     ON EACH [n.ruleText, n.condition, n.targetName, n.errorMessage]`,
    // Security Rule full-text search (Phase 6 - BRD Enhancement)
    `CREATE FULLTEXT INDEX security_fulltext_search IF NOT EXISTS
     FOR (n:SecurityRule)
     ON EACH [n.annotationText, n.expression, n.ruleDescription]`,
    // Error Message full-text search (Phase 6 - BRD Enhancement)
    `CREATE FULLTEXT INDEX errormessage_fulltext_search IF NOT EXISTS
     FOR (n:ErrorMessage)
     ON EACH [n.messageKey, n.messageText]`,
    // Method error messages full-text search (for code snippets)
    `CREATE FULLTEXT INDEX method_errors_fulltext_search IF NOT EXISTS
     FOR (n:JavaMethod)
     ON EACH [n.errorMessages, n.codeSnippet]`,
];

// Business Rule Extraction (Phase 3) - Constraints
const BUSINESS_RULE_CONSTRAINTS = [
    `CREATE CONSTRAINT businessrule_entityid_unique IF NOT EXISTS FOR (n:BusinessRule) REQUIRE n.entityId IS UNIQUE`,
    `CREATE CONSTRAINT validationconstraint_entityid_unique IF NOT EXISTS FOR (n:ValidationConstraint) REQUIRE n.entityId IS UNIQUE`,
    `CREATE CONSTRAINT guardclause_entityid_unique IF NOT EXISTS FOR (n:GuardClause) REQUIRE n.entityId IS UNIQUE`,
    `CREATE CONSTRAINT conditionalbusinesslogic_entityid_unique IF NOT EXISTS FOR (n:ConditionalBusinessLogic) REQUIRE n.entityId IS UNIQUE`,
    `CREATE CONSTRAINT testassertion_entityid_unique IF NOT EXISTS FOR (n:TestAssertion) REQUIRE n.entityId IS UNIQUE`,
];

// Menu & Screen Indexing (Phase 1) - Indexes
const MENU_SCREEN_INDEXES = [
    // MenuItem indexes
    `CREATE INDEX menuitem_label_idx IF NOT EXISTS FOR (n:MenuItem) ON (n.label)`,
    `CREATE INDEX menuitem_url_idx IF NOT EXISTS FOR (n:MenuItem) ON (n.url)`,
    `CREATE INDEX menuitem_flowid_idx IF NOT EXISTS FOR (n:MenuItem) ON (n.flowId)`,
    `CREATE INDEX menuitem_viewstateid_idx IF NOT EXISTS FOR (n:MenuItem) ON (n.viewStateId)`,
    `CREATE INDEX menuitem_parentmenu_idx IF NOT EXISTS FOR (n:MenuItem) ON (n.parentMenu)`,
    `CREATE INDEX menuitem_menulevel_idx IF NOT EXISTS FOR (n:MenuItem) ON (n.menuLevel)`,
    // Screen indexes
    `CREATE INDEX screen_screenid_idx IF NOT EXISTS FOR (n:Screen) ON (n.screenId)`,
    `CREATE INDEX screen_title_idx IF NOT EXISTS FOR (n:Screen) ON (n.title)`,
    `CREATE INDEX screen_flowid_idx IF NOT EXISTS FOR (n:Screen) ON (n.flowId)`,
    `CREATE INDEX screen_screentype_idx IF NOT EXISTS FOR (n:Screen) ON (n.screenType)`,
    `CREATE INDEX screen_actionclass_idx IF NOT EXISTS FOR (n:Screen) ON (n.actionClass)`,
    // ServiceMethod indexes
    `CREATE INDEX servicemethod_classname_idx IF NOT EXISTS FOR (n:ServiceMethod) ON (n.className)`,
    `CREATE INDEX servicemethod_methodname_idx IF NOT EXISTS FOR (n:ServiceMethod) ON (n.methodName)`,
    // SharedComponent indexes
    `CREATE INDEX sharedcomponent_type_idx IF NOT EXISTS FOR (n:SharedComponent) ON (n.componentType)`,
    `CREATE INDEX sharedcomponent_usagecount_idx IF NOT EXISTS FOR (n:SharedComponent) ON (n.usageCount)`,
    // EnrichedBusinessRule indexes
    `CREATE INDEX enrichedbusinessrule_ruletype_idx IF NOT EXISTS FOR (n:EnrichedBusinessRule) ON (n.ruleType)`,
    `CREATE INDEX enrichedbusinessrule_severity_idx IF NOT EXISTS FOR (n:EnrichedBusinessRule) ON (n.severity)`,
    `CREATE INDEX enrichedbusinessrule_menuitem_idx IF NOT EXISTS FOR (n:EnrichedBusinessRule) ON (n.menuItem)`,
];

// Menu & Screen full-text search
const MENU_SCREEN_FULLTEXT_INDEXES = [
    `CREATE FULLTEXT INDEX menu_fulltext_search IF NOT EXISTS
     FOR (n:MenuItem|Screen)
     ON EACH [n.label, n.title, n.name, n.url]`,
];

// Business Rule Extraction (Phase 3) - Indexes
const BUSINESS_RULE_INDEXES = [
    // BusinessRule indexes
    `CREATE INDEX businessrule_ruletype_idx IF NOT EXISTS FOR (n:BusinessRule) ON (n.ruleType)`,
    `CREATE INDEX businessrule_severity_idx IF NOT EXISTS FOR (n:BusinessRule) ON (n.severity)`,
    `CREATE INDEX businessrule_confidence_idx IF NOT EXISTS FOR (n:BusinessRule) ON (n.confidence)`,
    `CREATE INDEX businessrule_targetname_idx IF NOT EXISTS FOR (n:BusinessRule) ON (n.targetName)`,
    // ValidationConstraint indexes
    `CREATE INDEX validationconstraint_constraintname_idx IF NOT EXISTS FOR (n:ValidationConstraint) ON (n.constraintName)`,
    `CREATE INDEX validationconstraint_targetname_idx IF NOT EXISTS FOR (n:ValidationConstraint) ON (n.targetName)`,
    `CREATE INDEX validationconstraint_framework_idx IF NOT EXISTS FOR (n:ValidationConstraint) ON (n.framework)`,
    `CREATE INDEX validationconstraint_confidence_idx IF NOT EXISTS FOR (n:ValidationConstraint) ON (n.confidence)`,
    // GuardClause indexes
    `CREATE INDEX guardclause_guardtype_idx IF NOT EXISTS FOR (n:GuardClause) ON (n.guardType)`,
    `CREATE INDEX guardclause_guardedmethod_idx IF NOT EXISTS FOR (n:GuardClause) ON (n.guardedMethod)`,
    `CREATE INDEX guardclause_isprecondition_idx IF NOT EXISTS FOR (n:GuardClause) ON (n.isPrecondition)`,
    `CREATE INDEX guardclause_confidence_idx IF NOT EXISTS FOR (n:GuardClause) ON (n.confidence)`,
    // ConditionalBusinessLogic indexes
    `CREATE INDEX conditionalbusinesslogic_variable_idx IF NOT EXISTS FOR (n:ConditionalBusinessLogic) ON (n.variable)`,
    `CREATE INDEX conditionalbusinesslogic_operator_idx IF NOT EXISTS FOR (n:ConditionalBusinessLogic) ON (n.operator)`,
    `CREATE INDEX conditionalbusinesslogic_confidence_idx IF NOT EXISTS FOR (n:ConditionalBusinessLogic) ON (n.confidence)`,
    // TestAssertion indexes
    `CREATE INDEX testassertion_assertiontype_idx IF NOT EXISTS FOR (n:TestAssertion) ON (n.assertionType)`,
    `CREATE INDEX testassertion_testmethodname_idx IF NOT EXISTS FOR (n:TestAssertion) ON (n.testMethodName)`,
    `CREATE INDEX testassertion_testedentity_idx IF NOT EXISTS FOR (n:TestAssertion) ON (n.testedEntity)`,
    `CREATE INDEX testassertion_testframework_idx IF NOT EXISTS FOR (n:TestAssertion) ON (n.testFramework)`,
    // SecurityRule indexes (Phase 6 - BRD Enhancement)
    `CREATE INDEX securityrule_annotationtype_idx IF NOT EXISTS FOR (n:SecurityRule) ON (n.annotationType)`,
    `CREATE INDEX securityrule_roles_idx IF NOT EXISTS FOR (n:SecurityRule) ON (n.roles)`,
    `CREATE INDEX securityrule_targettype_idx IF NOT EXISTS FOR (n:SecurityRule) ON (n.targetType)`,
    // ErrorMessage indexes (Phase 6 - BRD Enhancement)
    `CREATE INDEX errormessage_messagekey_idx IF NOT EXISTS FOR (n:ErrorMessage) ON (n.messageKey)`,
    `CREATE INDEX errormessage_sourcefile_idx IF NOT EXISTS FOR (n:ErrorMessage) ON (n.sourceFile)`,
    `CREATE INDEX errormessage_locale_idx IF NOT EXISTS FOR (n:ErrorMessage) ON (n.locale)`,
    // Business Logic Blueprint indexes (Phase 7)
    `CREATE INDEX datatable_id_idx IF NOT EXISTS FOR (n:DataTable) ON (n.tableId)`,
    `CREATE INDEX datatable_datasource_idx IF NOT EXISTS FOR (n:DataTable) ON (n.dataSource)`,
    `CREATE INDEX businessconstant_name_idx IF NOT EXISTS FOR (n:BusinessConstant) ON (n.constantName)`,
    `CREATE INDEX businessconstant_value_idx IF NOT EXISTS FOR (n:BusinessConstant) ON (n.value)`,
    `CREATE INDEX businessconstant_type_idx IF NOT EXISTS FOR (n:BusinessConstant) ON (n.constantType)`,
    `CREATE INDEX screenmode_mode_idx IF NOT EXISTS FOR (n:ScreenMode) ON (n.mode)`,
    `CREATE INDEX screenmode_source_idx IF NOT EXISTS FOR (n:ScreenMode) ON (n.modeSource)`,
    `CREATE INDEX featureblueprint_name_idx IF NOT EXISTS FOR (n:FeatureBlueprint) ON (n.featureName)`,
    `CREATE INDEX featureblueprint_confidence_idx IF NOT EXISTS FOR (n:FeatureBlueprint) ON (n.confidence)`,
    `CREATE INDEX selectoption_value_idx IF NOT EXISTS FOR (n:SelectOption) ON (n.value)`,
];

// Repository Overview Feature - Analysis property indexes (for AstNode properties)
const ANALYSIS_INDEXES = [
    // Stereotype index for architecture analysis
    `CREATE INDEX node_stereotype_idx IF NOT EXISTS FOR (n:Class) ON (n.stereotype)`,
    `CREATE INDEX javaclass_stereotype_idx IF NOT EXISTS FOR (n:JavaClass) ON (n.stereotype)`,
    `CREATE INDEX csharpclass_stereotype_idx IF NOT EXISTS FOR (n:CSharpClass) ON (n.stereotype)`,
    // Documentation coverage index
    `CREATE INDEX node_hasdoc_idx IF NOT EXISTS FOR (n:Function) ON (n.hasDocumentation)`,
    `CREATE INDEX method_hasdoc_idx IF NOT EXISTS FOR (n:Method) ON (n.hasDocumentation)`,
    `CREATE INDEX class_hasdoc_idx IF NOT EXISTS FOR (n:Class) ON (n.hasDocumentation)`,
    // Deprecation index
    `CREATE INDEX node_deprecated_idx IF NOT EXISTS FOR (n:Function) ON (n.isDeprecated)`,
    `CREATE INDEX method_deprecated_idx IF NOT EXISTS FOR (n:Method) ON (n.isDeprecated)`,
    `CREATE INDEX class_deprecated_idx IF NOT EXISTS FOR (n:Class) ON (n.isDeprecated)`,
    // Complexity metrics indexes (for hotspot queries)
    `CREATE INDEX function_complexity_idx IF NOT EXISTS FOR (n:Function) ON (n.complexity)`,
    `CREATE INDEX method_complexity_idx IF NOT EXISTS FOR (n:Method) ON (n.complexity)`,
    // Entry point type index
    `CREATE INDEX node_entrypoint_idx IF NOT EXISTS FOR (n:Function) ON (n.entryPointType)`,
    `CREATE INDEX method_entrypoint_idx IF NOT EXISTS FOR (n:Method) ON (n.entryPointType)`,
    // PageRank index for relevance-based retrieval
    `CREATE INDEX class_pagerank_idx IF NOT EXISTS FOR (n:Class) ON (n.pageRank)`,
    `CREATE INDEX javaclass_pagerank_idx IF NOT EXISTS FOR (n:JavaClass) ON (n.pageRank)`,
    `CREATE INDEX function_pagerank_idx IF NOT EXISTS FOR (n:Function) ON (n.pageRank)`,
    `CREATE INDEX method_pagerank_idx IF NOT EXISTS FOR (n:Method) ON (n.pageRank)`,
    `CREATE INDEX springcontroller_pagerank_idx IF NOT EXISTS FOR (n:SpringController) ON (n.pageRank)`,
    `CREATE INDEX springservice_pagerank_idx IF NOT EXISTS FOR (n:SpringService) ON (n.pageRank)`,
];

// Node Uniqueness Constraints (Crucial for merging nodes correctly)
const nodeUniquenessConstraints = [
    ...NODE_LABELS.map(label =>
        `CREATE CONSTRAINT ${label.toLowerCase()}_entityid_unique IF NOT EXISTS FOR (n:\`${label}\`) REQUIRE n.entityId IS UNIQUE`
    ),
    ...JSP_SPRING_CONSTRAINTS,
    ...REPOSITORY_CONSTRAINTS,
    ...INDEX_STATE_CONSTRAINTS,
    ...MODULE_CONSTRAINTS,
    ...ENTRY_POINT_CONSTRAINTS,
    ...BUSINESS_RULE_CONSTRAINTS,
];

// Indexes for faster lookups (Essential for performance)
const indexes = [
    ...NODE_LABELS.map(label => `CREATE INDEX ${label.toLowerCase()}_filepath_index IF NOT EXISTS FOR (n:${label}) ON (n.filePath)`),
    ...NODE_LABELS.map(label => `CREATE INDEX ${label.toLowerCase()}_name_index IF NOT EXISTS FOR (n:${label}) ON (n.name)`),
    `CREATE INDEX file_kind_index IF NOT EXISTS FOR (n:File) ON (n.kind)`,
    ...JSP_SPRING_INDEXES,
    ...REPOSITORY_INDEXES,
    ...INDEX_STATE_INDEXES,
    ...MODULE_INDEXES,
    ...ENTRY_POINT_INDEXES,
    ...ANALYSIS_INDEXES,
    ...BUSINESS_RULE_INDEXES,
    ...FULLTEXT_INDEXES,
    ...MENU_SCREEN_INDEXES,
    ...MENU_SCREEN_FULLTEXT_INDEXES,
];

// Export schema arrays
export const SCHEMA_CONSTRAINTS = nodeUniquenessConstraints;
export const SCHEMA_INDEXES = indexes;

/**
 * Manages the application of schema (constraints and indexes) to the Neo4j database.
 */
export class SchemaManager {
    private neo4jClient: Neo4jClient;

    constructor(neo4jClient: Neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    /**
     * Applies all defined constraints and indexes to the database.
     * @param forceUpdate - If true, drops existing schema elements before applying.
     */
    async applySchema(forceUpdate: boolean = false): Promise<void> {
        logger.info(`Applying schema... Force update: ${forceUpdate}`);
        if (forceUpdate) {
            await this.dropAllSchemaElements();
        }

        const allSchemaCommands = [
            ...nodeUniquenessConstraints,
            ...indexes,
        ];

        let appliedCount = 0;
        let failedCount = 0;

        for (const command of allSchemaCommands) {
            try {
                await this.neo4jClient.runTransaction(command, {}, 'WRITE', 'SchemaManager');
                logger.debug(`Successfully applied schema command: ${command.split(' ')[2]}...`);
                appliedCount++;
            } catch (error: any) {
                const alreadyExists = error.code === 'Neo.ClientError.Schema.ConstraintAlreadyExists' ||
                                      error.code === 'Neo.ClientError.Schema.IndexAlreadyExists' ||
                                      error.message?.includes('already exists');

                if (!alreadyExists || forceUpdate) {
                    logger.error(`Failed to apply schema command: ${command}`, { code: error.code, message: error.message });
                    failedCount++;
                } else {
                     logger.debug(`Schema element already exists, skipping: ${command.split(' ')[2]}...`);
                }
            }
        }
        logger.info(`Schema application finished. Applied/Verified: ${appliedCount}, Failed: ${failedCount}.`);
        if (failedCount > 0 && forceUpdate) {
             throw new Neo4jError(`Failed to apply ${failedCount} schema elements during forced update.`);
        }
    }

    /**
     * Drops all known user-defined constraints and indexes.
     * WARNING: Use with caution.
     */
    async dropAllSchemaElements(): Promise<void> {
        logger.warn('Dropping ALL user-defined constraints and indexes from the database...');
        let droppedConstraints = 0;
        let droppedIndexes = 0;
        let failedDrops = 0;

        try {
            const constraintsResult = await this.neo4jClient.runTransaction<{ name: string }[]>(
                'SHOW CONSTRAINTS YIELD name', {}, 'READ', 'SchemaManager'
            );
            // @ts-ignore TODO: Fix type casting from runTransaction
            const constraintNames = constraintsResult.records?.map((r: any) => r.get('name')) || [];
            logger.debug(`Found ${constraintNames.length} existing constraints.`);

            for (const name of constraintNames) {
                try {
                    await this.neo4jClient.runTransaction(`DROP CONSTRAINT ${name}`, {}, 'WRITE', 'SchemaManager');
                    logger.debug(`Dropped constraint: ${name}`);
                    droppedConstraints++;
                } catch (error: any) {
                    logger.error(`Failed to drop constraint: ${name}`, { message: error.message });
                    failedDrops++;
                }
            }

            const indexesResult = await this.neo4jClient.runTransaction<{ name: string }[]>(
                'SHOW INDEXES YIELD name', {}, 'READ', 'SchemaManager'
            );
             // @ts-ignore TODO: Fix type casting from runTransaction
            const indexNames = indexesResult.records?.map((r: any) => r.get('name')).filter((name: string) => !name.includes('constraint')) || [];
            logger.debug(`Found ${indexNames.length} existing user indexes.`);

            for (const name of indexNames) {
                try {
                    await this.neo4jClient.runTransaction(`DROP INDEX ${name}`, {}, 'WRITE', 'SchemaManager');
                    logger.debug(`Dropped index: ${name}`);
                    droppedIndexes++;
                } catch (error: any) {
                    logger.error(`Failed to drop index: ${name}`, { message: error.message });
                    failedDrops++;
                }
            }

            logger.info(`Finished attempting to drop schema elements: ${droppedConstraints} constraints, ${droppedIndexes} indexes dropped. ${failedDrops} failures.`);

        } catch (error: any) {
            logger.error('Failed to retrieve existing schema elements for dropping.', { message: error.message });
            throw new Neo4jError('Failed to retrieve schema for dropping.', { originalError: error });
        }
         if (failedDrops > 0) {
             logger.warn(`Encountered ${failedDrops} errors while dropping schema elements.`);
         }
    }

     /**
     * Deletes all nodes and relationships from the database.
     * WARNING: This is destructive and irreversible.
     */
    async resetDatabase(): Promise<void> {
        logger.warn('Deleting ALL nodes and relationships from the database...');
        try {
            await this.neo4jClient.runTransaction('MATCH (n) DETACH DELETE n', {}, 'WRITE', 'SchemaManager');
            logger.info('All nodes and relationships deleted.');
        } catch (error: any) {
            logger.error('Failed to delete all data from the database.', { message: error.message });
            throw new Neo4jError('Failed to reset database.', { originalError: error });
        }
    }
}