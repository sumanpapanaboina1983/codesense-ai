interface LoadingSpinnerProps {
  message?: string;
}

export function LoadingSpinner({ message = 'Loading...' }: LoadingSpinnerProps) {
  return (
    <div className="loading-state">
      <div className="spinner" />
      <p style={{ marginTop: '1rem', color: 'var(--color-gray-500)' }}>{message}</p>
    </div>
  );
}
