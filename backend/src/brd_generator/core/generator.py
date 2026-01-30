"""Main BRD Generator orchestrator with Copilot SDK integration."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from ..models.request import BRDRequest
from ..models.output import BRDOutput, BRDDocument, EpicsOutput, BacklogsOutput, JiraCreationResult, Epic, UserStory
from ..models.repository import Repository, RepositoryStatus, AnalysisStatus
from ..mcp_clients.neo4j_client import Neo4jMCPClient
from ..mcp_clients.filesystem_client import FilesystemMCPClient
from .aggregator import ContextAggregator
from .synthesizer import LLMSynthesizer, TemplateConfig
from .tool_registry import ToolRegistry
from .skill_loader import SkillLoader
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Default MCP config locations
MCP_CONFIG_PATHS = [
    Path.home() / ".copilot" / "mcp-config.json",  # User's home directory
    Path("/home/appuser/.copilot/mcp-config.json"),  # Docker container
    Path.cwd() / ".copilot" / "mcp-config.json",  # Project directory
]

# Default skills directories
SKILLS_DIRECTORIES = [
    Path.home() / ".github" / "skills",
    Path("/home/appuser/.github/skills"),
    Path.cwd() / ".github" / "skills",
]

# Try to import Copilot SDK
try:
    from copilot import CopilotClient, MCPServerConfig
    from copilot.generated.session_events import SessionEventType
    COPILOT_SDK_AVAILABLE = True
    logger.info("GitHub Copilot SDK available")
except ImportError:
    COPILOT_SDK_AVAILABLE = False
    CopilotClient = None
    MCPServerConfig = None
    SessionEventType = None
    logger.warning(
        "GitHub Copilot SDK not installed. "
        "Install with: pip install github-copilot-sdk"
    )


class BRDGenerator:
    """
    Main orchestrator for BRD generation.

    Uses GitHub Copilot CLI and SDK for LLM synthesis:
    - Copilot CLI provides the model server with native MCP support
    - MCP servers (Neo4j, Filesystem) are registered via SDK session config
    - Copilot SDK provides the Python client interface

    Coordinates the MCP clients, context aggregation, and LLM synthesis
    to generate Business Requirements Documents, Epics, and User Stories.
    """

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        copilot_model: Optional[str] = None,
        copilot_cli_path: Optional[str] = None,
        mcp_config_path: Optional[Path] = None,
        use_native_mcp: bool = True,
        skills_dir: Optional[Path] = None,
        template_config: Optional[TemplateConfig] = None,
        templates_dir: Optional[Path] = None,
    ):
        """
        Initialize the BRD Generator.

        Args:
            workspace_root: Root path for the codebase
            copilot_model: Model to use (e.g., "claude-sonnet-4-5", "gpt-4")
            copilot_cli_path: Path to Copilot CLI executable
            mcp_config_path: Path to MCP config file (default: ~/.copilot/mcp-config.json)
            use_native_mcp: Whether to use native MCP config (default: True)
            skills_dir: Path to skills directory for Copilot skills
            template_config: Configuration for BRD output templates (organizational standards)
            templates_dir: Directory containing custom template files
        """
        self.workspace_root = workspace_root or Path(os.getenv("CODEBASE_ROOT", str(Path.cwd())))
        self.copilot_model = copilot_model or os.getenv("COPILOT_MODEL", "claude-sonnet-4-5")
        self.copilot_cli_path = copilot_cli_path or os.getenv("COPILOT_CLI_PATH")
        self.mcp_config_path = mcp_config_path
        self.use_native_mcp = use_native_mcp
        self.template_config = template_config
        self.templates_dir = templates_dir

        # Skills directory - use package default if not specified
        if skills_dir:
            self.skills_dir = skills_dir
        else:
            from ..skills import get_skills_directory
            self.skills_dir = get_skills_directory()

        # MCP server configuration from environment
        self.neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
        self.neo4j_database = os.getenv("NEO4J_DATABASE", "codegraph")
        self.neo4j_read_only = os.getenv("NEO4J_READ_ONLY", "true")

        # Initialize MCP clients (for fallback/direct access)
        self.neo4j_client = Neo4jMCPClient()
        self.filesystem_client = FilesystemMCPClient(workspace_root=self.workspace_root)

        # Copilot SDK components (set in initialize())
        self._copilot_client: Optional[Any] = None
        self._copilot_session: Optional[Any] = None

        # Skill loader for dynamic skill matching
        self.skill_loader = SkillLoader(skills_dir=self.skills_dir)

        # Other components
        self.aggregator: Optional[ContextAggregator] = None
        self.synthesizer: Optional[LLMSynthesizer] = None
        self.tool_registry: Optional[ToolRegistry] = None
        self._initialized = False

    def _find_skills_dir(self) -> Optional[Path]:
        """Find the skills directory."""
        # Check environment variable first
        env_skills = os.getenv("MCP_SKILLS_DIR")
        if env_skills:
            path = Path(env_skills)
            if path.exists():
                return path

        # Check default locations
        for path in SKILLS_DIRECTORIES:
            if path.exists():
                return path

        return None

    def _build_mcp_servers_config(self) -> dict[str, Any]:
        """
        Build the MCP servers configuration for Copilot SDK session.

        This registers the MCP servers inline with the session, allowing
        the LLM to use neo4j and filesystem tools directly.

        Returns:
            Dictionary of MCP server configurations (MCPServerConfig format)
        """
        mcp_servers: dict[str, Any] = {}

        # Filesystem MCP Server
        if os.getenv("MCP_FILESYSTEM_ENABLED", "true").lower() == "true":
            codebase_path = str(self.workspace_root)
            mcp_servers["filesystem"] = {
                "type": "stdio",
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-filesystem",
                    codebase_path
                ],
                "tools": ["*"],
                "timeout": 30000
            }
            logger.info(f"Registered filesystem MCP server for: {codebase_path}")

        # Neo4j Code Graph MCP Server
        if os.getenv("MCP_NEO4J_ENABLED", "true").lower() == "true":
            mcp_servers["neo4j-code-graph"] = {
                "type": "stdio",
                "command": "npx",
                "args": [
                    "-y",
                    "@neo4j-contrib/mcp-neo4j"
                ],
                "tools": ["*"],
                "timeout": 30000,
                "env": {
                    "NEO4J_URI": self.neo4j_uri,
                    "NEO4J_USERNAME": self.neo4j_user,
                    "NEO4J_PASSWORD": self.neo4j_password,
                    "NEO4J_DATABASE": self.neo4j_database,
                    "NEO4J_READ_ONLY": self.neo4j_read_only
                }
            }
            logger.info(f"Registered Neo4j MCP server: {self.neo4j_uri}/{self.neo4j_database}")

        # Atlassian MCP Server (JIRA integration)
        if os.getenv("MCP_ATLASSIAN_ENABLED", "false").lower() == "true":
            atlassian_url = os.getenv("ATLASSIAN_URL", "")
            atlassian_email = os.getenv("ATLASSIAN_EMAIL", "")
            atlassian_token = os.getenv("ATLASSIAN_API_TOKEN", "")

            if atlassian_url and atlassian_email and atlassian_token:
                mcp_servers["atlassian"] = {
                    "type": "stdio",
                    "command": "npx",
                    "args": [
                        "-y",
                        "@anthropic/atlassian-mcp-server"
                    ],
                    "tools": ["*"],
                    "timeout": 60000,
                    "env": {
                        "ATLASSIAN_URL": atlassian_url,
                        "ATLASSIAN_EMAIL": atlassian_email,
                        "ATLASSIAN_API_TOKEN": atlassian_token
                    }
                }
                logger.info(f"Registered Atlassian MCP server: {atlassian_url}")
            else:
                logger.warning("Atlassian MCP enabled but missing configuration (URL, EMAIL, or API_TOKEN)")

        return mcp_servers

    async def initialize(self) -> None:
        """Initialize Copilot SDK client and all components."""
        if self._initialized:
            return

        logger.info("Initializing BRD Generator...")

        # Connect MCP clients (for fallback/direct access)
        await self.neo4j_client.connect()
        await self.filesystem_client.connect()

        # Create Tool Registry for MCP tools (fallback)
        self.tool_registry = ToolRegistry(
            neo4j_client=self.neo4j_client,
            filesystem_client=self.filesystem_client,
        )
        logger.info("Tool registry created with MCP tools")

        # Initialize Copilot SDK client
        if COPILOT_SDK_AVAILABLE and CopilotClient is not None:
            try:
                # Create and start the client
                self._copilot_client = CopilotClient()
                await self._copilot_client.start()
                logger.info("Copilot SDK client started")

                # Map model name to Copilot CLI format
                copilot_model = self._get_copilot_model(self.copilot_model)

                # Build MCP servers configuration
                mcp_servers = self._build_mcp_servers_config()

                # Create session configuration with MCP servers
                session_config = {
                    "model": copilot_model,
                    "streaming": True,
                    "mcp_servers": mcp_servers,
                }

                # Add skills directory for Copilot SDK native skill loading
                # skill_directories: List[str] - directories to load skills from
                if self.skills_dir and self.skills_dir.exists():
                    session_config["skill_directories"] = [str(self.skills_dir)]
                    logger.info(f"Registered skills directory: {self.skills_dir}")

                    # Load skills locally for reference/logging
                    self.skill_loader.load_skills()
                    skill_names = list(self.skill_loader.skills.keys())
                    logger.info(f"Skills available: {skill_names}")

                # Log configuration
                logger.info(f"Session config: model={copilot_model}, mcp_servers={list(mcp_servers.keys())}")

                self._copilot_session = await self._copilot_client.create_session(session_config)
                logger.info(f"Copilot session created with model: {copilot_model}")
                logger.info(f"MCP servers registered: {list(mcp_servers.keys())}")

            except Exception as e:
                logger.error(f"Failed to initialize Copilot SDK: {e}")
                logger.warning("Will use mock mode for LLM responses")
                self._copilot_client = None
                self._copilot_session = None
        else:
            logger.warning("Copilot SDK not available - using mock mode")

        # Initialize context aggregator
        self.aggregator = ContextAggregator(
            self.neo4j_client,
            self.filesystem_client,
        )

        # Initialize synthesizer with Copilot session and template config
        templates_dir = self.templates_dir or Path(__file__).parent.parent / "templates"

        self.synthesizer = LLMSynthesizer(
            session=self._copilot_session,
            templates_dir=templates_dir,
            model=self._get_copilot_model(self.copilot_model),
            tool_registry=self.tool_registry,
            template_config=self.template_config,
        )

        self._initialized = True
        logger.info("BRD Generator initialized")

    async def generate_brd(
        self,
        request: BRDRequest,
        use_skill: bool = True,
    ) -> BRDOutput:
        """
        PHASE 1: Generate BRD only (without Epics/Stories).

        This is the first step in the separated flow. Users review the BRD
        and then invoke generate_epics_from_brd() when satisfied.

        Args:
            request: BRD generation request
            use_skill: If True, use Copilot skills with MCP tools.
                      If False, use template-based approach.

        Returns:
            BRDOutput containing only the BRD document
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()
        logger.info(f"[PHASE 1] Generating BRD for: {request.feature_description}")
        logger.info(f"Mode: {'Skill-based (automatic)' if use_skill else 'Template-based'}")

        # Build context from MCP servers
        context = await self.aggregator.build_context(
            request=request.feature_description,
            affected_components=request.affected_components,
            include_similar=request.include_similar_features,
        )

        # Generate BRD using Copilot SDK
        brd = await self.synthesizer.generate_brd(context, use_skill=use_skill)

        # Build output (no epics/stories in Phase 1)
        elapsed_ms = int((time.time() - start_time) * 1000)

        output = BRDOutput(
            brd=brd,
            epics=[],  # Empty - generated in Phase 2
            backlogs=[],  # Empty - generated in Phase 2
            metadata={
                "copilot_model": self.copilot_model,
                "copilot_available": self._copilot_session is not None,
                "generation_mode": "skill-based" if use_skill else "template-based",
                "phase": "brd_only",
                "files_analyzed": len(context.implementation.key_files),
                "generation_time_ms": elapsed_ms,
                "components_found": len(context.architecture.components),
                "mcp_servers": ["filesystem", "neo4j-code-graph"],
            },
        )

        logger.info(f"[PHASE 1] BRD generation complete in {elapsed_ms}ms")
        return output

    async def generate_epics_from_brd(
        self,
        brd: BRDDocument,
        use_skill: bool = True,
    ) -> EpicsOutput:
        """
        PHASE 2: Generate Epics from an approved BRD.

        This is called after the user has reviewed and approved the BRD.
        Uses the generate-epics-from-brd skill to create Epics only.
        User Stories are generated separately in Phase 3.

        Args:
            brd: The approved BRD document
            use_skill: If True, use Copilot skills with MCP tools.

        Returns:
            EpicsOutput containing Epics only (no stories)
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()
        logger.info(f"[PHASE 2] Generating Epics from BRD: {brd.title}")

        # Generate Epics only (no stories)
        epics = await self.synthesizer.generate_epics_from_brd(
            brd=brd,
            use_skill=use_skill,
        )

        # Calculate implementation order based on epic dependencies
        implementation_order = self._calculate_epic_implementation_order(epics)

        elapsed_ms = int((time.time() - start_time) * 1000)

        output = EpicsOutput(
            brd_id=f"BRD-{hash(brd.title) % 10000:04d}",
            brd_title=brd.title,
            epics=epics,
            implementation_order=implementation_order,
            metadata={
                "copilot_model": self.copilot_model,
                "generation_mode": "skill-based" if use_skill else "template-based",
                "phase": "epics_only",
                "generation_time_ms": elapsed_ms,
                "total_epics": len(epics),
            },
        )

        logger.info(f"[PHASE 2] Generated {len(epics)} Epics in {elapsed_ms}ms")
        return output

    async def generate_backlogs_from_epics(
        self,
        epics_output: EpicsOutput,
        use_skill: bool = True,
    ) -> BacklogsOutput:
        """
        PHASE 3: Generate User Stories (Backlogs) from approved Epics.

        This is called after the user has reviewed and approved the Epics.
        Uses the generate-backlogs-from-epics skill to create User Stories.

        Args:
            epics_output: The approved Epics
            use_skill: If True, use Copilot skills with MCP tools.

        Returns:
            BacklogsOutput containing User Stories for each Epic
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()
        logger.info(f"[PHASE 3] Generating Backlogs from {len(epics_output.epics)} Epics")

        # Generate Stories from Epics
        stories = await self.synthesizer.generate_backlogs_from_epics(
            epics=epics_output.epics,
            use_skill=use_skill,
        )

        # Calculate implementation order based on story dependencies
        implementation_order = self._calculate_story_implementation_order(stories)

        # Calculate total story points
        total_points = sum(s.estimated_points or 0 for s in stories)

        elapsed_ms = int((time.time() - start_time) * 1000)

        output = BacklogsOutput(
            epics=epics_output.epics,
            stories=stories,
            implementation_order=implementation_order,
            metadata={
                "copilot_model": self.copilot_model,
                "generation_mode": "skill-based" if use_skill else "template-based",
                "phase": "backlogs",
                "generation_time_ms": elapsed_ms,
                "total_stories": len(stories),
                "total_story_points": total_points,
            },
        )

        logger.info(f"[PHASE 3] Generated {len(stories)} Stories ({total_points} points) in {elapsed_ms}ms")
        return output

    def _calculate_epic_implementation_order(self, epics: list[Epic]) -> list[str]:
        """Calculate the implementation order based on epic dependencies."""
        order = []
        remaining = {e.id: e for e in epics}
        completed = set()
        max_iterations = len(epics) * 2

        for _ in range(max_iterations):
            if not remaining:
                break
            ready = [
                epic_id for epic_id, epic in remaining.items()
                if all(dep in completed for dep in epic.blocked_by)
            ]
            if not ready:
                ready = list(remaining.keys())[:1]
            for epic_id in ready:
                order.append(epic_id)
                completed.add(epic_id)
                del remaining[epic_id]

        return order

    def _calculate_story_implementation_order(self, stories: list[UserStory]) -> list[str]:
        """Calculate the implementation order based on story dependencies."""
        order = []
        remaining = {s.id: s for s in stories}
        completed = set()
        max_iterations = len(stories) * 2

        for _ in range(max_iterations):
            if not remaining:
                break
            ready = [
                story_id for story_id, story in remaining.items()
                if all(dep in completed for dep in story.blocked_by)
            ]
            if not ready:
                ready = list(remaining.keys())[:1]
            for story_id in ready:
                order.append(story_id)
                completed.add(story_id)
                del remaining[story_id]

        return order

    async def create_jira_issues(
        self,
        backlogs_output: BacklogsOutput,
        project_key: str,
        use_skill: bool = True,
    ) -> JiraCreationResult:
        """
        PHASE 4: Create Epics and Stories in JIRA.

        This is called after the user has reviewed and approved the Backlogs/Stories.
        Uses the create-jira-issues skill with Atlassian MCP server.

        Args:
            backlogs_output: The approved Epics and Stories
            project_key: JIRA project key (e.g., "PROJ")
            use_skill: If True, use Copilot skills with Atlassian MCP.

        Returns:
            JiraCreationResult with created issue details
        """
        if not self._initialized:
            await self.initialize()

        # Check if Atlassian MCP is enabled
        if os.getenv("MCP_ATLASSIAN_ENABLED", "false").lower() != "true":
            logger.error("Atlassian MCP server not enabled. Set MCP_ATLASSIAN_ENABLED=true")
            return JiraCreationResult(
                project_key=project_key,
                errors=[{"issue": "Configuration", "error": "Atlassian MCP server not enabled"}],
            )

        start_time = time.time()
        logger.info(f"[PHASE 4] Creating JIRA issues in project: {project_key}")

        # Create issues using the synthesizer
        result = await self.synthesizer.create_jira_issues(
            epics=backlogs_output.epics,
            stories=backlogs_output.stories,
            project_key=project_key,
            use_skill=use_skill,
        )

        elapsed_ms = int((time.time() - start_time) * 1000)
        result.metadata["creation_time_ms"] = elapsed_ms

        logger.info(
            f"[PHASE 4] Created {len(result.epics_created)} Epics and "
            f"{len(result.stories_created)} Stories in {elapsed_ms}ms"
        )
        return result

    async def generate(
        self,
        request: BRDRequest,
        use_skill: bool = True,
    ) -> BRDOutput:
        """
        Generate BRD, epics, and backlogs in one call (legacy/convenience method).

        For the new separated flow, use:
        1. generate_brd() - Get BRD for review
        2. generate_epics_from_brd() - Get Epics/Stories for review
        3. create_jira_issues() - Create in JIRA

        Args:
            request: BRD generation request
            use_skill: If True, use Copilot skills with MCP tools.

        Returns:
            Complete BRD output with epics and stories
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()
        logger.info(f"Generating BRD (legacy mode) for: {request.feature_description}")
        logger.info(f"Mode: {'Skill-based (automatic)' if use_skill else 'Template-based'}")

        # Build context from MCP servers
        context = await self.aggregator.build_context(
            request=request.feature_description,
            affected_components=request.affected_components,
            include_similar=request.include_similar_features,
        )

        # Generate BRD
        brd = await self.synthesizer.generate_brd(context, use_skill=use_skill)

        # Generate Epics
        epics = await self.synthesizer.generate_epics(context, brd, use_skill=use_skill)

        # Generate User Stories/Backlogs
        backlogs = await self.synthesizer.generate_backlogs(context, epics, use_skill=use_skill)

        # Build output
        elapsed_ms = int((time.time() - start_time) * 1000)

        output = BRDOutput(
            brd=brd,
            epics=epics,
            backlogs=backlogs,
            metadata={
                "copilot_model": self.copilot_model,
                "copilot_available": self._copilot_session is not None,
                "generation_mode": "skill-based" if use_skill else "template-based",
                "neo4j_queries": 0,
                "files_analyzed": len(context.implementation.key_files),
                "generation_time_ms": elapsed_ms,
                "components_found": len(context.architecture.components),
                "context_tokens": context.estimated_tokens,
                "mcp_servers": ["filesystem", "neo4j-code-graph"],
            },
        )

        logger.info(f"BRD generation complete in {elapsed_ms}ms")
        return output

    async def generate_brd_for_repository(
        self,
        repository: Repository,
        request: BRDRequest,
        mcp_servers: Optional[dict[str, Any]] = None,
        use_skill: bool = True,
    ) -> BRDOutput:
        """
        Generate BRD for a specific onboarded repository.

        This method creates a repository-scoped BRD generation session with
        custom MCP server configuration for the repository's code access.

        Args:
            repository: The onboarded repository to generate BRD for.
            request: BRD generation request.
            mcp_servers: Optional custom MCP server configuration.
                        If not provided, uses default configuration.
            use_skill: If True, use Copilot skills with MCP tools.

        Returns:
            BRDOutput containing the BRD document.

        Raises:
            ValueError: If repository is not ready for BRD generation.
        """
        # Check if repository is ready for BRD generation
        if repository.status != RepositoryStatus.CLONED:
            raise ValueError(
                f"Repository {repository.name} is not cloned. "
                f"Current status: {repository.status}"
            )

        if repository.analysis_status != AnalysisStatus.COMPLETED:
            raise ValueError(
                f"Repository {repository.name} is not analyzed. "
                f"Analysis status: {repository.analysis_status}"
            )

        if not self._initialized:
            await self.initialize()

        start_time = time.time()
        logger.info(
            f"[PHASE 1] Generating BRD for repository: {repository.name}"
        )
        logger.info(f"Feature: {request.feature_description}")
        logger.info(f"Mode: {'Skill-based (automatic)' if use_skill else 'Template-based'}")

        # Use repository's local path as workspace root
        workspace_root = Path(repository.local_path) if repository.local_path else self.workspace_root

        # Build repository-specific MCP servers if not provided
        if mcp_servers is None:
            mcp_servers = self._build_repository_mcp_config(repository)

        # Create a temporary session with repository-specific MCP config if available
        session = self._copilot_session
        if mcp_servers and COPILOT_SDK_AVAILABLE and self._copilot_client:
            try:
                copilot_model = self._get_copilot_model(self.copilot_model)
                session_config = {
                    "model": copilot_model,
                    "streaming": True,
                    "mcp_servers": mcp_servers,
                }

                # skill_directories: List[str] - directories to load skills from
                if self.skills_dir and self.skills_dir.exists():
                    session_config["skill_directories"] = [str(self.skills_dir)]

                session = await self._copilot_client.create_session(session_config)
                logger.info(
                    f"Created repository-scoped session with MCP servers: "
                    f"{list(mcp_servers.keys())}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to create repository session, using default: {e}"
                )
                session = self._copilot_session

        # Create repository-scoped aggregator
        repo_filesystem_client = FilesystemMCPClient(workspace_root=workspace_root)
        await repo_filesystem_client.connect()

        repo_aggregator = ContextAggregator(
            self.neo4j_client,
            repo_filesystem_client,
        )

        # Build context
        context = await repo_aggregator.build_context(
            request=request.feature_description,
            affected_components=request.affected_components,
            include_similar=request.include_similar_features,
        )

        # Create synthesizer with repository session
        templates_dir = self.templates_dir or Path(__file__).parent.parent / "templates"
        repo_synthesizer = LLMSynthesizer(
            session=session,
            templates_dir=templates_dir,
            model=self._get_copilot_model(self.copilot_model),
            tool_registry=self.tool_registry,
            template_config=self.template_config,
        )

        # Generate BRD
        try:
            brd = await repo_synthesizer.generate_brd(context, use_skill=use_skill)
        finally:
            # Cleanup repository-scoped resources
            await repo_filesystem_client.disconnect()
            await repo_synthesizer.cleanup()

            # Destroy temporary session if we created one
            if session != self._copilot_session and session is not None:
                try:
                    await session.destroy()
                except Exception as e:
                    logger.warning(f"Error destroying repository session: {e}")

        # Build output
        elapsed_ms = int((time.time() - start_time) * 1000)

        output = BRDOutput(
            brd=brd,
            epics=[],
            backlogs=[],
            metadata={
                "copilot_model": self.copilot_model,
                "copilot_available": session is not None,
                "generation_mode": "skill-based" if use_skill else "template-based",
                "phase": "brd_only",
                "repository_id": repository.id,
                "repository_name": repository.name,
                "files_analyzed": len(context.implementation.key_files),
                "generation_time_ms": elapsed_ms,
                "components_found": len(context.architecture.components),
                "mcp_servers": list(mcp_servers.keys()) if mcp_servers else [],
            },
        )

        logger.info(
            f"[PHASE 1] BRD generation complete for {repository.name} in {elapsed_ms}ms"
        )
        return output

    def _build_repository_mcp_config(self, repository: Repository) -> dict[str, Any]:
        """
        Build MCP server configuration for a repository.

        Args:
            repository: The repository to build config for.

        Returns:
            Dictionary of MCP server configurations.
        """
        mcp_servers: dict[str, Any] = {}

        # Filesystem MCP for local clone
        if repository.local_path:
            mcp_servers[f"filesystem-{repository.id[:8]}"] = {
                "type": "stdio",
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-filesystem",
                    repository.local_path,
                ],
                "tools": ["*"],
                "timeout": 30000,
            }
            logger.info(f"Added filesystem MCP for: {repository.local_path}")

        # Neo4j code graph MCP
        mcp_servers["neo4j-code-graph"] = {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@neo4j-contrib/mcp-neo4j"],
            "tools": ["*"],
            "timeout": 30000,
            "env": {
                "NEO4J_URI": self.neo4j_uri,
                "NEO4J_USERNAME": self.neo4j_user,
                "NEO4J_PASSWORD": self.neo4j_password,
                "NEO4J_DATABASE": self.neo4j_database,
                "NEO4J_READ_ONLY": self.neo4j_read_only,
            },
        }
        logger.info(f"Added Neo4j MCP: {self.neo4j_uri}/{self.neo4j_database}")

        return mcp_servers

    async def cleanup(self) -> None:
        """Cleanup resources."""
        # Cleanup synthesizer
        if self.synthesizer is not None:
            await self.synthesizer.cleanup()

        # Cleanup Copilot session
        if self._copilot_session is not None:
            try:
                await self._copilot_session.destroy()
                logger.info("Copilot session destroyed")
            except Exception as e:
                logger.warning(f"Error destroying Copilot session: {e}")
            self._copilot_session = None

        # Cleanup Copilot client
        if self._copilot_client is not None:
            try:
                if hasattr(self._copilot_client, 'stop'):
                    await self._copilot_client.stop()
                logger.info("Copilot client stopped")
            except Exception as e:
                logger.warning(f"Error stopping Copilot client: {e}")
            self._copilot_client = None

        # Disconnect MCP clients
        await self.neo4j_client.disconnect()
        await self.filesystem_client.disconnect()

        self._initialized = False
        logger.info("BRD Generator cleaned up")

    def _find_mcp_config(self) -> Optional[Path]:
        """Find the native MCP config file."""
        if self.mcp_config_path and self.mcp_config_path.exists():
            return self.mcp_config_path

        for path in MCP_CONFIG_PATHS:
            if path.exists():
                logger.info(f"Found native MCP config at: {path}")
                return path

        return None

    def _load_mcp_config(self, config_path: Path) -> dict:
        """Load MCP configuration from file."""
        try:
            with open(config_path) as f:
                config = json.load(f)
            logger.info(f"Loaded MCP config with {len(config.get('mcp_servers', {}))} servers")
            return config
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return {}

    def _get_copilot_model(self, model_name: str) -> str:
        """Map model names to Copilot CLI model names."""
        model_mapping = {
            # Claude 4.5 models
            "claude-sonnet-4-5": "claude-sonnet-4.5",
            "claude-4-5-sonnet": "claude-sonnet-4.5",
            "claude-sonnet-4.5": "claude-sonnet-4.5",
            "sonnet-4.5": "claude-sonnet-4.5",
            "sonnet-4-5": "claude-sonnet-4.5",
            # Claude 4.5 Haiku
            "claude-haiku-4-5": "claude-haiku-4.5",
            "claude-haiku-4.5": "claude-haiku-4.5",
            "haiku-4.5": "claude-haiku-4.5",
            # Claude 4.5 Opus
            "claude-opus-4-5": "claude-opus-4.5",
            "claude-opus-4.5": "claude-opus-4.5",
            "opus-4.5": "claude-opus-4.5",
            # Claude 4 Sonnet
            "claude-sonnet-4": "claude-sonnet-4",
            "sonnet-4": "claude-sonnet-4",
            # GPT models
            "gpt-5": "gpt-5",
            "gpt-5.1": "gpt-5.1",
            "gpt-5.2": "gpt-5.2",
            "gpt-4.1": "gpt-4.1",
            # Gemini
            "gemini-3-pro": "gemini-3-pro-preview",
        }

        if model_name.lower() in model_mapping:
            return model_mapping[model_name.lower()]

        # If already a valid model name, use as-is
        valid_models = [
            "claude-sonnet-4.5", "claude-haiku-4.5", "claude-opus-4.5",
            "claude-sonnet-4", "gpt-5.2-codex", "gpt-5.1-codex-max",
            "gpt-5.1-codex", "gpt-5.2", "gpt-5.1", "gpt-5",
            "gpt-5.1-codex-mini", "gpt-5-mini", "gpt-4.1",
            "gemini-3-pro-preview"
        ]
        if model_name in valid_models:
            return model_name

        logger.warning(f"Unknown model '{model_name}', defaulting to claude-sonnet-4.5")
        return "claude-sonnet-4.5"

    async def __aenter__(self) -> "BRDGenerator":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.cleanup()
