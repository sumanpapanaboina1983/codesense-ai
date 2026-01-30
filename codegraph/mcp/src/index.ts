#!/usr/bin/env node
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js"; // Use McpServer, import type
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { execa } from 'execa';
import path from 'path';
import { fileURLToPath } from 'url';
import { existsSync } from 'fs';
import { McpError, ErrorCode } from "@modelcontextprotocol/sdk/types.js"; // Import error types

// Define __dirname for ESM
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

 // Path to the compiled main script
 const analyzerScriptPath = path.resolve(__dirname, '..', '..', 'dist', 'index.js');

// Define the input schema for the run_analyzer tool - used for validation internally by SDK
const RunAnalyzerInputSchema = z.object({
  directory: z.string().describe("The absolute path to the project directory to analyze."),
  repositoryId: z.string().describe("UUID identifying the repository for multi-repository support."),
  repositoryName: z.string().optional().describe("Display name of the repository."),
  repositoryUrl: z.string().optional().describe("URL of the repository (e.g., GitHub URL)."),
});
// Define the expected shape of the arguments for the handler based on the schema
type RunAnalyzerArgs = z.infer<typeof RunAnalyzerInputSchema>;

// Create an MCP server
const server = new McpServer({
  name: "code-analyzer-mcp",
  version: "0.1.0"
});

// Add the run_analyzer tool
server.tool(
  "run_analyzer",
  // Provide the parameter shape, not the full schema object
  {
    directory: z.string(),
    repositoryId: z.string(),
    repositoryName: z.string().optional(),
    repositoryUrl: z.string().optional(),
  },
  // Let types be inferred for args and context, remove explicit McpResponse return type
  async (args, context) => {
    console.error(`[MCP Server Log] 'run_analyzer' tool called.`);

    // Type assertion for args based on the shape provided above
    const { directory, repositoryId, repositoryName, repositoryUrl } = args as RunAnalyzerArgs;
    const absoluteAnalysisDir = path.resolve(directory);
    const projectRootDir = path.resolve(__dirname, '..', '..');

    // Verify analyzer script exists
    if (!existsSync(analyzerScriptPath)) {
        console.error(`[MCP Server Log] Analyzer script not found at: ${analyzerScriptPath}`);
        return {
            content: [{ type: "text", text: `Analyzer script not found at: ${analyzerScriptPath}` }],
            isError: true
        };
    }

    // Verify target directory exists
    if (!existsSync(absoluteAnalysisDir)) {
        console.error(`[MCP Server Log] Target directory does not exist: ${absoluteAnalysisDir}`);
        return {
            content: [{ type: "text", text: `Target directory does not exist: ${absoluteAnalysisDir}` }],
            isError: true
        };
    }

    console.error(`[MCP Server Log] Attempting to run analyzer in: ${directory}`);
    console.error(`[MCP Server Log] Repository ID: ${repositoryId}`);
    console.error(`[MCP Server Log] Repository Name: ${repositoryName || 'not provided'}`);
    console.error(`[MCP Server Log] Analyzer script path: ${analyzerScriptPath}`);
    console.error(`[MCP Server Log] Target analysis directory (absolute): ${absoluteAnalysisDir}`);

    // --- Construct the manual command string with repository parameters ---
      const commandParts = [
        'node',
        `"${analyzerScriptPath}"`,
        'analyze',
        `"${absoluteAnalysisDir}"`,
        '--update-schema',
        '--repository-id', repositoryId,
        '--neo4j-url', process.env.NEO4J_URL || 'bolt://localhost:7687',
        '--neo4j-user', process.env.NEO4J_USER || 'neo4j',
        '--neo4j-password', process.env.NEO4J_PASSWORD || 'test1234',
        '--neo4j-database', process.env.NEO4J_DATABASE || 'codegraph'
      ];

      // Add optional repository name and URL if provided
      if (repositoryName) {
        commandParts.push('--repository-name', `"${repositoryName}"`);
      }
      if (repositoryUrl) {
        commandParts.push('--repository-url', `"${repositoryUrl}"`);
      }

      const commandString = commandParts.join(' ');

      console.error(`[MCP Server Log] Constructed command: ${commandString}`);
      console.error(`[MCP Server Log] Required CWD: ${projectRootDir}`);
      // Return the command details as JSON within the text content
      const commandDetails = {
           command: commandString,
          cwd: projectRootDir,
          repositoryId: repositoryId,
          repositoryName: repositoryName || path.basename(absoluteAnalysisDir)
      };
      return {
          content: [{ type: "text", text: JSON.stringify(commandDetails) }],
          _meta: { requires_execute_command: true } // Add metadata hint
      };
  }
);

