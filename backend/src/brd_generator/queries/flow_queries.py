"""Cypher queries for feature flow extraction.

This module contains all the Neo4j Cypher queries used for extracting
feature flows from UI to database.
"""

# Trace full flow from JSP/WebFlow through to SQL operations
TRACE_FULL_FLOW = """
    // Start from entry point (JSP or WebFlow)
    MATCH (entry)
    WHERE entry.entityId = $entryPointId
       OR entry.filePath CONTAINS $entryPointPath
       OR entry.name = $entryPointName

    // Collect entry point info
    WITH entry, labels(entry)[0] AS entryType

    // Find connected flow components
    OPTIONAL MATCH (entry)-[:CONTAINS_FORM|SUBMITS_TO_FLOW|FLOW_RENDERS_VIEW*0..2]-(flow:WebFlowDefinition)
    WITH entry, entryType, collect(DISTINCT flow) AS flowNodes

    // Find controllers/actions from flows
    OPTIONAL MATCH (f)-[:FLOW_EXECUTES_ACTION|HAS_ACTION_STATE*1..2]->(action)
    WHERE f IN flowNodes AND (action:FlowAction OR action:JavaMethod)
    WITH entry, entryType, flowNodes, collect(DISTINCT action) AS actionNodes

    // Find controller classes
    OPTIONAL MATCH (controller)-[:HAS_METHOD]->(a)
    WHERE a IN actionNodes AND (controller:JavaClass OR controller:SpringController)
    WITH entry, entryType, flowNodes, actionNodes, collect(DISTINCT controller) AS controllerNodes

    // Find services called by controllers
    OPTIONAL MATCH (c)-[:HAS_METHOD]->(:JavaMethod)-[:INVOKES|CALLS*1..3]->(serviceMethod:JavaMethod)
    WHERE c IN controllerNodes
    OPTIONAL MATCH (serviceClass)-[:HAS_METHOD]->(serviceMethod)
    WHERE toLower(serviceClass.name) CONTAINS 'service'
       OR toLower(serviceClass.name) CONTAINS 'builder'
       OR toLower(serviceClass.name) CONTAINS 'validator'
    WITH entry, entryType, flowNodes, controllerNodes,
         collect(DISTINCT serviceClass) AS serviceNodes,
         collect(DISTINCT serviceMethod) AS serviceMethods

    // Find DAOs called by services
    OPTIONAL MATCH (s)-[:HAS_METHOD]->(:JavaMethod)-[:INVOKES|CALLS*1..3]->(daoMethod:JavaMethod)
    WHERE s IN serviceNodes
    OPTIONAL MATCH (daoClass)-[:HAS_METHOD]->(daoMethod)
    WHERE toLower(daoClass.name) CONTAINS 'dao'
       OR toLower(daoClass.name) CONTAINS 'repository'
    WITH entry, entryType, flowNodes, controllerNodes, serviceNodes,
         collect(DISTINCT daoClass) AS daoNodes,
         collect(DISTINCT daoMethod) AS daoMethods

    // Find SQL operations
    OPTIONAL MATCH (dm)-[:EXECUTES_SQL]->(sql:SQLStatement)
    WHERE dm IN daoMethods
    WITH entry, entryType, flowNodes, controllerNodes, serviceNodes, daoNodes,
         collect(DISTINCT sql) AS sqlNodes

    // Return all layers with proper aggregation
    RETURN
        entry.entityId AS entryId,
        entry.name AS entryName,
        entry.filePath AS entryPath,
        entryType,
        [f IN flowNodes WHERE f IS NOT NULL | {
            name: f.name,
            path: f.filePath,
            type: 'WebFlowDefinition'
        }] AS flows,
        [c IN controllerNodes WHERE c IS NOT NULL | {
            name: c.name,
            path: c.filePath,
            type: labels(c)[0]
        }] AS controllers,
        [s IN serviceNodes WHERE s IS NOT NULL | {
            name: s.name,
            path: s.filePath,
            type: labels(s)[0]
        }] AS services,
        [d IN daoNodes WHERE d IS NOT NULL | {
            name: d.name,
            path: d.filePath,
            type: labels(d)[0]
        }] AS daos,
        [sq IN sqlNodes WHERE sq IS NOT NULL | {
            statementType: sq.statementType,
            tableName: sq.tableName,
            columns: sq.columns,
            rawSql: sq.rawSql,
            lineNumber: sq.lineNumber
        }] AS sqlOperations
"""

