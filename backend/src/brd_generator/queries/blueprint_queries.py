"""Neo4j queries for Business Logic Blueprint generation.

These queries fetch hierarchical data organized by Menu -> Screen -> Fields/Actions.
"""

# =============================================================================
# Menu Hierarchy Queries
# =============================================================================

GET_MENU_HIERARCHY = """
MATCH (m:MenuItem)
WHERE m.repositoryId = $repositoryId OR m.repositoryId IS NULL
OPTIONAL MATCH (m)-[:HAS_MENU_ITEM]->(sub:MenuItem)
OPTIONAL MATCH (sub)-[:MENU_OPENS_FLOW]->(flow:WebFlowDefinition)
OPTIONAL MATCH (flow)-[:FLOW_DEFINES_STATE]->(state:FlowState)
WHERE state.stateType = 'view-state'
WITH m, sub, flow, collect(DISTINCT {
    screenId: state.stateId,
    name: state.name,
    flowId: flow.flowId,
    viewName: state.properties.view
}) as screens
WITH m, collect(DISTINCT {
    label: sub.label,
    url: sub.url,
    flowId: sub.flowId,
    screens: screens
}) as children
WHERE m.menuLevel = 1 OR m.parentMenu IS NULL
RETURN {
    label: m.label,
    url: m.url,
    menuLevel: m.menuLevel,
    children: children
} as menu
ORDER BY m.sortOrder, m.label
"""

GET_SUBMENU_SCREENS = """
MATCH (m:MenuItem {label: $menuLabel})
OPTIONAL MATCH (m)-[:MENU_OPENS_FLOW]->(flow:WebFlowDefinition)
OPTIONAL MATCH (flow)-[:FLOW_DEFINES_STATE]->(state:FlowState)
WHERE state.stateType = 'view-state'
OPTIONAL MATCH (state)-[:SCREEN_RENDERS_JSP]->(jsp:JSPPage)
RETURN {
    screenId: state.stateId,
    name: state.name,
    flowId: flow.flowId,
    viewName: state.properties.view,
    jspPath: jsp.filePath
} as screen
"""

# =============================================================================
# Screen Detail Queries
# =============================================================================

GET_SCREEN_DETAILS = """
MATCH (state:FlowState {stateId: $screenId})
OPTIONAL MATCH (state)<-[:FLOW_DEFINES_STATE]-(flow:WebFlowDefinition)
OPTIONAL MATCH (state)-[:SCREEN_RENDERS_JSP]->(jsp:JSPPage)
OPTIONAL MATCH (state)-[:SCREEN_CALLS_ACTION]->(action:JavaClass)
RETURN {
    screenId: state.stateId,
    name: state.name,
    stateType: state.stateType,
    flowId: flow.flowId,
    jspPath: jsp.filePath,
    jspServletPath: jsp.properties.servletPath,
    actionClass: action.name,
    transitions: state.properties.transitions,
    onEntry: state.properties.onEntry,
    onExit: state.properties.onExit,
    onRender: state.properties.onRender
} as screen
"""

GET_SCREEN_FIELDS = """
MATCH (state:FlowState {stateId: $screenId})
OPTIONAL MATCH (state)-[:SCREEN_RENDERS_JSP]->(jsp:JSPPage)
OPTIONAL MATCH (jsp)-[:CONTAINS_FORM]->(form:JSPForm)

// Get form fields
WITH state, jsp, form
UNWIND coalesce(form.properties.fields, []) as field

RETURN {
    name: field.name,
    label: field.label,
    labelKey: field.labelKey,
    type: field.type,
    required: field.required,
    defaultValue: field.defaultValue,
    placeholder: field.placeholder,
    helpText: field.helpText,
    validationRules: field.validationRules,
    selectOptions: field.selectOptions,
    dataSource: field.dataSource,
    readOnly: field.readOnly,
    disabled: field.disabled,
    cssClasses: field.cssClasses
} as field
"""

