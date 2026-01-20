"""
Neo4j MCP Server - REST API wrapper for Neo4j graph database.
Provides endpoints for querying codebase structure and relationships.
"""

import os
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from neo4j import AsyncGraphDatabase
from pydantic import BaseModel


# Configuration from environment
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "3000"))


# Global driver
driver = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage Neo4j driver lifecycle."""
    global driver
    driver = AsyncGraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
    )
    yield
    await driver.close()


app = FastAPI(
    title="Neo4j MCP Server",
    description="MCP server for Neo4j graph database queries",
    version="1.0.0",
    lifespan=lifespan,
)


# Request/Response models
class QueryRequest(BaseModel):
    query: str
    parameters: Optional[dict[str, Any]] = None


class QueryResponse(BaseModel):
    nodes: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    paths: list[list[dict[str, Any]]]
    execution_time_ms: float


class HealthResponse(BaseModel):
    status: str
    neo4j_connected: bool


def serialize_node(node) -> dict[str, Any]:
    """Serialize a Neo4j node to dictionary."""
    return {
        "id": node.element_id,
        "labels": list(node.labels),
        **dict(node),
    }


def serialize_relationship(rel) -> dict[str, Any]:
    """Serialize a Neo4j relationship to dictionary."""
    return {
        "id": rel.element_id,
        "type": rel.type,
        "start_node": rel.start_node.element_id,
        "end_node": rel.end_node.element_id,
        **dict(rel),
    }


def serialize_path(path) -> list[dict[str, Any]]:
    """Serialize a Neo4j path to list of dictionaries."""
    result = []
    for node in path.nodes:
        result.append({"type": "node", **serialize_node(node)})
    for rel in path.relationships:
        result.append({"type": "relationship", **serialize_relationship(rel)})
    return result


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check server and Neo4j connection health."""
    try:
        async with driver.session() as session:
            await session.run("RETURN 1")
        return HealthResponse(status="healthy", neo4j_connected=True)
    except Exception as e:
        return HealthResponse(status="unhealthy", neo4j_connected=False)


@app.post("/query", response_model=QueryResponse)
async def execute_query(request: QueryRequest):
    """Execute a Cypher query against Neo4j."""
    if not driver:
        raise HTTPException(status_code=503, detail="Neo4j driver not initialized")

    start_time = time.time()
    nodes = []
    relationships = []
    paths = []

    try:
        async with driver.session() as session:
            result = await session.run(
                request.query,
                request.parameters or {},
            )
            records = await result.data()

            for record in records:
                for value in record.values():
                    if hasattr(value, "labels"):  # Node
                        nodes.append(serialize_node(value))
                    elif hasattr(value, "type") and hasattr(value, "start_node"):  # Relationship
                        relationships.append(serialize_relationship(value))
                    elif hasattr(value, "nodes"):  # Path
                        paths.append(serialize_path(value))
                    elif isinstance(value, dict):
                        nodes.append(value)
                    elif isinstance(value, (str, int, float, bool)):
                        nodes.append({"value": value})

        execution_time_ms = (time.time() - start_time) * 1000

        return QueryResponse(
            nodes=nodes,
            relationships=relationships,
            paths=paths,
            execution_time_ms=execution_time_ms,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Neo4j MCP Server",
        "version": "1.0.0",
        "status": "running",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