# Get method call chain with line numbers
GET_METHOD_CALL_CHAIN = """
    MATCH (entry {entityId: $methodId})

    // Traverse downstream calls
    OPTIONAL MATCH path = (entry)-[:CALLS|INVOKES|HAS_METHOD*1..$maxDepth]->(target)

    WITH entry, path, target,
         length(path) AS depth,
         [rel IN relationships(path) | {
             type: type(rel),
             lineNumber: rel.lineNumber,
             arguments: rel.arguments
         }] AS relationships

    // Get method details
    OPTIONAL MATCH (parent)-[:HAS_METHOD]->(target)

    RETURN DISTINCT
        target.entityId AS nodeId,
        target.name AS name,
        labels(target)[0] AS type,
        target.filePath AS filePath,
        target.startLine AS startLine,
        target.endLine AS endLine,
        COALESCE(target.signature, '') AS signature,
        parent.name AS parentClass,
        depth,
        relationships[-1].lineNumber AS calledAtLine,
        relationships[-1].arguments AS arguments,
        CASE
            WHEN 'JSPPage' IN labels(target) THEN 'UI'
            WHEN 'WebFlowDefinition' IN labels(target) OR 'FlowState' IN labels(target) THEN 'Flow'
            WHEN toLower(target.name) ENDS WITH 'action' OR toLower(target.name) ENDS WITH 'controller' THEN 'Controller'
            WHEN toLower(COALESCE(parent.name, target.name)) CONTAINS 'dao' OR toLower(COALESCE(parent.name, target.name)) CONTAINS 'repository' THEN 'DAO'
            WHEN toLower(COALESCE(parent.name, target.name)) CONTAINS 'service' OR toLower(COALESCE(parent.name, target.name)) CONTAINS 'builder' THEN 'Service'
            ELSE 'Unknown'
        END AS layer
    ORDER BY depth ASC
"""

# Get upstream call chain (who calls this method)
GET_UPSTREAM_CALL_CHAIN = """
    MATCH (target {entityId: $methodId})

    // Traverse upstream callers
    OPTIONAL MATCH path = (caller)-[:CALLS|INVOKES|HAS_METHOD*1..$maxDepth]->(target)

    WITH target, path, caller,
         length(path) AS depth,
         [rel IN relationships(path) | {
             type: type(rel),
             lineNumber: rel.lineNumber
         }] AS relationships

    // Get caller details
    OPTIONAL MATCH (parent)-[:HAS_METHOD]->(caller)

    RETURN DISTINCT
        caller.entityId AS nodeId,
        caller.name AS name,
        labels(caller)[0] AS type,
        caller.filePath AS filePath,
        caller.startLine AS startLine,
        caller.endLine AS endLine,
        COALESCE(caller.signature, '') AS signature,
        parent.name AS parentClass,
        depth,
        relationships[0].lineNumber AS callsAtLine,
        CASE
            WHEN 'JSPPage' IN labels(caller) THEN 'UI'
            WHEN 'WebFlowDefinition' IN labels(caller) THEN 'Flow'
            WHEN toLower(caller.name) ENDS WITH 'action' THEN 'Controller'
            WHEN toLower(COALESCE(parent.name, caller.name)) CONTAINS 'dao' THEN 'DAO'
            WHEN toLower(COALESCE(parent.name, caller.name)) CONTAINS 'service' THEN 'Service'
            ELSE 'Unknown'
        END AS layer
    ORDER BY depth ASC
"""

# Get data flow mapping: FormField -> EntityField -> SQLColumn
GET_DATA_FLOW_MAPPING = """
    // Start from form field binding
    MATCH (binding:FormFieldBinding)
    WHERE binding.fieldPath CONTAINS $fieldName
       OR binding.fieldName = $fieldName

    // Get parent JSP
    OPTIONAL MATCH (jsp:JSPPage)-[:HAS_FIELD_BINDING]->(binding)

    // Find entity field via BINDS_TO
    OPTIONAL MATCH (binding)-[:BINDS_TO]->(entityField:JavaField)
    OPTIONAL MATCH (entityClass)-[:HAS_FIELD]->(entityField)

    // Find related SQL columns (by field name matching)
    OPTIONAL MATCH (sql:SQLStatement)
    WHERE toLower(sql.columns) CONTAINS toLower(binding.fieldName)

    RETURN DISTINCT
        binding.fieldPath AS uiField,
        binding.inputType AS inputType,
        binding.required AS isRequired,
        binding.validationAttributes AS validationRules,
        binding.lineNumber AS uiLine,
        jsp.name AS uiComponent,
        entityField.name AS entityField,
        entityField.fieldType AS fieldType,
        entityClass.name AS entityClass,
        sql.tableName AS dbTable,
        binding.fieldName AS inferredColumn
"""

