import { useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Plus,
  Minus,
  Edit3,
  MessageSquare,
  FileText,
} from 'lucide-react';
import './SectionDiffViewer.css';

interface SectionDiff {
  before: string;
  after: string;
}

interface SectionDiffViewerProps {
  sectionDiffs: Record<string, SectionDiff>;
  sectionsAdded?: string[];
  sectionsRemoved?: string[];
  sectionsModified?: string[];
  feedbackApplied?: string[];
  viewMode?: 'side-by-side' | 'unified';
}

export function SectionDiffViewer({
  sectionDiffs,
  sectionsAdded = [],
  sectionsRemoved = [],
  sectionsModified = [],
  feedbackApplied = [],
  viewMode: initialViewMode = 'side-by-side',
}: SectionDiffViewerProps) {
  const [viewMode, setViewMode] = useState<'side-by-side' | 'unified'>(initialViewMode);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(Object.keys(sectionDiffs))
  );

  const toggleSection = (sectionName: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(sectionName)) {
      newExpanded.delete(sectionName);
    } else {
      newExpanded.add(sectionName);
    }
    setExpandedSections(newExpanded);
  };

  const expandAll = () => {
    setExpandedSections(new Set(Object.keys(sectionDiffs)));
  };

  const collapseAll = () => {
    setExpandedSections(new Set());
  };

  // Compute line-by-line diff for unified view
  const computeLineDiff = (before: string, after: string): Array<{
    type: 'unchanged' | 'added' | 'removed';
    content: string;
  }> => {
    const beforeLines = before.split('\n');
    const afterLines = after.split('\n');
    const result: Array<{ type: 'unchanged' | 'added' | 'removed'; content: string }> = [];

    // Simple LCS-based diff (not optimal but works for display)
    let i = 0;
    let j = 0;

    while (i < beforeLines.length || j < afterLines.length) {
      if (i >= beforeLines.length) {
        result.push({ type: 'added', content: afterLines[j] });
        j++;
      } else if (j >= afterLines.length) {
        result.push({ type: 'removed', content: beforeLines[i] });
        i++;
      } else if (beforeLines[i] === afterLines[j]) {
        result.push({ type: 'unchanged', content: beforeLines[i] });
        i++;
        j++;
      } else {
        // Look ahead to find matching lines
        let foundMatch = false;
        for (let k = 1; k <= 3 && j + k < afterLines.length; k++) {
          if (beforeLines[i] === afterLines[j + k]) {
            // Lines were added before this
            for (let m = 0; m < k; m++) {
              result.push({ type: 'added', content: afterLines[j + m] });
            }
            j += k;
            foundMatch = true;
            break;
          }
        }

        if (!foundMatch) {
          for (let k = 1; k <= 3 && i + k < beforeLines.length; k++) {
            if (beforeLines[i + k] === afterLines[j]) {
              // Lines were removed before this
              for (let m = 0; m < k; m++) {
                result.push({ type: 'removed', content: beforeLines[i + m] });
              }
              i += k;
              foundMatch = true;
              break;
            }
          }
        }

        if (!foundMatch) {
          // Treat as replacement
          result.push({ type: 'removed', content: beforeLines[i] });
          result.push({ type: 'added', content: afterLines[j] });
          i++;
          j++;
        }
      }
    }

    return result;
  };

  const getSectionStatus = (sectionName: string): 'added' | 'removed' | 'modified' | 'unchanged' => {
    if (sectionsAdded.includes(sectionName)) return 'added';
    if (sectionsRemoved.includes(sectionName)) return 'removed';
    if (sectionsModified.includes(sectionName)) return 'modified';
    return 'unchanged';
  };

  const allSections = [
    ...sectionsAdded,
    ...Object.keys(sectionDiffs),
    ...sectionsRemoved,
  ].filter((section, index, self) => self.indexOf(section) === index);

  return (
    <div className="section-diff-viewer">
      {/* Header with controls */}
      <div className="diff-header">
        <div className="diff-summary">
          {sectionsModified.length > 0 && (
            <span className="summary-item modified">
              <Edit3 size={14} />
              {sectionsModified.length} modified
            </span>
          )}
          {sectionsAdded.length > 0 && (
            <span className="summary-item added">
              <Plus size={14} />
              {sectionsAdded.length} added
            </span>
          )}
          {sectionsRemoved.length > 0 && (
            <span className="summary-item removed">
              <Minus size={14} />
              {sectionsRemoved.length} removed
            </span>
          )}
        </div>

        <div className="diff-controls">
          <div className="view-toggle">
            <button
              className={viewMode === 'side-by-side' ? 'active' : ''}
              onClick={() => setViewMode('side-by-side')}
            >
              Side by Side
            </button>
            <button
              className={viewMode === 'unified' ? 'active' : ''}
              onClick={() => setViewMode('unified')}
            >
              Unified
            </button>
          </div>
          <div className="expand-controls">
            <button onClick={expandAll}>Expand All</button>
            <button onClick={collapseAll}>Collapse All</button>
          </div>
        </div>
      </div>

      {/* Feedback Applied */}
      {feedbackApplied.length > 0 && (
        <div className="feedback-applied">
          <MessageSquare size={16} />
          <div className="feedback-list">
            <span className="feedback-label">Feedback Applied:</span>
            {feedbackApplied.map((feedback, index) => (
              <p key={index} className="feedback-text">"{feedback}"</p>
            ))}
          </div>
        </div>
      )}

      {/* Section Diffs */}
      <div className="diff-sections">
        {allSections.map((sectionName) => {
          const status = getSectionStatus(sectionName);
          const diff = sectionDiffs[sectionName];
          const isExpanded = expandedSections.has(sectionName);

          return (
            <div key={sectionName} className={`diff-section status-${status}`}>
              <div
                className="section-header"
                onClick={() => toggleSection(sectionName)}
              >
                <div className="section-title">
                  <FileText size={16} />
                  <span>{sectionName}</span>
                  <span className={`status-badge ${status}`}>
                    {status === 'added' && <Plus size={12} />}
                    {status === 'removed' && <Minus size={12} />}
                    {status === 'modified' && <Edit3 size={12} />}
                    {status}
                  </span>
                </div>
                {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
              </div>

              {isExpanded && diff && (
                <div className={`section-content ${viewMode}`}>
                  {viewMode === 'side-by-side' ? (
                    <div className="side-by-side-view">
                      <div className="diff-pane before">
                        <div className="pane-header">
                          <Minus size={14} />
                          Before
                        </div>
                        <pre className="diff-content">{diff.before || '(empty)'}</pre>
                      </div>
                      <div className="diff-pane after">
                        <div className="pane-header">
                          <Plus size={14} />
                          After
                        </div>
                        <pre className="diff-content">{diff.after || '(empty)'}</pre>
                      </div>
                    </div>
                  ) : (
                    <div className="unified-view">
                      {computeLineDiff(diff.before || '', diff.after || '').map((line, index) => (
                        <div key={index} className={`diff-line ${line.type}`}>
                          <span className="line-marker">
                            {line.type === 'added' && '+'}
                            {line.type === 'removed' && '-'}
                            {line.type === 'unchanged' && ' '}
                          </span>
                          <span className="line-content">{line.content || ' '}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {isExpanded && !diff && status === 'added' && (
                <div className="section-content">
                  <div className="new-section-notice">
                    <Plus size={16} />
                    This section was newly added
                  </div>
                </div>
              )}

              {isExpanded && !diff && status === 'removed' && (
                <div className="section-content">
                  <div className="removed-section-notice">
                    <Minus size={16} />
                    This section was removed
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {allSections.length === 0 && (
        <div className="no-changes">
          <p>No changes detected between versions.</p>
        </div>
      )}
    </div>
  );
}
