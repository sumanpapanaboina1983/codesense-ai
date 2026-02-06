import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
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
  Thermometer,
  Hash,
} from 'lucide-react';
import {
  getAnalyzedRepositories,
  generateBRDStream,
  getDefaultTemplate,
  type RepositorySummary,
  type BRDResponse,
  type StreamEvent,
  type GenerateBRDRequest,
  type GenerationMode,
  type GenerationApproach,
  type DetailLevel,
  type VerificationReport,
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

// Default values for advanced options
const DEFAULT_OPTIONS = {
  mode: 'draft' as GenerationMode,
  approach: 'context_first' as GenerationApproach,  // Always use context_first
  detail_level: 'standard' as DetailLevel,
  include_similar_features: true,
  max_iterations: 3,
  min_confidence: 0.7,
  show_evidence: false,
  temperature: 0.3,  // Lower = more consistent outputs
  seed: undefined as number | undefined,  // For reproducible outputs
};

export function GenerateBRD() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

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
  const [includeSimilarFeatures, setIncludeSimilarFeatures] = useState(DEFAULT_OPTIONS.include_similar_features);
  const [maxIterations, setMaxIterations] = useState(DEFAULT_OPTIONS.max_iterations);
  const [minConfidence, setMinConfidence] = useState(DEFAULT_OPTIONS.min_confidence);
  const [showEvidence, setShowEvidence] = useState(DEFAULT_OPTIONS.show_evidence);
  const [temperature, setTemperature] = useState(DEFAULT_OPTIONS.temperature);
  const [seed, setSeed] = useState<number | undefined>(DEFAULT_OPTIONS.seed);
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false);
  const [showVerificationReport, setShowVerificationReport] = useState(false);

  // Template upload state
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [templateContent, setTemplateContent] = useState<string>('');
  const [defaultTemplate, setDefaultTemplate] = useState<string>('');
  const [isUsingDefaultTemplate, setIsUsingDefaultTemplate] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Streaming state
  const [isGenerating, setIsGenerating] = useState(false);
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
    };

    // Add template config if template is provided
    if (templateContent) {
      request.brd_template = templateContent;
      request.template_config = {
        brd_template: templateContent,
      };
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
              setGeneratedBRD(event.data.brd);
              // Capture verification info including full report
              setVerificationInfo({
                is_verified: event.data.is_verified ?? false,
                confidence_score: event.data.confidence_score ?? 0,
                hallucination_risk: event.data.hallucination_risk ?? 'unknown',
                iterations_used: event.data.iterations_used ?? 0,
                needs_sme_review: event.data.needs_sme_review ?? false,
                mode: event.data.mode ?? mode,
                verification_report: event.data.verification_report,
              });
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
    navigate('/generate-epic', {
      state: {
        brd: generatedBRD,
        repository: selectedRepo,
      },
    });
  };

  const handleReset = () => {
    setGeneratedBRD(null);
    setVerificationInfo(null);
    setFeatureDescription('');
    setSelectedRepo(null);
    setThinkingSteps([]);
    setStreamedContent('');
    setError(null);
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
              <button className="btn btn-outline" onClick={handleReset}>
                <RefreshCw size={16} />
                Generate Another
              </button>
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

          {/* BRD Content Editor */}
          <div className="brd-editor">
            <div className="editor-header">
              <FileText size={20} />
              <span>Business Requirements Document</span>
            </div>
            <div className="editor-content markdown-body">
              <ReactMarkdown>{generatedBRD.markdown}</ReactMarkdown>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Generation in progress - show thinking process
  if (isGenerating) {
    return (
      <div className="generate-brd-page">
        <div className="generation-container">
          <div className="generation-header">
            <Brain size={32} className="brain-icon pulse" />
            <div>
              <h1>Generating BRD</h1>
              <p>Analyzing codebase and creating your Business Requirements Document...</p>
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

  return (
    <div className="generate-brd-page">
      <div className="page-header">
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

                  {/* Consistency Settings */}
                  <div className="consistency-options">
                    <h4>Consistency Settings</h4>

                    {/* Temperature */}
                    <div className="option-group">
                      <label>
                        <Thermometer size={14} />
                        Temperature
                        <span className="value-display">{temperature.toFixed(1)}</span>
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="10"
                        value={temperature * 10}
                        onChange={(e) => setTemperature(Number(e.target.value) / 10)}
                        className="option-range"
                      />
                      <span className="option-hint">
                        Lower = more consistent, Higher = more creative (0.0-1.0)
                      </span>
                    </div>

                    {/* Seed */}
                    <div className="option-group">
                      <label>
                        <Hash size={14} />
                        Seed (optional)
                      </label>
                      <input
                        type="number"
                        value={seed ?? ''}
                        onChange={(e) => setSeed(e.target.value ? Number(e.target.value) : undefined)}
                        placeholder="Leave empty for random"
                        className="option-input"
                      />
                      <span className="option-hint">
                        Set a seed for reproducible outputs
                      </span>
                    </div>
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
