import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import {
  FileText,
  ArrowRight,
  Loader2,
  CheckCircle,
  AlertCircle,
  Download,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  ChevronRight,
  FolderGit2,
  Sparkles,
  Upload,
  X,
  Brain,
  FileCode,
  Shield,
  ShieldCheck,
  Zap,
  Settings,
  Info,
  Eye,
  Layers,
  StopCircle,
  MessageSquare,
  History,
  Edit3,
  Send,
  Library,
  Plus,
  Trash2,
  ListTodo,
  Clock,
  Archive,
  MoreVertical,
  ArrowLeft,
} from 'lucide-react';
import {
  getAnalyzedRepositories,
  generateBRDStream,
  cancelBRDGeneration,
  getDefaultTemplate,
  parseTemplateSections,
  listAvailableModels,
  refineBRDSection,
  refineEntireBRD,
  getArtifactHistory,
  saveBRD,
  listBRDs,
  deleteBRD,
  downloadBRD,
  updateBRDStatus,
  updateBRD,
  type RepositorySummary,
  type BRDResponse,
  type StreamEvent,
  type GenerateBRDRequest,
  type GenerationMode,
  type GenerationApproach,
  type DetailLevel,
  type VerificationReport,
  type ModelInfo,
  type ArtifactHistoryEntry,
  type StoredBRD,
  type RefinedBRD,
  type StoredEpic,
} from '../../services/api';
import './GenerateBRD.css';

interface ThinkingStep {
  id: number;
  content: string;
  timestamp: Date;
  category?: 'init' | 'context' | 'section' | 'verification' | 'complete' | 'error';
}

interface ProgressStats {
  currentSection: string;
  sectionsCompleted: number;
  totalSections: number;
  claimsVerified: number;
  totalClaims: number;
  currentPhase: 'initializing' | 'gathering_context' | 'generating' | 'verifying' | 'complete';
}

interface VerificationInfo {
  is_verified: boolean;
  confidence_score: number;
  hallucination_risk: string;
  iterations_used: number;
  needs_sme_review: boolean;
  mode: GenerationMode;
  verification_report?: VerificationReport;
}

// Generate a deterministic seed from a string (for reproducible outputs)
function generateSeedFromString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  // Ensure positive number in reasonable range
  return Math.abs(hash) % 1000000;
}

// Default values for advanced options
const DEFAULT_OPTIONS = {
  mode: 'draft' as GenerationMode,
  approach: 'context_first' as GenerationApproach,  // Always use context_first
  detail_level: 'standard' as DetailLevel,
  include_similar_features: true,
  max_iterations: 3,
  min_confidence: 0.7,
  show_evidence: false,
  temperature: 0,  // Zero for deterministic outputs
  seed: undefined as number | undefined,  // Auto-generated from feature description
};

// Status configuration for library view
const statusConfig: Record<string, { icon: React.ReactNode; label: string; className: string }> = {
  draft: { icon: <Clock size={14} />, label: 'Draft', className: 'status-draft' },
  in_progress: { icon: <RefreshCw size={14} />, label: 'In Progress', className: 'status-progress' },
  completed: { icon: <CheckCircle size={14} />, label: 'Completed', className: 'status-completed' },
  approved: { icon: <CheckCircle size={14} />, label: 'Approved', className: 'status-approved' },
  archived: { icon: <Archive size={14} />, label: 'Archived', className: 'status-archived' },
};

const priorityColors: Record<string, string> = {
  critical: 'priority-critical',
  high: 'priority-high',
  medium: 'priority-medium',
  low: 'priority-low',
};

