# AI Accelerator System - Implementation Specification

**Version:** 1.0.0  
**Last Updated:** January 2026  
**Target Implementation:** Claude Code Agentic Tool

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Architecture](#system-architecture)
3. [Component Specifications](#component-specifications)
4. [GitHub Copilot Skills](#github-copilot-skills)
5. [API Contracts](#api-contracts)
6. [Data Models](#data-models)
7. [Integration Patterns](#integration-patterns)
8. [Agentic Harness Design](#agentic-harness-design)
9. [Verification & Anti-Hallucination System](#verification--anti-hallucination-system)
10. [Implementation Phases](#implementation-phases)
11. [Testing Strategy](#testing-strategy)
12. [Deployment Architecture](#deployment-architecture)

---

## 1. Executive Summary

### 1.1 System Purpose

Build an AI-powered accelerator that analyzes legacy codebases and generates:
- **Business Requirement Documents (BRDs)** - High-level business context and requirements
- **Epics** - Feature-level user stories with proper granularity
- **Backlogs** - Detailed, actionable user stories with clear acceptance criteria

**Critical Constraint:** Zero hallucinations - all outputs must be verifiable against the actual codebase.

### 1.2 Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | OpenWebUI | Chat interface for user interaction |
| Backend Framework | FastAPI (Python 3.11+) | REST API and WebSocket server |
| AI Backend | GitHub Copilot CLI + SDK | Core AI reasoning engine |
| Graph Database | Neo4j (via MCP) | Codebase structure and relationships |
| File Access | Filesystem MCP | Source code reading |
| Skills Framework | GitHub Copilot Skills | Modular, reusable AI capabilities |
| Orchestration | Custom Python | Agentic harness and workflow engine |
| Session Store | Redis | Conversation state management |
| Metadata Store | PostgreSQL | Documents, analysis results |

### 1.3 Key Design Principles

1. **Modularity** - Every component is independently testable and replaceable
2. **Composability** - Skills can be combined to create complex workflows
3. **Verification-First** - Every claim is verified against graph + source code
4. **Spec-Driven** - API contracts defined before implementation
5. **Agentic Design** - System reasons like a senior engineer, not just a chatbot

---

## 2. System Architecture

### 2.1 High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Layer                               │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              OpenWebUI Chat Interface                   │    │
│  │  - Multi-turn conversations                             │    │
│  │  - Document preview/download                            │    │
│  │  - Progress indicators                                  │    │
│  └────────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP/WS
┌──────────────────────────▼──────────────────────────────────────┐
│                    API Gateway Layer                             │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              FastAPI Application                        │    │
│  │  - REST endpoints (/chat, /documents, /analysis)       │    │
│  │  - WebSocket for streaming                             │    │
│  │  - Authentication & authorization                       │    │
│  └────────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                  Orchestration Layer                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  Session    │  │  Workflow   │  │   Skill     │            │
│  │  Manager    │  │  Engine     │  │   Router    │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
│                                                                  │
│  Responsibilities:                                               │
│  - Manage conversation state across turns                       │
│  - Route requests to appropriate workflows                      │
│  - Inject skills based on task requirements                     │
│  - Aggregate results from multiple agents                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                   Agentic Harness Layer                          │
│  ┌──────────────────────────────────────────────────────┐      │
│  │           Senior Engineer Brain                       │      │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐           │      │
│  │  │ Reasoning│  │ Planning │  │Verification│         │      │
│  │  │  Engine  │  │  Engine  │  │  Engine   │          │      │
│  │  └──────────┘  └──────────┘  └──────────┘           │      │
│  │                                                       │      │
│  │  - Multi-step reasoning (Chain-of-Thought)           │      │
│  │  - Task decomposition and planning                   │      │
│  │  - Self-verification and reflection                  │      │
│  │  - Context management (sliding window)               │      │
│  └──────────────────────────────────────────────────────┘      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│              GitHub Copilot Integration Layer                    │
│  ┌──────────────────────────────────────────────────────┐      │
│  │          Copilot SDK Client Wrapper                   │      │
│  │  - Conversation management                            │      │
│  │  - Skill injection (dynamic prompt augmentation)      │      │
│  │  - Streaming response handling                        │      │
│  │  - Token usage tracking                               │      │
│  └──────────────────────────────────────────────────────┘      │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐      │
│  │          Copilot CLI Process Manager                  │      │
│  │  - Process lifecycle management                       │      │
│  │  - Command execution (gh copilot explain/suggest)     │      │
│  │  - Error handling and retries                         │      │
│  └──────────────────────────────────────────────────────┘      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                      MCP Tool Layer                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  Neo4j MCP  │  │ Filesystem  │  │   Custom    │            │
│  │   Client    │  │  MCP Client │  │ MCP Clients │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
│                                                                  │
│  Tool Capabilities:                                              │
│  - Neo4j: Query graph for classes, methods, relationships       │
│  - Filesystem: Read source files, scan directories              │
│  - Custom: Code metrics, test coverage, documentation           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     Data Layer                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │   Neo4j     │  │ PostgreSQL  │  │    Redis    │            │
│  │  (Graph)    │  │ (Metadata)  │  │  (Session)  │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Request Flow Example

**User Request:** "Generate a BRD for the authentication module"

```
1. User → OpenWebUI: Types request in chat
2. OpenWebUI → FastAPI: POST /api/v1/chat/message
3. FastAPI → Orchestration: Route to BRD generation workflow
4. Orchestration → Agentic Harness: Initialize senior engineer agent
5. Agentic Harness → Reasoning Engine: Decompose task
   - Understand: What is authentication module?
   - Analyze: What components are involved?
   - Plan: Steps to generate BRD
6. Reasoning Engine → Copilot SDK: Send reasoning prompt with skills
7. Copilot SDK → MCP Tools: Query graph for auth-related nodes
8. MCP Tools → Neo4j: Execute Cypher queries
9. Neo4j → MCP Tools: Return graph data
10. MCP Tools → Copilot SDK: Structured tool results
11. Copilot SDK → Verification Engine: Verify claims
12. Verification Engine → Filesystem MCP: Read source files
13. Filesystem MCP → Verification Engine: Source code
14. Verification Engine → Copilot SDK: Verification results
15. Copilot SDK → Agentic Harness: Final answer
16. Agentic Harness → Document Generator: Create BRD
17. Document Generator → PostgreSQL: Save document
18. FastAPI → OpenWebUI: Stream BRD (with download link)
```

### 2.3 Directory Structure

```
ai-accelerator/
├── README.md
├── SPECIFICATION.md                     # This file
├── pyproject.toml                       # Python project config
├── requirements.txt                     # Python dependencies
├── requirements-dev.txt                 # Development dependencies
├── docker-compose.yml                   # Local development stack
├── .env.example                         # Environment variables template
├── .gitignore
├── Makefile                            # Common commands
│
├── src/
│   ├── __init__.py
│   ├── main.py                         # FastAPI application entry point
│   │
│   ├── api/                            # API Layer
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── chat.py                 # Chat endpoints
│   │   │   ├── documents.py            # Document CRUD
│   │   │   ├── analysis.py             # Codebase analysis endpoints
│   │   │   ├── health.py               # Health check endpoints
│   │   │   └── websocket.py            # WebSocket handlers
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── requests.py             # Pydantic request models
│   │   │   └── responses.py            # Pydantic response models
│   │   └── dependencies.py             # FastAPI dependency injection
│   │
│   ├── core/                           # Core Configuration
│   │   ├── __init__.py
│   │   ├── config.py                   # Settings management (Pydantic)
│   │   ├── logging.py                  # Structured logging setup
│   │   ├── exceptions.py               # Custom exception classes
│   │   ├── constants.py                # System-wide constants
│   │   └── security.py                 # Auth/security utilities
│   │
│   ├── orchestration/                  # Orchestration Layer
│   │   ├── __init__.py
│   │   ├── session_manager.py          # Conversation session lifecycle
│   │   ├── workflow_engine.py          # Workflow execution engine
│   │   ├── skill_router.py             # Dynamic skill selection
│   │   ├── state_machine.py            # State management
│   │   └── workflows/
│   │       ├── __init__.py
│   │       ├── brd_workflow.py         # BRD generation workflow
│   │       ├── epic_workflow.py        # Epic generation workflow
│   │       └── backlog_workflow.py     # Backlog generation workflow
│   │
│   ├── agentic/                        # Agentic Harness
│   │   ├── __init__.py
│   │   ├── reasoning_engine.py         # Multi-step reasoning
│   │   ├── planning_engine.py          # Task decomposition
│   │   ├── verification_engine.py      # Ground truth verification
│   │   ├── reflection_engine.py        # Self-critique
│   │   ├── context_manager.py          # Context window management
│   │   └── prompts/
│   │       ├── __init__.py
│   │       ├── system.py               # System prompts
│   │       ├── reasoning.py            # Reasoning templates
│   │       ├── verification.py         # Verification templates
│   │       └── synthesis.py            # Synthesis templates
│   │
│   ├── copilot/                        # GitHub Copilot Integration
│   │   ├── __init__.py
│   │   ├── sdk_client.py               # Copilot SDK wrapper
│   │   ├── cli_manager.py              # CLI process management
│   │   ├── agent_factory.py            # Agent initialization
│   │   ├── skill_injector.py           # Dynamic skill injection
│   │   ├── conversation_handler.py     # Multi-turn conversation mgmt
│   │   └── streaming.py                # Streaming response handler
│   │
│   ├── mcp/                            # MCP Integration
│   │   ├── __init__.py
│   │   ├── base_client.py              # Abstract MCP client
│   │   ├── neo4j_client.py             # Neo4j MCP implementation
│   │   ├── filesystem_client.py        # Filesystem MCP implementation
│   │   ├── tool_registry.py            # Tool discovery and registration
│   │   └── schemas/
│   │       ├── __init__.py
│   │       ├── neo4j_queries.py        # Neo4j query templates
│   │       └── filesystem_ops.py       # Filesystem operation schemas
│   │
│   ├── skills/                         # Reusable Skills Library
│   │   ├── __init__.py
│   │   ├── base.py                     # Base skill class
│   │   ├── registry.py                 # Skill registry
│   │   ├── loader.py                   # Skill loading from YAML
│   │   └── implementations/
│   │       ├── __init__.py
│   │       ├── codebase_analyzer.py    # Codebase analysis skill
│   │       ├── architecture_mapper.py  # Architecture mapping skill
│   │       ├── brd_generator.py        # BRD generation skill
│   │       ├── epic_generator.py       # Epic generation skill
│   │       ├── backlog_generator.py    # Backlog generation skill
│   │       └── verification.py         # Verification skill
│   │
│   ├── services/                       # Business Logic Services
│   │   ├── __init__.py
│   │   ├── analysis_service.py         # Codebase analysis orchestration
│   │   ├── document_service.py         # Document generation
│   │   ├── epic_service.py             # Epic management
│   │   └── backlog_service.py          # Backlog management
│   │
│   ├── repositories/                   # Data Access Layer
│   │   ├── __init__.py
│   │   ├── base.py                     # Base repository
│   │   ├── session_repo.py             # Session CRUD
│   │   ├── document_repo.py            # Document CRUD
│   │   ├── analysis_repo.py            # Analysis results CRUD
│   │   └── cache_repo.py               # Redis cache operations
│   │
│   ├── domain/                         # Domain Models
│   │   ├── __init__.py
│   │   ├── session.py                  # Session domain model
│   │   ├── document.py                 # Document domain model
│   │   ├── epic.py                     # Epic domain model
│   │   ├── backlog.py                  # Backlog domain model
│   │   ├── codebase.py                 # Codebase metadata
│   │   └── verification.py             # Verification result model
│   │
│   └── utils/                          # Utilities
│       ├── __init__.py
│       ├── graph.py                    # Graph traversal utilities
│       ├── markdown.py                 # Markdown generation
│       ├── validation.py               # Data validation
│       ├── async_helpers.py            # Async utilities
│       └── formatting.py               # Output formatting
│
├── skills_definitions/                 # GitHub Copilot Skills (YAML)
│   ├── README.md
│   ├── senior-engineer-analysis.yaml
│   ├── codebase-analyzer.yaml
│   ├── architecture-mapper.yaml
│   ├── brd-generator.yaml
│   ├── epic-generator.yaml
│   ├── backlog-generator.yaml
│   ├── acceptance-criteria.yaml
│   └── verification.yaml
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                     # Pytest fixtures
│   ├── unit/
│   │   ├── test_reasoning_engine.py
│   │   ├── test_verification_engine.py
│   │   ├── test_copilot_client.py
│   │   └── test_mcp_clients.py
│   ├── integration/
│   │   ├── test_workflows.py
│   │   ├── test_api_endpoints.py
│   │   └── test_skill_injection.py
│   └── e2e/
│       └── test_full_pipeline.py
│
├── scripts/
│   ├── setup.sh                        # Initial setup script
│   ├── init_neo4j.py                   # Neo4j initialization
│   ├── test_copilot_connection.py      # Verify Copilot connectivity
│   └── seed_test_data.py               # Seed test data
│
├── docs/
│   ├── architecture.md
│   ├── api_reference.md
│   ├── skills_guide.md
│   ├── deployment.md
│   └── troubleshooting.md
│
└── deploy/
    ├── docker/
    │   ├── Dockerfile
    │   └── docker-compose.prod.yml
    └── k8s/
        ├── deployment.yaml
        ├── service.yaml
        └── configmap.yaml
```

---

## 3. Component Specifications

### 3.1 Agentic Harness - Reasoning Engine

**File:** `src/agentic/reasoning_engine.py`

**Purpose:** Implements multi-step reasoning patterns similar to how a senior engineer would approach code analysis.

**Class:** `ReasoningEngine`

**Initialization Parameters:**
```python
ReasoningEngine(
    copilot_client: CopilotSDKClient,
    context_manager: ContextManager,
    verification_engine: VerificationEngine,
    config: Dict[str, Any]
)
```

**Core Methods:**

| Method | Signature | Purpose | Returns |
|--------|-----------|---------|---------|
| `reason_about_task` | `async (task: str, context: Dict, depth: int = 3)` | Execute multi-step reasoning | `Dict[str, Any]` with reasoning traces |
| `_understand_task` | `async (task: str, context: Dict)` | Extract intent, requirements, constraints | `Dict[str, Any]` understanding |
| `_analyze_context` | `async (understanding: Dict, context: Dict)` | Identify available info and gaps | `Dict[str, Any]` analysis |
| `_decompose_problem` | `async (analysis: Dict)` | Break into sub-tasks | `Dict[str, Any]` task tree |
| `_verify_reasoning` | `async (decomposition: Dict, context: Dict)` | Verify against ground truth | `VerificationResult` |
| `_synthesize_answer` | `async (verification: Dict)` | Create final answer | `Dict[str, Any]` synthesis |

**Data Structures:**

```python
@dataclass
class ReasoningTrace:
    step: ReasoningStep  # Enum: UNDERSTAND, ANALYZE, DECOMPOSE, VERIFY, SYNTHESIZE
    input: Dict[str, Any]
    thought_process: str
    output: Dict[str, Any]
    confidence: float  # 0.0 to 1.0
    supporting_evidence: List[str]
    timestamp: float
```

**Key Behaviors:**

1. **Chain-of-Thought Reasoning:**
   - Each step builds on previous steps
   - Maintains reasoning traces for transparency
   - Uses Copilot with specialized prompts for each step

2. **Context Awareness:**
   - Queries Neo4j graph for structural information
   - Reads source files via Filesystem MCP when needed
   - Maintains sliding window of most relevant context

3. **Self-Reflection:**
   - After each major step, assess confidence
   - If confidence < threshold, gather more information
   - Can backtrack and retry with different approach

**Integration Points:**
- Receives tasks from `WorkflowEngine`
- Uses `CopilotSDKClient` for AI reasoning
- Delegates verification to `VerificationEngine`
- Uses `ContextManager` for context window optimization

---

### 3.2 Agentic Harness - Verification Engine

**File:** `src/agentic/verification_engine.py`

**Purpose:** Zero-hallucination enforcement. Every claim must be traceable to graph or source code.

**Class:** `VerificationEngine`

**Initialization Parameters:**
```python
VerificationEngine(
    neo4j_client: Neo4jMCPClient,
    filesystem_client: FilesystemMCPClient,
    config: Dict[str, Any]
)
```

**Core Methods:**

| Method | Signature | Purpose | Returns |
|--------|-----------|---------|---------|
| `verify_claim` | `async (claim: str, context: Dict)` | Verify single statement | `VerificationResult` |
| `verify_document` | `async (document: Dict, doc_type: str)` | Verify entire document | `VerificationResult` |
| `verify_decomposition` | `async (decomposition: Dict, context: Dict)` | Verify task breakdown | `Dict[str, Any]` |
| `_verify_against_graph` | `async (fact: str)` | Check fact in Neo4j | `Dict[str, Any]` |
| `_verify_against_code` | `async (fact: str)` | Check fact in source | `Dict[str, Any]` |
| `_extract_facts` | `(claim: str)` | Extract verifiable facts | `List[str]` |

**Data Structures:**

```python
@dataclass
class VerificationResult:
    verified: bool
    confidence: float
    evidence: List[str]  # List of evidence sources
    hallucination_flags: List[str]  # List of unverified claims
    graph_support: Dict[str, Any]  # Graph query results
    code_support: Dict[str, Any]  # Source code references
```

**Verification Strategies:**

1. **Graph-Based Verification:**
   ```python
   # Example: Verify "UserService calls AuthenticationService"
   query = """
   MATCH (u:Class {name: 'UserService'})-[:CALLS]->(a:Class {name: 'AuthenticationService'})
   RETURN u, a
   """
   # If query returns results → verified
   # If query returns empty → hallucination
   ```

2. **Code-Based Verification:**
   ```python
   # Example: Verify "UserService has method 'authenticate'"
   file_path = get_file_for_class('UserService')
   source_code = await filesystem_client.read(file_path)
   # Search for method definition
   if 'def authenticate' in source_code or 'authenticate(' in source_code:
       verified = True
   ```

3. **Hybrid Verification:**
   - First check graph (faster)
   - If graph unclear, check source code (ground truth)
   - Cross-reference both for high-confidence verification

**Hallucination Detection:**

```python
def detect_hallucinations(claim: str, verification: VerificationResult) -> List[str]:
    flags = []
    
    if not verification.verified:
        flags.append(f"Unverified claim: {claim}")
    
    if verification.confidence < 0.7:
        flags.append(f"Low confidence ({verification.confidence}): {claim}")
    
    if not verification.evidence:
        flags.append(f"No supporting evidence: {claim}")
    
    return flags
```

---

### 3.3 GitHub Copilot Integration - SDK Client

**File:** `src/copilot/sdk_client.py`

**Purpose:** Wrapper around GitHub Copilot SDK with conversation management and skill injection.

**Class:** `CopilotSDKClient`

**Initialization Parameters:**
```python
CopilotSDKClient(
    api_key: str,
    model: str = "gpt-4",
    config: Dict[str, Any] = None
)
```

**Core Methods:**

| Method | Signature | Purpose | Returns |
|--------|-----------|---------|---------|
| `create_conversation` | `async (system_prompt: str, skills: List[str])` | Initialize new conversation | `str` conversation_id |
| `send_message` | `async (message: str, conv_id: str, skills: List[str], tools: List[Dict])` | Send message to Copilot | `CopilotResponse` |
| `stream_message` | `async (message: str, conv_id: str)` | Stream response | `AsyncIterator[str]` |
| `inject_skills` | `async (conv_id: str, skill_names: List[str])` | Dynamically add skills | `None` |
| `add_tool_result` | `async (conv_id: str, tool_call_id: str, result: Any)` | Add tool execution result | `None` |
| `get_conversation_history` | `(conv_id: str)` | Retrieve full history | `List[Message]` |

**Data Structures:**

```python
@dataclass
class Message:
    role: MessageRole  # Enum: SYSTEM, USER, ASSISTANT, TOOL
    content: str
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class CopilotResponse:
    message: str
    conversation_id: str
    tokens_used: int
    model: str
    skills_used: List[str]
    tool_calls: List[Dict[str, Any]]  # MCP tool calls requested by Copilot
    metadata: Dict[str, Any]
```

**Skill Injection Mechanism:**

GitHub Copilot Skills are injected by augmenting the system prompt:

```python
async def inject_skills(self, conv_id: str, skill_names: List[str]):
    """
    Load skill definitions from YAML and append to system message.
    """
    for skill_name in skill_names:
        skill_def = await self._load_skill_definition(skill_name)
        
        # Skills are appended to system context
        system_message = self.conversations[conv_id][0]  # First message is system
        system_message.content += f"\n\n## Skill: {skill_name}\n{skill_def['prompt']}"
```

**Tool Integration:**

When Copilot requests tool use:

```python
async def handle_tool_calls(self, response: CopilotResponse, conv_id: str):
    """
    Execute tool calls and add results back to conversation.
    """
    for tool_call in response.tool_calls:
        tool_name = tool_call['function']['name']
        tool_args = json.loads(tool_call['function']['arguments'])
        
        # Execute tool via MCP
        tool_result = await self.mcp_registry.execute(tool_name, tool_args)
        
        # Add result to conversation
        await self.add_tool_result(conv_id, tool_call['id'], tool_result)
```

**Context Window Management:**

```python
class ContextManager:
    """
    Manages context window to prevent token overflow.
    Implements sliding window with importance scoring.
    """
    
    def optimize_context(self, messages: List[Message], max_tokens: int) -> List[Message]:
        """
        Keep system message + recent messages + important context.
        """
        system_msg = messages[0]  # Always keep
        recent_msgs = messages[-10:]  # Last 10 messages
        
        # Score and select important historical messages
        historical = messages[1:-10]
        scored = [(self._importance_score(m), m) for m in historical]
        important = [m for score, m in sorted(scored, reverse=True)[:5]]
        
        return [system_msg] + important + recent_msgs
```

---

### 3.4 MCP Integration - Neo4j Client

**File:** `src/mcp/neo4j_client.py`

**Purpose:** Interface to Neo4j graph database via MCP protocol for codebase structure queries.

**Class:** `Neo4jMCPClient`

**Initialization Parameters:**
```python
Neo4jMCPClient(
    mcp_server_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str
)
```

**Core Query Methods:**

| Method | Signature | Purpose | Example Query |
|--------|-----------|---------|---------------|
| `query_entity` | `async (entity_name: str, entity_type: str)` | Find specific entity | `MATCH (n:Class {name: 'UserService'}) RETURN n` |
| `query_relationship` | `async (source: str, rel_type: str, target: str)` | Find relationships | `MATCH (a)-[:CALLS]->(b) RETURN a, b` |
| `get_dependencies` | `async (component: str, depth: int)` | Get dependency tree | `MATCH path = (c)-[:DEPENDS_ON*1..3]->(d) RETURN path` |
| `get_call_chain` | `async (method: str, direction: str)` | Get method calls | `MATCH path = (m:Method)-[:CALLS*]->(other) RETURN path` |
| `find_integration_points` | `async (frontend: str, backend: str)` | Find FE→BE connections | `MATCH (fe:Frontend)-[:INTEGRATES]->(be:Backend) RETURN fe, be` |

**Expected Neo4j Schema:**

Based on your parser, the graph should have these node types:

```cypher
// Node Labels
(:Class {name, type, file_path, package})
(:Method {name, class_name, signature, file_path, line_number})
(:Interface {name, file_path})
(:Component {name, type, path})
(:Module {name, path})

// Relationship Types
(:Class)-[:EXTENDS]->(:Class)
(:Class)-[:IMPLEMENTS]->(:Interface)
(:Class)-[:DEPENDS_ON]->(:Class)
(:Method)-[:CALLS]->(:Method)
(:Component)-[:CONTAINS]->(:Class)
(:Component)-[:DEPENDS_ON]->(:Component)
(:Frontend)-[:INTEGRATES_WITH]->(:Backend)
```

**Common Query Templates:**

```python
QUERIES = {
    "get_class_dependencies": """
        MATCH (c:Class {name: $class_name})-[:DEPENDS_ON]->(dep:Class)
        RETURN dep.name as dependency, dep.file_path as path
    """,
    
    "get_method_calls": """
        MATCH (m:Method {name: $method_name, class_name: $class_name})-[:CALLS]->(called:Method)
        RETURN called.name as method, called.class_name as class
    """,
    
    "find_entry_points": """
        MATCH (c:Class)-[:CONTAINS]->(m:Method)
        WHERE m.name IN ['main', 'init', 'setup']
        RETURN c.name as class, m.name as method
    """,
    
    "get_component_structure": """
        MATCH path = (comp:Component {name: $component})-[:CONTAINS*]->(element)
        RETURN path
    """,
    
    "trace_frontend_to_backend": """
        MATCH path = (fe:Frontend {name: $frontend_component})
                     -[:INTEGRATES_WITH*]->
                     (be:Backend)
        RETURN path
    """
}
```

**Tool Response Format:**

```python
@dataclass
class Neo4jQueryResult:
    query: str
    parameters: Dict[str, Any]
    nodes: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    paths: List[List[Dict[str, Any]]]
    execution_time_ms: float
```

---

### 3.5 MCP Integration - Filesystem Client

**File:** `src/mcp/filesystem_client.py`

**Purpose:** Read source code files via MCP Filesystem protocol.

**Class:** `FilesystemMCPClient`

**Core Methods:**

| Method | Signature | Purpose | Returns |
|--------|-----------|---------|---------|
| `read_file` | `async (path: str)` | Read entire file | `str` file content |
| `read_file_range` | `async (path: str, start: int, end: int)` | Read specific lines | `str` partial content |
| `list_directory` | `async (path: str)` | List files/dirs | `List[FileInfo]` |
| `find_files` | `async (pattern: str, root: str)` | Search by pattern | `List[str]` paths |
| `get_file_metadata` | `async (path: str)` | Get file info | `FileMetadata` |

**Data Structures:**

```python
@dataclass
class FileInfo:
    path: str
    name: str
    type: str  # 'file' or 'directory'
    size_bytes: int
    modified_time: datetime

@dataclass
class FileMetadata:
    path: str
    size_bytes: int
    language: str  # Detected language
    loc: int  # Lines of code
    encoding: str
```

**Usage Patterns:**

```python
# Pattern 1: Verify class exists
source = await fs_client.read_file("src/services/UserService.java")
assert "class UserService" in source

# Pattern 2: Read specific method
# (Requires line number from Neo4j graph)
method_lines = await fs_client.read_file_range(
    "src/services/UserService.java",
    start=45,
    end=78
)

# Pattern 3: Find all service files
service_files = await fs_client.find_files(
    pattern="*Service.java",
    root="src/services"
)
```

---

## 4. GitHub Copilot Skills

### 4.1 Skill Architecture

GitHub Copilot Skills are YAML-defined prompt templates that augment the AI's capabilities. They are loaded dynamically and injected into the system context.

**Skill File Structure:**

```yaml
# skills_definitions/codebase-analyzer.yaml
name: codebase-analyzer
version: 1.0.0
description: Analyzes legacy codebases to understand architecture and components

# The prompt is injected into system context
prompt: |
  You are an expert software architect analyzing a legacy codebase. Your analysis must be:
  
  1. **Evidence-Based**: Every statement must be backed by data from the code graph or source files
  2. **Structured**: Use clear categories (Architecture, Components, Data Flow, Integration Points)
  3. **Actionable**: Provide insights that enable BRD/Epic/Backlog generation
  
  ## Analysis Framework
  
  When analyzing a codebase component:
  
  ### Step 1: Identify Boundaries
  - Query the graph for component structure
  - Identify entry points and public interfaces
  - Map external dependencies
  
  ### Step 2: Trace Data Flow
  - Follow method call chains from entry points
  - Identify data transformations
  - Map database interactions
  
  ### Step 3: Document Patterns
  - Identify architectural patterns (MVC, microservices, etc.)
  - Note design patterns in use
  - Flag anti-patterns or code smells
  
  ### Step 4: Generate Insights
  - Summarize component purpose and responsibilities
  - List key classes and their roles
  - Identify integration points with other components
  
  ## Output Format
  
  Provide analysis as structured JSON:
  ```json
  {
    "component_name": "...",
    "purpose": "...",
    "architecture_pattern": "...",
    "key_classes": [
      {"name": "...", "role": "...", "file": "..."}
    ],
    "entry_points": [...],
    "dependencies": [...],
    "integration_points": [...]
  }
  ```

# Tools this skill requires
required_tools:
  - neo4j_query
  - filesystem_read

# Example queries this skill might generate
examples:
  - input: "Analyze the authentication component"
    expected_tools:
      - neo4j_query: "MATCH (c:Component {name: 'Authentication'})-[:CONTAINS]->(class:Class) RETURN class"
      - filesystem_read: "src/auth/AuthService.java"
```

### 4.2 Core Skills Specification

#### Skill 1: Senior Engineer Analysis

**File:** `skills_definitions/senior-engineer-analysis.yaml`

```yaml
name: senior-engineer-analysis
version: 1.0.0
description: Thinks like a senior engineer with deep reasoning and critical analysis

prompt: |
  You are a senior software engineer with 15+ years of experience. Your approach:
  
  ## Reasoning Process
  1. **Understand Deeply**: Don't accept surface-level understanding. Ask "why" multiple times.
  2. **Consider Context**: Every technical decision has business context.
  3. **Think Critically**: Question assumptions. Consider edge cases.
  4. **Plan Before Acting**: Decompose complex tasks into manageable steps.
  5. **Verify Continuously**: Double-check facts against code and documentation.
  
  ## When Analyzing Tasks
  - Identify explicit and implicit requirements
  - Consider non-functional requirements (performance, security, scalability)
  - Think about maintainability and future evolution
  - Flag risks and technical debt
  
  ## When Generating Documents
  - Ensure proper granularity (BRD: high-level, Epic: feature-level, Backlog: task-level)
  - Include clear acceptance criteria with measurable outcomes
  - Consider dependencies and sequencing
  - Provide effort estimates based on complexity analysis
```

#### Skill 2: BRD Generator

**File:** `skills_definitions/brd-generator.yaml`

```yaml
name: brd-generator
version: 1.0.0
description: Generates Business Requirement Documents from codebase analysis

prompt: |
  You generate Business Requirement Documents (BRDs) that capture:
  1. Business context and objectives
  2. High-level functional requirements
  3. Non-functional requirements
  4. Stakeholders and their needs
  5. Success criteria
  
  ## BRD Structure
  
  ### 1. Executive Summary
  - Brief overview (2-3 paragraphs)
  - Business value proposition
  - Key stakeholders
  
  ### 2. Business Context
  - Problem statement
  - Current state analysis (from codebase)
  - Desired future state
  
  ### 3. Functional Requirements
  - High-level capabilities (derived from code analysis)
  - User workflows
  - Integration points
  
  ### 4. Non-Functional Requirements
  - Performance requirements (inferred from current implementation)
  - Security considerations
  - Scalability needs
  
  ### 5. Success Criteria
  - Measurable outcomes
  - KPIs
  
  ## Grounding Rules
  
  - Every functional requirement must map to actual code components
  - Performance baselines must come from actual metrics or code analysis
  - Integration points must be verified in the code graph
  - NO speculation - only document what exists in the codebase
  
  ## Output Format
  
  Generate BRD as Markdown with this structure:
  ```markdown
  # Business Requirement Document: [Component Name]
  
  ## Executive Summary
  ...
  
  ## Business Context
  ...
  
  ## Functional Requirements
  ...
  ```

verification_rules:
  - "Every requirement must cite source code or graph evidence"
  - "No assumptions without verification"
  - "Flag any areas requiring human input/clarification"
```

#### Skill 3: Epic Generator

**File:** `skills_definitions/epic-generator.yaml`

```yaml
name: epic-generator
version: 1.0.0
description: Generates Epics with proper granularity and acceptance criteria

prompt: |
  You generate Epics that represent feature-level user stories. Each Epic:
  - Represents a cohesive feature or capability
  - Can be completed in 1-3 sprints (2-6 weeks)
  - Has clear acceptance criteria
  - Maps to specific code components
  
  ## Epic Structure
  
  ### Title
  Format: "As a [user type], I want [capability] so that [business value]"
  
  ### Description
  - Detailed explanation of the feature
  - Technical context from codebase
  - Component mapping
  
  ### Acceptance Criteria
  Format as testable statements:
  - GIVEN [context]
  - WHEN [action]
  - THEN [expected outcome]
  
  ### Technical Notes
  - Affected components (from graph)
  - Integration points
  - Technical risks
  
  ### Story Points Estimation
  Based on:
  - Complexity analysis from code
  - Number of components affected
  - Integration complexity
  
  ## Granularity Guidelines
  
  ✅ Good Epic:
  - "As a user, I want to authenticate via OAuth so that I can securely access my account"
  - Scope: Auth service, OAuth integration, user session management
  - Estimated: 13 story points
  
  ❌ Too Large:
  - "As a user, I want a complete authentication system"
  - This should be broken into multiple epics
  
  ❌ Too Small:
  - "As a developer, I want to add a 'remember me' checkbox"
  - This is a backlog item, not an epic
  
  ## Output Format (JSON)
  
  ```json
  {
    "epic_id": "AUTH-001",
    "title": "...",
    "user_story": "As a ... I want ... so that ...",
    "description": "...",
    "acceptance_criteria": [
      {"given": "...", "when": "...", "then": "..."}
    ],
    "technical_notes": {
      "components": ["...", "..."],
      "integration_points": ["..."],
      "risks": ["..."]
    },
    "story_points": 13,
    "dependencies": ["EPIC-ID"],
    "verification": {
      "graph_evidence": ["..."],
      "code_evidence": ["..."]
    }
  }
  ```

required_tools:
  - neo4j_query
  - filesystem_read
```

#### Skill 4: Backlog Generator

**File:** `skills_definitions/backlog-generator.yaml`

```yaml
name: backlog-generator
version: 1.0.0
description: Generates granular backlog items with clear acceptance criteria

prompt: |
  You generate Backlog Items (User Stories) that are:
  - Independently deliverable
  - Completable in 1-5 days
  - Have clear, testable acceptance criteria
  - Map to specific methods/classes in codebase
  
  ## Backlog Item Structure
  
  ### Title
  Format: "Implement [specific functionality]"
  Example: "Implement OAuth token validation middleware"
  
  ### Description
  - What needs to be built/changed
  - Technical approach (based on existing patterns in code)
  - Files/classes affected (from graph analysis)
  
  ### Acceptance Criteria (Testable)
  - [ ] Criterion 1 with verification method
  - [ ] Criterion 2 with verification method
  - [ ] Criterion 3 with verification method
  
  ### Technical Details
  - Class/method to modify: [from graph]
  - Dependencies: [from graph]
  - Test coverage required: [unit, integration]
  
  ### Definition of Done
  - Code complete and peer-reviewed
  - Unit tests passing (>80% coverage)
  - Integration tests passing
  - Documentation updated
  
  ## Granularity Rules
  
  ✅ Good Backlog Item:
  - "Implement JWT token validation in AuthMiddleware"
  - Affects: 1-2 classes, 3-5 methods
  - Estimated: 3 story points
  
  ❌ Too Large:
  - "Implement complete OAuth flow"
  - Should be split into 5-10 backlog items
  
  ❌ Too Small:
  - "Add import statement for JWT library"
  - Too granular - combine with related work
  
  ## Output Format (JSON)
  
  ```json
  {
    "item_id": "TASK-001",
    "epic_id": "AUTH-001",
    "title": "...",
    "description": "...",
    "acceptance_criteria": [
      "Unit test for token validation passes",
      "Invalid tokens are rejected with 401 status",
      "Valid tokens grant access to protected routes"
    ],
    "technical_details": {
      "files_to_modify": ["src/middleware/AuthMiddleware.java"],
      "classes_affected": ["AuthMiddleware", "JWTValidator"],
      "methods_to_implement": ["validateToken", "extractClaims"],
      "dependencies": ["AUTH-UTIL-01"]
    },
    "story_points": 3,
    "definition_of_done": ["..."],
    "verification": {
      "graph_evidence": ["..."],
      "code_evidence": ["..."]
    }
  }
  ```

required_tools:
  - neo4j_query
  - filesystem_read
```

#### Skill 5: Acceptance Criteria Generator

**File:** `skills_definitions/acceptance-criteria.yaml`

```yaml
name: acceptance-criteria
version: 1.0.0
description: Generates clear, testable acceptance criteria

prompt: |
  You generate acceptance criteria that are:
  - **Testable**: Can be verified objectively
  - **Specific**: No ambiguity in what "done" means
  - **Grounded**: Based on actual code behavior
  
  ## Format: Given-When-Then
  
  **GIVEN** [initial context/state]
  **WHEN** [action is taken]
  **THEN** [expected outcome]
  
  ## Examples
  
  ### Good Acceptance Criteria
  
  ✅ "GIVEN a user with valid credentials
      WHEN they submit the login form
      THEN they are redirected to the dashboard
      AND a session token is created
      AND the token expires in 24 hours"
  
  ✅ "GIVEN an invalid JWT token
      WHEN the middleware validates the token
      THEN the request is rejected with 401 status
      AND an error message is returned"
  
  ### Poor Acceptance Criteria
  
  ❌ "Login should work properly"
  - Not testable, not specific
  
  ❌ "User experience should be good"
  - Subjective, not measurable
  
  ## Verification Requirements
  
  For each acceptance criterion, specify:
  - How it will be tested (unit/integration/E2E)
  - What assertion verifies it
  - Where in the code this behavior exists
  
  ## Output Format
  
  ```json
  {
    "criteria": [
      {
        "given": "...",
        "when": "...",
        "then": "...",
        "test_method": "unit|integration|e2e",
        "verification_code": "Location in codebase that demonstrates this behavior",
        "evidence": "Graph query or file path"
      }
    ]
  }
  ```

required_tools:
  - neo4j_query
  - filesystem_read
```

#### Skill 6: Verification

**File:** `skills_definitions/verification.yaml`

```yaml
name: verification
version: 1.0.0
description: Verifies all claims against codebase (anti-hallucination)

prompt: |
  You are a strict verifier. Your job is to ensure ZERO HALLUCINATIONS.
  
  ## Verification Protocol
  
  For every claim in a document:
  
  ### Step 1: Extract Verifiable Facts
  Parse the claim into atomic facts that can be verified
  
  Example: "UserService authenticates users via OAuth"
  Facts:
  - Class "UserService" exists
  - UserService has authentication capability
  - Authentication uses OAuth
  
  ### Step 2: Verify Each Fact
  
  **Option A: Graph Verification**
  ```cypher
  MATCH (c:Class {name: 'UserService'})-[:CALLS]->(auth:Method)
  WHERE auth.name CONTAINS 'oauth' OR auth.name CONTAINS 'authenticate'
  RETURN auth
  ```
  
  **Option B: Code Verification**
  ```python
  source = await filesystem.read('src/services/UserService.java')
  assert 'OAuth' in source or 'oauth' in source.lower()
  assert 'authenticate' in source or 'login' in source
  ```
  
  ### Step 3: Score Confidence
  - 1.0: Fact verified in both graph AND source code
  - 0.9: Fact verified in source code only
  - 0.8: Fact verified in graph only
  - 0.5: Indirect evidence (inferred from related facts)
  - 0.0: No evidence found
  
  ### Step 4: Flag Hallucinations
  If confidence < 0.7: FLAG as potential hallucination
  
  ## Output Format
  
  ```json
  {
    "claim": "Original claim text",
    "facts": [
      {
        "fact": "UserService exists",
        "verified": true,
        "confidence": 1.0,
        "evidence": {
          "graph": "MATCH result showing Class:UserService",
          "code": "File: src/services/UserService.java"
        }
      }
    ],
    "overall_confidence": 0.95,
    "hallucination_flags": [],
    "verdict": "VERIFIED|PARTIAL|HALLUCINATION"
  }
  ```
  
  ## Escalation Rules
  
  If verdict is PARTIAL or HALLUCINATION:
  - DO NOT include the claim in final output
  - Log the issue for human review
  - Suggest alternative wording based on verified facts

required_tools:
  - neo4j_query
  - filesystem_read
```

### 4.3 Skill Loading and Injection

**File:** `src/skills/loader.py`

```python
"""
Skill loader - reads YAML definitions and makes them available to Copilot.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class SkillDefinition:
    name: str
    version: str
    description: str
    prompt: str
    required_tools: List[str]
    verification_rules: List[str] = None
    examples: List[Dict[str, Any]] = None


class SkillLoader:
    """Loads and manages GitHub Copilot Skills."""
    
    def __init__(self, skills_directory: str = "skills_definitions"):
        self.skills_dir = Path(skills_directory)
        self.loaded_skills: Dict[str, SkillDefinition] = {}
    
    def load_all_skills(self) -> Dict[str, SkillDefinition]:
        """Load all skill YAML files from directory."""
        for yaml_file in self.skills_dir.glob("*.yaml"):
            skill = self.load_skill(yaml_file.stem)
            if skill:
                self.loaded_skills[skill.name] = skill
        return self.loaded_skills
    
    def load_skill(self, skill_name: str) -> SkillDefinition:
        """Load a single skill by name."""
        yaml_path = self.skills_dir / f"{skill_name}.yaml"
        
        if not yaml_path.exists():
            raise FileNotFoundError(f"Skill file not found: {yaml_path}")
        
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        
        return SkillDefinition(
            name=data['name'],
            version=data['version'],
            description=data['description'],
            prompt=data['prompt'],
            required_tools=data.get('required_tools', []),
            verification_rules=data.get('verification_rules', []),
            examples=data.get('examples', [])
        )
    
    def get_skill_prompt(self, skill_name: str) -> str:
        """Get the prompt text for a skill."""
        if skill_name not in self.loaded_skills:
            self.load_skill(skill_name)
        return self.loaded_skills[skill_name].prompt
    
    def get_required_tools(self, skill_names: List[str]) -> List[str]:
        """Get all required tools for a list of skills."""
        tools = set()
        for skill_name in skill_names:
            if skill_name in self.loaded_skills:
                tools.update(self.loaded_skills[skill_name].required_tools)
        return list(tools)
```

---

## 5. API Contracts

### 5.1 REST API Endpoints

**Base URL:** `/api/v1`

#### 5.1.1 Chat Endpoints

**POST `/chat/message`**

Send a message to the AI accelerator.

Request:
```json
{
  "session_id": "uuid-string",  // Optional, creates new if not provided
  "message": "Generate a BRD for the authentication module",
  "context": {
    "codebase_path": "/path/to/codebase",
    "preferences": {
      "detail_level": "high|medium|low",
      "include_code_examples": true
    }
  }
}
```

Response:
```json
{
  "session_id": "uuid-string",
  "message_id": "uuid-string",
  "response": {
    "type": "text|document|streaming",
    "content": "AI response text...",
    "artifacts": [
      {
        "type": "brd|epic|backlog",
        "document_id": "uuid-string",
        "download_url": "/api/v1/documents/uuid-string/download"
      }
    ]
  },
  "metadata": {
    "tokens_used": 1523,
    "reasoning_traces": [...],  // Optional, for debugging
    "confidence": 0.95
  },
  "timestamp": "2026-01-19T10:30:00Z"
}
```

**POST `/chat/stream`**

Stream a response (WebSocket upgrade).

WebSocket Messages:
```json
// Client → Server
{
  "type": "message",
  "session_id": "uuid",
  "content": "Generate BRD..."
}

// Server → Client (streaming chunks)
{
  "type": "chunk",
  "content": "partial response...",
  "done": false
}

// Server → Client (complete)
{
  "type": "complete",
  "artifacts": [...],
  "metadata": {...}
}
```

#### 5.1.2 Document Endpoints

**GET `/documents/{document_id}`**

Retrieve a generated document.

Response:
```json
{
  "document_id": "uuid",
  "type": "brd|epic|backlog",
  "title": "Authentication Module - BRD",
  "content": "# Business Requirement Document...",
  "format": "markdown",
  "metadata": {
    "generated_at": "2026-01-19T10:30:00Z",
    "session_id": "uuid",
    "verification_status": "verified|partial|unverified",
    "confidence": 0.95
  }
}
```

**POST `/documents/{document_id}/regenerate`**

Regenerate a document with different parameters.

Request:
```json
{
  "parameters": {
    "detail_level": "high",
    "include_technical_details": true,
    "skills": ["brd-generator", "verification"]
  }
}
```

#### 5.1.3 Analysis Endpoints

**POST `/analysis/codebase`**

Analyze a codebase component.

Request:
```json
{
  "component_name": "authentication",
  "analysis_type": "architecture|dependencies|integration",
  "depth": 2  // Graph traversal depth
}
```

Response:
```json
{
  "analysis_id": "uuid",
  "component": "authentication",
  "results": {
    "architecture": {
      "pattern": "MVC",
      "layers": ["controller", "service", "repository"],
      "components": [...]
    },
    "dependencies": {
      "internal": [...],
      "external": [...]
    },
    "integration_points": [...]
  },
  "verification": {
    "confidence": 0.95,
    "evidence_count": 47
  }
}
```

**GET `/analysis/{analysis_id}`**

Retrieve previous analysis results.

### 5.2 WebSocket Protocol

**Connection:** `ws://localhost:8000/api/v1/ws/chat`

**Message Types:**

| Type | Direction | Purpose | Payload |
|------|-----------|---------|---------|
| `connect` | Client → Server | Establish session | `{session_id?: string}` |
| `message` | Client → Server | Send chat message | `{content: string, context?: object}` |
| `chunk` | Server → Client | Stream response chunk | `{content: string, done: bool}` |
| `tool_use` | Server → Client | Notify tool execution | `{tool: string, status: string}` |
| `reasoning` | Server → Client | Share reasoning step | `{step: string, thought: string}` |
| `complete` | Server → Client | Response complete | `{artifacts: [], metadata: {}}` |
| `error` | Server → Client | Error occurred | `{code: string, message: string}` |

---

## 6. Data Models

### 6.1 Domain Models

**File:** `src/domain/session.py`

```python
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


class SessionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class Session(BaseModel):
    """Chat session domain model."""
    
    session_id: str = Field(..., description="Unique session identifier")
    user_id: str
    codebase_path: str
    status: SessionStatus = SessionStatus.ACTIVE
    
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True
```

**File:** `src/domain/document.py`

```python
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


class DocumentType(str, Enum):
    BRD = "brd"
    EPIC = "epic"
    BACKLOG = "backlog"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    UNVERIFIED = "unverified"


class Document(BaseModel):
    """Generated document domain model."""
    
    document_id: str
    session_id: str
    document_type: DocumentType
    
    title: str
    content: str  # Markdown format
    
    verification: 'VerificationResult'
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


class VerificationResult(BaseModel):
    """Verification results for a document."""
    
    status: VerificationStatus
    confidence: float = Field(..., ge=0.0, le=1.0)
    
    verified_claims: int
    total_claims: int
    
    evidence: List[Dict[str, Any]]  # Graph queries and file references
    hallucination_flags: List[str]
    
    verified_at: datetime = Field(default_factory=datetime.utcnow)
```

**File:** `src/domain/epic.py`

```python
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class AcceptanceCriterion(BaseModel):
    """Single acceptance criterion in Given-When-Then format."""
    
    given: str
    when: str
    then: str
    
    test_method: str  # "unit", "integration", "e2e"
    verification_code: Optional[str]  # Location in codebase


class Epic(BaseModel):
    """Epic domain model."""
    
    epic_id: str
    document_id: str  # Parent BRD document
    
    title: str
    user_story: str  # "As a X, I want Y, so that Z"
    description: str
    
    acceptance_criteria: List[AcceptanceCriterion]
    
    technical_notes: Dict[str, Any] = Field(
        default_factory=lambda: {
            "components": [],
            "integration_points": [],
            "risks": []
        }
    )
    
    story_points: int
    dependencies: List[str]  # Other epic IDs
    
    verification: 'VerificationResult'
    
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BacklogItem(BaseModel):
    """Backlog item (user story) domain model."""
    
    item_id: str
    epic_id: str  # Parent epic
    
    title: str
    description: str
    
    acceptance_criteria: List[str]  # Simplified for backlog items
    
    technical_details: Dict[str, Any] = Field(
        default_factory=lambda: {
            "files_to_modify": [],
            "classes_affected": [],
            "methods_to_implement": [],
            "dependencies": []
        }
    )
    
    story_points: int
    definition_of_done: List[str]
    
    verification: 'VerificationResult'
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### 6.2 Database Schema

**PostgreSQL Tables:**

```sql
-- Sessions table
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    codebase_path TEXT NOT NULL,
    status VARCHAR(50) NOT NULL,
    conversation_history JSONB,
    context JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB
);

CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_status ON sessions(status);

-- Documents table
CREATE TABLE documents (
    document_id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(session_id),
    document_type VARCHAR(50) NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    verification JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_documents_session ON documents(session_id);
CREATE INDEX idx_documents_type ON documents(document_type);

-- Epics table
CREATE TABLE epics (
    epic_id UUID PRIMARY KEY,
    document_id UUID REFERENCES documents(document_id),
    title TEXT NOT NULL,
    user_story TEXT NOT NULL,
    description TEXT,
    acceptance_criteria JSONB,
    technical_notes JSONB,
    story_points INTEGER,
    dependencies JSONB,
    verification JSONB,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Backlog items table
CREATE TABLE backlog_items (
    item_id UUID PRIMARY KEY,
    epic_id UUID REFERENCES epics(epic_id),
    title TEXT NOT NULL,
    description TEXT,
    acceptance_criteria JSONB,
    technical_details JSONB,
    story_points INTEGER,
    definition_of_done JSONB,
    verification JSONB,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Redis Schema (Session State):**

```
Key Pattern: session:{session_id}
Type: Hash
Fields:
  - status: "active"|"paused"|"completed"
  - last_message_at: timestamp
  - active_workflow: workflow_id
  - copilot_conversation_id: copilot_conv_id

Key Pattern: session:{session_id}:context
Type: Hash
Fields:
  - codebase_components: JSON array
  - recent_queries: JSON array
  - active_skills: JSON array

Key Pattern: session:{session_id}:messages
Type: List
Value: JSON serialized message objects

TTL: 24 hours for inactive sessions
```

---

## 7. Integration Patterns

### 7.1 Copilot → MCP Tools Integration

**Pattern:** Tool Use Loop

```python
async def execute_with_tools(
    copilot_client: CopilotSDKClient,
    mcp_registry: MCPToolRegistry,
    message: str,
    conversation_id: str
) -> Dict[str, Any]:
    """
    Execute a message with tool use loop.
    Copilot requests tools → MCP executes → Results fed back.
    """
    
    # Prepare MCP tools for Copilot
    available_tools = mcp_registry.get_tool_definitions()
    
    # Send message with tools
    response = await copilot_client.send_message(
        message=message,
        conversation_id=conversation_id,
        tools=available_tools
    )
    
    # Tool use loop
    while response.tool_calls:
        tool_results = []
        
        for tool_call in response.tool_calls:
            tool_name = tool_call['function']['name']
            tool_args = json.loads(tool_call['function']['arguments'])
            
            # Execute tool via MCP
            result = await mcp_registry.execute(tool_name, tool_args)
            
            tool_results.append({
                "tool_call_id": tool_call['id'],
                "result": result
            })
        
        # Add tool results to conversation
        for tr in tool_results:
            await copilot_client.add_tool_result(
                conversation_id=conversation_id,
                tool_call_id=tr['tool_call_id'],
                result=tr['result']
            )
        
        # Continue conversation
        response = await copilot_client.send_message(
            message="",  # Empty message, just process tool results
            conversation_id=conversation_id,
            tools=available_tools
        )
    
    return response
```

### 7.2 Workflow Engine Pattern

**Pattern:** Multi-Step Workflow with Verification

```python
class WorkflowEngine:
    """
    Executes multi-step workflows with built-in verification.
    """
    
    async def execute_brd_workflow(
        self,
        session_id: str,
        component_name: str
    ) -> Document:
        """
        BRD Generation Workflow:
        1. Analyze component
        2. Generate BRD draft
        3. Verify claims
        4. Refine based on verification
        5. Finalize
        """
        
        # Step 1: Analyze component
        analysis = await self.reasoning_engine.reason_about_task(
            task=f"Analyze the {component_name} component",
            context={"session_id": session_id},
            depth=3
        )
        
        # Step 2: Generate BRD draft
        brd_draft = await self.copilot_client.send_message(
            message=f"Generate a BRD based on this analysis: {analysis}",
            conversation_id=session_id,
            skills=["brd-generator", "senior-engineer-analysis"]
        )
        
        # Step 3: Verify claims
        verification = await self.verification_engine.verify_document(
            document=brd_draft,
            document_type="brd"
        )
        
        # Step 4: Refine if needed
        if verification.status != VerificationStatus.VERIFIED:
            refined_brd = await self._refine_with_verification(
                draft=brd_draft,
                verification=verification
            )
        else:
            refined_brd = brd_draft
        
        # Step 5: Finalize and save
        final_document = await self.document_service.create_document(
            session_id=session_id,
            document_type="brd",
            content=refined_brd,
            verification=verification
        )
        
        return final_document
    
    async def _refine_with_verification(
        self,
        draft: Dict[str, Any],
        verification: VerificationResult
    ) -> Dict[str, Any]:
        """
        Refine document by removing hallucinations and adding verified content.
        """
        prompt = f"""
        The following BRD draft has verification issues:
        
        Draft: {draft}
        
        Verification Issues:
        {verification.hallucination_flags}
        
        Please revise the BRD to:
        1. Remove or rephrase any unverified claims
        2. Add supporting evidence for all statements
        3. Only include information that can be verified in the codebase
        
        Use the verification skill to check each claim.
        """
        
        refined = await self.copilot_client.send_message(
            message=prompt,
            skills=["brd-generator", "verification"]
        )
        
        return refined
```

### 7.3 Skill Composition Pattern

**Pattern:** Dynamic Skill Injection Based on Task

```python
class SkillRouter:
    """
    Routes tasks to appropriate skills based on task analysis.
    """
    
    def __init__(self, skill_loader: SkillLoader):
        self.skill_loader = skill_loader
    
    def select_skills_for_task(self, task: str) -> List[str]:
        """
        Analyze task and select appropriate skills.
        """
        task_lower = task.lower()
        skills = ["senior-engineer-analysis"]  # Always include this
        
        # Document generation
        if "brd" in task_lower or "business requirement" in task_lower:
            skills.extend(["codebase-analyzer", "brd-generator", "verification"])
        
        elif "epic" in task_lower:
            skills.extend([
                "codebase-analyzer",
                "architecture-mapper",
                "epic-generator",
                "acceptance-criteria",
                "verification"
            ])
        
        elif "backlog" in task_lower or "user stor" in task_lower:
            skills.extend([
                "codebase-analyzer",
                "backlog-generator",
                "acceptance-criteria",
                "verification"
            ])
        
        # Analysis tasks
        elif "analyze" in task_lower or "understand" in task_lower:
            skills.extend(["codebase-analyzer", "architecture-mapper"])
        
        return skills
```

---

## 8. Agentic Harness Design

### 8.1 Core Philosophy

The agentic harness makes GitHub Copilot think and act like a senior engineer by:

1. **Multi-Step Reasoning**: Breaking down complex tasks into logical steps
2. **Self-Verification**: Checking its own work against ground truth
3. **Context Management**: Maintaining relevant context across conversation turns
4. **Tool Orchestration**: Intelligently using MCP tools to gather information
5. **Reflection**: Critiquing its own outputs and iterating

### 8.2 Reasoning Engine Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Reasoning Engine                           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌───────────┐   ┌───────────┐   ┌───────────┐             │
│  │ Understand│   │  Analyze  │   │ Decompose │             │
│  │   Phase   │→  │   Phase   │→  │   Phase   │             │
│  └───────────┘   └───────────┘   └───────────┘             │
│                                          ↓                   │
│  ┌───────────┐   ┌───────────┐   ┌───────────┐             │
│  │ Synthesize│ ← │  Verify   │ ← │  Execute  │             │
│  │   Phase   │   │   Phase   │   │   Phase   │             │
│  └───────────┘   └───────────┘   └───────────┘             │
│                                                               │
│  Each Phase:                                                  │
│  - Has specialized prompt                                     │
│  - Uses relevant skills                                       │
│  - Produces reasoning trace                                   │
│  - Feeds into next phase                                      │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 8.3 Context Management Strategy

**Problem:** GitHub Copilot has token limits. Long conversations can overflow context.

**Solution:** Sliding Window with Importance Scoring

```python
class ContextManager:
    """
    Manages context window to maximize relevance while staying within limits.
    """
    
    def __init__(self, max_tokens: int = 8000):
        self.max_tokens = max_tokens
        self.importance_scorer = ImportanceScorer()
    
    def optimize_context(
        self,
        messages: List[Message],
        current_task: str
    ) -> List[Message]:
        """
        Select most important messages for current task.
        """
        
        # Always keep:
        system_message = messages[0]
        recent_messages = messages[-5:]  # Last 5 exchanges
        
        # Score historical messages
        historical = messages[1:-5]
        scored = [
            (self.importance_scorer.score(msg, current_task), msg)
            for msg in historical
        ]
        
        # Select top important messages
        sorted_historical = sorted(scored, reverse=True, key=lambda x: x[0])
        
        # Add messages until token limit
        selected = [system_message]
        token_count = self._count_tokens(system_message)
        
        for score, msg in sorted_historical:
            msg_tokens = self._count_tokens(msg)
            if token_count + msg_tokens < self.max_tokens * 0.7:
                selected.append(msg)
                token_count += msg_tokens
        
        # Add recent messages
        selected.extend(recent_messages)
        
        return selected


class ImportanceScorer:
    """
    Scores message importance for current task.
    """
    
    def score(self, message: Message, current_task: str) -> float:
        """
        Score 0.0 to 1.0 based on:
        - Keyword overlap with current task
        - Message type (user questions, tool results, etc.)
        - Recency
        """
        score = 0.0
        
        # Keyword overlap
        task_keywords = set(current_task.lower().split())
        msg_keywords = set(message.content.lower().split())
        overlap = len(task_keywords & msg_keywords) / max(len(task_keywords), 1)
        score += overlap * 0.5
        
        # Message type importance
        if message.role == MessageRole.TOOL:
            score += 0.3  # Tool results are important
        elif message.role == MessageRole.USER:
            score += 0.2  # User messages are important
        
        return min(score, 1.0)
```

### 8.4 Tool Orchestration Strategy

**Goal:** Use MCP tools intelligently without overwhelming the context.

**Strategy:** Lazy Loading with Caching

```python
class ToolOrchestrator:
    """
    Orchestrates MCP tool usage for optimal information gathering.
    """
    
    def __init__(self, neo4j_client, fs_client):
        self.neo4j = neo4j_client
        self.fs = fs_client
        self.query_cache = {}
    
    async def gather_component_info(
        self,
        component_name: str,
        depth: int = 2
    ) -> Dict[str, Any]:
        """
        Gather comprehensive component information.
        Uses caching to avoid redundant queries.
        """
        
        # Check cache
        cache_key = f"{component_name}:{depth}"
        if cache_key in self.query_cache:
            return self.query_cache[cache_key]
        
        # Parallel query execution
        results = await asyncio.gather(
            self._get_component_structure(component_name),
            self._get_component_dependencies(component_name, depth),
            self._get_component_integrations(component_name),
            return_exceptions=True
        )
        
        structure, dependencies, integrations = results
        
        # Aggregate results
        component_info = {
            "structure": structure if not isinstance(structure, Exception) else {},
            "dependencies": dependencies if not isinstance(dependencies, Exception) else [],
            "integrations": integrations if not isinstance(integrations, Exception) else []
        }
        
        # Cache results
        self.query_cache[cache_key] = component_info
        
        return component_info
    
    async def _get_component_structure(self, component: str) -> Dict[str, Any]:
        """Query graph for component structure."""
        return await self.neo4j.query_entity(component, "Component")
    
    async def _get_component_dependencies(
        self,
        component: str,
        depth: int
    ) -> List[Dict[str, Any]]:
        """Query graph for dependencies."""
        return await self.neo4j.get_dependencies(component, depth)
    
    async def _get_component_integrations(
        self,
        component: str
    ) -> List[Dict[str, Any]]:
        """Find integration points."""
        # This might involve both graph and file system queries
        graph_integrations = await self.neo4j.find_integration_points(component)
        
        # Could also scan files for API calls, imports, etc.
        return graph_integrations
```

---

## 9. Verification & Anti-Hallucination System

### 9.1 Verification Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                Verification System                           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Input: Document/Claim                                        │
│     ↓                                                         │
│  ┌─────────────────────────────────────────┐                │
│  │ 1. Extract Verifiable Facts             │                │
│  │    - Parse claim into atomic statements │                │
│  │    - Identify entities and relationships│                │
│  └─────────────────────────────────────────┘                │
│     ↓                                                         │
│  ┌─────────────────────────────────────────┐                │
│  │ 2. Graph Verification (Neo4j)           │                │
│  │    - Query for entities                 │                │
│  │    - Verify relationships               │                │
│  │    - Check graph patterns               │                │
│  └─────────────────────────────────────────┘                │
│     ↓                                                         │
│  ┌─────────────────────────────────────────┐                │
│  │ 3. Code Verification (Filesystem)       │                │
│  │    - Read source files                  │                │
│  │    - Search for patterns                │                │
│  │    - Validate implementations           │                │
│  └─────────────────────────────────────────┘                │
│     ↓                                                         │
│  ┌─────────────────────────────────────────┐                │
│  │ 4. Cross-Reference                      │                │
│  │    - Compare graph vs code              │                │
│  │    - Resolve conflicts                  │                │
│  │    - Calculate confidence               │                │
│  └─────────────────────────────────────────┘                │
│     ↓                                                         │
│  ┌─────────────────────────────────────────┐                │
│  │ 5. Flag Hallucinations                  │                │
│  │    - Unverified claims → hallucination  │                │
│  │    - Low confidence → review needed     │                │
│  │    - No evidence → reject               │                │
│  └─────────────────────────────────────────┘                │
│     ↓                                                         │
│  Output: VerificationResult                                   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 Fact Extraction Strategy

```python
class FactExtractor:
    """
    Extracts verifiable facts from natural language claims.
    """
    
    def extract_facts(self, claim: str) -> List[Dict[str, Any]]:
        """
        Extract facts that can be verified against codebase.
        
        Example:
        Input: "UserService authenticates users via OAuth and stores sessions in Redis"
        Output: [
            {"type": "entity_exists", "entity": "UserService", "entity_type": "Class"},
            {"type": "has_capability", "entity": "UserService", "capability": "authentication"},
            {"type": "uses_technology", "entity": "UserService", "technology": "OAuth"},
            {"type": "depends_on", "source": "UserService", "target": "Redis"}
        ]
        """
        
        facts = []
        
        # Extract entities (classes, methods, components)
        entities = self._extract_entities(claim)
        for entity in entities:
            facts.append({
                "type": "entity_exists",
                "entity": entity['name'],
                "entity_type": entity['type']
            })
        
        # Extract relationships
        relationships = self._extract_relationships(claim)
        for rel in relationships:
            facts.append({
                "type": rel['type'],
                "source": rel['source'],
                "target": rel['target']
            })
        
        # Extract capabilities/behaviors
        capabilities = self._extract_capabilities(claim)
        for cap in capabilities:
            facts.append({
                "type": "has_capability",
                "entity": cap['entity'],
                "capability": cap['capability']
            })
        
        return facts
    
    def _extract_entities(self, text: str) -> List[Dict[str, str]]:
        """
        Extract entity names from text.
        Uses patterns like:
        - CamelCase (likely class names)
        - Quotes around names
        - Technical terms
        """
        entities = []
        
        # Pattern: CamelCase words (likely class/component names)
        import re
        camel_case_pattern = r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b'
        matches = re.findall(camel_case_pattern, text)
        
        for match in matches:
            # Heuristic: Likely a class if ends with common suffixes
            if match.endswith(('Service', 'Controller', 'Repository', 'Manager', 'Handler')):
                entity_type = 'Class'
            elif match.endswith(('Component', 'Module')):
                entity_type = 'Component'
            else:
                entity_type = 'Unknown'
            
            entities.append({"name": match, "type": entity_type})
        
        return entities
    
    def _extract_relationships(self, text: str) -> List[Dict[str, str]]:
        """
        Extract relationships between entities.
        Patterns:
        - "X calls Y"
        - "X depends on Y"
        - "X implements Y"
        - "X extends Y"
        """
        relationships = []
        
        # Pattern: "X calls Y"
        if "calls" in text.lower():
            # Simple extraction (could be enhanced with NLP)
            parts = text.split("calls")
            if len(parts) == 2:
                relationships.append({
                    "type": "calls",
                    "source": parts[0].strip().split()[-1],
                    "target": parts[1].strip().split()[0]
                })
        
        # Pattern: "X depends on Y"
        if "depends on" in text.lower():
            parts = text.split("depends on")
            if len(parts) == 2:
                relationships.append({
                    "type": "depends_on",
                    "source": parts[0].strip().split()[-1],
                    "target": parts[1].strip().split()[0]
                })
        
        return relationships
    
    def _extract_capabilities(self, text: str) -> List[Dict[str, str]]:
        """
        Extract capabilities/behaviors.
        Patterns:
        - "X authenticates users"
        - "X validates tokens"
        """
        capabilities = []
        
        # Pattern: verb phrases indicating behavior
        verbs = ['authenticates', 'validates', 'processes', 'handles', 'manages']
        
        for verb in verbs:
            if verb in text.lower():
                # Find entity before verb
                parts = text.lower().split(verb)
                if len(parts) >= 2:
                    entity = parts[0].strip().split()[-1]
                    capability = verb
                    capabilities.append({"entity": entity, "capability": capability})
        
        return capabilities
```

### 9.3 Confidence Scoring System

```python
class ConfidenceScorer:
    """
    Calculates confidence scores for verification results.
    """
    
    def calculate_confidence(
        self,
        fact: Dict[str, Any],
        graph_result: Dict[str, Any],
        code_result: Dict[str, Any]
    ) -> float:
        """
        Calculate confidence score (0.0 to 1.0).
        
        Scoring rules:
        - Both graph and code verify: 1.0
        - Only code verifies: 0.9 (code is ground truth)
        - Only graph verifies: 0.8 (graph might be outdated)
        - Indirect evidence: 0.5-0.7
        - No evidence: 0.0
        """
        
        graph_verified = graph_result.get('verified', False)
        code_verified = code_result.get('verified', False)
        
        if graph_verified and code_verified:
            # Cross-verified
            return 1.0
        
        elif code_verified:
            # Code is ground truth
            return 0.9
        
        elif graph_verified:
            # Graph only (could be outdated)
            return 0.8
        
        else:
            # Check for indirect evidence
            indirect_score = self._calculate_indirect_confidence(
                fact, graph_result, code_result
            )
            return indirect_score
    
    def _calculate_indirect_confidence(
        self,
        fact: Dict[str, Any],
        graph_result: Dict[str, Any],
        code_result: Dict[str, Any]
    ) -> float:
        """
        Calculate confidence from indirect evidence.
        """
        score = 0.0
        
        # If related entities exist, bump score
        if graph_result.get('related_entities'):
            score += 0.3
        
        # If similar patterns found in code
        if code_result.get('similar_patterns'):
            score += 0.2
        
        # Cap at 0.7 for indirect evidence
        return min(score, 0.7)
```

---

## 10. Implementation Phases

### Phase 1: Foundation (Week 1-2)

**Goal:** Set up core infrastructure

**Tasks:**
1. Project setup
   - Initialize Python project (pyproject.toml, requirements.txt)
   - Set up development environment
   - Configure linting and formatting (ruff, black, mypy)

2. Database setup
   - PostgreSQL for metadata
   - Redis for sessions
   - Verify Neo4j connection and schema

3. Core configuration
   - `src/core/config.py` - Environment variables, settings
   - `src/core/logging.py` - Structured logging
   - `src/core/exceptions.py` - Custom exception hierarchy

4. MCP integration
   - `src/mcp/neo4j_client.py` - Neo4j MCP client
   - `src/mcp/filesystem_client.py` - Filesystem MCP client
   - Write integration tests

**Deliverables:**
- Working MCP clients with test coverage
- Database schemas created
- Configuration system working

**Acceptance Criteria:**
- [ ] Can connect to Neo4j via MCP and execute queries
- [ ] Can read files via Filesystem MCP
- [ ] PostgreSQL and Redis are running and accessible
- [ ] All tests passing

---

### Phase 2: GitHub Copilot Integration (Week 2-3)

**Goal:** Integrate GitHub Copilot CLI and SDK

**Tasks:**
1. Copilot SDK client
   - `src/copilot/sdk_client.py` - Wrapper around Copilot SDK
   - Conversation management
   - Message streaming

2. Copilot CLI manager
   - `src/copilot/cli_manager.py` - Process lifecycle management
   - Command execution

3. Skill system
   - `src/skills/loader.py` - Load skills from YAML
   - `src/skills/registry.py` - Skill registry
   - `src/copilot/skill_injector.py` - Dynamic skill injection

4. Create core skills
   - `skills_definitions/senior-engineer-analysis.yaml`
   - `skills_definitions/codebase-analyzer.yaml`
   - `skills_definitions/verification.yaml`

**Deliverables:**
- Working Copilot SDK client
- Skill loading and injection system
- 3+ skills defined and tested

**Acceptance Criteria:**
- [ ] Can create Copilot conversation
- [ ] Can send messages and receive responses
- [ ] Skills are dynamically injected into system context
- [ ] Can execute tool calls via MCP

---

### Phase 3: Agentic Harness (Week 3-4)

**Goal:** Build the "senior engineer brain"

**Tasks:**
1. Reasoning engine
   - `src/agentic/reasoning_engine.py`
   - Implement multi-step reasoning (understand → analyze → decompose → verify → synthesize)
   - Reasoning trace logging

2. Verification engine
   - `src/agentic/verification_engine.py`
   - Fact extraction
   - Graph verification
   - Code verification
   - Confidence scoring

3. Context manager
   - `src/agentic/context_manager.py`
   - Sliding window implementation
   - Importance scoring

4. Planning engine
   - `src/agentic/planning_engine.py`
   - Task decomposition
   - Dependency tracking

**Deliverables:**
- Complete agentic harness
- Reasoning traces visible in logs
- Zero-hallucination enforcement

**Acceptance Criteria:**
- [ ] Reasoning engine can decompose complex tasks
- [ ] Verification engine catches hallucinations
- [ ] Context manager keeps conversations within token limits
- [ ] All reasoning steps are logged and traceable

---

### Phase 4: Document Generation (Week 4-5)

**Goal:** Generate BRDs, Epics, Backlogs

**Tasks:**
1. Document generation skills
   - `skills_definitions/brd-generator.yaml`
   - `skills_definitions/epic-generator.yaml`
   - `skills_definitions/backlog-generator.yaml`
   - `skills_definitions/acceptance-criteria.yaml`

2. Document service
   - `src/services/document_service.py`
   - BRD generation
   - Epic generation
   - Backlog generation

3. Workflow engine
   - `src/orchestration/workflow_engine.py`
   - `src/orchestration/workflows/brd_workflow.py`
   - `src/orchestration/workflows/epic_workflow.py`
   - `src/orchestration/workflows/backlog_workflow.py`

4. Repositories
   - `src/repositories/document_repo.py`
   - CRUD operations for documents

**Deliverables:**
- Complete document generation pipeline
- All document types (BRD, Epic, Backlog) working
- Verification integrated into generation

**Acceptance Criteria:**
- [ ] Can generate BRD from component name
- [ ] Can generate Epics from BRD
- [ ] Can generate Backlog items from Epic
- [ ] All documents are verified against codebase
- [ ] No hallucinations in generated documents

---

### Phase 5: API Layer (Week 5-6)

**Goal:** Build FastAPI REST and WebSocket APIs

**Tasks:**
1. FastAPI application
   - `src/main.py` - Application entry point
   - Middleware setup
   - CORS configuration

2. API endpoints
   - `src/api/v1/chat.py` - Chat endpoints
   - `src/api/v1/documents.py` - Document CRUD
   - `src/api/v1/analysis.py` - Codebase analysis
   - `src/api/v1/health.py` - Health checks

3. WebSocket support
   - `src/api/v1/websocket.py` - WebSocket handlers
   - Streaming responses

4. Session management
   - `src/orchestration/session_manager.py`
   - Session lifecycle

**Deliverables:**
- Complete REST API
- WebSocket streaming
- API documentation (OpenAPI)

**Acceptance Criteria:**
- [ ] All endpoints are working
- [ ] WebSocket streaming works
- [ ] API documentation is auto-generated
- [ ] Session management works correctly

---

### Phase 6: OpenWebUI Integration (Week 6)

**Goal:** Integrate with OpenWebUI frontend

**Tasks:**
1. Configure OpenWebUI
   - Point OpenWebUI to FastAPI backend
   - Configure authentication

2. Custom UI components (if needed)
   - Document preview
   - Progress indicators
   - Reasoning trace viewer

3. Testing
   - End-to-end testing with OpenWebUI
   - User acceptance testing

**Deliverables:**
- Working OpenWebUI frontend
- Seamless chat interface
- Document download functionality

**Acceptance Criteria:**
- [ ] Can chat with AI through OpenWebUI
- [ ] Documents are downloadable from UI
- [ ] Progress is visible during generation
- [ ] Reasoning traces are viewable (for debugging)

---

### Phase 7: Testing & Refinement (Week 7)

**Goal:** Comprehensive testing and bug fixing

**Tasks:**
1. Unit tests
   - Test all core components
   - >80% code coverage

2. Integration tests
   - Test workflows end-to-end
   - Test MCP integration
   - Test Copilot integration

3. E2E tests
   - Test full user flows
   - Generate BRD → Epic → Backlog

4. Performance testing
   - Load testing
   - Token usage optimization

**Deliverables:**
- Test suite with high coverage
- Performance benchmarks
- Bug fixes

**Acceptance Criteria:**
- [ ] >80% code coverage
- [ ] All integration tests passing
- [ ] E2E tests passing
- [ ] No critical bugs

---

### Phase 8: Documentation & Deployment (Week 8)

**Goal:** Production-ready deployment

**Tasks:**
1. Documentation
   - API reference
   - Skill development guide
   - Deployment guide
   - Troubleshooting guide

2. Deployment configuration
   - Docker images
   - Kubernetes manifests
   - Environment configuration

3. Monitoring and logging
   - Set up monitoring (Prometheus, Grafana)
   - Structured logging
   - Error tracking (Sentry)

**Deliverables:**
- Complete documentation
- Production deployment
- Monitoring dashboards

**Acceptance Criteria:**
- [ ] Documentation is complete
- [ ] System is deployed to production
- [ ] Monitoring is set up
- [ ] Logs are being collected

---

## 11. Testing Strategy

### 11.1 Test Pyramid

```
         ╱╲
        ╱  ╲
       ╱ E2E╲            ~10% - Full user flows
      ╱──────╲
     ╱        ╲
    ╱Integration╲        ~30% - Component integration
   ╱────────────╲
  ╱              ╲
 ╱   Unit Tests   ╲     ~60% - Individual components
╱──────────────────╲
```

### 11.2 Unit Tests

**Test Files:**
```
tests/unit/
├── test_reasoning_engine.py       # Reasoning logic
├── test_verification_engine.py    # Verification logic
├── test_copilot_client.py         # Copilot SDK wrapper
├── test_neo4j_client.py           # Neo4j MCP client
├── test_filesystem_client.py      # Filesystem MCP client
├── test_skill_loader.py           # Skill loading
├── test_context_manager.py        # Context window mgmt
└── test_fact_extractor.py         # Fact extraction
```

**Example Test:**

```python
# tests/unit/test_verification_engine.py

import pytest
from src.agentic.verification_engine import VerificationEngine, VerificationResult
from src.mcp.neo4j_client import Neo4jMCPClient
from src.mcp.filesystem_client import FilesystemMCPClient


@pytest.fixture
def neo4j_client(mocker):
    """Mock Neo4j client."""
    client = mocker.Mock(spec=Neo4jMCPClient)
    return client


@pytest.fixture
def fs_client(mocker):
    """Mock Filesystem client."""
    client = mocker.Mock(spec=FilesystemMCPClient)
    return client


@pytest.fixture
def verification_engine(neo4j_client, fs_client):
    """Create verification engine with mocked clients."""
    return VerificationEngine(neo4j_client, fs_client)


@pytest.mark.asyncio
async def test_verify_claim_entity_exists(verification_engine, neo4j_client, fs_client):
    """Test verification of entity existence."""
    
    # Setup mocks
    neo4j_client.query_entity.return_value = [
        {"name": "UserService", "type": "Class"}
    ]
    fs_client.read_file.return_value = "class UserService { ... }"
    
    # Execute
    result = await verification_engine.verify_claim(
        claim="UserService exists",
        context={}
    )
    
    # Assert
    assert result.verified == True
    assert result.confidence >= 0.9
    assert len(result.evidence) > 0
    assert len(result.hallucination_flags) == 0


@pytest.mark.asyncio
async def test_verify_claim_hallucination(verification_engine, neo4j_client, fs_client):
    """Test detection of hallucination."""
    
    # Setup mocks - no results
    neo4j_client.query_entity.return_value = []
    fs_client.read_file.return_value = "class OtherService { ... }"
    
    # Execute
    result = await verification_engine.verify_claim(
        claim="NonExistentService handles authentication",
        context={}
    )
    
    # Assert
    assert result.verified == False
    assert result.confidence < 0.5
    assert len(result.hallucination_flags) > 0
    assert "NonExistentService" in result.hallucination_flags[0]
```

### 11.3 Integration Tests

**Test Files:**
```
tests/integration/
├── test_brd_workflow.py           # Full BRD generation
├── test_epic_workflow.py          # Full Epic generation
├── test_verification_integration.py  # Verification with real MCP
├── test_copilot_skill_injection.py   # Skill injection
└── test_tool_orchestration.py     # MCP tool usage
```

**Example Test:**

```python
# tests/integration/test_brd_workflow.py

import pytest
from src.orchestration.workflow_engine import WorkflowEngine
from src.domain.document import Document, VerificationStatus


@pytest.mark.integration
@pytest.mark.asyncio
async def test_brd_generation_workflow(workflow_engine, test_session):
    """
    Test full BRD generation workflow.
    This test uses real MCP connections.
    """
    
    # Execute workflow
    document = await workflow_engine.execute_brd_workflow(
        session_id=test_session.session_id,
        component_name="Authentication"
    )
    
    # Assertions
    assert isinstance(document, Document)
    assert document.document_type == "brd"
    assert document.title is not None
    assert len(document.content) > 0
    
    # Verify verification was performed
    assert document.verification.status in [
        VerificationStatus.VERIFIED,
        VerificationStatus.PARTIAL
    ]
    assert document.verification.confidence > 0.7
    
    # Verify structure
    assert "# Business Requirement Document" in document.content
    assert "## Executive Summary" in document.content
    assert "## Functional Requirements" in document.content
```

### 11.4 E2E Tests

**Test Files:**
```
tests/e2e/
├── test_full_pipeline.py          # Complete user flow
└── test_openwebui_integration.py  # OpenWebUI integration
```

**Example Test:**

```python
# tests/e2e/test_full_pipeline.py

import pytest
from httpx import AsyncClient


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_user_flow():
    """
    Test complete user flow:
    1. User sends chat message
    2. System analyzes codebase
    3. Generates BRD
    4. Generates Epics
    5. Generates Backlog items
    6. User downloads documents
    """
    
    async with AsyncClient(base_url="http://localhost:8000") as client:
        # Step 1: Send chat message
        response = await client.post(
            "/api/v1/chat/message",
            json={
                "message": "Generate complete documentation for Authentication module",
                "context": {
                    "codebase_path": "/test/codebase"
                }
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        session_id = data['session_id']
        
        # Step 2: Wait for BRD generation
        # (In real test, would poll or use WebSocket)
        
        # Step 3: Verify BRD was created
        response = await client.get(f"/api/v1/documents?session_id={session_id}")
        assert response.status_code == 200
        documents = response.json()
        
        brd = next((d for d in documents if d['type'] == 'brd'), None)
        assert brd is not None
        
        # Step 4: Request Epic generation
        response = await client.post(
            "/api/v1/chat/message",
            json={
                "session_id": session_id,
                "message": "Generate epics from this BRD"
            }
        )
        
        assert response.status_code == 200
        
        # Step 5: Verify Epics created
        # ...
        
        # Step 6: Download document
        response = await client.get(f"/api/v1/documents/{brd['id']}/download")
        assert response.status_code == 200
        assert response.headers['content-type'] == 'text/markdown'
```

---

## 12. Deployment Architecture

### 12.1 Docker Compose (Development)

**File:** `docker-compose.yml`

```yaml
version: '3.8'

services:
  # FastAPI Backend
  api:
    build:
      context: .
      dockerfile: deploy/docker/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/ai_accelerator
      - REDIS_URL=redis://redis:6379/0
      - NEO4J_MCP_URL=http://neo4j-mcp:3000
      - GITHUB_COPILOT_API_KEY=${GITHUB_COPILOT_API_KEY}
    depends_on:
      - postgres
      - redis
      - neo4j
    volumes:
      - ./skills_definitions:/app/skills_definitions:ro
      - ./codebase:/codebase:ro
    networks:
      - ai-accelerator

  # PostgreSQL
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=ai_accelerator
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - ai-accelerator

  # Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    networks:
      - ai-accelerator

  # Neo4j (already running, just expose)
  neo4j:
    image: neo4j:5
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/password
    volumes:
      - neo4j_data:/data
    networks:
      - ai-accelerator

  # Neo4j MCP Server
  neo4j-mcp:
    image: neo4j-mcp-server:latest  # Assuming you have this
    ports:
      - "3000:3000"
    environment:
      - NEO4J_URI=bolt://neo4j:7687
      - NEO4J_USER=neo4j
      - NEO4J_PASSWORD=password
    depends_on:
      - neo4j
    networks:
      - ai-accelerator

  # OpenWebUI
  openwebui:
    image: ghcr.io/open-webui/open-webui:main
    ports:
      - "3001:8080"
    environment:
      - OPENAI_API_BASE_URL=http://api:8000/api/v1/openai  # Compatibility endpoint
    depends_on:
      - api
    volumes:
      - openwebui_data:/app/backend/data
    networks:
      - ai-accelerator

volumes:
  postgres_data:
  neo4j_data:
  openwebui_data:

networks:
  ai-accelerator:
    driver: bridge
```

### 12.2 Kubernetes Deployment

**File:** `deploy/k8s/deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-accelerator-api
  labels:
    app: ai-accelerator
    component: api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ai-accelerator
      component: api
  template:
    metadata:
      labels:
        app: ai-accelerator
        component: api
    spec:
      containers:
      - name: api
        image: ai-accelerator:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: ai-accelerator-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            configMapKeyRef:
              name: ai-accelerator-config
              key: redis-url
        - name: GITHUB_COPILOT_API_KEY
          valueFrom:
            secretKeyRef:
              name: ai-accelerator-secrets
              key: copilot-api-key
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /api/v1/health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/v1/health/ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        volumeMounts:
        - name: skills
          mountPath: /app/skills_definitions
          readOnly: true
      volumes:
      - name: skills
        configMap:
          name: copilot-skills

---
apiVersion: v1
kind: Service
metadata:
  name: ai-accelerator-api
spec:
  selector:
    app: ai-accelerator
    component: api
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

---

## 13. Success Criteria

### 13.1 Functional Requirements

| Requirement | Acceptance Criteria | Priority |
|-------------|---------------------|----------|
| Generate BRD | BRD contains all required sections with codebase-grounded content | P0 |
| Generate Epics | Epics have proper granularity (1-3 sprint scope) | P0 |
| Generate Backlogs | Backlog items are independently deliverable (1-5 days) | P0 |
| Zero Hallucinations | All claims verified against graph or source code | P0 |
| Clear Acceptance Criteria | All epics/backlogs have Given-When-Then criteria | P0 |
| Multi-turn Conversations | System maintains context across conversation | P1 |
| Streaming Responses | Real-time response streaming via WebSocket | P1 |

### 13.2 Non-Functional Requirements

| Requirement | Acceptance Criteria | Priority |
|-------------|---------------------|----------|
| Response Time | <5 seconds for simple queries, <30 seconds for document generation | P0 |
| Accuracy | >95% verification confidence for generated documents | P0 |
| Token Efficiency | Context stays within 8K tokens for 90% of conversations | P1 |
| Uptime | 99% uptime in production | P1 |
| Scalability | Handle 100 concurrent users | P2 |

### 13.3 Quality Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Code Coverage | >80% | pytest-cov |
| Verification Accuracy | >95% | Manual review of generated docs |
| Hallucination Rate | <5% | Automated verification checks |
| User Satisfaction | >4.0/5.0 | User surveys |

---

## 14. Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| GitHub Copilot API changes | High | Medium | Abstract Copilot behind interface, easy to swap |
| Neo4j graph incomplete/outdated | High | Medium | Implement graph freshness checks, fallback to code |
| Token limit overflow | Medium | High | Implement context window management |
| Verification too strict | Medium | Medium | Tunable confidence thresholds |
| Performance bottlenecks | Medium | Medium | Caching, async operations, load testing |

---

## 15. Next Steps for Claude Code

### To Begin Implementation:

1. **Read this specification thoroughly**
2. **Start with Phase 1** - Set up foundation
3. **Follow the directory structure** exactly as specified
4. **Implement components in order** - dependencies matter
5. **Write tests as you go** - don't leave testing for later
6. **Use the provided code examples** as starting templates
7. **Reference the API contracts** when building endpoints
8. **Follow the data models** for consistency

### Key Files to Create First:

1. `pyproject.toml` - Project configuration
2. `src/core/config.py` - Configuration management
3. `src/core/logging.py` - Logging setup
4. `src/mcp/neo4j_client.py` - Neo4j integration
5. `src/mcp/filesystem_client.py` - Filesystem integration
6. `src/copilot/sdk_client.py` - Copilot wrapper
7. `skills_definitions/*.yaml` - All skill definitions

### Questions to Ask if Unclear:

- "What should the Neo4j query look like for [specific case]?"
- "How should I structure the verification result for [document type]?"
- "What level of detail should [specific component] have?"
- "Are there any additional skills needed for [workflow]?"

---

## Appendix: Reference Links

- **GitHub Copilot CLI:** https://github.com/github/copilot-cli
- **GitHub Copilot SDK:** https://github.com/github/copilot-sdk
- **GitHub Copilot Skills:** https://github.blog/changelog/2025-12-18-github-copilot-now-supports-agent-skills/
- **OpenWebUI:** https://github.com/open-webui/open-webui
- **MCP Protocol:** https://modelcontextprotocol.io/
- **Neo4j Python Driver:** https://neo4j.com/docs/api/python-driver/current/
- **FastAPI:** https://fastapi.tiangolo.com/
- **Pydantic:** https://docs.pydantic.dev/

---

**END OF SPECIFICATION**

This specification is designed to be fed directly to Claude Code or any agentic coding tool for implementation. All components, APIs, data models, and workflows are fully specified to minimize ambiguity.