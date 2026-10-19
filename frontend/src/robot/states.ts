import type { ApiErrorKind } from "../api/client";
import type { ChatResult } from "../api/types";

/** The nine states of the design's rig (States.dc.html), in its order. Each is a class on <svg class="rb">. */
export const ROBOT_STATES = ["idle", "greet", "attend", "support", "think", "answer", "confirm", "unsure", "error"] as const;
export type RobotState = (typeof ROBOT_STATES)[number];

/** Everything in the chatbot the robot reacts to. Components report these; only this module picks animations. */
export type ChatEvent =
  | { type: "first-visit" } // floating robot, 2 s after the first page load ever
  | { type: "nudge" } // floating robot, once per session after 8 s without scrolling or input
  | { type: "launcher-focus"; on: boolean } // pointer or keyboard focus on the closed launcher
  | { type: "opened" }
  | { type: "closed" }
  | { type: "new-chat" }
  | { type: "typing" } // the visitor types or moves through suggestions
  | { type: "retrieving" } // question sent; the RAG request is in flight
  | { type: "answered"; result: ChatResult }
  | { type: "failed"; kind: ApiErrorKind }
  | { type: "action" }; // the visitor opened an official page or document the answer linked

/**
 * How long a state is shown:
 * - "once": one full cycle of its animation, then back to the resting state
 * - "linger": like once, restarted by every repeat of the event (typing)
 * - "busy": until the request finishes (thinking)
 * - "rest": becomes the resting state until the visitor moves on (unsure, error)
 * - "hover": while the launcher has focus or the pointer
 */
export type Hold = "once" | "linger" | "busy" | "rest" | "hover";

export interface Reaction {
  state: RobotState;
  hold: Hold;
  /** Short status line shown next to the robot. */
  caption: string;
}

/** One animation cycle per state, from the keyframe durations in robot.css. */
export const CYCLE_MS: Record<RobotState, number> = {
  idle: 5000,
  greet: 3600,
  attend: 4000,
  support: 2800,
  think: 2400,
  answer: 2800,
  confirm: 2800,
  unsure: 3400,
  error: 7000,
};

export const IDLE_CAPTION = "Ask me about admissions";

const FAILURE_CAPTIONS: Partial<Record<ApiErrorKind, string>> = {
  network: "I can't reach the server right now",
  timeout: "That took too long. Please try again",
  rate_limited: "Too many messages. Wait a moment",
  starting: "I'm still starting up. Try again in a minute",
  unavailable: "I'm temporarily unavailable",
};

/** The single mapping from chatbot events to the design's animation states. */
export function reactionFor(event: ChatEvent): Reaction | null {
  switch (event.type) {
    case "first-visit":
      return { state: "greet", hold: "once", caption: "Hi! I'm Arivazhai" };
    case "nudge":
      return { state: "attend", hold: "once", caption: "Questions about admissions? Ask me!" };
    case "launcher-focus":
      return event.on ? { state: "support", hold: "hover", caption: "Ask Arivazhai about admissions" } : null;
    case "opened":
    case "new-chat":
      return { state: "greet", hold: "once", caption: "Hi! Ask me anything about the college" };
    case "closed":
      return { state: "idle", hold: "rest", caption: IDLE_CAPTION };
    case "typing":
      return { state: "attend", hold: "linger", caption: "Listening…" };
    case "retrieving":
      return { state: "think", hold: "busy", caption: "Searching the official website…" };
    case "action":
      return { state: "confirm", hold: "once", caption: "Opened the official page" };
    case "failed":
      // a message the server could not take is a clarification, not an outage
      if (event.kind === "invalid") return { state: "unsure", hold: "rest", caption: "Could you rephrase that?" };
      return { state: "error", hold: "rest", caption: FAILURE_CAPTIONS[event.kind] ?? "Something went wrong on our side" };
    case "answered": {
      const { result } = event;
      if (result.mode !== "no_answer") return { state: "answer", hold: "once", caption: "Here's what the official website says" };
      // related pages but no answer: the question is probably ambiguous or too broad
      if (result.related_sources.length > 0) {
        return { state: "unsure", hold: "rest", caption: "I'm not sure. Try rephrasing, or see the related pages" };
      }
      return { state: "error", hold: "rest", caption: "That isn't on the official website" };
    }
  }
}

export interface RobotSnapshot {
  state: RobotState;
  caption: string;
}

/**
 * Plays reactions without conflicts: one state at a time, thinking wins while a request is in
 * flight, short reactions return to the resting state, and unsure/error stay until the visitor
 * moves on. Framework-free so it can be driven and tested without React.
 */
export class RobotDirector {
  private snapshot: RobotSnapshot = { state: "idle", caption: IDLE_CAPTION };
  private rest: RobotSnapshot = this.snapshot;
  private busy: RobotSnapshot | null = null;
  private hovering = false;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private listeners = new Set<() => void>();

  getSnapshot = (): RobotSnapshot => this.snapshot;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  emit = (event: ChatEvent): void => {
    if (event.type === "launcher-focus" && !event.on) {
      this.hovering = false;
      if (this.snapshot.state === "support") this.settle();
      return;
    }
    const reaction = reactionFor(event);
    if (!reaction) return;
    const ends = event.type === "answered" || event.type === "failed";
    const resets = event.type === "closed" || event.type === "new-chat";
    // while a request is in flight only its result (or leaving the conversation) changes the robot
    if (this.busy && !ends && !resets) return;
    if (ends || event.type === "new-chat") this.busy = null;

    const shown = { state: reaction.state, caption: reaction.caption };
    switch (reaction.hold) {
      case "busy":
        this.busy = shown;
        this.show(shown);
        break;
      case "rest":
        this.rest = shown;
        this.show(this.busy ?? shown); // closing the panel does not hide a search still running
        break;
      case "hover":
        this.hovering = true;
        this.show(shown);
        break;
      case "linger":
        // the visitor has moved on from an unsure or failed answer
        this.rest = { state: "idle", caption: IDLE_CAPTION };
        this.show(shown, CYCLE_MS[reaction.state]);
        break;
      case "once":
        if (event.type === "new-chat") this.rest = { state: "idle", caption: IDLE_CAPTION };
        this.show(shown, CYCLE_MS[reaction.state]);
        break;
    }
  };

  /** Stop pending timers (component unmount). */
  dispose(): void {
    clearTimeout(this.timer);
  }

  private show(next: RobotSnapshot, durationMs?: number) {
    clearTimeout(this.timer);
    this.timer = durationMs ? setTimeout(() => this.settle(), durationMs) : undefined;
    if (next.state === this.snapshot.state && next.caption === this.snapshot.caption) return;
    this.snapshot = next;
    this.listeners.forEach((listener) => listener());
  }

  /** Back to what should show when no short reaction is playing. */
  private settle() {
    const hover = { state: "support" as const, caption: "Ask Arivazhai about admissions" };
    this.show(this.busy ?? (this.hovering && this.rest.state === "idle" ? hover : this.rest));
  }
}
