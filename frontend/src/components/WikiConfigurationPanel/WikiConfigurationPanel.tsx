import { useState, useCallback } from 'react';
import {
  Book,
  BookOpen,
  Layers,
  Code2,
  Database,
  Zap,
  FileText,
  Settings,
  Plus,
  Trash2,
  Edit3,
  ChevronRight,
  ChevronDown,
  GripVertical,
  AlertCircle,
  CheckCircle2,
  Info,
  Folder,
  File,
  X,
} from 'lucide-react';
import './WikiConfigurationPanel.css';

// Types
export interface WikiSection {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  enabled: boolean;
  required?: boolean;
  estimatedPages: number;
}

export interface CustomPage {
  id: string;
  title: string;
  purpose: string;
  notes?: string;
  parentId?: string;
  isSection?: boolean;
}

export interface WikiConfiguration {
  mode: 'standard' | 'advanced';
  // Standard mode options
  sections: WikiSection[];
  // Advanced mode options
  contextNotes: string[];
  customPages: CustomPage[];
}

export interface WikiConfigurationPanelProps {
  onConfigurationChange: (config: WikiConfiguration) => void;
  initialConfig?: Partial<WikiConfiguration>;
  repositoryName?: string;
}

// Default sections for Standard mode
const defaultSections: WikiSection[] = [
  {
    id: 'overview',
    name: 'Overview',
    description: 'System overview, stats, quick links',
    icon: <Book size={18} />,
    enabled: true,
    required: true,
    estimatedPages: 1,
  },
  {
    id: 'architecture',
    name: 'Architecture',
    description: 'Component diagrams, layers, design patterns',
    icon: <Layers size={18} />,
    enabled: true,
    required: true,
    estimatedPages: 1,
  },
  {
    id: 'tech-stack',
    name: 'Tech Stack',
    description: 'Languages, frameworks, dependencies',
    icon: <Code2 size={18} />,
    enabled: true,
    required: true,
    estimatedPages: 1,
  },
  {
    id: 'getting-started',
    name: 'Getting Started',
    description: 'Installation & first steps guide',
    icon: <BookOpen size={18} />,
    enabled: true,
    estimatedPages: 2,
  },
  {
    id: 'configuration',
    name: 'Configuration',
    description: 'Environment variables, settings',
    icon: <Settings size={18} />,
    enabled: true,
    estimatedPages: 1,
  },
  {
    id: 'deployment',
    name: 'Deployment',
    description: 'Docker, CI/CD, production setup',
    icon: <Zap size={18} />,
    enabled: false,
    estimatedPages: 2,
  },
  {
    id: 'core-systems',
    name: 'Core Systems',
    description: 'Authentication, Data Layer, API Layer (AI-discovered)',
    icon: <Layers size={18} />,
    enabled: true,
    estimatedPages: 8,
  },
  {
    id: 'features',
    name: 'Business Features',
    description: 'User Management, Payments, etc. (AI-discovered)',
    icon: <Zap size={18} />,
    enabled: true,
    estimatedPages: 6,
  },
  {
    id: 'integrations',
    name: 'Integrations',
    description: 'External APIs, 3rd party services',
    icon: <Database size={18} />,
    enabled: false,
    estimatedPages: 3,
  },
  {
    id: 'api-reference',
    name: 'API Reference',
    description: 'REST/GraphQL endpoints with examples',
    icon: <Code2 size={18} />,
    enabled: false,
    estimatedPages: 5,
  },
  {
    id: 'data-models',
    name: 'Data Models',
    description: 'Entity diagrams, schemas, relations',
    icon: <Database size={18} />,
    enabled: false,
    estimatedPages: 3,
  },
  {
    id: 'code-structure',
    name: 'Code Structure',
    description: 'Per-module/package documentation',
    icon: <Folder size={18} />,
    enabled: false,
    estimatedPages: 10,
  },
  {
    id: 'class-docs',
    name: 'Class Documentation',
    description: 'Individual class/service docs',
    icon: <FileText size={18} />,
    enabled: false,
    estimatedPages: 20,
  },
];

// Section groups for Standard mode
const sectionGroups = [
  {
    id: 'core',
    name: 'Core (Always Included)',
    sectionIds: ['overview', 'architecture', 'tech-stack'],
    required: true,
  },
  {
    id: 'user-guide',
    name: 'User Guide',
    sectionIds: ['getting-started', 'configuration', 'deployment'],
  },
  {
    id: 'concepts',
    name: 'AI-Discovered Concepts',
    sectionIds: ['core-systems', 'features', 'integrations'],
  },
  {
    id: 'technical',
    name: 'Technical Reference',
    sectionIds: ['api-reference', 'data-models', 'code-structure', 'class-docs'],
  },
];

