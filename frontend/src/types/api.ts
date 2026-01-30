// API Types for CodeGraph

export interface AnalyzeRequest {
  directory?: string;
  gitUrl?: string;
  branch?: string;
  gitToken?: string;
  repositoryId: string;
  repositoryName?: string;
  repositoryUrl?: string;
  updateSchema?: boolean;
  resetDb?: boolean;
  keepClone?: boolean;
}

export interface AnalysisJob {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  directory: string;
  gitUrl?: string;
  startedAt: string;
  completedAt?: string;
  error?: string;
  stats?: {
    filesScanned: number;
    nodesCreated: number;
    relationshipsCreated: number;
  };
}

export interface GraphStats {
  totalNodes: number;
  totalRelationships: number;
  nodesByLabel: Record<string, number>;
  relationshipsByType: Record<string, number>;
}

export interface Repository {
  id: string;
  name: string;
  url?: string;
  localPath?: string;
  gitUrl?: string;
  status: 'pending' | 'analyzing' | 'completed' | 'failed';
  lastAnalyzedAt?: string;
  analyzedAt?: string;
}

export interface QueryResult {
  records: Record<string, any>[];
  count: number;
}

export interface ApiConfig {
  neo4jUrl: string;
  neo4jDatabase: string;
  supportedExtensions: string[];
  ignorePatterns: string[];
}

export interface HealthStatus {
  status: 'healthy' | 'unhealthy';
  neo4j: 'connected' | 'disconnected';
  timestamp: string;
  error?: string;
}
