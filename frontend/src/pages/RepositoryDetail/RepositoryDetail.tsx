import { useEffect, useState, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  RefreshCw,
  Play,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  FileText,
  TestTube,
  Sparkles,
  ChevronDown,
  ChevronRight,
  Zap,
  BookOpen,
  Code2,
  Database,
  Layout,
  Server,
  TrendingUp,
  FileCode,
  Boxes,
  GitBranch,
  Network,
  Layers,
  PieChart,
  BarChart3,
  X,
  Book,
} from 'lucide-react';
import {
  getRepository,
  getReadinessReport,
  getCodebaseStatistics,
  getDiscoveredFeatures,
  getModuleDependencies,
  enrichDocumentation,
  enrichTests,
  type RepositoryDetail as RepoDetail,
  type AgenticReadinessResponse,
  type CodebaseStatisticsResponse,
  type DiscoveredFeaturesResponse,
  type BusinessFeature,
  type EnrichmentResponse,
} from '../../services/api';
import type { ModuleDependenciesResponse } from '../../types/api';
import { analyzeRepository } from '../../api/client';
import type { WikiGenerationOptions } from '../../api/client';
import { LoadingSpinner } from '../../components/LoadingSpinner';
import { StatusBadge } from '../../components/StatusBadge';
import { ModuleDependencyDiagram } from '../../components/ModuleDependencyDiagram';
import { WikiConfigurationPanel } from '../../components/WikiConfigurationPanel';
import type { WikiConfiguration } from '../../components/WikiConfigurationPanel';
import './RepositoryDetail.css';

// Grade color mapping
const gradeColors: Record<string, string> = {
  A: 'var(--color-success)',
  B: 'var(--color-success-light)',
  C: 'var(--color-warning)',
  D: 'var(--color-warning-dark)',
  F: 'var(--color-danger)',
};

const gradeBackgrounds: Record<string, string> = {
  A: 'rgba(16, 185, 129, 0.1)',
  B: 'rgba(16, 185, 129, 0.08)',
  C: 'rgba(245, 158, 11, 0.1)',
  D: 'rgba(245, 158, 11, 0.08)',
  F: 'rgba(239, 68, 68, 0.1)',
};

