import { create } from 'zustand';
import type { AnalysisJob, GraphStats, HealthStatus } from '../types/api';

interface AppState {
  // Health status
  health: HealthStatus | null;
  setHealth: (health: HealthStatus | null) => void;

  // Jobs
  jobs: AnalysisJob[];
  setJobs: (jobs: AnalysisJob[]) => void;
  updateJob: (job: AnalysisJob) => void;
  addJob: (job: AnalysisJob) => void;

  // Graph stats
  graphStats: GraphStats | null;
  setGraphStats: (stats: GraphStats | null) => void;

  // Active job polling
  activeJobId: string | null;
  setActiveJobId: (jobId: string | null) => void;

  // UI state
  sidebarOpen: boolean;
  toggleSidebar: () => void;

  // Loading states
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Health
  health: null,
  setHealth: (health) => set({ health }),

  // Jobs
  jobs: [],
  setJobs: (jobs) => set({ jobs }),
  updateJob: (job) =>
    set((state) => ({
      jobs: state.jobs.map((j) => (j.id === job.id ? job : j)),
    })),
  addJob: (job) =>
    set((state) => ({
      jobs: [job, ...state.jobs],
    })),

  // Graph stats
  graphStats: null,
  setGraphStats: (graphStats) => set({ graphStats }),

  // Active job
  activeJobId: null,
  setActiveJobId: (activeJobId) => set({ activeJobId }),

  // UI
  sidebarOpen: true,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  // Loading
  isLoading: false,
  setIsLoading: (isLoading) => set({ isLoading }),
}));
