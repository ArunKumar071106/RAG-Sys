import { useEffect, useRef } from "react";
import { brand } from "../brand";
import { useChat, type ChatStatusEvent } from "../hooks/useChat";
import { moments, momentForFailure, momentForResult } from "../robot/moments";
import { ChatInput } from "./ChatInput";
import { LoadingIndicator } from "./LoadingIndicator";
import { MessageBubble } from "./MessageBubble";
import { RobotProfile } from "../robot/RobotProfile";
import { AssistantLabel } from "./AssistantLabel";
import { SuggestedQuestions } from "./SuggestedQuestions";

/** Event the page's "Start chat" buttons send; the chat scrolls into view, greets and takes focus. */
export const START_CHAT_EVENT = "arivazhai:start-chat";

export function startChat() {
  window.dispatchEvent(new Event(START_CHAT_EVENT));
}

/** The robot pops up for the request's real progress: searching, not on the website, or failed. */
function showMoment(event: ChatStatusEvent) {
  if (event.type === "retrieving") moments.show({ kind: "think" });
  else if (event.type === "failed") moments.show(momentForFailure(event.kind));
  else {
    const cue = momentForResult(event.result);
    if (cue) moments.show(cue);
  }
}

export function ChatWindow() {
  const { messages, loading, send, retry, reset } = useChat(showMoment);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [messages.length, loading]);

  useEffect(() => {
    const start = () => {
      document.getElementById("assistant")?.scrollIntoView?.({ behavior: "smooth", block: "start" });
      inputRef.current?.focus({ preventScroll: true });
      moments.show({ kind: "greet" });
    };
    window.addEventListener(START_CHAT_EVENT, start);
    return () => window.removeEventListener(START_CHAT_EVENT, start);
  }, []);

  const latestAnswer = [...messages].reverse().find((m) => m.role === "assistant");

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
        <div className="chat__brand">
          <RobotProfile />
          <div className="chat__heading">
            <h2 id="chat-title" className="chat__title">
              Arivazhai
            </h2>
            <p className="chat__subtitle">{brand.short_name} admission help desk · answers from the official website</p>
          </div>
        </div>
        <button type="button" className="chat__new" onClick={startNewChat} disabled={messages.length === 0 && !loading}>
          New chat
        </button>
      </div>

      <div className="chat__log" role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversation">
        <div className="message message--assistant">
          <AssistantLabel />
          <div className="bubble bubble--assistant">
            <p>
              Vanakkam! I'm Arivazhai, the {brand.short_name} admission assistant. Ask me about eligibility, TNEA counselling,
              courses, fees, scholarships, hostel or placements. I answer from the official website and link every source.
            </p>
            {messages.length === 0 && <SuggestedQuestions onSelect={ask} disabled={loading} />}
          </div>
        </div>

        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            onRetry={retry}
            busy={loading}
            onAsk={message === latestAnswer && !loading ? ask : undefined}
          />
        ))}
        {loading && <LoadingIndicator />}
        <div ref={endRef} />
      </div>

      <div className="chat__footer">
        <ChatInput ref={inputRef} onSend={ask} disabled={loading} />
      </div>
    </section>
  );
}
