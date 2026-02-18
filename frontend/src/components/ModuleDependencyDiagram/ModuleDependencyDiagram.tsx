import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
  BackgroundVariant,
  Handle,
} from '@xyflow/react';
import type { Node, Edge } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Box, Code, FileCode, GitBranch, X } from 'lucide-react';
import type { ModuleInfo, ModuleDependencyEdge } from '../../types/api';
import './ModuleDependencyDiagram.css';

// Extended module data type with selection state and index signature for React Flow compatibility
interface ModuleNodeData extends Record<string, unknown> {
  name: string;
  path: string;
  fileCount: number;
  classCount: number;
  functionCount: number;
  totalLoc: number;
  avgComplexity?: number | null;
  maxComplexity?: number | null;
  dependencies: string[];
  dependents: string[];
  selected?: boolean;
}

interface ModuleDependencyDiagramProps {
  modules: ModuleInfo[];
  dependencyGraph: ModuleDependencyEdge[];
  onModuleSelect?: (module: ModuleInfo | null) => void;
}

// Custom node component for modules
function ModuleNodeComponent({ data }: { data: ModuleNodeData }) {
  return (
    <div className={`module-node ${data.selected ? 'selected' : ''}`}>
      {/* Top handle for incoming edges (dependencies point to this module) */}
      <Handle
        type="target"
        position={Position.Top}
        style={{ background: 'var(--color-primary)', width: 8, height: 8 }}
      />

      <div className="module-node-header">
        <Box size={14} />
        <span className="module-node-name">{data.name}</span>
      </div>
      <div className="module-node-stats">
        <div className="module-node-stat">
          <FileCode size={12} />
          <span>{data.fileCount} files</span>
        </div>
        <div className="module-node-stat">
          <Code size={12} />
          <span>{data.totalLoc.toLocaleString()} LOC</span>
        </div>
      </div>

      {/* Bottom handle for outgoing edges (this module depends on others) */}
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: 'var(--color-primary)', width: 8, height: 8 }}
      />
    </div>
  );
}

// Node types for React Flow
const nodeTypes = {
  moduleNode: ModuleNodeComponent,
};

// Type alias for module node
type ModuleFlowNode = Node<ModuleNodeData>;

// Layout modules in a hierarchical pattern using Sugiyama-style layout
function layoutModules(
  modules: ModuleInfo[],
  edges: ModuleDependencyEdge[]
): { nodes: ModuleFlowNode[]; edges: Edge[] } {
  if (modules.length === 0) {
    return { nodes: [], edges: [] };
  }

  // Build adjacency maps
  const outgoingEdges = new Map<string, string[]>();
  const incomingEdges = new Map<string, string[]>();

  modules.forEach((m) => {
    outgoingEdges.set(m.name, []);
    incomingEdges.set(m.name, []);
  });

  edges.forEach((e) => {
    const out = outgoingEdges.get(e.source);
    const inc = incomingEdges.get(e.target);
    if (out) out.push(e.target);
    if (inc) inc.push(e.source);
  });

  // Assign levels using topological sort
  const levels = new Map<string, number>();
  const visited = new Set<string>();

  function assignLevel(moduleName: string): number {
    if (levels.has(moduleName)) return levels.get(moduleName)!;
    if (visited.has(moduleName)) return 0; // Cycle detected
    visited.add(moduleName);

    const deps = outgoingEdges.get(moduleName) || [];
    let maxDepLevel = -1;
    deps.forEach((dep) => {
      const depLevel = assignLevel(dep);
      if (depLevel > maxDepLevel) maxDepLevel = depLevel;
    });

    const level = maxDepLevel + 1;
    levels.set(moduleName, level);
    return level;
  }

  modules.forEach((m) => assignLevel(m.name));

  // Group modules by level
  const levelGroups = new Map<number, ModuleInfo[]>();
  modules.forEach((m) => {
    const level = levels.get(m.name) || 0;
    if (!levelGroups.has(level)) levelGroups.set(level, []);
    levelGroups.get(level)!.push(m);
  });

  // Position nodes
  const NODE_WIDTH = 180;
  const NODE_HEIGHT = 80;
  const HORIZONTAL_GAP = 80;
  const VERTICAL_GAP = 120;

  const sortedLevels = Array.from(levelGroups.keys()).sort((a, b) => b - a);
  const maxLevelModules = Math.max(
    ...Array.from(levelGroups.values()).map((g) => g.length)
  );
  const totalWidth = maxLevelModules * (NODE_WIDTH + HORIZONTAL_GAP);

  const nodes: ModuleFlowNode[] = [];

  sortedLevels.forEach((level, levelIndex) => {
    const modulesAtLevel = levelGroups.get(level)!;
    const levelWidth = modulesAtLevel.length * (NODE_WIDTH + HORIZONTAL_GAP);
    const startX = (totalWidth - levelWidth) / 2;

    modulesAtLevel.forEach((module, moduleIndex) => {
      nodes.push({
        id: module.name,
        type: 'moduleNode',
        position: {
          x: startX + moduleIndex * (NODE_WIDTH + HORIZONTAL_GAP),
          y: levelIndex * (NODE_HEIGHT + VERTICAL_GAP),
        },
        data: { ...module, selected: false },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
      });
    });
  });

  // Create edges
  const flowEdges: Edge[] = edges.map((e, index) => ({
    id: `edge-${index}`,
    source: e.source,
    target: e.target,
    type: 'smoothstep',
    animated: false,
    style: { stroke: 'var(--color-primary)', strokeWidth: 2 },
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: 'var(--color-primary)',
    },
  }));

  return { nodes, edges: flowEdges };
}

