import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
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
  ExternalLink,
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
} from 'lucide-react';
import {
  getRepository,
  getReadinessReport,
  getCodebaseStatistics,
  getDiscoveredFeatures,
  enrichDocumentation,
  enrichTests,
  type RepositoryDetail as RepoDetail,
  type AgenticReadinessResponse,
  type CodebaseStatisticsResponse,
  type DiscoveredFeaturesResponse,
  type BusinessFeature,
  type EnrichmentResponse,
} from '../../services/api';
import { analyzeRepository } from '../../api/client';
import { LoadingSpinner } from '../../components/LoadingSpinner';
import { StatusBadge } from '../../components/StatusBadge';
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
  const [repository, setRepository] = useState<RepoDetail | null>(null);
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
  const [error, setError] = useState<string | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['overview', 'statistics', 'readiness']));

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

  const handleAnalyze = async () => {
    if (!id) return;
    try {
      await analyzeRepository(id);
      await fetchRepository();
    } catch (err) {
      console.error('Failed to analyze repository:', err);
    }
  };

  useEffect(() => {
    fetchRepository();
  }, [id]);

  useEffect(() => {
    if (repository?.analysis_status === 'completed') {
      fetchReadinessReport();
      fetchStatistics();
      fetchDiscoveredFeatures();
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
          <a
            href={repository.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-outline"
          >
            <ExternalLink size={16} />
            View on {repository.platform}
          </a>
          {isAnalyzed && (
            <Link to={`/generate-brd?repository=${id}`} className="btn btn-primary">
              <FileText size={16} />
              Generate BRD
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

            {!isAnalyzed && (
              <div className="action-banner">
                <AlertTriangle size={24} />
                <div className="banner-content">
                  <h4>Repository Not Analyzed</h4>
                  <p>Run analysis to enable Agentic Readiness reports and code enrichment features.</p>
                </div>
                <button
                  className="btn btn-primary"
                  onClick={handleAnalyze}
                  disabled={repository.status !== 'cloned'}
                >
                  <Play size={16} />
                  Analyze Now
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
                  {/* Features Table */}
                  <div className="features-table-container">
                    <table className="features-table">
                      <thead>
                        <tr>
                          <th>Feature</th>
                          <th>Source</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {discoveredFeatures.features.map((feature) => {
                          // Extract filename from file_path
                          const fileName = feature.file_path
                            ? feature.file_path.split('/').pop() || feature.file_path
                            : null;
                          const entryPoint = feature.entry_points[0] || '';

                          return (
                            <tr
                              key={feature.id}
                              className={selectedFeature?.id === feature.id ? 'selected' : ''}
                              onClick={() => setSelectedFeature(selectedFeature?.id === feature.id ? null : feature)}
                            >
                              <td className="feature-name-cell">
                                <div className="feature-name">{feature.name}</div>
                                <div className="feature-id">{feature.id}</div>
                              </td>
                              <td className="source-cell">
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
                              </td>
                              <td>
                                <Link
                                  to={`/generate-brd?repository=${id}&feature=${encodeURIComponent(feature.name)}`}
                                  className="btn btn-small btn-primary"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <FileText size={14} />
                                  BRD
                                </Link>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
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
                            to={`/generate-brd?repository=${id}&feature=${encodeURIComponent(selectedFeature.name)}&description=${encodeURIComponent(selectedFeature.description)}`}
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
    </div>
  );
}
