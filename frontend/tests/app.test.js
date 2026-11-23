import { afterEach, describe, expect, it, vi } from "vitest";
import { answerResult, flush, jsonResponse, loadPage } from "./load.js";

// The chat-app touches: greeting by name, Copy / Listen under answers, the ☰ menu, the jump arrow.
const $ = (selector) => document.querySelector(selector);

function ask(text) {
  const field = $("#chat-message");
  field.value = text;
  field.dispatchEvent(new Event("input", { bubbles: true }));
  field.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
}

function signedIn(name = "Meena") {
  window.localStorage.setItem("arivazhai-user", JSON.stringify({ name, token: "0123456789abcdef.sig" }));
}

afterEach(() => {
  window.localStorage.clear();
  document.documentElement.className = "";
  delete window.speechSynthesis;
  delete window.SpeechSynthesisUtterance;
});

describe("the chat app", () => {
  it("greets the visitor by name, with question cards", () => {
    signedIn("Meena");
    loadPage();
    expect($(".welcome__hello").textContent).toBe("Hello, Meena");
    expect($$cards()).toHaveLength(8);
    expect($$cards()[0].querySelector("svg")).not.toBeNull(); // each card has an icon
    expect($$cards()[0].textContent).toBe("What is the eligibility for B.E. / B.Tech admission?");
  });

  it("copies an answer without its citation marks", async () => {
    signedIn();
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(window.navigator, "clipboard", { value: { writeText }, configurable: true });
    loadPage(() => Promise.resolve(jsonResponse(answerResult)));
    ask("How do I get admission?");
    await flush();
    await flush();
    $('.feedback button[aria-label="Copy"]').click();
    await flush();
    expect(writeText.mock.calls[0][0]).toContain("Admission is through TNEA counselling");
    expect(writeText.mock.calls[0][0]).not.toMatch(/\[1\]/);
    expect($(".feedback").textContent).toContain("Copied");
  });

  it("reads an answer aloud, and stops on a second press", async () => {
    signedIn();
    const spoken = [];
    window.SpeechSynthesisUtterance = class {
      constructor(text) {
        this.text = text;
      }
    };
    window.speechSynthesis = { speak: (u) => spoken.push(u), cancel: vi.fn() };
    loadPage(() => Promise.resolve(jsonResponse(answerResult)));
    ask("How do I get admission?");
    await flush();
    await flush();
    const listen = $('.feedback button[aria-label="Listen"]');
    listen.click();
    expect(spoken[0].text).toContain("TNEA counselling");
    expect(spoken[0].lang).toBe("en-IN");
    expect(listen.getAttribute("aria-pressed")).toBe("true");
    expect(listen.getAttribute("aria-label")).toBe("Stop");
    listen.click();
    expect(window.speechSynthesis.cancel).toHaveBeenCalled();
    expect(listen.getAttribute("aria-pressed")).toBe("false");
  });

  it("opens the menu with ☰ and closes it with Esc, the backdrop or a link", () => {
    signedIn("Meena");
    loadPage();
    const root = document.documentElement;
    const menu = $(".chat__menu");
    menu.click();
    expect(root.classList.contains("drawer-open")).toBe(true);
    expect(menu.getAttribute("aria-expanded")).toBe("true");
    expect($(".drawer__user").textContent).toBe("Chatting as Meena");
    expect(document.activeElement).toBe($(".drawer__close"));
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(root.classList.contains("drawer-open")).toBe(false);
    menu.click();
    $(".drawer-backdrop").click();
    expect(root.classList.contains("drawer-open")).toBe(false);
    menu.click();
    $("#help-panel a").dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(root.classList.contains("drawer-open")).toBe(false);
  });

  it("signs out from the menu", () => {
    signedIn("Meena");
    loadPage();
    $(".chat__menu").click();
    $(".drawer__signout").click();
    expect($("#assistant").classList.contains("is-signed-out")).toBe(true);
    expect(document.documentElement.classList.contains("has-user")).toBe(false);
  });

  it("shows the jump arrow only when the conversation is scrolled up", () => {
    signedIn();
    loadPage();
    const log = $(".chat__log");
    const jump = $(".chat__jump");
    Object.defineProperty(log, "scrollHeight", { value: 2000, configurable: true });
    Object.defineProperty(log, "clientHeight", { value: 600, configurable: true });
    log.scrollTop = 200;
    log.dispatchEvent(new Event("scroll"));
    expect(jump.hidden).toBe(false);
    log.scrollTop = 1400;
    log.dispatchEvent(new Event("scroll"));
    expect(jump.hidden).toBe(true);
  });
});

function $$cards() {
  return [...document.querySelectorAll("#welcome-suggestions .chip")];
}