// Add query_repository tool for repository-scoped graph queries
server.tool(
  "query_repository",
  {
    repositoryId: z.string().describe("UUID of the repository to query."),
    queryType: z.enum(["classes", "functions", "files", "call_graph", "imports"]).describe("Type of query to run."),
    limit: z.number().optional().describe("Maximum number of results to return (default: 100)."),
  },
  async (args) => {
    const { repositoryId, queryType, limit = 100 } = args;
    console.error(`[MCP Server Log] 'query_repository' tool called for repo: ${repositoryId}, query: ${queryType}`);

    // Build repository-scoped Cypher queries
    let cypherQuery: string;
    switch (queryType) {
      case "classes":
        cypherQuery = `
          MATCH (repo:Repository {repositoryId: $repositoryId})<-[:BELONGS_TO]-(f:File)-[:CONTAINS]->(c:Class)
          RETURN c.name as name, c.filePath as filePath, c.startLine as startLine
          LIMIT $limit
        `;
        break;
      case "functions":
        cypherQuery = `
          MATCH (repo:Repository {repositoryId: $repositoryId})<-[:BELONGS_TO]-(f:File)-[:CONTAINS]->(fn:Function)
          RETURN fn.name as name, fn.filePath as filePath, fn.startLine as startLine
          LIMIT $limit
        `;
        break;
      case "files":
        cypherQuery = `
          MATCH (repo:Repository {repositoryId: $repositoryId})<-[:BELONGS_TO]-(f:File)
          RETURN f.name as name, f.filePath as filePath, f.language as language
          LIMIT $limit
        `;
        break;
      case "call_graph":
        cypherQuery = `
          MATCH (repo:Repository {repositoryId: $repositoryId})<-[:BELONGS_TO]-(f:File)
          MATCH (f)-[:CONTAINS]->(caller:Function)-[:CALLS]->(callee:Function)
          RETURN caller.name as caller, callee.name as callee, f.filePath as filePath
          LIMIT $limit
        `;
        break;
      case "imports":
        cypherQuery = `
          MATCH (repo:Repository {repositoryId: $repositoryId})<-[:BELONGS_TO]-(f:File)-[:IMPORTS]->(i:Import)
          RETURN f.name as file, i.name as import, i.filePath as importPath
          LIMIT $limit
        `;
        break;
      default:
        return {
          content: [{ type: "text", text: `Unknown query type: ${queryType}` }],
          isError: true
        };
    }

    // Return the query for execution by the client
    const queryDetails = {
      query: cypherQuery,
      parameters: { repositoryId, limit },
      description: `Repository-scoped ${queryType} query`
    };

    return {
      content: [{ type: "text", text: JSON.stringify(queryDetails, null, 2) }],
      _meta: { query_type: "cypher" }
    };
  }
);

process.on('SIGINT', async () => {
    await server.close();
    process.exit(0);
});
process.on('SIGTERM', async () => {
    await server.close();
    process.exit(0);
});


// Start receiving messages on stdin and sending messages on stdout
async function startServer() {
    console.error('[MCP Server Log] Starting server...');
    const transport = new StdioServerTransport();
    console.error('[MCP Server Log] Stdio transport created.');
    await server.connect(transport);
    console.error('[MCP Server Log] Server connected to transport. Running on stdio.');
}

startServer().catch(console.error);