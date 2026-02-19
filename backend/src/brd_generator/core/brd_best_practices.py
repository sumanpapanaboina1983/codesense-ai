"""BRD Best Practices and Default Configuration.

This module contains the best practices, writing guidelines, and default
section configuration for Business Requirements Documents (BRDs).
"""

# =============================================================================
# BRD Best Practices - System Prompt Content
# =============================================================================

BRD_BEST_PRACTICES = """
## BRD Best Practices Guide

### Purpose
Create Business Requirements Documents that are:
- Clear and understandable to NON-TECHNICAL business stakeholders
- Detailed enough for accurate system design and implementation
- Usable by AI development tools to generate aligned code

### Writing Guidelines

| Practice | Guideline |
|----------|-----------|
| Use plain English | Avoid code or technical jargon unless business-relevant |
| Be deterministic | Avoid vague phrases like "maybe" or "usually"; describe exact behavior |
| Write for business readers | Assume the reader is a product manager, BA, or executive |
| Explain "what" not "how" | Describe outcomes and behavior, not implementation details |
| Capture all business rules | Every condition in code should be expressed in business terms |
| Use numbered lists for flows | Improves traceability and readability |
| Include visual diagrams | Sequence diagrams help clarify complex flows |

### Common Pitfalls to Avoid

| Pitfall | Fix |
|---------|-----|
| Mixing UI behavior with logic | Only include UI if it drives a functional requirement |
| Using terms like "method" or "API" | Replace with "action," "service," or "system interaction" |
| Skipping edge cases | Always ask: "What if this input is missing, invalid, or late?" |
| Over-generalizing | Be precise. Instead of "system may notify," say "system must..." |
"""

# =============================================================================
# Default BRD Sections with Descriptions
# =============================================================================

