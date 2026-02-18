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
  baseURL: `${BACKEND_API_URL}/api/v1`,
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

// =============================================================================
// Enums for BRD Generation
// =============================================================================

export type GenerationMode = 'draft' | 'verified';
export type GenerationApproach = 'context_first' | 'skills_only' | 'auto';
export type DetailLevel = 'concise' | 'standard' | 'detailed';

// =============================================================================
// Sufficiency Criteria for Context Gathering
// =============================================================================

export interface SufficiencyDimension {
  name: string;
  description: string;
  required: boolean;
  min_evidence?: number;
}

export interface SufficiencyCriteria {
  dimensions?: SufficiencyDimension[];
  min_required_dimensions?: number;
  min_total_evidence?: number;
}

// =============================================================================
// Verification Limits
// =============================================================================

export interface VerificationLimits {
  max_entities_per_claim?: number;
  max_patterns_per_claim?: number;
  results_per_query?: number;
  code_refs_per_evidence?: number;
}

// =============================================================================
// Custom BRD Section
// =============================================================================

export interface BRDSection {
  name: string;
  description?: string;
  required?: boolean;
}

// =============================================================================
// Verification Report Types
// =============================================================================

export interface CodeReferenceItem {
  file_path: string;
  start_line: number;
  end_line: number;
  snippet?: string;
  explanation?: string;  // Why this code supports the claim
  entity_name?: string;  // Class/method/function name
  entity_type?: string;  // Class, Method, Function, etc.
}

export interface ClaimVerificationDetail {
  claim_id: string;
  claim_text: string;
  section: string;
  status: 'verified' | 'partially_verified' | 'unverified' | 'contradicted';
  confidence: number;
  is_verified: boolean;
  hallucination_risk: 'low' | 'medium' | 'high';
  needs_sme_review: boolean;
  evidence_count: number;
  evidence_types: string[];
  code_references: CodeReferenceItem[];
  verification_summary?: string;  // Brief summary of why claim is verified/not
}

export interface SectionVerificationReport {
  section_name: string;
  status: 'verified' | 'partially_verified' | 'unverified' | 'contradicted';
  confidence: number;
  hallucination_risk: string;
  total_claims: number;
  verified_claims: number;
  partially_verified_claims: number;
  unverified_claims: number;
  contradicted_claims: number;
  claims_needing_sme: number;
  verification_rate: number;
  claims: ClaimVerificationDetail[];
}

export interface VerificationReport {
  brd_id: string;
  brd_title: string;
  generated_at: string;
  overall_status: 'verified' | 'partially_verified' | 'unverified';
  overall_confidence: number;
  hallucination_risk: string;
  is_approved: boolean;
  total_claims: number;
  verified_claims: number;
  partially_verified_claims: number;
  unverified_claims: number;
  contradicted_claims: number;
  claims_needing_sme: number;
  verification_rate: number;
  sections: SectionVerificationReport[];
}

// =============================================================================
// BRD Generation Request
// =============================================================================

export interface GenerateBRDRequest {
  feature_description: string;

  // Generation mode selection
  mode?: GenerationMode;  // default: 'draft'

  // Generation approach selection
  approach?: GenerationApproach;  // default: 'auto'

  affected_components?: string[];
  include_similar_features?: boolean;  // default: true

  // Output control
  detail_level?: DetailLevel;  // default: 'standard'

  // Custom sections
  sections?: BRDSection[];

  // Template-driven BRD generation
  brd_template?: string;
  template_config?: BRDTemplateConfig;

  // Custom sections with word count configuration
  custom_sections?: Array<{
    name: string;
    description?: string;
    target_words?: number;
  }>;

  // Multi-agent verification settings (VERIFIED mode only)
  max_iterations?: number;  // default: 3, range: 1-10
  min_confidence?: number;  // default: 0.7, range: 0-1
  show_evidence?: boolean;  // default: false

  // Sufficiency criteria
  sufficiency_criteria?: SufficiencyCriteria;

  // Verification query limits (VERIFIED mode only)
  verification_limits?: VerificationLimits;

  // Model selection
  model?: string;  // LLM model to use (e.g., 'gpt-4.1', 'claude-sonnet-4.5')

  // Consistency controls for reproducible outputs
  temperature?: number;  // default: 0.3, range: 0-1 (lower = more consistent)
  seed?: number;  // optional, for reproducible outputs
}

export interface StreamEvent {
  type: 'thinking' | 'content' | 'complete' | 'error';
  content?: string;
  data?: GenerateBRDResponse;
}

export interface GenerateBRDResponse {
  success: boolean;
  brd: BRDResponse;

  // Generation mode used
  mode: GenerationMode;

  // Verification metrics (populated in VERIFIED mode, may be null in DRAFT)
  is_verified?: boolean;
  confidence_score?: number;
  hallucination_risk?: string;
  iterations_used?: number;

  // Complete verification report (VERIFIED mode only)
  verification_report?: VerificationReport;

  // Evidence trail (only if show_evidence=true in VERIFIED mode)
  evidence_trail?: Record<string, any>;
  evidence_trail_text?: string;

  // SME review
  needs_sme_review?: boolean;
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

  // Draft mode warning
  draft_warning?: string;

  metadata?: Record<string, any>;
}

export interface EpicResponse {
  id: string;
  title: string;
  description: string;
  components: string[];
  blocked_by?: string[];
  blocks?: string[];
  estimated_story_count?: number;
}

export interface GenerateEpicsRequestLegacy {
  brd: BRDResponse;
  use_skill?: boolean;
}

export interface GenerateEpicsResponseLegacy {
  success: boolean;
  brd_id: string;
  brd_title: string;
  epics: EpicResponse[];
  implementation_order: string[];
  metadata?: Record<string, any>;
}

