import { useState, useRef, useEffect } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import {
  ListTodo,
  Upload,
  Layers,
  ArrowRight,
  ArrowLeft,
  Loader2,
  CheckCircle,
  RefreshCw,
  Download,
  ExternalLink,
  Trash2,
  MessageSquare,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  X,
  Send,
  Sparkles,
  Target,
  FileText,
  User,
  Zap,
  Bug,
  HelpCircle,
  Settings,
  Shield,
  ShieldCheck,
  Brain,
  Info,
  Plus,
  Eye,
  Calendar,
  ArrowUp,
  ArrowDown,
} from 'lucide-react';
import {
  generateBacklogsStream,
  refineBacklogItem,
  regenerateBacklogsForEpic,
  getBRDDetail,
  saveBacklogsForEpic,
  parseBacklogTemplateFields,
  getDefaultBacklogTemplate,
  listAvailableModels,
  getAllBacklogs,
  getEpicDetail,
  type Epic,
  type BacklogItem,
  type BacklogStreamEvent,
  type GenerateBacklogsRequest,
  type CoverageMatrixEntry,
  type StoredBRD,
  type StoredBacklog,
  type StoredEpic,
  type BacklogFieldConfig,
  type BacklogTemplateConfig,
  type AnalyzeEpicsForBacklogsResponse,
  type ModelInfo,
  type GenerationMode,
} from '../../services/api';
import { useQuery } from '@tanstack/react-query';
import mammoth from 'mammoth';
import './GenerateBacklogs.css';

interface ThinkingStep {
  id: number;
  content: string;
  timestamp: Date;
}

type ViewMode = 'list' | 'create';
type WorkflowStep = 'source' | 'generating' | 'review' | 'approved';
type StatusFilter = 'all' | 'draft' | 'approved';
type SortField = 'title' | 'epic' | 'type' | 'priority' | 'updated';
type SortDirection = 'asc' | 'desc';

const priorityColors: Record<string, string> = {
  critical: 'badge-error',
  high: 'badge-warning',
  medium: 'badge-info',
  low: 'badge-pending',
};

const itemTypeIcons: Record<string, React.ReactNode> = {
  user_story: <User size={14} />,
  task: <Zap size={14} />,
  spike: <HelpCircle size={14} />,
  bug: <Bug size={14} />,
};

const itemTypeLabels: Record<string, string> = {
  user_story: 'Story',
  task: 'Task',
  spike: 'Spike',
  bug: 'Bug',
};

// Generate a deterministic seed from a string (for reproducible outputs)
function generateSeedFromString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash) % 1000000;
}

// Default values for generation options
const DEFAULT_OPTIONS = {
  mode: 'draft' as GenerationMode,
  temperature: 0,
  seed: undefined as number | undefined,
};