# Get SQL operations for a DAO class
GET_SQL_FOR_DAO = """
    MATCH (dao)
    WHERE dao.entityId = $daoId
       OR dao.name = $daoName

    OPTIONAL MATCH (dao)-[:HAS_METHOD]->(method:JavaMethod)
    OPTIONAL MATCH (method)-[:EXECUTES_SQL]->(sql:SQLStatement)

    RETURN DISTINCT
        method.name AS methodName,
        method.signature AS methodSignature,
        method.startLine AS methodStartLine,
        method.endLine AS methodEndLine,
        sql.statementType AS statementType,
        sql.tableName AS tableName,
        sql.columns AS columns,
        sql.rawSql AS rawSql,
        sql.lineNumber AS sqlLineNumber
    ORDER BY method.startLine
"""

# Find entry points for a feature keyword
FIND_ENTRY_POINTS = """
    // Find JSP pages matching feature name
    MATCH (jsp:JSPPage)
    WHERE toLower(jsp.name) CONTAINS toLower($keyword)
       OR toLower(jsp.filePath) CONTAINS toLower($keyword)

    RETURN DISTINCT
        jsp.entityId AS entryId,
        jsp.name AS name,
        jsp.filePath AS path,
        'JSPPage' AS type,
        'UI' AS layer,
        100 AS score

    UNION

    // Find WebFlows matching feature name
    MATCH (flow:WebFlowDefinition)
    WHERE toLower(flow.name) CONTAINS toLower($keyword)

    RETURN DISTINCT
        flow.entityId AS entryId,
        flow.name AS name,
        flow.filePath AS path,
        'WebFlowDefinition' AS type,
        'Flow' AS layer,
        90 AS score

    UNION

    // Find Controllers/Actions matching feature name
    MATCH (ctrl)
    WHERE (ctrl:JavaClass OR ctrl:SpringController)
      AND (toLower(ctrl.name) ENDS WITH 'action' OR toLower(ctrl.name) ENDS WITH 'controller')
      AND toLower(ctrl.name) CONTAINS toLower($keyword)

    RETURN DISTINCT
        ctrl.entityId AS entryId,
        ctrl.name AS name,
        ctrl.filePath AS path,
        labels(ctrl)[0] AS type,
        'Controller' AS layer,
        80 AS score

    ORDER BY score DESC
    LIMIT 20
"""

# Get form field bindings for a JSP page
GET_FORM_BINDINGS = """
    MATCH (jsp:JSPPage {entityId: $jspId})
    OPTIONAL MATCH (jsp)-[:HAS_FIELD_BINDING]->(binding:FormFieldBinding)

    RETURN
        binding.fieldPath AS fieldPath,
        binding.fieldName AS fieldName,
        binding.modelAttribute AS modelAttribute,
        binding.inputType AS inputType,
        binding.required AS required,
        binding.validationAttributes AS validationAttributes,
        binding.lineNumber AS lineNumber
    ORDER BY binding.lineNumber
"""

