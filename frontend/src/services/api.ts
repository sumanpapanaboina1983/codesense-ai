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

  // Multi-agent verification settings (VERIFIED mode only)
  max_iterations?: number;  // default: 3, range: 1-10
  min_confidence?: number;  // default: 0.7, range: 0-1
  show_evidence?: boolean;  // default: false

  // Sufficiency criteria
  sufficiency_criteria?: SufficiencyCriteria;

  // Verification query limits (VERIFIED mode only)
  verification_limits?: VerificationLimits;

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

// Generate BRD with streaming (SSE) - Multi-agent verification always enabled
export async function generateBRDStream(
  repositoryId: string,
  request: GenerateBRDRequest,
  onEvent: (event: StreamEvent) => void,
  onError?: (error: Error) => void
): Promise<void> {
  const url = `${BACKEND_API_URL}/api/v1/brd/generate/${repositoryId}`;

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

export interface DiscoveredFeaturesResponse {
  success: boolean;
  repository_id: string;
  repository_name: string;
  generated_at: string;
  features: BusinessFeature[];
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
}

// Get single repository by ID
export async function getRepository(repositoryId: string): Promise<RepositoryDetail> {
  const response = await backendApi.get<{ success: boolean; data: RepositoryDetail }>(
    `/repositories/${repositoryId}`
  );
  return response.data.data;
}

export default codegraphApi;
