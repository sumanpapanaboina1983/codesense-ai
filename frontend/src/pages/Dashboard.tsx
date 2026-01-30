import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  GitBranch,
  FileText,
  ListTree,
  ClipboardList,
  CheckCircle,
  XCircle,
  Clock,
  Activity,
} from 'lucide-react';
import { getRepositories, getHealth } from '../api/client';
import type { Repository, HealthStatus } from '../types';
import { LoadingSpinner } from '../components/LoadingSpinner';

export function Dashboard() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [repos, healthStatus] = await Promise.all([
          getRepositories(),
          getHealth(),
        ]);
        setRepositories(repos);
        setHealth(healthStatus);
      } catch (error) {
        console.error('Failed to fetch data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return <LoadingSpinner message="Loading dashboard..." />;
  }

  const analyzedCount = repositories.filter(
    (r) => r.analysis_status === 'completed'
  ).length;
  const pendingCount = repositories.filter(
    (r) => r.analysis_status === 'in_progress'
  ).length;
  const failedCount = repositories.filter(
    (r) => r.analysis_status === 'failed'
  ).length;

  return (
    <div className="dashboard">
      {/* Stats Grid */}
      <div className="grid grid-cols-4">
        <div className="stats-card">
          <div className="stats-icon info">
            <GitBranch size={28} />
          </div>
          <div className="stats-content">
            <span className="stats-title">Repositories</span>
            <span className="stats-value">{repositories.length}</span>
          </div>
        </div>

        <div className="stats-card">
          <div className="stats-icon success">
            <CheckCircle size={28} />
          </div>
          <div className="stats-content">
            <span className="stats-title">Analyzed</span>
            <span className="stats-value">{analyzedCount}</span>
          </div>
        </div>

        <div className="stats-card">
          <div className="stats-icon warning">
            <Clock size={28} />
          </div>
          <div className="stats-content">
            <span className="stats-title">In Progress</span>
            <span className="stats-value">{pendingCount}</span>
          </div>
        </div>

        <div className="stats-card">
          <div className="stats-icon error">
            <XCircle size={28} />
          </div>
          <div className="stats-content">
            <span className="stats-title">Failed</span>
            <span className="stats-value">{failedCount}</span>
          </div>
        </div>
      </div>

      {/* System Status */}
      <div className="card">
        <div className="card-header">
          <h3>System Status</h3>
        </div>
        <div className="card-body">
          <div className="grid grid-cols-3">
            <div className="stats-card">
              <div className={`stats-icon ${health?.mcp_servers.neo4j ? 'success' : 'error'}`}>
                <Activity size={24} />
              </div>
              <div className="stats-content">
                <span className="stats-title">Neo4j MCP</span>
                <span className={`badge ${health?.mcp_servers.neo4j ? 'badge-success' : 'badge-error'}`}>
                  {health?.mcp_servers.neo4j ? 'Connected' : 'Disconnected'}
                </span>
              </div>
            </div>

            <div className="stats-card">
              <div className={`stats-icon ${health?.mcp_servers.filesystem ? 'success' : 'error'}`}>
                <Activity size={24} />
              </div>
              <div className="stats-content">
                <span className="stats-title">Filesystem MCP</span>
                <span className={`badge ${health?.mcp_servers.filesystem ? 'badge-success' : 'badge-error'}`}>
                  {health?.mcp_servers.filesystem ? 'Connected' : 'Disconnected'}
                </span>
              </div>
            </div>

            <div className="stats-card">
              <div className={`stats-icon ${health?.copilot_available ? 'success' : 'error'}`}>
                <Activity size={24} />
              </div>
              <div className="stats-content">
                <span className="stats-title">Copilot SDK</span>
                <span className={`badge ${health?.copilot_available ? 'badge-success' : 'badge-error'}`}>
                  {health?.copilot_available ? 'Available' : 'Unavailable'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="card">
        <div className="card-header">
          <h3>Quick Actions</h3>
        </div>
        <div className="card-body">
          <div className="grid grid-cols-4">
            <Link to="/repositories" className="action-card">
              <div className="action-icon" style={{ background: 'var(--color-accent)', color: 'var(--color-primary)' }}>
                <GitBranch size={28} />
              </div>
              <div className="action-content">
                <h3>Onboard Repository</h3>
                <p>Add a new GitHub or GitLab repository</p>
              </div>
            </Link>

            <Link to="/workflow/brd" className="action-card">
              <div className="action-icon">
                <FileText size={28} />
              </div>
              <div className="action-content">
                <h3>Generate BRD</h3>
                <p>Create business requirements document</p>
              </div>
            </Link>

            <Link to="/workflow/epics" className="action-card">
              <div className="action-icon">
                <ListTree size={28} />
              </div>
              <div className="action-content">
                <h3>Generate Epics</h3>
                <p>Break down BRD into epics</p>
              </div>
            </Link>

            <Link to="/workflow/stories" className="action-card">
              <div className="action-icon">
                <ClipboardList size={28} />
              </div>
              <div className="action-content">
                <h3>Generate Stories</h3>
                <p>Create user stories from epics</p>
              </div>
            </Link>
          </div>
        </div>
      </div>

      {/* Recent Repositories */}
      {repositories.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h3>Recent Repositories</h3>
            <Link to="/repositories" className="btn btn-sm btn-outline">
              View All
            </Link>
          </div>
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Platform</th>
                  <th>Status</th>
                  <th>Analysis</th>
                  <th>Last Updated</th>
                </tr>
              </thead>
              <tbody>
                {repositories.slice(0, 5).map((repo) => (
                  <tr key={repo.id}>
                    <td>
                      <strong>{repo.name}</strong>
                    </td>
                    <td>
                      <span className="badge badge-info">{repo.platform}</span>
                    </td>
                    <td>
                      <span
                        className={`badge ${
                          repo.status === 'cloned'
                            ? 'badge-success'
                            : repo.status === 'cloning'
                            ? 'badge-running'
                            : repo.status === 'failed'
                            ? 'badge-error'
                            : 'badge-pending'
                        }`}
                      >
                        {repo.status}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`badge ${
                          repo.analysis_status === 'completed'
                            ? 'badge-success'
                            : repo.analysis_status === 'in_progress'
                            ? 'badge-running'
                            : repo.analysis_status === 'failed'
                            ? 'badge-error'
                            : 'badge-pending'
                        }`}
                      >
                        {repo.analysis_status.replace('_', ' ')}
                      </span>
                    </td>
                    <td>{new Date(repo.updated_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
