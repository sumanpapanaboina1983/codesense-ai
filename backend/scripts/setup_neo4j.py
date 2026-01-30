#!/usr/bin/env python3
"""
Setup script for Neo4j database with code graph schema.

This script initializes the Neo4j database with:
- Required constraints and indexes
- Sample data for testing
"""

import asyncio
import os
from neo4j import AsyncGraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


async def create_constraints(driver):
    """Create uniqueness constraints."""
    constraints = [
        "CREATE CONSTRAINT component_name IF NOT EXISTS FOR (c:Component) REQUIRE c.name IS UNIQUE",
        "CREATE CONSTRAINT file_path IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE",
        "CREATE CONSTRAINT class_fqn IF NOT EXISTS FOR (c:Class) REQUIRE c.fqn IS UNIQUE",
        "CREATE CONSTRAINT function_fqn IF NOT EXISTS FOR (f:Function) REQUIRE f.fqn IS UNIQUE",
    ]

    async with driver.session() as session:
        for constraint in constraints:
            try:
                await session.run(constraint)
                print(f"Created constraint: {constraint[:50]}...")
            except Exception as e:
                print(f"Constraint may already exist: {e}")


async def create_indexes(driver):
    """Create indexes for common queries."""
    indexes = [
        "CREATE INDEX component_type IF NOT EXISTS FOR (c:Component) ON (c.type)",
        "CREATE INDEX file_language IF NOT EXISTS FOR (f:File) ON (f.language)",
        "CREATE INDEX class_name IF NOT EXISTS FOR (c:Class) ON (c.name)",
        "CREATE INDEX function_name IF NOT EXISTS FOR (f:Function) ON (f.name)",
    ]

    async with driver.session() as session:
        for index in indexes:
            try:
                await session.run(index)
                print(f"Created index: {index[:50]}...")
            except Exception as e:
                print(f"Index may already exist: {e}")


async def create_sample_data(driver):
    """Create sample data for testing."""
    sample_data = """
    // Create components
    MERGE (api:Component {name: 'APIService', type: 'service'})
    SET api.description = 'Main API service handling HTTP requests'

    MERGE (auth:Component {name: 'AuthService', type: 'service'})
    SET auth.description = 'Authentication and authorization service'

    MERGE (db:Component {name: 'DatabaseService', type: 'service'})
    SET db.description = 'Database access layer'

    MERGE (cache:Component {name: 'CacheService', type: 'service'})
    SET cache.description = 'Caching layer using Redis'

    // Create relationships
    MERGE (api)-[:DEPENDS_ON]->(auth)
    MERGE (api)-[:DEPENDS_ON]->(db)
    MERGE (auth)-[:DEPENDS_ON]->(db)
    MERGE (auth)-[:DEPENDS_ON]->(cache)
    MERGE (db)-[:DEPENDS_ON]->(cache)

    // Create files
    MERGE (f1:File {path: 'src/api/main.py'})
    SET f1.language = 'python', f1.lines = 250

    MERGE (f2:File {path: 'src/auth/service.py'})
    SET f2.language = 'python', f2.lines = 180

    MERGE (f3:File {path: 'src/db/repository.py'})
    SET f3.language = 'python', f3.lines = 320

    // Link components to files
    MERGE (api)-[:IMPLEMENTED_IN]->(f1)
    MERGE (auth)-[:IMPLEMENTED_IN]->(f2)
    MERGE (db)-[:IMPLEMENTED_IN]->(f3)

    RETURN 'Sample data created successfully' AS result
    """

    async with driver.session() as session:
        result = await session.run(sample_data)
        record = await result.single()
        print(record["result"])


async def verify_setup(driver):
    """Verify the database setup."""
    queries = [
        ("Component count", "MATCH (c:Component) RETURN count(c) AS count"),
        ("File count", "MATCH (f:File) RETURN count(f) AS count"),
        ("Relationship count", "MATCH ()-[r]->() RETURN count(r) AS count"),
    ]

    async with driver.session() as session:
        print("\nVerification:")
        for name, query in queries:
            result = await session.run(query)
            record = await result.single()
            print(f"  {name}: {record['count']}")


async def main():
    """Main setup function."""
    print(f"Connecting to Neo4j at {NEO4J_URI}...")

    driver = AsyncGraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )

    try:
        # Verify connectivity
        await driver.verify_connectivity()
        print("Connected successfully!")

        # Run setup
        await create_constraints(driver)
        await create_indexes(driver)
        await create_sample_data(driver)
        await verify_setup(driver)

        print("\nNeo4j setup complete!")

    except Exception as e:
        print(f"Error: {e}")
        raise

    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
