import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Search,
  Loader2,
  FileCode,
  Server,
  Database,
  Layout,
  TestTube,
  Settings,
  Workflow,
  ChevronDown,
  ChevronRight,
  AlertCircle,
  CheckCircle,
  FolderGit2,
  Code2,
  Layers,
  Box,
  GitBranch,
  ArrowRight,
  ListTree,
} from 'lucide-react';
import { getAnalyzedRepositories, type RepositorySummary } from '../../services/api';
import './ContextExplorer.css';

// API types matching backend
interface FileInfo {
  path: string;
  name: string;
  type: string;
  relevance: string;
  relevance_score: number;
  content_preview?: string;
}

interface ComponentInfo {
  name: string;
  type: string;
  path: string;
  description: string;
  dependencies: string[];
  dependents: string[];
}

interface APIEndpointInfo {
  endpoint: string;
  method: string;
  service: string;
  handler_file?: string;
}

interface DatabaseEntityInfo {
  name: string;
  type: string;
  fields: string[];
  file_path?: string;
}

interface WebFlowInfo {
  flow_id: string;
  file_path: string;
  states: string[];
  description?: string;
}

interface CategorizedContext {
  frontend_files: FileInfo[];
  jsp_files: FileInfo[];
  backend_files: FileInfo[];
  controllers: ComponentInfo[];
  services: ComponentInfo[];
  repositories: ComponentInfo[];
  api_endpoints: APIEndpointInfo[];
  database_entities: DatabaseEntityInfo[];
  data_models: ComponentInfo[];
  webflow_definitions: WebFlowInfo[];
  config_files: FileInfo[];
  test_files: FileInfo[];
  other_components: ComponentInfo[];
}

interface ExploreContextResponse {
  success: boolean;
  feature_description: string;
  total_components: number;
  total_files: number;
  total_api_endpoints: number;
  total_database_entities: number;
  context: CategorizedContext;
  available_labels: string[];
  available_relationships: string[];
  search_keywords: string[];
  warnings: string[];
}

// Flow Graph types
interface FlowGraphNode {
  id: string;
  name: string;
  type: string;
  layer: 'presentation' | 'controller' | 'service' | 'data';
  path?: string;
}

interface FlowGraphEdge {
  source: string;
  target: string;
  relationship: string;
  label?: string;
}

interface FlowGraphResponse {
  success: boolean;
  nodes: FlowGraphNode[];
  edges: FlowGraphEdge[];
  entry_points: string[];
  exit_points: string[];
}

const BACKEND_API_URL = import.meta.env.VITE_BACKEND_API_URL || '/backend';

async function exploreContext(
  featureDescription: string,
  repositoryId?: string,
  includeFileContents?: boolean
): Promise<ExploreContextResponse> {
  const response = await fetch(`${BACKEND_API_URL}/api/v1/context/explore`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      feature_description: featureDescription,
      repository_id: repositoryId,
      include_file_contents: includeFileContents,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to explore context');
  }

  return response.json();
}

