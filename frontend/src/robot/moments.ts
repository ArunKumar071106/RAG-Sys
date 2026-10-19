import type { ApiErrorKind } from "../api/client";
import type { ChatResult } from "../api/types";

/** The six moments of the design (Moments.dc.html); each is a class on <svg class="rb">. */
export type MomentKind = "greet" | "load" | "think" | "error" | "net" | "unsure";

export interface Moment {
  id: number;
  kind: MomentKind;
  title: string;
  text: string;
}

/** From the design: 0.35 s fade and blur in, about 2.2 s hold, 0.4 s exit. */
export const ENTER_MS = 350;
export const HOLD_MS = 2200;
export const EXIT_MS = 400;
/** The loading moment stays at least this long, so it never just flickers. */
export const MIN_LOAD_MS = 1000;

/** Wording from the design, pointed at the official website the answers come from. */
export const MOMENT_TEXT: Record<MomentKind, { title: string; text: string }> = {
  greet: { title: "Vanakkam! I'm Arivazhai", text: "Your guide to AAACET admissions. Ask me anything." },
  load: { title: "Getting ready…", text: "Loading the official AAACET website content." },
  think: { title: "Finding your answer…", text: "Searching the official AAACET website." },
  error: { title: "Something went wrong", text: "Please try again in a moment." },
  net: { title: "You're offline", text: "Check your connection and try again." },
  unsure: { title: "I couldn't find that", text: "The admissions office can help you directly." },
};

type Cue = { kind: MomentKind; title?: string; text?: string };

const isOffline = () => typeof navigator !== "undefined" && navigator.onLine === false;

/** The moment for a failed request, worded for what actually went wrong. */
export function momentForFailure(kind: ApiErrorKind): Cue {
  if (isOffline()) return { kind: "net" };
  switch (kind) {
    case "network":
      return { kind: "error", title: "Can't reach the assistant", text: "Please check your connection and try again." };
    case "timeout":
      return { kind: "error", title: "That took too long", text: "Please try again in a moment." };
    case "rate_limited":
      return { kind: "error", title: "Too many questions at once", text: "Please wait a moment and try again." };
    case "starting":
      return { kind: "error", title: "Still getting ready", text: "Please try again in a minute." };
    case "invalid":
      return { kind: "unsure", title: "Could you rephrase that?", text: "Ask about admissions, courses, fees or campus life." };
    default:
      return { kind: "error" };
  }
}

/** Only an answer that is not on the website gets a moment; a real answer is simply shown. */
export function momentForResult(result: ChatResult): Cue | null {
  return result.mode === "no_answer" ? { kind: "unsure" } : null;
}

/**
 * Shows one moment at a time over the page: a newer moment replaces the one on screen and
 * restarts its timing. "sticky" moments (loading) stay until the next one replaces them.
 */
export class MomentStore {
  private current: Moment | null = null;
  private leaving = false;
  private shownAt = 0;
  private counter = 0;
  private timers: ReturnType<typeof setTimeout>[] = [];
  private listeners = new Set<() => void>();
  private snapshot = { moment: this.current, leaving: this.leaving };

  getSnapshot = () => this.snapshot;

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  show(cue: Cue, options: { sticky?: boolean } = {}): void {
    this.clearTimers();
    const base = MOMENT_TEXT[cue.kind];
    this.current = { id: ++this.counter, kind: cue.kind, title: cue.title ?? base.title, text: cue.text ?? base.text };
    this.leaving = false;
    this.shownAt = Date.now();
    this.emit();
    if (!options.sticky) this.timers.push(setTimeout(() => this.dismiss(), ENTER_MS + HOLD_MS));
  }

  /** Replace a sticky moment once it has been visible for at least minMs. */
  showAfter(cue: Cue, minMs: number): void {
    const wait = Math.max(0, this.shownAt + minMs - Date.now());
    if (!this.current || wait === 0) return this.show(cue);
    this.clearTimers();
    this.timers.push(setTimeout(() => this.show(cue), wait));
  }

  /** Float away now (Esc, or the hold is over). */
  dismiss(): void {
    if (!this.current || this.leaving) return;
    this.clearTimers();
    this.leaving = true;
    this.emit();
    this.timers.push(
      setTimeout(() => {
        this.current = null;
        this.leaving = false;
        this.emit();
      }, EXIT_MS),
    );
  }

  get kind(): MomentKind | null {
    return this.current?.kind ?? null;
  }

  dispose(): void {
    this.clearTimers();
  }

  private clearTimers() {
    this.timers.forEach(clearTimeout);
    this.timers = [];
  }

  private emit() {
    this.snapshot = { moment: this.current, leaving: this.leaving };
    this.listeners.forEach((listener) => listener());
  }
}

/** The page's one robot: chat components report to it, the overlay shows it. */
export const moments = new MomentStore();
