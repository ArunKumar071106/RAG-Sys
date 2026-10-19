import { useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { LauncherIcon } from "../robot/LauncherIcon";
import { DEFAULT_ACCENT, Robot } from "../robot/Robot";
import { useRobot, useRobotDirector } from "../robot/useRobot";
import { ChatWindow } from "./ChatWindow";

/** Below this width the launcher is the design's head-only disc and the panel fills the screen. */
export const NARROW_MAX_PX = 639;
const FIRST_VISIT_DELAY_MS = 2000;
const NUDGE_AFTER_IDLE_MS = 8000;
const GREETED_KEY = "arivazhai:greeted";
const NUDGED_KEY = "arivazhai:nudged";
/** States in which the launcher shows its caption bubble. */
const BUBBLE_STATES = new Set(["greet", "attend", "support", "think", "answer", "error", "unsure"]);

function storageFlag(storage: () => Storage, key: string, set = false): boolean {
  try {
    if (set) storage().setItem(key, "1");
    return storage().getItem(key) === "1";
  } catch {
    return set; // storage blocked (private mode, iframes): behave as if it worked for this page view
  }
}

interface Viewport {
  width: number;
  height: number;
}

/**
 * The visible viewport. In widget mode the app runs in a small iframe on the college website, so
 * the host page's size comes from the loader script (public/arivazhai-widget.js) instead.
 */
function useViewport(widget: boolean): Viewport {
  const read = () => ({ width: window.innerWidth, height: window.innerHeight });
  const [viewport, setViewport] = useState<Viewport>(() => {
    // the loader passes the host page's size in the iframe URL, so the first paint is already right
    const params = new URLSearchParams(window.location.search);
    const width = Number(params.get("vw"));
    const height = Number(params.get("vh"));
    return widget && width > 0 && height > 0 ? { width, height } : read();
  });
  useEffect(() => {
    if (widget) {
      const onMessage = (event: MessageEvent) => {
        const data = event.data;
        if (event.source !== window.parent || data?.type !== "arivazhai:viewport") return;
        if (typeof data.width === "number" && typeof data.height === "number") setViewport({ width: data.width, height: data.height });
      };
      window.addEventListener("message", onMessage);
      window.parent.postMessage({ type: "arivazhai:ready" }, "*");
      return () => window.removeEventListener("message", onMessage);
    }
    const onResize = () => setViewport(read());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [widget]);
  return viewport;
}

/** The iframe box the loader should give the widget, in CSS lengths. */
export function widgetFrameSize(open: boolean, narrow: boolean, bubble: boolean, viewport: Viewport) {
  if (open) return narrow ? { width: "100%", height: "100%" } : { width: `${Math.min(440, viewport.width)}px`, height: `${Math.min(760, viewport.height)}px` };
  if (narrow) return { width: "96px", height: "96px" };
  return { width: bubble ? "380px" : "150px", height: "160px" };
}

interface Props {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Running inside the loader's iframe on the college website. */
  widget?: boolean;
}

/**
 * Floating Arivazhai launcher (bottom-right) and the expanded chat panel. One robot director drives
 * both, and only one robot is rendered at a time: on the launcher while closed, in the panel while open.
 * The chat stays mounted while closed, so the conversation and a running search survive closing.
 */
export function ChatWidget({ open: controlled, onOpenChange, widget = false }: Props) {
  const [uncontrolled, setUncontrolled] = useState(false);
  const open = controlled ?? uncontrolled;
  const director = useRobotDirector();
  const robot = useRobot(director);
  const viewport = useViewport(widget);
  const narrow = viewport.width <= NARROW_MAX_PX;
  const launcherRef = useRef<HTMLButtonElement>(null);
  const [hover, setHover] = useState(false);
  const wasOpen = useRef(open);

  const setOpen = useCallback(
    (next: boolean) => {
      if (controlled === undefined) setUncontrolled(next);
      onOpenChange?.(next);
    },
    [controlled, onOpenChange],
  );

  // open/close side effects: greeting, focus, scroll lock
  useEffect(() => {
    if (open === wasOpen.current) return;
    wasOpen.current = open;
    if (open) {
      setHover(false);
      director.emit({ type: "launcher-focus", on: false });
      director.emit({ type: "opened" });
      // after the panel is visible
      requestAnimationFrame(() => document.getElementById("chat-message")?.focus());
    } else {
      director.emit({ type: "closed" });
      launcherRef.current?.focus();
    }
  }, [open, director]);

  useEffect(() => {
    if (!open || !narrow || widget) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open, narrow, widget]);

  // the design's own launcher triggers: greeting on the first visit, one attention wave per session
  useEffect(() => {
    if (open) return;
    const timers: ReturnType<typeof setTimeout>[] = [];
    if (!storageFlag(() => window.localStorage, GREETED_KEY)) {
      timers.push(
        setTimeout(() => {
          storageFlag(() => window.localStorage, GREETED_KEY, true);
          director.emit({ type: "first-visit" });
        }, FIRST_VISIT_DELAY_MS),
      );
    }
    if (storageFlag(() => window.sessionStorage, NUDGED_KEY)) return () => timers.forEach(clearTimeout);
    let idle: ReturnType<typeof setTimeout>;
    const restart = () => {
      clearTimeout(idle);
      idle = setTimeout(() => {
        storageFlag(() => window.sessionStorage, NUDGED_KEY, true);
        director.emit({ type: "nudge" });
      }, NUDGE_AFTER_IDLE_MS);
    };
    const events = ["scroll", "wheel", "pointerdown", "keydown", "touchstart"] as const;
    events.forEach((name) => window.addEventListener(name, restart, { passive: true }));
    restart();
    return () => {
      timers.forEach(clearTimeout);
      clearTimeout(idle);
      events.forEach((name) => window.removeEventListener(name, restart));
    };
  }, [open, director]);

  const showBubble = !open && !narrow && (hover || BUBBLE_STATES.has(robot.state));

  // tell the loader how big the iframe must be
  useEffect(() => {
    if (!widget) return;
    window.parent.postMessage({ type: "arivazhai:size", ...widgetFrameSize(open, narrow, showBubble, viewport) }, "*");
  }, [widget, open, narrow, showBubble, viewport]);

  const focusLauncher = (on: boolean) => {
    if (open) return;
    setHover(on);
    director.emit({ type: "launcher-focus", on });
  };

  const onPanelKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    // Escape first closes the suggestion list (ChatInput prevents the default), then the panel
    if (event.key === "Escape" && !event.defaultPrevented) {
      event.preventDefault();
      setOpen(false);
    }
  };

  const classes = ["widget", open ? "is-open" : "", narrow ? "is-narrow" : "", widget ? "is-framed" : ""].filter(Boolean).join(" ");

  return (
    <div className={classes} style={{ "--robot-accent": DEFAULT_ACCENT } as CSSProperties}>
      <div id="arivazhai-panel" className="widget__panel" role="dialog" aria-label="Arivazhai chat" hidden={!open} onKeyDown={onPanelKeyDown}>
        <ChatWindow director={director} showRobot={open} onClose={() => setOpen(false)} />
      </div>

      {showBubble && (
        <p className="widget__bubble" aria-hidden="true">
          {robot.caption}
        </p>
      )}

      <button
        ref={launcherRef}
        type="button"
        className={`widget__launcher${open ? " widget__launcher--close" : narrow ? " widget__launcher--disc" : " widget__launcher--robot"}`}
        aria-label={open ? "Close Arivazhai chat" : "Ask Arivazhai about admissions"}
        aria-expanded={open}
        aria-controls="arivazhai-panel"
        hidden={open && narrow}
        onClick={() => setOpen(!open)}
        onPointerEnter={() => focusLauncher(true)}
        onPointerLeave={() => focusLauncher(false)}
        onFocus={() => focusLauncher(true)}
        onBlur={() => focusLauncher(false)}
      >
        {open ? (
          <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" focusable="false">
            <path fill="currentColor" d="M7.4 8.6 12 13.2l4.6-4.6L18 10l-6 6-6-6z" />
          </svg>
        ) : narrow ? (
          <LauncherIcon />
        ) : (
          <Robot state={robot.state} decorative />
        )}
      </button>
    </div>
  );
}
