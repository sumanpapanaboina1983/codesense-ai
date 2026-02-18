import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Header } from '../../components/Layout';
import {
  ArrowLeft,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  RefreshCw,
  Play,
  Square,
  FileCode,
  Database,
  GitBranch,
  Terminal,
  Calendar,
  Timer,
  AlertCircle,
  Info,
  AlertTriangle,
  Download,
} from 'lucide-react';
import { getJobDetail, resumeJob, cancelJob, streamJobProgress, getJobLogs } from '../../services/api';
import type { JobDetail as JobDetailType, JobLog, JobProgressEvent } from '../../services/api';
import './JobDetail.css';

// Phase order for timeline
const PHASES = [
  { key: 'pending', label: 'Pending' },
  { key: 'cloning', label: 'Cloning' },
  { key: 'indexing_files', label: 'Indexing Files' },
  { key: 'parsing_code', label: 'Parsing Code' },
  { key: 'building_graph', label: 'Building Graph' },
  { key: 'completed', label: 'Completed' },
];

const getPhaseIndex = (phase: string): number => {
  const index = PHASES.findIndex((p) => p.key === phase);
  return index >= 0 ? index : 0;
};

export function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  const [job, setJob] = useState<JobDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [logs, setLogs] = useState<JobLog[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [downloadingLogs, setDownloadingLogs] = useState(false);

  const logsEndRef = useRef<HTMLDivElement>(null);
  const cleanupRef = useRef<(() => void) | null>(null);

  // Fetch job details
  const fetchJob = async () => {
    if (!jobId) return;

    try {
      const data = await getJobDetail(jobId);
      setJob(data.job);
      setLogs(data.job.recent_logs || []);
      setError(null);

      // Start streaming if job is running
      if (data.job.status === 'running' || data.job.status === 'pending') {
        startStreaming();
      }
    } catch (err) {
      setError('Failed to load job details');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Start SSE streaming
  const startStreaming = () => {
    if (!jobId || isStreaming) return;

    setIsStreaming(true);

    cleanupRef.current = streamJobProgress(
      jobId,
      (event: JobProgressEvent) => {
        if (event.type === 'complete') {
          setIsStreaming(false);
          fetchJob(); // Refresh to get final stats
        } else if (event.type === 'error') {
          setIsStreaming(false);
          if (event.error) {
            setError(event.error);
          }
          fetchJob();
        } else if (event.type === 'progress' || event.type === 'phase') {
          setJob((prev) =>
            prev
              ? {
                  ...prev,
                  current_phase: event.phase || prev.current_phase,
                  progress_pct: event.progress_pct,
                  status: event.status || prev.status,
                }
              : null
          );
        }
      },
      (err) => {
        console.error('Stream error:', err);
        setIsStreaming(false);
      }
    );
  };

  useEffect(() => {
    fetchJob();

    return () => {
      if (cleanupRef.current) {
        cleanupRef.current();
      }
    };
  }, [jobId]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const handleResume = async () => {
    if (!jobId) return;

    setActionLoading(true);
    try {
      await resumeJob(jobId);
      await fetchJob();
    } catch (err) {
      console.error('Failed to resume job:', err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!jobId || !confirm('Are you sure you want to cancel this job?')) return;

    setActionLoading(true);
    try {
      await cancelJob(jobId);
      await fetchJob();
    } catch (err) {
      console.error('Failed to cancel job:', err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDownloadLogs = async () => {
    if (!jobId || !job) return;

    setDownloadingLogs(true);
    try {
      // Fetch all logs (up to 1000)
      const allLogs = await getJobLogs(jobId, { limit: 1000 });

      // Format logs as text
      const logContent = allLogs
        .map((log) => {
          const timestamp = new Date(log.created_at).toISOString();
          return `[${timestamp}] [${log.level.toUpperCase()}] [${log.phase}] ${log.message}`;
        })
        .join('\n');

      // Create and download file
      const blob = new Blob([logContent], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `analysis-logs-${job.repository_name || jobId}-${new Date().toISOString().split('T')[0]}.txt`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to download logs:', err);
    } finally {
      setDownloadingLogs(false);
    }
  };

  const formatDuration = (seconds: number): string => {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  };

  const getLogIcon = (level: string) => {
    switch (level) {
      case 'error':
        return <AlertCircle size={14} className="log-icon error" />;
      case 'warning':
        return <AlertTriangle size={14} className="log-icon warning" />;
      default:
        return <Info size={14} className="log-icon info" />;
    }
  };

  if (loading) {
    return (
      <div>
        <Header title="Job Details" />
        <div className="page-container">
          <div className="loading-state">
            <Loader2 size={32} className="spinning" />
            <p>Loading job details...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error || !job) {
    return (
      <div>
        <Header title="Job Details" />
        <div className="page-container">
          <div className="error-state">
            <XCircle size={48} />
            <h3>Error Loading Job</h3>
            <p>{error || 'Job not found'}</p>
            <button className="btn btn-primary" onClick={() => navigate('/jobs')}>
              <ArrowLeft size={16} />
              Back to Jobs
            </button>
          </div>
        </div>
      </div>
    );
  }

  const currentPhaseIndex = getPhaseIndex(job.current_phase || 'pending');
  const isFailed = job.status === 'failed';
  const isCompleted = job.status === 'completed';
  const isRunning = job.status === 'running' || job.status === 'pending';

  return (
    <div>
      <Header
        title={`Analysis Job`}
        subtitle={job.repository_name || job.repository_id}
      />

      <div className="page-container">
        {/* Back button */}
        <button className="back-btn" onClick={() => navigate('/jobs')}>
          <ArrowLeft size={16} />
          Back to Jobs
        </button>

        {/* Job header with status and actions */}
        <div className="job-detail-header">
          <div className="job-detail-info">
            <div className={`job-status-large ${job.status}`}>
              {isCompleted && <CheckCircle size={24} />}
              {isFailed && <XCircle size={24} />}
              {isRunning && <Loader2 size={24} className="spinning" />}
              <span>{job.status.toUpperCase()}</span>
            </div>

            <div className="job-meta-row">
              <div className="meta-item">
                <Calendar size={16} />
                <span>Started: {new Date(job.created_at).toLocaleString()}</span>
              </div>
              {job.duration_seconds && (
                <div className="meta-item">
                  <Timer size={16} />
                  <span>Duration: {formatDuration(job.duration_seconds)}</span>
                </div>
              )}
              <div className="meta-item">
                <GitBranch size={16} />
                <span>Branch: {job.branch || 'main'}</span>
              </div>
            </div>
          </div>

          <div className="job-detail-actions">
            {job.can_resume && (
              <button
                className="btn btn-primary"
                onClick={handleResume}
                disabled={actionLoading}
              >
                {actionLoading ? <Loader2 size={16} className="spinning" /> : <Play size={16} />}
                Resume
              </button>
            )}
            {job.can_cancel && (
              <button
                className="btn btn-danger"
                onClick={handleCancel}
                disabled={actionLoading}
              >
                {actionLoading ? <Loader2 size={16} className="spinning" /> : <Square size={16} />}
                Cancel
              </button>
            )}
            <button
              className="btn btn-outline"
              onClick={fetchJob}
              disabled={loading}
            >
              <RefreshCw size={16} className={loading ? 'spinning' : ''} />
              Refresh
            </button>
          </div>
        </div>

        {/* Phase timeline */}
        <div className="phase-timeline">
          <h3>Analysis Phases</h3>
          <div className="timeline">
            {PHASES.map((phase, index) => {
              const isActive = index === currentPhaseIndex && isRunning;
              const isComplete = index < currentPhaseIndex || isCompleted;
              const isFuture = index > currentPhaseIndex;
              const isFailedPhase = isFailed && index === currentPhaseIndex;

              return (
                <div
                  key={phase.key}
                  className={`timeline-item ${isActive ? 'active' : ''} ${isComplete ? 'complete' : ''} ${isFuture ? 'future' : ''} ${isFailedPhase ? 'failed' : ''}`}
                >
                  <div className="timeline-dot">
                    {isComplete && <CheckCircle size={16} />}
                    {isActive && <Loader2 size={16} className="spinning" />}
                    {isFailedPhase && <XCircle size={16} />}
                    {isFuture && <Clock size={16} />}
                  </div>
                  <div className="timeline-label">{phase.label}</div>
                  {index < PHASES.length - 1 && <div className="timeline-connector" />}
                </div>
              );
            })}
          </div>
        </div>

        {/* Progress section for running jobs */}
        {isRunning && (
          <div className="progress-section">
            <h3>Current Progress</h3>
            <div className="progress-details">
              <div className="progress-stat">
                <span className="stat-label">Phase</span>
                <span className="stat-value">{job.current_phase || 'Initializing'}</span>
              </div>
              <div className="progress-stat">
                <span className="stat-label">Progress</span>
                <span className="stat-value">{job.progress_pct || 0}%</span>
              </div>
            </div>
            <div className="progress-bar-large">
              <div
                className="progress-fill"
                style={{ width: `${job.progress_pct || 0}%` }}
              />
            </div>
            {isStreaming && (
              <div className="streaming-indicator">
                <Loader2 size={14} className="spinning" />
                <span>Live updates active</span>
              </div>
            )}
          </div>
        )}

        {/* Error message for failed jobs */}
        {isFailed && job.error && (
          <div className="error-section">
            <h3>
              <XCircle size={20} />
              Error Details
            </h3>
            <div className="error-message">{job.error}</div>
          </div>
        )}

        {/* Stats for completed jobs */}
        {isCompleted && job.stats && (
          <div className="stats-section">
            <h3>Analysis Results</h3>
            <div className="stats-grid">
              <div className="stat-card">
                <FileCode size={24} />
                <div className="stat-content">
                  <span className="stat-value">{job.stats.filesScanned || 0}</span>
                  <span className="stat-label">Files Scanned</span>
                </div>
              </div>
              <div className="stat-card">
                <Database size={24} />
                <div className="stat-content">
                  <span className="stat-value">{job.stats.nodesCreated || 0}</span>
                  <span className="stat-label">Nodes Created</span>
                </div>
              </div>
              <div className="stat-card">
                <GitBranch size={24} />
                <div className="stat-content">
                  <span className="stat-value">{job.stats.relationshipsCreated || 0}</span>
                  <span className="stat-label">Relationships</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Logs terminal */}
        <div className="logs-section">
          <div className="logs-header">
            <h3>
              <Terminal size={20} />
              Analysis Logs
            </h3>
            <button
              className="btn btn-outline btn-sm"
              onClick={handleDownloadLogs}
              disabled={downloadingLogs || logs.length === 0}
              title="Download complete logs"
            >
              {downloadingLogs ? (
                <Loader2 size={14} className="spinning" />
              ) : (
                <Download size={14} />
              )}
              Download Logs
            </button>
          </div>
          <div className="logs-terminal">
            {logs.length === 0 ? (
              <div className="logs-empty">No logs available</div>
            ) : (
              <>
                {logs.map((log) => (
                  <div key={log.id} className={`log-entry ${log.level}`}>
                    <span className="log-time">
                      {new Date(log.created_at).toLocaleTimeString()}
                    </span>
                    {getLogIcon(log.level)}
                    <span className="log-phase">[{log.phase}]</span>
                    <span className="log-message">{log.message}</span>
                  </div>
                ))}
                <div ref={logsEndRef} />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
