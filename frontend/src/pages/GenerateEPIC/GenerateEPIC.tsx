import { useState, useRef, useEffect, Fragment } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Layers,
  Upload,
  FileText,
  ArrowRight,
  ArrowLeft,
  Loader2,
  CheckCircle,
  RefreshCw,
  Download,
  Trash2,
  MessageSquare,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  X,
  Send,
  Sparkles,
  GitBranch,
  Settings,
  Shield,
  ShieldCheck,
  Zap,
  Brain,
  Info,
  Edit3,
  Eye,
  Save,
  RotateCcw,
  Plus,
  Calendar,
  ListChecks,
  Target,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  FileStack,
  MoreVertical,
  Clock,
  FolderGit2,
} from 'lucide-react';
import {
  generateEpicsStream,
  refineEpic,
  getBRDDetail,
  saveEpicsForBRD,
  saveBRD,
  parseEpicTemplateFields,
  getDefaultEpicTemplate,
  analyzeBRDForEpics,
  listAvailableModels,
  getAllEpics,
  deleteEpic as deleteEpicApi,
  getRepositories,
  updateEpic,
  type Epic,
  type EpicStreamEvent,
  type GenerateEpicsRequest,
  type CoverageMatrixEntry,
  type StoredBRD,
  type StoredEpic,
  type EpicFieldConfig,
  type EpicTemplateConfig,
  type BRDAnalysisResult,
  type AnalyzeBRDRequest,
  type ModelInfo,
  type GenerationMode,
} from '../../services/api';
import mammoth from 'mammoth';
import './GenerateEPIC.css';

interface ThinkingStep {
  id: number;
  content: string;
  timestamp: Date;
}

type ViewMode = 'list' | 'create' | 'view';
type WorkflowStep = 'source' | 'generating' | 'review' | 'approved';
type StatusFilter = 'all' | 'draft' | 'approved';
type SortField = 'title' | 'brd' | 'backlogs' | 'updated';
type SortDirection = 'asc' | 'desc';

const priorityColors: Record<string, string> = {
  critical: 'badge-error',
  high: 'badge-warning',
  medium: 'badge-info',
  low: 'badge-pending',
};

