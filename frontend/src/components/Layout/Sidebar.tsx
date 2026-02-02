import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Activity,
  MessageSquare,
  FileText,
  Layers,
  ListTodo,
  ChevronLeft,
  ChevronRight,
  Code2,
  Plus,
  Library,
} from 'lucide-react';
import { useAppStore } from '../../store/appStore';
import './Sidebar.css';

const mainNavItems = [
  { path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/chat', icon: MessageSquare, label: 'Code Assistant' },
  { path: '/repositories', icon: Library, label: 'Repositories' },
  { path: '/analyze', icon: Plus, label: 'Add Repository' },
  { path: '/jobs', icon: Activity, label: 'Analysis Jobs' },
];

const workflowNavItems = [
  { path: '/generate-brd', icon: FileText, label: 'Generate BRD' },
  { path: '/generate-epic', icon: Layers, label: 'Generate EPIC' },
  { path: '/generate-backlogs', icon: ListTodo, label: 'Generate Backlogs' },
];

export function Sidebar() {
  const { sidebarOpen, toggleSidebar } = useAppStore();

  return (
    <aside className={`sidebar ${sidebarOpen ? 'open' : 'collapsed'}`}>
      <div className="sidebar-header">
        <div className="logo">
          <div className="logo-icon-wrapper">
            <Code2 />
          </div>
          {sidebarOpen && (
            <div className="logo-text-container">
              <span className="logo-title">CodeSense AI</span>
              <span className="logo-subtitle">Intelligent Analysis</span>
            </div>
          )}
        </div>
        <button className="toggle-btn" onClick={toggleSidebar} aria-label="Toggle sidebar">
          {sidebarOpen ? <ChevronLeft size={20} /> : <ChevronRight size={20} />}
        </button>
      </div>

      <nav className="sidebar-nav">
        {mainNavItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            title={item.label}
          >
            <item.icon size={20} />
            {sidebarOpen && <span>{item.label}</span>}
          </NavLink>
        ))}

        {sidebarOpen && <div className="nav-section-title">Workflow</div>}

        {workflowNavItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            title={item.label}
          >
            <item.icon size={20} />
            {sidebarOpen && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        {sidebarOpen && (
          <div className="api-status">
            <div className="status-dot"></div>
            <span className="status-text">API Connected</span>
          </div>
        )}
        {sidebarOpen && (
          <div className="version-info" style={{ marginTop: '8px' }}>
            v1.0.0
          </div>
        )}
      </div>
    </aside>
  );
}
