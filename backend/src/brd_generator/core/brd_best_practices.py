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
- Comprehensive in capturing ALL business logic and rules from the code
- Written in plain English without ANY code references (no class names, method names, file paths, or line numbers)

### Critical: Extract ALL Business Logic
You must thoroughly extract and document:
- **Every validation rule**: What inputs are checked? What makes them valid/invalid?
- **Every business constraint**: What limits exist? What conditions must be met?
- **Every conditional behavior**: What happens when X? What happens when Y?
- **Every data transformation**: How is data processed, converted, or calculated?
- **Every state transition**: What causes status changes? What are the allowed states?
- **Every error condition**: What can go wrong? How does the system respond?
- **Every default behavior**: What happens when no input is provided? What are the default values?

### Writing Guidelines

| Practice | Guideline |
|----------|-----------|
| Use plain English | NEVER mention class names, methods, file paths, or technical terms |
| Be exhaustive | Extract EVERY business rule found in code - don't summarize or skip |
| Be deterministic | Avoid vague phrases like "maybe" or "usually"; describe exact behavior |
| Write for business readers | Assume the reader is a product manager, BA, or executive |
| Explain "what" not "how" | Describe outcomes and behavior, not implementation details |
| Capture all business rules | Every condition in code should be expressed in business terms |
| Use numbered lists for flows | Improves traceability and readability |
| Include visual diagrams | Sequence diagrams help clarify complex flows |

### Translating Code to Business Language

| Code Concept | Business Language |
|--------------|-------------------|
| if (amount > 10000) | "When the amount exceeds $10,000..." |
| validateNotNull(field) | "The [field name] is required and cannot be left blank" |
| status == "ACTIVE" | "Only records with active status..." |
| list.size() > maxResults | "When the number of results exceeds the maximum allowed..." |
| toUpperCase() | "The system converts the input to uppercase for consistent matching" |
| trim() | "The system removes leading and trailing spaces from the input" |

### Common Pitfalls to Avoid

| Pitfall | Fix |
|---------|-----|
| Mentioning code references | Replace "UserValidator.validate()" with "The system validates user information" |
| Skipping validation rules | Document EVERY validation - field requirements, formats, ranges |
| Missing edge cases | Always ask: "What if this input is missing, invalid, or at boundary values?" |
| Over-generalizing | Be precise. Instead of "system may notify," say "system must..." |
| Incomplete rule extraction | If code has 10 validation rules, document all 10 in business terms |
"""

# =============================================================================
# Default BRD Sections with Descriptions
# =============================================================================

DEFAULT_BRD_SECTIONS = [
    {
        "name": "Feature Overview",
        "description": """A plain English summary of what the feature enables from a business standpoint.
Should answer: What problem does this solve? Who benefits? How does it work at a high level?

This section should:
- Explain the business problem being solved
- Identify who benefits from this feature (user groups, departments)
- Describe key capabilities in business terms
- Explain how it fits into broader business processes

Write in clear, accessible prose that any stakeholder can understand.
Avoid technical jargon - focus on business value and user outcomes.""",
        "required": True,
    },
    {
        "name": "Functional Requirements",
        "description": """Document EVERYTHING the system does in terms of BUSINESS BEHAVIOR.
Extract ALL capabilities from the code and describe them in plain English.

**IMPORTANT**: Be comprehensive. Document every feature, every capability, every user action supported.

Group requirements under clear subheadings:

**Core Capabilities**
- What are the primary functions of this feature?
- What different methods/options does it provide to accomplish the goal?
- What are all the ways users can interact with this feature?

**Data Entry and Input**
- What inputs does the system accept?
- What fields are available for user entry?
- How does the system help users enter data (auto-focus, defaults, enabling/disabling fields)?

**Search/Query Features** (if applicable)
- What search methods are available?
- How does each search method work from a user perspective?
- What filtering options exist?

**Results Display**
- How are results presented to users?
- What information is shown for each result?
- What actions can users take on results (sort, export, select)?

**User Experience Features**
- What feedback does the system provide (loading indicators, messages)?
- How does the system handle errors or edge cases?
- What keyboard shortcuts or convenience features exist?

Format each requirement as:
- "The system must [action]..."
- "Users must be able to [capability]..."
- "When [condition], the system must [behavior]..."

NEVER mention code references - describe only what users see and experience.""",
        "required": True,
    },
    {
        "name": "Business Validations and Rules",
        "description": """This is the MOST CRITICAL section. Extract and document EVERY business rule and validation from the code.

**IMPORTANT**: Be EXHAUSTIVE. If the code has 20 validation rules, document all 20. Do not summarize or skip any rules.

Organize into logical categories:

**Input Validation Rules**
- Required fields: Which fields must be provided?
- Format requirements: What formats are accepted (length limits, character types, numeric ranges)?
- Conditional requirements: Which fields are required based on other selections?
- Data transformations: How does the system process input before use (uppercase conversion, trimming, etc.)?

**Search/Query Execution Rules**
- How does each search type work?
- What comparisons are performed (exact match, starts with, contains, range)?
- Is matching case-sensitive or case-insensitive?
- How are special characters or spaces handled?

**Status and Filtering Rules**
- What status values exist and what do they mean?
- How does status filtering work?
- What is the default filter behavior?
- How are active/inactive records determined?

**Result Set Management Rules**
- Are there limits on how many results can be returned?
- What happens when limits are exceeded?
- How are results sorted by default?
- Can users change the sort order?

**Selection and Navigation Rules**
- What happens when a user selects a record?
- Are there different behaviors in different contexts (standalone vs popup)?
- What information is passed between screens?

For EACH rule, explain in plain English:
- What the rule is (the business constraint)
- When it applies (the condition)
- What happens (the outcome or error)

NEVER mention code references - translate everything to business language.""",
        "required": True,
    },
    {
        "name": "Actors and System Interactions",
        "description": """List ALL user roles or systems that interact with this functionality.
Use friendly, business-facing terms like "Customer," "Back Office User," "Validation Service," etc.

Format as a table:
| Actor / System | Role in Process |
|----------------|-----------------|
| Customer | Initiates the request |
| Validation Service | Performs real-time checks |
| Agent | Approves flagged requests |

Include both human actors AND system components that participate in the process.
Briefly explain what each actor does and why they're involved.""",
        "required": True,
    },
    {
        "name": "Business Process Flow",
        "description": """Describe step-by-step how the feature works from initiation to resolution.
Use NUMBERED LISTS for linear flows and "if...then..." for conditionals.

If there are multiple modes or paths, document each separately:
- **Mode 1 (e.g., Standalone Mode)**
  1. Step one...
  2. Step two...

- **Mode 2 (e.g., Modal/Popup Mode)**
  1. Step one...
  2. Step two...

Include decision points clearly:
- "If [condition], then [action]"
- "When [event occurs], the system [response]"

End each flow with the final outcome or resolution.""",
        "required": True,
    },
    {
        "name": "Sequence Diagram",
        "description": """Use Mermaid syntax to visualize the interactions between actors and systems.
Focus on BUSINESS-RELEVANT systems and flow, not technical implementation layers.

Show the key participants and message flows that matter to stakeholders.
Include decision points (alt blocks) for important conditional flows.

Example:
```mermaid
sequenceDiagram
    participant User
    participant SearchScreen
    participant ValidationService
    participant Database

    User->>SearchScreen: Enter search criteria
    SearchScreen->>ValidationService: Validate input
    ValidationService-->>SearchScreen: Validation result
    SearchScreen->>Database: Execute search
    Database-->>SearchScreen: Return results
    SearchScreen-->>User: Display results
```""",
        "required": False,
    },
    {
        "name": "Assumptions and Constraints",
        "description": """Document the conditions assumed by the system and any limitations.

**Assumptions**: What must be true for the feature to work correctly?
- User authentication and authorization assumptions
- Data integrity assumptions
- Integration assumptions

**Constraints**: What are the boundaries or limitations?
- Input field limits (character counts, numeric ranges)
- Result set limits
- Feature scope boundaries (what's NOT included)
- Platform/channel constraints (web only, mobile excluded, etc.)

Be specific - these help developers understand edge cases and testers design test scenarios.""",
        "required": True,
    },
    {
        "name": "Acceptance Criteria",
        "description": """List business-facing pass/fail conditions for the feature to be considered complete.
Make them MEASURABLE and ACTIONABLE.

Organize by functional area:
- **Search Functionality**: What search behaviors must work correctly?
- **Validation**: What validation behaviors must be enforced?
- **Display/Results**: What display behaviors must be correct?
- **User Experience**: What UX requirements must be met?

Format each criterion as a testable statement:
- "When [action], the system must [expected behavior]"
- "Given [condition], then [expected outcome]"

Example:
- When a user enters "NAT" in the name search, the system must return all entities whose names start with "NAT" (case-insensitive).
- When results exceed the maximum limit, the system must display a warning message.""",
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
        "standard": "Provide balanced coverage. Use clear prose with bullet points where appropriate. Be thorough but not verbose.",
        "detailed": "Provide comprehensive coverage with full explanations, examples, and edge cases.",
    }

    return f"""You are an expert Business Analyst creating a Business Requirements Document (BRD).

{BRD_BEST_PRACTICES}

## Output Detail Level: {detail_level.upper()}
{detail_instructions.get(detail_level, detail_instructions["standard"])}

## Required BRD Structure
Your BRD must include these sections in order:

1. **Feature Overview** - Plain English summary of what the feature enables, the problem it solves, and who benefits
2. **Functional Requirements** - What the system must do in terms of business behavior, grouped by capability area
3. **Business Validations and Rules** - All logic constraints and business rules in plain business terms
4. **Actors and System Interactions** - User roles and systems involved, formatted as a table
5. **Business Process Flow** - Step-by-step flow with numbered lists, covering all modes/paths
6. **Sequence Diagram** - Mermaid diagram showing interactions between actors and systems
7. **Assumptions and Constraints** - Conditions assumed and limitations of the feature
8. **Acceptance Criteria** - Measurable pass/fail conditions organized by functional area

## Writing Style Guidelines
- Write in clear, accessible prose that any business stakeholder can understand
- Use subheadings to organize content within sections
- Use tables for structured data (actors, field mappings, etc.)
- Use numbered lists for sequential processes
- Use bullet points for requirements and rules
- Be specific and deterministic - avoid "may", "might", "usually"
- Every claim should be based on actual system behavior

## Critical: No Code References
NEVER include in your output:
- Class names, method names, or variable names
- File paths or line numbers
- Technical terms like "DAO", "entity", "controller", "service"
- Code syntax or pseudo-code

ALWAYS translate to business language:
- "UserValidator.validateName()" → "The system validates the user name"
- "if (amount > 10000)" → "When the amount exceeds $10,000"
- "searchResults.size() > maxLimit" → "When results exceed the maximum allowed"

## Critical: Exhaustive Rule Extraction
Do NOT summarize or skip business rules. If the code contains:
- 10 validation rules → document all 10
- 5 search types → explain all 5
- 8 error conditions → describe all 8

The Business Validations and Rules section should be the most detailed section of the BRD.

Remember: Write for BUSINESS readers, not developers. Focus on WHAT the system does, not HOW it's implemented.
"""