export function GenerateBRD() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();

  // View mode state - 'library' shows existing BRDs, 'generate' shows the creation form
  const [viewMode, setViewMode] = useState<'library' | 'generate' | 'view'>(() => {
    // Check if URL has 'new=true' parameter to go directly to generate mode
    return searchParams.get('new') === 'true' ? 'generate' : 'library';
  });

  // Library view state
  const [librarySearchQuery, setLibrarySearchQuery] = useState('');
  const [selectedRepoFilter, setSelectedRepoFilter] = useState<string>('');
  const [selectedStatusFilter, setSelectedStatusFilter] = useState<string>('');
  const [expandedBRDs, setExpandedBRDs] = useState<Set<string>>(new Set());
  const [expandedEpics, setExpandedEpics] = useState<Set<string>>(new Set());
  const [actionMenuOpen, setActionMenuOpen] = useState<string | null>(null);

  // State
  const [selectedRepo, setSelectedRepo] = useState<RepositorySummary | null>(null);
  const [featureDescription, setFeatureDescription] = useState('');
  const [generatedBRD, setGeneratedBRD] = useState<BRDResponse | null>(null);
  const [verificationInfo, setVerificationInfo] = useState<VerificationInfo | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // Generation options state
  const [mode, setMode] = useState<GenerationMode>(DEFAULT_OPTIONS.mode);
  const [approach, setApproach] = useState<GenerationApproach>(DEFAULT_OPTIONS.approach);
  const [detailLevel, setDetailLevel] = useState<DetailLevel>(DEFAULT_OPTIONS.detail_level);

  // Model selection state
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [defaultModel, setDefaultModel] = useState<string>('');
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [includeSimilarFeatures, setIncludeSimilarFeatures] = useState(DEFAULT_OPTIONS.include_similar_features);
  const [maxIterations, setMaxIterations] = useState(DEFAULT_OPTIONS.max_iterations);
  const [minConfidence, setMinConfidence] = useState(DEFAULT_OPTIONS.min_confidence);
  const [showEvidence, setShowEvidence] = useState(DEFAULT_OPTIONS.show_evidence);
  const [seed, setSeed] = useState<number | undefined>(DEFAULT_OPTIONS.seed);
  // Temperature is fixed at 0 for deterministic outputs (not user-configurable)
  const temperature = DEFAULT_OPTIONS.temperature;
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false);
  const [showVerificationReport, setShowVerificationReport] = useState(false);

  // Template upload state
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [templateContent, setTemplateContent] = useState<string>('');
  const [defaultTemplate, setDefaultTemplate] = useState<string>('');
  const [isUsingDefaultTemplate, setIsUsingDefaultTemplate] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Section length configuration
  interface SectionConfig {
    name: string;
    words: number;
    description?: string;
  }
  const [sectionConfigs, setSectionConfigs] = useState<SectionConfig[]>([]);
  const [showSectionConfig, setShowSectionConfig] = useState(false);

  // Streaming state
  const [isGenerating, setIsGenerating] = useState(false);
  const [isCancelled, setIsCancelled] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const [streamedContent, setStreamedContent] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Progress tracking state
  const [progressStats, setProgressStats] = useState<ProgressStats>({
    currentSection: '',
    sectionsCompleted: 0,
    totalSections: 0,
    claimsVerified: 0,
    totalClaims: 0,
    currentPhase: 'initializing',
  });
  const thinkingContainerRef = useRef<HTMLDivElement>(null);

  // BRD Refinement state
  const [, setRefinedBRD] = useState(null);
  const [sectionFeedback, setSectionFeedback] = useState<Record<string, string>>({});
  const [showFeedbackFor, setShowFeedbackFor] = useState<string | null>(null);
  const [globalFeedback, setGlobalFeedback] = useState('');
  const [isRefining, setIsRefining] = useState(false);
  const [refiningSection, setRefiningSection] = useState<string | null>(null);
  const [refinementCount, setRefinementCount] = useState(0);

  // Audit history state
  const [showHistory, setShowHistory] = useState(false);
  const [artifactHistory, setArtifactHistory] = useState<ArtifactHistoryEntry[]>([]);

  // Database storage state
  const [savedBRD, setSavedBRD] = useState<StoredBRD | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // View mode state (for viewing existing BRDs)
  const [viewedBRD, setViewedBRD] = useState<StoredBRD | null>(null);
  const [isApproving, setIsApproving] = useState(false);

  // Edit mode state
  const [isEditing, setIsEditing] = useState(false);
  const [editingBRD, setEditingBRD] = useState<StoredBRD | null>(null);
  const [editingSections, setEditingSections] = useState<Array<{ name: string; content: string }>>([]);

  // View mode section state
  const [refiningSectionIndex, setRefiningSectionIndex] = useState<number | null>(null);
  const [sectionRefineFeedback, setSectionRefineFeedback] = useState<string>('');
  const [isRefiningSection, setIsRefiningSection] = useState(false);

  // Fetch repositories with completed analysis
  const {
    data: repositories,
    isLoading: isLoadingRepos,
    error: reposError,
    refetch: refetchRepos,
  } = useQuery({
    queryKey: ['analyzedRepositories'],
    queryFn: getAnalyzedRepositories,
  });

  // Fetch BRDs for library view
  const {
    data: brdsResponse,
    isLoading: isLoadingBRDs,
    error: brdsError,
    refetch: refetchBRDs,
  } = useQuery({
    queryKey: ['brds', selectedRepoFilter, selectedStatusFilter, librarySearchQuery],
    queryFn: () => listBRDs({
      repository_id: selectedRepoFilter || undefined,
      status: selectedStatusFilter || undefined,
      search: librarySearchQuery || undefined,
      limit: 100,
    }),
    refetchInterval: 30000,
    enabled: viewMode === 'library',
  });

  const brds = brdsResponse?.data || [];

  // Delete BRD mutation
  const deleteMutation = useMutation({
    mutationFn: deleteBRD,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brds'] });
    },
  });

  // Library view helper functions
  const toggleBRDExpanded = (brdId: string) => {
    setExpandedBRDs(prev => {
      const next = new Set(prev);
      if (next.has(brdId)) {
        next.delete(brdId);
      } else {
        next.add(brdId);
      }
      return next;
    });
  };

  const toggleEpicExpanded = (epicId: string) => {
    setExpandedEpics(prev => {
      const next = new Set(prev);
      if (next.has(epicId)) {
        next.delete(epicId);
      } else {
        next.add(epicId);
      }
      return next;
    });
  };

  const handleDownloadBRD = async (brd: StoredBRD, format: 'md' | 'html') => {
    try {
      const blob = await downloadBRD(brd.id, format, true);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${brd.brd_number}-${brd.title.replace(/\s+/g, '-')}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download failed:', err);
    }
    setActionMenuOpen(null);
  };

  const handleDeleteBRD = async (brdId: string) => {
    if (!confirm('Are you sure you want to delete this BRD? This will also delete all associated EPICs and Backlogs.')) {
      return;
    }
    try {
      await deleteMutation.mutateAsync(brdId);
    } catch (err) {
      console.error('Delete failed:', err);
    }
    setActionMenuOpen(null);
  };

  const handleGenerateEpicsFromBRD = (brd: StoredBRD) => {
    navigate(`/generate-epic?brd_id=${brd.id}`);
    setActionMenuOpen(null);
  };

  const handleViewBRD = (brd: StoredBRD) => {
    // Set the viewed BRD and switch to view mode
    setViewedBRD(brd);
    setViewMode('view');
    setActionMenuOpen(null);
  };

  const handleApproveAndContinue = async () => {
    if (!viewedBRD) return;

    setIsApproving(true);
    try {
      await updateBRDStatus(viewedBRD.id, 'approved');
      // Navigate to EPIC generation with this BRD
      navigate(`/generate-epic?brd_id=${viewedBRD.id}`);
    } catch (err) {
      console.error('Failed to approve BRD:', err);
      setIsApproving(false);
    }
  };

  const handleEditBRD = () => {
    if (!viewedBRD) return;

    // Set up editing mode with sections
    setEditingBRD(viewedBRD);
    setIsEditing(true);

    // Parse sections from BRD or create from markdown
    if (viewedBRD.sections && viewedBRD.sections.length > 0) {
      setEditingSections([...viewedBRD.sections]);
    } else {
      // Parse markdown into sections
      const sections = parseMarkdownIntoSections(viewedBRD.markdown_content);
      setEditingSections(sections);
    }

    setViewMode('view'); // Stay in view mode but with edit UI
  };

  const parseMarkdownIntoSections = (markdown: string): Array<{ name: string; content: string }> => {
    // Parse sections from markdown headers (## or ###)
    // This is template-agnostic - sections are determined by how the BRD was generated
    const sections: Array<{ name: string; content: string }> = [];
    const lines = markdown.split('\n');
    let currentSection: { name: string; content: string } | null = null;

    for (const line of lines) {
      // Match ## or ### headers, optionally with numbering like "## 1. Section Name"
      const headerMatch = line.match(/^#{2,3}\s+(?:\d+\.\s*)?(.+)/);
      if (headerMatch) {
        if (currentSection) {
          sections.push(currentSection);
        }
        currentSection = { name: headerMatch[1].trim(), content: '' };
      } else if (currentSection) {
        currentSection.content += line + '\n';
      }
    }

    if (currentSection) {
      sections.push(currentSection);
    }

    // Return sections with trimmed content
    return sections.map(s => ({
      name: s.name,
      content: s.content.trim()
    }));
  };

  const handleSaveEdit = async () => {
    if (!editingBRD) return;

    setIsSaving(true);
    try {
      // Rebuild markdown from sections
      const newMarkdown = editingSections
        .map(s => `## ${s.name}\n\n${s.content}`)
        .join('\n\n');

      // Update the BRD with edited content
      const updatedBRD = await updateBRD(editingBRD.id, {
        markdown_content: newMarkdown,
        sections: editingSections,
      });

      // Update the viewed BRD with saved data
      setViewedBRD(updatedBRD);
      setIsEditing(false);
      setEditingBRD(null);
      setEditingSections([]);

      // Refresh the list
      refetchBRDs();
    } catch (err) {
      console.error('Failed to save BRD:', err);
      setSaveError('Failed to save BRD');
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditingBRD(null);
    setEditingSections([]);
  };

  const handleSectionContentChange = (index: number, content: string) => {
    setEditingSections(prev => {
      const updated = [...prev];
      updated[index] = { ...updated[index], content };
      return updated;
    });
  };

  // Handle DOCX download - convert markdown to DOCX
  const handleDownloadDOCX = async (brd: StoredBRD) => {
    try {
      // Create a simple HTML-based DOCX conversion
      const markdown = brd.markdown_content || '';

      // Convert markdown to basic HTML
      let html = markdown
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br/>');

      html = `<html><head><meta charset="utf-8"><title>${brd.title}</title></head><body><h1>${brd.title}</h1><p>${html}</p></body></html>`;

      // Create blob with proper MIME type for Word
      const blob = new Blob([html], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${brd.brd_number}-${brd.title.replace(/\s+/g, '-')}.doc`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('DOCX download failed:', err);
      setError('Failed to download DOCX');
    }
  };

  // Handle AI refinement for a specific section in edit mode
  const handleRefineSectionWithAI = async (sectionIndex: number) => {
    if (!viewedBRD || !sectionRefineFeedback.trim()) return;

    setIsRefiningSection(true);
    try {
      const section = editingSections[sectionIndex];

      // Call the refineBRDSection API
      const response = await refineBRDSection(viewedBRD.id, section.name, {
        brd_id: viewedBRD.id,
        section_name: section.name,
        current_content: section.content,
        user_feedback: sectionRefineFeedback,
        full_brd_context: viewedBRD.markdown_content || '',
        repository_id: viewedBRD.repository_id,
      });

      // Update the section with refined content
      if (response.after_content) {
        handleSectionContentChange(sectionIndex, response.after_content);
      }

      setRefiningSectionIndex(null);
      setSectionRefineFeedback('');
    } catch (err) {
      console.error('Failed to refine section:', err);
      setError(err instanceof Error ? err.message : 'Failed to refine section');
    } finally {
      setIsRefiningSection(false);
    }
  };

  // Handle AI refinement for a specific section in view mode (updates BRD directly)
  const handleRefineViewSectionWithAI = async (sectionIndex: number, sections: Array<{ name: string; content: string }>) => {
    if (!viewedBRD || !sectionRefineFeedback.trim()) return;

    setIsRefiningSection(true);
    try {
      const section = sections[sectionIndex];

      // Call the refineBRDSection API
      const response = await refineBRDSection(viewedBRD.id, section.name, {
        brd_id: viewedBRD.id,
        section_name: section.name,
        current_content: section.content,
        user_feedback: sectionRefineFeedback,
        full_brd_context: viewedBRD.markdown_content || '',
        repository_id: viewedBRD.repository_id,
      });

      // Update the section with refined content
      if (response.after_content) {
        const updatedSections = [...sections];
        updatedSections[sectionIndex] = { ...section, content: response.after_content };

        // Rebuild markdown from sections
        const newMarkdown = updatedSections
          .map(s => `## ${s.name}\n\n${s.content}`)
          .join('\n\n');

        // Update the BRD in database
        const updatedBRD = await updateBRD(viewedBRD.id, {
          markdown_content: newMarkdown,
          sections: updatedSections,
        });

        // Update the viewed BRD state
        setViewedBRD(updatedBRD);

        // Refresh the list
        refetchBRDs();
      }

      setRefiningSectionIndex(null);
      setSectionRefineFeedback('');
    } catch (err) {
      console.error('Failed to refine section:', err);
      setError(err instanceof Error ? err.message : 'Failed to refine section');
    } finally {
      setIsRefiningSection(false);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  // Close action menu when clicking outside
  useEffect(() => {
    const handleClick = () => setActionMenuOpen(null);
    if (actionMenuOpen) {
      document.addEventListener('click', handleClick);
      return () => document.removeEventListener('click', handleClick);
    }
  }, [actionMenuOpen]);

  // Load default template on mount
  useEffect(() => {
    const loadDefaultTemplate = async () => {
      try {
        const response = await getDefaultTemplate();
        if (response.success && response.template) {
          setDefaultTemplate(response.template);
          setTemplateContent(response.template);
        }
      } catch (err) {
        console.error('Failed to load default template:', err);
      }
    };
    loadDefaultTemplate();
  }, []);

  // Load available models on mount
  useEffect(() => {
    const loadModels = async () => {
      setIsLoadingModels(true);
      try {
        const response = await listAvailableModels();
        setAvailableModels(response.models);
        setDefaultModel(response.default_model);
        setSelectedModel(response.default_model);
      } catch (err) {
        console.error('Failed to load available models:', err);
        // Set a reasonable default if API fails
        setSelectedModel('gpt-4.1');
      } finally {
        setIsLoadingModels(false);
      }
    };
    loadModels();
  }, []);

  // Parse sections from template content using LLM
  const [isParsingSections, setIsParsingSections] = useState(false);

  useEffect(() => {
    if (!templateContent) return;

    const parseSections = async () => {
      setIsParsingSections(true);
      try {
        // Use LLM to parse sections from template
        const response = await parseTemplateSections(templateContent);
        if (response.success && response.sections.length > 0) {
          // Normalize word counts to nearest preset (200, 300, 500) or default to 300
          const normalizeWords = (words: number): number => {
            if (words <= 200) return 200;
            if (words >= 450) return 500;
            return 300; // Default to Standard
          };
          setSectionConfigs(
            response.sections.map(s => ({
              name: s.name,
              words: normalizeWords(s.suggested_words || 300),
              description: s.description,
            }))
          );
        } else {
          // Fallback to default sections - all set to Standard (300 words)
          setSectionConfigs([
            { name: 'Feature Overview', words: 300, description: 'Summary of the feature' },
            { name: 'Functional Requirements', words: 300, description: 'What the system must do' },
            { name: 'Business Validations', words: 300, description: 'Logic constraints and rules' },
            { name: 'Actors and Interactions', words: 300, description: 'User roles and systems' },
            { name: 'Process Flow', words: 300, description: 'Step-by-step process' },
            { name: 'Acceptance Criteria', words: 300, description: 'Conditions for completion' },
          ]);
        }
      } catch (err) {
        console.error('Failed to parse template sections:', err);
        // Fallback to default sections on error - all set to Standard (300 words)
        setSectionConfigs([
          { name: 'Feature Overview', words: 300 },
          { name: 'Functional Requirements', words: 300 },
          { name: 'Business Validations', words: 300 },
          { name: 'Actors and Interactions', words: 300 },
          { name: 'Process Flow', words: 300 },
          { name: 'Acceptance Criteria', words: 300 },
        ]);
      } finally {
        setIsParsingSections(false);
      }
    };

    parseSections();
  }, [templateContent]);

  // Handle URL parameters for pre-filling form
  useEffect(() => {
    const repositoryId = searchParams.get('repository');
    const feature = searchParams.get('feature');
    const description = searchParams.get('description');
    const urlMode = searchParams.get('mode');

    // Set mode from URL parameter
    if (urlMode === 'verified' || urlMode === 'draft') {
      setMode(urlMode as GenerationMode);
    }

    // Set feature description from URL
    if (feature) {
      const fullDescription = description
        ? `${feature}\n\n${description}`
        : feature;
      setFeatureDescription(fullDescription);
    }

    // Select repository from URL parameter once repositories are loaded
    if (repositoryId && repositories && !selectedRepo) {
      const repo = repositories.find(r => r.id === repositoryId);
      if (repo) {
        setSelectedRepo(repo);
      }
    }
  }, [searchParams, repositories, selectedRepo]);

  // Auto-generate seed from feature description for reproducible outputs
  useEffect(() => {
    if (featureDescription && selectedRepo) {
      // Generate a deterministic seed from repo ID + feature description
      const seedInput = `${selectedRepo.id}:${featureDescription}`;
      const generatedSeed = generateSeedFromString(seedInput);
      setSeed(generatedSeed);
    }
  }, [featureDescription, selectedRepo]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = () => setDropdownOpen(false);
    if (dropdownOpen) {
      document.addEventListener('click', handleClickOutside);
      return () => document.removeEventListener('click', handleClickOutside);
    }
  }, [dropdownOpen]);

  // Auto-scroll thinking container
  useEffect(() => {
    if (thinkingContainerRef.current) {
      thinkingContainerRef.current.scrollTop = thinkingContainerRef.current.scrollHeight;
    }
  }, [thinkingSteps]);

  const handleTemplateUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      if (!file.name.endsWith('.md') && !file.name.endsWith('.txt')) {
        setError('Please upload a Markdown (.md) or text (.txt) file');
        return;
      }

      setTemplateFile(file);
      setIsUsingDefaultTemplate(false);
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result as string;
        setTemplateContent(content);
        setError(null);
      };
      reader.onerror = () => {
        setError('Failed to read template file');
      };
      reader.readAsText(file);
    }
  };

  const handleRemoveTemplate = () => {
    setTemplateFile(null);
    // Restore default template when custom template is removed
    setTemplateContent(defaultTemplate);
    setIsUsingDefaultTemplate(true);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleUseDefaultTemplate = () => {
    setTemplateFile(null);
    setTemplateContent(defaultTemplate);
    setIsUsingDefaultTemplate(true);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDownloadTemplate = () => {
    if (!templateContent) return;
    const blob = new Blob([templateContent], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = isUsingDefaultTemplate ? 'default-brd-template.md' : 'custom-brd-template.md';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleStopGeneration = async () => {
    // Immediately update UI
    setIsCancelled(true);
    setIsGenerating(false);
    setThinkingSteps((prev) => [
      ...prev,
      {
        id: Date.now(),
        content: '⏹️ Stopping generation...',
        timestamp: new Date(),
        category: 'error',
      },
    ]);

    // Then cancel on backend
    const wasCancelled = await cancelBRDGeneration();
    if (wasCancelled) {
      setThinkingSteps((prev) => [
        ...prev,
        {
          id: Date.now(),
          content: '⏹️ Generation stopped by user',
          timestamp: new Date(),
          category: 'error',
        },
      ]);
    }
  };

  const handleGenerate = async () => {
    if (!selectedRepo) {
      setError('Please select a repository');
      return;
    }
    if (!featureDescription.trim()) {
      setError('Please provide a feature description');
      return;
    }

    setIsGenerating(true);
    setIsCancelled(false);
    setThinkingSteps([]);
    setStreamedContent('');
    setError(null);
    setGeneratedBRD(null);
    setVerificationInfo(null);
    setProgressStats({
      currentSection: '',
      sectionsCompleted: 0,
      totalSections: 0,
      claimsVerified: 0,
      totalClaims: 0,
      currentPhase: 'initializing',
    });

    // Build request with all parameters
    const request: GenerateBRDRequest = {
      feature_description: featureDescription,
      mode: mode,
      approach: approach,
      detail_level: detailLevel,
      include_similar_features: includeSimilarFeatures,
      max_iterations: maxIterations,
      min_confidence: minConfidence,
      show_evidence: showEvidence,
      temperature: temperature,
      seed: seed,
      model: selectedModel !== defaultModel ? selectedModel : undefined,
    };

    // Add template config if template is provided
    if (templateContent) {
      request.brd_template = templateContent;
      request.template_config = {
        brd_template: templateContent,
      };
    }

    // Add section configurations with word counts
    if (sectionConfigs.length > 0) {
      request.custom_sections = sectionConfigs.map(section => ({
        name: section.name,
        description: section.description || `Content for ${section.name} section`,
        target_words: section.words,
      }));
    }

    let stepId = 0;

    await generateBRDStream(
      selectedRepo.id,
      request,
      (event: StreamEvent) => {
        switch (event.type) {
          case 'thinking':
            if (event.content) {
              const content = event.content;

              // Parse progress from content and update stats
              // Match "📋 Starting generation: X sections to process"
              const sectionsMatch = content.match(/(\d+) sections? to process/);
              if (sectionsMatch) {
                setProgressStats((prev) => ({
                  ...prev,
                  totalSections: parseInt(sectionsMatch[1]),
                  currentPhase: 'generating',
                }));
              }

              // Match "📝 Section X/Y: SectionName"
              const sectionMatch = content.match(/Section (\d+)\/(\d+): (.+)/);
              if (sectionMatch) {
                setProgressStats((prev) => ({
                  ...prev,
                  sectionsCompleted: parseInt(sectionMatch[1]) - 1,
                  totalSections: parseInt(sectionMatch[2]),
                  currentSection: sectionMatch[3],
                  currentPhase: 'generating',
                }));
              }

              // Match "✅ SectionName: X/Y claims verified (Z% confidence)"
              const sectionCompleteMatch = content.match(/(\d+)\/(\d+) claims verified/);
              if (sectionCompleteMatch && (content.includes('✅') || content.includes('⚠️'))) {
                setProgressStats((prev) => ({
                  ...prev,
                  sectionsCompleted: prev.sectionsCompleted + 1,
                  claimsVerified: prev.claimsVerified + parseInt(sectionCompleteMatch[1]),
                  totalClaims: prev.totalClaims + parseInt(sectionCompleteMatch[2]),
                }));
              }

              // Match "🔍 Verifying claims: X/Y (Z verified)"
              const verifyingMatch = content.match(/Verifying claims: (\d+)\/(\d+) \((\d+) verified\)/);
              if (verifyingMatch) {
                setProgressStats((prev) => ({
                  ...prev,
                  currentPhase: 'verifying',
                }));
              }

              // Match "📋 Extracted X claims from SectionName"
              const extractedMatch = content.match(/Extracted (\d+) claims from/);
              if (extractedMatch) {
                setProgressStats((prev) => ({
                  ...prev,
                  currentPhase: 'verifying',
                }));
              }

              // Match context gathering
              if (content.includes('Building codebase context') || content.includes('Gathering context')) {
                setProgressStats((prev) => ({
                  ...prev,
                  currentPhase: 'gathering_context',
                }));
              }

              // Determine category for styling
              let category: ThinkingStep['category'] = 'init';
              if (content.includes('Section') || content.includes('Generating content')) {
                category = 'section';
              } else if (content.includes('Verif') || content.includes('claims') || content.includes('🔬') || content.includes('🔍')) {
                category = 'verification';
              } else if (content.includes('context') || content.includes('📊')) {
                category = 'context';
              } else if (content.includes('✅') && content.includes('complete')) {
                category = 'complete';
              }

              setThinkingSteps((prev) => [
                ...prev,
                { id: stepId++, content: content, timestamp: new Date(), category },
              ]);
            }
            break;
          case 'content':
            if (event.content) {
              setStreamedContent((prev) => prev + event.content);
            }
            break;
          case 'complete':
            if (event.data?.brd) {
              const brd = event.data.brd;
              setGeneratedBRD(brd);
              // Capture verification info including full report
              const verInfo = {
                is_verified: event.data.is_verified ?? false,
                confidence_score: event.data.confidence_score ?? 0,
                hallucination_risk: event.data.hallucination_risk ?? 'unknown',
                iterations_used: event.data.iterations_used ?? 0,
                needs_sme_review: event.data.needs_sme_review ?? false,
                mode: event.data.mode ?? mode,
                verification_report: event.data.verification_report,
              };
              setVerificationInfo(verInfo);

              // Save BRD to database
              if (selectedRepo) {
                setIsSaving(true);
                setSaveError(null);
                saveBRD({
                  repository_id: selectedRepo.id,
                  title: brd.title,
                  feature_description: featureDescription,
                  markdown_content: brd.markdown,
                  mode: mode,
                  confidence_score: verInfo.confidence_score,
                  verification_report: verInfo.verification_report,
                }).then((stored) => {
                  setSavedBRD(stored);
                  setIsSaving(false);
                }).catch((err) => {
                  console.error('Failed to save BRD:', err);
                  setSaveError('Failed to save BRD to library');
                  setIsSaving(false);
                });
              }
            }
            setProgressStats((prev) => ({ ...prev, currentPhase: 'complete' }));
            setIsGenerating(false);
            break;
          case 'error':
            setError(event.content || 'An error occurred during generation');
            setIsGenerating(false);
            break;
        }
      },
      (err: Error) => {
        setError(err.message || 'Failed to generate BRD');
        setIsGenerating(false);
      },
      () => {
        // onCancel callback
        setIsCancelled(true);
        setIsGenerating(false);
      }
    );
  };

  const handleDownload = (format: 'md' | 'html') => {
    if (!generatedBRD) return;

    let content: string;
    let mimeType: string;
    let extension: string;

    if (format === 'md') {
      content = generatedBRD.markdown;
      mimeType = 'text/markdown';
      extension = 'md';
    } else {
      // Convert markdown to basic HTML
      content = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>${generatedBRD.title}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 40px; line-height: 1.6; }
    h1 { color: #1a365d; border-bottom: 2px solid #4299e1; padding-bottom: 10px; }
    h2 { color: #2c5282; margin-top: 30px; }
    h3 { color: #2d3748; }
    pre { background: #f7fafc; padding: 16px; border-radius: 8px; overflow-x: auto; }
    code { background: #edf2f7; padding: 2px 6px; border-radius: 4px; }
    blockquote { border-left: 4px solid #4299e1; margin: 0; padding-left: 16px; color: #4a5568; }
    table { border-collapse: collapse; width: 100%; margin: 16px 0; }
    th, td { border: 1px solid #e2e8f0; padding: 12px; text-align: left; }
    th { background: #f7fafc; }
  </style>
</head>
<body>
<pre>${generatedBRD.markdown}</pre>
</body>
</html>`;
      mimeType = 'text/html';
      extension = 'html';
    }

    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${generatedBRD.id}-${new Date().toISOString().split('T')[0]}.${extension}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleCreateEPIC = () => {
    // If BRD is saved to database, use brd_id parameter for cleaner flow
    if (savedBRD) {
      navigate(`/generate-epic?brd_id=${savedBRD.id}`);
    } else {
      // Fallback to passing BRD content via state
      navigate('/generate-epic', {
        state: {
          brd: generatedBRD,
          repository: selectedRepo,
          brdContent: generatedBRD?.markdown,
          brdTitle: generatedBRD?.title,
        },
      });
    }
  };

  const handleViewInLibrary = () => {
    navigate('/brds');
  };

  const handleReset = () => {
    setGeneratedBRD(null);
    setVerificationInfo(null);
    setFeatureDescription('');
    setSelectedRepo(null);
    setThinkingSteps([]);
    setStreamedContent('');
    setError(null);
    setIsCancelled(false);
    setTemplateFile(null);
    setTemplateContent('');
    setShowVerificationReport(false);
    setProgressStats({
      currentSection: '',
      sectionsCompleted: 0,
      totalSections: 0,
      claimsVerified: 0,
      totalClaims: 0,
      currentPhase: 'initializing',
    });
    // Reset options to defaults
    setMode(DEFAULT_OPTIONS.mode);
    setApproach(DEFAULT_OPTIONS.approach);
    setDetailLevel(DEFAULT_OPTIONS.detail_level);
    setIncludeSimilarFeatures(DEFAULT_OPTIONS.include_similar_features);
    setMaxIterations(DEFAULT_OPTIONS.max_iterations);
    setMinConfidence(DEFAULT_OPTIONS.min_confidence);
    setShowEvidence(DEFAULT_OPTIONS.show_evidence);
    setShowAdvancedOptions(false);
    // Reset refinement state
    setRefinedBRD(null);
    setSectionFeedback({});
    setShowFeedbackFor(null);
    setGlobalFeedback('');
    setRefinementCount(0);
    setShowHistory(false);
    setArtifactHistory([]);
    // Reset database storage state
    setSavedBRD(null);
    setSaveError(null);
  };

  // Handle section refinement
  const handleSectionRefine = async (sectionName: string) => {
    if (!generatedBRD || !selectedRepo) return;
    const feedback = sectionFeedback[sectionName];
    if (!feedback?.trim()) {
      setError('Please provide feedback for refinement');
      return;
    }

    setIsRefining(true);
    setRefiningSection(sectionName);
    setError(null);

    try {
      // Parse sections from markdown to find current content
      const sections = parseBRDSections(generatedBRD.markdown);
      const currentSection = sections.find(s => s.name === sectionName);
      if (!currentSection) {
        throw new Error(`Section "${sectionName}" not found`);
      }

      const response = await refineBRDSection(generatedBRD.id, sectionName, {
        brd_id: generatedBRD.id,
        section_name: sectionName,
        current_content: currentSection.content,
        user_feedback: feedback,
        full_brd_context: generatedBRD.markdown,
        repository_id: selectedRepo.id,
      });

      if (response.success) {
        // Update the markdown with refined section
        const updatedMarkdown = updateSectionInMarkdown(
          generatedBRD.markdown,
          sectionName,
          response.refined_section.content
        );

        setGeneratedBRD({
          ...generatedBRD,
          markdown: updatedMarkdown,
        });

        setRefinementCount(prev => prev + 1);
        setSectionFeedback(prev => ({ ...prev, [sectionName]: '' }));
        setShowFeedbackFor(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refine section');
    } finally {
      setIsRefining(false);
      setRefiningSection(null);
    }
  };

  // Handle global BRD refinement
  const handleGlobalRefine = async () => {
    if (!generatedBRD || !selectedRepo || !globalFeedback.trim()) {
      setError('Please provide feedback for refinement');
      return;
    }

    setIsRefining(true);
    setError(null);

    try {
      // Build RefinedBRD from current state
      const sections = parseBRDSections(generatedBRD.markdown);
      const currentBRD: RefinedBRD = {
        id: generatedBRD.id,
        title: generatedBRD.title,
        version: generatedBRD.version,
        repository_id: selectedRepo.id,
        sections: sections.map((s, i) => ({
          name: s.name,
          content: s.content,
          section_order: i,
          refinement_count: 0,
        })),
        markdown: generatedBRD.markdown,
        mode: mode,
        refinement_count: refinementCount,
        refinement_history: [],
        status: 'draft',
        created_at: generatedBRD.created_at,
      };

      const response = await refineEntireBRD(generatedBRD.id, {
        brd_id: generatedBRD.id,
        current_brd: currentBRD,
        global_feedback: globalFeedback,
        repository_id: selectedRepo.id,
      });

      if (response.success) {
        setGeneratedBRD({
          ...generatedBRD,
          markdown: response.refined_brd.markdown,
        });
        setRefinementCount(prev => prev + 1);
        setGlobalFeedback('');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refine BRD');
    } finally {
      setIsRefining(false);
    }
  };

  // Load artifact history
  const handleShowHistory = async () => {
    if (!generatedBRD) return;

    setShowHistory(true);
    try {
      const response = await getArtifactHistory('brd', generatedBRD.id);
      setArtifactHistory(response.history);
    } catch (err) {
      console.error('Failed to load history:', err);
      setArtifactHistory([]);
    }
  };

  // Helper: Parse sections from markdown
  const parseBRDSections = (markdown: string): { name: string; content: string }[] => {
    const sections: { name: string; content: string }[] = [];
    let currentSection: { name: string; content: string[] } | null = null;

    for (const line of markdown.split('\n')) {
      const headerMatch = line.match(/^##\s+(?:\d+\.?\s*)?(.+)$/);
      if (headerMatch) {
        if (currentSection) {
          sections.push({
            name: currentSection.name,
            content: currentSection.content.join('\n').trim(),
          });
        }
        currentSection = { name: headerMatch[1].trim(), content: [] };
      } else if (currentSection) {
        currentSection.content.push(line);
      }
    }

    if (currentSection) {
      sections.push({
        name: currentSection.name,
        content: currentSection.content.join('\n').trim(),
      });
    }

    return sections;
  };

  // Helper: Update a section in markdown
  const updateSectionInMarkdown = (markdown: string, sectionName: string, newContent: string): string => {
    const lines = markdown.split('\n');
    const result: string[] = [];
    let skipUntilNextSection = false;

    for (const line of lines) {
      const headerMatch = line.match(/^##\s+(?:\d+\.?\s*)?(.+)$/);

      if (headerMatch) {
        if (skipUntilNextSection) {
          // Add new content before next section
          skipUntilNextSection = false;
        }

        const currentSectionName = headerMatch[1].trim();
        if (currentSectionName.toLowerCase() === sectionName.toLowerCase()) {
          result.push(line);
          result.push('');
          result.push(newContent);
          result.push('');
          skipUntilNextSection = true;
          continue;
        }
      }

      if (!skipUntilNextSection) {
        result.push(line);
      }
    }

    return result.join('\n');
  };

  // Code Evidence Panel Component - displays code that supports a claim
  const CodeEvidencePanel = ({
    references,
    claimId,
  }: {
    references: Array<{
      file_path: string;
      start_line: number;
      end_line: number;
      snippet?: string;
      explanation?: string;
      entity_name?: string;
      entity_type?: string;
    }>;
    claimId: string;
  }) => {
    const [expandedSnippets, setExpandedSnippets] = useState<Set<number>>(new Set());
    const [showAllRefs, setShowAllRefs] = useState(false);

    const toggleSnippet = (index: number) => {
      const newExpanded = new Set(expandedSnippets);
      if (newExpanded.has(index)) {
        newExpanded.delete(index);
      } else {
        newExpanded.add(index);
      }
      setExpandedSnippets(newExpanded);
    };

    const displayRefs = showAllRefs ? references : references.slice(0, 3);

    return (
      <div className="code-evidence-panel">
        <div className="code-evidence-header">
          <FileCode size={14} />
          <span>Supporting Code ({references.length} location{references.length !== 1 ? 's' : ''})</span>
        </div>

        <div className="code-evidence-list">
          {displayRefs.map((ref, index) => {
            const isExpanded = expandedSnippets.has(index);
            const fileName = ref.file_path.split('/').pop() || ref.file_path;

            return (
              <div key={`${claimId}-ref-${index}`} className="code-evidence-item">
                <div
                  className="code-evidence-location"
                  onClick={() => ref.snippet && toggleSnippet(index)}
                  style={{ cursor: ref.snippet ? 'pointer' : 'default' }}
                >
                  <div className="location-info">
                    <span className="file-name">{fileName}</span>
                    <span className="line-range">:{ref.start_line}-{ref.end_line}</span>
                    {ref.entity_name && (
                      <span className="entity-badge">
                        {ref.entity_type && <span className="entity-type">{ref.entity_type}</span>}
                        {ref.entity_name}
                      </span>
                    )}
                  </div>
                  {ref.snippet && (
                    <button className="expand-btn" type="button">
                      {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      {isExpanded ? 'Hide' : 'View'} Code
                    </button>
                  )}
                </div>

                {/* Explanation of how this code supports the claim */}
                {ref.explanation && (
                  <div className="code-explanation">
                    <CheckCircle size={12} />
                    <span>{ref.explanation}</span>
                  </div>
                )}

                {/* Expandable code snippet */}
                {ref.snippet && isExpanded && (
                  <div className="code-snippet-container">
                    <div className="snippet-header">
                      <span className="snippet-path">{ref.file_path}</span>
                      <span className="snippet-lines">Lines {ref.start_line}-{ref.end_line}</span>
                    </div>
                    <pre className="code-snippet-full">
                      <code>{ref.snippet}</code>
                    </pre>
                  </div>
                )}

                {/* Show preview when collapsed */}
                {ref.snippet && !isExpanded && (
                  <pre className="code-snippet-preview">
                    <code>{ref.snippet.split('\n').slice(0, 3).join('\n')}{ref.snippet.split('\n').length > 3 ? '\n...' : ''}</code>
                  </pre>
                )}
              </div>
            );
          })}
        </div>

        {references.length > 3 && (
          <button
            className="show-more-refs"
            type="button"
            onClick={() => setShowAllRefs(!showAllRefs)}
          >
            {showAllRefs
              ? `Show less`
              : `Show ${references.length - 3} more code location${references.length - 3 !== 1 ? 's' : ''}`}
          </button>
        )}
      </div>
    );
  };

  // Helper function to render confidence bar
  const renderConfidenceBar = (confidence: number) => {
    const percentage = confidence * 100;
    const colorClass = percentage >= 80 ? 'high' : percentage >= 60 ? 'medium' : 'low';
    return (
      <div className="confidence-bar-container">
        <div className={`confidence-bar ${colorClass}`} style={{ width: `${percentage}%` }} />
        <span className="confidence-text">{percentage.toFixed(0)}%</span>
      </div>
    );
  };

  // Helper function to render claim status badge
  const renderStatusBadge = (status: string) => {
    const statusMap: Record<string, { icon: typeof CheckCircle; className: string }> = {
      verified: { icon: CheckCircle, className: 'status-verified' },
      partially_verified: { icon: AlertCircle, className: 'status-partial' },
      unverified: { icon: AlertCircle, className: 'status-unverified' },
      contradicted: { icon: X, className: 'status-contradicted' },
    };
    const config = statusMap[status] || statusMap.unverified;
    const Icon = config.icon;
    return (
      <span className={`status-badge ${config.className}`}>
        <Icon size={12} />
        {status.replace('_', ' ')}
      </span>
    );
  };

  // If BRD is generated, show the review screen
  if (generatedBRD) {
    const report = verificationInfo?.verification_report;
    const isVerifiedMode = verificationInfo?.mode === 'verified';

    return (
      <div className="generate-brd-page">
        <div className="brd-review-container">
          {/* Header */}
          <div className="review-header">
            <div className="header-left">
              <CheckCircle size={24} className="success-icon" />
              <div>
                <h1>BRD Generated Successfully</h1>
                <p>{generatedBRD.title}</p>
              </div>
              {/* Mode Badge */}
              <span className={`mode-badge ${verificationInfo?.mode || 'draft'}`}>
                {isVerifiedMode ? <ShieldCheck size={14} /> : <Zap size={14} />}
                {isVerifiedMode ? 'Verified' : 'Draft'}
              </span>
            </div>
            <div className="header-actions">
              {/* Save status indicator */}
              {isSaving && (
                <span className="save-status saving">
                  <Loader2 size={14} className="spin" />
                  Saving...
                </span>
              )}
              {savedBRD && !isSaving && (
                <span className="save-status saved">
                  <CheckCircle size={14} />
                  Saved as {savedBRD.brd_number}
                </span>
              )}
              {saveError && (
                <span className="save-status error">
                  <AlertCircle size={14} />
                  {saveError}
                </span>
              )}
              <button className="btn btn-outline" onClick={handleReset}>
                <RefreshCw size={16} />
                Generate Another
              </button>
              {savedBRD && (
                <button className="btn btn-outline" onClick={handleViewInLibrary}>
                  <Library size={16} />
                  View in Library
                </button>
              )}
              <div className="download-dropdown">
                <button className="btn btn-secondary" onClick={() => handleDownload('md')}>
                  <Download size={16} />
                  Download MD
                </button>
                <button className="btn btn-secondary" onClick={() => handleDownload('html')}>
                  <FileCode size={16} />
                  Download HTML
                </button>
              </div>
              <button className="btn btn-primary" onClick={handleCreateEPIC}>
                Create EPIC
                <ArrowRight size={16} />
              </button>
            </div>
          </div>

          {/* BRD Metadata */}
          <div className="brd-metadata">
            <div className="metadata-item">
              <span className="label">Document ID</span>
              <span className="value">{generatedBRD.id}</span>
            </div>
            <div className="metadata-item">
              <span className="label">Version</span>
              <span className="value">{generatedBRD.version}</span>
            </div>
            <div className="metadata-item">
              <span className="label">Created</span>
              <span className="value">{new Date(generatedBRD.created_at).toLocaleString()}</span>
            </div>
            <div className="metadata-item">
              <span className="label">Repository</span>
              <span className="value">{selectedRepo?.name}</span>
            </div>
            {verificationInfo && (
              <>
                <div className="metadata-item">
                  <span className="label">Mode</span>
                  <span className={`value mode-${verificationInfo.mode}`}>
                    {verificationInfo.mode === 'verified' ? 'Verified' : 'Draft'}
                  </span>
                </div>
                <div className="metadata-item">
                  <span className="label">Verified</span>
                  <span className={`value ${verificationInfo.is_verified ? 'verified' : 'unverified'}`}>
                    {verificationInfo.is_verified ? 'Yes' : 'No'}
                  </span>
                </div>
                <div className="metadata-item">
                  <span className="label">Confidence</span>
                  <span className="value">{(verificationInfo.confidence_score * 100).toFixed(0)}%</span>
                </div>
              </>
            )}
          </div>

          {/* Verification Report Section (only for verified mode) */}
          {isVerifiedMode && report && (
            <div className="verification-report-section">
              <div
                className="verification-report-header"
                onClick={() => setShowVerificationReport(!showVerificationReport)}
              >
                <div className="header-left">
                  <ShieldCheck size={20} />
                  <span>Verification Report</span>
                  <span className={`overall-status status-${report.overall_status}`}>
                    {report.overall_status.replace('_', ' ')}
                  </span>
                </div>
                <div className="header-right">
                  <span className="verification-summary">
                    {report.verified_claims}/{report.total_claims} claims verified ({report.verification_rate.toFixed(0)}%)
                  </span>
                  {showVerificationReport ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                </div>
              </div>

              {showVerificationReport && (
                <div className="verification-report-content">
                  {/* Overall Summary */}
                  <div className="verification-summary-grid">
                    <div className="summary-card">
                      <span className="summary-label">Overall Confidence</span>
                      {renderConfidenceBar(report.overall_confidence)}
                    </div>
                    <div className="summary-card">
                      <span className="summary-label">Verification Rate</span>
                      {renderConfidenceBar(report.verification_rate / 100)}
                    </div>
                    <div className="summary-card">
                      <span className="summary-label">SME Review Needed</span>
                      <span className="summary-value">{report.claims_needing_sme} claims</span>
                    </div>
                  </div>

                  {/* Claims Statistics */}
                  <div className="claims-statistics">
                    <h4>Claim Statistics</h4>
                    <div className="claims-stats-grid">
                      <div className="claim-stat verified">
                        <CheckCircle size={16} />
                        <span className="count">{report.verified_claims}</span>
                        <span className="label">Verified</span>
                      </div>
                      <div className="claim-stat partial">
                        <AlertCircle size={16} />
                        <span className="count">{report.partially_verified_claims}</span>
                        <span className="label">Partial</span>
                      </div>
                      <div className="claim-stat unverified">
                        <AlertCircle size={16} />
                        <span className="count">{report.unverified_claims}</span>
                        <span className="label">Unverified</span>
                      </div>
                      <div className="claim-stat contradicted">
                        <X size={16} />
                        <span className="count">{report.contradicted_claims}</span>
                        <span className="label">Contradicted</span>
                      </div>
                    </div>
                  </div>

                  {/* Per-Section Breakdown */}
                  <div className="sections-breakdown">
                    <h4>Section Breakdown</h4>
                    {report.sections.map((section, index) => (
                      <div key={index} className="section-report">
                        <div className="section-header">
                          <span className="section-name">{section.section_name}</span>
                          {renderStatusBadge(section.status)}
                          <span className="section-stats">
                            {section.verified_claims}/{section.total_claims} verified
                          </span>
                        </div>
                        <div className="section-confidence">
                          {renderConfidenceBar(section.confidence)}
                        </div>

                        {/* Claims in this section */}
                        {section.claims && section.claims.length > 0 && (
                          <div className="section-claims">
                            {section.claims.map((claim, claimIndex) => (
                              <div key={claimIndex} className={`claim-item ${claim.status}`}>
                                <div className="claim-header">
                                  {renderStatusBadge(claim.status)}
                                  <span className="claim-confidence">
                                    {(claim.confidence * 100).toFixed(0)}%
                                  </span>
                                  {claim.needs_sme_review && (
                                    <span className="sme-badge">
                                      <Eye size={12} />
                                      SME Review
                                    </span>
                                  )}
                                </div>
                                <p className="claim-text">{claim.claim_text}</p>

                                {/* Verification Summary */}
                                {claim.verification_summary && (
                                  <p className="verification-summary">{claim.verification_summary}</p>
                                )}

                                {/* Code Evidence - Shows actual code that implements the claim */}
                                {claim.code_references && claim.code_references.length > 0 && (
                                  <CodeEvidencePanel
                                    references={claim.code_references}
                                    claimId={claim.claim_id}
                                  />
                                )}

                                <div className="claim-meta">
                                  <span className="evidence-count">
                                    {claim.evidence_count} evidence items
                                  </span>
                                  {claim.evidence_types.length > 0 && (
                                    <span className="evidence-types">
                                      ({claim.evidence_types.join(', ')})
                                    </span>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Draft Mode Warning */}
          {!isVerifiedMode && (
            <div className="draft-warning">
              <AlertCircle size={18} />
              <div>
                <strong>Draft Mode</strong>
                <p>This BRD was generated without verification. For production use, consider regenerating with Verified mode for claim validation and evidence gathering.</p>
              </div>
            </div>
          )}

          {/* Global Feedback Panel */}
          <div className="global-feedback-panel">
            <div className="global-feedback-header">
              <MessageSquare size={18} />
              <span>Refine Entire BRD</span>
              {refinementCount > 0 && (
                <span className="refinement-badge">{refinementCount} refinements</span>
              )}
            </div>
            <div className="global-feedback-content">
              <textarea
                placeholder="Provide feedback to refine the entire BRD (e.g., 'Make requirements more specific', 'Add more technical details')"
                value={globalFeedback}
                onChange={(e) => setGlobalFeedback(e.target.value)}
                rows={3}
                disabled={isRefining}
              />
              <div className="global-feedback-actions">
                <button
                  className="btn btn-secondary"
                  onClick={handleShowHistory}
                  disabled={isRefining}
                >
                  <History size={16} />
                  View History
                </button>
                <button
                  className="btn btn-primary"
                  onClick={handleGlobalRefine}
                  disabled={isRefining || !globalFeedback.trim()}
                >
                  {isRefining && !refiningSection ? (
                    <Loader2 size={16} className="spin" />
                  ) : (
                    <Send size={16} />
                  )}
                  Apply Feedback
                </button>
              </div>
            </div>
          </div>

          {/* BRD Content Editor with Section Refinement */}
          <div className="brd-editor">
            <div className="editor-header">
              <FileText size={20} />
              <span>Business Requirements Document</span>
              <div className="editor-actions">
                {refinementCount > 0 && (
                  <span className="version-badge">v{refinementCount + 1}</span>
                )}
              </div>
            </div>
            <div className="editor-content-sections">
              {parseBRDSections(generatedBRD.markdown).map((section, index) => (
                <div key={index} className="brd-section">
                  <div className="section-header-row">
                    <h2>{section.name}</h2>
                    <button
                      className={`section-feedback-btn ${showFeedbackFor === section.name ? 'active' : ''}`}
                      onClick={() => setShowFeedbackFor(showFeedbackFor === section.name ? null : section.name)}
                      title="Provide feedback to refine this section"
                    >
                      <Edit3 size={14} />
                      Refine
                    </button>
                  </div>

                  {showFeedbackFor === section.name && (
                    <div className="section-feedback-panel">
                      <textarea
                        placeholder={`How should the "${section.name}" section be improved?`}
                        value={sectionFeedback[section.name] || ''}
                        onChange={(e) => setSectionFeedback(prev => ({
                          ...prev,
                          [section.name]: e.target.value,
                        }))}
                        rows={2}
                        disabled={isRefining}
                      />
                      <div className="section-feedback-actions">
                        <button
                          className="btn btn-sm btn-outline"
                          onClick={() => setShowFeedbackFor(null)}
                          disabled={isRefining}
                        >
                          Cancel
                        </button>
                        <button
                          className="btn btn-sm btn-primary"
                          onClick={() => handleSectionRefine(section.name)}
                          disabled={isRefining || !(sectionFeedback[section.name]?.trim())}
                        >
                          {refiningSection === section.name ? (
                            <>
                              <Loader2 size={14} className="spin" />
                              Refining...
                            </>
                          ) : (
                            <>
                              <Sparkles size={14} />
                              Refine Section
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="section-content markdown-body">
                    <ReactMarkdown>{section.content}</ReactMarkdown>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* History Sidebar */}
          {showHistory && (
            <div className="history-sidebar">
              <div className="history-header">
                <History size={20} />
                <span>Refinement History</span>
                <button className="close-btn" onClick={() => setShowHistory(false)}>
                  <X size={18} />
                </button>
              </div>
              <div className="history-content">
                {artifactHistory.length === 0 ? (
                  <div className="history-empty">
                    <p>No history available yet.</p>
                    <p className="hint">History will appear after refinements are made.</p>
                  </div>
                ) : (
                  <div className="history-timeline">
                    {artifactHistory.map((entry) => (
                      <div key={entry.id} className={`history-entry ${entry.action}`}>
                        <div className="entry-version">v{entry.version}</div>
                        <div className="entry-details">
                          <div className="entry-action">
                            {entry.action === 'created' ? 'Created' : 'Refined'}
                            {entry.feedback_scope === 'section' && entry.feedback_target && (
                              <span className="entry-target">: {entry.feedback_target}</span>
                            )}
                          </div>
                          {entry.user_feedback && (
                            <div className="entry-feedback">
                              "{entry.user_feedback.slice(0, 100)}
                              {entry.user_feedback.length > 100 ? '...' : ''}"
                            </div>
                          )}
                          {entry.changes_summary && (
                            <div className="entry-summary">{entry.changes_summary}</div>
                          )}
                          <div className="entry-time">
                            {new Date(entry.created_at).toLocaleString()}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Error Display */}
          {error && (
            <div className="refinement-error">
              <AlertCircle size={16} />
              <span>{error}</span>
              <button onClick={() => setError(null)}>
                <X size={14} />
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Generation in progress - show thinking process
  if (isGenerating || isCancelled) {
    return (
      <div className="generate-brd-page">
        <div className="generation-container">
          <div className="generation-header">
            {isCancelled ? (
              <StopCircle size={32} className="stop-icon" />
            ) : (
              <Brain size={32} className="brain-icon pulse" />
            )}
            <div>
              <h1>{isCancelled ? 'Generation Stopped' : 'Generating BRD'}</h1>
              <p>
                {isCancelled
                  ? 'BRD generation was stopped. You can start a new generation or review the partial progress below.'
                  : 'Analyzing codebase and creating your Business Requirements Document...'}
              </p>
            </div>
            <div className="generation-actions">
              {isGenerating && (
                <button
                  className="btn btn-danger btn-stop"
                  onClick={handleStopGeneration}
                  title="Stop generation"
                >
                  <StopCircle size={18} />
                  Stop Generation
                </button>
              )}
              {isCancelled && (
                <button
                  className="btn btn-primary"
                  onClick={handleReset}
                >
                  <RefreshCw size={18} />
                  Start Over
                </button>
              )}
            </div>
          </div>

          {/* Progress Stats Panel */}
          {mode === 'verified' && (progressStats.totalSections > 0 || progressStats.currentPhase !== 'initializing') && (
            <div className="progress-stats-panel">
              <div className="progress-stats-header">
                <Shield size={18} />
                <span>Verification Progress</span>
              </div>
              <div className="progress-stats-content">
                {/* Phase indicator */}
                <div className="progress-phase">
                  <span className="phase-label">Phase:</span>
                  <span className={`phase-value phase-${progressStats.currentPhase}`}>
                    {progressStats.currentPhase === 'initializing' && '🚀 Initializing'}
                    {progressStats.currentPhase === 'gathering_context' && '📊 Gathering Context'}
                    {progressStats.currentPhase === 'generating' && '📝 Generating Sections'}
                    {progressStats.currentPhase === 'verifying' && '🔬 Verifying Claims'}
                    {progressStats.currentPhase === 'complete' && '✅ Complete'}
                  </span>
                </div>

                {/* Section progress */}
                {progressStats.totalSections > 0 && (
                  <div className="progress-item">
                    <div className="progress-item-header">
                      <FileCode size={14} />
                      <span>Sections</span>
                      <span className="progress-count">
                        {progressStats.sectionsCompleted}/{progressStats.totalSections}
                      </span>
                    </div>
                    <div className="progress-bar">
                      <div
                        className="progress-bar-fill sections"
                        style={{ width: `${(progressStats.sectionsCompleted / progressStats.totalSections) * 100}%` }}
                      />
                    </div>
                    {progressStats.currentSection && (
                      <div className="current-item">
                        Current: <strong>{progressStats.currentSection}</strong>
                      </div>
                    )}
                  </div>
                )}

                {/* Claims progress */}
                {progressStats.totalClaims > 0 && (
                  <div className="progress-item">
                    <div className="progress-item-header">
                      <ShieldCheck size={14} />
                      <span>Claims Verified</span>
                      <span className="progress-count">
                        {progressStats.claimsVerified}/{progressStats.totalClaims}
                      </span>
                    </div>
                    <div className="progress-bar">
                      <div
                        className="progress-bar-fill claims"
                        style={{ width: `${(progressStats.claimsVerified / progressStats.totalClaims) * 100}%` }}
                      />
                    </div>
                    <div className="verification-rate">
                      Verification rate: <strong>{((progressStats.claimsVerified / progressStats.totalClaims) * 100).toFixed(0)}%</strong>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Thinking Process */}
          <div className="thinking-section">
            <div className="thinking-header">
              <Sparkles size={18} />
              <span>Thinking Process</span>
            </div>
            <div className="thinking-container" ref={thinkingContainerRef}>
              {thinkingSteps.map((step) => {
                // Check if content starts with an emoji (unicode ranges for common emojis)
                const hasEmoji = /^[\u{1F300}-\u{1F9FF}|\u{2600}-\u{26FF}|\u{2700}-\u{27BF}]/u.test(step.content);
                return (
                  <div key={step.id} className={`thinking-step ${step.category ? `category-${step.category}` : ''}`}>
                    {!hasEmoji && <div className="thinking-dot"></div>}
                    <span className="thinking-content">{step.content}</span>
                  </div>
                );
              })}
              {isGenerating && (
                <div className="thinking-step active">
                  <Loader2 size={14} className="spin" />
                  <span className="thinking-content">Processing...</span>
                </div>
              )}
            </div>
          </div>

          {/* Streaming Content Preview */}
          {streamedContent && (
            <div className="streaming-preview">
              <div className="streaming-header">
                <FileText size={18} />
                <span>Document Preview</span>
              </div>
              <div className="streaming-content">
                <pre>{streamedContent}</pre>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Library View
  // Compute status counts
  const statusCounts = {
    all: brds.length,
    draft: brds.filter(b => b.status === 'draft').length,
    approved: brds.filter(b => b.status === 'approved').length,
  };

  if (viewMode === 'library') {
    return (
      <div className="generate-brd-page library-view">
        {/* Header */}
        <div className="library-header">
          <div className="header-left">
            <FileText size={28} />
            <div>
              <h1>Business Requirements Documents</h1>
              <p>Manage your BRDs and generate new ones</p>
            </div>
          </div>
          <div className="header-actions">
            <button className="btn btn-primary" onClick={() => setViewMode('generate')}>
              <Plus size={16} />
              Generate New BRD
            </button>
          </div>
        </div>

        {/* Toolbar - matches EPIC screen */}
        <div className="library-toolbar">
          <div className="toolbar-left">
            {/* Status Filter Tabs */}
            <div className="filter-tabs">
              <button
                className={`filter-btn ${selectedStatusFilter === '' ? 'active' : ''}`}
                onClick={() => setSelectedStatusFilter('')}
              >
                All ({statusCounts.all})
              </button>
              <button
                className={`filter-btn ${selectedStatusFilter === 'draft' ? 'active' : ''}`}
                onClick={() => setSelectedStatusFilter('draft')}
              >
                <FileText size={14} />
                Draft ({statusCounts.draft})
              </button>
              <button
                className={`filter-btn completed ${selectedStatusFilter === 'approved' ? 'active' : ''}`}
                onClick={() => setSelectedStatusFilter('approved')}
              >
                <ShieldCheck size={14} />
                Approved ({statusCounts.approved})
              </button>
            </div>

            {/* Repository Filter */}
            {repositories && repositories.length > 0 && (
              <select
                className="filter-select"
                value={selectedRepoFilter}
                onChange={(e) => setSelectedRepoFilter(e.target.value)}
              >
                <option value="">All Repositories</option>
                {repositories?.map((repo: RepositorySummary) => (
                  <option key={repo.id} value={repo.id}>
                    {repo.name}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="toolbar-right">
            <input
              type="text"
              placeholder="Search BRDs..."
              value={librarySearchQuery}
              onChange={(e) => setLibrarySearchQuery(e.target.value)}
              className="search-input"
            />
            <button
              className="btn btn-outline refresh-btn"
              onClick={() => refetchBRDs()}
              disabled={isLoadingBRDs}
            >
              <RefreshCw size={16} className={isLoadingBRDs ? 'spinning' : ''} />
              Refresh
            </button>
          </div>
        </div>

        {/* Content */}
        {brdsError ? (
          <div className="error-state">
            <AlertCircle size={48} />
            <h3>Failed to load BRDs</h3>
            <p>{(brdsError as Error).message}</p>
            <button className="btn btn-primary" onClick={() => refetchBRDs()}>
              <RefreshCw size={16} />
              Retry
            </button>
          </div>
        ) : isLoadingBRDs ? (
          <div className="loading-state">
            <RefreshCw size={32} className="spin" />
            <p>Loading BRDs...</p>
          </div>
        ) : brds.length === 0 ? (
          <div className="empty-state">
            <FileText size={64} />
            <h3>No BRDs yet</h3>
            <p>Generate your first Business Requirements Document to get started.</p>
            <button className="btn btn-primary" onClick={() => setViewMode('generate')}>
              <Plus size={16} />
              Generate BRD
            </button>
          </div>
        ) : (
          <div className="brd-table-container">
            <table className="brd-table">
              <thead>
                <tr>
                  <th className="col-expand"></th>
                  <th className="col-brd">BRD</th>
                  <th className="col-repo">Repository</th>
                  <th className="col-status">Status</th>
                  <th className="col-epics">EPICs</th>
                  <th className="col-backlogs">Backlogs</th>
                  <th className="col-date">Created</th>
                  <th className="col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
            {brds.map((brd) => (
              <>
                <tr key={brd.id} className={`brd-row ${expandedBRDs.has(brd.id) ? 'expanded' : ''}`}>
                  <td className="col-expand">
                    <button
                      className="expand-btn"
                      onClick={() => toggleBRDExpanded(brd.id)}
                      disabled={brd.epic_count === 0}
                    >
                      {expandedBRDs.has(brd.id) ? (
                        <ChevronDown size={16} />
                      ) : (
                        <ChevronRight size={16} />
                      )}
                    </button>
                  </td>
                  <td className="col-brd">
                    <div className="brd-cell">
                      <span className="brd-number">{brd.brd_number}</span>
                      <span className="brd-title">{brd.title}</span>
                      {brd.mode === 'verified' && (
                        <span className="verified-badge" title="Verified with code evidence">
                          <CheckCircle size={12} />
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="col-repo">
                    <span className="repo-name">{brd.repository_name || 'Unknown'}</span>
                  </td>
                  <td className="col-status">
                    <span className={`status-badge ${statusConfig[brd.status]?.className || ''}`}>
                      {statusConfig[brd.status]?.icon}
                      {statusConfig[brd.status]?.label || brd.status}
                    </span>
                  </td>
                  <td className="col-epics">
                    <span className="count-badge epics">
                      <Layers size={12} />
                      {brd.epic_count}
                    </span>
                  </td>
                  <td className="col-backlogs">
                    <span className="count-badge backlogs">
                      <ListTodo size={12} />
                      {brd.backlog_count}
                    </span>
                  </td>
                  <td className="col-date">
                    <span className="date-text">{formatDate(brd.created_at)}</span>
                  </td>
                  <td className="col-actions">
                    <div className="action-menu-container">
                      <button
                        className="action-menu-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          setActionMenuOpen(actionMenuOpen === brd.id ? null : brd.id);
                        }}
                      >
                        <MoreVertical size={16} />
                      </button>
                      {actionMenuOpen === brd.id && (
                        <div className="action-menu" onClick={(e) => e.stopPropagation()}>
                          <button onClick={() => handleViewBRD(brd)}>
                            <Eye size={14} />
                            View BRD
                          </button>
                          {brd.status === 'approved' && (
                            <button onClick={() => handleGenerateEpicsFromBRD(brd)}>
                              <Layers size={14} />
                              Generate EPICs
                            </button>
                          )}
                          <hr />
                          <button onClick={() => handleDownloadBRD(brd, 'md')}>
                            <Download size={14} />
                            Download MD
                          </button>
                          <hr />
                          <button className="danger" onClick={() => handleDeleteBRD(brd.id)}>
                            <Trash2 size={14} />
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>

                {/* Expanded EPICs */}
                {expandedBRDs.has(brd.id) && brd.epics && brd.epics.length > 0 && (
                  <tr className="expanded-row">
                    <td colSpan={8}>
                      <div className="epics-container">
                        {brd.epics.map((epic) => (
                          <div key={epic.id} className="epic-row-group">
                            <div className={`epic-row ${expandedEpics.has(epic.id) ? 'expanded' : ''}`}>
                              <div className="col-expand">
                                <button
                                  className="expand-btn"
                                  onClick={() => toggleEpicExpanded(epic.id)}
                                  disabled={epic.backlog_count === 0}
                                >
                                  {expandedEpics.has(epic.id) ? (
                                    <ChevronDown size={14} />
                                  ) : (
                                    <ChevronRight size={14} />
                                  )}
                                </button>
                              </div>
                              <div className="epic-info">
                                <Layers size={14} />
                                <span className="epic-number">{epic.epic_number}</span>
                                <span className="epic-title">{epic.title}</span>
                              </div>
                              <div className="epic-meta">
                                <span className="count-badge backlogs">
                                  <ListTodo size={12} />
                                  {epic.backlog_count}
                                </span>
                              </div>
                            </div>

                            {/* Expanded Backlogs */}
                            {expandedEpics.has(epic.id) && epic.backlogs && epic.backlogs.length > 0 && (
                              <div className="backlogs-container">
                                {epic.backlogs.map((backlog) => (
                                  <div key={backlog.id} className="backlog-row">
                                    <div className="backlog-info">
                                      <ListTodo size={12} />
                                      <span className="backlog-number">{backlog.backlog_number}</span>
                                      <span className="backlog-type">{backlog.item_type}</span>
                                      <span className="backlog-title">{backlog.title}</span>
                                    </div>
                                    <div className="backlog-meta">
                                      <span className={`priority-badge ${priorityColors[backlog.priority]}`}>
                                        {backlog.priority}
                                      </span>
                                      {backlog.story_points && (
                                        <span className="points-badge">{backlog.story_points} pts</span>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  // View Mode - View existing BRD details with approval workflow
  if (viewMode === 'view' && viewedBRD) {
    const isDraft = viewedBRD.status === 'draft';
    const isApproved = viewedBRD.status === 'approved';

    return (
      <div className="generate-brd-page view-mode">
        {/* Back Button */}
        <button className="btn btn-outline back-to-list-btn" onClick={() => {
          if (isEditing) {
            handleCancelEdit();
          }
          setViewedBRD(null);
          setViewMode('library');
        }}>
          <ArrowLeft size={16} />
          Back to BRD Library
        </button>

        {/* BRD Detail Header */}
        <div className="brd-detail-header">
          <div className="brd-detail-title-section">
            <h1>{viewedBRD.title}</h1>
            <div className="brd-detail-meta">
              <span className="brd-id-badge">{viewedBRD.brd_number}</span>
              <span className={`status-badge ${viewedBRD.status}`}>
                {viewedBRD.status.charAt(0).toUpperCase() + viewedBRD.status.slice(1)}
              </span>
              {viewedBRD.mode === 'verified' && (
                <span className="verified-indicator">
                  <ShieldCheck size={14} />
                  Verified
                </span>
              )}
              {isEditing && (
                <span className="editing-indicator">
                  <Edit3 size={14} />
                  Editing
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Action Bar */}
        <div className="brd-action-bar">
          <div className="action-bar-left">
            <span className="repo-info">
              <FolderGit2 size={16} />
              {viewedBRD.repository_name || 'Unknown Repository'}
            </span>
            <span className="date-info">
              <Clock size={16} />
              Created {formatDate(viewedBRD.created_at)}
            </span>
          </div>
          <div className="action-bar-right">
            {isEditing ? (
              // Edit mode actions
              <>
                <button className="btn btn-outline" onClick={handleCancelEdit}>
                  <X size={16} />
                  Cancel
                </button>
                <button
                  className="btn btn-primary"
                  onClick={handleSaveEdit}
                  disabled={isSaving}
                >
                  {isSaving ? (
                    <>
                      <Loader2 size={16} className="spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <CheckCircle size={16} />
                      Save Changes
                    </>
                  )}
                </button>
              </>
            ) : (
              // View mode actions
              <>
                {isDraft && (
                  <>
                    <button className="btn btn-outline" onClick={handleEditBRD}>
                      <Edit3 size={16} />
                      Edit
                    </button>
                    <button
                      className="btn btn-primary"
                      onClick={handleApproveAndContinue}
                      disabled={isApproving}
                    >
                      {isApproving ? (
                        <>
                          <Loader2 size={16} className="spin" />
                          Approving...
                        </>
                      ) : (
                        <>
                          <CheckCircle size={16} />
                          Approve & Continue to EPICs
                        </>
                      )}
                    </button>
                  </>
                )}
                {isApproved && (
                  <button
                    className="btn btn-primary"
                    onClick={() => navigate(`/generate-epic?brd_id=${viewedBRD.id}`)}
                  >
                    <Layers size={16} />
                    Generate EPICs
                  </button>
                )}
                <button className="btn btn-outline" onClick={() => handleDownloadBRD(viewedBRD, 'md')}>
                  <Download size={16} />
                  Download MD
                </button>
                <button className="btn btn-outline" onClick={() => handleDownloadDOCX(viewedBRD)}>
                  <Download size={16} />
                  Download DOCX
                </button>
              </>
            )}
          </div>
        </div>

        {/* Main Content */}
        <div className="brd-view-content">
          {/* BRD Content */}
          <div className="brd-content-section">
            {isEditing ? (
              // Edit mode - Section by section editing with AI refinement
              <div className="brd-sections edit-mode">
                {editingSections.map((section, index) => (
                  <div key={index} className="brd-section editable">
                    <div className="section-header-row">
                      <h2 className="section-title">
                        <FileText size={18} />
                        {section.name}
                      </h2>
                      <button
                        className={`btn btn-sm btn-outline refine-btn ${refiningSectionIndex === index ? 'active' : ''}`}
                        onClick={() => {
                          if (refiningSectionIndex === index) {
                            setRefiningSectionIndex(null);
                            setSectionRefineFeedback('');
                          } else {
                            setRefiningSectionIndex(index);
                            setSectionRefineFeedback('');
                          }
                        }}
                      >
                        <Sparkles size={14} />
                        AI Refine
                      </button>
                    </div>

                    {/* AI Refinement Input */}
                    {refiningSectionIndex === index && (
                      <div className="section-refinement-input">
                        <textarea
                          value={sectionRefineFeedback}
                          onChange={(e) => setSectionRefineFeedback(e.target.value)}
                          placeholder="Describe how you'd like this section to be refined..."
                          rows={2}
                        />
                        <div className="refinement-actions">
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={() => handleRefineSectionWithAI(index)}
                            disabled={isRefiningSection || !sectionRefineFeedback.trim()}
                          >
                            {isRefiningSection ? <Loader2 size={14} className="spin" /> : <Send size={14} />}
                            Refine with AI
                          </button>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => {
                              setRefiningSectionIndex(null);
                              setSectionRefineFeedback('');
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}

                    <textarea
                      className="section-editor"
                      value={section.content}
                      onChange={(e) => handleSectionContentChange(index, e.target.value)}
                      rows={Math.max(5, section.content.split('\n').length + 2)}
                    />
                  </div>
                ))}
              </div>
            ) : (
              // View mode - Display sections like EPIC details page with AI refine capability
              <div className="brd-detail-content">
                {(() => {
                  const sections = viewedBRD.sections && viewedBRD.sections.length > 0
                    ? viewedBRD.sections
                    : parseMarkdownIntoSections(viewedBRD.markdown_content || '');

                  return sections.length > 0 ? (
                    sections.map((section, index) => (
                      <div key={index} className="brd-detail-section">
                        <div className="section-header-row">
                          <h3>
                            <FileText size={18} />
                            {section.name}
                          </h3>
                          <button
                            className={`btn btn-sm btn-outline refine-btn ${refiningSectionIndex === index ? 'active' : ''}`}
                            onClick={() => {
                              if (refiningSectionIndex === index) {
                                setRefiningSectionIndex(null);
                                setSectionRefineFeedback('');
                              } else {
                                setRefiningSectionIndex(index);
                                setSectionRefineFeedback('');
                              }
                            }}
                          >
                            <Sparkles size={14} />
                            AI Refine
                          </button>
                        </div>

                        {/* AI Refinement Input */}
                        {refiningSectionIndex === index && (
                          <div className="section-refinement-input">
                            <textarea
                              value={sectionRefineFeedback}
                              onChange={(e) => setSectionRefineFeedback(e.target.value)}
                              placeholder="Describe how you'd like this section to be refined..."
                              rows={2}
                            />
                            <div className="refinement-actions">
                              <button
                                className="btn btn-primary btn-sm"
                                onClick={() => handleRefineViewSectionWithAI(index, sections)}
                                disabled={isRefiningSection || !sectionRefineFeedback.trim()}
                              >
                                {isRefiningSection ? <Loader2 size={14} className="spin" /> : <Send size={14} />}
                                Refine with AI
                              </button>
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => {
                                  setRefiningSectionIndex(null);
                                  setSectionRefineFeedback('');
                                }}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        )}

                        <div className="section-content">
                          <ReactMarkdown>{section.content}</ReactMarkdown>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="brd-detail-section">
                      <div className="section-content">
                        <ReactMarkdown>{viewedBRD.markdown_content}</ReactMarkdown>
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}
          </div>

          {/* EPICs Grid - Show at bottom if there are EPICs and not editing */}
          {!isEditing && viewedBRD.epics && viewedBRD.epics.length > 0 && (
            <div className="linked-epics-section">
              <div className="section-header">
                <h3>
                  <Layers size={18} />
                  EPICs ({viewedBRD.epics.length})
                </h3>
              </div>
              <div className="epics-table-container">
                <table className="epics-table">
                  <thead>
                    <tr>
                      <th className="col-status">Status</th>
                      <th className="col-epic-id">EPIC ID</th>
                      <th className="col-title">Title</th>
                      <th className="col-backlogs">Backlogs</th>
                      <th className="col-updated">Updated</th>
                      <th className="col-actions">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {viewedBRD.epics.map((epic: StoredEpic) => (
                      <tr key={epic.id} className="epic-row">
                        <td className="col-status">
                          <span className={`status-badge ${epic.status}`}>
                            {epic.status === 'draft' && <FileText size={12} />}
                            {epic.status === 'approved' && <CheckCircle size={12} />}
                            {epic.status}
                          </span>
                        </td>
                        <td className="col-epic-id">
                          <span className="epic-number">{epic.epic_number}</span>
                        </td>
                        <td className="col-title">{epic.title}</td>
                        <td className="col-backlogs">
                          <span className="count-badge">
                            <ListTodo size={12} />
                            {epic.backlog_count || 0}
                          </span>
                        </td>
                        <td className="col-updated">
                          {epic.updated_at ? formatDate(epic.updated_at) : '-'}
                        </td>
                        <td className="col-actions">
                          <button
                            className="btn btn-sm btn-outline"
                            onClick={() => navigate(`/generate-epic?epic_id=${epic.id}`)}
                          >
                            <Eye size={14} />
                            View
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Generate View
  return (
    <div className="generate-brd-page">
      <div className="page-header with-back">
        <button className="btn btn-ghost back-to-library" onClick={() => setViewMode('library')}>
          <ArrowLeft size={20} />
          Back to Library
        </button>
        <h1>Generate Business Requirements Document</h1>
        <p>Select a repository with completed analysis and describe the feature to generate a BRD</p>
      </div>

      <div className="brd-form-container single-column">
        <div className="card">
          <div className="card-body">
            {/* Repository Selection */}
            <div className="form-group">
              <label htmlFor="repository">
                <FolderGit2 size={16} />
                Select Repository
              </label>
              <div className="dropdown-container">
                <button
                  type="button"
                  className={`dropdown-trigger ${dropdownOpen ? 'open' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    setDropdownOpen(!dropdownOpen);
                  }}
                  disabled={isLoadingRepos}
                >
                  {isLoadingRepos ? (
                    <span className="loading-text">
                      <Loader2 size={16} className="spin" />
                      Loading repositories...
                    </span>
                  ) : selectedRepo ? (
                    <span className="selected-repo">
                      <span className="repo-name">{selectedRepo.name}</span>
                      <span className="repo-url">{selectedRepo.url}</span>
                    </span>
                  ) : (
                    <span className="placeholder">Select a repository with completed analysis</span>
                  )}
                  <ChevronDown size={20} className={`chevron ${dropdownOpen ? 'rotated' : ''}`} />
                </button>

                {dropdownOpen && (
                  <div className="dropdown-menu">
                    {reposError ? (
                      <div className="dropdown-error">
                        <AlertCircle size={16} />
                        <span>Failed to load repositories</span>
                        <button onClick={() => refetchRepos()}>Retry</button>
                      </div>
                    ) : repositories && repositories.length > 0 ? (
                      repositories.map((repo) => (
                        <button
                          key={repo.id}
                          className={`dropdown-item ${selectedRepo?.id === repo.id ? 'selected' : ''}`}
                          onClick={() => {
                            setSelectedRepo(repo);
                            setDropdownOpen(false);
                          }}
                        >
                          <FolderGit2 size={16} />
                          <div className="repo-details">
                            <span className="repo-name">{repo.name}</span>
                            <span className="repo-meta">
                              {repo.platform} • {repo.default_branch}
                              {repo.last_analyzed_at && (
                                <> • Analyzed {new Date(repo.last_analyzed_at).toLocaleDateString()}</>
                              )}
                            </span>
                          </div>
                          {selectedRepo?.id === repo.id && <CheckCircle size={16} className="check-icon" />}
                        </button>
                      ))
                    ) : (
                      <div className="dropdown-empty">
                        <AlertCircle size={16} />
                        <span>No repositories with completed analysis found</span>
                        <p>Please onboard and analyze a repository first</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Generation Mode Toggle */}
            <div className="form-group">
              <label>
                <Shield size={16} />
                Generation Mode
              </label>
              <div className="mode-toggle-container">
                <button
                  type="button"
                  className={`mode-toggle-btn ${mode === 'draft' ? 'active' : ''}`}
                  onClick={() => setMode('draft')}
                >
                  <Zap size={18} />
                  <div className="mode-info">
                    <span className="mode-title">Draft</span>
                    <span className="mode-desc">Fast, single-pass generation</span>
                  </div>
                </button>
                <button
                  type="button"
                  className={`mode-toggle-btn ${mode === 'verified' ? 'active' : ''}`}
                  onClick={() => setMode('verified')}
                >
                  <ShieldCheck size={18} />
                  <div className="mode-info">
                    <span className="mode-title">Verified</span>
                    <span className="mode-desc">Multi-agent verification</span>
                  </div>
                </button>
              </div>
              <p className="input-hint">
                {mode === 'draft'
                  ? 'Draft mode is faster but may contain unverified claims. Good for exploration.'
                  : 'Verified mode validates claims against codebase with evidence gathering. Slower but more accurate.'}
              </p>
            </div>

            {/* Model Selection */}
            <div className="form-group">
              <label>
                <Brain size={16} />
                AI Model
              </label>
              <div className="model-selector">
                {isLoadingModels ? (
                  <div className="model-loading">
                    <Loader2 size={16} className="spin" />
                    <span>Loading models...</span>
                  </div>
                ) : (
                  <select
                    value={selectedModel}
                    onChange={(e) => setSelectedModel(e.target.value)}
                    className="model-select"
                  >
                    {availableModels.map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.name}
                        {model.is_recommended ? ' ⭐' : ''}
                        {model.is_default ? ' (Default)' : ''}
                        {model.min_tier !== 'free' ? ` [${model.min_tier}+]` : ''}
                      </option>
                    ))}
                  </select>
                )}
                {selectedModel && availableModels.length > 0 && (
                  <div className="model-info-panel">
                    {(() => {
                      const model = availableModels.find(m => m.id === selectedModel);
                      if (!model) return null;
                      return (
                        <>
                          <div className="model-provider">{model.provider}</div>
                          <div className="model-description">{model.description}</div>
                          {model.strengths.length > 0 && (
                            <div className="model-strengths">
                              {model.strengths.slice(0, 3).map((s, i) => (
                                <span key={i} className="strength-tag">{s}</span>
                              ))}
                            </div>
                          )}
                        </>
                      );
                    })()}
                  </div>
                )}
              </div>
              <p className="input-hint">
                Select the AI model to use for BRD generation. Different models have different strengths.
              </p>
            </div>

            {/* Template Upload */}
            <div className="form-group">
              <label htmlFor="template">
                <Upload size={16} />
                BRD Template
              </label>
              <div className="template-section">
                {/* Default Template Info */}
                {isUsingDefaultTemplate && !templateFile ? (
                  <div className="template-selected default-template">
                    <FileText size={20} className="file-icon" />
                    <div className="template-info">
                      <span className="template-name">
                        <CheckCircle size={14} className="default-badge" />
                        Default BRD Template
                      </span>
                      <span className="template-size">
                        {defaultTemplate ? `${(defaultTemplate.length / 1024).toFixed(1)} KB` : 'Loading...'}
                      </span>
                    </div>
                    <button
                      type="button"
                      className="download-template-btn"
                      onClick={handleDownloadTemplate}
                      title="Download template"
                    >
                      <Download size={14} />
                      Download
                    </button>
                    <label className="upload-custom-btn">
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".md,.txt"
                        onChange={handleTemplateUpload}
                        className="file-input"
                      />
                      <Upload size={14} />
                      Upload Custom
                    </label>
                  </div>
                ) : templateFile ? (
                  <div className="template-selected custom-template">
                    <FileText size={20} className="file-icon" />
                    <div className="template-info">
                      <span className="template-name">{templateFile.name}</span>
                      <span className="template-size">
                        {(templateFile.size / 1024).toFixed(1)} KB
                      </span>
                    </div>
                    <button
                      type="button"
                      className="use-default-btn"
                      onClick={handleUseDefaultTemplate}
                      title="Use default template"
                    >
                      <RefreshCw size={14} />
                      Use Default
                    </button>
                    <button
                      type="button"
                      className="remove-template"
                      onClick={handleRemoveTemplate}
                      aria-label="Remove template"
                    >
                      <X size={16} />
                    </button>
                  </div>
                ) : (
                  <div className="template-upload-area">
                    <label className="upload-label">
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".md,.txt"
                        onChange={handleTemplateUpload}
                        className="file-input"
                      />
                      <Upload size={24} className="upload-icon" />
                      <span className="upload-text">
                        Drop your template here or <span className="browse-link">browse</span>
                      </span>
                      <span className="upload-hint">Supports .md and .txt files</span>
                    </label>
                  </div>
                )}

                {/* Template Preview Toggle */}
                {templateContent && (
                  <details className="template-preview">
                    <summary>
                      <Eye size={14} />
                      Preview Template ({templateContent.split('\n').length} lines)
                    </summary>
                    <pre className="template-content">{templateContent}</pre>
                  </details>
                )}
              </div>
              <p className="input-hint">
                {isUsingDefaultTemplate
                  ? 'Using the default template with standard sections. Upload a custom template to override.'
                  : 'Custom template uploaded. Click "Use Default" to revert to the standard template.'}
              </p>
            </div>

            {/* Feature Description */}
            <div className="form-group">
              <label htmlFor="featureDescription">
                <Sparkles size={16} />
                Feature Description
              </label>
              <textarea
                id="featureDescription"
                className="input textarea"
                placeholder="Describe the feature or functionality you want to document in the BRD. Be specific about the business requirements, user needs, and expected outcomes..."
                value={featureDescription}
                onChange={(e) => setFeatureDescription(e.target.value)}
                rows={6}
              />
              <p className="input-hint">
                Provide a detailed description of the feature. The more context you provide, the better the generated BRD will be.
              </p>
            </div>

            {/* Advanced Options */}
            <div className="advanced-options-section">
              <button
                type="button"
                className="advanced-options-toggle"
                onClick={() => setShowAdvancedOptions(!showAdvancedOptions)}
              >
                <Settings size={16} />
                <span>Advanced Options</span>
                {showAdvancedOptions ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>

              {showAdvancedOptions && (
                <div className="advanced-options-content">
                  {/* Detail Level */}
                  <div className="option-group">
                    <label>
                      <Info size={14} />
                      Detail Level
                    </label>
                    <select
                      value={detailLevel}
                      onChange={(e) => setDetailLevel(e.target.value as DetailLevel)}
                      className="option-select"
                    >
                      <option value="concise">Concise (1-2 paragraphs/section)</option>
                      <option value="standard">Standard (Recommended)</option>
                      <option value="detailed">Detailed (Comprehensive)</option>
                    </select>
                  </div>

                  {/* Include Similar Features */}
                  <div className="option-group checkbox-group">
                    <label>
                      <input
                        type="checkbox"
                        checked={includeSimilarFeatures}
                        onChange={(e) => setIncludeSimilarFeatures(e.target.checked)}
                      />
                      <span>Include Similar Features</span>
                    </label>
                    <span className="option-hint">
                      Search for similar features in codebase for reference
                    </span>
                  </div>

                  {/* Verified Mode Options */}
                  {mode === 'verified' && (
                    <div className="verified-options">
                      <h4>Verification Settings</h4>

                      {/* Max Iterations */}
                      <div className="option-group">
                        <label>
                          <Info size={14} />
                          Max Iterations
                          <span className="value-display">{maxIterations}</span>
                        </label>
                        <input
                          type="range"
                          min="1"
                          max="10"
                          value={maxIterations}
                          onChange={(e) => setMaxIterations(Number(e.target.value))}
                          className="option-range"
                        />
                        <span className="option-hint">
                          Maximum generator-verifier cycles (1-10)
                        </span>
                      </div>

                      {/* Min Confidence */}
                      <div className="option-group">
                        <label>
                          <Info size={14} />
                          Min Confidence
                          <span className="value-display">{(minConfidence * 100).toFixed(0)}%</span>
                        </label>
                        <input
                          type="range"
                          min="0"
                          max="100"
                          value={minConfidence * 100}
                          onChange={(e) => setMinConfidence(Number(e.target.value) / 100)}
                          className="option-range"
                        />
                        <span className="option-hint">
                          Minimum confidence score for BRD approval (0-100%)
                        </span>
                      </div>

                      {/* Show Evidence */}
                      <div className="option-group checkbox-group">
                        <label>
                          <input
                            type="checkbox"
                            checked={showEvidence}
                            onChange={(e) => setShowEvidence(e.target.checked)}
                          />
                          <Eye size={14} />
                          <span>Include Full Evidence Trail</span>
                        </label>
                        <span className="option-hint">
                          Include detailed evidence for each verified claim
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Section Length Configuration */}
                  <div className="section-config-container">
                    <button
                      type="button"
                      className="section-config-toggle"
                      onClick={() => setShowSectionConfig(!showSectionConfig)}
                    >
                      <Layers size={16} />
                      <span>Section Length Configuration</span>
                      {isParsingSections ? (
                        <span className="section-count">
                          <Loader2 size={14} className="spin" /> Parsing...
                        </span>
                      ) : (
                        <span className="section-count">{sectionConfigs.length} sections</span>
                      )}
                      {showSectionConfig ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>

                    {showSectionConfig && (
                      <div className="section-config-content">
                        <p className="section-config-hint">
                          Configure target word count for each section. Higher values = more detailed content.
                        </p>
                        {isParsingSections ? (
                          <div className="section-parsing-loading">
                            <Loader2 size={24} className="spin" />
                            <span>Analyzing template sections with AI...</span>
                          </div>
                        ) : (
                          <div className="section-config-list">
                            {sectionConfigs.map((section, index) => (
                              <div key={index} className="section-config-row">
                                <div className="section-name-col">
                                  <label className="section-name">{section.name}</label>
                                  {section.description && (
                                    <span className="section-description">{section.description}</span>
                                  )}
                                </div>
                                <div className="section-controls">
                                  <div className="section-presets">
                                    <button
                                      type="button"
                                      className={`preset-btn ${section.words === 200 ? 'active' : ''}`}
                                      onClick={() => {
                                        const newConfigs = [...sectionConfigs];
                                        newConfigs[index] = { ...section, words: 200 };
                                        setSectionConfigs(newConfigs);
                                      }}
                                    >
                                      Concise
                                    </button>
                                    <button
                                      type="button"
                                      className={`preset-btn ${section.words === 300 ? 'active' : ''}`}
                                      onClick={() => {
                                        const newConfigs = [...sectionConfigs];
                                        newConfigs[index] = { ...section, words: 300 };
                                        setSectionConfigs(newConfigs);
                                      }}
                                    >
                                      Standard
                                    </button>
                                    <button
                                      type="button"
                                      className={`preset-btn ${section.words === 500 ? 'active' : ''}`}
                                      onClick={() => {
                                        const newConfigs = [...sectionConfigs];
                                        newConfigs[index] = { ...section, words: 500 };
                                        setSectionConfigs(newConfigs);
                                      }}
                                    >
                                      Detailed
                                    </button>
                                  </div>
                                  <div className="section-words-input">
                                    <input
                                      type="number"
                                      min="100"
                                      max="1000"
                                      step="50"
                                      value={section.words}
                                      onChange={(e) => {
                                        const newConfigs = [...sectionConfigs];
                                        newConfigs[index] = {
                                          ...section,
                                          words: Math.max(100, Math.min(1000, parseInt(e.target.value) || 300))
                                        };
                                        setSectionConfigs(newConfigs);
                                      }}
                                    />
                                    <span className="words-label">words</span>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Error Message */}
            {error && (
              <div className="error-message">
                <AlertCircle size={16} />
                <span>{error}</span>
                <button className="dismiss-error" onClick={() => setError(null)}>
                  <X size={14} />
                </button>
              </div>
            )}

            {/* Generate Button */}
            <div className="form-actions">
              <button
                className={`btn btn-primary btn-lg ${mode === 'verified' ? 'verified-mode' : ''}`}
                onClick={handleGenerate}
                disabled={!selectedRepo || !featureDescription.trim() || isGenerating}
              >
                {mode === 'verified' ? <ShieldCheck size={20} /> : <Zap size={20} />}
                Generate {mode === 'verified' ? 'Verified' : 'Draft'} BRD
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
