#!/usr/bin/env node

/**
 * CodeGraph API Server Entry Point
 *
 * This is the main entry point for running CodeGraph as an HTTP API server.
 *
 * Usage:
 *   npm run api          # Start the API server
 *   npm run api:dev      # Start with ts-node for development
 *
 * Environment Variables:
 *   PORT           - Server port (default: 8001)
 *   NEO4J_URL      - Neo4j connection URL
 *   NEO4J_USER     - Neo4j username
 *   NEO4J_PASSWORD - Neo4j password
 *   NEO4J_DATABASE - Neo4j database name
 */

import { startServer } from './server.js';

const port = parseInt(process.env.PORT || '8001', 10);

startServer(port).catch(error => {
    console.error('Failed to start server:', error);
    process.exit(1);
});
