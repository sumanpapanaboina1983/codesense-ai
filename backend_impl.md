# **BRD Generator Backend - Implementation Plan for Claude Code**

## **Project Overview**

Build a Python backend that generates Business Requirements Documents (BRDs), Epics, and Backlogs by:
1. Querying Neo4j for code structure/relationships
2. Reading relevant source files via filesystem
3. Aggregating context intelligently
4. Using GitHub Copilot SDK to synthesize requirements documents

---

## **Technology Stack**

```yaml
Runtime: Python 3.11+
Core Dependencies:
  - github-copilot-sdk: ^0.1.13
  - neo4j: ^5.14.0
  - pydantic: ^2.5.0
  - jinja2: ^3.1.2
  - asyncio: stdlib
  - pathlib: stdlib

Development Dependencies:
  - pytest: ^7.4.0
  - pytest-asyncio: ^0.21.0
  - black: ^23.0.0
  - ruff: ^0.1.0
```

---

## **Project Structure**

```
brd-backend/
├── pyproject.toml              # Poetry/pip configuration
├── README.md                   # Setup and usage docs
├── .env.example                # Environment variables template
│
├── src/
│   └── brd_generator/
│       ├── __init__.py
│       ├── main.py            # Entry point
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── generator.py   # BRDGenerator orchestrator
│       │   ├── aggregator.py  # ContextAggregator
│       │   └── synthesizer.py # LLMSynthesizer
│       │
│       ├── mcp_clients/
│       │   ├── __init__.py
│       │   ├── base.py        # Base MCP client
│       │   ├── neo4j_client.py
│       │   └── filesystem_client.py
│       │
│       ├── models/
│       │   ├── __init__.py
│       │   ├── request.py     # BRDRequest model
│       │   ├── context.py     # Context models
│       │   └── output.py      # BRD/Epic/Backlog models
│       │
│       ├── templates/
│       │   ├── brd-template.md
│       │   ├── epic-template.md
│       │   └── backlog-template.md
│       │
│       ├── prompts/
│       │   ├── system-message.txt
│       │   ├── analysis-prompt.txt
│       │   └── synthesis-prompt.txt
│       │
│       └── utils/
│           ├── __init__.py
│           ├── token_counter.py
│           ├── cache.py
│           └── logger.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Pytest fixtures
│   ├── test_generator.py
│   ├── test_aggregator.py
│   ├── test_neo4j_client.py
│   └── test_integration.py
│
├── examples/
│   ├── sample_request.json
│   └── sample_output/
│       ├── brd.md
│       ├── epics.json
│       └── backlogs.json
│
└── scripts/
    ├── setup_neo4j.py        # Initialize Neo4j with sample data
    └── validate_brd.py       # BRD validation script
```

---

## **Phase 1: Project Initialization & Core Models**

### **Task 1.1: Project Setup**

**File:** `pyproject.toml`

```toml
[tool.poetry]
name = "brd-generator"
version = "0.1.0"
description = "AI-powered BRD generation using Neo4j and Copilot SDK"
authors = ["Your Name <you@example.com>"]
readme = "README.md"
python = "^3.11"

[tool.poetry.dependencies]
python = "^3.11"
github-copilot-sdk = "^0.1.13"
neo4j = "^5.14.0"
pydantic = "^2.5.0"
pydantic-settings = "^2.1.0"
jinja2 = "^3.1.2"
python-dotenv = "^1.0.0"
rich = "^13.7.0"  # For CLI output

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.0"
pytest-asyncio = "^0.21.0"
pytest-cov = "^4.1.0"
black = "^23.0.0"
ruff = "^0.1.0"
mypy = "^1.7.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.black]
line-length = 100
target-version = ['py311']

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**File:** `.env.example`

```bash
# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password_here

# GitHub Copilot
GITHUB_TOKEN=ghp_your_token_here

# Application
LOG_LEVEL=INFO
CACHE_TTL=600
MAX_CONTEXT_TOKENS=100000
```

**File:** `README.md`

```markdown
# BRD Generator Backend

AI-powered Business Requirements Document generation using code graph analysis.

## Prerequisites

- Python 3.11+
- Neo4j 5.x (running locally or remote)
- GitHub Copilot subscription
- GitHub Copilot CLI installed

## Quick Start

```bash
# Install dependencies
poetry install

# Copy environment template
cp .env.example .env
# Edit .env with your credentials

# Run example
poetry run python -m brd_generator.main --request "Add OAuth2 authentication"
```

## Architecture

[Brief architecture diagram]

## Development

```bash
# Run tests
poetry run pytest

# Format code
poetry run black .

# Lint
poetry run ruff check .
```
```

**Validation Criteria:**
- [ ] `poetry install` completes successfully
- [ ] `.env` file created with valid credentials
- [ ] Project imports work: `python -c "from brd_generator import __version__"`

---

### **Task 1.2: Pydantic Models**

**File:** `src/brd_generator/models/request.py`

```python
"""Request models for BRD generation."""
from pydantic import BaseModel, Field
from typing import Optional, List