export interface RefineEpicsResponse {
  success: boolean;
  epics: Epic[];
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

// Job list response from backend
interface BackendJobListResponse {
  success: boolean;
  jobs: Array<{
    id: string;
    repository_id: string;
    repository_name?: string;
    status: string;
    current_phase?: string;
    progress_pct: number;
    commit_sha?: string;
    branch?: string;
    triggered_by: string;
    stats?: Record<string, any>;
    created_at: string;
    started_at?: string;
    completed_at?: string;
    duration_seconds?: number;
    error?: string;
  }>;
  total: number;
  limit: number;
  offset: number;
}

// Get all jobs from backend (persisted in PostgreSQL)
export async function getJobs(): Promise<{ jobs: AnalysisJob[] }> {
  const response = await backendApi.get<BackendJobListResponse>('/jobs');

  // Transform backend format to AnalysisJob format
  // Handle both snake_case (backend standard) and camelCase (codegraph legacy) stats keys
  const jobs: AnalysisJob[] = response.data.jobs.map(job => ({
    id: job.id,
    status: job.status as 'pending' | 'running' | 'completed' | 'failed',
    directory: job.repository_name || 'Unknown',
    gitUrl: undefined,
    startedAt: job.started_at || job.created_at,
    completedAt: job.completed_at,
    error: job.error,
    stats: job.stats ? {
      filesScanned: job.stats.files_scanned || job.stats.filesScanned || job.stats.total_files || 0,
      totalFiles: job.stats.total_files || job.stats.totalFiles || 0,
      nodesCreated: job.stats.nodes_created || job.stats.nodesCreated || 0,
      relationshipsCreated: job.stats.relationships_created || job.stats.relationshipsCreated || 0,
      classesFound: job.stats.classes_found || job.stats.classesFound || 0,
      methodsFound: job.stats.methods_found || job.stats.methodsFound || 0,
      functionsFound: job.stats.functions_found || job.stats.functionsFound || 0,
    } : undefined,
    currentPhase: job.current_phase,
    progressPct: job.progress_pct,
    repositoryId: job.repository_id,
    repositoryName: job.repository_name,
  }));

  return { jobs };
}

// Get job by ID from backend
export async function getJob(jobId: string): Promise<AnalysisJob> {
  const response = await backendApi.get<{ success: boolean; job: JobDetail }>(`/jobs/${jobId}`);
  const job = response.data.job;

  // Transform JobDetail to AnalysisJob format
  // Handle both snake_case (backend standard) and camelCase (codegraph legacy) stats keys
  return {
    id: job.id,
    status: job.status as 'pending' | 'running' | 'completed' | 'failed',
    directory: job.repository_name || 'Unknown',
    gitUrl: undefined,
    startedAt: job.started_at || job.created_at,
    completedAt: job.completed_at,
    error: job.error,
    stats: job.stats ? {
      filesScanned: job.stats.files_scanned || job.stats.filesScanned || job.stats.total_files || 0,
      totalFiles: job.stats.total_files || job.stats.totalFiles || 0,
      nodesCreated: job.stats.nodes_created || job.stats.nodesCreated || 0,
      relationshipsCreated: job.stats.relationships_created || job.stats.relationshipsCreated || 0,
      classesFound: job.stats.classes_found || job.stats.classesFound || 0,
      methodsFound: job.stats.methods_found || job.stats.methodsFound || 0,
      functionsFound: job.stats.functions_found || job.stats.functionsFound || 0,
    } : undefined,
    currentPhase: job.current_phase,
    progressPct: job.progress_pct,
    repositoryId: job.repository_id,
    repositoryName: job.repository_name,
    // Include logs from backend
    logs: job.recent_logs?.map(log => `[${log.level.toUpperCase()}] [${log.phase}] ${log.message}`),
  };
}

// =============================================================================
// Backend Jobs API (with checkpointing support)
// =============================================================================

export interface JobCheckpoint {
  id: string;
  current_phase: string;
  phase_progress_pct: number;
  total_files: number;
  processed_files: number;
  last_processed_file?: string;
  nodes_created: number;
  relationships_created: number;
  checkpoint_data?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface JobLog {
  id: string;
  level: string;
  phase: string;
  message: string;
  details?: Record<string, any>;
  created_at: string;
}

export interface JobDetail {
  id: string;
  repository_id: string;
  repository_name?: string;
  status: string;
  current_phase?: string;
  progress_pct: number;
  commit_sha?: string;
  branch?: string;
  triggered_by: string;
  stats?: Record<string, any>;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  error?: string;
  checkpoints: JobCheckpoint[];
  recent_logs: JobLog[];
  can_resume: boolean;
  can_cancel: boolean;
}

export interface JobDetailResponse {
  success: boolean;
  job: JobDetail;
}

export interface JobProgressEvent {
  type: 'progress' | 'phase' | 'complete' | 'error';
  phase?: string;
  progress_pct: number;
  processed_files: number;
  total_files: number;
  nodes_created: number;
  relationships_created: number;
  message?: string;
  status?: string;
  error?: string;
}

export interface ResumeResponse {
  success: boolean;
  message: string;
  job_id: string;
  phase: string;
  progress_pct: number;
}

export interface CancelResponse {
  success: boolean;
  message: string;
  job_id: string;
}

// Get detailed job info from codegraph (same source as job list)
export async function getJobDetail(jobId: string): Promise<JobDetailResponse> {
  const response = await codegraphApi.get<AnalysisJob>(`/jobs/${jobId}`);
  const job = response.data;

  // Transform codegraph job format to JobDetail format
  return {
    success: true,
    job: {
      id: job.id,
      repository_id: job.directory || '',
      repository_name: job.gitUrl || job.directory?.split('/').pop() || 'Unknown',
      status: job.status,
      current_phase: job.currentPhase,
      progress_pct: job.progressPct || 0,
      commit_sha: undefined,
      branch: undefined,
      triggered_by: 'manual',
      stats: job.stats,
      created_at: job.startedAt,
      started_at: job.startedAt,
      completed_at: job.completedAt,
      duration_seconds: job.completedAt && job.startedAt
        ? Math.floor((new Date(job.completedAt).getTime() - new Date(job.startedAt).getTime()) / 1000)
        : undefined,
      error: job.error,
      checkpoints: [],
      recent_logs: [],
      can_resume: job.status === 'failed',
      can_cancel: job.status === 'running' || job.status === 'pending',
    },
  };
}

// Cancel a running job (use backendApi since jobs are now persisted in PostgreSQL)
export async function cancelJob(jobId: string): Promise<CancelResponse> {
  const response = await backendApi.post<CancelResponse>(`/jobs/${jobId}/cancel`);
  return response.data;
}

// Pause a running job (can be resumed later)
export interface PauseResponse {
  success: boolean;
  message: string;
  job_id: string;
  phase: string;
  progress_pct: number;
}

export async function pauseJob(jobId: string): Promise<PauseResponse> {
  const response = await backendApi.post<PauseResponse>(`/jobs/${jobId}/pause`);
  return response.data;
}

// Resume a paused or failed job
export interface ResumeResponse {
  success: boolean;
  message: string;
  job_id: string;
  phase: string;
  progress_pct: number;
}

export async function resumeJob(jobId: string): Promise<ResumeResponse> {
  const response = await backendApi.post<ResumeResponse>(`/jobs/${jobId}/resume`);
  return response.data;
}

// Delete a job (use backendApi since jobs are now persisted in PostgreSQL)
export interface DeleteJobResponse {
  success: boolean;
  message: string;
  job_id: string;
}

export async function deleteJob(jobId: string): Promise<DeleteJobResponse> {
  const response = await backendApi.delete<DeleteJobResponse>(`/jobs/${jobId}`);
  return response.data;
}

// Get all logs for a job (with pagination support for large log sets)
export async function getJobLogs(
  jobId: string,
  options?: { level?: string; limit?: number; offset?: number }
): Promise<JobLog[]> {
  const params: Record<string, string | number> = {
    limit: options?.limit || 1000,
    offset: options?.offset || 0,
  };
  if (options?.level) {
    params.level = options.level;
  }
  const response = await backendApi.get<JobLog[]>(`/jobs/${jobId}/logs`, { params });
  return response.data;
}

// Download all logs for a job as a text file
export async function downloadJobLogs(jobId: string): Promise<void> {
  const response = await backendApi.get(`/jobs/${jobId}/logs/download`, {
    responseType: 'blob',
  });

  // Create download link
  const blob = new Blob([response.data], { type: 'text/plain' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;

  // Extract filename from Content-Disposition header or use default
  const contentDisposition = response.headers['content-disposition'];
  let filename = `analysis-logs-${jobId.substring(0, 8)}.txt`;
  if (contentDisposition) {
    const match = contentDisposition.match(/filename="?([^"]+)"?/);
    if (match) {
      filename = match[1];
    }
  }

  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

// Stream job progress via SSE
export function streamJobProgress(
  jobId: string,
  onProgress: (event: JobProgressEvent) => void,
  onError?: (error: Error) => void
): () => void {
  const url = `${BACKEND_API_URL}/api/v1/jobs/${jobId}/progress/stream`;

  const eventSource = new EventSource(url);

  eventSource.onmessage = (event) => {
    try {
      const data: JobProgressEvent = JSON.parse(event.data);
      onProgress(data);

      // Close on completion or error
      if (data.type === 'complete' || data.type === 'error') {
        eventSource.close();
      }
    } catch (e) {
      console.error('Failed to parse SSE data:', e);
    }
  };

  eventSource.onerror = (event) => {
    console.error('SSE error:', event);
    eventSource.close();
    if (onError) {
      onError(new Error('Connection lost'));
    }
  };

  // Return cleanup function
  return () => {
    eventSource.close();
  };
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

// Get default BRD template
export interface DefaultTemplateResponse {
  success: boolean;
  template: string;
  name: string;
  description: string;
}

export async function getDefaultTemplate(): Promise<DefaultTemplateResponse> {
  const response = await backendApi.get<DefaultTemplateResponse>('/brd/template/default');
  return response.data;
}

// Parse template sections using LLM
export interface TemplateSectionInfo {
  name: string;
  description?: string;
  suggested_words: number;
}

export interface ParseTemplateSectionsResponse {
  success: boolean;
  sections: TemplateSectionInfo[];
  error?: string;
}

export async function parseTemplateSections(templateContent: string): Promise<ParseTemplateSectionsResponse> {
  const response = await backendApi.post<ParseTemplateSectionsResponse>('/brd/template/parse-sections', {
    template_content: templateContent,
  });
  return response.data;
}

// List available LLM models
export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  description: string;
  min_tier: string;
  is_recommended: boolean;
  is_default: boolean;
  context_window?: number;
  strengths: string[];
  status: string;
}

export interface ListModelsResponse {
  models: ModelInfo[];
  default_model: string;
  recommended_models: string[];
}

export async function listAvailableModels(): Promise<ListModelsResponse> {
  const response = await backendApi.get<ListModelsResponse>('/brd/models');
  return response.data;
}

// Cancellation controller for BRD generation
let currentBRDGenerationController: AbortController | null = null;
let currentBRDGenerationRepositoryId: string | null = null;

// Generate BRD with streaming (SSE) - Multi-agent verification always enabled
export async function generateBRDStream(
  repositoryId: string,
  request: GenerateBRDRequest,
  onEvent: (event: StreamEvent) => void,
  onError?: (error: Error) => void,
  onCancel?: () => void
): Promise<void> {
  const url = `${BACKEND_API_URL}/api/v1/brd/generate/${repositoryId}`;

  // Create new AbortController for this request
  currentBRDGenerationController = new AbortController();
  currentBRDGenerationRepositoryId = repositoryId;
  const { signal } = currentBRDGenerationController;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      signal, // Pass abort signal to fetch
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
      // Check if aborted before reading
      if (signal.aborted) {
        reader.cancel();
        break;
      }

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
    // Handle abort separately from other errors
    if (error instanceof Error && error.name === 'AbortError') {
      console.log('BRD generation was cancelled');
      if (onCancel) {
        onCancel();
      }
      return;
    }

    if (onError) {
      onError(error instanceof Error ? error : new Error(String(error)));
    } else {
      throw error;
    }
  } finally {
    currentBRDGenerationController = null;
    currentBRDGenerationRepositoryId = null;
  }
}

// Cancel current BRD generation
export async function cancelBRDGeneration(): Promise<boolean> {
  if (currentBRDGenerationController && currentBRDGenerationRepositoryId) {
    // First, notify the backend to cancel
    try {
      await fetch(`${BACKEND_API_URL}/api/v1/brd/generate/${currentBRDGenerationRepositoryId}/cancel`, {
        method: 'POST',
      });
    } catch (error) {
      console.warn('Failed to notify backend of cancellation:', error);
    }

    // Then abort the client-side fetch
    currentBRDGenerationController.abort();
    currentBRDGenerationController = null;
    currentBRDGenerationRepositoryId = null;
    return true;
  }
  return false;
}

// Check if BRD generation can be cancelled
export function canCancelBRDGeneration(): boolean {
  return currentBRDGenerationController !== null;
}

// Generate Epics from BRD (legacy non-streaming)
export async function generateEpics(request: GenerateEpicsRequestLegacy): Promise<GenerateEpicsResponseLegacy> {
  const response = await backendApi.post<GenerateEpicsResponseLegacy>('/epics/generate', request);
  return response.data;
}

// =============================================================================
// Agentic Readiness API
// =============================================================================

export interface AgenticReadinessResponse {
  success: boolean;
  repository_id: string;
  repository_name: string;
  generated_at: string;
  overall_grade: 'A' | 'B' | 'C' | 'D' | 'F';
  overall_score: number;
  is_agentic_ready: boolean;
  testing: {
    overall_grade: string;
    overall_score: number;
    coverage: { percentage: number; grade: string };
    untested_critical_functions: Array<{
      entity_id: string;
      name: string;
      file_path: string;
      reason: string;
      stereotype?: string;
    }>;
    test_quality: {
      has_unit_tests: boolean;
      has_integration_tests: boolean;
      has_e2e_tests: boolean;
      frameworks: string[];
    };
    recommendations: string[];
  };
  documentation: {
    overall_grade: string;
    overall_score: number;
    coverage: { percentage: number; grade: string };
    public_api_coverage: { percentage: number; grade: string };
    undocumented_public_apis: Array<{
      entity_id: string;
      name: string;
      file_path: string;
      kind: string;
      signature?: string;
    }>;
    quality_distribution: {
      excellent: number;
      good: number;
      partial: number;
      minimal: number;
      none: number;
    };
    recommendations: string[];
  };
  recommendations: Array<{
    priority: 'high' | 'medium' | 'low';
    category: 'testing' | 'documentation';
    title: string;
    description: string;
    affected_count: number;
    estimated_effort?: string;
  }>;
  enrichment_actions: Array<{
    id: string;
    name: string;
    description: string;
    affected_entities: number;
    category: string;
    is_automated: boolean;
  }>;
  summary: {
    total_entities: number;
    tested_entities: number;
    documented_entities: number;
    critical_gaps: number;
  };
}

// Get Agentic Readiness Report
export async function getReadinessReport(repositoryId: string): Promise<AgenticReadinessResponse> {
  const response = await backendApi.get<AgenticReadinessResponse>(`/repositories/${repositoryId}/readiness`);
  return response.data;
}

// =============================================================================
// Enrichment API
// =============================================================================

export interface EnrichmentRequest {
  entity_ids: string[] | 'all-undocumented' | 'all-untested';
  style?: string;
  framework?: string;
  test_types?: string[];
  include_examples?: boolean;
  include_parameters?: boolean;
  include_returns?: boolean;
  include_throws?: boolean;
  include_mocks?: boolean;
  include_edge_cases?: boolean;
  max_entities?: number;
}

export interface EnrichmentResponse {
  success: boolean;
  entities_processed: number;
  entities_enriched: number;
  entities_skipped: number;
  generated_content: Array<{
    entity_id: string;
    entity_name: string;
    file_path: string;
    content: string;
    insert_position: { line: number; column: number };
    content_type: string;
    is_new_file: boolean;
  }>;
  errors: Array<{ entity_id: string; error: string }>;
  enrichment_type: string;
}

// Enrich Documentation
export async function enrichDocumentation(
  repositoryId: string,
  request: EnrichmentRequest
): Promise<EnrichmentResponse> {
  const response = await backendApi.post<EnrichmentResponse>(
    `/repositories/${repositoryId}/enrich/documentation`,
    request
  );
  return response.data;
}

// Enrich Tests
export async function enrichTests(
  repositoryId: string,
  request: EnrichmentRequest
): Promise<EnrichmentResponse> {
  const response = await backendApi.post<EnrichmentResponse>(
    `/repositories/${repositoryId}/enrich/tests`,
    request
  );
  return response.data;
}

// =============================================================================
// Codebase Statistics API
// =============================================================================

export interface LanguageBreakdown {
  language: string;
  file_count: number;
  lines_of_code: number;
  percentage: number;
}

export interface CodebaseStatistics {
  // Basic counts
  total_files: number;
  total_lines_of_code: number;

  // Code structure counts
  total_classes: number;
  total_interfaces: number;
  total_functions: number;
  total_components: number;

  // API and endpoints
  total_api_endpoints: number;
  rest_endpoints: number;
  graphql_operations: number;

  // Testing
  total_test_files: number;
  total_test_cases: number;

  // Dependencies
  total_dependencies: number;

  // Database/Models
  total_database_models: number;

  // Complexity metrics
  avg_cyclomatic_complexity?: number;
  max_cyclomatic_complexity?: number;
  avg_file_size?: number;

  // Language breakdown
  languages: LanguageBreakdown[];
  primary_language?: string;

  // Architecture breakdown
  services_count: number;
  controllers_count: number;
  repositories_count: number;

  // UI specific
  ui_routes: number;
  ui_components: number;

  // Config and infrastructure
  config_files: number;

  // Code quality indicators
  documented_entities: number;
  documentation_coverage: number;
}

export interface CodebaseStatisticsResponse {
  success: boolean;
  repository_id: string;
  repository_name: string;
  generated_at: string;
  statistics: CodebaseStatistics;
  summary: {
    files: number;
    loc: number;
    classes: number;
    functions: number;
    apis: number;
    components: number;
    tests: number;
    languages: number;
    primary_language?: string;
  };
}

// Get Codebase Statistics
export async function getCodebaseStatistics(repositoryId: string): Promise<CodebaseStatisticsResponse> {
  const response = await backendApi.get<CodebaseStatisticsResponse>(
    `/repositories/${repositoryId}/statistics`
  );
  return response.data;
}

// =============================================================================
// Business Features Discovery API
// =============================================================================

export type FeatureCategory =
  | 'authentication'
  | 'user_management'
  | 'data_management'
  | 'workflow'
  | 'reporting'
  | 'integration'
  | 'payment'
  | 'notification'
  | 'search'
  | 'admin'
  | 'configuration'
  | 'other';

export type FeatureComplexity = 'low' | 'medium' | 'high' | 'very_high';

export interface CodeFootprint {
  controllers: string[];
  services: string[];
  repositories: string[];
  models: string[];
  views: string[];
  config_files: string[];
  test_files: string[];
  total_files: number;
  total_lines: number;
}

export interface FeatureEndpoint {
  path: string;
  method: string;
  controller: string;
  description?: string;
}

export interface BusinessFeature {
  id: string;
  name: string;
  description: string;
  category: FeatureCategory;
  complexity: FeatureComplexity;
  complexity_score: number;
  discovery_source: 'webflow' | 'controller' | 'service_cluster' | 'screen';
  entry_points: string[];
  file_path?: string;
  feature_group?: string;  // Inferred group name for related features
  code_footprint: CodeFootprint;
  endpoints: FeatureEndpoint[];
  depends_on: string[];
  depended_by: string[];
  has_tests: boolean;
  test_coverage_estimate?: number;
  brd_generated: boolean;
  brd_id?: string;
}

export interface FeaturesSummary {
  total_features: number;
  by_category: Record<string, number>;
  by_complexity: Record<string, number>;
  by_discovery_source: Record<string, number>;
  features_with_tests: number;
  features_with_brd: number;
  avg_complexity_score: number;
}

export interface FeatureGroup {
  name: string;
  features: BusinessFeature[];
  feature_count: number;
}

export interface DiscoveredFeaturesResponse {
  success: boolean;
  repository_id: string;
  repository_name: string;
  generated_at: string;
  features: BusinessFeature[];
  feature_groups: FeatureGroup[];
  summary: FeaturesSummary;
  discovery_method: string;
  discovery_duration_ms?: number;
}

// Get Discovered Business Features
export async function getDiscoveredFeatures(repositoryId: string): Promise<DiscoveredFeaturesResponse> {
  const response = await backendApi.get<DiscoveredFeaturesResponse>(
    `/repositories/${repositoryId}/features`
  );
  return response.data;
}

// =============================================================================
// Repository Detail API
// =============================================================================

export interface RepositoryDetail extends RepositorySummary {
  local_path?: string;
  last_commit_sha?: string;
  file_count?: number;
  total_loc?: number;
  wiki_generated?: boolean;
}

// Get single repository by ID
export async function getRepository(repositoryId: string): Promise<RepositoryDetail> {
  const response = await backendApi.get<{ success: boolean; data: RepositoryDetail }>(
    `/repositories/${repositoryId}`
  );
  return response.data.data;
}

// =============================================================================
// Module Dependencies
// =============================================================================

import type { ModuleDependenciesResponse } from '../types/api';

export async function getModuleDependencies(repositoryId: string): Promise<ModuleDependenciesResponse> {
  const response = await backendApi.get<ModuleDependenciesResponse>(
    `/repositories/${repositoryId}/modules`
  );
  return response.data;
}

// =============================================================================
// EPIC Generation Types
// =============================================================================

export type EpicStatus = 'draft' | 'review' | 'approved' | 'exported';
export type EpicPriority = 'critical' | 'high' | 'medium' | 'low';
export type EffortSize = 'xs' | 'small' | 'medium' | 'large' | 'xlarge';
export type BacklogItemType = 'user_story' | 'task' | 'spike' | 'bug';

export interface ProjectContext {
  tech_stack: string[];
  terminology: Record<string, string>;
  conventions: string[];
  estimation_method: 'story_points' | 't_shirt' | 'hours';
  sprint_length_days: number;
  default_priority: EpicPriority;
}

export interface Epic {
  id: string;
  title: string;
  description: string;
  brd_id: string;
  brd_section_refs: string[];
  business_value: string;
  objectives: string[];
  acceptance_criteria: string[];
  status: EpicStatus;
  estimated_story_count?: number;
  depends_on: string[];
  blocks: string[];
  affected_components: string[];
  technical_notes?: string;
  refinement_count: number;
  last_feedback?: string;
  created_at: string;
  updated_at?: string;
}

export interface BacklogItem {
  id: string;
  epic_id: string;
  title: string;
  brd_section_refs: string[];
  item_type: BacklogItemType;
  description: string;
  as_a?: string;
  i_want?: string;
  so_that?: string;
  acceptance_criteria: string[];
  technical_notes?: string;
  files_to_modify: string[];
  files_to_create: string[];
  priority: EpicPriority;
  story_points?: number;
  effort_size?: EffortSize;
  depends_on: string[];
  blocks: string[];
  // New comprehensive story fields
  pre_conditions?: string[];
  post_conditions?: string[];
  testing_approach?: string;
  edge_cases?: string[];
  implementation_notes?: string;
  ui_ux_notes?: string;
  // Status and tracking
  status: string;
  refinement_count: number;
  last_feedback?: string;
  created_at: string;
  updated_at?: string;
}

export interface CoverageMatrixEntry {
  brd_section: string;
  brd_section_title?: string;
  epic_ids: string[];
  backlog_ids: string[];
  is_covered: boolean;
}

// =============================================================================
// EPIC Template Configuration Types
// =============================================================================

export interface EpicFieldConfig {
  field_name: string;
  enabled: boolean;
  target_words: number;
  guidelines?: string;
}

export interface EpicTemplateConfig {
  epic_template?: string;
  field_configs?: EpicFieldConfig[];
  default_description_words?: number;
  default_business_value_words?: number;
  default_objectives_count?: number;
  default_acceptance_criteria_count?: number;
  include_technical_components?: boolean;
  include_dependencies?: boolean;
  include_effort_estimates?: boolean;
}

// =============================================================================
// Backlog Template Configuration Types
// =============================================================================

export interface BacklogFieldConfig {
  field_name: string;
  enabled: boolean;
  target_words: number;
  guidelines?: string;
}

export interface BacklogTemplateConfig {
  backlog_template?: string;
  field_configs?: BacklogFieldConfig[];
  default_description_words: number;
  default_acceptance_criteria_count: number;
  default_technical_notes_words: number;
  require_user_story_format: boolean;
  include_technical_notes: boolean;
  include_file_references: boolean;
  include_story_points: boolean;
}

// =============================================================================
// Pre-Analysis Types (Phase 1: Intelligent Count Determination)
// =============================================================================

// Analysis focus types for BRD analysis
export type BRDAnalysisFocus =
  | 'functional_areas'
  | 'user_journeys'
  | 'technical_components'
  | 'business_capabilities'
  | 'integrations'
  | 'user_personas';

// Analysis focus types for Backlog analysis
export type BacklogAnalysisFocus =
  | 'user_stories'
  | 'technical_tasks'
  | 'testing'
  | 'integration'
  | 'ui_ux'
  | 'data_migration';

export interface SuggestedEpicBreakdown {
  id: string;
  name: string;
  scope: string;
  brd_sections: string[];
  estimated_stories: number;
  complexity: 'low' | 'medium' | 'high';
  reasoning: string;
  user_modified?: boolean;
}

export interface BRDAnalysisResult {
  success: boolean;
  brd_id: string;

  // Structural analysis
  functional_areas: string[];
  user_journeys: string[];
  user_personas: string[];
  integration_points: string[];

  // Complexity assessment
  complexity_level: 'low' | 'medium' | 'high' | 'very_high';
  complexity_factors: string[];

  // Size metrics
  word_count: number;
  section_count: number;
  requirement_count: number;

  // EPIC count recommendation
  recommended_epic_count: number;
  min_epic_count: number;
  max_epic_count: number;

  // Detailed breakdown
  suggested_epics: SuggestedEpicBreakdown[];

  // Reasoning
  recommendation_reasoning: string;

  // Warnings/notes
  warnings: string[];
}

export interface AnalyzeBRDRequest {
  brd_id: string;
  brd_markdown: string;
  brd_title?: string;

  // Analysis focus - what perspective to analyze from
  analysis_focus?: BRDAnalysisFocus;

  // User feedback for re-analysis
  user_feedback?: string;

  // Previous analysis to refine (for re-analysis)
  previous_epics?: SuggestedEpicBreakdown[];

  epic_size_preference?: 'small' | 'medium' | 'large';
  team_velocity?: number;
  target_sprint_count?: number;
}

export interface SuggestedBacklogBreakdown {
  id: string;
  title: string;
  item_type: 'user_story' | 'task' | 'spike';
  scope: string;
  complexity: 'low' | 'medium' | 'high';
  estimated_points: number;
  user_modified?: boolean;
}

export interface EpicAnalysisResult {
  epic_id: string;
  epic_title: string;

  // Scope analysis
  features_identified: string[];
  user_interactions: string[];
  technical_components: string[];

  // Complexity
  complexity_level: 'low' | 'medium' | 'high';

  // Backlog recommendation
  recommended_item_count: number;
  min_item_count: number;
  max_item_count: number;

  // Item type breakdown
  suggested_user_stories: number;
  suggested_tasks: number;
  suggested_spikes: number;

  // Detailed breakdown
  suggested_items: SuggestedBacklogBreakdown[];

  // Total points estimate
  estimated_total_points: number;

  reasoning: string;
}

export interface AnalyzeEpicsForBacklogsRequest {
  brd_id: string;
  brd_markdown: string;
  epics: Epic[];

  // Analysis focus - what perspective to analyze from
  analysis_focus?: BacklogAnalysisFocus;

  // User feedback for re-analysis
  user_feedback?: string;

  // Previous analysis to refine (for re-analysis)
  previous_items?: Record<string, SuggestedBacklogBreakdown[]>;

  granularity_preference?: 'fine' | 'medium' | 'coarse';
  include_technical_tasks?: boolean;
  include_spikes?: boolean;
}

export interface AnalyzeEpicsForBacklogsResponse {
  success: boolean;
  brd_id: string;

  // Per-EPIC analysis
  epic_analyses: EpicAnalysisResult[];

  // Totals
  total_recommended_items: number;
  total_estimated_points: number;

  // Summary by type
  total_user_stories: number;
  total_tasks: number;
  total_spikes: number;

  // Overall recommendation
  recommendation_summary: string;
}

// =============================================================================
// EPIC Generation Request/Response Types
// =============================================================================

export interface GenerateEpicsRequest {
  brd_id: string;
  brd_markdown: string;
  brd_title?: string;
  focus_sections?: string[];
  mode?: 'draft' | 'verified';
  max_epics?: number;
  include_dependencies?: boolean;
  include_estimates?: boolean;
  project_context?: ProjectContext;
  model?: string;

  // Detail level for content generation
  detail_level?: 'concise' | 'standard' | 'detailed';

  // Template configuration
  epic_template?: string;
  template_config?: EpicTemplateConfig;

  // Pre-analysis results (Phase 1)
  brd_analysis?: BRDAnalysisResult;

  // Dynamic EPIC count control
  epic_count_mode?: 'auto' | 'guided' | 'manual';
  epic_size_preference?: 'small' | 'medium' | 'large';
  use_suggested_breakdown?: boolean;

  // User-defined EPICs (edited/added/removed by user)
  user_defined_epics?: SuggestedEpicBreakdown[];
}

export interface RefineEpicRequest {
  epic_id: string;
  current_epic: Epic;
  user_feedback: string;
  brd_sections_content: string[];
  project_context?: ProjectContext;
}

export interface RefineAllEpicsRequest {
  epics: Epic[];
  global_feedback: string;
  brd_markdown: string;
  project_context?: ProjectContext;
}

export interface EpicVerificationResult {
  epic_id: string;
  epic_title: string;
  overall_confidence: number;
  is_approved: boolean;
  verification_status: 'verified' | 'partially_verified' | 'unverified' | 'contradicted';
  hallucination_risk: 'none' | 'low' | 'medium' | 'high';
  issues: string[];
  suggestions: string[];
  total_claims: number;
  verified_claims: number;
  unverified_claims: number;
}

export interface GenerateEpicsStreamResponse {
  success: boolean;
  brd_id: string;
  brd_title?: string;
  epics: Epic[];
  coverage_matrix: CoverageMatrixEntry[];
  uncovered_sections: string[];
  total_epics: number;
  recommended_order: string[];
  mode: string;
  model_used?: string;
  generated_at: string;

  // Verification results (populated in verified mode)
  verification_results?: EpicVerificationResult[];
  overall_confidence?: number;
  is_verified?: boolean;
  verification_status?: string;
  draft_warning?: string;
}

// =============================================================================
// Backlog Generation Request/Response Types
// =============================================================================

export interface GenerateBacklogsRequest {
  brd_id: string;
  brd_markdown: string;
  epics: Epic[];
  epic_ids?: string[];
  mode?: 'draft' | 'verified';
  items_per_epic?: number;
  include_technical_tasks?: boolean;
  include_spikes?: boolean;
  project_context?: ProjectContext;
  model?: string;

  // Consistency controls for reproducible outputs
  temperature?: number;
  seed?: number;

  // Template configuration
  backlog_template?: string;
  template_config?: BacklogTemplateConfig;
  default_description_words?: number;
  default_acceptance_criteria_count?: number;

  // Pre-analysis results (Phase 1)
  epic_analysis?: AnalyzeEpicsForBacklogsResponse;

  // Dynamic item count control
  item_count_mode?: 'auto' | 'guided' | 'manual';
  granularity_preference?: 'fine' | 'medium' | 'coarse';
  use_suggested_breakdown?: boolean;

  // User-defined items per EPIC (edited/added/removed by user)
  user_defined_items?: Record<string, SuggestedBacklogBreakdown[]>;
}

export interface RefineBacklogItemRequest {
  item_id: string;
  current_item: BacklogItem;
  user_feedback: string;
  epic: Epic;
  brd_sections_content: string[];
  project_context?: ProjectContext;
}

export interface BacklogVerificationResult {
  item_id: string;
  item_title: string;
  epic_id: string;
  overall_confidence: number;
  is_approved: boolean;
  verification_status: 'verified' | 'partially_verified' | 'unverified' | 'contradicted';
  hallucination_risk: 'none' | 'low' | 'medium' | 'high';
  issues: string[];
  suggestions: string[];
  total_claims: number;
  verified_claims: number;
}

export interface GenerateBacklogsResponse {
  success: boolean;
  brd_id: string;
  items: BacklogItem[];
  items_by_epic: Record<string, string[]>;
  coverage_matrix: CoverageMatrixEntry[];
  total_items: number;
  total_story_points: number;
  by_type: Record<string, number>;
  by_priority: Record<string, number>;
  recommended_order: string[];
  mode: string;
  model_used?: string;
  generated_at: string;

  // Verification results (populated in verified mode)
  verification_results?: BacklogVerificationResult[];
  overall_confidence?: number;
  is_verified?: boolean;
  verification_status?: string;
  draft_warning?: string;
}

// =============================================================================
// EPIC Stream Event Types
// =============================================================================

export interface EpicStreamEvent {
  type: 'thinking' | 'epic' | 'complete' | 'error';
  content?: string;
  epic?: Epic;
  data?: GenerateEpicsStreamResponse;
  error?: string;
}

export interface BacklogStreamEvent {
  type: 'thinking' | 'item' | 'complete' | 'error';
  content?: string;
  item?: BacklogItem;
  data?: GenerateBacklogsResponse;
  error?: string;
}

// =============================================================================
// Phase 1: Pre-Analysis API Functions
// =============================================================================

/**
 * Analyze BRD for intelligent EPIC count determination
 *
 * This should be called BEFORE generating EPICs to get AI-powered recommendations.
 *
 * @param request - The BRD content and analysis preferences
 * @returns Analysis result with recommended EPIC count and suggested breakdown
 */
export async function analyzeBRDForEpics(
  request: AnalyzeBRDRequest
): Promise<BRDAnalysisResult> {
  const response = await backendApi.post<BRDAnalysisResult>(
    '/epics/analyze-brd',
    request
  );
  return response.data;
}

/**
 * Analyze EPICs for intelligent backlog count determination
 *
 * This should be called BEFORE generating backlogs to get AI-powered recommendations.
 *
 * @param request - The EPICs and analysis preferences
 * @returns Analysis result with recommended item counts per EPIC
 */
export async function analyzeEpicsForBacklogs(
  request: AnalyzeEpicsForBacklogsRequest
): Promise<AnalyzeEpicsForBacklogsResponse> {
  const response = await backendApi.post<AnalyzeEpicsForBacklogsResponse>(
    '/backlogs/analyze-epics',
    request
  );
  return response.data;
}

// =============================================================================
// EPIC Generation API Functions
// =============================================================================

/**
 * Generate EPICs from BRD with streaming progress
 */
export async function generateEpicsStream(
  request: GenerateEpicsRequest,
  onEvent: (event: EpicStreamEvent) => void,
  onError?: (error: Error) => void
): Promise<void> {
  const url = `${BACKEND_API_URL}/api/v1/epics/generate`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
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
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            onEvent(data as EpicStreamEvent);
          } catch (e) {
            console.error('Failed to parse SSE data:', e);
          }
        }
      }
    }
  } catch (error) {
    console.error('EPIC generation stream error:', error);
    if (onError) {
      onError(error as Error);
    }
  }
}

