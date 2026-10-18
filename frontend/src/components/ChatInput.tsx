import { forwardRef, useState, type FormEvent, type KeyboardEvent } from "react";

export const MAX_MESSAGE_LENGTH = 1000;

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export const ChatInput = forwardRef<HTMLTextAreaElement, Props>(function ChatInput({ onSend, disabled }, ref) {
  const [value, setValue] = useState("");
  const trimmed = value.trim();
  const remaining = MAX_MESSAGE_LENGTH - value.length;

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form className="chat-input" onSubmit={submit}>
      <label htmlFor="chat-message" className="visually-hidden">
        Ask a question about AAACET
      </label>
      <textarea
        id="chat-message"
        ref={ref}
        className="chat-input__field"
        rows={1}
        placeholder="Ask about admissions, courses, facilities…"
        value={value}
        maxLength={MAX_MESSAGE_LENGTH}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        aria-describedby="chat-input-hint"
      />
      <button type="submit" className="btn btn--primary chat-input__send" disabled={!trimmed || disabled} aria-label="Send message">
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
          <path fill="currentColor" d="M2.01 21 23 12 2.01 3 2 10l15 2-15 2z" />
        </svg>
        <span className="chat-input__send-label">Send</span>
      </button>
      <p id="chat-input-hint" className="chat-input__hint">
        Press Enter to send, Shift + Enter for a new line.
        {remaining <= 100 && <span className="chat-input__count"> {remaining} characters left.</span>}
      </p>
    </form>
  );
});