class BRDRequest(BaseModel):
    """User request for BRD generation."""
    
    feature_description: str = Field(
        ..., 
        description="Natural language description of the feature",
        min_length=10
    )
    
    scope: Optional[str] = Field(
        default="full",
        description="Scope of analysis: 'full', 'component', or 'service'"
    )
    
    affected_components: Optional[List[str]] = Field(
        default=None,
        description="Specific components to analyze (if known)"
    )
    
    include_similar_features: bool = Field(
        default=True,
        description="Search for similar existing features"
    )
    
    output_format: str = Field(
        default="markdown",
        description="Output format: 'markdown', 'json', or 'jira'"
    )
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "feature_description": "Add OAuth2 authentication to user service",
                    "scope": "full",
                    "affected_components": ["auth-service", "user-service"],
                    "include_similar_features": True,
                    "output_format": "markdown"
                }
            ]
        }
    }
```

**File:** `src/brd_generator/models/context.py`

```python
"""Context models for aggregated information."""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any


class ComponentInfo(BaseModel):
    """Information about a code component."""
    name: str
    type: str  # 'service', 'module', 'class', etc.
    path: str
    dependencies: List[str] = []
    dependents: List[str] = []


class APIContract(BaseModel):
    """API contract definition."""
    endpoint: str
    method: str
    parameters: Dict[str, Any]
    response_schema: Optional[Dict[str, Any]] = None
    service: str


class DataModel(BaseModel):
    """Data model/entity definition."""
    name: str
    fields: Dict[str, str]
    relationships: List[str] = []


class FileContext(BaseModel):
    """Context from a source file."""
    path: str
    content: str
    summary: Optional[str] = None
    relevance_score: float = 0.0


class ArchitectureContext(BaseModel):
    """Aggregated architecture context."""
    components: List[ComponentInfo]
    dependencies: Dict[str, List[str]]
    api_contracts: List[APIContract]
    data_models: List[DataModel]


class ImplementationContext(BaseModel):
    """Implementation details context."""
    key_files: List[FileContext]
    patterns: List[str] = []
    configs: Dict[str, Any] = {}


class AggregatedContext(BaseModel):
    """Complete aggregated context for BRD generation."""
    request: str
    architecture: ArchitectureContext
    implementation: ImplementationContext
    similar_features: List[str] = []
    test_coverage: Optional[Dict[str, float]] = None
    
    @property
    def estimated_tokens(self) -> int:
        """Rough token count estimation."""
        # Simple heuristic: ~4 chars per token
        total_chars = len(self.model_dump_json())
        return total_chars // 4
```

**File:** `src/brd_generator/models/output.py`

```python
"""Output models for generated documents."""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class AcceptanceCriteria(BaseModel):
    """Acceptance criteria for a requirement."""
    criterion: str
    testable: bool = True


class Requirement(BaseModel):
    """A single requirement."""
    id: str
    title: str
    description: str
    priority: str  # 'high', 'medium', 'low'
    acceptance_criteria: List[AcceptanceCriteria]


class BRDDocument(BaseModel):
    """Business Requirements Document."""
    title: str
    version: str = "1.0"
    created_at: datetime = Field(default_factory=datetime.now)
    
    business_context: str
    objectives: List[str]
    functional_requirements: List[Requirement]
    technical_requirements: List[Requirement]
    dependencies: List[str]
    risks: List[str]
    
    def to_markdown(self) -> str:
        """Convert to Markdown format."""
        # Implementation in Task 3.4
        pass


class Epic(BaseModel):
    """Epic definition."""
    id: str
    title: str
    description: str
    components: List[str]
    estimated_effort: str  # 'small', 'medium', 'large'
    stories: List[str] = []  # Story IDs


class UserStory(BaseModel):
    """User story/backlog item."""
    id: str
    epic_id: str
    title: str
    description: str
    as_a: str  # User role
    i_want: str  # Capability
    so_that: str  # Benefit
    acceptance_criteria: List[AcceptanceCriteria]
    technical_notes: Optional[str] = None
    estimated_points: Optional[int] = None
    files_to_modify: List[str] = []


class BRDOutput(BaseModel):
    """Complete BRD generation output."""
    brd: BRDDocument
    epics: List[Epic]
    backlogs: List[UserStory]
    
    metadata: Dict[str, Any] = {
        "neo4j_queries": 0,
        "files_analyzed": 0,
        "generation_time_ms": 0
    }
