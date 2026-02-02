export interface Repository {
  id: string;
  url: string;
  name: string;
  platform: 'github' | 'gitlab';
  status: 'pending' | 'cloning' | 'cloned' | 'failed';
  analysis_status: 'not_started' | 'in_progress' | 'completed' | 'failed';
  stars?: number;
  forks?: number;
  language?: string;
  description?: string;
  created_at: string;
  updated_at: string;
  last_synced_at?: string;
  auto_analyze_on_sync: boolean;
}

export interface BRDRequest {
  feature_description: string;
  affected_components?: string[];
  template_config?: {
    template_path?: string;
    organization_name?: string;
    document_prefix?: string;
    include_risk_matrix?: boolean;
    include_code_references?: boolean;
    custom_sections?: string[];
    approval_workflow?: string[];
  };
}

export interface BRD {
  id: string;
  title: string;
  content: string;
  feature_description: string;
  functional_requirements: Requirement[];
  technical_requirements: Requirement[];
  dependencies: Dependency[];
  risks: Risk[];
  created_at: string;
}

export interface Requirement {
  id: string;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  acceptance_criteria: string[];
}

export interface Dependency {
  name: string;
  type: string;
  description: string;
}

export interface Risk {
  id: string;
  title: string;
  description: string;
  likelihood: 'high' | 'medium' | 'low';
  impact: 'high' | 'medium' | 'low';
  mitigation: string;
}

export interface Epic {
  id: string;
  title: string;
  description: string;
  priority: number;
  estimated_story_count: number;
  components: string[];
  dependencies: string[];
  implementation_order: number;
}

export interface EpicGenerationRequest {
  brd_content: string;
  brd_id?: string;
}

export interface UserStory {
  id: string;
  epic_id: string;
  title: string;
  user_story: string;
  acceptance_criteria: string[];
  files_to_modify: string[];
  files_to_create: string[];
  technical_notes: string;
  story_points: number;
  blocked_by: string[];
  blocks: string[];
}

export interface BacklogGenerationRequest {
  epics: Epic[];
  brd_content: string;
}

export interface JiraCreateRequest {
  project_key: string;
  epics: Epic[];
  stories: UserStory[];
}

export interface JiraCreateResult {
  created_issues: {
    key: string;
    id: string;
    type: 'epic' | 'story';
    title: string;
  }[];
  errors: {
    title: string;
    error: string;
  }[];
}

export interface HealthStatus {
  status: string;
  mcp_servers: {
    neo4j: boolean;
    filesystem: boolean;
  };
  copilot_available: boolean;
}

export interface AnalysisRun {
  id: string;
  repository_id: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  started_at: string;
  completed_at?: string;
  error_message?: string;
  files_analyzed?: number;
  nodes_created?: number;
  relationships_created?: number;
}

// =============================================================================
// Agentic Readiness Types
// =============================================================================

export type ReadinessGrade = 'A' | 'B' | 'C' | 'D' | 'F';

export interface TestingCoverage {
  percentage: number;
  grade: ReadinessGrade;
}

export interface TestQuality {
  has_unit_tests: boolean;
  has_integration_tests: boolean;
  has_e2e_tests: boolean;
  frameworks: string[];
}

export interface UntestedCriticalFunction {
  entity_id: string;
  name: string;
  file_path: string;
  reason: string;
  stereotype?: string;
}

export interface TestingReadiness {
  overall_grade: ReadinessGrade;
  overall_score: number;
  coverage: TestingCoverage;
  untested_critical_functions: UntestedCriticalFunction[];
  test_quality: TestQuality;
  recommendations: string[];
}

export interface DocumentationCoverage {
  percentage: number;
  grade: ReadinessGrade;
}

export interface UndocumentedPublicApi {
  entity_id: string;
  name: string;
  file_path: string;
  kind: string;
  signature?: string;
}

export interface DocumentationQualityDistribution {
  excellent: number;
  good: number;
  partial: number;
  minimal: number;
  none: number;
}

export interface DocumentationReadiness {
  overall_grade: ReadinessGrade;
  overall_score: number;
  coverage: DocumentationCoverage;
  public_api_coverage: DocumentationCoverage;
  undocumented_public_apis: UndocumentedPublicApi[];
  quality_distribution: DocumentationQualityDistribution;
  recommendations: string[];
}

export interface ReadinessRecommendation {
  priority: 'high' | 'medium' | 'low';
  category: 'testing' | 'documentation';
  title: string;
  description: string;
  affected_count: number;
  affected_entities?: string[];
  estimated_effort?: 'low' | 'medium' | 'high';
}

export interface EnrichmentAction {
  id: string;
  name: string;
  description: string;
  affected_entities: number;
  category: 'documentation' | 'testing';
  is_automated: boolean;
}

export interface ReadinessSummary {
  total_entities: number;
  tested_entities: number;
  documented_entities: number;
  critical_gaps: number;
}

export interface AgenticReadinessReport {
  success: boolean;
  repository_id: string;
  repository_name: string;
  generated_at: string;
  overall_grade: ReadinessGrade;
  overall_score: number;
  is_agentic_ready: boolean;
  testing: TestingReadiness;
  documentation: DocumentationReadiness;
  recommendations: ReadinessRecommendation[];
  enrichment_actions: EnrichmentAction[];
  summary: ReadinessSummary;
}

// =============================================================================
// Feature Discovery Types
// =============================================================================

export type FeatureCategory = 'user-facing' | 'admin' | 'internal' | 'api-only';
export type FeatureComplexity = 'simple' | 'moderate' | 'complex';

export interface DiscoveredFeature {
  entity_id: string;
  feature_name: string;
  description: string;
  category: FeatureCategory;
  confidence: number;
  ui_entry_points: string[];
  api_endpoints: string[];
  services: string[];
  database_entities: string[];
  complexity: FeatureComplexity;
  trace_path: string[];
}

export interface FeatureDiscoveryResult {
  features: DiscoveredFeature[];
  unmapped_endpoints: string[];
  unmapped_routes: string[];
  stats: {
    total_features: number;
    by_category: Record<FeatureCategory, number>;
    by_complexity: Record<FeatureComplexity, number>;
    coverage_percent: number;
  };
}

// =============================================================================
// Enrichment Types
// =============================================================================

export type DocumentationStyle = 'jsdoc' | 'javadoc' | 'docstring' | 'xmldoc' | 'godoc';
export type TestType = 'unit' | 'integration';

export interface DocumentationEnrichmentRequest {
  entity_ids: string[] | 'all-undocumented';
  style: DocumentationStyle;
  include_examples: boolean;
  include_parameters: boolean;
  include_returns: boolean;
  include_throws: boolean;
  max_entities?: number;
}

export interface TestEnrichmentRequest {
  entity_ids: string[] | 'all-untested';
  framework: string;
  test_types: TestType[];
  include_mocks: boolean;
  include_edge_cases: boolean;
  max_entities?: number;
}

export interface GeneratedContent {
  entity_id: string;
  entity_name: string;
  file_path: string;
  content: string;
  insert_position: { line: number; column: number };
  content_type: 'documentation' | 'test';
  is_new_file: boolean;
}

export interface EnrichmentResult {
  success: boolean;
  entities_processed: number;
  entities_enriched: number;
  entities_skipped: number;
  generated_content: GeneratedContent[];
  errors: { entity_id: string; error: string }[];
  enrichment_type: 'documentation' | 'testing';
}