async function getFlowGraph(
  featureDescription: string,
  repositoryId?: string
): Promise<FlowGraphResponse> {
  const params = new URLSearchParams({
    feature_description: featureDescription,
    ...(repositoryId && { repository_id: repositoryId }),
  });

  const response = await fetch(`${BACKEND_API_URL}/api/v1/context/flow-graph?${params}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to get flow graph');
  }

  return response.json();
}

// Collapsible section component
function CollapsibleSection({
  title,
  icon: Icon,
  count,
  children,
  defaultOpen = false,
  variant = 'default',
}: {
  title: string;
  icon: React.ComponentType<{ size?: number }>;
  count: number;
  children: React.ReactNode;
  defaultOpen?: boolean;
  variant?: 'frontend' | 'backend' | 'data' | 'config' | 'test' | 'default';
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  if (count === 0) return null;

  const variantClass = `section-${variant}`;

  return (
    <div className={`context-section ${variantClass}`}>
      <button
        className="section-header"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="section-title">
          {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          <Icon size={18} />
          <span>{title}</span>
        </div>
        <span className="section-count">{count}</span>
      </button>
      {isOpen && <div className="section-content">{children}</div>}
    </div>
  );
}

// File item component
function FileItem({ file }: { file: FileInfo }) {
  return (
    <div className="context-item file-item">
      <div className="item-header">
        <FileCode size={14} />
        <span className="item-name">{file.name}</span>
        <span className="item-type">{file.type}</span>
      </div>
      <div className="item-path">{file.path}</div>
      {file.relevance && <div className="item-relevance">{file.relevance}</div>}
    </div>
  );
}

// Component item
function ComponentItem({ component }: { component: ComponentInfo }) {
  return (
    <div className="context-item component-item">
      <div className="item-header">
        <Box size={14} />
        <span className="item-name">{component.name}</span>
        <span className="item-type">{component.type}</span>
      </div>
      <div className="item-path">{component.path}</div>
      {component.description && (
        <div className="item-description">{component.description}</div>
      )}
      {component.dependencies.length > 0 && (
        <div className="item-deps">
          <span className="deps-label">Dependencies:</span>
          <span className="deps-list">{component.dependencies.slice(0, 5).join(', ')}</span>
          {component.dependencies.length > 5 && (
            <span className="deps-more">+{component.dependencies.length - 5} more</span>
          )}
        </div>
      )}
    </div>
  );
}

// API endpoint item
function APIEndpointItem({ endpoint }: { endpoint: APIEndpointInfo }) {
  return (
    <div className="context-item api-item">
      <div className="item-header">
        <Server size={14} />
        <span className={`http-method ${endpoint.method.toLowerCase()}`}>
          {endpoint.method}
        </span>
        <span className="item-name">{endpoint.endpoint}</span>
      </div>
      <div className="item-service">Service: {endpoint.service}</div>
    </div>
  );
}

// Database entity item
function DatabaseEntityItem({ entity }: { entity: DatabaseEntityInfo }) {
  return (
    <div className="context-item db-item">
      <div className="item-header">
        <Database size={14} />
        <span className="item-name">{entity.name}</span>
        <span className="item-type">{entity.type}</span>
      </div>
      {entity.file_path && <div className="item-path">{entity.file_path}</div>}
      {entity.fields.length > 0 && (
        <div className="item-fields">
          Fields: {entity.fields.slice(0, 5).join(', ')}
          {entity.fields.length > 5 && ` +${entity.fields.length - 5} more`}
        </div>
      )}
    </div>
  );
}

// WebFlow item
function WebFlowItem({ flow }: { flow: WebFlowInfo }) {
  return (
    <div className="context-item flow-item">
      <div className="item-header">
        <Workflow size={14} />
        <span className="item-name">{flow.flow_id}</span>
      </div>
      <div className="item-path">{flow.file_path}</div>
      {flow.states.length > 0 && (
        <div className="item-states">
          States: {flow.states.slice(0, 5).join(', ')}
          {flow.states.length > 5 && ` +${flow.states.length - 5} more`}
        </div>
      )}
    </div>
  );
}

// Layer colors
const LAYER_COLORS = {
  presentation: { bg: '#8b5cf620', border: '#8b5cf6', text: '#8b5cf6' },
  controller: { bg: '#f59e0b20', border: '#f59e0b', text: '#f59e0b' },
  service: { bg: '#3b82f620', border: '#3b82f6', text: '#3b82f6' },
  data: { bg: '#22c55e20', border: '#22c55e', text: '#22c55e' },
};

const LAYER_LABELS = {
  presentation: 'UI / Presentation',
  controller: 'Controllers / Actions',
  service: 'Services / Business Logic',
  data: 'Data Access / Repository',
};

// Flow Graph Visualization Component
function FlowGraphVisualization({ flowGraph }: { flowGraph: FlowGraphResponse }) {
  const [selectedNode, setSelectedNode] = useState<FlowGraphNode | null>(null);

  // Group nodes by layer
  const nodesByLayer = useMemo(() => {
    const grouped: Record<string, FlowGraphNode[]> = {
      presentation: [],
      controller: [],
      service: [],
      data: [],
    };

    flowGraph.nodes.forEach((node) => {
      if (grouped[node.layer]) {
        grouped[node.layer].push(node);
      } else {
        grouped.service.push(node); // Default to service layer
      }
    });

    return grouped;
  }, [flowGraph.nodes]);

  // Create node position map for edges
  const nodePositions = useMemo(() => {
    const positions: Record<string, { x: number; y: number }> = {};
    const layers = ['presentation', 'controller', 'service', 'data'];
    const layerY = { presentation: 60, controller: 160, service: 260, data: 360 };

    layers.forEach((layer) => {
      const nodes = nodesByLayer[layer];
      const spacing = 800 / (nodes.length + 1);
      nodes.forEach((node, idx) => {
        positions[node.id] = {
          x: spacing * (idx + 1),
          y: layerY[layer as keyof typeof layerY],
        };
      });
    });

    return positions;
  }, [nodesByLayer]);

  if (flowGraph.nodes.length === 0) {
    return (
      <div className="flow-graph-empty">
        <GitBranch size={48} />
        <h3>No Flow Data</h3>
        <p>No relationships found between components for this feature.</p>
      </div>
    );
  }

  return (
    <div className="flow-graph-container">
      <div className="flow-graph-legend">
        {Object.entries(LAYER_LABELS).map(([layer, label]) => (
          <div key={layer} className="legend-item">
            <div
              className="legend-color"
              style={{
                backgroundColor: LAYER_COLORS[layer as keyof typeof LAYER_COLORS].bg,
                borderColor: LAYER_COLORS[layer as keyof typeof LAYER_COLORS].border,
              }}
            />
            <span>{label}</span>
            <span className="legend-count">({nodesByLayer[layer]?.length || 0})</span>
          </div>
        ))}
      </div>

      <div className="flow-graph-svg-container">
        <svg width="100%" height="450" viewBox="0 0 800 450" preserveAspectRatio="xMidYMid meet">
          {/* Layer backgrounds */}
          {Object.entries(LAYER_LABELS).map(([layer], idx) => (
            <g key={layer}>
              <rect
                x="0"
                y={idx * 100 + 20}
                width="800"
                height="90"
                fill={LAYER_COLORS[layer as keyof typeof LAYER_COLORS].bg}
                rx="8"
              />
              <text
                x="10"
                y={idx * 100 + 45}
                fill={LAYER_COLORS[layer as keyof typeof LAYER_COLORS].text}
                fontSize="12"
                fontWeight="600"
              >
                {LAYER_LABELS[layer as keyof typeof LAYER_LABELS]}
              </text>
            </g>
          ))}

          {/* Edges */}
          <g className="edges">
            {flowGraph.edges.map((edge, idx) => {
              const source = nodePositions[edge.source];
              const target = nodePositions[edge.target];
              if (!source || !target) return null;

              const midY = (source.y + target.y) / 2;

              return (
                <g key={idx}>
                  <path
                    d={`M ${source.x} ${source.y + 15} Q ${source.x} ${midY} ${target.x} ${target.y - 15}`}
                    fill="none"
                    stroke="var(--border-color)"
                    strokeWidth="2"
                    markerEnd="url(#arrowhead)"
                  />
                </g>
              );
            })}
          </g>

          {/* Arrow marker */}
          <defs>
            <marker
              id="arrowhead"
              markerWidth="10"
              markerHeight="7"
              refX="9"
              refY="3.5"
              orient="auto"
            >
              <polygon points="0 0, 10 3.5, 0 7" fill="var(--text-muted)" />
            </marker>
          </defs>

          {/* Nodes */}
          <g className="nodes">
            {flowGraph.nodes.map((node) => {
              const pos = nodePositions[node.id];
              if (!pos) return null;

              const colors = LAYER_COLORS[node.layer as keyof typeof LAYER_COLORS] || LAYER_COLORS.service;
              const isSelected = selectedNode?.id === node.id;
              const isEntryPoint = flowGraph.entry_points.includes(node.id);
              const isExitPoint = flowGraph.exit_points.includes(node.id);

              return (
                <g
                  key={node.id}
                  transform={`translate(${pos.x - 60}, ${pos.y - 15})`}
                  onClick={() => setSelectedNode(node)}
                  style={{ cursor: 'pointer' }}
                >
                  <rect
                    width="120"
                    height="30"
                    rx="6"
                    fill={isSelected ? colors.border : 'var(--bg-primary)'}
                    stroke={colors.border}
                    strokeWidth={isEntryPoint || isExitPoint ? 3 : 2}
                    strokeDasharray={isEntryPoint ? '5,3' : undefined}
                  />
                  <text
                    x="60"
                    y="19"
                    textAnchor="middle"
                    fill={isSelected ? 'white' : 'var(--text-primary)'}
                    fontSize="10"
                    fontWeight="500"
                  >
                    {node.name.length > 15 ? node.name.substring(0, 15) + '...' : node.name}
                  </text>
                  {isEntryPoint && (
                    <circle cx="0" cy="15" r="4" fill="#22c55e" />
                  )}
                  {isExitPoint && (
                    <circle cx="120" cy="15" r="4" fill="#ef4444" />
                  )}
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      {selectedNode && (
        <div className="flow-node-details">
          <h4>{selectedNode.name}</h4>
          <div className="node-detail-row">
            <span className="detail-label">Type:</span>
            <span className="detail-value">{selectedNode.type}</span>
          </div>
          <div className="node-detail-row">
            <span className="detail-label">Layer:</span>
            <span className="detail-value">{LAYER_LABELS[selectedNode.layer as keyof typeof LAYER_LABELS]}</span>
          </div>
          {selectedNode.path && (
            <div className="node-detail-row">
              <span className="detail-label">Path:</span>
              <span className="detail-value path">{selectedNode.path}</span>
            </div>
          )}
          <div className="node-connections">
            <span className="detail-label">Connections:</span>
            <div className="connections-list">
              {flowGraph.edges
                .filter((e) => e.source === selectedNode.id || e.target === selectedNode.id)
                .map((edge, idx) => {
                  const isOutgoing = edge.source === selectedNode.id;
                  const otherNodeId = isOutgoing ? edge.target : edge.source;
                  const otherNode = flowGraph.nodes.find((n) => n.id === otherNodeId);
                  return (
                    <div key={idx} className="connection-item">
                      <ArrowRight
                        size={12}
                        style={{ transform: isOutgoing ? 'none' : 'rotate(180deg)' }}
                      />
                      <span>{edge.label || edge.relationship}</span>
                      <span className="connection-target">{otherNode?.name || otherNodeId}</span>
                    </div>
                  );
                })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function ContextExplorer() {
  const [featureDescription, setFeatureDescription] = useState('');
  const [selectedRepo, setSelectedRepo] = useState<string>('');
  const [includeFileContents, setIncludeFileContents] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<ExploreContextResponse | null>(null);
  const [flowGraph, setFlowGraph] = useState<FlowGraphResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'categories' | 'flow'>('categories');

  // Fetch repositories
  const { data: repositories, isLoading: loadingRepos } = useQuery({
    queryKey: ['analyzedRepositories'],
    queryFn: getAnalyzedRepositories,
  });

  const handleSearch = async () => {
    if (!featureDescription.trim()) return;

    setIsSearching(true);
    setError(null);

    try {
      // Fetch both context and flow graph in parallel
      const [contextResults, graphResults] = await Promise.all([
        exploreContext(featureDescription, selectedRepo || undefined, includeFileContents),
        getFlowGraph(featureDescription, selectedRepo || undefined),
      ]);

      setSearchResults(contextResults);
      setFlowGraph(graphResults);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to explore context');
      setSearchResults(null);
      setFlowGraph(null);
    } finally {
      setIsSearching(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSearch();
    }
  };

  return (
    <div className="context-explorer">
      <div className="explorer-header">
        <div className="header-title">
          <Search size={24} />
          <h1>Context Explorer</h1>
        </div>
        <p className="header-description">
          Explore how features flow through your codebase. Enter a feature description to discover
          related components, files, and their relationships across all layers.
        </p>
      </div>

      <div className="search-section">
        <div className="search-controls">
          <div className="search-input-wrapper">
            <textarea
              className="search-input"
              placeholder="Enter a feature description (e.g., 'Legal Entity Search', 'User Authentication', 'Payment Processing')"
              value={featureDescription}
              onChange={(e) => setFeatureDescription(e.target.value)}
              onKeyDown={handleKeyPress}
              rows={3}
            />
          </div>

          <div className="search-options">
            <div className="option-group">
              <label>
                <FolderGit2 size={16} />
                Repository (optional):
              </label>
              <select
                value={selectedRepo}
                onChange={(e) => setSelectedRepo(e.target.value)}
                disabled={loadingRepos}
              >
                <option value="">All Repositories</option>
                {repositories?.map((repo: RepositorySummary) => (
                  <option key={repo.id} value={repo.id}>
                    {repo.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="option-group checkbox">
              <label>
                <input
                  type="checkbox"
                  checked={includeFileContents}
                  onChange={(e) => setIncludeFileContents(e.target.checked)}
                />
                Include file content previews
              </label>
            </div>
          </div>

          <button
            className="search-button"
            onClick={handleSearch}
            disabled={isSearching || !featureDescription.trim()}
          >
            {isSearching ? (
              <>
                <Loader2 size={18} className="spinning" />
                Exploring...
              </>
            ) : (
              <>
                <Search size={18} />
                Explore Context
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="error-message">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {searchResults && (
        <div className="results-section">
          <div className="results-summary">
            <div className="summary-header">
              <CheckCircle size={20} />
              <h2>Context Results</h2>
            </div>

            <div className="summary-stats">
              <div className="stat">
                <span className="stat-value">{searchResults.total_components}</span>
                <span className="stat-label">Components</span>
              </div>
              <div className="stat">
                <span className="stat-value">{searchResults.total_files}</span>
                <span className="stat-label">Files</span>
              </div>
              <div className="stat">
                <span className="stat-value">{searchResults.total_api_endpoints}</span>
                <span className="stat-label">API Endpoints</span>
              </div>
              <div className="stat">
                <span className="stat-value">{searchResults.total_database_entities}</span>
                <span className="stat-label">DB Entities</span>
              </div>
            </div>

            {searchResults.search_keywords.length > 0 && (
              <div className="search-keywords">
                <span className="keywords-label">Search keywords:</span>
                <div className="keywords-list">
                  {searchResults.search_keywords.map((kw, i) => (
                    <span key={i} className="keyword-tag">{kw}</span>
                  ))}
                </div>
              </div>
            )}

            {searchResults.warnings.length > 0 && (
              <div className="warnings">
                {searchResults.warnings.map((warning, i) => (
                  <div key={i} className="warning-item">
                    <AlertCircle size={14} />
                    <span>{warning}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Tab Navigation */}
          <div className="view-tabs">
            <button
              className={`view-tab ${activeTab === 'categories' ? 'active' : ''}`}
              onClick={() => setActiveTab('categories')}
            >
              <ListTree size={16} />
              Categories View
            </button>
            <button
              className={`view-tab ${activeTab === 'flow' ? 'active' : ''}`}
              onClick={() => setActiveTab('flow')}
            >
              <GitBranch size={16} />
              Flow Graph
            </button>
          </div>

          {activeTab === 'flow' && flowGraph && (
            <FlowGraphVisualization flowGraph={flowGraph} />
          )}

          {activeTab === 'categories' && (
            <div className="results-grid">
              {/* Frontend Layer */}
              <div className="results-column frontend-column">
                <h3 className="column-header">
                  <Layout size={18} />
                  Frontend / UI Layer
                </h3>

                <CollapsibleSection
                  title="JSP Files"
                  icon={FileCode}
                  count={searchResults.context.jsp_files.length}
                  defaultOpen={true}
                  variant="frontend"
                >
                  {searchResults.context.jsp_files.map((file, i) => (
                    <FileItem key={i} file={file} />
                  ))}
                </CollapsibleSection>

                <CollapsibleSection
                  title="Frontend Files"
                  icon={Layout}
                  count={searchResults.context.frontend_files.length}
                  defaultOpen={true}
                  variant="frontend"
                >
                  {searchResults.context.frontend_files.map((file, i) => (
                    <FileItem key={i} file={file} />
                  ))}
                </CollapsibleSection>

                <CollapsibleSection
                  title="WebFlow Definitions"
                  icon={Workflow}
                  count={searchResults.context.webflow_definitions.length}
                  defaultOpen={true}
                  variant="frontend"
                >
                  {searchResults.context.webflow_definitions.map((flow, i) => (
                    <WebFlowItem key={i} flow={flow} />
                  ))}
                </CollapsibleSection>
              </div>

              {/* Backend Layer */}
              <div className="results-column backend-column">
                <h3 className="column-header">
                  <Server size={18} />
                  Backend / Service Layer
                </h3>

                <CollapsibleSection
                  title="Controllers"
                  icon={Layers}
                  count={searchResults.context.controllers.length}
                  defaultOpen={true}
                  variant="backend"
                >
                  {searchResults.context.controllers.map((comp, i) => (
                    <ComponentItem key={i} component={comp} />
                  ))}
                </CollapsibleSection>

                <CollapsibleSection
                  title="Services"
                  icon={Code2}
                  count={searchResults.context.services.length}
                  defaultOpen={true}
                  variant="backend"
                >
                  {searchResults.context.services.map((comp, i) => (
                    <ComponentItem key={i} component={comp} />
                  ))}
                </CollapsibleSection>

                <CollapsibleSection
                  title="API Endpoints"
                  icon={Server}
                  count={searchResults.context.api_endpoints.length}
                  defaultOpen={true}
                  variant="backend"
                >
                  {searchResults.context.api_endpoints.map((endpoint, i) => (
                    <APIEndpointItem key={i} endpoint={endpoint} />
                  ))}
                </CollapsibleSection>

                <CollapsibleSection
                  title="Backend Files"
                  icon={FileCode}
                  count={searchResults.context.backend_files.length}
                  variant="backend"
                >
                  {searchResults.context.backend_files.map((file, i) => (
                    <FileItem key={i} file={file} />
                  ))}
                </CollapsibleSection>
              </div>

              {/* Data Layer */}
              <div className="results-column data-column">
                <h3 className="column-header">
                  <Database size={18} />
                  Data Layer
                </h3>

                <CollapsibleSection
                  title="Repositories/DAOs"
                  icon={Database}
                  count={searchResults.context.repositories.length}
                  defaultOpen={true}
                  variant="data"
                >
                  {searchResults.context.repositories.map((comp, i) => (
                    <ComponentItem key={i} component={comp} />
                  ))}
                </CollapsibleSection>

                <CollapsibleSection
                  title="Database Entities"
                  icon={Database}
                  count={searchResults.context.database_entities.length}
                  defaultOpen={true}
                  variant="data"
                >
                  {searchResults.context.database_entities.map((entity, i) => (
                    <DatabaseEntityItem key={i} entity={entity} />
                  ))}
                </CollapsibleSection>

                <CollapsibleSection
                  title="Data Models"
                  icon={Box}
                  count={searchResults.context.data_models.length}
                  defaultOpen={true}
                  variant="data"
                >
                  {searchResults.context.data_models.map((model, i) => (
                    <ComponentItem key={i} component={model} />
                  ))}
                </CollapsibleSection>

                <CollapsibleSection
                  title="Other Components"
                  icon={Box}
                  count={searchResults.context.other_components.length}
                  variant="default"
                >
                  {searchResults.context.other_components.map((comp, i) => (
                    <ComponentItem key={i} component={comp} />
                  ))}
                </CollapsibleSection>
              </div>

              {/* Support Layer */}
              <div className="results-column support-column">
                <h3 className="column-header">
                  <Settings size={18} />
                  Config & Tests
                </h3>

                <CollapsibleSection
                  title="Config Files"
                  icon={Settings}
                  count={searchResults.context.config_files.length}
                  defaultOpen={true}
                  variant="config"
                >
                  {searchResults.context.config_files.map((file, i) => (
                    <FileItem key={i} file={file} />
                  ))}
                </CollapsibleSection>

                <CollapsibleSection
                  title="Test Files"
                  icon={TestTube}
                  count={searchResults.context.test_files.length}
                  defaultOpen={true}
                  variant="test"
                >
                  {searchResults.context.test_files.map((file, i) => (
                    <FileItem key={i} file={file} />
                  ))}
                </CollapsibleSection>
              </div>
            </div>
          )}

          {/* Schema Info */}
          {(searchResults.available_labels.length > 0 || searchResults.available_relationships.length > 0) && (
            <div className="schema-info">
              <h3>Available Graph Schema</h3>
              <div className="schema-grid">
                <div className="schema-section">
                  <h4>Node Labels ({searchResults.available_labels.length})</h4>
                  <div className="schema-tags">
                    {searchResults.available_labels.slice(0, 20).map((label, i) => (
                      <span key={i} className="schema-tag label-tag">{label}</span>
                    ))}
                    {searchResults.available_labels.length > 20 && (
                      <span className="schema-more">+{searchResults.available_labels.length - 20} more</span>
                    )}
                  </div>
                </div>
                <div className="schema-section">
                  <h4>Relationship Types ({searchResults.available_relationships.length})</h4>
                  <div className="schema-tags">
                    {searchResults.available_relationships.slice(0, 20).map((rel, i) => (
                      <span key={i} className="schema-tag rel-tag">{rel}</span>
                    ))}
                    {searchResults.available_relationships.length > 20 && (
                      <span className="schema-more">+{searchResults.available_relationships.length - 20} more</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {!searchResults && !isSearching && !error && (
        <div className="empty-state">
          <Search size={48} />
          <h3>Enter a Feature Description</h3>
          <p>
            Type a feature name or description to see what context is retrieved from the codebase.
            This helps validate that the right files, methods, and components are being found.
          </p>
        </div>
      )}
    </div>
  );
}
