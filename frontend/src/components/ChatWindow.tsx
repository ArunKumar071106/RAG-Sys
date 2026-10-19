import { useEffect, useRef } from "react";
import { brand } from "../brand";
import { useChat } from "../hooks/useChat";
import { ChatInput } from "./ChatInput";
import { LoadingIndicator } from "./LoadingIndicator";
import { MessageBubble } from "./MessageBubble";
import { SuggestedQuestions } from "./SuggestedQuestions";

export function ChatWindow() {
  const { messages, loading, send, retry, reset } = useChat();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [messages.length, loading]);

  const startNewChat = () => {
    reset();
    inputRef.current?.focus();
  };

  const ask = (question: string) => {
    send(question);
    inputRef.current?.focus();
  };

  return (
    <section className="chat" id="assistant" aria-labelledby="chat-title">
      <div className="chat__header">
        <div>
          <h2 id="chat-title" className="chat__title">
            {brand.short_name} Virtual Assistant
          </h2>
          <p className="chat__subtitle">Answers from the official {brand.short_name} website, with links to every source.</p>
        </div>
        <button type="button" className="btn btn--outline" onClick={startNewChat} disabled={messages.length === 0 && !loading}>
          New chat
        </button>
      </div>

      <div className="chat__log" role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversation">
        <div className="message message--assistant">
          <div className="avatar" aria-hidden="true">AI</div>
          <div className="bubble bubble--assistant">
            <p>
              Welcome! I'm the {brand.short_name} Virtual Assistant. Ask me about admissions, courses, departments, placements,
              facilities or contact details. I answer from the official website and link every source.
            </p>
            {messages.length === 0 && <SuggestedQuestions onSelect={ask} disabled={loading} />}
          </div>
        </div>

        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} onRetry={retry} busy={loading} />
        ))}
        {loading && <LoadingIndicator />}
        <div ref={endRef} />
      </div>

      <ChatInput ref={inputRef} onSend={ask} disabled={loading} />
    </section>
  );
}
