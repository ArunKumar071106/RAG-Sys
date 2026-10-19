import { useEffect, useRef } from "react";
import { brand } from "../brand";
import { useChat, type ChatStatusEvent } from "../hooks/useChat";
import { moments, momentForFailure, momentForResult } from "../robot/moments";
import { ChatInput } from "./ChatInput";
import { LoadingIndicator } from "./LoadingIndicator";
import { MessageBubble } from "./MessageBubble";
import { AssistantLabel } from "./AssistantLabel";
import { SuggestedQuestions } from "./SuggestedQuestions";

/** Quick topics above the question box (Mobile.dc.html), each asking a question the website answers. */
export const QUICK_TOPICS = [
  { label: "Eligibility", question: "What is the eligibility for B.E. and B.Tech admission?" },
  { label: "Fees", question: "What are the tuition fees?" },
  { label: "Scholarships", question: "What scholarships are available?" },
  { label: "Hostel", question: "What hostel facilities are available?" },
];

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
          <span className="chat__badge" aria-hidden="true">
            AAA
          </span>
          <div className="chat__heading">
            <h2 id="chat-title" className="chat__title">
              Admission Help Desk
            </h2>
            <p className="chat__subtitle">Answers from the official {brand.short_name} website</p>
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
          <MessageBubble key={message.id} message={message} onRetry={retry} busy={loading} />
        ))}
        {loading && <LoadingIndicator />}
        <div ref={endRef} />
      </div>

      <div className="chat__footer">
        <ul className="topics" aria-label="Quick topics">
          {QUICK_TOPICS.map((topic) => (
            <li key={topic.label}>
              <button type="button" className="topic" onClick={() => ask(topic.question)} disabled={loading} title={topic.question}>
                {topic.label}
              </button>
            </li>
          ))}
        </ul>
        <ChatInput ref={inputRef} onSend={ask} disabled={loading} />
      </div>
    </section>
  );
}