GET_SCREEN_ACTIONS = """
MATCH (state:FlowState {stateId: $screenId})

// Get transitions as actions
WITH state, state.properties.transitions as transitions
UNWIND coalesce(transitions, []) as transition

// Get associated action methods
OPTIONAL MATCH (state)-[:FLOW_EXECUTES_ACTION]->(action:FlowAction)
WHERE action.properties.actionName CONTAINS transition.event OR
      action.properties.expression CONTAINS transition.event

RETURN {
    name: transition.event,
    label: transition.event,
    event: transition.event,
    targetState: transition.to,
    condition: transition.condition,
    method: action.properties.beanMethod,
    expression: action.properties.expression
} as action
"""

GET_SCREEN_VALIDATIONS = """
MATCH (state:FlowState {stateId: $screenId})

// Get validations from flow state
OPTIONAL MATCH (state)-[:SCREEN_CALLS_ACTION]->(actionClass:JavaClass)
OPTIONAL MATCH (actionClass)-[:HAS_METHOD]->(method:JavaMethod)
OPTIONAL MATCH (method)-[:GUARDS_METHOD]->(guard:GuardClause)
OPTIONAL MATCH (method)-[:VALIDATES_FIELD]-(validation:ValidationConstraint)

// Get validations from JSP
OPTIONAL MATCH (state)-[:SCREEN_RENDERS_JSP]->(jsp:JSPPage)
OPTIONAL MATCH (jsp)-[:ENFORCES_RULE]->(rule:BusinessRule)

WITH collect(DISTINCT {
    type: 'guard',
    ruleText: guard.ruleText,
    condition: guard.condition,
    targetName: guard.targetName,
    errorMessage: guard.errorMessage,
    confidence: guard.confidence
}) + collect(DISTINCT {
    type: 'validation',
    constraintName: validation.constraintName,
    targetName: validation.targetName,
    attributes: validation.attributes,
    message: validation.message,
    confidence: validation.confidence
}) + collect(DISTINCT {
    type: 'businessRule',
    ruleText: rule.ruleText,
    ruleType: rule.ruleType,
    severity: rule.severity,
    confidence: rule.confidence
}) as allValidations

UNWIND allValidations as validation
WHERE validation.ruleText IS NOT NULL OR validation.constraintName IS NOT NULL

RETURN {
    type: validation.type,
    description: coalesce(validation.ruleText, validation.constraintName, 'Validation'),
    ruleText: validation.ruleText,
    targetName: validation.targetName,
    errorMessage: coalesce(validation.errorMessage, validation.message),
    confidence: validation.confidence
} as validation
"""

GET_SECURITY_RULES_FOR_SCREEN = """
MATCH (state:FlowState {stateId: $screenId})

// Get security rules from action class
OPTIONAL MATCH (state)-[:SCREEN_CALLS_ACTION]->(actionClass:JavaClass)
OPTIONAL MATCH (actionClass)-[:SECURED_BY]->(classRule:SecurityRule)

// Get security rules from methods
OPTIONAL MATCH (actionClass)-[:HAS_METHOD]->(method:JavaMethod)
OPTIONAL MATCH (method)-[:SECURED_BY]->(methodRule:SecurityRule)

// Get security from flow definition
OPTIONAL MATCH (state)<-[:FLOW_DEFINES_STATE]-(flow:WebFlowDefinition)
OPTIONAL MATCH (flow)-[:SECURED_BY]->(flowRule:SecurityRule)

WITH collect(DISTINCT {
    annotationType: classRule.properties.annotationType,
    expression: classRule.properties.expression,
    roles: classRule.properties.roles,
    targetType: 'class',
    targetName: actionClass.name,
    ruleDescription: classRule.properties.ruleDescription
}) + collect(DISTINCT {
    annotationType: methodRule.properties.annotationType,
    expression: methodRule.properties.expression,
    roles: methodRule.properties.roles,
    targetType: 'method',
    targetName: method.name,
    ruleDescription: methodRule.properties.ruleDescription
}) + collect(DISTINCT {
    annotationType: flowRule.properties.annotationType,
    expression: flowRule.properties.expression,
    roles: flowRule.properties.roles,
    targetType: 'flow',
    targetName: flow.flowId,
    ruleDescription: flowRule.properties.ruleDescription
}) as allRules

UNWIND allRules as rule
WHERE rule.annotationType IS NOT NULL

RETURN rule
"""

