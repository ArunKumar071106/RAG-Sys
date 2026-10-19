import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatWindow } from "../components/ChatWindow";
import { DEFAULT_SUGGESTIONS } from "../components/SuggestedQuestions";
import { answerResult, jsonResponse, noAnswerResult } from "../test/fixtures";

afterEach(() => vi.unstubAllGlobals());

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe("ChatWindow", () => {
  it("shows the welcome message and suggested questions", () => {
    render(<ChatWindow />);
    expect(screen.getByText(/Welcome! I'm the AAACET Virtual Assistant/)).toBeInTheDocument();
    for (const q of DEFAULT_SUGGESTIONS) expect(screen.getByRole("button", { name: q })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  });

  it("sends with Enter, shows loading, then the answer with citations, sources and images", async () => {
    const pending = deferred<Response>();
    const fetchMock = vi.fn().mockReturnValue(pending.promise);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ChatWindow />);

    await user.type(screen.getByLabelText("Ask a question about AAACET"), "How do I get admission?{Enter}");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText("How do I get admission?")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Searching the official website");
    expect(screen.getByLabelText("Ask a question about AAACET")).toHaveValue("");

    pending.resolve(jsonResponse(answerResult));
    await screen.findByText("TNEA counselling");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    const citation = screen.getByRole("link", { name: /Source 1: Admissions/ });
    expect(citation).toHaveAttribute("href", "https://aaaenggcoll.ac.in/admission");
    expect(citation).toHaveAttribute("target", "_blank");
    expect(citation).toHaveAttribute("rel", "noopener noreferrer");

    const sources = screen.getByRole("region", { name: "Sources from the official website" });
    expect(within(sources).getByRole("link", { name: /Admissions - Admission Process/ })).toHaveAttribute("href", "https://aaaenggcoll.ac.in/admission");
    expect(within(sources).getByRole("link", { name: /Fee Structure/ })).toBeInTheDocument();

    const image = screen.getByRole("img", { name: "Admission notice" });
    expect(image.getAttribute("src")).toMatch(/\/api\/images\/img1\/file$/);
    expect(screen.getByText("AI-generated description")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View source page/ })).toHaveAttribute("href", "https://aaaenggcoll.ac.in/admission");
    // suggestions disappear once the conversation started
    expect(screen.queryByRole("button", { name: DEFAULT_SUGGESTIONS[0] })).not.toBeInTheDocument();
  });

  it("does not send on Shift+Enter or for blank input", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ChatWindow />);
    const box = screen.getByLabelText("Ask a question about AAACET");
    await user.type(box, "   {Enter}");
    await user.type(box, "line one{Shift>}{Enter}{/Shift}line two");
    expect(fetchMock).not.toHaveBeenCalled();
    // the blank message stays in the box; Shift+Enter inserted a newline instead of sending
    expect(box).toHaveValue("   line one\nline two");
  });

  it("sends a suggested question when clicked and passes history on follow-ups", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(answerResult)));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ChatWindow />);
    await user.click(screen.getByRole("button", { name: DEFAULT_SUGGESTIONS[1] }));
    await screen.findByText("TNEA counselling");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ message: DEFAULT_SUGGESTIONS[1], history: [] });

    await user.type(screen.getByLabelText("Ask a question about AAACET"), "and the fees?{Enter}");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const second = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(second.history).toEqual([
      { role: "user", content: DEFAULT_SUGGESTIONS[1] },
      { role: "assistant", content: answerResult.answer },
    ]);
  });

  it("shows a network error with a working retry", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(jsonResponse(answerResult));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ChatWindow />);
    await user.type(screen.getByLabelText("Ask a question about AAACET"), "Hostel details?{Enter}");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Can't reach the assistant");
    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    await screen.findByText("TNEA counselling");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ message: "Hostel details?", history: [] });
    expect(screen.getAllByText("Hostel details?")).toHaveLength(1);
  });

  it("renders the no-answer state with related official pages", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(noAnswerResult)));
    const user = userEvent.setup();
    render(<ChatWindow />);
    await user.type(screen.getByLabelText("Ask a question about AAACET"), "Cafeteria menu?{Enter}");
    await screen.findByText(/couldn't find this in the official AAACET website/);
    const related = screen.getByRole("region", { name: "These official pages may be related" });
    expect(within(related).getByRole("link")).toHaveAttribute("href", "https://aaaenggcoll.ac.in/admission");
    expect(screen.queryByRole("region", { name: "Related images from the official website" })).not.toBeInTheDocument();
  });

  it("starts a new chat", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(answerResult)));
    const user = userEvent.setup();
    render(<ChatWindow />);
    const newChat = screen.getByRole("button", { name: "New chat" });
    expect(newChat).toBeDisabled();
    await user.type(screen.getByLabelText("Ask a question about AAACET"), "Admissions?{Enter}");
    await screen.findByText("TNEA counselling");
    await user.click(newChat);
    expect(screen.queryByText("TNEA counselling")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: DEFAULT_SUGGESTIONS[0] })).toBeInTheDocument();
    expect(screen.getByLabelText("Ask a question about AAACET")).toHaveFocus();
  });
});