DEFAULT_BRD_SECTIONS = [
    {
        "name": "Feature Overview",
        "description": """A plain English summary of what the feature enables from a business standpoint.
Should answer: What problem does this solve? Who benefits?
Example: "This feature enables registered users to request a statement of all wire transfers
made in the last 12 months. It improves self-service transparency and reduces call center load." """,
        "required": True,
    },
    {
        "name": "Functional Requirements",
        "description": """Describe what the system must do in terms of BUSINESS BEHAVIOR.
Use simple, active statements (e.g., "The system must notify the customer...")
Group similar requirements under subheadings if needed (e.g., "Data Entry", "Review and Approval")
Format: Bullet points with "The system must..." or "Users must be able to..." """,
        "required": True,
    },
    {
        "name": "Business Validations and Rules",
        "description": """Capture ALL logic constraints, typically enforced via conditional checks in code.
Explain what is ALLOWED, REQUIRED, or BLOCKED, in business terms.
Examples:
- Transfer amount must be less than $50,000 unless user has verified identity.
- Users with "suspended" status cannot initiate transfers.
- Orders can only be placed between 6:00 AM and 10:00 PM local time.""",
        "required": True,
    },
    {
        "name": "Actors and System Interactions",
        "description": """List ALL user roles or systems that interact with this functionality.
Use friendly, business-facing terms like "Customer," "Back Office User," "KYC API," etc.
Format as a table:
| Actor | Role in Process |
| Customer | Initiates the request |
| Fraud Detection API | Performs real-time risk analysis |""",
        "required": True,
    },
    {
        "name": "Business Process Flow",
        "description": """Describe step-by-step how the feature works from initiation to resolution.
Use NUMBERED LISTS for linear flows and "if...then..." for conditionals.
Example:
1. Customer logs in and selects "Transfer Funds."
2. System displays transfer form.
3. Customer enters amount, recipient, and purpose.
4. If amount > $10,000, system triggers enhanced validation.
5. Upon confirmation, system creates the request and sends notification.""",
        "required": True,
    },
    {
        "name": "Sequence Diagram",
        "description": """Use Mermaid syntax to visualize component-level interactions.
Focus on BUSINESS-RELEVANT systems and flow, not technical layers.
Example:
```mermaid
sequenceDiagram
    participant Customer
    participant App
    participant ValidationService
    Customer->>App: Submit Request
    App->>ValidationService: Validate
    ValidationService-->>App: Result
    App-->>Customer: Confirmation
```""",
        "required": False,
    },
    {
        "name": "Technical Architecture",
        "description": """Document the complete end-to-end technical flow from UI to database.
This section provides FULL TRACEABILITY for architects, developers, and QA teams.

**Required content:**

1. **Data Flow Visualization**: Show the path UI → Flow → Controller → Service → DAO → Database

2. **UI Layer (Entry Point)**:
   - JSP/HTML files handling user input
   - Form fields and their input types
   - Client-side validations
   - File path and line numbers

3. **Flow/Navigation Layer** (if applicable):
   - WebFlow definitions or navigation rules
   - State transitions and conditions
   - View-to-action mappings

4. **Controller Layer (Request Processing)**:
   - Action/Controller class name
   - Method handling the request
   - Method signature with parameters
   - File path and line numbers (e.g., lines 234-267)
   - Request validations performed

5. **Service Layer (Business Logic)**:
   - Service/Builder/Validator classes
   - Business logic methods with signatures
   - Business rules applied (list each rule)
   - Data transformations performed
   - File path and line numbers

6. **Data Access Layer (Persistence)**:
   - DAO/Repository class name
   - Persistence methods (persist, update, delete, find)
   - File path and line numbers

7. **Database Layer**:
   - SQL operations (INSERT, UPDATE, SELECT, DELETE)
   - Table names and affected columns
   - Database constraints (PK, FK, UNIQUE, NOT NULL)

8. **Field-Level Data Mapping** (table showing):
   | UI Field | Entity Property | DB Column | Data Type | Required | Validations |

This section is AUTO-GENERATED from code graph traversal when available.
LLM should preserve auto-generated content and enhance with additional context.""",
        "required": False,
    },
    {
        "name": "Implementation Mapping",
        "description": """Provide comprehensive tabular mapping of operations to implementation components.
This section enables IMPACT ANALYSIS and ESTIMATION for development teams.

**Required tables:**

1. **Operation-to-Implementation Mapping**:
   Maps each business operation to implementing code at each architectural layer.

   | Operation | UI | Controller | Service | DAO | Database |
   |-----------|-----|------------|---------|-----|----------|
   | Save Entity | Form.jsp:45 | saveAction():234 | build():45 | persist():123 | INSERT table |
   | Validate Entity | - | validate():189 | validator():78 | - | SELECT table |

   Format: `ClassName.methodName():lineNumber` or `filename:lineNumber`

2. **Field-Level Data Mapping**:
   Traces each data field from UI through all layers to database.

   | Field | UI Location | Entity Property | DB Column | Validations | Required |
   |-------|-------------|-----------------|-----------|-------------|----------|
   | entityName | Form.jsp:45 | LegalEntity.name | entity_name | @NotNull, @Size | Yes |
   | taxId | Form.jsp:52 | LegalEntity.taxId | tax_id | @Pattern | Yes |

3. **Validation Checkpoints** (where each business rule is enforced):

   | Layer | Component | Validation Rule | Line |
   |-------|-----------|-----------------|------|
   | Controller | EntityAction.validate() | Required fields check | 189 |
   | Service | EntityValidator.validateTaxId() | Tax ID format validation | 78 |

**Legend:**
- Format for code references: `ClassName.methodName():lineNumber`
- UI references: `filename:lineNumber`
- Database operations: `OPERATION tableName`

This section is AUTO-GENERATED from code graph traversal when available.
LLM should preserve auto-generated mappings and add any missing operations discovered from code analysis.""",
        "required": False,
    },
    {
        "name": "Data Model",
        "description": """Document the data entities and their relationships involved in this feature.

**Required content:**

1. **Entity Classes**:
   For each entity involved:
   - Entity class name and file path
   - Key fields with data types
   - Validation annotations (@NotNull, @Size, @Pattern, etc.)
   - Relationships to other entities (OneToMany, ManyToOne, etc.)

2. **Database Tables**:
   | Table | Column | Type | Constraints | Description |
   |-------|--------|------|-------------|-------------|
   | les_legal_entity | entity_id | NUMBER | PK | Primary key |
   | les_legal_entity | entity_name | VARCHAR(100) | NOT NULL | Entity display name |
   | les_legal_entity | tax_id | VARCHAR(20) | UNIQUE | Tax identification |

3. **Entity Relationships** (if applicable):
   ```
   LegalEntity (1) --- (N) Address
   LegalEntity (N) --- (N) Contact
   ```

4. **Audit Fields** (if applicable):
   - created_date, created_by
   - updated_date, updated_by
   - version (optimistic locking)

This section helps developers understand the data structures and QA teams design test data.""",
        "required": False,
    },
    {
        "name": "Assumptions and Constraints",
        "description": """State conditions assumed by the system and any limitations.
Helps developers and testers align with edge-case behavior.
Examples:
- Assumes customer is already registered and verified.
- Applies only to domestic transactions; cross-border excluded.
- Does not apply to mobile app users (web only).""",
        "required": True,
    },
    {
        "name": "Acceptance Criteria",
        "description": """List business-facing pass/fail conditions for the feature to be considered complete.
Make them MEASURABLE and ACTIONABLE.
Examples:
- Users must receive email confirmation within 1 minute of submission.
- High-risk transactions must trigger manual review 100% of the time.
- "No results found" page must include retry option.""",
        "required": True,
    },
]

