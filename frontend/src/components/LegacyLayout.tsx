import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  GitBranch,
  FileText,
  ListTree,
  ClipboardList,
  Send,
  Settings,
  Brain,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { getHealth } from '../api/client';
import type { HealthStatus } from '../types';

interface LayoutProps {
  children: ReactNode;
}

const navItems = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/repositories', icon: GitBranch, label: 'Repositories' },
];

const workflowItems = [
  { path: '/workflow/brd', icon: FileText, label: 'Generate BRD' },
  { path: '/workflow/epics', icon: ListTree, label: 'Generate Epics' },
  { path: '/workflow/stories', icon: ClipboardList, label: 'Generate Stories' },
  { path: '/workflow/jira', icon: Send, label: 'Export to JIRA' },
];

export function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const [health, setHealth] = useState<HealthStatus | null>(null);

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const status = await getHealth();
        setHealth(status);
      } catch {
        setHealth(null);
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const getPageTitle = () => {
    const path = location.pathname;
    if (path === '/') return 'Dashboard';
    if (path === '/repositories') return 'Repositories';
    if (path === '/workflow/brd') return 'Generate BRD';
    if (path === '/workflow/epics') return 'Generate Epics';
    if (path === '/workflow/stories') return 'Generate Stories';
    if (path === '/workflow/jira') return 'Export to JIRA';
    if (path === '/settings') return 'Settings';
    return 'CodeSense AI';
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo">
            <div className="logo-icon">
              <Brain size={28} />
            </div>
            <div className="logo-text">
              <span className="logo-title">CodeSense</span>
              <span className="logo-subtitle">AI Platform</span>
            </div>
          </div>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `nav-item ${isActive ? 'active' : ''}`
              }
            >
              <item.icon size={20} />
              <span>{item.label}</span>
            </NavLink>
          ))}

          <div className="nav-section-title">Workflow</div>

          {workflowItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `nav-item ${isActive ? 'active' : ''}`
              }
            >
              <item.icon size={20} />
              <span>{item.label}</span>
            </NavLink>
          ))}

          <div className="nav-section-title">System</div>

          <NavLink
            to="/settings"
            className={({ isActive }) =>
              `nav-item ${isActive ? 'active' : ''}`
            }
          >
            <Settings size={20} />
            <span>Settings</span>
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <div className={`api-status ${health ? '' : 'offline'}`}>
            {health ? (
              <CheckCircle size={16} className="status-dot" style={{ background: 'none', color: '#28a745' }} />
            ) : (
              <XCircle size={16} className="status-dot" style={{ background: 'none', color: '#CC3362' }} />
            )}
            <span className="status-text">
              {health ? 'API Connected' : 'API Offline'}
            </span>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="top-header">
          <div className="header-title">
            <h1>{getPageTitle()}</h1>
          </div>
        </header>

        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}
