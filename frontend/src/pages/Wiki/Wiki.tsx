import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Book,
  ChevronRight,
  ChevronDown,
  Search,
  RefreshCw,
  FileText,
  Layers,
  Code2,
  Database,
  Layout,
  Zap,
  AlertTriangle,
  ExternalLink,
  MessageSquare,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import mermaid from 'mermaid';
import { getWikiTree, getWikiPage, searchWiki, generateWiki } from '../../services/api';
import { LoadingSpinner } from '../../components/LoadingSpinner';
import { WikiConfigurationPanel } from '../../components/WikiConfigurationPanel';
import type { WikiConfiguration } from '../../components/WikiConfigurationPanel';
import type { WikiGenerationOptions } from '../../api/client';
import './Wiki.css';

// Initialize mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  securityLevel: 'loose',
});

// Types
interface WikiTreeNode {
  slug: string;
  title: string;
  type: string;
  is_stale: boolean;
  children: WikiTreeNode[];
}

interface WikiStatus {
  status: string;
  total_pages: number;
  stale_pages: number;
  commit_sha: string | null;
  generation_mode: string | null;
  generated_at: string | null;
}

interface WikiPage {
  id: string;
  slug: string;
  title: string;
  type: string;
  content: string;
  summary: string | null;
  source_files: string[] | null;
  is_stale: boolean;
  stale_reason: string | null;
  updated_at: string;
  breadcrumbs: { slug: string; title: string }[];
  related: { slug: string; title: string }[];
}

interface SearchResult {
  slug: string;
  title: string;
  type: string;
  summary: string;
}

// Page type icons
const pageTypeIcons: Record<string, React.ReactNode> = {
  overview: <Book size={16} />,
  architecture: <Layers size={16} />,
  module: <Layout size={16} />,
  class: <Code2 size={16} />,
  api: <Zap size={16} />,
  data_model: <Database size={16} />,
  getting_started: <FileText size={16} />,
};

// Mermaid component
function MermaidDiagram({ chart }: { chart: string }) {
  const [svg, setSvg] = useState<string>('');

  useEffect(() => {
    const renderDiagram = async () => {
      try {
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
        const { svg } = await mermaid.render(id, chart);
        setSvg(svg);
      } catch (error) {
        console.error('Mermaid rendering error:', error);
        setSvg(`<pre class="mermaid-error">${chart}</pre>`);
      }
    };
    renderDiagram();
  }, [chart]);

  return <div className="mermaid-diagram" dangerouslySetInnerHTML={{ __html: svg }} />;
}

// Search Modal Component
function SearchModal({
  isOpen,
  onClose,
  repositoryId,
  onSelect,
}: {
  isOpen: boolean;
  onClose: () => void;
  repositoryId: string;
  onSelect: (slug: string) => void;
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  useEffect(() => {
    if (!isOpen) {
      setQuery('');
      setResults([]);
      setSelectedIndex(0);
    }
  }, [isOpen]);

  useEffect(() => {
    const search = async () => {
      if (query.length < 2) {
        setResults([]);
        return;
      }
      setLoading(true);
      try {
        const response = await searchWiki(repositoryId, query);
        setResults(response.results);
        setSelectedIndex(0);
      } catch (error) {
        console.error('Search error:', error);
      } finally {
        setLoading(false);
      }
    };

    const debounce = setTimeout(search, 300);
    return () => clearTimeout(debounce);
  }, [query, repositoryId]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === 'Escape') {
        onClose();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, results.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === 'Enter' && results[selectedIndex]) {
        onSelect(results[selectedIndex].slug);
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, results, selectedIndex, onSelect, onClose]);

  if (!isOpen) return null;

  return (
    <div className="search-modal-overlay" onClick={onClose}>
      <div className="search-modal" onClick={(e) => e.stopPropagation()}>
        <div className="search-input-container">
          <Search size={20} />
          <input
            type="text"
            placeholder="Search wiki..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <span className="search-shortcut">ESC</span>
        </div>

        {loading && (
          <div className="search-loading">
            <RefreshCw size={16} className="spin" />
            Searching...
          </div>
        )}

        {results.length > 0 && (
          <div className="search-results">
            {results.map((result, index) => (
              <div
                key={result.slug}
                className={`search-result-item ${index === selectedIndex ? 'selected' : ''}`}
                onClick={() => {
                  onSelect(result.slug);
                  onClose();
                }}
              >
                <div className="result-icon">{pageTypeIcons[result.type] || <FileText size={16} />}</div>
                <div className="result-content">
                  <div className="result-title">{result.title}</div>
                  <div className="result-summary">{result.summary}</div>
                </div>
                <div className="result-type">{result.type}</div>
              </div>
            ))}
          </div>
        )}

        {query.length >= 2 && results.length === 0 && !loading && (
          <div className="search-empty">No results found for "{query}"</div>
        )}

        <div className="search-footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> Navigate</span>
          <span><kbd>↵</kbd> Open</span>
          <span><kbd>ESC</kbd> Close</span>
        </div>
      </div>
    </div>
  );
}