# Section names only (for backward compatibility)
DEFAULT_SECTION_NAMES = [s["name"] for s in DEFAULT_BRD_SECTIONS]

# =============================================================================
# Section Writing Guidelines (for prompts)
# =============================================================================

def get_section_guidelines(section_name: str) -> str:
    """Get writing guidelines for a specific BRD section."""

    # Find section in defaults
    for section in DEFAULT_BRD_SECTIONS:
        if section["name"].lower().replace(" ", "_") == section_name.lower().replace(" ", "_"):
            return section["description"]
        # Also match by simple name comparison
        if section["name"].lower() == section_name.lower().replace("_", " "):
            return section["description"]

    # Fallback guidelines for custom sections
    return f"""Document this section thoroughly:
- Use clear, business-focused language
- Be specific and deterministic (avoid "may" or "might")
- Include concrete examples where helpful
- Capture all relevant business rules and constraints"""


def get_full_section_prompt(section_name: str, custom_description: str = None) -> str:
    """Get full section prompt including best practices."""

    description = custom_description or get_section_guidelines(section_name)

    return f"""## Section: {section_name}

### Section Guidelines
{description}

### Writing Best Practices
- Use plain English - avoid technical jargon
- Be deterministic - avoid vague phrases like "maybe" or "usually"
- Write for business readers - assume non-technical audience
- Explain "what" not "how" - describe outcomes, not implementation
- Use numbered lists for process flows
- Capture all business rules and constraints
"""


def build_brd_system_prompt(detail_level: str = "standard") -> str:
    """Build the full BRD system prompt with best practices."""

    detail_instructions = {
        "concise": "Keep sections brief (1-2 paragraphs). Use bullet points. Focus on key points only.",
        "standard": "Provide balanced coverage (2-4 paragraphs per section). Mix prose and bullets.",
        "detailed": "Provide comprehensive coverage with full explanations, examples, and edge cases.",
    }

    return f"""You are an expert Business Analyst creating a Business Requirements Document (BRD).

{BRD_BEST_PRACTICES}

## Output Detail Level: {detail_level.upper()}
{detail_instructions.get(detail_level, detail_instructions["standard"])}

## Required BRD Structure
Your BRD must include these sections in order:

1. **Feature Overview** - Plain English summary of what the feature enables
2. **Functional Requirements** - What the system must do (business behavior)
3. **Business Validations and Rules** - All logic constraints in business terms
4. **Actors and System Interactions** - User roles and systems involved
5. **Business Process Flow** - Step-by-step flow with numbered lists
6. **Sequence Diagram** - Mermaid diagram of interactions (if complex)
7. **Technical Architecture** - End-to-end flow from UI to database with file paths/line numbers (AUTO-GENERATED when available)
8. **Data Model** - Entity classes, database tables, and relationships
9. **Implementation Mapping** - Tabular mapping of operations to code (AUTO-GENERATED when available)
10. **Assumptions and Constraints** - Conditions assumed and limitations
11. **Acceptance Criteria** - Measurable pass/fail conditions

## Special Instructions for Technical Sections (7, 8, 9)
When auto-generated content is provided for Technical Architecture and Implementation Mapping:
- PRESERVE the auto-generated file paths, line numbers, and component mappings
- ENHANCE with additional context discovered from code analysis
- These sections provide TRACEABILITY for developers and QA teams

Remember: Write for BUSINESS readers, not developers. Focus on WHAT, not HOW.
"""


def build_reverse_engineering_prompt(feature_description: str, detail_level: str = "standard") -> str:
    """Build prompt for reverse engineering existing code into a BRD."""

    base_prompt = build_brd_system_prompt(detail_level)

    return f"""{base_prompt}

## CRITICAL: REVERSE ENGINEERING MODE

You are reverse engineering EXISTING code to create a BRD. The feature "{feature_description}" ALREADY EXISTS.

Your task is to:
1. ANALYZE the existing implementation from the provided context
2. DOCUMENT what the code currently does in business terms
3. EXTRACT business rules from the actual code behavior
4. DESCRIBE the existing flow, not propose new development

DO NOT:
- Propose new features or enhancements
- Write requirements for things that don't exist in the code
- Make assumptions without evidence from the code
- Use technical jargon - translate code behavior to business language

All claims must be backed by actual code found in the analysis.
"""
