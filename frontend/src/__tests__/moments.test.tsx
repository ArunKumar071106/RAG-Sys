import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatWindow, QUICK_TOPICS } from "../components/ChatWindow";
import { ENTER_MS, EXIT_MS, HOLD_MS, MIN_LOAD_MS, MomentStore, momentForFailure, momentForResult, moments } from "../robot/moments";
import { RobotMoments } from "../robot/RobotMoments";
import { answerResult, jsonResponse, noAnswerResult } from "../test/fixtures";

const shown = () => document.querySelector(".mov")?.getAttribute("data-moment") ?? null;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  act(() => moments.dismiss());
});

describe("moment mapping", () => {
  it("shows no moment for a real answer and 'no data' when the website does not cover it", () => {
    expect(momentForResult(answerResult)).toBeNull();
    expect(momentForResult(noAnswerResult)?.kind).toBe("unsure");
  });

  it("tells offline, unreachable, busy and invalid apart", () => {
    expect(momentForFailure("network")).toMatchObject({ kind: "error", title: "Can't reach the assistant" });
    expect(momentForFailure("timeout").kind).toBe("error");
    expect(momentForFailure("rate_limited").title).toMatch(/Too many/);
    expect(momentForFailure("starting").title).toMatch(/getting ready/);
    expect(momentForFailure("invalid").kind).toBe("unsure");
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    expect(momentForFailure("network").kind).toBe("net");
  });
});

describe("MomentStore", () => {
  beforeEach(() => void vi.useFakeTimers());

  it("pops in, holds about 2.2 s, floats away, then is gone (2 to 4 s in all)", () => {
    const store = new MomentStore();
    store.show({ kind: "think" });
    expect(store.getSnapshot()).toMatchObject({ moment: { kind: "think", title: "Finding your answer…" }, leaving: false });
    vi.advanceTimersByTime(ENTER_MS + HOLD_MS - 1);
    expect(store.getSnapshot().leaving).toBe(false);
    vi.advanceTimersByTime(1);
    expect(store.getSnapshot().leaving).toBe(true);
    vi.advanceTimersByTime(EXIT_MS);
    expect(store.getSnapshot().moment).toBeNull();
    expect(ENTER_MS + HOLD_MS + EXIT_MS).toBeGreaterThanOrEqual(2000);
    expect(ENTER_MS + HOLD_MS + EXIT_MS).toBeLessThanOrEqual(4000);
  });

  it("a newer moment replaces the one on screen; loading stays until replaced, at least briefly", () => {
    const store = new MomentStore();
    store.show({ kind: "load" }, { sticky: true });
    vi.advanceTimersByTime(60_000);
    expect(store.kind).toBe("load");
    store.show({ kind: "error" });
    expect(store.kind).toBe("error");

    store.show({ kind: "load" }, { sticky: true });
    store.showAfter({ kind: "greet" }, MIN_LOAD_MS);
    vi.advanceTimersByTime(MIN_LOAD_MS - 1);
    expect(store.kind).toBe("load");
    vi.advanceTimersByTime(1);
    expect(store.kind).toBe("greet");
  });
});

describe("RobotMoments on the page", () => {
  it("loads, then welcomes, centred over the page", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ status: "ok" })));
    render(<RobotMoments />);
    expect(shown()).toBe("load");
    expect(screen.getByText("Getting ready…")).toBeInTheDocument();
    expect(await screen.findByText("Vanakkam! I'm Arivazhai", {}, { timeout: MIN_LOAD_MS + 1000 })).toBeInTheDocument();
    expect(shown()).toBe("greet");
  });

  it("says when the assistant cannot be reached, and Esc dismisses it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const user = userEvent.setup();
    render(<RobotMoments />);
    expect(await screen.findByText("Can't reach the assistant", {}, { timeout: MIN_LOAD_MS + 1000 })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(document.querySelector(".moment")).toHaveClass("is-leaving");
  });

  it("shows 'no network' when the device goes offline", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    render(<RobotMoments />);
    act(() => void window.dispatchEvent(new Event("offline")));
    expect(shown()).toBe("net");
    expect(screen.getByText("You're offline")).toBeInTheDocument();
  });
});

describe("chat events bring the robot in", () => {
  it("thinks when a question is sent and says 'no data' when the website does not cover it", async () => {
    let reply!: (r: Response) => void;
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise<Response>((r) => (reply = r))));
    const user = userEvent.setup();
    render(
      <>
        <ChatWindow />
        <RobotMoments />
      </>,
    );
    act(() => moments.dismiss());
    await user.click(screen.getByRole("button", { name: QUICK_TOPICS[1].label }));
    expect(screen.getByText(QUICK_TOPICS[1].question)).toBeInTheDocument(); // the topic asked its question
    expect(shown()).toBe("think");
    await act(async () => reply(jsonResponse(noAnswerResult)));
    expect(shown()).toBe("unsure");
    expect(screen.getByText("I couldn't find that")).toBeInTheDocument();
  });

  it("shows the error moment when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => (String(url).includes("/api/chat") ? Promise.reject(new TypeError("Failed to fetch")) : new Promise(() => {}))),
    );
    const user = userEvent.setup();
    render(
      <>
        <ChatWindow />
        <RobotMoments />
      </>,
    );
    await user.type(screen.getByLabelText("Ask a question about AAACET"), "fees{Enter}");
    await screen.findByRole("alert");
    expect(shown()).toBe("error");
  });
});