export function GenerateBacklogs() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const thinkingContainerRef = useRef<HTMLDivElement>(null);

  // View mode state
  const [viewMode, setViewMode] = useState<ViewMode>('list');

  // Backlog List state
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [sortField, setSortField] = useState<SortField>('updated');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [expandedBacklogId, setExpandedBacklogId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Selected EPIC for generation (from URL param)
  const [selectedStoredEpic, setSelectedStoredEpic] = useState<StoredEpic | null>(null);
  const [isLoadingEpic, setIsLoadingEpic] = useState(false);

  // Workflow state
  const [step, setStep] = useState<WorkflowStep>('source');

  // Source data from navigation state
  const [epics, setEpics] = useState<Epic[]>(location.state?.epics || []);
  const [brdContent, setBrdContent] = useState<string>(location.state?.brdContent || '');
  const [brdId, setBrdId] = useState<string>(location.state?.brdId || `BRD-${Date.now()}`);
  const [brdTitle, setBrdTitle] = useState<string>(location.state?.brdTitle || '');

  // Database BRD state
  const [storedBRD, setStoredBRD] = useState<StoredBRD | null>(null);
  const [isLoadingBRD, setIsLoadingBRD] = useState(false);
  const [, setLoadError] = useState<string | null>(null);

  // Saved backlogs state
  const [, setSavedBacklogs] = useState<StoredBacklog[]>([]);
  const [, setIsSavingBacklogs] = useState(false);
  const [, setSaveError] = useState<string | null>(null);

  // Generation state
  const [isGenerating, setIsGenerating] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const [backlogItems, setBacklogItems] = useState<BacklogItem[]>([]);
  const [, setItemsByEpic] = useState<Record<string, string[]>>({});
  const [, setCoverageMatrix] = useState<CoverageMatrixEntry[]>([]);
  const [, setTotalStoryPoints] = useState(0);
  const [, setRecommendedOrder] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Refinement state
  const [refiningItemId, setRefiningItemId] = useState<string | null>(null);
  const [itemFeedback, setItemFeedback] = useState<Record<string, string>>({});
  const [showFeedbackFor, setShowFeedbackFor] = useState<string | null>(null);
  const [globalFeedback, setGlobalFeedback] = useState('');
  const [regeneratingEpicId, setRegeneratingEpicId] = useState<string | null>(null);

  // Expanded state
  const [expandedEpics, setExpandedEpics] = useState<Set<string>>(new Set());
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());

  // Generation mode and model state
  const [mode, setMode] = useState<GenerationMode>(DEFAULT_OPTIONS.mode);
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [seed, setSeed] = useState<number | undefined>(DEFAULT_OPTIONS.seed);
  const temperature = DEFAULT_OPTIONS.temperature;
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false);

  // Template configuration state
  const [backlogTemplate, setBacklogTemplate] = useState<string>('');
  const [defaultBacklogTemplate, setDefaultBacklogTemplate] = useState<string>('');
  const [isUsingDefaultTemplate, setIsUsingDefaultTemplate] = useState(true);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [isParsingTemplate, setIsParsingTemplate] = useState(false);
  const [showFieldConfig, setShowFieldConfig] = useState(false);
  const [fieldConfigs, setFieldConfigs] = useState<BacklogFieldConfig[]>([
    { field_name: 'description', enabled: true, target_words: 80 },
    { field_name: 'acceptance_criteria', enabled: true, target_words: 30 },
    { field_name: 'technical_notes', enabled: true, target_words: 50 },
  ]);
  const [detailLevel, setDetailLevel] = useState<'concise' | 'standard' | 'detailed'>('standard');
  const [defaultDescWords] = useState(80);
  const [defaultACCount] = useState(4);
  const templateInputRef = useRef<HTMLInputElement>(null);

  // EPIC Analysis state (simplified - no longer using analysis step)
  const [epicAnalysis, setEpicAnalysis] = useState<AnalyzeEpicsForBacklogsResponse | null>(null);

  // Fetch all backlogs for list view
  const {
    data: backlogsResponse,
    isLoading: isLoadingBacklogs,
    refetch: refetchBacklogs,
  } = useQuery({
    queryKey: ['backlogs'],
    queryFn: () => getAllBacklogs({}),
    enabled: viewMode === 'list',
  });

  // Extract backlogs array from response
  const storedBacklogsList = backlogsResponse?.data || [];

  // Handle epic_id URL parameter - auto-load EPIC
  useEffect(() => {
    const epicId = searchParams.get('epic_id');
    if (epicId && !selectedStoredEpic && !isLoadingEpic) {
      setIsLoadingEpic(true);
      getEpicDetail(epicId)
        .then((epic) => {
          setSelectedStoredEpic(epic);
          // Also set up the epics array for generation
          const convertedEpic: Epic = {
            id: epic.id,
            title: epic.title,
            description: epic.description,
            brd_id: epic.brd_id || '',
            brd_section_refs: [],
            business_value: epic.business_value || '',
            objectives: epic.objectives || [],
            acceptance_criteria: epic.acceptance_criteria || [],
            status: 'draft' as const,
            depends_on: epic.depends_on || [],
            blocks: [],
            affected_components: epic.affected_components || [],
            refinement_count: epic.refinement_count || 0,
            created_at: epic.created_at,
          };
          setEpics([convertedEpic]);
          // If EPIC has a BRD, load it
          if (epic.brd_id) {
            setBrdId(epic.brd_id);
          }
          // Switch to create view for backlog generation
          setViewMode('create');
          setIsLoadingEpic(false);
        })
        .catch((err) => {
          console.error('Failed to load EPIC:', err);
          setIsLoadingEpic(false);
        });
    }
  }, [searchParams, selectedStoredEpic, isLoadingEpic]);

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

  // Load default Backlog template on mount
  useEffect(() => {
    const loadDefaultTemplate = async () => {
      try {
        const response = await getDefaultBacklogTemplate();
        if (response.success && response.template) {
          setDefaultBacklogTemplate(response.template);
          setBacklogTemplate(response.template);
          // Set field configs from default template
          if (response.fields.length > 0) {
            setFieldConfigs(response.fields);
          }
        }
      } catch (err) {
        console.error('Failed to load default Backlog template:', err);
      }
    };
    loadDefaultTemplate();
  }, []);

  // Auto-generate seed from BRD and EPICs content for reproducible outputs
  useEffect(() => {
    if (brdContent && brdId && epics.length > 0) {
      const epicTitles = epics.map(e => e.title).join(',');
      const seedInput = `${brdId}:${epicTitles}:${brdContent.substring(0, 300)}`;
      const generatedSeed = generateSeedFromString(seedInput);
      setSeed(generatedSeed);
    }
  }, [brdContent, brdId, epics]);

  // Auto-expand all EPICs initially
  useEffect(() => {
    if (epics.length > 0 && expandedEpics.size === 0) {
      setExpandedEpics(new Set(epics.map((e) => e.id)));
    }
  }, [epics]);

  // Load BRD with EPICs from database if brd_id is in URL
  useEffect(() => {
    const brdIdParam = searchParams.get('brd_id');
    if (brdIdParam && !storedBRD && !isLoadingBRD) {
      setIsLoadingBRD(true);
      setLoadError(null);
      getBRDDetail(brdIdParam)
        .then((brd) => {
          setStoredBRD(brd);
          setBrdContent(brd.markdown_content);
          setBrdId(brd.brd_number);
          setBrdTitle(brd.title);
          // Convert stored EPICs to Epic format for generation
          if (brd.epics && brd.epics.length > 0) {
            const convertedEpics: Epic[] = brd.epics.map((e) => ({
              id: e.id,
              title: e.title,
              description: e.description,
              brd_id: brd.id,
              brd_section_refs: [],
              business_value: e.business_value || '',
              objectives: e.objectives || [],
              acceptance_criteria: e.acceptance_criteria || [],
              status: 'draft' as const,
              depends_on: e.depends_on || [],
              blocks: [],
              affected_components: e.affected_components || [],
              refinement_count: e.refinement_count || 0,
              created_at: e.created_at,
            }));
            setEpics(convertedEpics);
          }
          setIsLoadingBRD(false);
        })
        .catch((err) => {
          console.error('Failed to load BRD:', err);
          setLoadError('Failed to load BRD from library');
          setIsLoadingBRD(false);
        });
    }
  }, [searchParams, storedBRD, isLoadingBRD]);

  // Parse EPIC content from markdown text
  const parseEpicsFromMarkdown = (content: string): { epics: Epic[], brdTitle?: string } => {
    const epics: Epic[] = [];
    // Try to parse EPICs from markdown format
    // Expected format: ## EPIC-001: Title followed by content
    const epicPattern = /##\s*(EPIC-\d+):\s*(.+?)(?=\n##\s*EPIC-|\n##\s*$|$)/gs;
    let match;

    while ((match = epicPattern.exec(content)) !== null) {
      const id = match[1];
      const sectionContent = match[2];
      const titleMatch = sectionContent.match(/^([^\n]+)/);
      const title = titleMatch ? titleMatch[1].trim() : id;

      epics.push({
        id,
        title,
        description: sectionContent.trim(),
        brd_id: '',
        brd_section_refs: [],
        business_value: '',
        objectives: [],
        acceptance_criteria: [],
        status: 'draft' as const,
        depends_on: [],
        blocks: [],
        affected_components: [],
        refinement_count: 0,
        created_at: new Date().toISOString(),
      });
    }

    return { epics };
  };

  // Handle file upload (for importing EPICs from .md or .docx)
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const fileName = file.name.toLowerCase();
    let content = '';

    try {
      if (fileName.endsWith('.docx')) {
        // Parse .docx file using mammoth
        const arrayBuffer = await file.arrayBuffer();
        const result = await mammoth.extractRawText({ arrayBuffer });
        content = result.value;
      } else if (fileName.endsWith('.md')) {
        // Read .md file as text
        content = await file.text();
      } else {
        setError('Please upload a Markdown (.md) or Word (.docx) file');
        return;
      }

      // Try to parse as JSON first (for exported EPIC files)
      try {
        const parsed = JSON.parse(content);
        if (parsed.epics && Array.isArray(parsed.epics)) {
          setEpics(parsed.epics);
          if (parsed.brdContent) setBrdContent(parsed.brdContent);
          if (parsed.brdId) setBrdId(parsed.brdId);
          if (parsed.brdTitle) setBrdTitle(parsed.brdTitle);
          return;
        }
      } catch {
        // Not JSON, try to parse as markdown
      }

      // Parse as markdown EPIC document
      const parsed = parseEpicsFromMarkdown(content);
      if (parsed.epics.length > 0) {
        setEpics(parsed.epics);
        setBrdTitle(file.name.replace(/\.(md|docx)$/i, ''));
      } else {
        setError('Could not find EPICs in the document. Please ensure the file contains EPICs in the expected format (## EPIC-001: Title).');
      }
    } catch (err) {
      console.error('Failed to parse file:', err);
      setError('Failed to read the file. Please try a different file.');
    }
  };

  // Handle Backlog template upload
  const handleTemplateUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.md') && !file.name.endsWith('.txt')) {
      setError('Please upload a Markdown (.md) or text (.txt) file');
      return;
    }

    const content = await file.text();
    setBacklogTemplate(content);
    setTemplateFile(file);
    setIsUsingDefaultTemplate(false);
    setError(null);

    // Parse template to get field configs
    setIsParsingTemplate(true);
    try {
      const result = await parseBacklogTemplateFields(content);
      if (result.success && result.fields.length > 0) {
        setFieldConfigs(result.fields);
      }
    } catch (err) {
      console.error('Template parsing failed:', err);
    } finally {
      setIsParsingTemplate(false);
    }
  };

  // Clear template and revert to default
  const handleUseDefaultTemplate = async () => {
    setTemplateFile(null);
    setBacklogTemplate(defaultBacklogTemplate);
    setIsUsingDefaultTemplate(true);
    if (templateInputRef.current) {
      templateInputRef.current.value = '';
    }

    // Reset field configs to default template fields
    try {
      const response = await getDefaultBacklogTemplate();
      if (response.success && response.fields && response.fields.length > 0) {
        setFieldConfigs(response.fields);
      }
    } catch (err) {
      console.error('Failed to load default template fields:', err);
    }
  };

  // Download current template
  const handleDownloadTemplate = () => {
    if (!backlogTemplate) return;
    const blob = new Blob([backlogTemplate], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = isUsingDefaultTemplate ? 'default-backlog-template.md' : 'custom-backlog-template.md';
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
  const updateFieldConfig = (index: number, key: keyof BacklogFieldConfig, value: any) => {
    setFieldConfigs((prev) =>
      prev.map((field, i) =>
        i === index ? { ...field, [key]: value } : field
      )
    );
  };

  // Generate User Stories directly (simplified flow)
  const handleGenerateStories = () => {
    setEpicAnalysis(null);
    handleGenerateBacklogs();
  };

  // Generate Backlogs (with optional analysis guidance)
  const handleGenerateBacklogs = async () => {
    if (epics.length === 0) {
      setError('No EPICs available. Please go back and generate EPICs first.');
      return;
    }

    setIsGenerating(true);
    setStep('generating');
    setThinkingSteps([]);
    setBacklogItems([]);
    setError(null);

    // Build template config if custom settings are used
    const templateConfig: BacklogTemplateConfig | undefined = backlogTemplate || showFieldConfig ? {
      backlog_template: backlogTemplate || undefined,
      field_configs: fieldConfigs,
      default_description_words: defaultDescWords,
      default_acceptance_criteria_count: defaultACCount,
      default_technical_notes_words: 50,
      require_user_story_format: true,
      include_technical_notes: true,
      include_file_references: true,
      include_story_points: true,
    } : undefined;

    // Use analysis-based items count or default to 5
    const itemsPerEpic = epicAnalysis && epicAnalysis.epic_analyses.length > 0
      ? Math.ceil(epicAnalysis.total_recommended_items / epicAnalysis.epic_analyses.length)
      : 5;

    const request: GenerateBacklogsRequest = {
      brd_id: brdId,
      brd_markdown: brdContent,
      epics: epics,
      mode: mode,
      items_per_epic: itemsPerEpic,
      include_technical_tasks: true,
      include_spikes: true,
      backlog_template: backlogTemplate || undefined,
      template_config: templateConfig,
      default_description_words: defaultDescWords,
      default_acceptance_criteria_count: defaultACCount,
      epic_analysis: epicAnalysis || undefined,
      model: selectedModel || undefined,
      temperature: temperature,
      seed: seed,
    };

    let stepId = 0;

    await generateBacklogsStream(
      request,
      (event: BacklogStreamEvent) => {
        if (event.type === 'thinking' && event.content) {
          stepId++;
          setThinkingSteps((prev) => [
            ...prev,
            { id: stepId, content: event.content!, timestamp: new Date() },
          ]);
        } else if (event.type === 'item' && event.item) {
          setBacklogItems((prev) => [...prev, event.item!]);
        } else if (event.type === 'complete' && event.data) {
          setBacklogItems(event.data.items);
          setItemsByEpic(event.data.items_by_epic);
          setCoverageMatrix(event.data.coverage_matrix);
          setTotalStoryPoints(event.data.total_story_points);
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

  // Refine single item
  const handleRefineItem = async (itemId: string) => {
    const feedback = itemFeedback[itemId];
    if (!feedback?.trim()) return;

    const itemToRefine = backlogItems.find((i) => i.id === itemId);
    if (!itemToRefine) return;

    const epic = epics.find((e) => e.id === itemToRefine.epic_id);
    if (!epic) return;

    setRefiningItemId(itemId);

    try {
      const refined = await refineBacklogItem(itemId, {
        item_id: itemId,
        current_item: itemToRefine,
        user_feedback: feedback,
        epic: epic,
        brd_sections_content: [brdContent],
      });

      setBacklogItems((prev) => prev.map((i) => (i.id === itemId ? refined : i)));
      setItemFeedback((prev) => ({ ...prev, [itemId]: '' }));
      setShowFeedbackFor(null);
    } catch (err) {
      setError(`Failed to refine item: ${(err as Error).message}`);
    } finally {
      setRefiningItemId(null);
    }
  };

  // Regenerate all items for a specific EPIC
  const handleRegenerateForEpic = async (epicId: string) => {
    const epic = epics.find((e) => e.id === epicId);
    if (!epic) return;

    setRegeneratingEpicId(epicId);

    try {
      const newItems = await regenerateBacklogsForEpic(
        epicId,
        epic,
        brdContent,
        globalFeedback || undefined,
        5
      );

      // Replace items for this EPIC
      setBacklogItems((prev) => {
        const otherItems = prev.filter((i) => i.epic_id !== epicId);
        return [...otherItems, ...newItems];
      });

      // Update items by epic mapping
      setItemsByEpic((prev) => ({
        ...prev,
        [epicId]: newItems.map((i) => i.id),
      }));
    } catch (err) {
      setError(`Failed to regenerate items: ${(err as Error).message}`);
    } finally {
      setRegeneratingEpicId(null);
    }
  };

  // Delete item
  const handleDeleteItem = (itemId: string) => {
    const item = backlogItems.find((i) => i.id === itemId);
    if (!item) return;

    setBacklogItems((prev) => prev.filter((i) => i.id !== itemId));
    setItemsByEpic((prev) => ({
      ...prev,
      [item.epic_id]: prev[item.epic_id]?.filter((id) => id !== itemId) || [],
    }));
  };

  // Toggle EPIC expansion
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

  // Toggle item expansion
  const toggleItemExpanded = (itemId: string) => {
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else {
        next.add(itemId);
      }
      return next;
    });
  };

  // Approve backlogs and save to database
  const handleApprove = async () => {
    setIsSavingBacklogs(true);
    setSaveError(null);

    try {
      // Case 1: If we came from EPIC detail view (selectedStoredEpic is set)
      if (selectedStoredEpic && backlogItems.length > 0) {
        const backlogData = backlogItems.map((item) => ({
          title: item.title,
          description: item.description,
          item_type: item.item_type,
          as_a: item.as_a,
          i_want: item.i_want,
          so_that: item.so_that,
          acceptance_criteria: item.acceptance_criteria,
          technical_notes: item.technical_notes,
          files_to_modify: item.files_to_modify,
          files_to_create: item.files_to_create,
          priority: item.priority,
          story_points: item.story_points,
        }));
        const saved = await saveBacklogsForEpic(selectedStoredEpic.id, backlogData);
        setSavedBacklogs((prev) => [...prev, ...saved]);
      }
      // Case 2: If we have stored BRD with EPICs
      else if (storedBRD && storedBRD.epics && storedBRD.epics.length > 0) {
        // Group backlog items by epic and save
        for (const storedEpic of storedBRD.epics) {
          const epicItems = backlogItems.filter((item) =>
            epics.find((e) => e.id === item.epic_id)?.title === storedEpic.title
          );
          if (epicItems.length > 0) {
            const backlogData = epicItems.map((item) => ({
              title: item.title,
              description: item.description,
              item_type: item.item_type,
              as_a: item.as_a,
              i_want: item.i_want,
              so_that: item.so_that,
              acceptance_criteria: item.acceptance_criteria,
              technical_notes: item.technical_notes,
              files_to_modify: item.files_to_modify,
              files_to_create: item.files_to_create,
              priority: item.priority,
              story_points: item.story_points,
            }));
            const saved = await saveBacklogsForEpic(storedEpic.id, backlogData);
            setSavedBacklogs((prev) => [...prev, ...saved]);
          }
        }
      }
      // Case 3: If we have epics array with database IDs (from generation)
      else if (epics.length > 0 && backlogItems.length > 0) {
        // Group backlog items by epic_id and save
        const epicIds = [...new Set(backlogItems.map((item) => item.epic_id))];
        for (const epicId of epicIds) {
          const epicItems = backlogItems.filter((item) => item.epic_id === epicId);
          // Find the stored epic ID - check if the epic has a database ID format
          const epic = epics.find((e) => e.id === epicId);
          if (epic && epicItems.length > 0) {
            // Use the epic's database ID if it looks like a UUID, otherwise skip
            const isUUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(epicId);
            if (isUUID) {
              const backlogData = epicItems.map((item) => ({
                title: item.title,
                description: item.description,
                item_type: item.item_type,
                as_a: item.as_a,
                i_want: item.i_want,
                so_that: item.so_that,
                acceptance_criteria: item.acceptance_criteria,
                technical_notes: item.technical_notes,
                files_to_modify: item.files_to_modify,
                files_to_create: item.files_to_create,
                priority: item.priority,
                story_points: item.story_points,
              }));
              const saved = await saveBacklogsForEpic(epicId, backlogData);
              setSavedBacklogs((prev) => [...prev, ...saved]);
            }
          }
        }
      }

      setIsSavingBacklogs(false);
    } catch (err) {
      console.error('Failed to save backlogs:', err);
      setSaveError('Failed to save some backlogs');
      setIsSavingBacklogs(false);
    }

    setStep('approved');
  };

  // Download backlogs as markdown
  const handleDownload = () => {
    const content = epics
      .map((epic) => {
        const epicItems = backlogItems.filter((i) => i.epic_id === epic.id);
        const itemsContent = epicItems
          .map(
            (item) => `### ${item.id}: ${item.title}

**Priority:** ${item.priority}

${
  item.as_a
    ? `**As a** ${item.as_a}
**I want** ${item.i_want}
**So that** ${item.so_that}

`
    : ''
}**Description:**
${item.description}

**Acceptance Criteria:**
${item.acceptance_criteria.map((c) => `- [ ] ${c}`).join('\n')}

${item.pre_conditions && item.pre_conditions.length > 0 ? `**Pre-conditions:**\n${item.pre_conditions.map((c) => `- ${c}`).join('\n')}\n\n` : ''}${item.post_conditions && item.post_conditions.length > 0 ? `**Post-conditions:**\n${item.post_conditions.map((c) => `- ${c}`).join('\n')}\n\n` : ''}${item.testing_approach ? `**Testing Approach:**\n${item.testing_approach}\n\n` : ''}${item.edge_cases && item.edge_cases.length > 0 ? `**Edge Cases:**\n${item.edge_cases.map((c) => `- ${c}`).join('\n')}\n\n` : ''}${item.implementation_notes || item.technical_notes ? `**Implementation Notes:**\n${item.implementation_notes || item.technical_notes}\n\n` : ''}${item.ui_ux_notes ? `**UI/UX Notes:**\n${item.ui_ux_notes}\n\n` : ''}${item.files_to_modify.length > 0 ? `**Files to Modify:**\n${item.files_to_modify.map((f) => `- ${f}`).join('\n')}\n\n` : ''}${item.files_to_create.length > 0 ? `**Files to Create:**\n${item.files_to_create.map((f) => `- ${f}`).join('\n')}\n` : ''}
---
`
          )
          .join('\n');

        return `# EPIC: ${epic.id} - ${epic.title}

${itemsContent}`;
      })
      .join('\n\n');

    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `UserStories-${brdId}-${new Date().toISOString().split('T')[0]}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Get items for an EPIC
  const getItemsForEpic = (epicId: string): BacklogItem[] => {
    return backlogItems.filter((i) => i.epic_id === epicId);
  };

  // Calculate stats
  const stats = {
    totalItems: backlogItems.length,
    totalPoints: 0, // No longer tracking story points
    byType: backlogItems.reduce((acc, i) => {
      acc[i.item_type] = (acc[i.item_type] || 0) + 1;
      return acc;
    }, {} as Record<string, number>),
    byPriority: backlogItems.reduce((acc, i) => {
      acc[i.priority] = (acc[i.priority] || 0) + 1;
      return acc;
    }, {} as Record<string, number>),
  };

  // Filter and sort backlogs for list view
  const getFilteredBacklogs = () => {
    if (storedBacklogsList.length === 0) return [];
    let filtered = [...storedBacklogsList];

    // Apply status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter((b) => b.status === statusFilter);
    }

    // Apply search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (b) =>
          b.title.toLowerCase().includes(query) ||
          b.description?.toLowerCase().includes(query)
      );
    }

    // Apply sorting
    filtered.sort((a, b) => {
      let comparison = 0;
      switch (sortField) {
        case 'title':
          comparison = a.title.localeCompare(b.title);
          break;
        case 'epic':
          comparison = (a.epic_title || '').localeCompare(b.epic_title || '');
          break;
        case 'type':
          comparison = a.item_type.localeCompare(b.item_type);
          break;
        case 'priority':
          const priorityOrder: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
          comparison = (priorityOrder[a.priority] ?? 4) - (priorityOrder[b.priority] ?? 4);
          break;
        case 'updated':
        default:
          comparison = new Date(b.updated_at || b.created_at).getTime() -
            new Date(a.updated_at || a.created_at).getTime();
          break;
      }
      return sortDirection === 'asc' ? comparison : -comparison;
    });

    return filtered;
  };

  const filteredBacklogs = getFilteredBacklogs();

  // Toggle sort
  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  // Toggle backlog expansion in list view
  const toggleBacklogExpanded = (backlogId: string) => {
    setExpandedBacklogId(expandedBacklogId === backlogId ? null : backlogId);
  };

  // Handle new backlog generation
  const handleNewBacklogGeneration = () => {
    setViewMode('create');
    setSelectedStoredEpic(null);
  };

  // Format date for display
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  return (
    <div className="generate-backlogs-page">
      {/* List View */}
      {viewMode === 'list' && (
        <div className="backlog-list-view">
          {/* Header - matches EPIC screen */}
          <div className="library-header">
            <div className="header-left">
              <ListTodo size={28} />
              <div>
                <h1>Backlog Items</h1>
                <p>Manage your backlog items and generate new ones</p>
              </div>
            </div>
            <div className="header-actions">
              <button className="btn btn-primary" onClick={handleNewBacklogGeneration}>
                <Plus size={16} />
                Generate New Backlogs
              </button>
            </div>
          </div>

          {/* Toolbar - matches EPIC screen */}
          <div className="library-toolbar">
            <div className="toolbar-left">
              {/* Status Filter Tabs */}
              <div className="filter-tabs">
                <button
                  className={`filter-btn ${statusFilter === 'all' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('all')}
                >
                  All ({storedBacklogsList.length})
                </button>
                <button
                  className={`filter-btn ${statusFilter === 'draft' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('draft')}
                >
                  <FileText size={14} />
                  Draft ({storedBacklogsList.filter((b) => b.status === 'draft').length})
                </button>
                <button
                  className={`filter-btn completed ${statusFilter === 'approved' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('approved')}
                >
                  <ShieldCheck size={14} />
                  Approved ({storedBacklogsList.filter((b) => b.status === 'approved').length})
                </button>
              </div>
            </div>

            <div className="toolbar-right">
              <input
                type="text"
                placeholder="Search backlogs..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="search-input"
              />
              <button
                className="btn btn-outline refresh-btn"
                onClick={() => refetchBacklogs()}
                disabled={isLoadingBacklogs}
              >
                <RefreshCw size={16} className={isLoadingBacklogs ? 'spinning' : ''} />
                Refresh
              </button>
            </div>
          </div>

          {/* Backlog Grid/Table */}
          {isLoadingBacklogs ? (
            <div className="loading-state">
              <Loader2 className="spin" size={32} />
              <span>Loading backlogs...</span>
            </div>
          ) : filteredBacklogs.length === 0 ? (
            <div className="empty-state">
              <ListTodo size={48} />
              <h3>No Backlog Items Found</h3>
              <p>
                {searchQuery || statusFilter !== 'all'
                  ? 'Try adjusting your filters or search query'
                  : 'Generate backlog items from your EPICs'}
              </p>
              {!searchQuery && statusFilter === 'all' && (
                <button className="btn btn-primary" onClick={handleNewBacklogGeneration}>
                  <Plus size={18} />
                  Generate Backlogs
                </button>
              )}
            </div>
          ) : (
            <div className="backlog-table-container">
              <table className="backlog-table">
                <thead>
                  <tr>
                    <th className="col-expand"></th>
                    <th className="col-status">Status</th>
                    <th className="col-id">ID</th>
                    <th className="col-type sortable" onClick={() => handleSort('type')}>
                      Type
                      {sortField === 'type' && (
                        sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                      )}
                    </th>
                    <th className="col-title sortable" onClick={() => handleSort('title')}>
                      Title
                      {sortField === 'title' && (
                        sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                      )}
                    </th>
                    <th className="col-epic sortable" onClick={() => handleSort('epic')}>
                      EPIC
                      {sortField === 'epic' && (
                        sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                      )}
                    </th>
                    <th className="col-priority sortable" onClick={() => handleSort('priority')}>
                      Priority
                      {sortField === 'priority' && (
                        sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                      )}
                    </th>
                    <th className="col-points">Points</th>
                    <th className="col-updated sortable" onClick={() => handleSort('updated')}>
                      Updated
                      {sortField === 'updated' && (
                        sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                      )}
                    </th>
                    <th className="col-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                {filteredBacklogs.map((backlog) => (
                  <>
                    <tr
                      key={backlog.id}
                      className={`backlog-row ${expandedBacklogId === backlog.id ? 'expanded' : ''}`}
                      onClick={() => toggleBacklogExpanded(backlog.id)}
                    >
                      <td className="col-expand">
                        {expandedBacklogId === backlog.id
                          ? <ChevronUp size={16} />
                          : <ChevronDown size={16} />}
                      </td>
                      <td className="col-status">
                        <span className={`status-badge status-${backlog.status}`}>
                          {backlog.status === 'draft' && <FileText size={12} />}
                          {backlog.status === 'approved' && <CheckCircle size={12} />}
                          {backlog.status === 'in_progress' && <Loader2 size={12} />}
                          {backlog.status.replace('_', ' ')}
                        </span>
                      </td>
                      <td className="col-id">
                        <span className="backlog-id-badge">{backlog.backlog_number}</span>
                      </td>
                      <td className="col-type">
                        <span className="type-badge">
                          {itemTypeIcons[backlog.item_type]}
                          {itemTypeLabels[backlog.item_type] || backlog.item_type}
                        </span>
                      </td>
                      <td className="col-title">
                        <span className="backlog-title">{backlog.title}</span>
                      </td>
                      <td className="col-epic">
                        <span className="epic-link">
                          <Layers size={14} />
                          {backlog.epic_title || 'N/A'}
                        </span>
                      </td>
                      <td className="col-priority">
                        <span className={`priority-badge ${priorityColors[backlog.priority]}`}>
                          {backlog.priority}
                        </span>
                      </td>
                      <td className="col-points">
                        {backlog.story_points ? (
                          <span className="points-badge">{backlog.story_points} pts</span>
                        ) : (
                          <span className="no-points">-</span>
                        )}
                      </td>
                      <td className="col-updated">
                        <div className="time-cell">
                          <Calendar size={14} />
                          {formatDate(backlog.updated_at || backlog.created_at)}
                        </div>
                      </td>
                      <td className="col-actions" onClick={(e) => e.stopPropagation()}>
                        <div className="actions-cell">
                          <button
                            className="action-btn view"
                            title="View Details"
                            onClick={() => toggleBacklogExpanded(backlog.id)}
                          >
                            <Eye size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>

                    {/* Expanded Row Details */}
                    {expandedBacklogId === backlog.id && (
                      <tr className="backlog-expanded-row">
                        <td colSpan={10}>
                          <div className="expanded-content">
                            {/* User Story Format */}
                            {backlog.item_type === 'user_story' && backlog.as_a && (
                              <div className="user-story-section">
                                <p><strong>As a</strong> {backlog.as_a}</p>
                                <p><strong>I want</strong> {backlog.i_want}</p>
                                <p><strong>So that</strong> {backlog.so_that}</p>
                              </div>
                            )}

                            <div className="detail-section">
                              <h4>Description</h4>
                              <p>{backlog.description}</p>
                            </div>

                            {backlog.acceptance_criteria && backlog.acceptance_criteria.length > 0 && (
                              <div className="detail-section">
                                <h4>Acceptance Criteria</h4>
                                <ul>
                                  {backlog.acceptance_criteria.map((ac, i) => (
                                    <li key={i}>{ac}</li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {backlog.technical_notes && (
                              <div className="detail-section">
                                <h4>Technical Notes</h4>
                                <p>{backlog.technical_notes}</p>
                              </div>
                            )}

                            {backlog.files_to_modify && backlog.files_to_modify.length > 0 && (
                              <div className="detail-section">
                                <h4>Files to Modify</h4>
                                <div className="file-tags">
                                  {backlog.files_to_modify.map((file) => (
                                    <span key={file} className="file-tag">{file}</span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {backlog.files_to_create && backlog.files_to_create.length > 0 && (
                              <div className="detail-section">
                                <h4>Files to Create</h4>
                                <div className="file-tags">
                                  {backlog.files_to_create.map((file) => (
                                    <span key={file} className="file-tag new">+ {file}</span>
                                  ))}
                                </div>
                              </div>
                            )}
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
      )}

      {/* Create View (Existing Workflow) */}
      {viewMode === 'create' && (
        <>
          {/* Back to List Button */}
          <div className="view-nav">
            <button className="btn btn-outline" onClick={() => setViewMode('list')}>
              <ArrowLeft size={16} />
              Back to Backlog List
            </button>
            {selectedStoredEpic && (
              <div className="selected-epic-badge">
                <Layers size={16} />
                <span>Generating for: {selectedStoredEpic.title}</span>
              </div>
            )}
          </div>

      {/* Workflow Stepper */}
      <div className="workflow-stepper">
        <div className={`step ${step === 'source' ? 'active' : ''} ${['generating', 'review', 'approved'].includes(step) ? 'completed' : ''}`}>
          <div className="step-number">{step !== 'source' ? <CheckCircle size={16} /> : '1'}</div>
          <span className="step-label">Select EPICs</span>
        </div>
        <div className={`step ${step === 'generating' ? 'active' : ''} ${['review', 'approved'].includes(step) ? 'completed' : ''}`}>
          <div className="step-number">{['review', 'approved'].includes(step) ? <CheckCircle size={16} /> : '2'}</div>
          <span className="step-label">Generate Stories</span>
        </div>
        <div className={`step ${step === 'review' ? 'active' : ''} ${step === 'approved' ? 'completed' : ''}`}>
          <div className="step-number">{step === 'approved' ? <CheckCircle size={16} /> : '3'}</div>
          <span className="step-label">Review & Edit</span>
        </div>
        <div className={`step ${step === 'approved' ? 'active' : ''}`}>
          <div className="step-number">4</div>
          <span className="step-label">Export</span>
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

      {/* Step 1: EPICs Source */}
      {step === 'source' && (
        <div className="step-content">
          <div className="step-header">
            <ListTodo size={32} className="step-icon" />
            <h2>Generate Backlogs from EPICs</h2>
            <p>Review your BRD, EPICs and generate detailed backlog items</p>
          </div>

          {/* Template and EPICs Upload Row */}
          <div className="template-brd-row">
            {/* Backlog Template Section */}
            <div className="form-group template-section-outer">
              <label htmlFor="template">
                <Upload size={16} />
                Backlog Template
              </label>
              <div className="template-section">
                {/* Default Template Info */}
                {isUsingDefaultTemplate && !templateFile ? (
                  <div className="template-selected default-template">
                    <FileText size={20} className="file-icon" />
                    <div className="template-info">
                      <span className="template-name">
                        <CheckCircle size={14} className="default-badge" />
                        Default Backlog Template
                      </span>
                      <span className="template-size">
                        {defaultBacklogTemplate ? `${(defaultBacklogTemplate.length / 1024).toFixed(1)} KB` : 'Loading...'}
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

                {/* Template Preview Toggle */}
                {backlogTemplate && (
                  <details className="template-preview">
                    <summary>
                      <ChevronDown size={14} />
                      Preview Template ({backlogTemplate.split('\n').length} lines)
                    </summary>
                    <pre className="template-content">{backlogTemplate}</pre>
                  </details>
                )}
              </div>
              <p className="input-hint">
                {isUsingDefaultTemplate
                  ? 'Using the default template with standard sections. Upload a custom template to override.'
                  : 'Custom template uploaded. Click "Use Default" to revert to the standard template.'}
              </p>
            </div>

            {/* EPICs Source Section */}
            <div className="form-group brd-upload-section">
              <label>
                <Layers size={16} />
                EPICs Source
              </label>
              {epics.length > 0 ? (
                <div className="brd-preview-card compact">
                  <Layers size={20} />
                  <div className="brd-info">
                    <span className="brd-title">{epics.length} EPICs Ready</span>
                    <span className="brd-size">From: {brdTitle || brdId}</span>
                  </div>
                  <button
                    type="button"
                    className="change-brd-btn"
                    onClick={() => navigate('/generate-epic')}
                  >
                    <RefreshCw size={14} />
                    Change
                  </button>
                </div>
              ) : (
                <div className="brd-upload-area" onClick={() => fileInputRef.current?.click()}>
                  <Upload size={24} />
                  <span>Upload EPICs File</span>
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
                  ? 'Draft mode generates backlog items quickly. Good for exploration.'
                  : 'Verified mode validates items against BRD and EPICs. Slower but more accurate.'}
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
                  {/* Detail Level Dropdown */}
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
                      <option value="concise">Concise (Brief descriptions)</option>
                      <option value="standard">Standard (Recommended)</option>
                      <option value="detailed">Detailed (Comprehensive)</option>
                    </select>
                  </div>

                  {/* Section Length Configuration */}
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
                                      className={`preset-btn ${field.target_words <= 40 ? 'active' : ''}`}
                                      onClick={() => updateFieldConfig(index, 'target_words', 30)}
                                      disabled={!field.enabled}
                                    >
                                      Concise
                                    </button>
                                    <button
                                      type="button"
                                      className={`preset-btn ${field.target_words > 40 && field.target_words <= 70 ? 'active' : ''}`}
                                      onClick={() => updateFieldConfig(index, 'target_words', 50)}
                                      disabled={!field.enabled}
                                    >
                                      Standard
                                    </button>
                                    <button
                                      type="button"
                                      className={`preset-btn ${field.target_words > 70 ? 'active' : ''}`}
                                      onClick={() => updateFieldConfig(index, 'target_words', 100)}
                                      disabled={!field.enabled}
                                    >
                                      Detailed
                                    </button>
                                  </div>
                                  <div className="section-words-input">
                                    <input
                                      type="number"
                                      min={10}
                                      max={300}
                                      step={10}
                                      value={field.target_words}
                                      onChange={(e) => updateFieldConfig(index, 'target_words', Math.max(10, Math.min(300, parseInt(e.target.value) || 50)))}
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

                  {/* Seed Display */}
                  <div className="option-group">
                    <label>
                      <Info size={14} />
                      Reproducibility Seed
                    </label>
                    <div className="seed-display">
                      <input
                        type="number"
                        value={seed || ''}
                        onChange={(e) => setSeed(e.target.value ? parseInt(e.target.value) : undefined)}
                        placeholder="Auto-generated"
                        className="seed-input"
                      />
                      <span className="seed-hint">Auto-generated from BRD and EPICs</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* EPICs Preview and Actions */}
          {epics.length > 0 && (
            <div className="brd-preview-section">
              <div className="brd-preview-card full">
                <Layers size={24} />
                <div className="brd-info">
                  <h3>{epics.length} EPICs Ready for Backlog Generation</h3>
                  <div className="epic-summary-list">
                    {epics.slice(0, 5).map((epic) => (
                      <div key={epic.id} className="epic-summary-item">
                        <span className="epic-id">{epic.id}</span>
                        <span className="epic-title">{epic.title}</span>
                      </div>
                    ))}
                    {epics.length > 5 && (
                      <div className="epic-summary-item more">
                        <span>+{epics.length - 5} more EPICs</span>
                      </div>
                    )}
                  </div>
                </div>
                <div className="brd-actions">
                  <button className="btn btn-primary" onClick={handleGenerateStories}>
                    <Sparkles size={16} />
                    Generate User Stories
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Empty State - No EPICs */}
          {epics.length === 0 && (
            <div className="empty-brd-state">
              <div className="empty-icon">
                <Layers size={48} />
              </div>
              <h3>No EPICs Available</h3>
              <p>Generate EPICs from a BRD to create backlog items</p>
              <button
                className="btn btn-primary"
                onClick={() => navigate('/generate-epic')}
              >
                <Layers size={16} />
                Generate EPICs First
              </button>
            </div>
          )}
        </div>
      )}


      {/* Step 2: Generating */}
      {step === 'generating' && (
        <div className="generating-step">
          <div className="generating-header">
            <Loader2 className="spin" size={24} />
            <h2>Generating User Stories...</h2>
            <p>Creating comprehensive user stories from EPICs</p>
          </div>

          <div className="generation-progress">
            <div className="items-preview">
              <h3>
                <ListTodo size={18} />
                Items Generated ({backlogItems.length})
              </h3>
              {backlogItems.slice(-10).map((item) => (
                <div key={item.id} className="item-preview">
                  <span className="item-type-icon">
                    {itemTypeIcons[item.item_type]}
                  </span>
                  <span className="item-id">{item.id}</span>
                  <span className="item-title">{item.title}</span>
                  <span className={`badge ${priorityColors[item.priority]}`}>
                    {item.priority}
                  </span>
                </div>
              ))}
            </div>

            <div className="thinking-panel" ref={thinkingContainerRef}>
              <h3>
                <Target size={18} />
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

      {/* Step 3: Review & Refine */}
      {step === 'review' && (
        <div className="review-step">
          <div className="review-header">
            <div className="header-left">
              <h2>Review User Stories</h2>
              <span className="item-count">{backlogItems.length} stories</span>
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
              <button className="btn btn-primary" onClick={handleApprove}>
                Approve Backlogs
                <ArrowRight size={16} />
              </button>
            </div>
          </div>

          {/* Stats Bar */}
          <div className="stats-bar">
            <div className="stat-item">
              <span className="stat-value">{stats.byType.user_story || 0}</span>
              <span className="stat-label">Stories</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{stats.byType.task || 0}</span>
              <span className="stat-label">Tasks</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{stats.byType.spike || 0}</span>
              <span className="stat-label">Spikes</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{stats.byPriority.high || 0}</span>
              <span className="stat-label">High Priority</span>
            </div>
          </div>

          {/* Global Feedback */}
          <div className="global-feedback-panel">
            <h3>
              <Sparkles size={18} />
              Global Refinement
            </h3>
            <p>Apply feedback when regenerating items for an EPIC</p>
            <div className="global-feedback-input">
              <textarea
                value={globalFeedback}
                onChange={(e) => setGlobalFeedback(e.target.value)}
                placeholder="e.g., 'Focus on security requirements', 'Include database migration tasks'"
                rows={2}
              />
            </div>
          </div>

          {/* EPICs with Backlog Items */}
          <div className="epic-backlogs">
            {epics.map((epic) => {
              const epicItems = getItemsForEpic(epic.id);
              const isExpanded = expandedEpics.has(epic.id);

              return (
                <div key={epic.id} className="epic-backlog-group">
                  <div
                    className="epic-group-header"
                    onClick={() => toggleEpicExpanded(epic.id)}
                  >
                    <div className="epic-group-title">
                      <span className="epic-id">{epic.id}</span>
                      <h3>{epic.title}</h3>
                      <span className="item-count-badge">
                        {epicItems.length} items
                      </span>
                      <span className="points-badge">
                        {epicItems.reduce((sum, i) => sum + (i.story_points || 0), 0)} pts
                      </span>
                    </div>
                    <div className="epic-group-actions">
                      <button
                        className="btn btn-sm btn-outline"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRegenerateForEpic(epic.id);
                        }}
                        disabled={regeneratingEpicId === epic.id}
                      >
                        {regeneratingEpicId === epic.id ? (
                          <Loader2 className="spin" size={14} />
                        ) : (
                          <RefreshCw size={14} />
                        )}
                        Regenerate
                      </button>
                      <button className="expand-btn">
                        {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                      </button>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="backlog-items-list">
                      {epicItems.map((item) => {
                        const isItemExpanded = expandedItems.has(item.id);

                        return (
                          <div
                            key={item.id}
                            className={`backlog-item-card ${isItemExpanded ? 'expanded' : ''}`}
                          >
                            <div
                              className="item-header"
                              onClick={() => toggleItemExpanded(item.id)}
                            >
                              <div className="item-title-row">
                                <span className="item-type-badge">
                                  {itemTypeIcons[item.item_type]}
                                  {itemTypeLabels[item.item_type]}
                                </span>
                                <span className="item-id">{item.id}</span>
                                <h4>{item.title}</h4>
                              </div>
                              <div className="item-meta">
                                <span className={`badge ${priorityColors[item.priority]}`}>
                                  {item.priority}
                                </span>
                                <button className="expand-btn">
                                  {isItemExpanded ? (
                                    <ChevronUp size={16} />
                                  ) : (
                                    <ChevronDown size={16} />
                                  )}
                                </button>
                              </div>
                            </div>

                            {/* User Story Format */}
                            {item.item_type === 'user_story' && item.as_a && (
                              <div className="user-story-format">
                                <p><strong>As a</strong> {item.as_a}</p>
                                <p><strong>I want</strong> {item.i_want}</p>
                                <p><strong>So that</strong> {item.so_that}</p>
                              </div>
                            )}

                            {/* BRD References */}
                            {item.brd_section_refs.length > 0 && (
                              <div className="brd-refs">
                                <FileText size={14} />
                                <span>BRD:</span>
                                {item.brd_section_refs.map((ref) => (
                                  <span key={ref} className="brd-ref-badge">
                                    {ref}
                                  </span>
                                ))}
                              </div>
                            )}

                            {/* Expanded Content */}
                            {isItemExpanded && (
                              <div className="item-expanded-content">
                                <div className="expanded-section">
                                  <h5>Description</h5>
                                  <p>{item.description}</p>
                                </div>

                                {item.acceptance_criteria.length > 0 && (
                                  <div className="expanded-section">
                                    <h5>Acceptance Criteria</h5>
                                    <ul className="acceptance-list">
                                      {item.acceptance_criteria.map((ac, i) => (
                                        <li key={i}>{ac}</li>
                                      ))}
                                    </ul>
                                  </div>
                                )}

                                {item.pre_conditions && item.pre_conditions.length > 0 && (
                                  <div className="expanded-section">
                                    <h5>Pre-conditions</h5>
                                    <ul className="conditions-list">
                                      {item.pre_conditions.map((cond, i) => (
                                        <li key={i}>{cond}</li>
                                      ))}
                                    </ul>
                                  </div>
                                )}

                                {item.post_conditions && item.post_conditions.length > 0 && (
                                  <div className="expanded-section">
                                    <h5>Post-conditions</h5>
                                    <ul className="conditions-list">
                                      {item.post_conditions.map((cond, i) => (
                                        <li key={i}>{cond}</li>
                                      ))}
                                    </ul>
                                  </div>
                                )}

                                {item.testing_approach && (
                                  <div className="expanded-section">
                                    <h5>Testing Approach</h5>
                                    <p className="testing-approach">{item.testing_approach}</p>
                                  </div>
                                )}

                                {item.edge_cases && item.edge_cases.length > 0 && (
                                  <div className="expanded-section">
                                    <h5>Edge Cases</h5>
                                    <ul className="edge-cases-list">
                                      {item.edge_cases.map((ec, i) => (
                                        <li key={i}>{ec}</li>
                                      ))}
                                    </ul>
                                  </div>
                                )}

                                {(item.implementation_notes || item.technical_notes) && (
                                  <div className="expanded-section">
                                    <h5>Implementation Notes</h5>
                                    <p className="implementation-notes">{item.implementation_notes || item.technical_notes}</p>
                                  </div>
                                )}

                                {item.ui_ux_notes && (
                                  <div className="expanded-section">
                                    <h5>UI/UX Notes</h5>
                                    <p className="ui-ux-notes">{item.ui_ux_notes}</p>
                                  </div>
                                )}

                                {item.files_to_modify.length > 0 && (
                                  <div className="expanded-section">
                                    <h5>Files to Modify</h5>
                                    <div className="file-tags">
                                      {item.files_to_modify.map((file) => (
                                        <span key={file} className="file-tag">
                                          {file}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {item.files_to_create.length > 0 && (
                                  <div className="expanded-section">
                                    <h5>Files to Create</h5>
                                    <div className="file-tags">
                                      {item.files_to_create.map((file) => (
                                        <span key={file} className="file-tag new">
                                          + {file}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Refinement Badge */}
                            {item.refinement_count > 0 && (
                              <div className="refinement-badge">
                                Refined {item.refinement_count}x
                              </div>
                            )}

                            {/* Actions */}
                            <div className="item-actions">
                              <button
                                className={`feedback-btn ${showFeedbackFor === item.id ? 'active' : ''}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setShowFeedbackFor(showFeedbackFor === item.id ? null : item.id);
                                }}
                              >
                                <MessageSquare size={14} />
                                Feedback
                              </button>
                              <button
                                className="delete-btn"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeleteItem(item.id);
                                }}
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>

                            {/* Feedback Input */}
                            {showFeedbackFor === item.id && (
                              <div className="feedback-section" onClick={(e) => e.stopPropagation()}>
                                <textarea
                                  value={itemFeedback[item.id] || ''}
                                  onChange={(e) =>
                                    setItemFeedback((prev) => ({
                                      ...prev,
                                      [item.id]: e.target.value,
                                    }))
                                  }
                                  placeholder="Describe how you'd like to refine this item..."
                                  rows={3}
                                />
                                <button
                                  className="btn btn-primary"
                                  onClick={() => handleRefineItem(item.id)}
                                  disabled={!itemFeedback[item.id]?.trim() || refiningItemId === item.id}
                                >
                                  {refiningItemId === item.id ? (
                                    <Loader2 className="spin" size={14} />
                                  ) : (
                                    <Send size={14} />
                                  )}
                                  Refine with AI
                                </button>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Step 4: Approved */}
      {step === 'approved' && (
        <div className="approved-step">
          <div className="approved-header">
            <CheckCircle size={48} className="success-icon" />
            <h2>Backlogs Approved</h2>
            <p>{backlogItems.length} items ready for export</p>
          </div>

          <div className="approved-summary">
            <div className="summary-card">
              <h3>Summary</h3>
              <div className="summary-stats">
                <div className="stat">
                  <span className="stat-value">{backlogItems.length}</span>
                  <span className="stat-label">Total Items</span>
                </div>
                <div className="stat">
                  <span className="stat-value">{stats.totalPoints}</span>
                  <span className="stat-label">Story Points</span>
                </div>
                <div className="stat">
                  <span className="stat-value">{stats.byType.user_story || 0}</span>
                  <span className="stat-label">User Stories</span>
                </div>
                <div className="stat">
                  <span className="stat-value">{epics.length}</span>
                  <span className="stat-label">EPICs</span>
                </div>
              </div>
            </div>

            <div className="export-options">
              <h3>Export Options</h3>
              <div className="export-buttons">
                <button className="btn btn-secondary" onClick={handleDownload}>
                  <Download size={16} />
                  Download Markdown
                </button>
                <button className="btn btn-primary" disabled>
                  <ExternalLink size={16} />
                  Export to Jira (Coming Soon)
                </button>
              </div>
            </div>

            <div className="backlog-list-summary">
              <h3>All Backlog Items by EPIC</h3>
              {epics.map((epic) => {
                const epicItems = getItemsForEpic(epic.id);
                return (
                  <div key={epic.id} className="epic-items-summary">
                    <h4>
                      <span className="epic-id">{epic.id}</span>
                      {epic.title}
                    </h4>
                    <ul>
                      {epicItems.map((item) => (
                        <li key={item.id}>
                          <span className="item-type-icon">
                            {itemTypeIcons[item.item_type]}
                          </span>
                          <span className="item-id">{item.id}</span>
                          <span className="item-title">{item.title}</span>
                          {item.story_points && (
                            <span className="story-points">{item.story_points} pts</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="approved-actions">
            <button className="btn btn-outline" onClick={() => setStep('review')}>
              <ArrowLeft size={16} />
              Back to Review
            </button>
            <button className="btn btn-secondary" onClick={() => navigate('/generate-epic')}>
              <Layers size={16} />
              Generate More EPICs
            </button>
          </div>
        </div>
      )}
        </>
      )}
    </div>
  );
}
