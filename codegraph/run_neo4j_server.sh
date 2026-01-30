#!/bin/bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USERNAME="neo4j"
export NEO4J_PASSWORD="test@123"
export NEO4J_DATABASE="codegraph"

# Execute the actual server script
node ./node_modules/@alanse/mcp-neo4j-server/build/server.js