export function GenerateEPIC() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const thinkingContainerRef = useRef<HTMLDivElement>(null);

  // View mode state
  const [viewMode, setViewMode] = useState<ViewMode>('list');

  // EPIC List state
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [repositoryFilter, setRepositoryFilter] = useState<string>('all');
  const [brdFilter, setBrdFilter] = useState<string>('all');
  const [sortField, setSortField] = useState<SortField>('updated');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [expandedEpicId, setExpandedEpicId] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionMenuOpen, setActionMenuOpen] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedEpicForView, setSelectedEpicForView] = useState<StoredEpic | null>(null);

  // Workflow state (for create mode)
  const [step, setStep] = useState<WorkflowStep>('source');

  // BRD source state
  const [brdContent, setBrdContent] = useState<string>(location.state?.brdContent || '');
  const [brdId, setBrdId] = useState<string>(location.state?.brdId || `BRD-${Date.now()}`);
  const [brdTitle, setBrdTitle] = useState<string>(location.state?.brdTitle || 'Business Requirements Document');

  // Database BRD state
  const [storedBRD, setStoredBRD] = useState<StoredBRD | null>(null);
  const [isLoadingBRD, setIsLoadingBRD] = useState(false);
  const [, setLoadError] = useState<string | null>(null);

  // Saved EPICs state
  const [, setSavedEpics] = useState<StoredEpic[]>([]);
  const [isSavingEpics, setIsSavingEpics] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Generation state
  const [isGenerating, setIsGenerating] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const [epics, setEpics] = useState<Epic[]>([]);
  const [, setCoverageMatrix] = useState<CoverageMatrixEntry[]>([]);
  const [uncoveredSections, setUncoveredSections] = useState<string[]>([]);
  const [recommendedOrder, setRecommendedOrder] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Refinement state
  const [refiningEpicId, setRefiningEpicId] = useState<string | null>(null);
  const [epicFeedback, setEpicFeedback] = useState<Record<string, string>>({});
  const [showFeedbackFor, setShowFeedbackFor] = useState<string | null>(null);

  // Expanded EPICs state (for create mode review)
  const [expandedEpics, setExpandedEpics] = useState<Set<string>>(new Set());

  // Editing state
  const [editingEpicId, setEditingEpicId] = useState<string | null>(null);
  const [editFormData, setEditFormData] = useState<Partial<Epic>>({});

  // View mode editing state
  const [isEditingViewEpic, setIsEditingViewEpic] = useState(false);
  const [editingViewSections, setEditingViewSections] = useState<Array<{ name: string; key: string; content: string | string[] }>>([]);
  const [isSavingViewEpic, setIsSavingViewEpic] = useState(false);
  const [isApprovingEpic, setIsApprovingEpic] = useState(false);
  const [refiningSectionIdx, setRefiningSectionIdx] = useState<number | null>(null);
  const [sectionFeedback, setSectionFeedback] = useState<string>('');
  const [isRefiningSectionAI, setIsRefiningSectionAI] = useState(false);

  // Generation mode and model state
  const [mode, setMode] = useState<GenerationMode>('draft');
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false);

  // Template configuration state
  const [epicTemplate, setEpicTemplate] = useState<string>('');
  const [defaultEpicTemplate, setDefaultEpicTemplate] = useState<string>('');
  const [isUsingDefaultTemplate, setIsUsingDefaultTemplate] = useState(true);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [isParsingTemplate, setIsParsingTemplate] = useState(false);
  const [showFieldConfig, setShowFieldConfig] = useState(false);
  const [fieldConfigs, setFieldConfigs] = useState<EpicFieldConfig[]>([
    { field_name: 'description', enabled: true, target_words: 150 },
    { field_name: 'business_value', enabled: true, target_words: 100 },
    { field_name: 'objectives', enabled: true, target_words: 50 },
    { field_name: 'acceptance_criteria', enabled: true, target_words: 30 },
  ]);
  const [detailLevel, setDetailLevel] = useState<'concise' | 'standard' | 'detailed'>('standard');
  const templateInputRef = useRef<HTMLInputElement>(null);

  // Fetch all EPICs
  const { data: epicsData, isLoading: isLoadingEpics, refetch: refetchEpics, isFetching } = useQuery({
    queryKey: ['all-epics', statusFilter, searchQuery],
    queryFn: async () => {
      const params: Record<string, string | number> = { limit: 100, offset: 0 };
      if (statusFilter !== 'all') params.status = statusFilter;
      if (searchQuery) params.search = searchQuery;
      return getAllEpics(params);
    },
    enabled: viewMode === 'list',
  });

  const storedEpics = epicsData?.data || [];

  // Auto-scroll thinking steps
  useEffect(() => {
    if (thinkingContainerRef.current) {
      thinkingContainerRef.current.scrollTop = thinkingContainerRef.current.scrollHeight;
    }
  }, [thinkingSteps]);

  // Load available models on mount
  useEffect(() => {
    const loadModels = async () => {
      setIsLoadingModels(true);
      try {
        const response = await listAvailableModels();
        setAvailableModels(response.models);
        setSelectedModel(response.default_model);
      } catch (err) {
        console.error('Failed to load available models:', err);
        setSelectedModel('gpt-4.1');
      } finally {
        setIsLoadingModels(false);
      }
    };
    loadModels();
  }, []);

  // Load default EPIC template on mount
  useEffect(() => {
    const loadDefaultTemplate = async () => {
      try {
        const response = await getDefaultEpicTemplate();
        if (response.success && response.template) {
          setDefaultEpicTemplate(response.template);
          setEpicTemplate(response.template);
          if (response.fields.length > 0) {
            setFieldConfigs(response.fields);
          }
        }
      } catch (err) {
        console.error('Failed to load default EPIC template:', err);
      }
    };
    loadDefaultTemplate();
  }, []);

  // Check if we should go directly to create mode (if BRD is provided)
  useEffect(() => {
    const brdIdParam = searchParams.get('brd_id');
    if (brdIdParam && !storedBRD && !isLoadingBRD) {
      setIsLoadingBRD(true);
      setLoadError(null);
      setViewMode('create');
      getBRDDetail(brdIdParam)
        .then((brd) => {
          setStoredBRD(brd);
          setBrdContent(brd.markdown_content);
          setBrdId(brd.brd_number);
          setBrdTitle(brd.title);
          setIsLoadingBRD(false);
        })
        .catch((err) => {
          console.error('Failed to load BRD:', err);
          setLoadError('Failed to load BRD from library');
          setIsLoadingBRD(false);
        });
    }
  }, [searchParams, storedBRD, isLoadingBRD]);

  // Close action menu when clicking outside
  useEffect(() => {
    const handleClickOutside = () => {
      if (actionMenuOpen) {
        setActionMenuOpen(null);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [actionMenuOpen]);

  // Handle BRD file upload (supports .md and .docx)
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const fileName = file.name.toLowerCase();
    const title = file.name.replace(/\.(md|docx)$/i, '');

    if (fileName.endsWith('.docx')) {
      try {
        const arrayBuffer = await file.arrayBuffer();
        const result = await mammoth.extractRawText({ arrayBuffer });
        setBrdContent(result.value);
        setBrdTitle(title);
      } catch (err) {
        console.error('Failed to parse .docx file:', err);
        setError('Failed to parse the Word document. Please try a different file.');
      }
    } else if (fileName.endsWith('.md')) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result as string;
        setBrdContent(content);
        setBrdTitle(title);
      };
      reader.readAsText(file);
    } else {
      setError('Please upload a Markdown (.md) or Word (.docx) file');
    }
  };

  // Handle EPIC template upload
  const handleTemplateUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.md') && !file.name.endsWith('.txt')) {
      setError('Please upload a Markdown (.md) or text (.txt) file');
      return;
    }

    const content = await file.text();
    setEpicTemplate(content);
    setTemplateFile(file);
    setIsUsingDefaultTemplate(false);
    setError(null);

    setIsParsingTemplate(true);
    try {
      const response = await parseEpicTemplateFields(content);
      if (response.success && response.fields && response.fields.length > 0) {
        setFieldConfigs(response.fields);
      }
    } catch (err) {
      console.error('Failed to parse uploaded template sections:', err);
    } finally {
      setIsParsingTemplate(false);
    }
  };

  // Clear template and revert to default
  const handleUseDefaultTemplate = async () => {
    setTemplateFile(null);
    setEpicTemplate(defaultEpicTemplate);
    setIsUsingDefaultTemplate(true);
    if (templateInputRef.current) {
      templateInputRef.current.value = '';
    }

    try {
      const response = await getDefaultEpicTemplate();
      if (response.success && response.fields && response.fields.length > 0) {
        setFieldConfigs(response.fields);
      }
    } catch (err) {
      console.error('Failed to load default template fields:', err);
    }
  };

  // Download current template
  const handleDownloadTemplate = () => {
    if (!epicTemplate) return;
    const blob = new Blob([epicTemplate], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = isUsingDefaultTemplate ? 'default-epic-template.md' : 'custom-epic-template.md';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Remove custom template
  const handleRemoveTemplate = () => {
    handleUseDefaultTemplate();
  };

  // Update field config
  const updateFieldConfig = (index: number, key: keyof EpicFieldConfig, value: any) => {
    setFieldConfigs((prev) =>
      prev.map((field, i) =>
        i === index ? { ...field, [key]: value } : field
      )
    );
  };

  // Generate EPICs - combines analysis and generation in one step
  const handleGenerateEpics = async () => {
    if (!brdContent) {
      setError('Please provide BRD content first');
      return;
    }

    setIsGenerating(true);
    setStep('generating');
    setThinkingSteps([]);
    setEpics([]);
    setError(null);

    // First, do a quick analysis to get recommended EPIC count
    let brdAnalysis: BRDAnalysisResult | null = null;
    try {
      const analysisRequest: AnalyzeBRDRequest = {
        brd_id: brdId,
        brd_markdown: brdContent,
        brd_title: brdTitle,
        epic_size_preference: 'medium',
        analysis_focus: 'functional_areas',
      };
      brdAnalysis = await analyzeBRDForEpics(analysisRequest);
    } catch (err) {
      console.warn('BRD analysis failed, proceeding with default settings:', err);
    }

    // Build template config if custom settings are used
    const templateConfig: EpicTemplateConfig | undefined = epicTemplate || showFieldConfig ? {
      epic_template: epicTemplate || undefined,
      field_configs: fieldConfigs,
      include_technical_components: true,
      include_dependencies: true,
      include_effort_estimates: true,
    } : undefined;

    const maxEpics = brdAnalysis?.recommended_epic_count || 10;

    const request: GenerateEpicsRequest = {
      brd_id: brdId,
      brd_markdown: brdContent,
      brd_title: brdTitle,
      mode: mode,
      max_epics: maxEpics,
      include_dependencies: true,
      include_estimates: true,
      epic_template: epicTemplate || undefined,
      template_config: templateConfig,
      detail_level: detailLevel,
      brd_analysis: brdAnalysis || undefined,
      user_defined_epics: brdAnalysis?.suggested_epics || undefined,
      model: selectedModel || undefined,
    };

    let stepId = 0;

    await generateEpicsStream(
      request,
      (event: EpicStreamEvent) => {
        if (event.type === 'thinking' && event.content) {
          stepId++;
          setThinkingSteps((prev) => [
            ...prev,
            { id: stepId, content: event.content!, timestamp: new Date() },
          ]);
        } else if (event.type === 'epic' && event.epic) {
          setEpics((prev) => [...prev, event.epic!]);
        } else if (event.type === 'complete' && event.data) {
          setEpics(event.data.epics);
          setCoverageMatrix(event.data.coverage_matrix);
          setUncoveredSections(event.data.uncovered_sections);
          setRecommendedOrder(event.data.recommended_order);
          setStep('review');
          setIsGenerating(false);
        } else if (event.type === 'error') {
          setError(event.error || 'Unknown error occurred');
          setIsGenerating(false);
        }
      },
      (err) => {
        setError(err.message);
        setIsGenerating(false);
      }
    );
  };

  // Refine single EPIC with AI
  const handleRefineEpic = async (epicId: string) => {
    const feedback = epicFeedback[epicId];
    if (!feedback?.trim()) return;

    const epicToRefine = epics.find((e) => e.id === epicId);
    if (!epicToRefine) return;

    setRefiningEpicId(epicId);

    try {
      const refined = await refineEpic(epicId, {
        epic_id: epicId,
        current_epic: epicToRefine,
        user_feedback: feedback,
        brd_sections_content: [brdContent],
      });

      setEpics((prev) => prev.map((e) => (e.id === epicId ? refined : e)));
      setEpicFeedback((prev) => ({ ...prev, [epicId]: '' }));
      setShowFeedbackFor(null);
    } catch (err) {
      setError(`Failed to refine EPIC: ${(err as Error).message}`);
    } finally {
      setRefiningEpicId(null);
    }
  };

  // Delete EPIC (in create mode)
  const handleDeleteEpicInCreate = (epicId: string) => {
    setEpics((prev) => prev.filter((e) => e.id !== epicId));
  };

  // Toggle EPIC expansion (in create mode)
  const toggleEpicExpanded = (epicId: string) => {
    setExpandedEpics((prev) => {
      const next = new Set(prev);
      if (next.has(epicId)) {
        next.delete(epicId);
      } else {
        next.add(epicId);
      }
      return next;
    });
  };

  // Start editing an EPIC (in create mode)
  const handleStartEdit = (epic: Epic) => {
    setEditingEpicId(epic.id);
    setEditFormData({
      title: epic.title,
      description: epic.description,
      business_value: epic.business_value,
      objectives: epic.objectives,
      acceptance_criteria: epic.acceptance_criteria,
    });
  };

  // Save edited EPIC (in create mode)
  const handleSaveEdit = () => {
    if (!editingEpicId) return;

    setEpics((prev) =>
      prev.map((e) =>
        e.id === editingEpicId ? { ...e, ...editFormData } : e
      )
    );
    setEditingEpicId(null);
    setEditFormData({});
  };

  // Cancel editing
  const handleCancelEdit = () => {
    setEditingEpicId(null);
    setEditFormData({});
  };

  // Toggle individual EPIC approval status
  const handleToggleEpicApproval = (epicId: string) => {
    setEpics((prev) =>
      prev.map((e) =>
        e.id === epicId
          ? { ...e, status: e.status === 'approved' ? 'draft' : 'approved' }
          : e
      )
    );
  };

  // Approve all EPICs at once
  const handleApproveAllEpics = () => {
    setEpics((prev) =>
      prev.map((e) => ({ ...e, status: 'approved' as const }))
    );
  };

  // Count approved EPICs
  const approvedEpicsCount = epics.filter((e) => e.status === 'approved').length;

  // Approve and continue to backlogs - saves EPICs to database
  const handleApproveAndContinue = async () => {
    console.log('handleApproveAndContinue called', { storedBRD, epicsCount: epics.length, brdContent: brdContent?.length });

    if (epics.length === 0) {
      setSaveError('No EPICs to save');
      return;
    }

    setIsSavingEpics(true);
    setSaveError(null);

    try {
      const epicData = epics.map((epic) => ({
        title: epic.title,
        description: epic.description,
        business_value: epic.business_value,
        objectives: epic.objectives,
        acceptance_criteria: epic.acceptance_criteria,
        affected_components: epic.affected_components,
        depends_on: epic.depends_on,
      }));

      let targetBrdId = storedBRD?.id;

      // If no stored BRD, create one first
      if (!storedBRD && brdContent) {
        console.log('No storedBRD - creating BRD first...');
        try {
          // Get the first available repository
          const reposResponse = await getRepositories();
          const repos = reposResponse.data || [];
          if (repos.length === 0) {
            setSaveError('No repository available. Please create a repository first.');
            setIsSavingEpics(false);
            return;
          }

          // Save the BRD to the database
          const newBrd = await saveBRD({
            repository_id: repos[0].id,
            title: brdTitle || 'Uploaded BRD',
            feature_description: brdTitle || 'Uploaded BRD',
            markdown_content: brdContent,
            mode: 'draft',
          });
          console.log('BRD created successfully:', newBrd.id);
          setStoredBRD(newBrd);
          targetBrdId = newBrd.id;
        } catch (brdErr) {
          console.error('Failed to create BRD:', brdErr);
          setSaveError('Failed to save BRD. Please try again.');
          setIsSavingEpics(false);
          return;
        }
      }

      if (targetBrdId) {
        // Save EPICs to the BRD
        console.log('Saving EPICs to BRD:', targetBrdId);
        const saved = await saveEpicsForBRD(targetBrdId, epicData);
        console.log('EPICs saved successfully:', saved.length, 'EPICs');
        setSavedEpics(saved);
      } else {
        console.warn('No BRD ID available - EPICs will not be persisted');
        setSaveError('Unable to save EPICs - no BRD available.');
        setIsSavingEpics(false);
        return;
      }

      setIsSavingEpics(false);
      setStep('approved');
    } catch (err) {
      console.error('Failed to save EPICs:', err);
      setSaveError('Failed to save EPICs. Please try again.');
      setIsSavingEpics(false);
    }
  };

  // Navigate to backlog generation
  const handleContinueToBacklogs = async () => {
    if (storedBRD && epics.length > 0) {
      setIsSavingEpics(true);
      setSaveError(null);
      try {
        const epicData = epics.map((epic) => ({
          title: epic.title,
          description: epic.description,
          business_value: epic.business_value,
          objectives: epic.objectives,
          acceptance_criteria: epic.acceptance_criteria,
          affected_components: epic.affected_components,
          depends_on: epic.depends_on,
        }));
        const saved = await saveEpicsForBRD(storedBRD.id, epicData);
        setSavedEpics(saved);
        setIsSavingEpics(false);

        navigate(`/generate-backlogs?brd_id=${storedBRD.id}`);
      } catch (err) {
        console.error('Failed to save EPICs:', err);
        setSaveError('Failed to save EPICs');
        setIsSavingEpics(false);
        navigate('/generate-backlogs', {
          state: {
            epics,
            brdContent,
            brdId,
            brdTitle,
          },
        });
      }
    } else {
      navigate('/generate-backlogs', {
        state: {
          epics,
          brdContent,
          brdId,
          brdTitle,
        },
      });
    }
  };

  // Download EPICs as markdown
  const handleDownload = () => {
    const content = epics
      .map(
        (epic) => `# ${epic.id}: ${epic.title}

**Status:** ${epic.status}

## Description
${epic.description}

## Business Value
${epic.business_value}

## Objectives
${epic.objectives.map((o) => `- ${o}`).join('\n')}

## Acceptance Criteria
${epic.acceptance_criteria.map((c) => `- [ ] ${c}`).join('\n')}

## Dependencies
${epic.depends_on.length > 0 ? epic.depends_on.map((d) => `- Depends on: ${d}`).join('\n') : '- None'}

## Affected Components
${epic.affected_components.map((c) => `- ${c}`).join('\n') || '- TBD'}

---
`
      )
      .join('\n\n');

    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `EPICs-${brdId}-${new Date().toISOString().split('T')[0]}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // ============================================
  // List View Functions
  // ============================================

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const handleDeleteEpic = async (e: React.MouseEvent, epicId: string) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this EPIC? All associated backlogs will also be deleted.')) return;

    setActionLoading(epicId);
    try {
      await deleteEpicApi(epicId);
      refetchEpics();
    } catch (err: any) {
      console.error('Failed to delete EPIC:', err);
      alert(err.response?.data?.detail || 'Failed to delete EPIC');
    } finally {
      setActionLoading(null);
    }
  };

  const handleViewEpic = (e: React.MouseEvent, epic: StoredEpic) => {
    e.stopPropagation();
    setSelectedEpicForView(epic);
    setViewMode('view');
  };

  const handleGenerateBacklogsForEpic = (epicId: string) => {
    navigate(`/generate-backlogs?epic_id=${epicId}`);
  };

  // Generate markdown content for EPIC
  const generateEpicMarkdown = (epic: StoredEpic): string => {
    let content = `# ${epic.title}\n\n`;
    content += `**EPIC ID:** ${epic.epic_number}\n\n`;

    if (epic.description) {
      content += `## Description\n${epic.description}\n\n`;
    }

    if (epic.business_value) {
      content += `## Business Value\n${epic.business_value}\n\n`;
    }

    if (epic.objectives && epic.objectives.length > 0) {
      content += `## Objectives\n`;
      epic.objectives.forEach(obj => {
        content += `- ${obj}\n`;
      });
      content += '\n';
    }

    if (epic.acceptance_criteria && epic.acceptance_criteria.length > 0) {
      content += `## Acceptance Criteria\n`;
      epic.acceptance_criteria.forEach(ac => {
        content += `- ${ac}\n`;
      });
      content += '\n';
    }

    if (epic.affected_components && epic.affected_components.length > 0) {
      content += `## Affected Components\n`;
      epic.affected_components.forEach(comp => {
        content += `- ${comp}\n`;
      });
      content += '\n';
    }

    if (epic.depends_on && epic.depends_on.length > 0) {
      content += `## Dependencies\n`;
      epic.depends_on.forEach(dep => {
        content += `- ${dep}\n`;
      });
      content += '\n';
    }

    return content;
  };

  // Handle MD download
  const handleDownloadEpicMD = (epic: StoredEpic) => {
    const content = generateEpicMarkdown(epic);
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${epic.epic_number}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Handle DOCX download
  const handleDownloadEpicDOCX = (epic: StoredEpic) => {
    try {
      const markdown = generateEpicMarkdown(epic);

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

      html = `<html><head><meta charset="utf-8"><title>${epic.title}</title></head><body>${html}</body></html>`;

      const blob = new Blob([html], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${epic.epic_number}-${epic.title.replace(/\s+/g, '-')}.doc`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('DOCX download failed:', err);
      setError('Failed to download DOCX');
    }
  };

  const handleBackToListFromView = () => {
    setSelectedEpicForView(null);
    setViewMode('list');
    setIsEditingViewEpic(false);
    setEditingViewSections([]);
  };

  // Convert EPIC to editable sections
  const buildEditableSections = (epic: StoredEpic) => {
    const sections: Array<{ name: string; key: string; content: string | string[] }> = [];

    sections.push({ name: 'Title', key: 'title', content: epic.title || '' });
    sections.push({ name: 'Description', key: 'description', content: epic.description || '' });

    if (epic.business_value !== undefined) {
      sections.push({ name: 'Business Value', key: 'business_value', content: epic.business_value || '' });
    }

    if (epic.objectives !== undefined) {
      sections.push({ name: 'Objectives', key: 'objectives', content: epic.objectives || [] });
    }

    if (epic.acceptance_criteria !== undefined) {
      sections.push({ name: 'Acceptance Criteria', key: 'acceptance_criteria', content: epic.acceptance_criteria || [] });
    }

    if (epic.affected_components !== undefined) {
      sections.push({ name: 'Affected Components', key: 'affected_components', content: epic.affected_components || [] });
    }

    if (epic.depends_on !== undefined) {
      sections.push({ name: 'Dependencies', key: 'depends_on', content: epic.depends_on || [] });
    }

    return sections;
  };

  // Handle starting edit mode for view
  const handleStartEditViewEpic = () => {
    if (selectedEpicForView) {
      setEditingViewSections(buildEditableSections(selectedEpicForView));
      setIsEditingViewEpic(true);
    }
  };

  // Handle canceling edit
  const handleCancelEditViewEpic = () => {
    setIsEditingViewEpic(false);
    setEditingViewSections([]);
    setRefiningSectionIdx(null);
    setSectionFeedback('');
  };

  // Handle section content change
  const handleViewSectionChange = (index: number, newContent: string | string[]) => {
    setEditingViewSections(prev => prev.map((s, i) =>
      i === index ? { ...s, content: newContent } : s
    ));
  };

  // Handle saving edited EPIC
  const handleSaveViewEpic = async () => {
    if (!selectedEpicForView) return;

    setIsSavingViewEpic(true);
    try {
      // Build update request from sections
      const updateData: Record<string, string | string[]> = {};
      editingViewSections.forEach(section => {
        updateData[section.key] = section.content;
      });

      const updatedEpic = await updateEpic(selectedEpicForView.id, updateData);
      setSelectedEpicForView(updatedEpic);
      setIsEditingViewEpic(false);
      setEditingViewSections([]);
      refetchEpics();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save EPIC');
    } finally {
      setIsSavingViewEpic(false);
    }
  };

  // Handle approve and continue to backlogs (View mode)
  const handleApproveViewEpicAndContinue = async () => {
    if (!selectedEpicForView) return;

    setIsApprovingEpic(true);
    try {
      const updatedEpic = await updateEpic(selectedEpicForView.id, { status: 'approved' });
      setSelectedEpicForView(updatedEpic);
      refetchEpics();
      // Navigate to generate backlogs
      navigate(`/generate-backlogs?epic_id=${selectedEpicForView.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to approve EPIC');
    } finally {
      setIsApprovingEpic(false);
    }
  };

  // Handle AI refinement for a specific section
  const handleRefineSectionWithAI = async (sectionIndex: number) => {
    if (!selectedEpicForView || !sectionFeedback.trim()) return;

    setIsRefiningSectionAI(true);
    try {
      const section = editingViewSections[sectionIndex];

      // Build current epic from editing sections
      const currentEpic: Epic = {
        id: selectedEpicForView.id,
        title: '',
        description: '',
        business_value: '',
        brd_id: selectedEpicForView.brd_id || '',
        brd_section_refs: [],
        objectives: [],
        acceptance_criteria: [],
        status: 'draft',
        depends_on: [],
        blocks: [],
        affected_components: [],
        refinement_count: 0,
        created_at: new Date().toISOString(),
      };

      editingViewSections.forEach(s => {
        // Use type assertion with unknown first
        (currentEpic as unknown as Record<string, string | string[]>)[s.key] = s.content;
      });

      // Refine focusing on this section
      const refinedEpic = await refineEpic(selectedEpicForView.id, {
        epic_id: selectedEpicForView.id,
        current_epic: currentEpic,
        user_feedback: `Please refine the "${section.name}" section with this feedback: ${sectionFeedback}`,
        brd_sections_content: [],
      });

      // Update the specific section with refined content
      const refinedValue = (refinedEpic as unknown as Record<string, string | string[]>)[section.key];
      if (refinedValue !== undefined) {
        handleViewSectionChange(sectionIndex, refinedValue);
      }

      setRefiningSectionIdx(null);
      setSectionFeedback('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refine section');
    } finally {
      setIsRefiningSectionAI(false);
    }
  };

  const handleEditStoredEpic = (e: React.MouseEvent, epic: StoredEpic) => {
    e.stopPropagation();
    setExpandedEpicId(epic.id);
    // For now, just expand to show details
    // Full edit mode can be implemented later
  };

  const handleRowClick = (epic: StoredEpic) => {
    if (expandedEpicId === epic.id) {
      setExpandedEpicId(null);
    } else {
      setExpandedEpicId(epic.id);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const getStatusIcon = (status: string, size = 18) => {
    switch (status) {
      case 'completed':
      case 'approved':
        return <CheckCircle size={size} className="status-icon success" />;
      case 'draft':
        return <FileText size={size} className="status-icon pending" />;
      case 'in_progress':
        return <Loader2 size={size} className="status-icon running spinning" />;
      default:
        return <FileText size={size} className="status-icon" />;
    }
  };

  // Get unique repositories and BRDs for filter dropdowns
  const uniqueRepositories = Array.from(
    new Map(
      storedEpics
        .filter((e) => e.repository_id && e.repository_name)
        .map((e) => [e.repository_id, { id: e.repository_id!, name: e.repository_name! }])
    ).values()
  );

  const uniqueBRDs = Array.from(
    new Map(
      storedEpics
        .filter((e) => e.brd_id && e.brd_title)
        .map((e) => [e.brd_id, { id: e.brd_id, title: e.brd_title! }])
    ).values()
  );

  // Filter and sort EPICs
  const filteredEpics = storedEpics.filter((epic) => {
    if (statusFilter !== 'all' && epic.status !== statusFilter) return false;
    if (repositoryFilter !== 'all' && epic.repository_id !== repositoryFilter) return false;
    if (brdFilter !== 'all' && epic.brd_id !== brdFilter) return false;
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        epic.title.toLowerCase().includes(query) ||
        epic.epic_number.toLowerCase().includes(query) ||
        epic.description.toLowerCase().includes(query)
      );
    }
    return true;
  });

  const sortedEpics = [...filteredEpics].sort((a, b) => {
    let comparison = 0;

    switch (sortField) {
      case 'title':
        comparison = a.title.localeCompare(b.title);
        break;
      case 'brd':
        comparison = (a.brd_id || '').localeCompare(b.brd_id || '');
        break;
      case 'backlogs':
        comparison = (a.backlog_count || 0) - (b.backlog_count || 0);
        break;
      case 'updated':
        comparison = new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime();
        break;
    }

    return sortDirection === 'asc' ? comparison : -comparison;
  });

  // Count EPICs by status
  const statusCounts = {
    all: storedEpics.length,
    draft: storedEpics.filter((e) => e.status === 'draft' || !e.status).length,
    approved: storedEpics.filter((e) => e.status === 'approved').length,
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown size={14} className="sort-icon inactive" />;
    return sortDirection === 'asc'
      ? <ArrowUp size={14} className="sort-icon active" />
      : <ArrowDown size={14} className="sort-icon active" />;
  };

  const handleNewEpic = () => {
    setViewMode('create');
    setStep('source');
    setBrdContent('');
    setBrdId(`BRD-${Date.now()}`);
    setBrdTitle('Business Requirements Document');
    setStoredBRD(null);
    setEpics([]);
    setThinkingSteps([]);
  };

  const handleBackToList = () => {
    setViewMode('list');
    setStep('source');
    refetchEpics();
  };

  // ============================================
  // Render
  // ============================================

  // List View
  if (viewMode === 'list') {
    return (
      <div className="generate-epic-page library-view">
        {/* Header */}
        <div className="epic-list-header">
          <div className="header-left">
            <h1><Layers size={28} /> EPIC Library</h1>
            <span className="epic-count">{storedEpics.length} EPICs total</span>
          </div>
          <button className="btn btn-primary" onClick={handleNewEpic}>
            <Plus size={18} />
            New EPIC Generation
          </button>
        </div>

        {/* Toolbar */}
        <div className="jobs-toolbar">
          <div className="jobs-filters">
            <button
              className={`filter-btn ${statusFilter === 'all' ? 'active' : ''}`}
              onClick={() => setStatusFilter('all')}
            >
              All ({statusCounts.all})
            </button>
            <button
              className={`filter-btn ${statusFilter === 'draft' ? 'active' : ''}`}
              onClick={() => setStatusFilter('draft')}
            >
              <FileText size={14} />
              Draft ({statusCounts.draft})
            </button>
            <button
              className={`filter-btn completed ${statusFilter === 'approved' ? 'active' : ''}`}
              onClick={() => setStatusFilter('approved')}
            >
              <ShieldCheck size={14} />
              Approved ({statusCounts.approved})
            </button>

            {/* Repository Filter */}
            {uniqueRepositories.length > 0 && (
              <select
                className="filter-select"
                value={repositoryFilter}
                onChange={(e) => setRepositoryFilter(e.target.value)}
              >
                <option value="all">All Repositories</option>
                {uniqueRepositories.map((repo) => (
                  <option key={repo.id} value={repo.id}>
                    {repo.name}
                  </option>
                ))}
              </select>
            )}

            {/* BRD Filter */}
            {uniqueBRDs.length > 0 && (
              <select
                className="filter-select"
                value={brdFilter}
                onChange={(e) => setBrdFilter(e.target.value)}
              >
                <option value="all">All BRDs</option>
                {uniqueBRDs.map((brd) => (
                  <option key={brd.id} value={brd.id}>
                    {brd.title}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="toolbar-right">
            <input
              type="text"
              placeholder="Search EPICs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="search-input"
            />
            <button
              className="btn btn-outline refresh-btn"
              onClick={() => refetchEpics()}
              disabled={isFetching}
            >
              <RefreshCw size={16} className={isFetching ? 'spinning' : ''} />
              Refresh
            </button>
          </div>
        </div>

        {/* EPIC Table */}
        {isLoadingEpics ? (
          <div className="loading-state">
            <Loader2 size={32} className="spinning" />
            <p>Loading EPICs...</p>
          </div>
        ) : sortedEpics.length === 0 ? (
          <div className="empty-state">
            <Layers size={48} />
            <h3>No EPICs Found</h3>
            <p>Start by generating EPICs from a BRD document</p>
            <button className="btn btn-primary" onClick={handleNewEpic}>
              <Plus size={16} />
              Generate New EPIC
            </button>
          </div>
        ) : (
          <div className="jobs-table-container">
            <table className="jobs-table">
              <thead>
                <tr>
                  <th className="col-expand"></th>
                  <th className="col-status">Status</th>
                  <th className="col-epic-id">EPIC ID</th>
                  <th className="col-title sortable" onClick={() => handleSort('title')}>
                    Title <SortIcon field="title" />
                  </th>
                  <th className="col-repository">
                    Repository
                  </th>
                  <th className="col-brd sortable" onClick={() => handleSort('brd')}>
                    BRD <SortIcon field="brd" />
                  </th>
                  <th className="col-backlogs sortable" onClick={() => handleSort('backlogs')}>
                    Stories <SortIcon field="backlogs" />
                  </th>
                  <th className="col-updated sortable" onClick={() => handleSort('updated')}>
                    Last Updated <SortIcon field="updated" />
                  </th>
                  <th className="col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {sortedEpics.map((epic) => (
                  <Fragment key={epic.id}>
                    <tr
                      className={`job-row ${epic.status} ${expandedEpicId === epic.id ? 'expanded' : ''}`}
                      onClick={() => handleRowClick(epic)}
                    >
                      <td className="col-expand">
                        {expandedEpicId === epic.id
                          ? <ChevronUp size={18} />
                          : <ChevronDown size={18} />}
                      </td>
                      <td className="col-status">
                        <div className="status-cell">
                          {getStatusIcon(epic.status)}
                          <span className={`status-text ${epic.status}`}>
                            {epic.status.replace('_', ' ')}
                          </span>
                        </div>
                      </td>
                      <td className="col-epic-id">
                        <span className="epic-id-badge">{epic.epic_number}</span>
                      </td>
                      <td className="col-title">
                        <span className="epic-title-text">{epic.title}</span>
                      </td>
                      <td className="col-repository">
                        <span className="repository-name" title={epic.repository_name || ''}>
                          <GitBranch size={14} />
                          {epic.repository_name || '-'}
                        </span>
                      </td>
                      <td className="col-brd">
                        <span className="brd-link" title={epic.brd_title || epic.brd_id}>
                          <FileText size={14} />
                          {epic.brd_title || (epic.brd_id ? `BRD-${epic.brd_id.slice(0, 8)}` : '-')}
                        </span>
                      </td>
                      <td className="col-backlogs">
                        <div className="backlogs-cell">
                          <ListChecks size={14} />
                          <span>{epic.backlog_count || 0}</span>
                        </div>
                      </td>
                      <td className="col-updated">
                        <div className="time-cell">
                          <Calendar size={14} />
                          <span>{formatDate(epic.updated_at)}</span>
                        </div>
                      </td>
                      <td className="col-actions">
                        <div className="action-menu-container">
                          <button
                            className="action-menu-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              setActionMenuOpen(actionMenuOpen === epic.id ? null : epic.id);
                            }}
                          >
                            <MoreVertical size={16} />
                          </button>
                          {actionMenuOpen === epic.id && (
                            <div className="action-menu" onClick={(e) => e.stopPropagation()}>
                              <button onClick={(e) => handleViewEpic(e, epic)}>
                                <Eye size={14} />
                                View EPIC
                              </button>
                              <button onClick={(e) => handleEditStoredEpic(e, epic)}>
                                <Edit3 size={14} />
                                Edit EPIC
                              </button>
                              <hr />
                              <button className="danger" onClick={(e) => handleDeleteEpic(e, epic.id)}>
                                {actionLoading === epic.id ? (
                                  <Loader2 size={14} className="spinning" />
                                ) : (
                                  <Trash2 size={14} />
                                )}
                                Delete
                              </button>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>

                    {/* Expanded Row */}
                    {expandedEpicId === epic.id && (
                      <tr className="job-expanded-row">
                        <td colSpan={8}>
                          <div className="job-detail-panel">
                            {/* Stats Overview */}
                            <div className="detail-stats-grid epic-detail-grid">
                              <div className="detail-stat-card">
                                <div className="stat-icon files">
                                  <FileStack size={20} />
                                </div>
                                <div className="stat-content">
                                  <span className="stat-value">{epic.backlog_count || 0}</span>
                                  <span className="stat-label">Backlog Items</span>
                                </div>
                              </div>
                              <div className="detail-stat-card">
                                <div className="stat-icon nodes">
                                  <ListChecks size={20} />
                                </div>
                                <div className="stat-content">
                                  <span className="stat-value">{epic.acceptance_criteria?.length || 0}</span>
                                  <span className="stat-label">Acceptance Criteria</span>
                                </div>
                              </div>
                              <div className="detail-stat-card">
                                <div className="stat-icon relationships">
                                  <Layers size={20} />
                                </div>
                                <div className="stat-content">
                                  <span className="stat-value">{epic.objectives?.length || 0}</span>
                                  <span className="stat-label">Objectives</span>
                                </div>
                              </div>
                              <div className="detail-stat-card">
                                <div className="stat-icon classes">
                                  <GitBranch size={20} />
                                </div>
                                <div className="stat-content">
                                  <span className="stat-value">{epic.depends_on?.length || 0}</span>
                                  <span className="stat-label">Dependencies</span>
                                </div>
                              </div>
                            </div>

                            {/* Description */}
                            <div className="epic-detail-section">
                              <h4>Description</h4>
                              <p>{epic.description}</p>
                            </div>

                            {/* Business Value */}
                            {epic.business_value && (
                              <div className="epic-detail-section">
                                <h4>Business Value</h4>
                                <p>{epic.business_value}</p>
                              </div>
                            )}

                            {/* Objectives */}
                            {epic.objectives && epic.objectives.length > 0 && (
                              <div className="epic-detail-section">
                                <h4>Objectives</h4>
                                <ul>
                                  {epic.objectives.map((obj, i) => (
                                    <li key={i}>{obj}</li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {/* Acceptance Criteria */}
                            {epic.acceptance_criteria && epic.acceptance_criteria.length > 0 && (
                              <div className="epic-detail-section">
                                <h4>Acceptance Criteria</h4>
                                <ul>
                                  {epic.acceptance_criteria.map((ac, i) => (
                                    <li key={i}>{ac}</li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {/* Action Buttons */}
                            <div className="epic-detail-actions">
                              <button
                                className="btn btn-primary"
                                onClick={(e) => handleViewEpic(e, epic)}
                              >
                                <ArrowRight size={16} />
                                Generate Backlogs
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  // View Mode - EPIC Details
  if (viewMode === 'view' && selectedEpicForView) {
    return (
      <div className="generate-epic-page">
        {/* Back to List Button */}
        <button className="btn btn-outline back-to-list-btn" onClick={handleBackToListFromView}>
          <ArrowLeft size={16} />
          Back to EPIC Library
        </button>

        {/* EPIC Detail Header */}
        <div className="epic-detail-header">
          <div className="epic-detail-title-section">
            <h1>{isEditingViewEpic ? 'Editing EPIC' : selectedEpicForView.title}</h1>
            <div className="epic-detail-meta">
              <span className="epic-id-badge">{selectedEpicForView.epic_number}</span>
              <span className={`status-badge ${selectedEpicForView.status}`}>
                {selectedEpicForView.status.replace('_', ' ')}
              </span>
              {isEditingViewEpic && (
                <span className="editing-indicator">
                  <Edit3 size={14} />
                  Editing Mode
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Action Bar */}
        <div className="epic-action-bar">
          <div className="action-bar-left">
            <span className="repo-info">
              <FolderGit2 size={16} />
              {selectedEpicForView.repository_name || 'Unknown Repository'}
            </span>
            <span className="brd-info">
              <FileText size={16} />
              {selectedEpicForView.brd_title || (selectedEpicForView.brd_id ? `BRD-${selectedEpicForView.brd_id.slice(0, 8)}` : 'Unknown BRD')}
            </span>
            <span className="date-info">
              <Clock size={16} />
              Created {formatDate(selectedEpicForView.created_at)}
            </span>
          </div>
          <div className="action-bar-right">
            {isEditingViewEpic ? (
              <>
                <button
                  className="btn btn-outline"
                  onClick={handleCancelEditViewEpic}
                  disabled={isSavingViewEpic}
                >
                  <X size={16} />
                  Cancel
                </button>
                <button
                  className="btn btn-primary"
                  onClick={handleSaveViewEpic}
                  disabled={isSavingViewEpic}
                >
                  {isSavingViewEpic ? <Loader2 size={16} className="spin" /> : <Save size={16} />}
                  Save Changes
                </button>
              </>
            ) : (
              <>
                <button className="btn btn-outline" onClick={handleStartEditViewEpic}>
                  <Edit3 size={16} />
                  Edit
                </button>
                {selectedEpicForView.status === 'approved' ? (
                  <button
                    className="btn btn-primary"
                    onClick={() => handleGenerateBacklogsForEpic(selectedEpicForView.id)}
                  >
                    <ListChecks size={18} />
                    Generate Backlogs
                  </button>
                ) : (
                  <button
                    className="btn btn-primary"
                    onClick={handleApproveViewEpicAndContinue}
                    disabled={isApprovingEpic}
                  >
                    {isApprovingEpic ? <Loader2 size={16} className="spin" /> : <CheckCircle size={16} />}
                    Approve & Continue
                  </button>
                )}
                <button className="btn btn-outline" onClick={() => handleDownloadEpicMD(selectedEpicForView)}>
                  <Download size={16} />
                  Download MD
                </button>
                <button className="btn btn-outline" onClick={() => handleDownloadEpicDOCX(selectedEpicForView)}>
                  <Download size={16} />
                  Download DOCX
                </button>
              </>
            )}
          </div>
        </div>

        {/* EPIC Stats */}
        <div className="epic-detail-stats">
          <div className="detail-stat-card">
            <div className="stat-icon files">
              <ListChecks size={20} />
            </div>
            <div className="stat-content">
              <span className="stat-value">{selectedEpicForView.backlog_count || 0}</span>
              <span className="stat-label">Backlog Items</span>
            </div>
          </div>
          <div className="detail-stat-card">
            <div className="stat-icon nodes">
              <CheckCircle size={20} />
            </div>
            <div className="stat-content">
              <span className="stat-value">{selectedEpicForView.acceptance_criteria?.length || 0}</span>
              <span className="stat-label">Acceptance Criteria</span>
            </div>
          </div>
          <div className="detail-stat-card">
            <div className="stat-icon relationships">
              <Target size={20} />
            </div>
            <div className="stat-content">
              <span className="stat-value">{selectedEpicForView.objectives?.length || 0}</span>
              <span className="stat-label">Objectives</span>
            </div>
          </div>
          <div className="detail-stat-card">
            <div className="stat-icon classes">
              <GitBranch size={20} />
            </div>
            <div className="stat-content">
              <span className="stat-value">{selectedEpicForView.depends_on?.length || 0}</span>
              <span className="stat-label">Dependencies</span>
            </div>
          </div>
        </div>

        {/* EPIC Content Sections */}
        <div className="epic-detail-content">
          {isEditingViewEpic ? (
            /* Edit Mode - Section by Section */
            <div className="epic-edit-sections">
              {editingViewSections.map((section, index) => (
                <div key={section.key} className="epic-detail-section editable">
                  <div className="section-header-row">
                    <h3>{section.name}</h3>
                    <button
                      className={`btn btn-sm btn-outline refine-btn ${refiningSectionIdx === index ? 'active' : ''}`}
                      onClick={() => {
                        if (refiningSectionIdx === index) {
                          setRefiningSectionIdx(null);
                          setSectionFeedback('');
                        } else {
                          setRefiningSectionIdx(index);
                          setSectionFeedback('');
                        }
                      }}
                    >
                      <Sparkles size={14} />
                      AI Refine
                    </button>
                  </div>

                  {/* AI Refinement Input */}
                  {refiningSectionIdx === index && (
                    <div className="section-refinement-input">
                      <textarea
                        value={sectionFeedback}
                        onChange={(e) => setSectionFeedback(e.target.value)}
                        placeholder="Describe how you'd like this section to be refined..."
                        rows={2}
                      />
                      <div className="refinement-actions">
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => handleRefineSectionWithAI(index)}
                          disabled={isRefiningSectionAI || !sectionFeedback.trim()}
                        >
                          {isRefiningSectionAI ? <Loader2 size={14} className="spin" /> : <Send size={14} />}
                          Refine with AI
                        </button>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => {
                            setRefiningSectionIdx(null);
                            setSectionFeedback('');
                          }}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Section Editor */}
                  {Array.isArray(section.content) ? (
                    <div className="array-editor">
                      {(section.content as string[]).map((item, itemIdx) => (
                        <div key={itemIdx} className="array-item-row">
                          <input
                            type="text"
                            value={item}
                            onChange={(e) => {
                              const newArr = [...(section.content as string[])];
                              newArr[itemIdx] = e.target.value;
                              handleViewSectionChange(index, newArr);
                            }}
                          />
                          <button
                            className="btn btn-icon btn-sm"
                            onClick={() => {
                              const newArr = (section.content as string[]).filter((_, i) => i !== itemIdx);
                              handleViewSectionChange(index, newArr);
                            }}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      ))}
                      <button
                        className="btn btn-sm btn-outline add-item-btn"
                        onClick={() => {
                          handleViewSectionChange(index, [...(section.content as string[]), '']);
                        }}
                      >
                        <Plus size={14} />
                        Add Item
                      </button>
                    </div>
                  ) : (
                    <textarea
                      className="section-editor"
                      value={section.content as string}
                      onChange={(e) => handleViewSectionChange(index, e.target.value)}
                      rows={section.key === 'description' || section.key === 'business_value' ? 6 : 2}
                    />
                  )}
                </div>
              ))}
            </div>
          ) : (
            /* View Mode - Display Content */
            <>
              <div className="epic-detail-section">
                <h3><FileText size={18} /> Description</h3>
                <p>{selectedEpicForView.description}</p>
              </div>

              {selectedEpicForView.business_value && (
                <div className="epic-detail-section">
                  <h3><Sparkles size={18} /> Business Value</h3>
                  <p>{selectedEpicForView.business_value}</p>
                </div>
              )}

              {selectedEpicForView.objectives && selectedEpicForView.objectives.length > 0 && (
                <div className="epic-detail-section">
                  <h3><Target size={18} /> Objectives</h3>
                  <ul>
                    {selectedEpicForView.objectives.map((obj, i) => (
                      <li key={i}>{obj}</li>
                    ))}
                  </ul>
                </div>
              )}

              {selectedEpicForView.acceptance_criteria && selectedEpicForView.acceptance_criteria.length > 0 && (
                <div className="epic-detail-section">
                  <h3><CheckCircle size={18} /> Acceptance Criteria</h3>
                  <ul>
                    {selectedEpicForView.acceptance_criteria.map((ac, i) => (
                      <li key={i}>{ac}</li>
                    ))}
                  </ul>
                </div>
              )}

              {selectedEpicForView.affected_components && selectedEpicForView.affected_components.length > 0 && (
                <div className="epic-detail-section">
                  <h3><Layers size={18} /> Affected Components</h3>
                  <div className="component-tags">
                    {selectedEpicForView.affected_components.map((comp, i) => (
                      <span key={i} className="component-tag">{comp}</span>
                    ))}
                  </div>
                </div>
              )}

              {selectedEpicForView.depends_on && selectedEpicForView.depends_on.length > 0 && (
                <div className="epic-detail-section">
                  <h3><GitBranch size={18} /> Dependencies</h3>
                  <div className="component-tags">
                    {selectedEpicForView.depends_on.map((dep, i) => (
                      <span key={i} className="component-tag">{dep}</span>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Backlogs Section - Grid Table */}
        <div className="epic-backlogs-section">
          <div className="section-header">
            <h3><ListChecks size={18} /> Backlogs ({selectedEpicForView.backlogs?.length || 0})</h3>
          </div>
          {selectedEpicForView.backlogs && selectedEpicForView.backlogs.length > 0 ? (
            <div className="backlogs-table-container">
              <table className="backlogs-table">
                <thead>
                  <tr>
                    <th className="col-status">Status</th>
                    <th className="col-backlog-id">ID</th>
                    <th className="col-type">Type</th>
                    <th className="col-title">Title</th>
                    <th className="col-priority">Priority</th>
                    <th className="col-points">Points</th>
                    <th className="col-updated">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedEpicForView.backlogs.map((backlog) => (
                    <tr key={backlog.id} className={`backlog-row ${backlog.status}`}>
                      <td className="col-status">
                        <div className="status-cell">
                          {backlog.status === 'approved' ? (
                            <ShieldCheck size={14} className="status-icon approved" />
                          ) : backlog.status === 'draft' ? (
                            <FileText size={14} className="status-icon draft" />
                          ) : (
                            <CheckCircle size={14} className="status-icon" />
                          )}
                          <span className={`status-text ${backlog.status}`}>
                            {backlog.status.replace('_', ' ')}
                          </span>
                        </div>
                      </td>
                      <td className="col-backlog-id">
                        <span className="backlog-id-badge">{backlog.backlog_number}</span>
                      </td>
                      <td className="col-type">
                        <span className="type-badge">{backlog.item_type}</span>
                      </td>
                      <td className="col-title">
                        <span className="backlog-title-text">{backlog.title}</span>
                      </td>
                      <td className="col-priority">
                        <span className={`priority-badge ${priorityColors[backlog.priority]}`}>
                          {backlog.priority}
                        </span>
                      </td>
                      <td className="col-points">
                        <span className="points-badge">
                          {backlog.story_points || '-'}
                        </span>
                      </td>
                      <td className="col-updated">
                        <div className="time-cell">
                          <Calendar size={14} />
                          <span>{formatDate(backlog.updated_at)}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-backlogs-state">
              <ListChecks size={32} />
              <p>No backlogs generated yet</p>
              {selectedEpicForView.status === 'approved' && (
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => handleGenerateBacklogsForEpic(selectedEpicForView.id)}
                >
                  <Plus size={14} />
                  Generate Backlogs
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  // Create View (Original EPIC Generation Flow)
  return (
    <div className="generate-epic-page">
      {/* Back to List Button */}
      <button className="btn btn-outline back-to-list-btn" onClick={handleBackToList}>
        <ArrowLeft size={16} />
        Back to EPIC Library
      </button>

      {/* Workflow Stepper - Simplified */}
      <div className="workflow-stepper">
        <div className={`step ${step === 'source' ? 'active' : ''} ${['generating', 'review', 'approved'].includes(step) ? 'completed' : ''}`}>
          <div className="step-number">{step !== 'source' ? <CheckCircle size={16} /> : '1'}</div>
          <span className="step-label">Upload BRD</span>
        </div>
        <div className={`step ${step === 'generating' ? 'active' : ''} ${['review', 'approved'].includes(step) ? 'completed' : ''}`}>
          <div className="step-number">{['review', 'approved'].includes(step) ? <CheckCircle size={16} /> : '2'}</div>
          <span className="step-label">Generate EPICs</span>
        </div>
        <div className={`step ${step === 'review' ? 'active' : ''} ${step === 'approved' ? 'completed' : ''}`}>
          <div className="step-number">{step === 'approved' ? <CheckCircle size={16} /> : '3'}</div>
          <span className="step-label">Review & Edit</span>
        </div>
        <div className={`step ${step === 'approved' ? 'active' : ''}`}>
          <div className="step-number">4</div>
          <span className="step-label">Generate Backlogs</span>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="error-banner">
          <AlertTriangle size={20} />
          <span>{error}</span>
          <button onClick={() => setError(null)}>
            <X size={16} />
          </button>
        </div>
      )}

      {/* Step 1: BRD Source */}
      {step === 'source' && (
        <div className="step-content">
          <div className="step-header">
            <Layers size={32} className="step-icon" />
            <h2>Generate EPICs from BRD</h2>
            <p>Upload your BRD document to automatically generate EPICs</p>
          </div>

          {/* Template and BRD Upload Row */}
          <div className="template-brd-row">
            {/* EPIC Template Section */}
            <div className="form-group template-section-outer">
              <label htmlFor="template">
                <Upload size={16} />
                EPIC Template
              </label>
              <div className="template-section">
                {isUsingDefaultTemplate && !templateFile ? (
                  <div className="template-selected default-template">
                    <FileText size={20} className="file-icon" />
                    <div className="template-info">
                      <span className="template-name">
                        <CheckCircle size={14} className="default-badge" />
                        Default EPIC Template
                      </span>
                      <span className="template-size">
                        {defaultEpicTemplate ? `${(defaultEpicTemplate.length / 1024).toFixed(1)} KB` : 'Loading...'}
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
                        ref={templateInputRef}
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
                    {isParsingTemplate && (
                      <div className="parsing-indicator">
                        <Loader2 className="spin" size={14} />
                      </div>
                    )}
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
                        ref={templateInputRef}
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

                {epicTemplate && (
                  <details className="template-preview">
                    <summary>
                      <ChevronDown size={14} />
                      Preview Template ({epicTemplate.split('\n').length} lines)
                    </summary>
                    <pre className="template-content">{epicTemplate}</pre>
                  </details>
                )}
              </div>
              <p className="input-hint">
                {isUsingDefaultTemplate
                  ? 'Using the default template with standard sections. Upload a custom template to override.'
                  : 'Custom template uploaded. Click "Use Default" to revert to the standard template.'}
              </p>
            </div>

            {/* Upload BRD Section */}
            <div className="form-group brd-upload-section">
              <label>
                <FileText size={16} />
                Upload BRD
              </label>
              {brdContent ? (
                <div className="brd-preview-card compact">
                  <FileText size={20} />
                  <div className="brd-info">
                    <span className="brd-title">{brdTitle || 'BRD Document'}</span>
                    <span className="brd-size">{brdContent.length.toLocaleString()} chars</span>
                  </div>
                  <button
                    type="button"
                    className="change-brd-btn"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <RefreshCw size={14} />
                    Change
                  </button>
                </div>
              ) : (
                <div className="brd-upload-area" onClick={() => fileInputRef.current?.click()}>
                  <Upload size={24} />
                  <span>Upload BRD Document</span>
                  <span className="upload-hint">.md, .docx</span>
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".md,.docx"
                onChange={handleFileUpload}
                style={{ display: 'none' }}
              />
            </div>
          </div>

          {/* Generation Mode Toggle */}
          <div className="generation-mode-section">
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
                  ? 'Draft mode generates EPICs quickly. Good for exploration and iteration.'
                  : 'Verified mode validates EPICs against BRD content. Slower but more accurate.'}
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
                      </option>
                    ))}
                  </select>
                )}
              </div>
            </div>

            {/* Advanced Options Toggle */}
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
                  <div className="option-group">
                    <label>
                      <Info size={14} />
                      Detail Level
                    </label>
                    <select
                      value={detailLevel}
                      onChange={(e) => setDetailLevel(e.target.value as 'concise' | 'standard' | 'detailed')}
                      className="option-select"
                    >
                      <option value="concise">Concise (1-2 paragraphs/section)</option>
                      <option value="standard">Standard (Recommended)</option>
                      <option value="detailed">Detailed (Comprehensive)</option>
                    </select>
                  </div>

                  <div className="section-config-container">
                    <button
                      type="button"
                      className="section-config-toggle"
                      onClick={() => setShowFieldConfig(!showFieldConfig)}
                    >
                      <Layers size={16} />
                      <span>Section Length Configuration</span>
                      {isParsingTemplate ? (
                        <span className="section-count">
                          <Loader2 size={14} className="spin" /> Parsing...
                        </span>
                      ) : (
                        <span className="section-count">{fieldConfigs.length} sections</span>
                      )}
                      {showFieldConfig ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>

                    {showFieldConfig && (
                      <div className="section-config-content">
                        <p className="section-config-hint">
                          Configure target word count for each section. Higher values = more detailed content.
                        </p>
                        {isParsingTemplate ? (
                          <div className="section-parsing-loading">
                            <Loader2 size={24} className="spin" />
                            <span>Analyzing template sections with AI...</span>
                          </div>
                        ) : (
                          <div className="section-config-list">
                            {fieldConfigs.map((field, index) => (
                              <div key={field.field_name} className="section-config-row">
                                <div className="section-name-col">
                                  <label className="section-name">{field.field_name.replace(/_/g, ' ')}</label>
                                </div>
                                <div className="section-controls">
                                  <div className="section-presets">
                                    <button
                                      type="button"
                                      className={`preset-btn ${field.target_words <= 75 ? 'active' : ''}`}
                                      onClick={() => updateFieldConfig(index, 'target_words', 50)}
                                      disabled={!field.enabled}
                                    >
                                      Concise
                                    </button>
                                    <button
                                      type="button"
                                      className={`preset-btn ${field.target_words > 75 && field.target_words <= 125 ? 'active' : ''}`}
                                      onClick={() => updateFieldConfig(index, 'target_words', 100)}
                                      disabled={!field.enabled}
                                    >
                                      Standard
                                    </button>
                                    <button
                                      type="button"
                                      className={`preset-btn ${field.target_words > 125 ? 'active' : ''}`}
                                      onClick={() => updateFieldConfig(index, 'target_words', 150)}
                                      disabled={!field.enabled}
                                    >
                                      Detailed
                                    </button>
                                  </div>
                                  <div className="section-words-input">
                                    <input
                                      type="number"
                                      min={20}
                                      max={500}
                                      step={10}
                                      value={field.target_words}
                                      onChange={(e) => updateFieldConfig(index, 'target_words', Math.max(20, Math.min(500, parseInt(e.target.value) || 100)))}
                                      disabled={!field.enabled}
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
          </div>

          {/* Generate Button - Main CTA */}
          {brdContent && (
            <div className="generate-action-section">
              <button className="btn btn-primary btn-lg" onClick={handleGenerateEpics}>
                <Sparkles size={20} />
                Generate EPICs
                <ArrowRight size={20} />
              </button>
              <p className="action-hint">AI will analyze your BRD and generate comprehensive EPICs</p>
            </div>
          )}

          {/* Empty State - No BRD */}
          {!brdContent && (
            <div className="empty-brd-state">
              <div className="empty-icon">
                <FileText size={48} />
              </div>
              <h3>No BRD Document</h3>
              <p>Upload a BRD document to generate EPICs</p>
            </div>
          )}
        </div>
      )}

      {/* Step 2: Generating */}
      {step === 'generating' && (
        <div className="generating-step">
          <div className="generating-header">
            <Loader2 className="spin" size={24} />
            <h2>Generating EPICs...</h2>
            <p>Analyzing BRD and creating comprehensive EPICs</p>
          </div>

          <div className="generation-progress">
            <div className="epics-preview">
              <h3>
                <Layers size={18} />
                EPICs Generated ({epics.length})
              </h3>
              {epics.map((epic) => (
                <div key={epic.id} className="epic-preview-item">
                  <span className="epic-id">{epic.id}</span>
                  <span className="epic-title">{epic.title}</span>
                </div>
              ))}
            </div>

            <div className="thinking-panel" ref={thinkingContainerRef}>
              <h3>
                <Sparkles size={18} />
                Progress
              </h3>
              <div className="thinking-steps">
                {thinkingSteps.map((step) => (
                  <div key={step.id} className="thinking-step">
                    <span className="step-content">{step.content}</span>
                  </div>
                ))}
                {isGenerating && (
                  <div className="thinking-step active">
                    <Loader2 className="spin" size={14} />
                    <span>Processing...</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Step 3: Review & Edit */}
      {step === 'review' && (
        <div className="review-step">
          <div className="review-header">
            <div className="header-left">
              <h2>Review Generated EPICs</h2>
              <span className="epic-count">{epics.length} EPICs</span>
              <span className={`approval-count ${approvedEpicsCount === epics.length ? 'all-approved' : ''}`}>
                <ShieldCheck size={14} />
                {approvedEpicsCount} / {epics.length} Approved
              </span>
            </div>
            <div className="review-actions">
              <button className="btn btn-outline" onClick={() => setStep('source')}>
                <ArrowLeft size={16} />
                Back
              </button>
              <button className="btn btn-secondary" onClick={handleDownload}>
                <Download size={16} />
                Download
              </button>
              {approvedEpicsCount < epics.length && (
                <button
                  className="btn btn-secondary"
                  onClick={handleApproveAllEpics}
                  title="Approve all EPICs"
                >
                  <ShieldCheck size={16} />
                  Approve All
                </button>
              )}
              <button
                className="btn btn-primary"
                onClick={handleApproveAndContinue}
                disabled={isSavingEpics || approvedEpicsCount === 0}
                title={approvedEpicsCount === 0 ? 'Approve at least one EPIC to continue' : ''}
              >
                {isSavingEpics ? (
                  <>
                    <Loader2 size={16} className="spinning" />
                    Saving EPICs...
                  </>
                ) : (
                  <>
                    Continue to Backlogs
                    <ArrowRight size={16} />
                  </>
                )}
              </button>
              {saveError && (
                <span className="error-text" style={{ color: 'var(--color-error)', fontSize: '0.875rem', marginLeft: '0.5rem' }}>
                  {saveError}
                </span>
              )}
            </div>
          </div>

          {/* Coverage Warning */}
          {uncoveredSections.length > 0 && (
            <div className="coverage-warning">
              <AlertTriangle size={20} />
              <div>
                <strong>Incomplete Coverage</strong>
                <p>The following BRD sections are not covered by any EPIC:</p>
                <div className="uncovered-sections">
                  {uncoveredSections.map((section) => (
                    <span key={section} className="section-tag">
                      {section}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* EPIC Table/Grid */}
          <div className="epic-table-container">
            <table className="epic-table">
              <thead>
                <tr>
                  <th className="col-expand"></th>
                  <th className="col-id">ID</th>
                  <th className="col-title">Title</th>
                  <th className="col-status">Status</th>
                  <th className="col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {epics.map((epic) => (
                  <Fragment key={epic.id}>
                    <tr className={`epic-row ${expandedEpics.has(epic.id) ? 'expanded' : ''}`}>
                      <td className="col-expand">
                        <button
                          className="expand-btn"
                          onClick={() => toggleEpicExpanded(epic.id)}
                        >
                          {expandedEpics.has(epic.id) ? (
                            <ChevronUp size={18} />
                          ) : (
                            <ChevronDown size={18} />
                          )}
                        </button>
                      </td>
                      <td className="col-id">
                        <span className="epic-id-badge">{epic.id}</span>
                      </td>
                      <td className="col-title">
                        <span className="epic-title-text">{epic.title}</span>
                        {epic.depends_on.length > 0 && (
                          <span className="deps-indicator" title={`Depends on: ${epic.depends_on.join(', ')}`}>
                            <GitBranch size={12} />
                            {epic.depends_on.length}
                          </span>
                        )}
                      </td>
                      <td className="col-status">
                        <button
                          className={`status-toggle-btn ${epic.status === 'approved' ? 'approved' : 'draft'}`}
                          onClick={() => handleToggleEpicApproval(epic.id)}
                          title={epic.status === 'approved' ? 'Click to revert to draft' : 'Click to approve'}
                        >
                          {epic.status === 'approved' ? (
                            <>
                              <ShieldCheck size={14} />
                              Approved
                            </>
                          ) : (
                            <>
                              <FileText size={14} />
                              Draft
                            </>
                          )}
                        </button>
                      </td>
                      <td className="col-actions">
                        <div className="action-menu-container">
                          <button
                            className="action-menu-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              setActionMenuOpen(actionMenuOpen === `create-${epic.id}` ? null : `create-${epic.id}`);
                            }}
                          >
                            <MoreVertical size={16} />
                          </button>
                          {actionMenuOpen === `create-${epic.id}` && (
                            <div className="action-menu" onClick={(e) => e.stopPropagation()}>
                              <button onClick={() => toggleEpicExpanded(epic.id)}>
                                <Eye size={14} />
                                View Details
                              </button>
                              <button onClick={() => handleStartEdit(epic)}>
                                <Edit3 size={14} />
                                Edit EPIC
                              </button>
                              <button onClick={() => setShowFeedbackFor(showFeedbackFor === epic.id ? null : epic.id)}>
                                <MessageSquare size={14} />
                                AI Feedback
                              </button>
                              <hr />
                              <button className="danger" onClick={() => handleDeleteEpicInCreate(epic.id)}>
                                <Trash2 size={14} />
                                Delete
                              </button>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>

                    {/* Expanded Details Row */}
                    {expandedEpics.has(epic.id) && (
                      <tr className="epic-details-row">
                        <td colSpan={5}>
                          <div className="epic-details-content">
                            {editingEpicId === epic.id ? (
                              /* Edit Mode */
                              <div className="epic-edit-form">
                                <div className="edit-field">
                                  <label>Title</label>
                                  <input
                                    type="text"
                                    value={editFormData.title || ''}
                                    onChange={(e) => setEditFormData({ ...editFormData, title: e.target.value })}
                                  />
                                </div>
                                <div className="edit-field">
                                  <label>Description</label>
                                  <textarea
                                    value={editFormData.description || ''}
                                    onChange={(e) => setEditFormData({ ...editFormData, description: e.target.value })}
                                    rows={4}
                                  />
                                </div>
                                <div className="edit-field">
                                  <label>Business Value</label>
                                  <textarea
                                    value={editFormData.business_value || ''}
                                    onChange={(e) => setEditFormData({ ...editFormData, business_value: e.target.value })}
                                    rows={3}
                                  />
                                </div>
                                <div className="edit-actions">
                                  <button className="btn btn-primary" onClick={handleSaveEdit}>
                                    <Save size={16} />
                                    Save Changes
                                  </button>
                                  <button className="btn btn-outline" onClick={handleCancelEdit}>
                                    <RotateCcw size={16} />
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            ) : (
                              /* View Mode */
                              <div className="epic-view-content">
                                <div className="detail-section">
                                  <h4>Description</h4>
                                  <p>{epic.description}</p>
                                </div>
                                <div className="detail-section">
                                  <h4>Business Value</h4>
                                  <p>{epic.business_value}</p>
                                </div>
                                {epic.objectives.length > 0 && (
                                  <div className="detail-section">
                                    <h4>Objectives</h4>
                                    <ul>
                                      {epic.objectives.map((obj, i) => (
                                        <li key={i}>{obj}</li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                                {epic.acceptance_criteria.length > 0 && (
                                  <div className="detail-section">
                                    <h4>Acceptance Criteria</h4>
                                    <ul>
                                      {epic.acceptance_criteria.map((ac, i) => (
                                        <li key={i}>{ac}</li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                                {epic.affected_components.length > 0 && (
                                  <div className="detail-section">
                                    <h4>Affected Components</h4>
                                    <div className="component-tags">
                                      {epic.affected_components.map((comp) => (
                                        <span key={comp} className="component-tag">
                                          {comp}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                {epic.depends_on.length > 0 && (
                                  <div className="detail-section">
                                    <h4>Dependencies</h4>
                                    <div className="dependency-tags">
                                      {epic.depends_on.map((dep) => (
                                        <span key={dep} className="dependency-tag">
                                          <GitBranch size={12} />
                                          {dep}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}

                            {/* AI Feedback Section */}
                            {showFeedbackFor === epic.id && !editingEpicId && (
                              <div className="ai-feedback-section">
                                <h4>
                                  <Sparkles size={16} />
                                  Regenerate with AI Feedback
                                </h4>
                                <textarea
                                  value={epicFeedback[epic.id] || ''}
                                  onChange={(e) =>
                                    setEpicFeedback((prev) => ({
                                      ...prev,
                                      [epic.id]: e.target.value,
                                    }))
                                  }
                                  placeholder="Describe how you'd like to improve this EPIC..."
                                  rows={3}
                                />
                                <button
                                  className="btn btn-primary"
                                  onClick={() => handleRefineEpic(epic.id)}
                                  disabled={!epicFeedback[epic.id]?.trim() || refiningEpicId === epic.id}
                                >
                                  {refiningEpicId === epic.id ? (
                                    <Loader2 className="spin" size={16} />
                                  ) : (
                                    <Send size={16} />
                                  )}
                                  Regenerate EPIC
                                </button>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Step 4: Approved - Continue to Backlogs */}
      {step === 'approved' && (
        <div className="approved-step">
          <div className="approved-header">
            <CheckCircle size={48} className="success-icon" />
            <h2>EPICs Approved</h2>
            <p>{epics.length} EPICs are ready for backlog generation</p>
          </div>

          <div className="approved-summary">
            <div className="summary-card">
              <h3>Summary</h3>
              <div className="summary-stats">
                <div className="stat">
                  <span className="stat-value">{epics.length}</span>
                  <span className="stat-label">Total EPICs</span>
                </div>
                <div className="stat">
                  <span className="stat-value">
                    {epics.filter((e) => e.status === 'approved').length}
                  </span>
                  <span className="stat-label">Approved</span>
                </div>
                <div className="stat">
                  <span className="stat-value">
                    {new Set(epics.flatMap((e) => e.affected_components)).size}
                  </span>
                  <span className="stat-label">Components</span>
                </div>
              </div>
            </div>

            <div className="epic-list-summary">
              <h3>Approved EPICs</h3>
              {recommendedOrder.length > 0 ? (
                <ol className="ordered-epics">
                  {recommendedOrder.map((epicId) => {
                    const epic = epics.find((e) => e.id === epicId);
                    if (!epic) return null;
                    return (
                      <li key={epicId}>
                        <span className="epic-id">{epic.id}</span>
                        <span className="epic-title">{epic.title}</span>
                      </li>
                    );
                  })}
                </ol>
              ) : (
                <ul className="epic-list">
                  {epics.map((epic) => (
                    <li key={epic.id}>
                      <span className="epic-id">{epic.id}</span>
                      <span className="epic-title">{epic.title}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="approved-actions">
            <button className="btn btn-outline" onClick={() => setStep('review')}>
              <ArrowLeft size={16} />
              Back to Review
            </button>
            <button className="btn btn-secondary" onClick={handleDownload}>
              <Download size={16} />
              Download EPICs
            </button>
            <button className="btn btn-primary btn-lg" onClick={handleContinueToBacklogs}>
              Continue to Backlogs
              <ArrowRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