def build_reverse_engineering_prompt(feature_description: str, detail_level: str = "standard") -> str:
    """Build prompt for reverse engineering existing code into a BRD."""

    base_prompt = build_brd_system_prompt(detail_level)

    return f"""{base_prompt}

## CRITICAL: REVERSE ENGINEERING MODE

You are reverse engineering EXISTING code to create a BRD. The feature "{feature_description}" ALREADY EXISTS.

### Your Primary Task: EXHAUSTIVE Business Logic Extraction

You must extract and document EVERY piece of business logic from the code:

1. **ANALYZE** the existing implementation thoroughly
2. **EXTRACT** every validation, rule, condition, and behavior
3. **TRANSLATE** all code logic into plain English business language
4. **DOCUMENT** comprehensively - do not summarize or skip any rules

### What to Extract (Be Exhaustive)

**From Validation Code:**
- Every field that is validated (required, format, length, range)
- Every conditional validation (field X required when Y is selected)
- Every error message and when it appears
- Every data transformation (trimming, uppercase conversion, etc.)

**From Business Logic:**
- Every condition and its outcome (if X then Y)
- Every calculation or data processing rule
- Every status check and what statuses mean
- Every limit, threshold, or boundary condition

**From User Interface Logic:**
- Every field and its purpose
- Every button/action and what it does
- Every screen transition and when it occurs
- Every feedback message shown to users

**From Query/Search Logic:**
- How each search type works
- What matching rules apply (exact, partial, case-sensitivity)
- How results are filtered, sorted, and limited

### Writing Rules

**NEVER include:**
- Class names (e.g., "UserValidator", "SearchService")
- Method names (e.g., "validate()", "executeSearch()")
- File paths (e.g., "/src/main/java/...")
- Line numbers
- Technical terms (e.g., "DAO", "entity", "null check")

**ALWAYS use:**
- Plain English descriptions
- Business terminology
- User-centric language
- "The system must..." or "When the user..."

### Translation Examples

| Code Pattern | Business Language |
|--------------|-------------------|
| `if (field == null)` | "The field is required" |
| `field.length() <= 40` | "The field accepts up to 40 characters" |
| `searchType == "NAME_BEGINS"` | "When searching by name prefix..." |
| `results.size() > maxLimit` | "When results exceed the maximum allowed..." |
| `input.trim().toUpperCase()` | "The system removes extra spaces and performs case-insensitive matching" |
| `status == "ACTIVE"` | "Only currently active records are included" |

All claims must be backed by actual code found in the analysis, but expressed entirely in business terms.
"""
