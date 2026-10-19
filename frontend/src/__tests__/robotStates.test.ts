import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CYCLE_MS, reactionFor, RobotDirector, type ChatEvent, type RobotState } from "../robot/states";
import { answerResult, noAnswerResult } from "../test/fixtures";

const stateOf = (event: ChatEvent) => reactionFor(event)?.state;

describe("chat event -> animation state", () => {
  it("maps every chatbot event to the design's closest state", () => {
    expect(stateOf({ type: "opened" })).toBe("greet");
    expect(stateOf({ type: "typing" })).toBe("attend");
    expect(stateOf({ type: "retrieving" })).toBe("think");
    expect(stateOf({ type: "answered", result: answerResult })).toBe("answer");
    expect(stateOf({ type: "action" })).toBe("confirm");
    expect(stateOf({ type: "launcher-focus", on: true })).toBe("support");
    expect(stateOf({ type: "first-visit" })).toBe("greet");
    expect(stateOf({ type: "nudge" })).toBe("attend");
  });

  it("is honest about weak and missing answers and failures", () => {
    // related pages but no answer: ambiguous question
    expect(stateOf({ type: "answered", result: noAnswerResult })).toBe("unsure");
    // nothing in the knowledge base
    expect(stateOf({ type: "answered", result: { ...noAnswerResult, related_sources: [] } })).toBe("error");
    expect(stateOf({ type: "failed", kind: "invalid" })).toBe("unsure");
    for (const kind of ["network", "timeout", "rate_limited", "starting", "unavailable", "server"] as const) {
      expect(stateOf({ type: "failed", kind })).toBe("error");
    }
    expect(reactionFor({ type: "failed", kind: "network" })?.caption).toMatch(/can't reach/);
  });
});

describe("RobotDirector", () => {
  let director: RobotDirector;
  let seen: RobotState[];

  beforeEach(() => {
    vi.useFakeTimers();
    director = new RobotDirector();
    seen = [];
    director.subscribe(() => seen.push(director.getSnapshot().state));
  });

  afterEach(() => {
    director.dispose();
    vi.useRealTimers();
  });

  it("plays short reactions for one animation cycle, then rests", () => {
    director.emit({ type: "opened" });
    expect(director.getSnapshot().state).toBe("greet");
    vi.advanceTimersByTime(CYCLE_MS.greet - 1);
    expect(director.getSnapshot().state).toBe("greet");
    vi.advanceTimersByTime(1);
    expect(director.getSnapshot().state).toBe("idle");
  });

  it("thinks for exactly as long as the request runs, ignoring typing meanwhile", () => {
    director.emit({ type: "retrieving" });
    director.emit({ type: "typing" });
    director.emit({ type: "action" });
    vi.advanceTimersByTime(60_000);
    expect(director.getSnapshot().state).toBe("think");
    director.emit({ type: "answered", result: answerResult });
    expect(director.getSnapshot()).toMatchObject({ state: "answer", caption: expect.stringMatching(/official website/) });
    vi.advanceTimersByTime(CYCLE_MS.answer);
    expect(director.getSnapshot().state).toBe("idle");
    expect(seen).toEqual(["think", "answer", "idle"]);
  });

  it("keeps thinking visible when the panel is closed mid-search", () => {
    director.emit({ type: "retrieving" });
    director.emit({ type: "closed" });
    expect(director.getSnapshot().state).toBe("think");
    director.emit({ type: "answered", result: answerResult });
    vi.advanceTimersByTime(CYCLE_MS.answer);
    expect(director.getSnapshot().state).toBe("idle");
  });

  it("stays unsure or in error until the visitor moves on", () => {
    director.emit({ type: "retrieving" });
    director.emit({ type: "failed", kind: "network" });
    vi.advanceTimersByTime(60_000);
    expect(director.getSnapshot().state).toBe("error");
    director.emit({ type: "action" }); // short reactions return to the error rest
    vi.advanceTimersByTime(CYCLE_MS.confirm);
    expect(director.getSnapshot().state).toBe("error");
    director.emit({ type: "typing" });
    expect(director.getSnapshot().state).toBe("attend");
    vi.advanceTimersByTime(CYCLE_MS.attend);
    expect(director.getSnapshot().state).toBe("idle");
  });

  it("keeps listening while typing continues and greets on a new chat", () => {
    director.emit({ type: "typing" });
    vi.advanceTimersByTime(CYCLE_MS.attend - 100);
    director.emit({ type: "typing" });
    vi.advanceTimersByTime(CYCLE_MS.attend - 100);
    expect(director.getSnapshot().state).toBe("attend");
    expect(seen).toEqual(["attend"]); // no flicker between keystrokes
    director.emit({ type: "answered", result: noAnswerResult });
    expect(director.getSnapshot().state).toBe("unsure");
    director.emit({ type: "new-chat" });
    vi.advanceTimersByTime(CYCLE_MS.greet);
    expect(director.getSnapshot().state).toBe("idle");
  });

  it("reaches toward the chat while the launcher has focus", () => {
    director.emit({ type: "launcher-focus", on: true });
    expect(director.getSnapshot().state).toBe("support");
    director.emit({ type: "nudge" });
    vi.advanceTimersByTime(CYCLE_MS.attend);
    expect(director.getSnapshot().state).toBe("support"); // back to support, the pointer is still there
    director.emit({ type: "launcher-focus", on: false });
    expect(director.getSnapshot().state).toBe("idle");
  });
});
