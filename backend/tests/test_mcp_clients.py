"""
Tests for MCP clients.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from brd_generator.mcp_clients.neo4j_client import Neo4jMCPClient
from brd_generator.mcp_clients.filesystem_client import FilesystemMCPClient


class TestNeo4jMCPClient:
    """Tests for Neo4j MCP client."""

    @pytest.fixture
    def client(self) -> Neo4jMCPClient:
        """Create a Neo4j client instance."""
        return Neo4jMCPClient(server_url="http://localhost:8001")

    @pytest.mark.asyncio
    async def test_connect(self, client: Neo4jMCPClient):
        """Test client connection."""
        with patch.object(client, 'health_check', new_callable=AsyncMock) as mock_health:
            mock_health.return_value = True
            await client.connect()
            mock_health.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_code_structure(self, client: Neo4jMCPClient):
        """Test querying code structure."""
        mock_response = {
            "nodes": [
                {"id": "1", "labels": ["Class"], "properties": {"name": "UserService"}}
            ],
            "relationships": []
        }

        # Connect first
        with patch.object(client, 'health_check', new_callable=AsyncMock) as mock_health:
            mock_health.return_value = True
            await client.connect()

        with patch.object(client, 'call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response

            result = await client.query_code_structure("MATCH (n) RETURN n")

            assert "nodes" in result
            assert len(result["nodes"]) == 1

    @pytest.mark.asyncio
    async def test_get_component_dependencies(self, client: Neo4jMCPClient):
        """Test getting component dependencies."""
        mock_response = {
            "dependencies": ["Database", "Cache"],
            "dependents": ["APIController"]
        }

        with patch.object(client, 'call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response

            result = await client.get_component_dependencies("UserService")

            assert "dependencies" in result
            assert "Database" in result["dependencies"]

    @pytest.mark.asyncio
    async def test_search_similar_features(self, client: Neo4jMCPClient):
        """Test searching for similar features."""
        mock_response = [
            {"feature": "Login System", "similarity": 0.85},
            {"feature": "Password Reset", "similarity": 0.72}
        ]

        with patch.object(client, 'call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response

            result = await client.search_similar_features("user authentication")

            assert len(result) == 2
            assert result[0]["similarity"] > result[1]["similarity"]


class TestFilesystemMCPClient:
    """Tests for Filesystem MCP client."""

    @pytest.fixture
    def client(self) -> FilesystemMCPClient:
        """Create a Filesystem client instance."""
        return FilesystemMCPClient(server_url="http://localhost:8002")

    @pytest.mark.asyncio
    async def test_connect(self, client: FilesystemMCPClient):
        """Test client connection."""
        with patch.object(client, 'health_check', new_callable=AsyncMock) as mock_health:
            mock_health.return_value = True
            await client.connect()
            mock_health.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_file(self, client: FilesystemMCPClient):
        """Test reading a file."""
        mock_content = "def hello():\n    print('Hello, World!')"

        # Connect first
        with patch.object(client, 'health_check', new_callable=AsyncMock) as mock_health:
            mock_health.return_value = True
            await client.connect()

        with patch.object(client, 'call_tool', new_callable=AsyncMock) as mock_call:
            # Return plain content since read_file extracts from response
            mock_call.return_value = mock_content

            result = await client.read_file("src/main.py")

            assert result == mock_content

    @pytest.mark.asyncio
    async def test_list_directory(self, client: FilesystemMCPClient):
        """Test listing directory contents."""
        mock_response = [
            {"name": "main.py", "type": "file"},
            {"name": "utils", "type": "directory"}
        ]

        with patch.object(client, 'call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response

            result = await client.list_directory("src/")

            assert len(result) == 2
            assert result[0]["name"] == "main.py"

    @pytest.mark.asyncio
    async def test_search_files(self, client: FilesystemMCPClient):
        """Test searching files by pattern."""
        mock_response = [
            "src/services/auth.py",
            "src/services/user.py"
        ]

        with patch.object(client, 'call_tool', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response

            result = await client.search_files("*.py", "src/")

            assert len(result) == 2
            assert all(f.endswith(".py") for f in result)

class TestMCPClientErrors:
    """Tests for MCP client error handling."""

    @pytest.mark.asyncio
    async def test_neo4j_connection_graceful_degradation(self):
        """Test Neo4j client handles connection errors gracefully."""
        client = Neo4jMCPClient(server_url="http://invalid:9999")

        with patch.object(client, 'health_check', new_callable=AsyncMock) as mock_health:
            mock_health.side_effect = ConnectionError("Cannot connect")

            # Should not raise, just log warning and continue
            await client.connect()
            assert client._connected  # Still marks as connected

    @pytest.mark.asyncio
    async def test_filesystem_connection_graceful_degradation(self):
        """Test Filesystem client handles connection errors gracefully."""
        client = FilesystemMCPClient(server_url="http://invalid:9999")

        with patch.object(client, 'health_check', new_callable=AsyncMock) as mock_health:
            mock_health.side_effect = ConnectionError("Cannot connect")

            # Should not raise, just log warning and continue
            await client.connect()
            assert client._connected  # Still marks as connected
