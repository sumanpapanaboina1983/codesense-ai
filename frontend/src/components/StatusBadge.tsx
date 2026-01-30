interface StatusBadgeProps {
  status: string;
  type?: 'default' | 'analysis';
}

export function StatusBadge({ status, type = 'default' }: StatusBadgeProps) {
  const getStatusClass = () => {
    if (type === 'analysis') {
      switch (status) {
        case 'completed':
          return 'badge-success';
        case 'in_progress':
          return 'badge-running';
        case 'failed':
          return 'badge-error';
        case 'not_started':
        default:
          return 'badge-pending';
      }
    }

    switch (status) {
      case 'cloned':
      case 'completed':
        return 'badge-success';
      case 'cloning':
      case 'in_progress':
        return 'badge-running';
      case 'failed':
        return 'badge-error';
      case 'pending':
      case 'not_started':
      default:
        return 'badge-pending';
    }
  };

  const getStatusLabel = () => {
    return status.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
  };

  return <span className={`badge ${getStatusClass()}`}>{getStatusLabel()}</span>;
}
