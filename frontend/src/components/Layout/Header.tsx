import { useAppStore } from '../../store/appStore';
import { Circle, RefreshCw } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { getHealth } from '../../services/api';
import './Header.css';

interface HeaderProps {
  title: string;
  subtitle?: string;
}

export function Header({ title, subtitle }: HeaderProps) {
  const { health, setHealth } = useAppStore();

  const { isLoading, refetch } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 30000,
    refetchOnWindowFocus: true,
  });

  // Update store when health changes
  useQuery({
    queryKey: ['health-sync'],
    queryFn: async () => {
      const data = await getHealth();
      setHealth(data);
      return data;
    },
    refetchInterval: 30000,
  });

  const isHealthy = health?.status === 'healthy';

  return (
    <header className="header">
      <div className="header-content">
        <div className="header-title">
          <h1>{title}</h1>
          {subtitle && <p className="subtitle">{subtitle}</p>}
        </div>

        <div className="header-status">
          <div className={`status-indicator ${isHealthy ? 'healthy' : 'unhealthy'}`}>
            <Circle size={10} fill="currentColor" />
            <span>{isHealthy ? 'Connected' : 'Disconnected'}</span>
          </div>
          <button
            className="refresh-btn"
            onClick={() => refetch()}
            disabled={isLoading}
            title="Refresh connection status"
          >
            <RefreshCw size={16} className={isLoading ? 'spinning' : ''} />
          </button>
        </div>
      </div>
    </header>
  );
}