```

**Validation Criteria:**
- [ ] All models import successfully
- [ ] Example instances can be created and serialized to JSON
- [ ] Validation works: `BRDRequest(feature_description="test")` fails validation

---

## **Phase 2: MCP Client Infrastructure**

### **Task 2.1: Base MCP Client**

**File:** `src/brd_generator/mcp_clients/base.py`

```python
"""Base MCP client abstraction."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class MCPClient(ABC):
    """Abstract base class for MCP clients."""
    
    def __init__(self, server_name: str):
        self.server_name = server_name
        self._connected = False
    
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to MCP server."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to MCP server."""
        pass
    
    @abstractmethod
    async def call_tool(
        self, 
        tool_name: str, 
        parameters: Dict[str, Any]
    ) -> Any:
        """Call a tool provided by the MCP server."""
        pass
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


class MCPToolError(Exception):
    """Raised when MCP tool call fails."""
    pass
```

**File:** `src/brd_generator/utils/logger.py`

```python
"""Logging configuration."""
import logging
import sys
from rich.logging import RichHandler

def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Configure logger with Rich handler."""
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )
    return logging.getLogger(name)
```

**Validation Criteria:**
- [ ] Base classes import successfully
- [ ] Abstract methods are enforced (can't instantiate MCPClient directly)

---

### **Task 2.2: Neo4j MCP Client**

**File:** `src/brd_generator/mcp_clients/neo4j_client.py`

```python
"""Neo4j MCP client for code graph queries."""
from typing import Any, Dict, List, Optional
from .base import MCPClient, MCPToolError
import logging

logger = logging.getLogger(__name__)


class Neo4jMCPClient(MCPClient):
    """Client for Neo4j MCP server."""
    
    def __init__(self):
        super().__init__("neo4j-code-graph")
        # Note: Actual MCP connection will be through Copilot SDK
        # This is a logical wrapper that maps to MCP tool calls
    
    async def connect(self) -> None:
        """Initialize connection (placeholder for MCP context)."""
        logger.info(f"Neo4j MCP client ready: {self.server_name}")
        self._connected = True
    
    async def disconnect(self) -> None:
        """Close connection."""
        self._connected = False
    
    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """
        Call Neo4j MCP tool.
        
        In practice, this will be invoked by Copilot SDK's session.send()
        with the LLM choosing which tools to call.
        
        This method exists for:
        1. Direct tool calls during testing
        2. Explicit calls when you know exactly what you need
        """
        if not self._connected:
            raise MCPToolError("Neo4j MCP client not connected")
        
        # This would be replaced by actual MCP protocol call
        # For now, it's a placeholder for the interface
        raise NotImplementedError(
            "Direct MCP calls not implemented. Use Copilot SDK session."
        )
    
    async def query_code_structure(self, cypher_query: str) -> Dict[str, Any]:
        """
        Execute Cypher query against code graph.
        
        Args:
            cypher_query: Cypher query string
            
        Returns:
            Query results as dict
        """
        return await self.call_tool("query_code_structure", {
            "cypher_query": cypher_query
        })
    
    async def get_component_dependencies(
        self, 
        component_name: str
    ) -> Dict[str, List[str]]:
        """
        Get upstream and downstream dependencies for a component.
        
        Args:
            component_name: Name of the component
            
        Returns:
            Dict with 'upstream' and 'downstream' lists
        """
        return await self.call_tool("get_component_dependencies", {
            "component_name": component_name
        })
    
    async def get_api_contracts(self, service_name: str) -> List[Dict[str, Any]]:
        """
        Get API contracts for a service.
        
        Args:
            service_name: Name of the service
            
        Returns:
            List of API contract definitions
        """
        return await self.call_tool("get_api_contracts", {
            "service_name": service_name
        })
    
    async def search_similar_features(
        self, 
        description: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for similar features using vector similarity.
        
        Args:
            description: Feature description
            limit: Max results to return
            
        Returns:
            List of similar features with relevance scores
        """
        return await self.call_tool("search_similar_features", {
            "description": description,
            "limit": limit
        })
```

**Validation Criteria:**
- [ ] Client instantiates successfully
- [ ] Methods have proper type hints
- [ ] Logger outputs correctly

---

### **Task 2.3: Filesystem MCP Client**

**File:** `src/brd_generator/mcp_clients/filesystem_client.py`

```python
"""Filesystem MCP client for source code access."""
from typing import Any, Dict, List, Optional
from pathlib import Path
from .base import MCPClient, MCPToolError
import logging

logger = logging.getLogger(__name__)


