import { afterEach, describe, expect, it, vi } from "vitest";
import { answerResult, flush, jsonResponse, loadPage } from "./load.js";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const field = () => $("#chat-message");
const section = () => $("#assistant");

function ask(text) {
  field().value = text;
  field().dispatchEvent(new Event("input", { bubbles: true }));
  field().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
}

function signInWith(name, phone) {
  $("#login-name").value = name;
  $("#login-phone").value = phone;
  $(".chat-login").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
}

/** The backend: /api/users signs in, /api/chat answers (or says the sign-in is no longer valid). */
function backend({ chatStatus = 200 } = {}) {
  return vi.fn((url, init) => {
    if (String(url).includes("/api/users")) {
      const body = JSON.parse(init.body);
      return Promise.resolve(jsonResponse({ name: body.name, token: "0123456789abcdef.signature" }));
    }
    return Promise.resolve(chatStatus === 200 ? jsonResponse(answerResult) : jsonResponse({ detail: "Please sign in" }, chatStatus));
  });
}

afterEach(() => {
  window.localStorage.clear();
  delete window.SpeechRecognition;
  vi.useRealTimers();
});

describe("signing in", () => {
  it("asks for a name and mobile number before the chat", async () => {
    const fetchMock = backend();
    loadPage(fetchMock);
    expect(section().classList.contains("is-signed-out")).toBe(true);

    signInWith("A", "12345");
    expect($("#login-name-error").textContent).toContain("name");
    expect($("#login-phone-error").textContent).toContain("10-digit mobile number");
    expect($("#login-phone").getAttribute("aria-invalid")).toBe("true");
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining("/api/users"), expect.anything());

    signInWith("Arun Kumar", "+91 98765 43210");
    await flush();
    await flush();
    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).includes("/api/users"));
    expect(JSON.parse(init.body)).toEqual({ name: "Arun Kumar", phone: "9876543210" });
    expect(section().classList.contains("is-signed-out")).toBe(false);
    expect($(".chat__name").textContent).toBe("Arun Kumar");
    expect(JSON.parse(window.localStorage.getItem("arivazhai-user"))).toEqual({ name: "Arun Kumar", token: "0123456789abcdef.signature" });
    expect(window.localStorage.getItem("arivazhai-user")).not.toContain("98765"); // the number is not kept here

    ask("Is there a hostel?");
    await flush();
    const [, chatInit] = fetchMock.mock.calls.find(([url]) => String(url).includes("/api/chat"));
    expect(chatInit.headers["X-Arivazhai-User"]).toBe("0123456789abcdef.signature");
  });

  it("asks again when the server no longer knows the visitor", async () => {
    window.localStorage.setItem("arivazhai-user", JSON.stringify({ name: "Arun", token: "0123456789abcdef.old" }));
    loadPage(backend({ chatStatus: 401 }));
    expect(section().classList.contains("is-signed-out")).toBe(false);
    ask("Is there a hostel?");
    await flush();
    await flush();
    expect(section().classList.contains("is-signed-out")).toBe(true);
    expect(window.localStorage.getItem("arivazhai-user")).toBeNull();
  });
});

