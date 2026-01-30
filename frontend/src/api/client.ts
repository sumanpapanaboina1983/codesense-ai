import axios from 'axios';
import type {
  Repository,
  BRDRequest,
  BRD,
  Epic,
  EpicGenerationRequest,
  UserStory,
  BacklogGenerationRequest,
  JiraCreateRequest,
  JiraCreateResult,
  HealthStatus,
  AnalysisRun,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
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
  return response.data;
};

export const getRepository = async (id: string): Promise<Repository> => {
  const response = await api.get(`/repositories/${id}`);
  return response.data;
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
  deleteFiles?: boolean
): Promise<void> => {
  await api.delete(`/repositories/${id}`, {
    params: { delete_files: deleteFiles },
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

export const analyzeRepository = async (
  id: string,
  resetGraph?: boolean
): Promise<AnalysisRun> => {
  const response = await api.post(`/repositories/${id}/analyze`, null, {
    params: { reset_graph: resetGraph },
  });
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

export default api;
