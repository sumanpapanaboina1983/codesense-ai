import { useQuery } from '@tanstack/react-query';
import { Header } from '../../components/Layout';
import { getGraphStats } from '../../services/api';
import { useAppStore } from '../../store/appStore';
import {
  Database,
  GitBranch,
  RefreshCw,
  PieChart,
  BarChart3,
} from 'lucide-react';
import './Graph.css';

export function Graph() {
  const { graphStats, setGraphStats } = useAppStore();

  const { isLoading, refetch, isFetching } = useQuery({
    queryKey: ['graphStats'],
    queryFn: async () => {
      const data = await getGraphStats();
      setGraphStats(data);
      return data;
    },
    refetchInterval: 10000,
  });

  const nodeEntries = graphStats?.nodesByLabel
    ? Object.entries(graphStats.nodesByLabel).sort((a, b) => b[1] - a[1])
    : [];

  const relEntries = graphStats?.relationshipsByType
    ? Object.entries(graphStats.relationshipsByType).sort((a, b) => b[1] - a[1])
    : [];

  const maxNodeCount = nodeEntries.length > 0 ? nodeEntries[0][1] : 0;
  const maxRelCount = relEntries.length > 0 ? relEntries[0][1] : 0;

  return (
    <div>
      <Header
        title="Graph Explorer"
        subtitle="Explore the code graph statistics"
      />

      <div className="page-container">
        <div className="graph-header">
          <div className="stats-summary">
            <div className="summary-item">
              <Database size={20} />
              <span className="summary-value">
                {isLoading ? '...' : graphStats?.totalNodes?.toLocaleString() || 0}
              </span>
              <span className="summary-label">Total Nodes</span>
            </div>
            <div className="summary-item">
              <GitBranch size={20} />
              <span className="summary-value">
                {isLoading ? '...' : graphStats?.totalRelationships?.toLocaleString() || 0}
              </span>
              <span className="summary-label">Total Relationships</span>
            </div>
          </div>
          <button
            className="refresh-btn"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw size={16} className={isFetching ? 'spinning' : ''} />
            Refresh Stats
          </button>
        </div>

        <div className="graph-grid">
          {/* Node Distribution */}
          <div className="graph-card">
            <div className="card-header">
              <PieChart size={18} />
              <h2>Node Distribution</h2>
            </div>
            <div className="card-content">
              {nodeEntries.length === 0 ? (
                <div className="empty-state">
                  <p>No nodes in the graph</p>
                </div>
              ) : (
                <div className="distribution-list">
                  {nodeEntries.map(([label, count]) => (
                    <div key={label} className="distribution-item">
                      <div className="dist-header">
                        <span className="dist-label">{label}</span>
                        <span className="dist-count">{count.toLocaleString()}</span>
                      </div>
                      <div className="dist-bar">
                        <div
                          className="dist-fill node-fill"
                          style={{ width: `${(count / maxNodeCount) * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Relationship Distribution */}
          <div className="graph-card">
            <div className="card-header">
              <BarChart3 size={18} />
              <h2>Relationship Distribution</h2>
            </div>
            <div className="card-content">
              {relEntries.length === 0 ? (
                <div className="empty-state">
                  <p>No relationships in the graph</p>
                </div>
              ) : (
                <div className="distribution-list">
                  {relEntries.map(([type, count]) => (
                    <div key={type} className="distribution-item">
                      <div className="dist-header">
                        <span className="dist-label">{type}</span>
                        <span className="dist-count">{count.toLocaleString()}</span>
                      </div>
                      <div className="dist-bar">
                        <div
                          className="dist-fill rel-fill"
                          style={{ width: `${(count / maxRelCount) * 100}%` }}
                        />
                      </div>
                    </div>
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