# Create full feature trace from JSP to database
TRACE_JSP_TO_DATABASE = """
    // Match JSP entry point
    MATCH (jsp:JSPPage)
    WHERE jsp.entityId = $jspId
       OR jsp.name = $jspName
       OR jsp.filePath CONTAINS $jspPath

    // Get form bindings first
    OPTIONAL MATCH (jsp)-[:HAS_FIELD_BINDING]->(binding:FormFieldBinding)
    WITH jsp, collect(DISTINCT {path: binding.fieldPath, type: binding.inputType, required: binding.required}) AS bindings

    // Get WebFlow that renders this JSP
    OPTIONAL MATCH (flow:WebFlowDefinition)-[:FLOW_RENDERS_VIEW]->(jsp)
    WITH jsp, bindings, collect(DISTINCT flow) AS flows

    // Get first flow for further traversal
    WITH jsp, bindings, flows, CASE WHEN size(flows) > 0 THEN flows[0] ELSE null END AS flow

    // Get actions executed by flow states
    OPTIONAL MATCH (flow)-[:HAS_ACTION_STATE|FLOW_DEFINES_STATE*1..2]->(state)
    OPTIONAL MATCH (state)-[:FLOW_EXECUTES_ACTION]->(action:FlowAction)
    WITH jsp, bindings, flow, collect(DISTINCT state.name) AS stateNames, collect(DISTINCT action) AS actions

    // Get controller methods from action expressions
    UNWIND CASE WHEN size(actions) > 0 THEN actions ELSE [null] END AS action
    OPTIONAL MATCH (controllerClass)-[:HAS_METHOD]->(controllerMethod:JavaMethod)
    WHERE action IS NOT NULL AND (controllerMethod.name CONTAINS action.actionName OR controllerMethod.entityId = action.entityId)
    WITH jsp, bindings, flow, stateNames, collect(DISTINCT {ctrl: controllerClass, method: controllerMethod}) AS ctrlData

    // Extract first controller
    WITH jsp, bindings, flow, stateNames,
         CASE WHEN size(ctrlData) > 0 THEN ctrlData[0].ctrl ELSE null END AS controllerClass,
         CASE WHEN size(ctrlData) > 0 THEN ctrlData[0].method ELSE null END AS controllerMethod

    // Follow invocations from controller to service
    OPTIONAL MATCH (controllerMethod)-[:INVOKES]->(invocation:MethodInvocation)
    OPTIONAL MATCH (serviceClass)-[:HAS_METHOD]->(serviceMethod:JavaMethod)
    WHERE serviceMethod.name = invocation.methodName
    WITH jsp, bindings, flow, stateNames, controllerClass, controllerMethod,
         collect(DISTINCT {svc: serviceClass, method: serviceMethod}) AS svcData

    // Extract first service
    WITH jsp, bindings, flow, stateNames, controllerClass, controllerMethod,
         CASE WHEN size(svcData) > 0 THEN svcData[0].svc ELSE null END AS serviceClass,
         CASE WHEN size(svcData) > 0 THEN svcData[0].method ELSE null END AS serviceMethod

    // Follow invocations from service to DAO
    OPTIONAL MATCH (serviceMethod)-[:INVOKES]->(daoInvocation:MethodInvocation)
    OPTIONAL MATCH (daoClass)-[:HAS_METHOD]->(daoMethod:JavaMethod)
    WHERE daoMethod.name = daoInvocation.methodName
      AND (toLower(daoClass.name) CONTAINS 'dao' OR toLower(daoClass.name) CONTAINS 'repository')
    WITH jsp, bindings, flow, stateNames, controllerClass, controllerMethod, serviceClass, serviceMethod,
         collect(DISTINCT {dao: daoClass, method: daoMethod}) AS daoData

    // Extract first DAO
    WITH jsp, bindings, flow, stateNames, controllerClass, controllerMethod, serviceClass, serviceMethod,
         CASE WHEN size(daoData) > 0 THEN daoData[0].dao ELSE null END AS daoClass,
         CASE WHEN size(daoData) > 0 THEN daoData[0].method ELSE null END AS daoMethod

    // Get SQL from DAO
    OPTIONAL MATCH (daoMethod)-[:EXECUTES_SQL]->(sql:SQLStatement)
    WITH jsp, bindings, flow, stateNames, controllerClass, controllerMethod, serviceClass, serviceMethod, daoClass, daoMethod,
         collect(DISTINCT sql) AS sqlNodes

    // Return all layers with proper structure
    RETURN
        // UI Layer
        {
            name: jsp.name,
            path: jsp.filePath,
            line: 1,
            type: 'JSPPage',
            bindings: bindings
        } AS uiLayer,

        // Flow Layer
        {
            name: flow.name,
            path: flow.filePath,
            states: stateNames
        } AS flowLayer,

        // Controller Layer
        {
            class: controllerClass.name,
            method: controllerMethod.name,
            signature: controllerMethod.signature,
            path: controllerClass.filePath,
            startLine: controllerMethod.startLine,
            endLine: controllerMethod.endLine
        } AS controllerLayer,

        // Service Layer
        {
            class: serviceClass.name,
            method: serviceMethod.name,
            signature: serviceMethod.signature,
            path: serviceClass.filePath,
            startLine: serviceMethod.startLine,
            endLine: serviceMethod.endLine
        } AS serviceLayer,

        // DAO Layer
        {
            class: daoClass.name,
            method: daoMethod.name,
            path: daoClass.filePath,
            startLine: daoMethod.startLine,
            endLine: daoMethod.endLine
        } AS daoLayer,

        // Database Layer
        CASE WHEN size(sqlNodes) > 0 THEN {
            statementType: sqlNodes[0].statementType,
            tableName: sqlNodes[0].tableName,
            columns: sqlNodes[0].columns,
            rawSql: sqlNodes[0].rawSql
        } ELSE null END AS databaseLayer
"""