class FilesystemMCPClient(MCPClient):
    """Client for Filesystem MCP server."""
    
    def __init__(self, workspace_root: Optional[Path] = None):
        super().__init__("filesystem-reader")
        self.workspace_root = workspace_root or Path.cwd()
    
    async def connect(self) -> None:
        """Initialize connection."""
        logger.info(f"Filesystem MCP client ready: {self.workspace_root}")
        self._connected = True
    
    async def disconnect(self) -> None:
        """Close connection."""
        self._connected = False
    
    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Call Filesystem MCP tool (placeholder)."""
        if not self._connected:
            raise MCPToolError("Filesystem MCP client not connected")
        
        raise NotImplementedError(
            "Direct MCP calls not implemented. Use Copilot SDK session."
        )
    
    async def read_file(self, path: str) -> str:
        """
        Read file content.
        
        Args:
            path: Relative or absolute file path
            
        Returns:
            File content as string
        """
        return await self.call_tool("read_file", {"path": path})
    
    async def search_files(
        self, 
        pattern: str, 
        include_content: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search files by glob pattern.
        
        Args:
            pattern: Glob pattern (e.g., '**/*.py')
            include_content: Whether to include file contents
            
        Returns:
            List of matching files with metadata
        """
        return await self.call_tool("search_files", {
            "pattern": pattern,
            "include_content": include_content
        })
    
    async def get_file_metadata(self, path: str) -> Dict[str, Any]:
        """
        Get file metadata (git history, author, etc.).
        
        Args:
            path: File path
            
        Returns:
            Metadata dict
        """
        return await self.call_tool("get_file_metadata", {"path": path})
    
    async def read_multiple_files(self, paths: List[str]) -> Dict[str, str]:
        """
        Batch read multiple files.
        
        Args:
            paths: List of file paths
            
        Returns:
            Dict mapping path -> content
        """
        return await self.call_tool("read_multiple_files", {"paths": paths})
```

**Validation Criteria:**
- [ ] Client instantiates with default workspace
- [ ] Method signatures match design specification

---

## **Phase 3: Core Generation Logic**

### **Task 3.1: Context Aggregator**

**File:** `src/brd_generator/core/aggregator.py`

```python
"""Context aggregation from multiple sources."""
from typing import Dict, List, Optional, Any
from ..models.context import (
    AggregatedContext,
    ArchitectureContext,
    ImplementationContext,
    ComponentInfo,
    FileContext
)
from ..mcp_clients.neo4j_client import Neo4jMCPClient
from ..mcp_clients.filesystem_client import FilesystemMCPClient
from ..utils.token_counter import estimate_tokens
import logging

logger = logging.getLogger(__name__)


class ContextAggregator:
    """Aggregates context from Neo4j and Filesystem MCPs."""
    
    def __init__(
        self,
        neo4j_client: Neo4jMCPClient,
        filesystem_client: FilesystemMCPClient,
        max_tokens: int = 100000
    ):
        self.neo4j = neo4j_client
        self.filesystem = filesystem_client
        self.max_tokens = max_tokens
    
    async def build_context(
        self,
        request: str,
        affected_components: Optional[List[str]] = None,
        include_similar: bool = True
    ) -> AggregatedContext:
        """
        Build aggregated context from all sources.
        
        Args:
            request: User's feature request
            affected_components: Known affected components
            include_similar: Search for similar features
            
        Returns:
            Aggregated context ready for LLM
        """
        logger.info("Building aggregated context...")
        
        # Phase 1: Get architecture from Neo4j
        architecture = await self._get_architecture_context(
            request, 
            affected_components
        )
        
        # Phase 2: Get implementation details from filesystem
        implementation = await self._get_implementation_context(architecture)
        
        # Phase 3: Find similar features
        similar_features = []
        if include_similar:
            similar_features = await self._find_similar_features(request)
        
        # Build complete context
        context = AggregatedContext(
            request=request,
            architecture=architecture,
            implementation=implementation,
            similar_features=similar_features
        )
        
        # Check token budget
        if context.estimated_tokens > self.max_tokens:
            logger.warning(
                f"Context exceeds token limit ({context.estimated_tokens} > {self.max_tokens})"
            )
            context = await self._compress_context(context)
        
        logger.info(f"Context built: ~{context.estimated_tokens} tokens")
        return context
    
    async def _get_architecture_context(
        self,
        request: str,
        affected_components: Optional[List[str]]
    ) -> ArchitectureContext:
        """Extract architecture info from Neo4j."""
        
        # TODO: Implement Neo4j queries
        # For now, return placeholder
        
        components = []
        if affected_components:
            for comp_name in affected_components:
                # Would call: self.neo4j.get_component_dependencies(comp_name)
                components.append(ComponentInfo(
                    name=comp_name,
                    type="service",
                    path=f"/services/{comp_name}",
                    dependencies=[],
                    dependents=[]
                ))
        
        return ArchitectureContext(
            components=components,
            dependencies={},
            api_contracts=[],
            data_models=[]
        )
    
    async def _get_implementation_context(
        self,
        architecture: ArchitectureContext
    ) -> ImplementationContext:
        """Extract implementation details from filesystem."""
        
        # TODO: Implement file reading based on architecture
        # For now, return placeholder
        
        key_files = []
        
        return ImplementationContext(
            key_files=key_files,
            patterns=[],
            configs={}
        )
    
    async def _find_similar_features(self, request: str) -> List[str]:
        """Search for similar existing features."""
        
        # TODO: Implement vector similarity search
        # For now, return empty
        
        return []
    
    async def _compress_context(
        self,
        context: AggregatedContext
    ) -> AggregatedContext:
        """Compress context to fit token budget."""
        
        logger.info("Compressing context to fit token budget...")
        
        # Strategy 1: Summarize file contents
        for file_ctx in context.implementation.key_files:
            if len(file_ctx.content) > 1000:
                # Truncate large files, keep first/last portions
                file_ctx.summary = file_ctx.content[:500] + "\n...\n" + file_ctx.content[-500:]
                file_ctx.content = file_ctx.summary
        
        # Strategy 2: Reduce number of components
        if len(context.architecture.components) > 10:
            # Keep only top 10 most relevant
            context.architecture.components = context.architecture.components[:10]
        
        return context
