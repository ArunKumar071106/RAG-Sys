import type { ChatResult, ChatTurn } from "./types";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
const TIMEOUT_MS = Number(import.meta.env.VITE_CHAT_TIMEOUT_MS ?? 90000);

export type ApiErrorKind = "network" | "timeout" | "rate_limited" | "starting" | "unavailable" | "invalid" | "server";

export class ApiError extends Error {
  constructor(public kind: ApiErrorKind, message: string, public status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

/** Resolve an API-relative path (e.g. "/api/images/x/file") against the configured backend. */
export function apiUrl(path: string): string {
  return /^https?:\/\//.test(path) ? path : `${API_BASE_URL}${path}`;
}

function messageFor(kind: ApiErrorKind, detail?: string): string {
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

export async function sendChat(message: string, history: ChatTurn[], signal?: AbortSignal): Promise<ChatResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  const onAbort = () => controller.abort("cancelled");
  signal?.addEventListener("abort", onAbort);
  let response: Response;
  try {
    response = await fetch(apiUrl("/api/chat"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
      signal: controller.signal,
    });
  } catch (err) {
    if (controller.signal.aborted && controller.signal.reason === "timeout") {
      throw new ApiError("timeout", messageFor("timeout"));
    }
    if (controller.signal.aborted) throw err;
    throw new ApiError("network", messageFor("network"));
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : undefined;
    } catch {
      /* non-JSON error body */
    }
    // A 503 with Retry-After means "starting up" (first-start index build, or the dev proxy
    // could not reach a backend that is still loading).
    const kind: ApiErrorKind =
      response.status === 429 ? "rate_limited"
      : response.status === 503 ? (response.headers.get("Retry-After") ? "starting" : "unavailable")
      : response.status === 422 || response.status === 413 ? "invalid" : "server";
    throw new ApiError(kind, messageFor(kind, kind === "invalid" ? detail : undefined), response.status);
  }
  return (await response.json()) as ChatResult;
}

/** Type-ahead questions for what has been typed so far; [] on any problem (suggestions are optional). */
export async function fetchSuggestions(typed: string, signal?: AbortSignal): Promise<string[]> {
  try {
    const response = await fetch(apiUrl(`/api/suggest?q=${encodeURIComponent(typed)}&limit=6`), { signal });
    if (!response.ok) return [];
    const body = await response.json();
    return Array.isArray(body?.suggestions) ? body.suggestions.filter((s: unknown) => typeof s === "string") : [];
  } catch {
    return [];
  }
}
