import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatInput } from "../components/ChatInput";

const SUGGESTIONS = [
  "Who are the faculty of the Artificial Intelligence and Data Science department?",
  "What labs does the Artificial Intelligence and Data Science department have?",
];

function setup() {
  const onSend = vi.fn();
  const suggest = vi.fn().mockResolvedValue(SUGGESTIONS);
  const user = userEvent.setup();
  render(<ChatInput onSend={onSend} suggest={suggest} />);
  const box = screen.getByLabelText("Ask a question about AAACET");
  return { onSend, suggest, user, box };
}

describe("ChatInput suggestions", () => {
  it("suggests questions while typing, with the typed words highlighted", async () => {
    const { suggest, user, box } = setup();
    await user.type(box, "ai&ds fac");
    const list = await screen.findByRole("listbox", { name: "Suggested questions" });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(SUGGESTIONS);
    expect(suggest).toHaveBeenLastCalledWith("ai&ds fac", expect.any(AbortSignal));
    expect(list.querySelector("strong")?.textContent).toBe("faculty");
    expect(box).toHaveAttribute("aria-expanded", "true");
  });

  it("asks the picked suggestion with the arrow keys and Enter", async () => {
    const { onSend, user, box } = setup();
    await user.type(box, "ai&ds");
    await screen.findByRole("listbox");
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
    expect(box).toHaveAttribute("aria-activedescendant", screen.getAllByRole("option")[1].id);
    await user.keyboard("{Enter}");
    expect(onSend).toHaveBeenCalledWith(SUGGESTIONS[1]);
    expect(box).toHaveValue("");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("sends what was typed when nothing is picked, and Escape closes the list", async () => {
    const { onSend, user, box } = setup();
    await user.type(box, "ai&ds hod");
    await screen.findByRole("listbox");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    await user.keyboard("{Enter}");
    expect(onSend).toHaveBeenCalledWith("ai&ds hod");
  });

  it("asks a clicked suggestion, and Tab copies one into the box to edit", async () => {
    const { onSend, user, box } = setup();
    await user.type(box, "ai&ds");
    await user.click(await screen.findByRole("option", { name: SUGGESTIONS[0] }));
    expect(onSend).toHaveBeenCalledWith(SUGGESTIONS[0]);

    await user.type(box, "ai&ds");
    await screen.findByRole("listbox");
    await user.keyboard("{ArrowDown}{Tab}");
    expect(box).toHaveValue(SUGGESTIONS[0]);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("does not ask for suggestions for a single character", async () => {
    const { suggest, user, box } = setup();
    await user.type(box, "a");
    await new Promise((r) => setTimeout(r, 250));
    expect(suggest).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
  });
});