# Generate mermaid sequence diagram data
GET_SEQUENCE_DIAGRAM_DATA = """
    MATCH (entry {entityId: $entryPointId})

    // Collect all steps in order
    OPTIONAL MATCH path = (entry)-[:CALLS|INVOKES|HAS_METHOD|FLOW_EXECUTES_ACTION|EXECUTES_SQL*1..10]->(target)

    WITH entry, path, target,
         length(path) AS depth,
         [node IN nodes(path) |
             CASE
                 WHEN 'JSPPage' IN labels(node) THEN 'UI'
                 WHEN 'WebFlowDefinition' IN labels(node) THEN 'Flow'
                 WHEN toLower(node.name) ENDS WITH 'action' THEN 'Controller'
                 WHEN toLower(node.name) CONTAINS 'service' THEN 'Service'
                 WHEN toLower(node.name) CONTAINS 'dao' THEN 'DAO'
                 WHEN 'SQLStatement' IN labels(node) THEN 'Database'
                 ELSE 'Unknown'
             END
         ] AS layers,
         [node IN nodes(path) | node.name] AS names,
         [rel IN relationships(path) | type(rel)] AS relationships

    RETURN
        names,
        layers,
        relationships,
        depth
    ORDER BY depth
"""

# Get business rules and validations associated with a component
GET_BUSINESS_RULES_FOR_COMPONENT = """
    // Find component by entityId or name
    MATCH (comp)
    WHERE comp.entityId = $componentId
       OR comp.name = $componentName

    // Get associated business rules
    OPTIONAL MATCH (comp)-[:HAS_BUSINESS_RULE|ENFORCES_RULE|HAS_VALIDATION]->(rule:BusinessRule)

    // Get validation annotations from fields
    OPTIONAL MATCH (comp)-[:HAS_METHOD]->(method:JavaMethod)
    OPTIONAL MATCH (method)-[:HAS_VALIDATION]->(valRule:BusinessRule)

    // Get validation annotations from entity fields
    OPTIONAL MATCH (comp)-[:HAS_FIELD]->(field:JavaField)
    WHERE field.validationAnnotations IS NOT NULL

    RETURN DISTINCT
        comp.name AS componentName,
        labels(comp)[0] AS componentType,
        collect(DISTINCT {
            ruleName: rule.ruleName,
            ruleType: rule.ruleType,
            description: rule.description,
            sourceMethod: rule.sourceMethod,
            lineNumber: rule.lineNumber
        }) AS businessRules,
        collect(DISTINCT {
            methodName: method.name,
            ruleName: valRule.ruleName,
            ruleType: valRule.ruleType
        }) AS methodValidations,
        collect(DISTINCT {
            fieldName: field.name,
            validations: field.validationAnnotations
        }) AS fieldValidations
"""

# Get validation annotations for entity fields
GET_ENTITY_VALIDATIONS = """
    MATCH (entity)
    WHERE entity.entityId = $entityId
       OR entity.name = $entityName

    // Get fields with validation annotations
    OPTIONAL MATCH (entity)-[:HAS_FIELD]->(field:JavaField)
    WHERE field.validationAnnotations IS NOT NULL
       OR field.annotations IS NOT NULL

    RETURN
        entity.name AS entityName,
        entity.filePath AS entityPath,
        collect({
            fieldName: field.name,
            fieldType: field.fieldType,
            validationAnnotations: COALESCE(field.validationAnnotations, []),
            annotations: COALESCE(field.annotations, []),
            isRequired: field.isRequired
        }) AS fields
"""

# Get data model information for entity classes
GET_DATA_MODEL_INFO = """
    // Find entity classes by name pattern
    MATCH (entity:JavaClass)
    WHERE entity.name CONTAINS $entityPattern
       OR entity.annotations CONTAINS '@Entity'
       OR entity.annotations CONTAINS '@Table'

    // Get fields with types and annotations
    OPTIONAL MATCH (entity)-[:HAS_FIELD]->(field:JavaField)

    // Get relationships to other entities
    OPTIONAL MATCH (entity)-[rel:REFERENCES|HAS_RELATIONSHIP|ONE_TO_MANY|MANY_TO_ONE|MANY_TO_MANY]->(relatedEntity)

    RETURN
        entity.name AS entityName,
        entity.filePath AS entityPath,
        entity.annotations AS entityAnnotations,
        collect(DISTINCT {
            name: field.name,
            type: field.fieldType,
            annotations: field.annotations,
            validationAnnotations: field.validationAnnotations
        }) AS fields,
        collect(DISTINCT {
            relationshipType: type(rel),
            relatedEntity: relatedEntity.name
        }) AS relationships
    LIMIT 20
"""