```

**File:** `src/brd_generator/utils/token_counter.py`

```python
"""Token estimation utilities."""

def estimate_tokens(text: str) -> int:
    """
    Estimate token count using simple heuristic.
    
    Args:
        text: Text to estimate
        
    Returns:
        Estimated token count
    """
    # Simple heuristic: ~4 characters per token
    # More accurate: use tiktoken library
    return len(text) // 4
```

**Validation Criteria:**
- [ ] ContextAggregator instantiates with clients
- [ ] `build_context()` returns AggregatedContext
- [ ] Token compression works when context exceeds limit

---

### **Task 3.2: LLM Synthesizer**

**File:** `src/brd_generator/core/synthesizer.py`

```python
"""LLM synthesis using Copilot SDK."""
from typing import Optional
from copilot import CopilotClient, Session
from ..models.context import AggregatedContext
from ..models.output import BRDDocument, Epic, UserStory
from pathlib import Path
import logging
import json

logger = logging.getLogger(__name__)


class LLMSynthesizer:
    """Synthesizes BRD/Epics/Backlogs using LLM."""
    
    def __init__(self, session: Session, templates_dir: Path):
        self.session = session
        self.templates_dir = templates_dir
    
    async def generate_brd(self, context: AggregatedContext) -> BRDDocument:
        """
        Generate BRD from context.
        
        Args:
            context: Aggregated context
            
        Returns:
            Generated BRD document
        """
        logger.info("Generating BRD...")
        
        # Load template
        template = self._load_template("brd-template.md")
        
        # Load prompts
        analysis_prompt = self._load_prompt("analysis-prompt.txt")
        
        # Stage 1: Analysis
        analysis = await self._analyze_context(context, analysis_prompt)
        
        # Stage 2: BRD Generation
        brd_prompt = self._build_brd_prompt(context, analysis, template)
        
        response = await self.session.send({"prompt": brd_prompt})
        
        # Parse response into BRDDocument
        # TODO: Implement proper parsing
        brd = BRDDocument(
            title=f"BRD: {context.request}",
            business_context="Generated context...",
            objectives=[],
            functional_requirements=[],
            technical_requirements=[],
            dependencies=[],
            risks=[]
        )
        
        return brd
    
    async def generate_epics(
        self,
        context: AggregatedContext,
        brd: BRDDocument
    ) -> List[Epic]:
        """Generate epics from BRD and context."""
        logger.info("Generating epics...")
        
        # TODO: Implement epic generation
        
        return []
    
    async def generate_backlogs(
        self,
        context: AggregatedContext,
        epics: List[Epic]
    ) -> List[UserStory]:
        """Generate user stories from epics."""
        logger.info("Generating user stories...")
        
        # TODO: Implement backlog generation
        
        return []
    
    async def _analyze_context(
        self,
        context: AggregatedContext,
        analysis_prompt: str
    ) -> str:
        """First stage: analyze the context."""
        
        prompt = analysis_prompt.format(
            request=context.request,
            components=json.dumps([c.model_dump() for c in context.architecture.components], indent=2),
            files_count=len(context.implementation.key_files)
        )
        
        # Send to LLM for analysis
        response = await self.session.send({"prompt": prompt})
        
        # Extract text from response
        # TODO: Handle streaming response properly
        return "Analysis placeholder"
    
    def _build_brd_prompt(
        self,
        context: AggregatedContext,
        analysis: str,
        template: str
    ) -> str:
        """Build the BRD generation prompt."""
        
        return f"""
        Using this analysis:
        {analysis}
        
        And this template:
        {template}
        
        Generate a comprehensive Business Requirements Document for:
        {context.request}
        
        Architecture context:
        - Components: {len(context.architecture.components)}
        - Dependencies: {len(context.architecture.dependencies)}
        - API Contracts: {len(context.architecture.api_contracts)}
        
        Include:
        1. Business Context
        2. Objectives
        3. Functional Requirements
        4. Technical Requirements
        5. Dependencies & Risks
        
        Format: Follow the template structure exactly.
        """
    
    def _load_template(self, filename: str) -> str:
        """Load template file."""
        path = self.templates_dir / filename
        if not path.exists():
            logger.warning(f"Template not found: {filename}")
            return ""
        return path.read_text()
    
    def _load_prompt(self, filename: str) -> str:
        """Load prompt file."""
        prompts_dir = self.templates_dir.parent / "prompts"
        path = prompts_dir / filename
        if not path.exists():
            logger.warning(f"Prompt not found: {filename}")
            return ""
        return path.read_text()
