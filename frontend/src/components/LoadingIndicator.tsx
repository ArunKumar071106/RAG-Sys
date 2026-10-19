export function LoadingIndicator({ label = "Searching the official website…" }: { label?: string }) {
  return (
    <div className="message message--assistant" role="status" aria-live="polite">
      <div className="avatar" aria-hidden="true">AI</div>
      <div className="bubble bubble--assistant bubble--loading">
        <span className="dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        <span className="loading-label">{label}</span>
      </div>
    </div>
  );
}
