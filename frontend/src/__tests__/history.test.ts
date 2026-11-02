import { describe, expect, it } from "vitest";
import { historyFrom, type Message } from "../hooks/useChat";

describe("conversation history sent with a question", () => {
  it("keeps the start of long answers so the request stays small", () => {
    const table = "| Name | Designation |\n".repeat(1000);
    const messages = [
      { id: "1", role: "user", content: "faculty list" },
      { id: "2", role: "assistant", content: table },
      { id: "3", role: "user", content: "failed one", error: { kind: "network", message: "x" } },
    ] as unknown as Message[];
    const history = historyFrom(messages);
    expect(history).toHaveLength(2); // failed turns are left out
    expect(history[1].content.length).toBe(2000);
    expect(JSON.stringify(history).length).toBeLessThan(3000);
  });
});
