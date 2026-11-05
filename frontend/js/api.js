/*
 * Talking to the backend: /api/chat, /api/translate, /api/suggest and /api/health.
 * Every failure becomes an ApiError with a kind the page can word for people.
 */
(function (A) {
  "use strict";

  const config = window.ARIVAZHAI_CONFIG || {};
  const API_BASE_URL = String(config.apiBaseUrl || "").replace(/\/+$/, "");
  const TIMEOUT_MS = Number(config.chatTimeoutMs) || 90000;

  class ApiError extends Error {
    constructor(kind, message, status) {
      super(message);
      this.name = "ApiError";
      this.kind = kind; // network | timeout | rate_limited | starting | unavailable | invalid | server
      this.status = status;
    }
  }

  /** An API path ("/api/images/x/file") on the configured backend. */
  function apiUrl(path) {
    return /^https?:\/\//.test(path) ? path : API_BASE_URL + path;
  }

  function messageFor(kind, detail) {
    switch (kind) {
      case "network":
        return "Can't reach the assistant right now. Please check your connection and try again.";
      case "timeout":
        return "The assistant took too long to respond. Please try again.";
      case "rate_limited":
        return "You're sending messages too quickly. Please wait a moment and try again.";
      case "starting":
        return "The assistant is still starting up. Please try again in a minute.";
      case "unavailable":
        return "The assistant is temporarily unavailable. Please try again later.";
      case "invalid":
        return detail || "That message couldn't be processed. Please rephrase and try again.";
      default:
        return "Something went wrong on our side. Please try again.";
    }
  }

  /** Abort after ms, or when the caller's signal aborts; reason says which. */
  function timed(ms, signal) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort("timeout"), ms);
    const onAbort = () => controller.abort("cancelled");
    if (signal) signal.addEventListener("abort", onAbort);
    return {
      signal: controller.signal,
      done() {
        clearTimeout(timer);
        if (signal) signal.removeEventListener("abort", onAbort);
      },
    };
  }

  /** Ask a question. history: the earlier turns, [{role, content}], most recent last. */
  async function sendChat(message, history, signal) {
    const t = timed(TIMEOUT_MS, signal);
    let response;
    try {
      response = await fetch(apiUrl("/api/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message, history: history }),
        signal: t.signal,
      });
    } catch (err) {
      if (t.signal.aborted && t.signal.reason === "timeout") throw new ApiError("timeout", messageFor("timeout"));
      if (t.signal.aborted) throw err; // cancelled by the page (New chat)
      throw new ApiError("network", messageFor("network"));
    } finally {
      t.done();
    }

    if (!response.ok) {
      let detail;
      try {
        const body = await response.json();
        detail = body && typeof body.detail === "string" ? body.detail : undefined;
      } catch (e) {
        /* not JSON */
      }
      // 503 with Retry-After: still starting (the first start builds the search index)
      const kind =
        response.status === 429 ? "rate_limited"
        : response.status === 503 ? (response.headers.get("Retry-After") ? "starting" : "unavailable")
        : response.status === 422 || response.status === 413 ? "invalid"
        : "server";
      throw new ApiError(kind, messageFor(kind, kind === "invalid" ? detail : undefined), response.status);
    }
    return response.json();
  }

  /** The English version of an answer given in another language (needs the AI answer service). */
  async function translateAnswer(text, signal) {
    let response;
    try {
      response = await fetch(apiUrl("/api/translate"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text, target: "English" }),
        signal: signal,
      });
    } catch (e) {
      throw new ApiError("network", messageFor("network"));
    }
    if (!response.ok) {
      const kind = response.status === 429 ? "rate_limited" : response.status === 503 ? "unavailable" : "server";
      throw new ApiError(kind, kind === "unavailable" ? "The English version is not available right now." : messageFor(kind), response.status);
    }
    const body = await response.json();
    return body && typeof body.text === "string" ? body.text : "";
  }

  /** Questions that complete what has been typed; [] on any problem (suggestions are optional). */
  async function fetchSuggestions(typed, signal) {
    try {
      const response = await fetch(apiUrl("/api/suggest?q=" + encodeURIComponent(typed) + "&limit=6"), { signal: signal });
      if (!response.ok) return [];
      const body = await response.json();
      return Array.isArray(body && body.suggestions) ? body.suggestions.filter((s) => typeof s === "string") : [];
    } catch (e) {
      return [];
    }
  }

  /** "ok" when the assistant can be reached (also while it builds its index), else the problem. */
  async function checkHealth(signal) {
    const t = timed(10000, signal);
    try {
      const response = await fetch(apiUrl("/api/health"), { signal: t.signal });
      if (response.ok) return "ok";
      return response.status === 503 ? "starting" : "unavailable";
    } catch (e) {
      return t.signal.reason === "timeout" ? "timeout" : "network";
    } finally {
      t.done();
    }
  }

  A.api = { ApiError, apiUrl, sendChat, translateAnswer, fetchSuggestions, checkHealth, messageFor };
})((window.Arivazhai = window.Arivazhai || {}));