/**
 * Refine a single EPIC based on user feedback
 */
export async function refineEpic(
  epicId: string,
  request: RefineEpicRequest
): Promise<Epic> {
  const response = await backendApi.post<Epic>(
    `/epics/${epicId}/refine`,
    request
  );
  return response.data;
}

/**
 * Apply global feedback to all EPICs
 */
export async function refineAllEpics(
  request: RefineAllEpicsRequest
): Promise<RefineEpicsResponse> {
  const response = await backendApi.post<RefineEpicsResponse>(
    '/epics/refine-all',
    request
  );
  return response.data;
}

// =============================================================================
// EPIC and Backlog Template Parsing API Functions
// =============================================================================

export interface ParseEpicTemplateResponse {
  success: boolean;
  fields: EpicFieldConfig[];
  guidelines: string[];
  template_name?: string;
}

export interface ParseBacklogTemplateResponse {
  success: boolean;
  fields: BacklogFieldConfig[];
  item_types: string[];
  guidelines: string[];
  template_name?: string;
}

/**
 * Parse EPIC template to extract field configuration
 */
export async function parseEpicTemplateFields(
  templateContent: string
): Promise<ParseEpicTemplateResponse> {
  const response = await backendApi.post<ParseEpicTemplateResponse>(
    '/epics/template/parse-fields',
    { template_content: templateContent }
  );
  return response.data;
}

