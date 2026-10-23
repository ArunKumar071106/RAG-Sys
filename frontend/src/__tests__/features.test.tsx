import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { ChatWindow } from "../components/ChatWindow";
import { formatPhone } from "../components/ContactCard";
import { moments } from "../robot/moments";
import { answerResult, jsonResponse, noAnswerResult } from "../test/fixtures";

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => moments.dismiss());
});

const box = () => screen.getByLabelText("Ask a question about AAACET");

describe("answers in the question's language, with an English version", () => {
  it("shows 'Show in English' on a translatable answer and switches back", async () => {
    const tamil = { ...answerResult, answer: "சேர்க்கை **TNEA கலந்தாய்வு** மூலம் [S1].", translatable: true, images: [] };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(tamil))
      .mockResolvedValueOnce(jsonResponse({ text: "Admission is through **TNEA counselling** [S1]." }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ChatWindow />);
    await user.type(box(), "சேர்க்கை எப்படி?{Enter}");
    await screen.findByText("TNEA கலந்தாய்வு");

    await user.click(screen.getByRole("button", { name: /Show in English/ }));
    expect(await screen.findByText("TNEA counselling")).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ text: tamil.answer, target: "English" });
    expect(screen.getByRole("link", { name: /Source 1: Admissions/ })).toBeInTheDocument(); // citations still link

    await user.click(screen.getByRole("button", { name: /Show original/ }));
    expect(screen.getByText("TNEA கலந்தாய்வு")).toBeInTheDocument();
  });

  it("has no translate button on English answers", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(answerResult)));
    const user = userEvent.setup();
    render(<ChatWindow />);
    await user.type(box(), "How do I get admission?{Enter}");
    await screen.findByText("TNEA counselling");
    expect(screen.queryByRole("button", { name: /Show in English/ })).not.toBeInTheDocument();
  });
});

describe("contact details", () => {
  it("gives the phone numbers and email when the website does not cover a question", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(noAnswerResult)));
    const user = userEvent.setup();
    render(<ChatWindow />);
    await user.type(box(), "canteen menu?{Enter}");
    const card = await screen.findByRole("region", { name: "The admission office can help you directly" });
    expect(within(card).getByRole("link", { name: "04562-251111" })).toHaveAttribute("href", "tel:04562251111");
    expect(within(card).getByRole("link", { name: "1800 425 8807" })).toHaveAttribute("href", "tel:18004258807");
    expect(within(card).getByRole("link", { name: "enquiry@aaacet.ac.in" })).toHaveAttribute("href", "mailto:enquiry@aaacet.ac.in");
    expect(within(card).getByRole("link", { name: "04562-251112" })).toHaveAttribute("href", "tel:04562251112");
    expect(within(card).getByRole("link", { name: "admissions@aaacet.ac.in" })).toBeInTheDocument();
    // the website has no answer: the admission and scholarship staff can help
    expect(within(card).getByText("Mr. R. Chandhran")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "7373527252" })).toHaveAttribute("href", "tel:7373527252");
    expect(formatPhone("18004258807")).toBe("1800 425 8807");
  });

  it("adds them to answers about contacting the college", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(answerResult)));
    const user = userEvent.setup();
    render(<ChatWindow />);
    await user.type(box(), "How can I contact the admission office?{Enter}");
    const card = await screen.findByRole("region", { name: "Contact the college" });
    expect(within(card).getByText("Admission & scholarship")).toBeInTheDocument();
  });

  it("leaves the admission staff out of other contact questions", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(answerResult)));
    const user = userEvent.setup();
    render(<ChatWindow />);
    await user.type(box(), "What is the college phone number?{Enter}");
    const card = await screen.findByRole("region", { name: "Contact the college" });
    expect(within(card).getByRole("link", { name: "04562-251111" })).toBeInTheDocument();
    expect(within(card).queryByText("Admission & scholarship")).not.toBeInTheDocument();
  });
});

describe("suggested next questions", () => {
  it("offers full questions under the latest answer only, and asks the one picked", async () => {
    const first = { ...answerResult, follow_ups: ["What are the tuition fees?", "What scholarships are available for students?"] };
    const second = { ...answerResult, follow_ups: ["How do I apply for admission?"] };
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(first)).mockResolvedValueOnce(jsonResponse(second));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ChatWindow />);
    await user.type(box(), "How do I get admission?{Enter}");
    await user.click(await screen.findByRole("button", { name: "What are the tuition fees?" }));
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).message).toBe("What are the tuition fees?");
    expect(await screen.findByRole("button", { name: "How do I apply for admission?" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "What scholarships are available for students?" })).not.toBeInTheDocument();
    // the earlier question goes with the follow-up, so the answer can build on it
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).history[0]).toEqual({ role: "user", content: "How do I get admission?" });
  });
});

describe("the Arivazhai menu link", () => {
  it("brings the chat into view and puts the cursor in the question box, without a robot moment", async () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    const user = userEvent.setup();
    render(<App />);
    expect(screen.queryByRole("button", { name: /Start chat with Arivazhai/ })).not.toBeInTheDocument();
    await user.click(within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", { name: "Arivazhai" }));
    expect(box()).toHaveFocus();
    expect(scroll).toHaveBeenCalled();
    expect(moments.kind).toBe("load"); // still the page's loading moment: the click adds none
  });
});

describe("down arrow to the chat", () => {
  it("shows while the chat is below the screen, takes you there, and hides once it is in view", async () => {
    let callback!: (entries: Partial<IntersectionObserverEntry>[]) => void;
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(cb: typeof callback) {
          callback = cb;
        }
        observe() {}
        disconnect() {}
      },
    );
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    Element.prototype.scrollIntoView = vi.fn();
    const user = userEvent.setup();
    render(<App />);
    const arrow = screen.getByRole("button", { name: "Go to the chat below" });
    await user.click(arrow);
    expect(box()).toHaveFocus();
    act(() => callback([{ isIntersecting: true, boundingClientRect: { top: 400 } as DOMRectReadOnly }]));
    expect(screen.queryByRole("button", { name: "Go to the chat below" })).not.toBeInTheDocument();
    act(() => callback([{ isIntersecting: false, boundingClientRect: { top: -300 } as DOMRectReadOnly }]));
    expect(screen.queryByRole("button", { name: "Go to the chat below" })).not.toBeInTheDocument(); // scrolled past
    act(() => callback([{ isIntersecting: false, boundingClientRect: { top: 1200 } as DOMRectReadOnly }]));
    expect(screen.getByRole("button", { name: "Go to the chat below" })).toBeInTheDocument();
  });
});
