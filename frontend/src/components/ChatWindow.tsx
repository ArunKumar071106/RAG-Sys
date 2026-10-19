import { useEffect, useRef, type MouseEvent } from "react";
import { brand } from "../brand";
import { useChat } from "../hooks/useChat";
import { Robot } from "../robot/Robot";
import { RobotAvatar } from "../robot/RobotAvatar";
import type { RobotDirector } from "../robot/states";
import { useRobot, useRobotDirector } from "../robot/useRobot";
import { ChatInput } from "./ChatInput";
import { LoadingIndicator } from "./LoadingIndicator";
import { MessageBubble } from "./MessageBubble";
import { SuggestedQuestions } from "./SuggestedQuestions";

interface Props {
  /** Shared with the floating launcher; a standalone chat (embed mode) drives its own robot. */
  director?: RobotDirector;
  /** False while the panel is closed, so only one robot is ever on screen. */
  showRobot?: boolean;
  onClose?: () => void;
}

export function ChatWindow({ director: shared, showRobot = true, onClose }: Props) {
  const own = useRobotDirector();
  const director = shared ?? own;
  const robot = useRobot(director);
  const { messages, loading, send, retry, reset } = useChat(director.emit);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!shared) own.emit({ type: "opened" });
  }, [shared, own]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [messages.length, loading]);

  const startNewChat = () => {
    reset();
    director.emit({ type: "new-chat" });
    inputRef.current?.focus();
  };

  const ask = (question: string) => {
    send(question);
    inputRef.current?.focus();
  };

  // opening a cited official page, document or image is the conversation's "action"
  const onLogClick = (event: MouseEvent<HTMLDivElement>) => {
    const link = (event.target as Element).closest?.("a[href]");
    if (link && /^https?:\/\//.test(link.getAttribute("href") ?? "")) director.emit({ type: "action" });
  };

  return (
    <section className="chat" id="assistant" aria-labelledby="chat-title">
      <div className="chat__header">
        <div className="chat__robot">{showRobot && <Robot state={robot.state} decorative />}</div>
        <div className="chat__heading">
          <h2 id="chat-title" className="chat__title">
            Arivazhai
          </h2>
          <p className="chat__subtitle">{brand.short_name} admission assistant · answers from the official website</p>
          <p className="chat__status" data-state={robot.state}>
            {robot.caption}
          </p>
        </div>
        <div className="chat__actions">
          <button type="button" className="btn btn--outline btn--on-dark" onClick={startNewChat} disabled={messages.length === 0 && !loading}>
            New chat
          </button>
          {onClose && (
            <button type="button" className="chat__close" onClick={onClose} aria-label="Close Arivazhai chat">
              <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
                <path fill="currentColor" d="M18.3 5.7 12 12l6.3 6.3-1.4 1.4L10.6 13.4 4.3 19.7 2.9 18.3 9.2 12 2.9 5.7l1.4-1.4 6.3 6.3 6.3-6.3z" />
              </svg>
            </button>
          )}
        </div>
      </div>

      <div className="chat__log" role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversation" onClick={onLogClick}>
        <div className="message message--assistant">
          <RobotAvatar />
          <div className="bubble bubble--assistant">
            <p>
              Welcome! I'm Arivazhai, the {brand.short_name} admission assistant. Ask me about admissions, courses, departments,
              placements, facilities or contact details. I answer from the official website and link every source.
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

      <ChatInput ref={inputRef} onSend={ask} disabled={loading} onTyping={() => director.emit({ type: "typing" })} />
    </section>
  );
}