/**
 * Parse Backlog template to extract field configuration
 */
export async function parseBacklogTemplateFields(
  templateContent: string
): Promise<ParseBacklogTemplateResponse> {
  const response = await backendApi.post<ParseBacklogTemplateResponse>(
    '/backlogs/template/parse-fields',
    { template_content: templateContent }
  );
  return response.data;
}

/**
 * Response from getting default EPIC template
 */
export interface DefaultEpicTemplateResponse {
  success: boolean;
  template: string;
  fields: EpicFieldConfig[];
  guidelines: string[];
}

/**
 * Response from getting default Backlog template
 */
export interface DefaultBacklogTemplateResponse {
  success: boolean;
  template: string;
  fields: BacklogFieldConfig[];
  item_types: string[];
  guidelines: string[];
}

/**
 * Get the default EPIC template
 */
export async function getDefaultEpicTemplate(): Promise<DefaultEpicTemplateResponse> {
  const response = await backendApi.get<DefaultEpicTemplateResponse>('/epics/template/default');
  return response.data;
}

/**
 * Get the default Backlog template
 */
export async function getDefaultBacklogTemplate(): Promise<DefaultBacklogTemplateResponse> {
  const response = await backendApi.get<DefaultBacklogTemplateResponse>('/backlogs/template/default');
  return response.data;
}

