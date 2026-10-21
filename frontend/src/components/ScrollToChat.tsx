import { useEffect, useState } from "react";
import { startChat } from "./ChatWindow";

/**
 * Round down-arrow at the bottom-right while the chat's question box is still below the screen:
 * it shows people the chat is further down and takes them there.
 */
export function ScrollToChat() {
  const [below, setBelow] = useState(true);

  useEffect(() => {
    const target = document.querySelector(".chat__footer");
    if (!target || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => {
      // hidden when the question box is on screen, or already scrolled past (above the screen)
      setBelow(!entry.isIntersecting && entry.boundingClientRect.top > 0);
    });
    observer.observe(target);
    return () => observer.disconnect();
  }, []);

  if (!below) return null;
  return (
    <button type="button" className="scroll-to-chat" onClick={startChat} aria-label="Go to the chat below" title="The chat is below">
      <span className="scroll-to-chat__label" aria-hidden="true">
        Chat below
      </span>
      <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" focusable="false">
        <path fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" d="M6 9.5l6 6 6-6" />
      </svg>
    </button>
  );
}