export function RepositoryDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [repository, setRepository] = useState<RepoDetail | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [readinessReport, setReadinessReport] = useState<AgenticReadinessResponse | null>(null);
  const [statistics, setStatistics] = useState<CodebaseStatisticsResponse | null>(null);
  const [discoveredFeatures, setDiscoveredFeatures] = useState<DiscoveredFeaturesResponse | null>(null);
  const [selectedFeature, setSelectedFeature] = useState<BusinessFeature | null>(null);
  const [loading, setLoading] = useState(true);
  const [readinessLoading, setReadinessLoading] = useState(false);
  const [statisticsLoading, setStatisticsLoading] = useState(false);
  const [featuresLoading, setFeaturesLoading] = useState(false);
  const [enrichmentLoading, setEnrichmentLoading] = useState<string | null>(null);
  const [enrichmentResult, setEnrichmentResult] = useState<EnrichmentResponse | null>(null);
  const [moduleDependencies, setModuleDependencies] = useState<ModuleDependenciesResponse | null>(null);
  const [modulesLoading, setModulesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['overview', 'statistics', 'readiness']));
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [showWikiConfig, setShowWikiConfig] = useState(false);
  const [wikiConfig, setWikiConfig] = useState<WikiConfiguration | null>(null);

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  };

  const toggleFeatureGroup = (groupName: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupName)) {
        next.delete(groupName);
      } else {
        next.add(groupName);
      }
      return next;
    });
  };

  const fetchRepository = async () => {
    if (!id) return;
    try {
      const repo = await getRepository(id);
      setRepository(repo);
    } catch (err) {
      console.error('Failed to fetch repository:', err);
      setError('Failed to load repository details');
    } finally {
      setLoading(false);
    }
  };

  const fetchReadinessReport = async () => {
    if (!id) return;
    setReadinessLoading(true);
    try {
      const report = await getReadinessReport(id);
      setReadinessReport(report);
    } catch (err) {
      console.error('Failed to fetch readiness report:', err);
    } finally {
      setReadinessLoading(false);
    }
  };

  const fetchStatistics = async () => {
    if (!id) return;
    setStatisticsLoading(true);
    try {
      const stats = await getCodebaseStatistics(id);
      setStatistics(stats);
    } catch (err) {
      console.error('Failed to fetch codebase statistics:', err);
    } finally {
      setStatisticsLoading(false);
    }
  };

  const fetchDiscoveredFeatures = async () => {
    if (!id) return;
    setFeaturesLoading(true);
    try {
      const features = await getDiscoveredFeatures(id);
      setDiscoveredFeatures(features);
    } catch (err) {
      console.error('Failed to fetch discovered features:', err);
    } finally {
      setFeaturesLoading(false);
    }
  };

  const fetchModuleDependencies = async () => {
    if (!id) return;
    setModulesLoading(true);
    try {
      const modules = await getModuleDependencies(id);
      setModuleDependencies(modules);
    } catch (err) {
      console.error('Failed to fetch module dependencies:', err);
    } finally {
      setModulesLoading(false);
    }
  };

  const handleEnrichDocumentation = async () => {
    if (!id) return;
    setEnrichmentLoading('documentation');
    try {
      const result = await enrichDocumentation(id, {
        entity_ids: 'all-undocumented',
        style: 'jsdoc',
        include_examples: true,
        include_parameters: true,
        include_returns: true,
        include_throws: true,
        max_entities: 50,
      });
      setEnrichmentResult(result);
      // Refresh readiness report after enrichment
      await fetchReadinessReport();
    } catch (err) {
      console.error('Failed to enrich documentation:', err);
    } finally {
      setEnrichmentLoading(null);
    }
  };

  const handleEnrichTests = async () => {
    if (!id) return;
    setEnrichmentLoading('tests');
    try {
      const result = await enrichTests(id, {
        entity_ids: 'all-untested',
        framework: 'jest',
        test_types: ['unit'],
        include_mocks: true,
        include_edge_cases: true,
        max_entities: 20,
      });
      setEnrichmentResult(result);
      // Refresh readiness report after enrichment
      await fetchReadinessReport();
    } catch (err) {
      console.error('Failed to enrich tests:', err);
    } finally {
      setEnrichmentLoading(null);
    }
  };

  // Open wiki configuration modal before analysis
  const openWikiConfig = () => {
    setShowWikiConfig(true);
  };

  // Handle wiki configuration changes
  const handleWikiConfigChange = useCallback((config: WikiConfiguration) => {
    setWikiConfig(config);
  }, []);

  // Convert WikiConfiguration to API format
  const convertWikiConfigToApiFormat = (config: WikiConfiguration | null): WikiGenerationOptions => {
    if (!config) {
      // Default configuration
      return {
        enabled: true,
        depth: 'basic' as const,
        include_core_systems: true,
        include_features: true,
        include_api_reference: false,
        include_data_models: false,
        include_code_structure: false,
      };
    }

    if (config.mode === 'standard') {
      // Standard mode - use section toggles
      const enabledSections = config.sections.filter(s => s.enabled).map(s => s.id);
      const depth = enabledSections.includes('class-docs') ? 'comprehensive' as const :
                    enabledSections.includes('api-reference') ? 'standard' as const : 'basic' as const;
      return {
        enabled: true,
        depth,
        include_core_systems: enabledSections.includes('core-systems'),
        include_features: enabledSections.includes('features'),
        include_api_reference: enabledSections.includes('api-reference'),
        include_data_models: enabledSections.includes('data-models'),
        include_code_structure: enabledSections.includes('code-structure'),
        include_integrations: enabledSections.includes('integrations'),
        include_deployment: enabledSections.includes('deployment'),
        include_getting_started: enabledSections.includes('getting-started'),
        include_configuration: enabledSections.includes('configuration'),
      };
    } else {
      // Advanced mode - custom pages
      return {
        enabled: true,
        depth: 'custom' as const,
        mode: 'advanced' as const,
        context_notes: config.contextNotes.filter(n => n.trim()),
        custom_pages: config.customPages.map(page => ({
          title: page.title,
          purpose: page.purpose,
          notes: page.notes,
          parent_id: page.parentId,
          is_section: page.isSection,
        })),
      };
    }
  };

  const handleAnalyze = async () => {
    if (!id) return;
    setAnalyzing(true);
    setShowWikiConfig(false);
    try {
      // Trigger analysis with wiki configuration from modal
      const wikiOptions = convertWikiConfigToApiFormat(wikiConfig);
      await analyzeRepository(id, {
        reset_graph: false,
        wiki_options: wikiOptions,
      });
      // Navigate to Jobs page to show analysis progress
      navigate('/jobs');
    } catch (err) {
      console.error('Failed to analyze repository:', err);
      setAnalyzing(false);
      alert('Failed to start analysis. Please try again.');
    }
  };

  useEffect(() => {
    fetchRepository();
  }, [id]);

  // Poll for status updates when analysis is running
  useEffect(() => {
    const isInProgress = repository?.analysis_status === 'running' ||
                         repository?.analysis_status === 'pending' ||
                         repository?.analysis_status === 'in_progress';

    if (isInProgress) {
      const interval = setInterval(() => {
        fetchRepository();
      }, 3000); // Poll every 3 seconds

      return () => clearInterval(interval);
    }
  }, [repository?.analysis_status, id]);

  useEffect(() => {
    if (repository?.analysis_status === 'completed') {
      fetchReadinessReport();
      fetchStatistics();
      fetchDiscoveredFeatures();
      fetchModuleDependencies();
    }
  }, [repository?.analysis_status]);

  if (loading) {
    return <LoadingSpinner message="Loading repository..." />;
  }

  if (error || !repository) {
    return (
      <div className="error-state">
        <XCircle size={48} />
        <h3>Error</h3>
        <p>{error || 'Repository not found'}</p>
        <Link to="/repositories" className="btn btn-primary">
          <ArrowLeft size={16} />
          Back to Repositories
        </Link>
      </div>
    );
  }

  const isAnalyzed = repository.analysis_status === 'completed';
  const isAnalyzing = repository.analysis_status === 'running' ||
                      repository.analysis_status === 'pending' ||
                      repository.analysis_status === 'in_progress';

  return (
    <div className="repository-detail">
      {/* Header */}
      <div className="repo-header">
        <div className="repo-header-left">
          <Link to="/repositories" className="back-link">
            <ArrowLeft size={20} />
          </Link>
          <div className="repo-title">
            <h1>{repository.name}</h1>
            <div className="repo-badges">
              <StatusBadge status={repository.platform} />
              <StatusBadge status={repository.status} />
              <StatusBadge status={repository.analysis_status} type="analysis" />
            </div>
          </div>
        </div>
        <div className="repo-header-actions">
          {isAnalyzed && (
            <Link
              to={`/repositories/${id}/wiki`}
              className={`btn ${repository.wiki_generated ? 'btn-success' : 'btn-outline'}`}
            >
              <BookOpen size={16} />
              Documentation
              {repository.wiki_generated ? (
                <span className="doc-status generated">Generated</span>
              ) : (
                <span className="doc-status pending">Not Generated</span>
              )}
            </Link>
          )}
        </div>
      </div>

      {/* Overview Section */}
      <section className="detail-section">
        <div
          className="section-header"
          onClick={() => toggleSection('overview')}
        >
          <div className="section-title">
            <Layout size={20} />
            <h2>Repository Overview</h2>
          </div>
          {expandedSections.has('overview') ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
        </div>
        {expandedSections.has('overview') && (
          <div className="section-content">
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-icon">
                  <Code2 size={24} />
                </div>
                <div className="stat-info">
                  <span className="stat-label">Status</span>
                  <span className="stat-value">{repository.status}</span>
                </div>
              </div>
              <div className="stat-card">
                <div className="stat-icon">
                  <Database size={24} />
                </div>
                <div className="stat-info">
                  <span className="stat-label">Analysis</span>
                  <span className="stat-value">{repository.analysis_status}</span>
                </div>
              </div>
              <div className="stat-card">
                <div className="stat-icon">
                  <Server size={24} />
                </div>
                <div className="stat-info">
                  <span className="stat-label">Branch</span>
                  <span className="stat-value">{repository.default_branch || 'main'}</span>
                </div>
              </div>
              {repository.last_analyzed_at && (
                <div className="stat-card">
                  <div className="stat-icon">
                    <RefreshCw size={24} />
                  </div>
                  <div className="stat-info">
                    <span className="stat-label">Last Analyzed</span>
                    <span className="stat-value">
                      {new Date(repository.last_analyzed_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              )}
            </div>

            {isAnalyzing && (
              <div className="action-banner analyzing">
                <RefreshCw size={24} className="spin" />
                <div className="banner-content">
                  <h4>Analysis In Progress</h4>
                  <p>Code analysis is running. This may take a few minutes for large repositories.</p>
                </div>
                <Link to="/jobs" className="btn btn-outline">
                  View Progress
                </Link>
              </div>
            )}

            {!isAnalyzed && !isAnalyzing && (
              <div className="action-banner">
                <AlertTriangle size={24} />
                <div className="banner-content">
                  <h4>Repository Not Analyzed</h4>
                  <p>Run analysis to enable Agentic Readiness reports and code enrichment features.</p>
                </div>
                <button
                  className="btn btn-primary"
                  onClick={openWikiConfig}
                  disabled={repository.status !== 'cloned' || analyzing}
                >
                  {analyzing ? (
                    <>
                      <RefreshCw size={16} className="spin" />
                      Starting Analysis...
                    </>
                  ) : (
                    <>
                      <Play size={16} />
                      Analyze Now
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Codebase Statistics Section */}
      {isAnalyzed && (
        <section className="detail-section">
          <div
            className="section-header"
            onClick={() => toggleSection('statistics')}
          >
            <div className="section-title">
              <BarChart3 size={20} />
              <h2>Codebase Statistics</h2>
            </div>
            {expandedSections.has('statistics') ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
          </div>
          {expandedSections.has('statistics') && (
            <div className="section-content">
              {statisticsLoading ? (
                <div className="loading-inline">
                  <RefreshCw size={20} className="spin" />
                  <span>Loading codebase statistics...</span>
                </div>
              ) : statistics ? (
                <div className="statistics-content">
                  {/* Primary Stats Row */}
                  <div className="stats-grid primary-stats">
                    <div className="stat-card highlight">
                      <div className="stat-icon">
                        <FileCode size={24} />
                      </div>
                      <div className="stat-info">
                        <span className="stat-value">{statistics.statistics.total_files.toLocaleString()}</span>
                        <span className="stat-label">Total Files</span>
                      </div>
                    </div>
                    <div className="stat-card highlight">
                      <div className="stat-icon">
                        <Code2 size={24} />
                      </div>
                      <div className="stat-info">
                        <span className="stat-value">{statistics.statistics.total_lines_of_code.toLocaleString()}</span>
                        <span className="stat-label">Lines of Code</span>
                      </div>
                    </div>
                    <div className="stat-card highlight">
                      <div className="stat-icon">
                        <Boxes size={24} />
                      </div>
                      <div className="stat-info">
                        <span className="stat-value">{statistics.statistics.total_classes.toLocaleString()}</span>
                        <span className="stat-label">Classes</span>
                      </div>
                    </div>
                    <div className="stat-card highlight">
                      <div className="stat-icon">
                        <GitBranch size={24} />
                      </div>
                      <div className="stat-info">
                        <span className="stat-value">{statistics.statistics.total_functions.toLocaleString()}</span>
                        <span className="stat-label">Functions</span>
                      </div>
                    </div>
                  </div>

                  {/* Secondary Stats Grid */}
                  <div className="stats-categories">
                    {/* APIs & Endpoints */}
                    <div className="stats-category">
                      <h4><Network size={16} /> APIs & Endpoints</h4>
                      <div className="category-stats">
                        <div className="mini-stat">
                          <span className="mini-value">{statistics.statistics.rest_endpoints}</span>
                          <span className="mini-label">REST Endpoints</span>
                        </div>
                        <div className="mini-stat">
                          <span className="mini-value">{statistics.statistics.graphql_operations}</span>
                          <span className="mini-label">GraphQL Ops</span>
                        </div>
                        <div className="mini-stat total">
                          <span className="mini-value">{statistics.statistics.total_api_endpoints}</span>
                          <span className="mini-label">Total APIs</span>
                        </div>
                      </div>
                    </div>

                    {/* UI Components */}
                    <div className="stats-category">
                      <h4><Layout size={16} /> UI & Components</h4>
                      <div className="category-stats">
                        <div className="mini-stat">
                          <span className="mini-value">{statistics.statistics.ui_components}</span>
                          <span className="mini-label">Components</span>
                        </div>
                        <div className="mini-stat">
                          <span className="mini-value">{statistics.statistics.ui_routes}</span>
                          <span className="mini-label">Routes/Pages</span>
                        </div>
                      </div>
                    </div>

                    {/* Testing */}
                    <div className="stats-category">
                      <h4><TestTube size={16} /> Testing</h4>
                      <div className="category-stats">
                        <div className="mini-stat">
                          <span className="mini-value">{statistics.statistics.total_test_files}</span>
                          <span className="mini-label">Test Files</span>
                        </div>
                        <div className="mini-stat">
                          <span className="mini-value">{statistics.statistics.total_test_cases}</span>
                          <span className="mini-label">Test Cases</span>
                        </div>
                      </div>
                    </div>

                    {/* Architecture */}
                    <div className="stats-category">
                      <h4><Layers size={16} /> Architecture</h4>
                      <div className="category-stats">
                        <div className="mini-stat">
                          <span className="mini-value">{statistics.statistics.services_count}</span>
                          <span className="mini-label">Services</span>
                        </div>
                        <div className="mini-stat">
                          <span className="mini-value">{statistics.statistics.controllers_count}</span>
                          <span className="mini-label">Controllers</span>
                        </div>
                        <div className="mini-stat">
                          <span className="mini-value">{statistics.statistics.repositories_count}</span>
                          <span className="mini-label">Repositories</span>
                        </div>
                      </div>
                    </div>

                    {/* Data & Dependencies */}
                    <div className="stats-category">
                      <h4><Database size={16} /> Data & Dependencies</h4>
                      <div className="category-stats">
                        <div className="mini-stat">
                          <span className="mini-value">{statistics.statistics.total_database_models}</span>
                          <span className="mini-label">DB Models</span>
                        </div>
                        <div className="mini-stat">
                          <span className="mini-value">{statistics.statistics.total_dependencies}</span>
                          <span className="mini-label">Dependencies</span>
                        </div>
                        <div className="mini-stat">
                          <span className="mini-value">{statistics.statistics.config_files}</span>
                          <span className="mini-label">Config Files</span>
                        </div>
                      </div>
                    </div>

                    {/* Code Quality */}
                    <div className="stats-category">
                      <h4><TrendingUp size={16} /> Code Quality</h4>
                      <div className="category-stats">
                        <div className="mini-stat">
                          <span className="mini-value">
                            {statistics.statistics.avg_cyclomatic_complexity?.toFixed(1) ?? 'N/A'}
                          </span>
                          <span className="mini-label">Avg Complexity</span>
                        </div>
                        <div className="mini-stat">
                          <span className="mini-value">{statistics.statistics.documented_entities}</span>
                          <span className="mini-label">Documented</span>
                        </div>
                        <div className="mini-stat">
                          <span className="mini-value">{statistics.statistics.documentation_coverage.toFixed(0)}%</span>
                          <span className="mini-label">Doc Coverage</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Language Breakdown */}
                  {statistics.statistics.languages.length > 0 && (
                    <div className="language-breakdown">
                      <h4><PieChart size={16} /> Language Breakdown</h4>
                      <div className="language-bars">
                        {statistics.statistics.languages.slice(0, 6).map((lang, index) => (
                          <div key={lang.language} className="language-item">
                            <div className="language-header">
                              <span className="language-name">{lang.language}</span>
                              <span className="language-stats">
                                {lang.file_count} files • {lang.lines_of_code.toLocaleString()} LOC
                              </span>
                            </div>
                            <div className="language-bar">
                              <div
                                className={`language-fill lang-${index}`}
                                style={{ width: `${lang.percentage}%` }}
                              />
                              <span className="language-percentage">{lang.percentage.toFixed(1)}%</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="empty-state-inline">
                  <BarChart3 size={32} />
                  <p>Click refresh to load codebase statistics</p>
                  <button className="btn btn-primary" onClick={fetchStatistics}>
                    <RefreshCw size={16} />
                    Load Statistics
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* Modules & Dependencies Section */}
      {isAnalyzed && (
        <section className="detail-section">
          <div
            className="section-header"
            onClick={() => toggleSection('modules')}
          >
            <div className="section-title">
              <Network size={20} />
              <h2>Modules & Dependencies</h2>
              {moduleDependencies && moduleDependencies.totalModules > 0 && (
                <span className="module-count-badge">
                  {moduleDependencies.totalModules} modules
                </span>
              )}
            </div>
            {expandedSections.has('modules') ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
          </div>
          {expandedSections.has('modules') && (
            <div className="section-content">
              {modulesLoading ? (
                <div className="loading-inline">
                  <RefreshCw size={20} className="spin" />
                  <span>Loading module dependencies...</span>
                </div>
              ) : moduleDependencies && moduleDependencies.modules.length > 0 ? (
                <div className="modules-content">
                  {/* Module Statistics Summary */}
                  <div className="module-stats-summary">
                    <div className="module-stat-item">
                      <span className="module-stat-value">{moduleDependencies.totalModules}</span>
                      <span className="module-stat-label">Total Modules</span>
                    </div>
                    <div className="module-stat-item">
                      <span className="module-stat-value">{moduleDependencies.avgDependencies}</span>
                      <span className="module-stat-label">Avg Dependencies</span>
                    </div>
                    <div className="module-stat-item">
                      <span className="module-stat-value">{moduleDependencies.dependencyGraph.length}</span>
                      <span className="module-stat-label">Total Relationships</span>
                    </div>
                  </div>

                  {/* Module Dependency Diagram */}
                  <div className="module-diagram-container">
                    <ModuleDependencyDiagram
                      modules={moduleDependencies.modules}
                      dependencyGraph={moduleDependencies.dependencyGraph}
                    />
                  </div>
                </div>
              ) : (
                <div className="empty-state-inline">
                  <Network size={32} />
                  <p>No modules found in this repository</p>
                  <p className="empty-hint">
                    Module information is available for Java/Maven repositories with multi-module structure.
                  </p>
                  <button className="btn btn-primary" onClick={fetchModuleDependencies}>
                    <RefreshCw size={16} />
                    Load Modules
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* Business Features Section */}
      {isAnalyzed && (
        <section className="detail-section">
          <div
            className="section-header"
            onClick={() => toggleSection('features')}
          >
            <div className="section-title">
              <Boxes size={20} />
              <h2>Discovered Business Features</h2>
              {discoveredFeatures && (
                <span className="feature-count-badge">
                  {discoveredFeatures.summary.total_features} features
                </span>
              )}
            </div>
            {expandedSections.has('features') ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
          </div>
          {expandedSections.has('features') && (
            <div className="section-content">
              {featuresLoading ? (
                <div className="loading-inline">
                  <RefreshCw size={20} className="spin" />
                  <span>Discovering business features...</span>
                </div>
              ) : discoveredFeatures && discoveredFeatures.features.length > 0 ? (
                <div className="features-content">
                  {/* Grouped Features Accordion */}
                  <div className="feature-groups-container">
                    {discoveredFeatures.feature_groups.map((group) => (
                      <div key={group.name} className="feature-group">
                        <div
                          className="feature-group-header"
                          onClick={() => toggleFeatureGroup(group.name)}
                        >
                          {expandedGroups.has(group.name) ? (
                            <ChevronDown size={18} />
                          ) : (
                            <ChevronRight size={18} />
                          )}
                          <span className="group-name">{group.name}</span>
                          <span className="feature-count">{group.feature_count} feature{group.feature_count !== 1 ? 's' : ''}</span>
                        </div>
                        {expandedGroups.has(group.name) && (
                          <div className="feature-group-content">
                            {group.features.map((feature) => {
                              const fileName = feature.file_path
                                ? feature.file_path.split('/').pop() || feature.file_path
                                : null;
                              const entryPoint = feature.entry_points[0] || '';

                              return (
                                <div
                                  key={feature.id}
                                  className={`feature-row ${selectedFeature?.id === feature.id ? 'selected' : ''}`}
                                  onClick={() => setSelectedFeature(selectedFeature?.id === feature.id ? null : feature)}
                                >
                                  <div className="feature-row-main">
                                    <div className="feature-name-cell">
                                      <div className="feature-name">{feature.name}</div>
                                      <div className="feature-id">{feature.id}</div>
                                    </div>
                                    <div className="source-cell">
                                      <div className="source-info">
                                        <span className={`source-badge source-${feature.discovery_source}`}>
                                          {feature.discovery_source === 'service_cluster' ? 'service' : feature.discovery_source}
                                        </span>
                                        {fileName && (
                                          <div className="source-file" title={feature.file_path || ''}>
                                            {fileName}
                                          </div>
                                        )}
                                        {entryPoint && (
                                          <div className="source-entry-point">
                                            {entryPoint}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                    <div className="feature-actions-cell">
                                      <Link
                                        to={`/generate-brd?repository=${id}&feature=${encodeURIComponent(feature.name)}&mode=verified`}
                                        className="btn btn-small btn-primary"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        <FileText size={14} />
                                        Generate BRD
                                      </Link>
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Feature Detail Panel */}
                  {selectedFeature && (
                    <div className="feature-detail-panel">
                      <div className="feature-detail-header">
                        <h3>{selectedFeature.name}</h3>
                        <button
                          className="close-btn"
                          onClick={() => setSelectedFeature(null)}
                        >
                          <XCircle size={20} />
                        </button>
                      </div>
                      <div className="feature-detail-content">
                        <p className="feature-description">{selectedFeature.description}</p>

                        <div className="detail-grid">
                          <div className="detail-item">
                            <span className="detail-label">Category</span>
                            <span className={`category-badge category-${selectedFeature.category}`}>
                              {selectedFeature.category.replace('_', ' ')}
                            </span>
                          </div>
                          <div className="detail-item">
                            <span className="detail-label">Complexity</span>
                            <span>{selectedFeature.complexity} ({selectedFeature.complexity_score}/100)</span>
                          </div>
                          <div className="detail-item">
                            <span className="detail-label">Discovery Source</span>
                            <span>{selectedFeature.discovery_source}</span>
                          </div>
                          <div className="detail-item">
                            <span className="detail-label">Test Coverage</span>
                            <span>
                              {selectedFeature.has_tests
                                ? `~${selectedFeature.test_coverage_estimate || 0}%`
                                : 'No tests'}
                            </span>
                          </div>
                        </div>

                        {/* Code Footprint */}
                        <div className="footprint-section">
                          <h4>Code Footprint</h4>
                          <div className="footprint-grid">
                            {selectedFeature.code_footprint.controllers.length > 0 && (
                              <div className="footprint-item">
                                <span className="footprint-label">Controllers</span>
                                <ul>
                                  {selectedFeature.code_footprint.controllers.map((c, i) => (
                                    <li key={i}>{c}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {selectedFeature.code_footprint.services.length > 0 && (
                              <div className="footprint-item">
                                <span className="footprint-label">Services</span>
                                <ul>
                                  {selectedFeature.code_footprint.services.map((s, i) => (
                                    <li key={i}>{s}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {selectedFeature.code_footprint.repositories.length > 0 && (
                              <div className="footprint-item">
                                <span className="footprint-label">Repositories</span>
                                <ul>
                                  {selectedFeature.code_footprint.repositories.map((r, i) => (
                                    <li key={i}>{r}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {selectedFeature.code_footprint.views.length > 0 && (
                              <div className="footprint-item">
                                <span className="footprint-label">Views</span>
                                <ul>
                                  {selectedFeature.code_footprint.views.map((v, i) => (
                                    <li key={i}>{v}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* API Endpoints */}
                        {selectedFeature.endpoints.length > 0 && (
                          <div className="endpoints-section">
                            <h4>API Endpoints ({selectedFeature.endpoints.length})</h4>
                            <div className="endpoints-list">
                              {selectedFeature.endpoints.map((ep, i) => (
                                <div key={i} className="endpoint-item">
                                  <span className={`method-badge method-${ep.method.toLowerCase()}`}>
                                    {ep.method}
                                  </span>
                                  <code className="endpoint-path">{ep.path}</code>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        <div className="feature-actions">
                          <Link
                            to={`/generate-brd?repository=${id}&feature=${encodeURIComponent(selectedFeature.name)}&description=${encodeURIComponent(selectedFeature.description)}&mode=verified`}
                            className="btn btn-primary"
                          >
                            <FileText size={16} />
                            Generate BRD for this Feature
                          </Link>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ) : discoveredFeatures ? (
                <div className="empty-state-inline">
                  <Boxes size={32} />
                  <p>No business features discovered in this codebase.</p>
                  <p className="empty-hint">
                    Features are discovered from Controllers, Web Flows, and Service clusters.
                  </p>
                </div>
              ) : (
                <div className="empty-state-inline">
                  <Boxes size={32} />
                  <p>Click to discover business features from the codebase</p>
                  <button className="btn btn-primary" onClick={fetchDiscoveredFeatures}>
                    <RefreshCw size={16} />
                    Discover Features
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* Agentic Readiness Section */}
      {isAnalyzed && (
        <section className="detail-section">
          <div
            className="section-header"
            onClick={() => toggleSection('readiness')}
          >
            <div className="section-title">
              <Zap size={20} />
              <h2>Agentic Readiness Report</h2>
              {readinessReport && (
                <span
                  className="grade-badge"
                  style={{
                    backgroundColor: gradeBackgrounds[readinessReport.overall_grade],
                    color: gradeColors[readinessReport.overall_grade],
                  }}
                >
                  Grade {readinessReport.overall_grade}
                </span>
              )}
            </div>
            {expandedSections.has('readiness') ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
          </div>
          {expandedSections.has('readiness') && (
            <div className="section-content">
              {readinessLoading ? (
                <div className="loading-inline">
                  <RefreshCw size={20} className="spin" />
                  <span>Loading readiness report...</span>
                </div>
              ) : readinessReport ? (
                <div className="readiness-content">
                  {/* Overall Score */}
                  <div className="readiness-overview">
                    <div className="overall-score">
                      <div
                        className="score-circle"
                        style={{
                          borderColor: gradeColors[readinessReport.overall_grade],
                          backgroundColor: gradeBackgrounds[readinessReport.overall_grade],
                        }}
                      >
                        <span className="score-grade">{readinessReport.overall_grade}</span>
                        <span className="score-value">{readinessReport.overall_score}%</span>
                      </div>
                      <div className="score-info">
                        <h3>Overall Readiness</h3>
                        <p>
                          {readinessReport.is_agentic_ready ? (
                            <span className="ready-status ready">
                              <CheckCircle2 size={16} /> Agentic Ready
                            </span>
                          ) : (
                            <span className="ready-status not-ready">
                              <AlertTriangle size={16} /> Not Yet Ready
                            </span>
                          )}
                        </p>
                      </div>
                    </div>

                    <div className="summary-cards">
                      <div className="summary-card">
                        <TrendingUp size={20} />
                        <div>
                          <span className="summary-value">{readinessReport.summary.total_entities}</span>
                          <span className="summary-label">Total Entities</span>
                        </div>
                      </div>
                      <div className="summary-card">
                        <TestTube size={20} />
                        <div>
                          <span className="summary-value">{readinessReport.summary.tested_entities}</span>
                          <span className="summary-label">Tested</span>
                        </div>
                      </div>
                      <div className="summary-card">
                        <BookOpen size={20} />
                        <div>
                          <span className="summary-value">{readinessReport.summary.documented_entities}</span>
                          <span className="summary-label">Documented</span>
                        </div>
                      </div>
                      <div className="summary-card critical">
                        <AlertTriangle size={20} />
                        <div>
                          <span className="summary-value">{readinessReport.summary.critical_gaps}</span>
                          <span className="summary-label">Critical Gaps</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Critical Gaps Details - Show what the gaps are */}
                  {readinessReport.summary.critical_gaps > 0 && readinessReport.recommendations.length > 0 && (
                    <div className="critical-gaps-details">
                      <h3><AlertTriangle size={18} /> Critical Gaps Breakdown</h3>
                      <div className="gaps-grid">
                        {readinessReport.recommendations
                          .filter(rec => rec.priority === 'high' || rec.priority === 'medium')
                          .map((rec, index) => (
                            <div key={index} className={`gap-card priority-${rec.priority}`}>
                              <div className="gap-header">
                                <span className={`gap-priority priority-${rec.priority}`}>
                                  {rec.priority.toUpperCase()}
                                </span>
                                <span className="gap-category">{rec.category}</span>
                              </div>
                              <h4 className="gap-title">{rec.title}</h4>
                              <p className="gap-description">{rec.description}</p>
                              <div className="gap-footer">
                                <span className="gap-affected">
                                  <AlertTriangle size={14} />
                                  {rec.affected_count} entities affected
                                </span>
                              </div>
                            </div>
                          ))}
                      </div>
                    </div>
                  )}

                  {/* Testing & Documentation Cards */}
                  <div className="assessment-cards">
                    {/* Testing Card */}
                    <div className="assessment-card">
                      <div className="assessment-header">
                        <TestTube size={24} />
                        <h3>Testing Readiness</h3>
                        <span
                          className="grade-badge small"
                          style={{
                            backgroundColor: gradeBackgrounds[readinessReport.testing.overall_grade],
                            color: gradeColors[readinessReport.testing.overall_grade],
                          }}
                        >
                          {readinessReport.testing.overall_grade}
                        </span>
                      </div>
                      <div className="assessment-content">
                        <div className="progress-bar-container">
                          <div className="progress-label">
                            <span>Coverage</span>
                            <span>{readinessReport.testing.coverage.percentage}%</span>
                          </div>
                          <div className="progress-bar">
                            <div
                              className="progress-fill"
                              style={{
                                width: `${readinessReport.testing.coverage.percentage}%`,
                                backgroundColor: gradeColors[readinessReport.testing.coverage.grade],
                              }}
                            />
                          </div>
                        </div>
                        <div className="test-quality">
                          <div className={`quality-item ${readinessReport.testing.test_quality.has_unit_tests ? 'has' : ''}`}>
                            {readinessReport.testing.test_quality.has_unit_tests ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                            Unit Tests
                          </div>
                          <div className={`quality-item ${readinessReport.testing.test_quality.has_integration_tests ? 'has' : ''}`}>
                            {readinessReport.testing.test_quality.has_integration_tests ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                            Integration Tests
                          </div>
                          <div className={`quality-item ${readinessReport.testing.test_quality.has_e2e_tests ? 'has' : ''}`}>
                            {readinessReport.testing.test_quality.has_e2e_tests ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                            E2E Tests
                          </div>
                        </div>
                        {readinessReport.testing.untested_critical_functions.length > 0 && (
                          <div className="critical-items">
                            <span className="critical-label">
                              {readinessReport.testing.untested_critical_functions.length} untested critical functions
                            </span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Documentation Card */}
                    <div className="assessment-card">
                      <div className="assessment-header">
                        <BookOpen size={24} />
                        <h3>Documentation Readiness</h3>
                        <span
                          className="grade-badge small"
                          style={{
                            backgroundColor: gradeBackgrounds[readinessReport.documentation.overall_grade],
                            color: gradeColors[readinessReport.documentation.overall_grade],
                          }}
                        >
                          {readinessReport.documentation.overall_grade}
                        </span>
                      </div>
                      <div className="assessment-content">
                        <div className="progress-bar-container">
                          <div className="progress-label">
                            <span>Overall Coverage</span>
                            <span>{readinessReport.documentation.coverage.percentage}%</span>
                          </div>
                          <div className="progress-bar">
                            <div
                              className="progress-fill"
                              style={{
                                width: `${readinessReport.documentation.coverage.percentage}%`,
                                backgroundColor: gradeColors[readinessReport.documentation.coverage.grade],
                              }}
                            />
                          </div>
                        </div>
                        <div className="progress-bar-container">
                          <div className="progress-label">
                            <span>Public API Coverage</span>
                            <span>{readinessReport.documentation.public_api_coverage.percentage}%</span>
                          </div>
                          <div className="progress-bar">
                            <div
                              className="progress-fill"
                              style={{
                                width: `${readinessReport.documentation.public_api_coverage.percentage}%`,
                                backgroundColor: gradeColors[readinessReport.documentation.public_api_coverage.grade],
                              }}
                            />
                          </div>
                        </div>
                        {readinessReport.documentation.undocumented_public_apis.length > 0 && (
                          <div className="critical-items">
                            <span className="critical-label">
                              {readinessReport.documentation.undocumented_public_apis.length} undocumented public APIs
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Recommendations */}
                  {readinessReport.recommendations.length > 0 && (
                    <div className="recommendations">
                      <h3>Recommendations</h3>
                      <div className="recommendation-list">
                        {readinessReport.recommendations.map((rec, index) => (
                          <div key={index} className={`recommendation-item priority-${rec.priority}`}>
                            <div className="rec-priority">
                              {rec.priority === 'high' && <AlertTriangle size={16} />}
                              {rec.priority === 'medium' && <AlertTriangle size={16} />}
                              {rec.priority === 'low' && <CheckCircle2 size={16} />}
                              {rec.priority.toUpperCase()}
                            </div>
                            <div className="rec-content">
                              <span className="rec-category">{rec.category}</span>
                              <h4>{rec.title}</h4>
                              <p>{rec.description}</p>
                              <span className="rec-affected">{rec.affected_count} entities affected</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="empty-state-inline">
                  <Zap size={32} />
                  <p>Click refresh to generate the readiness report</p>
                  <button className="btn btn-primary" onClick={fetchReadinessReport}>
                    <RefreshCw size={16} />
                    Generate Report
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* Enrichment Actions Section */}
      {isAnalyzed && (
        <section className="detail-section">
          <div
            className="section-header"
            onClick={() => toggleSection('enrichment')}
          >
            <div className="section-title">
              <Sparkles size={20} />
              <h2>Enrich Codebase</h2>
            </div>
            {expandedSections.has('enrichment') ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
          </div>
          {expandedSections.has('enrichment') && (
            <div className="section-content">
              <p className="section-description">
                Use AI to automatically generate documentation and tests for your codebase.
              </p>

              <div className="enrichment-cards">
                {/* Documentation Enrichment */}
                <div className="enrichment-card">
                  <div className="enrichment-icon">
                    <BookOpen size={32} />
                  </div>
                  <h3>Generate Documentation</h3>
                  <p>Auto-generate JSDoc, JavaDoc, or docstrings for undocumented functions and classes.</p>
                  <ul className="enrichment-features">
                    <li>Function descriptions</li>
                    <li>Parameter documentation</li>
                    <li>Return type descriptions</li>
                    <li>Usage examples</li>
                  </ul>
                  <button
                    className="btn btn-primary"
                    onClick={handleEnrichDocumentation}
                    disabled={enrichmentLoading === 'documentation'}
                  >
                    {enrichmentLoading === 'documentation' ? (
                      <>
                        <RefreshCw size={16} className="spin" />
                        Generating...
                      </>
                    ) : (
                      <>
                        <Sparkles size={16} />
                        Generate Documentation
                      </>
                    )}
                  </button>
                </div>

                {/* Test Enrichment */}
                <div className="enrichment-card">
                  <div className="enrichment-icon">
                    <TestTube size={32} />
                  </div>
                  <h3>Generate Tests</h3>
                  <p>Auto-generate test skeletons for untested functions using Jest, Pytest, or JUnit.</p>
                  <ul className="enrichment-features">
                    <li>Unit test templates</li>
                    <li>Mock setup code</li>
                    <li>Edge case tests</li>
                    <li>Assertion patterns</li>
                  </ul>
                  <button
                    className="btn btn-primary"
                    onClick={handleEnrichTests}
                    disabled={enrichmentLoading === 'tests'}
                  >
                    {enrichmentLoading === 'tests' ? (
                      <>
                        <RefreshCw size={16} className="spin" />
                        Generating...
                      </>
                    ) : (
                      <>
                        <Sparkles size={16} />
                        Generate Tests
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Enrichment Result */}
              {enrichmentResult && (
                <div className="enrichment-result">
                  <h4>
                    {enrichmentResult.success ? (
                      <><CheckCircle2 size={20} /> Enrichment Complete</>
                    ) : (
                      <><XCircle size={20} /> Enrichment Failed</>
                    )}
                  </h4>
                  <div className="result-stats">
                    <span>Processed: {enrichmentResult.entities_processed}</span>
                    <span>Enriched: {enrichmentResult.entities_enriched}</span>
                    <span>Skipped: {enrichmentResult.entities_skipped}</span>
                  </div>
                  {enrichmentResult.generated_content.length > 0 && (
                    <div className="generated-preview">
                      <h5>Generated Content Preview</h5>
                      {enrichmentResult.generated_content.slice(0, 3).map((content, idx) => (
                        <div key={idx} className="content-preview">
                          <span className="content-path">{content.file_path}</span>
                          <code>{content.content.slice(0, 200)}...</code>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </section>
      )}

      <style>{`
        .spin {
          animation: spin 1s linear infinite;
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>

      {/* Wiki Configuration Modal */}
      {showWikiConfig && (
        <div className="wiki-config-modal-overlay" onClick={() => setShowWikiConfig(false)}>
          <div className="wiki-config-modal" onClick={(e) => e.stopPropagation()}>
            <div className="wiki-config-modal-header">
              <div className="modal-title">
                <Book size={24} />
                <div>
                  <h2>Configure Analysis</h2>
                  <p>Set up wiki documentation options before analyzing {repository.name}</p>
                </div>
              </div>
              <button className="close-btn" onClick={() => setShowWikiConfig(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="wiki-config-modal-body">
              <WikiConfigurationPanel
                onConfigurationChange={handleWikiConfigChange}
                repositoryName={repository.name}
              />
            </div>
            <div className="wiki-config-modal-footer">
              <button className="btn btn-outline" onClick={() => setShowWikiConfig(false)}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleAnalyze}
                disabled={analyzing}
              >
                {analyzing ? (
                  <>
                    <RefreshCw size={16} className="spin" />
                    Starting Analysis...
                  </>
                ) : (
                  <>
                    <Play size={16} />
                    Start Analysis
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
