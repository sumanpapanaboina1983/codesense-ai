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
