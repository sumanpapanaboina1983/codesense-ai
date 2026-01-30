import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  FileText,
  ArrowRight,
  Loader2,
  CheckCircle,
  AlertCircle,
  Download,
  RefreshCw,
  ChevronDown,
  FolderGit2,
  Sparkles,
  Upload,
  X,
  Brain,
  FileCode,
} from 'lucide-react';
import {
  getAnalyzedRepositories,
  generateBRDStream,
  type RepositorySummary,
  type BRDResponse,
  type StreamEvent,
  type GenerateBRDRequest,
  type GenerateBRDResponse,
} from '../../services/api';
import './GenerateBRD.css';

interface ThinkingStep {
  id: number;
  content: string;
  timestamp: Date;
}

export function GenerateBRD() {
  const navigate = useNavigate();

  // State
  const [selectedRepo, setSelectedRepo] = useState<RepositorySummary | null>(null);
  const [featureDescription, setFeatureDescription] = useState('');
  const [generatedBRD, setGeneratedBRD] = useState<BRDResponse | null>(null);
  const [verificationInfo, setVerificationInfo] = useState<{
    is_verified: boolean;
    confidence_score: number;
    hallucination_risk: string;
    iterations_used: number;
    needs_sme_review: boolean;
  } | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // Template upload state
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [templateContent, setTemplateContent] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Streaming state
  const [isGenerating, setIsGenerating] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const [streamedContent, setStreamedContent] = useState('');
  const [error, setError] = useState<string | null>(null);
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
    setTemplateContent('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
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
    setThinkingSteps([]);
    setStreamedContent('');
    setError(null);
    setGeneratedBRD(null);

    const request: GenerateBRDRequest = {
      feature_description: featureDescription,
      use_skill: true,
      include_similar_features: true,
    };

    // Add template config if template is provided
    if (templateContent) {
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
              setThinkingSteps((prev) => [
                ...prev,
                { id: stepId++, content: event.content!, timestamp: new Date() },
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
              // Capture verification info
              setVerificationInfo({
                is_verified: event.data.is_verified ?? false,
                confidence_score: event.data.confidence_score ?? 0,
                hallucination_risk: event.data.hallucination_risk ?? 'unknown',
                iterations_used: event.data.iterations_used ?? 0,
                needs_sme_review: event.data.needs_sme_review ?? false,
              });
            }
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
  };

  // If BRD is generated, show the review screen
  if (generatedBRD) {
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
                  <span className="label">Verified</span>
                  <span className={`value ${verificationInfo.is_verified ? 'verified' : 'unverified'}`}>
                    {verificationInfo.is_verified ? 'Yes' : 'No'}
                  </span>
                </div>
                <div className="metadata-item">
                  <span className="label">Confidence</span>
                  <span className="value">{(verificationInfo.confidence_score * 100).toFixed(0)}%</span>
                </div>
                <div className="metadata-item">
                  <span className="label">Hallucination Risk</span>
                  <span className={`value risk-${verificationInfo.hallucination_risk}`}>
                    {verificationInfo.hallucination_risk}
                  </span>
                </div>
                <div className="metadata-item">
                  <span className="label">Iterations</span>
                  <span className="value">{verificationInfo.iterations_used}</span>
                </div>
              </>
            )}
          </div>

          {/* BRD Content Editor */}
          <div className="brd-editor">
            <div className="editor-header">
              <FileText size={20} />
              <span>Business Requirements Document</span>
            </div>
            <div className="editor-content">
              <pre className="markdown-preview">{generatedBRD.markdown}</pre>
            </div>
          </div>

          {/* Quick Stats */}
          <div className="brd-stats">
            <div className="stat-item">
              <span className="stat-value">{generatedBRD.functional_requirements.length}</span>
              <span className="stat-label">Functional Requirements</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{generatedBRD.technical_requirements.length}</span>
              <span className="stat-label">Technical Requirements</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{generatedBRD.objectives.length}</span>
              <span className="stat-label">Objectives</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{generatedBRD.risks.length}</span>
              <span className="stat-label">Identified Risks</span>
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
                  <div key={step.id} className="thinking-step">
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

            {/* Template Upload */}
            <div className="form-group">
              <label htmlFor="template">
                <Upload size={16} />
                BRD Template (Optional)
              </label>
              <div className="template-upload-area">
                {templateFile ? (
                  <div className="template-selected">
                    <FileText size={20} className="file-icon" />
                    <div className="template-info">
                      <span className="template-name">{templateFile.name}</span>
                      <span className="template-size">
                        {(templateFile.size / 1024).toFixed(1)} KB
                      </span>
                    </div>
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
                )}
              </div>
              <p className="input-hint">
                Upload a custom BRD template to define the structure. The generated BRD will follow your template format.
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
                className="btn btn-primary btn-lg"
                onClick={handleGenerate}
                disabled={!selectedRepo || !featureDescription.trim() || isGenerating}
              >
                <FileText size={20} />
                Generate BRD
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
