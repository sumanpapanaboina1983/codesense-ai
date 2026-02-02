import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Plus,
  RefreshCw,
  Play,
  Trash2,
  GitBranch,
  ExternalLink,
  Star,
  GitFork,
  BarChart2,
} from 'lucide-react';
import {
  getRepositories,
  createRepository,
  deleteRepository,
  syncRepository,
  analyzeRepository,
} from '../api/client';
import type { Repository } from '../types';
import { Modal } from '../components/Modal';
import { StatusBadge } from '../components/StatusBadge';
import { LoadingSpinner } from '../components/LoadingSpinner';

export function Repositories() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [newRepoUrl, setNewRepoUrl] = useState('');
  const [newRepoToken, setNewRepoToken] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

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

  const handleAddRepository = async () => {
    if (!newRepoUrl) return;

    setSubmitting(true);
    try {
      await createRepository({
        url: newRepoUrl,
        personal_access_token: newRepoToken || undefined,
        auto_analyze_on_sync: true,
      });
      setNewRepoUrl('');
      setNewRepoToken('');
      setShowAddModal(false);
      fetchRepositories();
    } catch (error) {
      console.error('Failed to add repository:', error);
      alert('Failed to add repository. Please check the URL and try again.');
    } finally {
      setSubmitting(false);
    }
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

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this repository?')) return;

    setActionLoading(id);
    try {
      await deleteRepository(id, true);
      fetchRepositories();
    } catch (error) {
      console.error('Failed to delete repository:', error);
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return <LoadingSpinner message="Loading repositories..." />;
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--spacing-lg)' }}>
        <h2 style={{ margin: 0 }}>Manage Repositories</h2>
        <button className="btn btn-primary" onClick={() => setShowAddModal(true)}>
          <Plus size={20} />
          Add Repository
        </button>
      </div>

      {repositories.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <GitBranch size={64} />
            <h3>No repositories yet</h3>
            <p>Add your first GitHub or GitLab repository to get started with code analysis.</p>
            <button
              className="btn btn-primary"
              style={{ marginTop: 'var(--spacing-lg)' }}
              onClick={() => setShowAddModal(true)}
            >
              <Plus size={20} />
              Add Repository
            </button>
          </div>
        </div>
      ) : (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>Repository</th>
                <th>Platform</th>
                <th>Clone Status</th>
                <th>Analysis Status</th>
                <th>Stats</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {repositories.map((repo) => (
                <tr key={repo.id}>
                  <td>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <Link
                        to={`/repositories/${repo.id}`}
                        style={{ fontWeight: 600, color: 'var(--color-primary)', textDecoration: 'none' }}
                      >
                        {repo.name}
                      </Link>
                      {repo.description && (
                        <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-gray-500)' }}>
                          {repo.description.slice(0, 60)}
                          {repo.description.length > 60 ? '...' : ''}
                        </span>
                      )}
                      <a
                        href={repo.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: 'var(--font-size-xs)', display: 'flex', alignItems: 'center', gap: '4px' }}
                      >
                        <ExternalLink size={12} />
                        View on {repo.platform}
                      </a>
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
                    <div style={{ display: 'flex', gap: 'var(--spacing-md)', fontSize: 'var(--font-size-sm)' }}>
                      {repo.stars !== undefined && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <Star size={14} /> {repo.stars}
                        </span>
                      )}
                      {repo.forks !== undefined && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <GitFork size={14} /> {repo.forks}
                        </span>
                      )}
                      {repo.language && (
                        <span className="badge badge-info">{repo.language}</span>
                      )}
                    </div>
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 'var(--spacing-xs)' }}>
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
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        title="Add Repository"
        footer={
          <>
            <button className="btn btn-outline" onClick={() => setShowAddModal(false)}>
              Cancel
            </button>
            <button
              className="btn btn-primary"
              onClick={handleAddRepository}
              disabled={!newRepoUrl || submitting}
            >
              {submitting ? 'Adding...' : 'Add Repository'}
            </button>
          </>
        }
      >
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
          <small style={{ color: 'var(--color-gray-500)', marginTop: '4px', display: 'block' }}>
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
          <small style={{ color: 'var(--color-gray-500)', marginTop: '4px', display: 'block' }}>
            Required for private repositories
          </small>
        </div>
      </Modal>

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