// =============================================================================
// Backlog Generation API Functions
// =============================================================================

/**
 * Generate backlogs from EPICs with streaming progress
 */
export async function generateBacklogsStream(
  request: GenerateBacklogsRequest,
  onEvent: (event: BacklogStreamEvent) => void,
  onError?: (error: Error) => void
): Promise<void> {
  const url = `${BACKEND_API_URL}/api/v1/backlogs/generate`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
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
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            onEvent(data as BacklogStreamEvent);
          } catch (e) {
            console.error('Failed to parse SSE data:', e);
          }
        }
      }
    }
  } catch (error) {
    console.error('Backlog generation stream error:', error);
    if (onError) {
      onError(error as Error);
    }
  }
}

/**
 * Refine a single backlog item based on user feedback
 */
export async function refineBacklogItem(
  itemId: string,
  request: RefineBacklogItemRequest
): Promise<BacklogItem> {
  const response = await backendApi.post<BacklogItem>(
    `/backlogs/${itemId}/refine`,
    request
  );
  return response.data;
}

/**
 * Regenerate all backlogs for a specific EPIC
 */
export async function regenerateBacklogsForEpic(
  epicId: string,
  epic: Epic,
  brdMarkdown: string,
  feedback?: string,
  itemsPerEpic: number = 5,
  projectContext?: ProjectContext
): Promise<BacklogItem[]> {
  const response = await backendApi.post<BacklogItem[]>(
    `/backlogs/regenerate/${epicId}`,
    {
      epic,
      brd_markdown: brdMarkdown,
      feedback,
      items_per_epic: itemsPerEpic,
      project_context: projectContext,
    }
  );
  return response.data;
}

