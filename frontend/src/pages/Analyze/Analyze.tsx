import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Header } from '../../components/Layout';
import { startAnalysis } from '../../services/api';
import { useAppStore } from '../../store/appStore';
import { useNavigate } from 'react-router-dom';
import {
  FolderGit2,
  Globe,
  Folder,
  GitBranch,
  Key,
  Database,
  RefreshCw,
  Play,
  AlertCircle,
  CheckCircle,
} from 'lucide-react';
import './Analyze.css';

type InputType = 'gitUrl' | 'localPath';

export function Analyze() {
  const navigate = useNavigate();
  const { addJob } = useAppStore();

  const [inputType, setInputType] = useState<InputType>('gitUrl');
  const [gitUrl, setGitUrl] = useState('');
  const [localPath, setLocalPath] = useState('');
  const [branch, setBranch] = useState('');
  const [gitToken, setGitToken] = useState('');
  const [repositoryName, setRepositoryName] = useState('');
  const [updateSchema, setUpdateSchema] = useState(true);
  const [resetDb, setResetDb] = useState(false);
  const [keepClone, setKeepClone] = useState(false);

  const analyzeMutation = useMutation({
    mutationFn: startAnalysis,
    onSuccess: (data) => {
      // Add a placeholder job to show in UI immediately
      addJob({
        id: data.jobId,
        status: 'pending',
        directory: inputType === 'gitUrl' ? 'Cloning...' : localPath,
        gitUrl: inputType === 'gitUrl' ? gitUrl : undefined,
        startedAt: new Date().toISOString(),
      });
      // Navigate to jobs page
      navigate('/jobs');
    },
  });

  const generateRepositoryId = () => {
    return crypto.randomUUID();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const request: any = {
      repositoryId: generateRepositoryId(),
      repositoryName: repositoryName || extractRepoName(),
      updateSchema,
      resetDb,
    };

    if (inputType === 'gitUrl') {
      request.gitUrl = gitUrl;
      request.repositoryUrl = gitUrl;
      if (branch) request.branch = branch;
      if (gitToken) request.gitToken = gitToken;
      request.keepClone = keepClone;
    } else {
      request.directory = localPath;
    }

    analyzeMutation.mutate(request);
  };

  const extractRepoName = () => {
    if (inputType === 'gitUrl' && gitUrl) {
      const match = gitUrl.match(/\/([^\/]+?)(\.git)?$/);
      return match ? match[1] : 'repository';
    }
    if (inputType === 'localPath' && localPath) {
      return localPath.split('/').pop() || 'repository';
    }
    return 'repository';
  };

  const isFormValid = () => {
    if (inputType === 'gitUrl') {
      return gitUrl.trim().length > 0;
    }
    return localPath.trim().length > 0;
  };

  return (
    <div>
      <Header
        title="Analyze Repository"
        subtitle="Analyze a codebase from GitHub URL or local directory"
      />

      <div className="page-container">
        <div className="analyze-container">
          {/* Input Type Selector */}
          <div className="input-type-selector">
            <button
              className={`type-btn ${inputType === 'gitUrl' ? 'active' : ''}`}
              onClick={() => setInputType('gitUrl')}
            >
              <Globe size={20} />
              <span>Git URL</span>
            </button>
            <button
              className={`type-btn ${inputType === 'localPath' ? 'active' : ''}`}
              onClick={() => setInputType('localPath')}
            >
              <Folder size={20} />
              <span>Local Path</span>
            </button>
          </div>

          {/* Analysis Form */}
          <form onSubmit={handleSubmit} className="analyze-form">
            {/* Git URL Input */}
            {inputType === 'gitUrl' && (
              <div className="form-section">
                <h3>Repository URL</h3>
                <div className="form-group">
                  <label htmlFor="gitUrl">
                    <FolderGit2 size={16} />
                    Git URL
                  </label>
                  <input
                    id="gitUrl"
                    type="url"
                    placeholder="https://github.com/owner/repository"
                    value={gitUrl}
                    onChange={(e) => setGitUrl(e.target.value)}
                    required
                  />
                  <span className="form-hint">
                    Supports GitHub, GitLab, and Bitbucket URLs
                  </span>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="branch">
                      <GitBranch size={16} />
                      Branch (optional)
                    </label>
                    <input
                      id="branch"
                      type="text"
                      placeholder="main"
                      value={branch}
                      onChange={(e) => setBranch(e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="gitToken">
                      <Key size={16} />
                      Access Token (optional)
                    </label>
                    <input
                      id="gitToken"
                      type="password"
                      placeholder="For private repositories"
                      value={gitToken}
                      onChange={(e) => setGitToken(e.target.value)}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Local Path Input */}
            {inputType === 'localPath' && (
              <div className="form-section">
                <h3>Local Directory</h3>
                <div className="form-group">
                  <label htmlFor="localPath">
                    <Folder size={16} />
                    Directory Path
                  </label>
                  <input
                    id="localPath"
                    type="text"
                    placeholder="/path/to/your/project"
                    value={localPath}
                    onChange={(e) => setLocalPath(e.target.value)}
                    required
                  />
                  <span className="form-hint">
                    Absolute path to the project directory on the server
                  </span>
                </div>
              </div>
            )}

            {/* Repository Name */}
            <div className="form-section">
              <h3>Repository Details</h3>
              <div className="form-group">
                <label htmlFor="repoName">
                  <Database size={16} />
                  Repository Name (optional)
                </label>
                <input
                  id="repoName"
                  type="text"
                  placeholder={extractRepoName()}
                  value={repositoryName}
                  onChange={(e) => setRepositoryName(e.target.value)}
                />
                <span className="form-hint">
                  Display name for the repository in the graph
                </span>
              </div>
            </div>

            {/* Options */}
            <div className="form-section">
              <h3>Analysis Options</h3>
              <div className="options-grid">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={updateSchema}
                    onChange={(e) => setUpdateSchema(e.target.checked)}
                  />
                  <span className="checkbox-custom"></span>
                  <div className="checkbox-content">
                    <span className="checkbox-title">Update Schema</span>
                    <span className="checkbox-desc">Apply Neo4j constraints and indexes</span>
                  </div>
                </label>

                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={resetDb}
                    onChange={(e) => setResetDb(e.target.checked)}
                  />
                  <span className="checkbox-custom"></span>
                  <div className="checkbox-content">
                    <span className="checkbox-title">Reset Database</span>
                    <span className="checkbox-desc warning">Delete all existing nodes first</span>
                  </div>
                </label>

                {inputType === 'gitUrl' && (
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={keepClone}
                      onChange={(e) => setKeepClone(e.target.checked)}
                    />
                    <span className="checkbox-custom"></span>
                    <div className="checkbox-content">
                      <span className="checkbox-title">Keep Clone</span>
                      <span className="checkbox-desc">Don't delete cloned repo after analysis</span>
                    </div>
                  </label>
                )}
              </div>
            </div>

            {/* Error Message */}
            {analyzeMutation.isError && (
              <div className="error-message">
                <AlertCircle size={20} />
                <span>{(analyzeMutation.error as Error)?.message || 'Analysis failed'}</span>
              </div>
            )}

            {/* Success Message */}
            {analyzeMutation.isSuccess && (
              <div className="success-message">
                <CheckCircle size={20} />
                <span>Analysis started successfully!</span>
              </div>
            )}

            {/* Submit Button */}
            <div className="form-actions">
              <button
                type="submit"
                className="btn btn-primary btn-lg"
                disabled={!isFormValid() || analyzeMutation.isPending}
              >
                {analyzeMutation.isPending ? (
                  <>
                    <RefreshCw size={20} className="spinning" />
                    Starting Analysis...
                  </>
                ) : (
                  <>
                    <Play size={20} />
                    Start Analysis
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
