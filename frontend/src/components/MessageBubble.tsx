import { useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "../hooks/useChat";
import { safeHref } from "../brand";
import { CITATION_TEXT, linkCitations } from "./citations";
import { AssistantLabel } from "./AssistantLabel";
import { ADMISSION_QUESTION, CONTACT_QUESTION, ContactCard } from "./ContactCard";
import { ErrorMessage } from "./ErrorMessage";
import { ImageCard } from "./ImageCard";
import { SourceList } from "./SourceList";
import { SuggestedQuestions } from "./SuggestedQuestions";
import { TranslateToggle } from "./TranslateToggle";

function textOf(children: ReactNode): string {
  if (typeof children === "string" || typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(textOf).join("");
  return "";
}

const markdownComponents: Components = {
  a({ href, title, children }) {
    const text = textOf(children);
    if (href?.startsWith("#")) {
      return (
        <a href={href} className="citation citation--image">
          {children}
        </a>
      );
    }
    const safe = href ? safeHref(href) : undefined;
    if (!safe) return <>{children}</>;
    const isCitation = CITATION_TEXT.test(text);
    return (
      <a
        href={safe}
        title={title}
        target="_blank"
        rel="noopener noreferrer"
        className={isCitation ? "citation" : undefined}
        aria-label={isCitation && title ? `${title} (opens in a new tab)` : undefined}
      >
        {children}
      </a>
    );
  },
  img() {
    return null; // images are shown as cards, never inlined from model output
  },
};

interface Props {
  message: Message;
  onRetry?: (id: string) => void;
  busy?: boolean;
  /** Set on the latest answer: its suggested next questions are asked with this. */
  onAsk?: (question: string) => void;
}

export function MessageBubble({ message, onRetry, busy, onAsk }: Props) {
  const [english, setEnglish] = useState<string | null>(null);

  if (message.role === "user") {
    return (
      <div className="message message--user">
        <div className="bubble bubble--user">
          <span className="visually-hidden">You said: </span>
          <span dir="auto">{message.content}</span>
        </div>
      </div>
    );
  }

  if (message.error) {
    return (
      <div className="message message--assistant">
        <AssistantLabel />
        <div className="bubble bubble--assistant bubble--error">
          <ErrorMessage message={message.error.message} onRetry={onRetry ? () => onRetry(message.id) : undefined} retryDisabled={busy} />
        </div>
      </div>
    );
  }

  const result = message.result;
  const noAnswer = result?.mode === "no_answer";
  const text = english ?? message.content;
  const markdown = result ? linkCitations(text, result.sources, result.images, message.id) : text;
  // "not on the website" and contact questions end with how to reach the college
  const showContact = noAnswer || CONTACT_QUESTION.test(message.question ?? "");
  // the admission and scholarship staff, when that is who can help
  const showStaff = noAnswer || ADMISSION_QUESTION.test(message.question ?? "");
  const followUps = onAsk ? result?.follow_ups ?? [] : [];

  return (
    <div className="message message--assistant">
      <AssistantLabel />
      <div className={`bubble bubble--assistant${noAnswer ? " bubble--no-answer" : ""}`}>
        <span className="visually-hidden">Assistant: </span>
        <div className="markdown" dir="auto" lang={english ? "en" : undefined}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents} skipHtml>
            {markdown}
          </ReactMarkdown>
        </div>

        {result?.translatable && <TranslateToggle text={message.content} onShow={setEnglish} />}

        {result?.notice && <p className="notice">{result.notice}</p>}

        {result && result.images.length > 0 && (
          <section className="images" aria-label="Related images from the official website">
            <h4 className="images__title">Images from the official website</h4>
            <div className="images__grid">
              {result.images.map((image, i) => (
                <ImageCard key={image.image_id} image={image} index={i + 1} anchorId={`${message.id}-${image.id}`} />
              ))}
            </div>
          </section>
        )}

        {result && <SourceList sources={result.sources} />}
        {result && noAnswer && result.related_sources.length > 0 && (
          <SourceList sources={result.related_sources} variant="related" title="These official pages may be related" />
        )}
        {showContact && (
          <ContactCard title={noAnswer ? "The admission office can help you directly" : "Contact the college"} staff={showStaff} />
        )}
      </div>
      {followUps.length > 0 && onAsk && <SuggestedQuestions questions={followUps} onSelect={onAsk} disabled={busy} title="You can also ask" />}
    </div>
  );
}