GET_ERROR_MESSAGES_FOR_SCREEN = """
MATCH (state:FlowState {stateId: $screenId})

// Get error messages from action class methods
OPTIONAL MATCH (state)-[:SCREEN_CALLS_ACTION]->(actionClass:JavaClass)
OPTIONAL MATCH (actionClass)-[:HAS_METHOD]->(method:JavaMethod)
OPTIONAL MATCH (method)-[:REFERENCES_MESSAGE]->(msg:ErrorMessage)

// Get error messages from JSP
OPTIONAL MATCH (state)-[:SCREEN_RENDERS_JSP]->(jsp:JSPPage)
OPTIONAL MATCH (jsp)-[:REFERENCES_MESSAGE]->(jspMsg:ErrorMessage)

WITH collect(DISTINCT {
    messageKey: msg.properties.messageKey,
    messageText: msg.properties.messageText,
    sourceType: 'java',
    contextMethod: method.name,
    locale: msg.properties.locale
}) + collect(DISTINCT {
    messageKey: jspMsg.properties.messageKey,
    messageText: jspMsg.properties.messageText,
    sourceType: 'jsp',
    locale: jspMsg.properties.locale
}) as allMessages

UNWIND allMessages as message
WHERE message.messageKey IS NOT NULL

RETURN message
"""

GET_DATA_TABLES_FOR_SCREEN = """
MATCH (state:FlowState {stateId: $screenId})
OPTIONAL MATCH (state)-[:SCREEN_RENDERS_JSP]->(jsp:JSPPage)
OPTIONAL MATCH (jsp)-[:HAS_DATA_TABLE]->(table:DataTable)

WHERE table IS NOT NULL

RETURN {
    id: table.properties.id,
    dataSource: table.properties.dataSource,
    columns: table.properties.columns,
    paginated: table.properties.paginated,
    pageSize: table.properties.pageSize,
    selectable: table.properties.selectable,
    selectionMode: table.properties.selectionMode
} as dataTable
"""

# =============================================================================
# Feature-Level Queries
# =============================================================================

GET_FEATURE_BLUEPRINT_CONTEXT = """
// Search for feature by name in menu items
CALL db.index.fulltext.queryNodes('menu_fulltext_search', $featureName)
YIELD node as menuItem, score
WHERE score > 0.5

// Get the flow and screens for this menu item
OPTIONAL MATCH (menuItem)-[:MENU_OPENS_FLOW]->(flow:WebFlowDefinition)
OPTIONAL MATCH (flow)-[:FLOW_DEFINES_STATE]->(state:FlowState)
WHERE state.stateType = 'view-state'

// Get parent menu path
OPTIONAL MATCH path = (root:MenuItem)-[:HAS_MENU_ITEM*0..3]->(menuItem)
WHERE root.menuLevel = 1 OR root.parentMenu IS NULL

WITH menuItem, flow, collect(DISTINCT state) as screens,
     [n IN nodes(path) | n.label] as menuPath
ORDER BY score DESC
LIMIT 1

RETURN {
    featureName: menuItem.label,
    menuPath: menuPath,
    flowId: flow.flowId,
    flowName: flow.name,
    screens: [s IN screens | {
        screenId: s.stateId,
        name: s.name,
        viewName: s.properties.view
    }],
    score: score
} as feature
"""