```

**Validation Criteria:**
- [ ] Synthesizer instantiates with session
- [ ] Template loading works
- [ ] Prompt building produces valid strings

---

### **Task 3.3: Main Generator Orchestrator**

**File:** `src/brd_generator/core/generator.py`

```python
"""Main BRD Generator orchestrator."""
from typing import Optional
from copilot import CopilotClient
from ..models.request import BRDRequest
from ..models.output import BRDOutput
from ..mcp_clients.neo4j_client import Neo4jMCPClient
from ..mcp_clients.filesystem_client import FilesystemMCPClient
from .aggregator import ContextAggregator
from .synthesizer import LLMSynthesizer
from pathlib import Path
import logging
import time

logger = logging.getLogger(__name__)


class BRDGenerator:
    """Main orchestrator for BRD generation."""
    
    def __init__(
        self,
        copilot_client: CopilotClient,
        workspace_root: Optional[Path] = None
    ):
        self.copilot = copilot_client
        self.workspace_root = workspace_root or Path.cwd()
        
        # Initialize MCP clients
        self.neo4j_client = Neo4jMCPClient()
        self.filesystem_client = FilesystemMCPClient(workspace_root)
        
        # Will be set in initialize()
        self.session = None
        self.aggregator = None
        self.synthesizer = None
    
    async def initialize(self):
        """Initialize Copilot session and components."""
        logger.info("Initializing BRD Generator...")
        
        # Connect MCP clients
        await self.neo4j_client.connect()
        await self.filesystem_client.connect()
        
        # Create Copilot session
        self.session = await self.copilot.create_session({
            "model": "gpt-5",
            "system_message": self._load_system_message()
        })
        
        # Initialize components
        self.aggregator = ContextAggregator(
            self.neo4j_client,
            self.filesystem_client
        )
        
        templates_dir = Path(__file__).parent.parent / "templates"
        self.synthesizer = LLMSynthesizer(self.session, templates_dir)
        
        logger.info("BRD Generator initialized")
    
    async def generate(self, request: BRDRequest) -> BRDOutput:
        """
        Generate BRD, epics, and backlogs.
        
        Args:
            request: BRD generation request
            
        Returns:
            Complete BRD output
        """
        start_time = time.time()
        logger.info(f"Generating BRD for: {request.feature_description}")
        
        # Phase 1: Build context
        context = await self.aggregator.build_context(
            request=request.feature_description,
            affected_components=request.affected_components,
            include_similar=request.include_similar_features
        )
        
        # Phase 2: Generate BRD
        brd = await self.synthesizer.generate_brd(context)
        
        # Phase 3: Generate Epics
        epics = await self.synthesizer.generate_epics(context, brd)
        
        # Phase 4: Generate Backlogs
        backlogs = await self.synthesizer.generate_backlogs(context, epics)
        
        # Build output
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        output = BRDOutput(
            brd=brd,
            epics=epics,
            backlogs=backlogs,
            metadata={
                "neo4j_queries": 0,  # TODO: Track actual queries
                "files_analyzed": len(context.implementation.key_files),
                "generation_time_ms": elapsed_ms
            }
        )
        
        logger.info(f"BRD generation complete in {elapsed_ms}ms")
        return output
    
    async def cleanup(self):
        """Cleanup resources."""
        if self.session:
            await self.session.destroy()
        await self.neo4j_client.disconnect()
        await self.filesystem_client.disconnect()
    
    def _load_system_message(self) -> str:
        """Load system message for Copilot."""
        prompts_dir = Path(__file__).parent.parent / "prompts"
        path = prompts_dir / "system-message.txt"
        
        if path.exists():
            return path.read_text()
        
        # Default system message
        return """
        You are a technical product manager with deep codebase knowledge.

        Available Context:
        - Code graph showing component relationships
        - Source files with implementation patterns
        - API contracts and data models
        - Similar features for reference

        Your Task:
        Generate production-ready requirements documents that:
        1. Reflect actual codebase architecture
        2. Reference existing patterns and conventions
        3. Identify integration points accurately
        4. Include realistic effort estimates

        Format: Use provided templates exactly.
        """
```

**Validation Criteria:**
- [ ] Generator instantiates
- [ ] `initialize()` completes without errors
- [ ] `generate()` accepts BRDRequest and returns BRDOutput

---

### **Task 3.4: Template and Prompt Files**

**File:** `src/brd_generator/templates/brd-template.md`

```markdown
# Business Requirements Document: {TITLE}

**Version:** {VERSION}  
**Date:** {DATE}  
**Status:** Draft

