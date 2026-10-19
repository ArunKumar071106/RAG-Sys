import { forwardRef, useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { fetchSuggestions } from "../api/client";

export const MAX_MESSAGE_LENGTH = 1000;
const SUGGEST_DELAY_MS = 150;

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
  /** Type-ahead source; defaults to the API's /api/suggest. */
  suggest?: (typed: string, signal: AbortSignal) => Promise<string[]>;
}

/** Bold the words of a suggestion that start with a word the user typed. */
function highlight(text: string, typed: string): ReactNode[] {
  const words = typed.toLowerCase().match(/[a-z0-9]+/g) ?? [];
  return text.split(/(\s+)/).map((part, i) => {
    const plain = part.toLowerCase().replace(/[^a-z0-9]/g, "");
    return plain && words.some((w) => plain.startsWith(w)) ? <strong key={i}>{part}</strong> : part;
  });
}

export const ChatInput = forwardRef<HTMLTextAreaElement, Props>(function ChatInput(
  { onSend, disabled, suggest = fetchSuggestions },
  ref,
) {
  const [value, setValue] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [active, setActive] = useState(-1);
  const [open, setOpen] = useState(false);
  const typedRef = useRef(false); // suggestions follow typing, not text set by picking one
  const listId = useId();
  const trimmed = value.trim();
  const remaining = MAX_MESSAGE_LENGTH - value.length;
  const showList = open && suggestions.length > 0;

  useEffect(() => {
    if (!typedRef.current || trimmed.length < 2) {
      setSuggestions([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      suggest(trimmed, controller.signal).then((items) => {
        if (controller.signal.aborted) return;
        setSuggestions(items.filter((s) => s.toLowerCase() !== trimmed.toLowerCase()));
        setActive(-1);
        setOpen(true);
      });
    }, SUGGEST_DELAY_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [trimmed, suggest]);

  const close = () => {
    setOpen(false);
    setActive(-1);
  };

  const send = (text: string) => {
    if (!text.trim() || disabled) return;
    onSend(text.trim());
    typedRef.current = false;
    setValue("");
    setSuggestions([]);
    close();
  };

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    send(trimmed);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (showList && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      // -1 is "nothing picked" (Enter sends what was typed); the arrows cycle through it
      const last = suggestions.length - 1;
      setActive((i) => (event.key === "ArrowDown" ? (i >= last ? -1 : i + 1) : i <= -1 ? last : i - 1));
      return;
    }
    if (showList && event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (showList && event.key === "Tab" && active >= 0) {
      event.preventDefault(); // take the suggestion into the box to edit it
      typedRef.current = false;
      setValue(suggestions[active]);
      close();
      return;
    }
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (showList && active >= 0) send(suggestions[active]);
      else submit();
    }
  };

  const activeId = showList && active >= 0 && active < suggestions.length ? `${listId}-${active}` : undefined;

  return (
    <form className="chat-input" onSubmit={submit}>
      <label htmlFor="chat-message" className="visually-hidden">
        Ask a question about AAACET
      </label>
      {showList && (
        <ul id={listId} className="chat-suggestions" role="listbox" aria-label="Suggested questions">
          {suggestions.map((s, i) => (
            <li
              key={s}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={`chat-suggestions__item${i === active ? " is-active" : ""}`}
              onMouseDown={(e) => e.preventDefault()} // keep focus in the box
              onClick={() => send(s)}
              onMouseEnter={() => setActive(i)}
            >
              {highlight(s, value)}
            </li>
          ))}
        </ul>
      )}
      <textarea
        id="chat-message"
        ref={ref}
        className="chat-input__field"
        dir="auto"
        rows={1}
        placeholder="Ask about admissions, courses, facilities…"
        value={value}
        maxLength={MAX_MESSAGE_LENGTH}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={showList ? listId : undefined}
        aria-activedescendant={activeId}
        onChange={(e) => {
          typedRef.current = true;
          setValue(e.target.value);
        }}
        onKeyDown={onKeyDown}
        onBlur={close}
        aria-describedby="chat-input-hint"
      />
      <button type="submit" className="btn btn--primary chat-input__send" disabled={!trimmed || disabled} aria-label="Send message">
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
          <path fill="currentColor" d="M2.01 21 23 12 2.01 3 2 10l15 2-15 2z" />
        </svg>
        <span className="chat-input__send-label">Send</span>
      </button>
      <p id="chat-input-hint" className="chat-input__hint">
        Press Enter to send, Shift + Enter for a new line. Use ↑ ↓ to pick a suggestion.
        {remaining <= 100 && <span className="chat-input__count"> {remaining} characters left.</span>}
      </p>
    </form>
  );
});
