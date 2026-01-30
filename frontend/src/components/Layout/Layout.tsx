import type { ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { useAppStore } from '../../store/appStore';
import './Layout.css';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const { sidebarOpen } = useAppStore();

  return (
    <div className="app-layout">
      <Sidebar />
      <main className={`main-content ${sidebarOpen ? 'sidebar-open' : 'sidebar-collapsed'}`}>
        {children}
      </main>
    </div>
  );
}