GET_ALL_FEATURES_SUMMARY = """
MATCH (m:MenuItem)
WHERE m.menuLevel = 2 OR (m.menuLevel IS NULL AND m.parentMenu IS NOT NULL)
OPTIONAL MATCH (m)-[:MENU_OPENS_FLOW]->(flow:WebFlowDefinition)
OPTIONAL MATCH (flow)-[:FLOW_DEFINES_STATE]->(state:FlowState)
WHERE state.stateType = 'view-state'

// Get parent menu
OPTIONAL MATCH (parent:MenuItem)-[:HAS_MENU_ITEM]->(m)

WITH m, parent, flow, count(DISTINCT state) as screenCount
RETURN {
    featureName: m.label,
    parentMenu: parent.label,
    flowId: flow.flowId,
    screenCount: screenCount,
    url: m.url
} as feature
ORDER BY parent.label, m.label
"""

# =============================================================================
# Cross-Feature Analysis Queries
# =============================================================================

GET_SHARED_ENTITIES = """
// Find entities used by multiple screens
MATCH (state1:FlowState)-[:SCREEN_CALLS_ACTION]->(action1:JavaClass)
MATCH (action1)-[:HAS_METHOD]->(method1:JavaMethod)
MATCH (method1)-[:METHOD_USES_ENTITY]->(entity:JavaClass)
MATCH (method2:JavaMethod)-[:METHOD_USES_ENTITY]->(entity)
MATCH (action2:JavaClass)-[:HAS_METHOD]->(method2)
MATCH (state2:FlowState)-[:SCREEN_CALLS_ACTION]->(action2)
WHERE state1 <> state2

WITH entity, collect(DISTINCT state1.stateId) as screens1,
     collect(DISTINCT state2.stateId) as screens2
WHERE size(screens1 + screens2) > 1

RETURN {
    entityName: entity.name,
    entityType: entity.properties.qualifiedName,
    usedByScreens: apoc.coll.toSet(screens1 + screens2)
} as sharedEntity
"""

GET_FEATURE_DEPENDENCIES = """
// Find dependencies between menu items based on shared services/entities
MATCH (m1:MenuItem)-[:MENU_OPENS_FLOW]->(f1:WebFlowDefinition)
MATCH (f1)-[:FLOW_DEFINES_STATE]->(s1:FlowState)
MATCH (s1)-[:SCREEN_CALLS_ACTION]->(a1:JavaClass)
MATCH (a1)-[:INJECTS_SERVICE]->(service:SpringService)
MATCH (a2:JavaClass)-[:INJECTS_SERVICE]->(service)
MATCH (s2:FlowState)-[:SCREEN_CALLS_ACTION]->(a2)
MATCH (f2:WebFlowDefinition)-[:FLOW_DEFINES_STATE]->(s2)
MATCH (m2:MenuItem)-[:MENU_OPENS_FLOW]->(f2)
WHERE m1 <> m2

RETURN {
    feature1: m1.label,
    feature2: m2.label,
    sharedService: service.name,
    dependencyType: 'shared_service'
} as dependency
"""

# =============================================================================
# Constants and Thresholds Queries
# =============================================================================

GET_BUSINESS_CONSTANTS = """
MATCH (c:BusinessConstant)
WHERE c.repositoryId = $repositoryId OR c.repositoryId IS NULL
RETURN {
    name: c.properties.name,
    value: c.properties.value,
    dataType: c.properties.dataType,
    className: c.properties.className,
    description: c.properties.description,
    isConfigurable: c.properties.isConfigurable,
    isMagicNumber: c.properties.isMagicNumber
} as constant
ORDER BY c.properties.className, c.properties.name
"""

GET_CONSTANTS_FOR_FEATURE = """
MATCH (m:MenuItem {label: $featureName})
MATCH (m)-[:MENU_OPENS_FLOW]->(flow:WebFlowDefinition)
MATCH (flow)-[:FLOW_DEFINES_STATE]->(state:FlowState)
MATCH (state)-[:SCREEN_CALLS_ACTION]->(action:JavaClass)
MATCH (action)-[:HAS_CONSTANT]->(constant:BusinessConstant)

RETURN {
    name: constant.properties.name,
    value: constant.properties.value,
    dataType: constant.properties.dataType,
    className: action.name,
    description: constant.properties.description,
    usedInScreen: state.stateId
} as constant
"""