export function WikiConfigurationPanel({
  onConfigurationChange,
  initialConfig,
  repositoryName: _repositoryName,
}: WikiConfigurationPanelProps) {
  const [mode, setMode] = useState<'standard' | 'advanced'>(
    initialConfig?.mode || 'standard'
  );
  const [sections, setSections] = useState<WikiSection[]>(
    initialConfig?.sections || defaultSections
  );
  const [contextNotes, setContextNotes] = useState<string[]>(
    initialConfig?.contextNotes || ['']
  );
  const [customPages, setCustomPages] = useState<CustomPage[]>(
    initialConfig?.customPages || [
      { id: '1', title: 'Overview', purpose: 'System overview and introduction', isSection: false },
      { id: '2', title: 'Architecture', purpose: 'System architecture and design', isSection: false },
    ]
  );
  const [editingPage, setEditingPage] = useState<CustomPage | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    new Set(['core', 'user-guide', 'concepts'])
  );

  // Calculate estimates
  const estimatedPages = mode === 'standard'
    ? sections.filter((s) => s.enabled).reduce((sum, s) => sum + s.estimatedPages, 0)
    : customPages.length;

  const estimatedTime = Math.ceil(estimatedPages / 5); // ~5 pages per minute

  
  // Notify parent of changes
  const notifyChange = useCallback(
    (updates: Partial<WikiConfiguration>) => {
      onConfigurationChange({
        mode,
        sections,
        contextNotes: contextNotes.filter((n) => n.trim()),
        customPages,
        ...updates,
      });
    },
    [mode, sections, contextNotes, customPages, onConfigurationChange]
  );

  // Toggle section
  const toggleSection = (sectionId: string) => {
    const section = sections.find((s) => s.id === sectionId);
    if (section?.required) return;

    const updated = sections.map((s) =>
      s.id === sectionId ? { ...s, enabled: !s.enabled } : s
    );
    setSections(updated);
    notifyChange({ sections: updated });
  };

  // Toggle group expansion
  const toggleGroup = (groupId: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) {
        next.delete(groupId);
      } else {
        next.add(groupId);
      }
      return next;
    });
  };

  // Context notes handlers
  const updateContextNote = (index: number, value: string) => {
    const updated = [...contextNotes];
    updated[index] = value;
    setContextNotes(updated);
    notifyChange({ contextNotes: updated.filter((n) => n.trim()) });
  };

  const addContextNote = () => {
    if (contextNotes.length < 10) {
      setContextNotes([...contextNotes, '']);
    }
  };

  const removeContextNote = (index: number) => {
    const updated = contextNotes.filter((_, i) => i !== index);
    setContextNotes(updated.length ? updated : ['']);
    notifyChange({ contextNotes: updated.filter((n) => n.trim()) });
  };

  // Custom pages handlers
  const addCustomPage = (isSection: boolean = false) => {
    const newPage: CustomPage = {
      id: Date.now().toString(),
      title: isSection ? 'New Section' : 'New Page',
      purpose: '',
      isSection,
    };
    const updated = [...customPages, newPage];
    setCustomPages(updated);
    setEditingPage(newPage);
    notifyChange({ customPages: updated });
  };

  const updateCustomPage = (page: CustomPage) => {
    const updated = customPages.map((p) => (p.id === page.id ? page : p));
    setCustomPages(updated);
    setEditingPage(null);
    notifyChange({ customPages: updated });
  };

  const deleteCustomPage = (pageId: string) => {
    // Also remove children if deleting a section
    const updated = customPages.filter(
      (p) => p.id !== pageId && p.parentId !== pageId
    );
    setCustomPages(updated);
    notifyChange({ customPages: updated });
  };

  // Get sections for a parent
  const getSectionsForParent = () => {
    return customPages.filter((p) => p.isSection);
  };

  // Render page tree
  const renderPageTree = () => {
    const rootPages = customPages.filter((p) => !p.parentId && !p.isSection);
    const sections = customPages.filter((p) => p.isSection);

    return (
      <div className="page-tree">
        {/* Root level pages */}
        {rootPages.map((page) => (
          <div key={page.id} className="page-tree-item">
            <div className="page-tree-row">
              <GripVertical size={14} className="drag-handle" />
              <File size={14} />
              <span className="page-title">{page.title}</span>
              <div className="page-actions">
                <button
                  className="icon-btn"
                  onClick={() => setEditingPage(page)}
                  title="Edit"
                >
                  <Edit3 size={14} />
                </button>
                <button
                  className="icon-btn danger"
                  onClick={() => deleteCustomPage(page.id)}
                  title="Delete"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
            {page.purpose && (
              <div className="page-purpose">{page.purpose}</div>
            )}
          </div>
        ))}

        {/* Sections with children */}
        {sections.map((section) => (
          <div key={section.id} className="page-tree-section">
            <div className="page-tree-row section-row">
              <GripVertical size={14} className="drag-handle" />
              <Folder size={14} />
              <span className="page-title">{section.title}</span>
              <div className="page-actions">
                <button
                  className="icon-btn"
                  onClick={() => {
                    const newPage: CustomPage = {
                      id: Date.now().toString(),
                      title: 'New Page',
                      purpose: '',
                      parentId: section.id,
                    };
                    setCustomPages([...customPages, newPage]);
                    setEditingPage(newPage);
                  }}
                  title="Add child page"
                >
                  <Plus size={14} />
                </button>
                <button
                  className="icon-btn"
                  onClick={() => setEditingPage(section)}
                  title="Edit"
                >
                  <Edit3 size={14} />
                </button>
                <button
                  className="icon-btn danger"
                  onClick={() => deleteCustomPage(section.id)}
                  title="Delete"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
            {section.purpose && (
              <div className="page-purpose">{section.purpose}</div>
            )}
            {/* Children */}
            <div className="page-tree-children">
              {customPages
                .filter((p) => p.parentId === section.id)
                .map((child) => (
                  <div key={child.id} className="page-tree-item child">
                    <div className="page-tree-row">
                      <GripVertical size={14} className="drag-handle" />
                      <File size={14} />
                      <span className="page-title">{child.title}</span>
                      <div className="page-actions">
                        <button
                          className="icon-btn"
                          onClick={() => setEditingPage(child)}
                          title="Edit"
                        >
                          <Edit3 size={14} />
                        </button>
                        <button
                          className="icon-btn danger"
                          onClick={() => deleteCustomPage(child.id)}
                          title="Delete"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                    {child.purpose && (
                      <div className="page-purpose">{child.purpose}</div>
                    )}
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="wiki-config-panel">
      {/* Header with mode toggle */}
      <div className="wiki-config-header">
        <div className="wiki-config-title">
          <Book size={20} />
          <h3>Wiki Documentation</h3>
        </div>
        <div className="mode-toggle">
          <button
            className={`mode-btn ${mode === 'standard' ? 'active' : ''}`}
            onClick={() => {
              setMode('standard');
              notifyChange({ mode: 'standard' });
            }}
          >
            Standard
          </button>
          <button
            className={`mode-btn ${mode === 'advanced' ? 'active' : ''}`}
            onClick={() => {
              setMode('advanced');
              notifyChange({ mode: 'advanced' });
            }}
          >
            Advanced
          </button>
        </div>
      </div>

      {/* Mode description */}
      <div className="mode-description">
        {mode === 'standard' ? (
          <p>
            <Info size={14} />
            Toggle documentation sections on/off. AI will auto-discover concepts from your codebase.
          </p>
        ) : (
          <p>
            <Info size={14} />
            Define exact pages and provide context notes to guide AI generation.
          </p>
        )}
      </div>

      {/* Standard Mode */}
      {mode === 'standard' && (
        <div className="standard-mode">
          {sectionGroups.map((group) => (
            <div key={group.id} className="section-group">
              <div
                className="section-group-header"
                onClick={() => !group.required && toggleGroup(group.id)}
              >
                {!group.required && (
                  <span className="expand-icon">
                    {expandedGroups.has(group.id) ? (
                      <ChevronDown size={16} />
                    ) : (
                      <ChevronRight size={16} />
                    )}
                  </span>
                )}
                <span className="group-name">{group.name}</span>
                {group.required && (
                  <span className="required-badge">Always included</span>
                )}
              </div>
              {(expandedGroups.has(group.id) || group.required) && (
                <div className="section-group-content">
                  {group.sectionIds.map((sectionId) => {
                    const section = sections.find((s) => s.id === sectionId);
                    if (!section) return null;
                    return (
                      <div
                        key={section.id}
                        className={`section-item ${section.enabled ? 'enabled' : ''} ${section.required ? 'required' : ''}`}
                        onClick={() => toggleSection(section.id)}
                      >
                        <div className="section-checkbox">
                          {section.required ? (
                            <CheckCircle2 size={18} className="check-icon locked" />
                          ) : section.enabled ? (
                            <CheckCircle2 size={18} className="check-icon" />
                          ) : (
                            <div className="unchecked" />
                          )}
                        </div>
                        <div className="section-icon">{section.icon}</div>
                        <div className="section-info">
                          <span className="section-name">{section.name}</span>
                          <span className="section-description">
                            {section.description}
                          </span>
                        </div>
                        <div className="section-pages">
                          ~{section.estimatedPages} pages
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}

          {/* Summary */}
          <div className="config-summary">
            <div className="summary-item">
              <FileText size={16} />
              <span>~{estimatedPages} pages</span>
            </div>
            <div className="summary-item">
              <Zap size={16} />
              <span>~{estimatedTime} min</span>
            </div>
            <div className="summary-item">
              <CheckCircle2 size={16} />
              <span>AI-Powered</span>
            </div>
          </div>
        </div>
      )}

      {/* Advanced Mode */}
      {mode === 'advanced' && (
        <div className="advanced-mode">
          {/* Context Notes */}
          <div className="context-notes-section">
            <div className="section-header">
              <h4>Context Notes</h4>
              <span className="helper-text">
                Guide AI generation with project-specific context
              </span>
            </div>
            <div className="context-notes">
              {contextNotes.map((note, index) => (
                <div key={index} className="context-note">
                  <textarea
                    value={note}
                    onChange={(e) => updateContextNote(index, e.target.value)}
                    placeholder={
                      index === 0
                        ? `Example: "This is a Spring Boot microservices e-commerce platform. Focus on the payment and order modules. The auth service uses OAuth2 with Keycloak. Ignore the legacy-adapter module."`
                        : 'Add additional context...'
                    }
                    maxLength={10000}
                  />
                  <div className="note-footer">
                    <span className="char-count">
                      {note.length}/10,000
                    </span>
                    {contextNotes.length > 1 && (
                      <button
                        className="remove-note-btn"
                        onClick={() => removeContextNote(index)}
                      >
                        <X size={14} />
                        Remove
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {contextNotes.length < 10 && (
                <button className="add-note-btn" onClick={addContextNote}>
                  <Plus size={14} />
                  Add another note
                </button>
              )}
            </div>
          </div>

          {/* Custom Pages */}
          <div className="custom-pages-section">
            <div className="section-header">
              <h4>Custom Page Structure</h4>
              <span className="helper-text">
                Define exactly which pages to generate
              </span>
            </div>

            {renderPageTree()}

            <div className="add-page-actions">
              <button
                className="add-page-btn"
                onClick={() => addCustomPage(false)}
              >
                <Plus size={14} />
                Add Page
              </button>
              <button
                className="add-section-btn"
                onClick={() => addCustomPage(true)}
              >
                <Folder size={14} />
                Add Section
              </button>
            </div>

            {/* Limits */}
            <div className="limits-info">
              <span className={customPages.length > 30 ? 'warning' : ''}>
                <FileText size={14} />
                {customPages.length}/30 pages
              </span>
              <span>
                <AlertCircle size={14} />
                {contextNotes.filter((n) => n.trim()).length}/10 notes
              </span>
              {customPages.length <= 30 && (
                <span className="valid">
                  <CheckCircle2 size={14} />
                  Valid structure
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Page Editor Modal */}
      {editingPage && (
        <div className="page-editor-overlay" onClick={() => setEditingPage(null)}>
          <div className="page-editor" onClick={(e) => e.stopPropagation()}>
            <div className="page-editor-header">
              <h4>{editingPage.isSection ? 'Edit Section' : 'Edit Page'}</h4>
              <button
                className="close-btn"
                onClick={() => setEditingPage(null)}
              >
                <X size={18} />
              </button>
            </div>
            <div className="page-editor-content">
              <div className="form-group">
                <label>Title</label>
                <input
                  type="text"
                  value={editingPage.title}
                  onChange={(e) =>
                    setEditingPage({ ...editingPage, title: e.target.value })
                  }
                  placeholder="Page title"
                />
              </div>
              {!editingPage.isSection && (
                <div className="form-group">
                  <label>Parent Section (optional)</label>
                  <select
                    value={editingPage.parentId || ''}
                    onChange={(e) =>
                      setEditingPage({
                        ...editingPage,
                        parentId: e.target.value || undefined,
                      })
                    }
                  >
                    <option value="">No parent (root level)</option>
                    {getSectionsForParent().map((section) => (
                      <option key={section.id} value={section.id}>
                        {section.title}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <div className="form-group">
                <label>Purpose</label>
                <textarea
                  value={editingPage.purpose}
                  onChange={(e) =>
                    setEditingPage({ ...editingPage, purpose: e.target.value })
                  }
                  placeholder="Describe what this page should document..."
                  rows={3}
                />
              </div>
              <div className="form-group">
                <label>Notes (optional)</label>
                <textarea
                  value={editingPage.notes || ''}
                  onChange={(e) =>
                    setEditingPage({ ...editingPage, notes: e.target.value })
                  }
                  placeholder="Additional instructions for AI (e.g., 'Include sequence diagrams')"
                  rows={2}
                />
              </div>
            </div>
            <div className="page-editor-footer">
              <button
                className="btn btn-outline"
                onClick={() => setEditingPage(null)}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={() => updateCustomPage(editingPage)}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default WikiConfigurationPanel;