// =============================================================================
// BRD Refinement Types
// =============================================================================

export interface BRDSection {
  name: string;
  content: string;
  section_order?: number;
  refinement_count: number;
  last_feedback?: string;
  last_refined_at?: string;
}

export interface RefinementEntry {
  version: number;
  timestamp: string;
  feedback_type: 'section' | 'global';
  feedback_target?: string;
  user_feedback: string;
  changes_summary: string;
  sections_affected: string[];
  section_diffs?: Record<string, { before: string; after: string }>;
}

export interface RefinedBRD {
  id: string;
  title: string;
  version: string;
  repository_id: string;
  sections: BRDSection[];
  markdown: string;
  mode: 'draft' | 'verified';
  confidence_score?: number;
  verification_report?: VerificationReport;
  refinement_count: number;
  last_feedback?: string;
  refinement_history: RefinementEntry[];
  session_id?: string;
  status: 'draft' | 'review' | 'approved' | 'exported';
  created_at: string;
  updated_at?: string;
}

export interface RefineBRDSectionRequest {
  brd_id: string;
  section_name: string;
  current_content: string;
  user_feedback: string;
  full_brd_context: string;
  repository_id: string;
  session_id?: string;
  project_context?: Record<string, unknown>;
}

export interface RefineEntireBRDRequest {
  brd_id: string;
  current_brd: RefinedBRD;
  global_feedback: string;
  repository_id: string;
  session_id?: string;
  target_sections?: string[];
  project_context?: Record<string, unknown>;
}

export interface RefineBRDSectionResponse {
  success: boolean;
  brd_id: string;
  section_name: string;
  refined_section: BRDSection;
  changes_summary: string;
  before_content: string;
  after_content: string;
  updated_brd?: RefinedBRD;
}