describe("the conversation on this device", () => {
  it("comes back after a reload, and New chat deletes it after asking", async () => {
    window.localStorage.setItem("arivazhai-user", JSON.stringify({ name: "Arun", token: "0123456789abcdef.sig" }));
    loadPage(backend());
    ask("How do I get admission?");
    await flush();
    await flush();
    expect(JSON.parse(window.localStorage.getItem("arivazhai-history-0123456789abcdef"))).toHaveLength(2);

    loadPage(backend()); // a reload
    expect($(".message--user").textContent).toContain("How do I get admission?");
    expect($(".message--assistant .markdown strong").textContent).toBe("TNEA counselling");
    expect($("#welcome-suggestions").hidden).toBe(true);
    expect($(".chat__new").disabled).toBe(false);

    window.confirm = vi.fn(() => false); // "Keep this chat"
    $(".chat__new").click();
    await flush();
    expect(window.confirm.mock.calls[0][0]).toContain("will be deleted from this device");
    expect($$(".message--user")).toHaveLength(1);

    window.confirm = () => true; // "Delete and start new"
    $(".chat__new").click();
    await flush();
    expect($$(".message--user")).toHaveLength(0);
    expect(window.localStorage.getItem("arivazhai-history-0123456789abcdef")).toBeNull();
  });

  it("is kept per person: another sign-in on the same device starts empty", async () => {
    window.localStorage.setItem("arivazhai-user", JSON.stringify({ name: "Arun", token: "0123456789abcdef.sig" }));
    window.localStorage.setItem("arivazhai-history-0123456789abcdef", JSON.stringify([{ id: "a", role: "user", content: "Arun's question" }]));
    loadPage(backend());
    expect($(".message--user").textContent).toContain("Arun's question");
    $(".chat__signout").click();
    expect(section().classList.contains("is-signed-out")).toBe(true);
    expect($$(".message--user")).toHaveLength(0);
  });
});

describe("the page around the chat", () => {
  it("keeps the Arivazhai bar on screen and shows the college map under Apply", () => {
    loadPage();
    expect($(".chat__header").className).toContain("sticky");
    const panel = $(".help-panel");
    const apply = [...panel.querySelectorAll("a")].find((a) => a.textContent === "Apply for admission");
    const map = panel.querySelector("iframe");
    expect(apply.compareDocumentPosition(map) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(map.getAttribute("src")).toContain("output=embed");
    expect(map.getAttribute("title")).toContain("AAA College of Engineering and Technology");
  });
});

describe("asking by voice", () => {
  function fakeRecognition() {
    const made = [];
    window.SpeechRecognition = class {
      constructor() {
        made.push(this);
      }
      start() {}
      stop() {
        this.onend && this.onend();
      }
      abort() {
        this.onerror && this.onerror({ error: "aborted" });
        this.onend && this.onend();
      }
    };
    return made;
  }

  it("says when the voice cannot be heard", () => {
    vi.useFakeTimers();
    const made = fakeRecognition();
    const A = loadPage();
    const shown = vi.spyOn(A.robot.moments, "show");
    $(".chat-input__mic").click();
    made[0].onaudiostart();
    vi.advanceTimersByTime(4100); // no sound at all
    expect(shown).toHaveBeenCalledWith(expect.objectContaining({ title: "I can't hear you" }));
    expect($(".chat-input__status").textContent).toContain("speak a little louder");
    expect($(".chat-input__mic").getAttribute("aria-pressed")).toBe("false");
  });

  it("tells sound without clear words apart, and a missing microphone", () => {
    vi.useFakeTimers();
    const made = fakeRecognition();
    const A = loadPage();
    const shown = vi.spyOn(A.robot.moments, "show");
    $(".chat-input__mic").click();
    made[0].onaudiostart();
    made[0].onsoundstart();
    made[0].onspeechstart();
    expect($(".chat-input__status").textContent).toBe("I can hear you…");
    vi.advanceTimersByTime(7100); // a voice, but no words recognised
    expect(shown).toHaveBeenLastCalledWith(expect.objectContaining({ title: "I couldn't make out the words" }));

    $(".chat-input__mic").click();
    made[1].onerror({ error: "audio-capture" });
    expect(shown).toHaveBeenLastCalledWith(expect.objectContaining({ title: "No microphone found" }));
  });

  it("stays quiet when the words come through", () => {
    vi.useFakeTimers();
    const made = fakeRecognition();
    const A = loadPage();
    const shown = vi.spyOn(A.robot.moments, "show");
    $(".chat-input__mic").click();
    made[0].onaudiostart();
    made[0].onsoundstart();
    made[0].onresult({ results: [[{ transcript: "hostel fees" }]] });
    vi.advanceTimersByTime(8000);
    expect(shown).not.toHaveBeenCalledWith(expect.objectContaining({ kind: "unsure" }));
    expect(field().value).toBe("hostel fees");
  });
});
