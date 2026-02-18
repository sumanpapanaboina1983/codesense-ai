import axios from 'axios';
import type {
  Repository,
  Epic,
  EpicGenerationRequest,
  UserStory,
  BacklogGenerationRequest,
  JiraCreateRequest,
  JiraCreateResult,
  HealthStatus,
  AnalysisRun,
  ChatRequest,
  ChatResponse,
} from '../types';

// Use the backend proxy URL that works both in development and Docker
const API_BASE_URL = import.meta.env.VITE_BACKEND_API_URL || '/backend';

const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Health
export const getHealth = async (): Promise<HealthStatus> => {
  const response = await api.get('/health');
  return response.data;
};

// Repositories
export const getRepositories = async (params?: {
  status?: string;
  analysis_status?: string;
  platform?: string;
  limit?: number;
  offset?: number;
}): Promise<Repository[]> => {
  const response = await api.get('/repositories', { params });
  // API returns { success: true, data: [...] }
  return response.data.data || response.data;
};

export const getRepository = async (id: string): Promise<Repository> => {
  const response = await api.get(`/repositories/${id}`);
  // API returns { success: true, data: {...} }
  return response.data.data || response.data;
};

export const createRepository = async (data: {
  url: string;
  personal_access_token?: string;
  auto_analyze_on_sync?: boolean;
}): Promise<Repository> => {
  const response = await api.post('/repositories', data);
  return response.data;
};

export const updateRepository = async (
  id: string,
  data: { auto_analyze_on_sync?: boolean }
): Promise<Repository> => {
  const response = await api.patch(`/repositories/${id}`, data);
  return response.data;
};

export const deleteRepository = async (
  id: string,
  deleteFiles?: boolean,
  force?: boolean
): Promise<void> => {
  await api.delete(`/repositories/${id}`, {
    params: { delete_files: deleteFiles, force },
  });
};

export const syncRepository = async (
  id: string,
  force?: boolean
): Promise<{ commits_pulled: number; message: string }> => {
  const response = await api.post(`/repositories/${id}/sync`, null, {
    params: { force },
  });
  return response.data;
};

// Custom page definition for advanced wiki mode
export interface WikiCustomPage {
  title: string;
  purpose: string;
  notes?: string;
  parent_id?: string;
  is_section?: boolean;
}

// Wiki generation options for analysis
export interface WikiGenerationOptions {
  enabled?: boolean;
  depth?: 'quick' | 'basic' | 'standard' | 'comprehensive' | 'custom';
  mode?: 'standard' | 'advanced';
  // Standard mode options
  include_core_systems?: boolean;
  include_features?: boolean;
  include_api_reference?: boolean;
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

// Analysis request options
export interface AnalyzeOptions {
  reset_graph?: boolean;
  wiki_options?: WikiGenerationOptions;
}

export const analyzeRepository = async (
  id: string,
  options?: AnalyzeOptions
): Promise<AnalysisRun> => {
  // Build request body
  const requestBody = options ? {
    reset_graph: options.reset_graph ?? false,
    wiki_options: options.wiki_options,
  } : undefined;

  const response = await api.post(`/repositories/${id}/analyze`, requestBody);
  return response.data;
};

export const getAnalysisRuns = async (
  repositoryId: string
): Promise<AnalysisRun[]> => {
  const response = await api.get(`/repositories/${repositoryId}/analyses`);
  return response.data;
};

export const getAnalysisRun = async (
  repositoryId: string,
  analysisId: string
): Promise<AnalysisRun> => {
  const response = await api.get(
    `/repositories/${repositoryId}/analyses/${analysisId}`
  );
  return response.data;
};

// Upload Repository ZIP
export interface UploadRepositoryResponse {
  success: boolean;
  data: Repository;
  files_extracted: number;
  message: string;
}

export const uploadRepositoryZip = async (
  file: File,
  name?: string,
  autoAnalyze: boolean = true,
  onProgress?: (progress: number) => void
): Promise<UploadRepositoryResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  if (name) {
    formData.append('name', name);
  }
  formData.append('auto_analyze', String(autoAnalyze));

  const response = await axios.post(
    `${API_BASE_URL}/api/v1/repositories/upload`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percentCompleted = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          onProgress(percentCompleted);
        }
      },
    }
  );
  return response.data;
};

// BRD Generation
// Note: BRD generation now uses streaming via generateBRDStream in services/api.ts
// The unified endpoint POST /brd/generate/{repository_id} always uses multi-agent verification
// Use generateBRDStream from services/api.ts for BRD generation

// Epic Generation
export const generateEpics = async (
  data: EpicGenerationRequest
): Promise<Epic[]> => {
  const response = await api.post('/epics/generate', data);
  return response.data;
};

// Story Generation (Backlog)
export const generateBacklog = async (
  data: BacklogGenerationRequest
): Promise<UserStory[]> => {
  const response = await api.post('/backlogs/generate', data);
  return response.data;
};

// JIRA Integration
export const createJiraIssues = async (
  data: JiraCreateRequest
): Promise<JiraCreateResult> => {
  const response = await api.post('/jira/create', data);
  return response.data;
};

// Code Assistant Chat
export const sendChatMessage = async (
  repositoryId: string,
  question: string,
  conversationId?: string
): Promise<ChatResponse> => {
  const requestData: ChatRequest = {
    question,
    conversation_id: conversationId,
  };
  const response = await api.post(
    `/repositories/${repositoryId}/chat`,
    requestData
  );
  // API returns { success: true, data: {...} }
  return response.data.data || response.data;
};

export default api;