export interface RefineEntireBRDResponse {
  success: boolean;
  brd_id: string;
  refined_brd: RefinedBRD;
  changes_summary: string;
  sections_affected: string[];
  section_diffs: Record<string, { before: string; after: string }>;
}

// =============================================================================
// Audit History Types
// =============================================================================

export interface ArtifactHistoryEntry {
  id: string;
  artifact_type: 'brd' | 'epic' | 'backlog';
  artifact_id: string;
  version: number;
  action: 'created' | 'refined';
  user_feedback?: string;
  feedback_scope?: 'global' | 'section' | 'item';
  feedback_target?: string;
  changes_summary?: string;
  sections_changed: string[];
  model_used?: string;
  generation_mode?: 'draft' | 'verified';
  confidence_score?: number;
  created_at: string;
  created_by?: string;
}

export interface ArtifactHistoryResponse {
  success: boolean;
  artifact_type: string;
  artifact_id: string;
  total_versions: number;
  current_version: number;
  history: ArtifactHistoryEntry[];
}

export interface SessionHistoryResponse {
  success: boolean;
  session_id: string;
  repository_id: string;
  feature_description: string;
  status: 'active' | 'completed' | 'archived';
  brd_id: string;
  epic_ids: string[];
  backlog_ids: string[];
  history: ArtifactHistoryEntry[];
  total_refinements: number;
  brd_refinements: number;
  epic_refinements: number;
  backlog_refinements: number;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

export interface VersionDiffResponse {
  success: boolean;
  artifact_type: string;
  artifact_id: string;
  version1: number;
  version2: number;
  section_diffs: Record<string, { before: string; after: string }>;
  content_before?: string;
  content_after?: string;
  sections_added: string[];
  sections_removed: string[];
  sections_modified: string[];
  feedback_applied: string[];
}

// =============================================================================
// BRD Refinement API Functions
// =============================================================================

/**
 * Refine a specific BRD section based on user feedback
 */
export async function refineBRDSection(
  brdId: string,
  sectionName: string,
  request: RefineBRDSectionRequest
): Promise<RefineBRDSectionResponse> {
  const response = await backendApi.post<RefineBRDSectionResponse>(
    `/brd/${brdId}/sections/${encodeURIComponent(sectionName)}/refine`,
    request
  );
  return response.data;
}

/**
 * Apply global feedback to refine entire BRD
 */
export async function refineEntireBRD(
  brdId: string,
  request: RefineEntireBRDRequest
): Promise<RefineEntireBRDResponse> {
  const response = await backendApi.post<RefineEntireBRDResponse>(
    `/brd/${brdId}/refine`,
    request
  );
  return response.data;
}

// =============================================================================
// Audit History API Functions
// =============================================================================

/**
 * Get complete refinement history for an artifact
 */
export async function getArtifactHistory(
  artifactType: 'brd' | 'epic' | 'backlog',
  artifactId: string
): Promise<ArtifactHistoryResponse> {
  const response = await backendApi.get<ArtifactHistoryResponse>(
    `/audit/${artifactType}/${artifactId}/history`
  );
  return response.data;
}

/**
 * Get full audit trail for a generation session
 */
export async function getSessionHistory(
  sessionId: string
): Promise<SessionHistoryResponse> {
  const response = await backendApi.get<SessionHistoryResponse>(
    `/audit/session/${sessionId}`
  );
  return response.data;
}

/**
 * Get diff between two versions of an artifact
 */
export async function getVersionDiff(
  artifactType: 'brd' | 'epic' | 'backlog',
  artifactId: string,
  version1: number,
  version2: number
): Promise<VersionDiffResponse> {
  const response = await backendApi.get<VersionDiffResponse>(
    `/audit/${artifactType}/${artifactId}/diff/${version1}/${version2}`
  );
  return response.data;
}

/**
 * Create a new generation session
 */
export async function createAuditSession(
  repositoryId: string,
  brdId: string,
  featureDescription: string
): Promise<{ success: boolean; session_id: string }> {
  const response = await backendApi.post<{ success: boolean; session_id: string }>(
    '/audit/sessions',
    {
      repository_id: repositoryId,
      brd_id: brdId,
      feature_description: featureDescription,
    }
  );
  return response.data;
}

/**
 * Get current retention period configuration
 */
export async function getRetentionConfig(): Promise<{ retention_days: number }> {
  const response = await backendApi.get<{ retention_days: number }>(
    '/audit/config/retention'
  );
  return response.data;
}

/**
 * Set retention period configuration
 */
export async function setRetentionConfig(days: number): Promise<{ retention_days: number }> {
  const response = await backendApi.put<{ retention_days: number }>(
    '/audit/config/retention',
    { days }
  );
  return response.data;
}

// =============================================================================
// BRD Library Types
// =============================================================================

export type DocumentStatusType = 'draft' | 'in_progress' | 'completed' | 'approved' | 'archived';

export interface StoredBacklog {
  id: string;
  backlog_number: string;
  epic_id: string;
  epic_title?: string;
  title: string;
  description: string;
  item_type: string;
  as_a?: string;
  i_want?: string;
  so_that?: string;
  acceptance_criteria: string[];
  technical_notes?: string;
  files_to_modify: string[];
  files_to_create: string[];
  priority: string;
  story_points?: number;
  status: string;
  refinement_count: number;
  created_at: string;
  updated_at: string;
}

export interface StoredEpic {
  id: string;
  epic_number: string;
  brd_id: string;
  brd_title?: string;
  repository_id?: string;
  repository_name?: string;
  title: string;
  description: string;
  business_value?: string;
  objectives: string[];
  acceptance_criteria: string[];
  affected_components: string[];
  depends_on: string[];
  status: string;
  refinement_count: number;
  display_order: number;
  backlog_count: number;
  backlogs: StoredBacklog[];
  created_at: string;
  updated_at: string;
}

export interface StoredBRD {
  id: string;
  brd_number: string;
  title: string;
  feature_description: string;
  markdown_content: string;
  sections?: Array<{ name: string; content: string }>;
  repository_id: string;
  repository_name?: string;
  mode: string;
  confidence_score?: number;
  verification_report?: Record<string, any>;
  status: string;
  version: number;
  refinement_count: number;
  epic_count: number;
  backlog_count: number;
  epics: StoredEpic[];
  created_at: string;
  updated_at: string;
}

export interface BRDListResponse {
  success: boolean;
  data: StoredBRD[];
  total: number;
  limit: number;
  offset: number;
}

export interface BRDDetailResponse {
  success: boolean;
  data: StoredBRD;
}

export interface EpicDetailResponse {
  success: boolean;
  data: StoredEpic;
}

export interface EpicsListResponse {
  success: boolean;
  data: StoredEpic[];
  total: number;
}

export interface BacklogsListResponse {
  success: boolean;
  data: StoredBacklog[];
  total: number;
}

export interface SaveBRDRequest {
  repository_id: string;
  title: string;
  feature_description: string;
  markdown_content: string;
  sections?: Array<{ name: string; content: string }>;
  mode?: string;
  confidence_score?: number;
  verification_report?: Record<string, any>;
}

export interface UpdateBRDRequest {
  title?: string;
  markdown_content?: string;
  sections?: Array<{ name: string; content: string }>;
  status?: string;
  confidence_score?: number;
  verification_report?: Record<string, any>;
}

// =============================================================================
// BRD Library API Functions
// =============================================================================

/**
 * List all BRDs with optional filters
 */
export async function listBRDs(params?: {
  repository_id?: string;
  status?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<BRDListResponse> {
  const response = await backendApi.get<BRDListResponse>('/brds', { params });
  return response.data;
}

/**
 * Get BRD detail with EPICs and Backlogs
 */
export async function getBRDDetail(brdId: string): Promise<StoredBRD> {
  const response = await backendApi.get<BRDDetailResponse>(`/brds/${brdId}`);
  return response.data.data;
}

/**
 * Save a newly generated BRD
 */
export async function saveBRD(request: SaveBRDRequest): Promise<StoredBRD> {
  const response = await backendApi.post<BRDDetailResponse>('/brds', request);
  return response.data.data;
}

/**
 * Update an existing BRD
 */
export async function updateBRD(brdId: string, request: UpdateBRDRequest): Promise<StoredBRD> {
  const response = await backendApi.put<BRDDetailResponse>(`/brds/${brdId}`, request);
  return response.data.data;
}

/**
 * Update BRD status (approve, archive, etc.)
 */
export async function updateBRDStatus(brdId: string, status: DocumentStatusType): Promise<StoredBRD> {
  const response = await backendApi.patch<BRDDetailResponse>(`/brds/${brdId}/status`, { status });
  return response.data.data;
}

/**
 * Delete a BRD and all its EPICs/Backlogs
 */
export async function deleteBRD(brdId: string): Promise<void> {
  await backendApi.delete(`/brds/${brdId}`);
}

/**
 * Download BRD as Markdown or HTML
 */
export async function downloadBRD(
  brdId: string,
  format: 'md' | 'html' = 'md',
  includeChildren: boolean = false
): Promise<Blob> {
  const response = await backendApi.get(`/brds/${brdId}/download/${format}`, {
    params: { include_children: includeChildren },
    responseType: 'blob',
  });
  return response.data;
}

/**
 * Get EPICs for a BRD
 */
export async function getEpicsForBRD(brdId: string): Promise<StoredEpic[]> {
  const response = await backendApi.get<EpicsListResponse>(`/brds/${brdId}/epics`);
  return response.data.data;
}

/**
 * Save generated EPICs for a BRD
 */
export async function saveEpicsForBRD(brdId: string, epics: Record<string, any>[]): Promise<StoredEpic[]> {
  const response = await backendApi.post<EpicsListResponse>(`/brds/${brdId}/epics`, { epics });
  return response.data.data;
}

/**
 * Get EPIC detail with backlogs
 */
export async function getEpicDetail(epicId: string): Promise<StoredEpic> {
  const response = await backendApi.get<EpicDetailResponse>(`/epics/${epicId}`);
  return response.data.data;
}

/**
 * Get all EPICs across all BRDs
 */
export interface GetAllEpicsParams {
  status?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export async function getAllEpics(params: GetAllEpicsParams = {}): Promise<{ data: StoredEpic[]; total: number }> {
  const response = await backendApi.get<EpicsListResponse>('/epics', { params });
  return { data: response.data.data, total: response.data.total };
}

/**
 * Update an EPIC
 */
export interface UpdateEpicRequest {
  title?: string;
  description?: string;
  business_value?: string;
  objectives?: string[];
  acceptance_criteria?: string[];
  affected_components?: string[];
  depends_on?: string[];
  status?: string;
}

export async function updateEpic(epicId: string, data: UpdateEpicRequest): Promise<StoredEpic> {
  const response = await backendApi.put<EpicDetailResponse>(`/epics/${epicId}`, data);
  return response.data.data;
}

/**
 * Delete an EPIC
 */
export async function deleteEpic(epicId: string): Promise<{ success: boolean; message: string }> {
  const response = await backendApi.delete<{ success: boolean; message: string }>(`/epics/${epicId}`);
  return response.data;
}

/**
 * Get backlogs for an EPIC
 */
export async function getBacklogsForEpic(epicId: string): Promise<StoredBacklog[]> {
  const response = await backendApi.get<BacklogsListResponse>(`/epics/${epicId}/backlogs`);
  return response.data.data;
}

/**
 * Save generated backlogs for an EPIC
 */
export async function saveBacklogsForEpic(epicId: string, items: Record<string, any>[]): Promise<StoredBacklog[]> {
  const response = await backendApi.post<BacklogsListResponse>(`/epics/${epicId}/backlogs`, { items });
  return response.data.data;
}

/**
 * Get all backlogs across all EPICs
 */
export interface GetAllBacklogsParams {
  status?: string;
  item_type?: string;
  priority?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export async function getAllBacklogs(params: GetAllBacklogsParams = {}): Promise<{ data: StoredBacklog[]; total: number }> {
  const response = await backendApi.get<BacklogsListResponse>('/backlogs', { params });
  return { data: response.data.data, total: response.data.total };
}

// =============================================================================
// Wiki API (DeepWiki-style Documentation)
// =============================================================================

export interface WikiStatus {
  status: string;
  total_pages: number;
  stale_pages: number;
  commit_sha: string | null;
  generation_mode: string | null;
  generated_at: string | null;
  message?: string;
}

export interface WikiTreeNode {
  slug: string;
  title: string;
  type: string;
  is_stale: boolean;
  children: WikiTreeNode[];
}

export interface WikiTreeResponse {
  wiki: WikiStatus | null;
  tree: WikiTreeNode[];
}

export interface WikiPage {
  id: string;
  slug: string;
  title: string;
  type: string;
  content: string;
  summary: string | null;
  source_files: string[] | null;
  is_stale: boolean;
  stale_reason: string | null;
  updated_at: string;
  breadcrumbs: { slug: string; title: string }[];
  related: { slug: string; title: string }[];
}

export interface WikiSearchResult {
  slug: string;
  title: string;
  type: string;
  summary: string;
}

export interface WikiSearchResponse {
  query: string;
  results: WikiSearchResult[];
  total: number;
}

// Custom page definition for advanced wiki mode
export interface WikiCustomPage {
  title: string;
  purpose: string;
  notes?: string;
  parent_id?: string;
  is_section?: boolean;
}

export interface WikiGenerationOptions {
  enabled?: boolean;
  depth?: 'quick' | 'basic' | 'standard' | 'comprehensive' | 'custom';
  mode?: 'standard' | 'advanced';
  // Standard mode options
  include_modules?: boolean;
  include_core_systems?: boolean;
  include_features?: boolean;
  include_api_reference?: boolean;
  include_class_pages?: boolean;
  include_data_models?: boolean;
  include_code_structure?: boolean;
  include_integrations?: boolean;
  include_deployment?: boolean;
  include_getting_started?: boolean;
  include_configuration?: boolean;
  // Advanced mode options
  context_notes?: string[];
  custom_pages?: WikiCustomPage[];
}

/**
 * Get wiki status for a repository
 */
export async function getWikiStatus(repositoryId: string): Promise<WikiStatus> {
  const response = await backendApi.get<WikiStatus>(`/wiki/repositories/${repositoryId}/status`);
  return response.data;
}

/**
 * Get wiki navigation tree
 */
export async function getWikiTree(repositoryId: string): Promise<WikiTreeResponse> {
  const response = await backendApi.get<WikiTreeResponse>(`/wiki/repositories/${repositoryId}/tree`);
  return response.data;
}

/**
 * Get a specific wiki page
 */
export async function getWikiPage(repositoryId: string, slug: string): Promise<WikiPage> {
  const response = await backendApi.get<WikiPage>(`/wiki/repositories/${repositoryId}/pages/${slug}`);
  return response.data;
}

/**
 * Search wiki pages
 */
export async function searchWiki(repositoryId: string, query: string, limit: number = 20): Promise<WikiSearchResponse> {
  const response = await backendApi.get<WikiSearchResponse>(`/wiki/repositories/${repositoryId}/search`, {
    params: { q: query, limit }
  });
  return response.data;
}

/**
 * Generate wiki documentation
 */
export async function generateWiki(repositoryId: string, options?: WikiGenerationOptions): Promise<{ success: boolean; message: string }> {
  const response = await backendApi.post(`/wiki/repositories/${repositoryId}/generate`, {
    options: options || { depth: 'basic' }
  });
  return response.data;
}

/**
 * Regenerate a specific wiki page
 */
export async function regenerateWikiPage(repositoryId: string, slug: string): Promise<{ success: boolean; message: string }> {
  const response = await backendApi.post(`/wiki/repositories/${repositoryId}/pages/${slug}/regenerate`);
  return response.data;
}

/**
 * Delete wiki for a repository
 */
export async function deleteWiki(repositoryId: string): Promise<{ success: boolean; message: string }> {
  const response = await backendApi.delete(`/wiki/repositories/${repositoryId}`);
  return response.data;
}

export default codegraphApi;