// Sidebar Tree Node Component
function TreeNode({
  node,
  currentSlug,
  onSelect,
  level = 0,
}: {
  node: WikiTreeNode;
  currentSlug: string;
  onSelect: (slug: string) => void;
  level?: number;
}) {
  const [isExpanded, setIsExpanded] = useState(level === 0 || currentSlug.startsWith(node.slug));
  const hasChildren = node.children && node.children.length > 0;
  const isActive = currentSlug === node.slug;

  return (
    <div className="tree-node">
      <div
        className={`tree-node-header ${isActive ? 'active' : ''} ${node.is_stale ? 'stale' : ''}`}
        style={{ paddingLeft: `${12 + level * 16}px` }}
        onClick={() => {
          if (hasChildren) {
            setIsExpanded(!isExpanded);
          }
          onSelect(node.slug);
        }}
      >
        {hasChildren ? (
          <span className="tree-expand-icon">
            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        ) : (
          <span className="tree-expand-icon">{pageTypeIcons[node.type] || <FileText size={14} />}</span>
        )}
        <span className="tree-node-title">{node.title}</span>
        {node.is_stale && <AlertTriangle size={12} className="stale-icon" />}
      </div>
      {hasChildren && isExpanded && (
        <div className="tree-children">
          {node.children.map((child) => (
            <TreeNode
              key={child.slug}
              node={child}
              currentSlug={currentSlug}
              onSelect={onSelect}
              level={level + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Main Wiki Component
export function Wiki() {
  const { id: repositoryId, '*': pageSlug } = useParams<{ id: string; '*': string }>();
  const navigate = useNavigate();
  const currentSlug = pageSlug || 'overview';

  const [wikiStatus, setWikiStatus] = useState<WikiStatus | null>(null);
  const [tree, setTree] = useState<WikiTreeNode[]>([]);
  const [page, setPage] = useState<WikiPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [pageLoading, setPageLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [wikiConfig, setWikiConfig] = useState<WikiConfiguration | null>(null);
  const [sidebarCollapsed, _setSidebarCollapsed] = useState(false);

  // Keyboard shortcut for search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Fetch wiki tree
  const fetchTree = useCallback(async () => {
    if (!repositoryId) return;
    try {
      const data = await getWikiTree(repositoryId);
      setWikiStatus(data.wiki);
      setTree(data.tree);
    } catch (err) {
      console.error('Failed to fetch wiki tree:', err);
      setError('Failed to load wiki navigation');
    } finally {
      setLoading(false);
    }
  }, [repositoryId]);

  // Fetch page content
  const fetchPage = useCallback(async () => {
    if (!repositoryId || !currentSlug) return;
    setPageLoading(true);
    try {
      const data = await getWikiPage(repositoryId, currentSlug);
      setPage(data);
      setError(null);
    } catch (err: any) {
      console.error('Failed to fetch wiki page:', err);
      if (err.response?.status === 404) {
        setPage(null);
        setError(`Page not found: ${currentSlug}`);
      } else {
        setError('Failed to load page');
      }
    } finally {
      setPageLoading(false);
    }
  }, [repositoryId, currentSlug]);

  useEffect(() => {
    fetchTree();
  }, [fetchTree]);

  useEffect(() => {
    if (wikiStatus?.status === 'generated') {
      fetchPage();
    }
  }, [fetchPage, wikiStatus?.status]);

  // Handle page navigation
  const handlePageSelect = (slug: string) => {
    navigate(`/repositories/${repositoryId}/wiki/${slug}`);
  };

  // Handle wiki config change
  const handleWikiConfigChange = useCallback((config: WikiConfiguration) => {
    setWikiConfig(config);
  }, []);

  // Convert WikiConfiguration to API format
  const convertWikiConfigToApiFormat = (config: WikiConfiguration | null): WikiGenerationOptions => {
    if (!config) {
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

  // Handle wiki generation
  const handleGenerate = async () => {
    if (!repositoryId) return;
    setGenerating(true);
    try {
      const wikiOptions = convertWikiConfigToApiFormat(wikiConfig);
      await generateWiki(repositoryId, wikiOptions);
      // Refresh after generation
      await fetchTree();
    } catch (err) {
      console.error('Failed to generate wiki:', err);
      setError('Failed to generate wiki');
    } finally {
      setGenerating(false);
    }
  };

  if (loading) {
    return <LoadingSpinner message="Loading wiki..." />;
  }

  // Not generated state - show configuration panel
  if (!wikiStatus || wikiStatus.status === 'not_generated') {
    return (
      <div className="wiki-not-generated">
        <div className="wiki-not-generated-content wide">
          <div className="wiki-config-header-section">
            <Book size={48} />
            <div>
              <h2>Generate Wiki Documentation</h2>
              <p>Configure and generate comprehensive documentation for this repository.</p>
            </div>
          </div>

          <WikiConfigurationPanel
            onConfigurationChange={handleWikiConfigChange}
            repositoryName={repositoryId || ''}
          />

          <div className="wiki-generate-actions">
            <Link to={`/repositories/${repositoryId}`} className="btn btn-outline">
              <ArrowLeft size={16} />
              Back to Repository
            </Link>
            <button
              className="btn btn-primary btn-large"
              onClick={handleGenerate}
              disabled={generating}
            >
              {generating ? (
                <>
                  <RefreshCw size={20} className="spin" />
                  Generating Wiki...
                </>
              ) : (
                <>
                  <Zap size={20} />
                  Generate Wiki
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Generating state
  if (wikiStatus.status === 'generating') {
    return (
      <div className="wiki-generating">
        <RefreshCw size={48} className="spin" />
        <h2>Generating Wiki...</h2>
        <p>This may take a few minutes for large codebases.</p>
        <div className="generating-progress">
          <div className="progress-bar">
            <div className="progress-fill indeterminate" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`wiki-layout ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      {/* Sidebar */}
      <aside className="wiki-sidebar">
        <div className="wiki-sidebar-header">
          <Link to={`/repositories/${repositoryId}`} className="wiki-back-btn">
            <ArrowLeft size={16} />
          </Link>
          <h3>Wiki</h3>
          <button
            className="wiki-search-btn"
            onClick={() => setSearchOpen(true)}
            title="Search (⌘K)"
          >
            <Search size={16} />
          </button>
        </div>

        <div className="wiki-sidebar-search" onClick={() => setSearchOpen(true)}>
          <Search size={14} />
          <span>Search...</span>
          <kbd>⌘K</kbd>
        </div>

        <nav className="wiki-nav">
          {tree.map((node) => (
            <TreeNode
              key={node.slug}
              node={node}
              currentSlug={currentSlug}
              onSelect={handlePageSelect}
            />
          ))}
        </nav>

        <div className="wiki-sidebar-footer">
          <div className="wiki-stats">
            <span>{wikiStatus.total_pages} pages</span>
            {wikiStatus.stale_pages > 0 && (
              <span className="stale-count">{wikiStatus.stale_pages} stale</span>
            )}
          </div>
          {wikiStatus.generation_mode && (
            <div className={`wiki-generation-mode ${wikiStatus.generation_mode === 'llm-powered' ? 'llm' : 'template'}`}>
              {wikiStatus.generation_mode === 'llm-powered' ? (
                <>
                  <Zap size={12} />
                  <span>AI-Powered</span>
                </>
              ) : (
                <>
                  <FileText size={12} />
                  <span>Template</span>
                </>
              )}
            </div>
          )}
          {wikiStatus.commit_sha && (
            <div className="wiki-commit">
              Commit: {wikiStatus.commit_sha.slice(0, 7)}
            </div>
          )}
          <button className="btn btn-outline btn-small" onClick={handleGenerate} disabled={generating}>
            <RefreshCw size={14} className={generating ? 'spin' : ''} />
            Regenerate
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="wiki-content">
        {pageLoading ? (
          <div className="wiki-page-loading">
            <RefreshCw size={24} className="spin" />
            <span>Loading page...</span>
          </div>
        ) : error ? (
          <div className="wiki-error">
            <AlertTriangle size={48} />
            <h3>Error</h3>
            <p>{error}</p>
            <button className="btn btn-primary" onClick={fetchPage}>
              Try Again
            </button>
          </div>
        ) : page ? (
          <article className="wiki-page">
            {/* Source files header */}
            {page.source_files && page.source_files.length > 0 && (
              <div className="wiki-sources">
                <details>
                  <summary>
                    <FileText size={14} />
                    Sources ({page.source_files.length} files)
                  </summary>
                  <ul>
                    {page.source_files.map((file, i) => (
                      <li key={i}>
                        <code>{file}</code>
                      </li>
                    ))}
                  </ul>
                </details>
              </div>
            )}

            {/* Stale warning */}
            {page.is_stale && (
              <div className="wiki-stale-warning">
                <AlertTriangle size={16} />
                <span>This page may be outdated. {page.stale_reason}</span>
                <button className="btn btn-small">Regenerate</button>
              </div>
            )}

            {/* Breadcrumbs */}
            {page.breadcrumbs.length > 1 && (
              <nav className="wiki-breadcrumbs">
                {page.breadcrumbs.map((crumb, i) => (
                  <span key={crumb.slug}>
                    {i > 0 && <ChevronRight size={14} />}
                    <a onClick={() => handlePageSelect(crumb.slug)}>{crumb.title}</a>
                  </span>
                ))}
              </nav>
            )}

            {/* Page content */}
            <div className="wiki-page-content">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ node, inline, className, children, ...props }: any) {
                    const match = /language-(\w+)/.exec(className || '');
                    const language = match ? match[1] : '';

                    // Handle mermaid diagrams
                    if (language === 'mermaid') {
                      return <MermaidDiagram chart={String(children).replace(/\n$/, '')} />;
                    }

                    // Inline code
                    if (inline) {
                      return (
                        <code className="inline-code" {...props}>
                          {children}
                        </code>
                      );
                    }

                    // Code blocks with syntax highlighting
                    return (
                      <SyntaxHighlighter
                        style={oneDark}
                        language={language || 'text'}
                        PreTag="div"
                        {...props}
                      >
                        {String(children).replace(/\n$/, '')}
                      </SyntaxHighlighter>
                    );
                  },
                  table({ children }) {
                    return (
                      <div className="table-wrapper">
                        <table>{children}</table>
                      </div>
                    );
                  },
                  a({ href, children }) {
                    // Internal wiki links
                    if (href?.startsWith('./') || href?.startsWith('../')) {
                      const slug = href.replace(/^\.\//, '').replace(/^\.\.\//, '');
                      return (
                        <a className="wiki-link" onClick={() => handlePageSelect(slug)}>
                          {children}
                        </a>
                      );
                    }
                    // External links
                    return (
                      <a href={href} target="_blank" rel="noopener noreferrer">
                        {children}
                        <ExternalLink size={12} className="external-icon" />
                      </a>
                    );
                  },
                }}
              >
                {page.content}
              </ReactMarkdown>
            </div>

            {/* Related pages */}
            {page.related.length > 0 && (
              <div className="wiki-related">
                <h4>Related Pages</h4>
                <div className="related-links">
                  {page.related.map((rel) => (
                    <a key={rel.slug} onClick={() => handlePageSelect(rel.slug)}>
                      <FileText size={14} />
                      {rel.title}
                    </a>
                  ))}
                </div>
              </div>
            )}

            {/* Page footer */}
            <footer className="wiki-page-footer">
              <span>Last updated: {new Date(page.updated_at).toLocaleDateString()}</span>
              <Link to={`/repositories/${repositoryId}/chat`} className="ask-link">
                <MessageSquare size={14} />
                Ask about this page
              </Link>
            </footer>
          </article>
        ) : (
          <div className="wiki-empty">
            <Book size={48} />
            <p>Select a page from the sidebar</p>
          </div>
        )}
      </main>

      {/* Search Modal */}
      <SearchModal
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        repositoryId={repositoryId || ''}
        onSelect={handlePageSelect}
      />
    </div>
  );
}

export default Wiki;
