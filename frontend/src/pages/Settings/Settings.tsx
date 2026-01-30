import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Header } from '../../components/Layout';
import { getConfig, applySchema, resetDatabase } from '../../services/api';
import {
  Settings as SettingsIcon,
  Database,
  FileCode,
  AlertTriangle,
  Check,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import './Settings.css';

export function Settings() {
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  const { data: config, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: getConfig,
  });

  const schemaMutation = useMutation({
    mutationFn: applySchema,
  });

  const resetMutation = useMutation({
    mutationFn: resetDatabase,
    onSuccess: () => {
      setShowResetConfirm(false);
    },
  });

  return (
    <div>
      <Header
        title="Settings"
        subtitle="Configure CodeGraph settings and manage the database"
      />

      <div className="page-container">
        <div className="settings-grid">
          {/* Database Connection */}
          <div className="settings-card">
            <div className="card-header">
              <Database size={18} />
              <h2>Database Connection</h2>
            </div>
            <div className="card-content">
              {isLoading ? (
                <p className="loading">Loading configuration...</p>
              ) : (
                <div className="config-list">
                  <div className="config-item">
                    <span className="config-label">Neo4j URL</span>
                    <span className="config-value">{config?.neo4jUrl || 'Not configured'}</span>
                  </div>
                  <div className="config-item">
                    <span className="config-label">Database</span>
                    <span className="config-value">{config?.neo4jDatabase || 'neo4j'}</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Supported Extensions */}
          <div className="settings-card">
            <div className="card-header">
              <FileCode size={18} />
              <h2>Supported Extensions</h2>
            </div>
            <div className="card-content">
              {isLoading ? (
                <p className="loading">Loading configuration...</p>
              ) : (
                <div className="extensions-grid">
                  {config?.supportedExtensions?.map((ext) => (
                    <span key={ext} className="extension-badge">
                      {ext}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Schema Management */}
          <div className="settings-card">
            <div className="card-header">
              <SettingsIcon size={18} />
              <h2>Schema Management</h2>
            </div>
            <div className="card-content">
              <p className="card-description">
                Apply Neo4j schema constraints and indexes to optimize query performance.
              </p>
              <button
                className="action-btn"
                onClick={() => schemaMutation.mutate()}
                disabled={schemaMutation.isPending}
              >
                {schemaMutation.isPending ? (
                  <>
                    <RefreshCw size={16} className="spinning" />
                    Applying Schema...
                  </>
                ) : schemaMutation.isSuccess ? (
                  <>
                    <Check size={16} />
                    Schema Applied
                  </>
                ) : (
                  <>
                    <Database size={16} />
                    Apply Schema
                  </>
                )}
              </button>
              {schemaMutation.isError && (
                <p className="error-text">
                  {(schemaMutation.error as Error)?.message || 'Failed to apply schema'}
                </p>
              )}
            </div>
          </div>

          {/* Danger Zone */}
          <div className="settings-card danger">
            <div className="card-header">
              <AlertTriangle size={18} />
              <h2>Danger Zone</h2>
            </div>
            <div className="card-content">
              <p className="card-description warning">
                These actions are irreversible. Please proceed with caution.
              </p>

              {!showResetConfirm ? (
                <button
                  className="action-btn danger"
                  onClick={() => setShowResetConfirm(true)}
                >
                  <Trash2 size={16} />
                  Reset Database
                </button>
              ) : (
                <div className="confirm-dialog">
                  <p>Are you sure? This will delete ALL nodes and relationships.</p>
                  <div className="confirm-actions">
                    <button
                      className="action-btn danger"
                      onClick={() => resetMutation.mutate()}
                      disabled={resetMutation.isPending}
                    >
                      {resetMutation.isPending ? (
                        <>
                          <RefreshCw size={16} className="spinning" />
                          Resetting...
                        </>
                      ) : (
                        'Yes, Reset Database'
                      )}
                    </button>
                    <button
                      className="action-btn secondary"
                      onClick={() => setShowResetConfirm(false)}
                      disabled={resetMutation.isPending}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {resetMutation.isSuccess && (
                <p className="success-text">Database reset successfully</p>
              )}
              {resetMutation.isError && (
                <p className="error-text">
                  {(resetMutation.error as Error)?.message || 'Failed to reset database'}
                </p>
              )}
            </div>
          </div>

          {/* Ignore Patterns */}
          <div className="settings-card full-width">
            <div className="card-header">
              <FileCode size={18} />
              <h2>Ignore Patterns</h2>
            </div>
            <div className="card-content">
              {isLoading ? (
                <p className="loading">Loading configuration...</p>
              ) : (
                <div className="patterns-list">
                  {config?.ignorePatterns?.map((pattern, i) => (
                    <code key={i} className="pattern-item">
                      {pattern}
                    </code>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