export function ModuleDependencyDiagram({
  modules,
  dependencyGraph,
  onModuleSelect,
}: ModuleDependencyDiagramProps) {
  const [selectedModule, setSelectedModule] = useState<ModuleInfo | null>(null);

  // Layout the graph
  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => layoutModules(modules, dependencyGraph),
    [modules, dependencyGraph]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes when layout changes
  useEffect(() => {
    const { nodes: newNodes, edges: newEdges } = layoutModules(
      modules,
      dependencyGraph
    );
    setNodes(newNodes);
    setEdges(newEdges);
  }, [modules, dependencyGraph, setNodes, setEdges]);

  // Handle node click
  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      const module = modules.find((m) => m.name === node.id);
      if (module) {
        setSelectedModule(module);
        onModuleSelect?.(module);

        // Highlight selected node
        setNodes((nds) =>
          nds.map((n) => ({
            ...n,
            data: {
              ...n.data,
              selected: n.id === node.id,
            },
          }))
        );
      }
    },
    [modules, onModuleSelect, setNodes]
  );

  // Close module detail panel
  const closeDetail = useCallback(() => {
    setSelectedModule(null);
    onModuleSelect?.(null);
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: { ...n.data, selected: false },
      }))
    );
  }, [onModuleSelect, setNodes]);

  if (modules.length === 0) {
    return (
      <div className="diagram-empty-state">
        <GitBranch size={48} />
        <h4>No Modules Found</h4>
        <p>This repository doesn't have module information available.</p>
      </div>
    );
  }

  return (
    <div className="module-dependency-diagram">
      <div className="diagram-container">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.3}
          maxZoom={1.5}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
          <Controls showInteractive={false} />
        </ReactFlow>

        {/* Legend */}
        <div className="diagram-legend">
          <div className="legend-item">
            <div
              className="legend-line"
              style={{ background: 'var(--color-primary)' }}
            />
            <span>Depends on</span>
          </div>
        </div>
      </div>

      {/* Module Detail Panel */}
      {selectedModule && (
        <div className="module-detail-panel">
          <div className="panel-header">
            <h4>{selectedModule.name}</h4>
            <button className="close-btn" onClick={closeDetail}>
              <X size={16} />
            </button>
          </div>
          <div className="panel-content">
            <div className="panel-path">{selectedModule.path}</div>

            <div className="panel-stats">
              <div className="panel-stat">
                <span className="stat-value">{selectedModule.fileCount}</span>
                <span className="stat-label">Files</span>
              </div>
              <div className="panel-stat">
                <span className="stat-value">{selectedModule.classCount}</span>
                <span className="stat-label">Classes</span>
              </div>
              <div className="panel-stat">
                <span className="stat-value">
                  {selectedModule.functionCount}
                </span>
                <span className="stat-label">Functions</span>
              </div>
              <div className="panel-stat">
                <span className="stat-value">
                  {selectedModule.totalLoc.toLocaleString()}
                </span>
                <span className="stat-label">LOC</span>
              </div>
            </div>

            {selectedModule.avgComplexity && (
              <div className="panel-complexity">
                <div className="complexity-item">
                  <span className="complexity-label">Avg Complexity:</span>
                  <span className="complexity-value">
                    {selectedModule.avgComplexity.toFixed(1)}
                  </span>
                </div>
                {selectedModule.maxComplexity && (
                  <div className="complexity-item">
                    <span className="complexity-label">Max Complexity:</span>
                    <span className="complexity-value">
                      {selectedModule.maxComplexity}
                    </span>
                  </div>
                )}
              </div>
            )}

            {selectedModule.dependencies.length > 0 && (
              <div className="panel-dependencies">
                <h5>Dependencies ({selectedModule.dependencies.length})</h5>
                <div className="dependency-tags">
                  {selectedModule.dependencies.map((dep) => (
                    <span key={dep} className="dependency-tag outgoing">
                      {dep}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {selectedModule.dependents.length > 0 && (
              <div className="panel-dependencies">
                <h5>Dependents ({selectedModule.dependents.length})</h5>
                <div className="dependency-tags">
                  {selectedModule.dependents.map((dep) => (
                    <span key={dep} className="dependency-tag incoming">
                      {dep}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default ModuleDependencyDiagram;
