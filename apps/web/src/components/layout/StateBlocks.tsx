interface LoadingStateProps {
  label?: string;
}

interface EmptyStateProps {
  title: string;
  message?: string;
}

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function LoadingState({ label = "Loading..." }: LoadingStateProps) {
  return <div className="state-block">{label}</div>;
}

export function EmptyState({ title, message }: EmptyStateProps) {
  return (
    <div className="state-block">
      <strong>{title}</strong>
      {message ? <span>{message}</span> : null}
    </div>
  );
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="state-block error-state" role="alert">
      <span>{message}</span>
      {onRetry ? (
        <button className="button secondary" type="button" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}
