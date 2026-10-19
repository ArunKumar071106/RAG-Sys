import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatWidget, widgetFrameSize } from "../components/ChatWidget";
import { answerResult, jsonResponse, noAnswerResult } from "../test/fixtures";

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

/** The one robot rig on the page and its animation state. */
function robots() {
  return Array.from(document.querySelectorAll("svg.rb"));
}
const robotState = () => robots()[0]?.getAttribute("data-state");

describe("ChatWidget", () => {
  it("moves the single robot from the launcher into the panel and back", async () => {
    const user = userEvent.setup();
    render(<ChatWidget />);
    const launcher = screen.getByRole("button", { name: "Ask Arivazhai about admissions" });
    expect(launcher).toHaveAttribute("aria-expanded", "false");
    expect(robots()).toHaveLength(1);
    expect(launcher.querySelector("svg.rb")).not.toBeNull();

    await user.click(launcher);
    const panel = screen.getByRole("dialog", { name: "Arivazhai chat" });
    expect(robots()).toHaveLength(1);
    expect(panel.querySelector("svg.rb")).not.toBeNull();
    expect(robotState()).toBe("greet");
    await waitFor(() => expect(screen.getByLabelText("Ask a question about AAACET")).toHaveFocus());

    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog", { hidden: true })).not.toBeVisible();
    expect(robots()).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Ask Arivazhai about admissions" })).toHaveFocus();
  });

  it("reacts to typing, retrieval and the answer, and confirms opening a source", async () => {
    const pending = deferred<Response>();
    vi.stubGlobal("fetch", vi.fn((url: string) => (String(url).includes("/api/suggest") ? Promise.resolve(jsonResponse({ suggestions: [] })) : pending.promise)));
    const user = userEvent.setup();
    render(<ChatWidget />);
    await user.click(screen.getByRole("button", { name: "Ask Arivazhai about admissions" }));

    const box = screen.getByLabelText("Ask a question about AAACET");
    await user.type(box, "How do I get admission?");
    expect(robotState()).toBe("attend");
    expect(screen.getByText("Listening…")).toBeInTheDocument();

    await user.keyboard("{Enter}");
    expect(robotState()).toBe("think");
    pending.resolve(jsonResponse(answerResult));
    await screen.findByText("TNEA counselling");
    expect(robotState()).toBe("answer");
    expect(screen.getByText("Here's what the official website says")).toBeInTheDocument();

    const source = screen.getByRole("link", { name: /Source 1: Admissions/ });
    source.addEventListener("click", (e) => e.preventDefault()); // jsdom cannot open tabs
    await user.click(source);
    expect(robotState()).toBe("confirm");
  });

  it("is unsure about ambiguous questions and shows the error state on failures", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(noAnswerResult)).mockRejectedValueOnce(new TypeError("offline"));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ChatWidget open />);

    await user.click(screen.getByRole("button", { name: "Tell me about placements and recruiters" }));
    await screen.findByText(/These official pages may be related/);
    expect(robotState()).toBe("unsure");

    await user.type(screen.getByLabelText("Ask a question about AAACET"), "fees{Enter}");
    await screen.findByText(/Can't reach the assistant/);
    expect(robotState()).toBe("error");
    expect(screen.getByText("I can't reach the server right now")).toBeInTheDocument();
  });

  it("greets on the first visit only", () => {
    vi.useFakeTimers();
    try {
      const { unmount } = render(<ChatWidget />);
      expect(robotState()).toBe("idle");
      act(() => void vi.advanceTimersByTime(2000));
      expect(robotState()).toBe("greet");
      unmount();
      render(<ChatWidget />);
      act(() => void vi.advanceTimersByTime(2000));
      expect(robotState()).toBe("idle");
    } finally {
      vi.useRealTimers();
    }
  });

  it("uses the head-only disc on narrow screens and opens full screen", () => {
    const width = window.innerWidth;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    try {
      render(<ChatWidget />);
      const launcher = screen.getByRole("button", { name: "Ask Arivazhai about admissions" });
      expect(launcher).toHaveClass("widget__launcher--disc");
      expect(robots()).toHaveLength(0); // the disc is the design's head-only icon
      fireEvent.click(launcher);
      expect(robots()).toHaveLength(1);
      expect(document.querySelector(".widget")).toHaveClass("is-narrow");
    } finally {
      Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
    }
  });

  it("asks the loader for an iframe just big enough", () => {
    const desktop = { width: 1366, height: 900 };
    expect(widgetFrameSize(false, false, false, desktop)).toEqual({ width: "150px", height: "160px" });
    expect(widgetFrameSize(false, false, true, desktop).width).toBe("380px");
    expect(widgetFrameSize(true, false, false, desktop)).toEqual({ width: "440px", height: "760px" });
    expect(widgetFrameSize(true, true, false, { width: 390, height: 844 })).toEqual({ width: "100%", height: "100%" });
  });
});
