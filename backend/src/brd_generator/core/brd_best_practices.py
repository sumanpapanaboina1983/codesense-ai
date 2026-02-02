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
7. **Assumptions and Constraints** - Conditions assumed and limitations
8. **Acceptance Criteria** - Measurable pass/fail conditions

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