---

## 1. Business Context

{BUSINESS_CONTEXT}

## 2. Objectives

{OBJECTIVES}

## 3. Functional Requirements

{FUNCTIONAL_REQUIREMENTS}

## 4. Technical Requirements

{TECHNICAL_REQUIREMENTS}

## 5. Dependencies

{DEPENDENCIES}

## 6. Risks and Mitigation

{RISKS}

## 7. Acceptance Criteria

{ACCEPTANCE_CRITERIA}

---

**Approval:**
- Product Owner: _______________
- Technical Lead: _______________
```

**File:** `src/brd_generator/prompts/system-message.txt`

```text
You are a technical product manager with deep codebase knowledge.

Available Context:
- Code graph showing component relationships
- Source files with implementation patterns
- API contracts and data models
- Similar features for reference

Your Task:
Generate production-ready requirements documents that:
1. Reflect actual codebase architecture
2. Reference existing patterns and conventions
3. Identify integration points accurately
4. Include realistic effort estimates

Format: Use provided templates exactly.
Output: Well-structured, actionable requirements.
```

**File:** `src/brd_generator/prompts/analysis-prompt.txt`

```text
Analyze the following feature request and codebase context:

Feature Request: {request}

Architecture Components:
{components}

Files Available: {files_count}

Provide:
1. Scope assessment (which components affected)
2. Integration points identified
3. Similar existing features (if any)
4. Key technical challenges
5. Recommended implementation approach

Be specific and reference actual component names and file paths.
```

**Validation Criteria:**
- [ ] Templates exist and contain placeholders
- [ ] Prompts are well-formatted

---

## **Phase 4: Entry Point & CLI**

### **Task 4.1: Main Entry Point**

**File:** `src/brd_generator/main.py`

```python
"""Main entry point for BRD Generator."""
import asyncio
import argparse
import json
from pathlib import Path
from copilot import CopilotClient
from .core.generator import BRDGenerator
from .models.request import BRDRequest
from .utils.logger import setup_logger
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv()

logger = setup_logger("brd_generator")


async def main():
    """Main async entry point."""
    parser = argparse.ArgumentParser(
        description="Generate BRDs, Epics, and Backlogs using AI"
    )
    parser.add_argument(
        "--request",
        required=True,
        help="Feature description"
    )
    parser.add_argument(
        "--scope",
        default="full",
        choices=["full", "component", "service"],
        help="Analysis scope"
    )
    parser.add_argument(
        "--components",
        nargs="+",
        help="Specific components to analyze"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Output directory"
    )
    parser.add_argument(
        "--format",
        default="markdown",
        choices=["markdown", "json", "jira"],
        help="Output format"
    )
    
    args = parser.parse_args()
    
    # Build request
    request = BRDRequest(
        feature_description=args.request,
        scope=args.scope,
        affected_components=args.components,
        output_format=args.format
    )
    
    logger.info(f"Starting BRD generation: {request.feature_description}")
    
    # Initialize Copilot
    copilot_client = CopilotClient()
    
    try:
        await copilot_client.start()
        logger.info("Copilot CLI started")
        
        # Initialize generator
        generator = BRDGenerator(copilot_client)
        await generator.initialize()
        
        # Generate BRD
        output = await generator.generate(request)
        
        # Save output
        args.output.mkdir(parents=True, exist_ok=True)
        
        # Save as JSON
        output_file = args.output / "brd_output.json"
        with open(output_file, "w") as f:
            json.dump(output.model_dump(), f, indent=2, default=str)
        
        logger.info(f"Output saved to: {output_file}")
        
        # Save BRD as markdown
        brd_file = args.output / "BRD.md"
        with open(brd_file, "w") as f:
            f.write(output.brd.to_markdown())
        
        logger.info(f"BRD saved to: {brd_file}")
        
        # Cleanup
        await generator.cleanup()
        
    except Exception as e:
        logger.error(f"Error during generation: {e}", exc_info=True)
        sys.exit(1)
        
    finally:
        await copilot_client.stop()
        logger.info("Copilot CLI stopped")


def run():
    """Synchronous wrapper for async main."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
```

**Validation Criteria:**
- [ ] Script runs: `python -m brd_generator.main --help`
- [ ] Arguments parse correctly
- [ ] Copilot client starts and stops cleanly

---

## **Phase 5: Testing Infrastructure**

### **Task 5.1: Test Configuration**

**File:** `tests/conftest.py`

```python
"""Pytest configuration and fixtures."""
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def sample_request():
    """Sample BRD request for testing."""
    from brd_generator.models.request import BRDRequest
    
    return BRDRequest(
        feature_description="Add OAuth2 authentication to user service",
        scope="full",
        affected_components=["auth-service", "user-service"]
    )


@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j MCP client."""
    from brd_generator.mcp_clients.neo4j_client import Neo4jMCPClient
    
    client = AsyncMock(spec=Neo4jMCPClient)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.get_component_dependencies = AsyncMock(return_value={
        "upstream": ["database"],
        "downstream": ["api-gateway"]
    })
    
    return client


