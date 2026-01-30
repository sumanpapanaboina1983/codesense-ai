import { useQuery } from '@tanstack/react-query';
import { getGraphStats, getJobs, getHealth } from '../../services/api';
import { useAppStore } from '../../store/appStore';
import {
  Database,
  GitBranch,
  FileCode,
  Activity,
  CheckCircle,
  XCircle,
  Clock,
  ArrowRight,
  MessageSquare,
  FileText,
  Layers,
  ListTodo,
  FolderGit2,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import './Dashboard.css';

export function Dashboard() {
  const { setGraphStats, setJobs, setHealth } = useAppStore();

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['graphStats'],
    queryFn: async () => {
      const data = await getGraphStats();
      setGraphStats(data);
      return data;
    },
    refetchInterval: 10000,
  });

  const { data: jobsData, isLoading: jobsLoading } = useQuery({
    queryKey: ['jobs'],
    queryFn: async () => {
      const data = await getJobs();
      setJobs(data.jobs);
      return data;
    },
    refetchInterval: 5000,
  });

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const data = await getHealth();
      setHealth(data);
      return data;
    },
    refetchInterval: 30000,
  });

  const recentJobs = jobsData?.jobs?.slice(0, 5) || [];
  const runningJobs = jobsData?.jobs?.filter((j) => j.status === 'running').length || 0;
  const completedJobs = jobsData?.jobs?.filter((j) => j.status === 'completed').length || 0;
  const failedJobs = jobsData?.jobs?.filter((j) => j.status === 'failed').length || 0;

  const topNodeLabels = stats?.nodesByLabel
    ? Object.entries(stats.nodesByLabel)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6)
    : [];

  return (
    <div className="dashboard-page">
      <div className="page-header">
        <h1>Dashboard</h1>
        <p>Welcome to CodeSense AI - Your intelligent code analysis platform</p>
      </div>

      <div className="page-content">
        {/* Stats Cards */}
        <div className="stats-grid">
          <div className="stats-card">
            <div className="stats-icon info">
              <Database size={24} />
            </div>
            <div className="stats-content">
              <span className="stats-title">Total Nodes</span>
              <span className="stats-value">
                {statsLoading ? '...' : stats?.totalNodes?.toLocaleString() || 0}
              </span>
            </div>
          </div>

          <div className="stats-card">
            <div className="stats-icon success">
              <GitBranch size={24} />
            </div>
            <div className="stats-content">
              <span className="stats-title">Relationships</span>
              <span className="stats-value">
                {statsLoading ? '...' : stats?.totalRelationships?.toLocaleString() || 0}
              </span>
            </div>
          </div>

          <div className="stats-card">
            <div className="stats-icon warning">
              <FileCode size={24} />
            </div>
            <div className="stats-content">
              <span className="stats-title">Files Analyzed</span>
              <span className="stats-value">
                {statsLoading ? '...' : stats?.nodesByLabel?.File?.toLocaleString() || 0}
              </span>
            </div>
          </div>

          <div className="stats-card">
            <div className="stats-icon">
              <Activity size={24} />
            </div>
            <div className="stats-content">
              <span className="stats-title">Running Jobs</span>
              <span className="stats-value">{jobsLoading ? '...' : runningJobs}</span>
            </div>
          </div>
        </div>

        {/* Workflow Cards */}
        <div className="section-header">
          <h2>AI-Powered Workflows</h2>
          <p>Generate documentation and manage your development workflow</p>
        </div>

        <div className="workflow-grid">
          <Link to="/chat" className="action-card">
            <div className="action-icon">
              <MessageSquare size={28} />
            </div>
            <div className="action-content">
              <h3>Code Assistant</h3>
              <p>Ask questions about your codebase and get intelligent insights</p>
            </div>
            <ArrowRight size={20} className="arrow-icon" />
          </Link>

          <Link to="/generate-brd" className="action-card">
            <div className="action-icon">
              <FileText size={28} />
            </div>
            <div className="action-content">
              <h3>Generate BRD</h3>
              <p>Create Business Requirements Documents from code analysis</p>
            </div>
            <ArrowRight size={20} className="arrow-icon" />
          </Link>

          <Link to="/generate-epic" className="action-card">
            <div className="action-icon">
              <Layers size={28} />
            </div>
            <div className="action-content">
              <h3>Generate EPIC</h3>
              <p>Transform BRDs into detailed EPICs with user stories</p>
            </div>
            <ArrowRight size={20} className="arrow-icon" />
          </Link>

          <Link to="/generate-backlogs" className="action-card">
            <div className="action-icon">
              <ListTodo size={28} />
            </div>
            <div className="action-content">
              <h3>Generate Backlogs</h3>
              <p>Create actionable backlog items from EPICs</p>
            </div>
            <ArrowRight size={20} className="arrow-icon" />
          </Link>
        </div>

        {/* Main Content Grid */}
        <div className="dashboard-grid">
          {/* Recent Jobs */}
          <div className="card">
            <div className="card-header">
              <h3>Recent Analysis Jobs</h3>
              <Link to="/jobs" className="view-all-link">
                View All <ArrowRight size={16} />
              </Link>
            </div>
            <div className="card-body">
              {recentJobs.length === 0 ? (
                <div className="empty-state">
                  <FolderGit2 size={48} />
                  <h3>No analysis jobs yet</h3>
                  <p>Start by analyzing a repository to see your jobs here</p>
                  <Link to="/analyze" className="btn btn-primary">
                    Analyze Repository
                  </Link>
                </div>
              ) : (
                <div className="jobs-list">
                  {recentJobs.map((job) => (
                    <div key={job.id} className="job-item">
                      <div className="job-status">
                        {job.status === 'completed' && <CheckCircle size={18} className="success" />}
                        {job.status === 'failed' && <XCircle size={18} className="error" />}
                        {job.status === 'running' && <Clock size={18} className="running" />}
                        {job.status === 'pending' && <Clock size={18} className="pending" />}
                      </div>
                      <div className="job-info">
                        <span className="job-directory">{job.gitUrl || job.directory}</span>
                        <span className="job-time">
                          {new Date(job.startedAt).toLocaleString()}
                        </span>
                      </div>
                      <span className={`badge badge-${job.status === 'completed' ? 'success' : job.status === 'failed' ? 'error' : job.status === 'running' ? 'running' : 'pending'}`}>
                        {job.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Node Distribution */}
          <div className="card">
            <div className="card-header">
              <h3>Node Distribution</h3>
            </div>
            <div className="card-body">
              {topNodeLabels.length === 0 ? (
                <div className="empty-state">
                  <Database size={48} />
                  <h3>No graph data available</h3>
                  <p>Analyze a repository to see node distribution</p>
                  <Link to="/analyze" className="btn btn-primary">
                    Analyze a Repository
                  </Link>
                </div>
              ) : (
                <div className="distribution-list">
                  {topNodeLabels.map(([label, count]) => {
                    const percentage = stats?.totalNodes
                      ? ((count / stats.totalNodes) * 100).toFixed(1)
                      : 0;
                    return (
                      <div key={label} className="distribution-item">
                        <div className="distribution-label">
                          <span className="label-name">{label}</span>
                          <span className="label-count">{count.toLocaleString()}</span>
                        </div>
                        <div className="progress-bar">
                          <div
                            className="progress-fill"
                            style={{ width: `${percentage}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* System Status */}
          <div className="card">
            <div className="card-header">
              <h3>System Status</h3>
            </div>
            <div className="card-body">
              <div className="status-list">
                <div className="status-item">
                  <span>Neo4j Database</span>
                  <span className={`badge ${health?.neo4j === 'connected' ? 'badge-success' : 'badge-error'}`}>
                    {health?.neo4j || 'Unknown'}
                  </span>
                </div>
                <div className="status-item">
                  <span>Completed Jobs</span>
                  <span className="badge badge-success">{completedJobs}</span>
                </div>
                <div className="status-item">
                  <span>Failed Jobs</span>
                  <span className="badge badge-error">{failedJobs}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
