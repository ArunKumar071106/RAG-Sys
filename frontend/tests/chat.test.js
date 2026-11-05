import { describe, expect, it, vi } from "vitest";
import { answerResult, deferred, flush, jsonResponse, loadPage, noAnswerResult } from "./load.js";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const field = () => $("#chat-message");
const buttonNamed = (text) => $$("button").find((b) => b.textContent.trim() === text);

function type(text, key = "Enter", init = {}) {
  field().value = text;
  field().dispatchEvent(new Event("input", { bubbles: true }));
  field().dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init }));
}

const chatCalls = (fetchMock) => fetchMock.mock.calls.filter(([url]) => String(url).includes("/api/chat"));

describe("the chat", () => {
  it("welcomes with the parents' admission questions", () => {
    loadPage();
    expect($(".chat__log").textContent).toContain("Vanakkam! I'm Arivazhai, the AAACET admission assistant");
    expect($$("#welcome-suggestions .chip").map((b) => b.textContent)).toContain("How do I apply for admission online?");
    expect($(".chat-input__send").disabled).toBe(true);
    expect($(".chat__new").disabled).toBe(true);
    expect($(".chat__header svg.rb")).not.toBeNull(); // the robot's face is drawn
  });

  it("sends with Enter, shows the search, then the answer with citations, sources and photos", async () => {
    const pending = deferred();
    const fetchMock = vi.fn(() => pending.promise);
    loadPage(fetchMock);

    type("How do I get admission?");
    expect(chatCalls(fetchMock)).toHaveLength(1);
    expect(JSON.parse(chatCalls(fetchMock)[0][1].body)).toEqual({ message: "How do I get admission?", history: [] });
    expect($(".message--user").textContent).toContain("How do I get admission?");
    expect($('[role="status"]').textContent).toContain("Searching the official website");
    expect(field().value).toBe("");
    expect($("#welcome-suggestions").hidden).toBe(true);

    pending.resolve(jsonResponse(answerResult));
    await flush();
    await flush();
    expect($('[role="status"]')).toBeNull();
    expect($(".markdown strong").textContent).toBe("TNEA counselling");
    const citation = $("a.citation");
    expect(citation.getAttribute("href")).toBe("https://aaaenggcoll.ac.in/admission");
    expect(citation.getAttribute("title")).toBe("Source 1: Admissions");
    const sources = $('section[aria-label="Sources from the official website"]');
    expect(sources.textContent).toContain("Admissions - Admission Process");
    expect(sources.textContent).toContain("Fee Structure");
    const image = $(".image-card img");
    expect(image.getAttribute("src")).toMatch(/\/api\/images\/img1\/file$/);
    expect(image.getAttribute("alt")).toBe("Admission notice");
    expect($(".tag--ai").textContent).toBe("AI-generated description");
    expect($("a.citation--image").getAttribute("href")).toBe(`#${$(".image-card").id}`);
    // admission questions: no contact card unless it asks for a contact
    expect($(".contact-card")).toBeNull();
    // "You can also ask" under the answer, and it asks
    expect($(".message--assistant > .suggestions").textContent).toContain("What documents are needed for admission?");
    expect($(".chat__new").disabled).toBe(false);
  });

  it("does not send on Shift+Enter or a blank question", () => {
    const fetchMock = vi.fn(() => new Promise(() => {}));
    loadPage(fetchMock);
    type("hello", "Enter", { shiftKey: true });
    type("   ");
    expect(chatCalls(fetchMock)).toHaveLength(0);
  });

  it("says what went wrong and asks again with Try again", async () => {
    let calls = 0;
    const fetchMock = vi.fn(() => (++calls === 1 ? Promise.reject(new TypeError("Failed to fetch")) : Promise.resolve(jsonResponse(answerResult))));
    loadPage(fetchMock);
    type("What are the library timings?");
    await flush();
    expect($('[role="alert"]').textContent).toContain("Can't reach the assistant");
    buttonNamed("Try again").click();
    await flush();
    await flush();
    expect($('[role="alert"]')).toBeNull();
    expect($$(".message--user")).toHaveLength(1); // the question is asked again, not repeated
    expect(JSON.parse(chatCalls(fetchMock)[1][1].body)).toEqual({ message: "What are the library timings?", history: [] });
  });

  it("sends the earlier turns, offers next questions under the latest answer only, and New chat starts over", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(answerResult)));
    loadPage(fetchMock);
    type("First question");
    await flush();
    await flush();
    $(".message--assistant > .suggestions .chip").click();
    await flush();
    await flush();
    const second = JSON.parse(chatCalls(fetchMock)[1][1].body);
    expect(second.message).toBe("What documents are needed for admission?");
    expect(second.history.map((t) => t.role)).toEqual(["user", "assistant"]);
    expect($$(".message--assistant > .suggestions")).toHaveLength(1);

    buttonNamed("New chat").click();
    expect($$(".message--user")).toHaveLength(0);
    expect($("#welcome-suggestions").hidden).toBe(false);
    expect(document.activeElement).toBe(field());
  });

  it("not on the website: related pages and the admission office's contacts", async () => {
    loadPage(() => Promise.resolve(jsonResponse(noAnswerResult)));
    type("zzqx");
    await flush();
    await flush();
    expect($('section[aria-label="These official pages may be related"]')).not.toBeNull();
    const card = $(".contact-card");
    expect(card.textContent).toContain("The admission office can help you directly");
    expect($$(".contact-card a").map((a) => a.getAttribute("href"))).toContain("tel:18004258807");
    expect(card.textContent).toContain("1800 425 8807");
    expect(card.textContent).toContain("Mr. R. Chandhran");
  });

  it("photo questions show the photos before the text", async () => {
    loadPage(() => Promise.resolve(jsonResponse(answerResult)));
    type("Show me photos of the library");
    await flush();
    await flush();
    const bubble = $(".message--assistant:last-of-type .bubble");
    const order = [...bubble.children].map((c) => c.className);
    expect(order.indexOf("images")).toBeLessThan(order.indexOf("markdown"));
  });

  it("shows an answer in another language in English on request", async () => {
    const fetchMock = vi.fn((url) =>
      String(url).includes("/api/translate") ? Promise.resolve(jsonResponse({ text: "Hostels are available." })) : Promise.resolve(jsonResponse({ ...answerResult, answer: "விடுதி உள்ளது.", translatable: true })),
    );
    loadPage(fetchMock);
    type("விடுதி உள்ளதா?");
    await flush();
    await flush();
    $(".translate__button").click();
    await flush();
    await flush();
    expect($(".markdown").textContent).toBe("Hostels are available.");
    expect($(".translate__button").textContent).toContain("Show original");
    $(".translate__button").click();
    expect($(".markdown").textContent).toBe("விடுதி உள்ளது.");
  });

  it("suggests questions while typing; arrows pick one and Enter asks it", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn((url) =>
      String(url).includes("/api/suggest") ? Promise.resolve(jsonResponse({ suggestions: ["Are hostels available for boys and girls?", "Hostel fees"] })) : new Promise(() => {}),
    );
    loadPage(fetchMock);
    field().value = "hos";
    field().dispatchEvent(new Event("input", { bubbles: true }));
    await vi.advanceTimersByTimeAsync(200);
    vi.useRealTimers();
    await flush();
    const options = $$("#chat-suggestions [role=option]");
    expect(options.map((o) => o.textContent)).toEqual(["Are hostels available for boys and girls?", "Hostel fees"]);
    expect(options[0].querySelector("strong").textContent).toBe("hostels");
    field().dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }));
    expect(field().getAttribute("aria-activedescendant")).toBe(options[0].id);
    field().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    expect(JSON.parse(chatCalls(fetchMock)[0][1].body).message).toBe("Are hostels available for boys and girls?");
    expect($("#chat-suggestions").hidden).toBe(true);
  });
});