@pytest.fixture
def mock_filesystem_client():
    """Mock Filesystem MCP client."""
    from brd_generator.mcp_clients.filesystem_client import FilesystemMCPClient
    
    client = AsyncMock(spec=FilesystemMCPClient)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.read_file = AsyncMock(return_value="# Sample file content")
    
    return client


@pytest.fixture
def mock_copilot_session():
    """Mock Copilot session."""
    session = AsyncMock()
    session.send = AsyncMock(return_value="Generated BRD content...")
    session.destroy = AsyncMock()
    
    return session
```

**File:** `tests/test_generator.py`

```python
"""Tests for BRDGenerator."""
import pytest
from brd_generator.core.generator import BRDGenerator
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_generator_initialization():
    """Test generator initializes correctly."""
    mock_client = AsyncMock()
    mock_client.create_session = AsyncMock(return_value=AsyncMock())
    
    generator = BRDGenerator(mock_client)
    await generator.initialize()
    
    assert generator.session is not None
    assert generator.aggregator is not None
    assert generator.synthesizer is not None


@pytest.mark.asyncio
async def test_generate_brd(sample_request, mock_copilot_session):
    """Test BRD generation flow."""
    mock_client = AsyncMock()
    mock_client.create_session = AsyncMock(return_value=mock_copilot_session)
    
    generator = BRDGenerator(mock_client)
    await generator.initialize()
    
    # Mock aggregator
    generator.aggregator.build_context = AsyncMock()
    
    # Mock synthesizer
    from brd_generator.models.output import BRDDocument
    mock_brd = BRDDocument(
        title="Test BRD",
        business_context="Test context",
        objectives=[],
        functional_requirements=[],
        technical_requirements=[],
        dependencies=[],
        risks=[]
    )
    generator.synthesizer.generate_brd = AsyncMock(return_value=mock_brd)
    generator.synthesizer.generate_epics = AsyncMock(return_value=[])
    generator.synthesizer.generate_backlogs = AsyncMock(return_value=[])
    
    # Generate
    output = await generator.generate(sample_request)
    
    assert output.brd is not None
    assert output.brd.title == "Test BRD"
```

**Validation Criteria:**
- [ ] Tests run: `pytest tests/ -v`
- [ ] All fixtures load correctly
- [ ] Mock tests pass

---

## **Phase 6: Documentation & Examples**

### **Task 6.1: Example Files**

**File:** `examples/sample_request.json`

```json
{
  "feature_description": "Add OAuth2 authentication to the user service, supporting Google and GitHub as identity providers",
  "scope": "full",
  "affected_components": ["auth-service", "user-service", "api-gateway"],
  "include_similar_features": true,
  "output_format": "markdown"
}
```

**File:** `scripts/setup_neo4j.py`

```python
"""Setup Neo4j with sample code graph data."""
from neo4j import GraphDatabase
import os

def create_sample_graph():
    """Create sample code graph in Neo4j."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    with driver.session() as session:
        # Create sample nodes
        session.run("""
            CREATE (auth:Service {name: 'auth-service', type: 'microservice'})
            CREATE (user:Service {name: 'user-service', type: 'microservice'})
            CREATE (api:Service {name: 'api-gateway', type: 'gateway'})
            CREATE (db:Database {name: 'user-db', type: 'postgresql'})
            
            CREATE (auth)-[:DEPENDS_ON]->(db)
            CREATE (user)-[:DEPENDS_ON]->(auth)
            CREATE (api)-[:ROUTES_TO]->(user)
            CREATE (api)-[:ROUTES_TO]->(auth)
        """)
        
        print("Sample graph created successfully!")
    
    driver.close()

if __name__ == "__main__":
    create_sample_graph()
```

---

## **Final Validation Checklist**

**After completing all phases:**

- [ ] All dependencies install: `poetry install`
- [ ] Environment configured: `.env` file exists
- [ ] Project imports: `python -c "from brd_generator import BRDGenerator"`
- [ ] Tests pass: `pytest tests/ -v`
- [ ] CLI runs: `python -m brd_generator.main --request "test" --output /tmp/test`
- [ ] Copilot CLI detected: `copilot --version`
- [ ] Neo4j accessible: `python scripts/setup_neo4j.py`
- [ ] Code formatted: `black . && ruff check .`

---

## **Next Steps After Backend Complete**

1. **Tauri Desktop Integration** - Wrap backend with Tauri frontend
2. **MCP Server Implementation** - Wrap generator as MCP server
3. **Skill Definition** - Create `.github/skills/brd-generation/`
4. **Production Hardening** - Error handling, logging, monitoring

---

**This plan is ready to feed to Claude Code. Each phase builds incrementally with clear validation points.**