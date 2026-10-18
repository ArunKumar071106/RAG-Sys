import type { ChatResult, ChatTurn } from "./types";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
const TIMEOUT_MS = Number(import.meta.env.VITE_CHAT_TIMEOUT_MS ?? 90000);

export type ApiErrorKind = "network" | "timeout" | "rate_limited" | "unavailable" | "invalid" | "server";

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
    const kind: ApiErrorKind =
      response.status === 429 ? "rate_limited" : response.status === 503 ? "unavailable" : response.status === 422 || response.status === 413 ? "invalid" : "server";
    throw new ApiError(kind, messageFor(kind, kind === "invalid" ? detail : undefined), response.status);
  }
  return (await response.json()) as ChatResult;
}