describe("the history sent with a question", () => {
  it("keeps successful turns only, the last 12, each cut to 2,000 characters", () => {
    const { chat } = loadPage();
    const messages = [
      { role: "user", content: "a" },
      { role: "assistant", content: "", error: { message: "x" } },
      ...Array.from({ length: 14 }, (_, i) => ({ role: i % 2 ? "assistant" : "user", content: String(i).repeat(i === 13 ? 3000 : 1) })),
    ];
    const history = chat.historyFrom(messages);
    expect(history).toHaveLength(12);
    expect(history.at(-1).content).toHaveLength(2000);
  });
});

describe("the API client", () => {
  it("words each failure for people", async () => {
    const { api } = loadPage();
    const failWith = async (status, headers = {}, body = {}) => {
      window.fetch = () => Promise.resolve(jsonResponse(body, status, headers));
      try {
        await api.sendChat("q", []);
      } catch (err) {
        return err.kind;
      }
    };
    expect(await failWith(429)).toBe("rate_limited");
    expect(await failWith(503, { "Retry-After": "30" })).toBe("starting");
    expect(await failWith(503)).toBe("unavailable");
    expect(await failWith(422, {}, { detail: "Message too long" })).toBe("invalid");
    expect(await failWith(500)).toBe("server");
  });
});
