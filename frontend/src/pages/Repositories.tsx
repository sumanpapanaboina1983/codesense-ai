import { useEffect, useState, useRef, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Plus,
  RefreshCw,
  Play,
  Trash2,
  GitBranch,
  BarChart2,
  Upload,
  Link as LinkIcon,
  FileArchive,
  X,
  Search,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import {
  getRepositories,
  createRepository,
  deleteRepository,
  syncRepository,
  analyzeRepository,
  uploadRepositoryZip,
} from '../api/client';
import type { Repository } from '../types';
import { Modal } from '../components/Modal';
import { StatusBadge } from '../components/StatusBadge';
import { LoadingSpinner } from '../components/LoadingSpinner';
import './Repositories.css';

type AddMode = 'url' | 'upload';
type StatusFilter = 'all' | 'completed' | 'in_progress' | 'not_started' | 'failed';

const ITEMS_PER_PAGE = 10;

export function Repositories() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [addMode, setAddMode] = useState<AddMode>('url');
  const [newRepoUrl, setNewRepoUrl] = useState('');
  const [newRepoToken, setNewRepoToken] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Filter and pagination state
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [currentPage, setCurrentPage] = useState(1);

  // Upload mode state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState('');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [autoAnalyze, setAutoAnalyze] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Filtered and paginated repositories
  const filteredRepositories = useMemo(() => {
    let filtered = [...repositories];

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter((repo) =>
        repo.name.toLowerCase().includes(query)
      );
    }

    // Apply status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter((repo) => repo.analysis_status === statusFilter);
    }

    return filtered;
  }, [repositories, searchQuery, statusFilter]);

  const totalPages = Math.ceil(filteredRepositories.length / ITEMS_PER_PAGE);
  const paginatedRepositories = useMemo(() => {
    const start = (currentPage - 1) * ITEMS_PER_PAGE;
    return filteredRepositories.slice(start, start + ITEMS_PER_PAGE);
  }, [filteredRepositories, currentPage]);

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, statusFilter]);

  const fetchRepositories = async () => {
    try {
      const repos = await getRepositories();
      setRepositories(repos);
    } catch (error) {
      console.error('Failed to fetch repositories:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRepositories();
    const interval = setInterval(fetchRepositories, 10000);
    return () => clearInterval(interval);
  }, []);

  const resetModalState = () => {
    setNewRepoUrl('');
    setNewRepoToken('');
    setSelectedFile(null);
    setUploadName('');
    setUploadProgress(0);
    setAutoAnalyze(true);
    setAddMode('url');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleCloseModal = () => {
    setShowAddModal(false);
    resetModalState();
  };

  const handleAddRepository = async () => {
    if (!newRepoUrl) return;

    setSubmitting(true);
    try {
      await createRepository({
        url: newRepoUrl,
        personal_access_token: newRepoToken || undefined,
        auto_analyze_on_sync: true,
      });
      handleCloseModal();
      fetchRepositories();
    } catch (error) {
      console.error('Failed to add repository:', error);
      alert('Failed to add repository. Please check the URL and try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleUploadRepository = async () => {
    if (!selectedFile) return;

    setSubmitting(true);
    setUploadProgress(0);
    try {
      await uploadRepositoryZip(
        selectedFile,
        uploadName || undefined,
        autoAnalyze,
        (progress) => setUploadProgress(progress)
      );
      handleCloseModal();
      fetchRepositories();
    } catch (error: any) {
      console.error('Failed to upload repository:', error);
      const message = error.response?.data?.detail || 'Failed to upload repository. Please try again.';
      alert(message);
    } finally {
      setSubmitting(false);
      setUploadProgress(0);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith('.zip')) {
        alert('Please select a ZIP file');
        return;
      }
      setSelectedFile(file);
      // Set default name from filename (without .zip extension)
      if (!uploadName) {
        setUploadName(file.name.replace(/\.zip$/i, ''));
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith('.zip')) {
        alert('Please drop a ZIP file');
        return;
      }
      setSelectedFile(file);
      if (!uploadName) {
        setUploadName(file.name.replace(/\.zip$/i, ''));
      }
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleSync = async (id: string) => {
    setActionLoading(id);
    try {
      await syncRepository(id);
      fetchRepositories();
    } catch (error) {
      console.error('Failed to sync repository:', error);
    } finally {
      setActionLoading(null);
    }
  };

  const handleAnalyze = async (id: string) => {
    setActionLoading(id);
    try {
      await analyzeRepository(id);
      fetchRepositories();
    } catch (error) {
      console.error('Failed to analyze repository:', error);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (id: string, force: boolean = false) => {
    if (!force && !confirm('Are you sure you want to delete this repository?')) return;

    setActionLoading(id);
    try {
      await deleteRepository(id, true, force);
      fetchRepositories();
    } catch (error: any) {
      console.error('Failed to delete repository:', error);
      const errorDetail = error.response?.data?.detail || '';

      // Check if error is due to running analysis jobs
      if (errorDetail.includes('running analysis jobs') || errorDetail.includes('Running jobs')) {
        const forceDelete = confirm(
          `${errorDetail}\n\nDo you want to cancel the running jobs and delete anyway?`
        );
        if (forceDelete) {
          // Retry with force=true
          await handleDelete(id, true);
          return;
        }
      } else {
        alert(errorDetail || 'Failed to delete repository');
      }
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return <LoadingSpinner message="Loading repositories..." />;
  }

  return (
    <div className="repositories-page">
      <div className="repositories-header">
        <h2>Manage Repositories</h2>
        {repositories.length > 0 && (
          <button className="btn btn-primary" onClick={() => setShowAddModal(true)}>
            <Plus size={20} />
            Add Repository
          </button>
        )}
      </div>

      {repositories.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <GitBranch size={64} />
            <h3>No repositories yet</h3>
            <p>Add your first GitHub or GitLab repository to get started with code analysis.</p>
            <button
              className="btn btn-primary empty-state-button"
              onClick={() => setShowAddModal(true)}
            >
              <Plus size={20} />
              Add Repository
            </button>
          </div>
        </div>
      ) : (
        <>
          {/* Search and Filter Controls */}
          <div className="repo-controls">
            <div className="search-box">
              <Search size={18} />
              <input
                type="text"
                placeholder="Search repositories by name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button className="clear-search" onClick={() => setSearchQuery('')}>
                  <X size={16} />
                </button>
              )}
            </div>
            <div className="filter-tabs">
              {(['all', 'completed', 'in_progress', 'not_started', 'failed'] as StatusFilter[]).map((status) => (
                <button
                  key={status}
                  className={`filter-tab ${statusFilter === status ? 'active' : ''}`}
                  onClick={() => setStatusFilter(status)}
                >
                  {status === 'all' ? 'All' : status.replace('_', ' ')}
                  {status !== 'all' && (
                    <span className="count">
                      {repositories.filter((r) => r.analysis_status === status).length}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Repository Table */}
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Repository</th>
                  <th>Platform</th>
                  <th>Clone Status</th>
                  <th>Analysis Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {paginatedRepositories.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="no-results">
                      No repositories found matching your criteria
                    </td>
                  </tr>
                ) : (
                  paginatedRepositories.map((repo) => (
                    <tr key={repo.id}>
                      <td>
                        <div className="repo-name-cell">
                          <Link
                            to={`/repositories/${repo.id}`}
                            className="repo-name-link"
                          >
                            {repo.name}
                          </Link>
                          {repo.description && (
                            <span className="repo-description">
                              {repo.description.slice(0, 60)}
                              {repo.description.length > 60 ? '...' : ''}
                            </span>
                          )}
                        </div>
                      </td>
                      <td>
                        <StatusBadge status={repo.platform} />
                      </td>
                      <td>
                        <StatusBadge status={repo.status} />
                      </td>
                      <td>
                        <StatusBadge status={repo.analysis_status} type="analysis" />
                      </td>
                      <td>
                        <div className="repo-actions">
                          <Link
                            to={`/repositories/${repo.id}`}
                            className="btn btn-sm btn-outline"
                            title="View details & readiness report"
                          >
                            <BarChart2 size={16} />
                          </Link>
                          <button
                            className="btn btn-sm btn-outline"
                            onClick={() => handleSync(repo.id)}
                            disabled={actionLoading === repo.id || repo.status !== 'cloned'}
                            title="Sync repository"
                          >
                            <RefreshCw size={16} className={actionLoading === repo.id ? 'spin' : ''} />
                          </button>
                          <button
                            className="btn btn-sm btn-primary"
                            onClick={() => handleAnalyze(repo.id)}
                            disabled={
                              actionLoading === repo.id ||
                              repo.status !== 'cloned' ||
                              repo.analysis_status === 'in_progress'
                            }
                            title="Analyze repository"
                          >
                            <Play size={16} />
                          </button>
                          <button
                            className="btn btn-sm btn-danger"
                            onClick={() => handleDelete(repo.id)}
                            disabled={actionLoading === repo.id}
                            title="Delete repository"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="pagination">
              <button
                className="btn btn-sm btn-outline"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
              >
                <ChevronLeft size={16} />
                Previous
              </button>
              <span className="page-info">
                Page {currentPage} of {totalPages} ({filteredRepositories.length} repositories)
              </span>
              <button
                className="btn btn-sm btn-outline"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
              >
                Next
                <ChevronRight size={16} />
              </button>
            </div>
          )}
        </>
      )}

      <Modal
        isOpen={showAddModal}
        onClose={handleCloseModal}
        title="Add Repository"
        footer={
          <>
            <button className="btn btn-outline" onClick={handleCloseModal}>
              Cancel
            </button>
            {addMode === 'url' ? (
              <button
                className="btn btn-primary"
                onClick={handleAddRepository}
                disabled={!newRepoUrl || submitting}
              >
                {submitting ? 'Adding...' : 'Add Repository'}
              </button>
            ) : (
              <button
                className="btn btn-primary"
                onClick={handleUploadRepository}
                disabled={!selectedFile || submitting}
              >
                {submitting ? (
                  <>Uploading... {uploadProgress}%</>
                ) : (
                  <>
                    <Upload size={16} />
                    Upload Repository
                  </>
                )}
              </button>
            )}
          </>
        }
      >
        {/* Mode Tabs */}
        <div className="add-mode-tabs">
          <button
            className={`mode-tab ${addMode === 'url' ? 'active' : ''}`}
            onClick={() => setAddMode('url')}
          >
            <LinkIcon size={16} />
            Clone from URL
          </button>
          <button
            className={`mode-tab ${addMode === 'upload' ? 'active' : ''}`}
            onClick={() => setAddMode('upload')}
          >
            <Upload size={16} />
            Upload ZIP
          </button>
        </div>

        {addMode === 'url' ? (
          <>
            <div className="form-group">
              <label htmlFor="repo-url">Repository URL *</label>
              <input
                id="repo-url"
                type="url"
                className="input"
                placeholder="https://github.com/owner/repo"
                value={newRepoUrl}
                onChange={(e) => setNewRepoUrl(e.target.value)}
              />
              <small className="form-help">
                Supports GitHub and GitLab repositories
              </small>
            </div>

            <div className="form-group">
              <label htmlFor="repo-token">Personal Access Token (optional)</label>
              <input
                id="repo-token"
                type="password"
                className="input"
                placeholder="ghp_xxxxxxxxxxxx"
                value={newRepoToken}
                onChange={(e) => setNewRepoToken(e.target.value)}
              />
              <small className="form-help">
                Required for private repositories
              </small>
            </div>
          </>
        ) : (
          <>
            {/* File Drop Zone */}
            <div
              className={`file-drop-zone ${selectedFile ? 'has-file' : ''}`}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip"
                onChange={handleFileSelect}
                style={{ display: 'none' }}
              />
              {selectedFile ? (
                <div className="selected-file">
                  <FileArchive size={32} />
                  <div className="file-info">
                    <span className="file-name">{selectedFile.name}</span>
                    <span className="file-size">{formatFileSize(selectedFile.size)}</span>
                  </div>
                  <button
                    className="remove-file"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedFile(null);
                      if (fileInputRef.current) {
                        fileInputRef.current.value = '';
                      }
                    }}
                  >
                    <X size={16} />
                  </button>
                </div>
              ) : (
                <div className="drop-zone-content">
                  <Upload size={32} />
                  <p>Drag & drop a ZIP file here, or click to browse</p>
                  <small>Maximum file size: 500MB</small>
                </div>
              )}
            </div>

            {/* Upload Progress */}
            {submitting && uploadProgress > 0 && (
              <div className="upload-progress">
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <span>{uploadProgress}%</span>
              </div>
            )}

            <div className="form-group">
              <label htmlFor="upload-name">Repository Name (optional)</label>
              <input
                id="upload-name"
                type="text"
                className="input"
                placeholder="my-project"
                value={uploadName}
                onChange={(e) => setUploadName(e.target.value)}
              />
              <small className="form-help">
                Defaults to the ZIP filename
              </small>
            </div>

            <div className="form-group checkbox-group">
              <label>
                <input
                  type="checkbox"
                  checked={autoAnalyze}
                  onChange={(e) => setAutoAnalyze(e.target.checked)}
                />
                <span>Auto-analyze after upload</span>
              </label>
              <small className="form-help">
                Automatically start code analysis when upload completes
              </small>
            </div>
          </>
        )}
      </Modal>

    </div>
  );
}
