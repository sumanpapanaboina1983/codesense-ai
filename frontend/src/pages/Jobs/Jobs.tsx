import { useState, useEffect, useRef, useCallback, Fragment } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '../../components/Layout';
import { getJobs, getJob, cancelJob, deleteJob, pauseJob, resumeJob, downloadJobLogs } from '../../services/api';
import type { AnalysisJob } from '../../types/api';
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
  Database,
  ChevronDown,
  ChevronUp,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Terminal,
  Layers,
  Code2,
  Network,
  Box,
  StopCircle,
  Trash2,
  Pause,
  Play,
  Download,
} from 'lucide-react';
import './Jobs.css';

type StatusFilter = 'all' | 'running' | 'completed' | 'failed' | 'pending' | 'paused';
type SortField = 'status' | 'repository' | 'startedAt' | 'duration' | 'progress';
type SortDirection = 'asc' | 'desc';

interface StreamingState {
  logs: string[];
  phase: string;
  progress: number;
  filesProcessed: number;
  totalFiles: number;
  nodesCreated: number;
  relationshipsCreated: number;
  isConnected: boolean;
}

export function Jobs() {
  const { jobs, setJobs, updateJob } = useAppStore();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [sortField, setSortField] = useState<SortField>('status');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [streamingState, setStreamingState] = useState<StreamingState>({
    logs: [],
    phase: '',
    progress: 0,
    filesProcessed: 0,
    totalFiles: 0,
    nodesCreated: 0,
    relationshipsCreated: 0,
    isConnected: false,
  });

  const streamCleanupRef = useRef<(() => void) | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const { isLoading, refetch, isFetching } = useQuery({
    queryKey: ['jobs'],
    queryFn: async () => {
      const data = await getJobs();
      setJobs(data.jobs);
      return data;
    },
    refetchInterval: 3000,
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

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [streamingState.logs]);

  // Cleanup streaming on unmount or when expanding different job
  useEffect(() => {
    return () => {
      if (streamCleanupRef.current) {
        streamCleanupRef.current();
      }
    };
  }, []);

  const startStreaming = useCallback((jobId: string) => {
    // Cleanup previous polling
    if (streamCleanupRef.current) {
      streamCleanupRef.current();
    }

    let lastStatus = '';
    let cancelled = false;

    setStreamingState({
      logs: ['Polling job status...'],
      phase: 'Initializing',
      progress: 0,
      filesProcessed: 0,
      totalFiles: 0,
      nodesCreated: 0,
      relationshipsCreated: 0,
      isConnected: true,
    });

    // Poll for job status since SSE streaming isn't available for codegraph jobs
    const pollInterval = setInterval(async () => {
      if (cancelled) return;

      try {
        const job = await getJob(jobId);

        setStreamingState((prev) => {
          // Use logs from backend if available, otherwise build our own
          let newLogs: string[];
          if (job.logs && job.logs.length > 0) {
            // Use logs from backend (persisted in PostgreSQL)
            newLogs = job.logs;
          } else {
            newLogs = [...prev.logs];

            // Log status changes
            if (job.status !== lastStatus) {
              lastStatus = job.status;
              newLogs.push(`[STATUS] Job status: ${job.status}`);
              if (job.status === 'running') {
                newLogs.push(`[INFO] Analysis in progress...`);
              }
            }

            // Log stats if available
            if (job.stats) {
              const statsLine = `[STATS] Files: ${job.stats.filesScanned || 0}, Nodes: ${job.stats.nodesCreated || 0}, Relationships: ${job.stats.relationshipsCreated || 0}`;
              // Only add if different from last stats log
              if (!newLogs.some(l => l === statsLine)) {
                newLogs.push(statsLine);
              }
            }

            if (job.status === 'completed') {
              newLogs.push(`[COMPLETE] Analysis finished successfully!`);
              if (job.stats) {
                newLogs.push(`  - Files scanned: ${job.stats.filesScanned || 0}`);
                newLogs.push(`  - Nodes created: ${job.stats.nodesCreated || 0}`);
                newLogs.push(`  - Relationships created: ${job.stats.relationshipsCreated || 0}`);
              }
            } else if (job.status === 'failed') {
              newLogs.push(`[ERROR] ${job.error || 'Analysis failed'}`);
            }
          }

          // Keep only last 100 logs
          const trimmedLogs = newLogs.slice(-100);

          return {
            ...prev,
            logs: trimmedLogs,
            phase: job.currentPhase || (job.status === 'completed' ? 'Done' : (job.status === 'running' ? 'Analyzing' : job.status)),
            progress: job.status === 'completed' ? 100 : (job.progressPct || 0),
            filesProcessed: job.stats?.filesScanned || 0,
            totalFiles: job.stats?.totalFiles || 0,
            nodesCreated: job.stats?.nodesCreated || 0,
            relationshipsCreated: job.stats?.relationshipsCreated || 0,
            isConnected: job.status === 'running' || job.status === 'pending',
          };
        });

        // Stop polling on completion, error, or pause
        if (job.status === 'completed' || job.status === 'failed' || job.status === 'paused' || job.status === 'cancelled') {
          clearInterval(pollInterval);
          refetch();
        }
      } catch (error: any) {
        console.error('Failed to poll job status:', error);
        setStreamingState((prev) => ({
          ...prev,
          logs: [...prev.logs, `[ERROR] Failed to get job status: ${error.message}`],
        }));
      }
    }, 2000); // Poll every 2 seconds

    // Store cleanup function
    streamCleanupRef.current = () => {
      cancelled = true;
      clearInterval(pollInterval);
    };
  }, [refetch]);

  const handleRowClick = (job: AnalysisJob) => {
    if (expandedJobId === job.id) {
      // Collapse
      setExpandedJobId(null);
      if (streamCleanupRef.current) {
        streamCleanupRef.current();
        streamCleanupRef.current = null;
      }
      setStreamingState({
        logs: [],
        phase: '',
        progress: 0,
        filesProcessed: 0,
        totalFiles: 0,
        nodesCreated: 0,
        relationshipsCreated: 0,
        isConnected: false,
      });
    } else {
      // Expand
      setExpandedJobId(job.id);

      // Initialize with job's current state
      setStreamingState({
        logs: job.status === 'running' || job.status === 'pending'
          ? ['Starting live stream...']
          : [`Analysis ${job.status}. Showing final results.`],
        phase: job.currentPhase || '',
        progress: job.progressPct || 0,
        filesProcessed: job.stats?.filesScanned || 0,
        totalFiles: job.stats?.totalFiles || 0,
        nodesCreated: job.stats?.nodesCreated || 0,
        relationshipsCreated: job.stats?.relationshipsCreated || 0,
        isConnected: false,
      });

      // Start streaming for running jobs
      if (job.status === 'running' || job.status === 'pending') {
        startStreaming(job.id);
      }
    }
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const handleCancelJob = async (e: React.MouseEvent, jobId: string) => {
    e.stopPropagation(); // Prevent row expansion
    if (!confirm('Are you sure you want to cancel this analysis? This cannot be resumed.')) return;

    setActionLoading(jobId);
    try {
      await cancelJob(jobId);
      refetch();
    } catch (err: any) {
      console.error('Failed to cancel job:', err);
      alert(err.response?.data?.detail || 'Failed to cancel job');
    } finally {
      setActionLoading(null);
    }
  };

  const handlePauseJob = async (e: React.MouseEvent, jobId: string) => {
    e.stopPropagation(); // Prevent row expansion
    if (!confirm('Are you sure you want to pause this analysis? You can resume it later.')) return;

    setActionLoading(jobId);
    try {
      await pauseJob(jobId);
      refetch();
    } catch (err: any) {
      console.error('Failed to pause job:', err);
      alert(err.response?.data?.detail || 'Failed to pause job');
    } finally {
      setActionLoading(null);
    }
  };

  const handleResumeJob = async (e: React.MouseEvent, jobId: string) => {
    e.stopPropagation(); // Prevent row expansion

    setActionLoading(jobId);
    try {
      await resumeJob(jobId);
      refetch();
    } catch (err: any) {
      console.error('Failed to resume job:', err);
      alert(err.response?.data?.detail || 'Failed to resume job');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeleteJob = async (e: React.MouseEvent, jobId: string) => {
    e.stopPropagation(); // Prevent row expansion
    if (!confirm('Are you sure you want to delete this analysis job? This cannot be undone.')) return;

    setActionLoading(jobId);
    try {
      await deleteJob(jobId);
      // Close expanded row if it was the deleted job
      if (expandedJobId === jobId) {
        setExpandedJobId(null);
        if (streamCleanupRef.current) {
          streamCleanupRef.current();
          streamCleanupRef.current = null;
        }
      }
      refetch();
    } catch (err: any) {
      console.error('Failed to delete job:', err);
      alert(err.response?.data?.detail || 'Failed to delete job');
    } finally {
      setActionLoading(null);
    }
  };

  const getStatusIcon = (status: string, size = 18) => {
    switch (status) {
      case 'completed':
        return <CheckCircle size={size} className="status-icon success" />;
      case 'failed':
        return <XCircle size={size} className="status-icon error" />;
      case 'cancelled':
        return <StopCircle size={size} className="status-icon error" />;
      case 'running':
        return <Loader2 size={size} className="status-icon running spinning" />;
      case 'pending':
        return <Clock size={size} className="status-icon pending" />;
      case 'paused':
        return <Pause size={size} className="status-icon paused" />;
      default:
        return <Clock size={size} className="status-icon" />;
    }
  };

  const getStatusPriority = (status: string): number => {
    switch (status) {
      case 'running': return 0;
      case 'pending': return 1;
      case 'paused': return 2;
      case 'failed': return 3;
      case 'cancelled': return 4;
      case 'completed': return 5;
      default: return 6;
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

  const formatNumber = (num: number): string => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toString();
  };

  const getRepositoryName = (job: AnalysisJob): string => {
    // Use repositoryName directly if available (from database)
    if (job.repositoryName) {
      return job.repositoryName;
    }
    if (job.gitUrl) {
      const parts = job.gitUrl.split('/');
      return parts.slice(-2).join('/').replace('.git', '');
    }
    if (job.directory) {
      // Extract name from path if it looks like a path
      const name = job.directory.split('/').pop() || job.directory;
      return name;
    }
    return 'Unknown';
  };

  // Filter jobs
  const filteredJobs = jobs.filter((job) => {
    if (statusFilter === 'all') return true;
    if (statusFilter === 'running') return job.status === 'running' || job.status === 'pending';
    if (statusFilter === 'failed') return job.status === 'failed' || job.status === 'cancelled';
    if (statusFilter === 'paused') return job.status === 'paused';
    return job.status === statusFilter;
  });

  // Sort jobs
  const sortedJobs = [...filteredJobs].sort((a, b) => {
    let comparison = 0;

    switch (sortField) {
      case 'status':
        comparison = getStatusPriority(a.status) - getStatusPriority(b.status);
        break;
      case 'repository':
        comparison = getRepositoryName(a).localeCompare(getRepositoryName(b));
        break;
      case 'startedAt':
        comparison = new Date(a.startedAt).getTime() - new Date(b.startedAt).getTime();
        break;
      case 'duration':
        const durationA = a.completedAt
          ? new Date(a.completedAt).getTime() - new Date(a.startedAt).getTime()
          : Date.now() - new Date(a.startedAt).getTime();
        const durationB = b.completedAt
          ? new Date(b.completedAt).getTime() - new Date(b.startedAt).getTime()
          : Date.now() - new Date(b.startedAt).getTime();
        comparison = durationA - durationB;
        break;
      case 'progress':
        comparison = (a.progressPct || 0) - (b.progressPct || 0);
        break;
    }

    return sortDirection === 'asc' ? comparison : -comparison;
  });

  // Count jobs by status
  const statusCounts = {
    all: jobs.length,
    running: jobs.filter((j) => j.status === 'running' || j.status === 'pending').length,
    completed: jobs.filter((j) => j.status === 'completed').length,
    failed: jobs.filter((j) => j.status === 'failed' || j.status === 'cancelled').length,
    paused: jobs.filter((j) => j.status === 'paused').length,
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown size={14} className="sort-icon inactive" />;
    return sortDirection === 'asc'
      ? <ArrowUp size={14} className="sort-icon active" />
      : <ArrowDown size={14} className="sort-icon active" />;
  };

  return (
    <div>
      <Header
        title="Analysis Jobs"
        subtitle={`${jobs.length} total jobs, ${statusCounts.running} in progress`}
      />

      <div className="page-container">
        {/* Filters and Actions */}
        <div className="jobs-toolbar">
          <div className="jobs-filters">
            <button
              className={`filter-btn ${statusFilter === 'all' ? 'active' : ''}`}
              onClick={() => setStatusFilter('all')}
            >
              All ({statusCounts.all})
            </button>
            <button
              className={`filter-btn running ${statusFilter === 'running' ? 'active' : ''}`}
              onClick={() => setStatusFilter('running')}
            >
              <Loader2 size={14} className={statusCounts.running > 0 ? 'spinning' : ''} />
              In Progress ({statusCounts.running})
            </button>
            <button
              className={`filter-btn completed ${statusFilter === 'completed' ? 'active' : ''}`}
              onClick={() => setStatusFilter('completed')}
            >
              <CheckCircle size={14} />
              Completed ({statusCounts.completed})
            </button>
            <button
              className={`filter-btn failed ${statusFilter === 'failed' ? 'active' : ''}`}
              onClick={() => setStatusFilter('failed')}
            >
              <XCircle size={14} />
              Failed ({statusCounts.failed})
            </button>
            <button
              className={`filter-btn paused ${statusFilter === 'paused' ? 'active' : ''}`}
              onClick={() => setStatusFilter('paused')}
            >
              <Pause size={14} />
              Paused ({statusCounts.paused})
            </button>
          </div>
          <button
            className="btn btn-outline refresh-btn"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw size={16} className={isFetching ? 'spinning' : ''} />
            Refresh
          </button>
        </div>

        {/* Jobs Table */}
        {isLoading ? (
          <div className="loading-state">
            <Loader2 size={32} className="spinning" />
            <p>Loading jobs...</p>
          </div>
        ) : sortedJobs.length === 0 ? (
          <div className="empty-state">
            <FolderGit2 size={48} />
            <h3>No Analysis Jobs</h3>
            <p>Start by analyzing a repository from the Repositories page</p>
          </div>
        ) : (
          <div className="jobs-table-container">
            <table className="jobs-table">
              <thead>
                <tr>
                  <th className="col-expand"></th>
                  <th className="col-status sortable" onClick={() => handleSort('status')}>
                    Status <SortIcon field="status" />
                  </th>
                  <th className="col-repository sortable" onClick={() => handleSort('repository')}>
                    Repository <SortIcon field="repository" />
                  </th>
                  <th className="col-progress sortable" onClick={() => handleSort('progress')}>
                    Progress <SortIcon field="progress" />
                  </th>
                  <th className="col-phase">Phase</th>
                  <th className="col-started sortable" onClick={() => handleSort('startedAt')}>
                    Started <SortIcon field="startedAt" />
                  </th>
                  <th className="col-duration sortable" onClick={() => handleSort('duration')}>
                    Duration <SortIcon field="duration" />
                  </th>
                  <th className="col-stats">Stats</th>
                  <th className="col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {sortedJobs.map((job) => (
                  <Fragment key={job.id}>
                    <tr
                      className={`job-row ${job.status} ${expandedJobId === job.id ? 'expanded' : ''}`}
                      onClick={() => handleRowClick(job)}
                    >
                      <td className="col-expand">
                        {expandedJobId === job.id
                          ? <ChevronUp size={18} />
                          : <ChevronDown size={18} />}
                      </td>
                      <td className="col-status">
                        <div className="status-cell">
                          {getStatusIcon(job.status)}
                          <span className={`status-text ${job.status}`}>
                            {job.status}
                          </span>
                        </div>
                      </td>
                      <td className="col-repository">
                        <div className="repository-cell">
                          <FolderGit2 size={16} />
                          <span className="repo-name">{getRepositoryName(job)}</span>
                        </div>
                      </td>
                      <td className="col-progress">
                        <div className="progress-cell">
                          <div className="mini-progress-bar">
                            <div
                              className={`mini-progress-fill ${job.status}`}
                              style={{ width: `${job.status === 'completed' ? 100 : job.progressPct || 0}%` }}
                            />
                          </div>
                          <span className="progress-text">
                            {job.status === 'completed' ? '100' : job.progressPct || 0}%
                          </span>
                        </div>
                      </td>
                      <td className="col-phase">
                        <span className="phase-badge">
                          {job.currentPhase || (job.status === 'completed' ? 'Done' : '-')}
                        </span>
                      </td>
                      <td className="col-started">
                        <div className="time-cell">
                          <Calendar size={14} />
                          <span>{new Date(job.startedAt).toLocaleString()}</span>
                        </div>
                      </td>
                      <td className="col-duration">
                        <div className="time-cell">
                          <Timer size={14} />
                          <span>
                            {job.status === 'running' || job.status === 'pending'
                              ? formatDuration(job.startedAt)
                              : formatDuration(job.startedAt, job.completedAt)}
                          </span>
                        </div>
                      </td>
                      <td className="col-stats">
                        {job.stats ? (
                          <div className="stats-cell">
                            <span title="Files"><FileCode size={14} /> {formatNumber(job.stats.filesScanned || 0)}</span>
                            <span title="Nodes"><Database size={14} /> {formatNumber(job.stats.nodesCreated || 0)}</span>
                            <span title="Relationships"><Network size={14} /> {formatNumber(job.stats.relationshipsCreated || 0)}</span>
                          </div>
                        ) : (
                          <span className="no-stats">-</span>
                        )}
                      </td>
                      <td className="col-actions">
                        <div className="actions-cell">
                          {/* Resume button for paused/failed jobs */}
                          {(job.status === 'paused' || job.status === 'failed') && (
                            <button
                              className="action-btn resume"
                              onClick={(e) => handleResumeJob(e, job.id)}
                              disabled={actionLoading === job.id}
                              title="Resume analysis"
                            >
                              {actionLoading === job.id ? (
                                <Loader2 size={16} className="spinning" />
                              ) : (
                                <Play size={16} />
                              )}
                            </button>
                          )}
                          {/* Pause button for running jobs */}
                          {job.status === 'running' && (
                            <button
                              className="action-btn pause"
                              onClick={(e) => handlePauseJob(e, job.id)}
                              disabled={actionLoading === job.id}
                              title="Pause analysis"
                            >
                              {actionLoading === job.id ? (
                                <Loader2 size={16} className="spinning" />
                              ) : (
                                <Pause size={16} />
                              )}
                            </button>
                          )}
                          {/* Cancel button for running/paused/pending jobs */}
                          {(job.status === 'running' || job.status === 'pending' || job.status === 'paused') && (
                            <button
                              className="action-btn stop"
                              onClick={(e) => handleCancelJob(e, job.id)}
                              disabled={actionLoading === job.id}
                              title="Cancel analysis"
                            >
                              {actionLoading === job.id ? (
                                <Loader2 size={16} className="spinning" />
                              ) : (
                                <StopCircle size={16} />
                              )}
                            </button>
                          )}
                          <button
                            className="action-btn delete"
                            onClick={(e) => handleDeleteJob(e, job.id)}
                            disabled={actionLoading === job.id}
                            title="Delete job"
                          >
                            {actionLoading === job.id ? (
                              <Loader2 size={16} className="spinning" />
                            ) : (
                              <Trash2 size={16} />
                            )}
                          </button>
                        </div>
                      </td>
                    </tr>

                    {/* Expanded Row */}
                    {expandedJobId === job.id && (
                      <tr className="job-expanded-row">
                        <td colSpan={9}>
                          <div className="job-detail-panel">
                            {/* Stats Overview */}
                            <div className="detail-stats-grid">
                              <div className="detail-stat-card">
                                <div className="stat-icon files">
                                  <FileCode size={20} />
                                </div>
                                <div className="stat-content">
                                  <span className="stat-value">
                                    {formatNumber(streamingState.filesProcessed || job.stats?.filesScanned || 0)}
                                    {streamingState.totalFiles > 0 && (
                                      <span className="stat-total">/ {formatNumber(streamingState.totalFiles)}</span>
                                    )}
                                  </span>
                                  <span className="stat-label">Files Processed</span>
                                </div>
                              </div>
                              <div className="detail-stat-card">
                                <div className="stat-icon nodes">
                                  <Box size={20} />
                                </div>
                                <div className="stat-content">
                                  <span className="stat-value">
                                    {formatNumber(streamingState.nodesCreated || job.stats?.nodesCreated || 0)}
                                  </span>
                                  <span className="stat-label">Nodes Created</span>
                                </div>
                              </div>
                              <div className="detail-stat-card">
                                <div className="stat-icon relationships">
                                  <Network size={20} />
                                </div>
                                <div className="stat-content">
                                  <span className="stat-value">
                                    {formatNumber(streamingState.relationshipsCreated || job.stats?.relationshipsCreated || 0)}
                                  </span>
                                  <span className="stat-label">Relationships</span>
                                </div>
                              </div>
                              <div className="detail-stat-card">
                                <div className="stat-icon classes">
                                  <Code2 size={20} />
                                </div>
                                <div className="stat-content">
                                  <span className="stat-value">
                                    {job.stats?.classesFound ? formatNumber(job.stats.classesFound) : 'N/A'}
                                  </span>
                                  <span className="stat-label">Classes</span>
                                </div>
                              </div>
                              <div className="detail-stat-card">
                                <div className="stat-icon methods">
                                  <Layers size={20} />
                                </div>
                                <div className="stat-content">
                                  <span className="stat-value">
                                    {job.stats?.methodsFound ? formatNumber(job.stats.methodsFound) : 'N/A'}
                                  </span>
                                  <span className="stat-label">Methods</span>
                                </div>
                              </div>
                            </div>

                            {/* Progress Section */}
                            {(job.status === 'running' || job.status === 'pending') && (
                              <div className="detail-progress-section">
                                <div className="progress-header">
                                  <span className="progress-phase">
                                    <Loader2 size={16} className="spinning" />
                                    {streamingState.phase || job.currentPhase || 'Initializing...'}
                                  </span>
                                  <span className="progress-percentage">
                                    {streamingState.progress || job.progressPct || 0}%
                                  </span>
                                </div>
                                <div className="detail-progress-bar">
                                  <div
                                    className="detail-progress-fill"
                                    style={{ width: `${streamingState.progress || job.progressPct || 0}%` }}
                                  />
                                </div>
                                <div className="progress-stats">
                                  <span>
                                    {streamingState.filesProcessed || 0} / {streamingState.totalFiles || '?'} files
                                  </span>
                                  {streamingState.isConnected && (
                                    <span className="live-indicator">
                                      <span className="live-dot"></span>
                                      Live
                                    </span>
                                  )}
                                </div>
                              </div>
                            )}

                            {/* Error Display */}
                            {job.status === 'failed' && job.error && (
                              <div className="detail-error">
                                <XCircle size={18} />
                                <span>{job.error}</span>
                              </div>
                            )}

                            {/* Logs Terminal */}
                            <div className="detail-logs-section">
                              <div className="logs-header">
                                <Terminal size={16} />
                                <span>Analysis Logs</span>
                                {streamingState.isConnected && (
                                  <span className="streaming-badge">
                                    <span className="pulse"></span>
                                    Streaming
                                  </span>
                                )}
                                <button
                                  className="download-logs-btn"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    downloadJobLogs(job.id);
                                  }}
                                  title="Download all logs"
                                >
                                  <Download size={14} />
                                  Download
                                </button>
                              </div>
                              <div className="logs-terminal">
                                {streamingState.logs.length === 0 ? (
                                  <div className="logs-empty">
                                    {job.status === 'running' || job.status === 'pending'
                                      ? 'Waiting for logs...'
                                      : 'No logs available'}
                                  </div>
                                ) : (
                                  streamingState.logs.map((log, index) => (
                                    <div
                                      key={index}
                                      className={`log-entry ${
                                        log.startsWith('[ERROR]') ? 'error' :
                                        log.startsWith('[COMPLETE]') ? 'success' :
                                        log.startsWith('[PHASE]') ? 'phase' :
                                        'info'
                                      }`}
                                    >
                                      {log}
                                    </div>
                                  ))
                                )}
                                <div ref={logsEndRef} />
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
