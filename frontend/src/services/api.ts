import axios from 'axios';
import type {
  AnalyzeRequest,
  AnalysisJob,
  GraphStats,
  QueryResult,
  ApiConfig,
  HealthStatus,
} from '../types/api';

// Codegraph API (for analysis jobs, graph stats)
const CODEGRAPH_API_URL = import.meta.env.VITE_CODEGRAPH_API_URL || '/api';

// Backend API (for repositories, BRD generation)
const BACKEND_API_URL = import.meta.env.VITE_BACKEND_API_URL || '/backend';

const codegraphApi = axios.create({
  baseURL: CODEGRAPH_API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

const backendApi = axios.create({
  baseURL: BACKEND_API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// =============================================================================
// Types for Repository and BRD
// =============================================================================

export interface RepositorySummary {
  id: string;
  name: string;
  url: string;
  platform: string;
  status: string;
  analysis_status: string;
  default_branch: string;
  last_analyzed_at?: string;
}

export interface RepositoryListResponse {
  success: boolean;
  data: RepositorySummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface BRDRequirement {
  id: string;
  title: string;
  description: string;
  priority: string;
  acceptance_criteria: string[];
}

export interface BRDResponse {
  id: string;
  title: string;
  version: string;
  created_at: string;
  business_context: string;
  objectives: string[];
  functional_requirements: BRDRequirement[];
  technical_requirements: BRDRequirement[];
  dependencies: string[];
  risks: string[];
  markdown: string;
}

export interface BRDTemplateConfig {
  brd_template?: string;
  organization_name?: string;
  document_prefix?: string;
  require_approvals?: boolean;
  approval_roles?: string[];
  include_code_references?: boolean;
  include_risk_matrix?: boolean;
  max_requirements_per_section?: number;
  custom_sections?: string[];
}

export interface GenerateBRDRequest {
  feature_description: string;
  affected_components?: string[];
  include_similar_features?: boolean;
  template_config?: BRDTemplateConfig;
  // Multi-agent verification settings (always enabled)
  max_iterations?: number;  // default: 3, range: 1-5
  min_confidence?: number;  // default: 0.7, range: 0-1
  show_evidence?: boolean;  // default: false
}

export interface StreamEvent {
  type: 'thinking' | 'content' | 'complete' | 'error';
  content?: string;
  data?: GenerateBRDResponse;
}

export interface GenerateBRDResponse {
  success: boolean;
  brd: BRDResponse;
  // Verification metrics (always included since multi-agent is always on)
  is_verified: boolean;
  confidence_score: number;
  hallucination_risk: string;
  iterations_used: number;
  // Evidence trail (only if show_evidence=true)
  evidence_trail?: Record<string, any>;
  evidence_trail_text?: string;
  // SME review
  needs_sme_review: boolean;
  sme_review_claims?: Array<{
    claim_id: string;
    text: string;
    section: string;
    status: string;
    confidence: number;
    hallucination_risk: string;
    needs_sme_review: boolean;
    evidence_count: number;
  }>;
  metadata?: Record<string, any>;
}

export interface EpicResponse {
  id: string;
  title: string;
  description: string;
  components: string[];
  priority: string;
  estimated_effort?: string;
  blocked_by?: string[];
  blocks?: string[];
  estimated_story_count?: number;
}

export interface GenerateEpicsRequest {
  brd: BRDResponse;
  use_skill?: boolean;
}

export interface GenerateEpicsResponse {
  success: boolean;
  brd_id: string;
  brd_title: string;
  epics: EpicResponse[];
  implementation_order: string[];
  metadata?: Record<string, any>;
}

// =============================================================================
// Codegraph API (Analysis)
// =============================================================================

// Health check
export async function getHealth(): Promise<HealthStatus> {
  const response = await codegraphApi.get<HealthStatus>('/health');
  return response.data;
}

// Get API config
export async function getConfig(): Promise<ApiConfig> {
  const response = await codegraphApi.get<ApiConfig>('/config');
  return response.data;
}

// Start analysis
export async function startAnalysis(request: AnalyzeRequest): Promise<{ jobId: string; statusUrl: string }> {
  const response = await codegraphApi.post<{ message: string; jobId: string; statusUrl: string }>('/analyze', request);
  return response.data;
}

// Get all jobs
export async function getJobs(): Promise<{ jobs: AnalysisJob[] }> {
  const response = await codegraphApi.get<{ jobs: AnalysisJob[] }>('/jobs');
  return response.data;
}

// Get job by ID
export async function getJob(jobId: string): Promise<AnalysisJob> {
  const response = await codegraphApi.get<AnalysisJob>(`/jobs/${jobId}`);
  return response.data;
}

// Get graph statistics
export async function getGraphStats(): Promise<GraphStats> {
  const response = await codegraphApi.get<GraphStats>('/graph/stats');
  return response.data;
}

// Execute query
export async function executeQuery(query: string, params?: Record<string, unknown>): Promise<QueryResult> {
  const response = await codegraphApi.post<QueryResult>('/query', { query, params });
  return response.data;
}

// Apply schema
export async function applySchema(): Promise<{ message: string }> {
  const response = await codegraphApi.post<{ message: string }>('/schema/apply');
  return response.data;
}

// Reset database
export async function resetDatabase(): Promise<{ message: string }> {
  const response = await codegraphApi.post<{ message: string }>('/schema/reset');
  return response.data;
}

// =============================================================================
// Backend API (Repositories & BRD Generation)
// =============================================================================

// Get repositories with optional filters
export async function getRepositories(params?: {
  status?: string;
  analysis_status?: string;
  limit?: number;
  offset?: number;
}): Promise<RepositoryListResponse> {
  const response = await backendApi.get<RepositoryListResponse>('/repositories', { params });
  return response.data;
}

// Get repositories with completed analysis
export async function getAnalyzedRepositories(): Promise<RepositorySummary[]> {
  const response = await backendApi.get<RepositoryListResponse>('/repositories', {
    params: {
      analysis_status: 'completed',
      limit: 100,
    },
  });
  return response.data.data;
}

// Generate BRD with streaming (SSE) - Multi-agent verification always enabled
export async function generateBRDStream(
  repositoryId: string,
  request: GenerateBRDRequest,
  onEvent: (event: StreamEvent) => void,
  onError?: (error: Error) => void
): Promise<void> {
  const url = `${BACKEND_API_URL}/brd/generate/${repositoryId}`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();

      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Process complete SSE messages
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep incomplete line in buffer

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const jsonData = line.slice(6); // Remove 'data: ' prefix
            if (jsonData.trim()) {
              const event: StreamEvent = JSON.parse(jsonData);
              onEvent(event);
            }
          } catch (parseError) {
            console.warn('Failed to parse SSE event:', parseError);
          }
        }
      }
    }
  } catch (error) {
    if (onError) {
      onError(error instanceof Error ? error : new Error(String(error)));
    } else {
      throw error;
    }
  }
}

// Generate Epics from BRD
export async function generateEpics(request: GenerateEpicsRequest): Promise<GenerateEpicsResponse> {
  const response = await backendApi.post<GenerateEpicsResponse>('/epics/generate', request);
  return response.data;
}

export default codegraphApi;
