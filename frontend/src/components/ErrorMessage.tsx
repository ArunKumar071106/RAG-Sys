interface Props {
  message: string;
  onRetry?: () => void;
  retryDisabled?: boolean;
}

export function ErrorMessage({ message, onRetry, retryDisabled }: Props) {
  return (
    <div className="error-message" role="alert">
      <span className="error-message__icon" aria-hidden="true">!</span>
      <p className="error-message__text">{message}</p>
      {onRetry && (
        <button type="button" className="btn btn--outline btn--small" onClick={onRetry} disabled={retryDisabled}>
          Try again
        </button>
      )}
    </div>
  );
}
