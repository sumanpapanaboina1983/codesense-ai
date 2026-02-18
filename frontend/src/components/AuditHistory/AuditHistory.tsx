import { useState, useEffect } from 'react';
import {
  History,
  ChevronDown,
  ChevronUp,
  X,
  FileText,
  Layers,
  CheckSquare,
  RefreshCw,
  Clock,
  MessageSquare,
  Eye,
} from 'lucide-react';
import {
  getArtifactHistory,
  getSessionHistory,
  getVersionDiff,
  type ArtifactHistoryEntry,
  type SessionHistoryResponse,
  type VersionDiffResponse,
} from '../../services/api';
import { SectionDiffViewer } from '../SectionDiffViewer/SectionDiffViewer';
import './AuditHistory.css';

interface AuditHistoryProps {
  artifactType: 'brd' | 'epic' | 'backlog';
  artifactId: string;
  sessionId?: string;
  onRestore?: (version: number) => void;
  onClose?: () => void;
}

type ViewMode = 'artifact' | 'session';
type FilterType = 'all' | 'created' | 'refined';

export function AuditHistory({
  artifactType,
  artifactId,
  sessionId,
  onRestore,
  onClose,
}: AuditHistoryProps) {
  const [viewMode, setViewMode] = useState<ViewMode>(sessionId ? 'session' : 'artifact');
  const [history, setHistory] = useState<ArtifactHistoryEntry[]>([]);
  const [sessionData, setSessionData] = useState<SessionHistoryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedEntries, setExpandedEntries] = useState<Set<string>>(new Set());
  const [filterType, setFilterType] = useState<FilterType>('all');

  // Diff viewer state
  const [showDiff, setShowDiff] = useState(false);
  const [diffData, setDiffData] = useState<VersionDiffResponse | null>(null);
  const [comparingVersions, setComparingVersions] = useState<{ v1: number; v2: number } | null>(null);

  useEffect(() => {
    loadHistory();
  }, [artifactType, artifactId, sessionId, viewMode]);

  const loadHistory = async () => {
    setIsLoading(true);
    setError(null);

    try {
      if (viewMode === 'session' && sessionId) {
        const data = await getSessionHistory(sessionId);
        setSessionData(data);
        setHistory(data.history);
      } else {
        const data = await getArtifactHistory(artifactType, artifactId);
        setHistory(data.history);
        setSessionData(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load history');
    } finally {
      setIsLoading(false);
    }
  };

  const toggleEntry = (id: string) => {
    const newExpanded = new Set(expandedEntries);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedEntries(newExpanded);
  };

  const handleViewDiff = async (version1: number, version2: number) => {
    setComparingVersions({ v1: version1, v2: version2 });
    try {
      const diff = await getVersionDiff(artifactType, artifactId, version1, version2);
      setDiffData(diff);
      setShowDiff(true);
    } catch (err) {
      console.error('Failed to load diff:', err);
    }
  };

  const filteredHistory = history.filter((entry) => {
    if (filterType === 'all') return true;
    return entry.action === filterType;
  });

  const getArtifactIcon = (type: string) => {
    switch (type) {
      case 'brd':
        return <FileText size={14} />;
      case 'epic':
        return <Layers size={14} />;
      case 'backlog':
        return <CheckSquare size={14} />;
      default:
        return <FileText size={14} />;
    }
  };

  const getActionLabel = (action: string) => {
    switch (action) {
      case 'created':
        return 'Created';
      case 'refined':
        return 'Refined';
      case 'deleted':
        return 'Deleted';
      default:
        return action;
    }
  };

  if (showDiff && diffData) {
    return (
      <div className="audit-history-container">
        <div className="history-header">
          <button className="back-btn" onClick={() => setShowDiff(false)}>
            <ChevronDown size={16} className="rotate-90" />
            Back to History
          </button>
          <span>
            Comparing v{comparingVersions?.v1} to v{comparingVersions?.v2}
          </span>
          {onClose && (
            <button className="close-btn" onClick={onClose}>
              <X size={18} />
            </button>
          )}
        </div>
        <div className="diff-content">
          <SectionDiffViewer
            sectionDiffs={diffData.section_diffs}
            sectionsAdded={diffData.sections_added}
            sectionsRemoved={diffData.sections_removed}
            sectionsModified={diffData.sections_modified}
            feedbackApplied={diffData.feedback_applied}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="audit-history-container">
      {/* Header */}
      <div className="history-header">
        <History size={20} />
        <span>
          {viewMode === 'session' ? 'Session History' : 'Artifact History'}
        </span>
        {onClose && (
          <button className="close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        )}
      </div>

      {/* View Mode Toggle */}
      {sessionId && (
        <div className="view-mode-toggle">
          <button
            className={viewMode === 'artifact' ? 'active' : ''}
            onClick={() => setViewMode('artifact')}
          >
            {getArtifactIcon(artifactType)}
            This {artifactType.toUpperCase()}
          </button>
          <button
            className={viewMode === 'session' ? 'active' : ''}
            onClick={() => setViewMode('session')}
          >
            <Layers size={14} />
            Full Pipeline
          </button>
        </div>
      )}

      {/* Session Summary */}
      {viewMode === 'session' && sessionData && (
        <div className="session-summary">
          <div className="summary-row">
            <span className="label">Feature:</span>
            <span className="value">{sessionData.feature_description.slice(0, 100)}...</span>
          </div>
          <div className="summary-stats">
            <div className="stat">
              <span className="stat-value">{sessionData.total_refinements}</span>
              <span className="stat-label">Total Refinements</span>
            </div>
            <div className="stat">
              <span className="stat-value">{sessionData.brd_refinements}</span>
              <span className="stat-label">BRD</span>
            </div>
            <div className="stat">
              <span className="stat-value">{sessionData.epic_refinements}</span>
              <span className="stat-label">EPICs</span>
            </div>
            <div className="stat">
              <span className="stat-value">{sessionData.backlog_refinements}</span>
              <span className="stat-label">Backlogs</span>
            </div>
          </div>
          <div className="linked-artifacts">
            <span className="artifact-count">
              1 BRD / {sessionData.epic_ids.length} EPICs / {sessionData.backlog_ids.length} Backlogs
            </span>
          </div>
        </div>
      )}

      {/* Filter */}
      <div className="history-filter">
        <button
          className={filterType === 'all' ? 'active' : ''}
          onClick={() => setFilterType('all')}
        >
          All
        </button>
        <button
          className={filterType === 'created' ? 'active' : ''}
          onClick={() => setFilterType('created')}
        >
          Created
        </button>
        <button
          className={filterType === 'refined' ? 'active' : ''}
          onClick={() => setFilterType('refined')}
        >
          Refined
        </button>
        <button className="refresh-btn" onClick={loadHistory} disabled={isLoading}>
          <RefreshCw size={14} className={isLoading ? 'spin' : ''} />
        </button>
      </div>

      {/* History Content */}
      <div className="history-content">
        {isLoading ? (
          <div className="history-loading">
            <RefreshCw size={24} className="spin" />
            <span>Loading history...</span>
          </div>
        ) : error ? (
          <div className="history-error">
            <span>{error}</span>
            <button onClick={loadHistory}>Retry</button>
          </div>
        ) : filteredHistory.length === 0 ? (
          <div className="history-empty">
            <p>No history entries found.</p>
            {filterType !== 'all' && (
              <button onClick={() => setFilterType('all')}>Show All</button>
            )}
          </div>
        ) : (
          <div className="history-timeline">
            {filteredHistory.map((entry, index) => {
              const isExpanded = expandedEntries.has(entry.id);
              const prevVersion = index > 0 ? filteredHistory[index - 1].version : null;

              return (
                <div
                  key={entry.id}
                  className={`history-entry ${entry.action} ${isExpanded ? 'expanded' : ''}`}
                >
                  <div className="entry-marker">
                    <div className="marker-dot" />
                    {index < filteredHistory.length - 1 && <div className="marker-line" />}
                  </div>

                  <div className="entry-content">
                    <div
                      className="entry-header"
                      onClick={() => toggleEntry(entry.id)}
                    >
                      <div className="entry-main">
                        <span className="entry-version">v{entry.version}</span>
                        {viewMode === 'session' && (
                          <span className="entry-artifact-type">
                            {getArtifactIcon(entry.artifact_type)}
                            {entry.artifact_type.toUpperCase()}
                          </span>
                        )}
                        <span className={`entry-action action-${entry.action}`}>
                          {getActionLabel(entry.action)}
                        </span>
                        {entry.feedback_scope === 'section' && entry.feedback_target && (
                          <span className="entry-target">: {entry.feedback_target}</span>
                        )}
                      </div>
                      <div className="entry-meta">
                        <Clock size={12} />
                        <span>{new Date(entry.created_at).toLocaleString()}</span>
                        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="entry-details">
                        {entry.user_feedback && (
                          <div className="detail-section feedback">
                            <MessageSquare size={14} />
                            <div>
                              <span className="detail-label">Feedback:</span>
                              <p>{entry.user_feedback}</p>
                            </div>
                          </div>
                        )}

                        {entry.changes_summary && (
                          <div className="detail-section summary">
                            <span className="detail-label">Changes:</span>
                            <p>{entry.changes_summary}</p>
                          </div>
                        )}

                        {entry.sections_changed && entry.sections_changed.length > 0 && (
                          <div className="detail-section sections">
                            <span className="detail-label">Sections Modified:</span>
                            <div className="section-tags">
                              {entry.sections_changed.map((section, i) => (
                                <span key={i} className="section-tag">{section}</span>
                              ))}
                            </div>
                          </div>
                        )}

                        <div className="entry-actions">
                          {prevVersion && entry.action === 'refined' && (
                            <button
                              className="btn-view-diff"
                              onClick={() => handleViewDiff(prevVersion, entry.version)}
                            >
                              <Eye size={14} />
                              View Diff
                            </button>
                          )}
                          {onRestore && (
                            <button
                              className="btn-restore"
                              onClick={() => onRestore(entry.version)}
                            >
                              <RefreshCw size={14} />
                              Restore
                            </button>
                          )}
                        </div>

                        <div className="entry-metadata">
                          {entry.model_used && (
                            <span className="meta-item">Model: {entry.model_used}</span>
                          )}
                          {entry.generation_mode && (
                            <span className="meta-item">Mode: {entry.generation_mode}</span>
                          )}
                          {entry.confidence_score !== undefined && (
                            <span className="meta-item">
                              Confidence: {(entry.confidence_score * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
