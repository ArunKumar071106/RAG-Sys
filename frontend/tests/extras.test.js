import { afterEach, describe, expect, it, vi } from "vitest";
import { answerResult, flush, jsonResponse, loadPage, noAnswerResult } from "./load.js";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const field = () => $("#chat-message");

function ask(text) {
  field().value = text;
  field().dispatchEvent(new Event("input", { bubbles: true }));
  field().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
}

afterEach(() => {
  window.localStorage.clear();
  delete window.SpeechRecognition;
  delete window.webkitSpeechRecognition;
});

describe("feedback on answers", () => {
  it("sends 👍, and 👎 with what was wrong", async () => {
    const fetchMock = vi.fn((url) => Promise.resolve(jsonResponse(String(url).includes("/api/feedback") ? { ok: true } : answerResult)));
    loadPage(fetchMock);
    ask("How do I get admission?");
    await flush();
    await flush();
    const feedbackCalls = () =>
      fetchMock.mock.calls.filter(([url]) => String(url).includes("/api/feedback")).map(([, init]) => JSON.parse(init.body));

    $('button[aria-label="No, not helpful"]').click();
    const comment = $(".feedback input");
    comment.value = "No fee amount";
    $(".feedback form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    expect(feedbackCalls()).toEqual([
      { question: "How do I get admission?", answer: answerResult.answer, rating: "down", comment: "No fee amount" },
    ]);
    expect($(".feedback").textContent).toContain("Thank you");

    ask("Second question");
    await flush();
    await flush();
    $$('button[aria-label="Yes, helpful"]').pop().click();
    expect(feedbackCalls().pop()).toMatchObject({ question: "Second question", rating: "up" });
  });
});

describe("talking to a person", () => {
  it("offers call and email under an answer, and the full contact card when the website has no answer", async () => {
    let reply = answerResult;
    loadPage(() => Promise.resolve(jsonResponse(reply)));
    ask("What are the hostel facilities?");
    await flush();
    await flush();
    const links = $$(".talk a").map((a) => a.getAttribute("href"));
    expect(links).toEqual(["tel:04562251111", "mailto:admissions@aaacet.ac.in"]); // no WhatsApp until a number is set
    reply = noAnswerResult;
    ask("zzqx");
    await flush();
    await flush();
    const last = $$(".message--assistant").pop();
    expect(last.querySelector(".contact-card")).not.toBeNull();
    expect(last.querySelector(".talk")).toBeNull(); // not twice
  });
});

describe("asking by voice", () => {
  it("is hidden where the browser cannot listen", () => {
    loadPage();
    expect($(".chat-input__mic").hidden).toBe(true);
  });

  it("puts the spoken words in the question box, in the chat's language", () => {
    const made = [];
    window.SpeechRecognition = class {
      constructor() {
        made.push(this);
      }
      start() {}
      stop() {
        this.onend();
      }
    };
    loadPage();
    const mic = $(".chat-input__mic");
    expect(mic.hidden).toBe(false);
    mic.click();
    expect(made[0].lang).toBe("en-IN");
    expect(mic.getAttribute("aria-pressed")).toBe("true");
    expect($(".chat-input__status").textContent).toContain("Listening");
    made[0].onresult({ results: [[{ transcript: "hostel fees" }]] });
    expect(field().value).toBe("hostel fees");
    expect($(".chat-input__send").disabled).toBe(false);
    made[0].onend();
    expect(mic.getAttribute("aria-pressed")).toBe("false");
    made.length = 0;
    $(".chat__lang").click(); // Tamil
    mic.click();
    expect(made[0].lang).toBe("ta-IN");
  });

  it("says when the microphone is blocked", () => {
    window.webkitSpeechRecognition = class {
      start() {
        this.onerror({ error: "not-allowed" });
      }
    };
    loadPage();
    $(".chat-input__mic").click();
    expect($(".chat-input__status").textContent).toContain("Microphone access was blocked");
  });
});

describe("Tamil", () => {
  it("switches the chat's words and questions to Tamil and remembers it", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(answerResult)));
    loadPage(fetchMock);
    const lang = $(".chat__lang");
    expect(lang.textContent).toBe("தமிழ்");
    lang.click();
    expect(lang.textContent).toBe("English");
    expect($$("#welcome-suggestions .chip")[3].textContent).toBe("ஆன்லைனில் சேர்க்கைக்கு எப்படி விண்ணப்பிப்பது?");
    expect(field().getAttribute("placeholder")).toContain("கேளுங்கள்");
    expect($(".chat__new").textContent).toBe("புதிய உரையாடல்");
    expect(window.localStorage.getItem("arivazhai-lang")).toBe("ta");

    $$("#welcome-suggestions .chip")[3].click(); // asked in Tamil: the AI model answers in Tamil
    await flush();
    await flush();
    const asked = JSON.parse(fetchMock.mock.calls.find(([url]) => String(url).includes("/api/chat"))[1].body);
    expect(asked.message).toBe("ஆன்லைனில் சேர்க்கைக்கு எப்படி விண்ணப்பிப்பது?");
    expect($(".feedback").textContent).toContain("உதவியாக");

    loadPage(); // the next visit opens in Tamil
    expect($(".chat__lang").textContent).toBe("English");
  });
});
