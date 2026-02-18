"""Wiki generation service for DeepWiki-style documentation.

Generates comprehensive, concept-based documentation from code analysis.
Uses Copilot SDK for LLM-powered intelligent content generation.
"""

import asyncio
import time
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import (
    WikiDB,
    WikiPageDB,
    WikiStatus,
    WikiPageType,
    RepositoryDB,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# LLM Prompts for Wiki Generation
# =============================================================================

OVERVIEW_PROMPT = """You are a technical documentation expert analyzing source code to generate DeepWiki-style documentation.

## Repository Information
- **Name:** {repo_name}
- **Description:** {description}
- **Language:** {language}

## Codebase Statistics
- Total Files: {total_files}
- Total Classes: {total_classes}
- Total Functions: {total_functions}
- Modules: {module_count}

## Discovered Modules
{modules_info}

## Key Classes
{classes_info}

## SOURCE CODE ANALYSIS
The following is actual source code from key classes. Analyze this code to understand what the system does:

{source_code_snippets}

## Instructions
Based on your analysis of the ACTUAL SOURCE CODE above, generate a comprehensive overview page in Markdown format with:

1. **Overview Section**: Explain what this system ACTUALLY does based on the code you analyzed (2-3 paragraphs). Be specific about the functionality you observed in the code.
2. **Quick Stats Table**: A markdown table with the key metrics
3. **Tech Stack**: Identify the ACTUAL technologies, frameworks, and libraries used based on imports and annotations in the code
4. **Architecture Overview**: A Mermaid diagram showing how components actually interact (based on dependencies and method calls you see in the code)
5. **Key Features**: List the main features/capabilities you identified from analyzing the code
6. **Key Modules**: A list of modules with descriptions based on what their code actually does
7. **Quick Links**: Links to other wiki pages (architecture, getting-started, api)

IMPORTANT: Your documentation should reflect what the code ACTUALLY does, not just generic descriptions.
Output ONLY the markdown content, no additional explanation."""

ARCHITECTURE_PROMPT = """You are a software architect analyzing source code to document the system's architecture.

## Repository: {repo_name}

## Discovered Components

### Controllers (Presentation Layer)
{controllers_info}

### Services (Business Layer)
{services_info}

### Repositories/DAOs (Data Layer)
{repositories_info}

### Other Key Classes
{other_classes_info}

### API Endpoints
{endpoints_info}

## ACTUAL SOURCE CODE FOR ANALYSIS
Analyze the following source code to understand the real architecture:

{source_code_snippets}

## Instructions
Based on your analysis of the ACTUAL SOURCE CODE above, generate architecture documentation with:

1. **System Overview**: Describe the architecture based on what you see in the code (imports, annotations, class hierarchies, method calls)
2. **Component Diagram**: A Mermaid diagram showing ACTUAL component interactions based on the code's imports and method calls
3. **Layer Responsibilities**: Based on what each layer's code actually does
4. **Key Design Patterns**: Identify patterns you ACTUALLY SEE in the code (look for factory methods, singletons, strategy pattern, etc.)
5. **Request Flow**: A Mermaid sequence diagram showing how a request flows through the code (based on method calls you observe)
6. **Dependencies**: Actual dependencies you see in imports and constructor injection

IMPORTANT: Base your documentation on what the code ACTUALLY shows, not assumptions.
Output ONLY the markdown content."""

MODULE_PROMPT = """You are analyzing source code to document a specific module/package.

## Module: {module_name}
## Repository: {repo_name}

## Module Contents

### Source Files
{source_files}

### Classes in this Module
{classes_info}

### Functions/Methods
{functions_info}

### API Endpoints in this Module
{endpoints_info}

## ACTUAL SOURCE CODE FROM THIS MODULE
Analyze the following source code to understand what this module does:

{source_code_snippets}

## Instructions
Based on your analysis of the ACTUAL SOURCE CODE above, generate module documentation with:

1. **Details Section**: List source files as bullet points
2. **Overview**: Explain what this module ACTUALLY does based on the code you analyzed. Be specific about the functionality.
3. **Features Table**: A markdown table listing the actual features/capabilities you identified from the code
4. **Key Components**: For each class, explain what it actually does based on its methods and logic
5. **API Endpoints**: Table of endpoints with descriptions of what each endpoint actually does (based on the handler code)
6. **Data Flow Diagram**: A Mermaid diagram showing how data actually flows through this module (based on method calls)
7. **Usage Examples**: Show how this module is used based on the actual code patterns

IMPORTANT: Your documentation should explain what the code ACTUALLY does, not generic descriptions.
Output ONLY the markdown content."""

CLASS_PROMPT = """You are analyzing source code to document a specific class.

## Class: {class_name}
## File: {file_path}
## Type: {class_type}

## Dependencies
This class depends on: {dependencies}

## Used By
This class is used by: {used_by}

## ACTUAL SOURCE CODE
Analyze the following source code for this class:

```
{source_code}
```

## Instructions
Based on your analysis of the ACTUAL SOURCE CODE above, generate class documentation with:

1. **Details**: Source file path, module, and type
2. **Description**: Explain what this class ACTUALLY does based on its methods and logic. Be specific about its responsibilities.
3. **Constructor & Dependencies**: Explain what dependencies are injected and why (based on the constructor)
4. **Dependency Diagram**: A Mermaid diagram showing actual dependencies from the code
5. **Public Methods**: For EACH public method, explain:
   - What it does (based on the actual code logic)
   - Parameters and return type
   - Any important implementation details
6. **Usage Example**: A realistic code example based on the class's actual interface
7. **Key Implementation Details**: Important algorithms, error handling, or business logic you observe

IMPORTANT: Analyze the ACTUAL code and describe what it really does.
Output ONLY the markdown content."""

GETTING_STARTED_PROMPT = """You are writing a getting started guide for a codebase.

## Repository: {repo_name}
## Language: {language}
## Description: {description}

## Project Structure
{project_structure}

## Key Configuration Files
{config_files}

## Instructions
Generate a comprehensive getting started guide in Markdown with:

1. **Prerequisites**: What developers need before starting
2. **Installation**: Step-by-step installation commands
3. **Configuration**: How to configure the application (environment variables, config files)
4. **Running the Application**: Commands to start the application
5. **Project Structure**: Explain the directory structure
6. **Next Steps**: Links to other documentation pages

Use code blocks for commands. Be specific to the detected language and framework.
Output ONLY the markdown content."""

API_REFERENCE_PROMPT = """You are documenting the API endpoints of a codebase.

## Repository: {repo_name}

## Discovered Endpoints
{endpoints_by_controller}

## Controllers
{controllers_info}

## Instructions
Generate comprehensive API reference documentation in Markdown with:

1. **Overview**: Brief description of the API
2. **Base URL**: Infer the base URL pattern
3. **Authentication**: Note any authentication patterns observed
4. **Endpoints by Controller**: For each controller, list all endpoints with:
   - HTTP Method
   - Path
   - Handler method
   - Brief description of what the endpoint does

Use markdown tables for endpoint listings. Group by controller/resource.
Output ONLY the markdown content."""


# =============================================================================
# Concept Discovery Prompt (DeepWiki-style)
# =============================================================================

CONCEPT_DISCOVERY_PROMPT = """You are analyzing a codebase to identify the KEY CONCEPTS and SYSTEMS for documentation.

## Repository: {repo_name}
## Language: {language}

## Codebase Structure

### Modules/Packages
{modules_info}

### Key Classes (Controllers, Services, Repositories)
{classes_info}

### API Endpoints
{endpoints_info}

## SOURCE CODE SAMPLES
{source_code_snippets}

## Your Task

Analyze this codebase and identify the KEY CONCEPTS/SYSTEMS that should be documented.

Think like DeepWiki: Don't just list modules - identify the LOGICAL SYSTEMS and CONCEPTS that span across code.

For example:
- "Authentication System" (might include AuthController, AuthService, JwtProvider, UserRepository)
- "Data Access Layer" (might include all repositories and their patterns)
- "API Gateway" (might include all controllers and middleware)
- "Notification System" (might include EmailService, SMSService, NotificationController)

Return a JSON array with this structure:
```json
[
  {{
    "name": "Authentication System",
    "slug": "authentication-system",
    "type": "core_system",
    "description": "Handles user authentication, JWT token management, and session control",
    "related_classes": ["AuthController", "AuthService", "JwtTokenProvider", "UserRepository"],
    "related_files": ["src/auth/AuthController.java", "src/auth/AuthService.java"],
    "key_features": ["JWT-based authentication", "Role-based access control", "Session management"]
  }},
  {{
    "name": "User Management",
    "slug": "user-management",
    "type": "feature",
    "description": "CRUD operations for user accounts and profiles",
    "related_classes": ["UserController", "UserService", "UserRepository"],
    "related_files": ["src/user/UserController.java"],
    "key_features": ["User registration", "Profile management", "Password reset"]
  }}
]
```

Types should be one of:
- "core_system" - Major architectural component (e.g., "Data Access Layer", "API Layer")
- "feature" - Business capability (e.g., "User Management", "Search")
- "integration" - External system integration (e.g., "Database Integration", "Email Service")

Identify 5-15 concepts based on codebase complexity. Focus on what users need to UNDERSTAND, not just what code exists.

Return ONLY the JSON array, no other text."""


CONCEPT_PAGE_PROMPT = """You are generating DeepWiki-style documentation for a specific concept/system.

## Concept: {concept_name}
## Type: {concept_type}
## Repository: {repo_name}

## Concept Overview
{concept_description}

## Related Classes
{related_classes}

## Key Features
{key_features}

## SOURCE CODE FOR THIS CONCEPT
Analyze the following source code that implements this concept:

{source_code_snippets}

## Instructions

Generate comprehensive documentation for this concept/system in Markdown with:

1. **Overview**: What this system/concept does and WHY it exists (2-3 paragraphs based on the actual code)

2. **Architecture**: How this system is structured
   - Include a Mermaid diagram showing component relationships
   - Explain the design decisions visible in the code

3. **Key Components**: For each major class/component:
   - What it does (based on actual code analysis)
   - Its responsibilities
   - How it interacts with other components

4. **How It Works**: Step-by-step explanation of the main flows
   - Include sequence diagrams for complex flows
   - Reference actual method names from the code

5. **Configuration**: Any configuration options (from code analysis)

6. **Usage Examples**: How to use this system (based on actual patterns in code)

7. **Related Concepts**: Links to related systems/concepts

IMPORTANT: Base ALL documentation on the ACTUAL SOURCE CODE provided. Don't make assumptions - describe what the code really does.

Output ONLY the markdown content."""


USER_GUIDE_INSTALLATION_PROMPT = """You are generating installation documentation by analyzing the codebase.

## Repository: {repo_name}
## Language: {language}

## Project Structure
{project_structure}

## Configuration Files Found
{config_files}

## Package/Dependency Files
{dependency_info}

## Source Code Context
{source_code_snippets}

## Instructions

Generate comprehensive installation documentation in Markdown with:

1. **Prerequisites**: What needs to be installed first (based on dependencies found)
2. **System Requirements**: Minimum requirements inferred from the tech stack
3. **Installation Steps**: Step-by-step guide with actual commands
4. **Environment Setup**: Environment variables and configuration needed
5. **Verification**: How to verify the installation works
6. **Troubleshooting**: Common issues and solutions

Be specific to this project - use actual file names and commands from the codebase.
Output ONLY the markdown content."""


USER_GUIDE_CONFIGURATION_PROMPT = """You are generating configuration documentation by analyzing the codebase.

## Repository: {repo_name}

## Configuration Files
{config_files}

## Environment Variables (from code)
{env_vars}

## Source Code Context
{source_code_snippets}

## Instructions

Generate comprehensive configuration documentation in Markdown with:

1. **Configuration Overview**: How configuration works in this project
2. **Environment Variables**: Table with all environment variables, their purpose, and defaults
3. **Configuration Files**: Explain each config file and its options
4. **Profiles/Environments**: Different configuration profiles (dev, prod, test)
5. **Secrets Management**: How secrets are handled
6. **Examples**: Example configurations for common scenarios

Base everything on the ACTUAL configuration patterns found in the code.
Output ONLY the markdown content."""


# =============================================================================
# Wiki Page Templates (Fallback when LLM unavailable)
# =============================================================================

OVERVIEW_TEMPLATE = """# {repo_name}

## Overview

{description}

## Quick Stats

| Metric | Value |
|--------|-------|
| Total Files | {total_files} |
| Lines of Code | {total_loc} |
| Classes | {total_classes} |
| Functions | {total_functions} |
| Test Coverage | {test_coverage} |

## Tech Stack

{tech_stack}

## Architecture Overview

```mermaid
graph TB
    subgraph Frontend
        UI[UI Components]
        Pages[Pages/Routes]
    end

    subgraph Backend
        Controllers[Controllers]
        Services[Services]
        Repositories[Repositories]
    end

    subgraph Data
        DB[(Database)]
        Cache[(Cache)]
    end

    UI --> Pages
    Pages --> Controllers
    Controllers --> Services
    Services --> Repositories
    Repositories --> DB
    Services --> Cache
```

## Key Modules

{modules_list}

## Quick Links

- [Architecture Details](./architecture)
- [Getting Started](./getting-started)
- [API Reference](./api)
"""

ARCHITECTURE_TEMPLATE = """# Architecture

## System Overview

{architecture_description}

## Component Diagram

```mermaid
graph LR
    subgraph Presentation Layer
        {presentation_components}
    end

    subgraph Business Layer
        {business_components}
    end

    subgraph Data Layer
        {data_components}
    end

    Presentation Layer --> Business Layer
    Business Layer --> Data Layer
```

## Layer Responsibilities

### Presentation Layer
{presentation_description}

### Business Layer
{business_description}

### Data Layer
{data_description}

## Key Design Patterns

{patterns_list}

## Dependencies

{dependencies_diagram}
"""

MODULE_TEMPLATE = """# {module_name}

## Details

**Sources:**
{source_files_list}

## Overview

{module_description}

## Features

| Feature | Type | Complexity |
|---------|------|------------|
{features_table}

## Key Components

{components_list}

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
{endpoints_table}

## Data Flow

```mermaid
sequenceDiagram
    participant Client
    participant Controller
    participant Service
    participant Repository
    participant Database

    Client->>Controller: Request
    Controller->>Service: Process
    Service->>Repository: Query
    Repository->>Database: SQL
    Database-->>Repository: Results
    Repository-->>Service: Entities
    Service-->>Controller: Response
    Controller-->>Client: JSON
```

## Related Modules

{related_modules}
"""

CLASS_TEMPLATE = """# {class_name}

## Details

**Source:** `{file_path}`

**Module:** [{module_name}](../modules/{module_slug})

**Type:** {class_type}

## Description

{description}

## Dependencies

```mermaid
graph LR
    {class_name} --> {dependencies_diagram}
```

## Public Methods

{methods_list}

## Usage Example

```{language}
{usage_example}
```

## Used By

{used_by_list}
"""

GETTING_STARTED_TEMPLATE = """# Getting Started

## Prerequisites

{prerequisites}

## Installation

{installation_steps}

## Configuration

{configuration}

## Running the Application

{run_instructions}

## Project Structure

```
{project_structure}
```

## Next Steps

- [System Overview](./overview)
- [Architecture](./architecture)
- [API Reference](./api)
"""


# =============================================================================
# Wiki Service Class
# =============================================================================

class WikiService:
    """Service for generating and managing wiki documentation.

    Uses Copilot SDK for LLM-powered intelligent content generation.
    Reads actual source code via Filesystem MCP (same as BRD generator).
    Falls back to template-based generation when SDK is not available.
    """

    def __init__(self, neo4j_client=None, filesystem_client=None, copilot_session: Any = None):
        """Initialize the wiki service.

        Args:
            neo4j_client: Neo4j client for querying code graph (metadata, relationships)
            filesystem_client: Filesystem MCP client for reading actual source code
            copilot_session: Copilot SDK session for LLM-powered generation
        """
        self.neo4j_client = neo4j_client
        self.filesystem_client = filesystem_client
        self.copilot_session = copilot_session
        self._llm_available = copilot_session is not None

        if self._llm_available:
            logger.info("WikiService initialized with Copilot SDK for LLM-powered generation")
        else:
            logger.warning("WikiService initialized without Copilot SDK - using template fallback")

        if self.filesystem_client:
            logger.info("WikiService will read source code via Filesystem MCP")
        else:
            logger.warning("WikiService: No filesystem client - source code reading disabled")

    async def _send_to_llm(self, prompt: str, timeout: float = 120) -> Optional[str]:
        """Send a prompt to the LLM via Copilot SDK.

        Args:
            prompt: The prompt to send
            timeout: Timeout in seconds

        Returns:
            LLM response text or None if failed
        """
        if not self.copilot_session:
            return None

        try:
            import time
            start_time = time.time()

            prompt_preview = prompt[:100] + "..." if len(prompt) > 100 else prompt
            logger.info(f"[WIKI] Sending to LLM ({len(prompt)} chars)")
            logger.debug(f"[WIKI] Prompt preview: {prompt_preview}")

            message_options = {"prompt": prompt}

            if hasattr(self.copilot_session, 'send_and_wait'):
                event = await asyncio.wait_for(
                    self.copilot_session.send_and_wait(message_options, timeout=timeout),
                    timeout=timeout
                )
                elapsed = time.time() - start_time

                if event:
                    response = self._extract_from_event(event)
                    logger.info(f"[WIKI] Response received ({len(response)} chars, {elapsed:.2f}s)")
                    return response
                else:
                    logger.warning(f"[WIKI] No event returned from SDK ({elapsed:.2f}s)")
                    return None

            elif hasattr(self.copilot_session, 'send'):
                await self.copilot_session.send(message_options)
                response = await self._wait_for_response(timeout)
                return response

            return None

        except asyncio.TimeoutError:
            logger.warning(f"[WIKI] LLM timeout after {timeout}s")
            return None
        except Exception as e:
            logger.error(f"[WIKI] LLM error: {e}")
            return None

    def _extract_from_event(self, event: Any) -> str:
        """Extract text content from a Copilot event."""
        try:
            if hasattr(event, 'data'):
                data = event.data
                if hasattr(data, 'message') and hasattr(data.message, 'content'):
                    return str(data.message.content)
                if hasattr(data, 'content'):
                    return str(data.content)
                if hasattr(data, 'text'):
                    return str(data.text)

            if hasattr(event, 'content'):
                return str(event.content)
            if hasattr(event, 'text'):
                return str(event.text)

            return str(event)
        except Exception as e:
            logger.error(f"[WIKI] Error extracting from event: {e}")
            return ""

    async def _wait_for_response(self, timeout: float) -> str:
        """Wait for LLM response by polling messages."""
        start_time = asyncio.get_event_loop().time()
        poll_interval = 1.0

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                return ""

            try:
                messages = self.copilot_session.get_messages()
                for msg in reversed(messages):
                    if hasattr(msg, 'data'):
                        data = msg.data
                        if hasattr(data, 'role') and data.role == 'assistant':
                            return self._extract_from_event(msg)
            except Exception as e:
                logger.debug(f"[WIKI] Poll error: {e}")

            await asyncio.sleep(poll_interval)

    async def get_or_create_wiki(
        self,
        session: AsyncSession,
        repository_id: str
    ) -> WikiDB:
        """Get existing wiki or create a new one for a repository."""
        result = await session.execute(
            select(WikiDB).where(WikiDB.repository_id == repository_id)
        )
        wiki = result.scalar_one_or_none()

        if not wiki:
            wiki = WikiDB(
                id=str(uuid4()),
                repository_id=repository_id,
                status=WikiStatus.NOT_GENERATED,
            )
            session.add(wiki)
            await session.flush()
            logger.info(f"Created new wiki for repository {repository_id}")

        return wiki

    async def generate_wiki(
        self,
        session: AsyncSession,
        repository_id: str,
        commit_sha: Optional[str] = None,
        depth: str = "standard",  # quick, standard, comprehensive, custom
        wiki_options: Optional[dict] = None,  # Full wiki configuration options
        progress_callback=None,
    ) -> WikiDB:
        """Generate wiki documentation for a repository.

        Args:
            session: Database session
            repository_id: Repository ID
            commit_sha: Git commit SHA
            depth: Generation depth level
            wiki_options: Full wiki configuration options including advanced mode settings
            progress_callback: Async callback for progress updates

        Returns:
            Updated WikiDB instance
        """
        start_time = time.time()
        wiki_options = wiki_options or {}
        mode = wiki_options.get("mode", "standard")

        # Get or create wiki
        wiki = await self.get_or_create_wiki(session, repository_id)
        wiki.status = WikiStatus.GENERATING
        wiki.status_message = "Starting wiki generation..."
        await session.flush()

        if progress_callback:
            await progress_callback("init", "Starting wiki generation...")

        try:
            # Get repository info
            repo_result = await session.execute(
                select(RepositoryDB).where(RepositoryDB.id == repository_id)
            )
            repository = repo_result.scalar_one_or_none()

            if not repository:
                raise ValueError(f"Repository not found: {repository_id}")

            # Gather data from Neo4j and Filesystem
            if progress_callback:
                await progress_callback("gathering", "Gathering codebase information...")

            codebase_data = await self._gather_codebase_data(repository_id)

            # Add context notes to codebase_data for LLM prompts (advanced mode)
            if mode == "advanced":
                context_notes = wiki_options.get("context_notes", [])
                if context_notes:
                    codebase_data["context_notes"] = context_notes
                    logger.info(f"Using {len(context_notes)} context notes for wiki generation")

            # Discover concepts (DeepWiki-style)
            if progress_callback:
                await progress_callback("discovering", "Discovering concepts and systems...")

            # Generate pages based on mode and depth
            if mode == "advanced" and wiki_options.get("custom_pages"):
                # Advanced mode: Use custom page definitions
                pages_to_generate = self._get_pages_from_custom_config(
                    wiki_options.get("custom_pages", []),
                    codebase_data,
                    repository,
                )
                logger.info(f"Using {len(pages_to_generate)} custom pages from advanced mode config")
            else:
                # Standard mode: Generate pages based on depth and section toggles
                pages_to_generate = await self._get_pages_for_depth(
                    depth, codebase_data, repository, wiki_options
                )
            total_pages = len(pages_to_generate)

            if progress_callback:
                await progress_callback("generating", f"Generating {total_pages} pages...")

            # Generate each page
            generated_pages = []
            for idx, page_spec in enumerate(pages_to_generate):
                if progress_callback:
                    await progress_callback(
                        "page",
                        f"Generating: {page_spec['title']} ({idx + 1}/{total_pages})"
                    )

                page = await self._generate_page(
                    session,
                    wiki.id,
                    page_spec,
                    codebase_data,
                    repository,
                )
                generated_pages.append(page)

            # Update wiki status
            wiki.status = WikiStatus.GENERATED
            wiki.status_message = None
            wiki.commit_sha = commit_sha or repository.current_commit
            wiki.total_pages = len(generated_pages)
            wiki.stale_pages = 0
            wiki.generation_mode = "llm-powered" if self._llm_available else "template"
            wiki.generated_at = datetime.utcnow()

            duration_ms = int((time.time() - start_time) * 1000)
            generation_mode = "llm-powered" if self._llm_available else "template-based"
            logger.info(
                f"Wiki generated for repository {repository_id}: "
                f"{len(generated_pages)} pages in {duration_ms}ms (mode: {generation_mode})"
            )

            if progress_callback:
                await progress_callback("complete", f"Wiki generated: {len(generated_pages)} pages")

            return wiki

        except Exception as e:
            logger.exception(f"Wiki generation failed for {repository_id}")
            wiki.status = WikiStatus.FAILED
            wiki.status_message = str(e)
            await session.flush()
            raise

    async def _gather_codebase_data(self, repository_id: str, repository: RepositoryDB = None) -> dict:
        """Gather all codebase data needed for wiki generation.

        This method gathers both metadata AND actual source code content
        for LLM-powered documentation generation (DeepWiki-style).
        """
        data = {
            "statistics": {},
            "modules": [],
            "features": [],
            "classes": [],
            "endpoints": [],
            "patterns": [],
            "source_code": {},  # NEW: Actual source code snippets for LLM analysis
        }

        if not self.neo4j_client:
            logger.warning("No Neo4j client available, using minimal data")
            return data

        try:
            # Query statistics
            stats_query = """
            MATCH (r:Repository {repositoryId: $repository_id})
            OPTIONAL MATCH (r)-[:HAS_MODULE]->(m)
            OPTIONAL MATCH (m)-[:CONTAINS_FILE]->(f:File)
            OPTIONAL MATCH (f)-[:DEFINES_CLASS]->(c)
            OPTIONAL MATCH (f)-[:DEFINES_FUNCTION]->(fn)
            RETURN
                count(DISTINCT m) as modules,
                count(DISTINCT f) as files,
                count(DISTINCT c) as classes,
                count(DISTINCT fn) as functions
            """
            stats_result = await self.neo4j_client.query_code_structure(
                stats_query,
                {"repository_id": repository_id}
            )
            if stats_result and stats_result.get("nodes"):
                data["statistics"] = stats_result["nodes"][0]

            # Query modules/packages
            modules_query = """
            MATCH (r:Repository {repositoryId: $repository_id})-[:HAS_MODULE]->(m)
            OPTIONAL MATCH (m)-[:CONTAINS_FILE]->(f)
            OPTIONAL MATCH (f)-[:DEFINES_CLASS]->(c)
            RETURN
                m.name as name,
                m.path as path,
                count(DISTINCT f) as file_count,
                count(DISTINCT c) as class_count
            ORDER BY m.name
            """
            modules_result = await self.neo4j_client.query_code_structure(
                modules_query,
                {"repository_id": repository_id}
            )
            if modules_result and modules_result.get("nodes"):
                data["modules"] = modules_result["nodes"]

            # Query key classes (controllers, services)
            classes_query = """
            MATCH (r:Repository {repositoryId: $repository_id})-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f)-[:DEFINES_CLASS]->(c)
            WHERE c:SpringController OR c:SpringService OR c.stereotype IN ['Controller', 'Service', 'Repository']
            OPTIONAL MATCH (c)-[:USES|DEPENDS_ON]->(dep)
            RETURN
                c.name as name,
                c.filePath as file_path,
                c.stereotype as type,
                labels(c) as labels,
                collect(DISTINCT dep.name) as dependencies
            ORDER BY c.name
            LIMIT 100
            """
            classes_result = await self.neo4j_client.query_code_structure(
                classes_query,
                {"repository_id": repository_id}
            )
            if classes_result and classes_result.get("nodes"):
                data["classes"] = classes_result["nodes"]

            # Query endpoints
            endpoints_query = """
            MATCH (r:Repository {repositoryId: $repository_id})-[:HAS_MODULE]->(m)-[:CONTAINS_FILE]->(f)-[:DEFINES_CLASS]->(c)-[:HAS_METHOD]->(method)
            WHERE method.httpMethod IS NOT NULL
            RETURN
                method.httpMethod as method,
                method.path as path,
                method.name as handler,
                c.name as controller
            ORDER BY method.path
            LIMIT 200
            """
            endpoints_result = await self.neo4j_client.query_code_structure(
                endpoints_query,
                {"repository_id": repository_id}
            )
            if endpoints_result and endpoints_result.get("nodes"):
                data["endpoints"] = endpoints_result["nodes"]

            # Read actual source code via Filesystem MCP (same pattern as BRD generator)
            # Neo4j provides file paths, Filesystem MCP reads the actual code
            if self.filesystem_client and data["classes"]:
                logger.info("Reading source code via Filesystem MCP for DeepWiki-style generation")
                files_read = 0
                max_files = 25  # Limit to prevent excessive reads

                for cls in data["classes"][:max_files]:
                    file_path = cls.get("file_path", "")
                    class_name = cls.get("name", "")

                    if not file_path or not class_name:
                        continue

                    try:
                        # Read source code from filesystem (same as aggregator does)
                        content = await self.filesystem_client.read_file(file_path)

                        if content:
                            # Store source code keyed by class name
                            data["source_code"][class_name] = {
                                "code": content[:5000],  # Limit to 5000 chars per class
                                "file_path": file_path,
                                "type": cls.get("type", ""),
                                "labels": cls.get("labels", []),
                            }
                            files_read += 1

                    except Exception as e:
                        logger.debug(f"Could not read file {file_path}: {e}")

                logger.info(f"Read source code for {files_read} classes via Filesystem MCP")

        except Exception as e:
            logger.warning(f"Error gathering codebase data: {e}")

        return data

    async def _discover_concepts(
        self,
        codebase_data: dict,
        repository: RepositoryDB,
    ) -> list[dict]:
        """Discover key concepts/systems from the codebase using LLM.

        This is the core of DeepWiki-style documentation - instead of just
        documenting code structure, we identify logical concepts that span
        across the codebase.

        Returns:
            List of discovered concepts with metadata
        """
        if not self._llm_available:
            logger.warning("[WIKI] LLM not available - using fallback concept detection")
            return self._discover_concepts_fallback(codebase_data)

        try:
            # Format data for prompt
            modules_info = "\n".join([
                f"- **{m.get('name', 'Unknown')}**: {m.get('file_count', 0)} files, {m.get('class_count', 0)} classes"
                for m in codebase_data.get("modules", [])[:15]
            ]) or "No modules found"

            classes_info = "\n".join([
                f"- **{c.get('name', 'Unknown')}** ({c.get('type', 'Class')}): {c.get('file_path', '')}"
                for c in codebase_data.get("classes", [])[:30]
            ]) or "No classes found"

            endpoints_info = "\n".join([
                f"- {e.get('method', 'GET')} {e.get('path', '/')}: {e.get('handler', '')} ({e.get('controller', '')})"
                for e in codebase_data.get("endpoints", [])[:20]
            ]) or "No endpoints found"

            source_code_snippets = self._format_source_code_snippets(
                codebase_data.get("source_code", {}),
                max_total_chars=10000
            )

            prompt = CONCEPT_DISCOVERY_PROMPT.format(
                repo_name=repository.name,
                language=repository.language or "Unknown",
                modules_info=modules_info,
                classes_info=classes_info,
                endpoints_info=endpoints_info,
                source_code_snippets=source_code_snippets,
            )

            logger.info("[WIKI] Discovering concepts via LLM...")
            response = await self._send_to_llm(prompt, timeout=180)

            if response:
                # Parse JSON response
                import json
                # Clean response - extract JSON array
                response = response.strip()
                if response.startswith("```json"):
                    response = response[7:]
                if response.startswith("```"):
                    response = response[3:]
                if response.endswith("```"):
                    response = response[:-3]

                concepts = json.loads(response.strip())
                logger.info(f"[WIKI] Discovered {len(concepts)} concepts via LLM")
                return concepts

        except Exception as e:
            logger.error(f"[WIKI] Concept discovery failed: {e}")

        # Fallback to rule-based detection
        return self._discover_concepts_fallback(codebase_data)

    def _discover_concepts_fallback(self, codebase_data: dict) -> list[dict]:
        """Fallback concept detection when LLM is unavailable.

        Uses heuristics based on class names and patterns.
        """
        concepts = []
        classes = codebase_data.get("classes", [])

        # Group classes by common prefixes/patterns
        class_groups: dict[str, list] = {}

        for cls in classes:
            name = cls.get("name", "")
            cls_type = cls.get("type", "")

            # Try to extract concept from class name
            # e.g., "UserController" -> "User", "AuthService" -> "Auth"
            concept_name = None
            for suffix in ["Controller", "Service", "Repository", "Handler", "Manager", "Provider"]:
                if name.endswith(suffix):
                    concept_name = name[:-len(suffix)]
                    break

            if concept_name:
                if concept_name not in class_groups:
                    class_groups[concept_name] = []
                class_groups[concept_name].append(cls)

        # Create concepts from groups with multiple classes
        for concept_name, group_classes in class_groups.items():
            if len(group_classes) >= 1:  # Include even single-class concepts
                concepts.append({
                    "name": f"{concept_name} System",
                    "slug": concept_name.lower().replace(" ", "-") + "-system",
                    "type": "core_system",
                    "description": f"Handles {concept_name.lower()}-related functionality",
                    "related_classes": [c.get("name") for c in group_classes],
                    "related_files": [c.get("file_path") for c in group_classes if c.get("file_path")],
                    "key_features": [],
                })

        # Add standard architectural concepts if we have the right classes
        controller_count = len([c for c in classes if "Controller" in c.get("name", "")])
        service_count = len([c for c in classes if "Service" in c.get("name", "")])
        repo_count = len([c for c in classes if "Repository" in c.get("name", "")])

        if controller_count > 0:
            concepts.append({
                "name": "API Layer",
                "slug": "api-layer",
                "type": "core_system",
                "description": "REST API controllers and request handling",
                "related_classes": [c.get("name") for c in classes if "Controller" in c.get("name", "")],
                "related_files": [],
                "key_features": ["REST endpoints", "Request validation", "Response formatting"],
            })

        if service_count > 0:
            concepts.append({
                "name": "Business Logic Layer",
                "slug": "business-logic-layer",
                "type": "core_system",
                "description": "Core business logic and service orchestration",
                "related_classes": [c.get("name") for c in classes if "Service" in c.get("name", "")],
                "related_files": [],
                "key_features": ["Business rules", "Transaction management", "Service orchestration"],
            })

        if repo_count > 0:
            concepts.append({
                "name": "Data Access Layer",
                "slug": "data-access-layer",
                "type": "core_system",
                "description": "Database operations and data persistence",
                "related_classes": [c.get("name") for c in classes if "Repository" in c.get("name", "")],
                "related_files": [],
                "key_features": ["CRUD operations", "Query building", "Data mapping"],
            })

        logger.info(f"[WIKI] Fallback concept detection found {len(concepts)} concepts")
        return concepts

    def _get_pages_from_custom_config(
        self,
        custom_pages: list[dict],
        codebase_data: dict,
        repository: RepositoryDB,
    ) -> list[dict]:
        """Get list of pages from custom advanced mode configuration.

        Converts user-defined custom pages to the internal page spec format.
        """
        pages = []

        # Build a map of page IDs for parent resolution
        page_map = {p.get("title", ""): p for p in custom_pages}

        # First pass: add all sections
        sections = [p for p in custom_pages if p.get("is_section")]
        for section in sections:
            title = section.get("title", "Section")
            slug = title.lower().replace(" ", "-")
            pages.append({
                "slug": slug,
                "title": title,
                "type": WikiPageType.CUSTOM,
                "parent": None,
                "section": "custom",
                "purpose": section.get("purpose", ""),
                "notes": section.get("notes", ""),
            })

        # Second pass: add all pages
        non_sections = [p for p in custom_pages if not p.get("is_section")]
        for page in non_sections:
            title = page.get("title", "Page")
            slug = title.lower().replace(" ", "-")
            parent_id = page.get("parent_id")

            # Find parent section
            parent_slug = None
            if parent_id:
                # Find the parent section by its ID/title
                for section in sections:
                    if section.get("title") == parent_id or str(section.get("id")) == str(parent_id):
                        parent_slug = section.get("title", "").lower().replace(" ", "-")
                        slug = f"{parent_slug}/{slug}"
                        break

            pages.append({
                "slug": slug,
                "title": title,
                "type": WikiPageType.CUSTOM,
                "parent": parent_slug,
                "section": "custom",
                "purpose": page.get("purpose", ""),
                "notes": page.get("notes", ""),
            })

        logger.info(f"Created {len(pages)} page specs from custom configuration")
        return pages

    async def _get_pages_for_depth(
        self,
        depth: str,
        codebase_data: dict,
        repository: RepositoryDB,
        wiki_options: Optional[dict] = None,
    ) -> list[dict]:
        """Get list of pages to generate based on depth level and wiki options.

        Uses DeepWiki-style concept-based structure with dynamically
        discovered concepts from the codebase.

        The wiki_options parameter allows fine-grained control over which
        sections to include (standard mode).
        """
        pages = []
        wiki_options = wiki_options or {}

        # Helper to check if a section is enabled
        def is_enabled(key: str, default: bool = True) -> bool:
            return wiki_options.get(key, default)

        # =================================================================
        # SECTION 1: Overview & Architecture (always included)
        # =================================================================
        pages.extend([
            {"slug": "overview", "title": "Overview", "type": WikiPageType.OVERVIEW, "parent": None, "section": "overview"},
            {"slug": "architecture", "title": "Architecture", "type": WikiPageType.ARCHITECTURE, "parent": None, "section": "overview"},
            {"slug": "tech-stack", "title": "Tech Stack", "type": WikiPageType.TECH_STACK, "parent": None, "section": "overview"},
        ])

        # =================================================================
        # SECTION 2: User Guide (based on wiki_options)
        # =================================================================
        include_getting_started = is_enabled("include_getting_started", True)
        include_configuration = is_enabled("include_configuration", True)
        include_deployment = is_enabled("include_deployment", False)

        if include_getting_started or include_configuration or include_deployment:
            pages.append({
                "slug": "user-guide",
                "title": "User Guide",
                "type": WikiPageType.GETTING_STARTED,
                "parent": None,
                "section": "guide"
            })

            if include_getting_started:
                pages.extend([
                    {"slug": "user-guide/getting-started", "title": "Getting Started", "type": WikiPageType.GETTING_STARTED, "parent": "user-guide", "section": "guide"},
                    {"slug": "user-guide/installation", "title": "Installation", "type": WikiPageType.INSTALLATION, "parent": "user-guide", "section": "guide"},
                ])

            if include_configuration:
                pages.append({
                    "slug": "user-guide/configuration",
                    "title": "Configuration",
                    "type": WikiPageType.CONFIGURATION,
                    "parent": "user-guide",
                    "section": "guide"
                })

            if include_deployment:
                pages.append({
                    "slug": "user-guide/deployment",
                    "title": "Deployment",
                    "type": WikiPageType.DEPLOYMENT,
                    "parent": "user-guide",
                    "section": "guide"
                })

        # =================================================================
        # SECTION 3: Core Systems (DYNAMICALLY DISCOVERED CONCEPTS)
        # =================================================================
        include_core_systems = is_enabled("include_core_systems", True)
        include_features = is_enabled("include_features", True)
        include_integrations = is_enabled("include_integrations", False)

        concepts = []
        if include_core_systems or include_features or include_integrations:
            concepts = await self._discover_concepts(codebase_data, repository)

        # Separate concepts by type
        core_systems = [c for c in concepts if c.get("type") == "core_system"]
        features = [c for c in concepts if c.get("type") == "feature"]
        integrations = [c for c in concepts if c.get("type") == "integration"]

        # Add Core Systems section (if enabled)
        if include_core_systems and core_systems:
            pages.append({
                "slug": "core-systems",
                "title": "Core Systems",
                "type": WikiPageType.CORE_SYSTEM,
                "parent": None,
                "section": "systems",
            })

            for concept in core_systems[:10]:  # Limit to 10 core systems
                pages.append({
                    "slug": f"core-systems/{concept['slug']}",
                    "title": concept["name"],
                    "type": WikiPageType.CORE_SYSTEM,
                    "parent": "core-systems",
                    "section": "systems",
                    "data": concept,
                })

        # Add Features section (if enabled)
        if include_features and features:
            pages.append({
                "slug": "features",
                "title": "Features",
                "type": WikiPageType.FEATURE,
                "parent": None,
                "section": "features",
            })

            for concept in features[:10]:  # Limit to 10 features
                pages.append({
                    "slug": f"features/{concept['slug']}",
                    "title": concept["name"],
                    "type": WikiPageType.FEATURE,
                    "parent": "features",
                    "section": "features",
                    "data": concept,
                })

        # Add Integrations section (if enabled)
        if include_integrations and integrations:
            pages.append({
                "slug": "integrations",
                "title": "Integrations",
                "type": WikiPageType.INTEGRATION,
                "parent": None,
                "section": "integrations",
            })

            for concept in integrations[:5]:  # Limit to 5 integrations
                pages.append({
                    "slug": f"integrations/{concept['slug']}",
                    "title": concept["name"],
                    "type": WikiPageType.INTEGRATION,
                    "parent": "integrations",
                    "section": "integrations",
                    "data": concept,
                })

        # =================================================================
        # SECTION 4: Technical Reference (based on wiki_options or depth)
        # =================================================================
        include_api_reference = is_enabled("include_api_reference", depth in ["standard", "comprehensive"])
        include_data_models = is_enabled("include_data_models", depth in ["standard", "comprehensive"])

        if include_api_reference:
            endpoints = codebase_data.get("endpoints", [])
            if endpoints:
                pages.append({
                    "slug": "api-reference",
                    "title": "API Reference",
                    "type": WikiPageType.API,
                    "parent": None,
                    "section": "reference",
                })

        if include_data_models:
            pages.append({
                "slug": "data-models",
                "title": "Data Models",
                "type": WikiPageType.DATA_MODEL,
                "parent": None,
                "section": "reference",
            })

        # =================================================================
        # SECTION 5: Code Structure (based on wiki_options or depth)
        # =================================================================
        include_code_structure = is_enabled("include_code_structure", depth == "comprehensive")

        if include_code_structure:
            modules = codebase_data.get("modules", [])
            if modules:
                pages.append({
                    "slug": "code-structure",
                    "title": "Code Structure",
                    "type": WikiPageType.MODULE,
                    "parent": None,
                    "section": "code",
                })

                for module in modules[:15]:  # Limit modules
                    module_name = module.get("name", "Unknown")
                    module_slug = module_name.lower().replace(" ", "-").replace(".", "-")
                    pages.append({
                        "slug": f"code-structure/{module_slug}",
                        "title": module_name,
                        "type": WikiPageType.MODULE,
                        "parent": "code-structure",
                        "section": "code",
                        "data": module,
                    })

        return pages

    async def _generate_page(
        self,
        session: AsyncSession,
        wiki_id: str,
        page_spec: dict,
        codebase_data: dict,
        repository: RepositoryDB,
    ) -> WikiPageDB:
        """Generate a single wiki page."""
        start_time = time.time()

        # Check if page already exists
        result = await session.execute(
            select(WikiPageDB).where(
                WikiPageDB.wiki_id == wiki_id,
                WikiPageDB.slug == page_spec["slug"]
            )
        )
        existing_page = result.scalar_one_or_none()

        # Generate content based on page type
        content = await self._generate_page_content(
            page_spec,
            codebase_data,
            repository,
        )

        duration_ms = int((time.time() - start_time) * 1000)

        if existing_page:
            # Update existing page
            existing_page.markdown_content = content
            existing_page.is_stale = False
            existing_page.stale_reason = None
            existing_page.generation_duration_ms = duration_ms
            existing_page.updated_at = datetime.utcnow()
            return existing_page
        else:
            # Create new page
            page = WikiPageDB(
                id=str(uuid4()),
                wiki_id=wiki_id,
                slug=page_spec["slug"],
                title=page_spec["title"],
                page_type=page_spec["type"],
                markdown_content=content,
                parent_slug=page_spec.get("parent"),
                display_order=0,
                generation_duration_ms=duration_ms,
            )
            session.add(page)
            return page

    async def _generate_page_content(
        self,
        page_spec: dict,
        codebase_data: dict,
        repository: RepositoryDB,
    ) -> str:
        """Generate markdown content for a page using LLM or template fallback."""
        page_type = page_spec["type"]
        stats = codebase_data.get("statistics", {})
        modules = codebase_data.get("modules", [])
        classes = codebase_data.get("classes", [])
        endpoints = codebase_data.get("endpoints", [])

        # Try LLM-powered generation first
        if self._llm_available:
            llm_content = await self._generate_page_with_llm(
                page_spec, page_type, codebase_data, repository, stats, modules, classes, endpoints
            )
            if llm_content:
                return llm_content
            logger.warning(f"[WIKI] LLM generation failed for {page_spec['title']}, falling back to template")

        # Template-based fallback
        return self._generate_page_from_template(
            page_spec, page_type, codebase_data, repository, stats, modules, classes, endpoints
        )

    def _format_source_code_snippets(self, source_code: dict, filter_classes: list = None, max_total_chars: int = 15000) -> str:
        """Format source code snippets for LLM analysis.

        Args:
            source_code: Dict mapping class names to code info
            filter_classes: Optional list of class names to include
            max_total_chars: Maximum total characters for all snippets

        Returns:
            Formatted string with code snippets
        """
        if not source_code:
            return "No source code available for analysis."

        snippets = []
        total_chars = 0

        for class_name, info in source_code.items():
            # Filter if specified
            if filter_classes and class_name not in filter_classes:
                continue

            code = info.get("code", "")
            if not code:
                continue

            # Check if we'd exceed the limit
            snippet_text = f"\n### {class_name}\n**File:** `{info.get('file_path', 'unknown')}`\n**Type:** {info.get('type', 'Class')}\n\n```\n{code}\n```\n"

            if total_chars + len(snippet_text) > max_total_chars:
                # Truncate code to fit
                remaining = max_total_chars - total_chars - 200  # Buffer for formatting
                if remaining > 500:
                    truncated_code = code[:remaining] + "\n... (truncated)"
                    snippet_text = f"\n### {class_name}\n**File:** `{info.get('file_path', 'unknown')}`\n**Type:** {info.get('type', 'Class')}\n\n```\n{truncated_code}\n```\n"
                    snippets.append(snippet_text)
                break

            snippets.append(snippet_text)
            total_chars += len(snippet_text)

        return "\n".join(snippets) if snippets else "No source code available for analysis."

    async def _generate_page_with_llm(
        self,
        page_spec: dict,
        page_type: WikiPageType,
        codebase_data: dict,
        repository: RepositoryDB,
        stats: dict,
        modules: list,
        classes: list,
        endpoints: list,
    ) -> Optional[str]:
        """Generate page content using LLM with actual source code analysis (DeepWiki-style)."""
        try:
            # Get source code from codebase_data
            source_code = codebase_data.get("source_code", {})

            # Build prompts based on page type
            if page_type == WikiPageType.OVERVIEW:
                # Format modules info
                modules_info = "\n".join([
                    f"- **{m.get('name', 'Unknown')}**: {m.get('file_count', 0)} files, {m.get('class_count', 0)} classes"
                    for m in modules[:15]
                ]) or "No modules discovered"

                # Format classes info
                classes_info = "\n".join([
                    f"- **{c.get('name', 'Unknown')}** ({c.get('type', 'Class')}): {c.get('file_path', '')}"
                    for c in classes[:20]
                ]) or "No key classes discovered"

                # Format source code snippets for LLM analysis
                source_code_snippets = self._format_source_code_snippets(source_code, max_total_chars=12000)

                prompt = OVERVIEW_PROMPT.format(
                    repo_name=repository.name,
                    description=repository.description or f"A {repository.language or 'software'} project",
                    language=repository.language or "Unknown",
                    total_files=stats.get("files", 0),
                    total_classes=stats.get("classes", 0),
                    total_functions=stats.get("functions", 0),
                    module_count=len(modules),
                    modules_info=modules_info,
                    classes_info=classes_info,
                    source_code_snippets=source_code_snippets,
                )

            elif page_type == WikiPageType.ARCHITECTURE:
                # Categorize classes
                controllers = [c for c in classes if 'Controller' in str(c.get('labels', []))]
                services = [c for c in classes if 'Service' in str(c.get('labels', []))]
                repositories = [c for c in classes if 'Repository' in str(c.get('type', ''))]
                other_classes = [c for c in classes if c not in controllers + services + repositories]

                controllers_info = "\n".join([
                    f"- **{c.get('name')}**: {c.get('file_path', '')}"
                    for c in controllers[:10]
                ]) or "No controllers found"

                services_info = "\n".join([
                    f"- **{s.get('name')}**: Dependencies: {', '.join(s.get('dependencies', [])[:5])}"
                    for s in services[:10]
                ]) or "No services found"

                repositories_info = "\n".join([
                    f"- **{r.get('name')}**: {r.get('file_path', '')}"
                    for r in repositories[:10]
                ]) or "No repositories found"

                other_classes_info = "\n".join([
                    f"- **{c.get('name')}** ({c.get('type', 'Class')})"
                    for c in other_classes[:10]
                ]) or "None"

                endpoints_info = "\n".join([
                    f"- {e.get('method', 'GET')} {e.get('path', '/')}: {e.get('handler', '')}"
                    for e in endpoints[:20]
                ]) or "No endpoints discovered"

                # Include source code for architecture analysis
                source_code_snippets = self._format_source_code_snippets(source_code, max_total_chars=12000)

                prompt = ARCHITECTURE_PROMPT.format(
                    repo_name=repository.name,
                    controllers_info=controllers_info,
                    services_info=services_info,
                    repositories_info=repositories_info,
                    other_classes_info=other_classes_info,
                    endpoints_info=endpoints_info,
                    source_code_snippets=source_code_snippets,
                )

            elif page_type == WikiPageType.MODULE:
                module_data = page_spec.get("data", {})
                module_name = page_spec["title"]

                # Find classes and endpoints for this module
                module_classes = [c for c in classes if module_name.lower() in c.get('file_path', '').lower()]
                module_endpoints = [e for e in endpoints if module_name.lower() in e.get('controller', '').lower()]

                source_files = "\n".join([
                    f"- `{c.get('file_path', '')}`" for c in module_classes[:10]
                ]) or "- No source files identified"

                classes_info = "\n".join([
                    f"- **{c.get('name')}** ({c.get('type', 'Class')}): Dependencies - {', '.join(c.get('dependencies', [])[:3])}"
                    for c in module_classes[:15]
                ]) or "No classes found"

                endpoints_info = "\n".join([
                    f"- {e.get('method', 'GET')} {e.get('path', '/')}: {e.get('handler', '')}"
                    for e in module_endpoints[:10]
                ]) or "No endpoints in this module"

                # Filter source code for this module's classes
                module_class_names = [c.get('name') for c in module_classes if c.get('name')]
                source_code_snippets = self._format_source_code_snippets(
                    source_code,
                    filter_classes=module_class_names if module_class_names else None,
                    max_total_chars=10000
                )

                prompt = MODULE_PROMPT.format(
                    module_name=module_name,
                    repo_name=repository.name,
                    source_files=source_files,
                    classes_info=classes_info,
                    functions_info="See individual class documentation",
                    endpoints_info=endpoints_info,
                    source_code_snippets=source_code_snippets,
                )

            elif page_type == WikiPageType.CLASS:
                class_data = page_spec.get("data", {})
                class_name = class_data.get("name", page_spec["title"])

                # Get the actual source code for this specific class
                class_source = source_code.get(class_name, {})
                class_source_code = class_source.get("code", "Source code not available for this class.")

                prompt = CLASS_PROMPT.format(
                    class_name=class_name,
                    file_path=class_data.get("file_path", "Unknown"),
                    class_type=class_data.get("type", "Class"),
                    dependencies=", ".join(class_data.get("dependencies", [])[:10]) or "None",
                    used_by="See dependency graph",
                    source_code=class_source_code,
                )

            elif page_type == WikiPageType.GETTING_STARTED:
                # Detect project structure from modules
                project_structure = "\n".join([
                    f"├── {m.get('name', '')}/" for m in modules[:10]
                ]) or "├── src/\n├── tests/"

                prompt = GETTING_STARTED_PROMPT.format(
                    repo_name=repository.name,
                    language=repository.language or "Unknown",
                    description=repository.description or "A software project",
                    project_structure=project_structure,
                    config_files="See repository root for configuration files",
                )

            elif page_type == WikiPageType.API:
                # Group endpoints by controller
                endpoints_by_controller: dict[str, list] = {}
                for ep in endpoints:
                    controller = ep.get("controller", "Other")
                    if controller not in endpoints_by_controller:
                        endpoints_by_controller[controller] = []
                    endpoints_by_controller[controller].append(ep)

                endpoints_grouped = "\n\n".join([
                    f"### {controller}\n" + "\n".join([
                        f"- {e.get('method', 'GET')} {e.get('path', '/')}: {e.get('handler', '')}"
                        for e in eps
                    ])
                    for controller, eps in endpoints_by_controller.items()
                ]) or "No endpoints discovered"

                controllers_info = "\n".join([
                    f"- **{c.get('name')}**: {c.get('file_path', '')}"
                    for c in classes if 'Controller' in str(c.get('labels', []))
                ][:10]) or "No controllers found"

                prompt = API_REFERENCE_PROMPT.format(
                    repo_name=repository.name,
                    endpoints_by_controller=endpoints_grouped,
                    controllers_info=controllers_info,
                )

            # ================================================================
            # NEW: Concept-based pages (DeepWiki-style)
            # ================================================================
            elif page_type in [WikiPageType.CONCEPT, WikiPageType.CORE_SYSTEM, WikiPageType.FEATURE, WikiPageType.INTEGRATION]:
                # Get concept data from page_spec
                concept_data = page_spec.get("data", {})
                concept_name = concept_data.get("name", page_spec["title"])
                concept_type = concept_data.get("type", "concept")
                concept_description = concept_data.get("description", f"Documentation for {concept_name}")
                related_classes_list = concept_data.get("related_classes", [])
                key_features = concept_data.get("key_features", [])

                # Format related classes
                related_classes = "\n".join([
                    f"- **{cls}**" for cls in related_classes_list[:15]
                ]) or "No related classes identified"

                # Format key features
                key_features_formatted = "\n".join([
                    f"- {feature}" for feature in key_features
                ]) or "See documentation below"

                # Get source code for related classes
                source_code_snippets = self._format_source_code_snippets(
                    source_code,
                    filter_classes=related_classes_list if related_classes_list else None,
                    max_total_chars=12000
                )

                prompt = CONCEPT_PAGE_PROMPT.format(
                    concept_name=concept_name,
                    concept_type=concept_type,
                    repo_name=repository.name,
                    concept_description=concept_description,
                    related_classes=related_classes,
                    key_features=key_features_formatted,
                    source_code_snippets=source_code_snippets,
                )

            elif page_type == WikiPageType.INSTALLATION:
                # Installation documentation
                project_structure = "\n".join([
                    f"├── {m.get('name', '')}/" for m in modules[:10]
                ]) or "├── src/\n├── tests/"

                source_code_snippets = self._format_source_code_snippets(source_code, max_total_chars=5000)

                prompt = USER_GUIDE_INSTALLATION_PROMPT.format(
                    repo_name=repository.name,
                    language=repository.language or "Unknown",
                    project_structure=project_structure,
                    config_files="See repository root",
                    dependency_info="See package.json / pom.xml / requirements.txt",
                    source_code_snippets=source_code_snippets,
                )

            elif page_type == WikiPageType.CONFIGURATION:
                # Configuration documentation
                source_code_snippets = self._format_source_code_snippets(source_code, max_total_chars=5000)

                prompt = USER_GUIDE_CONFIGURATION_PROMPT.format(
                    repo_name=repository.name,
                    config_files="application.properties, .env, config.yaml, etc.",
                    env_vars="See source code for environment variable usage",
                    source_code_snippets=source_code_snippets,
                )

            elif page_type == WikiPageType.TECH_STACK:
                # Tech stack documentation
                tech_stack = self._detect_tech_stack(codebase_data)
                source_code_snippets = self._format_source_code_snippets(source_code, max_total_chars=8000)

                prompt = f"""You are documenting the technology stack for {repository.name}.

## Detected Technologies
{tech_stack}

## Codebase Statistics
- Files: {stats.get('files', 0)}
- Classes: {stats.get('classes', 0)}
- Functions: {stats.get('functions', 0)}

## Source Code Samples
{source_code_snippets}

## Instructions
Generate comprehensive tech stack documentation with:

1. **Languages & Frameworks**: Primary languages and frameworks used
2. **Dependencies**: Key libraries and their purposes
3. **Architecture Patterns**: Design patterns and architectural decisions
4. **Build Tools**: Build and package management tools
5. **Testing**: Testing frameworks and tools
6. **Infrastructure**: Deployment and infrastructure technologies

Base everything on the actual code and imports observed.
Output ONLY the markdown content."""

            elif page_type == WikiPageType.DATA_MODEL:
                # Data model documentation
                # Find repository/entity classes
                data_classes = [c for c in classes if any(x in c.get('name', '').lower() for x in ['entity', 'model', 'dto', 'repository'])]

                data_classes_info = "\n".join([
                    f"- **{c.get('name')}**: {c.get('file_path', '')}"
                    for c in data_classes[:20]
                ]) or "No data model classes found"

                source_code_snippets = self._format_source_code_snippets(
                    source_code,
                    filter_classes=[c.get('name') for c in data_classes if c.get('name')],
                    max_total_chars=10000
                )

                prompt = f"""You are documenting the data models for {repository.name}.

## Data Model Classes
{data_classes_info}

## Source Code
{source_code_snippets}

## Instructions
Generate comprehensive data model documentation with:

1. **Overview**: How data is structured in this application
2. **Entity Relationship Diagram**: Mermaid ER diagram showing relationships
3. **Entities**: For each entity/model class:
   - Fields and their types
   - Relationships to other entities
   - Validation rules
4. **DTOs**: Data transfer objects and their purposes
5. **Database Schema**: Inferred database structure

Output ONLY the markdown content."""

            else:
                # Generic prompt for other page types
                prompt = f"""Generate documentation for a wiki page titled "{page_spec['title']}" for the {repository.name} codebase.
                Include relevant markdown formatting, headers, and code examples where appropriate.
                Output ONLY the markdown content."""

            # Send to LLM
            logger.info(f"[WIKI] Generating {page_type.value} page with LLM: {page_spec['title']}")
            response = await self._send_to_llm(prompt)

            if response:
                # Clean up the response (remove code blocks if present)
                content = response.strip()
                if content.startswith("```markdown"):
                    content = content[11:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                return content.strip()

            return None

        except Exception as e:
            logger.error(f"[WIKI] LLM generation error for {page_spec['title']}: {e}")
            return None

    def _generate_page_from_template(
        self,
        page_spec: dict,
        page_type: WikiPageType,
        codebase_data: dict,
        repository: RepositoryDB,
        stats: dict,
        modules: list,
        classes: list,
        endpoints: list,
    ) -> str:
        """Generate page content using templates (fallback when LLM unavailable)."""

        if page_type == WikiPageType.OVERVIEW:
            # Generate modules list
            modules_list = "\n".join([
                f"- [{m.get('name', 'Unknown')}](./modules/{m.get('name', '').lower().replace(' ', '-').replace('.', '-')}) - {m.get('file_count', 0)} files, {m.get('class_count', 0)} classes"
                for m in modules[:10]
            ]) or "- No modules discovered yet"

            # Detect tech stack from modules/classes
            tech_stack = self._detect_tech_stack(codebase_data)

            return OVERVIEW_TEMPLATE.format(
                repo_name=repository.name,
                description=repository.description or f"Documentation for {repository.name}",
                total_files=stats.get("files", 0),
                total_loc=stats.get("lines", "N/A"),
                total_classes=stats.get("classes", 0),
                total_functions=stats.get("functions", 0),
                test_coverage="N/A",
                tech_stack=tech_stack,
                modules_list=modules_list,
            )

        elif page_type == WikiPageType.ARCHITECTURE:
            # Build component lists
            controllers = [c for c in classes if 'Controller' in str(c.get('labels', []))]
            services = [c for c in classes if 'Service' in str(c.get('labels', []))]
            repositories = [c for c in classes if 'Repository' in str(c.get('type', ''))]

            return ARCHITECTURE_TEMPLATE.format(
                architecture_description=f"The {repository.name} system follows a layered architecture pattern.",
                presentation_components="\n        ".join([f"C{i}[{c.get('name', '')}]" for i, c in enumerate(controllers[:5])]) or "Controllers",
                business_components="\n        ".join([f"S{i}[{s.get('name', '')}]" for i, s in enumerate(services[:5])]) or "Services",
                data_components="\n        ".join([f"R{i}[{r.get('name', '')}]" for i, r in enumerate(repositories[:5])]) or "Repositories",
                presentation_description="Handles HTTP requests and responses, routing, and input validation.",
                business_description="Contains business logic, orchestrates operations, and enforces business rules.",
                data_description="Manages data persistence, queries, and database interactions.",
                patterns_list="- **Layered Architecture**: Separation of concerns across presentation, business, and data layers\n- **Repository Pattern**: Abstraction over data access\n- **Dependency Injection**: Loose coupling between components",
                dependencies_diagram="See package.json / pom.xml / requirements.txt for full dependency list.",
            )

        elif page_type == WikiPageType.MODULE:
            module_data = page_spec.get("data", {})
            module_name = page_spec["title"]

            # Find features/classes for this module
            module_classes = [c for c in classes if module_name.lower() in c.get('file_path', '').lower()]
            module_endpoints = [e for e in endpoints if module_name.lower() in e.get('controller', '').lower()]

            source_files = [c.get('file_path', '') for c in module_classes[:5]]
            source_files_list = "\n".join([f"- `{f}`" for f in source_files]) or "- No source files identified"

            features_table = "\n".join([
                f"| {c.get('name', '')} | {c.get('type', 'class')} | Medium |"
                for c in module_classes[:10]
            ]) or "| No features discovered | - | - |"

            components_list = "\n".join([
                f"- **{c.get('name', '')}** - {c.get('type', 'Component')}"
                for c in module_classes[:10]
            ]) or "- No components discovered"

            endpoints_table = "\n".join([
                f"| {e.get('method', 'GET')} | {e.get('path', '/')} | {e.get('handler', '')} |"
                for e in module_endpoints[:10]
            ]) or "| No endpoints | - | - |"

            return MODULE_TEMPLATE.format(
                module_name=module_name,
                source_files_list=source_files_list,
                module_description=f"The {module_name} module handles functionality related to {module_name.lower().replace('-', ' ')}.",
                features_table=features_table,
                components_list=components_list,
                endpoints_table=endpoints_table,
                related_modules="See other modules in the sidebar.",
            )

        elif page_type == WikiPageType.GETTING_STARTED:
            # Detect project type and generate appropriate instructions
            language = repository.language or "Unknown"

            if language.lower() in ["java", "kotlin"]:
                install = "```bash\nmvn install\n# or\ngradle build\n```"
                run = "```bash\nmvn spring-boot:run\n# or\ngradle bootRun\n```"
            elif language.lower() in ["javascript", "typescript"]:
                install = "```bash\nnpm install\n# or\nyarn install\n```"
                run = "```bash\nnpm run dev\n# or\nyarn dev\n```"
            elif language.lower() == "python":
                install = "```bash\npip install -r requirements.txt\n# or\npoetry install\n```"
                run = "```bash\npython main.py\n# or\nuvicorn app:app --reload\n```"
            else:
                install = "See project documentation for installation instructions."
                run = "See project documentation for run instructions."

            return GETTING_STARTED_TEMPLATE.format(
                prerequisites=f"- {language} runtime environment\n- Package manager\n- Database (if required)",
                installation_steps=install,
                configuration="Check `.env.example` or configuration files for required environment variables.",
                run_instructions=run,
                project_structure=f"{repository.name}/\n├── src/\n├── tests/\n├── docs/\n└── README.md",
            )

        elif page_type == WikiPageType.API:
            # Generate API reference
            endpoints_by_controller: dict[str, list] = {}
            for ep in endpoints:
                controller = ep.get("controller", "Other")
                if controller not in endpoints_by_controller:
                    endpoints_by_controller[controller] = []
                endpoints_by_controller[controller].append(ep)

            sections = []
            for controller, eps in endpoints_by_controller.items():
                table_rows = "\n".join([
                    f"| {e.get('method', 'GET')} | `{e.get('path', '/')}` | {e.get('handler', '')} |"
                    for e in eps
                ])
                sections.append(f"## {controller}\n\n| Method | Path | Handler |\n|--------|------|---------|{table_rows}")

            return f"# API Reference\n\n" + "\n\n".join(sections) if sections else "# API Reference\n\nNo API endpoints discovered."

        elif page_type == WikiPageType.CLASS:
            class_data = page_spec.get("data", {})
            return CLASS_TEMPLATE.format(
                class_name=class_data.get("name", page_spec["title"]),
                file_path=class_data.get("file_path", "Unknown"),
                module_name="Unknown",
                module_slug="unknown",
                class_type=class_data.get("type", "Class"),
                description=f"Implementation of {class_data.get('name', 'this class')}.",
                dependencies_diagram=" & ".join(class_data.get("dependencies", [])[:5]) or "None",
                methods_list="See source file for method documentation.",
                language=repository.language or "java",
                usage_example="// See source for usage examples",
                used_by_list="- Used by various components",
            )

        else:
            return f"# {page_spec['title']}\n\nContent for this page is being generated."

    def _detect_tech_stack(self, codebase_data: dict) -> str:
        """Detect and format tech stack from codebase data."""
        classes = codebase_data.get("classes", [])

        tech = set()
        for cls in classes:
            labels = cls.get("labels", [])
            if "SpringController" in labels or "SpringService" in labels:
                tech.add("Spring Framework")
            if "Repository" in str(labels):
                tech.add("JPA/Hibernate")

        if not tech:
            tech.add("See project configuration files")

        return "\n".join([f"- {t}" for t in sorted(tech)])

    async def get_wiki_tree(
        self,
        session: AsyncSession,
        repository_id: str
    ) -> dict:
        """Get wiki navigation tree structure."""
        wiki = await self.get_or_create_wiki(session, repository_id)

        if wiki.status == WikiStatus.NOT_GENERATED:
            return {"wiki": None, "tree": []}

        # Get all pages
        result = await session.execute(
            select(WikiPageDB)
            .where(WikiPageDB.wiki_id == wiki.id)
            .order_by(WikiPageDB.display_order)
        )
        pages = result.scalars().all()

        # Build tree structure
        tree = self._build_tree(pages)

        return {
            "wiki": {
                "id": wiki.id,
                "status": wiki.status.value,
                "total_pages": wiki.total_pages,
                "stale_pages": wiki.stale_pages,
                "commit_sha": wiki.commit_sha,
                "generation_mode": wiki.generation_mode,
                "generated_at": wiki.generated_at.isoformat() if wiki.generated_at else None,
            },
            "tree": tree,
        }

    def _build_tree(self, pages: list[WikiPageDB]) -> list[dict]:
        """Build hierarchical tree from flat page list."""
        # Create page lookup
        page_dict = {p.slug: p for p in pages}

        # Build tree
        tree = []
        children_map: dict[str, list] = {}

        for page in pages:
            node = {
                "slug": page.slug,
                "title": page.title,
                "type": page.page_type.value,
                "is_stale": page.is_stale,
                "children": [],
            }

            if page.parent_slug:
                if page.parent_slug not in children_map:
                    children_map[page.parent_slug] = []
                children_map[page.parent_slug].append(node)
            else:
                tree.append(node)

        # Attach children
        def attach_children(nodes):
            for node in nodes:
                if node["slug"] in children_map:
                    node["children"] = children_map[node["slug"]]
                    attach_children(node["children"])

        attach_children(tree)
        return tree

    async def get_page(
        self,
        session: AsyncSession,
        repository_id: str,
        slug: str
    ) -> Optional[dict]:
        """Get a specific wiki page by slug."""
        wiki = await self.get_or_create_wiki(session, repository_id)

        if wiki.status == WikiStatus.NOT_GENERATED:
            return None

        result = await session.execute(
            select(WikiPageDB).where(
                WikiPageDB.wiki_id == wiki.id,
                WikiPageDB.slug == slug
            )
        )
        page = result.scalar_one_or_none()

        if not page:
            return None

        # Get breadcrumbs
        breadcrumbs = await self._get_breadcrumbs(session, wiki.id, slug)

        # Get related pages
        related = []
        if page.related_pages:
            for related_slug in page.related_pages[:5]:
                related_result = await session.execute(
                    select(WikiPageDB.slug, WikiPageDB.title).where(
                        WikiPageDB.wiki_id == wiki.id,
                        WikiPageDB.slug == related_slug
                    )
                )
                related_page = related_result.first()
                if related_page:
                    related.append({"slug": related_page[0], "title": related_page[1]})

        return {
            "id": page.id,
            "slug": page.slug,
            "title": page.title,
            "type": page.page_type.value,
            "content": page.markdown_content,
            "summary": page.summary,
            "source_files": page.source_files,
            "is_stale": page.is_stale,
            "stale_reason": page.stale_reason,
            "updated_at": page.updated_at.isoformat(),
            "breadcrumbs": breadcrumbs,
            "related": related,
        }

    async def _get_breadcrumbs(
        self,
        session: AsyncSession,
        wiki_id: str,
        slug: str
    ) -> list[dict]:
        """Get breadcrumb navigation for a page."""
        breadcrumbs = []
        current_slug = slug

        while current_slug:
            result = await session.execute(
                select(WikiPageDB.slug, WikiPageDB.title, WikiPageDB.parent_slug).where(
                    WikiPageDB.wiki_id == wiki_id,
                    WikiPageDB.slug == current_slug
                )
            )
            page = result.first()
            if page:
                breadcrumbs.insert(0, {"slug": page[0], "title": page[1]})
                current_slug = page[2]
            else:
                break

        return breadcrumbs

    async def search_wiki(
        self,
        session: AsyncSession,
        repository_id: str,
        query: str,
        limit: int = 20
    ) -> list[dict]:
        """Search wiki pages by title and content."""
        wiki = await self.get_or_create_wiki(session, repository_id)

        if wiki.status == WikiStatus.NOT_GENERATED:
            return []

        # Simple ILIKE search (could be enhanced with full-text search)
        search_pattern = f"%{query}%"
        result = await session.execute(
            select(WikiPageDB)
            .where(
                WikiPageDB.wiki_id == wiki.id,
                (WikiPageDB.title.ilike(search_pattern)) |
                (WikiPageDB.markdown_content.ilike(search_pattern))
            )
            .limit(limit)
        )
        pages = result.scalars().all()

        return [
            {
                "slug": page.slug,
                "title": page.title,
                "type": page.page_type.value,
                "summary": page.summary or page.markdown_content[:200] + "...",
            }
            for page in pages
        ]


# Global service instance
_wiki_service: Optional[WikiService] = None


def get_wiki_service(
    neo4j_client=None,
    filesystem_client=None,
    copilot_session: Any = None
) -> WikiService:
    """Get or create wiki service instance.

    Args:
        neo4j_client: Neo4j client for querying code graph (metadata, relationships)
        filesystem_client: Filesystem MCP client for reading actual source code
        copilot_session: Copilot SDK session for LLM-powered generation

    Returns:
        WikiService instance
    """
    global _wiki_service
    if _wiki_service is None:
        _wiki_service = WikiService(neo4j_client, filesystem_client, copilot_session)
    return _wiki_service


def reset_wiki_service() -> None:
    """Reset the global wiki service instance (useful for testing or reconfiguration)."""
    global _wiki_service
    _wiki_service = None
