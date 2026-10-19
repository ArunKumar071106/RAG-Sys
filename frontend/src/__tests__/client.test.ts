import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiUrl, sendChat } from "../api/client";
import { answerResult, jsonResponse } from "../test/fixtures";

afterEach(() => vi.unstubAllGlobals());

describe("sendChat", () => {
  it("posts the message and history as JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(answerResult));
    vi.stubGlobal("fetch", fetchMock);
    const result = await sendChat("Hi there", [{ role: "user", content: "earlier" }]);
    expect(result.answer).toBe(answerResult.answer);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/chat$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ message: "Hi there", history: [{ role: "user", content: "earlier" }] });
  });

  it.each([
    [429, "rate_limited"],
    [503, "unavailable"],
    [422, "invalid"],
    [500, "server"],
  ])("maps HTTP %i to %s", async (status, kind) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "Message too long" }, status)));
    await expect(sendChat("x", [])).rejects.toMatchObject({ kind, status });
  });

  it("reports a 503 with Retry-After as starting up", async () => {
    const response = jsonResponse({ detail: "starting" }, 503);
    response.headers.set("Retry-After", "30");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    await expect(sendChat("x", [])).rejects.toMatchObject({ kind: "starting", message: expect.stringMatching(/starting up/) });
  });

  it("shows the server's validation detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "Message too long (max 1000 characters)" }, 422)));
    await expect(sendChat("x", [])).rejects.toThrow("Message too long (max 1000 characters)");
  });

  it("reports network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await sendChat("x", []).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.kind).toBe("network");
  });
});

describe("apiUrl", () => {
  it("leaves absolute URLs alone and prefixes relative API paths", () => {
    expect(apiUrl("https://cdn.example/x.png")).toBe("https://cdn.example/x.png");
    expect(apiUrl("/api/images/a/file")).toMatch(/\/api\/images\/a\/file$/);
  });
});
