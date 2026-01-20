"""
Reasoning prompt templates for the Agentic Harness.
"""

REASONING_PROMPTS = {
    "understand": """
## Task Understanding

Analyze the following task and extract:
1. **Intent**: What is the user trying to achieve?
2. **Requirements**: What explicit requirements are stated?
3. **Constraints**: What limitations or constraints exist?
4. **Implicit Needs**: What unstated requirements can be inferred?

Task: {task}

Provide your analysis in a structured format:

### Intent
[Describe the core intent]

### Requirements
- [Requirement 1]
- [Requirement 2]
...

### Constraints
- [Constraint 1]
- [Constraint 2]
...

### Implicit Needs
- [Need 1]
- [Need 2]
...

### Clarifying Questions
[List any questions that would help clarify the task]
""",

    "analyze": """
## Context Analysis

Given the task understanding:
{understanding}

And the available context:
{context}

Analyze:
1. **Available Information**: What relevant data do we have?
2. **Information Gaps**: What do we need but don't have?
3. **Data Sources**: Where can we get missing information?
4. **Risks**: What could go wrong?

Use the available tools to gather information from the codebase graph and source files.

### Available Information
- [Info 1]
- [Info 2]
...

### Information Gaps
- [Gap 1]
- [Gap 2]
...

### Recommended Data Sources
- [Source 1]: [What to query]
- [Source 2]: [What to read]
...

### Risks
- [Risk 1]: [Mitigation]
- [Risk 2]: [Mitigation]
...
""",

    "decompose": """
## Task Decomposition

Based on the analysis:
{analysis}

Break down the task into {depth} levels of subtasks:

### Level 1: Major Steps
[High-level steps to complete the task]

### Level 2: Detailed Tasks
[Specific tasks for each major step]

### Dependencies
[Which tasks depend on others]

### Parallel Opportunities
[Which tasks can be done in parallel]

Provide the decomposition as:

### Subtasks
1. [Subtask description]
   - Tools needed: [tool1, tool2]
   - Dependencies: [none or task IDs]

2. [Subtask description]
   - Tools needed: [tool1, tool2]
   - Dependencies: [task IDs]
...

### Task Graph
[Describe the dependency graph]
""",

    "verify": """
## Verification

Verify the following execution results against the codebase:

Execution Results:
{execution}

Context:
{context}

For each claim or result:
1. Identify verifiable facts
2. Query the graph or read source code to verify
3. Score confidence (0.0 - 1.0)
4. Flag any hallucinations

### Verified Claims
- [Claim]: [Evidence] (Confidence: X.X)
...

### Unverified Claims
- [Claim]: [Reason unverified]
...

### Hallucination Flags
- [Flag]: [Explanation]
...

### Overall Verification Confidence
[X.X with explanation]
""",

    "synthesize": """
## Synthesis

Combine all reasoning steps into a final answer.

Understanding:
{understanding}

Execution Results:
{execution}

Verification:
{verification}

Create a final answer that:
1. Addresses all identified requirements
2. Is grounded in verified facts
3. Acknowledges any limitations
4. Provides actionable information

### Final Answer
[Comprehensive answer]

### Key Points
- [Point 1]
- [Point 2]
...

### Evidence Summary
[Summary of supporting evidence]

### Limitations
[Any caveats or limitations]

### Recommended Next Steps
[If applicable]
""",
}

# System prompts for different reasoning modes
SYSTEM_PROMPTS = {
    "default": """
You are an AI assistant that reasons carefully about software engineering tasks.
You think step-by-step, verify your claims, and never make unsupported assertions.
""",

    "analysis": """
You are analyzing a codebase to understand its architecture and components.
Every statement must be backed by evidence from the code graph or source files.
Use the available tools to gather information before making claims.
""",

    "document_generation": """
You are generating documentation for a software system.
All content must be:
1. Grounded in actual code analysis
2. Verifiable against the codebase
3. Structured according to the specified format
4. Free of hallucinations
""",

    "verification": """
You are a strict verifier ensuring zero hallucinations.
For every claim:
1. Identify what can be verified
2. Query the appropriate data source
3. Only confirm claims with evidence
4. Flag anything that cannot be verified
""",
}

# Templates for specific reasoning patterns
REASONING_PATTERNS = {
    "chain_of_thought": """
Let's think through this step by step:

1. First, I need to understand: {step1}
2. Then, I should analyze: {step2}
3. Based on that, I can: {step3}
4. Finally, I will verify: {step4}

Let me begin with step 1...
""",

    "tree_of_thought": """
Let me explore multiple approaches:

Approach A: {approach_a}
- Pros: ...
- Cons: ...

Approach B: {approach_b}
- Pros: ...
- Cons: ...

After evaluating both approaches, I recommend: ...
""",

    "reflection": """
Let me reflect on my reasoning:

What I concluded: {conclusion}

Is this conclusion well-supported?
- Evidence for: ...
- Evidence against: ...
- Gaps in reasoning: ...

Revised conclusion (if needed): ...
""",
}
