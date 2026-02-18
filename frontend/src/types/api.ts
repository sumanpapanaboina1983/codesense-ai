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
  status: 'pending' | 'running' | 'completed' | 'failed' | 'paused' | 'cancelled';
  directory: string;
  gitUrl?: string;
  startedAt: string;
  completedAt?: string;
  error?: string;
  currentPhase?: string;
  progressPct?: number;
  repositoryId?: string;
  repositoryName?: string;
  stats?: {
    filesScanned: number;
    totalFiles?: number;
    nodesCreated: number;
    relationshipsCreated: number;
    classesFound?: number;
    methodsFound?: number;
    functionsFound?: number;
  };
  logs?: string[];
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

// =============================================================================
// Chat / Code Assistant Types
// =============================================================================

export interface Citation {
  id: string;
  file_path: string;
  line_start: number;
  line_end: number;
  snippet: string;
  entity_name?: string;
  relevance_score: number;
}

export interface RelatedEntity {
  name: string;
  type: string;
  file_path: string;
}

export interface ChatRequest {
  question: string;
  conversation_id?: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  related_entities: RelatedEntity[];
  follow_up_suggestions: string[];
  conversation_id: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  related_entities?: RelatedEntity[];
  follow_up_suggestions?: string[];
  timestamp: Date;
}

// =============================================================================
// Module Dependencies Types
// =============================================================================

export interface ModuleInfo {
  name: string;
  path: string;
  fileCount: number;
  classCount: number;
  functionCount: number;
  totalLoc: number;
  avgComplexity?: number | null;
  maxComplexity?: number | null;
  dependencies: string[];
  dependents: string[];
}

export interface ModuleDependencyEdge {
  source: string;
  target: string;
  weight: number;
}

export interface ModuleDependenciesResponse {
  success: boolean;
  repository_id: string;
  repository_name: string;
  modules: ModuleInfo[];
  dependencyGraph: ModuleDependencyEdge[];
  totalModules: number;
  avgDependencies: number;
}
