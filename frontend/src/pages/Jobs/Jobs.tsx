import { useQuery } from '@tanstack/react-query';
import { Header } from '../../components/Layout';
import { getJobs, getJob } from '../../services/api';
import { useAppStore } from '../../store/appStore';
import {
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  RefreshCw,
  FolderGit2,
  Calendar,
  Timer,
  FileCode,
  GitBranch,
  Database,
} from 'lucide-react';
import './Jobs.css';

export function Jobs() {
  const { jobs, setJobs, updateJob } = useAppStore();

  const { isLoading, refetch, isFetching } = useQuery({
    queryKey: ['jobs'],
    queryFn: async () => {
      const data = await getJobs();
      setJobs(data.jobs);
      return data;
    },
    refetchInterval: 3000, // Poll every 3 seconds for running jobs
  });

  // Poll individual running jobs for updates
  const runningJobs = jobs.filter((j) => j.status === 'running' || j.status === 'pending');

  useQuery({
    queryKey: ['runningJobs', runningJobs.map((j) => j.id).join(',')],
    queryFn: async () => {
      const updates = await Promise.all(
        runningJobs.map((job) => getJob(job.id).catch(() => null))
      );
      updates.forEach((update) => {
        if (update) {
          updateJob(update);
        }
      });
      return updates;
    },
    enabled: runningJobs.length > 0,
    refetchInterval: 2000,
  });

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle size={20} className="status-icon success" />;
      case 'failed':
        return <XCircle size={20} className="status-icon error" />;
      case 'running':
        return <Loader2 size={20} className="status-icon running spinning" />;
      case 'pending':
        return <Clock size={20} className="status-icon pending" />;
      default:
        return <Clock size={20} className="status-icon" />;
    }
  };

  const formatDuration = (start: string, end?: string) => {
    const startDate = new Date(start);
    const endDate = end ? new Date(end) : new Date();
    const diff = endDate.getTime() - startDate.getTime();

    if (diff < 1000) return '<1s';
    if (diff < 60000) return `${Math.floor(diff / 1000)}s`;
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ${Math.floor((diff % 60000) / 1000)}s`;
    return `${Math.floor(diff / 3600000)}h ${Math.floor((diff % 3600000) / 60000)}m`;
  };

  const sortedJobs = [...jobs].sort(
    (a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime()
  );

  return (
    <div>
      <Header
        title="Analysis Jobs"
        subtitle={`${jobs.length} total jobs, ${runningJobs.length} running`}
      />

      <div className="page-container">
        <div className="jobs-header">
          <div className="jobs-filters">
            <span className="filter-label">All Jobs</span>
          </div>
          <button
            className="refresh-btn"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw size={16} className={isFetching ? 'spinning' : ''} />
            Refresh
          </button>
        </div>

        {isLoading ? (
          <div className="loading-state">
            <Loader2 size={32} className="spinning" />
            <p>Loading jobs...</p>
          </div>
        ) : sortedJobs.length === 0 ? (
          <div className="empty-state">
            <FolderGit2 size={48} />
            <h3>No Analysis Jobs</h3>
            <p>Start by analyzing a repository</p>
          </div>
        ) : (
          <div className="jobs-grid">
            {sortedJobs.map((job) => (
              <div key={job.id} className={`job-card ${job.status}`}>
                <div className="job-card-header">
                  {getStatusIcon(job.status)}
                  <span className={`job-status-badge ${job.status}`}>
                    {job.status}
                  </span>
                </div>

                <div className="job-card-body">
                  <div className="job-source">
                    {job.gitUrl ? (
                      <>
                        <GitBranch size={16} />
                        <span>{job.gitUrl}</span>
                      </>
                    ) : (
                      <>
                        <FolderGit2 size={16} />
                        <span>{job.directory}</span>
                      </>
                    )}
                  </div>

                  <div className="job-meta">
                    <div className="meta-item">
                      <Calendar size={14} />
                      <span>{new Date(job.startedAt).toLocaleString()}</span>
                    </div>
                    <div className="meta-item">
                      <Timer size={14} />
                      <span>
                        {job.status === 'running' || job.status === 'pending'
                          ? formatDuration(job.startedAt)
                          : formatDuration(job.startedAt, job.completedAt)}
                      </span>
                    </div>
                  </div>

                  {job.stats && (
                    <div className="job-stats">
                      <div className="stat-item">
                        <FileCode size={14} />
                        <span>{job.stats.filesScanned || 0} files</span>
                      </div>
                      <div className="stat-item">
                        <Database size={14} />
                        <span>{job.stats.nodesCreated || 0} nodes</span>
                      </div>
                      <div className="stat-item">
                        <GitBranch size={14} />
                        <span>{job.stats.relationshipsCreated || 0} rels</span>
                      </div>
                    </div>
                  )}

                  {job.error && (
                    <div className="job-error">
                      <XCircle size={14} />
                      <span>{job.error}</span>
                    </div>
                  )}
                </div>

                <div className="job-card-footer">
                  <span className="job-id">ID: {job.id.slice(0, 20)}...</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
