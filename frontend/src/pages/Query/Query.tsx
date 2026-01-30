import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Header } from '../../components/Layout';
import { executeQuery } from '../../services/api';
import {
  Play,
  RefreshCw,
  Copy,
  Check,
  AlertCircle,
  Database,
  Code,
} from 'lucide-react';
import './Query.css';

const EXAMPLE_QUERIES = [
  {
    name: 'Get all repositories',
    query: 'MATCH (r:Repository) RETURN r.name, r.repositoryId, r.fileCount LIMIT 10',
  },
  {
    name: 'Get all classes',
    query: 'MATCH (c:Class) RETURN c.name, c.filePath LIMIT 20',
  },
  {
    name: 'Get functions by file',
    query: 'MATCH (f:File)-[:CONTAINS]->(fn:Function) RETURN f.name, fn.name LIMIT 20',
  },
  {
    name: 'Get class methods',
    query: 'MATCH (c:Class)-[:HAS_METHOD]->(m:Method) RETURN c.name, m.name LIMIT 20',
  },
  {
    name: 'Get imports',
    query: 'MATCH (f:File)-[:IMPORTS]->(i:Import) RETURN f.name, i.name LIMIT 20',
  },
  {
    name: 'Get call relationships',
    query: 'MATCH (caller:Function)-[:CALLS]->(callee:Function) RETURN caller.name, callee.name LIMIT 20',
  },
  {
    name: 'Count nodes by label',
    query: `CALL db.labels() YIELD label
CALL apoc.cypher.run('MATCH (n:\`' + label + '\`) RETURN count(n) as count', {}) YIELD value
RETURN label, value.count as count
ORDER BY count DESC`,
  },
  {
    name: 'Repository file count',
    query: `MATCH (r:Repository)<-[:BELONGS_TO]-(f:File)
RETURN r.name as repository, count(f) as fileCount`,
  },
];

export function Query() {
  const [query, setQuery] = useState('MATCH (n) RETURN labels(n) as label, count(n) as count LIMIT 10');
  const [copied, setCopied] = useState(false);

  const queryMutation = useMutation({
    mutationFn: (q: string) => executeQuery(q),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      queryMutation.mutate(query);
    }
  };

  const handleExampleClick = (exampleQuery: string) => {
    setQuery(exampleQuery);
  };

  const copyToClipboard = () => {
    if (queryMutation.data) {
      navigator.clipboard.writeText(JSON.stringify(queryMutation.data.records, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div>
      <Header
        title="Query Interface"
        subtitle="Execute Cypher queries against the Neo4j graph"
      />

      <div className="page-container">
        <div className="query-layout">
          {/* Query Editor */}
          <div className="query-editor">
            <form onSubmit={handleSubmit}>
              <div className="editor-header">
                <div className="editor-title">
                  <Code size={18} />
                  <span>Cypher Query</span>
                </div>
                <button
                  type="submit"
                  className="run-btn"
                  disabled={queryMutation.isPending || !query.trim()}
                >
                  {queryMutation.isPending ? (
                    <>
                      <RefreshCw size={16} className="spinning" />
                      Running...
                    </>
                  ) : (
                    <>
                      <Play size={16} />
                      Run Query
                    </>
                  )}
                </button>
              </div>
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Enter your Cypher query here..."
                className="query-textarea"
                rows={6}
              />
            </form>

            {/* Error */}
            {queryMutation.isError && (
              <div className="query-error">
                <AlertCircle size={18} />
                <span>{(queryMutation.error as Error)?.message || 'Query failed'}</span>
              </div>
            )}

            {/* Results */}
            {queryMutation.isSuccess && queryMutation.data && (
              <div className="query-results">
                <div className="results-header">
                  <span>
                    <Database size={16} />
                    {queryMutation.data.count} results
                  </span>
                  <button className="copy-btn" onClick={copyToClipboard}>
                    {copied ? <Check size={16} /> : <Copy size={16} />}
                    {copied ? 'Copied!' : 'Copy'}
                  </button>
                </div>
                <div className="results-table-container">
                  {queryMutation.data.records.length > 0 ? (
                    <table className="results-table">
                      <thead>
                        <tr>
                          {Object.keys(queryMutation.data.records[0]).map((key) => (
                            <th key={key}>{key}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {queryMutation.data.records.map((record, i) => (
                          <tr key={i}>
                            {Object.values(record).map((value, j) => (
                              <td key={j}>
                                {typeof value === 'object'
                                  ? JSON.stringify(value)
                                  : String(value ?? '')}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <p className="no-results">No results returned</p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Example Queries */}
          <div className="examples-panel">
            <h3>Example Queries</h3>
            <div className="examples-list">
              {EXAMPLE_QUERIES.map((example, i) => (
                <button
                  key={i}
                  className="example-btn"
                  onClick={() => handleExampleClick(example.query)}
                >
                  <span className="example-name">{example.name}</span>
                  <Code size={14} />
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
