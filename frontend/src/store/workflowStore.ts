import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Repository, BRD, Epic, UserStory } from '../types';

export type WorkflowPhase = 'repository' | 'brd' | 'epics' | 'stories' | 'jira';

interface WorkflowState {
  currentPhase: WorkflowPhase;
  selectedRepository: Repository | null;
  brd: BRD | null;
  epics: Epic[];
  stories: UserStory[];
  jiraProjectKey: string;

  // Actions
  setPhase: (phase: WorkflowPhase) => void;
  setRepository: (repo: Repository | null) => void;
  setBRD: (brd: BRD | null) => void;
  setEpics: (epics: Epic[]) => void;
  setStories: (stories: UserStory[]) => void;
  setJiraProjectKey: (key: string) => void;
  resetWorkflow: () => void;
  canProceedToPhase: (phase: WorkflowPhase) => boolean;
}

const initialState = {
  currentPhase: 'repository' as WorkflowPhase,
  selectedRepository: null,
  brd: null,
  epics: [],
  stories: [],
  jiraProjectKey: '',
};

export const useWorkflowStore = create<WorkflowState>()(
  persist(
    (set, get) => ({
      ...initialState,

      setPhase: (phase) => set({ currentPhase: phase }),

      setRepository: (repo) =>
        set({
          selectedRepository: repo,
          currentPhase: repo ? 'brd' : 'repository',
        }),

      setBRD: (brd) =>
        set({
          brd,
          currentPhase: brd ? 'epics' : get().currentPhase,
        }),

      setEpics: (epics) =>
        set({
          epics,
          currentPhase: epics.length > 0 ? 'stories' : get().currentPhase,
        }),

      setStories: (stories) =>
        set({
          stories,
          currentPhase: stories.length > 0 ? 'jira' : get().currentPhase,
        }),

      setJiraProjectKey: (key) => set({ jiraProjectKey: key }),

      resetWorkflow: () => set(initialState),

      canProceedToPhase: (phase) => {
        const state = get();
        switch (phase) {
          case 'repository':
            return true;
          case 'brd':
            return state.selectedRepository !== null &&
                   state.selectedRepository.analysis_status === 'completed';
          case 'epics':
            return state.brd !== null;
          case 'stories':
            return state.epics.length > 0;
          case 'jira':
            return state.stories.length > 0;
          default:
            return false;
        }
      },
    }),
    {
      name: 'codesense-workflow',
      partialize: (state) => ({
        selectedRepository: state.selectedRepository,
        brd: state.brd,
        epics: state.epics,
        stories: state.stories,
        jiraProjectKey: state.jiraProjectKey,
        currentPhase: state.currentPhase,
      }),
    }
  )
);
